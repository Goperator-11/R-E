import copy
import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location("l3_extract", (Path(__file__).resolve().parents[1] / "g3/v33/validation/L3_final_analysis_v1/runs/l3_findings_extract_v1.py"))
extractor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extractor)


def fixture():
    comparisons = []
    for candidate, baseline in (("l3_none", "l1_none"), ("l3_c1", "l1_c1"), ("l3_c1", "v31")):
        for index in range(15):
            comparisons.append({"candidate": {"generation": candidate}, "baseline": {"generation": baseline},
                "scenario": f"cell{index:02d}", "primary": True, "kind": "direct_previous_policy",
                "seed_summary": {"mean": -.2, "lower": -.3, "upper": -.1}, "shared_mc_bound_ms": .01,
                "lower_bound_ms": -.31, "upper_bound_ms": -.09, "regression_gate": {"status": "pass"}})
    groups = []
    for sid in ("B1", "B2"):
        groups.append({"generation": "l3_c1", "scenario": sid, "family": sid,
            "expected_regret": {"seed_summary": {"mean": .01}, "lower_bound_ms": 0, "upper_bound_ms": .02},
            "observed": {"p_bias_high_phase": {}, "mean_extra_server_bytes": {}, "alarm_rate_per_1000": {}},
            "monitor_diagnostics": None, "p_convergence": None,
            "gates": {"regret": {"status": "pass"}, "monitor_alarm": {"status": "pass"}}})
    report = {"comparisons": comparisons, "groups": groups, "data_kind": "test_fixture"}
    operating = {"injection": {"replicates": 250, "median_including_censor_as_infinity": 10, "median_le_15": True}}
    return report, operating


def test_all_independent_adoption_conditions_required():
    report, operating = fixture()
    assert extractor.extract(report, operating)["candidate_eligible_for_adoption"]
    original = copy.deepcopy(report)
    for target, status in ((0, "fail"), (14, "inconclusive"), (44, "inconclusive")):
        changed = copy.deepcopy(report)
        changed["comparisons"][target]["regression_gate"]["status"] = status
        assert not extractor.extract(changed, operating)["candidate_eligible_for_adoption"]
    assert report == original


@pytest.mark.parametrize("sid,gate,status", [(0, "regret", "fail"), (1, "regret", "inconclusive"), (0, "monitor_alarm", "fail")])
def test_relative_success_cannot_hide_absolute_or_alarm_failure(sid, gate, status):
    report, operating = fixture()
    report["groups"][sid]["gates"][gate]["status"] = status
    result = extractor.extract(report, operating)
    assert result["primary_all_pass"]
    assert not result["candidate_eligible_for_adoption"]


@pytest.mark.parametrize("replicates,median,declared", [(249, 10, True), (250, None, False), (250, 16, False), (250, 10, False)])
def test_injection_population_censor_and_threshold_required(replicates, median, declared):
    report, operating = fixture()
    operating["injection"].update(replicates=replicates, median_including_censor_as_infinity=median, median_le_15=declared)
    assert not extractor.extract(report, operating)["candidate_eligible_for_adoption"]


def test_cost_reduction_must_have_negative_adjusted_upper_against_l1():
    report, operating = fixture()
    for row in report["comparisons"]:
        if row["baseline"]["generation"].startswith("l1_"):
            row["upper_bound_ms"] = 0
    result = extractor.extract(report, operating)
    assert result["primary_all_pass"]
    assert not result["candidate_eligible_for_adoption"]


def test_missing_absolute_group_or_noninferiority_cell_does_not_pass():
    report, operating = fixture()
    report["groups"].pop()
    assert not extractor.extract(report, operating)["candidate_eligible_for_adoption"]
    report, operating = fixture()
    report["comparisons"].pop()
    assert not extractor.extract(report, operating)["candidate_eligible_for_adoption"]
