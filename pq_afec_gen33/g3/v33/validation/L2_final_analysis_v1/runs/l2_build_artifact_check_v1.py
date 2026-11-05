import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
from pathlib import Path


RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
source_path = RUNS / "l1_precision_artifact_check_v4.py"
assert hashlib.sha256(source_path.read_bytes()).hexdigest() == "a7504e1a2c94e54721077bbdaff068241da4e4274e17883eb5a7bab8f94aefd6"
source = source_path.read_text(encoding="utf-8")
out = RUNS / "l2_joint_artifact_check_v1.py"
prefix = out.read_text(encoding="utf-8")
assert "def check_pool(" not in prefix and "def check_aggregates(" not in prefix
pool = source[source.index("def check_pool("):source.index("def weights(")]
start = pool.index('            old_path = Path(plan["original"]')
end = pool.index('            audit.near("structural_width_zero:', start)
pool = pool[:start] + '''            audit.equal("structural_reference_method:" + job_id, ref["method"], "structural_zero_loss_certificate")
            audit.equal("structural_certificate:" + job_id, value["certificate"], ref["certificate"])
            audit.equal("structural_resolved:" + job_id, value["uncertainty_resolved"], True)
            audit.near("structural_gap_subtraction:" + job_id, value["mean_gap_ms"], value["mean_hct_ms"] - value["reference_mean_hct_ms"])
''' + pool[end:]
pool = pool.replace('    audit.equal("fixed_job_partition", partition, plan["result_partition"])',
                    '    audit.equal("structural_partition", partition["structural"], sorted(job_id for job_id, job in jobs.items() if refs[job["context_id"]]["method"] == "structural_zero_loss_certificate"))')
aggregate = source[source.index("def check_aggregates("):source.index("def check_markdown(")]
aggregate = aggregate.replace('old_groups = {(group["generation"], group["scenario"]): group for group in old_report["groups"]}',
    'old_groups = {(group["generation"].replace("current_", "l1_"), group["scenario"]): group for group in old_report["groups"]}')
aggregate = aggregate.replace('len(actual), 75)', 'len(actual), 150)')
old = '''        for field in ("observed", "observation_diagnostics", "p_convergence"):
            audit.equal("unchanged_observation:" + label + field, group[field], old_groups[key][field])
'''
new = '''        for field, summary in group["observed"].items():
            check_seed_summary(audit, "observed_summary:" + label + field, summary, [run["summary"][field] for run in runs])
        if key in old_groups:
            for field in ("observed", "observation_diagnostics", "p_convergence"):
                audit.equal("unchanged_observation:" + label + field, group[field], old_groups[key][field])
        if group["family"] == "B4":
            check_gate(audit, "bytes_gate:" + label, group["gates"]["bytes"], group["observed"]["mean_extra_server_bytes"], 0, 0, protocol["thresholds"]["B4_extra_bytes"], False)
'''
assert old in aggregate
aggregate = aggregate.replace(old, new)
old = '''    pairs = [("current_" + mode, base) for mode in ("none", "c1", "ideal") for base in ("v32", "v31")]
    pairs.append(("current_c1", "current_none"))
'''
new = '''    pairs = [("l2_" + mode, generation) for mode in ("none", "c1", "ideal") for generation in ("v32", "v31")]
    pairs += [("l2_c1", "l2_none")]
    pairs += [("l2_" + mode, "l1_" + mode) for mode in ("none", "c1", "ideal")]
    pairs += [("l2_" + mode, "fixed_" + mode) for mode in ("none", "c1")]
    pairs += [("fixed_" + mode, "l1_" + mode) for mode in ("none", "c1")]
    primary = {("l2_none", "l1_none"), ("l2_c1", "l1_c1"), ("l2_c1", "v31"), ("l2_c1", "v32")}
'''
assert old in aggregate
aggregate = aggregate.replace(old, new)
aggregate = aggregate.replace('len(report["comparisons"]), 105)', 'len(report["comparisons"]), 210)')
aggregate = aggregate.replace('candidate == "current_c1" and baseline in ("v31", "v32")', '(candidate, baseline) in primary')
aggregate = aggregate.replace('candidate == "current_ideal"', 'candidate.endswith("ideal") or baseline.endswith("ideal")')
start = aggregate.index('    for baseline, name in (("v32",')
aggregate = aggregate[:start] + '''    for candidate, baseline in pairs:
        cells = [row for row in report["comparisons"] if row["candidate"]["generation"] == candidate and row["baseline"]["generation"] == baseline]
        statuses = [row["regression_gate"]["status"] for row in cells]
        status = "fail" if "fail" in statuses else "pass" if statuses and all(value == "pass" for value in statuses) else "inconclusive"
        name = candidate + "_vs_" + baseline
        value = report["noninferiority"][name]
        audit.equal("noninferiority_status:" + name, value["status"], status)
        audit.equal("noninferiority_count:" + name, value["cell_count"], 15)
        audit.equal("noninferiority_expected_count:" + name, value["required_cell_count"], 15)
        audit.equal("noninferiority_all_cells:" + name, value["all_cells_present"], True)
        audit.equal("noninferiority_primary:" + name, value["primary"], (candidate, baseline) in primary)


'''
content = prefix + "\n\n" + pool + aggregate + '\nif __name__ == "__main__":\n    raise SystemExit(main())\n'
compile(content, str(out), "exec")
out.write_text(content, encoding="utf-8", newline="\n")
print(hashlib.sha256(out.read_bytes()).hexdigest())
