import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import json
from pathlib import Path
import subprocess

BASE = Path(r"C:\dev\codex_handoff\v33")
ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = BASE / "runs"
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
state = read(BASE / "state/LOOP_STATE.json")
assert state["iterations"] == 22 and state["current"] == "L5"
task = state["tasks"]["L5"]
assert task["active_computation"]["driver_pid"] == 12044
assert not (BASE / "state/MEASURE_LOCK.json").exists()
assert not subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"], text=True).strip()
guard = subprocess.run([sys.executable, "-I", "-B", str(BASE / "tools/guard_check.py"), "--check"], capture_output=True, text=True, encoding="utf-8")
assert guard.returncode == 0 and guard.stdout.startswith("GUARD_OK")
plan = read(RUNS / "L5_joint_plan_v1.finished.json")
assert plan["status"] == "complete" and plan["exit_code"] == 0
progress = read(RUNS / "L5_joint_progress_01.json")
assert not progress["errors"] and progress["expected_actions"] == 118
next_action = "즉시 반복24에서 KST·guard·MEASURE_LOCK·LOOP_STATE·최근 JOURNAL3개·전체 CONTEXT·DECISIONS와 L5 카드 및 A1-12·A2-11·A2r1-10·A4-01·A8-06·verify 정정을 다시 읽는다. L5를doing으로 기록하고 PID12044의 전체118행동 계산을 재시작하지 않는다. l5_joint_progress_v1.py로 완료·오류 메타데이터만 확인한다. root complete/exit0 뒤 launch_l5_joint_report_v1.ps1, 보고 완료 뒤 launch_l5_validation_v2.ps1을 순서대로 실행하며 l5_checkpoint_phase_v1.py로 기록한다. 검증 driver_v2와 checker_v3의 단계 기록은 L5_validation_v1 이름이다. 독립 검사 통과 뒤 l5_findings_extract_v2.py로 원래30셀·none/C1 B5/B6·역사 관문을 판정한다. 역사 입력 부족 때문에 현재 후보는 채택할 수 없다. l5_revert_candidate_v2.py와 l5_revert_check_v1.py로 후보를 보존하고 L1을 복구·검증한다. coverage·후속 카드·최종 bundle·JOURNAL·MORNING_REPORT를 남기고 J7로 이어간다. J7 사전 검토는 J7_reading_during_L5_v1.md에 있다."
payload = {"task_id": "L5", "status": "partial",
    "summary": "L5 상태9의 완료 응답·물리 산술·크기 혼합 후보와 single 진단을 동결하고 새1500실행을 수집했다. 합동3000입력 검증과 독립 검사 준비를 마쳤으며 고정118행동 계산을 같은 프로세스로 다음 반복에 이어간다. 역사 자료 관문은 입력 부족으로 미완료다.",
    "commits": task["commits"], "gates": [
        {"name": "보호 경로", "result": "pass", "detail": guard.stdout.strip()},
        {"name": "핵심 정책", "result": "pass", "detail": "상태9. 핵심329시험·하위524개 통과. 완료 응답의 중복·ACK·완료 이후 바이트를 분리하고, y와 무관하게 갱신한다. 물리 prefix 엄격 경계, 두 산출 함수, 변화·혼합·조건부 우도와 구버전 거부를 검사했다."},
        {"name": "수집기와 전체 수집", "result": "pass", "detail": "수집기·관측52시험 통과. dry10·smoke10의120연결 검증. 전체75작업1500실행2055000연결이complete, 오류0. 세계·프로토콜·seed는 원래 값이다."},
        {"name": "분석·독립 검사 준비", "result": "pass", "detail": f"분석37시험·하위47개와 판정20시험 통과. 합성150그룹210대조55289검사·오류12건 거부. 응답120연결2340검사·오류15건, B5 60사례·B6 40그룹216264검사·오류11건 거부. B9 초기화 전달61검사. 합동3000입력 검증{plan['elapsed_seconds']:.3f}초 complete/exit0."},
        {"name": "과거 산출법 관문", "result": "skip", "detail": "기존 유효 모형의 앵커6/6와cert12000→11을 재현했으나 독립 검증이 아니다. H 각팔1800행과p13 집계5판본에 N·tail·완료 패킷목록이 없어 두 새 방법의 역사 관문은blocked_missing_inputs. cert3340의 불완전 첫 비행을 완료 응답으로 쓰지 않았다."},
        {"name": "고정 전체 평가", "result": "skip", "detail": f"N131072·seed850001·8worker·전체118행동. PID12044 실행 중. 최근 완료결과{progress['completed_result_files']}·오류0. 성능값을 읽지 않았으며 보고·독립검사 대기 중이다."},
        {"name": "채택·추적", "result": "skip", "detail": "원래30셀과none/C1 B5·B6의 성능 관문은 미확인이다. 역사 관문이 미완료여서 후보를 채택하지 않았다. 연결5감사의 완료coverage는 최종 판정 뒤 기록한다. 기존194항목 처리42·이관26·기록없음126을 유지한다."}],
    "next_task": "L5", "decisions_needed": ["D18"],
    "discarded": "세계의 native hct 키를 hct_ms로 읽던 관측기 초안을 고치고 최초 실패를 보존했다. 검사기의 tuple Counter JSON 비교, 합성B6 식별자, B9 초기화 누락과 음성 대조 예외를 정정했다. 후보·기준·seed는 바꾸지 않았다. 신규 시험 임시 폴더를 보존하도록 바꿨고 이후 회귀 시험에는 삭제 대신 허용 경로 안에 보존하는 어댑터를 준비했다. 앞서 기본 TemporaryDirectory가 정리한 내용은 복구할 수 없다.",
    "direction": "수집·합동 입력·검사 준비를 커밋했다. 남은 MC·보고·독립 검증·복구·최종 기록이75분 목표를 넘길 수 있어 일관된 단계에서 partial로 기록하고 곧바로 반복24로 이어간다. 기존 계산은 중단하거나 재시작하지 않는다.",
    "unknown": "실제 QUIC CRYPTO 구간·재분할·ACK 유실의 식별과 Go 거울은 미검증이다. world_receive_index_proxy는 수신 대용이며 전송 세계를 독립 재구현한 검사가 아니다. J7의46 B 프로파일은39 B 기존 원자료와 같은 세계로 섞을 수 없음을 읽기 기록에 남겼다. 볼트6경고 변경 주체는 미확인이고 보호 파일은 고치지 않았다.",
    "next_action": next_action,
    "report_line": "상태9 후보·single 진단1500실행 완료, 합동3000입력 검증 통과. 전체118행동MC PID12044 실행 중. 역사 입력 부족, 미채택. 바로반복24.",
    "numbers": "반복23 L5 준비: 핵심329시험·하위524개, 수집52시험, 분석37시험·하위47개, 판정20시험 통과. 개발 세계1500실행2055000연결 수집과 합동3000입력 검증 완료. 전체118행동 N131072·seed850001 계산 중이다. 독립 합성 대조55289검사, 응답2340검사, B5/B6 정상·오류216264검사 및 B9 초기화61검사를 보존했다. 유효 모형 앵커6/6·H cert12000의11은 적합 모형 재현이며 새 관측법의 역사 검증은 아니다.",
    "failure_note": "반복23 L5는 계산·검증 중인 partial이다. 물리 측정 잠금은 없고 CPU 개발 계산 PID12044를 유지한다. 역사 자료에 N·tail·목록이 없어 두 새 산출법 관문은 미완료다. D18 기본값에 따라 세계 성능으로 대체 채택하지 않는다. 기존L2/L3/J1/J6 blocked와L4/J2 의존 미충족은 유지한다."}
with (RUNS / "iter023_payload.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(payload, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps({"status": "prepared", "guard": guard.stdout.splitlines()[0], "iteration": 23, "active_pid": 12044}, ensure_ascii=False))
