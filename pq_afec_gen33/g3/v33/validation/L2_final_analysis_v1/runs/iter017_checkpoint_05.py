import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import json
from pathlib import Path


HANDOFF = Path(r"C:\dev\codex_handoff\v33")
RUNS = HANDOFF / "runs"
read = lambda path: json.loads(Path(path).read_text(encoding="utf-8"))
state_path = HANDOFF / "state/LOOP_STATE.json"
state = read(state_path)
assert state["iterations"] == 16 and state["current"] == "L2"
task = state["tasks"]["L2"]
report = read(RUNS / "L2_joint_report_v1.finished.json")
assert report["status"] == "complete" and report["exit_code"] == 0
launch = read(RUNS / "L2_validation_launch_v1.json")
old = task.pop("active_computation")
assert old["kind"] == "CPU_development_report"
old.update(status="complete", ended_kst=report["ended_kst"], completion_receipt=str(RUNS / "L2_joint_report_v1.finished.json"))
task.setdefault("completed_computations", []).append(old)
task["active_computation"] = {"kind": "CPU_development_independent_validation", "status": "running", "driver_pid": launch["driver_pid"],
    "started_kst": launch["started_kst"], "launch_record": str(RUNS / "L2_validation_launch_v1.json"),
    "expected_finished_receipt": str(RUNS / "L2_validation_v1.finished.json"), "check_path": str(RUNS / "L2_joint_artifact_check_v2.json")}
task["note"] = "반복17 진행 중. 수집·공동100행동 MC·전체 보고 모두 complete/exit0. 보고535.867초.13:44:22 독립검사 PID3644 시작. 검증 통과 뒤 추출기v2로 원래30셀 채택 조건을 판정한다. 실제 성능 수치는 아직 열람하지 않았다."
out = RUNS / "iter017_checkpoint_05.json"
checkpoint = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "iteration": 17,
    "task": "L2", "active_computation": task["active_computation"],
    "next_action": "Do not restart PID3644. After L2_validation_v1.finished.json complete/exit0 and checker pass, execute l2_findings_extract_v2.py. If validation fails preserve files and investigate checker/source assumptions; do not alter frozen producer/report/evaluation thresholds. Complete disposition, coverage, final analysis bundle, core checks only if policy changes, guard and iteration17 records; if unfinished near14:03 KST save partial and immediately begin iteration18."}
with out.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(checkpoint, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
task["active_iteration_checkpoint"] = str(out)
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps(checkpoint, ensure_ascii=False))
