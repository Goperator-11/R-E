package main

import (
	"bytes"
	"crypto/tls"
	"encoding/binary"
	"errors"
	"io"
	"net"
	"syscall"
	"testing"
	"time"

	"github.com/quic-go/quic-go"
	"golang.org/x/net/ipv4"
	"golang.org/x/net/ipv6"
	"golang.org/x/sys/unix"
)

var _ quic.OOBCapablePacketConn = (*udpDecodeConn)(nil)
var _ interface {
	ReadBatch([]ipv4.Message, int) (int, error)
} = (*udpDecodeConn)(nil)

type udpTestWire struct {
	*holdScriptConn
	metas               []packetMeta
	written             [][]byte
	controls            [][]byte
	send                func([]byte, []byte) (int, int, error)
	readSize, writeSize int
}

func (w *udpTestWire) SyscallConn() (syscall.RawConn, error) { return nil, syscall.ENOTSUP }
func (w *udpTestWire) SetReadBuffer(n int) error             { w.readSize = n; return nil }
func (w *udpTestWire) SetWriteBuffer(n int) error            { w.writeSize = n; return nil }
func (w *udpTestWire) ReadMsgUDP(b, oob []byte) (int, int, int, *net.UDPAddr, error) {
	i := w.i
	n, a, err := w.holdScriptConn.ReadFrom(b)
	if err != nil {
		return n, 0, 0, nil, err
	}
	meta := packetMeta{}
	if i < len(w.metas) {
		meta = w.metas[i]
	}
	flags := meta.flags
	if n < len(w.frames[i].data) {
		flags |= unix.MSG_TRUNC
	}
	nn := copy(oob, meta.oob)
	if nn < len(meta.oob) {
		flags |= unix.MSG_CTRUNC
	}
	return n, nn, flags, a.(*net.UDPAddr), nil
}
func (w *udpTestWire) WriteMsgUDP(b, oob []byte, a *net.UDPAddr) (int, int, error) {
	w.written = append(w.written, append([]byte(nil), b...))
	w.controls = append(w.controls, append([]byte(nil), oob...))
	if w.send != nil {
		return w.send(b, oob)
	}
	return len(b), len(oob), nil
}
func (w *udpTestWire) WriteTo(b []byte, a net.Addr) (int, error) {
	n, _, err := w.WriteMsgUDP(b, nil, a.(*net.UDPAddr))
	return n, err
}

func udpTestMeta(last byte) packetMeta {
	body := make([]byte, 12)
	binary.NativeEndian.PutUint32(body, 1)
	copy(body[8:], net.IPv4(127, 0, 0, last).To4())
	return packetMeta{oob: append(socketControl(unix.IPPROTO_IP, unix.IP_PKTINFO, body), socketControl(unix.IPPROTO_IP, unix.IP_TOS, []byte{3})...)}
}

func udpTestConn(data [][]byte, hold bool) (*udpDecodeConn, *udpTestWire) {
	s, c := holdTestConn(data, defaultHoldConfig())
	if !hold {
		s.hold = nil
	}
	w := &udpTestWire{holdScriptConn: c}
	for i := range data {
		w.metas = append(w.metas, udpTestMeta(byte(i+2)))
	}
	s.PacketConn = w
	return newUDPDecodeConn(s, w), w
}

func udpReadTest(t *testing.T, c *udpDecodeConn) ([]byte, packetMeta) {
	t.Helper()
	b, oob := make([]byte, 2000), make([]byte, 128)
	n, nn, flags, _, err := c.ReadMsgUDP(b, oob)
	if err != nil {
		t.Fatal(err)
	}
	return b[:n], packetMeta{oob[:nn], flags}
}

