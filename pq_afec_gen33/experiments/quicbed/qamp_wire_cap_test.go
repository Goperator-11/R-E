package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"hash/crc32"
	"io"
	"net"
	"testing"
	"time"

	"golang.org/x/sys/unix"
)

const wireCapHandoff = 1452

func wireCapFlight(ver, k, m, lead, wEff, dcidLen int, seed byte) ([][]byte, [][]byte) {
	dcid := bytes.Repeat([]byte{0xd1}, dcidLen)
	src := make([][]byte, k)
	crcs := make([]uint32, k)
	lens := make([]uint16, k)
	for i := range src {
		src[i] = leadTestInitial(dcid, leadTestSCID, wEff, seed+byte(i))
		crcs[i] = crc32.ChecksumIEEE(src[i])
		lens[i] = uint16(wEff)
	}
	syms := rsEncode(src, m, wEff)
	par := make([][]byte, m)
	for j := range par {
		par[j] = buildParity(dcid, leadTestSCID, fecBlock{ver: ver, flight: 1, k: k, m: m, lead: lead, index: j,
			symLen: wEff, crcs: crcs, lens: lens, sym: syms[j]})
	}
	return src, par
}

func wireCapServer(wide bool, dgs [][]byte) *decodeConn {
	s := &decodeConn{mode: "fec", wideRead: wide}
	s.PacketConn = &scriptConn{dgs: dgs, addr: &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: 5555}}
	return s
}

func wireCapDrain(s *decodeConn) [][]byte {
	out := [][]byte{}
	for {
		b := make([]byte, wireCapHandoff)
		n, _, err := s.ReadFrom(b)
		if err != nil {
			return out
		}
		out = append(out, append([]byte(nil), b[:n]...))
	}
}

func wireCapAccount(t *testing.T, s *decodeConn) *connAcct {
	t.Helper()
	if len(s.conns) != 1 {
		t.Fatalf("accounts %d", len(s.conns))
	}
	for _, ca := range s.conns {
		return ca
	}
	return nil
}

func TestOversizeParityRecoversWithWideRead(t *testing.T) {
	gfInit()
	for _, tc := range []struct{ ver, k, wEff, minD int }{
		{fecVerLead, 1, 1407, 14},
		{fecVerLead, 3, 1394, 15},
		{fecVerLead, 4, 1387, 16},
		{fecVer, 2, 1406, 9},
	} {
		for d := tc.minD; d <= 20; d++ {
			t.Run(fmt.Sprintf("v%d/k%d/w%d/d%d", tc.ver, tc.k, tc.wEff, d), func(t *testing.T) {
				src, par := wireCapFlight(tc.ver, tc.k, 1, 0, tc.wEff, d, byte(d))
				if len(par[0]) != tc.wEff+22+d+4+6*tc.k || len(par[0]) <= wireCapHandoff {
					t.Fatalf("fixture wire size %d", len(par[0]))
				}
				s := wireCapServer(true, append(append([][]byte{}, src[1:]...), par[0]))
				out := wireCapDrain(s)
				if len(out) != tc.k || !bytes.Equal(out[tc.k-1], src[0]) {
					t.Fatalf("lost original not recovered: %d datagrams, recovered %d parse_fail %d", len(out), s.stats.Recovered, s.stats.FecParseFail)
				}
				if s.stats.Recovered != 1 || s.stats.FecParseFail != 0 || s.stats.FecOversizeRead != 1 {
					t.Fatalf("recovered %d parse_fail %d oversize %d", s.stats.Recovered, s.stats.FecParseFail, s.stats.FecOversizeRead)
				}
				if s.stats.BytesToStack > s.stats.BytesIn {
					t.Fatalf("credit %d over arrivals %d", s.stats.BytesToStack, s.stats.BytesIn)
				}
			})
		}
	}
}

