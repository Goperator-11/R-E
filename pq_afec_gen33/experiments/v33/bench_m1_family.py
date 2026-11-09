import sys
sys.dont_write_bytecode = True
import argparse
import collections
from concurrent.futures import ProcessPoolExecutor, as_completed
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.v33 import bench, bench_m1 as collector, bench_learning as learning
from experiments.v33 import bench_learning_report as legacy, bench_action_pool_m1 as pool, bench_oracles
from experiments.v33 import m1_pool_validation as validation

PATH = Path(__file__).resolve()
IMPORTED_SHA = bench.file_hash(PATH)
SCHEMA = "padfec.v33.m1_action_family/1"
PLAN_SHA = "5be8bd6cb35a9d309c7c762a0ee0a2ff62e068c0f689875b4e0942fe2decf591"
IMPORT_PATH = ROOT / "g3/v33/bench_overlays/L1_v1_import.json"
IMPORT_SHA = "3450902fdfb3eb563b09f64240b4f29ddd27b8065cc9e8fd3260c8e00269645a"
equal, read = collector.equal, collector.read


def hashes(paths):
    return {str(Path(p).resolve(strict=True)): bench.file_hash(p) for p in paths}


def combined_protocol(plan):
    protocol = copy.deepcopy(plan["protocols"]["off"])
    protocol["scenarios"] = []
    for profile, source in plan["protocols"].items():
        for scenario in source["scenarios"]:
            item = copy.deepcopy(scenario)
            item["id"] = profile + "_" + item["id"]
            protocol["scenarios"].append(item)
    return protocol


def validate_shard(plan_path, job):
    plan = collector.load_plan(plan_path)
    profile, role, mode, sid = job
    folder = Path(plan["raw_root"]) / "_".join(job)
    manifest_path, finish_path = folder / "manifest.json", folder / "finished.json"
    manifest, finished = read(manifest_path), read(finish_path)
    protocol, policy = plan["protocols"][profile], plan["policies"][role]
    scenario = next(s for s in protocol["scenarios"] if s["id"] == sid)
    seeds = protocol["seeds"]
    for key, value in {"schema": collector.SCHEMA, "plan_sha256": PLAN_SHA, "job": list(job),
                       "mode": "full", "seeds": seeds, "source_sha256": collector.sources(),
                       "policy": policy, "protocol_sha256": bench.digest(protocol)}.items():
        equal(manifest[key], value, "shard manifest " + key)
    for key, value in {"status": "complete", "job": list(job), "seeds": seeds,
                       "manifest_sha256": bench.file_hash(manifest_path)}.items():
        equal(finished[key], value, "shard completion " + key)
    paths = [folder / f"seed{s:05d}.json" for s in seeds]
    equal(sorted(p.name for p in folder.glob("seed*.json")), sorted(p.name for p in paths), "seed file inventory")
    equal(finished["results_sha256"], hashes(paths), "seed completion hashes")
    inputs = hashes([manifest_path, finish_path, *paths])
    compact = []
    for seed, path in zip(seeds, paths):
        run = read(path)
        fixed_path = Path(plan["baseline_root"]) / profile / sid / f"seed{seed:05d}.json"
        fixed = read(fixed_path)
        for key, value in {"schema": collector.SCHEMA, "status": "complete", "profile": profile,
                           "role": role, "scenario": sid, "seed": seed, "mode": "full",
                           "observation_mode": mode, "plan_sha256": PLAN_SHA,
                           "source_sha256": collector.sources(), "protocol_sha256": bench.digest(protocol),
                           "baseline_path": str(fixed_path), "baseline_sha256": bench.file_hash(fixed_path),
                           "policy_fingerprint": policy["fingerprint"]}.items():
            equal(run[key], value, "raw " + key)
        equal([fixed[k] for k in ("profile", "scenario", "seed", "protocol_sha256")],
              [profile, sid, seed, bench.digest(protocol)], "fixed identity")
        learning.validate_initial(run["policy_initial"], policy)
        learning.validate_audit(run["policy_audit"], policy["fingerprint"])
        rows = collector.validate_rows(run, scenario, protocol, mode, fixed, False)
        diagnostics = legacy.observation_diagnostics(rows, mode)
        compact.append({k: run[k] for k in ("profile", "role", "scenario", "seed", "n", "summary",
                                          "action_counts", "observation_mode", "trace_path", "trace_sha256")}
                       | {"raw_path": str(path), "observation_diagnostics": diagnostics})
        inputs.update(hashes([fixed_path, fixed["trace_path"], run["trace_path"], folder / f"seed{seed:05d}.stderr.txt"]))
    legacy.check_files(inputs)
    return {"job": list(job), "runs": compact, "inputs_sha256": inputs}


