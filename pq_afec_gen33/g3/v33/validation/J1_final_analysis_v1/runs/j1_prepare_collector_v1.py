import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
base = ROOT / "experiments/v33/bench_learning.py"
assert sha(base) == "412666987b56f46cdfe6cfa7970c1c6da5ff3eeed207037bae997ec4790d873f"
value = base.read_text(encoding="utf-8")
value = value.replace('bench_learning.py', 'bench_learning_j1.py')
for name in ("learning_benchmark", "learning_raw", "learning_import"):
    value = value.replace('padfec.v33.' + name + '/1', 'padfec.v33.' + name + '/j1-1')
value = value.replace('    fingerprint = inventory(root)\n', '    if receipt.get("tail_variant") not in ("full", "cost_only"):\n        raise ValueError("J1 snapshot must declare tail variant")\n    equal(receipt.get("state_version"), 7, "J1 snapshot state version")\n    fingerprint = inventory(root)\n', 1)
value = value.replace('"state_version": 4}', '"state_version": 7, "tail_variant": receipt["tail_variant"]}')
target = ROOT / "experiments/v33/bench_learning_j1.py"
assert not target.exists()
compile(value, str(target), "exec")
target.write_text(value, encoding="utf-8", newline="\n")
test_base = ROOT / "tests/test_v33_learning_bench.py"
tests = test_base.read_text(encoding="utf-8").replace('bench_learning as learning', 'bench_learning_j1 as learning')
tests = tests.replace('"state_version": 4', '"state_version": 7').replace('"bench_learning.py"', '"bench_learning_j1.py"')
test_target = ROOT / "tests/test_v33_learning_j1.py"
assert not test_target.exists()
test_target.write_text(tests, encoding="utf-8", newline="\n")
driver_base = RUNS / "l2_bench_driver_v1.py"
driver = driver_base.read_text(encoding="utf-8").replace('l2', 'j1').replace('L2', 'J1')
driver = driver.replace('fixed_epsilon', 'cost_only').replace('J1_benchmark_plan.md', 'J1_tail_design.md')
driver_target = RUNS / "j1_bench_driver_v1.py"
assert not driver_target.exists()
compile(driver, str(driver_target), "exec")
driver_target.write_text(driver, encoding="utf-8", newline="\n")
receipt = {"status": "prepared", "inputs_sha256": {str(p): sha(p) for p in (base, test_base, driver_base)},
    "outputs_sha256": {str(p): sha(p) for p in (target, test_target, driver_target)},
    "script_sha256": sha(__file__), "scope": "L1 collector copied to distinct J1 schema/state7 with explicit snapshot variant; frozen earlier collectors unchanged"}
with (RUNS / "J1_collector_preparation_v1.json").open("x", encoding="utf-8") as stream:
    json.dump(receipt, stream, indent=2)
    stream.write("\n")
print(json.dumps(receipt))
