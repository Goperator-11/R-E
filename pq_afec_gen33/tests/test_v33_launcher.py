import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from experiments.v33.lib import launcher as launch
from experiments.v33.lib import launch_stage


def put_json(path, value):
    Path(path).write_text(json.dumps(value), encoding="utf-8")


class Process:
    def __init__(self, pid, result=0, waits=0):
        self.pid = pid
        self.returncode = None
        self.result = result
        self.remaining = waits
        self.wait = Mock(side_effect=self._wait)
        self.terminate = Mock(side_effect=self._terminate)

    def poll(self):
        return self.returncode

    def _wait(self, timeout=None):
        if self.remaining:
            self.remaining -= 1
            raise subprocess.TimeoutExpired("fixture", timeout)
        self.returncode = self.result
        return self.returncode

    def _terminate(self):
        self.returncode = 0


@pytest.fixture
def supervisor(tmp_path, monkeypatch):
    control = tmp_path / "control"
    control.mkdir()
    raw = tmp_path / "raw"
    raw.mkdir()
    config = {"schema": "padfec3.launch/1", "run_id": "fixture", "task": "M0", "card": "F26",
              "mode": "smoke", "until": "2100-01-01T00:00:00+09:00", "control_dir": str(control),
              "control_root": str(control), "launch_status": str(control / "launch_status.json"),
              "status_file": str(raw / "status_fixture.json"), "done_marker": str(raw / "DONE_fixture"),
              "resume_command": ["python", "-I", "-B", "launcher.py", "--resume"],
              "report_only_command": ["python", "-I", "-B", "launcher.py", "--report-only"],
              "wakehold": str(tmp_path / "wakehold.py"), "windows_root": str(tmp_path),
              "morning_report": str(tmp_path / "morning.md"), "lock": str(tmp_path / "measure.json")}
    Path(config["morning_report"]).write_text("원래 보고서\n", encoding="utf-8")
    path = control / "config.json"
    put_json(path, config)
    kernel = SimpleNamespace(SetThreadExecutionState=Mock(return_value=1))
    monkeypatch.setattr(launch.ctypes, "windll", SimpleNamespace(kernel32=kernel), raising=False)
    monkeypatch.setattr(launch, "os", SimpleNamespace(name="nt", getpid=lambda: 321, environ={}, execvp=Mock()))
    monkeypatch.setattr(launch, "wsl_path", lambda value: "/fixture/" + Path(value).name)
    monkeypatch.setattr(launch.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    acquire = Mock(return_value=1234)
    release = Mock()
    idle = Mock()
    checked = Mock(return_value='{"verified_files": 4}')
    monkeypatch.setattr(launch, "acquire_mutex", acquire)
    monkeypatch.setattr(launch, "release_mutex", release)
    monkeypatch.setattr(launch, "ensure_no_measurement", idle)
    monkeypatch.setattr(launch, "run_checked", checked)
    monkeypatch.setattr(launch, "power_status", lambda: {"lid_ac_index": 0, "ac_line_status": 1})
    wake = Process(333)
    child = Process(444)
    spawn = Mock(side_effect=[wake, child])
    monkeypatch.setattr(launch.subprocess, "Popen", spawn)
    return SimpleNamespace(path=path, config=config, kernel=kernel, acquire=acquire, release=release,
                           idle=idle, checked=checked, wake=wake, child=child, spawn=spawn, raw=raw)


def state(fixture):
    return json.loads(Path(fixture.config["launch_status"]).read_text(encoding="utf-8"))


def test_supervisor_waits_for_wsl_and_passes_actual_exit(supervisor):
    supervisor.child.result = 7
    supervisor.child.remaining = 2
    assert launch.supervise(supervisor.path) == 7
    assert supervisor.child.wait.call_count == 3
    assert all(call.kwargs == {"timeout": 5} for call in supervisor.child.wait.call_args_list)
    status = state(supervisor)
    assert status["state"] == "failed"
    assert status["wsl_returncode"] == 7
    assert status["wsl_windows_pid"] == 444
    assert status["supervisor_pid"] == 321
    assert supervisor.checked.call_count == 1
    assert not Path(supervisor.config["lock"]).exists()
    assert not Path(supervisor.config["done_marker"]).exists()
    assert not Path(supervisor.config["status_file"]).exists()
    supervisor.release.assert_called_once_with(1234)
    supervisor.wake.terminate.assert_called_once()


def test_supervisor_wakehold_has_supervisor_parent_and_hidden_wsl(supervisor):
    assert launch.supervise(supervisor.path) == 0
    wake_call, wsl_call = supervisor.spawn.call_args_list
    assert wake_call.args[0] == [sys.executable, "-I", "-B", supervisor.config["wakehold"],
                                 supervisor.config["until"], "321", "--ignore-stop"]
    assert wsl_call.args[0] == ["wsl", "-d", "Ubuntu", "--exec", "bash", "/fixture/run.sh"]
    for call in (wake_call, wsl_call):
        assert call.kwargs["creationflags"] == 0x08000000
        assert call.kwargs["stdin"] == subprocess.DEVNULL
        assert call.kwargs["close_fds"] is True
        assert call.kwargs["stdout"] != subprocess.PIPE
        assert call.kwargs["stderr"] != subprocess.PIPE
    assert wsl_call.kwargs["cwd"] == supervisor.config["windows_root"]
    assert state(supervisor)["state"] == "complete"
    assert state(supervisor)["completion"] == {"verified_files": 4}
    assert supervisor.checked.call_count == 2
    assert supervisor.kernel.SetThreadExecutionState.call_args_list[0].args == (0x80000001,)
    assert supervisor.kernel.SetThreadExecutionState.call_args_list[-1].args == (0x80000000,)


@pytest.mark.parametrize("boundary", ["mutex", "idle", "preflight", "wake_request", "wake_exit", "inspect"])
def test_supervisor_failure_boundaries_preserve_measurement_files(supervisor, boundary):
    lock = Path(supervisor.config["lock"])
    marker = Path(supervisor.config["done_marker"])
    measurement_status = Path(supervisor.config["status_file"])
    for path in (lock, marker, measurement_status):
        path.write_bytes(b"unrelated-existing-state")
    if boundary == "mutex":
        supervisor.acquire.side_effect = launch.LaunchError("occupied")
    elif boundary == "idle":
        supervisor.idle.side_effect = launch.LaunchError("busy")
    elif boundary == "preflight":
        supervisor.checked.side_effect = launch.LaunchError("preflight failed")
    elif boundary == "wake_request":
        supervisor.kernel.SetThreadExecutionState.return_value = 0
    elif boundary == "wake_exit":
        supervisor.wake.returncode = 1
    else:
        supervisor.checked.side_effect = ["{}", launch.LaunchError("artifact mismatch")]
    assert launch.supervise(supervisor.path) == 2
    assert state(supervisor)["state"] == "failed"
    assert "error" in state(supervisor)
    for path in (lock, marker, measurement_status):
        assert path.read_bytes() == b"unrelated-existing-state"
    if boundary in {"mutex", "idle", "preflight", "wake_request"}:
        supervisor.spawn.assert_not_called()
    if boundary == "mutex":
        supervisor.release.assert_not_called()
    else:
        supervisor.release.assert_called_once_with(1234)


def test_resume_claim_collision_prevents_second_resume(supervisor):
    supervisor.config["mode"] = "resume"
    put_json(supervisor.path, supervisor.config)
    claim = Path(supervisor.config["control_root"]) / "resume_claim.json"
    claim.write_bytes(b"earlier attempt")
    assert launch.supervise(supervisor.path) == 2
    assert claim.read_bytes() == b"earlier attempt"
    assert supervisor.spawn.call_count == 1
    supervisor.child.wait.assert_not_called()


def test_resume_creates_single_claim_before_wsl(supervisor):
    supervisor.config["mode"] = "resume"
    put_json(supervisor.path, supervisor.config)
    assert launch.supervise(supervisor.path) == 0
    claim = json.loads((Path(supervisor.config["control_root"]) / "resume_claim.json").read_text(encoding="utf-8"))
    assert claim["supervisor_pid"] == 321
    assert claim["config"] == str(supervisor.path)


def test_wake_deadline_does_not_stop_wsl(supervisor):
    supervisor.config["until"] = "2000-01-01T00:00:00+09:00"
    put_json(supervisor.path, supervisor.config)
    supervisor.child.remaining = 1
    assert launch.supervise(supervisor.path) == 0
    assert supervisor.child.wait.call_count == 2
    supervisor.child.terminate.assert_not_called()
    assert state(supervisor)["wake_deadline_reached"] is True
    assert state(supervisor)["sleep_prevention_requested"] is False
    assert supervisor.kernel.SetThreadExecutionState.call_count == 2


def test_status_write_failure_still_waits_for_live_wsl(supervisor, monkeypatch, capsys):
    original = launch.blocks._atomic_json
    writes = 0

    def broken_save(path, value):
        nonlocal writes
        writes += 1
        if writes >= 3:
            raise OSError("fixture status storage unavailable")
        original(path, value)

    monkeypatch.setattr(launch.blocks, "_atomic_json", broken_save)
    assert launch.supervise(supervisor.path) == 2
    supervisor.child.wait.assert_called_once_with()
    supervisor.child.terminate.assert_not_called()
    supervisor.release.assert_called_once_with(1234)
    assert "launch status 기록 실패" in capsys.readouterr().err
    assert not Path(supervisor.config["lock"]).exists()
    assert not Path(supervisor.config["done_marker"]).exists()


@pytest.mark.parametrize("wait_result,success", [(0, True), (0x80, True), (258, False), (0xFFFFFFFF, False)])
def test_named_mutex_accepts_only_acquired_or_abandoned(monkeypatch, wait_result, success):
    kernel = SimpleNamespace(CreateMutexW=Mock(return_value=4321), WaitForSingleObject=Mock(return_value=wait_result),
                             ReleaseMutex=Mock(), CloseHandle=Mock())
    monkeypatch.setattr(launch.ctypes, "windll", SimpleNamespace(kernel32=kernel), raising=False)
    if success:
        assert launch.acquire_mutex() == 4321
        kernel.CloseHandle.assert_not_called()
        launch.release_mutex(4321)
        kernel.ReleaseMutex.assert_called_once_with(4321)
    else:
        with pytest.raises(launch.LaunchError, match="감독자가 실행 중"):
            launch.acquire_mutex()
        kernel.ReleaseMutex.assert_not_called()
    kernel.CloseHandle.assert_called_once_with(4321)
    kernel.WaitForSingleObject.assert_called_once_with(4321, 0)


def test_named_mutex_creation_failure(monkeypatch):
    kernel = SimpleNamespace(CreateMutexW=Mock(return_value=0), WaitForSingleObject=Mock(), ReleaseMutex=Mock(), CloseHandle=Mock())
    monkeypatch.setattr(launch.ctypes, "windll", SimpleNamespace(kernel32=kernel), raising=False)
    with pytest.raises(launch.LaunchError, match="mutex 생성 실패"):
        launch.acquire_mutex()
    kernel.WaitForSingleObject.assert_not_called()
    kernel.CloseHandle.assert_not_called()


@pytest.fixture
def completion(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    root = tmp_path / "repo"
    result_dir = root / "g3/v33/results"
    result_dir.mkdir(parents=True)
    config = {"task": "M0", "card": "F26", "run_id": "fixture", "plan_sha256": "a" * 64,
              "status_file": str(raw / "status_fixture.json"), "done_marker": str(raw / "DONE_fixture"),
              "lock": str(tmp_path / "lock.json"), "artifacts_dir": str(artifacts), "raw_dir": str(raw)}
    status = {"run_id": "fixture", "task": "F26", "status_file": config["status_file"], "state": "complete",
              "measurement_task": "M0", "lock_file": config["lock"], "done_marker": config["done_marker"]}
    marker = {"run_id": "fixture", "task": "F26", "status_file": config["status_file"], "state": "DONE"}
    result = {"schema": "padfec3.devreport/1", "task": "M0", "run_id": "fixture", "plan_sha256": "a" * 64,
              "label": "development", "confirmatory": False, "policy_version": launch.devbed.learn3.POLICY_VERSION,
              "checks": {"fixture_check": "fail"}}
    put_json(config["status_file"], status)
    put_json(config["done_marker"], marker)
    result_path = result_dir / "v33_dev_M0_fixture.json"
    put_json(result_path, result)
    journal = raw / "units_fixture.jsonl"
    journal.write_text('{"fixture": true}\n', encoding="utf-8")
    manifest = artifacts / "M0_artifacts.sha256"

    def write_manifest(paths=None):
        files = paths if paths is not None else [result_path, journal]
        manifest.write_text("".join(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + str(path) + "\n"
                                    for path in files), encoding="utf-8")

    write_manifest()
    monkeypatch.setattr(launch, "ROOT", root)
    monkeypatch.setattr(launch_stage, "ensure_idle", Mock())
    return SimpleNamespace(config=config, status=status, marker=marker, result=result,
                           result_path=result_path, journal=journal, manifest=manifest, write_manifest=write_manifest)


def test_completion_verifies_artifacts_but_preserves_failed_measurement_checks(completion):
    value = launch.inspect_completion(completion.config)
    assert value["result_checks"] == {"fixture_check": "fail"}
    assert value["verified_files"] == 2
    assert value["result_path"] == str(completion.result_path)


@pytest.mark.parametrize("target,key,value", [
    ("status", "run_id", "another"), ("marker", "run_id", "another"),
    ("status", "task", "F27"), ("marker", "task", "F27"),
    ("status", "status_file", "other"), ("marker", "status_file", "other"),
    ("status", "measurement_task", "M1"), ("status", "lock_file", "other"),
    ("status", "done_marker", "other"), ("status", "state", "reporting"),
    ("marker", "state", "running"), ("result", "run_id", "another"),
    ("result", "task", "M1"), ("result", "plan_sha256", "b" * 64),
    ("result", "schema", "other"), ("result", "confirmatory", True),
    ("result", "policy_version", "other"),
])
def test_completion_rejects_wrong_identifiers_and_states(completion, target, key, value):
    data = getattr(completion, target)
    data[key] = value
    path = completion.result_path if target == "result" else completion.config["status_file" if target == "status" else "done_marker"]
    put_json(path, data)
    completion.write_manifest()
    with pytest.raises((ValueError, RuntimeError)):
        launch.inspect_completion(completion.config)


def test_completion_refuses_still_owned_measurement_lock(completion):
    lock = Path(completion.config["lock"])
    lock.write_bytes(b"owned")
    with pytest.raises(launch.LaunchError, match="잠금 해제"):
        launch.inspect_completion(completion.config)
    assert lock.read_bytes() == b"owned"


def test_completion_detects_hash_tampering(completion):
    completion.result_path.write_bytes(completion.result_path.read_bytes() + b" ")
    with pytest.raises((ValueError, RuntimeError)):
        launch.inspect_completion(completion.config)


def test_completion_requires_journal_in_sha_manifest(completion):
    completion.write_manifest([completion.result_path])
    with pytest.raises((ValueError, RuntimeError), match="저널"):
        launch.inspect_completion(completion.config)


@pytest.mark.parametrize("path,expected", [(r"C:\dev\a b\한글.json", "/mnt/c/dev/a b/한글.json"),
                                            ("D:/data/file", "/mnt/d/data/file")])
def test_windows_absolute_path_mapping(path, expected):
    assert launch.wsl_path(path) == expected


@pytest.mark.parametrize("path", ["relative/file", "C:relative", "/tmp/file", r"\\host\share\file"])
def test_ambiguous_wsl_path_rejected(path):
    with pytest.raises(launch.LaunchError, match="절대 드라이브"):
        launch.wsl_path(path)


def test_run_script_quotes_all_shell_arguments():
    root = "/mnt/c/repo's space/$(touch unwanted)"
    config_path = r"C:\config's space\$(touch unwanted).json"
    script = launch.make_run_script({"root": root}, config_path)
    lines = script.splitlines()
    assert shlex.split(lines[2]) == ["cd", root]
    assert shlex.split(lines[3]) == ["exec", "python3", "-I", "-B", root + "/experiments/v33/lib/launcher.py",
                                     "--stage", launch.wsl_path(config_path)]
    assert "nohup" not in script
    assert "setsid" not in script


@pytest.mark.parametrize("code,expected", [(0, "살아 있는"), (2, "조회 실패"), (255, "조회 실패")])
def test_process_query_failure_or_live_process_does_not_start(monkeypatch, code, expected):
    query = Mock(return_value=subprocess.CompletedProcess([], code, "123 devbed.py", "problem"))
    monkeypatch.setattr(launch.subprocess, "run", query)
    with pytest.raises(launch.LaunchError, match=expected):
        launch.ensure_no_measurement()
    assert query.call_args.args[0] == ["wsl", "-d", "Ubuntu", "--exec", "pgrep", "-af", "devbed"]


def test_process_query_no_match_is_idle(monkeypatch):
    monkeypatch.setattr(launch.subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 1, "", "")))
    launch.ensure_no_measurement()


