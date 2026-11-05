package main

import (
	"encoding/json"
	"net"
	"testing"
	"testing/synctest"
	"time"
)

func TestFlightExpectationPriority(t *testing.T) {
	warm := auto3Plan{Decision: p3Decision{K: 2, HasEJ: true}}
	for _, x := range []struct {
		k        int
		explicit bool
		mode     string
		plan     auto3Plan
		want     flightExpectation
	}{
		{0, false, "auto3", warm, flightExpectation{2, "cached_k", "first_flight"}},
		{0, true, "auto3", warm, flightExpectation{0, "explicit_timer", "timer_only"}},
		{3, true, "auto3", warm, flightExpectation{3, "explicit", "all_flights"}},
		{0, false, "auto3", auto3Plan{}, flightExpectation{0, "timer_only", "timer_only"}},
		{0, false, "auto3", auto3Plan{Decision: p3Decision{K: 5, HasEJ: true}}, flightExpectation{0, "timer_only", "timer_only"}},
		{0, false, "auto3", auto3Plan{Decision: p3Decision{K: 2}}, flightExpectation{0, "timer_only", "timer_only"}},
		{0, false, "auto", warm, flightExpectation{0, "timer_only", "timer_only"}},
		{0, false, "fec", warm, flightExpectation{0, "timer_only", "timer_only"}},
		{32, true, "fec", warm, flightExpectation{32, "explicit", "all_flights"}},
	} {
		if got := chooseFlightExpectation(x.k, x.explicit, x.mode, x.plan); got != x.want {
			t.Fatal(x, got)
		}
	}
}

func TestFlightExpectationUsesActualCacheDecision(t *testing.T) {
	c, err := loadDestCache3("")
	if err != nil {
		t.Fatal(err)
	}
	p, err := c.plan("cold", 1280, 0, cPktDefault)
	if err != nil {
		t.Fatal(err)
	}
	if chooseFlightExpectation(0, false, "auto3", p).K != 0 {
		t.Fatal("cold k invented", p)
	}
	st := newP3State()
	st.KHist = []int{2, 3, 2}
	st.SHist = []float64{6000}
	c.Dests["warm"] = &cache3Entry{State: st, MinRTT: 50, RTTObs: 1, Conns: 3}
	p, err = c.plan("warm", 1280, 0, cPktDefault)
	if err != nil {
		t.Fatal(err)
	}
	if p.Decision.K != 2 || chooseFlightExpectation(0, false, "auto3", p) != (flightExpectation{2, "cached_k", "first_flight"}) {
		t.Fatal(p)
	}
}

func flightInputFixture(hint flightExpectation) (*fecConn, *finalStatsConn, net.Addr) {
	c, w, a := finalStatsFixture("buf", 1, hint.K)
	c.expectation = hint
	c.parityDelay = 300 * time.Microsecond
	return c, w, a
}

func TestFlightCachedKOnlyFirstBundle(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		c, _, addr := flightInputFixture(flightExpectation{2, "cached_k", "first_flight"})
		defer c.finalSendStats()
		finalStatsWriteInitial(t, c, addr, 1)
		if c.snapshot().Flights != 0 {
			t.Fatal("early flush")
		}
		finalStatsWriteInitial(t, c, addr, 2)
		if st := c.snapshot(); st.Flights != 1 || st.FirstFlightDgrams != 2 {
			t.Fatal(st)
		}
		finalStatsWriteInitial(t, c, addr, 3)
		finalStatsWriteInitial(t, c, addr, 4)
		if c.snapshot().Flights != 1 {
			t.Fatal("cached k applied to retransmission")
		}
		time.Sleep(299 * time.Microsecond)
		synctest.Wait()
		if c.snapshot().Flights != 1 {
			t.Fatal("timer shortened")
		}
		time.Sleep(time.Microsecond)
		synctest.Wait()
		if st := c.snapshot(); st.Flights != 2 || st.FirstFlightDgrams != 2 {
			t.Fatal(st)
		}
		c.mu.Lock()
		c.flightID = 1
		c.flight = [][]byte{{1}, {2}}
		ready := c.expectationReadyLocked()
		c.flight = nil
		c.mu.Unlock()
		if ready {
			t.Fatal("flight ID wrap reused cached expectation")
		}
	})
}

func TestFlightWrongKRetainsTimerFallback(t *testing.T) {
	for _, k := range []int{1, 3} {
		synctest.Test(t, func(t *testing.T) {
			c, _, addr := flightInputFixture(flightExpectation{k, "cached_k", "first_flight"})
			defer c.finalSendStats()
			finalStatsWriteInitial(t, c, addr, 1)
			finalStatsWriteInitial(t, c, addr, 2)
			before := c.snapshot()
			if k == 1 && (before.Flights != 1 || before.FirstFlightDgrams != 1) {
				t.Fatal(before)
			}
			if k == 3 && before.Flights != 0 {
				t.Fatal(before)
			}
			time.Sleep(300 * time.Microsecond)
			synctest.Wait()
			got := c.snapshot()
			if k == 1 && (got.Flights != 2 || got.FirstFlightDgrams != 1) {
				t.Fatal("low estimate hidden", got)
			}
			if k == 3 && (got.Flights != 1 || got.FirstFlightDgrams != 2) {
				t.Fatal("high estimate waited forever", got)
			}
		})
	}
}

func TestFlightExplicitZeroAndPositiveScope(t *testing.T) {
	for _, k := range []int{0, 2} {
		synctest.Test(t, func(t *testing.T) {
			hint := chooseFlightExpectation(k, true, "auto3", auto3Plan{Decision: p3Decision{K: 2, HasEJ: true}})
			c, _, addr := flightInputFixture(hint)
			defer c.finalSendStats()
			for flight := 0; flight < 2; flight++ {
				finalStatsWriteInitial(t, c, addr, byte(flight*2+1))
				finalStatsWriteInitial(t, c, addr, byte(flight*2+2))
				if k == 0 {
					if c.snapshot().Flights != flight {
						t.Fatal("explicit zero used cached k")
					}
					time.Sleep(300 * time.Microsecond)
					synctest.Wait()
				}
				if c.snapshot().Flights != flight+1 {
					t.Fatal("explicit positive scope changed")
				}
			}
		})
	}
}

func TestFlightExpectationRecordedInFinalRow(t *testing.T) {
	hint := flightExpectation{2, "cached_k", "first_flight"}
	c, _, _ := flightInputFixture(hint)
	fin := c.finalSendStats()
	var row trial
	var agg clientStats
	recordFinalSendStats(&row, &agg, fin)
	if row.FlightExpectation != hint || agg.FlightExpectation != hint {
		t.Fatal(row, agg)
	}
	b, err := json.Marshal(row)
	if err != nil {
		t.Fatal(err)
	}
	var decoded map[string]json.RawMessage
	if err := json.Unmarshal(b, &decoded); err != nil {
		t.Fatal(err)
	}
	var got flightExpectation
	if err := json.Unmarshal(decoded["flight_expectation"], &got); err != nil || got != hint {
		t.Fatal(string(b), err)
	}
}
