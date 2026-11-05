import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
import math
from pathlib import Path


RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
path = RUNS / "L3_monitor_operating_v2.json"
value = json.loads(path.read_text(encoding="utf-8"))
assert value["sources_unchanged"]
assert all(sha(source) == expected for source, expected in value["sources_sha256"].items())
expected_rates = [(.03, 920001), (.06, 920002), (.42, 920003)]
assert len(value["rates"]) == 3
for row, (q, seed) in zip(value["rates"], expected_rates):
    assert row["q"] == q and row["seed"] == seed and row["connections"] == 200000
    assert all(type(row[key]) is int and row[key] >= 0 for key in ("up", "down"))
    assert row["both_per_1000"] == (row["up"] + row["down"]) / 200
injection = value["injection"]
assert [injection[key] for key in ("predicted_non1", "actual_non1_after_change", "baseline_connections", "change_connections", "replicates")] == [.03, .66, 500, 200, 250]
raw = injection["raw"]
assert len(raw) == 250 and [row["seed"] for row in raw] == list(range(910001, 910251))
delays = []
for row in raw:
    delay = row["delay_observations"]
    assert row["censored"] is (delay is None)
    assert delay is None or type(delay) is int and 1 <= delay <= 200
    assert type(row["baseline_alarms"]) is int and 0 <= row["baseline_alarms"] <= 500
    delays.append(float("inf") if delay is None else delay)
delays.sort()
median = (delays[124] + delays[125]) / 2
assert injection["median_including_censor_as_infinity"] == (median if math.isfinite(median) else None)
assert injection["median_le_15"] is (median <= 15)
assert injection["detected"] == sum(not row["censored"] for row in raw)
result = {"status": "pass", "operating_path": str(path), "operating_sha256": sha(path), "script_sha256": sha(__file__),
          "replicates": len(raw), "detected": injection["detected"], "median": median if math.isfinite(median) else None,
          "scope": "Source integrity, fixed population and censored-median arithmetic; no extra simulation samples"}
with (RUNS / "L3_operating_integrity_v1.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
    stream.write("\n")
print(json.dumps(result))
