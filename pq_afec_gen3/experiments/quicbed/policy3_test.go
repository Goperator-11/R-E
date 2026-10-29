package main

import (
	"bytes"
	"encoding/json"
	"math"
	"math/rand"
	"net"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"testing"
	"time"
)

func p3Close(a, b, tol float64) bool {
	return math.Abs(a-b) <= tol
}

func TestP3GridIsTheTableAxis(t *testing.T) {
	if len(pfailP) != p3NG {
		t.Fatalf("table p axis has %d points, policy3 grid %d", len(pfailP), p3NG)
	}
	for i, p := range pfailP {
		if p3G[i] != p {
			t.Fatalf("grid point %d: policy3 %v, table %v", i, p3G[i], p)
		}
	}
	want := []float64{0.03333333333333333, 0.01, 0.0033333333333333335, 0.001, 0.0003333333333333333}
	for i, h := range want {
		if p3H[i] != h {
			t.Fatalf("hazard %d: %v, want %v", i, p3H[i], h)
		}
	}
}

func TestP3ConstantsAreTheSharedOnes(t *testing.T) {
	c := p3Constants()
	if c["c_pkt"] != 41.983 || c["max_ips"] != 1452 || c["udp_max"] != 1472 ||
		c["j_tie_ms"] != 0.01 || c["t_pto_ms"] != 200.86 || c["t_ack_slope"] != 1.125 ||
		c["t_ack_base_ms"] != 1.424 || c["pto_sampled_mult"] != 3.0 || c["max_steps"] != 2 {
		t.Fatalf("constants drifted: %v", c)
	}
	if !reflect.DeepEqual(c["parity_overhead"], []int{39, 6}) {
		t.Fatalf("parity overhead %v", c["parity_overhead"])
	}
	wantD := []float64{0.0, 0.133, 0.266, 0.355, 0.533, 0.710, 1.066}
	wantQ := []float64{1.0, 0.996, 0.972, 0.640, 0.404, 0.212, 0.004}
	if !reflect.DeepEqual(raceDelayMs, wantD) || !reflect.DeepEqual(raceWinQ, wantQ) {
		t.Fatalf("race table %v %v", raceDelayMs, raceWinQ)
	}
}

func TestP3PySumIsCPythonSum(t *testing.T) {
	tenth := make([]float64, 10)
	for i := range tenth {
		tenth[i] = 0.1
	}
	naive := 0.0
	for _, x := range tenth {
		naive += x
	}
	for _, c := range []struct {
		xs   []float64
		want float64
	}{
		{nil, 0},
		{tenth, 1.0},
		{[]float64{1e100, 1.0, -1e100, 1.0}, 2.0},
		{[]float64{0.3, 0.2, 0.1}, 0.6},
		{[]float64{1e-16, 1.0, 1e-16}, 1.0000000000000002},
		{[]float64{9007199254740992, 1.0, 1.0}, 9007199254740994},
	} {
		if got := p3PySum(c.xs); got != c.want {
			t.Fatalf("p3PySum(%v) = %v, CPython sum %v", c.xs, got, c.want)
		}
	}
	if naive == 1.0 {
		t.Fatal("the naive loop should differ from CPython sum on ten 0.1s")
	}
}

func TestP3EvaluateMassAndEvent(t *testing.T) {
	for k := 1; k <= p3KMax; k++ {
		for m := 0; m <= p3MMax; m++ {
			for lead := 0; lead <= m; lead++ {
				for _, p := range []float64{0, 0.02, 0.15, 0.3} {
					for _, u := range []float64{0, 2, 100} {
						pt := p3Evaluate(k, 1280, m, lead, p, 50, u, 5)
						if !p3Close(pt.P1+pt.P2+pt.PF, 1, 1e-12) {
							t.Fatalf("k%d m%d L%d p%v u%v: mass %v", k, m, lead, p, u, pt.P1+pt.P2+pt.PF)
						}
						if pt.E != pt.P2+pt.PF {
							t.Fatalf("e is not p2 + pf")
						}
						if p == 0 && (pt.PF != 0 || pt.J < 50) {
							t.Fatalf("lossless k%d m%d L%d: pf %v J %v", k, m, lead, pt.PF, pt.J)
						}
					}
				}
			}
		}
	}
}

