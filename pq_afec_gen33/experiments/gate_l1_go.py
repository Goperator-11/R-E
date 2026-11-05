import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
from gate_v3_parity import binary_report, run_go, sha256_file, utc_now

REFERENCE_SCHEMA = "padfec3.v33fix_policy_reference/1"
SEED_DEFAULT = 20261102
SOURCES = ("experiments/gate_l1_go.py", "experiments/replay_g3.py",
           "padfec3/learn3.py", "padfec3/decide3.py", "padfec3/layout.py",
           "padfec/policy.py", "padfec/quantum.py", "padfec/table.py")
DECISION_KEYS = (
    "action", "delta", "lead", "T", "m", "mode", "W_eff", "client_bytes", "added", "ej", "pen",
    "score", "n2", "j3_pred_pre_ms", "jmin", "n_tied", "n_cands", "n_need", "k", "S", "why",
    "reeval_cond", "alt", "reeval", "p_mean", "p_map", "p_ge_010", "guard_alarm",
    "guard_common_ms", "guard_alarmed_actions", "guard_cleared", "dec_index", "n_reeval",
    "policy_version", "policy_path", "c1_seen", "arrival_streak", "reeval_feedback_suppressed")
C_PKT = 41.983
SEQUENCE_STATE_EVERY = 10
OBSERVATION_ROWS = 30
CACHE_ROWS = 48
SEQUENCE_ROWS = 200
NONE_EVIDENCE = (None,
                 dict(src="none", sent=0, lost=0, bitmap=None, trunc=False),
                 dict(src="none", sent=3, lost=1, bitmap=[0, 1, 1], trunc=False))
MIXED_EVIDENCE = (None,
                  dict(src="c1", sent=4, lost=1, bitmap=[1, 0, 1, 1], trunc=False),
                  dict(src="ack", sent=8, lost=3, bitmap=None, trunc=False),
                  dict(src="c1", sent=4, lost=1, bitmap=[0, 1], trunc=True),
                  dict(src="ack", sent=0, lost=0, bitmap=[], trunc=False),
                  dict(src="none", sent=3, lost=1, bitmap=[0, 1, 1], trunc=False),
                  dict(src="c1", sent=2, lost=2, bitmap=[0, 0], trunc=False),
                  dict(src="ack", sent=3, lost=0, bitmap=[1, 1], trunc=True),
                  dict(src="c1", sent=8, lost=0, bitmap=None, trunc=False))
MISSING_EVIDENCE = (dict(src="c1", sent=4, lost=1, bitmap=[0, 1], trunc=True),
                    None,
                    dict(src="none", sent=0, lost=0, bitmap=None, trunc=False),
                    dict(src="ack", sent=6, lost=2, bitmap=[1, 0, 1], trunc=True),
                    dict(src="c1", sent=0, lost=0, bitmap=None, trunc=False),
                    dict(src="ack", sent=5, lost=1, bitmap=None, trunc=False))
LOSSES = (0.0, 0.02, 0.05, 0.15, 0.3)
UPLINKS = (0.0, 2.0, 5.0, 10.0)
CERTS = (2955, 4032, 6000, 9000, 12000, 16000)
REEVAL_PRONE = {"W": 1280, "k": 2, "u": 2.0, "rtt": 50.0, "cert": 16000}
REQUIRED_COVERAGE = (
    "info_none_binary", "info_none_predict_only", "info_c1_datagram", "info_c1_categorical",
    "info_c1_predict_only", "skip_none_nominal2", "skip_none_shield", "skip_none_guard",
    "skip_c1_no_ctx", "decide_none_reeval", "decide_c1_reeval", "decide_c1_reeval_held",
    "decide_none_alarmed", "decide_cleared", "raised", "transitions", "streak_cap_hits",
    "decide_w1406_k2plus")


def _plain(value):
    return json.loads(json.dumps(value, allow_nan=False))


def _policy():
    sys.path.insert(0, str(ROOT))
    from padfec import policy, quantum
    from padfec3 import decide3, learn3
    from experiments.replay_g3 import RttTrack
    return policy, quantum, learn3, decide3, RttTrack


def _decision(d):
    if set(d) - {"cands"} != set(DECISION_KEYS):
        raise AssertionError("decision keys changed: %s" % sorted(set(d) ^ set(DECISION_KEYS)))
    out = {key: d[key] for key in DECISION_KEYS}
    out["alt"] = None if d["alt"] is None else list(d["alt"]["action"])
    return _plain(out)


