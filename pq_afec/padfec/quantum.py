# -*- coding: utf-8 -*-
"""양자 지렛대 - 증폭 허용량이 1,280 B 계단이라는 사실의 산술.

정본: `docs/PADFEC v2 명세.md` §1~§3. 이 파일은 그 문서의 수식을 코드로
옮긴 것이고, 문서와 어긋나면 **문서가 옳다**.

무엇이 계단인가
----------------
RFC 9000 §8.1 은 서버가 받은 바이트의 3배까지만 보내게 한다. 그런데
quic-go 의 `isAmplificationLimited()` 는 패킷을 **만들기 전에만**
`bytesSent >= 3*bytesReceived` 를 보는 불리언 게이트다. 예산이 1 바이트라도
남아 있으면 패킷 하나(P = 1,280 B)를 통째로 더 내보낸다. 그래서 실제 허용량은

    A(B) = ceil(3B/P) * P

이고, 이건 3B 를 **위로** 넘는 첫 P 배수다. 명세 §5 가 적어둔 대로 이건
규격 위반이며(RFC 9000 은 예외 없는 MUST NOT), 우리 설계는 그 위반에
기대고 있다. 그 점을 숨기지 않는다.

따름정리 - 기본값이 최악이다
-----------------------------
`W = 1280 = P` 이면 `B = k*1280` 이므로 `3B = 3k*1280` 은 **항상 P 의 배수**다.
따라서 `A(B) = 3B` 이고 `delta_min = 1` — k 와 무관하다. quic-go 클라이언트는
기본 설정에서 증폭 양자 경계에 **정확히 걸터앉아** 있다. 1 바이트만 더 보내면
서버 예산이 1,280 B 늘어난다. 이것이 얻을 수 있는 최대 낭비다.

정수 산술만 쓰는 이유 (측정해서 적는다)
----------------------------------------
나눗셈을 전부 `//` 와 올림 정수식으로만 한다. 다만 그 근거를 과장하지 않는다 —
**측정해 보니 실사용 구간에서는 부동소수도 같은 답을 냈다.**
`floor(A/3 - B) + 1` 을 float 로 계산해 정수식과 대조한 **결과만** 적는다.

    B = 1,200..300,000 전 구간         불일치 0 건
    B ~ 10^9 / 10^12 / 10^15           불일치 0 건
       (3B mod P == 0 인 퇴화 점과 3B mod P != 0 인 점을 함께 넣어 확인)

QUIC 첫 비행이 닿을 수 있는 크기에서는 갈라지지 않는다. 갈라지기 시작하는
자리는 대략 **2^51 대역**이다 — 옥타브마다 무작위 20 만 표본을 뽑으면
2^40..2^50 은 0 건, [2^51, 2^52) 에서 처음 나온다(56 건, 씨앗에 따라 개수는
조금 달라진다). 그리고 거기서 float 은 1 씩 어긋나기만 하는 게 아니라
**0 을 돌려 "반환 >= 1" 불변식을 깬다.**

    B = 3,753,141,324,338,347  ->  float 0,   정수식 427   (불변식 위반)
    B = 4,503,599,627,370,496  ->  float 172, 정수식 171
    B = 2^53                   ->  float 343, 정수식 342

주의 - 이 파일의 이전 판이 적었던 **"처음 갈라지는 지점은 B = 2^53"** 은 틀렸다.
2^53 은 최초 분기점이 아니라 그보다 약 4 배 큰 값이다. 자체시험 10b 는
2^53 **한 점만** 보므로 '처음'인지 '거기서만'인지를 시험한 적이 없다 —
이름도 그에 맞게 고쳤다.

그러므로 정수식의 값어치는 "float 이 틀린다"가 아니라 **틀릴 수 있는지를
따질 필요 자체를 없앤다**는 데 있다. Δ_min = 1 이 이 연구의 헤드라인이라
1 바이트가 결론을 바꾸는 만큼, 논증에 가정을 하나라도 덜 싣는 쪽을 고른다.
자체시험 10 이 이 대조를 매번 다시 돌린다.

on_boundary 의 정직한 한계
---------------------------
`on_boundary` 는 명세대로 "3B 가 P 의 배수인가"로 정의한다. 이것이 참이면
`delta_min == 1` 이지만 **역은 성립하지 않는다.** A(B) - 3B = P - (3B mod P)
이므로 3B mod P 가 P-1 또는 P-2 여도 delta_min 은 1 이 된다
(P=1280 에서 B ≡ 853 또는 426 (mod 1280)). 자체시험이 그 개수를 세어
INFO 로 보고한다. 우리가 다루는 B = k*W (W >= 1200) 에서는 실제로 잘
닿지 않지만, "배수 = 최악점"이라고 단정하면 그건 거짓이다.

s0 는 상수가 아니다 - 서버 패킷 수 항 (명세 §2.5)
--------------------------------------------------
서버 첫 비행은 **인증서 + 고정분 + (서버 패킷 수 x 패킷 오버헤드)** 다.

    s0(n) = s0_base + n*c ,   n = A(B)/P ,   c = 34.5 B
    s0_base:  x25519 396.5 ,  X25519MLKEM768 1527.5
    임계(B)  = A(B) - s0_base - (A(B)/P)*c

칸이 올라가면 서버가 패킷을 하나 더 쓰므로 s0 도 그만큼 커진다. 상수 s0 를
쓰면 높은 칸에서 임계를 **과대예측**한다(기존 8개 팔 대조: 평균절대오차
114.6 B vs 패킷항 20.2 B). `s0_at()` 과 `threshold()` 가 이 식이고,
`levers(..., s0_base=, c_pkt=)` 로 켠다. 안 켜면 호출자가 준 상수 s0 를
그대로 쓴다(하위호환).

c 의 정본값은 아직 하나로 못 박지 못한다 (2026-08-20 직접 측정)
----------------------------------------------------------------
`results/probe_s0_x25519.json` · `results/probe_s0_X25519MLKEM768.json` 이
임계를 거치지 않고 **서버 바이트를 직접 세서** 패킷항을 확인했다.
상수 s0 모형은 **기각된다.**

    방법                        x25519    X25519MLKEM768
    임계 역산(원래 34.5)          34.5          34.5
    서버 바이트 직접 계수         36.1          40.0     <- 직접 측정
    상수 모형 평균절대오차       224.5         144.2
    패킷항  평균절대오차         112.4         101.8

따라서 `c` 는 아직 **34.5 ~ 40.0 구간**으로만 정해진다. 이 파일의 기본값과
자체시험은 명세가 아직 쓰는 **34.5** 를 그대로 유지한다 — 상수를 바꾸는 것은
명세를 고친 뒤의 일이다. 절편끼리는 비교하면 안 된다(`server_bytes` 에
ACK·HANDSHAKE_DONE·NewSessionTicket 꼬리가 섞인다). **기울기만** 비교 가능하다.

주의 - **1 바이트 절벽은 이 두 모형을 구분하지 못한다.** 상수 s0 모형도 절벽
10 점을 똑같이 맞힌다(자체시험 5e). 절벽이 증명하는 것은 *양자화*이지
*패킷항*이 아니다. 두 모형을 실제로 가르는 것은 자체시험 5c2(높은 칸에서
상수 모형이 측정 밴드를 벗어난다)와 위의 직접 측정이다. 명세 §8 이 계획했던
`p12c`(ips 1707·2134)는 **영구히 불가능**하다 — quic-go 가
`InitialPacketSize` 를 1452 로 깎는다. 자체시험 5d 는 그 예측식을 재현할 뿐
**측정이 아니다.**

k 는 후보 안에서 무너지면 안 된다
----------------------------------
pad 후보는 기준선의 `k0 = natural_k(C, W_base, h)` 를 **유지한다**. W 를 키울 때
k 를 다시 계산하면 k 가 줄어(2->1) 비행이 오히려 작아지고 **칸이 내려간다** -
δ 로 칸을 올리는 후보, 즉 이 연구의 헤드라인 지렛대가 후보 집합에서 통째로
사라진다. 기준선이 이미 k0 개를 보내고 있으므로 각각을 δ 만큼 키우는 데는
재패킹이 필요 없다. 붕괴판을 보고 싶으면 `pad_repack` 이라는 **별도 후보**로
함께 돌려준다(대체가 아니다). 자체시험 9 가 스윕으로 그 규모를 직접 센다.

배치 의존성 (명세 §2.6 - 아직 가설)
------------------------------------
m=1 배치는 `[원본…, 패리티]` 라 k=1 이면 패리티가 **서버 결정 뒤에** 도착해
신용을 못 살 수 있다(x25519 on1 팔의 실측 초과 936 B). 후보 dict 에
`late_parity_risk` 로 **표시만** 하고 신용 계산은 아직 바꾸지 않는다 -
p13 이 B_eff 를 직접 재기 전까지는 가설이기 때문이다. `credit_bytes` 가
지금 신용 계산에 들어가는 바이트다(현재는 client_bytes 와 같다).

기호는 명세 §1 과 같다.
    C  ClientHello CRYPTO 총 바이트      W  데이터그램 하나의 와이어 크기
    k  첫 비행 데이터그램 수             B  첫 비행 총 바이트 = k*W (p1 12/12 실측)
    P  서버 패킷 크기(quic-go 1280)      A(B) 주소 검증 전 서버 허용량
    S  서버 첫 비행 = cert + s0
"""
from __future__ import annotations