func TestUDPMetadataRecoveryAndReply(t *testing.T) {
	m := udpTestMeta(2)
	m.flags = unix.MSG_TRUNC
	rec := m.recovery()
	msgs, err := unix.ParseSocketControlMessage(rec.oob)
	if err != nil || len(msgs) != 1 || msgs[0].Header.Type != unix.IP_PKTINFO || rec.flags != 0 {
		t.Fatal(msgs, rec.flags, err)
	}
	replies, err := unix.ParseSocketControlMessage(m.reply())
	if err != nil || len(replies) != 1 {
		t.Fatal(replies, err)
	}
	if r := replies[0]; r.Header.Type != unix.IP_PKTINFO || len(r.Data) != 12 || !net.IP(r.Data[4:8]).Equal(net.IPv4(127, 0, 0, 2)) || binary.NativeEndian.Uint32(r.Data) != 1 {
		t.Fatal("IPv4 send packet-info", r)
	}
	body := make([]byte, 20)
	copy(body, net.ParseIP("2001:db8::2"))
	binary.NativeEndian.PutUint32(body[16:], 7)
	v6 := packetMeta{oob: append(socketControl(unix.IPPROTO_IPV6, unix.IPV6_PKTINFO, body), socketControl(unix.IPPROTO_IPV6, unix.IPV6_TCLASS, []byte{3, 0, 0, 0})...)}
	messages, err := unix.ParseSocketControlMessage(v6.recovery().oob)
	if err != nil || len(messages) != 1 || messages[0].Header.Type != unix.IPV6_PKTINFO {
		t.Fatal(messages, err)
	}
	replies6, err := unix.ParseSocketControlMessage(v6.reply())
	if err != nil || len(replies6) != 1 {
		t.Fatal(replies6, err)
	}
	if r := replies6[0]; r.Header.Type != unix.IPV6_PKTINFO || len(r.Data) != 20 || !net.IP(r.Data[:16]).Equal(net.ParseIP("2001:db8::2")) || binary.NativeEndian.Uint32(r.Data[16:]) != 7 {
		t.Fatal("IPv6 send packet-info", r)
	}
	if len((packetMeta{oob: []byte{1}}).recovery().oob) != 0 {
		t.Fatal("malformed control copied")
	}
}

func TestUDPReadBatchRunsDecoder(t *testing.T) {
	gfInit()
	dg, src := leadBuildFlight(fecVer, 0, 1, 1, 11)
	c, w := udpTestConn([][]byte{dg[1].data}, false)
	ms := []ipv4.Message{{Buffers: [][]byte{make([]byte, 2000)}, OOB: make([]byte, 128)}, {N: 99}}
	n, err := c.ReadBatch(ms, 0)
	if err != nil || n != 1 || !bytes.Equal(ms[0].Buffers[0][:ms[0].N], src[0]) || ms[1].N != 99 {
		t.Fatal(n, err, ms[0].N)
	}
	if !bytes.Equal(ms[0].OOB[:ms[0].NN], w.metas[0].recovery().oob) || c.stats.Recovered != 1 || c.stats.UDPReadMsg != 1 || c.stats.UDPReadBatch != 1 {
		t.Fatal(c.stats)
	}
	if err := c.SetReadBuffer(123); err != nil {
		t.Fatal(err)
	}
	if err := c.SetWriteBuffer(456); err != nil {
		t.Fatal(err)
	}
	if w.readSize != 123 || w.writeSize != 456 {
		t.Fatal("buffer forwarding")
	}
	if _, err := c.ReadBatch(ms, unix.MSG_DONTWAIT); !errors.Is(err, syscall.EINVAL) {
		t.Fatal(err)
	}
	if n, err := c.ReadBatch(nil, 0); n != 0 || err != nil {
		t.Fatal(n, err)
	}
}

func TestUDPReadRawScatterAndTruncation(t *testing.T) {
	data := auditInitial(19)
	c, w := udpTestConn([][]byte{data, data}, false)
	c.mode = "off"
	ms := []ipv4.Message{{Buffers: [][]byte{make([]byte, 4), make([]byte, len(data)-4)}, OOB: make([]byte, 128)}}
	if n, err := c.ReadBatch(ms, 0); err != nil || n != 1 {
		t.Fatal(n, err)
	}
	if !bytes.Equal(append(ms[0].Buffers[0], ms[0].Buffers[1]...), data) || !bytes.Equal(ms[0].OOB[:ms[0].NN], w.metas[0].oob) {
		t.Fatal("raw scatter or metadata")
	}
	b := make([]byte, 5)
	oob := make([]byte, 1)
	n, nn, flags, _, err := c.ReadMsgUDP(b, oob)
	if err != nil || n != 5 || nn != 1 || flags&unix.MSG_TRUNC == 0 || flags&unix.MSG_CTRUNC == 0 {
		t.Fatal(n, nn, flags, err)
	}
}

