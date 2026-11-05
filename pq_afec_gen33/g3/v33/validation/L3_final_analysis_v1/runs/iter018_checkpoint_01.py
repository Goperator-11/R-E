import sys
sys.dont_write_bytecode = True
import datetime as dt
import hashlib
import json
from pathlib import Path


BASE = Path(r"C:\dev\codex_handoff\v33")
RUNS = BASE / "runs"
read = lambda p: json.loads(p.read_text(encoding="utf-8"))
launch = read(RUNS / "L3_collection_launch_v1.json")
state_path = BASE / "state/LOOP_STATE.json"
state = read(state_path)
assert state["iterations"] == 17 and state["current"] == "L3" and state["tasks"]["L3"]["status"] == "doing"
checkpoint = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
    "iteration": 18, "task": "L3", "status": "doing", "next": "Full collection must finish before reading performance; prepare joint report and independent checks while frozen collection runs",
    "commits": ["3ea0e04", "c4c76be18dc9f595f06612cc0a1471fb1f722336", "5401bbde0ccf22930b4e8eefca989addbd5758b0"],
    "computation": {"kind": "CPU_development_collection", "status": "running", "driver_pid": launch["driver_pid"],
        "started_kst": launch["started_kst"], "launch_record": str(RUNS / "L3_collection_launch_v1.json"),
        "plan_path": launch["plan_path"], "plan_sha256": launch["plan_sha256"],
        "expected_finished_receipt": str(RUNS / "L3_full_v1.finished.json")},
    "checks": {"core": "254 passed, 424 subtests", "collector": "28 passed, 17 subtests", "smoke": "6 runs, 72 connections, 36 source/receipt files verified", "known_q_injection": "250/250 detected; median 10 decisions"},
    "not_done": ["full W1 collection", "joint action evaluation", "independent report check", "adoption decision", "audit coverage"],
    "guard": "GUARD_OK 2026-10-31T14:20:17+09:00; six unchanged vault warnings, origin unknown"}
out = RUNS / "iter018_checkpoint_01.json"
with out.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(checkpoint, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
state["tasks"]["L3"].update(active_computation=checkpoint["computation"], active_iteration_checkpoint=str(out), commits=checkpoint["commits"])
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
