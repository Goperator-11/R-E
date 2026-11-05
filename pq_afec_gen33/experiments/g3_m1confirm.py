from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import signal
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import g3_stage0 as S
import g3bed as G
import padbed as B
from _journal import Journal, save_result, runtime_context

MODE = "m1confirm"
TAG = "g3_m1confirm"
PROTOCOL = "g3/PROTOCOL_m1confirm.md"
PREDICTIONS_REL = "g3/m1confirm_predictions.json"
SEAL_REL = "g3/SEAL_m1confirm.json"
PREDICTIONS = os.path.join(ROOT, PREDICTIONS_REL)
SEAL = os.path.join(ROOT, SEAL_REL)
SEALED_FILES = ("g3/PROTOCOL_m1confirm.md", "g3/m1confirm_predictions.json",
                "experiments/g3_m1confirm.py", "experiments/g3_stage0.py",
                "experiments/g3bed.py", "experiments/padbed.py",
                "experiments/_journal.py", "experiments/blockstat.py")
STAGE0_RESULT = "g3/RESULT_stage0.md"
G3_STAGE0_SHA256 = "d519b331962cbcf2103bf572d228cfb199eae4e588eedf93f8305c0d95b01f91"
CELL = {"cell": "bigcert_2", "pred_id": "bigcert_loss2", "cond": "bigcert",
        "loss_pct": 2.0, "blocks": 10, "arms": [("v2m1", 400), ("m4L3", 400)]}
TEST_ARM = "m4L3"
BASE_ARM = "v2m1"
ONE_RTT_MIN = 0.85
DIFF_MAX_MS = -18.0
CREDIT_FRAC_MIN = 0.90
LIVE_CMD = "Historical M1 confirmation is disabled in gen33."
RULE = {
    "name": "M1'",
    "cell": CELL["cell"],
    "a": {"quantity": "one_rtt_rate(m4L3), one_rtt = ok and hct_ms < nominal cutoff, "
                      "denominator = planned trials",
          "op": ">=", "threshold": ONE_RTT_MIN},
    "b": {"quantity": "mean_planned_imputed_ms(m4L3) - mean_planned_imputed_ms(v2m1), "
                      "failed or missing trials imputed at %.0f ms" % S.IMPUTE_MS,
          "op": "<=", "threshold": DIFF_MAX_MS},
    "c_prime": {"credit_frac": {"quantity": "g3 server, m4L3 segments: connections with "
                                            "tx_dgrams > 0 whose beff_credit == lead (3); "
                                            "a missing or non-integer beff_credit counts as "
                                            "not 3",
                                "op": ">=", "threshold": CREDIT_FRAC_MIN},
                "v3_equal": "credit_parities_v3 == credit_parities (both reported) in every "
                            "planned m4L3 segment",
                "flags": "client rows of m4L3: m_used, layout, lead and "
                         "first_flight_lead_dgrams never differ from the arm"},
    "pass": "a and b and c_prime",
    "reported_only": "1-RTT rate of m4L3 by server beff_credit (== 3 vs < 3) on segments "
                     "where client rows and server connections join by time order",
}
JOIN_RULE = ("per m4L3 segment: client rows i = 0..n-1 complete and in order; server new "
             "connections count == rows; every connection has first_rx_ns > 0; consecutive "
             "first_rx_ns gaps >= the client gap %d ms; conn_acct_dropped and "
             "conn_acct_alias_conflicts are 0 in that segment; then the k-th connection by "
             "first_rx_ns is client row k (the client opens one connection at a time)"
             % S.GAP_MS)


def runner_sha256():
    return G.sha256_or_none(os.path.abspath(__file__))


def paths():
    return {"journal": os.path.join(B.STATE, TAG + "_units.jsonl"),
            "meta": os.path.join(B.STATE, TAG + "_meta.json"),
            "status": os.path.join(B.STATE, TAG + "_status.json"),
            "incidents": os.path.join(B.STATE, TAG + "_incidents.jsonl"),
            "result": os.path.join(B.RESULTS, TAG + ".json")}


