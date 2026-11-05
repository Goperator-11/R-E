import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
SNAPSHOT = ROOT / "g3/v33/policy_snapshots/L1_v1"
sys.path.insert(0, str(SNAPSHOT))
from padfec3 import layout


sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert Path(layout.__file__).resolve().is_relative_to(SNAPSHOT.resolve())
inputs = {str(path): sha(path) for path in (Path(layout.__file__), Path(layout.policy.__file__), Path(layout.quantum.__file__),
    Path(r"C:\dev\codex_handoff\v33\evidence\verify-A1\v03_cross.py"))}
K, W, U, NEED, RTT = 2, 1280, 2.0, 15, 50.7


def cost(action, p, mode):
    delta, lead, trail = action
    width = W + delta
    ev = layout.evaluate(K, width, lead + trail, lead, p, RTT, U, NEED)
    q2 = p * p if trail >= 1 else p
    sample = RTT + layout.tau(lead * layout.parity_bytes(width, K) + width, U)
    delay = 0 if mode == "baseline" else layout.PTO_SAMPLED_MULT * (RTT if mode == "true_rtt" else sample)
    tail = ev["p_two_rtt"] * q2
    classes = [ev["p_one_rtt"], ev["p_two_rtt"] - tail, ev["p_fail"] + tail]
    assert abs(sum(classes) - 1) < 1e-12
    return {"J_ms": ev["J"], "corrected_J_ms": ev["J"] + tail * delay, "tail_increment_ms": tail * delay,
        "p_two_rtt_before": ev["p_two_rtt"], "q2": q2, "tail_probability": tail, "T2_ms": delay,
        "classes_with_tail": classes, "physical_first_flight_failure": ev["p_fail"]}


def difference(p, mode):
    return cost((0, 3, 1), p, mode)["corrected_J_ms"] - cost((0, 0, 4), p, mode)["corrected_J_ms"]


rows = []
for mode, expected in (("baseline", .2026), ("true_rtt", .2174), ("sample_rtt", .2148)):
    lo, hi = .1, .35
    assert difference(lo, mode) < 0 < difference(hi, mode)
    for _ in range(60):
        middle = (lo + hi) / 2
        if difference(middle, mode) >= 0:
            hi = middle
        else:
            lo = middle
    cross = (lo + hi) / 2
    assert round(cross, 4) == expected
    rows.append({"mode": mode, "crossing_p": cross, "audit_rounded_p": expected, "difference_at_p15_ms": difference(.15, mode),
        "p15_actions": [{"action": list(action), **cost(action, .15, mode)} for action in ((0, 3, 1), (0, 0, 4), (0, 4, 0))]})
assert all(sha(path) == expected for path, expected in inputs.items())
result = {"schema": "padfec.v33.j1_tail_reference_preparation/1", "status": "pass",
    "recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "context": {"k": K, "W": W, "u": U, "n_need": NEED, "rtt": RTT},
    "rows": rows, "input_sha256": inputs, "script_sha256": sha(__file__),
    "scope": "Read-only analytic reproduction of verify-A1 v03 on frozen L1 layout; no policy change, new W1 data or adoption. Tail probabilities are IID and are not validated conditional GE probabilities."}
with (RUNS / "J1_tail_reference_preparation_v1.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
    stream.write("\n")
print(json.dumps(result))