func TestP3EvaluateMatchesPythonPrimitives(t *testing.T) {
	for _, c := range []struct {
		k, w, m, lead    int
		p, rtt, u        float64
		nNeed            int
		j, e, p2, pf, p1 float64
	}{
		{3, 1281, 0, 0, 0.05, 37.5, 100.0, 15, 88.44377712457208, 0.9999999999999999, 0.8573749999999999, 0.142625, 0.0},
		{2, 1452, 4, 3, 0.12, 10.0, 2.0, 11, 40.79788845577526, 0.041403322368000005, 0.001659322368, 0.039744, 0.958596677632},
		{2, 1350, 4, 2, 0.2625, 10.0, 1.5, 1, 42.40132777525795, 0.05810734863281252, 0.0, 0.05810734863281252, 0.9418926513671877},
		{1, 1280, 4, 0, 0.252512, 50.0, 10.0, 4, 101.83438970118405, 0.9926161357352952, 0.9915895148184967, 0.0010266209167984995, 0.007383864264704742},
		{3, 1201, 1, 1, 0.12, 50.0, 1.5, 13, 187.98096681961943, 1.0, 0.681472, 0.318528, 0.0},
		{3, 1281, 3, 1, 0.08404, 100.0, 5.0, 2, 109.24927385951987, 0.005212433204687288, 0.0, 0.005212433204687288, 0.9947875667953128},
		{4, 1281, 4, 4, 0.041534, 100.0, 100.0, 20, 134.94507990542505, 0.16432803497706355, 0.00825885303661183, 0.15606918194045172, 0.8356719650229368},
		{1, 1350, 3, 2, 0.0, 200.0, 0.0, 1, 200.0, 0.0, 0.0, 0, 1.0},
	} {
		pt := p3Evaluate(c.k, c.w, c.m, c.lead, c.p, c.rtt, c.u, c.nNeed)
		got := []float64{pt.J, pt.E, pt.P2, pt.PF, pt.P1}
		want := []float64{c.j, c.e, c.p2, c.pf, c.p1}
		for i := range got {
			if !p3Close(got[i], want[i], 1e-9) {
				t.Fatalf("%+v field %d: go %v python %v", c, i, got[i], want[i])
			}
		}
	}
}

