import hashlib
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from padfec import policy, quantum
from padfec3 import layout

P20 = Path("C:/dev/pq_afec/experiments/results/p20_residual.json")
PROTO_DIR = Path("C:/dev/codex_handoff/state/evo/mbc")
JUDGE_SCRIPT = Path("C:/dev/codex_handoff/state/evo/judge/stage0_pred.py")
VERDICT = Path("C:/dev/codex_handoff/state/evo/verdict_v3.md")
OUT = ROOT / "g3" / "stage0_predictions.json"

K = 2
W = 1280
DELTA = 0
GROUP = "X25519MLKEM768"
S0_BASE = policy.S0_BASE_MLKEM
C_PKT = policy.C_PKT_POLICY_DEFAULT
OFFSET_ARMS = (("m1", 1), ("m2", 2), ("m3", 3))

ARMS = {
    "v2-m1": {"binary": "g2", "flags": "-fec fec -m 1", "m": 1, "lead": layout.LEGACY_LEAD, "later": "g2"},
    "v2-m3": {"binary": "g2", "flags": "-fec fec -m 3", "m": 3, "lead": layout.LEGACY_LEAD, "later": "g2"},
    "v3tr-m3": {"binary": "g3", "flags": "-fec fec -m 3 -layout v3 -lead 1", "m": 3, "lead": 1, "later": "v3"},
    "credit-only-l2": {"binary": "g3", "flags": "-fec fec -m 2 -layout v3 -lead 2", "m": 2, "lead": 2, "later": "v3"},
    "credit-only-l3": {"binary": "g3", "flags": "-fec fec -m 3 -layout v3 -lead 3", "m": 3, "lead": 3, "later": "v3"},
    "m4L1": {"binary": "g3", "flags": "-fec fec -m 4 -layout v3 -lead 1", "m": 4, "lead": 1, "later": "v3"},
    "m4L2": {"binary": "g3", "flags": "-fec fec -m 4 -layout v3 -lead 2", "m": 4, "lead": 2, "later": "v3"},
    "m4L3": {"binary": "g3", "flags": "-fec fec -m 4 -layout v3 -lead 3", "m": 4, "lead": 3, "later": "v3"},
}

CONDITIONS = [
    {"id": "bigcert_loss2", "label": "bigcert 2%", "cert": 16000, "rtt_ms": 50.0, "uplink_mbps": 2.0, "loss_pct": 2.0,
     "arms": [("v2-m1", 400), ("v2-m3", 400), ("v3tr-m3", 400), ("credit-only-l3", 400), ("m4L3", 400)],
     "verdict_ms": {"v2-m1": 122.5, "v2-m3": 132.9, "v3tr-m3": 127.3, "credit-only-l3": 90.1, "m4L3": 86.0},
     "verdict_p1": {"credit-only-l3": 0.90, "m4L3": 0.94}},
    {"id": "bigcert_loss15", "label": "bigcert 15%", "cert": 16000, "rtt_ms": 50.0, "uplink_mbps": 2.0, "loss_pct": 15.0,
     "arms": [("v2-m1", 800), ("v2-m3", 800), ("v3tr-m3", 800), ("credit-only-l3", 800), ("m4L1", 800), ("m4L3", 800)],
     "verdict_ms": {"v2-m1": 134.4, "v2-m3": 137.9, "v3tr-m3": 132.4, "credit-only-l3": 155.5, "m4L1": 131.2, "m4L3": 114.4},
     "verdict_p1": {"m4L3": 0.58}},
    {"id": "rtt200_loss15", "label": "RTT200 15%", "cert": 9000, "rtt_ms": 200.0, "uplink_mbps": 2.0, "loss_pct": 15.0,
     "arms": [("v2-m3", 800), ("v3tr-m3", 800), ("m4L1", 800), ("m4L2", 800), ("credit-only-l2", 400)],
     "verdict_ms": {"v2-m3": 240.9, "v3tr-m3": 240.1, "m4L1": 237.2, "m4L2": 218.6, "credit-only-l2": 388.7},
     "verdict_p1": {}},
    {"id": "2mbps_loss15", "label": "2Mbps 15%", "cert": 9000, "rtt_ms": 50.0, "uplink_mbps": 2.0, "loss_pct": 15.0,
     "arms": [("v2-m3", 800), ("v3tr-m3", 800), ("m4L2", 800)],
     "verdict_ms": {"v2-m3": 83.0, "v3tr-m3": 82.2, "m4L2": 79.7},
     "verdict_p1": {}},
]