func TestUDPHoldTimerKeepsEachPacketMetadata(t *testing.T) {
	gfInit()
	dg, src := leadBuildFlight(fecVerLead, 2, 2, 2, 41)
	c, w := udpTestConn([][]byte{dg[0].data, dg[1].data, src[0]}, true)
	expected := [][]byte{src[0], dg[1].data, src[1]}
	metas := []packetMeta{w.metas[2], w.metas[1], w.metas[0].recovery()}
	for i := range expected {
		b, m := udpReadTest(t, c)
		if !bytes.Equal(b, expected[i]) || !bytes.Equal(m.oob, metas[i].oob) || m.flags != 0 {
			t.Fatal("timer metadata", i, m, metas[i])
		}
	}
	if c.stats.Recovered != 1 || c.stats.UDPReadMsg != 3 {
		t.Fatal(c.stats)
	}
}

func TestUDPHoldOriginalAndRecoveryOrderMetadata(t *testing.T) {
	gfInit()
	dg, src := leadBuildFlight(fecVerLead, 2, 4, 4, 51)
	c, w := udpTestConn([][]byte{dg[0].data, dg[1].data, dg[6].data, src[0]}, true)
	for i := range src {
		b, m := udpReadTest(t, c)
		want := w.metas[0].recovery()
		if i == 0 {
			want = w.metas[3]
		}
		if !bytes.Equal(b, src[i]) || !bytes.Equal(m.oob, want.oob) {
			t.Fatal("pending metadata", i, m, want)
		}
	}
}

func TestUDPLegacyPendingIsolatesConnectionMetadata(t *testing.T) {
	gfInit()
	dg, src := leadBuildFlight(fecVer, 1, 3, 2, 71)
	foreign := leadTestInitial([]byte{5, 5, 5, 5}, []byte{6, 6, 6, 6}, 1200, 88)
	c, w := udpTestConn([][]byte{dg[3].data, foreign, dg[4].data}, false)
	got, meta := udpReadTest(t, c)
	if !bytes.Equal(got, foreign) || !bytes.Equal(meta.oob, w.metas[1].oob) {
		t.Fatal("foreign raw")
	}
	for i := range src {
		got, meta = udpReadTest(t, c)
		if !bytes.Equal(got, src[i]) || !bytes.Equal(meta.oob, w.metas[0].recovery().oob) {
			t.Fatal("legacy recovered", i)
		}
	}
	if c.stats.Recovered != 2 {
		t.Fatal(c.stats)
	}
}

func TestUDPPendingTruncationFlags(t *testing.T) {
	c, _ := udpTestConn(nil, false)
	ca := &connAcct{RxBytes: 100}
	c.stats.BytesIn = 100
	c.queuePendingLocked(pendingPkt{data: make([]byte, 100), addr: &net.UDPAddr{Port: 1}, acct: ca, meta: udpTestMeta(2).recovery()})
	n, _, flags, _, err := c.ReadMsgUDP(make([]byte, 10), make([]byte, 128))
	if err != nil || n != 10 || flags&unix.MSG_TRUNC == 0 || c.stats.BytesToStack != 10 {
		t.Fatal(n, flags, err, c.stats)
	}
}

func udpGSOControl(size uint16) []byte {
	return socketControl(unix.IPPROTO_UDP, unix.UDP_SEGMENT, binary.NativeEndian.AppendUint16(nil, size))
}

