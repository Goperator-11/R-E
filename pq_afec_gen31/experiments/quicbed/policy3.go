package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

const p3NG = 26
const p3NH = 5

var p3G = [p3NG]float64{0.0, 0.002, 0.005, 0.01, 0.02, 0.03, 0.04, 0.05, 0.065,
	0.08, 0.1, 0.12, 0.135, 0.15, 0.1625, 0.175, 0.1875, 0.2, 0.2125, 0.225,
	0.2375, 0.25, 0.2625, 0.275, 0.2875, 0.3}

var p3H = [p3NH]float64{1.0 / 30, 1.0 / 100, 1.0 / 300, 1.0 / 1000, 1.0 / 3000}

var (
	p3Eps         = 0.01
	p3WFloor      = 1e-6
	p3EventFrac   = 0.5
	p3ShieldRTTMs = 200.0
	p3ShieldE0    = 0.5
	p3GeCut       = 0.10
	p3GuardFrac   = 0.5
)

const (
	p3KWin              = 16
	p3SWin              = 16
	p3HCTWin            = 32
	p3BaseMin           = 8
	p3KMax              = 4
	p3MMax              = 4
	p3MinW              = 1200
	p3StateVersion      = 2
	p3UDPMax            = typicalMTU - 28
	p3Later             = "v3"
	p3CacheSchema       = "padfec3.cache3/2"
	p3MemoCap           = 100000
	p3PreflightAckBytes = 41
	p3PolicyVersion     = "v3.1"
	p3ReevalEvery       = 16
	p3GuardCommonWin    = 64
	p3GuardActionWin    = 32
	p3GuardMin          = 8
	p3GuardRefresh      = 64
	p3SkipShield        = "shield"
	p3SkipNominal2      = "nominal2"
	p3SkipGuard         = "guard"
)

type p3Action struct {
	Delta int
	Lead  int
	T     int
}

func (a p3Action) M() int {
	return a.Lead + a.T
}

func (a p3Action) Key() string {
	return fmt.Sprintf("%d,%d,%d", a.Delta, a.Lead, a.T)
}

func (a p3Action) valid() bool {
	return a.Delta >= 0 && a.Lead >= 0 && a.T >= 0 && a.Lead+a.T <= p3MMax
}

func (a p3Action) arr() [3]int {
	return [3]int{a.Delta, a.Lead, a.T}
}

func parseP3Key(s string) (p3Action, error) {
	parts := strings.Split(s, ",")
	if len(parts) != 3 {
		return p3Action{}, fmt.Errorf("arm key %q is not delta,lead,T", s)
	}
	var v [3]int
	for i, p := range parts {
		x, err := strconv.Atoi(p)
		if err != nil {
			return p3Action{}, fmt.Errorf("arm key %q: %v", s, err)
		}
		v[i] = x
	}
	a := p3Action{Delta: v[0], Lead: v[1], T: v[2]}
	if !a.valid() || a.Key() != s {
		return p3Action{}, fmt.Errorf("arm key %q is not a valid action", s)
	}
	return a, nil
}

func p3LegacyLead(m int) int {
	if m >= 2 {
		return 1
	}
	return 0
}

func p3Tau(nbytes int, u float64) float64 {
	if u <= 0 {
		return 0.0
	}
	return float64(nbytes) * 8.0 / (u * 1e3)
}

func p3PySum(xs []float64) float64 {
	if len(xs) == 0 {
		return 0
	}
	f := 0.0 + xs[0]
	c := 0.0
	for _, x := range xs[1:] {
		t := f + x
		if math.Abs(f) >= math.Abs(x) {
			c += (f - t) + x
		} else {
			c += (x - t) + f
		}
		f = t
	}
	if c != 0 && p3Finite(c) {
		f += c
	}
	return f
}

type p3Point struct {
	J  float64
	E  float64
	P1 float64
	P2 float64
	PF float64
}

type p3Fail struct {
	pr    float64
	tLast float64
	kind  int
}

func p3PreflightBytes(k int, u float64) int {
	if u <= 0 {
		return 0
	}
	return p3PreflightAckBytes * (k - 1)
}

func p3OneRTTOK(credit, need, aPre int) bool {
	return amplificationFactor*credit-aPre > serverPacketSize*(need-1)
}

func p3Evaluate(k, w, m, lead int, p, rtt, u float64, nNeed int) p3Point {
	if k < 1 || k > p3KMax || m < 0 || m > p3MMax || lead < 0 || lead > m {
		panic(fmt.Sprintf("p3Evaluate: k=%d m=%d lead=%d out of range", k, m, lead))
	}
	aPre := p3PreflightBytes(k, u)
	n := k + m
	pz := parityDatagramBytes(w, k)
	sizes := make([]int, n)
	for i := range sizes {
		if i >= lead && i < lead+k {
			sizes[i] = w
		} else {
			sizes[i] = pz
		}
	}
	resp := p3Tau(w, u)
	lastO := lead + k - 1
	pat := make([]bool, n)
	arr := make([]float64, n)
	trail := make([]int, 0, n)
	fails := make([]p3Fail, 0, 16)
	var J, p1, p2, nSum, succ float64
	for idx := 0; idx < 1<<n; idx++ {
		pr := 1.0
		for i := 0; i < n; i++ {
			pat[i] = (idx>>(n-1-i))&1 == 1
			if pat[i] {
				pr *= 1 - p
			} else {
				pr *= p
			}
		}
		if pr == 0 {
			continue
		}
		t := 0.0
		for i := 0; i < n; i++ {
			arr[i] = 0
			if pat[i] {
				t += p3Tau(sizes[i], u)
				arr[i] = t
			}
		}
		la := 0
		for i := 0; i < lead; i++ {
			if pat[i] {
				la++
			}
		}
		a := 0
		for i := lead; i < lead+k; i++ {
			if pat[i] {
				a++
			}
		}
		trail = trail[:0]
		for i := lead + k; i < n; i++ {
			if pat[i] {
				trail = append(trail, i)
			}
		}
		miss := k - a
		if miss == 0 || miss <= len(trail) {
			decI := lastO
			after := trail
			if miss > 0 {
				decI = trail[miss-1]
				after = trail[miss:]
			}
			tDec := arr[decI]
			base := la*pz + k*w
			add := func(wgt float64, cred int) {
				nr := 2
				if p3OneRTTOK(cred, nNeed, aPre) {
					nr = 1
				}
				extra := 0.0
				if nr == 2 {
					extra = resp
				}
				hct := float64(tDec+float64(rtt*float64(nr))) + extra
				pw := pr * wgt
				J += float64(pw * hct)
				if nr == 1 {
					p1 += pw
				} else {
					p2 += pw
				}
				nSum += float64(pw * float64(nr))
				succ += pw
			}
			prev := 1.0
			for i, ai := range after {
				qi := raceWinProb(arr[ai] - tDec)
				if prev-qi > 0 {
					add(prev-qi, base+i*pz)
				}
				prev = qi
			}
			if prev > 0 {
				add(prev, base+len(after)*pz)
			}
			continue
		}
		kind := 2
		if a == 0 {
			kind = 0
		} else if !pat[lastO] {
			kind = 1
		}
		tLast := 0.0
		found := false
		for i := lead; i < lead+k; i++ {
			if pat[i] && (!found || arr[i] > tLast) {
				tLast = arr[i]
				found = true
			}
		}
		fails = append(fails, p3Fail{pr: pr, tLast: tLast, kind: kind})
	}
	prs := make([]float64, len(fails))
	for i, f := range fails {
		prs[i] = f.pr
	}
	pf := p3PySum(prs)
	nOK := 2.0
	if succ > 1e-15 {
		nOK = nSum / succ
	}
	mult := 1.0
	if pf < 1 {
		mult = 1.0 / (1.0 - pf)
	}
	for _, f := range fails {
		var c float64
		switch f.kind {
		case 0:
			c = rtt + tPTONoAckMs + p3Tau(k*w, u)
		case 1:
			c = float64(f.tLast+float64(nOK*rtt)) + float64(ptoSampledRttMult*rtt)
		default:
			c = float64(f.tLast+float64(nOK*rtt)) +
				float64(float64(tAckRetxSlope*rtt)+tAckRetxBaseMs)
		}
		J += float64(float64(f.pr*mult) * c)
	}
	return p3Point{J: J, E: p2 + pf, P1: p1, P2: p2, PF: pf}
}

