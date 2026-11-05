package main

import (
	"bytes"
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

func p3C1State(st *p3State) *p3State {
	st.C1Seen = true
	st.GAlarm = map[string]int{}
	return st
}

func TestP3V331C1MissingReplyUsesCategoricalEvidence(t *testing.T) {
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
		{"failure_without_base", newP3State, a, math.NaN(), false, 50, 2, "", 1, 0},
	} {
		t.Run(tc.name, func(t *testing.T) {
			st := p3C1State(tc.state())
			st.ArrivalStreak = 4
			p3SetPoint(st, p3GIndex(0.02))
			st.W = []float64{0.4, 0.25, 0.15, 0.1, 0.1}
			_, hasCtx := p3Context(st, 1280, tc.u, tc.rtt, cPktDefault)
			wantPost, wantW := p3PredictStep(st.Post, st.W)
			kind := "predict_only"
			if hasCtx {
				wantPost, wantW = p3TestCategoricalPost(t, st, tc.arm, tc.hct, tc.ok, tc.rtt, tc.u)
				kind = "categorical"
			}
			info, err := p3Observe(st, tc.arm, tc.hct, tc.ok, 2, 18000, tc.rtt, 1280, tc.u, cPktDefault, nil)
			legacySkip := tc.skip
			if tc.noBase != 0 {
				legacySkip = "no_base"
			} else if tc.noCtx != 0 {
				legacySkip = "no_ctx"
			}
			wantSkip := ""
			if !hasCtx {
				wantSkip = "no_ctx"
			}
			if err != nil || info.Path != "c1" || info.Updated != hasCtx || info.Skip != wantSkip ||
				info.LegacySkip != legacySkip || info.LossUpdateKind != kind || info.ArrivalReject != "source_none" {
				t.Fatalf("observation %+v %v", info, err)
			}
			if !reflect.DeepEqual(st.Post, wantPost) || !reflect.DeepEqual(st.W, wantW) {
				t.Fatal("missing reply did not use one categorical transition")
			}
			if st.ArrivalStreak != 0 || info.StreakAfter != 0 || st.Stats.Binary != 0 || st.Stats.ArrNone != 1 ||
				st.Stats.Predict != 1 || st.Stats.NoBase != tc.noBase || st.Stats.NoCtx != tc.noCtx {
				t.Fatalf("counters %+v streak %d", st.Stats, st.ArrivalStreak)
			}
		})
	}
}

