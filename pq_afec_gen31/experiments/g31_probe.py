from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import signal
import statistics
import subprocess
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import g3_m1confirm as M
import g3_stage0 as S
import g3bed as G
import padbed as B
from _journal import Journal, save_result, runtime_context

LABEL = "development (not confirmatory)"
TAG = "g31_probe"
GEN_DEFAULT = "g31probe_20261002"
QUESTION = ("what the quic-go server sends in its first flight (datagram sizes, cumulative "
            "bytes) and when the amplification limit blocks it, per fixed layout; why delta=1 "
            "does not buy the extra round trip at cert 6000 / RTT 80 / 10 Mbit uplink; whether "
            "trailing parities at 10 Mbit arrive before or after the server blocks")
WORK = "/tmp/padfec_g31probe"
TAGS = ("g2", "g3b")
BINS = {"g2": G.BIN_ROOT + "/g2/qamp", "g3b": G.BIN_ROOT + "/g3b/qamp"}
PORTS = {"g2": 44433, "g3b": 44434}
INSTALL_CMD = "bash experiments/quicbed/build_g3b.sh --install-only"
STAGE2_G3B_SRCSHA = "1d331c2fb3944c2ae416ee0e6f9a0616c7b431248dd3bf9cc59d1ed70417a85f"
GEN3_QUICBED = os.path.join(os.path.dirname(ROOT), "pq_afec_gen3", "experiments", "quicbed")
QAMP_GO = os.path.join(G.QUICBED, "qamp.go")
POLICY3_GO = os.path.join(G.QUICBED, "policy3.go")
GROUP = S.GROUP
EXPECT_K = S.EXPECT_K
GAP_MS = S.GAP_MS
TIMEOUT_S = S.TIMEOUT_S
IMPUTE_MS = S.IMPUTE_MS
SERVER_FEC = S.SERVER_FEC
N_PER_ARM = 200
SEGMENT_N = 40
SMOKE_N = 5
WARMUP_N = 2
AMP_FACTOR = 3
TIMELINE_CAP = 40
FRAME_OVERHEAD_B = 42
BURST_GAP_RTT = 0.25
SEGMENT_FIXED_S = 0.35
SERVER_START_S = 2.0
CONN_OVERHEAD_MS = 25.0
PLAN_MARGIN = 1.15
HARNESS_FILES = ("experiments/g3bed.py", "experiments/padbed.py", "experiments/_journal.py",
                 "experiments/g3_stage0.py", "experiments/g3_m1confirm.py")
NEED_FLAGS = {"g2": ("fec", "ips", "gap", "timeout", "stats", "expect-k", "uplink-mbps"),
              "g3b": ("fec", "ips", "gap", "timeout", "stats", "expect-k", "uplink-mbps",
                      "layout", "lead")}

CELLS = [
    {"cell": "c6000_r80_u10_l0", "group_id": "A", "probe_cell": "c6000_r80_u10",
     "h_cell": "h_c6000_r80_u10", "cert": 6000, "rtt_ms": 80.0, "rate_mbit": 10.0,
     "loss_pct": 0.0},
    {"cell": "c6000_r80_u10_l1", "group_id": "A", "probe_cell": "c6000_r80_u10",
     "h_cell": "h_c6000_r80_u10", "cert": 6000, "rtt_ms": 80.0, "rate_mbit": 10.0,
     "loss_pct": 1.0},
    {"cell": "bigcert_r50_u2_l0", "group_id": "B", "probe_cell": "bigcert",
     "h_cell": None, "cert": 16000, "rtt_ms": 50.0, "rate_mbit": 2.0, "loss_pct": 0.0},
    {"cell": "c6000_r80_u0_l0", "group_id": "C", "probe_cell": "c6000_r80_u0",
     "h_cell": "h_c6000_r80_u0", "cert": 6000, "rtt_ms": 80.0, "rate_mbit": 0.0,
     "loss_pct": 0.0},
]


def _arm(label, action, tag, fec, ips, m, lead, layout):
    return {"label": label, "action": list(action), "bin": tag, "fec": fec, "ips": ips,
            "m": m, "lead": lead, "trail": m - lead, "layout": layout}


ARMS = {
    "none": _arm("none (no FEC)", (0, 0, 0), "g3b", "off", 1280, 0, 0, "v2"),
    "pad": _arm("pad-only (1,0,0)", (1, 0, 0), "g3b", "off", 1281, 0, 0, "v2"),
    "a104": _arm("(1,0,4)", (1, 0, 4), "g3b", "fec", 1281, 4, 0, "v3"),
    "a113": _arm("(1,1,3)", (1, 1, 3), "g3b", "fec", 1281, 4, 1, "v3"),
    "a004": _arm("(0,0,4)", (0, 0, 4), "g3b", "fec", 1280, 4, 0, "v3"),
    "a031": _arm("(0,3,1)", (0, 3, 1), "g3b", "fec", 1280, 4, 3, "v3"),
    "a013": _arm("(0,1,3)", (0, 1, 3), "g3b", "fec", 1280, 4, 1, "v3"),
    "g2pad": _arm("gen-2 pad-only (1,0,0)", (1, 0, 0), "g2", "off", 1281, 0, 0, "v2"),
}
ARM_ORDER = ("none", "pad", "a104", "a113", "a004", "a031", "a013", "g2pad")
FLAG_NOTES = (
    "-layout v3 is only accepted with -fec fec or -fec auto (qamp.go checkLayoutFlags), so "
    "none and pad-only run -fec off with the default -layout v2; with -fec off the client "
    "sends quic-go's datagrams unchanged, so the layout name has no wire effect",
    "delta is carried by -ips: InitialPacketSize = 1280 + delta, as the auto3 plan does "
    "(policy3.go auto3PlanFor, IPS = w + delta); the delta=0 arms pass -ips 1280 explicitly",
    "m = lead + trail, so every v3 arm here is -fec fec -m 4 -layout v3 -lead <lead>",
    "the gen-2 reference arm runs the frozen gen-2 binary against its own gen-2 server",
)
ONE_RTT_RULE = ("ok and hct_ms < 1.5*rtt_ms + tau(pre_bytes), tau(b) = 8*b/(1000*rate_mbit) "
                "(0 without a rate), pre_bytes = first_flight_bytes + first_flight_lead_dgrams "
                "* (first_flight_parity_bytes / first_flight_parity_dgrams) from the client row "
                "(g3_stage0.one_rtt_threshold); denominator = planned trials")
IMPUTATION = ("mean_planned_imputed_ms counts every planned trial; failed or missing trials "
              "are imputed at the client timeout %.0f ms" % IMPUTE_MS)
BURST_RULE = ("server sends of one connection (tx_ns, tx_sizes, tx_rx_timeline) are split "
              "where two consecutive sends are more than %.2f*RTT apart; burst 1 is the "
              "server first flight up to its first stall, burst 2 starts at the resume. "
              "amp_exhausted_at_b1_end = burst-1 bytes >= %d * stack bytes before the last "
              "burst-1 send (quic-go sends only while bytes_sent < %d * bytes_received before "
              "address validation); headroom = %d * that stack - burst-1 bytes"
              % (BURST_GAP_RTT, AMP_FACTOR, AMP_FACTOR, AMP_FACTOR))
ARRIVAL_MODEL = ("modeled, lossless: the client sends the first flight back to back in the "
                 "order [lead parities, originals, trailing parities]; with an uplink rate u "
                 "datagram j reaches the server sum_{i=1..j} 8*(size_i+%d)/(1000*u) ms after "
                 "datagram 0 (the server's first_rx_ns); %d B = Ethernet + IPv4 + UDP headers "
                 "that netem rate counts; trailing offsets are compared with the server's "
                 "first send and with the last burst-1 send. Measured counterparts: "
                 "beff_parity (parity bytes received before the first send) and stack growth "
                 "between sends" % (FRAME_OVERHEAD_B, FRAME_OVERHEAD_B))
JOIN_RULE = ("g3_m1confirm.join_segment, applied to every segment: client rows i = 0..n-1 "
             "complete and in order; server new connections count == rows; every connection "
             "has first_rx_ns > 0; consecutive first_rx_ns gaps >= the client gap %d ms; "
             "conn_acct_dropped and conn_acct_alias_conflicts are 0 in that segment; then the "
             "k-th connection by first_rx_ns is client row k (the client opens one connection "
             "at a time). Segments that fail a condition keep their rows and server records "
             "unpaired" % GAP_MS)
SERVER_LIFECYCLE = ("both servers (g2 :44433, g3b :44434, -fec on, the cell's cert) start fresh "
                    "at every block, then %d warm-up connections (-fec off) per server that "
                    "are not data; restarting per block keeps each process's per-connection "
                    "map at <= %d connections so its 100 ms stats dump stays small"
                    % (WARMUP_N, SEGMENT_N * (len(ARM_ORDER) - 1) + WARMUP_N))


def utc_now():
    return S.utc_now()


