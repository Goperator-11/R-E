import sys
sys.dont_write_bytecode = True
import argparse
from dataclasses import asdict, dataclass
import datetime as dt
import hashlib
import itertools
import json
import math
from pathlib import Path
import random


@dataclass(frozen=True)
class LossCase:
    name: str
    k: int
    lead: int
    trailing: int
    p: float
    burst_length: float
    lead_mode: str = "credit_only"
    loss_model: str = "ge"


def default_cases():
    cases = []
    for p in (0.02, 0.15, 0.30):
        for lead, trailing, mode in ((0, 1, "credit_only"), (0, 4, "credit_only"), (3, 1, "credit_only"), (3, 1, "buffered")):
            cases.append(LossCase(f"ge_p{p:g}_L3_L{lead}T{trailing}_{mode}", 2, lead, trailing, p, 3.0, mode))
    for p in (0.02, 0.15, 0.30):
        cases.append(LossCase(f"iid_boundary_p{p:g}", 2, 0, 4, p, 1.0 / (1.0 - p)))
    for p in (0.0, 1.0):
        cases.append(LossCase(f"deterministic_p{p:g}", 2, 0, 4, p, 3.0))
    return cases


def reference_parameters(p, burst_length):
    if isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1:
        raise ValueError("p must be finite and in [0,1]")
    if isinstance(burst_length, bool) or not isinstance(burst_length, (int, float)) or not math.isfinite(burst_length) or burst_length < 1:
        raise ValueError("burst_length must be finite and >=1")
    if p in (0.0, 1.0):
        return 0.0, 0.0
    recovery = 1.0 / burst_length
    entry = p / ((1.0 - p) * burst_length)
    if entry > 1.0 + 1e-15:
        raise ValueError("stationary p and burst_length imply a transition probability above 1")
    return min(entry, 1.0), recovery


def eligible_symbols(case):
    if any(isinstance(x, bool) or not isinstance(x, int) for x in (case.k, case.lead, case.trailing)):
        raise ValueError("k, lead and trailing must be integers")
    if case.k < 1 or case.lead < 0 or case.trailing < 0:
        raise ValueError("invalid block dimensions")
    if case.lead_mode not in ("credit_only", "buffered"):
        raise ValueError("invalid lead mode")
    if case.loss_model not in ("iid", "ge"):
        raise ValueError("invalid loss model")
    reference_parameters(case.p, case.burst_length)
    return (case.lead_mode == "buffered",) * case.lead + (True,) * (case.k + case.trailing)


def reference_enumeration(case):
    eligible = eligible_symbols(case)
    entry, recovery = reference_parameters(case.p, case.burst_length)
    failed = []
    masses = []
    for states in itertools.product((0, 1), repeat=len(eligible)):
        if case.loss_model == "iid":
            probability = math.prod(case.p if state else 1.0 - case.p for state in states)
        elif case.p in (0.0, 1.0):
            probability = float(all(state == int(case.p) for state in states))
        else:
            probability = case.p if states[0] else 1.0 - case.p
            for previous, current in zip(states, states[1:]):
                if previous:
                    probability *= 1.0 - recovery if current else recovery
                else:
                    probability *= entry if current else 1.0 - entry
        masses.append(probability)
        if sum(allow and state == 0 for allow, state in zip(eligible, states)) < case.k:
            failed.append(probability)
    return {"p_fail": math.fsum(failed), "probability_sum": math.fsum(masses)}


def reference_forward(case):
    eligible = eligible_symbols(case)
    entry, recovery = reference_parameters(case.p, case.burst_length)
    if case.loss_model == "iid":
        transition = ((1.0 - case.p, case.p), (1.0 - case.p, case.p))
    else:
        transition = ((1.0 - entry, entry), (recovery, 1.0 - recovery))
    current = {(0, 0): 1.0 - case.p, (1, 0): case.p}
    for index, allow in enumerate(eligible):
        emitted = {}
        for (state, count), mass in current.items():
            received = min(case.k, count + int(allow and state == 0))
            emitted[(state, received)] = emitted.get((state, received), 0.0) + mass
        if index == len(eligible) - 1:
            current = emitted
            break
        current = {}
        for (state, count), mass in emitted.items():
            for successor in (0, 1):
                key = successor, count
                current[key] = current.get(key, 0.0) + mass * transition[state][successor]
    return {"p_fail": math.fsum(mass for (state, count), mass in current.items() if count < case.k), "probability_sum": math.fsum(current.values())}


def run_length_sample(case, rng):
    eligible = eligible_symbols(case)
    if case.p in (0.0, 1.0):
        return case.p == 1.0
    if case.loss_model == "iid":
        return sum(allow and rng.random() >= case.p for allow in eligible) < case.k
    entry, recovery = reference_parameters(case.p, case.burst_length)
    bad = rng.random() < case.p
    index = received = 0
    while index < len(eligible):
        leave = recovery if bad else entry
        if leave == 0.0:
            length = len(eligible) - index
        elif leave == 1.0:
            length = 1
        else:
            length = 1 + int(math.log1p(-rng.random()) / math.log1p(-leave))
        stop = min(index + length, len(eligible))
        if not bad:
            received += sum(eligible[index:stop])
        index = stop
        bad = not bad
    return received < case.k


