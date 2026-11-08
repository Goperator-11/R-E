import argparse
import json
import math
import multiprocessing as mp
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RESULTS = os.path.join(HERE, "results")
TRACES = os.path.join(HERE, "traces")
sys.path.insert(0, ROOT)

from afec.channel import GilbertElliott

GRID = [(32, 0), (32, 2), (32, 4), (32, 8), (32, 16),
        (16, 2), (16, 4), (64, 8), (64, 16)]


def _harden():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


def load_mask_bits(name, n):
    with open(os.path.join(TRACES, name + ".mask"), "rb") as f:
        bm = f.read()
    return bm


def empirical_p_fail(bm, n, k, r, stride):
    win = k + r
    blocks = 0
    failed = 0
    losses_hist = {}
    i = 0
    while i + win <= n:
        lost = 0
        for t in range(i, i + win):
            if not ((bm[t >> 3] >> (t & 7)) & 1):
                lost += 1
        blocks += 1
        if lost > r:
            failed += 1
        losses_hist[lost] = losses_hist.get(lost, 0) + 1
        i += stride
    return blocks, failed, losses_hist


def binomial_p_fail(p, k, r):
    n = k + r
    acc = 0.0
    for i in range(r + 1, n + 1):
        acc += math.comb(n, i) * (p ** i) * ((1 - p) ** (n - i))
    return acc


def wilson(fail, total, z=1.96):
    if total == 0:
        return (0.0, 0.0)
    ph = fail / total
    d = 1 + z * z / total
    c = ph + z * z / (2 * total)
    s = z * math.sqrt(ph * (1 - ph) / total + z * z / (4 * total * total))
    return ((c - s) / d, (c + s) / d)


_CTX = {}


def _init(n):
    _CTX["n"] = n
    _harden()


def _job(args):
    name, p, L = args
    n = _CTX["n"]
    bm = load_mask_bits(name, n)
    ge = GilbertElliott.from_burst(p, max(L, 1.0))
    rows = []
    for (k, r) in GRID:
        blocks, failed, hist = empirical_p_fail(bm, n, k, r, k + r)
        emp = failed / blocks if blocks else 0.0
        lo, hi = wilson(failed, blocks)
        mdl = ge.p_fail(k, r)
        binom = binomial_p_fail(p, k, r)
        rows.append({
            "k": k, "r": r, "blocks": blocks, "failed": failed,
            "empirical": emp, "ci_lo": lo, "ci_hi": hi,
            "ge_model": mdl, "binomial": binom,
            "ge_in_ci": lo <= mdl <= hi,
            "ge_ratio": (mdl / emp) if emp > 0 else None,
            "binom_ratio": (binom / emp) if emp > 0 else None,
        })
    return name, p, L, rows


