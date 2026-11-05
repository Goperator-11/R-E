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

def write(path, content):
    compile(content, str(path), "exec")
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)

def transform(content):
    content = content.replace("j6", "l5").replace("J6", "L5")
    content = content.replace("margin_contrast", "mixture_change_contrast").replace("preflight_context_contrast", "response_geometry_contrast")
    content = content.replace("margin_zero", "single").replace('"zero"', '"single"').replace("zero_", "single_")
    return content.replace("budget_variant", "size_variant").replace("budget variant role", "size variant role")

value = transform((ROOT / "experiments/v33/bench_learning_j6_report.py").read_text(encoding="utf-8"))
value = value.replace("dc82aac283de90549ecc7c62744ea9ff33895f07128b790e219387469daac61c", sha(ROOT / "experiments/v33/bench_learning_l5.py"))
value = value.replace("0d71b6acb7b2e6e2a8faa79b3ef3d61e352def415db0debcdf6ab0d2207ab7d3", sha(RUNS / "L5_full_v1_plan.json"))
value = value.replace("zero margin is a diagnostic control", "single-size geometry is a diagnostic control")
value = value.replace("L5 대 L1은 전체 변경, L5 대 zero는 margin 기여, zero 대 L1은 A_pre·응답 범위·후보 연결 기여다.", "L5 대 L1은 전체 변경, L5 대 single은 변화·혼합 기여, single 대 L1은 완료 관측·물리 산술·조건부 우도 기여다.")
value = value.replace("ideal과 zero는 진단", "ideal과 single은 진단")
needle = '        group["p_convergence"] = legacy.convergence(group, by_group[key], scenarios[key[1]], protocol)'
assert value.count(needle) == 1
value = value.replace(needle, needle + '''
        if group["scenario"] == "B6":
            expected = group["expected_regret"]
            group["gates"]["mixture_fixed_regret"] = bench_report.threshold_from_summary(
                expected["seed_summary"], 0.5, mc_bound=expected["shared_mc_bound_ms"],
                selection_gap=expected["selection_gap_bound_ms"], inclusive=True)
''')
needle = '    report["analysis_aliases"] = ALIASES'
value = value.replace(needle, '    report["historical_new_methods_gate"] = "blocked_missing_inputs"\n    report["historical_fit_is_independent_validation"] = False\n' + needle)
target = ROOT / "experiments/v33/bench_learning_l5_report.py"
write(target, value)
driver = (RUNS / "j6_joint_driver_v1.py").read_text(encoding="utf-8").replace("j6", "l5").replace("J6", "L5")
driver = re.sub(r"WRAPPER_SHA = ['\"][0-9a-f]+['\"]", "WRAPPER_SHA = " + repr(sha(target)), driver)
driver = driver.replace("L5_preflight_budget.md", "L5_server_response.md")
start, end = driver.index("BOUND = "), driver.index("FAMILY = ")
bound = {str(RUNS / "L5_full_v1_plan.json"): sha(RUNS / "L5_full_v1_plan.json"),
         str(RUNS / "L1_action_family_v1.json"): sha(RUNS / "L1_action_family_v1.json"),
         str(ROOT / "docs/L5_server_response.md"): sha(ROOT / "docs/L5_server_response.md"),
         str(RUNS / "L5_anchor_availability_v1.json"): sha(RUNS / "L5_anchor_availability_v1.json")}
driver = driver[:start] + "BOUND = " + repr(bound) + "\n" + driver[end:]
write(RUNS / "l5_joint_driver_v1.py", driver)
for source, target_name in (("test_v33_learning_j6_report.py", "test_v33_learning_l5_report.py"),
                            ("test_v33_j6_joint_driver.py", "test_v33_l5_joint_driver.py")):
    write(ROOT / "tests" / target_name, transform((ROOT / "tests" / source).read_text(encoding="utf-8")))
check = (RUNS / "j6_analysis_check_v1.py").read_text(encoding="utf-8").replace("j6", "l5").replace("J6", "L5")
write(RUNS / "l5_analysis_check_v1.py", check)
status = (RUNS / "j6_collection_status.py").read_text(encoding="utf-8").replace("J6", "L5")
write(RUNS / "l5_collection_status.py", status)
print(json.dumps({"reporter_sha256": sha(ROOT / "experiments/v33/bench_learning_l5_report.py"), "driver_sha256": sha(RUNS / "l5_joint_driver_v1.py")}))
