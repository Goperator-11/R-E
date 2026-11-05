import sys
sys.dont_write_bytecode = True
import ast
from pathlib import Path

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
code = (RUNS / "j6_joint_plan_bundle_v1.py").read_text(encoding="utf-8").replace("j6", "l5").replace("J6", "L5")
begin = code.index("names = [")
end = code.index('\nassert read(RUNS / "L5_phase_launcher_parse_v1.json")', begin)
names = ["L5_joint_action_family_v1.json", "L5_joint_plan_v1.started.json", "L5_joint_plan_v1.finished.json", "L5_joint_plan_v1.stdout.txt",
         "L5_joint_plan_v1.stderr.txt", "L5_joint_plan_launch_v1.json", "L5_joint_plan_launcher_v1.stdout.txt", "L5_joint_plan_launcher_v1.stderr.txt",
         "launch_l5_joint_run_v1.ps1", "launch_l5_joint_report_v1.ps1", "launch_l5_validation_v1.ps1", "l5_prepare_phase_launchers_v1.py",
         "L5_phase_launcher_preparation_v1.json", "L5_phase_launcher_parse_v1.json", "l5_joint_progress_v1.py", "iter023_checkpoint_02.json",
         "L5_analysis_commit_receipt.json", "L5_finish_preparation_commit_receipt.json", "l5_joint_plan_bundle_v1.py", "l5_prepare_joint_plan_bundle_v1.py",
         "L5_full_v1.finished.json", "L5_collection_progress_09.json"]
code = code[:begin] + "names = " + repr(names) + code[end:]
code = code.replace('historical accounting reproduced with k counter exceptions', 'historical new-method inputs explicitly missing')
begin = code.index('    stream.write(f"WIP(L5)')
end = code.index('\nresult = subprocess.run', begin)
code = code[:begin] + '''    stream.write(f"WIP(L5): 전체 행동 평가 목록과 단계별 실행 근거 고정\\n\\n원자료3000실행 검증 완료. 전체{family['manifest']['evaluation_family_size']}행동에 N131072와 seed850001을 적용한다.\\n완료 응답·B5·B6 독립 검사는 준비됐고 역사 관문은 입력 부족이다.\\n후보 성능과 채택은 아직 미확인이다.\\n")''' + code[end:]
ast.parse(code)
with (RUNS / "l5_joint_plan_bundle_v1.py").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(code)
