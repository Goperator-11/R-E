import argparse
import hashlib
import json
import os
import random
import sys
import time

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from padfec import policy, quantum
from padfec3 import decide3, layout, learn3

SCHEMA = "padfec3.policy3_reference/2"
SEED_DECISIONS = 20261002
SEED_PRIMITIVES = 20261003
SEED_CLIFF = 20261031
SEED_PEN = 20261032
TRAJ_SEEDS = (31, 32, 33, 34, 35)
C_PKT = policy.C_PKT_POLICY_DEFAULT
KS = (1, 2, 3, 4)
WS = (1200, 1280, 1350)
CERTS = (1000, 2308, 3000, 3200, 4032, 5609, 5800, 6500, 8000, 9000, 10800,
         12000, 14000, 16000)
S0S = (382.45, 1472.0)
RTTS = (10.0, 50.0, 100.0, 200.0)
US = (0.0, 2.0, 5.0, 10.0, 100.0)
POST_KINDS = (("point", 70), ("mix2", 15), ("mix4", 10), ("full", 5))
DEBUG_EVERY = 10
PEN_EVERY = 5
PEN_PHASE = 2
N_PRIMITIVES = 2000
N_CLIFF = 800
TRAJ_STEPS = 10000
SNAP_EVERY = 1000
OUT_DEFAULT = os.path.join(ROOT, "g3", "policy3_reference.json")
SOURCES = ("padfec3/learn3.py", "padfec3/decide3.py", "padfec3/layout.py",
           "padfec/policy.py", "padfec/quantum.py", "padfec/table.py",
           "g3/policy3_reference_gen.py")
TRAJ_SPECS = (
    {"id": "T1_bigcert", "seed": TRAJ_SEEDS[0], "cert": 16000,
     "s0_base": 1472.0, "k": 2, "W": 1280, "u": 2.0, "rtt_true": 50.0,
     "schedule": [[0.02, 450], [0.15, 450]]},
    {"id": "T2_rtt200", "seed": TRAJ_SEEDS[1], "cert": 9000,
     "s0_base": 1472.0, "k": 2, "W": 1280, "u": 2.0, "rtt_true": 200.0,
     "schedule": [[0.02, 450], [0.15, 450]]},
    {"id": "T3_x25519_unlimited", "seed": TRAJ_SEEDS[2], "cert": 4032,
     "s0_base": 382.45, "k": 1, "W": 1280, "u": 0.0, "rtt_true": 50.0,
     "schedule": [[0.0, 700], [0.05, 300], [0.01, 500]]},
    {"id": "T4_shielded_rtt200", "seed": TRAJ_SEEDS[3], "cert": 30000,
     "s0_base": 1472.0, "k": 2, "W": 1280, "u": 5.0, "rtt_true": 200.0,
     "schedule": [[0.02, 450], [0.15, 450]]},
    {"id": "T5_guard_c6000_u10", "seed": TRAJ_SEEDS[4], "cert": 6000,
     "s0_base": 1472.0, "k": 2, "W": 1280, "u": 10.0, "rtt_true": 80.0,
     "schedule": [[0.01, 400], [0.08, 400]], "common_ms": 3.0,
     "bias": [{"action": [0, 2, 2], "rtt_mult": 1.0, "prob": 0.9}]},
)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def synth_s(cert, s0_base, k, w):
    return float(cert) + s0_base + float(quantum.bin_index(k * w)) * C_PKT


def draw_kind(rng):
    x = rng.randrange(100)
    acc = 0
    for name, wgt in POST_KINDS:
        acc += wgt
        if x < acc:
            return name
    return POST_KINDS[-1][0]


def draw_post(rng, kind):
    n = len(learn3.G)
    if kind == "point":
        return [rng.randrange(n)], [1.0]
    if kind == "full":
        gs = list(range(n))
    else:
        gs = sorted(rng.sample(range(n), 2 if kind == "mix2" else 4))
    raw = [rng.random() + 1e-3 for _ in gs]
    s = sum(raw)
    return gs, [x / s for x in raw]


def dense(gs, qs):
    post = [0.0] * len(learn3.G)
    for g, q in zip(gs, qs):
        post[g] = q
    return post


