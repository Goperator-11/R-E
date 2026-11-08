from copy import deepcopy
import json
from pathlib import Path

import pytest

from experiments.v33.lib import report


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def statistics():
    return json.loads((ROOT / "g3/v33/plans/final_bundle_v1.json").read_text(
        encoding="utf-8"))["statistics"]


def test_result_metadata_reuses_stored_identity_and_nested_environment(monkeypatch):
    stored = report.capture_metadata({"env": {"uname_r": "captured-kernel"},
                                      "started_at": "captured-time"})
    expected = json.dumps(stored, sort_keys=True)
    monkeypatch.setattr(report.learn3, "POLICY_VERSION", "changed-after-measurement")
    monkeypatch.setenv("PADFEC_X", "changed-after-measurement")
    first = report.result_metadata(stored)
    assert json.dumps(first, sort_keys=True) == expected
    assert first["policy_version"] == "v3.3.1-dev"
    first["env"]["uname_r"] = "caller-mutated"
    assert json.dumps(report.result_metadata(stored), sort_keys=True) == expected


@pytest.mark.parametrize("field,value", [("label", "confirmatory"),
                                         ("confirmatory", True),
                                         ("confirmatory", 0),
                                         ("policy_version", "wrong-version")])
def test_capture_metadata_rejects_conflicting_identity(field, value):
    with pytest.raises(ValueError):
        report.capture_metadata({field: value})


@pytest.mark.parametrize("stored", [{}, {"label": "development", "confirmatory": False},
                                    {"label": "development", "confirmatory": 0,
                                     "policy_version": "v3.3.1-dev"}])
def test_report_only_rejects_missing_identity(stored):
    with pytest.raises(ValueError):
        report.result_metadata(stored)


def test_row_provenance_preserves_frozen_policy_and_input():
    row = {"policy_version": "v3.1", "nested": {"value": 1}}
    original = deepcopy(row)
    result = report.attach_row_provenance(row, plan_sha256="a" * 64,
                                         binary_sha256="b" * 64, srcsha="c" * 64,
                                         server_binary_sha256="d" * 64,
                                         server_srcsha="e" * 64)
    assert row == original
    assert result["policy_version"] == "v3.1"
    assert result["plan_sha256"] == "a" * 64
    assert result["server_binary_sha256"] == "d" * 64
    result["nested"]["value"] = 2
    assert row == original


@pytest.mark.parametrize("change", ["conflict", "missing_server_source", "invalid_digest"])
def test_row_provenance_refuses_conflict_and_partial_identity(change):
    row = {}
    values = {"plan_sha256": "a" * 64, "binary_sha256": "b" * 64, "srcsha": "c" * 64}
    if change == "conflict":
        row["plan_sha256"] = "d" * 64
    elif change == "missing_server_source":
        values["server_binary_sha256"] = "d" * 64
    else:
        values["srcsha"] = None
    with pytest.raises(ValueError):
        report.attach_row_provenance(row, **values)


@pytest.mark.parametrize("has_data,checks,expected", [
    (False, {}, "자료 없음"), (True, {"rows": "missing"}, "자료 없음"),
    (True, {"rows": "pass", "bounds": "fail"}, "판정 실패"),
    (True, {"rows": "pass", "bounds": "pass"}, "판정 통과")])
def test_execution_status(has_data, checks, expected):
    assert report.execution_status(has_data=has_data, checks=checks) == expected


@pytest.mark.parametrize("checks", [{}, {"rtt": "warning"}, {"rows": True}])
def test_execution_status_requires_explicit_data_checks(checks):
    with pytest.raises(ValueError):
        report.execution_status(has_data=True, checks=checks)


@pytest.mark.parametrize("interval,expected", [([-5, 5], "판정 가능"),
                                               ([-5.001, 5], "판정불능"),
                                               ([-5, 5.001], "판정불능")])
def test_m1_tolerance_is_closed_and_inference_does_not_fail_execution(statistics,
                                                                    interval, expected):
    decision = report.m1_aa({"mean": 0, "ci95": interval}, statistics)
    assert decision["inference_status"] == expected
    assert report.execution_status(has_data=True, checks={"rows": "pass"}) == "판정 통과"


@pytest.mark.parametrize("contrast", [{"mean": float("nan"), "ci95": [-1, 1]},
                                       {"mean": 0, "ci95": [1, -1]},
                                       {"mean": 2, "ci95": [-1, 1]},
                                       {"mean": 0, "ci95": [-1, float("inf")]},
                                       {"mean": False, "ci95": [-1, 1]}])