func TestUDPGSOSegmentAccounting(t *testing.T) {
	c, w := udpTestConn(nil, false)
	addr := &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: 4555}
	a := c.acctLocked(addr, accountingPacket(0, []byte{1}, []byte{11}), false)
	b := c.acctLocked(addr, accountingPacket(0, []byte{2}, []byte{12}), false)
	a.Stack, a.RxBytes = 100, 200
	b.Stack, b.RxBytes = 300, 400
	first := accountingPacket(0, []byte{11}, []byte{21})
	second := accountingPacket(0, []byte{12}, []byte{22})
	payload := append(append(append([]byte(nil), first...), second...), first...)
	control := udpGSOControl(uint16(len(first)))
	w.send = func(data, oob []byte) (int, int, error) {
		if !bytes.Equal(data, payload) || !bytes.Equal(oob, control) || a.TxDgrams != 2 || b.TxDgrams != 1 {
			t.Fatal("pre-write segments")
		}
		c.mu.Lock()
		a.Stack += 7
		a.RxBytes += 7
		c.mu.Unlock()
		return len(data), len(oob), nil
	}
	if n, nn, err := c.WriteMsgUDP(payload, control, addr); err != nil || n != len(payload) || nn != len(control) {
		t.Fatal(n, nn, err)
	}
	if a.BeffStack != 100 || b.BeffStack != 300 || a.BeffPhys != 200 || a.Stack != 107 || a.TxBytes != int64(2*len(first)) || b.TxBytes != int64(len(second)) {
		t.Fatal(a, b)
	}
	if c.TxDgrams != 3 || c.TxBytes != int64(len(payload)) || c.stats.UDPGSOCalls != 1 || c.stats.UDPGSOSegments != 3 {
		t.Fatal(c.stats, c.TxDgrams, c.TxBytes)
	}
}

func TestUDPFailedGSORollbackAndFallback(t *testing.T) {
	for _, short := range []bool{false, true} {
		c, w := udpTestConn(nil, false)
		addr := &net.UDPAddr{Port: 4555}
		ca := c.acctLocked(addr, accountingPacket(0, []byte{1}, []byte{11}), false)
		ca.Stack, ca.RxBytes = 100, 200
		one := accountingPacket(0, []byte{11}, []byte{21})
		payload := append(append([]byte(nil), one...), one...)
		w.send = func(data, oob []byte) (int, int, error) {
			c.mu.Lock()
			ca.Stack += 10
			ca.RxBytes += 10
			c.mu.Unlock()
			if short {
				return 1, 0, nil
			}
			return 0, 0, syscall.EIO
		}
		_, _, err := c.WriteMsgUDP(payload, udpGSOControl(uint16(len(one))), addr)
		if err == nil || ca.TxDgrams != 0 || ca.TxBytes != 0 || ca.FirstTxNs != 0 || len(ca.TxNs) != 0 || ca.Stack != 110 || ca.RxBytes != 210 || c.TxDgrams != 0 {
			t.Fatal("rollback", short, err, ca)
		}
		w.send = nil
		for i := 0; i < 2; i++ {
			if _, err := c.WriteTo(one, addr); err != nil {
				t.Fatal(err)
			}
		}
		if ca.TxDgrams != 2 || c.TxDgrams != 2 || ca.BeffStack != 110 || ca.TxBytes != int64(2*len(one)) || c.stats.UDPWriteErrors != 1 || c.stats.UDPGSOCalls != 0 {
			t.Fatal("fallback", ca, c.stats)
		}
	}
}

func TestUDPSegmentControlValidation(t *testing.T) {
	for _, oob := range [][]byte{udpGSOControl(0), append(udpGSOControl(10), udpGSOControl(11)...), socketControl(unix.IPPROTO_UDP, unix.UDP_SEGMENT, []byte{1})} {
		if _, err := udpSegmentSize(oob); err == nil {
			t.Fatal("accepted invalid segment", oob)
		}
	}
	if size, err := udpSegmentSize(nil); size != 0 || err != nil {
		t.Fatal(size, err)
	}
}

