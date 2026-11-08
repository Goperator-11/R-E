from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from experiments.v33 import devreport
from experiments.v33.lib import report_docs


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def document_result():
    scope = {"n_rows": 30, "hct": {"mean": 81.25, "ci95": [80.0, 82.5]},
             "success_hct_mean_ms": 81.25, "failure_rate": 0, "one_rtt_rate": 0.9,
             "server_cost": {"bytes_in": 90000, "n_rows": 30, "bytes_per_conn": 3000,
                             "source": "server_delta.bytes_in", "status": "pass"},
             "first_flight_bytes_mean": 2560}
    return {"task": "X6", "run_id": "fixture", "label": "development", "confirmatory": False,
            "policy_version": "v3.3.1-dev", "status": "기술통계", "execution_status": "판정 통과",
            "conditions": {"quic_go_version": "v0.61.0", "w_base_bytes": 1280,
                           "initial_congestion_window_packets": 32,
                           "loss_direction": "c2s_only_except_X9_both"},
            "checks": {"w_bound": "pass", "server_uniform": "pass"},
            "statistics": {"cells": [{"cell": "S_bigcert", "arms": [
                {"arm": "v33none", "primary": scope, "all": scope}], "contrasts": [
                {"id": "c1_none", "x": "v33c1", "y": "v33none", "scope": "primary",
                 "hct": {"mean": 1.5, "ci95": [-0.5, 3.5], "n": 4, "df": 3},
                 "aa": {"status": "A/A 없음"}, "inference_status": "판정불능"}]}]},
            "m1_result": {"contrasts": {"a_b": {"mean": 0, "ci95": [-5, 5]},
                                        "e_f": {"mean": 0, "ci95": [-5, 5]},
                                        "c_d": {"mean": 0, "ci95": [-5, 5]}},
                          "a_vs_sealed": {"delta_ms": 5}},
            "server_summary": [{"cell": "S_bigcert", "arm": "g2auto", "fec_parse_fail": 0,
                                "g2auto_ips_used_ge1395": 7,
                                "client_parity_count_unreliable": True}],
            "observations": [{"cell": "S_bigcert", "arm": "v33none",
                              "valid_rtt": {"valid_rtt_rate": 0.98}, "mean_idle_ms": None,
                              "idle_status": "미확인", "mean_wait_plus_gap_ms": 50,
                              "c1_path_excluded": False}]}


@pytest.mark.parametrize("task", ["M0", "M1", "X1", "X6", "X9"])
def test_generated_document_passes_check_docs(document_result, tmp_path, task):
    document_result["task"] = task
    path = tmp_path / f"{task}_result.md"
    text = report_docs.render_document(document_result)
    path.write_text(text, encoding="utf-8", newline="\n")
    process = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "tools/check_docs.py"),
                              "--root", str(tmp_path), "--file", str(path)], cwd=ROOT, text=True,
                             encoding="utf-8", capture_output=True, timeout=30)
    assert process.returncode == 0, process.stdout + process.stderr
    assert "initial congestion window 32" in text.split("\n\n")[1]
    assert "development" in text.split("\n\n")[1]
    assert report_docs.check_document(path, result=document_result)["status"] == "pass"


@pytest.mark.parametrize("name", ["a_b", "e_f"])
@pytest.mark.parametrize("interval", [[-5.000001, 4], [-4, 5.000001]])
def test_server_equivalence_branch_is_independent(document_result, name, interval):
    document_result["m1_result"]["contrasts"][name]["ci95"] = interval
    text = report_docs.render_document(document_result)
    first = text.split("\n\n")[1]
    assert "봉인 측정과 직접 비교 불가" in first
    assert "봉인 환경과 표류가 있다" not in first
    assert "자 표류 큼" not in first
    assert "83.1" not in text


