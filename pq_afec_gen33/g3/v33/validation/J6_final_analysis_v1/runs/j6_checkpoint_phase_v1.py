import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import json
from pathlib import Path
import subprocess


BASE = Path(r"C:\dev\codex_handoff\v33")
ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = BASE / "runs"
phase, label = sys.argv[1:]
assert phase in ("plan", "run", "report", "validation")
assert label.startswith("iter") and label.endswith(".json") and Path(label).name == label
prefix = "J6_validation" if phase == "validation" else "J6_joint_" + phase
launch_path = RUNS / (prefix + "_launch_v1.json")
read = lambda p: json.loads(p.read_text(encoding="utf-8"))
launch = read(launch_path)
state_path = BASE / "state/LOOP_STATE.json"
state = read(state_path)
assert state["current"] == "J6" and state["tasks"]["J6"]["status"] == "doing"
task = state["tasks"]["J6"]
old = task.get("active_computation")
if old:
    end_path = Path(old["expected_finished_receipt"])
    end = read(end_path)
    assert end["status"] == "complete" and end.get("exit_code", 0) == 0
    old.update(status="complete", ended_kst=end["ended_kst"], completion_receipt=str(end_path))
    completed = task.setdefault("completed_computations", [])
    assert all(row.get("launch_record") != old["launch_record"] for row in completed)
    completed.append(old)
kind = {"plan": "CPU_development_input_validation", "run": "CPU_development_MC", "report": "CPU_development_report", "validation": "CPU_development_independent_validation"}[phase]
active = {"kind": kind, "status": "running", "driver_pid": launch["driver_pid"], "started_kst": launch["started_kst"],
          "launch_record": str(launch_path), "expected_finished_receipt": str(RUNS / (prefix + "_v1.finished.json"))}
for key in ("family_path", "family_sha256"):
    if key in launch:
        active[key] = launch[key]
task["active_computation"] = active
task["commits"] = subprocess.check_output(["git", "-C", str(ROOT), "rev-list", "--reverse", "e94961a4f472bc043374cb0ec15034583acc2f34..HEAD"], text=True).split()
path = RUNS / label
value = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "iteration": state["iterations"] + 1,
         "task": "J6", "phase": phase, "active_computation": active, "commits": task["commits"],
         "note": "Existing finite phase is running; do not restart. Adoption requires complete report and independent validation."}
with path.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(value, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
task["active_iteration_checkpoint"] = str(path)
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps(value))
