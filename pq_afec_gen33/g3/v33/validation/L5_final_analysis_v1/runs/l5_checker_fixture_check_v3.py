import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import collections
import copy
import gzip
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

checker = load("l5_checker_fixture", RUNS / "l5_joint_artifact_check_v3.py")
module = load("l5_report_fixture", ROOT / "tests/test_v33_learning_l5_report.py")
test = module.JointLearningReportTests()
test.setUp()
fixture = list(test.fixture())
protocol = fixture[0]
protocol["seeds"] = list(range(31, 51))
protocol["scenarios"] = [{**protocol["scenarios"][0], "id": f"cell{i:02d}"} for i in range(15)]
for index in range(1, 5):
    fixture[index] = [{**copy.deepcopy(row), "seed": seed, "scenario": scenario["id"]}
        for row in fixture[index] if row["seed"] == 31
        for scenario in protocol["scenarios"] for seed in protocol["seeds"]]
for index, action in ((2, (1, 0, 0)), (3, (2, 0, 0)), (4, (3, 0, 0))):
    for row in fixture[index]:
        test.base.replace_action(row, action)
for index, mean, width in ((1, .4, .03), (2, .1, .04), (3, .2, .02)):
    fixture[6]["c", (index, 0, 0)] = test.base.table((index, 0, 0), mean=mean, width=width)
report = test.aggregate(fixture)
old = module.report.legacy.aggregate_learning(protocol, fixture[1], fixture[2], fixture[5], fixture[6], trace_loader=test.base.trace)
groups = collections.defaultdict(list)
for row in module.report.analysis_runs(*fixture[:5]):
    groups[row["generation"], row["scenario"]].append(row)
timer = time.monotonic()
audit = checker.Audit()
checker.check_aggregates(audit, report, old, groups, fixture[6], fixture[5], protocol)
cases = []
for name in ("primary", "kind", "mean", "MC", "gate", "missing", "summary"):
    altered = copy.deepcopy(report)
    row = next(r for r in altered["comparisons"] if r["candidate"]["generation"] == "l5_c1" and r["baseline"]["generation"] == "l1_c1")
    if name == "primary":
        row["primary"] = False
    elif name == "kind":
        row["kind"] = "wrong_contrast"
    elif name == "mean":
        row["seed_estimates"][0]["mean_delta_ms"] += .1
    elif name == "MC":
        row["shared_mc_bound_ms"] = 0
    elif name == "gate":
        row["regression_gate"]["status"] = "fail"
    elif name == "missing":
        altered["comparisons"].remove(row)
    else:
        altered["noninferiority"]["l5_c1_vs_l1_c1"]["primary"] = False
    try:
        checker.check_aggregates(checker.Audit(), altered, old, groups, fixture[6], fixture[5], protocol)
    except ValueError as exc:
        cases.append({"mutation": name, "rejected_at": str(exc)})
    else:
        raise AssertionError("mutation accepted: " + name)
smoke_groups = collections.defaultdict(list)
for folder in RUNS.glob("L5_smoke_v1_L5_*"):
    if not folder.is_dir():
        continue
    for path in folder.glob("*/*/seed*.json"):
        if path.name.count(".") != 1:
            continue
        run = json.loads(path.read_text(encoding="utf-8"))
        run["analysis_role"] = "single" if "single" in folder.name else "l5"
        smoke_groups[run["analysis_role"], run["observation_mode"]].append(run)
grades = checker.grade.check_runs(audit, smoke_groups)
run = smoke_groups["l5", "none"][0]
with gzip.open(run["trace_path"], "rt", encoding="utf-8") as stream:
    rows = [json.loads(line) for line in stream]
for key, value in (("cut1_ms", 1.0), ("grade", 2), ("updated", False), ("epsilon_after", .01), ("loss_update_kind", "datagram")):
    row = copy.deepcopy(rows[1])
    assert row["observation_info"][key] != value
    row["observation_info"][key] = value
    try:
        checker.grade.check_row(checker.Audit(), row, "mutation_" + key)
    except ValueError as exc:
        cases.append({"mutation": key, "rejected_at": str(exc)})
    else:
        raise AssertionError("grade mutation accepted: " + key)
result = {"status": "pass", "groups": len(groups), "comparisons": len(report["comparisons"]), "positive_checks": audit.count,
    "mutations_rejected": cases, "smoke_grade_audit": grades, "elapsed_seconds": time.monotonic() - timer,
    "script_sha256": sha(__file__), "checker_sha256": sha(RUNS / "l5_joint_artifact_check_v3.py"),
    "scope": "Synthetic full-size aggregate arithmetic and mutation rejection, plus ten smoke grade traces; no full collection performance read."}
with (RUNS / "L5_checker_fixture_check_v3.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, indent=2)
    stream.write("\n")
print(json.dumps(result))
