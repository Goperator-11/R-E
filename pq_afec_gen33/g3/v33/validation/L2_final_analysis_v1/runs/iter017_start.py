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
assert state["iterations"] == 16 and state["current"] is None
assert all(state["tasks"][k]["status"] == "done" for k in ("L1", "E5", "E6"))
assert state["tasks"]["L2"]["status"] == "todo"
assert not (BASE / "state/MEASURE_LOCK.json").exists() and state["measurement"] is None
started = "2026-10-31T12:48:17+09:00"
state["current"] = "L2"
state["tasks"]["L2"].update(status="doing", started_kst=started)
path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
preflight = {"iteration": 17, "task": "L2", "started_kst": started,
             "guard": "GUARD_OK 2026-10-31T12:48:17+09:00", "guard_warning_count": 6,
             "guard_note": "볼트 경고에 PowerGuard 사라짐 확인.md 생성이 추가됐다. 반복16 guard 원문은6건이며 확인 못 한 것의5건은 갱신 누락이다. 변경 주체는 미확인이고 보호 경로를 수정하지 않는다.",
             "measurement_lock": False, "git_status": "clean", "git_head": "d845395c7e26637c853c76377139ed46b73907e0",
             "read": ["LOOP_STATE.json", "JOURNAL.md iterations14-16", "CONTEXT.md complete", "DECISIONS_NEEDED.md complete", "TASKS L common and L2", "six audit and verification sections"]}
selection = {"audit-learning.md": ["A2-06", "A2-07"], "audit-learning.run1.md": ["A2-01", "A2-15"],
             "audit-prior-art.md": ["A7-13"], "verify-A7.md": ["A7-13"]}
parts, inputs = [], {}
for name, ids in selection.items():
    source_path = BASE / "findings" / name
    source = source_path.read_text(encoding="utf-8")
    inputs[str(source_path)] = hashlib.sha256(source_path.read_bytes()).hexdigest()
    for section in re.split(r"(?=^## )", source, flags=re.M):
        if any(re.match(r"## " + re.escape(key) + r"\b", section) for key in ids):
            parts.append(name + "\n" + section)
assert len(parts) == 6
preflight["audit_sources_sha256"] = inputs
for name, content in (("iter017_preflight.json", json.dumps(preflight, ensure_ascii=False, indent=2) + "\n"),
                      ("iter017_sources.txt", "\n".join(parts))):
    with (BASE / "runs" / name).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
print(json.dumps(preflight, ensure_ascii=False))
