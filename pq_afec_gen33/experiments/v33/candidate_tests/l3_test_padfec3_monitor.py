from copy import deepcopy
import importlib.util
import math
from pathlib import Path
from unittest import mock

import pytest

from padfec import policy
from padfec3 import decide3, layout, learn3, monitor3


C_PKT = policy.C_PKT_POLICY_DEFAULT
ACTION = (0, 3, 1)
KEY = learn3.arm_key(ACTION)
EVIDENCE = {"src": "c1", "sent": 6, "lost": 1, "bitmap": None, "trunc": False}


def warm():
    state = learn3.new_state()
    state.k_hist = [2]
    state.S_hist = [18232.0]
    return state


def decide(state, **kwargs):
    return decide3.decide3(state, 1280, 2.0, 50.0, C_PKT, actions=[ACTION], **kwargs)


def observe(state, *, arrivals=EVIDENCE, hct=130.0, ok=True, rtt=50.0, action=ACTION):
    return learn3.observe3(state, action, hct, ok, 2, 18232, rtt, W=1280, u_mbps=2.0, c_pkt=C_PKT, arrivals=arrivals)


@pytest.mark.parametrize("q", [0.0, 1e-12, .03, .42, 1.0])
@pytest.mark.parametrize("z", [0, 1])
@pytest.mark.parametrize("ratio", [.5, 2.0])
def test_increment_is_log_likelihood_ratio(q, z, ratio):
    probability = min(1 - 1e-6, max(1e-6, q))
    alternative = probability * ratio / (1 - probability + probability * ratio)
    expected = math.log(alternative / probability) if z else math.log((1 - alternative) / (1 - probability))
    assert monitor3.increment(z, q, ratio) == pytest.approx(expected, abs=2e-10)


def test_alarm_at_threshold_resets_both_statistics_once():
    delta = monitor3.increment(1, .03, 2.0)
    up, down, direction = monitor3.step(5 - delta, 1.0, 1, .03)
    assert (up, down, direction) == (0.0, 0.0, 1)
    assert monitor3.step(5 - delta - 1e-10, 1.0, 1, .03)[2] == 0
    down_delta = monitor3.increment(0, .9, .5)
    assert monitor3.step(1.0, 5 - down_delta, 0, .9)[2] == -1


def test_regularized_logistic_fit_has_correct_direction_and_bounded_score_root():
    assert monitor3.fit_beta([[.5, 0], [.5, 1]]) == 0.0
    values = [[.2, int(i % 2 == 0)] for i in range(32)]
    beta = monitor3.fit_beta(values)
    assert 0 < beta < monitor3.BETA_MAX
    score = sum(z - monitor3.shifted(q, beta) for q, z in values) - monitor3.RIDGE * beta
    assert abs(score) < 1e-10
    assert monitor3.fit_beta([[.001, 1]] * 32) == monitor3.BETA_MAX
    assert monitor3.fit_beta([[.999, 0]] * 32) == -monitor3.BETA_MAX


def test_only_current_action_moves_and_shared_requires_two_fresh_eligible_alarms():
    state = monitor3.new_state()
    state["arms"]["a"] = monitor3.new_arm()
    state["arms"]["b"] = monitor3.new_arm()
    state["arms"]["a"].update(up=4.9, last_seen=1)
    state["arms"]["b"].update(up=4.9, last_seen=1)
    before = deepcopy(state["arms"]["b"])
    first = monitor3.observe(state, "a", .03, .03, 1, 2, True)
    assert first["direction"] == 1 and not first["shared"]
    assert state["arms"]["b"] == before
    second = monitor3.observe(state, "b", .03, .03, 1, 3, True)
    assert second["shared"] and second["shared_actions"] == ["a", "b"]
    assert all(row["beta"] == 0.0 for row in state["arms"].values())
    assert state["shared_count"] == 1
    state["arms"]["a"]["up"] = 4.9
    assert not monitor3.observe(state, "a", .03, .03, 1, 4, True)["shared"]


@pytest.mark.parametrize("case", ["single", "stale", "unready", "opposite"])
def test_shared_change_cannot_be_inferred_from_one_or_stale_or_unready_action(case):
    state = monitor3.new_state()
    state["arms"]["a"] = monitor3.new_arm()
    state["arms"]["a"]["up"] = 4.9
    if case != "single":
        other = monitor3.new_arm()
        other.update(alarm_at=1, last_seen=1, alarm_dir=-1 if case == "opposite" else 1,
                     reactive_alarm=case != "unready")
        state["arms"]["b"] = other
    at = 40 if case == "stale" else 2
    result = monitor3.observe(state, "a", .03, .03, 1, at, True)
    assert not result["shared"] and state["shared_count"] == 0


