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
checker_path = RUNS / "l5_joint_artifact_check_v2.py"
checker = load("l5_adaptation_checker", checker_path)
fixture_module = load("l5_adaptation_fixture", ROOT / "tests/test_v33_learning_l5_report.py")
test = fixture_module.JointLearningReportTests()
test.setUp()
audit = checker.Audit()
mutations = []
cases = 0
timer = time.monotonic()
for mean, uncertainty, expected in ((.02, .01, "pass"), (2, .01, "inconclusive"), (.02, None, "inconclusive")):
    fixture = test.fixture("B5")
    fixture[6]["c", (0, 0, 0)] = test.base.table(mean=mean, width=uncertainty)
    report = test.aggregate(fixture)
    groups = collections.defaultdict(list)
    for run in fixture_module.report.analysis_runs(*fixture[:5]):
        groups[run["generation"], run["scenario"]].append(run)
    def check(group):
        return checker.adaptation_audit.check_group(audit, group, groups[group["generation"], group["scenario"]], fixture[0]["scenarios"][0],
            fixture[0], fixture[5], fixture[6], checker.base.width, trace_loader=test.base.trace)
    for group in report["groups"]:
        cases += check(group)
        audit.equal("small_fixture_end_censor", group["gates"]["adaptation"]["status"], expected)
    if uncertainty == .01 and mean == .02:
        for kind in ("gate", "start", "unknown", "episode", "case_seed", "missing_case", "threshold"):
            group = copy.deepcopy(report["groups"][0])
            if kind == "gate":
                group["gates"]["adaptation"]["status"] = "fail"
            elif kind == "start":
                group["trace_metrics_by_seed"][0]["adaptation"][0]["start_new_observations"] = 1
            elif kind == "unknown":
                group["trace_metrics_by_seed"][0]["unknown_cost_rows"] = 1
            elif kind == "episode":
                group["trace_metrics_by_seed"][0]["longest_confirmed_suboptimal_episode"] = 1
            elif kind == "case_seed":
                group["gates"]["adaptation"]["cases"][0]["seed"] = 999
            elif kind == "missing_case":
                group["gates"]["adaptation"]["cases"].pop()
            else:
                group["gates"]["adaptation"]["threshold"] = 3
            try:
                check(group)
            except ValueError as exc:
                mutations.append({"mutation": kind, "rejected_at": str(exc)})
            else:
                raise AssertionError("accepted B5 mutation: " + kind)
for flags, expected in (([False] * 8, "fail"), ([False, False, True, True], "pass"), ([False, False, False, True, True], "fail"), ([None] * 8, "inconclusive")):
    value = checker.adaptation_audit.event(flags, 0, len(flags), 2, 2)
    audit.equal("B5_boundary:" + repr(flags), value["threshold_status"], expected)
for mean, width, status in ((.02, .01, "pass"), (2, .01, "fail"), (.02, None, "inconclusive"), (.49, 0, "pass")):
    fixture = list(test.fixture("B6"))
    fixture[0]["seeds"] = list(range(31, 51))
    fixture[0]["scenarios"] = [{**fixture[0]["scenarios"][0], "id": "B6" if i == 0 else f"cell{i:02d}", "family": "B6" if i == 0 else "B1"} for i in range(15)]
    for index in range(1, 5):
        fixture[index] = [{**copy.deepcopy(run), "seed": seed, "scenario": scenario["id"]}
            for run in fixture[index] if run["seed"] == 31 for scenario in fixture[0]["scenarios"] for seed in fixture[0]["seeds"]]
    fixture[6]["c", (0, 0, 0)] = test.base.table(mean=mean, width=width)
    report = test.aggregate(fixture)
    old = fixture_module.report.legacy.aggregate_learning(fixture[0], fixture[1], fixture[2], fixture[5], fixture[6], trace_loader=test.base.trace)
    groups = collections.defaultdict(list)
    for run in fixture_module.report.analysis_runs(*fixture[:5]):
        groups[run["generation"], run["scenario"]].append(run)
    checker.check_aggregates(audit, report, old, groups, fixture[6], fixture[5], fixture[0])
    for group in report["groups"]:
        if group["family"] == "B6":
            audit.equal("B6_expected_gate", group["gates"]["mixture_fixed_regret"]["status"], status)
    altered = copy.deepcopy(report)
    next(group for group in altered["groups"] if group["family"] == "B6")["gates"]["mixture_fixed_regret"]["status"] = "fail" if status != "fail" else "pass"
    try:
        checker.check_aggregates(audit, altered, old, groups, fixture[6], fixture[5], fixture[0])
    except ValueError as exc:
        mutations.append({"mutation": "B6_gate_" + str(mean) + "_" + str(width), "rejected_at": str(exc)})
    else:
        raise AssertionError("accepted B6 mutation")
result = {"status": "pass", "positive_and_mutation_checks": audit.count, "B5_cases": cases, "B6_groups": 40,
          "mutations_rejected": mutations, "elapsed_seconds": time.monotonic() - timer,
          "script_sha256": sha(__file__), "checker_sha256": sha(checker_path),
          "scope": "independent synthetic B5 change timing/censoring and B6 inclusive threshold/unknown uncertainty; no full performance read"}
with (RUNS / "L5_adaptation_fixture_check_v3.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, indent=2)
    stream.write("\n")
print(json.dumps(result))
