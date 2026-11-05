package main

import (
	"bytes"
	"encoding/json"
	"net"
	"testing"
	"testing/synctest"
	"time"

	"github.com/quic-go/quic-go/qlog"
)

func retransWire(w *finalStatsConn) [][]byte {
	w.mu.Lock()
	defer w.mu.Unlock()
	var out [][]byte
	for _, x := range w.writes {
		if x.err == nil {
			out = append(out, append([]byte{}, x.data...))
		}
	}
	return out
}

func TestRetransOriginalFirstMatrix(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		gfInit()
		for m := 1; m <= 4; m++ {
			for lead := 0; lead <= m; lead++ {
				for k := 1; k <= 3; k++ {
					c, w, a := flightInputFixture(flightExpectation{k, "explicit", "all_flights"})
					c.mode = "fec"
					c.m = m
					c.layout = "v3"
					c.lead = lead
					c.retransMode = "original_first"
					c.observer = newMemoryTrace(time.Now())
					pos := 0
					for round := 0; round < 4; round++ {
						if round == 1 {
							c.observer.RecordEvent(qlog.LossTimerUpdated{Type: qlog.LossTimerUpdateTypeExpired, TimerType: qlog.TimerTypePTO})
						}
						if round == 2 {
							c.mu.Lock()
							c.serverSeen = true
							c.mu.Unlock()
						}
						if round == 3 {
							c.mu.Lock()
							c.srvBig = true
							c.mu.Unlock()
						}
						for i := 0; i < k; i++ {
							traceWriteInitial(t, c, a, byte(round*k+i))
						}
						all := retransWire(w)
						out := all[pos:]
						pos = len(all)
						ld, trail, phase, rule := lead, m-lead, "first_bundle", "first_layout"
						if round == 1 || round == 2 {
							ld = 0
							trail = 1
							phase = "pre_response_followup"
							rule = "original_first"
						}
						if round == 3 {
							ld = 0
							trail = min(1, m-lead)
							phase = "post_response"
							rule = "post_response_xor"
						}
						if len(out) != k+ld+trail {
							t.Fatal(m, lead, k, round, len(out), ld, trail)
						}
						originals := [][]byte{}
						for i, d := range out {
							fb := parseFecBlock(d)
							if i >= ld && i < ld+k {
								if fb != nil {
									t.Fatal("parity before original", m, lead, k, round, i)
								}
								originals = append(originals, d)
							} else {
								if fb == nil || fb.ver != fecVerLead || fb.lead != ld || fb.m != ld+trail || fb.k != k || fb.flight != uint16(round+1) {
									t.Fatal(m, lead, k, round, i, fb)
								}
							}
						}
						st := c.snapshot()
						rec := st.FlightTrace.Records[round]
						if rec.Shape.Phase != phase || rec.Shape.Rule != rule || rec.Shape.Lead != ld || rec.Shape.Trail != trail || rec.Shape.OriginalImmediate != (round == 3) || rec.ParitySent != ld+trail || rec.ParityBytes <= 0 && ld+trail > 0 || rec.Shape.PTOCountAtStart != min(round, 1) || rec.Shape.PTOScope != "qlog_loss_timer_expired_lower_bound" {
							t.Fatal(m, lead, k, round, rec)
						}
						if round == 1 {
							for drop := 0; drop < k; drop++ {
								input := append([][]byte{}, out[:drop]...)
								input = append(input, out[drop+1:]...)
								sv := &decodeConn{mode: "fec"}
								sv.PacketConn = &auditConn{scriptConn: scriptConn{dgs: input, addr: a}}
								got := [][]byte{}
								buf := make([]byte, 2048)
								for {
									n, _, err := sv.ReadFrom(buf)
									if err != nil {
										break
									}
									got = append(got, append([]byte{}, buf[:n]...))
								}
								found := false
								for _, d := range got {
									if bytes.Equal(d, originals[drop]) {
										found = true
									}
								}
								if !found || sv.stats.Recovered != 1 {
									t.Fatal("followup single erasure not recovered", m, lead, k, drop, sv.stats)
								}
							}
						}
					}
					fin := c.finalSendStats()
					var row trial
					var agg clientStats
					recordFinalSendStats(&row, &agg, fin)
					var count int
					var total int64
					for _, f := range row.FlightTrace.Records {
						count += f.ParitySent
						total += f.ParityBytes
					}
					if count != row.Parity || total != row.BytesParity || row.RetransLayout != "original_first" || fin.FirstFlightParity != m || fin.LaterParitySent != 2+min(1, m-lead) {
						t.Fatal(m, lead, k, row)
					}
					data, err := json.Marshal(auto3Row(row, auto3Plan{}, p3ObsInfo{Y: -1}, nil, 0))
					if err != nil {
						t.Fatal(err)
					}
					var decoded trial
					if err = json.Unmarshal(data, &decoded); err != nil || decoded.BytesParity != total || decoded.RetransLayout != "original_first" {
						t.Fatal(err, string(data))
					}
				}
			}
		}
	})
}

