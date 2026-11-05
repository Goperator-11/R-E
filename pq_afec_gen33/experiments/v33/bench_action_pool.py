import sys
sys.dont_write_bytecode = True
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
import json
import math
import multiprocessing
import os
from pathlib import Path
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.v33 import bench, bench_oracles, oracle

SCHEMA = "padfec.v33.action_pool/1"
ADAPTER_PATH = Path(__file__).resolve()
IMPORTED_ADAPTER_SHA256 = bench.file_hash(ADAPTER_PATH)
IMPORTED_PRODUCER_SHA256 = {name: bench.file_hash(ADAPTER_PATH.with_name(name))
                           for name in sorted(bench_oracles.MANIFEST_SOURCES)}


class SourceMismatch(ValueError):
    pass


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _equal(actual, expected, label):
    if bench.canonical(actual) != bench.canonical(expected):
        raise ValueError(f"action pool {label} differs")


def _sources():
    return {name: bench.file_hash(ADAPTER_PATH.with_name(name))
            for name in sorted(bench_oracles.MANIFEST_SOURCES)}


def _stamp():
    return f"{time.time_ns():020d}_{uuid.uuid4().hex}"


def _new_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = bench.canonical(value) + b"\n"
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _publish(path, value):
    path = Path(path)
    staging = path.parent.parent / "published" / f"{path.stem}.{_stamp()}.json"
    _new_json(staging, value)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.link(staging, path)


@contextmanager
def exclusive_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError(f"action pool is already locked: {path}") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _input_hashes(raw_dirs, oracle_dirs):
    paths = []
    for folder in raw_dirs:
        paths.append(folder / "manifest.json")
        paths.extend(sorted(folder.glob("*/*/*/seed*.json")))
    for folder in oracle_dirs:
        paths.append(folder / "manifest.json")
        paths.extend(sorted(folder.glob("results/*.json")))
    return {str(path.resolve()): bench.file_hash(path) for path in paths}


