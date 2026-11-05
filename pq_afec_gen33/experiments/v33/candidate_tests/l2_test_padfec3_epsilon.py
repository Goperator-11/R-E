from copy import deepcopy
from fractions import Fraction
import json
import math
from unittest import mock

import pytest

from padfec import policy, quantum
from padfec3 import decide3, learn3


C_PKT = policy.C_PKT_POLICY_DEFAULT
ACTION = (0, 3, 1)


def warm():
    state = learn3.new_state()
    state.k_hist = [2]
    state.S_hist = [18232.0]
    return state


def decide(state, *, rtt=50.0, actions=(ACTION,)):
    return decide3.decide3(state, 1280, 2.0, rtt, C_PKT, actions=actions)


def observe(state, *, action=ACTION, hct=75.0, rtt=50.0, ok=True, arrivals=None, u=2.0):
    return learn3.observe3(state, action, hct, ok, 2, 18232.0, rtt,
                           W=1280, u_mbps=u, c_pkt=C_PKT, arrivals=arrivals)


def beta_moment(a, b, degree):
    result = Fraction(1)
    for i in range(degree):
        result *= (a + i) / (a + b + i)
    return result


@pytest.mark.parametrize("a,b", [(1, 999), (Fraction(1, 10), Fraction(9, 10)), (7, 3), (10000, 30000)])
@pytest.mark.parametrize("q", [Fraction(0), Fraction(1, 10**9), Fraction(1, 10), Fraction(1, 3), Fraction(2, 3), Fraction(999999999, 10**9), Fraction(1)])
def test_projection_matches_independent_polynomial_integrals(a, b, q):
    a, b = Fraction(a), Fraction(b)
    slope = (1 - 3 * q) / 2
    moments = [beta_moment(a, b, n) for n in range(4)]
    evidence = q + slope * moments[1]
    expected_mean = (q * moments[1] + slope * moments[2]) / evidence
    expected_second = (q * moments[2] + slope * moments[3]) / evidence
    new_a, new_b, _, _ = learn3.epsilon_posterior(float(a), float(b), float(q))
    total = new_a + new_b
    mean = new_a / total
    variance = (new_a / total) * (new_b / total) / (total + 1)
    assert mean == pytest.approx(float(expected_mean), rel=2e-12, abs=1e-15)
    assert variance == pytest.approx(float(expected_second - expected_mean**2), rel=2e-11, abs=1e-18)


def test_uninformative_and_conjugate_inputs_preserve_exact_parameters():
    assert learn3.epsilon_posterior(1, 999, 1 / 3)[:2] == (1, 999)
    assert learn3.epsilon_posterior(1, 999, 0)[:2] == (2, 999)
    assert learn3.epsilon_posterior(1, 999, 1)[:2] == (1, 1000)
    a, b, _, _ = learn3.epsilon_posterior(1, 999, 0.001)
    assert a + b < 1000


@pytest.mark.parametrize("a,b,q", [(0, 1, .1), (-1, 1, .1), (True, 2, .1),
                                  (1, math.inf, .1), (1e308, 1e308, .1),
                                  (1, 999, math.nan), (1, 999, -1e-9), (1, 999, 1.0001)])
def test_invalid_beta_and_probability_inputs_are_rejected(a, b, q):
    with pytest.raises((TypeError, ValueError)):
        learn3.epsilon_posterior(a, b, q)


def test_snapshot_uses_final_reevaluation_action_and_one_hazard_prediction():
    state = warm()
    state.S_hist = [16000.0 + policy.S0_BASE_MLKEM + quantum.bin_index(2560) * C_PKT]
    state.post = [[0.0] * (len(learn3.G) - 1) + [1.0] for _ in learn3.H]
    state.n_reeval = learn3.REEVAL_EVERY - 1
    before = deepcopy(state)
    decision = decide(state, actions=None)
    assert decision["reeval"] and decision["why"] == "reeval"
    snapshot = state.class_pending
    assert tuple(snapshot["action"]) == tuple(decision["action"])
    assert state.post == before.post and state.w == before.w
    ctx = snapshot["ctx"]
    expected = [0.0, 0.0, 0.0]
    for weight, hazard, row in zip(before.w, learn3.H, before.post):
        for g, mass in enumerate(row):
            prior = (1 - hazard) * mass + hazard / len(learn3.G)
            for z, q in enumerate(learn3.class_probabilities(ctx, decision["action"], g)):
                expected[z] += weight * prior * q
    assert snapshot["q"] == pytest.approx(expected, abs=1e-14)
    decision["class_prediction"]["q"][0] = -1
    assert state.class_pending["q"][0] >= 0


def test_current_rtt_cannot_relabel_a_predecision_grade():
    state = warm()
    decide(state, rtt=50)
    boundary = state.class_pending["cutoffs"][0]
    info = observe(state, hct=boundary, rtt=200)
    assert info["grade"] == 1
    assert info["cutoff_rtt_ms"] == 50
    assert info["cutoff_rtt_source"] == "decision_rtt_current_policy"
    assert info["epsilon_update_eligible"]
    assert state.class_pending is None


