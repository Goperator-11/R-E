import importlib
import json
import random
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.dont_write_bytecode = True

from padfec import policy, quantum
from padfec3 import decide3, layout, learn3


ROOT = Path(__file__).resolve().parents[1]
V32_ROOT = ROOT / "g3/v33/fixtures/S5_test_inputs_v1/policies/v32"
L3_RECORD_ROOT = ROOT / "g3/v33/policy_snapshots/L3_record_only_v1"
PACKAGES = ("afec", "padfec", "padfec3")
C_PKT = policy.C_PKT_POLICY_DEFAULT
L3_DECISION_SKIP = {"policy_version", "monitor_prediction", "monitor_mode"}
L3_INFO_SKIP = {"monitor_reason", "monitor_prediction", "monitor_grade", "monitor",
                "raised", "alarmed"}
L3_STATE_SKIP = {"v", "stats", "monitor", "monitor_pending"}


def _owned(name):
    return name.split(".", 1)[0] in PACKAGES


def load_reference(root, *, parity_cap=policy.QUICGO_MAX_IPS):
    root = str(Path(root).resolve(strict=True))
    saved = {name: module for name, module in sys.modules.items() if _owned(name)}
    for name in saved:
        del sys.modules[name]
    sys.path.insert(0, root)
    try:
        learn = importlib.import_module("padfec3.learn3")
        decide = importlib.import_module("padfec3.decide3")
        modules = {name: module for name, module in sys.modules.items() if _owned(name)}
    finally:
        sys.path.remove(root)
        for name in [name for name in sys.modules if _owned(name)]:
            del sys.modules[name]
        sys.modules.update(saved)
    if not Path(learn.__file__).resolve().is_relative_to(root):
        raise RuntimeError("reference policy was not loaded from its own root")
    if parity_cap is not None:
        decide.UDP_MAX = parity_cap
    return SimpleNamespace(learn3=learn, decide3=decide, modules=modules)


@pytest.fixture(scope="module")
def v32():
    return load_reference(V32_ROOT)


@pytest.fixture(scope="module")
def l3_record():
    ref = load_reference(L3_RECORD_ROOT)
    monitor = ref.modules["padfec3.monitor3"]
    assert (monitor.ENABLED, monitor.APPLY_BETA, monitor.APPLY_SHARED, monitor.C1_REEVAL) == \
        (True, False, False, False)
    return ref


def server_bytes(cert, k, w):
    return float(cert) + policy.S0_BASE_MLKEM + quantum.bin_index(k * w) * C_PKT


LOSSES = (0.0, 0.02, 0.05, 0.15, 0.3)
UPLINKS = (0.0, 2.0, 5.0, 10.0)
CERTS = (2955, 4032, 6000, 9000, 12000, 16000)
REEVAL_PRONE = {"W": 1280, "k": 2, "u": 2.0, "rtt": 50.0, "cert": 16000}


def random_scene(rng):
    scene = {"W": rng.choice((1200, 1280, 1350, 1406)), "k": rng.choice((1, 2, 2, 3)),
             "u": rng.choice(UPLINKS), "rtt": rng.choice((10.0, 50.0, 120.0, 200.0, 250.0)),
             "cert": rng.choice(CERTS)}
    if rng.random() < 0.4:
        scene.update(REEVAL_PRONE)
    scene["p"] = rng.choice(LOSSES)
    scene["bias_p"] = rng.choice((0.0, 0.3, 0.6))
    scene["reply"] = rng.choice((0.95, 0.7, 0.3))
    return scene


def drift(rng, scene):
    if rng.random() < 1.0 / 50:
        scene["p"] = rng.choice(LOSSES)
    if rng.random() < 1.0 / 80:
        scene["u"] = rng.choice(UPLINKS)
    if rng.random() < 1.0 / 80:
        scene["cert"] = rng.choice(CERTS)


def random_observation(rng, scene, decision, biases, seen):
    action = tuple(decision["action"])
    rtt = scene["rtt"]
    j_pred = decision.get("j3_pred_pre_ms")
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
    k_obs = scene["k"] if rng.random() >= 0.05 else rng.choice((1, 2, 3, True, None))
    size = server_bytes(scene["cert"], scene["k"], scene["W"])
    roll = rng.random()
    srv = size if roll >= 0.06 else (None if roll < 0.02 else 0 if roll < 0.04 else size * 1.2)
    if seen["blind"]:
        seen["blind"] -= 1
    elif rng.random() >= 0.03:
        raw = rtt * (1.0 + 0.3 * rng.random())
        seen["rtt"] = raw if seen["rtt"] is None else min(seen["rtt"], raw)
    if rng.random() < 0.05:
        j_pred = None
    return {"action": action, "hct_ms": hct, "ok": ok, "k_obs": k_obs, "srv_bytes": srv,
            "rtt_ms": seen["rtt"], "j_pred": j_pred}


