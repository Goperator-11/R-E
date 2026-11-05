import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import collections
import datetime as dt
import hashlib
import json
from pathlib import Path


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
PLAN = ROOT / "g3/v33/bench_overlays/L1_precision_v1.json"
REPORT = ROOT / "g3/v33/L1_benchmark_precision_v1.json"
ORIGINAL = ROOT / "g3/v33/L1_benchmark.json"
OUTPUT = RUNS / "L1_precision_findings_extract_v4.json"
CHECKER = RUNS / "l1_precision_artifact_check_v4.py"
CHECK = RUNS / "L1_precision_artifact_check_v4.json"
INPUTS = {}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    current = hashlib.sha256(raw).hexdigest()
    require(str(path) not in INPUTS or INPUTS[str(path)] == current, "input changed between reads")
    INPUTS[str(path)] = current
    return json.loads(raw)


def bind(path, expected):
    path = Path(path).resolve(strict=True)
    current = sha(path)
    require(current == expected, "bound file differs: " + str(path))
    require(str(path) not in INPUTS or INPUTS[str(path)] == expected, "bound file changed during extraction")
    INPUTS[str(path)] = current


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def contrast_key(item):
    return item["candidate"]["generation"], item["baseline"]["generation"], item["scenario"]


def group_key(item):
    return item["generation"], item["scenario"]


def interval_relation(lower, upper):
    if lower is None or upper is None:
        return "unknown"
    return "below_zero" if upper < 0 else "above_zero" if lower > 0 else "contains_zero"


def compact_comparison(item):
    fields = ("scenario", "primary", "seed_summary", "shared_mc_bound_ms", "selection_gap_bound_ms",
              "lower_bound_ms", "upper_bound_ms", "regression_gate", "realized_hct_diagnostic")
    return {**{key: item[key] for key in fields}, "candidate": item["candidate"]["generation"],
            "baseline": item["baseline"]["generation"],
            "interval_relative_to_zero": interval_relation(item["lower_bound_ms"], item["upper_bound_ms"])}


