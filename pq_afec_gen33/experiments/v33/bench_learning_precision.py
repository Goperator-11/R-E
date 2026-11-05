import sys
sys.dont_write_bytecode = True
import argparse
import copy
import hashlib
import json
from pathlib import Path
import time


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.v33 import bench, bench_action_pool as pool, bench_oracles
from experiments.v33 import bench_learning_report as reporting


PATH = Path(__file__).resolve()
IMPORTED_SHA256 = bench.file_hash(PATH)
PLAN_SCHEMA = "padfec.v33.learning_precision_plan/1"
PLAN_PUBLICATION_SCHEMA = "padfec.v33.learning_precision_plan_publication/1"
REPORT_SCHEMA = "padfec.v33.learning_precision_report/1"
PUBLICATION_SCHEMA = "padfec.v33.learning_precision_publication/1"
ORIGINAL_FAMILY_SHA256 = "e315280cf0199ab36a77f2f8a6d5289bf80dc00553aae4b0599610e2a5ff5e35"
ORIGINAL_REPORT_SHA256 = "c89026795ce3e04fb35dfc19d4bf01d0700571fc7fae1330a6caa065dc5616cb"
ORIGINAL_PUBLICATION_SHA256 = "ae7bdc37e3a20c344799bceb0ee9b7c654ddd9a85335cd0a99fda2925082e37a"
ORIGINAL_PROTOCOL_SHA256 = "10cf3aa16b460054b533f03170b7c8718a21450eba39359525dbdba098583305"
REPORTER_SHA256 = "9f480a41f456101e74461d2e8a3509625e3be148dda686eea752c1ce92a39c49"
CONTRACT = {
    "original_validation_samples": 131072,
    "validation_samples": 1048576,
    "validation_seed": 850001,
    "confidence": 0.99,
    "evaluation_family_size": 100,
    "mc_job_count": 84,
    "structural_job_count": 16,
    "reference_count": 19,
    "baseline_run_count": 600,
    "current_run_count": 900,
    "allowed_protocol_changes": ["oracle.validation_samples"],
    "recompute_from_connection": 0,
    "reuse_original_checkpoints": False,
    "stop_rule": "complete the one fixed target for every job; no performance-based stopping or further N search",
    "scope": "post-result development precision analysis; same-seed prefix, not independent replication",
    "additional_simultaneous_coverage_claim": False,
}


def equal(actual, expected, label):
    if bench.canonical(actual) != bench.canonical(expected):
        raise ValueError(f"learning precision {label} differs")


def check_sources():
    equal(bench.file_hash(PATH), IMPORTED_SHA256, "loaded wrapper source")
    equal(bench.file_hash(reporting.PATH), REPORTER_SHA256, "frozen reporter source")
    equal(reporting.IMPORTED_SHA256, REPORTER_SHA256, "loaded reporter source")
    reporting.check_reporter()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def merge_inputs(*inventories):
    result = {}
    for inventory in inventories:
        for path, sha in inventory.items():
            if path in result:
                equal(result[path], sha, f"conflicting input {path}")
            result[path] = sha
    return dict(sorted(result.items()))


def effective_protocol(base):
    equal(base["oracle"]["validation_samples"], CONTRACT["original_validation_samples"], "original N")
    equal(base["oracle"]["validation_seed"], CONTRACT["validation_seed"], "validation seed")
    equal(base["oracle"]["confidence"], CONTRACT["confidence"], "MC confidence")
    result = copy.deepcopy(base)
    result["oracle"]["validation_samples"] = CONTRACT["validation_samples"]
    return result


def validate_effective_protocol(base, actual):
    equal(actual, effective_protocol(base), "only the fixed validation_samples may change")
    equal(bench.all_contexts(actual), bench.all_contexts(base), "unchanged contexts")