type p3Key struct {
	k     int
	wEff  int
	u     float64
	rtt   float64
	nNeed int
	lead  int
	m     int
}

type p3Row struct {
	pts  [p3NG]p3Point
	done [p3NG]bool
}

var p3Memo = struct {
	sync.Mutex
	m map[p3Key]*p3Row
}{m: map[p3Key]*p3Row{}}

func p3MemoReset() {
	p3Memo.Lock()
	p3Memo.m = map[p3Key]*p3Row{}
	p3Memo.Unlock()
}

func p3MemoSize() int {
	p3Memo.Lock()
	defer p3Memo.Unlock()
	return len(p3Memo.m)
}

func p3ModelPoint(k, wEff int, u, rtt float64, nNeed, lead, m, g int) p3Point {
	key := p3Key{k: k, wEff: wEff, u: u, rtt: rtt, nNeed: nNeed, lead: lead, m: m}
	p3Memo.Lock()
	row := p3Memo.m[key]
	if row == nil {
		if len(p3Memo.m) >= p3MemoCap {
			p3Memo.m = map[p3Key]*p3Row{}
		}
		row = &p3Row{}
		p3Memo.m[key] = row
	}
	if row.done[g] {
		pt := row.pts[g]
		p3Memo.Unlock()
		return pt
	}
	p3Memo.Unlock()
	pt := p3Evaluate(k, wEff, m, lead, p3G[g], rtt, u, nNeed)
	p3Memo.Lock()
	row.pts[g] = pt
	row.done[g] = true
	p3Memo.Unlock()
	return pt
}

type p3Ctx struct {
	K     int
	S     float64
	NNeed int
	W     int
	U     float64
	RTT   float64
}

func (c *p3Ctx) point(a p3Action, g int) p3Point {
	return p3ModelPoint(c.K, c.W+a.Delta, c.U, c.RTT, c.NNeed, a.Lead, a.M(), g)
}

func (c *p3Ctx) nominalTwoRTT(a p3Action) bool {
	return c.point(a, 0).E >= p3ShieldE0
}

func (c *p3Ctx) eventProb(a p3Action, g int) float64 {
	pt := c.point(a, g)
	if c.nominalTwoRTT(a) {
		return pt.PF
	}
	return pt.E
}

func (c *p3Ctx) shielded(a p3Action) bool {
	return c.RTT >= p3ShieldRTTMs && c.nominalTwoRTT(a)
}

func (c *p3Ctx) skipReason(a p3Action) string {
	if !c.nominalTwoRTT(a) {
		return ""
	}
	if c.RTT >= p3ShieldRTTMs {
		return p3SkipShield
	}
	return p3SkipNominal2
}

type p3Stats struct {
	Obs          int `json:"obs"`
	Upd          int `json:"upd"`
	Shield       int `json:"shield"`
	Nominal2     int `json:"nominal2"`
	Guard        int `json:"guard"`
	NoBase       int `json:"no_base"`
	NoCtx        int `json:"no_ctx"`
	Events       int `json:"events"`
	Fail         int `json:"fail"`
	Resid        int `json:"resid"`
	Reeval       int `json:"reeval"`
	AlarmRaised  int `json:"alarm_raised"`
	AlarmCleared int `json:"alarm_cleared"`
}

type p3State struct {
	V       int                  `json:"v"`
	KHist   []int                `json:"k_hist"`
	SHist   []float64            `json:"S_hist"`
	HCT     map[string][]float64 `json:"hct"`
	HCTSeq  map[string]int       `json:"hct_seq"`
	Seq     int                  `json:"seq"`
	Post    [][]float64          `json:"post"`
	W       []float64            `json:"w"`
	NDec    int                  `json:"n_dec"`
	NReeval int                  `json:"n_reeval"`
	GResid  map[string][]float64 `json:"g_resid"`
	GCommon []float64            `json:"g_common"`
	GAlarm  map[string]int       `json:"g_alarm"`
	Stats   p3Stats              `json:"stats"`
}

func newP3State() *p3State {
	post := make([][]float64, p3NH)
	for j := range post {
		post[j] = make([]float64, p3NG)
		for i := range post[j] {
			post[j][i] = 1.0 / float64(p3NG)
		}
	}
	w := make([]float64, p3NH)
	for j := range w {
		w[j] = 1.0 / float64(p3NH)
	}
	return &p3State{V: p3StateVersion, KHist: []int{}, SHist: []float64{},
		HCT: map[string][]float64{}, HCTSeq: map[string]int{}, Post: post, W: w,
		GResid: map[string][]float64{}, GCommon: []float64{}, GAlarm: map[string]int{}}
}

func (st *p3State) normalize() {
	if st.KHist == nil {
		st.KHist = []int{}
	}
	if st.SHist == nil {
		st.SHist = []float64{}
	}
	if st.HCT == nil {
		st.HCT = map[string][]float64{}
	}
	if st.HCTSeq == nil {
		st.HCTSeq = map[string]int{}
	}
	for k, v := range st.HCT {
		if v == nil {
			st.HCT[k] = []float64{}
		}
	}
	if st.GResid == nil {
		st.GResid = map[string][]float64{}
	}
	for k, v := range st.GResid {
		if v == nil {
			st.GResid[k] = []float64{}
		}
	}
	if st.GCommon == nil {
		st.GCommon = []float64{}
	}
	if st.GAlarm == nil {
		st.GAlarm = map[string]int{}
	}
}

func p3Finite(x float64) bool {
	return !math.IsNaN(x) && !math.IsInf(x, 0)
}

func (st *p3State) validate() error {
	if st.V != p3StateVersion {
		return fmt.Errorf("state version %d, want %d", st.V, p3StateVersion)
	}
	if len(st.Post) != p3NH {
		return fmt.Errorf("posterior has %d rows, want %d", len(st.Post), p3NH)
	}
	for _, row := range st.Post {
		if len(row) != p3NG {
			return fmt.Errorf("posterior row has %d cells, want %d", len(row), p3NG)
		}
		for _, x := range row {
			if !p3Finite(x) || x < 0 {
				return errors.New("posterior has a negative or non-finite cell")
			}
		}
	}
	if len(st.W) != p3NH {
		return fmt.Errorf("weights have %d entries, want %d", len(st.W), p3NH)
	}
	for _, x := range st.W {
		if !p3Finite(x) || x < 0 {
			return errors.New("weights have a negative or non-finite entry")
		}
	}
	if len(st.KHist) > p3KWin || len(st.SHist) > p3SWin {
		return errors.New("k or S window longer than its cap")
	}
	for _, x := range st.SHist {
		if !p3Finite(x) {
			return errors.New("S window has a non-finite entry")
		}
	}
	for k, v := range st.HCT {
		if _, err := parseP3Key(k); err != nil {
			return err
		}
		if len(v) > p3HCTWin {
			return fmt.Errorf("hct window %s longer than %d", k, p3HCTWin)
		}
		for _, x := range v {
			if !p3Finite(x) {
				return fmt.Errorf("hct window %s has a non-finite entry", k)
			}
		}
		if _, ok := st.HCTSeq[k]; !ok {
			return fmt.Errorf("hct window %s has no sequence number", k)
		}
	}
	for k := range st.HCTSeq {
		if _, err := parseP3Key(k); err != nil {
			return err
		}
	}
	if st.NDec < 0 || st.NReeval < 0 {
		return errors.New("negative decision counter")
	}
	if len(st.GCommon) > p3GuardCommonWin {
		return fmt.Errorf("common residual window longer than %d", p3GuardCommonWin)
	}
	for _, x := range st.GCommon {
		if !p3Finite(x) {
			return errors.New("common residual window has a non-finite entry")
		}
	}
	for k, v := range st.GResid {
		if _, err := parseP3Key(k); err != nil {
			return err
		}
		if len(v) > p3GuardActionWin {
			return fmt.Errorf("residual window %s longer than %d", k, p3GuardActionWin)
		}
		for _, x := range v {
			if !p3Finite(x) {
				return fmt.Errorf("residual window %s has a non-finite entry", k)
			}
		}
	}
	for k, at := range st.GAlarm {
		if _, err := parseP3Key(k); err != nil {
			return err
		}
		if at < 0 || at > st.NDec {
			return fmt.Errorf("alarm %s raised at decision %d of %d", k, at, st.NDec)
		}
	}
	return nil
}