def collection_inputs(plan_path, plan):
    equal(bench.file_hash(plan_path), PLAN_SHA, "frozen plan")
    folder = Path(plan["raw_root"])
    started, finished = read(folder / "started.json"), read(folder / "finished.json")
    expected = {tuple(job) for job in collector.jobs(plan)}
    equal(started["plan_sha256"], PLAN_SHA, "collection start plan")
    equal(finished["plan_sha256"], PLAN_SHA, "collection completion plan")
    equal(finished["status"], "complete", "collection completion")
    equal(started["jobs"], len(expected), "starting job count")
    equal(finished["jobs"], len(expected), "finished job count")
    equal(len(finished["results"]), len(expected), "completion receipt count")
    equal({tuple(r["job"]) for r in finished["results"]}, expected, "complete job inventory")
    baseline_finished = read(Path(plan["baseline_root"]) / "finished.json")
    equal(baseline_finished["status"], "complete", "fixed collection completion")
    equal(baseline_finished["jobs"], sorted([[p, s["id"]] for p, protocol in plan["protocols"].items()
                                           for s in protocol["scenarios"]]), "fixed job inventory")
    paths = [plan_path, folder / "started.json", folder / "finished.json", Path(plan["baseline_root"]) / "finished.json"]
    for receipt in finished["results"]:
        label = "_".join(receipt["job"])
        path = folder / (label + ".receipt.json")
        equal(read(path), receipt, "job receipt copy")
        equal(receipt["exit_code"], 0, "job exit")
        paths.append(path)
        for stream in ("stdout", "stderr"):
            log = folder / (label + "." + stream + ".txt")
            equal(bench.file_hash(log), receipt[stream + "_sha256"], "job log")
            paths.append(log)
    inputs = hashes(paths)
    inputs.update(plan["source_sha256"])
    inputs.update(plan["inputs_sha256"])
    for policy in plan["policies"].values():
        base = Path(policy["fingerprint"]["source_root"])
        inputs.update({str((base / name).resolve()): sha for name, sha in policy["fingerprint"]["files"].items()})
    return inputs


def frozen_reference_controls(plan):
    equal(bench.file_hash(IMPORT_PATH), IMPORT_SHA, "original reference import")
    receipt = read(IMPORT_PATH)
    original = bench.load_protocol(Path(plan["original_protocol"]))
    folders = [Path(p) for p in receipt["oracle_dirs"]]
    refs = bench_oracles.references(folders, receipt["protocol_sha256"], original)
    equal({cid: bench.digest(value) for cid, value in refs.items()}, receipt["reference_digests"], "frozen reference values")
    inputs = hashes([IMPORT_PATH])
    for folder in folders:
        for path in [folder / "manifest.json", *sorted(folder.glob("results/*.json"))]:
            equal(bench.file_hash(path), receipt["files_sha256"][str(path)], "original reference file")
            inputs.update(hashes([path]))
    controls = {}
    old_scenarios = {s["id"]: s for s in original["scenarios"]}
    for profile, protocol in plan["protocols"].items():
        for scenario in protocol["scenarios"]:
            old = old_scenarios[scenario["id"]]
            for phase, old_phase in zip(scenario["phases"], old["phases"]):
                cid = bench.context_id(bench.context_spec(scenario, phase))
                old_cid = bench.context_id(bench.context_spec(old, old_phase))
                control = {"chosen_action": refs[old_cid]["chosen_action"], "original_context_id": old_cid,
                           "original_reference_sha256": bench.digest(refs[old_cid]),
                           "use": "fixed common control only; no optimum or certificate transfer across profiles"}
                if cid in controls:
                    equal(controls[cid], control, "shared context control")
                controls[cid] = control
    return controls, inputs


def historical_runs(plan):
    original = bench.load_protocol(Path(plan["original_protocol"]))
    raw, _, receipt = learning.imported_runs({"import_receipt_path": str(IMPORT_PATH)}, original, deep=True)
    scenarios = {s["id"]: s for s in plan["protocols"]["off"]["scenarios"]}
    remap = {}
    for old in original["scenarios"]:
        current = scenarios[old["id"]]
        for before, after in zip(old["phases"], current["phases"], strict=True):
            old_cid = bench.context_id(bench.context_spec(old, before))
            cid = bench.context_id(bench.context_spec(current, after))
            if old_cid in remap:
                equal(remap[old_cid], cid, "historical context remap")
            remap[old_cid] = cid
    compact = []
    for run in raw:
        compact.append({k: run[k] for k in ("scenario", "seed", "n", "summary", "trace_path", "trace_sha256")}
            | {"profile": "off", "role": run["generation"], "observation_mode": "legacy",
               "action_counts": [dict(row, context_id=remap[row["context_id"]]) for row in run["action_counts"]],
               "original_action_counts": run["action_counts"], "historical_import": str(IMPORT_PATH),
               "observation_diagnostics": {}})
    inputs = dict(receipt["files_sha256"])
    inputs.update(hashes([IMPORT_PATH]))
    legacy.check_files(inputs)
    compact.sort(key=lambda r: (r["profile"], r["role"], r["observation_mode"], r["scenario"], r["seed"]))
    return compact, inputs


