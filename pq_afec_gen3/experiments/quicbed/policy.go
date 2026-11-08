package main

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"sort"
	"sync"
)

const serverPacketSize = 1280
const amplificationFactor = 3

func allowedBytes(clientBytes int) int {
	b := amplificationFactor * clientBytes
	if b <= 0 {
		return 0
	}
	n := (b-1)/serverPacketSize + 1
	return n * serverPacketSize
}

func parityDatagramBytes(w, k int) int {
	return w + 39 + 6*k
}

func criticalPathBytes(k, m, w int) int {
	if m >= 2 {
		return k*w + parityDatagramBytes(w, k)
	}
	return k * w
}

func idxNearest(xs []int, v int) int {
	best, bd := 0, 1<<30
	for i, x := range xs {
		d := x - v
		if d < 0 {
			d = -d
		}
		if d < bd {
			bd, best = d, i
		}
	}
	return best
}

func normBurst(p, l float64) float64 {
	pc := p
	if pc < 0 {
		pc = 0
	}
	if pc > 0.999 {
		pc = 0.999
	}
	return l * (1.0 - pc)
}

func axisLerp(xs []float64, v float64) (int, int, float64) {
	if len(xs) < 2 {
		return 0, 0, 0
	}
	lo := 0
	for lo < len(xs)-2 && xs[lo+1] < v {
		lo++
	}
	hi := lo + 1
	span := xs[hi] - xs[lo]
	t := 0.0
	if span > 0 {
		t = (v - xs[lo]) / span
	}
	if t < 0 {
		t = 0
	}
	if t > 1 {
		t = 1
	}
	return lo, hi, t
}

func recoveryGroup(m int) int {
	if m <= 0 {
		return 0
	}
	if m == 1 {
		return 1
	}
	return m - 1
}

func jointLookup(k, m int, p, l float64) []float64 {
	ki := idxNearest(pfailK, k)
	mi := idxNearest(pfailM, m)
	if k != pfailK[ki] || m != pfailM[mi] {
		panic(fmt.Sprintf(
			"jointLookup: 표 범위 밖 (k=%d m=%d). 표는 k=%v m=%v 만 담는다 - "+
				"padfec/table.py 의 K_VALS/M_VALS 를 늘리고 다시 심어라",
			k, m, pfailK, pfailM))
	}
	row := jointTable4[ki][mi]

	plo, phi, t := axisLerp(pfailP, p)
	llo, lhi, tl := axisLerp(pfailU, normBurst(p, l))

	a00, a10 := row[plo][llo], row[phi][llo]
	a01, a11 := row[plo][lhi], row[phi][lhi]
	w00 := (1 - t) * (1 - tl)
	w10 := t * (1 - tl)
	w01 := (1 - t) * tl
	w11 := t * tl
	out := make([]float64, len(a00))
	for i := range a00 {
		out[i] = a00[i]*w00 + a10[i]*w10 + a01[i]*w01 + a11[i]*w11
	}
	return out
}

func failFracLookup(k, m int, p, l float64) (float64, float64, float64) {
	ki := idxNearest(pfailK, k)
	mi := idxNearest(pfailM, m)
	if k != pfailK[ki] || m != pfailM[mi] {
		panic(fmt.Sprintf(
			"failFracLookup: 표 범위 밖 (k=%d m=%d)", k, m))
	}
	row := failFracTable[ki][mi]

	plo, phi, t := axisLerp(pfailP, p)
	llo, lhi, tl := axisLerp(pfailU, normBurst(p, l))

	a00, a10 := row[plo][llo], row[phi][llo]
	a01, a11 := row[plo][lhi], row[phi][lhi]
	w00 := (1 - t) * (1 - tl)
	w10 := t * (1 - tl)
	w01 := (1 - t) * tl
	w11 := t * tl
	f0 := a00[0]*w00 + a10[0]*w10 + a01[0]*w01 + a11[0]*w11
	f1 := a00[1]*w00 + a10[1]*w10 + a01[1]*w01 + a11[1]*w11
	f2 := a00[2]*w00 + a10[2]*w10 + a01[2]*w01 + a11[2]*w11
	sum := f0 + f1 + f2
	if sum <= 0 {
		return 1, 0, 0
	}
	return f0 / sum, f1 / sum, f2 / sum
}

