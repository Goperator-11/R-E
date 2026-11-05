import sys
sys.dont_write_bytecode = True
from pathlib import Path

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
for source_name, target_name in (("j1_prepare_overlays_v1.py", "j6_prepare_overlays_v1.py"),
                                ("j1_bench_driver_v1.py", "j6_bench_driver_v1.py"),
                                ("j1_validate_smoke_v1.py", "j6_validate_smoke_v1.py")):
    value = (RUNS / source_name).read_text(encoding="utf-8")
    value = value.replace("j1", "j6").replace("J1", "J6")
    value = value.replace("cost_only", "margin_zero").replace("tail_variant", "budget_variant")
    value = value.replace("J6_tail_design.md", "J6_preflight_budget.md")
    value = value.replace('"scope": "smoke data and launch-plan integrity; no policy performance claim"', '"scope": "smoke data, received preflight replay and launch-plan integrity; no policy performance claim"')
    compile(value, target_name, "exec")
    with (RUNS / target_name).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(value)
print("prepared one-phase J6 execution tools")
