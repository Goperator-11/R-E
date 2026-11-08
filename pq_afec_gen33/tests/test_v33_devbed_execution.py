import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from experiments.v33 import devbed
from experiments.v33.lib import arms, blocks, report


class FakeNet:
    def __init__(self):
        self.calls = []

    def require_root(self):
        self.calls.append("root")

    def setup(self):
        self.calls.append("setup")
        return {"cpu_affinity": [0], "mtu": 1500}

    def set_netem(self, delay, *, journal, **kwargs):
        self.calls.append("netem")
        journal({"qdisc": {"fixture": True}, "requested": {"delay": delay, **kwargs}})


def m1_result_fixture(plan_sha256):
    return {"task": "M1", "label": "development", "confirmatory": False,
            "policy_version": "v3.3.1-dev", "plan_sha256": plan_sha256,
            "execution_status": "판정 통과", "status": "판정불능", "n_blocks": 30,
            "contrasts": {name: {"mean": 0, "ci95": [-6, 6], "n_blocks": 30}
                          for name in ("a_b", "e_f", "c_d", "b_c")},
            "a_vs_sealed": {"delta_ms": 0}}


@pytest.fixture
def execution(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    plan, digest = devbed.read_plan(devbed.ROOT / "g3/v33/plans/final_bundle_v1.json")
    cell = copy.deepcopy(plan["tasks"]["M0"]["cells"][0])
    cell["arms"] = ["m4L3", "pad4L3"]
    cell["phases"] = [{"blocks": 2, "connections_per_arm_block": 1,
                       "connections_per_arm": 2, "loss_c2s_pct": 2, "loss_s2c_pct": 0}]
    plan["tasks"]["M0"]["cells"] = [cell]
    plan["tasks"]["M0"]["connections_total"] = 4
    args = devbed.parser().parse_args(["--plan", str(tmp_path / "fixture-plan.json"), "--smoke",
        "--run-id", "fixture_run", "--lock", str(tmp_path / "MEASURE_LOCK.json"),
        "--artifacts-dir", str(tmp_path / "artifacts")])
    args.plan.write_text(json.dumps(plan), encoding="utf-8")
    provenance = {"plan_sha256": digest, "plan_commit": "a" * 40,
                  "plan_doc_commit": "b" * 40, "plan_doc_sha256": "b" * 64,
                  "plan_files": [{"committed_at": 1}]}
    raw = tmp_path / "v33_runs" / args.run_id
    calls = []
    behavior = {"fail_key": None, "omit_logs": False, "report_error": False, "ips": 1280,
                "cache_reads": [], "report_calls": 0, "rewrite_raw": False,
                "m1_change_when": None, "server_mutation": None, "row_mutation": None}

    def task_id():
        return "M0" if args.smoke else args.task[0]

    def change_m1():
        args.m1_result.write_bytes(args.m1_result.read_bytes() + b" ")

    class Backend:
        def __init__(self, plan, raw_dir, **kwargs):
            self.plan, self.raw, self.digest = plan, raw_dir, kwargs["plan_sha256"]

        def address_for(self, unit):
            return "10.9.0.2:44433"

        def verify_binaries(self):
            calls.append("verify")

        def run_unit(self, unit, *, cache_path, attempt):
            calls.append((unit["key"], attempt))
            directory = self.raw / "unit_data" / unit["key"] / str(attempt)
            directory.mkdir(parents=True)
            path = directory / "rows.jsonl"
            path.write_text("fixture\n", encoding="utf-8")
            if unit["cache_key"] is not None:
                before = cache_path.read_bytes() if cache_path.exists() else None
                behavior["cache_reads"].append((unit["arm"], attempt, before))
                address = self.address_for(unit)
                if before is None:
                    state = devbed.learn3.new_state().to_json()
                    entry = {"state": state, "min_rtt_ms": 50, "min_hct_ms": 50,
                             "rtt_observations": 0, "conns": 0}
                    value = {"schema": "padfec3.cache3/11", "dests": {address: entry}}
                else:
                    value = report.validate_cache_bytes(before, "gen33", address)
                    entry = value["dests"][address]
                entry["conns"] += 1
                entry["rtt_observations"] += 1
                entry["state"]["seq"] += 1
                entry["state"]["c1_seen"] = unit["arm"] == "v33c1"
                cache_path.write_bytes(json.dumps(value, indent=2).encode("utf-8") + b"\n")
            if behavior["fail_key"] == unit["key"]:
                raise RuntimeError("fixture interrupted")
            if behavior["m1_change_when"] == "measurement":
                change_m1()
            info = self.plan["binaries"][self.plan["arms"][unit["arm"]]["binary"]]
            row = {"ok": True, "ms": 50, "ips_eff": behavior["ips"],
                   "plan_sha256": self.digest, "binary_sha256": info["sha256"], "srcsha": info["srcsha"]}
            row.update(i=0, client_scid="01020304", first_flight_bytes=2560,
                       first_flight_parity_dgrams=4, first_flight_parity_bytes=5340,
                       first_flight_lead_dgrams=3, m_used=4, path_rtt_valid=False,
                       feedback_wait_ns=0, feedback_wait_received=unit["arm"] == "v33c1",
                       feedback_wait_limit_ms=unit["profile"]["feedback_wait_ms"],
                       handshake_end_ns=50000000,
                       flight_expectation={"source": "explicit", "k": unit["profile"]["expect_k"]})
            if behavior["row_mutation"] is not None:
                behavior["row_mutation"](row)
            log_path = directory / "server.conns.jsonl"
            conn = {"key": "01020304", "initial_dcid": "0102030405060708", "client_scid": "01020304",
                    "reason": "shutdown", "logged_ns": 100, "rx_bytes": 4096,
                    "rx_orig_bytes": 2560, "rx_parity_bytes": 1536, "stack_bytes": 4096,
                    "beff_stack": 4096, "beff_phys": 4096, "beff_orig": 2560, "beff_parity": 1536}
            log_path.write_text(json.dumps(conn) + "\n", encoding="utf-8")
            stats = {"bytes_in": 4096, "parities": 1, "recovered": 0, "credit_parities": 1,
                     "fb_sent": 0, "tls_accepted": 1, "feedback_version": 2, "fec_parse_fail": 0,
                     "conn_acct_evicted_lru": 0,
                     "conn_log": {"path": str(log_path), "lines": 1, "errors": 0, "pending": 0}}
            if behavior["server_mutation"] is not None:
                behavior["server_mutation"](stats)
            stamp = datetime.now(timezone.utc).isoformat()
            return {"rows": [row], "server": {"returncode": 0, "stats": stats,
                    "forced_kill": False, "exited_before_stop": False, "conn_log_path": str(log_path)},
                    "client_rc": 0, "started_at": stamp, "ended_at": stamp,
                    "raw_files": {"client_stdout": str(path), "conn_log": str(log_path)}}

    def reporter(journal_path, *, raw_dir, artifacts_dir, **kwargs):
        behavior["report_calls"] += 1
        assert args.lock.exists()
        assert (raw_dir / f"DONE_{args.run_id}").exists()
        if behavior["report_error"]:
            raise RuntimeError("fixture report failed")
        manifest = json.loads((raw_dir / f"manifest_{args.run_id}.json").read_text(encoding="utf-8"))
        journal = blocks.UnitJournal(journal_path, args.run_id, manifest["fingerprint"],
                                     arms.iter_units(plan, [task_id()]), resume=True)
        artifacts_dir.mkdir(exist_ok=True)
        result_path = artifacts_dir / f"v33_dev_{task_id()}_{args.run_id}.json"
        value = {"label": "development", "confirmatory": False, "policy_version": "v3.3.1-dev",
                 "run_id": args.run_id, "rows": [entry["payload"]["rows"] for entry in journal.records]}
        result_path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
        required = [result_path, Path(journal_path)]
        if not behavior["omit_logs"]:
            required += [raw_dir / name for entry in journal.records for name in entry["payload"]["raw_sha256"]]
        if behavior["rewrite_raw"]:
            path = raw_dir / next(iter(journal.records[0]["payload"]["raw_sha256"]))
            path.write_bytes(b"reporter changed raw and regenerated manifest\n")
        if behavior["m1_change_when"] == "reporting":
            change_m1()
        sha_path = artifacts_dir / "artifacts.sha256"
        sha_path.write_text("".join(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + str(path) + "\n"
                                    for path in required), encoding="utf-8")
        return {"result_path": str(result_path), "artifacts_manifest": str(sha_path)}

    def execute():
        return devbed.execute_run(args, plan, provenance, reporter=reporter, backend_factory=Backend,
                                 environment_collector=lambda: {"fixture_env": True}, net=net)

    def journal():
        manifest = json.loads((raw / f"manifest_{args.run_id}.json").read_text(encoding="utf-8"))
        return blocks.UnitJournal(raw / f"units_{args.run_id}.jsonl", args.run_id,
                                  manifest["fingerprint"], arms.iter_units(plan, [task_id()]), resume=True)

    net = FakeNet()
    return args, plan, provenance, raw, calls, behavior, execute, journal, net


def test_execution_records_complete_blocks_and_releases_only_after_sha(execution):
    args, plan, provenance, raw, calls, behavior, execute, journal, net = execution
    result = execute()
    saved = journal()
    assert saved.complete
    assert saved.next_index == 4
    assert not args.lock.exists()
    assert (raw / f"DONE_{args.run_id}").exists()
    assert saved.metadata["policy_version"] == "v3.3.1-dev"
    assert all(entry["payload"]["checks"]["ips"] == "pass" for entry in saved.records)
    assert len([event for event in saved.events if event["event"] == "netem"]) == 4
    assert net.calls.count("netem") == 4
    devbed.verify_report_artifacts(result, raw / f"units_{args.run_id}.jsonl")


def test_resume_skips_completed_block_and_retries_partial_block(execution):
    args, plan, provenance, raw, calls, behavior, execute, journal, net = execution
    units = arms.iter_units(plan, ["M0"])
    behavior["fail_key"] = units[3]["key"]
    with pytest.raises(RuntimeError, match="interrupted"):
        execute()
    assert journal().next_index == 2
    assert args.lock.exists()
    assert not (raw / f"DONE_{args.run_id}").exists()
    args.lock.unlink()
    args.resume = True
    behavior["fail_key"] = None
    calls.clear()
    execute()
    assert [call for call in calls if isinstance(call, tuple)] == [(unit["key"], 1) for unit in units[2:]]
    assert (raw / "unit_data" / units[2]["key"] / "0" / "rows.jsonl").exists()
    assert (raw / "unit_data" / units[2]["key"] / "1" / "rows.jsonl").exists()
    assert journal().complete


def test_report_failure_keeps_done_and_lock_then_report_only_reuses_bytes(execution, monkeypatch):
    args, plan, provenance, raw, calls, behavior, execute, journal, net = execution
    behavior["report_error"] = True
    with pytest.raises(RuntimeError, match="report failed"):
        execute()
    path = raw / f"units_{args.run_id}.jsonl"
    before = path.read_bytes()
    assert args.lock.exists()
    assert (raw / f"DONE_{args.run_id}").exists()
    monkeypatch.setattr(blocks, "_process_alive", lambda _: False)
    args.smoke = False
    args.report_only = True
    args.task = ["M0"]
    behavior["report_error"] = False
    calls.clear()
    net.calls.clear()
    first = execute()
    bytes1 = Path(first["result_path"]).read_bytes(), Path(first["artifacts_manifest"]).read_bytes()
    execute()
    assert bytes1 == (Path(first["result_path"]).read_bytes(), Path(first["artifacts_manifest"]).read_bytes())
    assert path.read_bytes() == before
    assert calls == [] and net.calls == []
    assert not args.lock.exists()


def test_missing_log_sha_prevents_lock_release(execution):
    args, plan, provenance, raw, calls, behavior, execute, journal, net = execution
    behavior["omit_logs"] = True
    with pytest.raises(devbed.PlanError, match="원자료 로그"):
        execute()
    assert args.lock.exists()
    assert (raw / f"DONE_{args.run_id}").exists()


def test_same_run_id_cannot_replace_existing_raw(execution):
    args, plan, provenance, raw, calls, behavior, execute, journal, net = execution
    execute()
    original = (raw / f"units_{args.run_id}.jsonl").read_bytes()
    with pytest.raises(devbed.PlanError, match="이미 있다"):
        execute()
    assert (raw / f"units_{args.run_id}.jsonl").read_bytes() == original


def test_report_only_rejects_changed_raw_before_new_lock(execution):
    args, plan, provenance, raw, calls, behavior, execute, journal, net = execution
    execute()
    saved = journal()
    path = raw / next(iter(saved.records[0]["payload"]["raw_sha256"]))
    path.write_bytes(b"changed\n")
    args.smoke = False
    args.report_only = True
    args.task = ["M0"]
    with pytest.raises(devbed.PlanError, match="원자료 지문"):
        execute()
    assert not args.lock.exists()


def test_explicit_ips_mismatch_becomes_check_failure(execution):
    args, plan, provenance, raw, calls, behavior, execute, journal, net = execution
    plan["arms"]["m4L3"]["ips"] = 1400
    execute()
    units = {unit["key"]: unit for unit in arms.iter_units(plan, ["M0"])}
    for entry in journal().records:
        expected = "fail" if units[entry["key"]]["arm"] == "m4L3" else "pass"
        assert entry["payload"]["checks"]["ips"] == expected


@pytest.mark.parametrize("task", ["X1", "X6", "X9"])
def test_m1_dependent_measurement_requires_input_before_writes(execution, task):
    args, plan, provenance, raw, calls, behavior, execute, journal, net = execution
    args.smoke = False
    args.task = [task]
    with pytest.raises(devbed.PlanError, match="m1-result"):
        execute()
    assert not raw.exists()
    assert not args.lock.exists()


def test_m1_wide_interval_is_inconclusive_and_can_continue(tmp_path):
    plan, digest = devbed.read_plan(devbed.ROOT / "g3/v33/plans/final_bundle_v1.json")
    path = tmp_path / "M1.json"
    result = m1_result_fixture(digest)
    path.write_text(json.dumps(result), encoding="utf-8")
    dependency = devbed.m1_dependency(plan, "X6", path, digest)
    assert dependency["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert report.m1_aa(dependency["result"]["contrasts"]["c_d"], plan["statistics"])["inference_status"] == "판정불능"


def test_auto_resume_restores_complete_block_caches_and_preserves_partial_attempt(execution):
    args, plan, provenance, raw, calls, behavior, execute, journal, net = execution
    plan["tasks"]["M0"]["cells"][0]["arms"] = ["v33none", "v33c1"]
    units = arms.iter_units(plan, ["M0"])
    behavior["fail_key"] = units[3]["key"]
    with pytest.raises(RuntimeError, match="interrupted"):
        execute()
    saved = journal()
    assert saved.next_index == 2
    assert [item[:2] for item in behavior["cache_reads"]] == [
        (unit["arm"], 0) for unit in units]
    assert all(item[2] is None for item in behavior["cache_reads"][:2])
    clean = {}
    dirty = {}
    for unit in units[:2]:
        arm = unit["arm"]
        clean[arm] = blocks.snapshot_bytes(saved.cache_after(unit["cache_key"]))
        checkpoint = report.validate_cache_bytes(clean[arm], "gen33", "10.9.0.2:44433")
        entry = checkpoint["dests"]["10.9.0.2:44433"]
        assert entry["conns"] == 1
        assert entry["state"]["c1_seen"] is (arm == "v33c1")
        path = raw / "attempts" / "0" / (unit["cache_key"] + ".json")
        dirty[arm] = path.read_bytes()
        assert dirty[arm] != clean[arm]
        assert report.validate_cache_bytes(dirty[arm], "gen33")["dests"]["10.9.0.2:44433"]["conns"] == 2
    args.lock.unlink()
    args.resume = True
    behavior["fail_key"] = None
    behavior["cache_reads"].clear()
    calls.clear()
    execute()
    assert [call for call in calls if isinstance(call, tuple)] == [(unit["key"], 1) for unit in units[2:]]
    assert behavior["cache_reads"] == [(unit["arm"], 1, clean[unit["arm"]]) for unit in units[2:]]
    final = journal()
    assert final.complete
    for unit in units[:2]:
        arm = unit["arm"]
        path = raw / "attempts" / "0" / (unit["cache_key"] + ".json")
        assert path.read_bytes() == dirty[arm]
        current = blocks.snapshot_bytes(final.cache_after(unit["cache_key"]))
        entry = report.validate_cache_bytes(current, "gen33")["dests"]["10.9.0.2:44433"]
        assert entry["conns"] == 2
        assert entry["state"]["c1_seen"] is (arm == "v33c1")
    for unit in units[2:]:
        for attempt in ("0", "1"):
            assert (raw / "unit_data" / unit["key"] / attempt / "rows.jsonl").exists()
    assert not args.lock.exists()


def test_reporter_cannot_replace_raw_and_regenerate_sha_to_release_lock(execution):
    args, plan, provenance, raw, calls, behavior, execute, journal, net = execution
    behavior["rewrite_raw"] = True
    with pytest.raises(devbed.PlanError, match="원자료 또는 저널 바이트"):
        execute()
    assert args.lock.exists()
    assert (raw / f"DONE_{args.run_id}").exists()
    assert behavior["report_calls"] == 1
    saved = journal()
    relative, original_digest = next(iter(saved.records[0]["payload"]["raw_sha256"].items()))
    changed = raw / relative
    changed_digest = hashlib.sha256(changed.read_bytes()).hexdigest()
    assert changed_digest != original_digest
    manifest = (args.artifacts_dir / "artifacts.sha256").read_text(encoding="utf-8")
    assert changed_digest + "  " + str(changed) in manifest


@pytest.mark.parametrize("when,expected_report_calls,message", [
    ("measurement", 0, "M1 입력이 측정 중"),
    ("reporting", 1, "결과 생성 중 M1 입력")])
def test_m1_input_is_rechecked_before_and_after_reporting(execution, when,
                                                         expected_report_calls, message):
    args, plan, provenance, raw, calls, behavior, execute, journal, net = execution
    plan["tasks"]["X1"]["cells"] = copy.deepcopy(plan["tasks"]["M0"]["cells"])
    plan["tasks"]["X1"]["connections_total"] = 4
    args.smoke = False
    args.task = ["X1"]
    args.m1_result = args.plan.parent / "M1.json"
    m1 = m1_result_fixture(provenance["plan_sha256"])
    original = json.dumps(m1).encode("utf-8")
    args.m1_result.write_bytes(original)
    behavior["m1_change_when"] = when
    with pytest.raises(devbed.PlanError, match=message):
        execute()
    assert args.lock.exists()
    assert (raw / f"DONE_{args.run_id}").exists()
    assert behavior["report_calls"] == expected_report_calls
    dependency = journal().metadata["m1_dependency"]
    assert dependency["sha256"] == hashlib.sha256(original).hexdigest()
    assert dependency["sha256"] != hashlib.sha256(args.m1_result.read_bytes()).hexdigest()
    assert dependency["result"] == json.loads(args.m1_result.read_bytes())


@pytest.mark.parametrize("mutation", [
    lambda stats: stats["conn_log"].update(pending=1),
    lambda stats: stats["conn_log"].update(lines=2),
    lambda stats: stats.pop("bytes_in"),
])
def test_incomplete_collection_records_missing_and_preserves_uncommitted_block(execution, mutation):
    args, plan, provenance, raw, calls, behavior, execute, journal, net = execution
    behavior["server_mutation"] = mutation
    with pytest.raises(devbed.PlanError, match="수집 검사 실패: 자료 없음"):
        execute()
    saved = journal()
    assert saved.next_index == 0
    event = saved.events[-1]
    assert event["event"] == "unit_rejected"
    assert event["data"]["payload"]["execution_status"] == "자료 없음"
    assert len(event["data"]["block_keys"]) == 2
    assert args.lock.exists()
    assert not (raw / f"DONE_{args.run_id}").exists()


def test_c1_version_rejects_entire_block_and_records_incident(execution):
    args, plan, provenance, raw, calls, behavior, execute, journal, net = execution
    plan["tasks"]["M0"]["cells"][0]["arms"] = ["m4L3", "v33c1"]
    behavior["server_mutation"] = lambda stats: stats.update(feedback_version=3)
    with pytest.raises(devbed.PlanError, match="수집 검사 실패: 판정 실패"):
        execute()
    saved = journal()
    assert saved.next_index == 0
    validation = saved.events[-1]["data"]["payload"]["collection"]["server"]
    assert validation["checks"]["c1_feedback_version"] == "fail"
    assert validation["reject_block"]
    assert validation["incidents"]


def test_missing_server_accept_and_rtt_warning_do_not_fail_complete_unit(execution):
    args, plan, provenance, raw, calls, behavior, execute, journal, net = execution
    behavior["server_mutation"] = lambda stats: stats.update(tls_accepted=0)
    execute()
    for entry in journal().records:
        payload = entry["payload"]
        assert payload["collection"]["server"]["not_accepted"] == 1
        assert payload["execution_status"] == "판정 통과"
        assert not any("idle" in name or "rtt" in name for name in payload["checks"])


def test_bad_connection_index_is_a_recorded_missing_unit(execution):
    args, plan, provenance, raw, calls, behavior, execute, journal, net = execution
    behavior["row_mutation"] = lambda row: row.pop("i")
    with pytest.raises(devbed.PlanError, match="수집 검사 실패: 자료 없음"):
        execute()
    saved = journal()
    assert saved.next_index == 0
    payload = saved.events[-1]["data"]["payload"]
    assert payload["collection"]["observations"]["checks"] == {"observations": "missing"}
    assert payload["execution_status"] == "자료 없음"


def test_completed_status_reports_every_unit(execution):
    args, plan, provenance, raw, calls, behavior, execute, journal, net = execution
    execute()
    status = json.loads(devbed.run_paths(args, "M0")["status"].read_text(encoding="utf-8"))
    assert status["completed_units"] == status["total_units"] == len(journal().records)
