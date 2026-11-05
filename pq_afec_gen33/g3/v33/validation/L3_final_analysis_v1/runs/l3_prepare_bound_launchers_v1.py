import sys
sys.dont_write_bytecode = True
import hashlib
import json
from pathlib import Path


RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
read = lambda path: json.loads(path.read_text(encoding="utf-8"))
family_path = RUNS / "L3_joint_action_family_v1.json"
receipt = read(RUNS / "L3_joint_plan_v1.finished.json")
assert receipt["status"] == "complete" and receipt["exit_code"] == 0
assert receipt["published_outputs_sha256"][str(family_path)] == sha(family_path)
family = read(family_path)
assert family["role_run_counts"] == {"baseline": 600, "l1": 900, "l3": 900, "guard": 300, "record": 300, "beta": 300}
assert len(family["manifest"]["raw_run_identities"]) == 3300
assert len(family["comparisons"]) == 14 and len(family["primary_comparisons"]) == 3
for phase in ("run", "report"):
    source = (RUNS / ("launch_l2_joint_" + phase + "_v1.ps1")).read_text(encoding="utf-8")
    replacements = [
        ("4e9d93ffb6f40b12ded8c1b46ca7ba68f23cb74df528c245f0ce8a66a503d67b", sha(RUNS / "l3_joint_driver_v1.py")),
        ("b793aa7df0a831195c2ba54d4f97fb0013c1792edf81946e58b3c00ae1249853", sha(family_path)),
        ("L2", "L3"), ("l2", "l3")]
    if phase == "run":
        replacements += [
            ("$family.role_run_counts.fixed -ne 600", "$family.role_run_counts.guard -ne 300 -or $family.role_run_counts.record -ne 300 -or $family.role_run_counts.beta -ne 300"),
            (".Count -ne 3000", ".Count -ne 3300")]
    for old, new in replacements:
        assert old in source, old
        source = source.replace(old, new)
    with (RUNS / ("launch_l3_joint_" + phase + "_v1.ps1")).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(source)
