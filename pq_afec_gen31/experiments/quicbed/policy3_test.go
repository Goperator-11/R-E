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
		{2, 1200, 15723.898, 200.0, 2.0, []int{20}, []float64{1.0}, p3Action{0, 3, 1}, 13, 28, "ead0a4faffd0f7c2a4d8af7491f213720b4f7f8e2e1c891b1781798fdf2dd3bb", 388.6937355289787, 1, "parity"},
		{1, 1200, 4797.949, 100.0, 0.0, []int{0}, []float64{1.0}, p3Action{81, 0, 0}, 4, 30, "819555259c00e1f22b4e8d7b304b0bf7f38c642ccc45ea9996a4cbedbc58e1fa", 100.0, 29, "pad"},
		{3, 1280, 7458.847, 200.0, 100.0, []int{0}, []float64{1.0}, p3Action{0, 0, 0}, 6, 17, "1d5f3391c1e4deaf62d0a963901a82eafe108cbb0b5ee573d4ff86e233ebd613", 200.3072, 6, "none"},
		{1, 1200, 15597.949, 100.0, 10.0, []int{0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25}, []float64{0.06503101279892642, 0.07028904107076685, 0.010451972206941898, 0.04577269167765198, 0.0005329923206520032, 0.019181507107660336, 0.061183188071661405, 0.0026221833058007746, 0.0018791695512713398, 0.06747692891820282, 0.029179837828303103, 0.058706501360453016, 0.047030083359234455, 0.05678797610846154, 0.06996924629811822, 0.021650263755264514, 0.04971208910009615, 0.0030634881718954415, 0.06444224602228374, 0.062207509498743804, 0.02247901123650686, 0.01146104068585015, 0.03685426319946053, 0.05500625470600149, 0.03436370204159975, 0.03266579959819148}, p3Action{47, 3, 1}, 13, 25, "1e2fb5f6aadddf30d96c1cf68516516273175fdffebc47a34370931d4b984de9", 142.20137940349358, 1, "combo"},
		{2, 1280, 12523.898, 50.0, 2.0, []int{5, 19}, []float64{0.19947915192038704, 0.800520848079613}, p3Action{0, 2, 2}, 10, 16, "68d0171ad8df1fcb348bac00b629431128c6a9c42d97503c244a56f09a3ae2a1", 75.94417557764409, 1, "parity"},
	} {
		post := make([]float64, p3NG)
		for i, g := range c.g {
			post[g] = c.q[i]
		}
		d, err := p3DecideCore(post, c.k, c.w, c.s, c.u, c.rtt, cPktDefault, false, nil, false)
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
		d, err := p3DecideCore(post, 2, 1280, s, 2, 50, cPktDefault, true, nil, false)
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
		p3Observe(st, a, hct, true, 2, 18000, rtt, 1280, 2, cPktDefault, nil)
	}
}

func TestP3ColdStartAndExit(t *testing.T) {
	st := newP3State()
	d, err := p3Decide(st, 1280, 2, 50, cPktDefault, false)
	if err != nil || d.Action != (p3Action{}) || d.Why != "cold" || d.HasEJ {
		t.Fatalf("cold decision %+v %v", d, err)
	}
	info, err := p3Observe(st, p3Action{}, 105, true, 2, 18000, 50, 1280, 2, cPktDefault, nil)
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
		if _, err := p3Observe(st, a, hct, ok, 2, 18000+float64(rng.Intn(50)), 50, 1280, 2, cPktDefault, nil); err != nil {
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
		p3Observe(st, a, 410, true, 2, 31500, 200, 1280, 5, cPktDefault, nil)
	}
	before, _ := json.Marshal(st.Post)
	wb, _ := json.Marshal(st.W)
	info, err := p3Observe(st, a, 700, true, 2, 31500, 200, 1280, 5, cPktDefault, nil)
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
	info, err := p3Observe(st, a, math.NaN(), false, 0, 0, 50, 1280, 2, cPktDefault, nil)
	if err != nil || info.Y != 1 || !info.Updated {
		t.Fatalf("failed observation %+v %v", info, err)
	}
	if len(st.KHist) != k || len(st.SHist) != s || len(st.HCT[a.Key()]) != h || st.Stats.Fail != 1 {
		t.Fatalf("failed observation entered a window")
	}
	if _, err := p3Observe(st, a, 0, true, 2, 1, 50, 1280, 2, cPktDefault, nil); err == nil {
		t.Fatal("ok observation with hct 0 accepted")
	}
}

