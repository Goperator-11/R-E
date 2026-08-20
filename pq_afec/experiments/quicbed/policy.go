// 폐루프 정책 - 클라이언트가 m 을 스스로 고른다.
//
// 여기까지 오기 전에는 m 을 -m 플래그로 사람이 줬다. 즉 "적응형" 이 아니라
// 고정 설정이었다. 닫으려면 정책이 필요로 하는 값을 클라이언트가 알아야
// 하는데, **첫 접속 순간에는 둘 다 모른다.**
//
//     서버 비행 크기 S   -> 얼마나 큰 인증서인지 모른다
//     경로 손실률 p      -> 이 경로가 얼마나 깨끗한지 모른다
//
// 그래서 목적지별로 관측해서 배운다. 전부 **클라이언트가 실제로 볼 수 있는
// 것**만 쓴다. 추정이나 가정으로 채운 값은 하나도 없다.
//
//     S      핸드셰이크 동안 받은 바이트를 세면 그대로 나온다
//     RTT    이 목적지의 **최소 HCT** 가 1-RTT 인 경우의 값이다
//     p      quic-go 가 Initial 을 재전송했는지로 손실 사건을 센다
//     실패비용 손실이 났던 연결의 HCT 에서 RTT 를 뺀 값 (관측값)
//
// 마지막 항목이 특히 중요하다. 원래 모형은 복구 실패 비용을 RFC 9002 의
// 초기 PTO(약 999 ms)로 뒀는데, p7 의 결정적 소거 시험이 **실제로는 왕복
// 2~5 회**임을 보였다. 서버가 받은 것에 ACK 를 주므로 클라이언트가 패킷번호
// 구멍으로 손실을 알아채고 곧바로 재전송하기 때문이다. 상수를 새로 박아
// 넣는 대신 그 값도 관측해서 배우게 했다.
package main

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"sort"
	"sync"
)

const serverPacketSize = 1280      // quic-go 가 한 번에 내보내는 패킷 크기
const amplificationFactor = 3      // RFC 9000 8.1

// allowedBytes 는 주소 검증 전 서버가 실제로 내보낼 수 있는 바이트다.
//
// 예산 자체가 아니라 **패킷 경계로 올림한 값**이다. quic-go 는 패킷을 만들기
// 전에만 `bytesSent >= 3*bytesReceived` 를 보므로, 예산이 조금이라도 남으면
// 패킷 하나를 통째로 더 보낸다. 이 계단이 팀 자료의 "교환비 1:3.8" 의 정체다.
func allowedBytes(clientBytes int) int {
	b := amplificationFactor * clientBytes
	if b <= 0 {
		return 0
	}
	n := (b-1)/serverPacketSize + 1
	return n * serverPacketSize
}

// parityDatagramBytes 는 패리티 데이터그램 하나의 크기다.
//   롱헤더(약 19) + FEC 머리(13) + crc/len 목록(6k) + 심볼(W)
func parityDatagramBytes(w, k int) int {
	return w + 32 + 6*k
}

// 🩸 pfailLookup 을 지웠다(2026-08-20 감사). P_fail 을 별도 표에서 읽으면
// 기대 왕복 수와 **다른 분포**에서 나오게 된다 - 그것이 결함 1 의 정체였다.
// 지금은 flightOutcome 이 결합분포 하나에서 둘 다 뽑는다. 두 번째 출처를
// 남겨 두면 누군가 다시 그걸 부른다.

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

func idxNearestF(xs []float64, v float64) int {
	best, bd := 0, math.Inf(1)
	for i, x := range xs {
		d := math.Abs(x - v)
		if d < bd {
			bd, best = d, i
		}
	}
	return best
}

