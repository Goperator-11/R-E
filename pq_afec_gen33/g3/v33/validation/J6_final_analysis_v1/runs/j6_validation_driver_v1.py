import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import time


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
CHECKER = RUNS / "j6_joint_artifact_check_v2.py"
CHECKER_SHA = 'cf7d3e7c3ebfb856a75f70f1001048a361d1db24630bccd821dc1b07490d7ee1'
OUT = RUNS / "J6_joint_artifact_check_v2.json"
KST = dt.timezone(dt.timedelta(hours=9))
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
read = lambda path: json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    assert sha(CHECKER) == CHECKER_SHA
    report_end = RUNS / "J6_joint_report_v1.finished.json"
    end = read(report_end)
    assert end["status"] == "complete" and end["exit_code"] == 0
    start_path, finish_path = RUNS / "J6_validation_v1.started.json", RUNS / "J6_validation_v1.finished.json"
    stdout, stderr = RUNS / "J6_validation_v1.stdout.txt", RUNS / "J6_validation_v1.stderr.txt"
    assert not any(path.exists() for path in (start_path, finish_path, stdout, stderr, OUT))
    family_path = RUNS / "J6_joint_action_family_v1.json"
    command = [sys.executable, "-I", "-B", str(CHECKER), "--out", str(OUT), "--family-sha256", sha(family_path)]
    inputs = {str(report_end): sha(report_end), str(family_path): sha(family_path), **end["published_outputs_sha256"]}
    assert all(sha(path) == expected for path, expected in inputs.items())
    common = {"command": command, "started_kst": dt.datetime.now(KST).isoformat(),
              "checker_sha256": CHECKER_SHA, "driver_sha256": sha(__file__), "inputs_sha256": inputs}
    save(start_path, common)
    timer, code, error = time.monotonic(), None, None
    try:
        with stdout.open("xb") as output, stderr.open("xb") as errors:
            process = subprocess.run(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=output, stderr=errors,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        code = process.returncode
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
    result = {**common, "ended_kst": dt.datetime.now(KST).isoformat(), "elapsed_seconds": time.monotonic() - timer,
              "exit_code": code, "error": error, "started_receipt_sha256": sha(start_path),
              "stdout_path": str(stdout), "stdout_sha256": sha(stdout), "stderr_path": str(stderr), "stderr_sha256": sha(stderr)}
    try:
        assert sha(CHECKER) == CHECKER_SHA and sha(__file__) == common["driver_sha256"]
        assert all(sha(path) == expected for path, expected in inputs.items())
        checked = read(OUT)
        assert checked["script_sha256"] == CHECKER_SHA
        result.update(status="complete" if code == 0 and checked["status"] == "pass" and error is None else "failed",
                      check_path=str(OUT), check_sha256=sha(OUT), checker_status=checked["status"])
    except Exception as exc:
        result.update(status="post_validation_failed", post_validation_error={"type": type(exc).__name__, "message": str(exc)})
    save(finish_path, result)
    print(json.dumps({key: result[key] for key in ("status", "exit_code", "elapsed_seconds")}), flush=True)
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
