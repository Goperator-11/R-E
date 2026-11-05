import sys
sys.dont_write_bytecode = True
import argparse
from concurrent.futures import ProcessPoolExecutor
import datetime
import hashlib
import json
import math
from pathlib import Path
import time


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.v33.worldsim import Action, World, WorldContext, load_params


SCHEMA = "padfec.v33fix.ack_sensitivity/1"
SEED = 860101
SAMPLES = 4096
ACK_RANGE = tuple(range(28, 55))
DEFAULT_ACK = 41
CONTEXTS = {
    "B12_c6000_p0.08": ("0d4cd14cd8ac65a43314", dict(k=2, w=1280, p=0.08, rtt_ms=120.0, uplink_mbps=10.0, cert_bytes=6000)),
    "B12_c6000_p0.01": ("25b8f9c00a6e624fb79f", dict(k=2, w=1280, p=0.01, rtt_ms=120.0, uplink_mbps=10.0, cert_bytes=6000)),
    "B12_c12000_p0.08": ("8d03ebd20b4b495c51d4", dict(k=2, w=1280, p=0.08, rtt_ms=120.0, uplink_mbps=5.0, cert_bytes=12000)),
    "B12_c12000_p0.01": ("e1b0c2a9f662c13a711d", dict(k=2, w=1280, p=0.01, rtt_ms=120.0, uplink_mbps=5.0, cert_bytes=12000)),
    "B4": ("7ae691dc839ee353e97b", dict(k=1, w=1280, p=0.0, rtt_ms=50.0, uplink_mbps=0.0, cert_bytes=4032)),
}
ROLES = {
    "B12_c6000_p0.08": {(7, 0, 4): "W1 oracle reference; J6 margin0", (12, 0, 4): "J6 margin30 none and C1",
                         (0, 2, 2): "L1 none and C1, v31, v32", (0, 1, 2): "L1 C1 minor"},
    "B12_c6000_p0.01": {(7, 0, 2): "W1 oracle reference; J6 margin0 C1", (12, 0, 2): "J6 margin30 C1",
                         (12, 0, 4): "J6 margin30 none", (0, 2, 2): "L1 none and C1, v31, v32", (0, 1, 2): "L1 C1"},
    "B12_c12000_p0.08": {(0, 3, 1): "W1 oracle reference; L1, J6, v31, v32", (0, 2, 2): "L1, v31, v32 minor"},
    "B12_c12000_p0.01": {(0, 3, 1): "W1 oracle reference; L1, J6, v31, v32", (0, 2, 2): "L1, v31, v32 minor"},
    "B4": {(1, 0, 0): "W1 structural reference", (0, 0, 0): "b0", (1, 0, 4): "L1 none, v31, v32",
           (11, 0, 4): "J6 margin30 none", (1, 0, 1): "L1 C1", (11, 0, 1): "J6 margin30 C1", (0, 0, 2): "L1 C1 and J6 C1"},
}
PACKETIZATION = {
    "world_default": {"note": "worldparams.json: s0 1472 (ML-KEM) or 382.45 (X25519), 41.983 B per packet, copied from padfec/policy.py"},
    "physical_fit": {"note": "audit-gen2-foundation (5): p13_beff physical fits, ML-KEM 1589.92+40.05n, X25519 477.98+40.21n",
                     "k2": {"s0_mlkem_bytes": 1589.92, "packet_overhead_bytes": 40.05},
                     "k1": {"s0_classical_bytes": 477.98, "packet_overhead_bytes": 40.21}},
    "sealed_c12000_low": {"note": "g3/v33/evidence/EVIDENCE.md 6: sealed H c12000 g3auto observed S minimum 14058 B, minus one 41 B pre-ACK", "server_bytes": 14017},
    "sealed_c12000_high": {"note": "g3/v33/evidence/EVIDENCE.md 6: sealed H c12000 g3auto observed S maximum 14114 B, minus one 41 B pre-ACK", "server_bytes": 14073},
}
ACK_SOURCE = {
    "default_41": "worldparams.json provenance.preflight_ack: A0 and audit-quicgo-source.md, 41 B = header 20 + ACK 5 + tag 16 for a 4 B CID",
    "sealed_difference": "C:/dev/codex_handoff/v33/runs/J6_historical_preflight_v1.md: sealed stage3 journals, 2 Mbps minus unlimited server-byte medians 42/44 B, 41/42 B after subtracting certificate size",
    "range_28_54": "Not a sealed measurement. C:/dev/codex_handoff/v33/prompt/TASKS.md 277 J6 card assumption 'A_pre +-13 B', reused by docs/J6_preflight_budget.md 9 as a unit-test range.",
}


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()


def world_params(profile, ack, k):
    server = {"preflight_ack_bytes": ack}
    if profile == "physical_fit":
        server.update(PACKETIZATION[profile]["k2" if k >= 2 else "k1"])
    return {"server": server}


def context_for(name, profile):
    values = dict(CONTEXTS[name][1])
    if profile.startswith("sealed_"):
        values.pop("cert_bytes")
        values["server_bytes"] = PACKETIZATION[profile]["server_bytes"]
    return values


