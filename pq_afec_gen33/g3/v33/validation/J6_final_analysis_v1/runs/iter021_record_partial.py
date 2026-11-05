import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import ast
import hashlib
import json
from pathlib import Path
import subprocess

BASE = Path(r"C:\dev\codex_handoff\v33")
RUNS = BASE / "runs"
ROOT = Path(r"C:\dev\pq_afec_gen33")
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
state = read(BASE / "state/LOOP_STATE.json")
assert state["iterations"] == 20 and state["current"] == "J6"
assert state["tasks"]["J6"]["active_computation"]["driver_pid"] == 25680
assert not (BASE / "state/MEASURE_LOCK.json").exists()
guard = subprocess.run([sys.executable, "-I", "-B", str(BASE / "tools/guard_check.py"), "--check"], capture_output=True, text=True, encoding="utf-8")
assert guard.returncode == 0 and guard.stdout.startswith("GUARD_OK")
git = ["git", "-C", str(ROOT)]
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
commits = subprocess.check_output(git + ["rev-list", "--reverse", "e94961a4f472bc043374cb0ec15034583acc2f34..HEAD"], text=True).split()
progress = read(RUNS / "J6_joint_progress_04.json")
assert not progress["errors"] and not progress["root_finished"] and progress["expected_actions"] == 116
for label in ("J6_core_check_02", "J6_collector_check_01", "J6_final_checks_01"):
    check = read(RUNS / (label + ".json"))
    assert check["exit_code"] == 0 and check["unchanged"]