func roundMultLookup(k, m int, p, l float64) float64 {
	ki := idxNearest(pfailK, k)
	mi := idxNearest(pfailM, m)
	if k != pfailK[ki] || m != pfailM[mi] {
		panic(fmt.Sprintf("roundMultLookup: 표 범위 밖 (k=%d m=%d)", k, m))
	}
	row := roundMultTable[ki][mi]
	plo, phi, t := axisLerp(pfailP, p)
	llo, lhi, tl := axisLerp(pfailU, normBurst(p, l))
	a00, a10 := row[plo][llo], row[phi][llo]
	a01, a11 := row[plo][lhi], row[phi][lhi]
	return a00*(1-t)*(1-tl) + a10*t*(1-tl) + a01*(1-t)*tl + a11*t*tl
}

func defaultTRecover(rttMs float64, arrivedAny bool) float64 {
	if arrivedAny {
		return tAckRetxSlope*rttMs + tAckRetxBaseMs
	}
	return tPTONoAckMs
}

func trailingParityDelayMs(k, w int, uplinkMbps float64) float64 {
	if uplinkMbps <= 0 {
		return 0.0
	}
	return float64(parityDatagramBytes(w, k)) * 8.0 /
		(uplinkMbps * 1e6) * 1e3
}

func raceWinProb(delayMs float64) float64 {
	n := len(raceDelayMs)
	if delayMs <= raceDelayMs[0] {
		return raceWinQ[0]
	}
	if delayMs >= raceDelayMs[n-1] {
		return 0.0
	}
	for i := 1; i < n; i++ {
		if delayMs <= raceDelayMs[i] {
			lo, hi := raceDelayMs[i-1], raceDelayMs[i]
			t := (delayMs - lo) / (hi - lo)
			return raceWinQ[i-1] + t*(raceWinQ[i]-raceWinQ[i-1])
		}
	}
	return 0.0
}

type creditBranch struct {
	wgt   float64
	bytes int
}

func creditBranches(a, w, parity, leadArrived, nTrail int,
	trailDelayMs float64) []creditBranch {
	base := a * w
	if leadArrived > 0 {
		base += parity
	}
	out := make([]creditBranch, 0, 4)
	prev := 1.0
	for i := 1; i <= nTrail; i++ {
		qi := raceWinProb(float64(i) * trailDelayMs)
		if prev-qi > 0.0 {
			out = append(out, creditBranch{
				wgt: prev - qi, bytes: base + (i-1)*parity})
		}
		prev = qi
	}
	if prev > 0.0 {
		out = append(out, creditBranch{wgt: prev, bytes: base + nTrail*parity})
	}
	return out
}

func flightOutcome(k, m, w int, p, l float64,
	nStar int, trailDelayMs float64) (nExp, pFail, pRec, trailBytes float64) {
	parity := parityDatagramBytes(w, k)
	pm := jointLookup(k, m, p, l)
	cols := m + 1
	g := recoveryGroup(m)
	cw := g + 1
	for a := 0; a <= k; a++ {
		for b := 0; b < cols; b++ {
			for r := 0; r < cw; r++ {
				idx := (a*cols+b)*cw + r
				if idx >= len(pm) {
					continue
				}
				pr := pm[idx]
				if pr <= 0 {
					continue
				}
				miss := k - a
				rec := miss >= 1 && miss <= r
				if miss > 0 && !rec {
					pFail += pr
					continue
				}
				used := 0
				if rec {
					used = miss
				}
				_ = used
				if rec {
					pRec += pr
					trailBytes += pr * float64(parity*miss)
					for _, br := range creditBranches(a+miss, w, parity,
						b-r, r-miss, trailDelayMs) {
						if binIndex(br.bytes) < nStar {
							nExp += pr * br.wgt * 2.0
						} else {
							nExp += pr * br.wgt
						}
					}
					continue
				}
				for _, br := range creditBranches(a, w, parity, b-r, r,
					trailDelayMs) {
					if binIndex(br.bytes) < nStar {
						nExp += pr * br.wgt * 2.0
					} else {
						nExp += pr * br.wgt
					}
				}
			}
		}
	}
	return nExp, pFail, pRec, trailBytes
}

const typicalMTU = 1500

func ceilDiv(a, b int) int {
	if b <= 0 {
		panic("ceilDiv: 나눗수는 양수여야 한다")
	}
	if a <= 0 {
		return 0
	}
	return (a + b - 1) / b
}