// binomPMF 는 시행 n 회 중 성공 k 회 확률이다.
// jointLookup 은 결합 도착분포를 표에서 읽는다. p 만 선형 보간한다.
//
// 돌려주는 것: 평탄화된 (k+1)x(m+1) 행렬. [a*(m+1)+b] = 원본 a 개·패리티
// b 개가 도착할 확률. 표는 padfec/table.py 가 검증된 Python 모형에서
// 생성한다 - Go 로 다시 구현하지 않는 이유는 그 파일 머리말에 적었다.
func jointLookup(k, m int, p, l float64) []float64 {
	ki := idxNearest(pfailK, k)
	mi := idxNearest(pfailM, m)
	li := idxNearestF(pfailL, l)
	row := jointTable[ki][mi]

	// p 선형 보간. 두 끝점이 각각 합 1 이므로 볼록결합도 합이 1 이다.
	lo := 0
	for lo < len(pfailP)-2 && pfailP[lo+1] < p {
		lo++
	}
	hi := lo + 1
	a, b := row[lo][li], row[hi][li]
	span := pfailP[hi] - pfailP[lo]
	t := 0.0
	if span > 0 {
		t = (p - pfailP[lo]) / span
	}
	if t < 0 {
		t = 0
	}
	if t > 1 {
		t = 1
	}
	out := make([]float64, len(a))
	for i := range a {
		out[i] = a[i]*(1-t) + b[i]*t
	}
	return out
}

// flightOutcome 은 기대 왕복 수와 복구 실패 확률을 **하나의 분포에서** 낸다.
// padfec/policy.py 의 flight_outcome 과 같은 식이다.
//
// 🩸 처음에는 **의도한** 클라이언트 바이트로 1 아니면 2 를 결정론적으로
// 정했다. 틀렸다. 증폭 신용은 보장된 것이 아니라 **패리티가 실제로 도착해야**
// 생긴다. 패리티가 유실되면 그 바이트가 예산에 안 잡혀 왕복 하나를 도로 잃는다.
// (실측: 임계위/손실 5% 꼬리가 m=1 8.0%, m=2 1.0% 로 갈렸다.)
//
// 🩸 2026-08-20 감사가 그 수리에서 결함 둘을 더 찾았다.
//
//	(1) 이 함수가 원본/패리티를 **각각 독립 이항**으로 굴렸는데 pfail 은
//	    Gilbert-Elliott 표에서 읽었다. 한 비용식에 손실 모형이 둘이었다.
//	    이제 둘 다 jointTable 에서 나온다.
//	(2) 모든 상태에 대해 E[n_rtt] 를 낸 뒤 거기에 P(실패)x비용을 **더했다.**
//	    전멸하면 서버가 아무것도 못 받아 allowed(0)=0 이라 n=2 로 세어지고,
//	    동시에 pfail 로 복구비용도 물었다 - 같은 사건을 두 번 청구한 것이다.
//	    그래서 n_rtt 는 **복구 성공 상태에만** 매기고, 실패는 호출부가
//	    (RTT + 복구비용) 한 번으로 값을 매긴다.
//
// 복구된 원본의 바이트는 **세지 않는다** - 회계 규칙상 복구본을 넣을 때
// 패리티를 버리므로, 서버가 실제로 센 바이트만 예산이 된다.
// defaultTRecover 는 복구 실패 한 번의 대가다. arrivedAny = 서버가 하나라도
// 받았는가. 상수의 출처는 pfail_table.go 머리말(결정적 소거 실측)에 있다.
func defaultTRecover(rttMs float64, arrivedAny bool) float64 {
	if arrivedAny {
		return tAckRetxSlope*rttMs + tAckRetxBaseMs
	}
	return tPTONoAckMs
}

