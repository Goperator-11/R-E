import numpy as np
import pytest
from scipy import stats as scipy_stats

from experiments.v33.lib import statistics
from test_v33_devreport_statistics import _arm, _inputs, _m1, plan


def _expected_interval(values):
    sample = np.asarray(values, dtype=float)
    mean = float(sample.mean())
    half = float(scipy_stats.t.ppf(0.975, sample.size - 1) * sample.std(ddof=1) / np.sqrt(sample.size))
    return mean, half


def _assert_interval(value, values):
    mean, half = _expected_interval(values)
    assert value["n"] == len(values)
    assert value["mean"] == pytest.approx(mean, abs=1e-9)
    assert value["halfwidth"] == pytest.approx(half, abs=1e-9)
    assert value["ci95"] == pytest.approx([mean - half, mean + half], abs=1e-9)


def _x6_layers():
    def change(unit, row):
        row["ms"] = 100
        if unit["cell"] == "S_bigcert" and unit["arm"] == "v33none":
            row["ms"] += {0: 60, 1: 20 + unit["trajectory"], 2: 4 + unit["trajectory"]}[unit["phase"]]
        elif unit["cell"] == "S_bigcert" and unit["arm"] == "g2auto" and unit["phase"] == 0:
            row["ms"] += 30
    return change


@pytest.fixture(scope="module")
def x6_result(plan):
    units, payloads = _inputs(plan, "X6", _x6_layers())
    return statistics.summarize(plan, "X6", units, payloads, _m1())


def _contrast(result, scope, contrast_id="v33none_minus_g2auto", cell="S_bigcert"):
    selected = next(item for item in result["cells"] if item["cell"] == cell)
    return next(item for item in selected["contrasts"] if item["id"] == contrast_id and item["scope"] == scope)


@pytest.mark.parametrize("scope,expected", [
    ("loss_2_0", [4, 5, 6, 7]),
    ("loss_15_0", [20, 21, 22, 23]),
    ("all_loss_2_0", [17, 17.5, 18, 18.5]),
    ("all_loss_15_0", [20, 21, 22, 23]),
    ("primary", [12, 13, 14, 15]),
    ("reweighted_1_1", [12, 13, 14, 15]),
])
def test_x6_contrast_scopes_follow_loss_and_burnin_by_hand(x6_result, scope, expected):
    value = _contrast(x6_result, scope)
    assert value["inference_unit"] == "trajectory"
    _assert_interval(value["hct"], expected)


def test_x6_burnin_scope_is_exactly_phase_zero(x6_result):
    value = _contrast(x6_result, "burnin")
    assert value["hct"]["mean"] == pytest.approx(30)
    assert value["hct"]["halfwidth"] == pytest.approx(0)


@pytest.mark.parametrize("loss,scope,rows,mean", [
    ((2, 0), "all", 2400, 132.75),
    ((2, 0), "primary", 1200, 105.5),
    ((15, 0), "all", 1200, 121.5),
    ((15, 0), "primary", 1200, 121.5),
])
def test_x6_arm_by_loss_rows_and_means_by_hand(x6_result, loss, scope, rows, mean):
    arm = _arm(x6_result, "S_bigcert", "v33none")
    layer = next(item for item in arm["by_loss"] if (item["loss_c2s_pct"], item["loss_s2c_pct"]) == loss)
    assert layer[scope]["n_rows"] == rows
    assert layer[scope]["hct"]["mean"] == pytest.approx(mean)
    assert layer[scope]["hct"]["df"] == 3


def test_x6_reweighted_contrast_averages_both_strata_for_every_metric(plan):
    def change(unit, row):
        row["ms"] = 500
        if unit["cell"] == "S_bigcert" and unit["arm"] == "v33none":
            row["ms"] = 50 if row["i"] < {0: 30, 1: 9, 2: 15}[unit["phase"]] else 500
        elif unit["cell"] == "S_bigcert" and unit["arm"] == "g2auto":
            row["ms"] = 50 if row["i"] < {0: 0, 1: 6, 2: 0}[unit["phase"]] else 500
    units, payloads = _inputs(plan, "X6", change)
    for unit, payload in zip(units, payloads):
        if unit["cell"] == "S_bigcert" and unit["arm"] == "v33none":
            payload["server_delta"]["bytes_in"] += 30 * {0: 0, 1: 10, 2: 2}[unit["phase"]]
    result = statistics.summarize(plan, "X6", units, payloads, _m1())
    value = _contrast(result, "reweighted_1_1")
    assert value["one_rtt_difference"]["mean"] == pytest.approx((15 / 30 + (9 - 6) / 30) / 2)
    assert value["server_bytes_in_per_conn_difference"]["mean"] == pytest.approx((2 + 10) / 2)
    assert value["n_pairs"] == 4
    assert value["weights"] == [0.5, 0.5]


