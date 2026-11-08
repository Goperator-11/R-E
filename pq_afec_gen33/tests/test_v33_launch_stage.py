import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from experiments.v33 import devbed
from experiments.v33.lib import blocks, launch_stage as stage, netbed


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    local_home = tmp_path / "home"
    local_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: local_home))
    monkeypatch.setattr(stage, "require_linux", lambda: None)
    monkeypatch.setattr(stage, "ensure_idle", lambda: None)
    plan, _ = devbed.read_plan(ROOT / "g3/v33/plans/final_bundle_v1.json")
    source = tmp_path / "frozen"
    for name, info in plan["binaries"].items():
        binary = source / name / "qamp"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(("binary:" + name).encode())
        binary.chmod(0o755)
        info["path"] = str(binary)
        info["sha256"] = stage.sha256(binary)
        info["srcsha"] = hashlib.sha256(name.encode()).hexdigest()
        Path(str(binary) + ".srcsha").write_text(info["srcsha"] + "\n", encoding="utf-8")
        if name == "gen33":
            Path(str(binary) + ".sha256").write_text(info["sha256"] + "  qamp\n", encoding="utf-8")
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    digest = stage.sha256(plan_path)
    provenance = {"plan_sha256": digest, "plan_commit": "a" * 40}
    monkeypatch.setattr(devbed, "verify_committed_plan", lambda *args: provenance)
    monkeypatch.setattr(devbed, "load_reporter", lambda: object())
    def verify_gen33(path):
        assert Path(str(path) + ".sha256").read_text(encoding="utf-8").split()[0] == stage.sha256(path)
    monkeypatch.setattr(netbed, "require_bin", verify_gen33)
    config = {"plan": str(plan_path), "task": "M0", "run_id": "fixture_run",
              "mode": "smoke", "lock": str(tmp_path / "MEASURE_LOCK.json"),
              "artifacts_dir": str(tmp_path / "artifacts"), "m1_result": None,
              "plan_sha256": digest}
    return config, plan, local_home, provenance


def snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_preflight_has_no_writes_and_copies_are_outside_tmp(fixture):
    config, plan, local_home, _ = fixture
    before = snapshot(local_home.parent)
    result = stage.prepare(config, copy=False)
    assert snapshot(local_home.parent) == before
    assert not (local_home / "v33_runs").exists()
    assert result["copied"] is False
    assert all(Path(path).is_relative_to(local_home / "v33_runs" / config["run_id"] / "bin")
               for path in result["binary_paths"].values())


def test_prepare_keeps_source_bytes_and_passes_real_copies_to_devbed(fixture):
    config, plan, local_home, _ = fixture
    before = snapshot(local_home.parent / "frozen")
    result = stage.prepare(config)
    assert snapshot(local_home.parent / "frozen") == before
    raw = Path(result["raw_dir"])
    assert {path.name for path in raw.iterdir()} == {"bin"}
    for name, path in result["binary_paths"].items():
        assert stage.sha256(path) == plan["binaries"][name]["sha256"]
        assert Path(path).name == "qamp"
        assert Path(str(path) + ".srcsha").read_text(encoding="utf-8").strip() == plan["binaries"][name]["srcsha"]
        assert name + "=" + path in result["command"]
    assert result["command"][:5] == ["unshare", "-Urnm", sys.executable, "-I", "-B"]
    assert result["command"][5] == str(Path(devbed.__file__).resolve())
    assert "--smoke" in result["command"]
    assert result["status_file"] == str(raw / "status_fixture_run.json")
    assert not Path(config["lock"]).exists()
    assert not Path(result["status_file"]).exists()
    assert not Path(result["done_marker"]).exists()
    assert not Path(config["artifacts_dir"]).exists()


def test_second_prepare_reuses_identical_copies_without_rewriting(fixture):
    config, _, local_home, _ = fixture
    first = stage.prepare(config)
    paths = [path for path in local_home.rglob("*") if path.is_file()]
    stamps = {path: path.stat().st_mtime_ns for path in paths}
    second = stage.prepare(config)
    assert first == second
    assert {path: path.stat().st_mtime_ns for path in paths} == stamps


@pytest.mark.parametrize("suffix", ["", ".srcsha", ".sha256"])
def test_existing_copy_corruption_fails_without_overwrite(fixture, suffix):
    config, _, local_home, _ = fixture
    result = stage.prepare(config)
    target = Path(result["binary_paths"]["gen33"] + suffix)
    target.write_bytes(b"corrupt")
    before = snapshot(local_home)
    with pytest.raises(stage.StageError, match="기존 실행 사본"):
        stage.prepare(config)
    assert snapshot(local_home) == before