func TestP3V331FirstReplySwitchesPathOnceAndClearsAlarms(t *testing.T) {
	a := p3Action{0, 2, 2}
	st := p3PointState(2, 1280, 9000, p3GIndex(0.15))
	st.W = []float64{0.2, 0.2, 0.2, 0.2, 0.2}
	st.HCT[a.Key()] = p3Rep(100, p3BaseMin)
	st.HCTSeq[a.Key()] = 0
	st.GAlarm = map[string]int{"0,1,2": 0, "0,2,2": 0}
	st.GResid = map[string][]float64{"0,1,2": p3Rep(40, 8), "0,2,2": p3Rep(45, 8)}
	st.GCommon = p3Rep(2, p3GuardCommonWin)
	before := p3CloneState(st)
	info, err := p3Observe(st, a, 110, true, 2, st.SHist[0], 50, 1280, 2, cPktDefault, nil,
		&p3Arrivals{Src: "none", Sent: 6, Lost: 2})
	if err != nil || info.Path != "none" || st.C1Seen || len(st.GAlarm) != 2 || info.LossUpdateKind == "datagram" {
		t.Fatalf("source none switched the path: %+v %v", info, err)
	}
	if info.Skip != p3SkipGuard || info.Updated || st.Stats.ArrNone != 1 || st.Stats.Guard != 1 {
		t.Fatalf("none path must keep the v3.2 guard skip: %+v %+v", info, st.Stats)
	}
	st = p3CloneState(before)
	l, err := p3ArrivalLikelihood(6, 2)
	if err != nil {
		t.Fatal(err)
	}
	wantPost, wantW := p3FilterStep(st.Post, st.W, l)
	jp := 100.0
	info, err = p3Observe(st, a, 160, true, 2, st.SHist[0], 50, 1280, 2, cPktDefault, &jp,
		&p3Arrivals{Src: "ack", Sent: 6, Lost: 2})
	if err != nil || info.Path != "c1" || !st.C1Seen || len(st.GAlarm) != 0 || info.LossUpdateKind != "datagram" ||
		info.Alarmed || len(info.Raised) != 0 || info.StreakAfter != 1 || st.ArrivalStreak != 1 {
		t.Fatalf("first reply %+v %v", info, err)
	}
	if !reflect.DeepEqual(st.Post, wantPost) || !reflect.DeepEqual(st.W, wantW) {
		t.Fatal("first reply was not one datagram transition")
	}
	if st.Stats.AlarmCleared != 2 || st.Stats.Datagram != 1 || st.Stats.Binary != 0 || st.Stats.AlarmRaised != 0 ||
		len(st.GResid["0,2,2"]) != 9 || st.Stats.Resid != 1 {
		t.Fatalf("switch counters %+v resid %v", st.Stats, st.GResid)
	}
	for i := 0; i < 12; i++ {
		info, err = p3Observe(st, a, 160, true, 2, st.SHist[0], 50, 1280, 2, cPktDefault, &jp)
		if err != nil || info.Path != "c1" || info.LossUpdateKind != "categorical" || len(st.GAlarm) != 0 || info.Alarmed {
			t.Fatalf("later missing reply %d: %+v %v", i, info, err)
		}
	}
	if st.ArrivalStreak != 0 || st.Stats.AlarmCleared != 2 || st.Stats.AlarmRaised != 0 {
		t.Fatalf("c1 destination raised alarms or kept a streak: %+v", st.Stats)
	}
	d, err := p3Decide(st, 1280, 2, 50, cPktDefault, true)
	if err != nil || d.PolicyPath != "c1" || !d.C1Seen || len(d.GuardCleared) != 0 || d.GuardAlarmed != 0 {
		t.Fatalf("c1 decision %+v %v", d, err)
	}
	for _, c := range d.Cands {
		if c.Pen != 0 || c.Score != c.EJ {
			t.Fatalf("c1 candidate carries a guard penalty: %+v", c)
		}
	}
}

func TestP3V331TruncatedAndEmptyRepliesSwitchWithoutDatagramEvidence(t *testing.T) {
	for _, arr := range []*p3Arrivals{
		{Src: "c1", Sent: 4, Lost: 1, Bitmap: []int{0, 1}, Trunc: true},
		{Src: "ack", Sent: 0, Lost: 0, Bitmap: []int{}},
	} {
		st := p3PointState(2, 1280, 9000, p3GIndex(0.02))
		st.HCT["0,1,2"] = p3Rep(100, p3BaseMin)
		st.HCTSeq["0,1,2"] = 0
		st.GAlarm = map[string]int{"0,1,2": 0}
		wantPost, wantW := p3TestCategoricalPost(t, st, p3Action{0, 1, 2}, 110, true, 50, 2)
		info, err := p3Observe(st, p3Action{0, 1, 2}, 110, true, 2, st.SHist[0], 50, 1280, 2, cPktDefault, nil, arr)
		if err != nil || !st.C1Seen || info.LossUpdateKind != "categorical" || st.ArrivalStreak != 0 ||
			len(st.GAlarm) != 0 || st.Stats.AlarmCleared != 1 || info.ArrivalReject == "" {
			t.Fatalf("%+v: %+v %v", arr, info, err)
		}
		if !reflect.DeepEqual(st.Post, wantPost) || !reflect.DeepEqual(st.W, wantW) {
			t.Fatalf("%+v: censored reply did not use categorical evidence", arr)
		}
	}
}

func TestP3V331StreakCountsUsableRepliesUpToCap(t *testing.T) {
	st := p3PointState(2, 1280, 9000, p3GIndex(0.02))
	full := &p3Arrivals{Src: "c1", Sent: 4, Lost: 0}
	for i := 1; i <= p3ArrivalStreakCap+3; i++ {
		info, err := p3Observe(st, p3Action{0, 1, 1}, 90, true, 2, st.SHist[0], 50, 1280, 2, cPktDefault, nil, full)
		want := min(i, p3ArrivalStreakCap)
		if err != nil || st.ArrivalStreak != want || info.StreakAfter != want {
			t.Fatalf("reply %d: streak %d %v", i, st.ArrivalStreak, err)
		}
	}
	if _, err := p3Observe(st, p3Action{0, 1, 1}, 90, true, 2, st.SHist[0], 50, 1280, 2, cPktDefault, nil,
		&p3Arrivals{Src: "c1", Sent: 4, Lost: 0, Trunc: true}); err != nil || st.ArrivalStreak != 0 {
		t.Fatalf("truncated reply kept the streak %d %v", st.ArrivalStreak, err)
	}
}

