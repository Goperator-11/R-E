import json
import os
import hashlib
import platform
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone


class Journal(object):
    def __init__(self, path, fingerprint=""):
        self.path = path
        self.fingerprint = fingerprint
        self.run_id = uuid.uuid4().hex
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        self._done = {}
        self._metadata = {}
        self._used = set()
        self._load()

    def _load(self):
        if not os.path.exists(self.path):
            return
        good = []
        with open(self.path, "rb") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    continue
                if not isinstance(rec, dict) or not isinstance(rec.get("key"), str):
                    continue
                if rec.get("fp") != self.fingerprint:
                    continue
                good.append(rec)
        for rec in good:
            self._done[rec["key"]] = rec.get("val")
            self._metadata[rec["key"]] = {
                "recorded_at": rec.get("recorded_at"),
                "run_id": rec.get("run_id"),
            }

    def has(self, key):
        return key in self._done

    def get(self, key, default=None):
        if key in self._done:
            self._used.add(key)
        return self._done.get(key, default)

    def keys(self):
        return set(self._done)

    def items(self):
        self._used.update(self._done)
        return dict(self._done)

    def provenance(self, keys=None):
        selected = sorted(self._used if keys is None else set(keys))
        units = []
        for key in selected:
            if key not in self._done:
                raise KeyError(key)
            meta = self._metadata[key]
            units.append(dict(meta, key=key,
                              reused=meta.get("run_id") != self.run_id))
        return {"schema_version": 1, "fingerprint": self.fingerprint,
                "current_run_id": self.run_id, "units": units,
                "used_units": len(units),
                "reused_units": sum(u["reused"] for u in units),
                "unknown_recording_time_units": sum(
                    not u.get("recorded_at") for u in units),
                "note": "Recording times are not measurement intervals; run IDs are not independent replicates."}

    def __len__(self):
        return len(self._done)

    def record(self, key, val):
        if not isinstance(key, str):
            raise TypeError("journal keys must be strings")
        meta = {"recorded_at": datetime.now(timezone.utc).isoformat(),
                "run_id": self.run_id}
        line = json.dumps(dict(meta, fp=self.fingerprint, key=key, val=val),
                          ensure_ascii=False)
        with open(self.path, "a+b") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size:
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b"\n":
                    f.write(b"\n")
            f.write((line + "\n").encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        self._done[key] = val
        self._metadata[key] = meta
        self._used.add(key)

    def reset(self):
        self._done = {}
        self._metadata = {}
        self._used = set()
        if os.path.exists(self.path):
            os.remove(self.path)


def atomic_write_json(path, obj, indent=2, default=None, before_replace=None):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=indent, ensure_ascii=False, default=default)
            f.flush()
            os.fsync(f.fileno())
        if before_replace is not None:
            before_replace()
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def save_result(path, obj, indent=1, backup_dir=None, default=None):
    def preserve():
        if not os.path.isfile(path):
            return
        archive = backup_dir or os.path.join(os.path.dirname(path), "..", "state", "backup")
        os.makedirs(archive, exist_ok=True)
        fd, previous = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".json",
                                         dir=archive)
        os.close(fd)
        shutil.copy2(path, previous)

    atomic_write_json(path, obj, indent=indent, default=default, before_replace=preserve)
    return path


def runtime_context():
    try:
        affinity = sorted(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        affinity = None
    return {"python": sys.version, "executable": sys.executable,
            "platform": platform.platform(), "machine": platform.machine(),
            "cpu_count": os.cpu_count(), "affinity": affinity,
            "padfec_env": {k: v for k, v in sorted(os.environ.items())
                           if k.startswith("PADFEC_")}}


def code_fingerprint(paths, root=None):
    h = hashlib.sha256()
    paths = set(paths)
    if root:
        for subdir, suffixes in (("experiments", (".py",)),
                                ("experiments/quicbed", (".go", ".sh", ".mod", ".sum")),
                                ("afec", (".py",)), ("padfec", (".py",))):
            directory = os.path.join(root, subdir)
            if os.path.isdir(directory):
                paths.update(subdir + "/" + name for name in os.listdir(directory)
                             if name.endswith(suffixes))
    h.update(json.dumps(runtime_context(), sort_keys=True).encode())
    for rel in sorted(paths):
        full = os.path.join(root, rel) if root else rel
        h.update(rel.encode())
        try:
            with open(full, "rb") as f:
                h.update(hashlib.sha256(f.read()).digest())
        except OSError:
            h.update(b"MISSING")
    return h.hexdigest()[:12]
