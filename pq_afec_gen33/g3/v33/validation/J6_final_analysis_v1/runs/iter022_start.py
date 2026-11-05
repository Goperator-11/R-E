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
initial = read(RUNS / "iter022_preflight_initial.json")
assert state["iterations"] == 21 and state["current"] is None
task = state["tasks"]["J6"]
assert task["status"] == "partial" and task["iterations"] == 1
assert initial["guard_exit_code"] == 0 and not initial["measurement_lock"]
assert not (BASE / "state/MEASURE_LOCK.json").exists()
task["previous_iteration_checkpoint"] = task["active_iteration_checkpoint"]
task.update(status="doing", started_kst=initial["started_kst"], note="반복21의 고정116행동MC PID25680를 이어간다. 원래30셀과C1 감소 관문을 전체 보고·독립v2검사 뒤 판정한다.")
state["current"] = "J6"
path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
initial["read"] = ["LOOP_STATE full parse", "JOURNAL19-21 complete", "CONTEXT complete", "DECISIONS complete", "J6 card complete", "coverage A1-04/A4-03/A8-06 complete", "A1-04 verify complete; no A4-03/A8-06 verify match"]
initial["source_sha256"] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [BASE / "prompt/CONTEXT.md", BASE / "state/DECISIONS_NEEDED.md", ROOT / "docs/J6_preflight_budget.md", RUNS / "J6_joint_action_family_v1.json"]}
initial["audit_source_sha256"] = read(RUNS / "iter022_sources_sha256.json")
with (RUNS / "iter022_preflight.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(initial, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps({"iteration": 22, "task": "J6", "started_kst": initial["started_kst"], "driver_pid": task["active_computation"]["driver_pid"]}))
