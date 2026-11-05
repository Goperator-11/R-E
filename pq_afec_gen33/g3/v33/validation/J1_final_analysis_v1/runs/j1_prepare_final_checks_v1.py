import sys
sys.dont_write_bytecode = True
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

text = (RUNS / "j1_analysis_check_v1.py").read_text(encoding="utf-8")
text = text.replace('"test_v33_learning_report.py"]', '"test_v33_learning_report.py", "test_v33_j1_findings.py"]')
text = text.replace('names = [', 'names = [str(RUNS / "j1_findings_extract_v1.py"), str(RUNS / "j1_joint_driver_v1.py"), ')
write(RUNS / "j1_final_checks_v1.py", text)
text = (RUNS / "l3_checkpoint_phase_v1.py").read_text(encoding="utf-8").replace('l3', 'j1').replace('L3', 'J1')
text = text.replace('67aed72df6ae0d1ce2bdc55392efa14d5a5377e2..HEAD', 'c81bbdf2dd17348a3a36707b3013ee3451fd97d2..HEAD')
write(RUNS / "j1_checkpoint_phase_v1.py", text)
text = (RUNS / "l3_validation_driver_v1.py").read_text(encoding="utf-8").replace('l3', 'j1').replace('L3', 'J1')
text = re.sub(r'CHECKER_SHA = "[0-9a-f]+"', 'CHECKER_SHA = ' + repr(sha(RUNS / "j1_joint_artifact_check_v1.py")), text)
text = text.replace('command = [sys.executable, "-I", "-B", str(CHECKER), "--out", str(OUT)]',
    'family_path = RUNS / "J1_joint_action_family_v1.json"\n    command = [sys.executable, "-I", "-B", str(CHECKER), "--out", str(OUT), "--family-sha256", sha(family_path)]')
text = text.replace('inputs = {str(report_end): sha(report_end), **end["published_outputs_sha256"]}', 'inputs = {str(report_end): sha(report_end), str(family_path): sha(family_path), **end["published_outputs_sha256"]}')
write(RUNS / "j1_validation_driver_v1.py", text)
print("J1 final check and phase record scripts prepared")
