import sys
sys.dont_write_bytecode = True
import hashlib
from pathlib import Path

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(path, text):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
checkpoint = (RUNS / "j6_checkpoint_phase_v1.py").read_text(encoding="utf-8").replace("j6", "l5").replace("J6", "L5")
checkpoint = checkpoint.replace("e94961a4f472bc043374cb0ec15034583acc2f34", "91432c35c122dd83bc946b2d53e68c96bd6fa14b")
save(RUNS / "l5_checkpoint_phase_v1.py", checkpoint)
validation = (RUNS / "j6_validation_driver_v1.py").read_text(encoding="utf-8").replace("j6", "l5").replace("J6", "L5")
validation = validation.replace("cf7d3e7c3ebfb856a75f70f1001048a361d1db24630bccd821dc1b07490d7ee1", sha(RUNS / "l5_joint_artifact_check_v2.py"))
save(RUNS / "l5_validation_driver_v1.py", validation)
launcher = (RUNS / "launch_j6_validation_v1.ps1").read_text(encoding="utf-8-sig").replace("j6", "l5").replace("J6", "L5")
launcher = launcher.replace("17ed0af865081af2632f70f46cf358014897925bca6aee543de04950867c0d98", sha(RUNS / "l5_validation_driver_v1.py"))
save(RUNS / "launch_l5_validation_v1.ps1", launcher)
note = """# L5 분석 준비 검증

2026-10-31 KST. 전체 수집 결과의 성능을 읽기 전에 검사기를 고정했다.

보고기는 원래 seed와 길이의 합동 3,000실행, 150그룹, 210대조를 유지한다. 주 비교는 none·C1 각각 L1 대비 15셀이다. single은 크기 혼합 기여를 보는 진단이다. 역사 자료 관문은 입력 부재로 미완료이며 세계 평가로 대체하지 않는다.

독립 검사기는 원자료·출처 해시와 seed 통계·공유 MC 경계를 재계산한다. 수신 기록에서 중복을 제외한 완료 응답, 결정 전 분포, 완료 응답에 조건화한 손실 문맥, 최근 창과 성분 이력을 별도로 재구성한다. B5는 연속 두 결정과 관측 두 개 이내 시작을 구분하고, 미정의 비용을 미확정으로 남긴다. B6는 사전 기준인 혼합 최선 고정 대비 보정 상한 0.5 ms/연결 이하를 적용한다.

합성 150그룹·210대조에서 55,289검사와 오류 주입 12건 거부를 확인했다. B5 60사례·B6 40그룹 시험은 정상·오류 경로를 합쳐 216,264검사를 수행했고 오류 11건을 거부했다. 완료 응답 smoke 120연결의 2,340검사와 오류 15건 거부도 통과했다. 분석 시험 37개와 하위 47개가 통과했다. 전체 수집 성능과 최종 관문은 아직 미확인이다.

처음 만든 B5 검사기는 tuple 키 Counter를 JSON으로 비교하려다 실패했다. 직접 계수 동등성으로 정정한 v2 helper를 사용한다. 다음 B6 합성 자료는 원래 B6 식별자를 cell로 바꿔 보고기의 해당 관문이 없는 상태였다. 실제 B6 식별자 하나와 나머지 B1 셀로 시험 구성을 정정했다. 최초 소스·실패 기록은 보존했다. 정책·seed·문턱은 바꾸지 않았다.

새 L5 시험의 임시 폴더는 이후 runs/L5_test_fixtures에 보존한다. 앞선 시험의 기본 TemporaryDirectory 정리는 이미 실행됐고 그 파일의 내용은 복구할 수 없다. 기존 회귀 시험에도 임시 파일 삭제가 있어, 이후 필요한 재실행은 보존 어댑터를 먼저 적용한다. 보호 경로에서 삭제가 발생했다는 근거는 없다.

이 검사는 전송 세계의 별도 구현이나 실제 네트워크 검증이 아니다. 손실 사후의 모든 확률 산술을 별도 재구현한 검사도 아니다. 수신 index는 세계 모형의 대용 관측이다.
"""
save(RUNS / "L5_analysis_preparation_v1.md", note)
code = (RUNS / "j6_analysis_bundle_v1.py").read_text(encoding="utf-8").replace("j6", "l5").replace("J6", "L5")
code = code.replace("L5_final_checks_01", "L5_analysis_02")
code = code.replace('("L5_checker_fixture_check_v2", "L5_preflight_fixture_check_v2")', '("L5_checker_fixture_check_v2", "L5_response_fixture_check_v3", "L5_adaptation_fixture_check_v3")')
begin = code.index('selected.update(RUNS / name')
end = code.index('entries = []', begin)
code = code[:begin] + '''selected.update(RUNS / name for name in ("launch_l5_joint_plan_v1.ps1", "launch_l5_validation_v1.ps1",
    "L5_analysis_01.json", "L5_analysis_01.log", "L5_analysis_02.json", "L5_analysis_02.log",
    "L5_checker_fixture_check_v1.json", "L5_checker_fixture_check_v2.json", "L5_response_fixture_check_v2.json",
    "L5_response_fixture_check_v3.json", "L5_adaptation_fixture_check_v3.json", "L5_adaptation_fixture_initial_failure.json",
    "L5_adaptation_fixture_second_failure.json", "L5_analysis_preparation_v1.md", "L5_collection_commit_receipt.json",
    "L5_collection_launch_v1.json", "L5_collection_progress_03.json", "L5_collection_progress_04.json", "L5_collection_progress_05.json", "iter023_checkpoint_01.json"))
selected.update(path for path in (RUNS / "L5_test_fixtures").rglob("*") if path.is_file())
''' + code[end:]
code = code.replace(', "tests/test_v33_l5_findings.py"', '')
code = code.replace('L5 analysis and independent arithmetic, grade and preflight checker preparation during collection; no full performance read', 'L5 analysis and independent arithmetic, grade, complete response and adaptation checker preparation during collection; no full performance read')
begin = code.index('    stream.write("WIP(L5)')
end = code.index('\nresult = subprocess.run', begin)
code = code[:begin] + '    stream.write("WIP(L5): 전체 짝비교와 완료 응답 독립 검사를 준비\\n\\n분석37시험·하위47개 통과. 합성150그룹·210대조와 오류12건 거부.\\n응답120연결2340검사·오류15건, B5·B6 검사와 오류11건 거부.\\n최초 검사기 두 가정 오류를 정정하고 실패 자료를 보존했다.\\n전체 수집과 성능 관문은 진행 중이며 역사 관문은 입력 부족이다.\\n")' + code[end:]
save(RUNS / "l5_analysis_bundle_v1.py", code)
