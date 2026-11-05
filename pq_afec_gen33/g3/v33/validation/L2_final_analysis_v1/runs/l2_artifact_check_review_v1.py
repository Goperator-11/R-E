import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import copy
from fractions import Fraction
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
from unittest import mock


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sys.path.insert(0, str(ROOT))


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


check = module("l2_artifact_checker", RUNS / "l2_joint_artifact_check_v1.py")
fixture_module = module("l2_report_fixture", ROOT / "tests/test_v33_learning_l2_report.py")
from experiments.v33 import bench_learning_l2_report as reporter, bench_learning_report as previous_reporter


fixture_helper = fixture_module.JointLearningReportTests()
fixture_helper.setUp()
fixture = list(fixture_helper.fixture("B4"))
protocol = fixture[0]
protocol["seeds"] = list(range(31, 51))
protocol["scenarios"] = [{**protocol["scenarios"][0], "id": f"cell{i:02d}"} for i in range(15)]
for index in range(1, 5):
    fixture[index] = [{**copy.deepcopy(row), "seed": seed, "scenario": scenario["id"]}
                      for row in fixture[index] if row["seed"] == 31
                      for scenario in protocol["scenarios"] for seed in protocol["seeds"]]
runs = reporter.analysis_runs(*fixture[:5])
groups = {}
for row in runs:
    groups.setdefault((row["generation"], row["scenario"]), []).append(row)
result = fixture_helper.aggregate(fixture)
old = previous_reporter.aggregate_learning(protocol, fixture[1], fixture[2], fixture[5], fixture[6], trace_loader=fixture_helper.base.trace)
audit = check.Audit()
check.check_aggregates(audit, result, old, groups, fixture[6], fixture[5], protocol)
arithmetic_checks = audit.count
rejected = []
changes = [lambda value: value["groups"][0]["expected_regret"].update(shared_mc_bound_ms=100),
           lambda value: value["comparisons"][0]["seed_summary"].update(mean=100),
           lambda value: value["comparisons"][0].update(primary=False),
           lambda value: value["noninferiority"]["l2_none_vs_l1_none"].update(status="fail")]
for index, change in enumerate(changes):
    changed = copy.deepcopy(result)
    change(changed)
    try:
        check.check_aggregates(check.Audit(), changed, old, groups, fixture[6], fixture[5], protocol)
    except ValueError as exc:
        rejected.append({"case": index, "reason": str(exc)})
    else:
        raise ValueError("checker accepted changed arithmetic")
moment_cases = 0
for a, b in ((1, 999), (999, 1), (.3, 4), (4000, 4000), (.00001, 7000), (7000, .00001)):
    for q in (0, 1 / 3, .001, .1, .9, 1):
        A, B, Q = Fraction(a), Fraction(b), Fraction(q)
        if q == 1 / 3:
            expected = float(a), float(b)
        else:
            rho = (1 - Q) * A / ((1 - Q) * A + 2 * Q * B)
            t = A + B + 1
            mean = (A + rho) / t
            second = (A + 1) * (A + 2 * rho) / (t * (t + 1))
            variance = second - mean * mean
            strength = mean * (1 - mean) / variance - 1
            expected = float(mean * strength), float((1 - mean) * strength)
        actual = check.posterior_moments(a, b, q)
        assert all(math.isclose(x, y, rel_tol=2e-9, abs_tol=1e-10) for x, y in zip(actual, expected)), (a, b, q, actual, expected)
        moment_cases += 1
smoke = json.loads((RUNS / "L2_smoke_v1.finished.json").read_text(encoding="utf-8"))
smoke_results, smoke_audit = [], check.Audit()
for receipt in smoke["results"]:
    command = receipt["command"]
    folder = Path(command[command.index("--out") + 1])
    overlay = json.loads(Path(command[command.index("--overlay") + 1]).read_text(encoding="utf-8"))
    for path in sorted(folder.glob("*/*/seed*.json")):
        if path.name.count(".") != 1:
            continue
        run = smoke_audit.read(path)
        run["analysis_role"] = "l2" if overlay["policy"]["epsilon_calibration"] == "adaptive" else "fixed"
        run["generation"] = run["analysis_role"] + "_" + run["observation_mode"]
        smoke_results.append(check.epsilon_seed(smoke_audit, run))
assert len(smoke_results) == 5 and sum(row["connections"] for row in smoke_results) == 60
assert sum(row["eligible"] for row in smoke_results) == 55
out = RUNS / sys.argv[1]
summary = {"status": "pass", "checker_sha256": check.SELF_SHA,
           "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           "synthetic_arithmetic_checks": arithmetic_checks, "rejected_mutations": rejected,
           "fraction_moment_cases": moment_cases, "actual_smoke_checks": smoke_audit.count,
           "actual_smoke_runs": len(smoke_results), "actual_smoke_connections": 60,
           "scope": "Synthetic full report arithmetic and previously completed smoke traces; no L2 full performance or MC results inspected."}
with out.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(summary, stream, ensure_ascii=False, indent=2, allow_nan=False)
    stream.write("\n")
print(json.dumps(summary, ensure_ascii=False))
