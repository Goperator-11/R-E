import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from experiments.v33 import bench, bench_action_pool as pool, bench_oracles, oracle


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def fixture(tmp_path, structural=True, action_count=2):
    context = {"k": 2, "w": 1280, "p": 0 if structural else .02,
               "rtt_ms": 50, "uplink_mbps": 2, "cert_bytes": 2955 if structural else 9000}
    protocol = {"schema": "padfec.v33.benchmark/1", "seeds": list(range(31, 51)),
                "world": {"profile": "default", "source_sha256": {name: bench.file_hash(pool.ADAPTER_PATH.with_name(name))
                          for name in ("worldsim.py", "worldparams.json")}},
                "oracle": {"stage_sizes": [4, 8], "validation_samples": 8, "min_elimination_samples": 4,
                           "m_max": 0, "original_max_bytes": 1280 + action_count - 1, "chunk_size": 2},
                "generations": {"fixture": {"source_root": str(tmp_path / "fixture_policy")}},
                "scenarios": [{"id": f"B{i}", "family": f"B{i}", "context": context,
                               "world_params": {}, "phases": [{"length": action_count}]} for i in range(1, 13)]}
    protocol_path = tmp_path / "protocol.json"
    write(protocol_path, protocol)
    phash = bench.file_hash(protocol_path)
    contexts = bench.all_contexts(protocol)
    cid = next(iter(contexts))
    raw_dir = tmp_path / "raw"
    fingerprint = {"source_root": str(tmp_path / "fixture_policy"), "files": {}}
    raw_manifest = {"schema": "padfec.v33.benchmark_raw_manifest/1", "mode": "full", "protocol": protocol,
                    "protocol_sha256": phash, "generations": ["fixture"], "variant": "full",
                    "scenarios": [s["id"] for s in protocol["scenarios"]], "seeds": protocol["seeds"],
                    "policy_source_fingerprints": {"fixture": fingerprint}, "source_sha256": bench.source_hashes()}
    write(raw_dir / "manifest.json", raw_manifest)
    trace = tmp_path / "synthetic_trace.txt"
    trace.write_text("synthetic fixture, no measured observations\n", encoding="utf-8")
    for scenario in protocol["scenarios"]:
        for seed in protocol["seeds"]:
            result = {"generation": "fixture", "variant": "full", "scenario": scenario["id"], "seed": seed,
                      "mode": "full", "protocol_sha256": phash, "n": action_count, "trace_path": str(trace),
                      "trace_sha256": bench.file_hash(trace),
                      "policy_audit": {"source_root": fingerprint["source_root"], "source_unchanged": True, "source_sha256": {}},
                      "action_counts": [{"context_id": cid, "action": [delta, 0, 0], "n": 1} for delta in range(action_count)]}
            write(raw_dir / "fixture" / "full" / scenario["id"] / f"seed{seed:05d}.json", result)
    raw = bench_oracles.raw_summaries([raw_dir], phash)
    identities = [[r["generation"], r["variant"], r["scenario"], r["seed"]] for r in raw]
    family_path = tmp_path / "family.json"
    family = {"protocol_sha256": phash, "raw_folders": [str(raw_dir)],
              "raw_manifests": [{"path": str(raw_dir / "manifest.json"), "sha256": bench.file_hash(raw_dir / "manifest.json")}],
              "raw_run_count": len(raw), "raw_run_identities": identities, "evaluation_family_size": action_count,
              "job_keys": [{"context_id": cid, "action": [d, 0, 0], "job_id": f"{cid}_{d}_0_0"} for d in range(action_count)],
              "jobs_by_context": {cid: action_count}}
    write(family_path, family)
    refs = tmp_path / "refs"
    ref_manifest = {"schema": "padfec.v33.oracle_jobs/1", "mode": "build", "protocol_sha256": phash,
                    "source_sha256": pool._sources(), "jobs": [{"context_id": cid, "job_id": cid}],
                    "evaluation_family_size": None, "raw_run_identities": [], "oracle_digests": {}}
    write(refs / "manifest.json", ref_manifest)
    result = oracle.build_oracle(context, {}, {**protocol["oracle"], "mixture": []})
    result.update(context_id=cid, job_id=cid, protocol_sha256=phash)
    write(refs / "results" / f"{cid}.json", result)
    return protocol_path, family_path, refs


def prepare(paths):
    protocol_path, family_path, refs = paths
    return pool.prepare_plan(protocol_path, family_path, bench.file_hash(family_path), [refs])