@pytest.mark.parametrize("task", ["X1", "X6", "X9"])
@pytest.mark.parametrize("delta", [-5.000001, 5.000001])
def test_sealed_drift_branch_is_independent(document_result, task, delta):
    document_result["task"] = task
    document_result["m1_result"]["a_vs_sealed"]["delta_ms"] = delta
    first = report_docs.render_document(document_result).split("\n\n")[1]
    assert "봉인 환경과 표류가 있다" in first
    assert "봉인 측정과 직접 비교 불가" not in first
    assert "자 표류 큼" not in first


@pytest.mark.parametrize("delta", [-5.000001, -5, 5, 5.000001])
def test_m1_own_drift_and_kernels_are_reported(document_result, delta):
    document_result["task"] = "M1"
    document_result["m1_result"] = None
    document_result["statistics"]["a_vs_sealed"] = {
        "current_mean_ms": 83.1 + delta, "sealed_mean_ms": 83.1, "delta_ms": delta,
        "kernel": "saved-measurement-kernel", "sealed_kernel": "saved-sealed-kernel",
        "source": "saved-sealed-reference", "exploratory": True}
    text = report_docs.render_document(document_result)
    assert ("봉인 환경과 표류가 있다" in text.split("\n\n")[1]) is (abs(delta) > 5)
    assert "| saved-measurement-kernel | saved-sealed-kernel | saved-sealed-reference |" in text
    assert "a·e의 동결 서버에는 -conn-log가 없어 최종 stats.conns를 사용했다" in text
    assert "사전 설명의 N+5~N+8 B 범위를 넘어선 관측도 아래 표에 그대로 남긴다" in text
    assert "같은 환경" not in text
    assert text == report_docs.render_document(json.loads(json.dumps(document_result, sort_keys=True)))


def test_m1_frozen_certificate_observations_do_not_impute_missing_sizes(document_result):
    document_result["task"] = "M1"
    document_result["server_summary"] = [
        {"cell": "bigcert_l2", "arm": "a", "certificate_observation": {
            "source": "server.stderr", "units_total": 30, "units_observed": 29,
            "der_bytes_values": [16005, 16007, 16009], "status": "미확인"}},
        {"cell": "bigcert_l2", "arm": "e", "certificate_observation": {
            "source": "server.stderr", "units_total": 30, "units_observed": 0,
            "der_bytes_values": [], "status": "미확인"}}]
    text = report_docs.render_document(document_result)
    assert "| bigcert_l2 | a | 16005, 16007, 16009 | 29 | 30 | server.stderr | 미확인 |" in text
    assert "| bigcert_l2 | e | 미확인 | 0 | 30 | server.stderr | 미확인 |" in text


@pytest.mark.parametrize("task", ["X1", "X6"])
def test_aa_drift_branch_and_common_server(document_result, task):
    document_result["task"] = task
    document_result["m1_result"]["contrasts"]["c_d"]["ci95"] = [-6, 4]
    first = report_docs.render_document(document_result).split("\n\n")[1]
    assert "자 표류 큼" in first
    assert "봉인 측정과 직접 비교 불가" not in first
    assert "봉인 환경과 표류가 있다" not in first
    assert "모든 팔을 같은 gen33 서버에 붙였고 봉인 측정의 세대별 서버와 다르다" in first


def test_exact_drift_boundaries_do_not_trigger(document_result):
    text = report_docs.render_document(document_result)
    assert "봉인 환경과 표류가 있다" not in text
    assert "봉인 측정과 직접 비교 불가" not in text
    assert "자 표류 큼" not in text
    assert "같은 환경" not in text


def test_idle_missing_and_parse_counters(document_result):
    text = report_docs.render_document(document_result)
    assert "실제 mean_idle_ms는 null·미확인" in text
    assert "| S_bigcert | g2auto | 0 | 7 | true |" in text
    assert "서버 계수 bytes_in" in text
    assert "| S_bigcert | v33none | 전체 | 0.98 | 미확인 | 미확인 | 50 | false |" in text
    document_result["server_summary"][0]["fec_parse_fail"] = None
    assert "| S_bigcert | g2auto | 미확인 | 7 | true |" in report_docs.render_document(document_result)


