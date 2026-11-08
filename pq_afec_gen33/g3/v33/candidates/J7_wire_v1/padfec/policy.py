from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from afec.channel import GilbertElliott

from . import amplif, capacity, quantum

M_MAX_DEFAULT = 3

QUICGO_MAX_IPS = 1452

C_PKT_POLICY_DEFAULT = 41.983

S0_BASE_X25519 = 382.45
S0_BASE_MLKEM = 1472.00

MAX_STEPS_DEFAULT = 2

PTO_NO_SAMPLE_MS = 999.0

DEFAULT_ASSUMED_BURST = 1.0

T_PTO_NO_ACK_MS = 200.86
T_ACK_RETX_SLOPE = 1.1250
T_ACK_RETX_BASE_MS = 1.424


PTO_SAMPLED_RTT_MULT = 3.0


def pto_with_rtt_sample_ms(rtt_ms):
    return PTO_SAMPLED_RTT_MULT * float(rtt_ms)


def default_t_recover(rtt_ms, arrived_any):
    if arrived_any:
        return T_ACK_RETX_SLOPE * float(rtt_ms) + T_ACK_RETX_BASE_MS
    return T_PTO_NO_ACK_MS


def erasure_probs(n_symbols, p, burst):
    ge = GilbertElliott.for_prior(p, burst)
    return ge.erasure_pmf(n_symbols)


def p_unrecoverable(k, m, p, burst):
    if p <= 0.0:
        return 0.0
    pmf = erasure_probs(k + m, p, burst)
    return float(sum(pmf[e] for e in range(m + 1, len(pmf))))


UPLINK_UNSHAPED = 0.0
UPLINK_MOBILE_MBPS = 10.0
UPLINK_CONSTRAINED_MBPS = 2.0
UPLINK_MBPS_DEFAULT = UPLINK_MOBILE_MBPS

J_TIE_MS = 0.01


def tx_cost_ms(extra_bytes, uplink_mbps):
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


def p_fail_of(cand, p, burst):
    if p <= 0.0:
        return 0.0
    k, m = cand["k"], cand["m"]
    g = recovery_group(k, m)
    pm = joint_arrival_pmf3c(k, m, p, burst)
    return float(sum(pm[a_][b_][c_]
                     for a_ in range(k + 1) for b_ in range(m + 1)
                     for c_ in range(g + 1)
                     if (k - a_) > 0 and not recovers(k, a_, c_)))


def cost_of(cand, rtt_ms, p, burst, t_recover_ms=None, uplink_mbps=UPLINK_MBPS_DEFAULT):
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
    return (e["added_bytes_real"],
            0 if e["cand"]["m"] > 0 else 1,
            1 if e["cand"]["late_parity_risk"] else 0,
            1 if e["cand"]["over_mtu"] else 0,
            e["cand"]["mode"])


def _pick_best(scored):
    exact = sorted(scored, key=lambda e: (e["j_ms"],) + _tie_key(e))
    j_min = exact[0]["j_ms"]
    tied = [e for e in exact if e["j_ms"] <= j_min + J_TIE_MS]
    tied.sort(key=_tie_key)
    rest = [e for e in exact if e["j_ms"] > j_min + J_TIE_MS]
    return tied + rest


def _rank_key(e):
    return (round(e["j_ms"], 6),
            e["added_bytes_real"],
            0 if e["cand"]["m"] > 0 else 1,
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
        e = cost_of_v2(c, W, rtt_ms, p, burst, t_recover_ms, uplink_mbps,
                       k0=k0, t_recover_ack_ms=t_recover_ack_ms)
        e["cand"] = c
        scored.append(e)
    scored = _pick_best(scored)

    best = scored[0]
    base = next((e for e in scored if e["cand"]["mode"] == "none"), scored[-1])

    reason = []
    bc, bs = best["cand"], base["cand"]
    if bc is not bs:
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
        "t_pto_ms": best["t_pto_ms"],
        "t_ack_ms": best["t_ack_ms"],
    }