def manifest_with_fixed(protocol, protocol_hash, aliases, controls):
    manifest = validation.family_manifest(protocol, protocol_hash, aliases, controls)
    path = collector.RUNS / "M1_fixed_checks_01.json"
    fixed = read(path)
    equal(fixed["plan_sha256"], PLAN_SHA, "fixed check plan")
    equal(fixed["script_sha256"], bench.file_hash(ROOT / "experiments/v33/m1_fixed_checks.py"), "fixed check recipe")
    actions = fixed["actions"]
    equal(len(actions), fixed["action_count"], "fixed action count")
    jobs = {(job["context_id"], tuple(job["action"])): job for job in manifest["jobs"]}
    fixed_keys = []
    for cid, spec in bench.all_contexts(protocol).items():
        context = spec["context"]
        target = {"k": 2, "w": 1280, "rtt_ms": 50, "uplink_mbps": 2, "cert_bytes": 16000}
        if context != dict(target, p=context.get("p")) or context.get("p") not in (.02, .15):
            continue
        if context.get("loss_model", "iid") != "iid" or context.get("s2c_loss", 0) != 0 or spec.get("mixture"):
            continue
        for action in actions:
            key = (cid, tuple(action))
            jobs[key] = {"context_id": cid, "action": action, "reference_action": controls[cid]["chosen_action"],
                         "job_id": cid + "_" + "_".join(map(str, action))}
            fixed_keys.append([cid, action])
    if not fixed_keys:
        raise ValueError("fixed action contexts missing")
    manifest["jobs"] = [jobs[key] for key in sorted(jobs)]
    manifest["evaluation_family_size"] = len(jobs)
    manifest["additional_fixed_design_keys"] = fixed_keys
    validation.bench_oracles.validate_oracle_manifest(manifest, protocol_hash=protocol_hash, mode="actions")
    return manifest


def freeze(plan_path, out, protocol_path, validated_path):
    destinations = [Path(p).resolve() for p in (out, protocol_path, validated_path)]
    if len(set(destinations)) != 3 or any(p.exists() for p in destinations):
        raise ValueError("family outputs must be three distinct new paths")
    plan = collector.load_plan(plan_path)
    inputs = collection_inputs(plan_path, plan)
    controls, reference_inputs = frozen_reference_controls(plan)
    inputs.update(reference_inputs)
    protocol = combined_protocol(plan)
    equal(protocol["oracle"]["validation_samples"], plan["report_rules"]["mc_samples"], "fixed MC samples")
    equal(protocol["oracle"]["validation_seed"], plan["report_rules"]["mc_seed"], "fixed MC seed")
    compact = []
    with ProcessPoolExecutor(max_workers=plan["workers"]) as executor:
        futures = [executor.submit(validate_shard, str(plan_path), job) for job in collector.jobs(plan)]
        for future in as_completed(futures):
            result = future.result()
            compact.extend(result["runs"])
            for path, sha in result["inputs_sha256"].items():
                if path in inputs:
                    equal(inputs[path], sha, "consistent repeated input")
                inputs[path] = sha
            print(json.dumps({"validated_job": result["job"], "validated_runs": len(compact)}), flush=True)
    compact.sort(key=lambda r: (r["profile"], r["role"], r["observation_mode"], r["scenario"], r["seed"]))
    equal(len(compact), sum(len(plan["protocols"][job[0]]["seeds"]) for job in collector.jobs(plan)), "complete run count")
    history, historical_inputs = historical_runs(plan)
    compact.extend(history)
    compact.sort(key=lambda r: (r["profile"], r["role"], r["observation_mode"], r["scenario"], r["seed"]))
    inputs.update(historical_inputs)
    aliases = [dict(r, generation=r["profile"] + "_" + r["role"] + "_" + r["observation_mode"], variant="full") for r in compact]
    equal(bench.file_hash(PATH), IMPORTED_SHA, "loaded family adapter")
    inputs.update(hashes([PATH, Path(legacy.__file__), Path(validation.__file__),
                         ROOT / "docs/M1 세계 간 MC 오차.md", ROOT / "experiments/v33/bench_m1_report.py",
                         ROOT / "experiments/v33/m1_fixed_world_report.py",
                         ROOT / "experiments/v33/m1_fixed_checks.py", collector.RUNS / "M1_fixed_checks_01.json"]))
    legacy.check_files(inputs)
    bench.write_new(protocol_path, protocol)
    equal(bench.load_protocol(protocol_path), protocol, "combined evaluation protocol")
    bench.write_new(validated_path, {"schema": SCHEMA, "runs": compact, "run_count": len(compact),
                                    "connections": sum(r["n"] for r in compact), "validation": "all raw rows and observation history"})
    inputs.update(hashes([protocol_path, validated_path]))
    manifest = manifest_with_fixed(protocol, bench.file_hash(protocol_path), aliases, controls)
    result = {"schema": SCHEMA, "collection_plan_path": str(plan_path.resolve()), "collection_plan_sha256": PLAN_SHA,
              "protocol_path": str(protocol_path.resolve()), "protocol_sha256": bench.file_hash(protocol_path),
              "validated_path": str(validated_path.resolve()), "validated_sha256": bench.file_hash(validated_path),
              "contexts_sha256": bench.digest(bench.all_contexts(protocol)), "manifest": manifest,
              "inputs_sha256": inputs, "planner_sha256": IMPORTED_SHA, "reference_controls": controls,
              "run_count": len(compact), "connections": sum(r["n"] for r in compact),
              "report_rules": plan["report_rules"], "data_kind": plan["data_kind"]}
    bench.write_new(out, result)
    return {"status": "complete", "family": len(manifest["jobs"]), "contexts": len(controls),
            "runs": len(compact), "connections": result["connections"], "sha256": bench.file_hash(out)}


