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
out, log = RUNS / (label + ".json"), RUNS / (label + ".log")
assert not out.exists() and not log.exists()
files = ["test_v33_learning_l2_report.py", "test_v33_learning_report.py", "test_v33_l2_joint_driver.py"]
sources = [ROOT / "experiments/v33/bench_learning_l2_report.py", ROOT / "experiments/v33/bench_learning_l2.py",
           ROOT / "experiments/v33/bench_learning_report.py", RUNS / "l2_joint_driver_v1.py"] + [ROOT / "tests" / name for name in files]
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
before = {str(path): sha(path) for path in sources}
code = "import sys; sys.dont_write_bytecode=True; sys.stdout.reconfigure(encoding='utf-8'); sys.path.insert(0," + repr(str(ROOT)) + "); import pytest; raise SystemExit(pytest.main(" + repr(["tests/" + name for name in files] + ["-q", "-p", "no:cacheprovider"]) + "))"
started, timer = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), time.monotonic()
with log.open("x", encoding="utf-8", newline="\n") as stream:
    completed = subprocess.run([sys.executable, "-I", "-B", "-c", code], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
after = {str(path): sha(path) for path in sources}
result = {"started_kst": started, "elapsed_seconds": time.monotonic() - timer, "exit_code": completed.returncode,
          "source_sha256": before, "source_sha256_after": after, "unchanged": before == after,
          "log_path": str(log), "log_sha256": sha(log), "script_sha256": sha(__file__)}
out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(log.read_text(encoding="utf-8"))
print(json.dumps({key: result[key] for key in ("exit_code", "elapsed_seconds", "unchanged", "log_sha256")}))
raise SystemExit(completed.returncode if before == after else 2)
