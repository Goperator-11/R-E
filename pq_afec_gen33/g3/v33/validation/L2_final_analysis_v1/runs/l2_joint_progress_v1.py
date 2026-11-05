import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path


RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
POOL = RUNS / "L2_joint_action_pool_v1"
FAMILY = RUNS / "L2_joint_action_family_v1.json"
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
read = lambda path: json.loads(Path(path).read_text(encoding="utf-8"))
assert sha(FAMILY) == "b793aa7df0a831195c2ba54d4f97fb0013c1792edf81946e58b3c00ae1249853"
family = read(FAMILY)
jobs = {row["job_id"] for row in family["manifest"]["jobs"]}
found = {path.stem for path in (POOL / "results").glob("*.json")}
assert found <= jobs
errors, states = [], []
for folder in ("runs", "attempts"):
    for path in sorted((POOL / folder).glob("*.finished.json")):
        value = read(path)
        if value["status"] not in ("partial", "complete") or value.get("unattested"):
            errors.append({"path": str(path), "status": value["status"], "error": value.get("error")})
        if folder == "runs":
            states.append({"path": str(path), "status": value["status"], "failed_jobs": value.get("failed_jobs", [])})
errors.extend({"path": str(path), "sha256": sha(path)} for path in (POOL / "failures").glob("*.json"))
end_path = RUNS / "L2_joint_run_v1.finished.json"
end = read(end_path) if end_path.exists() else None
result = {"schema": "padfec.v33.l2_joint_progress/1", "recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
          "family_sha256": sha(FAMILY), "expected_actions": len(jobs), "completed_result_files": len(found),
          "pending_actions": len(jobs - found), "errors": errors, "pool_states": states,
          "pool_manifest_exists": (POOL / "manifest.json").exists(), "root_finished": end is not None,
          "root_status": None if end is None else end["status"], "root_exit_code": None if end is None else end["exit_code"],
          "scope": "completion metadata only; no action-result performance values read", "script_sha256": sha(__file__)}
out = RUNS / sys.argv[1]
assert out.parent == RUNS and not out.exists()
with out.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps(result, ensure_ascii=False))
