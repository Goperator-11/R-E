import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from experiments.v33 import devbed, devreport
from experiments.v33.lib import arms, blocks, report


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(devreport.json_bytes(value))


def make_fixture(root, monkeypatch, *, runtime=False):
    root.mkdir(parents=True, exist_ok=True)
    raw = root / "v33_runs/fixture"
    raw.mkdir(parents=True)
    monkeypatch.chdir(raw)
    plan, _ = devbed.read_plan(devbed.ROOT / "g3/v33/plans/final_bundle_v1.json")
    cell = copy.deepcopy(plan["tasks"]["M0"]["cells"][0])
    cell["arms"] = ["m4L3", "pad4L3"]
    cell["phases"][0].update(blocks=2, connections_per_arm=4, connections_per_arm_block=2)
    plan["tasks"]["M0"]["cells"] = [cell]
    plan["tasks"]["M0"]["connections_total"] = 8
    plan_path = root / "fixture_plan.json"
    write_json(plan_path, plan)
    digest = devreport.file_sha256(plan_path)
    provenance = {"plan_sha256": digest, "plan_commit": "a" * 40,
        "plan_doc_commit": "b" * 40, "plan_doc_sha256": "b" * 64,
        "plan_files": [{"committed_at": 1, "path": "fixture_plan.json", "sha256": digest,
                        "commit": "a" * 40}]}
    meta = report.capture_metadata({"run_id": "fixture", "task": "M0", **provenance,
        "env": {"uname_r": "fixture", "python3_V": "fixture", "tc_V": "fixture",
                "ip_V": "fixture", "cpu_list": [0], "cpu_count": 1},
        "binary_sha256": {key: item["sha256"] for key, item in plan["binaries"].items()},
        "srcsha": {key: item["srcsha"] for key, item in plan["binaries"].items()},
        "m1_dependency": None})
    fingerprint = blocks.fingerprint(devbed.ROOT, digest, plan["binaries"]) if runtime else "c" * 64
    manifest = {"run_id": "fixture", "task": "M0", "plan": plan,
                "provenance": provenance, "meta": meta, "fingerprint": fingerprint,
                "m1_dependency": None}
    write_json(raw / "manifest_fixture.json", manifest)
    units = arms.iter_units(plan, ["M0"])
    journal = blocks.UnitJournal(raw / "units_fixture.jsonl", "fixture", fingerprint,
                                 units, metadata=meta)
    entries = []
    for unit in units:
        directory = Path("units") / unit["key"]
        directory.mkdir(parents=True)
        log = directory / "conns.jsonl"
        rows = []
        conns = []
        for index in range(2):
            scid = f"{index:08x}"
            row = {"i": index, "ok": True, "ms": 80 + unit["block"] + index,
                "client_scid": scid, "ips_eff": 1280, "m_used": 4,
                "first_flight_bytes": 2560, "first_flight_datagrams": 2,
                "first_flight_parity_bytes": 5340, "first_flight_parity_dgrams": 4,
                "first_flight_lead_dgrams": 3, "bytes_parity": 5340, "parity_sent": 4,
                "path_rtt_valid": False, "feedback_wait_received": False,
                "feedback_wait_limit_ms": 200, "feedback_wait_ns": 0,
                "flight_expectation": {"source": "explicit", "k": 2},
                "plan_sha256": digest,
                "binary_sha256": plan["binaries"]["gen33"]["sha256"],
                "srcsha": plan["binaries"]["gen33"]["srcsha"],
                "server_binary_sha256": plan["binaries"]["gen33"]["sha256"],
                "server_srcsha": plan["binaries"]["gen33"]["srcsha"]}
            if unit["arm"] == "pad4L3":
                row.update(first_flight_parity_bytes=0, first_flight_parity_dgrams=0,
                           first_flight_lead_dgrams=0, bytes_parity=0, parity_sent=0,
                           extra_sent={"first_bytes": 5340, "first_sent": 4, "first_lead": 3})
            rows.append(row)
            conns.append({"key": scid, "client_scid": scid, "initial_dcid": "abcdef0123456789",
                "reason": "shutdown", "logged_ns": index + 1, "rx_bytes": 4096,
                "rx_orig_bytes": 2560, "rx_parity_bytes": 1536, "stack_bytes": 4096,
                "beff_stack": 4096, "beff_phys": 4096, "beff_orig": 2560, "beff_parity": 1536})
        log.write_text("".join(json.dumps(value, sort_keys=True) + "\n" for value in conns),
                       encoding="utf-8", newline="\n")
        client = directory / "client.jsonl"
        client.write_text("".join(json.dumps(value, sort_keys=True) + "\n" for value in rows),
                          encoding="utf-8", newline="\n")
        stats = {"bytes_in": 8192, "parities": 8, "recovered": 0, "credit_parities": 8,
                 "fb_sent": 0, "tls_accepted": 1, "feedback_version": 2, "fec_parse_fail": 0,
                 "conn_acct_evicted_lru": 0,
                 "conn_log": {"path": str(log), "lines": 2, "errors": 0, "pending": 0}}
        payload = {"rows": rows, "client_rc": 0, "cache_after": None,
            "started_at": f"2026-11-06T10:00:{unit['block']:02d}+00:00",
            "ended_at": f"2026-11-06T10:00:{unit['block']:02d}+00:00",
            "server": {"returncode": 0, "forced_kill": False, "exited_before_stop": False,
                       "stats": stats, "conn_log_path": str(log),
                       "certificate": {"der_sha256": "d" * 64, "der_bytes": 16000}},
            "raw_files": {"conn_log": str(log), "client_stdout": str(client)},
            "raw_sha256": {path.as_posix(): devreport.file_sha256(path) for path in (log, client)}}
        collection = devbed.collection_validation(plan, unit, payload)
        payload.update(collection=collection, server_delta=collection["server"]["server_delta"],
                       checks={**collection["checks"], "ips": "pass"})
        payload["execution_status"] = report.execution_status(has_data=True, checks=payload["checks"])
        entries.append({"key": unit["key"], "payload": payload})
        if len(entries) == 2:
            journal.record_block(entries)
            entries = []
    return {"journal_path": journal.path, "plan_path": plan_path, "raw_dir": raw,
            "artifacts_dir": root / "artifacts", "result_dir": root / "g3/v33/results",
            "docs_dir": root / "docs"}


