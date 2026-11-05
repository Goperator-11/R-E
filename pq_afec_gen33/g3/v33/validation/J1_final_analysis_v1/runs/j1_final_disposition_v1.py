import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path


BASE = Path(r"C:\dev\codex_handoff\v33")
RUNS = BASE / "runs"
ROOT = Path(r"C:\dev\pq_afec_gen33")
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
f = read(RUNS / "J1_findings_v1.json")
check = read(RUNS / "J1_joint_artifact_check_v1.json")
tests = read(RUNS / "J1_revert_check_01.json")
assert check["status"] == "pass" and check["error"] is None
assert f["candidate_adopted"] is False and f["primary_counts"] == {"pass": 27, "inconclusive": 3}
assert f["c1_improvement_scenarios"] == []
assert f["checker_sha256"] == sha(RUNS / "J1_joint_artifact_check_v1.json")
assert tests["exit_code"] == 0 and tests["unchanged"]
assert "258 passed, 490 subtests passed" in (RUNS / "J1_revert_check_01.log").read_text(encoding="utf-8")
assert read(RUNS / "J1_revert_candidate_v1.json")["active_policy_exactly_matches_l1"] is True
rows = {(r["mode"], r["scenario"]): r for r in f["primary_rows"]}
assert {sid for (mode, sid), r in rows.items() if r["gate"] != "pass"} == {"B7", "B8_j10", "B8_j20"}
state_path = BASE / "state/LOOP_STATE.json"
state = read(state_path)
assert state["iterations"] == 19 and state["current"] == "J1" and state["tasks"]["J1"]["status"] == "doing"
assert "E9" not in state["tasks"]
extra_path = BASE / "state/EXTRA_TASKS.md"
assert "### E9 " not in extra_path.read_text(encoding="utf-8")