func TestUDPRealSocketDestinationECNAndFeedback(t *testing.T) {
	gfInit()
	for _, network := range []string{"udp4", "udp6"} {
		t.Run(network, func(t *testing.T) {
			bind, target := net.IPv4zero, net.IPv4(127, 0, 0, 2)
			if network == "udp6" {
				bind, target = net.IPv6zero, net.IPv6loopback
			}
			server, err := net.ListenUDP(network, &net.UDPAddr{IP: bind})
			if err != nil {
				t.Fatal(err)
			}
			defer server.Close()
			client, err := net.ListenUDP(network, &net.UDPAddr{IP: target})
			if err != nil {
				t.Fatal(err)
			}
			defer client.Close()
			if network == "udp4" {
				pc := ipv4.NewPacketConn(server)
				if err := pc.SetControlMessage(ipv4.FlagDst|ipv4.FlagInterface, true); err != nil {
					t.Fatal(err)
				}
				if err := ipv4.NewPacketConn(client).SetTOS(3); err != nil {
					t.Fatal(err)
				}
				raw, _ := server.SyscallConn()
				var se error
				raw.Control(func(fd uintptr) { se = unix.SetsockoptInt(int(fd), unix.IPPROTO_IP, unix.IP_RECVTOS, 1) })
				if se != nil {
					t.Fatal(se)
				}
			} else {
				pc := ipv6.NewPacketConn(server)
				if err := pc.SetControlMessage(ipv6.FlagDst|ipv6.FlagInterface|ipv6.FlagTrafficClass, true); err != nil {
					t.Fatal(err)
				}
				if err := ipv6.NewPacketConn(client).SetTrafficClass(3); err != nil {
					t.Fatal(err)
				}
			}
			c := newUDPDecodeConn(&decodeConn{countConn: countConn{PacketConn: server}, mode: "fec"}, server)
			if _, err := c.SyscallConn(); err != nil {
				t.Fatal(err)
			}
			if err := c.SetReadBuffer(1 << 20); err != nil {
				t.Fatal(err)
			}
			if err := c.SetWriteBuffer(1 << 20); err != nil {
				t.Fatal(err)
			}
			dst := &net.UDPAddr{IP: target, Port: server.LocalAddr().(*net.UDPAddr).Port}
			server.SetReadDeadline(time.Now().Add(2 * time.Second))
			client.SetReadDeadline(time.Now().Add(2 * time.Second))
			original := auditInitial(1)
			if _, err := client.WriteToUDP(original, dst); err != nil {
				t.Fatal(err)
			}
			got, raw := udpReadTest(t, c)
			if !bytes.Equal(got, original) {
				t.Fatal("real raw")
			}
			msgs, err := unix.ParseSocketControlMessage(raw.oob)
			if err != nil {
				t.Fatal(err)
			}
			ecn := false
			for _, m := range msgs {
				if (m.Header.Type == unix.IP_TOS && m.Header.Level == unix.IPPROTO_IP) || (m.Header.Type == unix.IPV6_TCLASS && m.Header.Level == unix.IPPROTO_IPV6) {
					ecn = len(m.Data) > 0 && m.Data[0]&3 == 3
				}
			}
			if !ecn {
				t.Fatal("ECN absent", msgs)
			}
			dg, src := leadBuildFlight(fecVer, 0, 1, 1, 92)
			if _, err := client.WriteToUDP(dg[1].data, dst); err != nil {
				t.Fatal(err)
			}
			got, recovered := udpReadTest(t, c)
			if !bytes.Equal(got, src[0]) || !bytes.Equal(recovered.oob, raw.recovery().oob) || len(recovered.oob) == 0 {
				t.Fatal("real recovery metadata", recovered, raw)
			}
			c.writeFeedback([]byte("feedback"), client.LocalAddr(), recovered)
			b := make([]byte, 20)
			n, from, err := client.ReadFromUDP(b)
			if err != nil || string(b[:n]) != "feedback" || !from.IP.Equal(target) || c.TxDgrams != 0 || c.stats.FbWriteErr != 0 {
				t.Fatal("reply source", n, from, err, c.stats)
			}
		})
	}
}