def build_plan():
    c = CELL
    arms = [a for a, _n in c["arms"]]
    totals = dict(c["arms"])
    nblk = c["blocks"]
    if max(totals.values()) != S.SEGMENT_N * nblk:
        raise ValueError("%s: %d blocks do not give %d-connection segments"
                         % (c["cell"], nblk, S.SEGMENT_N))
    sizes = {a: S.split(totals[a], nblk) for a in arms}
    positions = {a: [0] * len(arms) for a in arms}
    schedule = []
    for b in range(nblk):
        r = b % len(arms)
        order = arms[r:] + arms[:r]
        for pos, a in enumerate(order):
            positions[a][pos] += 1
        schedule.append({"cell": c["cell"], "block": b, "rotation": r, "order": order,
                         "sizes": {a: sizes[a][b] for a in order}})
    cond = S.CONDS[c["cond"]]
    cells = [{"cell": c["cell"], "pred_id": c["pred_id"], "cond": c["cond"],
              "loss_pct": c["loss_pct"], "blocks": nblk,
              "arms": [[a, totals[a]] for a in arms], "position_counts": positions,
              "latin_closed": nblk % len(arms) == 0}]
    plan = {"schema": "g3_m1confirm.plan.v1", "mode": MODE, "protocol": PROTOCOL,
            "group": S.GROUP, "expect_k": S.EXPECT_K, "gap_ms": S.GAP_MS,
            "timeout_s": S.TIMEOUT_S, "impute_ms": S.IMPUTE_MS,
            "server_fec": S.SERVER_FEC, "client_fec": S.CLIENT_FEC,
            "conds": {c["cond"]: cond}, "arms": {a: S.ARMS[a] for a in arms},
            "cells": cells, "schedule": schedule, "bins": G.BINS, "ports": G.PORTS,
            "bins_sha256_required": {"g2": G.G2_FROZEN_SHA256, "g3": G3_STAGE0_SHA256},
            "work": G.WORK, "settle_s": {c["cond"]: S.settle_s(cond)},
            "loss_direction": "client_to_server_only",
            "netem": "padbed.set_netem(rtt/2, loss_c2s=loss, rate_up_mbit=rate), Bernoulli loss",
            "rotation": "cyclic Latin as in stage 0: block b runs arms[b mod A:] + arms[:b mod A]",
            "segment_n": S.SEGMENT_N,
            "client_failure_rule": "client crash or short output is data: the missing "
                                   "trials are imputed and the block continues; only server "
                                   "death, missing server stats or a client that could not "
                                   "be executed (rc 126/127) retry the block",
            "server_lifecycle": "both servers start fresh at the first block run and after "
                                "an infrastructure retry",
            "one_rtt_rule": S.ONE_RTT_RULE, "imputation": S.IMPUTATION,
            "decision_rule": RULE, "join_rule": JOIN_RULE}
    return S.canon(plan)


def predictions_record():
    pred = S.read_json(PREDICTIONS) or {}
    return {"path": PREDICTIONS_REL, "sha256": G.sha256_or_none(PREDICTIONS),
            "copied_from": pred.get("copied_from")}


def seal_check():
    out = {"path": SEAL_REL, "sha256": G.sha256_or_none(SEAL), "changed": [],
           "missing": [], "uncovered": [], "ok": False}
    seal = S.read_json(SEAL)
    files = (seal or {}).get("sha256")
    if not isinstance(files, dict) or not files:
        out["missing"].append(SEAL_REL)
        return out
    for rel, h in sorted(files.items()):
        now = G.sha256_or_none(os.path.join(ROOT, rel))
        if now is None:
            out["missing"].append(rel)
        elif now != h:
            out["changed"].append(rel)
    out["uncovered"] = [rel for rel in SEALED_FILES if rel not in files]
    out["sealed_utc"] = seal.get("sealed_utc")
    out["ok"] = not out["changed"] and not out["missing"] and not out["uncovered"]
    return out


def sealed_plan_check(plan):
    pred = S.read_json(PREDICTIONS)
    if not isinstance(pred, dict) or not isinstance(pred.get("conditions"), dict):
        return ["sealed predictions unreadable: %s" % PREDICTIONS]
    diffs = []
    for cell in plan["cells"]:
        pc = pred["conditions"].get(cell["pred_id"])
        if not isinstance(pc, dict):
            diffs.append("%s: no sealed condition %s" % (cell["cell"], cell["pred_id"]))
            continue
        cond = S.CONDS[cell["cond"]]
        for k, ours in (("cert", cond["cert"]), ("rtt_ms", cond["rtt_ms"]),
                        ("uplink_mbps", cond["uplink_policy_mbps"]),
                        ("loss_pct", cell["loss_pct"])):
            if pc.get(k) != ours:
                diffs.append("%s.%s: ours %r sealed %r" % (cell["cell"], k, ours, pc.get(k)))
        sealed_arms = pc.get("arms") or {}
        ours_ids = [S.ARMS[a]["pred_id"] for a, _n in cell["arms"]]
        if sorted(ours_ids) != sorted(sealed_arms):
            diffs.append("%s: arms %s vs sealed %s" % (cell["cell"], ours_ids,
                                                       sorted(sealed_arms)))
        for a, n in cell["arms"]:
            sa = sealed_arms.get(S.ARMS[a]["pred_id"])
            if not isinstance(sa, dict):
                continue
            if sa.get("n_planned") != n:
                diffs.append("%s/%s: n %d vs sealed %r" % (cell["cell"], a, n,
                                                           sa.get("n_planned")))
            cut = S.nominal_threshold(S.ARMS[a]["lead"], cond)
            if (not isinstance(sa.get("one_rtt_cutoff_ms"), (int, float))
                    or abs(cut - sa["one_rtt_cutoff_ms"]) > 1e-6):
                diffs.append("%s/%s: 1-RTT cutoff %.6f vs sealed %r"
                             % (cell["cell"], a, cut, sa.get("one_rtt_cutoff_ms")))
    rule = pred.get("decision_rule") or {}
    for key, ours in (("a", ONE_RTT_MIN), ("b", DIFF_MAX_MS), ("c_prime", CREDIT_FRAC_MIN)):
        theirs = (rule.get(key) or {}).get("threshold")
        if theirs != ours:
            diffs.append("decision_rule.%s threshold: ours %r sealed %r" % (key, ours, theirs))
    if rule.get("condition") != CELL["pred_id"]:
        diffs.append("decision_rule.condition: ours %r sealed %r"
                     % (CELL["pred_id"], rule.get("condition")))
    return diffs


