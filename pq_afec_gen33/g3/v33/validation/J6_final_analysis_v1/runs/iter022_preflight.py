import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
import subprocess

BASE = Path(r"C:\dev\codex_handoff\v33")
ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = BASE / "runs"
started = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec="seconds")
state_path = BASE / "state/LOOP_STATE.json"
raw = state_path.read_bytes()
state = json.loads(raw)
assert state["iterations"] + 1 == 22 and state["current"] is None
assert [name for name, task in state["tasks"].items() if task["status"] in ("doing", "partial")] == ["J6"]
guard = subprocess.run([sys.executable, "-I", "-B", str(BASE / "tools/guard_check.py"), "--check"], capture_output=True, text=True, encoding="utf-8")
assert guard.returncode == 0 and guard.stdout.startswith("GUARD_OK")
assert not (BASE / "state/MEASURE_LOCK.json").exists() and state["measurement"] is None
git = ["git", "-C", str(ROOT)]
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
task = state["tasks"]["J6"]
assert task["active_computation"]["driver_pid"] == 25680
journal = (BASE / "state/JOURNAL.md").read_text(encoding="utf-8")
latest = "\n".join(re.split(r"(?=^## 반복 )", journal, flags=re.M)[-3:])
record = {"iteration": 22, "started_kst": started, "guard_exit_code": guard.returncode, "guard": guard.stdout,
    "measurement_lock": False, "task": "J6", "previous_status": task["status"], "git_status": "clean",
    "git_head": subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip(),
    "state_sha256_before": hashlib.sha256(raw).hexdigest(), "active_computation": task["active_computation"]}
for name, content in (("iter022_preflight_initial.json", json.dumps(record, ensure_ascii=False, indent=2) + "\n"),
    ("iter022_state_before.json", json.dumps(state, ensure_ascii=False, indent=2) + "\n"), ("iter022_recent_journal.txt", latest)):
    with (RUNS / name).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
print(json.dumps(record, ensure_ascii=False))
print(subprocess.check_output(git + ["log", "-3", "--oneline"], text=True, encoding="utf-8"))
