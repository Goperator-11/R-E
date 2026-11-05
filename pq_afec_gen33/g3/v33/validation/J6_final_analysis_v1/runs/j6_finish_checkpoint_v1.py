import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path

BASE = Path(r"C:\dev\codex_handoff\v33")
RUNS = BASE / "runs"
ROOT = Path(r"C:\dev\pq_afec_gen33")
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    state_path = BASE / "state/LOOP_STATE.json"
    state = read(state_path)
    assert state["iterations"] == 21 and state["current"] == "J6"
    task = state["tasks"]["J6"]
    assert task["status"] == "doing"
    out = RUNS / "iter022_checkpoint_03.json"
    assert not out.exists()
    findings_path = RUNS / "J6_findings_v1.json"
    findings = read(findings_path)
    check_path = RUNS / "J6_joint_artifact_check_v2.json"
    check = read(check_path)
    assert check["status"] == "pass" and check["error"] is None
    assert findings["checker_sha256"] == sha(check_path)
    assert findings["report_sha256"] == sha(ROOT / "g3/v33/J6_benchmark_v1.json")
    adopted = findings["candidate_adopted"]
    assert type(adopted) is bool
    labels = ("J6_core_check_02", "J6_collector_check_01", "J6_final_checks_01") if adopted else ("J6_revert_check_01",)
    tests = {}
    for label in labels:
        path = RUNS / (label + ".json")
        test = read(path)
        assert test["exit_code"] == 0 and test["unchanged"]
        assert all(sha(p) == value for p, value in test["source_sha256"].items())
        tests[str(path)] = sha(path)
    active = task["active_computation"]
    assert active["kind"] == "CPU_development_independent_validation"
    end_path = Path(active["expected_finished_receipt"])
    end = read(end_path)
    assert end["status"] == "complete" and end["exit_code"] == 0 and end["check_sha256"] == sha(check_path)
    completed = task.setdefault("completed_computations", [])
    assert all(row.get("launch_record") != active["launch_record"] for row in completed)
    active.update(status="complete", ended_kst=end["ended_kst"], completion_receipt=str(end_path))
    completed.append(active)
    del task["active_computation"]
    task["candidate_adopted"] = adopted
    if adopted:
        task.pop("blocker", None)
    else:
        assert "E10" in state["tasks"] and "E10" in state["order"]
        assert read(RUNS / "J6_revert_candidate_v1.json")["active_policy_exactly_matches_l1"] is True
        task["blocker"] = {"reason": findings["reason"], "followup": "E10", "depends": state["tasks"]["E10"]["depends"]}
    result = {"iteration": 22, "task": "J6", "recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
              "candidate_adopted": adopted, "primary_counts": findings["primary_counts"], "findings_sha256": sha(findings_path),
              "checker_sha256": sha(check_path), "validation_receipt_sha256": sha(end_path), "tests_sha256": tests,
              "blocker": task.get("blocker"), "script_sha256": sha(__file__),
              "scope": "Completed computation and disposition checkpoint; iteration closes only after evidence commit and journal/report update."}
    with out.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    task["active_iteration_checkpoint"] = str(out)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()
