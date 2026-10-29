package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/binary"
	"fmt"
	"hash/crc32"
	"net"
	"testing"
	"time"
)

func leadTestInitial(dcid, scid []byte, size int, seed byte) []byte {
	d := make([]byte, size)
	x := uint32(seed)*2654435761 + 12345
	for i := range d {
		x = x*1103515245 + 12345
		d[i] = byte(x >> 16)
	}
	d[0] = 0xc3
	d[1], d[2], d[3], d[4] = 0, 0, 0, 1
	d[5] = byte(len(dcid))
	copy(d[6:], dcid)
	d[6+len(dcid)] = byte(len(scid))
	copy(d[7+len(dcid):], scid)
	return d
}

var leadTestDCID = []byte{0xd1, 0xd2, 0xd3, 0xd4, 0xd5, 0xd6, 0xd7, 0xd8}
var leadTestSCID = []byte{0x51, 0x52, 0x53, 0x54}

func leadTranscript(fc *fecConn, k int) []byte {
	addr := &net.UDPAddr{IP: net.IPv4(10, 9, 0, 2), Port: 44433}
	srv := leadTestInitial(leadTestSCID, leadTestDCID, 1300, 200)
	wire := &auditConn{scriptConn: scriptConn{dgs: [][]byte{srv}, addr: addr}}
	fc.PacketConn = wire
	var out []byte
	put := func(n int, err error) {
		out = binary.BigEndian.AppendUint16(out, uint16(n))
		if err != nil {
			out = append(out, err.Error()...)
		}
	}
	for round := 0; round < 2; round++ {
		for i := 0; i < k; i++ {
			size := 1200
			if i == k-1 {
				size = 1100 - 37*round
			}
			put(fc.WriteTo(leadTestInitial(leadTestDCID, leadTestSCID, size, byte(16*round+i)), addr))
		}
	}
	buf := make([]byte, 2000)
	n, _, err := fc.ReadFrom(buf)
	put(n, err)
	put(fc.WriteTo(leadTestInitial(leadTestDCID, leadTestSCID, 1200, 99), addr))
	put(fc.WriteTo([]byte{0x40, 1, 2, 3, 4, 5, 6, 7}, addr))
	for _, w := range wire.written {
		out = binary.BigEndian.AppendUint16(out, uint16(len(w)))
		out = append(out, w...)
	}
	return out
}

func leadV2Conn(mode string, m, k int, inject bool) *fecConn {
	fc := &fecConn{mode: mode, m: m, expectK: k, dropParity: -1, corruptParity: -1,
		parityDelay: time.Hour}
	if inject {
		fc.dropInitial = map[int]bool{1: true}
		fc.dropParity = 0
		fc.corruptParity = 1
	}
	return fc
}

func leadV2Digest(mode string, mk func(mode string, m, k int, inject bool) *fecConn) string {
	h := sha256.New()
	for m := 1; m <= 4; m++ {
		for k := 1; k <= 3; k++ {
			for _, inject := range []bool{false, true} {
				fmt.Fprintf(h, "%s|%d|%d|%v|", mode, m, k, inject)
				h.Write(leadTranscript(mk(mode, m, k, inject), k))
			}
		}
	}
	return fmt.Sprintf("%x", h.Sum(nil))
}

var leadV2Golden = map[string]string{
	"off": "ae4b292f44316c12deed63a33d0b52959c8cc0b07aed81dbdaba6ec0938bac3c",
	"buf": "c148d149c90b87c4e386ffa0505c477c35b9622d0316e6eb80d4f6f69360cff5",
	"fec": "514ad428971dd3607b5cbe05da25d0e8e1510f3ad4ef2c10a7fb4bb024475487",
}

func TestLeadV2OutputMatchesGen2Golden(t *testing.T) {
	gfInit()
	explicit := func(mode string, m, k int, inject bool) *fecConn {
		fc := leadV2Conn(mode, m, k, inject)
		fc.layout = "v2"
		fc.lead = -1
		return fc
	}
	for mode, want := range leadV2Golden {
		if got := leadV2Digest(mode, leadV2Conn); got != want {
			t.Errorf("%s default layout transcript %s, gen-2 golden %s", mode, got, want)
		}
		if got := leadV2Digest(mode, explicit); got != want {
			t.Errorf("%s -layout v2 -lead -1 transcript %s, gen-2 golden %s", mode, got, want)
		}
	}
}