func TestP3DecisionsMatchPythonSample(t *testing.T) {
	for _, c := range []struct {
		k, w      int
		s, rtt, u float64
		g         []int
		q         []float64
		action    p3Action
		nNeed, n  int
		hash      string
		ej        float64
		nTied     int
		mode      string
	}{
		{4, 1350, 11728.229000000001, 200.0, 100.0, []int{10}, []float64{1.0}, p3Action{0, 0, 4}, 10, 16, "c6fa4aba889370466984775a5a6e3b7ff37ba5ece565e6cad2dd0bb5a4dbaecf", 200.61994613898588, 1, "parity"},
		{2, 1200, 6434.348, 100.0, 10.0, []int{2}, []float64{1.0}, p3Action{0, 0, 2}, 5, 16, "e89f37a8a7fe7143fc318e48f0e0b2925d4f132f9d59812ca582c0f16c602a95", 101.92050930203779, 3, "parity"},
		{2, 1200, 15723.898, 200.0, 2.0, []int{20}, []float64{1.0}, p3Action{55, 3, 1}, 13, 28, "ead0a4faffd0f7c2a4d8af7491f213720b4f7f8e2e1c891b1781798fdf2dd3bb", 308.56507093492513, 1, "combo"},
		{1, 1200, 4797.949, 100.0, 0.0, []int{0}, []float64{1.0}, p3Action{81, 0, 0}, 4, 30, "819555259c00e1f22b4e8d7b304b0bf7f38c642ccc45ea9996a4cbedbc58e1fa", 100.0, 29, "pad"},
		{3, 1280, 7458.847, 200.0, 100.0, []int{0}, []float64{1.0}, p3Action{0, 0, 0}, 6, 17, "1d5f3391c1e4deaf62d0a963901a82eafe108cbb0b5ee573d4ff86e233ebd613", 200.3072, 6, "none"},
		{1, 1200, 15597.949, 100.0, 10.0, []int{0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25}, []float64{0.06503101279892642, 0.07028904107076685, 0.010451972206941898, 0.04577269167765198, 0.0005329923206520032, 0.019181507107660336, 0.061183188071661405, 0.0026221833058007746, 0.0018791695512713398, 0.06747692891820282, 0.029179837828303103, 0.058706501360453016, 0.047030083359234455, 0.05678797610846154, 0.06996924629811822, 0.021650263755264514, 0.04971208910009615, 0.0030634881718954415, 0.06444224602228374, 0.062207509498743804, 0.02247901123650686, 0.01146104068585015, 0.03685426319946053, 0.05500625470600149, 0.03436370204159975, 0.03266579959819148}, p3Action{47, 3, 1}, 13, 25, "1e2fb5f6aadddf30d96c1cf68516516273175fdffebc47a34370931d4b984de9", 142.20137940349358, 1, "combo"},
		{2, 1280, 12523.898, 50.0, 2.0, []int{5, 19}, []float64{0.19947915192038704, 0.800520848079613}, p3Action{0, 2, 2}, 10, 16, "68d0171ad8df1fcb348bac00b629431128c6a9c42d97503c244a56f09a3ae2a1", 75.94417557764409, 1, "parity"},
	} {
		post := make([]float64, p3NG)
		for i, g := range c.g {
			post[g] = c.q[i]
		}
		d, err := p3DecideCore(post, c.k, c.w, c.s, c.u, c.rtt, cPktDefault, false)
		if err != nil {
			t.Fatal(err)
		}
		if d.Action != c.action || d.NNeed != c.nNeed || d.NCands != c.n || d.CandHash != c.hash ||
			d.NTied != c.nTied || d.Mode != c.mode || !p3Close(d.EJ, c.ej, 1e-9) {
			t.Fatalf("k%d W%d S%v: go %+v %d %d %s ej %v tied %d %s", c.k, c.w, c.s, d.Action,
				d.NNeed, d.NCands, d.CandHash, d.EJ, d.NTied, d.Mode)
		}
	}
}

func TestP3CandidatesContainGen2Actions(t *testing.T) {
	for k := 1; k <= p3KMax; k++ {
		for _, w := range []int{1200, 1280, 1350} {
			for _, cert := range []int{1000, 4032, 9000, 16000} {
				s := float64(cert) + 1472.0 + float64(binIndex(k*w))*cPktDefault
				cands := p3Candidates(k, w, s, cPktDefault)
				have := map[p3Action]bool{}
				for _, c := range cands {
					if have[c.Action] {
						t.Fatalf("duplicate candidate %+v", c.Action)
					}
					have[c.Action] = true
					if c.M > p3MMax || c.WEff > quicgoMaxIPS {
						t.Fatalf("candidate out of bounds %+v", c)
					}
				}
				for _, g := range levers(k, w, maxStepsDefault, mMaxDefault, s, cPktDefault, quicgoMaxIPS) {
					if g.wEff > quicgoMaxIPS || (g.m > 0 && parityDatagramBytes(g.wEff, k) > p3UDPMax) {
						continue
					}
					a := p3Action{Delta: g.delta, Lead: p3LegacyLead(g.m), T: g.m - p3LegacyLead(g.m)}
					if !have[a] {
						t.Fatalf("k%d W%d cert%d: gen-2 action %+v missing", k, w, cert, a)
					}
				}
			}
		}
	}
}

func TestP3PointPosteriorPicksTheTieRuleArgmin(t *testing.T) {
	for g := 0; g < p3NG; g += 5 {
		post := make([]float64, p3NG)
		post[g] = 1
		s := 16000 + 1472.0 + float64(binIndex(2*1280))*cPktDefault
		d, err := p3DecideCore(post, 2, 1280, s, 2, 50, cPktDefault, true)
		if err != nil {
			t.Fatal(err)
		}
		jmin := math.Inf(1)
		for _, c := range d.Cands {
			j := p3ModelPoint(2, c.WEff, 2, 50, d.NNeed, c.Action.Lead, c.M, g).J
			if j != c.EJ {
				t.Fatalf("point posterior EJ %v != J %v", c.EJ, j)
			}
			jmin = math.Min(jmin, j)
		}
		var tied []p3Cand
		for _, c := range d.Cands {
			if c.EJ <= jmin+jTieMs {
				tied = append(tied, c)
			}
		}
		sort.SliceStable(tied, func(i, j int) bool { return p3TieLess(&tied[i], &tied[j]) })
		if tied[0].Action != d.Action || d.JMin != jmin {
			t.Fatalf("g %d: picked %+v, tie-rule argmin %+v", g, d.Action, tied[0].Action)
		}
	}
}

