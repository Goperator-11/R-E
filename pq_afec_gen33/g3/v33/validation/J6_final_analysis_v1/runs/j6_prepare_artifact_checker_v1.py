import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
from pathlib import Path
import re

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

def write(path, value):
    assert not path.exists(), path
    compile(value, str(path), "exec")
    path.write_text(value, encoding="utf-8", newline="\n")

helper = (RUNS / "j6_preflight_audit_v1.py").read_text(encoding="utf-8")
helper = helper.replace("import json\n", "import json\nimport math\n")
helper = helper.replace("type(time) in (int, float) and time >= 0", "type(time) in (int, float) and math.isfinite(time) and time >= 0")
write(RUNS / "j6_preflight_audit_v2.py", helper)
grade = (RUNS / "j1_grade_audit_v1.py").read_text(encoding="utf-8").replace('("j1", "cost")', '("j6", "zero")')
write(RUNS / "j6_grade_audit_v1.py", grade)
value = (RUNS / "j1_joint_artifact_check_v1.py").read_text(encoding="utf-8").replace("j1", "j6").replace("J1", "J6")
value = value.replace("tail_likelihood_contrast", "margin_contrast").replace("tail_cost_contrast", "preflight_context_contrast")
value = value.replace('"cost"', '"zero"').replace('"cost_', '"zero_')
for key, path in (("REPORTER_SHA", ROOT / "experiments/v33/bench_learning_j6_report.py"),
                  ("DRIVER_SHA", RUNS / "j6_joint_driver_v1.py"), ("GRADE_SHA", RUNS / "j6_grade_audit_v1.py")):
    value = re.sub(key + r" = ['\"][0-9a-f]+['\"]", key + " = " + repr(sha(path)), value)
anchor = "grade_spec.loader.exec_module(grade)"
addition = '\nPREFLIGHT_PATH = RUNS / "j6_preflight_audit_v2.py"\nPREFLIGHT_SHA = ' + repr(sha(RUNS / "j6_preflight_audit_v2.py")) + '''
assert file_hash(PREFLIGHT_PATH) == PREFLIGHT_SHA
preflight_spec = importlib.util.spec_from_file_location("independent_preflight", PREFLIGHT_PATH)
preflight_audit = importlib.util.module_from_spec(preflight_spec)
preflight_spec.loader.exec_module(preflight_audit)
'''
value = value.replace(anchor, anchor + addition)
value = value.replace('    grade_counts = grade.check_runs(audit, groups)', '    grade_counts = grade.check_runs(audit, groups)\n    audit.file(PREFLIGHT_PATH, PREFLIGHT_SHA)\n    preflight_counts = preflight_audit.check_runs(audit, groups, protocol)')
value = value.replace('"grade_audit": grade_counts,', '"grade_audit": grade_counts, "preflight_audit": preflight_counts,')
value = value.replace("and update-population checks.", "update-population and causal preflight-budget checks. S selection uses preserved legacy_y.")
write(RUNS / "j6_joint_artifact_check_v1.py", value)
fixture = (RUNS / "j1_checker_fixture_check_v1.py").read_text(encoding="utf-8").replace("j1", "j6").replace("J1", "J6")
fixture = fixture.replace('"cost"', '"zero"').replace('"cost_only"', '"margin_zero"')
fixture = fixture.replace("plus five smoke grade traces", "plus ten smoke grade traces")
write(RUNS / "j6_checker_fixture_check_v1.py", fixture)
print(sha(RUNS / "j6_joint_artifact_check_v1.py"))
