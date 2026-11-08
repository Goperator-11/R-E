import copy
import itertools
import json
from collections import Counter
from pathlib import Path

import pytest

from experiments.v33.lib import arms


@pytest.fixture
def plan():
    return json.loads((Path(__file__).resolve().parents[1] / "g3/v33/plans/final_bundle_v1.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("n", range(1, 10))
def test_general_williams_pair_balance(n):
    rows = arms.williams(n)
    multiplier = 2 if n % 2 else 1
    assert len(rows) == multiplier * n
    assert all(sorted(row) == list(range(n)) for row in rows)
    observed = Counter(pair for row in rows for pair in zip(row, row[1:]))
    assert observed == Counter({pair: multiplier for pair in itertools.permutations(range(n), 2)})
    for column in range(n):
        assert Counter(row[column] for row in rows) == Counter({value: multiplier for value in range(n)})


@pytest.mark.parametrize("value", [0, -1, True, 1.5, None])
def test_williams_rejects_invalid_size(value):
    with pytest.raises(ValueError):
        arms.williams(value)


def test_six_arm_sequence_matches_plan():
    names = list("abcdef")
    assert arms.order_for(names, 0) == list("abfced")
    assert arms.order_for(names, 6) == arms.order_for(names, 0)
    with pytest.raises(ValueError):
        arms.order_for(["a", "a"], 0)
    with pytest.raises(ValueError):
        arms.order_for(names, -1)


def test_required_schedule_totals_burnin_warmup_and_cache_scope(plan):
    units = arms.iter_units(plan)
    assert sum(unit["connections"] for unit in units) == 78080
    assert sum(unit["connections"] for unit in units if not unit["additional"]) == 77180
    assert sum(unit["connections"] for unit in units if unit["additional"]) == 900
    assert len({unit["key"] for unit in units}) == len(units)
    assert all(unit["rows_expected"] == unit["connections"] for unit in units)
    for task in ("M0", "M1", "X1"):
        assert all(unit["burnin_connections"] == unit["warmup_connections"] == 0 for unit in units if unit["task"] == task)
    x9 = [unit for unit in units if unit["task"] == "X9"]
    assert all(unit["warmup_connections"] == 5 and unit["measured_connections"] == 100 for unit in x9)
    assert sum(unit["measured_connections"] for unit in x9) == 24400
    x6 = [unit for unit in units if unit["task"] == "X6"]
    caches = {unit["cache_key"] for unit in x6}
    assert None not in caches
    assert len(caches) == 49
    for cache_key in caches:
        trajectory = [unit for unit in x6 if unit["cache_key"] == cache_key]
        assert sum(unit["burnin_connections"] for unit in trajectory) == 300
        assert trajectory[0]["connection_offset"] == 0
        assert all(left["connection_offset"] + left["connections"] == right["connection_offset"] for left, right in zip(trajectory, trajectory[1:]))
    assert all(unit["cache_key"] is None for unit in units if unit["task"] in ("M1", "X1", "X9"))


def test_schedule_rotation_continues_across_phase_and_trajectory(plan):
    units = arms.iter_units(plan, ["X6"])
    for trajectory in range(4):
        for block in (0, 9, 10, 29):
            selected = [unit for unit in units if unit["cell"] == "S_bigcert" and unit["trajectory"] == trajectory and unit["block_across_phases"] == block]
            assert [unit["arm"] for unit in selected] == arms.order_for(["v33none", "v33c1", "v31auto", "g2auto"], block + trajectory)


def test_task_subset_stays_in_plan_order_and_additional_is_explicit(plan):
    assert arms.selected_tasks(plan, ["X6", "M0"]) == ["M0", "X6"]
    assert sum(unit["connections"] for unit in arms.iter_units(plan, "X6", include_additional=False)) == 35200
    assert sum(unit["connections"] for unit in arms.iter_units(plan, "M0")) == 480


@pytest.mark.parametrize("task", ["X2", "X3", "X4", "global_fixed_0_3_1", "X10", "missing"])
def test_optional_and_unknown_tasks_are_not_silently_scheduled(plan, task):
    with pytest.raises(ValueError):
        arms.iter_units(plan, task)


@pytest.mark.parametrize("field,value", [("blocks", 0), ("blocks", True), ("connections_per_arm_block", 19), ("connections_per_arm", 21), ("loss_c2s_pct", float("nan")), ("loss_s2c_pct", 101)])
def test_bad_phase_or_count_fails_closed(plan, field, value):
    plan["tasks"]["M0"]["cells"][0]["phases"][0][field] = value
    with pytest.raises(ValueError):
        arms.iter_units(plan, "M0")


def test_total_and_id_mismatch_fail_closed(plan):
    broken = copy.deepcopy(plan)
    broken["tasks"]["M0"]["connections_total"] -= 1
    with pytest.raises(ValueError):
        arms.iter_units(broken, "M0")
    plan["tasks"]["M0"]["cells"][0]["id"] = "../unsafe"
    with pytest.raises(ValueError):
        arms.iter_units(plan, "M0")


def test_commands_use_plan_flags_and_c1_gap_override(plan):
    units = arms.iter_units(plan, "M0")
    binaries = {key: f"/run/bin/{key}" for key in plan["binaries"]}
    for unit in units:
        command = arms.client_command(plan, unit, binary_paths=binaries, address="host:1234", cache="cache.json", stats="client.json")
        assert "-ips" not in command
        assert command[command.index("-expect-k") + 1] == str(unit["profile"]["expect_k"])
        assert "-uplink-mbps" in command
        server = arms.server_command(plan, unit, binary_paths=binaries, address="host:1234", cert_file="cert.pem", stats="server.json", conn_log="connections.jsonl")
        assert server[server.index("-profile") + 1] == "sealed31"
        if unit["arm"] == "v33c1":
            assert "-profile" not in command
            assert "-feedback" in command and "-feedback" in server
            assert command[command.index("-gap") + 1] == ("1ms" if unit["profile_id"] == "bigcert" else f"{unit['profile']['gap_ms']}ms")
        else:
            assert "-feedback" not in command and "-feedback" not in server


def test_cache_is_required_and_ips_only_comes_from_arm(plan):
    unit = arms.iter_units(plan, "M0")[0]
    binaries = {key: key for key in plan["binaries"]}
    with pytest.raises(ValueError):
        arms.client_command(plan, unit, binary_paths=binaries, address="host:1234")
    unit["arm"] = "initial1400"
    command = arms.client_command(plan, unit, binary_paths=binaries, address="host:1234")
    assert command[command.index("-ips") + 1] == "1400"
    plan["common"]["client_common_flags"] += ["-ips", "1280"]
    with pytest.raises(ValueError):
        arms.client_command(plan, unit, binary_paths=binaries, address="host:1234")


def test_m1_frozen_server_and_x9_basic_commands(plan):
    binaries = {key: key for key in plan["binaries"]}
    for unit in arms.iter_units(plan, "M1")[:6]:
        server = arms.server_command(plan, unit, binary_paths=binaries, address="host:1234", cert_file="cert.pem", stats="server.json", conn_log="connections.jsonl")
        if unit["arm"] in ("a", "e"):
            assert "-conn-log" not in server and "-cert-file" not in server and "-profile" not in server
        else:
            assert "-conn-log" in server and "-cert-file" in server
    for unit in arms.iter_units(plan, "X9")[:2]:
        server = arms.server_command(plan, unit, binary_paths=binaries, address="host:1234", cert_file="cert.pem", stats="server.json", conn_log="connections.jsonl")
        assert server[server.index("-profile") + 1] == "sealed31"
        assert server[server.index("-udp-path") + 1] == "basic"
        client = arms.client_command(plan, unit, binary_paths=binaries, address="host:1234")
        assert "-client-tracer=true" in client


def test_pre_decision_bytes_parity_padding_and_legacy():
    row = {"first_flight_bytes": 2560, "first_flight_parity_bytes": 4000, "first_flight_parity_dgrams": 4, "first_flight_lead_dgrams": 3, "m_used": 4}
    assert arms.pre_decision_bytes(row) == 5560
    del row["first_flight_lead_dgrams"]
    assert arms.pre_decision_bytes(row) == 3560
    row["m_used"] = 1
    assert arms.pre_decision_bytes(row) == 2560
    row["extra_sent"] = {"kind": "pad_junk", "first_sent": 4, "first_bytes": 4000, "first_lead": 3}
    assert arms.pre_decision_bytes(row) == 5560
    row["extra_sent"]["first_sent"] = 0
    assert arms.pre_decision_bytes(row) == 2560


def test_one_rtt_strict_boundary_and_settle():
    profile = {"rtt_ms": 50, "netem_uplink_mbps": 2}
    row = {"ok": True, "ms": 85.24, "first_flight_bytes": 2560}
    assert not arms.one_rtt(row, profile)
    row["ms"] = 85.239
    assert arms.one_rtt(row, profile)
    profile["netem_uplink_mbps"] = 0
    assert not arms.one_rtt(row, profile)
    row["ms"] = 74.999
    assert arms.one_rtt(row, profile)
    row["ok"] = False
    assert not arms.one_rtt(row, profile)
    assert arms.settle_s(profile) == 0.4


def test_one_rtt_uses_layout_cutoff(monkeypatch):
    profile = {"netem_uplink_mbps": 0, "rtt_ms": 100}
    row = {"ok": True, "ms": 155.0}
    assert arms.one_rtt(row, profile) is False
    monkeypatch.setattr(arms.layout, "ONE_RTT_CUTOFF_RTTS", 1.6)
    assert arms.one_rtt(row, profile) is True
