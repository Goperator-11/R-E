import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import subprocess


BASE = Path(r"C:\dev\codex_handoff\v33")
ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = BASE / "runs"
started = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec="seconds")
state_path = BASE / "state/LOOP_STATE.json"
state = json.loads(state_path.read_text(encoding="utf-8"))
assert state["iterations"] + 1 == 21 and state["current"] is None
guard = subprocess.run([sys.executable, "-I", "-B", str(BASE / "tools/guard_check.py"), "--check"], capture_output=True, text=True, encoding="utf-8")
assert guard.returncode == 0 and guard.stdout.startswith("GUARD_OK")
assert not (BASE / "state/MEASURE_LOCK.json").exists() and state["measurement"] is None
assert not any(row["status"] in ("doing", "partial") for row in state["tasks"].values())
skipped = []
for name in state["order"]:
    row = state["tasks"][name]
    if row["status"] == "done":
        continue
    missing = [dep for dep in row.get("depends", []) if state["tasks"][dep]["status"] != "done"]
    if row["status"] in ("blocked", "skipped") or missing:
        skipped.append({"task": name, "status": row["status"], "missing_dependencies": missing, "reason": row.get("blocker", row.get("note"))})
        continue
    selected = name
    break
assert selected == "J6"
git = ["git", "-C", str(ROOT)]
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
head = subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip()
journal = (BASE / "state/JOURNAL.md").read_text(encoding="utf-8")
latest = "\n".join(re.split(r"(?=^## 반복 )", journal, flags=re.M)[-3:])
record = {"iteration": 21, "started_kst": started, "guard_exit_code": guard.returncode, "guard": guard.stdout,
    "measurement_lock": False, "task": selected, "previous_status": state["tasks"][selected]["status"],
    "git_status": "clean", "git_head": head, "skipped_before_selection": skipped,
    "state_sha256_before": hashlib.sha256(state_path.read_bytes()).hexdigest()}
for name, content in (("iter021_preflight_initial.json", json.dumps(record, ensure_ascii=False, indent=2) + "\n"),
    ("iter021_state_before.json", json.dumps(state, ensure_ascii=False, indent=2) + "\n"), ("iter021_recent_journal.txt", latest)):
    with (RUNS / name).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
print(json.dumps(record, ensure_ascii=False))
print(json.dumps({"task_statuses": {key: row["status"] for key, row in state["tasks"].items()}}, ensure_ascii=False))
