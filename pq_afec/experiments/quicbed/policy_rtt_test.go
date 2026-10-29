package main

import (
	"fmt"
	"math"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/quic-go/quic-go"
)

func cacheWithTransportRTT(t *testing.T, hct float64) *destCache {
	t.Helper()
	path := filepath.Join(t.TempDir(), "cache.json")
	data := fmt.Sprintf(`{"test":{"k":2,"server_flight":17762,"min_hct_ms":%g,"min_rtt_ms":50,"rtt_observations":1,"probe_min_hct_ms":120,"loss_count":4,"obs_count":100,"conns":100,"since_probe":0}}`, hct)
	if err := os.WriteFile(path, []byte(data), 0600); err != nil {
		t.Fatal(err)
	}
	return newDestCache(path)
}

func TestPolicyDoesNotUseHandshakeDurationAsPathRTT(t *testing.T) {
	fast := cacheWithTransportRTT(t, 50)
	slow := cacheWithTransportRTT(t, 120)
	ipsA, mA, whyA, _ := fast.decide("test", 1280, 3, 0, 0,
		defaultAssumedBurst, cPktDefault, maxStepsDefault, quicgoMaxIPS, 2)
	ipsB, mB, whyB, _ := slow.decide("test", 1280, 3, 0, 0,
		defaultAssumedBurst, cPktDefault, maxStepsDefault, quicgoMaxIPS, 2)
	if ipsA != ipsB || mA != mB || whyA != whyB {
		t.Fatalf("same measured 50ms path RTT changed with HCT: ips/m/why %d/%d/%s vs %d/%d/%s", ipsA, mA, whyA, ipsB, mB, whyB)
	}
}

func TestTransportRTTDefaultIsNotAnObservation(t *testing.T) {
	stats := quic.ConnectionStats{MinRTT: 100 * time.Millisecond,
		LatestRTT: 100 * time.Millisecond, SmoothedRTT: 100 * time.Millisecond}
	if rtt, ok := measuredPathRTT(stats); ok || rtt != 0 {
		t.Fatalf("counted initial 100ms default as observed: %v %v", rtt, ok)
	}
	stats.MeanDeviation = 50 * time.Millisecond
	if rtt, ok := measuredPathRTT(stats); !ok || rtt != 100 {
		t.Fatalf("rejected a real 100ms observation: %v %v", rtt, ok)
	}
}

func TestTransportRTTUsesValidACKMinimum(t *testing.T) {
	stats := quic.ConnectionStats{MinRTT: 50 * time.Millisecond,
		LatestRTT: 60 * time.Millisecond, SmoothedRTT: 55 * time.Millisecond,
		MeanDeviation: 25 * time.Millisecond}
	if rtt, ok := measuredPathRTT(stats); !ok || rtt != 50 {
		t.Fatalf("expected observed ACK minimum 50ms: %v %v", rtt, ok)
	}
	for _, bad := range []quic.ConnectionStats{
		{MinRTT: 0, LatestRTT: time.Millisecond, MeanDeviation: time.Millisecond},
		{MinRTT: time.Millisecond, LatestRTT: 0, MeanDeviation: time.Millisecond},
		{MinRTT: time.Millisecond, LatestRTT: time.Millisecond, MeanDeviation: 0},
	} {
		if _, ok := measuredPathRTT(bad); ok {
			t.Fatal("accepted unconfirmed transport RTT")
		}
	}
}

func TestLegacyHCTProxyMigratesOnlyOnValidRTT(t *testing.T) {
	path := filepath.Join(t.TempDir(), "cache.json")
	c := &destCache{path: path, M: map[string]*destStat{}}
	c.observe("test", 2, 17762, 120, false, true)
	if rtt, source := policyRTT(*c.M["test"]); rtt != 120 || source != "hct_proxy_no_ack_rtt" {
		t.Fatalf("legacy fallback was relabeled: %g %s", rtt, source)
	}
	for _, bad := range []float64{0, -1, math.NaN(), math.Inf(1)} {
		c.observeRTT("test", bad)
	}
	if c.M["test"].RTTObservations != 0 {
		t.Fatal("invalid RTT modified observation count")
	}
	c.observeRTT("test", 50)
	c.observeRTT("test", 60)
	c.observe("test", 2, 17762, 130, false, false)
	if c.M["test"].MinHCT != 120 {
		t.Fatal("RTT observation changed the HCT loss baseline")
	}
	c.save()
	loaded := newDestCache(path)
	if rtt, source := policyRTT(*loaded.M["test"]); rtt != 52.5 || source != "quic_ack_rtt_ewma" {
		t.Fatalf("observed RTT lost across cache save/load: %g %s", rtt, source)
	}
	if loaded.M["test"].RTTObservations != 2 {
		t.Fatal("RTT sample provenance did not survive reload")
	}
}

