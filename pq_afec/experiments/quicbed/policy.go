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

// pfailLookup 은 표에서 복구 실패 확률을 읽는다. p 만 선형 보간한다.
// 표는 padfec/table.py 가 검증된 Python 모형에서 생성한다 - Go 로 다시
// 구현하지 않는 이유는 그 파일 머리말에 적었다.
func pfailLookup(k, m int, p, l float64) float64 {
	ki := idxNearest(pfailK, k)
	mi := idxNearest(pfailM, m)
	li := idxNearestF(pfailL, l)
	row := pfailTable[ki][mi]
	if p <= pfailP[0] {
		return row[0][li]
	}
	last := len(pfailP) - 1
	if p >= pfailP[last] {
		return row[last][li]
	}
	for i := 0; i < last; i++ {
		if p >= pfailP[i] && p <= pfailP[i+1] {
			lo, hi := pfailP[i], pfailP[i+1]
			t := 0.0
			if hi > lo {
				t = (p - lo) / (hi - lo)
			}
			return row[i][li]*(1-t) + row[i+1][li]*t
		}
	}
	return row[last][li]
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
func binomPMF(n, k int, q float64) float64 {
	if k < 0 || k > n {
		return 0
	}
	c := 1.0
	for i := 0; i < k; i++ {
		c = c * float64(n-i) / float64(i+1)
	}
	return c * math.Pow(q, float64(k)) * math.Pow(1-q, float64(n-k))
}

// expectedNRtt 는 기대 왕복 수다.
//
// 🩸 처음에는 **의도한** 클라이언트 바이트로 1 아니면 2 를 결정론적으로
// 정했다. 틀렸다. 증폭 신용은 보장된 것이 아니라 **패리티가 실제로 도착해야**
// 생긴다. 패리티가 유실되면 그 바이트가 예산에 안 잡혀 왕복 하나를 도로 잃는다.
//
// 그래서 m=1 은 이 위험이 그대로(패리티 하나뿐)이고 m=2 는 하나를 잃어도
// 남는다. 실측에서 임계위/손실5% 의 꼬리가 m=1 8.0%, m=2 1.0% 로 갈린 것이
// 정확히 이 항이었고, 이 항이 없어서 정책이 m=1 을 골라 후회 +6.5 ms 를 냈다.
//
// 도착한 원본 i 개와 패리티 j 개의 모든 경우에 대해 기댓값을 낸다.
// 복구된 원본의 바이트는 **세지 않는다** - 우리 회계 규칙상 복구본을 넣을
// 때 패리티를 버리므로, 서버가 실제로 센 바이트만 예산이 된다.
func expectedNRtt(k, m, w int, p float64, serverFlight float64) float64 {
	parity := parityDatagramBytes(w, k)
	q := 1 - p
	tot := 0.0
	for i := 0; i <= k; i++ {
		pi := binomPMF(k, i, q)
		if pi <= 0 {
			continue
		}
		for j := 0; j <= m; j++ {
			pj := binomPMF(m, j, q)
			if pj <= 0 {
				continue
			}
			n := 1.0
			if serverFlight > float64(allowedBytes(i*w+j*parity)) {
				n = 2.0
			}
			tot += pi * pj * n
		}
	}
	return tot
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

// decide 는 이 목적지에 대해 m 을 고른다.
// decide 는 이 목적지에 대해 m 을 고른다.
//
// probeEvery 번마다 한 번은 **일부러 m=0 으로** 간다. 그러지 않으면 손실을
// 관측할 길이 없다(위 observe 주석 참고). 탐색 비용은 작다 - 손실률 5%,
// 실패비용 150 ms 라면 20 연결에 한 번 무방비로 가는 값이
// 0.05 x 0.1 x 150 = 0.75 ms 다.
func (c *destCache) decide(addr string, w, mMax, coldM,
	probeEvery int) (int, string, bool) {
	c.mu.Lock()
	st := c.M[addr]
	var snap destStat
	if st != nil {
		snap = *st
	}
	c.mu.Unlock()

	if st == nil || snap.Conns < 1 || snap.MinHCT <= 0 || snap.K < 1 ||
		snap.ObsCount < 1 {
		return coldM, "콜드스타트(이 목적지 기록 없음)", true
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
	// 복구 실패 비용도 관측값이다. 아직 손실을 본 적이 없으면 보수적으로
	// 왕복 하나로 둔다(과대평가하면 쓸데없이 m 을 키우게 된다).
	extra := snap.LossHCT - rtt
	if extra <= 0 {
		extra = rtt
	}

	best, bestCost, why := 0, math.Inf(1), ""
	for m := 0; m <= mMax; m++ {
		n := expectedNRtt(k, m, w, p, snap.ServerFlight)
		pf := pfailLookup(k, m, p, 1.0)
		// 추가 바이트를 밀어내는 시간. 작지만 0 은 아니다 - 이 항이 없으면
		// 이득이 같을 때도 무조건 큰 m 을 고른다.
		tx := float64(m*parityDatagramBytes(w, k)) * 8.0 / 10e6 * 1000.0
		cost := n*rtt + pf*extra + tx
		if cost < bestCost {
			bestCost, best = cost, m
			why = fmt.Sprintf("S=%.0f p=%.4f 실패비용=%.0fms E[n_rtt]=%.3f "+
				"P(실패)=%.4f 비용=%.2fms", snap.ServerFlight, p, extra, n,
				pf, cost)
		}
	}
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
	cost0 := expectedNRtt(k, 0, w, p, snap.ServerFlight)*rtt +
		pfailLookup(k, 0, p, 1.0)*extra
	probeCost := cost0 - bestCost
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
				return 0, fmt.Sprintf("탐색(주기 %d, 탐색비용 %.1fms)",
					every, probeCost), true
			}
		}
		c.mu.Unlock()
	}
	return best, why, best == 0
}