def random_arrivals(rng, scene, action, first):
    sent = scene["k"] + action[1] + action[2]
    bits = [0 if rng.random() < scene["p"] else 1 for _ in range(sent)]
    lost = bits.count(0)
    if first or rng.random() < scene["reply"]:
        if rng.random() < 0.85:
            return {"src": "c1", "sent": sent, "lost": lost, "trunc": False,
                    "bitmap": bits if rng.random() < 0.5 else None}
        return {"src": "ack", "sent": sent, "lost": lost, "trunc": False, "bitmap": None}
    roll = rng.random()
    if roll < 0.4:
        return None
    if roll < 0.55:
        return {"src": "none", "sent": 0, "lost": 0, "trunc": False, "bitmap": None}
    if roll < 0.85:
        cut = rng.randrange(0, sent + 1)
        return {"src": "c1", "sent": sent, "lost": lost, "trunc": True, "bitmap": bits[:cut]}
    return {"src": "c1", "sent": 0, "lost": 0, "trunc": False, "bitmap": None}


def observe(learn, st, obs, scene, arrivals=False):
    extra = {} if arrivals is False else {"arrivals": deepcopy(arrivals)}
    return learn.observe3(st, obs["action"], obs["hct_ms"], obs["ok"], obs["k_obs"],
                          obs["srv_bytes"], obs["rtt_ms"], W=scene["W"], u_mbps=scene["u"],
                          c_pkt=C_PKT, j_pred=obs["j_pred"], **extra)


def decide(decide_module, st, scene, rtt_obs):
    return decide_module.decide3(st, scene["W"], scene["u"], rtt_obs, C_PKT)


def differences(expected, actual, skip=()):
    return sorted(key for key in expected if key not in skip and actual.get(key, KeyError) != expected[key])


def state_differences(expected, actual, skip_keys, skip_stats=()):
    out = [key for key in expected if key not in skip_keys and actual.get(key, KeyError) != expected[key]]
    out += ["stats." + key for key in expected.get("stats", {})
            if key not in skip_stats and actual["stats"].get(key, KeyError) != expected["stats"][key]]
    return sorted(out)


def run_none_equivalence(ref, steps, seed):
    rng = random.Random(seed)
    counts = {"steps": 0, "episodes": 0, "mismatch": [], "why": {}, "skip": {},
              "raised": 0, "pen_positive": 0, "fail": 0, "updated": 0, "cleared": 0}
    while counts["steps"] < steps:
        scene = random_scene(rng)
        counts["episodes"] += 1
        old, new = ref.learn3.new_state(), learn3.new_state()
        biases = {}
        seen = {"rtt": None, "blind": rng.choice((0, 0, 0, 30))}
        for _ in range(rng.randrange(40, 400)):
            if counts["steps"] >= steps:
                break
            counts["steps"] += 1
            drift(rng, scene)
            expected = decide(ref.decide3, old, scene, seen["rtt"])
            actual = decide(decide3, new, scene, seen["rtt"])
            bad = differences(expected, actual, {"policy_version"})
            if bad or actual["policy_path"] != "none":
                counts["mismatch"].append(("decide", counts["steps"], bad))
            counts["why"][expected["why"]] = counts["why"].get(expected["why"], 0) + 1
            counts["pen_positive"] += int(bool(expected["pen"]))
            counts["cleared"] += len(expected["guard_cleared"])
            obs = random_observation(rng, scene, expected, biases, seen)
            evidence = rng.choice((False, None, {"src": "none", "sent": 0, "lost": 0,
                                                 "trunc": False, "bitmap": None}))
            info_old = observe(ref.learn3, old, obs, scene)
            info_new = observe(learn3, new, obs, scene, evidence)
            bad = differences(info_old, info_new)
            if bad or info_new["policy_path"] != "none":
                counts["mismatch"].append(("observe", counts["steps"], bad))
            bad = state_differences(old.to_json(), new.to_json(), {"v", "stats"})
            if bad or new.c1_seen or new.arrival_streak:
                counts["mismatch"].append(("state", counts["steps"], bad))
            counts["skip"][info_old["skip"]] = counts["skip"].get(info_old["skip"], 0) + 1
            counts["raised"] += len(info_old["raised"])
            counts["fail"] += int(not obs["ok"])
            counts["updated"] += int(info_old["updated"])
    return counts


