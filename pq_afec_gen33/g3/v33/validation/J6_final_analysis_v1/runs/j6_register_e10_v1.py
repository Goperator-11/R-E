import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path

BASE = Path(r"C:\dev\codex_handoff\v33")
RUNS = BASE / "runs"
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
findings_path = RUNS / "J6_findings_v1.json"
findings = read(findings_path)
assert findings["candidate_adopted"] is False
assert findings["primary_counts"] == {"pass": 28, "inconclusive": 2}
assert read(RUNS / "J6_revert_check_01.json")["exit_code"] == 0
state_path = BASE / "state/LOOP_STATE.json"
state = read(state_path)
assert state["iterations"] == 21 and state["current"] == "J6"
assert "E10" not in state["tasks"] and "E10" not in state["order"]
extra = BASE / "state/EXTRA_TASKS.md"
decisions = BASE / "state/DECISIONS_NEEDED.md"
before = {str(p): sha(p) for p in (state_path, extra, decisions)}
card = """

### E10 서로 다른 행동의 수치상 영분산과 J6 채택 재검토
- 목적: J6의 B12 c6000 두 주 비교에서 MC 경계가 미정의인 원인을 다룬다. 원래 J6는28통과·2미확정으로 미채택이며 활성 정책은 L1이다.
- 근거: runs/J6_uncertainty_diagnosis_v1.json, J6_findings_v1.json, J6_bench.md, J6_joint_artifact_check_v2.json, g3/v33/bench_reporting_rules.json. p0.08의(12,0,4) 대(7,0,4), p0.01의(12,0,2) 대(7,0,2)는 각131072표본에서 차이 약0.008 ms, 분산 약6.42e-29·5.24e-29였으나 행동 항등 증명이 없어 오차 경계가 null이다.
- 할 일: 동결 세계의 패킷 크기·직렬화·손실 난수 결합·복구·증폭 게이트·PTO·재시도·최대 시간 경계를 읽는다. 표본에서 일정한 차이가 난 이유와 가능한 예외 경로를 먼저 확인한다. 해당 조건 전체에 성립하는 경로별 상한·정확한 기대값 또는 별도 타당한 불확실성 증명 방법을 검토한다. 결과가 안 나온 경로를 없다고 가정하지 않는다. 새 계산이 필요하면 후보·세계·문턱을 그대로 두고 검증 계획과 적용 범위를 먼저 고정한다. 원래 보고서와 판정은 덮어쓰지 않는다. 당시 활성 정책이 달라졌으면 그 정책과의 전체 비교도 별도로 필요하다.
- 완료 기준: 유효한 증명이나 한계를 파일·시험·해시로 남긴다. 영분산이라는 이유만으로 폭0을 넣지 않고, 반례·PTO·손실·지터·경계 변화에서 잘못된 증명을 거부하는 검사를 둔다. J6를 재검토할 때는 원래30셀 비열등과 C1 감소 조건을 모두 적용하고 전체210대조를 보존한다. 기준을 만족할 때만 J6 완료 의존을 해제하며, 아니면 blocked와 이유를 유지한다.
- 하지 말 것: 원래 N·seed·0.5 ms 문턱 변경, 영분산을 항등식으로 단정, margin0 진단 팔 대체 채택, 유리한 표본만 추가, 새 결과를 독립 확증으로 표현, 보호 경로·동결 세계 수정.
- 범위 연결: A1-04·A4-03·A8-06의 J6 채택 잔여를 맡는다. S·n_need·혼합은 L5, 실제 ACK 관측은 T4, Go 산술은 G1, 자연 k와 문서는 O4·R3의 기존 카드와 반복22 보충 기록에 남는다.
- 예상 시간: 소스·증명·시험60~75분과 사전에 정한 계산량. 의존: W1. 실제 장애가 L5/O3 완료가 아니라 두 행동의 미확정 오차이므로 그 과제를 불필요한 선행 의존으로 추가하지 않는다. 본래 TASKS 뒤 E9 다음에 등록하며 J6 blocked를 자동으로 done으로 바꾸지 않는다.
"""
assert "### E10 " not in extra.read_text(encoding="utf-8")
with extra.open("a", encoding="utf-8", newline="\n") as stream:
    stream.write(card)
decision_note = "\n반복22의 D17 실행 결과: margin30 후보의 전체30셀 중28셀은 비열등 통과, B12 c6000의 none·C1 두 셀은 MC 경계 미정의로 미확정이다. 점추정 차이는 -2.473480/-2.506470 ms이나 C1의 보정 상한0 미만 감소 조건을 판정할 수 없어 채택하지 않았다. margin0 진단으로 대체하지 않고 상태8 후보·전체 결과를 보존한 뒤 활성 L1 상태4로 복구했다. E10에서 서로 다른 두 행동의 수치상 영분산과 증명 범위를 재검토한다. 기본값 변경이나 사용자 응답을 기다리는 장애가 아니다.\n"
assert "반복22의 D17 실행 결과:" not in decisions.read_text(encoding="utf-8")
with decisions.open("a", encoding="utf-8", newline="\n") as stream:
    stream.write(decision_note)
state["tasks"]["E10"] = {"status": "todo", "iterations": 0, "commits": [], "depends": ["W1"], "optional": False,
    "note": "J6 B12 c6000의 distinct-action zero-variance MC 경계 미정의를 증명·반례로 검토한다. 원래 J6 미채택과 모든 평가를 보존한다."}
state["order"].append("E10")
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
result = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "card": card,
          "decision_note": decision_note, "depends": ["W1"], "order_location": "after E9, after original TASKS",
          "before_sha256": before, "after_sha256": {str(p): sha(p) for p in (state_path, extra, decisions)},
          "findings_sha256": sha(findings_path), "diagnosis_sha256": sha(RUNS / "J6_uncertainty_diagnosis_v1.json"), "script_sha256": sha(__file__)}
out = RUNS / "J6_e10_registered_v1.json"
with out.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps({"registered": "E10", "depends": ["W1"], "record_sha256": sha(out)}))