func TestPolicyRTTAdaptsAcrossConnections(t *testing.T) {
	c := &destCache{M: map[string]*destStat{}}
	c.observeRTT("test", 50)
	for i := 0; i < 8; i++ {
		c.observeRTT("test", 100)
	}
	st := c.M["test"]
	higher, source := policyRTT(*st)
	if higher < 90 || higher > 100 || source != "quic_ack_rtt_ewma" || st.MinRTT != 50 {
		t.Fatalf("policy kept historical minimum after path slowed: rtt=%g source=%s min=%g", higher, source, st.MinRTT)
	}
	for i := 0; i < 8; i++ {
		c.observeRTT("test", 25)
	}
	lower, source := policyRTT(*st)
	if lower < 25 || lower > 35 || source != "quic_ack_rtt_ewma" || st.MinRTT != 25 {
		t.Fatalf("policy did not adapt after path sped up: rtt=%g source=%s min=%g", lower, source, st.MinRTT)
	}
}

func TestLegacyACKMinimumStartsCurrentRTTEstimate(t *testing.T) {
	c := cacheWithTransportRTT(t, 120)
	if rtt, source := policyRTT(*c.M["test"]); rtt != 50 || source != "quic_ack_min_rtt" {
		t.Fatalf("legacy ACK provenance changed before a new observation: %g %s", rtt, source)
	}
	c.observeRTT("test", 100)
	if rtt, source := policyRTT(*c.M["test"]); rtt != 100 || source != "quic_ack_rtt_ewma" {
		t.Fatalf("new observed path retained stale legacy RTT: %g %s", rtt, source)
	}
}

func TestNullAndMalformedCacheRemainUsable(t *testing.T) {
	for _, data := range []string{"null", `{"test":{"k":2},"broken":`} {
		path := filepath.Join(t.TempDir(), "cache.json")
		if err := os.WriteFile(path, []byte(data), 0600); err != nil {
			t.Fatal(err)
		}
		c := newDestCache(path)
		if c.M == nil || len(c.M) != 0 {
			t.Fatalf("invalid cache was partially accepted: %v", c.M)
		}
		c.observeRTT("test", 50)
		c.observe("test", 2, 10472, 50, false, true)
		c.observeSymbols("test", 2, 0, 50)
		if c.M["test"].RTTObservations != 1 || c.M["test"].SymC1Conns != 1 {
			t.Fatal("discarded cache cannot record new observations")
		}
	}
}

func TestUnclassifiedFirstProbeDoesNotCountAsLossFree(t *testing.T) {
	c := &destCache{M: map[string]*destStat{}}
	c.observe("test", 2, 17762, 120, true, true)
	st := c.M["test"]
	if st.ObsCount != 0 || st.LossCount != 0 || st.ProbeMinHCT != 120 {
		t.Fatalf("unclassified first probe entered loss statistics: %+v", st)
	}
	c.observe("test", 2, 17762, 120, false, true)
	if st.ObsCount != 1 || st.LossCount != 0 {
		t.Fatalf("classified clean probe not counted once: %+v", st)
	}
	_, _, why, _ := c.decide("test", 1280, 3, 0, 0,
		defaultAssumedBurst, cPktDefault, maxStepsDefault, quicgoMaxIPS, 2)
	if strings.HasPrefix(why, "콜드스타트") {
		t.Fatal("baseline plus classified second probe must exit cold start")
	}
	c.observe("test", 2, 17762, 200, false, true)
	if math.Abs(st.ObsCount-1.99) > 1e-12 || st.LossCount != 1 {
		t.Fatalf("classified loss probe did not retain existing decay: %+v", st)
	}
}
