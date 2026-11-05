import sys
sys.dont_write_bytecode = True
from pathlib import Path


RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
source = (RUNS / "l3_report_check_v1.py").read_text(encoding="utf-8")
source = source.replace('files = ["test_v33_learning_l3_report.py", "test_v33_learning_report.py"]',
                        'files = ["test_v33_learning_l3_report.py", "test_v33_learning_report.py", "test_v33_l3_monitor_audit.py", "test_v33_l3_findings.py"]')
source = source.replace('driver = RUNS / "l3_joint_driver_v1.py"',
    'sources += [RUNS / "l3_monitor_audit_v1.py", RUNS / "l3_findings_extract_v1.py"]\ndriver = RUNS / "l3_joint_driver_v1.py"')
with (RUNS / "l3_analysis_check_v1.py").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(source)
