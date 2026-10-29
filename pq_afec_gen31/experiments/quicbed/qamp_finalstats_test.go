package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"math"
	"net"
	"reflect"
	"sync"
	"testing"
	"testing/synctest"
	"time"
)

type finalStatsWrite struct {
	data []byte
	err  error
}

type finalStatsConn struct {
	net.PacketConn
	mu        sync.Mutex
	writes    []finalStatsWrite
	closed    bool
	parityErr error
	block     func([]byte) bool
	blocked   bool
	entered   chan struct{}
	release   chan struct{}
}

func (c *finalStatsConn) WriteTo(b []byte, addr net.Addr) (int, error) {
	c.mu.Lock()
	var err error
	if c.closed {
		err = net.ErrClosed
	} else if parseFecBlock(b) != nil {
		err = c.parityErr
	}
	c.writes = append(c.writes, finalStatsWrite{append([]byte(nil), b...), err})
	block := !c.blocked && c.block != nil && c.block(b)
	if block {
		c.blocked = true
	}
	c.mu.Unlock()
	if block {
		close(c.entered)
		<-c.release
	}
	if err != nil {
		return 0, err
	}
	return len(b), nil
}

func (c *finalStatsConn) Close() error {
	c.mu.Lock()
	c.closed = true
	c.mu.Unlock()
	return nil
}

func (c *finalStatsConn) ledger() (int, int64, int) {
	c.mu.Lock()
	defer c.mu.Unlock()
	parities, originals := 0, 0
	var parityBytes int64
	for _, w := range c.writes {
		if w.err != nil {
			continue
		}
		if parseFecBlock(w.data) != nil {
			parities++
			parityBytes += int64(len(w.data))
		} else {
			originals++
		}
	}
	return parities, parityBytes, originals
}

func finalStatsFixture(mode string, m, expectK int) (*fecConn, *finalStatsConn, net.Addr) {
	wire := &finalStatsConn{entered: make(chan struct{}), release: make(chan struct{})}
	fc := &fecConn{mode: mode, m: m, expectK: expectK,
		dropParity: -1, corruptParity: -1, parityDelay: time.Millisecond,
		layout: "v2", lead: -1}
	fc.PacketConn = wire
	return fc, wire, &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: 4433}
}

func finalStatsInitial(seed byte) []byte {
	return leadTestInitial(leadTestDCID, leadTestSCID, 1200, seed)
}

func finalStatsWriteInitial(t *testing.T, fc *fecConn, addr net.Addr, seed byte) {
	t.Helper()
	d := finalStatsInitial(seed)
	if n, err := fc.WriteTo(d, addr); err != nil || n != len(d) {
		t.Fatalf("Initial WriteTo = %d, %v", n, err)
	}
}

func finalStatsStart(t *testing.T, fc *fecConn) <-chan clientStats {
	t.Helper()
	done := make(chan clientStats, 1)
	go func() { done <- fc.finalSendStats() }()
	synctest.Wait()
	fc.mu.Lock()
	final := fc.txFinal
	fc.mu.Unlock()
	if !final {
		t.Fatal("finalization did not close the send registration gate")
	}
	return done
}

func finalStatsMustWait(t *testing.T, done <-chan clientStats) {
	t.Helper()
	select {
	case <-done:
		t.Fatal("finalization returned with an accepted send still in progress")
	default:
	}
}

func finalStatsCheckLedger(t *testing.T, st clientStats, wire *finalStatsConn) {
	t.Helper()
	n, b, _ := wire.ledger()
	if st.ParitySent != n || st.BytesParity != b {
		t.Fatalf("stats parity %d/%d bytes, ledger %d/%d bytes", st.ParitySent, st.BytesParity, n, b)
	}
}

func TestFinalSendStatsWaitsForAcceptedParity(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		gfInit()
		fc, wire, addr := finalStatsFixture("fec", 1, 0)
		wire.block = func(d []byte) bool { return parseFecBlock(d) != nil }
		finalStatsWriteInitial(t, fc, addr, 1)
		<-wire.entered
		old := fc.snapshot()
		n, b, _ := wire.ledger()
		if n != 1 || b <= 0 || old.ParitySent != 0 || old.BytesParity != 0 {
			t.Fatalf("fixture did not expose accepted-but-unaccounted parity: old %+v, ledger %d/%d", old, n, b)
		}
		fc.mu.Lock()
		detached := len(fc.flight) == 0
		fc.mu.Unlock()
		if !detached {
			t.Fatal("timer callback did not detach its flight")
		}
		wire.Close()
		done := finalStatsStart(t, fc)
		finalStatsMustWait(t, done)
		close(wire.release)
		fin := <-done
		finalStatsCheckLedger(t, fin, wire)
		if fin.FirstFlightParity != 1 || fin.FirstFlightParityBytes != b {
			t.Fatalf("first-flight parity was not completed: %+v", fin)
		}
		if old.ParitySent != 0 || old.BytesParity != 0 {
			t.Fatal("finalization mutated the policy snapshot")
		}
	})
}

