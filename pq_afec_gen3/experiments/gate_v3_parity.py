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
QUICBED = os.path.join(HERE, "quicbed")
REF_DEFAULT = os.path.join(ROOT, "g3", "policy3_reference.json")
GEN_PATH = os.path.join(ROOT, "g3", "policy3_reference_gen.py")
OUT_DEFAULT = os.path.join(HERE, "results", "gate_v3_parity.json")
BIN_DEFAULT = os.path.expanduser("~/quicbed_g3b/bin/qamp")
G2_FROZEN_SHA256 = "d98b05d73f44774ad622ab1c4993526cac58957b22310fc61122d7bd44964213"
SCHEMA = "padfec3.gate_v3_parity/1"
J_TOL = 1e-9
REL_TOL = 1e-12
FRESH_SEED = 20261005
FRESH_DECISIONS = 5000
FRESH_PRIMITIVES = 2000
FRESH_TRAJ = (
    {"id": "F1_cert12000_k3", "seed": 35, "cert": 12000, "s0_base": 1472.0, "k": 3,
     "W": 1350, "u": 5.0, "rtt_true": 100.0, "schedule": [[0.01, 300], [0.08, 300]]},
    {"id": "F2_cert6000_rtt20", "seed": 36, "cert": 6000, "s0_base": 1472.0, "k": 2,
     "W": 1280, "u": 1.0, "rtt_true": 20.0, "schedule": [[0.0, 400], [0.12, 200]]},
)
PRIM_FIELDS = ("J", "e", "p_two_rtt", "p_fail", "p_one_rtt")
DEC_EXACT = ("action", "mode", "n_need", "n_cands", "cand_hash", "n_tied")
DEC_CLOSE = ("ej", "jmin")
STATE_EXACT = ("v", "k_hist", "S_hist", "hct", "hct_seq", "seq", "stats")


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
                  if n.endswith(".go") or n in ("build.sh", "go.mod", "go.sum")]
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
    for i, (r, g) in enumerate(zip(ref, go)):
        ids.add(r["id"] == g["id"], i, r["id"], g["id"])
        for f in PRIM_FIELDS:
            tallies[f].add(r[f], g[f], {"id": r["id"], "field": f})
    out["ids"] = ids.report()
    out["fields"] = {f: t.report() for f, t in tallies.items()}
    out["pass"] = (len(ref) == len(go) and ids.ok()
                   and all(t.ok() for t in tallies.values()))
    return out


def compare_decisions(ref, go):
    out = {"count_python": len(ref), "count_go": len(go)}
    exact = {f: Counter() for f in DEC_EXACT}
    close = {f: Tally(J_TOL, "abs") for f in DEC_CLOSE}
    errs = Counter()
    cand_order = Counter()
    cand_ej = Tally(J_TOL, "abs")
    with_cands = 0
    for r, g in zip(ref, go):
        where = {"id": r["id"]}
        errs.add(not g.get("err") and g["id"] == r["id"], where, r["id"], g.get("err"))
        if g.get("err"):
            continue
        for f in DEC_EXACT:
            exact[f].add(r[f] == g[f], where, r[f], g[f])
        for f in DEC_CLOSE:
            close[f].add(r[f], g[f], where)
        if "cands" in r:
            with_cands += 1
            gc = g.get("cands") or []
            same = (len(gc) == len(r["cands"])
                    and all(a[:3] == b[:3] for a, b in zip(r["cands"], gc)))
            cand_order.add(same, where, len(r["cands"]), len(gc))
            if same:
                for a, b in zip(r["cands"], gc):
                    cand_ej.add(a[3], b[3], {"id": r["id"], "action": a[:3]})
    out["errors"] = errs.report()
    out["exact"] = {f: c.report() for f, c in exact.items()}
    out["close"] = {f: t.report() for f, t in close.items()}
    out["candidate_lists"] = {"records": with_cands, "order": cand_order.report(),
                              "ej": cand_ej.report()}
    out["pass"] = (len(ref) == len(go) and errs.ok()
                   and all(c.ok() for c in exact.values())
                   and all(t.ok() for t in close.values())
                   and cand_order.ok() and cand_ej.ok())
    return out


