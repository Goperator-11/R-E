import sys
sys.dont_write_bytecode = True
import ast
from pathlib import Path

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
note = """# L5 독립 검사의 B9 이력 초기화

수집 완료 전 소스 대조에서 B9의 reset_each_connection을 독립 응답 검사 호출이 넘기지 않는 누락을 발견했다. 후보와 수집기는 원래부터 매 연결의 목적지 상태를 초기화한다. 검사 helper v3도 프로토콜의 값을 읽어 같은 조건으로 빈 이력을 재구성한다. 최종 S 중앙값의 정수·실수 JSON 표현은 값 동등성으로 대조한다.

기존 검사기 v1·v2와 결과는 보존했다. 사용할 조합은 l5_joint_artifact_check_v3.py, l5_response_audit_v3.py, l5_validation_driver_v2.py, launch_l5_validation_v2.ps1이다. 검증 단계의 실행 기록 이름은 아직 실행되지 않은 L5_validation_v1을 유지한다. 판정과 복구 스크립트는 l5_findings_extract_v2.py, l5_revert_candidate_v2.py다.

합성 cold 연결 세 개는 각각 창 크기1을 유지한다. 초기화를 끈 음성 대조는 size_distribution 키가 없는 cold 결정을 거부했다. 이 거부가 KeyError라 최초 fixture의 ValueError만 받는 부분에서 중단됐다. 음성 대조의 허용 예외에 KeyError를 더했고 최초 fixture는 별도 보존했다. 정책과 기준, 수집 원자료는 바꾸지 않았다.
"""
with (RUNS / "L5_checker_reset_revision_v1.md").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(note)
code = (RUNS / "l5_finish_preparation_bundle_v1.py").read_text(encoding="utf-8")
code = code.replace("L5_finish_preparation_v1", "L5_checker_reset_preparation_v1").replace("L5_finish_check_v1.json", "L5_finish_check_v2.json")
begin = code.index("resume = {")
end = code.index("sources = [", begin)
names = ["l5_prepare_checker_reset_v1.py", "l5_response_audit_v3.py", "l5_joint_artifact_check_v3.py", "l5_validation_driver_v2.py",
         "launch_l5_validation_v2.ps1", "l5_response_fixture_check_v4.py", "l5_response_fixture_check_v4_initial.py", "L5_response_fixture_check_v4.json",
         "l5_checker_fixture_check_v3.py", "L5_checker_fixture_check_v3.json", "l5_adaptation_fixture_check_v4.py", "L5_adaptation_fixture_check_v4.json",
         "l5_findings_extract_v2.py", "l5_revert_candidate_v2.py", "l5_finish_check_v2.py", "L5_finish_check_v2.json", "L5_finish_check_v2.log",
         "L5_checker_reset_revision_v1.md", "l5_checker_reset_bundle_prepare_v1.py", "l5_checker_reset_bundle_v1.py", "L5_collection_progress_10.json",
         "L5_full_v1.finished.json", "l5_prepare_phase_launchers_v1.py", "l5_prepare_joint_plan_bundle_v1.py"]
code = code[:begin] + "names = " + repr(names) + "\n" + code[end:]
code = code.replace("L5_finish_preparation_commit_message.txt", "L5_checker_reset_commit_message.txt").replace("L5_finish_preparation_commit_receipt.json", "L5_checker_reset_commit_receipt.json")
begin = code.index('message.write_text(')
end = code.index('\nsubprocess.run(git + ["commit"', begin)
code = code[:begin] + 'message.write_text("WIP(L5): 독립 검사에 연결별 초기화 계약 반영\\n\\nB9의 목적지 초기화를 검사 helper에 연결했다. 후보·수집 코드는 그대로다.\\n응답120연결과 오류15건, 합성 cold 초기화, 전체 대조와 B5·B6 시험을 통과했다.\\n판정20시험 통과. 전체1500수집이 오류 없이 끝났고 성능은 아직 읽지 않았다.\\n", encoding="utf-8", newline="\\n")' + code[end:]
ast.parse(code)
with (RUNS / "l5_checker_reset_bundle_v1.py").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(code)
