import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path

BASE = Path(r"C:\dev\codex_handoff\v33")
RUNS = BASE / "runs"
state_path = BASE / "state/LOOP_STATE.json"
before = state_path.read_bytes()
state = json.loads(before)
assert state["current"] == "L5" and state["iterations"] == 23
names = {"J7": ["J7_reading_during_L5_v1.md", "J7_reading_during_L5_v2.md", "J7_reading_during_L5_v3.md"], "M1": ["M1_reading_during_L5_v1.md", "M1_reading_during_L5_v2.md"], "S4": ["M1_reading_during_L5_v2.md"]}
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
for task, paths in names.items():
    assert state["tasks"][task]["status"] == "todo"
    for name in paths:
        path = RUNS / name
        assert path.is_file()
        notes = state["tasks"][task].setdefault("handoff_notes", [])
        assert str(path) not in notes
        notes.append(str(path))
with (RUNS / "L5_lookahead_state_before_v1.json").open("xb") as stream:
    stream.write(before)
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
value = {"scope": "Read-only lookahead notes registered without changing task status, dependencies or order", "tasks": names, "state_before_sha256": hashlib.sha256(before).hexdigest(), "state_after_sha256": sha(state_path), "note_sha256": {name: sha(RUNS / name) for paths in names.values() for name in paths}, "script_sha256": sha(__file__)}
with (RUNS / "L5_lookahead_registered_v1.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(value, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps({"registered_tasks": list(names), "note_references": sum(map(len, names.values()))}))
