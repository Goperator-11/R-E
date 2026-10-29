import collections
import hashlib
import json
import math
import os
import sys
import time
from datetime import datetime, timezone

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN3 = "C:/dev/pq_afec_gen3"
STATE = GEN3 + "/experiments/state"
OUT = os.path.join(ROOT, "g3", "dev_v31_redecide.json")
W = 1280
CELLS = {
    "H_h_c6000_r80_u10": {"cert": 6000, "rtt": 80.0, "rate": 10.0},
    "S_bigcert": {"cert": 16000, "rtt": 50.0, "rate": 2.0},
}
SHARED = ("padfec/policy.py", "padfec/quantum.py", "padfec/table.py")
V3_FILES = ("padfec3/layout.py", "padfec3/learn3.py", "padfec3/decide3.py")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def load_modules():
    for rel in SHARED:
        a = sha256_file(os.path.join(ROOT, rel))
        b = sha256_file(os.path.join(GEN3, rel))
        if a != b:
            raise SystemExit("shared module differs between gen3 and gen31: %s" % rel)
    sys.path.insert(0, ROOT)
    from padfec import policy, quantum
    sys.path.insert(0, GEN3)
    import padfec3.layout as v3_layout
    import padfec3.learn3 as v3_learn3
    import padfec3.decide3 as v3_decide3
    for m in (v3_layout, v3_learn3, v3_decide3):
        if not os.path.abspath(m.__file__).replace("\\", "/").startswith(GEN3):
            raise SystemExit("v3 module not from gen3: %s" % m.__file__)
    for name in [n for n in sys.modules if n == "padfec3" or n.startswith("padfec3.")]:
        del sys.modules[name]
    sys.path.remove(GEN3)
    import padfec3.layout as layout
    import padfec3.learn3 as learn3
    import padfec3.decide3 as decide3
    for m in (layout, learn3, decide3):
        if not os.path.abspath(m.__file__).replace("\\", "/").startswith(ROOT.replace("\\", "/")):
            raise SystemExit("v3.1 module not from gen31: %s" % m.__file__)
    if v3_learn3.layout is layout or learn3.POLICY_VERSION != "v3.1":
        raise SystemExit("module isolation failed")
    return policy, quantum, (v3_layout, v3_learn3, v3_decide3), (layout, learn3, decide3)


def load_blocks(cell):
    path = "%s/p21_run1_%s_units.jsonl" % (STATE, cell)
    out = []
    with open(path, encoding="utf-8") as f:
        for ln in f:
            out.append(json.loads(ln)["val"])
    out.sort(key=lambda v: (v["started_at"], v["block"]))
    return path, out


def arg_after(argv, flag, default=None):
    if flag in argv:
        return argv[argv.index(flag) + 1]
    return default


def tau_ms(nbytes, rate):
    return 8.0 * nbytes / (1000.0 * rate) if rate and rate > 0 else 0.0


def row_lead(row):
    v = row.get("first_flight_lead_dgrams")
    if type(v) is int:
        return v
    npar = row.get("first_flight_parity_dgrams")
    m = row.get("m_used")
    if type(npar) is int and type(m) is int:
        return min(1 if m >= 2 else 0, npar)
    return 0


def one_rtt(row, prof):
    if not row.get("ok"):
        return False
    ob = row.get("first_flight_bytes") or 0
    npar = row.get("first_flight_parity_dgrams") or 0
    pb = row.get("first_flight_parity_bytes") or 0
    size = (pb / float(npar)) if npar else 0.0
    pre = ob + row_lead(row) * size
    return row["ms"] < 1.5 * prof["rtt"] + tau_ms(pre, prof["rate"])


def akey(a):
    return "%d,%d,%d" % tuple(a)


class Replay:
    def __init__(self, learn3, decide3, u, c_pkt):
        self.learn3 = learn3
        self.decide3 = decide3
        self.st = learn3.new_state()
        self.min_rtt = 0.0
        self.rtt_obs = 0
        self.min_hct = 0.0
        self.u = float(u)
        self.c_pkt = c_pkt

    def policy_rtt(self):
        if self.rtt_obs > 0 and self.min_rtt > 0:
            return self.min_rtt
        if self.min_hct > 0:
            return self.min_hct
        return 0.0

    def observe(self, row):
        prt = row.get("path_rtt_ms")
        if row.get("path_rtt_valid") and prt and prt > 0 and math.isfinite(prt):
            if self.min_rtt <= 0 or prt < self.min_rtt:
                self.min_rtt = prt
            self.rtt_obs += 1
        hct = row["ms"]
        ok = bool(row["ok"])
        if ok and hct > 0 and (self.min_hct <= 0 or hct < self.min_hct):
            self.min_hct = hct
        sb = row.get("server_bytes")
        self.learn3.observe3(self.st, tuple(row["action"]), hct, ok,
                             row.get("first_flight_datagrams"),
                             float(sb) if sb is not None else None,
                             self.policy_rtt(), W=W, u_mbps=self.u,
                             c_pkt=self.c_pkt)


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else None


