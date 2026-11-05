import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
DEST = ROOT / "g3/v33/validation/L2_artifact_preparation"
assert not DEST.exists()
read = lambda path: json.loads(Path(path).read_text(encoding="utf-8"))
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
review = read(RUNS / "L2_artifact_check_review_v2.json")
assert review["status"] == "pass" and review["checker_sha256"] == sha(RUNS / "l2_joint_artifact_check_v2.py")
new_family, old_family = read(RUNS / "L2_joint_action_family_v1.json"), read(RUNS / "L1_action_family_v1.json")
assert new_family["manifest"]["jobs"] == old_family["manifest"]["jobs"]
assert new_family["manifest"]["oracle_digests"] == old_family["manifest"]["oracle_digests"]
names = ["l2_joint_artifact_check_v1.py", "l2_joint_artifact_check_v2.py", "l2_build_artifact_check_v1.py",
         "l2_artifact_check_review_v1.py", "l2_artifact_check_review_v2.py", "L2_artifact_check_review_v1_failure.json",
         "L2_artifact_check_review_v2.json", "l2_joint_plan_git_correction.py", "l2_joint_progress_v1.py",
         "L2_joint_progress_01.json", "L2_joint_run_launch_v1.json", "launch_l2_joint_report_v1.ps1",
         "iter017_checkpoint_03.py", "iter017_checkpoint_03.json", "l2_artifact_preparation_bundle.py"]
DEST.mkdir(parents=True)
entries = []
for name in names:
    source = RUNS / name
    raw = source.read_bytes()
    stored = raw.decode("utf-8").replace("\r\n", "\n").encode("utf-8")
    target = DEST / name
    with target.open("xb") as stream:
        stream.write(stored)
    entries.append({"source": str(source), "stored": name, "source_sha256": sha(source), "stored_sha256": sha(target),
                    "source_bytes": len(raw), "stored_bytes": len(stored)})
result = {"schema": "padfec.v33.l2_artifact_preparation/1", "entries": entries, "review": review,
          "joint_family_sha256": sha(RUNS / "L2_joint_action_family_v1.json"),
          "same_100_action_inventory_as_L1": True, "same_reference_digests_as_L1": True,
          "scope": "independent checker preparation while fixed MC runs; no new full performance inspection",
          "text_storage": "UTF-8 LF; original and stored bytes recorded separately"}
out = DEST / "manifest.json"
out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"files": len(entries), "manifest_sha256": sha(out)}))