@pytest.mark.parametrize("field", ["sha256", "srcsha"])
def test_source_identity_failure_prevents_all_destination_writes(fixture, field):
    config, plan, local_home, _ = fixture
    source = Path(plan["binaries"]["g3c"]["path"])
    target = source if field == "sha256" else Path(str(source) + ".srcsha")
    target.write_bytes(b"corrupt")
    with pytest.raises(RuntimeError, match="지문 불일치"):
        stage.prepare(config)
    assert not (local_home / "v33_runs").exists()


@pytest.mark.parametrize("mode", ["smoke", "run"])
def test_new_run_refuses_existing_raw_data(fixture, mode):
    config, _, local_home, _ = fixture
    config["mode"] = mode
    raw = local_home / "v33_runs" / config["run_id"]
    raw.mkdir(parents=True)
    (raw / "run.sh").write_bytes(b"old")
    with pytest.raises(stage.StageError, match="원자료가 이미"):
        stage.prepare(config)
    assert snapshot(raw) == {"run.sh": b"old"}


@pytest.mark.parametrize("mode", ["resume", "report-only"])
def test_resume_missing_manifest_refuses_writes(fixture, mode):
    config, _, local_home, _ = fixture
    config["mode"] = mode
    with pytest.raises(FileNotFoundError):
        stage.prepare(config)
    assert not (local_home / "v33_runs").exists()


def resumable(fixture, mode):
    config, plan, local_home, provenance = fixture
    first = stage.prepare(config)
    config["mode"] = mode
    manifest = {"run_id": config["run_id"], "task": config["task"], "provenance": provenance,
                "fingerprint": blocks.fingerprint(devbed.ROOT, config["plan_sha256"], plan["binaries"]),
                "m1_dependency": None}
    path = Path(first["raw_dir"]) / f"manifest_{config['run_id']}.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return first, path, manifest


@pytest.mark.parametrize("mode", ["resume", "report-only"])
def test_resume_uses_existing_binary_and_preserves_manifest(fixture, mode):
    config, _, local_home, _ = fixture
    first, path, _ = resumable(fixture, mode)
    before = snapshot(local_home)
    result = stage.prepare(config)
    assert "--" + mode in result["command"]
    assert result["binary_paths"] == first["binary_paths"]
    assert snapshot(local_home) == before


def test_resume_missing_copy_is_not_recreated(fixture):
    config, _, local_home, _ = fixture
    first, _, _ = resumable(fixture, "resume")
    missing = Path(first["binary_paths"]["g2"])
    missing.rename(missing.with_name("missing_saved"))
    with pytest.raises(stage.StageError, match="실행 사본이 없다"):
        stage.prepare(config)
    assert not missing.exists()


@pytest.mark.parametrize("field", ["run_id", "task", "provenance", "fingerprint", "m1_dependency"])
def test_resume_identity_is_checked_before_copy(fixture, field):
    config, _, local_home, _ = fixture
    _, path, manifest = resumable(fixture, "resume")
    manifest[field] = "bad"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    before = snapshot(local_home)
    with pytest.raises(stage.StageError, match="재개 manifest"):
        stage.prepare(config)
    assert snapshot(local_home) == before


@pytest.mark.parametrize("mode", ["smoke", "run", "resume"])
def test_remaining_lock_prevents_copy_and_is_preserved(fixture, mode):
    config, _, local_home, _ = fixture
    config["mode"] = mode
    lock = Path(config["lock"])
    lock.write_bytes(b"preserve")
    with pytest.raises(stage.StageError, match="잠금이 남아"):
        stage.prepare(config)
    assert lock.read_bytes() == b"preserve"
    assert not (local_home / "v33_runs").exists()


def test_report_only_leaves_lock_ownership_to_devbed(fixture):
    config, _, local_home, _ = fixture
    resumable(fixture, "report-only")
    lock = Path(config["lock"])
    lock.write_bytes(b"devbed checks this")
    stage.prepare(config)
    assert lock.read_bytes() == b"devbed checks this"


@pytest.mark.parametrize("value", ["../frozen", "x/y", "", "..", "a" * 81])
def test_invalid_run_id_rejected_before_writing(fixture, value):
    config, _, local_home, _ = fixture
    config["run_id"] = value
    with pytest.raises(stage.StageError, match="run ID"):
        stage.prepare(config)
    assert not (local_home / "v33_runs").exists()