def fingerprint(plan, binrep):
    h = hashlib.sha256()
    h.update(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    h.update(json.dumps(runtime_context(), sort_keys=True).encode("utf-8"))
    for tag in ("g2", "g3"):
        h.update(("%s=%s;" % (tag, binrep[tag].get("sha256"))).encode())
    for rel in SEALED_FILES + (SEAL_REL,):
        h.update(rel.encode())
        h.update((G.sha256_or_none(os.path.join(ROOT, rel)) or "MISSING").encode())
    return h.hexdigest()[:16]


def join_segment(seg):
    rows = seg.get("rows") or []
    conns = seg.get("server_new_conns") or []
    n = seg.get("n_planned")
    if len(rows) != n or [r.get("i") for r in rows] != list(range(len(rows))):
        return None, "client rows incomplete or out of order"
    if len(conns) != len(rows):
        return None, "server connections %d != client rows %d" % (len(conns), len(rows))
    if not all(type(c.get("first_rx_ns")) is int and c["first_rx_ns"] > 0 for c in conns):
        return None, "server connection without first_rx_ns"
    d = seg.get("server_delta") or {}
    if d.get("conn_acct_dropped") or d.get("conn_acct_alias_conflicts"):
        return None, "server connection accounting dropped or aliased"
    cs = sorted(conns, key=lambda c: c["first_rx_ns"])
    gaps = [(y["first_rx_ns"] - x["first_rx_ns"]) / 1e6 for x, y in zip(cs, cs[1:])]
    if gaps and min(gaps) < S.GAP_MS:
        return None, "first_rx gap %.3f ms < client gap %d ms" % (min(gaps), S.GAP_MS)
    return list(zip(rows, cs)), ""


def credit_class(conn, lead):
    bc = conn.get("beff_credit")
    if (conn.get("tx_dgrams") or 0) <= 0 or type(bc) is not int:
        return "no_tx_or_unknown"
    if bc == lead:
        return "eq_lead"
    return "lt_lead" if bc < lead else "gt_lead"


def credit_vs_one_rtt(plan, jr):
    cell = plan["cells"][0]
    cond = S.CONDS[cell["cond"]]
    lead = S.ARMS[TEST_ARM]["lead"]
    cut = S.nominal_threshold(lead, cond)
    groups = {k: {"n": 0, "one_rtt": 0} for k in ("eq_lead", "lt_lead", "gt_lead",
                                                  "no_tx_or_unknown")}
    joined, excluded = 0, []
    for b in plan["schedule"]:
        rec = jr.get(S.unit_key(plan["mode"], b["cell"], b["block"])) or {}
        for s in rec.get("segments", []):
            if s.get("arm") != TEST_ARM:
                continue
            pairs, why = join_segment(s)
            if pairs is None:
                excluded.append({"block": b["block"], "reason": why})
                continue
            joined += 1
            for r, c in pairs:
                g = groups[credit_class(c, lead)]
                g["n"] += 1
                g["one_rtt"] += int(bool(r.get("ok")) and r["ms"] < cut)
    for g in groups.values():
        g["one_rtt_rate"] = (g["one_rtt"] / g["n"]) if g["n"] else None
    return {"reported_not_judged": True, "arm": TEST_ARM, "lead": lead,
            "one_rtt_cutoff_ms": cut, "join_rule": JOIN_RULE,
            "segments_joined": joined, "segments_excluded": excluded,
            "groups": groups}


def m1_prime(cell):
    m4 = cell["arms"][TEST_ARM]
    lead = S.ARMS[TEST_ARM]["lead"]
    d = S.contrast({cell["cell"]: cell}, cell["cell"], TEST_ARM, BASE_ARM)
    srv = m4["server"]
    n_tx = srv["conns_with_tx"]
    n_eq = srv["beff_credit_hist"].get(str(lead), 0)
    frac = (n_eq / n_tx) if n_tx else None
    per = [{"block": p["block"], "credit_parities": p["srv_credit"],
            "credit_parities_v3": p["srv_credit_v3"],
            "equal": type(p["srv_credit_v3"]) is int and p["srv_credit_v3"] == p["srv_credit"]}
           for p in srv["lead_credit"]["per_segment"]]
    v3_ok = len(per) == cell["blocks_planned"] and all(p["equal"] for p in per)
    flags_ok = not any(m4["flag_mismatches"].values())
    rate = m4["one_rtt_rate"]
    diff = d["overall_diff_ms"]
    out = {"rule": RULE, "protocol": PROTOCOL,
           "a": {"one_rtt_rate": rate, "threshold": ONE_RTT_MIN,
                 "cutoff_ms": m4["one_rtt_threshold_nominal_ms"],
                 "ok": rate is not None and rate >= ONE_RTT_MIN},
           "b": {"diff_ms": diff, "threshold": DIFF_MAX_MS, "paired_blocks": d,
                 "ok": diff is not None and diff <= DIFF_MAX_MS},
           "c_prime": {"conns_with_tx": n_tx, "beff_credit_eq_lead": n_eq,
                       "beff_credit_hist": srv["beff_credit_hist"],
                       "frac_beff_credit_eq_lead": frac, "threshold": CREDIT_FRAC_MIN,
                       "frac_ok": frac is not None and frac >= CREDIT_FRAC_MIN,
                       "v3_equal_every_segment": v3_ok, "per_segment": per,
                       "flag_mismatches": m4["flag_mismatches"],
                       "flag_mismatches_zero": flags_ok},
           "stage0_c_reported_only": {"bound_ok": srv["lead_credit"]["bound_ok"],
                                      "rule": srv["lead_credit"]["rule"]}}
    out["c_prime"]["ok"] = bool(out["c_prime"]["frac_ok"] and v3_ok and flags_ok)
    out["pass"] = bool(out["a"]["ok"] and out["b"]["ok"] and out["c_prime"]["ok"])
    return out


def finalize(plan, meta, jr, P):
    cell_list = [S.summarize_cell(c, plan, jr) for c in plan["cells"]]
    report = {"schema": "g3_m1confirm.result.v1", "mode": MODE, "confirmatory": True,
              "protocol": PROTOCOL, "seal": SEAL_REL,
              "stage0_m1": "FAIL as recorded in %s; this run does not overturn it"
                           % STAGE0_RESULT,
              "generated_at": S.utc_now(),
              "journal": {"path": os.path.relpath(P["journal"], ROOT).replace("\\", "/"),
                          "fingerprint": meta["fp"]},
              "plan": plan, "env_starts": meta["starts"], "finished": meta.get("finished"),
              "one_rtt_rule": S.ONE_RTT_RULE, "imputation": S.IMPUTATION,
              "cells": cell_list,
              "m1_prime": m1_prime(cell_list[0]),
              "supporting": {"credit_vs_one_rtt": credit_vs_one_rtt(plan, jr)}}
    report["integrity"] = S.integrity(cell_list, plan, meta, jr, P)
    save_result(P["result"], report)
    return report


def fmt(v, spec):
    return (spec % v) if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)