func binIndex(clientBytes int) int {
	if clientBytes <= 0 {
		return 0
	}
	return ceilDiv(amplificationFactor*clientBytes, serverPacketSize)
}

func deltaMin(clientBytes, steps int) int {
	if steps <= 0 {
		return 0
	}
	b := clientBytes
	if b < 0 {
		b = 0
	}
	target := (binIndex(b) + steps - 1) * serverPacketSize
	return (target-amplificationFactor*b)/amplificationFactor + 1
}

func binNeeded(serverFlight float64, baseBin int, cPkt float64) int {
	s0abs := serverFlight - float64(baseBin)*cPkt
	den := float64(serverPacketSize) - cPkt
	if den <= 0 {
		return 1
	}
	n := int(s0abs / den)
	for float64(n*serverPacketSize) < s0abs+float64(n)*cPkt {
		n++
	}
	if n < 1 {
		n = 1
	}
	return n
}

func comboDeltas(k, m, w, ovh, nNeed, maxDelta int) []int {
	need := ((nNeed-1)*serverPacketSize)/amplificationFactor + 1
	set := map[int]bool{}
	g := recoveryGroup(m)
	for a := 0; a <= k; a++ {
		for b := 0; b <= m; b++ {
			if a+b == 0 {
				continue
			}
			used := k - a
			if used > b || used > g {
				continue
			}
			lack := need - (a+b)*w - (b-used)*ovh
			if lack <= 0 {
				continue
			}
			d := ceilDiv(lack, a+b)
			if d < 1 {
				continue
			}
			if maxDelta >= 0 && d > maxDelta {
				continue
			}
			set[d] = true
		}
	}
	out := make([]int, 0, len(set))
	for d := range set {
		out = append(out, d)
	}
	sort.Ints(out)
	return out
}

type cand struct {
	mode        string
	m           int
	delta       int
	wEff        int
	k           int
	clientBytes int
	steps       int
	lateParity  bool
	overMTU     bool
}

func levers(k, w, maxSteps, mMax int, serverFlight, cPkt float64,
	maxIPS int) []cand {
	base := k * w
	baseBin := binIndex(base)

	mk := func(mode string, m, delta int) cand {
		wEff := w + delta
		cb := k*wEff + m*parityDatagramBytes(wEff, k)
		return cand{
			mode: mode, m: m, delta: delta, wEff: wEff, k: k,
			clientBytes: cb,
			steps:       binIndex(cb) - baseBin,
			lateParity:  false,
			overMTU:     wEff > typicalMTU,
		}
	}

	out := []cand{mk("none", 0, 0)}
	for j := 1; j <= maxSteps; j++ {
		out = append(out, mk("pad", 0, ceilDiv(deltaMin(base, j), k)))
	}
	for m := 1; m <= mMax; m++ {
		out = append(out, mk("parity", m, 0))
	}
	for j := 1; j <= maxSteps; j++ {
		dj := deltaMin(base, j)
		if dj >= w {
			out = append(out, mk("parity", ceilDiv(dj, parityDatagramBytes(w, k)), 0))
		}
	}

	seen := map[string]bool{}
	uniq := make([]cand, 0, len(out))
	for _, c := range out {
		key := fmt.Sprintf("%s|%d|%d", c.mode, c.clientBytes, c.m)
		if seen[key] {
			continue
		}
		seen[key] = true
		uniq = append(uniq, c)
	}

	maxDelta := -1
	if maxIPS > 0 {
		maxDelta = maxIPS - w
		if maxDelta < 0 {
			maxDelta = 0
		}
	}
	nNeed := binNeeded(serverFlight, baseBin, cPkt)
	ovh := parityDatagramBytes(w, k) - w
	byteSeen := map[string]bool{}
	for _, c := range uniq {
		byteSeen[fmt.Sprintf("%d|%d", c.clientBytes, c.m)] = true
	}
	for m := 0; m <= mMax; m++ {
		for _, d := range comboDeltas(k, m, w, ovh, nNeed, maxDelta) {
			c := mk("combo", m, d)
			key := fmt.Sprintf("%d|%d", c.clientBytes, c.m)
			if byteSeen[key] {
				continue
			}
			byteSeen[key] = true
			uniq = append(uniq, c)
		}
	}
	return uniq
}

type scored struct {
	c     cand
	j     float64
	added int
}