def test_changed_plan_rejected_before_writing(fixture):
    config, _, local_home, _ = fixture
    config["plan_sha256"] = "0" * 64
    with pytest.raises(stage.StageError, match="계획 SHA"):
        stage.prepare(config)
    assert not (local_home / "v33_runs").exists()


@pytest.mark.parametrize("rc,stdout,stderr", [(0, "42 devbed.py", ""), (2, "", "error"),
                                            (1, "", "warning"), (1, "unexpected", "")])
def test_active_or_failed_process_query_is_rejected(monkeypatch, rc, stdout, stderr):
    monkeypatch.setattr(stage.subprocess, "run", lambda *args, **kwargs:
                        subprocess.CompletedProcess(args[0], rc, stdout, stderr))
    with pytest.raises(stage.StageError):
        stage.ensure_idle()


def test_absent_process_query_is_the_only_success(monkeypatch):
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 1, "", "")
    monkeypatch.setattr(stage.subprocess, "run", run)
    stage.ensure_idle()
    assert calls[0][0] == ["pgrep", "-af", "devbed"]
    assert calls[0][1]["timeout"] == 15


def test_process_query_exception_is_not_treated_as_absent(monkeypatch):
    def run(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 15)
    monkeypatch.setattr(stage.subprocess, "run", run)
    with pytest.raises(subprocess.TimeoutExpired):
        stage.ensure_idle()


def test_symlink_target_is_rejected_before_writing(fixture, monkeypatch):
    config, _, local_home, _ = fixture
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path:
                        path.name == "bin" or original(path))
    with pytest.raises(stage.StageError, match="symlink"):
        stage.prepare(config)
    assert not (local_home / "v33_runs").exists()


@pytest.mark.parametrize("field", ["raw_dir", "status_file", "done_marker"])
def test_config_path_mismatch_cannot_redirect_raw_writes(fixture, field):
    config, _, local_home, _ = fixture
    config[field] = str(local_home / "outside")
    with pytest.raises(stage.StageError, match="launcher 실행 경로"):
        stage.prepare(config)
    assert not (local_home / "v33_runs").exists()


@pytest.mark.parametrize("field", ["plan", "lock", "artifacts_dir"])
def test_relative_control_paths_are_rejected(fixture, field):
    config, _, local_home, _ = fixture
    config[field] = "relative"
    with pytest.raises(stage.StageError, match="절대 경로"):
        stage.prepare(config)
    assert not (local_home / "v33_runs").exists()


def test_preflight_detects_existing_copy_tamper(fixture):
    config, _, local_home, _ = fixture
    result = stage.prepare(config)
    Path(result["binary_paths"]["g2"]).write_bytes(b"different")
    before = snapshot(local_home)
    with pytest.raises(stage.StageError, match="기존 실행 사본"):
        stage.prepare(config, copy=False)
    assert snapshot(local_home) == before


def test_m1_result_is_validated_and_forwarded(fixture, monkeypatch):
    config, _, local_home, _ = fixture
    config.update(task="X1", mode="run", m1_result=str(local_home / "M1 result.json"))
    calls = []
    def dependency(plan, task, path, plan_sha):
        calls.append((task, path, plan_sha))
        return {"sha256": "a" * 64}
    monkeypatch.setattr(devbed, "m1_dependency", dependency)
    result = stage.prepare(config, copy=False)
    assert calls == [("X1", Path(config["m1_result"]), config["plan_sha256"])]
    index = result["command"].index("--m1-result")
    assert result["command"][index + 1] == config["m1_result"]
    assert "--run" in result["command"]


@pytest.mark.parametrize("method", ["verify_committed_plan", "load_reporter"])
def test_precommit_and_dependency_failure_precede_copies(fixture, monkeypatch, method):
    config, _, local_home, _ = fixture
    def failure(*args):
        raise devbed.PlanError("preflight failure")
    monkeypatch.setattr(devbed, method, failure)
    with pytest.raises(devbed.PlanError, match="preflight failure"):
        stage.prepare(config)
    assert not (local_home / "v33_runs").exists()


def test_platform_guard_rejects_windows(monkeypatch):
    monkeypatch.setattr(stage.sys, "platform", "win32")
    with pytest.raises(stage.StageError, match="Ubuntu WSL"):
        stage.require_linux()
