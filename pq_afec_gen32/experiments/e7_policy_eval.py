import argparse
import hashlib
import json
import multiprocessing as mp
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RESULTS = os.path.join(HERE, "results")
TRACES = os.path.join(HERE, "traces")
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from _journal import Journal, code_fingerprint
from afec import FecConfig, LossTrace, profile
from afec.sim import (expected_handshake_ms, simulate_data,
                      simulate_handshake)


def _harden():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


def load_trace(name, n):
    path = os.path.join(TRACES, name + ".mask")
    with open(path, "rb") as f:
        bm = f.read()
    return LossTrace(bm, n, label=name)


def mean_se(xs):
    if not xs:
        return 0.0, 0.0
    m = statistics.mean(xs)
    se = statistics.stdev(xs) / (len(xs) ** 0.5) if len(xs) > 1 else 0.0
    return m, se


def eval_trace(tr, meas, cfg, rtt, n_blocks, seeds, wrong_factor):
    p, L = meas["loss_rate"], max(meas["mean_burst"], 1.0)
    wrong_hi = (min(p * wrong_factor, 0.5), L, 100.0)
    wrong_lo = (max(p / wrong_factor, 1e-4), L, 100.0)

    plans = [
        ("none", dict(policy="none")),
        ("static", dict(policy="static")),
        ("rquic", dict(policy="rquic")),
        ("adaptive", dict(policy="adaptive")),
        ("cached_ok", dict(policy="cached", prior=(p, L, 100.0))),
        ("cached_hi", dict(policy="cached", prior=wrong_hi)),
        ("cached_lo", dict(policy="cached", prior=wrong_lo)),
        ("oracle", dict(policy="oracle")),
    ]
    per = {}
    for label, kw in plans:
        rows = []
        for s in range(seeds):
            r = simulate_data(p=p, burst=L, rtt_ms=rtt, cfg=cfg,
                              n_blocks=n_blocks, seed=1000 + s, trace=tr, **kw)
            rows.append(r)
        per[label] = {
            "total_ms": mean_se([r.total_ms for r in rows]),
            "goodput_mbps": mean_se([r.goodput_mbps for r in rows]),
            "overhead": mean_se([r.overhead for r in rows]),
            "block_fail_rate": mean_se([r.block_fail_rate for r in rows]),
            "recovery_rate": mean_se([1.0 - r.block_fail_rate for r in rows]),
            "mean_r": mean_se([r.mean_r for r in rows]),
        }
    base = per["oracle"]["total_ms"][0]
    for label in per:
        per[label]["regret"] = (per[label]["total_ms"][0] - base) / base if base else 0.0
    return per


_CTX = {}


def _init_worker(e6, cfg_kw, rtt, seeds, wrong_factor, nblocks, trials):
    _CTX["e6"] = e6
    _CTX["cfg"] = FecConfig(**cfg_kw)
    _CTX["rtt"] = rtt
    _CTX["seeds"] = seeds
    _CTX["wrong"] = wrong_factor
    _CTX["nblocks"] = nblocks
    _CTX["trials"] = trials
    _harden()


def _job_policy(args):
    span, name = args
    e6 = _CTX["e6"]
    meas = e6["configs"][name]
    tr = load_trace(name, e6["n"])
    per = eval_trace(tr, meas, _CTX["cfg"], _CTX["rtt"],
                     _CTX["nblocks"][span], _CTX["seeds"], _CTX["wrong"])
    return span, name, meas["loss_rate"], meas["mean_burst"], per


def _job_handshake(name):
    e6 = _CTX["e6"]
    meas = e6["configs"][name]
    tr = load_trace(name, e6["n"])
    p = meas["loss_rate"]
    L = max(meas["mean_burst"], 1.0)
    rtt = _CTX["rtt"]
    trials = _CTX["trials"]
    base_p = profile(None)
    mk = profile(768)
    a1 = simulate_handshake(base_p.k_client, base_p.k_server, 0, 0, p, L, rtt,
                            trials=trials, seed=5, trace=tr)
    a2 = simulate_handshake(mk.k_client, mk.k_server, 0, 0, p, L, rtt,
                            trials=trials, seed=5, trace=tr)
    a3 = simulate_handshake(mk.k_client, mk.k_server, 1, 1, p, L, rtt,
                            trials=trials, seed=5, trace=tr)
    gain = (a3.mean_ms - a2.mean_ms) / a2.mean_ms if a2.mean_ms else 0.0

    def d(x):
        return {"mean_ms": x.mean_ms, "p95_ms": x.p95_ms,
                "stall_rate": x.stall_rate}
    return {"name": name, "p": p, "L": L, "x25519": d(a1), "mlkem": d(a2),
            "mlkem_fec": d(a3), "fec_gain": gain}


