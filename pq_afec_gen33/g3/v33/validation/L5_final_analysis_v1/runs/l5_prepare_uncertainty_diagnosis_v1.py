import sys
sys.dont_write_bytecode = True
import ast
from pathlib import Path

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
code = (RUNS / "j6_uncertainty_diagnosis_v1.py").read_text(encoding="utf-8")
code = code.replace("J6", "L5").replace("j6", "l5").replace('"zero_"', '"single_"')
code = code.replace("L5_joint_artifact_check_v2.json", "L5_joint_artifact_check_v3.json")
code = code.replace('row["regression_gate"]["status"] == "fail" or row["scenario"] == "B12_c6000"', 'row["regression_gate"]["status"] != "pass" or row["primary"]')
code = code.replace('group["scenario"] == "B12_c6000"', 'group["scenario"] in ("B1", "B2", "B5", "B6", "B12_c6000")')
code = code.replace('"c6000_groups": groups', '"selected_groups": groups')
code = code.replace('"unresolved_actions": unresolved, "counts": dict(pairs), "comparisons": rows', '"unresolved_action_count": len(unresolved), "counts": dict(pairs), "selected_comparison_count": len(rows)')
ast.parse(code)
with (RUNS / "l5_uncertainty_diagnosis_v1.py").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(code)
print("Prepared read-only diagnosis; requires independently verified complete report")