def test_paired_one_rtt_difference_uses_every_selected_row_as_denominator(plan):
    def change(unit, row):
        row["ms"] = 500
        if unit["cell"] == "bigcert_l15":
            limit = {"pad4L3": 30, "m4L3": 10}.get(unit["arm"], 0)
            row["ms"] = 50 if row["i"] < limit else 500
    units, payloads = _inputs(plan, "X1", change)
    result = statistics.summarize(plan, "X1", units, payloads, _m1())
    contrast = next(item for item in result["cells"] if item["cell"] == "bigcert_l15")["contrasts"][0]
    assert contrast["one_rtt_difference"]["mean"] == pytest.approx(0.5, abs=1e-12)
    assert contrast["one_rtt_difference"]["halfwidth"] == pytest.approx(0, abs=1e-12)
    assert contrast["hct"]["mean"] == pytest.approx(162.5 - 387.5)
    assert _arm(result, "bigcert_l15", "pad4L3")["primary"]["one_rtt_rate"] == pytest.approx(0.75)


@pytest.mark.parametrize("cell,x_arm,blocks", [("bigcert_l15", "pad4L3", 28), ("rtt200_l15", "pad4L2", 16)])
def test_interval_containing_zero_alone_blocks_observed_difference(plan, cell, x_arm, blocks):
    def change(unit, row):
        row["ms"] = 90
        if unit["cell"] == cell and unit["arm"] == x_arm:
            row["ms"] += 5.5 if unit["block"] % 2 else -4.5
    units, payloads = _inputs(plan, "X1", change)
    result = statistics.summarize(plan, "X1", units, payloads, _m1())
    contrast = next(item for item in result["cells"] if item["cell"] == cell)["contrasts"][0]
    sample = [5.5 if block % 2 else -4.5 for block in range(blocks)]
    mean, half = _expected_interval(sample)
    assert mean - half < 0 < mean + half
    _assert_interval(contrast["hct"], sample)
    assert contrast["aa"]["applies"] is False
    assert contrast["ci95_contains_zero"] is True
    assert contrast["inference_reasons"] == ["95% 구간이 0을 포함"]
    assert contrast["inference_status"] == "판정불능"


def test_interval_excluding_zero_is_observed_without_reason(plan):
    def change(unit, row):
        row["ms"] = 90
        if unit["cell"] == "bigcert_l15" and unit["arm"] == "pad4L3":
            row["ms"] += 7 + (1 if unit["block"] % 2 else -1)
    units, payloads = _inputs(plan, "X1", change)
    result = statistics.summarize(plan, "X1", units, payloads, _m1())
    contrast = next(item for item in result["cells"] if item["cell"] == "bigcert_l15")["contrasts"][0]
    assert contrast["ci95_contains_zero"] is False
    assert contrast["inference_reasons"] == []
    assert contrast["inference_status"] == "차이 관측"


@pytest.mark.parametrize("ci,contains", [([0.0, 2.0], True), ([-2.0, 0.0], True), ([-1.0, 3.0], True),
                                         ([1e-9, 2.0], False), ([-2.0, -1e-9], False)])
def test_zero_rule_includes_interval_endpoints(plan, ci, contains):
    mean = (ci[0] + ci[1]) / 2
    value = {"hct": {"mean": mean, "ci95": ci, "halfwidth": (ci[1] - ci[0]) / 2}}
    judged = statistics._judgment(value, plan, "X1", "bigcert", 15, None)
    assert judged["ci95_contains_zero"] is contains
    assert ("95% 구간이 0을 포함" in judged["inference_reasons"]) is contains
    assert judged["inference_status"] == ("판정불능" if contains else "차이 관측")


def test_pto_auxiliary_needs_more_than_one_retransmitted_initial(plan):
    def change(unit, row):
        if unit["cell"] == "c2s" and unit["arm"] == "mlkem_off":
            row["initial_datagrams"] = {10: 3, 11: 4, 12: 2}.get(row["i"], row["initial_datagrams"])
    units, payloads = _inputs(plan, "X9", change)
    result = statistics.summarize(plan, "X9", units, payloads, _m1())
    pto = _arm(result, "c2s", "mlkem_off")["primary"]["pto"]
    assert pto["auxiliary"]["events"] == 61
    assert pto["auxiliary"]["rate"] == pytest.approx(61 / 6100)
    assert pto["definition_mismatch"] == 61
    assert pto["definition_comparable"] == 6100
    contrast = result["cells"][0]["pto_contrast"]["auxiliary"]
    assert contrast["mean"] == pytest.approx(0.01)
    assert contrast["n_blocks"] == 61


@pytest.mark.parametrize("initial,first,event", [(2, 2, False), (3, 2, False), (4, 2, True),
                                                 (5, 4, False), (6, 4, True), (0, 0, False)])
def test_pto_auxiliary_boundary_is_strict_first_plus_one(initial, first, event):
    row = {"row": {"initial_datagrams": initial, "first_flight_datagrams": first,
                   "observation": {"pto_count": 0, "tracer": "memory_qlog",
                                   "pto_count_scope": "qlog_loss_timer_expired_lower_bound"}}}
    assert statistics._pto([row])["auxiliary"]["events"] == int(event)


def test_m1_n_blocks_reports_smallest_contrast(plan, monkeypatch):
    units, payloads = _inputs(plan, "M1")
    original = statistics._paired
    calls = []

    def paired(left, right, selector, sample_unit):
        value = original(left, right, selector, sample_unit)
        calls.append(sample_unit)
        if len(calls) == 2:
            value["n_pairs"] = 29
        return value
    monkeypatch.setattr(statistics, "_paired", paired)
    result = statistics.summarize(plan, "M1", units, payloads)
    assert result["n_blocks"] == 29
    assert result["checks"]["n_blocks"] == "fail"
