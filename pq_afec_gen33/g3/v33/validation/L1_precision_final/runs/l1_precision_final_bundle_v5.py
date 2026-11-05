import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
OUT = ROOT / "g3/v33/validation/L1_precision_final"
REPORT = ROOT / "g3/v33/L1_benchmark_precision_v1.json"
POOL = RUNS / "L1_action_pool_precision_v2"
CHECKER = RUNS / "l1_precision_artifact_check_v4.py"
CHECKER_SHA = "a7504e1a2c94e54721077bbdaff068241da4e4274e17883eb5a7bab8f94aefd6"
EXTRACTOR = RUNS / "l1_precision_findings_extract_v4.py"
EXTRACTOR_SHA = "3a0d995c06120dde5e3c6e0c1a77f5476451dc7f31dd4841987461045ea1f504"
BOUND = {}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def bind(path, expected=None):
    path = Path(path).resolve(strict=True)
    require(path.is_file(), "source must be a file")
    require(any(path.is_relative_to(root) for root in (ROOT, RUNS, Path(r"C:\dev\pq_afec_gen31"), Path(r"C:\dev\pq_afec_gen32"))), "source is outside read-only verification roots")
    current = sha(path)
    require(expected is None or current == expected, "source SHA differs: " + str(path))
    require(path not in BOUND or BOUND[path] == current, "source changed during bundle: " + str(path))
    BOUND[path] = current
    return path


