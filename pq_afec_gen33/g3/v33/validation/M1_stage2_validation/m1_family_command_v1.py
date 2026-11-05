import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
FAMILY = RUNS / "M1_action_family_v1.json"
PROTOCOL = RUNS / "M1_combined_protocol_v1.json"
VALIDATED = RUNS / "M1_validated_runs_v1.json"
POOL = RUNS / "M1_action_pool_v1"
REPORT = ROOT / "g3/v33/M1_benchmark_v1.json"
MARKDOWN = RUNS / "M1_bench_v1.md"
PLAN = ROOT / "g3/v33/bench_overlays/M1_evaluation_v1.json"
PLAN_SHA = "5be8bd6cb35a9d309c7c762a0ee0a2ff62e068c0f689875b4e0942fe2decf591"
KST = dt.timezone(dt.timedelta(hours=9))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")


def check(files):
    for path, expected in files.items():
        if sha(path) != expected:
            raise ValueError("input changed: " + str(path))


def preceding(phase):
    path = RUNS / ("M1_family_" + phase + "_01.finished.json")
    value = read(path)
    if value["status"] != "complete" or value["exit_code"] != 0:
        raise ValueError("preceding phase failed")
    check(value["source_sha256"])
    check(value["outputs_sha256"])
    check({value["log_path"]: value["log_sha256"]})
    return {str(path): sha(path)}


def main():
    phase = sys.argv[1]
    assert phase in ("freeze", "run", "report")
    assert not (RUNS.parent / "state/MEASURE_LOCK.json").exists()
    assert sha(PLAN) == PLAN_SHA
    sources = [ROOT / "experiments/v33" / name for name in
               ("oracle_m1.py", "worldsim_m1.py", "world_receiver_m1.py", "worldparams_m1.json",
                "bench_oracles_m1.py", "bench_action_pool_m1.py", "bench_m1_family.py",
                "bench_m1_report.py", "m1_pool_validation.py")]
    sources += [PLAN, ROOT / "docs/M1_mc_contract.md", Path(__file__).resolve()]
    before = {str(p): sha(p) for p in sources}
    command = [sys.executable, "-X", "utf8", "-I", "-B"]
    bound = {}
    if phase == "freeze":
        completed = read(RUNS / "M1_collection_01.finished.json")
        assert completed["exit_code"] == 0 and completed["unchanged"] and completed["inputs_valid"]
        bound[str(RUNS / "M1_collection_01.finished.json")] = sha(RUNS / "M1_collection_01.finished.json")
        command += [str(ROOT / "experiments/v33/bench_m1_family.py"), "freeze", "--plan", str(PLAN),
                    "--out", str(FAMILY), "--protocol-out", str(PROTOCOL), "--validated-out", str(VALIDATED)]
        outputs = [FAMILY, PROTOCOL, VALIDATED]
    else:
        bound.update(preceding("freeze"))
        bound[str(FAMILY)] = sha(FAMILY)
        if phase == "run":
            assert not POOL.exists()
            command += [str(ROOT / "experiments/v33/bench_m1_family.py"), "run", "--family", str(FAMILY),
                        "--sha256", sha(FAMILY), "--out", str(POOL)]
            outputs = []
        else:
            bound.update(preceding("run"))
            command += [str(ROOT / "experiments/v33/bench_m1_report.py"), "--family", str(FAMILY),
                        "--sha256", sha(FAMILY), "--pool", str(POOL), "--out", str(REPORT),
                        "--markdown", str(MARKDOWN)]
            outputs = [REPORT, MARKDOWN]
    label = "M1_family_" + phase + "_01"
    log = RUNS / (label + ".log")
    start_path = RUNS / (label + ".started.json")
    finish_path = RUNS / (label + ".finished.json")
    assert not any(p.exists() for p in [log, start_path, finish_path, *outputs])
    before.update(bound)
    record = {"phase": phase, "command": command, "source_sha256": before,
              "driver_pid": os.getpid(), "started_kst": dt.datetime.now(KST).isoformat(), "log_path": str(log)}
    timer = time.monotonic()
    with log.open("xb") as stream:
        process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=stream,
                                   stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        record["child_pid"] = process.pid
        write(start_path, record)
        code = process.wait()
    record.update(exit_code=code, elapsed_seconds=time.monotonic()-timer,
                  ended_kst=dt.datetime.now(KST).isoformat(), log_sha256=sha(log),
                  started_receipt_sha256=sha(start_path))
    try:
        check(before)
        record["outputs_sha256"] = {str(p): sha(p) for p in outputs} if code == 0 else {}
        record["status"] = "complete" if code == 0 else "failed"
    except Exception as exc:
        record.update(status="post_validation_failed", validation_error=repr(exc))
    write(finish_path, record)
    print(json.dumps({k: record[k] for k in ("phase", "status", "exit_code", "elapsed_seconds")}), flush=True)
    return 0 if record["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
