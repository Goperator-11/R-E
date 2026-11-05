package main

import (
	"encoding/json"
	"errors"
	"math"
	"net"
	"reflect"
	"testing"
	"testing/synctest"
	"time"
)

func traceWriteInitial(t *testing.T, c *fecConn, a net.Addr, seed byte) {
	t.Helper()
	d := finalStatsInitial(seed)
	h := parseLongHdr(d)
	at := 7 + len(h.dcid) + len(h.scid)
	d[at] = 0
	copy(d[at+1:], appendVarint2(nil, uint64(len(d)-at-3)))
	if hasHandshake(d) {
		t.Fatal("invalid Initial fixture")
	}
	if n, err := c.WriteTo(d, a); err != nil || n != len(d) {
		t.Fatal(n, err)
	}
}

func traceClose(a, b float64) bool { return math.Abs(a-b) < 1e-9 }

func TestFlightTraceIntervals(t *testing.T) {
	for _, us := range []int{0, 100, 400} {
		synctest.Test(t, func(t *testing.T) {
			c, w, addr := flightInputFixture(flightExpectation{3, "explicit", "all_flights"})
			traceWriteInitial(t, c, addr, 1)
			time.Sleep(time.Duration(us) * time.Microsecond)
			synctest.Wait()
			traceWriteInitial(t, c, addr, 2)
			time.Sleep(300 * time.Microsecond)
			synctest.Wait()
			st := c.finalSendStats()
			wantFlights := 1
			if us == 400 {
				wantFlights = 2
			}
			if st.Flights != wantFlights || len(st.FlightTrace.Records) != wantFlights || st.FlightTrace.FlushedBytes != 2400 || st.FlightTrace.FlushedOriginals != 2 {
				t.Fatal(us, st)
			}
			for i, f := range st.FlightTrace.Records {
				first, last, k := 0.0, float64(us)/1000, 2
				if us == 400 {
					first = float64(i) * 0.4
					last = first
					k = 1
				}
				if !traceClose(f.FirstInputMS, first) || !traceClose(f.LastInputMS, last) || !traceClose(f.FlushMS, last+0.3) || !traceClose(f.EndMS, f.FlushMS) || !traceClose(f.BufferedLastWaitMS, 0.3) || !traceClose(f.BufferedFirstWaitMS, last+0.3-first) || f.ActualK != k || f.ExpectedK != 3 || f.Reason != "timer" || !f.KMismatch || !f.SplitSuspected || !f.Complete || !f.Flushed || f.OriginalImmediate || f.OriginalBytes != int64(k*1200) || f.FlushTxDgrams != k || f.FlushTxBytes != int64(k*1200) || f.FlushTxErrors != 0 {
					t.Fatal(us, f)
				}
			}
			_, _, sent := w.ledger()
			if sent != 2 {
				t.Fatal(sent)
			}
		})
	}
}

func TestFlightTraceExpectedAndUnobservableSplit(t *testing.T) {
	for _, k := range []int{1, 2} {
		synctest.Test(t, func(t *testing.T) {
			c, _, a := flightInputFixture(flightExpectation{k, "cached_k", "first_flight"})
			traceWriteInitial(t, c, a, 1)
			time.Sleep(100 * time.Microsecond)
			traceWriteInitial(t, c, a, 2)
			time.Sleep(300 * time.Microsecond)
			synctest.Wait()
			st := c.finalSendStats()
			f := st.FlightTrace.Records[0]
			if f.Reason != "expected_k" || f.ActualK != k || f.ExpectedK != k || f.KMismatch || f.SplitSuspected || f.BufferedLastWaitMS != 0 {
				t.Fatal(k, f)
			}
			if k == 1 {
				next := st.FlightTrace.Records[1]
				if next.ExpectedK != 0 || next.KMismatch || next.SplitSuspected || next.Reason != "timer" {
					t.Fatal(next)
				}
			} else if !traceClose(f.BufferedFirstWaitMS, 0.1) {
				t.Fatal(f)
			}
		})
	}
}

func TestFlightTraceStaleGeneration(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		c, _, a := flightInputFixture(flightExpectation{})
		traceWriteInitial(t, c, a, 1)
		c.mu.Lock()
		old := c.timerGeneration
		c.mu.Unlock()
		time.Sleep(100 * time.Microsecond)
		traceWriteInitial(t, c, a, 2)
		c.flushFlightFor("timer", old)
		if st := c.snapshot(); st.Flights != 0 || st.FlightTrace.StaleTriggers != 1 {
			t.Fatal(st)
		}
		time.Sleep(299 * time.Microsecond)
		synctest.Wait()
		if c.snapshot().Flights != 0 {
			t.Fatal("stale callback released a reset bundle")
		}
		time.Sleep(time.Microsecond)
		synctest.Wait()
		traceWriteInitial(t, c, a, 3)
		c.flushFlightFor("expected_k", old)
		if st := c.snapshot(); st.Flights != 1 || st.FlightTrace.StaleTriggers != 2 {
			t.Fatal(st)
		}
		fin := c.finalSendStats()
		c.flushFlightFor("timer", old)
		if !reflect.DeepEqual(fin, c.snapshot()) {
			t.Fatal("callback changed closed observation")
		}
	})
}

