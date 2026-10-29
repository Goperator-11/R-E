package main

import (
	"bytes"
	"crypto/sha256"
	"net"
	"testing"
	"time"
)

func TestRvV3StrictInvariantAllOrders(t *testing.T) {
	gfInit()
	runs := 0
	for lead := 0; lead <= 3; lead++ {
		for m := max(lead, 1); m <= 4; m++ {
			for k := 1; k <= 3; k++ {
				dg, _ := leadBuildFlight(fecVerLead, lead, m, k, byte(3*lead+7*m+k))
				for _, via := range []bool{false, true} {
					bad := ""
					rvOrders(len(dg), func(ord []int) {
						if bad != "" {
							return
						}
						runs++
						var send [][]byte
						for _, ix := range ord {
							send = append(send, dg[ix].data)
						}
						bad = rvServerRun(send, via, sha256.New())
					})
					if bad != "" {
						t.Fatalf("lead %d m %d k %d readfrom=%v: %s", lead, m, k, via, bad)
					}
				}
			}
		}
	}
	t.Logf("%d runs", runs)
}

type rvWire struct {
	data   []byte
	flight int
	orig   int
	credit bool
	recov  bool
}

func rvClientWire(m, lead, k int, retx bool, laterK int) ([]rvWire, [][][]byte) {
	addr := &net.UDPAddr{IP: net.IPv4(10, 9, 0, 2), Port: 44433}
	big := rvInitial(rvSCID, rvDCID, 1252, 99)
	wire := &auditConn{scriptConn: scriptConn{dgs: [][]byte{big}, addr: addr}}
	fc := &fecConn{mode: "fec", m: m, layout: "v3", lead: lead, dropParity: -1,
		corruptParity: -1, parityDelay: time.Hour}
	fc.PacketConn = wire
	short := []byte{0x41, 7, 7, 7, 7}
	var srcs [][][]byte
	var out []rvWire
	collect := func(fl int, src [][]byte) {
		for _, d := range wire.written {
			if bytes.Equal(d, short) {
				continue
			}
			w := rvWire{data: d, flight: fl, orig: -1}
			if fb := parseFecBlock(d); fb != nil {
				w.credit = isCreditParity(fb)
				w.recov = !w.credit
			} else {
				for i, s := range src {
					if bytes.Equal(s, d) {
						w.orig = i
					}
				}
			}
			out = append(out, w)
		}
		wire.written = nil
		srcs = append(srcs, src)
	}
	flight := func(fl, n int, seed byte) {
		var src [][]byte
		for i := 0; i < n; i++ {
			d := rvInitial(rvDCID, rvSCID, 1200-17*i, seed+byte(i))
			src = append(src, d)
			fc.WriteTo(d, addr)
		}
		fc.WriteTo(short, addr)
		collect(fl, src)
	}
	flight(0, k, 10)
	if retx {
		flight(1, k, 50)
	}
	buf := make([]byte, 2000)
	fc.ReadFrom(buf)
	if laterK > 0 {
		flight(len(srcs), laterK, 90)
	}
	return out, srcs
}