func evalCands(cs []cand, k, w int, serverFlight, rtt, p, burst, cPkt float64,
	maxIPS int, uplinkMbps float64) []scored {
	tPTO := defaultTRecover(rtt, false)
	tACK := defaultTRecover(rtt, true)
	baseBytes := k * w
	nStar := binNeeded(serverFlight, binIndex(baseBytes), cPkt)

	out := []scored{}
	for _, c := range cs {
		if maxIPS > 0 && c.wEff > maxIPS {
			continue
		}
		if c.m > 0 && parityDatagramBytes(c.wEff, c.k) > typicalMTU-28 {
			continue
		}
		n, pFailTot, pRec, trailB := flightOutcome(
			c.k, c.m, c.wEff, p, burst, nStar,
			trailingParityDelayMs(c.k, c.wEff, uplinkMbps))
		_ = pRec
		fNo, fSamp, fAck := failFracLookup(c.k, c.m, p, burst)
		pto := pFailTot * fNo
		ptoS := pFailTot * fSamp
		ack := pFailTot * fAck
		added := c.clientBytes - baseBytes
		if added < 0 {
			added = 0
		}
		txAdded := criticalPathBytes(c.k, c.m, c.wEff) -
			criticalPathBytes(k, 0, w)
		if txAdded < 0 {
			txAdded = 0
		}
		tx := 0.0
		if uplinkMbps > 0 {
			tx = float64(txAdded) * 8.0 / (uplinkMbps * 1e6) * 1000.0
			tx += trailB * 8.0 / (uplinkMbps * 1e6) * 1000.0
		}
		ok := 1.0 - pFailTot
		nGivenOK := 2.0
		if ok > 1e-15 {
			nGivenOK = n / ok
		}
		tPTOSampled := ptoSampledRttMult * rtt
		mult := roundMultLookup(c.k, c.m, p, burst)
		j := n*rtt + mult*(pto*(rtt+tPTO)+ptoS*(nGivenOK*rtt+tPTOSampled)+
			ack*(nGivenOK*rtt+tACK)) + tx
		out = append(out, scored{c: c, j: j, added: added})
	}

	tieLess := func(x, y scored) bool {
		if x.added != y.added {
			return x.added < y.added
		}
		px, py := 1, 1
		if x.c.m > 0 {
			px = 0
		}
		if y.c.m > 0 {
			py = 0
		}
		if px != py {
			return px < py
		}
		lx, ly := 0, 0
		if x.c.lateParity {
			lx = 1
		}
		if y.c.lateParity {
			ly = 1
		}
		if lx != ly {
			return lx < ly
		}
		ox, oy := 0, 0
		if x.c.overMTU {
			ox = 1
		}
		if y.c.overMTU {
			oy = 1
		}
		if ox != oy {
			return ox < oy
		}
		return x.c.mode < y.c.mode
	}

	sort.SliceStable(out, func(a, b int) bool {
		x, y := out[a], out[b]
		if x.j != y.j {
			return x.j < y.j
		}
		return tieLess(x, y)
	})
	if len(out) > 0 {
		jmin := out[0].j
		end := 0
		for end < len(out) && out[end].j <= jmin+jTieMs {
			end++
		}
		tied := out[:end]
		sort.SliceStable(tied, func(a, b int) bool {
			return tieLess(tied[a], tied[b])
		})
	}
	return out
}

type destStat struct {
	K               int     `json:"k"`
	ServerFlight    float64 `json:"server_flight"`
	MinHCT          float64 `json:"min_hct_ms"`
	MinRTT          float64 `json:"min_rtt_ms"`
	RTTObservations int     `json:"rtt_observations"`
	LossCount       float64 `json:"loss_count"`
	ObsCount        float64 `json:"obs_count"`
	LossHCT         float64 `json:"loss_hct_ms"`
	ProbeMinHCT     float64 `json:"probe_min_hct_ms"`
	SymLoss         float64 `json:"sym_loss"`
	SymObs          float64 `json:"sym_obs"`
	SymC2Conns      float64 `json:"sym_c2_conns"`
	SymC2Symbols    float64 `json:"sym_c2_symbols"`
	Conns           int     `json:"conns"`
	SinceProbe      int     `json:"since_probe"`
}

type destCache struct {
	mu   sync.Mutex
	path string
	M    map[string]*destStat
}

const ewmaAlpha = 0.25