def main():
    _harden()
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=0)
    a = ap.parse_args()

    with open(os.path.join(RESULTS, "e6_netem.json"), encoding="utf-8") as f:
        e6 = json.load(f)
    n = e6["n"]
    names = [k for k in sorted(e6["configs"]) if e6["configs"][k]["lost"] > 0]

    print("=" * 104)
    print("E9 - GE-DP model vs the REAL measured link  (%d traces, %d packets each)"
          % (len(names), n))
    print("=" * 104)

    kind = {}
    for nm in names:
        kind[nm] = "burst" if e6["configs"][nm].get("model") == "gemodel" \
            else "independent"

    jobs = [(nm, e6["configs"][nm]["loss_rate"],
             max(e6["configs"][nm]["mean_burst"], 1.0)) for nm in names]
    nproc = min(a.procs or (os.cpu_count() or 4), len(jobs))
    with mp.Pool(nproc, initializer=_init, initargs=(n,)) as pool:
        results = pool.map(_job, jobs)

    out = {"n": n, "traces": {}}
    print("")
    print("%-13s %-9s %10s %10s %10s %8s %9s %8s" %
          ("trace", "(K,r)", "empirical", "GE model", "binomial",
           "GE/emp", "binom/emp", "in 95CI"))
    print("-" * 104)
    ge_ratios = {"burst": [], "independent": []}
    binom_ratios = {"burst": [], "independent": []}
    in_ci = 0
    tested = 0
    misses = []
    for name, p, L, rows in results:
        kd = kind[name]
        out["traces"][name] = {"loss": p, "burst": L, "kind": kd, "rows": rows}
        for row in rows:
            if row["empirical"] <= 0 and row["ge_model"] < 1e-6:
                continue
            tested += 1
            if row["ge_in_ci"]:
                in_ci += 1
            else:
                misses.append((name, row["k"], row["r"], row["empirical"],
                               row["ge_model"], row["ci_lo"], row["ci_hi"]))
            if row["ge_ratio"]:
                ge_ratios[kd].append(row["ge_ratio"])
            if row["binom_ratio"]:
                binom_ratios[kd].append(row["binom_ratio"])
            print("%-13s %-9s %10.5f %10.5f %10.5f %8s %9s %8s" %
                  (name, "(%d,%d)" % (row["k"], row["r"]),
                   row["empirical"], row["ge_model"], row["binomial"],
                   ("%.2f" % row["ge_ratio"]) if row["ge_ratio"] else "-",
                   ("%.3f" % row["binom_ratio"]) if row["binom_ratio"] else "-",
                   "yes" if row["ge_in_ci"] else "NO"))

    print("-" * 104)

    def med(xs):
        xs = sorted(xs)
        return xs[len(xs) // 2] if xs else float("nan")

    def worst_under(xs):
        return min(xs) if xs else float("nan")

    summary = {
        "cells_tested": tested,
        "ge_within_95ci": in_ci,
        "ge_within_95ci_pct": 100.0 * in_ci / tested if tested else 0.0,
        "ge_ratio_median_all": med(ge_ratios["burst"] + ge_ratios["independent"]),
        "ge_ratio_median_burst": med(ge_ratios["burst"]),
        "ge_ratio_median_independent": med(ge_ratios["independent"]),
        "binomial_ratio_median_burst": med(binom_ratios["burst"]),
        "binomial_ratio_median_independent": med(binom_ratios["independent"]),
        "binomial_worst_ratio_burst": worst_under(binom_ratios["burst"]),
        "misses": misses,
    }
    bm = summary["binomial_ratio_median_burst"]
    bw = summary["binomial_worst_ratio_burst"]
    summary["burst_underestimate_median_x"] = (1.0 / bm) if bm else None
    FLOOR = 1e-6
    if bw is None or bw != bw:
        summary["burst_underestimate_worst_x"] = None
        summary["worst_is_effectively_infinite"] = False
    elif bw < FLOOR:
        summary["burst_underestimate_worst_x"] = None
        summary["worst_is_effectively_infinite"] = True
        summary["worst_lower_bound_x"] = 1.0 / FLOOR
    else:
        summary["burst_underestimate_worst_x"] = 1.0 / bw
        summary["worst_is_effectively_infinite"] = False
    out["summary"] = summary

    print("GE-DP inside the 95%% Wilson interval : %d / %d  (%.0f%%)"
          % (in_ci, tested, summary["ge_within_95ci_pct"]))
    for nm, k, r, emp, mdl, lo, hi in misses:
        print("   miss: %s (%d,%d) empirical=%.5f CI=[%.5f, %.5f] model=%.5f"
              % (nm, k, r, emp, lo, hi, mdl))
    print("GE-DP / empirical  median : %.2fx (burst) | %.2fx (independent)"
          % (summary["ge_ratio_median_burst"],
             summary["ge_ratio_median_independent"]))
    print("")
    print("What ignoring burst costs you (binomial / empirical):")
    print("  independent traces : %.3fx  <- binomial is the RIGHT model here,"
          " and it lands on 1.0 (self-check)"
          % summary["binomial_ratio_median_independent"])
    worst = ("사실상 무한대 (이항 예측이 0에 수렴)"
             if summary.get("worst_is_effectively_infinite")
             else "%.0fx" % (summary["burst_underestimate_worst_x"] or 0))
    print("  BURST traces       : %.4fx -> underestimates failure by"
          " **%.0fx median, worst = %s**"
          % (bm, summary["burst_underestimate_median_x"] or 0, worst))

    path = os.path.join(RESULTS, "e9_validation.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("")
    print("saved: %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
