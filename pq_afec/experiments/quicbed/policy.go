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
//   롱헤더+CID(약 26) + FEC 머리(13) + crc/len 목록(6k) + 심볼(W)
//
// 🩸 2026-08-20 p13 실측 수정. 예전 값 32 는 CID 를 과소평가했다 - 실측
// 패리티(서버 연결별 회계 beff_parity)는 x25519 1323.5~1326.5 /
// ML-KEM 1331~1332 로 W+32+6k 보다 ~7 B 크다. CID 길이가 연결마다 달라
// ±수 B 흔들리며, 중앙값 기준 base ≈ 39 다. padfec/policy.py
// PARITY_OVERHEAD_BASE 와 같은 값이어야 한다(격자 대조가 잡는다).
func parityDatagramBytes(w, k int) int {
	return w + 39 + 6*k
}

// criticalPathBytes 는 업링크 직렬화가 **핸드셰이크를 실제로 늦추는** 바이트다.
// padfec/policy.py 의 critical_path_bytes 와 같은 식이며 근거도 거기 적혀 있다.
// 요점: 서버가 응답을 만들려면 원본(CRYPTO)이 다 와야 하는데, flushFlight 는
// m>=2 일 때만 패리티 하나를 원본보다 **먼저** 내보낸다.
func criticalPathBytes(k, m, w int) int {
	if m >= 2 {
		return k*w + parityDatagramBytes(w, k)
	}
	return k * w
}

