import copy
import json
import math

import pytest

from padfec import policy, quantum
from padfec3 import decide3, layout, learn3, preflight


def observation(sizes, first=True, source="world_arrival_proxy"):
    return {"source": source, "small_initial_sizes": sizes,
            "first_large_seen": first, "srv_bytes_scope": "includes_observed_preflight"}


def feed(st, sizes, raw=7951, k=2, u=10, first=True, ok=True):
    return learn3.observe3(st, (0, 0, 0), 100 if ok else None, ok, k, raw, 100,
                          W=1280, u_mbps=u, c_pkt=policy.C_PKT_POLICY_DEFAULT,
                          preflight_observation=observation(sizes, first))


@pytest.mark.parametrize("margin,need,delta", [(0, 2574, 7), (20, 2581, 11), (30, 2584, 12), (40, 2588, 14)])
def test_c6000_integer_boundary(margin, need, delta):
    assert quantum.required_credit(7680, 41, margin) == need
    assert quantum.delta_min(2560, a_pre=41, margin=margin) == need - 2560
    values = decide3.candidates3(2, 1280, 7910, policy.C_PKT_POLICY_DEFAULT,
                                a_pre=41, margin=margin)
    assert (delta, 0, 0) in [value["action"] for value in values]
    assert 3 * (2560 + 2 * delta) - 41 > 7680
    assert 2560 + 2 * (delta - 1) < need
    if margin:
        for actual in range(28, 55):
            assert layout.one_rtt_ok(2560 + 2 * delta, 7, actual)
    else:
        assert not layout.one_rtt_ok(2560 + 12, 7, 41)
        assert not layout.one_rtt_ok(2560 + 14, 7, 54)


def test_integer_credit_sweep_and_distinct_margin_rounding():
    for prefix in list(range(0, 80)) + [7680, 10 ** 30 + 7]:
        for a_pre in (0, 1, 41, 54, 123):
            exact = quantum.required_credit(prefix, a_pre)
            assert 3 * (exact - 1) <= prefix + a_pre < 3 * exact
            for margin in (0, 1, 2, 3, 20, 30, 40):
                value = quantum.required_credit(prefix, a_pre, margin)
                assert value - exact == (margin + 2) // 3
                assert 3 * value > prefix + a_pre + margin
    assert quantum.required_credit(1, 0, 1) == 2
    assert (1 + 0 + 1) // 3 + 1 == 1


