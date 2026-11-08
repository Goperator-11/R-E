from copy import deepcopy
import json
from pathlib import Path

import pytest

from experiments.v33.lib import arms, observations


PLAN = json.loads((Path(__file__).resolve().parents[1]
                   / "g3/v33/plans/final_bundle_v1.json").read_text(encoding="utf-8"))


def unit_for(task="M0", arm="v33c1", cell="rtt200_l15", phase=0, block=0, trajectory=0):
    return next(unit for unit in arms.iter_units(PLAN, [task])
                if (unit["arm"], unit["cell"], unit["phase"], unit["block"], unit["trajectory"])
                == (arm, cell, phase, block, trajectory))


def payload_for(unit, **updates):
    rows = []
    for index in range(unit["rows_expected"]):
        rows.append({"i": index, "ok": True, "ms": 200,
                     "flight_expectation": {"source": "explicit", "k": unit["profile"]["expect_k"]},
                     "feedback_wait_limit_ms": unit["profile"]["feedback_wait_ms"],
                     "feedback_wait_received": True, "feedback_wait_ns": 100_000_000,
                     "path_rtt_valid": False, "first_flight_bytes": 2560,
                     "first_flight_parity_dgrams": 0, "first_flight_parity_bytes": 0,
                     **updates})
    return {"rows": rows, "started_at": "2026-11-06T00:00:00+00:00",
            "ended_at": "2026-11-06T00:00:10+00:00"}


def result_for(unit, **updates):
    return observations.unit_observations(PLAN, unit, payload_for(unit, **updates))


def test_rtt200_limits_and_actual_wait_are_distinct():
    result = result_for(unit_for())
    assert result["checks"] == {"explicit_flight": "pass", "feedback_wait_limit": "pass",
                                "feedback_received_field": "pass"}
    assert result["summary"]["mean_feedback_wait_ms"] == 100
    assert result["summary"]["feedback_wait_limit_ms"] == 500
    assert result["summary"]["mean_wait_plus_gap_ms"] == 150
    assert result["summary"]["wait_plus_gap_samples"] == 19
    assert result["summary"]["mean_idle_ms"] is None
    assert result["summary"]["idle_valid_samples"] == 0
    assert result["summary"]["idle_status"] == "미확인"
    assert all("idle" not in key and "rtt" not in key for key in result["checks"])


@pytest.mark.parametrize("expectation,expected", [
    ({"source": "cached_k", "k": 2}, "fail"),
    ({"source": "explicit", "k": 1}, "fail"),
    ({"source": "explicit", "k": True}, "fail"),
    (None, "missing"),
])
def test_gen33_explicit_expectation_is_checked(expectation, expected):
    result = result_for(unit_for(), flight_expectation=expectation)
    assert result["checks"]["explicit_flight"] == expected


def test_group_specific_k_is_used():
    unit = unit_for(task="X9", arm="x25519_off", cell="c2s")
    assert unit["profile"]["expect_k"] == 1
    assert result_for(unit)["checks"]["explicit_flight"] == "pass"
    assert result_for(unit, flight_expectation={"source": "explicit", "k": 2})["checks"]["explicit_flight"] == "fail"


@pytest.mark.parametrize("limit,expected", [(200, "fail"), (499.999, "fail"), (500, "pass"),
                                            (None, "missing"), (True, "missing"), (float("nan"), "missing")])
def test_c1_wait_limit_does_not_use_smoke_rate_to_pass(limit, expected):
    assert result_for(unit_for(), feedback_wait_limit_ms=limit)["checks"]["feedback_wait_limit"] == expected


@pytest.mark.parametrize("received,rate,excluded", [(19, 0.95, False), (18, 0.9, True)])
def test_class_threshold_includes_every_row(received, rate, excluded):
    unit = unit_for()
    payload = payload_for(unit)
    for row in payload["rows"][received:]:
        row["feedback_wait_received"] = False
    result = observations.unit_observations(PLAN, unit, payload)
    summary = result["summary"]
    assert summary["feedback_received_rate"] == rate
    assert summary["feedback_received_rate_by_class"]["one_rtt"]["n"] == 20
    assert summary["c1_path_excluded"] is excluded
    assert "c1_path" not in result["checks"]