// trailingParityBytes 는 **복구 가지에서만** 임계경로에 드는, 뒤따르는
// 패리티의 바이트다. Python padfec.policy.trailing_parity_bytes 와 같은 식.
//
// 🩸 2026-08-26 (2) **구조 수리** - criticalPathBytes 는 *첫 비행*의 임계경로
// 로는 옳지만 J 는 **완료 시각**이다. 복구가 일어나는 가지에서는 서버가 복구용
// 패리티(송신 순서상 마지막)까지 받아야 원본을 복원하므로 그 앞의 패리티들이
// 통째로 임계경로에 든다. 그전에는 이 비용이 **정확히 0** 이라 m=2·3·4 의
// t_tx 가 같았고, P_fail 은 안 오르므로 정책이 늘 m_max 를 골랐다.
//
// ⚠️ 인용 정정(2026-08-26 저녁): 이 수정을 **실측으로 정당화하지 않는다.**
// 처음 인용하던 p17 한 판(+0.73/+1.86)은 p18 이 같은 자리에서 −0.16/−1.26 로
// 뒤집었고, 판정하려면 팔당 8,544~12,404 판이 필요한데 지금 1,000 판이다.
// 남길 근거는 식 자체다 - 맞춘 상수가 없고, 무제한에서 옛 식과 비트 단위로
// 같다. 자세한 것은 padfec/policy.py 의 trailing_parity_bytes 에 한 곳으로.
func trailingParityBytes(k, m, w int) int {
	if m <= 0 {
		return 0
	}
	n := 1
	if m >= 2 {
		n = m - 1
	}
	return parityDatagramBytes(w, k) * n
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
	// 🩸 2026-08-21 - idxNearest 는 표 밖의 k·m 을 **조용히 가장 가까운
	//    마디로 잘라 읽는다.** k>=5 나 m>=3 을 주면 다른 기하의 분포를
	//    읽어 무손실 경로에서도 P_fail 이 1.0 이 나온다(감사 2026-08-21).
	//    조용히 틀린 답을 내느니 여기서 멈춘다 - 표를 늘릴 때까지는
	//    이 범위 밖을 지원하지 않는다는 것이 사실이기 때문이다.
	if k != pfailK[ki] || m != pfailM[mi] {
		panic(fmt.Sprintf(
			"jointLookup: 표 범위 밖 (k=%d m=%d). 표는 k=%v m=%v 만 담는다 - "+
				"padfec/table.py 의 K_VALS/M_VALS 를 늘리고 다시 심어라",
			k, m, pfailK, pfailM))
	}
	row := jointTable3[ki][mi]

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

// failFracLookup 은 실패 질량을 세 가지로 나눌 **비율**을 준다.
// padfec/table.py 의 fail_frac 이 만든 표를 읽는다. p 보간은 jointLookup 과
// 같은 식이어야 한다 - 두 표가 다른 p 에서 읽히면 회계가 갈라진다.
//
// 왜 확률이 아니라 비율인가: 총 실패 질량은 flightOutcome 이 jointTable3 에서
// 이미 정확히 세므로, 비율만 곱하면 총합이 옛 값과 비트 단위로 같다.
// 근거는 padfec/table.py fail_frac 주석.
func failFracLookup(k, m int, p, l float64) (float64, float64, float64) {
	ki := idxNearest(pfailK, k)
	mi := idxNearest(pfailM, m)
	li := idxNearestF(pfailL, l)
	if k != pfailK[ki] || m != pfailM[mi] {
		panic(fmt.Sprintf(
			"failFracLookup: 표 범위 밖 (k=%d m=%d)", k, m))
	}
	row := failFracTable[ki][mi]
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
	f0 := a[0]*(1-t) + b[0]*t
	f1 := a[1]*(1-t) + b[1]*t
	f2 := a[2]*(1-t) + b[2]*t
	sum := f0 + f1 + f2
	if sum <= 0 {
		return 1, 0, 0
	}
	return f0 / sum, f1 / sum, f2 / sum
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
// 2026-08-21 - serverFlight(전체 도착 기준 고정값) 대신 **nStar**
// (필요한 칸 수, 연결마다 하나의 상수)를 받는다. 근거는 Python
// quantum._candidate 의 n_need 주석. 부분 손실 상태에서 서버가 가진 적도
// 없는 큰 S 를 쓰던 것이 가짜 절벽을 만들었다.
// ---------------------------------------------------------------------------
// 증폭 신용의 '경주' — 뒤따르는 패리티는 **송신 결정 전에** 닿아야 신용이 된다
//
// 🩸 2026-08-26 구조 수리. 근거·측정·한계는 padfec/policy.py 의 '경주' 절에
//    한 곳으로 적어 뒀다. 여기는 그 식을 옮겨 적은 것뿐이고, 두 벌이 같은지는
//    experiments/gate_go_parity.py 가 격자로 못 박는다.
//
//    송신 순서(qamp.go flushFlight):
//      m = 1  : [원본..., 패리티]             패리티가 원본 뒤 -> 경주
//      m >= 2 : [패리티0, 원본..., 패리티1..]  앞선 하나는 결정적, 나머지는 경주
//    서버는 복호 가능한 마지막 패킷을 처리할 때 보낼지를 정하고, 패리티는
//    복호가 안 되므로 송신을 못 깨운다(quic-go connection.go:669).
// ---------------------------------------------------------------------------

// trailingParityDelayMs 는 뒤따르는 패리티 하나가 마지막 원본보다 늦게 도착하는
// 시간(ms)이다. Python trailing_parity_delay_ms 와 같은 식이어야 한다.
func trailingParityDelayMs(k, w int, uplinkMbps float64) float64 {
	if uplinkMbps <= 0 {
		return 0.0
	}
	return float64(parityDatagramBytes(w, k)) * 8.0 /
		(uplinkMbps * 1e6) * 1e3
}

// raceWinProb 는 지연 delayMs 로 도착한 패리티의 신용이 송신 결정에 잡힐
// 확률이다. 표는 pfail_table.go(자동 생성)에 있고 정의는 padfec/policy.py 다.
// Python race_win_prob 와 같은 식이어야 한다.
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

// creditBranches 는 송신 결정 시점의 신용 바이트를 (확률, 바이트) 가지로
// 쪼갠다. **복구가 없는 상태에서만** 부른다. Python credit_branches 와 같은
// 식이어야 하고, 가지를 만드는 **순서까지** 같아야 한다(부동소수 누적).
func creditBranches(a, w, parity, bCredit, r, m int,
	trailDelayMs float64) []creditBranch {
	nNonrec := 0
	if m >= 2 {
		nNonrec = m - 1
	}
	pLead := 0.0
	if nNonrec > 0 {
		pLead = float64(bCredit) / float64(nNonrec)
	}
	out := make([]creditBranch, 0, 4)
	leads := [2]int{1, 0}
	probs := [2]float64{pLead, 1.0 - pLead}
	for li := 0; li < 2; li++ {
		nLead, pL := leads[li], probs[li]
		if pL <= 0.0 {
			continue
		}
		nTrail := (bCredit - nLead) + r
		base := a*w + nLead*parity
		prev := 1.0
		for i := 1; i <= nTrail; i++ {
			qi := raceWinProb(float64(i) * trailDelayMs)
			if prev-qi > 0.0 {
				out = append(out, creditBranch{
					wgt: pL * (prev - qi), bytes: base + (i-1)*parity})
			}
			prev = qi
		}
		if prev > 0.0 {
			out = append(out, creditBranch{
				wgt: pL * prev, bytes: base + nTrail*parity})
		}
	}
	return out
}

func flightOutcome(k, m, w int, p, l float64,
	nStar int, trailDelayMs float64) (nExp, pFail, pRec float64) {
	parity := parityDatagramBytes(w, k)
	pm := jointLookup(k, m, p, l)
	cols := m + 1
	for a := 0; a <= k; a++ {
		for b := 0; b < cols; b++ {
			for r := 0; r < 2; r++ {
				idx := (a*cols+b)*2 + r
				if idx >= len(pm) {
					continue
				}
				pr := pm[idx]
				if pr <= 0 {
					continue
				}
				miss := k - a
				// 🩸 2026-08-21 - MDS(`k-a > b`)가 아니라 **구현의 규칙**이다.
				//    서버는 마지막으로 보낸 패리티(index m-1) 하나로 소거
				//    하나만 복구한다. Python policy.recovers 와 같다.
				rec := miss == 1 && r == 1
				if miss > 0 && !rec {
					// 🩸 2026-08-27 - 여기서는 **합계만** 센다.
					// 세 가지로 가르는 판별자(마지막 원본의 도착
					// 여부)가 이 루프의 축(a,b,r)에 없기 때문이다.
					// 비율은 failFracLookup 이 준다.
					// 근거·실측: padfec/policy.py last_original_pmf.
					pFail += pr
					continue
				}
				// 신용은 **서버 QUIC 스택이 실제로 센 바이트**다. 복구하면
				// 패리티를 버리고 복구본(원본 크기 w)을 대신 넘기므로 그
				// 만큼만 잡힌다. Python flight_outcome 과 같은 식이다.
				bCredit := b - r
				if rec {
					// 🩸 2026-08-26 - 복구가 일어난 상태에는 **경주가
					// 없다.** 서버는 복구용 패리티(송신 순서상 마지막)를
					// 받고 나서야 원본을 다 갖게 되므로, 송신 결정이 모든
					// 패킷보다 뒤에 온다.
					// 🩸 2026-08-26 (2) - 이 가지의 질량. 뒤따르는
					// 패리티가 임계경로에 드는 **유일한** 가지다.
					// Python flight_outcome 의 p_recovered 와 같다.
					pRec += pr
					arrived := a*w + bCredit*parity + w
					if binIndex(arrived) < nStar {
						nExp += pr * 2.0
					} else {
						nExp += pr
					}
					continue
				}
				// 복구가 없는 상태 = 원본이 다 왔다. 뒤따르는 패리티의
				// 신용은 마지막 원본을 처리하는 순간보다 먼저 닿아야 한다.
				for _, br := range creditBranches(a, w, parity, bCredit,
					r, m, trailDelayMs) {
					if binIndex(br.bytes) < nStar {
						nExp += pr * br.wgt * 2.0
					} else {
						nExp += pr * br.wgt
					}
				}
			}
		}
	}
	return nExp, pFail, pRec
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

// binNeeded 는 1-RTT 를 사려면 몇 번째 칸이 필요한지 준다 (명세 §2.5 고정점).
// padfec/quantum.py 의 bin_needed 와 **같은 산술**이다.
//
// 서버 비행 S 는 칸에 의존한다(칸이 오르면 서버가 패킷을 하나 더 쓴다).
// 그래서 "S 를 담는 칸"은 방정식이 아니라 고정점 n·P >= S(n) 의 최소해다.
// 여기서 받는 serverFlight 는 **지금 칸**의 관측값이므로, Python 이 쓰는
// 절대값 (cert + s0_base) 로 되돌린 뒤 같은 반복을 돈다.
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

// comboDeltas 는 부분 손실 상태 (a,b) 각각을 nNeed 칸으로 올리는 최소 δ 들이다.
// padfec/quantum.py 의 _combo_deltas 와 같다.
//
// 왜 필요한가 - 보조정리 1(같은 Δ 면 패리티가 패딩을 지배)이 2026-08-21 에
// 반증됐기 때문이다. 패리티의 신용은 **별도 데이터그램**이라 따로 유실되지만
// δ 는 살아남은 모든 데이터그램의 신용 바닥을 같이 올린다. 그래서 (δ>0, m>0)
// 결합이 둘 다보다 나은 구간이 있다(격자 12.7%, RTT 250 ms 에서 최대 72.5 ms).
//
// maxDelta < 0 이면 상한을 안 건다. Python 쪽은 None 이 같은 뜻이다.
func comboDeltas(k, m, w, ovh, nNeed, maxDelta int) []int {
	need := ((nNeed-1)*serverPacketSize)/amplificationFactor + 1
	set := map[int]bool{}
	for a := 0; a <= k; a++ {
		for b := 0; b <= m; b++ {
			if a+b == 0 {
				continue
			}
			if (k - a) > b { // 복구 불가 상태는 신용을 사도 소용없다
				continue
			}
			lack := need - (a+b)*w - b*ovh
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
			// 명세 §2.6 의 배치 의존성 가설은 p13 직접 측정으로 기각됐다 -
			// k=1·m=1 에서도 첫 비행 패리티는 100% 서버 결정 전에 도착해
			// 신용을 산다(results/p13_beff.json). 필드는 동점 처리 골격
			// 호환으로 남기고 항상 false. quantum.py 와 같은 값이어야 한다.
			lateParity: false,
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
	uniq := make([]cand, 0, len(out))
	for _, c := range out {
		key := fmt.Sprintf("%s|%d|%d", c.mode, c.clientBytes, c.m)
		if seen[key] {
			continue
		}
		seen[key] = true
		uniq = append(uniq, c)
	}

	// 🆕 결합 후보 (δ>0 · m>=0). 보조정리 1 정정의 따름정리 - comboDeltas 주석.
	// **기존 후보와 (바이트, m) 이 같은 것은 안 넣는다.** 같은 것을 이름만 바꿔
	// 넣으면 동점 처리(mode 이름)가 흔들려 예전 결정이 이유 없이 바뀐다.
	// Python quantum.levers 와 순서까지 같아야 격자 대조가 성립한다.
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
// uplinkMbps — 업링크 대역. 0 이하면 직렬화 시간을 **안 청구한다**.
//
//	🩸 2026-08-21 수리. 그전에는 이 자리에 `10e6` 이 리터럴로 박혀 있었고
//	   Python cost_of_v2 의 기본값과 "같은 값이니 괜찮다"고 적어 뒀다. 두 가지가
//	   틀렸다. (1) 10 Mbps 는 **어디서도 측정된 적이 없는 수**다 - 명세에도
//	   없다. (2) 우리 테스트베드의 netem 은 대역을 안 걸어서 이 항이 **실측과
//	   25 배 어긋난다**(p14 무손실: 1,324 B 추가에 실측 0.043 ms vs 모형
//	   1.06 ms). 그런데 이 항은 "이득이 같으면 큰 m 을 고르는 편향"을 막는
//	   **유일한 힘**이라, 틀리면 결정이 통째로 흔들린다 - 격자 720 점 중
//	   312 점(43.3%)에서 선택이 뒤집힌다. p11·p15 의 실패 조건이 정확히
//	   이것이었다(임계아래/손실5%, 임계사이/손실2%: 모형은 m=1, 실측 최선은 m=2).
//	   그래서 **리터럴을 없애고 인자로 뺀다.** 호출부(qamp -uplink-mbps)가
//	   자기가 도는 링크의 값을 준다. 재는 쪽은 p16 이 만든다.
func evalCands(cs []cand, k, w int, serverFlight, rtt, p, burst, cPkt float64,
	maxIPS int, uplinkMbps float64) []scored {
	tPTO := defaultTRecover(rtt, false)
	tACK := defaultTRecover(rtt, true)
	baseBytes := k * w
	// 필요한 칸 수. 도착 상태와 무관한 연결 상수다 (Python n_need 와 같다).
	nStar := binNeeded(serverFlight, binIndex(baseBytes), cPkt)

	out := []scored{}
	for _, c := range cs {
		if maxIPS > 0 && c.wEff > maxIPS {
			// 보낼 수 없는 후보다. 2026-08-20 실측: -ips 1707 을 줘도
			// quic-go 는 1452 B 로 깎아 보낸다.
			continue
		}
		// 2026-08-21 - `sf := serverFlight + steps*cPkt` 를 지웠다.
		// 필요한 칸은 후보와 무관한 상수이고 위에서 한 번만 구한다.
		// 🩸 2026-08-26 - 뒤따르는 패리티의 신용이 송신 결정 전에
		// 닿는지가 대역에 달렸다. 그 지연을 여기서 재서 넘긴다.
		n, pFailTot, pRec := flightOutcome(c.k, c.m, c.wEff, p, burst, nStar,
			trailingParityDelayMs(c.k, c.wEff, uplinkMbps))
		// 🩸 2026-08-27 - 실패 한 번의 대가가 **셋**으로 갈린다.
		// 판별자는 「마지막 원본이 도착했는가」다(RFC 9002 §6.1: 뒤에
		// 보낸 패킷이 ACK 돼야만 손실을 선언할 수 있는데, 우리 패리티는
		// 클라 패킷 번호를 안 갖고 영영 ACK 되지 않는다).
		// 근거·실측(p7 V2/V3/V9 가 96 ms 로 갈린다)은 Python
		// padfec/policy.py 의 last_original_pmf 주석에 있다.
		fNo, fSamp, fAck := failFracLookup(c.k, c.m, p, burst)
		pto := pFailTot * fNo
		ptoS := pFailTot * fSamp
		ack := pFailTot * fAck
		added := c.clientBytes - baseBytes
		if added < 0 {
			added = 0
		}
		// 🩸 2026-08-21 p16 실측 수리. 직렬화가 **핸드셰이크를 실제로 늦추는**
		// 바이트만 센다. 송신 순서(qamp.go flushFlight)가 m 으로 갈리기 때문이다.
		//   m = 1  : [원본..., 패리티]  -> 패리티가 뒤라 원본을 안 늦춘다
		//   m >= 2 : [패리티0, 원본...] -> 앞선 하나가 원본을 늦춘다
		// 실측(rate 10mbit, k=1): m=1 은 0.002 ms 인데 옛 식은 1.061 ms 를
		// 청구했다(530 배). Python criticalPathBytes 와 같은 식이어야 한다.
		txAdded := criticalPathBytes(c.k, c.m, c.wEff) -
			criticalPathBytes(k, 0, w)
		if txAdded < 0 {
			txAdded = 0
		}
		// 직렬화 시간. uplinkMbps <= 0 이면 대역 제한이 없다는 뜻이라 0 이다.
		// Python padfec.policy.tx_cost_ms 와 **같은 식**이어야 한다.
		// 🩸 2026-08-26 (2) - 복구 가지의 직렬화를 더한다. 대역이 무제한
		// (uplinkMbps <= 0)이면 **두 항 다 0** 이라 옛 식과 비트 단위로
		// 같다. Python cost_of_v2 와 같은 식·같은 순서여야 한다 -
		// 부동소수 누적이라 순서가 다르면 마지막 자리가 갈린다.
		tx := 0.0
		if uplinkMbps > 0 {
			tx = float64(txAdded) * 8.0 / (uplinkMbps * 1e6) * 1000.0
			tx += pRec * (float64(trailingParityBytes(c.k, c.m, c.wEff)) *
				8.0 / (uplinkMbps * 1e6) * 1000.0)
		}
		// 🩸 2026-08-27 **구조 수리 — ACK 실패 가지에 왕복 수를 안
		// 물리고 있었다.** T_recover 두 상수는 *기준선 대비 증분*으로
		// 쟀고(probe_trecover_rtt.json: t = drop_p50 - base_p50, 그
		// 기준선은 1-RTT), 이 식은 `rtt + t` 로 청구한다. 기준선이
		// 2 왕복인 팔에서는 왕복 하나가 통째로 빈다.
		//   ACK 가지 : 잃은 것만 다시 보내므로 누적 신용이 깨끗한 비행과
		//              같다 -> 그 팔의 정상 왕복 수가 그대로 든다.
		//   PTO 가지 : 비행 전체를 다시 보내 신용이 두 배가 된다 -> 그 뒤는
		//              1 왕복. 옛 식이 옳으므로 **안 건드린다.**
		// 실측 근거와 반증 시험은 Python padfec/policy.py cost_of_v2 의
		// 같은 자리 주석에 있다. 두 파일은 **같은 식**이어야 한다.
		ok := 1.0 - pFailTot
		nGivenOK := 2.0
		if ok > 1e-15 {
			nGivenOK = n / ok
		}
		// 세 가지가 무는 왕복 수도 다르다. 표본 없는 PTO 는 클라가 비행
		// 전체를 다시 보내 신용이 두 배가 되므로 1 왕복이고, 나머지 둘은
		// 못 받은 것만 다시 보내므로 그 팔의 정상 왕복 수(nGivenOK)가 든다.
		// Python cost_of_v2 와 **같은 식·같은 순서**여야 한다.
		tPTOSampled := ptoSampledRttMult * rtt
		j := n*rtt + pto*(rtt+tPTO) + ptoS*(nGivenOK*rtt+tPTOSampled) +
			ack*(nGivenOK*rtt+tACK) + tx
		out = append(out, scored{c: c, j: j, added: added})
	}

	// 동점 처리 (명세 §3): J -> 실제 추가 바이트 -> 같은 바이트면 패리티 우선
	//                    -> late_parity 없는 쪽 -> over_mtu 없는 쪽 -> mode 이름.
	// 동점 구간 안에서의 순서 (명세 §3). J 는 안 들어간다 - **동점으로 본
	// 것들끼리** 고르는 자리이기 때문이다. Python _tie_key 와 같아야 한다.
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

	// 🩸 2026-08-21 - 2 단 argmin. Python _pick_best 와 같은 절차다.
	//
	//  1) **정확한 J** 로 오름차순 정렬한다 (같으면 tieLess).
	//  2) 최소에서 jTieMs 이내인 앞부분만 동점으로 보고 tieLess 로 다시 세운다.
	//
	// 왜 J 를 양자화(버킷)하지 않는가: 버킷 경계에서는 아주 작은 차이가 칸을
	// 가르므로, Go(표+보간)와 Python(정확 계산)의 미세한 J 차이가 순위
	// 뒤집힘으로 **증폭**된다. 실제로 그렇게 해 봤다가 격자 대조 불일치
	// 117 건으로 드러났다(2026-08-21). 근거 전문은 policy.py _pick_best 주석.
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
	// 무편향(m=0) 연결들만의 최소 HCT. 손실 분류의 기준선이다 - 아래
	// observe 의 주석 참고. MinHCT(전체 최소)와 다르다: 임계 위 목적지에서
	// FEC 로 1-RTT 를 사는 동안 탐색은 2-RTT 로 돌 수 있는데, 그때 전체
	// 최소(52 ms)로 탐색(103 ms)을 분류하면 깨끗한 탐색이 전부 손실로 보인다.
	ProbeMinHCT  float64 `json:"probe_min_hct_ms"`
	// 🆕 C1 (2026-08-23) - **심볼 단위** 관측. 서버 수신 회신이 있으면
	// 연결마다 k+m 심볼의 도착 여부를 그대로 알 수 있다. 위 LossCount 는
	// **연결 단위**(그 연결에 손실이 있었나)라 단위가 다르므로 섞으면 안 되고,
	// 그래서 필드를 따로 둔다. 피드백을 끄면 이 둘이 0 으로 남아 기존
	// 경로가 그대로 쓰인다 - 음성 대조가 공짜로 된다.
	//
	// 왜 필요한가(p17 실측): 탐색 기반 관측은 구간당 7~8 개뿐이라 유효
	// 기억 100 을 못 갈아치우고, 손실 상승 적응률이 **0%** 였다.
	SymLoss float64 `json:"sym_loss"`
	SymObs  float64 `json:"sym_obs"`
	// C2(회신 없는 연결을 전멸로 본 것)가 위 통계에 얼마나 기여했는지.
	// 판정에는 안 쓰고 **원인을 가르는 자료로만** 남긴다 - 낮은 손실에서
	// p̂ 가 과대하면 여기부터 본다.
	SymC2Conns  float64 `json:"sym_c2_conns"`
	SymC2Symbols float64 `json:"sym_c2_symbols"`
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
		// 🩸 2026-08-20 p11 계측 수리. 호출부가 주는 lossEvent(비행 크기
		// 재전송 패턴)는 실측으로 두 사각지대가 확인됐다.
		//  (1) k>=2 의 단일 손실: 잃은 조각만 크기 1 비행으로 재전송되므로
		//      "같은 크기 비행 2회" 신호가 안 잡힌다. 실측(m0·k2·손실5%):
		//      감지 8/120 = 6.7%, 실제 연결당 손실 ~9.8%. 손실 0% 와 2% 가
		//      같은 선택 수열을 만들 정도로 추정이 눈멀었다(p11 원자료).
		//  (2) k=1 의 총 Initial 수 신호는 깨끗한 2-RTT 연결(Initial 3개)을
		//      손실로 오인할 수 있다.
		// 손실은 어느 유형이든 HCT 를 최소 T_ack(1.125·RTT+1.4)만큼 늘리므로,
		// **무편향 연결들 자신의 최소 HCT** 를 기준선으로 다시 분류한다.
		// x1.3+2ms 는 ACK 가지와 PTO 가지를 모든 RTT 에서 잡고, netem 지연이
		// 결정적인 이 테스트베드에서는 오탐이 없다. 지터 있는 실경로에서는
		// 여유를 다시 재야 한다(그때는 이 상수의 출처가 여기라는 것이 단서다).
		if st.ProbeMinHCT > 0 && hctMs > 0 {
			lossEvent = hctMs > st.ProbeMinHCT*1.3+2.0
		} else {
			lossEvent = false // 첫 무편향 관측은 기준선이 없어 분류 불가
		}
		if hctMs > 0 && (st.ProbeMinHCT <= 0 || hctMs < st.ProbeMinHCT) {
			st.ProbeMinHCT = hctMs
		}
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

// minHCT 는 이 목적지의 RTT 추정(최소 관측 HCT)을 준다. 없으면 0.
// C2 가 "이 연결이 PTO 를 물었는가"를 판정할 기준선으로 쓴다.
func (c *destCache) minHCT(addr string) float64 {
	c.mu.Lock()
	defer c.mu.Unlock()
	if st := c.M[addr]; st != nil {
		return st.MinHCT
	}
	return 0
}

// observeSymbols 는 심볼 단위 관측을 적립한다 (C1 서버 회신 / C2 PTO).
//
// nSym  이 연결에서 **보낸** 첫 비행 심볼 수 (원본 k + 패리티 m)
// nLost 그중 서버에 **도달하지 않은** 수
//
// 탐색 라운드와 달리 m>0 이어도 편향이 없다 - 서버가 "받은 것"을 세므로
// 복구가 손실을 가리지 않는다. 그래서 모든 연결에서 갱신할 수 있다.
func (c *destCache) observeSymbols(addr string, nSym, nLost int,
	hctMs float64) {
	c.observeSymbolsWhy(addr, nSym, nLost, hctMs, false)
}

// observeSymbolsWhy - c2 가 true 면 "회신 없음을 전멸로 본" 적립이다.
//
// 🩸 2026-08-23 - hctMs 를 함께 받아 MinHCT 를 갱신한다. 그전에는 MinHCT 가
//    `observe()` 에서만 갱신됐는데 그것은 **auto 모드에서만** 불린다. 그래서
//    고정팔로 도는 동안 기준선이 0 으로 남아 C2 판정(hct > 3*base)이 아예
//    발동하지 못했다(실측: 회신 없는 연결 34 건인데 C2 적립 0).
func (c *destCache) observeSymbolsWhy(addr string, nSym, nLost int,
	hctMs float64, c2 bool) {
	if nSym <= 0 || nLost < 0 || nLost > nSym {
		return // 말이 안 되는 값은 버린다 - 조용히 캐시를 오염시키느니
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
	// 🩸 2026-08-23 - 손실을 **루프 밖에서 한꺼번에** 더하면 감쇠를 nSym 번
	//    덜 받아 과대 추정된다. 관측과 같은 자리에서 세야 단위가 맞는다.
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
	burst, cPkt float64, maxSteps, maxIPS int,
	uplinkMbps float64) (int, int, string, bool) {
	c.mu.Lock()
	st := c.M[addr]
	var snap destStat
	if st != nil {
		snap = *st
	}
	c.mu.Unlock()

	if st == nil || snap.Conns < 1 || snap.MinHCT <= 0 || snap.K < 1 ||
		snap.ObsCount < 1 {
		// 🩸 2026-08-27 - 네 번째 반환값은 「이 판을 손실 관측에 써도
		//    되는가」인데 **리터럴 true** 였다. coldM > 0 이면 이 판은
		//    패리티로 보호되므로 소거가 복구돼 손실이 **안 보인다** -
		//    그 판으로 추정한 p 는 아래로 편향된다. 지금은 기본값이
		//    `-cold-m 0` 이라 드러나지 않지만, 계약이 코드와 어긋난 채로
		//    두면 누가 -cold-m 을 켜는 순간 조용히 틀린다.
		//    (destStat.ProbeMinHCT 주석이 말하는 계약 그대로다.)
		return w, coldM, "콜드스타트(이 목적지 기록 없음)", coldM == 0
	}
	// 탐색 주기는 뒤에서 정한다 - 얼마나 비싼지 알아야 하기 때문이다.
	k := snap.K
	rtt := snap.MinHCT
	// 연결당 손실 사건 비율 -> 데이터그램당 손실률.
	// Jeffreys 사후평균을 쓴다: (손실+0.5)/(관측+1).
	//
	// 🆕 C1 - 심볼 단위 관측이 있으면 그것을 쓴다. 그 통계는 **이미 심볼
	// 단위**라 연결->심볼 환산(1-(1-pConn)^(1/k))을 하면 안 된다.
	// 없으면(피드백 off) 기존 연결 단위 경로 그대로.
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
	ranked := evalCands(
		levers(k, w, maxSteps, mMax, snap.ServerFlight, cPkt, maxIPS),
		k, w, snap.ServerFlight, rtt, p, burst, cPkt, maxIPS, uplinkMbps)
	if len(ranked) == 0 {
		return w, 0, "후보가 하나도 안 남았다", true
	}
	bestC := ranked[0]
	bestCost := bestC.j
	why := fmt.Sprintf("%s δ=%d m=%d ips=%d 추가=%dB | S=%.0f p=%.4f "+
		"T_pto=%.0f T_ack=%.0f 비용=%.2fms",
		bestC.c.mode, bestC.c.delta, bestC.c.m, bestC.c.wEff, bestC.added,
		snap.ServerFlight, p, tPTO, tACK, bestC.j)
	// 🩸 2026-08-21 - jointLookup 의 보간 t 는 [0,1] 로 잘리므로 표
	// 상한(p=0.30) 을 넘는 p 는 **조용히** 0.30 행을 읽는다. 콜드
	// 구간(관측 1 회 + 손실 1 회 -> p=0.75)에서 실제로 도달한다.
	// 직접 확인한 결과 m_max=2 가 이미 상한이라 **선택은 안 바뀌지만**
	// (cert 2955/4032/9000 에서 p=0.30~0.75 전부 같은 답), 조용한
	// 절단을 남겨 두지는 않는다. 자료(m_why)에 그대로 찍는다.
	if pMax := pfailP[len(pfailP)-1]; p > pMax {
		why += fmt.Sprintf(" | ⚠p표상한절단 %.4f->%.4f", p, pMax)
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
	// 🆕 Step D - **피드백이 있으면 탐색하지 않는다.**
	// 탐색 라운드는 관측을 얻으려고 일부러 m=0 으로 가는 것이고, 그 대가가
	// p11 실측 +0.48~0.51 ms/연결(임계위 후회의 25~40%)이었다. 서버 회신이
	// 연결마다 k+m 심볼을 주므로 그 대가를 낼 이유가 없다.
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
	// 🆕 2026-08-21. up(업링크 Mbps) 축을 더한다. 그전에는 이 항이 양쪽에
	// 리터럴 10 Mbps 로 박혀 있어서 **격자 대조가 이 항의 갈라짐을 원리적으로
	// 못 잡았다.** 인자로 뺀 이상 자도 그 축을 훑어야 한다. 0 = 대역 무제한
	// (직렬화 시간 없음) 이고, 이게 우리 테스트베드의 실제 조건이다.
	for _, k := range []int{1, 2, 3} {
		for _, w := range []int{1200, 1280, 1350} {
			// 2026-08-21 - 3200 / 5800 / 10800 / 12000 을 더했다. n* 수정이
			// 필요했던 자리(단조성 위반·후보 누락이 나던 cert)를 격자가
			// 하나도 안 밟고 있었다 - 그래서 '불일치 0' 이 그 영역을
			// 전혀 안 지켰다.
			for _, cert := range []int{1000, 2308, 3000, 3200, 4032, 5609,
				5800, 6500, 8000, 10800, 12000} {
				// 🩸 2026-08-25 - 396.5 / 1527.5 는 **폐기된 c=34.5 세대**의
				//    값이다(padfec/quantum.py 머리말이 스스로 "폐기"라 적어
				//    두었다). 이 둘만 훑으면 관문이 **실제 운용 상수를 한 번도
				//    안 지난다** - 정본에서만 드러나는 갈라짐은 원리적으로 못
				//    잡는다. 정본(382.45 / 1472.00)을 같이 훑는다. 옛 값도
				//    남긴다 - 식 자체의 비교는 인자와 무관하게 유효하고,
				//    격자를 좁히면 덮는 범위가 줄기 때문이다.
				for _, s0base := range []float64{396.5, 1527.5, 382.45, 1472.0} {
					for _, rtt := range []float64{10, 50, 100} {
						for _, p := range []float64{0, 0.005, 0.007, 0.02, 0.035, 0.05, 0.15, 0.2} {
							for _, l := range []float64{1, 2, 3} {
								for _, up := range []float64{0, 10, 100} {
									// 관측 S 는 **지금 칸**의 값이다. Python 은
									// s0_at(n) = s0_base + n·c 로 절대값을 쓰므로,
									// 같은 것을 가리키도록 지금 칸 수를 곱해 준다.
									base := k * w
									S := float64(cert) + s0base +
										float64(binIndex(base))*cPktDefault
									r := evalCands(
										// 🩸 2026-08-25 - 여기 mMax 가 리터럴 2 였다.
										//    Python 이 상한을 3 으로 올렸을 때 이 자만
										//    옛 상한으로 답해 관문이 15,561 건 불일치를
										//    신고했다. 바로 위 머리말이 업링크에 대해
										//    지적한 사고와 같은 것이다 - 지적해 놓고
										//    옆 인자에서 같은 일을 하고 있었다.
										levers(k, w, maxStepsDefault, mMaxDefault, S,
											cPktDefault, quicgoMaxIPS),
										k, w, S, rtt, p, l, cPktDefault,
										quicgoMaxIPS, up)
									b := r[0].c
									// 2026-08-27 - **J 도 찍는다.** 관문이 여태 "결정이 같은가"만
									// 봤기 때문에, 결정을 안 뒤집는 J 어긋남은 통째로 안 보였다
									// (감사 2026-08-27). 같은 후보에 대한 두 언어의 J 를 대조할 수
									// 있어야 표 보간 오차가 실제로 얼마인지 사람이 알 수 있다.
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