def test_limit_removal_requires_actual_rows(document_result):
    document_result["measured_items"] = [{"id": "X4", "n_rows": 30, "execution_status": "판정 통과"},
                                          {"id": "X2", "status": "planned"},
                                          {"id": "X3", "n_rows": 0, "execution_status": "판정 통과"},
                                          {"id": "X5", "n_rows": 20, "execution_status": "skipped"}]
    text = report_docs.render_document(document_result)
    assert "토큰·resumption 기준선(X4)" not in text
    for item in ("업링크 오입력(X2)", "A_pre와 PTO 배수 탐침(X3)", "s2c 손실(X5)"):
        assert item in text


def test_document_detects_numeric_mutation(document_result, tmp_path):
    path = tmp_path / "result.md"
    path.write_text(report_docs.render_document(document_result).replace("81.25", "81.26"), encoding="utf-8")
    with pytest.raises(ValueError, match="결과 JSON"):
        report_docs.check_document(path, result=document_result)


@pytest.fixture
def errata_fixture(tmp_path):
    source = tmp_path / "g3/v33/results/result.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({"contrasts": {"c1_none": {"mean": 1.23456, "ci95": [-0.5, 2.96912]}},
                                  "rate": 0.123456, "unrelated": 999, "same": 1.23456}), encoding="utf-8")
    path = tmp_path / "errata.md"
    return tmp_path, path, source


def _errata(path, new, evidence, prefix="", suffix=""):
    encoded = json.dumps(new, ensure_ascii=False).replace("|", "\\|")
    path.write_text("# 정오표\n\n" + prefix + "## 측정 결과\n\n"
                    "| id | old | new | 근거 키 | selected |\n|---|---|---|---|---|\n"
                    f"| RT-99 | `\"9999 ms\"` | `{encoded}` | {evidence} | measured |\n\n" + suffix,
                    encoding="utf-8")


def test_check_doc_uses_only_selected_section_new(errata_fixture):
    root, path, source = errata_fixture
    _errata(path, '평균 1.235 ms와 "구간" | 95% 구간 [-0.5, 2.969] ms.',
            "g3/v33/results/result.json#contrasts.c1_none.mean; "
            "g3/v33/results/result.json#/contrasts/c1_none/ci95",
            prefix="## 다른 절\n\n| new | 근거 키 |\n|---|---|\n| 123 | g3/v33/results/missing.json#x |\n\n",
            suffix="## 나머지\n\n99.99 ms\n")
    assert report_docs.check_document(path, section="측정 결과", repo_root=root)["checked_rows"] == 1


def test_check_doc_percent_scaling_and_identifiers(errata_fixture):
    root, path, source = errata_fixture
    _errata(path, "v3.3.1-dev의 X9, C1 비율은 12.346%다.", "g3/v33/results/result.json#rate")
    assert report_docs.check_document(path, section="측정 결과", repo_root=root)["status"] == "pass"


def test_check_doc_other_key_same_number_cannot_pass(errata_fixture):
    root, path, source = errata_fixture
    data = json.loads(source.read_text(encoding="utf-8"))
    data["contrasts"]["c1_none"]["mean"] = 5.0
    source.write_text(json.dumps(data), encoding="utf-8")
    _errata(path, "평균 1.235 ms", "g3/v33/results/result.json#contrasts.c1_none.mean")
    with pytest.raises(ValueError, match="지정한 결과 키와 다르다"):
        report_docs.check_document(path, section="측정 결과", repo_root=root)


@pytest.mark.parametrize("key", ["missing", "contrasts.c1_none.missing"])
def test_check_doc_missing_key_fails(errata_fixture, key):
    root, path, source = errata_fixture
    _errata(path, "평균 1.235 ms", "g3/v33/results/result.json#" + key)
    with pytest.raises(ValueError, match="근거 키가 없다"):
        report_docs.check_document(path, section="측정 결과", repo_root=root)