func TestLeadV2LaterFlightKeepsGen2Shape(t *testing.T) {
	gfInit()
	for m := 1; m <= 4; m++ {
		fc := leadV2Conn("fec", m, 2, false)
		fc.layout = "v2"
		fc.lead = -1
		leadTranscript(fc, 2)
		st := fc.snapshot()
		if st.Layout != "v2" || st.Lead != min(1, m-1) {
			t.Fatalf("m=%d layout=%q lead=%d", m, st.Layout, st.Lead)
		}
		if st.FirstFlightLeadDgrams != st.Lead || st.LaterParitySent != 2*m {
			t.Fatalf("m=%d first-flight lead %d later parity %d", m, st.FirstFlightLeadDgrams, st.LaterParitySent)
		}
	}
}

type leadDgram struct {
	data   []byte
	orig   int
	par    int
	credit bool
}

func leadBuildFlight(ver, lead, m, k int, seed byte) ([]leadDgram, [][]byte) {
	src := make([][]byte, k)
	size := 0
	for i := range src {
		n := 1200
		if i == k-1 && k > 1 {
			n = 1150
		}
		src[i] = leadTestInitial(leadTestDCID, leadTestSCID, n, seed+byte(i))
		size = max(size, n)
	}
	crcs := make([]uint32, k)
	lens := make([]uint16, k)
	padded := make([][]byte, k)
	for i, d := range src {
		crcs[i] = crc32.ChecksumIEEE(d)
		lens[i] = uint16(len(d))
		padded[i] = make([]byte, size)
		copy(padded[i], d)
	}
	pars := rsEncode(padded, m, size)
	mkp := func(j int) leadDgram {
		return leadDgram{data: buildParity(leadTestDCID, leadTestSCID, fecBlock{ver: ver,
			flight: 1, k: k, m: m, lead: lead, index: j, symLen: size,
			crcs: crcs, lens: lens, sym: pars[j]}), orig: -1, par: j, credit: j < lead}
	}
	var dg []leadDgram
	for j := 0; j < lead; j++ {
		dg = append(dg, mkp(j))
	}
	for i := range src {
		dg = append(dg, leadDgram{data: src[i], orig: i, par: -1})
	}
	for j := lead; j < m; j++ {
		dg = append(dg, mkp(j))
	}
	return dg, src
}

func leadOrders(n int, visit func(ord []int)) {
	used := make([]bool, n)
	ord := make([]int, 0, n)
	var rec func()
	rec = func() {
		visit(ord)
		for i := 0; i < n; i++ {
			if used[i] {
				continue
			}
			used[i] = true
			ord = append(ord, i)
			rec()
			ord = ord[:len(ord)-1]
			used[i] = false
		}
	}
	rec()
}

func leadExpectation(dg []leadDgram, ord []int, k int) (absent, recArrived int, inOrder bool) {
	seen := map[int]bool{}
	inOrder = true
	for x, ix := range ord {
		if x > 0 && ix < ord[x-1] {
			inOrder = false
		}
		d := dg[ix]
		if d.orig >= 0 {
			seen[d.orig] = true
		} else if !d.credit {
			recArrived++
		}
	}
	return k - len(seen), recArrived, inOrder
}

