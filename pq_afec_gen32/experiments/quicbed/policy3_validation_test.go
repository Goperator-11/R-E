package main

import (
	"bytes"
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

func p3ValidationState() *p3State {
	a := p3Action{0, 1, 2}
	st := p3PointState(2, 1280, 9000, p3GIndex(0.02))
	st.HCT[a.Key()] = p3Rep(100, p3BaseMin)
	st.HCTSeq[a.Key()] = 0
	st.Seq = 1
	st.NDec = p3GuardRefresh
	st.GResid[a.Key()] = p3Rep(40, p3GuardMin)
	st.GCommon = p3Rep(2, p3GuardCommonWin)
	st.GAlarm[a.Key()] = 0
	return st
}

func p3StateBytes(t *testing.T, st *p3State) []byte {
	t.Helper()
	raw, err := json.Marshal(st)
	if err != nil {
		t.Fatal(err)
	}
	return raw
}

func TestP3InvalidObservationInputsLeaveStateUntouched(t *testing.T) {
	type input struct {
		w                 int
		u, rtt, cPkt, srv float64
		hct               float64
		jp                *float64
	}
	for _, tc := range []struct {
		name   string
		change func(*input)
	}{
		{"small_W", func(x *input) { x.w = 1199 }},
		{"negative_u", func(x *input) { x.u = -1 }},
		{"nan_u", func(x *input) { x.u = math.NaN() }},
		{"infinite_u", func(x *input) { x.u = math.Inf(1) }},
		{"negative_rtt", func(x *input) { x.rtt = -1 }},
		{"nan_rtt", func(x *input) { x.rtt = math.NaN() }},
		{"infinite_rtt", func(x *input) { x.rtt = math.Inf(1) }},
		{"negative_c_pkt", func(x *input) { x.cPkt = -1 }},
		{"c_pkt_at_packet_size", func(x *input) { x.cPkt = 1280 }},
		{"nan_c_pkt", func(x *input) { x.cPkt = math.NaN() }},
		{"infinite_c_pkt", func(x *input) { x.cPkt = math.Inf(1) }},
		{"negative_srv", func(x *input) { x.srv = -1 }},
		{"nan_srv", func(x *input) { x.srv = math.NaN() }},
		{"infinite_srv", func(x *input) { x.srv = math.Inf(1) }},
		{"zero_hct", func(x *input) { x.hct = 0 }},
		{"negative_hct", func(x *input) { x.hct = -1 }},
		{"nan_hct", func(x *input) { x.hct = math.NaN() }},
		{"infinite_hct", func(x *input) { x.hct = math.Inf(1) }},
		{"nan_prediction", func(x *input) { v := math.NaN(); x.jp = &v }},
		{"infinite_prediction", func(x *input) { v := math.Inf(1); x.jp = &v }},
	} {
		t.Run(tc.name, func(t *testing.T) {
			st := p3ValidationState()
			before := p3StateBytes(t, st)
			jp := 100.0
			x := input{1280, 2, 50, cPktDefault, 18000, 140, &jp}
			tc.change(&x)
			if _, err := p3Observe(st, p3Action{0, 1, 2}, x.hct, true, 2, x.srv,
				x.rtt, x.w, x.u, x.cPkt, x.jp); err == nil {
				t.Fatal("invalid observation accepted")
			}
			if !bytes.Equal(before, p3StateBytes(t, st)) {
				t.Fatal("rejected observation changed the state")
			}
		})
	}
}

func TestP3InvalidDecisionInputsDoNotReleaseAlarmsOrCount(t *testing.T) {
	for _, tc := range []struct {
		name         string
		w            int
		u, rtt, cPkt float64
	}{
		{"small_W", 1199, 2, 50, cPktDefault},
		{"negative_u", 1280, -1, 50, cPktDefault},
		{"nan_u", 1280, math.NaN(), 50, cPktDefault},
		{"infinite_u", 1280, math.Inf(1), 50, cPktDefault},
		{"negative_rtt", 1280, 2, -1, cPktDefault},
		{"nan_rtt", 1280, 2, math.NaN(), cPktDefault},
		{"infinite_rtt", 1280, 2, math.Inf(1), cPktDefault},
		{"negative_c_pkt", 1280, 2, 50, -1},
		{"c_pkt_at_packet_size", 1280, 2, 50, 1280},
		{"nan_c_pkt", 1280, 2, 50, math.NaN()},
		{"infinite_c_pkt", 1280, 2, 50, math.Inf(1)},
	} {
		t.Run(tc.name, func(t *testing.T) {
			st := p3ValidationState()
			before := p3StateBytes(t, st)
			if _, err := p3Decide(st, tc.w, tc.u, tc.rtt, tc.cPkt, false); err == nil {
				t.Fatal("invalid decision accepted")
			}
			if !bytes.Equal(before, p3StateBytes(t, st)) {
				t.Fatal("rejected decision released an alarm or changed counters")
			}
		})
	}
}

func TestP3CoreRejectsInvalidDistributionAndPhysicalInputs(t *testing.T) {
	type input struct {
		post            []float64
		k, w            int
		s, u, rtt, cPkt float64
	}
	for _, tc := range []struct {
		name   string
		change func(*input)
	}{
		{"short_posterior", func(x *input) { x.post = x.post[:p3NG-1] }},
		{"zero_mass", func(x *input) { x.post[0] = 0 }},
		{"negative_probability", func(x *input) { x.post[0], x.post[1] = 1.01, -0.01 }},
		{"nan_probability", func(x *input) { x.post[0] = math.NaN() }},
		{"infinite_probability", func(x *input) { x.post[0] = math.Inf(1) }},
		{"mass_too_low", func(x *input) { x.post[0] = 1 - 1e-8 }},
		{"mass_too_high", func(x *input) { x.post[0] = 1 + 1e-8 }},
		{"zero_k", func(x *input) { x.k = 0 }},
		{"large_k", func(x *input) { x.k = p3KMax + 1 }},
		{"small_W", func(x *input) { x.w = 1199 }},
		{"zero_S", func(x *input) { x.s = 0 }},
		{"negative_S", func(x *input) { x.s = -1 }},
		{"nan_S", func(x *input) { x.s = math.NaN() }},
		{"infinite_S", func(x *input) { x.s = math.Inf(1) }},
		{"negative_u", func(x *input) { x.u = -1 }},
		{"nan_u", func(x *input) { x.u = math.NaN() }},
		{"infinite_u", func(x *input) { x.u = math.Inf(1) }},
		{"missing_rtt", func(x *input) { x.rtt = 0 }},
		{"negative_rtt", func(x *input) { x.rtt = -1 }},
		{"nan_rtt", func(x *input) { x.rtt = math.NaN() }},
		{"infinite_rtt", func(x *input) { x.rtt = math.Inf(1) }},
		{"negative_c_pkt", func(x *input) { x.cPkt = -1 }},
		{"c_pkt_at_packet_size", func(x *input) { x.cPkt = 1280 }},
		{"nan_c_pkt", func(x *input) { x.cPkt = math.NaN() }},
		{"infinite_c_pkt", func(x *input) { x.cPkt = math.Inf(1) }},
	} {
		t.Run(tc.name, func(t *testing.T) {
			x := input{make([]float64, p3NG), 2, 1280, p3SynthS(9000, 2, 1280), 2, 50, cPktDefault}
			x.post[0] = 1
			tc.change(&x)
			before := append([]float64(nil), x.post...)
			if _, err := p3DecideCore(x.post, x.k, x.w, x.s, x.u, x.rtt, x.cPkt, false, nil, false); err == nil {
				t.Fatal("invalid core decision accepted")
			}
			for i, v := range before {
				if math.Float64bits(x.post[i]) != math.Float64bits(v) {
					t.Fatal("core validation changed the caller's posterior")
				}
			}
		})
	}
}

func TestP3StateRejectsInvalidMassWindowsSequencesAndStats(t *testing.T) {
	for _, tc := range []struct {
		name   string
		change func(*p3State)
	}{
		{"zero_posterior_mass", func(st *p3State) { st.Post[0] = make([]float64, p3NG) }},
		{"large_posterior_mass", func(st *p3State) { st.Post[0][0] += 1e-8 }},
		{"nan_posterior", func(st *p3State) { st.Post[0][0] = math.NaN() }},
		{"negative_posterior", func(st *p3State) { st.Post[0][0] = -1 }},
		{"zero_weight_mass", func(st *p3State) { st.W = make([]float64, p3NH) }},
		{"large_weight_mass", func(st *p3State) { st.W[0] += 1e-8 }},
		{"nan_weight", func(st *p3State) { st.W[0] = math.NaN() }},
		{"negative_weight", func(st *p3State) { st.W[0] = -1 }},
		{"zero_k_history", func(st *p3State) { st.KHist = []int{0} }},
		{"negative_k_history", func(st *p3State) { st.KHist = []int{-1} }},
		{"zero_S_history", func(st *p3State) { st.SHist = []float64{0} }},
		{"negative_S_history", func(st *p3State) { st.SHist = []float64{-1} }},
		{"nan_S_history", func(st *p3State) { st.SHist = []float64{math.NaN()} }},
		{"infinite_S_history", func(st *p3State) { st.SHist = []float64{math.Inf(1)} }},
		{"zero_hct_history", func(st *p3State) { st.HCT["0,1,2"] = []float64{0} }},
		{"negative_hct_history", func(st *p3State) { st.HCT["0,1,2"] = []float64{-1} }},
		{"nan_hct_history", func(st *p3State) { st.HCT["0,1,2"] = []float64{math.NaN()} }},
		{"infinite_hct_history", func(st *p3State) { st.HCT["0,1,2"] = []float64{math.Inf(1)} }},
		{"negative_sequence", func(st *p3State) { st.Seq = -1 }},
		{"negative_hct_sequence", func(st *p3State) { st.HCTSeq["0,1,2"] = -1 }},
	} {
		t.Run(tc.name, func(t *testing.T) {
			st := p3ValidationState()
			tc.change(st)
			if err := st.validate(); err == nil {
				t.Fatal("invalid state accepted")
			}
		})
	}
	for i := 0; i < reflect.TypeOf(p3Stats{}).NumField(); i++ {
		name := reflect.TypeOf(p3Stats{}).Field(i).Name
		t.Run("negative_stats_"+name, func(t *testing.T) {
			st := p3ValidationState()
			reflect.ValueOf(&st.Stats).Elem().Field(i).SetInt(-1)
			if err := st.validate(); err == nil {
				t.Fatalf("negative stats field %s accepted", name)
			}
		})
	}
}

func TestP3InvalidStateCannotMutateThroughObservationOrDecision(t *testing.T) {
	for _, operation := range []string{"observe", "decide"} {
		t.Run(operation, func(t *testing.T) {
			st := p3ValidationState()
			st.Post[0] = make([]float64, p3NG)
			before := p3StateBytes(t, st)
			var err error
			if operation == "observe" {
				_, err = p3Observe(st, p3Action{0, 1, 2}, 140, true, 2, 18000, 50, 1280, 2, cPktDefault, nil)
			} else {
				_, err = p3Decide(st, 1280, 2, 50, cPktDefault, false)
			}
			if err == nil || !bytes.Equal(before, p3StateBytes(t, st)) {
				t.Fatalf("invalid state mutated or was accepted: %v", err)
			}
		})
	}
}

func TestP3ContextRejectsInputsBeforeBinNeeded(t *testing.T) {
	st := p3ValidationState()
	for _, cPkt := range []float64{-1, 1280, math.NaN(), math.Inf(1)} {
		if c, ok := p3Context(st, 1280, 2, 50, cPkt); ok || c != nil {
			t.Fatalf("context accepted c_pkt %v", cPkt)
		}
	}
	for _, s := range []float64{0, -1, math.NaN(), math.Inf(1)} {
		st.SHist = []float64{s}
		if c, ok := p3Context(st, 1280, 2, 50, cPktDefault); ok || c != nil {
			t.Fatalf("context accepted S %v", s)
		}
	}
}

func TestP3ValidStateRoundTripAndMissingInputsRemainSupported(t *testing.T) {
	st := p3ValidationState()
	st.KHist = []int{p3KMax + 1}
	if err := st.validate(); err != nil {
		t.Fatalf("positive out-of-range k must retain the fallback: %v", err)
	}
	raw := p3StateBytes(t, st)
	var restored p3State
	if err := json.Unmarshal(raw, &restored); err != nil {
		t.Fatal(err)
	}
	if err := restored.validate(); err != nil || !bytes.Equal(raw, p3StateBytes(t, &restored)) {
		t.Fatalf("valid state round trip %v", err)
	}
	if d, err := p3Decide(&restored, 1280, 0, 50, 0, false); err != nil || d.Why != "k_range" {
		t.Fatalf("k_range fallback %+v %v", d, err)
	}
	st = newP3State()
	if d, err := p3Decide(st, 1200, 0, 0, 0, false); err != nil || d.Why != "cold" {
		t.Fatalf("missing RTT during cold start %+v %v", d, err)
	}
	if info, err := p3Observe(st, p3Action{}, 100, true, 2, 0, 0, 1200, 0, 0, nil); err != nil || info.Updated || len(st.SHist) != 0 {
		t.Fatalf("missing server bytes and RTT %+v %v", info, err)
	}
	st.SHist = []float64{18000}
	if d, err := p3Decide(st, 1200, 0, 0, 0, false); err != nil || d.Why != "no_rtt" {
		t.Fatalf("missing RTT fallback %+v %v", d, err)
	}
	post := make([]float64, p3NG)
	post[0] = 1 + 5e-10
	if _, err := p3DecideCore(post, 2, 1280, 18000, 0, 50, 0, false, nil, false); err != nil {
		t.Fatalf("mass within tolerance rejected: %v", err)
	}
}

func TestP3SafeBinCalculationMatchesNormalCasesAndHasAnExactByteBoundary(t *testing.T) {
	for k := 1; k <= p3KMax; k++ {
		for _, w := range []int{1200, 1280, 1350, 1452} {
			for _, cPkt := range []float64{0, 41.983, 1279} {
				for _, srv := range []float64{1, 1280, 18000, 32000} {
					base := binIndex(k * w)
					got, err := p3BinNeededChecked(srv, base, cPkt)
					if err != nil || got != binNeeded(srv, base, cPkt) {
						t.Fatalf("k%d W%d S%v c_pkt%v: %d %v", k, w, srv, cPkt, got, err)
					}
				}
			}
		}
	}
	s := float64(p3NNeedMax * serverPacketSize)
	if n, err := p3BinNeededChecked(s, 0, 0); err != nil || n != p3NNeedMax {
		t.Fatalf("exact byte boundary %d %v", n, err)
	}
	if _, err := p3BinNeededChecked(s+serverPacketSize, 0, 0); err == nil {
		t.Fatal("bin product above exact integer byte range accepted")
	}
	if n, err := p3BinNeededChecked(math.Nextafter(1280, math.Inf(1)), 0, 0); err != nil || n != 2 {
		t.Fatalf("single-step correction %d %v", n, err)
	}
}

func TestP3FiniteExtremesAreRejectedBeforeStateChanges(t *testing.T) {
	for _, tc := range []struct {
		name            string
		w               int
		s, u, rtt, cPkt float64
	}{
		{"huge_server_bytes", 1280, 1e308, 2, 50, cPktDefault},
		{"near_singular_c_pkt", 1280, 18000, 2, 50, math.Nextafter(1280, 0)},
		{"huge_rtt", 1280, 18000, 2, 1e308, cPktDefault},
		{"huge_bandwidth", 1280, 18000, 1e308, 50, cPktDefault},
		{"tiny_bandwidth", 1280, 18000, math.SmallestNonzeroFloat64, 50, cPktDefault},
		{"huge_W", int(^uint(0) >> 1), 18000, 2, 50, cPktDefault},
	} {
		t.Run(tc.name, func(t *testing.T) {
			post := make([]float64, p3NG)
			post[0] = 1
			if _, err := p3DecideCore(post, 2, tc.w, tc.s, tc.u, tc.rtt, tc.cPkt, false, nil, false); err == nil {
				t.Fatal("unrepresentable core input accepted")
			}
			st := p3ValidationState()
			before := p3StateBytes(t, st)
			if _, err := p3Observe(st, p3Action{0, 1, 2}, 140, true, 2, tc.s,
				tc.rtt, tc.w, tc.u, tc.cPkt, nil); err == nil {
				t.Fatal("unrepresentable observation accepted")
			}
			if !bytes.Equal(before, p3StateBytes(t, st)) {
				t.Fatal("unrepresentable observation changed the state")
			}
			st.SHist = []float64{tc.s}
			before = p3StateBytes(t, st)
			if _, err := p3Decide(st, tc.w, tc.u, tc.rtt, tc.cPkt, false); err == nil {
				t.Fatal("unrepresentable decision accepted")
			}
			if !bytes.Equal(before, p3StateBytes(t, st)) {
				t.Fatal("unrepresentable decision released an alarm or changed counters")
			}
		})
	}
}

func TestP3FailedCoreCalculationDoesNotCommitTheDecision(t *testing.T) {
	st := p3ValidationState()
	before := p3StateBytes(t, st)
	if _, err := p3Decide(st, quicgoMaxIPS+1, 2, 50, cPktDefault, false); err == nil {
		t.Fatal("decision without a transport-valid candidate accepted")
	}
	if !bytes.Equal(before, p3StateBytes(t, st)) {
		t.Fatal("failed core calculation committed counters or alarm refresh")
	}
}

func TestP3MedianAndResidualDoNotOverflowOnFiniteValues(t *testing.T) {
	if got := p3Median([]float64{1e308, 1e308}); got != 1e308 {
		t.Fatalf("positive median %v", got)
	}
	if got := p3Median([]float64{-1e308, -1e308}); got != -1e308 {
		t.Fatalf("negative median %v", got)
	}
	st := p3ValidationState()
	before := p3StateBytes(t, st)
	jp := -1e308
	if _, err := p3Observe(st, p3Action{0, 1, 2}, 1e308, true, 2, 18000, 50, 1280, 2, cPktDefault, &jp); err == nil {
		t.Fatal("overflowing residual accepted")
	}
	if !bytes.Equal(before, p3StateBytes(t, st)) {
		t.Fatal("overflowing residual changed the state")
	}
}

func TestP3ActionValidationRejectsIntegerOverflowAndUnrepresentableDelta(t *testing.T) {
	maxInt := int(^uint(0) >> 1)
	for _, a := range []p3Action{
		{p3MaxExactInt + 1, 0, 0},
		{0, maxInt, maxInt},
		{0, maxInt, 0},
		{0, 0, maxInt},
		{0, p3MMax, p3MMax},
	} {
		t.Run(a.Key(), func(t *testing.T) {
			if a.valid() {
				t.Fatalf("invalid action accepted: %+v", a)
			}
			if _, err := parseP3Key(a.Key()); err == nil {
				t.Fatal("invalid action key accepted")
			}
			st := p3ValidationState()
			before := p3StateBytes(t, st)
			if _, err := p3Observe(st, a, 140, true, 2, 18000, 50, 1280, 2, cPktDefault, nil); err == nil {
				t.Fatal("invalid action observation accepted")
			}
			if !bytes.Equal(before, p3StateBytes(t, st)) {
				t.Fatal("invalid action observation changed the state")
			}
			badState := newP3State()
			badState.HCT[a.Key()] = []float64{100}
			badState.HCTSeq[a.Key()] = 0
			cache := struct {
				Schema string                  `json:"schema"`
				Dests  map[string]*cache3Entry `json:"dests"`
			}{p3CacheSchema, map[string]*cache3Entry{"x": {State: badState}}}
			raw, err := json.Marshal(cache)
			if err != nil {
				t.Fatal(err)
			}
			path := filepath.Join(t.TempDir(), "cache3.json")
			if err := os.WriteFile(path, raw, 0600); err != nil {
				t.Fatal(err)
			}
			if _, err := loadDestCache3(path); err == nil {
				t.Fatal("cache containing an invalid action key accepted")
			}
		})
	}
	for _, a := range []p3Action{{p3MaxExactInt, 0, 0}, {0, p3MMax, 0}, {0, 0, p3MMax}} {
		if !a.valid() {
			t.Fatalf("action field boundary rejected: %+v", a)
		}
	}
}

func TestP3ObservedActionChecksItsEffectivePacketSizeBeforeMutation(t *testing.T) {
	st := p3ValidationState()
	before := p3StateBytes(t, st)
	a := p3Action{p3MaxExactInt, 0, 0}
	if _, err := p3Observe(st, a, 140, true, 2, 18000, 50, 1280, 2, cPktDefault, nil); err == nil {
		t.Fatal("unrepresentable effective packet size accepted")
	}
	if !bytes.Equal(before, p3StateBytes(t, st)) {
		t.Fatal("unrepresentable effective packet size changed the state")
	}
}