func TestP3ModeRecentAndMedian(t *testing.T) {
	if k, _ := p3ModeRecent([]int{2, 2, 3, 3}); k != 3 {
		t.Fatalf("tied mode should be the most recent value, got %d", k)
	}
	if k, _ := p3ModeRecent([]int{2, 2, 2, 3}); k != 2 {
		t.Fatalf("mode %d", k)
	}
	if _, ok := p3ModeRecent(nil); ok {
		t.Fatal("empty mode")
	}
	if m := p3Median([]float64{4, 1, 3, 2}); m != 2.5 {
		t.Fatalf("even median %v", m)
	}
	if m := p3Median([]float64{5, 1, 3}); m != 3 {
		t.Fatalf("odd median %v", m)
	}
}

func p3TestFeed(st *p3State, a p3Action, n int, hct float64, rtt float64) {
	for i := 0; i < n; i++ {
		p3Observe(st, a, hct, true, 2, 18000, rtt, 1280, 2, cPktDefault)
	}
}

func TestP3ColdStartAndExit(t *testing.T) {
	st := newP3State()
	d, err := p3Decide(st, 1280, 2, 50, cPktDefault, false)
	if err != nil || d.Action != (p3Action{}) || d.Why != "cold" || d.HasEJ {
		t.Fatalf("cold decision %+v %v", d, err)
	}
	info, err := p3Observe(st, p3Action{}, 105, true, 2, 18000, 50, 1280, 2, cPktDefault)
	if err != nil || info.Y != -1 || info.Updated || len(st.SHist) != 1 || len(st.KHist) != 1 {
		t.Fatalf("first observation %+v %v state %+v", info, err, st)
	}
	d, err = p3Decide(st, 1280, 2, 50, cPktDefault, false)
	if err != nil || d.Why != "ej" || !d.HasEJ {
		t.Fatalf("second decision %+v %v", d, err)
	}
	if d, _ := p3Decide(st, 1280, 2, 0, cPktDefault, false); d.Why != "no_rtt" {
		t.Fatalf("rtt 0 decision %+v", d)
	}
	st.KHist = []int{5}
	if d, _ := p3Decide(st, 1280, 2, 50, cPktDefault, false); d.Why != "k_range" {
		t.Fatalf("k 5 decision %+v", d)
	}
}

func TestP3PosteriorStaysNormalised(t *testing.T) {
	rng := rand.New(rand.NewSource(7))
	st := newP3State()
	arms := []p3Action{{0, 0, 0}, {0, 1, 2}, {0, 3, 1}, {0, 0, 4}}
	for i := 0; i < 400; i++ {
		a := arms[rng.Intn(len(arms))]
		hct := 55 + rng.Float64()*3
		if rng.Float64() < 0.2 {
			hct += 50
		}
		ok := rng.Float64() > 0.01
		if _, err := p3Observe(st, a, hct, ok, 2, 18000+float64(rng.Intn(50)), 50, 1280, 2, cPktDefault); err != nil {
			t.Fatal(err)
		}
		for j, row := range st.Post {
			s := 0.0
			for _, x := range row {
				s += x
			}
			if !p3Close(s, 1, 1e-12) {
				t.Fatalf("step %d posterior %d sums to %v", i, j, s)
			}
		}
		s := 0.0
		for _, x := range st.W {
			s += x
			if x < p3WFloor*(1-1e-9) {
				t.Fatalf("weight %v under the floor", x)
			}
		}
		if !p3Close(s, 1, 1e-12) {
			t.Fatalf("weights sum to %v", s)
		}
	}
	if st.Stats.Upd == 0 || st.Stats.Events == 0 {
		t.Fatalf("no updates %+v", st.Stats)
	}
}

