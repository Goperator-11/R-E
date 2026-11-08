from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from experiments.v33.lib import netbed


@pytest.fixture
def isolated(monkeypatch):
    original_read_text = netbed.Path.read_text
    original_stat = netbed.os.stat
    state = {"uid_map": "0 1000 1\n"}

    def read_text(path, *args, **kwargs):
        if path == netbed.Path("/proc/self/uid_map"):
            return state["uid_map"]
        return original_read_text(path, *args, **kwargs)

    def stat(path, *args, **kwargs):
        if path == "/proc/self/ns/user":
            return SimpleNamespace(st_dev=4, st_ino=11)
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(netbed.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(netbed.Path, "read_text", read_text)
    monkeypatch.setattr(netbed.os, "stat", stat)
    monkeypatch.setattr(netbed, "_namespace_owner", lambda name: (4, 11))
    return state


@pytest.mark.parametrize("failure", ["euid", "uid_map", "mount_owner", "net_owner", "owner_error"])
def test_namespace_failures_precede_mutation(monkeypatch, isolated, failure):
    if failure == "euid":
        monkeypatch.setattr(netbed.os, "geteuid", lambda: 1000)
    elif failure == "uid_map":
        isolated["uid_map"] = "0 0 4294967295\n"
    elif failure == "owner_error":
        monkeypatch.setattr(netbed, "_namespace_owner", Mock(side_effect=PermissionError("denied")))
    else:
        wrong = "mnt" if failure == "mount_owner" else "net"
        monkeypatch.setattr(netbed, "_namespace_owner", lambda name: (4, 12 if name == wrong else 11))
    process = Mock()
    mkdir = Mock()
    affinity = Mock()
    monkeypatch.setattr(netbed.subprocess, "run", process)
    monkeypatch.setattr(netbed.os, "makedirs", mkdir)
    monkeypatch.setattr(netbed.os, "sched_setaffinity", affinity, raising=False)
    for action in (lambda: netbed.run("never execute"), netbed.setup,
                   lambda: netbed.set_netem(25, journal=lambda event: None)):
        with pytest.raises(RuntimeError):
            action()
    process.assert_not_called()
    mkdir.assert_not_called()
    affinity.assert_not_called()


def test_namespace_requires_both_owners(monkeypatch, isolated):
    owner = Mock(return_value=(4, 11))
    monkeypatch.setattr(netbed, "_namespace_owner", owner)
    netbed.require_root()
    assert [call.args[0] for call in owner.call_args_list] == ["mnt", "net"]


def test_mount_failure_stops_before_directory_and_link_creation(monkeypatch):
    monkeypatch.setattr(netbed, "require_root", lambda: None)
    monkeypatch.setattr(netbed, "pin_cpus", lambda: [0, 1, 2, 3])
    runner = Mock(side_effect=RuntimeError("mount failed"))
    mkdir = Mock()
    monkeypatch.setattr(netbed, "run", runner)
    monkeypatch.setattr(netbed.os, "makedirs", mkdir)
    with pytest.raises(RuntimeError, match="mount failed"):
        netbed.setup()
    runner.assert_called_once_with("mount -t tmpfs none /run")
    mkdir.assert_not_called()


def test_setup_calls_static_arp_and_verifies_link(monkeypatch):
    monkeypatch.setattr(netbed, "require_root", lambda: None)
    monkeypatch.setattr(netbed, "pin_cpus", lambda: [1, 3, 5, 7])
    runner = Mock()
    arp = Mock()
    verify = Mock(return_value={"local": "local", "peer": "peer"})
    monkeypatch.setattr(netbed, "run", runner)
    monkeypatch.setattr(netbed.os, "makedirs", Mock())
    monkeypatch.setattr(netbed, "static_arp", arp)
    monkeypatch.setattr(netbed, "verify_link", verify)
    result = netbed.setup()
    commands = [call.args[0] for call in runner.call_args_list]
    assert commands[0] == "mount -t tmpfs none /run"
    assert "ip link set v1 netns peer" in commands
    assert "ip link set v0 mtu 1500" in commands
    assert "ip netns exec peer ip link set v1 mtu 1500" in commands
    arp.assert_called_once_with()
    verify.assert_called_once_with(1500)
    assert result["cpu_affinity"] == [1, 3, 5, 7]


def test_static_arp_is_permanent_and_crosses_the_peer_macs(monkeypatch):
    monkeypatch.setattr(netbed, "_mac", Mock(side_effect=["02:00:00:00:00:01", "02:00:00:00:00:02"]))
    runner = Mock()
    monkeypatch.setattr(netbed, "run", runner)
    netbed.static_arp()
    assert [call.args[0] for call in runner.call_args_list] == [
        "ip neigh replace 10.9.0.2 lladdr 02:00:00:00:00:02 dev v0 nud permanent",
        "ip netns exec peer ip neigh replace 10.9.0.1 lladdr 02:00:00:00:00:01 dev v1 nud permanent",
    ]


def test_static_arp_failure_prevents_successful_setup(monkeypatch):
    monkeypatch.setattr(netbed, "require_root", lambda: None)
    monkeypatch.setattr(netbed, "pin_cpus", lambda: [0])
    monkeypatch.setattr(netbed, "run", Mock())
    monkeypatch.setattr(netbed.os, "makedirs", Mock())
    monkeypatch.setattr(netbed, "static_arp", Mock(side_effect=RuntimeError("ARP failed")))
    verify = Mock()
    monkeypatch.setattr(netbed, "verify_link", verify)
    with pytest.raises(RuntimeError, match="ARP failed"):
        netbed.setup()
    verify.assert_not_called()


@pytest.mark.parametrize("local,peer,all_links", [
    ("2: v0: mtu 15000", "3: v1: mtu 1500", "2: v0: mtu 1500"),
    ("2: v0: mtu 1500", "3: v1: mtu 1280", "2: v0: mtu 1500"),
    ("2: v0: mtu 1500", "3: v1: mtu 1500", "2: v0: mtu 1500\n3: v1@v0: mtu 1500"),
])
def test_verify_link_rejects_wrong_mtu_or_unmoved_peer(monkeypatch, local, peer, all_links):
    monkeypatch.setattr(netbed, "run", Mock(side_effect=[
        SimpleNamespace(stdout=value) for value in (local, peer, all_links)]))
    with pytest.raises(RuntimeError):
        netbed.verify_link(1500)


def test_verify_link_allows_peer_name_only_in_veth_reference(monkeypatch):
    local = "2: v0@v1: mtu 1500\n"
    peer = "3: v1@v0: mtu 1500\n"
    monkeypatch.setattr(netbed, "run", Mock(side_effect=[
        SimpleNamespace(stdout=value) for value in (local, peer, local)]))
    assert netbed.verify_link(1500) == {"local": local, "peer": peer}


@pytest.fixture
def tc_runner(monkeypatch):
    monkeypatch.setattr(netbed, "require_root", lambda: None)
    calls = []
    outputs = {
        "tc qdisc show dev v0": "qdisc netem 10: root refcnt 2 limit 1000 delay 25ms loss 2% rate 2Mbit\n",
        "ip netns exec peer tc qdisc show dev v1": "qdisc netem 20: root refcnt 2 limit 1000 delay 25ms loss 7% rate 5Mbit\n",
    }

    def run(command, check=True):
        calls.append((command, check))
        return SimpleNamespace(stdout=outputs.get(command, ""), stderr="", returncode=0)

    monkeypatch.setattr(netbed, "run", run)
    return calls, outputs


def test_netem_keeps_directional_loss_rate_and_records_actual_output(tc_runner):
    calls, outputs = tc_runner
    records = []
    result = netbed.set_netem(25, loss_c2s=2, loss_s2c=7, rate_up_mbit=2,
                              rate_down_mbit=5, journal=records.append)
    assert ("tc qdisc add dev v0 root netem delay 25.000ms rate 2mbit loss 2.0000%", True) in calls
    assert ("ip netns exec peer tc qdisc add dev v1 root netem delay 25.000ms rate 5mbit loss 7.0000%", True) in calls
    assert records == [result]
    assert result["qdisc"]["c2s"]["stdout"] == outputs["tc qdisc show dev v0"]
    assert result["qdisc"]["s2c"]["stdout"] == outputs["ip netns exec peer tc qdisc show dev v1"]
    assert result["qdisc"]["c2s"]["stdout"] != result["qdisc"]["s2c"]["stdout"]


def test_netem_propagates_journal_write_failure(tc_runner):
    journal = Mock(side_effect=OSError("disk full"))
    with pytest.raises(OSError, match="disk full"):
        netbed.set_netem(25, journal=journal)
    journal.assert_called_once()


def test_missing_netem_output_is_not_journaled_as_success(tc_runner):
    _, outputs = tc_runner
    outputs["ip netns exec peer tc qdisc show dev v1"] = "qdisc noqueue 0: root refcnt 2\n"
    journal = Mock()
    with pytest.raises(RuntimeError):
        netbed.set_netem(25, journal=journal)
    journal.assert_not_called()


@pytest.mark.parametrize("kwargs", [
    {"loss_c2s": -1}, {"loss_s2c": 101}, {"rate_down_mbit": -1},
    {"burst_len": 0}, {"loss_c2s": 75, "burst_len": 2}, {"rate_up_mbit": float("nan")},
])
def test_invalid_netem_values_fail_before_tc(tc_runner, kwargs):
    calls, _ = tc_runner
    with pytest.raises(ValueError):
        netbed.set_netem(25, journal=lambda event: None, **kwargs)
    assert not calls


def test_missing_journal_fails_before_tc(tc_runner):
    calls, _ = tc_runner
    with pytest.raises(TypeError):
        netbed.set_netem(25, journal=None)
    assert not calls


def test_cpu_affinity_uses_first_four_allowed_cpus_and_reads_back(monkeypatch):
    monkeypatch.setattr(netbed, "require_root", lambda: None)
    getter = Mock(side_effect=[{9, 3, 1, 7, 5}, {1, 3, 5, 7}])
    setter = Mock()
    monkeypatch.setattr(netbed.os, "sched_getaffinity", getter, raising=False)
    monkeypatch.setattr(netbed.os, "sched_setaffinity", setter, raising=False)
    assert netbed.pin_cpus() == [1, 3, 5, 7]
    setter.assert_called_once_with(0, {1, 3, 5, 7})
    assert getter.call_count == 2


def test_cpu_affinity_mismatch_is_an_error(monkeypatch):
    monkeypatch.setattr(netbed, "require_root", lambda: None)
    monkeypatch.setattr(netbed.os, "sched_getaffinity", Mock(side_effect=[{1, 3}, {1}]), raising=False)
    monkeypatch.setattr(netbed.os, "sched_setaffinity", Mock(), raising=False)
    with pytest.raises(RuntimeError, match="CPU affinity"):
        netbed.pin_cpus()


@pytest.mark.parametrize("condition", ["valid", "missing_binary", "missing_sha", "bad_sha", "missing_srcsha", "bad_srcsha", "not_executable"])
def test_binary_identity_checks_use_current_gen33_fingerprint(monkeypatch, condition):
    digest, source = "a" * 64, "b" * 64
    monkeypatch.setattr(netbed.gate_v3_parity.os.path, "isfile", lambda path: condition != "missing_binary")
    monkeypatch.setattr(netbed.gate_v3_parity, "sha256_file", lambda path: digest)
    fingerprint = Mock(return_value=source)
    monkeypatch.setattr(netbed.gate_v3_parity, "quicbed_fingerprint", fingerprint)

    def read(path):
        if path.endswith(".sha256"):
            return None if condition == "missing_sha" else (("c" * 64 if condition == "bad_sha" else digest) + "  qamp")
        if path.endswith(".srcsha"):
            return None if condition == "missing_srcsha" else ("c" * 64 if condition == "bad_srcsha" else source)
        raise AssertionError(path)

    monkeypatch.setattr(netbed.gate_v3_parity, "read_text", read)
    monkeypatch.setattr(netbed.os, "access", lambda path, mode: condition != "not_executable")
    if condition == "valid":
        report = netbed.require_bin("test-qamp")
        assert report["sha256"] == digest
        assert report["srcsha"] == report["source_fingerprint_now"] == source
    else:
        with pytest.raises(RuntimeError):
            netbed.require_bin("test-qamp")
    if condition != "missing_binary":
        fingerprint.assert_called_once_with()


def test_run_raises_on_failure_unless_check_is_false(monkeypatch):
    monkeypatch.setattr(netbed, "require_root", lambda: None)
    failure = SimpleNamespace(returncode=3, stdout="output", stderr="error")
    monkeypatch.setattr(netbed.subprocess, "run", Mock(return_value=failure))
    with pytest.raises(RuntimeError, match="FAILED"):
        netbed.run("tc qdisc show dev v0")
    assert netbed.run("tc qdisc del dev v0 root", check=False) is failure