func TestRvClientServerLossSubsets(t *testing.T) {
	gfInit()
	total := 0
	for m := 1; m <= 4; m++ {
		for lead := 0; lead <= m; lead++ {
			for k := 1; k <= 3; k++ {
				for _, retx := range []bool{false, true} {
					if retx && (m > 3 || k > 2) {
						continue
					}
					for laterK := 0; laterK <= 2; laterK++ {
						w, srcs := rvClientWire(m, lead, k, retx, laterK)
						nf := len(srcs)
						lastFlight := nf - 1
						for fl := 0; fl < nf; fl++ {
							var lp, cr, rc int
							for _, x := range w {
								if x.flight != fl {
									continue
								}
								if x.credit {
									cr++
								}
								if x.recov {
									rc++
								}
								if x.orig < 0 && !x.credit && !x.recov {
									t.Fatalf("unclassified datagram")
								}
								lp++
							}
							later := laterK > 0 && fl == lastFlight
							wantCr, wantRc := lead, m-lead
							if later {
								wantCr, wantRc = 0, min(1, m-lead)
							}
							if cr != wantCr || rc != wantRc {
								t.Fatalf("m%d L%d k%d retx %v laterK %d flight %d: credit %d recov %d", m, lead, k, retx, laterK, fl, cr, rc)
							}
						}
						for mask := 0; mask < 1<<len(w); mask++ {
							total++
							var send [][]byte
							arrived := map[int]map[int]bool{}
							recArr := map[int]int{}
							credArr := 0
							for i, x := range w {
								if mask&(1<<i) != 0 {
									continue
								}
								send = append(send, x.data)
								if arrived[x.flight] == nil {
									arrived[x.flight] = map[int]bool{}
								}
								if x.orig >= 0 {
									arrived[x.flight][x.orig] = true
								}
								if x.recov {
									recArr[x.flight]++
								}
								if x.credit {
									credArr++
								}
							}
							sv := &decodeConn{mode: "fec"}
							sv.PacketConn = &auditConn{scriptConn: scriptConn{dgs: send,
								addr: &net.UDPAddr{IP: net.IPv4(10, 9, 0, 1), Port: 40000}}}
							var got [][]byte
							buf := make([]byte, 2000)
							var handed int64
							for {
								n, _, err := sv.ReadFrom(buf)
								if err != nil {
									break
								}
								handed += int64(n)
								got = append(got, append([]byte(nil), buf[:n]...))
								if sv.stats.BytesToStack+sv.pendingBytes > sv.stats.BytesIn {
									t.Fatalf("invariant m%d L%d k%d mask %b", m, lead, k, mask)
								}
							}
							if handed != sv.stats.BytesToStack || sv.pendingBytes != 0 {
								t.Fatalf("ledger m%d L%d k%d mask %b: handed %d stack %d pending %d", m, lead, k, mask, handed, sv.stats.BytesToStack, sv.pendingBytes)
							}
							if sv.stats.CreditParities != credArr || sv.stats.CreditParitiesV3 != credArr {
								t.Fatalf("credits m%d L%d k%d mask %b: %d/%d want %d", m, lead, k, mask, sv.stats.CreditParities, sv.stats.CreditParitiesV3, credArr)
							}
							if sv.stats.RecoverFail != 0 || sv.stats.RecoverRefused != 0 || sv.stats.PrematureRecover != 0 {
								t.Fatalf("m%d L%d k%d mask %b: fail %d refused %d premature %d", m, lead, k, mask, sv.stats.RecoverFail, sv.stats.RecoverRefused, sv.stats.PrematureRecover)
							}
							for fl, src := range srcs {
								miss := 0
								for i := range src {
									if !arrived[fl][i] {
										miss++
									}
								}
								want := miss <= recArr[fl]
								covered := true
								for _, s := range src {
									found := false
									for _, g := range got {
										if bytes.Equal(g, s) {
											found = true
											break
										}
									}
									if !found {
										covered = false
									}
								}
								if covered != want {
									t.Fatalf("m%d L%d k%d retx %v laterK %d mask %b flight %d: miss %d recov parities %d covered %v", m, lead, k, retx, laterK, mask, fl, miss, recArr[fl], covered)
								}
							}
						}
					}
				}
			}
		}
	}
	t.Logf("%d loss patterns", total)
}

func TestRvLaterFlightAfterSmallServerDatagram(t *testing.T) {
	gfInit()
	addr := &net.UDPAddr{IP: net.IPv4(10, 9, 0, 2), Port: 44433}
	for _, sz := range []int{1199, 1200} {
		wire := &auditConn{scriptConn: scriptConn{dgs: [][]byte{rvInitial(rvSCID, rvDCID, sz, 1)}, addr: addr}}
		fc := &fecConn{mode: "fec", m: 3, layout: "v3", lead: 1, dropParity: -1, corruptParity: -1, parityDelay: time.Hour}
		fc.PacketConn = wire
		fc.WriteTo(rvInitial(rvDCID, rvSCID, 1200, 2), addr)
		fc.WriteTo([]byte{0x41, 1, 2, 3}, addr)
		buf := make([]byte, 2000)
		fc.ReadFrom(buf)
		n0 := len(wire.written)
		fc.WriteTo(rvInitial(rvDCID, rvSCID, 1200, 3), addr)
		immediate := len(wire.written) > n0
		if immediate != (sz >= 1200) {
			t.Fatalf("server datagram %d B: later flight immediate %v", sz, immediate)
		}
	}
}

func TestRvAutoLeadClamp(t *testing.T) {
	fc := &fecConn{mode: "fec", m: 1, layout: "v3", lead: 3}
	t.Logf("auto-like m=1 with -lead 3 gives first lead %d (trailing %d)", fc.firstLead(), fc.m-fc.firstLead())
}
