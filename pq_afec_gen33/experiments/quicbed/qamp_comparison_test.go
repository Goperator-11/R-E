package main

import (
	"bytes"
	"encoding/json"
	"hash/crc32"
	"net"
	"testing"
	"testing/synctest"
)

func comparisonFixture(t *testing.T, kind string, m, lead, k int) (*fecConn, *finalStatsConn, net.Addr) {
	t.Helper()
	c, w, a := flightInputFixture(flightExpectation{k, "explicit", "all_flights"})
	c.mode = "fec"
	c.m = m
	c.layout = "v3"
	c.lead = lead
	c.retransMode = "original_first"
	c.padJunk = kind == "pad_junk"
	c.dup = kind == "dup"
	return c, w, a
}

func TestComparisonSameSlotsAndAccounting(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		gfInit()
		for m := 1; m <= 4; m++ {
			for lead := 0; lead <= m; lead++ {
				for k := 1; k <= 3; k++ {
					wires := map[string][][]byte{}
					stats := map[string]clientStats{}
					for _, kind := range []string{"parity", "pad_junk", "dup"} {
						c, w, a := comparisonFixture(t, kind, m, lead, k)
						for round := 0; round < 3; round++ {
							if round == 2 {
								c.mu.Lock()
								c.srvBig = true
								c.mu.Unlock()
							}
							for i := 0; i < k; i++ {
								traceWriteInitial(t, c, a, byte(1+round*k+i))
							}
						}
						fin := c.finalSendStats()
						wires[kind] = retransWire(w)
						stats[kind] = fin
						expected := m + 1 + min(1, m-lead)
						if fin.ExtraSent.Kind != kind || fin.ExtraSent.Sent != expected || fin.ExtraSent.FirstSent != m || fin.ExtraSent.FirstLead != lead || fin.ExtraSent.Errors != 0 {
							t.Fatal(kind, m, lead, k, fin)
						}
						total := extraSent{}
						for _, f := range fin.FlightTrace.Records {
							total.add(f.ExtraSent)
						}
						if total != fin.ExtraSent {
							t.Fatal(kind, total, fin.ExtraSent)
						}
						if kind != "parity" && (fin.ParitySent != 0 || fin.BytesParity != 0 || fin.FirstFlightParity != 0 || fin.LaterParitySent != 0) {
							t.Fatal(kind, fin)
						}
						var row trial
						var agg clientStats
						recordFinalSendStats(&row, &agg, fin)
						encoded, err := json.Marshal(row)
						if err != nil {
							t.Fatal(err)
						}
						var got trial
						if err = json.Unmarshal(encoded, &got); err != nil || got.ExtraSent != fin.ExtraSent || agg.ExtraSent != fin.ExtraSent {
							t.Fatal(err, got, agg)
						}
					}
					baseline := wires["parity"]
					for _, kind := range []string{"pad_junk", "dup"} {
						got := wires[kind]
						if len(got) != len(baseline) {
							t.Fatal(kind, len(got), len(baseline))
						}
						for i, pkt := range baseline {
							fb := parseFecBlock(pkt)
							if fb == nil {
								if !bytes.Equal(pkt, got[i]) {
									t.Fatal("original changed", kind, i)
								}
								continue
							}
							if parseFecBlock(got[i]) != nil {
								t.Fatal("replacement decoded as parity", kind, i)
							}
							if kind == "pad_junk" {
								h := parseLongHdr(pkt)
								at := h.bodyOff + 3
								if len(pkt) != len(got[i]) || !bytes.Equal(pkt[:at], got[i][:at]) || string(got[i][at:at+4]) != "JUNK" {
									t.Fatal("junk layout changed", i)
								}
							} else {
								round := int(fb.flight) - 1
								seed := byte(1 + round*k + fb.index%k)
								d := finalStatsInitial(seed)
								h := parseLongHdr(d)
								at := h.bodyOff
								d[at] = 0
								copy(d[at+1:], appendVarint2(nil, uint64(len(d)-at-3)))
								if !bytes.Equal(d, got[i]) {
									t.Fatal("duplicate not byte identical", m, lead, k, i, fb.index)
								}
							}
						}
						st := stats[kind].ExtraSent
						par := stats["parity"].ExtraSent
						if st.ParityBudgetBytes != par.Bytes || st.FirstParityBudgetBytes != par.FirstBytes {
							t.Fatal("budget differs", kind, st, par)
						}
						if kind == "pad_junk" && st.Bytes != par.Bytes {
							t.Fatal("junk unequal bytes", st, par)
						}
						if kind == "dup" && st.Bytes >= par.Bytes {
							t.Fatal("duplicate overhead hidden", st, par)
						}
					}
				}
			}
		}
	})
}

