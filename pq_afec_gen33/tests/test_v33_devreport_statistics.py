from copy import deepcopy
import json
import math
from pathlib import Path

import pytest

from experiments.v33.lib import arms, statistics


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def plan():
    return json.loads((ROOT / "g3/v33/plans/final_bundle_v1.json").read_text(encoding="utf-8"))


def _inputs(plan, task, row_change=None):
    units = arms.iter_units(plan, task)
    payloads = []
    for unit in units:
        rows = []
        for index in range(unit["rows_expected"]):
            row = {"i": index, "ok": True, "ms": 90 + unit["trajectory"],
                   "first_flight_bytes": 2560, "first_flight_parity_bytes": 5324,
                   "first_flight_parity_dgrams": 4, "first_flight_lead_dgrams": 3,
                   "initial_datagrams": 2, "first_flight_datagrams": 2,
                   "observation": {"pto_count": 0, "tracer": "memory_qlog",
                                   "pto_count_scope": "qlog_loss_timer_expired_lower_bound"},
                   "client_scid": str(index),
                   "bytes_parity": 20, "parity_sent": 1, "ips_used": 1280,
                   "action": [0, 3, 1], "p_mean": 0.02}
            if "-pad-junk" in plan["arms"][unit["arm"]]["client_flags"]:
                row["extra_sent"] = {"kind": "pad_junk", "first_bytes": 5310}
            if row_change:
                row_change(unit, row)
            rows.append(row)
        conns = [{"key": str(index), "rx_bytes": 3000 + index} for index in range(len(rows))]
        payloads.append({"rows": rows,
            "server_delta": {"bytes_in": sum(conn["rx_bytes"] for conn in conns),
                             "parities": 2, "recovered": 1, "credit_parities": 1},
            "collection": {"server": {"conns": conns,
                "conn_source": "conn_log", "fec_parse_fail": 0, "not_accepted": 1,
                "scid_matching": {"matches": [{"row_index": index, "conn_key": str(index)}
                                              for index in range(len(rows))]}}}})
    return units, payloads


def _m1():
    return {"contrasts": {"c_d": {"mean": 0, "ci95": [-1, 1]}},
            "a_vs_sealed": {"delta_ms": 0}}


def _arm(result, cell, arm):
    selected = next(item for item in result["cells"] if item["cell"] == cell)
    return next(item for item in selected["arms"] if item["arm"] == arm)


def test_interval_uses_student_t_four_independent_samples():
    value = statistics.interval([1, 2, 3, 4])
    halfwidth = 3.182446305284263 * math.sqrt(5 / 3) / 2
    assert value["n"] == 4
    assert value["df"] == 3
    assert value["mean"] == 2.5
    assert value["ci95"] == pytest.approx([2.5 - halfwidth, 2.5 + halfwidth])


@pytest.mark.parametrize("values", [[], [1]])
def test_interval_with_insufficient_samples_is_not_zero_width(values):
    value = statistics.interval(values)
    assert value["ci95"] is None
    assert value["status"] == "표본 부족"


@pytest.mark.parametrize("values", [[False], [float("nan")], [float("inf")]])
def test_interval_rejects_invalid_values(values):
    with pytest.raises(ValueError):
        statistics.interval(values)


def test_m1_pairs_blocks_and_imputes_returned_failures(plan):
    def change(unit, row):
        row["ms"] = 80 + unit["block"] * 100 + (2 if unit["arm"] == "a" else 0)
        if unit["arm"] == "a" and unit["block"] == 0 and row["i"] == 0:
            row.update(ok=False, ms=1)
    units, payloads = _inputs(plan, "M1", change)
    result = statistics.summarize(plan, "M1", units, payloads)
    delta = 2 + (10000 - 82) / 40 / 30
    assert result["contrasts"]["a_b"]["mean"] == pytest.approx(delta)
    assert result["contrasts"]["a_b"]["n_blocks"] == 30
    assert result["contrasts"]["a_b"]["df"] == 29
    arm = _arm(result, "bigcert_l2", "a")
    assert arm["primary"]["n_rows"] == 1200
    assert arm["primary"]["failed_rows"] == 1
    assert arm["primary"]["failure_rate"] == 1 / 1200
    assert arm["burnin"]["n_rows"] == 0
    assert result["a_vs_sealed"]["delta_ms"] == pytest.approx(arm["primary"]["hct"]["mean"] - 83.1)


def test_m1_broad_aa_is_inconclusive_without_execution_failure(plan):
    def change(unit, row):
        if unit["arm"] == "c":
            row["ms"] += 6
    units, payloads = _inputs(plan, "M1", change)
    result = statistics.summarize(plan, "M1", units, payloads)
    assert result["status"] == "판정불능"
    assert result["checks"] == {"n_blocks": "pass"}
    assert result["aa"]["ruler_ms"] == 6
    assert "c_g" not in result["contrasts"]


