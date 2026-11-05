import hashlib

from padfec import policy, quantum
from padfec3 import layout, learn3

MAX_STEPS = policy.MAX_STEPS_DEFAULT
M_MAX = layout.M_MAX
MAX_IPS = policy.QUICGO_MAX_IPS
UDP_MAX = quantum.TYPICAL_MTU - 28
J_TIE = policy.J_TIE_MS
MIN_W = learn3.MIN_W
CHOICE_KEYS = ("action", "delta", "lead", "T", "m", "mode", "W_eff",
               "client_bytes", "added", "ej", "pen", "score", "n2")


def parity_bytes(w, k):
    return policy.parity_datagram_bytes(w, k)


def check_candidate_options(max_ips, m_max, max_steps):
    m_max = learn3._int("m_max", m_max)
    max_steps = learn3._nonnegative_int("max_steps", max_steps)
    if m_max < 0 or m_max > M_MAX:
        raise ValueError("m_max must be in 0..%d: %r" % (M_MAX, m_max))
    if max_ips is not None:
        max_ips = learn3._int("max_ips", max_ips)
        if max_ips != 0 and max_ips < MIN_W:
            raise ValueError("max_ips must be 0 or >= %d: %r" % (MIN_W, max_ips))


def levers_s(k, w, max_steps, m_max, S, c_pkt, max_ips, *, a_pre=0, prefix=None):
    check_candidate_options(max_ips, m_max, max_steps)
    quantum.required_credit(0 if prefix is None else prefix, a_pre)
    base = k * w
    base_bin = quantum.bin_index(base)

    def mk(mode, m, delta):
        w_eff = w + delta
        learn3.check_model_arithmetic(w_eff, 0.0, 0.0)
        return {"mode": mode, "m": m, "delta": delta, "W_eff": w_eff,
                "client_bytes": k * w_eff + m * parity_bytes(w_eff, k)}

    out = [mk("none", 0, 0)]
    for j in range(1, max_steps + 1):
        delta = quantum._ceil_div(quantum.delta_min(base, j, a_pre=a_pre), k)
        out.append(mk("pad", 0, delta))
    for m in range(1, m_max + 1):
        out.append(mk("parity", m, 0))
    for j in range(1, max_steps + 1):
        dj = quantum.delta_min(base, j, a_pre=a_pre)
        if dj >= w:
            m = quantum._ceil_div(dj, parity_bytes(w, k))
            if m > m_max:
                break
            out.append(mk("parity", m, 0))
    seen = set()
    uniq = []
    for c in out:
        key = (c["mode"], c["client_bytes"], c["m"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
    max_delta = None
    if max_ips is not None and max_ips > 0:
        max_delta = max(0, max_ips - w)
    n_need = learn3.bin_needed_s(S, base_bin, c_pkt)
    ovh = parity_bytes(w, k) - w
    byte_seen = set((c["client_bytes"], c["m"]) for c in uniq)
    for m in range(0, m_max + 1):
        for d in quantum._combo_deltas(k, m, w, ovh, n_need, quantum.P_SERVER,
                                       max_delta, a_pre=a_pre, prefix=prefix):
            c = mk("combo", m, d)
            key = (c["client_bytes"], c["m"])
            if key in byte_seen:
                continue
            byte_seen.add(key)
            uniq.append(c)
    return uniq


def _cand(mode, delta, lead, t, k, w):
    m = lead + t
    w_eff = w + delta
    cb = k * w_eff + m * parity_bytes(w_eff, k)
    added = cb - k * w
    if added < 0:
        added = 0
    return {"action": (delta, lead, t), "delta": delta, "lead": lead, "T": t,
            "m": m, "mode": mode, "W_eff": w_eff, "client_bytes": cb,
            "added": added}


def candidates3(k, w, S, c_pkt, *, max_ips=MAX_IPS, m_max=M_MAX,
                max_steps=MAX_STEPS, a_pre=0, prefix=None):
    check_candidate_options(max_ips, m_max, max_steps)
    if max_ips:
        if w > max_ips:
            return []
        base = k * w
        base_bin = quantum.bin_index(base)
        pad_last = ((quantum.AMP * k * max_ips - 1) // quantum.P_SERVER
                    - base_bin + 1)
        parity_last = ((quantum.AMP * (base + m_max * parity_bytes(w, k)) - 1)
                       // quantum.P_SERVER - base_bin + 1)
        max_steps = min(max_steps, max(0, pad_last, parity_last))
    out = []
    seen = set()
    for c in levers_s(k, w, max_steps, m_max, S, c_pkt, max_ips, a_pre=a_pre, prefix=prefix):
        if c["m"] > m_max:
            continue
        if max_ips is not None and max_ips > 0 and c["W_eff"] > max_ips:
            continue
        if c["m"] > 0 and parity_bytes(c["W_eff"], k) > UDP_MAX:
            continue
        m = c["m"]
        leads = [0] if m == 0 else list(range(0, m + 1))
        for lead in leads:
            a = (c["delta"], lead, m - lead)
            if a in seen:
                continue
            seen.add(a)
            out.append(_cand(c["mode"], c["delta"], lead, m - lead, k, w))
    return out


def mode_of(action):
    d, lead, t = action
    if lead + t == 0:
        return "none" if d == 0 else "pad"
    return "parity" if d == 0 else "combo"


def explicit_candidates(actions, k, w):
    out = []
    for a in actions:
        d, lead, t = learn3.check_action(tuple(a))
        out.append(_cand(mode_of((d, lead, t)), d, lead, t, k, w))
    return out


def cand_hash(cands):
    s = ";".join("%d,%d,%d" % c["action"] for c in cands)
    return hashlib.sha256(s.encode("ascii")).hexdigest()


def tie_key(c):
    legacy = 0 if c["lead"] == layout.legacy_lead(c["m"]) else 1
    return (c["added"], 0 if c["m"] > 0 else 1, c["mode"], legacy, c["score"],
            c["lead"], c["m"], c["delta"])


def pick(cands):
    jmin = min(c["score"] for c in cands)
    tied = [c for c in cands if c["score"] <= jmin + J_TIE]
    return min(tied, key=tie_key), jmin, len(tied)


def choice_of(c):
    return {key: c[key] for key in CHOICE_KEYS}


def take(res, choice):
    for key in CHOICE_KEYS:
        res[key] = choice[key]
    res["j3_pred_pre_ms"] = choice["ej"]


def decide_core(post, k, W, S, u_mbps, rtt_ms, c_pkt, *, actions=None,
                later=learn3.LATER_DEFAULT, max_ips=MAX_IPS, m_max=M_MAX,
                max_steps=MAX_STEPS, keep_cands=False, pen=None, reeval=False, size_distribution=None):
    learn3.check_transport(W, u_mbps, rtt_ms, c_pkt)
    learn3.check_later(later)
    check_candidate_options(max_ips, m_max, max_steps)
    k = learn3._int("k", k)
    if k < 1 or k > layout.K_MAX:
        raise ValueError("k must be in 1..%d: %r" % (layout.K_MAX, k))
    learn3._finite("S", S, positive=True)
    post = learn3.check_probabilities("posterior", post, len(learn3.G))
    n_need = learn3.bin_needed_s(S, quantum.bin_index(k * W), c_pkt)
    ctx = {"k": k, "S": float(S), "n_need": n_need, "W": W,
           "u": float(u_mbps), "rtt": float(rtt_ms)}
    if size_distribution is not None:
        ctx = learn3.size_context(ctx, size_distribution)
        n_need = ctx["n_need"]
    if actions is None:
        if size_distribution is None:
            cands = candidates3(k, W, S, c_pkt, max_ips=max_ips, m_max=m_max,
                                max_steps=max_steps)
        else:
            cands, seen = [], set()
            for component in ctx["size_distribution"]:
                for candidate in candidates3(k, W, component["S"], c_pkt, max_ips=max_ips, m_max=m_max,
                                               max_steps=max_steps, a_pre=ctx["a_pre"], prefix=component["prefix"]):
                    if candidate["action"] not in seen:
                        seen.add(candidate["action"])
                        cands.append(candidate)
    else:
        cands = explicit_candidates(actions, k, W)
    if not cands:
        raise RuntimeError("no candidates")
    support = [g for g in range(len(post)) if post[g] != 0.0]
    for c in cands:
        learn3.check_model_arithmetic(c["W_eff"], u_mbps, rtt_ms)
        ej = 0.0
        for g in support:
            ej += post[g] * learn3.context_model_result(ctx, c["action"], g, later)[0][0]
        c["ej"] = learn3._finite("expected model cost", ej)
        c["pen"] = 0.0
        if pen:
            c["pen"] = learn3._finite(
                "guard penalty", pen.get(learn3.arm_key(c["action"]), 0.0))
        c["score"] = learn3._finite("decision cost", c["ej"] + c["pen"])
        e0 = learn3.context_model_result(ctx, c["action"], 0, later)[0][1]
        c["n2"] = e0 >= learn3.SHIELD_E0
    best, jmin, n_tied = pick(cands)
    n1 = [c for c in cands if not c["n2"]]
    alt = pick(n1)[0] if n1 else None
    res = {"jmin": jmin, "n_tied": n_tied, "n_cands": len(cands),
           "n_need": n_need, "k": k, "S": float(S), "why": "ej",
           "reeval_cond": bool(best["n2"] and alt is not None),
           "alt": None if alt is None else choice_of(alt)}
    if size_distribution is not None:
        res["size_distribution"] = ctx["size_distribution"]
        res["a_pre"] = ctx["a_pre"]
    take(res, best)
    if reeval and res["reeval_cond"]:
        take(res, res["alt"])
        res["why"] = "reeval"
    res["reeval"] = res["why"] == "reeval"
    if keep_cands:
        res["cands"] = cands
    return res


def b0_result(why, post):
    s = learn3.post_summary(post)
    return {"action": learn3.B0, "delta": 0, "lead": 0, "T": 0, "m": 0,
            "mode": "none", "W_eff": None, "client_bytes": None, "added": 0,
            "ej": None, "pen": 0.0, "score": None, "n2": None,
            "j3_pred_pre_ms": None, "jmin": None, "n_tied": 0, "n_cands": 0,
            "n_need": None, "k": None, "S": None, "why": why,
            "reeval_cond": False, "alt": None, "reeval": False,
            "p_mean": s["p_mean"], "p_map": s["p_map"],
            "p_ge_010": s["p_ge_010"]}


def decide3(st, W, u_mbps, rtt_ms, c_pkt, *, actions=None,
            later=learn3.LATER_DEFAULT, max_ips=MAX_IPS, m_max=M_MAX,
            max_steps=MAX_STEPS, keep_cands=False):
    learn3.check_transport(W, u_mbps, rtt_ms, c_pkt, missing_rtt=True)
    learn3.check_later(later)
    check_candidate_options(max_ips, m_max, max_steps)
    if actions is not None:
        actions = [learn3.check_action(tuple(a)) for a in actions]
        for a in actions:
            learn3.check_model_arithmetic(W + a[0], u_mbps, rtt_ms)
    expired = {key for key, at in st.g_alarm.items()
               if st.n_dec - at >= learn3.GUARD_REFRESH}
    b = learn3._finite("guard common delay", learn3.guard_common(st))
    pen = {key: learn3.guard_penalty(st, key, b)
           for key in sorted(st.g_alarm) if key not in expired}
    post = learn3.combined(st)
    learn3.check_probabilities("combined posterior", post, len(learn3.G))
    k = learn3.k_hat(st)
    if st.S_hist and k is not None and 1 <= k <= layout.K_MAX:
        learn3.bin_needed_s(learn3.s_hat(st), quantum.bin_index(k * W), c_pkt)
    if not st.S_hist or not st.k_hist:
        res = b0_result("cold", post)
    elif k < 1 or k > layout.K_MAX:
        res = b0_result("k_range", post)
    elif rtt_ms is None or not rtt_ms > 0:
        res = b0_result("no_rtt", post)
    else:
        res = decide_core(post, k, W, learn3.s_hat(st), u_mbps, rtt_ms, c_pkt,
                          actions=actions, later=later, max_ips=max_ips,
                          m_max=m_max, max_steps=max_steps,
                          keep_cands=keep_cands, pen=pen,
                          size_distribution=learn3.server_size.distribution(st.size_history, mode=learn3.SIZE_MODE))
        if res["reeval_cond"]:
            if (st.n_reeval + 1) % learn3.REEVAL_EVERY == 0:
                take(res, res["alt"])
                res["why"] = "reeval"
                res["reeval"] = True
        s = learn3.post_summary(post)
        res["p_mean"] = s["p_mean"]
        res["p_map"] = s["p_map"]
        res["p_ge_010"] = s["p_ge_010"]
    cleared = learn3.guard_refresh(st)
    st.n_dec += 1
    if res["reeval_cond"]:
        st.n_reeval += 1
    if res["reeval"]:
        st.stats["reeval"] += 1
    res["guard_alarm"] = learn3.arm_key(res["action"]) in st.g_alarm
    res["guard_common_ms"] = b
    res["guard_alarmed_actions"] = len(st.g_alarm)
    res["guard_cleared"] = cleared
    res["dec_index"] = st.n_dec
    res["n_reeval"] = st.n_reeval
    res["policy_version"] = learn3.POLICY_VERSION
    return res
