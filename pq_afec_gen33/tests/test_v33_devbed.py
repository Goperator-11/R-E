import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from experiments.v33 import devbed
from experiments.v33.lib import arms, blocks, report

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "g3/v33/plans/final_bundle_v1.json"


def load():
    return devbed.read_plan(PLAN)


def git(root, *args):
    return subprocess.run(["git", "-c", "core.longpaths=true", "-C", str(root), *args], check=True,
                          capture_output=True, text=True, encoding="utf-8")


@pytest.fixture
def plan_repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "core.longpaths", "true")
    plan, _ = load()
    json_path = tmp_path / plan["precommit"]["plan_paths"][0]
    json_path.parent.mkdir(parents=True)
    json_path.write_bytes(PLAN.read_bytes())
    doc_path = tmp_path / plan["precommit"]["plan_paths"][1]
    doc_path.write_bytes(b"fixture\n")
    git(tmp_path, "-c", "core.autocrlf=false", "add", ".")
    git(tmp_path, "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-qm", "계획 fixture")
    return tmp_path, json_path, doc_path, plan


def test_plan_summary_uses_all_required_and_additional_connections():
    plan, digest = load()
    result = devbed.planned_summary(plan, digest)
    assert result["connections"] == 78080
    assert result["expected_minutes"] == 224
    assert result["policy_version"] == "v3.3.1-dev"
    assert result["label"] == "development"
    assert result["confirmatory"] is False
    assert [row["task"] for row in result["tasks"]] == ["M0", "M1", "X1", "X9", "X6"]
    assert [row["connections"] for row in result["tasks"]] == [480, 7200, 8680, 25620, 36100]
    assert result["plan_sha256"] == hashlib.sha256(PLAN.read_bytes()).hexdigest()


def test_task_selection_retains_plan_order():
    plan, digest = load()
    result = devbed.planned_summary(plan, digest, ["X6", "M1"])
    assert [row["task"] for row in result["tasks"]] == ["M1", "X6"]


def test_six_arm_williams_covers_each_directed_neighbor_once():
    rows = arms.williams(6)
    pairs = [(left, right) for row in rows for left, right in zip(row, row[1:])]
    assert len(rows) == 6
    assert len(pairs) == len(set(pairs)) == 30
    assert set(pairs) == {(left, right) for left in range(6) for right in range(6) if left != right}


def test_fingerprint_ignores_env_and_other_files(tmp_path, monkeypatch):
    source = tmp_path / "experiments/v33"
    (source / "lib").mkdir(parents=True)
    runner = source / "devbed.py"
    runner.write_bytes(b"runner\n")
    (source / "lib/netbed.py").write_bytes(b"netbed\n")
    (source / "devreport.py").write_bytes(b"report\n")
    (tmp_path / "experiments/padbed.py").write_bytes(b"padbed\n")
    (tmp_path / "experiments/gate_v3_parity.py").write_bytes(b"gate\n")
    plan, digest = load()
    initial = blocks.fingerprint(tmp_path, digest, plan["binaries"])
    monkeypatch.setenv("PADFEC_X", "fixture")
    (tmp_path / "experiments/unrelated.py").write_bytes(b"unrelated\n")
    assert blocks.fingerprint(tmp_path, digest, plan["binaries"]) == initial
    runner.write_bytes(b"runner changed\n")
    assert blocks.fingerprint(tmp_path, digest, plan["binaries"]) != initial


def test_dry_run_does_not_write_or_launch_processes(tmp_path):
    code = r'''
import builtins, io, os, runpy, socket, subprocess, sys
root, plan = sys.argv[1:]
def deny(*args, **kwargs):
    raise AssertionError("mutation or process launch")
original = builtins.open
def readonly(path, mode="r", *args, **kwargs):
    if any(value in mode for value in "wax+"):
        deny()
    return original(path, mode, *args, **kwargs)
builtins.open = readonly
io.open = readonly
for name in ("mkdir", "makedirs", "remove", "unlink", "replace", "rename", "open"):
    setattr(os, name, deny)
subprocess.run = deny
subprocess.Popen = deny
socket.socket = deny
sys.argv = ["devbed.py", "--plan", plan, "--dry-run"]
runpy.run_path(root + "/experiments/v33/devbed.py", run_name="__main__")
'''
    result = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(ROOT), str(PLAN)],
                            cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["connections"] == 78080
    assert list(tmp_path.iterdir()) == []