def draw_pen(rng, cands, best):
    acts = [c["action"] for c in cands]
    pick = [best]
    for _ in range(rng.randrange(0, 3)):
        a = acts[rng.randrange(len(acts))]
        if a not in pick:
            pick.append(a)
    out = []
    for a in pick:
        ms = round(rng.random() * 80.0, 3) if rng.random() < 0.85 else 0.0
        out.append([a[0], a[1], a[2], ms])
    return out


def pen_map(rows):
    return {"%d,%d,%d" % (r[0], r[1], r[2]): float(r[3]) for r in rows}


def gen_decisions():
    rng = random.Random(SEED_DECISIONS)
    rng_pen = random.Random(SEED_PEN)
    ctxs = [(k, w, cert, s0, rtt, u) for k in KS for w in WS for cert in CERTS
            for s0 in S0S for rtt in RTTS for u in US]
    rng.shuffle(ctxs)
    out = []
    for i, (k, w, cert, s0, rtt, u) in enumerate(ctxs):
        kind = draw_kind(rng)
        gs, qs = draw_post(rng, kind)
        S = synth_s(cert, s0, k, w)
        post = dense(gs, qs)
        pen = None
        if i % PEN_EVERY == PEN_PHASE:
            r0 = decide3.decide_core(post, k, w, S, u, rtt, C_PKT,
                                     keep_cands=True)
            pen = draw_pen(rng_pen, r0["cands"], r0["action"])
        r = decide3.decide_core(post, k, w, S, u, rtt, C_PKT, keep_cands=True,
                                pen=None if pen is None else pen_map(pen))
        cands = r["cands"]
        alt = r["alt"]
        rec = {"id": i, "k": k, "W": w, "cert": cert, "s0_base": s0, "S": S,
               "rtt": rtt, "u": u, "a_pre": layout.preflight_bytes(k, u),
               "post_kind": kind, "g": gs, "q": qs,
               "n_need": r["n_need"],
               "n_need_cert": quantum.bin_needed(cert, None, s0, C_PKT),
               "n_cands": r["n_cands"], "cand_hash": decide3.cand_hash(cands),
               "action": list(r["action"]), "mode": r["mode"], "ej": r["ej"],
               "pen_chosen": r["pen"], "score": r["score"], "n2": r["n2"],
               "jmin": r["jmin"], "n_tied": r["n_tied"],
               "reeval_cond": r["reeval_cond"],
               "alt": None if alt is None else list(alt["action"]),
               "alt_ej": None if alt is None else alt["ej"],
               "alt_score": None if alt is None else alt["score"]}
        if pen is not None:
            rec["pen"] = pen
        if i % DEBUG_EVERY == 0 or pen is not None:
            rec["cands"] = [[c["delta"], c["lead"], c["T"], c["ej"],
                             1 if c["n2"] else 0, c["pen"]] for c in cands]
        out.append(rec)
    return out


def gen_primitives():
    rng = random.Random(SEED_PRIMITIVES)
    weffs = (1200, 1201, 1280, 1281, 1350, 1452)
    rtts = (10.0, 37.5, 50.0, 100.0, 200.0)
    us = (0.0, 1.5, 2.0, 5.0, 10.0, 100.0)
    out = []
    for i in range(N_PRIMITIVES):
        k = rng.choice(KS)
        m = rng.randrange(0, layout.M_MAX + 1)
        lead = rng.randrange(0, m + 1)
        w_eff = rng.choice(weffs)
        if rng.random() < 0.5:
            p = learn3.G[rng.randrange(len(learn3.G))]
        else:
            p = round(rng.random() * 0.3, 6)
        rtt = rng.choice(rtts)
        u = rng.choice(us)
        n_need = rng.randrange(1, 21)
        out.append(prim_rec(i, "random", k, w_eff, m, lead, p, rtt, u, n_need))
    rng = random.Random(SEED_CLIFF)
    i = N_PRIMITIVES
    while i < N_PRIMITIVES + N_CLIFF:
        k = rng.choice(KS)
        m = rng.randrange(0, layout.M_MAX + 1)
        lead = rng.randrange(0, m + 1)
        n_need = rng.randrange(2, 21)
        u = rng.choice((0.0, 2.0, 10.0, 100.0))
        a_max = layout.PREFLIGHT_ACK_BYTES * (k - 1)
        edge = quantum.P_SERVER * (n_need - 1)
        ws = [w for w in range(1200, 1453)
              if -30 <= 3 * layout.pre_decision_bytes(k, m, lead, w) - edge
              <= a_max + 30]
        if not ws:
            continue
        w_eff = ws[rng.randrange(len(ws))]
        p = 0.0 if rng.random() < 0.4 else learn3.G[rng.randrange(len(learn3.G))]
        rtt = rng.choice((20.0, 50.0, 80.0, 120.0))
        out.append(prim_rec(i, "cliff", k, w_eff, m, lead, p, rtt, u, n_need))
        i += 1
    return out


