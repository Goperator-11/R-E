import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import json
from pathlib import Path

BASE = Path(r"C:\dev\codex_handoff\v33")
RUNS = BASE / "runs"
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
state_path = BASE / "state/LOOP_STATE.json"
state = read(state_path)
assert state["iterations"] == 22 and state["current"] == "L5"
launch = read(RUNS / "L5_collection_launch_v1.json")
task = state["tasks"]["L5"]
assert not task.get("active_computation")
active = {"kind": "CPU_development_collection", "status": "running", "driver_pid": launch["driver_pid"],
    "started_kst": launch["started_kst"], "launch_record": str(RUNS / "L5_collection_launch_v1.json"),
    "plan_path": launch["plan_path"], "plan_sha256": launch["plan_sha256"],
    "expected_finished_receipt": str(RUNS / "L5_full_v1.finished.json")}
task["active_computation"] = active
task["commits"] = [read(RUNS / "L5_collection_commit_receipt.json")["commit"]]
task["active_iteration_checkpoint"] = str(RUNS / "iter023_checkpoint_01.json")
task["candidate_adopted"] = False
task["note"] = "L5 상태9 완료 응답·혼합 후보와 single 진단을 동결하고1500실행을 수집 중이다. 역사 N·tail·목록 부재로 과거 관문은 미완료이며 성능 결과로 대체하지 않는다."
value = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "iteration": 23,
    "task": "L5", "active_computation": active, "commits": task["commits"],
    "checks": {"core": "329 passed, 524 subtests", "collector_observer": "52 passed", "smoke": "10 runs, 120 connections", "independent_response": "2270 checks"},
    "known_failures_preserved": ["L5_focused_01: collector read hct_ms instead of native world hct; corrected without changing world or policy criteria"],
    "historical_gate": "blocked_missing_inputs; old effective model6/6 and cert12000=>11 do not validate two new observation methods",
    "scope": "CPU independent development world; no physical measurement lock"}
with Path(task["active_iteration_checkpoint"]).open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(value, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps(value, ensure_ascii=False))
