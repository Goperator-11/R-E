import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(r"C:\dev\pq_afec_gen33")
HANDOFF = Path(r"C:\dev\codex_handoff\v33")
RUNS = HANDOFF / "runs"
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
read = lambda path: json.loads(Path(path).read_text(encoding="utf-8"))
folder = ROOT / "g3/v33/validation/L2_report_preparation"
manifest = read(folder / "manifest.json")
for item in manifest["entries"]:
    path = folder / item["stored"]
    assert sha(path) == item["stored_sha256"] and sha(item["source"]) == item["source_sha256"]
    stored = subprocess.check_output(["git", "-C", str(ROOT), "show", "HEAD:" + path.relative_to(ROOT).as_posix()])
    assert hashlib.sha256(stored).hexdigest() == item["stored_sha256"]
finished = read(RUNS / "L2_full_v1.finished.json")
assert finished["status"] == "complete" and finished["jobs"] == 75
state_path = HANDOFF / "state/LOOP_STATE.json"
state = read(state_path)
assert state["iterations"] == 16 and state["current"] == "L2"
task = state["tasks"]["L2"]
computation = task.pop("active_computation")
computation.update(status="complete", ended_kst=finished["ended_kst"], progress_record=str(RUNS / "L2_collection_progress_04.json"),
                   completion_receipt=str(RUNS / "L2_full_v1.finished.json"))
task.setdefault("completed_computations", []).append(computation)
commits = subprocess.check_output(["git", "-C", str(ROOT), "log", "-2", "--format=%H"], text=True).splitlines()[::-1]
for commit in commits:
    if commit not in task["commits"]:
        task["commits"].append(commit)
task["active_computation"] = {"kind": "CPU_development_plan_validation", "status": "running", "session_id": 75121,
    "driver": str(RUNS / "l2_joint_driver_v1.py"), "started_receipt": str(RUNS / "L2_joint_plan_v1.started.json"),
    "expected_finished_receipt": str(RUNS / "L2_joint_plan_v1.finished.json")}
task["note"] = "반복17 진행 중. 전체75묶음·1500seed 수집 완료, 오류0. 공동 보고·실행 검사38개/하위47개 통과. 공동 행동 목록의 원자료 검증이 실행 중이며 기대비용과 채택은 미완료다."
checkpoint = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "iteration": 17,
              "task": "L2", "completed_collection": computation, "active_computation": task["active_computation"],
              "commits": commits, "stored_evidence_verified_files": len(manifest["entries"]),
              "reporter_sha256": sha(ROOT / "experiments/v33/bench_learning_l2_report.py"),
              "next_action": "Wait for L2_joint_plan_v1 complete/exit0, inspect generated action family identity, commit fixed plan then launch same driver run in hidden process. Do not restart collection or change policy/evaluation parameters."}
out = RUNS / "iter017_checkpoint_02.json"
with out.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(checkpoint, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
task["active_iteration_checkpoint"] = str(out)
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps(checkpoint, ensure_ascii=False))
