package main

type flightExpectation struct {
	K      int    `json:"k"`
	Source string `json:"source"`
	Scope  string `json:"scope"`
}

func chooseFlightExpectation(k int, explicit bool, mode string, plan auto3Plan) flightExpectation {
	if explicit {
		if k == 0 {
			return flightExpectation{Source: "explicit_timer", Scope: "timer_only"}
		}
		return flightExpectation{K: k, Source: "explicit", Scope: "all_flights"}
	}
	if mode == "auto3" && plan.Decision.HasEJ && plan.Decision.K >= 1 && plan.Decision.K <= p3KMax {
		return flightExpectation{K: plan.Decision.K, Source: "cached_k", Scope: "first_flight"}
	}
	return flightExpectation{Source: "timer_only", Scope: "timer_only"}
}

func (c *fecConn) expectedKLocked() int {
	if c.expectation.Scope == "first_flight" && (c.flightID != 1 || c.stats.Flights != 0) {
		return 0
	}
	return c.expectK
}

func (c *fecConn) expectationReadyLocked() bool {
	k := c.expectedKLocked()
	return k > 0 && len(c.flight) >= k
}
