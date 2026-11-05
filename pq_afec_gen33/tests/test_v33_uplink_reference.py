import math
from dataclasses import replace

import pytest

from experiments.v33.uplink_reference import (
    ModelReference, RACE_SCALES, RttObservation, UPLINK_SCENARIOS,
    estimate_uplink, normalize_uplink, race_interval, select_minimax,
)
from padfec import policy, quantum
from padfec3 import decide3, layout, learn3


def candidate(action):
    return decide3.explicit_candidates([action], 2, 1280)[0]


def samples(rate=2.0, count=8, same=False):
    result = []
    for i in range(count):
        prefix = 1280 if same or i % 2 == 0 else 2611
        rtt = 50.0 + (prefix * 0.008 / rate if rate else 0)
        result.append(RttObservation("host", prefix, rtt, True, True, True, True))
    return result


@pytest.mark.parametrize("value,expected", [(None, None), (-1, None), (0, 0), (2, 2), (0.5, 0.5)])
def test_uplink_semantics(value, expected):
    assert normalize_uplink(value) == expected


@pytest.mark.parametrize("value", [True, False, -2, math.inf, -math.inf, math.nan, "2"])
def test_uplink_invalid(value):
    with pytest.raises((TypeError, ValueError)):
        normalize_uplink(value)


def test_minimax_regret_uses_scenario_oracle_not_worst_cost():
    candidates = [candidate((0, 0, 0)), candidate((0, 1, 0)), candidate((0, 0, 1))]
    costs = [[101, 0], [100, 3], [102, 2]]
    result = select_minimax(candidates, costs)
    assert result["index"] == 0
    assert result["oracle_cost_ms"] == [100, 0]
    assert result["regret_ms"] == [1, 0]
    shifted = [[row[0] + 200, row[1] + 4] for row in costs]
    assert select_minimax(candidates, shifted)["index"] == 0


def test_minimax_exact_ties_use_sum_then_bytes_independent_of_order():
    candidates = [candidate((0, 0, 2)), candidate((0, 0, 1)), candidate((0, 0, 0))]
    costs = [[0, 2, 1], [2, 0, 0], [2, 0, 0]]
    assert select_minimax(candidates, costs)["candidate"]["action"] == (0, 0, 0)
    assert select_minimax(candidates[::-1], costs[::-1])["candidate"]["action"] == (0, 0, 0)


@pytest.mark.parametrize("costs", [[], [[]], [[1, 2], [1]], [[math.nan]], [[-1]], [[True]]])
def test_bad_matrix_rejected(costs):
    with pytest.raises((ValueError, TypeError)):
        select_minimax([candidate((0, 0, 0))], costs)


def test_duplicate_action_rejected():
    with pytest.raises(ValueError):
        select_minimax([candidate((0, 0, 0))] * 2, [[1], [2]])


@pytest.mark.parametrize("rate", UPLINK_SCENARIOS)
def test_nominal_reference_matches_original_layout_for_every_candidate(rate):
    distribution = [(0.02, 0.25), (0.15, 0.75)]
    table = ModelReference().cost_matrix(distribution, 2, 1280, 18231, 50, 41.983,
                                        uplink_mbps=rate)
    for c, row in zip(table["candidates"], table["cost_ms"]):
        expected = sum(weight * layout.evaluate(2, c["W_eff"], c["m"], c["lead"],
                       p, 50, rate, table["n_need"])["J"] for p, weight in distribution)
        assert row == [expected]


def test_race_models_are_isolated_from_global_policy_and_cache():
    q_before = policy.race_win_prob
    cached_before = dict(learn3._MODEL)
    reference = ModelReference()
    rows = reference.cost_matrix([(0.02, 1)], 2, 1280, 10992, 50, 41.983,
                                 uplink_mbps=20, race_scales=RACE_SCALES,
                                 actions=[(0, 0, 4)])["cost_ms"]
    assert len(set(rows[0])) == 3
    assert policy.race_win_prob is q_before
    assert dict(learn3._MODEL) == cached_before
    for scale in RACE_SCALES:
        assert reference._model(scale).policy.race_win_prob(0.71) == q_before(0.71 / scale)


def test_race_interval_contains_nominal_and_respects_endpoint_jump():
    for delay in [0, 0.133, 0.71, 1.0648, 1.066, 2.132, 10]:
        lo, hi = race_interval(delay)
        assert 0 <= lo <= policy.race_win_prob(delay) <= hi <= 1
    assert policy.race_win_prob(1.0648) > 0
    assert policy.race_win_prob(1.066) == 0


