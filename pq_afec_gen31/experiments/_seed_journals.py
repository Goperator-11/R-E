# -*- coding: utf-8 -*-
"""
One-off migration: rebuild the E7 / E12 unit journals under the NEW fingerprint.

Why this exists.  The journals originally keyed only on experiment parameters.
That is unsafe - fix a bug in the measurement code, rerun with the same
parameters, and the journal serves results the broken code produced.  So the
fingerprint now mixes in a hash of the source files that actually do the
measuring (see _journal.code_fingerprint).

Changing the fingerprint invalidates every existing journal entry, which would
force a full re-measurement.  For E7 and E12 that is unnecessary: their
MEASUREMENT code did not change, only the bookkeeping around it.  So we replay
the finished results out of their result JSON into a journal stamped with the
new fingerprint.  E13 is deliberately NOT seeded - its shim really did change
(the symbol length framing bug), so those units must be measured again.

Run once:  python experiments/_seed_journals.py
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from _journal import Journal, code_fingerprint       # noqa: E402

RESULTS = os.path.join(HERE, "results")
STATE = os.path.join(HERE, "state")


def seed_e7():
    p = os.path.join(RESULTS, "e7_policy.json")
    if not os.path.exists(p):
        return "e7: no results"
    d = json.load(open(p, encoding="utf-8"))
    fp = hashlib.sha256(json.dumps(
        {"seeds": d["seeds"], "rtt": d["rtt_ms"], "rate": d["rate_mbps"],
         "budget": 20.0, "wrong": 5.0, "long": 400, "short": 30,
         "trials": 10000, "n": d["n_trace"],
         "code": code_fingerprint(
             ["afec/sim.py", "afec/controller.py", "afec/estimator.py",
              "afec/channel.py", "afec/cache.py"], root=ROOT)},
        sort_keys=True).encode()).hexdigest()[:16]
    jr = Journal(os.path.join(STATE, "e7_units.jsonl"), fingerprint=fp)
    n = 0
    for span in ("long", "short"):
        for name, rec in d[span].items():
            key = "pol/%s/%s" % (span, name)
            if not jr.has(key):
                jr.record(key, rec)
                n += 1
    for name, h in (d.get("handshake") or {}).items():
        key = "hs/%s" % name
        if jr.has(key):
            continue
        row = dict(h)
        row["name"] = name
        row["p"] = d["long"][name]["measured_loss"]
        row["L"] = max(d["long"][name]["measured_burst"], 1.0)
        jr.record(key, row)
        n += 1
    return "e7: %d units seeded (fp=%s, total %d)" % (n, fp, len(jr))


def seed_e12():
    p = os.path.join(RESULTS, "e12_quic_testbed.json")
    if not os.path.exists(p):
        return "e12: no results"
    d = json.load(open(p, encoding="utf-8"))
    fp = hashlib.sha256(json.dumps(
        {"mtu": d["mtu"], "rtt": d["rtt_ms"], "cert": d["certsize"],
         "n": d["n"], "flight_ms": d["flight_ms"], "gap": 15.0,
         "code": code_fingerprint(
             ["experiments/quicbed/shim.py", "experiments/quicbed/client.go",
              "experiments/quicbed/server.go"], root=ROOT)},
        sort_keys=True).encode()).hexdigest()[:16]
    jr = Journal(os.path.join(STATE, "e12_units.jsonl"), fingerprint=fp)
    n = 0
    for label, arm in d["arms"].items():
        if not jr.has(label):
            jr.record(label, arm)
            n += 1
    return "e12: %d units seeded (fp=%s, total %d)" % (n, fp, len(jr))


if __name__ == "__main__":
    print(seed_e7())
    print(seed_e12())
    print("e13: NOT seeded on purpose - its shim changed, so it re-measures")
