import sys
sys.dont_write_bytecode = True
import argparse
import collections
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import time


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.v33 import bench, oracle
from experiments.v33.bench_metrics import paired_summary
from experiments.v33.first_flight_observer import make_world_evidence
from padfec3 import decide3, learn3


RUN_SCHEMA = "padfec.v33.cx1_eval_run/1"
SUMMARY_SCHEMA = "padfec.v33.cx1_eval_summary/1"
RUNS_ENV = "CX1_EVAL_RUNS"
TABLE_RUNS = ("L3_joint_action_pool_v1/results", "W1_action_pool_full_v1/results")
V32_RAW_RUN = "W1_raw_v32/v32/full"
PROTOCOL_PATH = ROOT / "g3/v33/bench_protocol.json"
EXPLORE = {"rate_ms": 0.05, "cap_ms": 100.0}
STRUCTURAL = {"B4": ((0, 0, 1), (1, 0, 0), (0, 0, 3))}
REPEAT_CELLS = ("B10",)
REPEAT_SEEDS = tuple(range(51, 131))
GATE_MS = 0.5
HCT_TOLERANCE_MS = 1e-9
MODES = ("none", "c1")
PARTS = ("w1", "c1", "rep")
PACKAGES = ("afec", "padfec", "padfec3")
EXPERIMENT_SOURCES = ("bench.py", "bench_metrics.py", "worldsim.py", "worldparams.json",
                      "first_flight_observer.py", "oracle.py", "cx1_eval.py")

PROTOCOL = bench.load_protocol(PROTOCOL_PATH)
SCENARIOS = {s["id"]: s for s in PROTOCOL["scenarios"]}
C_PKT = PROTOCOL["c_pkt"]


def run(cell, seed, explore, mode="none"):
    if mode not in MODES:
        raise ValueError("unknown mode: %r" % (mode,))
    scenario = SCENARIOS[cell]
    W = scenario["context"]["w"]
    u = scenario["context"]["uplink_mbps"]
    st = learn3.new_state()
    rtt = bench.ObservedRTT()
    world = bench.World(params=scenario["world_params"], seed=seed)
    idx = 0
    counts = collections.Counter()
    rows = []
    for pn, phase in enumerate(scenario["phases"]):
        spec = bench.context_spec(scenario, phase)
        cid = bench.context_id(spec)
        for pi in range(phase["length"]):
            if scenario["reset_each_connection"]:
                st = learn3.new_state()
                rtt = bench.ObservedRTT()
            if explore is not None:
                dec = decide3.decide3(st, W, u, rtt.value(), C_PKT, explore=explore)
            else:
                dec = decide3.decide3(st, W, u, rtt.value(), C_PKT)
            ctx = bench.mixture_context(spec, seed, idx)
            a = tuple(dec["action"])
            extra = {}
            if mode == "c1":
                obs = world.sample(ctx, bench.Action(*a), connection=idx, trace=True)
                projection = make_world_evidence(
                    obs, mode="c1", seed=seed, connection=idx,
                    feedback_loss_probability=ctx.s2c_loss if world.params["features"]["s2c_loss"] else 0.0,
                    receiver_max_datagram_bytes=world.params["server"]["decoder_max_datagram_bytes"],
                    feedback_grace_ms=200, crc_list_limit=64)
                extra["arrivals"] = projection["evidence"]
            else:
                obs = world.sample(ctx, bench.Action(*a), connection=idx)
            rtt.observe(obs)
            info = learn3.observe3(st, a, obs["hct"] if obs["ok"] else None, obs["ok"],
                                   obs["k_obs"], obs["srv_bytes"], rtt.value(), W=W, u_mbps=u,
                                   c_pkt=C_PKT, j_pred=dec.get("j3_pred_pre_ms", dec.get("ej")), **extra)
            counts[(cid, a)] += 1
            rows.append((pn, pi, a, obs["hct"], obs["ok"], obs["server_counted_uplink_bytes"],
                         dec["p_mean"], dec.get("why"), info.get("y"), info.get("updated"),
                         getattr(st, "x_ledger", None)))
            idx += 1
    return {"cell": cell, "seed": seed, "n": idx,
            "counts": [[c, list(a), n] for (c, a), n in sorted(counts.items())],
            "mean_hct": statistics.fmean(r[3] for r in rows),
            "mean_bytes": statistics.fmean(r[5] for r in rows),
            "fail": sum(not r[4] for r in rows),
            "last400": {"mean_hct": statistics.fmean(r[3] for r in rows[-400:]),
                        "mean_bytes": statistics.fmean(r[5] for r in rows[-400:]),
                        "p_mean_end": rows[-1][6],
                        "actions": collections.Counter(str(r[2]) for r in rows[-400:]).most_common(6)},
            "explore_n": sum(r[7] == "explore" for r in rows),
            "explore_events": sum(r[7] == "explore" and r[8] == 1 for r in rows),
            "phase": [{"pn": pn,
                       "mean_hct": statistics.fmean(r[3] for r in rows if r[0] == pn),
                       "mean_bytes": statistics.fmean(r[5] for r in rows if r[0] == pn),
                       "p_end": [r[6] for r in rows if r[0] == pn][-1],
                       "x": sum(r[7] == "explore" for r in rows if r[0] == pn)}
                      for pn in range(len(scenario["phases"]))]}


