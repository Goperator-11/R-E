from pathlib import Path
import re
from experiments.v33 import bench, bench_action_pool_m1 as pool, bench_oracles_m1 as bench_oracles, bench_report
from experiments.v33.bench_learning_report import equal, check_files

STAMP = r"[0-9]{20}_[0-9a-f]{32}"

def family_manifest(protocol, protocol_hash, runs, references):
    contexts = bench.all_contexts(protocol)
    equal(sorted(references), sorted(contexts), "full reference contexts")
    keys = set()
    for run in runs:
        for key in bench_report.weights(run):
            if key[0] not in contexts:
                raise ValueError("action is outside the protocol contexts")
            keys.add(key)
    if {cid for cid, _ in keys} != set(contexts):
        raise ValueError("full action family must cover every context")
    jobs = [{"context_id": cid, "action": list(action),
             "reference_action": references[cid]["chosen_action"],
             "job_id": cid + "_" + "_".join(map(str, action))} for cid, action in sorted(keys)]
    manifest = {"schema": "padfec.v33.oracle_jobs/1", "mode": "actions", "protocol_sha256": protocol_hash,
                "source_sha256": pool._sources(), "jobs": jobs, "evaluation_family_size": len(jobs),
                "raw_run_identities": [[run["generation"], run["variant"], run["scenario"], run["seed"]] for run in runs],
                "oracle_digests": {cid: bench.digest(value) for cid, value in sorted(references.items())}}
    bench_oracles.validate_oracle_manifest(manifest, protocol_hash=protocol_hash, mode="actions")
    return manifest


def job_set(value, known, label):
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"invalid {label}")
    if len(set(value)) != len(value) or not set(value) <= known:
        raise ValueError(f"duplicate or unknown {label}")
    return set(value)


def receipt_pairs(folder, pattern, metadata, manifest, runs=None):
    jobs = {job["job_id"]: job for job in manifest["jobs"]}
    pairs, hashes = {}, {}
    for path in sorted(Path(folder).glob("*.json")):
        match = re.fullmatch(pattern, path.name)
        if match is None:
            raise ValueError(f"unrecognized execution receipt: {path}")
        parts = match.groups()
        key, phase = tuple(parts[:-1]), parts[-1]
        entry = pool.read_json(path)
        equal(entry.get("schema"), pool.SCHEMA, "receipt schema")
        equal(entry.get("execution_sha256"), bench.digest(metadata), "receipt execution")
        if runs is None:
            equal(entry.get("run_id"), key[0], "run receipt identity")
        else:
            if key[0] not in jobs or entry.get("run_id") not in runs:
                raise ValueError("attempt has unknown job or run")
            equal(entry.get("job"), jobs[key[0]], "attempt job identity")
        pair = pairs.setdefault(key, {})
        if phase in pair:
            raise ValueError("duplicate receipt phase")
        pair[phase] = entry
        hashes[str(path.resolve())] = bench.file_hash(path)
    if not pairs:
        raise ValueError("execution receipts are missing")
    for key, pair in pairs.items():
        if set(pair) != {"started", "finished"}:
            raise ValueError("unfinished or unmatched execution receipt")
        start, finish = pair["started"], pair["finished"]
        equal(start["run_id"], finish["run_id"], "paired receipt run")
        if finish.get("status") not in ("complete", "partial"):
            raise ValueError("failed or unknown execution status requires investigation")
        if type(start.get("started_ns")) is not int or type(finish.get("finished_ns")) is not int:
            raise ValueError("receipt timestamps must be integers")
        if start["started_ns"] <= 0 or finish["finished_ns"] < start["started_ns"]:
            raise ValueError("invalid receipt timestamp order")
        if runs is None:
            equal(start.get("adapter_sha256"), metadata["adapter_sha256"], "run adapter")
            equal(finish.get("evaluation_family_size"), len(jobs), "run family")
            complete = job_set(finish.get("complete_jobs"), set(jobs), "complete jobs")
            pending = job_set(finish.get("pending_jobs"), set(jobs), "pending jobs")
            if complete & pending or complete | pending != set(jobs):
                raise ValueError("run does not partition the whole family")
            equal(finish.get("failed_jobs"), [], "failed jobs")
            equal(finish["status"], "partial" if pending else "complete", "run status")
        else:
            parent = runs[start["run_id"]]
            if start["started_ns"] < parent["started"]["started_ns"] or finish["finished_ns"] > parent["finished"]["finished_ns"]:
                raise ValueError("attempt timestamps are outside the run")
            equal(start.get("started_ns"), finish.get("started_ns"), "attempt start binding")
            equal(start.get("pid"), finish.get("pid"), "attempt worker identity")
    return pairs, hashes


def validate_pool_locked(out, manifest, metadata):
    out = Path(out).resolve()
    actual, saved, protocol, contexts = pool._load_execution(out)
    equal(actual, manifest, "pool full manifest")
    equal(saved, metadata, "pool execution metadata")
    pool._check_inputs(metadata)
    pool._check_output_inventory(out, manifest)
    if any((out / "failures").glob("*.json")):
        raise ValueError("pool failure files require investigation")
    run_pairs, receipt_hashes = receipt_pairs(out / "runs", rf"({STAMP})\.(started|finished)\.json", metadata, manifest)
    runs = {key[0]: pair for key, pair in run_pairs.items()}
    if runs[max(runs)]["finished"]["status"] != "complete":
        raise ValueError("latest pool run is incomplete")
    _, attempts = receipt_pairs(out / "attempts", rf"([^.]+)\.({STAMP})\.(started|finished)\.json", metadata, manifest, runs)
    receipt_hashes.update(attempts)
    tables = {}
    for job in manifest["jobs"]:
        status = pool.inspect_job(out, manifest, metadata, protocol, contexts, job)
        if status["status"] != "complete":
            raise ValueError("action job is incomplete")
        result_path, checkpoint_path = pool._job_paths(out, job["job_id"])
        item = pool.read_json(result_path)
        tables[(job["context_id"], tuple(job["action"]))] = item
        receipt_hashes[str(result_path.resolve())] = bench.file_hash(result_path)
        if checkpoint_path.exists():
            receipt_hashes[str(checkpoint_path.resolve())] = bench.file_hash(checkpoint_path)
    for name in ("manifest.json", "execution.json"):
        receipt_hashes[str(out / name)] = bench.file_hash(out / name)
    pool._check_sources(metadata)
    check_files(receipt_hashes)
    return tables, {"pool_path": str(out), "evaluation_family_size": len(manifest["jobs"]),
                    "validated_run_ids": sorted(runs), "files_sha256": receipt_hashes,
                    "execution_content_sha256": bench.digest(metadata),
                    "manifest_content_sha256": bench.digest(manifest)}
