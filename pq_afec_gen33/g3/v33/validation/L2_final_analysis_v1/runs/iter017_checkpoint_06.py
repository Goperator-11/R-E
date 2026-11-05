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
failed = read(RUNS / "L2_validation_v1.finished.json")
assert failed["status"] == "failed" and failed["exit_code"] == 1
launch = read(RUNS / "L2_validation_launch_v2.json")
old = task.pop("active_computation")
old.update(status="failed_checker_assumption", ended_kst=failed["ended_kst"], completion_receipt=str(RUNS / "L2_validation_v1.finished.json"),
           reason="v2 checker assumed20 numeric seeds for B9 alarm metric; frozen reporter correctly preserves undefined metric as n0/null")
task.setdefault("previous_computations", []).append(old)
task["active_computation"] = {"kind": "CPU_development_independent_validation", "status": "running", "driver_pid": launch["driver_pid"],
    "started_kst": launch["started_kst"], "launch_record": str(RUNS / "L2_validation_launch_v2.json"),
    "expected_finished_receipt": str(RUNS / "L2_validation_v2.finished.json"), "check_path": str(RUNS / "L2_joint_artifact_check_v3.json")}
task["note"] = "반복17 진행 중. 전체 보고 완료 뒤 검사기v2가 B9 미정의 경보율을 잘못 거부했다. v3는 동결 보고 규칙의 n0/null을 검증하며 합성53639·미정의36·유리수36·smoke545검사 통과.13:46:58 PID21872에서 실제 재검증 중. 정책·보고·수치문턱은 변경하지 않았다."
out = RUNS / "iter017_checkpoint_06.json"
checkpoint = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "iteration": 17, "task": "L2",
    "active_computation": task["active_computation"], "checker": str(RUNS / "l2_joint_artifact_check_v3.py"),
    "extractor": str(RUNS / "l2_findings_extract_v3.py"), "bundle": str(RUNS / "l2_final_bundle_v2.py"),
    "next_action": "Wait for L2_validation_v2.finished.json complete/exit0 and v3 checker pass. Then run l2_findings_extract_v3.py, review all30 original adoption cells and all60 primary reporting cells. Preserve v2 failure and v3 correction; if more failures investigate without changing frozen production. Finish17 records near14:03 target or save partial and immediately begin18."}
with out.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(checkpoint, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
task["active_iteration_checkpoint"] = str(out)
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps(checkpoint, ensure_ascii=False))