func TestComparisonDecoderCreditAndErasure(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		gfInit()
		for _, kind := range []string{"parity", "pad_junk", "dup"} {
			for _, drop := range []bool{false, true} {
				c, w, a := comparisonFixture(t, kind, 4, 3, 2)
				if drop {
					c.dropInitial = map[int]bool{0: true}
				}
				traceWriteInitial(t, c, a, 1)
				traceWriteInitial(t, c, a, 2)
				c.finalSendStats()
				wire := retransWire(w)
				sv := &decodeConn{mode: "fec"}
				sv.PacketConn = &auditConn{scriptConn: scriptConn{dgs: wire, addr: a}}
				buf := make([]byte, 2048)
				var total int64
				var count int
				for {
					n, _, err := sv.ReadFrom(buf)
					if err != nil {
						break
					}
					total += int64(n)
					count++
				}
				var incoming int64
				for _, d := range wire {
					incoming += int64(len(d))
				}
				if sv.stats.BytesIn != incoming || sv.stats.BytesToStack != total || total > incoming {
					t.Fatal(kind, drop, sv.stats, total, incoming)
				}
				if kind != "parity" && (sv.stats.Recovered != 0 || sv.stats.CreditParities != 0 || total != incoming || count != len(wire)) {
					t.Fatal("replacement was FEC", kind, drop, sv.stats)
				}
				if kind == "parity" && (sv.stats.CreditParities != 3 || drop && sv.stats.Recovered != 1 || !drop && sv.stats.Recovered != 0) {
					t.Fatal("baseline", drop, sv.stats)
				}
				if !drop && total != incoming {
					t.Fatal("no loss credit mismatch", kind, sv.stats)
				}
			}
		}
	})
}

func TestComparisonCorruptTailRemainsSingleSlot(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		gfInit()
		wires := [][][]byte{}
		for _, corrupt := range []int{-1, 3} {
			c, w, a := comparisonFixture(t, "parity", 4, 3, 2)
			c.corruptParity = corrupt
			traceWriteInitial(t, c, a, 1)
			traceWriteInitial(t, c, a, 2)
			fin := c.finalSendStats()
			wires = append(wires, retransWire(w))
			if fin.CorruptPar != min(1, corrupt+1) {
				t.Fatal(fin)
			}
		}
		for i := range wires[0] {
			want := append([]byte(nil), wires[0][i]...)
			if i == 5 {
				want[len(want)/2] ^= 0xff
			}
			if !bytes.Equal(want, wires[1][i]) {
				t.Fatal(i)
			}
		}
	})
}

func TestComparisonDropParityLedger(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		gfInit()
		want := map[string][3]int{"parity": {4, 1, 2}, "pad_junk": {2, 0, 0}, "dup": {2, 0, 0}}
		for _, kind := range []string{"parity", "pad_junk", "dup"} {
			c, w, a := comparisonFixture(t, kind, 2, 1, 2)
			c.dropParity = 0
			traceWriteInitial(t, c, a, 1)
			traceWriteInitial(t, c, a, 2)
			fin := c.finalSendStats()
			wire := retransWire(w)
			var received []uint32
			for _, d := range wire {
				received = append(received, crc32.ChecksumIEEE(d))
			}
			c.mu.Lock()
			c.fbLast, c.fbCount = &fbRec{version: fbVer, crcs: received}, 1
			c.mu.Unlock()
			got, d := c.arrivalEvidence(true)
			if got.Src != "c1" || got.Sent != want[kind][0] || got.Lost != want[kind][1] || got.Trunc || d.Reason != "complete_crc_lists" {
				t.Fatalf("%s ledger: arrivals %+v c1 %+v", kind, got, d)
			}
			if len(c.ffParCRC) != want[kind][2] || fin.DroppedPar != 1 || len(wire) != 3 {
				t.Fatalf("%s: parity CRCs %d dropped %d wire %d", kind, len(c.ffParCRC), fin.DroppedPar, len(wire))
			}
		}
	})
}

func TestComparisonFlagValidation(t *testing.T) {
	for _, kind := range []string{"pad", "dup"} {
		pad, dup := kind == "pad", kind == "dup"
		if err := checkComparisonFlags(pad, dup, "client", "fec", "v3", -1); err != nil {
			t.Fatal(err)
		}
		for _, v := range [][3]string{{"server", "fec", "v3"}, {"client", "off", "v3"}, {"client", "buf", "v3"}, {"client", "auto", "v3"}, {"client", "auto3", "v3"}, {"client", "fec", "v2"}} {
			if checkComparisonFlags(pad, dup, v[0], v[1], v[2], -1) == nil {
				t.Fatal(kind, v)
			}
		}
		if checkComparisonFlags(pad, dup, "client", "fec", "v3", 3) == nil {
			t.Fatal("corrupt conflict")
		}
	}
	if checkComparisonFlags(true, true, "client", "fec", "v3", -1) == nil {
		t.Fatal("mutual conflict")
	}
	if checkComparisonFlags(false, false, "server", "off", "v2", 3) != nil {
		t.Fatal("normal flags changed")
	}
}
