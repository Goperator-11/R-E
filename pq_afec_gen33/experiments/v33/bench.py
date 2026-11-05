import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import argparse
import collections
import dataclasses
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import random
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.v33.worldsim import Action, World, WorldContext


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def load_protocol(path):
    protocol = json.loads(path.read_text(encoding="utf-8"))
    if protocol.get("schema") != "padfec.v33.benchmark/1":
        raise ValueError("unsupported benchmark protocol")
    if protocol.get("world", {}).get("profile") != "default":
        raise ValueError("the benchmark requires the independent event world")
    if set(protocol["world"].get("source_sha256", {})) != {"worldsim.py","worldparams.json"}:
        raise ValueError("both frozen world source hashes are required")
    for name, expected in protocol["world"]["source_sha256"].items():
        if file_hash(Path(__file__).with_name(name)) != expected:
            raise ValueError(f"world source differs from frozen protocol: {name}")
    seeds = protocol["seeds"]
    if len(seeds) < 20 or len(set(seeds)) != len(seeds):
        raise ValueError("benchmark requires at least 20 distinct seeds")
    if any(isinstance(s, bool) or not isinstance(s, int) or s < 0 for s in seeds):
        raise ValueError("seeds must be nonnegative integers")
    ids = [s["id"] for s in protocol["scenarios"]]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate scenario")
    if {s["family"] for s in protocol["scenarios"]} != {f"B{i}" for i in range(1,13)}:
        raise ValueError("all 12 scenario families are required")
    for scenario in protocol["scenarios"]:
        WorldContext(**scenario["context"])
        for phase in scenario["phases"]:
            if isinstance(phase["length"], bool) or not isinstance(phase["length"], int) or phase["length"] < 1:
                raise ValueError("phase length must be a positive integer")
            World()._check(WorldContext(**phase_context(scenario, phase)), Action())
        mixture = scenario.get("mixture", [])
        if mixture and (abs(sum(m["weight"] for m in mixture) - 1) > 1e-12 or any(m["weight"] <= 0 for m in mixture)):
            raise ValueError("mixture weights must be positive and sum to one")
    return protocol


def phase_context(scenario, phase):
    return {**scenario["context"], **{key:value for key,value in phase.items() if key != "length"}}


def context_spec(scenario, phase):
    return {"context":phase_context(scenario, phase), "world_params":scenario["world_params"], "mixture":scenario.get("mixture", [])}


def context_id(spec):
    return digest(spec)[:20]


def all_contexts(protocol):
    result = {}
    for scenario in protocol["scenarios"]:
        for phase in scenario["phases"]:
            spec = context_spec(scenario, phase)
            key = context_id(spec)
            if key in result and result[key] != spec:
                raise ValueError("context digest collision")
            result[key] = spec
    return result


def mixture_context(spec, seed, connection):
    context = dict(spec["context"])
    if spec["mixture"]:
        source = int.from_bytes(hashlib.blake2b(f"{seed}:{connection}:mixture".encode(), digest_size=16).digest(), "big")
        value = random.Random(source).random()
        cumulative = 0.0
        for component in spec["mixture"]:
            cumulative += component["weight"]
            if value < cumulative:
                context.update(component["context"])
                break
    return WorldContext(**context)