@pytest.fixture
def fixture_run(tmp_path, monkeypatch):
    return make_fixture(tmp_path, monkeypatch)


def test_report_only_identical_bytes_and_expected_hashes(fixture_run):
    first = devreport.report_run(**fixture_run)
    before = {key: Path(path).read_bytes() for key, path in first.items()}
    second = devreport.report_run(**fixture_run)
    assert first == second
    assert before == {key: Path(path).read_bytes() for key, path in second.items()}
    value = json.loads(before["result_path"])
    assert value["label"] == "development" and value["confirmatory"] is False
    assert value["policy_version"] == "v3.3.1-dev"
    assert value["client_rows"] == 8 and value["units_completed"] == 4
    assert value["server_summary"][0]["not_accepted"] == 2
    assert value["idle_check"]["status"] == "미확인"
    assert all(item["mean_idle_ms"] is None for item in value["observations"])
    assert hashlib.sha256(before["result_path"]).hexdigest() == EXPECTED_RESULT_SHA
    assert hashlib.sha256(before["document_path"]).hexdigest() == EXPECTED_DOCUMENT_SHA


def test_artifact_manifest_detects_result_change(fixture_run):
    abandoned = fixture_run["raw_dir"] / "units/abandoned/attempt_0/server.stderr"
    abandoned.parent.mkdir(parents=True)
    abandoned.write_bytes(b"interrupted fixture log\n")
    output = devreport.report_run(**fixture_run)
    files = devreport.verify_artifacts(output["artifacts_manifest"])
    assert Path(output["document_path"]) in files
    assert abandoned in files
    result_path = Path(output["result_path"])
    value = json.loads(result_path.read_bytes())
    value["client_rows"] += 1
    result_path.write_bytes(devreport.json_bytes(value))
    with pytest.raises(ValueError, match="SHA 목록 검증 실패"):
        devreport.verify_artifacts(output["artifacts_manifest"])


def test_m1_build_result_uses_saved_environment(fixture_run, monkeypatch):
    run = devreport.read_run(fixture_run["journal_path"], plan_path=fixture_run["plan_path"],
                            raw_dir=fixture_run["raw_dir"])
    run["manifest"]["task"] = "M1"
    saved_env = run["manifest"]["meta"]["env"]
    saved_env["uname_r"] = "saved-kernel"
    captured = {}

    def summarize(*args, **kwargs):
        captured.update(kwargs)
        return {"checks": {}, "a_vs_sealed": {"kernel": kwargs["env"]["uname_r"]}}

    monkeypatch.setattr(devreport.statistics, "summarize", summarize)
    value = devreport.build_result(run)
    assert captured["env"] == saved_env
    assert value["a_vs_sealed"]["kernel"] == "saved-kernel"
    assert value["meta"]["env"] == value["env"] == saved_env
    saved_env["uname_r"] = "changed-after-build"
    assert value["meta"]["env"]["uname_r"] == "saved-kernel"


