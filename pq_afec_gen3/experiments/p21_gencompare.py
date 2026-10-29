from __future__ import annotations

import argparse
import ast
import glob
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
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import blockstat as BST
import g3bed as G
import padbed as B
from _journal import Journal, atomic_write_json, save_result, runtime_context

GEN_DEFAULT = "g3eval_20261002"
VERDICT = "C:/dev/codex_handoff/state/evo/verdict_v3.md sections 4.1, 4.3, 4.4, 4.5"
PROTOCOL_REL = "g3/PROTOCOL_stage2.md"
WORK = "/tmp/padfec_p21"
STATE = B.STATE
RESULTS = B.RESULTS
BIN_ROOT = G.BIN_ROOT
BINS = {"g2": BIN_ROOT + "/g2/qamp", "g3b": BIN_ROOT + "/g3b/qamp"}
STAGE0_G3_BIN = BIN_ROOT + "/g3/qamp"
SLOTS = {"A": 44433, "B": 44434, "C": 44435}
PKG_ROOT = ROOT
G2_FROZEN_SHA256 = G.G2_FROZEN_SHA256
INSTALL_HINT = ("bash experiments/quicbed/build_g3b.sh "
                "(or --install-only after /tmp was cleared)")
INSTALL_CMD = "bash experiments/quicbed/build_g3b.sh --install-only"
SEAL_REL = "g3/SEAL_stage2.json"
HDRAW_REL = "g3/stage2_h_draw.json"
HPRED_REL = "g3/stage2_h_predictions.json"
TODO_MARK = "TODO(stage2-"
RUNS = ("run1", "run2", "smoke")

MLKEM = "X25519MLKEM768"
X25519 = "x25519"
TIMEOUT_S = 10
IMPUTE_MS = TIMEOUT_S * 1000.0
SERVER_FEC = "on"
ALPHA = 0.05
TOL_MS = 1.0
NONINF_MS = -1.0
H3_MIN_PRED_MS = 2.0
H3_RATIO = (0.5, 2.0)
H2_NONINF = "비열등 확인"
H2_INFERIOR = "열등 확인"
H2_UNDECIDED = "판정불능(검정력 부족)"
H2_CATEGORIES = (H2_NONINF, H2_INFERIOR, H2_UNDECIDED)
P15_RATIO = 0.7
P15_W = 1280
P15_K = 1
P15_NOMINAL_M2_ADDED = 2 * (P15_W + 39 + 6 * P15_K)

P17_LOSSES = (2.0, 15.0)
P17_SEGMENT = 450
P17_CYCLES = 5
AA_CYCLES = 3
H_LOSSES = (1.0, 8.0)
H_WEIGHTS = (0.5, 0.5)
H_K = 2
H_W = 1280
H_C_MLKEM = 2308
H_G2_M_MAX = 3
H_LATER = {"g2": "g2", "g3": "v3"}
HPRED_TOL_MS = 1e-6
HPRED_DEPS = ("padfec3/layout.py", "padfec3/decide3.py", "padfec3/learn3.py",
              "padfec/policy.py", "padfec/quantum.py", "experiments/p21_gencompare.py")
H_SEGMENT = 300
H_CYCLES = 3
H_DRAW_N = 4
H_GRID = {"cert": (6000, 8000, 10000, 12000, 14000), "rtt_ms": (20, 80, 120),
          "uplink_mbps": (0, 1, 5, 10)}
BLOCKS = 10
N_BLOCK_ARM = 1600
COLD_SEGMENT = 8
COLD_N = 800
SEQ_N = 1600

SMOKE_N = 3
SMOKE_BLOCKS = 2

P17_S_PER_CONN = {"bigcert": 0.192, "rtt200": 0.366, "mbps2": 0.156, "unlimited": 0.086}
CONN_OVERHEAD_MS = 25.0
SEGMENT_FIXED_S = 0.35
SERVER_START_S = 2.0
FF_NOMINAL_BYTES = 2 * 1280 + 2 * (1280 + 39 + 12)
VERDICT_HOURS = {"S run 1": 1.9, "D": 1.1, "H": (0.6, 0.9),
                 "cold + A/A + server equivalence": 0.5, "S run 2": 1.3}

W2 = ((0, 1), (1, 0))
W3 = ((0, 1, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0), (1, 0, 2), (0, 2, 1))

J3_KEYS = ("j3_ms", "expected_j3_ms", "exp_j3_ms", "j3_exp_ms", "ej_ms", "ej", "j3")
PMEAN_KEYS = ("post_mean_p", "posterior_mean_p", "p_post_mean", "post_p_mean", "p_mean")
DELTA_KEYS = ("a_delta", "action_delta")
LEAD_KEYS = ("a_lead", "action_lead")
T_KEYS = ("a_T", "action_T", "a_trail", "action_trail")

DEV_DATA = (
    "C:/dev/pq_afec/experiments/results/p11_adaptive.json",
    "C:/dev/pq_afec/experiments/results/p15_v2policy.json",
    "C:/dev/pq_afec/experiments/results/p17_adaptive_value.json",
    "C:/dev/pq_afec/experiments/results/p18_mmax.json",
    "C:/dev/pq_afec/experiments/results/p20_residual.json",
    "C:/dev/pq_afec/experiments/state/p11_units.jsonl",
    "C:/dev/pq_afec/experiments/state/p15_units.jsonl",
    "C:/dev/pq_afec/experiments/state/p17_units.jsonl",
    "C:/dev/pq_afec/experiments/state/p18_units.jsonl",
    "C:/dev/codex_handoff/state/evo/boot_0.json",
    "C:/dev/codex_handoff/state/evo/boot_1.json",
    "C:/dev/codex_handoff/state/evo/boot_2.json",
    "C:/dev/codex_handoff/state/evo/boot_3.json",
    "C:/dev/codex_handoff/state/evo/replay_aligned.json",
    "C:/dev/codex_handoff/state/evo/p11_replay.json",
    "C:/dev/codex_handoff/state/evo/model_tab.json",
)
DEV_GLOBS = ("experiments/results/g3_*.json", "experiments/state/g3_*_units.jsonl",
             "experiments/results/replay_g3*.json", "g3/replay_g3*.json")
SEALED_FIXED = ("g3/PROTOCOL_stage2.md", HDRAW_REL, HPRED_REL,
                "experiments/p21_gencompare.py", "experiments/g3bed.py",
                "experiments/padbed.py", "experiments/_journal.py",
                "experiments/blockstat.py", "experiments/quicbed/build_g3b.sh",
                "padfec3/__init__.py", "padfec3/layout.py", "padfec3/learn3.py",
                "padfec3/decide3.py")
SEALED_GLOBS = ("experiments/quicbed/*.go", "experiments/quicbed/go.mod",
                "experiments/quicbed/go.sum", "g3/stage2_*.py")
RECORDED = ("tests/test_p21_gencompare.py", "padfec/policy.py", "padfec/quantum.py",
            "padfec/table.py", "g3/RESULT_stage0.md", "g3/SEAL_stage0.json",
            "g3/RESULT_m1confirm.md", "g3/SEAL_m1confirm.json",
            "experiments/results/gate_v3_parity.json")
HARNESS_FILES = ("experiments/g3bed.py", "experiments/padbed.py",
                 "experiments/_journal.py", "experiments/blockstat.py")


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


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


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


def sha256_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def local_path(p):
    if sys.platform.startswith("linux") and re.match(r"^[A-Za-z]:/", p):
        return "/mnt/%s/%s" % (p[0].lower(), p[3:])
    return p


def tau_ms(nbytes, rate_mbps):
    return 8.0 * nbytes / (1000.0 * rate_mbps) if rate_mbps and rate_mbps > 0 else 0.0


def profile(name, group, k, cert, rtt, rate, burst=1.0, ref=None):
    return {"name": name, "group": group, "expect_k": k, "cert": int(cert),
            "rtt_ms": float(rtt), "netem_rate_mbit": float(rate),
            "uplink_policy_mbps": float(rate), "burst": float(burst),
            "gap_ms": 50 if rate > 0 else 8, "throughput_ref": ref}


PROFILES = {
    "bigcert": profile("bigcert", MLKEM, 2, 16000, 50, 2.0, ref="bigcert"),
    "rtt200": profile("rtt200", MLKEM, 2, 9000, 200, 2.0, ref="rtt200"),
    "mbps2": profile("mbps2", MLKEM, 2, 9000, 50, 2.0, ref="mbps2"),
    "unlimited": profile("unlimited", MLKEM, 2, 9000, 50, 0.0, ref="unlimited"),
    "p11_2955": profile("p11_2955", MLKEM, 2, 2955, 50, 0.0, ref="unlimited"),
    "p11_9000": profile("p11_9000", MLKEM, 2, 9000, 50, 0.0, ref="unlimited"),
    "p15_4032": profile("p15_4032", X25519, 1, 4032, 50, 0.0, ref="unlimited"),
    "p18_burst3": profile("p18_burst3", MLKEM, 2, 4032, 50, 0.0, burst=3.0),
}
P17_NAMES = {"bigcert": "큰cert", "rtt200": "RTT200", "mbps2": "2Mbps", "unlimited": "무제한"}

ARMS = {
    "g2auto": {"label": "g2-auto", "bin": "g2", "slot": "A", "fec": "auto", "m": 1,
               "kind": "auto2", "extra": []},
    "g3auto": {"label": "g3-auto", "bin": "g3b", "slot": "B", "fec": "auto3", "m": 1,
               "kind": "auto3", "extra": []},
    "g3fixL3": {"label": "g3-fixed m4L3", "bin": "g3b", "slot": "C", "fec": "fec", "m": 4,
                "lead": 3, "kind": "fixed", "extra": ["-layout", "v3", "-lead", "3"]},
    "g3fixL2": {"label": "g3-fixed m4L2", "bin": "g3b", "slot": "C", "fec": "fec", "m": 4,
                "lead": 2, "kind": "fixed", "extra": ["-layout", "v3", "-lead", "2"]},
    "g2m3": {"label": "g2-fixed m3", "bin": "g2", "slot": "A", "fec": "fec", "m": 3,
             "lead": 1, "kind": "fixed", "extra": []},
    "g2m3B": {"label": "g2-fixed m3 on port B", "bin": "g2", "slot": "B", "fec": "fec",
              "m": 3, "lead": 1, "kind": "fixed", "extra": []},
}
S_FIXED = {"bigcert": "g3fixL3", "rtt200": "g3fixL2"}
SERVERS_DEFAULT = {"A": "g2", "B": "g3b"}
SERVERS_S1 = {"A": "g2", "B": "g3b", "C": "g3b"}
SERVERS_AA = {"A": "g2", "B": "g2"}
HARNESS_ARMS = ("g2m3", "g2m3B")


def cache_flags(arm, path):
    kind = ARMS[arm]["kind"]
    if kind == "auto2":
        return ["-cache", path, "-probe-every", "20"]
    if kind == "auto3":
        return ["-cache3", path]
    return []


def arm_flags(arm, path="<cache>"):
    a = ARMS[arm]
    return ["-fec", a["fec"], "-m", str(a["m"])] + cache_flags(arm, path) + list(a["extra"])


def is_auto(arm):
    return ARMS[arm]["kind"] in ("auto2", "auto3")


def williams(n):
    if n == 2:
        return W2
    if n == 3:
        return W3
    raise ValueError("only 2 or 3 arms per condition: %d" % n)


def order_for(arms, idx):
    w = williams(len(arms))
    return [arms[i] for i in w[idx % len(w)]]


