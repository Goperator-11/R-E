import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import time


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
WRAPPER = ROOT / "experiments/v33/bench_learning_l5_report.py"
WRAPPER_SHA = '094d0aed5a3d4d21d89dcdfd8251402719862cd1a0b34e355334ed4b03fcd7e8'
COLLECTION = RUNS / "L5_full_v1_plan.json"
PREVIOUS = RUNS / "L1_action_family_v1.json"
DESIGN = ROOT / "docs/L5_server_response.md"
BOUND = {'C:\\dev\\codex_handoff\\v33\\runs\\L5_full_v1_plan.json': 'e96fe173b9ed7fd73a22ed276f0aca50a5228d14e5936d41de5089172bf09b7e', 'C:\\dev\\codex_handoff\\v33\\runs\\L1_action_family_v1.json': 'e315280cf0199ab36a77f2f8a6d5289bf80dc00553aae4b0599610e2a5ff5e35', 'C:\\dev\\pq_afec_gen33\\docs\\L5_server_response.md': '5242a872c2a298d8e803067b1c639111e0232d645c3dcdf35d7b1e58e39f9f10', 'C:\\dev\\codex_handoff\\v33\\runs\\L5_anchor_availability_v1.json': '65379a9b450d070c1b3ab4f5132f565ba496d4f48883c3cf3b0e81723b00d31e'}
FAMILY = RUNS / "L5_joint_action_family_v1.json"
POOL = RUNS / "L5_joint_action_pool_v1"
REPORT = ROOT / "g3/v33/L5_benchmark_v1.json"
MARKDOWN = RUNS / "L5_bench_v1.md"
KST = dt.timezone(dt.timedelta(hours=9))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def verify(files):
    for path, expected in files.items():
        if sha(path) != expected:
            raise ValueError("source changed: " + str(path))


def phase_identity(phase):
    path = RUNS / ("L5_joint_" + phase + "_v1.finished.json")
    value = read(path)
    start_path = RUNS / ("L5_joint_" + phase + "_v1.started.json")
    if value["status"] != "complete" or value["exit_code"] != 0 or value["launch_error"] is not None:
        raise ValueError("preceding " + phase + " did not complete")
    for key, expected in (("wrapper_sha256", WRAPPER_SHA), ("driver_sha256", sha(__file__))):
        if value[key] != expected or value[key + "_after"] != expected:
            raise ValueError("preceding " + phase + " source changed")
    verify(value["inputs_sha256"])
    verify(value["published_outputs_sha256"])
    verify({str(start_path): value["started_receipt_sha256"]})
    start = read(start_path)
    for key in ("command", "wrapper_sha256", "driver_sha256", "inputs_sha256", "plan_identity", "preceding_run"):
        if start[key] != value[key]:
            raise ValueError("preceding phase receipt mismatch")
    for kind in ("stdout", "stderr"):
        verify({value[kind + "_path"]: value[kind + "_sha256"]})
    if phase == "plan" and set(value["published_outputs_sha256"]) != {str(FAMILY)}:
        raise ValueError("plan publication inventory mismatch")
    return {"path": str(path), "sha256": sha(path), "outputs_sha256": value["published_outputs_sha256"]}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("plan", "run", "report"))
    args = parser.parse_args(argv)
    verify({str(WRAPPER): WRAPPER_SHA, **BOUND})
    inputs = dict(BOUND)
    driver_hash = sha(__file__)
    identity, preceding_run = None, None
    command = [sys.executable, "-I", "-B", str(WRAPPER)]
    if args.command == "plan":
        command += ["freeze-family", "--collection-plan", str(COLLECTION), "--previous-family", str(PREVIOUS), "--out", str(FAMILY)]
        outputs = [FAMILY]
    else:
        identity = phase_identity("plan")
        family_sha = sha(FAMILY)
        inputs[str(FAMILY)] = family_sha
        command += [args.command, "--family-plan", str(FAMILY), "--family-sha256", family_sha]
        if args.command == "run":
            if POOL.exists():
                raise ValueError("joint evaluation pool must be new")
            command += ["--out", str(POOL), "--workers", "8", "--time-budget-seconds", "300", "--loop"]
            outputs = []
        else:
            preceding_run = phase_identity("run")
            previous = read(preceding_run["path"])
            if previous["plan_identity"] != identity or previous["inputs_sha256"] != inputs:
                raise ValueError("preceding run used another plan")
            command += ["--pool-dir", str(POOL), "--out", str(REPORT), "--markdown", str(MARKDOWN)]
            outputs = [REPORT, Path(str(REPORT) + ".published.json"), MARKDOWN]
    stem = "L5_joint_" + args.command + "_v1"
    start_path, finish_path = RUNS / (stem + ".started.json"), RUNS / (stem + ".finished.json")
    stdout_path, stderr_path = RUNS / (stem + ".stdout.txt"), RUNS / (stem + ".stderr.txt")
    if any(path.exists() for path in outputs + [start_path, finish_path, stdout_path, stderr_path]):
        raise ValueError("phase outputs and receipts must be new")
    started, timer = dt.datetime.now(KST).isoformat(), time.monotonic()
    common = {"started_kst": started, "command": command, "wrapper_sha256": WRAPPER_SHA,
              "driver_sha256": driver_hash, "inputs_sha256": inputs, "plan_identity": identity, "preceding_run": preceding_run}
    save(start_path, common)
    exit_code, launch_error = None, None
    try:
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            process = subprocess.run(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        exit_code = process.returncode
    except Exception as exc:
        launch_error = {"type": type(exc).__name__, "message": str(exc)}
    receipt = {**common, "ended_kst": dt.datetime.now(KST).isoformat(), "elapsed_seconds": time.monotonic() - timer,
               "started_receipt_sha256": sha(start_path), "exit_code": exit_code, "launch_error": launch_error}
    for kind, path in (("stdout", stdout_path), ("stderr", stderr_path)):
        receipt[kind + "_path"] = str(path)
        receipt[kind + "_sha256"] = sha(path) if path.exists() else None
    try:
        receipt["wrapper_sha256_after"], receipt["driver_sha256_after"] = sha(WRAPPER), sha(__file__)
        verify({str(WRAPPER): WRAPPER_SHA, str(Path(__file__)): driver_hash, **inputs})
        if identity is not None and phase_identity("plan") != identity:
            raise ValueError("preceding plan changed during phase")
        if preceding_run is not None and phase_identity("run") != preceding_run:
            raise ValueError("preceding run changed during phase")
        receipt["published_outputs_sha256"] = {str(path): sha(path) for path in outputs} if exit_code == 0 else {}
        receipt["status"] = "complete" if exit_code == 0 and launch_error is None else "failed"
    except Exception as exc:
        receipt["status"] = "post_validation_failed"
        receipt["post_validation_error"] = {"type": type(exc).__name__, "message": str(exc)}
    save(finish_path, receipt)
    print(json.dumps({key: receipt[key] for key in ("status", "exit_code", "elapsed_seconds", "stdout_path", "stderr_path")}), flush=True)
    return 0 if receipt["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
