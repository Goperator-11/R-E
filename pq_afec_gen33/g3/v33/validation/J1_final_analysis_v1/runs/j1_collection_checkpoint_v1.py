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
assert state["iterations"] == 19 and state["current"] == "J1"
launch = read(RUNS / "J1_collection_launch_v1.json")
task = state["tasks"]["J1"]
assert not task.get("active_computation")
active = {"kind": "CPU_development_collection", "status": "running", "driver_pid": launch["driver_pid"],
    "started_kst": launch["started_kst"], "launch_record": str(RUNS / "J1_collection_launch_v1.json"),
    "plan_path": launch["plan_path"], "plan_sha256": launch["plan_sha256"],
    "expected_finished_receipt": str(RUNS / "J1_full_v1.finished.json")}
task["active_computation"] = active
task["commits"] = [read(RUNS / "J1_collection_commit_receipt.json")["commit"]]
task["active_iteration_checkpoint"] = str(RUNS / "iter020_checkpoint_01.json")
task["note"] = "J1 상태7 후보와 비용만 보정한 진단 사본을 동결하고 전체1500실행을 수집 중이다. 활성 후보는 아직 미채택이며 성능 판정 뒤 실패·미확정이면 L1으로 복구한다."
value = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "iteration": 20,
    "task": "J1", "active_computation": active, "commits": task["commits"],
    "checks": {"core": "256 passed, 464 subtests", "collector": "63 passed, 17 subtests", "smoke": "5 runs, 60 connections", "historical": "20 groups, 480 normalization cases"},
    "known_failures_preserved": ["J1_check_01 model-world atoms omitted tail and float equality test", "J1_collector_check_01 fixture state/variant", "overlay preparation keyword absent before collector update", "new bundle manifest CRLF normalized to LF"]}
with Path(task["active_iteration_checkpoint"]).open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(value, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps(value, ensure_ascii=False))
