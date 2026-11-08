import argparse
import hashlib
import importlib.util
import json
import os
import platform
import random
import subprocess
import sys
import time
from datetime import datetime, timezone

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from generation import load_config

GENCONFIG = load_config(ROOT)
QUICBED = os.path.join(HERE, "quicbed")
REF_DEFAULT = os.path.join(ROOT, "g3", "policy3_reference.json")
GEN_PATH = os.path.join(ROOT, "g3", "policy3_reference_gen.py")
OUT_DEFAULT = os.path.join(HERE, "results", "gate_v3_parity.json")
BIN_DEFAULT = os.path.expanduser(GENCONFIG["binary"])
G2_FROZEN_SHA256 = "d98b05d73f44774ad622ab1c4993526cac58957b22310fc61122d7bd44964213"
SCHEMA = "padfec3.gate_v3_parity/2"
POLICY_VERSION = "v3.3.1-dev"
J_TOL = 1e-9
REL_TOL = 1e-12
FRESH_SEED = 20261005
FRESH_PEN_SEED = 20261006
FRESH_CLIFF_SEED = 20261007
FRESH_DECISIONS = 5000
FRESH_PRIMITIVES = 2000
FRESH_CLIFF = 600
FRESH_TRAJ = (
    {"id": "F1_cert12000_k3", "seed": 35, "cert": 12000, "s0_base": 1472.0, "k": 3,
     "W": 1350, "u": 5.0, "rtt_true": 100.0, "schedule": [[0.01, 300], [0.08, 300]]},
    {"id": "F2_cert6000_rtt20", "seed": 36, "cert": 6000, "s0_base": 1472.0, "k": 2,
     "W": 1280, "u": 1.0, "rtt_true": 20.0, "schedule": [[0.0, 400], [0.12, 200]]},
    {"id": "F3_reeval_cert16000_rtt30", "seed": 37, "cert": 16000, "s0_base": 382.45, "k": 2,
     "W": 1280, "u": 2.0, "rtt_true": 30.0, "schedule": [[0.03, 400], [0.18, 400]]},
    {"id": "F4_guard_cert14000_w1350", "seed": 39, "cert": 14000, "s0_base": 1472.0, "k": 2,
     "W": 1350, "u": 2.0, "rtt_true": 45.0, "schedule": [[0.02, 350], [0.16, 350]],
     "common_ms": 1.5, "bias": [{"action": [0, 3, 1], "rtt_mult": 0.8, "prob": 0.7}]},
)
PRIM_FIELDS = ("J", "e", "p_two_rtt", "p_fail", "p_one_rtt")
PRIM_EXACT = ("a_pre",)
DEC_EXACT = ("action", "mode", "n_need", "n_cands", "cand_hash", "n_tied", "n2", "reeval_cond",
             "alt")
DEC_CLOSE = ("ej", "jmin", "score", "pen_chosen", "alt_ej", "alt_score")
STEP_EXACT = ("a", "why", "y", "upd", "n2", "reeval", "alarm", "n_alarm", "skip")
STEP_CLOSE = ("ej", "pen", "common", "resid")
STATE_EXACT = ("v", "k_hist", "S_hist", "hct", "hct_seq", "seq", "n_dec", "n_reeval", "g_alarm",
               "stats")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def quicbed_fingerprint():
    names = sorted(os.listdir(QUICBED))
    build_like = [n for n in names
                  if n.endswith(".go") or n in ("build.sh", GENCONFIG["build_script"], "go.mod", "go.sum")]
    hook = os.path.join(QUICBED, "padfechook")
    if os.path.isdir(hook):
        build_like.extend("padfechook/" + n for n in os.listdir(hook)
                          if n.endswith(".go") or n == "go.mod")
    lines = "".join("%s %s\n" % (n, sha256_file(os.path.join(QUICBED, n)))
                    for n in sorted(build_like))
    return hashlib.sha256(lines.encode()).hexdigest()


def to_wsl(path):
    p = os.path.abspath(path).replace("\\", "/")
    if len(p) > 1 and p[1] == ":":
        return "/mnt/%s%s" % (p[0].lower(), p[2:])
    return p


