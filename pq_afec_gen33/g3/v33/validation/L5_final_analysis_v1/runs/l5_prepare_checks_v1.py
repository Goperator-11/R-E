import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
replacements = {
    "tests/test_padfec3_arrivals.py": [('data["v"] == 4', 'data["v"] == 9')],
    "tests/test_padfec3_dev_regressions.py": [('test_state_version_four_', 'test_state_version_nine_'), ('self.assertEqual(data["v"], 4)', 'self.assertEqual(data["v"], 9)'), ('for version in (1, 2, 3):', 'for version in range(1, 9):')],
    "tests/test_padfec3_learn.py": [('self.assertEqual(d["v"], 4)', 'self.assertEqual(d["v"], 9)')],
    "tests/test_v33_policy_worker.py": [('self.assertEqual(rows[0]["result"]["state_version"], 4)', 'self.assertEqual(rows[0]["result"]["state_version"], 9)')],
    "tests/test_v33_l3_candidate.py": [('learn3.STATE_VERSION == 4', 'learn3.STATE_VERSION == 9')],
    "tests/test_padfec3_followup.py": [('key = args + (learn3.LATER_DEFAULT,)', 'key = args + (learn3.LATER_DEFAULT, 41, 1280 * 13)')],
}
for name, changes in replacements.items():
    path = ROOT / name
    content = path.read_text(encoding="utf-8")
    for before, after in changes:
        assert content.count(before) == 1, (name, before)
        content = content.replace(before, after)
    path.write_text(content, encoding="utf-8", newline="\n")
script = (RUNS / "j6_revert_check_v1.py").read_text(encoding="utf-8")
old = '"test_v33_j1_joint_driver.py", "test_v33_j1_findings.py"]'
assert script.count(old) == 1
script = script.replace(old, '"test_v33_j1_joint_driver.py", "test_v33_j1_findings.py", "test_padfec3_server_size.py", "test_v33_server_response_observer.py"]')
script = script.replace('sources += [ROOT / "experiments/adaptation_benchmark.py"]', 'sources += [ROOT / "experiments/adaptation_benchmark.py", ROOT / "experiments/v33/server_response_observer.py"]')
script = script.replace('sources = [p for name', 'if len(sys.argv) > 2 and sys.argv[2] == "focused":\n    files = ["test_padfec3_server_size.py", "test_v33_server_response_observer.py"]\nsources = [p for name', 1)
with (RUNS / "l5_check_v1.py").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(script)
print("state9 contract expectations and focused/core check script prepared")
