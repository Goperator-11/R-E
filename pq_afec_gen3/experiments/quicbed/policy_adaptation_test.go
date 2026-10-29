package main

import (
	"strings"
	"testing"
)

func adaptationCache(symbols bool) *destCache {
	s := &destStat{K: 2, ServerFlight: 10472, MinHCT: 50,
		ProbeMinHCT: 100, ObsCount: 100, LossCount: 10,
		Conns: 200, SinceProbe: 100000}
	if symbols {
		s.SymObs, s.SymLoss = 100, 10
	}
	return &destCache{M: map[string]*destStat{"test": s}}
}

func TestDisabledProbesStayDisabled(t *testing.T) {
	for _, symbols := range []bool{false, true} {
		c := adaptationCache(symbols)
		probeEvery := 0
		if symbols {
			probeEvery = 20 // Valid symbol feedback itself disables probes.
		}
		_, m, why, _ := c.decide("test", 1280, 3, 0, probeEvery,
			defaultAssumedBurst, cPktDefault, maxStepsDefault, quicgoMaxIPS, 2)
		if strings.HasPrefix(why, "탐색 ") || m == 0 {
			t.Fatalf("symbols=%v: disabled probing returned m=%d, %s", symbols, m, why)
		}
		if c.M["test"].SinceProbe != 100000 {
			t.Fatal("disabled probing advanced the probe counter")
		}
	}
}

func TestEnabledProbesStillRun(t *testing.T) {
	c := adaptationCache(false)
	_, m, why, unbiased := c.decide("test", 1280, 3, 0, 20,
		defaultAssumedBurst, cPktDefault, maxStepsDefault, quicgoMaxIPS, 2)
	if m != 0 || !unbiased || !strings.HasPrefix(why, "탐색 ") || c.M["test"].SinceProbe != 0 {
		t.Fatalf("enabled probe not emitted: m=%d unbiased=%v why=%s", m, unbiased, why)
	}
}

func TestSymbolFeedbackExitsProtectedColdStart(t *testing.T) {
	c := &destCache{M: map[string]*destStat{}}
	c.observe("test", 2, 10472, 50, false, false)
	c.observeSymbols("test", 3, 0, 50)
	if c.M["test"].ObsCount != 0 {
		t.Fatal("protected trial must not create unbiased connection observations")
	}
	_, _, why, _ := c.decide("test", 1280, 3, 1, 20,
		defaultAssumedBurst, cPktDefault, maxStepsDefault, quicgoMaxIPS, 2)
	if strings.HasPrefix(why, "콜드스타트") {
		t.Fatal("valid symbol feedback did not exit cold start")
	}
}
