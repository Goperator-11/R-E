from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import re

import pytest

from experiments.v33 import devbed
from experiments.v33.lib import arms, report
from test_v33_devreport_checks import smoke_payload, summarize, target

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "g3/v33/plans/final_bundle_v3_x2.json"
DOCUMENT = ROOT / "g3/v33/plans/final_bundle_v3_x2.md"
V1 = ROOT / "g3/v33/plans/final_bundle_v1.json"
V2 = ROOT / "g3/v33/plans/final_bundle_v2.json"
DIAGNOSTICS = ROOT / "g3/v33/results/v33_dev_X6_final_x6_iter035_20261107.diagnostics.json"
TRUE_VALUES = {"bigcert": 2, "hc6000": 10, "rtt200": 2}
INPUTS = {"bigcert": [0, 1, 4, 10], "hc6000": [0, 5, 20, 10], "rtt200": [0, 1, 4, 10]}
CELLS = ["bigcert_l2", "bigcert_l15", "hc6000_l1", "hc6000_l8", "rtt200_l2", "rtt200_l15"]


@pytest.fixture(scope="module")
def loaded():
    return devbed.read_plan(PLAN)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _input(unit):
    return TRUE_VALUES[unit["profile_id"]] if unit["arm"] == "x2_true" else int(unit["arm"].removeprefix("x2_u"))


def test_plan_is_exploratory_development_with_own_documents(loaded):
    plan, _ = loaded
    assert plan["schema"] == "padfec3.final_bundle.v1" and plan["plan_id"] == "final_bundle_v3_x2"
    assert plan["label"] == "development" and plan["confirmatory"] is False and plan["exploratory"] is True
    assert plan["precommit"]["plan_paths"] == ["g3/v33/plans/final_bundle_v3_x2.json",
                                               "g3/v33/plans/final_bundle_v3_x2.md"]
    assert plan["optional"] == []
    assert plan["ordering"]["required_task_order"] == ["M0", "X2"]
    assert plan["result_contract"]["document_names"] == {"M0": "M0X2_result.md", "X2": "X2_result.md"}


def test_binary_is_the_frozen_gen33_of_v2(loaded):
    plan, _ = loaded
    v2, _ = devbed.read_plan(V2)
    assert set(plan["binaries"]) == {"gen33"}
    for key in ("path", "sha256", "srcsha", "source_commit"):
        assert plan["binaries"]["gen33"][key] == v2["binaries"]["gen33"][key]
    devbed.require_binary_identifiers(plan)


def test_after_results_are_filled_and_match_committed_bytes(loaded):
    plan, _ = loaded
    after = plan["after_results"]
    assert [item["path"] for item in after["base_plans"]] == ["g3/v33/plans/final_bundle_v1.json",
                                                              "g3/v33/plans/final_bundle_v2.json"]
    for item in after["base_plans"]:
        assert re.fullmatch("[0-9a-f]{40}", item["commit"])
        assert _sha((ROOT / item["path"]).read_bytes()) == item["sha256"]
        assert _sha(devbed.git(ROOT, "show", f"{item['commit']}:{item['path']}")) == item["sha256"]
    assert [item["id"] for item in after["seen_results"]] == ["X6", "M0S", "X6S"]
    for item in after["seen_results"]:
        assert "X6S_PENDING" not in (item["path"], item["sha256"])
        assert _sha((ROOT / item["path"]).read_bytes()) == item["sha256"]
        devbed.committed_file(ROOT, ROOT / item["path"])
    x6s = json.loads((ROOT / after["seen_results"][2]["path"]).read_text(encoding="utf-8"))
    assert x6s["task"] == "X6" and x6s["plan_id"] == "final_bundle_v2"
    assert x6s["plan_sha256"] == after["base_plans"][1]["sha256"]
    text = DOCUMENT.read_text(encoding="utf-8")
    assert "X6S_PENDING" not in text and after["seen_results"][2]["sha256"] in text


def test_dry_run_counts_and_times(loaded):
    plan, digest = loaded
    summary = devbed.planned_summary(plan, digest)
    assert [row["task"] for row in summary["tasks"]] == ["M0", "X2"]
    assert summary["connections"] == plan["required_connections_total"] == 9100
    assert summary["expected_minutes"] == plan["expected_required_minutes"] == 38
    assert [cell["id"] for cell in plan["tasks"]["X2"]["cells"]] == CELLS
    assert len(arms.iter_units(plan, "X2")) == 300
    m0 = arms.iter_units(plan, "M0")
    assert len(m0) == 5 and {unit["cell"] for unit in m0} == {"hc6000_l8"}
    assert sum(unit["connections"] for unit in m0) == 100
    assert {unit["loss_c2s_pct"] for unit in m0} == {8}