def rel_err(a, b):
    if a == b:
        return 0.0
    if a is None or b is None:
        return float("inf")
    d = abs(a - b)
    s = max(abs(a), abs(b))
    return d / s if s > 0 else d


def abs_err(a, b):
    if a is None or b is None:
        return 0.0 if a is None and b is None else float("inf")
    return abs(a - b)


class Tally:
    def __init__(self, tol, kind):
        self.tol = tol
        self.kind = kind
        self.n = 0
        self.bit_exact = 0
        self.max_err = 0.0
        self.over = 0
        self.first_over = None

    def add(self, a, b, where):
        self.n += 1
        err = abs_err(a, b) if self.kind == "abs" else rel_err(a, b)
        if a == b:
            self.bit_exact += 1
        if err > self.max_err:
            self.max_err = err
        if not err <= self.tol:
            self.over += 1
            if self.first_over is None:
                self.first_over = {"where": where, "python": a, "go": b, "err": err}

    def ok(self):
        return self.over == 0

    def report(self):
        return {"n": self.n, "tolerance": self.tol, "error": self.kind,
                "max_error": self.max_err, "over_tolerance": self.over,
                "bit_exact": self.bit_exact, "first_over": self.first_over}


class Counter:
    def __init__(self):
        self.n = 0
        self.bad = 0
        self.first = None

    def add(self, same, where, a, b):
        self.n += 1
        if not same:
            self.bad += 1
            if self.first is None:
                self.first = {"where": where, "python": a, "go": b}

    def ok(self):
        return self.bad == 0

    def report(self):
        return {"n": self.n, "mismatches": self.bad, "first_mismatch": self.first}


def run_go(binary, payload_path):
    t0 = time.time()
    with open(payload_path, "rb") as f:
        r = subprocess.run([binary, "-mode", "policy3ref"], stdin=f,
                           capture_output=True, timeout=1800)
    dt = time.time() - t0
    if r.returncode != 0:
        raise RuntimeError("qamp -mode policy3ref exit %d: %s"
                           % (r.returncode, r.stderr.decode("utf-8", "replace")[-500:]))
    return json.loads(r.stdout.decode("utf-8")), dt


def compare_constants(ref, go):
    diffs = {}
    for k, v in ref.items():
        if k not in go:
            diffs[k] = {"python": v, "go": "missing"}
        elif go[k] != v:
            diffs[k] = {"python": v, "go": go[k]}
    for k in go:
        if k not in ref:
            diffs[k] = {"python": "missing", "go": go[k]}
    return diffs


def compare_primitives(ref, go):
    out = {"count_python": len(ref), "count_go": len(go)}
    ids = Counter()
    tallies = {f: Tally(J_TOL, "abs") for f in PRIM_FIELDS}
    exact = {f: Counter() for f in PRIM_EXACT}
    for i, (r, g) in enumerate(zip(ref, go)):
        ids.add(r["id"] == g["id"], i, r["id"], g["id"])
        for f in PRIM_FIELDS:
            tallies[f].add(r[f], g[f], {"id": r["id"], "field": f})
        for f in PRIM_EXACT:
            exact[f].add(r.get(f) == g.get(f), {"id": r["id"], "field": f}, r.get(f), g.get(f))
    out["ids"] = ids.report()
    out["fields"] = {f: t.report() for f, t in tallies.items()}
    out["exact"] = {f: c.report() for f, c in exact.items()}
    out["a_pre_positive"] = sum(1 for r in ref if (r.get("a_pre") or 0) > 0)
    out["pass"] = (len(ref) == len(go) and ids.ok()
                   and all(t.ok() for t in tallies.values())
                   and all(c.ok() for c in exact.values()))
    return out