// flightOutcome 은 기대 왕복 수와 **두 갈래의** 복구 실패 확률을 낸다.
//
// 🩸 2026-08-20 실측 수리. 그전에는 실패 가지가 하나였고 그 값이 rtt 였다.
// 결정적 소거(-drop-initial)로 재 보니 대가가 **서버가 하나라도 받았는지**로
// 갈렸다: 0 개면 ACK 가 없어 PTO(RTT 무관 200.86 ms), 1 개 이상이면 ACK 로
// 구멍이 드러나 즉시 재전송(1.125·RTT + 1.42). k=1 은 실패가 곧 전멸이라
// 항상 PTO 가지인데 기본값이 rtt 였으니 RTT 10 ms 에서 20 배 작았다.
func flightOutcome(k, m, w int, p, l float64,
	serverFlight float64) (nExp, pFailPTO, pFailACK float64) {
	parity := parityDatagramBytes(w, k)
	pm := jointLookup(k, m, p, l)
	cols := m + 1
	for a := 0; a <= k; a++ {
		for b := 0; b < cols; b++ {
			idx := a*cols + b
			if idx >= len(pm) {
				continue
			}
			pr := pm[idx]
			if pr <= 0 {
				continue
			}
			// MDS: 받은 심볼이 k 개 이상이면 복구된다.
			if k-a > b {
				if a+b == 0 {
					pFailPTO += pr
				} else {
					pFailACK += pr
				}
				continue
			}
			if serverFlight > float64(allowedBytes(a*w+b*parity)) {
				nExp += pr * 2.0
			} else {
				nExp += pr
			}
		}
	}
	return nExp, pFailPTO, pFailACK
}


// ---------------------------------------------------------------------------
// 양자 지렛대 (padfec/quantum.py 이식) — 2026-08-20
//
// v2 는 결정 변수가 둘이다. m(패리티 개수)만 고르던 v1 에서 δ(데이터그램을
// 몇 바이트 키울지)가 추가됐다. 여기까지 이식하기 전에는 `-fec auto` 가
// m 만 골랐고, 헤드라인인 "1 바이트로 왕복 하나 사기"는 사람이 -ips 를
// 직접 줄 때만 실현됐다.
//
// **이 부분은 Go 로 다시 짜도 된다.** 정수 산술뿐이라 갈라질 여지가 없다.
// 갈라질 수 있는 것은 확률 모형(결합분포)이고 그건 표로 심는다 —
// padfec/table.py 머리말의 규칙 그대로다. 대신 padfec/policy.py 와 같은
// 답을 내는지 격자 대조로 못 박는다.
// ---------------------------------------------------------------------------

const typicalMTU = 1500

// ceilDiv 는 올림 나눗셈이다.
//
// 🩸 Python 의 `-((-a) // b)` 를 그대로 옮기면 안 된다. Python `//` 는
// **내림**이라 그 식이 올림이 되지만, Go `/` 는 **0 쪽으로 자른다**.
// 그대로 옮기면 올림이 아니라 내림이 나온다: ceilDiv(161,2) 가 81 이 아니라 80.
// 그러면 binIndex 가 한 칸씩 낮게 나오고 δ 후보가 칸을 못 올려 pad 가
// 통째로 쓸모없어진다(격자 대조에서 92/5670 불일치로 잡혔다).
// a >= 0, b > 0 만 쓰므로 (a+b-1)/b 로 쓴다.
func ceilDiv(a, b int) int {
	if b <= 0 {
		panic("ceilDiv: 나눗수는 양수여야 한다")
	}
	if a <= 0 {
		return 0
	}
	return (a + b - 1) / b
}

// binIndex 는 이 비행이 들어앉은 양자 칸 번호다. ceil(3B/P).
func binIndex(clientBytes int) int {
	if clientBytes <= 0 {
		return 0
	}
	return ceilDiv(amplificationFactor*clientBytes, serverPacketSize)
}

// deltaMin 은 steps 칸 위로 올라가는 최소 추가 바이트다 (명세 보조정리 2).
//
//	Δ_min = floor(A_target/3 − B) + 1
//
// W = 1280 = P 이면 3B 가 항상 P 의 배수라 Δ_min = 1 이다. k 와 무관하다 —
// quic-go 기본값이 증폭 양자 경계에 정확히 걸터앉아 있다는 뜻이고,
// 이것이 이 연구의 헤드라인이다.
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