def print_summary(report):
    print()
    print("=" * 100)
    for c in report["cells"]:
        print("%s  cert %d  RTT %g  loss %g%%  blocks %d/%d" % (
            c["cell"], c["cert"], c["rtt_ms"], c["loss_pct"], c["blocks_done"],
            c["blocks_planned"]))
        for a, v in c["arms"].items():
            print("   %-6s %s n %4d/%4d ok %4d fail %3d  mean* %8.2f  1RTT %.4f  "
                  "ff-up %7.0f B  beff_credit %s" % (
                      a, v["binary"], v["n_returned"], v["n_requested"], v["ok"],
                      v["failed"], v["mean_planned_imputed_ms"] or -1,
                      v["one_rtt_rate"] or 0.0, v["first_flight_uplink_bytes_mean"] or 0.0,
                      json.dumps(v["server"]["beff_credit_hist"])))
    m = report["m1_prime"]
    print("M1' %s  (a) 1-RTT %s >= %.2f %s  (b) diff %s ms <= %.0f %s  "
          "(c') frac %s >= %.2f, v3 equal %s, flags zero %s -> %s" % (
              "PASS" if m["pass"] else "FAIL",
              fmt(m["a"]["one_rtt_rate"], "%.4f"), ONE_RTT_MIN,
              "ok" if m["a"]["ok"] else "no",
              fmt(m["b"]["diff_ms"], "%.2f"), DIFF_MAX_MS, "ok" if m["b"]["ok"] else "no",
              fmt(m["c_prime"]["frac_beff_credit_eq_lead"], "%.4f"), CREDIT_FRAC_MIN,
              m["c_prime"]["v3_equal_every_segment"], m["c_prime"]["flag_mismatches_zero"],
              "ok" if m["c_prime"]["ok"] else "no"))
    sup = report["supporting"]["credit_vs_one_rtt"]
    print("reported only: segments joined %d, excluded %d; %s" % (
        sup["segments_joined"], len(sup["segments_excluded"]),
        ", ".join("%s %d/%d" % (k, g["one_rtt"], g["n"]) for k, g in sup["groups"].items())))
    print("integrity:", json.dumps({k: v for k, v in report["integrity"].items()
                                    if k in ("crc_fail_total", "global_acct_violations",
                                             "conn_stack_gt_rx", "binaries_constant",
                                             "quicbed_sources_unchanged",
                                             "attempts_gt_1", "client_error_segments",
                                             "missing_trials")}))