def test_m1_invalid_statistics_are_not_silently_accepted(statistics, contrast):
    with pytest.raises(ValueError):
        report.m1_aa(contrast, statistics)


def test_aa_ruler_uses_absolute_mean_and_halfwidth(statistics):
    m1 = {"contrasts": {"c_d": {"mean": -2, "ci95": [-6, 2]}}}
    result = report.aa_ruler(m1, task="X6", profile="bigcert", loss_pct=2,
                             statistics=statistics)
    assert result["ruler_ms"] == 6
    assert result["note"] == "자 표류 큼"
    assert result["inference_status"] == "판정불능"


@pytest.mark.parametrize("task,profile,loss", [("X1", "rtt200", 2),
                                               ("X6", "bigcert", 15),
                                               ("X9", "bigcert", 2)])
def test_aa_ruler_is_not_transferred_to_other_cells(statistics, task, profile, loss):
    result = report.aa_ruler(None, task=task, profile=profile, loss_pct=loss,
                             statistics=statistics)
    assert result == {"applies": False, "ruler_ms": None, "note": "A/A 없음"}


def test_applicable_aa_ruler_requires_m1_result(statistics):
    with pytest.raises(ValueError, match="M1"):
        report.aa_ruler(None, task="X1", profile="bigcert", loss_pct=2,
                        statistics=statistics)


@pytest.mark.parametrize("valid,total,rate,warning", [(90, 100, 0.9, False),
                                                      (89, 100, 0.89, True),
                                                      (0, 100, 0, True),
                                                      (0, 0, None, False)])
def test_valid_rtt_is_warning_only(valid, total, rate, warning):
    result = report.valid_rtt_warning(valid, total)
    assert result["valid_rtt_rate"] == rate
    assert result["warning"] is warning
    assert "status" not in result
    assert "checks" not in result


@pytest.mark.parametrize("valid,total,threshold", [(2, 1, 0.9), (-1, 1, 0.9),
                                                   (True, 1, 0.9), (0, -1, 0.9),
                                                   (0, 1, float("nan"))])
def test_valid_rtt_invalid_counts_are_rejected(valid, total, threshold):
    with pytest.raises(ValueError):
        report.valid_rtt_warning(valid, total, threshold=threshold)


def cache_fixture(binary_id):
    if binary_id == "g2":
        entry = {field: 0 for field in (
            "k", "server_flight", "min_hct_ms", "min_rtt_ms", "rtt_observations",
            "loss_count", "obs_count", "loss_hct_ms", "probe_min_hct_ms", "sym_loss",
            "sym_obs", "sym_c2_conns", "sym_c2_symbols", "conns", "since_probe")}
        return {"test-address": entry}
    version = 11 if binary_id == "gen33" else 2
    state = {"v": version, "k_hist": [], "S_hist": [], "hct": {}, "hct_seq": {},
             "seq": 0, "post": [[1 / 26] * 26 for _ in range(5)], "w": [0.2] * 5,
             "n_dec": 0, "n_reeval": 0, "g_resid": {}, "g_common": [],
             "g_alarm": {}, "stats": {}}
    if binary_id == "gen33":
        state.update(c1_seen=False, arrival_streak=0)
    entry = {"state": state, "min_rtt_ms": 0, "rtt_observations": 0,
             "min_hct_ms": 0, "conns": 0}
    return {"schema": f"padfec3.cache3/{version}", "dests": {"test-address": entry}}


@pytest.mark.parametrize("binary_id", ["gen33", "g3c", "g2"])
def test_cache_structure_matches_binary_generation_and_preserves_bytes(binary_id):
    value = cache_fixture(binary_id)
    raw = json.dumps(value, indent=2).encode() + b"\n"
    original = bytes(raw)
    assert report.validate_cache_bytes(raw, binary_id, "test-address") == value
    assert raw == original


@pytest.mark.parametrize("source,target", [("gen33", "g3c"), ("g3c", "gen33"),
                                          ("g2", "gen33"), ("gen33", "g2")])
def test_cache_generation_mixing_is_rejected(source, target):
    with pytest.raises(ValueError):
        report.validate_cache_bytes(json.dumps(cache_fixture(source)).encode(),
                                    target, "test-address")


