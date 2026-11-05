import sys
sys.dont_write_bytecode = True
import argparse
import dataclasses
import hashlib
import json
import math
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from experiments.v33.worldsim import Action, World, WorldContext
from padfec3 import layout


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(world, context, action, n, classification=False):
    mean = variance_sum = 0.0
    classes = {key: 0 for key in ("one", "two", "tail", "failure_or_initial_retransmission", "unclassified")}
    initial_counts = {}
    initial_failures = failed = retransmitted_or_failed = 0
    byte_sums = {key: 0 for key in ("client_first_flight_bytes", "client_total_uplink_bytes", "server_counted_uplink_bytes", "server_retransmission_bytes")}
    byte_unavailable = {key: 0 for key in byte_sums}
    for i in range(n):
        row = world.sample(context, action, connection=i)
        value = row["hct"]
        if not math.isfinite(value):
            raise ValueError("nonfinite HCT")
        delta = value - mean
        mean += delta / (i + 1)
        variance_sum += delta * (value - mean)
        initial_failures += bool(row["initial_failure"])
        failed += not row["ok"]
        datagrams = row["initial_datagrams"]
        retransmitted_or_failed += not row["ok"] or datagrams >= 4
        initial_counts[str(datagrams)] = initial_counts.get(str(datagrams), 0) + 1
        if classification:
            if not row["ok"] or datagrams >= 4:
                category = "failure_or_initial_retransmission"
            elif datagrams == 3:
                category = "one" if value < 100 else "two" if value < 200 else "tail"
            else:
                category = "unclassified"
            classes[category] += 1
        for key in byte_sums:
            if row[key] is None:
                byte_unavailable[key] += 1
            else:
                byte_sums[key] += row[key]
    variance = variance_sum / (n - 1) if n > 1 else 0.0
    return {"n": n, "mean_hct_ms": mean, "variance_hct_ms2": variance, "stderr_hct_ms": math.sqrt(variance / n), "initial_failure_fraction": initial_failures / n, "failure_or_initial_retransmission_fraction": retransmitted_or_failed / n, "connection_failed_fraction": failed / n, "initial_datagrams": initial_counts, "initial_5_fraction": initial_counts.get("5", 0) / n, "class_fractions": {key: count / n for key, count in classes.items()}, "mean_bytes": {key: None if byte_unavailable[key] else value / n for key, value in byte_sums.items()}, "unavailable_byte_counts": byte_unavailable}


def comparison(actual, target, tolerance):
    return {"actual": actual, "target": target, "difference": actual - target, "absolute_tolerance": tolerance, "pass": abs(actual - target) <= tolerance}


def validate_equivalence(protocol, progress):
    results = []
    spec = protocol["equivalence"]
    for context_spec in spec["contexts"]:
        context = WorldContext(**context_spec)
        for action_tuple in spec["actions"]:
            action = Action(*action_tuple)
            world = World(profile="policy_equivalent", seed=protocol["seed"])
            exact = world.exact_expectation(context, action)
            target = layout.evaluate(context.k, context.w + action.delta, action.lead + action.trailing, action.lead, context.p, context.rtt_ms, context.uplink_mbps, context.n_need)
            sampled = collect(world, context, action, protocol["samples_per_case"])
            tolerance = max(spec["exact_mean_abs_tolerance_ms"], spec["mean_tolerance_standard_errors"] * sampled["stderr_hct_ms"])
            row = {"context": dataclasses.asdict(context), "action": list(action_tuple), "exact": exact, "sampled": sampled, "target_J_ms": target["J"], "exact_check": comparison(exact["mean_hct_ms"], target["J"], spec["exact_mean_abs_tolerance_ms"]), "monte_carlo_check": comparison(sampled["mean_hct_ms"], target["J"], tolerance)}
            results.append(row)
            progress("equivalence", row)
    return results


def validate_calibration(protocol, progress):
    results = []
    limits = protocol["calibration"]["tolerances"]
    for case in protocol["calibration"]["cases"]:
        context = WorldContext(**case["context"])
        action = Action(*case["action"])
        world = World(profile="default", seed=protocol["seed"])
        sampled = collect(world, context, action, protocol["samples_per_case"], classification=True)
        observed = case["observed"]
        checks = {}
        if "mean_ms" in observed:
            checks["mean_ms"] = comparison(sampled["mean_hct_ms"], observed["mean_ms"], limits["mean_abs_ms"])
        for category, fraction in observed.get("class_fractions", {}).items():
            checks[category] = comparison(sampled["class_fractions"][category], fraction, limits["class_fraction_abs"])
        if "failure_fraction" in observed:
            checks["failure_fraction"] = comparison(sampled["failure_or_initial_retransmission_fraction"], observed["failure_fraction"], limits["failure_fraction_abs"])
        if "initial_5_fraction" in observed:
            checks["initial_5_fraction"] = comparison(sampled["initial_5_fraction"], observed["initial_5_fraction"], limits["initial_5_fraction_abs"])
        row = {"id": case["id"], "kind": case["kind"], "context": case["context"], "action": case["action"], "observed": observed, "sampled": sampled, "checks": checks, "within_predefined_tolerances": all(check["pass"] for check in checks.values())}
        results.append(row)
        progress("calibration", row)
    return results


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, default=ROOT / "g3/v33/world_validation_protocol.json")
    parser.add_argument("--mode", choices=("all", "equivalence", "calibration"), default="all")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists() or args.out.with_suffix(".progress.jsonl").exists():
        raise FileExistsError(args.out)
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    source_files = [Path(__file__), Path(__file__).with_name("worldsim.py"), Path(__file__).with_name("worldparams.json"), args.protocol]
    source_files += [ROOT / name for name in ("padfec3/layout.py", "padfec/policy.py", "padfec/quantum.py")]
    source_hashes = {str(path): file_hash(path) for path in source_files}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    began = time.monotonic()
    def progress(kind, row):
        with args.out.with_suffix(".progress.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps({"kind": kind, **row}, ensure_ascii=False, allow_nan=False) + "\n")
        print(json.dumps({"kind": kind, "id": row.get("id"), "action": row.get("action"), "p": row["context"]["p"], "mean_hct_ms": row["sampled"]["mean_hct_ms"], "elapsed_seconds": time.monotonic() - began}, ensure_ascii=False), flush=True)
    results = {"schema": "padfec.v33.world_validation_results/1", "source_sha256": source_hashes, "protocol": protocol, "mode": args.mode, "model_kinds": {"equivalence": "policy_equivalent_implementation_check", "calibration": "independent_world_simulation_vs_sealed_measurement"}}
    if args.mode in ("all", "equivalence"):
        results["equivalence"] = validate_equivalence(protocol, progress)
    if args.mode in ("all", "calibration"):
        results["calibration"] = validate_calibration(protocol, progress)
    if source_hashes != {str(path): file_hash(path) for path in source_files}:
        raise RuntimeError("validation source changed while running")
    results["elapsed_seconds"] = time.monotonic() - began
    with args.out.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(results, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    failures = sum(not row["exact_check"]["pass"] or not row["monte_carlo_check"]["pass"] for row in results.get("equivalence", []))
    print(json.dumps({"out": str(args.out), "equivalence_failures": failures, "calibration_limitations": sum(not row["within_predefined_tolerances"] for row in results.get("calibration", []))}))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
