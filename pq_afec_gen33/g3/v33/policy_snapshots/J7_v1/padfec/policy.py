# -*- coding: utf-8 -*-
"""PAD-FEC 결정 규칙 - 무엇을 보낼지 고른다.

1차 알고리즘(afec/controller.py)은 비용 최소화 한 식으로 잉여율 r 을 골랐다.
그 골격은 살아남았지만 **비용의 부호가 바뀌었다.**

    1차:  추가 바이트 = 대역폭 비용 (항상 양)
    2차:  추가 바이트 = 대역폭 비용 - 증폭 신용

RFC 9000 8.1 때문에 클라이언트가 Δ 바이트를 더 보내면 서버 예산이 3Δ
늘고, 서버 비행이 그 경계에 걸려 있으면 왕복 한 번이 통째로 사라진다.
그래서 어떤 구간에서는 **더 보내는 쪽이 더 빠르다.** 1차 모델에는 이런
항이 없었다.

기대 핸드셰이크 완료 시간

    E[HCT] = n_rtt(cert, 클라바이트) x RTT + P(복구 실패) x PTO비용

    n_rtt        증폭 예산이 서버 비행을 한 번에 못 담으면 2
    P(복구 실패)  k+m 개 중 m 개를 넘게 잃을 확률 (Gilbert-Elliott)
    PTO비용       RFC 9002 - RTT 표본이 없으면 첫 PTO 는 약 999 ms

주의: 보호 대상은 **클라이언트 -> 서버 방향의 첫 비행뿐**이다. 서버 비행에는
패딩이 없고(인증서로 꽉 찬다) 서버에게는 쓸 수 있는 무료 바이트도 없다.
반대 방향 손실은 이 설계로 줄지 않으며, 모형에도 넣지 않았다.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from afec.channel import GilbertElliott  # noqa: E402

from . import amplif, capacity, quantum  # noqa: E402

# 🩸 2026-08-25 - auto 가 고를 수 있는 최대 패리티 수.
#
#    **실측 1**: 무손실에서 m 별 1-RTT 한계 cert 를 이분탐색으로 직접
#    쟀다(고정팔 `-m`, 패딩 없음, n=20/점, 해상도 100 B). 같은 조건의
#    모형값과 나란히 놓으면:
#            모형      실측      차이
#        m=1 10,906   10,855    +51 B
#        m=2 14,609   14,601    **+8 B**
#        m=3 18,312   >=16,125 (천장에 막힘)
#    -> 모형은 이 축에서 정확하다(해상도 안). 교차 확인: m=1 의 실측
#       한계 10,855 는 p2 가 따로 잰 FEC 임계 [10,901 , 10,958] 과
#       100 B 해상도 안에서 일치한다.
#
#    **실측 2 (천장)**: 이 스택의 클라이언트는 CRYPTO 스트림을
#    16,384 B 로 막는다(CRYPTO_BUFFER_EXCEEDED). cert 16,125~16,187
#    위로는 **어떤 m 으로도 악수가 안 된다**.
#
#    **근거**: 정책이 *실제로 고르는 것*으로 보면
#        cert 15,860 까지  m_max=2 는 combo(패딩+m=2) 로 1-RTT 유지
#        cert 15,861 부터  m_max=2 는 **아예 포기**(none, 2-RTT)
#                          m_max=3 은 parity m=3 으로 1-RTT
#    -> 이득 구간 cert 15,861~16,125 (폭 265 B). 실측으로도 확인:
#       cert 16,000 에서 m=2 106.3 ms / m=3 53.7 ms (각 25/25 연결,
#       무손실이라 분산 없음 - 잡음이 아니다).
#
#    ⚠ 구간이 좁은 것은 **측정 환경의 천장 때문**이다. 모형상
#      m_max=3 은 cert 20,810 까지 1-RTT 를 유지하므로 CRYPTO 버퍼가
#      더 큰 스택에서는 이득 구간이 약 4,950 B 로 넓어진다.
#
#    m=4 로 올리지 않은 이유: m=3 이 이미 이 스택의 천장까지 덮는다.
#    손실 자리에서 m=4 가 나을 가능성은 남아 있지만 그건 아직
#    판정 불능이다(p18: 필요 표본 팔당 3,014~11,343, 지금 1,000).
#
#    ⚠ 이 수를 바꾸면 **확률표(padfec/table.py M_VALS)도 같이**
#      늘려야 한다. policy.go 는 표에 없는 (k,m) 을 받으면 죽는다.
M_MAX_DEFAULT = 3

# quic-go 가 실제로 내보낼 수 있는 InitialPacketSize 의 상한.
# 2026-08-20 실측: -ips 1707 을 줘도 클라이언트는 1452 B 로 깎아 보냈다.
# 그래서 δ 지렛대로 갈 수 있는 칸이 막힌다 — x25519 는 칸 3·4, ML-KEM 은 6·7 까지.
# 이 상수를 넘는 후보는 **보낼 수 없으므로** 기본적으로 후보에서 뺀다.
QUICGO_MAX_IPS = 1452

# ---------------------------------------------------------------------------
# 서버 첫 비행의 **유효** 모형  S_eff(n) = s0_base + n*c   (명세 §2.5)
#
# ⚠️ 이 둘은 **물리적 바이트 수가 아니다.** 임계(1-RTT/2-RTT 가 뒤집히는 인증서
#    크기)를 재현하도록 맞춘 **유효 파라미터**다. 그 사실을 여기 못박는 이유는
#    2026-08-21 에 두 측정이 100 B 어긋나 보였기 때문이다.
#
#      p13 직접 계수 : cert=3000, x25519 에서 서버 첫 비행 = 3,604 B (s0 = 604)
#      임계 역산     : 같은 칸(n=3)에서 s0 = 3,840 - 3,340 = 500
#
#    ✅ 2026-08-21 직접 실험으로 원인을 규명했다(서버 송신 타임라인의 패킷 크기).
#
#      cert=3250  첫 비행 [1280, 1280, 1209,  95] = 3,864 B  -> 1-RTT
#      cert=3300  첫 비행 [1280, 1280, 1257,  95] = 3,912 B  -> 1-RTT
#      cert=3340  첫 비행 [1280, 1280, 1280]      = 3,840 B  -> **2-RTT**
#
#    quic-go 는 패킷을 만들기 **전에** `bytesSent >= 3*bytesReceived` 를 본다.
#    그래서 마지막 패킷이 작으면 한도를 **넘겨서** 보낸다 - 실측 최대 +72 B.
#    정확한 규칙은 `S <= allowed` 가 아니라
#
#        1-RTT  ⟺  S - (마지막 패킷 크기) < 3B
#
#    이고, 마지막 패킷 크기는 cert 에 따라 95~1,280 B 로 변한다. 그 여유분을
#    유효 모형이 s0 를 ~100 B 작게 잡는 것으로 흡수한다. 즉 두 측정은 서로
#    모순이 아니라 **다른 양**이었다. 물리 s0 를 여기 넣으면 임계를 100 B
#    낮게 예측한다(= 정책이 필요 없는 바이트를 산다).
#
# 값의 출처 — 임계 앵커 6 개(그룹 x 팔)에 공통 c · 그룹별 s0_base 최소제곱.
#   B_eff 는 p13 이 직접 잰 값을 쓴다(results/p13_beff.json).
#
#   🩸 그전에는 **앵커 하나**(x25519 n=3, ML-KEM n=6)로 s0_base 를 정했다.
#      그러면 그 점은 정확히 맞지만 다른 칸에서 어긋난다 - p4 의 x25519 on1
#      예측이 8,300.0 으로 실측 밴드 8,239~8,296 을 **4 B 벗어났다**(7/8).
#      6 앵커 최소제곱으로 바꾸면 **6/6 전부 밴드 안**에 든다.
#
#   ✅ 교차 확인: 이렇게 얻은 c = 41.98 은 p13 이 **서버 패킷을 직접 세어**
#      얻은 c = 40.55(x25519) / 41.39(ML-KEM) 와 1.5 B/패킷 안에서 맞는다.
#      전혀 다른 두 관측(임계 이분탐색 vs 패킷 계수)이 같은 기울기를 준다 -
#      아핀 형태 S(n) = s0_base + n*c 자체가 옳다는 근거다.
C_PKT_POLICY_DEFAULT = 41.983

# 위 최소제곱의 그룹별 절편.
#   x25519  : 382.45   (옛 단일앵커 값 380.0)
#   ML-KEM  : 1472.00  (옛 단일앵커 값 1494.5)
S0_BASE_X25519 = 382.45
S0_BASE_MLKEM = 1472.00

# 후보로 볼 칸 수. 명세 §3 의 J 상한. 2 칸이면 δ 로 최대 2 칸까지 올린다.
MAX_STEPS_DEFAULT = 2

# RFC 9002 6.2.1 - RTT 표본이 없을 때의 초기 PTO.
#   kInitialRtt 333 ms, PTO = smoothed_rtt + 4*rttvar + max_ack_delay
#                          = 333 + 4*166.5 = 999 ms
PTO_NO_SAMPLE_MS = 999.0

# Go 가 버스트를 관측할 수 없을 때 쓰는 값. **한 곳에서만 정의한다** —
# table.py 가 이 값을 생성 파일에 심고 policy.go 는 거기서 읽는다.
#
# 🩸 2026-08-20 감사 결함 3: 예전에는 policy.go 가 `pfailLookup(..., 1.0)` 으로
#    **버스트를 호출부에 리터럴로 박아** 뒀고 Python 은 실제 버스트를 썼다.
#    같은 입력에 두 구현이 다른 m 을 골랐다(90 조건 중 17 건 불일치).
#    Go 가 버스트를 못 재는 것은 사실이지만, 그 사실이 **호출부에 숨어 있으면
#    안 된다.** 이름을 주고 인자로 흘린다 — 추정이 생기면 양쪽이 같이 받는다.
DEFAULT_ASSUMED_BURST = 1.0

# ---------------------------------------------------------------------------
# 복구 실패 비용 — 2026-08-20 결정적 소거로 직접 측정한 값.
#
# 🩸 그전 기본값은 `t_recover_ms = rtt_ms` 였다. **k=1 에서 4~20 배 작았다.**
#
# 실측(`experiments/_probe_trecover_rtt.py`, `results/probe_trecover_rtt.json`).
# `-drop-initial 0` 으로 매 판마다 첫 비행을 버리고 기준선과의 p50 차를 쟀다.
#
#     RTT     k=1 (x25519)          k=2 (X25519MLKEM768)
#     10 ms   200.90 ms (20.09x)     12.62 ms (1.26x)
#     50 ms   200.96 ms ( 4.02x)     57.77 ms (1.16x)
#    100 ms   200.73 ms ( 2.01x)    113.88 ms (1.14x)
#     판정    고정 상수(폭 0.23 ms)   RTT 비례(배수 폭 0.10)
#
# 가르는 것은 k 가 아니라 **실패한 순간 서버가 하나라도 받았는가**다.
#   받은 게 0 개  -> 서버가 ACK 를 못 준다 -> 클라가 PTO 타이머를 문다.
#                   그 타이머는 RTT 표본이 없을 때의 값이라 **경로와 무관한 상수**다.
#   1 개 이상     -> 서버가 ACK 를 준다 -> 클라가 패킷번호 구멍을 보고 즉시
#                   재전송한다 -> 대가는 왕복 하나 + 처리 오버헤드.
#
# k=1·m=0 은 실패가 곧 전멸이라 항상 PTO 가지이고, k>=2 는 대개 ACK 가지다.
# 그래서 겉보기에 "k 에 따라 다르다"로 보였다. 결합분포가 두 가지를 이미
# 구분해 주므로 **k 로 분기하지 않고 도착 개수로 나눈다.**
#
# v2 명세 §3 의 "서버가 ACK 를 주므로 대가는 왕복 하나다" 는 **ACK 가지에서만**
# 참이다. 코드 주석은 PTO 경로를 알고 있었는데(아래 cost_of_v2 참고) 기본값이
# 말없이 틀린 가지를 탔다.
#
# ⚠️ 이 세 수는 **quic-go v0.61.0 의 타이머**를 잰 것이다. 다른 스택에서는
#    다시 재야 한다. 상수를 쓰는 게 아니라 상수의 출처를 밝히는 게 요점이다.
# ⚠️ **알려진 한계 — 버스트에서 이 상수는 절반이다** (2026-08-25 실측)
#
# p3 원자료에서 t > 3·RTT 인 표본(=PTO 가지)만 골라 그 값을 직접 쟀다:
#
#     버스트   표본    PTO 한 번의 실측 값   모형(RTT+T_pto)   비
#       1      248        239.7 ms           250.9 ms      0.96 배
#       3      224        499.5 ms           250.9 ms      1.99 배
#
# 기전은 지수 백오프 마디 분포가 그대로 보여 준다
# (누적 마디 RTT + T·(2^n - 1) = 251 / 653 / 1456 / 3063 ms):
#
#     버스트 1:  1 차 97%   2 차  3%   3 차  0%   4 차 0%
#     버스트 3:  1 차 62%   2 차 24%   3 차 11%   4 차 3%
#
# 즉 버스트에서는 **재전송도 잃어서 PTO 가 연쇄**한다.
#
# **왜 안 고쳤나.** 두 점에서 배율을 뽑아 넣는 것은 곡선 적합이지 모형이
# 아니다. 대신 연쇄 확률 q = P(다음 재전송도 실패) 를 이미 가진 GE
# 모형으로 유도할 수 있는지 봤다(재전송이 원본만인 경우 R1, 패리티까지
# 보내는 경우 R2):
#
#     버스트   실측 q    R1 예측   R2 예측
#       1      0.038     0.065     0.036   <- R2 가 맞는다
#       3      0.397     0.052     0.042   <- 둘 다 8 배 낮다
#
# 원인은 이름 붙일 수 있다: **우리 버스트 모형에는 시간 축이 없다.**
# GilbertElliott.for_prior(p, burst) 는 연속된 *심볼* 의 묶음을 말하지
# 지속 *시간* 을 말하지 않는다. PTO 재전송은 200 ms 뒤에 나가는데 실측은
# 그때 채널이 아직 같은 나쁜 상태라고 말한다 - 심볼 단위 모형으로는
# 원리적으로 못 낸다. 시간 축이 있는 채널 모형으로 바꾸는 것은 별개의
# 큰 작업이다.
#
# **영향 범위 (재확인함).** PTO 값을 실측 배율로 바꿔 격자 528 점을 다시
# 결정해 봤더니 **0 점에서 선택이 바뀐다.** 즉 이것은 J 의 *크기* 오차이지
# *선택* 오차가 아니다. 보고되는 J 는 버스트 3 의 실패 가지에서 2 배
# 낮지만, 그 때문에 정책이 다른 것을 고르는 자리는 없다.
# (바른 C=1448 과 m_max=3 을 반영해 다시 잰 수다 - 예전 확인은 틀린 C
#  위에 있었다. 28 절 참고.)
T_PTO_NO_ACK_MS = 200.86        # 실측 200.90 / 200.96 / 200.73 의 평균
T_ACK_RETX_SLOPE = 1.1250       # 최소제곱 적합, 잔차 |0.10| ms 이내
T_ACK_RETX_BASE_MS = 1.424


# RFC 9002 에서 **유도한** 값. 맞춘 상수가 아니다.
#
#   §5.3  첫 RTT 표본에서   smoothed_rtt = 표본,  rttvar = 표본/2
#   §6.2.1 PTO = smoothed_rtt + max(4·rttvar, kGranularity) + max_ack_delay
#          Initial/Handshake 패킷 번호 공간에서는 max_ack_delay = 0
#   => PTO = rtt + 4·(rtt/2) = **3·rtt**
#
# 마지막 원본만 잃은 가지에서 클라이언트는 (앞의 원본이 ACK 됐으므로)
# RTT 표본을 갖고 있다. 그래서 표본 없는 PTO(T_PTO_NO_ACK_MS)가 아니라
# 이 값을 문다. last_original_pmf 주석에 근거와 실측이 있다.
#
# ⚠️ **한 점에서만 대조했다.** p7 V3(RTT 50, k=2): 실측 증분 154.5 ms vs
#    이 식 150.0 ms — +4.5 ms 어긋난다. 다른 두 상수의 잔차(V2 +0.5, V9
#    −0.3)보다 크다. **맞추지 않는다** — 한 점에서 배율을 뽑는 것은 곡선
#    적합이지 모형이 아니고, 이 저장소가 T_PTO 버스트 배율에서 같은 이유로
#    거부한 적이 있다(T_PTO_NO_ACK_MS 주석). 대신 재는 쪽을 만든다:
#    `_probe_trecover.py` 에 `-drop-initial k-1` 팔을 여러 RTT 에서 돌리면
#    이 식이 RTT 에 비례하는지가 직접 나온다. 그전까지는 **RFC 유도값**이다.
PTO_SAMPLED_RTT_MULT = 3.0


def pto_with_rtt_sample_ms(rtt_ms):
    """RTT 표본이 있을 때의 첫 PTO (ms). 위 주석의 유도."""
    return PTO_SAMPLED_RTT_MULT * float(rtt_ms)


def default_t_recover(rtt_ms, arrived_any):
    """복구 실패 한 번의 대가. arrived_any = 서버가 하나라도 받았는가."""
    if arrived_any:
        return T_ACK_RETX_SLOPE * float(rtt_ms) + T_ACK_RETX_BASE_MS
    return T_PTO_NO_ACK_MS


def erasure_probs(n_symbols, p, burst):
    """n 개 심볼 중 e 개가 소거될 확률 벡터."""
    ge = GilbertElliott.for_prior(p, burst)
    return ge.erasure_pmf(n_symbols)


def p_unrecoverable(k, m, p, burst):
    """k+m 개 중 m 개를 넘게 잃어 복구가 안 될 확률."""
    if p <= 0.0:
        return 0.0
    pmf = erasure_probs(k + m, p, burst)
    return float(sum(pmf[e] for e in range(m + 1, len(pmf))))


# ---------------------------------------------------------------------------
# 업링크 대역 — J 의 t_tx 항.
#
# 🩸 2026-08-21 수리. 그전에는 이 수(10.0)가 **함수 기본 인자에 리터럴로**
#    여덟 군데 박혀 있었고, Go(policy.go)에도 `10e6` 이 따로 박혀 있었다.
#    세 가지가 잘못돼 있었다.
#
#    (1) **출처가 없다.** 명세 어디에도 없고 측정한 적도 없다. 이 저장소의
#        규칙은 "상수를 쓰는 게 아니라 상수의 출처를 밝히는 게 요점"인데
#        (T_PTO_NO_ACK_MS 주석) 이 수만 예외였다.
#    (2) **측정 환경에 그 비용이 존재하지 않는다.** experiments/padbed.py 의
#        netem 은 delay 와 loss 만 걸고 rate 를 안 건다. 실측(p14, 무손실):
#            pad(1,281 B) 51.668 ms  vs  parity(2,605 B) 51.711 ms
#            -> 1,324 B 추가에 0.043 ms.  모형은 같은 자리에 1.06 ms 를 청구한다(25 배).
#    (3) 그런데 이 항은 "이득이 같으면 큰 m 을 고르는 편향"을 막는 **유일한
#        힘**이라, 틀리면 결정이 통째로 흔들린다. 격자 720 점 중 312 점(43.3%)
#        에서 선택이 뒤집힌다. p11·p15 가 실패하던 두 조건이 정확히 이것이었다:
#            임계아래/손실5%  모형 m=1 (J 51.62 vs 52.17) / 실측 최선 m=2 (52.49 vs 53.96)
#            임계사이/손실2%  모형 m=1 (J 52.120 vs 52.141) / 실측 최선 m=2 (51.11 vs 52.88)
#        두 자리 다 tx 항(1.06 ms)이 딱 뒤집을 만큼이었고, 항을 실측값으로
#        바꾸면 모형의 선택이 실측 최선과 일치한다.
#
# 그래서 **숨은 상수를 없애고 인자로 만든다.** 호출부가 자기가 도는 링크의
# 값을 준다(Go 는 `-uplink-mbps`, padbed 가 넘긴다).
#
#   UPLINK_UNSHAPED (=0.0)  대역 제한 없음 -> t_tx = 0.
#                           **우리 테스트베드의 실제 조건이다.**
#   UPLINK_MOBILE_MBPS      10 Mbps. 전형적인 모바일 업링크로 흔히 인용되는
#                           값이지만 이 연구가 측정한 값은 아니다. 대역이
#                           있는 경로의 거동을 보고 싶을 때 **명시적으로** 준다.
#
# 기본값은 모바일 시나리오 그대로 둔다 - 모형만 쓰는 호출자의 답을 말없이
# 바꾸지 않기 위해서다. 측정과 맞물리는 자리(padbed -> qamp)는 실제 링크 값을
# 넘긴다. 재는 쪽은 p16 이 만든다(experiments/p16_uplink.py).
UPLINK_UNSHAPED = 0.0
UPLINK_MOBILE_MBPS = 10.0
# 🩸 2026-08-25 - p17(적응의 값어치)용. **측정한 현장 값이 아니다.**
#    출처: 모형이 "두 손실 구간의 최적 m 이 갈리는" 대역 구간이
#    1~3 Mbps 라고 말한다(0.5 이하도, 4 이상도 안 갈린다). 그 가운데
#    값이다. 적응에 값어치가 생기려면 패리티가 공짜가 아니어야 하고,
#    이 수는 그 조건을 만드는 대역이다 - 현장 대표값이 아니라
#    **실험 조건**이다. p17 의 검사 9(무제한에서는 안 갈린다)가
#    이 사실을 음성 대조로 드러낸다.
UPLINK_CONSTRAINED_MBPS = 2.0
UPLINK_MBPS_DEFAULT = UPLINK_MOBILE_MBPS

# J 를 동점으로 볼 분해능 (ms).
#
# 🩸 2026-08-21. 그전에는 `round(j_ms, 6)` 즉 **1 나노초**였다. 그 정도 차이는
#    이 테스트베드에서 측정할 수 없는데도 순위를 갈랐다. 임계경로 t_tx 수리
#    (critical_path_bytes)로 m=1 의 대역 비용이 0 이 되자 곧바로 드러났다:
#
#        헤드라인 조건(p=0, 임계 바로 위, 10 Mbps)
#          parity m=1  J = 50.0000 ms   (패리티가 원본 뒤라 임계경로 밖)
#          pad    δ=1  J = 50.0008 ms   (1 바이트가 임계경로에 든다)
#
#    0.0008 ms 를 아끼려고 **1,325 바이트를 더 보내는** 결정이 된다. 시간으로는
#    맞지만 자원으로는 명백히 틀렸고, 무엇보다 그 0.0008 ms 는 **잴 수 없다**
#    (테스트베드의 HCT 분해능은 1 us = 0.001 ms, 팔 평균의 표준오차는 ~0.03 ms,
#     p11/p15 후회 지표의 잡음은 ~1 ms).
#
#    그래서 **잴 수 없는 차이는 동점으로 본다.** 동점이면 명세 §3 의 다음
#    기준이 정한다 - 추가 바이트가 적은 쪽, 그 다음 패리티 우선.
#    이건 기준 완화가 아니라 **분해능을 측정 가능한 값으로 되돌린 것**이다.
#    (1 ns 로 두면 모형의 반올림 잡음이 정책을 정하게 된다.)
#
#    0.01 ms 의 근거: 측정 분해능(0.001 ms)의 10 배이면서, 팔 평균 표준오차
#    (~0.03 ms)의 1/3, 이 연구가 주장하는 최소 효과(1 왕복 = 10~250 ms)의
#    1/1000 이하. Go 의 evalCands 정렬도 같은 값을 써야 한다(격자 대조가 잡는다).
J_TIE_MS = 0.01


def tx_cost_ms(extra_bytes, uplink_mbps):
    """추가 바이트를 실제로 밀어내는 데 드는 시간.

    작지만 0 이 아니다. 이 항이 없으면 정책이 이득이 같을 때도 무조건 큰
    m 을 고른다 - 1차 때 겪은 것과 같은 종류의 편향이다.

    uplink_mbps <= 0 이면 **대역 제한이 없다**는 뜻이라 0 이다(위 상수 주석).
    Go 의 evalCands 와 글자 단위로 같은 식이어야 한다.
    """
    if uplink_mbps <= 0:
        return 0.0
    return (extra_bytes * 8.0) / (uplink_mbps * 1e6) * 1000.0


def expected_hct_ms(cert_bytes, k, m, W, rtt_ms, p, burst, s0,
                    pto_ms=PTO_NO_SAMPLE_MS, uplink_mbps=UPLINK_MBPS_DEFAULT):
    client_bytes = (k + m) * W
    n = amplif.rtt_count(cert_bytes, client_bytes, s0)
    pf = p_unrecoverable(k, m, p, burst)
    tx = tx_cost_ms(m * W, uplink_mbps)
    return {
        "client_bytes": client_bytes,
        "n_rtt": n,
        "p_unrecoverable": pf,
        "tx_ms": tx,
        "hct_ms": n * rtt_ms + pf * pto_ms + tx,
        "base_ms": n * rtt_ms,
        "stall_ms": pf * pto_ms,
    }


def decide(C, cert_bytes, rtt_ms, p, burst, s0,
           W=capacity.MIN_INITIAL_DATAGRAM, m_max=M_MAX_DEFAULT,
           pto_ms=PTO_NO_SAMPLE_MS, uplink_mbps=UPLINK_MBPS_DEFAULT):
    """이 조건에서 패리티 데이터그램을 몇 개 붙일지 고른다.

    돌려주는 것: 선택과 그 근거, 그리고 후보 전부의 계산 결과.
    """
    k = capacity.natural_k(C, W)
    cand = []
    for m in range(0, m_max + 1):
        if m == 0:
            e = expected_hct_ms(cert_bytes, k, 0, W, rtt_ms, p, burst, s0,
                                pto_ms, uplink_mbps)
            e["p_unrecoverable"] = (
                0.0 if p <= 0 else
                float(1.0 - erasure_probs(k, p, burst)[0]))
            e["hct_ms"] = e["base_ms"] + e["p_unrecoverable"] * pto_ms
            e["stall_ms"] = e["p_unrecoverable"] * pto_ms
        else:
            if k < 1:
                continue
            e = expected_hct_ms(cert_bytes, k, m, W, rtt_ms, p, burst, s0,
                                pto_ms, uplink_mbps)
        e["m"] = m
        e["k"] = k
        e["extra_bytes"] = m * W
        e["mode"] = "off" if m == 0 else ("parity%d" % m)
        cand.append(e)

    best = min(cand, key=lambda e: (e["hct_ms"], e["extra_bytes"]))
    base = cand[0]
    reason = []
    if best["m"] > 0:
        if best["n_rtt"] < base["n_rtt"]:
            reason.append("증폭 신용으로 왕복 %d회 절약"
                          % (base["n_rtt"] - best["n_rtt"]))
        if best["p_unrecoverable"] < base["p_unrecoverable"]:
            reason.append("손실 복구로 정지 확률 %.3f -> %.3f"
                          % (base["p_unrecoverable"],
                             best["p_unrecoverable"]))
    else:
        reason.append("추가 바이트가 이득을 못 낸다")

    inplace = capacity.describe(C, W)
    return {
        "choice": best,
        "candidates": cand,
        "reason": "; ".join(reason),
        "gain_ms": base["hct_ms"] - best["hct_ms"],
        "inplace": inplace,
        "note_inplace": (
            "제자리(무비용) 배치 가능" if inplace["inplace_feasible"] else
            "제자리 불가 - 용량 부등식 C <= (k-1)(W-h-f) 위반, "
            "패리티는 데이터그램을 더 써야 한다"),
    }


# ---------------------------------------------------------------------------
# v2 — 두 지렛대(δ·m) 결합 결정.  명세 `docs/PADFEC v2 명세.md` §3.
# ---------------------------------------------------------------------------
#
# v1(위 decide)은 결정 변수가 m 하나였다. v2 는 δ 를 더한다.
#
#     δ  데이터그램을 키운다 (W -> W+δ)   신용 +3kδ,  복구 없음
#     m  패리티 데이터그램 m 개 추가       신용 +3mW,  1-소거 복구
#
# 신용은 **바이트 수에만** 의존하므로(실측: 내용이 문자 그대로 같은 복제
# 데이터그램도 임계를 옮겼다) 두 지렛대의 신용은 같은 식으로 계산된다.
# 갈리는 것은 복구뿐이다 — 보조정리 1(지배): 같은 추가 바이트에서 Δ >= W 이면
# 패리티가 패딩을 엄격히 지배한다. Δ < W 이면 패리티 데이터그램을 만들 수 없어
# δ 가 유일한 수단이고, 그때 δ 는 매우 싸다(경계에서는 1 바이트).
#
# ⚠️ T_recover 를 999 ms 에서 RTT 로 바꿨다.
#     v1 은 원본 하나를 잃으면 PTO(RFC 9002 초기값 999 ms)를 문다고 봤다.
#     **측정으로 틀렸음이 밝혀졌다** — 서버가 ACK 를 주므로 패킷 번호 구멍으로
#     즉시 재전송되고, 대가는 **왕복 하나**다. 그래서 기본값을 rtt_ms 로 둔다.
#     PTO 를 무는 경로(서버가 아무것도 못 받아 ACK 자체가 없는 경우)를 재고 싶으면
#     t_recover_ms 를 명시적으로 넘긴다.


def p_fail_of(cand, p, burst):
    """이 후보에서 '복구 실패' 확률. **flight_outcome 과 같은 분포에서 나온다.**

    m=0 (아무것도 안 함 / pad) 은 복구 수단이 없으므로 하나라도 잃으면 실패다.
    패딩은 복구를 주지 않는다 — 키운 데이터그램 안의 여분 바이트는 그
    데이터그램이 통째로 사라질 때 같이 사라진다(명세 §4, 용량 정리).

    🩸 예전에는 이 함수가 erasure_pmf 를, expected_n_rtt 가 이항분포를 써서
       한 비용식 안에 손실 모형이 둘이었다. 지금은 둘 다 joint_arrival_pmf 에서
       나온다. 자체시험 3 이 이 값이 MDS 하한(p_unrecoverable) 이상이고 m=1 에서만
       일치함을, 21b 가 expected_rounds 의 첫 라운드 실패 질량과 같음을 확인한다.
       m>=2 에서는 뒤따르는 패리티만 복구하므로(recovery_group) p_unrecoverable
       과 **일부러 다르다** (2026-09-07 정정 - 옛 문장은 「자체시험 4 가 일치를
       확인한다」였는데 4 는 버스트 반응 검사다).
    """
    if p <= 0.0:
        return 0.0
    k, m = cand["k"], cand["m"]
    # 🩸 2026-08-21 - MDS 규칙 `(k-a) > b` 가 아니라 **구현의 규칙**을 쓴다.
    #    서버는 마지막 패리티 하나로 소거 하나만 복구한다(recovers 주석).
    g = recovery_group(k, m)
    pm = joint_arrival_pmf3c(k, m, p, burst)
    return float(sum(pm[a_][b_][c_]
                     for a_ in range(k + 1) for b_ in range(m + 1)
                     for c_ in range(g + 1)
                     if (k - a_) > 0 and not recovers(k, a_, c_)))


def cost_of(cand, rtt_ms, p, burst, t_recover_ms=None, uplink_mbps=UPLINK_MBPS_DEFAULT):
    """명세 §3 의 J (결정론 n_rtt 판, 보고용). 낮을수록 좋다.

    ⚠️ 정책은 이걸 안 쓴다 — decide_v2 는 cost_of_v2 를 쓴다. 여기 기본값
    `t_recover_ms = rtt_ms` 는 2026-08-20 실측으로 **PTO 가지에서 4~20 배
    작다**는 게 밝혀졌다(T_PTO_NO_ACK_MS 주석). 호환을 위해 남겨 두되
    새 코드는 default_t_recover() 를 쓴다.
    """
    if t_recover_ms is None:
        t_recover_ms = rtt_ms
    pf = p_fail_of(cand, p, burst)
    added = max(0, cand["added_bytes"])
    tx = tx_cost_ms(added, uplink_mbps)
    return {
        "j_ms": cand["n_rtt"] * rtt_ms + pf * t_recover_ms + tx,
        "base_ms": cand["n_rtt"] * rtt_ms,
        "stall_ms": pf * t_recover_ms,
        "tx_ms": tx,
        "p_fail": pf,
    }


def _tie_key(e):
    """동점 구간 안에서의 순서. 명세 §3: 추가 바이트 -> 패리티 우선 -> ...

    J 는 여기 안 들어간다. **동점으로 본 것들끼리** 고르는 자리이기 때문이다.
    """
    return (e["added_bytes_real"],
            0 if e["cand"]["m"] > 0 else 1,          # 같은 바이트면 패리티 우선
            1 if e["cand"]["late_parity_risk"] else 0,
            1 if e["cand"]["over_mtu"] else 0,
            e["cand"]["mode"])


def _pick_best(scored):
    """2 단 argmin. 명세 §3 의 순서를 **분해능을 인정하며** 적용한다.

    1) 정확한 J 로 최소를 찾는다.
    2) 그 최소에서 J_TIE_MS 이내인 후보들만 모아 동점으로 보고,
       그 안에서 추가 바이트가 적은 쪽을 고른다.

    🩸 2026-08-21. 처음에는 J 를 J_TIE_MS 로 **양자화(버킷)** 해서 정렬 키의
       첫 성분으로 썼다. **그게 더 나빴다.** 버킷 경계에서는 아주 작은 차이가
       칸을 가르므로, Go(표+보간)와 Python(정확 계산)의 미세한 J 차이가
       **순위 뒤집힘으로 증폭**된다 - 격자 대조에서 불일치 117 건으로 즉시
       드러났다. 양자화는 "가까우면 같다"를 표현하는 올바른 방법이 아니다
       (동치관계가 아니라 추이성이 깨진다).

       2 단 argmin 은 그 문제가 없다. 갈릴 수 있는 자리는 후보가 정확히
       `j_min + J_TIE_MS` 선에 걸터앉은 경우뿐이고, 그때의 대가는 정의상
       J_TIE_MS 이하다(관문의 보간 한도 0.1 ms 안).
    """
    exact = sorted(scored, key=lambda e: (e["j_ms"],) + _tie_key(e))
    j_min = exact[0]["j_ms"]
    tied = [e for e in exact if e["j_ms"] <= j_min + J_TIE_MS]
    tied.sort(key=_tie_key)
    rest = [e for e in exact if e["j_ms"] > j_min + J_TIE_MS]
    return tied + rest


def _rank_key(e):
    """동점 처리. 명세 §3: J -> 추가 바이트 -> 같은 바이트면 패리티 우선.

    🩸 2026-08-20 감사 결함 4: 예전에는 `e["cand"]["added_bytes"]` 를 봤다.
       그건 패리티를 W 로 센 **근사값**이고, 점수 j_ms 는 실크기(W+32+6k)로
       계산됐다. 동점일 때 실제로 더 큰 후보를 "더 작다"고 보고 골랐다
       (m=1 에서 38 B, m=2 에서 76 B 차이). 이제 실제 바이트를 본다.

    뒤에 둘을 더 붙였다.
      - late_parity_risk 가 있는 후보를 뒤로 (명세 §2.6 가설: k=1·m=1 배치는
        패리티가 서버 결정 뒤에 도착해 신용을 못 살 수 있다. p13 전까지는
        **같은 값이면 피한다**는 소극적 처리만 한다 — 신용을 임의로 깎지 않는다.)
      - over_mtu 후보를 뒤로.
    """
    # 🩸 2026-08-21 - 이 키는 이제 **보고용 정렬**에만 쓴다. 실제 선택은
    #    _pick_best(2 단 argmin)가 한다. 근거는 그 함수 주석.
    return (round(e["j_ms"], 6),
            e["added_bytes_real"],
            0 if e["cand"]["m"] > 0 else 1,          # 같은 바이트면 패리티 우선
            1 if e["cand"]["late_parity_risk"] else 0,
            1 if e["cand"]["over_mtu"] else 0,
            e["cand"]["mode"])


def decide_v2(C, cert_bytes, rtt_ms, p, burst=DEFAULT_ASSUMED_BURST, s0=None,
              W=quantum.P_SERVER, h=51, f=16,
              max_steps=2, m_max=M_MAX_DEFAULT,
              s0_base=None, c_pkt=0.0,
              t_recover_ms=None, t_recover_ack_ms=None,
              uplink_mbps=UPLINK_MBPS_DEFAULT,
              max_ips=QUICGO_MAX_IPS, allow_repack=False):
    """이 조건에서 첫 비행을 어떻게 만들지 고른다 (δ 와 m 을 함께).

    돌려주는 것: 고른 후보와 그 근거, 후보 전부의 J, 그리고 배제된 후보와 사유.

    max_ips — 이 값을 넘는 W_eff 는 **보낼 수 없으므로** 후보에서 뺀다(실측 근거는
    QUICGO_MAX_IPS 주석). None 을 주면 거르지 않는다(모형 탐색용).
    allow_repack — 'pad_repack'(데이터그램을 합쳐 재패킹) 후보를 넣을지.
    기본은 False 다. 재패킹은 CRYPTO 를 다시 쪼개는 실제 구현 변경을 요구하는데
    우리 테스트베드는 그걸 안 한다 — 모형에만 있는 선택지를 고르면 안 된다.
    """
    # 패리티 실크기를 후보 생성기에 넘긴다 — 이래야 후보 dict 의
    # client_bytes·allowed·n_rtt·added_bytes 가 점수와 같은 바이트를 가리킨다.
    # max_delta - 결합 후보(δ>0·m>0)의 δ 상한. 어차피 아래에서 max_ips 로
    # 거르므로 생성 단계에서 미리 막아 후보 목록이 헛되이 길어지지 않게 한다.
    # None 이면 안 막는다(모형 탐색용).
    _max_delta = None if max_ips is None else max(0, int(max_ips) - int(W))
    cands = quantum.levers(C, cert_bytes, s0, W=W, h=h, f=f,
                           max_steps=max_steps, m_max=m_max,
                           s0_base=s0_base, c_pkt=c_pkt,
                           parity_bytes=parity_datagram_bytes,
                           max_delta=_max_delta)
    k0 = capacity.natural_k(C, W, h)

    kept, dropped = [], []
    for c in cands:
        why = None
        if not allow_repack and c["mode"] == "pad_repack":
            why = "재패킹은 구현이 안 되어 있다"
        elif max_ips is not None and c["W_eff"] > max_ips:
            why = ("W_eff %d > 보낼 수 있는 상한 %d"
                   % (c["W_eff"], max_ips))
        elif (c["m"] > 0 and int(c.get("parity_bytes")
                                 or parity_datagram_bytes(c["W_eff"], c["k"]))
              > PARITY_DATAGRAM_MAX):
            why = ("패리티 데이터그램 %d B > 서버 수신 상한 %d"
                   % (int(c.get("parity_bytes")
                          or parity_datagram_bytes(c["W_eff"], c["k"])),
                      PARITY_DATAGRAM_MAX))
        if why:
            dropped.append({"cand": c, "why": why})
        else:
            kept.append(c)

    if not kept:
        raise RuntimeError("후보가 하나도 안 남았다 (max_ips=%r)" % (max_ips,))

    scored = []
    for c in kept:
        # cost_of(결정론 n_rtt)가 아니라 cost_of_v2(Go 이식: 기대 왕복 수 +
        # 실제 패리티 크기)를 쓴다. 이유는 "Go 이식 정합" 절 참고.
        e = cost_of_v2(c, W, rtt_ms, p, burst, t_recover_ms, uplink_mbps,
                       k0=k0, t_recover_ack_ms=t_recover_ack_ms)
        e["cand"] = c
        scored.append(e)
    # 🩸 2026-08-21 - 정렬 키 하나로 고르지 않는다. 잴 수 없는 J 차이가
    #    1,325 바이트짜리 후보를 1 바이트짜리보다 위에 올리던 자리다.
    #    _pick_best 가 명세 §3 의 순서를 분해능을 인정하며 적용한다.
    scored = _pick_best(scored)

    best = scored[0]
    base = next((e for e in scored if e["cand"]["mode"] == "none"), scored[-1])

    # 🩸 2026-08-20 감사 결함 4: 예전에는 levers 가 준 근사 n_rtt(1 또는 2)와
    #    근사 added_bytes 를 인용했다. 점수는 기대 왕복 수로 매기면서 설명은
    #    결정론 값을 읽어, 무손실 스윕에서 13 건이 어긋났다(levers 는 2-RTT 라
    #    하는데 실제 기대는 1.0). 이제 점수와 같은 값을 인용한다.
    reason = []
    bc, bs = best["cand"], base["cand"]
    if bc is not bs:
        # 조건부 기댓값끼리 비교한다. 가중합(n_rtt_expected)은 질량이
        # (1 - p_fail) 이라 실패 확률이 다른 후보끼리 빼면 부호가 뒤집힌다.
        d_rtt = base["n_rtt_given_ok"] - best["n_rtt_given_ok"]
        if d_rtt > 1e-9:
            reason.append("증폭 신용으로 기대 왕복 %.3f회 절약 (추가 %d B)"
                          % (d_rtt, best["added_bytes_real"]))
        if best["p_fail"] < base["p_fail"] - 1e-12:
            reason.append("손실 복구로 실패 확률 %.4f -> %.4f"
                          % (base["p_fail"], best["p_fail"]))
        if bc["mode"] == "pad" and best["added_bytes_real"] < W:
            reason.append("패리티 없이 δ=%d B 만으로 칸을 올렸다"
                          % bc["delta_per_dgram"])
    else:
        reason.append("추가 바이트가 이득을 못 낸다")

    return {
        "choice": bc,
        "choice_cost": {k: v for k, v in best.items() if k != "cand"},
        "gain_ms": base["j_ms"] - best["j_ms"],
        "candidates": [dict(e["cand"], **{k: v for k, v in e.items()
                                          if k != "cand"})
                       for e in scored],
        "dropped": [{"mode": d["cand"]["mode"], "W_eff": d["cand"]["W_eff"],
                     "m": d["cand"]["m"], "why": d["why"]} for d in dropped],
        "reason": "; ".join(reason),
        "warnings": ([("고른 후보에 late_parity_risk 가 있다 — 명세 §2.6, "
                       "p13 전까지 신용이 과대평가일 수 있다")]
                     if bc["late_parity_risk"] else []),
        # 실패 가지가 둘이므로 값도 둘이다. 어느 쪽을 썼는지 밝힌다.
        "t_pto_ms": best["t_pto_ms"],
        "t_ack_ms": best["t_ack_ms"],
    }


# ---------------------------------------------------------------------------
# Go 이식 정합 — experiments/quicbed/policy.go 와 **글자 단위로** 맞춘다.
# ---------------------------------------------------------------------------
#
# 🩸 1차에서 Cauchy 행렬을 Go/Python 에 각각 짰다가 갈라졌다. 둘 다 MDS 라
#    각자는 정상 동작하는데 서로 호환이 안 됐고, 교차검증이 아니었으면 못 잡았다.
#    그래서 이번에는 **양쪽이 같은 식을 쓰는지 여기서 못 박는다.**
#
# 2026-08-20 에 실제로 두 군데가 갈라져 있었다.
#
#   (1) n_rtt 를 Python 은 결정론(1 또는 2)으로, Go 는 **기댓값**으로 계산했다.
#       Go 가 옳다 — 증폭 신용은 보장된 것이 아니라 **패리티가 실제로 도착해야**
#       생긴다. 패리티가 유실되면 그 바이트가 예산에 안 잡혀 왕복을 도로 잃는다.
#       (실측: 임계위·손실5% 꼬리가 m=1 8.0% vs m=2 1.0% 로 갈렸다.)
#
#   (2) 패리티 데이터그램 크기를 Python(quantum.levers)은 W 로, Go 는
#       W + 32 + 6k 로 봤다. 롱헤더(~19) + FEC 머리(13) + crc/len 목록(6k) 때문이다.
#       k=1·W=1280 에서 38 B 차이인데, 양자 경계에서는 이게 칸을 가른다.
#
# 그래서 v2 정책은 **후보 생성만** quantum.levers 에 맡기고, 비용 계산은
# 아래 Go 이식 함수로 다시 한다.

PARITY_OVERHEAD_BASE = 46
PARITY_OVERHEAD_PER_K = 6
PARITY_DATAGRAM_MAX = 1452


def parity_datagram_bytes(w, k):
    """패리티 데이터그램 하나의 크기. policy.go parityDatagramBytes 와 동일."""
    return w + PARITY_OVERHEAD_BASE + PARITY_OVERHEAD_PER_K * k


def flight_order(k, m):
    """비행 안 데이터그램 배치 (명세 §2.6).

    m=1  -> [원본…, 패리티]           뒤엣것이 복구용
    m>=2 -> [패리티0, 원본…, 패리티1] 앞이 신용, 뒤가 복구

    배치가 결과를 바꾼다 — 손실이 뭉치면(버스트) **인접한 것이 함께 사라지므로**
    패리티를 어디에 두느냐가 도착 조합의 분포를 바꾼다. 독립 손실 가정에서는
    배치가 무의미해서 예전 코드에는 이 함수가 필요 없었다.
    """
    if m <= 0:
        return ["O"] * k
    if m == 1:
        return ["O"] * k + ["P"]
    return ["P"] + ["O"] * k + ["P"] * (m - 1)


def joint_arrival_pmf(k, m, p, burst):
    """P[a][b] = 원본 a 개·패리티 b 개가 **도착**할 확률.

    🩸 2026-08-20 감사 결함 1 의 수리. 예전 `expected_n_rtt` 는 원본과 패리티를
       **각각 독립 이항**으로 굴렸는데, 같은 비용식 안의 `p_fail` 은
       Gilbert-Elliott 을 썼다. **한 식에 손실 모형이 두 개**였다.
       증거: k=2·m=1·p=0.05 에서 burst 를 1->5 로 바꾸면 p_fail 은 6.6 배가
       되는데 n_exp 는 소수점 6 자리까지 꿈쩍도 안 했다.

    그래서 두 항을 **한 분포에서** 뽑는다. DP 규약은 afec.channel.pmf_table 과
    같다(현재 상태로 손실을 내고 -> 전이한다). 그래야 이 함수의 주변분포가
    erasure_pmf 와 정확히 일치한다 — 자체시험 3 이 그것을 확인한다.
    """
    ge = GilbertElliott.for_prior(p, burst)
    order = flight_order(k, m)
    trans = ge.transition
    loss = (ge.p_good, ge.p_bad)
    pi = ge.stationary

    cur = [[[0.0] * (m + 1) for _ in range(k + 1)] for _ in range(2)]
    cur[0][0][0] = pi[0]
    cur[1][0][0] = pi[1]

    for tok in order:
        nxt = [[[0.0] * (m + 1) for _ in range(k + 1)] for _ in range(2)]
        for s_ in (0, 1):
            l = loss[s_]
            for a_ in range(k + 1):
                row = cur[s_][a_]
                for b_ in range(m + 1):
                    wgt = row[b_]
                    if wgt == 0.0:
                        continue
                    for s2 in (0, 1):
                        t = trans[s_][s2]
                        if t == 0.0:
                            continue
                        if l > 0.0:
                            nxt[s2][a_][b_] += wgt * l * t
                        if l < 1.0:
                            keep = wgt * (1.0 - l) * t
                            if tok == "O":
                                nxt[s2][a_ + 1][b_] += keep
                            else:
                                nxt[s2][a_][b_ + 1] += keep
        cur = nxt

    return [[cur[0][a_][b_] + cur[1][a_][b_] for b_ in range(m + 1)]
            for a_ in range(k + 1)]


MAX_RECOVERY_ROUNDS = 20      # 기대 라운드 급수를 끊는 자리 (수렴은 훨씬 빠르다)


def expected_rounds(k, m, p, burst):
    """이 비행이 **몇 번** 나가야 서버가 받는가의 기댓값 (첫 시도 포함).

    🩸 2026-08-29 신설 — **모형이 복구 라운드를 정확히 한 번만 청구하고 있었다.**
       stall 항이 `p_fail * (rtt + T_pto)` 꼴이라 「재전송이 또 실패하는 경우」가
       통째로 빠져 있었다. p18 실측(cert 4032, 버스트 3, 손실 15%, 팔당 9,000 판)
       에서 실패한 연결의 **평균 라운드 수**는

           m=1  1.760    m=2  1.629    m=3  1.337    m=4  1.242

       인데 모형은 전부 1.000 으로 봤다. 그리고 **그 오차가 m 에 따라 다르므로
       m 끼리의 비교를 왜곡한다** — p18 검사 6 이 버스트 3 에서 실측 이득 +31.01
       vs 예측 +13.51 (230%) 로 붉어진 것이 이것이다. 방향이 **우리에게 불리한
       쪽**이었다(우리 알고리즘의 값을 스스로 깎고 있었다).

    ## 왜 정상분포에서 다시 시작하면 안 되나

    재전송은 **직전 실패의 채널 상태에서 시작**한다. netem 의 gemodel 은
    **패킷마다** 전이하므로 PTO 대기(≈200 ms) 동안 사슬이 이완하지 않는다.
    정상분포 가정으로 재실패 확률을 재면 실측의 0.38 배로 **2.6 배 과소평가**다
    (m=1: 유도 0.136 vs 실측 0.356).

    그래서 라운드마다 **실패 시점의 조건부 상태**를 다음 라운드의 초기 분포로
    넘긴다. 그 상태는 같은 DP 에서 나온다 — **맞춘 상수가 하나도 없다.**

    ## 실측 대조 (p18 버스트 3, 팔당 9,000 판)

        m      모형 R      실측 R     비
        1      1.214766   1.1896    1.021
        2      1.188659   1.1759    1.011
        3      1.114800   1.1044    1.009
        4      1.072777   1.0648    1.008

    ⚠️ 정정 (2026-09-01 확인, 09-07 반영). 위 「모형 R」열의 m=2..4 는 처음에
       1.2590 / 1.1566 / 1.0993 으로 적혀 있었는데 **지금 코드의
       expected_rounds(2, m, 0.15, 3.0) 은 1.188659 / 1.114800 / 1.072777** 이다.
       「비」열도 따라서 1.07/1.05/1.03 이 아니라 1.011/1.009/1.008 이고,
       decide_v2 안의 주석 「모형 R / 실측 R = 1.01~1.02」가 맞는 쪽이었다.
       위 실측 R 열은 results/p18_mmax.json 에서 재현된다.

    ⚠️ 위 「실패한 연결의 평균 라운드 수」(1.760/1.629/1.337/1.242)는 **폐기된
       자로 잰 값**이다 - 지연을 구간으로 잘라 세던 q(= P(2 라운드 이상 |
       1 라운드 실패))의 08-28 일회성 분석이고(볼트 세션 로그 2026-08-28), 그
       조잡함 때문에 q 를 버리고 R 로 갈아탔다. p18 원자료(p18_units.jsonl)에는
       라운드 필드가 없어 지금은 재현할 수 없다. 이 R_fail 은 R 과 **다른 양**이다
       (R = 1 + pf1 x (R_fail - 1)); 같은 표에 두면 헷갈리므로 지우지 않고 근거로만
       남긴다 - 왜 R 로 갔는지의 기록이다.

    이 항이 이득 예측을 얼마나 움직였는지의 전후 비교(「212% -> 97%」로 적혀
    있었다)는 재현 가능한 기록이 없어 지웠다(2026-09-07). 지금 p18 원자료
    (results/p18_mmax.json, 임계사이·버스트3, 팔당 8,999 판)로는
    m=2 -> m=4 이득이 예측 +13.51 vs 실측 +31.01 ± 7.40 ms 로 **예측이 실측의
    44%** 다 - 버스트에서 모형이 m 의 값을 여전히 과소평가한다는 것이 지금의 사실이다.

    ## 안전판 (아래 자체시험 21a~21c 가 못 박는다)

      - p = 0 이면 정확히 1.0 (무손실 실측이 한 톨도 안 움직인다)
      - 버스트 1 에서는 2 차 항이다 — 사슬이 사실상 무기억이라 조건부 상태가
        정상분포와 거의 같다. p18 의 무버스트 조건에서 예측 이득이
        10.69 -> 10.56 (1.2%) 밖에 안 움직인다. **기존에 검증된 무버스트
        결과가 안 흔들린다는 뜻이다.**
      - R 은 m 에 대해 단조 비증가여야 한다(패리티가 늘면 라운드가 줄어든다).
    """
    if p <= 0.0:
        return 1.0
    k = int(k)
    m = int(m)
    dist = None                    # None = 정상분포에서 시작
    alive = 1.0
    extra = 0.0
    for _ in range(MAX_RECOVERY_ROUNDS):
        st = _joint3c_state(k, m, p, burst, dist)
        # 실패 판정은 **recovers 와 같은 규칙**이어야 한다: 없어진 원본 수가
        # 도착한 뒤따르는 패리티 수를 넘으면 실패다. "소거 개수 > g" 로 세면
        # m=1 과 m=2 가 갈라진다(둘 다 g=1 인데 m=2 는 데이터그램이 하나 더
        # 많으니 소거가 더 잘 생긴다). 그것은 p_fail_of 와 어긋나는 정의다.
        # ⚠️ `not recovers(...)` 로 쓰면 안 된다 — recovers 는 **소거 0 개일
        #    때도 False** 를 돌려준다("복구할 것이 없다", 실패가 아니다).
        #    그렇게 세면 무손실 경로(전체의 대부분)가 통째로 실패로 잡혀
        #    pf 가 0.14 대신 0.94 가 된다. 실패는 `miss > c` 하나다.
        fg = fb = 0.0
        for a_ in range(k + 1):
            miss = k - a_
            for b_ in range(m + 1):
                for c_ in range(len(st[0][a_][b_])):
                    if miss <= c_:
                        continue
                    fg += st[0][a_][b_][c_]
                    fb += st[1][a_][b_][c_]
        pf = fg + fb
        if pf <= 0.0:
            break
        extra += alive * pf        # 이 라운드가 실패해 한 번 더 나간다
        alive *= pf
        if alive <= 1e-15:
            break
        dist = [fg / pf, fb / pf]  # 다음 라운드는 **실패 시점 상태**에서
    return 1.0 + extra


def recovery_group(k, m):
    """복구에 쓸 수 있는 **뒤따르는** 패리티 수 g.

    🩸 2026-08-28 (2 단계). qamp.go 의 배치와 짝이다.
        m = 0  -> 0   패리티가 없다
        m = 1  -> 1   [원본..., P]  그 하나가 뒤따른다
        m >= 2 -> m-1 [P0, 원본..., P1..]  선행 P0 은 **신용 전용**

    선행 패리티를 복구에 안 쓰는 이유는 바이트 회계가 아니라 **시각**이다.
    그것은 원본보다 먼저 오므로, 그것으로 복구를 시도하면 아직 도착하지
    않은 원본을 「소거됐다」로 오해한다(qamp.go 의 같은 자리 주석).
    """
    if m <= 0:
        return 0
    return 1 if m == 1 else m - 1


def _joint3c_state(k, m, p, burst, init=None):
    """joint_arrival_pmf3c 와 같은 DP 인데 **마지막 상태를 안 합친다.**

    돌려주는 것: st[s][a][b][c] — s=0 Good, s=1 Bad.
    init 은 [P(G), P(B)]. None 이면 정상분포에서 시작한다.

    🆕 2026-08-29 - expected_rounds 가 라운드 사이로 채널 상태를 넘기려고
       만들었다. 기존 DP 가 이미 상태를 들고 있었으므로(cur[s][a][b][c])
       **마지막 합치기만 안 하면 된다** - 새 모형을 짜는 것이 아니다.
       joint_arrival_pmf3c 는 이 함수의 상태 주변화로 정의한다(아래) -
       그래야 둘이 갈라질 수가 없다.
    """
    ge = GilbertElliott.for_prior(p, burst)
    order = flight_order(k, m)
    trans = ge.transition
    loss = (ge.p_good, ge.p_bad)
    pi = ge.stationary if init is None else list(init)
    g = recovery_group(k, m)

    def _blank():
        return [[[[0.0] * (g + 1) for _ in range(m + 1)]
                 for _ in range(k + 1)] for _ in range(2)]

    cur = _blank()
    cur[0][0][0][0] = pi[0]
    cur[1][0][0][0] = pi[1]

    for ti, tok in enumerate(order):
        lead = (tok == "P" and m >= 2 and ti == 0)
        nxt = _blank()
        for s_ in (0, 1):
            l = loss[s_]
            for a_ in range(k + 1):
                for b_ in range(m + 1):
                    for c_ in range(g + 1):
                        wgt = cur[s_][a_][b_][c_]
                        if wgt == 0.0:
                            continue
                        for s2 in (0, 1):
                            t = trans[s_][s2]
                            if t == 0.0:
                                continue
                            if l > 0.0:
                                nxt[s2][a_][b_][c_] += wgt * l * t
                            if l < 1.0:
                                keep = wgt * (1.0 - l) * t
                                if tok == "O":
                                    nxt[s2][a_ + 1][b_][c_] += keep
                                elif lead:
                                    nxt[s2][a_][b_ + 1][c_] += keep
                                else:
                                    cc = min(g, c_ + 1)
                                    nxt[s2][a_][b_ + 1][cc] += keep
        cur = nxt
    return cur


def joint_arrival_pmf3c(k, m, p, burst):
    """P[a][b][c] - 원본 a 개·패리티 b 개 도착, c = **뒤따르는 패리티 중 몇 개**.

    🩸 2026-08-28 (2 단계) - 셋째 축이 불리언에서 **개수**가 됐다.
       그전에는 "복구용 패리티(마지막 하나)가 왔는가"만 봤고, 그래서 모형의
       복구 능력이 m 과 무관하게 1 개로 묶여 있었다. 구현도 그랬으므로 둘은
       일치했지만, 그 일치가 **부호가 할 수 있는 것보다 약한 자리**에 있었다
       (신레오 2026-08-27 보고). 이제 뒤따르는 패리티 c 개로 소거 c 개까지
       푼다 - Cauchy 는 어느 정방 부분행렬도 가역이라 조합을 안 가린다.

    c 로 주변화하면 joint_arrival_pmf 와 정확히 같아야 한다(자체시험 20a).
    g=1 인 (m<=2) 자리에서는 옛 joint_arrival_pmf3 과 **비트 단위로** 같다
    (자체시험 20b) - 즉 이 변경은 m>=3 에서만 무언가를 바꾼다.
    """
    ge = GilbertElliott.for_prior(p, burst)
    order = flight_order(k, m)
    trans = ge.transition
    loss = (ge.p_good, ge.p_bad)
    pi = ge.stationary
    g = recovery_group(k, m)

    def _blank():
        return [[[[0.0] * (g + 1) for _ in range(m + 1)]
                 for _ in range(k + 1)] for _ in range(2)]

    cur = _blank()
    cur[0][0][0][0] = pi[0]
    cur[1][0][0][0] = pi[1]

    for ti, tok in enumerate(order):
        # 선행 패리티(m>=2 의 자리 0)만 신용 전용이다.
        lead = (tok == "P" and m >= 2 and ti == 0)
        nxt = _blank()
        for s_ in (0, 1):
            l = loss[s_]
            for a_ in range(k + 1):
                for b_ in range(m + 1):
                    for c_ in range(g + 1):
                        wgt = cur[s_][a_][b_][c_]
                        if wgt == 0.0:
                            continue
                        for s2 in (0, 1):
                            t = trans[s_][s2]
                            if t == 0.0:
                                continue
                            if l > 0.0:
                                nxt[s2][a_][b_][c_] += wgt * l * t
                            if l < 1.0:
                                keep = wgt * (1.0 - l) * t
                                if tok == "O":
                                    nxt[s2][a_ + 1][b_][c_] += keep
                                elif lead:
                                    nxt[s2][a_][b_ + 1][c_] += keep
                                else:
                                    cc = min(g, c_ + 1)
                                    nxt[s2][a_][b_ + 1][cc] += keep
        cur = nxt

    return [[[cur[0][a_][b_][c_] + cur[1][a_][b_][c_]
              for c_ in range(g + 1)] for b_ in range(m + 1)]
            for a_ in range(k + 1)]


def joint_arrival_pmf3(k, m, p, burst):
    """P[a][b][r] - 원본 a 개·패리티 b 개 도착, r = **복구용 패리티가 도착했는가**.

    🩸 2026-08-21 수리. 그전에는 도착 **개수**만 셌고(joint_arrival_pmf),
       flight_outcome 이 MDS 규칙 `(k-a) <= b` 로 복구 가능 여부를 판정했다.
       **구현은 그렇게 동작하지 않는다.**

       `experiments/quicbed/qamp.go` 의 서버는 역할을 나눠 놨다:
         - 마지막으로 보낸 패리티(index m-1) **하나만** 복구용이다.
         - 그 앞의 것들은 순전히 증폭 신용용이라 복구에 쓰지 않는다
           (신용 패리티는 원본보다 먼저 도착하므로 그것으로 복구를 시도하면
            "마지막 원본이 아직 안 왔다"를 소거로 오해한다 - 실제로 그렇게
            오작동해서 역할을 코드에 못박은 것이다).
         - `tryRecoverLocked` 는 `len(missing) > 1` 이면 곧바로 포기한다.

       즉 **실제 복구 능력은 m 과 무관하게 소거 1 개**다. 모형은 m=2 에서
       소거 2 개까지 복구된다고 믿었다 - k=1·m=2·p=0.05 에서 P_fail 이
       1.25e-4 vs 실제 2.5e-3 으로 **20 배 낙관**이었다.

    그래서 "몇 개 왔나"가 아니라 "**어느 것이** 왔나"를 알아야 한다.
    flight_order 는 복구용 패리티를 항상 **맨 끝**에 둔다(m=1 은 [O..,P],
    m>=2 는 [P, O.., P..] 로 마지막 P 가 index m-1). 그래서 DP 의 마지막
    토큰만 표시하면 된다. m=0 이면 마지막 토큰이 "O" 라 r 은 언제나 0 이다.

    규약은 joint_arrival_pmf 와 같다(현재 상태로 손실을 내고 -> 전이한다).
    r 로 주변화하면 joint_arrival_pmf 와 정확히 같아야 한다 - 자체시험 3b.
    """
    ge = GilbertElliott.for_prior(p, burst)
    order = flight_order(k, m)
    trans = ge.transition
    loss = (ge.p_good, ge.p_bad)
    pi = ge.stationary
    last = len(order) - 1

    def _blank():
        return [[[[0.0, 0.0] for _ in range(m + 1)] for _ in range(k + 1)]
                for _ in range(2)]

    cur = _blank()
    cur[0][0][0][0] = pi[0]
    cur[1][0][0][0] = pi[1]

    for ti, tok in enumerate(order):
        nxt = _blank()
        for s_ in (0, 1):
            l = loss[s_]
            for a_ in range(k + 1):
                for b_ in range(m + 1):
                    for r_ in (0, 1):
                        wgt = cur[s_][a_][b_][r_]
                        if wgt == 0.0:
                            continue
                        for s2 in (0, 1):
                            t = trans[s_][s2]
                            if t == 0.0:
                                continue
                            if l > 0.0:
                                nxt[s2][a_][b_][r_] += wgt * l * t
                            if l < 1.0:
                                keep = wgt * (1.0 - l) * t
                                if tok == "O":
                                    nxt[s2][a_ + 1][b_][r_] += keep
                                else:
                                    rr = 1 if ti == last else r_
                                    nxt[s2][a_][b_ + 1][rr] += keep
        cur = nxt

    return [[[cur[0][a_][b_][r_] + cur[1][a_][b_][r_] for r_ in (0, 1)]
             for b_ in range(m + 1)] for a_ in range(k + 1)]


def last_original_index(k, m):
    """비행 안에서 **마지막 원본**이 놓이는 자리. flight_order 와 짝이다."""
    order = flight_order(k, m)
    return max((i for i, t in enumerate(order) if t == "O"), default=-1)


def last_original_pmf(k, m, p, burst):
    """P[a][r][o] - o = **마지막 원본이 도착했는가.**

    🩸 2026-08-27 수리. 그전에는 복구 실패의 대가를 `a == 0`(서버가 하나도
       못 받았는가)로 갈랐다. **틀린 판별자다.**

       RFC 9002 §6.1 - QUIC 은 패킷 손실을 **그보다 뒤에 보낸 패킷이
       ACK 됐을 때만** 패킷 임계/시간 임계로 선언할 수 있다. 우리 패리티는
       심(shim)이 소켓에 직접 쓰는 롱헤더 위장 패킷이라 **클라이언트 패킷
       번호를 안 갖고**, 서버는 AEAD 에서 버리므로 **영원히 ACK 되지 않는다**
       (qamp.go flushFlight -> c.PacketConn.WriteTo). 그러므로 첫 비행에서
       **가장 큰 패킷 번호는 마지막 원본**의 것이다.

         · 마지막 원본이 **도착**하고 앞의 것이 없어졌다
             -> 그 ACK 이 시간 임계를 무장시킨다 -> 9/8·RTT 만에 재전송.
                (T_ACK_RETX_SLOPE 가 1.125 = 9/8 인 것이 우연이 아니다 —
                 RFC 9002 §6.1.2 의 kTimeThreshold 가 바로 9/8 이다.)
         · 마지막 원본이 **없어졌다** (앞의 것은 도착)
             -> 뒤에 ACK 될 패킷이 없다 -> **구멍을 영영 못 본다** -> PTO.
                다만 앞의 원본이 ACK 됐으므로 **RTT 표본이 있다**:
                RFC 9002 §5.3 첫 표본에서 rttvar = 표본/2 이고, §6.2.1 의
                PTO = srtt + 4·rttvar (Initial/Handshake 는 max_ack_delay 제외)
                -> **PTO = 3·RTT.** 맞춘 상수가 아니라 RFC 에서 나온 값이다.
         · 아무것도 도착 안 했다
             -> ACK 자체가 없어 RTT 표본도 없다 -> 경로 무관 상수(T_PTO_NO_ACK_MS).

    **이 저장소의 원자료가 그대로 판정한다** (`results/p7_verify.json`,
    결정적 소거, k=2 · RTT 50 · cert 2955 · 팔당 n=40):

        V1 소거 없음                        p50  54.027 ms   (기준선)
        V2 원본0 소거 (마지막 원본 **도착**)   p50 112.258 ms   +58.2  ≈ 9/8·RTT
        V3 원본1 소거 (마지막 원본 **유실**)   p50 208.545 ms   +154.5 ≈ 3·RTT
        V9 원본0+1 소거 (아무것도 없음)        p50 254.623 ms   +200.6 ≈ 200.86

        (위는 2026-08-2x 판이다. 2026-08-30 재측정 results/p7_verify.json 은
         기준선 51.591 에 증분 +58.6 / +152.6 / +201.6 - 배율 오차 +1.7% 안에서
         같은 세 모드다. 자체시험 19d 가 이 파일을 직접 읽어 대조한다.)

    **V2 와 V3 은 옛 모형에서 완전히 같은 상태(a=1, r=0)인데 96.3 ms 갈린다.**
    p95 가 각각 114.8 / 210.7 로 붙어 있으니 잡음이 아니라 서로 다른 두
    결정적 모드다. 옛 식은 둘 다 V2 쪽으로 봤고, 그래서 V3 에서 **96.8 ms**
    를 빠뜨렸다.

    T_ACK_RETX 세 상수가 `-drop-initial 0`(= V2 조건)으로만 측정된 것이
    이 결함이 오래 숨은 이유다. k=1 에서 그 조건은 "아무것도 안 왔다"이자
    "마지막 원본이 없어졌다"이고, k=2 에서는 "뭔가 왔다"이자 "마지막 원본이
    왔다"라서 **두 후보 규칙이 설계상 완전히 교락**돼 있었다. 한 설계로 두
    규칙을 가를 수 없었다는 뜻이고, 그래서 검사가 아니라 **설계**를 고쳐야
    한다 - `_probe_trecover.py` 에 `-drop-initial k-1` 팔을 더할 것.

    ⚠️ 왜 (a, r, o) 만 돌려주고 b 를 안 세나 - 실패 가지의 값은 b 에
       의존하지 않기 때문이다. b 가 필요한 회계(신용·왕복 수)는
       joint_arrival_pmf3 이 그대로 맡는다. **분포를 하나 더 만드는 것이
       아니라 같은 DP 를 다른 축으로 주변화하는 것**이라 두 분포는 정의상
       서로 맞는다 - 자체시험 19a 가 확인한다.
    """
    ge = GilbertElliott.for_prior(p, burst)
    order = flight_order(k, m)
    trans = ge.transition
    loss = (ge.p_good, ge.p_bad)
    pi = ge.stationary
    last_o = last_original_index(k, m)
    g = recovery_group(k, m)

    # 🩸 2026-08-28 (2 단계) - 축이 (a, c, o) 다. c 는 **뒤따르는 패리티
    #    개수**이고 옛 판의 불리언 r 을 대신한다. 복구 성립 여부가 c 로
    #    갈리므로, 실패 질량을 세려면 이 축이 있어야 한다.
    def _blank():
        return [[[[0.0, 0.0] for _ in range(g + 1)] for _ in range(k + 1)]
                for _ in range(2)]

    cur = _blank()
    cur[0][0][0][0] = pi[0]
    cur[1][0][0][0] = pi[1]

    for ti, tok in enumerate(order):
        lead = (tok == "P" and m >= 2 and ti == 0)
        nxt = _blank()
        for s_ in (0, 1):
            l = loss[s_]
            for a_ in range(k + 1):
                for c_ in range(g + 1):
                    for o_ in (0, 1):
                        wgt = cur[s_][a_][c_][o_]
                        if wgt == 0.0:
                            continue
                        for s2 in (0, 1):
                            t = trans[s_][s2]
                            if t == 0.0:
                                continue
                            if l > 0.0:
                                nxt[s2][a_][c_][o_] += wgt * l * t
                            if l < 1.0:
                                keep = wgt * (1.0 - l) * t
                                if tok == "O":
                                    oo = 1 if ti == last_o else o_
                                    nxt[s2][a_ + 1][c_][oo] += keep
                                elif lead:
                                    nxt[s2][a_][c_][o_] += keep
                                else:
                                    cc = min(g, c_ + 1)
                                    nxt[s2][a_][cc][o_] += keep
        cur = nxt

    return [[[cur[0][a_][c_][o_] + cur[1][a_][c_][o_] for o_ in (0, 1)]
             for c_ in range(g + 1)] for a_ in range(k + 1)]


def fail_split(k, m, p, burst):
    """실패 질량을 세 가지로 나눈 (pto_noack, pto_sampled, ack).

    합은 p_fail 과 정확히 같아야 한다(자체시험 19a). 이 함수만 다른 축의
    분포를 쓰고, 나머지 회계는 joint_arrival_pmf3c 그대로다 - 수리의
    접촉면을 **실패 가지 하나로** 좁혀 둔다.
    """
    if p <= 0.0:
        return 0.0, 0.0, 0.0
    g = recovery_group(k, m)
    pm = last_original_pmf(k, m, p, burst)
    noack = sampled = ack = 0.0
    for a_ in range(k + 1):
        for c_ in range(g + 1):
            for o_ in (0, 1):
                pr = pm[a_][c_][o_]
                if pr <= 0.0:
                    continue
                miss = k - a_
                if miss <= 0 or recovers(k, a_, c_):
                    continue
                if o_:
                    ack += pr
                elif a_ == 0:
                    noack += pr
                else:
                    sampled += pr
    return noack, sampled, ack


def recovers(k, a, recovery_parity_count):
    """이 도착 상태에서 서버가 실제로 복구하는가. qamp.go tryRecoverLocked 와 같다.

    🩸 2026-08-28 (2 단계) - 셋째 인자가 불리언에서 **개수**가 됐다.
       규칙: 소거 e 개는 **뒤따르는 패리티 e 개**로 푼다.

           소거 0 개        복구할 것이 없다 (실패도 아니다)
           1 <= e <= c      복구한다
           e > c            패리티가 모자란다. 실패

       그전 규칙은 `e == 1 and 마지막 패리티 도착` 이었다. 그것은 구현이
       소거를 정수 하나로만 받았기 때문이고(recoverOne), 부호 자체의 한계가
       아니었다 - Cauchy 는 어느 정방 부분행렬도 가역이다. 구현을
       recoverMany 로 바꿨으므로 모형도 따라간다.

       ⚠️ g = recovery_group(k, m) 이라 m<=2 에서는 g=1 이고, 그때 이 규칙은
          옛 규칙과 **완전히 같다.** 즉 이 변경은 m>=3 에서만 무언가를 바꾼다.
    """
    miss = k - a
    if miss <= 0:
        return False
    return miss <= int(recovery_parity_count)


def n_need_for_flight(server_flight, pkt=quantum.P_SERVER):
    """칸에 의존하지 않는 S 를 담는 최소 칸. 자체시험·탐침용 보조."""
    import math
    return max(1, int(math.ceil(float(server_flight) / float(pkt))))


# ---------------------------------------------------------------------------
# 증폭 신용의 '경주' — 뒤따르는 패리티는 **송신 결정 전에** 닿아야 신용이 된다
# ---------------------------------------------------------------------------
#
# 🩸 2026-08-26 실측 수리. 그전 모형은 패리티 m 개의 바이트를 **무조건** 증폭
#    예산에 넣었다. 바이트 회계로는 그게 옳다(qamp.go:1402 - 복호 불가 패킷도
#    quic-go 가 바이트를 센 뒤 버리므로 예산은 그만큼 오른다). 틀린 것은
#    바이트가 아니라 **시각**이었다.
#
#    송신 순서(qamp.go flushFlight)가 m 으로 갈린다:
#        m = 1  : [원본..., 패리티]              패리티가 원본 **뒤**
#        m >= 2 : [패리티0, 원본..., 패리티1..]   하나가 원본 **앞**
#
#    서버는 **복호 가능한 마지막 패킷**을 처리할 때 보낼지를 정한다. 패리티는
#    복호가 안 되므로 송신을 깨우지 못한다(quic-go connection.go:669 의
#    `if !wasProcessed { continue }`). 그래서 뒤따르는 패리티의 바이트는 예산에
#    들어가되 **그 결정보다 늦으면 그 연결에서는 소용이 없다.**
#
#    대역이 걸리면 늦는 정도는 직렬화 시간 그대로다:  d = 패리티 바이트 / 대역
#    m=1 은 이 경주에서 지면 왕복을 통째로 하나 더 쓴다. 2 Mbps·cert 9000·k=2
#    에서 모형 53.0 ms vs 실측 122.2 ms - **오차 69.2 ms** 였고, 정책이 그 값을
#    믿고 m=1 을 골라 최선(m=3, 71.0 ms)보다 51 ms 손해를 봤다.
#
#    ⚠️ 대역 무제한이면 d=0 이라 q=1 이고, 이 항은 **아무것도 바꾸지 않는다.**
#       그래서 무제한에서 이미 검증된 것들(p4·p16·p18)은 그대로 남는다.
#
# q(d) 를 **표로** 심는 이유는 padfec/table.py 머리말과 같다 - 이건 유도한
# 모형이 아니라 **이 기계에서 잰 값**이고, 함수꼴로 적으면 자료에 없는 모양을
# 지어내게 된다. 실제로 지수꼴·정규꼴을 맞춰 봤는데 평평한 머리(d<=0.27)와
# 꼬리를 동시에 못 맞췄다(정규꼴은 d=0.133 에서 0.86 이라 실측 0.996 과
# 14 %p 어긋난다). 마디 사이는 선형보간하고 마지막 마디 위는 0 이다.
#
# 실측 2026-08-26 (probe_race2.py, cert 9000·k=2·RTT 50·**손실 0%**·gap 50 ms
# ·팔당 250 연결). 손실 0 으로 재는 이유: 손실이 있으면 m=1 의 2-RTT 가 두
# 원인(경주에 짐 / 패리티 자체를 잃음)에서 나와 섞인다. 손실 0 이면 이 모형의
# p_two_rtt 가 0 이므로 **m1 의 1-RTT 비율이 곧 q(d)** 다.
#
#     업링크   80    40    30    20    15    10 Mbps   (무제한 = d 0)
#     d(ms)  0.133 0.266 0.355 0.533 0.710 1.066
#     m1 q   0.996 0.972 0.640 0.404 0.212 0.004
#     m2     1.000 1.000 1.000 1.000 1.000 1.000   <- 앞선 패리티는 경주가 없다
#
# m=2 가 **어느 대역에서도 100%** 인 것이 이 모형의 뼈대를 그대로 확인해 준다.
# 그리고 1.066 ms 위는 아침 스윕(4·2·1 Mbps, d = 2.66·5.32·10.65)에서 팔당
# 150 연결 중 **1-RTT 가 한 건도 없었다.**
#
# ⚠️ 한계: q 는 서버의 송신 결정 지연 X 의 분포이고 그건 **기계와 부하에**
#    달렸다(T_PTO_NO_ACK_MS·C_PKT_POLICY_DEFAULT 와 같은 종류의 환경 상수다).
#    같은 자리를 부하가 있을 때 재면 X 가 커져 q 가 올라간다 - 실제로 다른
#    실험과 겹쳐 돌던 아침 탐침은 d=1.066 에서 0.387 이 나왔다(여기서는
#    0.004). 정책이 실제로 밟는 자리는 d>=1 ms(대역 <=10 Mbps, q~0)이거나
#    d=0(무제한, q=1)이라 이 흔들림이 선택을 바꾸지는 않는다.
RACE_DELAY_MS = (0.0, 0.133, 0.266, 0.355, 0.533, 0.710, 1.066)
RACE_WIN_Q = (1.0, 0.996, 0.972, 0.640, 0.404, 0.212, 0.004)


def trailing_parity_delay_ms(k, w, uplink_mbps):
    """뒤따르는 패리티 하나가 **마지막 원본보다** 늦게 도착하는 시간 (ms).

    앞선 패리티(m>=2 의 index 0)는 원본보다 먼저 나가므로 이 지연을 안 겪는다.
    uplink_mbps <= 0 이면 대역 제한이 없다는 뜻이라 0 이다 - tx_cost_ms 와
    같은 약속이다.
    """
    if not uplink_mbps or uplink_mbps <= 0:
        return 0.0
    return parity_datagram_bytes(w, k) * 8.0 / (float(uplink_mbps) * 1e6) * 1e3


def race_win_prob(delay_ms):
    """지연 delay_ms 로 도착한 패리티의 신용이 **송신 결정에 잡힐** 확률.

    마디 사이는 선형보간, 마지막 마디 위는 0. Go 의 raceWinProb 와 글자 단위로
    같은 식이어야 한다(표는 pfail_table.go 에 심는다).
    """
    d = float(delay_ms)
    if d <= RACE_DELAY_MS[0]:
        return RACE_WIN_Q[0]
    if d >= RACE_DELAY_MS[-1]:
        return 0.0
    for i in range(1, len(RACE_DELAY_MS)):
        if d <= RACE_DELAY_MS[i]:
            lo, hi = RACE_DELAY_MS[i - 1], RACE_DELAY_MS[i]
            t = (d - lo) / (hi - lo)
            return RACE_WIN_Q[i - 1] + t * (RACE_WIN_Q[i] - RACE_WIN_Q[i - 1])
    return 0.0


def credit_branches(a, w, parity, lead_arrived, n_trail, trail_delay_ms):
    """송신 결정 시점의 신용 바이트를 (확률, 바이트) 가지로 쪼갠다.

    **복구가 없는 상태에서만** 부른다(복구가 일어나면 서버는 복구용 패리티를
    받은 뒤에야 원본을 다 갖게 되므로 경주 자체가 없다).

    인자
        lead_arrived  선행 패리티(m>=2 의 자리 0)가 왔는가. 0 또는 1.
        n_trail       **뒤따르는** 패리티 중 몇 개가 도착했는가.

    🩸 2026-08-28 (2 단계) - **근사를 없앴다.** 그전 시그니처는 (b_credit, r)
       이었고, 결합분포가 패리티를 개수로만 세는 탓에 선행 패리티가 왔는지를
       `b_credit / (m-1)` 이라는 **교환가능 가정**으로 추측했다. 버스트 손실
       에서는 그 가정이 틀리고(살아남는 것이 뒤쪽에 몰린다), 감사가 최악
       0.058 왕복(RTT 50 에서 2.9 ms)으로 재 뒀다. 이제 셋째 축이 「뒤따르는
       패리티 개수」라 선행 도착 여부를 **정확히** 안다 - 추측할 것이 없다.

    남은 근사 하나는 적어 둔다: 도착한 뒤따르는 패리티가 **송신 순서상 앞의
    n_trail 개**라고 본다. i 번째 뒤따르는 패리티는 마지막 원본보다 i*d 늦으
    므로 P(i 개 이상 닿음) = q(i*d) 이고, 정확히 j 개일 확률은
    q(j*d) - q((j+1)*d) 다. 어느 것이 살아남았는지까지 세려면 자리 축이 하나
    더 필요한데, q 가 사실상 계단이라(d>=1.066 ms 면 0, d=0 이면 1) 정책이
    밟는 자리에서는 답이 같다.

    trail_delay_ms = 0 이면 q 가 전부 1 이라 옛 식(도착한 패리티 전부를 신용에
    넣는 식)과 **글자 그대로 같은 값**이 나온다.
    """
    base = a * w + (1 if lead_arrived else 0) * parity
    out = []
    prev = 1.0
    for i in range(1, int(n_trail) + 1):
        qi = race_win_prob(i * trail_delay_ms)
        if prev - qi > 0.0:
            out.append((prev - qi, base + (i - 1) * parity))
        prev = qi
    if prev > 0.0:
        out.append((prev, base + int(n_trail) * parity))
    return out


def flight_outcome(k, m, w, p, burst, n_need, trail_delay_ms=0.0):
    """한 비행의 결과를 **하나의 분포에서** 낸다. policy.go flightOutcome 과 같다.

        n_rtt_expected  복구에 성공한 상태들만의 기대 왕복 수
        p_fail          복구 불가 확률
        p_two_rtt       복구는 됐는데 증폭 예산이 모자라 2-RTT 인 확률

    🩸 2026-08-20 감사 결함 2 의 수리 — **같은 손실 사건을 두 번 청구하지 않는다.**
       예전 식은 모든 상태에 대해 E[n_rtt] 를 낸 뒤 거기에 P(실패)·T_recover 를
       **더했다.** 그런데 데이터그램이 전멸하면 서버는 아무것도 못 받으므로
       allowed(0)=0 이라 n=2 로 세어지고, 동시에 p_fail 로 T_recover 도 물었다.
       물리적으로는 한 사건(전멸 -> 재전송)이다.
       실측 예: m=0·k=1·p=0.2 에서 base 60 ms + stall 10 ms = 70 ms 였다.
       보정하면 60 ms 이고, 290 조건 중 5 건에서 결정이 뒤집혔다(전부 불필요한
       1,318 B 패리티를 사고 있었다).

    그래서 n_rtt 는 **복구 성공 상태에만** 매기고, 복구 실패는 호출부가
    (RTT + T_recover) 한 번으로 값을 매긴다. p=0 이면 실패 확률이 0 이라 예전
    식과 결과가 완전히 같다 — 헤드라인(1 바이트 절벽)은 영향받지 않는다.
    """
    parity = parity_datagram_bytes(w, k)
    g = recovery_group(k, m)
    pm = joint_arrival_pmf3c(k, m, p, burst)
    n_sum = 0.0
    p_fail = 0.0
    p_two = 0.0
    p_rec = 0.0
    # 🩸 2026-08-28 (2 단계 감사) - 복구 가지의 임계경로에 실제로
    #    드는 뒤따르는 패리티 바이트의 **기댓값**. 상수
    #    trailing_parity_bytes(=parity*(m-1)) 를 대신한다.
    trail_bytes = 0.0
    for a_ in range(k + 1):
        for b_ in range(m + 1):
            for c_ in range(g + 1):
                pr = pm[a_][b_][c_]
                if pr <= 0.0:
                    continue
                miss = k - a_
                rec = recovers(k, a_, c_)
                if miss > 0 and not rec:
                    p_fail += pr
                    # 실패의 대가는 **서버 QUIC 스택이 ACK 를 낼 수 있었는지**
                    # 로 갈린다. 0 이면 ACK 가 없어 PTO(경로 무관 상수),
                    # 아니면 ACK 로 구멍이 드러나 즉시 재전송(왕복 하나).
                    #
                    # 🩸 2026-08-23 정정 — 조건이 `(a_ + b_) == 0` 이었다.
                    #    즉 **패리티만 도착해도 ACK 가 난다**고 봤는데 틀렸다.
                    #    우리 패리티는 롱헤더로 위장한 패킷이라 AEAD 를 통과하지
                    #    못하고, QUIC 스택은 복호 실패 패킷을 **조용히 버리며
                    #    ACK 하지 않는다**(RFC 9000 §12.2). 복구에 성공해야만
                    #    원본이 스택에 올라가고, 실패했으면 올라가는 것은
                    #    복호 불가 바이트뿐이다. 그러므로 ACK 를 낼 수 있는
                    #    조건은 **복호 가능한 원본이 하나라도 왔는가**(a_ >= 1)다.
                    #
                    #    실측이 이 정정을 지지한다(p17, 10Mbps·p=0.155·k=2):
                    #        모형(옛): m=1 PTO 0.0241 / m=2 PTO 0.0037
                    #        **실측**: m=1 PTO 0.023  / m=2 PTO 0.023
                    #        모형(새): m=1 PTO 0.0241 / m=2 PTO 0.0241
                    #    옛 식은 m 을 늘리면 PTO 가 6 배 줄어든다고 봐서 m=2 를
                    #    과대평가했다. m2-m1 예측이 -1.85 ms(m2 유리)였는데
                    #    실측은 +0.94 ms(m1 유리)로 **부호가 반대**였다.
                    #    정정 후 예측 +1.06 ms — 부호도 크기도 맞는다.
                    #    격자 330 점 중 81 점(24.5%)에서 선택이 바뀐다.
                    # 🩸 2026-08-27 - 여기서는 **합계만** 센다. 세 가지로
                    #    가르는 것은 fail_split 이 한다(그 주석에 근거와
                    #    실측이 있다). 판별자가 이 루프의 축(a, b, r)에
                    #    없는 값(마지막 원본의 도착 여부)이라 같은 자리에서
                    #    못 가른다 - 축을 늘리는 대신 주변화된 분포를 따로
                    #    쓴다. 둘의 합이 같은지는 자체시험 19b 가 못 박는다.
                    continue
                # 🩸 2026-08-21 수리 — 신용은 **서버 QUIC 스택이 실제로 센
                #    바이트**다. qamp.go 의 decodeConn.ReadFrom 이 하는 일:
                #      · 신용 패리티(index < m-1) -> 그대로 스택에 넘긴다(파 바이트)
                #      · 복구용 패리티(index m-1)
                #          복구 성공 -> **패리티를 버리고 복구본(원본, w 바이트)**
                #                       을 대신 넘긴다(불변식: 스택 누적 <= 물리
                #                       수신 누적. 안 그러면 3 배 한도를 우회한다)
                #          그 외     -> 패리티를 그대로 넘긴다
                #
                #    그전 식 `a*w + b*파` 는 복구가 일어난 상태에서 **잃은
                #    원본의 신용까지 패리티 크기로 셌다.** k=1·m=1 에서 실제
                #    신용은 1,280 B 인데 모형은 2,605 B 로 봤고, 그래서
                #    임계 근처에서 2-RTT 를 1-RTT 로 착각했다.
                #
                #    실측이 그대로 보여 준다(p15 임계사이/손실5%, k=1·m=1):
                #      모형(옛) 2-RTT 4.75%  |  실측 꼬리 9.0%
                #      옳은 회계: P(패리티 유실)=4.75% + P(원본 유실->복구)=4.75%
                #                 = 9.5%  <- 두 경우 다 신용이 1,280 으로 떨어진다
                # 🩸 2026-08-28 (2 단계) - 복구에 **쓰인** 패리티만 신용에서
                #    빠진다. 소거 e 개를 풀면 뒤따르는 패리티 e 개가 복원본
                #    (원본 크기 w)으로 바뀌고, 나머지는 신용 그대로다.
                #    e 는 miss 와 같다(복구가 일어난 가지에서만 쓴다).
                used = miss if rec else 0
                b_credit = b_ - used               # 신용으로 남는 패리티 수
                # 2026-08-21 - `server_flight > allowed(arrived)` 가
                # 아니라 **칸 비교**다. 필요한 칸 n_need 는 연결마다
                # 하나의 상수이고 도착 상태와 무관하다 - 서버는 자기가
                # 실제로 받은 신용으로 보낼 수 있는 만큼만 보낸다.
                # 근거는 quantum._candidate 의 n_need 주석.
                if rec:
                    # 🩸 2026-08-26 (2) - 이 가지의 질량을 따로 센다. 여기가
                    #    **뒤따르는 패리티가 임계경로에 드는 유일한 가지**다
                    #    (아래 trailing_parity_bytes 주석 참고).
                    p_rec += pr
                    # 🩸 2026-08-28 (2 단계 감사) - **복구 가지에도 경주가 있다.**
                    #    옛 주석은 "서버는 복구용 패리티(송신 순서상 마지막)를
                    #    받고 나서야 원본을 다 갖게 되므로 경주가 없다"고 적었다.
                    #    2 단계 뒤로 그 문장은 거짓이다. 복구는 **miss 번째**
                    #    뒤따르는 패리티에서 끝나고(qamp.go tryRecoverLocked ->
                    #    settleRecovery 가 그 자리에서 복원본을 넘기고 반환한다),
                    #    그 뒤에 오는 c_-miss 개는 **결정보다 늦게 닿는다.**
                    #    옛 식은 그것들을 b_credit 에 전액 넣어 신용으로 셌다.
                    #      k=2 m=3 p=0.02 n_need=11 trail_delay=5.324 에서
                    #        옛: p_two_rtt 0.963074, n_rtt 1.963042
                    #        옳: 1.0, 2.0        (상태 (a=1,b=3,c=2), 질량 0.0369)
                    #      RTT 50 에서 J 가 1.845 ms 과소 - J_TIE_MS 의 184 배다.
                    #    g=1 인 m<=2 는 c_==miss 라 초과분이 원리적으로 없다.
                    #
                    #    복구가 끝난 시점의 확실한 신용:
                    #      원본 a_ 개 + 복원본 miss 개 = (a_+miss)*w = k*w
                    #      + 선행 패리티(왔다면)
                    #    남은 c_-miss 개는 credit_branches 로 편다. 지연 기준점은
                    #    **복구 시점**이므로 j 번째는 j*d 다(credit_branches 가
                    #    i*d 로 세므로 그대로 넘기면 된다).
                    _lead_arrived = b_ - c_
                    _late_trail = c_ - miss
                    # 🩸 2026-08-28 (2 단계 감사) - **임계경로에 드는 것은
                    #    쓰인 패리티뿐이다.** trailing_parity_bytes 는 상수로
                    #    parity*(m-1) 을 청구하는데, 복구는 miss 번째에서
                    #    끝나므로 그 뒤 것들의 직렬화는 핸드셰이크를 안 늦춘다.
                    #    상태별로 세어 호출부에 넘긴다(tx_cost_ms 가 바이트에
                    #    선형이라 기댓값을 누적해도 정확하다).
                    trail_bytes += pr * parity * miss
                    for wgt, arrived in credit_branches(a_ + miss, w, parity,
                                                        _lead_arrived,
                                                        _late_trail,
                                                        trail_delay_ms):
                        if quantum.bin_index(arrived) < n_need:
                            n_sum += pr * wgt * 2.0
                            p_two += pr * wgt
                        else:
                            n_sum += pr * wgt
                    continue
                # 복구가 없는 상태 = 원본이 다 왔다. 서버는 **마지막 원본**을
                # 처리하면서 보낼지 정하므로, 뒤따르는 패리티의 신용은 그
                # 결정보다 먼저 닿아야 한다(위 '경주' 절).
                # 복구가 없는 가지에서는 도착한 패리티가 전부 신용이다.
                # credit_branches 는 「선행 패리티가 왔는가」와 「뒤따르는 것이
                # 결정 전에 닿았는가」를 편다 - 셋째 인자는 뒤따르는 개수다.
                _lead_arrived = b_ - c_            # 선행 패리티 도착 여부(0/1)
                for wgt, arrived in credit_branches(a_, w, parity,
                                                    _lead_arrived, c_,
                                                    trail_delay_ms):
                    if quantum.bin_index(arrived) < n_need:
                        n_sum += pr * wgt * 2.0
                        p_two += pr * wgt
                    else:
                        n_sum += pr * wgt
    # 실패 질량을 세 가지로 나눈다. 합은 정의상 p_fail 이다.
    p_fail_pto, p_fail_pto_sampled, p_fail_ack = fail_split(k, m, p, burst)
    ok = 1.0 - p_fail
    return {
        # 복구 성공 상태들에 대한 **가중합**이다. 질량이 (1 - p_fail) 이므로
        # p_fail 이 큰 후보끼리 이 값만 비교하면 안 된다 — 그럴 때는 아래
        # n_rtt_given_ok(조건부 기댓값)를 쓴다. 비용식은 가중합 쪽을 쓴다.
        "n_rtt_expected": n_sum,
        "n_rtt_given_ok": (n_sum / ok if ok > 1e-15 else 2.0),
        "p_fail": p_fail,
        # 실패 질량을 두 가지로 나눈다. 합은 p_fail 이다.
        "p_fail_pto": p_fail_pto,                  # 아무것도 없음 -> 표본 없는 PTO
        "p_fail_pto_sampled": p_fail_pto_sampled,  # 마지막 원본 유실 -> 3·RTT PTO
        "p_fail_ack": p_fail_ack,                  # 마지막 원본 도착 -> 시간 임계
        "p_two_rtt": p_two,
        "p_recoverable": ok,
        # 복구가 **실제로 일어난** 질량(소거가 있었고 복원에 성공). 성공
        # 상태 전체(ok)가 아니다 - ok 에는 "소거가 아예 없었다" 가 들어 있고
        # 그 가지에서는 서버가 마지막 원본에서 결정하므로 뒤따르는 패리티를
        # 기다리지 않는다.
        "p_recovered": p_rec,
        # 복구 가지에서 임계경로에 든 뒤따르는 패리티 바이트의
        # 기댓값(질량 가중). cost_of_v2 가 tx_cost_ms 로 바꾼다.
        "trail_bytes_expected": trail_bytes,
    }


def client_bytes_of(cand):
    """이 후보가 실제로 내보내는 클라이언트 바이트 (패리티 크기 반영)."""
    k, m, w = cand["k"], cand["m"], cand["W_eff"]
    return k * w + m * parity_datagram_bytes(w, k)


def critical_path_bytes(k, m, w):
    """업링크 직렬화가 **핸드셰이크를 실제로 늦추는** 바이트.

    🩸 2026-08-21 p16 실측 수리. 그전에는 t_tx 를 `추가 바이트 전부`에 물렸다.
       **틀렸다** - 비행 안에서 패리티가 어디에 실리는지에 따라 임계경로에
       드는 것과 안 드는 것이 갈린다. 송신 순서는 flight_order 와 같고,
       그 순서를 정하는 코드는 `qamp.go` 의 flushFlight 다.

         m = 1  : [원본..., 패리티]            패리티가 **뒤**라 원본을 안 늦춘다
         m >= 2 : [패리티0, 원본..., 패리티1..] 앞의 하나가 원본을 늦춘다

       서버가 응답을 만들려면 원본(CRYPTO)이 다 와야 하므로, 임계경로는
       `원본 k 개 + (m>=2 일 때) 앞선 패리티 하나` 다. 뒤따르는 패리티들은
       핸드셰이크를 안 늦춘다.

    실측(p16, netem rate 10mbit, x25519 k=1, 임계 아래):

        팔            추가 바이트   옛 모형     이 식      실측
        pad δ=172         172     0.138 ms   0.138 ms   0.141 ms
        m=1             1,326     1.061 ms   0.000 ms   0.002 ms   <- 530 배 과대였다
        m=2             2,654     2.121 ms   1.060 ms   0.951 ms

    옛 식은 m=1 의 대역 비용을 **530 배** 과대평가했다. 그래서 대역이 있는
    경로에서 정책이 패리티를 부당하게 기피했다.

    ⚠️ 이 식은 우리 배치(flight_order)에 묶여 있다. 배치를 바꾸면 여기도
       같이 바꿔야 한다 - 그래서 flight_order 바로 아래에 두지 않고 이름을
       주고 한 곳에서만 정의한다. Go 는 criticalPathBytes 가 같은 식이다.
    """
    if m >= 2:
        return k * w + parity_datagram_bytes(w, k)
    return k * w


def trailing_parity_bytes(k, m, w):
    """**복구 가지에서만** 임계경로에 드는, 뒤따르는 패리티의 바이트.

    🩸 2026-08-26 (2) **구조 수리** — 근거는 실측이 아니라 식 자체다.
       `critical_path_bytes` 는 *첫 비행*의 임계경로로는 옳지만(서버가 응답을
       만들려면 원본이 다 와야 한다), J 는 **핸드셰이크 완료 시각**이다. 복구가
       일어나는 가지에서는 서버가 **복구용 패리티(송신 순서상 마지막)까지
       받아야** 원본을 복원하므로, 그 앞에 줄 서 있는 패리티들의 직렬화가
       통째로 임계경로에 든다. flight_outcome 이 이미 그 사실을 신용 회계에
       쓰고 있었다("복구가 일어난 상태에는 경주가 없다") — 같은 분해를
       **시간**에는 안 쓰고 있었던 것이 결함이다.

       그전 식은 뒤따르는 패리티의 시간 비용을 **정확히 0** 으로 줬다. 그래서
       m=2·3·4 의 t_tx 가 전부 같은데 P_fail 은 안 오르므로, **J 에서 m 은 클수록
       좋고 정책은 늘 m_max 를 골랐다.** 대역이 걸린 자리에서 그것은 물리적으로
       틀렸다 — 패리티 데이터그램 하나가 2 Mbps 에서 5.32 ms 를 쓴다.

    ⚠️ **인용 정정 (2026-08-26 저녁).** 이 수정은 처음에 p17 한 판(cert 9000,
       k=2, 17:31)의 부호를 인용해 정당화됐다. **그 인용은 철회한다.** 같은
       운용점을 p18 이 독립으로 다시 재니 부호가 반대로 나왔다:

           m3 − m2                손실 2%     손실 15%
           p17 (n=750/팔, 17:31)   +0.73 ms   +1.86 ms
           p18 (n=1000/팔, 19:01)  −0.16 ms   −1.26 ms
           모형 (이 수정 후)        +0.17 ms   −0.23 ms   <- 두 측정 **사이**

       p18 은 자기 정밀도를 스스로 계산한다 — 이 크기를 판정하려면 **팔당
       8,544~12,404 판**이 필요한데 지금은 1,000 판이다. 두 측정 다 잡음에서
       나온 draw 이고, 따라서 이 수정은 **반증되지도 검증되지도 않았다.**

       그래도 남기는 근거는 셋이며 **전부 측정과 무관하다**:
         (1) 기전을 `qamp.go` 의 송신 순서가 직접 뒷받침한다 — 복구 가지에서
             서버는 송신 순서상 마지막 패리티까지 받아야 원본을 복원한다.
         (2) **맞춘 상수가 하나도 없다.** 바이트 수와 대역만으로 정해진다.
         (3) 무제한(대역 0)에서 옛 식과 **비트 단위로 같다**(자체시험 17a).
             즉 이미 검증된 무제한 결과를 하나도 안 흔든다.

       앞으로 이 수정을 인용할 때는 「실측이 요구해서」가 아니라 **「식이
       구조적으로 뒤따르는 패리티를 0 으로 셌으므로」** 라고 적는다.

    (이 식을 세운 p16 실측(2026-08-21)은 **임계 아래·저손실**이라 복구 가지를
     한 번도 안 밟았다 — 그것이 이 항이 빠진 채로 남아 있던 이유다.)

    보내는 순서(qamp.go flushFlight):
        m = 1  : [원본..., 패리티]              뒤따름 = 패리티 1 개
        m >= 2 : [패리티0, 원본..., 패리티1..]   뒤따름 = 패리티 (m−1) 개
    """
    if m <= 0:
        return 0
    parity = parity_datagram_bytes(w, k)
    return parity * (m - 1 if m >= 2 else 1)


def cost_of_v2(cand, W_base, rtt_ms, p, burst,
               t_recover_ms=None, uplink_mbps=UPLINK_MBPS_DEFAULT, k0=None,
               t_recover_ack_ms=None):
    """명세 §3 의 J — Go(policy.go) 와 같은 식으로 계산한다.

        J = E[n_rtt | 복구 성공]·RTT
          + P(실패·PTO)·(RTT + T_pto)
          + P(실패·ACK)·(RTT + T_ack)
          + t_tx

    네 항 전부가 **하나의 결합분포**(joint_arrival_pmf)에서 나온다.

    🩸 2026-08-20 실측 수리. 그전에는 실패 가지가 하나였고 그 값이
       `t_recover_ms = rtt_ms` 였다. **k=1 에서 4~20 배 작았다** — 결정적 소거로
       재 보니 서버가 아무것도 못 받는 경우는 RTT 와 무관한 **200.86 ms 상수**
       (quic-go 의 PTO 타이머)였다. 기본값을 그대로 두면 손실 한 번이 201 ms 인
       자리에서 정책이 무방비를 고른다(스윕 2,640 조건 중 405 건, k=1 만 보면
       1,320 중 286 건에서 결정이 뒤집혔다).

    t_recover_ms — PTO 가지 값을 직접 주고 싶을 때. None 이면 측정 상수.
    t_recover_ack_ms — ACK 가지 값. None 이면 측정 적합식(1.125·RTT + 1.42).
        Go 의 목적지 캐시가 관측값을 갖고 있으면 그것을 여기로 넘긴다 -
        **양쪽이 같은 인자를 받아야 같은 답이 나온다.**

    k0 — 기준선("아무것도 안 함")의 데이터그램 수. 추가 바이트를 이것 대비로
    센다. 안 주면 후보 자신의 k 를 쓴다(pad/parity 는 levers 가 k_floor=k0 로
    고정하므로 같다).
    """
    t_pto = (default_t_recover(rtt_ms, False) if t_recover_ms is None
             else float(t_recover_ms))
    t_ack = (default_t_recover(rtt_ms, True) if t_recover_ack_ms is None
             else float(t_recover_ack_ms))
    # 🩸 2026-08-21 - 2 차 수정으로 이 함수의 **계약이 바뀌었다**:
    #    1-RTT 판정을 cand["server_flight"] 가 아니라 상태 무관 상수
    #    cand["n_need"] 로 한다. 그런데 그 사실이 아무 데도 안 적혀
    #    있어서, 손으로 후보를 만드는 호출자(p4_model)가 조용히
    #    KeyError 로 죽었다. 무엇을 어떻게 채우라고 말한다.
    if "n_need" not in cand:
        raise KeyError(
            "cost_of_v2: 후보에 'n_need' 가 없다. 2026-08-21 부터 "
            "1-RTT 판정은 상태 무관 상수 n* 로 한다. "
            "quantum._candidate() 가 만든 후보는 이미 담고 있고, "
            "손으로 만들 때는 "
            "quantum.bin_needed(cert, None, s0_base, c_pkt) 로 채운다. "
            "(policy.n_need_for_flight(S) 는 c 항이 없는 근사라 "
            "정책 경로와 어긋날 수 있다 - 탐침 전용이다.) "
            "받은 열쇠: %s" % sorted(cand))
    k, m, w = cand["k"], cand["m"], cand["W_eff"]
    base_k = k if k0 is None else k0
    cb = client_bytes_of(cand)
    added = max(0, cb - base_k * W_base)
    tx_added = max(0, critical_path_bytes(k, m, w)
                   - critical_path_bytes(base_k, 0, W_base))
    # 🩸 2026-08-26 - 뒤따르는 패리티의 신용이 송신 결정 전에
    #    닿는지가 대역에 달렸다. 그 지연을 여기서 재서 넘긴다.
    out = flight_outcome(k, m, w, p, burst, cand["n_need"],
                         trail_delay_ms=trailing_parity_delay_ms(
                             k, w, uplink_mbps))
    n_exp = out["n_rtt_expected"]
    pf = out["p_fail"]
    # 🩸 2026-08-27 **구조 수리 — 실패 가지에 왕복 수를 안 물리고 있었다.**
    #
    #    T_recover 두 상수는 **기준선 대비 증분**으로 쟀다. 원자료가 그렇게
    #    말한다(`results/probe_trecover_rtt.json`): 행마다
    #        t_recover_ms = drop_p50 - base_p50
    #    이고, 그 잰 자리(cert 2308 · ips 1280)의 base_p50 은 51.3 ms —
    #    즉 **1-RTT 기준선**이다. 그런데 이 식은 `rtt_ms + t_recover` 로
    #    청구한다. 그것은 「기준선이 언제나 1 왕복」일 때만 맞는다.
    #
    #    기준선이 2 왕복인 팔(증폭 예산이 모자라 어차피 2-RTT 인 후보)에서는
    #    **왕복 하나를 통째로 빠뜨린다.**
    #
    #    실측이 이 자리를 직접 보여 준다(p17, 무제한 · 손실 15% · cert 9000 ·
    #    m=0, n=750). 느린 연결의 히스토그램이 여러 봉우리로 갈리는데:
    #        90~110 ms  463 건   정상 2-RTT (기준선 103 ms)
    #        150~170 ms  59 건   **103 + 57.7** <- ACK 재전송 가지
    #        250~270 ms  80 건   **50 + 200.86** <- PTO 가지
    #    ACK 가지는 기준선(2-RTT) **위에** 증분이 얹혀 있다. 모형은 그것을
    #    50 + 57.7 = 107.7 로 청구했다 - 왕복 하나(50 ms)가 빈다.
    #
    #    두 가지가 왜 다른가 — 재전송하는 **양**이 다르다.
    #      ACK 가지 : 서버가 ACK 를 줘 구멍이 드러나므로 클라는 **잃은 것만**
    #                 다시 보낸다. 서버의 누적 수신은 결국 깨끗한 비행과 같고,
    #                 따라서 왕복 수도 그 팔의 정상값 그대로다.
    #      PTO 가지 : 서버가 하나도 못 받았으므로 클라는 **비행 전체**를 다시
    #                 보낸다. 서버의 누적 신용이 사실상 두 배가 되어 그 뒤는
    #                 1 왕복이다. 위 히스토그램의 250~270 봉우리(=50+200.86,
    #                 2-RTT 기준선 103 이 아니라 **1 왕복**)가 그 증거다.
    #    그래서 PTO 가지의 옛 식은 옳고, **ACK 가지만** 고친다.
    #
    #    ⚠️ 맞춘 상수는 하나도 없다. n_rtt_given_ok 는 이미 같은 분포에서
    #       나오는 값이고, 여기서 새로 도입한 수는 없다.
    #
    #    반증 시험(experiments/p20_residual.py 의 84 팔쌍, p17·p18·p15·p16
    #    네 계기 전부): 팔쌍 잔차 |측정Δ - 모형ΔJ| 의 평균이
    #        7.149 ms -> 6.002 ms (-16.1%)  개선 33 · 악화 9 · 무변화 42
    #    악화 9 건은 전부 0.1 ms 미만(J_TIE_MS 의 10 배 안)이다. 한 조건에
    #    맞춘 것이 아니라 **독립인 네 계기에서 같이 좋아진다.**
    #
    #    p=0 이면 p_fail_ack = 0 이라 이 항은 통째로 사라진다 - 헤드라인
    #    (1 바이트 절벽)은 영향받지 않는다. 자체시험 18a 가 그것을 못 박는다.
    n_ok = out["n_rtt_given_ok"]
    # 🩸 2026-08-27 (2) - 실패 가지가 **셋**이다. 판별자와 근거는
    #    last_original_pmf 주석(p7 의 V2/V3/V9 가 96 ms 로 갈린다).
    #    세 가지가 무는 왕복 수도 다르다:
    #      표본 없는 PTO : 아무것도 ACK 안 됐으므로 클라가 **비행 전체**를
    #                      다시 보낸다 -> 서버 신용이 사실상 두 배 -> 1 왕복.
    #      표본 있는 PTO : 앞의 원본은 ACK 됐으므로 **못 받은 것만** 다시
    #                      보낸다 -> 누적 신용이 깨끗한 비행과 같다 -> n_ok.
    #      시간 임계     : 같은 이유로 n_ok.
    t_pto_s = pto_with_rtt_sample_ms(rtt_ms)
    # 🩸 2026-08-29 - **반복 라운드.** 세 가지의 질량은 「한 번이라도 실패할
    #    확률」이고, 옛 식은 거기에 **복구 한 번의 대가**만 곱했다. 재전송이
    #    또 실패하는 경우가 통째로 빠져 있었다.
    #      p18 실측(cert 4032, 버스트 3, 손실 15%, 팔당 9,000 판)에서 실패한
    #      연결의 평균 라운드 수는 m=1 1.76 · m=4 1.24 인데 모형은 전부 1.00.
    #      **오차가 m 에 따라 다르므로 m 비교를 왜곡한다** - 검사 6 이
    #      실측 이득 +31.01 vs 예측 +13.51 (212%) 로 붉어진 것이 이것이다.
    #
    #    expected_rounds 가 GE 사슬에서 유도한다(맞춘 상수 없음). 총 실패
    #    질량 p_fail 회당 평균 (R-1)/p_fail 번의 추가 라운드가 있으므로,
    #    각 가지의 대가에 그 배율을 곱한다. 세 가지의 상대 비율은 안 건드린다
    #    (failFracLookup 이 주는 배분을 그대로 쓴다).
    #
    #    안전판: p=0 이면 R=1 이라 배율 1.0 -> **무손실 실측이 한 톨도 안
    #    움직인다.** 버스트 1 에서는 2 차 항이라 p18 무버스트 조건의 예측
    #    이득이 10.69 -> 10.56 (1.2%) 밖에 안 변한다.
    #    실측 대조: 모형 R / 실측 R = 1.01~1.02 (m=1..4).
    _R = expected_rounds(k, m, p, burst)
    _pf = out["p_fail"]
    _mult = ((_R - 1.0) / _pf) if _pf > 1e-15 else 1.0
    stall = _mult * (out["p_fail_pto"] * (rtt_ms + t_pto)
                     + out["p_fail_pto_sampled"] * (n_ok * rtt_ms + t_pto_s)
                     + out["p_fail_ack"] * (n_ok * rtt_ms + t_ack))
    # 🩸 2026-08-26 (2) - 복구 가지의 직렬화. 대역이 무제한이면 tx_cost_ms 가
    #    0 이므로 **이 항은 통째로 사라지고 옛 식과 비트 단위로 같다**(자체시험
    #    17b). 그래서 무제한에서 이미 검증된 것들은 그대로 남는다 - 이게 이
    #    수리의 안전판이다. 맞춘 상수는 하나도 없다.
    # 🩸 2026-08-28 (2 단계 감사) - 옛 식은
    #        out["p_recovered"] * tx_cost_ms(trailing_parity_bytes(k, m, w), ...)
    #    로 **뒤따르는 패리티 전부**(parity*(m-1))를 복구 가지의 대기시간으로
    #    청구했다. 2 단계의 recovers 는 miss <= c 이므로 복원은 **miss 번째**
    #    패리티에서 끝나고, 그 뒤 것들의 직렬화는 핸드셰이크를 안 늦춘다.
    #      k=2 m=3 p=0.02 2 Mbps: 옛 0.42133 ms vs 옳은 0.21271 ms
    #      (복구 질량의 99.0% 가 miss=1 이라 패리티 하나만 기다린다)
    #    m<=2 는 m-1 == miss 라 값이 같다 - 그래서 자체시험 17a/17b 가
    #    이 결함을 원리적으로 못 봤다.
    tx = (tx_cost_ms(tx_added, uplink_mbps)
          + tx_cost_ms(out["trail_bytes_expected"], uplink_mbps))
    return {
        "j_ms": n_exp * rtt_ms + stall + tx,
        "n_rtt_expected": n_exp,
        "n_rtt_given_ok": out["n_rtt_given_ok"],
        "p_two_rtt": out["p_two_rtt"],
        "client_bytes_real": cb,
        "added_bytes_real": added,
        "allowed_real": quantum.allowed(cb),
        "base_ms": n_exp * rtt_ms,
        "stall_ms": stall,
        "tx_ms": tx,
        "p_fail": pf,
        "p_fail_pto": out["p_fail_pto"],
        "p_fail_pto_sampled": out["p_fail_pto_sampled"],
        "t_pto_sampled_ms": t_pto_s,
        "p_fail_ack": out["p_fail_ack"],
        "t_pto_ms": t_pto,
        "t_ack_ms": t_ack,
    }


# ---------------------------------------------------------------------------
# 자체시험. 출력은 ASCII 로만 한다 - 윈도우 콘솔이 cp949 라 한글이 깨진다.
#
# 여기 있는 검사는 전부 **감사나 실측이 실제로 잡은 결함**을 고정한 것이다.
# 하나라도 붉어지면 그 결함이 되살아난 것이다.
#   1~12  2026-08-20 반증 감사 (결함 4 건)
#   5c~5h 2026-08-20 결정적 소거 실측 (T_recover)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    _fail = [0]
    _n = [0]

    def _chk(name, cond, detail=""):
        mark = "ok  " if cond else "FAIL"
        _n[0] += 1
        if not cond:
            _fail[0] += 1
        print("  [%s] %s%s" % (mark, name, ("  " + detail) if detail else ""))

    # 1. 결합분포가 확률분포인가
    _bad = []
    for k in (1, 2, 3, 4):
        for m in (0, 1, 2):
            for pp in (0.0, 0.01, 0.05, 0.2, 0.5):
                for LL in (1.0, 2.0, 5.0):
                    pm = joint_arrival_pmf(k, m, pp, LL)
                    tot = sum(sum(r) for r in pm)
                    if abs(tot - 1.0) > 1e-9 or any(v < -1e-15
                                                    for r in pm for v in r):
                        _bad.append((k, m, pp, LL, tot))
    _chk("1. joint_arrival_pmf is a distribution", not _bad, str(_bad[:3]))

    # 2. 주변분포가 채널의 erasure_pmf 와 일치하는가.
    worst = 0.0
    for k in (1, 2, 3):
        for m in (0, 1, 2):
            for pp in (0.01, 0.05, 0.2):
                for LL in (1.0, 3.0):
                    pm = joint_arrival_pmf(k, m, pp, LL)
                    got = [0.0] * (k + m + 1)
                    for a_ in range(k + 1):
                        for b_ in range(m + 1):
                            got[(k - a_) + (m - b_)] += pm[a_][b_]
                    ref = erasure_probs(k + m, pp, LL)
                    worst = max(worst,
                                max(abs(got[i] - ref[i])
                                    for i in range(k + m + 1)))
    _chk("2. marginal == afec.channel.erasure_pmf", worst < 1e-12,
         "worst %.3g" % worst)

    # 3. 🩸 2026-08-21. 예전 시험은 `p_fail_of == p_unrecoverable` 이었다.
    #    p_unrecoverable 은 **MDS 가정**(패리티 b 개면 소거 b 개까지 복구)인데
    #    구현은 마지막 패리티 하나로 소거 하나만 복구한다(recovers 주석).
    #    같기를 요구하던 시험이 곧 결함을 고정하고 있었다.
    #
    #    정정판이 요구하는 것 둘:
    #      (a) 구현 규칙이 MDS 보다 **낙관적일 수 없다** (p_fail_of >= MDS)
    #      (b) m=1 에서는 둘이 정확히 같다 (m=1 이면 MDS 도 소거 1 개다)
    #      (c) m=2 에서는 실제로 갈린다 - 안 갈리면 이 시험이 공허하다
    worst_neg = 0.0
    worst_m1 = 0.0
    gap_m2 = 0.0
    for k in (1, 2, 3, 4):
        for m in (1, 2):
            for pp in (0.01, 0.05, 0.2):
                for LL in (1.0, 2.0, 5.0):
                    va = p_fail_of({"k": k, "m": m}, pp, LL)
                    vb = p_unrecoverable(k, m, pp, LL)
                    worst_neg = max(worst_neg, vb - va)      # 음수여야 정상
                    if m == 1:
                        worst_m1 = max(worst_m1, abs(va - vb))
                    else:
                        gap_m2 = max(gap_m2, va - vb)
    _chk("3. p_fail_of >= MDS 하한, m=1 에서는 일치",
         worst_neg < 1e-12 and worst_m1 < 1e-12,
         "MDS 초과 %.3g / m=1 차 %.3g" % (worst_neg, worst_m1))
    _chk("3a. m=2 에서 구현 규칙이 MDS 와 실제로 갈린다 (시험이 공허하지 않다)",
         gap_m2 > 1e-6, "최대 차 %.4g (0 이면 결함이 되살아난 것)" % gap_m2)

    # 3b. 3-지표 분포를 r 로 주변화하면 2-지표 분포와 같아야 한다.
    worst = 0.0
    for k in (1, 2, 3):
        for m in (0, 1, 2):
            for pp in (0.0, 0.05, 0.2):
                for LL in (1.0, 3.0):
                    p3 = joint_arrival_pmf3(k, m, pp, LL)
                    p2 = joint_arrival_pmf(k, m, pp, LL)
                    for a_ in range(k + 1):
                        for b_ in range(m + 1):
                            worst = max(worst,
                                        abs(p3[a_][b_][0] + p3[a_][b_][1]
                                            - p2[a_][b_]))
    _chk("3b. joint_arrival_pmf3 를 r 로 주변화 == joint_arrival_pmf",
         worst < 1e-12, "worst %.3g" % worst)

    # 3c. 실측 고정. p15/p14 가 잰 자리(x25519 k=1, cert 4032, 손실 5%)에서
    #     m=1 의 2-RTT 확률이 **9.5%** 여야 한다. 옛 회계는 4.75% 였고 실측은
    #     9.0%(p15, n=400) / 8.0%(p14, n=200) 였다. 이 수가 다시 반토막 나면
    #     복구 상태의 신용 회계가 되살아난 것이다.
    _s0 = S0_BASE_X25519 + 7 * C_PKT_POLICY_DEFAULT      # 칸 7
    _o = flight_outcome(1, 1, 1280, 0.05, 1.0,
                        n_need_for_flight(4032 + _s0))
    _chk("3c. 복구 상태의 신용 하락이 반영된다 (실측 p15 9.0% / p14 8.0%)",
         abs(_o["p_two_rtt"] - 0.095) < 1e-3,
         "p_two_rtt %.4f (옛 회계는 0.0475)" % _o["p_two_rtt"])

    # 4. 결함 1 - n_rtt 항이 버스트에 반응해야 한다.
    o1 = flight_outcome(2, 1, 1280, 0.05, 1.0, n_need_for_flight(6000.0))
    o5 = flight_outcome(2, 1, 1280, 0.05, 5.0, n_need_for_flight(6000.0))
    _chk("4. n_rtt term reacts to burst (defect 1)",
         abs(o1["n_rtt_expected"] - o5["n_rtt_expected"]) > 1e-6,
         "L=1 %.6f vs L=5 %.6f" % (o1["n_rtt_expected"],
                                   o5["n_rtt_expected"]))

    # 5. 결함 2 - 같은 손실 사건을 두 번 청구하지 않는다.
    o = flight_outcome(1, 0, 1280, 0.2, 1.0, n_need_for_flight(3000.0))
    _chk("5. n-term mass == 1 - p_fail (defect 2)",
         abs(o["p_recoverable"] - 0.8) < 1e-12
         and abs(o["n_rtt_expected"] - 0.8) < 1e-12,
         "n=%.6f p_ok=%.6f" % (o["n_rtt_expected"], o["p_recoverable"]))
    # 5a2. 계약: n_need 없는 후보는 **무엇을 채우라고** 말하며 죽는다.
    #      (2026-08-21 p4 가 이 자리에서 KeyError 로 죽었다)
    try:
        cost_of_v2({"k": 1, "m": 0, "W_eff": 1280,
                    "server_flight": 3000.0}, 1280, 50.0, 0.2, 1.0)
        _chk("5a2. n_need 없는 후보는 거절된다", False, "안 죽었다")
    except KeyError as _ex:
        _chk("5a2. n_need 없는 후보는 거절된다 (안내문 포함)",
             "bin_needed" in str(_ex), str(_ex)[:60])
    e = cost_of_v2({"k": 1, "m": 0, "W_eff": 1280,
                    "server_flight": 3000.0,
                    "n_need": n_need_for_flight(3000.0)},
                   1280, 50.0, 0.2, 1.0, t_recover_ms=50.0,
                   t_recover_ack_ms=50.0)
    # 🩸 2026-08-29 - 옛 검사는 `J == 60.0` 을 못박았다. 그 60 은 **복구
    #    라운드를 한 번만 청구하던 시절의 값**이다. 반복 라운드를 넣으면
    #    65 가 맞다 - 유도가 있다:
    #      k=1 m=0 p=0.2 버스트 1 -> 무기억이므로 R = 1/(1-0.2) = 1.25 (정확)
    #      실패 한 번의 대가 = rtt + T_rec = 50 + 50 = 100
    #      stall = (R-1) x 100 = 0.25 x 100 = 25,  base 40  ->  J = 65
    #    옛 20 은 "재시도가 또 실패할 수 있다"를 안 센 값이다.
    #
    #    이 검사가 원래 막던 것(결함 2: 같은 손실 사건을 왕복 수와 T_recover
    #    로 **두 번** 청구)은 위 검사 5 가 지킨다(n 항 질량 == 1 - p_fail).
    #    여기서는 마법의 수 대신 **식 자체**를 못박는다 - 그래야 다음에
    #    라운드 모형이 또 바뀌어도 이 검사가 옳은 것을 계속 본다.
    _R5 = expected_rounds(1, 0, 0.2, 1.0)
    _exp5 = 40.0 + (_R5 - 1.0) * (50.0 + 50.0)
    _chk("5b. J = base + (R-1)x(rtt+T_rec)  (k=1 m=0 p=0.2, R=1/(1-p) 무기억)",
         abs(_R5 - 1.25) < 1e-12 and abs(e["j_ms"] - _exp5) < 1e-9,
         "R=%.6f J=%.4f 기대 %.4f" % (_R5, e["j_ms"], _exp5))

    # 5c~5h. 2026-08-20 결정적 소거 실측을 고정한다.
    _chk("5c. k=1,m=0 failure is always the PTO branch",
         abs(o["p_fail_pto"] - o["p_fail"]) < 1e-12 and o["p_fail_ack"] == 0.0,
         "pto=%.6f ack=%.6f" % (o["p_fail_pto"], o["p_fail_ack"]))
    o2 = flight_outcome(2, 0, 1280, 0.2, 1.0, n_need_for_flight(3000.0))
    # 🩸 2026-08-27 - 가지가 **셋**이 됐다(last_original_pmf). 이 검사는
    #    "둘로 갈린다"였는데 이제 셋이고, 셋의 합이 p_fail 이어야 한다.
    #    k=2 · m=0 · p=0.2 의 손계산: 둘 다 유실 0.04 / 마지막만 유실
    #    0.8x0.2=0.16 / 마지막은 도착 0.2x0.8=0.16, 합 0.36.
    _s3 = (o2["p_fail_pto"] + o2["p_fail_pto_sampled"] + o2["p_fail_ack"])
    _chk("5d. k=2,m=0 failure splits into three branches (sums to p_fail)",
         o2["p_fail_pto"] > 0 and o2["p_fail_pto_sampled"] > 0
         and o2["p_fail_ack"] > 0
         and abs(_s3 - o2["p_fail"]) < 1e-12
         and abs(o2["p_fail_pto"] - 0.04) < 1e-12
         and abs(o2["p_fail_pto_sampled"] - 0.16) < 1e-12
         and abs(o2["p_fail_ack"] - 0.16) < 1e-12,
         "pto=%.6f sampled=%.6f ack=%.6f fail=%.6f"
         % (o2["p_fail_pto"], o2["p_fail_pto_sampled"], o2["p_fail_ack"],
            o2["p_fail"]))
    # results/probe_trecover.json, RTT 50 ms:
    #   k=1 기준 51.27 -> 소거 252.09 (PTO)   k=2 기준 51.30 -> 소거 109.07 (ACK)
    _chk("5e. PTO branch reproduces measured 252.09 ms",
         abs((51.27 + default_t_recover(50.0, False)) - 252.09) < 0.3,
         "pred %.2f" % (51.27 + default_t_recover(50.0, False)))
    _chk("5f. ACK branch reproduces measured 109.07 ms",
         abs((51.30 + default_t_recover(50.0, True)) - 109.07) < 0.3,
         "pred %.2f" % (51.30 + default_t_recover(50.0, True)))
    _chk("5g. PTO cost is RTT-independent (measured constant)",
         default_t_recover(10.0, False) == default_t_recover(200.0, False),
         "%.2f / %.2f" % (default_t_recover(10.0, False),
                          default_t_recover(200.0, False)))
    _chk("5h. ACK cost scales with RTT",
         default_t_recover(200.0, True) > 3 * default_t_recover(50.0, True),
         "%.2f vs %.2f" % (default_t_recover(50.0, True),
                           default_t_recover(200.0, True)))

    # 6. p=0 이면 예전 결정론 식과 정확히 같아야 한다 (헤드라인 불변)
    _bad = []
    for k in (1, 2, 3):
        for m in (0, 1, 2):
            for sf in (3000.0, 5000.0, 9000.0):
                oo = flight_outcome(k, m, 1280, 0.0, 1.0, n_need_for_flight(sf))
                det = 1.0 if sf <= quantum.allowed(
                    k * 1280 + m * parity_datagram_bytes(1280, k)) else 2.0
                if abs(oo["n_rtt_expected"] - det) > 1e-12 or oo["p_fail"] != 0.0:
                    _bad.append((k, m, sf))
    _chk("6. p=0 reduces to the deterministic rule", not _bad, str(_bad[:3]))

    # 7. 헤드라인 - cert 4000 / 무손실 -> 1 바이트 pad
    r = decide_v2(C=259, cert_bytes=4000, rtt_ms=50.0, p=0.0, burst=1.0,
                  s0_base=396.5, c_pkt=34.5)
    _chk("7. headline: 1-byte pad still chosen",
         r["choice"]["mode"] == "pad" and r["choice"]["delta_per_dgram"] == 1,
         "%s d=%d gain=%.3f" % (r["choice"]["mode"],
                                r["choice"]["delta_per_dgram"], r["gain_ms"]))

    # 8. 결함 4 - 후보의 added_bytes 가 점수와 같은 바이트를 가리키는가
    _bad = []
    for cert in range(2000, 9001, 250):
        r = decide_v2(C=259, cert_bytes=cert, rtt_ms=50.0, p=0.05, burst=1.0,
                      s0_base=396.5, c_pkt=34.5)
        for c in r["candidates"]:
            if c["added_bytes"] != c["added_bytes_real"]:
                _bad.append((cert, c["mode"], c["m"]))
    _chk("8. cand added_bytes == added_bytes_real (defect 4)",
         not _bad, str(_bad[:3]))

    # 9. 결함 4 - levers 의 n_rtt 와 실제 기대 왕복이 무손실에서 일치
    #
    # 🩸 2026-08-26 - **대역 무제한에서** 잰다. levers 의 n_rtt 는 도착한
    #    바이트를 전부 신용으로 세는 결정론 근사이고, 그건 시간 축이 없다.
    #    대역이 걸리면 뒤따르는 패리티의 신용이 송신 결정보다 늦게 닿아
    #    (위 '경주' 절) 둘이 **정당하게** 갈린다 - 자를 늘린 게 아니라
    #    자가 재는 것을 정확히 적은 것이다. 갈리는 자리는 바로 아래 9a 가
    #    따로 못 박는다.
    _bad = []
    for cert in range(2000, 9001, 100):
        r = decide_v2(C=259, cert_bytes=cert, rtt_ms=50.0, p=0.0, burst=1.0,
                      s0_base=396.5, c_pkt=34.5, uplink_mbps=0.0)
        for c in r["candidates"]:
            if abs(c["n_rtt"] - c["n_rtt_expected"]) > 1e-9:
                _bad.append((cert, c["mode"], c["m"]))
    _chk("9. levers n_rtt == expected n_rtt at p=0, uplink 0 (defect 4)",
         not _bad, str(_bad[:3]))

    # 9a. 경주가 무는 자리는 **"앞선 패리티만으로 신용이 차는가"** 하나다
    #
    # ⚠️ 처음에는 "대역이 걸리면 m=1 만 갈린다"로 적었다가 **틀린 것을 확인해
    #    고쳤다.** m>=2 도 앞선 패리티 하나로 칸이 안 차면(큰 cert) 뒤따르는
    #    것의 신용이 필요하고, 그러면 그것도 경주다. 실측에서 m2 가 늘 100%
    #    였던 것은 그 자리가 앞선 하나로 차는 자리였기 때문이지 m>=2 라서가
    #    아니다. 그러므로 자는 m 이 아니라 **칸**으로 재야 한다.
    #
    #   (1) 앞선 패리티만으로 차면  -> 지연이 아무리 커도 1-RTT (결정적)
    #   (2) 원본만으로는 안 차고 뒤따르는 것이 있어야 차면
    #       -> 지연 0 이면 1-RTT, 지연이 크면 2-RTT 로 **간다**
    _bad_lead, _bad_trail, _n1, _n2 = [], [], 0, 0
    for k in (1, 2, 3):
        w_ = 1280
        _par = parity_datagram_bytes(w_, k)
        for m in (1, 2, 3):
            for nn in range(1, 12):
                lead = k * w_ + (_par if m >= 2 else 0)
                allp = k * w_ + m * _par
                n_far = flight_outcome(k, m, w_, 0.0, 1.0, nn,
                                       trail_delay_ms=5.0)["n_rtt_expected"]
                n_near = flight_outcome(k, m, w_, 0.0, 1.0, nn,
                                        trail_delay_ms=0.0)["n_rtt_expected"]
                if quantum.bin_index(lead) >= nn:
                    _n1 += 1
                    if abs(n_far - 1.0) > 1e-12 or abs(n_near - 1.0) > 1e-12:
                        _bad_lead.append((k, m, nn, n_near, n_far))
                elif quantum.bin_index(allp) >= nn:
                    _n2 += 1
                    if abs(n_near - 1.0) > 1e-12 or abs(n_far - 2.0) > 1e-12:
                        _bad_trail.append((k, m, nn, n_near, n_far))
    _chk("9a. race bites exactly where the lead parity alone is not enough",
         (not _bad_lead) and (not _bad_trail) and _n1 > 0 and _n2 > 0,
         ("앞선것만으로 차는 자리 %d 개(어긋남 %s) / 뒤따르는것이 필요한 자리 "
          "%d 개(어긋남 %s)") % (_n1, _bad_lead[:2], _n2, _bad_trail[:2]))

    # 9b. 경주 항은 **대역 무제한에서 아무것도 바꾸지 않는다**
    #
    # 이게 이 수리의 안전판이다. 무제한(d=0)이면 q=1 이라 옛 식과 글자
    # 그대로 같은 값이 나와야 한다 - 그래야 무제한에서 이미 검증된 것들
    # (p4·p16·p18)이 그대로 남는다. 옛 식을 여기 다시 적어 직접 댄다.
    def _old_flight_outcome(k, m, w, p_, burst_, n_need):
        parity = parity_datagram_bytes(w, k)
        pm = joint_arrival_pmf3c(k, m, p_, burst_)
        n_sum = 0.0
        for a_ in range(k + 1):
            for b_ in range(m + 1):
                for r_ in range(recovery_group(k, m) + 1):
                    pr = pm[a_][b_][r_]
                    if pr <= 0.0:
                        continue
                    miss = k - a_
                    rec = recovers(k, a_, r_)
                    if miss > 0 and not rec:
                        continue
                    # 🩸 2026-08-28 - 참조식이 **경주 항만** 격리하도록 맞춘다.
                    #    이 검사의 주장은 「trail_delay=0 이면 경주가 아무것도
                    #    안 바꾼다」이지 「복구 규칙이 안 바뀌었다」가 아니다.
                    #    복구 규칙은 2 단계에서 의도적으로 바뀌었으므로
                    #    (뒤따르는 패리티 c 개로 소거 c 개), 참조식도 같은
                    #    규칙을 써야 두 식이 경주 하나만 두고 갈린다.
                    used = miss if rec else 0
                    arrived = (a_ * w + (b_ - used) * parity + used * w)
                    n_sum += pr * (2.0 if quantum.bin_index(arrived) < n_need
                                   else 1.0)
        return n_sum

    _worst, _bad = 0.0, []
    for k in (1, 2, 3):
        for m in (0, 1, 2, 3):
            for pp in (0.0, 0.02, 0.15):
                for sf in (3000.0, 6000.0, 9000.0):
                    nn = n_need_for_flight(sf)
                    a = flight_outcome(k, m, 1280, pp, 1.0, nn,
                                       trail_delay_ms=0.0)["n_rtt_expected"]
                    b = _old_flight_outcome(k, m, 1280, pp, 1.0, nn)
                    if abs(a - b) > _worst:
                        _worst = abs(a - b)
                    if abs(a - b) > 1e-12:
                        _bad.append((k, m, pp, sf, a, b))
    _chk("9b. trail_delay=0 reproduces the pre-race formula exactly",
         not _bad, "최대 차이 %.3g %s" % (_worst, _bad[:2]))

    # 9c. q(d) 자체의 성질 - 단조 비증가, q(0)=1, 마지막 마디 위는 0
    _xs = [i * 0.01 for i in range(0, 300)]
    _qs = [race_win_prob(x) for x in _xs]
    _mono = all(_qs[i + 1] <= _qs[i] + 1e-12 for i in range(len(_qs) - 1))
    _chk("9c. race_win_prob is monotone, q(0)=1, q(2ms)=0",
         _mono and race_win_prob(0.0) == 1.0 and race_win_prob(2.0) == 0.0,
         "q(0)=%.3f q(0.5)=%.3f q(1)=%.3f q(2)=%.3f"
         % (race_win_prob(0.0), race_win_prob(0.5), race_win_prob(1.0),
            race_win_prob(2.0)))

    # 9d. credit_branches 가 확률분포인가 (질량 1, 바이트 단조)
    # 🩸 2026-08-28 - 인자가 (선행 도착 0/1, 뒤따르는 개수) 로 바뀌었다.
    _bad = []
    for m in (0, 1, 2, 3):
        g = recovery_group(2, m)
        for lead in (0, 1):
            if lead and m < 2:
                continue
            for n_trail in range(0, g + 1):
                for d in (0.0, 0.3, 0.6, 1.5):
                    br = credit_branches(2, 1280, 1332, lead, n_trail, d)
                    tot = sum(x[0] for x in br)
                    if abs(tot - 1.0) > 1e-12 or any(x[0] < 0 for x in br):
                        _bad.append((m, lead, n_trail, d, tot))
    _chk("9d. credit_branches is a distribution", not _bad, str(_bad[:3]))

    # 9e. ⭐ 실측 대조 - 2 Mbps 에서 m=1 이 m=2 보다 **비싸야** 한다
    #
    # 이게 이 수리가 고친 결함 그 자체다. 고치기 전 모형은 m1 을 53.0 ms 로
    # 봐서 최적이라 했는데 실측은 121.3 ms 로 두 번째로 나빴다(오차 68.3).
    # 실측(p17 2026-08-26, cert 9000·k=2·RTT 50·손실 2%·gap 50, 팔당 750):
    #     m0 126.78   m1 121.31   m2 70.36   m3 70.50
    # 즉 **m1 > m2** 이고 m2 ~= m3 이다. 모형도 그 순서를 내야 한다.
    _r2 = decide_v2(C=1450, cert_bytes=9000, rtt_ms=50.0, p=0.02, burst=1.0,
                    s0_base=S0_BASE_MLKEM, c_pkt=C_PKT_POLICY_DEFAULT,
                    W=1280, max_steps=2, uplink_mbps=2.0)
    _j = {c["m"]: c["j_ms"] for c in _r2["candidates"]
          if c["mode"] in ("none", "parity")}
    _chk("9e. 2Mbps: model puts m=1 above m=2 (measured 121.3 vs 70.4)",
         _j.get(1, 0) > _j.get(2, 0) + 20.0 and _r2["choice"]["m"] >= 2,
         "m0=%.2f m1=%.2f m2=%.2f m3=%.2f -> 고른 m=%d"
         % (_j.get(0, -1), _j.get(1, -1), _j.get(2, -1), _j.get(3, -1),
            _r2["choice"]["m"]))

    # 10. 결함 4 - pad_repack 의 추가 바이트를 기준선(k0) 대비로 센다
    r = decide_v2(C=1150, cert_bytes=6000, rtt_ms=50.0, p=0.0, burst=1.0,
                  s0=1734.5, W=1200, allow_repack=True, max_ips=None)
    _k0 = capacity.natural_k(1150, 1200, 51)
    _bad = [(c["mode"], c["added_bytes_real"])
            for c in r["candidates"] if c["mode"] == "pad_repack"
            and c["added_bytes_real"] != max(0, c["client_bytes_real"]
                                             - _k0 * 1200)]
    _chk("10. pad_repack added measured vs baseline k0 (defect 4)",
         not _bad, str(_bad[:2]))

    # 11. 🩸 2026-08-21. 예전 판정은 `gain_ms >= 0` 이었다. **항등이라 실패할 수
    #     없다** - decide_v2 는 base 를 **포함한** 집합에서 최소를 고르므로
    #     gain_ms = J(base) - J(best) >= 0 이 정의상 항상 참이다. 비용식이
    #     난수여도 통과한다. 헤드라인 안전성질("정책은 손해보지 않는다")을
    #     지키는 척만 하고 있었다.
    #
    #     정정판이 지키는 것: **고른 후보가 후보 전부에 대해 실제로 최소인가.**
    #     candidates 를 다시 훑어 J 최소를 독립적으로 구하고, 고른 것이 그
    #     최소에서 J_TIE_MS 안에 있는지 본다(2 단 argmin 의 계약).
    #     이건 argmin 의 항등이 아니라 **_pick_best 의 계약**을 시험한다 -
    #     정렬 키를 망가뜨리면 여기서 붉어진다.
    _bad = []
    _n11 = 0
    for C in (259, 1450):
        for cert in range(1000, 9001, 500):
            for pp in (0.0, 0.05, 0.2):
                for LL in (1.0, 3.0):
                    r = decide_v2(C=C, cert_bytes=cert, rtt_ms=50.0, p=pp,
                                  burst=LL, s0_base=S0_BASE_X25519,
                                  c_pkt=C_PKT_POLICY_DEFAULT)
                    _n11 += 1
                    cs = r["candidates"]
                    jmin = min(c["j_ms"] for c in cs)
                    jsel = r["choice_cost"]["j_ms"]
                    if jsel > jmin + J_TIE_MS + 1e-9:
                        _bad.append((C, cert, pp, LL, jsel - jmin))
                    # 동점 구간 안에서는 **추가 바이트가 최소**여야 한다.
                    tied = [c for c in cs if c["j_ms"] <= jmin + J_TIE_MS]
                    if tied and (r["choice_cost"]["added_bytes_real"]
                                 > min(c["added_bytes_real"] for c in tied)):
                        _bad.append((C, cert, pp, LL, "bytes"))
                    if r["gain_ms"] < -1e-9:
                        _bad.append((C, cert, pp, LL, r["gain_ms"]))
    _chk("11. 고른 후보가 (J 최소 +- 분해능) 이고 그 안에서 바이트 최소",
         not _bad, "%d 조건 / 위반 %s" % (_n11, _bad[:3]))

    # 12. 손실이 커지면 고르는 m 이 줄어들면 안 된다
    _bad = []
    for cert in (3000, 4000, 6000):
        seq = [decide_v2(C=259, cert_bytes=cert, rtt_ms=50.0, p=pp, burst=1.0,
                         s0_base=396.5, c_pkt=34.5)["choice"]["m"]
               for pp in (0.0, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3)]
        if any(seq[i] > seq[i + 1] for i in range(len(seq) - 1)):
            _bad.append((cert, seq))
    _chk("12. chosen m is non-decreasing in p", not _bad, str(_bad[:2]))

    # ---- 13~16b. 단조성 불변식 --------------------------------------
    # 2026-08-21 신설. 이 검사들이 **실제로 결함 셋을 잡아냈다**:
    #   - 결합 후보의 목표 칸을 기준선에서 계산하던 버그 (cert 단조 위반)
    #   - 서버 비행 S 를 전체 도착 기준으로 고정하던 근사 (delta/m 단조 위반)
    #   - for_prior 의 버스트 경계가 1.0 이던 것 (L=1.001 에서 50 배 낙관)
    # 저장소에 이 성질을 지키는 검사가 **하나도 없어서** 셋 다 살아남았다.
    _CERTS = list(range(1000, 14001, 500))
    _GRPS = ((1146, S0_BASE_X25519), (2308, S0_BASE_MLKEM))

    def _cand13(C, cert, s0b, dl, m, k0):
        return quantum._candidate(
            "x", m, dl, C, 1280, 51, 16, cert, None, k0 * 1280,
            quantum.bin_index(k0 * 1280), 1280, k_floor=k0,
            s0_base=s0b, c_pkt=C_PKT_POLICY_DEFAULT,
            parity_bytes=parity_datagram_bytes)

    _bd, _bm, _bc = [], [], []
    for _C, _s0b in _GRPS:
        _k0 = capacity.natural_k(_C, 1280, 51)
        _prevc = None
        for _cert in _CERTS:
            for _m in (0, 1, 2):                       # 13. delta 단조
                _pv = None
                for _dl in range(0, 173, 16):
                    _c = _cand13(_C, _cert, _s0b, _dl, _m, _k0)
                    if _c["W_eff"] > QUICGO_MAX_IPS:
                        break
                    _j = cost_of_v2(_c, 1280, 50.0, 0.05, 1.0, k0=_k0,
                                    uplink_mbps=UPLINK_UNSHAPED)["j_ms"]
                    if _pv is not None and _j > _pv + 1e-9:
                        _bd.append((_C, _cert, _m, _dl))
                    _pv = _j
            for _dl in (0, 1, 81):                     # 14. m 단조
                _pv = None
                for _m in (0, 1, 2):
                    _c = _cand13(_C, _cert, _s0b, _dl, _m, _k0)
                    if _c["W_eff"] > QUICGO_MAX_IPS:
                        continue
                    _j = cost_of_v2(_c, 1280, 50.0, 0.05, 1.0, k0=_k0,
                                    uplink_mbps=UPLINK_UNSHAPED)["j_ms"]
                    if _pv is not None and _j > _pv + 1e-9:
                        _bm.append((_C, _cert, _dl, _m))
                    _pv = _j
            _r = decide_v2(C=_C, cert_bytes=_cert, rtt_ms=50.0, p=0.05,
                           burst=1.0, s0=None, s0_base=_s0b,
                           c_pkt=C_PKT_POLICY_DEFAULT,
                           uplink_mbps=UPLINK_UNSHAPED)
            _v = _r["choice_cost"]["j_ms"]             # 15. cert 단조
            if _prevc is not None and _v < _prevc - 1e-9:
                _bc.append((_C, _cert, round(_prevc, 4), round(_v, 4)))
            _prevc = _v
    _chk("13. 대역 비용 0 에서 delta 를 키우면 J 가 늘지 않는다",
         not _bd, str(_bd[:3]))
    _chk("14. 대역 비용 0 에서 m 을 키우면 J 가 늘지 않는다",
         not _bm, str(_bm[:3]))
    _chk("15. cert 를 키우면 정책의 최적 J 가 줄지 않는다",
         not _bc, str(_bc[:3]))

    # 16. 버스트 단조. **방향이 m 으로 갈리고, 증가 방향은 범위가 있다.**
    #   m = 0 : 복구가 없으므로 '하나라도 잃으면 실패'다. 손실이 뭉치면 같은
    #           손실 질량이 더 적은 비행에 몰려 **전부 깨끗한 비행이 늘어난다**
    #           -> P_fail 이 **줄어야** 한다. 이건 전 범위에서 참이다.
    #   m >= 1: 원본과 패리티를 **같이** 잃어야 실패인데 뭉치면 그 사건이
    #           흔해진다 -> P_fail 이 **늘어야** 한다. 다만 L -> 무한이면
    #           채널이 all-or-nothing 이 되어 P_fail 이 p 로 되돌아온다.
    #           즉 단조가 아니라 **단봉**이다. 직접 확인(k=3, m=1, p=0.2):
    #             L=1.0 0.1808 -> L=3.0 0.2310(정점) -> L=200 0.2010 ~= p
    #           그래서 증가 방향은 **운용 구간**(k<=3, p<=0.05)에서만 단언한다.
    #           그 밖에서 붉어지면 결함이 아니라 물리다 - 범위를 넓히기 전에
    #           이 주석을 먼저 읽을 것.
    _bl = []
    _Ls = (1.0, 1.001, 1.01, 1.05, 1.1, 1.5, 2.0, 3.0, 5.0)
    for _k in (1, 2, 3, 4):
        for _p in (0.002, 0.01, 0.05, 0.1, 0.2, 0.3):
            _row = [p_fail_of({"k": _k, "m": 0}, _p, _L)
                    for _L in _Ls + (50.0,)]
            for _i in range(len(_row) - 1):
                if _row[_i + 1] > _row[_i] + 1e-15:
                    _bl.append(("m0증가", _k, _p))
    for _k in (1, 2, 3):
        for _m in (1, 2):
            for _p in (0.002, 0.005, 0.01, 0.02, 0.03, 0.05):
                _row = [p_fail_of({"k": _k, "m": _m}, _p, _L) for _L in _Ls]
                for _i in range(len(_row) - 1):
                    if _row[_i + 1] < _row[_i] - 1e-15:
                        _bl.append(("m1감소", _k, _m, _p, _Ls[_i + 1]))
    _chk("16. P_fail 버스트 단조 (m=0 전범위 감소 / m>=1 운용구간 증가)",
         not _bl, str(_bl[:3]))
    _j0 = p_fail_of({"k": 1, "m": 1}, 0.05, 1.0)
    _j1 = p_fail_of({"k": 1, "m": 1}, 0.05, 1.001)
    _chk("16a. L=1.0 과 1.001 이 같다 (옛 경계는 50 배 차이가 났다)",
         abs(_j0 - _j1) < 1e-12,
         "L=1.0 %.6e vs L=1.001 %.6e" % (_j0, _j1))
    _sp = (p_fail_of({"k": 2, "m": 1}, 0.05, 5.0)
           - p_fail_of({"k": 2, "m": 1}, 0.05, 1.0))
    _chk("16b. [부정] 버스트가 P_fail 을 실제로 움직인다 (시험이 공허하지 않다)",
         _sp > 1e-3, "k=2 m=1 p=0.05 에서 L 1->5 차이 %.5f" % _sp)

    # --- 17. 복구 가지의 뒤따르는 패리티 직렬화 (2026-08-26 (2) 수리) --------
    def _J(m, up, p, cert=9000):
        d = decide_v2(C=1450, cert_bytes=cert, rtt_ms=50.0, p=p, burst=1.0,
                      s0_base=S0_BASE_MLKEM, c_pkt=C_PKT_POLICY_DEFAULT,
                      W=1280, max_steps=2, m_max=3, uplink_mbps=up)
        return min(c["j_ms"] for c in d["candidates"] if c["m"] == m)

    # 🩸 **안전판**: 대역이 무제한이면 새 항이 통째로 0 이라 옛 식과 같아야
    #    한다. 이게 성립해야 "무제한에서 이미 검증된 것들은 그대로 남는다" 고
    #    말할 수 있다. 새 항을 손으로 빼서 직접 댄다.
    _worst = 0.0
    for _m in (0, 1, 2, 3):
        for _p in (0.0, 0.02, 0.15):
            _o = flight_outcome(2, _m, 1280, _p, 1.0, 9,
                                trail_delay_ms=trailing_parity_delay_ms(
                                    2, 1280, 0.0))
            _extra = tx_cost_ms(_o["trail_bytes_expected"], 0.0)
            _worst = max(_worst, abs(_extra))
    _chk("17a. [안전판] 무제한(대역 0)이면 새 항이 정확히 0 이다 (옛 식과 같다)",
         _worst == 0.0, "최대 추가항 %.3e ms" % _worst)

    # 🩸 [부정] 시험이 공허하지 않다 - 대역이 걸리면 항이 실제로 붙는다.
    _e2 = tx_cost_ms(flight_outcome(
        2, 2, 1280, 0.15, 1.0, 9,
        trail_delay_ms=trailing_parity_delay_ms(2, 1280, 2.0)
    )["trail_bytes_expected"], 2.0)
    _e3 = tx_cost_ms(flight_outcome(
        2, 3, 1280, 0.15, 1.0, 9,
        trail_delay_ms=trailing_parity_delay_ms(2, 1280, 2.0)
    )["trail_bytes_expected"], 2.0)
    _chk("17b. [부정] 2 Mbps 에서는 항이 붙고 m 이 클수록 크다 (공허하지 않다)",
         _e3 > _e2 > 0.1, "m2 %.3f ms < m3 %.3f ms" % (_e2, _e3))

    # 🩸 2026-08-28 (2 단계 감사) - **옛 17c 를 철회한다.**
    #    옛 검사는 「2 Mbps 저손실에서 m3 이 m2 보다 비싸다」(_J 차 > 0)를
    #    못 박고 있었다. 그 결론은 **결함의 산물**이었다 - 복구 가지의 대기
    #    비용을 상수 parity*(m-1) 로 청구해서, m=3 이 실제로는 기다리지 않는
    #    패리티까지 값을 물었다(p=0.02 에서 0.4213 vs 옳은 0.2127 ms).
    #    고치니 부호가 뒤집힌다(-0.148 ms). 옛 결론을 시험으로 못 박아 둔
    #    탓에 **결함이 자기를 지키고 있었다.**
    #
    #    그 자리를 대신할 것은 부호가 아니라 **구조**다: 복구 가지의 대기
    #    비용은 쓰인 패리티 수에 비례해야지 m-1 에 비례해서는 안 된다.
    #    m<=2 는 miss == m-1 == 1 이라 두 식이 같고(위 20b 와 같은 안전판),
    #    m=3 에서만 갈라진다.
    _cst2 = (flight_outcome(2, 2, 1280, 0.02, 1.0, 9,
                            trail_delay_ms=trailing_parity_delay_ms(2, 1280, 2.0))
             ["p_recovered"] * tx_cost_ms(trailing_parity_bytes(2, 2, 1280), 2.0))
    _new2 = _e2_lo = tx_cost_ms(flight_outcome(
        2, 2, 1280, 0.02, 1.0, 9,
        trail_delay_ms=trailing_parity_delay_ms(2, 1280, 2.0)
    )["trail_bytes_expected"], 2.0)
    _cst3 = (flight_outcome(2, 3, 1280, 0.02, 1.0, 9,
                            trail_delay_ms=trailing_parity_delay_ms(2, 1280, 2.0))
             ["p_recovered"] * tx_cost_ms(trailing_parity_bytes(2, 3, 1280), 2.0))
    _new3 = tx_cost_ms(flight_outcome(
        2, 3, 1280, 0.02, 1.0, 9,
        trail_delay_ms=trailing_parity_delay_ms(2, 1280, 2.0)
    )["trail_bytes_expected"], 2.0)
    _chk("17c. [안전판] m<=2 는 옛 상수식과 **비트 단위로 같다**",
         abs(_cst2 - _new2) < 1e-12,
         "m2 상수 %.8f vs 상태별 %.8f" % (_cst2, _new2))
    _chk("17c2. m=3 은 옛 상수식이 **과대**였다 (안 기다리는 패리티까지 청구)",
         _cst3 > _new3 * 1.5,
         "m3 상수 %.5f vs 상태별 %.5f ms (과대 %.5f)"
         % (_cst3, _new3, _cst3 - _new3))

    # 🩸 [부정] 무제한에서는 **부호가 반대**여야 한다. 이게 아니면 위 검사가
    #    대역이 아니라 다른 것을 재고 있다는 뜻이다. 17a 가 무제한에서 새 항이
    #    정확히 0 임을 못 박으므로, 여기 부호는 **옛 식의 부호와 같아야** 한다.
    _du = _J(3, 0.0, 0.02) - _J(2, 0.0, 0.02)
    _chk("17d. [부정] 무제한에서는 m3 이 여전히 싸다 (새 항이 0 이라 옛 식과 같다)",
         _du < 0, "모형 m3-m2 = %+.3f ms" % _du)

    # --- 18. ACK 실패 가지의 왕복 수 (2026-08-27 수리) ---------------------
    #
    # T_recover 는 **기준선 대비 증분**이다. 그러므로 실패 가지의 값은
    # (그 팔의 정상 왕복 수)x RTT + 증분 이어야 한다. 옛 식은 왕복 수를
    # 언제나 1 로 봤다 - 기준선이 2-RTT 인 팔에서 왕복 하나가 통째로 빈다.

    def _cost(m, cert, p, up=0.0, k=2, w=1280):
        d = decide_v2(C=1450, cert_bytes=cert, rtt_ms=50.0, p=p, burst=1.0,
                      s0_base=S0_BASE_MLKEM, c_pkt=C_PKT_POLICY_DEFAULT,
                      W=w, max_steps=2, m_max=max(m, 1), uplink_mbps=up)
        cs = [c for c in d["candidates"]
              if c["m"] == m and c.get("delta_per_dgram", 0) == 0
              and c["mode"] in ("none", "parity")]
        return min(cs, key=lambda e: e["j_ms"])

    # 🩸 **안전판**: 손실이 0 이면 p_fail_ack = 0 이라 이 항이 통째로 사라진다.
    #    헤드라인(1 바이트 절벽)이 무손실 자리라 영향을 안 받는다는 근거다.
    _w18 = 0.0
    for _cert in (3000, 9000, 15000):
        for _m in (0, 1, 2, 3):
            _c = _cost(_m, _cert, 0.0)
            _w18 = max(_w18, _c["p_fail_ack"], _c["p_fail_pto"])
    _chk("18a. [안전판] 무손실이면 실패 가지 질량이 정확히 0 (옛 식과 같다)",
         _w18 == 0.0, "최대 실패 질량 %.3e" % _w18)

    # 🩸 이 수리가 **고치려던 것**. 기준선이 2 왕복인 팔(cert 9000 의 m=0 -
    #    증폭 예산이 모자라 어차피 2-RTT)에서 실패 가지 값이 왕복 하나만큼
    #    올라야 한다. 실측 근거: p17 무제한 손실 15% 의 m=0 히스토그램에서
    #    ACK 가지 봉우리가 **2-RTT 기준선(103 ms) 위에** 얹혀 있다(150~170).
    _c0 = _cost(0, 9000, 0.15)
    _n_ok0 = _c0["n_rtt_given_ok"]
    _gap = _c0["p_fail_ack"] * (_n_ok0 - 1.0) * 50.0
    _chk("18b. 기준선이 2 왕복인 팔은 실패 가지가 왕복 하나만큼 더 든다",
         _n_ok0 > 1.99 and _gap > 5.0,
         "n_rtt|ok = %.3f, 옛 식이 빠뜨리던 양 %.2f ms" % (_n_ok0, _gap))

    # 🩸 [부정] 기준선이 1 왕복인 팔에서는 **아무것도 안 바뀐다.** 이게
    #    아니면 위 검사가 왕복 수가 아니라 다른 것을 재고 있다는 뜻이다.
    _c3 = _cost(3, 9000, 0.15)
    _gap3 = _c3["p_fail_ack"] * (_c3["n_rtt_given_ok"] - 1.0) * 50.0
    _chk("18c. [부정] 기준선이 1 왕복인 팔은 옛 식과 사실상 같다",
         _gap3 < 0.2, "n_rtt|ok = %.3f, 차이 %.3f ms"
         % (_c3["n_rtt_given_ok"], _gap3))

    # 🩸 PTO 가지는 **안 건드렸다.** 비행 전체를 다시 보내 신용이 두 배가
    #    되므로 그 뒤는 1 왕복이고, 실측 봉우리(50+200.86=251)가 그렇게 말한다.
    #    이 검사는 누가 나중에 "대칭이 예쁘다"며 PTO 가지도 바꾸는 것을 막는다.
    _pto_only = _c0["p_fail_pto"] * (50.0 + _c0["t_pto_ms"])
    # 🩸 2026-08-29 - 반복 라운드 배율을 기대식에도 **같이** 넣는다.
    #    이 검사가 보는 것은 **가지별 왕복 수의 구조**(표본 없는 PTO 만
    #    1 왕복, 나머지 둘은 n_ok 왕복)이지 stall 의 절대 크기가 아니다.
    #    배율을 안 넣으면 이 검사가 "구조"가 아니라 "옛 스케일"을 지키게 된다.
    _R18 = expected_rounds(2, 0, 0.15, 1.0)
    _m18 = ((_R18 - 1.0) / _c0["p_fail"]) if _c0["p_fail"] > 1e-15 else 1.0
    _stall_expect = _m18 * (_pto_only
                            + _c0["p_fail_pto_sampled"]
                            * (_n_ok0 * 50.0 + _c0["t_pto_sampled_ms"])
                            + _c0["p_fail_ack"]
                            * (_n_ok0 * 50.0 + _c0["t_ack_ms"]))
    _chk("18d. 표본 없는 PTO 가지만 1 왕복 (나머지 둘은 n_ok 왕복)",
         abs(_c0["stall_ms"] - _stall_expect) < 1e-9,
         "stall %.6f vs 기대 %.6f" % (_c0["stall_ms"], _stall_expect))

    # --- 19. 마지막 원본 판별자 (2026-08-27 수리) ---------------------------
    #
    # p7 의 V2/V3 은 옛 모형에서 **같은 상태**였는데 실측이 96.3 ms 갈렸다.
    # 이 검사들은 그 수리가 되살아나 사라지지 않도록 못 박는다.

    # 🩸 **안전판**: 새 분포는 같은 DP 의 다른 주변화이므로 실패 질량의
    #    합이 옛 p_fail 과 **비트 단위로** 같아야 한다. 이게 깨지면 회계가
    #    두 군데로 갈라진 것이다.
    _w19 = 0.0
    for _k in (1, 2, 3, 4):
        for _m in (0, 1, 2, 3):
            for _p in (0.0, 0.02, 0.15, 0.3):
                for _L in (1.0, 3.0):
                    _o = flight_outcome(_k, _m, 1280, _p, _L, 9)
                    _w19 = max(_w19, abs(_o["p_fail_pto"]
                                         + _o["p_fail_pto_sampled"]
                                         + _o["p_fail_ack"] - _o["p_fail"]))
    _chk("19a. [안전판] 세 가지의 합 == p_fail (분포가 안 갈라졌다)",
         _w19 < 1e-12, "최대 차이 %.3e" % _w19)

    # 🩸 이 수리가 **고치려던 것**: 마지막 원본이 도착했는지로 갈린다.
    #    k=2·m=0 은 두 원본 중 하나만 잃는 두 경우가 정확히 대칭이므로
    #    (p(1-p) 씩) 옛 규칙에서는 **둘 다 ACK 가지**였다.
    #    ⚠️ k=2 로는 이 검사를 세울 수 없다 - 두 가지 질량이 둘 다
    #       p(1-p)=0.16 으로 **같아서**, 판별자를 통째로 뒤집어도 검사가
    #       통과한다(감사 2026-08-27 이 지적). k=3 을 쓰면 셋이 전부
    #       갈린다. 손계산(p=0.2, 독립):
    #         아무것도 없음      0.2^3            = 0.008
    #         마지막만 유실      0.2(1 - 0.2^2)   = 0.192
    #         마지막은 도착      0.8(1 - 0.8^2)   = 0.288
    #         합 0.488 = 1 - 0.8^3  ✓
    _fs = fail_split(3, 0, 0.2, 1.0)
    _chk("19b. 마지막 원본 유실이 ACK 가지가 아니라 PTO 가지로 간다",
         abs(_fs[0] - 0.008) < 1e-12 and abs(_fs[1] - 0.192) < 1e-12
         and abs(_fs[2] - 0.288) < 1e-12,
         "표본없는PTO %.4f / 표본있는PTO %.4f / 시간임계 %.4f" % _fs)

    # 🩸 [부정] k=1 에서는 **아무것도 안 바뀐다** - 원본이 하나뿐이라
    #    "마지막 원본 유실"과 "아무것도 없음"이 같은 사건이다. 이게 아니면
    #    위 검사가 마지막 원본이 아니라 다른 것을 재고 있다는 뜻이다.
    _fs1 = fail_split(1, 0, 0.2, 1.0)
    _chk("19c. [부정] k=1 에서는 세 번째 가지가 비어 있다 (사건이 같다)",
         _fs1[1] == 0.0 and _fs1[2] == 0.0 and abs(_fs1[0] - 0.2) < 1e-12,
         "표본없는PTO %.4f / 표본있는PTO %.4f / 시간임계 %.4f" % _fs1)

    # 🩸 p7 의 세 모드를 모형이 실제로 재현하는지 - 값으로 못 박는다.
    #    (기준선 1 왕복, RTT 50, k=2.)
    # 🩸 2026-09-07 - 실측 증분을 **원자료에서 읽는다.** 그전에는 58.2 / 154.5
    #    / 200.6 이 박혀 있었는데 그건 08-2x 판이고 08-30 재측정은 58.6 / 152.6
    #    / 201.6 이다(한도 10 ms 라 통과는 했지만 「실측」이라 적힌 수가 실측이
    #    아니었다). results/p7_verify.json 이 있으면 거기서 V1(기준선)·V2·V3·V9
    #    의 p50 을 읽고, 없으면 마지막으로 읽은 값을 쓰되 그 사실을 찍는다.
    #    ⚠️ 여기서 results/*.json 을 **읽지 않는다.** padfec/ 는 파일·네트워크를
    #    안 만진다는 격리 전제가 있고 verify.py 의 발자국 시험이 그것을 지킨다
    #    (2026-09-08 에 실제로 붉어졌다). 원자료와의 대조는 원자료를 읽는 자리인
    #    p19_provenance.py 가 한다(「T_recover 상수가 p7 원자료를 재현」 검사).
    #    아래 내장값은 results/p7_verify.json 2026-08-30 판, V1 51.591 기준 p50
    #    증분이다. p7 이 다시 돌면 p19 가 새 값으로 대조한다.
    _p7_meas = {"V2": 58.6, "V3": 152.6, "V9": 201.6}
    _p7_src = "내장값(08-30 판, p19 가 원자료와 대조)"
    _p7 = [("V2 마지막 원본 도착", default_t_recover(50.0, True), _p7_meas["V2"]),
           ("V3 마지막 원본 유실", pto_with_rtt_sample_ms(50.0), _p7_meas["V3"]),
           ("V9 아무것도 없음", default_t_recover(50.0, False), _p7_meas["V9"])]
    _worst7 = max(abs(mo - me) for _, mo, me in _p7)
    _chk("19d. p7 결정적 소거 세 모드를 10 ms 안에서 재현한다 (%s)" % _p7_src,
         _worst7 < 10.0,
         " | ".join("%s 모형 %.1f vs 실측 %.1f" % (n, mo, me)
                    for n, mo, me in _p7))

    # --- 20. 다중 소거 복구 (2026-08-28, 2 단계) ---------------------------
    #
    # 신레오 2026-08-27 보고: 구현이 소거를 하나만 복구했다. 부호(Cauchy)는
    # 어느 정방 부분행렬도 가역이라 e 개를 풀 수 있는데, recoverOne 이 소거를
    # 정수 하나로만 받았기 때문이었다. 구현을 recoverMany 로 바꿨고 모형이
    # 따라간다. 여기서 그 규칙을 못 박는다.

    # 🩸 **안전판 1**: 새 분포를 c 로 주변화하면 옛 분포와 같아야 한다.
    _w20 = 0.0
    for _k in (1, 2, 3, 4):
        for _m in (0, 1, 2, 3, 4):
            for _p in (0.0, 0.02, 0.15, 0.3):
                for _L in (1.0, 3.0):
                    _a = joint_arrival_pmf3c(_k, _m, _p, _L)
                    _b = joint_arrival_pmf(_k, _m, _p, _L)
                    for _i in range(_k + 1):
                        for _j in range(_m + 1):
                            _w20 = max(_w20, abs(sum(_a[_i][_j]) - _b[_i][_j]))
    _chk("20a. [안전판] 새 분포를 c 로 주변화 == joint_arrival_pmf",
         _w20 < 1e-12, "최대 차이 %.3e" % _w20)

    # 🩸 **안전판 2**: g=1 인 자리(m<=2)에서는 옛 분포와 **비트 단위로** 같다.
    #    즉 이 변경은 m>=3 에서만 무언가를 바꾼다 - m<=2 로 얻은 기존 실측은
    #    한 점도 흔들리지 않는다.
    # m=0 은 패리티가 없어 축이 퇴화한다(g=0 vs 옛 판의 길이 2). 뺀다.
    _w20b = 0.0
    for _k in (1, 2, 3, 4):
        for _m in (1, 2):
            for _p in (0.0, 0.02, 0.15, 0.3):
                for _L in (1.0, 3.0):
                    _a = joint_arrival_pmf3c(_k, _m, _p, _L)
                    _o = joint_arrival_pmf3(_k, _m, _p, _L)
                    for _i in range(_k + 1):
                        for _j in range(_m + 1):
                            for _r in range(len(_o[_i][_j])):
                                _w20b = max(_w20b,
                                            abs(_a[_i][_j][_r]
                                                - _o[_i][_j][_r]))
    _chk("20b. [안전판] m<=2 는 옛 분포와 비트 단위로 같다 (기존 실측 불변)",
         _w20b == 0.0, "최대 차이 %.3e" % _w20b)

    # 🩸 이 수리가 **고치려던 것**: m=3 이 처음으로 m=2 보다 안전해진다.
    #    그전에는 m=1·2·3 의 P_fail 이 **완전히 같았다**(복구가 1 개로 묶여
    #    있었으므로). 그래서 정책이 m>=3 을 고를 보호 목적의 이유가 없었다 -
    #    저장소의 미해결 질문 A-7 이 그것이다.
    _f1 = p_fail_of({"k": 2, "m": 1}, 0.15, 1.0)
    _f2 = p_fail_of({"k": 2, "m": 2}, 0.15, 1.0)
    _f3 = p_fail_of({"k": 2, "m": 3}, 0.15, 1.0)
    _chk("20c. m=3 이 m=2 보다 실제로 안전하다 (m<=2 는 여전히 같다)",
         abs(_f1 - _f2) < 1e-15 and _f3 < _f2 * 0.5,
         "k=2 p=0.15  m1 %.5f = m2 %.5f > m3 %.5f (%.1f 배)"
         % (_f1, _f2, _f3, _f2 / _f3 if _f3 > 0 else float("inf")))

    # 🩸 [부정] 복구 능력은 **뒤따르는 패리티 수**로 묶인다. 선행 패리티는
    #    신용 전용이라 복구에 못 쓴다 - 그래서 m=2 는 소거 2 개를 못 고친다.
    #    신레오님의 m=2 팔이 이 설계로도 여전히 실패하는 이유이고, 결함이
    #    아니라 대가다. 이게 무너지면 신용 회계가 깨진 것이다.
    # --- 21. 반복 라운드 (2026-08-29 신설) ---------------------------------
    #
    # 이 항은 **우리에게 유리한 방향**이다(m 의 값이 커진다). 그래서 안전판을
    # 남보다 촘촘히 건다. 판정자로 p18 검사 6 을 쓰지 않는다 - 그건 결과다.
    _r21 = [expected_rounds(k, m, 0.0, L)
            for k in (1, 2, 3) for m in (0, 1, 2, 3) for L in (1.0, 3.0, 5.0)]
    _chk("21a. [안전판] 무손실이면 R 이 **정확히** 1.0 (옛 실측 불변)",
         all(x == 1.0 for x in _r21), "최대 %.17g" % max(_r21))

    # 첫 라운드의 실패 질량은 p_fail_of 와 같아야 한다 - 두 곳이 갈라지면
    # 회계가 두 세계로 나뉜다(2026-08-20 결함 1 과 같은 형태).
    _w21 = 0.0
    for _k in (1, 2, 3):
        for _m in (0, 1, 2, 3):
            for _p in (0.02, 0.15, 0.25):
                for _L in (1.0, 3.0, 5.0):
                    _st = _joint3c_state(_k, _m, _p, _L)
                    _f = sum(_st[_s][_a][_b][_c]
                             for _s in (0, 1) for _a in range(_k + 1)
                             for _b in range(_m + 1)
                             for _c in range(len(_st[0][_a][_b]))
                             if (_k - _a) > _c)
                    _w21 = max(_w21, abs(_f - p_fail_of({"k": _k, "m": _m},
                                                        _p, _L)))
    _chk("21b. [안전판] 첫 라운드 실패 질량 == p_fail_of (회계가 안 갈라진다)",
         _w21 < 1e-12, "최대 차이 %.3e" % _w21)

    # 무기억(버스트 1, m=0)에서는 정확히 기하급수여야 한다. 유도가 맞는지
    # 닫힌 형태로 대조한다 - 여기가 어긋나면 상태 이어받기가 틀린 것이다.
    _w21c = 0.0
    for _p in (0.02, 0.05, 0.15, 0.25):
        _got = expected_rounds(1, 0, _p, 1.0)
        _w21c = max(_w21c, abs(_got - 1.0 / (1.0 - _p)))
    _chk("21c. [안전판] k=1 m=0 버스트1 은 정확히 1/(1-p) (무기억 닫힌해)",
         _w21c < 1e-9, "최대 차이 %.3e" % _w21c)

    # [부정] 버스트가 R 을 실제로 움직여야 한다. 안 움직이면 이 항 전체가
    # 공허하다(무기억이면 굳이 상태를 이어받을 이유가 없다).
    _r1 = expected_rounds(2, 1, 0.15, 1.0)
    _r5 = expected_rounds(2, 1, 0.15, 5.0)
    _chk("21d. [부정] 버스트가 R 을 키운다 (상태 이어받기가 공허하지 않다)",
         _r5 > _r1 * 1.15,
         "L=1 %.5f -> L=5 %.5f (%.2f 배)" % (_r1, _r5, _r5 / _r1))

    # R 은 m 에 단조 비증가여야 한다(패리티가 늘면 라운드가 준다).
    _bad21 = []
    for _k in (1, 2, 3):
        for _L in (1.0, 3.0, 5.0):
            _v = [expected_rounds(_k, _m, 0.15, _L) for _m in range(4)]
            if any(_v[i] < _v[i + 1] - 1e-12 for i in range(3)):
                _bad21.append((_k, _L, [round(x, 5) for x in _v]))
    _chk("21e. R 이 m 에 단조 비증가", not _bad21, str(_bad21[:2]))

    _chk("20d. [부정] 소거 e 개는 뒤따르는 패리티 e 개가 있어야만 풀린다",
         recovery_group(2, 2) == 1 and recovery_group(2, 3) == 2
         and not recovers(2, 0, 1) and recovers(2, 0, 2),
         "g(m=2)=%d g(m=3)=%d | 소거2·패리티1 -> %s, 소거2·패리티2 -> %s"
         % (recovery_group(2, 2), recovery_group(2, 3),
            recovers(2, 0, 1), recovers(2, 0, 2)))

    print("")
    print("%d checks, %d failed" % (_n[0], _fail[0]))
    sys.exit(1 if _fail[0] else 0)