func TestP3ShieldedObservationLeavesThePosterior(t *testing.T) {
	st := newP3State()
	a := p3Action{0, 0, 4}
	for i := 0; i < 10; i++ {
		p3Observe(st, a, 410, true, 2, 31500, 200, 1280, 5, cPktDefault)
	}
	before, _ := json.Marshal(st.Post)
	wb, _ := json.Marshal(st.W)
	info, err := p3Observe(st, a, 700, true, 2, 31500, 200, 1280, 5, cPktDefault)
	if err != nil || !info.Shielded || info.Updated || info.Y != 1 {
		t.Fatalf("shield %+v %v", info, err)
	}
	after, _ := json.Marshal(st.Post)
	wa, _ := json.Marshal(st.W)
	if !bytes.Equal(before, after) || !bytes.Equal(wb, wa) || st.Stats.Upd != 0 {
		t.Fatal("shielded observation moved the posterior")
	}
}

func TestP3FailedConnectionCountsButIsNotWindowed(t *testing.T) {
	st := newP3State()
	a := p3Action{0, 3, 1}
	p3TestFeed(st, a, 8, 60, 50)
	k, s, h := len(st.KHist), len(st.SHist), len(st.HCT[a.Key()])
	info, err := p3Observe(st, a, math.NaN(), false, 0, 0, 50, 1280, 2, cPktDefault)
	if err != nil || info.Y != 1 || !info.Updated {
		t.Fatalf("failed observation %+v %v", info, err)
	}
	if len(st.KHist) != k || len(st.SHist) != s || len(st.HCT[a.Key()]) != h || st.Stats.Fail != 1 {
		t.Fatalf("failed observation entered a window")
	}
	if _, err := p3Observe(st, a, 0, true, 2, 1, 50, 1280, 2, cPktDefault); err == nil {
		t.Fatal("ok observation with hct 0 accepted")
	}
}

func TestP3OutlierDoesNotMoveTheBaseline(t *testing.T) {
	st := newP3State()
	a := p3Action{0, 3, 1}
	p3TestFeed(st, a, 15, 60, 50)
	b0, _, _ := p3Baseline(st, nil, a)
	p3Observe(st, a, 82.4, true, 2, 18000, 50, 1280, 2, cPktDefault)
	b1, _, _ := p3Baseline(st, nil, a)
	if b0 != 60 || b1 != 60 {
		t.Fatalf("baseline %v -> %v", b0, b1)
	}
}

func TestP3BaselineTransfer(t *testing.T) {
	st := newP3State()
	ref := p3Action{0, 1, 2}
	p3TestFeed(st, ref, 9, 105, 50)
	c, ok := p3Context(st, 1280, 2, 50, cPktDefault)
	if !ok {
		t.Fatal("no context")
	}
	a := p3Action{0, 3, 1}
	b, r, ok := p3Baseline(st, c, a)
	want := float64(105+c.point(a, 0).J) - c.point(ref, 0).J
	if !ok || r != ref.Key() || b != want {
		t.Fatalf("transfer %v %s %v, want %v", b, r, ok, want)
	}
}

