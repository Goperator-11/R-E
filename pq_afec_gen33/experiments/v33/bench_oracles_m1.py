import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import argparse
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.v33 import bench, oracle_m1 as oracle


def emit(value):
    print(json.dumps(value, ensure_ascii=False, allow_nan=False), flush=True)


RESULT_SOURCES = frozenset(("oracle_m1.py", "worldsim_m1.py", "worldparams_m1.json", "world_receiver_m1.py"))
MANIFEST_SOURCES = RESULT_SOURCES | {"bench.py", "bench_oracles_m1.py"}


def _same(actual, expected, name):
    if bench.canonical(actual) != bench.canonical(expected):
        raise ValueError(f"oracle {name} differs")


def _required(value, name):
    if name not in value:
        raise ValueError(f"oracle {name} is missing")
    return value[name]


def _source_contract(value, names):
    if not isinstance(value, dict) or set(value) != set(names):
        raise ValueError("oracle source hash keys differ")
    for name in names:
        if value[name] != bench.file_hash(Path(__file__).with_name(name)):
            raise ValueError(f"oracle source differs: {name}")


def _job_contract(job, mode):
    keys = {"context_id", "job_id"} | ({"action", "reference_action"} if mode == "actions" else set())
    if not isinstance(job, dict) or set(job) != keys:
        raise ValueError("oracle job fields differ")
    cid = job["context_id"]
    if not isinstance(cid, str) or not cid:
        raise ValueError("oracle context_id is invalid")
    expected = cid
    if mode == "actions":
        action = oracle._action(job["action"])
        oracle._action(job["reference_action"])
        expected += "_" + "_".join(map(str, action))
    _same(job["job_id"], expected, "job_id")


def validate_oracle_manifest(manifest, *, protocol_hash, mode):
    if mode not in ("build", "actions"):
        raise ValueError("oracle manifest mode is invalid")
    for key, value in (("schema", "padfec.v33.oracle_jobs/1"), ("mode", mode), ("protocol_sha256", protocol_hash)):
        _same(_required(manifest, key), value, key)
    _source_contract(_required(manifest, "source_sha256"), MANIFEST_SOURCES)
    jobs = _required(manifest, "jobs")
    if not isinstance(jobs, list) or not jobs:
        raise ValueError("oracle jobs must be nonempty")
    for job in jobs:
        _job_contract(job, mode)
    if len({job["job_id"] for job in jobs}) != len(jobs):
        raise ValueError("duplicate oracle job")
    _same(_required(manifest, "evaluation_family_size"), len(jobs) if mode == "actions" else None, "evaluation_family_size")
    digests = _required(manifest, "oracle_digests")
    if not isinstance(digests, dict) or mode == "build" and digests:
        raise ValueError("oracle reference digests differ")
    if mode == "actions" and any(job["context_id"] not in digests for job in jobs):
        raise ValueError("oracle reference digest is missing")


def _expected_result_contract(protocol, context_spec, mode, evaluation_family_size):
    value = {**protocol["oracle"], "mixture":context_spec.get("mixture", [])}
    if mode == "actions":
        if type(evaluation_family_size) is not int or evaluation_family_size < 1:
            raise ValueError("oracle evaluation_family_size must be positive")
        value["evaluation_family_size"] = evaluation_family_size
    elif mode != "build" or evaluation_family_size is not None:
        raise ValueError("oracle result mode or family differs")
    spec = oracle._spec(value)
    params = oracle.load_params(context_spec["world_params"])
    mixture = oracle._Mixture(context_spec["context"], spec)
    universe = oracle.action_universe(context_spec["context"], params, spec)
    expected = {"context":context_spec["context"], "mixture":mixture.description,
                "world_params_sha256":oracle.World(params).params_sha256,
                "spec":oracle._semantic_spec(spec), "universe_count":len(universe),
                "universe_sha256":oracle._digest(universe), "max_parity":spec["max_parity"]}
    return expected, spec, params, mixture, universe