@pytest.mark.parametrize("env", [None, {"uname_r": "saved-measurement-kernel"}])
def test_m1_sealed_drift_keeps_saved_and_reference_kernels_separate(plan, env):
    units, payloads = _inputs(plan, "M1")
    result = statistics.summarize(plan, "M1", units, payloads, env=env)
    value = result["a_vs_sealed"]
    assert value["kernel"] == (env["uname_r"] if env else None)
    assert value["sealed_kernel"] == plan["statistics"]["sealed_drift"]["sealed_kernel"]
    assert value["source"] == plan["statistics"]["sealed_drift"]["source"]
    assert value["exploratory"] is True


def test_m1_tolerance_boundary_is_not_outside(plan):
    def change(unit, row):
        if unit["arm"] == "c":
            row["ms"] += 5
    units, payloads = _inputs(plan, "M1", change)
    result = statistics.summarize(plan, "M1", units, payloads)
    assert result["status"] == "판정 가능"


def test_cost_uses_all_returned_rows_and_not_client_parity_or_tls_accepts(plan):
    units, payloads = _inputs(plan, "M0")
    before = statistics.summarize(plan, "M0", units, payloads)
    for payload in payloads:
        for row in payload["rows"]:
            row["bytes_parity"] = 99999999
            row["parity_sent"] = 999999
        payload["collection"]["server"]["tls_accepted"] = 1
    after = statistics.summarize(plan, "M0", units, payloads)
    for old, new in zip(before["cells"], after["cells"]):
        for a, b in zip(old["arms"], new["arms"]):
            assert a["primary"]["server_cost"] == b["primary"]["server_cost"]
            assert b["primary"]["server_cost"]["bytes_per_conn"] == 3009.5
            assert a["primary"]["client_diagnostics"] != b["primary"]["client_diagnostics"]
    assert _arm(after, "bigcert_l2", "g2auto")["client_parity_count_unreliable"] is True


def test_missing_server_cost_is_unknown(plan):
    units, payloads = _inputs(plan, "M0")
    del payloads[0]["server_delta"]["bytes_in"]
    result = statistics.summarize(plan, "M0", units, payloads)
    cost = _arm(result, units[0]["cell"], units[0]["arm"])["primary"]["server_cost"]
    assert cost["bytes_per_conn"] is None
    assert cost["status"] == "미확인"
    assert cost["missing_units"] == [units[0]["key"]]


def test_x1_contrast_ids_keep_cells_and_plan_arm_names(plan):
    def change(unit, row):
        if unit["arm"].startswith("pad"):
            row["ms"] += {"bigcert_l2": 1, "bigcert_l15": 2, "rtt200_l15": 3}[unit["cell"]]
    units, payloads = _inputs(plan, "X1", change)
    result = statistics.summarize(plan, "X1", units, payloads, _m1())
    primary = [cell["contrasts"][0] for cell in result["cells"]]
    assert [value["hct"]["mean"] for value in primary] == [1, 2, 3]
    assert [value["n_pairs"] for value in primary] == [39, 28, 16]
    assert primary[2]["x"] == "pad4L2"
    assert primary[2]["y"] == "m4L2"
    assert [value["aa"]["applies"] for value in primary] == [True, False, False]
    assert primary[0]["inference_status"] == "차이 관측"
    assert primary[0]["first_flight_difference"]["original_bytes"] == 0
    assert primary[0]["first_flight_difference"]["extra_bytes"] == -14
    assert primary[0]["first_flight_difference"]["total_bytes"] == -14


def test_x1_aa_is_separate_from_ci_zero_check(plan):
    def change(unit, row):
        if unit["arm"].startswith("pad"):
            row["ms"] += 2
    units, payloads = _inputs(plan, "X1", change)
    m1 = {"contrasts": {"c_d": {"mean": 4, "ci95": [2, 6]}}}
    result = statistics.summarize(plan, "X1", units, payloads, m1)
    contrast = result["cells"][0]["contrasts"][0]
    assert contrast["ci95_contains_zero"] is False
    assert contrast["aa"]["note"] == "자 표류 큼"
    assert contrast["inference_status"] == "판정불능"


