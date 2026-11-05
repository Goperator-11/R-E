import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path


RUNS = Path(r"C:\dev\codex_handoff\v33\runs")


def make(source, target, replacements):
    value = (RUNS / source).read_text(encoding="utf-8")
    for old, new in replacements:
        assert old in value, old
        value = value.replace(old, new)
    with (RUNS / target).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(value)


make("l2_prepare_collectors.py", "l3_prepare_collectors.py", [
    ('("L2_v1", "L2_fixed_epsilon_v1")', '("L3_v1", "L3_guard_only_v1", "L3_record_only_v1", "L3_beta_only_v1")'),
    ('"epsilon_calibration": overlay["policy"]["epsilon_calibration"]', '"monitor_config": overlay["policy"]["monitor_config"], "monitor_variant": overlay["policy"]["monitor_variant"]'),
    ("bench_learning_l2", "bench_learning_l3"), ("L2_prepare", "L3_prepare")])
make("l2_bench_driver_v1.py", "l3_bench_driver_v1.py", [
    ('(("L2_v1", ("none", "c1", "ideal")), ("L2_fixed_epsilon_v1", ("none", "c1")))',
     '(("L3_v1", ("none", "c1", "ideal")), ("L3_guard_only_v1", ("c1",)), ("L3_record_only_v1", ("c1",)), ("L3_beta_only_v1", ("c1",)))'),
    ("L2_benchmark_plan.md", "L3_monitor_design.md"),
    ("learning_launch/3", "learning_launch/4"),
    ("fixed_epsilon_is_diagnostic_only", "ablation_arms_are_diagnostic_only"),
    ("L2_", "L3_"), ("bench_learning_l2", "bench_learning_l3")])
make("l2_validate_smoke_v1.py", "l3_validate_smoke_v1.py", [
    (" == 75", " == 90"), (" == 1500", " == 1800"), (" == 2055000", " == 2466000"), (" == 5\n", " == 6\n"),
    ('"calibrated": 0', '"monitored": 0'),
    ('totals["calibrated"] += sum(row["observation_info"]["epsilon_update_eligible"] for row in rows)',
     'totals["monitored"] += sum(row["observation_info"]["monitor"] is not None for row in rows)'),
    ('row["observation_info"]["epsilon_update_reason"] == "no_ctx"', 'row["observation_info"]["monitor_reason"] == "no_ctx"'),
    ("L2_", "L3_"), ("l2_", "l3_")])
make("l3_monitor_operating_v1.py", "l3_monitor_operating_v2.py", [("L3_monitor_operating_v1.json", "L3_monitor_operating_v2.json")])
print("L3 수집 준비 스크립트 4개 생성")
