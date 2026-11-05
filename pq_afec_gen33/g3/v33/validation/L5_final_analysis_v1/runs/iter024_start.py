import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path

BASE = Path(r"C:\dev\codex_handoff\v33")
RUNS = BASE / "runs"
ROOT = Path(r"C:\dev\pq_afec_gen33")
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
path = BASE / "state/LOOP_STATE.json"
state = read(path)
initial = read(RUNS / "iter024_preflight_initial.json")
assert state["iterations"] == 23 and state["current"] is None
task = state["tasks"]["L5"]
assert task["status"] == "partial" and task["iterations"] == 1
assert initial["guard_exit_code"] == 0 and not initial["measurement_lock"]
assert not (BASE / "state/MEASURE_LOCK.json").exists()
task["previous_iteration_checkpoint"] = task["active_iteration_checkpoint"]
task.update(status="doing", started_kst=initial["started_kst"], note="반복23의 고정118행동MC PID12044를 이어간다. 원래30셀·none/C1 B5/B6·역사 관문을 전체 보고·독립v3검사 뒤 판정한다.")
state["current"] = "L5"
path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
initial["read"] = ["LOOP_STATE full parse", "JOURNAL21-23 complete", "CONTEXT complete", "DECISIONS complete reread after truncated batch", "L common and L5 complete", "coverage A1-12/A2-11/A2r1-10/A4-01/A8-06 complete", "A1-12 verify complete"]
initial["source_sha256"] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [BASE / "prompt/CONTEXT.md", BASE / "state/DECISIONS_NEEDED.md", ROOT / "docs/L5_server_response.md", RUNS / "L5_joint_action_family_v1.json"]}
initial["audit_source_sha256"] = read(RUNS / "iter024_sources_sha256.json")
with (RUNS / "iter024_preflight.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(initial, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps({"iteration": 24, "task": "L5", "started_kst": initial["started_kst"], "driver_pid": task["active_computation"]["driver_pid"]}))
