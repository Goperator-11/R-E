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
initial = json.loads((BASE / "runs/iter018_preflight_initial.json").read_text(encoding="utf-8"))
assert state["iterations"] == 17 and state["current"] is None
assert initial["guard_exit_code"] == 0 and not initial["measurement_lock"]
assert state["tasks"]["L2"]["status"] == "blocked" and state["tasks"]["L3"]["status"] == "todo"
assert all(state["tasks"][key]["status"] == "done" for key in state["tasks"]["L3"]["depends"])
state["current"] = "L3"
state["tasks"]["L3"].update(status="doing", started_kst=initial["started_kst"])
path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
selection = {"audit-learning.md": ["A2-02", "A2-04", "A2-05", "A2-10"],
             "audit-learning.run1.md": ["A2-03", "A2-04", "A2-05", "A2-08"],
             "audit-prior-art.md": ["A7-14", "A7-16"], "verify-A7.md": ["A7-14", "A7-16"]}
parts, inputs = [], {}
for name, ids in selection.items():
    source = BASE / "findings" / name
    inputs[str(source)] = hashlib.sha256(source.read_bytes()).hexdigest()
    for section in re.split(r"(?=^## )", source.read_text(encoding="utf-8"), flags=re.M):
        if any(re.match(r"## " + re.escape(key) + r"\b", section) for key in ids):
            parts.append(name + "\n" + section)
assert len(parts) == 12
qsource = Path(r"C:\dev\pq_afec_gen31\g3\RESULT_stage3.md")
inputs[str(qsource)] = hashlib.sha256(qsource.read_bytes()).hexdigest()
parts.append(str(qsource) + "\n" + "\n".join(qsource.read_text(encoding="utf-8").splitlines()[102:110]))
initial.update(task="L3", skipped_task={"task": "L2", "reason": "adoption gate incomplete; E7 after J2/O3"},
               git_head="67aed72df6ae0d1ce2bdc55392efa14d5a5377e2", git_status="clean",
               read=["LOOP_STATE complete", "JOURNAL15-17", "CONTEXT complete", "DECISIONS complete", "L common/L3 complete", "L3_preparation complete", "11 audit items plus2 verification notes and Q23 original"],
               audit_sources_sha256=inputs)
for name, value in (("iter018_preflight.json", json.dumps(initial, ensure_ascii=False, indent=2) + "\n"), ("iter018_sources.txt", "\n".join(parts))):
    with (BASE / "runs" / name).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(value)
print(json.dumps({"iteration": 18, "task": "L3", "started_kst": initial["started_kst"], "source_sections": len(parts)}))