def test_power_warning_is_prepended_without_changing_original(tmp_path):
    path = tmp_path / "morning.md"
    path.write_text("원래 표\n내용\n", encoding="utf-8")
    warnings = launch.record_power_warning({"lid_ac_index": 1, "ac_line_status": 0}, path)
    assert len(warnings) == 2
    assert path.read_text(encoding="utf-8").endswith("원래 표\n내용\n")
    assert "배터리" in path.read_text(encoding="utf-8").splitlines()[0]


def test_no_power_warning_preserves_file_bytes(tmp_path):
    path = tmp_path / "morning.md"
    path.write_bytes(b"unchanged\r\n")
    assert launch.record_power_warning({"lid_ac_index": 0, "ac_line_status": 1}, path) == []
    assert path.read_bytes() == b"unchanged\r\n"


@pytest.mark.parametrize("mode", ["--smoke", "--run", "--resume", "--report-only"])
def test_cli_missing_required_parameters_returns_two(mode, monkeypatch):
    spawn = Mock()
    monkeypatch.setattr(launch, "launch", spawn)
    assert launch.main([mode]) == 2
    spawn.assert_not_called()


@pytest.mark.parametrize("content", ["{", "[]", "null", '{}'])
def test_malformed_supervisor_config_has_runtime_failure_log(tmp_path, content):
    config = tmp_path / "config.json"
    config.write_text(content, encoding="utf-8")
    assert launch.main(["--supervise", str(config)]) == 2
    assert (tmp_path / "supervisor_runtime.log").stat().st_size > 0
    assert not (tmp_path / "launch_status.json").exists()