def validate_oracle_result(result, *, protocol, context_spec, job, mode, evaluation_family_size=None):
    _job_contract(job, mode)
    expected, spec, params, mixture, universe = _expected_result_contract(protocol, context_spec, mode, evaluation_family_size)
    for key, value in {"schema":oracle.SCHEMA, "status":"complete", "context_id":job["context_id"], "job_id":job["job_id"], **expected}.items():
        _same(_required(result, key), value, key)
    _source_contract(_required(result, "source_hashes"), RESULT_SOURCES)
    method = _required(result, "method")
    structural_method = "structural_zero_loss_certificate" if mode == "build" else "structural_zero_loss_pair"
    mc_method = "paired_stage_screening_then_independent_validation" if mode == "build" else "independent_paired_validation"
    if method not in (structural_method, mc_method):
        raise ValueError("oracle method differs")
    structural = method == structural_method
    _same(_required(result, "approximate"), not structural, "approximate")
    _same(_required(result, "validation_samples"), 0 if structural else spec["validation_samples"], "validation_samples")
    if mode == "build":
        _same(_required(result, "model_kind"), "independent_event_world", "model_kind")
        chosen = oracle._action(_required(result, "chosen_action"))
        if chosen not in universe:
            raise ValueError("oracle chosen action is outside the universe")
    else:
        for key in ("action", "reference_action"):
            _same(_required(result, key), job[key], key)
            if oracle._action(result[key]) not in universe:
                raise ValueError("oracle evaluated action is outside the universe")
        _same(_required(result, "validation_seed"), spec["validation_seed"], "validation_seed")
        _same(_required(result, "n"), 0 if structural else spec["validation_samples"], "n")
        _same(_required(result, "evaluation_family_size"), evaluation_family_size, "evaluation_family_size")
    if structural:
        certificate = oracle._certificate(mixture, params, oracle._source_hashes(), spec)
        if certificate is None:
            raise ValueError("oracle structural certificate is not applicable")
        _same(_required(result, "certificate"), certificate, "certificate")
        _same(_required(result, "uncertainty_resolved"), True, "uncertainty_resolved")
        if mode == "build":
            _same(result["chosen_action"], certificate["action"], "chosen_action")
            for key, value in (("confidence", None), ("stage_results", []), ("oracle_gap_upper_ms", 0.0), ("selection_gap_upper_ms", 0.0)):
                _same(_required(result, key), value, key)
        return
    _same(_required(result, "confidence"), spec["confidence"], "confidence")
    if mode == "actions":
        _same(_required(result, "evaluation_seed_must_not_have_selected_either_action"), True, "evaluation seed independence marker")
        return
    _same(_required(result, "validation_seed"), spec["validation_seed"], "validation_seed")
    _same(_required(result, "validation_changed_choice"), False, "validation_changed_choice")
    _same(_required(result, "selection_stage_samples_are_fresh_blocks"), True, "selection stage blocks")
    history = _required(result, "history")
    _same(_required(result, "stage_results"), history, "stage_results")
    if not isinstance(history, list) or len(history) != len(spec["stage_sizes"]):
        raise ValueError("oracle selection stage count differs")
    active = set(universe)
    reference = min(universe, key=lambda action:oracle._wire_key(action, mixture, params))
    evaluations = 0
    for stage, (entry, n) in enumerate(zip(history, spec["stage_sizes"])):
        for key, value in (("stage_index", stage), ("new_independent_connections", n), ("seed", oracle._derive_seed(spec["selection_seed"], f"selection_stage:{stage}")), ("reference_action", reference), ("before", len(active))):
            _same(_required(entry, key), value, key)
        eliminated = [oracle._action(_required(item, "action")) for item in _required(entry, "eliminated")]
        if len(set(eliminated)) != len(eliminated) or not set(eliminated) <= active or eliminated and n < spec["min_elimination_samples"]:
            raise ValueError("oracle elimination history differs")
        evaluations += len(active) * n
        active -= set(eliminated)
        reference = oracle._action(_required(entry, "empirical_choice"))
        if reference not in active:
            raise ValueError("oracle empirical choice did not survive")
        _same(_required(entry, "after"), len(active), "surviving candidate count")
    _same(result["chosen_action"], reference, "chosen_action")
    validations = _required(result, "validation")
    if not isinstance(validations, list):
        raise ValueError("oracle validation must be a list")
    validated = [oracle._action(_required(item, "action")) for item in validations]
    if len(set(validated)) != len(validated) or set(validated) != active:
        raise ValueError("oracle validation actions differ from survivors")
    for item in validations:
        _same(_required(item, "n"), spec["validation_samples"], "validation row n")
    _same(_required(result, "validation_candidate_count"), len(active), "validation_candidate_count")
    _same(_required(result, "total_world_evaluations"), evaluations + len(active) * spec["validation_samples"], "total_world_evaluations")


