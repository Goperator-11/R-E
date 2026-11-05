import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path

BASE = Path(r"C:\dev\codex_handoff\v33")
RUNS = BASE / "runs"
path = BASE / "state/LOOP_STATE.json"
state = json.loads(path.read_text(encoding="utf-8"))
initial = json.loads((RUNS / "iter021_preflight_initial.json").read_text(encoding="utf-8"))
assert state["iterations"] == 20 and state["current"] is None
assert state["tasks"]["J6"]["status"] == "todo"
assert state["tasks"]["W1"]["status"] == "done"
assert initial["guard_exit_code"] == 0 and not initial["measurement_lock"]
assert not (BASE / "state/MEASURE_LOCK.json").exists()
state["tasks"]["J6"].update(status="doing", started_kst=initial["started_kst"], note="활성 L1에서 A_pre 후보·평가·관측 계약을 맞춘다. L2/L3/J1 blocked와 L4/J2 의존 미충족은 이전 판단을 유지한다.")
state["current"] = "J6"
path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
initial["read"] = ["LOOP_STATE parsed complete", "JOURNAL18-20", "CONTEXT complete", "DECISIONS complete", "J6 full card", "A1-04 original and verification, A4-03, A8-06", "J6_preparation complete", "J6_reading_during_J1_v1 complete", "active decide3/layout/learn3 complete and quantum relevant definitions"]
initial["audit_source_sha256"] = json.loads((RUNS / "iter021_sources_sha256.json").read_text(encoding="utf-8"))
initial["source_before"] = {name: hashlib.sha256((Path(r"C:\dev\pq_afec_gen33") / name).read_bytes()).hexdigest() for name in ("padfec/quantum.py", "padfec3/layout.py", "padfec3/learn3.py", "padfec3/decide3.py")}
with (RUNS / "iter021_preflight.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(initial, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps({"iteration": 21, "task": "J6", "started_kst": initial["started_kst"]}))