func leadCheckFeedOne(ver, lead, k int, dg []leadDgram, src [][]byte, ord []int) string {
	sv := &decodeConn{mode: "fec"}
	buf := make([]byte, 2000)
	for _, ix := range ord {
		d := dg[ix]
		sv.mu.Lock()
		stk, cr, cr3 := sv.stats.BytesToStack, sv.stats.CreditParities, sv.stats.CreditParitiesV3
		sv.mu.Unlock()
		copy(buf, d.data)
		sv.feedOne(buf[:len(d.data)])
		sv.mu.Lock()
		over := sv.stats.BytesToStack+sv.pendingBytes > sv.stats.BytesIn
		dStk := sv.stats.BytesToStack - stk
		dCr, dCr3 := sv.stats.CreditParities-cr, sv.stats.CreditParitiesV3-cr3
		sv.mu.Unlock()
		if over {
			return fmt.Sprint("invariant broken after datagram ", ix)
		}
		wantCr3 := 0
		if d.credit && ver == fecVerLead {
			wantCr3 = 1
		}
		if d.credit && (dStk != int64(len(d.data)) || dCr != 1 || dCr3 != wantCr3) {
			return fmt.Sprint("credit ", ix, " not stacked at once: stack +", dStk, " credit +", dCr, " v3 +", dCr3)
		}
		if !d.credit && (dCr != 0 || dCr3 != 0) {
			return fmt.Sprint("non-credit ", ix, " counted as credit")
		}
	}
	absent, recArrived, inOrder := leadExpectation(dg, ord, k)
	sv.mu.Lock()
	defer sv.mu.Unlock()
	delivered := map[uint32]bool{}
	for _, ix := range ord {
		if dg[ix].orig >= 0 {
			delivered[crc32.ChecksumIEEE(dg[ix].data)] = true
		}
	}
	for _, fr := range sv.flights {
		for c := range fr.recCRC {
			delivered[c] = true
		}
		for j := range fr.syms {
			if j < lead {
				return fmt.Sprint("credit index ", j, " stored as recovery symbol")
			}
		}
	}
	covered := true
	for _, s := range src {
		if !delivered[crc32.ChecksumIEEE(s)] {
			covered = false
		}
	}
	want := absent <= recArrived
	if covered != want {
		return fmt.Sprint("absent ", absent, " recovery parities ", recArrived, " covered ", covered)
	}
	if !want && sv.stats.RecoverEvents != 0 {
		return "recovery event without enough recovery parities"
	}
	if sv.stats.RecoverFail != 0 || sv.stats.RecoverEvents > 1 || sv.stats.RecoverRefused != 0 {
		return fmt.Sprintf("crc fail %d events %d refused %d", sv.stats.RecoverFail, sv.stats.RecoverEvents, sv.stats.RecoverRefused)
	}
	if inOrder && sv.stats.PrematureRecover != 0 {
		return "premature recovery without reordering"
	}
	return ""
}

func leadCheckReadFrom(k int, dg []leadDgram, src [][]byte, ord []int) string {
	send := make([][]byte, 0, len(ord))
	for _, ix := range ord {
		send = append(send, dg[ix].data)
	}
	sv := &decodeConn{mode: "fec"}
	sv.PacketConn = &auditConn{scriptConn: scriptConn{dgs: send,
		addr: &net.UDPAddr{IP: net.IPv4(10, 9, 0, 3), Port: 5555}}}
	var handed int64
	var got [][]byte
	buf := make([]byte, 2000)
	for {
		n, _, err := sv.ReadFrom(buf)
		if err != nil {
			break
		}
		handed += int64(n)
		got = append(got, append([]byte(nil), buf[:n]...))
		sv.mu.Lock()
		over := handed > sv.stats.BytesIn
		sv.mu.Unlock()
		if over {
			return fmt.Sprint("handed ", handed, " > arrived")
		}
	}
	sv.mu.Lock()
	stk := sv.stats.BytesToStack
	sv.mu.Unlock()
	if handed != stk {
		return fmt.Sprint("handed ", handed, " != ledger ", stk)
	}
	has := func(d []byte) bool {
		for _, g := range got {
			if bytes.Equal(g, d) {
				return true
			}
		}
		return false
	}
	for _, ix := range ord {
		if dg[ix].credit && !has(dg[ix].data) {
			return fmt.Sprint("credit ", ix, " never reached the stack")
		}
	}
	absent, recArrived, _ := leadExpectation(dg, ord, k)
	covered := true
	for _, s := range src {
		if !has(s) {
			covered = false
		}
	}
	if covered != (absent <= recArrived) {
		return fmt.Sprint("absent ", absent, " recovery parities ", recArrived, " covered ", covered)
	}
	return ""
}