func TestOversizeCreditParityKeepsHandoff(t *testing.T) {
	gfInit()
	_, par := wireCapFlight(fecVerLead, 3, 2, 1, 1394, 20, 7)
	if len(par[0]) != 1458 {
		t.Fatalf("fixture wire size %d", len(par[0]))
	}
	for _, wide := range []bool{false, true} {
		t.Run(fmt.Sprintf("wide_%v", wide), func(t *testing.T) {
			s := wireCapServer(wide, [][]byte{par[0]})
			out := wireCapDrain(s)
			if len(out) != 1 || !bytes.Equal(out[0], par[0][:wireCapHandoff]) {
				t.Fatalf("handoff %d datagrams", len(out))
			}
			if s.stats.BytesIn != wireCapHandoff || s.stats.BytesToStack != wireCapHandoff {
				t.Fatalf("bytes in %d to stack %d", s.stats.BytesIn, s.stats.BytesToStack)
			}
			ca := wireCapAccount(t, s)
			whole := inCRC(ca.RxCRC, crc32.ChecksumIEEE(par[0]))
			if wide {
				if s.stats.CreditParities != 1 || ca.RxParityN != 1 || ca.RxOrigN != 0 || s.stats.FecParseFail != 0 || s.stats.FecOversizeRead != 1 || !whole {
					t.Fatalf("credit %d parity_n %d orig_n %d parse_fail %d oversize %d crc %v", s.stats.CreditParities, ca.RxParityN, ca.RxOrigN, s.stats.FecParseFail, s.stats.FecOversizeRead, whole)
				}
			} else if s.stats.CreditParities != 0 || ca.RxParityN != 0 || ca.RxOrigN != 1 || s.stats.FecParseFail != 1 || s.stats.FecOversizeRead != 0 || whole {
				t.Fatalf("credit %d parity_n %d orig_n %d parse_fail %d oversize %d crc %v", s.stats.CreditParities, ca.RxParityN, ca.RxOrigN, s.stats.FecParseFail, s.stats.FecOversizeRead, whole)
			}
		})
	}
}

func TestWideReadMatchesNarrowUpTo1452(t *testing.T) {
	gfInit()
	for _, tc := range []struct{ k, m, lead, wEff, d int }{
		{2, 3, 1, 1280, 8},
		{2, 3, 1, 1280, 20},
		{2, 1, 0, 1394, 20},
		{3, 2, 1, 1388, 20},
		{1, 2, 1, 1400, 20},
	} {
		src, par := wireCapFlight(fecVerLead, tc.k, tc.m, tc.lead, tc.wEff, tc.d, 23)
		dgs := append(append([][]byte{}, par...), src...)
		for _, d := range dgs {
			if len(d) > wireCapHandoff {
				t.Fatalf("fixture over handoff %d", len(d))
			}
		}
		seen := 0
		leadOrders(len(dgs), func(ord []int) {
			seen++
			script := make([][]byte, len(ord))
			for i, x := range ord {
				script[i] = dgs[x]
			}
			narrow, wide := wireCapServer(false, script), wireCapServer(true, script)
			a, b := wireCapDrain(narrow), wireCapDrain(wide)
			if len(a) != len(b) {
				t.Fatalf("order %v: %d vs %d", ord, len(a), len(b))
			}
			for i := range a {
				if !bytes.Equal(a[i], b[i]) {
					t.Fatalf("order %v datagram %d differs", ord, i)
				}
			}
			x, _ := json.Marshal(narrow.stats)
			y, _ := json.Marshal(wide.stats)
			if !bytes.Equal(x, y) {
				t.Fatalf("order %v stats\n%s\n%s", ord, x, y)
			}
		})
		if seen == 0 {
			t.Fatal("no arrival orders")
		}
	}
}