def initialize(out, manifest, metadata):
    pool._new_json(out / "manifest.json", manifest)
    pool._new_json(out / "execution.json", metadata)


def inspect(out, manifest, metadata, job):
    _, _, protocol, contexts = pool._load_execution(out)
    return pool.inspect_job(out, manifest, metadata, protocol, contexts, job)


def test_manifest_uses_whole_inventory_and_original_validator(tmp_path):
    paths = fixture(tmp_path)
    manifest, metadata = prepare(paths)
    assert manifest["evaluation_family_size"] == len(manifest["jobs"]) == 2
    assert len(manifest["raw_run_identities"]) == 240
    assert set(manifest["oracle_digests"]) == {job["context_id"] for job in manifest["jobs"]}
    bench_oracles.validate_oracle_manifest(manifest, protocol_hash=manifest["protocol_sha256"], mode="actions")
    assert "workers" not in metadata
    assert "workers" not in manifest
    assert metadata["adapter_sha256"] == bench.file_hash(pool.ADAPTER_PATH)
    family = pool.read_json(paths[1])
    family["job_keys"].pop()
    family["evaluation_family_size"] = 1
    family["jobs_by_context"][manifest["jobs"][0]["context_id"]] = 1
    write(paths[1], family)
    with pytest.raises(ValueError, match="whole action family"):
        prepare(paths)


def test_family_plan_hash_is_external_and_references_must_all_be_ready(tmp_path):
    paths = fixture(tmp_path)
    with pytest.raises(ValueError, match="family plan hash"):
        pool.prepare_plan(paths[0], paths[1], "0" * 64, [paths[2]])
    result = next((paths[2] / "results").glob("*.json"))
    result.rename(result.with_suffix(".pending"))
    with pytest.raises(ValueError, match="all reference results"):
        prepare(paths)


def test_family_eighty_one_survives_partial_completion(tmp_path):
    manifest, metadata = prepare(fixture(tmp_path, action_count=81))
    out = tmp_path / "out"
    initialize(out, manifest, metadata)
    for job in (manifest["jobs"][0], manifest["jobs"][-1]):
        assert pool.run_job(out, job["job_id"], "test", 2)["status"] == "complete"
        result = pool.read_json(out / "results" / f'{job["job_id"]}.json')
        assert result["evaluation_family_size"] == 81
        assert result["spec"]["evaluation_family_size"] == 81
        assert result["n"] == 0
    assert sum(inspect(out, manifest, metadata, job)["status"] == "pending" for job in manifest["jobs"]) == 79
    assert pool.read_json(out / "manifest.json")["evaluation_family_size"] == 81


def test_duplicate_reference_folders_or_contexts_are_rejected(tmp_path):
    paths = fixture(tmp_path)
    with pytest.raises(ValueError, match="unique"):
        pool.prepare_plan(paths[0], paths[1], bench.file_hash(paths[1]), [paths[2], paths[2]])
    other = tmp_path / "duplicate_refs"
    write(other / "manifest.json", pool.read_json(paths[2] / "manifest.json"))
    result = next((paths[2] / "results").glob("*.json"))
    write(other / "results" / result.name, pool.read_json(result))
    with pytest.raises(ValueError, match="duplicate reference"):
        pool.prepare_plan(paths[0], paths[1], bench.file_hash(paths[1]), [paths[2], other])


@pytest.mark.parametrize("kind", ["producer", "policy"])
def test_raw_sources_are_verified_beyond_the_pinned_manifest_hash(tmp_path, kind):
    paths = fixture(tmp_path)
    family = pool.read_json(paths[1])
    raw_manifest_path = Path(family["raw_folders"][0]) / "manifest.json"
    manifest = pool.read_json(raw_manifest_path)
    if kind == "producer":
        manifest["source_sha256"]["bench.py"] = "wrong"
    else:
        manifest["policy_source_fingerprints"]["fixture"]["files"]["padfec/policy.py"] = "wrong"
    write(raw_manifest_path, manifest)
    family["raw_manifests"][0]["sha256"] = bench.file_hash(raw_manifest_path)
    write(paths[1], family)
    with pytest.raises(ValueError, match="raw .* sources"):
        prepare(paths)


def test_job_lock_rejects_duplicate_execution_and_complete_is_reused(tmp_path):
    manifest, metadata = prepare(fixture(tmp_path))
    out = tmp_path / "out"
    initialize(out, manifest, metadata)
    job = manifest["jobs"][0]
    with pool.exclusive_lock(out / "locks" / f'{job["job_id"]}.lock'):
        with pytest.raises(RuntimeError, match="already locked"):
            pool.run_job(out, job["job_id"], "test", 2)
    assert pool.run_job(out, job["job_id"], "test", 2)["status"] == "complete"
    assert pool.run_job(out, job["job_id"], "test2", 2)["reused"] is True
    assert len(list((out / "attempts").glob("*.started.json"))) == 1
    assert inspect(out, manifest, metadata, job)["status"] == "complete"


