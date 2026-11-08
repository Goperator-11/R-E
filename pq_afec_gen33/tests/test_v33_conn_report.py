import copy
import json
from pathlib import Path

import pytest

from experiments.v33.lib import arms, report


def conn(scid="abcd", dcid="12345678", **changes):
    value = {"key": f"initial:{dcid}/{scid}", "initial_dcid": dcid, "client_scid": scid,
             "reason": "shutdown", "logged_ns": 100,
             "rx_bytes": 3000, "rx_orig_bytes": 2600, "rx_parity_bytes": 400,
             "stack_bytes": 2800, "beff_stack": 2700, "beff_phys": 2700,
             "beff_orig": 2300, "beff_parity": 400,
             "tx_rx_timeline": [2700, 2800], "tx_sizes": [1280, 900], "tx_ns": [70, 80]}
    value.update(changes)
    return value


def write_log(path, values):
    path.write_text("".join(json.dumps(value) + "\n" for value in values), encoding="utf-8")


def fixture(tmp_path, arm="m4L3", task="M0"):
    plan = json.loads((Path(__file__).resolve().parents[1] /
                       "g3/v33/plans/final_bundle_v1.json").read_text(encoding="utf-8"))
    unit = next(item for item in arms.iter_units(plan, [task]) if item["arm"] == arm)
    unit["rows_expected"] = 2
    path = tmp_path / "conns.jsonl"
    records = [conn("abcd"), conn("eeee")]
    write_log(path, records)
    stats = {"bytes_in": 6000, "parities": 2, "recovered": 1, "credit_parities": 1,
             "fb_sent": 0, "tls_accepted": 2, "feedback_version": 2, "fec_parse_fail": 0,
             "conn_acct_evicted_lru": 0,
             "conn_log": {"path": str(path), "lines": 2, "errors": 0, "pending": 0}}
    server = {"returncode": 0, "forced_kill": False, "exited_before_stop": False,
              "conn_log_path": str(path), "stats": stats}
    payload = {"rows": [{"ok": True, "client_scid": "abcd"}, {"ok": True, "client_scid": "eeee"}],
               "server": server}
    return plan, unit, payload, path, records


def test_conn_log_retains_record_fields_and_order(tmp_path):
    path = tmp_path / "conns.jsonl"
    records = [conn("eeee", reason="expired"), conn("abcd", rx_bytes=0)]
    write_log(path, records)
    assert report.read_conn_log(path) == records
    path.write_bytes(b"")
    assert report.read_conn_log(path) == []


@pytest.mark.parametrize("raw", [b"{\n", b"{}\n", b"[]\n", b"null\n", b"\n",
    b'{"key":"a","key":"b"}\n', b'{"key":NaN}\n', b'{"key":1e999}\n', b"\xff\n",
    b'{}', b'\xef\xbb\xbf{}\n'])
def test_conn_log_rejects_corrupt_rows(tmp_path, raw):
    path = tmp_path / "conns.jsonl"
    path.write_bytes(raw)
    with pytest.raises(ValueError):
        report.read_conn_log(path)


@pytest.mark.parametrize("field,value", [("rx_bytes", True), ("beff_stack", -1),
    ("rx_parity_bytes", 1.5), ("reason", "unknown"), ("key", ""),
    ("client_scid", None), ("logged_ns", False), ("tx_sizes", [1, -1])])
def test_conn_log_rejects_invalid_record_fields(tmp_path, field, value):
    path = tmp_path / "conns.jsonl"
    write_log(path, [conn(**{field: value})])
    with pytest.raises(ValueError):
        report.read_conn_log(path)


def test_conn_log_rejects_duplicate_connection_keys(tmp_path):
    path = tmp_path / "conns.jsonl"
    write_log(path, [conn(), conn(reason="expired")])
    with pytest.raises(ValueError, match="key 중복"):
        report.read_conn_log(path)


