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
assert state["iterations"] + 1 == 19 and state["current"] is None
assert state["tasks"]["L3"]["status"] == "partial"
guard = subprocess.run([sys.executable, "-I", "-B", str(BASE / "tools/guard_check.py"), "--check"], capture_output=True, text=True, encoding="utf-8")
assert guard.returncode == 0 and guard.stdout.startswith("GUARD_OK")
assert not (BASE / "state/MEASURE_LOCK.json").exists()
git = ["git", "-C", str(ROOT)]
dirty = subprocess.check_output(git + ["status", "--porcelain"], text=True)
assert not dirty.strip()
head = subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip()
journal = (BASE / "state/JOURNAL.md").read_text(encoding="utf-8")
latest = "\n".join(re.split(r"(?=^## 반복 )", journal, flags=re.M)[-3:])
selection = {"audit-learning.md": ["A2-02", "A2-04", "A2-05", "A2-10"],
    "audit-learning.run1.md": ["A2-03", "A2-04", "A2-05", "A2-08"], "audit-prior-art.md": ["A7-14", "A7-16"], "verify-A7.md": ["A7-14", "A7-16"]}
parts, hashes = [], {}
for name, ids in selection.items():
    path = BASE / "findings" / name
    hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    for section in re.split(r"(?=^## )", path.read_text(encoding="utf-8"), flags=re.M):
        if any(re.match(r"## " + re.escape(key) + r"\b", section) for key in ids):
            parts.append(name + "\n" + section)
assert len(parts) == 12
q = Path(r"C:\dev\pq_afec_gen31\g3\RESULT_stage3.md")
hashes[str(q)] = hashlib.sha256(q.read_bytes()).hexdigest()
parts.append(str(q) + "\n" + "\n".join(q.read_text(encoding="utf-8").splitlines()[102:110]))
record = {"iteration": 19, "started_kst": started, "guard_exit_code": guard.returncode, "guard": guard.stdout,
    "measurement_lock": False, "task": "L3", "previous_status": "partial", "git_status": "clean", "git_head": head,
    "state_sha256_before": hashlib.sha256(state_path.read_bytes()).hexdigest(), "audit_source_sha256": hashes,
    "active_computation": state["tasks"]["L3"]["active_computation"]}
for name, content in (("iter019_preflight_initial.json", json.dumps(record, ensure_ascii=False, indent=2) + "\n"),
    ("iter019_sources.txt", "\n".join(parts)), ("iter019_recent_journal.txt", latest)):
    with (RUNS / name).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
print(json.dumps(record, ensure_ascii=False))
print(json.dumps({"L3": state["tasks"]["L3"], "L2": {key: state["tasks"]["L2"][key] for key in ("status", "note", "blocker")},
    "task_statuses": {key: row["status"] for key, row in state["tasks"].items()}}, ensure_ascii=False))