def l3_from_current(ref, st):
    data = st.to_json()
    data.pop("c1_seen")
    data["v"] = ref.learn3.STATE_VERSION
    data["monitor"] = ref.modules["padfec3.monitor3"].new_state()
    data["monitor_pending"] = None
    return ref.learn3.DestState3.from_json(data)


def run_c1_lockstep(ref, old, new, scene, rng, seen, length, counts, first):
    biases = {}
    for step in range(length):
        counts["steps"] += 1
        drift(rng, scene)
        was_c1 = new.c1_seen
        expected = decide(ref.decide3, old, scene, seen["rtt"])
        actual = decide(decide3, new, scene, seen["rtt"])
        bad = differences(expected, actual, L3_DECISION_SKIP)
        if bad or actual["policy_path"] != ("c1" if was_c1 else "none"):
            counts["mismatch"].append(("decide", counts["steps"], bad))
        counts["why"][expected["why"]] = counts["why"].get(expected["why"], 0) + 1
        counts["suppressed"] += int(expected["reeval_feedback_suppressed"] and expected["reeval_cond"])
        obs = random_observation(rng, scene, expected, biases, seen)
        arrivals = random_arrivals(rng, scene, obs["action"], first and step == 0)
        info_old = observe(ref.learn3, old, obs, scene, arrivals)
        info_new = observe(learn3, new, obs, scene, arrivals)
        bad = differences(info_old, info_new, L3_INFO_SKIP)
        if bad or info_new["policy_path"] != "c1":
            counts["mismatch"].append(("observe", counts["steps"], bad))
        bad = state_differences(old.to_json(), new.to_json(), L3_STATE_SKIP, {"alarm_raised"})
        if bad or not new.c1_seen:
            counts["mismatch"].append(("state", counts["steps"], bad))
        kind = info_old["loss_update_kind"]
        counts["kind"][kind] = counts["kind"].get(kind, 0) + 1
        counts["streak_max"] = max(counts["streak_max"], new.arrival_streak)


def new_c1_counts():
    return {"steps": 0, "episodes": 0, "mismatch": [], "why": {}, "kind": {},
            "suppressed": 0, "streak_max": 0}


def run_c1_equivalence(ref, steps, seed):
    rng = random.Random(seed)
    counts = new_c1_counts()
    while counts["steps"] < steps:
        scene = random_scene(rng)
        counts["episodes"] += 1
        length = min(rng.randrange(40, 400), steps - counts["steps"])
        run_c1_lockstep(ref, ref.learn3.new_state(), learn3.new_state(), scene, rng,
                        {"rtt": None, "blind": rng.choice((0, 0, 0, 30))}, length, counts, True)
    return counts


def run_transition(v32_ref, l3_ref, seed, before, after):
    rng = random.Random(seed)
    scene = {"W": 1280, "k": 2, "u": 2.0, "rtt": 50.0, "cert": 9000, "p": 0.15, "bias_p": 0.6,
             "reply": 0.7}
    old, new = v32_ref.learn3.new_state(), learn3.new_state()
    biases = {}
    seen = {"rtt": None, "blind": 0}
    for _ in range(before):
        drift(rng, scene)
        expected = decide(v32_ref.decide3, old, scene, seen["rtt"])
        actual = decide(decide3, new, scene, seen["rtt"])
        assert differences(expected, actual, {"policy_version"}) == []
        obs = random_observation(rng, scene, expected, biases, seen)
        observe(v32_ref.learn3, old, obs, scene)
        observe(learn3, new, obs, scene, None)
    assert not new.c1_seen and new.to_json()["post"] == old.to_json()["post"]
    alarms = len(new.g_alarm)
    cleared = new.stats["alarm_cleared"]
    decision = decide(decide3, new, scene, seen["rtt"])
    obs = random_observation(rng, scene, decision, biases, seen)
    arrivals = random_arrivals(rng, scene, obs["action"], True)
    prior = deepcopy(new)
    info = observe(learn3, new, obs, scene, arrivals)
    assert info["policy_path"] == "c1" and info["loss_update_kind"] == "datagram"
    assert new.c1_seen and new.g_alarm == {} and new.arrival_streak == 1
    assert new.stats["alarm_cleared"] == cleared + alarms
    values = learn3.arrival_likelihood(arrivals["sent"], arrivals["lost"])
    post, weights, _ = learn3.filter_step(prior.post, prior.w, values)
    assert (new.post, new.w) == (post, weights)
    counts = new_c1_counts()
    shadow = l3_from_current(l3_ref, new)
    run_c1_lockstep(l3_ref, shadow, new, scene, rng, seen, after, counts, False)
    return alarms, counts


