import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

def write(path, value):
    assert not path.exists(), path
    compile(value, str(path), "exec")
    path.write_text(value, encoding="utf-8", newline="\n")

base = ROOT / "experiments/v33/bench_learning_l2_report.py"
value = base.read_text(encoding="utf-8").replace('l2', 'j1').replace('L2', 'J1')
value = value.replace('J1_fixed_epsilon_v1', 'J1_cost_only_v1').replace('"fixed"', '"cost"').replace('fixed_', 'cost_')
value = value.replace('epsilon_adaptation_contrast', 'tail_likelihood_contrast').replace('boundary_timing_contrast', 'tail_cost_contrast')
value = value.replace('"42dbff55bc984c3d34d2e159c3d162b79376104bd73a9751db66a915a47dcf3e"', repr(sha(ROOT / "experiments/v33/bench_learning_j1.py")))
value = value.replace('"14712a6836c2069cc8e695635ff90f4cc64f9aee829b5360d6ec54c46697fce0"', repr(sha(RUNS / "J1_full_v1_plan.json")))
value = value.replace('PRIMARY = {("j1_c1", "l1_c1"), ("j1_none", "l1_none"), ("j1_c1", "v31"), ("j1_c1", "v32")}', 'PRIMARY = {("j1_c1", "l1_c1"), ("j1_none", "l1_none")}')
value = value.replace('expected_mode = "adaptive" if role == "j1" else "cost_ablation"', 'expected_mode = "full" if role == "j1" else "cost_only"')
value = value.replace('["epsilon_calibration"], expected_mode, "calibration role"', '["tail_variant"], expected_mode, "tail variant role"')
start, end = value.index('def epsilon_diagnostics('), value.index('def aggregate(')
value = value[:start] + value[end:]
value = value.replace('by_group, diagnostics, eps = collections.defaultdict(list), collections.defaultdict(list), collections.defaultdict(list)', 'by_group, diagnostics = collections.defaultdict(list), collections.defaultdict(list)')
value = value.replace('        if run["analysis_role"] in ("j1", "cost"):\n            eps[key].append({"seed": run["seed"], **epsilon_diagnostics(rows)})\n', '')
start, end = value.index('        group["epsilon_diagnostics"] = None'), value.index('    comparisons, missing =')
value = value[:start] + value[end:]
value = value.replace('Predeclared J1 development comparison after L1 results; fixed epsilon is a diagnostic control, not another candidate selected from outcomes.', 'Predeclared J1 development comparison against active L1; cost-only is a diagnostic control, not another candidate selected from outcomes.')
start, end = value.index('def markdown('), value.index('def final_report(')
value = value[:start] + '''def markdown(report):
    text = bench_report.markdown(report).replace("# W1 벤치 보고서", "# J1 공동 행동 평가 보고서", 1)
    return text + "\\nJ1 대 L1은 전체 변경, J1 대 cost는 등급 우도 기여, cost 대 L1은 비용 보정 기여다.\\nnone과 c1의 L1 대비 각15셀 비열등을 요구한다. ideal과 cost는 진단이며 사후 대체 후보로 쓰지 않는다.\\n"


''' + value[end:]
target = ROOT / "experiments/v33/bench_learning_j1_report.py"
write(target, value)
driver = (RUNS / "l2_joint_driver_v1.py").read_text(encoding="utf-8").replace('l2', 'j1').replace('L2', 'J1')
driver = re.sub(r'WRAPPER_SHA = "[0-9a-f]+"', 'WRAPPER_SHA = ' + repr(sha(target)), driver)
driver = driver.replace('J1_benchmark_plan.md', 'J1_tail_design.md')
start, end = driver.index('BOUND = '), driver.index('FAMILY = ')
bound = {str(RUNS / "J1_full_v1_plan.json"): sha(RUNS / "J1_full_v1_plan.json"),
    str(RUNS / "L1_action_family_v1.json"): sha(RUNS / "L1_action_family_v1.json"),
    str(ROOT / "docs/J1_tail_design.md"): sha(ROOT / "docs/J1_tail_design.md")}
driver = driver[:start] + 'BOUND = ' + repr(bound) + '\n' + driver[end:]
write(RUNS / "j1_joint_driver_v1.py", driver)
tests = (ROOT / "tests/test_v33_learning_l2_report.py").read_text(encoding="utf-8").replace('l2', 'j1').replace('L2', 'J1')
tests = tests.replace('"fixed"', '"cost"').replace('fixed_', 'cost_').replace('epsilon_adaptation_contrast', 'tail_likelihood_contrast').replace('boundary_timing_contrast', 'tail_cost_contrast')
start, end = tests.index('    def trace('), tests.index('    def aggregate(')
tests = tests[:start] + '    def trace(self, run):\n        return self.base.trace(run)\n\n' + tests[end:]
tests = tests.replace('sum(row["primary"] for row in result["comparisons"]), 60', 'sum(row["primary"] for row in result["comparisons"]), 30')
start, end = tests.index('        eps = '), tests.index('    def test_three_contrasts')
tests = tests[:start] + '        self.assertEqual(sum(row["observation_diagnostics"] is not None for row in result["groups"]), 120)\n\n' + tests[end:]
start, end = tests.index('    def test_epsilon_diagnostics'), tests.index('    def test_phase_gates')
tests = tests[:start] + tests[end:]
write(ROOT / "tests/test_v33_learning_j1_report.py", tests)
tests = (ROOT / "tests/test_v33_l2_joint_driver.py").read_text(encoding="utf-8").replace('l2', 'j1').replace('L2', 'J1')
write(ROOT / "tests/test_v33_j1_joint_driver.py", tests)
status = (RUNS / "l2_collection_status.py").read_text(encoding="utf-8").replace('L2', 'J1')
write(RUNS / "j1_collection_status.py", status)
check = (RUNS / "j1_collector_check_v1.py").read_text(encoding="utf-8")
check = check.replace('files = ["test_v33_learning_j1.py", "test_v33_policy_worker.py", "test_padfec3_second_flight.py"]', 'files = ["test_v33_learning_j1_report.py", "test_v33_j1_joint_driver.py", "test_v33_learning_report.py"]')
check = check.replace('"experiments/v33/bench_learning_j1.py", "experiments/adaptation_benchmark.py",', '"experiments/v33/bench_learning_j1.py", "experiments/v33/bench_learning_j1_report.py",')
write(RUNS / "j1_analysis_check_v1.py", check)
print(json.dumps({"status": "prepared", "reporter_sha256": sha(target), "driver_sha256": sha(RUNS / "j1_joint_driver_v1.py")}))