func newDestCache(path string) *destCache {
	c := &destCache{path: path, M: map[string]*destStat{}}
	if path != "" {
		if b, err := os.ReadFile(path); err == nil {
			_ = json.Unmarshal(b, &c.M)
		}
	}
	return c
}

func (c *destCache) save() {
	if c.path == "" {
		return
	}
	c.mu.Lock()
	b, _ := json.MarshalIndent(c.M, "", " ")
	c.mu.Unlock()
	_ = os.WriteFile(c.path, b, 0644)
}

func ewma(old, new_ float64, n int) float64 {
	if n <= 0 || old <= 0 {
		return new_
	}
	return old*(1-ewmaAlpha) + new_*ewmaAlpha
}

func (c *destCache) observe(addr string, k int, flightBytes, hctMs float64,
	lossEvent bool, unbiased bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	st := c.M[addr]
	if st == nil {
		st = &destStat{}
		c.M[addr] = st
	}
	if k > 0 {
		st.K = k
	}
	if flightBytes > 0 {
		st.ServerFlight = ewma(st.ServerFlight, flightBytes, st.Conns)
	}
	if hctMs > 0 && (st.MinHCT <= 0 || hctMs < st.MinHCT) {
		st.MinHCT = hctMs
	}
	if unbiased {
		classified := st.ProbeMinHCT > 0 && hctMs > 0
		if classified {
			lossEvent = hctMs > st.ProbeMinHCT*1.3+2.0
		}
		if hctMs > 0 && (st.ProbeMinHCT <= 0 || hctMs < st.ProbeMinHCT) {
			st.ProbeMinHCT = hctMs
		}
		if classified {
			const decay = 0.99
			st.LossCount *= decay
			st.ObsCount *= decay
			st.ObsCount++
			if lossEvent {
				st.LossCount++
				st.LossHCT = ewma(st.LossHCT, hctMs, st.Conns)
			}
		}
	}
	st.Conns++
}

func (c *destCache) minHCT(addr string) float64 {
	c.mu.Lock()
	defer c.mu.Unlock()
	if st := c.M[addr]; st != nil {
		return st.MinHCT
	}
	return 0
}

