import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
for source, target in (("j6_prepare_overlays_v1.py", "l5_prepare_overlays_v1.py"),
                       ("j6_bench_driver_v1.py", "l5_bench_driver_v1.py"),
                       ("j6_validate_smoke_v1.py", "l5_validate_smoke_v1.py")):
    content = (RUNS / source).read_text(encoding="utf-8")
    content = content.replace("j6", "l5").replace("J6", "L5").replace("margin_zero", "single").replace("budget_variant", "size_variant")
    content = content.replace("L5_preflight_budget.md", "L5_server_response.md").replace("received preflight replay", "received response replay")
    compile(content, str(RUNS / target), "exec")
    with (RUNS / target).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
print("prepared independent L5 snapshot overlay and one-phase execution tools")