def test_plan_commit_is_last_change_not_head(plan_repo):
    root, path, doc, plan = plan_repo
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    first = devbed.verify_committed_plan(path, plan, digest, root)
    (root / "other.txt").write_bytes(b"unrelated\n")
    git(root, "add", "other.txt")
    git(root, "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-qm", "별도 fixture")
    second = devbed.verify_committed_plan(path, plan, digest, root)
    assert second == first
    assert second["plan_commit"] != git(root, "rev-parse", "HEAD").stdout.strip()


@pytest.mark.parametrize("target,staged", [("json", False), ("json", True), ("doc", False), ("doc", True)])
def test_dirty_plan_or_doc_refused(plan_repo, target, staged):
    root, path, doc, plan = plan_repo
    changed = path if target == "json" else doc
    changed.write_bytes(changed.read_bytes() + b"\n")
    if staged:
        git(root, "add", str(changed))
    with pytest.raises(devbed.PlanError, match="커밋하지 않은"):
        devbed.verify_committed_plan(path, plan, hashlib.sha256(path.read_bytes()).hexdigest(), root)


def test_uncommitted_plan_cli_returns_two_before_runtime(plan_repo, monkeypatch, capsys):
    root, path, doc, plan = plan_repo
    plan["precommit"]["plan_paths"] = ["new.json", "new.md"]
    new_path = root / "new.json"
    new_path.write_text(json.dumps(plan), encoding="utf-8")
    (root / "new.md").write_bytes(b"fixture\n")
    monkeypatch.setattr(devbed, "ROOT", root)
    assert devbed.main(["--plan", str(new_path), "--run"]) == 2
    error = capsys.readouterr().err
    assert "git 확인 실패" in error
    assert "부분 구현" not in error


@pytest.mark.parametrize("mode", ["--run", "--smoke"])
@pytest.mark.parametrize("field", ["sha256", "srcsha"])
def test_null_binary_identifiers_refused_before_runtime(tmp_path, mode, field, capsys):
    plan, _ = load()
    plan["binaries"]["gen33"][field] = None
    path = tmp_path / "null.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    assert devbed.main(["--plan", str(path), mode]) == 2
    assert f"gen33.{field}가 미확정" in capsys.readouterr().err


def test_exact_bytes_checked_even_when_git_hides_worktree_change(plan_repo):
    root, path, doc, plan = plan_repo
    git(root, "update-index", "--assume-unchanged", str(path))
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    with pytest.raises(devbed.PlanError, match="바이트"):
        devbed.verify_committed_plan(path, plan, hashlib.sha256(path.read_bytes()).hexdigest(), root)


@pytest.mark.parametrize("content", [b'{"schema":1,"schema":2}', b'{"schema":NaN}', b'[]'])
def test_malformed_plan_refused(tmp_path, content):
    path = tmp_path / "plan.json"
    path.write_bytes(content)
    with pytest.raises(devbed.PlanError):
        devbed.read_plan(path)


def test_plan_commit_must_precede_first_actual_start():
    provenance = {"plan_files": [{"committed_at": 100}, {"committed_at": 200}]}
    with pytest.raises(devbed.PlanError, match="앞서지"):
        devbed.require_plan_before_start(provenance, "1970-01-01T00:03:20+00:00")
    devbed.require_plan_before_start(provenance, "1970-01-01T00:03:21+00:00")
    with pytest.raises(devbed.PlanError, match="timezone"):
        devbed.require_plan_before_start(provenance, "1970-01-01T00:03:21")


def test_missing_reporter_refuses_before_files(plan_repo, monkeypatch, capsys):
    root, path, doc, plan = plan_repo
    monkeypatch.setattr(devbed, "ROOT", root)
    def unavailable():
        raise devbed.PlanError("F24 결과 생성기가 없어 측정을 시작할 수 없다")
    monkeypatch.setattr(devbed, "load_reporter", unavailable)
    output = root / "raw"
    for mode in ("--run", "--smoke", "--resume", "--report-only"):
        assert devbed.main(["--plan", str(path), mode, "--raw-dir", str(output),
                            "--lock", str(root / "lock.json"), "--artifacts-dir", str(root / "artifacts")]) == 2
        assert "F24 결과 생성기" in capsys.readouterr().err
    assert not output.exists()
    assert not (root / "lock.json").exists()
    assert not (root / "artifacts").exists()


def test_environment_commands_can_be_replaced_without_network(monkeypatch):
    commands = []
    def fake(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "fixture version\n", "")
    monkeypatch.setattr(os, "sched_getaffinity", lambda _: {2, 3}, raising=False)
    monkeypatch.setattr(os, "cpu_count", lambda: 8)
    env = devbed.collect_environment(fake)
    assert set(env) == {"uname_r", "python3_V", "tc_V", "ip_V", "cpu_list", "cpu_count"}
    assert env["cpu_list"] == [2, 3]
    assert [sys.executable, "-I", "-B", "--version"] in commands