func TestFinalSendStatsIncludesLateACKInRowsAndTotals(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		gfInit()
		fc, wire, addr := finalStatsFixture("fec", 2, 1)
		fc.layout, fc.lead = "v3", 1
		finalStatsWriteInitial(t, fc, addr, 1)
		old := fc.snapshot()
		fc.mu.Lock()
		fc.srvBig, fc.expectK = true, 0
		fc.mu.Unlock()
		finalStatsWriteInitial(t, fc, addr, 2)
		<-time.After(2 * fc.parityDelay)
		synctest.Wait()
		wire.Close()
		fin := fc.finalSendStats()
		finalStatsCheckLedger(t, fin, wire)
		row := trial{Ms: 50, Dgrams: old.InitialDgram, Parity: old.ParitySent,
			Layout: old.Layout, Lead: old.Lead}
		agg := clientStats{ParitySent: 7, BytesParity: 123,
			FlightSizes: map[string]int{"1": 3}, FbRecv: 8}
		recordFinalSendStats(&row, &agg, fin)
		if row.Dgrams != 2 || row.Parity != 3 || row.LaterParity != 1 || row.FFLead != 1 ||
			row.FFParity != 2 || row.FFParityBytes != old.FirstFlightParityBytes || row.Ms != 50 {
			t.Fatalf("late ACK missing from row: %+v", row)
		}
		if agg.ParitySent != 10 || agg.BytesParity != 123+fin.BytesParity ||
			agg.InitialDgram != 2 || agg.BytesOrig != 2400 || agg.Flights != 2 ||
			agg.FlightSizes["1"] != 5 || agg.LaterParitySent != 1 || agg.FbRecv != 8 {
			t.Fatalf("late ACK missing from aggregate or feedback overwritten: %+v", agg)
		}
		for _, output := range []any{row, auto3Row(row, auto3Plan{}, p3ObsInfo{Y: -1}, nil, 0)} {
			data, err := json.Marshal(output)
			if err != nil {
				t.Fatal(err)
			}
			var got trial
			if err := json.Unmarshal(data, &got); err != nil {
				t.Fatal(err)
			}
			if got.Parity != 3 || got.LaterParity != 1 || got.Dgrams != 2 {
				t.Fatalf("serialized row retained stale counters: %s", data)
			}
		}
		if old.ParitySent != 2 || old.InitialDgram != 1 || old.LaterParitySent != 0 || old.FlightSizes["1"] != 1 {
			t.Fatalf("late ACK mutated the policy snapshot: %+v", old)
		}
	})
}

func TestFinalSendStatsRegistrationBoundaries(t *testing.T) {
	t.Run("registered Initial creates timer after finalization starts", func(t *testing.T) {
		synctest.Test(t, func(t *testing.T) {
			fc, wire, addr := finalStatsFixture("off", 1, 0)
			wire.block = func(d []byte) bool { return parseFecBlock(d) == nil }
			writeDone := make(chan error, 1)
			go func() {
				_, err := fc.WriteTo(finalStatsInitial(1), addr)
				writeDone <- err
			}()
			<-wire.entered
			wire.Close()
			done := finalStatsStart(t, fc)
			finalStatsMustWait(t, done)
			close(wire.release)
			if err := <-writeDone; err != nil {
				t.Fatal(err)
			}
			fin := <-done
			if fin.InitialDgram != 1 || fin.BytesOrig != 1200 || fin.Flights != 0 {
				t.Fatalf("registered Initial lost or unsent buffer flushed: %+v", fin)
			}
			fc.mu.Lock()
			clean := fc.timer == nil && len(fc.flight) == 0
			fc.mu.Unlock()
			if !clean {
				t.Fatal("timer created by the registered Initial survived finalization")
			}
			_, _, originals := wire.ledger()
			if originals != 1 {
				t.Fatalf("accepted original count = %d", originals)
			}
		})
	})
	t.Run("callback starts after finalization", func(t *testing.T) {
		synctest.Test(t, func(t *testing.T) {
			fc, wire, addr := finalStatsFixture("fec", 1, 0)
			finalStatsWriteInitial(t, fc, addr, 1)
			fc.mu.Lock()
			fc.timer.Stop()
			fc.mu.Unlock()
			gate, callbackDone := make(chan struct{}), make(chan struct{})
			go func() {
				<-gate
				fc.flushFlight()
				close(callbackDone)
			}()
			wire.Close()
			fin := fc.finalSendStats()
			close(gate)
			<-callbackDone
			if got := fc.snapshot(); !reflect.DeepEqual(got, fin) {
				t.Fatalf("late callback changed final counters: before %+v, after %+v", fin, got)
			}
			if len(wire.writes) != 0 {
				t.Fatal("late callback attempted a send")
			}
		})
	})
}