def compare_decisions(ref, go):
    out = {"count_python": len(ref), "count_go": len(go)}
    exact = {f: Counter() for f in DEC_EXACT}
    close = {f: Tally(J_TOL, "abs") for f in DEC_CLOSE}
    errs = Counter()
    cand_order = Counter()
    cand_n2 = Counter()
    cand_ej = Tally(J_TOL, "abs")
    cand_pen = Tally(J_TOL, "abs")
    with_cands = 0
    with_pen = 0
    for r, g in zip(ref, go):
        where = {"id": r["id"]}
        errs.add(not g.get("err") and g["id"] == r["id"], where, r["id"], g.get("err"))
        if g.get("err"):
            continue
        if "pen" in r:
            with_pen += 1
        for f in DEC_EXACT:
            exact[f].add(r[f] == g.get(f), where, r[f], g.get(f))
        for f in DEC_CLOSE:
            close[f].add(r[f], g.get(f), where)
        if "cands" in r:
            with_cands += 1
            gc = g.get("cands") or []
            same = (len(gc) == len(r["cands"])
                    and all(a[:3] == b[:3] for a, b in zip(r["cands"], gc)))
            cand_order.add(same, where, len(r["cands"]), len(gc))
            if same:
                for a, b in zip(r["cands"], gc):
                    w = {"id": r["id"], "action": a[:3]}
                    cand_ej.add(a[3], b[3], w)
                    cand_n2.add(len(b) == len(a) and a[4] == b[4], w, a[4:5], b[4:5])
                    if len(b) == len(a):
                        cand_pen.add(a[5], b[5], w)
    out["errors"] = errs.report()
    out["with_penalties"] = with_pen
    out["exact"] = {f: c.report() for f, c in exact.items()}
    out["close"] = {f: t.report() for f, t in close.items()}
    out["candidate_lists"] = {"records": with_cands, "order": cand_order.report(),
                              "n2": cand_n2.report(), "ej": cand_ej.report(),
                              "pen": cand_pen.report()}
    out["pass"] = (len(ref) == len(go) and errs.ok()
                   and all(c.ok() for c in exact.values())
                   and all(t.ok() for t in close.values())
                   and cand_order.ok() and cand_n2.ok() and cand_ej.ok() and cand_pen.ok())
    return out


def compare_state(rs, gs, where, exact, post, guard):
    for f in STATE_EXACT:
        exact.add(rs.get(f) == gs.get(f), dict(where, field="state." + f), rs.get(f), gs.get(f))
    for j, (ra, ga) in enumerate(zip(rs["post"], gs["post"])):
        for i, (a, b) in enumerate(zip(ra, ga)):
            post.add(a, b, dict(where, field="state.post", h=j, g=i))
    for j, (a, b) in enumerate(zip(rs["w"], gs["w"])):
        post.add(a, b, dict(where, field="state.w", h=j))
    rr, gr = rs.get("g_resid") or {}, gs.get("g_resid") or {}
    shape_r = {k: len(v) for k, v in rr.items()}
    shape_g = {k: len(v) for k, v in gr.items()}
    exact.add(shape_r == shape_g, dict(where, field="state.g_resid shape"), shape_r, shape_g)
    if shape_r == shape_g:
        for k in sorted(rr):
            for i, (a, b) in enumerate(zip(rr[k], gr[k])):
                guard.add(a, b, dict(where, field="state.g_resid", key=k, i=i))
    rc, gc = rs.get("g_common"), gs.get("g_common")
    same_len = isinstance(rc, list) and isinstance(gc, list) and len(rc) == len(gc)
    exact.add(same_len, dict(where, field="state.g_common length"),
              None if rc is None else len(rc), None if gc is None else len(gc))
    if same_len:
        for i, (a, b) in enumerate(zip(rc, gc)):
            guard.add(a, b, dict(where, field="state.g_common", i=i))


def step_coverage(rs):
    skips = {}
    for s in rs["skip"]:
        if s is not None:
            skips[s] = skips.get(s, 0) + 1
    return {"reeval": sum(rs["reeval"]), "alarm_steps": sum(rs["alarm"]),
            "max_alarmed": max(rs["n_alarm"]) if rs["n_alarm"] else 0,
            "n2_steps": sum(1 for x in rs["n2"] if x == 1),
            "penalised_steps": sum(1 for x in rs["pen"] if x),
            "residuals": sum(1 for x in rs["resid"] if x is not None),
            "skips": dict(sorted(skips.items())), "updates": sum(rs["upd"])}