func (c *destCache) observeRTT(addr string, rttMs float64) {
	if rttMs <= 0 || math.IsNaN(rttMs) || math.IsInf(rttMs, 0) {
		return
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	st := c.M[addr]
	if st == nil {
		st = &destStat{}
		c.M[addr] = st
	}
	if st.MinRTT <= 0 || rttMs < st.MinRTT {
		st.MinRTT = rttMs
	}
	st.RTTObservations++
}

func policyRTT(st destStat) (float64, string) {
	if st.RTTObservations > 0 && st.MinRTT > 0 &&
		!math.IsNaN(st.MinRTT) && !math.IsInf(st.MinRTT, 0) {
		return st.MinRTT, "quic_ack_min_rtt"
	}
	return st.MinHCT, "hct_proxy_no_ack_rtt"
}

func (c *destCache) observeSymbols(addr string, nSym, nLost int,
	hctMs float64) {
	c.observeSymbolsWhy(addr, nSym, nLost, hctMs, false)
}

func (c *destCache) observeSymbolsWhy(addr string, nSym, nLost int,
	hctMs float64, c2 bool) {
	if nSym <= 0 || nLost < 0 || nLost > nSym {
		return
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	st := c.M[addr]
	if st == nil {
		st = &destStat{}
		c.M[addr] = st
	}
	if hctMs > 0 && (st.MinHCT <= 0 || hctMs < st.MinHCT) {
		st.MinHCT = hctMs
	}
	const decay = 0.99
	for i := 0; i < nSym; i++ {
		st.SymLoss *= decay
		st.SymObs *= decay
		st.SymObs++
		if i < nLost {
			st.SymLoss++
		}
	}
	if c2 {
		st.SymC2Conns++
		st.SymC2Symbols += float64(nLost)
	}
}

func (c *destCache) decide(addr string, w, mMax, coldM, probeEvery int,
	burst, cPkt float64, maxSteps, maxIPS int,
	uplinkMbps float64) (int, int, string, bool) {
	c.mu.Lock()
	st := c.M[addr]
	var snap destStat
	if st != nil {
		snap = *st
	}
	c.mu.Unlock()

	rtt, rttSource := policyRTT(snap)
	if st == nil || snap.Conns < 1 || rtt <= 0 || snap.K < 1 ||
		(snap.ObsCount < 1 && snap.SymObs < 1) {
		return w, coldM, "콜드스타트(이 목적지 기록 없음)", coldM == 0
	}
	k := snap.K
	var p float64
	if snap.SymObs >= 1 {
		p = (snap.SymLoss + 0.5) / (snap.SymObs + 1.0)
	} else {
		pConn := (snap.LossCount + 0.5) / (snap.ObsCount + 1.0)
		if pConn < 0 {
			pConn = 0
		}
		if pConn > 0.99 {
			pConn = 0.99
		}
		p = 1 - math.Pow(1-pConn, 1.0/float64(k))
	}
	if p < 0 {
		p = 0
	}
	if p > 0.99 {
		p = 0.99
	}
	tPTO := defaultTRecover(rtt, false)
	tACK := defaultTRecover(rtt, true)

	ranked := evalCands(
		levers(k, w, maxSteps, mMax, snap.ServerFlight, cPkt, maxIPS),
		k, w, snap.ServerFlight, rtt, p, burst, cPkt, maxIPS, uplinkMbps)
	if len(ranked) == 0 {
		return w, 0, "후보가 하나도 안 남았다", true
	}
	bestC := ranked[0]
	bestCost := bestC.j
	why := fmt.Sprintf("%s δ=%d m=%d ips=%d 추가=%dB | S=%.0f p=%.4f "+
		"RTT=%.3f(%s) T_pto=%.0f T_ack=%.0f 비용=%.2fms",
		bestC.c.mode, bestC.c.delta, bestC.c.m, bestC.c.wEff, bestC.added,
		snap.ServerFlight, p, rtt, rttSource, tPTO, tACK, bestC.j)
	if pMax := pfailP[len(pfailP)-1]; p > pMax {
		why += fmt.Sprintf(" | ⚠p표상한절단 %.4f->%.4f", p, pMax)
	}
	if snap.SymObs >= 1 {
		probeEvery = 0
	}
	probeC := ranked[0]
	for i := range ranked {
		if ranked[i].c.m == 0 {
			probeC = ranked[i]
			break
		}
	}
	probeCost := probeC.j - bestCost
	every := probeEvery
	if every > 0 && probeCost > 0 && rtt > 0 {
		need := int(math.Ceil(probeCost / (0.01 * rtt)))
		if need > every {
			every = need
		}
	}
	if every > 0 {
		c.mu.Lock()
		if cur := c.M[addr]; cur != nil {
			cur.SinceProbe++
			if cur.SinceProbe >= every {
				cur.SinceProbe = 0
				c.mu.Unlock()
				return probeC.c.wEff, 0, fmt.Sprintf(
					"탐색 %s δ=%d ips=%d (주기 %d, 탐색비용 %.2fms)",
					probeC.c.mode, probeC.c.delta, probeC.c.wEff,
					every, probeCost), true
			}
		}
		c.mu.Unlock()
	}
	return bestC.c.wEff, bestC.c.m, why, bestC.c.m == 0
}

func policyGrid() {
	for _, k := range []int{1, 2, 3} {
		for _, w := range []int{1200, 1280, 1350} {
			for _, cert := range []int{1000, 2308, 3000, 3200, 4032, 5609,
				5800, 6500, 8000, 10800, 12000} {
				for _, s0base := range []float64{396.5, 1527.5, 382.45, 1472.0} {
					for _, rtt := range []float64{10, 50, 100} {
						for _, p := range []float64{0, 0.007, 0.015, 0.035,
							0.0725, 0.09, 0.15, 0.156, 0.181, 0.244,
							0.294} {
							for _, l := range []float64{1, 1.5, 2, 3, 4} {
								for _, up := range []float64{0, 10, 100} {
									base := k * w
									S := float64(cert) + s0base +
										float64(binIndex(base))*cPktDefault
									r := evalCands(
										levers(k, w, maxStepsDefault, mMaxDefault, S,
											cPktDefault, quicgoMaxIPS),
										k, w, S, rtt, p, l, cPktDefault,
										quicgoMaxIPS, up)
									b := r[0].c
									fmt.Printf("%d %d %d %g %g %g %g %g %s %d %d %d %.12g\n",
										k, w, cert, s0base, rtt, p, l, up,
										b.mode, b.delta, b.m, b.wEff, r[0].j)
								}
							}
						}
					}
				}
			}
		}
	}
}
