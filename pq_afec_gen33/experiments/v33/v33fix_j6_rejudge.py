import sys
sys.dont_write_bytecode = True
import argparse
from concurrent.futures import ProcessPoolExecutor
import datetime
import hashlib
import json
from pathlib import Path
import time


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.v33 import bench_report, zero_variance


SCHEMA = "padfec.v33fix.j6_rejudge/1"
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
BENCHMARK = ROOT / "g3" / "v33" / "J6_benchmark_v1.json"
PLAN = RUNS / "J6_full_v1_plan.json"
L1_FAMILY = RUNS / "L1_action_family_v1.json"
POOL = RUNS / "J6_joint_action_pool_v1" / "results"
SCENARIO = "B12_c6000"
SEEDS = tuple(range(31, 51))
SAMPLES = 131072
THRESHOLD = 0.5
ASSIGNMENTS = (("0d4cd14cd8ac65a43314", (12, 0, 4), (7, 0, 4), 860001, 860002),
               ("25b8f9c00a6e624fb79f", (12, 0, 2), (7, 0, 2), 860003, 860004))
ROLES = {"j6_none": ("J6_v1", "none"), "j6_c1": ("J6_v1", "c1"), "j6_ideal": ("J6_v1", "ideal"),
         "zero_none": ("J6_margin_zero_v1", "none"), "zero_c1": ("J6_margin_zero_v1", "c1"),
         "l1_none": ("L1", "none"), "l1_c1": ("L1", "c1"), "l1_ideal": ("L1", "ideal"),
         "v31": ("W1", "v31"), "v32": ("W1", "v32")}
PAIRS = [("j6_none", "v32"), ("j6_none", "v31"), ("j6_c1", "v32"), ("j6_c1", "v31"),
         ("j6_ideal", "v32"), ("j6_ideal", "v31"), ("j6_c1", "j6_none"),
         ("j6_none", "l1_none"), ("j6_c1", "l1_c1"), ("j6_ideal", "l1_ideal"),
         ("j6_none", "zero_none"), ("j6_c1", "zero_c1"), ("zero_none", "l1_none"), ("zero_c1", "l1_c1")]
PRIMARY = {("j6_c1", "l1_c1"), ("j6_none", "l1_none")}


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def now():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()


def known_hashes(benchmark):
    known = {}
    provenance = benchmark["provenance"]
    for role in provenance["learning_inputs"].values():
        known.update(role["inputs_sha256"])
    known.update(provenance["action_pool"]["files_sha256"])
    return known


def verified(path, known, used):
    path = str(Path(path))
    if path not in known:
        raise ValueError("input not bound by J6 provenance: " + path)
    actual = file_hash(path)
    if actual != known[path]:
        raise ValueError("input hash differs: " + path)
    used[path] = actual
    return read(path)


def role_dirs(plan, family):
    result = {}
    for job in plan["jobs"]:
        if job["scenario"] == SCENARIO:
            result[(job["policy"], job["mode"])] = Path(job["out"]) / job["mode"] / SCENARIO
    for directory in family["raw_dirs"]:
        for mode in ("none", "c1", "ideal"):
            candidate = Path(directory) / mode / SCENARIO
            if candidate.is_dir():
                result[("L1", mode)] = candidate
    result[("W1", "v31")] = RUNS / "W1_raw_v31" / "v31" / "full" / SCENARIO
    result[("W1", "v32")] = RUNS / "W1_raw_v32" / "v32" / "full" / SCENARIO
    return result


def load_runs(directories, known, used):
    runs = {}
    for alias, key in ROLES.items():
        rows = []
        for seed in SEEDS:
            row = verified(directories[key] / f"seed{seed:05d}.json", known, used)
            if row["seed"] != seed or row["scenario"] != SCENARIO or row["variant"] != "full":
                raise ValueError("unexpected raw run identity")
            if key[0] != "W1" and row.get("observation_mode") != key[1]:
                raise ValueError("unexpected observation mode")
            rows.append(row)
        runs[alias] = rows
    return runs