PARITY_OVERHEAD_BASE = 46
PARITY_OVERHEAD_PER_K = 6
PARITY_DATAGRAM_MAX = 1452


def parity_datagram_bytes(w, k):
    return w + PARITY_OVERHEAD_BASE + PARITY_OVERHEAD_PER_K * k


def flight_order(k, m):
    if m <= 0:
        return ["O"] * k
    if m == 1:
        return ["O"] * k + ["P"]
    return ["P"] + ["O"] * k + ["P"] * (m - 1)


def joint_arrival_pmf(k, m, p, burst):
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


MAX_RECOVERY_ROUNDS = 20


def expected_rounds(k, m, p, burst):
    if p <= 0.0:
        return 1.0
    k = int(k)
    m = int(m)
    dist = None
    alive = 1.0
    extra = 0.0
    for _ in range(MAX_RECOVERY_ROUNDS):
        st = _joint3c_state(k, m, p, burst, dist)
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
        extra += alive * pf
        alive *= pf
        if alive <= 1e-15:
            break
        dist = [fg / pf, fb / pf]
    return 1.0 + extra


def recovery_group(k, m):
    if m <= 0:
        return 0
    return 1 if m == 1 else m - 1


def _joint3c_state(k, m, p, burst, init=None):
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
    order = flight_order(k, m)
    return max((i for i, t in enumerate(order) if t == "O"), default=-1)


def last_original_pmf(k, m, p, burst):
    ge = GilbertElliott.for_prior(p, burst)
    order = flight_order(k, m)
    trans = ge.transition
    loss = (ge.p_good, ge.p_bad)
    pi = ge.stationary
    last_o = last_original_index(k, m)
    g = recovery_group(k, m)

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
    miss = k - a
    if miss <= 0:
        return False
    return miss <= int(recovery_parity_count)


def n_need_for_flight(server_flight, pkt=quantum.P_SERVER):
    import math
    return max(1, int(math.ceil(float(server_flight) / float(pkt))))


RACE_DELAY_MS = (0.0, 0.133, 0.266, 0.355, 0.533, 0.710, 1.066)
RACE_WIN_Q = (1.0, 0.996, 0.972, 0.640, 0.404, 0.212, 0.004)


def trailing_parity_delay_ms(k, w, uplink_mbps):
    if not uplink_mbps or uplink_mbps <= 0:
        return 0.0
    return parity_datagram_bytes(w, k) * 8.0 / (float(uplink_mbps) * 1e6) * 1e3


def race_win_prob(delay_ms):
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
    parity = parity_datagram_bytes(w, k)
    g = recovery_group(k, m)
    pm = joint_arrival_pmf3c(k, m, p, burst)
    n_sum = 0.0
    p_fail = 0.0
    p_two = 0.0
    p_rec = 0.0
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
                    continue
                used = miss if rec else 0
                b_credit = b_ - used
                if rec:
                    p_rec += pr
                    _lead_arrived = b_ - c_
                    _late_trail = c_ - miss
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
                _lead_arrived = b_ - c_
                for wgt, arrived in credit_branches(a_, w, parity,
                                                    _lead_arrived, c_,
                                                    trail_delay_ms):
                    if quantum.bin_index(arrived) < n_need:
                        n_sum += pr * wgt * 2.0
                        p_two += pr * wgt
                    else:
                        n_sum += pr * wgt
    p_fail_pto, p_fail_pto_sampled, p_fail_ack = fail_split(k, m, p, burst)
    ok = 1.0 - p_fail
    return {
        "n_rtt_expected": n_sum,
        "n_rtt_given_ok": (n_sum / ok if ok > 1e-15 else 2.0),
        "p_fail": p_fail,
        "p_fail_pto": p_fail_pto,
        "p_fail_pto_sampled": p_fail_pto_sampled,
        "p_fail_ack": p_fail_ack,
        "p_two_rtt": p_two,
        "p_recoverable": ok,
        "p_recovered": p_rec,
        "trail_bytes_expected": trail_bytes,
    }


