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
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    # torn final line from an interrupted write: drop it
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
        self._done[key] = val
        line = json.dumps({"fp": self.fingerprint, "key": key, "val": val},
                          ensure_ascii=False)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())

    def reset(self):
        self._done = {}
        if os.path.exists(self.path):
            os.remove(self.path)


def atomic_write_json(path, obj):
    """Write JSON so a crash mid-write cannot leave a half file behind."""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def code_fingerprint(paths, root=None):
    """Hash the source files that actually produce the results.

    A journal keyed only on experiment PARAMETERS is a trap: fix a bug in the
    measurement code, rerun with the same parameters, and the journal happily
    serves the results the broken code produced.  That is exactly how a
    resumable pipeline gets into a state nobody can explain.  Mixing the code
    hash into the fingerprint makes stale units invisible instead.
    """
    import hashlib
    import os
    h = hashlib.sha256()
    for rel in sorted(paths):
        full = os.path.join(root, rel) if root else rel
        h.update(rel.encode())
        try:
            with open(full, "rb") as f:
                h.update(hashlib.sha256(f.read()).digest())
        except OSError:
            h.update(b"MISSING")
    return h.hexdigest()[:12]