func leadExhaustive(t *testing.T, ver int, cases [][3]int, viaReadFrom bool) {
	gfInit()
	runs := 0
	for _, c := range cases {
		lead, m, k := c[0], c[1], c[2]
		dg, src := leadBuildFlight(ver, lead, m, k, byte(17*lead+5*m+k))
		for _, d := range dg {
			fb := parseFecBlock(d.data)
			if d.orig >= 0 {
				if fb != nil {
					t.Fatal("original parsed as parity")
				}
				continue
			}
			if fb == nil || fb.ver != max(ver, fecVer) || fb.lead != lead || fb.m != m || isCreditParity(fb) != d.credit {
				t.Fatalf("ver %d lead %d m %d k %d: parity %d parsed as %+v", ver, lead, m, k, d.par, fb)
			}
		}
		bad := ""
		leadOrders(len(dg), func(ord []int) {
			if bad != "" {
				return
			}
			runs++
			if viaReadFrom {
				bad = leadCheckReadFrom(k, dg, src, ord)
			} else {
				bad = leadCheckFeedOne(ver, lead, k, dg, src, ord)
			}
			if bad != "" {
				bad = fmt.Sprint("ver ", ver, " lead ", lead, " m ", m, " k ", k, " order ", ord, ": ", bad)
			}
		})
		if bad != "" {
			t.Fatal(bad)
		}
	}
	t.Logf("%d arrival subsets x orders checked", runs)
}

func leadV3Cases() [][3]int {
	var cs [][3]int
	for lead := 0; lead <= 3; lead++ {
		for m := max(lead, 1); m <= 4; m++ {
			for k := 1; k <= 3; k++ {
				cs = append(cs, [3]int{lead, m, k})
			}
		}
	}
	return cs
}

func leadV1Cases() [][3]int {
	var cs [][3]int
	for m := 1; m <= 4; m++ {
		for k := 1; k <= 3; k++ {
			cs = append(cs, [3]int{min(1, m-1), m, k})
		}
	}
	return cs
}

func TestLeadV3AllArrivalsFeedOne(t *testing.T) {
	leadExhaustive(t, fecVerLead, leadV3Cases(), false)
}

func TestLeadV3AllArrivalsReadFrom(t *testing.T) {
	leadExhaustive(t, fecVerLead, leadV3Cases(), true)
}

func TestLeadVer1LegacyAllArrivalsFeedOne(t *testing.T) {
	leadExhaustive(t, fecVer, leadV1Cases(), false)
}

func TestLeadVer1LegacyAllArrivalsReadFrom(t *testing.T) {
	leadExhaustive(t, fecVer, leadV1Cases(), true)
}

func TestLeadCreditRule(t *testing.T) {
	for m := 1; m <= 8; m++ {
		for j := 0; j < m; j++ {
			want := m >= 2 && j == 0
			if got := isCreditParity(&fecBlock{ver: fecVer, m: m, lead: 3, index: j}); got != want {
				t.Fatalf("ver 1 m %d index %d credit %v", m, j, got)
			}
		}
	}
	for m := 1; m <= 15; m++ {
		for lead := 0; lead <= m; lead++ {
			for j := 0; j < m; j++ {
				if got := isCreditParity(&fecBlock{ver: fecVerLead, m: m, lead: lead, index: j}); got != (j < lead) {
					t.Fatalf("ver 3 lead %d m %d index %d credit %v", lead, m, j, got)
				}
			}
		}
	}
}

