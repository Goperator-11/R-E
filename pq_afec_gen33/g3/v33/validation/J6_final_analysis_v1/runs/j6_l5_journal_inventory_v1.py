import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import collections
import datetime as dt
import hashlib
import json
from pathlib import Path

path = Path(r"C:\dev\pq_afec_gen31\experiments\state\p31_run1_H_h_c12000_r120_u5_units.jsonl")
runs = Path(r"C:\dev\codex_handoff\v33\runs")
raw = path.read_bytes()
units = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
counts = collections.Counter()
fields = collections.defaultdict(set)
server_fields = collections.defaultdict(set)
packet_hits = []
for line_no, unit in enumerate(units, 1):
    for seg in unit["val"]["segments"]:
        arm = seg["arm"]
        counts[arm] += len(seg["rows"])
        for row in seg["rows"]:
            fields[arm].update(row)
        for field in ("server_delta", "server_after"):
            server_fields[field].update(seg[field])
            assert all(not isinstance(value, (dict, list)) for value in seg[field].values())
    stack = [("$", unit)]
    while stack:
        at, obj = stack.pop()
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in ("tx_ns", "tx_sizes", "rx_ns", "rx_sizes", "server_first_flight_sizes", "server_dgram_sizes"):
                    packet_hits.append({"line": line_no, "path": at + "." + key})
                stack.append((at + "." + key, value))
        elif isinstance(obj, list):
            stack.extend((at + "[" + str(i) + "]", value) for i, value in enumerate(obj))
assert raw == path.read_bytes()
result = {"schema": "padfec.v33.l5_historical_packet_inventory/1", "recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
          "path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "units": len(units),
          "rows_per_arm": dict(counts), "row_fields_per_arm": {key: sorted(value) for key, value in fields.items()},
          "server_aggregate_fields": {key: sorted(value) for key, value in server_fields.items()}, "packet_list_hits": packet_hits,
          "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          "scope": "Read-only schema inventory of the full H c12000 run1 journal. No missing packet counts or tails are imputed."}
out = runs / "J6_L5_historical_packet_inventory_v1.json"
with out.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps({key: result[key] for key in ("sha256", "units", "rows_per_arm", "packet_list_hits")}))