def prim_rec(i, kind, k, w_eff, m, lead, p, rtt, u, n_need):
    ev = layout.evaluate(k, w_eff, m, lead, p, rtt, u, n_need, "v3")
    return {"id": i, "set": kind, "k": k, "W_eff": w_eff, "m": m,
            "lead": lead, "p": p, "rtt": rtt, "u": u, "n_need": n_need,
            "a_pre": ev["a_pre"],
            "margin": 3 * layout.pre_decision_bytes(k, m, lead, w_eff)
            - quantum.P_SERVER * (n_need - 1),
            "J": ev["J"], "e": ev["e"], "p_two_rtt": ev["p_two_rtt"],
            "p_fail": ev["p_fail"], "p_one_rtt": ev["p_one_rtt"]}


def loss_at(spec, t):
    period = sum(n for _, n in spec["schedule"])
    x = t % period
    for p, n in spec["schedule"]:
        if x < n:
            return p
        x -= n
    return spec["schedule"][-1][0]


def simulate(spec, rng, action, p_true, rtt_true):
    k = spec["k"]
    d, lead, t = action
    m = lead + t
    w_eff = spec["W"] + d
    S_true = synth_s(spec["cert"], spec["s0_base"], k, spec["W"])
    n_need = quantum.bin_needed(spec["cert"], None, spec["s0_base"], C_PKT)
    ev = layout.evaluate(k, w_eff, m, lead, p_true, rtt_true, spec["u"],
                         n_need, "v3")
    pre = layout.tau(layout.pre_decision_bytes(k, m, lead, w_eff), spec["u"])
    x = rng.random()
    jit = rng.random() * 2.0
    srv = int(S_true) + rng.randint(-30, 30)
    if x < ev["p_one_rtt"]:
        hct = rtt_true + pre + jit
    elif x < ev["p_one_rtt"] + ev["p_two_rtt"]:
        hct = 2 * rtt_true + pre + layout.tau(w_eff, spec["u"]) + jit
    else:
        n_nom = 2 if ev["e"] >= 0.5 and ev["p_fail"] < 0.5 else 1
        if rng.random() < 0.3:
            hct = rtt_true + layout.T_PTO_MS + jit
        else:
            hct = (n_nom * rtt_true + layout.T_ACK_SLOPE * rtt_true
                   + layout.T_ACK_BASE_MS + pre + jit * 2.5)
        srv += rng.randint(1000, 3000)
    if rng.random() < 0.001:
        hct *= 0.6
    hct += spec.get("common_ms", 0.0)
    for rule in spec.get("bias", ()):
        if list(action) == rule["action"] and rng.random() < rule["prob"]:
            hct += rule["rtt_mult"] * rtt_true
    ok = rng.random() >= 0.0005
    kk = k
    r = rng.random()
    if r < 0.005:
        kk = max(1, k - 1)
    elif r < 0.01:
        kk = min(4, k + 1)
    return (round(hct, 3) if ok else None), ok, kk, srv


