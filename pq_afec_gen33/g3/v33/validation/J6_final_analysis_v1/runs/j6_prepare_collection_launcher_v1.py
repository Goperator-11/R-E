import sys
sys.dont_write_bytecode = True
import hashlib
from pathlib import Path
import re

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
value = (RUNS / "launch_j1_collection_v1.ps1").read_text(encoding="utf-8-sig").replace("j1", "j6").replace("J1", "J6")
value = re.sub(r"if \(\$driverSha -ne '[0-9a-f]+'\)", "if ($driverSha -ne '" + sha(RUNS / "j6_bench_driver_v1.py") + "')", value)
value = re.sub(r"if \(\$planSha -ne '[0-9a-f]+'\)", "if ($planSha -ne '" + sha(RUNS / "J6_full_v1_plan.json") + "')", value)
with (RUNS / "launch_j6_collection_v1.ps1").open("x", encoding="utf-8-sig", newline="\n") as stream:
    stream.write(value)
print("prepared detached single collection phase")