def test_check_doc_rejects_broad_object_evidence(errata_fixture):
    root, path, source = errata_fixture
    _errata(path, "평균 1.235 ms", "g3/v33/results/result.json#contrasts")
    with pytest.raises(ValueError, match="수치 또는 수치 배열"):
        report_docs.check_document(path, section="측정 결과", repo_root=root)


def test_check_doc_rejects_missing_section_and_zero_targets(errata_fixture):
    root, path, source = errata_fixture
    path.write_text("# 정오표\n\n## 측정 결과\n\n아직 미확인이다.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="대조할 측정 행이 없다"):
        report_docs.check_document(path, section="측정 결과", repo_root=root)
    with pytest.raises(ValueError, match="측정 절이 없다"):
        report_docs.check_document(path, section="없는 절", repo_root=root)


def test_generated_document_auto_loads_exact_result(document_result, tmp_path):
    document_result["result_source"] = "g3/v33/results/generated.json"
    source = tmp_path / document_result["result_source"]
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps(document_result, ensure_ascii=False), encoding="utf-8")
    path = tmp_path / "result.md"
    path.write_text(report_docs.render_document(document_result), encoding="utf-8")
    assert report_docs.check_document(path, repo_root=tmp_path)["status"] == "pass"
    changed = deepcopy(document_result)
    changed["statistics"]["cells"][0]["arms"][0]["primary"]["hct"]["mean"] += 1
    source.write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="결과 JSON"):
        report_docs.check_document(path, repo_root=tmp_path)


def test_aa_ruler_and_reweighted_summary_are_not_dropped(document_result):
    cell = document_result["statistics"]["cells"][0]
    cell["contrasts"][0]["aa"] = {"applies": True, "ruler_ms": 3.25,
                                      "note": "자 표류 큼", "inference_status": "판정불능"}
    cell["arms"][0]["reweighted_1_1"] = {
        "hct": {"mean": 82.75, "ci95": [81.25, 84.25], "n": 4, "df": 3},
        "inference_unit": "trajectory", "losses": [[2, 0], [15, 0]],
        "weights": [0.5, 0.5], "aa": "A/A 없음"}
    text = report_docs.render_document(document_result)
    assert "| A/A 적용 | 3.25 | 자 표류 큼 | 판정불능 |" in text
    assert "| S_bigcert | v33none | 82.75 | [81.25, 84.25] | 4 | 3 | A/A 없음 |" in text


def test_x9_pto_counts_missing_and_percentage_points(document_result):
    document_result["task"] = "X9"
    cell = document_result["statistics"]["cells"][0]
    cell["cell"] = "both"
    cell["arms"][0]["arm"] = "mlkem_off"
    cell["arms"][0]["primary"]["pto"] = {
        "primary": {"events": 123, "n_total": 1000, "n_valid": 999, "missing": 1,
                    "scope_invalid": 1, "rate": 123 / 999},
        "auxiliary": {"events": 124, "n_total": 1000, "n_valid": 1000, "missing": 0,
                      "rate": 0.124},
        "definition_mismatch": 3, "definition_comparable": 999}
    cell["pto_contrast"] = {
        "primary": {"mean": 0.01234, "ci95": [-0.001, 0.02568], "n_blocks": 10,
                    "missing_blocks": 0, "df": 9},
        "auxiliary": {"mean": None, "ci95": None, "n_blocks": 10,
                      "missing_blocks": 1, "df": None}}
    text = report_docs.render_document(document_result)
    assert "| both | mlkem_off | 주 정의 | 123 | 1000 | 999 | 1 | 1 | 12.312312 | 3 | 999 |" in text
    assert "| both | 주 정의 | 1.234 | [-0.1, 2.568] | 10 | 0 | 9 |" in text
    assert "| both | 보조 정의 | 미확인 | 미확인 | 10 | 1 | 미확인 |" in text
    assert "계획용 검정력 근사는 실제 검정력이 아니며" in text
    assert "메모리 qlog에 기록된 timer 만료 횟수의 하한" in text
    assert "tracer가 비활성이거나 관측 범위가 맞지 않으면 누락" in text


