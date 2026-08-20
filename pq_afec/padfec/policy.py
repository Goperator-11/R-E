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
    """이 후보에서 '복구 실패' 확률.

    m=0 (아무것도 안 함 / pad) 은 복구 수단이 없으므로 **하나라도 잃으면 실패**다.
    패딩은 복구를 주지 않는다 — 키운 데이터그램 안의 여분 바이트는 그
    데이터그램이 통째로 사라질 때 같이 사라진다(명세 §4, 용량 정리).
    """
    if p <= 0.0:
        return 0.0
    k, m = cand["k"], cand["m"]
    if m <= 0:
        return float(1.0 - erasure_probs(k, p, burst)[0])
    return p_unrecoverable(k, m, p, burst)


def cost_of(cand, rtt_ms, p, burst, t_recover_ms=None, uplink_mbps=10.0):
    """명세 §3 의 J. 낮을수록 좋다."""
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

    뒤에 둘을 더 붙였다.
      - late_parity_risk 가 있는 후보를 뒤로 (명세 §2.6 가설: k=1·m=1 배치는
        패리티가 서버 결정 뒤에 도착해 신용을 못 살 수 있다. p13 전까지는
        **같은 값이면 피한다**는 소극적 처리만 한다 — 신용을 임의로 깎지 않는다.)
      - over_mtu 후보를 뒤로.
    """
    return (round(e["j_ms"], 6),
            e["cand"]["added_bytes"],
            0 if e["cand"]["m"] > 0 else 1,          # 같은 바이트면 패리티 우선
            1 if e["cand"]["late_parity_risk"] else 0,
            1 if e["cand"]["over_mtu"] else 0,
            e["cand"]["mode"])


def decide_v2(C, cert_bytes, rtt_ms, p, burst, s0=None,
              W=quantum.P_SERVER, h=51, f=16,
              max_steps=2, m_max=2,
              s0_base=None, c_pkt=0.0,
              t_recover_ms=None, uplink_mbps=10.0,
              max_ips=QUICGO_MAX_IPS, allow_repack=False):
    """이 조건에서 첫 비행을 어떻게 만들지 고른다 (δ 와 m 을 함께).

    돌려주는 것: 고른 후보와 그 근거, 후보 전부의 J, 그리고 배제된 후보와 사유.

    max_ips — 이 값을 넘는 W_eff 는 **보낼 수 없으므로** 후보에서 뺀다(실측 근거는
    QUICGO_MAX_IPS 주석). None 을 주면 거르지 않는다(모형 탐색용).
    allow_repack — 'pad_repack'(데이터그램을 합쳐 재패킹) 후보를 넣을지.
    기본은 False 다. 재패킹은 CRYPTO 를 다시 쪼개는 실제 구현 변경을 요구하는데
    우리 테스트베드는 그걸 안 한다 — 모형에만 있는 선택지를 고르면 안 된다.
    """
    cands = quantum.levers(C, cert_bytes, s0, W=W, h=h, f=f,
                           max_steps=max_steps, m_max=m_max,
                           s0_base=s0_base, c_pkt=c_pkt)

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
        e = cost_of_v2(c, W, rtt_ms, p, burst, t_recover_ms, uplink_mbps)
        e["cand"] = c
        scored.append(e)
    scored.sort(key=_rank_key)

    best = scored[0]
    base = next((e for e in scored if e["cand"]["mode"] == "none"), scored[-1])

    reason = []
    bc, bs = best["cand"], base["cand"]
    if bc is not bs:
        if bc["n_rtt"] < bs["n_rtt"]:
            reason.append("증폭 신용으로 왕복 %d회 절약 (추가 %d B)"
                          % (bs["n_rtt"] - bc["n_rtt"], bc["added_bytes"]))
        if best["p_fail"] < base["p_fail"]:
            reason.append("손실 복구로 실패 확률 %.4f -> %.4f"
                          % (base["p_fail"], best["p_fail"]))
        if bc["mode"] == "pad" and bc["added_bytes"] < W:
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
        "t_recover_ms": rtt_ms if t_recover_ms is None else t_recover_ms,
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


def _binom_pmf(n, k, q):
    """policy.go binomPMF 와 동일(같은 곱셈 순서)."""
    if k < 0 or k > n:
        return 0.0
    c = 1.0
    for i in range(k):
        c = c * float(n - i) / float(i + 1)
    return c * (q ** k) * ((1.0 - q) ** (n - k))


def expected_n_rtt(k, m, w, p, server_flight):
    """기대 왕복 수. policy.go expectedNRtt 의 이식.

    도착한 원본 i 개와 패리티 j 개의 모든 경우에 기댓값을 낸다.
    **복구된 원본의 바이트는 세지 않는다** — 회계 규칙상 복구본을 넣을 때
    패리티를 버리므로, 서버가 실제로 센 바이트만 예산이 된다.
    """
    parity = parity_datagram_bytes(w, k)
    q = 1.0 - p
    tot = 0.0
    for i in range(k + 1):
        pi = _binom_pmf(k, i, q)
        if pi <= 0:
            continue
        for j in range(m + 1):
            pj = _binom_pmf(m, j, q)
            if pj <= 0:
                continue
            n = 1.0
            if server_flight > float(quantum.allowed(i * w + j * parity)):
                n = 2.0
            tot += pi * pj * n
    return tot


def client_bytes_of(cand):
    """이 후보가 실제로 내보내는 클라이언트 바이트 (패리티 크기 반영)."""
    k, m, w = cand["k"], cand["m"], cand["W_eff"]
    return k * w + m * parity_datagram_bytes(w, k)


def cost_of_v2(cand, W_base, rtt_ms, p, burst,
               t_recover_ms=None, uplink_mbps=10.0):
    """명세 §3 의 J — Go 와 같은 식으로 다시 계산한다.

    quantum.levers 가 준 n_rtt/allowed 는 후보 생성용 근사이고, 여기서
    (1) 기대 왕복 수 (2) 실제 패리티 크기 를 반영해 덮어쓴다.
    """
    if t_recover_ms is None:
        t_recover_ms = rtt_ms
    k, m, w = cand["k"], cand["m"], cand["W_eff"]
    cb = client_bytes_of(cand)
    # 기준선은 "아무것도 안 함" = k0 개 x W_base. k0 는 pad/parity 후보의 k 와
    # 같다(levers 가 k_floor=k0 로 고정한다). pad_repack 만 k 가 작을 수 있는데
    # 그 후보는 decide_v2 가 기본으로 뺀다.
    added = max(0, cb - k * W_base)
    n_exp = expected_n_rtt(k, m, w, p, cand["server_flight"])
    pf = p_fail_of(cand, p, burst)
    tx = tx_cost_ms(added, uplink_mbps)
    return {
        "j_ms": n_exp * rtt_ms + pf * t_recover_ms + tx,
        "n_rtt_expected": n_exp,
        "client_bytes_real": cb,
        "added_bytes_real": added,
        "allowed_real": quantum.allowed(cb),
        "base_ms": n_exp * rtt_ms,
        "stall_ms": pf * t_recover_ms,
        "tx_ms": tx,
        "p_fail": pf,
    }
