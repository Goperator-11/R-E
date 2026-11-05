import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path
import re


BASE = Path(r"C:\dev\codex_handoff\v33")
RUNS = BASE / "runs"
state_path = BASE / "state/LOOP_STATE.json"
state = json.loads(state_path.read_text(encoding="utf-8"))
initial = json.loads((RUNS / "iter020_preflight_initial.json").read_text(encoding="utf-8"))
assert state["iterations"] == 19 and state["current"] is None and state["tasks"]["J1"]["status"] == "todo"
assert initial["guard_exit_code"] == 0 and not initial["measurement_lock"]
assert state["tasks"]["W1"]["status"] == "done"
parts, hashes = [], {}
for name, key in (("audit-cost-model.md", "A1-01"), ("verify-A1.md", "A1-01"), ("audit-learning.md", "A2-17"), ("audit-quicgo-source.md", "A8-08")):
    path = BASE / "findings" / name
    hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    selected = [section for section in re.split(r"(?=^## )", path.read_text(encoding="utf-8"), flags=re.M) if re.match(r"## " + re.escape(key) + r"\b", section)]
    assert len(selected) == 1
    parts.append(name + "\n" + selected[0])
q = Path(r"C:\dev\pq_afec_gen31\g3\RESULT_stage3.md")
hashes[str(q)] = hashlib.sha256(q.read_bytes()).hexdigest()
parts.append(str(q) + "\n" + "\n".join(q.read_text(encoding="utf-8").splitlines()[102:110]))
with (RUNS / "iter020_sources.txt").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write("\n".join(parts))
state["tasks"]["J1"].update(status="doing", started_kst=initial["started_kst"], note="L2·L3 blocked와 L4 의존 미충족을 건너뛰고 활성 L1에서 둘째 왕복 꼬리 모형을 검토한다.")
state["current"] = "J1"
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
initial["read"] = ["LOOP_STATE parsed complete", "JOURNAL17-19", "CONTEXT complete", "DECISIONS complete", "J1 full card", "A1-01 original and PARTLY correction, A2-17, A8-08, Q23 and source"]
initial["audit_source_sha256"] = hashes
with (RUNS / "iter020_preflight.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(initial, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps({"iteration": 20, "task": "J1", "started_kst": initial["started_kst"], "source_sections": len(parts)}))