def _info(info):
    return _plain(info)


def _roundtrip(learn3, st):
    return learn3.DestState3.from_json(json.loads(json.dumps(st.to_json())))


def _initial(learn3, name):
    st = learn3.new_state()
    if name not in ("cold", "no_rtt"):
        st.k_hist = [2] * 16
        st.S_hist = [30000.0 if name == "nominal" else 8500.0] * 16
        st.hct = {"0,0,0": [100.0] * 32}
        st.hct_seq = {"0,0,0": 0}
        st.seq = 1
    if name == "guard":
        st.g_resid = {"0,2,2": [140.0] * 16}
        st.g_common = [0.0] * 64
        st.g_alarm = {"0,2,2": 0}
    if name == "c1hot":
        st.c1_seen = True
        st.arrival_streak = 3
    return st


def _evidence(mode, i):
    if mode == "none":
        return NONE_EVIDENCE[i % len(NONE_EVIDENCE)]
    if mode == "mixed":
        return MIXED_EVIDENCE[i % len(MIXED_EVIDENCE)]
    if mode == "late":
        if i < 24:
            return NONE_EVIDENCE[i % len(NONE_EVIDENCE)]
        return MIXED_EVIDENCE[(i - 24) % len(MIXED_EVIDENCE)]
    return MISSING_EVIDENCE[i % len(MISSING_EVIDENCE)]


def _observations(learn3):
    result = []
    actions = [(0, 0, 0), (0, 2, 2), (16, 1, 0), (0, 4, 0), (0, 0, 4)]
    cases = [(name, mode) for name in ("cold", "hot", "rtt200", "nominal", "no_rtt", "guard")
             for mode in ("none", "mixed", "late", "trunc_first")]
    cases += [("c1hot", "none"), ("c1hot", "mixed")]
    for name, mode in cases:
        st = _initial(learn3, name)
        case = dict(id="%s_%s" % (name, mode), initial=st.to_json(), rows=[])
        for i in range(OBSERVATION_ROWS):
            rtt = 0.0 if name == "no_rtt" else 200.0 if name in ("rtt200", "nominal") else 50.0
            a = actions[i % len(actions)]
            ctx = learn3.context(st, 1280, 2.0, rtt, C_PKT)
            cuts = learn3.grade_cutoffs(ctx, a) if ctx else (80.0, 150.0)
            hct = [math.nextafter(cuts[0], 0.0), cuts[0], math.nextafter(cuts[0], math.inf),
                   math.nextafter(cuts[1], 0.0), cuts[1], math.nextafter(cuts[1], math.inf)][i % 6]
            row = dict(a=list(a), hct=None if i % 11 == 0 else hct, ok=i % 11 != 0,
                       k=2 if i % 17 else 5, srv=8500.0, rtt=rtt, w=1280, u=2.0, c_pkt=C_PKT,
                       j_pred=None if i % 3 else 80.0, arrivals=_evidence(mode, i))
            info = learn3.observe3(st, a, row["hct"], row["ok"], row["k"], row["srv"], rtt,
                                   W=1280, u_mbps=2.0, c_pkt=C_PKT,
                                   j_pred=row["j_pred"], arrivals=row["arrivals"])
            row.update(info=_info(info), state=_plain(st.to_json()))
            st = _roundtrip(learn3, st)
            case["rows"].append(row)
        result.append(case)
    return result


def _server_bytes(policy, quantum, cert, k, w):
    return float(cert) + policy.S0_BASE_MLKEM + quantum.bin_index(k * w) * C_PKT


def _scene(rng, w=None):
    scene = {"W": rng.choice((1200, 1280, 1350, 1406)), "k": rng.choice((1, 2, 2, 3)),
             "u": rng.choice(UPLINKS), "rtt": rng.choice((10.0, 50.0, 120.0, 200.0, 250.0)),
             "cert": rng.choice(CERTS)}
    if rng.random() < 0.4:
        scene.update(REEVAL_PRONE)
    if w is not None:
        scene["W"] = w
    scene["p"] = rng.choice(LOSSES)
    scene["bias_p"] = rng.choice((0.0, 0.3, 0.6))
    scene["reply"] = rng.choice((0.95, 0.7, 0.3))
    return scene


def _drift(rng, scene):
    if rng.random() < 1.0 / 50:
        scene["p"] = rng.choice(LOSSES)
    if rng.random() < 1.0 / 80:
        scene["u"] = rng.choice(UPLINKS)
    if rng.random() < 1.0 / 80:
        scene["cert"] = rng.choice(CERTS)


