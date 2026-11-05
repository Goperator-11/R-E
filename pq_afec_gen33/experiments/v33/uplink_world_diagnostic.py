import sys
sys.dont_write_bytecode = True
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import copy
import datetime as dt
import gzip
import hashlib
import io
import json
import math
import os
import time

from experiments.v33.bench_metrics import paired_summary
from experiments.v33.uplink_reference import ModelReference, RACE_SCALES, UPLINK_SCENARIOS
from experiments.v33.worldsim import Action, World, WorldContext
from padfec import policy, quantum
from padfec3 import decide3


SCENARIOS = ("B1", "B2", "B11", "B12_c6000", "B12_c12000")
UNKNOWN_ARMS = ("unknown_u_nominal", "unknown_u_race")
REFERENCES = ("known_u_model", "fixed_trailing4")
FAMILY_SIZE = 240


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def source_hashes():
    paths = [Path(__file__), Path(__file__).with_name("uplink_reference.py"),
             Path(__file__).with_name("worldsim.py"), Path(__file__).with_name("worldparams.json"),
             Path(__file__).with_name("bench_metrics.py"), ROOT / "g3/v33/bench_protocol.json",
             ROOT / "docs/O2_world_diagnostic_plan.md"]
    paths += sorted((ROOT / "padfec").glob("*.py")) + sorted((ROOT / "padfec3").glob("*.py"))
    return {str(p.relative_to(ROOT).as_posix()): sha(p) for p in paths}


def make_plan():
    protocol = read(ROOT / "g3/v33/bench_protocol.json")
    assert protocol["seeds"] == list(range(31, 51))
    assert protocol["world"]["profile"] == "default"
    for name, digest in protocol["world"]["source_sha256"].items():
        assert sha(Path(__file__).with_name(name)) == digest
    scenarios = [next(s for s in protocol["scenarios"] if s["id"] == name) for name in SCENARIOS]
    for scenario in scenarios:
        assert [p["length"] for p in scenario["phases"]] == [450, 450, 450]
        assert len({p["p"] for p in scenario["phases"]}) == 2
        assert not scenario.get("mixture") and scenario["world_params"] == {}
    return {"schema": "o2-hidden-u-world-diagnostic/1", "data_kind": "development_independent_event_world",
            "scenarios": scenarios, "seeds": protocol["seeds"], "true_u_mbps": UPLINK_SCENARIOS,
            "c_pkt": protocol["c_pkt"], "source_sha256": source_hashes(), "family_size": FAMILY_SIZE,
            "threshold_ms": 6.5, "family_confidence": 0.95, "paired_confidence": 0.95,
            "seed_runs": 600, "connection_contexts": 810000,
            "active_policy_changed": False, "global_oracle_computed": False,
            "estimator_connected": False, "full_w1_adoption_gate": False}


def validate_plan(plan):
    expected = make_plan()
    if json.dumps(expected, sort_keys=True) != json.dumps(plan, sort_keys=True):
        raise ValueError("plan or source identity changed")


def schedule(scenario, smoke=False):
    offset = 0
    for phase_number, phase in enumerate(scenario["phases"]):
        length = min(4, phase["length"]) if smoke else phase["length"]
        for phase_index in range(length):
            yield phase_number, phase_index, offset + phase_index
        offset += phase["length"]


def phase_design(scenario, phase, true_u, c_pkt, reference=None):
    reference = ModelReference() if reference is None else reference
    context = dict(scenario["context"])
    context.update({key: value for key, value in phase.items() if key != "length"})
    context["uplink_mbps"] = true_u
    k, w, p = context["k"], context["w"], context["p"]
    S = context["cert_bytes"] + quantum.s0_at(quantum.bin_index(k * w), policy.S0_BASE_MLKEM, c_pkt)
    common = ([(p, 1.0)], k, w, S, context["rtt_ms"], c_pkt)
    nominal = reference.decide(*common, uplink_mbps=None)
    joint = reference.decide(*common, uplink_mbps=None, race_scales=RACE_SCALES)
    known = reference.decide(*common, uplink_mbps=true_u)
    arms = {"unknown_u_nominal": nominal["candidate"]["action"],
            "unknown_u_race": joint["candidate"]["action"],
            "known_u_model": known["candidate"]["action"], "fixed_trailing4": (0, 0, 4)}
    candidates = {c["action"] for c in decide3.candidates3(k, w, S, c_pkt)}
    assert all(action in candidates for action in arms.values())
    return {"world_context": context, "selector_input": {"p": p, "k": k, "w": w, "S": S,
            "rtt_ms": context["rtt_ms"], "c_pkt": c_pkt, "unknown_u": None},
            "arms": arms, "nominal_model_regret_ms": nominal["worst_regret_ms"],
            "joint_model_regret_ms": joint["worst_regret_ms"]}