func TestLeadHeaderRoundTrip(t *testing.T) {
	sym := []byte{1, 2, 3, 4, 5, 6, 7, 8}
	base := fecBlock{flight: 9, k: 2, symLen: len(sym), crcs: []uint32{1, 2},
		lens: []uint16{8, 7}, sym: sym}
	for m := 1; m <= 15; m++ {
		for lead := 0; lead <= m; lead++ {
			for j := 0; j < m; j++ {
				fb := base
				fb.ver, fb.m, fb.lead, fb.index = fecVerLead, m, lead, j
				pkt := buildParity(leadTestDCID, leadTestSCID, fb)
				v1 := base
				v1.m, v1.index = min(m, 8), min(j, 7)
				if n1 := len(buildParity(leadTestDCID, leadTestSCID, v1)); len(pkt) != n1 {
					t.Fatalf("v3 parity %d B, v1 parity %d B", len(pkt), n1)
				}
				got := parseFecBlock(pkt)
				if got == nil || got.ver != fecVerLead || got.m != m || got.lead != lead ||
					got.index != j || got.k != 2 || got.flight != 9 || !bytes.Equal(got.sym, sym) {
					t.Fatalf("lead %d m %d index %d parsed %+v", lead, m, j, got)
				}
			}
		}
	}
	for m := 1; m <= 8; m++ {
		fb := base
		fb.m = m
		got := parseFecBlock(buildParity(leadTestDCID, leadTestSCID, fb))
		if got == nil || got.ver != fecVer || got.m != m || got.lead != min(1, m-1) {
			t.Fatalf("ver 1 m %d parsed %+v", m, got)
		}
	}
	reject := func(name string, fb fecBlock, patch func([]byte)) {
		pkt := buildParity(leadTestDCID, leadTestSCID, fb)
		if patch != nil {
			patch(pkt)
		}
		if parseFecBlock(pkt) != nil {
			t.Errorf("accepted %s", name)
		}
	}
	verAt := 10 + len(leadTestDCID) + len(leadTestSCID) + 4
	bad := base
	bad.ver, bad.m, bad.lead = fecVerLead, 2, 3
	reject("lead > m", bad, nil)
	bad.m, bad.lead = 0, 1
	reject("v3 m = 0", bad, nil)
	bad.m, bad.lead, bad.index = 2, 1, 2
	reject("v3 index >= m", bad, nil)
	ok := base
	ok.m = 1
	reject("version 2", ok, func(p []byte) { p[verAt] = 2 })
	reject("version 4", ok, func(p []byte) { p[verAt] = 4 })
	ok.m = 0x13
	reject("ver 1 m byte with lead nibble", ok, nil)
}

func leadParseWire(t *testing.T, d []byte) *fecBlock {
	fb := parseFecBlock(d)
	if fb == nil {
		t.Fatalf("expected parity, got %d B datagram %x", len(d), d[:min(len(d), 16)])
	}
	return fb
}

