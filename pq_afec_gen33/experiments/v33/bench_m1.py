import sys
sys.dont_write_bytecode = True
import argparse
import collections
import concurrent.futures
import copy
import datetime as dt
import gzip
import io
import json
from pathlib import Path
import subprocess
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.v33 import bench, bench_learning as learning, bench_report
from experiments.v33.bench_metrics import summarize_run
from experiments.v33 import worldsim_m1

bench.World = worldsim_m1.World
bench.WorldContext = worldsim_m1.WorldContext
bench.Action = worldsim_m1.Action

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
PLAN = ROOT / "g3/v33/bench_overlays/M1_evaluation_v1.json"
SOURCES = tuple(dict.fromkeys(("bench_m1.py", "worldsim_m1.py", "worldparams_m1.json", "world_receiver_m1.py", *learning.SOURCE_NAMES)))
SCHEMA = "padfec.v33.m1_factorial/1"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def now():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()


def equal(actual, expected, name):
    learning.equal(actual, expected, "M1 " + name)


def sources():
    return {str(Path(__file__).with_name(name)): bench.file_hash(Path(__file__).with_name(name)) for name in SOURCES}


IMPORTED_SOURCES = sources()


def snapshot_identity(root, receipt_path):
    receipt = read(receipt_path)
    result = learning.snapshot_identity(root, receipt_path)
    version = receipt.get("state_version", 4)
    if version not in (4, 10):
        raise ValueError("unexpected M1 policy state version")
    result["state_version"] = version
    return result


def load_plan(path):
    plan = read(path)
    equal(plan["schema"], SCHEMA, "plan schema")
    equal(plan["source_sha256"], sources(), "producer sources")
    equal(sources(), IMPORTED_SOURCES, "loaded producer identity")
    for name, checksum in plan["inputs_sha256"].items():
        equal(bench.file_hash(name), checksum, "input hash")
    for policy in plan["policies"].values():
        equal(snapshot_identity(policy["fingerprint"]["source_root"], policy["receipt_path"]), policy, "policy snapshot")
    original = bench.load_protocol(Path(plan["original_protocol"]))
    for profile, protocol in plan["protocols"].items():
        expected = copy.deepcopy(original)
        if profile not in ("off", "hold"):
            raise ValueError("unexpected M1 receiver profile")
        for scenario in expected["scenarios"]:
            scenario["world_params"].setdefault("fec", {}).update(lead_mode="buffered" if profile == "hold" else "credit_only", hold_margin_ms=1.0,
                hold_ttl_ms=1000.0, hold_recent_ms=3000.0, hold_flight_memory_bytes=32768)
        equal(protocol, expected, "protocol differs beyond M1 receiver override")
    equal(plan["modes"], ["none", "c1", "ideal"], "all observation modes")
    equal(set(plan["policies"]), {"l1", "m1"}, "policy roles")
    equal(plan["workers"], 8, "worker count")
    return plan


