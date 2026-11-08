package main

import (
	"math"
	"math/bits"
	"path/filepath"
	"strings"
	"testing"
)

func adaptationCache(symbols bool) *destCache {
	s := &destStat{K: 2, ServerFlight: 10472, MinHCT: 50,
		ProbeMinHCT: 100, ObsCount: 100, LossCount: 10,
		Conns: 200, SinceProbe: 100000}
	if symbols {
		s.SymObs, s.SymLoss = 100, 10
		s.SymC1Conns, s.SymLastC1Conn = 1, s.Conns
	}
	return &destCache{M: map[string]*destStat{"test": s}}
}

func TestProtectedColdStartBootstrapsLossObservation(t *testing.T) {
	c := &destCache{M: map[string]*destStat{}}
	_, m, why, unbiased := c.decide("test", 1280, 3, 1, 20,
		defaultAssumedBurst, cPktDefault, maxStepsDefault, quicgoMaxIPS, 2)
	if m != 1 || unbiased || !strings.HasPrefix(why, "콜드스타트") {
		t.Fatalf("first protected cold trial changed: m=%d unbiased=%v why=%s", m, unbiased, why)
	}
	c.observe("test", 2, 10472, 50, false, false)
	for i := 0; i < 2; i++ {
		_, m, why, unbiased = c.decide("test", 1280, 3, 1, 20,
			defaultAssumedBurst, cPktDefault, maxStepsDefault, quicgoMaxIPS, 2)
		if m != 0 || !unbiased || !strings.HasPrefix(why, "초기 탐색") {
			t.Fatalf("protected cold start did not request observation %d: m=%d unbiased=%v why=%s", i, m, unbiased, why)
		}
		c.observe("test", 2, 10472, 100, false, unbiased)
	}
	if c.M["test"].ObsCount != 1 {
		t.Fatal("bootstrap must establish baseline before counting a classified probe")
	}
	_, _, why, _ = c.decide("test", 1280, 3, 1, 20,
		defaultAssumedBurst, cPktDefault, maxStepsDefault, quicgoMaxIPS, 2)
	if strings.HasPrefix(why, "콜드스타트") || strings.HasPrefix(why, "초기 탐색") {
		t.Fatalf("classified probe did not complete bootstrap: %s", why)
	}
}

func TestDisabledProbesKeepProtectedColdStart(t *testing.T) {
	c := &destCache{M: map[string]*destStat{}}
	for i := 0; i < 3; i++ {
		_, m, why, unbiased := c.decide("test", 1280, 3, 1, 0,
			defaultAssumedBurst, cPktDefault, maxStepsDefault, quicgoMaxIPS, 2)
		if m != 1 || unbiased || !strings.HasPrefix(why, "콜드스타트") {
			t.Fatalf("disabled probes emitted cold-start probe: m=%d unbiased=%v why=%s", m, unbiased, why)
		}
		c.observe("test", 2, 10472, 50, false, unbiased)
	}
}

func TestMissingFeedbackRestoresProbing(t *testing.T) {
	c := adaptationCache(true)
	st := c.M["test"]
	for i := 0; i < 19; i++ {
		c.observe("test", 2, 10472, 50, false, false)
	}
	_, _, why, _ := c.decide("test", 1280, 3, 0, 20,
		defaultAssumedBurst, cPktDefault, maxStepsDefault, quicgoMaxIPS, 2)
	if strings.HasPrefix(why, "탐색 ") {
		t.Fatalf("recent C1 observation did not suppress probing: %s", why)
	}
	c.observe("test", 2, 10472, 50, false, false)
	_, m, why, unbiased := c.decide("test", 1280, 3, 0, 20,
		defaultAssumedBurst, cPktDefault, maxStepsDefault, quicgoMaxIPS, 2)
	if m != 0 || !unbiased || !strings.HasPrefix(why, "탐색 ") {
		t.Fatalf("stale C1 cache suppressed probe: m=%d unbiased=%v why=%s", m, unbiased, why)
	}
	if st.SymC1Conns != 1 || st.SymLastC1Conn != 200 {
		t.Fatal("missing feedback was counted as a fresh C1 observation")
	}
}

