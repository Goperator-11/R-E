import math

from padfec import quantum, table
from padfec3 import layout

G = tuple(float(x) for x in table.P_VALS)
H = (1.0 / 30, 1.0 / 100, 1.0 / 300, 1.0 / 1000, 1.0 / 3000)
EPS = 0.01
W_FLOOR = 1e-6
K_WIN = 16
S_WIN = 16
HCT_WIN = 32
BASE_MIN = 8
EVENT_RTT_FRAC = 0.5
SHIELD_RTT_MS = 200.0
SHIELD_E0 = 0.5
P_SERVER = 1280
B0 = (0, 0, 0)
LATER_DEFAULT = "v3"
STATE_VERSION = 1

_MODEL = {}


def clear_model_cache():
    _MODEL.clear()


def model_cache_size():
    return len(_MODEL)


def _int(name, v):
    if isinstance(v, bool) or not isinstance(v, int):
        raise TypeError("%s must be int: %r" % (name, v))
    return v


def check_action(action):
    if len(action) != 3:
        raise ValueError("action must be (delta, lead, T): %r" % (action,))
    d, lead, t = (_int("delta", action[0]), _int("lead", action[1]),
                  _int("T", action[2]))
    if d < 0 or lead < 0 or t < 0 or lead + t > layout.M_MAX:
        raise ValueError("bad action: %r" % (action,))
    return d, lead, t


def arm_key(action):
    d, lead, t = check_action(action)
    return "%d,%d,%d" % (d, lead, t)


def parse_arm_key(key):
    parts = key.split(",")
    return check_action(tuple(int(x) for x in parts))


def bin_needed_s(S, base_bin, c_pkt):
    if c_pkt is None:
        raise TypeError("c_pkt must be given")
    s0abs = float(S) - float(base_bin) * float(c_pkt)
    den = float(P_SERVER) - float(c_pkt)
    if den <= 0:
        return 1
    n = int(s0abs / den)
    while float(n * P_SERVER) < s0abs + float(n) * float(c_pkt):
        n += 1
    if n < 1:
        n = 1
    return n


def model_point(k, w_eff, u, rtt, n_need, lead, m, g, later=LATER_DEFAULT):
    key = (k, w_eff, float(u), float(rtt), n_need, lead, m, g, later)
    r = _MODEL.get(key)
    if r is None:
        ev = layout.evaluate(k, w_eff, m, lead, G[g], float(rtt), float(u),
                             n_need, later)
        r = (ev["J"], ev["e"], ev["p_two_rtt"], ev["p_fail"])
        _MODEL[key] = r
    return r


def j3_at(ctx, action, g, later=LATER_DEFAULT):
    d, lead, t = check_action(action)
    return model_point(ctx["k"], ctx["W"] + d, ctx["u"], ctx["rtt"],
                       ctx["n_need"], lead, lead + t, g, later)[0]


def nominal_two_rtt(ctx, action, later=LATER_DEFAULT):
    d, lead, t = check_action(action)
    e0 = model_point(ctx["k"], ctx["W"] + d, ctx["u"], ctx["rtt"],
                     ctx["n_need"], lead, lead + t, 0, later)[1]
    return e0 >= SHIELD_E0


def event_prob(ctx, action, g, later=LATER_DEFAULT):
    d, lead, t = check_action(action)
    _, e, _, pf = model_point(ctx["k"], ctx["W"] + d, ctx["u"], ctx["rtt"],
                              ctx["n_need"], lead, lead + t, g, later)
    if nominal_two_rtt(ctx, action, later):
        return pf
    return e


def shielded(ctx, action, later=LATER_DEFAULT):
    return ctx["rtt"] >= SHIELD_RTT_MS and nominal_two_rtt(ctx, action, later)