func TestP3OutlierDoesNotMoveTheBaseline(t *testing.T) {
	st := newP3State()
	a := p3Action{0, 3, 1}
	p3TestFeed(st, a, 15, 60, 50)
	b0, _, _ := p3Baseline(st, nil, a)
	p3Observe(st, a, 82.4, true, 2, 18000, 50, 1280, 2, cPktDefault, nil)
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
		if _, _, err := c.observePred(addr, p.Action, p.jPred(), hct, true, 2, 18000, 50.5, true, 1280, 2, cPktDefault); err != nil {
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
	sep := func(empty string) string {
		if strings.Contains(string(raw), empty) {
			return ""
		}
		return ","
	}
	long := strings.TrimSuffix(strings.Repeat("1,", p3GuardCommonWin+1), ",")
	for _, bad := range []string{
		strings.Replace(string(raw), p3CacheSchema, "padfec3.cache3/0", 1),
		strings.Replace(string(raw), `"v":2`, `"v":1`, 1),
		strings.Replace(string(raw), `"g_alarm":{`, `"g_alarm":{"9,9":3`+sep(`"g_alarm":{}`), 1),
		strings.Replace(string(raw), `"g_resid":{`, `"g_resid":{"0,0,9":[1]`+sep(`"g_resid":{}`), 1),
		strings.Replace(string(raw), `"g_common":[`, `"g_common":[`+long+sep(`"g_common":[]`), 1),
		strings.Replace(string(raw), `"n_dec":`, `"n_dec":-`, 1),
		strings.Replace(string(raw), `"hct":{"`, `"hct":{"9,9,9":[1],"`, 1),
		`{"schema":"` + p3CacheSchema + `","dests":{"x":{"state":null}}}`,
		`{"schema":"` + p3CacheSchema + `","dests":{},"extra":1}`,
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
	want := []string{"S_hist", "g_alarm", "g_common", "g_resid", "hct", "hct_seq", "k_hist", "n_dec",
		"n_reeval", "post", "seq", "stats", "v", "w"}
	if !reflect.DeepEqual(keys, want) {
		t.Fatalf("state keys %v", keys)
	}
	if string(m["hct"]) != "{}" || string(m["k_hist"]) != "[]" || string(m["S_hist"]) != "[]" ||
		string(m["g_resid"]) != "{}" || string(m["g_common"]) != "[]" || string(m["g_alarm"]) != "{}" ||
		string(m["v"]) != "2" {
		t.Fatalf("empty containers encode as %s %s %s %s %s %s v %s", m["hct"], m["k_hist"], m["S_hist"],
			m["g_resid"], m["g_common"], m["g_alarm"], m["v"])
	}
	var stats map[string]int
	json.Unmarshal(m["stats"], &stats)
	var sk []string
	for k := range stats {
		sk = append(sk, k)
	}
	sort.Strings(sk)
	wantStats := []string{"alarm_cleared", "alarm_raised", "events", "fail", "guard", "no_base", "no_ctx",
		"nominal2", "obs", "reeval", "resid", "shield", "upd"}
	if !reflect.DeepEqual(sk, wantStats) {
		t.Fatalf("stats keys %v", sk)
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
	for _, k := range []string{"j3_pred_pre_ms", "guard_alarm", "guard_resid_ms", "guard_common_ms",
		"guard_alarmed_actions", "reeval", "policy_version", "obs_skip"} {
		if _, ok := r[k]; !ok {
			t.Fatalf("cold row has no %s: %s", k, raw)
		}
	}
	if r["j3_pred_pre_ms"] != nil || r["guard_resid_ms"] != nil || r["guard_alarm"] != false ||
		r["guard_common_ms"] != 0.0 || r["guard_alarmed_actions"] != 0.0 || r["reeval"] != false ||
		r["policy_version"] != "v3.1" || r["obs_skip"] != nil {
		t.Fatalf("cold row guard fields %s", raw)
	}
	d := p3Decision{Action: p3Action{0, 3, 1}, HasEJ: true, EJ: 81.5, JMin: 81.4, PMean: 0.05,
		Why: "ej", Mode: "parity", K: 2, S: 18000, NNeed: 15}
	hot := auto3Row(trial{Layout: "v3", Lead: 3}, auto3PlanFor(d, 1280, 50, "quic_ack_min_rtt"),
		p3ObsInfo{Y: 0, Updated: true, HasBase: true, Baseline: 81}, nil, 0.049)
	raw, _ = json.Marshal(&hot)
	r = map[string]any{}
	json.Unmarshal(raw, &r)
	if r["j3_ms"] != 81.5 || !reflect.DeepEqual(r["action"], []any{0.0, 3.0, 1.0}) || r["p_mean"] != 0.05 ||
		r["obs_y"] != 0.0 || r["lead"] != 3.0 || r["n_need"] != 15.0 || r["j3_pred_pre_ms"] != 81.5 ||
		r["guard_resid_ms"] != nil || r["policy_version"] != "v3.1" {
		t.Fatalf("decided row %s", raw)
	}
	d.Why, d.Reeval, d.GuardAlarm, d.GuardCommon, d.GuardAlarmed, d.Pen = "reeval", true, true, 2.5, 3, 7.25
	g := auto3Row(trial{Ms: 84.75, OK: true, Layout: "v3", Lead: 3}, auto3PlanFor(d, 1280, 50, "quic_ack_min_rtt"),
		p3ObsInfo{Y: 0, HasBase: true, Baseline: 81, HasResid: true, Resid: 3.25, Skip: p3SkipGuard}, nil, 0.049)
	raw, _ = json.Marshal(&g)
	r = map[string]any{}
	json.Unmarshal(raw, &r)
	if r["why3"] != "reeval" || r["reeval"] != true || r["guard_alarm"] != true || r["guard_common_ms"] != 2.5 ||
		r["guard_alarmed_actions"] != 3.0 || r["guard_resid_ms"] != 3.25 || r["obs_skip"] != "guard" ||
		r["obs_shielded"] != false || r["j3_pred_pre_ms"] != 81.5 || r["j3_ms"] != 81.5 {
		t.Fatalf("guarded row %s", raw)
	}
	if w := auto3PlanFor(d, 1280, 50, "quic_ack_min_rtt").Why; !strings.Contains(w, "reeval") ||
		!strings.Contains(w, "pen=7.250ms") {
		t.Fatalf("plan why %q", w)
	}
}

func p3SynthS(cert, k, w int) float64 {
	return float64(cert) + 1472.0 + float64(binIndex(k*w))*cPktDefault
}

func p3Feed(st *p3State, a p3Action, hcts []float64, jPred *float64, cert int, rtt, u float64) []p3ObsInfo {
	s := p3SynthS(cert, 2, 1280)
	out := make([]p3ObsInfo, 0, len(hcts))
	for _, h := range hcts {
		info, err := p3Observe(st, a, h, true, 2, s, rtt, 1280, u, cPktDefault, jPred)
		if err != nil {
			panic(err)
		}
		out = append(out, info)
	}
	return out
}

func p3FeedG(st *p3State, a p3Action, hcts []float64, jPred float64) []p3ObsInfo {
	return p3Feed(st, a, hcts, &jPred, 9000, 50, 2)
}

func p3Rep(x float64, n int) []float64 {
	out := make([]float64, n)
	for i := range out {
		out[i] = x
	}
	return out
}

func p3PointState(k, w, cert, g int) *p3State {
	st := newP3State()
	st.KHist = []int{k}
	st.SHist = []float64{p3SynthS(cert, k, w)}
	p3SetPoint(st, g)
	st.W = []float64{1, 0, 0, 0, 0}
	return st
}

func p3SetPoint(st *p3State, g int) {
	for j := range st.Post {
		for i := range st.Post[j] {
			st.Post[j][i] = 0
		}
		st.Post[j][g] = 1
	}
}

func p3GIndex(p float64) int {
	for i, x := range p3G {
		if x == p {
			return i
		}
	}
	panic("grid point missing")
}

func p3PostCopy(st *p3State) string {
	b, _ := json.Marshal([]any{st.Post, st.W})
	return string(b)
}

func TestP3CompletionRuleWithoutPreflightIsTheCeilRule(t *testing.T) {
	for c := -3; c <= 60000; c++ {
		if c > 12000 && (c-12000)%7 != 0 {
			continue
		}
		for need := 0; need <= 45; need++ {
			if p3OneRTTOK(c, need, 0) != (binIndex(c) >= need) {
				t.Fatalf("credit %d need %d: rule %v, ceil %v", c, need, p3OneRTTOK(c, need, 0), binIndex(c) >= need)
			}
		}
	}
}

func TestP3PreflightBytesGateTheCliff(t *testing.T) {
	for _, c := range []struct {
		k    int
		u    float64
		want int
	}{{1, 10, 0}, {2, 10, 41}, {3, 2, 82}, {4, 100, 123}, {3, 0, 0}, {4, -1, 0}} {
		if got := p3PreflightBytes(c.k, c.u); got != c.want {
			t.Fatalf("A_pre(k=%d, u=%v) = %d, want %d", c.k, c.u, got, c.want)
		}
	}
	if p3OneRTTOK(2568, 7, 41) || !p3OneRTTOK(2568, 7, 0) || !p3OneRTTOK(2582, 7, 41) {
		t.Fatal("A_pre does not move the 1-RTT edge by 41 bytes")
	}
	for _, c := range []struct {
		w      int
		u      float64
		p1, p2 float64
	}{{1284, 0, 1, 0}, {1284, 10, 0, 1}, {1291, 0, 1, 0}, {1291, 10, 1, 0}} {
		pt := p3Evaluate(2, c.w, 0, 0, 0, 50, c.u, 7)
		if pt.P1 != c.p1 || pt.P2 != c.p2 || pt.PF != 0 {
			t.Fatalf("W%d u%v: p1 %v p2 %v pf %v", c.w, c.u, pt.P1, pt.P2, pt.PF)
		}
	}
}

func TestP3SkipUsesV31CompletionRule(t *testing.T) {
	s := p3SynthS(6000, 2, 1280)
	c10 := &p3Ctx{K: 2, S: s, NNeed: binNeeded(s, binIndex(2560), cPktDefault), W: 1280, U: 10, RTT: 80}
	c0 := *c10
	c0.U = 0
	if c10.NNeed != 7 {
		t.Fatalf("n_need %d", c10.NNeed)
	}
	for _, a := range []p3Action{{1, 0, 0}, {1, 0, 4}} {
		if !c10.nominalTwoRTT(a) || c0.nominalTwoRTT(a) {
			t.Fatalf("%+v: nominal 2 at u=10 %v, at u=0 %v", a, c10.nominalTwoRTT(a), c0.nominalTwoRTT(a))
		}
		if c10.skipReason(a) != p3SkipNominal2 || c0.skipReason(a) != "" {
			t.Fatalf("%+v: skip %q %q", a, c10.skipReason(a), c0.skipReason(a))
		}
	}
	for _, a := range []p3Action{{1, 1, 3}, {0, 2, 2}, {0, 1, 3}} {
		if c10.nominalTwoRTT(a) {
			t.Fatalf("%+v nominal 2 at u=10", a)
		}
	}
}

func TestP3NominalTwoObservationUpdatesWindowsNotPosterior(t *testing.T) {
	st := newP3State()
	var hs []float64
	for i := 0; i < 10; i++ {
		hs = append(hs, 80.0+0.1*float64(i))
	}
	p3Feed(st, p3Action{0, 3, 1}, hs, nil, 16000, 50, 2)
	upd0 := st.Stats.Upd
	if upd0 == 0 {
		t.Fatal("no update from the 1-RTT arm")
	}
	arm := p3Action{0, 0, 4}
	c, _ := p3Context(st, 1280, 2, 50, cPktDefault)
	if !c.nominalTwoRTT(arm) || c.shielded(arm) || c.skipReason(arm) != p3SkipNominal2 ||
		c.skipReason(p3Action{0, 3, 1}) != "" {
		t.Fatal("skip classification")
	}
	post0 := p3PostCopy(st)
	k0 := len(st.KHist)
	s0 := append([]float64(nil), st.SHist...)
	infos := p3Feed(st, arm, []float64{120, 121, 300}, nil, 16000, 50, 2)
	for i, want := range []int{0, 0, 1} {
		if infos[i].Y != want || infos[i].Skip != p3SkipNominal2 || infos[i].Updated || infos[i].Shielded {
			t.Fatalf("obs %d: %+v", i, infos[i])
		}
	}
	if p3PostCopy(st) != post0 || st.Stats.Upd != upd0 || st.Stats.Nominal2 != 3 || len(st.KHist) != k0+3 {
		t.Fatalf("nominal-2 observation moved the posterior or counters: %+v", st.Stats)
	}
	wantS := append(s0, p3SynthS(16000, 2, 1280), p3SynthS(16000, 2, 1280))
	if len(wantS) > p3SWin {
		wantS = wantS[len(wantS)-p3SWin:]
	}
	if !reflect.DeepEqual(st.SHist, wantS) || !reflect.DeepEqual(st.HCT[arm.Key()], []float64{120, 121, 300}) {
		t.Fatalf("windows %v %v", st.SHist, st.HCT[arm.Key()])
	}
	info := p3Feed(st, p3Action{0, 3, 1}, []float64{80.5}, nil, 16000, 50, 2)[0]
	if !info.Updated || p3PostCopy(st) == post0 {
		t.Fatal("the 1-RTT arm stopped updating")
	}
}

func TestP3ReevalEverySixteenthQualifyingDecision(t *testing.T) {
	k, w, cert, u, rtt := 2, 1280, 16000, 2.0, 50.0
	s := p3SynthS(cert, k, w)
	hi, lo := p3GIndex(0.3), p3GIndex(0.02)
	st := p3PointState(k, w, cert, hi)
	ref, err := p3DecideCore(p3Combined(st), k, w, s, u, rtt, cPktDefault, true, nil, false)
	if err != nil {
		t.Fatal(err)
	}
	if !ref.N2 || !ref.ReevalCond || !ref.HasAlt || ref.Alt.N2 || ref.Alt.Action == ref.Action {
		t.Fatalf("reference decision %+v", ref)
	}
	var one []p3Cand
	for _, c := range ref.Cands {
		e0 := p3Evaluate(k, c.WEff, c.M, c.Action.Lead, 0, rtt, u, ref.NNeed).E
		if c.N2 != (e0 >= 0.5) {
			t.Fatalf("%+v: n2 %v, e0 %v", c.Action, c.N2, e0)
		}
		if !c.N2 {
			one = append(one, c)
		}
	}
	jmin := math.Inf(1)
	for _, c := range one {
		jmin = math.Min(jmin, c.EJ)
	}
	var tied []p3Cand
	for _, c := range one {
		if c.EJ <= jmin+jTieMs {
			tied = append(tied, c)
		}
	}
	sort.SliceStable(tied, func(i, j int) bool { return p3TieLess(&tied[i], &tied[j]) })
	if tied[0].Action != ref.Alt.Action || tied[0].EJ != ref.Alt.EJ {
		t.Fatalf("alt %+v, by hand %+v", ref.Alt.Action, tied[0].Action)
	}
	for i := 0; i < 48; i++ {
		d, err := p3Decide(st, w, u, rtt, cPktDefault, false)
		if err != nil {
			t.Fatal(err)
		}
		if d.DecIndex != i+1 || d.NReeval != i+1 || d.PolicyVersion != "v3.1" {
			t.Fatalf("decision %d: index %d reeval %d %s", i, d.DecIndex, d.NReeval, d.PolicyVersion)
		}
		want, why := ref.Action, "ej"
		if (i+1)%16 == 0 {
			want, why = ref.Alt.Action, "reeval"
		}
		if d.Action != want || d.Why != why || d.Reeval != (why == "reeval") {
			t.Fatalf("decision %d: %+v %s %v", i, d.Action, d.Why, d.Reeval)
		}
		p := auto3PlanFor(d, w, rtt, "test")
		if jp := p.jPred(); jp == nil || *jp != d.EJ {
			t.Fatalf("decision %d: j3_pred_pre %v, EJ %v", i, jp, d.EJ)
		}
	}
	if st.Stats.Reeval != 3 {
		t.Fatalf("reeval count %d", st.Stats.Reeval)
	}
	p3SetPoint(st, lo)
	for i := 0; i < 10; i++ {
		d, _ := p3Decide(st, w, u, rtt, cPktDefault, false)
		if d.ReevalCond || d.Why != "ej" {
			t.Fatalf("low-loss decision %+v", d)
		}
	}
	if st.NReeval != 48 || st.NDec != 58 {
		t.Fatalf("counters %d %d", st.NReeval, st.NDec)
	}
	p3SetPoint(st, hi)
	for i := 0; i < 16; i++ {
		d, _ := p3Decide(st, w, u, rtt, cPktDefault, false)
		if (d.Why == "reeval") != (i == 15) {
			t.Fatalf("decision %d after the pause: %s", i, d.Why)
		}
	}
	if st.Stats.Reeval != 4 {
		t.Fatalf("reeval count %d", st.Stats.Reeval)
	}
}

func TestP3NoReevalWithoutNominalOneCandidate(t *testing.T) {
	st := p3PointState(2, 1280, 30000, p3GIndex(0.3))
	for i := 0; i < 40; i++ {
		d, err := p3Decide(st, 1280, 5, 200, cPktDefault, true)
		if err != nil {
			t.Fatal(err)
		}
		if !d.N2 || d.HasAlt || d.ReevalCond || d.Why != "ej" {
			t.Fatalf("decision %d: %+v", i, d)
		}
		for _, c := range d.Cands {
			if !c.N2 {
				t.Fatalf("candidate %+v is nominally 1-RTT", c.Action)
			}
		}
	}
	if st.NReeval != 0 || st.NDec != 40 || st.Stats.Reeval != 0 {
		t.Fatalf("counters %d %d %d", st.NReeval, st.NDec, st.Stats.Reeval)
	}
}

func TestP3ColdDecisionCountsButNeverReevaluates(t *testing.T) {
	st := newP3State()
	d, err := p3Decide(st, 1280, 2, 50, cPktDefault, false)
	if err != nil || d.Why != "cold" || d.Reeval || d.HasEJ || d.PolicyVersion != "v3.1" {
		t.Fatalf("cold %+v %v", d, err)
	}
	if st.NDec != 1 || st.NReeval != 0 || auto3PlanFor(d, 1280, 50, "x").jPred() != nil {
		t.Fatalf("counters %d %d", st.NDec, st.NReeval)
	}
}

func TestP3CommonDelayIsTheMedianOfUnalarmedResiduals(t *testing.T) {
	st := newP3State()
	b := p3Action{0, 2, 2}
	if p3GuardCommon(st) != 0 {
		t.Fatal("empty common delay")
	}
	p3FeedG(st, b, []float64{101, 103}, 100)
	if p3GuardCommon(st) != 2 {
		t.Fatalf("common %v", p3GuardCommon(st))
	}
	p3FeedG(st, b, []float64{110}, 100)
	if p3GuardCommon(st) != 3 {
		t.Fatalf("common %v", p3GuardCommon(st))
	}
	var hs, want []float64
	for i := 0; i < 100; i++ {
		hs = append(hs, 100+float64(i))
	}
	for i := 36; i < 100; i++ {
		want = append(want, float64(i))
	}
	p3FeedG(st, b, hs, 100)
	if !reflect.DeepEqual(st.GCommon, want) || len(st.GResid[b.Key()]) != p3GuardActionWin ||
		p3GuardCommon(st) != (67.0+68.0)/2.0 {
		t.Fatalf("windows %v %d", st.GCommon, len(st.GResid[b.Key()]))
	}
	if p3MeanSeq([]float64{1, 2, 4}) != 7.0/3.0 {
		t.Fatal("mean")
	}
}

func p3GuardWarm(t *testing.T) *p3State {
	st := newP3State()
	a, b := p3Action{0, 1, 2}, p3Action{0, 2, 2}
	for _, info := range p3FeedG(st, b, p3Rep(102, 10), 100) {
		if !info.HasResid || info.Resid != 2 {
			t.Fatalf("warm residual %+v", info)
		}
	}
	c, ok := p3Context(st, 1280, 2, 50, cPktDefault)
	if !ok || c.nominalTwoRTT(a) || c.nominalTwoRTT(b) {
		t.Fatal("guard test arms must be nominally 1-RTT")
	}
	return st
}

func TestP3AlarmNeedsEightResidualsAndHalfRTTExcess(t *testing.T) {
	a, b := p3Action{0, 1, 2}, p3Action{0, 2, 2}
	st := p3GuardWarm(t)
	for _, info := range p3FeedG(st, a, p3Rep(140, 7), 100) {
		if info.Y >= 0 && !info.Updated {
			t.Fatalf("unalarmed observation skipped %+v", info)
		}
	}
	if len(st.GAlarm) != 0 || p3GuardCommon(st) != 2 {
		t.Fatalf("alarm %v common %v", st.GAlarm, p3GuardCommon(st))
	}
	post0 := p3PostCopy(st)
	info := p3FeedG(st, a, []float64{140}, 100)[0]
	if !reflect.DeepEqual(info.Raised, []string{a.Key()}) || !info.Alarmed || info.Skip != p3SkipGuard ||
		info.Updated || p3PostCopy(st) != post0 {
		t.Fatalf("raising observation %+v", info)
	}
	if !reflect.DeepEqual(st.GAlarm, map[string]int{a.Key(): 0}) || st.Stats.Guard != 1 ||
		st.Stats.AlarmRaised != 1 || len(st.GCommon) != 18 {
		t.Fatalf("alarm state %v %+v %d", st.GAlarm, st.Stats, len(st.GCommon))
	}
	st2 := p3GuardWarm(t)
	p3FeedG(st2, b, p3Rep(102, 30), 100)
	p3FeedG(st2, a, p3Rep(127, 8), 100)
	if p3GuardCommon(st2) != 2 || p3MeanSeq(st2.GResid[a.Key()])-2 != 25 || len(st2.GAlarm) != 0 {
		t.Fatalf("exactly half an RTT must not alarm: %v", st2.GAlarm)
	}
	p3FeedG(st2, a, []float64{128}, 100)
	if !reflect.DeepEqual(st2.GAlarm, map[string]int{a.Key(): 0}) {
		t.Fatalf("alarm %v", st2.GAlarm)
	}
}

func TestP3AlarmedActionPenaltySkipAndClear(t *testing.T) {
	a, b := p3Action{0, 1, 2}, p3Action{0, 2, 2}
	ka := a.Key()
	st := p3GuardWarm(t)
	p3FeedG(st, a, p3Rep(140, 8), 100)
	nCommon := len(st.GCommon)
	bc := p3GuardCommon(st)
	if bc != 2 || !reflect.DeepEqual(p3GuardPenalties(st, bc), map[string]float64{ka: 38}) {
		t.Fatalf("penalty %v", p3GuardPenalties(st, bc))
	}
	d, err := p3Decide(st, 1280, 2, 50, cPktDefault, true)
	if err != nil || d.GuardAlarmed != 1 || d.GuardCommon != 2 || d.GuardAlarm != (d.Action == a) {
		t.Fatalf("decision %+v %v", d, err)
	}
	jmin := math.Inf(1)
	for _, c := range d.Cands {
		jmin = math.Min(jmin, c.Score)
		if c.Action == a {
			if c.Pen != 38 || c.Score != c.EJ+38 {
				t.Fatalf("alarmed candidate %+v", c)
			}
		} else if c.Pen != 0 || c.Score != c.EJ {
			t.Fatalf("unalarmed candidate %+v", c)
		}
	}
	if d.JMin != jmin {
		t.Fatalf("jmin %v, min score %v", d.JMin, jmin)
	}
	post0 := p3PostCopy(st)
	for _, info := range p3FeedG(st, a, []float64{150, 150}, 100) {
		if info.Skip != p3SkipGuard || info.Updated {
			t.Fatalf("alarmed observation %+v", info)
		}
	}
	if p3PostCopy(st) != post0 || len(st.GCommon) != nCommon || len(st.GResid[ka]) != 10 {
		t.Fatal("alarmed observation reached the posterior or the common window")
	}
	if p := p3GuardPenalties(st, bc)[ka]; p != (8*40.0+2*50.0)/10-2.0 {
		t.Fatalf("penalty %v", p)
	}
	for i := 2; i < 65; i++ {
		d, _ := p3Decide(st, 1280, 2, 50, cPktDefault, false)
		if len(d.GuardCleared) != 0 || d.GuardAlarmed != 1 {
			t.Fatalf("decision %d cleared early %+v", i, d.GuardCleared)
		}
	}
	if st.NDec != 64 {
		t.Fatalf("n_dec %d", st.NDec)
	}
	d, _ = p3Decide(st, 1280, 2, 50, cPktDefault, true)
	if !reflect.DeepEqual(d.GuardCleared, []string{ka}) || d.GuardAlarmed != 0 || d.GuardAlarm {
		t.Fatalf("clearing decision %+v", d)
	}
	for _, c := range d.Cands {
		if c.Pen != 0 {
			t.Fatalf("penalty after clearing %+v", c)
		}
	}
	if _, ok := st.GResid[ka]; ok || len(st.GAlarm) != 0 || st.Stats.AlarmCleared != 1 {
		t.Fatalf("cleared state %v %v", st.GResid, st.GAlarm)
	}
	p3FeedG(st, b, p3Rep(102, 40), 100)
	p3FeedG(st, a, p3Rep(140, 7), 100)
	if len(st.GAlarm) != 0 {
		t.Fatal("re-armed before eight new residuals")
	}
	p3FeedG(st, a, []float64{140}, 100)
	if !reflect.DeepEqual(st.GAlarm, map[string]int{ka: 65}) {
		t.Fatalf("re-armed %v", st.GAlarm)
	}
}

func TestP3PenaltyFloorsAtZeroWhenCommonDelayRises(t *testing.T) {
	a, b := p3Action{0, 1, 2}, p3Action{0, 2, 2}
	st := p3GuardWarm(t)
	p3FeedG(st, a, p3Rep(140, 8), 100)
	p3FeedG(st, b, p3Rep(160, 64), 100)
	bc := p3GuardCommon(st)
	if _, on := st.GAlarm[b.Key()]; bc != 60 || on {
		t.Fatalf("common %v alarms %v", bc, st.GAlarm)
	}
	if !reflect.DeepEqual(p3GuardPenalties(st, bc), map[string]float64{a.Key(): 0}) {
		t.Fatalf("penalties %v", p3GuardPenalties(st, bc))
	}
}

func TestP3OtherActionsCanAlarmWhenCommonDelayFalls(t *testing.T) {
	a, b := p3Action{0, 1, 2}, p3Action{0, 2, 2}
	st := newP3State()
	p3FeedG(st, a, p3Rep(120, 8), 100)
	if len(st.GAlarm) != 0 {
		t.Fatal("early alarm")
	}
	p3FeedG(st, b, p3Rep(90, 40), 100)
	if p3GuardCommon(st) != -10 || !reflect.DeepEqual(st.GAlarm, map[string]int{a.Key(): 0}) {
		t.Fatalf("common %v alarms %v", p3GuardCommon(st), st.GAlarm)
	}
}

func TestP3NoResidualWithoutPredictionOrOnFailure(t *testing.T) {
	st := newP3State()
	b := p3Action{0, 2, 2}
	info := p3Feed(st, b, []float64{100}, nil, 9000, 50, 2)[0]
	if info.HasResid || len(st.GResid) != 0 || len(st.GCommon) != 0 || st.Stats.Resid != 0 {
		t.Fatalf("residual without prediction %+v", info)
	}
	jp := 100.0
	info, err := p3Observe(st, b, math.NaN(), false, 0, 0, 50, 1280, 2, cPktDefault, &jp)
	if err != nil || info.HasResid || len(st.GCommon) != 0 || st.Stats.Fail != 1 {
		t.Fatalf("failed connection made a residual %+v %v", info, err)
	}
	nan := math.NaN()
	if _, err := p3Observe(st, b, 100, true, 2, 10000, 50, 1280, 2, cPktDefault, &nan); err == nil {
		t.Fatal("non-finite j_pred accepted")
	}
}

func TestAuto3CacheFeedsThePlanPrediction(t *testing.T) {
	c, err := loadDestCache3("")
	if err != nil {
		t.Fatal(err)
	}
	addr := "10.0.0.3:44434"
	p, _ := c.plan(addr, 1280, 2, cPktDefault)
	info, _, err := c.observePred(addr, p.Action, p.jPred(), 120, true, 2, 18000, 50, true, 1280, 2, cPktDefault)
	if err != nil || p.Decision.Why != "cold" || info.HasResid {
		t.Fatalf("cold plan %+v info %+v %v", p.Decision, info, err)
	}
	p, _ = c.plan(addr, 1280, 2, cPktDefault)
	if !p.Decision.HasEJ || p.Decision.DecIndex != 2 {
		t.Fatalf("second plan %+v", p.Decision)
	}
	info, _, err = c.observePred(addr, p.Action, p.jPred(), 77.5, true, 2, 18000, 50, true, 1280, 2, cPktDefault)
	if err != nil || !info.HasResid || info.Resid != 77.5-p.Decision.EJ {
		t.Fatalf("residual %+v, EJ %v", info, p.Decision.EJ)
	}
	st := c.Dests[addr].State
	if !reflect.DeepEqual(st.GResid[p.Action.Key()], []float64{77.5 - p.Decision.EJ}) || len(st.GCommon) != 1 {
		t.Fatalf("guard windows %v %v", st.GResid, st.GCommon)
	}
	info, _, err = c.observe(addr, p.Action, 80, true, 2, 18000, 50, true, 1280, 2, cPktDefault)
	if err != nil || info.HasResid || len(st.GCommon) != 1 {
		t.Fatalf("observe without a prediction made a residual %+v", info)
	}
}