func TestFreshSymbolFeedbackContinuesSuppressingProbes(t *testing.T) {
	c := adaptationCache(true)
	for i := 0; i < 50; i++ {
		c.observe("test", 2, 10472, 50, false, false)
		c.observeSymbols("test", 3, 0, 50)
		_, _, why, _ := c.decide("test", 1280, 3, 0, 20,
			defaultAssumedBurst, cPktDefault, maxStepsDefault, quicgoMaxIPS, 2)
		if strings.HasPrefix(why, "탐색 ") || strings.HasPrefix(why, "초기 탐색") {
			t.Fatalf("fresh feedback emitted unnecessary probe at connection %d: %s", i, why)
		}
	}
	if c.M["test"].SinceProbe != 100000 {
		t.Fatal("active symbol feedback advanced the probe counter")
	}
}

func TestFailedAttemptsExpireSymbolFeedback(t *testing.T) {
	c := adaptationCache(true)
	st := c.M["test"]
	for i := 1; i <= 20; i++ {
		_, _, why, _ := c.decide("test", 1280, 3, 0, 20,
			defaultAssumedBurst, cPktDefault, maxStepsDefault, quicgoMaxIPS, 2)
		if strings.HasPrefix(why, "탐색 ") {
			t.Fatalf("C1 expired before decision age limit at decision %d: %s", i, why)
		}
	}
	_, m, why, _ := c.decide("test", 1280, 3, 0, 20,
		defaultAssumedBurst, cPktDefault, maxStepsDefault, quicgoMaxIPS, 2)
	if m != 0 || !strings.HasPrefix(why, "탐색 ") || st.Conns != 200 {
		t.Fatalf("failed attempts retained C1 despite decision age: m=%d conns=%d why=%s", m, st.Conns, why)
	}
	c.observeSymbols("test", 3, 0, 50)
	st.SinceProbe = 100000
	_, _, why, _ = c.decide("test", 1280, 3, 0, 20,
		defaultAssumedBurst, cPktDefault, maxStepsDefault, quicgoMaxIPS, 2)
	if strings.HasPrefix(why, "탐색 ") || st.SymLastC1Decision != 21 {
		t.Fatalf("fresh C1 did not reset decision age: %s", why)
	}
	c = adaptationCache(true)
	for i := 0; i < 21; i++ {
		_, _, why, _ = c.decide("test", 1280, 3, 0, 0,
			defaultAssumedBurst, cPktDefault, maxStepsDefault, quicgoMaxIPS, 2)
		if strings.HasPrefix(why, "탐색 ") || c.M["test"].SinceProbe != 100000 {
			t.Fatalf("expired C1 reenabled explicitly disabled probing: %s", why)
		}
	}
}

func TestEveryConnectionFeedbackDisablesEveryConnectionProbes(t *testing.T) {
	c := adaptationCache(true)
	for i := 0; i < 5; i++ {
		_, _, why, _ := c.decide("test", 1280, 3, 0, 1,
			defaultAssumedBurst, cPktDefault, maxStepsDefault, quicgoMaxIPS, 2)
		if strings.HasPrefix(why, "탐색 ") {
			t.Fatalf("active C1 with period 1 emitted a costly probe: %s", why)
		}
		c.observe("test", 2, 10472, 50, false, false)
		c.observeSymbols("test", 3, 0, 50)
	}
}

func TestFeedbackFreshnessSurvivesCacheReload(t *testing.T) {
	c := adaptationCache(true)
	c.M["test"].PolicyDecisions = 35
	c.M["test"].SymLastC1Decision = 30
	c.path = filepath.Join(preservedTempDir(t), "cache.json")
	c.save()
	loaded := newDestCache(c.path)
	if !recentSymbolFeedback(*loaded.M["test"], 20) ||
		loaded.M["test"].PolicyDecisions != 35 || loaded.M["test"].SymLastC1Decision != 30 {
		t.Fatal("saved current C1 provenance was lost")
	}
	for i := 0; i < 20; i++ {
		loaded.observe("test", 2, 10472, 50, false, false)
	}
	loaded.save()
	loaded = newDestCache(c.path)
	if recentSymbolFeedback(*loaded.M["test"], 20) {
		t.Fatal("cache reload reset expired feedback to current")
	}
}

