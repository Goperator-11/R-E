from copy import deepcopy
import json
from pathlib import Path

from experiments.v33 import devbed, devreport
from experiments.v33.lib import arms, blocks, report
from test_v33_devreport_checks import smoke_payload, summarize, target, tc_output

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "g3/v33/plans/final_bundle_v2.json"
ADDRESS = "10.9.0.2:44433"


def _cache_bytes(seen):
    state = {"v": 11, "k_hist": [], "S_hist": [], "hct": {}, "hct_seq": {}, "seq": 0,
             "post": [[1 / 26] * 26 for _ in range(5)], "w": [0.2] * 5, "n_dec": 0, "n_reeval": 0,
             "g_resid": {}, "g_common": [], "g_alarm": {}, "stats": {}, "c1_seen": seen, "arrival_streak": 0}
    entry = {"state": state, "min_rtt_ms": 0, "rtt_observations": 0, "min_hct_ms": 0, "conns": 0}
    return json.dumps({"schema": "padfec3.cache3/11", "dests": {ADDRESS: entry}}).encode()


def _small_plan():
    plan, _ = devbed.read_plan(PLAN)
    for name, value in (("gen33", "a"), ("gen33pre", "b")):
        plan["binaries"][name]["sha256"] = value * 64
        plan["binaries"][name]["srcsha"] = value * 64
    cells = deepcopy(plan["tasks"]["X6"]["cells"][:2])
    for cell in cells:
        cell["trajectories"] = 2
        cell["burnin_per_arm_trajectory"] = 2
        for phase in cell["phases"]:
            phase.update(blocks=2, connections_per_arm=4, connections_per_arm_block=2)
    plan["tasks"]["X6"]["cells"] = cells
    plan["tasks"]["X6"]["connections_total"] = sum(3 * cell["trajectories"] * len(cell["phases"]) * 4 for cell in cells)
    plan["required_connections_total"] = plan["tasks"]["X6"]["connections_total"] + plan["tasks"]["M0"]["connections_total"]
    return plan


def _rows(plan, unit, digest):
    arm = plan["arms"][unit["arm"]]
    feedback = arm.get("server_feedback", False)
    rows, conns = [], []
    for index in range(unit["rows_expected"]):
        scid = f"{unit['cell']}{unit['trajectory']}{unit['phase']}{unit['block']}{index}{unit['arm']}"
        rows.append({"i": index, "ok": True, "ms": 200 + (5 if unit["arm"] == "v33pre_c1" else 0) + unit["trajectory"],
                     "client_scid": scid, "ips_eff": 1280, "m_used": 3, "first_flight_bytes": 2560,
                     "first_flight_datagrams": 2, "first_flight_parity_bytes": 5340, "first_flight_parity_dgrams": 4,
                     "first_flight_lead_dgrams": 2, "bytes_parity": 5340, "parity_sent": 4,
                     "flight_trace": {"omitted": 0, "records": [{"parity_sent": 4, "parity_bytes": 5340}]},
                     "path_rtt_valid": False, "feedback_wait_received": feedback,
                     "feedback_wait_limit_ms": unit["profile"]["feedback_wait_ms"] if feedback else None,
                     "feedback_wait_ns": 1000 if feedback else 0, "flight_expectation": {"source": "explicit", "k": 2},
                     "policy_path": "c1" if feedback else "none", "p_mean": 0.1, "action": [0, 2, 2], "s_hat": 10984,
                     "n_need": 9, "arrivals": {"src": "c1" if feedback else "none"}, "plan_sha256": digest,
                     "policy_uplink_mbps": unit["profile"]["policy_uplink_mbps"],
                     "binary_sha256": plan["binaries"][arm["binary"]]["sha256"],
                     "srcsha": plan["binaries"][arm["binary"]]["srcsha"],
                     "server_binary_sha256": plan["binaries"]["gen33"]["sha256"],
                     "server_srcsha": plan["binaries"]["gen33"]["srcsha"]})
        conns.append({"key": scid, "client_scid": scid, "initial_dcid": "ab", "reason": "shutdown", "logged_ns": index + 1,
                      "rx_bytes": 4096, "rx_orig_bytes": 2560, "rx_parity_bytes": 1536, "stack_bytes": 4096,
                      "beff_stack": 4096, "beff_phys": 4096, "beff_orig": 2560, "beff_parity": 1536,
                      "first_rx_ns": 1000 + index})
    return rows, conns


def _netem(unit):
    drops = int(unit["loss_c2s_pct"] * 10)
    before = {direction: tc_output(unit, direction) for direction in ("c2s", "s2c")}
    after = {"c2s": tc_output(unit, "c2s", 1000 - drops, drops), "s2c": tc_output(unit, "s2c", 1000, 0)}
    event = {"attempt": 0,
             "requested": {"one_way_ms": unit["profile"]["rtt_ms"] / 2,
                           "loss_c2s": unit["loss_c2s_pct"], "loss_s2c": unit["loss_s2c_pct"],
                           "burst_len": 1, "rate_up_mbit": unit["profile"]["netem_uplink_mbps"], "rate_down_mbit": 0},
             "qdisc": {direction: tc_output(unit, direction) for direction in ("c2s", "s2c")}}
    return before, after, event