def gen_trajectory(spec):
    rng = random.Random(spec["seed"])
    st = learn3.new_state()
    W, u = spec["W"], spec["u"]
    rtt_pol = 0.0
    steps = {"a": [], "why": [], "ej": [], "p_mean": [], "rtt": [], "hct": [],
             "ok": [], "k": [], "srv": [], "y": [], "upd": [], "n2": [],
             "reeval": [], "pen": [], "alarm": [], "common": [],
             "n_alarm": [], "resid": [], "skip": []}
    snaps = []
    for t in range(TRAJ_STEPS):
        p_true = loss_at(spec, t)
        sample = round(spec["rtt_true"] + 0.5 + rng.random() * 7.5, 3)
        if rtt_pol <= 0 or sample < rtt_pol:
            rtt_pol = sample
        r = decide3.decide3(st, W, u, rtt_pol, C_PKT)
        a = tuple(r["action"])
        hct, ok, kk, srv = simulate(spec, rng, a, p_true, spec["rtt_true"])
        info = learn3.observe3(st, a, hct, ok, kk, srv, rtt_pol, W=W,
                               u_mbps=u, c_pkt=C_PKT,
                               j_pred=r["j3_pred_pre_ms"])
        steps["a"].append(list(a))
        steps["why"].append(r["why"])
        steps["ej"].append(r["ej"])
        steps["p_mean"].append(r["p_mean"])
        steps["rtt"].append(rtt_pol)
        steps["hct"].append(hct)
        steps["ok"].append(1 if ok else 0)
        steps["k"].append(kk)
        steps["srv"].append(srv)
        steps["y"].append(info["y"])
        steps["upd"].append(1 if info["updated"] else 0)
        steps["n2"].append(None if r["n2"] is None else (1 if r["n2"] else 0))
        steps["reeval"].append(1 if r["reeval"] else 0)
        steps["pen"].append(r["pen"])
        steps["alarm"].append(1 if r["guard_alarm"] else 0)
        steps["common"].append(r["guard_common_ms"])
        steps["n_alarm"].append(r["guard_alarmed_actions"])
        steps["resid"].append(info["resid"])
        steps["skip"].append(info["skip"])
        if (t + 1) % SNAP_EVERY == 0:
            post = learn3.combined(st)
            ctx = learn3.context(st, W, u, rtt_pol, C_PKT)
            snaps.append({"after_step": t + 1, "post_h": [list(p) for p in st.post],
                          "w": list(st.w), "combined": post,
                          "p_mean": learn3.post_mean(post),
                          "k_hat": learn3.k_hat(st), "S_hat": learn3.s_hat(st),
                          "n_need": None if ctx is None else ctx["n_need"],
                          "state": st.to_json()})
    acts = {}
    for a in steps["a"]:
        key = "%d,%d,%d" % tuple(a)
        acts[key] = acts.get(key, 0) + 1
    return {"id": spec["id"], "seed": spec["seed"], "cert": spec["cert"],
            "s0_base": spec["s0_base"], "k_true": spec["k"], "W": W, "u": u,
            "c_pkt": C_PKT, "rtt_true": spec["rtt_true"],
            "schedule": spec["schedule"],
            "common_ms": spec.get("common_ms", 0.0),
            "bias": list(spec.get("bias", ())), "n_steps": TRAJ_STEPS,
            "action_counts": dict(sorted(acts.items())),
            "final_stats": dict(st.stats), "steps": steps, "snapshots": snaps}


def constants():
    return {"G": list(learn3.G), "H": list(learn3.H), "eps": learn3.EPS,
            "w_floor": learn3.W_FLOOR, "k_win": learn3.K_WIN,
            "s_win": learn3.S_WIN, "hct_win": learn3.HCT_WIN,
            "base_min": learn3.BASE_MIN,
            "event_rtt_frac": learn3.EVENT_RTT_FRAC,
            "shield_rtt_ms": learn3.SHIELD_RTT_MS,
            "shield_e0": learn3.SHIELD_E0, "j_tie_ms": decide3.J_TIE,
            "max_ips": decide3.MAX_IPS, "udp_max": decide3.UDP_MAX,
            "m_max": decide3.M_MAX, "k_max": layout.K_MAX,
            "max_steps": decide3.MAX_STEPS, "c_pkt": C_PKT,
            "p_server": quantum.P_SERVER,
            "parity_overhead": [policy.PARITY_OVERHEAD_BASE,
                                policy.PARITY_OVERHEAD_PER_K],
            "t_pto_ms": layout.T_PTO_MS, "t_ack_slope": layout.T_ACK_SLOPE,
            "t_ack_base_ms": layout.T_ACK_BASE_MS,
            "pto_sampled_mult": layout.PTO_SAMPLED_MULT,
            "race_delay_ms": list(policy.RACE_DELAY_MS),
            "race_win_q": list(policy.RACE_WIN_Q), "later": "v3",
            "b0": list(learn3.B0),
            "policy_version": learn3.POLICY_VERSION,
            "state_version": learn3.STATE_VERSION,
            "preflight_ack_bytes": layout.PREFLIGHT_ACK_BYTES,
            "reeval_every": learn3.REEVAL_EVERY,
            "guard_common_win": learn3.GUARD_COMMON_WIN,
            "guard_action_win": learn3.GUARD_ACTION_WIN,
            "guard_min": learn3.GUARD_MIN,
            "guard_rtt_frac": learn3.GUARD_RTT_FRAC,
            "guard_refresh": learn3.GUARD_REFRESH}


