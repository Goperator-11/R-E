import hashlib
import json
from pathlib import Path

import pytest

from experiments.v33 import x6_diagnostics as tool


def _unit(rows=4):
    return {"key": "X6.S.t0.p0.b0.a", "rows_expected": rows, "phase": 0, "block": 0, "connection_offset": 30}


def test_point_keeps_absent_key_marker_and_connection_index():
    unit = _unit()
    present = tool.point_row(unit, {"i": 2, "p_mean": 0.25})
    absent = tool.point_row(unit, {"i": 3})
    assert present == {"unit_key": unit["key"], "phase": 0, "block": 0, "i": 2, "connection_offset": 30,
                       "connection_index": 32, "p_mean_present": True, "p_mean": 0.25}
    assert absent["p_mean_present"] is False and absent["p_mean"] is None


def test_null_p_mean_differs_from_absent_key():
    point = tool.point_row(_unit(), {"i": 1, "p_mean": None})
    assert point["p_mean_present"] is True and point["p_mean"] is None


def test_idle_uses_first_rx_order_and_skips_last_connection():
    rows = [{"i": index, "ok": True, "ms": 10.0} for index in range(3)]
    conns = [{"first_rx_ns": 2_000_000_000, "client_scid": "c"},
             {"first_rx_ns": 1_000_000_000, "client_scid": "a"},
             {"first_rx_ns": 1_100_000_000, "client_scid": "b"}]
    samples, problem, mismatch = tool.idle_samples(_unit(3), rows, conns)
    assert problem is None and mismatch == 0
    assert [item["i"] for item in samples] == [0, 1]
    assert samples[0]["spacing_ms"] == pytest.approx(100.0)
    assert samples[0]["idle_ms"] == pytest.approx(90.0)
    assert samples[1]["idle_ms"] == pytest.approx(890.0)


def test_idle_counts_scid_rank_mismatch():
    rows = [{"i": 0, "ok": True, "ms": 1.0, "client_scid": "b"}, {"i": 1, "ok": True, "ms": 1.0, "client_scid": "a"}]
    conns = [{"first_rx_ns": 1, "client_scid": "a"}, {"first_rx_ns": 2, "client_scid": "b"}]
    assert tool.idle_samples(_unit(2), rows, conns)[2] == 2


@pytest.mark.parametrize("rows,conns", [
    ([{"i": 0, "ok": False, "ms": 1.0}, {"i": 1, "ok": True, "ms": 1.0}],
     [{"first_rx_ns": 1, "client_scid": ""}, {"first_rx_ns": 2, "client_scid": ""}]),
    ([{"i": 0, "ok": True, "ms": 1.0}, {"i": 1, "ok": True, "ms": 1.0}], [{"first_rx_ns": 1, "client_scid": ""}]),
    ([{"i": 0, "ok": True, "ms": 1.0}], [{"client_scid": ""}])])
def test_idle_refuses_unusable_units(rows, conns):
    samples, problem, _ = tool.idle_samples(_unit(2), rows, conns)
    assert samples == [] and problem is not None


def test_loss_row_uses_attempts_denominator():
    row = tool.loss_row(98, 2, 2, 0.999)
    assert row["attempts"] == 100 and row["realized_rate"] == 0.02
    assert row["inside_prediction_interval"] is True


def test_loss_row_zero_attempts():
    assert tool.loss_row(0, 0, 2, 0.999)["realized_rate"] is None


def test_raw_unit_rejects_changed_bytes(tmp_path):
    relative = "units/K/attempt_0/client.jsonl"
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(b'{"i":0}\n')
    meta = {"attempt": 0, "raw_sha256": {relative: hashlib.sha256(b"other").hexdigest()}}
    with pytest.raises(ValueError):
        tool.RawUnit(tmp_path, {"key": "K", "rows_expected": 1}, meta).read("client.jsonl")


def test_series_bytes_are_canonical():
    assert tool.canonical({"b": 1, "a": [1.5]}) == b'{"a":[1.5],"b":1}\n'


def test_document_states_official_idle_is_kept():
    whole = {"rows": 2, "mean": 1.5, "ci95": [1.0, 2.0]}
    diagnostics = {"task": "X6", "run_id": "r",
                   "provenance": {"result_sha256": "a" * 64, "journal_sha256": "b" * 64, "series_sha256": "c" * 64},
                   "p_mean": {"summary": [{"cell": "C", "arm": "g2auto", "points": 2, "numeric": 0, "key_absent": 2, "present_null": 0}],
                              "crosscheck_with_result": {"compared": 3, "mismatches": []}},
                   "idle_approx": {"kind": "근사", "official": {"status": "미확인", "decision": "D79"}, "limits": ["한계"],
                                   "arms": [{"cell": "C", "arm": "a", "whole_trajectory_including_burnin": whole, "median_ms": 1.0}],
                                   "contrasts": [], "judgment_approx": [],
                                   "exclusion_rule": {"reason": "사유"},
                                   "excluded_rows": [{"unit": "U", "i": 1, "idle_ms": 7015.0, "spacing_ms": 7094.0, "hct_ms": 79.0,
                                                      "first_rx_utc": "t"}]},
                   "realized_loss": {"source": "tc", "note": "참고", "by_cell_arm_loss": [
                       {"cell": "C", "arm": "a", "nominal_pct": 2, "attempts": 100, "dropped": 2, "realized_rate": 0.02,
                        "prediction_interval_dropped": [0, 8], "inside_prediction_interval": True}]},
                   "fec_parse_fail": {"sum_by_cell_arm": [], "events": [], "effects": []}, "policy_state": []}
    document = tool.render_document(diagnostics, "series.json")
    assert "상태 미확인, 결정 D79" in document
    assert "키 부재" in document and "| C | g2auto | 2 | 0 | 2 | 0 |" in document
    assert "7015" in document and "series.json" in document