def result_partition(manifest, tables):
    expected = {(job["context_id"], tuple(job["action"])) for job in manifest["jobs"]}
    equal(sorted(tables), sorted(expected), "complete result keys")
    result = {"mc": [], "structural": []}
    for job in manifest["jobs"]:
        value = tables[job["context_id"], tuple(job["action"])]
        method = value.get("method")
        if method == "structural_zero_loss_pair":
            category = "structural"
        elif method == "independent_paired_validation":
            category = "mc"
        else:
            raise ValueError("learning precision unknown action result method")
        result[category].append(job["job_id"])
    result = {key: sorted(value) for key, value in result.items()}
    equal(len(result["mc"]), CONTRACT["mc_job_count"], "MC job count")
    equal(len(result["structural"]), CONTRACT["structural_job_count"], "structural job count")
    return result


def validate_original_publication(publication, original_report, report_path, family_path, family_sha, metadata, loaded):
    protocol, baseline, current, references, provenance = loaded
    for key, value in {"schema": reporting.PUBLICATION_SCHEMA, "status": "complete",
                       "family_plan_path": str(family_path), "family_plan_sha256": family_sha,
                       "reporter_sha256": REPORTER_SHA256,
                       "input_inventory_sha256": bench.digest(metadata["inputs_sha256"]),
                       "execution_content_sha256": bench.digest(metadata)}.items():
        equal(publication.get(key), value, f"original publication {key}")
    if type(publication.get("published_ns")) is not int or publication["published_ns"] <= 0:
        raise ValueError("learning precision invalid original publication time")
    artifacts = publication.get("artifacts_sha256")
    if not isinstance(artifacts, dict) or len(artifacts) != 2 or artifacts.get(str(report_path)) != ORIGINAL_REPORT_SHA256:
        raise ValueError("learning precision original report artifact binding differs")
    markdown_paths = [Path(path) for path in artifacts if path != str(report_path)]
    if len(markdown_paths) != 1 or markdown_paths[0].suffix != ".md":
        raise ValueError("learning precision original Markdown artifact differs")
    reporting.check_files(artifacts)
    for key, value in {"schema": reporting.REPORT_SCHEMA, "status": "complete", "missing": [],
                       "missing_raw_groups": [], "evaluation_family_size": CONTRACT["evaluation_family_size"],
                       "analysis_aliases": reporting.ALIASES,
                       "comparison_plan": [list(pair) for pair in reporting.PAIRS]}.items():
        equal(original_report.get(key), value, f"original report {key}")
    origin = original_report["provenance"]
    for key, value in {"family_plan_path": str(family_path), "family_plan_sha256": family_sha,
                       "reporter_sha256": REPORTER_SHA256, "frozen_sources": reporting.FROZEN_SOURCES,
                       "learning_inputs": provenance}.items():
        equal(origin.get(key), value, f"original provenance {key}")
    equal(publication.get("pool_attestation_sha256"), bench.digest(origin["action_pool"]), "original pool attestation digest")
    equal(len(baseline), CONTRACT["baseline_run_count"], "baseline run count")
    equal(len(current), CONTRACT["current_run_count"], "current run count")
    equal(len(references), CONTRACT["reference_count"], "original reference count")
    reporting.analysis_runs(protocol, baseline, current)
    return artifacts


