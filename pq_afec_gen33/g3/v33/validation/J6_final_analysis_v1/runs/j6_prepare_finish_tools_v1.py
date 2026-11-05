import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import ast
import hashlib
import json
from pathlib import Path

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
value = (RUNS / "j6_core_check_v2.py").read_text(encoding="utf-8")
old = '"test_padfec3_preflight.py", "test_v33_preflight_observer.py"'
assert old in value
value = value.replace(old, '"test_v33_j6_candidate.py", "test_v33_learning_j6.py", "test_v33_learning_j6_report.py", "test_v33_j6_joint_driver.py", "test_v33_j6_findings.py"')
value = value.replace('sources += sorted((ROOT / "experiments/v33/candidate_tests").glob("j1_*.py"))', 'sources += sorted((ROOT / "experiments/v33/candidate_tests").glob("j1_*.py"))\nsources += sorted((ROOT / "experiments/v33/candidate_tests").glob("j6_*.py"))')
ast.parse(value)
output = RUNS / "j6_revert_check_v1.py"
with output.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(value)
check_path = RUNS / "J6_finish_tool_parse_v1.json"
result = {"parsed": [], "scope": "Syntax check only. Revert remains guarded by independently validated failed adoption; no policy mutation executed."}
for path in (RUNS / "j6_revert_candidate_v1.py", output, RUNS / "j6_joint_plan_bundle_v1.py", RUNS / "j6_prepare_phase_launchers_v1.py", Path(__file__)):
    ast.parse(path.read_text(encoding="utf-8"))
    result["parsed"].append({"path": str(path), "sha256": sha(path)})
with check_path.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, indent=2)
    stream.write("\n")
print(json.dumps(result))
