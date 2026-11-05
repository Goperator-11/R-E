package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"slices"
)

const p3ClassEps = 0.001
const p3ClassCProcMs = 3.0

var p3ClassNames = []string{"one_rtt", "two_rtt", "late_or_failure"}

type p3Arrivals struct {
	Src    string `json:"src"`
	Sent   int    `json:"sent"`
	Lost   int    `json:"lost"`
	Bitmap []int  `json:"bitmap"`
	Trunc  bool   `json:"trunc"`
}

func (a *p3Arrivals) UnmarshalJSON(b []byte) error {
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(b, &fields); err != nil {
		return err
	}
	if len(fields) != 5 {
		return errors.New("arrivals requires exactly src,sent,lost,bitmap,trunc")
	}
	for _, key := range []string{"src", "sent", "lost", "bitmap", "trunc"} {
		v, ok := fields[key]
		if !ok || (key != "bitmap" && bytes.Equal(bytes.TrimSpace(v), []byte("null"))) {
			return fmt.Errorf("invalid arrivals field %s", key)
		}
	}
	type plain p3Arrivals
	var next plain
	if err := json.Unmarshal(b, &next); err != nil {
		return err
	}
	var bits []json.RawMessage
	if err := json.Unmarshal(fields["bitmap"], &bits); err != nil {
		return err
	}
	for _, bit := range bits {
		if bytes.Equal(bytes.TrimSpace(bit), []byte("null")) {
			return errors.New("null bitmap bit")
		}
	}
	x, err := p3NormalizeArrivals([]*p3Arrivals{(*p3Arrivals)(&next)})
	if err == nil {
		*a = x
	}
	return err
}

func p3NormalizeArrivals(values []*p3Arrivals) (p3Arrivals, error) {
	if len(values) > 1 {
		return p3Arrivals{}, errors.New("at most one arrivals value is allowed")
	}
	if len(values) == 0 || values[0] == nil {
		return p3Arrivals{Src: "none"}, nil
	}
	a := *values[0]
	if a.Src != "c1" && a.Src != "ack" && a.Src != "none" {
		return a, errors.New("invalid arrivals source")
	}
	if a.Lost < 0 || a.Sent < a.Lost || a.Sent > p3KMax+p3MMax {
		return a, errors.New("invalid arrivals counts")
	}
	if a.Bitmap != nil {
		lost := 0
		for _, bit := range a.Bitmap {
			if bit != 0 && bit != 1 {
				return a, errors.New("invalid arrivals bitmap bit")
			}
			if bit == 0 {
				lost++
			}
		}
		if len(a.Bitmap) > a.Sent || (!a.Trunc && (len(a.Bitmap) != a.Sent || lost != a.Lost)) {
			return a, errors.New("arrivals bitmap disagrees with counts")
		}
		a.Bitmap = slices.Clone(a.Bitmap)
	}
	return a, nil
}

func p3ArrivalLikelihood(sent, lost int) ([]float64, error) {
	if sent < 1 || sent > p3KMax+p3MMax || lost < 0 || lost > sent {
		return nil, errors.New("invalid arrival likelihood counts")
	}
	out := make([]float64, p3NG)
	for g, p := range p3G {
		v := 1.0
		for i := 0; i < lost; i++ {
			v *= p
		}
		for i := 0; i < sent-lost; i++ {
			v *= 1.0 - p
		}
		out[g] = v
	}
	return out, nil
}

func p3GradeCutoffs(c *p3Ctx, a p3Action) (float64, float64, error) {
	if c == nil || !a.valid() {
		return 0, 0, errors.New("grade cutoff needs context and valid action")
	}
	w := c.W + a.Delta
	first := float64(float64(1.5*c.RTT)+p3Tau(c.K*w+a.Lead*parityDatagramBytes(w, c.K), c.U)) + p3ClassCProcMs
	second := float64(first+c.RTT) + p3Tau(w, c.U)
	if !p3Finite(first) || !p3Finite(second) || first <= 0 || second <= 0 {
		return 0, 0, errors.New("invalid grade cutoffs")
	}
	return first, second, nil
}