def load_original(family_path, family_sha, report_path, decision_path):
    check_sources()
    family_path = Path(family_path).resolve(strict=True)
    report_path = Path(report_path).resolve(strict=True)
    decision_path = Path(decision_path).resolve(strict=True)
    publication_path = Path(str(report_path) + ".published.json").resolve(strict=True)
    equal(family_sha, ORIGINAL_FAMILY_SHA256, "pinned original family")
    for path, sha in ((family_path, family_sha), (report_path, ORIGINAL_REPORT_SHA256),
                      (publication_path, ORIGINAL_PUBLICATION_SHA256)):
        equal(bench.file_hash(path), sha, f"original file {path}")
    if decision_path.suffix != ".md" or not decision_path.read_text(encoding="utf-8").strip():
        raise ValueError("learning precision a nonempty decision Markdown is required")
    decision_sha = bench.file_hash(decision_path)
    manifest, metadata, loaded = reporting.execution_plan(family_path, family_sha)
    equal(metadata["protocol_sha256"], ORIGINAL_PROTOCOL_SHA256, "original protocol identity")
    equal(manifest["evaluation_family_size"], CONTRACT["evaluation_family_size"], "original full family")
    publication, original_report = pool.read_json(publication_path), pool.read_json(report_path)
    artifacts = validate_original_publication(publication, original_report, report_path, family_path, family_sha, metadata, loaded)
    old_attestation = original_report["provenance"]["action_pool"]
    old_pool = Path(old_attestation["pool_path"]).resolve(strict=True)
    equal(str(old_pool), old_attestation["pool_path"], "original pool normalized path")
    with pool.exclusive_lock(old_pool / "pool.lock"):
        tables, attestation = reporting.validate_pool_locked(old_pool, manifest, metadata)
        equal(attestation, old_attestation, "original published pool attestation")
        partition = result_partition(manifest, tables)
        reporting.check_files(attestation["files_sha256"])
    protocol, baseline, current, references, provenance = loaded
    effective_protocol(protocol)
    sources = {str(family_path): family_sha, str(report_path): ORIGINAL_REPORT_SHA256,
               str(publication_path): ORIGINAL_PUBLICATION_SHA256, str(decision_path): decision_sha,
               str(PATH): IMPORTED_SHA256}
    inputs = merge_inputs(metadata["inputs_sha256"], artifacts, attestation["files_sha256"], sources)
    reporting.check_files(inputs)
    check_sources()
    return {"manifest": manifest, "metadata": metadata, "loaded": loaded,
            "family_path": str(family_path), "family_sha256": family_sha,
            "report_path": str(report_path), "report_sha256": ORIGINAL_REPORT_SHA256,
            "publication_path": str(publication_path), "publication_sha256": ORIGINAL_PUBLICATION_SHA256,
            "decision_path": str(decision_path), "decision_sha256": decision_sha,
            "pool_path": str(old_pool), "pool_attestation_sha256": bench.digest(attestation),
            "partition": partition, "inputs_sha256": inputs}


def build_plan(original, effective_path):
    protocol = original["loaded"][0]
    effective = effective_protocol(protocol)
    effective_path = Path(effective_path).resolve()
    effective_sha = hashlib.sha256(json_bytes(effective)).hexdigest()
    manifest = copy.deepcopy(original["manifest"])
    manifest["protocol_sha256"] = effective_sha
    bench_oracles.validate_oracle_manifest(manifest, protocol_hash=effective_sha, mode="actions")
    inputs = merge_inputs(original["inputs_sha256"], {str(effective_path): effective_sha})
    lineage_keys = ("family_path", "family_sha256", "report_path", "report_sha256", "publication_path",
                    "publication_sha256", "decision_path", "decision_sha256", "pool_path", "pool_attestation_sha256")
    plan = {"schema": PLAN_SCHEMA, "contract": copy.deepcopy(CONTRACT),
            "original": {key: original[key] for key in lineage_keys},
            "base_protocol_path": original["metadata"]["protocol_path"],
            "base_protocol_sha256": original["metadata"]["protocol_sha256"],
            "effective_protocol_path": str(effective_path), "effective_protocol_sha256": effective_sha,
            "contexts_sha256": bench.digest(bench.all_contexts(protocol)), "manifest": manifest,
            "result_partition": original["partition"], "inputs_sha256": inputs,
            "wrapper_sha256": IMPORTED_SHA256, "reporter_sha256": REPORTER_SHA256,
            "frozen_sources": reporting.FROZEN_SOURCES,
            "reference_lineage": {"protocol_sha256": original["metadata"]["protocol_sha256"],
                                  "oracle_digests": original["manifest"]["oracle_digests"],
                                  "retagged": False, "reevaluated": False},
            "analysis_aliases": reporting.ALIASES, "comparisons": [list(pair) for pair in reporting.PAIRS]}
    return copy.deepcopy(plan), effective


