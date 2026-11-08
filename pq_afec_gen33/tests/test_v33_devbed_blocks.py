import copy
import hashlib
import json
import threading
import time
from pathlib import Path

import pytest

from experiments.v33.lib import blocks


FP = "a" * 64
RUN_ID = "test-run"


def units(arms=("none", "c1"), count=2):
    result = []
    for block in range(count):
        for arm in arms:
            result.append({"key": f"M0.cell.t0.p0.b{block}.{arm}", "task": "M0",
                           "cell": "cell", "trajectory": 0, "phase": 0,
                           "block": block, "arm": arm, "rows_expected": 2,
                           "cache_key": f"M0.cell.t0.{arm}"})
    return result


def snapshot(raw=b'{"cache": "state"}\r\n'):
    import base64
    return {"encoding": "base64", "data": base64.b64encode(raw).decode("ascii"),
            "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}


def payload(cache=None):
    return {"rows": [{"ok": True}, {"ok": False}],
            "started_at": "2026-11-06T12:00:00+00:00",
            "ended_at": "2026-11-06T12:00:01+00:00",
            "server": {"collection": "fixture"},
            "cache_after": snapshot() if cache is None else cache}


def entries(schedule):
    return [{"key": unit["key"], "payload": payload()} for unit in schedule]


def create(tmp_path, schedule=None, **kwargs):
    return blocks.UnitJournal(tmp_path / f"{RUN_ID}.journal.jsonl", RUN_ID, FP,
                              units() if schedule is None else schedule,
                              metadata={"env": {"version": "recorded"}}, **kwargs)


def reopen(journal, **kwargs):
    return blocks.UnitJournal(journal.path, RUN_ID, FP, journal.expected_units,
                              resume=True, **kwargs)


def rehash_record(value):
    value.pop("record_sha256", None)
    value["record_sha256"] = hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode("utf-8")).hexdigest()
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8") + b"\n"


def test_resume_preserves_identity_metadata_and_bytes(tmp_path):
    journal = create(tmp_path)
    journal.record_block(entries(journal.expected_units[:2]))
    before = journal.path.read_bytes()
    resumed = reopen(journal, metadata={"env": {"version": "different"}})
    assert resumed.run_id == RUN_ID
    assert resumed.metadata == {"env": {"version": "recorded"}}
    assert resumed.records == journal.records
    assert resumed.next_index == 2
    assert not resumed.complete
    assert journal.path.read_bytes() == before


def test_new_run_rejects_existing_journal(tmp_path):
    journal = create(tmp_path)
    before = journal.path.read_bytes()
    with pytest.raises(FileExistsError):
        create(tmp_path)
    assert journal.path.read_bytes() == before


def test_completion_requires_whole_block_in_williams_order(tmp_path):
    journal = create(tmp_path)
    expected = entries(journal.expected_units[:2])
    for invalid in (expected[:1], list(reversed(expected)), [expected[0], expected[0]]):
        with pytest.raises(blocks.JournalError):
            journal.record_block(invalid)
    with pytest.raises(blocks.JournalError, match="record_block"):
        journal.record(expected[0]["key"], expected[0]["payload"])
    assert journal.next_index == 0
    journal.record_block(expected)
    with pytest.raises(blocks.JournalError, match="out of order"):
        journal.record_block(expected)


def test_single_arm_block_and_complete_boundary(tmp_path):
    schedule = units(arms=("none",), count=1)
    journal = create(tmp_path, schedule)
    journal.record(schedule[0]["key"], payload())
    assert journal.complete
    assert reopen(journal).complete
    with pytest.raises(blocks.JournalError):
        journal.record_event(schedule[0]["key"], "netem", {})