class PolicyWorker:
    def __init__(self, source_root, scenario, protocol, variant, log_path):
        self.error_stream = log_path.open("x", encoding="utf-8", newline="\n")
        self.process = subprocess.Popen([sys.executable, "-I", "-B", str(Path(__file__).with_name("policy_worker.py"))], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.error_stream, text=True, encoding="utf-8", bufsize=1)
        try:
            self.initial = self.request({"op":"init", "source_root":str(source_root), "W":scenario["context"]["w"], "u_mbps":scenario["context"]["uplink_mbps"], "c_pkt":protocol["c_pkt"], "variant":variant})
        except BaseException:
            self.process.stdin.close()
            self.process.wait(timeout=30)
            self.error_stream.close()
            raise

    def request(self, request):
        self.process.stdin.write(json.dumps(request, ensure_ascii=False, allow_nan=False) + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError(f"policy worker ended with {self.process.poll()}")
        result = json.loads(line)
        if not result.get("ok"):
            raise RuntimeError(f"policy worker rejected request: {result}")
        return result["result"]

    def close(self):
        if self.process.stdin and not self.process.stdin.closed:
            self.process.stdin.close()
        code = self.process.wait(timeout=30)
        self.error_stream.close()
        if code != 0:
            raise RuntimeError(f"policy worker exit {code}")


class ObservedRTT:
    def __init__(self):
        self.minimum_rtt = None
        self.minimum_hct = None

    def observe(self, row):
        value = row.get("rtt")
        if value is not None and math.isfinite(value) and value > 0:
            self.minimum_rtt = value if self.minimum_rtt is None else min(self.minimum_rtt, value)
        if row["ok"]:
            self.minimum_hct = row["hct"] if self.minimum_hct is None else min(self.minimum_hct, row["hct"])

    def value(self):
        return self.minimum_rtt if self.minimum_rtt is not None else self.minimum_hct


def observation_request(decision, row, rtt):
    return {"op":"observe", "destination":"d", "action":decision["action"], "hct_ms":row["hct"] if row["ok"] else None, "ok":row["ok"], "k_obs":row["k_obs"], "srv_bytes":row["srv_bytes"], "rtt_ms":rtt, "j_pred":decision.get("j3_pred_pre_ms", decision.get("ej"))}


def source_hashes():
    names = ["bench.py", "bench_metrics.py", "policy_worker.py", "worldsim.py", "worldparams.json"]
    return {name:file_hash(Path(__file__).with_name(name)) for name in names}


def policy_source_fingerprints(protocol, generations):
    results = {}
    for generation in generations:
        root = Path(protocol["generations"][generation]["source_root"]).resolve()
        files = {path.relative_to(root).as_posix():file_hash(path) for package in ("afec","padfec","padfec3") for path in sorted((root / package).rglob("*.py"))}
        results[generation] = {"source_root":str(root), "files":files}
    return results


def validate_policy_audit(audit, fingerprint):
    root = Path(fingerprint["source_root"])
    if Path(audit["source_root"]).resolve() != root or not audit.get("source_unchanged"):
        raise ValueError("policy source identity differs")
    for path, value in audit["source_sha256"].items():
        relative = Path(path).resolve().relative_to(root).as_posix()
        if fingerprint["files"].get(relative) != value:
            raise ValueError(f"loaded policy file differs: {relative}")


def validate_resume(result, *, generation, variant, scenario, seed, planned, fingerprint):
    expected_n = sum(min(phase["length"],4) if planned["mode"] == "smoke" else phase["length"] for phase in scenario["phases"])
    expected = {"generation":generation,"variant":variant,"scenario":scenario["id"],"seed":seed,"mode":planned["mode"],"protocol_sha256":planned["protocol_sha256"],"n":expected_n}
    if any(result.get(key) != value for key,value in expected.items()):
        raise ValueError("resume run identity differs")
    if result["trace_sha256"] != file_hash(result["trace_path"]):
        raise ValueError("resume trace differs")
    validate_policy_audit(result["policy_audit"], fingerprint)


def run_seed(worker, scenario, protocol, seed, trace_path, smoke=False):
    from experiments.v33.bench_metrics import summarize_run
    worker.request({"op":"reset", "destination":"d"})
    observed_rtt = ObservedRTT()
    world = World(params=scenario["world_params"], seed=seed)
    baseline = World(params=scenario["world_params"], seed=seed)
    fixed = World(params=scenario["world_params"], seed=seed)
    rows = []
    index = 0
    with trace_path.open("xb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as zipped:
            with io.TextIOWrapper(zipped, encoding="utf-8", newline="\n") as stream:
                for phase_number, phase in enumerate(scenario["phases"]):
                    spec = context_spec(scenario, phase)
                    cid = context_id(spec)
                    for phase_index in range(min(phase["length"], 4) if smoke else phase["length"]):
                        if scenario["reset_each_connection"]:
                            worker.request({"op":"reset", "destination":"d"})
                            observed_rtt = ObservedRTT()
                        decide_input = {"op":"decide", "destination":"d", "rtt_ms":observed_rtt.value()}
                        result = worker.request(decide_input)
                        decision = result["decision"]
                        context = mixture_context(spec, seed, index)
                        action = Action(*decision["action"])
                        observation = world.sample(context, action, connection=index)
                        b0 = baseline.sample(context, Action(), connection=index)
                        global_fixed = fixed.sample(context, Action(0,3,1), connection=index)
                        observed_rtt.observe(observation)
                        observe_input = observation_request(decision, observation, observed_rtt.value())
                        feedback = worker.request(observe_input)
                        info = feedback["observation"]
                        first_received = sum(packet["read_size"] for packet in observation["arrivals"] if packet["flight"] == 0 and packet["arrived"])
                        row = {"index":index, "phase":phase_number, "phase_index":phase_index, "phase_p":context.p, "p_mean_pre":decision["p_mean"], "S_hat_pre":result["before"]["S_hat"], "action":list(decision["action"]), "context_id":cid, "hct_ms":observation["hct"], "ok":observation["ok"], "extra_server_bytes":observation["server_counted_uplink_bytes"]-b0["server_counted_uplink_bytes"], "extra_first_flight_bytes":first_received-context.k*context.w, "extra_client_first_flight_bytes":observation["client_first_flight_bytes"]-context.k*context.w, "server_bytes":observation["server_counted_uplink_bytes"], "b0_server_bytes":b0["server_counted_uplink_bytes"], "alarm_raised":info.get("raised", []), "guard_alarm":decision.get("guard_alarm", False), "reeval":decision.get("reeval", False), "updated":info.get("updated", False), "decision_why":decision.get("why"), "observation_skip":info.get("skip"), "policy_rtt_ms":observed_rtt.value(), "raw_observed_rtt_ms":observation["rtt"], "S_hat_post":feedback["state"]["S_hat"], "selected_cert_bytes":observation["selected_cert_bytes"], "true_rtt_ms":observation["true_rtt_ms"], "initial_datagrams":observation["initial_datagrams"], "stop_reason":observation["stop_reason"]}
                        row.update(b0_hct_ms=b0["hct"], global_fixed_hct_ms=global_fixed["hct"], global_fixed_server_bytes=global_fixed["server_counted_uplink_bytes"])
                        row.update(policy_decide_input=decide_input, policy_observe_input=observe_input, decision=decision, observation_info=info)
                        rows.append(row)
                        stream.write(json.dumps(row, ensure_ascii=False, separators=(",",":"), allow_nan=False) + "\n")
                        index += 1
    snapshot = worker.request({"op":"snapshot", "destination":"d"})
    counts = collections.Counter((row["context_id"], tuple(row["action"])) for row in rows)
    return {"seed":seed, "n":len(rows), "summary":summarize_run(rows, scenario, protocol), "action_counts":[{"context_id":key[0],"action":list(key[1]),"n":n} for key,n in sorted(counts.items())], "final_state":snapshot["state"], "policy_audit":snapshot["audit"], "trace_path":str(trace_path), "trace_sha256":file_hash(trace_path)}


def run_benchmark(args, protocol):
    selected = [s for s in protocol["scenarios"] if not args.scenarios or s["id"] in args.scenarios]
    if not selected or args.scenarios and set(args.scenarios) != {s["id"] for s in selected}:
        raise ValueError("unknown scenario selection")
    generations = args.generations or ["current"]
    if not set(generations) <= set(protocol["generations"]):
        raise ValueError("unknown generation")
    seeds = protocol["seeds"][:1] if args.smoke else protocol["seeds"]
    planned = {"protocol_sha256":file_hash(args.protocol), "mode":"smoke" if args.smoke else "full", "generations":generations, "variant":args.variant, "scenarios":[s["id"] for s in selected], "seeds":seeds, "connections_per_generation":sum((sum(min(p["length"],4) for p in s["phases"]) if args.smoke else sum(p["length"] for p in s["phases"])) for s in selected)*len(seeds), "context_ids":list(all_contexts(protocol))}
    if args.dry_run:
        print(json.dumps(planned, ensure_ascii=False, indent=2))
        return
    if args.out is None:
        raise ValueError("--out is required")
    args.out.mkdir(parents=True, exist_ok=True)
    sources = source_hashes()
    fingerprints = policy_source_fingerprints(protocol, generations)
    manifest = {**planned, "schema":"padfec.v33.benchmark_raw_manifest/1", "source_sha256":sources, "policy_source_fingerprints":fingerprints, "protocol":protocol}
    manifest_path = args.out / "manifest.json"
    if manifest_path.exists():
        if not args.resume or json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
            raise ValueError("existing manifest differs or --resume is missing")
    else:
        write_new(manifest_path, manifest)
    for generation in generations:
        for scenario in selected:
            folder = args.out / generation / args.variant / scenario["id"]
            folder.mkdir(parents=True, exist_ok=True)
            pending = []
            for seed in seeds:
                summary_path = folder / f"seed{seed:05d}.json"
                if summary_path.exists():
                    old = json.loads(summary_path.read_text(encoding="utf-8"))
                    if not args.resume:
                        raise ValueError("--resume is required")
                    validate_resume(old, generation=generation, variant=args.variant, scenario=scenario, seed=seed, planned=planned, fingerprint=fingerprints[generation])
                else:
                    pending.append(seed)
            if not pending:
                continue
            for seed in pending:
                log_path = folder / f"worker_seed{seed:05d}_{time.time_ns()}.stderr.txt"
                worker = PolicyWorker(protocol["generations"][generation]["source_root"], scenario, protocol, args.variant, log_path)
                try:
                    validate_policy_audit(worker.initial["audit"], fingerprints[generation])
                    write_new(folder / f"worker_seed{seed:05d}_{time.time_ns()}.init.json", worker.initial)
                    start = time.monotonic()
                    trace_path = folder / f"seed{seed:05d}.{time.time_ns()}.jsonl.gz"
                    result = run_seed(worker, scenario, protocol, seed, trace_path, smoke=args.smoke)
                    validate_policy_audit(result["policy_audit"], fingerprints[generation])
                    if source_hashes() != sources or file_hash(args.protocol) != planned["protocol_sha256"]:
                        raise RuntimeError("benchmark source changed during run")
                    result.update(generation=generation, variant=args.variant, scenario=scenario["id"], mode=planned["mode"], protocol_sha256=planned["protocol_sha256"], elapsed_seconds=time.monotonic()-start)
                    write_new(folder / f"seed{seed:05d}.json", result)
                    print(json.dumps({"generation":generation,"variant":args.variant,"scenario":scenario["id"],"seed":seed,"n":result["n"],"elapsed_seconds":result["elapsed_seconds"]}), flush=True)
                finally:
                    worker.close()
    print(json.dumps({"status":"complete","out":str(args.out),"mode":planned["mode"]}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, default=ROOT / "g3/v33/bench_protocol.json")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--generations", nargs="+")
    parser.add_argument("--scenarios", nargs="+")
    parser.add_argument("--variant", choices=("full","guard_off","reeval_off"), default="full")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    protocol = load_protocol(args.protocol)
    run_benchmark(args, protocol)


if __name__ == "__main__":
    main()
