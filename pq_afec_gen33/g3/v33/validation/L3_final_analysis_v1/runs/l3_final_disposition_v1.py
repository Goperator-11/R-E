import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import collections
import datetime as dt
import hashlib
import json
from pathlib import Path


BASE = Path(r"C:\dev\codex_handoff\v33")
RUNS = BASE / "runs"
ROOT = Path(r"C:\dev\pq_afec_gen33")
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
f = read(RUNS / "L3_findings_v1.json")
check = read(RUNS / "L3_joint_artifact_check_v1.json")
revert = read(RUNS / "L3_revert_candidate_v1.json")
tests = read(RUNS / "L3_revert_check_01.json")
assert check["status"] == "pass" and check["error"] is None
assert f["candidate_eligible_for_adoption"] is False
assert f["provenance"]["check_sha256"] == sha(RUNS / "L3_joint_artifact_check_v1.json")
assert revert["active_policy_exactly_matches_l1"] is True
assert tests["exit_code"] == 0 and tests["unchanged"] is True
assert "218 passed, 461 subtests passed" in (RUNS / "L3_revert_check_01.log").read_text(encoding="utf-8")
primary_counts = dict(collections.Counter(row["gate"] for row in f["comparisons"] if row["primary"]))
all_counts = dict(collections.Counter(row["gate"] for row in f["comparisons"]))
assert primary_counts == {"pass": 43, "fail": 1, "inconclusive": 1}
assert all_counts == {"pass": 190, "fail": 8, "inconclusive": 12}
pair = lambda candidate, baseline, sid: next(r for r in f["comparisons"] if (r["candidate"], r["baseline"], r["scenario"]) == (candidate, baseline, sid))
bad = pair("l3_c1", "l1_c1", "B8_j20")
legacy = pair("l3_c1", "v31", "B8_j20")
assert bad["adjusted_lower_ms"] > .5 and legacy["gate"] == "inconclusive"
gates = f["absolute_and_alarm_gates"]
disposition = f"""# L3 판정과 활성 정책

2026-10-31 반복19. L3 후보는 채택하지 않고 과제를 blocked로 남긴다. 전체 평가와 독립 검증은 완료했지만 사전에 정한 채택 조건을 충족하지 못했다. 활성 padfec·padfec3의 모든 Python 파일은 L1 커밋 d845395c7e26637c853c76377139ed46b73907e0과 바이트 단위로 동일하게 복구했다.

| 사전 채택 비교 | 통과 | 실패 | 미확정 |
|---|---:|---:|---:|
| L3 none 대 L1 none | 15 | 0 | 0 |
| L3 c1 대 L1 c1 | 14 | 1 | 0 |
| L3 c1 대 v31 | 14 | 0 | 1 |

C1 B8_j20의 L1 대비 비용 차이는 {bad['mean_ms']:.6f} ms/연결이다. seed95% 구간 [{bad['seed_95_lower_ms']:.6f},{bad['seed_95_upper_ms']:.6f}], 공유 MC 폭 {bad['shared_mc_bound_ms']:.6f}, 조정 경계 [{bad['adjusted_lower_ms']:.6f},{bad['adjusted_upper_ms']:.6f}]로 하한도 허용 악화0.5를 넘는다. 같은 셀의 v31 대비 차이는 {legacy['mean_ms']:.6f}, 조정 경계 [{legacy['adjusted_lower_ms']:.6f},{legacy['adjusted_upper_ms']:.6f}]로 미확정이다. 전체45셀은 통과43·실패1·미확정1이며, 진단을 포함한210대조는 통과190·실패8·미확정12다.

C1 B1 절대 기대 후회는 {gates['B1_regret']['estimate']:.6f}, 조정 경계 [{gates['B1_regret']['adjusted_lower']:.6f},{gates['B1_regret']['adjusted_upper']:.6f}] ms/연결이다. 점추정은0.1 아래지만 상한은 넘으므로 미확정이다. B2는 {gates['B2_regret']['estimate']:.6f}, 조정 경계 [{gates['B2_regret']['adjusted_lower']:.6f},{gates['B2_regret']['adjusted_upper']:.6f}]로0.5 기준을 통과한다. B1 전체27000결정에서 경보9회, 1000결정당0.333333, seed95% 구간[0.095397,0.571269]로1 미만 기준을 통과한다. 감시 관측26980개를 분모로 한 별도 지표와 섞지 않는다. B9의 감시 관측 분모 비율은 n0/null이며 전체 결정 분모의0과 구분한다.

L1 대비 조정 상한이0 아래인 비용 감소 셀은 none의 B1·B6, c1의 B1·B2·B6이다. 예를 들어 C1 B1 차이는 -1.132398, B2는 -0.202831, B6는 -2.779400 ms/연결이다. 이 감소로 B8_j20 실패를 상쇄하지 않는다. C1 B5의+0.249302와 B7의+0.042830처럼0.5 이내의 증가도 전후 표에 남겼다. none은 L1 대비15셀을 통과하지만 v31 대비 B6·B7, v32 대비 B6 실패가 남는다. L3가 none의 기존 성능 문제를 해결했다고 쓰지 않는다.

단계별 진단에서 beta 대 record는 B5 +0.741469,[0.529123,0.953814], B8_j20 +0.811553,[0.521950,1.101155]로0.5 비열등에 실패한다. record 대 guard는15셀 통과지만 이를 사후 대체 후보로 채택하지 않는다. guard 대 L1의 B6와 전체 후보 대 beta의 B6도 미확정으로 보존했다. 이 결과는 감시 보정과 지터·모형 오차를 E8에서 검토할 근거이며 물리적 원인 식별은 아니다. 표본 추가나 문턱·seed 변경으로 이번 후보를 통과시키지 않는다.

알려진q 오류 주입250회는 전부 감지했고 미감지를 무한대로 포함한 중앙 지연은10결정이다. 정상 q=.03/.06/.42 각각200000연결의 경보는1000연결당0.065/0.165/0.56이었다. 이 통제 시험을 실제 손실 변화와 모형 오류의 식별 보장으로 쓰지 않는다. 전체 수집의 감시 가능한 실패연결은0이며 실패 분기는 단위 시험 범위다.

원형과 합친3300실행,165그룹,210대조,19문맥과 전체101행동을 검증했다. MC85개는N131072·seed850001, 구조적 무손실16개는 고정 세계 조건을 썼다. 독립 검사기는{check['checks']}검사를 통과했고 새 수집2466000연결의 감시 상태를 재생했다. 검사 범위는 출처·산술·판정·감시 상태다. 세계 시뮬레이터 자체의 독립 재구현이나 실제 네트워크 검증은 아니다. 전체 결과와 발행 SHA는 g3/v33/L3_benchmark_v1.json, 전후30행은 runs/L3_bench.md, 모든 대조는 L3_findings_v1.json/md에 있다.

후보 상태6과 세 진단 사본은 g3/v33/policy_snapshots/L3_v1, L3_guard_only_v1, L3_record_only_v1, L3_beta_only_v1에 보존한다. 활성 상태4는 후보 상태6을 거부한다. 후보 전용 시험3개는 experiments/v33/candidate_tests로 옮겼고 tests/test_v33_l3_candidate.py가 별도 프로세스에서 동결 후보를 검사한다. 복구 후 핵심·worker·보고·driver·격리 시험218개와 하위461개가 통과했다. 실행 전후 소스 해시는 같았다. 복구 정책은 L1과 정확히 같아 별도 새 후보로 전체 W1을 재실행하지 않는다.

실행·검사 실패 흔적도 남긴다. 반복18의 smoke 검증기 import 잔재와 보존기 clean 검사 순서 오류는 이미 수정 후 검증했다. 이번 반복에서는 PowerShell 시작 호출 뒤의 잘못된 LASTEXITCODE 확인이 예외를 냈으나 실제 독립 검사는 정상 시작됐다. 시작 기록과 PID를 확인해 중복 실행 없이 상태 기록만 이어 썼다. L3_validation_launch_shell_note.md에 근거를 남겼다.

연결 감사11항목은 L3_coverage.md에 범위별로 기록한다. E8은 J1·J2 이후 감시 후보와 조건부 지연 잔차, BOCPD·적응 창·시간 전체 신뢰구간의 적용 조건을 검토한다. 실제 C1 회신 비용·wire·Go는 T4·T5·G1, prior와 hazard는 L4, H 예측 정의는 R2에 남는다. L4는 L3 완료 의존이 풀리지 않아 건너뛰고 W1만 의존하는 J1을 바로 진행한다. L3 blocked를 done으로 취급하지 않는다.

모든 수치는 독립 사건 세계의 개발 평가다. 원형1800개 압축 연결 추적은 runs에 보존하며 해시·크기 목록을 최종 묶음에 남긴다. 나머지 원자료 요약·실행 기록·검사기·실패 기록·MC 결과·보고는 저장소의 L3_final_analysis_v1에 보존한다.
"""
coverage = """# L3 감사 범위 기록

2026-10-31 반복19. 후보의 구현과 전체 개발 평가를 끝냈지만 채택 기준에 실패해 활성 정책은 L1으로 복구했다. 과제 상태는 blocked다. 아래 이관은 이미 처리된 범위를 지우지 않으며 L3 후보의 활성 채택을 뜻하지 않는다. L3_disposition.md, L3_findings_v1.json/md, L3_joint_artifact_check_v1.json과 L3_revert_check_01.json이 근거다.

| 항목 | 상태 | 근거와 남은 범위 |
|---|---|---|
| A2-02 | 다른 과제로 넘김(E8,T4,T5) | L1의 도착 우도는 활성 상태에 유지한다. 이전 C1 증거에 따른 재평가 제거는 후보로 평가했지만 전체 후보의 C1 B8_j20 조정하한0.569639가0.5를 넘었다. E8 카드에서 감시와 함께 재검토한다. 실제 회신 비용·wire 결함은 기존 T4·T5 카드다. |
| A2-04 | 다른 과제로 넘김(E8,J1,J2) | 결정 전 예측을 쓰는 양방향 위험 보정 감시를 구현·재생했으나 채택하지 않았다. 조건부 지연 잔차 감시는 미구현이다. E8 카드에 이 범위를 명시했고 J1·J2의 비용 보정을 먼저 확인한다. |
| A2-05 | 다른 과제로 넘김(E8) | 가산 벌점·학습 차단 제거와 β 회복을 후보에서 검증했다. beta 대 record의 B5·B8_j20 비열등 실패 때문에 단독 또는 전체 후보 채택을 주장하지 않는다. E8에 보정과 모형 혼동 검토를 등록했다. |
| A2-10 | 다른 과제로 넘김(E8) | record 대 guard는15셀 통과했지만 진단 팔을 사후 대체 후보로 채택하지 않는다. C1 준비 조건에 따른 재평가 제거와 선택 사항인 KG 필요성은 E8의 설계 검토 범위다. |
| A2r1-03 | 다른 과제로 넘김(E8,L4) | 도착 우도·벌점·재평가·β·공통 변화의 단계별 비교를 전부 보존했다. 전체45채택셀은43통과·1실패·1미확정이다. 감시는 E8, 낮은 사전과 hazard 집합은 기존 L4 카드다. |
| A2r1-04 | 다른 과제로 넘김(E8) | 관측 행동별 갱신·실패F·현재 이전8개 준비 조건·여러 행동의 공통 반응을 구현하고 독립 재생했다. 알려진q 중앙10결정 감지와 실제 B1 경보 관문은 통과했지만 전체 후보는 미채택이다. E8에서 식별·초기화 가정을 검토한다. |
| A2r1-05 | 다른 과제로 넘김(L4,E8) | 순수 hazard 예측과 원형 두 세대 짝비교를 보존했다. 재주입 분포·hazard 집합 변경은 이번 후보에 섞지 않았으며 기존 L4 카드에 남긴다. L4의 L3 의존은 아직 풀리지 않았다. |
| A2r1-08 | 다른 과제로 넘김(E8) | C1 재평가 제거와 none 유지의 후보를 평가했다. C1 B1은 절대후회0.093952·조정상한0.127028로 미확정이고 B2는0.313869·상한0.379121로 통과한다. 전체 후보 실패를 선택 진단 결과로 덮지 않는다. |
| A7-14 | 다른 과제로 넘김(E8,J1,J2) | proposal doubtful 단서를 유지한다. 알려진q 시험은 손실 변화와 모형 오류를 식별하지 않으며 준비8회가 p 정확성을 보장하지 않는다. C1 B8_j20 악화와 beta 단계 실패를 E8에 연결했다. |
| A7-16 | 처리함(TS 금지와 검증 범위) | 이번 설계와 활성 L1 모두 TS를 도입하지 않는다. 후보의 C1 재평가 억제는 현재 이전 관측만 사용하도록 검사했다. 이 항목의 검증자 단서에 따라 TS가 모든 조건에서 나쁘다는 결론은 내리지 않는다. 재평가 후보 채택은 E8에 남고 S·k 불확실성 탐색은 이번 범위 밖이다. |
| Q-23 | 다른 과제로 넘김(J1,J2,R2,E8) | 감시 후보의 실패·미확정과 명목2 문제를 전체 표에 보존했다. 15% 조건부 지연 과소예측은 기존 J1·J2, H 예측 정의는 R2, 감시 잔여는 E8 카드다. 기존 RESULT_stage3와 봉인 판정은 바꾸지 않았다. |

처리함1행은 TS 금지와 해석 범위에 한정된다. 다른 과제로 넘김10행, 빈칸0이다. L3 전체 완료나 후보 채택으로 집계하지 않는다.
"""
paths = {RUNS / "L3_disposition.md": disposition, RUNS / "L3_coverage.md": coverage}
assert not any(p.exists() for p in paths)
for p, text in paths.items():
    with p.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
