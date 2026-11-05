import sys
sys.dont_write_bytecode = True
import hashlib
from pathlib import Path

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
text = (RUNS / "launch_l3_joint_plan_v1.ps1").read_text(encoding="utf-8-sig").replace('l3', 'j1').replace('L3', 'J1')
old_driver = sha(RUNS / "l3_joint_driver_v1.py")
assert old_driver in text
text = text.replace(old_driver, sha(RUNS / "j1_joint_driver_v1.py"))
text = text.replace(' -ne 90', ' -ne 75')
text = text.replace('4e48e8d951fe1b9b6ce24babb1119775eb49d4e45bf2964be1d6152da31fb9c5', sha(RUNS / "J1_full_v1_plan.json"))
path = RUNS / "launch_j1_joint_plan_v1.ps1"
assert not path.exists()
path.write_text(text, encoding="utf-8-sig", newline="\n")
print(sha(path))
