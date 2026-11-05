import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path
import re
import subprocess

BASE = Path(r"C:\dev\codex_handoff\v33")
RUNS = BASE / "runs"
ROOT = Path(r"C:\dev\pq_afec_gen33")
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
state = read(BASE / "state/LOOP_STATE.json")
assert state["iterations"] == 23 and state["current"] == "L5"
assert "active_computation" not in state["tasks"]["L5"]
assert state["tasks"]["L5"]["candidate_adopted"] is False and state["tasks"]["E11"]["status"] == "todo"
assert not (BASE / "state/MEASURE_LOCK.json").exists()
git = ["git", "-C", str(ROOT)]
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
receipt = read(RUNS / "L5_final_commit_receipt.json")
assert receipt["git_status"] == "clean" and receipt["candidate_adopted"] is False
assert receipt["commit"] == subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip()
manifest_path = ROOT / "g3/v33/validation/L5_final_analysis_v1/manifest.json"
assert receipt["bundle_manifest_sha256"] == sha(manifest_path)
manifest = read(manifest_path)
check = read(RUNS / "L5_joint_artifact_check_v3.json")
findings = read(RUNS / "L5_findings_v1.json")
assert check["status"] == "pass" and check["error"] is None
assert findings["candidate_adopted"] is False and findings["checker_sha256"] == sha(RUNS / "L5_joint_artifact_check_v3.json")
restore = read(RUNS / "L5_revert_check_02.json")
assert restore["exit_code"] == 0 and restore["unchanged"]
test_lines = [line for line in (RUNS / "L5_revert_check_02.log").read_text(encoding="utf-8").splitlines() if re.search(r"\b\d+ passed\b", line)]
assert test_lines
test_summary = test_lines[-1]
coverage = read(RUNS / "iter024_coverage_status.json")
assert coverage["source_count"] == 194 and sum(coverage["counts"].values()) == 194
guard = subprocess.run([sys.executable, "-I", "-B", str(BASE / "tools/guard_check.py"), "--check"], capture_output=True, text=True, encoding="utf-8")
guard_value = {"exit_code": guard.returncode, "stdout": guard.stdout, "stderr": guard.stderr}
with (RUNS / "iter024_guard_final.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(guard_value, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
assert guard.returncode == 0 and guard.stdout.startswith("GUARD_OK")
commits = subprocess.check_output(git + ["rev-list", "--reverse", "91432c35c122dd83bc946b2d53e68c96bd6fa14b..HEAD"], text=True).split()
run = read(RUNS / "L5_joint_run_v1.finished.json")
report = read(RUNS / "L5_joint_report_v1.finished.json")
assert all(value["status"] == "complete" and value["exit_code"] == 0 for value in (run, report))
counts, specific = findings["primary_counts"], findings["specific_gates"]
pool, response = check["summary"]["pool"], check["summary"]["response_audit"]
next_action = "즉시 반복25에서 KST·guard·MEASURE_LOCK·LOOP_STATE·최근 JOURNAL3개·전체 CONTEXT·DECISIONS를 다시 읽는다. doing·partial이 없으면 blocked와 의존 미충족 과제를 기록하고 S0만 의존하는 J7을 선택한다. J7 카드와 A3-05·A4-02·A8-05 및 검증 정정을 모두 읽는다. 상태 handoff_notes의 J7_reading_during_L5_v1/v2/v3.md를 읽고 활성 L1 상태4와 후보 상태9 격리를 확인한다. L5_c12000_diagnosis_v1.md의1461 B 잘림·C1 검열을 읽고 CID·패딩·1452 B 상한·PFEC 파싱 실패 계측의 계약을 먼저 고정한다. Go 빌더 stage·Go 시험 TempDir·fresh 관문 벡터를 삭제하지 않도록 보존 방식을 마련한다. 기존 L1/Go 관문 차이를 기록하고 기준을 낮추지 않는다. 세계39 B 원자료와 새46 B 조건을 같은 세계로 섞지 않는다. 변경·해당 시험·관문·전체 평가·추적을 수행하고 반복 기록 뒤 다음 과제로 이어간다."
payload = {"task_id": "L5", "status": "blocked", "summary": "L5의 전체 개발 평가와 독립 검사를 마쳤으나 c12000 none·C1의 약24.9 ms 악화와 역사 입력 부족으로 후보를 채택하지 않았다. 후보와 근거를 보존하고 활성 L1 복구·시험을 끝냈으며, E11에 후속을 등록한 뒤 J7로 진행한다.", "commits": commits,
    "gates": [
        {"name": "보호 경로", "result": "pass", "detail": guard.stdout.strip()},
        {"name": "전체 개발 평가", "result": "pass", "detail": f"새1500실행2055000연결, 합동3000실행·150그룹·210대조·118행동(MC{pool['MC_jobs']}·구조{pool['structural_jobs']}). N131072·seed850001 고정. run{run['elapsed_seconds']:.3f}초·report{report['elapsed_seconds']:.3f}초 complete/exit0와 발행SHA 일치."},
        {"name": "독립 검사", "result": "pass", "detail": f"{check['checks']}검사·{check['elapsed_seconds']:.3f}초 통과. 응답 관측 재생 {json.dumps(response, ensure_ascii=False)}. 원자료·seed통계·공유MC·B5/B6·인과적 혼합 이력을 대조했으며 실제 QUIC나 세계 전체의 독립 재구현은 아니다."},
        {"name": "원래 채택 관문", "result": "fail", "detail": f"원래30셀 {counts}, c12000 none/C1 차이+24.911063/+24.893233 ms로 두 셀 비열등 실패. none/C1 B5/B6 {specific}. 역사 관문 {findings['historical_gate']}. 보정 상한0미만 감소 셀 {findings['primary_reduction_cells']}. 미채택 이유 {findings['reason']}. 원래 기준·표본·seed·후보를 유지했다."},
        {"name": "기여 분리와 보존", "result": "pass", "detail": f"전체210대조 {findings['all_comparison_counts']}를 보존했다. single 진단은 대체 채택하지 않았다. 두 S 산출 함수를 구현했으나 앵커6/6·cert12000→11의 기존 유효 모형 재현을 새 관측법 검증으로 쓰지 않았다."},
        {"name": "활성 정책 복구", "result": "pass", "detail": f"활성 padfec·padfec3는 직전L1 91432c3와 바이트 동일. 상태4가 후보상태9를 거부한다. 복구 시험 {test_summary}. 실행 전후 소스SHA 동일. 후보시험2파일은 동결 사본을 읽는 별도 프로세스로 격리했다."},
        {"name": "감사 추적", "result": "pass", "detail": f"연결5감사 이관·빈칸0. 전체194항목 {coverage['counts']}. 증거{manifest['file_count']}파일·{manifest['stored_bytes']} B, Git index{receipt['verified_index_blobs']}blob SHA 대조. 압축추적1500개 원형위치·SHA 보존. E11 카드·상태·order와 기존T4/G1/O4/R3 후속을 등록했다."}],
    "next_task": "J7", "decisions_needed": [],
    "discarded": "c12000 none +24.911063 ms(조정[23.775437,26.046689]), C1 +24.893233 ms(조정[23.731675,26.054792])로 실패한 L5 후보를 활성 정책에서 제거하고 L1으로 복구했다. W1에서 유리한 셀이나 single 진단으로 역사 검증을 대신하지 않았다. 성능 전에 판정기v3에 기존 공통 개선 조건을 명시했고21시험으로 확인했다. 후보·세계·seed·표본·문턱은 그대로다. 복구 실행기01은 Windows 경로의 역슬래시 해석 때문에 시험 시작 전에 실패했다. 경로 직렬화만 고친 v2의02는351시험·548하위검사를 통과했다. 최초 실패와 기존 TemporaryDirectory 정리 사실도 보존했다.",
    "direction": "D18 기본값과 원래 채택 조건을 적용했다. E11은 J7의 수신 상한과 T4의 실제 응답 관측 뒤 입력·채택 잔여를 재검토하며, S4→T4 경로에는 L5/G1 순환 의존이 없다. L5 blocked는 G1 의존을 해제하지 않는다. 독립적인 J7로 바로 진행한다. 보고 대기 중 J7·M1·S4 소스 검토와1차 문헌 확인을 기록했고 이들 과제의 구현 완료로 세지 않았다.",
    "unknown": "과거 N·tail·완료 패킷목록, 실제 QUIC CRYPTO 재분할·ACK 유실 식별·C1 회신 비용·Go 거울은 미검증이다. 세계 수신 index는 실제 관측의 대용이다. M1의700116 순열·소거 사례는 예정 규모를 센 것이며 실행 시험은0이다. 보호 경로 점검에 나타난 볼트 경고의 변경 주체는 미확인이고 보호 파일은 고치지 않았다.",
    "next_action": next_action,
    "report_line": f"미채택: 주30셀{counts}, B5/B6{specific}, c12000 약24.9 ms 악화·역사 입력 부족. L1복구·검사 통과. E11등록, 다음J7.",
    "numbers": f"L5 [독립 세계 개발 평가, 반복24]: 합동3000실행·150그룹·210대조·118행동(MC{pool['MC_jobs']}/구조{pool['structural_jobs']}), N131072·seed850001. 주30셀{counts}, 전체210대조{findings['all_comparison_counts']}, B5/B6{specific}. 보정 감소 셀{findings['primary_reduction_cells']}. 독립{check['checks']}검사 통과, 복구{test_summary}. c12000 none/C1 차이+24.911063/+24.893233 ms, 조정구간[23.775437,26.046689]/[23.731675,26.054792]. B5 none/C1 차이-3.261987/-2.256370, B6-20.917953/-14.552788 ms. 각 L5 팔 수신한도 초과26980/27000회. c12000 악화·역사 입력 부족으로 미채택·활성L1상태4. 출처:L5_findings_v1.json,L5_bench.md,L5_disposition.md,L5_joint_artifact_check_v3.json. 전체194항목{coverage['counts']}.",
    "failure_note": f"반복24 L5 blocked: {findings['reason']}. E11에 입력·실제 응답·채택 재검토를 등록했다. 현재 측정·CPU 계산은 없고 다음J7을 바로 시작한다. L2/L3/J1/J6의blocked와L4/J2의 의존 미충족은 유지한다."}
with (RUNS / "iter024_payload.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(payload, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps({"prepared": "iter024_payload.json", "guard": guard.stdout.splitlines()[0], "commits": len(commits), "tests": test_summary}, ensure_ascii=False))