@pytest.mark.parametrize("binary_id", ["gen33", "g3c", "g2"])
def test_cache_expected_destination_is_required(binary_id):
    with pytest.raises(ValueError, match="목적지"):
        report.validate_cache_bytes(json.dumps(cache_fixture(binary_id)).encode(),
                                    binary_id, "different-address")


@pytest.mark.parametrize("change", ["missing_counter", "nonfinite", "post_shape",
                                    "missing_c1", "bool_counter", "null_state"])
def test_cache3_malformed_state_is_rejected(change):
    value = cache_fixture("gen33")
    entry = value["dests"]["test-address"]
    if change == "missing_counter":
        del entry["conns"]
    elif change == "nonfinite":
        entry["state"]["post"][0][0] = float("inf")
    elif change == "post_shape":
        entry["state"]["post"][0].pop()
    elif change == "missing_c1":
        del entry["state"]["c1_seen"]
    elif change == "bool_counter":
        entry["state"]["n_dec"] = False
    else:
        entry["state"] = None
    with pytest.raises(ValueError):
        report.validate_cache_bytes(json.dumps(value).encode(), "gen33", "test-address")


@pytest.mark.parametrize("raw", [b'{"same": {}, "same": {}}', b'{"truncated":',
                                b'{"first": {}} {"second": {}}', b'null', b'[]'])
def test_cache_invalid_json_cannot_become_fresh_state(raw):
    with pytest.raises(ValueError):
        report.validate_cache_bytes(raw, "g2")


def test_cache_snapshot_content_is_validated_after_digest_check(tmp_path):
    from experiments.v33.lib import blocks

    path = tmp_path / "cache.json"
    path.write_bytes(b'{"schema":"padfec3.cache3/11","dests":{"test-address":{}}}')
    snapshot = blocks.snapshot_cache(path)
    raw = blocks.snapshot_bytes(snapshot)
    with pytest.raises(ValueError, match="필수 필드"):
        report.validate_cache_bytes(raw, "gen33", "test-address")


@pytest.fixture
def m1_input():
    plan = json.loads((ROOT / "g3/v33/plans/final_bundle_v1.json").read_text(encoding="utf-8"))
    value = {"task": "M1", "label": "development", "confirmatory": False,
             "policy_version": plan["policy_version"], "plan_sha256": "a" * 64,
             "execution_status": "판정 통과", "status": "판정 가능", "n_blocks": 30,
             "contrasts": {name: {"mean": 0, "ci95": [-5, 5], "n_blocks": 30}
                           for name in plan["tasks"]["M1"]["primary"]},
             "a_vs_sealed": {"delta_ms": 0}}
    return plan, value


@pytest.mark.parametrize("interval,status", [([-5, 5], "판정 가능"), ([-6, 6], "판정불능")])
def test_m1_result_requires_complete_execution_but_accepts_inconclusive_aa(m1_input, interval, status):
    plan, value = m1_input
    value["contrasts"]["c_d"]["ci95"] = interval
    value["status"] = status
    result = report.validate_m1_result(value, plan, "a" * 64)
    assert result == value
    result["contrasts"]["c_d"]["mean"] = 1
    assert value["contrasts"]["c_d"]["mean"] == 0


@pytest.mark.parametrize("mutation", [
    lambda value: value.update(task="M0"),
    lambda value: value.update(policy_version="v3.3-dev"),
    lambda value: value.update(plan_sha256="b" * 64),
    lambda value: value.update(execution_status="자료 없음"),
    lambda value: value.update(execution_status="판정 실패"),
    lambda value: value.update(n_blocks=29),
    lambda value: value.update(n_blocks=True),
    lambda value: value["contrasts"].pop("a_b"),
    lambda value: value["contrasts"]["e_f"].update(n_blocks=29),
    lambda value: value["contrasts"]["b_c"].update(n_blocks=31),
    lambda value: value["contrasts"]["a_b"].update(ci95=[0, float("inf")]),
    lambda value: value["contrasts"]["e_f"].update(mean=6),
    lambda value: value["contrasts"]["b_c"].update(mean=True),
    lambda value: value.update(status="판정불능"),
    lambda value: value.pop("a_vs_sealed"),
    lambda value: value["a_vs_sealed"].update(delta_ms=float("nan")),
])
def test_m1_result_rejects_wrong_task_plan_incomplete_pairs_and_missing_drift(m1_input, mutation):
    plan, value = m1_input
    mutation(value)
    with pytest.raises(ValueError):
        report.validate_m1_result(value, plan, "a" * 64)