func p3ModeRecent(xs []int) (int, bool) {
	if len(xs) == 0 {
		return 0, false
	}
	counts := map[int]int{}
	for _, v := range xs {
		counts[v]++
	}
	best, have := 0, false
	for i := len(xs) - 1; i >= 0; i-- {
		v := xs[i]
		if !have || counts[v] > counts[best] {
			best, have = v, true
		}
	}
	return best, true
}

func p3Median(xs []float64) float64 {
	s := append([]float64(nil), xs...)
	sort.Float64s(s)
	n := len(s)
	h := n / 2
	if n%2 == 1 {
		return s[h]
	}
	return (s[h-1] + s[h]) / 2.0
}

func (st *p3State) kHat() (int, bool) {
	return p3ModeRecent(st.KHist)
}

func (st *p3State) sHat() (float64, bool) {
	if len(st.SHist) == 0 {
		return 0, false
	}
	return p3Median(st.SHist), true
}

func p3Combined(st *p3State) []float64 {
	out := make([]float64, p3NG)
	for j := range st.W {
		wh := st.W[j]
		ph := st.Post[j]
		for i := 0; i < p3NG; i++ {
			out[i] += float64(wh * ph[i])
		}
	}
	return out
}

func p3PostMean(post []float64) float64 {
	s := 0.0
	for i, q := range post {
		s += float64(q * p3G[i])
	}
	return s
}

type p3Summary struct {
	PMean  float64
	PMap   float64
	Mass   float64
	PGe010 float64
}

func p3PostSummary(post []float64) p3Summary {
	s := 0.0
	for _, q := range post {
		s += q
	}
	mode := 0
	for i := 1; i < len(post); i++ {
		if post[i] > post[mode] {
			mode = i
		}
	}
	hi := 0.0
	for i, q := range post {
		if p3G[i] >= p3GeCut {
			hi += q
		}
	}
	return p3Summary{PMean: p3PostMean(post), PMap: p3G[mode], Mass: s, PGe010: hi}
}

func p3Context(st *p3State, w int, u, rtt, cPkt float64) (*p3Ctx, bool) {
	k, okK := st.kHat()
	s, okS := st.sHat()
	if !okK || !okS {
		return nil, false
	}
	if k < 1 || k > p3KMax {
		return nil, false
	}
	if !(rtt > 0) {
		return nil, false
	}
	nNeed := binNeeded(s, binIndex(k*w), cPkt)
	return &p3Ctx{K: k, S: s, NNeed: nNeed, W: w, U: u, RTT: rtt}, true
}

func p3FilterStep(post [][]float64, w []float64, l []float64) ([][]float64, []float64) {
	inv := 1.0 / float64(p3NG)
	newPost := make([][]float64, p3NH)
	raw := make([]float64, p3NH)
	for j := 0; j < p3NH; j++ {
		h := p3H[j]
		ph := post[j]
		prior := make([]float64, p3NG)
		for i := 0; i < p3NG; i++ {
			prior[i] = float64((1.0-h)*ph[i]) + float64(h*inv)
		}
		z := 0.0
		for i := 0; i < p3NG; i++ {
			z += float64(prior[i] * l[i])
		}
		np := make([]float64, p3NG)
		for i := 0; i < p3NG; i++ {
			np[i] = prior[i] * l[i] / z
		}
		newPost[j] = np
		raw[j] = w[j] * z
	}
	s := 0.0
	for _, x := range raw {
		s += x
	}
	nw := make([]float64, p3NH)
	for j, x := range raw {
		nw[j] = x / s
	}
	for j, x := range nw {
		if !(x >= p3WFloor) {
			nw[j] = p3WFloor
		}
	}
	s2 := 0.0
	for _, x := range nw {
		s2 += x
	}
	for j, x := range nw {
		nw[j] = x / s2
	}
	return newPost, nw
}

func p3Likelihood(c *p3Ctx, a p3Action, y int) []float64 {
	out := make([]float64, p3NG)
	for g := 0; g < p3NG; g++ {
		e := c.eventProb(a, g)
		l1 := float64((1.0-p3Eps)*e) + float64(p3Eps*(1.0-e))
		if y == 1 {
			out[g] = l1
		} else {
			out[g] = 1.0 - l1
		}
	}
	return out
}

