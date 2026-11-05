import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path

BASE = Path(r"C:\dev\codex_handoff\v33")
RUNS = BASE / "runs"
ROOT = Path(r"C:\dev\pq_afec_gen33")
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

def write_new(path, text):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)

def main():
    findings = read(RUNS / "L5_findings_v1.json")
    checked = read(RUNS / "L5_joint_artifact_check_v3.json")
    restored = read(RUNS / "L5_revert_candidate_v1.json")
    tests = read(RUNS / "L5_revert_check_02.json")
    assert checked["status"] == "pass" and checked["error"] is None
    assert findings["candidate_adopted"] is False and findings["historical_gate"] == "blocked_missing_inputs"
    assert findings["checker_sha256"] == sha(RUNS / "L5_joint_artifact_check_v3.json")
    assert restored["active_policy_exactly_matches_l1"] is True
    assert tests["exit_code"] == 0 and tests["unchanged"]
    assert all(sha(p) == h for p, h in tests["source_sha256"].items())
    state_path = BASE / "state/LOOP_STATE.json"
    state = read(state_path)
    assert state["current"] == "L5" and state["tasks"]["L5"]["status"] == "doing"
    assert "E11" not in state["tasks"]
    active = state["tasks"]["L5"]["active_computation"]
    end = read(active["expected_finished_receipt"])
    assert end["status"] == "complete" and end["exit_code"] == 0
    for name in ("L5_coverage.md", "L5_disposition.md", "L5_followup_registered_v1.json", "L5_finish_record_inputs_v1"):
        assert not (RUNS / name).exists()
    extra_path = BASE / "state/EXTRA_TASKS.md"
    extra = extra_path.read_text(encoding="utf-8")
    assert "### E11 " not in extra
    backup = RUNS / "L5_finish_record_inputs_v1"
    backup.mkdir()
    for path in (state_path, extra_path, BASE / "state/DECISIONS_NEEDED.md"):
        with (backup / path.name).open("xb") as stream:
            stream.write(path.read_bytes())
    card = """

### E11 완료 서버 응답의 관측 입력·수신 한도와 L5 채택 재검토
- 목적: c12000의 none·C1 악화 +24.911063/+24.893233 ms와1461 B 패리티 잘림을 재검토한다. L5의 두 새 S 산출법을 검증할 입력을 확보하고, 완료 응답·변화·혼합 후보의 채택 잔여를 다시 판단한다. 상태9 후보와 single 진단은 보존됐으며 활성 L1 상태4를 유지한다.
- 근거: runs/L5_disposition.md, L5_bench.md, L5_findings_v1.json, L5_joint_artifact_check_v3.json, L5_anchor_availability_v1.json, docs/L5_server_response.md. 감사 A1-12·A2-11·A2r1-10·A4-01·A8-06의 L5 범위를 맡는다.
- 할 일: runs/L5_c12000_diagnosis_v1.md와 JSON을 읽는다. 각 L5 팔의27000연결 중26980회 수신 한도 초과와 C1 도착 관측 검열을 J7의 상한·wire 수정과 연결한다. 잘림·크기 모형·손실 우도의 기여를 사전 고정 대조로 분리하고 유리한 팔로 대체 채택하지 않는다. T4의 관측 계약에서 실제 서버 패킷과 CRYPTO 구간을 연결해 완료 응답의 중복·재분할·작은 ACK·완료 뒤 바이트를 구분한다. C1 rxRetx는 업링크 CRC 개수이므로 다운링크 바이트에서 빼지 않는다. 과거 앵커/H c12000의 원패킷목록·N·tail을 출처와 함께 더 찾을 수 있는지 확인한다. 입력이 없으면 미확인을 유지한다. 새 개발 측정은 새 자료로 표시하고 역사 관문을 대신했다고 쓰지 않는다. 유효 모형 적합과 독립 검증을 분리한다. 당시 활성 정책과 근거 있는 새 후보의 비교 계획을 결과 전에 고정한다.
- 완료 기준: 두 산출법의 입력 출처·경계·한계와 원래 6개 앵커 밴드·H c12000 판정을 남긴다. 재구성할 수 없는 역사 관문은 blocked다. 실제 관측이 검증된 후보만 원래 W1 전체 시나리오에서 평가하고, none·C1의 30셀 비열등, B5 적응≤2연결, B6 최선 고정 대비 상한0.5 ms/연결, 보정 상한0 미만 감소와 역사 관문을 모두 만족할 때만 L5 완료 의존을 해제한다. G1이 끝난 뒤 정책을 바꾸면 같은 과제에서 거울·관문도 다시 확인한다.
- 하지 말 것: 없는 N·tail 생성, 맞춘 앵커를 독립 검증으로 표현, 과거 기록 덮어쓰기, 유리한 single 진단으로 교체 채택, 원래 표본·seed·세계·문턱 변경, 새로운 개발 자료로 과거 관문을 자동 통과, 봉인·확증 실행.
- 범위 연결: 자연 k는 O4, 실제 관측은 T4, Go 거울은 G1, J6 사전 ACK 후보의 불확실성은 E10, 과거 자료 해석은 R3의 기존 카드와 아래 보충 기록에 남는다.
- 예상 시간: 자료·설계·시험60~75분과 사전 고정 계산량. 의존: J7,T4. S0→J7와 S4→T4는 L5/G1에 의존하지 않으므로 순환 의존이 없다. 본래 TASKS 뒤 E10 다음에 등록한다.

## L5에서 확인한 기존 과제의 후속 범위 (반복24)

- J7: L5의c12000에서 δ130·W1410·패리티1461 B가1452 B 수신 한도를 넘었다. 각 L5 팔26980/27000회 초과이며 L1 none·C1은0회다. L5_c12000_diagnosis_v1.md·JSON을 상한·wire 계약 검증에 사용한다. 총 악화의 인과 기여는 별도 대조 전까지 미확인이다.
- T4·G1: world_receive_index_proxy는 실제 QUIC 패킷 번호나 CRYPTO 구간이 아니다. 완료 응답의 원본 데이터·재전송·ACK·재분할과 완료 이후 수신을 구분하고 인과 순서를 확인한다. 현재 연결의 완료 응답은 다음 결정에만 쓰며, 해당 연결의 관측 우도를 보정할 때는 결정 당시 문맥과 구분한다.
- O4: L5는 k 관측을 고치지 않았다. ClientHello CRYPTO 길이와 W의 자연 k 및 flushFlight의 첫 묶음 계수를 구분하는 기존 후속을 유지한다.
- R3: 과거 유효 모형 앵커6/6과 cert12000→11은 재현됐지만 L5의 두 새 산출법 검증은 아니다. p13 다섯 판본과 H 각팔1800행에 없는 패킷목록·N·tail을 추정해 넣지 않는다. A8-06의 서로 다른 DER 크기와 ML-KEM 계수1 예외7행 정정은 반복22 근거를 유지한다.
"""
    extra_path.write_text(extra.rstrip() + card + "\n", encoding="utf-8", newline="\n")
    state["tasks"]["E11"] = {"status": "todo", "iterations": 0, "commits": [], "note": "L5 c12000 악화·수신 한도·역사 입력·실제 응답 식별과 채택 잔여 재검토. 현재 L1 유지.", "depends": ["J7", "T4"], "optional": False}
    state["order"].append("E11")
    for name in ("J7", "T4", "G1", "O4", "R3"):
        state["tasks"][name].setdefault("handoff_notes", []).append(str(RUNS / "L5_followup_registered_v1.json"))
    state["tasks"]["L5"].update(candidate_adopted=False, blocker={"reason": findings["reason"], "followup": "E11", "depends": ["J7", "T4"]})
    active = state["tasks"]["L5"].pop("active_computation")
    active.update(status="complete", ended_kst=end["ended_kst"], completion_receipt=active["expected_finished_receipt"])
    state["tasks"]["L5"].setdefault("completed_computations", []).append(active)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    coverage = """# L5 감사 범위 기록

반복24. 상태9 후보의 구현·전체 개발 평가와 독립 검증을 마쳤다. c12000의 none·C1 비열등 실패와 역사 관문 입력 부족 때문에 채택하지 않고 활성 L1 상태4를 복구했다. 아래 이관은 실제 wire 검증이나 L5 완료를 뜻하지 않는다. 수치와 입력 해시는 L5_disposition.md, L5_bench.md, L5_findings_v1.json, L5_joint_artifact_check_v3.json, L5_anchor_availability_v1.json, L5_revert_check_02.json에 있다.

| 항목 | 상태 | 근거와 남은 범위 |
|---|---|---|
| A1-12 | 다른 과제로 넘김(E11,O4,G1,T4) | 물리 prefix·S 혼합 E[J] 후보와 엄격 경계를 구현했지만 채택하지 않았다. E11 카드가 S 산출법의 역사 입력과 전체 채택 재검토를 맡는다. k는 바꾸지 않았으며 O4의 자연 k·실제 분할, T4의 관측, G1의 거울을 기존 카드와 EXTRA_TASKS에 연결했다. |
| A2-11 | 다른 과제로 넘김(E11,G1,T4) | 모든 완료 응답을 y와 무관하게 반영하고 수신 index 중복·ACK·완료 뒤 바이트를 분리했다. 최근64관측·성분8개와 변화 초기화, 조건부 관측 우도를 후보·single 대조로 평가했다. B5/B6 실제 판정은 L5_bench.md에 보존했다. E11은 미채택 범위와 실제 QUIC 관측을 T4 결과 뒤 검토한다. |
| A2r1-10 | 다른 과제로 넘김(E11,G1,T4) | 원문 audit-learning.run1의 A2-10과 대응한다. 패킷 절반 기준 변화와 S 혼합 후보를 보존했고 C1 rxRetx를 다운링크 재전송 바이트로 쓰지 않았다. 전체 개발 결과와 복구는 L5_disposition.md에 있다. 실제 CRYPTO 재분할·서버 혼합 조건은 T4 및 E11로 남는다. |
| A4-01 | 다른 과제로 넘김(E11,T4,R3) | 보정식과 마지막 데이터그램을 뺀 물리 prefix를 모두 구현했다. 기존 유효 모형은 앵커6/6와 cert12000→11을 재현했으나 두 새 방법의 독립 검증이 아니다. H·p13에 N·tail·완료 패킷목록이 없어 역사 관문은 blocked_missing_inputs다. E11 카드와 R3 보충에 입력 부재·적합 구분을 적었다. |
| A8-06 | 다른 과제로 넘김(E11,E10,O4,R3,G1,T4) | 완료 응답 데이터만 S에 넣고 legacy A_pre를 신용에서 한 번 적용했다. 관측 A_pre·margin30인 J6와 구분하고 full과single을 평가했다. 후보는 미채택이다. E11은 깨끗한 응답·n_need, E10은 J6 잔여, O4·R3는 자연 k와 과거 자료 정정, G1·T4는 실제 관측·산술을 맡으며 기존 카드와 EXTRA_TASKS에 연결했다. |

이관5행, 빈칸0이다. A0 등 앞선 과제의 처리 범위는 유지한다. 세계의 수신 index 대조는 실제 QUIC 재전송 식별이나 전송 세계 전체를 독립 재구현한 검사가 아니다.
"""
    write_new(RUNS / "L5_coverage.md", coverage)
    summary = checked["summary"]
    lines = ["# L5 판정과 활성 정책", "", "반복24. L5 상태9 후보와 single 진단을 보존하고 활성 정책을 직전 L1 상태4로 복구했다. 활성 padfec·padfec3의 Python 파일은 시작 전 커밋 91432c35c122dd83bc946b2d53e68c96bd6fa14b와 바이트 단위로 같다.", "", f"채택하지 않은 사유: {findings['reason']}.", "", f"원래 none·C1 30셀 판정은 {findings['primary_counts']}다. 전체210대조는 {findings['all_comparison_counts']}다. 모드별 전후 평균과 seed95%·공유 MC·조정 구간을 L5_bench.md에 남겼다. 보정 상한0 미만인 주 비교는 {findings['primary_reduction_cells']}다.", "", f"B5/B6 관문: {findings['specific_gates']}. 역사 관문: {findings['historical_gate']}.", "", "두 새 산출법에 필요한 N·tail·완료 패킷목록이 과거 p13 다섯 판본과 H c12000 저널에 없다. 기존 유효 모형의 앵커6/6과 cert12000→11 재현을 새 방법의 검증으로 쓰지 않았다. cert3340의 불완전 첫 비행도 완료 응답으로 쓰지 않았다.", "", f"독립 검사 {checked['checks']}건이 {checked['elapsed_seconds']:.3f}초에 통과했다. 원자료 {summary['raw_runs']}실행, {summary['groups']}그룹, {summary['comparisons']}대조를 확인했다. 고정118행동에 원래 N131072·seed850001을 사용했다. 새 수집은1500실행·2055000연결이며 기존1500실행과 합쳤다.", "", "모든 완료 응답을 반영하는 후보는 실제 수신한 world data index를 중복 제거한다. 이는 QUIC CRYPTO 구간의 재분할을 검증한 어댑터가 아니다. S에는 data만 들어가고 legacy A_pre=41(k-1), u=0이면0을 신용에서 한 번 뺀다. 추가 margin은0이며 J6의 성능을 보고 교체 채택한 진단이 아니다. 현재 연결의 완료 크기는 해당 연결의 결정 전에 소급해 넣지 않는다.", "", "핵심 후보329시험·하위524개, 수집·관측52시험, 분석37시험·하위47개와 판정21시험이 통과했다. 합성 집계55289검사·12오류 주입 거부, 응답2340검사·15오류 거부, B5/B6 216264검사·11오류 거부, B9 초기화61검사를 보존했다. 복구 시험의 실제 결과는 L5_revert_check_02.log와 JSON에 있으며 실행 전후 소스 SHA가 같다. 상태4는 후보상태9를 거부한다.", "", "최초 실패와 검사기 정정도 보존했다. native hct 키, tuple Counter 비교, B6 fixture 식별자, B9 reset_each_connection 전달과 음성 대조 예외를 고쳤다. 전체 결과를 읽기 전에 기존 공통 개선 조건을 판정기 v3에 명시했다. 후보·세계·seed·표본·문턱은 바꾸지 않았다.", "", "E11에 역사 입력·실제 응답 식별과 채택 재검토를 등록했다. 의존은 J7·T4이며 S0→J7와 S4→T4 경로는 L5/G1에 의존하지 않는다. L5 blocked는 G1 선행 의존을 해제하지 않는다. 다음 J7은 S0만 의존하므로 진행할 수 있다. 실제 wire·Go·C1 회신 비용은 미검증이다. 결과는 개발 세계 시뮬레이션이며 확증이나 전체 동시95% 보장으로 표현하지 않는다.", ""]
    lines[2:2] = ["c12000에서 none은 L1 0.121485→L5 25.032549 ms, 차이+24.911063, 조정 구간[23.775437,26.046689]다. C1은0.139315→25.032549, 차이+24.893233, 조정 구간[23.731675,26.054792]다. 두 셀 모두0.5 ms 허용치를 넘는 악화다. B5의 none/C1 차이-3.261987/-2.256370와 B6의-20.917953/-14.552788 ms 감소가 이 실패를 상쇄하지 않는다.", "", "사후 진단에서 full none·C1·ideal과 single none·C1 각각26980/27000연결이1461 B 패리티를 골라1452 B decoder 한도를 넘었다. C1 관측 검열26195회, 회신 없음785회가 있으며 categorical 갱신은26980회다. 세계 코드에서 잘린 패리티는 복구되지 않고 신용만 계상된다. 총 악화 중 이 요인의 기여는 별도 대조 전까지 미확인이다. L5_c12000_diagnosis_v1.md와 JSON에 입력 SHA·140추적·189000행을 보존했고 J7 및 E11에 연결했다.", ""]
    lines += ["복구 실행기 첫 시도는 Windows 경로의 역슬래시 해석 때문에 pytest를 시작하기 전에 실패했다. L5_revert_check_01의 로그와 JSON을 보존하고 경로를 repr로 직렬화한 v2로 재실행했다. L5_revert_check_02는351시험·548하위검사 통과, 소스 불변이다. 이 수정은 후보나 시험 기준을 바꾸지 않는다.", ""]
    write_new(RUNS / "L5_disposition.md", "\n".join(lines))
    with (RUNS / "L5_disposition.md").open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(f"\n118행동 중 MC {summary['pool']['MC_jobs']}개에는 각각 N131072를 사용했고, 나머지 {summary['pool']['structural_jobs']}개는 동결 세계의 구조적 결과다. 선택 기준과의 기대 격차를 후회로 표기했으며, 정확한 참 최적값과의 격차를 증명한 수치가 아니다.\n")
    decisions = BASE / "state/DECISIONS_NEEDED.md"
    with decisions.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write("\nD18 반복24 결과: L5의 전체 개발 평가와 독립 검사를 마쳤으나 c12000 none·C1의 약24.9 ms 악화와 역사 입력 부족으로 후보를 채택하지 않았다. 원래 기준과 기본값을 유지하고 L1 상태4를 복구했다. 상세 판정은 runs/L5_disposition.md, 후속은 EXTRA_TASKS.md의 E11이며 사용자 응답을 기다리지 않는다.\n")
    receipt = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "followup": "E11", "depends": ["J7", "T4"], "coverage_rows": 5, "source_sha256": {str(p): sha(p) for p in (extra_path, decisions, RUNS / "L5_coverage.md", RUNS / "L5_disposition.md", RUNS / "L5_findings_v1.json")}, "script_sha256": sha(__file__)}
    write_new(RUNS / "L5_followup_registered_v1.json", json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"followup": "E11", "coverage_rows": 5, "candidate_adopted": False}))

if __name__ == "__main__":
    main()