func TestP3V331C1ReevaluationWaitsForMissingFeedback(t *testing.T) {
	k, w, cert := 2, 1280, 16000
	st := p3C1State(p3PointState(k, w, cert, p3GIndex(0.3)))
	st.ArrivalStreak = 3
	for i := 0; i < 40; i++ {
		d, err := p3Decide(st, w, 2, 50, cPktDefault, false)
		if err != nil || d.Why != "ej" || !d.ReevalCond || !d.ReevalHeld || d.PolicyPath != "c1" {
			t.Fatalf("held decision %d: %+v %v", i, d, err)
		}
	}
	if st.NReeval != 0 || st.NDec != 40 || st.Stats.Reeval != 0 {
		t.Fatalf("held decisions advanced reevaluation: %d %d", st.NReeval, st.NDec)
	}
	st.ArrivalStreak = 0
	for i := 0; i < 16; i++ {
		d, err := p3Decide(st, w, 2, 50, cPktDefault, false)
		want := "ej"
		if i == 15 {
			want = "reeval"
		}
		if err != nil || d.Why != want || d.ReevalHeld {
			t.Fatalf("open decision %d: %+v %v", i, d, err)
		}
	}
	if st.NReeval != 16 || st.Stats.Reeval != 1 {
		t.Fatalf("open decisions %d reeval %d", st.NReeval, st.Stats.Reeval)
	}
}

func TestP3V331NoneReevaluationIgnoresFeedbackState(t *testing.T) {
	st := p3PointState(2, 1280, 16000, p3GIndex(0.3))
	for i := 0; i < 32; i++ {
		d, err := p3Decide(st, 1280, 2, 50, cPktDefault, false)
		want := "ej"
		if i%16 == 15 {
			want = "reeval"
		}
		if err != nil || d.Why != want || d.ReevalHeld || d.PolicyPath != "none" || d.C1Seen {
			t.Fatalf("none decision %d: %+v %v", i, d, err)
		}
	}
}

func TestP3V331C1DecisionsIgnoreGuardResiduals(t *testing.T) {
	st := p3PointState(2, 1280, 9000, p3GIndex(0.02))
	jp := 100.0
	for i := 0; i < 12; i++ {
		if _, err := p3Observe(st, p3Action{0, 2, 2}, 102, true, 2, st.SHist[0], 50, 1280, 2, cPktDefault, &jp); err != nil {
			t.Fatal(err)
		}
	}
	p3EnterC1(st)
	for i := 0; i < 12; i++ {
		info, err := p3Observe(st, p3Action{0, 1, 2}, 160, true, 2, st.SHist[0], 50, 1280, 2, cPktDefault, &jp)
		if err != nil || len(info.Raised) != 0 || info.Alarmed {
			t.Fatalf("c1 residual %d: %+v %v", i, info, err)
		}
	}
	if len(st.GAlarm) != 0 || p3Median(st.GResid["0,1,2"]) != 60 || !(p3Median(st.GResid["0,1,2"])-p3GuardCommon(st) > p3GuardFrac*50) {
		t.Fatalf("residual window %v common %v alarms %v", st.GResid, p3GuardCommon(st), st.GAlarm)
	}
	d, err := p3Decide(st, 1280, 2, 50, cPktDefault, true)
	if err != nil || d.GuardAlarm || len(d.GuardCleared) != 0 {
		t.Fatalf("decision %+v %v", d, err)
	}
	for _, c := range d.Cands {
		if c.Pen != 0 || c.Score != c.EJ {
			t.Fatalf("penalised c1 candidate %+v", c)
		}
	}
}

