import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path

BASE = Path(r"C:\dev\codex_handoff\v33")
RUNS = BASE / "runs"
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
path = BASE / "state/LOOP_STATE.json"
state = read(path)
initial = read(RUNS / "iter023_preflight_initial.json")
assert state["iterations"] == 22 and state["current"] is None
task = state["tasks"]["L5"]
assert task["status"] == "todo" and task["iterations"] == 0
assert initial["guard_exit_code"] == 0 and not initial["measurement_lock"]
assert not (BASE / "state/MEASURE_LOCK.json").exists()
task.update(status="doing", started_kst=initial["started_kst"], note="완료 수신 index 관측과 두 S 산출법, 변화·혼합 규칙을 성능 실행 전에 고정한다. 과거 자료의 N·tail 부재를 임의 값으로 채우지 않는다.")
state["current"] = "L5"
path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
initial["read"] = ["LOOP_STATE full parse", "JOURNAL20-22 complete", "CONTEXT complete", "DECISIONS complete", "L common and L5 complete", "coverage A1-12/A2-11/A2r1-10/A4-01/A8-06 complete", "verify A1-12 complete; other exact IDs absent", "L5 preparation and J6 handoff notes complete"]
initial["source_sha256"] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [BASE / "prompt/CONTEXT.md", BASE / "prompt/TASKS.md", BASE / "state/DECISIONS_NEEDED.md", RUNS / "L5_preparation.md", RUNS / "L5_reading_during_J6_v1.md", RUNS / "J6_L5_history_availability_note_v2.md", RUNS / "J6_L5_p13_fit_note_v1.md"]}
initial["audit_source_sha256"] = read(RUNS / "iter023_sources_sha256.json")
with (RUNS / "iter023_preflight.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(initial, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps({"iteration": 23, "task": "L5", "started_kst": initial["started_kst"]}))