disposition = """# J1 판정과 활성 정책

2026-10-31 반복20. J1은 전체 평가와 독립 검증을 마쳤지만 채택 조건을 충족하지 못해 blocked로 남긴다. 후보 상태7은 보존하고 활성 정책은 직전 L1 상태4로 복구했다. 복구한 padfec·padfec3의 Python 파일은 반복19 끝 커밋 c81bbdf2dd17348a3a36707b3013ee3451fd97d2와 바이트 단위로 같다. 이 커밋의 정책은 채택 L1 d845395c7e26637c853c76377139ed46b73907e0과 같다.

| 채택 비교 | 통과 | 실패 | 미확정 |
|---|---:|---:|---:|
| J1 none 대 L1 none | 12 | 0 | 3 |
| J1 c1 대 L1 c1 | 15 | 0 | 0 |

none의 B7 비용 차이는 +0.318209 ms/연결, 조정 경계는 [0.081258,0.555160]이다. B8_j10은 -1.821025,[-5.640545,1.998494], B8_j20은 -7.010346,[-15.079136,1.058444]다. 세 상한 모두 허용 악화0.5를 넘는다. 이 결과는 비열등 미확정이며 0.5 초과 악화가 확정됐다는 뜻은 아니다. B8 두 조건의 큰 음수 평균만 보고 통과시키지 않는다.

C1에서는 조정 상한이0 미만인 감소 셀이 없다. B12_c12000의 seed95% 구간은 [-0.002436,-0.000021]이지만 공유 MC 폭을 포함하면 상한0.000358이므로 사전 감소 조건을 통과하지 않는다. B2 차이는 +0.162446,[0.024294,0.300598]로 증가했지만 0.5 제한 안이다. none B1·B5·B6의 감소 -1.082294/-0.807454/-5.753805는 다른 셀의 미확정이나 C1 감소 조건 부재를 상쇄하지 않는다.

전체210대조는 통과194·실패1·미확정15다. 유일한 실패는 none 대 v31의 B7 +1.679258,[1.385826,1.972691]이다. C1 대 v32의 B6도 조정 상한0.534898로 미확정이다. 원래30셀 채택 비교와 과거 세대 대조를 구분한다. C1 B1의 선택 기준 대비 기대 격차는1.235436,[0.909333,1.561538]로0.1 목표 실패이고, B2는0.679146,[0.435380,0.922911]로0.5 목표 미확정이다. 이는 정확한 참 최적값에 대한 후회가 아니라 동결한 선택 기준과의 차이다.

비용만 바꾼 진단은 none B6에서 L1 대비 -4.461986,[−5.431046,−3.492926]이고, 전체 후보가 그 진단에 비해 추가로 -1.291819,[−1.977863,−0.605775]다. C1 B2는 비용 변경만으로 +0.118739,[0.006514,0.230964], 등급 변경이 추가된 전체 후보에서 진단 대비 +0.043707,[0.005387,0.082027]이다. 비용과 등급의 기여를 기록하되 진단 팔을 사후 대체 후보로 채택하지 않는다. seed·표본·세계·문턱은 바꾸지 않았다.

고정 행동의 과거 관측에서는 비용 모형 오차가 줄었다. 15% (0,0,4)의 관측 평균123.618824와 모형116.872472의 차이6.746353은 꼬리 항 뒤2.980005 ms다. (0,3,1)은 관측109.742817, 모형104.446326의 차이5.296492에서3.540155 ms가 남는다. 모형 추가분3.766348/1.756336과 관측 초과 꼬리4.289507/1.672236을 구분한다. 카드의 약4.3/1.7을 모형이 정확히 재현했다고 쓰지 않는다. 표본 RTT를 쓰는 교차점0.2147906과 참 RTT만 쓰는0.2173651도 구분했다.

A0와 같은20개 관측 그룹을 재현했고 IID·GE 재가중480개 확률 합 검사를 통과했다. 이 대수 검사는 GE의 연속 later 손실이 p²라는 물리 근거가 아니다. 기존 W0의7조건을 다시 표로 만들었으며 세계를 재표본화하지 않았다. 15% 두 고정 행동의 W0 잔차는 (0,3,1)6.582348→4.843137, (0,0,4)7.214780→3.495664 ms다. 처리 시간, 첫 비행 실패 타이머, GE·RTT200 오차는 남는다.

감사의 과거1비트 정보량 정정582·121·86을 재현했다. J1 3등급에서 log(10)/KL 관측 척도는 (0,0,4)450.879와 (0,3,1)70.196이다. 이는 고정 행동 IID 모형의 평균 로그우도 누적 척도이며 실제 적응 시간이나 고착 해소 보장이 아니다. 자세한 식과 출처는 J1_likelihood_information_v1.py/json/md에 있다.

새1500실행·2055000연결과 기존1500실행을 합쳐3000실행,150그룹,210대조를 검증했다. 문맥19개와 전체100행동 중84개 MC는 N131072·seed850001을, 구조적 무손실16개는 동결 세계 조건을 사용했다. 독립24667219검사가 통과했고 새 연결의 도착 우도1155349회, 등급 우도844419회, 예측만55232회를 대조했다. 유효 실패연결은0이며 실패 분기는 단위 시험 범위다. 출처·산술·판정·등급 검증이며 세계 자체의 독립 재구현이나 실제 네트워크 검증은 아니다.

seed Student t 95% 구간과 문맥·행동 집합의 MC 정규근사99% 보정은 별도의 범위를 가진다. 합친 경계를 전체 동시95% 보장으로 해석하지 않는다. 실제 C1 회신 비용은 D14의 수동 관측 근사에 따라 세계 비용에 포함되지 않는다.

후보와 비용만 바꾼 사본은 g3/v33/policy_snapshots/J1_v1과 J1_cost_only_v1에 남긴다. 상태4는 후보 상태7을 거부한다. 후보 꼬리 시험과 model-world 어댑터는 experiments/v33/candidate_tests로 보존했고 별도 프로세스에서 검사한다. 활성 L1 복구 후258개·하위490개가 통과했고 실행 전후 소스 해시가 같았다. 정확히 복구한 L1에 새 W1 표본을 추가하지 않는다.

준비 중 발생한 시험·보존 오류도 보존했다. 처음에는 model-world 원자와 일부 시험 기대값이 꼬리 항을 반영하지 못했고, float 경계 비교와 수집 fixture도 수정 후 통과했다. 새 묶음 생성 뒤 git clean을 요구한 보존 순서 오류는 생성물 SHA를 검증하고 해당 경로만 커밋하는 방식으로 고쳤다. 보호 경로 검사는16:34 KST GUARD_OK였고 기존 볼트6경고의 변경 주체는 미확인이다. 보호 파일을 직접 고치지 않았다.

E9에 J1 재검토를 등록한다. O3·J5 뒤 none의 지터·s2c 손실과 비용·등급 모형 차이를 검토한다. J2를 E9 의존에 넣으면 J2가 J1 완료를 기다리는 순환이 생기므로 넣지 않는다. J1 blocked를 done으로 취급하지 않으며 J2·J4는 계속 의존 미충족이다. 다음 과제는 W1만 의존하는 J6다. 실제 처리 상수·실패 비용·wire·Go와 H 예측 정의는 각각 기존 과제에 남는다.
""".replace("−", "-")