def read(path):
    path = bind(path)
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    bind(path)
    return value


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--iteration", type=int, required=True)
    args = parser.parse_args(argv)
    require(args.iteration >= 15, "iteration predates recovery")
    require(not OUT.exists(), "final bundle must be new")
    script_path = bind(__file__)
    receipts = {}
    for phase in ("run", "report"):
        path = RUNS / ("L1_precision_" + phase + "_v2.finished.json")
        receipt = read(path)
        require(receipt["status"] == "complete" and receipt["exit_code"] == 0, "phase incomplete: " + phase)
        require(receipt["driver_sha256"] == receipt["driver_sha256_after"], "driver changed")
        require(receipt["wrapper_sha256"] == receipt["wrapper_sha256_after"], "wrapper changed")
        bind(RUNS / "l1_precision_driver_v2.py", receipt["driver_sha256"])
        bind(ROOT / "experiments/v33/bench_learning_precision.py", receipt["wrapper_sha256"])
        bind(RUNS / ("L1_precision_" + phase + "_v2.started.json"), receipt["started_receipt_sha256"])
        for field in ("stdout", "stderr"):
            bind(receipt[field + "_path"], receipt[field + "_sha256"])
        for source, expected in receipt["published_outputs_sha256"].items():
            bind(source, expected)
        receipts[phase] = receipt
    require(receipts["run"]["recovery_identity"] == receipts["report"]["recovery_identity"], "recovery identity differs")
    require(receipts["report"]["preceding_run"]["path"] == str(RUNS / "L1_precision_run_v2.finished.json"), "report binds another run")
    bind(receipts["report"]["preceding_run"]["path"], receipts["report"]["preceding_run"]["sha256"])
    bind(CHECKER, CHECKER_SHA)
    bind(EXTRACTOR, EXTRACTOR_SHA)
    check_path = RUNS / "L1_precision_artifact_check_v4.json"
    check = read(check_path)
    require(check["status"] == "pass" and check["error"] is None, "artifact check has not passed")
    require(check["script_sha256"] == check["script_sha256_after"] == CHECKER_SHA, "checker binding differs")
    for key, expected in (("raw_seed_runs", 1500), ("references", 19), ("family", 100), ("groups", 75), ("comparisons", 105), ("MC_N", 1048576)):
        require(check["counts"][key] == expected, "artifact count differs: " + key)
    for path, expected in check["verified_files_sha256"].items():
        bind(path, expected)
    findings = read(RUNS / "L1_precision_findings_extract_v4.json")
    require(findings["script_sha256"] == EXTRACTOR_SHA, "extractor binding differs")
    require(findings["artifact_check"]["sha256"] == sha(check_path), "extraction binds another check")
    for path, expected in findings["inputs_sha256"].items():
        bind(path, expected)
    marker_path = Path(str(REPORT) + ".published.json")
    marker, report = read(marker_path), read(REPORT)
    require(marker["status"] == report["status"] == "complete", "publication incomplete")
    require(not report["missing"] and not report["missing_raw_groups"], "publication has missing data")
    require(report["evaluation_family_size"] == 100, "family size differs")
    require(report["provenance"]["action_pool"]["pool_path"] == str(POOL), "publication binds another pool")
    for path, expected in marker["artifacts_sha256"].items():
        bind(path, expected)
    pool_files = {path.resolve(strict=True) for path in POOL.rglob("*") if path.is_file() and path.suffix != ".lock"}
    for path in pool_files:
        bind(path)
    names = ["L1_precision_acceptance_scope.md", "L1_precision_disposition.md", "L1_coverage.md",
             "E5_coverage.md", "E6_coverage.md", "L1_precision_artifact_review_v4.md", "L1_precision_checker_root_review.md",
             "L1_precision_findings_extract_v4.json", "L1_precision_artifact_check_v4.json", "L1_precision_interruption_v1.json",
             "L1_precision_recovery.md", "L1_precision_launch_v2.json", "l1_precision_final_bundle_v5.py"]
    names.extend([
        "l1_precision_artifact_check_v2.py", "l1_precision_artifact_check_v3.py",
        "L1_precision_artifact_check.json", "L1_precision_artifact_check_v3.json",
        "L1_precision_artifact_review.md", "L1_precision_artifact_review_v3.md",
        "l1_precision_checker_v3_patch_check.py", "L1_precision_checker_v3_patch_check.json",
        "l1_precision_checker_v4_patch_check.py", "L1_precision_checker_v4_patch_check.json",
        "L1_precision_checker_correction.md", "L1_precision_bundle_correction.md", "l1_precision_final_bundle_v4.py", "L1_precision_coverage_draft.md",
        "launch_l1_precision_report_v2.ps1", "L1_precision_report_launch_v2.json",
        "L1_precision_report_launcher_v2.stdout.txt", "L1_precision_report_launcher_v2.stderr.txt",
        "iter016_start.py", "iter016_preflight.json", "iter016_sources.txt",
        "L1_precision_v2_progress_11.json", "coverage_iter016_final.json"
    ])
    selected = pool_files | {REPORT, marker_path, CHECKER, EXTRACTOR}
    selected.update(RUNS / name for name in names)
    selected.update(Path(path) for path in marker["artifacts_sha256"])
    for phase in ("run", "report"):
        selected.update(RUNS / ("L1_precision_" + phase + "_v2" + ending) for ending in (".started.json", ".finished.json", ".stdout.txt", ".stderr.txt"))
    prior_bundles = {}
    for name in ("L1_final", "L1_precision_plan", "L1_precision_recovery", "L1_precision_checker", "L1_precision_report_launcher_preparation"):
        path = bind(ROOT / "g3/v33/validation" / name / "bundle_manifest.json")
        prior_bundles[str(path)] = BOUND[path]
        selected.add(path)
    selected = {bind(path) for path in selected}
    require(all(path.is_relative_to(ROOT) or path.is_relative_to(RUNS) for path in selected), "copy sources must be current repository or v33 runs")
    locations = {}
    for path in sorted(selected):
        relative = Path("runs") / path.relative_to(RUNS) if path.is_relative_to(RUNS) else Path("repo") / path.relative_to(ROOT)
        require(relative.as_posix() not in locations, "duplicate bundle destination")
        require((OUT / relative).resolve().is_relative_to(OUT.resolve()), "destination escapes bundle")
        locations[relative.as_posix()] = path
    OUT.mkdir(parents=True, exist_ok=False)
    entries = []
    for relative, path in sorted(locations.items()):
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == BOUND[path], "source changed before copy")
        stored = ("\n".join(line.rstrip() for line in raw.decode("utf-8-sig").splitlines()).rstrip("\n") + "\n").encode("utf-8") if raw else b""
        destination = OUT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(stored)
        require(sha(destination) == hashlib.sha256(stored).hexdigest(), "stored bytes differ")
        entries.append({"source": str(path), "repository_file": relative, "source_sha256": BOUND[path],
                        "stored_sha256": sha(destination), "stored_bytes": len(stored)})
    require(pool_files == {path.resolve(strict=True) for path in POOL.rglob("*") if path.is_file() and path.suffix != ".lock"}, "pool file set changed")
    for path, expected in BOUND.items():
        require(sha(path) == expected, "verified source changed before bundle publication: " + str(path))
    manifest = {"schema": "padfec.v33.learning_precision_final_bundle/1", "iteration": args.iteration,
                "recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
                "status": "validated_precision_evidence_preserved_see_disposition_for_acceptance",
                "script_sha256": BOUND[script_path], "publication_sha256": sha(marker_path), "artifact_check_sha256": sha(check_path),
                "normalization": "UTF-8 LF and trailing line whitespace removed; exact source SHA retained",
                "scope": "New precision pool and final artifacts; prior raw data and recovery evidence remain linked by verified source inventories and existing repository bundles",
                "prior_bundle_manifests_sha256": prior_bundles,
                "verified_sources_sha256": {str(path): value for path, value in sorted(BOUND.items())}, "files": entries}
    with (OUT / "bundle_manifest.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"out": str(OUT), "files": len(entries), "stored_bytes": sum(item["stored_bytes"] for item in entries),
                      "manifest_sha256": sha(OUT / "bundle_manifest.json")}), flush=True)


if __name__ == "__main__":
    main()