def plan_publication(plan, path, sha):
    return {"schema": PLAN_PUBLICATION_SCHEMA, "status": "complete", "precision_plan_path": str(path),
            "precision_plan_sha256": sha, "wrapper_sha256": IMPORTED_SHA256,
            "artifacts_sha256": {str(path): sha, plan["effective_protocol_path"]: plan["effective_protocol_sha256"]},
            "input_inventory_sha256": bench.digest(plan["inputs_sha256"]),
            "original_publication_sha256": plan["original"]["publication_sha256"]}


def freeze_plan(family_path, family_sha, report_path, decision_path, effective_path, out):
    out, effective_path = Path(out).resolve(), Path(effective_path).resolve()
    publication_path = Path(str(out) + ".published.json")
    destinations = (out, effective_path, publication_path)
    if len(set(destinations)) != len(destinations) or any(path.exists() for path in destinations):
        raise ValueError("learning precision plan outputs must be distinct new files")
    original = load_original(family_path, family_sha, report_path, decision_path)
    plan, effective = build_plan(original, effective_path)
    reporting.check_files(original["inputs_sha256"])
    check_sources()
    bench.write_new(effective_path, effective)
    equal(bench.file_hash(effective_path), plan["effective_protocol_sha256"], "written effective protocol")
    bench.write_new(out, plan)
    reporting.check_files(plan["inputs_sha256"])
    check_sources()
    sha = bench.file_hash(out)
    bench.write_new(publication_path, {**plan_publication(plan, out, sha), "published_ns": time.time_ns()})
    return plan


def execution_plan(plan_path, plan_sha):
    check_sources()
    plan_path = Path(plan_path).resolve(strict=True)
    equal(bench.file_hash(plan_path), plan_sha, "precision plan SHA")
    saved = pool.read_json(plan_path)
    equal(saved.get("schema"), PLAN_SCHEMA, "plan schema")
    equal(saved.get("contract"), CONTRACT, "fixed precision contract")
    publication_path = Path(str(plan_path) + ".published.json")
    publication = pool.read_json(publication_path)
    if type(publication.get("published_ns")) is not int or publication["published_ns"] <= 0:
        raise ValueError("learning precision invalid plan publication time")
    equal({key: value for key, value in publication.items() if key != "published_ns"},
          plan_publication(saved, plan_path, plan_sha), "plan publication")
    reporting.check_files(publication["artifacts_sha256"])
    reporting.check_files(saved["inputs_sha256"])
    origin = saved["original"]
    original = load_original(origin["family_path"], origin["family_sha256"], origin["report_path"], origin["decision_path"])
    rebuilt, effective = build_plan(original, saved["effective_protocol_path"])
    equal(saved, rebuilt, "reconstructed complete precision plan")
    actual_protocol = bench.load_protocol(Path(saved["effective_protocol_path"]))
    validate_effective_protocol(original["loaded"][0], actual_protocol)
    equal(actual_protocol, effective, "evaluation protocol")
    manifest = saved["manifest"]
    inputs = merge_inputs(saved["inputs_sha256"], {str(plan_path): plan_sha,
                          str(publication_path): bench.file_hash(publication_path)})
    metadata = {"schema": pool.SCHEMA, "adapter_sha256": reporting.FROZEN_SOURCES["bench_action_pool.py"],
                "manifest_sha256": bench.digest(manifest), "protocol_path": saved["effective_protocol_path"],
                "protocol_sha256": saved["effective_protocol_sha256"], "family_plan_path": str(plan_path),
                "family_plan_sha256": plan_sha, "source_sha256": manifest["source_sha256"],
                "inputs_sha256": inputs, "contexts_sha256": saved["contexts_sha256"],
                "precision_schema": PLAN_SCHEMA, "precision_contract": saved["contract"],
                "wrapper_sha256": IMPORTED_SHA256, "reporter_sha256": REPORTER_SHA256,
                "base_protocol_sha256": saved["base_protocol_sha256"], "original": saved["original"],
                "reference_lineage": saved["reference_lineage"], "result_partition": saved["result_partition"]}
    pool._check_sources(metadata)
    pool._check_inputs(metadata)
    check_sources()
    return manifest, metadata, original["loaded"]