// cand 는 후보 하나다. padfec/quantum.py 의 _candidate 와 같은 필드를 갖는다.
type cand struct {
	mode        string // none | pad | parity
	m           int
	delta       int // 데이터그램당 추가 바이트
	wEff        int
	k           int
	clientBytes int
	steps       int // 기준선 대비 실제로 올라간 칸 수
	lateParity  bool
	overMTU     bool
}

// levers 는 명세 §3 의 후보 집합이다. 연속 스윕이 아니라 **경계점만** 본다.
//
//	후보 = {(0,0)}
//	     ∪ {(ceil(Δ_j/k), 0) : j = 1..maxSteps}   # δ 로 j 칸
//	     ∪ {(0, m)           : m = 1..mMax}       # 패리티만
//	     ∪ {(0, ceil(Δ_j/파)) : j, Δ_j >= W}      # 패리티로 j 칸
//
// k 는 관측값(첫 비행 데이터그램 수)을 그대로 고정한다. Python 은 k_floor=k0
// 로 같은 일을 한다 - W 를 키울 때 k 를 다시 계산하면 k 가 줄어 칸이
// **내려가고** δ 지렛대가 후보에서 통째로 사라지기 때문이다.
func levers(k, w, maxSteps, mMax int) []cand {
	base := k * w
	baseBin := binIndex(base)

	mk := func(mode string, m, delta int) cand {
		wEff := w + delta
		cb := k*wEff + m*parityDatagramBytes(wEff, k)
		return cand{
			mode: mode, m: m, delta: delta, wEff: wEff, k: k,
			clientBytes: cb,
			steps:       binIndex(cb) - baseBin,
			// 명세 §2.6(가설): k=1·m=1 배치는 [원본, 패리티] 라 원본 하나로
			// 서버가 곧장 응답 비행을 만들기 시작하고, 뒤따르는 패리티는
			// 결정 시점 이후에 도착해 신용을 못 살 수 있다. 같은 값이면 피한다.
			lateParity: k == 1 && m == 1,
			overMTU:    wEff > typicalMTU,
		}
	}

	out := []cand{mk("none", 0, 0)}
	for j := 1; j <= maxSteps; j++ { // δ 지렛대
		out = append(out, mk("pad", 0, ceilDiv(deltaMin(base, j), k)))
	}
	for m := 1; m <= mMax; m++ { // m 지렛대(복구 목적)
		out = append(out, mk("parity", m, 0))
	}
	for j := 1; j <= maxSteps; j++ { // m 지렛대(칸 올리기 목적)
		dj := deltaMin(base, j)
		if dj >= w {
			// 패리티 하나가 실제로 싣는 바이트로 나눈다. W 로 나누면
			// 필요한 개수를 과대평가한다(패리티가 원본보다 크다).
			out = append(out, mk("parity", ceilDiv(dj, parityDatagramBytes(w, k)), 0))
		}
	}

	// 🩸 Python quantum.levers 에는 후보가 하나 더 있다 - `pad_repack`
	// (데이터그램을 합쳐 재패킹). **일부러 안 옮겼다.** 그건 CRYPTO 를 다시
	// 쪼개는 실제 구현 변경을 요구하는데 우리 테스트베드는 그걸 안 한다.
	// 모형에만 있는 선택지를 정책이 고르면 실현할 수 없는 답이 나온다.
	// Python 도 기본값 allow_repack=False 로 같은 자리에서 뺀다 - 그래서
	// 격자 대조가 성립한다. 재패킹을 구현하는 날 양쪽을 같이 열어야 한다.

	// 중복 제거. mode 가 다르면 바이트가 같아도 남긴다 - 같은 바이트에서
	// 복구 유무가 갈리는 것이 시험 대상이기 때문이다.
	seen := map[string]bool{}
	uniq := out[:0]
	for _, c := range out {
		key := fmt.Sprintf("%s|%d|%d", c.mode, c.clientBytes, c.m)
		if seen[key] {
			continue
		}
		seen[key] = true
		uniq = append(uniq, c)
	}
	return uniq
}

// scored 는 후보 하나의 점수다.
type scored struct {
	c     cand
	j     float64
	added int
}