def prepare_plan(protocol_path, family_plan_path, family_plan_sha256, oracle_dirs):
    protocol_path, family_plan_path = Path(protocol_path).resolve(), Path(family_plan_path).resolve()
    _equal(bench.file_hash(family_plan_path), family_plan_sha256, "family plan hash")
    family_plan = read_json(family_plan_path)
    protocol = bench.load_protocol(protocol_path)
    protocol_hash = bench.file_hash(protocol_path)
    _equal(family_plan["protocol_sha256"], protocol_hash, "family protocol")
    raw_dirs = [Path(path).resolve() for path in family_plan["raw_folders"]]
    oracle_dirs = [Path(path).resolve() for path in oracle_dirs]
    if not raw_dirs or len(set(raw_dirs)) != len(raw_dirs):
        raise ValueError("action pool raw folders must be unique and nonempty")
    if not oracle_dirs or len(set(oracle_dirs)) != len(oracle_dirs):
        raise ValueError("action pool oracle folders must be unique and nonempty")
    raw_manifests = [{"path": str(path / "manifest.json"), "sha256": bench.file_hash(path / "manifest.json")}
                     for path in raw_dirs]
    _equal(raw_manifests, family_plan["raw_manifests"], "raw manifests")
    initial_inputs = _input_hashes(raw_dirs, oracle_dirs)
    raw = bench_oracles.raw_summaries(raw_dirs, protocol_hash)
    identities = [[r["generation"], r["variant"], r["scenario"], r["seed"]] for r in raw]
    _equal(len(raw), family_plan["raw_run_count"], "raw run count")
    _equal(identities, family_plan["raw_run_identities"], "raw identities")
    for folder in raw_dirs:
        manifest = read_json(folder / "manifest.json")
        _equal(manifest["protocol"], protocol, "raw embedded protocol")
        _equal(manifest["source_sha256"], bench.source_hashes(), "raw producer sources")
        _equal(manifest["policy_source_fingerprints"], bench.policy_source_fingerprints(protocol, manifest["generations"]), "raw policy sources")
    contexts = bench.all_contexts(protocol)
    keys = sorted({(row["context_id"], tuple(row["action"])) for result in raw for row in result["action_counts"]})
    job_keys = [{"context_id": cid, "action": list(action), "job_id": cid + "_" + "_".join(map(str, action))}
                for cid, action in keys]
    _equal(job_keys, family_plan["job_keys"], "whole action family")
    _equal(len(keys), family_plan["evaluation_family_size"], "family size")
    counts = {cid: sum(key[0] == cid for key in keys) for cid in sorted({key[0] for key in keys})}
    _equal(counts, family_plan["jobs_by_context"], "jobs by context")
    if set(counts) != set(contexts):
        raise ValueError("action pool requires actions for every protocol context")
    reference_jobs = set()
    for folder in oracle_dirs:
        manifest = read_json(folder / "manifest.json")
        bench_oracles.validate_oracle_manifest(manifest, protocol_hash=protocol_hash, mode="build")
        expected = {job["job_id"] for job in manifest["jobs"]}
        if reference_jobs & expected:
            raise ValueError("duplicate reference context across oracle folders")
        reference_jobs |= expected
        found = {path.stem for path in folder.glob("results/*.json")}
        if found != expected:
            raise ValueError("all reference results must be complete before action evaluation")
    if reference_jobs != set(contexts):
        raise ValueError("action pool requires every protocol reference context")
    refs = bench_oracles.references(oracle_dirs, protocol_hash, protocol)
    _equal(set(refs) == set(contexts), True, "reference coverage")
    jobs = [{"context_id": cid, "action": list(action), "reference_action": refs[cid]["chosen_action"],
             "job_id": cid + "_" + "_".join(map(str, action))} for cid, action in keys]
    manifest = {"schema": "padfec.v33.oracle_jobs/1", "mode": "actions", "protocol_sha256": protocol_hash,
                "source_sha256": _sources(), "jobs": jobs, "evaluation_family_size": len(jobs),
                "raw_run_identities": identities, "oracle_digests": {key: bench.digest(value) for key, value in refs.items()}}
    bench_oracles.validate_oracle_manifest(manifest, protocol_hash=protocol_hash, mode="actions")
    _equal(_input_hashes(raw_dirs, oracle_dirs), initial_inputs, "inputs changed during preparation")
    metadata = {"schema": SCHEMA, "adapter_sha256": IMPORTED_ADAPTER_SHA256,
                "manifest_sha256": bench.digest(manifest), "protocol_path": str(protocol_path),
                "protocol_sha256": protocol_hash, "family_plan_path": str(family_plan_path),
                "family_plan_sha256": family_plan_sha256, "source_sha256": manifest["source_sha256"],
                "inputs_sha256": initial_inputs, "contexts_sha256": bench.digest(contexts)}
    _check_sources(metadata)
    return manifest, metadata


def _check_sources(metadata):
    try:
        _equal(bench.file_hash(ADAPTER_PATH), IMPORTED_ADAPTER_SHA256, "loaded adapter source")
        _equal(IMPORTED_ADAPTER_SHA256, metadata["adapter_sha256"], "adapter source")
        _equal(_sources(), IMPORTED_PRODUCER_SHA256, "loaded producer sources")
        _equal(_sources(), metadata["source_sha256"], "producer sources")
        _equal(bench.file_hash(metadata["protocol_path"]), metadata["protocol_sha256"], "protocol source")
        _equal(bench.file_hash(metadata["family_plan_path"]), metadata["family_plan_sha256"], "family plan source")
    except (ValueError, OSError) as exc:
        raise SourceMismatch(str(exc)) from exc


def _check_inputs(metadata):
    for path, expected in metadata["inputs_sha256"].items():
        _equal(bench.file_hash(path), expected, f"input {path}")


def _load_execution(out):
    out = Path(out)
    manifest = read_json(out / "manifest.json")
    metadata = read_json(out / "execution.json")
    _equal(metadata["schema"], SCHEMA, "execution schema")
    _equal(bench.digest(manifest), metadata["manifest_sha256"], "execution manifest")
    _equal(manifest["source_sha256"], metadata["source_sha256"], "execution sources")
    _check_sources(metadata)
    bench_oracles.validate_oracle_manifest(manifest, protocol_hash=metadata["protocol_sha256"], mode="actions")
    protocol = bench.load_protocol(Path(metadata["protocol_path"]))
    contexts = bench.all_contexts(protocol)
    _equal(bench.digest(contexts), metadata["contexts_sha256"], "contexts")
    return manifest, metadata, protocol, contexts


def _job_paths(out, job_id):
    return Path(out) / "results" / f"{job_id}.json", Path(out) / "checkpoints" / f"{job_id}.json"


