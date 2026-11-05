import sys
sys.dont_write_bytecode = True
import hashlib
from pathlib import Path


RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
source = RUNS / "l3_final_bundle_v1.py"
text = source.read_text(encoding="utf-8")
assert '"iter018_*"' in text
text = text.replace('"iter018_*"', '"iter018_*", "iter019_*"')
with (RUNS / "l3_final_bundle_v2.py").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(text)
print(hashlib.sha256((RUNS / "l3_final_bundle_v2.py").read_bytes()).hexdigest())
