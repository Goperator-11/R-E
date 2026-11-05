package main

import (
	"bytes"
	"encoding/json"
	"math"
	"path/filepath"
	"reflect"
	"testing"
)

func p3TestCategoricalPost(t *testing.T, st *p3State, a p3Action, hct float64, ok bool, rtt, u float64) ([][]float64, []float64) {
	t.Helper()
	c, has := p3Context(st, 1280, u, rtt, cPktDefault)
	if !has {
		t.Fatal("categorical fixture has no context")
	}
	grade, _, _, err := p3ClassifyHCT(c, a, hct, ok)
	if err != nil {
		t.Fatal(err)
	}
	l, err := p3ClassLikelihood(c, a, grade)
	if err != nil {
		t.Fatal(err)
	}
	post, weights := p3FilterStep(st.Post, st.W, l)
	return post, weights
}

func TestP3L1ArrivalFailureAndNoContext(t *testing.T) {
	st := newP3State()
	arr := &p3Arrivals{Src: "c1", Sent: 3, Lost: 1, Bitmap: []int{1, 0, 1}}
	l, err := p3ArrivalLikelihood(3, 1)
	if err != nil {
		t.Fatal(err)
	}
	wantPost, wantW := p3FilterStep(st.Post, st.W, l)
	info, err := p3Observe(st, p3Action{}, math.NaN(), false, 0, 0, 0, 1280, 2, cPktDefault, nil, arr)
	if err != nil || !info.Updated || info.HasCtx || info.Grade != 2 || info.LossUpdateKind != "datagram" ||
		!reflect.DeepEqual(st.Post, wantPost) || !reflect.DeepEqual(st.W, wantW) {
		t.Fatalf("failed cold arrival %+v %v", info, err)
	}
	arr.Bitmap[0] = 0
	if info.Evidence.Bitmap[0] != 1 {
		t.Fatal("arrival bitmap aliases caller")
	}
	if st.Stats.ArrSent != 3 || st.Stats.ArrLost != 1 || st.Stats.GradeLate != 1 || st.Stats.Predict != 1 {
		t.Fatal(st.Stats)
	}
}

func TestP3L1InvalidArrivalAndLateFailureAreAtomic(t *testing.T) {
	st := p3PointState(2, 1280, 9000, p3GIndex(0.02))
	before, _ := json.Marshal(st)
	bad := []*p3Arrivals{{Src: "bad"}, {Src: "c1", Sent: -1}, {Src: "c1", Sent: 2, Lost: 3},
		{Src: "ack", Sent: 9}, {Src: "c1", Sent: 2, Lost: 1, Bitmap: []int{1, 1}}}
	for _, arr := range bad {
		if _, err := p3Observe(st, p3Action{}, 80, true, 2, 8500, 50, 1280, 2, cPktDefault, nil, arr); err == nil {
			t.Fatal("bad arrival accepted", arr)
		}
		after, _ := json.Marshal(st)
		if !bytes.Equal(before, after) {
			t.Fatal("bad arrival mutated state")
		}
	}
	if _, err := p3Observe(st, p3Action{}, 80, true, 2, 8500, 50, 1280, 2, cPktDefault, nil, nil, nil); err == nil {
		t.Fatal("multiple arrivals accepted")
	}
	st.GResid["0,0,0"] = []float64{math.MaxFloat64}
	st.GCommon = []float64{}
	before, _ = json.Marshal(st)
	jp := math.MaxFloat64
	if _, err := p3Observe(st, p3Action{0, 1, 0}, 1, true, 2, 8500, 50, 1280, 2, cPktDefault, &jp); err == nil {
		t.Fatal("overflow accepted")
	}
	after, _ := json.Marshal(st)
	if !bytes.Equal(before, after) {
		t.Fatal("late error mutated state")
	}
}

func TestP3L1CacheArrivalsPersistAndRejectAtomically(t *testing.T) {
	path := filepath.Join(preservedTempDir(t), "cache.json")
	c, err := loadDestCache3(path)
	if err != nil {
		t.Fatal(err)
	}
	arr := &p3Arrivals{Src: "ack", Sent: 2, Lost: 1}
	if _, _, err := c.observe("x", p3Action{}, 80, true, 2, 8500, 50, true, 1280, 2, cPktDefault, arr); err != nil {
		t.Fatal(err)
	}
	before, _ := json.Marshal(c.Dests)
	arr.Lost = 3
	if _, _, err := c.observe("x", p3Action{}, 70, true, 2, 8500, 40, true, 1280, 2, cPktDefault, arr); err == nil {
		t.Fatal("bad cache arrival accepted")
	}
	after, _ := json.Marshal(c.Dests)
	if !bytes.Equal(before, after) {
		t.Fatal("cache metadata or posterior mutated on error")
	}
	if err := c.save(); err != nil {
		t.Fatal(err)
	}
	reloaded, err := loadDestCache3(path)
	if err != nil {
		t.Fatal(err)
	}
	raw, _ := json.Marshal(reloaded.Dests)
	if !bytes.Equal(before, raw) {
		t.Fatal("cache round trip differs")
	}
	if reloaded.Dests["x"].State.Stats.ArrACK != 1 || reloaded.Dests["x"].State.Stats.Datagram != 1 {
		t.Fatal("missing L1 cache counters")
	}
}

func TestP3L1RejectsNullJSONFieldsAndOldStates(t *testing.T) {
	for _, raw := range []string{
		`{"src":"c1","sent":null,"lost":0,"bitmap":null,"trunc":false}`,
		`{"src":"c1","sent":1,"lost":0,"bitmap":[null],"trunc":false}`,
		`{"src":"c1","sent":1,"lost":0,"bitmap":[true],"trunc":false}`,
		`{"src":"c1","sent":true,"lost":0,"bitmap":null,"trunc":false}`,
	} {
		var a p3Arrivals
		if err := json.Unmarshal([]byte(raw), &a); err == nil {
			t.Fatal("bad JSON accepted", raw)
		}
	}
	for _, v := range []int{1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12} {
		st := newP3State()
		st.V = v
		if err := st.validate(); err == nil {
			t.Fatal("foreign state accepted", v)
		}
	}
	st := newP3State()
	st.Stats.ArrLost = -1
	if err := st.validate(); err == nil {
		t.Fatal("negative new counter accepted")
	}
}
