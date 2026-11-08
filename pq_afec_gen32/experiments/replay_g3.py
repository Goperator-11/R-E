import argparse
import collections
import hashlib
import json
import math
import os
import random
import statistics
import sys
import time

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from padfec import policy as POL
from padfec3 import decide3, learn3

P17_DEFAULT = "C:/dev/pq_afec/experiments/state/p17_units.jsonl"
PROTO_DEFAULT = "C:/dev/codex_handoff/state/evo"
OUT_DEFAULT = os.path.join(ROOT, "g3", "replay_g3_dev.json")
FP = "79c049550139"
C_ML = 1447
W = 1280
C_PKT = POL.C_PKT_POLICY_DEFAULT
ARMS = (0, 1, 2, 3)
LEGACY = {0: (0, 0, 0), 1: (0, 0, 1), 2: (0, 1, 1), 3: (0, 1, 2)}
ACTION_ARM = {v: k for k, v in LEGACY.items()}
FAIL_MS = 10000.0
SEEDS = (0, 1, 2, 3, 4, 5)
PFINE = [i * 0.0025 for i in range(0, 121)]
LABEL = ("development data (in-sample): offline replay of the p17 journal "
         "(gen-2 generation fp %s); the v3 classifier baseline (median) and "
         "epsilon were chosen after seeing p17, so nothing here is "
         "confirmatory" % FP)