def test_cli_modes_are_mutually_exclusive():
    with pytest.raises(SystemExit) as error:
        launch.parser().parse_args(["--run", "--smoke"])
    assert error.value.code == 2


def test_launch_preflight_failure_records_error_without_detach(tmp_path, monkeypatch):
    from experiments.v33.lib import launch_windows
    monkeypatch.setattr(launch, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(launch, "LOOP", tmp_path)
    monkeypatch.setattr(launch, "ensure_no_measurement", Mock())
    monkeypatch.setattr(launch, "run_checked", Mock(side_effect=["/home/fixture\n", launch.LaunchError("preflight rejected")]))
    monkeypatch.setattr(launch, "config_for", lambda args, home: {"root": "/mnt/c/repo", "status_file": "raw/status", "done_marker": "raw/DONE"})
    monkeypatch.setattr(launch, "recovery_command", lambda args, mode: [mode])
    monkeypatch.setattr(launch, "wsl_path", lambda path: "/fixture/config.json")
    detach = Mock()
    monkeypatch.setattr(launch_windows, "detach", detach)
    args = SimpleNamespace(run_id="fixture")
    with pytest.raises(launch.LaunchError, match="preflight rejected"):
        launch.launch(args)
    detach.assert_not_called()
    errors = list((tmp_path / "runs/launches/fixture").glob("*/launch_error.json"))
    assert len(errors) == 1
    assert json.loads(errors[0].read_text(encoding="utf-8"))["error"] == "preflight rejected"
    assert not (tmp_path / "state/MEASURE_LOCK.json").exists()


@pytest.fixture
def configuration(tmp_path, monkeypatch):
    plan = {"tasks": {"M0": {"card": "F26", "expected_minutes": 10},
                      "M1": {"card": "F27", "expected_minutes": 20}}}
    monkeypatch.setattr(launch.devbed, "read_plan", Mock(return_value=(plan, "a" * 64)))
    identifiers = Mock()
    committed = Mock()
    summary = Mock()
    dependency = Mock()
    monkeypatch.setattr(launch.devbed, "require_binary_identifiers", identifiers)
    monkeypatch.setattr(launch.devbed, "verify_committed_plan", committed)
    monkeypatch.setattr(launch.devbed, "planned_summary", summary)
    monkeypatch.setattr(launch.devbed, "m1_dependency", dependency)
    monkeypatch.setattr(launch, "wsl_path", lambda path: "/mapped/" + Path(path).name)
    args = launch.parser().parse_args(["--smoke", "--run-id", "fixture", "--until", "2100-01-01T00:00:00+09:00",
                                      "--plan", str(tmp_path / "plan.json"), "--lock", str(tmp_path / "lock.json"),
                                      "--artifacts-dir", str(tmp_path / "artifacts")])
    return SimpleNamespace(plan=plan, args=args, identifiers=identifiers, committed=committed,
                           summary=summary, dependency=dependency)


def test_config_preserves_plan_run_card_and_recovery_paths(configuration):
    value = launch.config_for(configuration.args, "/home/fixture")
    assert value["schema"] == "padfec3.launch/1"
    assert value["mode"] == "smoke"
    assert value["task"] == "M0"
    assert value["card"] == "F26"
    assert value["raw_dir"] == "/home/fixture/v33_runs/fixture"
    assert value["status_file"] == "/home/fixture/v33_runs/fixture/status_fixture.json"
    assert value["done_marker"] == "/home/fixture/v33_runs/fixture/DONE_fixture"
    assert value["plan_sha256"] == "a" * 64
    configuration.identifiers.assert_called_once_with(configuration.plan)
    configuration.committed.assert_called_once_with(configuration.args.plan, configuration.plan, "a" * 64)
    configuration.summary.assert_called_once_with(configuration.plan, "a" * 64, ["M0"])
    configuration.dependency.assert_called_once_with(configuration.plan, "M0", None, "a" * 64)


@pytest.mark.parametrize("run_id", ["", "../outside", "a/b", " space", ".hidden", "a" * 81, "a\nnext"])
def test_config_refuses_unsafe_run_ids(configuration, run_id):
    configuration.args.run_id = run_id
    with pytest.raises(launch.LaunchError, match="run ID"):
        launch.config_for(configuration.args, "/home/fixture")


@pytest.mark.parametrize("task", ["M1", "missing"])
def test_smoke_cannot_change_measurement_task(configuration, task):
    configuration.args.task = task
    with pytest.raises(launch.LaunchError, match="M0만"):
        launch.config_for(configuration.args, "/home/fixture")


def test_run_requires_known_task(configuration):
    configuration.args.smoke = False
    configuration.args.run = True
    with pytest.raises(launch.LaunchError, match="필수 과제"):
        launch.config_for(configuration.args, "/home/fixture")


@pytest.mark.parametrize("until", ["2000-01-01T00:00:00+09:00", "invalid-time"])
def test_config_rejects_elapsed_or_invalid_wake_deadline(configuration, until):
    configuration.args.until = until
    with pytest.raises(ValueError):
        launch.config_for(configuration.args, "/home/fixture")


def test_recovery_preserves_m1_and_all_execution_arguments(configuration, tmp_path):
    args = configuration.args
    args.m1_result = tmp_path / "M1 result.json"
    command = launch.recovery_command(args, "report-only")
    assert command[0:3] == [sys.executable, "-I", "-B"]
    assert command[4] == "--report-only"
    for flag, value in (("--plan", str(args.plan.resolve())), ("--task", "M0"),
                        ("--run-id", "fixture"), ("--lock", str(args.lock.resolve())),
                        ("--artifacts-dir", str(args.artifacts_dir.resolve())),
                        ("--m1-result", str(args.m1_result.resolve())), ("--until", args.until)):
        assert command[command.index(flag) + 1] == value