func TestP3StateAndCacheRoundTrip(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "c3.json")
	c, err := loadDestCache3(path)
	if err != nil {
		t.Fatal(err)
	}
	addr := "10.0.0.2:44434"
	for i := 0; i < 40; i++ {
		p, err := c.plan(addr, 1280, 2, cPktDefault)
		if err != nil {
			t.Fatal(err)
		}
		hct := 60.0 + float64(i%7)
		if p.M == 0 {
			hct += 50
		}
		if _, _, err := c.observe(addr, p.Action, hct, true, 2, 18000, 50.5, true, 1280, 2, cPktDefault); err != nil {
			t.Fatal(err)
		}
	}
	if err := c.save(); err != nil {
		t.Fatal(err)
	}
	c2, err := loadDestCache3(path)
	if err != nil {
		t.Fatal(err)
	}
	a, _ := json.Marshal(c.Dests)
	b, _ := json.Marshal(c2.Dests)
	if !bytes.Equal(a, b) {
		t.Fatal("cache3 round trip changed the state")
	}
	p1, _ := c.plan(addr, 1280, 2, cPktDefault)
	p2, _ := c2.plan(addr, 1280, 2, cPktDefault)
	if p1.Action != p2.Action || p1.Decision.EJ != p2.Decision.EJ || p1.RTT != 50.5 {
		t.Fatalf("reloaded plan %+v vs %+v", p1, p2)
	}
	raw, _ := os.ReadFile(path)
	for _, bad := range []string{
		strings.Replace(string(raw), p3CacheSchema, "padfec3.cache3/0", 1),
		strings.Replace(string(raw), `"v":1`, `"v":2`, 1),
		strings.Replace(string(raw), `"hct":{"`, `"hct":{"9,9,9":[1],"`, 1),
		`{"schema":"padfec3.cache3/1","dests":{"x":{"state":null}}}`,
		`{"schema":"padfec3.cache3/1","dests":{},"extra":1}`,
	} {
		if err := os.WriteFile(path, []byte(bad), 0644); err != nil {
			t.Fatal(err)
		}
		if _, err := loadDestCache3(path); err == nil {
			t.Fatalf("corrupt cache3 accepted: %.80s", bad)
		}
	}
	empty, err := loadDestCache3(filepath.Join(dir, "missing.json"))
	if err != nil || len(empty.Dests) != 0 {
		t.Fatalf("missing cache3 %v %v", empty, err)
	}
}

func TestP3StateJSONMatchesPythonKeys(t *testing.T) {
	raw, _ := json.Marshal(newP3State())
	var m map[string]json.RawMessage
	json.Unmarshal(raw, &m)
	var keys []string
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	want := []string{"S_hist", "hct", "hct_seq", "k_hist", "post", "seq", "stats", "v", "w"}
	if !reflect.DeepEqual(keys, want) {
		t.Fatalf("state keys %v", keys)
	}
	if string(m["hct"]) != "{}" || string(m["k_hist"]) != "[]" || string(m["S_hist"]) != "[]" {
		t.Fatalf("empty containers encode as %s %s %s", m["hct"], m["k_hist"], m["S_hist"])
	}
}

func TestAuto3FlagChecks(t *testing.T) {
	for _, c := range []struct {
		set    bool
		layout string
		lead   int
		ips    int
		ok     bool
	}{
		{false, "v2", -1, 0, true},
		{true, "v3", -1, 0, true},
		{true, "v2", -1, 0, false},
		{false, "v2", 2, 0, false},
		{false, "v2", -1, 1350, true},
		{false, "v2", -1, 1452, true},
		{false, "v2", -1, 1453, false},
		{false, "v2", -1, 1100, false},
	} {
		err := checkAuto3Flags(c.set, c.layout, c.lead, c.ips)
		if (err == nil) != c.ok {
			t.Errorf("%+v: %v", c, err)
		}
	}
	if err := checkLayoutFlags("v3", 1, "auto3", 3); err == nil {
		t.Error("checkLayoutFlags accepted -fec auto3")
	}
}