def check_pool_destination(out, metadata):
    out = Path(out).resolve()
    original = Path(metadata["original"]["pool_path"]).resolve()
    if out.is_relative_to(original) or original.is_relative_to(out):
        raise ValueError("learning precision output overlaps the original pool")
    return out


def run_precision(plan_path, plan_sha, out, *, workers=2, time_budget_seconds=300.0, resume=False, loop=False):
    if type(workers) is not int or not 1 <= workers <= 8:
        raise ValueError("learning precision requires 1 to 8 workers")
    manifest, metadata, _ = execution_plan(plan_path, plan_sha)
    out = check_pool_destination(out, metadata)
    result = pool.run_pool(out, manifest, metadata, workers=workers, time_budget_seconds=time_budget_seconds,
                           resume=resume, loop=loop)
    check_sources()
    pool._check_inputs(metadata)
    return result


def aggregate_precision(loaded, tables, trace_loader=reporting.bench_report.load_trace):
    protocol, baseline, current, references, _ = loaded
    result = reporting.aggregate_learning(protocol, baseline, current, references, tables, trace_loader=trace_loader)
    if result.get("status") != "complete" or result.get("missing") != [] or result.get("missing_raw_groups") != []:
        raise ValueError("learning precision incomplete aggregate cannot be published")
    result["schema"] = REPORT_SCHEMA
    result["precision_scope"] = copy.deepcopy(CONTRACT)
    return result


def markdown(result):
    prefix = ("# L1 고정 N 정밀화 추가 보고\n\n"
              "기존 결과를 본 뒤 계획한 개발 정밀화다. 원래 보고서를 보존하며 독립 재현으로 해석하지 않는다.\n"
              "전체 100행동 중 84개 MC는 N=1048576, 16개 구조적 계산은 n=0이다. "
              "seed 850001의 기존 prefix를 다시 포함하며 새 동시 신뢰 보장을 주장하지 않는다.\n"
              "모든 seed별 기대 차이는 새 MC 평균으로 다시 집계했다. 실현 HCT·관측 궤적과 원래 선택 참조는 그대로다.\n\n")
    return prefix + reporting.markdown(result)


