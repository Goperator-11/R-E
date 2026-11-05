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
assert state["iterations"] == 20 and state["current"] == "J6"
launch = read(RUNS / "J6_collection_launch_v1.json")
task = state["tasks"]["J6"]
assert not task.get("active_computation")
active = {"kind": "CPU_development_collection", "status": "running", "driver_pid": launch["driver_pid"],
    "started_kst": launch["started_kst"], "launch_record": str(RUNS / "J6_collection_launch_v1.json"),
    "plan_path": launch["plan_path"], "plan_sha256": launch["plan_sha256"],
    "expected_finished_receipt": str(RUNS / "J6_full_v1.finished.json")}
task["active_computation"] = active
task["commits"] = [read(RUNS / "J6_collection_commit_receipt.json")["commit"]]
task["active_iteration_checkpoint"] = str(RUNS / "iter021_checkpoint_01.json")
task["note"] = "J6 상태8·margin30 후보와 margin0 진단을 동결하고 전체1500실행을 수집 중이다. 아직 미채택이며 원래 관문이 실패·미확정이면 활성 L1으로 복구한다."
value = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "iteration": 21,
    "task": "J6", "active_computation": active, "commits": task["commits"],
    "checks": {"core": "276 passed, 494 subtests", "collector_observer": "47 passed", "smoke": "10 runs, 120 connections", "independent_preflight": "5640 checks"},
    "known_failures_preserved": ["J6_core_check_01: 5 old candidate/state4 expectations; updated to declared margin30/state8, no performance thresholds changed"],
    "scope": "CPU independent development world; no physical measurement lock"}
with Path(task["active_iteration_checkpoint"]).open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(value, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps(value, ensure_ascii=False))