def compare_trajectory(r, g):
    out = {"id": r["id"]}
    if g.get("err"):
        out["error"] = g["err"]
        out["pass"] = False
        return out
    rs, gs = r["steps"], g["steps"]
    n = len(rs["a"])
    out["steps_python"] = n
    out["steps_go"] = len(gs["a"])
    out["coverage"] = step_coverage(rs)
    exact = {f: Counter() for f in STEP_EXACT}
    close = {f: Tally(J_TOL, "abs") for f in STEP_CLOSE}
    pmean = Tally(REL_TOL, "rel")
    lengths_ok = all(len(gs.get(f) or []) == n for f in STEP_EXACT + STEP_CLOSE + ("p_mean",))
    for t in range(min(n, len(gs["a"]))):
        for f in STEP_EXACT:
            gv = gs[f][t] if t < len(gs.get(f) or []) else "missing"
            exact[f].add(rs[f][t] == gv, t, rs[f][t], gv)
        for f in STEP_CLOSE:
            gv = gs[f][t] if t < len(gs.get(f) or []) else float("nan")
            close[f].add(rs[f][t], gv, t)
        pmean.add(rs["p_mean"][t], gs["p_mean"][t], t)
    snaps_exact = Counter()
    post = Tally(REL_TOL, "rel")
    guard = Tally(J_TOL, "abs")
    rsn, gsn = r["snapshots"], g["snapshots"]
    for sr, sg in zip(rsn, gsn):
        where = {"after_step": sr["after_step"]}
        for f in ("after_step", "k_hat", "S_hat", "n_need"):
            snaps_exact.add(sr[f] == sg[f], dict(where, field=f), sr[f], sg[f])
        for j, (ra, ga) in enumerate(zip(sr["post_h"], sg["post_h"])):
            for i, (a, b) in enumerate(zip(ra, ga)):
                post.add(a, b, dict(where, field="post_h", h=j, g=i))
        for j, (a, b) in enumerate(zip(sr["w"], sg["w"])):
            post.add(a, b, dict(where, field="w", h=j))
        for i, (a, b) in enumerate(zip(sr["combined"], sg["combined"])):
            post.add(a, b, dict(where, field="combined", g=i))
        post.add(sr["p_mean"], sg["p_mean"], dict(where, field="p_mean"))
        compare_state(sr["state"], sg["state"], where, snaps_exact, post, guard)
    out.update({"step_exact": {f: c.report() for f, c in exact.items()},
                "step_close": {f: t.report() for f, t in close.items()},
                "decisions": exact["a"].report(), "ej": close["ej"].report(),
                "step_p_mean": pmean.report(),
                "snapshots_python": len(rsn), "snapshots_go": len(gsn),
                "snapshot_exact": snaps_exact.report(), "posterior": post.report(),
                "guard_state": guard.report()})
    out["pass"] = (n == len(gs["a"]) and lengths_ok and len(rsn) == len(gsn) and len(rsn) > 0
                   and all(c.ok() for c in exact.values())
                   and all(t.ok() for t in close.values())
                   and pmean.ok() and snaps_exact.ok() and post.ok() and guard.ok())
    return out


def compare_trajectories(ref, go):
    out = {"count_python": len(ref), "count_go": len(go), "each": []}
    ok = len(ref) == len(go)
    for r, g in zip(ref, go):
        if r["id"] != g["id"]:
            out["each"].append({"id": r["id"], "go_id": g["id"], "pass": False})
            ok = False
            continue
        c = compare_trajectory(r, g)
        out["each"].append(c)
        ok = ok and c["pass"]
    out["pass"] = ok
    return out


