import sys
sys.dont_write_bytecode = True
import hashlib
from pathlib import Path
import re

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
source = (RUNS / "l2_joint_artifact_check_v3.py").read_text(encoding="utf-8")
value = source.replace('l2', 'j1').replace('L2', 'J1').replace('"fixed"', '"cost"').replace('fixed_', 'cost_')
value = re.sub(r'FAMILY_SHA = "[0-9a-f]+"', 'FAMILY_SHA = None', value)
value = re.sub(r'REPORTER_SHA = "[0-9a-f]+"', 'REPORTER_SHA = ' + repr(sha(ROOT / "experiments/v33/bench_learning_j1_report.py")), value)
value = re.sub(r'DRIVER_SHA = "[0-9a-f]+"', 'DRIVER_SHA = ' + repr(sha(RUNS / "j1_joint_driver_v1.py")), value)
anchor = 'SELF_SHA = file_hash(__file__)'
helper = 'GRADE_PATH = RUNS / "j1_grade_audit_v1.py"\nGRADE_SHA = ' + repr(sha(RUNS / "j1_grade_audit_v1.py")) + '\nassert file_hash(GRADE_PATH) == GRADE_SHA\ngrade_spec = importlib.util.spec_from_file_location("independent_j1_grade", GRADE_PATH)\ngrade = importlib.util.module_from_spec(grade_spec)\ngrade_spec.loader.exec_module(grade)\n'
value = value.replace(anchor, anchor + '\n' + helper)
start, end = value.index('def posterior_moments('), value.index('def verify(')
value = value[:start] + value[end:]
value = value.replace('    epsilon_counts = check_epsilon(audit, report, groups)', '    audit.file(GRADE_PATH, GRADE_SHA)\n    grade_counts = grade.check_runs(audit, groups)')
value = value.replace('"epsilon": epsilon_counts', '"grade_audit": grade_counts').replace('gate and EPS moment checks', 'gate, fixed-EPS, observation-grade and update-population checks')
value = value.replace('def main(argv=None):\n', 'def main(argv=None):\n    global FAMILY_SHA\n')
value = value.replace('    args = parser.parse_args(argv)', '    parser.add_argument("--family-sha256", required=True)\n    args = parser.parse_args(argv)\n    if re.fullmatch(r"[0-9a-f]{64}", args.family_sha256) is None:\n        raise ValueError("invalid family hash")\n    FAMILY_SHA = args.family_sha256')
value = value.replace('audit.equal("job_count", len(jobs), 100)', 'family_size = manifest["evaluation_family_size"]\n    audit.equal("job_count", len(jobs), family_size)')
value = value.replace('end["evaluation_family_size"], 100)', 'end["evaluation_family_size"], family_size)')
value = value.replace('(2 * 100)', '(2 * family_size)').replace('("evaluation_family_size", 100)', '("evaluation_family_size", family_size)').replace('"evaluation_family_size": 100}', '"evaluation_family_size": family_size}')
value = value.replace('    audit.equal("MC_job_count", len(partition["mc"]), 84)\n    audit.equal("structural_job_count", len(partition["structural"]), 16)', '    audit.equal("complete_job_partition", sorted(partition["mc"] + partition["structural"]), sorted(jobs))')
value = value.replace('"MC_jobs": 84, "structural_jobs": 16', '"MC_jobs": len(partition["mc"]), "structural_jobs": len(partition["structural"])')
value = value.replace('primary = {("j1_none", "l1_none"), ("j1_c1", "l1_c1"), ("j1_c1", "v31"), ("j1_c1", "v32")}', 'primary = {("j1_none", "l1_none"), ("j1_c1", "l1_c1")}')
anchor = '        audit.equal("comparison_primary:" + label, row["primary"], (candidate, baseline) in primary)'
value = value.replace(anchor, anchor + '\n        expected_kind = "tail_likelihood_contrast" if baseline.startswith("cost_") else "tail_cost_contrast" if candidate.startswith("cost_") else "direct_previous_policy" if baseline.startswith("l1_") else "legacy_or_mode_contrast"\n        audit.equal("comparison_kind:" + label, row["kind"], expected_kind)')
target = RUNS / "j1_joint_artifact_check_v1.py"
assert not target.exists()
compile(value, str(target), "exec")
target.write_text(value, encoding="utf-8", newline="\n")
print(sha(target))