func p3ClassifyHCT(c *p3Ctx, a p3Action, hct float64, ok bool) (int, float64, float64, error) {
	grade := -1
	if !ok {
		grade = 2
	}
	if c == nil {
		return grade, 0, 0, nil
	}
	first, second, err := p3GradeCutoffs(c, a)
	if err != nil {
		return grade, first, second, err
	}
	if !ok {
		return 2, first, second, nil
	}
	if !p3Finite(hct) || hct <= 0 {
		return -1, first, second, errors.New("HCT must be finite and positive")
	}
	grade = 2
	if hct < first {
		grade = 0
	} else if hct < second {
		grade = 1
	}
	return grade, first, second, nil
}

func p3ClassProbabilities(c *p3Ctx, a p3Action, g int) ([]float64, error) {
	if c == nil || !a.valid() || g < 0 || g >= p3NG {
		return nil, errors.New("invalid categorical input")
	}
	pt := p3ModelPoint(c.K, c.W+a.Delta, c.U, c.RTT, c.NNeed, a.Lead, a.M(), g)
	if !p3Finite(pt.J) {
		return nil, errors.New("model cost exceeds floating-point range")
	}
	q := []float64{pt.P1, pt.P2, pt.PF}
	return q, p3ValidateMass(q, 3, "categorical probabilities")
}

func p3ClassLikelihood(c *p3Ctx, a p3Action, grade int) ([]float64, error) {
	if grade < 0 || grade > 2 {
		return nil, errors.New("invalid grade")
	}
	out := make([]float64, p3NG)
	for g := range out {
		qs, err := p3ClassProbabilities(c, a, g)
		if err != nil {
			return nil, err
		}
		q := qs[grade]
		out[g] = float64((1.0-p3ClassEps)*q) + float64(p3ClassEps*(1.0-q))/2.0
	}
	return out, nil
}

func p3NullableString(s string) any {
	if s == "" {
		return nil
	}
	return s
}

func p3L1Info(info p3ObsInfo) map[string]any {
	var y, b, resid any
	if info.Y >= 0 {
		y = info.Y
	}
	if info.HasBase {
		b = info.Baseline
	}
	if info.HasResid {
		resid = info.Resid
	}
	raised := info.Raised
	if raised == nil {
		raised = []string{}
	}
	out := map[string]any{
		"y": y, "baseline": b, "ref": p3NullableString(info.Ref), "updated": info.Updated,
		"shielded": info.Shielded, "skip": p3NullableString(info.Skip), "ctx": info.Ctx, "resid": resid,
		"alarmed": info.Alarmed, "raised": raised, "common": info.Common, "n_alarm": info.NAlarm,
		"loss_evidence_src": info.Evidence.Src, "arrival_sent": info.Evidence.Sent,
		"arrival_lost": info.Evidence.Lost, "arrival_trunc": info.Evidence.Trunc, "arrival_bitmap": info.Evidence.Bitmap,
		"arrival_usable": info.ArrivalReject == "", "arrival_reject_reason": p3NullableString(info.ArrivalReject),
		"loss_update_kind": info.LossUpdateKind, "policy_path": info.Path, "c1_seen": info.C1Seen,
		"arrival_streak_after": info.StreakAfter,
	}
	if info.Path != "c1" {
		return out
	}
	var grade, gradeName, cut1, cut2 any
	if info.Grade >= 0 {
		grade = info.Grade
		gradeName = p3ClassNames[info.Grade]
	}
	reason := "no_ctx"
	if info.HasCtx {
		cut1 = info.Cut1
		cut2 = info.Cut2
		reason = "hct_or_failure"
	}
	for key, value := range map[string]any{
		"grade": grade, "grade_name": gradeName, "grade_valid": info.HasCtx, "grade_reason": reason,
		"cut1_ms": cut1, "cut2_ms": cut2, "cutoff_rtt_ms": info.CutoffRTT,
		"cutoff_rtt_source": "observation_rtt_current_policy", "c_proc_used_ms": p3ClassCProcMs,
		"margin1_ms": 0.0, "margin2_ms": 0.0, "epsilon_before": p3ClassEps, "epsilon_after": p3ClassEps,
		"epsilon_update_eligible": false, "legacy_y": y, "legacy_skip_reason": p3NullableString(info.LegacySkip),
		"legacy_shielded": info.LegacyShielded,
	} {
		out[key] = value
	}
	return out
}

