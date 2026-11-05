import sys
sys.dont_write_bytecode = True
import datetime as dt
import json
from pathlib import Path
import subprocess


BASE = Path(r"C:\dev\codex_handoff\v33")
ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = BASE / "runs"
read = lambda p: json.loads(p.read_text(encoding="utf-8"))
state_path = BASE / "state/LOOP_STATE.json"
state = read(state_path)
assert state["iterations"] == 17 and state["current"] == "L3"
task = state["tasks"]["L3"]
task["commits"] = [subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", commit], text=True).strip()
    for commit in ["3ea0e04", "c4c76be18dc9f595f06612cc0a1471fb1f722336", "5401bbde0ccf22930b4e8eefca989addbd5758b0", "6acec358f7ecc63e77525cb2a3ce0c96dccb6c8f"]]
task["active_computation"]["progress_record"] = str(RUNS / "L3_collection_progress_05.json")
checkpoint = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "iteration": 18,
    "task": "L3", "status": "doing", "commits": task["commits"], "computation": task["active_computation"],
    "analysis_check": "61 passed, 57 subtests; 6 independent smoke replays, 72 connections",
    "next": "Wait for root L3_full_v1.finished complete 90/90, then launch_l3_joint_plan_v1.ps1 once. No raw performance read before complete. After plan, generate bound artifact checker and run/report launchers, commit family, then whole fixed MC.",
    "remaining": ["collection", "joint family validation", "fixed whole-family MC", "report", "independent report checks", "adoption and coverage"]}
path = RUNS / "iter018_checkpoint_02.json"
with path.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(checkpoint, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
task["active_iteration_checkpoint"] = str(path)
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