def test_environment_missing_output_is_an_error():
    def fake(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, "", "")
    with pytest.raises(devbed.PlanError, match="환경 정보"):
        devbed.collect_environment(fake)


def conn_fixture(tmp_path, arm="m4L3"):
    plan, _ = load()
    unit = next(unit for unit in arms.iter_units(plan, ["M0"]) if unit["arm"] == arm)
    unit = {**unit, "rows_expected": 2}
    path = tmp_path / "connections.jsonl"
    records = [{"key": f"account-{i}", "client_scid": f"0000000{i}",
                "initial_dcid": "0102030405060708", "reason": "shutdown", "logged_ns": 10 + i,
                "rx_bytes": 3000 + i, "rx_orig_bytes": 2500, "rx_parity_bytes": 500 + i,
                "stack_bytes": 3000, "beff_stack": 2560, "beff_phys": 2560,
                "beff_orig": 2000, "beff_parity": 560} for i in (1, 2)]
    path.write_text("".join(json.dumps(row) + "\n" for row in reversed(records)), encoding="utf-8")
    stats = {"bytes_in": 6003, "parities": 2, "recovered": 0, "credit_parities": 2,
             "fb_sent": 0, "feedback_version": 2, "fec_parse_fail": 0,
             "conn_acct_evicted_lru": 0, "tls_accepted": 1,
             "conn_log": {"path": str(path), "lines": 2, "errors": 0, "pending": 0}}
    payload = {"rows": [{"ok": True, "client_scid": row["client_scid"]} for row in records],
               "server": {"returncode": 0, "forced_kill": False, "exited_before_stop": False,
                          "stats": stats, "conn_log_path": str(path)}}
    return plan, unit, payload, path, records


def test_conn_log_roundtrip(tmp_path):
    plan, unit, payload, path, records = conn_fixture(tmp_path)
    assert report.read_conn_log(path) == list(reversed(records))
    result = report.validate_server_unit(plan, unit, payload)
    assert result["execution_status"] == "판정 통과"
    assert result["conn_log"]["actual_lines"] == 2
    assert result["not_accepted"] == 1
    assert result["server_delta"]["bytes_in"] == 6003
    assert result["reject_block"] is False
    assert result["unit_identity"]["phase"] == unit["phase"]


def test_frozen_arm_block_rejected_on_feedback(tmp_path):
    plan, unit, payload, path, records = conn_fixture(tmp_path, "v31auto")
    payload["server"]["stats"]["fb_sent"] = 1
    result = report.validate_server_unit(plan, unit, payload)
    assert result["execution_status"] == "판정 실패"
    assert result["checks"]["frozen_feedback"] == "fail"
    assert result["frozen_arm_fb_sent"] == 1
    assert result["reject_block"] is True
    assert any(row["check"] == "frozen_feedback" for row in result["incidents"])


def test_cost_uses_server_counters():
    from experiments.v33.lib import statistics

    plan, _ = load()
    units = arms.iter_units(plan, ["M0"])
    payloads = [{"rows": [{"i": index, "ok": True, "ms": 90,
                            "first_flight_bytes": 2560, "bytes_parity": 200,
                            "parity_sent": 1} for index in range(unit["rows_expected"])],
                 "server_delta": {"bytes_in": 60000, "parities": 40,
                                  "recovered": 1, "credit_parities": 40},
                 "collection": {"server": {"fec_parse_fail": 0, "tls_accepted": 1}}}
                for unit in units]
    before = statistics.summarize(plan, "M0", units, payloads)
    for payload in payloads:
        for row in payload["rows"]:
            row.update(bytes_parity=999999, parity_sent=999)
    after = statistics.summarize(plan, "M0", units, payloads)
    before_costs = [(cell["cell"], arm["arm"], arm["primary"]["server_cost"])
                    for cell in before["cells"] for arm in cell["arms"]]
    after_costs = [(cell["cell"], arm["arm"], arm["primary"]["server_cost"])
                   for cell in after["cells"] for arm in cell["arms"]]
    assert before_costs == after_costs
    assert all(cost["bytes_per_conn"] == 3000 and cost["n_rows"] == 20
               for _, _, cost in after_costs)
    assert all(arm["client_parity_count_unreliable"] for cell in after["cells"]
               for arm in cell["arms"] if arm["arm"] == "g2auto")