def split(n, blocks):
    return [n // blocks + (1 if b < n % blocks else 0) for b in range(blocks)]


def contrast(cid, x, y, use):
    return {"id": cid, "x": x, "y": y, "use": list(use)}


def c_sched(cid, batch, family, prof, arms, losses, seg_n, cycles, contrasts, mirrors,
            servers=None, extra=None):
    out = {"cond": cid, "batch": batch, "family": family, "design": "sched",
           "mirrors": mirrors, "profile": dict(prof), "arms": list(arms),
           "servers": dict(servers or SERVERS_DEFAULT), "losses": list(losses),
           "segment_n": seg_n, "cycles": cycles,
           "n_per_arm": seg_n * cycles * len(losses), "contrasts": contrasts}
    out.update(extra or {})
    return out


def c_blocks(cid, batch, family, prof, arms, loss, n_per_arm, blocks, contrasts, mirrors,
             servers=None, design="blocks", extra=None):
    out = {"cond": cid, "batch": batch, "family": family, "design": design,
           "mirrors": mirrors, "profile": dict(prof), "arms": list(arms),
           "servers": dict(servers or SERVERS_DEFAULT), "loss": float(loss),
           "blocks": blocks, "n_per_arm": n_per_arm, "contrasts": contrasts}
    out.update(extra or {})
    return out


def h_cells():
    out = []
    for cert in H_GRID["cert"]:
        for rtt in H_GRID["rtt_ms"]:
            for up in H_GRID["uplink_mbps"]:
                out.append({"cell": "h_c%d_r%d_u%d" % (cert, rtt, up), "cert": cert,
                            "rtt_ms": rtt, "uplink_mbps": up})
    return out


def h_seed(srcsha):
    return hashlib.sha256(srcsha.encode("ascii")).hexdigest()


def h_draw(srcsha, k=H_DRAW_N):
    if not isinstance(srcsha, str) or not re.fullmatch(r"[0-9a-f]{64}", srcsha):
        raise ValueError("source fingerprint must be a 64-hex sha256: %r" % (srcsha,))
    seed = h_seed(srcsha)
    ranked = sorted(h_cells(), key=lambda c: (sha256_text(seed + "|" + c["cell"]), c["cell"]))
    return {"source_fingerprint": srcsha, "seed": seed,
            "cells": [c["cell"] for c in ranked[:k]],
            "rule": ("seed = sha256(g3b qamp.srcsha as ASCII); rank every grid cell by "
                     "sha256(seed + '|' + cell id); take the %d lowest; no model "
                     "prediction is consulted" % k)}


def h_profile(cell):
    c = cell if isinstance(cell, dict) else next(x for x in h_cells() if x["cell"] == cell)
    return profile(c["cell"], MLKEM, 2, c["cert"], c["rtt_ms"], c["uplink_mbps"])


H_PLACEHOLDER = {"cell": "h_placeholder", "cert": 10000, "rtt_ms": 80, "uplink_mbps": 1}
H_SMOKE = {"cell": "h_smoke_offgrid", "cert": 7000, "rtt_ms": 50, "uplink_mbps": 3}


def main_contrast(use):
    return contrast("g2-g3", "g2auto", "g3auto", use)


def harness_contrast():
    return contrast("A-B", HARNESS_ARMS[0], HARNESS_ARMS[1], ["HARNESS"])


def conds_run1(hcells):
    out = [c_sched("AA_bigcert", "A/A", "AA", PROFILES["bigcert"], list(HARNESS_ARMS),
                   P17_LOSSES, P17_SEGMENT, AA_CYCLES, [harness_contrast()],
                   "p17 큰cert schedule, %d cycles, fixed g2 -fec fec -m 3 (stage-0 v2m3) "
                   "against g2 servers on both ports" % AA_CYCLES,
                   servers=SERVERS_AA)]
    for p in ("bigcert", "rtt200"):
        fx = S_FIXED[p]
        out.append(c_sched("S_" + p, "S run 1", "S", PROFILES[p], ["g2auto", "g3auto", fx],
                           P17_LOSSES, P17_SEGMENT, P17_CYCLES,
                           [main_contrast(["H1", "H2"]),
                            contrast("fix-g3", fx, "g3auto", ["H4"])],
                           "p17 " + P17_NAMES[p] + "; %s on its own g3b server (slot C)" % fx,
                           servers=SERVERS_S1))
    for p in ("mbps2", "unlimited"):
        out.append(c_sched("D_p17_" + p, "D", "D", PROFILES[p], ["g2auto", "g3auto"],
                           P17_LOSSES, P17_SEGMENT, P17_CYCLES, [main_contrast(["H2"])],
                           "p17 " + P17_NAMES[p]))
    for cert in (2955, 9000):
        for loss in (0, 2, 5):
            out.append(c_blocks("D_p11_%d_l%d" % (cert, loss), "D", "D",
                                PROFILES["p11_%d" % cert], ["g2auto", "g3auto"], loss,
                                N_BLOCK_ARM, BLOCKS, [main_contrast(["H2"])],
                                "p11 cert %d loss %d%%" % (cert, loss)))
    for loss in (0, 2, 5):
        out.append(c_blocks("D_p15_4032_l%d" % loss, "D", "D", PROFILES["p15_4032"],
                            ["g2auto", "g3auto"], loss, N_BLOCK_ARM, BLOCKS,
                            [main_contrast(["H2"])], "p15 x25519 cert 4032 loss %d%%" % loss))
    out.append(c_blocks("D_p18_burst3", "D", "D", PROFILES["p18_burst3"],
                        ["g2auto", "g3auto"], 15.0, N_BLOCK_ARM, BLOCKS,
                        [main_contrast(["H2"])], "p18 임계사이·버스트3 (cert 4032, burst 3, 15%)"))
    for cell in hcells:
        prof = h_profile(cell)
        out.append(c_sched("H_" + prof["name"], "H", "H", prof, ["g2auto", "g3auto"],
                           H_LOSSES, H_SEGMENT, H_CYCLES, [main_contrast(["H2", "H3"])],
                           "held-out grid cell", extra={"h_cell": prof["name"],
                                                        "placeholder": cell is H_PLACEHOLDER
                                                        or (isinstance(cell, dict) and cell.get("placeholder"))}))
    out.append(c_blocks("C_bigcert_l2", "cold", "C", PROFILES["bigcert"],
                        ["g2auto", "g3auto"], 2.0, COLD_N, COLD_N // COLD_SEGMENT,
                        [main_contrast(["H5"])], "cold, p17 큰cert at 2%", design="cold"))
    out.append(c_blocks("C_2955_l0", "cold", "C", PROFILES["p11_2955"],
                        ["g2auto", "g3auto"], 0.0, COLD_N, COLD_N // COLD_SEGMENT,
                        [main_contrast(["H5"])], "cold, p11 cert 2955 unlimited 0%",
                        design="cold"))
    out.append(c_blocks("SEQ_mbps2_l15", "server equivalence", "SEQ", PROFILES["mbps2"],
                        list(HARNESS_ARMS), 15.0, SEQ_N, BLOCKS, [harness_contrast()],
                        "fixed g2 client (-fec fec -m 3) against the g2 server (A) and the "
                        "g3b server (B)"))
    return out


def conds_run2():
    return [c_sched("S_" + p, "S run 2", "S", PROFILES[p], ["g2auto", "g3auto"],
                    P17_LOSSES, P17_SEGMENT, P17_CYCLES, [main_contrast(["H1", "H2"])],
                    "p17 " + P17_NAMES[p]) for p in ("bigcert", "rtt200")]


def conds_smoke():
    n, nb = SMOKE_N, SMOKE_BLOCKS
    hp = h_profile(H_SMOKE)
    return [
        c_sched("AA_bigcert", "smoke", "AA", PROFILES["bigcert"], list(HARNESS_ARMS),
                P17_LOSSES, n, 1, [harness_contrast()], "smoke", servers=SERVERS_AA),
        c_sched("S_bigcert", "smoke", "S", PROFILES["bigcert"],
                ["g2auto", "g3auto", "g3fixL3"], P17_LOSSES, n, 1,
                [main_contrast(["H1", "H2"]), contrast("fix-g3", "g3fixL3", "g3auto", ["H4"])],
                "smoke", servers=SERVERS_S1),
        c_sched("D_p17_mbps2", "smoke", "D", PROFILES["mbps2"], ["g2auto", "g3auto"],
                P17_LOSSES, n, 1, [main_contrast(["H2"])], "smoke"),
        c_blocks("D_p11_9000_l2", "smoke", "D", PROFILES["p11_9000"], ["g2auto", "g3auto"],
                 2.0, n * nb, nb, [main_contrast(["H2"])], "smoke"),
        c_blocks("D_p15_4032_l0", "smoke", "D", PROFILES["p15_4032"], ["g2auto", "g3auto"],
                 0.0, n * nb, nb, [main_contrast(["H2"])], "smoke"),
        c_blocks("D_p18_burst3", "smoke", "D", PROFILES["p18_burst3"], ["g2auto", "g3auto"],
                 15.0, n * nb, nb, [main_contrast(["H2"])], "smoke"),
        c_sched("H_" + hp["name"], "smoke", "H", hp, ["g2auto", "g3auto"], H_LOSSES, n, 1,
                [main_contrast(["H2", "H3"])], "smoke, off-grid cell",
                extra={"h_cell": hp["name"], "placeholder": True}),
        c_blocks("C_bigcert_l2", "smoke", "C", PROFILES["bigcert"], ["g2auto", "g3auto"],
                 2.0, COLD_SEGMENT * nb, nb, [main_contrast(["H5"])], "smoke", design="cold"),
        c_blocks("SEQ_mbps2_l15", "smoke", "SEQ", PROFILES["mbps2"], list(HARNESS_ARMS),
                 15.0, n * nb, nb, [harness_contrast()], "smoke"),
    ]


def schedule_for(cond):
    out = []
    arms = cond["arms"]
    if cond["design"] == "sched":
        nl, cyc = len(cond["losses"]), cond["cycles"]
        for c in range(cyc):
            for s, loss in enumerate(cond["losses"]):
                idx = s * cyc + c
                out.append({"cond": cond["cond"], "block": c * nl + s, "cycle": c,
                            "stratum": s, "loss": float(loss), "seq_index": idx,
                            "order": order_for(arms, idx),
                            "sizes": {a: cond["segment_n"] for a in arms},
                            "clear_cache": False})
        return out
    nb = cond["blocks"]
    if cond["design"] == "cold":
        sizes = {a: [COLD_SEGMENT] * nb for a in arms}
        if cond["n_per_arm"] != COLD_SEGMENT * nb:
            raise ValueError("%s: cold blocks must hold %d connections per arm"
                             % (cond["cond"], COLD_SEGMENT))
    else:
        sizes = {a: split(cond["n_per_arm"], nb) for a in arms}
    for b in range(nb):
        out.append({"cond": cond["cond"], "block": b, "cycle": b, "stratum": 0,
                    "loss": cond["loss"], "seq_index": b, "order": order_for(arms, b),
                    "sizes": {a: sizes[a][b] for a in arms},
                    "clear_cache": cond["design"] == "cold"})
    return out


def run_conds(run, hcells=None):
    if run == "run1":
        return conds_run1(hcells if hcells is not None else [H_PLACEHOLDER] * H_DRAW_N)
    if run == "run2":
        return conds_run2()
    if run == "smoke":
        return conds_smoke()
    raise ValueError(run)


def build_plan(run, hcells=None):
    conds = run_conds(run, hcells)
    if run == "run1" and hcells is None:
        for i, c in enumerate([c for c in conds if c["family"] == "H"]):
            c["cond"] = "H_slot%d" % (i + 1)
            c["placeholder"] = True
    ids = [c["cond"] for c in conds]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate condition ids: %s" % ids)
    for c in conds:
        slots = [ARMS[a]["slot"] for a in c["arms"]]
        if len(set(slots)) != len(slots) or not set(slots) <= set(c["servers"]):
            raise ValueError("%s: every arm needs its own server slot (arms %s, slots %s, "
                             "servers %s)" % (c["cond"], c["arms"], slots, c["servers"]))
    schedule = [b for c in conds for b in schedule_for(c)]
    used = []
    for c in conds:
        used += [a for a in c["arms"] if a not in used]
    plan = {"schema": "p21_gencompare.plan.v1", "run": run, "verdict": VERDICT,
            "protocol": PROTOCOL_REL, "conds": conds, "schedule": schedule,
            "arms": {a: dict(ARMS[a], flags=arm_flags(a)) for a in used},
            "bins": BINS, "slots": SLOTS, "work": WORK, "timeout_s": TIMEOUT_S,
            "impute_ms": IMPUTE_MS, "server_fec": SERVER_FEC, "alpha": ALPHA,
            "loss_direction": "client_to_server_only",
            "netem": "padbed.set_netem(rtt/2, loss_c2s=loss, burst_len=burst, rate_up_mbit=rate)",
            "ordering": ("Williams sets W2=(AB,BA), W3=(ABC,BCA,CAB,CBA,BAC,ACB). Schedule "
                         "conditions: block (cycle c, stratum s) uses W[(s*cycles+c) mod |W|], "
                         "run cycle-major like p17. Block and cold conditions: block b uses "
                         "W[b mod |W|] (AB/BA alternation)."),
            "cache_rule": ("each auto arm has its own cache file per run and condition, "
                           "deleted at the condition start and carried across all blocks "
                           "(p17/p11/p15 semantics); cold conditions delete both caches "
                           "before every %d-connection segment; on resume the caches are "
                           "restored from the last journaled block" % COLD_SEGMENT),
            "imputation": ("primary metric = mean over all planned trials; failed or missing "
                           "trials count as %.0f ms (client timeout)" % IMPUTE_MS)}
    return canon(plan)


def settle_s(prof):
    return 0.3 + 2.0 * prof["rtt_ms"] / 1000.0


def conn_s(prof):
    ref = prof.get("throughput_ref")
    if ref in P17_S_PER_CONN:
        return P17_S_PER_CONN[ref], "p17 measured s/conn (%s)" % ref
    s = (prof["gap_ms"] + 1.2 * prof["rtt_ms"] + tau_ms(FF_NOMINAL_BYTES,
                                                         prof["netem_rate_mbit"])
         + CONN_OVERHEAD_MS) / 1000.0
    return s, "formula (gap + 1.2 RTT + tau(%d B) + %g ms)" % (FF_NOMINAL_BYTES,
                                                               CONN_OVERHEAD_MS)


def cond_seconds(cond, blocks):
    prof = cond["profile"]
    per, src = conn_s(prof)
    conns = sum(sum(b["sizes"].values()) for b in blocks)
    segs = sum(len(b["order"]) for b in blocks)
    sec = (conns * per + segs * (SEGMENT_FIXED_S + settle_s(prof))
           + len(cond["servers"]) * SERVER_START_S)
    return {"cond": cond["cond"], "batch": cond["batch"], "connections": conns,
            "segments": segs, "s_per_conn": per, "s_per_conn_source": src, "seconds": sec}


def estimate(plan):
    rows = []
    for c in plan["conds"]:
        blocks = [b for b in plan["schedule"] if b["cond"] == c["cond"]]
        rows.append(cond_seconds(c, blocks))
    batches = {}
    for r in rows:
        batches[r["batch"]] = batches.get(r["batch"], 0.0) + r["seconds"]
    return {"conds": rows, "batches": batches, "total_s": sum(batches.values()),
            "assumptions": {"p17_s_per_conn": P17_S_PER_CONN,
                            "conn_overhead_ms": CONN_OVERHEAD_MS,
                            "segment_fixed_s": SEGMENT_FIXED_S,
                            "settle_s": "0.3 + 2*RTT per segment",
                            "server_start_s": "%g per server per condition" % SERVER_START_S}}


def h_grid_estimate():
    out = []
    for cell in h_cells():
        c = conds_run1([cell])
        hc = [x for x in c if x["family"] == "H"][0]
        out.append(cond_seconds(hc, schedule_for(hc))["seconds"])
    return {"min_s": min(out), "mean_s": sum(out) / len(out), "max_s": max(out),
            "cells": len(out)}


def t_sf(t, df):
    if df is None or not df > 0:
        raise ValueError("df must be positive")
    if t >= 0:
        return 0.5 * BST._regularized_beta(df / (df + t * t), df / 2.0, 0.5)
    return 1.0 - t_sf(-t, df)


def stratified(dx, dy, weights):
    by, terms, est = {}, [], 0.0
    for s, w in sorted(weights.items()):
        keys = sorted(k for k in dx if k[1] == s and k in dy)
        d = [dx[k] - dy[k] for k in keys]
        if len(d) < 2:
            return {"method": "stratified_welch", "est": None, "se": None, "df": None,
                    "n_units": sum(len(v["d"]) for v in by.values()) + len(d),
                    "by_stratum": by, "why": "stratum %s has %d paired units" % (s, len(d))}
        mu = sum(d) / len(d)
        var = statistics.variance(d)
        by[str(s)] = {"weight": w, "n": len(d), "mean": mu, "var": var, "d": d}
        est += w * mu
        terms.append((w * w * var / len(d), len(d)))
    se2 = sum(t for t, _n in terms)
    if se2 > 0:
        df = se2 * se2 / sum(t * t / (n - 1) for t, n in terms if t > 0)
    else:
        df = float(sum(n - 1 for _t, n in terms))
    return {"method": "stratified_welch", "est": est, "se": math.sqrt(se2), "df": df,
            "n_units": sum(n for _t, n in terms), "by_stratum": by}


def paired_blocks(bx, by):
    keys = sorted(set(bx) & set(by))
    d = [bx[k] - by[k] for k in keys]
    if len(d) < 2:
        return {"method": "paired_blocks", "est": mean(d), "se": None, "df": None,
                "n_units": len(d), "why": "fewer than 2 paired blocks"}
    sd = statistics.stdev(d)
    return {"method": "paired_blocks", "est": sum(d) / len(d), "se": sd / math.sqrt(len(d)),
            "df": float(len(d) - 1), "n_units": len(d), "sd": sd}


def interval(res, alpha=ALPHA):
    est, se, df = res.get("est"), res.get("se"), res.get("df")
    if est is None or se is None or df is None:
        return None, None
    if se == 0:
        return est, est
    h = BST.t_crit(df, alpha) * se
    return est - h, est + h


def q_value(est, se, df, c):
    if est is None or se is None or df is None:
        return 1.0
    if se == 0:
        return 0.0 if est > c else 1.0
    return min(1.0, 2.0 * t_sf((est - c) / se, df))


def holm(tests, alpha=ALPHA):
    m = len(tests)
    for t in tests:
        if "q" not in t:
            t["q"] = q_value(t.get("est"), t.get("se"), t.get("df"), t["c"])
    order = sorted(range(m), key=lambda i: (tests[i]["q"], i))
    running = 0.0
    for rank, i in enumerate(order, 1):
        t = tests[i]
        level = alpha / (m - rank + 1)
        running = max(running, min(1.0, (m - rank + 1) * t["q"]))
        t["holm_rank"] = rank
        t["holm_m"] = m
        t["holm_level"] = level
        t["p_holm"] = running
        t["reject"] = running <= alpha
        if t.get("est") is None or t.get("se") is None or t.get("df") is None:
            t["lb_holm"] = None
        elif t["se"] == 0:
            t["lb_holm"] = t["est"]
        else:
            t["lb_holm"] = t["est"] - BST.t_crit(t["df"], level) * t["se"]
    return tests


def segment_mean_imputed(seg, n_planned):
    rows = seg.get("rows") or []
    ok = [r["ms"] for r in rows if r.get("ok")]
    return (sum(ok) + IMPUTE_MS * (n_planned - len(ok))) / n_planned


def row_lead(row):
    v = row.get("first_flight_lead_dgrams")
    if type(v) is int:
        return v
    npar = row.get("first_flight_parity_dgrams")
    m = row.get("m_used")
    if type(npar) is int and type(m) is int:
        return min(1 if m >= 2 else 0, npar)
    return 0


def pre_decision_bytes(row):
    ob = row.get("first_flight_bytes") or 0
    npar = row.get("first_flight_parity_dgrams") or 0
    pb = row.get("first_flight_parity_bytes") or 0
    size = (pb / float(npar)) if npar else 0.0
    return ob + row_lead(row) * size


def one_rtt(row, prof):
    if not row.get("ok"):
        return False
    return row["ms"] < 1.5 * prof["rtt_ms"] + tau_ms(pre_decision_bytes(row),
                                                     prof["netem_rate_mbit"])


def ff_uplink(row):
    return (row.get("first_flight_bytes") or 0) + (row.get("first_flight_parity_bytes") or 0)


def added_bytes(row, k, w=P15_W):
    return max(0, ff_uplink(row) - k * w)


def first_present(row, keys):
    for k in keys:
        if k in row and row[k] is not None:
            return row[k]
    return None


def row_action(row):
    a = row.get("action")
    if isinstance(a, dict):
        vals = (a.get("delta"), a.get("lead"), a.get("T", a.get("t", a.get("trail"))))
    elif isinstance(a, (list, tuple)) and len(a) == 3:
        vals = tuple(a)
    else:
        vals = (first_present(row, DELTA_KEYS), first_present(row, LEAD_KEYS),
                first_present(row, T_KEYS))
    if all(type(v) is int for v in vals):
        return tuple(vals)
    return None


def row_j3(row):
    v = first_present(row, J3_KEYS)
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def row_pmean(row):
    v = first_present(row, PMEAN_KEYS)
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


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


def flag_mismatches(arm, rows):
    a = ARMS[arm]
    out = {"layout": 0, "m_used": 0, "lead": 0, "action_fields_missing": 0}
    for r in rows:
        if a["bin"] == "g2":
            if r.get("layout") not in (None, "v2"):
                out["layout"] += 1
            if a["kind"] == "fixed" and r.get("m_used") != a["m"]:
                out["m_used"] += 1
        elif a["kind"] == "fixed":
            if r.get("layout") != "v3":
                out["layout"] += 1
            if r.get("m_used") != a["m"]:
                out["m_used"] += 1
            if r.get("lead") != a["lead"]:
                out["lead"] += 1
        else:
            if r.get("layout") != "v3":
                out["layout"] += 1
            act = row_action(r)
            if (act is None or row_pmean(r) is None
                    or (row_j3(r) is None and act != (0, 0, 0))):
                out["action_fields_missing"] += 1
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
    caches = rec.get("cache_after")
    if not isinstance(caches, dict):
        return False
    for a in blk["order"]:
        if is_auto(a) and not isinstance(caches.get(a), dict):
            return False
    return True


def unit_key(run, cond, block):
    return "%s|%s|b%03d" % (run, cond, block)


def arm_segments(arm, blocks, recs):
    out = []
    for b in blocks:
        for s in (recs.get(b["block"]) or {}).get("segments", []):
            if s.get("arm") == arm:
                out.append((b, s))
    return out


def summarize_arm(cond, arm, blocks, recs):
    a = ARMS[arm]
    prof = cond["profile"]
    segs = arm_segments(arm, blocks, recs)
    rows = [r for _b, s in segs for r in s.get("rows") or []]
    n_req = sum(b["sizes"][arm] for b in blocks)
    ok_ms = [r["ms"] for r in rows if r.get("ok")]
    fails = [r for r in rows if not r.get("ok")]
    units = {}
    pos = {}
    for b, s in segs:
        units[(b["cycle"], b["stratum"])] = segment_mean_imputed(s, b["sizes"][arm])
        pos[(b["cycle"], b["stratum"])] = s.get("pos")
    cli = sum_numeric(s.get("client_stats") for _b, s in segs)
    srv = sum_numeric(s.get("server_delta") for _b, s in segs)
    acct = sum(1 for _b, s in segs if (s.get("server_after") or {}).get("bytes_to_stack", 0)
               > (s.get("server_after") or {}).get("bytes_in", 0))
    cross = sum(1 for _b, s in segs if (s.get("other_server_delta") or {}).get("bytes_in"))
    n_rows = len(rows)
    strata = {}
    for b, s in segs:
        st = strata.setdefault(str(b["loss"]), {"rows": [], "planned": 0})
        st["rows"] += s.get("rows") or []
        st["planned"] += b["sizes"][arm]
    by_loss = {}
    for loss, st in strata.items():
        oks = [r["ms"] for r in st["rows"] if r.get("ok")]
        acts = Counter(",".join(str(x) for x in row_action(r)) for r in st["rows"]
                       if row_action(r) is not None)
        by_loss[loss] = {
            "planned": st["planned"], "returned": len(st["rows"]),
            "mean_planned_imputed_ms": (sum(oks) + IMPUTE_MS * (st["planned"] - len(oks)))
            / st["planned"] if st["planned"] else None,
            "one_rtt_rate": (sum(1 for r in st["rows"] if one_rtt(r, prof)) / st["planned"])
            if st["planned"] else None,
            "m_ips_hist": dict(sorted(Counter("m%s/ips%s" % (r.get("m_used"), r.get("ips_used"))
                                              for r in st["rows"]).items())),
            "action_hist": dict(sorted(acts.items())),
            "post_mean_p_median": median([row_pmean(r) for r in st["rows"]]),
            "j3_mean_ms": mean([row_j3(r) for r in st["rows"]])}
    cold = None
    if cond["design"] == "cold":
        first = [(s.get("rows") or [None])[0] for _b, s in segs]
        fv = [r["ms"] if (r and r.get("ok")) else IMPUTE_MS for r in first]
        cold = {"first_visit_n": len(first),
                "first_visit_mean_imputed_ms": mean(fv),
                "first_visit_ff_uplink_bytes_mean": mean([ff_uplink(r) for r in first if r]),
                "first_visit_m_ips_hist": dict(sorted(Counter(
                    "m%s/ips%s" % ((r or {}).get("m_used"), (r or {}).get("ips_used"))
                    for r in first).items())),
                "visits_per_cache": COLD_SEGMENT}
    return {
        "label": a["label"], "binary": a["bin"], "binary_path": BINS[a["bin"]],
        "slot": a["slot"], "port": SLOTS[a["slot"]],
        "server_binary": cond["servers"][a["slot"]], "flags": arm_flags(arm),
        "n_requested": n_req, "n_returned": n_rows, "ok": len(ok_ms), "failed": len(fails),
        "timeouts": sum(1 for r in fails if is_timeout(r.get("err"))),
        "missing": n_req - n_rows,
        "fail_errors": dict(Counter((r.get("err") or "")[:80] for r in fails)),
        "mean_planned_imputed_ms": ((sum(ok_ms) + IMPUTE_MS * (n_req - len(ok_ms))) / n_req)
        if n_req else None,
        "mean_ok_ms": mean(ok_ms), "median_ok_ms": median(ok_ms),
        "p90_ok_ms": B.pctl(ok_ms, 0.90), "p99_ok_ms": B.pctl(ok_ms, 0.99),
        "one_rtt_rate": (sum(1 for r in rows if one_rtt(r, prof)) / n_req) if n_req else None,
        "one_rtt_rule": "ok and ms < 1.5*RTT + tau(first_flight_bytes + lead*parity size)",
        "ff_uplink_bytes_mean": mean([ff_uplink(r) for r in rows]),
        "uplink_bytes_per_conn": ((cli.get("bytes_orig", 0) + cli.get("bytes_parity", 0))
                                  / n_rows) if n_rows else None,
        "uplink_bytes_note": ("client counters; bytes_parity is counted where parity_sent is, "
                              "which stage 0 found undercounts later-flight parity after "
                              "1-RTT handshakes; server_bytes_in_per_conn is the server-side "
                              "cross-check (after loss)"),
        "server_bytes_in_per_conn": (srv.get("bytes_in", 0) / n_rows) if n_rows else None,
        "parity_sent_per_conn": (cli.get("parity_sent", 0) / n_rows) if n_rows else None,
        "m_ips_hist": dict(sorted(Counter("m%s/ips%s" % (r.get("m_used"), r.get("ips_used"))
                                          for r in rows).items())),
        "lead_hist": dict(sorted(Counter(str(r.get("lead")) for r in rows).items())),
        "action_rows": sum(1 for r in rows if row_action(r) is not None),
        "j3_rows": sum(1 for r in rows if row_j3(r) is not None),
        "pmean_rows": sum(1 for r in rows if row_pmean(r) is not None),
        "by_loss": by_loss, "cold": cold,
        "server_counters": srv, "crc_fail": srv.get("recover_crc_fail", 0),
        "acct_violation_segments": acct, "cross_traffic_segments": cross,
        "client_stats_sum": cli, "flag_mismatches": flag_mismatches(arm, rows),
        "client_error_segments": [{"block": b["block"], "err": s.get("client_err")}
                                  for b, s in segs if s.get("client_err")],
        "_units": units, "_pos": pos}


def contrast_estimate(cond, arms_out, con, blocks):
    ux, uy = arms_out[con["x"]]["_units"], arms_out[con["y"]]["_units"]
    if cond["design"] == "sched":
        totals = {}
        for b in blocks:
            totals[b["stratum"]] = totals.get(b["stratum"], 0) + b["sizes"][con["x"]]
        tot = float(sum(totals.values()))
        res = stratified(ux, uy, {s: n / tot for s, n in totals.items()})
    else:
        res = paired_blocks({k[0]: v for k, v in ux.items()}, {k[0]: v for k, v in uy.items()})
    lo, hi = interval(res)
    res.update({"id": con["id"], "x": con["x"], "y": con["y"], "use": con["use"],
                "lo95": lo, "hi95": hi, "sign": "positive = %s slower than %s"
                % (con["x"], con["y"])})
    mx, my = (arms_out[con["x"]]["mean_planned_imputed_ms"],
              arms_out[con["y"]]["mean_planned_imputed_ms"])
    res["overall_diff_ms"] = (mx - my) if mx is not None and my is not None else None
    return res


def position_effect(arms_out):
    resid = {}
    for v in arms_out.values():
        base = v["mean_planned_imputed_ms"]
        for key, x in v["_units"].items():
            p = v["_pos"].get(key)
            if base is not None and p is not None:
                resid.setdefault(p, []).append(x - base)
    return {str(k): mean(v) for k, v in sorted(resid.items())}


def order_balance(cond, blocks):
    pos = {a: Counter() for a in cond["arms"]}
    prec = Counter()
    for b in blocks:
        for i, a in enumerate(b["order"]):
            pos[a][i] += 1
        for con in cond["contrasts"]:
            o = b["order"]
            if con["x"] in o and con["y"] in o:
                key = "%s before %s" % ((con["x"], con["y"]) if o.index(con["x"])
                                        < o.index(con["y"]) else (con["y"], con["x"]))
                prec["%s|%s" % (con["id"], key)] += 1
    return {"positions": {a: dict(sorted(c.items())) for a, c in pos.items()},
            "precedence": dict(sorted(prec.items()))}


def summarize_cond(cond, blocks, recs):
    arms_out = {a: summarize_arm(cond, a, blocks, recs) for a in cond["arms"]}
    cons = [contrast_estimate(cond, arms_out, con, blocks) for con in cond["contrasts"]]
    pos = position_effect(arms_out)
    for v in arms_out.values():
        v.pop("_units")
        v.pop("_pos")
    done = sum(1 for b in blocks if block_complete(recs.get(b["block"]), b))
    netem = [(recs.get(b["block"]) or {}).get("netem") for b in blocks]
    return {"cond": cond["cond"], "batch": cond["batch"], "family": cond["family"],
            "design": cond["design"], "mirrors": cond["mirrors"],
            "profile": cond["profile"], "servers": cond["servers"],
            "losses": cond.get("losses") or [cond.get("loss")],
            "h_cell": cond.get("h_cell"), "placeholder": cond.get("placeholder", False),
            "blocks_planned": len(blocks), "blocks_done": done,
            "complete": done == len(blocks),
            "netem_first_block": next((n for n in netem if n), None),
            "arms": arms_out, "contrasts": cons, "position_effect_ms": pos,
            "order_balance": order_balance(cond, blocks)}


def get_contrast(cond_sum, cid):
    return next((c for c in cond_sum["contrasts"] if c["id"] == cid), None)


def test_of(cond_sum, cid, c):
    con = get_contrast(cond_sum, cid) or {}
    return {"cond": cond_sum["cond"], "contrast": cid, "c": c, "est": con.get("est"),
            "se": con.get("se"), "df": con.get("df"), "lo95": con.get("lo95"),
            "hi95": con.get("hi95")}


def h1_eval(conds, bound_ms):
    thr = 0.0 if bound_ms is None else max(0.0, float(bound_ms))
    tests = holm([test_of(c, "g2-g3", thr) for c in conds if c["family"] == "S"])
    lbs = [t["lb_holm"] for t in tests]
    ok = (bound_ms is not None and len(tests) == 2 and all(t["reject"] for t in tests)
          and all(x is not None for x in lbs) and sum(lbs) / 2.0 >= TOL_MS)
    return {"rule": "both S conditions: Holm (m=2) 95%% lower bound of g2-g3 > max(0, B) "
                    "with B the harness bias bound, and the mean of the two Holm lower "
                    "bounds >= %.1f ms" % TOL_MS,
            "harness_bound_ms": bound_ms, "threshold_ms": thr,
            "evaluable": bound_ms is not None,
            "tests": tests, "mean_lb_holm": (sum(lbs) / 2.0) if len(lbs) == 2
            and all(x is not None for x in lbs) else None, "pass": bool(ok)}


def h2_category(t):
    if t["reject"]:
        return H2_NONINF
    if t["inferior_reject"]:
        return H2_INFERIOR
    return H2_UNDECIDED


def h2_upper_bounds(tests):
    neg = holm([{"c": 0.0, "est": -t["est"] if t.get("est") is not None else None,
                 "se": t.get("se"), "df": t.get("df")} for t in tests])
    for t, u in zip(tests, neg):
        t["ub_holm"] = -u["lb_holm"] if u["lb_holm"] is not None else None
        t["inferior_holm_rank"] = u["holm_rank"]
        t["inferior_holm_level"] = u["holm_level"]
        t["inferior_reject"] = u["reject"]
        t["holm_ub_below_0"] = t["ub_holm"] is not None and t["ub_holm"] < 0.0
    return tests


def h2_eval(conds):
    tests = holm([test_of(c, "g2-g3", NONINF_MS) for c in conds
                  if c["family"] in ("S", "D", "H")])
    h2_upper_bounds(tests)
    for t in tests:
        t["category"] = h2_category(t)
        if t.get("est") is None or t.get("se") is None or t.get("df") is None:
            t["why"] = "no estimate (a stratum or a block pair is missing)"
    counts ={k: sum(1 for t in tests if t["category"] == k) for k in H2_CATEGORIES}
    return {"rule": "every S, D and H condition: Holm 95%% lower bound of g2-g3 > %.1f ms "
                    "(Holm step-down rejection); categories per condition: '%s' if that "
                    "holds, otherwise '%s' if a separate Holm step-down over the same family "
                    "for H0: g2-g3 >= 0 rejects (its Holm upper bound < 0), else '%s'"
                    % (NONINF_MS, H2_NONINF, H2_INFERIOR, H2_UNDECIDED),
            "family_size": len(tests), "tests": tests, "category_counts": counts,
            "by_category": {k: [t["cond"] for t in tests if t["category"] == k]
                            for k in H2_CATEGORIES},
            "failed": [t["cond"] for t in tests if not t["reject"]],
            "reading": "'%s' means the interval was too wide to decide; it is not evidence "
                       "that g3 is slower" % H2_UNDECIDED,
            "pass": bool(tests) and all(t["category"] == H2_NONINF for t in tests)}


def h3_eval(conds, hpred):
    hconds = [c for c in conds if c["family"] == "H"]
    cells = (hpred or {}).get("cells") if isinstance(hpred, dict) else None
    if not isinstance(cells, dict):
        return {"rule": "H cells with sealed delta_hat >= 2 ms: Holm lower bound > 0 and "
                        "observed/predicted in [0.5, 2]; other H cells: H2 only",
                "evaluable": False, "why": "sealed H prediction table missing (%s)" % HPRED_REL,
                "pass": False}
    strong, weak, missing = [], [], []
    for c in hconds:
        p = cells.get(c.get("h_cell"))
        dh = p.get("delta_hat_ms") if isinstance(p, dict) else None
        if not isinstance(dh, (int, float)):
            missing.append(c["cond"])
        elif dh >= H3_MIN_PRED_MS:
            t = test_of(c, "g2-g3", 0.0)
            t["delta_hat_ms"] = dh
            strong.append(t)
        else:
            weak.append({"cond": c["cond"], "delta_hat_ms": dh, "rule": "H2 only"})
    holm(strong)
    for t in strong:
        t["ratio"] = (t["est"] / t["delta_hat_ms"]) if t["est"] is not None else None
        t["ratio_ok"] = t["ratio"] is not None and H3_RATIO[0] <= t["ratio"] <= H3_RATIO[1]
        t["pass"] = bool(t["reject"] and t["ratio_ok"])
    return {"rule": "H cells with sealed delta_hat >= %.0f ms: Holm (within those cells) 95%% "
                    "lower bound of g2-g3 > 0 and observed/predicted in [%.1f, %.1f]; other H "
                    "cells: H2 only" % (H3_MIN_PRED_MS, H3_RATIO[0], H3_RATIO[1]),
            "evaluable": not missing, "missing_predictions": missing,
            "strong": strong, "weak": weak,
            "pass": not missing and all(t["pass"] for t in strong)}


def h4_eval(conds):
    tests = holm([test_of(c, "fix-g3", 0.0) for c in conds
                  if c["family"] == "S" and get_contrast(c, "fix-g3")])
    for t in tests:
        t["adaptation_contributed"] = bool(t["reject"])
    return {"rule": "exploratory: write 'adaptation contributed' for an S condition only if "
                    "the Holm (m=2) 95% lower bound of (g3-fixed minimax) - g3 > 0",
            "tests": tests}


def h5_eval(conds):
    out = []
    for c in conds:
        if c["family"] != "C":
            continue
        con = get_contrast(c, "g2-g3") or {}
        out.append({"cond": c["cond"],
                    "arms": {a: {"first_visit_mean_imputed_ms": (v.get("cold") or {}).get(
                        "first_visit_mean_imputed_ms"),
                        "first_visit_ff_uplink_bytes_mean": (v.get("cold") or {}).get(
                            "first_visit_ff_uplink_bytes_mean"),
                        "mean_planned_imputed_ms": v["mean_planned_imputed_ms"],
                        "ff_uplink_bytes_mean": v["ff_uplink_bytes_mean"]}
                        for a, v in c["arms"].items()},
                    "g2_minus_g3_all_visits": {k: con.get(k) for k in ("est", "lo95", "hi95")}})
    return {"rule": "report only: cold first-visit mean HCT and bytes (cache cleared every "
                    "%d connections)" % COLD_SEGMENT, "conds": out}


def harness_eval(conds):
    out = {}
    for c in conds:
        if c["family"] not in ("AA", "SEQ"):
            continue
        con = get_contrast(c, "A-B") or {}
        lo, hi, est = con.get("lo95"), con.get("hi95"), con.get("est")
        evaluable = lo is not None and hi is not None and est is not None
        out[c["family"]] = {"cond": c["cond"], "est": est, "se": con.get("se"),
                            "df": con.get("df"), "lo95": lo, "hi95": hi,
                            "evaluable": evaluable,
                            "ci_excludes_0": bool(evaluable and (lo > 0.0 or hi < 0.0)),
                            "bound_ms": max(abs(lo), abs(hi)) if evaluable else None}
    evaluable = set(out) == {"AA", "SEQ"} and all(v["evaluable"] for v in out.values())
    detected = any(v["ci_excludes_0"] for v in out.values())
    bound = max(v["bound_ms"] for v in out.values()) if evaluable else None
    ok = evaluable and not detected
    return {"rule": "harness_bias_detected = (A/A unadjusted 95% interval excludes 0) or "
                    "(server-equivalence unadjusted 95% interval excludes 0); if detected, or "
                    "if a control is missing, every stage-2 verdict is suspended; otherwise "
                    "B = max over the two controls of max(|lo95|, |hi95|) and H1 uses "
                    "max(0, B)",
            "controls": out, "evaluable": evaluable, "harness_bias_detected": detected,
            "B_ms": bound, "h1_threshold_ms": max(0.0, bound) if ok else None, "ok": ok}


def p15_bytes_eval(conds):
    c = next((x for x in conds if x["cond"] == "D_p15_4032_l0"), None)
    if not c:
        return {"evaluable": False}
    out = {"rule": ("p15 L540 analogue at cert 4032 0%%: mean added first-flight bytes of the "
                    "arm's final block < %.1f x nominal m2 added bytes %d = %.1f B"
                    % (P15_RATIO, P15_NOMINAL_M2_ADDED, P15_RATIO * P15_NOMINAL_M2_ADDED)),
           "expected": "g3-auto fails (verdict 4.4); g2-auto reported for reference",
           "arms": {}}
    for a, v in c["arms"].items():
        fb = v.get("final_block_added_bytes_mean")
        out["arms"][a] = {"final_block_added_bytes_mean": fb,
                          "pass": fb is not None and fb < P15_RATIO * P15_NOMINAL_M2_ADDED}
    g3 = out["arms"].get("g3auto", {})
    out["g3_failed_as_expected"] = g3.get("pass") is False
    out["evaluable"] = all(v["final_block_added_bytes_mean"] is not None
                           for v in out["arms"].values())
    return out


def decide(res1, res2=None, hpred=None, label="confirmatory"):
    c1 = (res1 or {}).get("conds") or []
    c2 = (res2 or {}).get("conds") or []
    harness = harness_eval(c1)
    bound = harness["h1_threshold_ms"]
    h1r1 = h1_eval(c1, bound) if c1 else None
    h1r2 = h1_eval(c2, bound) if c2 else None
    suspended = not harness["ok"]
    if suspended:
        claim = ("suspended (harness bias detected)" if harness["harness_bias_detected"]
                 else "suspended (harness control missing or not evaluable)")
    elif not h1r1 or not h1r1["pass"]:
        claim = "no improvement claim (H1 failed in run 1)"
    elif not h1r2:
        claim = "pending run 2"
    elif all((t.get("est") or 0.0) > 0 for t in h1r2["tests"]) and len(h1r2["tests"]) == 2:
        claim = "improvement claimed (run 1 H1 passed, run 2 same direction in both S conditions)"
    else:
        claim = "no improvement claim (run 2 not in the same direction)"
    return {"schema": "p21_gencompare.decisions.v1", "label": label,
            "generated_at": utc_now(), "harness": harness,
            "verdicts_suspended": suspended,
            "H1": {"run1": h1r1, "run2": h1r2, "claim": claim,
                   "same_direction_rule": "run 2 point estimates of g2-g3 > 0 in both S "
                                          "conditions"},
            "H2": {"run1": h2_eval(c1) if c1 else None, "run2": h2_eval(c2) if c2 else None},
            "H3": h3_eval(c1, hpred) if c1 else None,
            "H4": h4_eval(c1) if c1 else None,
            "H5": h5_eval(c1) if c1 else None,
            "expected_failure_p15_bytes": p15_bytes_eval(c1) if c1 else None}


def add_final_block_bytes(cond_sum, cond, blocks, recs):
    if cond["cond"] != "D_p15_4032_l0":
        return
    last = blocks[-1]
    for a in cond["arms"]:
        segs = [s for _b, s in arm_segments(a, [last], recs)]
        rows = [r for s in segs for r in s.get("rows") or []]
        cond_sum["arms"][a]["final_block_added_bytes_mean"] = (
            mean([added_bytes(r, cond["profile"]["expect_k"]) for r in rows]))


def paths(run):
    return {"meta": os.path.join(STATE, "p21_%s_meta.json" % run),
            "status": os.path.join(STATE, "p21_%s_status.json" % run),
            "incidents": os.path.join(STATE, "p21_%s_incidents.jsonl" % run),
            "result": os.path.join(RESULTS, "p21_gencompare_%s.json" % run),
            "decisions": os.path.join(RESULTS, "p21_gencompare_decisions.json")}


def journal_path(run, cond):
    return os.path.join(STATE, "p21_%s_%s_units.jsonl" % (run, cond))


def write_status(P, **kw):
    kw["updated_at"] = utc_now()
    kw["pid"] = os.getpid()
    try:
        atomic_write_json(P["status"], kw)
    except OSError:
        pass


def incident(P, rec):
    rec = dict(rec, at=utc_now())
    os.makedirs(os.path.dirname(P["incidents"]), exist_ok=True)
    with open(P["incidents"], "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def source_hashes():
    out = {}
    for pattern in ("padfec3/*.py", "experiments/quicbed/*.go", "experiments/quicbed/*.sh",
                    "experiments/quicbed/go.mod", "experiments/quicbed/go.sum",
                    "experiments/p21_gencompare.py") + HARNESS_FILES:
        for p in sorted(glob.glob(os.path.join(ROOT, pattern))):
            r = os.path.relpath(p, ROOT).replace("\\", "/")
            out[r] = G.sha256_or_none(p)
    return out


def cond_fingerprint(run, cond, bins_sha, seal_sha):
    h = hashlib.sha256()
    h.update(json.dumps(canon(cond), sort_keys=True, ensure_ascii=False).encode("utf-8"))
    h.update(run.encode())
    h.update(json.dumps(runtime_context(), sort_keys=True).encode("utf-8"))
    for tag in sorted(bins_sha):
        h.update(("%s=%s;" % (tag, bins_sha[tag])).encode())
    for rel in HARNESS_FILES:
        h.update(rel.encode())
        h.update((G.sha256_or_none(os.path.join(ROOT, rel)) or "MISSING").encode())
    h.update(("runner=%s" % G.sha256_or_none(os.path.abspath(__file__))).encode())
    h.update(("seal=%s" % seal_sha).encode())
    return h.hexdigest()[:16]


def journal_provenance(run, plan, meta):
    run_ids = set()
    for s in meta.get("starts") or []:
        run_ids.update((s.get("journal_run_ids") or {}).values())
    units, reused, used = [], 0, 0
    for c in plan["conds"]:
        jr = Journal(journal_path(run, c["cond"]), meta["fps"][c["cond"]])
        keys = [unit_key(run, c["cond"], b["block"]) for b in plan["schedule"]
                if b["cond"] == c["cond"] and jr.has(unit_key(run, c["cond"], b["block"]))]
        if not keys:
            continue
        prov = jr.provenance(keys)
        for u in prov["units"]:
            used += 1
            if u.get("run_id") not in run_ids:
                reused += 1
                units.append(u["key"])
    return {"used_units": used, "reused_units": reused, "reused_keys": units[:20],
            "invocations": len(meta.get("starts") or []),
            "rule": "reused = journaled by an invocation that this run's meta does not list"}


def integrity(run, plan, meta, conds_out):
    arms = [(c["cond"], a, v) for c in conds_out for a, v in c["arms"].items()]
    starts = meta.get("starts") or []
    finished = meta.get("finished") or {}
    bins0 = starts[0].get("bins_sha256") if starts else None
    src0 = starts[0].get("source_hashes") if starts else None
    recs_bins = set()
    attempts, cerrs, loads = 0, 0, set()
    for c in plan["conds"]:
        jr = Journal(journal_path(run, c["cond"]), meta["fps"][c["cond"]])
        for b in plan["schedule"]:
            if b["cond"] != c["cond"]:
                continue
            r = jr.get(unit_key(run, c["cond"], b["block"]))
            if not r:
                continue
            recs_bins.add(json.dumps(r.get("bins_sha256"), sort_keys=True))
            attempts += 1 if (r.get("attempt") or 1) > 1 else 0
            cerrs += len(r.get("client_errors") or [])
            loads.update(r.get("load_processes") or [])
    g3rows = [(v["n_returned"], v["action_rows"], v["j3_rows"], v["pmean_rows"])
              for _c, a, v in arms if ARMS[a]["kind"] == "auto3"]
    tot = sum(x[0] for x in g3rows)
    return {
        "crc_fail_total": sum(v["crc_fail"] for _c, _a, v in arms),
        "acct_violation_segments": sum(v["acct_violation_segments"] for _c, _a, v in arms),
        "cross_traffic_segments": sum(v["cross_traffic_segments"] for _c, _a, v in arms),
        "timeouts_total": sum(v["timeouts"] for _c, _a, v in arms),
        "missing_trials": sum(v["missing"] for _c, _a, v in arms),
        "client_error_segments": cerrs, "attempts_gt_1": attempts,
        "flag_mismatches": {"%s/%s" % (c, a): v["flag_mismatches"] for c, a, v in arms
                            if any(v["flag_mismatches"].values())},
        "g3_rows_with_action_j3_pmean": {"rows": tot,
                                         "action": sum(x[1] for x in g3rows),
                                         "j3": sum(x[2] for x in g3rows),
                                         "post_mean_p": sum(x[3] for x in g3rows)},
        "binaries_constant": recs_bins <= {json.dumps(bins0, sort_keys=True)}
        if bins0 else None,
        "binaries_seen": [json.loads(x) for x in sorted(recs_bins)],
        "sources_unchanged": (finished.get("source_hashes") == src0) if finished and src0
        else None,
        "seal_ok_at_every_start": [s.get("seal_check", {}).get("ok") for s in starts],
        "journal": journal_provenance(run, plan, meta),
        "load_processes_seen": sorted(loads),
        "incidents": read_jsonl(paths(run)["incidents"])}


def finalize(run, plan, meta):
    conds_out = []
    for c in plan["conds"]:
        jr = Journal(journal_path(run, c["cond"]), meta["fps"][c["cond"]])
        blocks = [b for b in plan["schedule"] if b["cond"] == c["cond"]]
        recs = {b["block"]: jr.get(unit_key(run, c["cond"], b["block"])) for b in blocks}
        s = summarize_cond(c, blocks, recs)
        add_final_block_bytes(s, c, blocks, recs)
        conds_out.append(s)
    starts = meta.get("starts") or []
    confirmatory = (run in ("run1", "run2") and bool(starts)
                    and all(s.get("seal_check", {}).get("ok") for s in starts)
                    and len({s.get("seal_check", {}).get("sha256") for s in starts}) == 1)
    integ = integrity(run, plan, meta, conds_out)
    drift = [k for k in ("sources_unchanged", "binaries_constant") if integ.get(k) is False]
    confirmatory = confirmatory and not drift
    report = {"schema": "p21_gencompare.result.v1", "run": run, "verdict": VERDICT,
              "protocol": PROTOCOL_REL, "generated_at": utc_now(),
              "label": ("smoke (code path check, not data for any verdict)" if run == "smoke"
                        else "confirmatory" if confirmatory else
                        "development (%s)" % ("changed during the run: " + ", ".join(drift)
                                              if drift else "seal missing, failed or changed "
                                              "between invocations")),
              "confirmatory": confirmatory,
              "seal_sha256": starts[0].get("seal_check", {}).get("sha256") if starts else None,
              "plan": plan, "env_starts": starts, "finished": meta.get("finished"),
              "estimate": estimate(plan), "conds": conds_out}
    report["integrity"] = integ
    if run == "smoke":
        report["decisions_smoke"] = decide(report, None, None, label="smoke")
    save_result(paths(run)["result"], report)
    if run in ("run1", "run2"):
        write_decisions()
    return report


def write_decisions():
    r1 = read_json(paths("run1")["result"])
    r2 = read_json(paths("run2")["result"])
    if not r1:
        return None
    ok1 = bool(r1.get("confirmatory")) and all(c.get("complete") for c in r1.get("conds", []))
    use2 = (r2 if r2 and r2.get("confirmatory") and r2.get("seal_sha256") == r1.get("seal_sha256")
            and all(c.get("complete") for c in r2.get("conds", [])) else None)
    hpred = read_json(os.path.join(ROOT, HPRED_REL))
    d = decide(r1, use2, hpred, label="confirmatory" if ok1 else "development")
    d["runs_used"] = {"run1": paths("run1")["result"], "run2": paths("run2")["result"]
                      if use2 else None}
    d["run2_excluded_reason"] = (None if use2 or not r2 else
                                 "run 2 is not confirmatory, incomplete, or sealed differently "
                                 "from run 1")
    save_result(paths("run1")["decisions"], d)
    return d


def binary_report():
    rep, problems = {}, []
    sources, current = G.quicbed_sources()
    for tag in ("g2", "g3b"):
        path = BINS[tag]
        info = {"path": path, "exists": os.path.isfile(path)}
        if info["exists"]:
            info["sha256"] = G.sha256_file(path)
            info["executable"] = os.access(path, os.X_OK)
            info["srcsha"] = G._read_text(path + ".srcsha")
            info["sha256_file"] = (G._read_text(path + ".sha256") or "").split(" ")[0] or None
            if not info["executable"]:
                problems.append("%s binary is not executable: %s" % (tag, path))
        else:
            problems.append("%s binary missing: %s (install with %s)" % (tag, path, INSTALL_HINT))
        rep[tag] = info
    g2, g3 = rep["g2"], rep["g3b"]
    if g2["exists"] and g2["sha256"] != G2_FROZEN_SHA256:
        problems.append("g2 binary sha256 %s is not the frozen %s" % (g2["sha256"],
                                                                       G2_FROZEN_SHA256))
    if g3["exists"]:
        g3["source_fingerprint_now"] = current
        if g3["sha256"] == G2_FROZEN_SHA256:
            problems.append("g3b binary is byte-identical to the frozen gen-2 binary")
        if not g3["srcsha"]:
            problems.append("g3b binary has no qamp.srcsha next to it (install with %s)"
                            % INSTALL_HINT)
        elif g3["srcsha"] != current:
            problems.append("g3b binary was built from other sources: srcsha %s, "
                            "experiments/quicbed now %s (rebuild with %s)"
                            % (g3["srcsha"], current, INSTALL_HINT))
        if g3["sha256_file"] and g3["sha256_file"] != g3["sha256"]:
            problems.append("g3b binary does not match its qamp.sha256")
    rep["stage0_g3"] = {"path": STAGE0_G3_BIN, "sha256": G.sha256_or_none(STAGE0_G3_BIN),
                        "note": "recorded only; p21 never runs or writes it"}
    rep["frozen_g2_sha256"] = G2_FROZEN_SHA256
    rep["quicbed_sources"] = sources
    return rep, problems


def flag_report(rep):
    out, problems = {}, []
    for tag in ("g2", "g3b"):
        if not rep.get(tag, {}).get("exists"):
            out[tag] = None
            continue
        flags, err = G.help_flags(rep[tag]["path"])
        text = help_text(rep[tag]["path"])
        out[tag] = {"flags": flags, "error": err, "mentions_auto3": "auto3" in text}
        if flags is None:
            problems.append("%s -h failed: %s" % (tag, err))
            continue
        have = set(flags)
        if tag == "g3b":
            need = {"cache3", "layout", "lead"}
            if not need <= have:
                problems.append("g3b binary lacks %s (flags: %s)"
                                % (sorted(need - have), ", ".join(flags)))
            if "auto3" not in text:
                problems.append("g3b -h does not mention -fec auto3; an unknown -fec value "
                                "silently means off in qamp")
        if tag == "g2" and ("layout" in have or "cache3" in have):
            problems.append("g2 binary unexpectedly has -layout/-cache3")
    return out, problems


def help_text(path):
    try:
        r = subprocess.run([path, "-h"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (r.stdout or "") + (r.stderr or "")


def validate_arm(arm):
    a = ARMS[arm]
    vdir = os.path.join(WORK, "validate")
    os.makedirs(vdir, exist_ok=True)
    cache = os.path.join(vdir, "%s.json" % arm)
    argv = ([BINS[a["bin"]], "-mode", "client", "-addr", "%s:%d" % (B.RX_IP, SLOTS[a["slot"]]),
             "-n", "0"] + arm_flags(arm, cache))
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, argv, str(exc)
    finally:
        try:
            os.unlink(cache)
        except OSError:
            pass
    text = ((r.stdout or "") + (r.stderr or "")).strip()
    return r.returncode == 0, argv, text[-300:]


def _consts(path, pol=None):
    with open(path, encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src)

    def val(node):
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id == "POL"):
            return (pol or {}).get(node.attr)
        if isinstance(node, (ast.List, ast.Tuple)):
            return [val(e) for e in node.elts]
        try:
            return ast.literal_eval(node)
        except (ValueError, TypeError, SyntaxError):
            return None

    out = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            out[node.targets[0].id] = val(node.value)
    return out, src


def mirror_check():
    out = {"sources": {}, "facts": {}, "differences": [], "ok": False}
    files = {"p17": "experiments/p17_adaptive_value.py", "p11": "experiments/p11_adaptive.py",
             "p15": "experiments/p15_v2policy.py", "p18": "experiments/p18_mmax.py",
             "policy": "padfec/policy.py", "qamp": "experiments/quicbed/qamp.go"}
    try:
        pol, _ = _consts(os.path.join(ROOT, files["policy"]))
        c17, s17 = _consts(os.path.join(ROOT, files["p17"]), pol)
        c11, s11 = _consts(os.path.join(ROOT, files["p11"]), pol)
        c15, s15 = _consts(os.path.join(ROOT, files["p15"]), pol)
        c18, s18 = _consts(os.path.join(ROOT, files["p18"]), pol)
        with open(os.path.join(ROOT, files["qamp"]), encoding="utf-8") as f:
            sq = f.read()
    except (OSError, SyntaxError) as exc:
        out["differences"].append("cannot parse a mirrored script: %s" % exc)
        return out
    for k, rel in files.items():
        out["sources"][k] = {"path": rel, "sha256": G.sha256_or_none(os.path.join(ROOT, rel))}
    p17 = {}
    for e in c17.get("CONDS") or []:
        if isinstance(e, list) and len(e) == 5:
            p17[e[0]] = {"netem_rate_mbit": e[1], "uplink_policy_mbps": e[2], "cert": e[3],
                         "rtt_ms": e[4]}
    for key, name in P17_NAMES.items():
        ours = PROFILES[key]
        theirs = p17.get(name)
        if theirs is None:
            out["differences"].append("p17 has no condition %r" % name)
            continue
        for f in ("netem_rate_mbit", "uplink_policy_mbps", "cert", "rtt_ms"):
            if ours[f] != theirs[f]:
                out["differences"].append("p17 %s.%s: ours %r, p17 %r" % (name, f, ours[f],
                                                                          theirs[f]))
    sched = c17.get("SCHEDULE") or []
    p11c = {(e[1], e[2]) for e in c11.get("CONDS") or [] if isinstance(e, list) and len(e) == 3}
    p15c = {(e[1], e[2]) for e in c15.get("CONDS") or [] if isinstance(e, list) and len(e) == 3}
    p18c = [e for e in c18.get("CONDS") or [] if isinstance(e, list) and len(e) == 6]
    facts = {
        "p17_group_k": c17.get("GROUP") == MLKEM and c17.get("K") == 2,
        "p17_segment_450": c17.get("N_PRECISE") == P17_SEGMENT,
        "p17_losses": [x[0] for x in sched if isinstance(x, list)] == list(P17_LOSSES),
        "p17_auto_flags": bool(re.search(
            r'\["-cache", CACHE, "-probe-every", "20"\]\s*\n?\s*if fec == "auto"', s17)),
        "p17_auto_m1": "m=max(m, 1)" in s17,
        "p17_gap_rule": bool(re.search(r"gap_ms\s*=\s*50\s+if\s+rate\s*>\s*0\s+else\s+8", s17)),
        "p17_timeout_10": "timeout_s=10" in s17,
        "p17_server_fec_on": 'B.start_server(cert, fec="on"' in s17,
        "p17_netem_call": bool(re.search(
            r"B\.set_netem\(rtt\s*/\s*2\.0,\s*loss_c2s=loss,\s*rate_up_mbit=rate\)", s17)),
        "p11_conds": p11c == {(2955, 0.0), (2955, 2.0), (2955, 5.0), (9000, 0.0), (9000, 2.0),
                              (9000, 5.0)},
        "p11_blocks_10": c11.get("BLOCKS") == BLOCKS,
        "p11_group_k_rtt_uplink": (c11.get("GROUP") == MLKEM and c11.get("K") == 2
                                   and c11.get("RTT_MS") == 50.0
                                   and c11.get("UPLINK_MBPS") == 0.0),
        "p11_auto_flags": '"auto", 1, ["-cache", CACHE]' in s11,
        "p11_gap_8": "gap_ms=8" in s11,
        "qamp_probe_every_default_20": 'flag.Int("probe-every", 20,' in sq,
        "p15_conds": {(4032, 0.0), (4032, 2.0), (4032, 5.0)} <= p15c,
        "p15_group_k_rtt_uplink": (c15.get("GROUP") == X25519 and c15.get("K") == 1
                                   and c15.get("RTT_MS") == 50.0
                                   and c15.get("UPLINK_MBPS") == 0.0),
        "p15_auto_flags": 'extra=["-cache", CACHE, "-probe-every", "20"]' in s15,
        "p15_gap_8": "gap_ms=8" in s15,
        "p15_l540_threshold_0_7_of_m2": "ab < 0.7 * m2b" in s15,
        "p18_burst3_cond": any(e[1] == 4032 and e[2] == 3.0 and e[3] == 15.0 and e[4] == 0.0
                               for e in p18c),
        "p18_group_k_rtt": (c18.get("GROUP") == MLKEM and c18.get("K") == 2
                            and c18.get("RTT_MS") == 50.0),
        "p18_gap_rule": "gap_ms=(50 if up > 0 else 8)" in s18,
        "p18_netem_burst": "burst_len=L" in s18,
    }
    out["facts"] = facts
    for k, v in facts.items():
        if not v:
            out["differences"].append("mirror fact not confirmed: %s" % k)
    out["notes"] = [
        "p11 passes only -cache; qamp's -probe-every default is 20, so p17's explicit "
        "-probe-every 20 gives the same g2 client in every condition",
        "p15 used 1600 fixed-arm trials and 10 auto rounds of 1600; here both auto arms get "
        "1600 in 10 AB/BA blocks like p11",
        "p18 measured fixed m1..m4 only; here the two auto arms run its burst-3 condition",
    ]
    out["ok"] = not out["differences"]
    return out


def seal_files():
    rels = list(SEALED_FIXED)
    for pattern in SEALED_GLOBS:
        for p in sorted(glob.glob(os.path.join(ROOT, pattern))):
            r = os.path.relpath(p, ROOT).replace("\\", "/")
            if r not in rels:
                rels.append(r)
    return rels


def seal_check():
    path = os.path.join(ROOT, SEAL_REL)
    out = {"path": SEAL_REL, "sha256": G.sha256_or_none(path), "changed": [], "missing": [],
           "unsealed_new": [], "ok": False}
    seal = read_json(path)
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
    out["unsealed_new"] = [r for r in seal_files() if r not in files]
    out["sealed_utc"] = seal.get("sealed_utc")
    out["binaries"] = seal.get("binaries")
    out["h_cells"] = seal.get("h_cells")
    out["ok"] = not out["changed"] and not out["missing"] and not out["unsealed_new"]
    return out


def draw_check(srcsha=None):
    path = os.path.join(ROOT, HDRAW_REL)
    d = read_json(path)
    out = {"path": HDRAW_REL, "exists": d is not None, "ok": False, "cells": None,
           "problems": []}
    if d is None:
        out["problems"].append("H draw not made yet (%s); it is made after the gate passes"
                               % HDRAW_REL)
        return out
    src = d.get("source_fingerprint")
    try:
        again = h_draw(src)
    except ValueError as exc:
        out["problems"].append(str(exc))
        return out
    if again["cells"] != d.get("cells") or again["seed"] != d.get("seed"):
        out["problems"].append("recorded draw does not reproduce from its fingerprint")
    if srcsha is not None and srcsha != src:
        out["problems"].append("draw used source fingerprint %s but g3b is %s" % (src, srcsha))
    grid = {c["cell"]: c for c in h_cells()}
    if any(c not in grid for c in d.get("cells") or []):
        out["problems"].append("draw names a cell outside the grid")
    out["cells"] = [grid[c] for c in d.get("cells") or [] if c in grid]
    out["source_fingerprint"] = src
    out["ok"] = not out["problems"]
    return out


H_PRED_RULE = (
    "structure only, no learning: for each drawn cell and each loss p of its schedule "
    "(1%% and 8%%), Delta(p) = min over gen-2-representable actions of J3 minus min over "
    "the full v3 candidate set of J3, both from padfec3/layout.py at the exact p; gen-2 "
    "actions = the candidates policy.decide_v2 keeps from quantum.levers (delta from the "
    "gen-2 levers, m <= %d, lead = [m>=2]) scored with later='g2'; v3 actions = "
    "decide3.candidates3 scored with later='v3'; common inputs k=%d (ML-KEM, ClientHello "
    "%d B), W=%d, the cell's cert, RTT and uplink, n_need = layout.n_need(cert, "
    "S0_BASE_MLKEM, C_PKT_POLICY_DEFAULT), and for candidates3 the server-bytes equivalent "
    "S = cert + s0_at(bin_index(k*W)) that gives the same n_need; delta_hat_ms = "
    "%.1f*Delta(1%%) + %.1f*Delta(8%%) (equal time at both losses)"
    % (H_G2_M_MAX, H_K, H_C_MLKEM, H_W, H_WEIGHTS[0], H_WEIGHTS[1]))


def _padfec_modules():
    if PKG_ROOT not in sys.path:
        sys.path.insert(0, PKG_ROOT)
    from padfec import policy, quantum
    from padfec3 import decide3, layout, learn3
    return policy, quantum, layout, learn3, decide3


def h_cell_inputs(cell):
    policy, quantum, layout, learn3, _d = _padfec_modules()
    s0b, cp = policy.S0_BASE_MLKEM, policy.C_PKT_POLICY_DEFAULT
    base_bin = quantum.bin_index(H_K * H_W)
    need = layout.n_need(cell["cert"], s0_base=s0b, c_pkt=cp)
    s_eq = cell["cert"] + quantum.s0_at(base_bin, s0b, cp)
    if learn3.bin_needed_s(s_eq, base_bin, cp) != need:
        raise ValueError("%s: server-bytes equivalent %r does not give n_need %d"
                         % (cell["cell"], s_eq, need))
    return {"k": H_K, "W": H_W, "cert": cell["cert"], "rtt_ms": float(cell["rtt_ms"]),
            "uplink_mbps": float(cell["uplink_mbps"]), "n_need": need,
            "server_bytes_equiv": s_eq, "s0_base": s0b, "c_pkt": cp}


def h_g2_actions(inp):
    policy, _q, layout, _l, _d = _padfec_modules()
    r = policy.decide_v2(C=H_C_MLKEM, cert_bytes=inp["cert"], rtt_ms=inp["rtt_ms"],
                         p=H_LOSSES[0] / 100.0, burst=1.0, s0=None, W=inp["W"],
                         s0_base=inp["s0_base"], c_pkt=inp["c_pkt"],
                         uplink_mbps=inp["uplink_mbps"], max_ips=policy.QUICGO_MAX_IPS)
    out = []
    for c in r["candidates"]:
        if c["k"] != inp["k"]:
            raise ValueError("gen-2 lever candidate with k=%r, expected %d" % (c["k"], inp["k"]))
        m = c["m"]
        if m > H_G2_M_MAX:
            continue
        lead = layout.legacy_lead(m)
        a = (c["delta_per_dgram"], lead, m - lead)
        if a not in [x["action"] for x in out]:
            out.append({"action": a, "W_eff": c["W_eff"], "m": m, "lead": lead})
    return out


def h_g3_actions(inp):
    _p, _q, _layout, _l, decide3 = _padfec_modules()
    return [{"action": tuple(c["action"]), "W_eff": c["W_eff"], "m": c["m"], "lead": c["lead"]}
            for c in decide3.candidates3(inp["k"], inp["W"], inp["server_bytes_equiv"],
                                         inp["c_pkt"])]


def h_best(cands, inp, p, later):
    _p, _q, layout, _l, _d = _padfec_modules()
    return min((layout.j3(inp["k"], c["W_eff"], c["m"], c["lead"], p, inp["rtt_ms"],
                          inp["uplink_mbps"], inp["n_need"], later=later), c["action"])
               for c in cands)


def h_predict_cell(cell):
    inp = h_cell_inputs(cell)
    g2, g3 = h_g2_actions(inp), h_g3_actions(inp)
    by_loss, dh = {}, 0.0
    for wgt, loss in zip(H_WEIGHTS, H_LOSSES):
        p = loss / 100.0
        jg2, ag2 = h_best(g2, inp, p, H_LATER["g2"])
        jg3, ag3 = h_best(g3, inp, p, H_LATER["g3"])
        by_loss["%g" % loss] = {"p": p, "j_g2": jg2, "j_g3": jg3, "delta_ms": jg2 - jg3,
                                "argmin_g2": list(ag2), "argmin_g3": list(ag3)}
        dh += wgt * (jg2 - jg3)
    return {"cell": cell["cell"], "inputs": inp, "n_actions_g2": len(g2),
            "n_actions_g3": len(g3), "actions_g2": [list(c["action"]) for c in g2],
            "delta_hat_ms": dh, "h3_target": dh >= H3_MIN_PRED_MS,
            "j_g2": {k: v["j_g2"] for k, v in by_loss.items()},
            "j_g3": {k: v["j_g3"] for k, v in by_loss.items()},
            "argmin_g2": {k: v["argmin_g2"] for k, v in by_loss.items()},
            "argmin_g3": {k: v["argmin_g3"] for k, v in by_loss.items()},
            "by_loss": by_loss}


def h_predictions(cells, draw_sha):
    return {"schema": "padfec3.stage2_h_predictions.v1", "generated_utc": utc_now(),
            "generator": "experiments/p21_gencompare.py h_predictions (--draw-h, --predict-h)",
            "draw_sha256": draw_sha,
            "layout_py_sha256": G.sha256_or_none(os.path.join(PKG_ROOT, "padfec3", "layout.py")),
            "code_sha256": {r: G.sha256_or_none(os.path.join(PKG_ROOT, r)) for r in HPRED_DEPS},
            "definition": H_PRED_RULE, "losses_pct": list(H_LOSSES),
            "weights": list(H_WEIGHTS), "h3_min_pred_ms": H3_MIN_PRED_MS,
            "cells": {c["cell"]: h_predict_cell(c) for c in cells}}


def predictions_check(cells):
    d = read_json(os.path.join(ROOT, HPRED_REL))
    out = {"path": HPRED_REL, "exists": d is not None, "ok": False, "problems": []}
    if d is None:
        out["problems"].append("H prediction table missing (%s)" % HPRED_REL)
        return out
    pc = d.get("cells")
    want = sorted(c["cell"] for c in cells or [])
    if not isinstance(pc, dict) or sorted(pc) != want:
        out["problems"].append("prediction cells %s differ from the draw %s"
                               % (sorted(pc or {}), want))
    else:
        for k, v in pc.items():
            if not isinstance(v, dict) or not isinstance(v.get("delta_hat_ms"), (int, float)):
                out["problems"].append("%s: delta_hat_ms missing" % k)
    if d.get("draw_sha256") != G.sha256_or_none(os.path.join(ROOT, HDRAW_REL)):
        out["problems"].append("prediction table does not name the current draw file sha256")
    if not out["problems"]:
        for c in cells:
            try:
                again = h_predict_cell(c)["delta_hat_ms"]
            except (ImportError, ValueError, TypeError, KeyError, RuntimeError) as exc:
                out["problems"].append("%s: cannot recompute the prediction: %s"
                                       % (c["cell"], exc))
                continue
            got = pc[c["cell"]]["delta_hat_ms"]
            if abs(again - got) > HPRED_TOL_MS:
                out["problems"].append("%s: recorded delta_hat_ms %r does not reproduce "
                                       "(recomputed %r)" % (c["cell"], got, again))
    out["ok"] = not out["problems"]
    return out


def print_predictions(d):
    print("H predictions (%s), definition: %s" % (HPRED_REL, d.get("definition")))
    print("| 셀 id | J_g2(1%) | J_g3(1%) | J_g2(8%) | J_g3(8%) | delta_hat ms | H3 대상 |")
    print("|---|---:|---:|---:|---:|---:|---|")
    for cid, v in sorted((d.get("cells") or {}).items()):
        jg2, jg3 = v["j_g2"], v["j_g3"]
        lo, hi = "%g" % H_LOSSES[0], "%g" % H_LOSSES[1]
        print("| %s | %.3f | %.3f | %.3f | %.3f | %.3f | %s |"
              % (cid, jg2[lo], jg3[lo], jg2[hi], jg3[hi], v["delta_hat_ms"],
                 "예" if v["delta_hat_ms"] >= H3_MIN_PRED_MS else "아니오"))
    for cid, v in sorted((d.get("cells") or {}).items()):
        print("  %s argmin g2 %s, g3 %s (delta, lead, T); actions g2 %d, g3 %d"
              % (cid, json.dumps(v["argmin_g2"]), json.dumps(v["argmin_g3"]),
                 v["n_actions_g2"], v["n_actions_g3"]))


def dev_data_manifest(with_hash=True):
    out = {}
    for p in DEV_DATA:
        lp = local_path(p)
        ent = {"exists": os.path.isfile(lp)}
        if ent["exists"]:
            ent["bytes"] = os.path.getsize(lp)
            if with_hash:
                ent["sha256"] = G.sha256_or_none(lp)
        out[p] = ent
    for pattern in DEV_GLOBS:
        for lp in sorted(glob.glob(os.path.join(ROOT, pattern))):
            r = os.path.relpath(lp, ROOT).replace("\\", "/")
            ent = {"exists": True, "bytes": os.path.getsize(lp)}
            if with_hash:
                ent["sha256"] = G.sha256_or_none(lp)
            out[r] = ent
    return out


def setup():
    os.makedirs(WORK, exist_ok=True)
    saved = B.WORK
    B.WORK = WORK
    try:
        B.setup(1500)
    finally:
        B.WORK = saved


def set_netem(prof, loss):
    one = prof["rtt_ms"] / 2.0
    B.set_netem(one, loss_c2s=loss, burst_len=prof["burst"],
                rate_up_mbit=prof["netem_rate_mbit"])
    out = {"c2s": B._netem_spec(one, loss, prof["burst"], prof["netem_rate_mbit"]),
           "s2c": B._netem_spec(one, 0.0, prof["burst"], 0.0)}
    out["tc_c2s"] = B.run("tc qdisc show dev %s" % B.DEV_LOCAL, check=False).stdout.strip()
    out["tc_s2c"] = B.run("ip netns exec %s tc qdisc show dev %s" % (B.NS, B.DEV_PEER),
                          check=False).stdout.strip()
    return out


def start_server(slot, tag, cert):
    path = BINS[tag]
    stats_path = os.path.join(WORK, "srv_%s.json" % slot)
    err_path = os.path.join(WORK, "srv_%s_stderr.txt" % slot)
    for p in (stats_path, stats_path + ".tmp"):
        try:
            os.unlink(p)
        except OSError:
            pass
    cmd = ["ip", "netns", "exec", B.NS] + B.TASKSET + [
        path, "-mode", "server", "-addr", "%s:%d" % (B.RX_IP, SLOTS[slot]),
        "-certsize", str(cert), "-fec", SERVER_FEC, "-stats", stats_path]
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
        raise RuntimeError("server %s (%s) not ready: %s"
                           % (slot, tag, text[-1000:].decode("utf-8", "replace")))
    der = re.search(rb"cert DER = (\d+) bytes", text)
    return {"slot": slot, "tag": tag, "proc": p, "pid": p.pid, "stats_path": stats_path,
            "argv": cmd, "certsize": cert, "cert_der": int(der.group(1)) if der else None}


def stop_server(server):
    if server:
        B.stop_server(server.get("proc"))


def server_alive(server):
    return bool(server) and server["proc"].poll() is None


def start_servers(cond):
    servers = {}
    try:
        for slot in sorted(cond["servers"]):
            servers[slot] = start_server(slot, cond["servers"][slot], cond["profile"]["cert"])
    except Exception:
        stop_servers(servers)
        raise
    return servers


def stop_servers(servers):
    for s in (servers or {}).values():
        stop_server(s)


def run_client(arm, n, prof, cache_path):
    a = ARMS[arm]
    stats_path = os.path.join(WORK, "cli_stats.json")
    try:
        os.unlink(stats_path)
    except OSError:
        pass
    argv = ([BINS[a["bin"]], "-mode", "client", "-addr", "%s:%d" % (B.RX_IP, SLOTS[a["slot"]]),
             "-group", prof["group"], "-n", str(n)] + arm_flags(arm, cache_path)
            + ["-gap", "%dms" % int(prof["gap_ms"]), "-timeout", "%ds" % TIMEOUT_S,
               "-stats", stats_path, "-uplink-mbps", "%g" % prof["uplink_policy_mbps"],
               "-expect-k", str(prof["expect_k"])])
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
    stats = read_json(stats_path) or {}
    err = ""
    if r.returncode != 0:
        tail = (r.stderr or "")[-300:].strip().replace("\n", " | ")
        err = "timeout(rc124)" if r.returncode == 124 else "exit %d: %s" % (r.returncode, tail)
    elif len(rows) != n:
        err = "rows %d != n %d" % (len(rows), n)
    elif not stats:
        err = "client stats missing"
    return rows, stats, err, argv, r.returncode


def cache_path(run, cond, arm):
    return os.path.join(WORK, "cache", "%s_%s_%s.json" % (run, cond, arm))


def cache_read(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
    except FileNotFoundError:
        return {"exists": False, "sha256": None, "text": None}
    except OSError as exc:
        return {"exists": None, "sha256": None, "text": None, "error": str(exc)}
    return {"exists": True, "sha256": hashlib.sha256(data).hexdigest(),
            "text": data.decode("utf-8", "replace")}


def cache_write(path, snap):
    try:
        os.unlink(path)
    except OSError:
        pass
    if snap and snap.get("exists") and snap.get("text") is not None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(snap["text"])
        if cache_read(path)["sha256"] != snap["sha256"]:
            raise RuntimeError("cache restore mismatch for %s" % path)


def caches_snapshot(run, cond):
    return {a: cache_read(cache_path(run, cond["cond"], a)) for a in cond["arms"] if is_auto(a)}


def caches_restore(run, cond, snaps):
    for a in cond["arms"]:
        if is_auto(a):
            cache_write(cache_path(run, cond["cond"], a), (snaps or {}).get(a))


def run_segment(run, cond, arm, n, pos, servers, clear_cache):
    a = ARMS[arm]
    prof = cond["profile"]
    slot = a["slot"]
    slots = sorted(servers)
    others = [s for s in slots if s != slot]
    cpath = cache_path(run, cond["cond"], arm)
    if clear_cache and is_auto(arm):
        cache_write(cpath, None)
    cb = cache_read(cpath)["sha256"] if is_auto(arm) else None
    before = {s: G.read_stats(servers[s]["stats_path"]) for s in slots}
    started = utc_now()
    t0 = time.monotonic()
    os.makedirs(os.path.dirname(cpath), exist_ok=True)
    rows, cstats, client_err, argv, rc = run_client(arm, n, prof, cpath)
    wall = time.monotonic() - t0
    time.sleep(settle_s(prof))
    after = {s: G.read_stats(servers[s]["stats_path"]) for s in slots}
    alive = {s: server_alive(servers[s]) for s in slots}
    other_delta = sum_numeric(G.scalar_delta(before[s], after[s]) for s in others)
    err = ""
    if not all(alive.values()):
        err = "server died: %s" % [s for s, v in alive.items() if not v]
    elif not before[slot] or not after[slot]:
        err = "server stats missing"
    if len(rows) > n:
        err = err or "rows %d > n %d" % (len(rows), n)
    if rc in (126, 127):
        err = err or "client could not be executed (rc %d): %s" % (rc, client_err)
    return {"arm": arm, "pos": pos, "bin": a["bin"], "slot": slot, "port": SLOTS[slot],
            "server_binary": servers[slot]["tag"], "argv": argv, "rc": rc, "err": err,
            "client_err": client_err or "", "n_planned": n, "n_rows": len(rows),
            "rows": rows, "client_stats": cstats,
            "server_delta": G.scalar_delta(before[slot], after[slot]),
            "server_after": G.scalars(after[slot]),
            "other_server_delta": {k: v for k, v in other_delta.items() if v},
            "cache_before_sha256": cb,
            "cache_after_sha256": cache_read(cpath)["sha256"] if is_auto(arm) else None,
            "started_at": started, "finished_at": utc_now(), "wall_s": wall}


def run_block(run, cond, blk, servers, attempt, bins_sha):
    started = utc_now()
    netem = set_netem(cond["profile"], blk["loss"])
    segs = []
    for pos, arm in enumerate(blk["order"]):
        segs.append(run_segment(run, cond, arm, blk["sizes"][arm], pos, servers,
                                blk["clear_cache"]))
        if segs[-1]["err"]:
            break
    err = next((s["err"] for s in segs if s["err"]), "")
    return {"cond": blk["cond"], "block": blk["block"], "cycle": blk["cycle"],
            "stratum": blk["stratum"], "loss": blk["loss"], "order": blk["order"],
            "sizes": blk["sizes"], "attempt": attempt, "started_at": started,
            "finished_at": utc_now(), "netem": netem,
            "servers": {s: {k: v[k] for k in ("tag", "pid", "cert_der", "certsize", "argv")}
                        for s, v in servers.items()},
            "segments": segs, "cache_after": caches_snapshot(run, cond),
            "load_processes": G.load_processes(), "bins_sha256": bins_sha,
            "runner_sha256": G.sha256_or_none(os.path.abspath(__file__)), "err": err,
            "client_errors": [{"arm": s["arm"], "rc": s["rc"], "err": s["client_err"],
                               "n_rows": s["n_rows"], "n_planned": s["n_planned"]}
                              for s in segs if s.get("client_err")]}


class Abort(Exception):
    pass


def run_condition(run, cond, plan, fp, P, start_bins, journal_ids, save_meta=None):
    jr = Journal(journal_path(run, cond["cond"]), fp)
    journal_ids[cond["cond"]] = jr.run_id
    if save_meta is not None:
        save_meta()
    blocks = [b for b in plan["schedule"] if b["cond"] == cond["cond"]]
    done = [block_complete(jr.get(unit_key(run, cond["cond"], b["block"])), b) for b in blocks]
    first = next((i for i, d in enumerate(done) if not d), None)
    if first is None:
        return 0
    if not all(done[:first]) or any(done[first:]):
        later = [b["block"] for b, d in zip(blocks[first:], done[first:]) if d]
        if later:
            incident(P, {"cond": cond["cond"], "note": "blocks after the first incomplete one "
                         "are journaled and will be rerun in order", "blocks": later})
    if first == 0:
        caches_restore(run, cond, None)
    else:
        prev = jr.get(unit_key(run, cond["cond"], blocks[first - 1]["block"]))
        caches_restore(run, cond, prev.get("cache_after"))
        incident(P, {"cond": cond["cond"], "resumed_at_block": blocks[first]["block"], "fp": fp,
                     "restored_caches": {a: (v or {}).get("sha256")
                                         for a, v in (prev.get("cache_after") or {}).items()}})
    servers = start_servers(cond)
    try:
        for blk in blocks[first:]:
            key = unit_key(run, cond["cond"], blk["block"])
            for attempt in (1, 2):
                busy = G.busy_processes([s["pid"] for s in servers.values()])
                bins_now = {t: G.sha256_or_none(BINS[t]) for t in BINS}
                if busy or bins_now != start_bins:
                    why = busy or ["binary changed: %s" % bins_now]
                    incident(P, {"key": key, "attempt": attempt, "abort": why, "fp": fp})
                    raise Abort("before %s: %s" % (key, why))
                if not all(server_alive(s) for s in servers.values()):
                    stop_servers(servers)
                    servers = start_servers(cond)
                snap = caches_snapshot(run, cond)
                write_status(P, run=run, state="running", current=key, attempt=attempt)
                rec = run_block(run, cond, blk, servers, attempt, bins_now)
                if block_complete(rec, blk):
                    jr.record(key, rec)
                    if rec["client_errors"]:
                        incident(P, {"key": key, "attempt": attempt, "fp": fp,
                                     "kept_as_data": True,
                                     "client_errors": rec["client_errors"]})
                    break
                incident(P, {"key": key, "attempt": attempt, "fp": fp, "err": rec["err"],
                             "segments": [{"arm": s["arm"], "rc": s["rc"], "err": s["err"],
                                           "client_err": s.get("client_err"),
                                           "n_rows": s["n_rows"],
                                           "n_planned": s["n_planned"]}
                                          for s in rec["segments"]]})
                caches_restore(run, cond, snap)
                stop_servers(servers)
                servers = start_servers(cond)
            else:
                raise Abort("%s failed twice; rerun the same command to resume" % key)
            print("   %-22s b%03d %-30s recorded" % (cond["cond"], blk["block"],
                                                     " ".join(blk["order"])), flush=True)
    finally:
        stop_servers(servers)
    return len(blocks) - first


def execute(run, plan, meta, P, start_bins, seal_sha):
    journal_ids = meta["starts"][-1].setdefault("journal_run_ids", {})
    est = {r["cond"]: r["seconds"] for r in estimate(plan)["conds"]}
    t0 = time.monotonic()
    for i, cond in enumerate(plan["conds"]):
        fp = meta["fps"][cond["cond"]]
        n = run_condition(run, cond, plan, fp, P, start_bins, journal_ids,
                          lambda: atomic_write_json(P["meta"], meta, indent=1))
        atomic_write_json(P["meta"], meta, indent=1)
        rem = sum(est[c["cond"]] for c in plan["conds"][i + 1:])
        write_status(P, run=run, state="running", conds_done=i + 1,
                     conds_total=len(plan["conds"]), elapsed_s=time.monotonic() - t0,
                     planned_remaining_s=rem)
        print("[%2d/%2d] %-22s %s" % (i + 1, len(plan["conds"]), cond["cond"],
                                      "%d blocks run" % n if n else "already journaled"),
              flush=True)
    return 0


def refuse(lines):
    for line in lines:
        print("REFUSED: %s" % line, file=sys.stderr)
    return 2


def _sigterm(_signum, _frame):
    raise SystemExit(143)


def preflight(run):
    problems = []
    binrep, bp = binary_report()
    problems += bp
    flags, fp_ = flag_report(binrep) if not bp else (None, [])
    problems += fp_
    mirror = mirror_check()
    if not mirror["ok"]:
        problems += ["mirror check: %s" % d for d in mirror["differences"]]
    seal = seal_check()
    srcsha = binrep["g3b"].get("srcsha")
    draw = draw_check(srcsha)
    hcells = None
    preds = None
    if run in ("run1", "run2"):
        if not seal["ok"]:
            problems.append("seal check failed (%s): changed %s, missing %s, unsealed %s"
                            % (SEAL_REL, seal["changed"], seal["missing"],
                               seal["unsealed_new"]))
        sb = seal.get("binaries") or {}
        for tag in ("g2", "g3b"):
            if sb.get(tag) != binrep[tag].get("sha256"):
                problems.append("%s binary %s is not the sealed %s"
                                % (tag, binrep[tag].get("sha256"), sb.get(tag)))
        if sb.get("g3b_srcsha") != srcsha:
            problems.append("g3b source fingerprint %s is not the sealed %s"
                            % (srcsha, sb.get("g3b_srcsha")))
    if run == "run1":
        problems += ["H draw: %s" % p for p in draw["problems"]]
        if draw["ok"]:
            hcells = draw["cells"]
            preds = predictions_check(hcells)
            problems += ["H predictions: %s" % p for p in preds["problems"]]
            if (seal.get("h_cells") or None) != [c["cell"] for c in hcells]:
                problems.append("sealed H cells %s differ from the draw" % seal.get("h_cells"))
    if run == "run2":
        m1 = read_json(paths("run1")["meta"])
        s1 = ((m1 or {}).get("starts") or [{}])[0].get("seal_check", {}).get("sha256")
        if m1 and s1 != seal.get("sha256"):
            problems.append("seal changed after run 1 (%s -> %s): run 1 is development data "
                            "now; re-seal and repeat run 1 first" % (s1, seal.get("sha256")))
    return {"binaries": binrep, "help_flags": flags, "mirror": mirror, "seal": seal,
            "draw": draw, "predictions": preds, "hcells": hcells}, problems


def live(run):
    B.harden()
    signal.signal(signal.SIGTERM, _sigterm)
    if not sys.platform.startswith("linux"):
        return refuse(["live modes run inside WSL Ubuntu: wsl -d Ubuntu -- bash -lc "
                       "'cd /mnt/c/dev/pq_afec_gen3 && %s && unshare -Urnm python3 -u "
                       "experiments/p21_gencompare.py --%s'" % (INSTALL_CMD, run)])
    B.require_root()
    os.environ.setdefault("PADFEC_GEN", GEN_DEFAULT)
    P = paths(run)
    busy = G.busy_processes()
    if busy:
        return refuse(["another measurement is running"] + busy)
    load = G.load_processes()
    if load:
        return refuse(["build or compile processes are running"] + load)
    pre, problems = preflight(run)
    if problems:
        return refuse(problems)
    plan = build_plan(run, pre["hcells"] if run == "run1" else None)
    validation = {}
    for a in plan["arms"]:
        ok, argv, text = validate_arm(a)
        validation[a] = {"ok": ok, "argv": argv, "output_tail": text}
        if not ok:
            problems.append("arm %s flags rejected by %s: %s" % (a, ARMS[a]["bin"], text))
    if problems:
        return refuse(problems)
    start_bins = {t: pre["binaries"][t]["sha256"] for t in BINS}
    seal_sha = pre["seal"].get("sha256") if run != "smoke" else None
    fps = {c["cond"]: cond_fingerprint(run, c, start_bins, seal_sha) for c in plan["conds"]}
    env = G.environment()
    env.pop("ports", None)
    env.update({"bins": BINS, "slots": SLOTS, "work": WORK, "bins_sha256": start_bins,
                "binaries": pre["binaries"], "help_flags": pre["help_flags"],
                "mirror_check": pre["mirror"], "seal_check": pre["seal"],
                "h_draw": pre["draw"], "h_predictions": pre["predictions"],
                "arm_flag_validation": validation, "source_hashes": source_hashes(),
                "runner_sha256": G.sha256_or_none(os.path.abspath(__file__)),
                "argv": sys.argv, "started_at": utc_now(), "pid": os.getpid(),
                "padfec_gen": os.environ.get("PADFEC_GEN")})
    meta = read_json(P["meta"])
    if not meta or meta.get("fps") != fps or canon(meta.get("plan")) != plan:
        meta = {"run": run, "plan": plan, "fps": fps, "starts": []}
    meta["starts"].append(env)
    meta.pop("finished", None)
    save_result(P["meta"], meta)
    print("p21 %s: %d conditions, %d blocks, label %s" % (
        run, len(plan["conds"]), len(plan["schedule"]),
        "smoke" if run == "smoke" else "sealed %s" % (seal_sha or "?")[:16]), flush=True)
    setup()
    try:
        execute(run, plan, meta, P, start_bins, seal_sha)
    except Abort as exc:
        write_status(P, run=run, state="aborted", reason=str(exc))
        atomic_write_json(P["meta"], meta, indent=1)
        print("ABORT %s" % exc, file=sys.stderr)
        return 3
    except (KeyboardInterrupt, SystemExit) as exc:
        write_status(P, run=run, state="interrupted")
        atomic_write_json(P["meta"], meta, indent=1)
        return exc.code if isinstance(exc, SystemExit) and exc.code else 130
    meta["finished"] = {"at": utc_now(), "source_hashes": source_hashes(),
                        "bins_sha256": {t: G.sha256_or_none(BINS[t]) for t in BINS}}
    save_result(P["meta"], meta)
    report = finalize(run, plan, meta)
    write_status(P, run=run, state="done", result=P["result"])
    print_summary(report)
    print("result: %s" % P["result"])
    return 0


def print_summary(report):
    print()
    print("=" * 100)
    print("p21 %s  label: %s" % (report["run"], report["label"]))
    for c in report["conds"]:
        print("%-22s %-7s blocks %d/%d" % (c["cond"], c["family"], c["blocks_done"],
                                           c["blocks_planned"]))
        for a, v in c["arms"].items():
            print("   %-9s n %5d/%5d fail %3d  mean* %9.2f  1RTT %.3f  ff-up %7.0f B"
                  % (a, v["n_returned"], v["n_requested"], v["failed"],
                     v["mean_planned_imputed_ms"] or -1, v["one_rtt_rate"] or 0.0,
                     v["ff_uplink_bytes_mean"] or 0.0))
        for con in c["contrasts"]:
            print("   %-7s est %s  95%% [%s, %s]  df %s" % (
                con["id"], fmt(con.get("est")), fmt(con.get("lo95")), fmt(con.get("hi95")),
                fmt(con.get("df"), 1)))
    integ = report["integrity"]
    print("integrity:", json.dumps({k: integ[k] for k in (
        "crc_fail_total", "acct_violation_segments", "cross_traffic_segments", "timeouts_total",
        "missing_trials", "binaries_constant", "sources_unchanged",
        "g3_rows_with_action_j3_pmean")}, ensure_ascii=False))


def fmt(x, nd=2):
    return ("%." + str(nd) + "f") % x if isinstance(x, (int, float)) else "-"


def report_only(run):
    B.harden()
    P = paths(run)
    meta = read_json(P["meta"])
    if not meta or "fps" not in meta:
        print("no meta file: %s" % P["meta"], file=sys.stderr)
        return 2
    plan = meta["plan"]
    missing = []
    for c in plan["conds"]:
        jr = Journal(journal_path(run, c["cond"]), meta["fps"][c["cond"]])
        for b in plan["schedule"]:
            if b["cond"] == c["cond"] and not block_complete(
                    jr.get(unit_key(run, c["cond"], b["block"])), b):
                missing.append(unit_key(run, c["cond"], b["block"]))
    if missing:
        print("incomplete: %d blocks missing, first %s" % (len(missing), missing[0]),
              file=sys.stderr)
        return 3
    report = finalize(run, plan, meta)
    print_summary(report)
    print("result: %s" % P["result"])
    return 0


def gate_check(gate, binrep):
    if not isinstance(gate, dict):
        return ["gate evidence is not a JSON object"]
    problems = []
    if gate.get("pass") is not True:
        problems.append("gate evidence does not record pass: true")
    gb = gate.get("binary") if isinstance(gate.get("binary"), dict) else {}
    g3 = binrep.get("g3b") or {}
    for k in ("sha256", "srcsha"):
        if not gb.get(k) or gb.get(k) != g3.get(k):
            problems.append("gate evidence binary %s %s is not the installed g3b %s"
                            % (k, gb.get(k), g3.get(k)))
    return problems


def draw_mode(gate_evidence):
    B.harden()
    if not sys.platform.startswith("linux"):
        return refuse(["--draw-h reads the installed g3b binary: run it in WSL Ubuntu"])
    if not gate_evidence or not os.path.isfile(gate_evidence):
        return refuse(["--draw-h needs --gate-evidence PATH (the passing gate result file)"])
    gate = read_json(gate_evidence)
    binrep, problems = binary_report()
    if problems:
        return refuse(problems)
    problems = gate_check(gate, binrep)
    if problems:
        return refuse(["gate evidence %s: %s" % (gate_evidence, p) for p in problems])
    d = h_draw(binrep["g3b"]["srcsha"])
    d.update({"schema": "padfec3.stage2_h_draw.v1", "drawn_utc": utc_now(),
              "grid": H_GRID, "g3b_sha256": binrep["g3b"]["sha256"],
              "gate_evidence": {"path": os.path.relpath(os.path.abspath(gate_evidence), ROOT)
                                .replace("\\", "/"),
                                "sha256": G.sha256_or_none(gate_evidence)}})
    path = os.path.join(ROOT, HDRAW_REL)
    old = read_json(path)
    if old is not None:
        if old.get("cells") != d["cells"] or old.get("seed") != d["seed"]:
            return refuse(["%s exists with another draw %s; a redraw is not allowed"
                           % (HDRAW_REL, old.get("cells"))])
        print("draw already recorded and reproduces: %s" % old["cells"])
    else:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print(json.dumps(d, ensure_ascii=False, indent=1))
    grid = {c["cell"]: c for c in h_cells()}
    return write_predictions([grid[c] for c in d["cells"]])


def write_predictions(cells):
    path = os.path.join(ROOT, HPRED_REL)
    if os.path.exists(path):
        chk = predictions_check(cells)
        if not chk["ok"]:
            return refuse(["%s exists but does not match the draw or the code: %s; it is not "
                           "overwritten (before the seal a person may delete it and rerun "
                           "--predict-h)" % (HPRED_REL, "; ".join(chk["problems"]))])
        print("H prediction table already recorded and reproduces")
        print_predictions(read_json(path))
        return 0
    data = h_predictions(cells, G.sha256_or_none(os.path.join(ROOT, HDRAW_REL)))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("wrote %s" % HPRED_REL)
    print_predictions(data)
    return 0


def predict_mode():
    B.harden()
    draw = draw_check()
    if not draw["ok"]:
        return refuse(["H draw: %s" % p for p in draw["problems"]])
    return write_predictions(draw["cells"])


def seal_mode():
    B.harden()
    if not sys.platform.startswith("linux"):
        return refuse(["--seal reads the installed binaries: run it in WSL Ubuntu"])
    path = os.path.join(ROOT, SEAL_REL)
    if os.path.exists(path):
        return refuse(["%s already exists; a new seal needs that file removed by hand and "
                       "the reason written in the protocol change log" % SEAL_REL])
    binrep, problems = binary_report()
    draw = draw_check(binrep["g3b"].get("srcsha"))
    problems += ["H draw: %s" % p for p in draw["problems"]]
    if draw["ok"]:
        problems += ["H predictions: %s" % p
                     for p in predictions_check(draw["cells"])["problems"]]
    try:
        with open(os.path.join(ROOT, PROTOCOL_REL), encoding="utf-8") as f:
            if TODO_MARK in f.read():
                problems.append("%s still has %s slots" % (PROTOCOL_REL, TODO_MARK))
    except OSError:
        problems.append("%s missing" % PROTOCOL_REL)
    rels = seal_files()
    miss = [r for r in rels if not os.path.isfile(os.path.join(ROOT, r))]
    problems += ["sealed file missing: %s" % r for r in miss]
    if problems:
        return refuse(problems)
    data = {"schema": "padfec3.stage2_seal.v1",
            "sealed_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "stage": "PAD-FEC v3 stage 2 (verdict_v3.md 4.3-4.5)",
            "sha256": {r: G.sha256_or_none(os.path.join(ROOT, r)) for r in rels},
            "also_recorded_sha256": {r: G.sha256_or_none(os.path.join(ROOT, r))
                                     for r in RECORDED},
            "binaries": {"g2": binrep["g2"]["sha256"], "g3b": binrep["g3b"]["sha256"],
                         "g3b_srcsha": binrep["g3b"]["srcsha"]},
            "h_cells": [c["cell"] for c in draw["cells"]],
            "development_data_sha256": dev_data_manifest(True),
            "check": "python3 experiments/p21_gencompare.py --dry-run"}
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("sealed %d files, binaries %s" % (len(rels), data["binaries"]))
    return 0


def print_plan(plan, est):
    print()
    total_conns = sum(r["connections"] for r in est["conds"])
    print("schedule %s: %d conditions, %d blocks, %d connections"
          % (plan["run"], len(plan["conds"]), len(plan["schedule"]), total_conns))
    rows = {r["cond"]: r for r in est["conds"]}
    for c in plan["conds"]:
        blocks = [b for b in plan["schedule"] if b["cond"] == c["cond"]]
        prof = c["profile"]
        r = rows[c["cond"]]
        if c["design"] == "sched":
            design = "losses %s, %d/segment, %d cycles" % (
                "<->".join("%g%%" % x for x in c["losses"]), c["segment_n"], c["cycles"])
        elif c["design"] == "cold":
            design = "loss %g%%, %d blocks of %d, caches cleared every segment" % (
                c["loss"], c["blocks"], COLD_SEGMENT)
        else:
            design = "loss %g%%, %d blocks, %d/arm" % (c["loss"], c["blocks"], c["n_per_arm"])
        print("  %-22s %-18s %s cert %d RTT %g up %g burst %g gap %d | %s | servers %s"
              "%s" % (c["cond"], c["batch"], prof["group"], prof["cert"], prof["rtt_ms"],
                      prof["netem_rate_mbit"], prof["burst"], prof["gap_ms"], design,
                      " ".join("%s=%s" % kv for kv in sorted(c["servers"].items())),
                      (" [off-grid smoke cell]" if c["batch"] == "smoke" else
                       " [placeholder until the draw]") if c.get("placeholder") else ""))
        print("      mirrors: %s; arms %s; n/arm %d; contrasts %s" % (
            c["mirrors"], ", ".join(c["arms"]), c["n_per_arm"],
            ", ".join("%s(%s)" % (k["id"], "+".join(k["use"])) for k in c["contrasts"])))
        show = blocks if len(blocks) <= 10 else blocks[:4]
        for b in show:
            print("      b%03d c%d s%d loss %5g  %s" % (b["block"], b["cycle"], b["stratum"],
                                                     b["loss"], "  ".join(
                                                         "%s:%d" % (a, b["sizes"][a])
                                                         for a in b["order"])))
        if len(blocks) > len(show):
            print("      ... %d more blocks, same alternation" % (len(blocks) - len(show)))
        bal = order_balance(c, blocks)
        print("      positions %s; precedence %s" % (json.dumps(bal["positions"]),
                                                     json.dumps(bal["precedence"])))
        print("      estimate %.0f s (%d conns x %.3f s %s + %d segments)" % (
            r["seconds"], r["connections"], r["s_per_conn"], r["s_per_conn_source"],
            r["segments"]))


def dry_run():
    B.harden()
    print("p21_gencompare dry run: no root, no network, nothing written")
    print("protocol: %s ; verdict: %s" % (PROTOCOL_REL, VERDICT))
    mirror = mirror_check()
    print()
    print("mirror check against the gen-2 stage scripts: %s" % (
        "ok" if mirror["ok"] else "DIFFERENCES %s" % mirror["differences"]))
    print("  facts: %s" % ", ".join("%s=%s" % (k, "ok" if v else "NO")
                                    for k, v in mirror["facts"].items()))
    for n in mirror.get("notes", []):
        print("  note: %s" % n)
    print()
    print("network profiles (netem on v0 client->server; v1 server->client delay only):")
    for k, p in PROFILES.items():
        print("  %-11s %-14s k=%d cert %5d RTT %5g up %g burst %g gap %d ms | v0 '%s'"
              % (k, p["group"], p["expect_k"], p["cert"], p["rtt_ms"], p["netem_rate_mbit"],
                 p["burst"], p["gap_ms"],
                 B._netem_spec(p["rtt_ms"] / 2.0, 2.0, p["burst"], p["netem_rate_mbit"])))
    print()
    print("servers (peer netns, -fec %s, own stats file, started fresh per condition):"
          % SERVER_FEC)
    for slot, port in SLOTS.items():
        uses = Counter()
        for c in build_plan("run1")["conds"] + build_plan("run2")["conds"]:
            if slot in c["servers"]:
                uses["%s server in %s" % (c["servers"][slot], c["batch"])] += 1
        print("  slot %s :%d  %s" % (slot, port, "; ".join(
            "%s (%d conditions)" % (k, v) for k, v in sorted(uses.items()))))
    print("  each arm of a condition has its own server process (S run 1: g2auto on A, "
          "g3auto on B, the g3-fixed arm on C)")
    print()
    print("arms (client in root netns, %s):" % (" ".join(B.TASKSET) or "no taskset"))
    for a, v in ARMS.items():
        print("  %-8s %-18s %s -> :%d  %s -mode client -addr %s:%d -group <G> -n <n> %s "
              "-gap <gap>ms -timeout %ds -stats %s/cli_stats.json -uplink-mbps <u> "
              "-expect-k <k>" % (a, v["label"], v["bin"], SLOTS[v["slot"]], BINS[v["bin"]],
                                  B.RX_IP, SLOTS[v["slot"]],
                                  " ".join(arm_flags(a, "%s/cache/<run>_<cond>_%s.json"
                                                     % (WORK, a))), TIMEOUT_S, WORK))
    totals = {}
    for run in ("run1", "run2", "smoke"):
        plan = build_plan(run)
        est = estimate(plan)
        print_plan(plan, est)
        print("  batches (%s):" % run)
        for bname, sec in est["batches"].items():
            print("    %-20s %6.2f h" % (bname, sec / 3600.0))
        print("  total %s: %.2f h" % (run, est["total_s"] / 3600.0))
        totals[run] = est["total_s"]
    hg = h_grid_estimate()
    print()
    print("H cells: drawn after the gate passes; per-cell estimate over the 60-cell grid "
          "min %.0f s, mean %.0f s, max %.0f s, so 4 cells take %.2f-%.2f h (run1 above uses "
          "the placeholder cell %s)" % (hg["min_s"], hg["mean_s"], hg["max_s"],
                                         4 * hg["min_s"] / 3600.0, 4 * hg["max_s"] / 3600.0,
                                         H_PLACEHOLDER["cell"]))
    print("verdict 4.5 plan for comparison (hours): %s" % json.dumps(VERDICT_HOURS))
    print("decision rules (pre-seal deviations, PROTOCOL 14.1): harness = %s; H1 = %s; H2 "
          "categories = %s" % (harness_eval([])["rule"], h1_eval([], None)["rule"],
                              ", ".join(H2_CATEGORIES)))
    print("wall clock: run1 %.2f h, run2 %.2f h, run1+run2 %.2f h, smoke %.1f min" % (
        totals["run1"] / 3600.0, totals["run2"] / 3600.0,
        (totals["run1"] + totals["run2"]) / 3600.0, totals["smoke"] / 60.0))
    print("  if the night overruns: run2 (S run 2) moves to the next night and the H1 claim "
          "waits for it; run1 is never cut short")
    print("  estimate assumptions: %s" % json.dumps(estimate(build_plan("run2"))["assumptions"],
                                                     ensure_ascii=False))
    print()
    print("held-out grid: %s (%d cells), schedule %s, segment %d, %d cycles; draw rule: %s"
          % (json.dumps(H_GRID), len(h_cells()), "<->".join("%g%%" % x for x in H_LOSSES),
             H_SEGMENT, H_CYCLES, h_draw("0" * 64)["rule"]))
    print()
    print("outputs: results %s ; decisions %s ; state %s, %s"
          % (os.path.relpath(paths("run1")["result"], ROOT),
             os.path.relpath(paths("run1")["decisions"], ROOT),
             os.path.relpath(journal_path("run1", "<cond>"), ROOT),
             os.path.relpath(paths("run1")["meta"], ROOT)))
    print()
    print("preflight (informational in a dry run):")
    binrep, problems = binary_report()
    for tag in ("g2", "g3b"):
        info = binrep[tag]
        print("  %s binary %s: %s" % (tag, info["path"], ("sha256 %s srcsha %s" % (
            info["sha256"], info.get("srcsha"))) if info["exists"] else "missing"))
    print("  stage-0 g3 binary (never used here): %s sha256 %s"
          % (STAGE0_G3_BIN, binrep["stage0_g3"]["sha256"]))
    print("  experiments/quicbed source fingerprint now: %s"
          % G.quicbed_sources()[1])
    seal = seal_check()
    print("  seal %s: %s" % (SEAL_REL, "ok" if seal["ok"] else "not ok (missing %s, changed "
                                                                "%s, unsealed %s)"
                             % (seal["missing"], seal["changed"], seal["unsealed_new"])))
    draw = draw_check(binrep["g3b"].get("srcsha"))
    print("  H draw %s: %s" % (HDRAW_REL, draw["cells"] if draw["ok"] else draw["problems"]))
    if draw["ok"]:
        print("  H predictions: %s" % (predictions_check(draw["cells"])["problems"] or "ok"))
    dev = dev_data_manifest(False)
    print("  development data files: %d listed, %d present, %.1f MB"
          % (len(dev), sum(1 for v in dev.values() if v["exists"]),
             sum(v.get("bytes", 0) for v in dev.values()) / 1e6))
    for p, v in dev.items():
        if not v["exists"]:
            print("    missing: %s" % p)
    if sys.platform.startswith("linux"):
        if not problems:
            _f, fproblems = flag_report(binrep)
            problems += fproblems
        print("  other measurements: %s" % (G.busy_processes() or "none"))
        print("  build processes: %s" % (G.load_processes() or "none"))
    else:
        print("  process and flag checks: skipped (not Linux)")
    print("  binary problems a live run would refuse on: %s" % (problems or "none"))
    print("  live runs also refuse on: another qamp or measurement script, go/compile "
          "processes, a failed mirror check, an arm whose flags the binary rejects (-n 0), "
          "and for run1/run2 a missing or broken seal, binaries or g3b srcsha that differ "
          "from the seal, a draw that does not reproduce, or a missing H prediction table")
    print()
    print("commands (WSL Ubuntu):")
    print("  build: wsl -d Ubuntu -- bash /mnt/c/dev/pq_afec_gen3/experiments/quicbed/"
          "build_g3b.sh")
    print("  after the gate (writes %s and %s): wsl -d Ubuntu -- bash -lc 'cd "
          "/mnt/c/dev/pq_afec_gen3 && %s && python3 experiments/p21_gencompare.py --draw-h "
          "--gate-evidence <gate result>'" % (HDRAW_REL, HPRED_REL, INSTALL_CMD))
    print("  check or rewrite a missing H prediction table (no binaries needed): "
          "python3 experiments/p21_gencompare.py --predict-h")
    print("  after the protocol slots are filled: wsl -d Ubuntu -- bash -lc "
          "'cd /mnt/c/dev/pq_afec_gen3 && %s && python3 experiments/p21_gencompare.py --seal'"
          % INSTALL_CMD)
    for m in ("smoke", "run1", "run2"):
        print("  wsl -d Ubuntu -- bash -lc 'cd /mnt/c/dev/pq_afec_gen3 && %s && unshare -Urnm "
              "python3 -u experiments/p21_gencompare.py --%s'" % (INSTALL_CMD, m))
    print("  python3 experiments/p21_gencompare.py --report-only run1")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="PAD-FEC stage-2 gen-2 vs gen-3 comparison "
                                             "(%s)" % VERDICT)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true",
                   help="print schedule, arm mapping and wall-clock estimate; no root, no network")
    g.add_argument("--smoke", action="store_true", help="tiny real run of every condition type")
    g.add_argument("--run1", action="store_true",
                   help="A/A, S run 1, D, H, cold and server equivalence")
    g.add_argument("--run2", action="store_true", help="S run 2")
    g.add_argument("--report-only", nargs="?", const="run1", choices=RUNS,
                   help="rebuild the result (and decisions) from the journals")
    g.add_argument("--draw-h", action="store_true",
                   help="record the held-out draw from the g3b source fingerprint (after the "
                        "gate) and write the H prediction table for it")
    g.add_argument("--predict-h", action="store_true",
                   help="write the H prediction table for the recorded draw if it is missing, "
                        "or check that the recorded table reproduces")
    g.add_argument("--seal", action="store_true", help="write g3/SEAL_stage2.json")
    ap.add_argument("--gate-evidence", help="gate result file for --draw-h")
    args = ap.parse_args(argv)
    if args.dry_run:
        return dry_run()
    if args.report_only:
        return report_only(args.report_only)
    if args.draw_h:
        return draw_mode(args.gate_evidence)
    if args.predict_h:
        return predict_mode()
    if args.seal:
        return seal_mode()
    return live("smoke" if args.smoke else "run1" if args.run1 else "run2")


if __name__ == "__main__":
    sys.exit(main())