def job_id(scenario, rate, seed):
    return f"{scenario}_u{rate:g}_seed{seed}"


def execute_job(job):
    plan, scenario, rate, seed, out, smoke = job
    validate_plan(plan)
    destination = Path(out) / job_id(scenario["id"], rate, seed)
    destination.mkdir(parents=True, exist_ok=False)
    reference = ModelReference()
    designs = [phase_design(scenario, phase, rate, plan["c_pkt"], reference) for phase in scenario["phases"]]
    world = World(params=scenario["world_params"], profile="default", seed=seed)
    assert not world.params["channel"]["preserve_ge_across_connections"]
    groups = {}
    rows = samples = 0
    timer = time.monotonic()
    raw = destination / "rows.jsonl.gz"
    with raw.open("xb") as binary:
        with gzip.GzipFile(fileobj=binary, mode="wb", mtime=0, filename="") as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="\n") as stream:
                for phase_number, phase_index, connection in schedule(scenario, smoke):
                    design = designs[phase_number]
                    context = WorldContext(**design["world_context"])
                    outputs = {}
                    for action in sorted(set(tuple(x) for x in design["arms"].values())):
                        observation = world.sample(context, Action(*action), connection=connection, trace=phase_index == 0)
                        assert observation["model_kind"] == "independent_event_world"
                        key = ",".join(str(x) for x in action)
                        outputs[key] = {"hct_ms": observation["hct"], "ok": observation["ok"],
                                        "server_bytes": observation["server_counted_uplink_bytes"],
                                        "client_bytes": observation["client_total_uplink_bytes"],
                                        "pto_count": observation["pto_count"], "world_class": observation["world_class"],
                                        "stop_reason": observation["stop_reason"], "min_rtt_ms": observation["min_rtt_ms"]}
                        if phase_index == 0:
                            write_new(destination / f"phase{phase_number}_action{key.replace(',', '_')}_trace.json", observation)
                        samples += 1
                    row = {"index": rows, "connection": connection, "phase": phase_number,
                           "phase_index": phase_index, "p": context.p, "samples": outputs}
                    stream.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
                    group = groups.setdefault(str(context.p), {"n": 0, "arms": {name: {"hct_sum": 0.0,
                            "server_bytes_sum": 0, "client_bytes_sum": 0, "failures": 0}
                            for name in UNKNOWN_ARMS + REFERENCES}, "pairs": {}})
                    group["n"] += 1
                    for name, action in design["arms"].items():
                        values = outputs[",".join(str(x) for x in action)]
                        sums = group["arms"][name]
                        sums["hct_sum"] += values["hct_ms"]
                        sums["server_bytes_sum"] += values["server_bytes"]
                        sums["client_bytes_sum"] += values["client_bytes"]
                        sums["failures"] += not values["ok"]
                    for candidate in UNKNOWN_ARMS:
                        for comparator in REFERENCES:
                            key = candidate + ":" + comparator
                            values = group["pairs"].setdefault(key, {"difference_sum": 0.0, "same_action": True})
                            aa, bb = design["arms"][candidate], design["arms"][comparator]
                            values["same_action"] &= tuple(aa) == tuple(bb)
                            values["difference_sum"] += outputs[",".join(map(str, aa))]["hct_ms"] - outputs[",".join(map(str, bb))]["hct_ms"]
                    rows += 1
    validate_plan(plan)
    result = {"job_id": destination.name, "scenario": scenario["id"], "true_u_mbps": rate, "seed": seed,
              "smoke": smoke, "n": rows, "world_samples": samples, "designs": designs, "groups": groups,
              "rows_path": str(raw), "rows_sha256": sha(raw), "seconds": time.monotonic() - timer,
              "source_sha256": source_hashes(), "params_sha256": world.params_sha256}
    write_new(destination / "result.json", result)
    return result