def write_trace(path, rows):
    with Path(path).open("xb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as zipped:
            with io.TextIOWrapper(zipped, encoding="utf-8", newline="\n") as stream:
                for row in rows:
                    stream.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")


def counts(rows):
    values = collections.Counter((row["context_id"], tuple(row["action"])) for row in rows)
    return [{"context_id": key[0], "action": list(key[1]), "n": n} for key, n in sorted(values.items())]


def baseline(plan, profile, scenario, seed, folder):
    world = bench.World(params=scenario["world_params"], seed=seed)
    fixed_world = bench.World(params=scenario["world_params"], seed=seed)
    rows = []
    for phase_number, phase_index, index, phase in learning.schedule(scenario):
        spec = bench.context_spec(scenario, phase)
        context = bench.mixture_context(spec, seed, index)
        b0 = world.sample(context, bench.Action(), connection=index)
        fixed = fixed_world.sample(context, bench.Action(0, 3, 1), connection=index)
        equal((b0["selected_cert_bytes"], b0["true_rtt_ms"]), (fixed["selected_cert_bytes"], fixed["true_rtt_ms"]), "counterfactual CRN")
        rows.append({"index": index, "phase": phase_number, "phase_index": phase_index,
                     "context_id": bench.context_id(spec), "phase_p": context.p, "action": [0, 0, 0],
                     "selected_cert_bytes": b0["selected_cert_bytes"], "true_rtt_ms": b0["true_rtt_ms"],
                     "b0_hct_ms": b0["hct"], "b0_server_bytes": b0["server_counted_uplink_bytes"],
                     "global_fixed_hct_ms": fixed["hct"], "global_fixed_server_bytes": fixed["server_counted_uplink_bytes"]})
    trace = folder / f"seed{seed:05d}.jsonl.gz"
    write_trace(trace, rows)
    value = {"schema": SCHEMA, "profile": profile, "scenario": scenario["id"], "seed": seed,
             "n": len(rows), "action_counts": counts(rows), "trace_path": str(trace),
             "trace_sha256": bench.file_hash(trace), "protocol_sha256": bench.digest(plan["protocols"][profile])}
    bench_report.load_trace(value)
    bench.write_new(folder / f"seed{seed:05d}.json", value)
    return value


def validate_rows(run, scenario, protocol, mode, fixed, smoke):
    rows = bench_report.load_trace(run)
    fixed_rows = bench_report.load_trace(fixed)
    scheduled = list(learning.schedule(scenario, smoke))
    equal(len(rows), len(scheduled), "complete connection count")
    observed_rtt = bench.ObservedRTT()
    for row, (phase_number, phase_index, world_index, phase) in zip(rows, scheduled):
        if scenario["reset_each_connection"]:
            observed_rtt = bench.ObservedRTT()
        spec = bench.context_spec(scenario, phase)
        context = bench.mixture_context(spec, run["seed"], world_index)
        cid = bench.context_id(spec)
        base = learning.counterfactual_row(fixed_rows, world_index, phase_number, phase_index, cid, context)
        for name, expected in {"phase": phase_number, "phase_index": phase_index,
                               "world_connection_index": world_index, "context_id": cid, "observation_mode": mode,
                               "selected_cert_bytes": base["selected_cert_bytes"], "true_rtt_ms": base["true_rtt_ms"]}.items():
            equal(row[name], expected, "trace " + name)
        equal(row["policy_decide_input"], {"op": "decide", "destination": "d", "rtt_ms": observed_rtt.value()}, "causal RTT")
        observed_rtt.observe({"rtt": row["raw_observed_rtt_ms"], "hct": row["hct_ms"], "ok": row["ok"]})
        equal(row["policy_rtt_ms"], observed_rtt.value(), "observed RTT")
        request = row["policy_observe_input"]
        equal(set(request["optional"]), {"first_flight_evidence"}, "observation boundary")
        evidence = request["optional"]["first_flight_evidence"]
        learning.first_flight_evidence(evidence)
        if mode == "none":
            equal(evidence["src"], "none", "none evidence")
        equal(row["action"], request["action"], "action observation pairing")
        equal(row["action"], row["decision"]["action"], "action decision pairing")
    equal(run["summary"], summarize_run(rows, scenario, protocol), "summary recomputation")
    return rows


def collect_job(plan_path, job, out, smoke=False, dry_run=False):
    plan = load_plan(plan_path)
    profile, role, mode, sid = job
    protocol = plan["protocols"][profile]
    scenario = next(s for s in protocol["scenarios"] if s["id"] == sid)
    policy = plan["policies"][role]
    seeds = protocol["seeds"][:1] if smoke else protocol["seeds"]
    manifest = {"schema": SCHEMA, "plan_sha256": bench.file_hash(plan_path), "job": list(job),
                "mode": "smoke" if smoke else "full", "seeds": seeds,
                "source_sha256": sources(), "policy": policy,
                "protocol_sha256": bench.digest(protocol), "started_kst": now()}
    if dry_run:
        return {key: value for key, value in manifest.items() if key != "started_kst"}
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    bench.write_new(out / "manifest.json", manifest)
    try:
        for seed in seeds:
            load_plan(plan_path)
            fixed_path = Path(plan["baseline_root"]) / profile / sid / f"seed{seed:05d}.json"
            fixed = read(fixed_path)
            equal((fixed["profile"], fixed["scenario"], fixed["seed"], fixed["protocol_sha256"]),
                  (profile, sid, seed, bench.digest(protocol)), "counterfactual profile")
            worker = bench.PolicyWorker(policy["fingerprint"]["source_root"], scenario, protocol, "full", out / f"seed{seed:05d}.stderr.txt")
            try:
                learning.validate_initial(worker.initial, policy)
                run = learning.run_seed(worker, scenario, protocol, seed, out / f"seed{seed:05d}.jsonl.gz", mode, fixed, smoke)
                initial = worker.initial
            finally:
                worker.close()
            learning.validate_audit(run["policy_audit"], policy["fingerprint"])
            run.update(schema=SCHEMA, status="complete", profile=profile, role=role, scenario=sid,
                       observation_mode=mode, mode=manifest["mode"], policy_initial=initial,
                       plan_sha256=manifest["plan_sha256"], source_sha256=manifest["source_sha256"],
                       protocol_sha256=manifest["protocol_sha256"], baseline_path=str(fixed_path),
                       baseline_sha256=bench.file_hash(fixed_path), policy_fingerprint=policy["fingerprint"])
            validate_rows(run, scenario, protocol, mode, fixed, smoke)
            load_plan(plan_path)
            bench.write_new(out / f"seed{seed:05d}.json", run)
        load_plan(plan_path)
        receipt = {"status": "complete", "job": list(job), "seeds": seeds, "ended_kst": now(),
                   "manifest_sha256": bench.file_hash(out / "manifest.json"),
                   "results_sha256": {str(out / f"seed{s:05d}.json"): bench.file_hash(out / f"seed{s:05d}.json") for s in seeds}}
        bench.write_new(out / "finished.json", receipt)
        return receipt
    except BaseException:
        bench.write_new(out / "failed.json", {"status": "failed", "error": traceback.format_exc(), "ended_kst": now()})
        raise


def jobs(plan, smoke=False):
    return [(profile, role, mode, scenario["id"]) for profile, protocol in plan["protocols"].items()
            for role in plan["policies"] for mode in plan["modes"] for scenario in protocol["scenarios"]
            if not smoke or scenario["id"] in ("B1", "B12_c6000")]


def baseline_job(plan, profile, scenario):
    folder = Path(plan["baseline_root"]) / profile / scenario["id"]
    folder.mkdir(parents=True, exist_ok=False)
    for seed in plan["protocols"][profile]["seeds"]:
        baseline(plan, profile, scenario, seed, folder)
    return [profile, scenario["id"]]


def build_baselines(plan):
    base = Path(plan["baseline_root"])
    base.mkdir(parents=True, exist_ok=False)
    with concurrent.futures.ProcessPoolExecutor(max_workers=plan["workers"]) as executor:
        futures = [executor.submit(baseline_job, plan, profile, scenario) for profile, protocol in plan["protocols"].items() for scenario in protocol["scenarios"]]
        completed = [future.result() for future in concurrent.futures.as_completed(futures)]
    bench.write_new(base / "finished.json", {"status": "complete", "jobs": sorted(completed), "ended_kst": now()})
    return {"status": "complete", "jobs": len(completed)}


def batch(plan_path, smoke):
    plan = load_plan(plan_path)
    base = Path(plan["raw_root"] + ("_smoke" if smoke else ""))
    base.mkdir(parents=True, exist_ok=False)
    before = bench.file_hash(plan_path)
    bench.write_new(base / "started.json", {"started_kst": now(), "plan_sha256": before, "jobs": len(jobs(plan, smoke))})
    if not smoke:
        prior = Path(plan["raw_root"] + "_smoke")
        equal(read(prior / "finished.json")["status"], "complete", "smoke completion")
        equal(read(prior / "started.json")["plan_sha256"], before, "smoke plan")
    def one(job):
        label = "_".join(job)
        command = [sys.executable, "-X", "utf8", "-I", "-B", str(Path(__file__).resolve()), "job", "--plan", str(plan_path), "--job", *job, "--out", str(base / label)]
        if smoke:
            command.append("--smoke")
        with (base / (label + ".stdout.txt")).open("xb") as stdout, (base / (label + ".stderr.txt")).open("xb") as stderr:
            result = subprocess.run(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        receipt = {"job": list(job), "command": command, "exit_code": result.returncode,
                   "stdout_sha256": bench.file_hash(base / (label + ".stdout.txt")),
                   "stderr_sha256": bench.file_hash(base / (label + ".stderr.txt"))}
        bench.write_new(base / (label + ".receipt.json"), receipt)
        print(json.dumps({"job": job, "exit_code": result.returncode}), flush=True)
        return receipt
    with concurrent.futures.ThreadPoolExecutor(max_workers=plan["workers"]) as executor:
        futures = [executor.submit(one, job) for job in jobs(plan, smoke)]
        receipts = [future.result() for future in concurrent.futures.as_completed(futures)]
    load_plan(plan_path)
    equal(bench.file_hash(plan_path), before, "plan after collection")
    result = {"status": "complete" if all(r["exit_code"] == 0 for r in receipts) else "failed",
              "jobs": len(receipts), "results": receipts, "ended_kst": now(), "plan_sha256": before}
    bench.write_new(base / "finished.json", result)
    if result["status"] != "complete":
        raise RuntimeError("one or more collection jobs failed")
    return {"status": result["status"], "jobs": result["jobs"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("check", "baselines", "smoke", "full", "job"))
    parser.add_argument("--plan", type=Path, default=PLAN)
    parser.add_argument("--job", nargs=4)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    plan = load_plan(args.plan)
    if (RUNS.parent / "state/MEASURE_LOCK.json").exists():
        raise ValueError("measurement lock forbids simulation")
    if args.command == "check":
        result = {"jobs": len(jobs(plan)), "seed_runs": len(jobs(plan)) * len(plan["protocols"]["off"]["seeds"]), "sources_valid": True}
        for job in jobs(plan, True):
            collect_job(args.plan, job, RUNS / "M1_dry_run_must_not_exist", smoke=True, dry_run=True)
        if (RUNS / "M1_dry_run_must_not_exist").exists():
            raise ValueError("dry-run created data")
    elif args.command == "baselines":
        result = build_baselines(plan)
    elif args.command == "job":
        result = collect_job(args.plan, args.job, args.out, args.smoke, args.dry_run)
    else:
        result = batch(args.plan, args.command == "smoke")
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