PROTO_CODE = r"""
import sys, json
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
from layout_model import evaluate
req = json.loads(sys.stdin.read())
out = []
for k, w, m, lead, p, rtt, up, nn, tr in req:
    r = evaluate(k, w, m, lead, p, rtt, up, nn, tr)
    out.append([r["J"], r["p1"], r["p2"], r["pf"]])
print(json.dumps(out))
"""


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_obs():
    d = json.load(open(P20, encoding="utf-8"))
    obs = {}
    for c in d["conds"]:
        if c["source"] != "p17":
            continue
        for a in c["arms"]:
            obs[(c["cert"], c["rtt_ms"], c["uplink_mbps"], c["loss_pct"], a["arm"])] = {
                "cond": c["cond"], "mean": a["mean"], "n": a["n"]}
    return obs


def arm_eval(arm, cond, need):
    spec = ARMS[arm]
    p = cond["loss_pct"] / 100.0
    lead = layout.resolve_lead(spec["m"], spec["lead"])
    r = layout.evaluate(K, W + DELTA, spec["m"], lead, p, cond["rtt_ms"], cond["uplink_mbps"],
                        need, later=spec["later"])
    return lead, r


def prototype_crosscheck(rows):
    if not (PROTO_DIR / "layout_model.py").exists():
        return {"status": "unavailable"}
    req = [[K, W, m, lead, c["loss_pct"] / 100.0, c["rtt_ms"], c["uplink_mbps"], need,
            "g2" if later == "g2" else "g3"] for m, later, c, need, lead, _r in rows]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    res = subprocess.run([sys.executable, "-B", "-c", PROTO_CODE, str(PROTO_DIR)],
                         input=json.dumps(req), capture_output=True, text=True, env=env)
    if res.returncode != 0:
        return {"status": "error", "stderr": res.stderr[-2000:]}
    got = json.loads(res.stdout)
    dj = dp1 = dp2 = dpf = 0.0
    for (_m, _l, _c, _n, _ld, r), (J, p1, p2, pf) in zip(rows, got):
        dj = max(dj, abs(r["J"] - J))
        dp1 = max(dp1, abs(r["p_one_rtt"] - p1))
        dp2 = max(dp2, abs(r["p_two_rtt"] - p2))
        dpf = max(dpf, abs(r["p_fail"] - pf))
    return {"status": "ok", "prototype": str(PROTO_DIR / "layout_model.py").replace("\\", "/"),
            "prototype_sha256": sha256(PROTO_DIR / "layout_model.py"), "points": len(rows),
            "max_abs_diff": {"J_ms": dj, "p_one_rtt": dp1, "p_two_rtt": dp2, "p_fail": dpf}}


def r6(x):
    return round(x, 6)


