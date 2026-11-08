import base64
import binascii
import copy
import hashlib
import json
import os
import re
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


class JournalError(ValueError):
    pass


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _hex(value, field):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise JournalError(f"invalid {field}")
    return value


def fingerprint(root, plan_sha256, binaries):
    root = Path(root)
    files = [root / "experiments/v33/devbed.py", root / "experiments/v33/devreport.py",
             root / "experiments/padbed.py", root / "experiments/gate_v3_parity.py"]
    files.extend(sorted((root / "experiments/v33/lib").glob("*.py")))
    source = {path.relative_to(root).as_posix():
              hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    identities = {}
    for name, binary in sorted(binaries.items()):
        identities[name] = {field: _hex(binary.get(field), f"{name}.{field}")
                            for field in ("sha256", "srcsha")}
    if not identities:
        raise JournalError("binary identities are empty")
    return _digest({"plan_sha256": _hex(plan_sha256, "plan_sha256"),
                    "binaries": identities, "source": source})


def cache_key(unit):
    value = unit.get("cache_key")
    if value is not None and (not isinstance(value, str) or not value):
        raise JournalError("invalid cache key")
    return value


def snapshot_cache(path):
    path = Path(path)
    if not path.exists():
        return None
    raw = path.read_bytes()
    return {"encoding": "base64", "data": base64.b64encode(raw).decode("ascii"),
            "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}


def _snapshot_bytes(snapshot):
    if snapshot is None:
        return None
    if not isinstance(snapshot, dict) or set(snapshot) != {
            "encoding", "data", "sha256", "size"}:
        raise JournalError("invalid cache snapshot")
    if snapshot["encoding"] != "base64" or not isinstance(snapshot["data"], str):
        raise JournalError("invalid cache encoding")
    try:
        raw = base64.b64decode(snapshot["data"], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise JournalError("invalid cache data") from exc
    if type(snapshot["size"]) is not int or snapshot["size"] != len(raw):
        raise JournalError("cache size mismatch")
    if _hex(snapshot["sha256"], "cache sha256") != hashlib.sha256(raw).hexdigest():
        raise JournalError("cache digest mismatch")
    return raw


def snapshot_bytes(snapshot):
    return _snapshot_bytes(snapshot)


def restore_cache(path, snapshot):
    path = Path(path)
    raw = _snapshot_bytes(snapshot)
    if path.exists():
        if raw is None or path.read_bytes() != raw:
            raise JournalError("cache destination already contains different state")
        return
    if raw is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())


def _datetime(value):
    if not isinstance(value, str):
        raise JournalError("unit timestamp is missing")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise JournalError("invalid unit timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise JournalError("unit timestamp must include timezone")
    return parsed


def _block_key(unit):
    return tuple(unit[field] for field in ("task", "cell", "trajectory", "phase", "block"))


def _validate_units(units):
    units = copy.deepcopy(list(units))
    if not units:
        raise JournalError("unit schedule is empty")
    keys = set()
    closed_blocks = set()
    previous = None
    for unit in units:
        if not isinstance(unit, dict):
            raise JournalError("invalid scheduled unit")
        key = unit.get("key")
        if not isinstance(key, str) or not key or key in keys:
            raise JournalError("missing or duplicate scheduled key")
        keys.add(key)
        if type(unit.get("rows_expected")) is not int or unit["rows_expected"] < 1:
            raise JournalError("invalid expected row count")
        cache_key(unit)
        try:
            block = _block_key(unit)
            hash(block)
        except (KeyError, TypeError) as exc:
            raise JournalError("missing or invalid block identity") from exc
        if previous != block:
            if block in closed_blocks:
                raise JournalError("noncontiguous scheduled block")
            closed_blocks.add(block)
            previous = block
    _json_bytes(units)
    return units


def _object_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise JournalError("duplicate JSON object key")
        value[key] = item
    return value


def _bad_constant(value):
    raise JournalError(f"invalid JSON constant: {value}")


class UnitJournal:
    def __init__(self, path, run_id, fingerprint, expected_units, *, metadata=None,
                 resume=False, validator=None):
        self.path = Path(path)
        if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", run_id):
            raise JournalError("invalid run ID")
        if run_id not in self.path.name:
            raise JournalError("journal filename must contain run ID")
        self.run_id = run_id
        self.fingerprint = _hex(fingerprint, "fingerprint")
        self._expected_units = _validate_units(expected_units)
        self.schedule_sha256 = _digest(self._expected_units)
        self._metadata = {}
        self._records = []
        self._events = []
        self._next_index = 0
        self._sequence = 0
        self._previous_sha256 = "0" * 64
        self._size = 0
        self.validator = validator
        self._poisoned = False
        if resume:
            self._load()
        else:
            if not isinstance(metadata, dict):
                raise JournalError("new journal requires metadata")
            self._metadata = copy.deepcopy(metadata)
            header = self._envelope("header", {"schema": "padfec3.devbed.journal/1",
                                               "schedule_sha256": self.schedule_sha256,
                                               "metadata": self._metadata})
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("xb") as stream:
                self._write(stream, header)

    @property
    def metadata(self):
        return copy.deepcopy(self._metadata)

    @property
    def expected_units(self):
        return copy.deepcopy(self._expected_units)

    @property
    def records(self):
        return copy.deepcopy(self._records)

    @property
    def events(self):
        return copy.deepcopy(self._events)

    @property
    def next_index(self):
        return self._next_index

    @property
    def complete(self):
        return self._next_index == len(self._expected_units)

    def _current_block(self):
        if self.complete:
            return []
        first = _block_key(self._expected_units[self._next_index])
        units = []
        for unit in self._expected_units[self._next_index:]:
            if _block_key(unit) != first:
                break
            units.append(unit)
        return units

    def _envelope(self, kind, data):
        record = {"kind": kind, "run_id": self.run_id,
                  "fingerprint": self.fingerprint, "sequence": self._sequence,
                  "previous_sha256": self._previous_sha256, "data": data}
        record["record_sha256"] = _digest(record)
        return record

    def _write(self, stream, record):
        line = _json_bytes(record) + b"\n"
        stream.write(line)
        stream.flush()
        os.fsync(stream.fileno())
        self._size += len(line)
        self._sequence += 1
        self._previous_sha256 = record["record_sha256"]

    def _append(self, kind, data):
        if self._poisoned:
            raise JournalError("journal write failed; reopen before continuing")
        record = self._envelope(kind, data)
        try:
            with self.path.open("r+b") as stream:
                stream.seek(0, os.SEEK_END)
                if stream.tell() != self._size:
                    raise JournalError("journal changed since it was opened")
                self._write(stream, record)
        except BaseException:
            self._poisoned = True
            raise

    def _validate_payload(self, unit, payload):
        if not isinstance(payload, dict):
            raise JournalError("invalid completed unit")
        rows = payload.get("rows")
        if not isinstance(rows, list) or len(rows) != unit["rows_expected"]:
            raise JournalError("completed unit row count mismatch")
        if not all(isinstance(row, dict) for row in rows):
            raise JournalError("invalid client row")
        if _datetime(payload.get("ended_at")) < _datetime(payload.get("started_at")):
            raise JournalError("unit end precedes start")
        if not isinstance(payload.get("server"), dict) or not payload["server"]:
            raise JournalError("server collection is missing")
        if "cache_after" not in payload:
            raise JournalError("cache snapshot field is missing")
        snapshot = payload["cache_after"]
        _snapshot_bytes(snapshot)
        if cache_key(unit) is not None and snapshot is None:
            raise JournalError("completed auto unit cache is missing")
        if cache_key(unit) is None and snapshot is not None:
            raise JournalError("fixed unit cannot have an auto cache")
        if self.validator is not None:
            self.validator(copy.deepcopy(unit), copy.deepcopy(payload))
        _json_bytes(payload)

    def _validate_block(self, entries):
        expected = self._current_block()
        if not expected or not isinstance(entries, list) or len(entries) != len(expected):
            raise JournalError("completed block is missing scheduled arms")
        for unit, entry in zip(expected, entries):
            if not isinstance(entry, dict) or set(entry) != {"key", "payload"}:
                raise JournalError("invalid block entry")
            if entry["key"] != unit["key"]:
                raise JournalError("completed block is out of order")
            self._validate_payload(unit, entry["payload"])

    def record_block(self, entries):
        entries = copy.deepcopy(entries)
        self._validate_block(entries)
        self._append("block", {"units": entries})
        self._records.extend(entries)
        self._next_index += len(entries)

    def record(self, key, payload):
        if len(self._current_block()) != 1:
            raise JournalError("use record_block for a block with multiple arms")
        self.record_block([{"key": key, "payload": payload}])

    def record_event(self, key, event, data):
        if key not in {unit["key"] for unit in self._current_block()}:
            raise JournalError("event does not belong to the current block")
        if not isinstance(event, str) or not event or not isinstance(data, dict):
            raise JournalError("invalid journal event")
        value = {"key": key, "event": event, "data": copy.deepcopy(data),
                 "recorded_at": datetime.now(timezone.utc).isoformat()}
        self._append("event", value)
        self._events.append(value)

    def cache_after(self, key):
        for unit, record in reversed(list(zip(self._expected_units, self._records))):
            if cache_key(unit) == key:
                return copy.deepcopy(record["payload"]["cache_after"])
        return None

    def _load(self):
        raw = self.path.read_bytes()
        if not raw or not raw.endswith(b"\n"):
            raise JournalError("journal is empty or has a truncated tail")
        for number, line in enumerate(raw.splitlines(), 1):
            try:
                record = json.loads(line.decode("utf-8"), object_pairs_hook=_object_pairs,
                                    parse_constant=_bad_constant)
            except (ValueError, UnicodeDecodeError) as exc:
                raise JournalError(f"invalid journal line {number}: {exc}") from exc
            if not isinstance(record, dict) or set(record) != {
                    "kind", "run_id", "fingerprint", "sequence", "previous_sha256",
                    "data", "record_sha256"}:
                raise JournalError(f"invalid journal record at line {number}")
            digest = record.pop("record_sha256")
            if _digest(record) != digest:
                raise JournalError(f"journal digest mismatch at line {number}")
            if record["run_id"] != self.run_id or record["fingerprint"] != self.fingerprint:
                raise JournalError("journal identity or fingerprint mismatch")
            if type(record["sequence"]) is not int or record["sequence"] != self._sequence:
                raise JournalError("journal sequence mismatch")
            if record["previous_sha256"] != self._previous_sha256:
                raise JournalError("journal digest chain mismatch")
            data = record["data"]
            if not isinstance(data, dict):
                raise JournalError("invalid journal data")
            kind = record["kind"]
            if number == 1:
                if kind != "header" or data.get("schema") != "padfec3.devbed.journal/1":
                    raise JournalError("journal header is missing")
                if data.get("schedule_sha256") != self.schedule_sha256:
                    raise JournalError("journal schedule mismatch")
                if not isinstance(data.get("metadata"), dict):
                    raise JournalError("journal metadata is missing")
                self._metadata = data["metadata"]
            elif kind == "block":
                entries = data.get("units")
                self._validate_block(entries)
                self._records.extend(entries)
                self._next_index += len(entries)
            elif kind == "event":
                if data.get("key") not in {unit["key"] for unit in self._current_block()}:
                    raise JournalError("event does not belong to current block")
                if not isinstance(data.get("event"), str) or not data["event"]:
                    raise JournalError("invalid event name")
                if not isinstance(data.get("data"), dict):
                    raise JournalError("invalid event data")
                _datetime(data.get("recorded_at"))
                self._events.append(data)
            else:
                raise JournalError("unexpected journal record kind")
            self._sequence += 1
            self._previous_sha256 = digest
        self._size = len(raw)


def _read_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"),
                           object_pairs_hook=_object_pairs, parse_constant=_bad_constant)
    except (ValueError, UnicodeDecodeError) as exc:
        raise JournalError(f"invalid JSON file: {path}") from exc
    if not isinstance(value, dict):
        raise JournalError(f"JSON object required: {path}")
    return value


_REPLACE_RETRY_S = 2 if os.name == "nt" else 0


def _replace(source, target):
    limit = time.monotonic() + _REPLACE_RETRY_S
    while True:
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if time.monotonic() >= limit:
                raise
            time.sleep(0.01)


def _atomic_json(path, value, *, exclusive=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp",
                                             dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_json_bytes(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            os.link(temporary, path)
        else:
            _replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _process_alive(pid):
    if type(pid) is not int or pid <= 0:
        raise JournalError("invalid measurement PID")
    if pid == os.getpid():
        return True
    if os.name != "posix":
        raise JournalError("measurement PID liveness must be checked inside WSL")
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _kst(value=None):
    zone = timezone(timedelta(hours=9))
    if value is None:
        return datetime.now(zone).isoformat(timespec="seconds")
    if not isinstance(value, str):
        raise JournalError("invalid KST timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise JournalError("invalid KST timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    return parsed.astimezone(zone).isoformat(timespec="seconds")


class MeasurementLock:
    _LOCK_KEYS = {"task", "started_kst", "expected_end_kst", "wsl_pid",
                  "status_file", "done_marker"}
    _STATUS_KEYS = _LOCK_KEYS | {"run_id", "lock_file", "heartbeat"}

    def __init__(self, lock_path, status_file, done_marker, *, task, run_id,
                 expected_end_kst, started_kst=None, heartbeat_s=5, resume=False):
        self.lock_path = Path(lock_path).resolve()
        self.status_file = Path(status_file).resolve()
        self.done_marker = Path(done_marker).resolve()
        if len({self.lock_path, self.status_file, self.done_marker}) != 3:
            raise JournalError("measurement paths must be distinct")
        for value in (task, run_id):
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", value):
                raise JournalError("invalid measurement identity")
        if not 0 < heartbeat_s < 15:
            raise JournalError("heartbeat interval must be between 0 and 15 seconds")
        self.task = task
        self.run_id = run_id
        self.started_kst = _kst(started_kst)
        self.expected_end_kst = _kst(expected_end_kst)
        self.heartbeat_s = heartbeat_s
        self.resume = resume
        self._state = {}
        self._lock_data = None
        self._thread = None
        self._stop = threading.Event()
        self._mutex = threading.RLock()
        self._thread_error = None
        self._started = False
        self._closed = False
        self._released = False

    def _identity(self):
        return {"task": self.task, "run_id": self.run_id,
                "lock_file": str(self.lock_path), "status_file": str(self.status_file),
                "done_marker": str(self.done_marker)}

    def _validate_status(self, value):
        if any(value.get(key) != item for key, item in self._identity().items()):
            raise JournalError("measurement status identity mismatch")
        _datetime(value.get("heartbeat"))
        _datetime(value.get("started_kst"))
        _datetime(value.get("expected_end_kst"))
        if type(value.get("wsl_pid")) is not int or value["wsl_pid"] <= 0:
            raise JournalError("invalid status PID")

    def _validate_marker(self):
        value = _read_json(self.done_marker)
        expected = {"task": self.task, "run_id": self.run_id, "state": "DONE",
                    "status_file": str(self.status_file)}
        if any(value.get(key) != item for key, item in expected.items()):
            raise JournalError("measurement DONE identity mismatch")
        _datetime(value.get("completed_at"))
        return value

    def _validate_owned_lock(self):
        value = _read_json(self.lock_path)
        if value != self._lock_data:
            raise JournalError("measurement lock ownership changed")

    def _write_status(self, *, exclusive=False):
        value = dict(self._state)
        value.update(self._lock_data)
        value.update(self._identity())
        value["heartbeat"] = datetime.now(timezone.utc).isoformat()
        _atomic_json(self.status_file, value, exclusive=exclusive)

    def start(self):
        if self._started or self._closed:
            raise JournalError("measurement lock cannot be started twice")
        previous_lock = None
        if self.resume:
            prior = _read_json(self.status_file)
            self._validate_status(prior)
            self.started_kst = _kst(prior["started_kst"])
            self._state = {key: value for key, value in prior.items()
                           if key not in self._STATUS_KEYS}
            if self.done_marker.exists():
                self._validate_marker()
            if self.lock_path.exists():
                previous_lock = _read_json(self.lock_path)
                if set(previous_lock) != self._LOCK_KEYS:
                    raise JournalError("invalid measurement lock keys")
                if any(previous_lock[key] != prior[key] for key in self._LOCK_KEYS):
                    raise JournalError("measurement lock and status disagree")
                if _process_alive(previous_lock["wsl_pid"]):
                    raise JournalError("measurement process is still alive")
                if not self.done_marker.exists():
                    raise JournalError("unfinished lock must be removed by the supervisor")
        else:
            if self.status_file.exists() or self.done_marker.exists():
                raise FileExistsError("measurement status or DONE already exists")
        if _datetime(self.expected_end_kst) < _datetime(self.started_kst):
            raise JournalError("expected end precedes measurement start")
        self._lock_data = {"task": self.task, "started_kst": self.started_kst,
                           "expected_end_kst": self.expected_end_kst, "wsl_pid": os.getpid(),
                           "status_file": str(self.status_file), "done_marker": str(self.done_marker)}
        if previous_lock is None:
            _atomic_json(self.lock_path, self._lock_data, exclusive=True)
        else:
            if _read_json(self.lock_path) != previous_lock:
                raise JournalError("measurement lock changed during recovery")
            _atomic_json(self.lock_path, self._lock_data)
        self._state["state"] = "reporting" if self.done_marker.exists() else "measuring"
        self._state.pop("last_error", None)
        self._write_status(exclusive=not self.resume)
        self._started = True
        self._thread = threading.Thread(target=self._heartbeat, name="devbed-heartbeat", daemon=True)
        self._thread.start()
        return self

    def _heartbeat(self):
        while not self._stop.wait(self.heartbeat_s):
            try:
                with self._mutex:
                    self._validate_owned_lock()
                    self._write_status()
            except BaseException as exc:
                self._thread_error = exc
                with self._mutex:
                    self._state["last_error"] = f"{type(exc).__name__}: {exc}"
                    try:
                        self._validate_owned_lock()
                        self._write_status()
                    except BaseException:
                        pass
                self._stop.set()

    def check(self):
        if self._thread_error is not None:
            raise JournalError(f"measurement heartbeat failed: {self._thread_error}") from self._thread_error
        if not self._started or self._released:
            raise JournalError("measurement lock is not active")
        self._validate_owned_lock()

    def update(self, **fields):
        if self._STATUS_KEYS.intersection(fields):
            raise JournalError("measurement identity fields cannot be updated")
        with self._mutex:
            self.check()
            self._state.update(copy.deepcopy(fields))
            self._write_status()

    def mark_measurement_done(self):
        with self._mutex:
            self.check()
            if self.done_marker.exists():
                self._validate_marker()
            else:
                _atomic_json(self.done_marker,
                             {"task": self.task, "run_id": self.run_id, "state": "DONE",
                              "status_file": str(self.status_file),
                              "completed_at": datetime.now(timezone.utc).isoformat()}, exclusive=True)
            self._state["state"] = "reporting"
            self._write_status()

    def finish_report_success(self):
        self.close()
        with self._mutex:
            self.check()
            self._validate_status(_read_json(self.status_file))
            self._validate_marker()
            self._state["state"] = "complete"
            self._write_status()
            self._validate_owned_lock()
            self.lock_path.unlink()
            self._released = True

    def close(self):
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=15)
            if self._thread.is_alive():
                raise JournalError("measurement heartbeat did not stop")
        self._closed = True
