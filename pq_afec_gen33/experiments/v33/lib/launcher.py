from __future__ import annotations

import argparse
import contextlib
import ctypes
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shlex
import subprocess
import sys
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.v33 import devbed
from experiments.v33.lib import blocks

LOOP = Path("C:/dev/codex_handoff/final")
KST = timezone(timedelta(hours=9))


class LaunchError(ValueError):
    pass


def wsl_path(path):
    value = PureWindowsPath(str(path))
    if not re.fullmatch(r"[A-Za-z]:", value.drive) or not value.root:
        raise LaunchError("WSL 경로 변환에는 Windows 절대 드라이브 경로가 필요하다")
    return "/mnt/" + value.drive[0].lower() + "/" + "/".join(value.parts[1:])


def timestamp():
    return datetime.now(KST).isoformat(timespec="seconds")


def run_checked(command, *, timeout=90):
    options = {}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=timeout, **options)
    if result.returncode:
        raise LaunchError(f"명령 실패 rc={result.returncode}: {result.stderr.strip()}")
    return result.stdout


def ensure_no_measurement():
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    result = subprocess.run(["wsl", "-d", "Ubuntu", "--exec", "pgrep", "-af", "devbed"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=30, **options)
    if result.returncode == 0:
        raise LaunchError("살아 있는 devbed가 있어 시작하지 않는다: " + result.stdout.strip())
    if result.returncode != 1:
        raise LaunchError(f"devbed 조회 실패 rc={result.returncode}: {result.stderr.strip()}")
    if result.stdout.strip() or result.stderr.strip():
        raise LaunchError("devbed 없음 응답에 예상하지 않은 출력이 있다")


def power_status():
    output = run_checked(["powercfg", "/q", "SCHEME_CURRENT", "SUB_BUTTONS", "LIDACTION"])
    indices = re.findall(r"0x([0-9a-fA-F]+)", output)
    if len(indices) < 2:
        raise LaunchError("충전 중 덮개 설정을 읽을 수 없다")

    class Power(ctypes.Structure):
        _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                    ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                    ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]

    value = Power()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(value)):
        raise LaunchError("전원 공급 상태를 읽을 수 없다")
    return {"lid_ac_index": int(indices[-2], 16), "ac_line_status": value.ACLineStatus,
            "powercfg_output": output}


def record_power_warning(power, morning):
    warnings = []
    if power["lid_ac_index"] != 0:
        warnings.append("충전 중 덮개를 닫으면 잠들 수 있다")
    if power["ac_line_status"] == 0:
        warnings.append("배터리로 측정한다")
    elif power["ac_line_status"] != 1:
        warnings.append("전원 공급 상태 미확인")
    if warnings:
        text = Path(morning).read_text(encoding="utf-8")
        with Path(morning).open("w", encoding="utf-8", newline="\n") as stream:
            stream.write("경고(" + timestamp() + "): " + ". ".join(warnings) + ".\n" + text)
    return warnings


def config_for(args, home):
    plan, digest = devbed.read_plan(args.plan)
    devbed.require_binary_identifiers(plan)
    devbed.verify_committed_plan(args.plan, plan, digest)
    task = "M0" if args.smoke else args.task
    if task not in plan["tasks"]:
        raise LaunchError("--task에 계획의 필수 과제 하나가 필요하다")
    if args.smoke and args.task not in (None, "M0"):
        raise LaunchError("--smoke는 M0만 실행한다")
    devbed.planned_summary(plan, digest, [task])
    devbed.m1_dependency(plan, task, args.m1_result, digest)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", args.run_id):
        raise LaunchError("run ID 형식 오류")
    until = datetime.fromisoformat(args.until)
    if until.tzinfo is None:
        until = until.replace(tzinfo=KST)
    minutes = plan["tasks"][task]["expected_minutes"] + plan["tasks"][task].get("additional_expected_minutes", 0)
    if until <= datetime.now(KST) + timedelta(minutes=minutes + 60):
        raise LaunchError("--until은 계획 예상 시간과 사망 확인 여유 60분보다 뒤여야 한다")
    mode = next(name for name in ("smoke", "run", "resume", "report_only") if getattr(args, name))
    raw = home.rstrip("/") + "/v33_runs/" + args.run_id
    return {"schema": "padfec3.launch/1", "root": wsl_path(ROOT),
            "plan": wsl_path(args.plan.resolve()), "plan_sha256": digest, "task": task,
            "card": plan["tasks"][task]["card"], "run_id": args.run_id,
            "mode": mode.replace("_", "-"), "lock": wsl_path(args.lock.resolve()),
            "artifacts_dir": wsl_path(args.artifacts_dir.resolve()),
            "m1_result": wsl_path(args.m1_result.resolve()) if args.m1_result else None,
            "raw_dir": raw, "status_file": raw + "/status_" + args.run_id + ".json",
            "done_marker": raw + "/DONE_" + args.run_id,
            "until": until.isoformat(), "windows_root": str(ROOT),
            "wakehold": str(LOOP / "tools/wakehold_v33.py"),
            "morning_report": str(LOOP / "runs/MORNING_REPORT.md")}