def main():
    _harden()
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=32)
    ap.add_argument("--rtt", type=float, default=40.0)
    ap.add_argument("--rate-mbps", type=float, default=50.0)
    ap.add_argument("--budget-ms", type=float, default=20.0)
    ap.add_argument("--wrong-factor", type=float, default=5.0)
    ap.add_argument("--long-blocks", type=int, default=400)
    ap.add_argument("--short-blocks", type=int, default=30)
    ap.add_argument("--trials", type=int, default=20000)
    ap.add_argument("--procs", type=int, default=0)
    a = ap.parse_args()

    with open(os.path.join(RESULTS, "e6_netem.json"), encoding="utf-8") as f:
        e6 = json.load(f)
    n = e6["n"]

    names = [k for k in e6["configs"] if e6["configs"][k]["lost"] > 0]
    print("=" * 96)
    print("E7 - policy evaluation on %d measured netem traces (%d seeds each)"
          % (len(names), a.seeds))
    print("=" * 96)

    out = {"seeds": a.seeds, "rtt_ms": a.rtt, "rate_mbps": a.rate_mbps,
           "n_trace": n, "long": {}, "short": {}}
    labels = ["none", "static", "rquic", "adaptive",
              "cached_ok", "cached_hi", "cached_lo"]
    nblocks = {"long": a.long_blocks, "short": a.short_blocks}
    cfg_kw = dict(rate_bps=a.rate_mbps * 1e6, delay_budget_ms=a.budget_ms)

    fp = hashlib.sha256(json.dumps(
        {"seeds": a.seeds, "rtt": a.rtt, "rate": a.rate_mbps,
         "budget": a.budget_ms, "wrong": a.wrong_factor,
         "long": a.long_blocks, "short": a.short_blocks,
         "trials": a.trials, "n": n,
         "code": code_fingerprint(
             ["afec/sim.py", "afec/controller.py", "afec/estimator.py",
              "afec/channel.py", "afec/cache.py"], root=ROOT)},
        sort_keys=True).encode()).hexdigest()[:16]
    jr = Journal(os.path.join(HERE, "state", "e7_units.jsonl"), fingerprint=fp)

    all_jobs = [(span, nm) for span in ("long", "short") for nm in names]
    todo = [j for j in all_jobs if not jr.has("pol/%s/%s" % (j[0], j[1]))]
    hs_todo = [nm for nm in names if not jr.has("hs/%s" % nm)]
    if len(jr):
        print("재개: 정책 %d/%d, 핸드셰이크 %d/%d 이미 완료"
              % (len(all_jobs) - len(todo), len(all_jobs),
                 len(names) - len(hs_todo), len(names)))

    nproc = min(a.procs or (os.cpu_count() or 4), max(len(todo) + len(hs_todo), 1))
    if todo or hs_todo:
        print("남은 작업 %d개를 프로세스 %d개로 분산"
              % (len(todo) + len(hs_todo), nproc))
        init_args = (e6, cfg_kw, a.rtt, a.seeds, a.wrong_factor, nblocks, a.trials)
        with mp.Pool(nproc, initializer=_init_worker, initargs=init_args) as pool:
            if todo:
                for span, name, loss, burst, per in pool.imap_unordered(
                        _job_policy, todo):
                    jr.record("pol/%s/%s" % (span, name),
                              {"measured_loss": loss, "measured_burst": burst,
                               "policies": per})
                    print("   [기록] %s/%s" % (span, name))
            if hs_todo:
                for row in pool.imap_unordered(_job_handshake, hs_todo):
                    jr.record("hs/%s" % row["name"], row)
                    print("   [기록] handshake/%s" % row["name"])
    else:
        print("모든 작업이 저널에 있다 - 계산 없이 결과만 조립한다")

    for span in ("long", "short"):
        for name in names:
            rec = jr.get("pol/%s/%s" % (span, name))
            if rec is not None:
                out[span][name] = rec
    names = [nm for nm in names if nm in out["long"] and nm in out["short"]]
    hs_rows = [jr.get("hs/%s" % nm) for nm in names if jr.has("hs/%s" % nm)]

    for span in ("long", "short"):
        print("")
        print("### %s connections (%d blocks)" % (span, nblocks[span]))
        print("%-14s %7s %6s | %s" % ("trace", "loss", "burst",
                                      "regret vs oracle (%)"))
        print("%-14s %7s %6s | %s" % ("", "", "",
                                      " ".join("%9s" % l for l in labels)))
        print("-" * 96)
        for name in names:
            row = out[span][name]
            per = row["policies"]
            print("%-14s %7.4f %6.2f | %s"
                  % (name, row["measured_loss"], row["measured_burst"],
                     " ".join("%8.1f%%" % (per[l]["regret"] * 100) for l in labels)))
        print("-" * 96)
        worst = {l: max(out[span][nm]["policies"][l]["regret"] for nm in names)
                 for l in labels}
        out[span + "_worst_regret"] = worst
        print("%-14s %7s %6s | %s" % ("WORST CASE", "", "",
                                      " ".join("%8.1f%%" % (worst[l] * 100)
                                               for l in labels)))

    print("")
    print("### handshake completion time on measured traces (%d trials)" % a.trials)
    print("%-14s %7s %6s | %9s %9s %9s %8s %8s" %
          ("trace", "loss", "burst", "x25519", "ML-KEM", "+FEC", "gain", "stall"))
    print("-" * 96)
    hs = {}
    for row in hs_rows:
        if not row:
            continue
        name = row["name"]
        hs[name] = {k: row[k] for k in
                    ("x25519", "mlkem", "mlkem_fec", "fec_gain")}
        print("%-14s %7.4f %6.2f | %8.1fms %8.1fms %8.1fms %7.1f%% %7.1f%%"
              % (name, row["p"], row["L"], row["x25519"]["mean_ms"],
                 row["mlkem"]["mean_ms"], row["mlkem_fec"]["mean_ms"],
                 row["fec_gain"] * 100, row["mlkem"]["stall_rate"] * 100))
    out["handshake"] = hs

    path = os.path.join(RESULTS, "e7_policy.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("")
    print("saved: %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