def decision_coverage(decs, G):
    def vals(f):
        return sorted(set(d[f] for d in decs))
    point_g = sorted(set(d["g"][0] for d in decs if len(d["g"]) == 1))
    kinds = {}
    for d in decs:
        kinds[d["post_kind"]] = kinds.get(d["post_kind"], 0) + 1
    acts = set(tuple(d["action"]) for d in decs)
    nonlegacy = sum(1 for d in decs
                    if d["action"][1] != (1 if d["action"][1] + d["action"][2] >= 2 else 0))
    grid = set((d["k"], d["W"], d["cert"], d["s0_base"], d["rtt"], d["u"]) for d in decs)
    return {"n": len(decs), "k": vals("k"), "W": vals("W"), "cert": vals("cert"),
            "s0_base": vals("s0_base"), "rtt": vals("rtt"), "u": vals("u"),
            "distinct_contexts": len(grid), "post_kinds": dict(sorted(kinds.items())),
            "point_posterior_grid_points": len(point_g), "grid_points": len(G),
            "distinct_actions": len(acts), "tied_decisions": sum(1 for d in decs if d["n_tied"] > 1),
            "lead_not_legacy": nonlegacy,
            "modes": dict(sorted((m, sum(1 for d in decs if d["mode"] == m))
                                 for m in set(d["mode"] for d in decs))),
            "with_penalties": sum(1 for d in decs if "pen" in d),
            "penalised_choice": sum(1 for d in decs if d.get("pen_chosen")),
            "nominal2_choice": sum(1 for d in decs if d.get("n2")),
            "reeval_cond": sum(1 for d in decs if d.get("reeval_cond")),
            "no_alt": sum(1 for d in decs if d.get("alt") is None),
            "a_pre_positive": sum(1 for d in decs if (d.get("a_pre") or 0) > 0)}


