from copy import deepcopy
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest

from experiments.v33 import devbed, devreport
from experiments.v33.lib import arms, blocks, report, report_docs, statistics
from test_v33_devreport_statistics import _inputs
from test_v33_plan_v2_report import ADDRESS, _cache_bytes, _netem, _rows

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "g3/v33/plans/final_bundle_v3_x2.json"
OFFSETS = {"x2_true": 0, "x2_u0": 7, "x2_u1": 3, "x2_u4": 0, "x2_u5": 2, "x2_u10": 5, "x2_u20": -4}
EVIDENCE = re.compile(r"결과 근거: `(g3/v33/results/v33_dev_[A-Za-z0-9_.-]+\.json)`\.")


def _noise(arm, block):
    if arm == "x2_true":
        return 0
    if arm == "x2_u4":
        return 1 if block % 2 else -1
    return block % 2


@pytest.fixture(scope="module")
def plan():
    return json.loads(PLAN.read_text(encoding="utf-8"))


def test_x2_contrasts_pair_post_burnin_blocks_within_one_trajectory(plan):
    def change(unit, row):
        row["ms"] = 100 + OFFSETS[unit["arm"]] + _noise(unit["arm"], unit["block"])
        if row["i"] < unit["burnin_connections"] and unit["arm"] != "x2_true":
            row["ms"] = 9000
    units, payloads = _inputs(plan, "X2", change)
    result = statistics.summarize(plan, "X2", units, payloads)
    assert [cell["cell"] for cell in result["cells"]] == [cell["id"] for cell in plan["tasks"]["X2"]["cells"]]
    for cell in result["cells"]:
        by_arm = {arm["arm"]: arm for arm in cell["arms"]}
        for arm in by_arm.values():
            assert arm["all"]["n_rows"] == 300 and arm["burnin"]["n_rows"] == 100 and arm["primary"]["n_rows"] == 200
            assert arm["primary"]["hct"]["n"] == 7 and arm["primary"]["inference_unit"] == "block"
        assert len(cell["contrasts"]) == 4
        for contrast in cell["contrasts"]:
            noise = 1 / 7 if contrast["x"] == "x2_u4" else 4 / 7
            assert contrast["hct"]["mean"] == pytest.approx(OFFSETS[contrast["x"]] + noise)
            assert contrast["n_pairs"] == 7 and contrast["hct"]["df"] == 6
            assert contrast["inference_unit"] == "block" and contrast["scope"] == "primary"
            assert contrast["independent_trajectory_claim"] is False
            assert contrast["aa"] == {"applies": False, "ruler_ms": None, "note": "A/A 없음"}
            assert contrast["y"] == "x2_true" and contrast["cell"] == cell["cell"]
            assert {"input_mbps", "true_mbps", "kind", "card_input"} <= contrast.keys()
            assert contrast["one_rtt_difference"]["n"] == 7
            assert contrast["server_bytes_in_per_conn_difference"]["mean"] == 0
            if contrast["x"] == "x2_u4":
                assert contrast["inference_status"] == "판정불능"
                assert contrast["inference_reasons"] == ["95% 구간이 0을 포함"]
            else:
                assert contrast["inference_status"] == "차이 관측"
    hc = next(cell for cell in result["cells"] if cell["cell"] == "hc6000_l1")
    assert [item["kind"] for item in hc["contrasts"]] == ["오입력", "오입력", "오입력", "A/A"]


def test_x2_branch_does_not_touch_other_tasks(plan):
    units, payloads = _inputs(plan, "M0")
    result = statistics.summarize(plan, "M0", units, payloads)
    assert all(cell["contrasts"] == [] for cell in result["cells"])
    other = deepcopy(plan)
    other["tasks"]["X2"]["contrasts"] = []
    units, payloads = _inputs(other, "X2")
    assert all(cell["contrasts"] == [] for cell in statistics.summarize(other, "X2", units, payloads)["cells"])


def _small_plan():
    plan, _ = devbed.read_plan(PLAN)
    cells = deepcopy([cell for cell in plan["tasks"]["X2"]["cells"] if cell["id"] in ("bigcert_l2", "hc6000_l1")])
    for cell in cells:
        cell["burnin_per_arm_trajectory"] = 3
        cell["phases"][0].update(blocks=4, connections_per_arm=8, connections_per_arm_block=2)
    plan["tasks"]["X2"]["cells"] = cells
    plan["tasks"]["X2"]["connections_total"] = 2 * 5 * 8
    plan["required_connections_total"] = plan["tasks"]["X2"]["connections_total"] + plan["tasks"]["M0"]["connections_total"]
    return plan