// evalCands 는 후보 전부에 J 를 매기고 명세 §3 의 순서로 정렬해 돌려준다.
//
//	J = E[n_rtt|복구성공]·RTT
//	  + P(실패·PTO)·(RTT + T_pto)
//	  + P(실패·ACK)·(RTT + T_ack)
//	  + t_tx
//
// cPkt — 서버 패킷 오버헤드(명세 §2.5). 칸이 오르면 서버가 패킷을 하나 더
// 쓰므로 서버 비행이 그만큼 커진다. 관측 S 는 **지금 칸**의 값이므로
// 올라간 칸 수만큼 더해 준다. Python 의 s0_at() 과 같은 식이다
// (Python 은 절대값 s0_base + n·c, 여기는 상대값 S_obs + Δn·c — S_obs 의
// 정의상 둘이 같다).
func evalCands(cs []cand, k, w int, serverFlight, rtt, p, burst, cPkt float64,
	maxIPS int) []scored {
	tPTO := defaultTRecover(rtt, false)
	tACK := defaultTRecover(rtt, true)
	baseBytes := k * w

	out := []scored{}
	for _, c := range cs {
		if maxIPS > 0 && c.wEff > maxIPS {
			// 보낼 수 없는 후보다. 2026-08-20 실측: -ips 1707 을 줘도
			// quic-go 는 1452 B 로 깎아 보낸다.
			continue
		}
		sf := serverFlight + float64(c.steps)*cPkt
		n, pto, ack := flightOutcome(c.k, c.m, c.wEff, p, burst, sf)
		added := c.clientBytes - baseBytes
		if added < 0 {
			added = 0
		}
		// 업링크 10 Mbps 고정. Python cost_of_v2 의 기본값과 같은 값이다.
		// 🩸 인자로 빼지 않았다 - Go 는 업링크를 관측할 수단이 없어서
		// 인자로 만들면 호출부가 또 리터럴을 박게 된다(버스트에서 그 일을
		// 이미 겪었다). 재려면 재는 쪽을 먼저 만들어야 한다.
		// 참고: 이 테스트베드는 netem 이 대역을 안 걸어서 이 항이 실측과
		// 안 맞는다(m=1 대 m=2 실측 차 0.001 ms vs 모형 1.054 ms).
		tx := float64(added) * 8.0 / 10e6 * 1000.0
		j := n*rtt + pto*(rtt+tPTO) + ack*(rtt+tACK) + tx
		out = append(out, scored{c: c, j: j, added: added})
	}

	// 동점 처리 (명세 §3): J -> 실제 추가 바이트 -> 같은 바이트면 패리티 우선
	//                    -> late_parity 없는 쪽 -> over_mtu 없는 쪽 -> mode 이름.
	sort.SliceStable(out, func(a, b int) bool {
		x, y := out[a], out[b]
		jx := math.Round(x.j*1e6) / 1e6
		jy := math.Round(y.j*1e6) / 1e6
		if jx != jy {
			return jx < jy
		}
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
	})
	return out
}

