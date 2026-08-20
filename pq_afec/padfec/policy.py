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

# quic-go 가 실제로 내보낼 수 있는 InitialPacketSize 의 상한.
# 2026-08-20 실측: -ips 1707 을 줘도 클라이언트는 1452 B 로 깎아 보냈다.
# 그래서 δ 지렛대로 갈 수 있는 칸이 막힌다 — x25519 는 칸 3·4, ML-KEM 은 6·7 까지.
# 이 상수를 넘는 후보는 **보낼 수 없으므로** 기본적으로 후보에서 뺀다.
QUICGO_MAX_IPS = 1452

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
T_PTO_NO_ACK_MS = 200.86        # 실측 200.90 / 200.96 / 200.73 의 평균
T_ACK_RETX_SLOPE = 1.1250       # 최소제곱 적합, 잔차 |0.10| ms 이내
T_ACK_RETX_BASE_MS = 1.424


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


def tx_cost_ms(extra_bytes, uplink_mbps):
    """추가 바이트를 실제로 밀어내는 데 드는 시간.

    작지만 0 이 아니다. 이 항이 없으면 정책이 이득이 같을 때도 무조건 큰
    m 을 고른다 - 1차 때 겪은 것과 같은 종류의 편향이다.
    """
    if uplink_mbps <= 0:
        return 0.0
    return (extra_bytes * 8.0) / (uplink_mbps * 1e6) * 1000.0


