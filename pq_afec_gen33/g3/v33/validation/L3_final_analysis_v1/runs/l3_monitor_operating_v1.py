import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import time


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sys.path.insert(0, str(ROOT))
from padfec3 import monitor3


sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
sources = {str(path): sha(path) for path in [ROOT / "padfec3/monitor3.py", ROOT / "docs/L3_monitor_design.md", Path(__file__)]}
assert not (RUNS / "L3_monitor_operating_v1.json").exists()
started = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
clock = time.monotonic()
rates = []
for index, q in enumerate((.03, .06, .42)):
    rng = random.Random(920001 + index)
    up = down = 0.0
    counts = {-1: 0, 1: 0}
    for _ in range(200000):
        z = int(rng.random() < q)
        up, down, direction = monitor3.step(up, down, z, q)
        if direction:
            counts[direction] += 1
    rates.append({"q": q, "seed": 920001 + index, "connections": 200000, "up": counts[1], "down": counts[-1],
                  "both_per_1000": sum(counts.values()) / 200.0,
                  "scope": "one fixed-q null stream; no independent-seed confidence interval"})
delays = []
for repetition in range(250):
    rng = random.Random(910001 + repetition)
    up = down = 0.0
    pre_alarms = 0
    for _ in range(500):
        up, down, direction = monitor3.step(up, down, int(rng.random() < .03), .03)
        pre_alarms += int(direction != 0)
    delay = None
    for index in range(200):
        up, down, direction = monitor3.step(up, down, int(rng.random() < .66), .03)
        if direction == 1 and delay is None:
            delay = index + 1
    delays.append({"seed": 910001 + repetition, "delay_observations": delay, "censored": delay is None,
                   "baseline_alarms": pre_alarms})
ordered = sorted(float("inf") if row["censored"] else row["delay_observations"] for row in delays)
median = statistics.median(ordered)
result = {"schema": "padfec.v33.l3_monitor_operating/1", "data_kind": "development_fixed_q_bernoulli_simulation",
    "started_kst": started, "elapsed_seconds": time.monotonic() - clock, "sources_sha256": sources,
    "sources_unchanged": all(sha(path) == expected for path, expected in sources.items()), "rates": rates,
    "injection": {"predicted_non1": .03, "actual_non1_after_change": .66, "baseline_connections": 500,
        "change_connections": 200, "replicates": 250, "detected": sum(not row["censored"] for row in delays),
        "median_including_censor_as_infinity": None if not math.isfinite(median) else median,
        "median_le_15": median <= 15, "raw": delays},
    "limits": "Known-q scalar detector only. Not the W1 closed-loop false-alarm gate, not a guarantee for every realization or an EPS estimate."}
assert result["sources_unchanged"]
with (RUNS / "L3_monitor_operating_v1.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    stream.write("\n")
print(json.dumps({"rates": rates, "detected": result["injection"]["detected"], "median": result["injection"]["median_including_censor_as_infinity"],
                  "median_le_15": median <= 15, "elapsed_seconds": result["elapsed_seconds"]}))
