from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import re
import signal
import statistics
import sys
import time
from collections import Counter
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import g3bed as G
import padbed as B
import blockstat as BST
from _journal import Journal, atomic_write_json, save_result, runtime_context

GEN_DEFAULT = "g3eval_20261002"
VERDICT = "C:/dev/codex_handoff/state/evo/verdict_v3.md section 4.2"
GROUP = "X25519MLKEM768"
EXPECT_K = 2
GAP_MS = 50
TIMEOUT_S = 10
IMPUTE_MS = TIMEOUT_S * 1000.0
SERVER_FEC = "on"
CLIENT_FEC = "fec"
NOMINAL_W = 1280
NOMINAL_PARITY = NOMINAL_W + 39 + 6 * EXPECT_K
SMOKE_N = 5
SEGMENT_FIXED_S = 0.35
SERVER_START_S = 2.0
CONN_OVERHEAD_MS = 12.0
PREDICTIONS = os.path.join(ROOT, "g3", "stage0_predictions.json")
SEAL = os.path.join(ROOT, "g3", "SEAL_stage0.json")
PROTOCOL = "g3/PROTOCOL_stage0.md section 8"
HARNESS_FILES = ("experiments/g3bed.py", "experiments/padbed.py",
                 "experiments/_journal.py")
SEALED_FILES = ("g3/SEAL_stage0.json", "g3/stage0_predictions.json")
ONE_RTT_RULE = ("ok and hct_ms < 1.5*rtt_ms + 8*pre_bytes/(1000*rate_mbps) with the "
                "sealed nominal pre_bytes = lead*%d + %d*%d (PROTOCOL_stage0.md section 6); "
                "one_rtt_rate_row_bytes repeats the test with per-trial pre_bytes = "
                "first_flight_bytes + first_flight_lead_dgrams * "
                "(first_flight_parity_bytes / first_flight_parity_dgrams)"
                % (NOMINAL_PARITY, EXPECT_K, NOMINAL_W))
IMPUTATION = ("mean_planned_imputed_ms counts every planned trial; failed or "
              "missing trials (client crash, short output) are imputed at the "
              "client timeout %.0f ms" % IMPUTE_MS)

CONDS = {
    "bigcert": {"p17_name": "큰cert", "cert": 16000, "rtt_ms": 50.0,
                "netem_rate_mbit": 2.0, "uplink_policy_mbps": 2.0},
    "rtt200": {"p17_name": "RTT200", "cert": 9000, "rtt_ms": 200.0,
               "netem_rate_mbit": 2.0, "uplink_policy_mbps": 2.0},
    "mbps2": {"p17_name": "2Mbps", "cert": 9000, "rtt_ms": 50.0,
              "netem_rate_mbit": 2.0, "uplink_policy_mbps": 2.0},
}

ARMS = {
    "v2m1": {"label": "v2-m1", "pred_id": "v2-m1", "bin": "g2", "m": 1, "lead": 0,
             "extra": []},
    "v2m3": {"label": "v2-m3", "pred_id": "v2-m3", "bin": "g2", "m": 3, "lead": 1,
             "extra": []},
    "v3trm3": {"label": "v3tr-m3", "pred_id": "v3tr-m3", "bin": "g3", "m": 3, "lead": 1,
               "extra": ["-layout", "v3", "-lead", "1"]},
    "creditl3": {"label": "credit-only l3", "pred_id": "credit-only-l3", "bin": "g3",
                 "m": 3, "lead": 3, "extra": ["-layout", "v3", "-lead", "3"]},
    "creditl2": {"label": "credit-only l2", "pred_id": "credit-only-l2", "bin": "g3",
                 "m": 2, "lead": 2, "extra": ["-layout", "v3", "-lead", "2"]},
    "m4L1": {"label": "m4L1", "pred_id": "m4L1", "bin": "g3", "m": 4, "lead": 1,
             "extra": ["-layout", "v3", "-lead", "1"]},
    "m4L2": {"label": "m4L2", "pred_id": "m4L2", "bin": "g3", "m": 4, "lead": 2,
             "extra": ["-layout", "v3", "-lead", "2"]},
    "m4L3": {"label": "m4L3", "pred_id": "m4L3", "bin": "g3", "m": 4, "lead": 3,
             "extra": ["-layout", "v3", "-lead", "3"]},
}

SEGMENT_N = 40
CELLS = [
    {"cell": "bigcert_2", "pred_id": "bigcert_loss2", "cond": "bigcert", "loss_pct": 2.0,
     "blocks": 10,
     "arms": [("v2m1", 400), ("v2m3", 400), ("v3trm3", 400),
              ("creditl3", 400), ("m4L3", 400)]},
    {"cell": "bigcert_15", "pred_id": "bigcert_loss15", "cond": "bigcert", "loss_pct": 15.0,
     "blocks": 20,
     "arms": [("v2m1", 800), ("v2m3", 800), ("v3trm3", 800),
              ("creditl3", 800), ("m4L1", 800), ("m4L3", 800)]},
    {"cell": "rtt200_15", "pred_id": "rtt200_loss15", "cond": "rtt200", "loss_pct": 15.0,
     "blocks": 20,
     "arms": [("v2m3", 800), ("v3trm3", 800), ("m4L1", 800), ("m4L2", 800),
              ("creditl2", 400)]},
    {"cell": "mbps2_15", "pred_id": "2mbps_loss15", "cond": "mbps2", "loss_pct": 15.0,
     "blocks": 20,
     "arms": [("v2m3", 800), ("v3trm3", 800), ("m4L2", 800)]},
]