def _validate_result(result, manifest, protocol, contexts, job):
    _equal(result.get("protocol_sha256"), manifest["protocol_sha256"], "result protocol")
    bench_oracles.validate_oracle_result(result, protocol=protocol, context_spec=contexts[job["context_id"]],
                                        job=job, mode="actions", evaluation_family_size=manifest["evaluation_family_size"])


def _checkpoint_identity(protocol, context, job, family):
    spec = oracle._spec({**protocol["oracle"], "mixture": context["mixture"], "evaluation_family_size": family})
    params = oracle.load_params(context["world_params"])
    return oracle._digest({"kind": "evaluate_action", "context": context["context"],
                           "action": oracle._action(job["action"]), "reference": oracle._action(job["reference_action"]),
                           "params": params, "spec": oracle._semantic_spec(spec), "sources": oracle._source_hashes()})


def inspect_job(out, manifest, metadata, protocol, contexts, job):
    result_path, checkpoint_path = _job_paths(out, job["job_id"])
    starts = sorted((Path(out) / "attempts").glob(f'{job["job_id"]}.*.started.json'))
    receipts = sorted((Path(out) / "attempts").glob(f'{job["job_id"]}.*.finished.json'))
    if {path.name.replace(".started.json", "") for path in starts} != {path.name.replace(".finished.json", "") for path in receipts}:
        raise ValueError(f'unfinished attempt requires investigation: {job["job_id"]}')
    previous_checkpoint = None
    completed = False
    for start_path, receipt_path in zip(starts, receipts):
        start, receipt = read_json(start_path), read_json(receipt_path)
        for entry in (start, receipt):
            _equal(entry["job"], job, "attempt job")
            _equal(entry["execution_sha256"], bench.digest(metadata), "attempt execution")
        _equal(receipt["started_sha256"], bench.file_hash(start_path), "attempt start hash")
        _equal(start["input_checkpoint_sha256"], previous_checkpoint, "checkpoint chain")
        if completed or receipt["status"] not in ("complete", "partial", "failed"):
            raise ValueError("duplicate complete job or unknown attempt status")
        if receipt.get("unattested"):
            raise ValueError("unattested worker failure requires investigation")
        previous_checkpoint = receipt["checkpoint_sha256"]
        completed = receipt["status"] == "complete"
        if completed:
            _equal(bench.file_hash(result_path), receipt["result_sha256"], "result content hash")
        elif receipt.get("result_sha256") is not None:
            raise ValueError("incomplete attempt has a result digest")
    actual_checkpoint = bench.file_hash(checkpoint_path) if checkpoint_path.exists() else None
    _equal(actual_checkpoint, previous_checkpoint, "checkpoint content hash")
    if checkpoint_path.exists():
        checkpoint = read_json(checkpoint_path)
        _equal(checkpoint.get("schema"), oracle.SCHEMA, "checkpoint schema")
        _equal(checkpoint.get("identity"), _checkpoint_identity(protocol, contexts[job["context_id"]], job, manifest["evaluation_family_size"]), "checkpoint identity")
    if result_path.exists() != completed:
        raise ValueError("result exists without a completed receipt")
    if completed:
        _validate_result(read_json(result_path), manifest, protocol, contexts, job)
    return {"status": "complete" if completed else "pending", "checkpoint_sha256": actual_checkpoint,
            "previous_attempts": len(receipts)}


def progress_writer(out, attempt, job_id, run_id, clock=time.monotonic):
    last_recorded = None
    def progress(value):
        nonlocal last_recorded
        now = clock()
        if last_recorded is None or now - last_recorded >= 5.0 or value["connections"] == value["target_connections"]:
            _new_json(Path(out) / "progress" / f"{attempt}.{_stamp()}.json", {"job_id": job_id, "run_id": run_id, **value})
            last_recorded = now
    return progress


