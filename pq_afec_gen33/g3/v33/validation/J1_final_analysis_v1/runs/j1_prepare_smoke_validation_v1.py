import sys
sys.dont_write_bytecode = True
from pathlib import Path

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
source = (RUNS / "l2_validate_smoke_v1.py").read_text(encoding="utf-8")
value = source.replace('l2', 'j1').replace('L2', 'J1')
value = value.replace('"calibrated": 0, "cold_skips": 0', '"updated": 0, "cold_skips": 0')
value = value.replace('totals["calibrated"] += sum(row["observation_info"]["epsilon_update_eligible"] for row in rows)', 'totals["updated"] += sum(row["observation_info"]["updated"] for row in rows)')
value = value.replace('row["observation_info"]["epsilon_update_reason"] == "no_ctx"', 'row["observation_info"]["skip"] == "no_ctx"')
target = RUNS / "j1_validate_smoke_v1.py"
assert not target.exists()
compile(value, str(target), "exec")
target.write_text(value, encoding="utf-8", newline="\n")