def _report(tmp_path, monkeypatch, plan, task):
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
    meta = report.capture_metadata({"run_id": "fixture", "task": task, **provenance,
        "env": {"uname_r": "f", "python3_V": "f", "tc_V": "f", "ip_V": "f", "cpu_list": [0], "cpu_count": 1},
        "binary_sha256": {key: item["sha256"] for key, item in plan["binaries"].items()},
        "srcsha": {key: item["srcsha"] for key, item in plan["binaries"].items()}, "m1_dependency": None})
    manifest = {"run_id": "fixture", "task": task, "plan": plan, "provenance": provenance, "meta": meta,
                "fingerprint": "c" * 64, "m1_dependency": None}
    (raw / "manifest_fixture.json").write_bytes(devreport.json_bytes(manifest))
    units = arms.iter_units(plan, [task])
    journal = blocks.UnitJournal(raw / "units_fixture.jsonl", "fixture", "c" * 64, units, metadata=meta)
    entries = []
    for unit in units:
        directory = Path("units") / unit["key"] / "attempt_0"
        directory.mkdir(parents=True)
        rows, conns = _rows(plan, unit, digest)
        for row in rows:
            row["ms"] = 100 + OFFSETS[unit["arm"]] + _noise(unit["arm"], unit["block"])
        log = directory / "server.conns.jsonl"
        log.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in conns), encoding="utf-8", newline="\n")
        client = directory / "client.jsonl"
        client.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in rows), encoding="utf-8", newline="\n")
        stats = {"bytes_in": 8192, "parities": 8, "recovered": 1, "credit_parities": 8, "fb_sent": 0,
                 "tls_accepted": len(rows), "feedback_version": 2, "fec_parse_fail": 0, "conn_acct_evicted_lru": 0,
                 "recover_crc_fail": 0,
                 "conn_log": {"path": str(log), "lines": len(rows), "errors": 0, "pending": 0}}
        tc_before, tc_after, netem = _netem(unit)
        journal.record_event(unit["key"], "netem", netem)
        cache = tmp_path / "cache.json"
        cache.write_bytes(_cache_bytes(False))
        payload = {"rows": rows, "client_rc": 0, "cache_after": blocks.snapshot_cache(cache),
                   "tc_before": tc_before, "tc_after": tc_after,
                   "commands": {"client": ["qamp", "-addr", ADDRESS], "server": []}, "attempt": 0,
                   "started_at": "2026-11-09T10:00:00+00:00", "ended_at": "2026-11-09T10:00:01+00:00",
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
        if len(entries) == len(plan["tasks"][task]["cells"][0]["arms"]):
            journal.record_block(entries)
            entries = []
    output = devreport.report_run(journal.path, plan_path=plan_path, raw_dir=raw, artifacts_dir=root / "art",
                                  result_dir=root / "g3/v33/results", docs_dir=root / "docs")
    value = json.loads(Path(output["result_path"]).read_text(encoding="utf-8"))
    return root, output, value


def test_x2_report_writes_own_document_and_drops_x2_limit(tmp_path, monkeypatch):
    plan = _small_plan()
    root, output, value = _report(tmp_path, monkeypatch, plan, "X2")
    assert Path(output["document_path"]).name == "X2_result.md"
    assert value["exploratory"] is True and value["plan_id"] == "final_bundle_v3_x2"
    assert value["execution_status"] == "판정 통과"
    for name in ("none_path", "trajectory_end_c1_seen", "policy_uplink", "netem_config", "realized_loss",
                 "success_rate", "server_uniform", "no_feedback", "fec_parse_fail"):
        assert value["checks"][name] == "pass"
    assert "c1_path" not in value["checks"]
    assert value["measured_items"] == [{"id": "X2", "n_rows": 80, "execution_status": "판정 통과"}]
    assert [(row["cell"], row["arm"], row["policy_uplink_mbps"]) for row in value["policy_uplink_inputs"]] == [
        ("bigcert_l2", "x2_true", 2), ("bigcert_l2", "x2_u0", 0), ("bigcert_l2", "x2_u1", 1),
        ("bigcert_l2", "x2_u4", 4), ("bigcert_l2", "x2_u10", 10),
        ("hc6000_l1", "x2_true", 10), ("hc6000_l1", "x2_u0", 0), ("hc6000_l1", "x2_u5", 5),
        ("hc6000_l1", "x2_u20", 20), ("hc6000_l1", "x2_u10", 10)]
    for cell in value["statistics"]["cells"]:
        for contrast in cell["contrasts"]:
            assert contrast["n_pairs"] == 3 and contrast["hct"]["df"] == 2
    document = Path(output["document_path"]).read_text(encoding="utf-8")
    first = document.split("\n\n")[1]
    assert "정책 입력 uplink는 팔마다 계획에 고정한 값이며 netem 대역은 바꾸지 않음." in first
    assert "정책 입력 uplink는 netem 대역과 같음" not in document
    assert "탐색 계획 final_bundle_v3_x2의 측정이다" in first
    assert "## 정책 uplink 입력" in document and "## uplink 오입력 대조" in document
    assert "| hc6000_l1 | x2_u10 | 10 | 10 | 참값 |" in document
    assert "| hc6000_l1 | x2_u0 | 0 | 10 | 오입력 |" in document
    assert re.search(r"\| hc6000_l1 \| x2_u10_minus_x2_true \| 10 \| 10 \| A/A \|", document)
    assert "같은 대조의 1-RTT 비율과 서버 수신량 차이" in document
    limits = document.split("## 한계")[1]
    assert "업링크 오입력(X2)" not in limits and "토큰·resumption 기준선(X4)" in limits
    assert report_docs.check_document(Path(output["document_path"]), result=value)["status"] == "pass"
    process = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "tools/check_docs.py"), "--root", str(root),
                              "--file", str(output["document_path"])], cwd=ROOT, text=True, encoding="utf-8",
                             capture_output=True, timeout=60)
    assert process.returncode == 0, process.stdout + process.stderr
    assert not (root / "docs/X6_result.md").exists() and not (root / "docs/X6S_result.md").exists()