def test_current_loss_uses_old_epsilon_and_next_connection_uses_update():
    state = warm()
    decide(state)
    snapshot = deepcopy(state.class_pending)
    cut1, cut2 = snapshot["cutoffs"]
    before = deepcopy(state)
    old_epsilon = before.class_epsilon["a"] / (before.class_epsilon["a"] + before.class_epsilon["b"])
    likelihood = learn3.class_likelihood(snapshot["ctx"], ACTION, 2, epsilon=old_epsilon)
    expected_post, expected_weights, _ = learn3.filter_step(before.post, before.w, likelihood)
    with mock.patch.object(learn3, "filter_step", wraps=learn3.filter_step) as filtering:
        info = observe(state, hct=cut2 + 100)
    assert filtering.call_count == 1
    assert state.post == expected_post and state.w == expected_weights
    assert info["epsilon_before"] == .001
    assert info["epsilon_after"] != info["epsilon_before"]
    decide(state)
    second = observe(state, hct=cut1 / 2)
    assert second["epsilon_before"] == info["epsilon_after"]
    assert state.class_epsilon["updates"] == 2


def test_c1_posterior_is_independent_of_hct_grade_and_epsilon():
    first, second = warm(), warm()
    second.class_epsilon.update(a=25., b=75.)
    evidence = {"src": "c1", "sent": 6, "lost": 2, "bitmap": None, "trunc": False}
    for state in (first, second):
        decide(state)
    a = observe(first, hct=75, arrivals=evidence)
    b = observe(second, hct=None, ok=False, arrivals=evidence)
    assert first.post == second.post and first.w == second.w
    assert a["epsilon_update_eligible"] and b["epsilon_update_eligible"]
    assert a["grade"] != b["grade"]
    assert a["loss_update_kind"] == b["loss_update_kind"] == "datagram"
    assert first.class_epsilon != second.class_epsilon


@pytest.mark.parametrize("arrivals", [None,
    {"src": "c1", "sent": 6, "lost": 1, "bitmap": None, "trunc": False},
    {"src": "c1", "sent": 6, "lost": 1, "bitmap": [0, 1], "trunc": True}])
def test_epsilon_population_does_not_select_by_c1_availability(arrivals):
    state = warm()
    decide(state)
    info = observe(state, hct=None, ok=False, arrivals=arrivals)
    assert info["epsilon_update_eligible"]
    assert state.class_epsilon["updates"] == 1
    assert state.class_epsilon["skips"] == {}


@pytest.mark.parametrize("mode,reason", [("missing", "missing_snapshot"), ("stale", "stale_snapshot"),
                                       ("action", "action_mismatch"), ("transport", "transport_mismatch"),
                                       ("epsilon", "epsilon_mismatch")])
def test_unmatched_snapshot_skips_calibration_and_is_consumed(mode, reason):
    state = warm()
    decide(state)
    if mode == "missing":
        state.class_pending = None
    elif mode == "stale":
        state.n_dec += 1
    elif mode == "epsilon":
        state.class_epsilon["b"] += 1
    before = deepcopy(state.class_epsilon)
    info = observe(state, action=(0, 0, 0) if mode == "action" else ACTION,
                   u=0 if mode == "transport" else 2)
    assert not info["epsilon_update_eligible"]
    assert info["epsilon_update_reason"] == reason
    assert state.class_epsilon["a"] == before["a"] and state.class_epsilon["b"] == before["b"]
    assert state.class_epsilon["skips"] == {reason: 1}
    assert state.class_pending is None


def test_cold_decision_cannot_use_current_context_or_actual_world_truth():
    state = learn3.new_state()
    decision = decide(state)
    info = observe(state, action=tuple(decision["action"]))
    assert info["ctx"] is None and not info["epsilon_update_eligible"]
    assert info["epsilon_update_reason"] == "no_ctx"
    assert info["loss_update_kind"] == "predict_only"
    assert state.class_epsilon["a"] == 1 and state.class_epsilon["b"] == 999
    assert state.k_hist and state.S_hist


def test_pending_snapshot_roundtrip_and_destination_isolation():
    first, other = warm(), warm()
    decide(first)
    serialized = json.loads(json.dumps(first.to_json()))
    restored = learn3.DestState3.from_json(serialized)
    assert restored.to_json() == serialized
    assert observe(first) == observe(restored)
    assert first.to_json() == restored.to_json()
    assert other.class_epsilon == learn3.new_state().class_epsilon
    assert other.class_pending is None
    with pytest.raises(ValueError, match="version mismatch"):
        learn3.DestState3.from_json(dict(serialized, v=4))


@pytest.mark.parametrize("field,bad", [("a", 0), ("b", math.inf), ("q", [-.1, .5, .6]),
                                     ("q", [1.0000000001, 0, 0]), ("cutoffs", [1, 2]),
                                     ("dec_index", True), ("c_proc_ms", 4)])
def test_corrupt_snapshot_rejects_decision_observation_and_deserialization_atomically(field, bad):
    state = warm()
    decide(state)
    state.class_pending[field] = bad
    before = state.to_json()
    for operation in (lambda: observe(state), lambda: decide(state),
                      lambda: learn3.DestState3.from_json(before)):
        with pytest.raises((TypeError, ValueError)):
            operation()
        assert state.to_json() == before


def test_invalid_arrivals_do_not_consume_snapshot_or_update_beta():
    state = warm()
    decide(state)
    before = state.to_json()
    with pytest.raises(ValueError):
        observe(state, arrivals={"src": "c1"})
    assert state.to_json() == before
