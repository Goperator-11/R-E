package main

import (
	"math"
	"reflect"
	"testing"
)

func TestP3V331VersionsSeparateOldCaches(t *testing.T) {
	if p3PolicyVersion != "v3.3.1-dev" || p3StateVersion != 11 || p3CacheSchema != "padfec3.cache3/11" {
		t.Fatalf("versions %s %d %s", p3PolicyVersion, p3StateVersion, p3CacheSchema)
	}
	for _, v := range []int{2, 3, 4} {
		st := newP3State()
		st.V = v
		if err := st.validate(); err == nil {
			t.Fatalf("state version %d accepted by v3.3.1-dev", v)
		}
	}
}

func TestP3SkippedObservationsAdvanceEachHazardOnce(t *testing.T) {
	a := p3Action{0, 1, 2}
	withContext := func(cert int, arm p3Action, base float64) *p3State {
		st := p3PointState(2, 1280, cert, p3GIndex(0.02))
		st.HCT[arm.Key()] = p3Rep(base, p3BaseMin)
		st.HCTSeq[arm.Key()] = 0
		return st
	}
	for _, tc := range []struct {
		name   string
		state  func() *p3State
		arm    p3Action
		hct    float64
		ok     bool
		rtt    float64
		u      float64
		skip   string
		noBase int
		noCtx  int
	}{
		{"no_base", newP3State, a, 100, true, 50, 2, "", 1, 0},
		{"no_context", func() *p3State {
			st := newP3State()
			st.HCT[a.Key()] = p3Rep(100, p3BaseMin)
			st.HCTSeq[a.Key()] = 0
			return st
		}, a, 110, true, 50, 2, "", 0, 1},
		{"no_rtt", func() *p3State { return withContext(9000, a, 100) }, a, 110, true, 0, 2, "", 1, 0},
		{"shield", func() *p3State { return withContext(30000, p3Action{0, 0, 4}, 410) },
			p3Action{0, 0, 4}, 700, true, 200, 5, p3SkipShield, 0, 0},
		{"nominal_two", func() *p3State { return withContext(16000, p3Action{0, 0, 4}, 120) },
			p3Action{0, 0, 4}, 125, true, 50, 2, p3SkipNominal2, 0, 0},
		{"guard", func() *p3State {
			st := withContext(9000, a, 100)
			st.GAlarm[a.Key()] = 0
			return st
		}, a, 110, true, 50, 2, p3SkipGuard, 0, 0},
		{"failure_without_base", newP3State, a, math.NaN(), false, 50, 2, "", 1, 0},
	} {
		t.Run(tc.name, func(t *testing.T) {
			st := tc.state()
			g := p3GIndex(0.02)
			p3SetPoint(st, g)
			weights := []float64{0.4, 0.25, 0.15, 0.1, 0.1}
			st.W = append([]float64(nil), weights...)
			info, err := p3Observe(st, tc.arm, tc.hct, tc.ok, 2, 18000, tc.rtt, 1280, tc.u, cPktDefault, nil)
			if err != nil || info.Updated || info.Skip != tc.skip {
				t.Fatalf("observation %+v %v", info, err)
			}
			for j, row := range st.Post {
				for i, got := range row {
					want := p3H[j] / float64(p3NG)
					if i == g {
						want += 1 - p3H[j]
					}
					if !p3Close(got, want, 1e-14) {
						t.Fatalf("hazard %d grid %d: got %.17g, one transition %.17g", j, i, got, want)
					}
				}
			}
			if !reflect.DeepEqual(st.W, weights) || st.Stats.Obs != 1 || st.Stats.Predict != 1 ||
				st.Stats.Upd != 0 || st.Stats.NoBase != tc.noBase || st.Stats.NoCtx != tc.noCtx {
				t.Fatalf("skipped evidence changed weights or counters: %v %+v", st.W, st.Stats)
			}
		})
	}
}

func TestP3SkippedRunForgetsAtTheHazardRate(t *testing.T) {
	st := newP3State()
	g := p3GIndex(0.3)
	p3SetPoint(st, g)
	weights := append([]float64(nil), st.W...)
	const steps = 64
	for i := 0; i < steps; i++ {
		info, err := p3Observe(st, p3Action{}, math.NaN(), false, 0, 0, 50, 1280, 2, cPktDefault, nil)
		if err != nil || info.Updated {
			t.Fatalf("step %d: %+v %v", i, info, err)
		}
	}
	for j, row := range st.Post {
		retained := math.Pow(1-p3H[j], steps)
		for i, got := range row {
			want := (1 - retained) / float64(p3NG)
			if i == g {
				want += retained
			}
			if !p3Close(got, want, 1e-13) {
				t.Fatalf("hazard %d grid %d: got %.17g, elapsed-time prior %.17g", j, i, got, want)
			}
		}
	}
	if !reflect.DeepEqual(st.W, weights) || st.Stats.Predict != steps || st.Stats.Obs != steps ||
		st.Stats.Fail != steps || st.Stats.Upd != 0 {
		t.Fatalf("skipped run weights or counters: %v %+v", st.W, st.Stats)
	}
}

