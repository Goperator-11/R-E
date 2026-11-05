from copy import deepcopy
import json
import math
from unittest import mock

import pytest

from padfec import policy, quantum
from padfec3 import decide3, layout, learn3, server_size

C = policy.C_PKT_POLICY_DEFAULT


def evidence(sizes, *, complete=True, duplicates=0, other=41, post=0):
    return {"source": "world_receive_index_proxy", "complete": complete,
            "packets": [[i, size] for i, size in enumerate(sizes)],
            "received_server_bytes": sum(sizes) + duplicates + other + post,
            "duplicate_data_bytes": duplicates, "other_received_bytes": other,
            "post_complete_bytes": post}


def observe(state, value, *, ok=True, hct=75.0, action=(0, 3, 1), arrivals=None):
    return learn3.observe3(state, action, hct if ok else None, ok, 2, value["received_server_bytes"], 50.0,
                           W=1280, u_mbps=2.0, c_pkt=C, arrivals=arrivals, server_response=value)


def component(sizes, weight=1.0):
    sample = server_size.physical(sizes)
    return {"prefix": sample["prefix"], "S": sample["bytes"], "packet": sample["packet"], "n_need": sample["n_need"], "weight": weight}


def test_physical_rule_preserves_irregular_prefix_and_strict_boundary():
    for sizes in ([1280, 1280, 1209, 95], [1280, 1280, 1257, 95], [1100, 900, 600], [75]):
        sample = server_size.physical(sizes)
        assert sample["prefix"] == sum(sizes[:-1])
        for pre in (0, 1, 41, 54):
            threshold = (sum(sizes[:-1]) + pre) // 3 + 1
            for credit in (threshold - 1, threshold, threshold + 1):
                assert layout.one_rtt_ok(credit, sample["n_need"], pre, prefix=sample["prefix"]) == (3 * credit - pre > sum(sizes[:-1]))
            assert quantum.required_credit(sample["prefix"], pre) == threshold
    assert layout.one_rtt_ok(1280, 3, 0, prefix=3769)
    assert layout.one_rtt_ok(1280, 3, 0, prefix=3817)
    assert not layout.one_rtt_ok(1280, 4, 0, prefix=3840)


def test_effective_correction_requires_actual_inputs_and_keeps_scope():
    assert server_size.effective_bytes(14000, 11, 100, 6, 40) == 13700
    assert server_size.effective_bytes(14000, 11, 0, 6, 40) == 13800
    with pytest.raises(TypeError):
        server_size.effective_bytes(14000, 11, base_bin=6, c_pkt=40)
    for args in ((14000, 11, None, 6, 40), (14000, 11, 14000, 6, 40),
                 (100, 4096, 0, 0, 1279), (14000, True, 100, 6, 40),
                 (14000, 11, -1, 6, 40), (14000, 11, 100, 6, math.nan)):
        with pytest.raises((TypeError, ValueError)):
            server_size.effective_bytes(*args)


def test_new_chain_resets_window_and_known_mixture_preserves_both():
    history = server_size.new_history()
    small, big = server_size.physical([1280] * 8 + [600]), server_size.physical([1280] * 14 + [200])
    for _ in range(80):
        server_size.record(history, small)
    assert len(history["window"]) == 64
    result = server_size.record(history, big)
    assert result["size_reset"] and len(history["window"]) == 1
    assert server_size.distribution(history) == [component([1280] * 14 + [200])]
    for sample in (small, big) * 32:
        assert not server_size.record(history, sample)["size_reset"]
    assert server_size.distribution(history) == [component([1280] * 8 + [600], 0.5), component([1280] * 14 + [200], 0.5)]
    assert history["resets"] == 1
    assert server_size.validate_history(json.loads(json.dumps(history))) == history