func TestLeadClientV3Layout(t *testing.T) {
	gfInit()
	addr := &net.UDPAddr{IP: net.IPv4(10, 9, 0, 2), Port: 44433}
	small := leadTestInitial(leadTestSCID, leadTestDCID, 120, 201)
	big := leadTestInitial(leadTestSCID, leadTestDCID, 1300, 202)
	for m := 1; m <= 4; m++ {
		for lead := 0; lead <= m; lead++ {
			for k := 1; k <= 3; k++ {
				name := fmt.Sprintf("m%d L%d k%d", m, lead, k)
				wire := &auditConn{scriptConn: scriptConn{dgs: [][]byte{small, big}, addr: addr}}
				fc := &fecConn{mode: "fec", m: m, layout: "v3", lead: lead, expectK: k,
					dropParity: -1, corruptParity: -1, parityDelay: time.Hour}
				fc.PacketConn = wire
				pos := 0
				flight := func(round int, fid uint16) {
					var src [][]byte
					size := 0
					for i := 0; i < k; i++ {
						n := 1200
						if i == k-1 {
							n = 1111
						}
						size = max(size, n)
						d := leadTestInitial(leadTestDCID, leadTestSCID, n, byte(40*round+i))
						src = append(src, d)
						fc.WriteTo(d, addr)
					}
					w := wire.written[pos:]
					if len(w) != k+m {
						t.Fatalf("%s round %d: %d datagrams on wire, want %d", name, round, len(w), k+m)
					}
					for x, d := range w {
						switch {
						case x < lead:
							fb := leadParseWire(t, d)
							if fb.ver != fecVerLead || fb.lead != lead || fb.m != m || fb.index != x || fb.k != k || fb.flight != fid {
								t.Fatalf("%s round %d slot %d: %+v", name, round, x, fb)
							}
						case x < lead+k:
							if !bytes.Equal(d, src[x-lead]) {
								t.Fatalf("%s round %d slot %d: original %d out of place", name, round, x, x-lead)
							}
						default:
							fb := leadParseWire(t, d)
							if fb.ver != fecVerLead || fb.lead != lead || fb.m != m || fb.index != x-k || fb.flight != fid {
								t.Fatalf("%s round %d slot %d: %+v", name, round, x, fb)
							}
						}
						if x < lead || x >= lead+k {
							v1 := len(buildParity(leadTestDCID, leadTestSCID, fecBlock{k: k, m: m,
								symLen: size, crcs: make([]uint32, k), lens: make([]uint16, k),
								sym: make([]byte, size)}))
							if len(d) != v1 {
								t.Fatalf("%s: v3 parity %d B, gen-2 parity %d B", name, len(d), v1)
							}
						}
					}
					pos = len(wire.written)
				}
				flight(0, 1)
				flight(1, 2)
				buf := make([]byte, 2000)
				if n, _, _ := fc.ReadFrom(buf); n != len(small) {
					t.Fatal("scripted small server datagram not read")
				}
				flight(2, 3)
				if n, _, _ := fc.ReadFrom(buf); n != len(big) {
					t.Fatal("scripted server flight datagram not read")
				}
				var later [][]byte
				for i := 0; i < 2; i++ {
					d := leadTestInitial(leadTestDCID, leadTestSCID, 1200-100*i, byte(150+i))
					later = append(later, d)
					fc.WriteTo(d, addr)
					if i == 0 && k > 1 && (len(wire.written) != pos+1 || !bytes.Equal(wire.written[pos], d)) {
						t.Fatalf("%s: later original was not sent at once", name)
					}
				}
				short := []byte{0x40, 9, 9, 9, 9, 9}
				fc.WriteTo(short, addr)
				w := wire.written[pos:]
				var origs, pars [][]byte
				for _, d := range w[:len(w)-1] {
					if parseFecBlock(d) == nil {
						if len(pars) > 0 && k > 1 {
							t.Fatalf("%s: later parity sent before a later original", name)
						}
						origs = append(origs, d)
					} else {
						pars = append(pars, d)
					}
				}
				if !bytes.Equal(w[len(w)-1], short) || len(origs) != 2 ||
					!bytes.Equal(origs[0], later[0]) || !bytes.Equal(origs[1], later[1]) {
					t.Fatalf("%s: later flight wire %d datagrams", name, len(w))
				}
				wantPar := 0
				if m-lead >= 1 {
					wantPar = 1
				}
				if k == 1 {
					wantPar *= 2
				}
				if len(pars) != wantPar {
					t.Fatalf("%s: %d later parities, want %d", name, len(pars), wantPar)
				}
				for _, p := range pars {
					fb := leadParseWire(t, p)
					if fb.ver != fecVerLead || fb.lead != 0 || fb.m != 1 || fb.index != 0 || isCreditParity(fb) {
						t.Fatalf("%s: later parity header %+v", name, fb)
					}
					cover := later
					if k == 1 {
						cover = later[:1]
						if fb.flight == 5 {
							cover = later[1:]
						}
					}
					if fb.k != len(cover) {
						t.Fatalf("%s: later parity covers %d originals", name, fb.k)
					}
					x := make([]byte, fb.symLen)
					for _, o := range cover {
						for b := range o {
							x[b] ^= o[b]
						}
					}
					if !bytes.Equal(fb.sym, x) {
						t.Fatalf("%s: later parity is not the XOR of its flight", name)
					}
				}
				st := fc.snapshot()
				if st.Layout != "v3" || st.Lead != lead || st.FirstFlightLeadDgrams != lead ||
					st.FirstFlightParity != m || st.LaterParitySent != 2*m+wantPar {
					t.Fatalf("%s: stats layout %q lead %d ff-lead %d ff-parity %d later %d",
						name, st.Layout, st.Lead, st.FirstFlightLeadDgrams, st.FirstFlightParity, st.LaterParitySent)
				}
			}
		}
	}
}

func TestLeadClientV3LegacyLeadDefault(t *testing.T) {
	for m := 1; m <= 4; m++ {
		fc := &fecConn{mode: "fec", m: m, layout: "v3", lead: -1}
		if fc.firstLead() != min(1, m-1) {
			t.Fatalf("m %d legacy lead %d", m, fc.firstLead())
		}
	}
	for _, mode := range []string{"off", "buf"} {
		fc := &fecConn{mode: mode, m: 3, layout: "v3", lead: 2}
		if fc.v3() || fc.firstLead() != 0 {
			t.Fatalf("%s mode took the v3 layout", mode)
		}
	}
}

