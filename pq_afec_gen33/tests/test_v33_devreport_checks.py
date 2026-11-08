from copy import deepcopy
import base64
import hashlib
import json
from pathlib import Path

import pytest

from experiments.v33.lib import arms, observations, report_checks
from padfec3 import learn3


ROOT = Path(__file__).resolve().parents[1]


def tc_output(unit, direction, sent=0, dropped=0):
    rate = unit["profile"]["netem_uplink_mbps"] if direction == "c2s" else 0
    loss = unit["loss_c2s_pct"] if direction == "c2s" else unit["loss_s2c_pct"]
    line = f"qdisc netem 8001: root refcnt 2 limit 1000 delay {unit['profile']['rtt_ms'] / 2}ms"
    if rate:
        line += f" rate {rate}Mbit"
    if loss:
        line += f" loss {loss}%"
    return {"returncode": 0, "stdout": line + f"\n Sent 0 bytes {sent} pkt (dropped {dropped}, overlimits 0 requeues 0)\n"}


def smoke_payload(plan, unit):
    arm = plan["arms"][unit["arm"]]
    is_pad = "-pad-junk" in arm["client_flags"]
    parity = 0 if is_pad else 4
    payload = {"attempt": 0, "client_rc": 0, "checks": {"explicit_flight": "pass"}, "rows": [],
               "started_at": "2026-11-06T12:00:00+00:00", "ended_at": "2026-11-06T12:00:01+00:00",
               "server": {"returncode": 0, "stats": {"recover_crc_fail": 0, "parities": 4,
                          "recovered": int(not is_pad and unit["loss_c2s_pct"] == 15)},
                          "certificate": {"der_sha256": "a" * 64, "der_bytes": unit["profile"]["certsize"]}}}
    for index in range(unit["rows_expected"]):
        payload["rows"].append({"i": index, "ok": True,
            "ms": {"bigcert": 80, "rtt200": 250, "p11": 50}.get(unit["profile_id"], 80),
            "ips_eff": 1280, "m_used": 4, "parity_sent": parity, "bytes_parity": 1335 * parity,
            "policy_uplink_mbps": unit["profile"]["policy_uplink_mbps"],
            "flight_trace": {"omitted": 0, "records": [{"parity_sent": parity, "parity_bytes": 1335 * parity}]},
            "first_flight_bytes": 2560, "first_flight_parity_bytes": 1335 * parity,
            "first_flight_parity_dgrams": parity, "first_flight_lead_dgrams": 3,
            "extra_sent": {"kind": "pad_junk" if is_pad else "parity", "first_bytes": 5340, "first_sent": 4, "first_lead": 3},
            "server_binary_sha256": plan["binaries"]["gen33"]["sha256"],
            "flight_expectation": {"source": "explicit", "k": unit["profile"]["expect_k"]},
            "feedback_wait_received": unit["arm"] == "v33c1",
            "feedback_wait_ns": 0, "feedback_wait_limit_ms": unit["profile"]["feedback_wait_ms"],
            "path_rtt_valid": False, "arrivals": {"src": "c1" if unit["arm"] == "v33c1" else "none"},
            "policy_path": "c1" if unit["arm"] == "v33c1" and index > 0 else "none"})
    payload["tc_before"] = {direction: tc_output(unit, direction) for direction in ("c2s", "s2c")}
    drops = int(unit["loss_c2s_pct"] * 10)
    payload["tc_after"] = {"c2s": tc_output(unit, "c2s", 1000 - drops, drops), "s2c": tc_output(unit, "s2c", 1000, 0)}
    event = {"key": unit["key"], "event": "netem", "data": {
        "attempt": 0,
        "requested": {"one_way_ms": unit["profile"]["rtt_ms"] / 2,
                      "loss_c2s": unit["loss_c2s_pct"], "loss_s2c": unit["loss_s2c_pct"],
                      "burst_len": 1, "rate_up_mbit": unit["profile"]["netem_uplink_mbps"], "rate_down_mbit": 0},
        "qdisc": {direction: tc_output(unit, direction) for direction in ("c2s", "s2c")}}}
    return payload, event


@pytest.fixture
def smoke():
    plan = json.loads((ROOT / "g3/v33/plans/final_bundle_v1.json").read_text(encoding="utf-8"))
    units = arms.iter_units(plan, ["M0"])
    payloads, events = zip(*(smoke_payload(plan, unit) for unit in units))
    return plan, units, list(payloads), list(events)