@pytest.mark.parametrize("key", ["adapter_sha256", "protocol_sha256", "source_sha256"])
def test_source_or_execution_contamination_is_rejected_before_job(tmp_path, key):
    manifest, metadata = prepare(fixture(tmp_path))
    out = tmp_path / "out"
    metadata = copy.deepcopy(metadata)
    metadata[key] = {"oracle.py": "wrong"} if key == "source_sha256" else "wrong"
    initialize(out, manifest, metadata)
    with pytest.raises(ValueError):
        pool.run_job(out, manifest["jobs"][0]["job_id"], "test", 2)
    assert not list((out / "attempts").glob("*.json"))


def test_modified_complete_result_rejected_even_when_metadata_still_valid(tmp_path):
    manifest, metadata = prepare(fixture(tmp_path))
    out = tmp_path / "out"
    initialize(out, manifest, metadata)
    job = manifest["jobs"][0]
    assert pool.run_job(out, job["job_id"], "test", 2)["status"] == "complete"
    path = out / "results" / f'{job["job_id"]}.json'
    result = pool.read_json(path)
    result["mean_hct_ms"] += 1
    write(path, result)
    with pytest.raises(ValueError, match="result content hash"):
        pool.run_job(out, job["job_id"], "resume", 2)


def test_mc_checkpoint_content_and_binding_are_checked_on_resume(tmp_path):
    manifest, metadata = prepare(fixture(tmp_path, structural=False))
    out = tmp_path / "out"
    initialize(out, manifest, metadata)
    job = manifest["jobs"][0]
    assert pool.run_job(out, job["job_id"], "test", 2)["status"] == "complete"
    path = out / "checkpoints" / f'{job["job_id"]}.json'
    checkpoint = pool.read_json(path)
    checkpoint["identity"] = "wrong"
    write(path, checkpoint)
    with pytest.raises(ValueError, match="checkpoint content hash"):
        pool.run_job(out, job["job_id"], "resume", 2)


def test_failure_is_preserved_and_explicit_resume_can_retry(tmp_path, monkeypatch):
    manifest, metadata = prepare(fixture(tmp_path))
    out = tmp_path / "out"
    initialize(out, manifest, metadata)
    job = manifest["jobs"][0]
    evaluate = oracle.evaluate_action
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic worker failure")
    monkeypatch.setattr(oracle, "evaluate_action", fail)
    failed = pool.run_job(out, job["job_id"], "test", 2)
    assert failed["status"] == "failed"
    receipt_path = Path(failed["receipt"])
    before = receipt_path.read_bytes()
    assert "synthetic worker failure" in pool.read_json(receipt_path)["traceback"]
    assert not (out / "results" / f'{job["job_id"]}.json').exists()
    monkeypatch.setattr(oracle, "evaluate_action", evaluate)
    assert pool.run_job(out, job["job_id"], "retry", 2)["status"] == "complete"
    assert receipt_path.read_bytes() == before
    assert inspect(out, manifest, metadata, job)["previous_attempts"] == 2


def test_partial_is_reported_and_resumes_same_family(tmp_path):
    manifest, metadata = prepare(fixture(tmp_path, structural=False))
    out = tmp_path / "out"
    initialize(out, manifest, metadata)
    job = manifest["jobs"][0]
    partial = pool.run_job(out, job["job_id"], "tiny_budget", 1e-12)
    assert partial["status"] == "partial"
    assert inspect(out, manifest, metadata, job)["status"] == "pending"
    assert pool.run_job(out, job["job_id"], "resume", 2)["status"] == "complete"
    result = pool.read_json(out / "results" / f'{job["job_id"]}.json')
    assert result["evaluation_family_size"] == 2
    assert result["n"] == 8


