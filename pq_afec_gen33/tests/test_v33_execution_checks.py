import json
from pathlib import Path

import numpy as np
import pytest
from scipy import stats as scipy_stats

from experiments.v33.lib import arms, report_checks
from test_v33_devreport_checks import smoke_payload, tc_output


ROOT = Path(__file__).resolve().parents[1]
PLAN = json.loads((ROOT / "g3/v33/plans/final_bundle_v1.json").read_text(encoding="utf-8"))


def build(task, keep=lambda unit: True):
    units = [unit for unit in arms.iter_units(PLAN, [task]) if keep(unit)]
    payloads, events = zip(*(smoke_payload(PLAN, unit) for unit in units))
    return PLAN, units, list(payloads), list(events)


def set_tc(unit, payload, direction, attempts, dropped):
    payload["tc_after"][direction] = tc_output(unit, direction, attempts - dropped, dropped)


def run(fixture, task):
    plan, units, payloads, events = fixture
    return report_checks.summarize_checks(plan, task, units, payloads, [], events, extended=True)


def exact_interval(attempts, percent, confidence=0.999):
    support = np.arange(attempts + 1)
    pmf = scipy_stats.binom.pmf(support, attempts, percent / 100)
    cdf = np.cumsum(pmf)
    tail = (1 - confidence) / 2
    return int(np.searchsorted(cdf, tail)), int(np.searchsorted(cdf, 1 - tail))


def spread(fixture, select, direction, total_dropped, attempts_each=1000):
    plan, units, payloads, events = fixture
    chosen = [(unit, payload) for unit, payload in zip(units, payloads) if select(unit)]
    base, extra = divmod(total_dropped, len(chosen))
    for index, (unit, payload) in enumerate(chosen):
        set_tc(unit, payload, direction, attempts_each, base + (index < extra))
    return len(chosen) * attempts_each


@pytest.mark.parametrize("task", ["M1", "X1", "X9"])
def test_every_measurement_task_runs_execution_checks(task):
    fixture = build(task)
    for unit, payload in zip(fixture[1], fixture[2]):
        if unit["loss_s2c_pct"]:
            set_tc(unit, payload, "s2c", 1000, 10 * unit["loss_s2c_pct"])
    result = run(fixture, task)
    assert result["checks"]["netem_config"] == "pass"
    assert result["checks"]["success_rate"] == "pass"
    assert result["checks"]["realized_loss"] == "pass"


@pytest.mark.parametrize("task,keep", [
    ("M1", lambda unit: True),
    ("X1", lambda unit: True),
    ("X9", lambda unit: unit["cell"] == "c2s"),
    ("X6", lambda unit: unit["cell"] == "S_rtt200" and unit["arm"] == "v33none"),
])
def test_netem_drift_fails_outside_smoke(task, keep):
    fixture = build(task, keep)
    payload = fixture[2][0]
    output = payload["tc_after"]["c2s"]
    output["stdout"] = output["stdout"].replace("delay ", "delay 1", 1)
    result = run(fixture, task)
    assert result["checks"]["netem_config"] == "fail"


def test_missing_netem_event_is_missing_not_pass():
    fixture = build("X1")
    fixture[3].pop()
    assert run(fixture, "X1")["checks"]["netem_config"] == "missing"


def test_x6_realized_loss_is_stratified_by_direction_and_nominal_loss():
    fixture = build("X6", lambda unit: unit["cell"] == "S_bigcert" and unit["arm"] in ("v33none", "v33c1")
                    and (unit["phase"], unit["block"]) in ((0, 0), (1, 0), (2, 9)))
    assert len(fixture[1]) == 24
    details = run(fixture, "X6")["details"]["realized_loss"]
    found = {(item["direction"], item["loss_pct"]): (item["attempts"], item["dropped"], item["status"]) for item in details}
    assert found == {("c2s", 2): (16000, 320, "pass"), ("c2s", 15): (8000, 1200, "pass"), ("s2c", 0): (24000, 0, "pass")}


@pytest.mark.parametrize("offset,status", [(0, "pass"), (1, "fail")])
def test_x1_realized_loss_upper_boundary_matches_exact_binomial(offset, status):
    fixture = build("X1", lambda unit: unit["cell"] == "rtt200_l15")
    low, high = exact_interval(32000, 15)
    assert spread(fixture, lambda unit: True, "c2s", high + offset) == 32000
    value = next(item for item in run(fixture, "X1")["details"]["realized_loss"] if item["direction"] == "c2s")
    assert value["prediction_interval"] == [low, high]
    assert value["status"] == status


@pytest.mark.parametrize("offset,status", [(0, "pass"), (-1, "fail")])
def test_x1_realized_loss_lower_boundary_matches_exact_binomial(offset, status):
    fixture = build("X1", lambda unit: unit["cell"] == "rtt200_l15")
    low, high = exact_interval(32000, 15)
    spread(fixture, lambda unit: True, "c2s", low + offset)
    value = next(item for item in run(fixture, "X1")["details"]["realized_loss"] if item["direction"] == "c2s")
    assert value["status"] == status


