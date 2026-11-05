import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path
import subprocess


BASE = Path(r"C:\dev\codex_handoff\v33")
ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = BASE / "runs"
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
state = read(BASE / "state/LOOP_STATE.json")
assert state["iterations"] == 17 and state["current"] == "L3"
assert state["tasks"]["L3"]["status"] == "doing"
assert not (BASE / "state/MEASURE_LOCK.json").exists()
assert read(RUNS / "L3_full_v1.finished.json")["status"] == "complete"
assert read(RUNS / "L3_joint_plan_v1.finished.json")["status"] == "complete"
assert read(RUNS / "L3_checker_fixture_check_v1.json")["status"] == "pass"
progress = read(RUNS / "L3_joint_progress_02.json")
assert not progress["errors"] and not progress["root_finished"]
guard = (RUNS / "iter018_guard_end.txt").read_text(encoding="utf-8")
assert guard.startswith("GUARD_OK")
git = ["git", "-C", str(ROOT)]
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
destination = ROOT / "g3/v33/validation/L3_iteration18_handoff"
assert not destination.exists()
names = ["iter018_finish.py", "iter018_guard_end.txt", "iter018_coverage_status.json", "iter018_checkpoint_04.json",
    "L3_joint_run_launch_v1.json", "L3_joint_progress_01.json", "L3_joint_progress_02.json", "L3_joint_plan_commit_receipt.json",
    "J1_preparation_during_L3_v2.md", "j1_tail_reference_preparation_v1.py", "J1_tail_reference_preparation_v1.json"]
entries = []
for name in names:
    source, target = RUNS / name, destination / name
    text = source.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
    entries.append({"source": str(source), "stored": name, "source_sha256": sha(source), "stored_sha256": sha(target)})