def run_job(out, job_id, run_id, time_budget_seconds):
    out = Path(out)
    with exclusive_lock(out / "locks" / f"{job_id}.lock"):
        manifest, metadata, protocol, contexts = _load_execution(out)
        jobs = {job["job_id"]: job for job in manifest["jobs"]}
        if job_id not in jobs:
            raise ValueError("job is outside the full manifest")
        job = jobs[job_id]
        previous = inspect_job(out, manifest, metadata, protocol, contexts, job)
        if previous["status"] == "complete":
            return {"job_id": job_id, "status": "complete", "reused": True}
        result_path, checkpoint_path = _job_paths(out, job_id)
        attempt = f"{job_id}.{_stamp()}"
        started_path = out / "attempts" / f"{attempt}.started.json"
        receipt_path = out / "attempts" / f"{attempt}.finished.json"
        binding = {"schema": SCHEMA, "job": job, "execution_sha256": bench.digest(metadata), "run_id": run_id,
                   "pid": os.getpid(), "started_ns": time.time_ns()}
        _new_json(started_path, {**binding, "input_checkpoint_sha256": previous["checkpoint_sha256"]})
        receipt = {**binding, "started_sha256": bench.file_hash(started_path)}
        try:
            _check_sources(metadata)
            context = contexts[job["context_id"]]
            spec = {**protocol["oracle"], "mixture": context["mixture"],
                    "evaluation_family_size": manifest["evaluation_family_size"],
                    "checkpoint_path": str(checkpoint_path), "time_budget_seconds": time_budget_seconds}
            progress = progress_writer(out, attempt, job_id, run_id)
            result = oracle.evaluate_action(context["context"], job["action"], job["reference_action"], context["world_params"], spec, progress)
            _check_sources(metadata)
            result.update(context_id=job["context_id"], protocol_sha256=manifest["protocol_sha256"], job_id=job_id)
            if result["status"] == "complete":
                bench_oracles._complete_action_metadata(result, protocol, context, manifest["evaluation_family_size"])
                _validate_result(result, manifest, protocol, contexts, job)
                _publish(result_path, result)
                receipt.update(status="complete", result_sha256=bench.file_hash(result_path))
            elif result["status"] == "partial":
                if not checkpoint_path.is_file():
                    raise ValueError("partial action evaluation has no checkpoint")
                receipt.update(status="partial", result_sha256=None, partial_result=result)
            else:
                raise ValueError("unknown action evaluation status")
        except Exception as exc:
            receipt.update(status="failed", result_sha256=None, error_type=type(exc).__name__,
                           error=str(exc), traceback=traceback.format_exc(),
                           unattested=isinstance(exc, SourceMismatch) or result_path.exists())
            try:
                _check_sources(metadata)
                if checkpoint_path.exists():
                    checkpoint = read_json(checkpoint_path)
                    _equal(checkpoint.get("schema"), oracle.SCHEMA, "failed checkpoint schema")
                    _equal(checkpoint.get("identity"), _checkpoint_identity(protocol, contexts[job["context_id"]], job, manifest["evaluation_family_size"]), "failed checkpoint identity")
                    if checkpoint.get("status") == "complete":
                        candidate = dict(checkpoint["report"])
                        candidate.update(context_id=job["context_id"], protocol_sha256=manifest["protocol_sha256"], job_id=job_id)
                        bench_oracles._complete_action_metadata(candidate, protocol, contexts[job["context_id"]], manifest["evaluation_family_size"])
                        _validate_result(candidate, manifest, protocol, contexts, job)
            except Exception as attestation_error:
                receipt.update(unattested=True, attestation_error=str(attestation_error))
        receipt.update(finished_ns=time.time_ns(), checkpoint_sha256=bench.file_hash(checkpoint_path) if checkpoint_path.exists() else None)
        _new_json(receipt_path, receipt)
        return {"job_id": job_id, "status": receipt["status"], "receipt": str(receipt_path),
                "error": receipt.get("error"), "n": receipt.get("partial_result", {}).get("n")}


def _check_output_inventory(out, manifest):
    ids = {job["job_id"] for job in manifest["jobs"]}
    for directory in ("results", "checkpoints"):
        for path in (Path(out) / directory).glob("*.json"):
            if path.stem not in ids:
                raise ValueError(f"unknown {directory} job: {path.name}")
    for path in (Path(out) / "attempts").glob("*.json"):
        if not any(path.name.startswith(job_id + ".") for job_id in ids):
            raise ValueError("attempt is outside the manifest")


