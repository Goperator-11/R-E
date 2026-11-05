import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
DEST = ROOT / "g3/v33/validation/L2_interpretation_preparation"
assert not DEST.exists()
assert not (ROOT / "g3/v33/L2_benchmark_v1.json").exists()
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
read = lambda path: json.loads(Path(path).read_text(encoding="utf-8"))
review = read(RUNS / "L2_findings_extract_review_v2.json")
assert review["status"] == "pass" and review["extractor_sha256"] == sha(RUNS / "l2_findings_extract_v2.py")
historical = read(RUNS / "L2_historical_current_v2.json")
assert historical["status"] == "pass"
names = ["l2_findings_extract_v1.py", "l2_findings_extract_v2.py", "l2_findings_extract_review_v1.py", "l2_findings_extract_review_v2.py",
         "L2_findings_extract_review_v1.json", "L2_findings_extract_review_v2.json", "L2_extraction_scope_correction.md",
         "l2_historical_current_prepare.py", "L2_historical_current_prepare.json", "l2_historical_current_v1.py", "l2_historical_current_v2.py",
         "L2_historical_current_v1_failure.json", "L2_historical_current_v2.json", "L2_historical_current_v2.md", "l2_historical_current_report.py",
         "L2_joint_progress_02.json", "L2_joint_progress_03.json", "L2_joint_progress_04.json", "L2_joint_report_launch_v1.json",
         "l2_final_bundle_v1.py", "l2_interpretation_preparation_bundle.py"]
names += ["L2_joint_run_v1" + suffix for suffix in (".started.json", ".finished.json", ".stdout.txt", ".stderr.txt")]
DEST.mkdir(parents=True)
entries = []
for name in names:
    src, dst = RUNS / name, DEST / name
    raw = src.read_bytes()
    stored = raw.decode("utf-8-sig").replace("\r\n", "\n").encode("utf-8")
    with dst.open("xb") as stream:
        stream.write(stored)
    entries.append({"source": str(src), "stored": name, "source_sha256": sha(src), "stored_sha256": sha(dst),
                    "source_bytes": len(raw), "stored_bytes": len(stored)})
value = {"schema": "padfec.v33.l2_interpretation_preparation/1", "recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
         "entries": entries, "source_plan_sha256": sha(ROOT / "docs/L2_benchmark_plan.md"),
         "report_file_absent_before_preparation": True, "performance_inspected": False,
         "scope": "Original30-cell before/after adoption scope preserved, all60 primary reporting cells retained; source-bound historical6777-row replay and interpretation tools prepared."}
out = DEST / "manifest.json"
with out.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(value, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps({"files": len(entries), "manifest_sha256": sha(out), "recorded_kst": value["recorded_kst"]}))
