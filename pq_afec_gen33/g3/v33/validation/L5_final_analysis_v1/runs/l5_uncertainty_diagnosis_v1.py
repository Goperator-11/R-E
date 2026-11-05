import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import collections
import datetime as dt
import hashlib
import json
from pathlib import Path

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
ROOT = Path(r"C:\dev\pq_afec_gen33")
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
checker_path = RUNS / "L5_joint_artifact_check_v3.json"
checker = read(checker_path)
assert checker["status"] == "pass" and checker["error"] is None
report_path = ROOT / "g3/v33/L5_benchmark_v1.json"
assert sha(report_path) == checker["files_sha256"][str(report_path)]
report = read(report_path)
unresolved, result_hashes = [], {}
for path in sorted((RUNS / "L5_joint_action_pool_v1/results").glob("*.json")):
    assert sha(path) == checker["files_sha256"][str(path)]
    value = read(path)
    result_hashes[str(path)] = sha(path)
    if value.get("uncertainty_resolved") is False:
        selected = {key: value[key] for key in ("context", "action", "reference_action", "method", "n", "mean_gap_ms", "gap_variance_ms2", "gap_half_width_ms", "min_gap_ms", "max_gap_ms", "zero_observed_variance", "gap_exact_by_identity", "uncertainty_resolved")}
        unresolved.append({"path": str(path), "sha256": sha(path), **selected})
pairs = collections.defaultdict(collections.Counter)
rows = []
for row in report["comparisons"]:
    candidate, baseline = row["candidate"]["generation"], row["baseline"]["generation"]
    pairs[candidate + "_vs_" + baseline][row["regression_gate"]["status"]] += 1
    if row["regression_gate"]["status"] != "pass" or row["primary"]:
        rows.append({"candidate": candidate, "baseline": baseline, "scenario": row["scenario"], "primary": row["primary"],
                     "mean_delta_ms": row["seed_summary"]["mean"], "seed_lower_ms": row["seed_summary"]["lower"], "seed_upper_ms": row["seed_summary"]["upper"],
                     "mc_bound_ms": row["shared_mc_bound_ms"], "adjusted_lower_ms": row["lower_bound_ms"], "adjusted_upper_ms": row["upper_bound_ms"],
                     "gate": row["regression_gate"]["status"]})
groups = []
for group in report["groups"]:
    if group["scenario"] in ("B1", "B2", "B5", "B6", "B12_c6000") and group["generation"].startswith(("l5_", "single_", "l1_")):
        groups.append({"generation": group["generation"], "scenario": group["scenario"], "observed": group["observed"],
                       "expected_regret": group["expected_regret"]})
rules = ROOT / "g3/v33/bench_reporting_rules.json"
value = {"schema": "padfec.v33.l5_uncertainty_diagnosis/1", "recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
         "script_sha256": sha(__file__), "report_sha256": sha(report_path), "checker_sha256": sha(checker_path),
         "rules_sha256": sha(rules), "unresolved_actions": unresolved, "comparison_counts": dict(pairs), "selected_comparisons": rows,
         "selected_groups": groups, "result_files_sha256": result_hashes,
         "scope": "Read-only diagnosis of frozen completed results. Numerical-zero distinct-action variance is not an identity proof; no new samples, thresholds, parameter changes, or diagnostic adoption."}
out = RUNS / "L5_uncertainty_diagnosis_v1.json"
with out.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
    stream.write("\n")
print(json.dumps({"unresolved_action_count": len(unresolved), "counts": dict(pairs), "selected_comparison_count": len(rows)}, ensure_ascii=False))