func TestFinalSendStatsRejectsInitialAndDiscardsBuffer(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		fc, wire, addr := finalStatsFixture("fec", 2, 0)
		finalStatsWriteInitial(t, fc, addr, 1)
		wire.Close()
		fin := fc.finalSendStats()
		if n, err := fc.WriteTo(finalStatsInitial(2), addr); n != 0 || !errors.Is(err, net.ErrClosed) {
			t.Fatalf("post-finalization Initial = %d, %v", n, err)
		}
		fc.flushFlight()
		<-time.After(2 * fc.parityDelay)
		synctest.Wait()
		if len(wire.writes) != 0 || fin.ParitySent != 0 || fin.ParityFail != 0 || fin.Flights != 0 {
			t.Fatalf("finalization force-flushed buffered data: writes %d, stats %+v", len(wire.writes), fin)
		}
		if got := fc.finalSendStats(); !reflect.DeepEqual(got, fin) {
			t.Fatalf("finalization was not stable: before %+v, after %+v", fin, got)
		}
	})
}

func TestFinalSendStatsModesAndFailures(t *testing.T) {
	for _, mode := range []string{"off", "buf", "fec"} {
		for _, timer := range []bool{false, true} {
			for _, fault := range []string{"none", "error", "drop", "corrupt"} {
				name := mode + "/" + fault + "/immediate"
				if timer {
					name = mode + "/" + fault + "/timer"
				}
				t.Run(name, func(t *testing.T) {
					synctest.Test(t, func(t *testing.T) {
						gfInit()
						expectK := 2
						if timer {
							expectK = 0
						}
						fc, wire, addr := finalStatsFixture(mode, 2, expectK)
						switch fault {
						case "error":
							wire.parityErr = errors.New("parity send rejected")
						case "drop":
							fc.dropParity = 1
						case "corrupt":
							fc.corruptParity = 1
						}
						finalStatsWriteInitial(t, fc, addr, 1)
						finalStatsWriteInitial(t, fc, addr, 2)
						if timer {
							<-time.After(2 * fc.parityDelay)
							synctest.Wait()
						}
						wire.Close()
						fin := fc.finalSendStats()
						finalStatsCheckLedger(t, fin, wire)
						wantSent, wantFail, wantDrop, wantCorrupt := 0, 0, 0, 0
						if mode == "fec" {
							wantSent = 2
							switch fault {
							case "error":
								wantSent, wantFail = 0, 2
							case "drop":
								wantSent, wantDrop = 1, 1
							case "corrupt":
								wantCorrupt = 1
							}
						}
						if fin.ParitySent != wantSent || fin.ParityFail != wantFail ||
							fin.DroppedPar != wantDrop || fin.CorruptPar != wantCorrupt ||
							fin.FirstFlightParity != wantSent || fin.FirstFlightParityBytes != fin.BytesParity ||
							fin.InitialDgram != 2 || fin.FirstFlightDgrams != 2 || fin.BytesOrig != 2400 ||
							fin.FirstFlightBytes != 2400 || fin.Flights != 1 {
							t.Fatalf("unexpected final counters: %+v", fin)
						}
						var row trial
						var agg clientStats
						recordFinalSendStats(&row, &agg, fin)
						if agg.ParitySent != wantSent || agg.ParityFail != wantFail ||
							agg.DroppedPar != wantDrop || agg.CorruptPar != wantCorrupt {
							t.Fatalf("fault counts did not reach aggregate: %+v", agg)
						}
					})
				})
			}
		}
	}
	for _, failed := range []bool{false, true} {
		name := "v3 later success"
		if failed {
			name = "v3 later error"
		}
		t.Run(name, func(t *testing.T) {
			synctest.Test(t, func(t *testing.T) {
				gfInit()
				fc, wire, addr := finalStatsFixture("fec", 2, 1)
				fc.layout, fc.lead = "v3", 1
				finalStatsWriteInitial(t, fc, addr, 1)
				fc.mu.Lock()
				fc.srvBig = true
				fc.mu.Unlock()
				if failed {
					wire.parityErr = errors.New("later parity rejected")
				}
				finalStatsWriteInitial(t, fc, addr, 2)
				wire.Close()
				fin := fc.finalSendStats()
				finalStatsCheckLedger(t, fin, wire)
				wantLater, wantFail := 1, 0
				if failed {
					wantLater, wantFail = 0, 1
				}
				if fin.LaterParitySent != wantLater || fin.ParityFail != wantFail ||
					fin.ParitySent != 2+wantLater || fin.FirstFlightParity != 2 || fin.FirstFlightLeadDgrams != 1 {
					t.Fatalf("later-flight accounting: %+v", fin)
				}
			})
		})
	}
}

