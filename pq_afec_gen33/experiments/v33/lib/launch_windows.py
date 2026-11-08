import base64
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path


DETACH_FLAGS = 0x01000210
CREATE_NO_WINDOW = 0x08000000


def _write_event(log, event, **fields):
    value = {"time": dt.datetime.now(dt.timezone.utc).isoformat(), "event": event, **fields}
    log.write((json.dumps(value, ensure_ascii=False) + "\n").encode("utf-8"))
    log.flush()


def _powershell_literal(value):
    return "'" + value.replace("'", "''") + "'"


def _wmi_command(command, cwd):
    source = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)",
        "$startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly "
        "-Property @{ShowWindow=[uint16]0; CreateFlags=[uint32]" + str(DETACH_FLAGS) + "}",
        "$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{"
        "CommandLine=" + _powershell_literal(subprocess.list2cmdline(command)) + "; "
        "CurrentDirectory=" + _powershell_literal(str(cwd)) + "; "
        "ProcessStartupInformation=$startup}",
        "[pscustomobject]@{ReturnValue=$r.ReturnValue; ProcessId=$r.ProcessId} | "
        "ConvertTo-Json -Compress",
    ])
    encoded = base64.b64encode(source.encode("utf-16-le")).decode("ascii")
    return ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]


def _parse_wmi_result(result):
    if result.returncode != 0:
        raise RuntimeError(f"WMI PowerShell exit {result.returncode}: {result.stderr.strip()}")
    try:
        value = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError("WMI returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError("WMI returned a non-object result")
    code = value.get("ReturnValue")
    pid = value.get("ProcessId")
    if type(code) is not int or code != 0:
        raise RuntimeError(f"WMI Create ReturnValue={code!r}")
    if type(pid) is not int or pid <= 0 or pid > 0xFFFFFFFF:
        raise RuntimeError(f"WMI Create invalid ProcessId={pid!r}")
    return pid


def detach(command: list[str], *, cwd: Path, log_path: Path) -> dict:
    if sys.platform != "win32":
        raise RuntimeError("Windows launcher requires Windows")
    if not isinstance(command, list) or not command or any(
        not isinstance(arg, str) or "\x00" in arg for arg in command
    ) or not command[0]:
        raise ValueError("command must be a nonempty string argument list without NUL")
    cwd = Path(cwd).resolve(strict=True)
    log_path = Path(log_path).resolve()
    if not cwd.is_dir():
        raise ValueError("launcher cwd must be a directory")
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    environment = dict(os.environ)
    environment.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    with log_path.open("ab", buffering=0) as log:
        _write_event(log, "detach_attempt", creationflags=DETACH_FLAGS)
        try:
            child = subprocess.Popen(
                command,
                cwd=str(cwd),
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=DETACH_FLAGS,
                startupinfo=startup,
                close_fds=True,
            )
        except OSError as exc:
            reason = f"{type(exc).__name__}: {exc}"
            _write_event(log, "breakaway_failed", reason=reason)
        else:
            if type(child.pid) is not int or child.pid <= 0:
                _write_event(log, "detach_failed", reason="CreateProcess returned invalid PID")
                raise RuntimeError("CreateProcess returned invalid PID")
            _write_event(log, "supervisor_created", method="breakaway", pid=child.pid)
            return {"pid": child.pid, "method": "breakaway"}
        try:
            result = subprocess.run(
                _wmi_command(command, cwd),
                cwd=str(cwd),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                creationflags=CREATE_NO_WINDOW,
                startupinfo=startup,
                close_fds=True,
            )
            pid = _parse_wmi_result(result)
        except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
            error = f"{type(exc).__name__}: {exc}"
            _write_event(log, "wmi_failed", reason=error, fallback_reason=reason)
            raise RuntimeError(f"BREAKAWAY failed ({reason}); WMI failed ({error})") from exc
        _write_event(log, "supervisor_created", method="wmi", pid=pid, fallback_reason=reason)
        return {"pid": pid, "method": "wmi", "fallback_reason": reason}