func TestP3V331StateMarkersAreValidated(t *testing.T) {
	good := p3C1State(p3PointState(2, 1280, 9000, p3GIndex(0.02)))
	good.ArrivalStreak = 2
	if err := good.validate(); err != nil {
		t.Fatal(err)
	}
	for name, mutate := range map[string]func(*p3State){
		"streak_over_cap": func(st *p3State) { st.ArrivalStreak = p3ArrivalStreakCap + 1 },
		"negative_streak": func(st *p3State) { st.ArrivalStreak = -1 },
		"streak_without":  func(st *p3State) { st.C1Seen = false },
		"c1_with_alarm":   func(st *p3State) { st.GAlarm["0,1,2"] = 0 },
		"negative_binary": func(st *p3State) { st.Stats.Binary = -1 },
	} {
		t.Run(name, func(t *testing.T) {
			st := p3CloneState(good)
			mutate(st)
			before, _ := json.Marshal(st)
			if err := st.validate(); err == nil {
				t.Fatal("invalid markers accepted")
			}
			if _, err := p3Decide(st, 1280, 2, 50, cPktDefault, false); err == nil {
				t.Fatal("decide accepted invalid markers")
			}
			if _, err := p3Observe(st, p3Action{}, 80, true, 2, 8500, 50, 1280, 2, cPktDefault, nil); err == nil {
				t.Fatal("observe accepted invalid markers")
			}
			after, _ := json.Marshal(st)
			if !bytes.Equal(before, after) {
				t.Fatal("rejected call mutated state")
			}
		})
	}
	raw, err := json.Marshal(good)
	if err != nil {
		t.Fatal(err)
	}
	var back p3State
	if err := json.Unmarshal(raw, &back); err != nil || back.validate() != nil || !back.C1Seen || back.ArrivalStreak != 2 {
		t.Fatalf("round trip %+v %v", back, err)
	}
	for _, bad := range []string{
		strings.Replace(string(raw), `"c1_seen":true,`, ``, 1),
		strings.Replace(string(raw), `,"arrival_streak":2`, ``, 1),
		strings.Replace(string(raw), `"c1_seen":true`, `"c1_seen":null`, 1),
		strings.Replace(string(raw), `"arrival_streak":2`, `"arrival_streak":null`, 1),
		strings.Replace(string(raw), `"c1_seen":true`, `"c1_seen":1`, 1),
		strings.Replace(string(raw), `"c1_seen":true`, `"c1_seen":"true"`, 1),
		strings.Replace(string(raw), `"arrival_streak":2`, `"arrival_streak":2.0`, 1),
		strings.Replace(string(raw), `"arrival_streak":2`, `"arrival_streak":true`, 1),
		strings.Replace(string(raw), `"v":11`, `"v":11,"extra":1`, 1),
		strings.Replace(string(raw), `"binary":0`, `"binary":0,"monitor":0`, 1),
	} {
		if bad == string(raw) {
			t.Fatal("fixture replacement did not apply")
		}
		var st p3State
		err := json.Unmarshal([]byte(bad), &st)
		if err == nil {
			st.normalize()
			err = st.validate()
		}
		if err == nil {
			t.Fatalf("bad state accepted: %s", bad)
		}
	}
}

func TestP3V331CacheSchemaRejectsEarlierGenerations(t *testing.T) {
	dir := t.TempDir()
	c, err := loadDestCache3(filepath.Join(dir, "cache3.json"))
	if err != nil {
		t.Fatal(err)
	}
	if _, _, err := c.observe("x", p3Action{}, 80, true, 2, 8500, 50, true, 1280, 2, cPktDefault,
		&p3Arrivals{Src: "c1", Sent: 2, Lost: 0}); err != nil {
		t.Fatal(err)
	}
	if err := c.save(); err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(c.path)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(raw), `"schema":"padfec3.cache3/11"`) || !strings.Contains(string(raw), `"c1_seen":true`) {
		t.Fatalf("saved cache %s", raw)
	}
	back, err := loadDestCache3(c.path)
	if err != nil || !back.Dests["x"].State.C1Seen || back.Dests["x"].State.ArrivalStreak != 1 {
		t.Fatalf("reload %v", err)
	}
	for name, text := range map[string]string{
		"v32_schema":  strings.Replace(string(raw), "padfec3.cache3/11", "padfec3.cache3/3", 1),
		"v4_state":    strings.Replace(string(raw), `"v":11`, `"v":4`, 1),
		"no_marker":   strings.Replace(string(raw), `"c1_seen":true,`, ``, 1),
		"alarm_on_c1": strings.Replace(string(raw), `"g_alarm":{}`, `"g_alarm":{"0,0,0":0}`, 1),
	} {
		if text == string(raw) {
			t.Fatalf("%s: fixture replacement did not apply", name)
		}
		path := filepath.Join(dir, name+".json")
		if err := os.WriteFile(path, []byte(text), 0600); err != nil {
			t.Fatal(err)
		}
		_, err := loadDestCache3(path)
		if err == nil {
			t.Fatalf("%s accepted", name)
		}
		if name == "v32_schema" && !strings.Contains(err.Error(), `want "padfec3.cache3/11"`) {
			t.Fatalf("old cache error does not name the schema: %v", err)
		}
	}
}

