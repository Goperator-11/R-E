from copy import deepcopy
import json
from pathlib import Path

import pytest

from experiments.v33 import devbed
from experiments.v33.lib import arms, observations, report

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "g3/v33/plans/final_bundle_v2.json"


@pytest.fixture
def loaded():
    return devbed.read_plan(PLAN)


def test_plan_is_marked_exploratory_and_keeps_v1(loaded):
    plan, _ = loaded
    assert plan["exploratory"] is True and plan["confirmatory"] is False
    assert plan["precommit"]["plan_paths"][0].endswith("final_bundle_v2.json")
    assert (ROOT / "g3/v33/plans/final_bundle_v1.json").exists()


def test_dry_run_counts(loaded):
    plan, digest = loaded
    summary = devbed.planned_summary(plan, digest)
    assert [row["task"] for row in summary["tasks"]] == ["M0", "X6"]
    assert summary["connections"] == 22820
    x6 = arms.iter_units(plan, "X6")
    assert len(x6) == 810
    assert sum(unit["connections"] for unit in x6) == 22500
    assert x6[0]["cell"] == "S_rtt200"


def test_x6_needs_no_m1(loaded):
    plan, digest = loaded
    assert devbed.m1_dependency(plan, "X6", None, digest) is None
    assert report.aa_ruler(None, task="X6", profile="bigcert", loss_pct=2,
                           statistics=plan["statistics"])["applies"] is False


def test_conditions_match_v1(loaded):
    plan, _ = loaded
    v1, _ = devbed.read_plan(ROOT / "g3/v33/plans/final_bundle_v1.json")
    old = {(unit["cell"], unit["phase"], unit["block"], unit["arm"]): unit for unit in arms.iter_units(plan=v1, task_ids="X6")}
    mapping = {"v33s_none": "v33none", "v33s_c1": "v33c1", "v33pre_c1": "v33c1"}
    for unit in arms.iter_units(plan, "X6"):
        twin = old[(unit["cell"], unit["phase"], unit["block"], mapping[unit["arm"]])]
        for field in ("profile", "profile_id", "connections", "burnin_connections", "connection_offset",
                      "loss_c2s_pct", "loss_s2c_pct"):
            assert unit[field] == twin[field]
        paths = {name: Path("/x") for name in plan["binaries"]}
        new_client = arms.client_command(plan, unit, binary_paths=paths, address="A", cache="C")
        v1_paths = {name: Path("/x") for name in v1["binaries"]}
        old_client = arms.client_command(v1, twin, binary_paths=v1_paths, address="A", cache="C")
        assert new_client == old_client


def test_old_c1_arm_is_gen33_family(loaded):
    plan, _ = loaded
    assert arms.client_family(plan, plan["arms"]["v33pre_c1"]) == "gen33"
    assert arms.client_family(plan, plan["arms"]["v33s_none"]) == "gen33"
    v1, _ = devbed.read_plan(ROOT / "g3/v33/plans/final_bundle_v1.json")
    assert arms.client_family(v1, v1["arms"]["v31auto"]) == "g3c"
    assert arms.client_family(v1, v1["arms"]["g2auto"]) == "g2"


def _stats(path, connection_count, *, fb_sent, version):
    return {"bytes_in": 1, "parities": 1, "recovered": 0, "credit_parities": 0, "fb_sent": fb_sent,
            "tls_accepted": connection_count, "feedback_version": version, "fec_parse_fail": 0,
            "conn_acct_evicted_lru": 0,
            "conn_log": {"lines": connection_count, "errors": 0, "pending": 0, "path": str(path)}}


def _payload(tmp_path, unit, *, fb_sent, version):
    path = tmp_path / "conns.jsonl"
    rows = []
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for index in range(unit["rows_expected"]):
            stream.write(json.dumps({"key": f"k{index}", "initial_dcid": "d", "client_scid": f"s{index}", "rx_bytes": 1,
                                     "rx_orig_bytes": 1, "rx_parity_bytes": 0, "stack_bytes": 1, "beff_stack": 1,
                                     "beff_phys": 1, "beff_orig": 1, "beff_parity": 0, "reason": "shutdown",
                                     "logged_ns": 1}) + "\n")
            rows.append({"i": index, "ok": True, "ms": 1.0, "client_scid": f"s{index}"})
    return {"rows": rows, "server": {"returncode": 0, "forced_kill": False, "exited_before_stop": False,
                                     "conn_log_path": str(path),
                                     "stats": _stats(path, unit["rows_expected"], fb_sent=fb_sent, version=version)}}


def test_old_c1_block_is_not_rejected_for_feedback(loaded, tmp_path):
    plan, _ = loaded
    unit = next(item for item in arms.iter_units(plan, "M0") if item["arm"] == "v33pre_c1")
    result = report.validate_server_unit(plan, unit, _payload(tmp_path, unit, fb_sent=20, version=2))
    assert "frozen_feedback" not in result["checks"]
    assert result["checks"]["c1_feedback_version"] == "pass"
    assert result["reject_block"] is False
    assert result["scid_matching"]["status"] == "확인"


def test_new_none_arm_still_rejects_feedback(loaded, tmp_path):
    plan, _ = loaded
    unit = next(item for item in arms.iter_units(plan, "M0") if item["arm"] == "v33s_none")
    result = report.validate_server_unit(plan, unit, _payload(tmp_path, unit, fb_sent=1, version=2))
    assert result["checks"]["no_feedback"] == "fail"
    assert result["reject_block"] is True


def test_v1_frozen_arm_rule_is_unchanged(tmp_path):
    v1, _ = devbed.read_plan(ROOT / "g3/v33/plans/final_bundle_v1.json")
    unit = next(item for item in arms.iter_units(v1, "M0") if item["arm"] == "g2auto")
    result = report.validate_server_unit(v1, unit, _payload(tmp_path, unit, fb_sent=1, version=2))
    assert result["checks"]["frozen_feedback"] == "fail"
    assert result["scid_matching"]["status"] == "동결 클라이언트 필드 미제공"


def test_old_c1_rows_get_explicit_flight_check(loaded):
    plan, _ = loaded
    unit = next(item for item in arms.iter_units(plan, "M0") if item["arm"] == "v33pre_c1")
    rows = [{"i": index, "ok": True, "ms": 1.0, "flight_expectation": {"source": "explicit", "k": 2},
             "feedback_wait_limit_ms": unit["profile"]["feedback_wait_ms"], "feedback_wait_received": True,
             "feedback_wait_ns": 1000, "path_rtt_valid": False} for index in range(unit["rows_expected"])]
    result = observations.unit_observations(plan, unit, {"rows": rows})
    assert result["checks"]["explicit_flight"] == "pass"


def test_document_names_do_not_touch_x6_document(loaded):
    plan, _ = loaded
    assert plan["result_contract"]["document_names"] == {"M0": "M0S_result.md", "X6": "X6S_result.md"}