func TestOversizeParityUDPMessagePath(t *testing.T) {
	gfInit()
	src, par := wireCapFlight(fecVerLead, 3, 2, 1, 1394, 20, 11)
	c, wire := udpTestConn([][]byte{par[0], src[1], src[2], par[1]}, false)
	c.wideRead = true
	read := func(i int) ([]byte, int) {
		b, oob := make([]byte, wireCapHandoff), make([]byte, 128)
		n, nn, flags, _, err := c.ReadMsgUDP(b, oob)
		if err != nil {
			t.Fatal(err)
		}
		if i < 3 && !bytes.Equal(oob[:nn], wire.metas[i].oob) {
			t.Fatalf("read %d control data", i)
		}
		return b[:n], flags
	}
	d, flags := read(0)
	if !bytes.Equal(d, par[0][:wireCapHandoff]) || flags&unix.MSG_TRUNC == 0 {
		t.Fatalf("credit handoff %d flags %x", len(d), flags)
	}
	for i, want := range [][]byte{src[1], src[2]} {
		if d, flags = read(i + 1); !bytes.Equal(d, want) || flags&unix.MSG_TRUNC != 0 {
			t.Fatalf("original %d flags %x", i, flags)
		}
	}
	if d, flags = read(3); !bytes.Equal(d, src[0]) || flags&unix.MSG_TRUNC != 0 {
		t.Fatalf("recovery %d flags %x recovered %d", len(d), flags, c.stats.Recovered)
	}
	if c.stats.Recovered != 1 || c.stats.CreditParities != 1 || c.stats.FecParseFail != 0 || c.stats.UDPReadMsg != 4 {
		t.Fatalf("recovered %d credit %d parse_fail %d read_msg %d", c.stats.Recovered, c.stats.CreditParities, c.stats.FecParseFail, c.stats.UDPReadMsg)
	}
}

func TestOversizeParityHoldRecovers(t *testing.T) {
	gfInit()
	src, par := wireCapFlight(fecVerLead, 3, 2, 1, 1394, 20, 13)
	s, _ := holdTestConn([][]byte{par[0], src[1], src[2], par[1]}, defaultHoldConfig())
	s.wideRead = true
	found := false
	for i := 0; i < 30; i++ {
		b := make([]byte, wireCapHandoff)
		n, _, err := s.ReadFrom(b)
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			t.Fatal(err)
		}
		if bytes.Equal(b[:n], src[0]) {
			found = true
		}
		if s.stats.BytesToStack+s.pendingBytes > s.stats.BytesIn {
			t.Fatalf("credit %d pending %d over arrivals %d", s.stats.BytesToStack, s.pendingBytes, s.stats.BytesIn)
		}
	}
	if !found || s.stats.Recovered != 1 || s.stats.FecParseFail != 0 || s.stats.FecOversizeRead != 2 {
		t.Fatalf("found %v recovered %d parse_fail %d oversize %d", found, s.stats.Recovered, s.stats.FecParseFail, s.stats.FecOversizeRead)
	}
}

func TestOversizeParityHoldDeadlineUsesWireLength(t *testing.T) {
	gfInit()
	config := defaultHoldConfig()
	for _, tc := range []struct {
		name string
		d    int
		wide bool
		wire int
	}{{"oversize_wide", 20, true, 1458}, {"fit_narrow", 8, false, 1446}, {"fit_wide", 8, true, 1446}} {
		t.Run(tc.name, func(t *testing.T) {
			src, par := wireCapFlight(fecVerLead, 3, 2, 1, 1394, tc.d, 29)
			if len(par[0]) != tc.wire {
				t.Fatalf("fixture wire size %d", len(par[0]))
			}
			originals := 0
			for _, o := range src {
				originals += len(o)
			}
			remaining := int64(len(par[0]) + originals)
			want := config.margin + time.Duration((remaining*8_000_000+config.uplinkKbps-1)/config.uplinkKbps)
			s, c := holdTestConn([][]byte{par[0]}, config)
			s.wideRead = tc.wide
			var got []time.Duration
			c.check = func() {
				for _, fr := range s.hold.flights {
					got = append(got, fr.deadline.Sub(fr.created))
				}
			}
			for i := 0; i < 10; i++ {
				if _, _, err := s.ReadFrom(make([]byte, wireCapHandoff)); err != nil {
					break
				}
			}
			if len(got) == 0 || got[0] != want {
				t.Fatalf("hold deadline %v, want %v from wire length %d", got, want, len(par[0]))
			}
		})
	}
}

type wireErrConn struct {
	net.PacketConn
	data []byte
	err  error
}

func (c *wireErrConn) ReadFrom(b []byte) (int, net.Addr, error) {
	return copy(b, c.data), &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: 5555}, c.err
}

