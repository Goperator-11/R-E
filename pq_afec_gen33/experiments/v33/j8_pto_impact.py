import sys
sys.dont_write_bytecode = True
import argparse
from concurrent.futures import ProcessPoolExecutor
import datetime
import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist
import time
import types


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.v33 import bench_metrics, bench_report, initial_count_diag, oracle, v33fix_j6_rejudge as rejudge
from experiments.v33 import worldsim


WORLD_SOURCE = Path(worldsim.__file__)
PATCHES = (
    ('                 "last_retry_flight": -1,\n',
     '                 "last_retry_flight": -1, "server_last_eliciting": None,\n'),
    ('            counters["server_sent"] += size\n',
     '            counters["server_sent"] += size\n            if kind == "data":\n                state["server_last_eliciting"] = time\n'),
    ('            schedule(time + base * 2 ** state["server_retry"], "server_pto", state["server_epoch"])\n',
     '            reference = time if state["server_last_eliciting"] is None else state["server_last_eliciting"]\n'
     '            schedule(max(time, reference + base * 2 ** state["server_retry"]), "server_pto", state["server_epoch"])\n'),
)
SCENARIO = "B7"
CONTEXT_ID = "0998e3f951c80c846cc2"
SAMPLES = 131072
SEED = 850001
FAMILY = 116
PAIRS = rejudge.PAIRS + [("v32", "v31")]


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()


def patched_source():
    text = WORLD_SOURCE.read_text(encoding="utf-8")
    for old, new in PATCHES:
        if text.count(old) != 1:
            raise ValueError("worldsim.py no longer matches the J8 patch anchor")
        text = text.replace(old, new)
    return text


def patched_module():
    name = "experiments.v33.worldsim_j8_last_send"
    if name in sys.modules:
        return sys.modules[name]
    module = types.ModuleType(name)
    module.__file__ = str(WORLD_SOURCE)
    sys.modules[name] = module
    exec(compile(patched_source(), str(WORLD_SOURCE) + ":j8_last_send", "exec"), module.__dict__)
    return module


def module_for(kind):
    return worldsim if kind == "w0" else patched_module()


def sample_series(job):
    kind, context, action, seed, samples = job
    module = module_for(kind)
    world = module.World(seed=seed)
    ctx, act = module.WorldContext(**context), module.Action(*action)
    rows = []
    for connection in range(samples):
        row = world.sample(ctx, act, connection=connection)
        rows.append((row["hct"], row["server_counted_uplink_bytes"], row["client_total_uplink_bytes"], row["ok"],
                     row["server_retransmission_bytes"] > 0))
    return kind, tuple(action), rows


def as_row(values):
    hct, server, client, ok, _ = values
    return {"hct": hct, "server_counted_uplink_bytes": server, "client_total_uplink_bytes": client, "ok": ok}


def table(action, reference, rows, reference_rows, z):
    stats = oracle._new_moments()
    for a, b in zip(rows, reference_rows):
        oracle._update(stats, as_row(a), as_row(b))
    summary = oracle._summary(stats, z)
    unresolved = summary["zero_observed_variance"] and action != reference
    if unresolved:
        summary["gap_half_width_ms"] = None
    return summary | {"action": list(action), "reference_action": list(reference), "approximate": True,
                      "uncertainty_resolved": not unresolved, "evaluation_family_size": FAMILY}


def load_b7(known, used):
    plan, family = rejudge.read(rejudge.PLAN), rejudge.read(rejudge.L1_FAMILY)
    directories = {}
    for job in plan["jobs"]:
        if job["scenario"] == SCENARIO:
            directories[(job["policy"], job["mode"])] = Path(job["out"]) / job["mode"] / SCENARIO
    for directory in family["raw_dirs"]:
        for mode in ("none", "c1", "ideal"):
            candidate = Path(directory) / mode / SCENARIO
            if candidate.is_dir():
                directories[("L1", mode)] = candidate
    for generation in ("v31", "v32"):
        directories[("W1", generation)] = rejudge.RUNS / f"W1_raw_{generation}" / generation / "full" / SCENARIO
    runs = {}
    for alias, key in rejudge.ROLES.items():
        runs[alias] = [rejudge.verified(directories[key] / f"seed{seed:05d}.json", known, used) for seed in rejudge.SEEDS]
    return runs


