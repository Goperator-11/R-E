import sys
sys.dont_write_bytecode = True
import ast
from pathlib import Path

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
code = (RUNS / "j6_final_bundle_v2.py").read_text(encoding="utf-8")
code = code.replace("J6", "L5").replace("j6", "l5")
code = code.replace("l5_joint_artifact_check_v2.py", "l5_joint_artifact_check_v3.py").replace("L5_joint_artifact_check_v2.json", "L5_joint_artifact_check_v3.json")
code = code.replace("l5_findings_extract_v1.py", "l5_findings_extract_v3.py")
code = code.replace("cf7d3e7c3ebfb856a75f70f1001048a361d1db24630bccd821dc1b07490d7ee1", "c42dab5f81a270a0565ec971e914e6906b8edab077c2d13a6d586ea0e1a82c70")
code = code.replace("e2da5da58eb5993b38a17a98df16d470deacc15bad745f01577a7ed974c7b0ec", "53dd0c2b3297b52d2985f8d4de034689f21693093852e487ba982d991840acd4")
code = code.replace("f39e2c068b365bfbc73ee8a3927c5ed738b6e94e89bf7c019919a6876b150c86", "50ee782b1142f41faa8810a1c066c52f2a351e75622d67df9b4672742a63e9a0")
code = code.replace('"iter021_*", "iter022_*", "iter023_*"', '"iter023_*", "iter024_*", "J7_reading_during_L5_*", "j7_reading_during_l5_*.py"')
code = code.replace('    selected.update((RUNS / "l5_history_availability_during_l5_v2.py", RUNS / "L5_history_availability_during_L5_v2.json"))', '    selected.add(RUNS / "preserve_test_files_v1.py")')
code = code.replace('    mandatory = [REPORT,', '    validation = read(RUNS / "L5_validation_v1.finished.json")\n    assert validation["status"] == "complete" and validation["exit_code"] == 0\n    mandatory = [REPORT,')
ast.parse(code)
assert 'history_availability_during_l5' not in code
with (RUNS / "l5_final_bundle_v1.py").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(code)
print("Prepared l5_final_bundle_v1.py; execution requires completed validation and disposition")
