import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = Path(r"C:\dev\pq_afec")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
paths = [ROOT / "experiments/results/p13_beff.json",
         ROOT / "experiments/state/backup_2026-09-08_0947/results/p13_beff.json"]
paths += sorted((ROOT / "experiments/state/backup").glob("p13_beff.json.*.json"))
records = []
for path in paths:
    raw = path.read_bytes()
    obj = json.loads(raw)
    arrays = []
    hits = []
    stack = [("$", obj)]
    while stack:
        at, value = stack.pop()
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ("tx_sizes", "tx_ns", "rx_sizes", "server_first_flight_sizes"):
                    hits.append({"path": at + "." + key, "type": type(item).__name__, "length": len(item) if hasattr(item, "__len__") else None})
                stack.append((at + "." + key, item))
        elif isinstance(value, list):
            if value and isinstance(value[0], dict):
                arrays.append({"path": at, "length": len(value), "first_keys": sorted(value[0])})
            stack.extend((at + "[" + str(i) + "]", v) for i, v in enumerate(value))
    assert path.read_bytes() == raw
    records.append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
                    "top_keys": sorted(obj), "packet_list_hits": hits, "record_arrays": arrays})
log = ROOT / "experiments/state/log2_p13.txt"
log_raw = log.read_bytes()
result = {"schema": "padfec.v33.l5_history_availability/2", "recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
          "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "records": records,
          "log": {"path": str(log), "sha256": hashlib.sha256(log_raw).hexdigest(), "bytes": len(log_raw),
                  "packet_list_token_present": any(t in log_raw for t in (b"tx_sizes", b"tx_ns"))},
          "scope": "Read-only metadata search for historical per-connection server packet lists. No simulation or source mutation."}
out = RUNS / "L5_history_availability_during_J6_v2.json"
with out.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    stream.write("\n")
print(json.dumps(result, ensure_ascii=False))
