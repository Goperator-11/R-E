import argparse
import gzip
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import source_path, source_reference

FIELDS = {"est", "se", "df", "lo95", "hi95", "lb_holm", "reject", "category", "ratio"}
DENOMINATORS = {"n", "n_units", "n_planned", "n_returned", "missing", "blocks_planned", "blocks_done", "n_blocks"}
VERDICTS = {"pass", "claim", "evaluable", "complete", "verdicts_suspended", "status", "same_direction", "ok"}
IDENTITIES = {"cond", "contrast", "arm", "cell", "run", "block", "order", "positions", "precedence"}


def read_bytes(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as stream:
        return stream.read()


def read_json(path):
    return json.loads(read_bytes(path).decode("utf-8"))


def digest(path):
    return hashlib.sha256(read_bytes(path)).hexdigest()


def read_units(path, fingerprint, expected):
    records = {}
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except ValueError as exc:
                raise ValueError(f"partial journal: {path.name}:{number}") from exc
            if not isinstance(item, dict) or item.get("fp") != fingerprint or not isinstance(item.get("val"), dict):
                raise ValueError(f"invalid journal record: {path.name}:{number}")
            key = item.get("key")
            if key in records:
                raise ValueError(f"duplicate unit: {path.name}:{key}")
            if key not in expected:
                raise ValueError(f"unexpected unit: {path.name}:{key}")
            records[key] = item["val"]
    if set(records) != set(expected):
        raise ValueError(f"partial journal: {path.name}: missing {len(set(expected) - set(records))} units")
    return records


def output_path(path):
    path = path.resolve()
    if path.exists():
        raise FileExistsError("refusing to overwrite output: " + str(path))
    protected = [source_path(key).parents[1] for key in ("sealed_v30_module", "sealed_v31_module", "seal_stage0", "seal_stage3")]
    protected.append(source_path("archive_index").parent)
    if any(path == root or root in path.parents for root in protected):
        raise ValueError("output must not be inside a preserved source tree")
    if not path.parent.is_dir():
        raise FileNotFoundError("output parent must exist: " + str(path.parent))
    return path


def read_only_audit(event, args):
    if event == "open":
        mode, flags = args[1:3]
        if (isinstance(mode, str) and any(c in mode for c in "wax+")) or (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
            raise PermissionError("recompute worker cannot write")
    if event in {"os.mkdir", "os.remove", "os.rename", "os.rmdir", "os.chmod", "os.truncate", "subprocess.Popen", "os.system", "socket.connect", "socket.bind"}:
        raise PermissionError("recompute worker forbids " + event)


def load_module(path):
    def existing_directory(name, mode=0o777, exist_ok=False):
        if not exist_ok or not Path(name).is_dir():
            raise PermissionError("recompute import cannot create a directory")
    os.makedirs = existing_directory
    sys.path[:0] = [str(path.parent), str(path.parents[1])]
    spec = importlib.util.spec_from_file_location("sealed_comparison", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compare(expected, actual, path, items, errors, selected=False):
    if isinstance(expected, (dict, list)) and not isinstance(actual, type(expected)):
        errors.append(path + ": container type differs")
        return
    if isinstance(actual, dict):
        if not isinstance(expected, dict):
            errors.append(path + ": object type differs")
            return
        actual_keys = {str(key) for key in actual}
        for key in expected:
            if path == "decisions" and key in {"final_validation", "run2_final_validation", "h_predictions_check", "runs_used", "run2_excluded_reason"}:
                continue
            if key not in actual_keys:
                errors.append(path + "." + str(key) + ": missing recomputed value")
        for key, value in actual.items():
            key = str(key)
            chosen = selected or key in FIELDS | DENOMINATORS | VERDICTS | IDENTITIES or isinstance(value, (bool, int, float)) or isinstance(expected.get(key), (bool, int, float))
            if key not in expected:
                if chosen:
                    errors.append(path + "." + key + ": missing reference")
                continue
            compare(expected[key], value, path + "." + key, items, errors, chosen)
    elif isinstance(actual, list):
        if not isinstance(expected, list) or len(expected) != len(actual):
            errors.append(path + ": list length differs")
            return
        for index, value in enumerate(actual):
            compare(expected[index], value, f"{path}[{index}]", items, errors, selected)
    elif selected:
        numeric = type(actual) in (int, float) and type(expected) in (int, float)
        difference = abs(actual - expected) if numeric else None
        match = (math.isfinite(actual) and math.isfinite(expected) and difference < 1e-6) if numeric else type(actual) is type(expected) and actual == expected
        items.append({"path": path, "reference": expected, "recomputed": actual, "abs_diff": difference, "match": match})
        if not match:
            errors.append(path + ": value differs")


def worker(alias):
    sys.addaudithook(read_only_audit)
    module_path = source_path(alias)
    root = module_path.parents[1]
    module = load_module(module_path)
    prefix = getattr(module, "RESULT_PREFIX", "p21")
    items, errors, runs, inputs, provenance = [], [], [], [], {}
    for run in ("run1", "run2"):
        meta_path = root / "experiments/state" / f"{prefix}_{run}_meta.json"
        meta = read_json(meta_path)
        if meta.get("run") != run or not meta.get("finished") or not meta.get("starts"):
            raise ValueError("partial run metadata: " + str(meta_path))
        plan = meta["plan"]
        if plan.get("run") != run:
            raise ValueError("metadata plan run differs")
        names = [condition["cond"] for condition in plan["conds"]]
        if len(names) != len(set(names)):
            raise ValueError("duplicate condition in plan")
        summaries = []
        inputs.append({"path": meta_path.relative_to(root).as_posix(), "sha256": digest(meta_path)})
        for condition in plan["conds"]:
            name = condition["cond"]
            blocks = [block for block in plan["schedule"] if block["cond"] == name]
            expected = {module.unit_key(run, name, block["block"]): block for block in blocks}
            if not blocks or len(expected) != len(blocks):
                raise ValueError("empty or duplicate block schedule: " + name)
            path = root / "experiments/state" / f"{prefix}_{run}_{name}_units.jsonl.gz"
            if not path.is_file():
                path = path.with_suffix("")
            units = read_units(path, meta["fps"][name], expected)
            records = {}
            for key, block in expected.items():
                record = units[key]
                if any(record.get(field) != block.get(field) for field in ("cond", "block", "order", "sizes", "cycle", "stratum", "loss")) or not module.block_complete(record, block):
                    raise ValueError("partial or changed block: " + key)
                records[block["block"]] = record
            summary = module.summarize_cond(condition, blocks, records)
            module.add_final_block_bytes(summary, condition, blocks, records)
            if not summary["complete"]:
                raise ValueError("incomplete condition: " + name)
            summaries.append(summary)
            inputs.append({"path": path.relative_to(root).as_posix(), "sha256_uncompressed": digest(path), "units": len(units)})
        reference_path = root / "experiments/results" / f"{prefix}_gencompare_{run}.json"
        reference = read_json(reference_path)
        compare(reference["conds"], summaries, run + ".conds", items, errors)
        if reference["plan"] != plan:
            raise ValueError("preserved result plan differs: " + run)
        runs.append({"conds": summaries, "estimate": module.estimate(plan)})
        provenance[run] = {"env_starts": meta["starts"], "finished": meta["finished"], "seal_check": [start.get("seal_check") for start in meta["starts"]], "bins_sha256": [start.get("bins_sha256") for start in meta["starts"]]}
        inputs.append({"path": reference_path.relative_to(root).as_posix(), "sha256": digest(reference_path)})
    prediction_path = root / module.HPRED_REL
    predictions = read_json(prediction_path)
    seal_path = root / module.SEAL_REL
    seal = read_json(seal_path)
    if seal["sha256"][module.HPRED_REL] != digest(prediction_path):
        raise ValueError("prediction seal mismatch")
    seal_hash = digest(seal_path)
    if any(not start.get("seal_check", {}).get("ok") or start.get("seal_check", {}).get("sha256") != seal_hash for run in provenance.values() for start in run["env_starts"]):
        raise ValueError("run seal provenance differs")
    decisions = module.decide(runs[0], runs[1], predictions, label="confirmatory")
    reference_path = root / "experiments/results" / f"{prefix}_gencompare_decisions.json"
    reference = read_json(reference_path)
    compare(reference, decisions, "decisions", items, errors)
    if not items or not any(item["path"].startswith("decisions.") and item["path"].rsplit(".", 1)[-1] in FIELDS for item in items):
        raise ValueError("no verdict comparison items")
    for path in (prediction_path, seal_path, reference_path, module_path):
        inputs.append({"path": path.relative_to(root).as_posix(), "sha256": digest(path)})
    return {"source_alias": alias, "module": source_reference(alias), "independent": False, "method": "preserved summarize_cond, estimate and decide functions in an isolated read-only process; current environment and binaries are not checked", "inputs": inputs, "provenance": provenance, "items": items, "errors": errors, "known_display_diffs": [], "all_verdicts_match": not errors, "max_abs_diff_ms": max((item["abs_diff"] for item in items if item["abs_diff"] is not None), default=0.0)}


def verify_manifest():
    index_path = source_path("archive_index")
    index = read_json(index_path)
    entries = index["entries"]
    expected = "".join(entry["original_sha256"] + "  " + entry["logical_path"] + "\n" for entry in entries)
    if source_path("archive_manifest").read_text(encoding="utf-8") != expected:
        raise ValueError("archive manifest differs from index")
    roots = [source_path(alias).parents[1].relative_to(index_path.parent).as_posix() + "/" for alias in ("sealed_v30_module", "sealed_v31_module")]
    checked = []
    for entry in entries:
        if any(entry["logical_path"].startswith(root) for root in roots):
            path = index_path.parent / entry["archive_path"]
            if digest(path) != entry["original_sha256"]:
                raise ValueError("archive manifest mismatch: " + entry["logical_path"])
            checked.append(entry["logical_path"])
    if not checked:
        raise ValueError("archive manifest has no matching entries")
    return {"index_sha256": digest(index_path), "manifest_sha256": digest(source_path("archive_manifest")), "checked": len(checked), "mismatches": 0}


def rehash_seals():
    files = []
    for alias in ("seal_stage0", "seal_m1confirm", "seal_stage2", "seal_stage3"):
        path = source_path(alias)
        seal = read_json(path)
        for relative, expected in seal["sha256"].items():
            actual = digest(path.parents[1] / relative)
            files.append({"seal": alias, "path": relative, "expected": expected, "actual": actual, "match": actual == expected})
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "file_count": len(files), "mismatch_count": sum(not row["match"] for row in files), "files": files}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    parser.add_argument("--worker", choices=("sealed_v30_module", "sealed_v31_module"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args.worker), ensure_ascii=False, allow_nan=False))
        return 0
    if args.out is None:
        parser.error("--out must name a new output directory")
    out = output_path(args.out)
    manifest = verify_manifest()
    seals = rehash_seals()
    results = {}
    for alias in ("sealed_v30_module", "sealed_v31_module"):
        command = [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--worker", alias]
        process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8"))
        if process.returncode:
            raise RuntimeError(process.stderr.strip())
        results[alias] = json.loads(process.stdout)
    items = [dict(item, generation=alias) for alias, result in results.items() for item in result["items"]]
    result = {"schema": "v3_verdict_recompute/1", "generated_at": datetime.now(timezone.utc).isoformat(), "independent": False, "item_count": len(items), "items": items, "max_abs_diff_ms": max(value["max_abs_diff_ms"] for value in results.values()), "all_verdicts_match": all(value["all_verdicts_match"] for value in results.values()), "known_display_diffs": [], "archive_manifest": manifest, "generations": results}
    out.mkdir()
    for name, value in (("v3_verdict_recompute.json", result), ("seal_rehash.json", seals)):
        with (out / name).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"out": str(out), "items": len(items), "max_abs_diff_ms": result["max_abs_diff_ms"], "all_verdicts_match": result["all_verdicts_match"], "seal_files": seals["file_count"], "seal_mismatches": seals["mismatch_count"], "archive_entries": manifest["checked"]}, ensure_ascii=False))
    return 0 if result["all_verdicts_match"] and result["max_abs_diff_ms"] < 1e-6 and seals["file_count"] == 71 and seals["mismatch_count"] == 0 else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        raise SystemExit(1)