coverage = """# J1 감사 범위 기록

반복20. 전체 후보를 구현하고 평가했지만 채택 조건 미충족으로 활성 L1을 복구했다. 아래는 남은 범위를 이관하는 기록이며 J1 완료나 실제 기제 확인을 뜻하지 않는다. 근거는 J1_disposition.md, J1_bench.md, J1_findings_v1.json, J1_joint_artifact_check_v1.json, J1_revert_check_01.json이다.

| 항목 | 상태 | 근거와 남은 범위 |
|---|---|---|
| A1-01 | 다른 과제로 넘김(E9,J5,G1,T4) | 둘째 비행 비용·등급 후보, 첫 비행 질량 보존, 교차점0.2147906, 과거20그룹·확률480검사와 정보량 정정을 검증했다. 모형 추가3.766348/1.756336과 관측 초과4.289507/1.672236은 구분한다. none3셀 미확정 및 C1 감소 조건 부재로 채택하지 않았다. E9 카드에 재검토, 기존 J5에 GE, G1에 Go, T4에 실제 손실·PTO 계측을 남긴다. |
| A2-17 | 다른 과제로 넘김(E9,J2,J3,T4,E8) | 2R 꼬리를 F 전체와 구분해 구현·평가했지만 미채택이다. J1_bench.md의30행과 비용만 변경한 진단을 보존했다. 처리 상수는 J2, 첫 비행 실패 타이머는 J3, 실제 ACK 손실 식별은 T4, 감시는 E8이며 각각 기존 카드와 E9 연결 기록에 있다. |
| A8-08 | 다른 과제로 넘김(E9,J2,J3,O3,T4) | 고정 W0 7조건 오차와 관측 잔차를 분리했다. 15% 잔차가 남으며 세 원인을 동시에 해결했다고 하지 않는다. 처리·실패 타이머·RTT·기제 식별은 기존 J2·J3·O3·T4, 미채택 꼬리 후보는 E9다. |
| Q-23 | 다른 과제로 넘김(E9,J2,R2,E8) | 15% 과소예측의 꼬리 범위를 평가했고 결과를 보존했다. 미채택 후보는 E9, 처리 시간은 J2, H 예측 정의는 R2, 감시·고착은 L1·L3 기록과 E8에 남는다. 기존 RESULT_stage3와 봉인 판정은 바꾸지 않았다. |

이관4행, 빈칸0이다. 선행 A0 재현 기록이나 다른 과제의 처리 범위는 유지한다.
"""
extra = """
### E9 둘째 비행 꼬리 후보의 관측 모형과 채택 재검토
- 목적: J1 미채택 원인인 none B7·B8_j10·B8_j20 비열등 미확정과 C1 감소 조건 부재를 다시 검토한다. 전체30셀27통과·3미확정, 전체210대조194통과·1실패·15미확정의 원자료를 출발점으로 삼는다.
- 근거: J1_disposition.md, J1_bench.md, J1_findings_v1.json, J1_joint_artifact_check_v1.json, J1_historical_reference_v1.json, J1_w0_error_table_v1.json. 연결 감사는 A1-01·A2-17·A8-08·Q-23이다.
- 할 일: O3·J5 이후 당시 활성 정책과 비용 모형의 변경 범위를 읽는다. none의 지터·s2c 손실에 대한 등급 혼동, 첫 비행과 둘째 비행의 조건부 손실, 비용·우도 보정의 차이를 검토한다. 정당화된 새 설계와 전체 W1 비교를 성능 전에 고정한다. 이번 미확정을 해소하려고 사후 표본을 추가하거나 진단 팔을 교체 채택하지 않는다. 새 설계의 근거가 없으면 J1 blocked를 유지한다.
- 완료 기준: 원래 J1의 고정 팔·교차점·확률 합·W0 오차표를 다시 확인하고, 당시 활성 정책과의 원래 전체 시나리오 비열등 및 사전 개선 기준을 통과한다. 통과했을 때만 J1 완료 의존을 해제할 수 있다. 단위 시험·직렬화 거부·출처 검증·기여 분리·감사 추적이 필요하다.
- 범위 연결: 처리 상수는 J2, 실패 타이머는 J3, 실제 ACK/PTO 계측은 T4, Go는 G1, 감시는 E8, H 정의는 R2에 남는다. J2가 J1 완료를 기다리므로 E9에 J2 의존을 추가하지 않는다. 처리 보정이 반드시 선행돼야 한다는 근거가 생기면 독립 교정 하위 과제를 명시적으로 나누고 순환 의존을 만들지 않는다.
- 예상 시간: 설계·구현60~75분과 고정 전체 벤치 계산량. 의존: O3,J5. 본래 과제 뒤에 수행하며 J1 blocked는 자동으로 done이 되지 않는다.
"""
for path, value in ((RUNS / "J1_disposition.md", disposition), (RUNS / "J1_coverage.md", coverage)):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(value)
with extra_path.open("a", encoding="utf-8", newline="\n") as stream:
    stream.write(extra)
with (RUNS / "J1_extra_tasks_after_disposition.md").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(extra_path.read_text(encoding="utf-8"))
task = state["tasks"]["J1"]
active = task.pop("active_computation")
end_path = Path(active["expected_finished_receipt"])
end = read(end_path)
assert end["status"] == "complete" and end["checker_status"] == "pass"
active.update(status="complete", ended_kst=end["ended_kst"], completion_receipt=str(end_path))
task["completed_computations"].append(active)
task["candidate_adopted"] = False
task["blocker"] = {"reason": "none B7/B8_j10/B8_j20 noninferiority inconclusive and no C1 adjusted upper below zero", "followup": "E9", "depends": ["O3", "J5"]}
task["note"] = "전체 J1 평가·독립 검증 완료. 미채택 후 활성 L1 복구·258시험/490하위 통과. 최종 보존·반복 기록 중."
state["tasks"]["E9"] = {"status": "todo", "iterations": 0, "commits": [], "note": "J1 미채택 후속. 관측 모형과 꼬리 비용·우도를 O3/J5 뒤 재검토한다.", "depends": ["O3", "J5"], "optional": False}
state["order"].append("E9")
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"candidate_adopted": False, "followup": "E9", "next_task": "J6", "coverage_rows": 4}))