func p3Baseline(st *p3State, c *p3Ctx, a p3Action) (float64, string, bool) {
	key := a.Key()
	if own := st.HCT[key]; len(own) >= p3BaseMin {
		return p3Median(own), key, true
	}
	if c == nil {
		return 0, "", false
	}
	keys := make([]string, 0, len(st.HCT))
	for k := range st.HCT {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	best, bestLen, bestSeq, have := "", 0, 0, false
	for _, k2 := range keys {
		v := st.HCT[k2]
		if len(v) < p3BaseMin {
			continue
		}
		seq, ok := st.HCTSeq[k2]
		if !ok {
			seq = -1
		}
		if !have || len(v) > bestLen || (len(v) == bestLen && seq > bestSeq) {
			best, bestLen, bestSeq, have = k2, len(v), seq, true
		}
	}
	if !have {
		return 0, "", false
	}
	ra, err := parseP3Key(best)
	if err != nil {
		return 0, "", false
	}
	b := float64(p3Median(st.HCT[best])+c.point(a, 0).J) - c.point(ra, 0).J
	return b, best, true
}

func p3PushInt(xs []int, v, limit int) []int {
	xs = append(xs, v)
	if len(xs) > limit {
		xs = append([]int(nil), xs[len(xs)-limit:]...)
	}
	return xs
}

func p3PushFloat(xs []float64, v float64, limit int) []float64 {
	xs = append(xs, v)
	if len(xs) > limit {
		xs = append([]float64(nil), xs[len(xs)-limit:]...)
	}
	return xs
}

func p3MeanSeq(xs []float64) float64 {
	s := 0.0
	for _, x := range xs {
		s += x
	}
	return s / float64(len(xs))
}

func p3GuardCommon(st *p3State) float64 {
	if len(st.GCommon) == 0 {
		return 0.0
	}
	return p3Median(st.GCommon)
}

func p3GuardPenalty(st *p3State, key string, b float64) float64 {
	if _, ok := st.GAlarm[key]; !ok {
		return 0.0
	}
	win := st.GResid[key]
	if len(win) == 0 {
		return 0.0
	}
	x := p3MeanSeq(win) - b
	if !(x > 0) {
		return 0.0
	}
	return x
}

func p3SortedKeys[V any](m map[string]V) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

func p3GuardPenalties(st *p3State, b float64) map[string]float64 {
	out := make(map[string]float64, len(st.GAlarm))
	for _, key := range p3SortedKeys(st.GAlarm) {
		out[key] = p3GuardPenalty(st, key, b)
	}
	return out
}

func p3GuardRelease(st *p3State) []string {
	cleared := []string{}
	for _, key := range p3SortedKeys(st.GAlarm) {
		if st.NDec-st.GAlarm[key] >= p3GuardRefresh {
			delete(st.GAlarm, key)
			delete(st.GResid, key)
			cleared = append(cleared, key)
		}
	}
	st.Stats.AlarmCleared += len(cleared)
	return cleared
}

func p3GuardCheck(st *p3State, rtt float64) []string {
	raised := []string{}
	if !(rtt > 0) {
		return raised
	}
	b := p3GuardCommon(st)
	lim := p3GuardFrac * rtt
	for _, key := range p3SortedKeys(st.GResid) {
		if _, on := st.GAlarm[key]; on {
			continue
		}
		win := st.GResid[key]
		if len(win) >= p3GuardMin && p3MeanSeq(win)-b > lim {
			st.GAlarm[key] = st.NDec
			raised = append(raised, key)
		}
	}
	st.Stats.AlarmRaised += len(raised)
	return raised
}

func p3GuardObserve(st *p3State, key string, resid, rtt float64) []string {
	_, pre := st.GAlarm[key]
	st.GResid[key] = p3PushFloat(st.GResid[key], resid, p3GuardActionWin)
	if !pre {
		st.GCommon = p3PushFloat(st.GCommon, resid, p3GuardCommonWin)
	}
	st.Stats.Resid++
	return p3GuardCheck(st, rtt)
}

type p3ObsInfo struct {
	Y        int
	Baseline float64
	HasBase  bool
	Ref      string
	Updated  bool
	Shielded bool
	HasCtx   bool
	Skip     string
	HasResid bool
	Resid    float64
	Alarmed  bool
	Raised   []string
	Common   float64
	NAlarm   int
}

func p3Observe(st *p3State, a p3Action, hct float64, ok bool, kObs int, srv float64,
	rtt float64, w int, u, cPkt float64, jPred *float64) (p3ObsInfo, error) {
	if !a.valid() {
		return p3ObsInfo{Y: -1}, fmt.Errorf("invalid action %+v", a)
	}
	key := a.Key()
	if ok && (!p3Finite(hct) || hct <= 0) {
		return p3ObsInfo{Y: -1}, fmt.Errorf("ok observation needs hct > 0, got %v", hct)
	}
	if jPred != nil && !p3Finite(*jPred) {
		return p3ObsInfo{Y: -1}, fmt.Errorf("j_pred must be finite, got %v", *jPred)
	}
	st.Stats.Obs++
	if !ok {
		st.Stats.Fail++
	}
	c, hasCtx := p3Context(st, w, u, rtt, cPkt)
	b, ref, hasB := p3Baseline(st, c, a)
	info := p3ObsInfo{Y: -1, Baseline: b, HasBase: hasB, Ref: ref, HasCtx: hasCtx}
	if hasB && rtt > 0 {
		if !ok || hct-b >= p3EventFrac*rtt {
			info.Y = 1
		} else {
			info.Y = 0
		}
	}
	if ok && jPred != nil {
		info.HasResid = true
		info.Resid = hct - *jPred
		info.Raised = p3GuardObserve(st, key, info.Resid, rtt)
	}
	_, info.Alarmed = st.GAlarm[key]
	info.Common = p3GuardCommon(st)
	info.NAlarm = len(st.GAlarm)
	skip := ""
	if hasCtx {
		skip = c.skipReason(a)
	}
	if skip == "" && info.Alarmed {
		skip = p3SkipGuard
	}
	switch {
	case info.Y < 0:
		st.Stats.NoBase++
	case !hasCtx:
		st.Stats.NoCtx++
	case skip != "":
		switch skip {
		case p3SkipShield:
			st.Stats.Shield++
		case p3SkipNominal2:
			st.Stats.Nominal2++
		default:
			st.Stats.Guard++
		}
		info.Skip = skip
		info.Shielded = skip == p3SkipShield
	default:
		l := p3Likelihood(c, a, info.Y)
		st.Post, st.W = p3FilterStep(st.Post, st.W, l)
		st.Stats.Upd++
		if info.Y == 1 {
			st.Stats.Events++
		}
		info.Updated = true
	}
	if ok {
		if kObs >= 1 {
			st.KHist = p3PushInt(st.KHist, kObs, p3KWin)
		}
		st.HCT[key] = p3PushFloat(st.HCT[key], hct, p3HCTWin)
		st.HCTSeq[key] = st.Seq
		st.Seq++
		if info.Y != 1 && srv > 0 {
			st.SHist = p3PushFloat(st.SHist, srv, p3SWin)
		}
	}
	return info, nil
}

type p3Cand struct {
	Action      p3Action
	M           int
	Mode        string
	WEff        int
	ClientBytes int
	Added       int
	EJ          float64
	Pen         float64
	Score       float64
	N2          bool
}

func p3NewCand(mode string, a p3Action, k, w int) p3Cand {
	m := a.M()
	wEff := w + a.Delta
	cb := k*wEff + m*parityDatagramBytes(wEff, k)
	added := cb - k*w
	if added < 0 {
		added = 0
	}
	return p3Cand{Action: a, M: m, Mode: mode, WEff: wEff, ClientBytes: cb, Added: added}
}

func p3Candidates(k, w int, s, cPkt float64) []p3Cand {
	out := []p3Cand{}
	seen := map[p3Action]bool{}
	for _, c := range levers(k, w, maxStepsDefault, p3MMax, s, cPkt, quicgoMaxIPS) {
		if quicgoMaxIPS > 0 && c.wEff > quicgoMaxIPS {
			continue
		}
		if c.m > 0 && parityDatagramBytes(c.wEff, k) > p3UDPMax {
			continue
		}
		for lead := 0; lead <= c.m; lead++ {
			a := p3Action{Delta: c.delta, Lead: lead, T: c.m - lead}
			if seen[a] {
				continue
			}
			seen[a] = true
			out = append(out, p3NewCand(c.mode, a, k, w))
		}
	}
	return out
}

func p3CandHash(cands []p3Cand) string {
	parts := make([]string, len(cands))
	for i, c := range cands {
		parts[i] = c.Action.Key()
	}
	sum := sha256.Sum256([]byte(strings.Join(parts, ";")))
	return hex.EncodeToString(sum[:])
}

func p3TieLess(x, y *p3Cand) bool {
	if x.Added != y.Added {
		return x.Added < y.Added
	}
	px, py := 1, 1
	if x.M > 0 {
		px = 0
	}
	if y.M > 0 {
		py = 0
	}
	if px != py {
		return px < py
	}
	if x.Mode != y.Mode {
		return x.Mode < y.Mode
	}
	lx, ly := 1, 1
	if x.Action.Lead == p3LegacyLead(x.M) {
		lx = 0
	}
	if y.Action.Lead == p3LegacyLead(y.M) {
		ly = 0
	}
	if lx != ly {
		return lx < ly
	}
	if x.Score != y.Score {
		return x.Score < y.Score
	}
	if x.Action.Lead != y.Action.Lead {
		return x.Action.Lead < y.Action.Lead
	}
	if x.M != y.M {
		return x.M < y.M
	}
	return x.Action.Delta < y.Action.Delta
}

type p3Decision struct {
	Action        p3Action
	M             int
	Mode          string
	WEff          int
	ClientBytes   int
	Added         int
	HasEJ         bool
	EJ            float64
	Pen           float64
	Score         float64
	N2            bool
	JMin          float64
	NTied         int
	NCands        int
	NNeed         int
	K             int
	S             float64
	Why           string
	CandHash      string
	ReevalCond    bool
	HasAlt        bool
	Alt           p3Cand
	Reeval        bool
	PMean         float64
	PMap          float64
	PGe010        float64
	GuardAlarm    bool
	GuardCommon   float64
	GuardAlarmed  int
	GuardCleared  []string
	DecIndex      int
	NReeval       int
	PolicyVersion string
	Cands         []p3Cand
}

func (d *p3Decision) take(c p3Cand) {
	d.Action, d.M, d.Mode, d.WEff = c.Action, c.M, c.Mode, c.WEff
	d.ClientBytes, d.Added = c.ClientBytes, c.Added
	d.EJ, d.Pen, d.Score, d.N2 = c.EJ, c.Pen, c.Score, c.N2
}

func p3Pick(cands []p3Cand, idx []int) (int, float64, int) {
	jmin := cands[idx[0]].Score
	for _, i := range idx[1:] {
		if cands[i].Score < jmin {
			jmin = cands[i].Score
		}
	}
	lim := jmin + jTieMs
	best := -1
	nTied := 0
	for _, i := range idx {
		if !(cands[i].Score <= lim) {
			continue
		}
		nTied++
		if best < 0 || p3TieLess(&cands[i], &cands[best]) {
			best = i
		}
	}
	return best, jmin, nTied
}

func p3DecideCore(post []float64, k, w int, s, u, rtt, cPkt float64, keep bool,
	pen map[string]float64, reeval bool) (p3Decision, error) {
	if w < p3MinW {
		return p3Decision{}, fmt.Errorf("W must be >= %d: %d", p3MinW, w)
	}
	if len(post) != p3NG {
		return p3Decision{}, fmt.Errorf("posterior length %d, want %d", len(post), p3NG)
	}
	if k < 1 || k > p3KMax {
		return p3Decision{}, fmt.Errorf("k out of range: %d", k)
	}
	nNeed := binNeeded(s, binIndex(k*w), cPkt)
	cands := p3Candidates(k, w, s, cPkt)
	if len(cands) == 0 {
		return p3Decision{}, errors.New("no candidates")
	}
	support := make([]int, 0, p3NG)
	for g := 0; g < p3NG; g++ {
		if post[g] != 0.0 {
			support = append(support, g)
		}
	}
	all := make([]int, 0, len(cands))
	one := make([]int, 0, len(cands))
	for i := range cands {
		c := &cands[i]
		ej := 0.0
		for _, g := range support {
			pt := p3ModelPoint(k, c.WEff, u, rtt, nNeed, c.Action.Lead, c.M, g)
			ej += float64(post[g] * pt.J)
		}
		c.EJ = ej
		c.Pen = pen[c.Action.Key()]
		c.Score = c.EJ + c.Pen
		c.N2 = p3ModelPoint(k, c.WEff, u, rtt, nNeed, c.Action.Lead, c.M, 0).E >= p3ShieldE0
		all = append(all, i)
		if !c.N2 {
			one = append(one, i)
		}
	}
	bestI, jmin, nTied := p3Pick(cands, all)
	if bestI < 0 {
		return p3Decision{}, errors.New("no candidate within the tie window")
	}
	d := p3Decision{HasEJ: true, JMin: jmin, NTied: nTied, NCands: len(cands), NNeed: nNeed,
		K: k, S: s, Why: "ej", CandHash: p3CandHash(cands), PolicyVersion: p3PolicyVersion}
	d.take(cands[bestI])
	if len(one) > 0 {
		altI, _, _ := p3Pick(cands, one)
		if altI >= 0 {
			d.HasAlt, d.Alt = true, cands[altI]
		}
	}
	d.ReevalCond = d.N2 && d.HasAlt
	if reeval && d.ReevalCond {
		d.take(d.Alt)
		d.Why = "reeval"
		d.Reeval = true
	}
	if keep {
		d.Cands = cands
	}
	return d, nil
}

func p3B0(why string, post []float64) p3Decision {
	s := p3PostSummary(post)
	return p3Decision{Mode: "none", Why: why, PMean: s.PMean, PMap: s.PMap, PGe010: s.PGe010,
		PolicyVersion: p3PolicyVersion}
}

func p3Decide(st *p3State, w int, u, rtt, cPkt float64, keep bool) (p3Decision, error) {
	cleared := p3GuardRelease(st)
	b := p3GuardCommon(st)
	pen := p3GuardPenalties(st, b)
	st.NDec++
	post := p3Combined(st)
	k, _ := st.kHat()
	var d p3Decision
	switch {
	case len(st.SHist) == 0 || len(st.KHist) == 0:
		d = p3B0("cold", post)
	case k < 1 || k > p3KMax:
		d = p3B0("k_range", post)
	case !(rtt > 0):
		d = p3B0("no_rtt", post)
	default:
		s, _ := st.sHat()
		var err error
		d, err = p3DecideCore(post, k, w, s, u, rtt, cPkt, keep, pen, false)
		if err != nil {
			return d, err
		}
		if d.ReevalCond {
			st.NReeval++
			if st.NReeval%p3ReevalEvery == 0 {
				d.take(d.Alt)
				d.Why = "reeval"
				d.Reeval = true
				st.Stats.Reeval++
			}
		}
		sm := p3PostSummary(post)
		d.PMean, d.PMap, d.PGe010 = sm.PMean, sm.PMap, sm.PGe010
	}
	_, d.GuardAlarm = st.GAlarm[d.Action.Key()]
	d.GuardCommon = b
	d.GuardAlarmed = len(st.GAlarm)
	d.GuardCleared = cleared
	d.DecIndex = st.NDec
	d.NReeval = st.NReeval
	d.PolicyVersion = p3PolicyVersion
	return d, nil
}

type cache3Entry struct {
	State  *p3State `json:"state"`
	MinRTT float64  `json:"min_rtt_ms"`
	RTTObs int      `json:"rtt_observations"`
	MinHCT float64  `json:"min_hct_ms"`
	Conns  int      `json:"conns"`
}

func (e *cache3Entry) policyRTT() (float64, string) {
	if e.RTTObs > 0 && e.MinRTT > 0 && p3Finite(e.MinRTT) {
		return e.MinRTT, "quic_ack_min_rtt"
	}
	if e.MinHCT > 0 {
		return e.MinHCT, "hct_proxy_no_ack_rtt"
	}
	return 0, "none"
}

type destCache3 struct {
	mu     sync.Mutex
	path   string
	Schema string                  `json:"schema"`
	Dests  map[string]*cache3Entry `json:"dests"`
}

func loadDestCache3(path string) (*destCache3, error) {
	c := &destCache3{path: path, Schema: p3CacheSchema, Dests: map[string]*cache3Entry{}}
	if path == "" {
		return c, nil
	}
	b, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return c, nil
	}
	if err != nil {
		return nil, err
	}
	var f struct {
		Schema string                  `json:"schema"`
		Dests  map[string]*cache3Entry `json:"dests"`
	}
	dec := json.NewDecoder(bytes.NewReader(b))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&f); err != nil {
		return nil, fmt.Errorf("%s: %v", path, err)
	}
	if f.Schema != p3CacheSchema {
		return nil, fmt.Errorf("%s: schema %q, want %q", path, f.Schema, p3CacheSchema)
	}
	for addr, e := range f.Dests {
		if e == nil || e.State == nil {
			return nil, fmt.Errorf("%s: destination %s has no state", path, addr)
		}
		e.State.normalize()
		if err := e.State.validate(); err != nil {
			return nil, fmt.Errorf("%s: destination %s: %v", path, addr, err)
		}
		c.Dests[addr] = e
	}
	return c, nil
}