def test_each_arm_has_100_burnin_then_200_analysis_connections(loaded):
    plan, _ = loaded
    units = arms.iter_units(plan, "X2")
    groups = defaultdict(list)
    for unit in units:
        groups[(unit["cell"], unit["arm"])].append(unit)
    assert len(groups) == 30
    for subset in groups.values():
        subset.sort(key=lambda unit: unit["block"])
        assert [unit["connections"] for unit in subset] == [30] * 10
        assert [unit["burnin_connections"] for unit in subset] == [30, 30, 30, 10, 0, 0, 0, 0, 0, 0]
        assert sum(unit["measured_connections"] for unit in subset) == 200
        assert len({unit["cache_key"] for unit in subset}) == 1
    assert len({unit["cache_key"] for unit in units}) == 30
    for cell in CELLS:
        orders = {tuple(unit["arm"] for unit in units if unit["cell"] == cell and unit["block"] == block)
                  for block in range(10)}
        assert len(orders) == 10


def test_arms_differ_from_v1_none_only_in_policy_input(loaded):
    plan, _ = loaded
    v1, _ = devbed.read_plan(V1)
    assert plan["common"]["client_common_flags"] == v1["common"]["client_common_flags"]
    assert plan["common"]["server_flags"] == v1["common"]["server_flags"]
    paths = {"gen33": Path("/x")}
    v1_paths = {name: Path("/x") for name in v1["binaries"]}
    for unit in arms.iter_units(plan, ["M0", "X2"]):
        arm = plan["arms"][unit["arm"]]
        assert arm["client_flags"] == v1["arms"]["v33none"]["client_flags"]
        assert arm["binary"] == arm["server"] == "gen33" and arm["kind"] == "auto3"
        assert arm["none_path_check"] is True and not arm.get("server_feedback")
        true_value = TRUE_VALUES[unit["profile_id"]]
        assert unit["profile"]["policy_uplink_mbps"] == _input(unit)
        assert unit["profile"]["netem_uplink_mbps"] == true_value
        for key in ("certsize", "rtt_ms", "expect_k", "group", "gap_ms"):
            assert unit["profile"][key] == v1["profiles"][unit["profile_id"]][key]
        command = arms.client_command(plan, unit, binary_paths=paths, address="A", cache="C")
        twin = dict(unit, arm="v33none", profile=dict(unit["profile"], policy_uplink_mbps=true_value))
        old = arms.client_command(v1, twin, binary_paths=v1_paths, address="A", cache="C")
        index = command.index("-uplink-mbps") + 1
        assert command[index] == format(_input(unit), "g")
        assert command[:index] + command[index + 1:] == old[:index] + old[index + 1:]
        assert "-ips" not in command
        server = arms.server_command(plan, unit, binary_paths=paths, address="A", cert_file="P", stats="S", conn_log="L")
        assert "-feedback" not in server and server[server.index("-certsize") + 1] == str(unit["profile"]["certsize"])


def test_contrasts_are_input_minus_true_with_hc6000_aa(loaded):
    plan, _ = loaded
    contrasts = plan["tasks"]["X2"]["contrasts"]
    assert len(contrasts) == 24
    for cell in plan["tasks"]["X2"]["cells"]:
        true_value = TRUE_VALUES[cell["profile"]]
        assert cell["arms"] == ["x2_true"] + [f"x2_u{value}" for value in INPUTS[cell["profile"]]]
        assert cell["trajectories"] == 1 and cell["burnin_per_arm_trajectory"] == 100
        rows = [item for item in contrasts if item["cell"] == cell["id"]]
        assert [item["x"] for item in rows] == cell["arms"][1:]
        assert [item["input_mbps"] for item in rows] == [0, true_value / 2, 2 * true_value, 10]
        assert [item["card_input"] for item in rows] == ["0", "u/2", "2u", "10"]
        for item in rows:
            assert item["y"] == "x2_true" and item["true_mbps"] == true_value
            assert item["id"] == item["x"] + "_minus_x2_true"
            assert item["kind"] == ("A/A" if item["input_mbps"] == true_value else "오입력")
    assert [(item["cell"], item["x"]) for item in contrasts if item["kind"] == "A/A"] == [
        ("hc6000_l1", "x2_u10"), ("hc6000_l8", "x2_u10")]