// ------------------------------------------------------------ 목적지 캐시
//
// 1 차 연구에서 목적지별 사전분포 캐시(afec/cache.py)를 만들었다가 2 차에서
// "데이터 구간 전용" 이라며 내렸었다. 폐루프를 닫으려니 정확히 그 부품이
// 필요했다. 버린 것이 아니라 자리를 옮긴 것이다.
type destStat struct {
	K            int     `json:"k"`             // 첫 비행 데이터그램 수
	ServerFlight float64 `json:"server_flight"` // EWMA, 바이트
	MinHCT       float64 `json:"min_hct_ms"`    // 이 목적지의 RTT 추정
	// 🩸 손실률은 EWMA 로 추정하면 안 된다. 3% 짜리 희귀 사건인데 alpha=0.25
	// 로 두면 손실 한 번에 0.25 로 튀고 깨끗한 연결 몇 번에 0 으로 꺼진다.
	// 그래서 m 이 0 과 1 사이를 블록 단위로 **진동**했다(수렴하지 않았다).
	//
	// 계수로 바꾼다. 사후평균 (손실+0.5)/(관측+1) 은 Jeffreys 사전분포이고,
	// 관측이 쌓일수록 좁아진다. 경로가 변할 수 있으니 매 관측마다 두 계수를
	// 0.99 배로 줄여 유효 기억을 100 연결쯤으로 둔다.
	LossCount    float64 `json:"loss_count"`
	ObsCount     float64 `json:"obs_count"`
	LossHCT      float64 `json:"loss_hct_ms"`   // 손실이 났을 때의 HCT (EWMA)
	Conns        int     `json:"conns"`
	SinceProbe   int     `json:"since_probe"`   // 마지막 탐색 이후 연결 수
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

// observe 는 한 번의 핸드셰이크에서 본 것을 기록한다.
//
// 🩸 unbiased 가 핵심이다. 손실 신호는 "quic-go 가 첫 비행을 재전송했는가"
// 인데, **FEC 가 성공하면 복구되어 재전송이 일어나지 않는다.** 그래서 m>=1
// 로 돈 연결의 관측은 손실률을 체계적으로 0 쪽으로 끌어내린다.
// 정책이 자기 성공에 눈이 머는 구조다 - 잘 막을수록 경로가 깨끗하다고
// 믿고 방어를 줄인다.
//
// 실제로 그랬다. 임계위 조건에서 손실 0%/2%/5% 의 선택 분포가
// {1:156, 2:43} 으로 **완전히 같았다.** 손실을 전혀 못 배운 것이다.
//
// 그래서 손실 계수는 **m=0 으로 돈 연결에서만** 갱신한다. S 와 RTT 는
// 어느 연결에서든 편향 없이 관측되므로 항상 갱신한다.
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
		const decay = 0.99
		st.LossCount *= decay
		st.ObsCount *= decay
		st.ObsCount++
		if lossEvent {
			st.LossCount++
			if hctMs > 0 {
				st.LossHCT = ewma(st.LossHCT, hctMs, st.Conns)
			}
		}
	}
	st.Conns++
}