def expected_hct_ms(cert_bytes, k, m, W, rtt_ms, p, burst, s0,
                    pto_ms=PTO_NO_SAMPLE_MS, uplink_mbps=10.0):
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
           W=capacity.MIN_INITIAL_DATAGRAM, m_max=2,
           pto_ms=PTO_NO_SAMPLE_MS, uplink_mbps=10.0):
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
       나온다. 자체시험 4 가 이 값이 p_unrecoverable 과 일치하는지 확인한다.
    """
    if p <= 0.0:
        return 0.0
    k, m = cand["k"], cand["m"]
    pm = joint_arrival_pmf(k, m, p, burst)
    return float(sum(pm[a_][b_]
                     for a_ in range(k + 1) for b_ in range(m + 1)
                     if (k - a_) > b_))


def cost_of(cand, rtt_ms, p, burst, t_recover_ms=None, uplink_mbps=10.0):
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
    return (round(e["j_ms"], 6),
            e["added_bytes_real"],
            0 if e["cand"]["m"] > 0 else 1,          # 같은 바이트면 패리티 우선
            1 if e["cand"]["late_parity_risk"] else 0,
            1 if e["cand"]["over_mtu"] else 0,
            e["cand"]["mode"])


def decide_v2(C, cert_bytes, rtt_ms, p, burst=DEFAULT_ASSUMED_BURST, s0=None,
              W=quantum.P_SERVER, h=51, f=16,
              max_steps=2, m_max=2,
              s0_base=None, c_pkt=0.0,
              t_recover_ms=None, t_recover_ack_ms=None,
              uplink_mbps=10.0,
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
    cands = quantum.levers(C, cert_bytes, s0, W=W, h=h, f=f,
                           max_steps=max_steps, m_max=m_max,
                           s0_base=s0_base, c_pkt=c_pkt,
                           parity_bytes=parity_datagram_bytes)
    k0 = capacity.natural_k(C, W, h)

    kept, dropped = [], []
    for c in cands:
        why = None
        if not allow_repack and c["mode"] == "pad_repack":
            why = "재패킹은 구현이 안 되어 있다"
        elif max_ips is not None and c["W_eff"] > max_ips:
            why = ("W_eff %d > 보낼 수 있는 상한 %d"
                   % (c["W_eff"], max_ips))
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
    scored.sort(key=_rank_key)

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

PARITY_OVERHEAD_BASE = 32      # 롱헤더 약 19 + FEC 머리 13
PARITY_OVERHEAD_PER_K = 6      # crc/len 목록


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


def flight_outcome(k, m, w, p, burst, server_flight):
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
    pm = joint_arrival_pmf(k, m, p, burst)
    n_sum = 0.0
    p_fail = 0.0
    p_fail_pto = 0.0
    p_fail_ack = 0.0
    p_two = 0.0
    for a_ in range(k + 1):
        for b_ in range(m + 1):
            pr = pm[a_][b_]
            if pr <= 0.0:
                continue
            # MDS: 받은 심볼이 k 개 이상이면 복구된다(잃은 원본 <= 도착 패리티).
            if (k - a_) > b_:
                p_fail += pr
                # 실패의 대가는 **서버가 하나라도 받았는지**로 갈린다.
                # 0 개면 ACK 자체가 없어 PTO(경로 무관 상수), 1 개 이상이면
                # ACK 로 구멍이 드러나 즉시 재전송(왕복 하나). 실측 근거는
                # 위 T_PTO_NO_ACK_MS 주석.
                if (a_ + b_) == 0:
                    p_fail_pto += pr
                else:
                    p_fail_ack += pr
                continue
            # 복구된 원본의 바이트는 신용에 안 넣는다 — 회계 규칙상 복구본을
            # 넣을 때 패리티를 버리므로 서버가 실제로 센 바이트만 예산이 된다.
            arrived = a_ * w + b_ * parity
            if server_flight > float(quantum.allowed(arrived)):
                n_sum += pr * 2.0
                p_two += pr
            else:
                n_sum += pr
    ok = 1.0 - p_fail
    return {
        # 복구 성공 상태들에 대한 **가중합**이다. 질량이 (1 - p_fail) 이므로
        # p_fail 이 큰 후보끼리 이 값만 비교하면 안 된다 — 그럴 때는 아래
        # n_rtt_given_ok(조건부 기댓값)를 쓴다. 비용식은 가중합 쪽을 쓴다.
        "n_rtt_expected": n_sum,
        "n_rtt_given_ok": (n_sum / ok if ok > 1e-15 else 2.0),
        "p_fail": p_fail,
        # 실패 질량을 두 가지로 나눈다. 합은 p_fail 이다.
        "p_fail_pto": p_fail_pto,   # 서버가 0 개 받음 -> ACK 없음 -> PTO
        "p_fail_ack": p_fail_ack,   # 1 개 이상 받음 -> ACK -> 즉시 재전송
        "p_two_rtt": p_two,
        "p_recoverable": ok,
    }


def client_bytes_of(cand):
    """이 후보가 실제로 내보내는 클라이언트 바이트 (패리티 크기 반영)."""
    k, m, w = cand["k"], cand["m"], cand["W_eff"]
    return k * w + m * parity_datagram_bytes(w, k)


def cost_of_v2(cand, W_base, rtt_ms, p, burst,
               t_recover_ms=None, uplink_mbps=10.0, k0=None,
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
    k, m, w = cand["k"], cand["m"], cand["W_eff"]
    base_k = k if k0 is None else k0
    cb = client_bytes_of(cand)
    added = max(0, cb - base_k * W_base)
    out = flight_outcome(k, m, w, p, burst, cand["server_flight"])
    n_exp = out["n_rtt_expected"]
    pf = out["p_fail"]
    stall = (out["p_fail_pto"] * (rtt_ms + t_pto)
             + out["p_fail_ack"] * (rtt_ms + t_ack))
    tx = tx_cost_ms(added, uplink_mbps)
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

    # 3. p_fail_of 가 p_unrecoverable 과 같은가 (한 분포에서 나오는지의 시험)
    worst = 0.0
    for k in (1, 2, 3, 4):
        for m in (1, 2):
            for pp in (0.01, 0.05, 0.2):
                for LL in (1.0, 2.0, 5.0):
                    va = p_fail_of({"k": k, "m": m}, pp, LL)
                    vb = p_unrecoverable(k, m, pp, LL)
                    worst = max(worst, abs(va - vb))
    _chk("3. p_fail_of == p_unrecoverable", worst < 1e-12, "worst %.3g" % worst)

    # 4. 결함 1 - n_rtt 항이 버스트에 반응해야 한다.
    o1 = flight_outcome(2, 1, 1280, 0.05, 1.0, 6000.0)
    o5 = flight_outcome(2, 1, 1280, 0.05, 5.0, 6000.0)
    _chk("4. n_rtt term reacts to burst (defect 1)",
         abs(o1["n_rtt_expected"] - o5["n_rtt_expected"]) > 1e-6,
         "L=1 %.6f vs L=5 %.6f" % (o1["n_rtt_expected"],
                                   o5["n_rtt_expected"]))

    # 5. 결함 2 - 같은 손실 사건을 두 번 청구하지 않는다.
    o = flight_outcome(1, 0, 1280, 0.2, 1.0, 3000.0)
    _chk("5. n-term mass == 1 - p_fail (defect 2)",
         abs(o["p_recoverable"] - 0.8) < 1e-12
         and abs(o["n_rtt_expected"] - 0.8) < 1e-12,
         "n=%.6f p_ok=%.6f" % (o["n_rtt_expected"], o["p_recoverable"]))
    e = cost_of_v2({"k": 1, "m": 0, "W_eff": 1280, "server_flight": 3000.0},
                   1280, 50.0, 0.2, 1.0, t_recover_ms=50.0,
                   t_recover_ack_ms=50.0)
    _chk("5b. J = 60ms not 70ms  (k=1 m=0 p=0.2 rtt=50, T_rec forced to RTT)",
         abs(e["j_ms"] - 60.0) < 1e-9, "J=%.4f" % e["j_ms"])

    # 5c~5h. 2026-08-20 결정적 소거 실측을 고정한다.
    _chk("5c. k=1,m=0 failure is always the PTO branch",
         abs(o["p_fail_pto"] - o["p_fail"]) < 1e-12 and o["p_fail_ack"] == 0.0,
         "pto=%.6f ack=%.6f" % (o["p_fail_pto"], o["p_fail_ack"]))
    o2 = flight_outcome(2, 0, 1280, 0.2, 1.0, 3000.0)
    _chk("5d. k=2,m=0 failure splits into both branches",
         o2["p_fail_pto"] > 0 and o2["p_fail_ack"] > 0
         and abs(o2["p_fail_pto"] + o2["p_fail_ack"] - o2["p_fail"]) < 1e-12,
         "pto=%.6f ack=%.6f fail=%.6f" % (o2["p_fail_pto"], o2["p_fail_ack"],
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
                oo = flight_outcome(k, m, 1280, 0.0, 1.0, sf)
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
    _bad = []
    for cert in range(2000, 9001, 100):
        r = decide_v2(C=259, cert_bytes=cert, rtt_ms=50.0, p=0.0, burst=1.0,
                      s0_base=396.5, c_pkt=34.5)
        for c in r["candidates"]:
            if abs(c["n_rtt"] - c["n_rtt_expected"]) > 1e-9:
                _bad.append((cert, c["mode"], c["m"]))
    _chk("9. levers n_rtt == expected n_rtt at p=0 (defect 4)",
         not _bad, str(_bad[:3]))

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

    # 11. 정책이 기준선보다 나쁜 것을 고르지 않는다
    _bad = []
    for C in (259, 1450):
        for cert in range(1000, 9001, 500):
            for pp in (0.0, 0.05, 0.2):
                for LL in (1.0, 3.0):
                    r = decide_v2(C=C, cert_bytes=cert, rtt_ms=50.0, p=pp,
                                  burst=LL, s0_base=396.5, c_pkt=34.5)
                    if r["gain_ms"] < -1e-9:
                        _bad.append((C, cert, pp, LL, r["gain_ms"]))
    _chk("11. gain_ms >= 0 over the sweep", not _bad, str(_bad[:3]))

    # 12. 손실이 커지면 고르는 m 이 줄어들면 안 된다
    _bad = []
    for cert in (3000, 4000, 6000):
        seq = [decide_v2(C=259, cert_bytes=cert, rtt_ms=50.0, p=pp, burst=1.0,
                         s0_base=396.5, c_pkt=34.5)["choice"]["m"]
               for pp in (0.0, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3)]
        if any(seq[i] > seq[i + 1] for i in range(len(seq) - 1)):
            _bad.append((cert, seq))
    _chk("12. chosen m is non-decreasing in p", not _bad, str(_bad[:2]))

    print("")
    print("%d checks, %d failed" % (_n[0], _fail[0]))
    sys.exit(1 if _fail[0] else 0)
