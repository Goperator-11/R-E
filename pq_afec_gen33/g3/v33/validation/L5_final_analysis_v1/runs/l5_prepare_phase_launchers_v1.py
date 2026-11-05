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
family_path = RUNS / "L5_joint_action_family_v1.json"
family = read(family_path)
end = read(RUNS / "L5_joint_plan_v1.finished.json")
assert end["status"] == "complete" and end["exit_code"] == 0
assert end["published_outputs_sha256"][str(family_path)] == sha(family_path)
assert family["role_run_counts"] == {"baseline": 600, "l1": 900, "l5": 900, "single": 600}
assert len(family["manifest"]["raw_run_identities"]) == 3000
replacements = {
    "31d6c7ecab527e026cf5619cd22f9d57c6ac2e01990d33ca33f4d2e0d9eeb981": sha(RUNS / "l5_joint_driver_v1.py"),
    "f39e2c068b365bfbc73ee8a3927c5ed738b6e94e89bf7c019919a6876b150c86": sha(family_path),
    "role_run_counts.zero": "role_run_counts.single",
}
outputs = {}
for name in ("launch_j6_joint_run_v1.ps1", "launch_j6_joint_report_v1.ps1", "j6_joint_progress_v1.py"):
    value = (RUNS / name).read_text(encoding="utf-8-sig").replace("J6", "L5").replace("j6", "l5")
    for old, new in replacements.items():
        value = value.replace(old, new)
    output = RUNS / name.replace("j6", "l5")
    if output.suffix == ".py":
        ast.parse(value)
    with output.open("x", encoding="utf-8-sig" if output.suffix == ".ps1" else "utf-8", newline="\n") as stream:
        stream.write(value)
    outputs[str(output)] = sha(output)
value = {"family_sha256": sha(family_path), "family_size": family["manifest"]["evaluation_family_size"], "outputs_sha256": outputs, "script_sha256": sha(__file__)}
with (RUNS / "L5_phase_launcher_preparation_v1.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(value, stream, indent=2)
    stream.write("\n")
print(json.dumps(value))