func TestWideReadErrorReturnsCallerBytes(t *testing.T) {
	data := make([]byte, udpMaxPayload)
	for i := range data {
		data[i] = byte(i*7 + 3)
	}
	fail := errors.New("read failed after data")
	for _, tc := range []struct {
		name string
		wide bool
		mode string
		size int
	}{{"wide", true, "fec", wireCapHandoff}, {"narrow", false, "fec", wireCapHandoff}, {"wide_off_mode", true, "off", wireCapHandoff},
		{"wide_full_buffer", true, "fec", udpMaxPayload}} {
		t.Run(tc.name, func(t *testing.T) {
			s := &decodeConn{mode: tc.mode, wideRead: tc.wide}
			s.PacketConn = &wireErrConn{data: data, err: fail}
			b := make([]byte, tc.size)
			n, _, err := s.ReadFrom(b)
			if !errors.Is(err, fail) || n != tc.size || !bytes.Equal(b[:n], data[:n]) {
				t.Fatalf("n %d err %v bytes match %v", n, err, n <= len(b) && bytes.Equal(b[:min(n, len(b))], data[:min(n, len(b))]))
			}
		})
	}
}

func TestOversizeParityRealSocket(t *testing.T) {
	gfInit()
	_, par := wireCapFlight(fecVerLead, 3, 2, 1, 1394, 20, 17)
	for _, tc := range []struct {
		path string
		wide bool
	}{{"basic", false}, {"basic", true}, {"oob", false}, {"oob", true}} {
		t.Run(fmt.Sprintf("%s/wide_%v", tc.path, tc.wide), func(t *testing.T) {
			udp, err := net.ListenUDP("udp4", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1)})
			if err != nil {
				t.Fatal(err)
			}
			defer udp.Close()
			sender, err := net.DialUDP("udp4", nil, udp.LocalAddr().(*net.UDPAddr))
			if err != nil {
				t.Fatal(err)
			}
			defer sender.Close()
			if _, err := sender.Write(par[0]); err != nil {
				t.Fatal(err)
			}
			if err := udp.SetReadDeadline(time.Now().Add(5 * time.Second)); err != nil {
				t.Fatal(err)
			}
			s := &decodeConn{countConn: countConn{PacketConn: udp}, mode: "fec", wideRead: tc.wide}
			b := make([]byte, wireCapHandoff)
			var n int
			if tc.path == "oob" {
				n, _, _, _, err = newUDPDecodeConn(s, udp).ReadMsgUDP(b, make([]byte, 128))
			} else {
				n, _, err = s.ReadFrom(b)
			}
			if err != nil {
				t.Fatal(err)
			}
			if n != wireCapHandoff || !bytes.Equal(b[:n], par[0][:n]) {
				t.Fatalf("handoff %d", n)
			}
			parsed, failed := 0, 1
			if tc.wide {
				parsed, failed = 1, 0
			}
			if s.stats.CreditParities != parsed || s.stats.FecParseFail != failed {
				t.Fatalf("credit %d parse_fail %d", s.stats.CreditParities, s.stats.FecParseFail)
			}
		})
	}
}

func TestWideReadProfile(t *testing.T) {
	if !wideReadFor("") || wideReadFor(profileSealed31) {
		t.Fatal("default profile reads wide and sealed31 keeps the 1452 B read")
	}
}

func TestAuto3ParityWarning(t *testing.T) {
	const top = "auto3: no parity candidate above W 1407"
	k2 := "auto3: no parity candidate for k>=2 above W 1401"
	k3 := "auto3: no parity candidate for k>=3 above W 1395"
	k4 := "auto3: no parity candidate for k>=4 above W 1389"
	for _, tc := range []struct {
		ips, expectK int
		want         string
	}{
		{0, 0, ""}, {1280, 0, ""}, {1389, 0, ""},
		{1390, 0, k4}, {1395, 0, k4}, {1396, 0, k3}, {1401, 0, k3}, {1402, 0, k2}, {1406, 0, k2}, {1407, 0, k2},
		{1408, 0, top}, {1452, 0, top},
		{1406, 1, ""}, {1406, 2, k2}, {1406, 4, k2}, {1396, 2, ""}, {1396, 3, k3}, {1390, 3, ""}, {1390, 4, k4}, {1408, 1, top},
	} {
		if got := auto3ParityWarning(tc.ips, tc.expectK); got != tc.want {
			t.Errorf("ips %d expect-k %d: %q, want %q", tc.ips, tc.expectK, got, tc.want)
		}
	}
}