def compare_state(rs, gs, where, exact, post):
    for f in STATE_EXACT:
        exact.add(rs.get(f) == gs.get(f), dict(where, field="state." + f), rs.get(f), gs.get(f))
    for j, (ra, ga) in enumerate(zip(rs["post"], gs["post"])):
        for i, (a, b) in enumerate(zip(ra, ga)):
            post.add(a, b, dict(where, field="state.post", h=j, g=i))
    for j, (a, b) in enumerate(zip(rs["w"], gs["w"])):
        post.add(a, b, dict(where, field="state.w", h=j))


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
    decisions = Counter()
    why = Counter()
    ys = Counter()
    upd = Counter()
    ej = Tally(J_TOL, "abs")
    pmean = Tally(REL_TOL, "rel")
    for t in range(min(n, len(gs["a"]))):
        decisions.add(rs["a"][t] == gs["a"][t], t, rs["a"][t], gs["a"][t])
        why.add(rs["why"][t] == gs["why"][t], t, rs["why"][t], gs["why"][t])
        ys.add(rs["y"][t] == gs["y"][t], t, rs["y"][t], gs["y"][t])
        upd.add(rs["upd"][t] == gs["upd"][t], t, rs["upd"][t], gs["upd"][t])
        ej.add(rs["ej"][t], gs["ej"][t], t)
        pmean.add(rs["p_mean"][t], gs["p_mean"][t], t)
    snaps_exact = Counter()
    post = Tally(REL_TOL, "rel")
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
        compare_state(sr["state"], sg["state"], where, snaps_exact, post)
    out.update({"decisions": decisions.report(), "why": why.report(), "y": ys.report(),
                "updated": upd.report(), "ej": ej.report(), "step_p_mean": pmean.report(),
                "snapshots_python": len(rsn), "snapshots_go": len(gsn),
                "snapshot_exact": snaps_exact.report(), "posterior": post.report()})
    out["pass"] = (n == len(gs["a"]) and len(rsn) == len(gsn) and len(rsn) > 0
                   and decisions.ok() and why.ok() and ys.ok() and upd.ok() and ej.ok()
                   and pmean.ok() and snaps_exact.ok() and post.ok())
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
                                 for m in set(d["mode"] for d in decs)))}


def load_gen():
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    spec = importlib.util.spec_from_file_location("policy3_reference_gen", GEN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fresh_doc(n_dec, n_prim, seed):
    gen = load_gen()
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
        ev = layout.evaluate(k, w_eff, m, lead, p, rtt, u, n_need, "v3")
        prims.append({"id": i, "k": k, "W_eff": w_eff, "m": m, "lead": lead, "p": p,
                      "rtt": rtt, "u": u, "n_need": n_need, "J": ev["J"], "e": ev["e"],
                      "p_two_rtt": ev["p_two_rtt"], "p_fail": ev["p_fail"],
                      "p_one_rtt": ev["p_one_rtt"]})
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
        r = decide3.decide_core(gen.dense(gs, qs), k, w, S, u, rtt, gen.C_PKT,
                                keep_cands=True)
        rec = {"id": i, "k": k, "W": w, "cert": cert, "s0_base": s0, "S": S, "rtt": rtt,
               "u": u, "post_kind": kind, "g": gs, "q": qs, "n_need": r["n_need"],
               "n_cands": r["n_cands"], "cand_hash": decide3.cand_hash(r["cands"]),
               "action": list(r["action"]), "mode": r["mode"], "ej": r["ej"],
               "jmin": r["jmin"], "n_tied": r["n_tied"]}
        if i % gen.DEBUG_EVERY == 0:
            rec["cands"] = [[c["delta"], c["lead"], c["T"], c["ej"]] for c in r["cands"]]
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
        problems.append("binary missing: %s (build with bash experiments/quicbed/build_g3b.sh)"
                        % path)
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
    if not sys.platform.startswith("linux"):
        cmd = ["wsl", "-d", "Ubuntu", "--", "python3", "-B", to_wsl(__file__)] + list(
            argv if argv is not None else sys.argv[1:])
        print("re-running inside WSL: %s" % " ".join(cmd))
        return subprocess.call(cmd)
    t0 = time.time()
    problems = []
    res = {"schema": SCHEMA, "started_utc": utc_now(),
           "label": ("deterministic cross-language parity check of experiments/quicbed/policy3.go "
                     "against padfec3/learn3.py + decide3.py + layout.py; no network, "
                     "no measurement data"),
           "verdict": "C:/dev/codex_handoff/state/evo/verdict_v3.md section 3 C",
           "criteria": {"decision": "action, mode, n_need, n_cands, cand_hash, n_tied identical",
                        "j_abs_tol_ms": J_TOL, "posterior_rel_tol": REL_TOL,
                        "trajectory": "every step: action, why, y, updated identical; ej abs <= "
                                      "1e-9; step p_mean rel <= 1e-12; snapshots: post_h, w, "
                                      "combined, state.post, state.w rel <= 1e-12, windows and "
                                      "counters identical"},
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
            fpath = os.path.join("/tmp", "gate_v3_fresh_%d.json" % os.getpid())
            with open(fpath, "w", encoding="utf-8", newline="\n") as f:
                json.dump(fresh, f)
            try:
                gof, dtf = run_go(a.bin, fpath)
            finally:
                os.unlink(fpath)
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
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
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
        for t in res["trajectories"]["each"]:
            if "posterior" in t:
                print("  %s: decisions %d/%d match, posterior max rel %.3g, bit-exact %d/%d"
                      % (t["id"], t["decisions"]["n"] - t["decisions"]["mismatches"],
                         t["decisions"]["n"], t["posterior"]["max_error"],
                         t["posterior"]["bit_exact"], t["posterior"]["n"]))
    if "fresh" in res:
        fr = res["fresh"]
        print("  fresh seed %d: primitives %s, decisions %s (n %d, max |dJ| %.3g), "
              "trajectories %s"
              % (fr["seed"], fr["primitives"]["pass"], fr["decisions"]["pass"],
                 fr["decisions"]["count_python"], fr["decisions"]["close"]["ej"]["max_error"],
                 fr["trajectories"]["pass"]))
    print("wrote %s" % a.out)
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
