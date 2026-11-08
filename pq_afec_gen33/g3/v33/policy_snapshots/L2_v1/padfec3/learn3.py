import math
from collections import OrderedDict
from copy import deepcopy

from padfec import policy, quantum, table
from padfec3 import layout

G = tuple(float(x) for x in table.P_VALS)
H = (1.0 / 30, 1.0 / 100, 1.0 / 300, 1.0 / 1000, 1.0 / 3000)
EPS = 0.01
CLASS_EPS = 1e-3
CLASS_EPS_A = 1.0
CLASS_EPS_B = 999.0
CLASS_EPS_SCHEMA = "padfec.class_epsilon_moment_projection/1"
CLASS_C_PROC_MS = 3.0
CLASS_NAMES = ("one_rtt", "two_rtt", "late_or_failure")
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
STATE_VERSION = 5
POLICY_VERSION = "v3.3-dev"
MIN_W = 1200
PROB_MASS_TOL = 1e-9
MAX_EXACT_INT = (1 << 53) - 1
N_NEED_MAX = MAX_EXACT_INT // P_SERVER
REEVAL_EVERY = 16
GUARD_COMMON_WIN = 64
GUARD_ACTION_WIN = 32
GUARD_MIN = 8
GUARD_RTT_FRAC = 0.5
GUARD_REFRESH = 64
SKIP_SHIELD = "shield"
SKIP_NOMINAL2 = "nominal2"
SKIP_GUARD = "guard"

MODEL_CACHE_MAX = 100000
_MODEL = OrderedDict()


def clear_model_cache():
    _MODEL.clear()


def model_cache_size():
    return len(_MODEL)


def _int(name, v):
    if isinstance(v, bool) or not isinstance(v, int):
        raise TypeError("%s must be int: %r" % (name, v))
    return v


def _nonnegative_int(name, value):
    value = _int(name, value)
    if value < 0:
        raise ValueError("%s must be >= 0: %r" % (name, value))
    return value