def test_unknown_rate_crosses_all_coherent_race_scenarios():
    table = ModelReference().cost_matrix([(0.02, 1)], 2, 1280, 18231, 50, 41.983,
                                        race_scales=RACE_SCALES, actions=[(0, 0, 0)])
    assert table["scenarios"] == [{"uplink_mbps": u, "race_scale": s}
                                  for u in UPLINK_SCENARIOS for s in RACE_SCALES]
    assert len(table["cost_ms"][0]) == 18


@pytest.mark.parametrize("options", [
    {"race_scales": []}, {"race_scales": [1, 1]}, {"race_scales": [0]},
    {"actions": []}, {"actions": [(200, 0, 0)]}, {"actions": [(0, 0, 0)] * 2},
    {"uplink_mbps": -2},
])
def test_model_options_rejected(options):
    with pytest.raises((TypeError, ValueError)):
        ModelReference().cost_matrix([(0.02, 1)], 2, 1280, 18231, 50, 41.983, **options)


@pytest.mark.parametrize("rate", [2, 5, 10, 20, 50])
def test_estimator_first_possible_convergence_without_true_rtt(rate):
    values = samples(rate)
    for n in range(8):
        assert estimate_uplink(values[:n], "host")["uplink_mbps"] is None
    result = estimate_uplink(values, "host")
    assert result["status"] == "estimated"
    assert result["uplink_mbps"] == pytest.approx(rate)
    shifted = [replace(x, min_rtt_ms=x.min_rtt_ms + 123) for x in values]
    assert estimate_uplink(shifted, "host")["uplink_mbps"] == pytest.approx(rate)


@pytest.mark.parametrize("field", ["full_sent", "loss_free", "retransmission_free", "path_stable"])
def test_missing_evidence_prevents_estimate(field):
    values = [replace(x, **{field: False}) for x in samples()]
    result = estimate_uplink(values, "host")
    assert result["qualified_samples"] == 0
    assert result["uplink_mbps"] is None


def test_estimator_default_flags_do_not_assert_observability():
    values = [RttObservation(x.destination, x.prefix_bytes, x.min_rtt_ms) for x in samples()]
    assert estimate_uplink(values, "host")["qualified_samples"] == 0


def test_estimator_destination_window_and_lost_identifiability():
    values = samples()
    assert estimate_uplink(values, "another")["window_samples"] == 0
    values += [replace(x, destination="another") for x in samples(count=80)]
    assert estimate_uplink(values, "host")["uplink_mbps"] == pytest.approx(2)
    values += samples(count=64, same=True)
    result = estimate_uplink(values, "host")
    assert result["window_samples"] == 64
    assert result["reason"] == "insufficient_byte_diversity"
    assert result["uplink_mbps"] is None


def test_unqualified_recent_window_does_not_revive_old_samples():
    values = samples() + [replace(x, loss_free=False) for x in samples(count=64)]
    assert estimate_uplink(values, "host")["qualified_samples"] == 0


@pytest.mark.parametrize("rate", [0, -2])
def test_nonpositive_slope_stays_unknown(rate):
    assert estimate_uplink(samples(rate), "host")["uplink_mbps"] is None


def test_small_byte_span_and_rare_groups_are_not_identifiable():
    values = [replace(x, prefix_bytes=1281 if x.prefix_bytes == 2611 else 1280) for x in samples()]
    assert estimate_uplink(values, "host")["reason"] == "insufficient_byte_span"
    assert estimate_uplink(samples(count=7) + samples(count=1), "host")["reason"] == "insufficient_byte_diversity"


def test_confounded_rtt_can_produce_wrong_rate_despite_input_flags():
    values = [replace(x, min_rtt_ms=x.min_rtt_ms + x.prefix_bytes * 0.004)
              for x in samples(2)]
    assert estimate_uplink(values, "host")["uplink_mbps"] == pytest.approx(1)


@pytest.mark.parametrize("change", [{"prefix_bytes": True}, {"prefix_bytes": -1},
    {"min_rtt_ms": math.nan}, {"min_rtt_ms": 0}, {"full_sent": 1}, {"destination": ""}])
def test_estimator_invalid_observation_rejected(change):
    with pytest.raises((TypeError, ValueError)):
        estimate_uplink([replace(samples()[0], **change)], "host")