def final_report(plan_path, plan_sha, pool_dir, out, markdown_path):
    pool_dir = Path(pool_dir).resolve(strict=True)
    manifest, metadata, loaded = execution_plan(plan_path, plan_sha)
    check_pool_destination(pool_dir, metadata)
    destinations = [Path(out).resolve(), Path(markdown_path).resolve()]
    publication_path = Path(str(destinations[0]) + ".published.json")
    all_destinations = destinations + [publication_path]
    if len(set(all_destinations)) != len(all_destinations) or any(path.exists() or path.is_relative_to(pool_dir) for path in all_destinations):
        raise ValueError("learning precision report outputs must be distinct new files outside the pool")
    with pool.exclusive_lock(pool_dir / "pool.lock"):
        pool._check_sources(metadata)
        pool._check_inputs(metadata)
        tables, attestation = reporting.validate_pool_locked(pool_dir, manifest, metadata)
        equal(result_partition(manifest, tables), metadata["result_partition"], "unchanged structural job partition")
        result = aggregate_precision(loaded, tables)
        result["evaluation_family_size"] = manifest["evaluation_family_size"]
        result["provenance"] = {"precision_plan_path": str(Path(plan_path).resolve()), "precision_plan_sha256": plan_sha,
                                "wrapper_sha256": IMPORTED_SHA256, "reporter_sha256": REPORTER_SHA256,
                                "original": metadata["original"], "base_protocol_sha256": metadata["base_protocol_sha256"],
                                "evaluation_protocol_path": metadata["protocol_path"],
                                "evaluation_protocol_sha256": metadata["protocol_sha256"],
                                "reference_lineage": metadata["reference_lineage"],
                                "learning_inputs": loaded[4], "action_pool": attestation,
                                "result_partition": metadata["result_partition"], "frozen_sources": reporting.FROZEN_SOURCES}
        check_sources()
        pool._check_sources(metadata)
        pool._check_inputs(metadata)
        reporting.check_files(attestation["files_sha256"])
        bench.write_new(destinations[0], result)
        destinations[1].parent.mkdir(parents=True, exist_ok=True)
        with destinations[1].open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(markdown(result))
        check_sources()
        pool._check_sources(metadata)
        pool._check_inputs(metadata)
        reporting.check_files(attestation["files_sha256"])
        bench.write_new(publication_path, {"schema": PUBLICATION_SCHEMA, "status": "complete", "published_ns": time.time_ns(),
                         "artifacts_sha256": {str(path): bench.file_hash(path) for path in destinations},
                         "precision_plan_path": str(Path(plan_path).resolve()), "precision_plan_sha256": plan_sha,
                         "input_inventory_sha256": bench.digest(metadata["inputs_sha256"]),
                         "pool_attestation_sha256": bench.digest(attestation), "execution_content_sha256": bench.digest(metadata),
                         "wrapper_sha256": IMPORTED_SHA256, "reporter_sha256": REPORTER_SHA256,
                         "original_publication_sha256": metadata["original"]["publication_sha256"]})
        return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--original-family", type=Path, required=True)
    plan.add_argument("--original-family-sha256", required=True)
    plan.add_argument("--original-report", type=Path, required=True)
    plan.add_argument("--decision", type=Path, required=True)
    plan.add_argument("--effective-protocol", type=Path, required=True)
    plan.add_argument("--out", type=Path, required=True)
    run = commands.add_parser("run")
    report = commands.add_parser("report")
    for command in (run, report):
        command.add_argument("--precision-plan", type=Path, required=True)
        command.add_argument("--precision-plan-sha256", required=True)
        command.add_argument("--out", type=Path, required=True)
    run.add_argument("--workers", type=int, default=2)
    run.add_argument("--time-budget-seconds", type=float, default=300.0)
    run.add_argument("--resume", action="store_true")
    run.add_argument("--loop", action="store_true")
    report.add_argument("--pool", type=Path, required=True)
    report.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "plan":
        result = freeze_plan(args.original_family, args.original_family_sha256, args.original_report,
                             args.decision, args.effective_protocol, args.out)
        summary = {"status": "complete", "out": str(args.out.resolve()), "sha256": bench.file_hash(args.out),
                   "publication_receipt": str(Path(str(args.out.resolve()) + ".published.json")),
                   "effective_protocol": result["effective_protocol_path"], "effective_protocol_sha256": result["effective_protocol_sha256"],
                   "evaluation_family_size": result["manifest"]["evaluation_family_size"], "contract": result["contract"]}
    elif args.command == "run":
        summary = run_precision(args.precision_plan, args.precision_plan_sha256, args.out, workers=args.workers,
                                time_budget_seconds=args.time_budget_seconds, resume=args.resume, loop=args.loop)
    else:
        result = final_report(args.precision_plan, args.precision_plan_sha256, args.pool, args.out, args.markdown)
        summary = {"status": result["status"], "out": str(args.out.resolve()), "sha256": bench.file_hash(args.out),
                   "publication_receipt": str(Path(str(args.out.resolve()) + ".published.json")),
                   "evaluation_family_size": result["evaluation_family_size"], "noninferiority": result["noninferiority"]}
    print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), flush=True)
    return 0 if summary["status"] == "complete" else 2 if summary["status"] == "failed" else 3


if __name__ == "__main__":
    raise SystemExit(main())