func (c *destCache3) save() error {
	if c.path == "" {
		return nil
	}
	c.mu.Lock()
	b, err := json.Marshal(struct {
		Schema string                  `json:"schema"`
		Dests  map[string]*cache3Entry `json:"dests"`
	}{p3CacheSchema, c.Dests})
	c.mu.Unlock()
	if err != nil {
		return err
	}
	b = append(b, '\n')
	tmp := c.path + ".tmp"
	if err := os.WriteFile(tmp, b, 0644); err != nil {
		return err
	}
	return os.Rename(tmp, c.path)
}

func (c *destCache3) entry(addr string) *cache3Entry {
	e := c.Dests[addr]
	if e == nil {
		e = &cache3Entry{State: newP3State()}
		c.Dests[addr] = e
	}
	return e
}

type auto3Plan struct {
	Decision  p3Decision
	Action    p3Action
	IPS       int
	M         int
	Lead      int
	FecMode   string
	Why       string
	RTT       float64
	RTTSource string
}

func auto3PlanFor(d p3Decision, w int, rtt float64, src string) auto3Plan {
	a := d.Action
	p := auto3Plan{Decision: d, Action: a, IPS: w + a.Delta, M: a.M(), Lead: a.Lead,
		FecMode: "off", RTT: rtt, RTTSource: src}
	if p.M > 0 {
		p.FecMode = "fec"
	}
	if d.HasEJ {
		p.Why = fmt.Sprintf("auto3 %s %s δ=%d ℓ=%d T=%d ips=%d EJ=%.3fms 동점%d/%d "+
			"n_need=%d k=%d S=%.0f p̄=%.4f RTT=%.3f(%s)", d.Why, d.Mode, a.Delta, a.Lead,
			a.T, p.IPS, d.EJ, d.NTied, d.NCands, d.NNeed, d.K, d.S, d.PMean, rtt, src)
		if d.Pen > 0 {
			p.Why += fmt.Sprintf(" pen=%.3fms", d.Pen)
		}
	} else {
		p.Why = fmt.Sprintf("auto3 %s b0 p̄=%.4f RTT=%.3f(%s)", d.Why, d.PMean, rtt, src)
	}
	return p
}