def test_x6_uses_four_trajectories_and_burnin_once(plan):
    def change(unit, row):
        row["ms"] = 50 if unit["loss_c2s_pct"] == 2 else 150
        if unit["arm"] == "v33none":
            row["ms"] += unit["trajectory"] + 1
    units, payloads = _inputs(plan, "X6", change)
    result = statistics.summarize(plan, "X6", units, payloads, _m1())
    value = _arm(result, "S_bigcert", "g2auto")
    assert value["all"]["n_rows"] == 3600
    assert value["burnin"]["n_rows"] == 1200
    assert value["primary"]["n_rows"] == 2400
    assert value["all"]["hct"]["mean"] == pytest.approx(250 / 3)
    assert value["primary"]["hct"]["mean"] == 100
    assert value["reweighted_1_1"]["hct"]["mean"] == 100
    assert value["primary"]["hct"]["df"] == 3
    primary = next(item for item in result["cells"][0]["contrasts"]
                   if item["id"] == "v33none_minus_g2auto" and item["scope"] == "primary")
    assert primary["hct"] == {**statistics.interval([1, 2, 3, 4]), "missing_pairs": 0}
    assert primary["aa"]["note"] == "A/A 없음"
    layers = [item for item in result["cells"][0]["contrasts"]
              if item["id"] == "v33none_minus_g2auto" and item["scope"].startswith("loss_")]
    assert [value["aa"]["applies"] for value in layers] == [True, False]
    p11 = _arm(result, "D_p11_2955_l0", "g2auto")
    assert p11["primary"]["n_rows"] == 400
    assert p11["reweighted_1_1"] is None
    assert result["idle_comparison"]["status"] == "미확인"
    control = result["cells"][-1]
    assert control["additional"] is True
    assert control["contrasts"][0]["n_pairs"] == 20
    assert control["contrasts"][0]["inference_unit"] == "block"
    assert control["contrasts"][0]["independent_trajectory_claim"] is False


def test_x6_actual_precision_rule_is_not_planned_halfwidth(plan):
    def change(unit, row):
        if unit["arm"] == "v33none":
            row["ms"] += [-8, -2, 4, 10][unit["trajectory"]]
    units, payloads = _inputs(plan, "X6", change)
    result = statistics.summarize(plan, "X6", units, payloads, _m1())
    contrast = result["cells"][0]["contrasts"][0]
    assert contrast["hct"]["mean"] == 1
    assert contrast["hct"]["halfwidth"] > 5
    assert "차이가 실제 구간 반폭보다 작음" in contrast["inference_reasons"]


def test_x9_direction_warmup_pto_definitions_and_server_subset(plan):
    def change(unit, row):
        if row["i"] < 5:
            row["ms"] = 9999
            row["observation"]["pto_count"] = 1
        elif unit["arm"] == "mlkem_off" and row["i"] < 15:
            row["observation"]["pto_count"] = 1
        if row["i"] == 10 and unit["arm"] == "mlkem_off":
            row["initial_datagrams"] = 4
    units, payloads = _inputs(plan, "X9", change)
    result = statistics.summarize(plan, "X9", units, payloads, _m1())
    assert len(result["cells"]) == 2
    for cell in result["cells"]:
        value = next(item for item in cell["arms"] if item["arm"] == "mlkem_off")
        assert value["primary"]["n_rows"] == 6100
        assert value["primary"]["hct"]["mean"] == 90
        assert value["warmup_excluded"] == 305
        assert value["primary"]["pto"]["primary"]["events"] == 610
        assert value["primary"]["pto"]["primary"]["rate"] == 0.1
        assert value["primary"]["pto"]["definition_mismatch"] == 549
        assert value["primary"]["server_cost"]["bytes_per_conn"] == 3054.5
        assert value["primary"]["server_cost"]["source"] == "conn_log.rx_bytes"
        assert cell["pto_contrast"]["primary"]["mean"] == 0.1
        assert cell["pto_contrast"]["primary"]["df"] == 60
    assert set(result["checks"].values()) == {"pass"}
    assert result["power"] == plan["tasks"]["X9"]["power"]


@pytest.mark.parametrize("missing,expected", [(5, "pass"), (6, "fail")])
def test_x9_missing_pto_is_counted_and_minimum_stays_6095(plan, missing, expected):
    def change(unit, row):
        if (unit["cell"] == "c2s" and unit["arm"] == "mlkem_off"
                and unit["block"] == 0 and 5 <= row["i"] < 5 + missing):
            del row["observation"]["pto_count"]
    units, payloads = _inputs(plan, "X9", change)
    result = statistics.summarize(plan, "X9", units, payloads, _m1())
    value = _arm(result, "c2s", "mlkem_off")["primary"]["pto"]["primary"]
    assert value["missing"] == missing
    assert value["n_total"] == 6100
    assert value["n_valid"] == 6100 - missing
    assert result["checks"]["c2s:mlkem_off:pto_denominator"] == expected
    assert result["checks"]["both:mlkem_off:pto_denominator"] == "pass"
    assert result["checks"]["c2s:mlkem_off:pto_primary_fields"] == "missing"
    assert result["cells"][0]["pto_contrast"]["primary"]["ci95"] is None
    assert result["cells"][0]["pto_contrast"]["primary"]["missing_blocks"] == 1