def _complete_action_metadata(result, protocol, context_spec, family):
    expected, spec, _, _, _ = _expected_result_contract(protocol, context_spec, "actions", family)
    metadata = {key:expected[key] for key in ("spec", "universe_count", "universe_sha256", "max_parity")}
    metadata["validation_samples"] = 0 if result["method"] == "structural_zero_loss_pair" else spec["validation_samples"]
    metadata["evaluation_family_size"] = family
    for key, value in metadata.items():
        if key in result:
            _same(result[key], value, key)
        else:
            result[key] = value


def raw_summaries(folders, protocol_hash):
    results = []
    identities = set()
    for folder in folders:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        if manifest["protocol_sha256"] != protocol_hash or manifest["mode"] != "full":
            raise ValueError("raw inputs must use the full frozen protocol")
        expected = {(g,manifest["variant"],s,seed) for g in manifest["generations"] for s in manifest["scenarios"] for seed in manifest["seeds"]}
        found = set()
        scenarios = {item["id"]:item for item in manifest["protocol"]["scenarios"]}
        for path in sorted(folder.glob("*/*/*/seed*.json")):
            result = json.loads(path.read_text(encoding="utf-8"))
            key = (result["generation"], result["variant"], result["scenario"], result["seed"])
            if key in identities:
                raise ValueError(f"duplicate raw run {key}")
            if key not in expected or path.stem != f'seed{result["seed"]:05d}':
                raise ValueError("raw run identity or filename differs")
            if result["mode"] != "full" or result["protocol_sha256"] != protocol_hash:
                raise ValueError("raw seed has mismatched protocol")
            identities.add(key)
            found.add(key)
            bench.validate_resume(result,generation=result["generation"],variant=result["variant"],scenario=scenarios[result["scenario"]],seed=result["seed"],planned=manifest,fingerprint=manifest["policy_source_fingerprints"][result["generation"]])
            results.append(result)
        if found != expected:
            raise ValueError(f"raw benchmark is incomplete: {len(found)}/{len(expected)}")
    return results