func TestFlightTraceImmediateModes(t *testing.T) {
	for _, mode := range []string{"off", "later"} {
		synctest.Test(t, func(t *testing.T) {
			gfInit()
			c, w, a := flightInputFixture(flightExpectation{})
			c.mode = mode
			if mode == "later" {
				c.mode = "fec"
				c.layout = "v3"
				c.lead = 0
				c.srvBig = true
			}
			traceWriteInitial(t, c, a, 1)
			_, _, n := w.ledger()
			if n != 1 {
				t.Fatal(mode, n)
			}
			time.Sleep(300 * time.Microsecond)
			synctest.Wait()
			fin := c.finalSendStats()
			f := fin.FlightTrace.Records[0]
			if !f.OriginalImmediate || f.BufferedFirstWaitMS != 0 || f.BufferedLastWaitMS != 0 || !traceClose(f.FlushMS, 0.3) {
				t.Fatal(mode, f)
			}
			if mode == "off" && f.FlushTxDgrams != 0 {
				t.Fatal(f)
			}
			if mode == "later" && f.FlushTxDgrams != 1 {
				t.Fatal(f)
			}
		})
	}
}

func TestFlightTraceNonInitialAndFinalDiscard(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		c, _, a := flightInputFixture(flightExpectation{3, "explicit", "all_flights"})
		traceWriteInitial(t, c, a, 1)
		time.Sleep(100 * time.Microsecond)
		if _, err := c.WriteTo([]byte{0x40, 1}, a); err != nil {
			t.Fatal(err)
		}
		traceWriteInitial(t, c, a, 2)
		time.Sleep(100 * time.Microsecond)
		fin := c.finalSendStats()
		tr := fin.FlightTrace
		if fin.Flights != 1 || tr.FlushedOriginals != 1 || tr.DiscardedOriginals != 1 || tr.FlushedBytes != 1200 || tr.DiscardedBytes != 1200 || len(tr.Records) != 2 {
			t.Fatal(fin)
		}
		f, d := tr.Records[0], tr.Records[1]
		if f.Reason != "non_initial" || !f.Flushed || !traceClose(f.FlushMS, 0.1) || d.Reason != "final_discard" || d.Flushed || !d.Complete || !traceClose(d.EndMS, 0.2) || d.FlushTxDgrams != 0 || d.BufferedFirstWaitMS != 0 {
			t.Fatal(tr)
		}
	})
}

func TestFlightTraceCompletionAndFirstSequence(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		gfInit()
		c, w, a := flightInputFixture(flightExpectation{})
		c.mode = "fec"
		w.block = func(b []byte) bool { return parseFecBlock(b) != nil }
		traceWriteInitial(t, c, a, 1)
		<-w.entered
		old := c.snapshot()
		if old.Flights != 1 || old.FlightTrace.Records[0].Complete {
			t.Fatal(old)
		}
		traceWriteInitial(t, c, a, 2)
		c.flushFlight()
		current := c.snapshot()
		if current.Flights != 2 || current.FirstFlightDgrams != 1 || current.FlightTrace.Records[0].Complete || !current.FlightTrace.Records[1].Complete || current.FlightTrace.Records[1].Sequence != 2 {
			t.Fatal(current)
		}
		time.Sleep(2 * time.Millisecond)
		close(w.release)
		synctest.Wait()
		fin := c.finalSendStats()
		if !fin.FlightTrace.Records[0].Complete || !traceClose(fin.FlightTrace.Records[0].EndMS, 2.3) || old.FlightTrace.Records[0].Complete {
			t.Fatal(old, fin)
		}
		finalStatsCheckLedger(t, fin, w)
	})
}

func TestFlightTraceBoundAndSnapshotRows(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		c, _, a := flightInputFixture(flightExpectation{1, "explicit", "all_flights"})
		for i := 0; i < flightTraceCap+2; i++ {
			traceWriteInitial(t, c, a, byte(i))
		}
		fin := c.finalSendStats()
		if fin.Flights != 130 || len(fin.FlightTrace.Records) != 128 || fin.FlightTrace.Omitted != 2 || fin.FlightTrace.FlushedOriginals != 130 || fin.FlightTrace.FlushedBytes != 156000 {
			t.Fatal(fin)
		}
		var row trial
		var agg clientStats
		recordFinalSendStats(&row, &agg, fin)
		recordFinalSendStats(&row, &agg, fin)
		if agg.FlightTrace.FlushedOriginals != 260 || len(agg.FlightTrace.Records) != 0 || agg.FlightTrace.Omitted != 4 {
			t.Fatal(agg)
		}
		data, err := json.Marshal(auto3Row(row, auto3Plan{}, p3ObsInfo{Y: -1}, nil, 0))
		if err != nil {
			t.Fatal(err)
		}
		var got trial
		if err = json.Unmarshal(data, &got); err != nil || !reflect.DeepEqual(row.FlightTrace, got.FlightTrace) {
			t.Fatal(err, string(data))
		}
		row.FlightTrace.Records[0].Reason = "changed"
		if c.snapshot().FlightTrace.Records[0].Reason != "expected_k" || fin.FlightTrace.Records[0].Reason != "expected_k" {
			t.Fatal("snapshot alias")
		}
	})
}

func TestFlightTraceSendFailure(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		gfInit()
		c, w, a := flightInputFixture(flightExpectation{1, "explicit", "all_flights"})
		c.mode = "fec"
		w.parityErr = errors.New("rejected parity")
		traceWriteInitial(t, c, a, 1)
		fin := c.finalSendStats()
		f := fin.FlightTrace.Records[0]
		if !f.Complete || f.FlushTxErrors != 1 || f.FlushTxDgrams != 1 || f.FlushTxBytes != 1200 || fin.ParityFail != 1 || fin.ParitySent != 0 {
			t.Fatal(fin)
		}
	})
}