func TestRetransEmptyModeFollowsCLIDefault(t *testing.T) {
	def := defaultRunSettings().RetransLayout
	if def != "repeat_first" {
		t.Fatalf("CLI retrans-layout default %q", def)
	}
	synctest.Test(t, func(t *testing.T) {
		gfInit()
		for m := 1; m <= 4; m++ {
			for lead := 0; lead <= m; lead++ {
				for k := 1; k <= 3; k++ {
					var wires [2][][]byte
					var rows [2]trial
					for i, mode := range []string{"", def} {
						c, w, a := flightInputFixture(flightExpectation{k, "explicit", "all_flights"})
						c.mode = "fec"
						c.m = m
						c.layout = "v3"
						c.lead = lead
						c.retransMode = mode
						for round := 0; round < 3; round++ {
							if round == 2 {
								c.mu.Lock()
								c.srvBig = true
								c.mu.Unlock()
							}
							for j := 0; j < k; j++ {
								traceWriteInitial(t, c, a, byte(1+round*k+j))
							}
						}
						fin := c.finalSendStats()
						wires[i] = retransWire(w)
						var agg clientStats
						recordFinalSendStats(&rows[i], &agg, fin)
						rec := fin.FlightTrace.Records[1]
						if rec.Shape.Phase != "pre_response_followup" || rec.Shape.Rule != def || rec.Shape.Lead != lead || rec.Shape.Trail != m-lead || rec.ParitySent != m {
							t.Fatal(mode, m, lead, k, rec)
						}
					}
					if rows[0].RetransLayout != def || rows[1].RetransLayout != def || len(wires[0]) != len(wires[1]) {
						t.Fatal(m, lead, k, rows[0].RetransLayout, rows[1].RetransLayout, len(wires[0]), len(wires[1]))
					}
					for i := range wires[0] {
						if !bytes.Equal(wires[0][i], wires[1][i]) {
							t.Fatal("empty retrans mode changed the wire", m, lead, k, i)
						}
					}
				}
			}
		}
	})
}

func TestRetransShapeIsFixedAtBundleStart(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		gfInit()
		c, w, a := flightInputFixture(flightExpectation{2, "explicit", "all_flights"})
		c.mode = "fec"
		c.m = 4
		c.layout = "v3"
		c.lead = 3
		c.retransMode = "original_first"
		traceWriteInitial(t, c, a, 1)
		traceWriteInitial(t, c, a, 2)
		traceWriteInitial(t, c, a, 3)
		c.mu.Lock()
		c.srvBig = true
		c.mu.Unlock()
		traceWriteInitial(t, c, a, 4)
		st := c.snapshot()
		f := st.FlightTrace.Records[1]
		if f.Shape.Phase != "pre_response_followup" || f.Shape.Rule != "original_first" || f.OriginalImmediate || f.ParitySent != 1 {
			t.Fatal(f)
		}
		wire := retransWire(w)
		if parseFecBlock(wire[6]) != nil || parseFecBlock(wire[7]) != nil || parseFecBlock(wire[8]) == nil {
			t.Fatal("unstable followup shape")
		}
		traceWriteInitial(t, c, a, 5)
		traceWriteInitial(t, c, a, 6)
		fin := c.finalSendStats()
		if !fin.FlightTrace.Records[2].OriginalImmediate || fin.FlightTrace.Records[2].Shape.Phase != "post_response" {
			t.Fatal(fin)
		}
	})
}

func TestRetransIDWrapKeepsFollowup(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		gfInit()
		c, _, a := flightInputFixture(flightExpectation{1, "explicit", "all_flights"})
		c.mode = "fec"
		c.layout = "v3"
		c.m = 4
		c.lead = 4
		c.retransMode = "original_first"
		traceWriteInitial(t, c, a, 1)
		c.mu.Lock()
		c.flightID = 65535
		c.mu.Unlock()
		traceWriteInitial(t, c, a, 2)
		fin := c.finalSendStats()
		f := fin.FlightTrace.Records[1]
		if f.ID != 0 || f.Shape.Phase != "pre_response_followup" || f.Shape.Lead != 0 || f.Shape.Trail != 1 || f.ParitySent != 1 {
			t.Fatal(fin)
		}
	})
}

func TestRetransDisabledAndLegacyModes(t *testing.T) {
	for _, mode := range []string{"off", "buf", "fec"} {
		synctest.Test(t, func(t *testing.T) {
			gfInit()
			c, _, a := flightInputFixture(flightExpectation{1, "explicit", "all_flights"})
			c.mode = mode
			c.m = 3
			c.layout = "v2"
			c.lead = -1
			traceWriteInitial(t, c, a, 1)
			traceWriteInitial(t, c, a, 2)
			fin := c.finalSendStats()
			if fin.RetransLayout != "not_applicable" {
				t.Fatal(fin)
			}
			for _, f := range fin.FlightTrace.Records {
				if mode == "fec" {
					if f.Shape.Rule != "v2_layout" || f.ParitySent != 3 {
						t.Fatal(f)
					}
				} else if f.Shape.Rule != "disabled" || f.ParitySent != 0 {
					t.Fatal(f)
				}
			}
		})
	}
}

func TestRetransFlagValidation(t *testing.T) {
	for _, s := range []string{"original_first", "repeat_first"} {
		if err := checkRetransLayout(s); err != nil {
			t.Fatal(err)
		}
	}
	for _, s := range []string{"", "legacy", "original-first", "none"} {
		if checkRetransLayout(s) == nil {
			t.Fatal("invalid layout accepted", s)
		}
	}
}

var _ net.PacketConn = (*fecConn)(nil)