def comparisons(runs, tables):
    output = []
    for candidate, baseline in PAIRS:
        row = bench_report.direct_comparison(runs[candidate], runs[baseline], tables)
        gate = bench_metrics.evaluate_threshold(
            row["seed_summary"]["mean"], row["seed_summary"]["lower"], row["seed_summary"]["upper"], 0.5,
            mc_bound=row["shared_mc_bound_ms"], selection_gap=0.0, inclusive=True)
        output.append({"candidate": candidate, "baseline": baseline, "seed_mean_ms": row["seed_summary"]["mean"],
                       "seed_interval_ms": [row["seed_summary"]["lower"], row["seed_summary"]["upper"]],
                       "shared_mc_bound_ms": row["shared_mc_bound_ms"], "status": gate["status"],
                       "adjusted_interval_ms": [gate["adjusted_lower"], gate["adjusted_upper"]]})
    return output


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=initial_count_diag.DIAG)
    parser.add_argument("--samples", type=int, default=SAMPLES)
    parser.add_argument("--workers", type=int, default=20)
    args = parser.parse_args(argv)
    started_kst, started = now(), time.monotonic()
    benchmark = rejudge.read(rejudge.BENCHMARK)
    known = rejudge.known_hashes(benchmark)
    used = {}
    runs = load_b7(known, used)
    keys = set()
    for rows in runs.values():
        for row in rows:
            keys.update(bench_report.weights(row))
    stored = {}
    for cid, action in sorted(keys):
        if cid != CONTEXT_ID:
            raise ValueError("unexpected B7 context")
        stored[(cid, action)] = rejudge.verified(rejudge.POOL / f"{cid}_{action[0]}_{action[1]}_{action[2]}.json", known, used)
    context = next(iter(stored.values()))["context"]
    reference = tuple(next(iter(stored.values()))["reference_action"])
    actions = sorted({action for _, action in stored} | {reference})
    jobs = [(kind, context, action, SEED, args.samples) for kind in ("w0", "last_send") for action in actions]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        series = {(kind, action): rows for kind, action, rows in pool.map(sample_series, jobs)}
    z = NormalDist().inv_cdf(1.0 - 0.01 / (2.0 * FAMILY))
    tables = {kind: {(CONTEXT_ID, action): table(action, reference, series[(kind, action)], series[(kind, reference)], z) for action in actions}
              for kind in ("w0", "last_send")}
    reproduction = {}
    if args.samples == SAMPLES:
        for key, old in stored.items():
            mine = tables["w0"][key]
            reproduction[",".join(map(str, key[1]))] = (mine["mean_gap_ms"] == old["mean_gap_ms"]
                                                        and mine["gap_half_width_ms"] == old["gap_half_width_ms"])
    actions_out = []
    for action in actions:
        a, b = series[("w0", action)], series[("last_send", action)]
        changed = sum(x[0] != y[0] for x, y in zip(a, b))
        diffs = [y[0] - x[0] for x, y in zip(a, b)]
        mean = math.fsum(diffs) / len(diffs)
        sd = math.sqrt(math.fsum((d - mean) ** 2 for d in diffs) / (len(diffs) - 1))
        actions_out.append({"action": list(action), "w0_mean_hct_ms": tables["w0"][(CONTEXT_ID, action)]["mean_hct_ms"],
                            "last_send_mean_hct_ms": tables["last_send"][(CONTEXT_ID, action)]["mean_hct_ms"],
                            "paired_change_ms": mean, "paired_change_se_ms": sd / math.sqrt(len(diffs)),
                            "connections_changed": changed, "connections_with_server_retransmission_w0": sum(x[4] for x in a),
                            "w0_gap_to_reference_ms": tables["w0"][(CONTEXT_ID, action)]["mean_gap_ms"],
                            "last_send_gap_to_reference_ms": tables["last_send"][(CONTEXT_ID, action)]["mean_gap_ms"]})
    original = comparisons(runs, tables["w0"])
    patched = comparisons(runs, tables["last_send"])
    changes = [{"candidate": o["candidate"], "baseline": o["baseline"], "w0_status": o["status"], "last_send_status": p["status"],
                "w0_seed_mean_ms": o["seed_mean_ms"], "last_send_seed_mean_ms": p["seed_mean_ms"],
                "w0_adjusted_ms": o["adjusted_interval_ms"], "last_send_adjusted_ms": p["adjusted_interval_ms"]}
               for o, p in zip(original, patched)]
    payload = {"item": "E-J8-1", "started_kst": started_kst, "finished_kst": now(), "seconds": time.monotonic() - started,
               "patch": "server PTO deadline = max(now, last ack-eliciting server data send + PTO * 2^retry), as quic-go v0.61.0 getPTOTimeAndSpace; single packet-number space; worldsim.py on disk is unchanged",
               "patch_text": [list(item) for item in PATCHES], "world_source_sha256": file_hash(WORLD_SOURCE),
               "patched_source_sha256": hashlib.sha256(patched_source().encode("utf-8")).hexdigest(),
               "script_sha256": file_hash(Path(__file__)), "scenario": SCENARIO, "context_id": CONTEXT_ID, "context": context,
               "reference_action": list(reference), "seed": SEED, "samples": args.samples, "evaluation_family_size": FAMILY,
               "w0_tables_reproduce_j6_pool": reproduction, "inputs_sha256": dict(sorted(used.items())),
               "actions": actions_out, "comparisons": changes,
               "scope": "Diagnostic of the W1 B7 judgments under a corrected server PTO base. Selection seed 850001 is reused only to reproduce the stored tables. No frozen result is replaced."}
    initial_count_diag.merge_section(args.out, "j8_pto", payload)
    print(json.dumps({"out": str(args.out), "seconds": payload["seconds"],
                      "reproduced": all(reproduction.values()) if reproduction else None}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