def binaries():
    binrep, problems = G.binary_report()
    g3 = binrep.get("g3") or {}
    if g3.get("exists") and g3.get("sha256") != G3_STAGE0_SHA256:
        problems.append("g3 binary sha256 %s is not the stage-0 g3 binary %s"
                        % (g3.get("sha256"), G3_STAGE0_SHA256))
    return binrep, problems


def preflight(plan):
    binrep, problems = binaries()
    flags, fproblems = G.flag_report(binrep) if not problems else (None, [])
    problems += fproblems
    preds = predictions_record()
    seal = seal_check()
    sealed_diffs = sealed_plan_check(plan)
    if not preds["sha256"]:
        problems.append("sealed predictions missing: %s" % PREDICTIONS)
    if not seal["ok"]:
        problems.append("seal check failed (%s): changed %s, missing %s, not covered %s"
                        % (seal["path"], seal["changed"], seal["missing"],
                           seal["uncovered"]))
    problems += ["plan differs from sealed predictions: %s" % d for d in sealed_diffs]
    return binrep, flags, preds, seal, sealed_diffs, problems


def live():
    B.harden()
    signal.signal(signal.SIGTERM, S._sigterm)
    if not sys.platform.startswith("linux"):
        return S.refuse(["the live run is inside WSL Ubuntu: %s" % LIVE_CMD])
    B.require_root()
    os.environ.setdefault("PADFEC_GEN", S.GEN_DEFAULT)
    P = paths()
    busy = G.busy_processes()
    if busy:
        return S.refuse(["another measurement is running"] + busy)
    load = G.load_processes()
    if load:
        return S.refuse(["build or compile processes are running"] + load)
    chk = S.p17_check()
    if not chk["ok"]:
        return S.refuse(["p17 condition check failed"] + chk["differences"])
    plan = build_plan()
    binrep, flags, preds, seal, sealed_diffs, problems = preflight(plan)
    validation = {}
    if not problems:
        for a, v in plan["arms"].items():
            ok, argv, text = G.validate_client(v["bin"], S.CLIENT_FEC, v["m"], v["extra"])
            validation[a] = {"ok": ok, "argv": argv, "output_tail": text}
            if not ok:
                problems.append("arm %s flags rejected by %s: %s" % (a, v["bin"], text))
    if problems:
        return S.refuse(problems)
    fp = fingerprint(plan, binrep)
    env = G.environment()
    env.update({"binaries": binrep, "help_flags": flags, "predictions": preds,
                "seal_check": seal, "sealed_plan_differences": sealed_diffs,
                "arm_flag_validation": validation, "p17_check": chk,
                "runner_sha256": runner_sha256(),
                "stage0_module_sha256": S.runner_sha256(), "argv": sys.argv,
                "started_at": S.utc_now(), "pid": os.getpid(),
                "padfec_gen": os.environ.get("PADFEC_GEN")})
    meta = S.read_json(P["meta"])
    if not meta or meta.get("fp") != fp:
        meta = {"fp": fp, "mode": MODE, "plan": plan, "starts": []}
    meta["starts"].append(env)
    meta.pop("finished", None)
    save_result(P["meta"], meta)
    jr = Journal(P["journal"], fp)
    schedule = plan["schedule"]
    cells = {c["cell"]: c for c in plan["cells"]}
    est = S.estimate(plan)["per_block_s"]
    pending = [b for b in schedule
               if not S.block_complete(jr.get(S.unit_key(MODE, b["cell"], b["block"])), b)]
    print("g3_m1confirm: fp %s, %d/%d blocks pending, journal %s"
          % (fp, len(pending), len(schedule), P["journal"]), flush=True)
    start_bins = {t: binrep[t]["sha256"] for t in ("g2", "g3")}
    if pending:
        G.setup()
    servers, cur_cell = {}, None
    t0 = time.monotonic()
    est_done = 0.0
    done_n = len(schedule) - len(pending)
    try:
        for blk in pending:
            key = S.unit_key(MODE, blk["cell"], blk["block"])
            cell = cells[blk["cell"]]
            cert = S.CONDS[cell["cond"]]["cert"]
            if blk["cell"] != cur_cell:
                S.stop_servers(servers)
                servers = S.start_servers(cert)
                cur_cell = blk["cell"]
            for attempt in (1, 2):
                allowed = [s["pid"] for s in servers.values()]
                busy = G.busy_processes(allowed)
                bins_now = {t: G.sha256_or_none(G.BINS[t]) for t in ("g2", "g3")}
                if busy or bins_now != start_bins:
                    why = busy or ["binary changed: %s" % bins_now]
                    S.incident(P, {"key": key, "attempt": attempt, "abort": why, "fp": fp})
                    S.write_status(P, mode=MODE, fp=fp, state="aborted", reason=why,
                                   blocks_done=done_n, blocks_total=len(schedule))
                    print("ABORT before %s: %s" % (key, why), file=sys.stderr)
                    return 3
                if not all(G.server_alive(s) for s in servers.values()):
                    S.stop_servers(servers)
                    servers = S.start_servers(cert)
                S.write_status(P, mode=MODE, fp=fp, state="running", current=key,
                               attempt=attempt, blocks_done=done_n,
                               blocks_total=len(schedule), elapsed_s=time.monotonic() - t0)
                rec = S.run_block(blk, cell, servers, attempt, bins_now)
                rec["runner_sha256"] = runner_sha256()
                rec["stage0_module_sha256"] = S.runner_sha256()
                if S.block_complete(rec, blk):
                    jr.record(key, rec)
                    if rec["client_errors"]:
                        S.incident(P, {"key": key, "attempt": attempt, "fp": fp,
                                       "kept_as_data": True,
                                       "client_errors": rec["client_errors"]})
                        print("   %s client errors kept as imputed failures: %s"
                              % (key, ", ".join("%s %d/%d" % (c["arm"], c["n_rows"],
                                                              c["n_planned"])
                                                for c in rec["client_errors"])), flush=True)
                    break
                S.incident(P, {"key": key, "attempt": attempt, "fp": fp, "err": rec["err"],
                               "segments": [{"arm": s["arm"], "rc": s["rc"], "err": s["err"],
                                             "client_err": s.get("client_err"),
                                             "n_rows": s["n_rows"],
                                             "n_planned": s["n_planned"]}
                                            for s in rec["segments"]]})
                print("   %s attempt %d failed: %s" % (key, attempt, rec["err"]), flush=True)
                S.stop_servers(servers)
                servers = S.start_servers(cert)
            else:
                S.write_status(P, mode=MODE, fp=fp, state="aborted",
                               reason="block failed twice: %s" % key,
                               blocks_done=done_n, blocks_total=len(schedule))
                print("ABORT: %s failed twice; rerun the same command to resume" % key,
                      file=sys.stderr)
                return 3
            done_n += 1
            est_done += est[(blk["cell"], blk["block"])]
            elapsed = time.monotonic() - t0
            remaining = sum(est[(b["cell"], b["block"])] for b in pending
                            if not jr.has(S.unit_key(MODE, b["cell"], b["block"])))
            eta = remaining * (elapsed / est_done) if est_done else None
            S.write_status(P, mode=MODE, fp=fp, state="running", blocks_done=done_n,
                           blocks_total=len(schedule), elapsed_s=elapsed, eta_s=eta)
            print("   [%2d/%2d] %-10s b%02d %-12s recorded, elapsed %5.0f s, eta %s s"
                  % (done_n, len(schedule), blk["cell"], blk["block"],
                     " ".join(blk["order"]), elapsed,
                     "%.0f" % eta if eta is not None else "?"), flush=True)
    except (KeyboardInterrupt, SystemExit) as exc:
        S.write_status(P, mode=MODE, fp=fp, state="interrupted", blocks_done=done_n,
                       blocks_total=len(schedule))
        return exc.code if isinstance(exc, SystemExit) and exc.code else 130
    finally:
        S.stop_servers(servers)
    sources, build_fp = G.quicbed_sources()
    meta["finished"] = {"at": S.utc_now(), "quicbed_sources_sha256": sources,
                        "quicbed_build_style_fingerprint": build_fp,
                        "bins_sha256": {t: G.sha256_or_none(G.BINS[t]) for t in ("g2", "g3")}}
    save_result(P["meta"], meta)
    report = finalize(plan, meta, jr, P)
    S.write_status(P, mode=MODE, fp=fp, state="done", blocks_done=done_n,
                   blocks_total=len(schedule), result=P["result"])
    print_summary(report)
    print("result: %s" % P["result"])
    return 0