@pytest.mark.parametrize("missing", [False, True])
def test_x9_named_fields_preserve_direction_denominators_and_unknowns(fixture_run, monkeypatch, missing):
    run = devreport.read_run(fixture_run["journal_path"], plan_path=fixture_run["plan_path"],
                            raw_dir=fixture_run["raw_dir"])
    run["manifest"]["task"] = "X9"
    c2s_rate = None if missing else 0.125
    c2s_ci = None if missing else [-0.05, 0.2]
    stats = {"cells": [
        {"cell": "both", "arms": [
            {"arm": "mlkem_off", "warmup_excluded": 10, "primary": {"pto": {
                "primary": {"rate": 0.5, "n_valid": 6}, "definition_mismatch": 3}}},
            {"arm": "x25519_off", "warmup_excluded": 5, "primary": {"pto": {
                "primary": {"rate": 0.25, "n_valid": 4}, "definition_mismatch": 1}}}],
         "pto_contrast": {"primary": {"ci95": [0.1, 0.4], "effect_sign": "MLKEM-x25519"}}},
        {"cell": "c2s", "arms": [
            {"arm": "x25519_off", "warmup_excluded": 15, "primary": {"pto": {
                "primary": {"rate": 0.0, "n_valid": 9}, "definition_mismatch": 0}}},
            {"arm": "mlkem_off", "warmup_excluded": 20, "primary": {"pto": {
                "primary": {"rate": c2s_rate, "n_valid": 0 if missing else 8},
                "definition_mismatch": 2}}}],
         "pto_contrast": {"primary": {"ci95": c2s_ci, "effect_sign": "MLKEM-x25519"}}}]}
    before = copy.deepcopy(stats)
    monkeypatch.setattr(devreport.statistics, "summarize", lambda *args, **kwargs: stats)
    monkeypatch.setattr(devreport.report_checks, "summarize_checks",
                        lambda *args, **kwargs: {"checks": {"client_rows": "pass"}, "details": {}})
    value = devreport.build_result(run)
    assert stats == before
    saved = json.loads(devreport.json_bytes(value))["x9_by_direction"]
    units = {"pto_rate": "proportion", "diff_ci95": "proportion", "n_measured": "connections",
             "warmup_excluded": "connections", "pto_definition_mismatch": "connections"}
    assert saved == {
        "both": {"definition": "primary", "effect_sign": "MLKEM-x25519", "units": units,
                 "pto_rate_x25519": 0.25, "pto_rate_mlkem": 0.5, "diff_ci95": [0.1, 0.4],
                 "n_measured": {"x25519_off": 4, "mlkem_off": 6},
                 "warmup_excluded": {"x25519_off": 5, "mlkem_off": 10},
                 "pto_definition_mismatch": {"x25519_off": 1, "mlkem_off": 3}},
        "c2s": {"definition": "primary", "effect_sign": "MLKEM-x25519", "units": units,
                "pto_rate_x25519": 0.0, "pto_rate_mlkem": c2s_rate, "diff_ci95": c2s_ci,
                "n_measured": {"x25519_off": 9, "mlkem_off": 0 if missing else 8},
                "warmup_excluded": {"x25519_off": 15, "mlkem_off": 20},
                "pto_definition_mismatch": {"x25519_off": 0, "mlkem_off": 2}}}
    stats["cells"][0]["pto_contrast"]["primary"]["ci95"][0] = -9
    assert value["x9_by_direction"]["both"]["diff_ci95"] == [0.1, 0.4]


@pytest.mark.parametrize("missing", [False, True])
def test_certificate_summary_preserves_observed_and_unknown_units(fixture_run, missing):
    run = devreport.read_run(fixture_run["journal_path"], plan_path=fixture_run["plan_path"],
                            raw_dir=fixture_run["raw_dir"])
    for unit, payload in zip(run["units"], run["payloads"]):
        if unit["arm"] == "m4L3":
            known = not missing or unit["block"] == 0
            payload["collection"]["server"]["certificate_observation"] = {
                "source": "server.stderr", "status": "확인" if known else "미확인",
                "der_bytes": 16007 if known else None, "reported_lines": 1 if known else 0}
    value = devreport.server_summary(run["plan"], run["units"], run["payloads"])
    observed = next(item for item in value if item["arm"] == "m4L3")["certificate_observation"]
    assert observed == {"source": "server.stderr", "units_total": 2,
                        "units_observed": 1 if missing else 2, "der_bytes_values": [16007],
                        "status": "미확인" if missing else "확인"}
    assert "certificate_observation" not in next(item for item in value if item["arm"] == "pad4L3")


@pytest.mark.parametrize("target", ["log", "plan", "manifest", "tail"])
def test_changed_inputs_refused_before_outputs(fixture_run, target):
    if target == "log":
        path = next(fixture_run["raw_dir"].rglob("client.jsonl"))
        path.write_bytes(path.read_bytes() + b" ")
    elif target == "plan":
        path = fixture_run["plan_path"]
        path.write_bytes(path.read_bytes() + b" ")
    elif target == "manifest":
        path = fixture_run["raw_dir"] / "manifest_fixture.json"
        value = json.loads(path.read_bytes())
        value["meta"]["env"].pop("tc_V")
        write_json(path, value)
    else:
        path = fixture_run["journal_path"]
        path.write_bytes(path.read_bytes()[:-1])
    with pytest.raises((ValueError, RuntimeError)):
        devreport.report_run(**fixture_run)
    assert not fixture_run["result_dir"].exists()


