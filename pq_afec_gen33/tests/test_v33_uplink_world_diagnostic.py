import copy

import pytest

from experiments.v33 import uplink_world_diagnostic as diagnostic


def test_plan_keeps_frozen_seeds_schedules_world_and_rates():
    plan = diagnostic.make_plan()
    diagnostic.validate_plan(plan)
    assert plan["seeds"] == list(range(31, 51))
    assert list(plan["true_u_mbps"]) == [0, 2, 5, 10, 20, 50]
    assert [x["id"] for x in plan["scenarios"]] == ["B1", "B2", "B11", "B12_c6000", "B12_c12000"]
    assert sum(sum(p["length"] for p in s["phases"]) for s in plan["scenarios"]) * 20 * 6 == 810000


@pytest.mark.parametrize("field,value", [("seeds", [31]), ("threshold_ms", 6.51),
    ("family_size", 1), ("true_u_mbps", [2]), ("source_sha256", {})])
def test_plan_rejects_changed_conditions(field, value):
    plan = diagnostic.make_plan()
    plan[field] = value
    with pytest.raises(ValueError):
        diagnostic.validate_plan(plan)


def test_smoke_preserves_phase_connection_offsets():
    scenario = diagnostic.make_plan()["scenarios"][0]
    steps = list(diagnostic.schedule(scenario, smoke=True))
    assert [x[2] for x in steps] == [0, 1, 2, 3, 450, 451, 452, 453, 900, 901, 902, 903]
    full = list(diagnostic.schedule(scenario))
    assert len(full) == 1350
    assert [x[2] for x in full] == list(range(1350))


def test_unknown_selector_actions_do_not_receive_true_rate():
    plan = diagnostic.make_plan()
    scenario = plan["scenarios"][0]
    results = [diagnostic.phase_design(scenario, scenario["phases"][1], rate, plan["c_pkt"])
               for rate in plan["true_u_mbps"]]
    for arm in diagnostic.UNKNOWN_ARMS:
        assert len({tuple(r["arms"][arm]) for r in results}) == 1
    assert len({tuple(r["arms"]["known_u_model"]) for r in results}) > 1
    assert all(r["selector_input"]["unknown_u"] is None for r in results)


def test_paired_threshold_uses_family_bound_and_seed_units():
    differences = [20 + (-1 if i % 2 else 1) for i in range(20)]
    result = diagnostic.paired_inference(differences, False)
    assert result["counterexample_6_5"]
    assert result["family95"]["n"] == 20
    assert result["family95"]["lower"] < result["paired95"]["lower"]
    near = diagnostic.paired_inference([6.5 + (-1 if i % 2 else 1) for i in range(20)], False)
    assert not near["counterexample_6_5"]


def test_unobserved_variance_is_not_a_zero_error_certificate():
    result = diagnostic.paired_inference([20.0] * 20, False)
    assert result["zero_variance_unresolved"]
    assert result["family95"]["lower"] is None
    assert not result["counterexample_6_5"]
    zero = diagnostic.paired_inference([0.0] * 20, True)
    assert zero["structural_zero"]
    assert zero["family95"]["lower"] == zero["family95"]["upper"] == 0
    with pytest.raises(ValueError):
        diagnostic.paired_inference([1.0] * 20, True)


def test_summary_requires_every_frozen_seed():
    plan = diagnostic.make_plan()
    incomplete = [{"scenario":"B1", "true_u_mbps":0, "seed":31,
                   "groups":{"0.02":{"n":900,"pairs":{"unknown_u_nominal:known_u_model":
                       {"difference_sum":0,"same_action":True}}}}}]
    with pytest.raises(AssertionError):
        diagnostic.summarize(incomplete, plan, False)