def test_classes_below_twenty_do_not_claim_pass():
    unit = unit_for()
    payload = payload_for(unit)
    payload["rows"][0]["ms"] = 1000
    payload["rows"][0]["feedback_wait_received"] = False
    summary = observations.unit_observations(PLAN, unit, payload)["summary"]
    assert summary["feedback_received_rate_by_class"]["one_rtt"]["status"] == "표본 부족"
    assert summary["feedback_received_rate_by_class"]["not_one_rtt"]["status"] == "표본 부족"
    assert not summary["c1_path_excluded"]


def test_class_rate_is_recomputed_after_combining_small_units():
    first = unit_for(task="X6", cell="D_p11_2955_l0", block=0)
    second = unit_for(task="X6", cell="D_p11_2955_l0", block=1)
    results = []
    for unit in (first, second):
        payload = payload_for(unit, ms=50)
        for row in payload["rows"][10:]:
            row["ms"] = 100
            row["feedback_wait_received"] = False
        results.append(observations.unit_observations(PLAN, unit, payload))
    assert all(not result["summary"]["c1_path_excluded"] for result in results)
    summary = observations.summarize_observations(PLAN, results)[0]
    assert summary["feedback_received_rate_by_class"]["not_one_rtt"]["n"] == 20
    assert summary["feedback_received_rate_by_class"]["not_one_rtt"]["rate"] == 0
    assert summary["c1_path_excluded"]


def test_missing_receipt_is_not_silently_false_or_removed_from_denominator():
    unit = unit_for()
    payload = payload_for(unit)
    del payload["rows"][0]["feedback_wait_received"]
    result = observations.unit_observations(PLAN, unit, payload)
    assert result["checks"]["feedback_received_field"] == "missing"
    assert result["summary"]["feedback_received"]["n"] == 20
    assert result["summary"]["feedback_received"]["received"] == 19
    assert result["summary"]["feedback_received"]["missing"] == 1
    assert result["summary"]["feedback_received_rate"] is None
    assert result["summary"]["c1_path_excluded"]


def test_low_valid_rtt_rate_is_only_a_warning():
    result = result_for(unit_for())
    assert result["summary"]["valid_rtt"]["valid_rtt_rate"] == 0
    assert result["summary"]["valid_rtt"]["warning"]
    assert all(value == "pass" for value in result["checks"].values())


def test_missing_valid_rtt_does_not_become_zero():
    result = result_for(unit_for(), path_rtt_valid=None)
    assert result["summary"]["valid_rtt"]["valid_rtt_rate"] is None
    assert result["summary"]["valid_rtt"]["missing"] == 20
    assert not result["summary"]["valid_rtt"]["warning"]


def test_frozen_rows_do_not_require_gen33_fields():
    unit = unit_for(arm="g2auto")
    result = result_for(unit, flight_expectation=None, feedback_wait_received=None,
                        feedback_wait_limit_ms=None, feedback_wait_ns=None)
    assert result["checks"] == {}
    assert result["summary"]["feedback_received"]["status"] == "해당 없음"
    assert result["summary"]["mean_wait_plus_gap_ms"] is None
    assert not result["summary"]["c1_path_excluded"]


def test_actual_wait_is_not_replaced_by_limit_or_zero_when_missing():
    result = result_for(unit_for(), feedback_wait_ns=None)
    assert result["summary"]["mean_feedback_wait_ms"] is None
    assert result["summary"]["mean_wait_plus_gap_ms"] is None
    assert result["summary"]["mean_idle_ms"] is None