def test_hazard_boost_preserves_within_group_ratios_and_cap():
    weights = [.1, .2, .3, .25, .15]
    boosted = monitor3.boost_fast(weights)
    assert sum(boosted) == pytest.approx(1.0)
    assert sum(boosted[:2]) == pytest.approx(.6 / 1.3)
    assert boosted[0] / boosted[1] == pytest.approx(.5)
    assert boosted[2] / boosted[3] == pytest.approx(1.2)
    assert monitor3.boost_fast([.5, .4, .1]) == [.5, .4, .1]


@pytest.mark.parametrize("beta,z", [(0.5, 0), (-0.5, 1)])
def test_recovery_uses_its_own_direction_zero_and_cannot_reverse_sign(beta, z):
    state = monitor3.new_state()
    state["arms"]["a"] = monitor3.new_arm()
    state["arms"]["a"]["beta"] = beta
    result = monitor3.observe(state, "a", .5, monitor3.shifted(.5, beta), z, 1, True)
    assert result["direction"] == 0
    assert result["action"] == "recovery" and result["beta_after"] == 0.0
    assert max(result["up"], result["down"]) > 0.0


@pytest.mark.parametrize("p", [0.0, .02, .15, .25])
@pytest.mark.parametrize("action", [(0, 3, 1), (0, 0, 4), (0, 0, 0)])
def test_cost_components_preserve_original_layout_arithmetic(p, action):
    root = Path(__file__).resolve().parents[3]
    source = root / "g3/v33/policy_snapshots/L2_v1/padfec3/layout.py"
    spec = importlib.util.spec_from_file_location("old_layout_monitor_test", source)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    d, lead, trailing = action
    arguments = (2, 1280 + d, lead + trailing, lead, p, 50, 2.0, 15)
    actual = layout.evaluate(*arguments)
    before = old.evaluate(*arguments)
    assert all(actual[key] == value for key, value in before.items())
    assert sum(actual["class_cost_contributions_ms"]) == pytest.approx(actual["J"], abs=1e-10)
    assert all(value >= 0 for value in actual["class_cost_contributions_ms"])


def test_calibration_reweights_class_costs_instead_of_adding_ms():
    state = warm()
    ctx = learn3.context(state, 1280, 2, 50, C_PKT)
    post = [0.0] * len(learn3.G)
    index = min(range(len(learn3.G)), key=lambda i: abs(learn3.G[i] - .15))
    post[index] = 1.0
    ev = layout.evaluate(2, 1280, 4, 3, learn3.G[index], 50, 2, ctx["n_need"])
    probabilities = [ev[key] for key in ("p_one_rtt", "p_two_rtt", "p_fail")]
    for beta in [-monitor3.BETA_MAX, 0.0, monitor3.BETA_MAX]:
        actual = learn3.calibrated_cost(ctx, ACTION, post, beta, ev["J"])
        q = learn3.monitor_probabilities(probabilities, beta)
        assert sum(q) == pytest.approx(1.0)
        assert q[1] / q[2] == pytest.approx(probabilities[1] / probabilities[2])
        expected = sum(part * new / old for part, new, old in zip(ev["class_cost_contributions_ms"], q, probabilities) if old > 0)
        assert actual == pytest.approx(expected)
        if beta == 0:
            assert actual == ev["J"]


def test_snapshot_is_before_observation_and_loss_uses_unchanged_l1_context():
    state = warm()
    prediction = decide(state)["monitor_prediction"]
    left, right = deepcopy(state), deepcopy(state)
    info_left = observe(left, arrivals={**EVIDENCE, "lost": 0}, hct=100, rtt=20)
    info_right = observe(right, arrivals={**EVIDENCE, "lost": 6}, hct=100, rtt=20)
    assert info_left["monitor_prediction"] == info_right["monitor_prediction"] == prediction
    assert info_left["monitor"]["q_raw"] == info_right["monitor"]["q_raw"]
    assert left.post != right.post
    assert info_left["cutoff_rtt_ms"] == 20 and prediction["ctx"]["rtt"] == 50
    assert info_left["grade"] != info_left["monitor_grade"]
    assert left.monitor_pending is None
    repeated = observe(left)
    assert repeated["monitor_reason"] == "missing_snapshot"
    assert left.monitor["arms"][KEY]["n"] == 1