def mean(v):
    v = [x for x in v if x is not None]
    return (sum(v) / len(v)) if v else None


def median(v):
    v = [x for x in v if x is not None]
    return statistics.median(v) if v else None


def dist(v):
    v = [x for x in v if isinstance(x, (int, float)) and not isinstance(x, bool)]
    if not v:
        return {"n": 0, "mean": None, "median": None, "p10": None, "p90": None,
                "min": None, "max": None}
    return {"n": len(v), "mean": sum(v) / len(v), "median": statistics.median(v),
            "p10": B.pctl(v, 0.10), "p90": B.pctl(v, 0.90), "min": min(v), "max": max(v)}


def hist(v):
    c = Counter(json.dumps(x) for x in v)
    return {k: n for k, n in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))}


def share(v):
    v = [x for x in v if isinstance(x, bool)]
    return (sum(v) / len(v)) if v else None


def arm_flags(arm):
    a = ARMS[arm]
    out = ["-fec", a["fec"]]
    if a["fec"] == "fec":
        out += ["-m", str(a["m"])]
    out += ["-ips", str(a["ips"])]
    if a["layout"] == "v3":
        out += ["-layout", "v3", "-lead", str(a["lead"])]
    return out


def layout_flags_ok(arm):
    a = ARMS[arm]
    if a["layout"] == "v2":
        return True
    return (a["fec"] in ("fec", "auto") and 0 <= a["lead"] <= 15
            and a["lead"] <= max(a["m"], 1) <= 15)


def client_argv(tag, flags, n, rate_mbit, stats_path):
    rate = rate_mbit if isinstance(rate_mbit, str) else "%g" % float(rate_mbit)
    return ([BINS[tag], "-mode", "client", "-addr", "%s:%d" % (B.RX_IP, PORTS[tag]),
             "-group", GROUP, "-n", str(n)] + list(flags)
            + ["-gap", "%dms" % GAP_MS, "-timeout", "%ds" % TIMEOUT_S, "-stats", stats_path,
               "-uplink-mbps", rate, "-expect-k", str(EXPECT_K)])


def server_argv(tag, cert, stats_path):
    return (["ip", "netns", "exec", B.NS] + B.TASKSET
            + [BINS[tag], "-mode", "server", "-addr", "%s:%d" % (B.RX_IP, PORTS[tag]),
               "-certsize", str(cert), "-fec", SERVER_FEC, "-stats", stats_path])


def cond_of(cell):
    return {"rtt_ms": cell["rtt_ms"], "netem_rate_mbit": cell["rate_mbit"]}


def settle_s(cell):
    return 0.3 + 2.0 * cell["rtt_ms"] / 1000.0


def burst_gap_ms(rtt_ms):
    return BURST_GAP_RTT * rtt_ms


def paths(mode):
    tag = TAG if mode == "run" else TAG + "_smoke"
    return {"journal": os.path.join(B.STATE, tag + "_units.jsonl"),
            "meta": os.path.join(B.STATE, tag + "_meta.json"),
            "status": os.path.join(B.STATE, tag + "_status.json"),
            "incidents": os.path.join(B.STATE, tag + "_incidents.jsonl"),
            "result": os.path.join(B.RESULTS, tag + ".json")}


def unit_key(mode, cell, block):
    return "%s|%s|b%02d" % (mode, cell, block)


def build_plan(mode):
    if mode not in ("run", "smoke"):
        raise ValueError("mode must be run or smoke: %r" % (mode,))
    per_arm = SMOKE_N if mode == "smoke" else N_PER_ARM
    nblk = 1 if mode == "smoke" else N_PER_ARM // SEGMENT_N
    if mode == "run" and nblk * SEGMENT_N != N_PER_ARM:
        raise ValueError("%d per arm is not a multiple of %d" % (N_PER_ARM, SEGMENT_N))
    arms = list(ARM_ORDER)
    cells, schedule = [], []
    for c in CELLS:
        sizes = {a: S.split(per_arm, nblk) for a in arms}
        positions = {a: [0] * len(arms) for a in arms}
        for b in range(nblk):
            r = b % len(arms)
            order = arms[r:] + arms[:r]
            for pos, a in enumerate(order):
                positions[a][pos] += 1
            schedule.append({"cell": c["cell"], "block": b, "rotation": r, "order": order,
                             "sizes": {a: sizes[a][b] for a in order}})
        cells.append(dict(c, blocks=nblk, arms=[[a, per_arm] for a in arms],
                          position_counts=positions, latin_closed=nblk % len(arms) == 0,
                          netem=G.netem_specs(c["rtt_ms"] / 2.0, c["loss_pct"],
                                              c["rate_mbit"])))
    plan = {"schema": "g31_probe.plan.v1", "label": LABEL, "mode": mode,
            "question": QUESTION, "group": GROUP, "expect_k": EXPECT_K, "gap_ms": GAP_MS,
            "timeout_s": TIMEOUT_S, "impute_ms": IMPUTE_MS, "server_fec": SERVER_FEC,
            "arm_order": arms,
            "arms": {a: dict(ARMS[a], flags=arm_flags(a)) for a in arms},
            "flag_notes": list(FLAG_NOTES), "cells": cells, "schedule": schedule,
            "bins": BINS, "ports": PORTS, "work": WORK, "segment_n": SEGMENT_N,
            "warmup_n": WARMUP_N, "settle_s": {c["cell"]: settle_s(c) for c in CELLS},
            "loss_direction": "client_to_server_only",
            "netem": "padbed.set_netem(rtt/2, loss_c2s=loss, rate_up_mbit=rate), Bernoulli loss",
            "rotation": ("cyclic: block b runs arms[b mod A:] + arms[:b mod A]; with %d blocks "
                         "and A = %d arms the positions are not balanced"
                         % (nblk, len(arms))),
            "server_lifecycle": SERVER_LIFECYCLE,
            "client_failure_rule": "client crash or short output is data: the missing trials "
                                   "are imputed and the block continues; only server death, "
                                   "missing server stats, a server that does not start or a "
                                   "client that could not be executed (rc 126/127) retry the "
                                   "block",
            "one_rtt_rule": ONE_RTT_RULE, "imputation": IMPUTATION, "burst_rule": BURST_RULE,
            "arrival_model": ARRIVAL_MODEL, "join_rule": JOIN_RULE}
    return S.canon(plan)


def flight_bytes(arm):
    a = ARMS[arm]
    parity = a["ips"] + 39 + 6 * EXPECT_K if a["m"] else 0
    return EXPECT_K * a["ips"] + a["m"] * parity


def hct_est_ms(cell, arm, rtts):
    return rtts * cell["rtt_ms"] + S.tau_ms(flight_bytes(arm), cell["rate_mbit"])


def warmup_s(cell):
    return (len(TAGS) * WARMUP_N * (2 * cell["rtt_ms"] + GAP_MS + CONN_OVERHEAD_MS) / 1000.0
            + settle_s(cell))


def estimate(plan):
    cmap = {c["cell"]: c for c in plan["cells"]}
    per_block, cells = {}, {}
    for b in plan["schedule"]:
        c = cmap[b["cell"]]
        fixed = (len(b["order"]) * (SEGMENT_FIXED_S + settle_s(c)) + SERVER_START_S
                 + warmup_s(c))
        lo = fixed + sum(n * (hct_est_ms(c, a, 1) + GAP_MS + CONN_OVERHEAD_MS)
                         for a, n in b["sizes"].items()) / 1000.0
        hi = fixed + sum(n * (hct_est_ms(c, a, 2) + GAP_MS + CONN_OVERHEAD_MS)
                         for a, n in b["sizes"].items()) / 1000.0
        per_block[(b["cell"], b["block"])] = hi
        e = cells.setdefault(b["cell"], {"cell": b["cell"], "blocks": 0, "connections": 0,
                                         "low_s": 0.0, "high_s": 0.0})
        e["blocks"] += 1
        e["connections"] += sum(b["sizes"].values())
        e["low_s"] += lo
        e["high_s"] += hi
    lo_t = sum(e["low_s"] for e in cells.values())
    hi_t = sum(e["high_s"] for e in cells.values())
    return {"cells": list(cells.values()), "total_low_s": lo_t, "total_high_s": hi_t,
            "planning_s": hi_t * PLAN_MARGIN, "per_block_s": per_block,
            "assumptions": {"low": "every connection 1 RTT + tau(first flight)",
                            "high": "every connection 2 RTT + tau(first flight)",
                            "conn_overhead_ms": CONN_OVERHEAD_MS, "gap_ms": GAP_MS,
                            "segment_fixed_s": SEGMENT_FIXED_S,
                            "server_start_s_per_block": SERVER_START_S,
                            "warmup_connections_per_server_per_block": WARMUP_N,
                            "planning_margin": PLAN_MARGIN}}


