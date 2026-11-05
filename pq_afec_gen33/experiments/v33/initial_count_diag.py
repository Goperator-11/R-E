import sys
sys.dont_write_bytecode = True
import argparse
from concurrent.futures import ProcessPoolExecutor
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.v33.worldsim import Action, World, WorldContext


SCHEMA = "padfec.v33fix.world_diagnostics/1"
PROTOCOL = ROOT / "g3" / "v33" / "world_validation_protocol.json"
W0_RESULT = ROOT / "g3" / "v33" / "validation" / "W0" / "W0_world_validation.json"
DIAG = ROOT / "g3" / "v33" / "V33FIX_world_diag_v1.json"
CLASSES = ("one", "two", "tail", "failure_or_initial_retransmission", "unclassified")
DEFINITIONS = {
    "w0": "W0 validate_world.py: every client O, R and B datagram is an Initial datagram",
    "key_discard": "quic-go client Initial keys are discarded when the client first sends a Handshake packet (RFC 9001 4.9.1). In this world that is the first R, which still coalesces the Initial ACK. O and B datagrams sent before it and the first R count; R retransmissions do not.",
}


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()


def merge_section(path, name, payload):
    path = Path(path)
    current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"schema": SCHEMA, "sections": {}}
    if current.get("schema") != SCHEMA:
        raise ValueError("unexpected diagnostics schema")
    if name in current["sections"]:
        raise ValueError("diagnostic section already written: " + name)
    current["sections"][name] = payload
    data = json.dumps(current, ensure_ascii=False, indent=1, sort_keys=True, allow_nan=False) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
        stream.write(data)
        temporary = Path(stream.name)
    os.replace(temporary, path)


def counts(row):
    kinds = [item["kind"] for item in row["arrivals"]]
    w0 = sum(kind in ("O", "R", "B") for kind in kinds)
    if w0 != row["initial_datagrams"]:
        raise AssertionError("W0 Initial count differs from the world counter")
    first_reply = kinds.index("R") if "R" in kinds else len(kinds)
    key_discard = sum(kind in ("O", "B") for kind in kinds[:first_reply]) + (first_reply < len(kinds))
    if any(kind in ("O", "B") for kind in kinds[first_reply:]):
        raise AssertionError("Initial datagram after the first reply")
    return w0, key_discard


def classify(row, datagrams):
    if not row["ok"] or datagrams >= 4:
        return "failure_or_initial_retransmission"
    if datagrams == 3:
        value = row["hct"]
        return "one" if value < 100 else "two" if value < 200 else "tail"
    return "unclassified"


def evaluate(job):
    case, seed, samples = job
    world = World(seed=seed)
    context, action = WorldContext(**case["context"]), Action(*case["action"])
    result = {name: {"classes": {key: 0 for key in CLASSES}, "initial_datagrams": {}, "retransmitted_or_failed": 0} for name in DEFINITIONS}
    mean = 0.0
    moved = []
    for connection in range(samples):
        row = world.sample(context, action, connection=connection)
        mean += (row["hct"] - mean) / (connection + 1)
        w0, key = counts(row)
        for name, value in (("w0", w0), ("key_discard", key)):
            item = result[name]
            item["classes"][classify(row, value)] += 1
            item["initial_datagrams"][str(value)] = item["initial_datagrams"].get(str(value), 0) + 1
            item["retransmitted_or_failed"] += not row["ok"] or value >= 4
        if classify(row, w0) != classify(row, key):
            moved.append(row["hct"])
    for item in result.values():
        item["class_fractions"] = {key: value / samples for key, value in item["classes"].items()}
        item["failure_or_initial_retransmission_fraction"] = item["retransmitted_or_failed"] / samples
        item["initial_5_fraction"] = item["initial_datagrams"].get("5", 0) / samples
    moved.sort()
    summary = {"count": len(moved)}
    if moved:
        summary.update(min_hct_ms=moved[0], median_hct_ms=moved[len(moved) // 2], max_hct_ms=moved[-1])
    return {"id": case["id"], "context": case["context"], "action": case["action"], "observed": case["observed"],
            "n": samples, "seed": seed, "mean_hct_ms": mean, "definitions": result, "reclassified": summary}


def comparisons(row, tolerances):
    observed = row["observed"]
    output = {}
    for name in DEFINITIONS:
        item = row["definitions"][name]
        checks = {}
        for category, fraction in observed.get("class_fractions", {}).items():
            actual = item["class_fractions"][category]
            checks[category] = {"world": actual, "observed": fraction, "difference": actual - fraction,
                                "within_w0_tolerance": abs(actual - fraction) <= tolerances["class_fraction_abs"]}
        if "failure_fraction" in observed:
            actual = item["failure_or_initial_retransmission_fraction"]
            checks["failure_fraction"] = {"world": actual, "observed": observed["failure_fraction"], "difference": actual - observed["failure_fraction"],
                                          "within_w0_tolerance": abs(actual - observed["failure_fraction"]) <= tolerances["failure_fraction_abs"]}
        if "initial_5_fraction" in observed:
            actual = item["initial_5_fraction"]
            checks["initial_5_fraction"] = {"world": actual, "observed": observed["initial_5_fraction"], "difference": actual - observed["initial_5_fraction"],
                                            "within_w0_tolerance": abs(actual - observed["initial_5_fraction"]) <= tolerances["initial_5_fraction_abs"]}
        output[name] = checks
    return output


def reproduces_w0(rows):
    stored = {row["id"]: row for row in json.loads(W0_RESULT.read_text(encoding="utf-8"))["calibration"]}
    result = {}
    for row in rows:
        old = stored[row["id"]]["sampled"]
        mine = row["definitions"]["w0"]
        same = abs(old["mean_hct_ms"] - row["mean_hct_ms"]) <= 1e-9 and old["class_fractions"] == mine["class_fractions"]
        same = same and old["initial_datagrams"] == mine["initial_datagrams"]
        result[row["id"]] = same
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DIAG)
    parser.add_argument("--samples", type=int)
    parser.add_argument("--workers", type=int, default=7)
    args = parser.parse_args(argv)
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    samples = args.samples or protocol["samples_per_case"]
    started_kst, started = now(), time.monotonic()
    cases = protocol["calibration"]["cases"]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(evaluate, [(case, protocol["seed"], samples) for case in cases]))
    tolerances = protocol["calibration"]["tolerances"]
    for row in rows:
        row["checks"] = comparisons(row, tolerances)
    payload = {"item": "C-E5", "started_kst": started_kst, "finished_kst": now(), "seconds": time.monotonic() - started,
               "definitions": DEFINITIONS, "protocol": str(PROTOCOL), "protocol_sha256": file_hash(PROTOCOL),
               "w0_result": str(W0_RESULT), "w0_result_sha256": file_hash(W0_RESULT),
               "w0_reproduced_exactly": reproduces_w0(rows) if samples == protocol["samples_per_case"] else None,
               "script_sha256": file_hash(Path(__file__)),
               "world_sources_sha256": {name: file_hash(ROOT / "experiments" / "v33" / name) for name in ("worldsim.py", "worldparams.json")},
               "rows": rows,
               "scope": "Reclassification only. validate_world.py and the W0 tolerances are unchanged. Policy inputs do not contain Initial counts."}
    merge_section(args.out, "initial_count", payload)
    print(json.dumps({"out": str(args.out), "seconds": payload["seconds"], "w0_reproduced": payload["w0_reproduced_exactly"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