func TestFinalSendStatsPreservesHCTAndPolicyObservation(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		gfInit()
		fc, wire, addr := finalStatsFixture("fec", 2, 1)
		fc.layout, fc.lead = "v3", 1
		wire.block = func(d []byte) bool {
			fb := parseFecBlock(d)
			return fb != nil && fb.index == 1
		}
		writeDone := make(chan error, 1)
		go func() {
			_, err := fc.WriteTo(finalStatsInitial(1), addr)
			writeDone <- err
		}()
		<-wire.entered
		start := time.Now()
		dialDone := make(chan time.Time, 1)
		time.AfterFunc(37*time.Millisecond, func() { dialDone <- time.Now() })
		el := (<-dialDone).Sub(start)
		st := fc.snapshot()
		fc.countRx(17762)
		_, _, _, srvBytes := fc.counts()
		hct := float64(el.Microseconds()) / 1000
		row := trial{Ms: hct, OK: true, SrvBytes: srvBytes, PathRTTMS: 25,
			PathRTTValid: true, PathRTTSource: "quic_ack_min_rtt", Layout: st.Layout, Lead: st.Lead}
		cache := newDestCache("")
		cache.observe(addr.String(), st.FirstFlightDgrams, float64(srvBytes), hct, false, true)
		nSent := st.FirstFlightDgrams + st.FirstFlightParity
		cache.observeSymbols(addr.String(), nSent, 0, hct)
		c3, err := loadDestCache3("")
		if err != nil {
			t.Fatal(err)
		}
		plan := auto3Plan{Action: p3Action{Lead: 1, T: 1}, M: 2, Lead: 1}
		info, after, obsErr := c3.observe(addr.String(), plan.Action, hct, true,
			st.FirstFlightDgrams, float64(srvBytes), row.PathRTTMS, row.PathRTTValid,
			1280, 10, cPktDefault)
		if obsErr != nil {
			t.Fatal(obsErr)
		}
		beforePolicy, err := json.Marshal([]any{cache.M, c3.Dests})
		if err != nil {
			t.Fatal(err)
		}
		wire.Close()
		done := finalStatsStart(t, fc)
		finalStatsMustWait(t, done)
		<-time.After(5 * time.Second)
		close(wire.release)
		if err := <-writeDone; err != nil {
			t.Fatal(err)
		}
		fin := <-done
		var agg clientStats
		recordFinalSendStats(&row, &agg, fin)
		output := auto3Row(row, plan, info, obsErr, after)
		if time.Since(start) != 5037*time.Millisecond || output.Ms != 37 ||
			output.SrvBytes != 17762 || output.PathRTTMS != 25 || output.Parity != 2 ||
			output.FFParity != 2 || st.FirstFlightParity != 1 || agg.ParitySent != 2 {
			t.Fatalf("cleanup affected HCT or final send fields were stale: row %+v, old %+v, aggregate %+v", output, st, agg)
		}
		v2 := cache.M[addr.String()]
		v3 := c3.Dests[addr.String()]
		if v2.MinHCT != 37 || v2.K != st.FirstFlightDgrams || v2.ServerFlight != float64(srvBytes) ||
			math.Abs(v2.SymObs-1.99) > 1e-12 || nSent != 2 || v3.MinHCT != 37 ||
			len(v3.State.HCT[plan.Action.Key()]) != 1 || v3.State.HCT[plan.Action.Key()][0] != 37 {
			t.Fatalf("policy consumed final counters or cleanup duration: v2 %+v, v3 %+v", v2, v3)
		}
		afterPolicy, err := json.Marshal([]any{cache.M, c3.Dests})
		if err != nil {
			t.Fatal(err)
		}
		if !bytes.Equal(beforePolicy, afterPolicy) {
			t.Fatal("final send accounting changed policy state")
		}
	})
}