def parse_cells(text):
    cells = list(SCENARIOS) if text == "all" else text.split(",")
    unknown = [c for c in cells if c not in SCENARIOS]
    if unknown:
        raise ValueError("unknown cells: %s" % ",".join(unknown))
    return cells


def parse_seeds(text):
    if text == "all":
        return list(PROTOCOL["seeds"])
    if "-" in text:
        lo, hi = text.split("-")
        return list(range(int(lo), int(hi) + 1))
    return [int(x) for x in text.split(",")]


def arm_value(name):
    if name == "on":
        return dict(EXPLORE)
    if name == "off":
        return None
    raise ValueError("explore must be on or off")


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_jobs(jobs, workers, scratch):
    scratch = Path(scratch)
    scratch.mkdir(parents=True)
    shards = [jobs[i::workers] for i in range(workers)]
    running = []
    for i, shard in enumerate(shards):
        if not shard:
            continue
        job_path = scratch / ("jobs_%02d.json" % i)
        out_path = scratch / ("out_%02d.json" % i)
        err_path = scratch / ("err_%02d.txt" % i)
        write_new(job_path, shard)
        command = [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "shard",
                   "--jobs", str(job_path), "--out", str(out_path)]
        err = err_path.open("x", encoding="utf-8")
        running.append((subprocess.Popen(command, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=err), err,
                        out_path, err_path, job_path))
    results = []
    failed = []
    for process, err, out_path, err_path, job_path in running:
        code = process.wait()
        err.close()
        if code != 0:
            failed.append("%s rc=%d %s" % (out_path.name, code, err_path.read_text(encoding="utf-8")[-2000:]))
            continue
        results.extend(read_json(out_path))
        for path in (out_path, err_path, job_path):
            path.unlink()
    if failed:
        raise RuntimeError("shard failure: " + " | ".join(failed))
    scratch.rmdir()
    return sorted(results, key=lambda r: (r["cell"], r["seed"]))


def run_arm(explore_name, mode, cells, seeds, workers, out):
    out = Path(out)
    if out.exists():
        raise FileExistsError(out)
    explore = arm_value(explore_name)
    jobs = [[cell, seed, explore, mode] for cell in cells for seed in seeds]
    started = time.time()
    results = run_jobs(jobs, workers, out.with_name(out.stem + "_shards"))
    elapsed = round(time.time() - started, 1)
    value = {"schema": RUN_SCHEMA, "arm": explore, "explore": explore_name, "mode": mode,
             "cells": cells, "seeds": seeds, "elapsed_s": elapsed, "results": results}
    write_new(out, value)
    print("run", explore_name, mode, len(results), "elapsed", elapsed, flush=True)
    return value


def shard(jobs_path, out_path):
    jobs = read_json(jobs_path)
    write_new(out_path, [run(cell, seed, explore, mode) for cell, seed, explore, mode in jobs])


def runs_root(value=None):
    value = value or os.environ.get(RUNS_ENV)
    if not value:
        raise ValueError("give --runs or set %s to the v33 runs folder" % RUNS_ENV)
    root = Path(value)
    if not root.is_dir():
        raise FileNotFoundError("v33 runs folder not found: %s" % root)
    return root