def test_one_rtt_uses_strict_padding_aware_rule():
    unit = unit_for(arm="pad4L2")
    boundary = 1.5 * 200 + 8 * (2560 + 2 * 1300) / (1000 * 2)
    extra = {"kind": "pad_junk", "first_sent": 4, "first_lead": 2, "first_bytes": 5200}
    below = result_for(unit, ms=boundary - 0.001, extra_sent=extra)
    equal = result_for(unit, ms=boundary, extra_sent=extra)
    assert all(row["one_rtt"] for row in below["row_observations"])
    assert not any(row["one_rtt"] for row in equal["row_observations"])


def test_zero_rate_and_failed_rows_use_existing_classifier():
    unit = unit_for(cell="p11_l0")
    assert all(row["one_rtt"] for row in result_for(unit, ms=74.999)["row_observations"])
    assert not any(row["one_rtt"] for row in result_for(unit, ms=75)["row_observations"])
    assert not any(row["one_rtt"] for row in result_for(unit, ms=1, ok=False)["row_observations"])


def test_phase_keys_burnin_and_order_survive_aggregation():
    units = [unit_for(task="X6", cell="S_bigcert", phase=phase) for phase in (0, 1, 2)]
    results = [result_for(unit, ms=50, feedback_wait_ns=(phase + 1) * 1_000_000)
               for phase, unit in enumerate(units)]
    summary = observations.summarize_observations(PLAN, results)[0]
    assert summary == observations.summarize_observations(PLAN, list(reversed(results)))[0]
    assert summary["n_rows"] == 90
    assert summary["burnin"]["n_rows"] == 30
    assert summary["post_burnin"]["n_rows"] == 60
    assert [item["n_rows"] for item in summary["by_loss"]] == [60, 30]
    assert summary["mean_wait_plus_gap_ms"] == 3
    assert all(item["mean_idle_ms"] is None for item in summary["by_loss"])
    assert all(item["mean_idle_ms"] is None for item in summary["by_one_rtt"].values())
    assert len(summary["unit_boundaries"]["samples"]) == 2


def test_unit_boundaries_do_not_become_client_idle():
    first = result_for(unit_for(task="X6", cell="S_bigcert", block=0))
    second = result_for(unit_for(task="X6", cell="S_bigcert", block=1))
    second["started_at"] = "2026-11-06T00:00:15+00:00"
    summary = observations.summarize_observations(PLAN, [first, second])[0]
    assert summary["unit_boundaries"]["mean_elapsed_ms"] == 5000
    assert summary["mean_idle_ms"] is None


def test_cells_and_arms_are_not_combined():
    results = [result_for(unit_for()), result_for(unit_for(cell="bigcert_l2")),
               result_for(unit_for(arm="v33none"))]
    assert len(observations.summarize_observations(PLAN, results)) == 3


def test_duplicate_units_refused():
    result = result_for(unit_for())
    with pytest.raises(ValueError, match="중복"):
        observations.summarize_observations(PLAN, [result, deepcopy(result)])


@pytest.mark.parametrize("change", ["duplicate", "missing", "boolean", "count"])
def test_invalid_row_indices_are_not_positionally_repaired(change):
    unit = unit_for()
    payload = payload_for(unit)
    if change == "duplicate":
        payload["rows"][1]["i"] = 0
    elif change == "missing":
        del payload["rows"][0]["i"]
    elif change == "boolean":
        payload["rows"][0]["i"] = False
    else:
        payload["rows"].pop()
    with pytest.raises(ValueError, match="순번"):
        observations.unit_observations(PLAN, unit, payload)


def test_row_order_does_not_change_observations():
    unit = unit_for()
    payload = payload_for(unit)
    expected = observations.unit_observations(PLAN, unit, payload)
    payload["rows"].reverse()
    assert observations.unit_observations(PLAN, unit, payload) == expected


def test_mismatched_c1_setting_refused_in_aggregation():
    result = result_for(unit_for())
    result["feedback_enabled"] = False
    with pytest.raises(ValueError, match="C1 설정"):
        observations.summarize_observations(PLAN, [result])
