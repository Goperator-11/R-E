import sys
sys.dont_write_bytecode = True
import ast
from pathlib import Path

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
code = (RUNS / "j6_final_commit_v1.py").read_text(encoding="utf-8")
code = code.replace("J6", "L5").replace("j6", "l5")
code = code.replace("e94961a4f472bc043374cb0ec15034583acc2f34", "91432c35c122dd83bc946b2d53e68c96bd6fa14b")
code = code.replace("L5_joint_artifact_check_v2.json", "L5_joint_artifact_check_v3.json")
code = code.replace('    assert type(adopted) is bool', '    assert adopted is False')
code = code.replace('"tests/test_v33_policy_worker.py",', '"tests/test_v33_policy_worker.py", "tests/test_padfec3_followup.py",')
code = code.replace("l5_test_padfec3_preflight.py", "l5_test_padfec3_server_size.py")
code = code.replace("l5_test_v33_preflight_observer.py", "l5_test_v33_server_response_observer.py")
code = code.replace("padfec3/preflight.py", "padfec3/server_size.py")
code = code.replace("test_padfec3_preflight.py", "test_padfec3_server_size.py")
code = code.replace("test_v33_preflight_observer.py", "test_v33_server_response_observer.py")
code = code.replace("과거25저널124800행을 재검산하고 k 계수 예외7행을 구분했다.", "두 새 산출법의 역사 관문은 N·tail·완료 패킷목록 부족으로 미완료다.")
ast.parse(code)
with (RUNS / "l5_final_commit_v1.py").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(code)
print("Prepared l5_final_commit_v1.py; commit requires verified final manifest and L1 restore tests")
