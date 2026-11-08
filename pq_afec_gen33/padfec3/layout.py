import itertools

from padfec import policy, quantum

P_SERVER = quantum.P_SERVER
T_PTO_MS = policy.T_PTO_NO_ACK_MS
T_ACK_SLOPE = policy.T_ACK_RETX_SLOPE
T_ACK_BASE_MS = policy.T_ACK_RETX_BASE_MS
PTO_SAMPLED_MULT = policy.PTO_SAMPLED_RTT_MULT
G2_PARITY_DELAY_MS = 0.3
ONE_RTT_CUTOFF_RTTS = 1.5
K_MAX = 4
M_MAX = 4
LEGACY_LEAD = -1
LATER_MODES = ("v3", "g2", "off")
FAIL_KINDS = ("pto", "ptoS", "ack")
PREFLIGHT_ACK_BYTES = 41


def tau(nbytes, uplink_mbps):
    if not uplink_mbps or uplink_mbps <= 0:
        return 0.0
    return nbytes * 8.0 / (uplink_mbps * 1e3)


def legacy_lead(m):
    return 1 if m >= 2 else 0


def _check_int(name, value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("%s must be int: %r" % (name, value))
    return value


def resolve_lead(m, lead):
    _check_int("m", m)
    _check_int("lead", lead)
    if lead < 0:
        if lead != LEGACY_LEAD:
            raise ValueError("lead must be >= 0 or %d: %r" % (LEGACY_LEAD, lead))
        return legacy_lead(m)
    return lead


def check_action(k, m, lead):
    _check_int("k", k)
    _check_int("m", m)
    _check_int("lead", lead)
    if k < 1 or k > K_MAX:
        raise ValueError("k out of range 1..%d: %r" % (K_MAX, k))
    if m < 0 or m > M_MAX:
        raise ValueError("m out of range 0..%d: %r" % (M_MAX, m))
    if lead < 0 or lead > m:
        raise ValueError("lead out of range 0..m=%d: %r" % (m, lead))


def parity_bytes(w, k):
    return policy.parity_datagram_bytes(w, k)


def send_order(k, m, lead):
    lead = resolve_lead(m, lead)
    check_action(k, m, lead)
    return ["L"] * lead + ["O"] * k + ["P"] * (m - lead)


def client_bytes(k, m, w):
    return k * w + m * parity_bytes(w, k)


def pre_decision_bytes(k, m, lead, w):
    lead = resolve_lead(m, lead)
    check_action(k, m, lead)
    return k * w + lead * parity_bytes(w, k)


def n_need(cert_bytes, *, s0_base, c_pkt):
    if s0_base is None or c_pkt is None:
        raise TypeError("n_need needs explicit s0_base and c_pkt")
    return quantum.bin_needed(cert_bytes, None, s0_base=float(s0_base),
                              c_pkt=float(c_pkt))


def preflight_bytes(k, uplink_mbps):
    _check_int("k", k)
    if not uplink_mbps or uplink_mbps <= 0:
        return 0
    return PREFLIGHT_ACK_BYTES * (k - 1)


def one_rtt_ok(credit, need, a_pre=0):
    return quantum.AMP * credit - a_pre > P_SERVER * (need - 1)


def rtt_count(credit, need, a_pre=0):
    return 1 if one_rtt_ok(credit, need, a_pre) else 2


def race_branches(base, delays, parity):
    out = []
    prev = 1.0
    for i, d in enumerate(delays):
        qi = policy.race_win_prob(d)
        if prev - qi > 0:
            out.append((prev - qi, base + i * parity))
        prev = qi
    if prev > 0:
        out.append((prev, base + len(delays) * parity))
    return out


def response_term(m, w, uplink_mbps, later):
    if later not in LATER_MODES:
        raise ValueError("later must be one of %r: %r" % (LATER_MODES, later))
    if later == "off":
        return 0.0
    tr = tau(w, uplink_mbps)
    if later == "g2":
        if m >= 2:
            tr += tau(parity_bytes(w, 1), uplink_mbps)
        if m >= 1:
            tr += G2_PARITY_DELAY_MS
    return tr


def outcomes(k, m, lead, w, p, uplink_mbps):
    if not 0.0 <= p <= 1.0:
        raise ValueError("p out of range 0..1: %r" % (p,))
    order = send_order(k, m, lead)
    lead = order.count("L")
    pz = parity_bytes(w, k)
    sizes = [w if t == "O" else pz for t in order]
    n = len(order)
    last_o = lead + k - 1
    for pat in itertools.product((0, 1), repeat=n):
        pr = 1.0
        for x in pat:
            pr *= (1 - p) if x else p
        if pr == 0:
            continue
        t = 0.0
        arr_t = [None] * n
        for i in range(n):
            if pat[i]:
                t += tau(sizes[i], uplink_mbps)
                arr_t[i] = t
        la = sum(1 for i in range(lead) if pat[i])
        a = sum(1 for i in range(lead, lead + k) if pat[i])
        trail = [i for i in range(lead + k, n) if pat[i]]
        miss = k - a
        phys = sum(sizes[i] for i in range(n) if pat[i])
        rec = {"pattern": pat, "pr": pr, "arrival_ms": arr_t, "sizes": sizes,
               "lead_arrived": la, "orig_arrived": a, "miss": miss,
               "trail_arrived": len(trail), "phys_bytes": phys}
        if miss == 0 or miss <= len(trail):
            if miss == 0:
                dec_i = last_o
                after = trail
            else:
                dec_i = trail[miss - 1]
                after = trail[miss:]
            t_dec = arr_t[dec_i]
            rec["kind"] = "ok"
            rec["decision_index"] = dec_i
            rec["t_dec"] = t_dec
            rec["phys_at_dec"] = sum(sizes[i] for i in range(dec_i + 1) if pat[i])
            rec["base_credit"] = la * pz + k * w
            rec["after_delays"] = [arr_t[i] - t_dec for i in after]
            rec["after_sizes"] = [sizes[i] for i in after]
            rec["branches"] = race_branches(rec["base_credit"],
                                            rec["after_delays"], pz)
        else:
            if a == 0:
                kind = "pto"
            elif not pat[last_o]:
                kind = "ptoS"
            else:
                kind = "ack"
            rec["kind"] = kind
            rec["t_last_o"] = max([arr_t[i] for i in range(lead, lead + k)
                                   if pat[i]] or [0.0])
        yield rec


def evaluate(k, w, m, lead, p, rtt_ms, uplink_mbps, n_need, later="v3"):
    lead = resolve_lead(m, lead)
    check_action(k, m, lead)
    resp = response_term(m, w, uplink_mbps, later)
    a_pre = preflight_bytes(k, uplink_mbps)
    J = 0.0
    p1 = 0.0
    p2 = 0.0
    n_sum = 0.0
    succ = 0.0
    t_dec_sum = 0.0
    fails = []
    for rec in outcomes(k, m, lead, w, p, uplink_mbps):
        pr = rec["pr"]
        if rec["kind"] != "ok":
            fails.append(rec)
            continue
        for wgt, cred in rec["branches"]:
            nr = rtt_count(cred, n_need, a_pre)
            hct = rec["t_dec"] + rtt_ms * nr + (resp if nr == 2 else 0.0)
            J += pr * wgt * hct
            if nr == 1:
                p1 += pr * wgt
            else:
                p2 += pr * wgt
            n_sum += pr * wgt * nr
            succ += pr * wgt
            t_dec_sum += pr * wgt * rec["t_dec"]
    pf = sum(f["pr"] for f in fails)
    n_ok = n_sum / succ if succ > 1e-15 else 2.0
    M = 1.0 / (1.0 - pf) if pf < 1 else 1.0
    split = {kind: 0.0 for kind in FAIL_KINDS}
    for f in fails:
        kind = f["kind"]
        if kind == "pto":
            c = rtt_ms + T_PTO_MS + tau(k * w, uplink_mbps)
        elif kind == "ptoS":
            c = f["t_last_o"] + n_ok * rtt_ms + PTO_SAMPLED_MULT * rtt_ms
        else:
            c = f["t_last_o"] + n_ok * rtt_ms + (T_ACK_SLOPE * rtt_ms + T_ACK_BASE_MS)
        J += f["pr"] * M * c
        split[kind] += f["pr"]
    return {
        "J": J,
        "p_one_rtt": p1,
        "p_two_rtt": p2,
        "p_success": succ,
        "p_fail": pf,
        "p_fail_pto": split["pto"],
        "p_fail_pto_sampled": split["ptoS"],
        "p_fail_ack": split["ack"],
        "n_rtt_expected": n_sum,
        "n_rtt_given_ok": n_ok,
        "round_mult": M,
        "e": p2 + pf,
        "t_dec_given_ok": (t_dec_sum / succ if succ > 1e-15 else 0.0),
        "response_term_ms": resp,
        "a_pre": a_pre,
        "client_bytes": client_bytes(k, m, w),
        "pre_decision_bytes": pre_decision_bytes(k, m, lead, w),
        "k": k, "m": m, "lead": lead, "trail": m - lead, "w": w,
        "later": later,
    }


def j3(k, w, m, lead, p, rtt_ms, uplink_mbps, n_need, later="v3"):
    return evaluate(k, w, m, lead, p, rtt_ms, uplink_mbps, n_need, later)["J"]


def one_rtt_cutoff_ms(rtt_ms, k, m, lead, w, uplink_mbps):
    return ONE_RTT_CUTOFF_RTTS * rtt_ms + tau(pre_decision_bytes(k, m, lead, w), uplink_mbps)