def test_incomplete_journal_is_not_filled_with_failures(fixture_run):
    path = fixture_run["journal_path"]
    lines = path.read_bytes().splitlines(keepends=True)
    path.write_bytes(b"".join(lines[:-1]))
    with pytest.raises(ValueError, match="완료 저널"):
        devreport.report_run(**fixture_run)


def test_generated_document_check_docs_and_cli(fixture_run):
    output = devreport.report_run(**fixture_run)
    checked = subprocess.run([sys.executable, "-I", "-B", str(devbed.ROOT / "tools/check_docs.py"),
                              "--root", str(fixture_run["docs_dir"].parent),
                              "--file", output["document_path"]], cwd=devbed.ROOT,
                             capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    command = [sys.executable, "-I", "-B", str(devbed.ROOT / "experiments/v33/devreport.py"),
               "--report-only", str(fixture_run["journal_path"]),
               "--plan", str(fixture_run["plan_path"]),
               "--artifacts-dir", str(fixture_run["artifacts_dir"]),
               "--result-dir", str(fixture_run["result_dir"]), "--docs-dir", str(fixture_run["docs_dir"])]
    original = {key: Path(path).read_bytes() for key, path in output.items()}
    for _ in range(2):
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=30)
        assert completed.returncode == 0, completed.stderr
        assert original == {key: Path(path).read_bytes() for key, path in output.items()}
    assert "서버 계수" in original["document_path"].decode("utf-8")


def test_raw_destination_collision_refused(fixture_run):
    fixture_run["result_dir"] = fixture_run["raw_dir"]
    with pytest.raises(ValueError, match="원자료 안"):
        devreport.report_run(**fixture_run)


def test_runner_reports_missing_report_dependency_before_runtime(monkeypatch):
    def unavailable(name):
        raise ModuleNotFoundError("fixture missing scipy", name="scipy")
    monkeypatch.setattr(devbed.importlib, "import_module", unavailable)
    with pytest.raises(devbed.PlanError, match="의존성이 없다: scipy"):
        devbed.load_reporter()


@pytest.mark.parametrize("fail_reporting", [False, True])
def test_real_reporter_controls_runner_lock_after_done(tmp_path, monkeypatch, fail_reporting):
    inputs = make_fixture(tmp_path, monkeypatch, runtime=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(blocks, "_process_alive", lambda _: False)
    lock_path = tmp_path / "MEASURE_LOCK.json"
    raw = inputs["raw_dir"]
    lock = blocks.MeasurementLock(lock_path, raw / "status_fixture.json", raw / "DONE_fixture",
        task="F26", run_id="fixture", expected_end_kst="2026-11-14T23:00:00+09:00")
    lock.start()
    lock.mark_measurement_done()
    lock.close()
    args = devbed.parser().parse_args(["--plan", str(inputs["plan_path"]), "--report-only",
        "--task", "M0", "--run-id", "fixture", "--lock", str(lock_path),
        "--artifacts-dir", str(inputs["artifacts_dir"])])
    manifest = devreport.read_json(raw / "manifest_fixture.json")
    class Backend:
        def __init__(self, *args, **kwargs):
            pass
    def reporter(journal_path, **kwargs):
        result = devreport.report_run(journal_path, **kwargs, result_dir=inputs["result_dir"],
                                     docs_dir=inputs["docs_dir"])
        if fail_reporting:
            Path(result["result_path"]).write_bytes(b"changed after generation\n")
        return result
    before = inputs["journal_path"].read_bytes()
    if fail_reporting:
        with pytest.raises(devbed.PlanError, match="SHA 목록 검증 실패"):
            devbed.execute_run(args, manifest["plan"], manifest["provenance"],
                               reporter=reporter, backend_factory=Backend, net=object())
        assert lock_path.exists()
    else:
        devbed.execute_run(args, manifest["plan"], manifest["provenance"],
                          reporter=reporter, backend_factory=Backend, net=object())
        assert not lock_path.exists()
    assert (raw / "DONE_fixture").exists()
    assert inputs["journal_path"].read_bytes() == before


EXPECTED_RESULT_SHA = "8ebaa81af6c03735f95f469750fab1eac3778524428fbe7cc94f13222c8e02a5"
EXPECTED_DOCUMENT_SHA = "ed8fdd7210986c6d6c877bafa88902f0cd1a77ddec62a412515933af900337c7"