def references(folders, protocol_hash, protocol):
    results = {}
    contexts = bench.all_contexts(protocol)
    for folder in folders:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        validate_oracle_manifest(manifest, protocol_hash=protocol_hash, mode="build")
        jobs = {job["job_id"]:job for job in manifest["jobs"]}
        for path in sorted(folder.glob("results/*.json")):
            item = json.loads(path.read_text(encoding="utf-8"))
            if item.get("protocol_sha256") != protocol_hash or path.stem not in jobs:
                raise ValueError("mismatched oracle protocol or filename")
            cid = item["context_id"]
            if cid not in contexts:
                raise ValueError("unknown oracle context")
            validate_oracle_result(item, protocol=protocol, context_spec=contexts[cid], job=jobs[path.stem], mode="build")
            if cid in results and bench.digest(results[cid]) != bench.digest(item):
                raise ValueError("duplicate oracle context with different results")
            results[cid] = item
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build","actions"))
    parser.add_argument("--protocol", type=Path, default=ROOT / "g3/v33/bench_protocol.json")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--contexts", nargs="+")
    parser.add_argument("--raw-dirs", type=Path, nargs="+", default=[])
    parser.add_argument("--oracle-dirs", type=Path, nargs="+", default=[])
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--time-budget-seconds", type=float, default=300.0)
    args = parser.parse_args()
    protocol = bench.load_protocol(args.protocol)
    protocol_hash = bench.file_hash(args.protocol)
    contexts = bench.all_contexts(protocol)
    selected = args.contexts or list(contexts)
    if len(set(selected)) != len(selected) or not set(selected) <= set(contexts):
        raise ValueError("invalid context selection")
    sources = {name:bench.file_hash(Path(__file__).with_name(name)) for name in sorted(MANIFEST_SOURCES)}
    raw = raw_summaries(args.raw_dirs, protocol_hash) if args.mode == "actions" else []
    refs = references(args.oracle_dirs, protocol_hash, protocol) if args.mode == "actions" else {}
    jobs = []
    if args.mode == "build":
        for cid in sorted(selected, key=lambda value:(contexts[value]["context"]["p"] != 0, value)):
            jobs.append({"context_id":cid})
    else:
        keys = {(row["context_id"],tuple(row["action"])) for result in raw for row in result["action_counts"] if row["context_id"] in selected}
        if not keys:
            raise ValueError("no completed raw actions found")
        for cid, action in sorted(keys):
            if cid not in refs:
                raise ValueError(f"oracle is not ready: {cid}")
            jobs.append({"context_id":cid,"action":list(action),"reference_action":refs[cid]["chosen_action"]})
    for job in jobs:
        job["job_id"] = job["context_id"] if args.mode == "build" else job["context_id"] + "_" + "_".join(map(str,job["action"]))
    manifest = {"schema":"padfec.v33.oracle_jobs/1","mode":args.mode,"protocol_sha256":protocol_hash,"source_sha256":sources,"jobs":jobs,"evaluation_family_size":len(jobs) if args.mode == "actions" else None,"raw_run_identities":[[r["generation"],r["variant"],r["scenario"],r["seed"]] for r in raw],"oracle_digests":{key:bench.digest(value) for key,value in refs.items()}}
    validate_oracle_manifest(manifest, protocol_hash=protocol_hash, mode=args.mode)
    args.out.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out / "manifest.json"
    if manifest_path.exists():
        if not args.resume or json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
            raise ValueError("job manifest changed or --resume is missing")
    else:
        bench.write_new(manifest_path, manifest)
    (args.out / "results").mkdir(exist_ok=True)
    (args.out / "attempts").mkdir(exist_ok=True)
    while True:
        remaining = 0
        for job in jobs:
            destination = args.out / "results" / (job["job_id"] + ".json")
            if destination.exists():
                existing = json.loads(destination.read_text(encoding="utf-8"))
                if existing.get("protocol_sha256") != protocol_hash:
                    raise ValueError("existing oracle protocol differs")
                validate_oracle_result(existing, protocol=protocol, context_spec=contexts[job["context_id"]], job=job, mode=args.mode, evaluation_family_size=len(jobs) if args.mode == "actions" else None)
                continue
            current_sources = {name:bench.file_hash(Path(__file__).with_name(name)) for name in sources}
            if current_sources != sources or bench.file_hash(args.protocol) != protocol_hash:
                raise RuntimeError("oracle sources changed during job")
            spec = {**protocol["oracle"],"mixture":contexts[job["context_id"]]["mixture"],"checkpoint_path":str(args.out / "checkpoints" / (job["job_id"] + ".json")),"time_budget_seconds":args.time_budget_seconds}
            context = contexts[job["context_id"]]
            def progress(value):
                emit({"job_id":job["job_id"],**value})
            if args.mode == "build":
                result = oracle.build_oracle(context["context"],context["world_params"],spec,progress)
            else:
                spec["evaluation_family_size"] = len(jobs)
                result = oracle.evaluate_action(context["context"],job["action"],job["reference_action"],context["world_params"],spec,progress)
            if {name:bench.file_hash(Path(__file__).with_name(name)) for name in sources} != sources or bench.file_hash(args.protocol) != protocol_hash:
                raise RuntimeError("oracle sources changed during evaluation")
            result.update(context_id=job["context_id"],protocol_sha256=protocol_hash,job_id=job["job_id"])
            if result["status"] == "complete":
                if args.mode == "actions":
                    _complete_action_metadata(result, protocol, context, len(jobs))
                validate_oracle_result(result, protocol=protocol, context_spec=context, job=job, mode=args.mode, evaluation_family_size=len(jobs) if args.mode == "actions" else None)
                bench.write_new(destination,result)
            else:
                remaining += 1
                bench.write_new(args.out / "attempts" / f'{job["job_id"]}.{time.time_ns()}.json',result)
            emit({"job_id":job["job_id"],"status":result["status"],"chosen_action":result.get("chosen_action"),"selection_gap_upper_ms":result.get("selection_gap_upper_ms"),"n":result.get("n")})
        emit({"mode":args.mode,"remaining":remaining,"out":str(args.out)})
        if not args.loop or not remaining:
            break


if __name__ == "__main__":
    main()