@pytest.mark.parametrize("field,value", [
    ("rows", [{"ok": True}]),
    ("rows", [{"ok": True}, None]),
    ("started_at", None),
    ("started_at", "2026-11-06T12:00:00"),
    ("ended_at", "2026-11-06T11:59:00+00:00"),
    ("server", {}),
    ("server", None),
    ("cache_after", None),
    ("cache_after", {"encoding": "base64", "data": "x", "sha256": "a" * 64, "size": 1}),
])
def test_incomplete_payload_rejected_before_append(tmp_path, field, value):
    journal = create(tmp_path)
    batch = entries(journal.expected_units[:2])
    batch[1]["payload"][field] = value
    before = journal.path.read_bytes()
    with pytest.raises(blocks.JournalError):
        journal.record_block(batch)
    assert journal.path.read_bytes() == before
    assert journal.next_index == 0


def test_cache_snapshot_and_restore_preserve_exact_bytes(tmp_path):
    source = tmp_path / "source.json"
    raw = b'{\r\n "x" : "\xc3\xa9", "n": 1.00\r\n}\n'
    source.write_bytes(raw)
    captured = blocks.snapshot_cache(source)
    destination = tmp_path / "new" / "cache.json"
    blocks.restore_cache(destination, captured)
    assert destination.read_bytes() == raw
    blocks.restore_cache(destination, captured)
    with pytest.raises(blocks.JournalError):
        blocks.restore_cache(destination, None)
    assert destination.read_bytes() == raw
    with pytest.raises(blocks.JournalError):
        blocks.restore_cache(destination, snapshot(b"different"))
    absent = tmp_path / "absent.json"
    assert blocks.snapshot_cache(absent) is None
    blocks.restore_cache(absent, None)
    assert not absent.exists()


@pytest.mark.parametrize("change", ["size", "sha256", "data", "encoding", "extra"])
def test_cache_corruption_rejected(tmp_path, change):
    captured = snapshot()
    captured[change] = {"size": 1, "sha256": "b" * 64, "data": "!!",
                        "encoding": "hex", "extra": "no"}[change]
    path = tmp_path / "new.json"
    with pytest.raises(blocks.JournalError):
        blocks.restore_cache(path, captured)
    assert not path.exists()


def test_partial_block_events_do_not_advance_or_replace_cache(tmp_path):
    journal = create(tmp_path)
    journal.record_block(entries(journal.expected_units[:2]))
    journal.record_event(journal.expected_units[2]["key"], "netem",
                         {"attempt": "partial", "tc": {"loss": "2%"}})
    interrupted_state = snapshot(b'{"dirty": true}')
    journal.record_event(journal.expected_units[3]["key"], "client_finished",
                         {"cache_after": interrupted_state})
    resumed = reopen(journal)
    assert resumed.next_index == 2
    assert len(resumed.events) == 2
    assert resumed.cache_after("M0.cell.t0.none") == snapshot()
    assert resumed.cache_after("M0.cell.t1.none") is None
    with pytest.raises(blocks.JournalError):
        resumed.record_event(journal.expected_units[0]["key"], "netem", {})
    resumed.record_block(entries(journal.expected_units[2:]))
    assert resumed.complete


def test_independent_trajectory_uses_distinct_cache(tmp_path):
    schedule = units(arms=("none",), count=1)
    other = copy.deepcopy(schedule[0])
    other.update(key="M0.cell.t1.p0.b0.none", trajectory=1, cache_key="M0.cell.t1.none")
    schedule.append(other)
    journal = create(tmp_path, schedule)
    journal.record(schedule[0]["key"], payload())
    assert journal.cache_after("M0.cell.t0.none") == snapshot()
    assert journal.cache_after("M0.cell.t1.none") is None