def _observation(rng, policy, quantum, scene, decision, biases, seen):
    action = tuple(decision["action"])
    rtt = scene["rtt"]
    j_pred = decision["j3_pred_pre_ms"]
    if action not in biases:
        biases[action] = 0.8 * rtt if rng.random() < scene["bias_p"] else 0.0
    ok = rng.random() >= 0.4 * scene["p"]
    hct = None
    if ok:
        base = j_pred if j_pred is not None else 2.0 * rtt + 20.0
        hct = base + rng.gauss(0.0, 3.0) + biases[action]
        if rng.random() < min(0.9, 1.5 * scene["p"]):
            hct += rtt
        hct = max(1.0, hct)
    k_obs = scene["k"] if rng.random() >= 0.05 else rng.choice((0, 1, 2, 3, 5))
    size = _server_bytes(policy, quantum, scene["cert"], scene["k"], scene["W"])
    roll = rng.random()
    srv = size if roll >= 0.06 else 0.0 if roll < 0.04 else size * 1.2
    if seen["blind"]:
        seen["blind"] -= 1
    elif rng.random() >= 0.03:
        raw = rtt * (1.0 + 0.3 * rng.random())
        seen["rtt"] = raw if seen["rtt"] is None else min(seen["rtt"], raw)
    if rng.random() < 0.05:
        j_pred = None
    return dict(a=list(action), hct=hct, ok=ok, k=k_obs, srv=srv, rtt=seen["rtt"] or 0.0,
                w=scene["W"], u=scene["u"], c_pkt=C_PKT, j_pred=j_pred)


def _arrivals(rng, scene, action, first):
    sent = scene["k"] + action[1] + action[2]
    bits = [0 if rng.random() < scene["p"] else 1 for _ in range(sent)]
    lost = bits.count(0)
    if first or rng.random() < scene["reply"]:
        if rng.random() < 0.85:
            return dict(src="c1", sent=sent, lost=lost, bitmap=bits if rng.random() < 0.5 else None,
                        trunc=False)
        return dict(src="ack", sent=sent, lost=lost, bitmap=None, trunc=False)
    roll = rng.random()
    if roll < 0.4:
        return None
    if roll < 0.55:
        return dict(src="none", sent=0, lost=0, bitmap=None, trunc=False)
    if roll < 0.85:
        return dict(src="c1", sent=sent, lost=lost, bitmap=bits[:rng.randrange(0, sent + 1)], trunc=True)
    return dict(src="c1", sent=0, lost=0, bitmap=None, trunc=False)


def _sequence(learn3, decide3, ident, st, steps):
    initial = _plain(st.to_json())
    rows = []
    state_at = []
    for i in range(steps["n"]):
        scene = steps["scene"](i)
        decide_rtt = steps["rtt"]()
        d = decide3.decide3(st, scene["W"], scene["u"], decide_rtt, C_PKT)
        row = steps["row"](i, d)
        row["decide_rtt"] = decide_rtt
        info = learn3.observe3(st, tuple(row["a"]), row["hct"], row["ok"], row["k"], row["srv"],
                               row["rtt"], W=row["w"], u_mbps=row["u"], c_pkt=row["c_pkt"],
                               j_pred=row["j_pred"], arrivals=row["arrivals"])
        row.update(decision=_decision(d), info=_info(info))
        if i % SEQUENCE_STATE_EVERY == SEQUENCE_STATE_EVERY - 1 or i == steps["n"] - 1:
            row["state"] = _plain(st.to_json())
            state_at.append(i)
        st = _roundtrip(learn3, st)
        rows.append(row)
    return dict(id=ident, initial=initial, rows=rows, state_at=state_at)


def _random_sequence(rng, policy, quantum, learn3, decide3, ident, kind, w):
    scene = _scene(rng, w)
    biases = {}
    seen = {"rtt": None, "blind": rng.choice((0, 0, 0, 30))}
    switch_at = SEQUENCE_ROWS // 2 if kind == "switch" else 0 if kind == "c1" else None

    def drifted(i):
        _drift(rng, scene)
        return scene

    def make_row(i, d):
        row = _observation(rng, policy, quantum, scene, d, biases, seen)
        if switch_at is None or i < switch_at:
            row["arrivals"] = rng.choice((None, NONE_EVIDENCE[1]))
        else:
            row["arrivals"] = _arrivals(rng, scene, row["a"], i == switch_at)
        return row

    steps = dict(n=SEQUENCE_ROWS, scene=drifted, rtt=lambda: seen["rtt"] or 0.0, row=make_row)
    return _sequence(learn3, decide3, ident, learn3.new_state(), steps)


