import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path


RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
source = RUNS / "l3_validate_smoke_v1.py"
text = source.read_text(encoding="utf-8")
assert "bench_learning_l2 as learning" in text
record = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "status": "failed",
          "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "exit_code": 1,
          "error": "ValueError: learning overlay schema differs", "cause": "v1 copied validator retained L2 loader import; L3 collector and six smoke jobs completed successfully"}
with (RUNS / "L3_validate_smoke_v1_failed.json").open("x", encoding="utf-8") as stream:
    json.dump(record, stream, indent=2)
with (RUNS / "l3_validate_smoke_v2.py").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(text.replace("bench_learning_l2 as learning", "bench_learning_l3 as learning").replace("L3_validate_smoke_v1.json", "L3_validate_smoke_v2.json"))