func TestAuto3PlanDrivesTheV3Transport(t *testing.T) {
	gfInit()
	addr := &net.UDPAddr{IP: net.IPv4(10, 9, 0, 2), Port: 44434}
	for _, a := range []p3Action{{0, 0, 0}, {37, 0, 0}, {0, 0, 1}, {0, 1, 0}, {0, 3, 1}, {0, 2, 2}, {0, 0, 4}, {12, 1, 3}, {0, 4, 0}} {
		k := 2
		p := auto3PlanFor(p3Decision{Action: a, HasEJ: true, EJ: 1}, 1280, 50, "quic_ack_min_rtt")
		if p.IPS != 1280+a.Delta || p.M != a.M() || p.Lead != a.Lead {
			t.Fatalf("%+v: plan %+v", a, p)
		}
		if (p.FecMode == "fec") != (a.M() > 0) {
			t.Fatalf("%+v: fec mode %s", a, p.FecMode)
		}
		wire := &auditConn{scriptConn: scriptConn{addr: addr}}
		fc := &fecConn{mode: p.FecMode, m: maxInt(p.M, 1), layout: "v3", lead: p.Lead,
			expectK: k, dropParity: -1, corruptParity: -1, parityDelay: time.Hour}
		fc.PacketConn = wire
		var src [][]byte
		for i := 0; i < k; i++ {
			d := leadTestInitial(leadTestDCID, leadTestSCID, 1200, byte(i))
			src = append(src, d)
			fc.WriteTo(d, addr)
		}
		w := wire.written
		if len(w) != k+a.M() {
			t.Fatalf("%+v: %d datagrams, want %d", a, len(w), k+a.M())
		}
		for x, d := range w {
			if x >= a.Lead && x < a.Lead+k {
				if !bytes.Equal(d, src[x-a.Lead]) {
					t.Fatalf("%+v: slot %d is not original %d", a, x, x-a.Lead)
				}
				continue
			}
			fb := leadParseWire(t, d)
			if fb.ver != fecVerLead || fb.lead != a.Lead || fb.m != a.M() || fb.k != k {
				t.Fatalf("%+v slot %d: %+v", a, x, fb)
			}
			if (x < a.Lead) != isCreditParity(fb) {
				t.Fatalf("%+v slot %d: credit flag wrong", a, x)
			}
		}
		st := fc.snapshot()
		if st.Layout != "v3" || st.Lead != a.Lead || st.FirstFlightLeadDgrams != a.Lead || st.FirstFlightParity != a.M() {
			t.Fatalf("%+v: stats %+v", a, st)
		}
	}
}

func TestAuto3RowAddsFieldsAndLeavesTrialAlone(t *testing.T) {
	raw, _ := json.Marshal(&trial{})
	var plain map[string]any
	json.Unmarshal(raw, &plain)
	wantPlain := []string{"cipher_id", "first_flight_bytes", "first_flight_datagrams",
		"first_flight_lead_dgrams", "first_flight_parity_bytes", "first_flight_parity_dgrams",
		"group", "i", "initial_datagrams", "ips_eff", "ips_used", "kem_id", "later_parity_sent",
		"layout", "lead", "loss_event", "m_used", "ms", "ok", "parity_sent", "path_rtt_ms",
		"path_rtt_source", "path_rtt_valid", "server_bytes"}
	var got []string
	for k := range plain {
		got = append(got, k)
	}
	sort.Strings(got)
	if !reflect.DeepEqual(got, wantPlain) {
		t.Fatalf("gen-2 trial row keys changed: %v", got)
	}
	cold := auto3Row(trial{Layout: "v3"}, auto3PlanFor(p3B0("cold", make([]float64, p3NG)), 1280, 0, "none"),
		p3ObsInfo{Y: -1}, nil, 0.13)
	raw, _ = json.Marshal(&cold)
	var r map[string]any
	json.Unmarshal(raw, &r)
	if r["j3_ms"] != nil || !reflect.DeepEqual(r["action"], []any{0.0, 0.0, 0.0}) || r["layout"] != "v3" ||
		r["p_mean"] == nil || r["why3"] != "cold" {
		t.Fatalf("cold row %s", raw)
	}
	d := p3Decision{Action: p3Action{0, 3, 1}, HasEJ: true, EJ: 81.5, JMin: 81.4, PMean: 0.05,
		Why: "ej", Mode: "parity", K: 2, S: 18000, NNeed: 15}
	hot := auto3Row(trial{Layout: "v3", Lead: 3}, auto3PlanFor(d, 1280, 50, "quic_ack_min_rtt"),
		p3ObsInfo{Y: 0, Updated: true, HasBase: true, Baseline: 81}, nil, 0.049)
	raw, _ = json.Marshal(&hot)
	r = map[string]any{}
	json.Unmarshal(raw, &r)
	if r["j3_ms"] != 81.5 || !reflect.DeepEqual(r["action"], []any{0.0, 3.0, 1.0}) || r["p_mean"] != 0.05 ||
		r["obs_y"] != 0.0 || r["lead"] != 3.0 || r["n_need"] != 15.0 {
		t.Fatalf("decided row %s", raw)
	}
}
