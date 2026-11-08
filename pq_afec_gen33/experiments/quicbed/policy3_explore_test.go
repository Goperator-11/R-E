package main

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"reflect"
	"slices"
	"testing"
)

type cx1Run struct {
	A       [3]int   `json:"a"`
	Why     string   `json:"why"`
	HCT     *float64 `json:"hct"`
	OK      bool     `json:"ok"`
	C1      bool     `json:"c1"`
	N       int      `json:"n"`
	Ledger  *float64 `json:"ledger"`
	Pending *bool    `json:"pending"`
	Alarms  []string `json:"alarms"`
}

type cx1Case struct {
	Name string   `json:"name"`
	K    int      `json:"k"`
	W    int      `json:"w"`
	U    float64  `json:"u"`
	RTT  float64  `json:"rtt"`
	S    float64  `json:"s"`
	CPkt float64  `json:"c_pkt"`
	Rate float64  `json:"rate_ms"`
	Cap  float64  `json:"cap_ms"`
	Runs []cx1Run `json:"runs"`
}

func cx1C1Arrivals(k int) *p3Arrivals {
	bitmap := make([]int, k)
	for i := range bitmap {
		bitmap[i] = 1
	}
	return &p3Arrivals{Src: "c1", Sent: k, Bitmap: bitmap}
}

func cx1Show[T any](p *T) string {
	if p == nil {
		return "null"
	}
	return fmt.Sprint(*p)
}

func cx1CheckRunEnd(t *testing.T, name string, r int, st *p3State, run cx1Run) {
	t.Helper()
	if (run.Ledger == nil) != (st.XLedger == nil) || (run.Ledger != nil && math.Abs(*run.Ledger-*st.XLedger) > 1e-9) {
		t.Fatalf("%s run %d: ledger %s want %s", name, r, cx1Show(st.XLedger), cx1Show(run.Ledger))
	}
	if (run.Pending == nil) != (st.XPending == nil) || (run.Pending != nil && *run.Pending != *st.XPending) {
		t.Fatalf("%s run %d: pending %s want %s", name, r, cx1Show(st.XPending), cx1Show(run.Pending))
	}
	alarms := make([]string, 0, len(st.GAlarm))
	for key := range st.GAlarm {
		alarms = append(alarms, key)
	}
	slices.Sort(alarms)
	if !slices.Equal(alarms, run.Alarms) {
		t.Fatalf("%s run %d: alarms %v want %v", name, r, alarms, run.Alarms)
	}
}

func TestP3ExploreMatchesPythonVector(t *testing.T) {
	var cases []cx1Case
	if err := json.Unmarshal([]byte(cx1VectorJSON), &cases); err != nil {
		t.Fatal(err)
	}
	defer func() { p3ExploreRateMs, p3ExploreCapMs = 0, 100.0 }()
	for _, tc := range cases {
		p3ExploreRateMs, p3ExploreCapMs = tc.Rate, tc.Cap
		st := newP3State()
		for r, run := range tc.Runs {
			want := p3Action{Delta: run.A[0], Lead: run.A[1], T: run.A[2]}
			hct := 0.0
			if run.HCT != nil {
				hct = *run.HCT
			}
			for i := 0; i < run.N; i++ {
				d, err := p3Decide(st, tc.W, tc.U, tc.RTT, tc.CPkt, false)
				if err != nil {
					t.Fatalf("%s run %d: %v", tc.Name, r, err)
				}
				if d.Action != want || d.Why != run.Why {
					t.Fatalf("%s run %d step %d: %+v %s, want %+v %s", tc.Name, r, i, d.Action, d.Why, want, run.Why)
				}
				var jp *float64
				if d.HasEJ {
					j := d.EJ
					jp = &j
				}
				var arrivals []*p3Arrivals
				if run.C1 {
					arrivals = append(arrivals, cx1C1Arrivals(tc.K))
				}
				if _, err := p3Observe(st, d.Action, hct, run.OK, tc.K, tc.S, tc.RTT, tc.W, tc.U, tc.CPkt, jp, arrivals...); err != nil {
					t.Fatalf("%s run %d: %v", tc.Name, r, err)
				}
			}
			cx1CheckRunEnd(t, tc.Name, r, st, run)
		}
	}
}