def test_feedback_class_exclusion_and_idle_subsets(document_result):
    group = document_result["observations"][0]
    group["arm"] = "v33c1"
    group["c1_path_excluded"] = True
    group["feedback_received_rate_by_class"] = {
        "one_rtt": {"n": 30, "received": 27, "missing": 0, "rate": 0.9, "status": "fail"},
        "not_one_rtt": {"n": 10, "received": 10, "missing": 0, "rate": 1, "status": "표본 부족"}}
    group["by_one_rtt"] = {"one_rtt": {"mean_idle_ms": None, "idle_status": "미확인"}}
    group["by_loss"] = [{"loss_c2s_pct": 2, "loss_s2c_pct": 0,
                          "mean_idle_ms": None, "idle_status": "미확인"}]
    text = report_docs.render_document(document_result)
    assert "| S_bigcert | v33c1 | one_rtt | 30 | 27 | 0 | 0.9 | fail | true |" in text
    assert "| S_bigcert | v33c1 | not_one_rtt | 10 | 10 | 0 | 1 | 표본 부족 | true |" in text
    assert "| S_bigcert | v33c1 | c2s=2% s2c=0% | 미확인 | 미확인 | 미확인 |" in text


def test_m0_class_rows_keep_order_after_sorted_json_roundtrip(document_result, tmp_path):
    document_result["task"] = "M0"
    document_result["result_source"] = "g3/v33/results/roundtrip.json"
    group = document_result["observations"][0]
    group["arm"] = "v33c1"
    group["by_one_rtt"] = {
        "one_rtt": {"valid_rtt": {"valid_rtt_rate": 1}, "mean_idle_ms": None,
                    "idle_status": "미확인", "mean_wait_plus_gap_ms": 50, "c1_path_excluded": False},
        "not_one_rtt": {"valid_rtt": {"valid_rtt_rate": 0.5}, "mean_idle_ms": None,
                        "idle_status": "미확인", "mean_wait_plus_gap_ms": 200, "c1_path_excluded": False}}
    group["feedback_received_rate_by_class"] = {
        "one_rtt": {"n": 12, "received": 12, "missing": 0, "rate": 1, "status": "표본 부족"},
        "not_one_rtt": {"n": 8, "received": 8, "missing": 0, "rate": 1, "status": "표본 부족"}}
    before = report_docs.render_document(document_result).encode("utf-8")
    source = tmp_path / document_result["result_source"]
    source.parent.mkdir(parents=True)
    source.write_bytes(devreport.json_bytes(document_result))
    loaded = devreport.read_json(source)
    assert list(loaded["observations"][0]["by_one_rtt"]) == ["not_one_rtt", "one_rtt"]
    assert list(loaded["observations"][0]["feedback_received_rate_by_class"]) == ["not_one_rtt", "one_rtt"]
    assert report_docs.render_document(loaded).encode("utf-8") == before
    text = before.decode("utf-8")
    assert text.index("| v33c1 | one_rtt | 1 | 미확인 |") < text.index("| v33c1 | not_one_rtt | 0.5 | 미확인 |")
    assert text.index("| v33c1 | one_rtt | 12 | 12 |") < text.index("| v33c1 | not_one_rtt | 8 | 8 |")
    path = tmp_path / "M0_result.md"
    path.write_bytes(before)
    assert report_docs.check_document(path, repo_root=tmp_path)["status"] == "pass"


def test_jsonpath_evidence_and_array_index(errata_fixture):
    root, path, source = errata_fixture
    _errata(path, "평균 1.235 ms와 하한 -0.5 ms",
            "g3/v33/results/result.json#$.contrasts.c1_none.mean; "
            "g3/v33/results/result.json#contrasts.c1_none.ci95[0]")
    assert report_docs.check_document(path, section="측정 결과", repo_root=root)["status"] == "pass"


