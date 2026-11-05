package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"maps"
	"math"
	"os"
	"path/filepath"
	"slices"
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
	p3StateVersion      = 4
	p3UDPMax            = parityDatagramMax
	p3Later             = "v3"
	p3CacheSchema       = "padfec3.cache3/3"
	p3MemoCap           = 100000
	p3PreflightAckBytes = 41
	p3PolicyVersion     = "v3.3-dev"
	p3ReevalEvery       = 16
	p3GuardCommonWin    = 64
	p3GuardActionWin    = 32
	p3GuardMin          = 8
	p3GuardRefresh      = 64
	p3SkipShield        = "shield"
	p3SkipNominal2      = "nominal2"
	p3SkipGuard         = "guard"
	p3MaxExactInt       = (1 << 53) - 1
	p3NNeedMax          = p3MaxExactInt / serverPacketSize
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
	return a.Delta >= 0 && a.Delta <= p3MaxExactInt &&
		a.Lead >= 0 && a.Lead <= p3MMax && a.T >= 0 && a.T <= p3MMax &&
		a.Lead+a.T <= p3MMax
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
	K     int     `json:"k"`
	S     float64 `json:"S"`
	NNeed int     `json:"n_need"`
	W     int     `json:"W"`
	U     float64 `json:"u"`
	RTT   float64 `json:"rtt"`
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
	Predict      int `json:"predict"`
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
	Datagram     int `json:"datagram"`
	Categorical  int `json:"categorical"`
	PredictOnly  int `json:"predict_only"`
	ArrC1        int `json:"arr_c1"`
	ArrACK       int `json:"arr_ack"`
	ArrNone      int `json:"arr_none"`
	ArrTrunc     int `json:"arr_trunc"`
	ArrEmpty     int `json:"arr_empty"`
	ArrSent      int `json:"arr_sent"`
	ArrLost      int `json:"arr_lost"`
	GradeOne     int `json:"grade_one_rtt"`
	GradeTwo     int `json:"grade_two_rtt"`
	GradeLate    int `json:"grade_late_or_failure"`
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

func p3ValidateMass(xs []float64, n int, name string) error {
	if len(xs) != n {
		return fmt.Errorf("%s has %d entries, want %d", name, len(xs), n)
	}
	for _, x := range xs {
		if !p3Finite(x) || x < 0 {
			return fmt.Errorf("%s has a negative or non-finite entry", name)
		}
	}
	mass := p3PySum(xs)
	if !p3Finite(mass) || math.Abs(mass-1) > 1e-9 {
		return fmt.Errorf("%s mass %v, want 1 within 1e-9", name, mass)
	}
	return nil
}

// p3BinNeededChecked preserves binNeeded's floating-point comparisons while
// keeping its integer byte products exact and limiting correction to one step.
func p3BinNeededChecked(s float64, baseBin int, cPkt float64) (int, error) {
	if !p3Finite(s) || s <= 0 || !p3Finite(cPkt) || cPkt < 0 || cPkt >= serverPacketSize {
		return 0, errors.New("invalid server bytes or c_pkt for bin calculation")
	}
	if baseBin < 0 || baseBin > p3NNeedMax {
		return 0, errors.New("base bin exceeds exact integer byte range")
	}
	s0abs := s - float64(baseBin)*cPkt
	den := float64(serverPacketSize) - cPkt
	q := s0abs / den
	if !p3Finite(q) || math.Abs(q) > float64(p3NNeedMax) {
		return 0, errors.New("needed bins exceed exact integer byte range")
	}
	n := int(q)
	needsMore := func(n int) bool {
		return float64(n*serverPacketSize) < s0abs+float64(n)*cPkt
	}
	if needsMore(n) {
		n++
		if n > p3NNeedMax || needsMore(n) {
			return 0, errors.New("bin correction exceeds floating-point representability")
		}
	}
	if n < 1 {
		n = 1
	}
	return n, nil
}