def paired_inference(seed_differences, same_action, family_size=FAMILY_SIZE):
    nominal = paired_summary(seed_differences)
    adjusted = paired_summary(seed_differences, confidence=1 - 0.05 / family_size)
    unresolved = not same_action and (nominal["sd"] is None or nominal["sd"] <= 1e-12)
    if same_action:
        if any(x != 0 for x in seed_differences):
            raise ValueError("identical actions produced different outcomes")
    elif unresolved:
        for report in (nominal, adjusted):
            report.update(lower=None, upper=None, half_width=None, interval_available=False)
    lower = adjusted["lower"]
    return {"paired95": nominal, "family95": adjusted, "structural_zero": same_action,
            "zero_variance_unresolved": unresolved,
            "counterexample_6_5": lower is not None and lower > 6.5,
            "known_action_gap_above_0_5": lower is not None and lower > 0.5}


def summarize(results, plan, smoke):
    groups = {}
    for result in results:
        for p, group in result["groups"].items():
            for pair, values in group["pairs"].items():
                key = (result["scenario"], result["true_u_mbps"], float(p), pair)
                target = groups.setdefault(key, [])
                target.append((result["seed"], values["difference_sum"] / group["n"], values["same_action"]))
    rows = []
    for key, group in sorted(groups.items()):
        group.sort()
        if not smoke:
            assert [x[0] for x in group] == plan["seeds"]
        inference = paired_inference([x[1] for x in group], all(x[2] for x in group))
        rows.append(dict(scenario=key[0], true_u_mbps=key[1], p=key[2], pair=key[3],
                         seed_differences=[dict(seed=x[0],difference_ms=x[1]) for x in group], **inference))
    assert len(rows) == FAMILY_SIZE
    return {"data_kind": "development_independent_event_world", "smoke": smoke,
            "runs": len(results), "connection_contexts": sum(x["n"] for x in results),
            "world_samples": sum(x["world_samples"] for x in results), "comparisons": rows,
            "counterexamples": sum(x["counterexample_6_5"] for x in rows),
            "global_oracle_computed": False, "adoption_pass": False}


def collect(plan, output, smoke=False, workers=2):
    validate_plan(plan)
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / "plan.json", plan)
    seeds = plan["seeds"][:1] if smoke else plan["seeds"]
    jobs = [(plan, s, u, seed, str(output / "jobs"), smoke)
            for s in plan["scenarios"] for u in plan["true_u_mbps"] for seed in seeds]
    results = []
    timer = time.monotonic()
    def status(state):
        value = dict(status=state, pid=os.getpid(), completed=len(results), total=len(jobs),
                     seconds=time.monotonic()-timer, smoke=smoke,
                     updated_kst=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat())
        (output/"status.json").write_text(json.dumps(value,indent=2)+"\n",encoding="utf-8",newline="\n")
        return value
    status("running")
    try:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(execute_job, job) for job in jobs]
            for future in as_completed(futures):
                results.append(future.result())
                status("running")
        validate_plan(plan)
        result = summarize(results, plan, smoke)
        result["source_sha256"] = source_hashes()
        result["elapsed_seconds"] = time.monotonic()-timer
        result["input_results"] = [{"job_id": x["job_id"],
            "sha256": sha(output/"jobs"/x["job_id"]/"result.json")} for x in sorted(results,key=lambda x:x["job_id"])]
        write_new(output/"summary.json", result)
        status("complete")
        (output/"DONE").write_text(sha(output/"summary.json")+"\n",encoding="ascii")
    except BaseException:
        status("failed")
        raise
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.prepare:
        write_new(args.plan, make_plan())
        print(json.dumps({"plan":str(args.plan),"sha256":sha(args.plan)}))
        return
    plan = read(args.plan)
    validate_plan(plan)
    if args.dry_run:
        print(json.dumps({"status":"PASS","source_files":len(plan["source_sha256"]),
                          "runs":plan["seed_runs"],"connection_contexts":plan["connection_contexts"]}))
        return
    if args.out is None:
        parser.error("--out is required")
    result = collect(plan,args.out,smoke=args.smoke)
    print(json.dumps({k:result[k] for k in ("runs","connection_contexts","world_samples","counterexamples","elapsed_seconds")}))


if __name__ == "__main__":
    main()
