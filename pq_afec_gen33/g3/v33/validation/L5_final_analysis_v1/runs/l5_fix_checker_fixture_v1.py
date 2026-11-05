import sys
sys.dont_write_bytecode = True
import hashlib
import json
from pathlib import Path

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(name, value):
    with (RUNS / name).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(value)
failure = {"status": "fail", "phase": "synthetic B5 checker preparation", "error_type": "TypeError",
           "error": "keys must be str, int, float, bool or None, not tuple",
           "cause": "Audit.equal serializes tuple-key Counter; direct count equality is required",
           "helper_sha256": sha(RUNS / "l5_adaptation_audit_v1.py"),
           "checker_sha256": sha(RUNS / "l5_joint_artifact_check_v1.py"),
           "scope": "checker fixture failed before full collection performance read; candidate unchanged"}
save("L5_adaptation_fixture_initial_failure.json", json.dumps(failure, indent=2) + "\n")
code = (RUNS / "l5_adaptation_audit_v1.py").read_text(encoding="utf-8")
code = code.replace('audit.equal("B5_trace_action_counts:" + tag, actual, expected)', 'audit.check("B5_trace_action_counts:" + tag, actual == expected)')
save("l5_adaptation_audit_v2.py", code)
checker = (RUNS / "l5_joint_artifact_check_v1.py").read_text(encoding="utf-8")
checker = checker.replace("l5_adaptation_audit_v1.py", "l5_adaptation_audit_v2.py").replace(sha(RUNS / "l5_adaptation_audit_v1.py"), sha(RUNS / "l5_adaptation_audit_v2.py"))
save("l5_joint_artifact_check_v2.py", checker)
for old, new in (("l5_checker_fixture_check_v1.py", "l5_checker_fixture_check_v2.py"),
                 ("l5_response_fixture_check_v2.py", "l5_response_fixture_check_v3.py"),
                 ("l5_adaptation_fixture_check_v1.py", "l5_adaptation_fixture_check_v2.py")):
    text = (RUNS / old).read_text(encoding="utf-8")
    text = text.replace("l5_joint_artifact_check_v1.py", "l5_joint_artifact_check_v2.py")
    text = text.replace(Path(old).stem.replace("l5_", "L5_") + ".json", Path(new).stem.replace("l5_", "L5_") + ".json")
    save(new, text)