def evaluate(job):
    name, profile, ack, action, samples, seed = job
    values = context_for(name, profile)
    context = WorldContext(**values)
    world = World(world_params(profile, ack, context.k), seed=seed)
    n = 0
    mean = m2 = 0.0
    classes = {"one": 0, "two": 0, "tail": 0, "failure": 0}
    failed = 0
    sizes = None
    for connection in range(samples):
        row = world.sample(context, Action(*action), connection=connection)
        n += 1
        delta = row["hct"] - mean
        mean += delta / n
        m2 += delta * (row["hct"] - mean)
        classes[row["world_class"]] += 1
        failed += not row["ok"]
        sizes = row["server_first_flight_sizes"] if sizes is None else sizes
    variance = m2 / (n - 1)
    return {"context_name": name, "context_id": CONTEXTS[name][0], "context": values, "profile": profile,
            "ack_bytes": ack, "action": list(action), "role": ROLES[name][action], "n": n, "seed": seed,
            "mean_hct_ms": mean, "se_ms": math.sqrt(variance / n), "variance_hct_ms2": variance,
            "class_fractions": {key: value / n for key, value in classes.items()}, "failed": failed,
            "server_first_flight_sizes": sizes, "server_first_flight_bytes": sum(sizes),
            "params_sha256": world.params_sha256}


def jobs(samples, seed):
    result = []
    for name in CONTEXTS:
        k = CONTEXTS[name][1]["k"]
        acks = ACK_RANGE if CONTEXTS[name][1]["uplink_mbps"] > 0 and k >= 2 else (28, DEFAULT_ACK, 54)
        profiles = ["world_default", "physical_fit"]
        if name.startswith("B12_c12000"):
            profiles += ["sealed_c12000_low", "sealed_c12000_high"]
        for action in ROLES[name]:
            for profile in profiles:
                for ack in acks:
                    result.append((name, profile, ack, action, samples, seed))
    return result


def cliffs(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault((row["context_name"], row["profile"], tuple(row["action"])), []).append(row)
    result = []
    for (name, profile, action), items in sorted(grouped.items()):
        items.sort(key=lambda row: row["ack_bytes"])
        rtt = CONTEXTS[name][1]["rtt_ms"]
        base = items[0]
        jump = next((row["ack_bytes"] for row in items if row["mean_hct_ms"] - base["mean_hct_ms"] > rtt / 2), None)
        at = {row["ack_bytes"]: row["mean_hct_ms"] for row in items}
        result.append({"context_name": name, "profile": profile, "action": list(action), "role": ROLES[name][action],
                       "ack_values": [row["ack_bytes"] for row in items], "mean_hct_at_28_ms": at.get(28),
                       "mean_hct_at_41_ms": at.get(DEFAULT_ACK), "mean_hct_at_54_ms": at.get(54),
                       "first_ack_bytes_with_jump_over_half_rtt": jump})
    return result


def best_by_ack(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault((row["context_name"], row["profile"], row["ack_bytes"]), []).append(row)
    result = []
    for (name, profile, ack), items in sorted(grouped.items()):
        best = min(items, key=lambda row: row["mean_hct_ms"])
        result.append({"context_name": name, "profile": profile, "ack_bytes": ack, "best_listed_action": best["action"],
                       "best_listed_mean_hct_ms": best["mean_hct_ms"],
                       "gaps_to_best_ms": {",".join(map(str, row["action"])): row["mean_hct_ms"] - best["mean_hct_ms"] for row in items}})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "g3" / "v33" / "V33FIX_ack_sensitivity_v1.json")
    parser.add_argument("--samples", type=int, default=SAMPLES)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--workers", type=int, default=20)
    args = parser.parse_args(argv)
    if args.out.exists():
        raise SystemExit("refusing to overwrite " + str(args.out))
    started_kst, started = now(), time.monotonic()
    work = jobs(args.samples, args.seed)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(evaluate, work, chunksize=4))
    output = {"schema": SCHEMA, "data_kind": "development_independent_world_sensitivity",
              "started_kst": started_kst, "finished_kst": now(), "seconds": time.monotonic() - started,
              "seed": args.seed, "samples_per_point": args.samples, "common_random_numbers": "same seed and connection index for every action, ACK size and profile",
              "script_sha256": file_hash(Path(__file__)),
              "world_sources_sha256": {name: file_hash(ROOT / "experiments" / "v33" / name) for name in ("worldsim.py", "worldparams.json")},
              "default_params_sha256": World().params_sha256, "ack_source": ACK_SOURCE, "packetization_profiles": PACKETIZATION,
              "rows": rows, "cliffs": cliffs(rows), "best_listed_action_by_ack": best_by_ack(rows),
              "scope": "Diagnostic only. The frozen default world and every W1 result keep the 41 B ACK. Best listed action is the minimum over the listed actions, not a new oracle."}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "x", encoding="utf-8", newline="\n") as stream:
        json.dump(output, stream, ensure_ascii=False, indent=1, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"out": str(args.out), "rows": len(rows), "seconds": output["seconds"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