def summarize(recs):
    out = {"n": len(recs)}
    v3c = collections.Counter(akey(r["v3_action"]) for r in recs)
    v31c = collections.Counter(akey(r["v31_action"]) for r in recs)
    tr = collections.Counter("%s -> %s" % (akey(r["v3_action"]), akey(r["v31_action"]))
                             for r in recs)
    out["v3_actions"] = dict(sorted(v3c.items()))
    out["v31_actions"] = dict(sorted(v31c.items()))
    out["transitions"] = dict(sorted(tr.items()))
    out["changed"] = sum(1 for r in recs if r["v3_action"] != r["v31_action"])
    out["changed_frac"] = out["changed"] / len(recs) if recs else None
    per = {}
    for a in sorted(v3c):
        rs = [r for r in recs if akey(r["v3_action"]) == a]
        per[a] = {"n": len(rs),
                  "measured_ms_mean": mean(r["ms"] for r in rs),
                  "measured_one_rtt": mean(1.0 if r["one_rtt"] else 0.0 for r in rs),
                  "measured_ok": mean(1.0 if r["ok"] else 0.0 for r in rs),
                  "pred_v3_ms_mean": mean(r["v3_ej"] for r in rs),
                  "pred_v31_same_action_ms_mean": mean(r["v31_ej_of_v3_action"] for r in rs),
                  "pred_v31_one_rtt_same_action_mean": mean(r["v31_p1_of_v3_action"] for r in rs),
                  "v31_nominal2_frac": mean(1.0 if r["v31_n2_of_v3_action"] else 0.0
                                            for r in rs)}
    out["by_v3_action"] = per
    per = {}
    for a in sorted(v31c):
        rs = [r for r in recs if akey(r["v31_action"]) == a]
        per[a] = {"n": len(rs), "pred_v31_ms_mean": mean(r["v31_ej"] for r in rs),
                  "pred_v31_one_rtt_mean": mean(r["v31_p1"] for r in rs)}
    out["by_v31_action"] = per
    return out


def guard_passive(learn3, recs, rtt_key="rtt"):
    st = learn3.new_state()
    alarm_rows = 0
    raised = []
    pen = []
    for r in recs:
        learn3.guard_refresh(st)
        st.n_dec += 1
        key = akey(r["v3_action"])
        if key in st.g_alarm:
            alarm_rows += 1
            pen.append(learn3.guard_penalty(st, key, learn3.guard_common(st)))
        if r["ok"]:
            res = r["ms"] - r["v31_ej_of_v3_action"]
            for k in learn3.guard_observe(st, key, res, r[rtt_key]):
                raised.append({"row": r["seq"], "action": k, "loss": r["loss"]})
    return {"rows": len(recs), "rows_on_alarmed_action": alarm_rows,
            "alarms_raised": len(raised),
            "alarms_by_action": dict(collections.Counter(x["action"] for x in raised)),
            "alarms_by_loss": {str(k): v for k, v in sorted(collections.Counter(
                x["loss"] for x in raised).items())},
            "penalty_ms_mean_when_alarmed": mean(pen),
            "first_alarms": raised[:10]}