def test_half_packet_boundary_and_catalog_eviction_are_deterministic():
    history = server_size.new_history()
    server_size.record(history, server_size.physical([1280, 100]))
    assert not server_size.record(history, server_size.physical([1280, 739]))["size_reset"]
    assert server_size.record(history, server_size.physical([1280, 740]))["size_reset"]
    for count in range(4, 15):
        server_size.record(history, server_size.physical([1280] * count))
    assert len(history["catalog"]) == 8
    assert len({row["id"] for row in history["catalog"]}) == 8
    assert server_size.validate_history(history) == history


def test_single_diagnostic_retains_window_and_chooses_actual_median_neighbor():
    history = server_size.new_history()
    for count in (3, 3, 5, 5):
        server_size.record(history, server_size.physical([1280] * count), mode="single")
    assert history["resets"] == 0 and len(history["window"]) == 4
    assert server_size.distribution(history, mode="single") == [component([1280] * 5)]


def test_all_completed_responses_ignore_legacy_event_selection():
    states = []
    for hct in (75, 175):
        state = learn3.new_state()
        state.k_hist, state.S_hist = [2], [4000]
        state.hct[learn3.arm_key((0, 3, 1))] = [75.0] * learn3.BASE_MIN
        result = observe(state, evidence([1280] * 8 + [600], duplicates=1280, post=1280), hct=hct)
        assert result["legacy_y"] == int(hct == 175)
        assert result["size_updated"]
        assert state.S_hist == [10840.0]
        states.append(state)
    assert states[0].size_history == states[1].size_history


def test_incomplete_and_missing_observation_do_not_mix_scopes():
    state = learn3.new_state()
    observe(state, evidence([1280, 900]))
    before = deepcopy(state.size_history)
    partial = evidence([1280], complete=False)
    result = observe(state, partial, ok=False)
    assert not result["size_updated"] and state.size_history == before
    learn3.observe3(state, (0, 3, 1), 75, True, 2, 99999, 50, W=1280, u_mbps=2, c_pkt=C)
    assert state.S_hist == [2180.0] and state.size_history == before


def test_same_data_with_ack_and_duplicate_differences_has_same_S():
    states = []
    for other, duplicate in ((0, 0), (41, 1280), (82, 2560)):
        state = learn3.new_state()
        observe(state, evidence([1280] * 10 + [1000], other=other, duplicates=duplicate))
        states.append(state)
    assert all(state.size_history == states[0].size_history for state in states)
    ctx = learn3.context(states[0], 1280, 2, 50, C)
    assert ctx["a_pre"] == 41 and ctx["n_need"] == 11
    assert ctx["size_distribution"][0]["prefix"] == 12800


def test_completed_size_conditions_loss_likelihood_after_decision():
    state = learn3.new_state()
    observe(state, evidence([1280] * 8 + [600]))
    before = deepcopy(state)
    decision = decide3.decide3(state, 1280, 2, 50, C)
    predicted = deepcopy(decision)
    observation = evidence([1280] * 14 + [200])
    with mock.patch.object(learn3, "class_likelihood", wraps=learn3.class_likelihood) as likelihood:
        result = observe(state, observation, action=decision["action"], hct=125)
    assert decision == predicted
    assert result["ctx"]["size_distribution"] == server_size.distribution(before.size_history)
    assert result["loss_context_source"] == "observed_complete_response"
    assert likelihood.call_args.args[0]["size_distribution"] == [component([1280] * 14 + [200])]
    assert result["size_reset"]
    assert learn3.context(state, 1280, 2, 50, C)["size_distribution"] == [component([1280] * 14 + [200])]