def _finite(name, value, *, minimum=None, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("%s must be a number: %r" % (name, value))
    try:
        result = float(value)
    except OverflowError:
        raise ValueError("%s must be finite: %r" % (name, value)) from None
    if not math.isfinite(result):
        raise ValueError("%s must be finite: %r" % (name, value))
    if positive and result <= 0:
        raise ValueError("%s must be > 0: %r" % (name, value))
    if minimum is not None and result < minimum:
        raise ValueError("%s must be >= %r: %r" % (name, minimum, value))
    return result


def check_c_pkt(c_pkt):
    value = _finite("c_pkt", c_pkt, minimum=0.0)
    if value >= P_SERVER:
        raise ValueError("c_pkt must be < %d: %r" % (P_SERVER, c_pkt))
    return value


def check_later(later):
    if later not in layout.LATER_MODES:
        raise ValueError("later must be one of %r: %r" % (layout.LATER_MODES, later))


def check_transport(W, u_mbps, rtt_ms, c_pkt, *, missing_rtt=False):
    W = _int("W", W)
    if W < MIN_W:
        raise ValueError("W must be >= %d: %r" % (MIN_W, W))
    _finite("u_mbps", u_mbps, minimum=0.0)
    check_c_pkt(c_pkt)
    if rtt_ms is not None or not missing_rtt:
        _finite("rtt_ms", rtt_ms, minimum=0.0,
                positive=not missing_rtt)
    check_model_arithmetic(W, u_mbps, rtt_ms)


def check_model_arithmetic(w_eff, u_mbps, rtt_ms):
    flight = ((layout.K_MAX + layout.M_MAX) * w_eff
              + layout.M_MAX * layout.parity_bytes(0, layout.K_MAX)
              + policy.MAX_STEPS_DEFAULT * P_SERVER)
    if quantum.AMP * flight > MAX_EXACT_INT:
        raise ValueError("flight credit exceeds exact float integer range")
    serial = 0.0
    if u_mbps > 0:
        den = _finite("uplink serialization denominator", u_mbps * 1e3,
                      positive=True)
        serial = _finite("uplink serialization time", flight * 8.0 / den)
    rtt = 0.0 if rtt_ms is None else float(rtt_ms)
    delay = (3.0 * serial + (2.0 + layout.PTO_SAMPLED_MULT) * rtt
             + layout.T_PTO_MS + layout.T_ACK_BASE_MS
             + layout.G2_PARITY_DELAY_MS)
    _finite("model cost upper bound", delay / (1.0 - G[-1]) ** layout.K_MAX)


def _sequence(name, value, *, cap=None, length=None):
    if not isinstance(value, (list, tuple)):
        raise TypeError("%s must be a sequence" % name)
    if cap is not None and len(value) > cap:
        raise ValueError("%s exceeds window cap %d" % (name, cap))
    if length is not None and len(value) != length:
        raise ValueError("%s length must be %d" % (name, length))
    return value


def check_probabilities(name, value, length):
    values = _sequence(name, value, length=length)
    result = [_finite("%s[%d]" % (name, i), x, minimum=0.0)
              for i, x in enumerate(values)]
    if abs(sum(result) - 1.0) > PROB_MASS_TOL:
        raise ValueError("%s probability mass must be 1" % name)
    return result


def _float_window(name, value, cap, *, positive=False):
    values = _sequence(name, value, cap=cap)
    return [_finite("%s[%d]" % (name, i), x, positive=positive)
            for i, x in enumerate(values)]


def _mapping(name, value, *, arms=False):
    if not isinstance(value, dict):
        raise TypeError("%s must be a mapping" % name)
    if arms:
        for key in value:
            if not isinstance(key, str):
                raise TypeError("%s action keys must be strings" % name)
            parse_arm_key(key)
    return value


def check_action(action):
    if len(action) != 3:
        raise ValueError("action must be (delta, lead, T): %r" % (action,))
    d, lead, t = (_int("delta", action[0]), _int("lead", action[1]),
                  _int("T", action[2]))
    if d < 0 or lead < 0 or t < 0 or lead + t > layout.M_MAX:
        raise ValueError("bad action: %r" % (action,))
    if d > MAX_EXACT_INT:
        raise ValueError("delta exceeds exact float integer range")
    return d, lead, t


def arm_key(action):
    d, lead, t = check_action(action)
    return "%d,%d,%d" % (d, lead, t)


def parse_arm_key(key):
    parts = key.split(",")
    return check_action(tuple(int(x) for x in parts))


def bin_needed_s(S, base_bin, c_pkt):
    S = _finite("S", S, positive=True)
    c_pkt = check_c_pkt(c_pkt)
    base_bin = _nonnegative_int("base_bin", base_bin)
    if base_bin > N_NEED_MAX:
        raise ValueError("base_bin exceeds exact packet-byte range")
    s0abs = S - float(base_bin) * c_pkt
    den = float(P_SERVER) - c_pkt
    q = _finite("packet-count quotient", s0abs / den)
    if abs(q) > N_NEED_MAX:
        raise ValueError("packet count exceeds exact packet-byte range")
    n = int(q)
    if float(n * P_SERVER) < s0abs + float(n) * c_pkt:
        n += 1
    if abs(n) > N_NEED_MAX:
        raise ValueError("packet count exceeds exact packet-byte range")
    if float(n * P_SERVER) < s0abs + float(n) * c_pkt:
        raise ValueError("packet count cannot be resolved by float arithmetic")
    if n < 1:
        n = 1
    return n


def _model_result(k, w_eff, u, rtt, n_need, lead, m, g, later):
    check_later(later)
    key = (k, w_eff, float(u), float(rtt), n_need, lead, m, g, later)
    r = _MODEL.get(key)
    if r is None:
        ev = layout.evaluate(k, w_eff, m, lead, G[g], float(rtt), float(u),
                             n_need, later)
        _finite("model cost", ev["J"])
        r = ((ev["J"], ev["e"], ev["p_two_rtt"], ev["p_fail"]),
             (ev["p_one_rtt"], ev["p_two_rtt"], ev["p_fail"]))
        while len(_MODEL) >= MODEL_CACHE_MAX:
            _MODEL.popitem(last=False)
        _MODEL[key] = r
    return r


def model_point(k, w_eff, u, rtt, n_need, lead, m, g, later=LATER_DEFAULT):
    return _model_result(k, w_eff, u, rtt, n_need, lead, m, g, later)[0]


def normalize_arrivals(arrivals):
    if arrivals is None:
        return {"src": "none", "sent": 0, "lost": 0, "bitmap": None, "trunc": False}
    fields = {"src", "sent", "lost", "bitmap", "trunc"}
    if not isinstance(arrivals, dict) or set(arrivals) != fields:
        raise ValueError("arrivals requires exactly src,sent,lost,bitmap,trunc")
    src, sent, lost = arrivals["src"], arrivals["sent"], arrivals["lost"]
    bitmap, trunc = arrivals["bitmap"], arrivals["trunc"]
    if src not in ("c1", "ack", "none") or type(trunc) is not bool:
        raise ValueError("invalid arrivals source or truncation marker")
    if type(sent) is not int or type(lost) is not int:
        raise ValueError("arrivals counts must be integers, not bool")
    if not 0 <= lost <= sent <= layout.K_MAX + layout.M_MAX:
        raise ValueError("arrivals require 0 <= lost <= sent <= 8")
    if bitmap is not None:
        if not isinstance(bitmap, list) or any(type(bit) is not int or bit not in (0, 1) for bit in bitmap):
            raise ValueError("arrivals bitmap must contain integer 0/1 values")
        if len(bitmap) > sent or (not trunc and (len(bitmap) != sent or bitmap.count(0) != lost)):
            raise ValueError("arrivals bitmap disagrees with counts")
        bitmap = list(bitmap)
    return {"src": src, "sent": sent, "lost": lost, "bitmap": bitmap, "trunc": trunc}


def arrival_likelihood(sent, lost):
    counts = normalize_arrivals({"src": "c1", "sent": sent, "lost": lost,
                                 "bitmap": None, "trunc": False})
    if counts["sent"] == 0:
        raise ValueError("arrival likelihood needs at least one datagram")
    result = []
    for p in G:
        value = 1.0
        for _ in range(lost):
            value *= p
        for _ in range(sent - lost):
            value *= 1.0 - p
        result.append(value)
    return result


def grade_cutoffs(ctx, action, later=LATER_DEFAULT, *, c_proc_ms=CLASS_C_PROC_MS):
    check_later(later)
    c_proc_ms = _finite("categorical processing margin", c_proc_ms, minimum=0.0)
    d, lead, trailing = check_action(action)
    m, w = lead + trailing, ctx["W"] + d
    first = _finite("one RTT cutoff", layout.one_rtt_cutoff_ms(
        ctx["rtt"], ctx["k"], m, lead, w, ctx["u"]) + c_proc_ms, positive=True)
    second = _finite("two RTT cutoff", first + ctx["rtt"]
                     + layout.response_term(m, w, ctx["u"], later), positive=True)
    return first, second


def classify_hct(ctx, action, hct_ms, ok, later=LATER_DEFAULT):
    if not ok:
        return 2
    if ctx is None:
        return None
    hct_ms = _finite("HCT grade observation", hct_ms, positive=True)
    first, second = grade_cutoffs(ctx, action, later)
    return 0 if hct_ms < first else 1 if hct_ms < second else 2


def class_probabilities(ctx, action, g, later=LATER_DEFAULT):
    d, lead, trailing = check_action(action)
    values = _model_result(ctx["k"], ctx["W"] + d, ctx["u"], ctx["rtt"],
                           ctx["n_need"], lead, lead + trailing, g, later)[1]
    return check_probabilities("categorical model probabilities", values, 3)


def class_likelihood(ctx, action, grade, later=LATER_DEFAULT, *, epsilon=CLASS_EPS):
    if type(grade) is not int or grade not in (0, 1, 2):
        raise ValueError("grade must be integer 0, 1, or 2")
    epsilon = _finite("categorical epsilon", epsilon, minimum=0.0)
    if epsilon > 1.0:
        raise ValueError("categorical epsilon must be <= 1")
    out = []
    for g in range(len(G)):
        q = class_probabilities(ctx, action, g, later)[grade]
        out.append((1.0 - epsilon) * q + epsilon * (1.0 - q) / 2.0)
    return out


def beta_parameters(a, b):
    a = _finite("epsilon a", a, positive=True)
    b = _finite("epsilon b", b, positive=True)
    total = _finite("epsilon strength", a + b, positive=True)
    _finite("epsilon mean", a / total, positive=True)
    _finite("epsilon complementary mean", b / total, positive=True)
    return a, b, total


def epsilon_posterior(a, b, q):
    a, b, total = beta_parameters(a, b)
    q = _finite("epsilon predictive probability", q, minimum=0.0)
    if q > 1.0:
        raise ValueError("epsilon predictive probability must be <= 1")
    if q == 1.0 / 3.0:
        return a, b, a / total, "uninformative"
    if q == 0.0:
        new_a, new_b, _ = beta_parameters(a + 1.0, b)
        return new_a, new_b, 1.0, "conjugate_error"
    if q == 1.0:
        new_a, new_b, _ = beta_parameters(a, b + 1.0)
        return new_a, new_b, 0.0, "conjugate_match"
    wrong = (a / total) * (1.0 - q) / 2.0
    correct = (b / total) * q
    normalizer = _finite("epsilon likelihood", wrong + correct, positive=True)
    rho, other = wrong / normalizer, correct / normalizer
    t = _finite("epsilon updated strength scale", total + 1.0, positive=True)
    mean = (a + rho) / t
    complement = (b + other) / t
    var0 = (a / t) * ((b + 1.0) / t) / (t + 1.0)
    var1 = ((a + 1.0) / t) * (b / t) / (t + 1.0)
    variance = _finite("epsilon mixture variance", other * var0 + rho * var1
                       + rho * other / t / t, positive=True)
    strength = _finite("epsilon projected strength", mean * complement / variance - 1.0,
                       positive=True)
    new_a, new_b, _ = beta_parameters(mean * strength, complement * strength)
    return new_a, new_b, rho, "moment_projection"


def check_epsilon_state(value):
    fields = {"schema", "a", "b", "updates", "skips"}
    if not isinstance(value, dict) or set(value) != fields or value["schema"] != CLASS_EPS_SCHEMA:
        raise ValueError("invalid epsilon state schema")
    a, b, _ = beta_parameters(value["a"], value["b"])
    skips = _mapping("epsilon skips", value["skips"])
    reasons = {"missing_snapshot", "stale_snapshot", "action_mismatch", "transport_mismatch",
               "epsilon_mismatch", "no_ctx"}
    if not set(skips).issubset(reasons):
        raise ValueError("unknown epsilon skip reason")
    return {"schema": CLASS_EPS_SCHEMA, "a": a, "b": b,
            "updates": _nonnegative_int("epsilon updates", value["updates"]),
            "skips": {key: _nonnegative_int("epsilon skip " + key, count)
                      for key, count in sorted(skips.items())}}


def check_class_snapshot(value):
    if value is None:
        return None
    fields = {"v", "dec_index", "obs_index", "action", "W", "u", "c_pkt", "later",
              "ctx", "c_proc_ms", "cutoffs", "q", "a", "b"}
    if not isinstance(value, dict) or set(value) != fields or type(value["v"]) is not int or value["v"] != 1:
        raise ValueError("invalid class snapshot schema")
    result = deepcopy(value)
    result["dec_index"] = _nonnegative_int("snapshot decision", value["dec_index"])
    result["obs_index"] = _nonnegative_int("snapshot observation", value["obs_index"])
    result["action"] = list(check_action(_sequence("snapshot action", value["action"], length=3)))
    check_transport(value["W"], value["u"], None, value["c_pkt"], missing_rtt=True)
    check_later(value["later"])
    result["a"], result["b"], _ = beta_parameters(value["a"], value["b"])
    margin = _finite("snapshot processing margin", value["c_proc_ms"], minimum=0.0)
    if margin != CLASS_C_PROC_MS:
        raise ValueError("snapshot processing margin mismatch")
    ctx = value["ctx"]
    if ctx is None:
        if value["q"] is not None or value["cutoffs"] is not None:
            raise ValueError("context-free snapshot must not contain probabilities or cutoffs")
    else:
        if not isinstance(ctx, dict) or set(ctx) != {"k", "S", "n_need", "W", "u", "rtt"}:
            raise ValueError("invalid snapshot context")
        k = _int("snapshot k", ctx["k"])
        if not 1 <= k <= layout.K_MAX:
            raise ValueError("snapshot k out of range")
        check_transport(ctx["W"], ctx["u"], ctx["rtt"], value["c_pkt"])
        if ctx["W"] != value["W"] or ctx["u"] != value["u"]:
            raise ValueError("snapshot transport inconsistent with context")
        needed = bin_needed_s(ctx["S"], quantum.bin_index(k * ctx["W"]), value["c_pkt"])
        if _int("snapshot n_need", ctx["n_need"]) != needed:
            raise ValueError("snapshot packet count mismatch")
        cutoffs = _sequence("snapshot cutoffs", value["cutoffs"], length=2)
        for item in cutoffs:
            _finite("snapshot cutoff", item, positive=True)
        if tuple(cutoffs) != grade_cutoffs(ctx, result["action"], value["later"], c_proc_ms=margin):
            raise ValueError("snapshot cutoffs mismatch")
        result["cutoffs"] = list(cutoffs)
        result["q"] = check_probabilities("snapshot predictive classes", value["q"], 3)
        if any(probability > 1.0 for probability in result["q"]):
            raise ValueError("snapshot predictive probability must be <= 1")
    return result


def class_snapshot(st, action, W, u_mbps, rtt_ms, c_pkt, later):
    eps = check_epsilon_state(st.class_epsilon)
    ctx = context(st, W, u_mbps, rtt_ms, c_pkt)
    q, cutoffs = None, None
    if ctx is not None:
        prior, weights = predict_step(st.post, st.w)
        post = [0.0] * len(G)
        for weight, row in zip(weights, prior):
            for g in range(len(G)):
                post[g] += weight * row[g]
        q = [0.0, 0.0, 0.0]
        for g in range(len(G)):
            values = class_probabilities(ctx, action, g, later)
            for grade in range(3):
                q[grade] += post[g] * values[grade]
        normalizer = _finite("predictive class mass", sum(q), positive=True)
        q = [value / normalizer for value in q]
        cutoffs = list(grade_cutoffs(ctx, action, later))
    return check_class_snapshot({"v": 1, "dec_index": st.n_dec + 1, "obs_index": st.stats["obs"],
                                 "action": list(action), "W": W, "u": float(u_mbps),
                                 "c_pkt": float(c_pkt), "later": later, "ctx": ctx,
                                 "c_proc_ms": CLASS_C_PROC_MS, "cutoffs": cutoffs, "q": q,
                                 "a": eps["a"], "b": eps["b"]})


def consume_class_snapshot(st, action, W, u_mbps, c_pkt, later):
    snapshot = check_class_snapshot(st.class_pending)
    st.class_pending = None
    reason = "missing_snapshot"
    if snapshot is not None:
        if snapshot["dec_index"] != st.n_dec or snapshot["obs_index"] != st.stats["obs"]:
            reason = "stale_snapshot"
        elif tuple(snapshot["action"]) != tuple(action):
            reason = "action_mismatch"
        elif (snapshot["W"], snapshot["u"], snapshot["c_pkt"], snapshot["later"]) != (W, u_mbps, c_pkt, later):
            reason = "transport_mismatch"
        elif (snapshot["a"], snapshot["b"]) != (st.class_epsilon["a"], st.class_epsilon["b"]):
            reason = "epsilon_mismatch"
        else:
            return snapshot, None if snapshot["ctx"] is not None else "no_ctx"
    return None, reason


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


def skip_reason(ctx, action, later=LATER_DEFAULT):
    if not nominal_two_rtt(ctx, action, later):
        return None
    if ctx["rtt"] >= SHIELD_RTT_MS:
        return SKIP_SHIELD
    return SKIP_NOMINAL2


def median(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        raise ValueError("median of empty list")
    h = n // 2
    if n % 2 == 1:
        return float(s[h])
    a, b = float(s[h - 1]), float(s[h])
    total = a + b
    return total / 2.0 if math.isfinite(total) else a / 2.0 + b / 2.0


def mean_seq(xs):
    n = len(xs)
    if n == 0:
        raise ValueError("mean of empty list")
    s = 0.0
    for x in xs:
        s += x
    return s / n


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
        self.n_dec = 0
        self.n_reeval = 0
        self.class_epsilon = {"schema": CLASS_EPS_SCHEMA, "a": CLASS_EPS_A, "b": CLASS_EPS_B,
                              "updates": 0, "skips": {}}
        self.class_pending = None
        self.g_resid = {}
        self.g_common = []
        self.g_alarm = {}
        self.stats = {"obs": 0, "upd": 0, "predict": 0, "shield": 0, "nominal2": 0,
                      "guard": 0, "no_base": 0, "no_ctx": 0, "events": 0,
                      "fail": 0, "resid": 0, "reeval": 0, "alarm_raised": 0,
                      "alarm_cleared": 0, "datagram": 0, "categorical": 0,
                      "predict_only": 0, "arr_c1": 0, "arr_ack": 0,
                      "arr_none": 0, "arr_trunc": 0, "arr_empty": 0,
                      "arr_sent": 0, "arr_lost": 0,
                      "grade_one_rtt": 0, "grade_two_rtt": 0,
                      "grade_late_or_failure": 0}

    def to_json(self):
        return {"v": STATE_VERSION, "k_hist": list(self.k_hist),
                "S_hist": list(self.S_hist),
                "hct": {k: list(v) for k, v in sorted(self.hct.items())},
                "hct_seq": dict(sorted(self.hct_seq.items())),
                "seq": self.seq,
                "post": [list(p) for p in self.post], "w": list(self.w),
                "n_dec": self.n_dec, "n_reeval": self.n_reeval,
                "class_epsilon": deepcopy(self.class_epsilon),
                "class_pending": deepcopy(self.class_pending),
                "g_resid": {k: list(v) for k, v in sorted(self.g_resid.items())},
                "g_common": list(self.g_common),
                "g_alarm": dict(sorted(self.g_alarm.items())),
                "stats": dict(self.stats)}

    @classmethod
    def from_json(cls, d):
        _mapping("state", d)
        if d.get("v") != STATE_VERSION:
            raise ValueError("state version mismatch: %r" % (d.get("v"),))
        _int("state version", d["v"])
        st = cls()
        st.k_hist = [_int("k_hist[%d]" % i, x)
                     for i, x in enumerate(_sequence("k_hist", d["k_hist"],
                                                     cap=K_WIN))]
        if any(x < 1 for x in st.k_hist):
            raise ValueError("k_hist values must be >= 1")
        st.S_hist = _float_window("S_hist", d["S_hist"], S_WIN, positive=True)
        st.hct = {k: _float_window("hct[%s]" % k, v, HCT_WIN, positive=True)
                  for k, v in _mapping("hct", d["hct"], arms=True).items()}
        st.hct_seq = {k: _nonnegative_int("hct_seq[%s]" % k, v)
                      for k, v in _mapping("hct_seq", d["hct_seq"],
                                           arms=True).items()}
        st.seq = _nonnegative_int("seq", d["seq"])
        st.post = [check_probabilities("post[%d]" % i, p, len(G))
                   for i, p in enumerate(_sequence("post", d["post"],
                                                   length=len(H)))]
        st.w = check_probabilities("w", d["w"], len(H))
        st.n_dec = _nonnegative_int("n_dec", d["n_dec"])
        st.n_reeval = _nonnegative_int("n_reeval", d["n_reeval"])
        st.class_epsilon = check_epsilon_state(d["class_epsilon"])
        st.class_pending = check_class_snapshot(d["class_pending"])
        st.g_resid = {k: _float_window("g_resid[%s]" % k, v, GUARD_ACTION_WIN)
                      for k, v in _mapping("g_resid", d["g_resid"],
                                           arms=True).items()}
        st.g_common = _float_window("g_common", d["g_common"], GUARD_COMMON_WIN)
        st.g_alarm = {k: _nonnegative_int("g_alarm[%s]" % k, v)
                      for k, v in _mapping("g_alarm", d["g_alarm"],
                                           arms=True).items()}
        if any(at > st.n_dec for at in st.g_alarm.values()):
            raise ValueError("alarm time must be <= n_dec")
        st.stats.update({k: _nonnegative_int("stats[%s]" % k, v)
                         for k, v in _mapping("stats", d.get("stats", {})).items()})
        b = guard_common(st)
        for key in st.g_resid:
            guard_excess(st, key, b)
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


def predict_step(post, w):
    n = len(G)
    return [[(1.0 - h) * ph[i] + h * (1.0 / n) for i in range(n)]
            for ph, h in zip(post, H)], list(w)


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


def guard_common(st):
    if not st.g_common:
        return 0.0
    return median(st.g_common)


def guard_excess(st, key, b):
    win = st.g_resid.get(key)
    if not win:
        return None
    return _finite("guard gap for %s" % key, median(win) - b)


def guard_penalty(st, key, b):
    if key not in st.g_alarm:
        return 0.0
    x = guard_excess(st, key, b)
    if x is None or not x > 0:
        return 0.0
    return x


def guard_penalties(st, b):
    return {key: guard_penalty(st, key, b) for key in sorted(st.g_alarm)}


def guard_refresh(st):
    cleared = []
    for key in sorted(st.g_alarm):
        if st.n_dec - st.g_alarm[key] >= GUARD_REFRESH:
            del st.g_alarm[key]
            st.g_resid.pop(key, None)
            cleared.append(key)
    st.stats["alarm_cleared"] += len(cleared)
    return cleared


def guard_check(st, rtt_ms):
    if rtt_ms is None or not rtt_ms > 0:
        return []
    b = guard_common(st)
    gaps = {key: guard_excess(st, key, b) for key in sorted(st.g_resid)}
    lim = GUARD_RTT_FRAC * float(rtt_ms)
    raised = []
    for key in sorted(st.g_resid):
        if key in st.g_alarm:
            continue
        win = st.g_resid[key]
        if len(win) >= GUARD_MIN and gaps[key] > lim:
            st.g_alarm[key] = st.n_dec
            raised.append(key)
    st.stats["alarm_raised"] += len(raised)
    return raised


def guard_observe(st, key, resid, rtt_ms):
    win = list(st.g_resid.get(key, []))
    common = list(st.g_common)
    _push(win, resid, GUARD_ACTION_WIN)
    _push(common, resid, GUARD_COMMON_WIN)
    b = median(common)
    preview = dict(st.g_resid)
    preview[key] = win
    for action_key, values in preview.items():
        if values:
            _finite("guard gap for %s" % action_key, median(values) - b)
    st.g_resid[key] = win
    st.g_common = common
    st.stats["resid"] += 1
    return guard_check(st, rtt_ms)


def observe3(st, action, hct_ms, ok, k_obs, srv_bytes, rtt_ms, *, W, u_mbps,
             c_pkt, later=LATER_DEFAULT, j_pred=None, arrivals=None):
    check_later(later)
    candidate = deepcopy(st)
    info = _observe3(candidate, action, hct_ms, ok, k_obs, srv_bytes, rtt_ms,
                     W=W, u_mbps=u_mbps, c_pkt=c_pkt, later=later,
                     j_pred=j_pred, arrivals=arrivals)
    st.__dict__.update(candidate.__dict__)
    return info


def _observe3(st, action, hct_ms, ok, k_obs, srv_bytes, rtt_ms, *, W, u_mbps,
              c_pkt, later, j_pred, arrivals):
    st.class_epsilon = check_epsilon_state(st.class_epsilon)
    evidence = normalize_arrivals(arrivals)
    check_transport(W, u_mbps, rtt_ms, c_pkt, missing_rtt=True)
    if srv_bytes is not None:
        _finite("srv_bytes", srv_bytes, minimum=0.0)
    key = arm_key(action)
    check_model_arithmetic(W + action[0], u_mbps, rtt_ms)
    ok = bool(ok)
    if ok and (hct_ms is None or not math.isfinite(hct_ms) or hct_ms <= 0):
        raise ValueError("ok observation needs hct_ms > 0: %r" % (hct_ms,))
    if j_pred is not None and not math.isfinite(j_pred):
        raise ValueError("j_pred must be finite: %r" % (j_pred,))
    if srv_bytes is not None and srv_bytes > 0:
        for k in range(1, layout.K_MAX + 1):
            bin_needed_s(srv_bytes, quantum.bin_index(k * W), c_pkt)
    k = k_hat(st)
    if st.S_hist and k is not None and 1 <= k <= layout.K_MAX:
        bin_needed_s(s_hat(st), quantum.bin_index(k * W), c_pkt)
    observation_ctx = context(st, W, u_mbps, rtt_ms, c_pkt)
    snapshot, epsilon_reason = consume_class_snapshot(st, action, W, u_mbps, c_pkt, later)
    ctx = observation_ctx if snapshot is None else snapshot["ctx"]
    epsilon_a, epsilon_b, epsilon_strength = beta_parameters(st.class_epsilon["a"], st.class_epsilon["b"])
    epsilon_before = epsilon_a / epsilon_strength
    grade = classify_hct(ctx, action, hct_ms, ok, later)
    cut1, cut2 = (None, None) if ctx is None else grade_cutoffs(ctx, action, later)
    b, ref = baseline(st, observation_ctx, action, later)
    if b is not None:
        _finite("HCT baseline", b)
    y = None
    if b is not None and rtt_ms is not None and rtt_ms > 0:
        if (not ok) or (hct_ms - b >= EVENT_RTT_FRAC * float(rtt_ms)):
            y = 1
        else:
            y = 0
    resid = None
    raised = []
    if ok and j_pred is not None:
        resid = _finite("guard residual", float(hct_ms) - float(j_pred))
    st.stats["obs"] += 1
    if not ok:
        st.stats["fail"] += 1
    if resid is not None:
        raised = guard_observe(st, key, resid, rtt_ms)
    alarmed = key in st.g_alarm
    info = {"y": y, "baseline": b, "ref": ref, "updated": False,
            "shielded": False, "skip": None, "ctx": ctx, "resid": resid,
            "alarmed": alarmed, "raised": raised,
            "common": guard_common(st), "n_alarm": len(st.g_alarm),
            "loss_evidence_src": evidence["src"],
            "arrival_sent": evidence["sent"], "arrival_lost": evidence["lost"],
            "arrival_trunc": evidence["trunc"], "arrival_bitmap": evidence["bitmap"],
            "grade": grade, "grade_name": None if grade is None else CLASS_NAMES[grade],
            "grade_valid": ctx is not None, "grade_reason": "no_ctx" if ctx is None else "hct_or_failure",
            "cut1_ms": cut1, "cut2_ms": cut2,
            "cutoff_rtt_ms": rtt_ms if snapshot is None else None if ctx is None else ctx["rtt"],
            "cutoff_rtt_source": "observation_rtt_direct_call" if snapshot is None else "decision_rtt_current_policy",
            "c_proc_used_ms": CLASS_C_PROC_MS, "margin1_ms": 0.0, "margin2_ms": 0.0,
            "epsilon_before": epsilon_before, "epsilon_after": epsilon_before,
            "epsilon_a_before": epsilon_a, "epsilon_b_before": epsilon_b,
            "epsilon_update_eligible": epsilon_reason is None, "epsilon_update_reason": epsilon_reason,
            "epsilon_q_pre": None if snapshot is None else snapshot["q"],
            "epsilon_snapshot_dec_index": None if snapshot is None else snapshot["dec_index"],
            "epsilon_schema": CLASS_EPS_SCHEMA, "legacy_y": y}
    skip = None if observation_ctx is None else skip_reason(observation_ctx, action, later)
    if skip is None and alarmed:
        skip = SKIP_GUARD
    legacy_skip = "no_base" if y is None else "no_ctx" if observation_ctx is None else skip
    info["legacy_skip_reason"] = legacy_skip
    info["legacy_shielded"] = skip == SKIP_SHIELD
    if legacy_skip is not None:
        st.stats[legacy_skip] += 1
    if y == 1:
        st.stats["events"] += 1
    st.stats["arr_" + evidence["src"]] += 1
    st.stats["arr_trunc"] += int(evidence["trunc"])
    st.stats["arr_empty"] += int(evidence["sent"] == 0)
    if grade is not None:
        st.stats["grade_" + CLASS_NAMES[grade]] += 1
    reason = ("source_none" if evidence["src"] == "none" else "truncated" if evidence["trunc"]
              else "empty" if evidence["sent"] == 0 else None)
    info["arrival_usable"] = reason is None
    info["arrival_reject_reason"] = reason
    if reason is None:
        L = arrival_likelihood(evidence["sent"], evidence["lost"])
        kind = "datagram"
        st.stats["arr_sent"] += evidence["sent"]
        st.stats["arr_lost"] += evidence["lost"]
    elif ctx is not None:
        L = class_likelihood(ctx, action, grade, later, epsilon=epsilon_before)
        kind = "categorical"
    else:
        L = None
        kind = "predict_only"
        info["skip"] = "no_ctx"
    if L is not None:
        st.post, st.w, _ = filter_step(st.post, st.w, L)
        st.stats["upd"] += 1
        info["updated"] = True
    else:
        st.post, st.w = predict_step(st.post, st.w)
    info["loss_update_kind"] = kind
    st.stats[kind] += 1
    st.stats["predict"] += 1
    if epsilon_reason is None:
        a, b, rho, update_reason = epsilon_posterior(epsilon_a, epsilon_b, snapshot["q"][grade])
        st.class_epsilon.update(a=a, b=b, updates=st.class_epsilon["updates"] + 1)
        info["epsilon_rho"] = rho
        info["epsilon_update_reason"] = update_reason
        info["epsilon_after"] = a / (a + b)
    else:
        skips = st.class_epsilon["skips"]
        skips[epsilon_reason] = skips.get(epsilon_reason, 0) + 1
        info["epsilon_rho"] = None
    info["epsilon_a_after"] = st.class_epsilon["a"]
    info["epsilon_b_after"] = st.class_epsilon["b"]
    if ok:
        if isinstance(k_obs, int) and not isinstance(k_obs, bool) and k_obs >= 1:
            _push(st.k_hist, k_obs, K_WIN)
        _push(st.hct.setdefault(key, []), float(hct_ms), HCT_WIN)
        st.hct_seq[key] = st.seq
        st.seq += 1
        if y != 1 and srv_bytes is not None and srv_bytes > 0:
            _push(st.S_hist, float(srv_bytes), S_WIN)
    return info
