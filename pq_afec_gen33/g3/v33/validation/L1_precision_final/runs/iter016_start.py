import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path
import re


BASE = Path(r"C:\dev\codex_handoff\v33")
path = BASE / "state/LOOP_STATE.json"
state = json.loads(path.read_text(encoding="utf-8"))
assert state["iterations"] == 15 and state["current"] is None
assert state["tasks"]["L1"]["status"] == "partial"
assert state["tasks"]["L1"]["active_computation"]["driver_pid"] == 11448
assert not (BASE / "state/MEASURE_LOCK.json").exists()
started = "2026-10-31T11:37:45+09:00"
state["tasks"]["L1"]["previous_iteration_checkpoint"] = state["tasks"]["L1"].pop("active_iteration_checkpoint")
state["current"] = "L1"
state["tasks"]["L1"].update(status="doing", started_kst=started)
path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
preflight = {"iteration": 16, "task": "L1", "started_kst": started,
             "guard": "GUARD_OK 2026-10-31T11:37:45+09:00", "measurement_lock": False,
             "git_status": "clean", "git_head": "c38658d70f0163e323dc332350791470e0819888",
             "continuation": "Continue v2 precision run driver PID11448. Original v1 is interrupted and preserved. E5/E6 split exists. Progress and errors only until complete; sources and target frozen."}
selection = {"audit-learning.md": ["A2-01", "A2-02", "A2-08", "A2-12"],
             "audit-learning.run1.md": ["A2-02", "A2-06", "A2-11"], "audit-go-wire.md": ["A3-02"],
             "audit-prior-art.md": ["A7-11"], "audit-quicgo-source.md": ["A8-09"], "verify-A7.md": ["A7-11"]}
parts, inputs = [], {}
for name, ids in selection.items():
    source_path = BASE / "findings" / name
    source = source_path.read_text(encoding="utf-8")
    inputs[str(source_path)] = hashlib.sha256(source_path.read_bytes()).hexdigest()
    for section in re.split(r"(?=^## )", source, flags=re.M):
        if any(re.match(r"## " + re.escape(key) + r"\b", section) for key in ids):
            parts.append(name + "\n" + section)
source_path = BASE / "findings/verify-A1.md"
source = source_path.read_text(encoding="utf-8")
inputs[str(source_path)] = hashlib.sha256(source_path.read_bytes()).hexdigest()
parts.extend("verify-A1.md\n" + section for section in re.split(r"(?=^## )", source, flags=re.M)
             if "## MISSED" in section and ("정보" in section or "탐욕" in section))
assert len(parts) == 12
preflight["audit_sources_sha256"] = inputs
for name, content in (("iter016_preflight.json", json.dumps(preflight, ensure_ascii=False, indent=2) + "\n"),
                      ("iter016_sources.txt", "\n".join(parts))):
    with (BASE / "runs" / name).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
print(json.dumps(preflight, ensure_ascii=False))