def report_only():
    B.harden()
    P = paths()
    meta = S.read_json(P["meta"])
    if not meta or "fp" not in meta:
        print("no meta file: %s" % P["meta"], file=sys.stderr)
        return 2
    plan = meta["plan"]
    if S.canon(plan) != build_plan():
        print("note: the recorded plan differs from the current code; analysing the recorded plan")
    jr = Journal(P["journal"], meta["fp"])
    missing = [S.unit_key(MODE, b["cell"], b["block"]) for b in plan["schedule"]
               if not S.block_complete(jr.get(S.unit_key(MODE, b["cell"], b["block"])), b)]
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
    plan = build_plan()
    cell = plan["cells"][0]
    cond = S.CONDS[cell["cond"]]
    chk = S.p17_check()
    est = S.estimate(plan)
    pred = S.read_json(PREDICTIONS) or {}
    print("g3_m1confirm dry run: no root, no network, nothing written")
    print("protocol: %s, sealed by %s" % (PROTOCOL, SEAL_REL))
    print("stage-0 M1 stays FAIL (%s); this run does not overturn it" % STAGE0_RESULT)
    print()
    row = chk["conds"][cell["cond"]]
    print("condition %s = p17 %s: cert %d, RTT %g ms, netem rate %g Mbit uplink only, "
          "policy -uplink-mbps %g, loss %g%% client->server only -> p17 %s"
          % (cell["cond"], row["p17_name"], cond["cert"], cond["rtt_ms"],
             cond["netem_rate_mbit"], cond["uplink_policy_mbps"], cell["loss_pct"],
             "match" if row["match"] else "DIFFERENT %s" % row["p17"]))
    print("  same cell as stage-0 bigcert_2: %s"
          % ({k: v for k, v in next(c for c in S.CELLS if c["cell"] == "bigcert_2").items()
              if k in ("cond", "loss_pct")} == {"cond": cell["cond"],
                                                "loss_pct": cell["loss_pct"]}))
    print("  p17 check differences: %s" % (chk["differences"] or "none"))
    spec = G.netem_specs(cond["rtt_ms"] / 2.0, cell["loss_pct"], cond["netem_rate_mbit"])
    print("  netem v0 (client->server) '%s'; v1 (server->client) '%s'"
          % (spec["c2s"], spec["s2c"]))
    print()
    print("servers (peer netns, cert %d, own stats files):" % cond["cert"])
    for tag in ("g2", "g3"):
        print("  %s  %s -mode server -addr %s:%d -certsize %d -fec %s -stats %s/srv_%s.json"
              % (tag, G.BINS[tag], B.RX_IP, G.PORTS[tag], cond["cert"], S.SERVER_FEC,
                 G.WORK, tag))
    print()
    print("arms (client in root netns):")
    for a, _n in cell["arms"]:
        v = plan["arms"][a]
        print("  %-5s %-6s %s :%d lead %d  1-RTT cutoff %.3f ms  %s -mode client -addr %s:%d "
              "-group %s -n <n> -fec %s -m %d -gap %dms -timeout %ds -stats %s/cli_stats.json "
              "-uplink-mbps %g -expect-k %d%s"
              % (a, v["label"], v["bin"], G.PORTS[v["bin"]], v["lead"],
                 S.nominal_threshold(v["lead"], cond), G.BINS[v["bin"]], B.RX_IP,
                 G.PORTS[v["bin"]], S.GROUP, S.CLIENT_FEC, v["m"], S.GAP_MS, S.TIMEOUT_S,
                 G.WORK, cond["uplink_policy_mbps"], S.EXPECT_K,
                 (" " + " ".join(v["extra"])) if v["extra"] else ""))
    print()
    total = sum(n for _a, n in cell["arms"])
    print("schedule %s: %d blocks, %d connections, n/arm %s, latin %s"
          % (plan["mode"], len(plan["schedule"]), total,
             ", ".join("%s %d" % (a, n) for a, n in cell["arms"]),
             "closed, positions %s" % cell["position_counts"] if cell["latin_closed"]
             else "open, positions %s" % cell["position_counts"]))
    for b in plan["schedule"]:
        print("  b%02d rot%d  %s" % (b["block"], b["rotation"], "  ".join(
            "%s:%d" % (a, b["sizes"][a]) for a in b["order"])))
    for c in est["cells"]:
        print("  estimate %s: %d conns, %d segments, p17-throughput %.0f s, predicted-HCT %.0f s;"
              " plan for %.0f min" % (c["cell"], c["connections"], c["segments"],
                                     c["p17_throughput_s"], c["predicted_hct_s"],
                                     math.ceil(est["planning_s"] / 60.0)))
    print()
    pc = (pred.get("conditions") or {}).get(cell["pred_id"]) or {}
    pa = pc.get("arms") or {}
    rule = pred.get("decision_rule") or {}
    print("decision rule M1' (all three):")
    print("  (a) one_rtt_rate(m4L3) >= %.2f; sealed stage-0 prediction %s"
          % (ONE_RTT_MIN, fmt((pa.get("m4L3") or {}).get("pred_one_rtt_frac"), "%.4f")))
    print("  (b) mean(m4L3) - mean(v2m1) <= %.0f ms over all planned trials, failures at %.0f ms;"
          " sealed stage-0 prediction %s ms"
          % (DIFF_MAX_MS, S.IMPUTE_MS, fmt((rule.get("b") or {}).get("predicted"), "%.2f")))
    print("  (c') g3 server, m4L3 connections with tx_dgrams > 0: share with beff_credit == %d"
          " >= %.2f; credit_parities_v3 == credit_parities in every m4L3 segment; zero m4L3"
          " client flag mismatches" % (S.ARMS[TEST_ARM]["lead"], CREDIT_FRAC_MIN))
    print("  reported only: m4L3 1-RTT rate for beff_credit == 3 vs < 3; join: %s" % JOIN_RULE)
    print()
    P = paths()
    print("outputs: %s ; %s" % (os.path.relpath(P["result"], ROOT).replace("\\", "/"),
                                ", ".join(os.path.relpath(P[k], ROOT).replace("\\", "/")
                                          for k in ("journal", "meta", "status", "incidents"))))
    print()
    print("preflight (informational in dry run):")
    preds = predictions_record()
    print("  predictions %s sha256: %s" % (PREDICTIONS_REL, preds["sha256"]))
    print("  copied from: %s" % json.dumps(preds["copied_from"], ensure_ascii=False))
    seal = seal_check()
    print("  seal check %s (sealed %s): %s" % (
        seal["path"], seal.get("sealed_utc"), "ok" if seal["ok"] else
        "FAILED changed %s missing %s not covered %s"
        % (seal["changed"], seal["missing"], seal["uncovered"])))
    print("  plan vs sealed predictions (condition, arms, n, 1-RTT cutoffs, thresholds): %s"
          % (sealed_plan_check(plan) or "match"))
    binrep, problems = binaries()
    print("  required binaries: g2 frozen %s, g3 stage-0 %s"
          % (G.G2_FROZEN_SHA256, G3_STAGE0_SHA256))
    for tag in ("g2", "g3"):
        info = binrep[tag]
        print("  %s binary %s: %s" % (tag, info["path"], ("sha256 %s" % info["sha256"])
                                      if info["exists"] else "missing"))
    if sys.platform.startswith("linux"):
        flags, fproblems = G.flag_report(binrep) if not problems else (None, [])
        problems += fproblems
        print("  other measurements: %s" % (G.busy_processes() or "none"))
        print("  build processes: %s" % (G.load_processes() or "none"))
    else:
        print("  process checks: skipped (not Linux)")
    print("  problems a live run would refuse on: %s" % (problems or "none"))
    print("  --full also refuses when another measurement or a build runs, when the p17 check"
          " fails, when a client binary rejects an arm's flags, when %s does not cover %s or"
          " a sealed file changed, and when the plan differs from %s"
          % (SEAL_REL, ", ".join(SEALED_FILES), PREDICTIONS_REL))
    print()
    print("live command (one WSL invocation, /tmp is a tmpfs):")
    print("  %s" % LIVE_CMD)
    print("report again from the journal: python3 experiments/g3_m1confirm.py --report-only")
    return 0


def historical_m1_main(argv=None):
    ap = argparse.ArgumentParser(description="PAD-FEC v3 M1 re-confirmation (%s)" % PROTOCOL)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true",
                   help="print plan, rule and preflight; no root, no network")
    g.add_argument("--full", action="store_true", help="the sealed M1 re-confirmation run")
    g.add_argument("--report-only", action="store_true",
                   help="rebuild the result file from the journal")
    args = ap.parse_args(argv)
    if args.dry_run:
        return dry_run()
    if args.report_only:
        return report_only()
    return live()


def main(argv=None):
    print("Historical M1 confirmation is disabled in gen33.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