manifest = destination / "manifest.json"
with manifest.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump({"entries": entries, "scope": "Iteration18 coherent partial checkpoint; same finite MC process continues into iteration19"}, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
subprocess.run(git + ["add", "-f", "--", destination.relative_to(ROOT).as_posix()], check=True, capture_output=True)
for path, expected in [(destination / row["stored"], row["stored_sha256"]) for row in entries] + [(manifest, sha(manifest))]:
    assert hashlib.sha256(subprocess.check_output(git + ["show", ":" + path.relative_to(ROOT).as_posix()])).hexdigest() == expected
message = RUNS / "iter018_commit_message.txt"
with message.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write("WIP(L3): 고정 평가 실행을 다음 반복으로 인계\n\n1800실행·2466000연결 수집과 전체3300실행 입력 검증 완료.\n101행동·N131072·seed850001 계산은 PID33836에서 진행 중이며 재시작하지 않는다.\n핵심254시험·하위424개, 합성 독립집계56999검사·변조거부7건의 근거를 유지한다.\nJ1 교차점0.2026/0.2174/0.2148 재현과 준비 문서의 GE 과제번호J5 정정을 보존했다.\n")
completed = subprocess.run(git + ["commit", "-F", str(message)], capture_output=True, text=True, encoding="utf-8")
assert completed.returncode == 0, completed.stdout + completed.stderr
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
commits = subprocess.check_output(git + ["rev-list", "--reverse", "67aed72df6ae0d1ce2bdc55392efa14d5a5377e2..HEAD"], text=True).split()
state["tasks"]["L3"]["active_computation"].update(progress_record=str(RUNS / "L3_joint_progress_02.json"), last_checked_kst=progress["recorded_kst"])
(BASE / "state/LOOP_STATE.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
payload = {
    "task_id": "L3", "status": "partial", "summary": "L3 후보와 세 진단 사본을 구현하고 전체1800실행을 수집했다. 원형과 합친3300실행 검증 및 독립 검사 준비를 마쳤고, 고정101행동 계산을 같은 프로세스로 다음 반복에 이어간다.",
    "commits": commits, "next_task": "L3", "decisions_needed": ["D16"],
    "gates": [
        {"name": "보호 경로", "result": "pass", "detail": guard.strip()},
        {"name": "핵심 정책", "result": "pass", "detail": "상태6, 고정EPS0.001. 최종 핵심254개·하위424개 통과. 방향별 회복 수정 전 실패기록 보존. L2 후보시험은 격리된 사본으로 유지."},
        {"name": "수집기", "result": "pass", "detail": "28시험·하위17개, dry-run6·smoke6 통과. 독립 재생6실행72연결 통과. 실제 전체90작업1800실행2466000연결 모두 complete."},
        {"name": "분석·독립 검사 준비", "result": "pass", "detail": "분석61시험·하위57개, 독립 감시15시험 통과. 합성165그룹210대조의 집계56999검사와 오류 주입7건 거부 통과. 전체3300원자료 검증397.51초 complete/exit0."},
        {"name": "알려진q 감지 시험", "result": "pass", "detail": "사전 고정250반복 모두 감지, 미감지를 무한대로 포함한 중앙지연10결정. null q=.03/.06/.42 각200000연결의 양방향 경보0.065/0.165/0.56 per1000. 폐루프 B1 결과와 구분."},
        {"name": "고정 전체 평가", "result": "skip", "detail": "N131072·seed850001·8worker·전체101행동. PID33836가 입력을 재검증 중이며 아직 pool manifest 없음, 실패기록 없음. 성능값 미열람."},
        {"name": "L3 채택·추적", "result": "skip", "detail": "전체45채택셀, B1/B2절대목표·B1경보율 미확인. 연결11감사의 준비기록만 있으며 완료coverage는 아직 쓰지 않았다. 전체194항목 처리42·이관13·기록없음139 유지."}
    ],
    "discarded": "초안의 양방향 CUSUM 동시0 회복 조건을 방향별0 조건으로 고친 뒤 전체 수집 전에 고정했다. smoke검사기의 L2 import 잔재와 보존기의 새폴더 생성 뒤 clean 검사 순서 오류는 검사·보존 코드만 고치고 실패자료를 남겼다. 표본·seed·문턱·세계는 바꾸지 않았다.",
    "direction": "구현·수집·계획 고정을 일관된 단계로 마쳤다. 남은 CPU 계산·보고·독립 검증이75분 목표를 넘길 수 있어 partial로 기록하며 즉시 반복19로 이어간다. 실행 중인 계산은 재시작하지 않는다.",
    "unknown": "전체 세계 성능과 채택, 준비된 C1의 p 정확성, 실제 회신 비용·wire·Go는 미확인이다. 알려진q 감지 시험을 손실 변화와 모형 오류의 식별 보장으로 쓰지 않는다. guard 볼트6경고 변경 주체는 미확인이며 직접 고치지 않았다. J1 준비의 GE 과제번호J6은J5로 정정했고 카드 꼬리식과 실제 꼬리 수치 차이를 보존했다.",
    "next_action": "즉시 반복19에서 KST·guard·MEASURE_LOCK·LOOP_STATE·최근JOURNAL3개·CONTEXT·DECISIONS와 L3카드·연결감사 원문을 다시 읽는다. L3_joint_run_launch_v1.json의 PID33836를 재시작하지 말고 l3_joint_progress_v1.py로 진행만 기록한다. 전체101행동과 root complete/exit0 뒤 launch_l3_joint_report_v1.ps1, 완료 뒤 launch_l3_validation_v1.ps1을 순서대로 실행한다. 각 단계는 l3_checkpoint_phase_v1.py로 기록한다. 독립검사 통과 뒤 l3_findings_extract_v1.py로45채택셀·절대목표·경보·주입 조건을 판정하고 미충족이면 후보를 보존해 활성L1으로 복구한다. 최종bundle은 반복19기록도 포함하도록 별도v2로 준비한다.",
    "report_line": "상태6 후보·1800실행 수집 완료. 전체3300검증 후101행동 계산중(PID33836). 성능·채택미확인",
    "numbers": "L3 [독립 세계 개발 평가 준비, 반복18]: 핵심254시험·하위424, 수집28시험·하위17, 분석61시험·하위57, 독립감시15시험 통과. 원형 포함3300실행 입력검증397.51초. 새1800실행2466000연결 수집 완료. 101행동 N131072·seed850001 계산중, 전체성능미열람. 알려진q 주입250/250감지·중앙10결정; q=.03/.06/.42 각200000연결 경보0.065/0.165/0.56 per1000. 이 값은 폐루프 W1 경보율이 아니다. 합성 집계56999검사·변조7건거부 통과. 출처:L3_core_check_04.json,L3_analysis_check_01.json,L3_audit_check_02.json,L3_checker_fixture_check_v1.json,L3_monitor_operating_v2.json,L3_full_v1.finished.json.",
    "failure_note": "L3는 전체 고정 평가·엄격 보고·독립 검증이 남아 partial이다. 채택을 선언하지 않는다. L2 blocked와 E7 의존은 유지한다."
}
path = RUNS / "iter018_payload.json"
with path.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(payload, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
subprocess.run([sys.executable, "-I", "-B", str(RUNS / "record_iteration.py"), str(path)], check=True)
