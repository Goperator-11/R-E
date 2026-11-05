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
files = ["test_v33_learning_j6.py", "test_v33_preflight_observer.py", "test_padfec3_preflight.py"]
names = ["experiments/v33/bench_learning_j6.py", "experiments/v33/policy_worker_j6.py", "experiments/v33/policy_bridge_j6.py", "experiments/v33/preflight_observer.py"] + ["tests/" + name for name in files]
names += [p.relative_to(ROOT).as_posix() for p in (ROOT / "padfec3").glob("*.py")]
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
before = {str(ROOT / name): sha(ROOT / name) for name in names}
code = "import sys; sys.dont_write_bytecode=True; sys.stdout.reconfigure(encoding='utf-8'); sys.path.insert(0," + repr(str(ROOT)) + "); import pytest; raise SystemExit(pytest.main(" + repr(["tests/" + name for name in files] + ["-q", "-p", "no:cacheprovider"]) + "))"
started = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
timer = time.monotonic()
with log.open("x", encoding="utf-8", newline="\n") as stream:
    result = subprocess.run([sys.executable, "-I", "-B", "-c", code], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
after = {path: sha(path) for path in before}
receipt = {"exit_code": result.returncode, "started_kst": started, "elapsed_seconds": time.monotonic() - timer,
    "source_sha256": before, "source_sha256_after": after, "unchanged": before == after,
    "script_sha256": sha(__file__), "log_path": str(log), "log_sha256": sha(log)}
with out.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(receipt, stream, indent=2)
    stream.write("\n")
print(log.read_text(encoding="utf-8"))
raise SystemExit(result.returncode if before == after else 2)
