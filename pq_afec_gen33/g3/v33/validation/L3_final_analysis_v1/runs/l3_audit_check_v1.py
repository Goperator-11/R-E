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
sources = [RUNS / "l3_monitor_audit_v1.py", ROOT / "tests/test_v33_l3_monitor_audit.py", ROOT / "tests/test_v33_learning_l3.py",
           ROOT / "padfec3/monitor3.py", ROOT / "padfec3/learn3.py", ROOT / "padfec3/decide3.py"]
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
before = {str(path): sha(path) for path in sources}
log, out = RUNS / (label + ".log"), RUNS / (label + ".json")
assert not log.exists() and not out.exists()
code = "import sys; sys.dont_write_bytecode=True; sys.stdout.reconfigure(encoding='utf-8'); sys.path.insert(0," + repr(str(ROOT)) + "); import pytest; raise SystemExit(pytest.main(['tests/test_v33_l3_monitor_audit.py','-q','-p','no:cacheprovider']))"
started, timer = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), time.monotonic()
with log.open("x", encoding="utf-8", newline="\n") as stream:
    result = subprocess.run([sys.executable, "-I", "-B", "-c", code], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
after = {str(path): sha(path) for path in sources}
value = {"started_kst": started, "elapsed_seconds": time.monotonic() - timer, "exit_code": result.returncode,
    "source_sha256": before, "source_sha256_after": after, "unchanged": before == after,
    "log_path": str(log), "log_sha256": sha(log), "script_sha256": sha(__file__)}
with out.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(value, stream, indent=2)
    stream.write("\n")
print(log.read_text(encoding="utf-8"))
print(json.dumps({k: value[k] for k in ("exit_code", "elapsed_seconds", "unchanged", "log_sha256")}))
raise SystemExit(result.returncode if before == after else 2)
