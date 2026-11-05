import sys
sys.dont_write_bytecode = True
import ast
import hashlib
from pathlib import Path

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(name, code):
    if name.endswith(".py"):
        ast.parse(code)
    with (RUNS / name).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(code)

helper = (RUNS / "l5_response_audit_v2.py").read_text(encoding="utf-8")
helper = helper.replace('    totals = Counter()\n', '    totals = Counter()\n    scenarios = {row["id"]: row for row in protocol["scenarios"]}\n')
helper = helper.replace('value = audit_rows(rows, variant="single" if run["analysis_role"] == "single" else "full")', 'value = audit_rows(rows, variant="single" if run["analysis_role"] == "single" else "full",\n                reset_each_connection=scenarios[run["scenario"]]["reset_each_connection"])')
helper = helper.replace('audit.equal("response_final_state:" + label + observed, run["final_state"][observed], value[expected])', 'audit.check("response_final_state:" + label + observed, run["final_state"][observed] == value[expected])')
save("l5_response_audit_v3.py", helper)
checker = (RUNS / "l5_joint_artifact_check_v2.py").read_text(encoding="utf-8").replace("l5_response_audit_v2.py", "l5_response_audit_v3.py")
checker = checker.replace(sha(RUNS / "l5_response_audit_v2.py"), sha(RUNS / "l5_response_audit_v3.py"))
save("l5_joint_artifact_check_v3.py", checker)
driver = (RUNS / "l5_validation_driver_v1.py").read_text(encoding="utf-8").replace("l5_joint_artifact_check_v2.py", "l5_joint_artifact_check_v3.py").replace("L5_joint_artifact_check_v2.json", "L5_joint_artifact_check_v3.json")
driver = driver.replace(sha(RUNS / "l5_joint_artifact_check_v2.py"), sha(RUNS / "l5_joint_artifact_check_v3.py"))
save("l5_validation_driver_v2.py", driver)
launcher = (RUNS / "launch_l5_validation_v1.ps1").read_text(encoding="utf-8-sig").replace("l5_validation_driver_v1.py", "l5_validation_driver_v2.py").replace("L5_joint_artifact_check_v2.json", "L5_joint_artifact_check_v3.json")
launcher = launcher.replace(sha(RUNS / "l5_validation_driver_v1.py"), sha(RUNS / "l5_validation_driver_v2.py"))
save("launch_l5_validation_v2.ps1", launcher)
fixture = (RUNS / "l5_response_fixture_check_v3.py").read_text(encoding="utf-8").replace("l5_joint_artifact_check_v2.py", "l5_joint_artifact_check_v3.py").replace("L5_response_fixture_check_v3.json", "L5_response_fixture_check_v4.json")
fixture = fixture.replace('checker.response_audit.check_runs(audit, groups, {})', 'checker.response_audit.check_runs(audit, groups, {"scenarios": [{"id": key[1], "reset_each_connection": False} for key in groups]})')
marker = 'mutations = []'
fixture = fixture.replace(marker, '''cold_rows = [copy.deepcopy(samples[0]) for _ in range(3)]
for index, row in enumerate(cold_rows):
    row["index"] = index
cold_result = checker.response_audit.audit_rows(cold_rows, variant="full", reset_each_connection=True)
assert cold_result["size_updates"] == 3 and cold_result["final_window_count"] == 1
try:
    checker.response_audit.audit_rows(cold_rows, variant="full", reset_each_connection=False)
except ValueError:
    pass
else:
    raise AssertionError("cold destination sequence incorrectly retained history")
''' + marker)
save("l5_response_fixture_check_v4.py", fixture)
for old, new in (("l5_checker_fixture_check_v2.py", "l5_checker_fixture_check_v3.py"), ("l5_adaptation_fixture_check_v3.py", "l5_adaptation_fixture_check_v4.py")):
    code = (RUNS / old).read_text(encoding="utf-8").replace("l5_joint_artifact_check_v2.py", "l5_joint_artifact_check_v3.py")
    code = code.replace(Path(old).stem.replace("l5_", "L5_") + ".json", Path(new).stem.replace("l5_", "L5_") + ".json")
    save(new, code)
for old, new in (("l5_findings_extract_v1.py", "l5_findings_extract_v2.py"), ("l5_revert_candidate_v1.py", "l5_revert_candidate_v2.py")):
    code = (RUNS / old).read_text(encoding="utf-8").replace("L5_joint_artifact_check_v2.json", "L5_joint_artifact_check_v3.json")
    code = code.replace("L5_response_fixture_check_v3.json", "L5_response_fixture_check_v4.json").replace("L5_adaptation_fixture_check_v3.json", "L5_adaptation_fixture_check_v4.json")
    save(new, code)
test = ROOT / "tests/test_v33_l5_findings.py"
test.write_text(test.read_text(encoding="utf-8").replace("l5_findings_extract_v1.py", "l5_findings_extract_v2.py"), encoding="utf-8", newline="\n")
code = (RUNS / "l5_finish_check_v1.py").read_text(encoding="utf-8").replace("l5_findings_extract_v1.py", "l5_findings_extract_v2.py").replace("l5_revert_candidate_v1.py", "l5_revert_candidate_v2.py").replace("L5_finish_check_v1", "L5_finish_check_v2")
save("l5_finish_check_v2.py", code)