def src_fingerprint(directory):
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return None
    build_like = [n for n in names
                  if n.endswith(".go") or n in ("build.sh", "go.mod", "go.sum")]
    lines = "".join("%s %s\n" % (n, G.sha256_or_none(os.path.join(directory, n)))
                    for n in sorted(build_like))
    return hashlib.sha256(lines.encode()).hexdigest()


def binary_report():
    rep, problems, warnings = {}, [], []
    for tag in TAGS:
        path = BINS[tag]
        info = {"path": path, "port": PORTS[tag], "exists": os.path.isfile(path)}
        if info["exists"]:
            info["sha256"] = G.sha256_file(path)
            info["executable"] = os.access(path, os.X_OK)
            info["srcsha"] = G._read_text(path + ".srcsha")
            info["sha256_file"] = (G._read_text(path + ".sha256") or "").split(" ")[0] or None
            if not info["executable"]:
                problems.append("%s binary is not executable: %s" % (tag, path))
            if info["sha256_file"] and info["sha256_file"] != info["sha256"]:
                problems.append("%s binary does not match its qamp.sha256" % tag)
        else:
            problems.append("%s binary missing: %s (install with %s)" % (tag, path, INSTALL_CMD))
        rep[tag] = info
    g2, g3 = rep["g2"], rep["g3b"]
    if g2["exists"] and g2["sha256"] != G.G2_FROZEN_SHA256:
        problems.append("g2 binary sha256 %s is not the frozen %s"
                        % (g2["sha256"], G.G2_FROZEN_SHA256))
    fps = {"gen31_quicbed_now": src_fingerprint(G.QUICBED),
           "gen3_quicbed_now": src_fingerprint(GEN3_QUICBED),
           "stage2_g3b_draw": STAGE2_G3B_SRCSHA}
    rep["source_fingerprints"] = fps
    if g3["exists"]:
        if g3["sha256"] == G.G2_FROZEN_SHA256:
            problems.append("g3b binary is byte-identical to the frozen gen-2 binary")
        src = g3.get("srcsha")
        g3["srcsha_matches"] = {k: bool(src) and src == v for k, v in fps.items()}
        if not src:
            warnings.append("g3b binary has no qamp.srcsha; its source tree is unknown")
        elif src != fps["gen31_quicbed_now"]:
            hit = [k for k, v in g3["srcsha_matches"].items() if v]
            warnings.append("g3b srcsha %s is not the current gen31 experiments/quicbed %s "
                            "(matches %s); the probe measures the installed binary as is"
                            % (src, fps["gen31_quicbed_now"], hit or "none of the known trees"))
    rep["frozen_g2_sha256"] = G.G2_FROZEN_SHA256
    return rep, problems, warnings


def flag_report(rep):
    out, problems = {}, []
    for tag in TAGS:
        if not rep.get(tag, {}).get("exists"):
            out[tag] = None
            continue
        flags, err = G.help_flags(rep[tag]["path"])
        out[tag] = {"flags": flags, "error": err}
        if flags is None:
            problems.append("%s -h failed: %s" % (tag, err))
            continue
        missing = sorted(set(NEED_FLAGS[tag]) - set(flags))
        if missing:
            problems.append("%s binary lacks %s (flags: %s)" % (tag, missing, ", ".join(flags)))
    return out, problems


def validate_arm(arm):
    a = ARMS[arm]
    argv = ([BINS[a["bin"]], "-mode", "client", "-addr",
             "%s:%d" % (B.RX_IP, PORTS[a["bin"]]), "-n", "0"] + arm_flags(arm))
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, argv, str(exc)
    text = ((r.stdout or "") + (r.stderr or "")).strip()
    return r.returncode == 0, argv, text[-300:]


def busy(allowed=()):
    found = list(G.busy_processes(allowed))
    table = G._proc_table() or []
    skip = G._lineage(table) | set(allowed)
    for p in table:
        if p["pid"] in skip or not p["argv"]:
            continue
        exe = os.path.basename(p["argv"][0])
        args = p["argv"][1:]
        if (exe.startswith("python") and any("g31_probe.py" in x for x in args)
                and not any(x in ("--dry-run", "--report-only") for x in args)):
            found.append("probe pid %d: %s" % (p["pid"], " ".join(p["argv"])[:200]))
    return found


