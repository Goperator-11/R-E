import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
ROOT = Path(r"C:\dev\pq_afec_gen33")
paths = [RUNS / "L5_preparation.md", RUNS / "J2_L5_preparation_review.md", RUNS / "L5_reading_during_J6_v1.md",
    ROOT / "experiments/v33/worldsim.py", ROOT / "experiments/v33/bench_learning_j6.py", ROOT / "experiments/p13_beff.py",
    ROOT / "g3/v33/evidence/06_server_size_bins.py", ROOT / "g3/v33/evidence/06_server_size_bins.json",
    Path(r"C:\dev\pq_afec\experiments\results\p13_beff.json"), Path(r"C:\dev\pq_afec\docs\PADFEC v2 명세.md"),
    Path(r"C:\dev\padfec_archive\v31_stage3\experiments\quicbed\qamp.go"),
    RUNS / "J6_historical_preflight_v1.json", RUNS / "J6_historical_preflight_v1.md", RUNS / "J6_historical_k_anomalies_v1.json"]
files = {}
for path in paths:
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    files[str(path)] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
source = json.loads(paths[8].read_text(encoding="utf-8"))
fields = sorted({key for row in source["sweep"] for key in row})
result = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "files": files,
    "p13_sweep_fields": fields, "p13_sweep_rows": len(source["sweep"]), "p13_has_tx_sizes_per_sweep": any("tx_sizes" in row for row in source["sweep"]),
    "scope": "Read-only source inspection during J6; no new policy or world evaluation, no L5 adoption."}
out = RUNS / "L5_reading_sources_during_J6_v1.json"
with out.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps({"sources": len(files), "p13_sweep_rows": len(source["sweep"]), "p13_fields": fields, "output": str(out)}, ensure_ascii=False))
