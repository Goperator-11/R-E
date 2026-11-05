import sys
sys.dont_write_bytecode = True
import hashlib
from pathlib import Path

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
value = (RUNS / "launch_l3_collection_v1.ps1").read_text(encoding="utf-8-sig").replace('l3', 'j1').replace('L3', 'J1')
value = value.replace('J1_validate_smoke_v2.json', 'J1_validate_smoke_v1.json')
value = value.replace('b42071631b813b7be088b9744213339f37c888ff999b9c636351b7fd63ba6afc', sha(RUNS / "j1_bench_driver_v1.py"))
value = value.replace('4e48e8d951fe1b9b6ce24babb1119775eb49d4e45bf2964be1d6152da31fb9c5', sha(RUNS / "J1_full_v1_plan.json"))
value = value.replace('90 shards, 1800 seed runs, 2466000', '75 shards, 1500 seed runs, 2055000')
value = value.replace('Smoke and independent validation must pass.', 'Smoke integrity validation must pass.')
target = RUNS / "launch_j1_collection_v1.ps1"
assert not target.exists()
target.write_text(value, encoding="utf-8-sig", newline="\n")