func TestP3ObservedEvidenceUsesOnlyOneTransition(t *testing.T) {
	a := p3Action{0, 2, 2}
	st := p3PointState(2, 1280, 9000, p3GIndex(0.3))
	st.W = []float64{0.2, 0.2, 0.2, 0.2, 0.2}
	st.HCT[a.Key()] = p3Rep(100, p3BaseMin)
	st.HCTSeq[a.Key()] = 0
	c, ok := p3Context(st, 1280, 2, 50, cPktDefault)
	if !ok || c.skipReason(a) != "" {
		t.Fatal("evidence test arm must be observable")
	}
	l := p3Likelihood(c, a, 0)
	wantPost := make([][]float64, p3NH)
	wantW := make([]float64, p3NH)
	evidence := 0.0
	for j, h := range p3H {
		wantPost[j] = make([]float64, p3NG)
		z := 0.0
		for i, likelihood := range l {
			prior := h / float64(p3NG)
			if i == p3GIndex(0.3) {
				prior += 1 - h
			}
			wantPost[j][i] = prior * likelihood
			z += wantPost[j][i]
		}
		for i := range wantPost[j] {
			wantPost[j][i] /= z
		}
		wantW[j] = 0.2 * z
		evidence += wantW[j]
	}
	for j := range wantW {
		wantW[j] /= evidence
		if wantW[j] < p3WFloor {
			t.Fatal("test fixture unexpectedly reaches the weight floor")
		}
	}
	info, err := p3Observe(st, a, 110, true, 2, c.S, 50, 1280, 2, cPktDefault, nil)
	if err != nil || !info.Updated || info.Y != 0 || st.Stats.Obs != 1 || st.Stats.Predict != 1 || st.Stats.Upd != 1 {
		t.Fatalf("normal observation %+v %v %+v", info, err, st.Stats)
	}
	for j, row := range st.Post {
		for i, got := range row {
			if !p3Close(got, wantPost[j][i], 1e-13) {
				t.Fatalf("hazard %d grid %d: got %.17g, one transition plus evidence %.17g", j, i, got, wantPost[j][i])
			}
		}
		if !p3Close(st.W[j], wantW[j], 1e-13) {
			t.Fatalf("hazard %d weight %.17g, want %.17g", j, st.W[j], wantW[j])
		}
	}
}

func TestP3GuardMedianResistsSingleActionOutliers(t *testing.T) {
	a := p3Action{0, 1, 2}
	st := newP3State()
	st.GCommon = p3Rep(2, p3GuardCommonWin)
	st.GResid[a.Key()] = append(p3Rep(2, 7), 2000)
	if raised := p3GuardCheck(st, 50); len(raised) != 0 {
		t.Fatalf("a single outlier raised an alarm: %v", raised)
	}
	st.GAlarm[a.Key()] = 0
	if penalty := p3GuardPenalty(st, a.Key(), p3GuardCommon(st)); penalty != 0 {
		t.Fatalf("a single outlier added penalty %v", penalty)
	}
	delete(st.GAlarm, a.Key())
	st.GResid[a.Key()] = append(p3Rep(40, 7), 2000)
	if raised := p3GuardCheck(st, 50); !reflect.DeepEqual(raised, []string{a.Key()}) {
		t.Fatalf("persistent action excess did not alarm: %v", raised)
	}
	if penalty := p3GuardPenalty(st, a.Key(), p3GuardCommon(st)); penalty != 38 {
		t.Fatalf("median excess penalty %v, want 38", penalty)
	}
}

func TestP3AlarmedSuccessesRefreshTheCommonDelay(t *testing.T) {
	a := p3Action{0, 1, 2}
	st := p3PointState(2, 1280, 9000, p3GIndex(0.02))
	st.HCT[a.Key()] = p3Rep(100, p3BaseMin)
	st.HCTSeq[a.Key()] = 0
	st.GCommon = p3Rep(2, p3GuardCommonWin)
	st.GResid[a.Key()] = p3Rep(40, p3GuardMin)
	st.GAlarm[a.Key()] = 0
	jp := 100.0
	for i := 0; i < 33; i++ {
		info, err := p3Observe(st, a, 140, true, 2, st.SHist[0], 50, 1280, 2, cPktDefault, &jp)
		if err != nil || info.Updated || info.Skip != p3SkipGuard || !info.HasResid {
			t.Fatalf("alarmed success %d: %+v %v", i, info, err)
		}
	}
	if common := p3GuardCommon(st); common != 40 || len(st.GCommon) != p3GuardCommonWin ||
		p3GuardPenalty(st, a.Key(), common) != 0 || st.Stats.Resid != 33 || st.Stats.Predict != 33 {
		t.Fatalf("alarmed successes froze the common delay: %v %+v", st.GCommon, st.Stats)
	}
	if _, on := st.GAlarm[a.Key()]; !on {
		t.Fatal("common delay update must preserve the configured refresh lifetime")
	}
}
