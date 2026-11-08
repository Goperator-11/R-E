import base64
import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from experiments.v33.lib import launch_windows as launch


@pytest.fixture
def windows(monkeypatch, tmp_path):
    startup = SimpleNamespace(dwFlags=8, wShowWindow=7)
    monkeypatch.setattr(launch.sys, "platform", "win32")
    monkeypatch.setattr(launch.subprocess, "STARTUPINFO", lambda: startup, raising=False)
    monkeypatch.setattr(launch.subprocess, "STARTF_USESHOWWINDOW", 1, raising=False)
    command = [sys.executable, "-I", "-B", "launcher.py", "--supervise", "config.json"]
    return command, tmp_path, tmp_path / "detach.jsonl", startup


def test_breakaway_owns_hidden_console_and_redirects_handles(windows, monkeypatch):
    command, cwd, log_path, startup = windows
    spawn = Mock(return_value=SimpleNamespace(pid=123))
    wmi = Mock()
    monkeypatch.setattr(launch.subprocess, "Popen", spawn)
    monkeypatch.setattr(launch.subprocess, "run", wmi)
    result = launch.detach(command, cwd=cwd, log_path=log_path)
    assert result == {"pid": 123, "method": "breakaway"}
    spawn.assert_called_once()
    wmi.assert_not_called()
    assert spawn.call_args.args == (command,)
    options = spawn.call_args.kwargs
    assert options["creationflags"] == 0x01000210
    assert options["startupinfo"] is startup
    assert startup.dwFlags == 9
    assert startup.wShowWindow == 0
    assert options["cwd"] == str(cwd)
    assert options["stdin"] == subprocess.DEVNULL
    assert options["stderr"] == subprocess.STDOUT
    assert options["stdout"].name == str(log_path)
    assert options["stdout"].closed
    assert options["close_fds"] is True
    assert options["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
    assert options["env"]["PYTHONIOENCODING"] == "utf-8"
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert [event["event"] for event in events] == ["detach_attempt", "supervisor_created"]


def test_refused_breakaway_uses_explicit_hidden_wmi_once(windows, monkeypatch):
    command, cwd, log_path, startup = windows
    spawn = Mock(side_effect=OSError("breakaway refused"))
    wmi = Mock(return_value=subprocess.CompletedProcess([], 0, '{"ReturnValue":0,"ProcessId":456}', ""))
    monkeypatch.setattr(launch.subprocess, "Popen", spawn)
    monkeypatch.setattr(launch.subprocess, "run", wmi)
    result = launch.detach(command, cwd=cwd, log_path=log_path)
    assert result == {"pid": 456, "method": "wmi", "fallback_reason": "OSError: breakaway refused"}
    spawn.assert_called_once()
    wmi.assert_called_once()
    options = wmi.call_args.kwargs
    assert options["creationflags"] == 0x08000000
    assert options["startupinfo"] is startup
    assert options["stdin"] == subprocess.DEVNULL
    assert options["close_fds"] is True
    assert options["timeout"] == 60
    invocation = wmi.call_args.args[0]
    assert invocation[:-1] == ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand"]
    script = base64.b64decode(invocation[-1]).decode("utf-16-le")
    assert "Invoke-CimMethod -ClassName Win32_Process -MethodName Create" in script
    assert "ShowWindow=[uint16]0; CreateFlags=[uint32]16777744" in script
    assert "ProcessStartupInformation=$startup" in script
    assert "ConvertTo-Json -Compress" in script
    assert "breakaway_failed" in log_path.read_text(encoding="utf-8")


def test_wmi_quoting_keeps_unicode_spaces_quotes_and_shell_metacharacters(tmp_path):
    command = [r"C:\Program Files\Python\python.exe", "-I", "-B", r"C:\실행 파일\launcher's.py", 'a"b', "$(whoami); & x"]
    path = tmp_path / "parent's 공간"
    encoded = launch._wmi_command(command, path)[-1]
    script = base64.b64decode(encoded).decode("utf-16-le")
    assert "CommandLine='" + subprocess.list2cmdline(command).replace("'", "''") + "';" in script
    assert "CurrentDirectory='" + str(path).replace("'", "''") + "';" in script
    assert "launcher''s.py" in script
    assert "$(whoami); & x" in script


@pytest.mark.parametrize("code,stdout,stderr,error", [
    (1, '{"ReturnValue":0,"ProcessId":456}', "denied", "PowerShell exit 1"),
    (0, '{"ReturnValue":2,"ProcessId":456}', "", "ReturnValue=2"),
    (0, '{"ReturnValue":"0","ProcessId":456}', "", "ReturnValue='0'"),
    (0, '{"ReturnValue":false,"ProcessId":456}', "", "ReturnValue=False"),
    (0, '{"ReturnValue":0,"ProcessId":0}', "", "ProcessId=0"),
    (0, '{"ReturnValue":0,"ProcessId":-1}', "", "ProcessId=-1"),
    (0, '{"ReturnValue":0,"ProcessId":true}', "", "ProcessId=True"),
    (0, '{"ReturnValue":0,"ProcessId":4294967296}', "", "ProcessId=4294967296"),
    (0, '{"ReturnValue":0,"ProcessId":"456"}', "", "ProcessId='456'"),
    (0, '{"ReturnValue":0}', "", "ProcessId=None"),
    (0, '{"ProcessId":456}', "", "ReturnValue=None"),
    (0, '[]', "", "non-object"),
    (0, '456', "", "non-object"),
    (0, 'unexpected text\n{"ReturnValue":0,"ProcessId":456}', "", "invalid JSON"),
])
def test_wmi_failure_is_not_reported_as_created(windows, monkeypatch, code, stdout, stderr, error):
    command, cwd, log_path, _ = windows
    spawn = Mock(side_effect=OSError("breakaway refused"))
    wmi = Mock(return_value=subprocess.CompletedProcess([], code, stdout, stderr))
    monkeypatch.setattr(launch.subprocess, "Popen", spawn)
    monkeypatch.setattr(launch.subprocess, "run", wmi)
    with pytest.raises(RuntimeError, match=error):
        launch.detach(command, cwd=cwd, log_path=log_path)
    spawn.assert_called_once()
    wmi.assert_called_once()
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert events[-1]["event"] == "wmi_failed"
    assert "breakaway refused" in events[-1]["fallback_reason"]
    assert all(event["event"] != "supervisor_created" for event in events)


@pytest.mark.parametrize("error", [OSError("PowerShell missing"), subprocess.TimeoutExpired("powershell.exe", 60)])
def test_wmi_transport_failure_is_preserved_without_retry(windows, monkeypatch, error):
    command, cwd, log_path, _ = windows
    spawn = Mock(side_effect=OSError("breakaway refused"))
    wmi = Mock(side_effect=error)
    monkeypatch.setattr(launch.subprocess, "Popen", spawn)
    monkeypatch.setattr(launch.subprocess, "run", wmi)
    with pytest.raises(RuntimeError, match="BREAKAWAY failed.*WMI failed"):
        launch.detach(command, cwd=cwd, log_path=log_path)
    spawn.assert_called_once()
    wmi.assert_called_once()
    assert "wmi_failed" in log_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("command", [[], [""], ["a\x00b"], ["python", None], "python"])
def test_invalid_argument_list_does_not_launch(windows, monkeypatch, command):
    _, cwd, log_path, _ = windows
    spawn = Mock()
    monkeypatch.setattr(launch.subprocess, "Popen", spawn)
    with pytest.raises(ValueError, match="argument list"):
        launch.detach(command, cwd=cwd, log_path=log_path)
    spawn.assert_not_called()
    assert not log_path.exists()


def test_non_windows_rejected_without_starting_child(tmp_path, monkeypatch):
    monkeypatch.setattr(launch.sys, "platform", "linux")
    spawn = Mock()
    monkeypatch.setattr(launch.subprocess, "Popen", spawn)
    with pytest.raises(RuntimeError, match="requires Windows"):
        launch.detach(["python"], cwd=tmp_path, log_path=tmp_path / "log")
    spawn.assert_not_called()


def test_invalid_direct_pid_is_not_retried(windows, monkeypatch):
    command, cwd, log_path, _ = windows
    monkeypatch.setattr(launch.subprocess, "Popen", Mock(return_value=SimpleNamespace(pid=0)))
    wmi = Mock()
    monkeypatch.setattr(launch.subprocess, "run", wmi)
    with pytest.raises(RuntimeError, match="invalid PID"):
        launch.detach(command, cwd=cwd, log_path=log_path)
    wmi.assert_not_called()


def test_log_open_failure_prevents_launch(windows, monkeypatch):
    command, cwd, _, _ = windows
    spawn = Mock()
    monkeypatch.setattr(launch.subprocess, "Popen", spawn)
    with pytest.raises(FileNotFoundError):
        launch.detach(command, cwd=cwd, log_path=cwd / "missing" / "log")
    spawn.assert_not_called()