def median(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        raise ValueError("median of empty list")
    h = n // 2
    if n % 2 == 1:
        return float(s[h])
    return (float(s[h - 1]) + float(s[h])) / 2.0


def mode_recent(xs):
    if not xs:
        return None
    counts = {}
    for v in xs:
        counts[v] = counts.get(v, 0) + 1
    best = None
    for v in reversed(xs):
        if best is None or counts[v] > counts[best]:
            best = v
    return best


class DestState3:
    def __init__(self):
        n = len(G)
        self.k_hist = []
        self.S_hist = []
        self.hct = {}
        self.hct_seq = {}
        self.seq = 0
        self.post = [[1.0 / n] * n for _ in H]
        self.w = [1.0 / len(H)] * len(H)
        self.stats = {"obs": 0, "upd": 0, "shield": 0, "no_base": 0,
                      "no_ctx": 0, "events": 0, "fail": 0}

    def to_json(self):
        return {"v": STATE_VERSION, "k_hist": list(self.k_hist),
                "S_hist": list(self.S_hist),
                "hct": {k: list(v) for k, v in sorted(self.hct.items())},
                "hct_seq": dict(sorted(self.hct_seq.items())),
                "seq": self.seq,
                "post": [list(p) for p in self.post], "w": list(self.w),
                "stats": dict(self.stats)}

    @classmethod
    def from_json(cls, d):
        if d.get("v") != STATE_VERSION:
            raise ValueError("state version mismatch: %r" % (d.get("v"),))
        st = cls()
        st.k_hist = [int(x) for x in d["k_hist"]]
        st.S_hist = [float(x) for x in d["S_hist"]]
        st.hct = {k: [float(x) for x in v] for k, v in d["hct"].items()}
        st.hct_seq = {k: int(v) for k, v in d["hct_seq"].items()}
        st.seq = int(d["seq"])
        st.post = [[float(x) for x in p] for p in d["post"]]
        st.w = [float(x) for x in d["w"]]
        st.stats.update(d.get("stats", {}))
        if len(st.post) != len(H) or any(len(p) != len(G) for p in st.post):
            raise ValueError("posterior shape mismatch")
        if len(st.w) != len(H):
            raise ValueError("weight shape mismatch")
        return st


def new_state():
    return DestState3()


def k_hat(st):
    return mode_recent(st.k_hist)


def s_hat(st):
    if not st.S_hist:
        return None
    return median(st.S_hist)


def combined(st):
    n = len(G)
    out = [0.0] * n
    for wh, ph in zip(st.w, st.post):
        for i in range(n):
            out[i] += wh * ph[i]
    return out


def post_mean(post):
    s = 0.0
    for q, p in zip(post, G):
        s += q * p
    return s


def post_summary(post):
    s = 0.0
    for q in post:
        s += q
    mode_i = max(range(len(post)), key=lambda i: (post[i], -i))
    hi = 0.0
    for q, p in zip(post, G):
        if p >= 0.10:
            hi += q
    return {"p_mean": post_mean(post), "p_map": G[mode_i], "mass": s,
            "p_ge_010": hi}


def context(st, W, u_mbps, rtt_ms, c_pkt):
    k = k_hat(st)
    S = s_hat(st)
    if k is None or S is None:
        return None
    if k < 1 or k > layout.K_MAX:
        return None
    if rtt_ms is None or not rtt_ms > 0:
        return None
    n_need = bin_needed_s(S, quantum.bin_index(k * W), c_pkt)
    return {"k": k, "S": S, "n_need": n_need, "W": W, "u": float(u_mbps),
            "rtt": float(rtt_ms)}


def filter_step(post, w, L):
    n = len(G)
    new_post = []
    raw = []
    zs = []
    for wh, ph, h in zip(w, post, H):
        prior = [(1.0 - h) * ph[i] + h * (1.0 / n) for i in range(n)]
        z = 0.0
        for i in range(n):
            z += prior[i] * L[i]
        new_post.append([prior[i] * L[i] / z for i in range(n)])
        raw.append(wh * z)
        zs.append(z)
    s = 0.0
    for x in raw:
        s += x
    nw = [x / s for x in raw]
    nw = [x if x >= W_FLOOR else W_FLOOR for x in nw]
    s2 = 0.0
    for x in nw:
        s2 += x
    nw = [x / s2 for x in nw]
    return new_post, nw, zs


def likelihood(ctx, action, y, later=LATER_DEFAULT):
    out = []
    for g in range(len(G)):
        e = event_prob(ctx, action, g, later)
        l1 = (1.0 - EPS) * e + EPS * (1.0 - e)
        out.append(l1 if y else 1.0 - l1)
    return out


def baseline(st, ctx, action, later=LATER_DEFAULT):
    key = arm_key(action)
    own = st.hct.get(key, [])
    if len(own) >= BASE_MIN:
        return median(own), key
    if ctx is None:
        return None, None
    best = None
    for k2, v in st.hct.items():
        if len(v) < BASE_MIN:
            continue
        cand = (len(v), st.hct_seq.get(k2, -1))
        if best is None or cand > best[0]:
            best = (cand, k2)
    if best is None:
        return None, None
    ref = best[1]
    ref_action = parse_arm_key(ref)
    b = (median(st.hct[ref]) + j3_at(ctx, action, 0, later)
         - j3_at(ctx, ref_action, 0, later))
    return b, ref


def _push(lst, v, cap):
    lst.append(v)
    if len(lst) > cap:
        del lst[0:len(lst) - cap]


def observe3(st, action, hct_ms, ok, k_obs, srv_bytes, rtt_ms, *, W, u_mbps,
             c_pkt, later=LATER_DEFAULT):
    key = arm_key(action)
    ok = bool(ok)
    if ok and (hct_ms is None or not math.isfinite(hct_ms) or hct_ms <= 0):
        raise ValueError("ok observation needs hct_ms > 0: %r" % (hct_ms,))
    st.stats["obs"] += 1
    if not ok:
        st.stats["fail"] += 1
    ctx = context(st, W, u_mbps, rtt_ms, c_pkt)
    b, ref = baseline(st, ctx, action, later)
    y = None
    if b is not None and rtt_ms is not None and rtt_ms > 0:
        if (not ok) or (hct_ms - b >= EVENT_RTT_FRAC * float(rtt_ms)):
            y = 1
        else:
            y = 0
    info = {"y": y, "baseline": b, "ref": ref, "updated": False,
            "shielded": False, "ctx": ctx}
    if y is None:
        st.stats["no_base"] += 1
    elif ctx is None:
        st.stats["no_ctx"] += 1
    elif shielded(ctx, action, later):
        st.stats["shield"] += 1
        info["shielded"] = True
    else:
        L = likelihood(ctx, action, y, later)
        st.post, st.w, _ = filter_step(st.post, st.w, L)
        st.stats["upd"] += 1
        if y:
            st.stats["events"] += 1
        info["updated"] = True
    if ok:
        if isinstance(k_obs, int) and not isinstance(k_obs, bool) and k_obs >= 1:
            _push(st.k_hist, k_obs, K_WIN)
        _push(st.hct.setdefault(key, []), float(hct_ms), HCT_WIN)
        st.hct_seq[key] = st.seq
        st.seq += 1
        if y != 1 and srv_bytes is not None and srv_bytes > 0:
            _push(st.S_hist, float(srv_bytes), S_WIN)
    return info