def structural_tables(out_dir, runs):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True)
    made = []
    for cell, actions in STRUCTURAL.items():
        scenario = SCENARIOS[cell]
        for phase in scenario["phases"]:
            cid = bench.context_id(bench.context_spec(scenario, phase))
            templates = sorted((Path(runs) / TABLE_RUNS[0]).glob(cid + "_*.json"))
            if not templates:
                raise FileNotFoundError("no L3 table for %s %s" % (cell, cid))
            template = read_json(templates[0])
            for action in actions:
                report = oracle.evaluate_action(template["context"], list(action), template["reference_action"],
                                                world_params=template.get("world_params"),
                                                spec=template.get("spec"))
                if (report.get("method") != "structural_zero_loss_pair" or report.get("status") != "complete"
                        or report.get("uncertainty_resolved") is not True):
                    raise ValueError("table is not a structural zero-loss pair: %s %s" % (cid, action))
                report["context_id"] = cid
                path = out_dir / ("%s_%d_%d_%d.json" % ((cid,) + tuple(action)))
                write_new(path, report)
                made.append({"cell": cell, "context_id": cid, "action": list(action),
                             "method": report["method"], "mean_gap_ms": report["mean_gap_ms"],
                             "gap_half_width_ms": report["gap_half_width_ms"],
                             "mean_server_counted_uplink_bytes": report["mean_server_counted_uplink_bytes"],
                             "template": templates[0].name})
    return made


def load_tables(runs, extra=None):
    tables = {}
    counts = {}
    folders = [("runs:" + name, Path(runs) / name) for name in TABLE_RUNS] + list((extra or {}).items())
    for label, folder in folders:
        paths = sorted(Path(folder).glob("*.json"))
        counts[label] = len(paths)
        for path in paths:
            item = read_json(path)
            tables.setdefault((item["context_id"], tuple(item["action"])), item)
    return tables, counts


def by_cell(results):
    out = collections.defaultdict(dict)
    for r in results:
        out[r["cell"]][r["seed"]] = r
    return out


def judge(arm_results, base_results, tables):
    A, B = by_cell(arm_results), by_cell(base_results)
    rows = []
    for cell in sorted(A):
        est, real, coef = [], [], collections.Counter()
        missing = set()
        for seed, r in sorted(A[cell].items()):
            b = B[cell][seed]
            cw = {(c, tuple(a)): k / r["n"] for c, a, k in r["counts"]}
            bw = {(c, tuple(a)): k / b["n"] for c, a, k in b["counts"]}
            diff = {k: cw.get(k, 0.0) - bw.get(k, 0.0) for k in set(cw) | set(bw)}
            absent = [k for k, v in diff.items() if v and k not in tables]
            missing.update(absent)
            est.append(None if absent else math.fsum(v * tables[k]["mean_gap_ms"] for k, v in diff.items() if v))
            for k, v in diff.items():
                coef[k] += v / len(A[cell])
            real.append(r["mean_hct"] - b["mean_hct"])
        rs = paired_summary(real)
        row = {"cell": cell, "seeds": len(est), "missing": sorted("%s %s" % (c, list(a)) for c, a in missing)}
        if missing:
            row["gate"] = "missing_table"
        else:
            s = paired_summary(est)
            widths = [(abs(v), tables[k].get("gap_half_width_ms")) for k, v in coef.items() if v]
            mc = None if any(w is None for _, w in widths) else math.fsum(a * w for a, w in widths)
            row.update({"mean": round(s["mean"], 6), "sd": round(s["sd"], 6),
                        "seed_lower": round(s["lower"], 6), "seed_upper": round(s["upper"], 6),
                        "mc": None if mc is None else round(mc, 6),
                        "adj_upper": None if mc is None else round(s["upper"] + mc, 6),
                        "adj_lower": None if mc is None else round(s["lower"] - mc, 6),
                        "gate": ("inconclusive" if mc is None else "pass" if s["upper"] + mc <= GATE_MS
                                 else "fail" if s["lower"] - mc > GATE_MS else "inconclusive"),
                        "changed_keys": [["%s" % k[0], list(k[1]), round(v, 9),
                                          tables[k]["mean_gap_ms"], tables[k].get("gap_half_width_ms"),
                                          tables[k].get("method")]
                                         for k, v in sorted(coef.items()) if v]})
        row.update({"real_mean": round(rs["mean"], 6), "real_lower": round(rs["lower"], 6),
                    "real_upper": round(rs["upper"], 6),
                    "bytes_arm": round(statistics.fmean(r["mean_bytes"] for r in A[cell].values()), 1),
                    "bytes_base": round(statistics.fmean(r["mean_bytes"] for r in B[cell].values()), 1),
                    "explore": round(statistics.fmean(r["explore_n"] for r in A[cell].values()), 2),
                    "events": round(statistics.fmean(r["explore_events"] for r in A[cell].values()), 2),
                    "last400_bytes_arm": round(statistics.fmean(r["last400"]["mean_bytes"] for r in A[cell].values()), 1),
                    "last400_bytes_base": round(statistics.fmean(r["last400"]["mean_bytes"] for r in B[cell].values()), 1),
                    "p_end_arm": round(statistics.fmean(r["last400"]["p_mean_end"] for r in A[cell].values()), 5),
                    "p_end_base": round(statistics.fmean(r["last400"]["p_mean_end"] for r in B[cell].values()), 5),
                    "fail_arm": sum(r["fail"] for r in A[cell].values()),
                    "fail_base": sum(r["fail"] for r in B[cell].values()),
                    "identical_seeds": sum(A[cell][s0]["counts"] == B[cell][s0]["counts"] for s0 in A[cell])})
        rows.append(row)
    return rows


