import copy
import gzip
import importlib.util
import json
from pathlib import Path
import tempfile

import pytest


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROOT = Path(__file__).resolve().parents[3]
independent = load("l3_monitor_audit", ROOT / "g3/v33/validation/L3_final_analysis_v1/runs/l3_monitor_audit_v1.py")
fixture = load("monitor_fixture", Path(__file__).with_name("l3_test_v33_learning_l3.py"))
base = load("independent_check_helpers", ROOT / "g3/v33/validation/L1_precision_final/runs/l1_precision_artifact_check_v4.py")
from experiments.v33 import bench_learning_l3_report as report
from padfec3 import learn3


@pytest.mark.parametrize("role,variant", [("l3", "full"), ("guard", "guard_only"), ("record", "record_only"), ("beta", "beta_only")])
def test_independent_reconstruction_and_diagnostics(role, variant):
    rows, state = fixture.sequence(fixture.CONFIGS[variant])
    audit, chain = base.Audit(), independent.initial()
    for index, row in enumerate(rows):
        independent.advance(audit, row, index, role, chain)
    independent.close(audit, "final", chain["monitor"], state.monitor)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "trace.gz"
        with gzip.open(path, "wt", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps(row) + "\n")
        result = independent.monitor_seed(audit, {"trace_path": str(path), "scenario": "B1", "analysis_role": role,
            "seed": 31, "n": len(rows), "final_serialized_state": {"v": 6, "arrival_streak": state.arrival_streak, "monitor_pending": state.monitor_pending, "monitor": state.monitor}})
    assert result == {"seed": 31, **report.monitor_diagnostics(rows)}


@pytest.mark.parametrize("field,value", [("direction", 1), ("beta_after", .1), ("up", 4), ("shared", True),
                                        ("q_used", .9), ("z", 0), ("reactive", True)])
def test_independent_checker_rejects_arithmetic_mutations(field, value):
    rows, _ = fixture.sequence(fixture.CONFIGS["full"], 2)
    audit, chain = base.Audit(), independent.initial()
    independent.advance(audit, rows[0], 0, "l3", chain)
    changed = copy.deepcopy(rows[1])
    changed["observation_info"]["monitor"][field] = value
    with pytest.raises(ValueError):
        independent.advance(audit, changed, 1, "l3", chain)


def test_independent_fit_rejects_wrong_bounded_optimum():
    with pytest.raises(ValueError):
        independent.fitted(base.Audit(), "fit", [[.01, 1]] * 32, .1)


def test_empty_monitor_population_uses_unavailable_interval():
    summary = report.paired_summary([])
    independent.check_population_summary(base.Audit(), "empty", summary, [], base.check_seed_summary)


def test_b9_reset_trace_does_not_carry_readiness_between_connections():
    rows, state = fixture.sequence(fixture.CONFIGS["full"], 1)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "reset.gz"
        with gzip.open(path, "wt", encoding="utf-8") as stream:
            for _ in range(3):
                stream.write(json.dumps(rows[0]) + "\n")
        result = independent.monitor_seed(base.Audit(), {"trace_path": str(path), "scenario": "B9", "analysis_role": "l3",
            "seed": 31, "n": 3, "final_serialized_state": state.to_json()})
    assert result["connections"] == result["skipped"] == 3
    assert result["ready"] == result["monitored"] == 0
    assert result["alarm_per_1000_monitored"] is None


def test_failed_connection_uses_f_grade_without_hct():
    rows, _ = fixture.sequence(fixture.CONFIGS["full"], 2)
    audit, chain = base.Audit(), independent.initial()
    independent.advance(audit, rows[0], 0, "l3", chain)
    changed = copy.deepcopy(rows[1])
    changed.update(ok=False, hct_ms=None)
    changed["observation_info"]["monitor_grade"] = 2
    independent.advance(audit, changed, 1, "l3", chain)