func TestUDPRealGSOSegments(t *testing.T) {
	server, err := net.ListenUDP("udp4", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1)})
	if err != nil {
		t.Fatal(err)
	}
	defer server.Close()
	client, err := net.ListenUDP("udp4", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1)})
	if err != nil {
		t.Fatal(err)
	}
	defer client.Close()
	c := newUDPDecodeConn(&decodeConn{countConn: countConn{PacketConn: server}}, server)
	payload := make([]byte, 2500)
	for i := range payload {
		payload[i] = byte(i)
	}
	if n, _, err := c.WriteMsgUDP(payload, udpGSOControl(1200), client.LocalAddr().(*net.UDPAddr)); err != nil || n != len(payload) {
		t.Fatal(n, err)
	}
	client.SetReadDeadline(time.Now().Add(2 * time.Second))
	total := 0
	for _, want := range []int{1200, 1200, 100} {
		b := make([]byte, 2000)
		n, _, err := client.ReadFromUDP(b)
		if err != nil || n != want || !bytes.Equal(b[:n], payload[total:total+n]) {
			t.Fatal(n, want, err)
		}
		total += n
	}
	if c.TxDgrams != 3 || c.TxBytes != 2500 || c.stats.UDPGSOSegments != 3 {
		t.Fatal(c.stats, c.TxDgrams, c.TxBytes)
	}
}

func udpReferenceReader(s *decodeConn, c *holdScriptConn) func([]byte) (int, net.Addr, error) {
	wire := &udpTestWire{holdScriptConn: c}
	for range c.frames {
		wire.metas = append(wire.metas, udpTestMeta(2))
	}
	s.PacketConn = wire
	wrapped := newUDPDecodeConn(s, wire)
	return func(b []byte) (int, net.Addr, error) {
		ms := []ipv4.Message{{Buffers: [][]byte{b}, OOB: make([]byte, 128)}}
		n, err := wrapped.ReadBatch(ms, 0)
		if err != nil {
			return 0, nil, err
		}
		if n != 1 {
			return 0, nil, io.ErrUnexpectedEOF
		}
		return ms[0].N, ms[0].Addr, nil
	}
}

func TestUDPQUICEnablesSocketCapabilities(t *testing.T) {
	cert, _, err := serverCertificate(6000, "")
	if err != nil {
		t.Fatal(err)
	}
	for _, network := range []string{"udp4", "udp6"} {
		t.Run(network, func(t *testing.T) {
			ip, level, mtuOpt, ecnOpt, infoOpt := net.IPv4zero, unix.IPPROTO_IP, unix.IP_MTU_DISCOVER, unix.IP_RECVTOS, unix.IP_PKTINFO
			if network == "udp6" {
				ip, level, mtuOpt, ecnOpt, infoOpt = net.IPv6zero, unix.IPPROTO_IPV6, unix.IPV6_MTU_DISCOVER, unix.IPV6_RECVTCLASS, unix.IPV6_RECVPKTINFO
			}
			udp, err := net.ListenUDP(network, &net.UDPAddr{IP: ip})
			if err != nil {
				t.Fatal(err)
			}
			defer udp.Close()
			wrapped := newUDPDecodeConn(&decodeConn{countConn: countConn{PacketConn: udp}, mode: "off"}, udp)
			transport := &quic.Transport{Conn: wrapped}
			defer transport.Close()
			listener, err := transport.Listen(&tls.Config{Certificates: []tls.Certificate{cert}, NextProtos: []string{"padfec"}}, &quic.Config{})
			if err != nil {
				t.Fatal(err)
			}
			defer listener.Close()
			raw, err := wrapped.SyscallConn()
			if err != nil {
				t.Fatal(err)
			}
			for _, option := range []struct{ key, want int }{{mtuOpt, unix.IP_PMTUDISC_PROBE}, {ecnOpt, 1}, {infoOpt, 1}} {
				var value int
				var sockErr error
				err := raw.Control(func(fd uintptr) { value, sockErr = unix.GetsockoptInt(int(fd), level, option.key) })
				if err != nil || sockErr != nil || value != option.want {
					t.Fatal(option, value, err, sockErr)
				}
			}
		})
	}
}
