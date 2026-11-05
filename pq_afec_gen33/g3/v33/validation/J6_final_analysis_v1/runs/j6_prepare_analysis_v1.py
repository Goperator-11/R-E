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

def transform(value):
    value = value.replace("j1", "j6").replace("J1", "J6")
    value = value.replace("tail_likelihood_contrast", "margin_contrast").replace("tail_cost_contrast", "preflight_context_contrast")
    value = value.replace("cost_only", "margin_zero").replace('"cost"', '"zero"').replace("cost_", "zero_")
    value = value.replace("tail_variant", "budget_variant").replace("tail variant role", "budget variant role")
    return value

value = transform((ROOT / "experiments/v33/bench_learning_j1_report.py").read_text(encoding="utf-8"))
value = value.replace("1660eaf4ebad78194aee04705ea89157e921686659ac9a808941bde805079008", sha(ROOT / "experiments/v33/bench_learning_j6.py"))
value = value.replace("9c9490afa5b93de3c24e784ce31f109cb1ca0e9409fe864db1344b0678327ebd", sha(RUNS / "J6_full_v1_plan.json"))
value = value.replace("cost-only is a diagnostic control", "zero margin is a diagnostic control")
value = value.replace("J6 대 L1은 전체 변경, J6 대 cost는 등급 우도 기여, cost 대 L1은 비용 보정 기여다.", "J6 대 L1은 전체 변경, J6 대 zero는 margin 기여, zero 대 L1은 A_pre·응답 범위·후보 연결 기여다.")
value = value.replace("ideal과 cost는 진단", "ideal과 zero는 진단")
target = ROOT / "experiments/v33/bench_learning_j6_report.py"
write(target, value)
driver = (RUNS / "j1_joint_driver_v1.py").read_text(encoding="utf-8").replace("j1", "j6").replace("J1", "J6")
driver = re.sub(r"WRAPPER_SHA = ['\"][0-9a-f]+['\"]", "WRAPPER_SHA = " + repr(sha(target)), driver)
driver = driver.replace("J6_tail_design.md", "J6_preflight_budget.md")
start, end = driver.index("BOUND = "), driver.index("FAMILY = ")
bound = {str(RUNS / "J6_full_v1_plan.json"): sha(RUNS / "J6_full_v1_plan.json"),
         str(RUNS / "L1_action_family_v1.json"): sha(RUNS / "L1_action_family_v1.json"),
         str(ROOT / "docs/J6_preflight_budget.md"): sha(ROOT / "docs/J6_preflight_budget.md")}
driver = driver[:start] + "BOUND = " + repr(bound) + "\n" + driver[end:]
write(RUNS / "j6_joint_driver_v1.py", driver)
for source_name, target_name in (("test_v33_learning_j1_report.py", "test_v33_learning_j6_report.py"),
                                ("test_v33_j1_joint_driver.py", "test_v33_j6_joint_driver.py")):
    write(ROOT / "tests" / target_name, transform((ROOT / "tests" / source_name).read_text(encoding="utf-8")))
check = (RUNS / "j1_analysis_check_v1.py").read_text(encoding="utf-8").replace("j1", "j6").replace("J1", "J6")
write(RUNS / "j6_analysis_check_v1.py", check)
status = (RUNS / "j1_collection_status.py").read_text(encoding="utf-8").replace("J1", "J6")
write(RUNS / "j6_collection_status.py", status)
print(json.dumps({"reporter_sha256": sha(target), "driver_sha256": sha(RUNS / "j6_joint_driver_v1.py")}))