def fingerprint(plan, binrep):
    h = hashlib.sha256()
    h.update(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    h.update(json.dumps(runtime_context(), sort_keys=True).encode("utf-8"))
    for tag in TAGS:
        h.update(("%s=%s;" % (tag, binrep[tag].get("sha256"))).encode())
    for rel in HARNESS_FILES:
        h.update(rel.encode())
        h.update((G.sha256_or_none(os.path.join(ROOT, rel)) or "MISSING").encode())
    return h.hexdigest()[:16]


def runner_sha256():
    return G.sha256_or_none(os.path.abspath(__file__))


def source_refs():
    pats = {
        "conns map (stats JSON)": r'json:"conns"',
        "first_rx_ns field": r'json:"first_rx_ns"',
        "first_tx_ns field": r'json:"first_tx_ns"',
        "beff_stack field": r'json:"beff_stack"',
        "beff_parity field": r'json:"beff_parity"',
        "beff_credit field": r'json:"beff_credit"',
        "tx_rx_timeline field": r'json:"tx_rx_timeline"',
        "tx_sizes field": r'json:"tx_sizes"',
        "tx_ns field": r'json:"tx_ns"',
        "timeline cap": r"const connTimelineCap",
        "first-send snapshot (WriteTo)": r"ca\.BeffStack = ca\.Stack",
        "first_rx stamp (ReadFrom)": r"ca\.FirstRxNs = time",
        "checkLayoutFlags": r"func checkLayoutFlags",
        "v3 needs fec": r"-layout v3 needs -fec fec or -fec auto",
        "-ips flag": r'flag\.Int\("ips"',
        "-layout flag": r'flag\.String\("layout"',
        "-lead flag": r'flag\.Int\("lead"',
    }
    out = {}
    try:
        with open(QAMP_GO, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    for name, pat in pats.items():
        rx = re.compile(pat)
        out[name] = next(("qamp.go:%d" % (i + 1) for i, ln in enumerate(lines) if rx.search(ln)),
                         None)
    try:
        with open(POLICY3_GO, encoding="utf-8", errors="replace") as f:
            plines = f.read().splitlines()
    except OSError:
        plines = []
    out["auto3 IPS = w + delta"] = next(("policy3.go:%d" % (i + 1) for i, ln in enumerate(plines)
                                         if "IPS: w + a.Delta" in ln), None)
    return out


def new_conn_records(before, after):
    bc = (before or {}).get("conns") or {}
    ac = (after or {}).get("conns") or {}
    out = []
    for key in sorted(set(ac) - set(bc)):
        c = ac[key]
        if isinstance(c, dict):
            rec = dict(c)
            rec["conn_key"] = key
            out.append(rec)
    return out


def _int(v):
    return v if type(v) is int else None


def conn_metrics(conn, rtt_ms, k_orig_bytes):
    sizes = conn.get("tx_sizes") or []
    tl = conn.get("tx_rx_timeline") or []
    tns = conn.get("tx_ns") or []
    n = min(len(sizes), len(tl), len(tns))
    first_rx = _int(conn.get("first_rx_ns"))
    beff_orig = _int(conn.get("beff_orig"))
    out = {"has_tx": n > 0, "timeline_n": n, "timeline_truncated": n >= TIMELINE_CAP,
           "tx_dgrams": conn.get("tx_dgrams"), "beff_stack": conn.get("beff_stack"),
           "beff_phys": conn.get("beff_phys"), "beff_orig": conn.get("beff_orig"),
           "beff_parity": conn.get("beff_parity"), "beff_credit": conn.get("beff_credit"),
           "first_send_before_all_originals": (beff_orig < k_orig_bytes
                                               if beff_orig is not None and k_orig_bytes
                                               else None)}
    if n == 0:
        return out
    t = [(x - tns[0]) / 1e6 for x in tns[:n]]
    gap = burst_gap_ms(rtt_ms)
    cuts = [j for j in range(1, n) if t[j] - t[j - 1] > gap]
    b1 = cuts[0] if cuts else n
    b2_end = cuts[1] if len(cuts) > 1 else n
    cum, amp_ok = 0, True
    for j in range(b1):
        if not cum < AMP_FACTOR * tl[j]:
            amp_ok = False
        cum += sizes[j]
    last = b1 - 1
    rel = first_rx is not None and first_rx > 0
    out.update({
        "first_tx_size": sizes[0],
        "first_send_after_rx_ms": (tns[0] - first_rx) / 1e6 if rel else None,
        "b1_n": b1, "b1_sizes": list(sizes[:b1]), "b1_bytes": cum,
        "b1_span_ms": t[last],
        "b1_end_after_rx_ms": (tns[last] - first_rx) / 1e6 if rel else None,
        "stack_at_first_send": tl[0], "stack_at_b1_last_send": tl[last],
        "stack_growth_in_b1": tl[last] - tl[0],
        "amp_limit_at_b1_end": AMP_FACTOR * tl[last],
        "headroom_at_b1_end": AMP_FACTOR * tl[last] - cum,
        "amp_exhausted_at_b1_end": cum >= AMP_FACTOR * tl[last],
        "amp_rule_held_in_b1": amp_ok,
        "bursts": len(cuts) + 1,
        "resume_after_first_tx_ms": t[b1] if cuts else None,
        "stack_at_resume": tl[b1] if cuts else None,
        "stall_stack_growth": (tl[b1] - tl[last]) if cuts else None,
        "b2_n": (b2_end - b1) if cuts else 0,
        "b2_sizes": list(sizes[b1:b2_end]) if cuts else [],
        "b2_bytes": sum(sizes[b1:b2_end]) if cuts else 0,
    })
    return out


def arrival_offsets_ms(sizes, rate_mbit):
    out, acc = [], 0.0
    for j, s in enumerate(sizes):
        if j:
            acc += S.tau_ms(s + FRAME_OVERHEAD_B, rate_mbit)
        out.append(acc)
    return out


def joined_metrics(row, conn, arm, cell):
    a = ARMS[arm]
    cond = cond_of(cell)
    k = row.get("first_flight_datagrams") or 0
    ob = row.get("first_flight_bytes") or 0
    cm = conn_metrics(conn, cell["rtt_ms"], ob or EXPECT_K * a["ips"])
    npar = row.get("first_flight_parity_dgrams") or 0
    pb = row.get("first_flight_parity_bytes") or 0
    osz = (ob / float(k)) if k else 0.0
    psz = (pb / float(npar)) if npar else 0.0
    lead = S.ff_lead(row, a["lead"])
    trail = max(0, npar - lead)
    kinds = ["L"] * lead + ["O"] * k + ["P"] * trail
    offs = arrival_offsets_ms([psz] * lead + [osz] * k + [psz] * trail, cell["rate_mbit"])
    trailing = [o for o, kind in zip(offs, kinds) if kind == "P"]
    fs = cm.get("first_send_after_rx_ms")
    be = cm.get("b1_end_after_rx_ms")
    thr = S.one_rtt_threshold(row, a["lead"], cond)
    ok = bool(row.get("ok"))
    ms = row.get("ms")
    bp = _int(conn.get("beff_parity"))
    pbefore = (int(round(bp / psz)) if psz and bp is not None
               else (0 if not npar and bp is not None else None))
    out = {"ok": ok, "ms": ms, "one_rtt": ok and isinstance(ms, (int, float)) and ms < thr,
           "one_rtt_threshold_ms": thr, "orig_dgram_bytes": osz, "parity_dgram_bytes": psz,
           "originals_sent": k, "lead_sent": lead, "trailing_sent": trail,
           "first_flight_uplink_bytes": ob + pb,
           "parities_before_first_send": pbefore,
           "trailing_before_first_send_measured": (max(0, pbefore - lead)
                                                   if pbefore is not None else None),
           "model_last_original_after_rx_ms": max((o for o, kind in zip(offs, kinds)
                                                   if kind == "O"), default=None),
           "model_trailing_after_rx_ms": trailing,
           "model_trailing_minus_first_send_ms": ([o - fs for o in trailing]
                                                  if fs is not None else None),
           "model_trailing_minus_b1_end_ms": ([o - be for o in trailing]
                                              if be is not None else None),
           "model_trailing_before_first_send": (sum(1 for o in trailing if o < fs)
                                                if fs is not None else None),
           "model_trailing_after_b1_end": (sum(1 for o in trailing if o > be)
                                           if be is not None else None)}
    out["server"] = cm
    return out


def flag_mismatches(arm, rows):
    a = ARMS[arm]
    out = {"ips_used": 0, "m_used": 0, "layout": 0, "lead": 0, "first_flight_lead": 0,
           "first_flight_parity": 0}
    for r in rows:
        if "ips_used" in r and r.get("ips_used") != a["ips"]:
            out["ips_used"] += 1
        if a["fec"] == "fec":
            if r.get("m_used") != a["m"]:
                out["m_used"] += 1
            if r.get("layout") != "v3":
                out["layout"] += 1
            if r.get("lead") != a["lead"]:
                out["lead"] += 1
            if _int(r.get("first_flight_lead_dgrams")) != a["lead"]:
                out["first_flight_lead"] += 1
            if _int(r.get("first_flight_parity_dgrams")) != a["m"]:
                out["first_flight_parity"] += 1
        else:
            if r.get("layout") not in (None, "v2"):
                out["layout"] += 1
            if r.get("first_flight_parity_dgrams") not in (None, 0):
                out["first_flight_parity"] += 1
    return out


def group_one_rtt(items, key):
    out = {}
    for it in items:
        k = key(it)
        g = out.setdefault(json.dumps(k), {"n": 0, "one_rtt": 0, "ms": []})
        g["n"] += 1
        g["one_rtt"] += int(bool(it["one_rtt"]))
        if it["ok"]:
            g["ms"].append(it["ms"])
    for g in out.values():
        g["one_rtt_rate"] = g["one_rtt"] / g["n"] if g["n"] else None
        g["mean_ok_ms"] = mean(g.pop("ms"))
    return dict(sorted(out.items()))


def elementwise_median(seqs, limit=16):
    out = []
    for j in range(limit):
        col = [s[j] for s in seqs if len(s) > j]
        if not col:
            break
        out.append({"index": j, "n": len(col), "median": statistics.median(col)})
    return out


def by_index_median(lists):
    lists = [x for x in lists if isinstance(x, list)]
    width = max((len(x) for x in lists), default=0)
    return [{"index": j, "n": sum(1 for x in lists if len(x) > j),
             "median_ms": median([x[j] for x in lists if len(x) > j])} for j in range(width)]


def server_block(cms):
    tx = [m for m in cms if m["has_tx"]]
    b1s = [tuple(m["b1_sizes"]) for m in tx]
    mode = Counter(b1s).most_common(1)
    return {
        "conns": len(cms), "conns_with_tx": len(tx),
        "timeline_truncated": sum(1 for m in tx if m["timeline_truncated"]),
        "first_send_after_rx_ms": dist([m["first_send_after_rx_ms"] for m in tx]),
        "first_tx_size_hist": hist([m["first_tx_size"] for m in tx]),
        "stack_at_first_send_hist": hist([m["stack_at_first_send"] for m in tx]),
        "beff_stack": dist([m["beff_stack"] for m in tx]),
        "beff_orig_hist": hist([m["beff_orig"] for m in tx]),
        "beff_parity": dist([m["beff_parity"] for m in tx]),
        "beff_parity_hist": hist([m["beff_parity"] for m in tx]),
        "beff_credit_hist": hist([m["beff_credit"] for m in tx]),
        "first_send_before_all_originals_share": share([m["first_send_before_all_originals"]
                                                        for m in tx]),
        "b1_n_hist": hist([m["b1_n"] for m in tx]),
        "b1_sizes_mode": ({"sizes": list(mode[0][0]), "count": mode[0][1],
                           "share": mode[0][1] / len(tx)} if mode else None),
        "b1_sizes_top": [{"sizes": list(k), "count": v}
                         for k, v in Counter(b1s).most_common(5)],
        "b1_sizes_elementwise_median": elementwise_median([list(s) for s in b1s]),
        "b1_bytes": dist([m["b1_bytes"] for m in tx]),
        "b1_bytes_hist": hist([m["b1_bytes"] for m in tx]),
        "stack_at_b1_last_send": dist([m["stack_at_b1_last_send"] for m in tx]),
        "stack_growth_in_b1": dist([m["stack_growth_in_b1"] for m in tx]),
        "headroom_at_b1_end": dist([m["headroom_at_b1_end"] for m in tx]),
        "amp_exhausted_at_b1_end_share": share([m["amp_exhausted_at_b1_end"] for m in tx]),
        "amp_rule_held_in_b1_share": share([m["amp_rule_held_in_b1"] for m in tx]),
        "b1_span_ms": dist([m["b1_span_ms"] for m in tx]),
        "bursts_hist": hist([m["bursts"] for m in tx]),
        "resume_after_first_tx_ms": dist([m["resume_after_first_tx_ms"] for m in tx]),
        "stall_stack_growth": dist([m["stall_stack_growth"] for m in tx]),
        "b2_n_hist": hist([m["b2_n"] for m in tx]),
        "b2_bytes": dist([m["b2_bytes"] for m in tx if m["b2_n"]]),
    }


def summarize_arm(arm, cell, blocks, recs):
    a = ARMS[arm]
    cond = cond_of(cell)
    segs = []
    for b in blocks:
        for s in (recs.get(b["block"]) or {}).get("segments", []):
            if s.get("arm") == arm:
                segs.append((b, s))
    rows = [r for _b, s in segs for r in s.get("rows") or []]
    n_req = sum(b["sizes"][arm] for b in blocks)
    ok_ms = [r["ms"] for r in rows if r.get("ok")]
    fails = [r for r in rows if not r.get("ok")]
    thr = [S.one_rtt_threshold(r, a["lead"], cond) for r in rows]
    one = [bool(r.get("ok")) and r["ms"] < t for r, t in zip(rows, thr)]
    conns = [c for _b, s in segs for c in s.get("server_new_conns") or []]
    k_orig = median([r.get("first_flight_bytes") for r in rows
                     if r.get("first_flight_bytes")]) or EXPECT_K * a["ips"]
    cms = [conn_metrics(c, cell["rtt_ms"], k_orig) for c in conns]
    joined, unjoined, connections, excluded = [], [], [], []
    seg_joined = 0
    for b, s in segs:
        pairs, why = M.join_segment(s)
        if pairs is None:
            excluded.append({"block": b["block"], "reason": why})
            unjoined.append({"block": b["block"], "reason": why, "rows": s.get("rows") or [],
                             "server_conns": s.get("server_new_conns") or []})
            continue
        seg_joined += 1
        for idx, (r, c) in enumerate(pairs):
            d = joined_metrics(r, c, arm, cell)
            joined.append(d)
            connections.append({"block": b["block"], "index": idx, "row": r, "server": c,
                                "derived": d})
    cli = S.sum_numeric(s.get("client_stats") for _b, s in segs)
    n_rows = len(rows)
    ffup = [(r.get("first_flight_bytes") or 0) + (r.get("first_flight_parity_bytes") or 0)
            for r in rows]
    js = [d for d in joined if d["server"]["has_tx"]]
    summary = {
        "label": a["label"], "action_delta_lead_trail": a["action"], "binary": a["bin"],
        "binary_path": BINS[a["bin"]], "port": PORTS[a["bin"]], "flags": arm_flags(arm),
        "n_requested": n_req, "n_returned": n_rows, "ok": len(ok_ms), "failed": len(fails),
        "timeouts": sum(1 for r in fails if S.is_timeout(r.get("err"))),
        "missing": n_req - n_rows,
        "fail_errors": dict(Counter((r.get("err") or "")[:80] for r in fails)),
        "mean_planned_imputed_ms": ((sum(ok_ms) + IMPUTE_MS * (n_req - len(ok_ms))) / n_req)
        if n_req else None,
        "mean_ok_ms": mean(ok_ms), "median_ok_ms": median(ok_ms),
        "p10_ok_ms": B.pctl(ok_ms, 0.10), "p90_ok_ms": B.pctl(ok_ms, 0.90),
        "one_rtt_rate": (sum(one) / n_req) if n_req else None,
        "one_rtt_rate_scope": "one_rtt trials / planned trials",
        "one_rtt_threshold_median_ms": median(thr),
        "client": {
            "first_flight_uplink_bytes": dist(ffup),
            "first_flight_orig_bytes_hist": hist([r.get("first_flight_bytes") for r in rows]),
            "first_flight_parity_bytes_hist": hist([r.get("first_flight_parity_bytes")
                                                    for r in rows]),
            "first_flight_datagrams_hist": hist(["%s+%s" % (
                r.get("first_flight_datagrams"), r.get("first_flight_parity_dgrams"))
                for r in rows]),
            "first_flight_lead_hist": hist([r.get("first_flight_lead_dgrams") for r in rows]),
            "ips_eff_hist": hist([r.get("ips_eff") for r in rows]),
            "pre_decision_bytes": dist([S.pre_decision_bytes(r, a["lead"]) for r in rows]),
            "server_bytes": dist([r.get("server_bytes") for r in rows]),
            "initial_uplink_bytes_per_conn": ((cli.get("bytes_orig", 0)
                                               + cli.get("bytes_parity", 0)) / n_rows)
            if n_rows else None,
            "parity_sent_per_conn": (cli.get("parity_sent", 0) / n_rows) if n_rows else None,
            "client_stats_sum": cli},
        "flag_mismatches": flag_mismatches(arm, rows),
        "server": server_block(cms),
        "joined": {
            "join_rule": JOIN_RULE, "segments": len(segs), "segments_joined": seg_joined,
            "segments_excluded": excluded, "connections": len(joined),
            "one_rtt_rate_joined": share([d["one_rtt"] for d in joined]),
            "one_rtt_by_amp_exhausted_at_b1_end": group_one_rtt(
                js, lambda d: d["server"]["amp_exhausted_at_b1_end"]),
            "one_rtt_by_bursts": group_one_rtt(js, lambda d: min(d["server"]["bursts"], 3)),
            "one_rtt_by_first_send_before_all_originals": group_one_rtt(
                js, lambda d: d["server"]["first_send_before_all_originals"]),
            "one_rtt_by_parities_before_first_send": group_one_rtt(
                js, lambda d: d["parities_before_first_send"]),
            "one_rtt_by_beff_credit": group_one_rtt(js, lambda d: d["server"]["beff_credit"]),
            "one_rtt_by_b1_n": group_one_rtt(js, lambda d: d["server"]["b1_n"]),
            "trailing": {
                "trailing_sent_hist": hist([d["trailing_sent"] for d in js]),
                "measured_trailing_before_first_send_hist": hist(
                    [d["trailing_before_first_send_measured"] for d in js]),
                "model_trailing_before_first_send_hist": hist(
                    [d["model_trailing_before_first_send"] for d in js]),
                "model_trailing_after_b1_end_hist": hist(
                    [d["model_trailing_after_b1_end"] for d in js]),
                "model_minus_first_send_ms_by_index": by_index_median(
                    [d["model_trailing_minus_first_send_ms"] for d in js]),
                "model_minus_b1_end_ms_by_index": by_index_median(
                    [d["model_trailing_minus_b1_end_ms"] for d in js]),
                "model_last_original_after_rx_ms": dist(
                    [d["model_last_original_after_rx_ms"] for d in js]),
                "first_send_after_rx_ms": dist(
                    [d["server"]["first_send_after_rx_ms"] for d in js]),
                "b1_end_after_rx_ms": dist([d["server"]["b1_end_after_rx_ms"] for d in js]),
                "arrival_model": ARRIVAL_MODEL}},
        "per_connection": {"joined": connections, "unjoined_segments": unjoined},
        "block_positions": {str(b["block"]): s.get("pos") for b, s in segs},
    }
    return summary


def summarize_cell(cell, plan, jr):
    blocks = [b for b in plan["schedule"] if b["cell"] == cell["cell"]]
    recs = {b["block"]: jr.get(unit_key(plan["mode"], cell["cell"], b["block"]))
            for b in blocks}
    arms = [a for a, _n in cell["arms"]]
    netem = [r.get("netem") for r in recs.values() if r]
    return {"cell": cell["cell"], "label": LABEL, "group_id": cell["group_id"],
            "probe_cell": cell["probe_cell"], "h_cell": cell["h_cell"], "cert": cell["cert"],
            "rtt_ms": cell["rtt_ms"], "rate_mbit": cell["rate_mbit"],
            "loss_pct": cell["loss_pct"], "blocks_planned": len(blocks),
            "blocks_done": sum(1 for b in blocks if S.block_complete(recs[b["block"]], b)),
            "netem_specs": netem[0] if netem else None,
            "netem_expected_tokens_all_blocks": (all((n or {}).get("expected_tokens")
                                                     and all(n["expected_tokens"].values())
                                                     for n in netem) if netem else None),
            "server_cert_der": sorted({json.dumps({t: ((r.get("servers") or {}).get(t) or {})
                                                   .get("cert_der") for t in TAGS},
                                                  sort_keys=True)
                                       for r in recs.values() if r}),
            "arms": {a: summarize_arm(a, cell, blocks, recs) for a in arms}}


def integrity(cell_list, plan, meta, jr, P):
    recs = [jr.get(unit_key(plan["mode"], b["cell"], b["block"])) for b in plan["schedule"]]
    recs = [r for r in recs if r]
    segs = [s for r in recs for s in r.get("segments", [])]
    deltas = [s.get("server_delta") or {} for s in segs]
    bins_seen = sorted({json.dumps(r.get("bins_sha256"), sort_keys=True) for r in recs})
    start_bins = {t: meta["starts"][0]["binaries"][t]["sha256"] for t in TAGS}
    finished = meta.get("finished") or {}
    src0 = meta["starts"][0].get("quicbed_sources_sha256")
    conns = [c for s in segs for c in s.get("server_new_conns") or []]

    def tot(k):
        return sum(d.get(k, 0) for d in deltas)

    return {
        "crc_fail_total": tot("recover_crc_fail"),
        "premature_recovered_total": tot("premature_recovered"),
        "conn_acct_dropped_total": tot("conn_acct_dropped"),
        "conn_acct_alias_conflicts_total": tot("conn_acct_alias_conflicts"),
        "conn_acct_unmapped_rx_total": tot("conn_acct_unmapped_rx"),
        "conn_acct_unmapped_tx_total": tot("conn_acct_unmapped_tx"),
        "global_acct_violations": sum(1 for s in segs
                                      if (s.get("server_after") or {}).get("bytes_to_stack", 0)
                                      > (s.get("server_after") or {}).get("bytes_in", 0)),
        "conn_stack_gt_rx": sum(1 for c in conns
                                if (c.get("stack_bytes") or 0) > (c.get("rx_bytes") or 0)),
        "timeline_truncated_conns": sum(1 for c in conns
                                        if len(c.get("tx_sizes") or []) >= TIMELINE_CAP),
        "cross_traffic_segments": sum(1 for s in segs
                                      if (s.get("other_server_delta") or {}).get("bytes_in")),
        "flag_mismatches": {"%s/%s" % (c["cell"], a): v["flag_mismatches"]
                            for c in cell_list for a, v in c["arms"].items()
                            if any(v["flag_mismatches"].values())},
        "netem_expected_tokens_all_cells": all(c["netem_expected_tokens_all_blocks"]
                                               for c in cell_list),
        "server_stats_present_all_segments": all(s.get("server_after") for s in segs),
        "binaries_constant": bins_seen == [json.dumps(start_bins, sort_keys=True)],
        "binaries_seen": [json.loads(x) for x in bins_seen],
        "quicbed_sources_unchanged": (finished.get("quicbed_sources_sha256") == src0
                                      if finished else None),
        "runner_sha256_seen": sorted({str(r.get("runner_sha256")) for r in recs}),
        "attempts_gt_1": sum(1 for r in recs if (r.get("attempt") or 1) > 1),
        "client_error_segments": sum(len(r.get("client_errors") or []) for r in recs),
        "missing_trials": sum(v["missing"] for c in cell_list for v in c["arms"].values()),
        "warmup_failures": sum(1 for r in recs for w in ((r.get("warmup") or {}).values())
                               if isinstance(w, dict) and (w.get("err") or w.get("ok", 0)
                                                           < w.get("n", 0))),
        "incidents": S.read_jsonl(P["incidents"]),
        "load_processes_seen": sorted({x for r in recs for x in r.get("load_processes") or []}),
        "journal_provenance": jr.provenance(),
    }


def finalize(plan, meta, jr, P):
    cell_list = [summarize_cell(c, plan, jr) for c in plan["cells"]]
    report = {"schema": "g31_probe.result.v1", "label": LABEL, "status": LABEL,
              "confirmatory": False, "mode": plan["mode"], "question": QUESTION,
              "generated_at": utc_now(),
              "journal": {"path": os.path.relpath(P["journal"], ROOT).replace("\\", "/"),
                          "fingerprint": meta["fp"]},
              "plan": plan, "env_starts": meta["starts"], "finished": meta.get("finished"),
              "one_rtt_rule": ONE_RTT_RULE, "imputation": IMPUTATION,
              "burst_rule": BURST_RULE, "arrival_model": ARRIVAL_MODEL,
              "notes": ["beff_* and tx_rx_timeline are the qamp wrapper's records at the "
                        "moment a datagram is handed to or taken from quic-go, not quic-go's "
                        "internal gate state",
                        "server records have no per-datagram receive times; trailing-parity "
                        "timing relative to the server's sends is modeled, with beff_parity "
                        "and stack growth as the measured checks",
                        "first_send_before_all_originals compares beff_orig with the client "
                        "row's first_flight_bytes (joined) or the arm's median "
                        "first_flight_bytes (server-only summaries)",
                        "fixed arms only; nothing here evaluates the v3 or v3.1 policy"],
              "cells": cell_list}
    report["integrity"] = integrity(cell_list, plan, meta, jr, P)
    save_result(P["result"], report, indent=None)
    return report


def fmt(v, spec):
    return (spec % v) if isinstance(v, (int, float)) and not isinstance(v, bool) else "-"


def print_summary(report):
    print()
    print("=" * 110)
    print("g31_probe %s, %s" % (report["mode"], LABEL))
    for c in report["cells"]:
        print("%s  cert %d  RTT %g  rate %g Mbit  loss %g%%  blocks %d/%d  (%s)" % (
            c["cell"], c["cert"], c["rtt_ms"], c["rate_mbit"], c["loss_pct"],
            c["blocks_done"], c["blocks_planned"], c["h_cell"] or "off-grid"))
        for a, v in c["arms"].items():
            sv = v["server"]
            mode = sv["b1_sizes_mode"] or {}
            print("   %-6s %-22s n %3d/%3d ok %3d mean* %7.2f 1RTT %.3f ff-up %6s B "
                  "beff_stack %6s b1 %s=%s B exh %s pre-O %s resume %s ms"
                  % (a, v["label"], v["n_returned"], v["n_requested"], v["ok"],
                     v["mean_planned_imputed_ms"] or -1, v["one_rtt_rate"] or 0.0,
                     fmt(v["client"]["first_flight_uplink_bytes"]["mean"], "%.0f"),
                     fmt(sv["beff_stack"]["median"], "%.0f"),
                     mode.get("sizes"), fmt(sv["b1_bytes"]["median"], "%.0f"),
                     fmt(sv["amp_exhausted_at_b1_end_share"], "%.2f"),
                     fmt(sv["first_send_before_all_originals_share"], "%.2f"),
                     fmt(sv["resume_after_first_tx_ms"]["median"], "%.1f")))
    keys = ("crc_fail_total", "conn_acct_dropped_total", "conn_acct_alias_conflicts_total",
            "global_acct_violations", "conn_stack_gt_rx", "timeline_truncated_conns",
            "binaries_constant", "quicbed_sources_unchanged", "attempts_gt_1",
            "client_error_segments", "missing_trials", "warmup_failures",
            "netem_expected_tokens_all_cells")
    print("integrity:", json.dumps({k: report["integrity"].get(k) for k in keys}))


def write_status(P, **kw):
    S.write_status(P, label=LABEL, **kw)


def incident(P, rec):
    S.incident(P, dict(rec, label=LABEL))


def setup():
    os.makedirs(WORK, exist_ok=True)
    saved = B.WORK
    B.WORK = WORK
    try:
        B.setup(1500)
    finally:
        B.WORK = saved


def set_netem(cell):
    one = cell["rtt_ms"] / 2.0
    out = G.set_netem(one, cell["loss_pct"], cell["rate_mbit"])
    tc, ts = out["tc_c2s"], out["tc_s2c"]
    out["expected_tokens"] = {
        "c2s_delay": ("delay %gms" % one) in tc,
        "c2s_loss": (("loss %g%%" % cell["loss_pct"]) in tc) if cell["loss_pct"] > 0
        else "loss" not in tc,
        "c2s_rate": (("rate %gMbit" % cell["rate_mbit"]) in tc) if cell["rate_mbit"] > 0
        else "rate" not in tc,
        "s2c_delay": ("delay %gms" % one) in ts,
        "s2c_no_loss": "loss" not in ts,
        "s2c_no_rate": "rate" not in ts}
    return out


def start_server(tag, cert):
    stats_path = os.path.join(WORK, "srv_%s.json" % tag)
    err_path = os.path.join(WORK, "srv_%s_stderr.txt" % tag)
    for p in (stats_path, stats_path + ".tmp"):
        try:
            os.unlink(p)
        except OSError:
            pass
    cmd = server_argv(tag, cert, stats_path)
    err_f = open(err_path, "wb")
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=err_f)
    err_f.close()
    deadline = time.monotonic() + 15
    ready = False
    while time.monotonic() < deadline:
        if b"READY" in G._read_bytes(err_path):
            ready = True
            break
        if p.poll() is not None:
            break
        time.sleep(0.05)
    text = G._read_bytes(err_path)
    if not ready or p.poll() is not None:
        B.stop_server(p)
        raise RuntimeError("server %s not ready: %s"
                           % (tag, text[-1000:].decode("utf-8", "replace")))
    der = re.search(rb"cert DER = (\d+) bytes", text)
    return {"tag": tag, "proc": p, "pid": p.pid, "stats_path": stats_path,
            "stderr_path": err_path, "argv": cmd, "certsize": cert,
            "cert_der": int(der.group(1)) if der else None}


def stop_servers(servers):
    for s in (servers or {}).values():
        if s:
            B.stop_server(s.get("proc"))


def start_servers(cert):
    servers = {}
    try:
        for tag in TAGS:
            servers[tag] = start_server(tag, cert)
    except Exception:
        stop_servers(servers)
        raise
    return servers


def run_client(tag, flags, n, rate_mbit, stats_name="cli_stats.json"):
    stats_path = os.path.join(WORK, stats_name)
    try:
        os.unlink(stats_path)
    except OSError:
        pass
    argv = client_argv(tag, flags, n, rate_mbit, stats_path)
    cmd = ["timeout", str(int(TIMEOUT_S * n + 120))] + B.TASKSET + argv
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S * n + 180)
    except subprocess.TimeoutExpired:
        return [], {}, "timeout(python)", argv, None
    rows = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    stats = S.read_json(stats_path) or {}
    err = ""
    if r.returncode != 0:
        tail = (r.stderr or "")[-300:].strip().replace("\n", " | ")
        err = "timeout(rc124)" if r.returncode == 124 else "exit %d: %s" % (r.returncode, tail)
    elif len(rows) != n:
        err = "rows %d != n %d" % (len(rows), n)
    elif not stats:
        err = "client stats missing"
    return rows, stats, err, argv, r.returncode


