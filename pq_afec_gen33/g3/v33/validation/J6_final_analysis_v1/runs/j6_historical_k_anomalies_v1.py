import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
ARCHIVE = Path(r"C:\dev\padfec_archive")
source = RUNS / "J6_historical_preflight_v1.json"
original = json.loads(source.read_text(encoding="utf-8"))
anomalies = []
for entry in original["inputs"]:
    path = ARCHIVE / entry["archive_path"]
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == entry["stored_sha256"]
    decoded = gzip.decompress(raw)
    assert hashlib.sha256(decoded).hexdigest() == entry["original_sha256"]
    for line_number, line in enumerate(decoded.splitlines(), 1):
        if not line.strip():
            continue
        unit = json.loads(line)
        value = unit["val"]
        for segment in value["segments"]:
            for row_index, row in enumerate(segment["rows"]):
                if row.get("ok") and row.get("group") == "X25519MLKEM768" and row.get("first_flight_datagrams") != 2:
                    anomalies.append({"source": entry["logical_path"], "original_sha256": entry["original_sha256"], "line": line_number, "unit_key": unit["key"], "fingerprint": unit["fp"], "condition": value["cond"], "loss": value["loss"], "block": value["block"], "arm": segment["arm"], "slot": segment.get("slot"), "row_index": row_index, "row": row})
assert len(anomalies) == 7
result = {"schema": "padfec.v33.j6_historical_k_anomalies/1", "recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "anomalies": anomalies, "scope": "Recorded successful ML-KEM rows with first_flight_datagrams != 2; stored group and counters alone do not establish negotiated key exchange or physical complete first flight."}
output = RUNS / "J6_historical_k_anomalies_v1.json"
with output.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps(result, ensure_ascii=False))