THROUGHPUT_S = {"bigcert": 0.192, "rtt200": 0.366, "mbps2": 0.156}
PRED_MS = {
    "bigcert_2": {"v2m1": 122.5, "v2m3": 132.9, "v3trm3": 127.3,
                  "creditl3": 90.1, "m4L3": 86.0},
    "bigcert_15": {"v2m1": 134.4, "v2m3": 137.9, "v3trm3": 132.4,
                   "creditl3": 155.5, "m4L1": 131.2, "m4L3": 114.4},
    "rtt200_15": {"v2m3": 240.9, "v3trm3": 240.1, "m4L1": 237.2,
                  "m4L2": 218.6, "creditl2": 388.7},
    "mbps2_15": {"v2m3": 83.0, "v3trm3": 82.2, "m4L2": 79.7},
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def mean(v):
    v = [x for x in v if x is not None]
    return (sum(v) / len(v)) if v else None


def median(v):
    v = [x for x in v if x is not None]
    return statistics.median(v) if v else None


def canon(obj):
    return json.loads(json.dumps(obj, sort_keys=True, ensure_ascii=False))


def settle_s(cond):
    return 0.3 + 2.0 * cond["rtt_ms"] / 1000.0


def paths(mode):
    tag = "g3_stage0" if mode == "full" else "g3_stage0_smoke"
    return {"journal": os.path.join(B.STATE, tag + "_units.jsonl"),
            "meta": os.path.join(B.STATE, tag + "_meta.json"),
            "status": os.path.join(B.STATE, tag + "_status.json"),
            "incidents": os.path.join(B.STATE, tag + "_incidents.jsonl"),
            "result": os.path.join(B.RESULTS, tag + ".json")}


def split(n, blocks):
    return [n // blocks + (1 if b < n % blocks else 0) for b in range(blocks)]


def build_plan(mode):
    cells, schedule, used = [], [], []
    for c in CELLS:
        arms = [a for a, _n in c["arms"]]
        used += [a for a in arms if a not in used]
        if mode == "smoke":
            nblk, totals = 1, {a: SMOKE_N for a in arms}
        else:
            nblk, totals = c["blocks"], dict(c["arms"])
            if max(totals.values()) != SEGMENT_N * nblk:
                raise ValueError("%s: %d blocks do not give %d-connection segments (%s)"
                                 % (c["cell"], nblk, SEGMENT_N, PROTOCOL))
        sizes = {a: split(totals[a], nblk) for a in arms}
        positions = {a: [0] * len(arms) for a in arms}
        for b in range(nblk):
            r = b % len(arms)
            order = arms[r:] + arms[:r]
            for pos, a in enumerate(order):
                positions[a][pos] += 1
            schedule.append({"cell": c["cell"], "block": b, "rotation": r,
                             "order": order,
                             "sizes": {a: sizes[a][b] for a in order}})
        cells.append({"cell": c["cell"], "pred_id": c["pred_id"], "cond": c["cond"],
                      "loss_pct": c["loss_pct"], "blocks": nblk,
                      "arms": [[a, totals[a]] for a in arms],
                      "position_counts": positions,
                      "latin_closed": nblk % len(arms) == 0})
    plan = {"schema": "g3_stage0.plan.v1", "mode": mode, "group": GROUP,
            "expect_k": EXPECT_K, "gap_ms": GAP_MS, "timeout_s": TIMEOUT_S,
            "impute_ms": IMPUTE_MS, "server_fec": SERVER_FEC,
            "client_fec": CLIENT_FEC, "conds": CONDS,
            "arms": {a: ARMS[a] for a in used}, "cells": cells,
            "schedule": schedule, "bins": G.BINS, "ports": G.PORTS,
            "work": G.WORK,
            "settle_s": {k: settle_s(v) for k, v in CONDS.items()},
            "loss_direction": "client_to_server_only",
            "netem": "padbed.set_netem(rtt/2, loss_c2s=loss, rate_up_mbit=rate), Bernoulli loss",
            "rotation": ("cyclic Latin: block b runs arms[b mod A:] + arms[:b mod A]; "
                         "cycles = n/{0} per {1}, so cells whose cycle count is not a "
                         "multiple of A are not position-balanced").format(SEGMENT_N, PROTOCOL),
            "segment_n": SEGMENT_N,
            "client_failure_rule": "client crash or short output is data: the "
                                   "missing trials are imputed and the block continues; "
                                   "only server death, missing server stats or a client "
                                   "that could not be executed (rc 126/127) retry the block",
            "server_lifecycle": "both servers start fresh at the first block run in each cell and after an infrastructure retry",
            "one_rtt_rule": ONE_RTT_RULE, "imputation": IMPUTATION}
    return canon(plan)


def unit_key(mode, cell, block):
    return "%s|%s|b%02d" % (mode, cell, block)


def fingerprint(plan, binrep):
    h = hashlib.sha256()
    h.update(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    h.update(json.dumps(runtime_context(), sort_keys=True).encode("utf-8"))
    for tag in ("g2", "g3"):
        h.update(("%s=%s;" % (tag, binrep[tag].get("sha256"))).encode())
    for rel in HARNESS_FILES + SEALED_FILES:
        h.update(rel.encode())
        h.update((G.sha256_or_none(os.path.join(ROOT, rel)) or "MISSING").encode())
    return h.hexdigest()[:16]


def predictions_record():
    return {"path": "g3/stage0_predictions.json",
            "sha256": G.sha256_or_none(PREDICTIONS),
            "layout_py_sha256": G.sha256_or_none(
                os.path.join(ROOT, "padfec3", "layout.py")),
            "stage0_predict_py_sha256": G.sha256_or_none(
                os.path.join(ROOT, "g3", "stage0_predict.py"))}


def seal_check():
    out = {"path": "g3/SEAL_stage0.json", "sha256": G.sha256_or_none(SEAL),
           "changed": [], "missing": [], "ok": False}
    seal = read_json(SEAL)
    files = (seal or {}).get("sha256")
    if not isinstance(files, dict) or not files:
        out["missing"].append("g3/SEAL_stage0.json")
        return out
    for rel, h in sorted(files.items()):
        now = G.sha256_or_none(os.path.join(ROOT, rel))
        if now is None:
            out["missing"].append(rel)
        elif now != h:
            out["changed"].append(rel)
    out["sealed_utc"] = seal.get("sealed_utc")
    out["ok"] = not out["changed"] and not out["missing"]
    return out


def sealed_plan_check(plan):
    pred = read_json(PREDICTIONS)
    diffs = []
    if not isinstance(pred, dict) or not isinstance(pred.get("conditions"), dict):
        return ["sealed predictions unreadable: %s" % PREDICTIONS]
    for cell in plan["cells"]:
        pc = pred["conditions"].get(cell["pred_id"])
        if not isinstance(pc, dict):
            diffs.append("%s: no sealed condition %s" % (cell["cell"], cell["pred_id"]))
            continue
        cond = CONDS[cell["cond"]]
        for k, ours in (("cert", cond["cert"]), ("rtt_ms", cond["rtt_ms"]),
                        ("uplink_mbps", cond["uplink_policy_mbps"]),
                        ("loss_pct", cell["loss_pct"])):
            if pc.get(k) != ours:
                diffs.append("%s.%s: ours %r sealed %r" % (cell["cell"], k, ours, pc.get(k)))
        sealed_arms = pc.get("arms") or {}
        ours_ids = [ARMS[a]["pred_id"] for a, _n in cell["arms"]]
        if sorted(ours_ids) != sorted(sealed_arms):
            diffs.append("%s: arms %s vs sealed %s" % (cell["cell"], ours_ids,
                                                       sorted(sealed_arms)))
        for a, n in cell["arms"]:
            sa = sealed_arms.get(ARMS[a]["pred_id"])
            if not isinstance(sa, dict):
                continue
            if sa.get("n_planned") != n:
                diffs.append("%s/%s: n %d vs sealed %r" % (cell["cell"], a, n,
                                                           sa.get("n_planned")))
            cut = nominal_threshold(ARMS[a]["lead"], cond)
            if (not isinstance(sa.get("one_rtt_cutoff_ms"), (int, float))
                    or abs(cut - sa["one_rtt_cutoff_ms"]) > 1e-6):
                diffs.append("%s/%s: 1-RTT cutoff %.6f vs sealed %r"
                             % (cell["cell"], a, cut, sa.get("one_rtt_cutoff_ms")))
    return diffs


def runner_sha256():
    return G.sha256_or_none(os.path.abspath(__file__))


def _literal(node):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return None


def p17_check():
    src_path = os.path.join(HERE, "p17_adaptive_value.py")
    pol_path = os.path.join(ROOT, "padfec", "policy.py")
    out = {"source": "experiments/p17_adaptive_value.py",
           "sha256": G.sha256_or_none(src_path), "conds": {}, "facts": {},
           "differences": [], "ok": False}
    try:
        with open(src_path, encoding="utf-8") as f:
            src = f.read()
        with open(pol_path, encoding="utf-8") as f:
            pol = ast.parse(f.read())
        tree = ast.parse(src)
    except (OSError, SyntaxError) as exc:
        out["differences"].append("cannot parse p17 or policy.py: %s" % exc)
        return out
    polc = {}
    for node in pol.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            polc[node.targets[0].id] = _literal(node.value)
    consts, conds = {}, None
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            if node.targets[0].id == "CONDS":
                conds = node.value
            else:
                consts[node.targets[0].id] = _literal(node.value)

    def val(node):
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id == "POL"):
            return polc.get(node.attr)
        return _literal(node)

    p17 = {}
    for elt in getattr(conds, "elts", []):
        items = [val(e) for e in getattr(elt, "elts", [])]
        if len(items) == 5:
            p17[items[0]] = {"netem_rate_mbit": items[1],
                             "uplink_policy_mbps": items[2], "cert": items[3],
                             "rtt_ms": items[4]}
    out["p17_conds"] = p17
    for name, c in CONDS.items():
        theirs = p17.get(c["p17_name"])
        row = {"ours": {k: c[k] for k in ("cert", "rtt_ms", "netem_rate_mbit",
                                           "uplink_policy_mbps")},
               "p17_name": c["p17_name"], "p17": theirs, "match": False}
        if theirs is None:
            out["differences"].append("p17 has no condition %r" % c["p17_name"])
        else:
            diffs = [k for k in row["ours"] if row["ours"][k] != theirs.get(k)]
            row["match"] = not diffs
            for k in diffs:
                out["differences"].append("%s.%s: ours %r vs p17 %r"
                                          % (name, k, row["ours"][k], theirs.get(k)))
        out["conds"][name] = row
    facts = {
        "group": consts.get("GROUP") == GROUP,
        "expect_k": consts.get("K") == EXPECT_K,
        "client_timeout_10s": "timeout_s=10" in src and TIMEOUT_S == 10,
        "gap_50ms_when_rate_gt_0": bool(re.search(
            r"gap_ms\s*=\s*50\s+if\s+rate\s*>\s*0\s+else\s+8", src)) and GAP_MS == 50,
        "server_fec_on": 'B.start_server(cert, fec="on"' in src and SERVER_FEC == "on",
        "netem_call": bool(re.search(
            r"B\.set_netem\(rtt\s*/\s*2\.0,\s*loss_c2s=loss,\s*rate_up_mbit=rate\)", src)),
        "client_uplink_flag": "uplink_mbps=up_policy" in src,
        "client_expect_k": "expect_k=K" in src,
        "fixed_arms_fec_on": consts.get("ARMS") is not None and all(
            f in ("on", "auto", "off") for _n, f, _m in consts.get("ARMS") or []),
    }
    out["facts"] = facts
    for k, v in facts.items():
        if not v:
            out["differences"].append("p17 harness fact not confirmed: %s" % k)
    out["notes"] = [
        "p17 runs each condition as a 2%<->15% schedule with one server; stage 0 fixes the loss per cell and runs two servers (g2 :44433, g3 :44434) in the same netns",
        "client -fec fec here equals p17's -fec on (qamp maps both to fmode fec)",
    ]
    out["ok"] = not out["differences"]
    return out


def estimate(plan):
    cells, tot_a, tot_b = [], 0.0, 0.0
    per_block = {}
    for cell in plan["cells"]:
        cond = CONDS[cell["cond"]]
        blocks = [b for b in plan["schedule"] if b["cell"] == cell["cell"]]
        nseg = sum(len(b["order"]) for b in blocks)
        conns = sum(n for _a, n in cell["arms"])
        seg_s = nseg * (SEGMENT_FIXED_S + settle_s(cond))
        a_s = conns * THROUGHPUT_S[cell["cond"]] + seg_s + SERVER_START_S
        b_s = (sum(n * (PRED_MS[cell["cell"]][a] + GAP_MS + CONN_OVERHEAD_MS)
                   for a, n in cell["arms"]) / 1000.0 + seg_s + SERVER_START_S)
        for b in blocks:
            per_block[(b["cell"], b["block"])] = (
                sum(b["sizes"][a] * (PRED_MS[cell["cell"]][a] + GAP_MS
                                     + CONN_OVERHEAD_MS) / 1000.0
                    + SEGMENT_FIXED_S + settle_s(cond) for a in b["order"]))
        cells.append({"cell": cell["cell"], "connections": conns,
                      "segments": nseg, "p17_throughput_s": a_s,
                      "predicted_hct_s": b_s})
        tot_a += a_s
        tot_b += b_s
    return {"cells": cells, "total_p17_throughput_s": tot_a,
            "total_predicted_hct_s": tot_b, "planning_s": max(tot_a, tot_b),
            "per_block_s": per_block,
            "assumptions": {"p17_s_per_conn": THROUGHPUT_S,
                            "conn_overhead_ms": CONN_OVERHEAD_MS,
                            "segment_fixed_s": SEGMENT_FIXED_S,
                            "server_start_s_per_cell": SERVER_START_S,
                            "pred_ms_source": "verdict_v3.md 4.2 provisional table (duration estimate only)"}}


def ff_lead(row, lead):
    v = row.get("first_flight_lead_dgrams")
    if type(v) is int:
        return v
    npar = row.get("first_flight_parity_dgrams")
    return min(lead, npar) if type(npar) is int else 0


def pre_decision_bytes(row, lead):
    ob = row.get("first_flight_bytes") or 0
    npar = row.get("first_flight_parity_dgrams") or 0
    pb = row.get("first_flight_parity_bytes") or 0
    size = (pb / float(npar)) if npar else 0.0
    return ob + ff_lead(row, lead) * size


def tau_ms(nbytes, rate_mbps):
    return 8.0 * nbytes / (1000.0 * rate_mbps) if rate_mbps > 0 else 0.0


def one_rtt_threshold(row, lead, cond):
    return 1.5 * cond["rtt_ms"] + tau_ms(pre_decision_bytes(row, lead),
                                         cond["netem_rate_mbit"])


def nominal_threshold(lead, cond):
    return 1.5 * cond["rtt_ms"] + tau_ms(EXPECT_K * NOMINAL_W
                                         + lead * NOMINAL_PARITY,
                                         cond["netem_rate_mbit"])


def is_timeout(err):
    e = (err or "").lower()
    return "timeout" in e or "deadline" in e or "no recent network activity" in e


def sum_numeric(dicts):
    out = {}
    for d in dicts:
        for k, v in (d or {}).items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                out[k] = out.get(k, 0) + v
    return out


def block_complete(rec, blk):
    if not isinstance(rec, dict) or rec.get("err"):
        return False
    segs = rec.get("segments")
    if not isinstance(segs, list) or not all(isinstance(s, dict) for s in segs):
        return False
    if [s.get("arm") for s in segs] != list(blk["order"]):
        return False
    for s in segs:
        n = blk["sizes"][s["arm"]]
        rows = s.get("rows")
        if (s.get("err") or s.get("n_planned") != n or not isinstance(rows, list)
                or len(rows) > n or not s.get("server_after")):
            return False
        if len(rows) < n and not s.get("client_err"):
            return False
        for r in rows:
            if not isinstance(r, dict) or type(r.get("ok")) is not bool:
                return False
            ms = r.get("ms")
            if type(ms) not in (int, float) or not math.isfinite(ms) or ms < 0:
                return False
    return True


def flag_mismatches(arm, rows):
    a = ARMS[arm]
    out = {"m_used": 0, "layout": 0, "lead": 0, "first_flight_lead": 0}
    for r in rows:
        if r.get("m_used") != a["m"]:
            out["m_used"] += 1
        if a["bin"] == "g3":
            if r.get("layout") != "v3":
                out["layout"] += 1
            if r.get("lead") != a["lead"]:
                out["lead"] += 1
            v = r.get("first_flight_lead_dgrams")
            if type(v) is not int or v != a["lead"]:
                out["first_flight_lead"] += 1
        elif r.get("layout") not in (None, "v2"):
            out["layout"] += 1
    return out


def lead_credit(arm, segs):
    a = ARMS[arm]
    trailing = a["m"] - a["lead"]
    per = []
    for b, s in segs:
        d = s.get("server_delta") or {}
        cs = s.get("client_stats") or {}
        srv_par = d.get("parities", 0)
        srv_cred = d.get("credit_parities", 0)
        leads = sum(ff_lead(r, a["lead"]) for r in s["rows"])
        sent = cs.get("parity_sent")
        if type(sent) is not int:
            sent = sum(r.get("parity_sent") or 0 for r in s["rows"])
        trailing_max = sent - leads
        v3 = d.get("credit_parities_v3")
        per.append({"block": b["block"], "srv_parities": srv_par,
                    "srv_credit": srv_cred, "srv_credit_v3": v3,
                    "cli_parity_sent": sent,
                    "cli_first_flight_leads": leads,
                    "bound_ok": (None if (len(s["rows"]) < s.get("n_planned", 0)
                                          or s.get("rc") not in (0, None))
                                 else (srv_par - srv_cred) <= trailing_max),
                    "exact_ok": (srv_cred == srv_par) if trailing == 0 else None,
                    "v3_consistent": ((v3 == srv_cred) if a["bin"] == "g3"
                                      and v3 is not None else None)})

    def agg(key):
        vals = [p[key] for p in per if p[key] is not None]
        return all(vals) if vals else None

    return {"rule": ("non-credit parities received <= client parity_sent - first-flight "
                     "leads sent (per segment, segments with a client crash or short "
                     "output excluded); on the g3 server credit_parities_v3 == "
                     "credit_parities; credit-only arms report credit_parities == parities "
                     "as supporting data"),
            "bound_ok": agg("bound_ok"), "exact_ok": agg("exact_ok"),
            "v3_consistent": agg("v3_consistent"),
            "srv_parities": sum(p["srv_parities"] for p in per),
            "srv_credit": sum(p["srv_credit"] for p in per),
            "cli_parity_sent": sum(p["cli_parity_sent"] for p in per),
            "cli_first_flight_leads": sum(p["cli_first_flight_leads"] for p in per),
            "per_segment": per}


def server_summary(arm, segs):
    a = ARMS[arm]
    conns = [c for _b, s in segs for c in (s.get("server_new_conns") or [])]
    tx = [c for c in conns if (c.get("tx_dgrams") or 0) > 0]
    bc = [c.get("beff_credit") for c in tx if type(c.get("beff_credit")) is int]
    waits = [(c["first_tx_ns"] - c["first_rx_ns"]) / 1e6 for c in tx
             if type(c.get("first_tx_ns")) is int and type(c.get("first_rx_ns")) is int
             and c["first_tx_ns"] > 0 and c["first_rx_ns"] > 0]
    counters = sum_numeric(s.get("server_delta") for _b, s in segs)
    acct = sum(1 for _b, s in segs
               if (s.get("server_after") or {}).get("bytes_to_stack", 0)
               > (s.get("server_after") or {}).get("bytes_in", 0))
    cross = sum(1 for _b, s in segs if (s.get("other_server_delta") or {}).get("bytes_in"))
    return {"server": a["bin"], "port": G.PORTS[a["bin"]], "counters": counters,
            "conns_seen": len(conns), "conns_with_tx": len(tx),
            "beff_credit_hist": {str(k): v for k, v in sorted(Counter(bc).items())},
            "frac_beff_credit_eq_lead": (sum(1 for x in bc if x == a["lead"]) / len(bc))
            if bc else None,
            "frac_beff_stack_ge_phys": (sum(1 for c in tx if (c.get("beff_stack") or 0)
                                            >= (c.get("beff_phys") or 0)) / len(tx))
            if tx else None,
            "median_beff_stack": median([c.get("beff_stack") for c in tx]),
            "median_beff_phys": median([c.get("beff_phys") for c in tx]),
            "median_first_tx_after_first_rx_ms": median(waits),
            "conn_stack_gt_rx": sum(1 for c in conns if (c.get("stack_bytes") or 0)
                                    > (c.get("rx_bytes") or 0)),
            "global_acct_violations": acct,
            "crc_fail": counters.get("recover_crc_fail", 0),
            "cross_traffic_segments": cross,
            "lead_credit": lead_credit(arm, segs)}


def summarize_arm(arm, cond, blocks, recs):
    a = ARMS[arm]
    segs = []
    for b in blocks:
        rec = recs.get(b["block"])
        for s in (rec or {}).get("segments", []):
            if s.get("arm") == arm:
                segs.append((b, s))
    rows = [r for _b, s in segs for r in s["rows"]]
    blk = [b["block"] for b, s in segs for _r in s["rows"]]
    n_req = sum(b["sizes"][arm] for b in blocks)
    ok_ms = [r["ms"] for r in rows if r.get("ok")]
    nom = nominal_threshold(a["lead"], cond)
    one = [bool(r.get("ok")) and r["ms"] < nom for r in rows]
    thr = [one_rtt_threshold(r, a["lead"], cond) for r in rows]
    one_row = [bool(r.get("ok")) and r["ms"] < t for r, t in zip(rows, thr)]
    cerrs = [(b["block"], s.get("client_err")) for b, s in segs if s.get("client_err")]
    pre = [pre_decision_bytes(r, a["lead"]) for r in rows]
    ffup = [(r.get("first_flight_bytes") or 0) + (r.get("first_flight_parity_bytes") or 0)
            for r in rows]
    fails = [r for r in rows if not r.get("ok")]
    bm_imp, bm_ok, bm_pos = {}, {}, {}
    for b, s in segs:
        nb = b["sizes"][arm]
        oks = [r["ms"] for r in s["rows"] if r.get("ok")]
        bm_imp[b["block"]] = (sum(oks) + IMPUTE_MS * (nb - len(oks))) / nb
        bm_ok[b["block"]] = mean(oks)
        bm_pos[b["block"]] = s.get("pos")
    cli = sum_numeric(s.get("client_stats") for _b, s in segs)
    n_rows = len(rows)
    ffk = Counter("%s+%s" % (r.get("first_flight_datagrams"),
                             r.get("first_flight_parity_dgrams")) for r in rows)
    return {
        "label": a["label"], "binary": a["bin"], "binary_path": G.BINS[a["bin"]],
        "port": G.PORTS[a["bin"]], "m": a["m"], "lead": a["lead"],
        "extra_flags": a["extra"],
        "n_requested": n_req, "n_returned": n_rows, "ok": len(ok_ms),
        "failed": len(fails), "timeouts": sum(1 for r in fails if is_timeout(r.get("err"))),
        "missing": n_req - n_rows,
        "fail_errors": dict(Counter((r.get("err") or "")[:80] for r in fails)),
        "mean_planned_imputed_ms": ((sum(ok_ms) + IMPUTE_MS * (n_req - len(ok_ms))) / n_req)
        if n_req else None,
        "mean_ok_ms": mean(ok_ms), "median_ok_ms": median(ok_ms),
        "p90_ok_ms": B.pctl(ok_ms, 0.90), "p99_ok_ms": B.pctl(ok_ms, 0.99),
        "one_rtt_rate": (sum(one) / n_req) if n_req else None,
        "one_rtt_rate_scope": "one_rtt trials / planned trials",
        "one_rtt_threshold_nominal_ms": nom,
        "one_rtt_rate_row_bytes": (sum(one_row) / n_req) if n_req else None,
        "one_rtt_threshold_row_median_ms": median(thr),
        "client_error_segments": [{"block": b, "err": e} for b, e in cerrs],
        "pre_decision_bytes_median": median(pre),
        "first_flight_uplink_bytes_mean": mean(ffup),
        "initial_uplink_bytes_per_conn": ((cli.get("bytes_orig", 0) + cli.get("bytes_parity", 0))
                                          / n_rows) if n_rows else None,
        "parity_sent_per_conn": (cli.get("parity_sent", 0) / n_rows) if n_rows else None,
        "first_flight_datagrams_hist": dict(sorted(ffk.items())),
        "first_flight_lead_hist": dict(sorted(Counter(
            str(r.get("first_flight_lead_dgrams")) for r in rows).items())),
        "server_bytes_median": median([r.get("server_bytes") for r in rows]),
        "client_stats_sum": cli,
        "flag_mismatches": flag_mismatches(arm, rows),
        "server": server_summary(arm, segs),
        "block_means_imputed_ms": {str(k): v for k, v in bm_imp.items()},
        "block_means_ok_ms": {str(k): v for k, v in bm_ok.items()},
        "block_positions": {str(k): v for k, v in bm_pos.items()},
        "trials": {"block": blk, "ms": [r["ms"] for r in rows],
                   "ok": [bool(r.get("ok")) for r in rows], "one_rtt": one,
                   "one_rtt_row_bytes": one_row,
                   "threshold_row_ms": thr, "pre_decision_bytes": pre,
                   "first_flight_datagrams": [r.get("first_flight_datagrams") for r in rows],
                   "first_flight_parity_dgrams": [r.get("first_flight_parity_dgrams") for r in rows],
                   "first_flight_lead_dgrams": [r.get("first_flight_lead_dgrams") for r in rows],
                   "first_flight_uplink_bytes": ffup,
                   "server_bytes": [r.get("server_bytes") for r in rows]},
        "_bm_imp": bm_imp,
    }


def paired(bm_a, bm_b, alpha=0.05):
    common = sorted(set(bm_a) & set(bm_b))
    d = [bm_a[c] - bm_b[c] for c in common]
    if not d:
        return {"blocks": 0, "mean": None, "sd": None, "half": None, "lo": None, "hi": None}
    mu = sum(d) / len(d)
    if len(d) < 2:
        return {"blocks": 1, "mean": mu, "sd": None, "half": None, "lo": None, "hi": None}
    sd = statistics.stdev(d)
    half = BST.t_crit(len(d) - 1, alpha) * sd / math.sqrt(len(d))
    return {"blocks": len(d), "mean": mu, "sd": sd, "half": half,
            "lo": mu - half, "hi": mu + half}


def position_effect(arms_out):
    resid = {}
    for v in arms_out.values():
        base = v["mean_planned_imputed_ms"]
        for blk, x in v["_bm_imp"].items():
            pos = v["block_positions"].get(str(blk))
            if base is not None and pos is not None:
                resid.setdefault(pos, []).append(x - base)
    return {str(k): mean(v) for k, v in sorted(resid.items())}


def summarize_cell(cell, plan, jr):
    cond = CONDS[cell["cond"]]
    blocks = [b for b in plan["schedule"] if b["cell"] == cell["cell"]]
    recs = {b["block"]: jr.get(unit_key(plan["mode"], cell["cell"], b["block"]))
            for b in blocks}
    arms = [a for a, _n in cell["arms"]]
    arms_out = {a: summarize_arm(a, cond, blocks, recs) for a in arms}
    contrasts = {}
    for i, a in enumerate(arms):
        for b in arms[i + 1:]:
            c = paired(arms_out[a]["_bm_imp"], arms_out[b]["_bm_imp"])
            c["overall_diff_ms"] = (arms_out[a]["mean_planned_imputed_ms"]
                                    - arms_out[b]["mean_planned_imputed_ms"])
            ma, mb = arms_out[a]["mean_ok_ms"], arms_out[b]["mean_ok_ms"]
            c["ok_only_diff_ms"] = (ma - mb) if ma is not None and mb is not None else None
            contrasts["%s - %s" % (a, b)] = c
    pos = position_effect(arms_out)
    for v in arms_out.values():
        v.pop("_bm_imp")
    netem = [r.get("netem") for r in recs.values() if r]
    servers = [r.get("servers") for r in recs.values() if r]
    return {"cell": cell["cell"], "cond": cell["cond"], "loss_pct": cell["loss_pct"],
            "cert": cond["cert"], "rtt_ms": cond["rtt_ms"],
            "netem_rate_mbit": cond["netem_rate_mbit"],
            "uplink_policy_mbps": cond["uplink_policy_mbps"],
            "blocks_planned": len(blocks),
            "blocks_done": sum(1 for b in blocks if block_complete(recs[b["block"]], b)),
            "netem_specs": netem[0] if netem else None,
            "netem_expected_tokens_all_blocks": (all(all((n or {}).get("expected_tokens", {}).values())
                                                     and (n or {}).get("expected_tokens")
                                                     for n in netem) if netem else None),
            "server_cert_der": [json.loads(x) for x in sorted({
                json.dumps({t: (s or {}).get(t, {}).get("cert_der") for t in ("g2", "g3")},
                           sort_keys=True) for s in servers})],
            "arms": arms_out, "contrasts": contrasts,
            "position_effect_ms": pos}


def contrast(cells, cell, a, b):
    c = cells[cell]["contrasts"]
    k = "%s - %s" % (a, b)
    if k in c:
        return dict(c[k])
    r = dict(c["%s - %s" % (b, a)])
    for f in ("mean", "overall_diff_ms", "ok_only_diff_ms"):
        if r.get(f) is not None:
            r[f] = -r[f]
    if r.get("lo") is not None:
        r["lo"], r["hi"] = -r["hi"], -r["lo"]
    return r


def mechanism_checks(cell_list):
    cells = {c["cell"]: c for c in cell_list}

    def arm(cell, a):
        return cells[cell]["arms"][a]

    m4 = arm("bigcert_2", "m4L3")
    cl3 = arm("bigcert_2", "creditl3")
    d1 = contrast(cells, "bigcert_2", "m4L3", "v2m1")
    lc = m4["server"]["lead_credit"]
    c_parts = {"m4L3_bound_ok": lc["bound_ok"],
               "m4L3_v3_consistent": lc["v3_consistent"],
               "m4L3_flag_mismatches_zero": not any(m4["flag_mismatches"].values())}
    m1 = {"rule": "bigcert 2%: m4L3 1-RTT rate >= 0.85, m4L3 - v2m1 <= -18 ms, server credits all leading datagrams",
          "one_rtt_rate": m4["one_rtt_rate"], "a_ok": m4["one_rtt_rate"] is not None
          and m4["one_rtt_rate"] >= 0.85,
          "diff_ms": d1["overall_diff_ms"], "diff_paired": d1,
          "b_ok": d1["overall_diff_ms"] is not None and d1["overall_diff_ms"] <= -18.0,
          "c_parts": c_parts, "c_ok": all(v is True for v in c_parts.values()),
          "c_operationalization": lc["rule"],
          "c_supporting": {"m4L3_frac_beff_credit_eq_lead": m4["server"]["frac_beff_credit_eq_lead"],
                           "m4L3_beff_credit_hist": m4["server"]["beff_credit_hist"],
                           "creditl3_all_parities_credited":
                               cl3["server"]["lead_credit"]["exact_ok"]}}
    m1["pass"] = bool(m1["a_ok"] and m1["b_ok"] and m1["c_ok"])
    d2 = contrast(cells, "bigcert_2", "v2m3", "v3trm3")
    m2 = {"rule": "bigcert 2%: 2.8 <= (v2m3 - v3trm3) <= 11.2 ms",
          "diff_ms": d2["overall_diff_ms"], "diff_paired": d2,
          "pass": d2["overall_diff_ms"] is not None and 2.8 <= d2["overall_diff_ms"] <= 11.2}
    d3 = contrast(cells, "rtt200_15", "v2m3", "m4L2")
    m3 = {"rule": "RTT200 15%: 11 <= (v2m3 - m4L2) <= 44 ms",
          "diff_ms": d3["overall_diff_ms"], "diff_paired": d3,
          "pass": d3["overall_diff_ms"] is not None and 11.0 <= d3["overall_diff_ms"] <= 44.0}
    m4r = {"rule": "report only: FEC share = creditl3 - m4L3 (projection about 4 ms at 2%, 41 ms at 15%)"}
    for cell in ("bigcert_2", "bigcert_15"):
        d = contrast(cells, cell, "creditl3", "m4L3")
        m4r[cell] = {"fec_share_ms": d["overall_diff_ms"], "paired": d}
    return {"source": VERDICT, "auto_evaluated": True,
            "point_estimate": "difference of mean_planned_imputed_ms",
            "M1": m1, "M2": m2, "M3": m3, "M4": m4r}


def read_jsonl(path):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return out


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def integrity(cell_list, plan, meta, jr, P):
    arms = [(c["cell"], a, v) for c in cell_list for a, v in c["arms"].items()]
    recs = [jr.get(unit_key(plan["mode"], b["cell"], b["block"])) for b in plan["schedule"]]
    recs = [r for r in recs if r]
    bins_seen = sorted({json.dumps(r.get("bins_sha256"), sort_keys=True) for r in recs})
    start_bins = {t: meta["starts"][0]["binaries"][t]["sha256"] for t in ("g2", "g3")}
    finished = meta.get("finished") or {}
    src0 = meta["starts"][0].get("quicbed_sources_sha256")
    return {
        "crc_fail_total": sum(v["server"]["crc_fail"] for _c, _a, v in arms),
        "global_acct_violations": sum(v["server"]["global_acct_violations"] for _c, _a, v in arms),
        "conn_stack_gt_rx": sum(v["server"]["conn_stack_gt_rx"] for _c, _a, v in arms),
        "flag_mismatches": {"%s/%s" % (c, a): v["flag_mismatches"] for c, a, v in arms
                            if any(v["flag_mismatches"].values())},
        "server_stats_present_all_segments": all(
            s.get("server_after") for r in recs for s in r.get("segments", [])),
        "binaries_constant": bins_seen == [json.dumps(start_bins, sort_keys=True)],
        "binaries_seen": [json.loads(x) for x in bins_seen],
        "quicbed_sources_unchanged": (finished.get("quicbed_sources_sha256") == src0
                                      if finished else None),
        "runner_sha256_seen": sorted({str(r.get("runner_sha256")) for r in recs}),
        "attempts_gt_1": sum(1 for r in recs if (r.get("attempt") or 1) > 1),
        "client_error_segments": sum(len(r.get("client_errors") or []) for r in recs),
        "missing_trials": sum(v["missing"] for _c, _a, v in arms),
        "seal_check_at_starts": [s.get("seal_check", {}).get("ok") for s in meta["starts"]],
        "incidents": read_jsonl(P["incidents"]),
        "load_processes_seen": sorted({x for r in recs for x in r.get("load_processes") or []}),
        "journal_provenance": jr.provenance(),
    }


def finalize(plan, meta, jr, P):
    cell_list = [summarize_cell(c, plan, jr) for c in plan["cells"]]
    report = {"schema": "g3_stage0.result.v1", "mode": plan["mode"],
              "confirmatory": plan["mode"] == "full", "verdict": VERDICT,
              "generated_at": utc_now(),
              "journal": {"path": os.path.relpath(P["journal"], ROOT).replace("\\", "/"),
                          "fingerprint": meta["fp"]},
              "plan": plan, "env_starts": meta["starts"],
              "finished": meta.get("finished"),
              "one_rtt_rule": ONE_RTT_RULE, "imputation": IMPUTATION,
              "cells": cell_list,
              "mechanism_checks": (mechanism_checks(cell_list)
                                   if plan["mode"] == "full" else None)}
    report["integrity"] = integrity(cell_list, plan, meta, jr, P)
    save_result(P["result"], report)
    return report


def print_summary(report):
    print()
    print("=" * 100)
    for c in report["cells"]:
        print("%s  cert %d  RTT %g  loss %g%%  blocks %d/%d" % (
            c["cell"], c["cert"], c["rtt_ms"], c["loss_pct"], c["blocks_done"],
            c["blocks_planned"]))
        for a, v in c["arms"].items():
            print("   %-9s %s n %4d/%4d ok %4d fail %3d  mean* %8.2f  1RTT %.3f  "
                  "ff-up %7.0f B  credit %s/%s" % (
                      a, v["binary"], v["n_returned"], v["n_requested"], v["ok"],
                      v["failed"], v["mean_planned_imputed_ms"] or -1,
                      v["one_rtt_rate"] or 0.0,
                      v["first_flight_uplink_bytes_mean"] or 0.0,
                      v["server"]["lead_credit"]["srv_credit"],
                      v["server"]["lead_credit"]["srv_parities"]))
    mc = report.get("mechanism_checks")
    if mc:
        for k in ("M1", "M2", "M3"):
            print("%s %s  diff %s" % (k, "PASS" if mc[k]["pass"] else "FAIL",
                                      mc[k].get("diff_ms")))
        print("M4", json.dumps({k: v["fec_share_ms"] for k, v in mc["M4"].items()
                                if isinstance(v, dict)}))
    print("integrity:", json.dumps({k: v for k, v in report["integrity"].items()
                                    if k in ("crc_fail_total", "global_acct_violations",
                                             "conn_stack_gt_rx", "binaries_constant",
                                             "quicbed_sources_unchanged",
                                             "attempts_gt_1", "client_error_segments",
                                             "missing_trials")}))


def write_status(P, **kw):
    kw["updated_at"] = utc_now()
    kw["pid"] = os.getpid()
    try:
        atomic_write_json(P["status"], kw)
    except OSError:
        pass


def incident(P, rec):
    rec = dict(rec, at=utc_now())
    with open(P["incidents"], "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def start_servers(cert):
    servers = {}
    try:
        for tag in ("g2", "g3"):
            servers[tag] = G.start_server(tag, cert, fec=SERVER_FEC)
    except Exception:
        stop_servers(servers)
        raise
    return servers


def stop_servers(servers):
    for s in (servers or {}).values():
        G.stop_server(s)


def run_segment(arm, n, pos, servers, cond):
    a = ARMS[arm]
    tag = a["bin"]
    other = "g3" if tag == "g2" else "g2"
    before = {t: G.read_stats(servers[t]["stats_path"]) for t in ("g2", "g3")}
    started = utc_now()
    t0 = time.monotonic()
    rows, cstats, client_err, argv, rc = G.run_client(
        tag, GROUP, n, CLIENT_FEC, a["m"], GAP_MS, TIMEOUT_S, EXPECT_K,
        cond["uplink_policy_mbps"], a["extra"])
    wall = time.monotonic() - t0
    time.sleep(settle_s(cond))
    after = {t: G.read_stats(servers[t]["stats_path"]) for t in ("g2", "g3")}
    alive = {t: G.server_alive(servers[t]) for t in ("g2", "g3")}
    err = ""
    if not all(alive.values()):
        err = "server died: %s" % [t for t, v in alive.items() if not v]
    elif not before[tag] or not after[tag]:
        err = "server stats missing"
    if len(rows) > n:
        err = err or "rows %d > n %d" % (len(rows), n)
    if rc in (126, 127):
        err = err or "client could not be executed (rc %d): %s" % (rc, client_err)
    return {"arm": arm, "pos": pos, "bin": tag, "port": G.PORTS[tag],
            "argv": argv, "rc": rc, "err": err, "client_err": client_err or "",
            "n_planned": n,
            "n_rows": len(rows), "rows": rows, "client_stats": cstats,
            "server_delta": G.scalar_delta(before[tag], after[tag]),
            "server_after": G.scalars(after[tag]),
            "server_new_conns": G.new_conns(before[tag], after[tag]),
            "other_server_delta": {k: v for k, v in G.scalar_delta(
                before[other], after[other]).items() if v},
            "started_at": started, "finished_at": utc_now(), "wall_s": wall}


def run_block(blk, cell, servers, attempt, bins_sha):
    cond = CONDS[cell["cond"]]
    started = utc_now()
    netem = G.set_netem(cond["rtt_ms"] / 2.0, cell["loss_pct"],
                        cond["netem_rate_mbit"])
    netem["expected_tokens"] = {
        "c2s_delay": ("delay %gms" % (cond["rtt_ms"] / 2.0)) in netem["tc_c2s"],
        "c2s_loss": ("loss %g%%" % cell["loss_pct"]) in netem["tc_c2s"],
        "c2s_rate": ("rate %gMbit" % cond["netem_rate_mbit"]) in netem["tc_c2s"],
        "s2c_delay": ("delay %gms" % (cond["rtt_ms"] / 2.0)) in netem["tc_s2c"],
        "s2c_no_loss": "loss" not in netem["tc_s2c"],
        "s2c_no_rate": "rate" not in netem["tc_s2c"]}
    segs = []
    for pos, arm in enumerate(blk["order"]):
        segs.append(run_segment(arm, blk["sizes"][arm], pos, servers, cond))
        if segs[-1]["err"]:
            break
    err = next((s["err"] for s in segs if s["err"]), "")
    return {"cell": blk["cell"], "block": blk["block"], "rotation": blk["rotation"],
            "order": blk["order"], "sizes": blk["sizes"], "attempt": attempt,
            "started_at": started, "finished_at": utc_now(), "netem": netem,
            "servers": {t: {k: s[k] for k in ("pid", "cert_der", "certsize", "argv")}
                        for t, s in servers.items()},
            "segments": segs, "load_processes": G.load_processes(),
            "bins_sha256": bins_sha, "runner_sha256": runner_sha256(), "err": err,
            "client_errors": [{"arm": s["arm"], "rc": s["rc"], "err": s["client_err"],
                               "n_rows": s["n_rows"], "n_planned": s["n_planned"]}
                              for s in segs if s.get("client_err")]}


def refuse(lines):
    for line in lines:
        print("REFUSED: %s" % line, file=sys.stderr)
    return 2


def _sigterm(_signum, _frame):
    raise SystemExit(143)


def live(mode):
    B.harden()
    signal.signal(signal.SIGTERM, _sigterm)
    if not sys.platform.startswith("linux"):
        return refuse(["Historical stage-0 execution is disabled in gen33."])
    B.require_root()
    os.environ.setdefault("PADFEC_GEN", GEN_DEFAULT)
    P = paths(mode)
    busy = G.busy_processes()
    if busy:
        return refuse(["another measurement is running"] + busy)
    load = G.load_processes()
    if load:
        return refuse(["build or compile processes are running"] + load)
    chk = p17_check()
    if not chk["ok"]:
        return refuse(["p17 condition check failed"] + chk["differences"])
    binrep, problems = G.binary_report()
    flags, fproblems = G.flag_report(binrep) if not problems else (None, [])
    problems += fproblems
    preds = predictions_record()
    seal = seal_check()
    plan = build_plan(mode)
    sealed_diffs = sealed_plan_check(build_plan("full"))
    if mode == "full":
        if not preds["sha256"]:
            problems.append("sealed predictions missing: %s" % PREDICTIONS)
        if not seal["ok"]:
            problems.append("seal check failed (%s): changed %s, missing %s"
                            % (seal["path"], seal["changed"], seal["missing"]))
        problems += ["plan differs from sealed predictions: %s" % d for d in sealed_diffs]
    validation = {}
    if not problems:
        for a, v in plan["arms"].items():
            ok, argv, text = G.validate_client(v["bin"], CLIENT_FEC, v["m"], v["extra"])
            validation[a] = {"ok": ok, "argv": argv, "output_tail": text}
            if not ok:
                problems.append("arm %s flags rejected by %s: %s" % (a, v["bin"], text))
    if problems:
        return refuse(problems)
    fp = fingerprint(plan, binrep)
    env = G.environment()
    env.update({"binaries": binrep, "help_flags": flags,
                "predictions": preds, "seal_check": seal,
                "sealed_plan_differences": sealed_diffs,
                "arm_flag_validation": validation, "p17_check": chk,
                "runner_sha256": runner_sha256(), "argv": sys.argv,
                "started_at": utc_now(), "pid": os.getpid(),
                "padfec_gen": os.environ.get("PADFEC_GEN")})
    meta = read_json(P["meta"])
    if not meta or meta.get("fp") != fp:
        meta = {"fp": fp, "mode": mode, "plan": plan, "starts": []}
    meta["starts"].append(env)
    meta.pop("finished", None)
    save_result(P["meta"], meta)
    jr = Journal(P["journal"], fp)
    schedule = plan["schedule"]
    cells = {c["cell"]: c for c in plan["cells"]}
    est = estimate(plan)["per_block_s"]
    pending = [b for b in schedule
               if not block_complete(jr.get(unit_key(mode, b["cell"], b["block"])), b)]
    print("g3_stage0 %s: fp %s, %d/%d blocks pending, journal %s"
          % (mode, fp, len(pending), len(schedule), P["journal"]), flush=True)
    start_bins = {t: binrep[t]["sha256"] for t in ("g2", "g3")}
    if pending:
        G.setup()
    servers, cur_cell = {}, None
    t0 = time.monotonic()
    est_done = 0.0
    done_n = len(schedule) - len(pending)
    try:
        for blk in pending:
            key = unit_key(mode, blk["cell"], blk["block"])
            cell = cells[blk["cell"]]
            if blk["cell"] != cur_cell:
                stop_servers(servers)
                servers = start_servers(CONDS[cell["cond"]]["cert"])
                cur_cell = blk["cell"]
            for attempt in (1, 2):
                allowed = [s["pid"] for s in servers.values()]
                busy = G.busy_processes(allowed)
                bins_now = {t: G.sha256_or_none(G.BINS[t]) for t in ("g2", "g3")}
                if busy or bins_now != start_bins:
                    why = busy or ["binary changed: %s" % bins_now]
                    incident(P, {"key": key, "attempt": attempt, "abort": why, "fp": fp})
                    write_status(P, mode=mode, fp=fp, state="aborted", reason=why,
                                 blocks_done=done_n, blocks_total=len(schedule))
                    print("ABORT before %s: %s" % (key, why), file=sys.stderr)
                    return 3
                if not all(G.server_alive(s) for s in servers.values()):
                    stop_servers(servers)
                    servers = start_servers(CONDS[cell["cond"]]["cert"])
                write_status(P, mode=mode, fp=fp, state="running", current=key,
                             attempt=attempt, blocks_done=done_n,
                             blocks_total=len(schedule),
                             elapsed_s=time.monotonic() - t0)
                rec = run_block(blk, cell, servers, attempt, bins_now)
                if block_complete(rec, blk):
                    jr.record(key, rec)
                    if rec["client_errors"]:
                        incident(P, {"key": key, "attempt": attempt, "fp": fp,
                                     "kept_as_data": True,
                                     "client_errors": rec["client_errors"]})
                        print("   %s client errors kept as imputed failures: %s"
                              % (key, ", ".join("%s %d/%d" % (c["arm"], c["n_rows"],
                                                              c["n_planned"])
                                                for c in rec["client_errors"])),
                              flush=True)
                    break
                incident(P, {"key": key, "attempt": attempt, "fp": fp, "err": rec["err"],
                             "segments": [{"arm": s["arm"], "rc": s["rc"], "err": s["err"],
                                           "client_err": s.get("client_err"),
                                           "n_rows": s["n_rows"], "n_planned": s["n_planned"]}
                                          for s in rec["segments"]]})
                print("   %s attempt %d failed: %s" % (key, attempt, rec["err"]),
                      flush=True)
                stop_servers(servers)
                servers = start_servers(CONDS[cell["cond"]]["cert"])
            else:
                write_status(P, mode=mode, fp=fp, state="aborted",
                             reason="block failed twice: %s" % key,
                             blocks_done=done_n, blocks_total=len(schedule))
                print("ABORT: %s failed twice; rerun the same command to resume"
                      % key, file=sys.stderr)
                return 3
            done_n += 1
            est_done += est[(blk["cell"], blk["block"])]
            elapsed = time.monotonic() - t0
            remaining = sum(est[(b["cell"], b["block"])] for b in pending
                            if not jr.has(unit_key(mode, b["cell"], b["block"])))
            eta = remaining * (elapsed / est_done) if est_done else None
            write_status(P, mode=mode, fp=fp, state="running", blocks_done=done_n,
                         blocks_total=len(schedule), elapsed_s=elapsed, eta_s=eta)
            print("   [%3d/%3d] %-10s b%02d %-46s recorded, elapsed %6.0f s, eta %s s"
                  % (done_n, len(schedule), blk["cell"], blk["block"],
                     " ".join(blk["order"]), elapsed,
                     "%.0f" % eta if eta is not None else "?"), flush=True)
    except (KeyboardInterrupt, SystemExit) as exc:
        write_status(P, mode=mode, fp=fp, state="interrupted", blocks_done=done_n,
                     blocks_total=len(schedule))
        return exc.code if isinstance(exc, SystemExit) and exc.code else 130
    finally:
        stop_servers(servers)
    sources, build_fp = G.quicbed_sources()
    meta["finished"] = {"at": utc_now(), "quicbed_sources_sha256": sources,
                        "quicbed_build_style_fingerprint": build_fp,
                        "bins_sha256": {t: G.sha256_or_none(G.BINS[t]) for t in ("g2", "g3")}}
    save_result(P["meta"], meta)
    report = finalize(plan, meta, jr, P)
    write_status(P, mode=mode, fp=fp, state="done", blocks_done=done_n,
                 blocks_total=len(schedule), result=P["result"])
    print_summary(report)
    print("result: %s" % P["result"])
    return 0


def report_only(mode):
    B.harden()
    P = paths(mode)
    meta = read_json(P["meta"])
    if not meta or "fp" not in meta:
        print("no meta file: %s" % P["meta"], file=sys.stderr)
        return 2
    plan = meta["plan"]
    if canon(plan) != build_plan(mode):
        print("note: the recorded plan differs from the current code; analysing the recorded plan")
    jr = Journal(P["journal"], meta["fp"])
    missing = [unit_key(mode, b["cell"], b["block"]) for b in plan["schedule"]
               if not block_complete(jr.get(unit_key(mode, b["cell"], b["block"])), b)]
    if missing:
        print("incomplete: %d blocks missing, first %s" % (len(missing), missing[0]),
              file=sys.stderr)
        return 3
    report = finalize(plan, meta, jr, P)
    print_summary(report)
    print("result: %s" % P["result"])
    return 0


def dry_run():
    B.harden()
    plan = build_plan("full")
    smoke = build_plan("smoke")
    chk = p17_check()
    est = estimate(plan)
    est_s = estimate(smoke)
    print("g3_stage0 dry run: no root, no network, nothing written")
    print("protocol: %s" % VERDICT)
    print()
    print("conditions (checked against %s CONDS, sha256 %s):"
          % (chk["source"], (chk["sha256"] or "?")[:16]))
    for name, row in chk["conds"].items():
        o = row["ours"]
        print("  %-8s = p17 %-7s cert %5d  RTT %5.0f ms  netem rate %g Mbit uplink only"
              "  policy -uplink-mbps %g  -> %s"
              % (name, row["p17_name"], o["cert"], o["rtt_ms"], o["netem_rate_mbit"],
                 o["uplink_policy_mbps"],
                 "match" if row["match"] else "DIFFERENT %s" % row["p17"]))
    print("  harness facts: %s" % ", ".join("%s=%s" % (k, "ok" if v else "NOT CONFIRMED")
                                            for k, v in chk["facts"].items()))
    for n in chk["notes"]:
        print("  note: %s" % n)
    print("  differences: %s" % (chk["differences"] or "none"))
    print()
    print("netem per cell: padbed.set_netem(RTT/2, loss_c2s=loss, rate_up_mbit=2); v0 (client->server):"
          " '%s'; v1 (server->client): '%s'"
          % (G.netem_specs(25.0, 2.0, 2.0)["c2s"], G.netem_specs(25.0, 2.0, 2.0)["s2c"]))
    print()
    print("servers (peer netns, same cert per cell, own stats files, restarted per cell):")
    for tag in ("g2", "g3"):
        print("  %s  %s -mode server -addr %s:%d -certsize <cert> -fec %s -stats %s/srv_%s.json"
              % (tag, G.BINS[tag], B.RX_IP, G.PORTS[tag], SERVER_FEC, G.WORK, tag))
    print()
    print("arms (client in root netns, %s):" % ("taskset %s" % " ".join(B.TASKSET[1:])
                                                if B.TASKSET else "taskset if present"))
    for a, v in plan["arms"].items():
        print("  %-9s %-15s %s :%d lead %d  %s -mode client -addr %s:%d -group %s -n <n> "
              "-fec %s -m %d -gap %dms -timeout %ds -stats %s/cli_stats.json "
              "-uplink-mbps 2 -expect-k %d%s"
              % (a, v["label"], v["bin"], G.PORTS[v["bin"]], v["lead"], G.BINS[v["bin"]],
                 B.RX_IP, G.PORTS[v["bin"]], GROUP, CLIENT_FEC, v["m"], GAP_MS, TIMEOUT_S,
                 G.WORK, EXPECT_K, (" " + " ".join(v["extra"])) if v["extra"] else ""))
    for mode_plan, e in ((plan, est), (smoke, est_s)):
        print()
        total_conns = sum(n for c in mode_plan["cells"] for _a, n in c["arms"])
        print("schedule %s: %d blocks, %d connections"
              % (mode_plan["mode"], len(mode_plan["schedule"]), total_conns))
        for cell in mode_plan["cells"]:
            cond = CONDS[cell["cond"]]
            print("  %s: cert %d, RTT %g ms, loss %g%% c2s, %d blocks, n/arm %s, "
                  "latin %s"
                  % (cell["cell"], cond["cert"], cond["rtt_ms"], cell["loss_pct"],
                     cell["blocks"], ", ".join("%s %d" % (a, n) for a, n in cell["arms"]),
                     "closed" if cell["latin_closed"] else
                     "open, positions %s" % cell["position_counts"]))
            for b in mode_plan["schedule"]:
                if b["cell"] == cell["cell"]:
                    print("    b%02d rot%d  %s" % (b["block"], b["rotation"], "  ".join(
                        "%s:%d" % (a, b["sizes"][a]) for a in b["order"])))
        for c in e["cells"]:
            print("  estimate %-10s %5d conns %3d segments  p17-throughput %6.0f s  "
                  "predicted-HCT %6.0f s" % (c["cell"], c["connections"], c["segments"],
                                             c["p17_throughput_s"], c["predicted_hct_s"]))
        print("  estimated wall clock (%s): %.1f min by p17 throughput, %.1f min by predicted HCT;"
              " plan for %.0f min" % (mode_plan["mode"], e["total_p17_throughput_s"] / 60.0,
                                      e["total_predicted_hct_s"] / 60.0,
                                      math.ceil(e["planning_s"] / 60.0)))
    print("  estimate assumptions: %s" % json.dumps(est["assumptions"], ensure_ascii=False))
    print()
    print("outputs: results %s ; state %s"
          % (os.path.relpath(paths("full")["result"], ROOT),
             ", ".join(os.path.relpath(paths("full")[k], ROOT)
                       for k in ("journal", "meta", "status", "incidents"))))
    print("smoke outputs: %s" % os.path.relpath(paths("smoke")["result"], ROOT))
    print()
    preds = predictions_record()
    print("preflight (informational in dry run):")
    print("  sealed predictions g3/stage0_predictions.json sha256: %s" % preds["sha256"])
    seal = seal_check()
    print("  seal check %s: %s" % (seal["path"], "ok" if seal["ok"] else
                                   "FAILED changed %s missing %s"
                                   % (seal["changed"], seal["missing"])))
    print("  plan vs sealed predictions (arms, n, conditions, 1-RTT cutoffs): %s"
          % (sealed_plan_check(plan) or "match"))
    binrep, problems = G.binary_report()
    for tag in ("g2", "g3"):
        info = binrep[tag]
        print("  %s binary %s: %s" % (tag, info["path"], ("sha256 %s" % info["sha256"])
                                      if info["exists"] else "missing"))
    if sys.platform.startswith("linux"):
        flags, fproblems = G.flag_report(binrep) if not problems else (None, [])
        problems += fproblems
        busy = G.busy_processes()
        print("  other measurements: %s" % (busy or "none"))
        print("  build processes: %s" % (G.load_processes() or "none"))
    else:
        print("  process checks: skipped (not Linux)")
    print("  problems a live run would refuse on: %s" % (problems or "none"))
    print("  live runs also refuse when the p17 check fails, when pgrep -x qamp or /proc shows "
          "another measurement (experiments/p*.py, fixloop, loop2, g3_*), when go/compile "
          "processes run, when a client binary rejects an arm's flags (-n 0 check), and "
          "--full refuses without the sealed predictions file, on a failed seal check "
          "or when the plan differs from the sealed predictions")
    print()
    print("Historical stage-0 execution and report rewriting are disabled in gen33.")
    return 0


def historical_stage0_main(argv=None):
    ap = argparse.ArgumentParser(description="PAD-FEC v3 stage-0 fixed-arm runner (%s)" % VERDICT)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true",
                   help="print schedule, arm mapping and estimate; no root, no network")
    g.add_argument("--smoke", action="store_true",
                   help="tiny real run: %d connections per arm per cell" % SMOKE_N)
    g.add_argument("--full", action="store_true", help="the stage-0 measurement")
    g.add_argument("--report-only", nargs="?", const="full", choices=("full", "smoke"),
                   help="rebuild the result file from the journal")
    args = ap.parse_args(argv)
    if args.dry_run:
        return dry_run()
    if args.report_only:
        return report_only(args.report_only)
    return live("smoke" if args.smoke else "full")


def main(argv=None):
    print("Historical stage-0 execution is disabled in gen33.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
