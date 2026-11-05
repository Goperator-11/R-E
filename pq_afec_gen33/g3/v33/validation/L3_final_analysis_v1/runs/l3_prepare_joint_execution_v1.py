import sys
sys.dont_write_bytecode = True
import hashlib
from pathlib import Path


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
source = (RUNS / "l2_joint_driver_v1.py").read_text(encoding="utf-8")
replacements = [
    ("d90449ae24665ac622c783804bc2afb048529882661098a856fdd5a50cedde96", sha(ROOT / "experiments/v33/bench_learning_l3_report.py")),
    ("14712a6836c2069cc8e695635ff90f4cc64f9aee829b5360d6ec54c46697fce0", sha(RUNS / "L3_full_v1_plan.json")),
    ("52230684bfdcfe6d49883a0c98221c63c23ef6a54665dc0497286f582d656b1d", sha(ROOT / "docs/L3_monitor_design.md")),
    ("L2_benchmark_plan.md", "L3_monitor_design.md"), ("L2", "L3"), ("l2", "l3")]
for old, new in replacements:
    assert old in source, old
    source = source.replace(old, new)
with (RUNS / "l3_joint_driver_v1.py").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(source)
for old, new in [(RUNS / "l2_collection_status.py", RUNS / "l3_collection_status.py"),
                 (ROOT / "tests/test_v33_l2_joint_driver.py", ROOT / "tests/test_v33_l3_joint_driver.py")]:
    source = old.read_text(encoding="utf-8").replace("L2", "L3").replace("l2", "l3")
    with new.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(source)
