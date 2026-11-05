import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
DEST = ROOT / "g3/v33/validation/J1_final_analysis_v1"
REPORT = ROOT / "g3/v33/J1_benchmark_v1.json"
CHECKER = RUNS / "j1_joint_artifact_check_v1.py"
CHECKER_SHA = "49854f577ac0fd344f78f93bb207cadb48144f3ee20cb948de1f7c4f89e1f390"
EXTRACTOR = RUNS / "j1_findings_extract_v1.py"
EXTRACTOR_SHA = "71a0763e3262fba7627a1bd7383cd88dabbc04623975d0094cc1b21d44dc51d2"
FAMILY_SHA = "8b60c0f75564545b2a40a4598454236082fa6fe58fbafb49f222995c51ceebfc"
read = lambda path: json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def main():
    assert not DEST.exists()
    assert sha(CHECKER) == CHECKER_SHA and sha(EXTRACTOR) == EXTRACTOR_SHA
    check_path = RUNS / "J1_joint_artifact_check_v1.json"
    check = read(check_path)
    assert check["status"] == "pass" and check["error"] is None and check["script_sha256"] == CHECKER_SHA
    assert check["summary"]["raw_runs"] == 3000 and check["summary"]["groups"] == 150 and check["summary"]["comparisons"] == 210
    verified = dict(check["files_sha256"])
    for path, expected in verified.items():
        assert sha(path) == expected, path
    family_path = RUNS / "J1_joint_action_family_v1.json"
    assert sha(family_path) == FAMILY_SHA
    family = read(family_path)
    findings = read(RUNS / "J1_findings_v1.json")
    assert findings["checker_sha256"] == sha(check_path)
    assert findings["report_sha256"] == sha(REPORT)
    assert findings["script_sha256"] == EXTRACTOR_SHA
    collection = read(RUNS / "J1_full_v1_plan.json")
    collection_end = read(RUNS / "J1_full_v1.finished.json")
    assert collection_end["status"] == "complete" and collection_end["jobs"] == 75
    for phase in ("plan", "run", "report"):
        receipt = read(RUNS / ("J1_joint_" + phase + "_v1.finished.json"))
        assert receipt["status"] == "complete" and receipt["exit_code"] == 0
    mandatory = [REPORT, Path(str(REPORT) + ".published.json"), RUNS / "J1_coverage.md", RUNS / "J1_disposition.md",
                 RUNS / "J1_findings_v1.json", RUNS / "J1_bench.md", check_path, CHECKER, EXTRACTOR, Path(__file__)]
    assert all(path.is_file() for path in mandatory)
    selected = set(mandatory)
    for pattern in ("J1_*", "j1_*.py", "launch_j1_*.ps1", "iter020_*", "iter021_*", "iter022_*"):
        selected.update(path for path in RUNS.glob(pattern) if path.is_file())
    pool = RUNS / "J1_joint_action_pool_v1"
    selected.update(path for path in pool.rglob("*") if path.is_file() and path.suffix != ".lock")
    raw_inventory = {}
    for job in collection["jobs"]:
        folder = Path(job["out"])
        for path in folder.rglob("*"):
            if not path.is_file() or path.suffix == ".lock":
                continue
            raw_inventory[str(path)] = {"sha256": sha(path), "bytes": path.stat().st_size,
                "storage": "retained_original_gzip_in_runs" if path.suffix == ".gz" else "copied_to_bundle"}
            if path.suffix != ".gz":
                selected.add(path)
    assert sum(item["storage"] == "retained_original_gzip_in_runs" for item in raw_inventory.values()) == 1500
    selected = {path.resolve(strict=True) for path in selected}
    assert all(path.is_relative_to(ROOT) or path.is_relative_to(RUNS) for path in selected)
    selected_hashes = {str(path): sha(path) for path in selected}
    DEST.mkdir(parents=True)
    entries = []
    for path in sorted(selected):
        relative = Path("runs") / path.relative_to(RUNS) if path.is_relative_to(RUNS) else Path("repo") / path.relative_to(ROOT)
        target = DEST / relative
        assert target.resolve().is_relative_to(DEST.resolve())
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == selected_hashes[str(path)]
        stored = raw.decode("utf-8-sig").replace("\r\n", "\n").encode("utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(stored)
        entries.append({"source": str(path), "stored": relative.as_posix(), "source_sha256": selected_hashes[str(path)],
                        "stored_sha256": hashlib.sha256(stored).hexdigest(), "source_bytes": len(raw), "stored_bytes": len(stored)})
    for path, value in raw_inventory.items():
        assert sha(path) == value["sha256"]
    for path, expected in selected_hashes.items():
        assert sha(path) == expected
    manifest = {"schema": "padfec.v33.j1_final_analysis_bundle/1", "created_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
                "entries": entries, "file_count": len(entries), "stored_bytes": sum(row["stored_bytes"] for row in entries),
                "raw_collection_inventory": raw_inventory, "verified_source_sha256": verified,
                "scope": "Completed development analysis evidence. Original1500 compressed traces remain in runs and are hash-bound, not duplicated into Git. Adoption is recorded in J1_disposition.md.",
                "family_sha256": FAMILY_SHA, "checker_sha256": CHECKER_SHA, "extractor_sha256": EXTRACTOR_SHA,
                "report_sha256": sha(REPORT), "script_sha256": sha(__file__), "text_storage": "UTF-8 LF with separate source/stored hashes"}
    out = DEST / "manifest.json"
    with out.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"files": len(entries), "stored_bytes": manifest["stored_bytes"], "raw_files": len(raw_inventory),
                      "retained_gzip_files": 1500, "manifest_sha256": sha(out)}))


if __name__ == "__main__":
    main()