def test_no_unknown_arm_and_netem_rate_is_never_an_arm_value(loaded):
    plan, _ = loaded
    assert set(plan["arms"]) == {"x2_true", "x2_u0", "x2_u1", "x2_u4", "x2_u5", "x2_u10", "x2_u20"}
    assert "policy_uplink_mbps" not in plan["arms"]["x2_true"]
    assert all("netem_uplink_mbps" not in arm for arm in plan["arms"].values())
    assert plan["tasks"]["X2"]["netem_rate_unchanged"] is True
    assert plan["tasks"]["X2"]["independent_trajectory_claim"] is False


def test_tasks_need_no_m1_and_no_aa_ruler(loaded):
    plan, digest = loaded
    for task in ("M0", "X2"):
        assert devbed.m1_dependency(plan, task, None, digest) is None
    for cell in plan["tasks"]["X2"]["cells"]:
        assert report.aa_ruler(None, task="X2", profile=cell["profile"], loss_pct=cell["phases"][0]["loss_c2s_pct"],
                               statistics=plan["statistics"])["applies"] is False


def test_x2_is_selectable_here_but_v1_optional_is_still_refused(loaded):
    plan, _ = loaded
    assert arms.selected_tasks(plan, "X2") == ["X2"]
    v1, _ = devbed.read_plan(V1)
    with pytest.raises(ValueError, match="보충 계획"):
        arms.selected_tasks(v1, "X2")


def test_wall_clock_estimate_comes_from_x6_unit_times(loaded):
    plan, _ = loaded
    task = plan["tasks"]["X2"]
    estimate = task["wall_clock_estimate"]
    timing = json.loads(DIAGNOSTICS.read_text(encoding="utf-8"))["timing"]
    seconds = {(row["cell"], row["arm"]): row["sum_minutes"] * 60 / row["units"] for row in timing["arms"]}
    gap = estimate["between_units_seconds_median"]
    assert gap == timing["between_units_seconds"]["median"]
    bounds = estimate["unit_seconds"]
    for profile, cell in (("bigcert", "S_bigcert"), ("rtt200", "S_rtt200")):
        assert bounds[profile]["low"] == pytest.approx(seconds[(cell, "v33none")], abs=1e-4)
        assert bounds[profile]["high"] == pytest.approx(seconds[(cell, "g2auto")], abs=1e-4)
    assert estimate["units_per_cell"] == 5 * 10

    def pair(value):
        return 2 * estimate["units_per_cell"] * (value + gap) / 60
    low = pair(bounds["bigcert"]["low"]) + pair(bounds["hc6000"]["plan"]) + pair(bounds["rtt200"]["low"])
    high = pair(bounds["bigcert"]["high"]) + pair(bounds["hc6000"]["plan"]) + pair(bounds["rtt200"]["high"])
    assert estimate["measure_minutes"] == pytest.approx([low, high], abs=0.01)
    assert task["expected_minutes"] == math.ceil(estimate["measure_minutes"][1])
    assert estimate["total_minutes"] == pytest.approx(
        [low + estimate["report_and_inspect_minutes"], high + estimate["report_and_inspect_minutes"]], abs=0.02)


def test_m0_smoke_checks_policy_input_and_none_path(loaded):
    plan, _ = loaded
    units = arms.iter_units(plan, ["M0"])
    payloads, events = zip(*(smoke_payload(plan, unit) for unit in units))
    fixture = (plan, units, list(payloads), list(events))
    result = summarize(fixture)
    assert set(result["checks"].values()) == {"pass"}
    for name in ("none_path", "policy_uplink", "netem_config", "realized_loss", "server_uniform", "success_rate"):
        assert result["checks"][name] == "pass"
    checked = {item["arm"]: item["expected"] for item in result["details"]["policy_uplink"]}
    assert checked == {"x2_true": 10, "x2_u0": 0, "x2_u5": 5, "x2_u20": 20, "x2_u10": 10}
    target(fixture, "x2_u0", "hc6000_l8")["rows"][0]["policy_uplink_mbps"] = 10
    assert summarize(fixture)["checks"]["policy_uplink"] == "fail"
