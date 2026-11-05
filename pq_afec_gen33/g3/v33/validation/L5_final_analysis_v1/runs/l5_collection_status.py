import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path


RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
name = sys.argv[1]
assert name.startswith("L5_collection_progress_") and Path(name).name == name and name.endswith(".json")
destination = RUNS / name
assert not destination.exists()
plan_path = RUNS / "L5_full_v1_plan.json"
plan = json.loads(plan_path.read_text(encoding="utf-8"))
errors, jobs = [], []
for job in plan["jobs"]:
    folder = Path(job["out"])
    result_files = [path for path in folder.glob("*/*/seed*.json") if path.name.count(".") == 1]
    started = RUNS / (job["id"] + ".started.json")
    finished = RUNS / (job["id"] + ".finished.json")
    status, code = "pending", None
    if started.exists():
        status = "running"
    if finished.exists():
        receipt = json.loads(finished.read_text(encoding="utf-8"))
        status, code = receipt["status"], receipt["exit_code"]
        if status != "complete" or code != 0:
            errors.append({"job": job["id"], "receipt": str(finished), "error": receipt.get("error")})
    failures = list(folder.rglob("*.failed.json")) if folder.exists() else []
    for path in failures:
        value = json.loads(path.read_text(encoding="utf-8"))
        errors.append({"job": job["id"], "path": str(path), "error_type": value.get("error_type"), "error": value.get("error")})
    jobs.append({"id": job["id"], "status": status, "exit_code": code,
                 "completed_result_files": len(result_files), "failure_receipts": len(failures)})
root_path = RUNS / "L5_full_v1.finished.json"
root = json.loads(root_path.read_text(encoding="utf-8")) if root_path.exists() else None
result = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
          "plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
          "completed_result_files": sum(job["completed_result_files"] for job in jobs), "expected_seed_runs": plan["seed_runs"],
          "completed_shards": sum(job["status"] == "complete" for job in jobs),
          "running_shards": sum(job["status"] == "running" for job in jobs),
          "pending_shards": sum(job["status"] == "pending" for job in jobs),
          "root_finished": root is not None, "root_status": None if root is None else root["status"],
          "root_error": None if root is None else root.get("error"), "errors": errors, "jobs": jobs,
          "scope": "completion and failure metadata only; raw performance values are not read"}
with destination.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    stream.write("\n")
print(json.dumps({key: value for key, value in result.items() if key != "jobs"}, ensure_ascii=False))