func (c *destCache3) plan(addr string, w int, u, cPkt float64) (auto3Plan, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	e := c.entry(addr)
	rtt, src := e.policyRTT()
	d, err := p3Decide(e.State, w, u, rtt, cPkt, false)
	if err != nil {
		return auto3Plan{}, err
	}
	return auto3PlanFor(d, w, rtt, src), nil
}

func (p auto3Plan) jPred() *float64 {
	if !p.Decision.HasEJ {
		return nil
	}
	j := p.Decision.EJ
	return &j
}

func (c *destCache3) observe(addr string, a p3Action, hct float64, ok bool, kObs int,
	srv float64, pathRTT float64, pathValid bool, w int, u, cPkt float64) (p3ObsInfo, float64, error) {
	return c.observePred(addr, a, nil, hct, ok, kObs, srv, pathRTT, pathValid, w, u, cPkt)
}

func (c *destCache3) observePred(addr string, a p3Action, jPred *float64, hct float64, ok bool,
	kObs int, srv float64, pathRTT float64, pathValid bool, w int, u, cPkt float64) (p3ObsInfo, float64, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	e := c.entry(addr)
	if pathValid && pathRTT > 0 && p3Finite(pathRTT) {
		if e.MinRTT <= 0 || pathRTT < e.MinRTT {
			e.MinRTT = pathRTT
		}
		e.RTTObs++
	}
	if ok && hct > 0 && (e.MinHCT <= 0 || hct < e.MinHCT) {
		e.MinHCT = hct
	}
	e.Conns++
	rtt, _ := e.policyRTT()
	info, err := p3Observe(e.State, a, hct, ok, kObs, srv, rtt, w, u, cPkt, jPred)
	return info, p3PostMean(p3Combined(e.State)), err
}

func checkAuto3Flags(layoutSet bool, layout string, lead, ips int) error {
	if layoutSet && layout != "v3" {
		return fmt.Errorf("-fec auto3 always uses -layout v3, got -layout %s", layout)
	}
	if lead != -1 {
		return fmt.Errorf("-fec auto3 chooses the lead itself; drop -lead %d", lead)
	}
	w := ips
	if w <= 0 {
		w = 1280
	}
	if w < p3MinW || w > quicgoMaxIPS {
		return fmt.Errorf("-fec auto3 needs %d <= InitialPacketSize <= %d, got %d", p3MinW, quicgoMaxIPS, w)
	}
	return nil
}

type trial3 struct {
	trial
	Action          [3]int   `json:"action"`
	J3              *float64 `json:"j3_ms"`
	J3Min           *float64 `json:"j3_min_ms"`
	PMean           float64  `json:"p_mean"`
	PMap            float64  `json:"p_map"`
	PGe010          float64  `json:"p_ge_010"`
	Why3            string   `json:"why3"`
	Mode3           string   `json:"mode3"`
	KHat            *int     `json:"k_hat"`
	SHat            *float64 `json:"s_hat"`
	NNeed           *int     `json:"n_need"`
	NCands          int      `json:"n_cands"`
	NTied           int      `json:"n_tied"`
	PolicyRTT       float64  `json:"policy_rtt_ms"`
	PolicyRTTSource string   `json:"policy_rtt_source"`
	ObsY            *int     `json:"obs_y"`
	ObsUpdated      bool     `json:"obs_updated"`
	ObsShielded     bool     `json:"obs_shielded"`
	ObsBaseline     *float64 `json:"obs_baseline_ms"`
	ObsErr          string   `json:"obs_err,omitempty"`
	PMeanAfter      float64  `json:"p_mean_after"`
	J3PredPre       *float64 `json:"j3_pred_pre_ms"`
	GuardAlarm      bool     `json:"guard_alarm"`
	GuardResid      *float64 `json:"guard_resid_ms"`
	GuardCommon     float64  `json:"guard_common_ms"`
	GuardAlarmed    int      `json:"guard_alarmed_actions"`
	Reeval          bool     `json:"reeval"`
	PolicyVersion   string   `json:"policy_version"`
	ObsSkip         *string  `json:"obs_skip"`
}

func auto3Row(t trial, p auto3Plan, info p3ObsInfo, obsErr error, pAfter float64) trial3 {
	d := p.Decision
	r := trial3{trial: t, Action: p.Action.arr(), PMean: d.PMean, PMap: d.PMap,
		PGe010: d.PGe010, Why3: d.Why, Mode3: d.Mode, NCands: d.NCands, NTied: d.NTied,
		PolicyRTT: p.RTT, PolicyRTTSource: p.RTTSource, ObsUpdated: info.Updated,
		ObsShielded: info.Shielded, PMeanAfter: pAfter, GuardAlarm: d.GuardAlarm,
		GuardCommon: d.GuardCommon, GuardAlarmed: d.GuardAlarmed, Reeval: d.Reeval,
		PolicyVersion: p3PolicyVersion}
	if d.HasEJ {
		ej, jm, k, s, nn, jp := d.EJ, d.JMin, d.K, d.S, d.NNeed, d.EJ
		r.J3, r.J3Min, r.KHat, r.SHat, r.NNeed, r.J3PredPre = &ej, &jm, &k, &s, &nn, &jp
	}
	if info.HasResid {
		x := info.Resid
		r.GuardResid = &x
	}
	if info.Skip != "" {
		sk := info.Skip
		r.ObsSkip = &sk
	}
	if info.Y >= 0 {
		y := info.Y
		r.ObsY = &y
	}
	if info.HasBase {
		b := info.Baseline
		r.ObsBaseline = &b
	}
	if obsErr != nil {
		r.ObsErr = obsErr.Error()
	}
	return r
}