def analyze(cell, mods, policy, quantum):
    (v3_layout, v3_learn3, v3_decide3), (layout, learn3, decide3) = mods
    prof = CELLS[cell]
    c_pkt = policy.C_PKT_POLICY_DEFAULT
    path, blocks = load_blocks(cell)
    rep = None
    recs = []
    other = collections.Counter()
    for v in blocks:
        loss = float(v["loss"])
        seg = [s for s in v["segments"] if s["arm"] == "g3auto"][0]
        u = float(arg_after(seg["argv"], "-uplink-mbps", "0"))
        if u != prof["rate"]:
            raise SystemExit("%s: uplink %r != %r" % (cell, u, prof["rate"]))
        if rep is None:
            rep = Replay(v3_learn3, v3_decide3, u, c_pkt)
        for row in seg["rows"]:
            rtt = rep.policy_rtt()
            post = v3_learn3.combined(rep.st)
            d = v3_decide3.decide3(rep.st, W, u, rtt, c_pkt)
            if list(d["action"]) != list(row["action"]) or d["why"] != row["why3"]:
                raise SystemExit("v3 replay diverged at %s block %s row %s"
                                 % (cell, v["block"], row["i"]))
            if row["why3"] == "ej":
                if d["ej"] != row["j3_ms"]:
                    raise SystemExit("v3 replay j3 differs at %s row %s" % (cell, row["i"]))
                r31 = decide3.decide_core(post, d["k"], W, d["S"], u, rtt, c_pkt,
                                          keep_cands=True)
                if r31["n_need"] != d["n_need"] or r31["n_cands"] != d["n_cands"]:
                    raise SystemExit("candidate context differs at %s row %s" % (cell, row["i"]))
                same = [c for c in r31["cands"] if c["action"] == tuple(row["action"])][0]
                pts = [(post[g], g) for g in range(len(post)) if post[g] != 0.0]

                def p1_of(c):
                    s = 0.0
                    for q, g in pts:
                        e = learn3.model_point(d["k"], c["W_eff"], u, rtt, d["n_need"],
                                               c["lead"], c["m"], g)[1]
                        s += q * (1.0 - e)
                    return s
                best = [c for c in r31["cands"] if c["action"] == r31["action"]][0]
                recs.append({"seq": len(recs), "block": v["block"], "loss": loss,
                             "i": row["i"], "ms": row["ms"], "ok": bool(row["ok"]),
                             "one_rtt": one_rtt(row, prof), "rtt": rtt,
                             "v3_action": tuple(row["action"]), "v3_ej": row["j3_ms"],
                             "v31_action": r31["action"], "v31_ej": r31["ej"],
                             "v31_p1": p1_of(best), "v31_n2": r31["n2"],
                             "v31_ej_of_v3_action": same["ej"],
                             "v31_p1_of_v3_action": p1_of(same),
                             "v31_n2_of_v3_action": same["n2"],
                             "v31_reeval_cond": r31["reeval_cond"],
                             "k_hat": d["k"], "s_hat": d["S"], "n_need": d["n_need"],
                             "p_mean": row["p_mean"]})
            else:
                other[row["why3"]] += 1
            rep.observe(row)
    by_loss = {}
    for loss in sorted(set(r["loss"] for r in recs)):
        by_loss[str(loss)] = summarize([r for r in recs if r["loss"] == loss])
    return {"journal": path.replace("\\", "/"), "journal_sha256": sha256_file(path),
            "cert": prof["cert"], "rtt_true_ms": prof["rtt"], "uplink_mbps": prof["rate"],
            "blocks": len(blocks), "replay_bit_exact": True,
            "decisions_ej": len(recs), "decisions_other": dict(other),
            "context": {"k_hat": sorted(set(r["k_hat"] for r in recs)),
                        "n_need": sorted(set(r["n_need"] for r in recs)),
                        "s_hat_range": [min(r["s_hat"] for r in recs),
                                        max(r["s_hat"] for r in recs)],
                        "a_pre": layout.preflight_bytes(recs[0]["k_hat"], prof["rate"])},
            "all": summarize(recs), "by_loss": by_loss,
            "v31_choice_nominal2_frac": mean(1.0 if r["v31_n2"] else 0.0 for r in recs),
            "v31_reeval_condition_frac": mean(1.0 if r["v31_reeval_cond"] else 0.0
                                              for r in recs),
            "guard_passive": guard_passive(learn3, recs)}


def main():
    t0 = time.time()
    policy, quantum, v3, v31 = load_modules()
    doc = {"schema": "padfec3.dev_v31_redecide/1",
           "label": "development, in-sample (not confirmatory)",
           "status": "development (not confirmatory)",
           "confirmatory": False,
           "generated_at": datetime.now(timezone.utc).isoformat(),
           "question": ("which action the v3.1 completion rule alone would choose, given the "
                        "exact context, candidate set and full posterior that each recorded "
                        "v3 decision used (stage-2 run1 journals, re-analyzed after the fact)"),
           "method": ("replay the sealed v3 learner (C:/dev/pq_afec_gen3 padfec3, imported "
                      "read-only) in journal order, assert that every decision and j3_ms "
                      "match the journal bit for bit, then call gen31 decide3.decide_core "
                      "on the same posterior, k_hat, s_hat, policy RTT and uplink with no "
                      "guard penalty and no re-evaluation. Only the completion rule differs "
                      "from v3. v3.1 learning (nominal-2 skip, guard, re-evaluation) is not "
                      "applied to the posterior, so this is not a v3.1 trajectory."),
           "one_rtt_rule": "ms < 1.5*rtt_true + tau(pre-decision bytes), as the stage-2 runner",
           "guard_passive_note": ("guard windows fed with the residual ms - EJ_v3.1(v3 action) "
                                  "along the recorded v3 actions; actions are not changed by "
                                  "alarms, so alarm counts describe the residual stream only"),
           "code": {"gen31": {p: sha256_file(os.path.join(ROOT, p))
                              for p in V3_FILES + SHARED + ("g3/dev_v31_redecide.py",)},
                    "gen3_v3": {p: sha256_file(os.path.join(GEN3, p)) for p in V3_FILES}},
           "constants": {"preflight_ack_bytes": v31[0].PREFLIGHT_ACK_BYTES,
                         "c_pkt": policy.C_PKT_POLICY_DEFAULT, "W": W},
           "cells": {}}
    for cell in CELLS:
        doc["cells"][cell] = analyze(cell, (v3, v31), policy, quantum)
    doc["elapsed_s"] = time.time() - t0
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, OUT)
    for cell, c in doc["cells"].items():
        print(cell, "decisions", c["decisions_ej"], "changed", c["all"]["changed"],
              "(%.4f)" % c["all"]["changed_frac"])
        print("  transitions", c["all"]["transitions"])
        for loss, s in c["by_loss"].items():
            print("  loss", loss, "n", s["n"], "v31", s["v31_actions"])
        print("  guard_passive", {k: v for k, v in c["guard_passive"].items()
                                  if k != "first_alarms"})
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