func TestLeadClientToServerRecovers(t *testing.T) {
	gfInit()
	addr := &net.UDPAddr{IP: net.IPv4(10, 9, 0, 2), Port: 44433}
	for m := 1; m <= 4; m++ {
		for lead := 0; lead <= m; lead++ {
			for k := 1; k <= 3; k++ {
				for drop := 0; drop < k; drop++ {
					wire := &auditConn{}
					fc := &fecConn{mode: "fec", m: m, layout: "v3", lead: lead, expectK: k,
						dropInitial: map[int]bool{drop: true}, dropParity: -1, corruptParity: -1,
						parityDelay: time.Hour}
					fc.PacketConn = wire
					var src [][]byte
					for i := 0; i < k; i++ {
						d := leadTestInitial(leadTestDCID, leadTestSCID, 1200-50*i, byte(70+i))
						src = append(src, d)
						fc.WriteTo(d, addr)
					}
					sv := &decodeConn{mode: "fec"}
					sv.PacketConn = &auditConn{scriptConn: scriptConn{dgs: wire.written,
						addr: &net.UDPAddr{IP: net.IPv4(10, 9, 0, 1), Port: 40000}}}
					var got [][]byte
					buf := make([]byte, 2000)
					for {
						n, _, err := sv.ReadFrom(buf)
						if err != nil {
							break
						}
						got = append(got, append([]byte(nil), buf[:n]...))
					}
					recovered := false
					for _, g := range got {
						if bytes.Equal(g, src[drop]) {
							recovered = true
						}
					}
					if recovered != (m-lead >= 1) {
						t.Fatalf("m%d L%d k%d drop %d: recovered %v", m, lead, k, drop, recovered)
					}
					if sv.stats.CreditParitiesV3 != lead || sv.stats.CreditParities != lead {
						t.Fatalf("m%d L%d k%d: server credited %d (v3 %d)", m, lead, k,
							sv.stats.CreditParities, sv.stats.CreditParitiesV3)
					}
					if len(sv.conns) != 1 {
						t.Fatalf("m%d L%d k%d: %d server accounts", m, lead, k, len(sv.conns))
					}
					for _, c := range sv.conns {
						if c.CreditN != lead {
							t.Fatalf("m%d L%d k%d: per-connection credit %d", m, lead, k, c.CreditN)
						}
					}
				}
			}
		}
	}
}

func TestLeadLayoutFlags(t *testing.T) {
	for _, c := range []struct {
		layout string
		lead   int
		fmode  string
		m      int
		ok     bool
	}{
		{"v2", -1, "fec", 1, true},
		{"v2", -1, "fec", 3, true},
		{"v2", -1, "fec", 4, true},
		{"v2", -1, "auto", 3, true},
		{"v2", -1, "off", 1, true},
		{"v2", 1, "fec", 3, false},
		{"v3", 1, "fec", 3, true},
		{"v3", 3, "fec", 3, true},
		{"v3", 2, "fec", 2, true},
		{"v3", 1, "fec", 4, true},
		{"v3", 2, "fec", 4, true},
		{"v3", 3, "fec", 4, true},
		{"v3", -1, "fec", 3, true},
		{"v3", 0, "fec", 1, true},
		{"v3", 1, "auto", 3, true},
		{"v3", 4, "fec", 3, false},
		{"v3", 2, "fec", 1, false},
		{"v3", -2, "fec", 3, false},
		{"v3", 1, "off", 3, false},
		{"v3", 1, "buf", 3, false},
		{"v3", 15, "fec", 16, false},
		{"v9", -1, "fec", 3, false},
	} {
		err := checkLayoutFlags(c.layout, c.lead, c.fmode, c.m)
		if (err == nil) != c.ok {
			t.Errorf("-layout %s -lead %d -fec %s -m %d: err %v", c.layout, c.lead, c.fmode, c.m, err)
		}
	}
}