func TestC2DoesNotRefreshC1Feedback(t *testing.T) {
	c := adaptationCache(true)
	st := c.M["test"]
	st.Conns += 20
	c.observeSymbolsWhy("test", 3, 3, 200, true)
	if recentSymbolFeedback(*st, 20) || st.SymC1Conns != 1 || st.SymLastC1Conn != 200 {
		t.Fatal("inferred C2 loss was relabeled as a current server C1 observation")
	}
	c.observeSymbols("test", 3, 1, 50)
	if !recentSymbolFeedback(*st, 20) || st.SymC1Conns != 2 || st.SymLastC1Conn != st.Conns {
		t.Fatal("valid C1 observation did not refresh feedback provenance")
	}
}

func TestLegacySymbolsDoNotPermanentlyDisableProbing(t *testing.T) {
	c := adaptationCache(true)
	c.M["test"].SymC1Conns = 0
	_, m, why, _ := c.decide("test", 1280, 3, 0, 20,
		defaultAssumedBurst, cPktDefault, maxStepsDefault, quicgoMaxIPS, 2)
	if m != 0 || !strings.HasPrefix(why, "탐색 ") {
		t.Fatalf("legacy symbols without freshness blocked probing: m=%d why=%s", m, why)
	}
	c = adaptationCache(true)
	c.M["test"].SymC1Conns = 0
	_, _, why, _ = c.decide("test", 1280, 3, 0, 0,
		defaultAssumedBurst, cPktDefault, maxStepsDefault, quicgoMaxIPS, 2)
	if strings.HasPrefix(why, "탐색 ") || c.M["test"].SinceProbe != 100000 {
		t.Fatalf("legacy migration reenabled explicitly disabled probing: %s", why)
	}
}

func TestSymbolCountsAverageUnknownArrivalOrder(t *testing.T) {
	for n := 1; n <= 6; n++ {
		for lost := 0; lost <= n; lost++ {
			var totalLoss, totalObs float64
			orders := 0
			for mask := uint(0); mask < 1<<n; mask++ {
				if bits.OnesCount(mask) != lost {
					continue
				}
				loss, obs := 7.0, 50.0
				for i := 0; i < n; i++ {
					loss *= 0.99
					obs = obs*0.99 + 1
					if mask&(1<<i) != 0 {
						loss++
					}
				}
				totalLoss += loss
				totalObs += obs
				orders++
			}
			c := &destCache{M: map[string]*destStat{"test": {SymObs: 50, SymLoss: 7}}}
			c.observeSymbols("test", n, lost, 50)
			st := c.M["test"]
			if math.Abs(st.SymLoss-totalLoss/float64(orders)) > 1e-12 ||
				math.Abs(st.SymObs-totalObs/float64(orders)) > 1e-12 {
				t.Fatalf("n=%d lost=%d: count update (%g,%g) disagrees with order average (%g,%g)",
					n, lost, st.SymLoss, st.SymObs, totalLoss/float64(orders), totalObs/float64(orders))
			}
		}
	}
}

func TestSymbolBatchPreservesObservedLossFraction(t *testing.T) {
	c := &destCache{M: map[string]*destStat{}}
	c.observeSymbols("test", 5, 2, 50)
	st := c.M["test"]
	if math.Abs(st.SymLoss/st.SymObs-0.4) > 1e-12 {
		t.Fatalf("unknown symbol ordering distorted 2/5 loss fraction: %g", st.SymLoss/st.SymObs)
	}
}

func TestDisabledProbesStayDisabled(t *testing.T) {
	for _, symbols := range []bool{false, true} {
		c := adaptationCache(symbols)
		probeEvery := 0
		if symbols {
			probeEvery = 20
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