def test_failure_without_hct_is_monitored_and_arrival_learning_continues():
    state = warm()
    state.arrival_streak = 8
    decide(state)
    before = deepcopy(state)
    info = observe(state, hct=None, ok=False)
    expected_post, expected_weights, _ = learn3.filter_step(before.post, before.w, learn3.arrival_likelihood(6, 1))
    assert info["monitor_grade"] == 2 and info["monitor"]["z"] == 1
    assert state.post == expected_post and state.w == expected_weights
    assert info["updated"] and state.stats["predict"] == 1


def test_snapshot_roundtrip_and_old_versions_rejected():
    state = warm()
    decide(state)
    restored = learn3.DestState3.from_json(state.to_json())
    assert observe(state) == observe(restored)
    assert state.to_json() == restored.to_json()
    for version in range(1, 6):
        value = state.to_json()
        value["v"] = version
        with pytest.raises(ValueError, match="version"):
            learn3.DestState3.from_json(value)


@pytest.mark.parametrize("field,value", [("q_used", [.5, .5, 0]), ("cutoffs", [1, 2]), ("ready", 1), ("beta", math.inf)])
def test_malformed_snapshot_observation_is_atomic(field, value):
    state = warm()
    decide(state)
    state.monitor_pending[field] = value
    before = deepcopy(state.__dict__)
    with pytest.raises((TypeError, ValueError)):
        observe(state)
    assert state.__dict__ == before


@pytest.mark.parametrize("kind", ["action", "transport", "stale"])
def test_valid_but_unmatched_snapshot_is_skipped_without_blocking_loss(kind):
    state = warm()
    decide(state)
    if kind == "action":
        result = observe(state, action=(0, 0, 4))
    elif kind == "transport":
        result = learn3.observe3(state, ACTION, 130, True, 2, 18232, 50, W=1280, u_mbps=5, c_pkt=C_PKT, arrivals=EVIDENCE)
    else:
        state.n_dec += 1
        result = observe(state)
    assert result["updated"] and result["monitor"] is None and result["monitor_reason"].endswith("mismatch" if kind != "stale" else "snapshot")


def test_reactions_require_previous_and_current_complete_feedback():
    for previous, current, wanted in [(0, EVIDENCE, False), (8, None, False), (8, EVIDENCE, True)]:
        state = warm()
        state.arrival_streak = previous
        row = monitor3.new_arm()
        row["up"] = 4.9
        state.monitor["arms"][KEY] = row
        decide(state)
        result = observe(state, arrivals=current, hct=300)
        assert result["monitor"]["reactive"] == wanted
        if not wanted:
            assert state.monitor["arms"][KEY]["beta"] == 0


def test_feedback_readiness_is_from_previous_observations_and_resets_on_missing():
    state = warm()
    for index in range(9):
        result = decide(state)
        assert result["monitor_prediction"]["ready"] == (index >= 8)
        assert result["reeval_feedback_suppressed"] == (index > 0)
        observe(state)
    decide(state)
    observe(state, arrivals=None)
    assert state.arrival_streak == 0
    assert not decide(state)["reeval_feedback_suppressed"]


@pytest.mark.parametrize("baseline", [False, True])
def test_legacy_penalty_cannot_change_decision_and_no_residual_alarm_is_raised(baseline):
    state = warm()
    state.g_common = [0.] * 64
    state.g_resid[KEY] = [100.] * 32
    state.g_alarm[KEY] = 0
    if baseline:
        state.hct[KEY] = [80.] * 8
    result = decide(state)
    assert result["pen"] == 0.0 and result["score"] == result["ej"]
    before = deepcopy(state.g_common)
    info = learn3.observe3(state, ACTION, 130, True, 2, 18232, 50, W=1280, u_mbps=2, c_pkt=C_PKT, j_pred=1, arrivals=EVIDENCE)
    assert state.g_common == (before + [129.0])[-64:]
    assert ("guard" if baseline else "no_base") == info["legacy_skip_reason"]
    assert info["skip"] is None and result["pen"] == 0.0
    assert info["updated"]


def test_forged_readiness_is_not_used_for_reaction():
    state = warm()
    decide(state)
    state.monitor_pending["ready"] = True
    result = observe(state)
    assert result["monitor_reason"] == "readiness_mismatch"
    assert result["monitor"] is None and result["updated"]


@pytest.mark.parametrize("field,value", [("up", 5.0), ("down", -1), ("beta", math.nan), ("n", True), ("last_seen", 100)])
def test_malformed_monitor_state_is_rejected_without_mutation(field, value):
    state = warm()
    decide(state)
    observe(state)
    data = state.to_json()
    data["monitor"]["arms"][KEY][field] = value
    with pytest.raises((ValueError, TypeError)):
        learn3.DestState3.from_json(data)