def warmup(cell):
    out = {}
    for tag in TAGS:
        rows, _stats, err, argv, rc = run_client(tag, ["-fec", "off"], WARMUP_N,
                                                 cell["rate_mbit"], "warmup_%s.json" % tag)
        out[tag] = {"n": WARMUP_N, "ok": sum(1 for r in rows if r.get("ok")),
                    "ms": [r.get("ms") for r in rows], "err": err, "rc": rc, "argv": argv}
    time.sleep(settle_s(cell))
    return out


def run_segment(arm, n, pos, servers, cell):
    a = ARMS[arm]
    tag = a["bin"]
    other = "g2" if tag == "g3b" else "g3b"
    before = {t: G.read_stats(servers[t]["stats_path"]) for t in TAGS}
    started = utc_now()
    t0 = time.monotonic()
    rows, cstats, client_err, argv, rc = run_client(tag, arm_flags(arm), n, cell["rate_mbit"])
    wall = time.monotonic() - t0
    time.sleep(settle_s(cell))
    after = {t: G.read_stats(servers[t]["stats_path"]) for t in TAGS}
    alive = {t: servers[t]["proc"].poll() is None for t in TAGS}
    err = ""
    if not all(alive.values()):
        err = "server died: %s" % [t for t, v in alive.items() if not v]
    elif not before[tag] or not after[tag]:
        err = "server stats missing"
    if len(rows) > n:
        err = err or "rows %d > n %d" % (len(rows), n)
    if rc in (126, 127):
        err = err or "client could not be executed (rc %d): %s" % (rc, client_err)
    return {"arm": arm, "pos": pos, "bin": tag, "port": PORTS[tag], "argv": argv, "rc": rc,
            "err": err, "client_err": client_err or "", "n_planned": n, "n_rows": len(rows),
            "rows": rows, "client_stats": cstats,
            "server_delta": G.scalar_delta(before[tag], after[tag]),
            "server_after": G.scalars(after[tag]),
            "server_new_conns": new_conn_records(before[tag], after[tag]),
            "other_server_delta": {k: v for k, v in G.scalar_delta(
                before[other], after[other]).items() if v},
            "other_server_new_conns": len(new_conn_records(before[other], after[other])),
            "started_at": started, "finished_at": utc_now(), "wall_s": wall}


