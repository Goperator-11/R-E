import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sys.path.insert(0, str(ROOT))
from experiments.v33 import bench_learning_l2 as learning


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


plan = read(RUNS / "L2_full_v1_plan.json")
assert len(plan["jobs"]) == 75 and len({job["id"] for job in plan["jobs"]}) == 75
assert len({(job["policy"], job["mode"], job["scenario"]) for job in plan["jobs"]}) == 75
assert plan["seed_runs"] == 1500 and plan["connections"] == 2055000
assert plan["driver_sha256"] == sha(RUNS / "l2_bench_driver_v1.py")
for path, checksum in plan["inputs_sha256"].items():
    assert sha(path) == checksum
finish = read(RUNS / "L2_smoke_v1.finished.json")
assert finish["status"] == "complete" and finish["jobs"] == finish["expected_jobs"] == 5
assert finish["plan_sha256"] == sha(RUNS / "L2_full_v1_plan.json")
assert finish["started_receipt_sha256"] == sha(RUNS / "L2_smoke_v1.started.json")
verified, totals = {}, {"seed_runs": 0, "connections": 0, "calibrated": 0, "cold_skips": 0}
for receipt in finish["results"]:
    assert receipt["status"] == "complete" and receipt["exit_code"] == 0
    assert receipt["driver_sha256"] == receipt["driver_sha256_after"] == plan["driver_sha256"]
    for field in ("stdout", "stderr"):
        assert sha(receipt[field + "_path"]) == receipt[field + "_sha256"]
        verified[receipt[field + "_path"]] = receipt[field + "_sha256"]
    command = receipt["command"]
    folder = Path(command[command.index("--out") + 1])
    overlay_path = Path(command[command.index("--overlay") + 1])
    overlay, protocol = learning.load_overlay(overlay_path)
    baseline, _, _ = learning.imported_runs(overlay, protocol)
    baseline_map = {(row["scenario"], row["seed"]): row for row in baseline if row["generation"] == "v32"}
    manifest = read(folder / "manifest.json")
    assert manifest["mode"] == "smoke"
    assert manifest == learning.make_manifest(overlay_path, overlay, protocol, manifest["observation_modes"], manifest["scenarios"], smoke=True)
    scenarios = {item["id"]: item for item in protocol["scenarios"]}
    expected_paths = set()
    for mode in manifest["observation_modes"]:
        for sid in manifest["scenarios"]:
            for seed in manifest["seeds"]:
                path = folder / mode / sid / f"seed{seed:05d}.json"
                expected_paths.add(path)
                run = read(path)
                rows = learning.validate_run(run, manifest, overlay, scenarios[sid], mode, seed, baseline_map[sid, seed])
                verified.update(learning.validate_receipt(run, path))
                assert run["summary"] == learning.summarize_run(rows, scenarios[sid], protocol)
                totals["seed_runs"] += 1
                totals["connections"] += len(rows)
                totals["calibrated"] += sum(row["observation_info"]["epsilon_update_eligible"] for row in rows)
                totals["cold_skips"] += sum(row["observation_info"]["epsilon_update_reason"] == "no_ctx" for row in rows)
                verified[str(path)] = sha(path)
                verified[run["trace_path"]] = run["trace_sha256"]
    assert {p for p in folder.glob("*/*/seed*.json") if p.name.count(".") == 1} == expected_paths
    assert not list(folder.rglob("*.failed.json"))
result = {"status": "pass", "scope": "smoke data and launch-plan integrity; no policy performance claim",
          "script_sha256": sha(__file__), "plan_sha256": sha(RUNS / "L2_full_v1_plan.json"),
          "collector_sha256": sha(learning.__file__), "totals": totals, "verified_files_sha256": verified}
with (RUNS / "L2_validate_smoke_v1.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    stream.write("\n")
print(json.dumps({"status": "pass", "totals": totals, "verified_files": len(verified)}))