def build():
    t0 = time.time()
    doc = {"schema": SCHEMA,
           "label": "deterministic reference vectors for the Go port of "
                    "padfec3 learn3/decide3 (no measurement data)",
           "generated_by": "g3/policy3_reference_gen.py",
           "seeds": {"decisions": SEED_DECISIONS,
                     "primitives": SEED_PRIMITIVES,
                     "cliff_primitives": SEED_CLIFF,
                     "penalties": SEED_PEN,
                     "trajectories": list(TRAJ_SEEDS)},
           "sources_sha256": {p: sha256_file(os.path.join(ROOT, p))
                              for p in SOURCES},
           "constants": constants()}
    learn3.clear_model_cache()
    doc["primitives"] = gen_primitives()
    t1 = time.time()
    doc["decisions"] = gen_decisions()
    t2 = time.time()
    doc["trajectories"] = [gen_trajectory(s) for s in TRAJ_SPECS]
    t3 = time.time()
    doc["timing_s"] = {"primitives": t1 - t0, "decisions": t2 - t1,
                       "trajectories": t3 - t2}
    return doc


def dump(doc, path):
    head = {k: v for k, v in doc.items()
            if k not in ("primitives", "decisions", "trajectories")}
    lines = ["{"]
    for k, v in head.items():
        lines.append("%s: %s," % (json.dumps(k), json.dumps(v)))
    for name in ("primitives", "decisions"):
        lines.append("%s: [" % json.dumps(name))
        rows = doc[name]
        for i, r in enumerate(rows):
            lines.append(json.dumps(r, separators=(",", ":"))
                         + ("," if i < len(rows) - 1 else ""))
        lines.append("],")
    lines.append('"trajectories": [')
    ts = doc["trajectories"]
    for i, tr in enumerate(ts):
        lines.append(json.dumps(tr, separators=(",", ":"))
                     + ("," if i < len(ts) - 1 else ""))
    lines.append("]")
    lines.append("}")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, path)


def strip(doc):
    return {k: v for k, v in doc.items() if k not in ("timing_s",)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    doc = build()
    if a.check:
        with open(a.out, encoding="utf-8") as f:
            old = json.load(f)
        new = json.loads(json.dumps(strip(doc)))
        same = strip(old) == new
        diff = [k for k in new if strip(old).get(k) != new.get(k)]
        print("check: %s%s" % ("identical" if same else "DIFFERENT",
                               "" if same else " " + ",".join(diff)))
        return 0 if same else 1
    dump(doc, a.out)
    with open(a.out, encoding="utf-8") as f:
        back = json.load(f)
    assert strip(back) == json.loads(json.dumps(strip(doc)))
    acts = {}
    for d in doc["decisions"]:
        key = "%d,%d,%d" % tuple(d["action"])
        acts[key] = acts.get(key, 0) + 1
    print("primitives %d, decisions %d (distinct actions %d), trajectories %d"
          " x %d steps; timing %s"
          % (len(doc["primitives"]), len(doc["decisions"]), len(acts),
             len(doc["trajectories"]), TRAJ_STEPS,
             {k: round(v, 1) for k, v in doc["timing_s"].items()}))
    for tr in doc["trajectories"]:
        stp = tr["steps"]
        print(tr["id"], tr["action_counts"], tr["final_stats"],
              "reeval", sum(stp["reeval"]), "alarm_steps", sum(stp["alarm"]),
              "max_n_alarm", max(stp["n_alarm"]))
    print("wrote %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