def test_x9_both_checks_server_to_client_loss_separately():
    fixture = build("X9", lambda unit: unit["cell"] == "both")
    attempts = spread(fixture, lambda unit: True, "s2c", 0)
    assert attempts == 122000
    details = run(fixture, "X9")["details"]["realized_loss"]
    by_direction = {item["direction"]: item for item in details}
    assert by_direction["s2c"]["status"] == "fail"
    assert by_direction["s2c"]["loss_pct"] == 5
    spread(fixture, lambda unit: True, "s2c", 6100)
    details = run(fixture, "X9")["details"]["realized_loss"]
    assert {item["direction"]: item["status"] for item in details} == {"c2s": "pass", "s2c": "pass"}


def test_x9_c2s_cell_rejects_any_server_to_client_drop():
    fixture = build("X9", lambda unit: unit["cell"] == "c2s")
    set_tc(fixture[1][0], fixture[2][0], "s2c", 1000, 1)
    details = run(fixture, "X9")["details"]["realized_loss"]
    value = next(item for item in details if item["direction"] == "s2c")
    assert value["prediction_interval"] == [0, 0]
    assert value["status"] == "fail"


@pytest.mark.parametrize("failures,status", [(16, "pass"), (17, "fail")])
def test_x1_success_rate_is_per_cell_arm_at_plan_threshold(failures, status):
    fixture = build("X1", lambda unit: unit["cell"] == "rtt200_l15")
    rows = [row for unit, payload in zip(fixture[1], fixture[2]) if unit["arm"] == "m4L2" for row in payload["rows"]]
    assert len(rows) == 320
    for row in rows[:failures]:
        row["ok"] = False
    details = run(fixture, "X1")["details"]["success_rate"]
    assert {item["arm"]: item["status"] for item in details} == {"m4L2": status, "pad4L2": "pass"}
    value = next(item for item in details if item["arm"] == "m4L2")
    assert value["n"] == 320
    assert value["rate"] == pytest.approx((320 - failures) / 320)


def test_success_rate_missing_ok_is_missing():
    fixture = build("X1", lambda unit: unit["cell"] == "rtt200_l15")
    del fixture[2][0]["rows"][0]["ok"]
    assert run(fixture, "X1")["checks"]["success_rate"] == "missing"


@pytest.mark.parametrize("cell,value,status", [("bigcert_l2", 2, "pass"), ("bigcert_l2", 2.0, "pass"),
                                               ("bigcert_l2", 10, "fail"), ("p11_l0", 0, "pass"), ("p11_l0", 2, "fail")])
def test_policy_uplink_row_must_match_plan_profile(smoke_fixture, cell, value, status):
    payload = next(payload for unit, payload in zip(smoke_fixture[1], smoke_fixture[2])
                   if unit["cell"] == cell and unit["arm"] == "v33none")
    payload["rows"][3]["policy_uplink_mbps"] = value
    assert run(smoke_fixture, "M0")["checks"]["policy_uplink"] == status


@pytest.mark.parametrize("mutate", [lambda row: row.pop("policy_uplink_mbps"),
                                    lambda row: row.update(policy_uplink_mbps=None),
                                    lambda row: row.update(policy_uplink_mbps="2")])
def test_policy_uplink_missing_or_malformed_is_missing(smoke_fixture, mutate):
    payload = next(payload for unit, payload in zip(smoke_fixture[1], smoke_fixture[2])
                   if unit["cell"] == "bigcert_l2" and unit["arm"] == "v33c1")
    mutate(payload["rows"][0])
    assert run(smoke_fixture, "M0")["checks"]["policy_uplink"] == "missing"


def test_policy_uplink_only_applies_to_gen33_auto3_arms(smoke_fixture):
    for unit, payload in zip(smoke_fixture[1], smoke_fixture[2]):
        if unit["arm"] not in ("v33none", "v33c1"):
            for row in payload["rows"]:
                row.pop("policy_uplink_mbps", None)
    result = run(smoke_fixture, "M0")
    assert result["checks"]["policy_uplink"] == "pass"
    assert {item["arm"] for item in result["details"]["policy_uplink"]} == {"v33none", "v33c1"}
    assert len(result["details"]["policy_uplink"]) == 8


def test_x6_idle_control_arm_is_also_checked():
    fixture = build("X6", lambda unit: unit["cell"] == "S_rtt200_idle_control"
                    and (unit["phase"], unit["block"]) == (0, 0))
    assert run(fixture, "X6")["checks"]["policy_uplink"] == "pass"
    fixture[2][0]["rows"][0]["policy_uplink_mbps"] = 10
    assert run(fixture, "X6")["checks"]["policy_uplink"] == "fail"


def test_measured_v1_plan_keeps_measurement_time_check_names():
    new = {"netem_config", "realized_loss", "success_rate", "policy_uplink"}
    plan, units, payloads, events = build("X1", lambda unit: unit["cell"] == "rtt200_l15")
    assert plan["plan_id"] in report_checks.MEASURED_PLAN_IDS
    assert not new & set(report_checks.summarize_checks(plan, "X1", units, payloads, [], events)["checks"])
    later = dict(plan, plan_id="final_bundle_v2")
    assert new - {"policy_uplink"} <= set(report_checks.summarize_checks(later, "X1", units, payloads, [], events)["checks"])
    plan, units, payloads, events = build("M0")
    checks = report_checks.summarize_checks(plan, "M0", units, payloads, [], events)["checks"]
    assert "policy_uplink" not in checks
    assert {"netem_config", "realized_loss", "success_rate"} <= set(checks)


@pytest.fixture
def smoke_fixture():
    return build("M0")
