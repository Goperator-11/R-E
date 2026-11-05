import sys
sys.dont_write_bytecode = True
import ast
from pathlib import Path

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
code = (RUNS / "l5_findings_extract_v2.py").read_text(encoding="utf-8")
code = code.replace('    adopt = noninferior and specific and historical == "pass"', '    reductions = [row for row in rows if row["upper_bound_ms"] is not None and row["upper_bound_ms"] < 0]\n    adopt = noninferior and specific and historical == "pass" and bool(reductions)')
code = code.replace('    if historical != "pass":', '    if not reductions:\n        reasons.append("no primary reduction with adjusted upper below zero")\n    if historical != "pass":')
code = code.replace('"all predeclared primary, B5/B6 and historical gates pass"', '"all primary, B5/B6 and historical gates pass with at least one primary reduction"')
code = code.replace('        "historical_gate": historical,', '        "primary_reduction_cells": [row["candidate"]["generation"] + ":" + row["scenario"] for row in reductions],\n        "historical_gate": historical,')
code = code.replace('채택에는 none·C1의 B5 적응·B6 혼합 관문과 두 새 산출법의 역사 관문도 필요하다.', '채택에는 none·C1의 B5 적응·B6 혼합 관문과 두 새 산출법의 역사 관문, 주 비교의 보정 상한0 미만 감소가 적어도 한 셀 필요하다.')
ast.parse(code)
with (RUNS / "l5_findings_extract_v3.py").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(code)
path = ROOT / "tests/test_v33_l5_findings.py"
test = path.read_text(encoding="utf-8").replace("l5_findings_extract_v2.py", "l5_findings_extract_v3.py")
test += '''

def test_no_improvement_is_rejected_even_when_every_threshold_passes():
    value = fixture()
    for row in value["comparisons"]:
        row["upper_bound_ms"] = 0.0
    assert not findings.assess(value, ["B5", "B6"])["candidate_adopted"]
    value["comparisons"][0]["upper_bound_ms"] = -.01
    assert findings.assess(value, ["B5", "B6"])["candidate_adopted"]
'''
path.write_text(test, encoding="utf-8", newline="\n")
check = (RUNS / "l5_finish_check_v2.py").read_text(encoding="utf-8").replace("l5_findings_extract_v2.py", "l5_findings_extract_v3.py").replace("L5_finish_check_v2", "L5_finish_check_v3")
with (RUNS / "l5_finish_check_v3.py").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(check)
note = """# L5 판정기의 공통 개선 조건

반복24 시작에 TASKS의 L 공통 규칙을 다시 읽었다. '개선이 없거나 다른 시나리오가 0.5 ms/연결 넘게 나빠지면 그 변경을 되돌린다'는 조건이 있다. 판정기 v2는 비열등·B5/B6·역사 관문을 요구했지만, 모든 비용 차이가0인 경우를 별도로 거부하지 않았다.

성능 보고를 읽기 전에 v3에서 주 비교 none·C1 중 보정 상한0 미만인 셀이 적어도 하나 있어야 한다는 조건을 추가했다. C1에만 한정하는 추가 기준은 두지 않는다. 원래 유리한 점추정만으로 감소라고 부르지 않는 규칙을 따른다. 후보·세계·seed·표본·0.5 ms 문턱은 바꾸지 않았다. 역사 자료 관문 미완료는 이 조건과 독립적으로 여전히 채택을 막는다.

이후 사용하는 판정기는 l5_findings_extract_v3.py다. 출력 이름은 아직 생성되지 않은 L5_findings_v1.json이고, l5_revert_candidate_v2.py의 입력 계약은 그대로다. 새 시험은 모든 문턱을 통과하더라도 차이가0이면 거부하고, 역사 관문까지 통과한 합성 자료에서 확인된 감소가 있으면 허용하는지 검사한다.
"""
with (RUNS / "L5_disposition_rule_review_v1.md").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(note)