def test_x6_report_runs_on_v2_plan_without_touching_x6_document(tmp_path, monkeypatch):
    plan = _small_plan()
    root = tmp_path / "root"
    raw = root / "v33_runs/fixture"
    raw.mkdir(parents=True)
    monkeypatch.chdir(raw)
    plan_path = root / "plan.json"
    plan_path.write_bytes(devreport.json_bytes(plan))
    digest = devreport.file_sha256(plan_path)
    provenance = {"plan_sha256": digest, "plan_commit": "a" * 40, "plan_doc_commit": "b" * 40,
                  "plan_doc_sha256": "b" * 64,
                  "plan_files": [{"committed_at": 1, "path": "plan.json", "sha256": digest, "commit": "a" * 40}]}
    meta = report.capture_metadata({"run_id": "fixture", "task": "X6", **provenance,
        "env": {"uname_r": "f", "python3_V": "f", "tc_V": "f", "ip_V": "f", "cpu_list": [0], "cpu_count": 1},
        "binary_sha256": {key: item["sha256"] for key, item in plan["binaries"].items()},
        "srcsha": {key: item["srcsha"] for key, item in plan["binaries"].items()}, "m1_dependency": None})
    manifest = {"run_id": "fixture", "task": "X6", "plan": plan, "provenance": provenance, "meta": meta,
                "fingerprint": "c" * 64, "m1_dependency": None}
    (raw / "manifest_fixture.json").write_bytes(devreport.json_bytes(manifest))
    units = arms.iter_units(plan, ["X6"])
    journal = blocks.UnitJournal(raw / "units_fixture.jsonl", "fixture", "c" * 64, units, metadata=meta)
    entries = []
    for unit in units:
        feedback = plan["arms"][unit["arm"]].get("server_feedback", False)
        directory = Path("units") / unit["key"] / "attempt_0"
        directory.mkdir(parents=True)
        rows, conns = _rows(plan, unit, digest)
        log = directory / "server.conns.jsonl"
        log.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in conns), encoding="utf-8", newline="\n")
        client = directory / "client.jsonl"
        client.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in rows), encoding="utf-8", newline="\n")
        stats = {"bytes_in": 8192, "parities": 8, "recovered": 1, "credit_parities": 8,
                 "fb_sent": 2 if feedback else 0, "tls_accepted": 2, "feedback_version": 2, "fec_parse_fail": 0,
                 "conn_acct_evicted_lru": 0, "conn_log": {"path": str(log), "lines": 2, "errors": 0, "pending": 0}}
        tc_before, tc_after, netem = _netem(unit)
        journal.record_event(unit["key"], "netem", netem)
        cache = tmp_path / "cache.json"
        cache.write_bytes(_cache_bytes(feedback))
        payload = {"rows": rows, "client_rc": 0, "cache_after": blocks.snapshot_cache(cache),
                   "tc_before": tc_before, "tc_after": tc_after,
                   "commands": {"client": ["qamp", "-addr", ADDRESS], "server": []}, "attempt": 0,
                   "started_at": "2026-11-08T10:00:00+00:00", "ended_at": "2026-11-08T10:00:01+00:00",
                   "server": {"returncode": 0, "forced_kill": False, "exited_before_stop": False, "stats": stats,
                              "conn_log_path": str(log),
                              "certificate": {"der_sha256": "d" * 64, "der_bytes": unit["profile"]["certsize"]}},
                   "raw_files": {"conn_log": str(log), "client_stdout": str(client)},
                   "raw_sha256": {path.as_posix(): devreport.file_sha256(path) for path in (log, client)}}
        collection = devbed.collection_validation(plan, unit, payload)
        assert collection["reject_block"] is False
        payload.update(collection=collection, server_delta=collection["server"]["server_delta"],
                       checks={**collection["checks"], "ips": "pass"})
        payload["execution_status"] = report.execution_status(has_data=True, checks=payload["checks"])
        entries.append({"key": unit["key"], "payload": payload})
        if len(entries) == 3:
            journal.record_block(entries)
            entries = []
    output = devreport.report_run(journal.path, plan_path=plan_path, raw_dir=raw, artifacts_dir=root / "art",
                                  result_dir=root / "res", docs_dir=root / "docs")
    assert Path(output["document_path"]).name == "X6S_result.md"
    assert Path(output["result_path"]).name == "v33_dev_X6_fixture.json"
    value = json.loads(Path(output["result_path"]).read_text(encoding="utf-8"))
    assert value["exploratory"] is True and value["plan_id"] == "final_bundle_v2"
    assert value["execution_status"] == "판정 통과"
    assert "frozen_feedback" not in value["checks"]
    for name in ("netem_config", "realized_loss", "success_rate", "policy_uplink"):
        assert value["checks"][name] == "pass"
    assert value["checks"]["trajectory_end_c1_seen"] == "pass"
    for cell in value["statistics"]["cells"]:
        assert {row["id"] for row in cell["contrasts"]} == {"v33s_c1_minus_v33pre_c1", "v33s_c1_minus_v33s_none",
                                                            "v33pre_c1_minus_v33s_none"}
        for row in cell["contrasts"]:
            assert row["inference_unit"] == "trajectory"
            assert row["aa"]["applies"] is False
    document = Path(output["document_path"]).read_text(encoding="utf-8")
    assert "탐색 계획 final_bundle_v2의 측정이다" in document
    assert not (root / "docs/X6_result.md").exists()


def test_v2_smoke_runs_none_path_check_on_flagged_none_arm():
    plan, _ = devbed.read_plan(PLAN)
    assert "v33none" not in plan["arms"] and plan["arms"]["v33s_none"]["none_path_check"] is True
    units = arms.iter_units(plan, ["M0"])
    payloads, events = zip(*(smoke_payload(plan, unit) for unit in units))
    fixture = (plan, units, list(payloads), list(events))
    result = summarize(fixture)
    checked = {(item["cell"], item["arm"]) for item in result["details"]["none_path"]}
    assert checked == {(unit["cell"], "v33s_none") for unit in units if unit["arm"] == "v33s_none"}
    assert result["checks"]["none_path"] == "pass"
    target(fixture, "v33s_none")["rows"][0].update(policy_path="c1")
    assert summarize(fixture)["checks"]["none_path"] == "fail"