def _reeval_sequence(policy, quantum, learn3, decide3, ident, c1):
    hi = learn3.G.index(0.3)
    st = learn3.new_state()
    size = _server_bytes(policy, quantum, 16000, 2, 1280)
    st.k_hist, st.S_hist = [2], [size]
    st.post = [[1.0 if i == hi else 0.0 for i in range(len(learn3.G))] for _ in learn3.H]
    st.w = [1.0, 0.0, 0.0, 0.0, 0.0]
    st.c1_seen, st.arrival_streak = c1, 3 if c1 else 0
    scene = dict(W=1280, u=2.0)

    def make_row(i, d):
        a = list(d["action"])
        sent = 2 + a[1] + a[2]
        lost = min(sent, (sent * 3 + i % 3) // 10)
        evidence = None
        if c1 and (i < 20 or i % 7 == 3):
            evidence = dict(src="c1", sent=sent, lost=lost, bitmap=None, trunc=False)
        elif c1 and i % 5 == 0:
            evidence = dict(src="c1", sent=sent, lost=lost, bitmap=[1], trunc=True)
        j_pred = d["j3_pred_pre_ms"]
        ok = i % 13 != 12
        hct = (j_pred if j_pred is not None else 120.0) + (i % 4) * 7.5 if ok else None
        return dict(a=a, hct=hct, ok=ok, k=2, srv=size, rtt=50.0, w=1280, u=2.0,
                    c_pkt=C_PKT, j_pred=j_pred, arrivals=evidence)

    steps = dict(n=64, scene=lambda i: scene, rtt=lambda: 50.0, row=make_row)
    return _sequence(learn3, decide3, ident, st, steps)


def _guard_sequence(policy, quantum, learn3, decide3, ident, switch_at):
    st = learn3.new_state()
    size = _server_bytes(policy, quantum, 9000, 2, 1280)
    st.k_hist, st.S_hist = [2] * 16, [size] * 16
    st.g_common = [2.0] * 64
    st.g_resid = {"0,1,2": [40.0] * 8, "0,2,2": [45.0] * 8}
    biased = ("0,1,2", "0,2,2", "0,3,1")
    scene = dict(W=1280, u=2.0)

    def make_row(i, d):
        a = list(d["action"])
        key = "%d,%d,%d" % tuple(a)
        j_pred = d["j3_pred_pre_ms"]
        ok = i % 17 != 16
        hct = None
        if ok:
            hct = (j_pred if j_pred is not None else 110.0) + 2.0 + (40.0 if key in biased else 0.0)
        evidence = None
        if switch_at is not None and i >= switch_at:
            sent = 2 + a[1] + a[2]
            evidence = None if i % 3 == 2 else dict(src="c1", sent=sent, lost=i % 2, bitmap=None, trunc=False)
        return dict(a=a, hct=hct, ok=ok, k=2, srv=size, rtt=50.0, w=1280, u=2.0, c_pkt=C_PKT,
                    j_pred=j_pred, arrivals=evidence)

    steps = dict(n=96, scene=lambda i: scene, rtt=lambda: 50.0, row=make_row)
    return _sequence(learn3, decide3, ident, st, steps)


def _sequences(seed, policy, quantum, learn3, decide3):
    rng = random.Random(seed)
    out = []
    for kind in ("none", "c1", "switch"):
        for j in range(3):
            w = (None, None, 1406)[j]
            out.append(_random_sequence(rng, policy, quantum, learn3, decide3, "%s_%d" % (kind, j), kind, w))
    out.append(_reeval_sequence(policy, quantum, learn3, decide3, "reeval_none", False))
    out.append(_reeval_sequence(policy, quantum, learn3, decide3, "reeval_c1", True))
    out.append(_guard_sequence(policy, quantum, learn3, decide3, "guard_none", None))
    out.append(_guard_sequence(policy, quantum, learn3, decide3, "guard_switch", 30))
    return out


def _caches(learn3, decide3, RttTrack):
    cases = []
    for name, mode in itertools.product(("proxy", "ack_later", "ack_first"), ("none", "mixed")):
        st = learn3.new_state()
        rt = RttTrack()
        rows = []
        for i in range(CACHE_ROWS):
            d = decide3.decide3(st, 1280, 2.0, rt.rtt(), C_PKT)
            valid = name == "ack_first" or (name == "ack_later" and i >= 7)
            ok = i % 13 != 0
            hct = 80.0 + (i % 5) * 60.0
            path_rtt = [70.0, 50.0, 60.0, 40.0][i % 4]
            row = dict(a=list(d["action"]), hct=hct if ok else None, ok=ok, k=2, srv=8500.0,
                       path_rtt=path_rtt, path_valid=valid, w=1280, u=2.0, c_pkt=C_PKT,
                       j_pred=d["j3_pred_pre_ms"], arrivals=_evidence(mode, i))
            rt.observe(dict(path_rtt_valid=valid, path_rtt_ms=path_rtt, ok=ok, ms=hct))
            info = learn3.observe3(st, d["action"], row["hct"], ok, 2, 8500.0, rt.rtt(),
                                   W=1280, u_mbps=2.0, c_pkt=C_PKT,
                                   j_pred=d["j3_pred_pre_ms"], arrivals=row["arrivals"])
            entry = dict(state=st.to_json(), min_rtt_ms=rt.min_rtt, rtt_observations=rt.rtt_obs,
                         min_hct_ms=rt.min_hct, conns=i + 1)
            row.update(decision=_decision(d), info=_info(info), entry=_plain(entry),
                       p_after=learn3.post_mean(learn3.combined(st)))
            st = _roundtrip(learn3, st)
            rows.append(row)
        cases.append(dict(id="%s_%s" % (name, mode), rows=rows))
    return cases


def _invalid_arrivals(learn3):
    base = dict(src="c1", sent=2, lost=1, bitmap=[1, 0], trunc=False)
    invalid = [[], {}, {**base, "extra": 0}]
    for key, values in {"src": [None, 3, "bad"], "sent": [None, True, 1.5, -1, 9],
                        "lost": [None, False, 1.2, -1, 3], "trunc": [None, 0, 1, "false"],
                        "bitmap": [[True, 0], [2, 0], [1], [1, 1], [1, 0, 1], "10"]}.items():
        invalid.extend({**base, key: value} for value in values)
    for key in base:
        invalid.append({k: v for k, v in base.items() if k != key})
    for name in ("hot", "c1hot"):
        for value in invalid:
            st = _initial(learn3, name)
            before = st.to_json()
            try:
                learn3.observe3(st, (0, 0, 0), 80.0, True, 2, 8500.0, 50.0,
                                W=1280, u_mbps=2.0, c_pkt=C_PKT, arrivals=value)
            except (ValueError, TypeError):
                if before != st.to_json():
                    raise AssertionError("rejected arrivals mutated state: %r" % (value,))
            else:
                raise AssertionError("arrivals accepted: %r" % (value,))
    return invalid


def _states(learn3):
    none_state = _initial(learn3, "guard")
    c1_state = _initial(learn3, "hot")
    learn3.observe3(c1_state, (0, 2, 2), 120.0, True, 2, 8500.0, 50.0, W=1280, u_mbps=2.0,
                    c_pkt=C_PKT, j_pred=118.0,
                    arrivals=dict(src="ack", sent=6, lost=1, bitmap=None, trunc=False))
    return _plain(none_state.to_json()), _plain(c1_state.to_json())


def _invalid_states(learn3):
    none_state, c1_state = _states(learn3)
    invalid = [dict(c1_state, v=v) for v in list(range(1, 11)) + [12, 11.0, None, "11"]]
    invalid += [dict(c1_state, c1_seen=v) for v in (1, 0, None, "true", "false", [])]
    invalid += [dict(c1_state, arrival_streak=v) for v in (-1, True, False, 1.0, 9, None, "1")]
    invalid.append(dict(none_state, arrival_streak=1))
    invalid.append(dict(none_state, c1_seen=True))
    invalid.append(dict(c1_state, stats=dict(c1_state["stats"], binary=-1)))
    for key in ("c1_seen", "arrival_streak"):
        invalid.append({k: v for k, v in c1_state.items() if k != key})
    for value in invalid:
        try:
            learn3.DestState3.from_json(json.loads(json.dumps(value)))
        except (ValueError, TypeError, KeyError):
            continue
        raise AssertionError("state accepted: %r" % ({k: value[k] for k in ("v", "c1_seen", "arrival_streak") if k in value},))
    return invalid


def _cache_files(learn3, schema):
    none_state, c1_state = _states(learn3)
    def entry(state, conns):
        return dict(state=state, min_rtt_ms=50.0, rtt_observations=conns, min_hct_ms=90.5, conns=conns)
    good = dict(schema=schema, dests={"192.0.2.1:443": entry(none_state, 3),
                                      "192.0.2.2:443": entry(c1_state, 5)})
    for e in good["dests"].values():
        learn3.DestState3.from_json(e["state"])
    v4 = {k: v for k, v in none_state.items() if k not in ("c1_seen", "arrival_streak")}
    v4["v"] = 4
    v4["stats"] = {k: v for k, v in none_state["stats"].items() if k != "binary"}
    v3 = dict(v4, v=3)
    def doc(state, schema=schema, **extra):
        return json.dumps(dict(schema=schema, dests={"192.0.2.1:443": entry(state, 1)}, **extra))
    files = [dict(id="valid_two_paths", text=json.dumps(good), ok=True, saved=good),
             dict(id="valid_empty", text=json.dumps(dict(schema=schema, dests={})), ok=True,
                  saved=dict(schema=schema, dests={})),
             dict(id="old_schema_v3_state", text=doc(v3, "padfec3.cache3/3"), ok=False),
             dict(id="old_schema_v4_state", text=doc(v4, "padfec3.cache3/3"), ok=False),
             dict(id="old_schema_current_state", text=doc(c1_state, "padfec3.cache3/3"), ok=False),
             dict(id="current_schema_v4_state", text=doc(v4), ok=False),
             dict(id="missing_c1_seen", text=doc({k: v for k, v in c1_state.items() if k != "c1_seen"}), ok=False),
             dict(id="missing_streak", text=doc({k: v for k, v in c1_state.items() if k != "arrival_streak"}), ok=False),
             dict(id="null_c1_seen", text=doc(dict(c1_state, c1_seen=None)), ok=False),
             dict(id="string_c1_seen", text=doc(dict(c1_state, c1_seen="true")), ok=False),
             dict(id="streak_over_cap", text=doc(dict(c1_state, arrival_streak=9)), ok=False),
             dict(id="streak_float", text=doc(dict(c1_state, arrival_streak=1.5)), ok=False),
             dict(id="streak_without_c1", text=doc(dict(none_state, arrival_streak=2)), ok=False),
             dict(id="c1_with_alarm", text=doc(dict(none_state, c1_seen=True)), ok=False),
             dict(id="unknown_state_key", text=doc(dict(c1_state, extra=1)), ok=False),
             dict(id="unknown_stats_key", text=doc(dict(c1_state, stats=dict(c1_state["stats"], monitor=0))), ok=False),
             dict(id="trailing_document", text=json.dumps(good) + " {}", ok=False)]
    for f in files:
        if not f["ok"]:
            f.pop("saved", None)
    return files


def generate(dest, seed):
    if dest.exists():
        raise FileExistsError(dest)
    policy, quantum, learn3, decide3, RttTrack = _policy()
    if decide3.UDP_MAX != policy.QUICGO_MAX_IPS or learn3.STATE_VERSION != 11:
        raise AssertionError("unexpected policy constants")
    if abs(policy.C_PKT_POLICY_DEFAULT - C_PKT) != 0.0:
        raise AssertionError("c_pkt drifted")
    started = time.monotonic()
    arrivals = [dict(sent=s, lost=l, likelihood=learn3.arrival_likelihood(s, l))
                for s in range(1, 9) for l in range(s + 1)]
    classes = []
    actions = [(d, lead, m - lead) for d in (0, 16) for m in range(5) for lead in range(m + 1)]
    for k, u, rtt, n, a in itertools.product((1, 2, 4), (0.0, 2.0), (50.0, 200.0), (1, 7, 20), actions):
        ctx = dict(k=k, W=1280, u=u, rtt=rtt, n_need=n, S=8500.0)
        cuts = learn3.grade_cutoffs(ctx, a)
        hs = [x for cut in cuts for x in (math.nextafter(cut, 0.0), cut, math.nextafter(cut, math.inf))]
        classes.append(dict(ctx=ctx, a=list(a), cuts=list(cuts), hct=hs,
                            grades=[learn3.classify_hct(ctx, a, h, True) for h in hs],
                            probabilities=[learn3.class_probabilities(ctx, a, g) for g in range(26)],
                            likelihood=[learn3.class_likelihood(ctx, a, grade) for grade in range(3)]))
    schema = "padfec3.cache3/%d" % learn3.STATE_VERSION
    doc = dict(schema=REFERENCE_SCHEMA, seed=seed, policy_version=learn3.POLICY_VERSION,
               state_version=learn3.STATE_VERSION, cache_schema=schema, udp_max=decide3.UDP_MAX,
               arrivals=arrivals, classes=classes, observations=_observations(learn3),
               sequences=_sequences(seed, policy, quantum, learn3, decide3),
               caches=_caches(learn3, decide3, RttTrack),
               invalid_arrivals=_invalid_arrivals(learn3), invalid_states=_invalid_states(learn3),
               cache_files=_cache_files(learn3, schema))
    doc["coverage"] = coverage(doc)
    missing = [key for key in REQUIRED_COVERAGE if not doc["coverage"].get(key)]
    if missing:
        raise AssertionError("reference lost coverage: %s" % missing)
    doc["sources"] = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES}
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n"
    dest.write_text(text, encoding="utf-8", newline="\n")
    receipt = dict(path=dest.name, sha256=hashlib.sha256(dest.read_bytes()).hexdigest(), seed=seed,
                   schema=REFERENCE_SCHEMA, policy_version=doc["policy_version"],
                   state_version=doc["state_version"], cache_schema=schema, udp_max=doc["udp_max"],
                   counts={key: len(doc[key]) for key in ("arrivals", "classes", "observations", "sequences",
                                                          "caches", "invalid_arrivals", "invalid_states",
                                                          "cache_files")},
                   rows=dict(observations=sum(len(s["rows"]) for s in doc["observations"]),
                             sequences=sum(len(s["rows"]) for s in doc["sequences"]),
                             caches=sum(len(s["rows"]) for s in doc["caches"])),
                   coverage=doc["coverage"], sources=doc["sources"],
                   python_seconds=time.monotonic() - started)
    dest.with_suffix(".receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8",
                                                 newline="\n")
    return receipt