def test_post_evaluation_source_failure_never_reuses_its_checkpoint(tmp_path, monkeypatch):
    manifest, metadata = prepare(fixture(tmp_path, structural=False))
    out = tmp_path / "out"
    initialize(out, manifest, metadata)
    job = manifest["jobs"][0]
    original = pool._check_sources
    calls = 0
    def fail_after_evaluation(value):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise pool.SourceMismatch("synthetic post-evaluation source change")
        original(value)
    monkeypatch.setattr(pool, "_check_sources", fail_after_evaluation)
    failed = pool.run_job(out, job["job_id"], "test", 2)
    assert failed["status"] == "failed"
    assert pool.read_json(failed["receipt"])["unattested"] is True
    assert (out / "checkpoints" / f'{job["job_id"]}.json').exists()
    monkeypatch.setattr(pool, "_check_sources", original)
    with pytest.raises(ValueError, match="unattested worker failure"):
        pool.run_job(out, job["job_id"], "resume", 2)


def test_transient_post_evaluation_source_io_failure_is_unattested(tmp_path, monkeypatch):
    manifest, metadata = prepare(fixture(tmp_path, structural=False))
    out = tmp_path / "out"
    initialize(out, manifest, metadata)
    job = manifest["jobs"][0]
    sources = pool._sources
    calls = 0
    def transient_failure():
        nonlocal calls
        calls += 1
        if calls == 5:
            raise FileNotFoundError("synthetic source disappeared")
        return sources()
    monkeypatch.setattr(pool, "_sources", transient_failure)
    failed = pool.run_job(out, job["job_id"], "test", 2)
    assert failed["status"] == "failed"
    assert pool.read_json(failed["receipt"])["error_type"] == "SourceMismatch"
    assert pool.read_json(failed["receipt"])["unattested"] is True
    monkeypatch.setattr(pool, "_sources", sources)
    with pytest.raises(ValueError, match="unattested worker failure"):
        pool.run_job(out, job["job_id"], "resume", 2)


def test_progress_is_throttled_without_changing_callback_results(tmp_path):
    times = iter([0.0, 1.0, 4.9, 5.0, 5.1, 6.0])
    callback = pool.progress_writer(tmp_path, "attempt", "job", "run", lambda: next(times))
    for n in range(1, 7):
        assert callback({"connections": n, "target_connections": 6}) is None
    rows = [pool.read_json(path) for path in sorted((tmp_path / "progress").glob("*.json"))]
    assert [row["connections"] for row in rows] == [1, 4, 6]


def test_unfinished_attempt_and_unknown_results_are_not_silently_skipped(tmp_path):
    manifest, metadata = prepare(fixture(tmp_path))
    out = tmp_path / "out"
    initialize(out, manifest, metadata)
    job = manifest["jobs"][0]
    write(out / "attempts" / f'{job["job_id"]}.unfinished.started.json', {})
    with pytest.raises(ValueError, match="unfinished attempt"):
        pool.run_job(out, job["job_id"], "resume", 2)
    write(out / "results" / "unknown.json", {})
    with pytest.raises(ValueError, match="unknown results"):
        pool._check_output_inventory(out, manifest)


def test_actual_spawn_cli_smoke_and_resume_keep_full_family(tmp_path):
    paths = fixture(tmp_path)
    out = tmp_path / "spawn_out"
    command = [sys.executable, "-I", "-B", str(pool.ADAPTER_PATH),
               "--protocol", str(paths[0]), "--family-plan", str(paths[1]),
               "--family-plan-sha256", bench.file_hash(paths[1]), "--oracle-dirs", str(paths[2]),
               "--out", str(out), "--workers", "2", "--time-budget-seconds", "2"]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = pool.read_json(out / "manifest.json")
    assert manifest["evaluation_family_size"] == 2
    receipts = sorted((out / "attempts").glob("*.finished.json"))
    assert len(receipts) == 2
    for path in (out / "results").glob("*.json"):
        assert pool.read_json(path)["method"] == "structural_zero_loss_pair"
        assert pool.read_json(path)["evaluation_family_size"] == 2
    before = {path.name: path.read_bytes() for path in receipts}
    result = subprocess.run(command + ["--resume"], capture_output=True, text=True, encoding="utf-8", timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
    assert {path.name: path.read_bytes() for path in (out / "attempts").glob("*.finished.json")} == before
    runtime = [pool.read_json(path) for path in (out / "runs").glob("*.started.json")]
    assert len(runtime) == 2
    assert all(item["workers"] == 2 and item["start_method"] == "spawn" for item in runtime)
    mutated = pool.read_json(out / "manifest.json")
    mutated["jobs"].pop()
    mutated["evaluation_family_size"] = 1
    write(out / "manifest.json", mutated)
    rejected = subprocess.run(command + ["--resume"], capture_output=True, text=True, encoding="utf-8", timeout=40)
    assert rejected.returncode != 0
    assert "resume whole manifest" in rejected.stderr