def world_enumeration(case, world):
    eligible = eligible_symbols(case)
    mass = failed = 0.0
    for pattern in itertools.product((False, True), repeat=len(eligible)):
        probability = world.pattern_probability(pattern, case.p, loss_model=case.loss_model, burst_length=case.burst_length)
        result = world.first_flight_outcome(pattern, case.k, case.lead, case.trailing, lead_mode=case.lead_mode)
        mass += probability
        if not result["success"]:
            failed += probability
    return {"p_fail": failed, "probability_sum": mass}


def sample_comparison(failures, samples, truth, sigma):
    estimate = failures / samples
    standard_error = math.sqrt(truth * (1.0 - truth) / samples)
    tolerance = sigma * standard_error + 1e-12
    return {"failures": failures, "samples": samples, "estimate": estimate, "reference": truth, "difference": estimate - truth, "standard_error": standard_error, "tolerance": tolerance, "pass": abs(estimate - truth) <= tolerance}


def validate(cases, samples, seeds, sigma, exact_tolerance, world):
    if samples < 1 or sigma <= 0 or exact_tolerance < 0:
        raise ValueError("invalid validation settings")
    if len(cases) != len(seeds):
        raise ValueError("each case needs a fixed seed")
    results = []
    for index, case in enumerate(cases):
        seed = seeds[index]
        enumeration = reference_enumeration(case)
        forward = reference_forward(case)
        engine = world_enumeration(case, world)
        truth = enumeration["p_fail"]
        exact_pass = all(abs(value["p_fail"] - truth) <= exact_tolerance and abs(value["probability_sum"] - 1.0) <= exact_tolerance for value in (enumeration, forward, engine))
        rng = random.Random(seed)
        independent_failures = sum(run_length_sample(case, rng) for _ in range(samples))
        world_failures = 0
        for connection in range(samples):
            pattern = world.sample_loss_pattern(case.k + case.lead + case.trailing, case.p, loss_model=case.loss_model, burst_length=case.burst_length, seed=seed, connection=connection)
            outcome = world.first_flight_outcome(pattern, case.k, case.lead, case.trailing, lead_mode=case.lead_mode)
            world_failures += not outcome["success"]
        independent_mc = sample_comparison(independent_failures, samples, truth, sigma)
        world_mc = sample_comparison(world_failures, samples, truth, sigma)
        result = {"case": asdict(case), "seed": seed, "enumeration": enumeration, "forward_dp": forward, "world_enumeration": engine, "exact_pass": exact_pass, "independent_run_length_mc": independent_mc, "world_mc": world_mc, "pass": exact_pass and independent_mc["pass"] and world_mc["pass"]}
        results.append(result)
        print(json.dumps({"case": case.name, "pass": result["pass"], "exact": truth, "independent_mc": independent_mc["estimate"], "world_mc": world_mc["estimate"]}), flush=True)
    return results


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    protocol_bytes = args.protocol.read_bytes()
    protocol = json.loads(protocol_bytes)
    spec = protocol["loss"]
    cases = [LossCase(f"{index:02d}_{row['kind']}_p{row['p']:g}_L{row['lead']}T{row['trailing']}_{row['lead_mode']}", row["k"], row["lead"], row["trailing"], row["p"], row["L"], row["lead_mode"], "ge") for index, row in enumerate(spec["cases"])]
    seeds = [row["seed"] for row in spec["cases"]]
    output = args.out.resolve()
    allowed = (Path(__file__).resolve().parents[2], Path(r"C:\dev\codex_handoff\v33").resolve() if sys.platform == "win32" else Path("/mnt/c/dev/codex_handoff/v33"))
    if output.suffix != ".json" or not any(output.is_relative_to(root) for root in allowed):
        raise ValueError("output must be a JSON file within gen33 or the v33 handoff")
    if output.exists():
        raise FileExistsError(output)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import worldsim
    source_paths = (Path(__file__).resolve(), Path(worldsim.__file__).resolve())
    source_before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths}
    results = validate(cases, protocol["samples_per_case"], seeds, spec["monte_carlo_sigma"], spec["exact_tolerance"], worldsim)
    source_after = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths}
    changed_sources = [path for path in source_before if source_before[path] != source_after[path]]
    protocol_unchanged = hashlib.sha256(args.protocol.read_bytes()).digest() == hashlib.sha256(protocol_bytes).digest()
    stable = not changed_sources and protocol_unchanged
    report = {"schema": "padfec.v33.loss_validation/1", "generated_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec="seconds"), "data_kind": "independent_markov_enumeration_and_simulation", "literature_formula_verified": False, "protocol_path": str(args.protocol.resolve()), "protocol_sha256": hashlib.sha256(protocol_bytes).hexdigest(), "source_sha256": source_before, "source_sha256_after": source_after, "changed_sources": changed_sources, "protocol_unchanged": protocol_unchanged, "inputs_stable": stable, "results": results, "pass": stable and all(result["pass"] for result in results)}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