def coverage(doc):
    counts = {}
    def add(key, n=1):
        counts[key] = counts.get(key, 0) + n
    rows = [r for s in doc["observations"] for r in s["rows"]]
    rows += [r for s in doc["sequences"] for r in s["rows"]]
    rows += [r for s in doc["caches"] for r in s["rows"]]
    for r in rows:
        info = r["info"]
        add("info_%s_%s" % (info["policy_path"], info["loss_update_kind"]))
        if info["skip"] is not None:
            add("skip_%s_%s" % (info["policy_path"], info["skip"]))
        if info.get("legacy_skip_reason") is not None:
            add("legacy_skip_%s" % info["legacy_skip_reason"])
        add("raised", len(info["raised"]))
        add("streak_cap_hits", int(info["arrival_streak_after"] == 8))
        d = r.get("decision")
        if d is None:
            continue
        path = d["policy_path"]
        add("decide_%s_%s" % (path, d["why"]))
        add("decide_%s_penalised" % path, int(d["pen"] > 0))
        add("decide_%s_reeval_cond" % path, int(d["reeval_cond"]))
        add("decide_%s_reeval_held" % path, int(d["reeval_cond"] and d["reeval_feedback_suppressed"]))
        add("decide_cleared", len(d["guard_cleared"]))
        add("decide_%s_alarmed" % path, int(d["guard_alarmed_actions"] > 0))
        add("decide_w1406", int(d["W_eff"] is not None and d["W_eff"] - d["delta"] == 1406))
        add("decide_w1406_k2plus", int(d["k"] is not None and d["k"] >= 2 and d["W_eff"] - d["delta"] == 1406))
    for s in doc["observations"] + doc["sequences"]:
        before = s["initial"]
        for r in s["rows"]:
            if r["info"]["policy_path"] == "c1" and not before["c1_seen"]:
                add("transitions")
                break
    return dict(sorted(counts.items()))


