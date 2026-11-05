import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import json
from pathlib import Path


BASE = Path(r"C:\dev\codex_handoff\v33")
path = BASE / "state/LOOP_STATE.json"
state = json.loads(path.read_text(encoding="utf-8"))
initial = json.loads((BASE / "runs/iter019_preflight_initial.json").read_text(encoding="utf-8"))
assert state["iterations"] == 18 and state["current"] is None and state["tasks"]["L3"]["status"] == "partial"
assert initial["guard_exit_code"] == 0 and not initial["measurement_lock"]
task = state["tasks"]["L3"]
assert task["active_computation"] == initial["active_computation"]
task.update(status="doing", started_kst=initial["started_kst"])
task["previous_iteration_checkpoint"] = task.pop("active_iteration_checkpoint")
state["current"] = "L3"
path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
initial["read"] = ["LOOP_STATE complete", "JOURNAL16-18", "CONTEXT complete", "DECISIONS complete", "L common and L3 full card", "all11 mapped audits, verify-A7 notes and Q23 source"]
with (BASE / "runs/iter019_preflight.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(initial, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps({"iteration": 19, "task": "L3", "started_kst": initial["started_kst"], "driver_pid": task["active_computation"]["driver_pid"]}))