def test_none_path_matches_v32_bit_for_bit(v32):
    counts = run_none_equivalence(v32, 800, 20261102)
    assert counts["mismatch"] == []
    assert counts["why"].get("reeval", 0) > 0 and counts["why"].get("cold", 0) > 0
    assert counts["why"].get("no_rtt", 0) > 0
    for reason in ("nominal2", "shield", "guard"):
        assert counts["skip"].get(reason, 0) > 0, reason
    assert counts["raised"] > 0 and counts["pen_positive"] > 0 and counts["fail"] > 0


def test_c1_path_matches_l3_record_only_decisions(l3_record):
    counts = run_c1_equivalence(l3_record, 800, 31415)
    assert counts["mismatch"] == []
    assert counts["why"].get("reeval", 0) > 0 and counts["suppressed"] > 0
    for kind in ("datagram", "categorical", "predict_only"):
        assert counts["kind"].get(kind, 0) > 0, kind
    assert counts["streak_max"] == learn3.ARRIVAL_STREAK_CAP


def test_calibrated_cost_with_zero_beta_is_the_expected_cost(l3_record):
    ref = l3_record.learn3
    state = ref.new_state()
    state.k_hist, state.S_hist = [2], [server_bytes(9000, 2, 1280)]
    ctx = ref.context(state, 1280, 2.0, 50.0, C_PKT)
    post = ref.combined(state)
    for candidate in l3_record.decide3.candidates3(2, 1280, ctx["S"], C_PKT):
        expected = 0.0
        for g, weight in enumerate(post):
            expected += weight * ref.model_point(2, candidate["W_eff"], 2.0, 50.0, ctx["n_need"],
                                                 candidate["lead"], candidate["m"], g)[0]
        assert ref.calibrated_cost(ctx, candidate["action"], post, 0.0, expected) is expected


def test_destination_switches_from_v32_rules_to_c1_rules_once(v32, l3_record):
    alarms, counts = run_transition(v32, l3_record, 10, 260, 300)
    assert alarms > 0
    assert counts["mismatch"] == []
    assert counts["kind"].get("categorical", 0) > 0


def test_none_evidence_after_c1_keeps_c1_rules():
    state = learn3.new_state()
    state.k_hist, state.S_hist = [2], [server_bytes(9000, 2, 1280)]
    state.hct["0,3,1"] = [75.0] * learn3.BASE_MIN
    learn3.observe3(state, (0, 3, 1), 75.0, True, 2, server_bytes(9000, 2, 1280), 50.0, W=1280,
                    u_mbps=2.0, c_pkt=C_PKT,
                    arrivals={"src": "c1", "sent": 6, "lost": 0, "bitmap": None, "trunc": False})
    assert state.c1_seen and state.arrival_streak == 1
    info = learn3.observe3(state, (0, 3, 1), 75.0, True, 2, server_bytes(9000, 2, 1280), 50.0,
                           W=1280, u_mbps=2.0, c_pkt=C_PKT, j_pred=74.0)
    assert info["policy_path"] == "c1" and info["loss_update_kind"] == "categorical"
    assert state.c1_seen and state.arrival_streak == 0 and state.g_alarm == {}


def test_c1_reevaluation_waits_for_missing_feedback():
    hi = learn3.G.index(0.3)
    state = learn3.new_state()
    state.k_hist, state.S_hist = [2], [server_bytes(16000, 2, 1280)]
    state.post = [[1.0 if i == hi else 0.0 for i in range(len(learn3.G))] for _ in learn3.H]
    state.w = [1.0, 0.0, 0.0, 0.0, 0.0]
    state.c1_seen, state.arrival_streak = True, 3
    whys = [decide3.decide3(state, 1280, 2.0, 50.0, C_PKT)["why"] for _ in range(40)]
    assert whys == ["ej"] * 40 and state.n_reeval == 0 and state.n_dec == 40
    state.arrival_streak = 0
    results = [decide3.decide3(state, 1280, 2.0, 50.0, C_PKT) for _ in range(16)]
    assert [r["why"] for r in results] == ["ej"] * 15 + ["reeval"]
    assert all(r["reeval_cond"] and not r["reeval_feedback_suppressed"] for r in results)
    assert state.n_reeval == 16