def expected(doc):
    return {
        "arrivals": [{"likelihood": r["likelihood"]} for r in doc["arrivals"]],
        "classes": [{k: r[k] for k in ("cuts", "grades", "probabilities", "likelihood")} for r in doc["classes"]],
        "observations": [dict(id=s["id"], rows=[{k: r[k] for k in ("info", "state")} for r in s["rows"]])
                         for s in doc["observations"]],
        "sequences": [dict(id=s["id"], rows=[{k: r[k] for k in ("decision", "info", "state") if k in r}
                                             for r in s["rows"]]) for s in doc.get("sequences", [])],
        "caches": [dict(id=s["id"], rows=[{k: r[k] for k in ("decision", "info", "entry", "p_after")} for r in s["rows"]])
                   for s in doc["caches"]],
        "invalid_arrivals": [True] * len(doc["invalid_arrivals"]),
        "invalid_states": [True] * len(doc.get("invalid_states", [])),
        "cache_files": [{k: f[k] for k in ("id", "ok", "saved") if k in f} for f in doc.get("cache_files", [])],
    }


def compare(want, got):
    counts = dict(leaves=0, bit_exact=0, relative=0, absolute=0, failures=0)
    first = []
    def fail(path, a, b):
        counts["failures"] += 1
        if len(first) < 20:
            first.append(dict(path=path, expected=a, actual=b))
    def visit(a, b, path):
        if isinstance(a, dict):
            if not isinstance(b, dict) or set(a) != set(b):
                fail(path, sorted(a), sorted(b) if isinstance(b, dict) else b)
                return
            for key in a:
                visit(a[key], b[key], path + "." + key)
        elif isinstance(a, list):
            if not isinstance(b, list) or len(a) != len(b):
                fail(path, len(a), len(b) if isinstance(b, list) else b)
                return
            for i, (x, y) in enumerate(zip(a, b)):
                visit(x, y, path + "[%d]" % i)
        else:
            counts["leaves"] += 1
            if a == b and (a is None or isinstance(a, bool) == isinstance(b, bool)):
                counts["bit_exact"] += 1
                return
            exact_window = any(key in path for key in (".state.S_hist[", ".state.hct.", ".entry.state.S_hist[", ".entry.state.hct."))
            if not exact_window and isinstance(a, float) and isinstance(b, (int, float)) and not isinstance(b, bool) and math.isfinite(b):
                relative = any(key in path for key in (".post[", ".w[", ".p_mean", ".p_after", ".probabilities[", ".likelihood["))
                counts["relative" if relative else "absolute"] += 1
                error = abs(a - b)
                if error <= (1e-12 * max(abs(a), abs(b)) if relative else 1e-9):
                    return
            fail(path, a, b)
    visit(want, got, "l1")
    return dict(counts=counts, first_failures=first, passed=counts["failures"] == 0)