def load_gen():
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    spec = importlib.util.spec_from_file_location("policy3_reference_gen", GEN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fresh_doc(n_dec, n_prim, seed, n_cliff=FRESH_CLIFF):
    gen = load_gen()
    from padfec import quantum
    from padfec3 import decide3, layout, learn3
    learn3.clear_model_cache()
    rng = random.Random(seed)
    prims = []
    for i in range(n_prim):
        k = rng.randint(1, layout.K_MAX)
        m = rng.randint(0, layout.M_MAX)
        lead = rng.randint(0, m)
        w_eff = rng.randint(1200, 1452)
        p = learn3.G[rng.randrange(len(learn3.G))] if rng.random() < 0.3 else rng.random() * 0.3
        rtt = rng.choice((10.0, 50.0, 200.0)) if rng.random() < 0.3 else 5.0 + rng.random() * 245.0
        u = 0.0 if rng.random() < 0.25 else rng.choice((2.0, 5.0, rng.random() * 120.0))
        n_need = rng.randint(1, 20)
        prims.append(gen.prim_rec(i, "random", k, w_eff, m, lead, p, rtt, u, n_need))
    crng = random.Random(FRESH_CLIFF_SEED)
    i = n_prim
    while i < n_prim + n_cliff:
        k = crng.randint(1, layout.K_MAX)
        m = crng.randint(0, layout.M_MAX)
        lead = crng.randint(0, m)
        n_need = crng.randint(2, 24)
        u = crng.choice((0.0, 1.0, 5.0, 50.0, crng.random() * 120.0))
        a_max = layout.PREFLIGHT_ACK_BYTES * (k - 1)
        edge = quantum.P_SERVER * (n_need - 1)
        ws = [w for w in range(1200, 1453)
              if -30 <= 3 * layout.pre_decision_bytes(k, m, lead, w) - edge <= a_max + 30]
        if not ws:
            continue
        w_eff = ws[crng.randrange(len(ws))]
        p = 0.0 if crng.random() < 0.4 else crng.random() * 0.3
        rtt = 5.0 + crng.random() * 195.0
        prims.append(gen.prim_rec(i, "cliff", k, w_eff, m, lead, p, rtt, u, n_need))
        i += 1
    prng = random.Random(FRESH_PEN_SEED)
    decs = []
    for i in range(n_dec):
        k = rng.choice(gen.KS)
        w = rng.choice(gen.WS)
        cert = rng.choice(gen.CERTS)
        s0 = rng.choice(gen.S0S)
        rtt = rng.choice(gen.RTTS)
        u = rng.choice(gen.US)
        kind = gen.draw_kind(rng)
        gs, qs = gen.draw_post(rng, kind)
        S = gen.synth_s(cert, s0, k, w)
        post = gen.dense(gs, qs)
        pen = None
        if i % gen.PEN_EVERY == gen.PEN_PHASE:
            r0 = decide3.decide_core(post, k, w, S, u, rtt, gen.C_PKT, keep_cands=True)
            pen = gen.draw_pen(prng, r0["cands"], r0["action"])
        r = decide3.decide_core(post, k, w, S, u, rtt, gen.C_PKT, keep_cands=True,
                                pen=None if pen is None else gen.pen_map(pen))
        alt = r["alt"]
        rec = {"id": i, "k": k, "W": w, "cert": cert, "s0_base": s0, "S": S, "rtt": rtt,
               "u": u, "a_pre": layout.preflight_bytes(k, u), "post_kind": kind, "g": gs,
               "q": qs, "n_need": r["n_need"],
               "n_cands": r["n_cands"], "cand_hash": decide3.cand_hash(r["cands"]),
               "action": list(r["action"]), "mode": r["mode"], "ej": r["ej"],
               "pen_chosen": r["pen"], "score": r["score"], "n2": r["n2"],
               "jmin": r["jmin"], "n_tied": r["n_tied"], "reeval_cond": r["reeval_cond"],
               "alt": None if alt is None else list(alt["action"]),
               "alt_ej": None if alt is None else alt["ej"],
               "alt_score": None if alt is None else alt["score"]}
        if pen is not None:
            rec["pen"] = pen
        if i % gen.DEBUG_EVERY == 0 or pen is not None:
            rec["cands"] = [[c["delta"], c["lead"], c["T"], c["ej"], 1 if c["n2"] else 0,
                             c["pen"]] for c in r["cands"]]
        decs.append(rec)
        if learn3.model_cache_size() > 300000:
            learn3.clear_model_cache()
    learn3.clear_model_cache()
    trajs = [gen.gen_trajectory(spec) for spec in FRESH_TRAJ]
    return {"primitives": prims, "decisions": decs, "trajectories": trajs}


def binary_report(path):
    rep = {"path": path, "exists": os.path.isfile(path)}
    problems = []
    if not rep["exists"]:
        problems.append("binary missing: %s (build with bash experiments/quicbed/%s)"
                        % (path, GENCONFIG["build_script"]))
        return rep, problems
    rep["sha256"] = sha256_file(path)
    rep["sha256_file"] = (read_text(path + ".sha256") or "").split(" ")[0] or None
    rep["srcsha"] = read_text(path + ".srcsha")
    rep["source_fingerprint_now"] = quicbed_fingerprint()
    if rep["sha256"] == G2_FROZEN_SHA256:
        problems.append("binary is the frozen gen-2 qamp")
    if rep["sha256_file"] != rep["sha256"]:
        problems.append("binary does not match its qamp.sha256")
    if rep["srcsha"] != rep["source_fingerprint_now"]:
        problems.append("binary srcsha %s is not the current experiments/quicbed fingerprint %s"
                        % (rep["srcsha"], rep["source_fingerprint_now"]))
    return rep, problems


def reference_report(path, doc):
    rep = {"path": os.path.relpath(path, ROOT).replace("\\", "/"), "sha256": sha256_file(path),
           "schema": doc.get("schema"), "seeds": doc.get("seeds"), "sources": {}}
    problems = []
    for rel, want in sorted(doc.get("sources_sha256", {}).items()):
        p = os.path.join(ROOT, rel)
        now = sha256_file(p) if os.path.isfile(p) else None
        rep["sources"][rel] = {"recorded": want, "now": now, "same": now == want}
        if now != want:
            problems.append("reference is stale: %s changed since it was generated "
                            "(run python -B g3/policy3_reference_gen.py)" % rel)
    if not rep["sources"]:
        problems.append("reference has no sources_sha256")
    return rep, problems


def print_traj(t):
    if "posterior" not in t:
        print("  %s: %s" % (t["id"], t.get("error", "no comparison")))
        return
    cov = t["coverage"]
    print("  %s: decisions %d/%d match, posterior max rel %.3g (bit-exact %d/%d), guard state "
          "max abs %.3g (bit-exact %d/%d); reeval %d, alarm steps %d, skips %s"
          % (t["id"], t["decisions"]["n"] - t["decisions"]["mismatches"],
             t["decisions"]["n"], t["posterior"]["max_error"],
             t["posterior"]["bit_exact"], t["posterior"]["n"],
             t["guard_state"]["max_error"], t["guard_state"]["bit_exact"],
             t["guard_state"]["n"], cov["reeval"], cov["alarm_steps"], cov["skips"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Go policy3 vs Python learn3/decide3 parity gate")
    ap.add_argument("--bin", default=BIN_DEFAULT)
    ap.add_argument("--ref", default=REF_DEFAULT)
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--fresh-decisions", type=int, default=FRESH_DECISIONS)
    ap.add_argument("--fresh-primitives", type=int, default=FRESH_PRIMITIVES)
    ap.add_argument("--fresh-seed", type=int, default=FRESH_SEED)
    ap.add_argument("--no-fresh", action="store_true")
    a = ap.parse_args(argv)
    if os.path.isdir(a.out):
        ap.error("--out must be a file path, not a directory")
    if not sys.platform.startswith("linux"):
        cmd = ["wsl", "-d", "Ubuntu", "--", "python3", "-I", "-B", to_wsl(__file__)] + list(
            argv if argv is not None else sys.argv[1:])
        print("re-running inside WSL: %s" % " ".join(cmd))
        return subprocess.call(cmd)
    t0 = time.time()
    problems = []
    res = {"schema": SCHEMA, "started_utc": utc_now(),
           "label": ("deterministic cross-language parity check of experiments/quicbed/policy3.go "
                     "(policy " + POLICY_VERSION + ") against padfec3/learn3.py + decide3.py + layout.py; "
                     "no network, no measurement data"),
           "verdict": "C:/dev/codex_handoff/state/evo/verdict_v3.md section 3 C",
           "criteria": {"primitive": "a_pre identical; J, e, p_two_rtt, p_fail, p_one_rtt "
                                     "abs <= 1e-9",
                        "decision": "action, mode, n_need, n_cands, cand_hash, n_tied, n2, "
                                    "reeval_cond, alt identical; ej, jmin, score, pen_chosen, "
                                    "alt_ej, alt_score abs <= 1e-9; candidate order and n2 "
                                    "identical, candidate ej and pen abs <= 1e-9",
                        "j_abs_tol_ms": J_TOL, "posterior_rel_tol": REL_TOL,
                        "trajectory": "every step: action, why, y, updated, n2, reeval, alarm, "
                                      "n_alarm, skip identical; ej, pen, common, resid abs <= "
                                      "1e-9; step p_mean rel <= 1e-12; snapshots: post_h, w, "
                                      "combined, state.post, state.w rel <= 1e-12; state.g_resid "
                                      "and state.g_common abs <= 1e-9 with identical shape; "
                                      "windows, counters, n_dec, n_reeval, g_alarm identical"},
           "host": {"python": sys.version.split()[0], "platform": platform.platform()}}
    binrep, bp = binary_report(a.bin)
    res["binary"] = binrep
    problems += bp
    with open(a.ref, encoding="utf-8") as f:
        ref = json.load(f)
    refrep, rp = reference_report(a.ref, ref)
    res["reference"] = refrep
    problems += rp
    res["coverage_reference"] = decision_coverage(ref["decisions"], ref["constants"]["G"])
    if ref["constants"].get("policy_version") != POLICY_VERSION:
        problems.append("reference policy_version %r, want %r"
                        % (ref["constants"].get("policy_version"), POLICY_VERSION))
    sections = {}
    if binrep["exists"]:
        go, dt = run_go(a.bin, a.ref)
        res["go_timing_s"] = {"wall": dt, "inner": go.get("timing_s")}
        cdiff = compare_constants(ref["constants"], go["constants"])
        res["constants"] = {"pass": not cdiff, "differences": cdiff}
        sections["constants"] = not cdiff
        res["primitives"] = compare_primitives(ref["primitives"], go["primitives"])
        res["decisions"] = compare_decisions(ref["decisions"], go["decisions"])
        res["trajectories"] = compare_trajectories(ref["trajectories"], go["trajectories"])
        for k in ("primitives", "decisions", "trajectories"):
            sections[k] = res[k]["pass"]
        if not a.no_fresh:
            tf = time.time()
            fresh = fresh_doc(a.fresh_decisions, a.fresh_primitives, a.fresh_seed)
            tp = time.time() - tf
            artifact_dir = os.path.dirname(os.path.abspath(a.out))
            os.makedirs(artifact_dir, exist_ok=True)
            fpath = os.path.join(artifact_dir, "gate_v3_fresh_%d_%d.json" % (os.getpid(), time.time_ns()))
            with open(fpath, "x", encoding="utf-8", newline="\n") as f:
                json.dump(fresh, f)
            res["fresh_input"] = {"path": fpath, "sha256": sha256_file(fpath), "preserved": True}
            gof, dtf = run_go(a.bin, fpath)
            fr = {"seed": a.fresh_seed, "python_s": tp, "go_wall_s": dtf,
                  "coverage": decision_coverage(fresh["decisions"], ref["constants"]["G"]),
                  "primitives": compare_primitives(fresh["primitives"], gof["primitives"]),
                  "decisions": compare_decisions(fresh["decisions"], gof["decisions"]),
                  "trajectories": compare_trajectories(fresh["trajectories"],
                                                       gof["trajectories"])}
            fr["trajectory_specs"] = FRESH_TRAJ
            fr["pass"] = (fr["primitives"]["pass"] and fr["decisions"]["pass"]
                          and fr["trajectories"]["pass"])
            res["fresh"] = fr
            sections["fresh"] = fr["pass"]
    if binrep["exists"]:
        if "fresh" not in sections:
            problems.append("fresh seeded sample skipped (--no-fresh); verdict 3C needs it")
        elif (res["fresh"]["decisions"]["count_python"] < FRESH_DECISIONS
              or res["fresh"]["primitives"]["count_python"] < FRESH_PRIMITIVES):
            problems.append("fresh sample smaller than %d decisions and %d primitives"
                            % (FRESH_DECISIONS, FRESH_PRIMITIVES))
    res["sections"] = sections
    res["problems"] = problems
    res["pass"] = bool(sections) and all(sections.values()) and not problems
    res["elapsed_s"] = time.time() - t0
    res["finished_utc"] = utc_now()
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    tmp = a.out + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, a.out)
    print("gate_v3_parity: %s  (%s)" % ("PASS" if res["pass"] else "FAIL",
                                       ", ".join("%s=%s" % kv for kv in sections.items())))
    for p in problems:
        print("  problem:", p)
    if "decisions" in res:
        d = res["decisions"]
        print("  reference: primitives %d, decisions %d (actions %d, tied %d), trajectories %d"
              % (res["primitives"]["count_python"], d["count_python"],
                 res["coverage_reference"]["distinct_actions"],
                 res["coverage_reference"]["tied_decisions"],
                 res["trajectories"]["count_python"]))
        print("  max |dJ| primitives %.3g, decisions ej %.3g; bit-exact ej %d/%d"
              % (max(v["max_error"] for v in res["primitives"]["fields"].values()),
                 d["close"]["ej"]["max_error"], d["close"]["ej"]["bit_exact"],
                 d["close"]["ej"]["n"]))
        print("  decision exact fields: %s"
              % ", ".join("%s %d/%d" % (f, c["n"] - c["mismatches"], c["n"])
                          for f, c in d["exact"].items()))
        print("  reference coverage: penalised %d, nominal-2 choice %d, reeval_cond %d, "
              "a_pre>0 %d decisions, %d primitives"
              % (res["coverage_reference"]["with_penalties"],
                 res["coverage_reference"]["nominal2_choice"],
                 res["coverage_reference"]["reeval_cond"],
                 res["coverage_reference"]["a_pre_positive"],
                 res["primitives"]["a_pre_positive"]))
        for t in res["trajectories"]["each"]:
            print_traj(t)
    if "fresh" in res:
        fr = res["fresh"]
        print("  fresh seed %d: primitives %s (n %d), decisions %s (n %d, penalised %d, "
              "max |dJ| %.3g), trajectories %s"
              % (fr["seed"], fr["primitives"]["pass"], fr["primitives"]["count_python"],
                 fr["decisions"]["pass"], fr["decisions"]["count_python"],
                 fr["decisions"]["with_penalties"], fr["decisions"]["close"]["ej"]["max_error"],
                 fr["trajectories"]["pass"]))
        for t in fr["trajectories"]["each"]:
            print_traj(t)
    print("wrote %s" % a.out)
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