try:                                    # 패키지로 임포트될 때
    from . import capacity
except ImportError:                     # `python padfec/quantum.py` 로 직접 실행할 때
    import os as _os
    import sys as _sys

    _sys.path.insert(
        0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from padfec import capacity         # noqa: E402

# quic-go 서버가 한 번에 내보내는 패킷 크기. amplif.SERVER_PACKET_SIZE 와 같은 값이며
# 자체시험이 두 모듈의 allowed 계산이 갈라지지 않는지 전 구간에서 대조한다.
P_SERVER = 1280

# RFC 9000 §8.1 - 주소 검증 전 증폭 상한 배수.
AMP = 3

# 전형적인 이더넷 MTU. 이보다 큰 데이터그램은 경로에서 조각나거나 버려질 수
# 있으므로 후보에 `over_mtu` 로 표시한다(계산에서 배제하지는 않는다 -
# 실험실 경로에서는 실제로 보낼 수 있고, 판단은 호출자 몫이다).
TYPICAL_MTU = 1500


def _ceil_div(a, b):
    """올림 나눗셈. 부동소수를 거치지 않는다."""
    if b <= 0:
        raise ValueError("나눗수는 양수여야 한다: %r" % (b,))
    return -((-a) // b)


def _require_int(name, value):
    """정수만 받는다. bool 은 int 의 하위형이지만 여기서는 거부한다.

    바이트 수에 float 가 섞이면 `//` 가 조용히 float 를 돌려주고 경계에서
    1 바이트가 어긋난다. Δ_min = 1 이 이 연구의 헤드라인이라 그 1 바이트가
    결론을 바꾼다 - 그래서 입구에서 막는다.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("%s 는 정수여야 한다: %r" % (name, value))
    return value


def allowed(client_bytes, pkt=P_SERVER):
    """A(B) = ceil(3B/pkt)*pkt — 주소 검증 전 서버가 실제로 내보낼 수 있는 바이트.

    예산 3B 그 자체가 아니라 **예산을 넘어서는 첫 패킷 경계**다.
    client_bytes <= 0 이면 0. pkt <= 0 이면 양자화 없이 3B (amplif 와 같은 규약).
    """
    if client_bytes <= 0:
        return 0
    if pkt <= 0:
        return AMP * client_bytes
    return _ceil_div(AMP * client_bytes, pkt) * pkt


def bin_index(client_bytes, pkt=P_SERVER):
    """ceil(3B/pkt) — 이 비행이 들어앉은 양자 칸 번호. 빈 비행은 0 번 칸."""
    if pkt <= 0:
        raise ValueError("pkt <= 0 이면 칸이 정의되지 않는다")
    if client_bytes <= 0:
        return 0
    return _ceil_div(AMP * client_bytes, pkt)


def delta_min(client_bytes, steps=1, pkt=P_SERVER):
    """지금 칸에서 steps 칸 위로 올라가는 최소 추가 바이트 (명세 보조정리 2).

        Δ_min = floor(A_target/3 - B) + 1,   A_target = A(B) + (steps-1)*pkt

    steps 칸 위에 들어가려면 3(B+Δ) > A_target 이어야 한다. 정수이므로 위 식이고,
    여기서는 `(A_target - 3B)//3 + 1` 로 정수만 써서 계산한다. 근거는 모듈
    머리말과 같다 — **측정해 보니 실사용 구간에서는 float 도 같은 답을 냈다**
    (B = 1,200..300,000 과 10^9·10^12·10^15 대역에서 불일치 0 건). 갈라지기
    시작하는 자리는 대략 2^51 대역이고, 거기서 float 은 0 을 돌려 이 함수의
    "반환 >= 1" 불변식을 깬다(머리말의 반례 표 참고). 정수식의 값어치는
    "float 이 틀린다"가 아니라 틀릴 수 있는지를 따질 필요 자체를 없앤다는
    데 있다. 자체시험 10 이 매번 재확인한다.

    steps <= 0 이면 0. 반환값은 항상 >= 1 이다(A_target >= 3B 이므로).
    """
    _require_int("client_bytes", client_bytes)
    _require_int("steps", steps)
    _require_int("pkt", pkt)
    if steps <= 0:
        return 0
    if pkt <= 0:
        raise ValueError("pkt <= 0 이면 칸이 정의되지 않는다")
    b = client_bytes if client_bytes > 0 else 0
    target = (bin_index(b, pkt) + steps - 1) * pkt
    return (target - AMP * b) // AMP + 1


def boundary_W(k, W, steps=1, pkt=P_SERVER):
    """k 개 데이터그램일 때 steps 칸 올리려면 데이터그램 크기를 얼마로 키워야 하나.

        boundary_W = W + ceil(delta_min(k*W, steps) / k)

    부족한 Δ 를 k 개 데이터그램에 고르게 나눠 싣는다. k 로 나누어떨어지지 않으면
    올림이므로 실제 추가분은 Δ 보다 최대 k-1 바이트 많다.

    명세 §2 실측 대조: `boundary_W(1, 1200) = 1281` 과 `boundary_W(1, 1280) = 1281`
    이 같은 점을 가리킨다. 서로 다른 두 계산이 한 점에서 만나는 것이 이 모형의
    반증 지점이다(빗나가면 모형이 틀린 것이다).
    """
    if k <= 0:
        raise ValueError("k 는 1 이상이어야 한다: %r" % (k,))
    if steps <= 0:
        return W
    return W + _ceil_div(delta_min(k * W, steps, pkt), k)


def on_boundary(client_bytes, pkt=P_SERVER):
    """3B 가 pkt 의 배수인가 = 최악의 자리에 걸터앉아 있는가.

    **`on_boundary(B)` 와 `delta_min(B) == 1` 은 동치가 아니다.** 참이면
    A(B) = 3B 이므로 delta_min == 1 이지만, 역은 성립하지 않는다:
    A(B) - 3B = pkt - (3B mod pkt) 이므로 `3B mod pkt` 가 pkt-1 또는 pkt-2 여도
    delta_min 은 1 이다. P = 1280 에서 그건 **B ≡ 426 또는 853 (mod 1280)** 이고,
    이 두 잉여류는 on_boundary 가 False 인데도 1 바이트면 칸이 올라간다.
    (자체시험 6 이 그 개수를 세어 INFO 로 보고한다.)

    빈 비행(B <= 0)은 판정 대상이 아니므로 False.
    """
    if pkt <= 0:
        raise ValueError("pkt <= 0 이면 경계가 정의되지 않는다")
    if client_bytes <= 0:
        return False
    return (AMP * client_bytes) % pkt == 0


def s0_at(bin_n, s0_base, c_pkt):
    """s0(n) = s0_base + n*c — 칸 n 에서의 서버 첫 비행 고정분 (명세 §2.5).

    s0 는 상수가 아니다. 칸이 올라가면 서버가 패킷을 하나 더 쓰므로 그 패킷의
    오버헤드 c 만큼 s0 도 커진다. 실측(명세 §2.5 표):

        s0_at(3, 396.5, 34.5)  == 500.0     x25519,          A = 3,840
        s0_at(4, 396.5, 34.5)  == 534.5     x25519,          A = 5,120
        s0_at(6, 1527.5, 34.5) == 1734.5    X25519MLKEM768,  A = 7,680
        s0_at(7, 1527.5, 34.5) == 1769.0    X25519MLKEM768,  A = 8,960

    두 그룹이 **독립적으로 같은 c = 34.5** 를 줬다. 다만 정직하게: 그룹당 2점,
    그것도 폭 ~56 B 이분탐색 구간의 중점에서 나온 값이라 불확실성이 크다
    (±40 B 수준). 확정은 p12c(ips 1707·2134)가 한다.
    """
    if bin_n < 0:
        raise ValueError("칸 번호는 음수일 수 없다: %r" % (bin_n,))
    return float(s0_base) + bin_n * float(c_pkt)


def threshold(client_bytes, s0_base, c_pkt, pkt=P_SERVER):
    """이 비행 크기에서 1-RTT 를 유지할 수 있는 최대 인증서 (명세 §2.5).

        임계(B) = A(B) - s0_base - (A(B)/pkt) * c

    `amplif.threshold_cert()` 는 s0 를 상수로 쓰는 옛 식이다. 그쪽은 높은 칸에서
    임계를 **과대예측**한다 — 칸이 올라갈 때 늘어나는 서버 패킷 오버헤드를
    빼지 않기 때문이다. 실측 밴드 대조(2026-08-20 probe_cliff / ips_sweep):

        x25519 B=1280 -> 3340.0  in [3312, 3368]
        x25519 B=1350 -> 4585.5  in [4557, 4614]
        MLKEM  B=2560 -> 5945.5  in [5917, 5974]
        MLKEM  B=2700 -> 7191.0  in [7163, 7219]
    """
    a = allowed(client_bytes, pkt)
    n_pkt = (a // pkt) if pkt > 0 else 0
    return a - s0_at(n_pkt, s0_base, c_pkt)


def _candidate(mode, m, delta, C, W, h, f, cert_bytes, s0,
               base_bytes, base_bin, pkt, k_floor=1,
               s0_base=None, c_pkt=0.0, parity_bytes=None):
    """후보 하나를 계산한다. 모든 후보가 같은 경로로 만들어진다.

    k_floor — 이 후보가 **유지해야 하는 최소 데이터그램 수**. levers() 는 여기에
    기준선의 `k0 = natural_k(C, W_base, h)` 를 넣는다. 근거: 기준선이 이미 k0 개를
    보내고 있으므로, 그 k0 개를 각각 δ 만큼 키우는 데는 **재패킹이 필요 없다**.
    CRYPTO 스트림을 k0 조각으로 쪼개 보내는 것은 합법이고(CRYPTO 프레임은 오프셋을
    갖는다) 기준선이 이미 그렇게 하고 있다.

    k_floor 없이 `natural_k(C, W+δ, h)` 로 다시 계산하면 W 를 키울수록 k 가 줄어
    (2->1) 비행이 오히려 작아지고 **칸이 내려간다**. 그러면 δ 로 칸을 올리는
    후보가 후보 집합에서 통째로 사라진다 — 이 연구의 헤드라인 지렛대가.
    재현(C=1150, W=1200, cert=6000, s0=1734.5): k 고정이면 W_eff=1281 -> B=2562
    -> A=8960 -> 1-RTT 를 **162 B** 로 산다. 붕괴시키면 B=1281 -> A=5120 -> 여전히
    2-RTT 라 같은 RTT 를 1,200 B 짜리 패리티로 사게 된다(7.4배 손해).
    붕괴판이 필요하면 k_floor=1 로 'pad_repack' 후보를 **추가로** 만든다.
    """
    w_eff = W + delta
    k = max(k_floor, capacity.natural_k(C, w_eff, h))
    # 🩸 2026-08-20 감사 결함 4: 패리티 데이터그램은 원본보다 크다(롱헤더 +
    #    FEC 머리 + crc/len 목록 = W+32+6k). 예전에는 여기서 W 로 세고
    #    policy.cost_of_v2 가 뒤에서 다시 셌다. 그래서 이 dict 의
    #    client_bytes·allowed·n_rtt·added_bytes 가 **전부 과소평가**였고,
    #    그 값들이 동점 처리와 설명문에 그대로 쓰였다(무손실 스윕에서
    #    n_rtt 가 실제와 13 건 어긋났다). 이제 호출자가 진짜 크기를 준다.
    pbytes = (w_eff if parity_bytes is None else int(parity_bytes(w_eff, k)))
    client_bytes = k * w_eff + m * pbytes
    a = allowed(client_bytes, pkt)
    # s0 는 상수가 아니다 — 명세 §2.5. s0_base 를 주면 칸마다 서버 패킷 수가
    # 달라지는 것을 반영하고, 안 주면 호출자가 준 상수 s0 를 그대로 쓴다(하위호환).
    # s0 는 실측 역산값이라 반정수일 수 있다(명세 §2.5: 500.0 / 1734.5).
    # int 로 자르면 경계에서 n_rtt 가 뒤집히므로 자르지 않는다.
    if s0_base is None:
        s0_eff = float(s0)
    else:
        s0_eff = s0_at((a // pkt) if pkt > 0 else 0, s0_base, c_pkt)
    flight = cert_bytes + s0_eff
    return {
        "mode": mode,
        # 요청한 j 가 아니라 **실제로 올라간 칸 수**다. k 가 줄어들면 둘이 다르다.
        "steps": bin_index(client_bytes, pkt) - base_bin,
        "m": m,
        "delta_per_dgram": delta,
        # 이 후보가 실제로 쓴 패리티 데이터그램 크기. parity_bytes 를 안 주면
        # w_eff 와 같다(하위호환) — 그 경우 client_bytes 는 근사다.
        "parity_bytes": pbytes,
        "W_eff": w_eff,
        "k": k,
        "client_bytes": client_bytes,
        # 지금 모형이 신용 계산에 쓰는 바이트. 명세 §2.6 의 B_eff(서버가 응답
        # 비행을 만들기로 결정한 시점까지 도착한 바이트)가 이것과 갈릴 수 있으나,
        # p13 이 직접 재기 전까지는 가설이므로 **바꾸지 않고 같게 둔다**.
        "credit_bytes": client_bytes,
        # 아무것도 안 했을 때 대비 순증분. W 를 키워 k 가 줄면 음수가 될 수 있다.
        "added_bytes": client_bytes - base_bytes,
        "allowed": a,
        "s0_eff": s0_eff,
        # s0_eff 를 만든 칸 번호가 무엇이었는지 밝힌다. 명세 §2.5 식은
        # n = A(B)/P 를 쓰는데, 서버가 실제로 내보내는 데이터그램 수는
        # ceil(S/P) 라서 둘이 다를 수 있다(명세 §2.5 각주: n̂ = ceil(S/1280) 이
        # 경계에서 한 칸씩 틀린다). 즉 s0_eff 는 **명세식의 값**이지 서버가
        # 실제로 쓴 패킷 수를 잰 물리량이 아니다 - 단서 없이 노출하지 않는다.
        "s0_eff_basis": "A/P",
        "server_flight": flight,
        "n_rtt": 1 if flight <= a else 2,
        # 전형 MTU 초과. 경로에서 조각나거나 버려질 수 있다는 경고일 뿐,
        # 후보에서 빼지는 않는다(판단은 호출자 몫).
        "over_mtu": w_eff > TYPICAL_MTU,
        # 명세 §2.6 (가설). m=1 배치는 [원본…, 패리티] 이므로 k==1 이면 원본
        # 하나로 서버가 곧장 응답 비행을 만들기 시작하고, 뒤따르는 패리티는
        # **결정 시점 이후**에 도착해 신용을 못 살 수 있다(x25519 on1 초과 936 B).
        # 표시만 한다 — credit_bytes 는 아직 깎지 않는다(p13 대기).
        "late_parity_risk": (k == 1 and m == 1),
        # 이 기하(데이터그램 k+m 개 x W_eff)에서 제자리 1-소거 보호가 성립하는가.
        # mode 와 무관한 **기하 판정**이며, 'pad' 후보가 복구를 준다는 뜻이 아니다
        # (명세 §4: 키운 데이터그램의 여분 바이트는 그 데이터그램과 함께 사라진다).
        "inplace_feasible": capacity.inplace_feasible(C, k + m, w_eff, h, f),
    }


def levers(C, cert_bytes, s0, W=P_SERVER, h=51, f=16, max_steps=2, m_max=2,
           s0_base=None, c_pkt=0.0, parity_bytes=None):
    """명세 §3 의 후보 집합. 연속 스윕이 아니라 **경계점만** 본다.

        후보 = {(0,0)}
             ∪ {(ceil(Δ_j/k0), 0) : j = 1..max_steps}     # δ 로 j 칸
             ∪ {(0, m)            : m = 1..m_max}         # 패리티만
             ∪ {(0, ceil(Δ_j/파))  : j, Δ_j >= W}         # 패리티로 j 칸
                                                          (파 = 패리티 실크기)

    Δ_j 가 W 보다 작으면 패리티 데이터그램을 만들 수 없다(Initial 데이터그램은
    >= 1200 B 여야 하고 그건 곧 데이터그램 하나다). 그때는 δ 가 **유일한** 수단이고
    동시에 매우 싸다. 반대로 Δ >= W 이면 보조정리 1 로 패리티가 패딩을 지배한다.

    pad 후보는 **k 를 기준선의 k0 로 유지한다**(_candidate 의 k_floor 참고).
    W 를 키울 때 k 를 다시 계산하면 k 가 줄어 칸이 내려가면서 δ 지렛대 자체가
    사라지기 때문이다. 그 붕괴판이 궁금한 호출자를 위해, 실제로 붕괴가 일어나는
    경우에 한해 **`pad_repack` 후보를 추가로** 넣는다(pad 를 대체하지 않는다).

    s0_base 를 주면 명세 §2.5 의 서버 패킷 수 항을 켠다 — 후보마다
    `s0_eff = s0_base + (A(B)/P)*c_pkt` 를 쓰고 dict 에 `s0_eff` 로 담는다.
    칸 번호는 명세식대로 **n = A(B)/P** 이지 서버가 실제로 쓴 데이터그램 수
    ceil(S/P) 가 아니다. 그 사실을 dict 에 `s0_eff_basis="A/P"` 로 함께 담는다.
    이때 인자 `s0` 는 **쓰이지 않는다**(None 을 넘겨도 된다). s0_base 를 안 주면
    예전처럼 s0 를 상수로 쓴다(하위호환).

    `c_pkt` 만 주고 `s0_base` 를 빠뜨리면 패킷항이 **조용히 무시되고** 상수 모형
    으로 되돌아간다 — 그건 오답을 말없이 돌려주는 것이므로 ValueError 로 막는다.
    (반대 방향인 `s0=None` + `s0_base=None` 도 아래에서 같이 막는다.)

    중복 후보(같은 mode·client_bytes·m)는 앞의 것만 남긴다. mode 가 다르면
    바이트가 같아도 남긴다 — 같은 바이트에서 복구 유무가 갈리는 것이 §13 의
    시험 대상이기 때문이다.
    """
    _require_int("C", C)
    _require_int("W", W)
    _require_int("h", h)
    _require_int("f", f)
    _require_int("max_steps", max_steps)
    _require_int("m_max", m_max)
    if C <= 0:
        raise ValueError("C 는 양수여야 한다: %r" % (C,))
    if W < capacity.MIN_INITIAL_DATAGRAM:
        raise ValueError("W 는 %d 이상이어야 한다(RFC 9000 §14.1): %r"
                         % (capacity.MIN_INITIAL_DATAGRAM, W))
    if m_max < 0 or max_steps < 0:
        raise ValueError("max_steps, m_max 는 음수일 수 없다")
    if s0 is None and s0_base is None:
        raise ValueError("s0(상수) 또는 s0_base(명세 §2.5 패킷항) 중 하나는 "
                         "있어야 한다")
    # 가드가 한쪽만 있으면 안 된다. c_pkt 만 주고 s0_base 를 빠뜨리면 패킷항이
    # 조용히 버려지고 상수 s0 모형의 답이 나온다 — 틀린 답을 말없이 돌려준다.
    if s0_base is None and c_pkt != 0:
        # 메시지는 cp949 로 인코딩 가능한 글자만 쓴다(윈도우 콘솔에서 이 예외가
        # 그대로 출력되면 em-dash 하나에 UnicodeEncodeError 로 뒤바뀐다).
        raise ValueError("c_pkt=%r 를 줬는데 s0_base 가 없다 - 패킷항이 조용히 "
                         "무시되고 상수 s0 모형으로 되돌아간다. s0_base 를 함께 "
                         "주거나 c_pkt 를 빼라" % (c_pkt,))

    pkt = P_SERVER
    k0 = capacity.natural_k(C, W, h)
    base_bytes = k0 * W                       # B = k*W (p1 12/12 로 확인)
    base_bin = bin_index(base_bytes, pkt)

    def mk(mode, m, delta, k_floor=k0):
        return _candidate(mode, m, delta, C, W, h, f, cert_bytes, s0,
                          base_bytes, base_bin, pkt, k_floor=k_floor,
                          s0_base=s0_base, c_pkt=c_pkt,
                          parity_bytes=parity_bytes)

    out = [mk("none", 0, 0)]

    for j in range(1, max_steps + 1):                      # δ 지렛대
        d_pad = _ceil_div(delta_min(base_bytes, j, pkt), k0)
        out.append(mk("pad", 0, d_pad))
        # 붕괴판. 재패킹해서 데이터그램 수를 줄이는 것도 **실재하는 선택지**다
        # (예: 1200 B 두 개 대신 1281 B 하나 -> 1,119 B 절약). 다만 신용은 줄어
        # 칸이 내려가므로, 기본 pad 를 대체하지 않고 별도 이름으로 덧붙인다.
        if capacity.natural_k(C, W + d_pad, h) < k0:
            out.append(mk("pad_repack", 0, d_pad, k_floor=1))

    for m in range(1, m_max + 1):                          # m 지렛대(복구 목적)
        out.append(mk("parity", m, 0))

    for j in range(1, max_steps + 1):                      # m 지렛대(칸 올리기 목적)
        d_j = delta_min(base_bytes, j, pkt)
        if d_j >= W:
            # 패리티 하나가 실제로 싣는 바이트로 나눈다. W 로 나누면 필요한
            # 개수를 과대평가한다(패리티가 원본보다 크므로).
            per = W if parity_bytes is None else int(parity_bytes(W, k0))
            out.append(mk("parity", _ceil_div(d_j, per), 0))

    seen = set()
    uniq = []
    for c in out:
        key = (c["mode"], c["client_bytes"], c["m"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
    return uniq


def dominates(a, b):
    """보조정리 1 - a 가 b 를 엄격히 지배하는가.

    같은 추가 바이트에서 신용이 같으면(신용은 바이트 수에만 의존한다) 패리티가
    추가로 1-소거 복구를 준다. 복구 확률은 m 에 대해 단조 증가이므로 어떤
    손실률에서도 손해가 아니다. 그래서 세 축을 함께 본다.

        added_bytes <=,  allowed >=,  m >=,  그리고 적어도 하나가 엄격히 낫다.

    이 관계는 곱순서에서 온 **엄격 부분순서**다(비반사·비대칭·추이적).
    따라서 지배 그래프에 순환이 없다 — 자체시험 7 이 그것을 직접 확인한다.
    """
    ge = (a["added_bytes"] <= b["added_bytes"]
          and a["allowed"] >= b["allowed"]
          and a["m"] >= b["m"])
    if not ge:
        return False
    return (a["added_bytes"] < b["added_bytes"]
            or a["allowed"] > b["allowed"]
            or a["m"] > b["m"])


# ---------------------------------------------------------------------------
# 자체시험. 출력은 ASCII 로만 한다 - 윈도우 콘솔이 cp949 라 한글이 깨진다.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    try:
        from padfec import amplif
    except ImportError:                 # 패키지 경로가 이미 잡혀 있으면
        from . import amplif            # type: ignore

    _results = []

    def check(name, cond, detail=""):
        _results.append((bool(cond), name, detail))
        print("[%s] %s%s" % ("PASS" if cond else "FAIL", name,
                             ("  | " + detail) if detail else ""))

    def info(msg):
        print("[INFO] " + msg)

    print("=" * 72)
    print("padfec/quantum.py self-test   "
          "(spec: PAD-FEC v2, sections 1-3 / 2.5 / 2.6)")
    print("=" * 72)

    # -- 1. corollary: W = P => delta_min == 1 for every k -------------------
    bad = [k for k in range(1, 9) if delta_min(k * 1280) != 1]
    check("1. corollary delta_min(k*1280)==1 for k=1..8", not bad,
          "k=1..8 all 1 B" if not bad else "violations at k=%s" % bad)
    notb = [k for k in range(1, 9) if not on_boundary(k * 1280)]
    check("1b. on_boundary(k*1280) true for k=1..8", not notb,
          "3B is always a multiple of P" if not notb else "off at k=%s" % notb)

    # -- 2. spec section 2 measured cross-check (W=1200) ---------------------
    d1200 = delta_min(1200)
    bw1200 = boundary_W(1, 1200)
    check("2. delta_min(1200)==81 and boundary_W(1,1200)==1281",
          d1200 == 81 and bw1200 == 1281,
          "delta_min=%d  boundary_W=%d  A(1200)=%d" % (d1200, bw1200,
                                                       allowed(1200)))

    # -- 2b. measured cliff, 2026-08-20 probe_cliff (both k) -----------------
    # 1279/1280 -> same bin (negative control), 1281/1282/1350 -> next bin.
    # The boundary ips is 1281 for k=1 AND k=2 -- the corollary says k does not
    # move it, and the measurement agrees.
    cliff_bad = []
    for kk in (1, 2):
        lo = set(bin_index(kk * i) for i in (1279, 1280))
        hi = set(bin_index(kk * i) for i in (1281, 1282, 1350))
        if not (len(lo) == 1 and len(hi) == 1 and min(hi) == min(lo) + 1):
            cliff_bad.append((kk, sorted(lo), sorted(hi)))
    check("2b. bins: 1279==1280 (negative control), 1281==1282==1350, +1 step",
          not cliff_bad,
          "k=1 bins 3->4, k=2 bins 6->7" if not cliff_bad
          else "%r" % (cliff_bad,))

    # -- 3. same boundary regardless of k ------------------------------------
    b1, b2 = boundary_W(1, 1280), boundary_W(2, 1280)
    check("3. boundary_W(1,1280)==boundary_W(2,1280)==1281",
          b1 == 1281 and b2 == 1281,
          "k=1 -> %d, k=2 -> %d (k does not move the boundary)" % (b1, b2))
    check("3b. the two computations agree with the W=1200 route",
          bw1200 == b1 == b2, "1200-route=%d  1280-route=%d" % (bw1200, b1))

    # -- 4. allowed() spot values --------------------------------------------
    want = [(1280, 3840), (1281, 5120), (2560, 7680), (2562, 8960)]
    got = [(b, allowed(b)) for b, _ in want]
    check("4. allowed() spot values", got == want,
          " ".join("A(%d)=%d" % (b, a) for b, a in got))

    # -- 5. threshold predictions vs measured intervals ----------------------
    t1 = allowed(1280) - 500.0            # x25519  s0 = 500.0  (spec section 5)
    t2 = allowed(2560) - 1734.5           # ML-KEM  s0 = 1734.5 (spec section 5)
    in1 = 3312 <= t1 <= 3368
    in2 = 5917 <= t2 <= 5974
    check("5. cert threshold prediction inside measured band",
          t1 == 3340.0 and t2 == 5945.5 and in1 and in2,
          "x25519 %.1f in [3312,3368]=%s ; MLKEM %.1f in [5917,5974]=%s"
          % (t1, in1, t2, in2))

    # -- 5b. spec section 2.5 table: s0 is NOT a constant --------------------
    S0_TABLE = [(3, 396.5, 34.5, 500.0), (4, 396.5, 34.5, 534.5),
                (6, 1527.5, 34.5, 1734.5), (7, 1527.5, 34.5, 1769.0)]
    s0_bad = [(n, s0_at(n, b, c), w) for n, b, c, w in S0_TABLE
              if s0_at(n, b, c) != w]
    check("5b. s0_at() reproduces the spec 2.5 table exactly", not s0_bad,
          " ".join("s0(%d)=%.1f" % (n, s0_at(n, b, c))
                   for n, b, c, _ in S0_TABLE) if not s0_bad
          else "%r" % (s0_bad,))

    # -- 5c. threshold() with the packet term lands in the measured bands ----
    BANDS = [  # (label, B, s0_base, band_lo, band_hi, expected)
        ("x25519 ips=1280", 1280, 396.5, 3312, 3368, 3340.0),
        ("x25519 ips=1350", 1350, 396.5, 4557, 4614, 4585.5),
        ("MLKEM  ips=1280", 2560, 1527.5, 5917, 5974, 5945.5),
        ("MLKEM  ips=1350", 2700, 1527.5, 7163, 7219, 7191.0),
    ]
    band_bad, band_txt = [], []
    for lbl, B, sb, lo_b, hi_b, want_t in BANDS:
        t = threshold(B, sb, 34.5)
        band_txt.append("%s %.1f" % (lbl.split()[0], t))
        if not (t == want_t and lo_b <= t <= hi_b):
            band_bad.append((lbl, t, lo_b, hi_b, want_t))
    check("5c. threshold() inside every measured band (4/4)", not band_bad,
          " ".join(band_txt) if not band_bad else "%r" % (band_bad,))

    # The constant-s0 model is calibrated at the LOW bin of each group
    # (x25519 500.0 at bin 3, MLKEM 1734.5 at bin 6 -- spec section 5). Carry it
    # to the next bin unchanged and it overpredicts by exactly c = 34.5 B and
    # falls OUTSIDE the measured band. That is why the packet term exists.
    CONST_S0 = {396.5: 500.0, 1527.5: 1734.5}
    const_out, pkt_in = 0, 0
    const_txt = []
    for lbl, B, sb, lo_b, hi_b, _ in BANDS:
        t_const = amplif.threshold_cert(B, CONST_S0[sb])
        t_pkt = threshold(B, sb, 34.5)
        if not (lo_b <= t_const <= hi_b):
            const_out += 1
        if lo_b <= t_pkt <= hi_b:
            pkt_in += 1
        const_txt.append("%s const=%.1f pkt=%.1f d=%+.1f"
                         % (lbl.split()[0], t_const, t_pkt, t_const - t_pkt))
    check("5c2. constant-s0 leaves the band at the higher bin, packet term "
          "stays in", const_out == 2 and pkt_in == 4,
          "%d/4 const outside, %d/4 packet-term inside | %s"
          % (const_out, pkt_in, " ; ".join(const_txt)))

    # -- 5d. spec section 2.5 new predictions (the p12c targets) -------------
    NEWPRED = [("x25519 ips=1707 bin5", 1707, 396.5, 5831.0),
               ("x25519 ips=2134 bin6", 2134, 396.5, 7076.5),
               ("MLKEM  ips=1281 bin7", 2562, 1527.5, 7191.0)]
    np_bad = [(l, threshold(B, sb, 34.5), w) for l, B, sb, w in NEWPRED
              if threshold(B, sb, 34.5) != w]
    check("5d. threshold() reproduces the p12c predictions", not np_bad,
          " ".join("%s=%.1f" % (l.split()[-1], threshold(B, sb, 34.5))
                   for l, B, sb, _ in NEWPRED) if not np_bad
          else "%r" % (np_bad,))

    # -- 5e. the 2026-08-20 cliff: all 10 measured points are reproduced -----
    # cert fixed between two predicted thresholds; only ips moves.
    #
    # 정정(2026-08-20, results/probe_s0_*.json): 이 절벽은 **패킷항의 증거가
    # 아니다.** 상수 s0 모형도 이 10 점을 똑같이 맞힌다 - cert 가 두 칸 사이에
    # 고정돼 있고 두 모형의 임계가 그 사이에서 갈리지 않기 때문이다. 절벽이
    # 증명하는 것은 *양자화*(한 칸이 통째로 뛴다)뿐이고, s0 가 상수인지 서버
    # 패킷 수에 비례하는지는 **구분하지 못한다.** 두 모형을 실제로 가르는 것은
    # 5c2(높은 칸에서 상수 모형이 측정 밴드를 벗어난다)와 서버 바이트 직접
    # 측정(머리말 표)이다. 아래 검사는 "예측 n_rtt == 관측 n_rtt" 그 이상을
    # 주장하지 않는다.
    CLIFF = [  # (label, k, ips, cert, s0_base, OBSERVED n_rtt)
        ("x25519 1279", 1, 1279, 4000, 396.5, 2),
        ("x25519 1280", 1, 1280, 4000, 396.5, 2),
        ("x25519 1281", 1, 1281, 4000, 396.5, 1),
        ("x25519 1282", 1, 1282, 4000, 396.5, 1),
        ("x25519 1350", 1, 1350, 4000, 396.5, 1),
        ("MLKEM  1279", 2, 1279, 6500, 1527.5, 2),
        ("MLKEM  1280", 2, 1280, 6500, 1527.5, 2),
        ("MLKEM  1281", 2, 1281, 6500, 1527.5, 1),
        ("MLKEM  1282", 2, 1282, 6500, 1527.5, 1),
        ("MLKEM  1350", 2, 1350, 6500, 1527.5, 1),
    ]
    cl_bad = [lbl for lbl, kk, ips, cert, sb, obs in CLIFF
              if (1 if cert <= threshold(kk * ips, sb, 34.5) else 2) != obs]
    check("5e. predicted n_rtt == observed n_rtt on all 10 probe_cliff points",
          not cl_bad, "10/10 (x25519 cert=4000, MLKEM cert=6500)"
          if not cl_bad else "misses: %r" % (cl_bad,))

    # -- 6. exhaustive invariants over B = 1200..20000 -----------------------
    LO, HI = 1200, 20000
    v_a = v_b = v_c = v_d = v_x = 0
    first_bad = None
    only_dmin1 = 0                       # delta_min==1 but NOT on_boundary
    for B in range(LO, HI + 1):
        A = allowed(B)
        dm = delta_min(B)
        if A < AMP * B:
            v_a += 1
            first_bad = first_bad or ("a", B)
        if A - AMP * B >= 1280:
            v_b += 1
            first_bad = first_bad or ("b", B)
        if bin_index(B + dm) != bin_index(B) + 1:
            v_c += 1
            first_bad = first_bad or ("c", B)
        if dm < 1:
            v_d += 1
            first_bad = first_bad or ("d", B)
        if A != amplif.allowed_bytes(B):          # cross-module agreement
            v_x += 1
            first_bad = first_bad or ("x", B)
        if dm == 1 and not on_boundary(B):
            only_dmin1 += 1
    n = HI - LO + 1
    check("6a. allowed(B) >= 3B          (B=%d..%d, n=%d)" % (LO, HI, n),
          v_a == 0, "%d violations" % v_a)
    check("6b. allowed(B) - 3B < 1280", v_b == 0, "%d violations" % v_b)
    check("6c. bin_index(B+delta_min(B)) == bin_index(B)+1", v_c == 0,
          "%d violations" % v_c)
    check("6d. delta_min(B) >= 1", v_d == 0, "%d violations" % v_d)
    check("6e. allowed() == amplif.allowed_bytes() (no drift)", v_x == 0,
          "%d disagreements" % v_x)
    if first_bad:
        info("first violation: %r" % (first_bad,))
    info("delta_min==1 but NOT on_boundary: %d of %d  "
         "(3B mod P in {P-1,P-2}; B = 426 or 853 mod 1280) "
         "-- on_boundary implies delta_min==1, not the converse"
         % (only_dmin1, n))

    # -- 7. dominance digraph is acyclic -------------------------------------
    SCEN = [
        # (name, C, cert, s0, W)  - C from p1_flight.json, s0 from spec section 5
        ("x25519  ips=1280", 259, 4000, 500.0, 1280),
        ("MLKEM   ips=1280", 1450, 6000, 1734.5, 1280),
        ("MLKEM   ips=1200", 1451, 6000, 1734.5, 1200),
        ("MLKEM   big-cert", 1457, 9000, 1769.0, 1350),
    ]
    # levers() 가 만드는 후보는 added_bytes 와 allowed 가 함께 증가하므로
    # 구조적으로 **반사슬(antichain)** 이다 - 서로 지배하지 않는다. 그 집합만으로
    # 비순환을 시험하면 간선이 0 개라 시험이 공허해진다. 그래서 보조정리 1 의
    # 실제 대립쌍(같은 Δ 에서 pad vs parity)을 만들어 간선이 있는 그래프로 시험한다.
    _bb = 1 * 1280
    _args = (259, 1280, 51, 16, 4000, 500.0, _bb, bin_index(_bb), P_SERVER)
    lem_pad = _candidate("pad", 0, 1280, *_args)      # delta = W, 복구 없음
    lem_par = _candidate("parity", 1, 0, *_args)      # 같은 바이트, 복구 있음
    lemma1 = (dominates(lem_par, lem_pad)
              and not dominates(lem_pad, lem_par))
    check("7-0. Lemma 1: at delta == W parity strictly dominates pad", lemma1,
          "pad added=%d allowed=%d m=%d  vs  parity added=%d allowed=%d m=%d"
          % (lem_pad["added_bytes"], lem_pad["allowed"], lem_pad["m"],
             lem_par["added_bytes"], lem_par["allowed"], lem_par["m"]))

    # 간선 1 개짜리 그래프에서는 추이성이 검사할 삼중항이 0 개라 시험이 공허하다.
    # 같은 칸·같은 바이트(B = 3,840)에 m = 0/1/2 를 나란히 놓아 **2-체인**을 만든다.
    #   pad    m=0 delta=2560 -> W_eff 3840, k=1, B = 1*3840
    #   parity m=1 delta= 640 -> W_eff 1920, k=1, B = 2*1920
    #   parity m=2 delta=   0 -> W_eff 1280, k=1, B = 3*1280
    # 셋 다 added_bytes 와 allowed 가 같고 m 만 다르므로 m=2 > m=1 > m=0 이고
    # m=2 > m=0 도 성립해야 한다(추이성). 이게 보조정리 1 의 사슬 판이다.
    ch_m0 = _candidate("pad", 0, 2560, *_args)
    ch_m1 = _candidate("parity", 1, 640, *_args)
    ch_m2 = _candidate("parity", 2, 0, *_args)
    CHAIN = [ch_m0, ch_m1, ch_m2]
    same_cell = (len(set(c["client_bytes"] for c in CHAIN)) == 1
                 and len(set(c["allowed"] for c in CHAIN)) == 1
                 and len(set(c["added_bytes"] for c in CHAIN)) == 1)
    chain_ok = (same_cell
                and dominates(ch_m2, ch_m1) and dominates(ch_m1, ch_m0)
                and dominates(ch_m2, ch_m0)          # 추이성이 실제로 필요
                and not dominates(ch_m0, ch_m1)
                and not dominates(ch_m1, ch_m2))
    check("7-1. a real 2-chain exists: parity m=2 > m=1 > m=0 at equal bytes",
          chain_ok,
          "B=%d allowed=%d added=%d for all three; m = 0/1/2"
          % (ch_m0["client_bytes"], ch_m0["allowed"], ch_m0["added_bytes"]))

    LEMMA = [lem_pad, lem_par] + CHAIN

    total_edges = 0
    n_irr = n_anti = n_trans = n_cyc = n_chain2 = 0
    distinct_edges = set()
    for nm, C, cert, s0v, Wv in SCEN:
        cs = levers(C, cert, s0v, W=Wv)
        if Wv == 1280 and C == 259:
            cs = cs + LEMMA                # 간선과 2-체인이 존재하는 그래프로 만든다
        idx = range(len(cs))
        edges = {i: [j for j in idx if i != j and dominates(cs[i], cs[j])]
                 for i in idx}
        total_edges += sum(len(v) for v in edges.values())

        def sig(c):                        # 같은 내용의 후보는 같은 간선으로 센다
            return (c["mode"], c["m"], c["client_bytes"], c["added_bytes"],
                    c["allowed"])

        for i in idx:
            for j in edges[i]:
                distinct_edges.add((sig(cs[i]), sig(cs[j])))
        for i in idx:
            if dominates(cs[i], cs[i]):
                n_irr += 1
            for j in idx:
                if dominates(cs[i], cs[j]) and dominates(cs[j], cs[i]):
                    n_anti += 1
                for kk in idx:
                    if dominates(cs[i], cs[j]) and dominates(cs[j], cs[kk]):
                        n_chain2 += 1      # i -> j -> kk : 검사할 삼중항
                        if not dominates(cs[i], cs[kk]):
                            n_trans += 1
        # explicit DFS cycle detection over the whole digraph
        colour = {i: 0 for i in idx}

        def visit(u):
            colour[u] = 1
            hit = False
            for w in edges[u]:
                if colour[w] == 1:
                    hit = True
                elif colour[w] == 0 and visit(w):
                    hit = True
            colour[u] = 2
            return hit

        for i in idx:
            if colour[i] == 0 and visit(i):
                n_cyc += 1
    check("7. dominance is irreflexive", n_irr == 0, "%d self-loops" % n_irr)
    check("7b. dominance is antisymmetric", n_anti == 0,
          "%d mutual pairs" % n_anti)
    check("7c. dominance is transitive", n_trans == 0,
          "%d broken triples out of %d i->j->k chains" % (n_trans, n_chain2))
    check("7d. dominance digraph is ACYCLIC (DFS)", n_cyc == 0,
          "%d cycles over %d scenarios, %d edges"
          % (n_cyc, len(SCEN), total_edges))
    check("7e. the test is NOT vacuous: >=2 distinct edges AND >=1 2-chain",
          len(distinct_edges) >= 2 and n_chain2 >= 1,
          "%d distinct edges (%d total), %d 2-chains to check transitivity on"
          % (len(distinct_edges), total_edges, n_chain2))
    _anti = levers(259, 4000, 500.0, W=1280)
    _pairs = sum(1 for a in _anti for b in _anti
                 if a is not b and dominates(a, b))
    info("levers() candidate set is a Pareto ANTICHAIN: %d dominated pairs "
         "among %d candidates -- Lemma 1 prunes nothing here, so J must be "
         "evaluated at every boundary point" % (_pairs, len(_anti)))

    # -- 8. the headline: 1-2 bytes buy a round trip --------------------------
    for nm, C, cert, s0v, Wv, want_add in (
            ("x25519 C=259  cert=4000 s0=500.0", 259, 4000, 500.0, 1280, 1),
            ("MLKEM  C=1450 cert=6000 s0=1734.5", 1450, 6000, 1734.5, 1280, 2)):
        cs = levers(C, cert, s0v, W=Wv)
        base = cs[0]
        win = [c for c in cs if c["mode"] == "pad" and c["n_rtt"] == 1]
        ok = (base["n_rtt"] == 2 and win
              and min(c["added_bytes"] for c in win) == want_add)
        check("8. %s -> pad of %d B removes one RTT" % (nm, want_add), ok,
              "base n_rtt=%d allowed=%d S=%.1f ; cheapest 1-RTT pad = %s B"
              % (base["n_rtt"], base["allowed"], base["server_flight"],
                 (min(c["added_bytes"] for c in win) if win else "none")))

    # -- 9. the k-collapse trap: pad candidates must NOT lose k ---------------
    # 명세 §3 의 후보식 (ceil(Δ_j/k), 0) 은 k 가 그대로라고 가정한다. k 를 W_eff 로
    # 다시 계산하면 C 가 W-h 를 겨우 넘는 설정에서 k 가 2->1 로 무너지고, 비행이
    # 오히려 작아져 **칸이 내려간다** - δ 지렛대가 후보 집합에서 사라진다.
    # 감사 재현: C=1150, W=1200, cert=6000, s0=1734.5.
    trap = levers(1150, 6000, 1734.5, W=1200)
    tbase = trap[0]
    tpad = [c for c in trap if c["mode"] == "pad"]
    trep = [c for c in trap if c["mode"] == "pad_repack"]
    cheap = [c for c in tpad if c["n_rtt"] == 1]
    check("9. pad keeps k0: C=1150 W=1200 buys 1-RTT for 162 B (not 1200 B)",
          tbase["k"] == 2 and tbase["n_rtt"] == 2
          and all(c["k"] == 2 for c in tpad)
          and cheap and min(c["added_bytes"] for c in cheap) == 162,
          "base k=2 A=%d S=%.1f n_rtt=2 -> pad W_eff=%d k=%d B=%d A=%d "
          "added=%d n_rtt=%d"
          % (tbase["allowed"], tbase["server_flight"], tpad[0]["W_eff"],
             tpad[0]["k"], tpad[0]["client_bytes"], tpad[0]["allowed"],
             tpad[0]["added_bytes"], tpad[0]["n_rtt"]))
    check("9b. the collapsed variant is KEPT, but as a separate 'pad_repack'",
          len(trep) == 2
          and all(c["k"] == 1 and c["added_bytes"] < 0 and c["steps"] < 0
                  and c["n_rtt"] == 2 for c in trep),
          "pad_repack k=1 added=%s steps=%s A=%s (still 2-RTT)"
          % ([c["added_bytes"] for c in trep], [c["steps"] for c in trep],
             [c["allowed"] for c in trep]))
    info("repacking is NOT a bug to filter: one 1281 B datagram instead of two "
         "1200 B ones saves 1119 B. It is a real option whose n_rtt is simply "
         "worse here, so it is offered alongside -- never instead of -- pad.")

    # -- 9c. how big is the collapse? count it, do not quote an old number ----
    SW_W = (1200, 1250, 1280, 1300, 1350, 1400)
    SW_C = range(200, 3000)
    n_collapse = 0
    collapse_cfg = set()
    hist = {}
    fixed_better = repack_better = credit_lost = 0
    for Wv in SW_W:
        for Cv in SW_C:
            cs = levers(Cv, 6000, 1734.5, W=Wv, m_max=0)
            reps = [c for c in cs if c["mode"] == "pad_repack"]
            if not reps:
                continue
            pads = dict((c["delta_per_dgram"], c) for c in cs
                        if c["mode"] == "pad")
            collapse_cfg.add((Cv, Wv))
            n_collapse += len(reps)
            for r in reps:
                hist[r["steps"]] = hist.get(r["steps"], 0) + 1
                p = pads[r["delta_per_dgram"]]
                if p["allowed"] > r["allowed"]:
                    credit_lost += 1
                if p["n_rtt"] < r["n_rtt"]:
                    fixed_better += 1
                elif r["n_rtt"] < p["n_rtt"]:
                    repack_better += 1
    check("9c. repacking NEVER beats the k-fixed pad on n_rtt (0 counterex.)",
          repack_better == 0 and credit_lost == n_collapse and n_collapse > 0,
          "%d collapsing candidates over %d distinct (C,W); credit lost in "
          "%d/%d; k-fixed strictly better on n_rtt in %d (%.1f%%), repack "
          "better in %d"
          % (n_collapse, len(collapse_cfg), credit_lost, n_collapse,
             fixed_better, 100.0 * fixed_better / n_collapse, repack_better))
    info("collapse sweep: C=%d..%d x W in %s (cert=6000 s0=1734.5 m_max=0); "
         "steps histogram %s -- the candidate that k-fixing rescues always "
         "dropped 2 or more bins"
         % (SW_C[0], SW_C[-1], list(SW_W),
            sorted(hist.items())))

    # -- 10. integer vs float differential (do not overstate the rationale) ---
    import math as _math

    def _dm_float(B, pkt=P_SERVER):
        A = _math.ceil(AMP * B / pkt) * pkt
        return _math.floor(A / AMP - B) + 1

    mism = [B for B in range(1200, 300001) if _dm_float(B) != delta_min(B)]
    check("10. float and int agree on B=1200..300000 (rationale is honest)",
          not mism, "%d mismatches over %d values" % (len(mism), 300001 - 1200))
    # 머리말이 주장하는 10^9 / 10^12 / 10^15 도 매번 다시 확인한다.
    # 다만 그 셋만 쓰면 안 된다: 셋 다 3B mod P == 0 인 **퇴화 표본**이라
    # A(B) = 3B 가 되어 float 이 반올림할 여지가 구조적으로 없다. 같은 크기대에서
    # 3B mod P != 0 인 점을 함께 넣는다 — +427 이면 3B mod P == 1(즉 A-3B == P-1,
    # 나눗셈이 가장 큰 자리), +853 이면 3B mod P == P-1(즉 delta_min == 1, 경계 옆).
    BIG = [10 ** 9, 10 ** 12, 10 ** 15,
           10 ** 9 + 427, 10 ** 12 + 853, 10 ** 15 + 427, 10 ** 15 + 853]
    nondeg = [B for B in BIG if (AMP * B) % P_SERVER != 0]
    big_bad = [(B, _dm_float(B), delta_min(B)) for B in BIG
               if _dm_float(B) != delta_min(B)]
    check("10a. float and int also agree at B ~ 1e9/1e12/1e15, %d of %d points "
          "non-degenerate (3B mod P != 0)" % (len(nondeg), len(BIG)),
          not big_bad and len(nondeg) >= 4,
          " ".join("3B%%P=%d:dm=%d" % ((AMP * B) % P_SERVER, delta_min(B))
                   for B in BIG) if not big_bad else "%r" % (big_bad,))
    _brk = 2 ** 53
    # 이 검사는 2**53 **한 점**에서 둘이 갈린다는 것만 본다. '처음'도 '거기서만'도
    # 시험하지 않는다 — 실제 최초 분기는 훨씬 아래(2^51 대역)다(머리말 참고).
    check("10b. at B = 2**53 float and int disagree (a single spot check -- "
          "NOT a claim that 2**53 is the first or only such B; it is neither)",
          _dm_float(_brk) != delta_min(_brk),
          "B=2**53: float=%d int=%d" % (_dm_float(_brk), delta_min(_brk)))
    info("integer arithmetic is used to remove the question, NOT because "
         "float demonstrably breaks in range -- it does not.")

    # -- 11. input validation: bytes are integers, full stop ------------------
    val_bad = []
    for fn, args in ((delta_min, (1280.0,)), (delta_min, (1280, 1.0)),
                     (delta_min, (1280, 1, 1280.0)), (delta_min, (True,)),
                     (levers, (259.0, 4000, 500.0)),
                     (levers, (259, 4000, 500.0, 1280.5))):
        try:
            fn(*args)
        except TypeError:
            continue
        except Exception as exc:                      # noqa: BLE001
            val_bad.append((fn.__name__, args, type(exc).__name__))
            continue
        val_bad.append((fn.__name__, args, "NO RAISE"))
    check("11. non-int byte/step counts raise TypeError (6/6)", not val_bad,
          "delta_min and levers both reject float and bool"
          if not val_bad else "%r" % (val_bad,))
    try:
        levers(259, 4000, None)
        _both = "NO RAISE"
    except ValueError:
        _both = "ValueError"
    except Exception as exc:                          # noqa: BLE001
        _both = type(exc).__name__
    check("11b. levers(s0=None) without s0_base is refused up front",
          _both == "ValueError", "raised %s" % _both)

    # -- 12. spec 2.6 flags and the section 2.5 path through levers() ---------
    v_const = levers(1450, 6000, 1734.5, W=1280)
    # s0_base 를 주면 상수 s0 는 쓰이지 않는다 - None 을 넘겨 그것을 보인다.
    v_pkt = levers(1450, 6000, None, W=1280, s0_base=1527.5, c_pkt=34.5)
    bc = all(c["s0_eff"] == 1734.5 for c in v_const)
    pk = all(c["s0_eff"] == s0_at(c["allowed"] // P_SERVER, 1527.5, 34.5)
             for c in v_pkt)
    n_s0 = len(set(c["s0_eff"] for c in v_pkt))
    check("12. s0_base=None keeps the old constant s0; s0_base set makes "
          "s0_eff bin-dependent", bc and pk and n_s0 > 1,
          "constant path all %.1f ; packet path %d distinct s0_eff over "
          "%d candidates: %s"
          % (1734.5, n_s0, len(v_pkt),
             sorted(set(c["s0_eff"] for c in v_pkt))))
    # credit_bytes: 지금은 client_bytes 와 같아야 한다(p13 전까지 안 바꾼다).
    all_c = v_const + v_pkt + levers(259, 4000, 500.0, W=1280)
    check("12b. credit_bytes == client_bytes for every candidate (p13 pending)",
          all(c["credit_bytes"] == c["client_bytes"] for c in all_c),
          "%d candidates, none re-credited yet" % len(all_c))
    # late_parity_risk: k==1 이고 m==1 인 후보만.
    lp = [c for c in all_c if c["late_parity_risk"]]
    check("12c. late_parity_risk marks exactly the k==1, m==1 candidates",
          all((c["k"] == 1 and c["m"] == 1) == c["late_parity_risk"]
              for c in all_c) and lp,
          "%d flagged of %d; spec 2.6 measured excess for x25519 on1 = 936 B"
          % (len(lp), len(all_c)))
    # over_mtu: W_eff > 1500 인 후보만.
    _mtu = levers(4200, 4000, 500.0, W=1450, max_steps=2, m_max=1)
    over = [c for c in _mtu if c["over_mtu"]]
    check("12d. over_mtu flags exactly W_eff > %d" % TYPICAL_MTU,
          all((c["W_eff"] > TYPICAL_MTU) == c["over_mtu"] for c in all_c + _mtu)
          and over,
          "W_eff seen: %s ; flagged %d"
          % (sorted(set(c["W_eff"] for c in _mtu)), len(over)))

    # -- candidate table (evidence, ASCII) -----------------------------------
    HDR = ("mode", "st", "m", "dlt", "W_eff", "k", "cbytes", "added",
           "allowed", "s0_eff", "rtt", "inpl", "lateP", "mtu!")
    FMT = "%-10s %3d %2d %4d %6d %2d %7d %7d %8d %7.1f %3d %5s %5s %4s"

    def table(title, cands):
        print("-" * 78)
        print(title)
        print("%-10s %3s %2s %4s %6s %2s %7s %7s %8s %7s %3s %5s %5s %4s" % HDR)
        for c in cands:
            print(FMT % (c["mode"], c["steps"], c["m"], c["delta_per_dgram"],
                         c["W_eff"], c["k"], c["client_bytes"],
                         c["added_bytes"], c["allowed"], c["s0_eff"],
                         c["n_rtt"], c["inplace_feasible"],
                         c["late_parity_risk"], c["over_mtu"]))

    table("levers(C=1450, cert=6000, s0=1734.5, W=1280)   [MLKEM, k=2, "
          "constant s0]", levers(1450, 6000, 1734.5, W=1280))
    table("levers(C=1450, cert=6000, s0=None, W=1280, s0_base=1527.5, "
          "c_pkt=34.5)   [MLKEM, spec 2.5 packet term]",
          levers(1450, 6000, None, W=1280, s0_base=1527.5, c_pkt=34.5))
    table("levers(C=1150, cert=6000, s0=1734.5, W=1200)   [k-collapse case: "
          "pad keeps k0=2, pad_repack does not]",
          levers(1150, 6000, 1734.5, W=1200))
    print("-" * 78)

    failed = [r for r in _results if not r[0]]
    print("%d checks, %d failed" % (len(_results), len(failed)))
    for _, nm, det in failed:
        print("  FAILED: %s | %s" % (nm, det))
    sys.exit(1 if failed else 0)
