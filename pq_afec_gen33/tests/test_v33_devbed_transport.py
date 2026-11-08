import copy
import hashlib
import json
from pathlib import Path
import subprocess
from unittest.mock import Mock

import pytest

from experiments.v33 import devbed
from experiments.v33.lib import arms, transport


class FakeProcesses:
    def __init__(self):
        self.calls = []
        self.processes = []
        self.time = 0
        self.client_rc = 0
        self.server_rc = 0
        self.malformed = False
        self.missing_stats = False
        self.missing_conn_log = False
        self.ready = True
        self.early_exit = False
        self.force_kill = False
        self.client_timeout = False
        self.tc_failure = False
        self.failed_rows = False

    def sleep(self, value):
        self.time += value

    def run(self, command, **kwargs):
        self.calls.append(command)
        if "tc" in command:
            return subprocess.CompletedProcess(command, 2 if self.tc_failure else 0,
                                               b"qdisc netem 1: root\n Sent 100 bytes 1 pkt (dropped 0)\n", b"")
        if "certgen" in command:
            path = Path(command[command.index("-cert-file") + 1])
            path.write_bytes(b"synthetic certificate fixture")
            size = int(command[command.index("-certsize") + 1])
            metadata = {"label": "development", "der_bytes": size,
                        "der_sha256": "e" * 64,
                        "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            return subprocess.CompletedProcess(command, 0, json.dumps(metadata).encode(), b"")
        if self.client_timeout:
            raise subprocess.TimeoutExpired(command, 10)
        count = int(command[command.index("-n") + 1])
        row = b'{"ok":false,"ms":10000}\n' if self.failed_rows else b'{"ok":true,"ms":50}\n'
        data = b"bad json\n" if self.malformed else row * count
        kwargs["stdout"].write(data)
        if not self.missing_stats:
            Path(command[command.index("-stats") + 1]).write_text('{"trials":1}', encoding="utf-8")
        return subprocess.CompletedProcess(command, self.client_rc)

    def popen(self, command, **kwargs):
        self.calls.append(command)
        owner = self
        class Process:
            def __init__(self):
                self.pid = 100
                self.terminated = False
                self.killed = False
                self.code = owner.server_rc if owner.early_exit else None
            def poll(self):
                return self.code
            def terminate(self):
                self.terminated = True
            def kill(self):
                self.killed = True
            def wait(self, timeout):
                if owner.force_kill and not self.killed:
                    raise subprocess.TimeoutExpired(command, timeout)
                self.code = owner.server_rc
                Path(command[command.index("-stats") + 1]).write_text('{"tls_accepted":1}', encoding="utf-8")
                if "-conn-log" in command and not owner.missing_conn_log:
                    Path(command[command.index("-conn-log") + 1]).write_bytes(b"")
                return self.code
        if self.ready:
            kwargs["stderr"].write(b"READY fixture:1234\n")
            kwargs["stderr"].flush()
        process = Process()
        self.processes.append(process)
        return process


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(transport.netbed, "require_root", Mock())
    monkeypatch.setattr(transport.netbed, "require_bin", Mock())
    monkeypatch.setattr(transport.os, "access", lambda *args: True)
    plan = json.loads((Path(__file__).resolve().parents[1] / "g3/v33/plans/final_bundle_v1.json").read_text(encoding="utf-8"))
    binaries = {}
    for key, info in plan["binaries"].items():
        path = tmp_path / "binaries" / key / "qamp"
        path.parent.mkdir(parents=True)
        path.write_bytes(key.encode())
        info["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        Path(str(path) + ".srcsha").write_text(info["srcsha"], encoding="utf-8")
        binaries[key] = path
    fake = FakeProcesses()
    backend = transport.Transport(plan, home / "v33_runs" / "fixture", binary_paths=binaries,
                                  plan_sha256="a" * 64, run=fake.run, popen=fake.popen,
                                  sleep=fake.sleep, monotonic=lambda: fake.time)
    return backend, fake, plan


def fixed_unit(plan, task="M0", arm="m4L3"):
    return next(unit for unit in arms.iter_units(plan, task) if unit["arm"] == arm)


def test_binary_identity_checked_and_gen33_gate_used(runtime):
    backend, fake, plan = runtime
    identities = backend.verify_binaries()
    assert set(identities) == {"gen33", "g3c", "g2"}
    transport.netbed.require_bin.assert_called_once_with(backend.binary_paths["gen33"])
    assert not fake.calls
    backend.binary_paths["g2"].write_bytes(b"changed binary")
    with pytest.raises(transport.TransportError, match="지문 불일치"):
        backend.verify_binaries()


def test_srcsha_mismatch_refuses_before_execution(runtime):
    backend, fake, plan = runtime
    Path(str(backend.binary_paths["g3c"]) + ".srcsha").write_text("0" * 64, encoding="utf-8")
    with pytest.raises(transport.TransportError, match="지문 불일치"):
        backend.run_unit(fixed_unit(plan, "M1", "a"))
    assert not fake.calls and not backend.raw_dir.exists()


def test_certificate_created_once_per_cell_and_reverified(runtime):
    backend, fake, plan = runtime
    unit = fixed_unit(plan)
    first = backend.prepare_certificate(unit)
    second = backend.prepare_certificate(unit)
    assert first == second
    assert len(fake.calls) == 1
    path = Path(first["path"])
    assert path.parent == backend.raw_dir / "certs"
    path.write_bytes(b"changed fixture")
    with pytest.raises(transport.TransportError, match="지문 불일치"):
        backend.prepare_certificate(unit)


def test_frozen_server_does_not_generate_certificate(runtime):
    backend, fake, plan = runtime
    assert backend.prepare_certificate(fixed_unit(plan, "M1", "a")) is None
    assert not fake.calls


def test_raw_dir_must_be_named_run_under_home(runtime, tmp_path):
    backend, fake, plan = runtime
    with pytest.raises(transport.TransportError, match="v33_runs"):
        transport.Transport(plan, tmp_path / "wrong")


def test_isolation_rejection_precedes_mutation(runtime, monkeypatch):
    backend, fake, plan = runtime
    monkeypatch.setattr(transport.netbed, "require_root", Mock(side_effect=RuntimeError("namespace")))
    with pytest.raises(RuntimeError, match="namespace"):
        backend.run_unit(fixed_unit(plan))
    assert not backend.raw_dir.exists() and not fake.calls


def test_complete_unit_preserves_raw_data_and_provenance(runtime):
    backend, fake, plan = runtime
    unit = fixed_unit(plan)
    payload = backend.run_unit(unit)
    assert len(payload["rows"]) == unit["rows_expected"]
    assert payload["client_rc"] == payload["server"]["returncode"] == 0
    assert payload["server"]["forced_kill"] is False
    assert payload["server"]["exited_before_stop"] is False
    assert payload["server"]["stats"] == {"tls_accepted": 1}
    assert payload["client_stats"] == {"trials": 1}
    assert payload["commands"]["server"][:4] == ["ip", "netns", "exec", "peer"]
    assert payload["commands"]["client"][0] == str(backend.binary_paths["gen33"])
    assert fake.time == arms.settle_s(unit["profile"])
    assert fake.processes[0].terminated
    assert all(row["binary_sha256"] == plan["binaries"]["gen33"]["sha256"] and row["plan_sha256"] == "a" * 64 for row in payload["rows"])
    assert all(Path(path).is_file() for path in payload["raw_files"].values())
    assert "synthetic certificate fixture" not in json.dumps(payload)
    assert set(payload["tc_before"]) == set(payload["tc_after"]) == {"c2s", "s2c"}
    assert "dropped 0" in payload["tc_before"]["c2s"]["stdout"]


def test_frozen_server_payload_and_stable_distinct_ports(runtime):
    backend, fake, plan = runtime
    unit = fixed_unit(plan, "M1", "a")
    payload = backend.run_unit(unit)
    assert payload["server"]["conn_log_path"] is None
    assert payload["server"]["certificate"] is None
    assert "conn_log" not in payload["raw_files"]
    assert "-conn-log" not in payload["commands"]["server"]
    assert payload["rows"][0]["binary_sha256"] == plan["binaries"]["g3c"]["sha256"]
    other = copy.deepcopy(unit)
    other["trajectory"] = 3
    assert backend.address_for(other) == backend.address_for(unit)
    other["arm"] = "b"
    assert backend.address_for(other) != backend.address_for(unit)


def test_duplicate_attempt_refused_without_overwrite(runtime):
    backend, fake, plan = runtime
    unit = fixed_unit(plan)
    payload = backend.run_unit(unit)
    saved = Path(payload["raw_files"]["client_stdout"]).read_bytes()
    with pytest.raises(FileExistsError):
        backend.run_unit(unit)
    assert Path(payload["raw_files"]["client_stdout"]).read_bytes() == saved
    resumed = backend.run_unit(unit, attempt=1)
    assert resumed["raw_files"]["client_stdout"] != payload["raw_files"]["client_stdout"]


@pytest.mark.parametrize("failure", ["malformed", "missing_stats", "missing_conn_log", "client_timeout", "force_kill", "early_exit"])
def test_failures_keep_diagnostics_and_stop_server(runtime, failure):
    backend, fake, plan = runtime
    setattr(fake, failure, True)
    with pytest.raises(transport.TransportError) as error:
        backend.run_unit(fixed_unit(plan))
    payload = error.value.payload
    assert payload["started_at"] and payload["ended_at"]
    assert "raw_files" in payload
    assert fake.processes[0].terminated or fake.processes[0].poll() is not None
    if failure == "force_kill":
        assert payload["server"]["forced_kill"]


@pytest.mark.parametrize("side", ["client_rc", "server_rc"])
def test_nonzero_process_code_is_not_a_valid_unit(runtime, side):
    backend, fake, plan = runtime
    setattr(fake, side, 2)
    with pytest.raises(transport.TransportError, match="종료 코드"):
        backend.run_unit(fixed_unit(plan))


def test_readiness_timeout_stops_server_and_never_runs_client(runtime):
    backend, fake, plan = runtime
    fake.ready = False
    with pytest.raises(transport.TransportError, match="READY"):
        backend.run_unit(fixed_unit(plan))
    assert fake.time >= 15
    assert fake.processes[0].terminated
    assert not any("client" in command for command in fake.calls)


def test_cache_path_outside_run_is_rejected(runtime, tmp_path):
    backend, fake, plan = runtime
    unit = next(unit for unit in arms.iter_units(plan, "M0") if unit["arm"] == "v33none")
    with pytest.raises(transport.TransportError, match="실행 폴더 밖"):
        backend.run_unit(unit, cache_path=tmp_path / "elsewhere.json")
    assert not fake.calls


def test_every_unit_rechecks_binary_hash(runtime):
    backend, fake, plan = runtime
    unit = fixed_unit(plan)
    backend.run_unit(unit)
    backend.binary_paths["gen33"].write_bytes(b"changed")
    with pytest.raises(transport.TransportError, match="지문 불일치"):
        backend.run_unit(unit, attempt=1)
    assert len(fake.processes) == 1


def test_missing_plan_digest_stops_before_execution(runtime):
    backend, fake, plan = runtime
    backend.plan_sha256 = None
    with pytest.raises(transport.TransportError, match="SHA256"):
        backend.run_unit(fixed_unit(plan))
    assert not fake.calls


def test_tc_failure_is_preserved_and_prevents_client(runtime):
    backend, fake, plan = runtime
    fake.tc_failure = True
    with pytest.raises(transport.TransportError, match="tc 상태") as error:
        backend.run_unit(fixed_unit(plan))
    assert not fake.processes
    data = json.loads(Path(error.value.payload["raw_files"]["tc_before"]).read_text(encoding="utf-8"))
    assert data["c2s"]["returncode"] == 2


def test_handshake_failure_rows_are_kept_as_planned_observations(runtime):
    backend, fake, plan = runtime
    fake.failed_rows = True
    unit = fixed_unit(plan)
    payload = backend.run_unit(unit)
    assert len(payload["rows"]) == unit["connections"]
    assert all(row["ok"] is False for row in payload["rows"])
    assert payload["client_rc"] == 0
    assert payload["server"]["pid"] == 100


def test_existing_conn_log_refused_before_server_launch(runtime, monkeypatch):
    backend, fake, plan = runtime
    original = arms.server_command
    paths = []
    def stale(*args, **kwargs):
        path = kwargs["conn_log"]
        path.write_bytes(b"preserved stale log\n")
        paths.append(path)
        return original(*args, **kwargs)
    monkeypatch.setattr(arms, "server_command", stale)
    with pytest.raises(transport.TransportError, match="이미 있다"):
        backend.run_unit(fixed_unit(plan))
    assert not fake.processes
    assert paths[0].read_bytes() == b"preserved stale log\n"


def test_transport_payload_reaches_collection_and_resume_validator(runtime):
    backend, fake, plan = runtime
    unit = fixed_unit(plan)
    original_run, original_popen = fake.run, fake.popen
    conns = []
    def run(command, **kwargs):
        if "-mode" not in command or command[command.index("-mode") + 1] != "client":
            return original_run(command, **kwargs)
        for i in range(unit["rows_expected"]):
            scid = f"{i + 1:08x}"
            row = {"i": i, "ok": True, "ms": 50, "client_scid": scid,
                   "flight_expectation": {"source": "explicit", "k": unit["profile"]["expect_k"]},
                   "first_flight_bytes": 2560, "path_rtt_valid": False,
                   "feedback_wait_ns": 0, "feedback_wait_received": False}
            kwargs["stdout"].write((json.dumps(row) + "\n").encode())
            conns.append({"key": scid, "client_scid": scid, "initial_dcid": "0102030405060708",
                          "reason": "shutdown", "logged_ns": i + 1, "rx_bytes": 2560,
                          "rx_orig_bytes": 2560, "rx_parity_bytes": 0, "stack_bytes": 2560,
                          "beff_stack": 2560, "beff_phys": 2560, "beff_orig": 2560, "beff_parity": 0})
        Path(command[command.index("-stats") + 1]).write_text('{"trials":20}', encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)
    def popen(command, **kwargs):
        process = original_popen(command, **kwargs)
        wait = process.wait
        def finish(timeout):
            code = wait(timeout)
            path = Path(command[command.index("-conn-log") + 1])
            path.write_text("".join(json.dumps(row) + "\n" for row in reversed(conns)), encoding="utf-8")
            stats = {"bytes_in": 2560 * len(conns), "parities": 0, "recovered": 0,
                     "credit_parities": 0, "fb_sent": 0, "tls_accepted": len(conns) - 1,
                     "feedback_version": 2, "fec_parse_fail": 0, "conn_acct_evicted_lru": 0,
                     "conn_log": {"path": str(path), "lines": len(conns), "errors": 0, "pending": 0}}
            Path(command[command.index("-stats") + 1]).write_text(json.dumps(stats), encoding="utf-8")
            return code
        process.wait = finish
        return process
    backend.run, backend.popen = run, popen
    payload = backend.run_unit(unit)
    collection = devbed.collection_validation(plan, unit, payload)
    assert collection["execution_status"] == "판정 통과"
    assert collection["server"]["not_accepted"] == 1
    payload.update(collection=collection, checks={**collection["checks"], "ips": "pass"},
                   execution_status=collection["execution_status"],
                   server_delta=collection["server"]["server_delta"], cache_after=None)
    payload["raw_sha256"] = {
        Path(path).relative_to(backend.raw_dir).as_posix(): hashlib.sha256(Path(path).read_bytes()).hexdigest()
        for path in payload["raw_files"].values()}
    provenance = {"plan_sha256": "a" * 64, "plan_files": [{"committed_at": 1}]}
    validate = devbed.unit_validator(plan, provenance, backend.raw_dir, backend)
    validate(unit, payload)
    payload["server_delta"]["bytes_in"] += 1
    with pytest.raises(devbed.PlanError, match="원자료 재검사|단위 집계"):
        validate(unit, payload)