func TestP3ExploreVectorCoversLedgerBranches(t *testing.T) {
	var cases []cx1Case
	if err := json.Unmarshal([]byte(cx1VectorJSON), &cases); err != nil {
		t.Fatal(err)
	}
	seen := map[string]bool{}
	for _, tc := range cases {
		for _, run := range tc.Runs {
			seen["explore"] = seen["explore"] || run.Why == "explore"
			seen["cap"] = seen["cap"] || (run.Ledger != nil && *run.Ledger == tc.Cap)
			seen["failure"] = seen["failure"] || (!run.OK && run.Ledger != nil)
			seen["alarm"] = seen["alarm"] || len(run.Alarms) > 0
			seen["c1"] = seen["c1"] || run.C1
		}
	}
	for _, key := range []string{"explore", "cap", "failure", "alarm", "c1"} {
		if !seen[key] {
			t.Fatalf("vector has no %s run", key)
		}
	}
}

func cx1ExploreReadyDecision(t *testing.T) (*p3State, p3Decision) {
	t.Helper()
	p3ExploreRateMs = 0
	st := newP3State()
	for i := 0; i < 40; i++ {
		d, err := p3Decide(st, 1280, 0, 50, cPktDefault, false)
		if err != nil {
			t.Fatal(err)
		}
		var jp *float64
		if d.HasEJ {
			j := d.EJ
			jp = &j
		}
		if _, err := p3Observe(st, d.Action, 53, true, 2, 3840, 50, 1280, 0, cPktDefault, jp); err != nil {
			t.Fatal(err)
		}
	}
	d, err := p3Decide(st, 1280, 0, 50, cPktDefault, true)
	if err != nil {
		t.Fatal(err)
	}
	if !d.HasEJ || d.M == 0 || len(d.Cands) == 0 {
		t.Fatalf("decision %+v has no protected action to explore from", d.Action)
	}
	ledger := 100.0
	st.XLedger, st.XPending = &ledger, p3Flag(false)
	p3ExploreRateMs = 0.05
	return st, d
}

func TestP3ExploreLeavesReevaluationDecisionAlone(t *testing.T) {
	defer func() { p3ExploreRateMs = 0 }()
	st, d := cx1ExploreReadyDecision(t)
	control, controlState := d, p3CloneState(st)
	p3ExploreStep(controlState, &control, 0, 50, true, false)
	if control.Why != "explore" || !*controlState.XPending {
		t.Fatalf("control decision %+v %s pending %v: setup cannot explore", control.Action, control.Why, *controlState.XPending)
	}
	reeval := d
	reeval.Reeval, reeval.Why = true, "reeval"
	p3ExploreStep(st, &reeval, 0, 50, true, false)
	if reeval.Action != d.Action || reeval.Why != "reeval" || *st.XPending {
		t.Fatalf("reevaluation became %+v %s pending %v", reeval.Action, reeval.Why, *st.XPending)
	}
	if *st.XLedger != 100 {
		t.Fatalf("reevaluation ledger %v, want cap 100", *st.XLedger)
	}
}

func TestP3ExplorePickSkipsAlarmedArm(t *testing.T) {
	defer func() { p3ExploreRateMs = 0 }()
	st, d := cx1ExploreReadyDecision(t)
	first := p3ExplorePick(st, &d, 0, 50)
	if first < 0 {
		t.Fatal("setup cannot explore")
	}
	key := d.Cands[first].Action.Key()
	st.GAlarm[key] = st.NDec
	if next := p3ExplorePick(st, &d, 0, 50); next >= 0 && d.Cands[next].Action.Key() == key {
		t.Fatalf("explore picked alarmed arm %s", key)
	}
}

func TestP3ExploreOffWritesNoStateFields(t *testing.T) {
	p3ExploreRateMs = 0
	st := newP3State()
	if _, err := p3Decide(st, 1280, 2, 50, cPktDefault, false); err != nil {
		t.Fatal(err)
	}
	raw, err := json.Marshal(st)
	if err != nil {
		t.Fatal(err)
	}
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(raw, &fields); err != nil {
		t.Fatal(err)
	}
	for _, key := range []string{"x_ledger", "x_pending"} {
		if _, ok := fields[key]; ok {
			t.Fatalf("flag off wrote %s", key)
		}
	}
}

