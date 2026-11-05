import sys
sys.dont_write_bytecode = True
from pathlib import Path
import hashlib


RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
source = (RUNS / "launch_l2_collection_v1.ps1").read_text(encoding="utf-8")
replacements = [
    ("e617f4d9d791a923436ff8600a64071115eba99accf4766371d54c053c88de3d", sha(RUNS / "l3_bench_driver_v1.py")),
    ("14712a6836c2069cc8e695635ff90f4cc64f9aee829b5360d6ec54c46697fce0", sha(RUNS / "L3_full_v1_plan.json")),
    ("L2_validate_smoke_v1.json", "L3_validate_smoke_v2.json"),
    ("L2", "L3"), ("l2", "l3"),
    ("75 shards, 1500 seed runs, 2055000", "90 shards, 1800 seed runs, 2466000")]
for old, new in replacements:
    assert old in source, old
    source = source.replace(old, new)
with (RUNS / "launch_l3_collection_v1.ps1").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(source)
