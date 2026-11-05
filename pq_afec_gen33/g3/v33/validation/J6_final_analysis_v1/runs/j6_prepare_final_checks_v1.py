import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
from pathlib import Path
import re

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

def write(path, text):
    assert not path.exists()
    compile(text, str(path), "exec")
    path.write_text(text, encoding="utf-8", newline="\n")

text = (RUNS / "j1_findings_extract_v1.py").read_text(encoding="utf-8").replace("j1", "j6").replace("J1", "J6")
text = text.replace("J6_joint_artifact_check_v1.json", "J6_joint_artifact_check_v2.json")
text = text.replace('        historical_sha256=sha(RUNS / "J6_historical_reference_v1.json"), w0_sha256=sha(RUNS / "J6_w0_error_table_v1.json"),', '        preflight_fixture_sha256=sha(RUNS / "J6_preflight_fixture_check_v2.json"),')
text = text.replace("No cost-only substitution", "No zero-margin substitution")
write(RUNS / "j6_findings_extract_v1.py", text)
text = (ROOT / "tests/test_v33_j1_findings.py").read_text(encoding="utf-8").replace("j1", "j6").replace("J1", "J6")
write(ROOT / "tests/test_v33_j6_findings.py", text)
text = (RUNS / "j6_analysis_check_v1.py").read_text(encoding="utf-8")
text = text.replace('"test_v33_learning_report.py"]', '"test_v33_learning_report.py", "test_v33_j6_findings.py"]')
text = text.replace('names = [', 'names = [str(RUNS / "j6_findings_extract_v1.py"), str(RUNS / "j6_joint_driver_v1.py"), ')
write(RUNS / "j6_final_checks_v1.py", text)
text = (RUNS / "j1_checkpoint_phase_v1.py").read_text(encoding="utf-8").replace("j1", "j6").replace("J1", "J6")
text = text.replace("c81bbdf2dd17348a3a36707b3013ee3451fd97d2..HEAD", "e94961a4f472bc043374cb0ec15034583acc2f34..HEAD")
write(RUNS / "j6_checkpoint_phase_v1.py", text)
text = (RUNS / "j1_validation_driver_v1.py").read_text(encoding="utf-8").replace("j1", "j6").replace("J1", "J6")
text = text.replace("j6_joint_artifact_check_v1.py", "j6_joint_artifact_check_v2.py").replace("J6_joint_artifact_check_v1.json", "J6_joint_artifact_check_v2.json")
text = re.sub(r"CHECKER_SHA = ['\"][0-9a-f]+['\"]", "CHECKER_SHA = " + repr(sha(RUNS / "j6_joint_artifact_check_v2.py")), text)
write(RUNS / "j6_validation_driver_v1.py", text)
text = (RUNS / "launch_j1_joint_plan_v1.ps1").read_text(encoding="utf-8-sig").replace("j1", "j6").replace("J1", "J6")
text = text.replace(sha(RUNS / "j1_joint_driver_v1.py"), sha(RUNS / "j6_joint_driver_v1.py"))
text = text.replace(sha(RUNS / "J1_full_v1_plan.json"), sha(RUNS / "J6_full_v1_plan.json"))
with (RUNS / "launch_j6_joint_plan_v1.ps1").open("x", encoding="utf-8-sig", newline="\n") as stream:
    stream.write(text)
print("prepared J6 findings, validation and plan phase")