func p3RefDecision(d p3Decision) map[string]any {
	var wEff, cb, ej, score, n2, jmin, nNeed, k, s, alt any
	if d.HasEJ {
		wEff, cb, ej, score, n2, jmin, nNeed, k, s = d.WEff, d.ClientBytes, d.EJ, d.Score, d.N2, d.JMin, d.NNeed, d.K, d.S
	}
	if d.HasAlt {
		alt = d.Alt.Action.arr()
	}
	cleared := d.GuardCleared
	if cleared == nil {
		cleared = []string{}
	}
	return map[string]any{
		"action": d.Action.arr(), "delta": d.Action.Delta, "lead": d.Action.Lead, "T": d.Action.T,
		"m": d.M, "mode": d.Mode, "W_eff": wEff, "client_bytes": cb, "added": d.Added,
		"ej": ej, "pen": d.Pen, "score": score, "n2": n2, "j3_pred_pre_ms": ej, "jmin": jmin,
		"n_tied": d.NTied, "n_cands": d.NCands, "n_need": nNeed, "k": k, "S": s, "why": d.Why,
		"reeval_cond": d.ReevalCond, "alt": alt, "reeval": d.Reeval, "p_mean": d.PMean,
		"p_map": d.PMap, "p_ge_010": d.PGe010, "guard_alarm": d.GuardAlarm,
		"guard_common_ms": d.GuardCommon, "guard_alarmed_actions": d.GuardAlarmed,
		"guard_cleared": cleared, "dec_index": d.DecIndex, "n_reeval": d.NReeval,
		"policy_version": d.PolicyVersion, "policy_path": d.PolicyPath, "c1_seen": d.C1Seen,
		"arrival_streak": d.ArrivalStreak, "reeval_feedback_suppressed": d.ReevalHeld,
	}
}

type p3L1Row struct {
	A         [3]int      `json:"a"`
	HCT       *float64    `json:"hct"`
	OK        bool        `json:"ok"`
	K         int         `json:"k"`
	Srv       float64     `json:"srv"`
	RTT       float64     `json:"rtt"`
	W         int         `json:"w"`
	U         float64     `json:"u"`
	CPkt      float64     `json:"c_pkt"`
	JPred     *float64    `json:"j_pred"`
	Arrivals  *p3Arrivals `json:"arrivals"`
	PathRTT   float64     `json:"path_rtt"`
	PathValid bool        `json:"path_valid"`
	DecideRTT float64     `json:"decide_rtt"`
}

func (row *p3L1Row) observe(st *p3State) (p3ObsInfo, error) {
	a := p3Action{row.A[0], row.A[1], row.A[2]}
	hct := math.NaN()
	if row.HCT != nil {
		hct = *row.HCT
	}
	return p3Observe(st, a, hct, row.OK, row.K, row.Srv, row.RTT, row.W, row.U, row.CPkt, row.JPred, row.Arrivals)
}

