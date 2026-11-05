import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import ast
import hashlib
from pathlib import Path

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
value = (RUNS / "j1_final_bundle_v1.py").read_text(encoding="utf-8").replace("J1", "J6").replace("j1", "j6")
changes = {
    "49854f577ac0fd344f78f93bb207cadb48144f3ee20cb948de1f7c4f89e1f390": sha(RUNS / "j6_joint_artifact_check_v2.py"),
    "71a0763e3262fba7627a1bd7383cd88dabbc04623975d0094cc1b21d44dc51d2": sha(RUNS / "j6_findings_extract_v1.py"),
    "8b60c0f75564545b2a40a4598454236082fa6fe58fbafb49f222995c51ceebfc": sha(RUNS / "J6_joint_action_family_v1.json"),
    "j6_joint_artifact_check_v1.py": "j6_joint_artifact_check_v2.py",
    "J6_joint_artifact_check_v1.json": "J6_joint_artifact_check_v2.json",
    '"iter020_*", "iter021_*", "iter022_*"': '"iter021_*", "iter022_*", "iter023_*"',
}
for old, new in changes.items():
    assert old in value, old
    value = value.replace(old, new)
ast.parse(value)
path = RUNS / "j6_final_bundle_v1.py"
with path.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(value)
print(sha(path))