def build():
    obs = load_obs()
    conds_out = {}
    xrows = []
    worst_table = 0.0
    for cond in CONDITIONS:
        need = layout.n_need(cond["cert"], s0_base=S0_BASE, c_pkt=C_PKT)
        p = cond["loss_pct"] / 100.0
        terms = {}
        for name, m in OFFSET_ARMS:
            key = (cond["cert"], cond["rtt_ms"], cond["uplink_mbps"], cond["loss_pct"], name)
            ob = obs[key]
            lead = layout.legacy_lead(m)
            r = layout.evaluate(K, W, m, lead, p, cond["rtt_ms"], cond["uplink_mbps"], need, later="g2")
            terms[name] = {"p17_cond": ob["cond"], "obs_mean_ms": ob["mean"], "obs_n": ob["n"],
                           "model": {"m": m, "lead": lead, "later": "g2"},
                           "J_ms": r["J"], "residual_ms": ob["mean"] - r["J"]}
            xrows.append((m, "g2", cond, need, lead, r))
        offset = math.fsum(t["residual_ms"] for t in terms.values()) / len(terms)
        arms_out = {}
        for arm, n in cond["arms"]:
            lead, r = arm_eval(arm, cond, need)
            spec = ARMS[arm]
            pred = r["J"] + offset
            cut = layout.one_rtt_cutoff_ms(cond["rtt_ms"], K, spec["m"], lead, W + DELTA, cond["uplink_mbps"])
            vt = cond["verdict_ms"].get(arm)
            if vt is not None:
                worst_table = max(worst_table, abs(round(pred, 1) - vt))
            arms_out[arm] = {
                "binary": spec["binary"], "client_flags": spec["flags"], "n_planned": n,
                "model": {"k": K, "w": W + DELTA, "m": spec["m"], "lead": lead, "trail": spec["m"] - lead,
                          "later": spec["later"], "response_term_ms": r["response_term_ms"]},
                "J_ms": r["J"], "offset_ms": offset,
                "pred_mean_hct_ms": pred, "pred_mean_hct_ms_1dp": round(pred, 1),
                "pred_one_rtt_frac": r["p_one_rtt"], "pred_two_rtt_frac": r["p_two_rtt"],
                "pred_fail_frac": r["p_fail"],
                "pred_fail_split": {"pto": r["p_fail_pto"], "pto_sampled": r["p_fail_pto_sampled"],
                                    "ack": r["p_fail_ack"]},
                "event_prob_e": r["e"], "round_mult_M": r["round_mult"],
                "client_bytes": r["client_bytes"], "pre_decision_bytes": r["pre_decision_bytes"],
                "one_rtt_cutoff_ms": cut,
                "verdict_table_ms": vt, "verdict_table_p1": cond["verdict_p1"].get(arm),
            }
            xrows.append((spec["m"], spec["later"], cond, need, lead, r))
        conds_out[cond["id"]] = {
            "label": cond["label"], "group": GROUP, "cert": cond["cert"], "rtt_ms": cond["rtt_ms"],
            "uplink_mbps": cond["uplink_mbps"], "loss_pct": cond["loss_pct"], "p": p, "burst": 1.0,
            "k": K, "W": W, "delta": DELTA, "n_need": need,
            "offset_ms": offset, "offset_terms": terms, "arms": arms_out,
        }
    if worst_table > 0.05 + 1e-9:
        raise SystemExit("prediction table disagrees with verdict 4.2 by %.3f ms" % worst_table)

    def pm(cid, arm):
        return conds_out[cid]["arms"][arm]["pred_mean_hct_ms"]

    def p1(cid, arm):
        return conds_out[cid]["arms"][arm]["pred_one_rtt_frac"]

    m1_frac = p1("bigcert_loss2", "m4L3")
    m1_diff = pm("bigcert_loss2", "m4L3") - pm("bigcert_loss2", "v2-m1")
    m2_diff = pm("bigcert_loss2", "v2-m3") - pm("bigcert_loss2", "v3tr-m3")
    m3_diff = pm("rtt200_loss15", "v2-m3") - pm("rtt200_loss15", "m4L2")
    m4_2 = pm("bigcert_loss2", "m4L3") - pm("bigcert_loss2", "credit-only-l3")
    m4_15 = pm("bigcert_loss15", "m4L3") - pm("bigcert_loss15", "credit-only-l3")
    rules = {
        "M1": {
            "name": "multiple leading credit",
            "condition": "bigcert_loss2",
            "criteria": [
                {"quantity": "one_rtt_frac(m4L3)", "op": ">=", "threshold": 0.85,
                 "predicted": m1_frac, "predicted_pass": m1_frac >= 0.85},
                {"quantity": "mean_hct(m4L3) - mean_hct(v2-m1) [ms]", "op": "<=", "threshold": -18.0,
                 "predicted": m1_diff, "predicted_pass": m1_diff <= -18.0},
                {"quantity": "server stats: all lead datagrams of m4L3 handed to the stack as credit",
                 "op": "all", "threshold": None,
                 "predicted": "not a model quantity; expected true under the ver-3 server rule index < lead",
                 "predicted_pass": None},
            ],
            "on_fail": "withdraw lead>=2; v3 shrinks to legacy layout + F2 + learning; withdraw the large-gain claim",
        },
        "M2": {
            "name": "F2 (second-flight leading parity and buffering wait)",
            "condition": "bigcert_loss2",
            "quantity": "mean_hct(v2-m3) - mean_hct(v3tr-m3) [ms]",
            "interval": [2.8, 11.2], "predicted": m2_diff,
            "predicted_pass": 2.8 <= m2_diff <= 11.2,
            "on_fail": "withdraw the F2 claim and switch the tau(W) term off",
        },
        "M3": {
            "name": "credit duplication",
            "condition": "rtt200_loss15",
            "quantity": "mean_hct(v2-m3) - mean_hct(m4L2) [ms]",
            "interval": [11.0, 44.0], "predicted": m3_diff,
            "predicted_pass": 11.0 <= m3_diff <= 44.0,
            "on_fail": "move RTT200 from S to D",
        },
        "M4": {
            "name": "attribution (reported, not a decision rule)",
            "quantity": "mean_hct(m4L3) - mean_hct(credit-only-l3) [ms]",
            "predicted": {"bigcert_loss2": m4_2, "bigcert_loss15": m4_15},
            "fec_share_ms": {"bigcert_loss2": -m4_2, "bigcert_loss15": -m4_15},
        },
    }
    cross = prototype_crosscheck(xrows)
    return {
        "schema": "padfec3.stage0_predictions.v1",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "provisional predictions sealed before stage-0 measurement (verdict_v3.md section 4.2)",
        "generator": "g3/stage0_predict.py",
        "model": {
            "module": "padfec3/layout.py", "function": "evaluate (J3, verdict_v3.md section 2.3)",
            "sha256": sha256(ROOT / "padfec3" / "layout.py"),
            "dependencies_sha256": {
                "padfec/policy.py": sha256(ROOT / "padfec" / "policy.py"),
                "padfec/quantum.py": sha256(ROOT / "padfec" / "quantum.py"),
                "afec/channel.py": sha256(ROOT / "afec" / "channel.py"),
            },
            "later_modes": {
                "g2": "2-RTT branch pays tau(W) + [m>=2] tau(parity(W,1)) + [m>=1] 0.3 ms (gen-2 second flight)",
                "v3": "2-RTT branch pays tau(W) only (v3 later-flight rule)",
            },
        },
        "inputs": {
            "k": K, "W": W, "delta": DELTA, "group": GROUP,
            "s0_base": S0_BASE, "c_pkt": C_PKT, "P_server": quantum.P_SERVER,
            "parity_bytes": "W + %d + %d*k" % (policy.PARITY_OVERHEAD_BASE, policy.PARITY_OVERHEAD_PER_K),
            "loss_model": "independent per datagram (burst 1), client-to-server only",
            "uplink_rate": "netem rate on the uplink only; lost datagrams do not consume link time",
            "T_pto_no_ack_ms": layout.T_PTO_MS, "T_ack_slope": layout.T_ACK_SLOPE,
            "T_ack_base_ms": layout.T_ACK_BASE_MS, "pto_sampled_rtt_mult": layout.PTO_SAMPLED_MULT,
            "g2_parity_delay_ms": layout.G2_PARITY_DELAY_MS,
            "race_delay_ms": list(policy.RACE_DELAY_MS), "race_win_q": list(policy.RACE_WIN_Q),
            "round_mult": "M = 1/(1-P_fail)",
            "offset_rule": "per condition, mean over p17 arms m1,m2,m3 of (observed mean - J with legacy layout and later=g2); same as judge/stage0_pred.py",
            "p20_residual": {"path": str(P20).replace("\\", "/"), "sha256": sha256(P20)},
            "judge_script": {"path": str(JUDGE_SCRIPT).replace("\\", "/"),
                             "sha256": sha256(JUDGE_SCRIPT) if JUDGE_SCRIPT.exists() else None},
            "verdict": {"path": str(VERDICT).replace("\\", "/"),
                        "sha256": sha256(VERDICT) if VERDICT.exists() else None},
        },
        "one_rtt_definition": "HCT < 1.5*RTT + tau(pre_decision_bytes), pre_decision_bytes = lead*parity(W,k) + k*W, tau(b) = 8b/(1000*u) ms",
        "notes": [
            "pred_mean_hct_ms = J + offset_ms. Offsets cancel in every between-arm difference used by M1-M4.",
            "Predictions do not include client timeouts; the primary metric imputes failed attempts with the client timeout (verdict 4.1), which the model does not predict.",
            "pred_one_rtt_frac is the model mass of successful first flights whose decision-time credit reaches n_need; failure branches are never 1-RTT.",
            "verdict_table_ms are the rounded provisional values printed in verdict_v3.md 4.2; max |round(pred,1) - table| = %.3f ms." % worst_table,
        ],
        "conditions": conds_out,
        "decision_rules": rules,
        "crosscheck_vs_prototype": cross,
    }


def main():
    data = build()
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(OUT)
    for cid, c in data["conditions"].items():
        print("%s n_need %d offset %.3f" % (cid, c["n_need"], c["offset_ms"]))
        for arm, a in c["arms"].items():
            print("  %-15s pred %8.3f  P1 %.3f  Pfail %.4f  n %d  cut %.2f" % (
                arm, a["pred_mean_hct_ms"], a["pred_one_rtt_frac"], a["pred_fail_frac"],
                a["n_planned"], a["one_rtt_cutoff_ms"]))
    for k, v in data["decision_rules"].items():
        print(k, json.dumps(v.get("predicted", [c.get("predicted") for c in v.get("criteria", [])])))
    print("crosscheck", json.dumps(data["crosscheck_vs_prototype"]))


if __name__ == "__main__":
    main()