def load_tables(runs, known, used):
    keys = set()
    for rows in runs.values():
        for row in rows:
            keys.update(bench_report.weights(row))
    tables = {}
    for cid, action in sorted(keys):
        path = POOL / f"{cid}_{action[0]}_{action[1]}_{action[2]}.json"
        table = verified(path, known, used)
        if table["context_id"] != cid or tuple(table["action"]) != action or table["n"] != SAMPLES:
            raise ValueError("unexpected action table identity")
        tables[(cid, action)] = table
    return tables


def stored_comparisons(benchmark):
    result = {}
    for row in benchmark["comparisons"]:
        if row["scenario"] == SCENARIO and row["candidate"]["variant"] == "full":
            result[(row["candidate"]["generation"], row["baseline"]["generation"])] = row
    return result


def reproduce(runs, tables, stored):
    checks = []
    for candidate, baseline in PAIRS:
        actual = bench_report.direct_comparison(runs[candidate], runs[baseline], tables)
        expected = stored[(candidate, baseline)]
        same = all(actual["seed_summary"][key] == expected["seed_summary"][key] for key in ("mean", "lower", "upper"))
        same = same and actual["shared_mc_bound_ms"] == expected["shared_mc_bound_ms"]
        if not same:
            raise ValueError(f"stored J6 comparison is not reproduced: {candidate} vs {baseline}")
        checks.append({"candidate": candidate, "baseline": baseline, "seed_mean_ms": actual["seed_summary"]["mean"],
                       "stored_shared_mc_bound_ms": expected["shared_mc_bound_ms"], "reproduced": True})
    return checks


def _sample(job):
    context, action, seed, samples = job
    return zero_variance.sample_moments(context, action, seed, samples)


def resolve(tables, samples, workers):
    jobs, meta = [], []
    for cid, action, reference, action_seed, reference_seed in ASSIGNMENTS:
        table = tables.get((cid, action))
        if table is None or not zero_variance.needs_resolution(table) or tuple(table["reference_action"]) != reference:
            raise ValueError("assignment does not match an unresolved J6 table")
        jobs.append((table["context"], action, action_seed, samples))
        jobs.append((table["context"], reference, reference_seed, samples))
        meta.append((cid, action, reference, table))
    started = time.monotonic()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        moments = list(pool.map(_sample, jobs))
    elapsed = time.monotonic() - started
    resolved, rows = {}, []
    for index, (cid, action, reference, table) in enumerate(meta):
        a, r = moments[2 * index], moments[2 * index + 1]
        result = zero_variance.interval(a, r, table["evaluation_family_size"], table["confidence"], table["mean_gap_ms"])
        rows.append({"context_id": cid, "context": table["context"], "action": list(action),
                     "reference_action": list(reference), "paired_table_mean_gap_ms": table["mean_gap_ms"],
                     "paired_table_gap_variance_ms2": table["gap_variance_ms2"],
                     "paired_table_seed": table["validation_seed"], "action_moments": a, "reference_moments": r, **result})
        if result["effective_gap_half_width_ms"] is not None:
            resolved[(cid, action)] = result["effective_gap_half_width_ms"]
    return resolved, rows, elapsed


def adoption(benchmark, rejudged):
    primary = []
    for row in benchmark["comparisons"]:
        pair = (row["candidate"]["generation"], row["baseline"]["generation"])
        if pair not in PRIMARY or row["candidate"]["variant"] != "full":
            continue
        gate = row["regression_gate"]
        source = "stored J6_benchmark_v1"
        if row["scenario"] == SCENARIO:
            gate = rejudged[pair]["regression_gate"]
            source = "Z1 rejudge"
        primary.append({"candidate": pair[0], "baseline": pair[1], "scenario": row["scenario"], "status": gate["status"],
                        "adjusted_upper_ms": gate["adjusted_upper"], "source": source})
    if len(primary) != 30:
        raise ValueError("J6 primary comparison count differs from 30")
    upper_ok = all(row["adjusted_upper_ms"] is not None and row["adjusted_upper_ms"] <= THRESHOLD for row in primary)
    c1_decrease = [row["scenario"] for row in primary if row["candidate"] == "j6_c1"
                   and row["adjusted_upper_ms"] is not None and row["adjusted_upper_ms"] < 0]
    return {"rule": "docs/J6_preflight_budget.md 25: every primary cell adjusted upper <= 0.5 ms and at least one C1 cell adjusted upper < 0",
            "primary_cells": primary, "all_primary_upper_within_0_5": upper_ok,
            "c1_decrease_cells": c1_decrease, "adopt_under_original_rule": upper_ok and bool(c1_decrease),
            "active_policy_changed": False}