def test_mixture_cost_class_probabilities_and_candidate_union():
    components = [component([1280] * 5 + [300], 0.25), component([1280] * 13 + [500], 0.75)]
    post = [0.0] * len(learn3.G)
    post[5] = 1.0
    result = decide3.decide_core(post, 2, 1280, 10000, 2, 50, C, size_distribution=components, keep_cands=True)
    expected_actions = set()
    for part in components:
        expected_actions.update(c["action"] for c in decide3.candidates3(2, 1280, part["S"], C, a_pre=41, prefix=part["prefix"]))
    assert {row["action"] for row in result["cands"]} == expected_actions
    ctx = learn3.size_context({"k": 2, "W": 1280, "u": 2.0, "rtt": 50.0, "S": 10000, "n_need": 9}, components)
    for candidate in result["cands"]:
        delta, lead, trailing = candidate["action"]
        costs, probabilities = [], []
        for part in components:
            value = layout.evaluate(2, 1280 + delta, lead + trailing, lead, learn3.G[5], 50, 2, part["n_need"], a_pre=41, prefix=part["prefix"])
            costs.append(value["J"])
            probabilities.append((value["p_one_rtt"], value["p_two_rtt"], value["p_fail"]))
        assert candidate["ej"] == 0.25 * costs[0] + 0.75 * costs[1]
        assert learn3.class_probabilities(ctx, candidate["action"], 5) == pytest.approx([0.25 * a + 0.75 * b for a, b in zip(*probabilities)])
    independent = min(row["ej"] for row in result["cands"])
    assert result["ej"] <= independent + decide3.J_TIE


def test_single_component_preserves_exact_model_arithmetic_and_cache_scope():
    part = component([1100, 900, 600])
    ctx = learn3.size_context({"k": 2, "W": 1280, "u": 2.0, "rtt": 50.0, "S": 2600, "n_need": 3}, [part])
    action = (0, 0, 0)
    expected = learn3.model_point(2, 1280, 2, 50, part["n_need"], 0, 0, 5, a_pre=41, prefix=2000)
    assert learn3.context_model_result(ctx, action, 5)[0] == expected
    learn3.clear_model_cache()
    low = learn3.model_point(2, 1280, 2, 50, 7, 0, 0, 0, a_pre=41, prefix=7638)
    high = learn3.model_point(2, 1280, 2, 50, 7, 0, 0, 0, a_pre=41, prefix=7639)
    assert high[0] > low[0] and learn3.model_cache_size() == 2


def test_state_nine_roundtrip_rejects_all_older_versions_and_bad_history():
    state = learn3.new_state()
    observe(state, evidence([1280] * 8 + [600]))
    observe(state, evidence([1280] * 14 + [200]))
    observe(state, evidence([1280] * 8 + [600]))
    encoded = json.loads(json.dumps(state.to_json()))
    restored = learn3.DestState3.from_json(encoded)
    assert encoded["v"] == 9 and restored.to_json() == encoded
    assert decide3.decide3(state, 1280, 2, 50, C) == decide3.decide3(restored, 1280, 2, 50, C)
    for version in range(1, 9):
        with pytest.raises(ValueError):
            learn3.DestState3.from_json({**encoded, "v": version})
    for field, value in (("S_scope", "legacy_unclassified"), ("S_hist", [1]), ("size_history", {})):
        with pytest.raises(ValueError):
            learn3.DestState3.from_json({**encoded, field: value})


@pytest.mark.parametrize("mutation", ["source", "count", "index", "size", "scope", "extra", "complete", "oversize"])
def test_bad_response_is_transactionally_rejected(mutation):
    state = learn3.new_state()
    observe(state, evidence([1280, 900]))
    before = state.to_json()
    value = evidence([1280, 900])
    if mutation == "source":
        value["source"] = "server_sent"
    elif mutation == "count":
        value["duplicate_data_bytes"] += 1
    elif mutation == "index":
        value["packets"][1][0] = 2
    elif mutation == "size":
        value["packets"][0][1] = True
    elif mutation == "scope":
        value["other_received_bytes"] = -1
    elif mutation == "extra":
        value["rxRetx"] = 2
    elif mutation == "complete":
        value["complete"] = 1
    else:
        value["packets"][0][1] = 2 ** 53
    with pytest.raises((TypeError, ValueError)):
        observe(state, value)
    assert state.to_json() == before