func p3ValidateInputs(w int, u, rtt, cPkt float64, allowMissingRTT bool) error {
	if w < p3MinW {
		return fmt.Errorf("W must be >= %d: %d", p3MinW, w)
	}
	flight := float64(p3KMax+p3MMax)*float64(w) +
		float64(p3MMax*parityDatagramBytes(0, p3KMax)+maxStepsDefault*serverPacketSize)
	if float64(amplificationFactor)*flight > float64(p3MaxExactInt) {
		return errors.New("client credit exceeds exact integer byte range")
	}
	if !p3Finite(u) || u < 0 {
		return fmt.Errorf("u must be finite and >= 0, got %v", u)
	}
	if !p3Finite(cPkt) || cPkt < 0 || cPkt >= 1280 {
		return fmt.Errorf("c_pkt must be finite and in [0, 1280), got %v", cPkt)
	}
	if !p3Finite(rtt) || rtt < 0 || (!allowMissingRTT && rtt == 0) {
		if allowMissingRTT {
			return fmt.Errorf("rtt must be finite and >= 0, got %v", rtt)
		}
		return fmt.Errorf("rtt must be finite and > 0, got %v", rtt)
	}
	serial := 0.0
	if u > 0 {
		den := u * 1e3
		if !p3Finite(den) {
			return errors.New("bandwidth conversion exceeds floating-point range")
		}
		serial = flight * 8 / den
	}
	costBound := (3*serial + (2+ptoSampledRttMult)*rtt +
		tPTONoAckMs + tAckRetxBaseMs + 0.3) / math.Pow(1-p3G[p3NG-1], p3KMax)
	if !p3Finite(costBound) {
		return errors.New("model time arithmetic exceeds floating-point range")
	}
	return nil
}

func p3ValidateStateBins(st *p3State, w int, cPkt float64) error {
	k, okK := st.kHat()
	s, okS := st.sHat()
	if !okK || !okS || k < 1 || k > p3KMax {
		return nil
	}
	_, err := p3BinNeededChecked(s, binIndex(k*w), cPkt)
	return err
}

