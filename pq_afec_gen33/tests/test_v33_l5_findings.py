import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("l5_findings", (Path(__file__).resolve().parents[1] / "g3/v33/validation/L5_final_analysis_v1/runs/l5_findings_extract_v3.py"))
findings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(findings)


def fixture():
    rows = []
    groups = []
    for mode in ("none", "c1"):
        for sid in ("B5", "B6"):
            rows.append({"candidate": {"generation": "l5_" + mode}, "baseline": {"generation": "l1_" + mode},
                "scenario": sid, "primary": True, "regression_gate": {"status": "pass"},
                "seed_summary": {"mean": -.3, "lower": -.4, "upper": -.2}, "shared_mc_bound_ms": .01,
                "lower_bound_ms": -.41, "upper_bound_ms": -.19})
            groups.append({"generation": "l5_" + mode, "scenario": sid,
                "gates": {"adaptation" if sid == "B5" else "mixture_fixed_regret": {"status": "pass"}}})
    return {"status": "complete", "missing": [], "missing_raw_groups": [], "comparisons": rows,
            "groups": groups, "historical_new_methods_gate": "pass"}


def test_all_predeclared_gates_required_even_with_favorable_mean():
    value = fixture()
    assert findings.assess(value, ["B5", "B6"])["candidate_adopted"]
    value["historical_new_methods_gate"] = "blocked_missing_inputs"
    assert not findings.assess(value, ["B5", "B6"])["candidate_adopted"]


@pytest.mark.parametrize("mode", ["none", "c1"])
@pytest.mark.parametrize("family", ["B5", "B6"])
@pytest.mark.parametrize("status", ["fail", "inconclusive"])
def test_specific_gate_cannot_be_cancelled_by_other_gains(mode, family, status):
    value = fixture()
    group = next(row for row in value["groups"] if row["generation"] == "l5_" + mode and row["scenario"] == family)
    next(iter(group["gates"].values()))["status"] = status
    assert not findings.assess(value, ["B5", "B6"])["candidate_adopted"]


@pytest.mark.parametrize("status", ["fail", "inconclusive"])
def test_primary_gate_cannot_be_cancelled_by_specific_pass(status):
    value = fixture()
    value["comparisons"][0]["regression_gate"]["status"] = status
    assert not findings.assess(value, ["B5", "B6"])["candidate_adopted"]


@pytest.mark.parametrize("kind", ["missing", "duplicate", "unplanned", "unmarked", "partial", "group_missing", "group_duplicate", "history_missing", "specific_unknown"])
def test_incomplete_or_invalid_inventory_is_rejected(kind):
    value = fixture()
    if kind == "missing":
        value["comparisons"].pop()
    elif kind == "duplicate":
        value["comparisons"].append(copy.deepcopy(value["comparisons"][0]))
    elif kind == "unplanned":
        value["comparisons"][0]["scenario"] = "unplanned"
    elif kind == "unmarked":
        value["comparisons"][0]["primary"] = False
    elif kind == "partial":
        value["status"] = "partial"
    elif kind == "group_missing":
        value["groups"].pop()
    elif kind == "group_duplicate":
        value["groups"].append(copy.deepcopy(value["groups"][0]))
    elif kind == "history_missing":
        del value["historical_new_methods_gate"]
    else:
        next(iter(value["groups"][0]["gates"].values()))["status"] = "unknown"
    with pytest.raises(ValueError):
        findings.assess(value, ["B5", "B6"])


def test_no_improvement_is_rejected_even_when_every_threshold_passes():
    value = fixture()
    for row in value["comparisons"]:
        row["upper_bound_ms"] = 0.0
    assert not findings.assess(value, ["B5", "B6"])["candidate_adopted"]
    value["comparisons"][0]["upper_bound_ms"] = -.01
    assert findings.assess(value, ["B5", "B6"])["candidate_adopted"]