def test_c1_decisions_ignore_guard_residuals():
    state = learn3.new_state()
    size = server_bytes(9000, 2, 1280)
    for _ in range(12):
        learn3.observe3(state, (0, 2, 2), 102.0, True, 2, size, 50.0, W=1280, u_mbps=2.0,
                        c_pkt=C_PKT, j_pred=100.0)
    learn3.enter_c1(state)
    for _ in range(12):
        info = learn3.observe3(state, (0, 1, 2), 160.0, True, 2, size, 50.0, W=1280,
                               u_mbps=2.0, c_pkt=C_PKT, j_pred=100.0)
        assert info["raised"] == [] and not info["alarmed"]
    assert state.g_alarm == {} and learn3.guard_excess(state, "0,1,2", 2.0) == 58.0
    result = decide3.decide3(state, 1280, 2.0, 50.0, C_PKT, keep_cands=True)
    assert all(c["pen"] == 0.0 and c["score"] == c["ej"] for c in result["cands"])
    assert result["guard_cleared"] == [] and not result["guard_alarm"]


@pytest.mark.parametrize("k,w,size", [(2, 1406, 2000.0), (2, 1406, 30000.0), (1, 1200, 21250.0),
                                      (2, 1280, 30000.0), (4, 1440, 30000.0), (1, 1410, 12000.0)])
def test_parity_datagrams_never_exceed_quic_go_receive_limit(k, w, size):
    assert decide3.UDP_MAX == policy.QUICGO_MAX_IPS == 1452
    candidates = decide3.candidates3(k, w, size, C_PKT)
    assert candidates
    assert all(c["m"] == 0 or policy.parity_datagram_bytes(c["W_eff"], k) <= 1452
               for c in candidates)
    fits = policy.parity_datagram_bytes(w, k) <= 1452
    assert any(c["m"] > 0 for c in candidates) == fits


def test_parity_cap_removes_exactly_the_oversized_candidates():
    for k, w, size in ((1, 1200, 21250.0), (2, 1406, 2000.0), (1, 1410, 12000.0)):
        capped = {c["action"] for c in decide3.candidates3(k, w, size, C_PKT)}
        try:
            decide3.UDP_MAX = quantum.TYPICAL_MTU - 28
            wide = decide3.candidates3(k, w, size, C_PKT)
        finally:
            decide3.UDP_MAX = policy.QUICGO_MAX_IPS
        oversized = {c["action"] for c in wide
                     if c["m"] > 0 and policy.parity_datagram_bytes(c["W_eff"], k) > 1452}
        assert oversized
        assert capped == {c["action"] for c in wide} - oversized


def c1_state():
    state = learn3.new_state()
    state.k_hist, state.S_hist = [2], [server_bytes(9000, 2, 1280)]
    learn3.observe3(state, (0, 3, 1), 75.0, True, 2, server_bytes(9000, 2, 1280), 50.0, W=1280,
                    u_mbps=2.0, c_pkt=C_PKT,
                    arrivals={"src": "ack", "sent": 6, "lost": 1, "bitmap": None, "trunc": False})
    return state


def test_state_version_eleven_round_trips_and_rejects_older_states():
    for state in (learn3.new_state(), c1_state()):
        data = json.loads(json.dumps(state.to_json()))
        assert data["v"] == 11 and learn3.POLICY_VERSION == "v3.3.1-dev"
        assert learn3.DestState3.from_json(data).to_json() == data
        for version in range(1, 11):
            with pytest.raises(ValueError, match="version mismatch"):
                learn3.DestState3.from_json(dict(data, v=version))
    data = c1_state().to_json()
    assert (data["c1_seen"], data["arrival_streak"]) == (True, 1)


@pytest.mark.parametrize("change", [
    {"c1_seen": 1}, {"c1_seen": None}, {"c1_seen": "true"},
    {"arrival_streak": -1}, {"arrival_streak": True}, {"arrival_streak": 1.0},
    {"arrival_streak": learn3.ARRIVAL_STREAK_CAP + 1},
    {"c1_seen": False, "arrival_streak": 1},
    {"g_alarm": {"0,3,1": 0}},
])
def test_invalid_c1_markers_are_rejected(change):
    data = json.loads(json.dumps(c1_state().to_json()))
    data.update(change)
    with pytest.raises((TypeError, ValueError)):
        learn3.DestState3.from_json(data)


@pytest.mark.parametrize("field", ["c1_seen", "arrival_streak"])
def test_missing_c1_markers_are_rejected(field):
    data = c1_state().to_json()
    del data[field]
    with pytest.raises(KeyError):
        learn3.DestState3.from_json(data)


def test_decide_rejects_inconsistent_live_c1_markers():
    for c1_seen, streak, alarms in ((1, 0, {}), (False, 2, {}), (True, 9, {}),
                                    (True, 0, {"0,3,1": 0})):
        state = c1_state()
        state.c1_seen, state.arrival_streak, state.g_alarm = c1_seen, streak, alarms
        with pytest.raises(ValueError):
            decide3.decide3(state, 1280, 2.0, 50.0, C_PKT)