def run_block(blk, cell, attempt, bins_sha):
    started = utc_now()
    netem = set_netem(cell)
    servers, segs, warm, err = {}, [], None, ""
    try:
        servers = start_servers(cell["cert"])
        warm = warmup(cell)
        for pos, arm in enumerate(blk["order"]):
            segs.append(run_segment(arm, blk["sizes"][arm], pos, servers, cell))
            if segs[-1]["err"]:
                break
        err = next((s["err"] for s in segs if s["err"]), "")
    except RuntimeError as exc:
        err = "server start failed: %s" % exc
    finally:
        stop_servers(servers)
    return {"label": LABEL, "cell": blk["cell"], "block": blk["block"],
            "rotation": blk["rotation"], "order": blk["order"], "sizes": blk["sizes"],
            "attempt": attempt, "started_at": started, "finished_at": utc_now(),
            "netem": netem, "warmup": warm,
            "servers": {t: {k: s[k] for k in ("pid", "cert_der", "certsize", "argv")}
                        for t, s in servers.items()},
            "segments": segs, "load_processes": G.load_processes(), "bins_sha256": bins_sha,
            "runner_sha256": runner_sha256(), "err": err,
            "client_errors": [{"arm": s["arm"], "rc": s["rc"], "err": s["client_err"],
                               "n_rows": s["n_rows"], "n_planned": s["n_planned"]}
                              for s in segs if s.get("client_err")]}


