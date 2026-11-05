import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import ast
import hashlib
import json
from pathlib import Path

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
family_path = RUNS / "J6_joint_action_family_v1.json"
family = read(family_path)
end = read(RUNS / "J6_joint_plan_v1.finished.json")
assert end["status"] == "complete" and end["exit_code"] == 0
assert end["published_outputs_sha256"][str(family_path)] == sha(family_path)
assert family["role_run_counts"] == {"baseline": 600, "l1": 900, "j6": 900, "zero": 600}
assert len(family["manifest"]["raw_run_identities"]) == 3000
replacements = {
    "967281984c9621f6393cb54f7fcab9dcd78cdd9e5d392e5a25b3e840450a23f2": sha(RUNS / "j6_joint_driver_v1.py"),
    "8b60c0f75564545b2a40a4598454236082fa6fe58fbafb49f222995c51ceebfc": sha(family_path),
    "bf8bf4a6a158c0d56521c0674095fe5fe07107cb44c8746625ee1f394eeb7e11": sha(RUNS / "j6_validation_driver_v1.py"),
    "role_run_counts.cost": "role_run_counts.zero",
    "J6_joint_artifact_check_v1.json": "J6_joint_artifact_check_v2.json",
}
outputs = {}
for name in ("launch_j1_joint_run_v1.ps1", "launch_j1_joint_report_v1.ps1", "launch_j1_validation_v1.ps1", "j1_joint_progress_v1.py"):
    value = (RUNS / name).read_text(encoding="utf-8-sig").replace("J1", "J6").replace("j1", "j6")
    for old, new in replacements.items():
        value = value.replace(old, new)
    assert "J1" not in value and "j1" not in value and "role_run_counts.cost" not in value
    output = RUNS / name.replace("j1", "j6")
    if output.suffix == ".py":
        ast.parse(value)
    with output.open("x", encoding="utf-8-sig" if output.suffix == ".ps1" else "utf-8", newline="\n") as stream:
        stream.write(value)
    outputs[str(output)] = sha(output)
result = {"family_sha256": sha(family_path), "family_size": family["manifest"]["evaluation_family_size"], "outputs_sha256": outputs, "script_sha256": sha(__file__)}
with (RUNS / "J6_phase_launcher_preparation_v1.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, indent=2)
    stream.write("\n")
print(json.dumps(result))