def summarize(fixture, task="M0"):
    plan, units, payloads, events = fixture
    observed = observations.summarize_observations(plan, [
        observations.unit_observations(plan, unit, payload) for unit, payload in zip(units, payloads)])
    return report_checks.summarize_checks(plan, task, units, payloads, observed, events)


def target(smoke, arm="m4L3", cell="bigcert_l2"):
    return next(payload for unit, payload in zip(smoke[1], smoke[2]) if unit["cell"] == cell and unit["arm"] == arm)


def test_smoke_checks_follow_complete_plan_without_idle_or_rtt_failure(smoke):
    result = summarize(smoke)
    assert set(result["checks"].values()) == {"pass"}
    assert not any("idle" in name or "rtt" in name for name in result["checks"])
    assert len(result["details"]["realized_loss"]) == 4
    assert len(result["details"]["success_rate"]) == 24


@pytest.mark.parametrize("ips,count,status", [(1279, 0, "fail"), (1280, 4, "pass"),
    (1401, 4, "pass"), (1402, 4, "fail"), (1452, 0, "pass")])
def test_w_bound_uses_effective_ips_and_positive_m(smoke, ips, count, status):
    row = target(smoke)["rows"][0]
    row.update(ips_eff=ips, m_used=count)
    assert summarize(smoke)["checks"]["w_bound"] == status


@pytest.mark.parametrize("size,status", [(1452, "pass"), (1453, "fail")])
def test_parity_cap_uses_each_flight_size(smoke, size, status):
    row = target(smoke)["rows"][0]
    row.update(bytes_parity=4 * size, flight_trace={"omitted": 0, "records": [{"parity_sent": 4, "parity_bytes": 4 * size}]})
    assert summarize(smoke)["checks"]["w_bound"] == status


@pytest.mark.parametrize("mutation", [
    lambda row: row.pop("bytes_parity"),
    lambda row: row["flight_trace"].update(omitted=1),
    lambda row: row["flight_trace"]["records"][0].update(parity_bytes=5339),
    lambda row: row["flight_trace"]["records"][0].update(parity_sent=3),
])
def test_missing_or_inconsistent_parity_evidence_is_unconfirmed(smoke, mutation):
    mutation(target(smoke)["rows"][0])
    assert summarize(smoke)["checks"]["w_bound"] == "missing"


def test_netem_actual_configuration_must_match_even_when_request_matches(smoke):
    smoke[3][0]["data"]["qdisc"]["c2s"]["stdout"] = smoke[3][0]["data"]["qdisc"]["c2s"]["stdout"].replace("rate 2Mbit", "rate 3Mbit")
    assert summarize(smoke)["checks"]["netem_config"] == "fail"


@pytest.mark.parametrize("field", ["tc_before", "tc_after"])
def test_netem_configuration_cannot_drift_after_setup_event(smoke, field):
    output = target(smoke)[field]["c2s"]
    output["stdout"] = output["stdout"].replace("loss 2%", "loss 3%")
    assert summarize(smoke)["checks"]["netem_config"] == "fail"


@pytest.mark.parametrize("mutation,status", [
    (lambda fixture: fixture[3].pop(), "missing"),
    (lambda fixture: fixture[3][0]["data"]["requested"].update(loss_c2s=3), "fail"),
    (lambda fixture: fixture[3][0]["data"]["qdisc"]["c2s"].update(stdout="qdisc pfifo_fast root"), "missing"),
])
def test_netem_missing_and_incorrect_records_do_not_pass(smoke, mutation, status):
    mutation(smoke)
    assert summarize(smoke)["checks"]["netem_config"] == status


def test_realized_loss_aggregates_cell_instead_of_testing_each_arm(smoke):
    candidates = [(unit, payload) for unit, payload in zip(smoke[1], smoke[2]) if unit["cell"] == "bigcert_l2"]
    for index, (unit, payload) in enumerate(candidates):
        dropped = 120 if index == 0 else 0
        payload["tc_after"]["c2s"] = tc_output(unit, "c2s", 1000 - dropped, dropped)
    result = summarize(smoke)
    assert result["checks"]["realized_loss"] == "pass"
    cell = next(item for item in result["details"]["realized_loss"] if item["cell"] == "bigcert_l2")
    assert cell["attempts"] == 6000 and cell["dropped"] == 120