def run_pool(out, manifest, metadata, *, workers=2, time_budget_seconds=300.0, resume=False, loop=False):
    if type(workers) is not int or workers < 1:
        raise ValueError("workers must be a positive integer")
    if not math.isfinite(time_budget_seconds) or time_budget_seconds <= 0:
        raise ValueError("time budget must be finite and positive")
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    with exclusive_lock(out / "pool.lock"):
        _check_sources(metadata)
        _check_inputs(metadata)
        manifest_path, execution_path = out / "manifest.json", out / "execution.json"
        if manifest_path.exists() or execution_path.exists():
            if not resume or not manifest_path.exists() or not execution_path.exists():
                raise ValueError("--resume and both existing metadata files are required")
            _equal(read_json(manifest_path), manifest, "resume whole manifest")
            _equal(read_json(execution_path), metadata, "resume execution metadata")
        else:
            if any(path.name != "pool.lock" for path in out.iterdir()):
                raise ValueError("new action pool directory is not empty")
            _new_json(manifest_path, manifest)
            _new_json(execution_path, metadata)
        loaded, saved, protocol, contexts = _load_execution(out)
        _equal(loaded, manifest, "loaded manifest")
        _equal(saved, metadata, "loaded execution")
        _check_output_inventory(out, manifest)
        for job in manifest["jobs"]:
            inspect_job(out, manifest, metadata, protocol, contexts, job)
        run_id = _stamp()
        runtime = {"schema": SCHEMA, "run_id": run_id, "execution_sha256": bench.digest(metadata),
                   "adapter_sha256": metadata["adapter_sha256"], "workers": workers,
                   "time_budget_seconds": time_budget_seconds, "loop": loop, "resume": resume,
                   "progress_interval_seconds": 5.0,
                   "pid": os.getpid(), "python": sys.version, "start_method": "spawn", "started_ns": time.time_ns()}
        _new_json(out / "runs" / f"{run_id}.started.json", runtime)
        failed = []
        try:
            while True:
                pending = [job for job in manifest["jobs"]
                           if inspect_job(out, manifest, metadata, protocol, contexts, job)["status"] != "complete"]
                if not pending:
                    break
                with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as executor:
                    futures = {executor.submit(run_job, str(out), job["job_id"], run_id, time_budget_seconds): job for job in pending}
                    for future in as_completed(futures):
                        job = futures[future]
                        try:
                            result = future.result()
                        except Exception as exc:
                            result = {"job_id": job["job_id"], "status": "failed", "error": str(exc),
                                      "error_type": type(exc).__name__, "traceback": traceback.format_exc()}
                            _new_json(out / "failures" / f'{job["job_id"]}.{_stamp()}.json', result)
                        if result["status"] == "failed":
                            failed.append(result)
                        print(json.dumps(result, ensure_ascii=False), flush=True)
                _check_sources(metadata)
                _check_inputs(metadata)
                if failed or not loop:
                    break
            complete = []
            pending = []
            for job in manifest["jobs"]:
                status = inspect_job(out, manifest, metadata, protocol, contexts, job)
                (complete if status["status"] == "complete" else pending).append(job["job_id"])
            _check_sources(metadata)
            _check_inputs(metadata)
            report = {"schema": SCHEMA, "run_id": run_id, "status": "failed" if failed else "partial" if pending else "complete",
                      "evaluation_family_size": manifest["evaluation_family_size"], "complete_jobs": complete,
                      "pending_jobs": pending, "failed_jobs": failed, "execution_sha256": bench.digest(metadata),
                      "finished_ns": time.time_ns()}
        except Exception as exc:
            report = {"schema": SCHEMA, "run_id": run_id, "status": "failed", "error": str(exc),
                      "error_type": type(exc).__name__, "traceback": traceback.format_exc(),
                      "execution_sha256": bench.digest(metadata), "finished_ns": time.time_ns()}
            _new_json(out / "runs" / f"{run_id}.finished.json", report)
            raise
        _new_json(out / "runs" / f"{run_id}.finished.json", report)
        return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, default=ROOT / "g3/v33/bench_protocol.json")
    parser.add_argument("--family-plan", type=Path, required=True)
    parser.add_argument("--family-plan-sha256", required=True)
    parser.add_argument("--oracle-dirs", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--time-budget-seconds", type=float, default=300.0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args(argv)
    manifest, metadata = prepare_plan(args.protocol, args.family_plan, args.family_plan_sha256, args.oracle_dirs)
    report = run_pool(args.out, manifest, metadata, workers=args.workers, time_budget_seconds=args.time_budget_seconds,
                      resume=args.resume, loop=args.loop)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "complete" else 2 if report["status"] == "failed" else 3


if __name__ == "__main__":
    raise SystemExit(main())
