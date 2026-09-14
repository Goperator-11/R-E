# -*- coding: utf-8 -*-
"""
Append-only unit journal - lets a long sweep resume in the middle.

The pipeline can restart a whole stage, but some stages take 10-30 minutes
(the netem sweep, the policy evaluation, the live QUIC testbed).  Re-running
those from scratch after an interruption wastes most of the work, so each of
them records every finished unit here and skips units it already has.

Design rules that make this safe to interrupt at ANY point:
  * append-only JSONL - a torn last line is discarded on load, never merged
  * one line = one completed unit, written and flushed atomically enough that
    a crash can only lose the line in flight, not corrupt earlier ones
  * the key is a stable string derived from the unit's parameters, so a rerun
    with different parameters does not silently reuse old results
  * a `fingerprint` field records the experiment parameters; if they change,
    load() ignores the old lines instead of mixing two configurations

Standard library only.  ASCII console output.
"""
import json
import os
import hashlib
import platform
import shutil
import sys
import tempfile


class Journal(object):
    def __init__(self, path, fingerprint=""):
        self.path = path
        self.fingerprint = fingerprint
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        self._done = {}
        self._load()

    # ------------------------------------------------------------ loading
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
                    # torn final line from an interrupted write: drop it
                    continue
                if not isinstance(rec, dict) or not isinstance(rec.get("key"), str):
                    continue
                if rec.get("fp") != self.fingerprint:
                    continue
                good.append(rec)
        for rec in good:
            self._done[rec["key"]] = rec.get("val")

    # ------------------------------------------------------------- access
    def has(self, key):
        return key in self._done

    def get(self, key, default=None):
        return self._done.get(key, default)

    def keys(self):
        return set(self._done)

    def items(self):
        return dict(self._done)

    def __len__(self):
        return len(self._done)

    # -------------------------------------------------------------- write
    def record(self, key, val):
        if not isinstance(key, str):
            raise TypeError("journal keys must be strings")
        line = json.dumps({"fp": self.fingerprint, "key": key, "val": val},
                          ensure_ascii=False)
        # Preserve a torn tail, but separate it from the next complete record.
        # Publish the in-memory completion only after the durable append succeeds.
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

    def reset(self):
        self._done = {}
        if os.path.exists(self.path):
            os.remove(self.path)


def atomic_write_json(path, obj, indent=2, default=None, before_replace=None):
    """Write JSON so a crash mid-write cannot leave a half file behind."""
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
    """Retain an existing result, then replace it atomically. Never prune raw data."""
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
    """Stable run settings, excluding changing load and timestamps."""
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
    """Hash the source files that actually produce the results.

    A journal keyed only on experiment PARAMETERS is a trap: fix a bug in the
    measurement code, rerun with the same parameters, and the journal happily
    serves the results the broken code produced.  That is exactly how a
    resumable pipeline gets into a state nobody can explain.  Mixing the code
    hash into the fingerprint makes stale units invisible instead.
    """
    h = hashlib.sha256()
    # Handwritten dependency lists used to miss shared measurement helpers and
    # generated Go code. A conservative source closure prevents stale reuse.
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
