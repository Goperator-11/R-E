"""Read-only run provenance check; never imports or executes the experiment runner."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inside(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Path outside source root: {relative}")
    return path


def declared_stages(source):
    found = {}
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "Stage"):
            continue
        sid = ast.literal_eval(node.args[0])
        if sid in found:
            raise ValueError(f"Duplicate stage: {sid}")
        output_node = next(k.value for k in node.keywords if k.arg == "outputs")
        outputs = ast.literal_eval(output_node)
        if not isinstance(outputs, list) or not all(isinstance(x, str) for x in outputs):
            raise ValueError(f"Nonliteral output declaration: {sid}")
        found[sid] = outputs
    if not found:
        raise ValueError("No stages declared")
    return found


def classify_stage(sid, outputs, state, runtime, started, snapshot):
    rec = state.get("stages", {}).get(sid, {})
    row = {"stage": sid, "runner_status": rec.get("status"),
           "finished": rec.get("finished"), "recorded_fingerprint": rec.get("fingerprint"),
           "outputs": [], "issues": [], "classification": "pending_or_historical"}
    try:
        finished = datetime.strptime(rec.get("finished", ""), "%Y-%m-%d %H:%M")
    except ValueError:
        return row
    # Runner timestamps have minute resolution; compare at the same resolution.
    if finished < started.replace(second=0, microsecond=0):
        return row
    events = [e for e in state.get("history", []) if e.get("stage") == sid
              and e.get("at") == rec.get("finished")]
    if not events:
        row["issues"].append("missing_matching_run_event")
    elif events[-1].get("stale_deps"):
        row["issues"].append("stale_upstream_dependencies")
    expected = rec.get("output_hashes", {})
    if set(expected) != set(outputs):
        row["issues"].append("missing_or_extra_output_hashes")
    for relative in outputs:
        detail = {"path": relative, "expected_sha256": expected.get(relative)}
        try:
            path = inside(runtime, relative)
            before = path.stat()
            data = path.read_bytes()
            after = path.stat()
            detail.update(sha256=sha(data), bytes=len(data),
                          mtime_local=datetime.fromtimestamp(after.st_mtime).astimezone().isoformat())
            if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
                row["issues"].append(f"concurrent_output_change:{relative}")
            if detail["sha256"] != expected.get(relative):
                row["issues"].append(f"output_hash_mismatch:{relative}")
            if datetime.fromtimestamp(after.st_mtime) < started:
                row["issues"].append(f"historical_output:{relative}")
            # Preserve exactly the bytes examined, even if they show a discrepancy.
            destination = inside(snapshot, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        except (OSError, ValueError) as exc:
            row["issues"].append(f"unreadable_output:{relative}:{type(exc).__name__}")
        row["outputs"].append(detail)
    if row["issues"]:
        row["classification"] = "provenance_review_required"
    elif rec.get("status") == "done":
        if not events or events[-1].get("ok") is not True:
            row["classification"] = "provenance_review_required"
            row["issues"].append("inconsistent_success_event")
        else:
            row["classification"] = "current_run_runner_pass"
    else:
        row["classification"] = "current_run_not_passed"
    return row


def check_sources(manifest, repos):
    rows, seen = [], set()
    for entry in manifest:
        rel = entry["repo_path"]
        if rel in seen:
            raise ValueError(f"Duplicate source manifest path: {rel}")
        seen.add(rel)
        paths = [("source", Path(entry["source"]))]
        paths += [(f"repository_{i + 1}", inside(repo, rel)) for i, repo in enumerate(repos)]
        for label, path in paths:
            try:
                digest = sha(path.read_bytes())
            except OSError:
                digest = None
            rows.append({"repo_path": rel, "copy": label, "path": str(path),
                         "expected_sha256": entry["after_sha256"], "sha256": digest,
                         "matches": digest == entry["after_sha256"]})
    return rows


def run(args):
    runtime = args.runtime.resolve()
    root = args.output_dir.resolve()
    # Output locations cannot be placed inside any measured or distribution tree.
    for protected in [runtime, *args.repo]:
        if root.is_relative_to(protected.resolve()):
            raise ValueError("Audit output must be outside measurement and repository roots")
    stamp = datetime.now().astimezone()
    started = datetime.fromisoformat(args.started)
    if started.tzinfo is not None:
        started = started.astimezone().replace(tzinfo=None)
    snapshot = root / stamp.strftime("%Y%m%d_%H%M%S_%f")
    snapshot.mkdir(parents=True, exist_ok=False)
    runner_bytes = (runtime / "experiments/loop2.py").read_bytes()
    state_bytes = (runtime / "experiments/state/loop2.json").read_bytes()
    manifest_bytes = args.manifest.read_bytes()
    state = json.loads(state_bytes)
    declarations = declared_stages(runner_bytes)
    (snapshot / "loop2.json").write_bytes(state_bytes)
    (snapshot / "loop2.py.txt").write_bytes(runner_bytes)
    (snapshot / "source_manifest.json").write_bytes(manifest_bytes)
    rows = [classify_stage(sid, outputs, state, runtime, started, snapshot)
            for sid, outputs in declarations.items()]
    checks = check_sources(json.loads(manifest_bytes), args.repo)
    result = {
        "checked_at": stamp.isoformat(), "run_started_local": started.isoformat(),
        "runtime": str(runtime), "snapshot": str(snapshot),
        "state_sha256": sha(state_bytes), "runner_sha256": sha(runner_bytes),
        "source_manifest_sha256": sha(manifest_bytes),
        "state_changed_during_audit": sha((runtime / "experiments/state/loop2.json").read_bytes()) != sha(state_bytes),
        "counts": dict(Counter(r["classification"] for r in rows)),
        "source_manifest_entries": len(json.loads(manifest_bytes)),
        "source_copy_checks": len(checks),
        "source_copy_mismatches": sum(not r["matches"] for r in checks),
        "stages": rows, "source_checks": checks,
        "limits": [
            "Runner pass is not confirmation of every scientific hypothesis.",
            "The audit reads recorded fingerprints; it does not recompute the running process environment.",
            "Source comparison covers the supplied change manifest, not every dependency or binary.",
            "Pending stages may retain old success records; these are excluded from the current run.",
            "This snapshot neither starts nor stops experiments and performs no inferential reanalysis.",
        ],
    }
    result["all_stages_current_runner_pass"] = all(
        r["classification"] == "current_run_runner_pass" for r in rows)
    result["issues_present"] = bool(result["source_copy_mismatches"] or
        result["state_changed_during_audit"] or any(r["issues"] for r in rows))
    (snapshot / "audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ["checked_at", "snapshot", "counts",
        "source_manifest_entries", "source_copy_checks", "source_copy_mismatches",
        "all_stages_current_runner_pass", "issues_present"]}, ensure_ascii=False))
    return 1 if result["issues_present"] else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--repo", action="append", type=Path, default=[])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--started", required=True, help="ISO run start time, including local offset")
    parser.add_argument("--output-dir", type=Path, required=True)
    raise SystemExit(run(parser.parse_args()))