func TestP3ExploreStateRoundTripAndValidation(t *testing.T) {
	defer func() { p3ExploreRateMs = 0 }()
	p3ExploreRateMs = 0.05
	st := newP3State()
	if _, err := p3Decide(st, 1280, 2, 50, cPktDefault, false); err != nil {
		t.Fatal(err)
	}
	if _, err := p3Observe(st, p3Action{}, 53, true, 2, 3840, 50, 1280, 2, cPktDefault, nil); err != nil {
		t.Fatal(err)
	}
	if _, err := p3Decide(st, 1280, 2, 50, cPktDefault, false); err != nil {
		t.Fatal(err)
	}
	raw, err := json.Marshal(st)
	if err != nil {
		t.Fatal(err)
	}
	var back p3State
	if err := json.Unmarshal(raw, &back); err != nil || back.validate() != nil || back.XLedger == nil || *back.XLedger != *st.XLedger {
		t.Fatalf("round trip %v %v", err, back.XLedger)
	}
	back.XLedger = nil
	back.XPending = p3Flag(true)
	if back.validate() == nil {
		t.Fatal("x_pending without x_ledger passed validation")
	}
	bad := math.Inf(1)
	back.XLedger, back.XPending = &bad, p3Flag(false)
	if back.validate() == nil {
		t.Fatal("infinite x_ledger passed validation")
	}
	ledger := 1.0
	back.XLedger, back.XPending = &ledger, nil
	if back.validate() == nil {
		t.Fatal("x_ledger without x_pending passed validation")
	}
}

func TestP3ExploreStateJSONMatchesPython(t *testing.T) {
	var states map[string]json.RawMessage
	if err := json.Unmarshal([]byte(cx1PythonStatesJSON), &states); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"pending_false", "pending_true"} {
		raw := states[name]
		var st p3State
		if err := json.Unmarshal(raw, &st); err != nil {
			t.Fatalf("%s: %v", name, err)
		}
		if err := st.validate(); err != nil {
			t.Fatalf("%s: %v", name, err)
		}
		back, err := json.Marshal(&st)
		if err != nil {
			t.Fatal(err)
		}
		var want, got map[string]any
		if err := json.Unmarshal(raw, &want); err != nil {
			t.Fatal(err)
		}
		if err := json.Unmarshal(back, &got); err != nil {
			t.Fatal(err)
		}
		for key := range want {
			if !reflect.DeepEqual(want[key], got[key]) {
				t.Fatalf("%s: field %s Go %v Python %v", name, key, got[key], want[key])
			}
		}
		if len(got) != len(want) {
			t.Fatalf("%s: Go wrote %d fields, Python %d", name, len(got), len(want))
		}
		for _, edit := range []struct {
			key   string
			value json.RawMessage
		}{{"x_ledger", nil}, {"x_pending", nil}, {"x_ledger", json.RawMessage("null")}, {"x_pending", json.RawMessage("null")}} {
			var fields map[string]json.RawMessage
			if err := json.Unmarshal(raw, &fields); err != nil {
				t.Fatal(err)
			}
			if edit.value == nil {
				delete(fields, edit.key)
			} else {
				fields[edit.key] = edit.value
			}
			broken, err := json.Marshal(fields)
			if err != nil {
				t.Fatal(err)
			}
			var bad p3State
			if err := json.Unmarshal(broken, &bad); err == nil && bad.validate() == nil {
				t.Fatalf("%s with %s=%s passed", name, edit.key, edit.value)
			}
			cache := filepath.Join(t.TempDir(), "cache3.json")
			body := `{"schema":"` + p3CacheSchema + `","dests":{"127.0.0.1:4433":{"state":` + string(broken) +
				`,"min_rtt_ms":0,"rtt_observations":0,"min_hct_ms":0,"conns":0}}}`
			if err := os.WriteFile(cache, []byte(body), 0o644); err != nil {
				t.Fatal(err)
			}
			if _, err := loadDestCache3(cache); err == nil {
				t.Fatalf("cache with %s %s=%s loaded", name, edit.key, edit.value)
			}
		}
	}
}