def main():
    require(not OUTPUT.exists(), "extract output must be new")
    bind(__file__, sha(__file__))
    checked = read(CHECK)
    require(checked["status"] == "pass" and checked["error"] is None, "independent artifact check has not passed")
    require(checked["script_path"] == str(CHECKER) and checked["script_sha256"] == checked["script_sha256_after"], "checker source binding differs")
    bind(CHECKER, checked["script_sha256"])
    for path in (REPORT, Path(str(REPORT) + ".published.json")):
        bind(path, checked["verified_files_sha256"][str(path)])
    for key, expected in (("raw_seed_runs", 1500), ("references", 19), ("family", 100), ("groups", 75), ("comparisons", 105), ("MC_N", 1048576)):
        require(checked["counts"][key] == expected, "verified input count differs: " + key)
    receipts = {}
    for phase in ("plan", "run", "report"):
        path = RUNS / ("L1_precision_" + phase + ("_v1.finished.json" if phase == "plan" else "_v2.finished.json"))
        receipt = read(path)
        require(receipt["status"] == "complete" and receipt["exit_code"] == 0, "precision phase incomplete: " + phase)
        require(receipt["wrapper_sha256"] == receipt["wrapper_sha256_after"] and
                receipt["driver_sha256"] == receipt["driver_sha256_after"], "phase source changed")
        start_path = RUNS / ("L1_precision_" + phase + ("_v1.started.json" if phase == "plan" else "_v2.started.json"))
        bind(start_path, receipt["started_receipt_sha256"])
        bind(ROOT / "experiments/v33/bench_learning_precision.py", receipt["wrapper_sha256"])
        bind(RUNS / ("l1_precision_driver_v1.py" if phase == "plan" else "l1_precision_driver_v2.py"), receipt["driver_sha256"])
        for field in ("stdout", "stderr"):
            bind(receipt[field + "_path"], receipt[field + "_sha256"])
        for artifact, expected in receipt["published_outputs_sha256"].items():
            bind(artifact, expected)
        receipts[phase] = receipt
    require(receipts["run"]["recovery_identity"] == receipts["report"]["recovery_identity"], "restart recovery link differs")
    recovery = receipts["run"]["recovery_identity"]
    bind(recovery["path"], recovery["sha256"])
    require(receipts["run"]["plan_identity"] == receipts["report"]["plan_identity"], "run/report plan differs")
    require(receipts["report"]["preceding_run"]["path"] == str(RUNS / "L1_precision_run_v2.finished.json"), "report run path differs")
    bind(receipts["report"]["preceding_run"]["path"], receipts["report"]["preceding_run"]["sha256"])
    plan = read(PLAN)
    require(sha(PLAN) == "f71d22fba623fd42a0ae9e906ede79372449e008e9669174888ba2a78975a4ff", "fixed precision plan differs")
    marker_path = Path(str(REPORT) + ".published.json")
    marker = read(marker_path)
    require(marker["schema"] == "padfec.v33.learning_precision_publication/1" and marker["status"] == "complete", "precision publication incomplete")
    require(set(marker["artifacts_sha256"]) == {str(REPORT), str(RUNS / "L1_precision_bench_v1.md")}, "publication artifact inventory differs")
    for path, expected in marker["artifacts_sha256"].items():
        bind(path, expected)
    bind(marker["precision_plan_path"], marker["precision_plan_sha256"])
    require(marker["precision_plan_sha256"] == sha(PLAN), "publication plan differs")
    bind(ORIGINAL, plan["original"]["report_sha256"])
    bind(plan["original"]["publication_path"], plan["original"]["publication_sha256"])
    require(marker["original_publication_sha256"] == plan["original"]["publication_sha256"], "original publication linkage differs")
    original_marker = read(plan["original"]["publication_path"])
    for path, expected in original_marker["artifacts_sha256"].items():
        bind(path, expected)
    protocol = read(plan["base_protocol_path"])
    bind(plan["base_protocol_path"], plan["base_protocol_sha256"])
    bind(plan["effective_protocol_path"], plan["effective_protocol_sha256"])
    report, original = read(REPORT), read(ORIGINAL)
    require(report["schema"] == "padfec.v33.learning_precision_report/1" and report["status"] == "complete", "precision report incomplete")
    require(not report["missing"] and not report["missing_raw_groups"], "precision report missing inputs")
    require(original["status"] == "complete" and original["schema"] == "padfec.v33.learning_report/1", "original report incomplete")
    provenance = report["provenance"]
    require(provenance["precision_plan_sha256"] == marker["precision_plan_sha256"], "report plan differs")
    require(provenance["wrapper_sha256"] == marker["wrapper_sha256"] == plan["wrapper_sha256"], "wrapper binding differs")
    require(provenance["reporter_sha256"] == marker["reporter_sha256"] == plan["reporter_sha256"], "reporter binding differs")
    require(provenance["reference_lineage"] == plan["reference_lineage"], "reference lineage differs")
    require(provenance["result_partition"] == plan["result_partition"], "result partition differs")
    require(digest(provenance["action_pool"]) == marker["pool_attestation_sha256"], "pool attestation digest differs")
    require(provenance["action_pool"]["execution_content_sha256"] == marker["execution_content_sha256"], "execution digest differs")
    require(provenance["learning_inputs"] == original["provenance"]["learning_inputs"], "original learning inputs differ")
    require(report["precision_scope"] == plan["contract"], "precision interpretation differs")
    names = ("v31", "v32", "current_none", "current_c1", "current_ideal")
    scenarios = [item["id"] for item in protocol["scenarios"]]
    expected_groups = {(name, scenario) for name in names for scenario in scenarios}
    pairs = [("current_" + mode, base) for mode in ("none", "c1", "ideal") for base in ("v32", "v31")] + [("current_c1", "current_none")]
    expected_comparisons = {(a, b, scenario) for a, b in pairs for scenario in scenarios}
    for value in (report, original):
        group_keys = [group_key(item) for item in value["groups"]]
        comparison_keys = [contrast_key(item) for item in value["comparisons"]]
        require(len(group_keys) == len(set(group_keys)) == 75 and set(group_keys) == expected_groups, "group inventory differs")
        require(len(comparison_keys) == len(set(comparison_keys)) == 105 and set(comparison_keys) == expected_comparisons, "comparison inventory differs")
        require(all(item["variant"] == "full" and item["seeds"] == protocol["seeds"] for item in value["groups"]), "group variants or seeds differ")
        require(all([row["seed"] for row in item["seed_estimates"]] == protocol["seeds"] for item in value["comparisons"]), "comparison seeds differ")
        require(value["evaluation_family_size"] == 100, "action family differs")
    original_groups = {group_key(item): item for item in original["groups"]}
    original_comparisons = {contrast_key(item): item for item in original["comparisons"]}
    compact_groups, comparison_changes = [], []
    for item in report["groups"]:
        old = original_groups[group_key(item)]
        for field in ("observed", "p_convergence", "observation_diagnostics"):
            require(item[field] == old[field], "unchanged raw summary differs: " + field)
        compact_groups.append({key: item[key] for key in ("generation", "scenario", "family", "observation_mode", "expected_regret", "observed", "gates", "p_convergence", "observation_diagnostics")})
    for item in report["comparisons"]:
        old = original_comparisons[contrast_key(item)]
        require(item["realized_hct_diagnostic"] == old["realized_hct_diagnostic"], "realized HCT changed")
        require(item["selection_gap_bound_ms"] == old["selection_gap_bound_ms"], "reference selection bound changed")
        require(item["regression_gate"]["threshold"] == protocol["thresholds"]["max_regression_vs_v31_ms"] and item["regression_gate"]["inclusive"], "regression threshold differs")
        comparison_changes.append({"original": compact_comparison(old), "precision": compact_comparison(item)})
    before_after = [item for item in report["comparisons"] if item["primary"] and item["baseline"]["generation"] == "v32"]
    require(len(before_after) == 15 and all(item["candidate"]["generation"] == "current_c1" for item in before_after), "primary comparison inventory differs")
    result = {"schema": "padfec.v33.learning_precision_findings_extract/1",
              "recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
              "source_data_kind": "post_result_development_precision_same_seed_prefix_not_independent_replication",
              "scope": "Descriptive extraction only; no changed threshold, seed, interval, policy or adoption decision",
              "script_sha256": sha(__file__), "inputs_sha256": INPUTS,
              "artifact_check": {"path": str(CHECK), "sha256": sha(CHECK), "script_sha256": checked["script_sha256"]},
              "precision_scope": report["precision_scope"], "inference_scope": report["inference_scope"],
              "inventory": {"groups": 75, "comparisons": 105, "raw_runs": 1500, "references": 19, "action_family": 100},
              "noninferiority": report["noninferiority"], "groups": compact_groups,
              "comparison_changes": comparison_changes,
              "c1_vs_v32": {"expected_improvement_adjusted_upper_below_zero": [item["scenario"] for item in before_after if item["upper_bound_ms"] is not None and item["upper_bound_ms"] < 0],
                            "regression_gate_fail": [item["scenario"] for item in before_after if item["regression_gate"]["status"] == "fail"],
                            "regression_gate_inconclusive": [item["scenario"] for item in before_after if item["regression_gate"]["status"] == "inconclusive"]},
              "all_comparison_gate_counts": dict(collections.Counter(item["regression_gate"]["status"] for item in report["comparisons"]))}
    for path, expected in INPUTS.items():
        require(sha(path) == expected, "input changed before extraction publication")
    with OUTPUT.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"out": str(OUTPUT), "sha256": sha(OUTPUT), "c1_vs_v32": result["c1_vs_v32"],
                      "noninferiority": result["noninferiority"], "all_comparison_gate_counts": result["all_comparison_gate_counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