func TestP3V331ParityDatagramsFitQuicGoReceiveLimit(t *testing.T) {
	if p3UDPMax != quicgoMaxIPS || quicgoMaxIPS != 1452 {
		t.Fatalf("parity cap %d", p3UDPMax)
	}
	for _, tc := range []struct {
		k, w int
		s    float64
	}{{2, 1406, 2000}, {2, 1406, 30000}, {1, 1200, 21250}, {2, 1280, 30000}, {4, 1440, 30000}, {1, 1410, 12000}} {
		cands := p3Candidates(tc.k, tc.w, tc.s, cPktDefault)
		if len(cands) == 0 {
			t.Fatalf("%+v: no candidates", tc)
		}
		have := map[p3Action]bool{}
		parity := false
		for _, c := range cands {
			have[c.Action] = true
			if c.M > 0 {
				parity = true
				if parityDatagramBytes(c.WEff, tc.k) > 1452 {
					t.Fatalf("%+v: parity datagram %d bytes", c.Action, parityDatagramBytes(c.WEff, tc.k))
				}
			}
		}
		if parity != (parityDatagramBytes(tc.w, tc.k) <= 1452) {
			t.Fatalf("%+v: parity candidates %v", tc, parity)
		}
		for _, g := range levers(tc.k, tc.w, maxStepsDefault, p3MMax, tc.s, cPktDefault, quicgoMaxIPS) {
			if g.wEff > quicgoMaxIPS {
				continue
			}
			oversized := g.m > 0 && parityDatagramBytes(g.wEff, tc.k) > 1452
			for lead := 0; lead <= g.m; lead++ {
				a := p3Action{Delta: g.delta, Lead: lead, T: g.m - lead}
				if have[a] == oversized {
					t.Fatalf("%+v: action %+v present %v, oversized %v", tc, a, have[a], oversized)
				}
			}
		}
	}
}

func TestAuto3RowReportsPolicyPath(t *testing.T) {
	st := p3C1State(p3PointState(2, 1280, 16000, p3GIndex(0.3)))
	st.ArrivalStreak = 1
	d, err := p3Decide(st, 1280, 2, 50, cPktDefault, false)
	if err != nil {
		t.Fatal(err)
	}
	info, err := p3Observe(st, d.Action, 120, true, 2, st.SHist[0], 50, 1280, 2, cPktDefault, nil)
	if err != nil {
		t.Fatal(err)
	}
	row := auto3Row(trial{Layout: "v3"}, auto3PlanFor(d, 1280, 50, "quic_ack_min_rtt"), info, nil, 0.3)
	raw, _ := json.Marshal(&row)
	var r map[string]any
	json.Unmarshal(raw, &r)
	if r["policy_path"] != "c1" || r["reeval_feedback_suppressed"] != true || r["obs_policy_path"] != "c1" ||
		r["obs_loss_update_kind"] != "categorical" || r["policy_version"] != "v3.3.1-dev" {
		t.Fatalf("row %s", raw)
	}
	cold := auto3Row(trial{Layout: "v3"}, auto3PlanFor(p3B0("cold", make([]float64, p3NG)), 1280, 0, "none"),
		p3ObsInfo{Y: -1}, nil, 0.13)
	raw, _ = json.Marshal(&cold)
	r = map[string]any{}
	json.Unmarshal(raw, &r)
	if r["obs_policy_path"] != nil || r["obs_loss_update_kind"] != nil {
		t.Fatalf("row without observation %s", raw)
	}
}