def test_client_finished_loss_is_not_missing_or_failed(tmp_path):
    plan, unit, payload, path, records = fixture(tmp_path)
    payload["server"]["stats"]["tls_accepted"] = 1
    initial = copy.deepcopy(payload)
    result = report.validate_server_unit(plan, unit, payload)
    assert result["execution_status"] == "판정 통과"
    assert result["has_data"] and not result["reject_block"]
    assert result["not_accepted"] == 1
    assert result["server_delta"] == {"bytes_in": 6000, "parities": 2,
                                      "recovered": 1, "credit_parities": 1}
    assert result["scid_matching"]["matched"] == 2
    assert payload == initial


@pytest.mark.parametrize("field,value", [("returncode", 1), ("returncode", -9),
    ("returncode", False), ("returncode", None), ("forced_kill", True),
    ("forced_kill", None), ("exited_before_stop", True)])
def test_bad_server_completion_marks_unit_missing(tmp_path, field, value):
    plan, unit, payload, path, records = fixture(tmp_path)
    payload["server"][field] = value
    result = report.validate_server_unit(plan, unit, payload)
    assert result["execution_status"] == "자료 없음"
    assert result["checks"]["server_process"] == "missing"
    assert result["reject_block"]


@pytest.mark.parametrize("field,value", [("lines", 3), ("lines", 1), ("errors", 1),
    ("pending", 1), ("lines", False), ("lines", None)])
def test_bad_conn_log_stats_marks_unit_missing(tmp_path, field, value):
    plan, unit, payload, path, records = fixture(tmp_path)
    payload["server"]["stats"]["conn_log"][field] = value
    result = report.validate_server_unit(plan, unit, payload)
    assert result["execution_status"] == "자료 없음"
    assert result["checks"]["connection_collection"] == "missing"
    assert result["reject_block"]


@pytest.mark.parametrize("field", ["bytes_in", "parities", "recovered", "credit_parities", "fb_sent",
    "tls_accepted", "feedback_version", "fec_parse_fail", "conn_acct_evicted_lru", "conn_log"])
def test_missing_stats_field_is_never_normal_zero(tmp_path, field):
    plan, unit, payload, path, records = fixture(tmp_path)
    del payload["server"]["stats"][field]
    result = report.validate_server_unit(plan, unit, payload)
    assert result["execution_status"] == "자료 없음"
    assert result["reject_block"]


@pytest.mark.parametrize("changed", ["deleted", "malformed", "truncated", "wrong_path", "lru", "tls_exceeds"])
def test_missing_or_inconsistent_log_is_not_replaced_by_stats_conns(tmp_path, changed):
    plan, unit, payload, path, records = fixture(tmp_path)
    payload["server"]["stats"]["conns"] = {item["key"]: item for item in records}
    if changed == "deleted":
        path.unlink()
    elif changed == "malformed":
        path.write_bytes(b"{}\n")
    elif changed == "truncated":
        path.write_bytes(path.read_bytes()[:-1])
    elif changed == "wrong_path":
        payload["server"]["stats"]["conn_log"]["path"] = str(path.with_name("other.jsonl"))
    elif changed == "lru":
        payload["server"]["stats"]["conn_acct_evicted_lru"] = 1
    else:
        payload["server"]["stats"]["tls_accepted"] = 3
    result = report.validate_server_unit(plan, unit, payload)
    assert result["execution_status"] == "자료 없음"
    assert result["reject_block"]


def test_failed_rows_can_have_no_server_account(tmp_path):
    plan, unit, payload, path, records = fixture(tmp_path)
    payload["rows"][1]["ok"] = False
    write_log(path, records[:1])
    payload["server"]["stats"]["conn_log"]["lines"] = 1
    payload["server"]["stats"]["tls_accepted"] = 1
    result = report.validate_server_unit(plan, unit, payload)
    assert result["execution_status"] == "판정 통과"
    assert result["scid_matching"]["unmatched_client_rows"] == [1]
    payload["rows"][1]["ok"] = True
    assert report.validate_server_unit(plan, unit, payload)["execution_status"] == "자료 없음"