def keyed(results):
    out = {(r["cell"], r["seed"]): r for r in results}
    if len(out) != len(results):
        raise ValueError("duplicate cell and seed")
    return out


def normal_counts(items):
    return sorted([c, list(a), n] for c, a, n in items)


def compare_runs(a_results, b_results):
    A, B = keyed(a_results), keyed(b_results)
    if set(A) != set(B):
        raise ValueError("run sets differ")
    diffs = [abs(A[k]["mean_hct"] - B[k]["mean_hct"]) for k in A]
    return {"runs": len(A),
            "counts_equal": sum(normal_counts(A[k]["counts"]) == normal_counts(B[k]["counts"]) for k in A),
            "mean_hct_within_tolerance": sum(d <= HCT_TOLERANCE_MS for d in diffs),
            "mean_hct_bit_equal": sum(d == 0.0 for d in diffs),
            "max_abs_mean_hct_diff_ms": max(diffs),
            "records_equal": sum(A[k] == B[k] for k in A),
            "explore_n_a": sum(A[k]["explore_n"] for k in A),
            "explore_n_b": sum(B[k]["explore_n"] for k in B),
            "tolerance_ms": HCT_TOLERANCE_MS}


def compare_v32(results, runs):
    counts_equal = 0
    diffs = []
    for r in results:
        frozen = read_json(Path(runs) / V32_RAW_RUN / r["cell"] / ("seed%05d.json" % r["seed"]))
        if frozen["seed"] != r["seed"] or frozen["n"] != r["n"]:
            raise ValueError("frozen run mismatch: %s %s" % (r["cell"], r["seed"]))
        frozen_counts = [[i["context_id"], i["action"], i["n"]] for i in frozen["action_counts"]]
        counts_equal += normal_counts(r["counts"]) == normal_counts(frozen_counts)
        diffs.append(abs(r["mean_hct"] - frozen["summary"]["mean_hct_ms"]))
    return {"runs": len(results), "reference": "runs:" + V32_RAW_RUN, "counts_equal": counts_equal,
            "mean_hct_within_tolerance": sum(d <= HCT_TOLERANCE_MS for d in diffs),
            "mean_hct_bit_equal": sum(d == 0.0 for d in diffs),
            "max_abs_mean_hct_diff_ms": max(diffs), "tolerance_ms": HCT_TOLERANCE_MS}


def sources():
    files = {path.relative_to(ROOT).as_posix(): bench.file_hash(path)
             for package in PACKAGES for path in sorted((ROOT / package).rglob("*.py"))}
    for name in EXPERIMENT_SOURCES:
        files["experiments/v33/" + name] = bench.file_hash(ROOT / "experiments/v33" / name)
    files["g3/v33/bench_protocol.json"] = bench.file_hash(PROTOCOL_PATH)
    return files


