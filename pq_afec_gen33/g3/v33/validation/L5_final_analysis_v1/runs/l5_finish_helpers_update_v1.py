import sys
sys.dont_write_bytecode = True
import ast
from pathlib import Path

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
names = ("l5_finish_records_v1.py", "l5_final_commit_v1.py", "iter024_prepare_record_v1.py", "iter024_report_finish_v1.py")
texts = {name: (RUNS / name).read_text(encoding="utf-8") for name in names}
for name in names:
    texts[name] = texts[name].replace("L5_revert_check_01", "L5_revert_check_02")

def change(name, old, new):
    assert old in texts[name], (name, old)
    texts[name] = texts[name].replace(old, new)

name = "l5_finish_records_v1.py"
change(name, "### E11 완료 서버 응답의 관측 입력과 L5 채택 재검토", "### E11 완료 서버 응답의 관측 입력·수신 한도와 L5 채택 재검토")
change(name, "- 목적: L5의 두 새 S 산출법을 검증할 입력을 확보하고,", "- 목적: c12000의 none·C1 악화 +24.911063/+24.893233 ms와1461 B 패리티 잘림을 재검토한다. L5의 두 새 S 산출법을 검증할 입력을 확보하고,")
change(name, "- 할 일: T4의 관측 계약에서", "- 할 일: runs/L5_c12000_diagnosis_v1.md와 JSON을 읽는다. 각 L5 팔의27000연결 중26980회 수신 한도 초과와 C1 도착 관측 검열을 J7의 상한·wire 수정과 연결한다. 잘림·크기 모형·손실 우도의 기여를 사전 고정 대조로 분리하고 유리한 팔로 대체 채택하지 않는다. T4의 관측 계약에서")
change(name, "의존: T4. S4→T4는 L5/G1에 의존하지 않으므로", "의존: J7,T4. S0→J7와 S4→T4는 L5/G1에 의존하지 않으므로")
change(name, '"depends": ["T4"]', '"depends": ["J7", "T4"]')
change(name, 'for name in ("T4", "G1", "O4", "R3"):', 'for name in ("J7", "T4", "G1", "O4", "R3"):')
change(name, "L5의 역사 입력·실제 응답 식별과 채택 잔여 재검토.", "L5 c12000 악화·수신 한도·역사 입력·실제 응답 식별과 채택 잔여 재검토.")
change(name, "역사 관문 입력 부족을 포함한 판정 사유 때문에", "c12000의 none·C1 비열등 실패와 역사 관문 입력 부족 때문에")
change(name, "의존은 T4이며 S4→T4 경로는", "의존은 J7·T4이며 S0→J7와 S4→T4 경로는")
change(name, "- T4·G1: world_receive_index_proxy", "- J7: L5의c12000에서 δ130·W1410·패리티1461 B가1452 B 수신 한도를 넘었다. 각 L5 팔26980/27000회 초과이며 L1 none·C1은0회다. L5_c12000_diagnosis_v1.md·JSON을 상한·wire 계약 검증에 사용한다. 총 악화의 인과 기여는 별도 대조 전까지 미확인이다.\n- T4·G1: world_receive_index_proxy")
change(name, '    write_new(RUNS / "L5_disposition.md", "\\n".join(lines))', '''    lines[2:2] = ["c12000에서 none은 L1 0.121485→L5 25.032549 ms, 차이+24.911063, 조정 구간[23.775437,26.046689]다. C1은0.139315→25.032549, 차이+24.893233, 조정 구간[23.731675,26.054792]다. 두 셀 모두0.5 ms 허용치를 넘는 악화다. B5의 none/C1 차이-3.261987/-2.256370와 B6의-20.917953/-14.552788 ms 감소가 이 실패를 상쇄하지 않는다.", "", "사후 진단에서 full none·C1·ideal과 single none·C1 각각26980/27000연결이1461 B 패리티를 골라1452 B decoder 한도를 넘었다. C1 관측 검열26195회, 회신 없음785회가 있으며 categorical 갱신은26980회다. 세계 코드에서 잘린 패리티는 복구되지 않고 신용만 계상된다. 총 악화 중 이 요인의 기여는 별도 대조 전까지 미확인이다. L5_c12000_diagnosis_v1.md와 JSON에 입력 SHA·140추적·189000행을 보존했고 J7 및 E11에 연결했다.", ""]
    lines += ["복구 실행기 첫 시도는 Windows 경로의 역슬래시 해석 때문에 pytest를 시작하기 전에 실패했다. L5_revert_check_01의 로그와 JSON을 보존하고 경로를 repr로 직렬화한 v2로 재실행했다. L5_revert_check_02는351시험·548하위검사 통과, 소스 불변이다. 이 수정은 후보나 시험 기준을 바꾸지 않는다.", ""]
    write_new(RUNS / "L5_disposition.md", "\\n".join(lines))''')
