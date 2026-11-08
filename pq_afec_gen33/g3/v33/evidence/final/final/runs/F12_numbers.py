import hashlib
import json
import os
from pathlib import Path
import sys
import time


os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
REPO = Path("C:/dev/pq_afec_gen33")
RUNS = Path("C:/dev/codex_handoff/final/runs")
sys.path.insert(0, str(REPO))
from padfec3 import decide3


def source_hashes():
    return {
        str(path.relative_to(REPO)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (REPO / "padfec3" / "decide3.py", REPO / "padfec" / "policy.py")
    }


def exceed(k, s):
    return [
        c for c in decide3.candidates3(k, 1280, float(s), 41.983)
        if c["m"] > 0 and c["W_eff"] + 46 + 6 * k > 1452
    ]


def intervals(values, step):
    result = []
    for value in values:
        if result and value == result[-1][1] + step:
            result[-1][1] = value
        else:
            result.append([value, value])
    return result


started = time.monotonic()
before = source_hashes()
caps = []
for k in (1, 2, 3, 4):
    cap = max(
        w for w in range(1280, 1453)
        if any(c["m"] > 0 for c in decide3.candidates3(k, w, 9000.0, 41.983))
    )
    caps.append(cap)
wire_caps = [1452 - 46 - 6 * k for k in (1, 2, 3, 4)]
assert caps == [1407, 1401, 1395, 1389]
assert wire_caps == [1400, 1394, 1388, 1382]
grid = {}
for k in (1, 2, 3, 4):
    hit_s = []
    shapes = set()
    for s in range(1500, 60001, 5):
        bad = exceed(k, s)
        if bad:
            hit_s.append(s)
            shapes.update((c["delta"], c["W_eff"], c["W_eff"] + 39 + 6 * k, c["W_eff"] + 46 + 6 * k) for c in bad)
    grid[str(k)] = {
        "s_points": len(range(1500, 60001, 5)),
        "exceed_s_points": len(hit_s),
        "exceed_s_intervals_5B": intervals(hit_s, 5),
        "shapes": [dict(zip(("delta", "W_eff", "model_bytes", "wire_worst_bytes"), row)) for row in sorted(shapes)],
    }
    print(json.dumps({"k": k, "grid": grid[str(k)]}, ensure_ascii=False), flush=True)
assert grid["1"]["exceed_s_points"] == grid["2"]["exceed_s_points"] == 0
assert grid["3"]["exceed_s_intervals_5B"] == [[25140, 26375]]
assert grid["4"]["exceed_s_intervals_5B"] == [[16600, 17835]]
edges = {}
for k, points in ((3, (25138, 25139, 26376, 26377)), (4, (16598, 16599, 17836, 17837))):
    edges[str(k)] = [{"S": s, "has_exceed_candidate": bool(exceed(k, s))} for s in points]
    assert [row["has_exceed_candidate"] for row in edges[str(k)]] == [False, True, True, False]
after = source_hashes()
assert before == after
result = {
    "source_kind": "model_candidate_calculation",
    "conditions": {"W": 1280, "S_grid_start": 1500, "S_grid_end": 60000, "S_step": 5, "c_pkt": 41.983, "UDP_MAX": 1452, "cap_check_S": 9000.0, "cap_check_W": [1280, 1452]},
    "model_cap_W": caps,
    "wire_safe_cap_W_eff": wire_caps,
    "grid": grid,
    "integer_edge_checks": edges,
    "source_sha256_before": before,
    "source_sha256_after": after,
    "elapsed_seconds": round(time.monotonic() - started, 3),
    "pass": True,
}
(RUNS / "F12_numbers.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