def check(args):
    target = Path(args.out)
    if target.exists():
        raise FileExistsError(target)
    started = time.monotonic()
    doc = json.loads(Path(args.ref).read_text(encoding="utf-8"))
    problems = []
    for rel, sha in doc["sources"].items():
        if sha256_file(str(ROOT / rel)) != sha:
            problems.append("reference source changed: " + rel)
    receipt = json.loads(Path(args.ref).with_suffix(".receipt.json").read_text(encoding="utf-8"))
    if sha256_file(args.ref) != receipt["sha256"]:
        problems.append("reference differs from frozen receipt")
    binary, bp = binary_report(args.bin)
    problems += bp
    input_path = target.with_suffix(".input.json")
    with input_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump({"l1": doc}, stream)
        stream.write("\n")
    got, go_seconds = run_go(args.bin, str(input_path))
    got_path = target.with_suffix(".go.json")
    with got_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(got, stream)
        stream.write("\n")
    constants = got.get("constants", {})
    for key, want in (("policy_version", doc.get("policy_version")), ("state_version", doc.get("state_version")),
                      ("udp_max", doc.get("udp_max"))):
        if want is not None and constants.get(key) != want:
            problems.append("binary constant %s %r, reference %r" % (key, constants.get(key), want))
    result = compare(expected(doc), got["l1"])
    result.update(schema="padfec3.gate_l1_go/2", finished_utc=utc_now(), reference=str(args.ref),
                  reference_schema=doc.get("schema"), reference_seed=doc.get("seed"),
                  reference_sha256=sha256_file(args.ref), input_sha256=sha256_file(str(input_path)),
                  output_sha256=sha256_file(str(got_path)), binary=binary, problems=problems,
                  go_seconds=go_seconds, elapsed_seconds=time.monotonic() - started)
    result["passed"] = result["passed"] and not problems
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result))
    return 0 if result["passed"] else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate", metavar="REF")
    parser.add_argument("--seed", type=int, default=SEED_DEFAULT)
    parser.add_argument("--ref")
    parser.add_argument("--bin")
    parser.add_argument("--out")
    args = parser.parse_args()
    if args.generate:
        print(json.dumps(generate(Path(args.generate), args.seed)))
        return 0
    if not (args.ref and args.bin and args.out):
        parser.error("--ref, --bin and --out are required unless --generate is given")
    return check(args)


if __name__ == "__main__":
    raise SystemExit(main())