@pytest.mark.parametrize("arm", ["v31auto", "g2auto"])
def test_frozen_client_still_uses_gen33_conn_log(tmp_path, arm):
    plan, unit, payload, path, records = fixture(tmp_path, arm=arm)
    for row in payload["rows"]:
        del row["client_scid"]
    result = report.validate_server_unit(plan, unit, payload)
    assert result["execution_status"] == "판정 통과"
    assert result["conn_source"] == "conn_log"
    assert result["frozen_arm_fb_sent"] == 0
    assert result["scid_matching"]["status"] == "동결 클라이언트 필드 미제공"
    payload["server"]["stats"]["fb_sent"] = 1
    result = report.validate_server_unit(plan, unit, payload)
    assert result["execution_status"] == "판정 실패"
    assert result["checks"]["frozen_feedback"] == "fail"
    assert result["has_data"] and result["reject_block"]
    assert result["incidents"][0]["check"] == "frozen_feedback"


@pytest.mark.parametrize("arm", ["a", "e"])
def test_actual_frozen_servers_use_stats_conns_without_inventing_gen33_fields(tmp_path, arm):
    plan, unit, payload, path, records = fixture(tmp_path, arm=arm, task="M1")
    old_stats = {key: payload["server"]["stats"][key]
                 for key in ("bytes_in", "parities", "recovered", "credit_parities", "fb_sent")}
    old_stats["conns"] = {item["key"]: {key: value for key, value in item.items()
                                      if key not in ("key", "reason", "logged_ns")}
                          for item in records}
    payload["server"]["stats"] = old_stats
    payload["server"]["conn_log_path"] = None
    path.unlink()
    result = report.validate_server_unit(plan, unit, payload)
    assert result["execution_status"] == "판정 통과"
    assert result["conn_source"] == "frozen_stats"
    assert len(result["conns"]) == 2
    assert result["conn_log"] is None and result["tls_accepted"] is None
    assert result["feedback_version"] is None and result["fec_parse_fail"] is None


def test_only_m1_g_can_omit_gen33_connection_log(tmp_path):
    plan, unit, payload, path, records = fixture(tmp_path, arm="c", task="M1")
    unit["arm"] = "g"
    payload["server"]["conn_log_path"] = None
    del payload["server"]["stats"]["conn_log"]
    path.unlink()
    result = report.validate_server_unit(plan, unit, payload)
    assert result["execution_status"] == "판정 통과"
    assert result["conn_source"] == "planned_omission"
    assert result["conns"] is None
    unit["arm"] = "c"
    assert report.validate_server_unit(plan, unit, payload)["execution_status"] == "자료 없음"
    plan["arms"]["c"]["conn_log"] = False
    assert report.validate_server_unit(plan, unit, payload)["execution_status"] == "자료 없음"


def test_c1_v3_is_failed_and_rejected_but_not_missing(tmp_path):
    plan, unit, payload, path, records = fixture(tmp_path, arm="v33c1")
    payload["server"]["stats"]["fb_sent"] = 2
    payload["server"]["stats"]["feedback_version"] = 3
    result = report.validate_server_unit(plan, unit, payload)
    assert result["execution_status"] == "판정 실패"
    assert result["has_data"] and result["reject_block"]
    assert result["checks"]["c1_feedback_version"] == "fail"


def test_auto_parse_failure_is_a_check_failure_with_complete_data(tmp_path):
    plan, unit, payload, path, records = fixture(tmp_path, arm="v33none")
    payload["server"]["stats"]["fec_parse_fail"] = 1
    result = report.validate_server_unit(plan, unit, payload)
    assert result["execution_status"] == "판정 실패"
    assert result["has_data"] and not result["reject_block"]
    assert result["checks"]["fec_parse_fail"] == "fail"


def test_scid_join_does_not_depend_on_log_order(tmp_path):
    plan, unit, payload, path, records = fixture(tmp_path)
    first = report.validate_server_unit(plan, unit, payload)["scid_matching"]
    write_log(path, list(reversed(records)))
    second = report.validate_server_unit(plan, unit, payload)["scid_matching"]
    assert first == second
    assert first["matches"][0]["conn_key"] == records[0]["key"]