@pytest.mark.parametrize("corrupt", ["tail", "json", "empty", "digest", "duplicate", "sequence"])
def test_corrupt_journal_is_not_silently_skipped(tmp_path, corrupt):
    journal = create(tmp_path)
    journal.record_block(entries(journal.expected_units[:2]))
    original = journal.path.read_bytes()
    lines = original.splitlines(keepends=True)
    if corrupt == "tail":
        broken = original[:-1]
    elif corrupt == "json":
        broken = original + b"{broken}\n"
    elif corrupt == "empty":
        broken = b""
    elif corrupt == "digest":
        broken = original.replace(b'"ok":true', b'"ok":null', 1)
    elif corrupt == "duplicate":
        broken = original + lines[-1]
    else:
        value = json.loads(lines[-1])
        value["sequence"] = 99
        broken = lines[0] + rehash_record(value)
    journal.path.write_bytes(broken)
    with pytest.raises(blocks.JournalError):
        reopen(journal)
    assert journal.path.read_bytes() == broken


@pytest.mark.parametrize("field", ["identity", "fingerprint", "schedule"])
def test_resume_rejects_changed_identity_and_plan(tmp_path, field):
    journal = create(tmp_path)
    run_id = RUN_ID
    fp = FP
    schedule = journal.expected_units
    if field == "identity":
        run_id = "test"
    elif field == "fingerprint":
        fp = "b" * 64
    else:
        schedule[0]["rows_expected"] += 1
    with pytest.raises(blocks.JournalError):
        blocks.UnitJournal(journal.path, run_id, fp, schedule, resume=True)


def test_external_collection_validator_applies_on_write_and_resume(tmp_path):
    journal = create(tmp_path)
    journal.record_block(entries(journal.expected_units[:2]))

    def validator(unit, value):
        if value["server"].get("complete") is not True:
            raise blocks.JournalError("server collection incomplete")

    with pytest.raises(blocks.JournalError, match="server collection incomplete"):
        reopen(journal, validator=validator)
    journal.validator = validator
    with pytest.raises(blocks.JournalError, match="server collection incomplete"):
        journal.record_block(entries(journal.expected_units[2:]))
    assert journal.next_index == 2


def test_fsync_failure_never_publishes_completion(tmp_path, monkeypatch):
    journal = create(tmp_path)

    def fail(fd):
        raise OSError("fsync failure")

    monkeypatch.setattr(blocks.os, "fsync", fail)
    with pytest.raises(OSError, match="fsync failure"):
        journal.record_block(entries(journal.expected_units[:2]))
    assert journal.next_index == 0
    assert journal.records == []
    with pytest.raises(blocks.JournalError, match="reopen"):
        journal.record_block(entries(journal.expected_units[:2]))


def test_journal_detects_external_append(tmp_path):
    journal = create(tmp_path)
    with journal.path.open("ab") as stream:
        stream.write(b"{}\n")
    with pytest.raises(blocks.JournalError, match="changed"):
        journal.record_block(entries(journal.expected_units[:2]))


def test_fixed_arm_has_no_auto_cache(tmp_path):
    schedule = units(arms=("fixed",), count=1)
    schedule[0]["cache_key"] = None
    journal = create(tmp_path, schedule)
    data = payload()
    with pytest.raises(blocks.JournalError, match="fixed"):
        journal.record(schedule[0]["key"], data)
    data["cache_after"] = None
    journal.record(schedule[0]["key"], data)
    assert reopen(journal).complete