type p3L1Reference struct {
	Arrivals []struct {
		Sent int `json:"sent"`
		Lost int `json:"lost"`
	} `json:"arrivals"`
	Classes []struct {
		Ctx p3Ctx     `json:"ctx"`
		A   [3]int    `json:"a"`
		HCT []float64 `json:"hct"`
	} `json:"classes"`
	Observations []struct {
		ID      string    `json:"id"`
		Initial p3State   `json:"initial"`
		Rows    []p3L1Row `json:"rows"`
	} `json:"observations"`
	Sequences []struct {
		ID      string    `json:"id"`
		Initial p3State   `json:"initial"`
		Rows    []p3L1Row `json:"rows"`
		StateAt []int     `json:"state_at"`
	} `json:"sequences"`
	Caches []struct {
		ID   string    `json:"id"`
		Rows []p3L1Row `json:"rows"`
	} `json:"caches"`
	InvalidArrivals []json.RawMessage `json:"invalid_arrivals"`
	InvalidStates   []json.RawMessage `json:"invalid_states"`
	CacheFiles      []struct {
		ID   string `json:"id"`
		Text string `json:"text"`
	} `json:"cache_files"`
}

func p3L1StateSnapshot(st *p3State) (json.RawMessage, error) {
	raw, err := json.Marshal(st)
	if err != nil {
		return nil, err
	}
	var next p3State
	if err := json.Unmarshal(raw, &next); err != nil {
		return nil, err
	}
	next.normalize()
	if err := next.validate(); err != nil {
		return nil, err
	}
	*st = next
	return raw, nil
}

func p3RefCacheFile(text string) (map[string]any, error) {
	dir, err := os.MkdirTemp("", "policy3ref-")
	if err != nil {
		return nil, err
	}
	defer os.RemoveAll(dir)
	path := filepath.Join(dir, "cache3.json")
	if err := os.WriteFile(path, []byte(text), 0600); err != nil {
		return nil, err
	}
	c, err := loadDestCache3(path)
	if err != nil {
		return map[string]any{"ok": false}, nil
	}
	c.path = filepath.Join(dir, "saved.json")
	if err := c.save(); err != nil {
		return nil, err
	}
	raw, err := os.ReadFile(c.path)
	if err != nil {
		return nil, err
	}
	var saved any
	if err := json.Unmarshal(raw, &saved); err != nil {
		return nil, err
	}
	return map[string]any{"ok": true, "saved": saved}, nil
}