def test_realized_loss_uses_sent_plus_dropped_and_rejects_outside_interval(smoke):
    unit, payload = next((unit, payload) for unit, payload in zip(smoke[1], smoke[2]) if unit["cell"] == "p11_l0")
    payload["tc_after"]["c2s"] = tc_output(unit, "c2s", 999, 1)
    result = summarize(smoke)
    assert result["checks"]["realized_loss"] == "fail"
    cell = next(item for item in result["details"]["realized_loss"] if item["cell"] == "p11_l0")
    assert cell["attempts"] == 6000 and cell["prediction_interval"] == [0, 0]


@pytest.mark.parametrize("mutation", [
    lambda payload: payload["server"]["certificate"].update(der_sha256="b" * 64),
    lambda payload: payload["server"]["certificate"].update(der_bytes=16001),
    lambda payload: payload["rows"][0].update(server_binary_sha256="b" * 64),
])
def test_common_server_and_certificate_checks(smoke, mutation):
    mutation(target(smoke))
    assert summarize(smoke)["checks"]["server_uniform"] == "fail"


def test_m1_planned_server_exception_is_explicit(smoke):
    target(smoke)["server"]["certificate"] = None
    result = summarize(smoke, "M1")
    assert result["checks"]["server_uniform"] == "pass"
    assert all("exception" in item for item in result["details"]["server_uniform"])


@pytest.mark.parametrize("mutate,check", [
    (lambda fixture: target(fixture)["rows"][0].update(first_flight_bytes=2561), "fixed_first_flight_bytes"),
    (lambda fixture: target(fixture)["rows"][0].update(first_flight_parity_bytes=5389), "fixed_extra_byte_range"),
    (lambda fixture: target(fixture, "pad4L3")["rows"][0]["extra_sent"].update(first_bytes=5389), "fixed_extra_byte_range"),
    (lambda fixture: target(fixture, "pad4L3")["server"]["stats"].update(recovered=1), "pad_recovered"),
    (lambda fixture: target(fixture, "g2auto")["server"]["stats"].update(parities=0), "frozen_parities"),
    (lambda fixture: target(fixture)["server"]["stats"].update(recover_crc_fail=1), "recover_crc_fail"),
    (lambda fixture: target(fixture, "g2auto", "bigcert_l15")["server"]["stats"].update(recovered=0), "recovered_positive"),
    (lambda fixture: target(fixture, "v33none")["rows"][0].update(policy_path="c1"), "none_path"),
    (lambda fixture: target(fixture, "v33c1")["rows"][1].update(policy_path="none"), "c1_path"),
    (lambda fixture: target(fixture)["rows"][0].update(ms=2000), "hct_mean_range"),
    (lambda fixture: target(fixture).update(client_rc=2), "process_rc"),
])
def test_each_smoke_boundary_detects_its_violation(smoke, mutate, check):
    mutate(smoke)
    assert summarize(smoke)["checks"][check] == "fail"


@pytest.mark.parametrize("failed,status", [(1, "pass"), (2, "fail")])
def test_success_rate_includes_all_returned_rows(smoke, failed, status):
    for row in target(smoke)["rows"][:failed]:
        row["ok"] = False
    assert summarize(smoke)["checks"]["success_rate"] == status


@pytest.mark.parametrize("received,status", [(17, "pass"), (16, "fail")])
def test_smoke_receipt_threshold_is_cell_085_not_class_095(smoke, received, status):
    rows = target(smoke, "v33c1")["rows"]
    for index, row in enumerate(rows):
        row["feedback_wait_received"] = index < received
        row["arrivals"]["src"] = "c1" if index < received else "none"
    result = summarize(smoke)
    assert result["checks"]["c1_feedback_received"] == status
    assert result["checks"]["c1_arrivals"] == status


def test_fec_parse_failure_is_carried_to_checks(smoke):
    target(smoke, "v33none")["checks"]["fec_parse_fail"] = "fail"
    assert summarize(smoke)["checks"]["fec_parse_fail"] == "fail"


def test_old_attempt_netem_events_do_not_change_completed_attempt_check(smoke):
    old = deepcopy(smoke[3][0])
    old["data"]["attempt"] = -1
    old["data"]["requested"]["loss_c2s"] = 99
    smoke[3].append(old)
    assert summarize(smoke)["checks"]["netem_config"] == "pass"