def run_all(work, workers, parts, runs):
    work = Path(work)
    work.mkdir(parents=True)
    started = time.time()
    summary = {"schema": SUMMARY_SCHEMA, "explore": EXPLORE, "gate_ms": GATE_MS, "parts": list(parts),
               "workers": workers, "sources_before": sources(), "evidence_kind": "W0 world simulation"}
    cells = list(SCENARIOS)
    seeds = list(PROTOCOL["seeds"])
    extra = {}
    if "w1" in parts or "rep" in parts:
        summary["structural_tables"] = structural_tables(work / "extra_tables", runs)
        extra = {"work:extra_tables": work / "extra_tables"}
    tables, table_counts = load_tables(runs, extra)
    summary["table_files"] = table_counts
    if "w1" in parts:
        on = run_arm("on", "none", cells, seeds, workers, work / "w1_on.json")
        off = run_arm("off", "none", cells, seeds, workers, work / "w1_off.json")
        summary["w1"] = {"cells": cells, "seeds": seeds, "elapsed_s": [on["elapsed_s"], off["elapsed_s"]],
                         "judge": judge(on["results"], off["results"], tables),
                         "off_vs_w1_raw_v32": compare_v32(off["results"], runs)}
    if "rep" in parts:
        on = run_arm("on", "none", list(REPEAT_CELLS), list(REPEAT_SEEDS), workers, work / "rep_on.json")
        off = run_arm("off", "none", list(REPEAT_CELLS), list(REPEAT_SEEDS), workers, work / "rep_off.json")
        summary["rep"] = {"cells": list(REPEAT_CELLS), "seeds": [REPEAT_SEEDS[0], REPEAT_SEEDS[-1]],
                          "elapsed_s": [on["elapsed_s"], off["elapsed_s"]],
                          "judge": judge(on["results"], off["results"], tables)}
    if "c1" in parts:
        on = run_arm("on", "c1", cells, seeds, workers, work / "c1_on.json")
        off = run_arm("off", "c1", cells, seeds, workers, work / "c1_off.json")
        summary["c1"] = {"cells": cells, "seeds": seeds, "elapsed_s": [on["elapsed_s"], off["elapsed_s"]],
                         "on_vs_off": compare_runs(on["results"], off["results"])}
    summary["sources_after"] = sources()
    summary["sources_stable"] = summary["sources_after"] == summary["sources_before"]
    summary["elapsed_s"] = round(time.time() - started, 1)
    write_new(work / "summary.json", summary)
    print(json.dumps({k: summary[k] for k in ("elapsed_s", "sources_stable")}), flush=True)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description="CX1 opt-in exploration world evaluation")
    sub = parser.add_subparsers(dest="command", required=True)
    inputs = argparse.ArgumentParser(add_help=False)
    inputs.add_argument("--runs", help="v33 runs folder with the L3, W1 and W1_raw_v32 inputs (default: $%s)" % RUNS_ENV)
    p = sub.add_parser("run")
    p.add_argument("--explore", choices=("on", "off"), required=True)
    p.add_argument("--mode", choices=MODES, default="none")
    p.add_argument("--cells", default="all")
    p.add_argument("--seeds", default="all")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--out", required=True)
    p = sub.add_parser("shard")
    p.add_argument("--jobs", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("tables", parents=[inputs])
    p.add_argument("--out", required=True)
    p = sub.add_parser("judge", parents=[inputs])
    p.add_argument("--arm", required=True)
    p.add_argument("--base", required=True)
    p.add_argument("--tables", action="append", default=[])
    p.add_argument("--out")
    p = sub.add_parser("compare", parents=[inputs])
    p.add_argument("--a", required=True)
    p.add_argument("--b")
    p.add_argument("--v32", action="store_true")
    p.add_argument("--out")
    p = sub.add_parser("all", parents=[inputs])
    p.add_argument("--work", required=True)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--parts", default=",".join(PARTS))
    args = parser.parse_args(argv)
    if args.command == "run":
        if args.workers < 1:
            raise ValueError("workers must be positive")
        run_arm(args.explore, args.mode, parse_cells(args.cells), parse_seeds(args.seeds), args.workers, args.out)
    elif args.command == "shard":
        shard(args.jobs, args.out)
    elif args.command == "tables":
        print(json.dumps(structural_tables(args.out, runs_root(args.runs)), ensure_ascii=False))
    elif args.command == "judge":
        tables, _ = load_tables(runs_root(args.runs), {str(x): Path(x) for x in args.tables})
        rows = judge(read_json(args.arm)["results"], read_json(args.base)["results"], tables)
        if args.out:
            write_new(args.out, rows)
        for row in rows:
            print(json.dumps({k: v for k, v in row.items() if k != "changed_keys"}, ensure_ascii=False))
    elif args.command == "compare":
        a = read_json(args.a)["results"]
        if args.v32 == (args.b is not None):
            raise ValueError("give exactly one of --b or --v32")
        result = compare_v32(a, runs_root(args.runs)) if args.v32 else compare_runs(a, read_json(args.b)["results"])
        if args.out:
            write_new(args.out, result)
        print(json.dumps(result))
    else:
        parts = [x for x in args.parts.split(",") if x]
        if not parts or any(x not in PARTS for x in parts):
            raise ValueError("parts must come from %s" % ",".join(PARTS))
        if args.workers < 1:
            raise ValueError("workers must be positive")
        run_all(args.work, args.workers, parts, runs_root(args.runs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