@pytest.mark.parametrize("task", ["X1", "X6"])
def test_rate_and_cost_contrast_units(document_result, task):
    document_result["task"] = task
    contrast = document_result["statistics"]["cells"][0]["contrasts"][0]
    contrast["one_rtt_difference"] = {"mean": 0.025, "ci95": [-0.01, 0.06]}
    contrast["server_bytes_in_per_conn_difference"] = {"mean": 123.5, "ci95": [122.25, 124.75]}
    text = report_docs.render_document(document_result)
    assert "| 0.025 | [-0.01, 0.06] | 123.5 | [122.25, 124.75] |" in text
    assert "95% 구간(비율)" in text
    assert "95% 구간(B/연결)" in text


def test_x1_first_flight_diagnostic_and_missing_rows(document_result):
    document_result["task"] = "X1"
    contrast = document_result["statistics"]["cells"][0]["contrasts"][0]
    contrast["first_flight_difference"] = {"original_bytes": 0, "extra_bytes": 12,
        "total_bytes": 12, "missing_rows": {"x": 1, "y": 0}, "unit": "B", "scope": "primary"}
    text = report_docs.render_document(document_result)
    assert "| primary | 0 | 12 | 12 | 1 | 0 |" in text
    assert "클라이언트 행의 진단" in text
    assert "서버 수신량 비용과 구분" in text


def test_m0_omits_comparison_additions(document_result):
    document_result["task"] = "M0"
    before = report_docs.render_document(document_result)
    contrast = document_result["statistics"]["cells"][0]["contrasts"][0]
    contrast["one_rtt_difference"] = {"mean": 0.025, "ci95": [-0.01, 0.06]}
    contrast["server_bytes_in_per_conn_difference"] = {"mean": 123.5, "ci95": [122.25, 124.75]}
    contrast["first_flight_difference"] = {"original_bytes": 0, "extra_bytes": 12,
        "total_bytes": 12, "missing_rows": {"x": 1, "y": 0}, "unit": "B", "scope": "primary"}
    assert report_docs.render_document(document_result) == before


def test_measured_plan_keeps_measurement_time_bytes(document_result):
    group = document_result["statistics"]["cells"][0]["contrasts"][0]
    group["aa"] = {"applies": True, "ruler_ms": 1.25, "note": None, "inference_status": "판정 가능"}
    document_result["plan_sha256"] = "74f58fbb6b0db5c30ef9abf0698ae13dd6bede861bef3215646e5ca3232154b6"
    assert "| A/A 적용 | 1.25 | 미확인 |" in report_docs.render_document(document_result)
    document_result["plan_sha256"] = "0" * 64
    assert "| A/A 적용 | 1.25 | 해당 없음 |" in report_docs.render_document(document_result)
    group["aa"] = {"applies": False, "ruler_ms": None, "note": "A/A 없음"}
    assert "| A/A 없음 | 해당 없음 | A/A 없음 |" in report_docs.render_document(document_result)


def test_check_doc_reads_selected_measured_column(errata_fixture):
    root, path, source = errata_fixture
    path.write_text("# 정오표\n\n## 측정 결과\n\n"
                    "| id | old | new | 측정 뒤 문구 | 근거 키 | selected |\n|---|---|---|---|---|---|\n"
                    "| RT-99 | `\"x\"` | `\"측정 대기\"` | `\"평균 1.235 ms\"` | "
                    "g3/v33/results/result.json#contrasts.c1_none.mean | 측정 뒤 문구 |\n\n", encoding="utf-8")
    assert report_docs.check_document(path, section="측정 결과", repo_root=root)["checked_rows"] == 1
    path.write_text(path.read_text(encoding="utf-8").replace("1.235", "9.235"), encoding="utf-8")
    with pytest.raises(ValueError):
        report_docs.check_document(path, section="측정 결과", repo_root=root)
