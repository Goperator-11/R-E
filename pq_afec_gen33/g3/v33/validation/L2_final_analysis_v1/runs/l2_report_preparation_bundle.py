import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
DEST = ROOT / "g3/v33/validation/L2_report_preparation"
assert not DEST.exists()
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
finish = json.loads((RUNS / "L2_full_v1.finished.json").read_text(encoding="utf-8"))
assert finish["status"] == "complete" and finish["error"] is None and finish["jobs"] == finish["expected_jobs"] == 75
assert all(row["status"] == "complete" and row["exit_code"] == 0 for row in finish["results"])
names = ["l2_joint_driver_v1.py", "l2_report_check.py", "l2_report_preparation_bundle.py", "l2_collection_status.py",
         "L2_report_check_01.json", "L2_report_check_01.log", "L2_report_check_02.json", "L2_report_check_02.log",
         "L2_collection_progress_02.json", "L2_collection_progress_03.json", "L2_collection_progress_04.json",
         "L2_full_v1.started.json", "L2_full_v1.finished.json", "L2_collection_launch_v1.json"]
names += ["L2_raw_v1_" + f"{i:02d}" + suffix for i in range(1, 76) for suffix in (".started.json", ".finished.json", ".stdout.txt", ".stderr.txt")]
DEST.mkdir(parents=True)
entries = []
for name in names:
    src, dst = RUNS / name, DEST / name
    source = src.read_bytes()
    content = source.decode("utf-8").replace("\r\n", "\n").encode("utf-8")
    with dst.open("xb") as stream:
        stream.write(content)
    entries.append({"source": str(src), "stored": name, "source_sha256": sha(src), "stored_sha256": sha(dst),
                    "source_bytes": len(source), "stored_bytes": len(content)})
manifest = {"schema": "padfec.v33.l2_report_preparation/1", "entries": entries, "file_count": len(entries),
            "scope": "reporter and driver validation, completed collection receipts; raw performance not inspected",
            "tests": {"passed": 38, "subtests": 47}, "collection": {"completed_shards": 75, "seed_runs": 1500},
            "text_storage": "UTF-8 LF, source and stored byte hashes recorded separately", "script_sha256": sha(__file__)}
out = DEST / "manifest.json"
out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"files": len(entries), "manifest_sha256": sha(out)}))