REPLAY_NOTE = ("Development counterfactual only: journal outcomes came from the "
               "recorded policy. New decisions were not executed, and these "
               "results are not a measured or closed-loop trajectory of "
               "the current policy.")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path):
    conds = {}
    order = []
    sel = hashlib.sha256()
    with open(path, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d.get("fp") != FP:
                continue
            sel.update(line.encode("utf-8"))
            v = d["val"]
            name = v["cond"]
            if name not in conds:
                order.append(name)
            rows = {}
            for s in v["segments"]:
                rows[(s["cycle"], s["loss"], s["arm"])] = s["trial_records"]
            conds[name] = {"val": v, "rows": rows, "run_id": d.get("run_id"),
                           "recorded_at": d.get("recorded_at")}
    return order, conds, sel.hexdigest()


def interp(arr, p):
    p = min(max(p, 0.0), 0.30)
    x = p / 0.0025
    i = int(x)
    if i >= len(arr) - 1:
        return arr[-1]
    t = x - i
    return arr[i] * (1 - t) + arr[i + 1] * t


def pick_tie(costs):
    costs = sorted(costs)
    jmin = costs[0][0]
    tied = [c for c in costs if c[0] <= jmin + 0.01]
    tied.sort(key=lambda c: c[1])
    return tied[0][1]


class G2Tables:
    def __init__(self, cert, up):
        self.cert = cert
        self.up = up
        self.tab = {}

    def fine(self, rtt):
        key = round(rtt, 1)
        if key in self.tab:
            return self.tab[key]
        fine = {a: [] for a in ARMS}
        for p in PFINE:
            pp = min(p, 0.30)
            d = POL.decide_v2(C=C_ML, cert_bytes=self.cert, rtt_ms=rtt, p=pp,
                              burst=1.0, s0_base=POL.S0_BASE_MLKEM,
                              c_pkt=POL.C_PKT_POLICY_DEFAULT, W=W,
                              max_steps=2, m_max=POL.M_MAX_DEFAULT,
                              uplink_mbps=self.up)
            o = {}
            for c in d["candidates"]:
                if c["W_eff"] == W and c["mode"] in ("none", "parity"):
                    o[c["m"]] = c
            for a in ARMS:
                fine[a].append(o[a]["j_ms"])
        self.tab[key] = fine
        return fine


class RttTrack:
    def __init__(self):
        self.min_rtt = 0.0
        self.rtt_obs = 0
        self.min_hct = 0.0

    def observe(self, row):
        if row.get("path_rtt_valid") and row["path_rtt_ms"] > 0:
            if self.min_rtt <= 0 or row["path_rtt_ms"] < self.min_rtt:
                self.min_rtt = row["path_rtt_ms"]
            self.rtt_obs += 1
        if row["ok"]:
            h = row["ms"]
            if h > 0 and (self.min_hct <= 0 or h < self.min_hct):
                self.min_hct = h

    def rtt(self):
        if self.rtt_obs > 0 and self.min_rtt > 0:
            return self.min_rtt
        return self.min_hct


class Gen2Clone:
    def __init__(self, tables):
        self.tables = tables
        self.st = None
        self.unb = True

    def rtt(self):
        st = self.st
        if st is None:
            return 0.0
        if st["RTTObs"] > 0 and st["MinRTT"] > 0:
            return st["MinRTT"]
        return st["MinHCT"]

    def decide(self):
        st = self.st
        rtt = self.rtt()
        if (st is None or st["Conns"] < 1 or rtt <= 0 or st["K"] < 1
                or st["ObsCount"] < 1):
            self.unb = True
            return 0
        pconn = (st["LossCount"] + 0.5) / (st["ObsCount"] + 1.0)
        pconn = min(max(pconn, 0), 0.99)
        p = 1 - (1 - pconn) ** (1.0 / st["K"])
        fine = self.tables.fine(rtt)
        costs = [(interp(fine[a], p), a) for a in ARMS]
        best = pick_tie(costs)
        jb = dict((a, j) for j, a in costs)
        probe_cost = jb[0] - jb[best]
        every = 20
        if probe_cost > 0:
            every = max(every, int(math.ceil(probe_cost / (0.01 * rtt))))
        st["SinceProbe"] += 1
        if st["SinceProbe"] >= every:
            st["SinceProbe"] = 0
            self.unb = True
            return 0
        self.unb = best == 0
        return best

    def observe(self, arm, row):
        unb = self.unb
        if self.st is None:
            self.st = dict(K=0, S=0.0, MinHCT=0.0, MinRTT=0.0, RTTObs=0,
                           LossCount=0.0, ObsCount=0.0, ProbeMinHCT=0.0,
                           Conns=0, SinceProbe=0)
        st = self.st
        if row.get("path_rtt_valid") and row["path_rtt_ms"] > 0:
            if st["MinRTT"] <= 0 or row["path_rtt_ms"] < st["MinRTT"]:
                st["MinRTT"] = row["path_rtt_ms"]
            st["RTTObs"] += 1
        if not row["ok"]:
            return
        k = row["first_flight_datagrams"]
        h = row["ms"]
        if k > 0:
            st["K"] = k
        sb = row["server_bytes"]
        st["S"] = sb if (st["Conns"] <= 0 or st["S"] <= 0) else st["S"] * 0.75 + sb * 0.25
        if h > 0 and (st["MinHCT"] <= 0 or h < st["MinHCT"]):
            st["MinHCT"] = h
        if unb:
            classified = st["ProbeMinHCT"] > 0 and h > 0
            le = False
            if classified:
                le = h > st["ProbeMinHCT"] * 1.3 + 2.0
            if h > 0 and (st["ProbeMinHCT"] <= 0 or h < st["ProbeMinHCT"]):
                st["ProbeMinHCT"] = h
            if classified:
                st["LossCount"] *= 0.99
                st["ObsCount"] *= 0.99
                st["ObsCount"] += 1
                if le:
                    st["LossCount"] += 1
        st["Conns"] += 1

    def snapshot(self):
        return None

    def diag(self):
        return {}


class V3Learn:
    def __init__(self, up, later):
        self.up = up
        self.later = later
        self.st = learn3.new_state()
        self.rt = RttTrack()
        self.whys = collections.Counter()
        self.n_need = collections.Counter()
        self.khat = collections.Counter()
        self.last_decision = None
        self.last_row = None
        self.guard = collections.Counter()
        self.residuals = []

    def decide(self):
        res = decide3.decide3(self.st, W, self.up, self.rt.rtt(), C_PKT,
                              actions=[LEGACY[a] for a in ARMS],
                              later=self.later)
        self.whys[res["why"]] += 1
        self.last_decision = res
        if res["n_need"] is not None:
            self.n_need[res["n_need"]] += 1
            self.khat[res["k"]] += 1
        return ACTION_ARM[tuple(res["action"])]

    def observe(self, arm, row):
        if self.last_decision is None:
            raise RuntimeError("observe needs a preceding decision")
        res = self.last_decision
        if tuple(res["action"]) != LEGACY[arm]:
            raise ValueError("observed arm differs from the preceding decision")
        self.rt.observe(row)
        info = learn3.observe3(
            self.st, LEGACY[arm], row["ms"] if row["ok"] else None,
            row["ok"], row["first_flight_datagrams"], row["server_bytes"],
            self.rt.rtt(), W=W, u_mbps=self.up, c_pkt=C_PKT,
            later=self.later, j_pred=res.get("j3_pred_pre_ms", res.get("ej")))
        self.last_row = {key: res[key] for key in
                         ("policy_version", "j3_pred_pre_ms", "guard_alarm",
                          "guard_common_ms", "guard_alarmed_actions", "reeval")}
        self.last_row["guard_resid_ms"] = info["resid"]
        self.guard["rows"] += 1
        self.guard["alarm_rows"] += int(res["guard_alarm"])
        self.guard["reeval_rows"] += int(res["reeval"])
        if info["resid"] is not None:
            self.residuals.append(info["resid"])
        self.last_decision = None

    def snapshot(self):
        return learn3.post_summary(learn3.combined(self.st))["p_mean"]

    def diag(self):
        return {"policy_version": learn3.POLICY_VERSION,
                "guard": dict(self.guard), "last_row": self.last_row,
                "residuals": {"n": len(self.residuals), "mean_ms":
                              statistics.mean(self.residuals)
                              if self.residuals else None},
                "whys": dict(self.whys),
                "n_need": {str(k): v for k, v in sorted(self.n_need.items())},
                "k_hat": {str(k): v for k, v in sorted(self.khat.items())},
                "stats": dict(self.st.stats)}


def run(cond, pol, seed, resample):
    rng = random.Random(seed)
    v = cond["val"]
    rows = cond["rows"]
    res = []
    for c in range(v["protocol"]["cycles"]):
        for loss, n in v["protocol"]["schedule"]:
            seg = []
            for t in range(n):
                arm = pol.decide()
                rl = rows[(c, loss, "m%d" % arm)]
                r = rl[rng.randrange(len(rl))] if resample else rl[t]
                pol.observe(arm, r)
                seg.append((arm, r["ms"] if r["ok"] else FAIL_MS))
            res.append((c, loss, seg, pol.snapshot()))
    return res


def summarize(res, orcarm):
    by = collections.defaultdict(list)
    arms = collections.defaultdict(collections.Counter)
    hits = collections.defaultdict(list)
    pm = collections.defaultdict(list)
    for c, loss, seg, snap in res:
        n_hit = 0
        for a, ms in seg:
            by[loss].append(ms)
            arms[loss][a] += 1
            if a == orcarm[loss]:
                n_hit += 1
        hits[loss].append(n_hit / len(seg))
        if snap is not None:
            pm[loss].append(snap)
    allms = [x for l in by for x in by[l]]
    out = {"mean": sum(allms) / len(allms), "n": len(allms)}
    for l in sorted(by):
        tag = "%g" % l
        out["mean_" + tag] = sum(by[l]) / len(by[l])
        out["arms_" + tag] = {"m%d" % a: n for a, n in sorted(arms[l].items())}
        out["hit_" + tag] = statistics.mean(hits[l])
        if pm[l]:
            out["p_mean_end_" + tag] = pm[l]
    return out


def fixed_and_oracle(cond):
    v = cond["val"]
    rows = cond["rows"]
    sched = v["protocol"]["schedule"]
    cyc = v["protocol"]["cycles"]
    m = {}
    for a in ARMS:
        for loss, _ in sched:
            xs = [r["ms"] if r["ok"] else FAIL_MS for c in range(cyc)
                  for r in rows[(c, loss, "m%d" % a)]]
            m[(a, loss)] = sum(xs) / len(xs)
    losses = [l for l, _ in sched]
    fixed = {a: sum(m[(a, l)] for l in losses) / len(losses) for a in ARMS}
    orc = sum(min(m[(a, l)] for a in ARMS) for l in losses) / len(losses)
    orcarm = {l: min(ARMS, key=lambda a: m[(a, l)]) for l in losses}
    return m, fixed, orc, orcarm


def boot_block(cond, factory, orcarm):
    seeds = []
    for sd in SEEDS:
        pol = factory()
        res = run(cond, pol, sd, True)
        s = summarize(res, orcarm)
        s.pop("p_mean_end_2", None)
        s.pop("p_mean_end_15", None)
        s["seed"] = sd
        s["diag"] = pol.diag()
        seeds.append(s)
    means = [s["mean"] for s in seeds]
    return {"means": means, "mean": statistics.mean(means),
            "sd": statistics.pstdev(means), "min": min(means),
            "max": max(means), "per_seed": seeds}


def work(args):
    name, cond, variants = args
    t0 = time.time()
    v = cond["val"]
    cert = v["cert"]
    up = float(v["up_policy"])
    m, fixed, orc, orcarm = fixed_and_oracle(cond)
    out = {"cond": name, "cert": cert, "rtt_ms": v["rtt_ms"], "uplink_mbps": up,
           "run_id": cond["run_id"], "recorded_at": cond["recorded_at"],
           "actual_auto": v["arms"]["auto"]["mean"],
           "actual_auto_n": v["arms"]["auto"]["n"],
           "fixed": {"m%d" % a: fixed[a] for a in ARMS},
           "fixed_by_loss": {"m%d|%g" % (a, l): x for (a, l), x in m.items()},
           "oracle": orc, "oracle_arm": {"%g" % l: "m%d" % a
                                         for l, a in orcarm.items()}}
    tab_a = G2Tables(cert, up)
    res = run(cond, Gen2Clone(tab_a), 0, False)
    out["gen2_clone_aligned"] = summarize(res, orcarm)
    tab_b = G2Tables(cert, up)
    out["gen2_clone_boot"] = boot_block(cond, lambda: Gen2Clone(tab_b), orcarm)
    for label, later in variants:
        learn3.clear_model_cache()
        pol = V3Learn(up, later)
        res = run(cond, pol, 0, False)
        s = summarize(res, orcarm)
        s["diag"] = pol.diag()
        out[label + "_aligned"] = s
        out[label + "_boot"] = boot_block(cond, lambda: V3Learn(up, later),
                                          orcarm)
    out["cpu_s"] = time.time() - t0
    return out


def proto_compare(proto_dir, results):
    found = {}
    if not proto_dir or not os.path.isdir(proto_dir):
        return {"available": False}
    for i in range(4):
        p = os.path.join(proto_dir, "boot_%d.json" % i)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        found[d["cond"]] = d
    out = {"available": bool(found), "files_sha256": {}}
    for i in range(4):
        p = os.path.join(proto_dir, "boot_%d.json" % i)
        if os.path.exists(p):
            out["files_sha256"]["boot_%d.json" % i] = sha256_file(p)
    rows = {}
    for r in results:
        d = found.get(r["cond"])
        if d is None or "gen2" not in d:
            continue
        mine = r["gen2_clone_boot"]["means"]
        theirs = d["gen2"]["means"]
        row = {"proto_gen2_means": theirs, "max_abs_diff_ms":
               max(abs(a - b) for a, b in zip(mine, theirs)),
               "proto_gen2_mean": d["gen2"]["mean"],
               "proto_gen2_sd": d["gen2"]["sd"]}
        for lab in ("v3-bayes", "v3-ids", "v3-plugin", "v3-m0only"):
            if lab in d:
                row["proto_" + lab] = {"mean": d[lab]["mean"], "sd": d[lab]["sd"]}
        rows[r["cond"]] = row
    out["by_cond"] = rows
    return out


def paired(a_means, b_means):
    ds = [x - y for x, y in zip(a_means, b_means)]
    return {"diffs": ds, "mean": statistics.mean(ds),
            "sd": statistics.pstdev(ds), "min": min(ds), "max": max(ds)}


def recorded_v31(journal, cond_names=(), limit=0):
    states, seen, results = {}, set(), []
    with open(journal, encoding="utf-8") as f:
        for line in f:
            unit = json.loads(line)
            val = unit["val"]
            name = val["cond"]
            if cond_names and name not in cond_names:
                continue
            segments = [s for s in val["segments"] if s["arm"] == "g3auto"]
            if not segments:
                continue
            identity = (unit["run_id"], unit["key"])
            if identity in seen or val.get("attempt", 1) != 1 or val.get("err"):
                raise ValueError("duplicate, retried or failed journal unit: %s"
                                 % (identity,))
            seen.add(identity)
            for seg in segments:
                argv = seg["argv"]
                up = float(argv[argv.index("-uplink-mbps") + 1])
                state_key = (unit["run_id"], name)
                st, rt, state_up = states.setdefault(
                    state_key, (learn3.new_state(), RttTrack(), up))
                if up != state_up:
                    raise ValueError("uplink changed within a recorded condition")
                for row in seg["rows"]:
                    if row.get("policy_version") != "v3.1":
                        raise ValueError("recorded-v31 requires v3.1 auto rows")
                    if row.get("why3") == "cold":
                        st, rt = learn3.new_state(), RttTrack()
                        states[state_key] = (st, rt, up)
                    action = learn3.check_action(tuple(row["action"]))
                    rtt = rt.rtt()
                    res = decide3.decide3(st, W, up, rtt, C_PKT)
                    prediction = res["j3_pred_pre_ms"]
                    if action != tuple(res["action"]):
                        prediction = None
                        if st.k_hist and st.S_hist and rtt > 0:
                            prediction = decide3.decide_core(
                                learn3.combined(st), learn3.k_hat(st), W,
                                learn3.s_hat(st), up, rtt, C_PKT,
                                actions=[action])["ej"]
                    rt.observe(row)
                    info = learn3.observe3(
                        st, action, row["ms"] if row["ok"] else None,
                        row["ok"], row["first_flight_datagrams"],
                        row["server_bytes"], rt.rtt(), W=W, u_mbps=up,
                        c_pkt=C_PKT, j_pred=prediction)
                    results.append({
                        "unit": unit["key"], "row_i": row["i"], "cond": name,
                        "recorded_policy_version": "v3.1",
                        "recorded_action": list(action), "recorded_hct_ms":
                        row["ms"] if row["ok"] else None,
                        "new_decision": {key: res[key] for key in
                                         ("action", "policy_version", "reeval",
                                          "j3_pred_pre_ms", "guard_alarm",
                                          "guard_common_ms", "guard_alarmed_actions")},
                        "recorded_action_prediction_ms": prediction,
                        "recorded_action_residual_ms": info["resid"],
                        "new_observation": {key: info[key] for key in
                                            ("y", "skip", "updated", "raised",
                                             "alarmed", "common", "n_alarm")},
                        "new_posterior_after": learn3.post_summary(learn3.combined(st)),
                        "new_stats_after": {key: st.stats[key] for key in
                                            ("obs", "upd", "predict", "guard")}})
                    if limit and len(results) >= limit:
                        return results
    if not results:
        raise ValueError("no selected v3.1 g3auto journal rows")
    return results


def write_doc(path, doc):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", default=P17_DEFAULT)
    ap.add_argument("--proto-dir", default=PROTO_DEFAULT)
    ap.add_argument("--out")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--conds", default="")
    ap.add_argument("--no-v3later", action="store_true")
    ap.add_argument("--recorded-v31", action="store_true",
                    help="feed recorded v3.1 actions/outcomes, without executing new decisions")
    ap.add_argument("--limit", type=int, default=0,
                    help="maximum recorded-v31 rows (0 means all)")
    a = ap.parse_args(argv)
    if a.limit < 0 or (a.limit and not a.recorded_v31):
        ap.error("--limit requires --recorded-v31 and a non-negative value")
    if a.recorded_v31 and not a.out:
        ap.error("--recorded-v31 requires an explicit --out development file")
    a.out = a.out or OUT_DEFAULT
    if os.path.normcase(os.path.realpath(a.out)) == os.path.normcase(os.path.realpath(a.journal)):
        ap.error("output must differ from the input journal")
    t0 = time.time()
    if a.recorded_v31:
        rows = recorded_v31(a.journal, set(filter(None, a.conds.split(","))), a.limit)
        doc = {"schema": "replay_g3.recorded_v31.development.v1",
               "label": "development/counterfactual", "confirmatory": False,
               "policy_version": learn3.POLICY_VERSION,
               "trajectory_kind": "recorded_action_observation_replay",
               "note": REPLAY_NOTE,
               "journal": {"path": a.journal, "sha256": sha256_file(a.journal),
                           "recorded_policy_version": "v3.1"},
               "limit": a.limit, "rows": rows}
        write_doc(a.out, doc)
        print("development/counterfactual: %s; %d historical rows" %
              (learn3.POLICY_VERSION, len(rows)))
        print(REPLAY_NOTE)
        print("wrote %s" % a.out)
        return doc
    order, conds, sel_sha = load(a.journal)
    if a.conds:
        keep = set(a.conds.split(","))
        order = [n for n in order if n in keep]
    variants = [("v3_g2later", "g2")]
    if not a.no_v3later:
        variants.append(("v3_v3later", "v3"))
    jobs = [(n, conds[n], variants) for n in order]
    if a.jobs > 1 and len(jobs) > 1:
        import multiprocessing
        with multiprocessing.Pool(min(a.jobs, len(jobs))) as pool:
            results = pool.map(work, jobs)
    else:
        results = [work(j) for j in jobs]
    summary = {}
    for r in results:
        row = {"actual_auto": r["actual_auto"],
               "clone_aligned": r["gen2_clone_aligned"]["mean"],
               "clone_aligned_minus_actual":
                   r["gen2_clone_aligned"]["mean"] - r["actual_auto"],
               "clone_boot_mean": r["gen2_clone_boot"]["mean"],
               "clone_boot_sd": r["gen2_clone_boot"]["sd"],
               "clone_boot_minus_actual":
                   r["gen2_clone_boot"]["mean"] - r["actual_auto"],
               "clone_aligned_within_0p8_ms": (
                   abs(r["gen2_clone_aligned"]["mean"] - r["actual_auto"]) <= 0.8),
               "actual_within_clone_boot_range": (
                   r["gen2_clone_boot"]["min"] <= r["actual_auto"]
                   <= r["gen2_clone_boot"]["max"]),
               "best_fixed": min(r["fixed"], key=r["fixed"].get),
               "best_fixed_mean": min(r["fixed"].values()),
               "oracle": r["oracle"]}
        for label, _ in variants:
            row[label + "_aligned"] = r[label + "_aligned"]["mean"]
            row[label + "_boot_mean"] = r[label + "_boot"]["mean"]
            row[label + "_boot_sd"] = r[label + "_boot"]["sd"]
            row[label + "_minus_clone_aligned"] = (
                r[label + "_aligned"]["mean"] - r["gen2_clone_aligned"]["mean"])
            row[label + "_minus_clone_boot"] = paired(
                r[label + "_boot"]["means"], r["gen2_clone_boot"]["means"])
            row[label + "_minus_actual_aligned"] = (
                r[label + "_aligned"]["mean"] - r["actual_auto"])
        summary[r["cond"]] = row
    doc = {"label": LABEL + "; " + REPLAY_NOTE,
           "analysis_kind": "development/counterfactual", "confirmatory": False,
           "policy_version": learn3.POLICY_VERSION,
           "trajectory_kind": "offline_journal_outcome_resampling",
           "generated_by": "experiments/replay_g3.py",
           "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "journal": {"path": a.journal, "sha256": sha256_file(a.journal),
                       "fp": FP, "selected_lines_sha256": sel_sha,
                       "conds": order},
           "inputs": {"C": C_ML, "W": W, "c_pkt": C_PKT, "fail_ms": FAIL_MS,
                      "seeds": list(SEEDS),
                      "legacy_actions": {"m%d" % k: list(v)
                                         for k, v in LEGACY.items()},
                      "learn3": {"G": list(learn3.G), "H": list(learn3.H),
                                 "eps": learn3.EPS, "w_floor": learn3.W_FLOOR,
                                 "k_win": learn3.K_WIN, "s_win": learn3.S_WIN,
                                 "hct_win": learn3.HCT_WIN,
                                 "base_min": learn3.BASE_MIN,
                                 "event_rtt_frac": learn3.EVENT_RTT_FRAC,
                                 "shield_rtt_ms": learn3.SHIELD_RTT_MS},
                      "variants": {lab: {"later": lt} for lab, lt in variants}},
           "notes": [
               "gen2_clone is a port of the design_learning prototype "
               "replay.py Gen2 (decide_v2 J at W=1280, arms m0..m3, m0 probe "
               "rule, 1.3x+2 ms classifier, 0.99 decay, last-K)",
               "v3_* run padfec3.learn3/decide3 with the action set restricted "
               "to the four journal arms (legacy layout, delta 0); n_need comes "
               "from the median of server_bytes, k from the mode of the last 16",
               "v3_g2later uses the gen-2 later-flight term in J3 (the journal "
               "was measured with the gen-2 transport); v3_v3later uses the v3 "
               "term as a sensitivity row",
               "boot rows resample journal rows with random.Random(seed) exactly "
               "as the prototype boot.py; aligned rows take trial t of the "
               "chosen arm's segment"],
           "summary": summary,
           "prototype_compare": proto_compare(a.proto_dir, results),
           "by_cond": results,
           "cpu_wall_s": time.time() - t0}
    write_doc(a.out, doc)
    print("development/counterfactual: %s" % learn3.POLICY_VERSION)
    print(REPLAY_NOTE)
    for name in order:
        row = summary[name]
        line = ["%s: actual %.3f | clone aligned %.3f (%+.3f) boot %.3f+-%.3f (%+.3f)"
                % (name, row["actual_auto"], row["clone_aligned"],
                   row["clone_aligned_minus_actual"], row["clone_boot_mean"],
                   row["clone_boot_sd"], row["clone_boot_minus_actual"])]
        for label, _ in variants:
            line.append("  %s aligned %.3f (%+.3f vs clone) boot %.3f+-%.3f "
                        "(paired %+.3f+-%.3f)"
                        % (label, row[label + "_aligned"],
                           row[label + "_minus_clone_aligned"],
                           row[label + "_boot_mean"], row[label + "_boot_sd"],
                           row[label + "_minus_clone_boot"]["mean"],
                           row[label + "_minus_clone_boot"]["sd"]))
        print("\n".join(line))
    pc = doc["prototype_compare"]
    if pc.get("available"):
        for name, row in pc["by_cond"].items():
            print("prototype gen2 boot reproduction %s: max |diff| %.6f ms"
                  % (name, row["max_abs_diff_ms"]))
    print("wrote %s (%.0f s)" % (a.out, time.time() - t0))
    return doc


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