def test_fingerprint_ignores_env_paths_and_unrelated_files(tmp_path, monkeypatch):
    source = tmp_path / "experiments/v33"
    (source / "lib").mkdir(parents=True)
    (source / "devbed.py").write_text("runner = 1\n", encoding="utf-8")
    (source / "lib/blocks.py").write_text("blocks = 1\n", encoding="utf-8")
    (source / "devreport.py").write_text("report = 1\n", encoding="utf-8")
    (tmp_path / "experiments/padbed.py").write_text("padbed = 1\n", encoding="utf-8")
    (tmp_path / "experiments/gate_v3_parity.py").write_text("gate = 1\n", encoding="utf-8")
    binaries = {"gen33": {"path": "somewhere", "sha256": "1" * 64,
                           "srcsha": "2" * 64, "source": "label"},
                "g2": {"sha256": "3" * 64, "srcsha": "4" * 64}}
    original = blocks.fingerprint(tmp_path, "5" * 64, binaries)
    monkeypatch.setenv("PADFEC_X", "changed")
    (tmp_path / "experiments/unrelated.py").write_text("other = 1\n", encoding="utf-8")
    binaries["gen33"]["path"] = "another location"
    binaries["gen33"]["source"] = "another label"
    assert blocks.fingerprint(tmp_path, "5" * 64, binaries) == original
    (source / "devbed.py").write_text("runner = 2\n", encoding="utf-8")
    changed = blocks.fingerprint(tmp_path, "5" * 64, binaries)
    assert changed != original
    (source / "lib/blocks.py").write_text("blocks = 2\n", encoding="utf-8")
    changed_lib = blocks.fingerprint(tmp_path, "5" * 64, binaries)
    assert changed_lib != changed
    for name in ("experiments/v33/devreport.py", "experiments/padbed.py", "experiments/gate_v3_parity.py"):
        before = blocks.fingerprint(tmp_path, "5" * 64, binaries)
        (tmp_path / name).write_text("changed = 1\n", encoding="utf-8")
        assert blocks.fingerprint(tmp_path, "5" * 64, binaries) != before
    changed_lib = blocks.fingerprint(tmp_path, "5" * 64, binaries)
    binaries["gen33"]["sha256"] = "6" * 64
    assert blocks.fingerprint(tmp_path, "5" * 64, binaries) != changed_lib


def test_missing_fingerprint_inputs_fail(tmp_path):
    with pytest.raises(FileNotFoundError):
        blocks.fingerprint(tmp_path, "a" * 64, {"g2": {"sha256": "b" * 64, "srcsha": "c" * 64}})


def test_external_mutation_cannot_change_schedule_or_saved_payload(tmp_path):
    schedule = units()
    journal = create(tmp_path, schedule)
    schedule[0]["rows_expected"] = 10
    exposed = journal.expected_units
    exposed[0]["rows_expected"] = 20

    def mutating_validator(unit, value):
        unit["rows_expected"] = 30
        value["rows"].clear()

    journal.validator = mutating_validator
    batch = entries(journal.expected_units[:2])
    journal.record_block(batch)
    batch[0]["payload"]["rows"].clear()
    assert journal.expected_units[0]["rows_expected"] == 2
    assert len(journal.records[0]["payload"]["rows"]) == 2
    assert len(reopen(journal).records[0]["payload"]["rows"]) == 2


def measurement(tmp_path, **kwargs):
    options = {"task": "F26", "run_id": RUN_ID,
               "started_kst": "2026-11-06T21:00:00+09:00",
               "expected_end_kst": "2026-11-06T22:00:00+09:00", "heartbeat_s": 0.01}
    options.update(kwargs)
    return blocks.MeasurementLock(tmp_path / "MEASURE_LOCK.json",
                                  tmp_path / f"{RUN_ID}.status.json",
                                  tmp_path / f"{RUN_ID}.DONE", **options)


def live_status(owner):
    with owner._mutex:
        return json.loads(owner.status_file.read_bytes())


def wait_for(predicate, timeout=2):
    limit = time.monotonic() + timeout
    while time.monotonic() < limit:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition did not become true")