end = read(RUNS / "J6_full_v1.finished.json")
assert end["status"] == "complete" and end["jobs"] == 75 and not end["error"]
plan = read(RUNS / "J6_joint_plan_v1.finished.json")
assert plan["status"] == "complete" and plan["exit_code"] == 0
next_action = "즉시 반복22에서 KST·guard·MEASURE_LOCK·LOOP_STATE·최근JOURNAL3개·전체CONTEXT·DECISIONS와 J6 카드 및 A1-04·A4-03·A8-06·verify 정정을 다시 읽는다. J6을doing으로 기록하고 PID25680의 기존 전체116행동 계산을 재시작하지 않는다. j6_joint_progress_v1.py로 완료·오류 메타데이터만 확인한다. root complete/exit0 뒤 launch_j6_joint_report_v1.ps1, 보고 완료 뒤 launch_j6_validation_v1.ps1을 순서대로 실행하고 각 단계를 j6_checkpoint_phase_v1.py로 기록한다. 독립v2검사 통과 뒤 j6_findings_extract_v1.py로 원래30셀과C1감소를 판정한다. 실패·미확정이면 준비된 j6_revert_candidate_v1.py와 j6_revert_check_v1.py로 후보를 보존하고 L1을 복구한다. coverage·후속 카드·최종bundle·JOURNAL·MORNING_REPORT를 남긴 뒤 L5로 이어간다."
payload = {
    "task_id": "J6", "status": "partial", "summary": "J6 상태8·margin30 후보와 margin0 진단을 동결하고 새1500실행을 수집했다. 합동3000실행의 입력 검증과 독립 검사 준비를 마쳤으며, 고정116행동 계산을 같은 프로세스로 다음 반복에 이어간다.",
    "commits": commits,
    "gates": [
        {"name": "보호 경로", "result": "pass", "detail": guard.stdout.strip()},
        {"name": "핵심 정책", "result": "pass", "detail": "상태8, margin30 B. 핵심276시험·하위494개 통과. c6000 margin0 δ7, margin30 δ12와 A_pre28~54 B 경계를 검사했다. 관측 중앙값·현재결정 이전 문맥·중복 계수·구버전 거부를 확인했다."},
        {"name": "수집기와 전체 수집", "result": "pass", "detail": "수집47시험 통과. dry10·smoke10의120연결을 검증했다. 실제 전체75작업1500실행2055000연결이complete이며 실패0. 세계·프로토콜·seed를 바꾸지 않았다."},
        {"name": "분석·독립 검사 준비", "result": "pass", "detail": "분석·판정45시험·하위47개 통과. 합성150그룹210대조55289검사 및12오류주입 거부. 사전ACK5650재생검사·별도12오류주입 거부. 전체3000입력검증326.725초 complete/exit0."},
        {"name": "과거 관측과 소스", "result": "pass", "detail": "25저널124800행·압축/원본SHA 검증. n_need 경계492/16000=0.03075, 고정8조건 차이0. 서버중앙10991/10993/10949 B 재현. ML-KEM k2행수93992/3596/6과 계수1 예외7행을 함께 보존했다. 로컬Go소스 key_share1184+32=1216 B 확인. 실제 자연k 분할·예외원인은 미확인."},
        {"name": "고정 전체 평가", "result": "skip", "detail": "N131072·seed850001·8worker·전체116행동. PID25680가 실행 중이고 pool manifest가 생겼다. 최근 결과파일0·오류0. 성능값을 읽지 않았으며 보고·독립검사는 대기 중이다."},
        {"name": "채택·추적", "result": "skip", "detail": "원래30채택셀과C1 조정상한0미만 감소 조건은 미확인. 연결3감사의 완료coverage는 최종판정 뒤 쓴다. 기존 전체194항목 처리42·이관23·기록없음129를 유지한다."}
    ],
    "next_task": "J6", "decisions_needed": ["D17"],
    "discarded": "원래 시험의 상태4 기대5곳을 상태8 계약에 맞췄고 최초 실패를 보존했다. 독립 검사기의 중앙값41과41.0 JSON 표현 불일치를 v3 helper·v2 checker로 정정했으며 후보 코드는 바꾸지 않았다. 과거 감사의 ML-KEM 전부k2 서술은 계수1인7행 때문에 그대로 쓰지 않는다. 여덟 소스 읽기의1216 B는 전체ClientHello 크기로 확대하지 않는다.",
    "direction": "수집·고정계획·검사 준비와 후속 소스 검토를 커밋했다. 남은 MC·보고·독립검증·최종판정이75분 목표를 넘길 수 있어 일관된 단계에서 partial로 기록하고 곧바로 반복22로 이어간다. 계산은 중단하거나 재시작하지 않는다.",
    "unknown": "실제 QUIC 작은 Initial 분류·A_pre 송신량·ACK 손실·Go 거울·실제wire 효과는 미확인이다. J6은 S의 기존 y!=1 선택을 유지하므로 L5가 필요하다. L5에 수신index 중복 제거 가능성과 p13 집계의 개별목록 부재를 읽기 기록으로 남겼다. guard 볼트6경고 변경 주체는 미확인이며 보호 파일은 고치지 않았다.",
    "next_action": next_action,
    "report_line": "상태8·margin30 후보와 margin0 진단 수집1500실행 완료, 합동3000입력검증 통과. 전체116행동MC PID25680 진행 중. 후보 미채택, 바로반복22.",
    "numbers": "반복21 J6 준비: 핵심276시험·하위494개, 수집47시험, 분석45시험·하위47개 통과. 개발 세계 새1500실행2055000연결과 합동3000입력 검증 완료. 전체116행동의 N131072·seed850001 계산 중이며 아직 비용·채택 수치는 없다. 과거25저널124800행에서 경계492/16000=0.03075와 고정8조건 차이0을 재현했다. ML-KEM 첫 비행 계수1 예외7행을 보존했고 key_share1216 B는 로컬 소스의 데이터 길이다.",
    "failure_note": "반복21 J6은 계산·검증 중인 partial이다. 측정잠금은 없고 CPU 개발 계산 PID25680를 유지한다. 기존L2/L3/J1 blocked와L4/J2 의존 미충족은 그대로다. 최초 시험·검사기 표현 오류는 수정·보존했으며 전체 후보 채택은 아직 판정하지 않았다."
}
with (RUNS / "iter021_payload.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(payload, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
original = (RUNS / "record_iteration.py").read_text(encoding="utf-8")
updated = original.replace('encoding="utf-8")\n', 'encoding="utf-8")\n')
updated = updated.replace(' + "\\n", encoding="utf-8")', ' + "\\n", encoding="utf-8", newline="\\n")')
updated = updated.replace('.open("a", encoding="utf-8")', '.open("a", encoding="utf-8", newline="\\n")')
updated = updated.replace('write_text(report, encoding="utf-8")', 'write_text(report, encoding="utf-8", newline="\\n")')
ast.parse(updated)
tool = RUNS / "record_iteration_v2.py"
with tool.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(updated)
print(json.dumps({"payload": str(RUNS / "iter021_payload.json"), "guard": guard.stdout.strip(), "commits": commits, "recorder_sha256": hashlib.sha256(tool.read_bytes()).hexdigest()}, ensure_ascii=False))