change(name, "역사 관문 입력 부족을 포함한 판정 사유로 후보를", "c12000 none·C1의 약24.9 ms 악화와 역사 입력 부족으로 후보를")

name = "iter024_prepare_record_v1.py"
change(name, "역사 입력 부족을 포함한 채택 조건 미충족으로", "c12000 none·C1의 약24.9 ms 악화와 역사 입력 부족으로")
change(name, "역사 관문 입력이 없는 L5 후보를", "c12000 none +24.911063 ms(조정[23.775437,26.046689]), C1 +24.893233 ms(조정[23.731675,26.054792])로 실패한 L5 후보를")
change(name, "E11은 T4의 실제 응답 관측 뒤", "E11은 J7의 수신 상한과 T4의 실제 응답 관측 뒤")
change(name, "역사 입력 부족. L1복구", "c12000 약24.9 ms 악화·역사 입력 부족. L1복구")
change(name, "역사 입력 부족으로 미채택·활성L1상태4.", "c12000 none/C1 차이+24.911063/+24.893233 ms, 조정구간[23.775437,26.046689]/[23.731675,26.054792]. B5 none/C1 차이-3.261987/-2.256370, B6-20.917953/-14.552788 ms. 각 L5 팔 수신한도 초과26980/27000회. c12000 악화·역사 입력 부족으로 미채택·활성L1상태4.")
change(name, "최초 관측·검사기 실패와 기존 TemporaryDirectory 정리 사실은 반복23 기록을 보존했다.", "복구 실행기01은 Windows 경로의 역슬래시 해석 때문에 시험 시작 전에 실패했다. 경로 직렬화만 고친 v2의02는351시험·548하위검사를 통과했다. 최초 실패와 기존 TemporaryDirectory 정리 사실도 보존했다.")
change(name, "CID·패딩·1452 B 상한·PFEC", "L5_c12000_diagnosis_v1.md의1461 B 잘림·C1 검열을 읽고 CID·패딩·1452 B 상한·PFEC")
change(name, "원래30셀 {counts}, none/C1 B5/B6", "원래30셀 {counts}, c12000 none/C1 차이+24.911063/+24.893233 ms로 두 셀 비열등 실패. none/C1 B5/B6")

name = "iter024_report_finish_v1.py"
change(name, "역사 관문 입력 부족으로 미채택이며", "c12000 none·C1 약24.9 ms 악화와 역사 관문 입력 부족으로 미채택이며")
change(name, "반복24에서 이 규칙을 적용해", "반복24에서는 c12000의 none·C1 비열등 실패도 확인했으며 이 규칙을 적용해")
change(name, "E11은 T4 뒤에 수행한다.", "E11은 J7·T4 뒤에 수행한다.")

name = "l5_final_commit_v1.py"
change(name, "두 새 산출법의 역사 관문은 N·tail·완료 패킷목록 부족으로 미완료다.", "c12000 none·C1은 약24.9 ms 악화했고 각 팔26980/27000회 패리티 크기 초과를 진단했다.\\n복구351시험·548하위검사가 통과했다.\\n두 새 산출법의 역사 관문은 N·tail·완료 패킷목록 부족으로 미완료다.")
for name, text in texts.items():
    ast.parse(text, filename=name)
for name, text in texts.items():
    (RUNS / name).write_text(text, encoding="utf-8", newline="\n")
print("updated", len(texts))