def execution_plan(path, sha):
    equal(bench.file_hash(path), sha, "family hash")
    saved = read(path)
    equal(saved["schema"], SCHEMA, "family schema")
    equal(saved["planner_sha256"], IMPORTED_SHA, "planner identity")
    equal(bench.file_hash(PATH), IMPORTED_SHA, "loaded planner identity")
    collector.load_plan(saved["collection_plan_path"])
    legacy.check_files(saved["inputs_sha256"])
    protocol = bench.load_protocol(Path(saved["protocol_path"]))
    plan = collector.load_plan(saved["collection_plan_path"])
    equal(saved["report_rules"], plan["report_rules"], "frozen reporting rules")
    equal(protocol, combined_protocol(plan), "combined protocol reconstruction")
    compact = read(saved["validated_path"])["runs"]
    history, _ = historical_runs(plan)
    equal([r for r in compact if r["role"] in ("v31", "v32")], history, "historical import reconstruction")
    aliases = [dict(r, generation=r["profile"] + "_" + r["role"] + "_" + r["observation_mode"], variant="full") for r in compact]
    controls, _ = frozen_reference_controls(plan)
    equal(controls, saved["reference_controls"], "common controls")
    rebuilt = manifest_with_fixed(protocol, saved["protocol_sha256"], aliases, controls)
    equal(rebuilt, saved["manifest"], "whole action family reconstruction")
    metadata = {"schema": pool.SCHEMA, "adapter_sha256": bench.file_hash(pool.__file__),
                "manifest_sha256": bench.digest(rebuilt), "protocol_path": saved["protocol_path"],
                "protocol_sha256": saved["protocol_sha256"], "family_plan_path": str(Path(path).resolve()),
                "family_plan_sha256": sha, "source_sha256": rebuilt["source_sha256"],
                "inputs_sha256": saved["inputs_sha256"], "contexts_sha256": saved["contexts_sha256"],
                "planner_sha256": IMPORTED_SHA, "input_validation": "M1 complete 2x2x3 factorial and original v31/v32; every trace row validated"}
    pool._check_sources(metadata)
    return saved, metadata, compact


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("freeze")
    p.add_argument("--plan", type=Path, default=collector.PLAN)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--protocol-out", type=Path, required=True)
    p.add_argument("--validated-out", type=Path, required=True)
    p = sub.add_parser("run")
    p.add_argument("--family", type=Path, required=True)
    p.add_argument("--sha256", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if (collector.RUNS.parent / "state/MEASURE_LOCK.json").exists():
        raise ValueError("measurement lock forbids computation")
    if args.command == "freeze":
        result = freeze(args.plan, args.out, args.protocol_out, args.validated_out)
    else:
        saved, metadata, _ = execution_plan(args.family, args.sha256)
        result = pool.run_pool(args.out, saved["manifest"], metadata, workers=8, time_budget_seconds=300,
                               loop=True, resume=args.resume)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