def recovery_command(args, mode):
    command = [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--" + mode,
               "--plan", str(args.plan.resolve()), "--task", "M0" if args.smoke else args.task,
               "--run-id", args.run_id, "--lock", str(args.lock.resolve()),
               "--artifacts-dir", str(args.artifacts_dir.resolve()), "--until", args.until]
    if args.m1_result is not None:
        command += ["--m1-result", str(args.m1_result.resolve())]
    return command


def make_run_script(config, config_path):
    command = ["python3", "-I", "-B", config["root"] + "/experiments/v33/lib/launcher.py",
               "--stage", wsl_path(config_path)]
    return "set -euo pipefail\nexport PYTHONDONTWRITEBYTECODE=1\ncd " + shlex.quote(config["root"]) + "\nexec " + shlex.join(command) + "\n"


def linux_call(config_path, mode):
    return ["wsl", "-d", "Ubuntu", "--exec", "python3", "-I", "-B",
            wsl_path(Path(__file__).resolve()), "--" + mode, wsl_path(config_path)]


def launch(args):
    if os.name != "nt":
        raise LaunchError("분리 실행은 Windows Python에서 호출한다")
    ensure_no_measurement()
    home = run_checked(["wsl", "-d", "Ubuntu", "--exec", "python3", "-I", "-B", "-c",
                        "from pathlib import Path; print(Path.home())"]).strip()
    if not home.startswith("/") or "\n" in home:
        raise LaunchError("WSL HOME 응답 오류")
    config = config_for(args, home)
    control_root = LOOP / "runs/launches" / args.run_id
    control = control_root / uuid.uuid4().hex
    control.mkdir(parents=True)
    config_path = control / "config.json"
    config.update({"control_dir": str(control), "control_root": str(control_root),
                   "launch_status": str(control / "launch_status.json"),
                   "resume_command": recovery_command(args, "resume"),
                   "report_only_command": recovery_command(args, "report-only")})
    devbed.write_new_json(config_path, config)
    script = control / "run.sh"
    with script.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(make_run_script(config, config_path))
    try:
        prepared = json.loads(run_checked(linux_call(config_path, "preflight"), timeout=120))
        devbed.write_new_json(control / "preflight.json", prepared)
        from experiments.v33.lib.launch_windows import detach
        command = [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--supervise", str(config_path)]
        receipt = detach(command, cwd=ROOT, log_path=control / "supervisor.log")
        receipt.update({"config": str(config_path), "launch_status": config["launch_status"],
                        "measurement_status": config["status_file"], "done_marker": config["done_marker"],
                        "state": "created", "created_at": timestamp()})
        devbed.write_new_json(control / "receipt.json", receipt)
        return receipt
    except BaseException as exc:
        devbed.write_new_json(control / "launch_error.json", {"error": str(exc), "at": timestamp()})
        raise


def acquire_mutex():
    kernel = ctypes.windll.kernel32
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel.ReleaseMutex.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateMutexW(None, False, "Local\\PADFEC_gen33_development_launcher")
    if not handle:
        raise LaunchError("Windows 측정 감독자 mutex 생성 실패")
    if kernel.WaitForSingleObject(handle, 0) not in (0, 0x80):
        kernel.CloseHandle(handle)
        raise LaunchError("다른 Windows 측정 감독자가 실행 중이다")
    return handle


def release_mutex(handle):
    ctypes.windll.kernel32.ReleaseMutex(handle)
    ctypes.windll.kernel32.CloseHandle(handle)


def supervise(config_path):
    if os.name != "nt":
        raise LaunchError("감독자는 Windows에서 실행해야 한다")
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    control = Path(config["control_dir"])
    state = {"schema": "padfec3.launch.status/1", "run_id": config["run_id"], "task": config["task"],
             "supervisor_pid": os.getpid(), "state": "starting", "started_at": timestamp(),
             "measurement_status": config["status_file"], "done_marker": config["done_marker"],
             "resume_command": config["resume_command"], "report_only_command": config["report_only_command"],
             "wake_until": config["until"]}

    def save(**updates):
        state.update(updates)
        state["updated_at"] = timestamp()
        blocks._atomic_json(config["launch_status"], state)

    def save_after_error(**updates):
        try:
            save(**updates)
        except (OSError, ValueError, RuntimeError) as exc:
            try:
                print(f"{timestamp()} launch status 기록 실패: {exc}", file=sys.stderr)
            except OSError:
                pass

    mutex = None
    wake = None
    child = None
    execution_state = False
    save()
    try:
        mutex = acquire_mutex()
        ensure_no_measurement()
        json.loads(run_checked(linux_call(config_path, "preflight"), timeout=120))
        power = power_status()
        warnings = record_power_warning(power, config["morning_report"])
        save(power=power, warnings=warnings)
        if not ctypes.windll.kernel32.SetThreadExecutionState(0x80000001):
            raise LaunchError("Windows 절전 방지 요청 실패")
        execution_state = True
        with (control / "wakehold.log").open("ab", buffering=0) as wake_log:
            wake = subprocess.Popen([sys.executable, "-I", "-B", config["wakehold"], config["until"],
                                     str(os.getpid()), "--ignore-stop"], stdin=subprocess.DEVNULL,
                                    stdout=wake_log, stderr=subprocess.STDOUT,
                                    creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
        if wake.poll() is not None:
            raise LaunchError("wakehold가 시작 직후 종료됐다")
        if config["mode"] == "resume":
            devbed.write_new_json(Path(config["control_root"]) / "resume_claim.json",
                                  {"config": str(config_path), "at": timestamp(), "supervisor_pid": os.getpid()})
        with (control / "wsl_stdout.log").open("ab", buffering=0) as stdout, (control / "wsl_stderr.log").open("ab", buffering=0) as stderr:
            child = subprocess.Popen(["wsl", "-d", "Ubuntu", "--exec", "bash", wsl_path(control / "run.sh")],
                                     cwd=config["windows_root"], stdin=subprocess.DEVNULL,
                                     stdout=stdout, stderr=stderr, creationflags=subprocess.CREATE_NO_WINDOW,
                                     close_fds=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            save(state="waiting_wsl", wsl_windows_pid=child.pid, wakehold_pid=wake.pid,
                 sleep_prevention_requested=True)
            while True:
                try:
                    code = child.wait(timeout=5)
                    break
                except subprocess.TimeoutExpired:
                    if execution_state and datetime.now(KST) >= datetime.fromisoformat(config["until"]):
                        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
                        execution_state = False
                        save(sleep_prevention_requested=False, wake_deadline_reached=True)
                    save(wakehold_returncode=wake.poll())
        save(state="wsl_exited", wsl_returncode=code, wakehold_returncode=wake.poll())
        if code != 0:
            save(state="failed")
            return code
        completion = json.loads(run_checked(linux_call(config_path, "inspect"), timeout=120))
        save(state="complete", completion=completion)
        return 0
    except BaseException as exc:
        save_after_error(state="failed", error=f"{type(exc).__name__}: {exc}")
        return 2
    finally:
        if child is not None and child.poll() is None:
            save_after_error(state="waiting_after_supervisor_error")
            code = child.wait()
            save_after_error(wsl_returncode=code, state="failed")
        try:
            if wake is not None and wake.poll() is None:
                wake.terminate()
                wake.wait(timeout=10)
        finally:
            if execution_state:
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            if mutex is not None:
                release_mutex(mutex)


def inspect_completion(config):
    from experiments.v33 import devreport
    from experiments.v33.lib.launch_stage import ensure_idle
    ensure_idle()
    status_path = Path(config["status_file"])
    status = json.loads(status_path.read_text(encoding="utf-8"))
    marker = json.loads(Path(config["done_marker"]).read_text(encoding="utf-8"))
    for value in (status, marker):
        if any(value.get(key) != expected for key, expected in
               (("run_id", config["run_id"]), ("task", config["card"]), ("status_file", str(status_path)))):
            raise LaunchError("측정 완료 식별자가 다르다")
    if (status.get("measurement_task") != config["task"]
            or status.get("lock_file") != config["lock"]
            or status.get("done_marker") != config["done_marker"]):
        raise LaunchError("측정 상태의 과제 또는 경로가 다르다")
    if status.get("state") != "complete" or marker.get("state") != "DONE" or Path(config["lock"]).exists():
        raise LaunchError("보고 완료·DONE·잠금 해제를 함께 확인하지 못했다")
    manifest = Path(config["artifacts_dir"]) / (config["task"] + "_artifacts.sha256")
    files = devreport.verify_artifacts(manifest)
    result_path = ROOT / "g3/v33/results" / f"v33_dev_{config['task']}_{config['run_id']}.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("schema") != "padfec3.devreport/1":
        raise LaunchError("완료 결과 schema가 다르다")
    journal = Path(config["raw_dir"]) / f"units_{config['run_id']}.jsonl"
    devbed.verify_report_artifacts({"result_path": result_path, "artifacts_manifest": manifest}, journal)
    if any(result.get(key) != config[key] for key in ("plan_sha256", "run_id", "task")):
        raise LaunchError("완료 결과의 계획 SHA 또는 실행 식별자가 다르다")
    return {"result_path": str(result_path), "artifacts_manifest": str(manifest),
            "verified_files": len(files), "result_checks": result.get("checks"),
            "measurement_status": status, "done": marker}


def parser():
    value = argparse.ArgumentParser(description="Windows 부모가 WSL 개발 측정을 끝까지 기다리는 launcher")
    mode = value.add_mutually_exclusive_group(required=True)
    for name in ("smoke", "run", "resume", "report-only"):
        mode.add_argument("--" + name, action="store_true")
    for name in ("supervise", "preflight", "stage", "inspect"):
        mode.add_argument("--" + name, type=Path)
    value.add_argument("--plan", type=Path, default=ROOT / "g3/v33/plans/final_bundle_v1.json")
    value.add_argument("--task")
    value.add_argument("--run-id")
    value.add_argument("--until")
    value.add_argument("--lock", type=Path, default=LOOP / "state/MEASURE_LOCK.json")
    value.add_argument("--artifacts-dir", type=Path)
    value.add_argument("--m1-result", type=Path)
    return value


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.supervise:
            os.environ.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
            with (args.supervise.parent / "supervisor_runtime.log").open("a", encoding="utf-8", buffering=1) as log:
                with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                    try:
                        return supervise(args.supervise)
                    except BaseException as exc:
                        print(f"{timestamp()} {type(exc).__name__}: {exc}", file=sys.stderr)
                        return 2
        internal = args.preflight or args.stage or args.inspect
        if internal:
            config = json.loads(internal.read_text(encoding="utf-8"))
            if args.inspect:
                result = inspect_completion(config)
            else:
                from experiments.v33.lib.launch_stage import prepare
                result = prepare(config, copy=bool(args.stage))
                if args.stage:
                    os.execvp(result["command"][0], result["command"])
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if not args.run_id or not args.until or args.artifacts_dir is None:
            raise LaunchError("--run-id, --until, --artifacts-dir가 필요하다")
        print(json.dumps(launch(args), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