def client_bytes_of(cand):
    k, m, w = cand["k"], cand["m"], cand["W_eff"]
    return k * w + m * parity_datagram_bytes(w, k)


def critical_path_bytes(k, m, w):
    if m >= 2:
        return k * w + parity_datagram_bytes(w, k)
    return k * w


def trailing_parity_bytes(k, m, w):
    if m <= 0:
        return 0
    parity = parity_datagram_bytes(w, k)
    return parity * (m - 1 if m >= 2 else 1)


def cost_of_v2(cand, W_base, rtt_ms, p, burst,
               t_recover_ms=None, uplink_mbps=UPLINK_MBPS_DEFAULT, k0=None,
               t_recover_ack_ms=None):
    t_pto = (default_t_recover(rtt_ms, False) if t_recover_ms is None
             else float(t_recover_ms))
    t_ack = (default_t_recover(rtt_ms, True) if t_recover_ack_ms is None
             else float(t_recover_ack_ms))
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
    out = flight_outcome(k, m, w, p, burst, cand["n_need"],
                         trail_delay_ms=trailing_parity_delay_ms(
                             k, w, uplink_mbps))
    n_exp = out["n_rtt_expected"]
    pf = out["p_fail"]
    n_ok = out["n_rtt_given_ok"]
    t_pto_s = pto_with_rtt_sample_ms(rtt_ms)
    _R = expected_rounds(k, m, p, burst)
    _pf = out["p_fail"]
    _mult = ((_R - 1.0) / _pf) if _pf > 1e-15 else 1.0
    stall = _mult * (out["p_fail_pto"] * (rtt_ms + t_pto)
                     + out["p_fail_pto_sampled"] * (n_ok * rtt_ms + t_pto_s)
                     + out["p_fail_ack"] * (n_ok * rtt_ms + t_ack))
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

    worst_neg = 0.0
    worst_m1 = 0.0
    gap_m2 = 0.0
    for k in (1, 2, 3, 4):
        for m in (1, 2):
            for pp in (0.01, 0.05, 0.2):
                for LL in (1.0, 2.0, 5.0):
                    va = p_fail_of({"k": k, "m": m}, pp, LL)
                    vb = p_unrecoverable(k, m, pp, LL)
                    worst_neg = max(worst_neg, vb - va)
                    if m == 1:
                        worst_m1 = max(worst_m1, abs(va - vb))
                    else:
                        gap_m2 = max(gap_m2, va - vb)
    _chk("3. p_fail_of >= MDS 하한, m=1 에서는 일치",
         worst_neg < 1e-12 and worst_m1 < 1e-12,
         "MDS 초과 %.3g / m=1 차 %.3g" % (worst_neg, worst_m1))
    _chk("3a. m=2 에서 구현 규칙이 MDS 와 실제로 갈린다 (시험이 공허하지 않다)",
         gap_m2 > 1e-6, "최대 차 %.4g (0 이면 결함이 되살아난 것)" % gap_m2)

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

    _s0 = S0_BASE_X25519 + 7 * C_PKT_POLICY_DEFAULT
    _o = flight_outcome(1, 1, 1280, 0.05, 1.0,
                        n_need_for_flight(4032 + _s0))
    _chk("3c. 복구 상태의 신용 하락이 반영된다 (실측 p15 9.0% / p14 8.0%)",
         abs(_o["p_two_rtt"] - 0.095) < 1e-3,
         "p_two_rtt %.4f (옛 회계는 0.0475)" % _o["p_two_rtt"])

    o1 = flight_outcome(2, 1, 1280, 0.05, 1.0, n_need_for_flight(6000.0))
    o5 = flight_outcome(2, 1, 1280, 0.05, 5.0, n_need_for_flight(6000.0))
    _chk("4. n_rtt term reacts to burst (defect 1)",
         abs(o1["n_rtt_expected"] - o5["n_rtt_expected"]) > 1e-6,
         "L=1 %.6f vs L=5 %.6f" % (o1["n_rtt_expected"],
                                   o5["n_rtt_expected"]))

    o = flight_outcome(1, 0, 1280, 0.2, 1.0, n_need_for_flight(3000.0))
    _chk("5. n-term mass == 1 - p_fail (defect 2)",
         abs(o["p_recoverable"] - 0.8) < 1e-12
         and abs(o["n_rtt_expected"] - 0.8) < 1e-12,
         "n=%.6f p_ok=%.6f" % (o["n_rtt_expected"], o["p_recoverable"]))
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
    _R5 = expected_rounds(1, 0, 0.2, 1.0)
    _exp5 = 40.0 + (_R5 - 1.0) * (50.0 + 50.0)
    _chk("5b. J = base + (R-1)x(rtt+T_rec)  (k=1 m=0 p=0.2, R=1/(1-p) 무기억)",
         abs(_R5 - 1.25) < 1e-12 and abs(e["j_ms"] - _exp5) < 1e-9,
         "R=%.6f J=%.4f 기대 %.4f" % (_R5, e["j_ms"], _exp5))

    _chk("5c. k=1,m=0 failure is always the PTO branch",
         abs(o["p_fail_pto"] - o["p_fail"]) < 1e-12 and o["p_fail_ack"] == 0.0,
         "pto=%.6f ack=%.6f" % (o["p_fail_pto"], o["p_fail_ack"]))
    o2 = flight_outcome(2, 0, 1280, 0.2, 1.0, n_need_for_flight(3000.0))
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

    r = decide_v2(C=259, cert_bytes=4000, rtt_ms=50.0, p=0.0, burst=1.0,
                  s0_base=396.5, c_pkt=34.5)
    _chk("7. headline: 1-byte pad still chosen",
         r["choice"]["mode"] == "pad" and r["choice"]["delta_per_dgram"] == 1,
         "%s d=%d gain=%.3f" % (r["choice"]["mode"],
                                r["choice"]["delta_per_dgram"], r["gain_ms"]))

    _bad = []
    for cert in range(2000, 9001, 250):
        r = decide_v2(C=259, cert_bytes=cert, rtt_ms=50.0, p=0.05, burst=1.0,
                      s0_base=396.5, c_pkt=34.5)
        for c in r["candidates"]:
            if c["added_bytes"] != c["added_bytes_real"]:
                _bad.append((cert, c["mode"], c["m"]))
    _chk("8. cand added_bytes == added_bytes_real (defect 4)",
         not _bad, str(_bad[:3]))

    _bad = []
    for cert in range(2000, 9001, 100):
        r = decide_v2(C=259, cert_bytes=cert, rtt_ms=50.0, p=0.0, burst=1.0,
                      s0_base=396.5, c_pkt=34.5, uplink_mbps=0.0)
        for c in r["candidates"]:
            if abs(c["n_rtt"] - c["n_rtt_expected"]) > 1e-9:
                _bad.append((cert, c["mode"], c["m"]))
    _chk("9. levers n_rtt == expected n_rtt at p=0, uplink 0 (defect 4)",
         not _bad, str(_bad[:3]))

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

    _xs = [i * 0.01 for i in range(0, 300)]
    _qs = [race_win_prob(x) for x in _xs]
    _mono = all(_qs[i + 1] <= _qs[i] + 1e-12 for i in range(len(_qs) - 1))
    _chk("9c. race_win_prob is monotone, q(0)=1, q(2ms)=0",
         _mono and race_win_prob(0.0) == 1.0 and race_win_prob(2.0) == 0.0,
         "q(0)=%.3f q(0.5)=%.3f q(1)=%.3f q(2)=%.3f"
         % (race_win_prob(0.0), race_win_prob(0.5), race_win_prob(1.0),
            race_win_prob(2.0)))

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

    r = decide_v2(C=1150, cert_bytes=6000, rtt_ms=50.0, p=0.0, burst=1.0,
                  s0=1734.5, W=1200, allow_repack=True, max_ips=None)
    _k0 = capacity.natural_k(1150, 1200, 51)
    _bad = [(c["mode"], c["added_bytes_real"])
            for c in r["candidates"] if c["mode"] == "pad_repack"
            and c["added_bytes_real"] != max(0, c["client_bytes_real"]
                                             - _k0 * 1200)]
    _chk("10. pad_repack added measured vs baseline k0 (defect 4)",
         not _bad, str(_bad[:2]))

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
                    tied = [c for c in cs if c["j_ms"] <= jmin + J_TIE_MS]
                    if tied and (r["choice_cost"]["added_bytes_real"]
                                 > min(c["added_bytes_real"] for c in tied)):
                        _bad.append((C, cert, pp, LL, "bytes"))
                    if r["gain_ms"] < -1e-9:
                        _bad.append((C, cert, pp, LL, r["gain_ms"]))
    _chk("11. 고른 후보가 (J 최소 +- 분해능) 이고 그 안에서 바이트 최소",
         not _bad, "%d 조건 / 위반 %s" % (_n11, _bad[:3]))

    _bad = []
    for cert in (3000, 4000, 6000):
        seq = [decide_v2(C=259, cert_bytes=cert, rtt_ms=50.0, p=pp, burst=1.0,
                         s0_base=396.5, c_pkt=34.5)["choice"]["m"]
               for pp in (0.0, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3)]
        if any(seq[i] > seq[i + 1] for i in range(len(seq) - 1)):
            _bad.append((cert, seq))
    _chk("12. chosen m is non-decreasing in p", not _bad, str(_bad[:2]))

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
            for _m in (0, 1, 2):
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
            for _dl in (0, 1, 81):
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
            _v = _r["choice_cost"]["j_ms"]
            if _prevc is not None and _v < _prevc - 1e-9:
                _bc.append((_C, _cert, round(_prevc, 4), round(_v, 4)))
            _prevc = _v
    _chk("13. 대역 비용 0 에서 delta 를 키우면 J 가 늘지 않는다",
         not _bd, str(_bd[:3]))
    _chk("14. 대역 비용 0 에서 m 을 키우면 J 가 늘지 않는다",
         not _bm, str(_bm[:3]))
    _chk("15. cert 를 키우면 정책의 최적 J 가 줄지 않는다",
         not _bc, str(_bc[:3]))

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

    def _J(m, up, p, cert=9000):
        d = decide_v2(C=1450, cert_bytes=cert, rtt_ms=50.0, p=p, burst=1.0,
                      s0_base=S0_BASE_MLKEM, c_pkt=C_PKT_POLICY_DEFAULT,
                      W=1280, max_steps=2, m_max=3, uplink_mbps=up)
        return min(c["j_ms"] for c in d["candidates"] if c["m"] == m)

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

    _du = _J(3, 0.0, 0.02) - _J(2, 0.0, 0.02)
    _chk("17d. [부정] 무제한에서는 m3 이 여전히 싸다 (새 항이 0 이라 옛 식과 같다)",
         _du < 0, "모형 m3-m2 = %+.3f ms" % _du)

    def _cost(m, cert, p, up=0.0, k=2, w=1280):
        d = decide_v2(C=1450, cert_bytes=cert, rtt_ms=50.0, p=p, burst=1.0,
                      s0_base=S0_BASE_MLKEM, c_pkt=C_PKT_POLICY_DEFAULT,
                      W=w, max_steps=2, m_max=max(m, 1), uplink_mbps=up)
        cs = [c for c in d["candidates"]
              if c["m"] == m and c.get("delta_per_dgram", 0) == 0
              and c["mode"] in ("none", "parity")]
        return min(cs, key=lambda e: e["j_ms"])

    _w18 = 0.0
    for _cert in (3000, 9000, 15000):
        for _m in (0, 1, 2, 3):
            _c = _cost(_m, _cert, 0.0)
            _w18 = max(_w18, _c["p_fail_ack"], _c["p_fail_pto"])
    _chk("18a. [안전판] 무손실이면 실패 가지 질량이 정확히 0 (옛 식과 같다)",
         _w18 == 0.0, "최대 실패 질량 %.3e" % _w18)

    _c0 = _cost(0, 9000, 0.15)
    _n_ok0 = _c0["n_rtt_given_ok"]
    _gap = _c0["p_fail_ack"] * (_n_ok0 - 1.0) * 50.0
    _chk("18b. 기준선이 2 왕복인 팔은 실패 가지가 왕복 하나만큼 더 든다",
         _n_ok0 > 1.99 and _gap > 5.0,
         "n_rtt|ok = %.3f, 옛 식이 빠뜨리던 양 %.2f ms" % (_n_ok0, _gap))

    _c3 = _cost(3, 9000, 0.15)
    _gap3 = _c3["p_fail_ack"] * (_c3["n_rtt_given_ok"] - 1.0) * 50.0
    _chk("18c. [부정] 기준선이 1 왕복인 팔은 옛 식과 사실상 같다",
         _gap3 < 0.2, "n_rtt|ok = %.3f, 차이 %.3f ms"
         % (_c3["n_rtt_given_ok"], _gap3))

    _pto_only = _c0["p_fail_pto"] * (50.0 + _c0["t_pto_ms"])
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

    _fs = fail_split(3, 0, 0.2, 1.0)
    _chk("19b. 마지막 원본 유실이 ACK 가지가 아니라 PTO 가지로 간다",
         abs(_fs[0] - 0.008) < 1e-12 and abs(_fs[1] - 0.192) < 1e-12
         and abs(_fs[2] - 0.288) < 1e-12,
         "표본없는PTO %.4f / 표본있는PTO %.4f / 시간임계 %.4f" % _fs)

    _fs1 = fail_split(1, 0, 0.2, 1.0)
    _chk("19c. [부정] k=1 에서는 세 번째 가지가 비어 있다 (사건이 같다)",
         _fs1[1] == 0.0 and _fs1[2] == 0.0 and abs(_fs1[0] - 0.2) < 1e-12,
         "표본없는PTO %.4f / 표본있는PTO %.4f / 시간임계 %.4f" % _fs1)

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

    _f1 = p_fail_of({"k": 2, "m": 1}, 0.15, 1.0)
    _f2 = p_fail_of({"k": 2, "m": 2}, 0.15, 1.0)
    _f3 = p_fail_of({"k": 2, "m": 3}, 0.15, 1.0)
    _chk("20c. m=3 이 m=2 보다 실제로 안전하다 (m<=2 는 여전히 같다)",
         abs(_f1 - _f2) < 1e-15 and _f3 < _f2 * 0.5,
         "k=2 p=0.15  m1 %.5f = m2 %.5f > m3 %.5f (%.1f 배)"
         % (_f1, _f2, _f3, _f2 / _f3 if _f3 > 0 else float("inf")))

    _r21 = [expected_rounds(k, m, 0.0, L)
            for k in (1, 2, 3) for m in (0, 1, 2, 3) for L in (1.0, 3.0, 5.0)]
    _chk("21a. [안전판] 무손실이면 R 이 **정확히** 1.0 (옛 실측 불변)",
         all(x == 1.0 for x in _r21), "최대 %.17g" % max(_r21))

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

    _w21c = 0.0
    for _p in (0.02, 0.05, 0.15, 0.25):
        _got = expected_rounds(1, 0, _p, 1.0)
        _w21c = max(_w21c, abs(_got - 1.0 / (1.0 - _p)))
    _chk("21c. [안전판] k=1 m=0 버스트1 은 정확히 1/(1-p) (무기억 닫힌해)",
         _w21c < 1e-9, "최대 차이 %.3e" % _w21c)

    _r1 = expected_rounds(2, 1, 0.15, 1.0)
    _r5 = expected_rounds(2, 1, 0.15, 5.0)
    _chk("21d. [부정] 버스트가 R 을 키운다 (상태 이어받기가 공허하지 않다)",
         _r5 > _r1 * 1.15,
         "L=1 %.5f -> L=5 %.5f (%.2f 배)" % (_r1, _r5, _r5 / _r1))

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
