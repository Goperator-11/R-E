# -*- coding: utf-8 -*-
"""정책이 쓰는 복구 실패 확률표를 Go 소스로 뽑아낸다.

왜 표인가
--------
폐루프를 닫으려면 결정이 **클라이언트 안에서** 일어나야 하고, 우리 클라이언트는
Go 다. 그런데 Gilbert-Elliott 소거 분포를 Go 로 다시 짜면 두 구현이 갈라진다 -
이번 연구에서 이미 Cauchy 생성행렬로 그 일을 겪었다(둘 다 MDS 였지만 서로
호환되지 않았고, 교차검증이 아니었으면 못 잡았다).

그래서 **다시 짜지 않는다.** 검증이 끝난 Python 모형으로 표를 만들어 Go 에
심고, Go 는 조회만 한다. 나머지(증폭 예산 산술)는 곱셈과 나눗셈뿐이라
그대로 옮겨도 갈라질 여지가 없다.

표 크기: k 4개 x m 3개 x p 11개 x L 4개 = 528 개. 심어도 부담이 없다.

사용
    python -m padfec.table experiments/quicbed/pfail_table.go

🩸 stdout 리다이렉션으로 쓰면 안 된다. 윈도우 콘솔이 cp949 라 한글 주석이
깨져 Go 가 "illegal UTF-8 encoding" 으로 거부한다. 파일을 직접 연다.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from padfec import policy   # noqa: E402

K_VALS = [1, 2, 3, 4]
# 🩸 2026-08-25 - m=3 을 추가했다. policy.M_MAX_DEFAULT 와 **반드시**
#    맞아야 한다 - policy.go 는 표에 없는 (k,m) 을 받으면 죽는다
#    (experiments/quicbed/policy.go 119 행). 근거는 policy.py 의
#    M_MAX_DEFAULT 주석: cert 14,601~16,125 에서 m=2 는 2-RTT,
#    m=3 은 1-RTT 라는 실측.
M_VALS = [0, 1, 2, 3]
# 🩸 2026-08-25 - 0.15 를 마디로 추가했다. 관문이 42,768 격자점 중
#    2 건에서 불일치를 신고했는데(k=3 cert=12000 rtt=100 **p=0.15**),
#    Python J 로 본 대가가 0.104 ms 로 보간 허용치 0.100 ms 를 아슬하게
#    넘었다. 원인은 0.15 가 마디가 아니라 0.12~0.20 **사이**라 Go 가
#    넓은 구간을 선형보간한 것이다. 자를 늘리는 대신 **표를 촘촘히**
#    한다 - 게다가 0.15 는 우리가 실제로 재는 손실률이다(p3/p11/p18).
P_VALS = [0.0, 0.002, 0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.12, 0.15,
          0.20, 0.30]
# 🩸 2026-08-28 - 버스트 축을 **정규화 좌표 u = L·(1-p) 로 바꿨다.**
#    (그전에는 L_VALS = [1.0, 2.0, 3.0, 5.0] 이었다.)
#
#    왜: P_fail 은 L 에 대해 매끄럽지 않다. GilbertElliott.for_prior 는
#    L <= 1/(1-p) 이면 독립 손실을, 그 위에서는 GE 를 쓴다(afec/channel.py
#    의 2026-08-21 정정 - iid 채널의 평균 버스트가 1 이 아니라 1/(1-p) 라서
#    경계를 거기로 옮겼다). 그래서 **L = 1/(1-p) 에 꺾인 점이 있다.**
#    p=0.2 면 1.25, p=0.05 면 1.053 - **꺾이는 자리가 p 에 따라 움직인다.**
#    고정된 L 격자는 이 꺾인 점을 원리적으로 못 얹는다. 곡선은 꺾인 점
#    왼쪽에서 완전히 평평하다가 오른쪽에서 급히 오르므로, 그 위를 가로질러
#    선형보간하면 평평한 구간을 크게 부풀린다.
#
#    u = L·(1-p) 로 바꾸면 꺾인 점이 **모든 p 에서 u = 1** 이 되어
#    첫 마디에 정확히 얹힌다. 실측한 개선(288 조건에서 J 오차):
#        현행 L 4 점    평균 0.3502  최악 1.6840 ms
#        u    8 점     평균 0.0738  최악 0.3778 ms
#        u   12 점     평균 0.0273  최악 0.1171 ms
#        u   21 점     평균 0.0102  최악 0.0594 ms   <- 관문 한도 0.100 통과
#    그래서 21 점이다. 표가 5.25 배 커지지만(273 KB -> 약 1.4 MB) 생성물이라
#    사람이 읽을 것도 아니고, 그 대가로 **버스트 축이 처음으로 정확해진다.**
#
#    이름을 L_VALS -> U_VALS / pfailL -> pfailU 로 바꾼 것은 의도적이다.
#    반쯤 적용된 변경이 **조용히 도는 대신 빌드에서 깨지게** 하려는 것이다
#    (jointTable3 -> jointTable4 때와 같은 이유).
#    간격은 균등하지 않다. **꺾인 점 바로 오른쪽이 가장 급하다**(곡선이
#    평평하다가 그 자리에서 꺾여 오르므로 곡률이 거기 몰린다). 21 점 균등
#    (0.125 간격)으로 돌렸더니 최악 J 어긋남이 u=1.2 에서 0.104 ms 로
#    한도 0.100 을 4% 넘었다. 선형보간 오차는 구간 길이의 제곱에 비례하므로
#    [1, 1.5] 만 0.0625 로 반 접으면 그 구간 오차가 약 1/4 이 된다.
U_VALS = ([round(1.0 + 0.0625 * i, 4) for i in range(8)]      # 1.0 ~ 1.4375
          + [round(1.5 + 0.125 * i, 3) for i in range(13)]    # 1.5  ~ 3.0
          + [3.5, 4.0, 4.5, 5.0])


def _clamp_p(p):
    """afec.channel.GilbertElliott.for_prior 와 **같은** 클램프.

    Go 쪽(policy.go 의 u 계산)도 이 식을 쓴다. 셋이 갈라지면 표를 만든
    지점과 읽는 지점이 어긋나므로, 근거를 여기 한 곳에 둔다.
    """
    return min(max(p, 0.0), 0.999)


def _L_of(p, u):
    """정규화 버스트 u 를 실제 평균 버스트 L 로 되돌린다."""
    return u / (1.0 - _clamp_p(p))


def pfail(k, m, p, L):
    """k+m 개 중 m 개를 넘게 잃어 복구가 안 될 확률.

    m = 0 은 이중화가 없다는 뜻이므로 '하나라도 잃으면 실패' 다.
    """
    if p <= 0.0:
        return 0.0
    if m == 0:
        return float(1.0 - policy.erasure_probs(k, p, L)[0])
    return policy.p_unrecoverable(k, m, p, L)


def joint(k, m, p, L):
    """P[a][b][r] = 원본 a·패리티 b 도착, r = 복구용 패리티가 왔는가.

    🩸 2026-08-21 - 2 지표에서 3 지표로 늘렸다. "몇 개 왔나"만으로는 복구
       여부를 알 수 없기 때문이다. 구현(qamp.go)은 **마지막으로 보낸 패리티
       하나로 소거 하나만** 복구하는데, 예전 표는 MDS(패리티 b 개면 소거 b
       개까지)를 가정한 채로 Go 에 심겨 있었다. 자세한 근거는
       padfec/policy.py joint_arrival_pmf3 주석.
    """
    return policy.joint_arrival_pmf3c(k, m, p, L)


def _check_consistent():
    """표의 m 범위와 정책 상한이 어긋나면 **표를 만들지 않는다.**

    🩸 2026-08-25 - 어긋나면 policy.go 가 표에 없는 (k,m) 을 받고
       죽는데(policy.go 119 행), 그건 **실행 중**에 터진다. 측정을
       한참 돌린 뒤에 알게 되느니 생성 시점에 막는다.
    """
    if max(M_VALS) != policy.M_MAX_DEFAULT:
        raise SystemExit(
            "표의 M_VALS 최대(%d) 와 policy.M_MAX_DEFAULT(%d) 가 다르다. "
            "둘을 맞춰라 - 안 맞으면 Go 가 실행 중에 죽는다."
            % (max(M_VALS), policy.M_MAX_DEFAULT))

    # 🩸 2026-08-28 - **u 축의 전제를 여기서 못박는다.**
    #    U_VALS 는 "꺾인 점(독립<->GE 경계)이 L = 1/(1-p) 에 있다"에 통째로
    #    기대고 있다. afec/channel.py 의 for_prior 가 그 경계를 옮기면
    #    (2026-08-21 에 실제로 한 번 옮겼다: `<= 1.0` -> `<= 1/(1-p)`)
    #    u=1 이 더 이상 꺾인 점이 아니게 되고, **표는 조용히 엉뚱한 좌표로
    #    만들어진다.** 관문이 결국 잡겠지만 그건 몇 분 뒤이고, 그때 보이는
    #    증상은 "J 가 좀 어긋난다"라 원인까지 가기 멀다. 여기서 막는다.
    for _p in (0.05, 0.15, 0.20):
        _lo = policy.p_fail_of({"k": 2, "m": 1}, _p, _L_of(_p, 1.0) * 0.999)
        _at = policy.p_fail_of({"k": 2, "m": 1}, _p, _L_of(_p, 1.0))
        _hi = policy.p_fail_of({"k": 2, "m": 1}, _p, _L_of(_p, 1.0) * 1.05)
        # 꺾인 점 왼쪽은 평평(독립 구간), 오른쪽은 올라야 한다.
        if not (abs(_lo - _at) < 1e-12 and _hi > _at + 1e-9):
            raise SystemExit(
                "u 축의 전제가 깨졌다: p=%g 에서 꺾인 점이 L=1/(1-p)=%.4f 가 "
                "아니다 (왼쪽 %.6g, 그 점 %.6g, 오른쪽 %.6g). "
                "afec/channel.py 의 for_prior 경계가 바뀌었으면 "
                "padfec/table.py 의 U_VALS 좌표도 같이 고쳐야 한다."
                % (_p, _L_of(_p, 1.0), _lo, _at, _hi))


def fail_frac(k, m, p, L):
    """실패 질량을 세 가지로 나눈 **비율** (합 1, 실패가 0 이면 (1,0,0)).

    🩸 2026-08-27 신설. 실패의 대가는 **마지막 원본이 도착했는가**로 갈린다
       (padfec/policy.py last_original_pmf - RFC 9002 §6.1 과 p7 의 V2/V3/V9).
       그 판별자는 결합 도착분포의 축(a, b, r)에 없으므로 jointTable4 만으로는
       Go 가 가를 수 없다.

    **표를 하나 더 싣되 확률이 아니라 비율을 싣는다.** 총 실패 질량은 Go 가
    이미 jointTable4 에서 정확히 세고 있으므로, 비율만 보간해서 곱하면
    (a) 총합이 옛 값과 **비트 단위로 같고** (b) 보간 오차가 세 가지 사이의
    배분에만 남는다. 확률 세 개를 따로 실으면 보간 뒤 합이 총 실패와 미세하게
    어긋나 회계가 두 군데로 갈라진다 - 이 저장소가 2026-08-20 감사 결함 1 에서
    겪은 것과 같은 형태다.
    """
    a, b, c = policy.fail_split(k, m, p, L)
    tot = a + b + c
    if tot <= 0.0:
        # 2026-08-27 - **경계값(1,0,0) 을 실으면 안 된다.** p=0 에서는
        #    실패 질량이 0 이라 비율이 정의되지 않는데, Go 는 마디 사이를
        #    **선형보간**하므로 0 < p < 0.002 인 모든 점에서 이 뜻 없는
        #    (1,0,0) 을 실제 비율 쪽으로 끌고 간다. 그 구간에서 Go 는
        #    가장 비싼 가지(표본 없는 PTO, 200.86 ms)에 질량을 몰아
        #    Python 보다 J 를 부풀린다 - 감사에서 m=0 후보 기준 최대
        #    0.168 ms 로 잡혔고, 그건 J_TIE_MS(0.01)의 17 배다.
        #    비율의 **극한값**(p -> 0+)을 실으면 보간이 연속이 된다.
        a, b, c = policy.fail_split(k, m, 1e-9, L)
        tot = a + b + c
        if tot <= 0.0:
            return (1.0, 0.0, 0.0)
    return (a / tot, b / tot, c / tot)


def build():
    _check_consistent()
    tab, jtab, ftab = {}, {}, {}
    for k in K_VALS:
        for m in M_VALS:
            for pi, p in enumerate(P_VALS):
                for li, u in enumerate(U_VALS):
                    # 마디마다 **그 p 에서의** 실제 L 로 되돌려 계산한다.
                    # 같은 u 라도 p 가 다르면 L 이 다르다 - 그게 이 좌표의
                    # 요점이다(꺾인 점을 u=1 에 고정한다).
                    L = _L_of(p, u)
                    tab[(k, m, pi, li)] = pfail(k, m, p, L)
                    jtab[(k, m, pi, li)] = joint(k, m, p, L)
                    ftab[(k, m, pi, li)] = fail_frac(k, m, p, L)
    return tab, jtab, ftab


def emit_go(tab, jtab, ftab, out):
    w = out.write
    w("// 자동 생성 파일. 손대지 마라.\n")
    w("//   생성: python -m padfec.table experiments/quicbed/pfail_table.go\n")
    w("//\n")
    w("// padfec/policy.py 의 Gilbert-Elliott 분포를 그대로 담은 표다.\n")
    w("// Go 로 다시 구현하지 않는 이유는 table.py 의 머리말에 적었다 -\n")
    w("// 같은 알고리즘을 두 언어로 짜면 갈라지고, 이 연구에서 이미 겪었다.\n")
    w("//\n")
    w("// 2026-08-20 감사 결함 1·3 의 수리로 **결합 도착분포**를 새로 싣는다.\n")
    w("//   예전에는 Go 가 pfail 만 표에서 읽고 기대 왕복 수는 제 손으로\n")
    w("//   이항분포를 굴려 셌다. 한 비용식 안에 손실 모형이 둘이었고,\n")
    w("//   버스트가 있으면 두 항이 다른 세계를 봤다. 이제 둘 다 여기서 나온다.\n")
    w("package main\n\n")

    w("// Go 는 버스트를 관측할 수단이 없다. 그 사실을 호출부 리터럴로 숨기지\n")
    w("// 않고 이름 있는 값으로 둔다. 정의는 padfec/policy.py 한 곳뿐이다.\n")
    w("const defaultAssumedBurst = %g\n\n" % policy.DEFAULT_ASSUMED_BURST)

    w("// 복구 실패 한 번의 대가. 2026-08-20 결정적 소거 실측\n")
    w("//   (experiments/_probe_trecover_rtt.py -> results/probe_trecover_rtt.json)\n")
    w("//   서버가 0 개 받음 -> ACK 없음 -> PTO.  RTT 와 무관한 상수.\n")
    w("//   1 개 이상       -> ACK -> 즉시 재전송. RTT 에 비례.\n")
    w("// 정의는 padfec/policy.py 한 곳뿐이다.\n")
    w("const tPTONoAckMs = %.10g\n" % policy.T_PTO_NO_ACK_MS)
    w("const tAckRetxSlope = %.10g\n" % policy.T_ACK_RETX_SLOPE)
    w("const tAckRetxBaseMs = %.10g\n\n" % policy.T_ACK_RETX_BASE_MS)

    w("// 정책이 쓰는 상수. 정의는 padfec/policy.py 한 곳뿐이다.\n")
    w("//   quicgoMaxIPS  실측: -ips 1707 을 줘도 클라는 1452 로 깎아 보낸다\n")
    w("//   cPktDefault   서버 첫 비행 유효 모형 S_eff(n)=s0_base+n*c 의 기울기.\n")
    w("//                 **물리 바이트 수가 아니라 임계를 재현하는 유효값**이다\n")
    w("//                 (2026-08-21: quic-go 는 마지막 패킷이 작으면 한도를\n")
    w("//                  최대 +72 B 넘겨 보낸다. 그 여유를 유효 s0 가 흡수한다).\n")
    w("//                 임계 앵커 6 개 최소제곱. 패킷 직접 계수(40.55/41.39)와\n")
    w("//                 1.5 B/패킷 안에서 일치한다 - 근거는 padfec/policy.py.\n")
    w("const quicgoMaxIPS = %d\n" % policy.QUICGO_MAX_IPS)
    w("const maxStepsDefault = %d\n" % policy.MAX_STEPS_DEFAULT)
    # 🩸 2026-08-25 - mMax 도 여기서 심는다. 그전에는 policy.go 의
    #    policyGrid 안에 **리터럴 2** 로 박혀 있어서, Python 이 상한을
    #    3 으로 올렸을 때 Go 격자만 옛 상한으로 답했다(관문이 42,768 중
    #    15,561 건 불일치로 잡았다). 정본을 한 곳에 두면 못 갈라진다.
    w("const mMaxDefault = %d\n" % max(M_VALS))
    w("const cPktDefault = %.10g\n" % policy.C_PKT_POLICY_DEFAULT)

    w("\n// 업링크 대역 Mbps. J 의 t_tx 항이 쓴다. 0 이면 대역 제한 없음.\n")
    w("//   🩸 2026-08-21 - 그전에는 policy.go 안에 `10e6` 이 리터럴로 박혀\n")
    w("//   있었다. 어디서도 측정된 적 없는 수인데 격자 720 점 중 312 점\n")
    w("//   (43.3%) 의 선택을 좌우했고, 정작 이 테스트베드는 netem 이 대역을\n")
    w("//   안 걸어 실측과 25 배 어긋났다. 이제 `-uplink-mbps` 로 받고,\n")
    w("//   기본값 정의는 padfec/policy.py 한 곳뿐이다.\n")
    w("const uplinkMbpsDefault = %.10g\n\n" % policy.UPLINK_MBPS_DEFAULT)

    w("// J 를 동점으로 볼 분해능(ms). 1 ns 로 두면 모형의 반올림 잡음이\n")
    w("// 정책을 정한다 - 실제로 그랬다(2026-08-21: 헤드라인 조건에서\n")
    w("// 0.0008 ms 차이로 1,325 B 를 더 사는 결정이 나왔다. 그 차이는\n")
    w("// 이 테스트베드의 측정 분해능 1 us 보다 작다).\n")
    w("// 정의는 padfec/policy.py 한 곳뿐이다.\n")
    w("const jTieMs = %.10g\n\n" % policy.J_TIE_MS)

    w("\n// 뒤따르는 패리티의 신용이 **송신 결정에 잡힐** 확률 q(d) 의 실측 표.\n")
    w("//   d = 패리티 바이트 / 업링크 대역 (ms). 마디 사이는 선형보간하고\n")
    w("//   마지막 마디 위는 0 이다. 이 표를 왜 함수꼴로 안 적는지, 어떻게\n")
    w("//   쟀는지는 padfec/policy.py 의 '경주' 절에 있다 - 정의는 거기 한 곳뿐이다.\n")
    w("//   실측 2026-08-26 probe_race2.py (cert 9000·k=2·RTT 50·손실 0%·gap 50).\n")
    w("var raceDelayMs = []float64{%s}\n"
      % ", ".join("%.17g" % v for v in policy.RACE_DELAY_MS))
    w("var raceWinQ = []float64{%s}\n\n"
      % ", ".join("%.17g" % v for v in policy.RACE_WIN_Q))

    w("var pfailK = []int{%s}\n" % ", ".join(str(v) for v in K_VALS))
    w("var pfailM = []int{%s}\n" % ", ".join(str(v) for v in M_VALS))
    w("var pfailP = []float64{%s}\n"
      % ", ".join("%g" % v for v in P_VALS))
    # 🩸 이름이 pfailL 이 아니라 **pfailU** 다. 축이 평균 버스트 L 이
    #    아니라 정규화 버스트 u = L·(1-p) 이기 때문이다(U_VALS 주석 참고).
    #    읽는 쪽(policy.go)은 반드시 u 로 바꿔서 조회해야 한다.
    w("// 정규화 버스트 축. u = L*(1-p). 꺾인 점(독립<->GE 경계)이\n")
    w("// 모든 p 에서 u=1 에 오도록 잡은 좌표다 - 근거는 padfec/table.py\n")
    w("// 의 U_VALS 주석. **L 을 그대로 넣으면 안 된다.**\n")
    w("var pfailU = []float64{%s}\n\n"
      % ", ".join("%g" % v for v in U_VALS))

    # pfailTable 은 더 이상 내보내지 않는다(2026-08-20 감사). Go 가 P_fail 을
    # 별도 표에서 읽으면 기대 왕복 수와 다른 분포에서 나온다 - 그게 결함 1
    # 이었다. flightOutcome 이 jointTable 하나에서 둘 다 뽑는다.
    # Python 쪽 pfail() 은 v1 호환과 자체검증용으로 남겨 둔다.
    w("// jointTable4[k인덱스][m인덱스][p인덱스][L인덱스] = 평탄화된 (k+1)x(m+1)x2\n")
    w("//   원소 [(a*(m+1)+b)*2 + r]\n")
    w("//     = 원본 a 개·패리티 b 개가 도착하고, 그중 **복구용 패리티**\n")
    w("//       (마지막으로 보낸 것, index m-1)의 도착 여부가 r 일 확률\n")
    w("//\n")
    w("// 🩸 2026-08-21 - 이름을 jointTable -> jointTable4 으로 바꿨다. 배치가\n")
    w("//   달라졌는데 이름이 같으면 옛 pfail_table.go 가 남아 있을 때 Go 가\n")
    w("//   **조용히 잘못 읽는다.** 이름을 바꾸면 컴파일이 깨져 드러난다.\n")
    w("//   왜 r 이 필요한가: 서버(qamp.go)는 마지막 패리티 하나로 소거 하나만\n")
    w("//   복구하고, 복구하면 그 패리티를 버리고 복구본(원본 크기)을 스택에\n")
    w("//   넘긴다. '몇 개 왔나' 만으로는 복구 여부도 신용 바이트도 정할 수 없다.\n")
    w("var jointTable4 = [][][][][]float64{\n")
    for k in K_VALS:
        w("\t{ // k=%d\n" % k)
        for m in M_VALS:
            w("\t\t{ // m=%d\n" % m)
            for pi, p in enumerate(P_VALS):
                w("\t\t\t{ // p=%g\n" % p)
                for li, u in enumerate(U_VALS):
                    # %.17g = float64 왕복 정밀도. 9 자리로 찍으면
                    # Go 가 읽은 값이 Python 값과 ~1e-9 어긋나서
                    # '글자 단위로 맞춘다'는 약속이 검증 불가가 된다.
                    # 파일이 커지는 대신 두 구현이 비트 단위로 같아진다.
                    mat = jtab[(k, m, pi, li)]
                    gg = policy.recovery_group(k, m)
                    flat = [mat[a_][b_][c_] for a_ in range(k + 1)
                            for b_ in range(m + 1) for c_ in range(gg + 1)]
                    w("\t\t\t\t{%s}, // u=%g (L=%.4g)\n"
                      % (", ".join("%.17g" % v for v in flat),
                         u, _L_of(p, u)))
                w("\t\t\t},\n")
            w("\t\t},\n")
        w("\t},\n")
    w("}\n\n")

    w("// RTT 표본이 있을 때의 첫 PTO 배율. RFC 9002 §5.3 + §6.2.1 에서\n")
    w("// **유도한** 값이지 맞춘 상수가 아니다 - 근거는 padfec/policy.py 의\n")
    w("// PTO_SAMPLED_RTT_MULT 주석에 있다.\n")
    w("const ptoSampledRttMult = %g\n\n" % policy.PTO_SAMPLED_RTT_MULT)

    w("// failFracTable[k][m][p][L] = {표본없는PTO, 표본있는PTO, 시간임계} 의 **비율**\n")
    w("//\n")
    w("// 실패 한 번의 대가는 **마지막 원본이 도착했는가**로 갈린다.\n")
    w("//   마지막 원본 도착 -> 그 ACK 이 시간 임계를 무장 -> 9/8·RTT\n")
    w("//   마지막 원본 유실, 앞의 것은 도착 -> 구멍을 못 봄 -> PTO(표본 있음) = 3·RTT\n")
    w("//   아무것도 없음 -> ACK 도 표본도 없음 -> PTO(표본 없음) = 상수\n")
    w("// 판별자가 jointTable4 의 축(a,b,r)에 없어서 표를 하나 더 싣는다.\n")
    w("// **확률이 아니라 비율**인 이유는 padfec/table.py 의 fail_frac 주석 참고.\n")
    w("var failFracTable = [][][][][]float64{\n")
    for k in K_VALS:
        w("\t{ // k=%d\n" % k)
        for m in M_VALS:
            w("\t\t{ // m=%d\n" % m)
            for pi, p in enumerate(P_VALS):
                w("\t\t\t{ // p=%g\n" % p)
                for li, u in enumerate(U_VALS):
                    fr = ftab[(k, m, pi, li)]
                    w("\t\t\t\t{%s}, // u=%g (L=%.4g)\n"
                      % (", ".join("%.17g" % v for v in fr),
                         u, _L_of(p, u)))
                w("\t\t\t},\n")
            w("\t\t},\n")
        w("\t},\n")
    w("}\n")


def main():
    if len(sys.argv) < 2:
        sys.stderr.write('사용: python -m padfec.table <출력경로>' + chr(10))
        return 2
    tab, jtab, ftab = build()
    import io as _io
    with _io.open(sys.argv[1], 'w', encoding='utf-8', newline=chr(10)) as f:
        emit_go(tab, jtab, ftab, f)
    sys.stderr.write('wrote %s (pfail %d + joint %d + failfrac %d)'
                     % (sys.argv[1], len(tab), len(jtab), len(ftab)) + chr(10))
    return 0


if __name__ == "__main__":
    sys.exit(main())
