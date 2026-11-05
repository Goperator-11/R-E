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
run = read(RUNS / "L2_joint_run_v1.finished.json")
assert run["status"] == "complete" and run["exit_code"] == 0
launch = read(RUNS / "L2_joint_report_launch_v1.json")
old = task.pop("active_computation")
assert old["kind"] == "CPU_development_MC"
old.update(status="complete", ended_kst=run["ended_kst"], completion_receipt=str(RUNS / "L2_joint_run_v1.finished.json"), progress_record=str(RUNS / "L2_joint_progress_04.json"))
task.setdefault("completed_computations", []).append(old)
task["active_computation"] = {"kind": "CPU_development_report", "status": "running", "driver_pid": launch["driver_pid"],
    "started_kst": launch["started_kst"], "launch_record": str(RUNS / "L2_joint_report_launch_v1.json"),
    "family_sha256": launch["family_sha256"], "expected_finished_receipt": str(RUNS / "L2_joint_report_v1.finished.json")}
commits = subprocess.check_output(["git", "-C", str(ROOT), "log", "-2", "--format=%H"], text=True).splitlines()[::-1]
for commit in commits:
    if commit not in task["commits"]:
        task["commits"].append(commit)
task["note"] = "반복17 진행 중. 공동100행동 계산 complete/exit0,13:35:17 보고 PID24900 시작. 현재코드 과거6777행 재생 완료. 추출기v2는 원래 수집 전 계획대로 L1 대비none·C1 30셀을 채택 조건으로, legacy 포함60셀을 주 비교 보고로 구분한다. 실제 성능은 아직 열람하지 않았다."
out = RUNS / "iter017_checkpoint_04.json"
checkpoint = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "iteration": 17,
    "task": "L2", "active_computation": task["active_computation"], "commits": commits,
    "checker": str(RUNS / "l2_joint_artifact_check_v2.py"), "extractor": str(RUNS / "l2_findings_extract_v2.py"),
    "next_action": "After report complete/exit0 launch launch_l2_validation_v1.ps1. Wait for L2_validation_v1.finished.json complete/exit0 and checker pass, then run l2_findings_extract_v2.py. Use original30-cell adoption scope from docs/L2_benchmark_plan.md; retain all60 primary report cells and all210 comparisons. Finish iteration17 before14:03 KST target if work remains, preserving active phase."}
with out.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(checkpoint, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
task["active_iteration_checkpoint"] = str(out)
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps(checkpoint, ensure_ascii=False))