type p3RefIn struct {
	Primitives []struct {
		ID    int     `json:"id"`
		K     int     `json:"k"`
		WEff  int     `json:"W_eff"`
		M     int     `json:"m"`
		Lead  int     `json:"lead"`
		P     float64 `json:"p"`
		RTT   float64 `json:"rtt"`
		U     float64 `json:"u"`
		NNeed int     `json:"n_need"`
	} `json:"primitives"`
	Decisions []struct {
		ID  int         `json:"id"`
		K   int         `json:"k"`
		W   int         `json:"W"`
		S   float64     `json:"S"`
		RTT float64     `json:"rtt"`
		U   float64     `json:"u"`
		G   []int       `json:"g"`
		Q   []float64   `json:"q"`
		Pen [][]float64 `json:"pen"`
	} `json:"decisions"`
	Trajectories []p3RefTrajIn `json:"trajectories"`
}

type p3RefStepsIn struct {
	A   [][3]int   `json:"a"`
	EJ  []*float64 `json:"ej"`
	RTT []float64  `json:"rtt"`
	HCT []*float64 `json:"hct"`
	OK  []int      `json:"ok"`
	K   []int      `json:"k"`
	Srv []float64  `json:"srv"`
}

type p3RefTrajIn struct {
	ID        string       `json:"id"`
	W         int          `json:"W"`
	U         float64      `json:"u"`
	CPkt      float64      `json:"c_pkt"`
	Steps     p3RefStepsIn `json:"steps"`
	Snapshots []struct {
		AfterStep int `json:"after_step"`
	} `json:"snapshots"`
}

type p3RefPrim struct {
	ID   int     `json:"id"`
	APre int     `json:"a_pre"`
	J    float64 `json:"J"`
	E    float64 `json:"e"`
	P2   float64 `json:"p_two_rtt"`
	PF   float64 `json:"p_fail"`
	P1   float64 `json:"p_one_rtt"`
}

type p3RefDec struct {
	ID         int      `json:"id"`
	Err        string   `json:"err,omitempty"`
	NNeed      int      `json:"n_need"`
	NCands     int      `json:"n_cands"`
	CandHash   string   `json:"cand_hash"`
	Action     [3]int   `json:"action"`
	Mode       string   `json:"mode"`
	EJ         float64  `json:"ej"`
	PenChosen  float64  `json:"pen_chosen"`
	Score      float64  `json:"score"`
	N2         bool     `json:"n2"`
	JMin       float64  `json:"jmin"`
	NTied      int      `json:"n_tied"`
	ReevalCond bool     `json:"reeval_cond"`
	Alt        *[3]int  `json:"alt"`
	AltEJ      *float64 `json:"alt_ej"`
	AltScore   *float64 `json:"alt_score"`
	Cands      [][]any  `json:"cands"`
}

type p3RefSnap struct {
	AfterStep int             `json:"after_step"`
	PostH     [][]float64     `json:"post_h"`
	W         []float64       `json:"w"`
	Combined  []float64       `json:"combined"`
	PMean     float64         `json:"p_mean"`
	KHat      *int            `json:"k_hat"`
	SHat      *float64        `json:"S_hat"`
	NNeed     *int            `json:"n_need"`
	State     json.RawMessage `json:"state"`
}

type p3RefSteps struct {
	A      [][3]int   `json:"a"`
	Why    []string   `json:"why"`
	EJ     []*float64 `json:"ej"`
	PMean  []float64  `json:"p_mean"`
	Y      []*int     `json:"y"`
	Upd    []int      `json:"upd"`
	N2     []*int     `json:"n2"`
	Reeval []int      `json:"reeval"`
	Pen    []float64  `json:"pen"`
	Alarm  []int      `json:"alarm"`
	Common []float64  `json:"common"`
	NAlarm []int      `json:"n_alarm"`
	Resid  []*float64 `json:"resid"`
	Skip   []*string  `json:"skip"`
}

type p3RefTraj struct {
	ID        string      `json:"id"`
	Err       string      `json:"err,omitempty"`
	Steps     p3RefSteps  `json:"steps"`
	Snapshots []p3RefSnap `json:"snapshots"`
}

func p3Constants() map[string]any {
	ovh := parityDatagramBytes(0, 0)
	return map[string]any{
		"G": p3G[:], "H": p3H[:], "eps": p3Eps, "w_floor": p3WFloor,
		"k_win": p3KWin, "s_win": p3SWin, "hct_win": p3HCTWin, "base_min": p3BaseMin,
		"event_rtt_frac": p3EventFrac, "shield_rtt_ms": p3ShieldRTTMs,
		"shield_e0": p3ShieldE0, "j_tie_ms": float64(jTieMs), "max_ips": quicgoMaxIPS,
		"udp_max": p3UDPMax, "m_max": p3MMax, "k_max": p3KMax,
		"max_steps": maxStepsDefault, "c_pkt": float64(cPktDefault),
		"p_server":        serverPacketSize,
		"parity_overhead": []int{ovh, parityDatagramBytes(0, 1) - ovh},
		"t_pto_ms":        float64(tPTONoAckMs), "t_ack_slope": float64(tAckRetxSlope),
		"t_ack_base_ms":    float64(tAckRetxBaseMs),
		"pto_sampled_mult": float64(ptoSampledRttMult),
		"race_delay_ms":    raceDelayMs, "race_win_q": raceWinQ, "later": p3Later,
		"b0":                  []int{0, 0, 0},
		"policy_version":      p3PolicyVersion,
		"state_version":       p3StateVersion,
		"preflight_ack_bytes": p3PreflightAckBytes,
		"reeval_every":        p3ReevalEvery,
		"guard_common_win":    p3GuardCommonWin,
		"guard_action_win":    p3GuardActionWin,
		"guard_min":           p3GuardMin,
		"guard_rtt_frac":      p3GuardFrac,
		"guard_refresh":       p3GuardRefresh,
	}
}

func p3RefPenMap(rows [][]float64) (map[string]float64, error) {
	if rows == nil {
		return nil, nil
	}
	out := make(map[string]float64, len(rows))
	for _, r := range rows {
		if len(r) != 4 {
			return nil, fmt.Errorf("penalty row %v is not [delta, lead, T, ms]", r)
		}
		a := p3Action{Delta: int(r[0]), Lead: int(r[1]), T: int(r[2])}
		if float64(a.Delta) != r[0] || float64(a.Lead) != r[1] || float64(a.T) != r[2] || !a.valid() {
			return nil, fmt.Errorf("penalty row %v has a bad action", r)
		}
		out[a.Key()] = r[3]
	}
	return out, nil
}

func p3Bit(b bool) int {
	if b {
		return 1
	}
	return 0
}

