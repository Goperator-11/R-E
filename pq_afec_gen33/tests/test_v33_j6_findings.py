import copy
import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location("j6_findings", (Path(__file__).resolve().parents[1] / "g3/v33/validation/J6_final_analysis_v1/runs/j6_findings_extract_v1.py"))
findings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(findings)


def fixture():
    rows = []
    for mode in ("none", "c1"):
        for sid in ("B1", "B2"):
            rows.append({"candidate": {"generation": "j6_" + mode}, "baseline": {"generation": "l1_" + mode},
                "scenario": sid, "primary": True, "regression_gate": {"status": "pass"},
                "seed_summary": {"mean": -.3, "lower": -.4, "upper": -.2}, "shared_mc_bound_ms": .01,
                "lower_bound_ms": -.41, "upper_bound_ms": -.19})
    return {"status": "complete", "missing": [], "missing_raw_groups": [], "comparisons": rows}


def test_requires_every_original_cell_and_a_c1_reduction():
    report = fixture()
    assert findings.assess(report, ["B1", "B2"])["candidate_adopted"]
    for row in report["comparisons"]:
        row["upper_bound_ms"] = 0.0
    assert not findings.assess(report, ["B1", "B2"])["candidate_adopted"]


@pytest.mark.parametrize("status", ["fail", "inconclusive"])
def test_one_unresolved_or_regressed_cell_is_not_cancelled_by_other_gains(status):
    report = fixture()
    report["comparisons"][0]["regression_gate"]["status"] = status
    result = findings.assess(report, ["B1", "B2"])
    assert not result["candidate_adopted"] and result["primary_counts"][status] == 1


@pytest.mark.parametrize("kind", ["missing", "duplicate", "unplanned", "unmarked", "partial"])
def test_bad_report_inventory_is_rejected(kind):
    report = fixture()
    if kind == "missing":
        report["comparisons"].pop()
    elif kind == "duplicate":
        report["comparisons"].append(copy.deepcopy(report["comparisons"][0]))
    elif kind == "unplanned":
        report["comparisons"][0]["scenario"] = "unplanned"
    elif kind == "unmarked":
        report["comparisons"][0]["primary"] = False
    else:
        report["status"] = "partial"
    with pytest.raises(ValueError):
        findings.assess(report, ["B1", "B2"])