def test_measurement_constructor_has_no_filesystem_side_effect(tmp_path):
    measurement(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_measurement_heartbeat_runs_while_main_work_is_busy(tmp_path):
    owner = measurement(tmp_path).start()
    try:
        first = live_status(owner)["heartbeat"]
        wait_for(lambda: live_status(owner)["heartbeat"] != first)
        owner.check()
        record = json.loads(owner.lock_path.read_bytes())
        assert set(record) == {"task", "started_kst", "expected_end_kst", "wsl_pid",
                               "status_file", "done_marker"}
        assert record["task"] == "F26"
        owner.update(current_unit="cell.block.arm")
        assert live_status(owner)["current_unit"] == "cell.block.arm"
    finally:
        owner.close()
    assert owner.lock_path.exists()
    assert not owner.done_marker.exists()


def test_measurement_close_retains_lock_after_failure(tmp_path):
    owner = measurement(tmp_path).start()
    try:
        owner.update(state="failed", error="fixture failure")
    finally:
        owner.close()
    assert owner.lock_path.exists()
    status = json.loads(owner.status_file.read_bytes())
    assert status["state"] == "failed"
    assert status["run_id"] == RUN_ID


def test_measurement_done_persists_when_reporting_fails(tmp_path):
    owner = measurement(tmp_path).start()
    try:
        owner.mark_measurement_done()
        before = owner.done_marker.read_bytes()
        owner.update(report_error="fixture report error")
    finally:
        owner.close()
    assert owner.done_marker.read_bytes() == before
    assert owner.lock_path.exists()
    assert json.loads(owner.done_marker.read_bytes())["state"] == "DONE"


def test_only_report_success_releases_lock(tmp_path):
    owner = measurement(tmp_path).start()
    owner.mark_measurement_done()
    owner.finish_report_success()
    assert not owner.lock_path.exists()
    assert owner.done_marker.exists()
    assert json.loads(owner.status_file.read_bytes())["state"] == "complete"
    assert not list(tmp_path.glob("*.tmp"))
    with pytest.raises(blocks.JournalError, match="active"):
        owner.check()


def test_report_success_without_done_is_rejected(tmp_path):
    owner = measurement(tmp_path).start()
    with pytest.raises(FileNotFoundError):
        owner.finish_report_success()
    assert owner.lock_path.exists()


def test_new_measurement_rejects_colliding_status(tmp_path):
    owner = measurement(tmp_path).start()
    owner.close()
    before = owner.status_file.read_bytes()
    with pytest.raises(FileExistsError):
        measurement(tmp_path).start()
    assert owner.status_file.read_bytes() == before


def test_existing_lock_cannot_be_taken_by_same_process(tmp_path):
    owner = measurement(tmp_path).start()
    owner.mark_measurement_done()
    owner.close()
    with pytest.raises(blocks.JournalError, match="still alive"):
        measurement(tmp_path, resume=True).start()
    assert owner.lock_path.exists()


def test_resume_after_supervisor_removes_dead_lock_keeps_identity(tmp_path):
    owner = measurement(tmp_path).start()
    owner.update(current_unit="interrupted")
    owner.close()
    owner.lock_path.unlink()
    resumed = measurement(tmp_path, resume=True,
                          started_kst="2026-11-06T21:10:00+09:00").start()
    try:
        status = live_status(resumed)
        assert status["started_kst"] == "2026-11-06T21:00:00+09:00"
        assert status["run_id"] == RUN_ID
        assert status["current_unit"] == "interrupted"
        assert status["state"] == "measuring"
    finally:
        resumed.close()


def test_dead_incomplete_lock_requires_supervisor_cleanup(tmp_path, monkeypatch):
    owner = measurement(tmp_path).start()
    owner.close()
    monkeypatch.setattr(blocks, "_process_alive", lambda pid: False)
    with pytest.raises(blocks.JournalError, match="supervisor"):
        measurement(tmp_path, resume=True).start()
    assert owner.lock_path.exists()


def test_report_recovery_checks_identity_and_preserves_done(tmp_path, monkeypatch):
    owner = measurement(tmp_path).start()
    owner.mark_measurement_done()
    owner.close()
    before = owner.done_marker.read_bytes()
    monkeypatch.setattr(blocks, "_process_alive", lambda pid: False)
    recovered = measurement(tmp_path, resume=True).start()
    recovered.finish_report_success()
    assert recovered.done_marker.read_bytes() == before
    assert not recovered.lock_path.exists()


@pytest.mark.parametrize("which", ["status", "marker", "lock"])
def test_recovery_rejects_foreign_identity(tmp_path, monkeypatch, which):
    owner = measurement(tmp_path).start()
    owner.mark_measurement_done()
    owner.close()
    monkeypatch.setattr(blocks, "_process_alive", lambda pid: False)
    path = {"status": owner.status_file, "marker": owner.done_marker,
            "lock": owner.lock_path}[which]
    value = json.loads(path.read_bytes())
    value["task"] = "F27"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(blocks.JournalError):
        measurement(tmp_path, resume=True).start()
    assert owner.lock_path.exists()


def test_heartbeat_failure_reaches_main_and_keeps_lock(tmp_path, monkeypatch):
    owner = measurement(tmp_path).start()
    original = blocks._atomic_json
    failed = threading.Event()

    def fail_status(path, value, **kwargs):
        if Path(path) == owner.status_file:
            failed.set()
            raise OSError("fixture disk error")
        return original(path, value, **kwargs)

    monkeypatch.setattr(blocks, "_atomic_json", fail_status)
    try:
        assert failed.wait(timeout=2)
        wait_for(lambda: owner._thread_error is not None)
        with pytest.raises(blocks.JournalError, match="heartbeat failed"):
            owner.check()
    finally:
        owner.close()
    assert owner.lock_path.exists()


def test_status_creation_failure_retains_owned_lock(tmp_path, monkeypatch):
    owner = measurement(tmp_path)
    original = blocks._atomic_json

    def fail_status(path, value, **kwargs):
        if Path(path) == owner.status_file:
            raise OSError("fixture status failure")
        return original(path, value, **kwargs)

    monkeypatch.setattr(blocks, "_atomic_json", fail_status)
    with pytest.raises(OSError, match="status failure"):
        owner.start()
    owner.close()
    assert owner.lock_path.exists()
    assert not owner.status_file.exists()


def test_foreign_lock_is_never_released(tmp_path):
    owner = measurement(tmp_path).start()
    owner.mark_measurement_done()
    owner.close()
    data = json.loads(owner.lock_path.read_bytes())
    data["task"] = "F27"
    owner.lock_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(blocks.JournalError, match="ownership"):
        owner.finish_report_success()
    assert json.loads(owner.lock_path.read_bytes())["task"] == "F27"


def test_identity_fields_cannot_be_mutated_by_status_update(tmp_path):
    owner = measurement(tmp_path).start()
    try:
        with pytest.raises(blocks.JournalError, match="identity"):
            owner.update(run_id="another")
        owner.check()
    finally:
        owner.close()


def test_atomic_json_retries_transient_replace_denial(tmp_path, monkeypatch):
    original = blocks.os.replace
    calls = []

    def deny_once(source, target):
        calls.append(target)
        if len(calls) == 1:
            raise PermissionError(13, "fixture sharing violation")
        return original(source, target)

    monkeypatch.setattr(blocks, "_REPLACE_RETRY_S", 1)
    monkeypatch.setattr(blocks.os, "replace", deny_once)
    path = tmp_path / "status.json"
    blocks._atomic_json(path, {"ok": True})
    assert len(calls) == 2
    assert json.loads(path.read_bytes()) == {"ok": True}
    assert not list(tmp_path.glob("*.tmp"))


def test_atomic_json_raises_after_retry_budget(tmp_path, monkeypatch):
    calls = []

    def deny(source, target):
        calls.append(target)
        raise PermissionError(13, "fixture sharing violation")

    monkeypatch.setattr(blocks, "_REPLACE_RETRY_S", 0)
    monkeypatch.setattr(blocks.os, "replace", deny)
    with pytest.raises(PermissionError):
        blocks._atomic_json(tmp_path / "status.json", {"ok": True})
    assert len(calls) == 1
    assert not list(tmp_path.glob("*.tmp"))