def test_partial_connection_cost_needs_scid_mapping(plan):
    units, payloads = _inputs(plan, "X9")
    payloads[0]["collection"]["server"]["scid_matching"]["matches"] = []
    result = statistics.summarize(plan, "X9", units, payloads, _m1())
    cost = _arm(result, units[0]["cell"], units[0]["arm"])["primary"]["server_cost"]
    assert cost["status"] == "미확인"
    assert cost["bytes_in"] is None


@pytest.mark.parametrize("tracer,scope", [("disabled", "tracer_disabled"),
                                         ("memory_qlog", "unknown"),
                                         (None, None)])
def test_x9_disabled_or_unknown_tracer_is_not_a_zero_pto_observation(plan, tracer, scope):
    def change(unit, row):
        if unit["cell"] == "c2s" and unit["arm"] == "mlkem_off" and unit["block"] == 0 and row["i"] == 5:
            row["observation"].update(tracer=tracer, pto_count_scope=scope)
    units, payloads = _inputs(plan, "X9", change)
    result = statistics.summarize(plan, "X9", units, payloads, _m1())
    pto = _arm(result, "c2s", "mlkem_off")["primary"]["pto"]["primary"]
    assert pto["missing"] == pto["scope_invalid"] == 1
    assert pto["n_valid"] == 6099
    assert result["cells"][0]["pto_contrast"]["primary"]["ci95"] is None
    assert result["checks"]["c2s:mlkem_off:pto_primary_fields"] == "missing"


def test_x1_missing_padding_count_does_not_substitute_zero_parity(plan):
    units, payloads = _inputs(plan, "X1")
    for unit, payload in zip(units, payloads):
        if unit["cell"] == "bigcert_l2" and unit["arm"] == "pad4L3" and unit["block"] == 0:
            payload["rows"][0].pop("extra_sent")
            payload["rows"][0]["first_flight_parity_bytes"] = 0
    result = statistics.summarize(plan, "X1", units, payloads, _m1())
    difference = result["cells"][0]["contrasts"][0]["first_flight_difference"]
    assert difference["original_bytes"] == 0
    assert difference["extra_bytes"] is None
    assert difference["total_bytes"] is None
    assert difference["missing_rows"]["x"] == {"extra": 1, "total": 1}


def test_sorting_rows_and_units_does_not_change_result(plan):
    units, payloads = _inputs(plan, "M0")
    original = statistics.summarize(plan, "M0", units, payloads)
    for payload in payloads:
        payload["rows"].reverse()
        for match in payload["collection"]["server"]["scid_matching"]["matches"]:
            match["row_index"] = len(payload["rows"]) - 1 - match["row_index"]
    assert statistics.summarize(plan, "M0", list(reversed(units)), list(reversed(payloads))) == original


@pytest.mark.parametrize("fault", ["missing_unit", "duplicate_unit", "missing_row", "duplicate_row", "wrong_unit"])
def test_incomplete_or_duplicate_data_is_not_imputed(plan, fault):
    units, payloads = _inputs(plan, "M0")
    if fault == "missing_unit":
        units.pop()
        payloads.pop()
    elif fault == "duplicate_unit":
        units[-1] = units[0]
    elif fault == "missing_row":
        payloads[0]["rows"].pop()
    elif fault == "duplicate_row":
        payloads[0]["rows"][-1]["i"] = 0
    else:
        units[0]["profile"]["rtt_ms"] += 1
    with pytest.raises(ValueError):
        statistics.summarize(plan, "M0", units, payloads)


def test_parse_fail_and_g2_ips_are_reported_without_frozen_imputation(plan):
    units, payloads = _inputs(plan, "M0")
    for unit, payload in zip(units, payloads):
        if unit["arm"] == "g2auto":
            payload["rows"][0]["ips_used"] = 1395
            payload["rows"][1]["ips_used"] = 1394
        if unit["arm"] == "v33none":
            payload["collection"]["server"]["fec_parse_fail"] = 2
    result = statistics.summarize(plan, "M0", units, payloads)
    assert _arm(result, "bigcert_l2", "g2auto")["g2auto_ips_used_ge_1395"] == 1
    assert _arm(result, "bigcert_l2", "v33none")["fec_parse_fail"] == 2
    units, payloads = _inputs(plan, "M1")
    for unit, payload in zip(units, payloads):
        if unit["arm"] == "a":
            payload["collection"]["server"]["fec_parse_fail"] = None
    result = statistics.summarize(plan, "M1", units, payloads)
    assert _arm(result, "bigcert_l2", "a")["fec_parse_fail"] is None
    assert _arm(result, "bigcert_l2", "a")["fec_parse_fail_status"] == "미확인"
