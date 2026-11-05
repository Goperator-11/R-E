import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import time
import traceback


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
SCRIPT = ROOT / "experiments/v33/bench_learning_j1.py"
PROTOCOL = ROOT / "g3/v33/bench_protocol.json"
PLAN = RUNS / "J1_full_v1_plan.json"
REPO_PLAN = ROOT / "g3/v33/bench_overlays/J1_v1_execution_plan.json"
KST = dt.timezone(dt.timedelta(hours=9))


def now():
    return dt.datetime.now(KST).isoformat()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def plan_contract():
    protocol = read(PROTOCOL)
    tasks, inputs = [], {str(PROTOCOL): sha(PROTOCOL), str(SCRIPT): sha(SCRIPT),
                         str(ROOT / "docs/J1_tail_design.md"): sha(ROOT / "docs/J1_tail_design.md")}
    for name, modes in (("J1_v1", ("none", "c1", "ideal")), ("J1_cost_only_v1", ("none", "c1"))):
        path = ROOT / "g3/v33/bench_overlays" / (name + ".json")
        overlay = read(path)
        inputs[str(path)] = sha(path)
        inputs[overlay["policy"]["receipt_path"]] = overlay["policy"]["receipt_sha256"]
        for mode in modes:
            for scenario in protocol["scenarios"]:
                tasks.append({"policy": name, "mode": mode, "scenario": scenario["id"], "overlay": str(path),
                              "connections": sum(p["length"] for p in scenario["phases"]) * len(protocol["seeds"])})
    tasks.sort(key=lambda job: (-job["connections"], job["policy"], job["mode"], job["scenario"]))
    for index, task in enumerate(tasks, 1):
        task["id"] = f"J1_raw_v1_{index:02d}"
        task["out"] = str(RUNS / task["id"])
        task["command"] = [sys.executable, "-I", "-B", str(SCRIPT), "collect", "--overlay", task["overlay"],
                           "--out", task["out"], "--modes", task["mode"], "--scenarios", task["scenario"]]
    return {"schema": "padfec.v33.learning_launch/3", "driver_sha256": sha(__file__), "inputs_sha256": inputs,
            "workers": 8, "jobs": tasks, "seed_runs": len(tasks) * len(protocol["seeds"]),
            "connections": sum(task["connections"] for task in tasks), "data_kind": "development_independent_world",
            "physical_measurement": False, "same_protocol_seeds_and_phase_lengths": True,
            "cost_only_is_diagnostic_only": True, "primary_previous_policy": "L1",
            "adoption_modes_vs_L1": ["none", "c1"], "no_performance_based_stopping": True}


def validate_plan(plan):
    expected = plan_contract()
    if set(plan) != set(expected) | {"created_kst"}:
        raise ValueError("unexpected plan fields")
    for key, value in expected.items():
        if plan[key] != value:
            raise ValueError("plan differs: " + key)
    for path, expected_sha in plan["inputs_sha256"].items():
        if sha(path) != expected_sha:
            raise ValueError("plan input changed: " + path)


def run_one(job, dry_run=False):
    command = job["command"] + (["--dry-run"] if dry_run else [])
    stem = job["id"] + ("_dry" if dry_run else "")
    started, tic, driver_before = now(), time.monotonic(), sha(__file__)
    start_path = RUNS / (stem + ".started.json")
    out, err = RUNS / (stem + ".stdout.txt"), RUNS / (stem + ".stderr.txt")
    save(start_path, {"command": command, "started_kst": started, "driver_sha256": driver_before,
                      "overlay_sha256": sha(job["overlay"]), "collector_sha256": sha(SCRIPT)})
    exit_code, error = None, None
    try:
        with out.open("xb") as stdout, err.open("xb") as stderr:
            completed = subprocess.run(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        exit_code = completed.returncode
    except BaseException:
        error = traceback.format_exc()
    driver_after = sha(__file__)
    receipt = {"command": command, "started_kst": started, "ended_kst": now(), "exit_code": exit_code,
               "status": "complete" if exit_code == 0 and error is None and driver_before == driver_after else "failed",
               "elapsed_seconds": time.monotonic() - tic, "error": error,
               "started_receipt_sha256": sha(start_path), "stdout_path": str(out), "stderr_path": str(err),
               "stdout_sha256": sha(out) if out.exists() else None, "stderr_sha256": sha(err) if err.exists() else None,
               "driver_sha256": driver_before, "driver_sha256_after": driver_after,
               "collector_sha256": sha(SCRIPT), "overlay_sha256": sha(job["overlay"])}
    save(RUNS / (stem + ".finished.json"), receipt)
    print(json.dumps({"stem": stem, "status": receipt["status"], "exit_code": exit_code,
                      "elapsed_seconds": receipt["elapsed_seconds"]}), flush=True)
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("plan", "smoke", "full"))
    args = parser.parse_args()
    if args.command == "plan":
        plan = {**plan_contract(), "created_kst": now()}
        validate_plan(plan)
        save(PLAN, plan)
        save(REPO_PLAN, plan)
        print(json.dumps({key: plan[key] for key in ("workers", "seed_runs", "connections", "inputs_sha256")}), flush=True)
        return 0
    plan = read(PLAN)
    validate_plan(plan)
    if sha(PLAN) != sha(REPO_PLAN):
        raise ValueError("launch plan copies differ")
    if (RUNS.parent / "state/MEASURE_LOCK.json").exists():
        raise ValueError("physical measurement lock forbids CPU collection")
    stem = "J1_" + args.command + "_v1"
    jobs = plan["jobs"]
    if args.command == "smoke":
        jobs = []
        for original in plan["jobs"]:
            if original["scenario"] != "B1":
                continue
            job = dict(original)
            job["id"] = "J1_smoke_v1_" + original["policy"] + "_" + original["mode"]
            job["out"] = str(RUNS / job["id"])
            job["command"] = list(original["command"])
            job["command"][job["command"].index("--out") + 1] = job["out"]
            job["command"].append("--smoke")
            jobs.append(job)
    else:
        smoke = read(RUNS / "J1_smoke_v1.finished.json")
        if smoke["status"] != "complete" or smoke["plan_sha256"] != sha(PLAN):
            raise ValueError("matching smoke phase must complete first")
    start_path = RUNS / (stem + ".started.json")
    save(start_path, {"started_kst": now(), "plan_sha256": sha(PLAN), "driver_sha256": sha(__file__),
                      "jobs": len(jobs), "workers": plan["workers"]})
    results, error = [], None
    try:
        if args.command == "smoke":
            for job in jobs:
                dry = run_one(job, dry_run=True)
                if dry["status"] != "complete" or Path(job["out"]).exists():
                    raise ValueError("dry-run failed or created output directory")
        with concurrent.futures.ThreadPoolExecutor(max_workers=plan["workers"]) as executor:
            futures = [executor.submit(run_one, job) for job in jobs]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        validate_plan(plan)
    except BaseException:
        error = traceback.format_exc()
    complete = error is None and len(results) == len(jobs) and all(item["status"] == "complete" for item in results)
    result = {"ended_kst": now(), "plan_sha256": sha(PLAN), "driver_sha256": sha(__file__),
              "started_receipt_sha256": sha(start_path), "status": "complete" if complete else "failed",
              "error": error, "jobs": len(results), "expected_jobs": len(jobs), "results": results}
    save(RUNS / (stem + ".finished.json"), result)
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