func (st *p3State) validate() error {
	if st == nil {
		return errors.New("state is nil")
	}
	if st.V != p3StateVersion {
		return fmt.Errorf("state version %d, want %d", st.V, p3StateVersion)
	}
	if len(st.Post) != p3NH {
		return fmt.Errorf("posterior has %d rows, want %d", len(st.Post), p3NH)
	}
	for j, row := range st.Post {
		if err := p3ValidateMass(row, p3NG, fmt.Sprintf("posterior row %d", j)); err != nil {
			return err
		}
	}
	if err := p3ValidateMass(st.W, p3NH, "weights"); err != nil {
		return err
	}
	if len(st.KHist) > p3KWin || len(st.SHist) > p3SWin {
		return errors.New("k or S window longer than its cap")
	}
	for _, x := range st.KHist {
		if x <= 0 {
			return errors.New("k window has a non-positive entry")
		}
	}
	for _, x := range st.SHist {
		if !p3Finite(x) || x <= 0 {
			return errors.New("S window has a non-positive or non-finite entry")
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
			if !p3Finite(x) || x <= 0 {
				return fmt.Errorf("hct window %s has a non-positive or non-finite entry", k)
			}
		}
		if _, ok := st.HCTSeq[k]; !ok {
			return fmt.Errorf("hct window %s has no sequence number", k)
		}
	}
	for k, seq := range st.HCTSeq {
		if _, err := parseP3Key(k); err != nil {
			return err
		}
		if seq < 0 {
			return fmt.Errorf("hct sequence %s is negative", k)
		}
	}
	if st.Seq < 0 || st.NDec < 0 || st.NReeval < 0 {
		return errors.New("negative sequence or decision counter")
	}
	for _, counter := range []struct {
		name  string
		value int
	}{
		{"obs", st.Stats.Obs}, {"predict", st.Stats.Predict}, {"upd", st.Stats.Upd},
		{"shield", st.Stats.Shield}, {"nominal2", st.Stats.Nominal2}, {"guard", st.Stats.Guard},
		{"no_base", st.Stats.NoBase}, {"no_ctx", st.Stats.NoCtx}, {"events", st.Stats.Events},
		{"fail", st.Stats.Fail}, {"resid", st.Stats.Resid}, {"reeval", st.Stats.Reeval},
		{"alarm_raised", st.Stats.AlarmRaised}, {"alarm_cleared", st.Stats.AlarmCleared},
		{"datagram", st.Stats.Datagram}, {"categorical", st.Stats.Categorical},
		{"predict_only", st.Stats.PredictOnly}, {"arr_c1", st.Stats.ArrC1},
		{"arr_ack", st.Stats.ArrACK}, {"arr_none", st.Stats.ArrNone},
		{"arr_trunc", st.Stats.ArrTrunc}, {"arr_empty", st.Stats.ArrEmpty},
		{"arr_sent", st.Stats.ArrSent}, {"arr_lost", st.Stats.ArrLost},
		{"grade_one_rtt", st.Stats.GradeOne}, {"grade_two_rtt", st.Stats.GradeTwo},
		{"grade_late_or_failure", st.Stats.GradeLate},
	} {
		if counter.value < 0 {
			return fmt.Errorf("negative stats counter %s", counter.name)
		}
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
	return p3ValidateGuardGaps(st)
}

func p3ValidateGuardGaps(st *p3State) error {
	b := p3GuardCommon(st)
	for key, win := range st.GResid {
		if len(win) > 0 && !p3Finite(p3Median(win)-b) {
			return fmt.Errorf("guard residual gap %s exceeds floating-point range", key)
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
	sum := s[h-1] + s[h]
	if p3Finite(sum) {
		return sum / 2.0
	}
	return s[h-1]/2.0 + s[h]/2.0
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
	if st == nil || p3ValidateInputs(w, u, rtt, cPkt, false) != nil {
		return nil, false
	}
	k, okK := st.kHat()
	s, okS := st.sHat()
	if !okK || !okS {
		return nil, false
	}
	if k < 1 || k > p3KMax {
		return nil, false
	}
	if !p3Finite(s) || s <= 0 {
		return nil, false
	}
	nNeed, err := p3BinNeededChecked(s, binIndex(k*w), cPkt)
	if err != nil {
		return nil, false
	}
	return &p3Ctx{K: k, S: s, NNeed: nNeed, W: w, U: u, RTT: rtt}, true
}

// p3PredictStep advances the channel prior without treating a skipped observation
// as evidence for either loss outcome or for a particular hazard.
func p3PredictStep(post [][]float64, w []float64) ([][]float64, []float64) {
	inv := 1.0 / float64(p3NG)
	newPost := make([][]float64, p3NH)
	for j := 0; j < p3NH; j++ {
		h := p3H[j]
		newPost[j] = make([]float64, p3NG)
		for i := 0; i < p3NG; i++ {
			newPost[j][i] = float64((1.0-h)*post[j][i]) + float64(h*inv)
		}
	}
	return newPost, append([]float64(nil), w...)
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
	x := p3Median(win) - b
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
		if len(win) >= p3GuardMin && p3Median(win)-b > lim {
			st.GAlarm[key] = st.NDec
			raised = append(raised, key)
		}
	}
	st.Stats.AlarmRaised += len(raised)
	return raised
}

func p3GuardObserve(st *p3State, key string, resid, rtt float64) []string {
	st.GResid[key] = p3PushFloat(st.GResid[key], resid, p3GuardActionWin)
	st.GCommon = p3PushFloat(st.GCommon, resid, p3GuardCommonWin)
	st.Stats.Resid++
	return p3GuardCheck(st, rtt)
}

type p3ObsInfo struct {
	Evidence       p3Arrivals
	Grade          int
	Cut1           float64
	Cut2           float64
	CutoffRTT      float64
	LegacySkip     string
	LegacyShielded bool
	ArrivalReject  string
	LossUpdateKind string
	Y              int
	Baseline       float64
	HasBase        bool
	Ref            string
	Updated        bool
	Shielded       bool
	HasCtx         bool
	Skip           string
	HasResid       bool
	Resid          float64
	Alarmed        bool
	Raised         []string
	Common         float64
	NAlarm         int
}

func p3Observe(st *p3State, a p3Action, hct float64, ok bool, kObs int, srv float64,
	rtt float64, w int, u, cPkt float64, jPred *float64, arrivals ...*p3Arrivals) (p3ObsInfo, error) {
	evidence, err := p3NormalizeArrivals(arrivals)
	if err != nil {
		return p3ObsInfo{Y: -1, Grade: -1}, err
	}
	if err := st.validate(); err != nil {
		return p3ObsInfo{Y: -1, Grade: -1}, err
	}
	next := p3CloneState(st)
	info, err := p3ObserveCandidate(next, a, hct, ok, kObs, srv, rtt, w, u, cPkt, jPred, evidence)
	if err == nil {
		*st = *next
	}
	return info, err
}

func p3ObserveCandidate(st *p3State, a p3Action, hct float64, ok bool, kObs int, srv float64,
	rtt float64, w int, u, cPkt float64, jPred *float64, evidence p3Arrivals) (p3ObsInfo, error) {
	if err := p3ValidateInputs(w, u, rtt, cPkt, true); err != nil {
		return p3ObsInfo{Y: -1}, err
	}
	if !p3Finite(srv) || srv < 0 {
		return p3ObsInfo{Y: -1}, fmt.Errorf("srv must be finite and >= 0, got %v", srv)
	}
	if !a.valid() {
		return p3ObsInfo{Y: -1}, fmt.Errorf("invalid action %+v", a)
	}
	if err := p3ValidateInputs(w+a.Delta, u, rtt, cPkt, true); err != nil {
		return p3ObsInfo{Y: -1}, err
	}
	key := a.Key()
	if ok && (!p3Finite(hct) || hct <= 0) {
		return p3ObsInfo{Y: -1}, fmt.Errorf("ok observation needs hct > 0, got %v", hct)
	}
	if jPred != nil && !p3Finite(*jPred) {
		return p3ObsInfo{Y: -1}, fmt.Errorf("j_pred must be finite, got %v", *jPred)
	}
	if ok && jPred != nil && !p3Finite(hct-*jPred) {
		return p3ObsInfo{Y: -1}, errors.New("residual exceeds floating-point range")
	}
	if err := st.validate(); err != nil {
		return p3ObsInfo{Y: -1}, err
	}
	if err := p3ValidateStateBins(st, w, cPkt); err != nil {
		return p3ObsInfo{Y: -1}, err
	}
	if srv > 0 {
		for k := 1; k <= p3KMax; k++ {
			if _, err := p3BinNeededChecked(srv, binIndex(k*w), cPkt); err != nil {
				return p3ObsInfo{Y: -1}, err
			}
		}
	}
	if ok && jPred != nil {
		preview := p3CloneState(st)
		p3GuardObserve(preview, key, hct-*jPred, rtt)
		if err := p3ValidateGuardGaps(preview); err != nil {
			return p3ObsInfo{Y: -1}, err
		}
	}
	c, hasCtx := p3Context(st, w, u, rtt, cPkt)
	grade, cut1, cut2, err := p3ClassifyHCT(c, a, hct, ok)
	if err != nil {
		return p3ObsInfo{Y: -1, Grade: -1}, err
	}
	b, ref, hasB := p3Baseline(st, c, a)
	if hasB && !p3Finite(b) {
		return p3ObsInfo{Y: -1}, errors.New("HCT baseline exceeds floating-point range")
	}
	st.Stats.Obs++
	st.Stats.Predict++
	if !ok {
		st.Stats.Fail++
	}
	info := p3ObsInfo{Y: -1, Baseline: b, HasBase: hasB, Ref: ref, HasCtx: hasCtx,
		Grade: grade, Cut1: cut1, Cut2: cut2, CutoffRTT: rtt, Evidence: evidence, Raised: []string{}}
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
		info.LegacySkip = "no_base"
	case !hasCtx:
		st.Stats.NoCtx++
		info.LegacySkip = "no_ctx"
	case skip != "":
		switch skip {
		case p3SkipShield:
			st.Stats.Shield++
		case p3SkipNominal2:
			st.Stats.Nominal2++
		default:
			st.Stats.Guard++
		}
		info.LegacySkip = skip
	}
	info.LegacyShielded = skip == p3SkipShield
	if info.Y == 1 {
		st.Stats.Events++
	}
	switch evidence.Src {
	case "c1":
		st.Stats.ArrC1++
	case "ack":
		st.Stats.ArrACK++
	case "none":
		st.Stats.ArrNone++
	}
	if evidence.Trunc {
		st.Stats.ArrTrunc++
	}
	if evidence.Sent == 0 {
		st.Stats.ArrEmpty++
	}
	switch grade {
	case 0:
		st.Stats.GradeOne++
	case 1:
		st.Stats.GradeTwo++
	case 2:
		st.Stats.GradeLate++
	}
	switch {
	case evidence.Src == "none":
		info.ArrivalReject = "source_none"
	case evidence.Trunc:
		info.ArrivalReject = "truncated"
	case evidence.Sent == 0:
		info.ArrivalReject = "empty"
	}
	var likelihood []float64
	if info.ArrivalReject == "" {
		likelihood, err = p3ArrivalLikelihood(evidence.Sent, evidence.Lost)
		info.LossUpdateKind = "datagram"
		st.Stats.Datagram++
		st.Stats.ArrSent += evidence.Sent
		st.Stats.ArrLost += evidence.Lost
	} else if hasCtx {
		likelihood, err = p3ClassLikelihood(c, a, grade)
		info.LossUpdateKind = "categorical"
		st.Stats.Categorical++
	} else {
		info.LossUpdateKind = "predict_only"
		info.Skip = "no_ctx"
		st.Stats.PredictOnly++
	}
	if err != nil {
		return info, err
	}
	if likelihood == nil {
		st.Post, st.W = p3PredictStep(st.Post, st.W)
	} else {
		st.Post, st.W = p3FilterStep(st.Post, st.W, likelihood)
		st.Stats.Upd++
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
	if k < 1 || k > p3KMax || p3ValidateInputs(w, 0, 0, cPkt, true) != nil {
		return nil
	}
	if _, err := p3BinNeededChecked(s, binIndex(k*w), cPkt); err != nil {
		return nil
	}
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
	if err := p3ValidateInputs(w, u, rtt, cPkt, false); err != nil {
		return p3Decision{}, err
	}
	if err := p3ValidateMass(post, p3NG, "posterior"); err != nil {
		return p3Decision{}, err
	}
	if k < 1 || k > p3KMax {
		return p3Decision{}, fmt.Errorf("k out of range: %d", k)
	}
	if !p3Finite(s) || s <= 0 {
		return p3Decision{}, fmt.Errorf("S must be finite and > 0, got %v", s)
	}
	nNeed, err := p3BinNeededChecked(s, binIndex(k*w), cPkt)
	if err != nil {
		return p3Decision{}, err
	}
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
			if !p3Finite(pt.J) {
				return p3Decision{}, errors.New("model cost exceeds floating-point range")
			}
			ej += float64(post[g] * pt.J)
		}
		c.EJ = ej
		c.Pen = pen[c.Action.Key()]
		c.Score = c.EJ + c.Pen
		if !p3Finite(c.Score) {
			return p3Decision{}, errors.New("candidate score exceeds floating-point range")
		}
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
	if err := p3ValidateInputs(w, u, rtt, cPkt, true); err != nil {
		return p3Decision{}, err
	}
	if err := st.validate(); err != nil {
		return p3Decision{}, err
	}
	if err := p3ValidateStateBins(st, w, cPkt); err != nil {
		return p3Decision{}, err
	}
	post := p3Combined(st)
	if err := p3ValidateMass(post, p3NG, "combined posterior"); err != nil {
		return p3Decision{}, err
	}
	b := p3GuardCommon(st)
	pen := p3GuardPenalties(st, b)
	for key, at := range st.GAlarm {
		if st.NDec-at >= p3GuardRefresh {
			delete(pen, key)
		}
	}
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
		sm := p3PostSummary(post)
		d.PMean, d.PMap, d.PGe010 = sm.PMean, sm.PMap, sm.PGe010
	}
	cleared := p3GuardRelease(st)
	st.NDec++
	if d.ReevalCond {
		st.NReeval++
		if st.NReeval%p3ReevalEvery == 0 {
			d.take(d.Alt)
			d.Why = "reeval"
			d.Reeval = true
			st.Stats.Reeval++
		}
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

func (e *cache3Entry) validate() error {
	if e == nil || e.State == nil {
		return errors.New("destination has no state")
	}
	if !p3Finite(e.MinRTT) || e.MinRTT < 0 || !p3Finite(e.MinHCT) || e.MinHCT < 0 {
		return errors.New("cache minimum RTT and HCT must be finite and nonnegative")
	}
	if e.RTTObs < 0 || e.Conns < 0 {
		return errors.New("cache observation and connection counters must be nonnegative")
	}
	return e.State.validate()
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
	var trailing any
	if err := dec.Decode(&trailing); err != io.EOF {
		if err == nil {
			err = errors.New("more than one JSON document")
		}
		return nil, fmt.Errorf("%s: trailing cache data: %v", path, err)
	}
	if f.Schema != p3CacheSchema {
		return nil, fmt.Errorf("%s: schema %q, want %q", path, f.Schema, p3CacheSchema)
	}
	for addr, e := range f.Dests {
		if e == nil || e.State == nil {
			return nil, fmt.Errorf("%s: destination %s has no state", path, addr)
		}
		e.State.normalize()
		if err := e.validate(); err != nil {
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
	for addr, e := range c.Dests {
		if err := e.validate(); err != nil {
			c.mu.Unlock()
			return fmt.Errorf("destination %s: %v", addr, err)
		}
	}
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

func p3CloneState(st *p3State) *p3State {
	if st == nil {
		return nil
	}
	next := *st
	next.KHist = slices.Clone(st.KHist)
	next.SHist = slices.Clone(st.SHist)
	next.Post = slices.Clone(st.Post)
	for j, row := range st.Post {
		next.Post[j] = slices.Clone(row)
	}
	next.W = slices.Clone(st.W)
	next.HCT = maps.Clone(st.HCT)
	for key, win := range st.HCT {
		next.HCT[key] = slices.Clone(win)
	}
	next.HCTSeq = maps.Clone(st.HCTSeq)
	next.GResid = maps.Clone(st.GResid)
	for key, win := range st.GResid {
		next.GResid[key] = slices.Clone(win)
	}
	next.GCommon = slices.Clone(st.GCommon)
	next.GAlarm = maps.Clone(st.GAlarm)
	return &next
}

// candidate and commit are called with c.mu held. Failed policy calls never
// publish their candidate, including destination creation and RTT metadata.
func (c *destCache3) candidate(addr string) *cache3Entry {
	e := c.Dests[addr]
	if e == nil {
		return &cache3Entry{State: newP3State()}
	}
	next := *e
	next.State = p3CloneState(e.State)
	return &next
}

func (c *destCache3) commit(addr string, next *cache3Entry) {
	e := c.Dests[addr]
	if e == nil {
		c.Dests[addr] = next
		return
	}
	if e.State != nil && next.State != nil {
		*e.State = *next.State
		next.State = e.State
	}
	*e = *next
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
	e := c.candidate(addr)
	if err := e.validate(); err != nil {
		return auto3Plan{}, err
	}
	rtt, src := e.policyRTT()
	d, err := p3Decide(e.State, w, u, rtt, cPkt, false)
	if err != nil {
		return auto3Plan{}, err
	}
	c.commit(addr, e)
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
	srv float64, pathRTT float64, pathValid bool, w int, u, cPkt float64, arrivals ...*p3Arrivals) (p3ObsInfo, float64, error) {
	return c.observePred(addr, a, nil, hct, ok, kObs, srv, pathRTT, pathValid, w, u, cPkt, arrivals...)
}

func (c *destCache3) observePred(addr string, a p3Action, jPred *float64, hct float64, ok bool,
	kObs int, srv float64, pathRTT float64, pathValid bool, w int, u, cPkt float64, arrivals ...*p3Arrivals) (p3ObsInfo, float64, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	e := c.candidate(addr)
	if err := e.validate(); err != nil {
		return p3ObsInfo{Y: -1}, 0, err
	}
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
	if err := e.validate(); err != nil {
		return p3ObsInfo{Y: -1}, 0, err
	}
	rtt, _ := e.policyRTT()
	info, err := p3Observe(e.State, a, hct, ok, kObs, srv, rtt, w, u, cPkt, jPred, arrivals...)
	if err != nil {
		return info, 0, err
	}
	after := p3PostMean(p3Combined(e.State))
	c.commit(addr, e)
	return info, after, nil
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
	L1         *p3L1Reference `json:"l1"`
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
		"class_eps": p3ClassEps, "class_c_proc_ms": p3ClassCProcMs, "class_names": p3ClassNames,
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
	if doc.L1 != nil {
		l1, err := p3RunL1Reference(doc.L1)
		if err != nil {
			fmt.Fprintln(os.Stderr, "policy3ref: L1:", err)
			return 2
		}
		res["l1"] = l1
	}
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
