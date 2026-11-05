import sys
sys.dont_write_bytecode = True
import hashlib
from pathlib import Path


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
source = (RUNS / "l2_joint_artifact_check_v3.py").read_text(encoding="utf-8")
source = source.replace("L2", "L3").replace("l2", "l3")


def replace(old, new):
    global source
    assert old in source, old
    source = source.replace(old, new)


replace("b793aa7df0a831195c2ba54d4f97fb0013c1792edf81946e58b3c00ae1249853", sha(RUNS / "L3_joint_action_family_v1.json"))
replace("d90449ae24665ac622c783804bc2afb048529882661098a856fdd5a50cedde96", sha(ROOT / "experiments/v33/bench_learning_l3_report.py"))
replace("4e9d93ffb6f40b12ded8c1b46ca7ba68f23cb74df528c245f0ce8a66a503d67b", sha(RUNS / "l3_joint_driver_v1.py"))
replace('SELF_SHA = file_hash(__file__)', '''MONITOR_HELPER = RUNS / "l3_monitor_audit_v1.py"
MONITOR_HELPER_SHA = "''' + sha(RUNS / "l3_monitor_audit_v1.py") + '''"
assert file_hash(MONITOR_HELPER) == MONITOR_HELPER_SHA
monitor_spec = importlib.util.spec_from_file_location("independent_monitor_arithmetic", MONITOR_HELPER)
monitor_helper = importlib.util.module_from_spec(monitor_spec)
monitor_spec.loader.exec_module(monitor_helper)
SELF_SHA = file_hash(__file__)''')
replace('"l3" if job["policy"] == "L3_v1" else "fixed"', '{"L3_v1": "l3", "L3_guard_only_v1": "guard", "L3_record_only_v1": "record", "L3_beta_only_v1": "beta"}[job["policy"]]')
replace('"fixed_none", "fixed_c1"', '"guard_c1", "record_c1", "beta_c1"')
replace('("baseline", "l1", "l3", "fixed")', '("baseline", "l1", "l3", "guard", "record", "beta")')
first, last = source.index("def posterior_moments("), source.index("def verify(audit):")
source = source[:first] + source[last:]
replace('    receipts = driver_receipts(audit)', '    audit.file(MONITOR_HELPER, MONITOR_HELPER_SHA)\n    receipts = driver_receipts(audit)')
replace('epsilon_counts = check_epsilon(audit, report, groups)', 'monitor_counts = monitor_helper.check_monitors(audit, report, groups, check_seed_summary, check_gate)')
replace('"epsilon": epsilon_counts', '"monitor": monitor_counts')
replace("gate and EPS moment checks", "gate and predecision monitor arithmetic checks")
replace('audit.equal("job_count", len(jobs), 100)', 'audit.equal("job_count", len(jobs), manifest["evaluation_family_size"])\n    audit.equal("unique_jobs", len(jobs), len(manifest["jobs"]))')
replace('end["evaluation_family_size"], 100', 'end["evaluation_family_size"], len(jobs)')
replace('(2 * 100)', '(2 * len(jobs))')
replace('("evaluation_family_size", 100)', '("evaluation_family_size", len(jobs))')
replace('"evaluation_family_size": 100', '"evaluation_family_size": len(jobs)')
replace('audit.equal("MC_job_count", len(partition["mc"]), 84)\n    audit.equal("structural_job_count", len(partition["structural"]), 16)',
        'audit.equal("whole_partition", sorted(partition["mc"] + partition["structural"]), sorted(jobs))')
replace('"MC_jobs": 84, "structural_jobs": 16', '"MC_jobs": len(partition["mc"]), "structural_jobs": len(partition["structural"])')
replace('len(actual), 150', 'len(actual), 165')
replace('    pairs += [("l3_" + mode, "fixed_" + mode) for mode in ("none", "c1")]\n    pairs += [("fixed_" + mode, "l1_" + mode) for mode in ("none", "c1")]',
        '    pairs += [("guard_c1", "l1_c1"), ("record_c1", "guard_c1"), ("beta_c1", "record_c1"), ("l3_c1", "beta_c1")]')
replace(', ("l3_c1", "v32")}', '}')
replace('        audit.equal("comparison_primary:" + label, row["primary"], (candidate, baseline) in primary)',
        '        audit.equal("comparison_primary:" + label, row["primary"], (candidate, baseline) in primary)\n        kind = "ablation_step_contrast" if (candidate, baseline) in pairs[-4:] else "direct_previous_policy" if baseline.startswith("l1_") else "legacy_or_mode_contrast"\n        audit.equal("comparison_kind:" + label, row["kind"], kind)')
with (RUNS / "l3_joint_artifact_check_v1.py").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(source)
