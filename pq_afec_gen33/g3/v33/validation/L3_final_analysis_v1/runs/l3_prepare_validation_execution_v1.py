import sys
sys.dont_write_bytecode = True
import hashlib
from pathlib import Path


RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
source = (RUNS / "l2_validation_driver_v2.py").read_text(encoding="utf-8")
source = source.replace("L2", "L3").replace("l2", "l3")
replacements = [
    ("l3_joint_artifact_check_v3.py", "l3_joint_artifact_check_v1.py"),
    ("L3_joint_artifact_check_v3.json", "L3_joint_artifact_check_v1.json"),
    ("05a4a8c51ef3d57ef36ed170d8910f8080750994d4fd21632ad3144309c7e6f1", sha(RUNS / "l3_joint_artifact_check_v1.py")),
    ("L3_validation_v2", "L3_validation_v1")]
for old, new in replacements:
    assert old in source, old
    source = source.replace(old, new)
with (RUNS / "l3_validation_driver_v1.py").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(source)
source = (RUNS / "launch_l2_validation_v2.ps1").read_text(encoding="utf-8")
replacements = [
    ("69f5338edf3494433a9c10080b7adb04d0616217c590d429312766e2ef7fbe9e", sha(RUNS / "l3_validation_driver_v1.py")),
    ("L2_joint_artifact_check_v3.json", "L3_joint_artifact_check_v1.json"),
    ("L2", "L3"), ("l2", "l3"), ("v2", "v1")]
for old, new in replacements:
    assert old in source, old
    source = source.replace(old, new)
with (RUNS / "launch_l3_validation_v1.ps1").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(source)
source = (RUNS / "l2_joint_progress_v1.py").read_text(encoding="utf-8").replace("L2", "L3").replace("l2", "l3")
assert "b793aa7df0a831195c2ba54d4f97fb0013c1792edf81946e58b3c00ae1249853" in source
source = source.replace("b793aa7df0a831195c2ba54d4f97fb0013c1792edf81946e58b3c00ae1249853", sha(RUNS / "L3_joint_action_family_v1.json"))
with (RUNS / "l3_joint_progress_v1.py").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(source)