func p3RunL1Reference(doc *p3L1Reference) (map[string]any, error) {
	arrivals := []any{}
	for _, row := range doc.Arrivals {
		l, err := p3ArrivalLikelihood(row.Sent, row.Lost)
		if err != nil {
			return nil, err
		}
		arrivals = append(arrivals, map[string]any{"likelihood": l})
	}
	classes := []any{}
	for _, row := range doc.Classes {
		c := &row.Ctx
		a := p3Action{row.A[0], row.A[1], row.A[2]}
		first, second, err := p3GradeCutoffs(c, a)
		if err != nil {
			return nil, err
		}
		grades := []int{}
		for _, h := range row.HCT {
			grade, _, _, err := p3ClassifyHCT(c, a, h, true)
			if err != nil {
				return nil, err
			}
			grades = append(grades, grade)
		}
		probs := [][]float64{}
		for g := 0; g < p3NG; g++ {
			q, err := p3ClassProbabilities(c, a, g)
			if err != nil {
				return nil, err
			}
			probs = append(probs, q)
		}
		likelihood := [][]float64{}
		for grade := 0; grade < 3; grade++ {
			l, err := p3ClassLikelihood(c, a, grade)
			if err != nil {
				return nil, err
			}
			likelihood = append(likelihood, l)
		}
		classes = append(classes, map[string]any{"cuts": []float64{first, second}, "grades": grades,
			"probabilities": probs, "likelihood": likelihood})
	}
	observations := []any{}
	for _, series := range doc.Observations {
		st := p3CloneState(&series.Initial)
		st.normalize()
		rows := []any{}
		for i := range series.Rows {
			info, err := series.Rows[i].observe(st)
			if err != nil {
				return nil, fmt.Errorf("observe %s step %d: %w", series.ID, i, err)
			}
			raw, err := p3L1StateSnapshot(st)
			if err != nil {
				return nil, err
			}
			rows = append(rows, map[string]any{"info": p3L1Info(info), "state": raw})
		}
		observations = append(observations, map[string]any{"id": series.ID, "rows": rows})
	}
	sequences := []any{}
	for _, series := range doc.Sequences {
		st := p3CloneState(&series.Initial)
		st.normalize()
		keep := map[int]bool{}
		for _, i := range series.StateAt {
			keep[i] = true
		}
		rows := []any{}
		for i := range series.Rows {
			row := &series.Rows[i]
			d, err := p3Decide(st, row.W, row.U, row.DecideRTT, row.CPkt, false)
			if err != nil {
				return nil, fmt.Errorf("decide %s step %d: %w", series.ID, i, err)
			}
			info, err := row.observe(st)
			if err != nil {
				return nil, fmt.Errorf("observe %s step %d: %w", series.ID, i, err)
			}
			raw, err := p3L1StateSnapshot(st)
			if err != nil {
				return nil, err
			}
			out := map[string]any{"decision": p3RefDecision(d), "info": p3L1Info(info)}
			if keep[i] {
				out["state"] = raw
			}
			rows = append(rows, out)
		}
		sequences = append(sequences, map[string]any{"id": series.ID, "rows": rows})
	}
	caches := []any{}
	for _, series := range doc.Caches {
		cache, err := loadDestCache3("")
		if err != nil {
			return nil, err
		}
		rows := []any{}
		for i := range series.Rows {
			row := &series.Rows[i]
			plan, err := cache.plan(series.ID, row.W, row.U, row.CPkt)
			if err != nil {
				return nil, err
			}
			a := p3Action{row.A[0], row.A[1], row.A[2]}
			hct := math.NaN()
			if row.HCT != nil {
				hct = *row.HCT
			}
			info, after, err := cache.observePred(series.ID, a, row.JPred, hct, row.OK, row.K, row.Srv,
				row.PathRTT, row.PathValid, row.W, row.U, row.CPkt, row.Arrivals)
			if err != nil {
				return nil, fmt.Errorf("cache %s step %d: %w", series.ID, i, err)
			}
			raw, err := json.Marshal(cache.Dests[series.ID])
			if err != nil {
				return nil, err
			}
			var next cache3Entry
			if err := json.Unmarshal(raw, &next); err != nil {
				return nil, err
			}
			next.State.normalize()
			if err := next.validate(); err != nil {
				return nil, err
			}
			cache.commit(series.ID, &next)
			rows = append(rows, map[string]any{"decision": p3RefDecision(plan.Decision), "info": p3L1Info(info),
				"entry": json.RawMessage(raw), "p_after": after})
		}
		caches = append(caches, map[string]any{"id": series.ID, "rows": rows})
	}
	invalid := []bool{}
	for _, raw := range doc.InvalidArrivals {
		var a p3Arrivals
		invalid = append(invalid, json.Unmarshal(raw, &a) != nil)
	}
	invalidStates := []bool{}
	for _, raw := range doc.InvalidStates {
		var st p3State
		err := json.Unmarshal(raw, &st)
		if err == nil {
			st.normalize()
			err = st.validate()
		}
		invalidStates = append(invalidStates, err != nil)
	}
	files := []any{}
	for _, file := range doc.CacheFiles {
		out, err := p3RefCacheFile(file.Text)
		if err != nil {
			return nil, fmt.Errorf("cache file %s: %w", file.ID, err)
		}
		out["id"] = file.ID
		files = append(files, out)
	}
	return map[string]any{"arrivals": arrivals, "classes": classes, "observations": observations,
		"sequences": sequences, "caches": caches, "invalid_arrivals": invalid,
		"invalid_states": invalidStates, "cache_files": files}, nil
}
