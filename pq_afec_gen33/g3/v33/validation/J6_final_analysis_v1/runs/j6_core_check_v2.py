import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
label = sys.argv[1]
assert label.replace("_", "").isalnum()
assert not (RUNS.parent / "state/MEASURE_LOCK.json").exists()
out, log = RUNS / (label + ".json"), RUNS / (label + ".log")
assert not out.exists() and not log.exists()
files = ["test_core_regressions.py", "test_padfec3_learn.py", "test_padfec3_layout.py",
         "test_padfec3_dev_regressions.py", "test_padfec3_input_validation.py", "test_padfec3_followup.py",
         "test_replay_g3_dev.py", "test_gen32_runner_isolation.py", "test_adaptation_benchmark.py",
         "test_padfec3_arrivals.py", "test_v33_l2_candidate.py", "test_v33_policy_worker.py",
         "test_v33_learning_l2_report.py", "test_v33_l2_joint_driver.py", "test_v33_l3_candidate.py",
         "test_v33_learning_l3_report.py", "test_v33_l3_joint_driver.py", "test_v33_l3_findings.py",
         "test_padfec3_preflight.py", "test_v33_preflight_observer.py", "test_v33_j1_candidate.py", "test_v33_learning_j1.py", "test_v33_learning_j1_report.py", "test_v33_j1_joint_driver.py", "test_v33_j1_findings.py"]
sources = [p for name in ("padfec", "padfec3") for p in (ROOT / name).glob("*.py")]
sources += [ROOT / "tests" / name for name in files]
sources += [ROOT / "experiments/adaptation_benchmark.py"]
sources += sorted((ROOT / "experiments/v33/candidate_tests").glob("j1_*.py"))
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
before = {str(path): sha(path) for path in sources}
code = "import sys; sys.dont_write_bytecode=True; sys.stdout.reconfigure(encoding='utf-8'); sys.path.insert(0," + repr(str(ROOT)) + "); import pytest; raise SystemExit(pytest.main(" + repr(["tests/" + name for name in files] + ["-q", "-p", "no:cacheprovider"]) + "))"
started = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
timer = time.monotonic()
with log.open("x", encoding="utf-8", newline="\n") as stream:
    completed = subprocess.run([sys.executable, "-I", "-B", "-c", code], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
after = {str(path): sha(path) for path in sources}
result = {"started_kst": started, "elapsed_seconds": time.monotonic() - timer, "exit_code": completed.returncode,
          "source_sha256": before, "source_sha256_after": after, "unchanged": before == after,
          "log_path": str(log), "log_sha256": sha(log), "script_sha256": sha(__file__)}
with out.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(log.read_text(encoding="utf-8"))
print(json.dumps({key: result[key] for key in ("exit_code", "elapsed_seconds", "unchanged", "log_sha256")}))
raise SystemExit(completed.returncode if before == after else 2)