def cache_snapshot(seen):
    state = learn3.new_state().to_json()
    state["c1_seen"] = seen
    value = {"schema": "padfec3.cache3/11", "dests": {"fixture-address": {
        "state": state, "min_rtt_ms": 50, "min_hct_ms": 50,
        "rtt_observations": 1, "conns": 1}}}
    raw = json.dumps(value).encode("utf-8")
    return {"encoding": "base64", "data": base64.b64encode(raw).decode("ascii"),
            "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


@pytest.fixture
def x6(smoke):
    plan = smoke[0]
    units = [unit for unit in arms.iter_units(plan, "X6")
             if unit["cell"] == "S_bigcert" and unit["arm"] in ("v33none", "v33c1")
             and (unit["phase"], unit["block"]) in ((0, 0), (2, 9))]
    payloads, events = zip(*(smoke_payload(plan, unit) for unit in units))
    for unit, payload in zip(units, payloads):
        seen = unit["arm"] == "v33c1"
        payload["cache_after"] = cache_snapshot(seen)
        payload["commands"] = {"client": ["qamp", "-addr", "fixture-address"]}
        if seen and unit["connection_offset"]:
            for row in payload["rows"]:
                row["policy_path"] = "c1"
    return plan, units, list(payloads), list(events)


def test_x6_none_and_c1_paths_and_last_cache_are_checked_per_trajectory(x6):
    result = summarize(x6, "X6")
    assert set(result["checks"].values()) == {"pass"}
    assert len(result["details"]["trajectory_end_c1_seen"]) == 8
    assert {item["trajectory"] for item in result["details"]["trajectory_end_c1_seen"]} == {0, 1, 2, 3}


@pytest.mark.parametrize("arm,seen", [("v33none", True), ("v33c1", False)])
def test_x6_last_cache_cannot_be_opposite_path(x6, arm, seen):
    payload = next(payload for unit, payload in zip(x6[1], x6[2])
                   if unit["arm"] == arm and unit["phase"] == 2 and unit["trajectory"] == 3)
    payload["cache_after"] = cache_snapshot(seen)
    assert summarize(x6, "X6")["checks"]["trajectory_end_c1_seen"] == "fail"


def test_x6_cache_check_reads_last_unit_not_first_receipt_state(x6):
    payload = next(payload for unit, payload in zip(x6[1], x6[2])
                   if unit["arm"] == "v33c1" and unit["phase"] == 0)
    payload["cache_after"] = cache_snapshot(False)
    assert summarize(x6, "X6")["checks"]["trajectory_end_c1_seen"] == "pass"


def test_x6_c1_path_cannot_reset_at_block_boundary(x6):
    payload = next(payload for unit, payload in zip(x6[1], x6[2])
                   if unit["arm"] == "v33c1" and unit["phase"] == 2)
    payload["rows"][0]["policy_path"] = "none"
    assert summarize(x6, "X6")["checks"]["c1_path"] == "fail"


def test_x6_none_path_checks_burnin_rows_too(x6):
    payload = next(payload for unit, payload in zip(x6[1], x6[2])
                   if unit["arm"] == "v33none" and unit["phase"] == 0)
    payload["rows"][0]["arrivals"]["src"] = "c1"
    assert summarize(x6, "X6")["checks"]["none_path"] == "fail"


@pytest.mark.parametrize("mutation", [
    lambda payload: payload.update(cache_after=None),
    lambda payload: payload["cache_after"].update(sha256="a" * 64),
    lambda payload: payload["commands"].update(client=["qamp", "-addr", "wrong-address"]),
])
def test_x6_missing_or_wrong_cache_is_unconfirmed(x6, mutation):
    payload = next(payload for unit, payload in zip(x6[1], x6[2]) if unit["phase"] == 2)
    mutation(payload)
    assert summarize(x6, "X6")["checks"]["trajectory_end_c1_seen"] == "missing"


@pytest.mark.parametrize("arm,recovered,status", [("pad4L3", 0, "pass"), ("pad4L3", 1, "fail"),
                                                   ("m4L3", 1, "pass"), ("m4L3", 0, "fail")])
def test_x1_recovery_checks_are_separate_from_smoke_loss_exception(smoke, arm, recovered, status):
    payload = target(smoke, arm)
    payload["server"]["stats"]["recovered"] = recovered
    for unit, item in zip(smoke[1], smoke[2]):
        if unit["arm"] == "m4L3" and item is not payload:
            item["server"]["stats"]["recovered"] = 1
    check = "pad_recovered" if arm.startswith("pad") else "m4L3_recovered"
    assert summarize(smoke, "X1")["checks"][check] == status
