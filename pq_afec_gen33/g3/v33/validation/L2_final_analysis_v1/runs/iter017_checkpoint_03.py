import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import json
from pathlib import Path
import subprocess


ROOT = Path(r"C:\dev\pq_afec_gen33")
HANDOFF = Path(r"C:\dev\codex_handoff\v33")
RUNS = HANDOFF / "runs"
read = lambda path: json.loads(Path(path).read_text(encoding="utf-8"))
state_path = HANDOFF / "state/LOOP_STATE.json"
state = read(state_path)
assert state["iterations"] == 16 and state["current"] == "L2"
task = state["tasks"]["L2"]
plan = read(RUNS / "L2_joint_plan_v1.finished.json")
launch = read(RUNS / "L2_joint_run_launch_v1.json")
progress = read(RUNS / "L2_joint_progress_01.json")
assert plan["status"] == "complete" and plan["exit_code"] == 0
old = task.pop("active_computation")
assert old["kind"] == "CPU_development_plan_validation"
old.update(status="complete", ended_kst=plan["ended_kst"], completion_receipt=str(RUNS / "L2_joint_plan_v1.finished.json"))
task.setdefault("completed_computations", []).append(old)
task["active_computation"] = {"kind": "CPU_development_MC", "status": "running", "driver_pid": launch["driver_pid"],
    "started_kst": launch["started_kst"], "launch_record": str(RUNS / "L2_joint_run_launch_v1.json"),
    "plan_path": launch["family_path"], "plan_sha256": launch["family_sha256"],
    "pool_path": str(RUNS / "L2_joint_action_pool_v1"), "progress_record": str(RUNS / "L2_joint_progress_01.json")}
head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
if head not in task["commits"]:
    task["commits"].append(head)
task["note"] = "반복17 진행 중. 전체수집과3000실행 원자료 검증 완료. 공동100행동·N131072·seed850001 MC를13:22:35 PID11188에서 시작했다.13:29 결과파일28/100, 오류0. 성능 판정은 아직 하지 않았다. 독립검사기v2 합성47639검사·유리수36조건·실제smoke545검사를 통과했다."
out = RUNS / "iter017_checkpoint_03.json"
checkpoint = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "iteration": 17,
              "task": "L2", "active_computation": task["active_computation"], "progress": progress,
              "checker": str(RUNS / "l2_joint_artifact_check_v2.py"), "checker_review": str(RUNS / "L2_artifact_check_review_v2.json"),
              "next_action": "Do not restart PID11188. After complete100 actions and root complete/exit0, run launch_l2_joint_report_v1.ps1. Then run l2_joint_artifact_check_v2.py with a new output path, extract findings, record all primary and diagnostic cells without tuning. v1 checker synthetic failure is preserved."}
with out.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(checkpoint, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
task["active_iteration_checkpoint"] = str(out)
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps(checkpoint, ensure_ascii=False))