def live_cmd(mode):
    return ("wsl -d Ubuntu -- bash -lc 'cd /mnt/c/dev/pq_afec_gen31 && %s && unshare -Urnm "
            "python3 -u experiments/g31_probe.py --%s'" % (INSTALL_CMD, mode))


def preflight():
    problems = []
    b = busy()
    if b:
        problems += ["another measurement is running"] + b
    load = G.load_processes()
    if load:
        problems += ["build or compile processes are running"] + load
    binrep, bproblems, warnings = binary_report()
    problems += bproblems
    flags, fproblems = flag_report(binrep) if not bproblems else (None, [])
    problems += fproblems
    for arm in ARM_ORDER:
        if not layout_flags_ok(arm):
            problems.append("arm %s flags break qamp's layout rule: %s" % (arm, arm_flags(arm)))
    validation = {}
    if not problems:
        for arm in ARM_ORDER:
            ok, argv, text = validate_arm(arm)
            validation[arm] = {"ok": ok, "argv": argv, "output_tail": text}
            if not ok:
                problems.append("arm %s flags rejected by %s: %s" % (arm, ARMS[arm]["bin"], text))
    return binrep, flags, validation, warnings, problems


def live(mode):
    B.harden()
    signal.signal(signal.SIGTERM, S._sigterm)
    if not sys.platform.startswith("linux"):
        return S.refuse(["live modes run inside WSL Ubuntu: %s" % live_cmd(mode)])
    B.require_root()
    os.environ.setdefault("PADFEC_GEN", GEN_DEFAULT)
    P = paths(mode)
    plan = build_plan(mode)
    binrep, flags, validation, warnings, problems = preflight()
    if problems:
        return S.refuse(problems)
    for w in warnings:
        print("WARNING: %s" % w, file=sys.stderr, flush=True)
    fp = fingerprint(plan, binrep)
    env = G.environment()
    env.update({"label": LABEL, "work": WORK, "bins": BINS, "ports": PORTS,
                "binaries": binrep, "help_flags": flags, "arm_flag_validation": validation,
                "binary_warnings": warnings, "source_refs": source_refs(),
                "runner_sha256": runner_sha256(), "argv": sys.argv, "started_at": utc_now(),
                "pid": os.getpid(), "padfec_gen": os.environ.get("PADFEC_GEN")})
    meta = S.read_json(P["meta"])
    if not meta or meta.get("fp") != fp:
        meta = {"label": LABEL, "fp": fp, "mode": mode, "plan": plan, "starts": []}
    meta["starts"].append(env)
    meta.pop("finished", None)
    save_result(P["meta"], meta)
    jr = Journal(P["journal"], fp)
    schedule = plan["schedule"]
    cells = {c["cell"]: c for c in plan["cells"]}
    est = estimate(plan)["per_block_s"]
    pending = [b for b in schedule
               if not S.block_complete(jr.get(unit_key(mode, b["cell"], b["block"])), b)]
    print("g31_probe %s (%s): fp %s, %d/%d blocks pending, journal %s"
          % (mode, LABEL, fp, len(pending), len(schedule), P["journal"]), flush=True)
    start_bins = {t: binrep[t]["sha256"] for t in TAGS}
    if pending:
        setup()
    t0 = time.monotonic()
    est_done = 0.0
    done_n = len(schedule) - len(pending)
    try:
        for blk in pending:
            key = unit_key(mode, blk["cell"], blk["block"])
            cell = cells[blk["cell"]]
            for attempt in (1, 2):
                why = busy()
                load = G.load_processes()
                bins_now = {t: G.sha256_or_none(BINS[t]) for t in TAGS}
                if why or load or bins_now != start_bins:
                    why = why or load or ["binary changed: %s" % bins_now]
                    incident(P, {"key": key, "attempt": attempt, "abort": why, "fp": fp})
                    write_status(P, mode=mode, fp=fp, state="aborted", reason=why,
                                 blocks_done=done_n, blocks_total=len(schedule))
                    print("ABORT before %s: %s" % (key, why), file=sys.stderr)
                    return 3
                write_status(P, mode=mode, fp=fp, state="running", current=key,
                             attempt=attempt, blocks_done=done_n, blocks_total=len(schedule),
                             elapsed_s=time.monotonic() - t0)
                rec = run_block(blk, cell, attempt, bins_now)
                if S.block_complete(rec, blk):
                    jr.record(key, rec)
                    if rec["client_errors"]:
                        incident(P, {"key": key, "attempt": attempt, "fp": fp,
                                     "kept_as_data": True,
                                     "client_errors": rec["client_errors"]})
                        print("   %s client errors kept as imputed failures: %s"
                              % (key, ", ".join("%s %d/%d" % (c["arm"], c["n_rows"],
                                                              c["n_planned"])
                                                for c in rec["client_errors"])), flush=True)
                    break
                incident(P, {"key": key, "attempt": attempt, "fp": fp, "err": rec["err"],
                             "segments": [{"arm": s["arm"], "rc": s["rc"], "err": s["err"],
                                           "client_err": s.get("client_err"),
                                           "n_rows": s["n_rows"], "n_planned": s["n_planned"]}
                                          for s in rec["segments"]]})
                print("   %s attempt %d failed: %s" % (key, attempt, rec["err"]), flush=True)
            else:
                write_status(P, mode=mode, fp=fp, state="aborted",
                             reason="block failed twice: %s" % key, blocks_done=done_n,
                             blocks_total=len(schedule))
                print("ABORT: %s failed twice; rerun the same command to resume" % key,
                      file=sys.stderr)
                return 3
            done_n += 1
            est_done += est[(blk["cell"], blk["block"])]
            elapsed = time.monotonic() - t0
            remaining = sum(est[(b["cell"], b["block"])] for b in pending
                            if not jr.has(unit_key(mode, b["cell"], b["block"])))
            eta = remaining * (elapsed / est_done) if est_done else None
            write_status(P, mode=mode, fp=fp, state="running", blocks_done=done_n,
                         blocks_total=len(schedule), elapsed_s=elapsed, eta_s=eta)
            print("   [%2d/%2d] %-18s b%02d %-40s recorded, elapsed %6.0f s, eta %s s"
                  % (done_n, len(schedule), blk["cell"], blk["block"],
                     " ".join(blk["order"]), elapsed,
                     "%.0f" % eta if eta is not None else "?"), flush=True)
    except (KeyboardInterrupt, SystemExit) as exc:
        write_status(P, mode=mode, fp=fp, state="interrupted", blocks_done=done_n,
                     blocks_total=len(schedule))
        return exc.code if isinstance(exc, SystemExit) and exc.code else 130
    sources, build_fp = G.quicbed_sources()
    meta["finished"] = {"at": utc_now(), "quicbed_sources_sha256": sources,
                        "quicbed_build_style_fingerprint": build_fp,
                        "bins_sha256": {t: G.sha256_or_none(BINS[t]) for t in TAGS}}
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
    meta = S.read_json(P["meta"])
    if not meta or "fp" not in meta:
        print("no meta file: %s" % P["meta"], file=sys.stderr)
        return 2
    plan = meta["plan"]
    if S.canon(plan) != build_plan(mode):
        print("note: the recorded plan differs from the current code; analysing the recorded plan")
    jr = Journal(P["journal"], meta["fp"])
    missing = [unit_key(mode, b["cell"], b["block"]) for b in plan["schedule"]
               if not S.block_complete(jr.get(unit_key(mode, b["cell"], b["block"])), b)]
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
    plan = build_plan("run")
    smoke = build_plan("smoke")
    print("g31_probe dry run, %s: no root, no network, nothing written" % LABEL)
    print("question: %s" % QUESTION)
    print()
    print("cells (netem on v0 client->server and v1 server->client; loss client->server only):")
    for c in plan["cells"]:
        print("  %-18s %s cert %5d  RTT %3g ms  rate %4g Mbit up  loss %g%%  H grid %s"
              % (c["cell"], c["group_id"], c["cert"], c["rtt_ms"], c["rate_mbit"],
                 c["loss_pct"], c["h_cell"] or "outside the grid"))
        print("  %18s v0 '%s'  v1 '%s'  -uplink-mbps %g" % ("", c["netem"]["c2s"],
                                                           c["netem"]["s2c"], c["rate_mbit"]))
    print()
    print("servers (peer netns, restarted every block, %d warm-up connections each):" % WARMUP_N)
    for tag in TAGS:
        print("  %-4s %s" % (tag, " ".join(server_argv(tag, "<cert>",
                                                      "%s/srv_%s.json" % (WORK, tag)))))
    print()
    print("arms (client in root netns, %s):" % ("taskset %s" % " ".join(B.TASKSET[1:])
                                                if B.TASKSET else "taskset if present"))
    for arm in ARM_ORDER:
        a = ARMS[arm]
        print("  %-6s %-24s delta %d lead %d trail %d  %s  layout rule %s"
              % (arm, a["label"], a["action"][0], a["action"][1], a["action"][2],
                 " ".join(arm_flags(arm)), "ok" if layout_flags_ok(arm) else "BROKEN"))
        print("  %6s %s" % ("", " ".join(client_argv(a["bin"], arm_flags(arm), "<n>",
                                                      "<cell rate>",
                                                      "%s/cli_stats.json" % WORK))))
    for n in FLAG_NOTES:
        print("  note: %s" % n)
    print()
    for mode_plan in (plan, smoke):
        e = estimate(mode_plan)
        total = sum(n for c in mode_plan["cells"] for _a, n in c["arms"])
        print("schedule %s: %d blocks, %d connections, %d per arm per cell"
              % (mode_plan["mode"], len(mode_plan["schedule"]), total,
                 mode_plan["cells"][0]["arms"][0][1]))
        for b in mode_plan["schedule"]:
            print("  %-18s b%02d rot%d  %s" % (b["cell"], b["block"], b["rotation"], "  ".join(
                "%s:%d" % (a, b["sizes"][a]) for a in b["order"])))
        for c in e["cells"]:
            print("  estimate %-18s %4d conns  %5.0f s (all 1-RTT) .. %5.0f s (all 2-RTT)"
                  % (c["cell"], c["connections"], c["low_s"], c["high_s"]))
        print("  estimated wall clock (%s): %.1f .. %.1f min; plan for %.0f min"
              % (mode_plan["mode"], e["total_low_s"] / 60.0, e["total_high_s"] / 60.0,
                 math.ceil(e["planning_s"] / 60.0)))
    print("  estimate assumptions: %s" % json.dumps(estimate(plan)["assumptions"]))
    print()
    print("rules:")
    for name, text in (("1-RTT", ONE_RTT_RULE), ("bursts", BURST_RULE),
                       ("arrival model", ARRIVAL_MODEL), ("join", JOIN_RULE),
                       ("servers", SERVER_LIFECYCLE)):
        print("  %s: %s" % (name, text))
    print()
    print("server per-connection fields used (whole record is saved), current source lines:")
    for k, v in source_refs().items():
        print("  %-32s %s" % (k, v or "NOT FOUND"))
    print()
    for m in ("run", "smoke"):
        P = paths(m)
        print("outputs %s: %s ; %s" % (m, os.path.relpath(P["result"], ROOT).replace("\\", "/"),
                                       ", ".join(os.path.relpath(P[k], ROOT).replace("\\", "/")
                                                 for k in ("journal", "meta", "status",
                                                           "incidents"))))
    print()
    print("preflight (informational in dry run):")
    binrep, problems, warnings = binary_report()
    for tag in TAGS:
        info = binrep[tag]
        print("  %-4s binary %s: %s" % (tag, info["path"], ("sha256 %s srcsha %s" % (
            info["sha256"], info.get("srcsha"))) if info["exists"] else "missing here"))
    for k, v in binrep["source_fingerprints"].items():
        print("  source fingerprint %-18s %s" % (k, v))
    if sys.platform.startswith("linux"):
        flags, fproblems = flag_report(binrep) if not problems else (None, [])
        problems += fproblems
        print("  other measurements: %s" % (busy() or "none"))
        print("  build processes: %s" % (G.load_processes() or "none"))
    else:
        print("  process and binary checks: skipped (not Linux; /tmp/qamp_g3 lives in WSL)")
    print("  warnings: %s" % (warnings or "none"))
    print("  problems a live run would refuse on: %s" % (problems or "none"))
    print("  live runs also refuse when pgrep -x qamp, a measurement script (experiments/p*.py, "
          "g3_*, another g31_probe) or a go/compile process is visible, when a binary lacks a "
          "needed flag, or when a client rejects an arm's flags (-n 0 check); before every "
          "block the same process check and the binary hashes are repeated")
    print()
    print("live commands (one WSL invocation each; /tmp is a tmpfs, so install first):")
    print("  %s" % live_cmd("smoke"))
    print("  %s" % live_cmd("run"))
    print("  report again from the journal: python3 experiments/g31_probe.py --report-only run")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="PAD-FEC v3.1 first-flight probe, %s" % LABEL)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true",
                   help="print schedule, flags, cell mapping and estimate; nothing written")
    g.add_argument("--smoke", action="store_true",
                   help="tiny real run: %d connections per arm per cell" % SMOKE_N)
    g.add_argument("--run", action="store_true",
                   help="the probe: %d connections per arm per cell" % N_PER_ARM)
    g.add_argument("--report-only", nargs="?", const="run", choices=("run", "smoke"),
                   help="rebuild the result file from the journal")
    args = ap.parse_args(argv)
    if args.dry_run:
        return dry_run()
    if args.report_only:
        return report_only(args.report_only)
    return live("smoke" if args.smoke else "run")


if __name__ == "__main__":
    sys.exit(main())
