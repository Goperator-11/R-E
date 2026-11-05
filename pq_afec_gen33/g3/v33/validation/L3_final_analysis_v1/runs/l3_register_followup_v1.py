import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path


BASE = Path(r"C:\dev\codex_handoff\v33")
state_path = BASE / "state/LOOP_STATE.json"
extra_path = BASE / "state/EXTRA_TASKS.md"
out = BASE / "runs/L3_followup_registration_v1.json"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
state = json.loads(state_path.read_text(encoding="utf-8"))
assert state["iterations"] == 18 and state["current"] == "L3"
assert "E8" not in state["tasks"] and "E8" not in state["order"]
extra = extra_path.read_text(encoding="utf-8")
assert "### E8 " not in extra and not out.exists()
before = {str(p): sha(p) for p in (state_path, extra_path)}
card = """
### E8 비용 모형 보정 뒤 감시와 변화 감지 재검토
- 목적: J1·J2 이후 행동별 모형 오차와 실제 손실 변화의 혼동을 다시 검토하고, 선행 알고리즘의 적용 조건을 확인해 감시 코드를 개선한다. L3의 최종 채택·미채택 판정과 남은 범위를 출발점으로 삼는다.
- 근거: A2-04·A2-05·A2r1-04·A7-14, runs/L3_literature_review_v1.md, L3 최종 disposition·coverage·전체 개발 평가. 사용자가 추가한 지속적인 알고리즘 오류 수정·시험·선행연구 검토 목표를 반영한다.
- 할 일: J1·J2의 보정 결과와 당시 활성 정책을 읽는다. 기존 위험 보정 CUSUM, BOCPD, 적응 창 기반 초기화, 시간 전체 신뢰구간의 관측 가정과 역할을 구분한다. 조건부 지연 잔차 감시의 필요성도 별도 검토한다. 관측 이전 예측·누락·행동 선택·GE 의존성·초기화 다중성을 다루는 설계를 성능 전에 고정한다. 단독 수식·경계·직렬화 시험을 거쳐 정당화된 후보만 전체 W1로 평가한다. G1이 완료된 뒤 Python 정책을 바꾸면 같은 과제에서 Go 거울과 관문도 맞춘다.
- 완료 기준: 원문에 근거한 채택·배제 이유, 현재 정책과 새 후보의 전체 none·c1 전후 표, 정상 경보율·감지 지연·비용·바이트 및 식별 한계, 핵심 시험과 해당 관문, 감사별 coverage를 남긴다. 남아 있는 L3 채택 조건은 L3를 다시 열어 별도로 판정한다. 정당화된 후보가 없으면 그 이유를 기록한다.
- 하지 말 것: 현재 L3의 문턱·seed·표본 변경, 원래 결과 덮어쓰기, 유리한 진단 팔을 사후 채택, 불리한 셀 제외, 원문 조건을 확인하지 않은 보장 주장, TS 도입, 봉인·확증 실행.
- 예상 시간: 설계·구현60~75분과 고정 전체 벤치 실제 계산량. 의존: J1,J2. TASKS 본래 과제 뒤에 수행하며 부모 L3가 blocked여도 그 상태를 완료로 바꾸지 않고 재검토할 수 있다.

"""
with extra_path.open("a", encoding="utf-8", newline="\n") as stream:
    stream.write(card)
state["tasks"]["E8"] = {"status": "todo", "depends": ["J1", "J2"], "iterations": 0, "commits": [],
    "note": "L3 최종 판정 이후 비용 모형 보정과 선행 알고리즘 검토를 연결한 감시 후속. EXTRA_TASKS E8 참조."}
state["order"].append("E8")
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
receipt = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "task": "E8",
    "depends": ["J1", "J2"], "before_sha256": before, "after_sha256": {str(p): sha(p) for p in (state_path, extra_path)},
    "source_note_sha256": sha(BASE / "runs/L3_literature_review_v1.md"), "script_sha256": sha(__file__),
    "reason": "User continuous algorithm improvement goal; original L3 evaluation remains frozen"}
with out.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(receipt, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps(receipt, ensure_ascii=False))