func p3RefTrajectory(w int, u, cPkt float64, steps *p3RefStepsIn, snapAt map[int]bool) (p3RefSteps, []p3RefSnap, error) {
	n := len(steps.A)
	if len(steps.RTT) != n || len(steps.HCT) != n || len(steps.OK) != n ||
		len(steps.K) != n || len(steps.Srv) != n || len(steps.EJ) != n {
		return p3RefSteps{}, nil, errors.New("step arrays differ in length")
	}
	out := p3RefSteps{A: make([][3]int, 0, n), Why: make([]string, 0, n),
		EJ: make([]*float64, 0, n), PMean: make([]float64, 0, n),
		Y: make([]*int, 0, n), Upd: make([]int, 0, n), N2: make([]*int, 0, n),
		Reeval: make([]int, 0, n), Pen: make([]float64, 0, n), Alarm: make([]int, 0, n),
		Common: make([]float64, 0, n), NAlarm: make([]int, 0, n),
		Resid: make([]*float64, 0, n), Skip: make([]*string, 0, n)}
	snaps := []p3RefSnap{}
	st := newP3State()
	for t := 0; t < n; t++ {
		rtt := steps.RTT[t]
		d, err := p3Decide(st, w, u, rtt, cPkt, false)
		if err != nil {
			return out, snaps, fmt.Errorf("step %d: %v", t, err)
		}
		out.A = append(out.A, d.Action.arr())
		out.Why = append(out.Why, d.Why)
		if d.HasEJ {
			ej, n2 := d.EJ, p3Bit(d.N2)
			out.EJ = append(out.EJ, &ej)
			out.N2 = append(out.N2, &n2)
		} else {
			out.EJ = append(out.EJ, nil)
			out.N2 = append(out.N2, nil)
		}
		out.PMean = append(out.PMean, d.PMean)
		out.Reeval = append(out.Reeval, p3Bit(d.Reeval))
		out.Pen = append(out.Pen, d.Pen)
		out.Alarm = append(out.Alarm, p3Bit(d.GuardAlarm))
		out.Common = append(out.Common, d.GuardCommon)
		out.NAlarm = append(out.NAlarm, d.GuardAlarmed)
		ra := steps.A[t]
		a := p3Action{Delta: ra[0], Lead: ra[1], T: ra[2]}
		hct := math.NaN()
		if steps.HCT[t] != nil {
			hct = *steps.HCT[t]
		}
		info, err := p3Observe(st, a, hct, steps.OK[t] == 1, steps.K[t], steps.Srv[t], rtt, w, u, cPkt,
			steps.EJ[t])
		if err != nil {
			return out, snaps, fmt.Errorf("step %d: %v", t, err)
		}
		if info.Y >= 0 {
			y := info.Y
			out.Y = append(out.Y, &y)
		} else {
			out.Y = append(out.Y, nil)
		}
		out.Upd = append(out.Upd, p3Bit(info.Updated))
		if info.HasResid {
			r := info.Resid
			out.Resid = append(out.Resid, &r)
		} else {
			out.Resid = append(out.Resid, nil)
		}
		if info.Skip != "" {
			sk := info.Skip
			out.Skip = append(out.Skip, &sk)
		} else {
			out.Skip = append(out.Skip, nil)
		}
		if snapAt[t+1] {
			post := p3Combined(st)
			sn := p3RefSnap{AfterStep: t + 1, Combined: post, PMean: p3PostMean(post)}
			for _, row := range st.Post {
				sn.PostH = append(sn.PostH, append([]float64(nil), row...))
			}
			sn.W = append([]float64(nil), st.W...)
			if k, ok := st.kHat(); ok {
				sn.KHat = &k
			}
			if s, ok := st.sHat(); ok {
				sn.SHat = &s
			}
			if c, ok := p3Context(st, w, u, rtt, cPkt); ok {
				nn := c.NNeed
				sn.NNeed = &nn
			}
			raw, err := json.Marshal(st)
			if err != nil {
				return out, snaps, err
			}
			sn.State = raw
			snaps = append(snaps, sn)
		}
	}
	return out, snaps, nil
}

func policy3RefMain(in io.Reader, out io.Writer) int {
	t0 := time.Now()
	var doc p3RefIn
	dec := json.NewDecoder(in)
	if err := dec.Decode(&doc); err != nil {
		fmt.Fprintln(os.Stderr, "policy3ref: reading input:", err)
		return 2
	}
	res := map[string]any{"schema": "padfec3.policy3_go/2", "constants": p3Constants(),
		"binary": filepath.Base(os.Args[0])}
	prims := make([]p3RefPrim, 0, len(doc.Primitives))
	for _, p := range doc.Primitives {
		pt := p3Evaluate(p.K, p.WEff, p.M, p.Lead, p.P, p.RTT, p.U, p.NNeed)
		prims = append(prims, p3RefPrim{ID: p.ID, APre: p3PreflightBytes(p.K, p.U), J: pt.J,
			E: pt.E, P2: pt.P2, PF: pt.PF, P1: pt.P1})
	}
	res["primitives"] = prims
	t1 := time.Now()
	decs := make([]p3RefDec, 0, len(doc.Decisions))
	for _, d := range doc.Decisions {
		post := make([]float64, p3NG)
		r := p3RefDec{ID: d.ID}
		if len(d.G) != len(d.Q) {
			r.Err = "g and q differ in length"
			decs = append(decs, r)
			continue
		}
		bad := false
		for i, g := range d.G {
			if g < 0 || g >= p3NG {
				bad = true
				break
			}
			post[g] = d.Q[i]
		}
		if bad {
			r.Err = "g index out of range"
			decs = append(decs, r)
			continue
		}
		pen, err := p3RefPenMap(d.Pen)
		if err != nil {
			r.Err = err.Error()
			decs = append(decs, r)
			continue
		}
		cd, err := p3DecideCore(post, d.K, d.W, d.S, d.U, d.RTT, cPktDefault, true, pen, false)
		if err != nil {
			r.Err = err.Error()
			decs = append(decs, r)
			continue
		}
		r.NNeed, r.NCands, r.CandHash = cd.NNeed, cd.NCands, cd.CandHash
		r.Action, r.Mode, r.EJ, r.JMin, r.NTied = cd.Action.arr(), cd.Mode, cd.EJ, cd.JMin, cd.NTied
		r.PenChosen, r.Score, r.N2, r.ReevalCond = cd.Pen, cd.Score, cd.N2, cd.ReevalCond
		if cd.HasAlt {
			alt, ej, sc := cd.Alt.Action.arr(), cd.Alt.EJ, cd.Alt.Score
			r.Alt, r.AltEJ, r.AltScore = &alt, &ej, &sc
		}
		for _, c := range cd.Cands {
			r.Cands = append(r.Cands, []any{c.Action.Delta, c.Action.Lead, c.Action.T, c.EJ,
				p3Bit(c.N2), c.Pen})
		}
		decs = append(decs, r)
		if p3MemoSize() > p3MemoCap/2 {
			p3MemoReset()
		}
	}
	res["decisions"] = decs
	t2 := time.Now()
	trajs := make([]p3RefTraj, 0, len(doc.Trajectories))
	for i := range doc.Trajectories {
		tr := &doc.Trajectories[i]
		p3MemoReset()
		snapAt := map[int]bool{}
		for _, s := range tr.Snapshots {
			snapAt[s.AfterStep] = true
		}
		o := p3RefTraj{ID: tr.ID}
		if tr.CPkt != float64(cPktDefault) {
			o.Err = fmt.Sprintf("trajectory c_pkt %v differs from the binary's %v", tr.CPkt, float64(cPktDefault))
		}
		steps, snaps, err := p3RefTrajectory(tr.W, tr.U, cPktDefault, &tr.Steps, snapAt)
		if err != nil && o.Err == "" {
			o.Err = err.Error()
		}
		o.Steps, o.Snapshots = steps, snaps
		trajs = append(trajs, o)
	}
	res["trajectories"] = trajs
	t3 := time.Now()
	res["timing_s"] = map[string]float64{"primitives": t1.Sub(t0).Seconds(),
		"decisions": t2.Sub(t1).Seconds(), "trajectories": t3.Sub(t2).Seconds()}
	b, err := json.Marshal(res)
	if err != nil {
		fmt.Fprintln(os.Stderr, "policy3ref: encoding output:", err)
		return 2
	}
	b = append(b, '\n')
	if _, err := out.Write(b); err != nil {
		fmt.Fprintln(os.Stderr, "policy3ref: writing output:", err)
		return 2
	}
	return 0
}