def forward_rule(benchmark, rejudged):
    rows = []
    for row in benchmark["comparisons"]:
        pair = (row["candidate"]["generation"], row["baseline"]["generation"])
        if pair not in (("j6_none", "v32"), ("j6_c1", "v32")) or row["candidate"]["variant"] != "full":
            continue
        gate = rejudged[pair]["regression_gate"] if row["scenario"] == SCENARIO else row["regression_gate"]
        rows.append({"candidate": pair[0], "baseline": pair[1], "scenario": row["scenario"], "status": gate["status"],
                     "adjusted_lower_ms": gate["adjusted_lower"], "adjusted_upper_ms": gate["adjusted_upper"]})
    failed = [row for row in rows if row["status"] != "pass"]
    return {"rule": "docs/v3.3.1 판정 규칙.md 2.1: every deployment path, none included, must be noninferior to v32",
            "cells": rows, "not_passing": failed, "adopt_under_forward_rule": not failed}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "g3" / "v33" / "V33FIX_J6_rejudge_v1.json")
    parser.add_argument("--samples", type=int, default=SAMPLES)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    if args.out.exists():
        raise SystemExit("refusing to overwrite " + str(args.out))
    started_kst = now()
    rule_sha = zero_variance.check_rule()
    rules_stat = zero_variance.RULES_PATH.stat()
    benchmark = read(BENCHMARK)
    known = known_hashes(benchmark)
    used = {}
    runs = load_runs(role_dirs(read(PLAN), read(L1_FAMILY)), known, used)
    tables = load_tables(runs, known, used)
    stored = stored_comparisons(benchmark)
    checks = reproduce(runs, tables, stored)
    resolved, evaluations, elapsed = resolve(tables, args.samples, args.workers)
    rejudged = {}
    for candidate, baseline in PAIRS:
        row = zero_variance.rejudged_comparison(runs[candidate], runs[baseline], tables, resolved, THRESHOLD)
        row.update({"candidate": candidate, "baseline": baseline, "scenario": SCENARIO,
                    "primary": (candidate, baseline) in PRIMARY,
                    "stored_status": stored[(candidate, baseline)]["regression_gate"]["status"]})
        rejudged[(candidate, baseline)] = row
    output = {"schema": SCHEMA, "data_kind": "development_independent_world_simulation",
              "started_kst": started_kst, "finished_kst": now(),
              "rule_document": str(zero_variance.RULES_PATH), "rule_section_sha256": rule_sha,
              "rule_document_mtime_utc": datetime.datetime.fromtimestamp(rules_stat.st_mtime, datetime.timezone.utc).isoformat(),
              "samples_per_action": args.samples, "sampling_seconds": elapsed,
              "script_sha256": file_hash(Path(__file__)), "zero_variance_sha256": file_hash(zero_variance.__file__),
              "world_sources_sha256": {name: file_hash(ROOT / "experiments" / "v33" / name) for name in ("worldsim.py", "worldparams.json", "oracle.py")},
              "benchmark_sha256": file_hash(BENCHMARK), "inputs_sha256": dict(sorted(used.items())),
              "reproduction_checks": checks, "z1_evaluations": evaluations,
              "comparisons": [rejudged[pair] for pair in PAIRS],
              "j6_adoption": adoption(benchmark, rejudged), "forward_rule": forward_rule(benchmark, rejudged),
              "scope": "Development independent event world. Z1 replaces only the null MC width of the two distinct-action zero-variance tables. Seeds, N, thresholds and the original adoption rule are unchanged. The active policy is not changed."}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "x", encoding="utf-8", newline="\n") as stream:
        json.dump(output, stream, ensure_ascii=False, indent=1, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"out": str(args.out), "adopt_original_rule": output["j6_adoption"]["adopt_under_original_rule"],
                      "adopt_forward_rule": output["forward_rule"]["adopt_under_forward_rule"],
                      "sampling_seconds": elapsed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