def test_m0x2_smoke_document_keeps_m0_shape_with_policy_inputs(tmp_path, monkeypatch):
    plan, _ = devbed.read_plan(PLAN)
    root, output, value = _report(tmp_path, monkeypatch, plan, "M0")
    assert Path(output["document_path"]).name == "M0X2_result.md"
    assert value["measured_items"] == []
    assert len(value["policy_uplink_inputs"]) == 5
    document = Path(output["document_path"]).read_text(encoding="utf-8")
    assert "## 정책 uplink 입력" in document and "## uplink 오입력 대조" not in document
    assert "업링크 오입력(X2)" in document.split("## 한계")[1]
    assert not (root / "docs/M0_result.md").exists() and not (root / "docs/M0S_result.md").exists()


def test_documents_without_policy_inputs_keep_original_header():
    result = {"task": "X6", "run_id": "fixture", "label": "development", "confirmatory": False,
              "policy_version": "v3.3.1-dev", "conditions": {"quic_go_version": "v0.61.0", "w_base_bytes": 1280,
              "initial_congestion_window_packets": 32, "loss_direction": "c2s_only_except_X9_both"}}
    text = report_docs.render_document(result)
    assert "packet, 정책 입력 uplink는 netem 대역과 같음. development 측정이며 확증이 아니다." in text
    assert "## 정책 uplink 입력" not in text and "## uplink 오입력 대조" not in text
    result["policy_uplink_inputs"] = []
    assert report_docs.render_document(result) == text


def _committed_documents():
    found = []
    for path in sorted((ROOT / "docs").glob("*_result.md")):
        match = EVIDENCE.search(path.read_text(encoding="utf-8"))
        if match is not None and (ROOT / match[1]).is_file():
            found.append(path.name)
    return found


@pytest.mark.parametrize("name", _committed_documents())
def test_committed_result_documents_render_unchanged(name):
    assert report_docs.check_document(ROOT / "docs" / name, repo_root=ROOT)["status"] == "pass"


def test_committed_documents_include_measured_tasks():
    assert {"M0_result.md", "M0S_result.md", "M1_result.md", "X1_result.md", "X6_result.md",
            "X9_result.md"} <= set(_committed_documents())