def test_scid_diagnostics_do_not_guess_for_empty_or_duplicate_ids():
    rows = [{"client_scid": "aa"}, {"client_scid": "aa"}, {}, {"client_scid": "bb"},
            {"client_scid": "cc"}, {"client_scid": "dd"}]
    records = [conn("aa"), conn("bb"), conn("bb", dcid="87654321"), conn(""), conn("dd")]
    result = report.match_client_scids(rows, records)
    assert result["matches"] == [{"row_index": 5, "client_scid": "dd", "conn_key": "initial:12345678/dd"}]
    assert result["duplicate_client_scids"] == {"aa": [0, 1]}
    assert result["duplicate_server_scids"] == {"bb": ["initial:12345678/bb", "initial:87654321/bb"]}
    assert result["empty_client_rows"] == [2]
    assert result["empty_server_keys"] == ["initial:12345678/"]
    assert result["unmatched_client_rows"] == [0, 1, 2, 3, 4]


def test_unit_identity_keeps_phase_and_global_block(tmp_path):
    plan, unit, payload, path, records = fixture(tmp_path)
    first = report.validate_server_unit(plan, unit, payload)["unit_identity"]
    unit["phase"] += 1
    unit["block_across_phases"] += 10
    second = report.validate_server_unit(plan, unit, payload)["unit_identity"]
    assert first["block"] == second["block"]
    assert first["phase"] != second["phase"]
    assert first["block_across_phases"] != second["block_across_phases"]


@pytest.mark.parametrize("arm", ["a", "e"])
def test_frozen_certificate_observation_reads_actual_stderr_without_changing_checks(tmp_path, arm):
    plan, unit, payload, path, records = fixture(tmp_path, arm=arm, task="M1")
    payload["server"]["stats"]["conns"] = {item["key"]: item for item in records}
    before = report.validate_server_unit(plan, unit, payload)
    stderr = tmp_path / "server.stderr"
    stderr.write_bytes(b"cert DER = 42167 bytes\nREADY fixture:4433\n")
    payload["server"]["stderr_path"] = str(stderr)
    saved = copy.deepcopy(payload)
    observed = report.validate_server_unit(plan, unit, payload)
    assert observed["certificate_observation"] == {
        "source": "server.stderr", "status": "확인", "der_bytes": 42167, "reported_lines": 1}
    assert observed["checks"] == before["checks"]
    assert observed["execution_status"] == before["execution_status"] == "판정 통과"
    assert payload == saved
    stderr.write_bytes(b"cert DER = 42168 bytes\r\nREADY fixture:4433\r\n")
    assert report.validate_server_unit(plan, unit, payload)["certificate_observation"]["der_bytes"] == 42168


@pytest.mark.parametrize("raw,count", [
    (b"READY fixture:4433\n", 0),
    (b"cert DER = 42167 bytes\ncert DER = 42167 bytes\n", 2),
    (b"cert DER = 0 bytes\n", 1),
    (b"cert DER = -1 bytes\n", 1),
    (b"cert DER = 42167 bytes", 1),
    (b"cert DER = unknown bytes\n", 1),
])
def test_frozen_certificate_missing_or_ambiguous_is_unknown_not_filled(tmp_path, raw, count):
    plan, unit, payload, path, records = fixture(tmp_path, arm="a", task="M1")
    payload["server"]["stats"]["conns"] = {item["key"]: item for item in records}
    stderr = tmp_path / "server.stderr"
    stderr.write_bytes(raw)
    payload["server"]["stderr_path"] = str(stderr)
    result = report.validate_server_unit(plan, unit, payload)
    observed = result["certificate_observation"]
    assert observed["status"] == "미확인" and observed["der_bytes"] is None
    assert observed["reported_lines"] == count and observed["reason"]
    assert result["execution_status"] == "판정 통과"


def test_frozen_certificate_unreadable_path_is_unknown_and_m0_contract_is_unchanged(tmp_path):
    plan, unit, payload, path, records = fixture(tmp_path, arm="a", task="M1")
    payload["server"]["stderr_path"] = str(tmp_path / "absent.stderr")
    observed = report.validate_server_unit(plan, unit, payload)["certificate_observation"]
    assert observed["status"] == "미확인" and observed["der_bytes"] is None
    assert observed["reported_lines"] is None and observed["reason"]
    plan, unit, payload, path, records = fixture(tmp_path, arm="v31auto", task="M0")
    assert "certificate_observation" not in report.validate_server_unit(plan, unit, payload)
