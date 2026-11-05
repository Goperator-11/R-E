import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess


HANDOFF = Path(r"C:\dev\codex_handoff\v33")
ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = HANDOFF / "runs"
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert read(RUNS / "L2_revert_check_01.json")["exit_code"] == 0
state_path = HANDOFF / "state/LOOP_STATE.json"
state = read(state_path)
assert state["iterations"] == 16 and state["current"] == "L2"
assert "E7" not in state["tasks"]
card = """
### E7 L2 EPS 적응의 식별과 채택 재검토
- 목적: 처리 상수·RTT 보정 이후 목적지별 EPS 적응이 모형 오류를 흡수하는 문제와 none 지터 셀의 미확정을 검토한다. 부모 L2의 미완료 채택 관문을 맡는다.
- 근거: runs/L2_disposition.md, L2_coverage.md, L2_findings_v3.json, A2-07·A2r1-15·A7-13. 원래30셀 중 none B8_j10 조정상한1.721694가0.5를 넘었고 C1 B6 EPS평균은0.387294였다.
- 할 일: J2와 O3의 완료된 보정 범위·근거를 읽고 기존 후보의 실패·미확정·모형 혼동을 구분한다. 현재 채택 정책과 새 설계의 전체 W1 비교 계획을 성능 전에 고정한다. 원래 L2 후보는 보존하고 prior·경계·seed를 보고 골라 통과시키지 않는다. 새로운 설계가 정당화되지 않으면 근거와 함께 blocked를 유지한다.
- 완료 기준: 목적지 EPS 채택 또는 미채택 판정, 전체 none·c1 전후 비교와 식별 한계, 과거 라벨 기준, 핵심 시험·관문·coverage가 기록됨. L2를 다시 열어 잔여 요구의 완료 여부를 별도로 확인한다. 미확정은 통과가 아니다.
- 하지 말 것: 원래3000실행·100행동·210대조 덮어쓰기, 진단용 고정 EPS를 사후 후보로 바꾸기, 불리한 셀 제외, 물리 오탐률 식별·확증 주장.
- 예상 시간: 설계·구현60~75분과 고정 전체 벤치 실제 계산량. 의존: J2,O3. TASKS 본래 과제 후 수행하며 의존이 충족되지 않으면 이유를 남긴다.
"""
with (HANDOFF / "state/EXTRA_TASKS.md").open("a", encoding="utf-8") as stream:
    stream.write("\n" + card)
state["tasks"]["E7"] = {"status": "todo", "depends": ["J2", "O3"], "iterations": 0, "commits": [],
    "note": "L2 EPS 후보 미채택의 후속. 원래 none B8_j10 비열등 미확정과 EPS/모형오류 혼동을 처리 상수·RTT 보정 뒤 재검토한다. EXTRA_TASKS E7 참조."}
state["order"].append("E7")
task = state["tasks"]["L2"]
active = task.pop("active_computation")
end = read(RUNS / "L2_validation_v2.finished.json")
assert end["status"] == "complete" and end["checker_status"] == "pass"
active.update(status="complete", ended_kst=end["ended_kst"], completion_receipt=str(RUNS / "L2_validation_v2.finished.json"))
task.setdefault("completed_computations", []).append(active)
task["candidate_adopted"] = False
task["blocker"] = {"reason": "Original none B8_j10 noninferiority gate inconclusive", "followup": "E7", "depends": ["J2", "O3"]}
task["note"] = "L2 후보 검증 완료 후 원래30셀 채택 관문 미충족으로 L1 활성 정책을 복구했다. EPS 채택은 미완료이며 반복 종료시 blocked로 기록한다. E7 후속, L3는L1만 의존하므로 즉시 진행 가능."
checkpoint = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "iteration": 17,
    "checker_status": "pass", "checks": 18504407, "candidate_adopted": False, "next_status": "blocked", "next_task": "L3",
    "findings_sha256": sha(RUNS / "L2_findings_v3.json"), "restore_receipt": str(RUNS / "L2_revert_candidate_v1.json"),
    "next_action": "Package evidence, commit passing restored policy and report. Finish17 blocked with E7 followup and immediately start18 L3."}
with (RUNS / "iter017_checkpoint_07.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(checkpoint, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
task["active_iteration_checkpoint"] = str(RUNS / "iter017_checkpoint_07.json")
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
with (HANDOFF / "state/DECISIONS_NEEDED.md").open("a", encoding="utf-8") as stream:
    stream.write("\n반복17의 D15 실행 결과: 고정한 Beta(1,999) 후보를 평가했으나 none B8_j10 비열등 미확정으로 채택하지 않았다. 기본값을 결과에 맞춰 바꾸지 않았다. 활성 L1은 고정 EPS0.001·상태4를 유지한다. 원래 후보와 근거를 보존하고 E7에서 J2/O3 뒤 재검토한다. 사용자 결정이나 응답을 기다리는 장애가 아니다.\n")
with (RUNS / "L2_bench.md").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write("# L2 전체 전후 벤치\n\n후보 미채택, 활성 L1 복구, L2 blocked. 판정·출처·후속은 L2_disposition.md다. 아래210대조와150그룹은 동결 원형 보고에서 추출했으며 모든 실패와 미확정을 유지한다.\n\n")
    stream.write((RUNS / "L2_findings_v3.md").read_text(encoding="utf-8"))
code = "import sys; sys.path.insert(0," + repr(str(ROOT)) + "); from padfec3 import learn3; d=learn3.new_state().to_json(); assert d['v']==4; d['v']=5\ntry: learn3.DestState3.from_json(d)\nexcept ValueError: print('state5_rejected_by_active4')\nelse: raise AssertionError('candidate state accepted')"
result = subprocess.run([sys.executable, "-I", "-B", "-c", code], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
assert result.returncode == 0, result.stdout + result.stderr
with (RUNS / "L2_revert_state_check.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump({"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr, "script_sha256": sha(__file__)}, stream, indent=2)
    stream.write("\n")
print(json.dumps(checkpoint, ensure_ascii=False))