extra_path = BASE / "state/EXTRA_TASKS.md"
extra = extra_path.read_text(encoding="utf-8")
assert "### E8 " in extra and "반복19 판정 연결" not in extra
with extra_path.open("a", encoding="utf-8", newline="\n") as stream:
    stream.write("반복19 판정 연결: L3는 C1 B8_j20의 L1 대비 조정하한0.569639>0.5와 B1 절대후회 미확정 때문에 blocked다. E8이 채택 잔여와 A2-02·A2-04·A2-05·A2-10·A2r1-03·A2r1-04·A2r1-05·A2r1-08·A7-14·Q-23의 감시 범위를 이어받는다. A2-10의 선택 사항 KG도 필요성을 검토하되 진단 결과를 보고 이번 후보를 교체하지 않는다. 별도 prior·hazard는 L4, wire는 T4·T5, H 예측 정의는 R2에 남는다.\n")
with (RUNS / "L3_extra_tasks_after_disposition.md").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(extra_path.read_text(encoding="utf-8"))
state_path = BASE / "state/LOOP_STATE.json"
state = read(state_path)
assert state["iterations"] == 18 and state["current"] == "L3" and state["tasks"]["L3"]["status"] == "doing"
task = state["tasks"]["L3"]
active = task.pop("active_computation")
end_path = Path(active["expected_finished_receipt"])
end = read(end_path)
assert end["status"] == "complete" and end["checker_status"] == "pass"
active.update(status="complete", ended_kst=end["ended_kst"], completion_receipt=str(end_path))
task["completed_computations"].append(active)
task["candidate_adopted"] = False
task["blocker"] = {"reason": "C1 B8_j20 L1 noninferiority failed; B1 absolute regret and C1-v31 B8_j20 inconclusive",
    "followup": "E8", "depends": ["J1", "J2"]}
task["note"] = "전체 L3 평가와 독립 검증 완료. 채택 관문 미충족으로 활성 L1 복구·시험 통과. 최종 보존·반복 기록 중."
state["tasks"]["E8"]["note"] = "L3 미채택 후속. C1 B8_j20 악화·B1 절대후회 미확정과 모형 오류·손실 변화의 혼동을 J1/J2 뒤 재검토한다."
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
receipt = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "candidate_adopted": False,
    "primary_counts": primary_counts, "all_comparison_counts": all_counts, "next_task": "J1",
    "skipped_dependency": {"task": "L4", "reason": "L3 not done"},
    "document_sha256": {str(p): sha(p) for p in paths}, "script_sha256": sha(__file__),
    "findings_sha256": sha(RUNS / "L3_findings_v1.json"), "restore_tests_sha256": sha(RUNS / "L3_revert_check_01.json")}
with (RUNS / "L3_final_disposition_v1.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(receipt, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps(receipt, ensure_ascii=False))
