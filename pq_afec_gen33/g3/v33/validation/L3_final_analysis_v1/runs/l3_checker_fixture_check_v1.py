import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import collections
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import time


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sys.path.insert(0, str(ROOT))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = load("joint_checker_fixture", RUNS / "l3_joint_artifact_check_v1.py")
fixture_module = load("l3_report_fixture", ROOT / "tests/test_v33_learning_l3_report.py")
test = fixture_module.MonitorReportTests()
test.setUp()
fixture = test.fixture()
protocol = fixture[0]
protocol["seeds"] = list(range(31, 51))
protocol["scenarios"] = [{**protocol["scenarios"][0], "id": f"cell{i:02d}"} for i in range(15)]
for index in range(1, 7):
    fixture[index] = [{**copy.deepcopy(row), "seed": seed, "scenario": scenario["id"]}
        for row in fixture[index] if row["seed"] == 31
        for scenario in protocol["scenarios"] for seed in protocol["seeds"]]
for index, action in ((2, (1, 0, 0)), (3, (5, 0, 0)), (4, (2, 0, 0)), (5, (3, 0, 0)), (6, (4, 0, 0))):
    for row in fixture[index]:
        test.base.replace_action(row, action)
for index in range(1, 6):
    fixture[8]["c", (index, 0, 0)] = test.base.table((index, 0, 0), mean=.6 - .1 * index, width=.01 * index)
report = test.aggregate(fixture)
old = fixture_module.report.legacy.aggregate_learning(protocol, fixture[1], fixture[2], fixture[7], fixture[8], trace_loader=test.base.trace)
groups = collections.defaultdict(list)
for row in fixture_module.report.analysis_runs(*fixture[:7]):
    groups[row["generation"], row["scenario"]].append(row)
started = time.monotonic()
audit = checker.Audit()
checker.check_aggregates(audit, report, old, groups, fixture[8], fixture[7], protocol)
cases = []
for name in ("primary", "kind", "mean", "MC", "gate", "missing", "summary"):
    altered = copy.deepcopy(report)
    row = next(row for row in altered["comparisons"] if row["candidate"]["generation"] == "l3_c1" and row["baseline"]["generation"] == "l1_c1")
    if name == "primary":
        row["primary"] = False
    elif name == "kind":
        row["kind"] = "ablation_step_contrast"
    elif name == "mean":
        row["seed_estimates"][0]["mean_delta_ms"] += .1
    elif name == "MC":
        row["shared_mc_bound_ms"] = 0
    elif name == "gate":
        row["regression_gate"]["status"] = "fail"
    elif name == "missing":
        altered["comparisons"].remove(row)
    else:
        altered["noninferiority"]["l3_c1_vs_l1_c1"]["primary"] = False
    try:
        checker.check_aggregates(checker.Audit(), altered, old, groups, fixture[8], fixture[7], protocol)
    except ValueError as exc:
        cases.append({"mutation": name, "rejected_at": str(exc)})
    else:
        raise AssertionError("mutation accepted: " + name)
result = {"status": "pass", "groups": len(groups), "comparisons": len(report["comparisons"]), "positive_checks": audit.count,
    "mutations_rejected": cases, "elapsed_seconds": time.monotonic() - started, "script_sha256": sha(__file__),
    "checker_sha256": sha(RUNS / "l3_joint_artifact_check_v1.py"), "scope": "Synthetic full-size aggregate arithmetic and rejection checks; no full collection performance read"}
with (RUNS / "L3_checker_fixture_check_v1.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, indent=2)
    stream.write("\n")
print(json.dumps(result))