def test_shared_legacy_delta_and_combo_exact_zero_defaults():
    for base in (-2, 0, 1, 1200, 2560, 10 ** 30):
        for steps in (-1, 0, 1, 2, 8):
            expected = 0 if steps <= 0 else (((3 * max(0, base) + 1279) // 1280 + steps - 1) * 1280 - 3 * max(0, base)) // 3 + 1
            assert quantum.delta_min(base, steps) == expected
            assert quantum.delta_min(base, steps, a_pre=0, margin=0) == expected
    for k in range(1, 5):
        for m in range(5):
            for n in (1, 4, 7, 12):
                for limit in (None, 0, 7, 172):
                    assert quantum._combo_deltas(k, m, 1280, 39 + 6 * k, n, max_delta=limit) == quantum._combo_deltas(k, m, 1280, 39 + 6 * k, n, max_delta=limit, a_pre=0, margin=0)


def test_partial_arrival_boundaries_independent_enumeration():
    for k in range(1, 5):
        for m in range(5):
            for prefix in (1280, 5000, 7680, 10003, 14080):
                for a_pre, margin in ((0, 0), (41, 0), (54, 30)):
                    need = (prefix + a_pre) // 3 + 1 + (margin + 2) // 3
                    expected = set()
                    for a in range(k + 1):
                        for b in range(m + 1):
                            g = 0 if m == 0 else 1 if m == 1 else m - 1
                            if a + b == 0 or k - a > min(b, g):
                                continue
                            credit = lambda delta: (a + b) * (1280 + delta) + (a + b - k) * (39 + 6 * k)
                            match = next((d for d in range(173) if credit(d) >= need), None)
                            if match not in (None, 0):
                                expected.add(match)
                                assert credit(match - 1) < need <= credit(match)
                    actual = quantum._combo_deltas(k, m, 1280, 39 + 6 * k, 7, max_delta=172,
                                                    a_pre=a_pre, margin=margin, prefix=prefix)
                    assert actual == sorted(expected)


@pytest.mark.parametrize("bad", [True, -1, 1.2, "41", None])
def test_bad_integer_budget_inputs(bad):
    for key in ("a_pre", "margin", "prefix"):
        args = {"prefix": 7680, "a_pre": 41, "margin": 30, key: bad}
        with pytest.raises((ValueError, TypeError)):
            quantum.required_credit(**args)


def test_cache_and_class_probabilities_use_physical_budget_not_margin():
    learn3.clear_model_cache()
    args = (2, 1287, 10, 100, 7, 0, 0, 0)
    first = learn3.model_point(*args, a_pre=41)
    second = learn3.model_point(*args, a_pre=54)
    third = learn3.model_point(*args, a_pre=0, prefix=7721)
    fourth = learn3.model_point(*args, a_pre=41, prefix=7681)
    assert first[2] == 0 and second[2] == 1 and fourth[2] == 1
    assert first == third
    assert learn3.model_cache_size() == 4
    ctx = {"k": 2, "W": 1280, "u": 10, "rtt": 100, "n_need": 7, "a_pre": 54, "prefix": 7680}
    assert learn3.class_probabilities(ctx, (7, 0, 0), 0) == [0.0, 1.0, 0.0]
    ctx["a_pre"] = 41
    assert learn3.class_probabilities(ctx, (7, 0, 0), 0) == [1.0, 0.0, 0.0]


def test_observation_sum_scope_causality_and_median_rounding():
    st = learn3.new_state()
    st.k_hist = [2]
    st.S_hist = [9000]
    first = feed(st, [20, 21])
    assert first["ctx"]["a_pre"] == 41
    assert first["ctx"]["S"] == 9000
    assert st.S_hist == [7910.0]
    assert first["preflight_observed_bytes"] == 41
    assert learn3.preflight_context(st, 2, 10)["a_pre_source"] == "received_initial_median"
    second = feed(st, [42], raw=7952)
    assert second["ctx"]["a_pre"] == 41
    assert learn3.preflight_context(st, 2, 10) == {"a_pre": 42, "a_pre_median": 41.5, "a_pre_n": 2, "a_pre_source": "received_initial_median"}
    decision = decide3.decide3(st, 1280, 10, 100, policy.C_PKT_POLICY_DEFAULT, keep_cands=True)
    assert decision["a_pre"] == 42 and decision["margin_server_bytes"] == 30
    assert decision["S_scope"] == "response_excludes_observed_preflight"
    assert decision["prefix"] == 7680
    for candidate in decision["cands"]:
        assert candidate["client_bytes"] == 2 * candidate["W_eff"] + candidate["m"] * policy.parity_datagram_bytes(candidate["W_eff"], 2)
        assert candidate["W_eff"] <= decide3.MAX_IPS
        if candidate["m"]:
            assert policy.parity_datagram_bytes(candidate["W_eff"], 2) <= decide3.UDP_MAX


def test_missing_zero_context_and_history_caps():
    st = learn3.new_state()
    feed(st, [])
    feed(st, [41], first=False)
    assert st.apre_hist == []
    assert learn3.preflight_context(st, 2, 10)["a_pre"] == 41
    assert learn3.preflight_context(st, 2, 0)["a_pre"] == 0
    for value in range(1, 81):
        feed(st, [value], raw=7910 + value)
    assert len(st.apre_hist) == 64
    assert learn3.preflight_context(st, 2, 10)["a_pre"] == 73
    assert learn3.preflight_context(st, 2, 10)["a_pre_n"] == 16
    assert learn3.preflight_context(st, 3, 10)["a_pre"] == 82
    assert learn3.preflight_context(st, 2, 2)["a_pre_source"] == "legacy_estimate"
    before = len(st.apre_hist)
    feed(st, [90], ok=False)
    assert len(st.apre_hist) == before and st.apre_hist[-1]["bytes"] == 90


def test_state_roundtrip_rejects_old_and_invalid_history():
    st = learn3.new_state()
    feed(st, [41])
    value = json.loads(json.dumps(st.to_json()))
    assert learn3.DestState3.from_json(value).to_json() == value
    for version in (1, 2, 3, 4, 5, 6, 7, True):
        bad = {**value, "v": version}
        with pytest.raises((ValueError, TypeError)):
            learn3.DestState3.from_json(bad)
    for key, bad_value in (("k", True), ("k", 0), ("u", -1), ("u", math.inf), ("bytes", 0), ("source", "server_sent")):
        bad = copy.deepcopy(value)
        bad["apre_hist"][0][key] = bad_value
        with pytest.raises((ValueError, TypeError)):
            learn3.DestState3.from_json(bad)


def test_invalid_observations_preserve_all_state():
    st = learn3.new_state()
    feed(st, [41])
    cases = [observation([True]), observation([-1]), observation([1200]), observation([1.5]),
             observation([41], first=1), observation([41], source="server_sent"), observation([1] * 65),
             {**observation([41]), "srv_bytes_scope": "excludes_preflight"}, {**observation([41]), "extra": 1}]
    for value in cases:
        before = st.to_json()
        with pytest.raises((ValueError, TypeError)):
            learn3.observe3(st, (0, 0, 0), 100, True, 2, 7951, 100, W=1280,
                            u_mbps=10, c_pkt=policy.C_PKT_POLICY_DEFAULT, preflight_observation=value)
        assert st.to_json() == before
    with pytest.raises(ValueError):
        preflight.normalize(observation([41]), 40)


def test_equivalent_ack_scope_and_double_count_counterexample():
    for prefix in range(7600, 7750):
        for credit in range(2540, 2600):
            assert layout.one_rtt_ok(credit, 7, 41, prefix=prefix) == layout.one_rtt_ok(credit, 7, 0, prefix=prefix + 41)
    assert layout.one_rtt_ok(2574, 7, 41, prefix=7680)
    assert not layout.one_rtt_ok(2574, 7, 41, prefix=7721)