// decide 는 이 목적지에 쓸 (InitialPacketSize, m) 을 고른다.
//
// probeEvery 번마다 한 번은 **일부러 m=0 으로** 간다. 그러지 않으면 손실을
// 관측할 길이 없다(위 observe 주석 참고). 탐색 비용은 작다 - 손실률 5%,
// 실패비용 150 ms 라면 20 연결에 한 번 무방비로 가는 값이
// 0.05 x 0.1 x 150 = 0.75 ms 다.
// burst - 평균 버스트 길이. Go 는 이걸 관측할 수단이 없으므로 호출부가
// defaultAssumedBurst(생성 표에 심긴 값, 정의는 padfec/policy.py 한 곳)를
// 준다. 🩸 예전에는 pfailLookup(..., 1.0) 으로 **호출부에 리터럴을 박아** 뒀고
// Python 은 실제 버스트를 썼다. 같은 입력에 두 구현이 다른 m 을 골랐다
// (90 조건 중 17 건). 못 재는 것은 사실이지만 숨기지는 않는다.
// 돌려주는 것: (쓸 InitialPacketSize, 패리티 개수 m, 근거, 손실관측에 쓸 수 있나)
//
// 🩸 2026-08-20 v2 이식. 그전에는 m 만 골랐다(반환값도 m 하나였다). δ 지렛대가
// 없으니 "1 바이트로 왕복 하나 사기"는 사람이 -ips 를 직접 줄 때만 실현됐다.
// 이제 후보 집합이 Python decide_v2 와 같다: {none, pad(δ), parity(m)}.
func (c *destCache) decide(addr string, w, mMax, coldM, probeEvery int,
	burst, cPkt float64, maxSteps, maxIPS int) (int, int, string, bool) {
	c.mu.Lock()
	st := c.M[addr]
	var snap destStat
	if st != nil {
		snap = *st
	}
	c.mu.Unlock()

	if st == nil || snap.Conns < 1 || snap.MinHCT <= 0 || snap.K < 1 ||
		snap.ObsCount < 1 {
		return w, coldM, "콜드스타트(이 목적지 기록 없음)", true
	}
	// 탐색 주기는 뒤에서 정한다 - 얼마나 비싼지 알아야 하기 때문이다.
	k := snap.K
	rtt := snap.MinHCT
	// 연결당 손실 사건 비율 -> 데이터그램당 손실률.
	// Jeffreys 사후평균을 쓴다: (손실+0.5)/(관측+1).
	pConn := (snap.LossCount + 0.5) / (snap.ObsCount + 1.0)
	if pConn < 0 {
		pConn = 0
	}
	if pConn > 0.99 {
		pConn = 0.99
	}
	p := 1 - math.Pow(1-pConn, 1.0/float64(k))
	// 복구 실패 비용.
	//
	// 🩸 2026-08-20 실측 수리. 그전에는 관측값 하나(LossHCT-rtt)를 쓰고 없으면
	// rtt 로 뒀다. 두 문제가 있었다.
	//   (1) 없을 때의 기본값 rtt 가 PTO 가지에서 4~20 배 작다.
	//   (2) LossHCT 는 두 실패 유형(PTO/ACK)을 **뭉뚱그린 평균**이라 어느
	//       가지에 넣어도 틀린다.
	// 그래서 PTO 가지는 측정 상수를, ACK 가지는 측정 적합식을 쓴다. 관측값은
	// 캐시에 계속 쌓되(경로가 달라졌는지 보는 신호로 쓸 수 있다) 비용에는
	// 넣지 않는다 - 어느 가지의 것인지 모르는 값이기 때문이다.
	tPTO := defaultTRecover(rtt, false)
	tACK := defaultTRecover(rtt, true)

	// 후보 집합을 만들고 J 로 줄 세운다 (명세 §3). Python decide_v2 와 같다.
	ranked := evalCands(levers(k, w, maxSteps, mMax), k, w,
		snap.ServerFlight, rtt, p, burst, cPkt, maxIPS)
	if len(ranked) == 0 {
		return w, 0, "후보가 하나도 안 남았다", true
	}
	bestC := ranked[0]
	bestCost := bestC.j
	why := fmt.Sprintf("%s δ=%d m=%d ips=%d 추가=%dB | S=%.0f p=%.4f "+
		"T_pto=%.0f T_ack=%.0f 비용=%.2fms",
		bestC.c.mode, bestC.c.delta, bestC.c.m, bestC.c.wEff, bestC.added,
		snap.ServerFlight, p, tPTO, tACK, bestC.j)
	// ------------------------------------------------------------- 탐색
	//
	// 🩸 탐색 주기를 고정하면 안 된다. 무방비(m=0) 로 가는 값이 조건마다
	// 완전히 다르기 때문이다. 임계 위에서는 m=0 이 곧 2-RTT 라 한 번에
	// 왕복 하나를 통째로 문다. 20 연결마다 탐색하면 그것만으로
	// 10 x 51ms / 200 = 2.55 ms/연결 이 나가고, 실측 후회가 정확히
	// 그 값이었다(임계위 조건 +2.5 ms).
	//
	// 그래서 **탐색 비용이 RTT 의 1% 를 넘지 않도록** 주기를 늘린다.
	// 탐색이 싼 곳(임계 아래)에서는 자주 재고, 비싼 곳에서는 드물게 잰다.
	// 탐색은 **가장 싼 m=0 후보**로 간다.
	//
	// 🩸 2026-08-20 δ 이식이 열어 준 개선. 그전에는 맨몸 기준선(δ=0, m=0)으로만
	// 탐색했는데, 임계 위에서는 그게 곧 2-RTT 라 적응 주기가 늘어나고 관측이
	// 안 쌓였다. 실측: 400 연결에 무편향 관측 3 회, p 가 Jeffreys 사전값
	// 근처(0.126)에 정체 -> 그 p 로는 패리티가 늘 이겨 δ 후보가 영영 안 뽑힌다.
	//
	// **δ 는 복구를 주지 않으므로 손실 관측을 편향시키지 않는다.** m=0 이기만
	// 하면 무엇이든 탐색으로 쓸 수 있고, 후보는 이미 J 로 정렬돼 있으니
	// 첫 m=0 후보가 가장 싼 탐색이다. m 만 있던 시절엔 m=0 후보가 맨몸
	// 하나뿐이라 이 선택지가 존재하지 않았다.
	probeC := ranked[0]
	for i := range ranked {
		if ranked[i].c.m == 0 {
			probeC = ranked[i]
			break
		}
	}
	probeCost := probeC.j - bestCost
	every := probeEvery
	if probeCost > 0 && rtt > 0 {
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
	// 손실 관측에 쓸 수 있는가 = 패리티가 손실을 가리지 않는가.
	// δ 는 복구를 주지 않으므로 관측을 편향시키지 않는다.
	return bestC.c.wEff, bestC.c.m, why, bestC.c.m == 0
}

// ---------------------------------------------------------------------------
// 격자 덤프 — Python decide_v2 와 글자 단위로 같은 답을 내는지 재는 자
// ---------------------------------------------------------------------------
//
// 🩸 이 함수는 **검증용인데 제품 바이너리 안에 있다.** 일부러다. 2026-08-20
// v2 이식을 대조할 때 똑같은 프로그램을 임시 폴더에 만들어 돌렸는데, 세션이
// 끝나면 사라져서 다음 사람에게는 "5,670 격자점 불일치 0 건"이라는 **문장만**
// 남는다. padfec/policy.py 머리말은 "격자 대조로 못 박는다"고 적어 뒀지만
// 정작 그 자가 저장소에 없었다. 자를 코드 옆에 둬야 관문에서 매번 돌아간다.
//
// 격자의 정본은 여기다. Python 쪽(experiments/gate_go_parity.py)은 이 출력을
// 읽어서 따라간다 - 양쪽에 같은 목록을 적으면 언젠가 갈라지기 때문이다.
//
// 한 줄 형식: k w cert s0base rtt p L mode δ m ips
func policyGrid() {
	// k       첫 비행 데이터그램 수. 실측에서 본 범위.
	// w       InitialPacketSize. 1280 은 quic-go 기본값,
	//         1200 은 RFC 9000 최소, 1350 은 그 위 고원.
	// cert    인증서 크기. 임계 양쪽과 실측에 쓴 값들.
	// s0base  서버 비행의 인증서 무관 성분. x25519 / ML-KEM 두 값.
	// p, L    손실률과 평균 버스트 길이.
	for _, k := range []int{1, 2, 3} {
		for _, w := range []int{1200, 1280, 1350} {
			for _, cert := range []int{1000, 2308, 3000, 4032, 5609, 6500, 8000} {
				for _, s0base := range []float64{396.5, 1527.5} {
					for _, rtt := range []float64{10, 50, 100} {
						for _, p := range []float64{0, 0.005, 0.02, 0.05, 0.2} {
							for _, l := range []float64{1, 2, 3} {
								// 관측 S 는 **지금 칸**의 값이다. Python 은
								// s0_at(n) = s0_base + n·c 로 절대값을 쓰므로,
								// 같은 것을 가리키도록 지금 칸 수를 곱해 준다.
								base := k * w
								S := float64(cert) + s0base +
									float64(binIndex(base))*cPktDefault
								r := evalCands(levers(k, w, maxStepsDefault, 2),
									k, w, S, rtt, p, l, cPktDefault, quicgoMaxIPS)
								b := r[0].c
								fmt.Printf("%d %d %d %g %g %g %g %s %d %d %d\n",
									k, w, cert, s0base, rtt, p, l,
									b.mode, b.delta, b.m, b.wEff)
							}
						}
					}
				}
			}
		}
	}
}
