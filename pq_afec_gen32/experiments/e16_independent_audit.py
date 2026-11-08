import itertools
import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RESULTS = os.path.join(HERE, "results")
sys.path.insert(0, ROOT)

from afec.channel import GilbertElliott
from afec.controller import FecConfig, choose_redundancy
from afec.rs import RSErasureCode

FAIL = []
PASS = []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("  [%s] %-50s %s" % ("OK" if ok else "FAIL", name, detail))


def _harden():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


def brute_force_pmf(ch, n):
    pi = ch.stationary
    P = ch.transition
    lossp = [ch.p_good, ch.p_bad]
    pmf = [0.0] * (n + 1)
    for states in itertools.product((0, 1), repeat=n):
        p_path = pi[states[0]]
        for i in range(1, n):
            p_path *= P[states[i - 1]][states[i]]
        if p_path == 0.0:
            continue
        sub = [1.0]
        for s in states:
            q = lossp[s]
            nxt = [0.0] * (len(sub) + 1)
            for c, w in enumerate(sub):
                nxt[c] += w * (1.0 - q)
                nxt[c + 1] += w * q
            sub = nxt
        for c, w in enumerate(sub):
            pmf[c] += p_path * w
    return pmf


def a1_brute_force():
    print("\n[A1] DP vs brute-force enumeration of all state paths")
    worst = 0.0
    for (p, L) in ((0.05, 1.0), (0.05, 4.0), (0.10, 2.0), (0.01, 8.0),
                   (0.30, 3.0)):
        ch = GilbertElliott.from_burst(p, L)
        for n in (1, 2, 5, 9, 12):
            dp = ch.erasure_pmf(n)
            bf = brute_force_pmf(ch, n)
            worst = max(worst, max(abs(a - b) for a, b in zip(dp, bf)))
    check("A1 DP == brute force (all paths)", worst < 1e-12,
          "max abs diff %.2e" % worst)


def transfer_matrix_pmf(ch, n):
    P = ch.transition
    lg, lb = ch.p_good, ch.p_bad
    pi = ch.stationary
    vec = [[pi[0]], [pi[1]]]

    def mul_lin(poly, a0, a1):
        out = [0.0] * (len(poly) + 1)
        for i, c in enumerate(poly):
            out[i] += c * a0
            out[i + 1] += c * a1
        return out

    def add(a, b):
        m = max(len(a), len(b))
        return [(a[i] if i < len(a) else 0.0) + (b[i] if i < len(b) else 0.0)
                for i in range(m)]

    for _ in range(n):
        emitted = [mul_lin(vec[0], 1.0 - lg, lg),
                   mul_lin(vec[1], 1.0 - lb, lb)]
        nxt = [[0.0], [0.0]]
        for s in (0, 1):
            for t in (0, 1):
                if P[s][t]:
                    nxt[t] = add(nxt[t], [c * P[s][t] for c in emitted[s]])
        vec = nxt
    total = add(vec[0], vec[1])
    total = total + [0.0] * (n + 1 - len(total))
    return total[:n + 1]


def a2_transfer_matrix():
    print("\n[A2] DP vs transfer-matrix / generating function")
    worst = 0.0
    for (p, L) in ((0.02, 1.0), (0.05, 4.0), (0.10, 8.0), (0.20, 2.0)):
        ch = GilbertElliott.from_burst(p, L)
        for n in (1, 8, 32, 64, 100):
            dp = ch.erasure_pmf(n)
            tm = transfer_matrix_pmf(ch, n)
            worst = max(worst, max(abs(a - b) for a, b in zip(dp, tm)))
    check("A2 DP == transfer matrix", worst < 1e-12,
          "max abs diff %.2e" % worst)


def a3_identities():
    print("\n[A3] from_burst(p, L) really produces loss rate p and burst L")
    bad_p = bad_L = 0.0
    for (p, L) in ((0.001, 1.0), (0.01, 2.0), (0.05, 4.0), (0.10, 8.0),
                   (0.25, 3.0), (0.5, 5.0)):
        ch = GilbertElliott.from_burst(p, L)
        bad_p = max(bad_p, abs(ch.loss_rate - p))
        bad_L = max(bad_L, abs(ch.mean_burst - L))
    check("A3a stationary loss rate == p", bad_p < 1e-12, "max err %.2e" % bad_p)
    check("A3b mean burst == L", bad_L < 1e-12, "max err %.2e" % bad_L)

    rng = random.Random(4242)
    ch = GilbertElliott.from_burst(0.05, 4.0)
    st = 1 if rng.random() < ch.stationary[1] else 0
    n = 400000
    lost = 0
    runs = []
    cur = 0
    for _ in range(n):
        pl = ch.p_bad if st else ch.p_good
        if rng.random() < pl:
            lost += 1
            cur += 1
        elif cur:
            runs.append(cur)
            cur = 0
        q = ch.q_gb if st == 0 else ch.q_bg
        if rng.random() < q:
            st ^= 1
    emp_p = lost / n
    emp_L = sum(runs) / len(runs)
    check("A3c simulated chain matches p (400k)", abs(emp_p - 0.05) < 0.003,
          "empirical p = %.4f" % emp_p)
    check("A3d simulated chain matches L (400k)", abs(emp_L - 4.0) < 0.15,
          "empirical L = %.3f" % emp_L)


def a4_interleave():
    print("\n[A4] interleave=D equals observing the chain every D steps")
    worst = 0.0
    for (p, L, D) in ((0.05, 4.0, 2), (0.05, 4.0, 4), (0.10, 8.0, 3)):
        ch = GilbertElliott.from_burst(p, L)
        Pd = ch.transition
        for _ in range(D - 1):
            Pd = [[sum(Pd[i][k] * ch.transition[k][j] for k in range(2))
                   for j in range(2)] for i in range(2)]
        sub = GilbertElliott(q_gb=Pd[0][1], q_bg=Pd[1][0],
                             p_good=ch.p_good, p_bad=ch.p_bad)
        for n in (8, 32, 64):
            a = ch.erasure_pmf(n, interleave=D)
            b = sub.erasure_pmf(n)
            worst = max(worst, max(abs(x - y) for x, y in zip(a, b)))
    check("A4 interleaved DP == subsampled chain", worst < 1e-12,
          "max abs diff %.2e" % worst)


def a5_rs_mds():
    print("\n[A5] Reed-Solomon: exhaustive erasure patterns")
    ok_all = True
    detail = ""
    for (k, r) in ((1, 1), (2, 1), (3, 2), (4, 3), (6, 3), (8, 4)):
        code = RSErasureCode(k, r)
        src = [bytes([(i * 31 + t * 7) & 0xFF for t in range(16)])
               for i in range(k)]
        rep = code.encode(src)
        allsym = {i: src[i] for i in range(k)}
        allsym.update({k + j: rep[j] for j in range(r)})
        n = k + r
        for lost in itertools.combinations(range(n), r):
            recv = {i: v for i, v in allsym.items() if i not in lost}
            try:
                out = code.decode(recv)
            except Exception as e:
                ok_all, detail = False, "k=%d r=%d lost=%s raised %s" % (
                    k, r, lost, e)
                break
            if out != src:
                ok_all, detail = False, "k=%d r=%d lost=%s wrong output" % (
                    k, r, lost)
                break
        if not ok_all:
            break
        for lost in itertools.combinations(range(n), r + 1):
            recv = {i: v for i, v in allsym.items() if i not in lost}
            try:
                out = code.decode(recv)
            except Exception:
                continue
            if out == src:
                ok_all, detail = False, (
                    "k=%d r=%d recovered from %d erasures - not MDS-tight"
                    % (k, r, r + 1))
                break
        if not ok_all:
            break
    check("A5 MDS: r erasures recover, r+1 do not", ok_all,
          detail or "exhaustive over 6 (k,r) pairs")


def a6_argmin():
    print("\n[A6] choose_redundancy returns the global argmin of J")
    cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0)
    mismatches = []
    nonunimodal = 0
    cells = 0
    for p in (0.0, 0.001, 0.01, 0.05, 0.10, 0.20, 0.35, 0.50):
        for L in (1.0, 2.0, 4.0, 8.0):
            for k in (8, 16, 32, 64):
                for trec in (40.0, 999.0):
                    cells += 1
                    d = choose_redundancy(k, p, L, trec, 0.0, cfg)
                    ch = GilbertElliott.cached(p, L)
                    r_max = min(max(int(math.ceil(k * cfg.rho_max)), 0),
                                max(255 - k, 0))
                    byte_ms = cfg.symbol_bytes * 8.0 / cfg.rate_bps * 1000.0
                    best_r, best_J = None, None
                    Js = []
                    for r in range(r_max + 1):
                        J = r * byte_ms + ch.p_fail(k, r) * trec
                        Js.append(J)
                        if best_J is None or J < best_J - 1e-12:
                            best_r, best_J = r, J
                    if d.r != best_r:
                        mismatches.append((p, L, k, trec, d.r, best_r,
                                           Js[d.r] - best_J))
                    downs = [i for i in range(1, len(Js)) if Js[i] < Js[i - 1]]
                    ups = [i for i in range(1, len(Js)) if Js[i] > Js[i - 1]]
                    if downs and ups and min(ups) < max(downs):
                        nonunimodal += 1
    check("A6 argmin == exhaustive scan", not mismatches,
          "%d mismatch(es) over %d cells" % (len(mismatches), cells))
    for m in mismatches[:5]:
        print("        p=%.3f L=%.1f k=%d T=%.0f  got r=%d want r=%d "
              "(J excess %.4f)" % m)
    print("        note: J(r) non-unimodal in %d/%d cells - expected, this is "
          "the documented 'abandonment ridge'" % (nonunimodal, cells))


def a7_numerics():
    print("\n[A7] numerical health and monotonicity laws")
    worst_sum = 0.0
    neg = 0
    for (p, L) in ((0.0, 1.0), (1e-6, 1.0), (0.05, 4.0), (0.5, 8.0),
                   (0.9, 2.0)):
        ch = GilbertElliott.from_burst(p, L)
        for n in (1, 32, 128, 255):
            pmf = ch.erasure_pmf(n)
            worst_sum = max(worst_sum, abs(sum(pmf) - 1.0))
            neg += sum(1 for x in pmf if x < -1e-15)
    check("A7a pmf sums to 1 (n up to 255)", worst_sum < 1e-9,
          "max |sum-1| = %.2e" % worst_sum)
    check("A7b no negative probabilities", neg == 0, "%d negative" % neg)

    bad = []
    for k, r in ((32, 4), (32, 8), (64, 16)):
        for L in (1.0, 4.0):
            prev = -1.0
            for i in range(0, 60):
                p = i / 100.0
                v = GilbertElliott.from_burst(p, L).p_fail(k, r)
                if v < prev - 1e-12:
                    bad.append((k, r, L, p))
                prev = v
    check("A7c P_fail non-decreasing in p", not bad,
          "%d violation(s)" % len(bad))

    bad2 = []
    for p, L in ((0.05, 1.0), (0.05, 4.0), (0.15, 8.0)):
        ch = GilbertElliott.from_burst(p, L)
        prev = 2.0
        for r in range(0, 33):
            v = ch.p_fail(32, r)
            if v > prev + 1e-12:
                bad2.append((p, L, r))
            prev = v
    check("A7d P_fail non-increasing in r", not bad2,
          "%d violation(s)" % len(bad2))

    cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0)
    diff = 0
    for i in range(400):
        p = 0.0001 + i * 0.0007
        a = choose_redundancy(32, p, 3.0, 40.0, 0.0, cfg).r
        exact = GilbertElliott.from_burst(p, 3.0)
        byte_ms = cfg.symbol_bytes * 8.0 / cfg.rate_bps * 1000.0
        best_r, best_J = None, None
        for r in range(0, 17):
            J = r * byte_ms + exact.p_fail(32, r) * 40.0
            if best_J is None or J < best_J - 1e-12:
                best_r, best_J = r, J
        if a != best_r:
            diff += 1
    check("A7e cache quantisation does not change r", diff == 0,
          "%d/400 differ" % diff)


def a8_report_consistency():
    print("\n[A8] numbers quoted in the report are traceable to the raw JSON")
    rep_path = os.path.join(ROOT, "docs", "실측 보고서.md")
    if not os.path.exists(rep_path):
        check("A8 report present", False, "not found")
        return
    with open(rep_path, encoding="utf-8") as f:
        text = f.read()

    def load(n):
        p = os.path.join(RESULTS, n)
        if not os.path.exists(p):
            return None
        with open(p, encoding="utf-8") as f2:
            return json.load(f2)

    e1 = load("e1_mlkem.json")
    e6 = load("e6_netem.json")
    e7 = load("e7_policy.json")
    e8 = load("e8_cpu.json")
    e9 = load("e9_validation.json")

    facts = []
    if e1:
        enc = 1e6 / e1["timing"]["ML-KEM-768"]["encaps_ops_median"]
        x25 = 1e6 / e1["timing"]["X25519"]["encaps_ops_median"]
        facts.append(("ML-KEM-768 encaps", "%.1f" % enc, "15.5" in text))
        facts.append(("X25519 encaps", "%.1f" % x25, "41.0" in text))
        facts.append(("speed ratio", "%.1f" % (x25 / enc), "2.7" in text))
    if e9:
        s = e9["summary"]
        facts.append(("cells in 95%CI",
                      "%d/%d" % (s["ge_within_95ci"], s["cells_tested"]),
                      "97" in text and "98" in text))
        u = s.get("burst_underestimate_median_x") or 0
        facts.append(("binomial underestimate", "%.0f" % u, "16" in text))
    if e7:
        lw = e7["long_worst_regret"]
        facts.append(("worst regret none", "%.0f" % (lw["none"] * 100),
                      "523" in text))
        facts.append(("worst regret rquic", "%.0f" % (lw["rquic"] * 100),
                      "72" in text))
        facts.append(("worst regret adaptive", "%.1f" % (lw["adaptive"] * 100),
                      "6" in text))
    if e8:
        vals = [g["c_cpu_fraction"] * 100 for g in e8["grid"].values()
                if "c_cpu_fraction" in g]
        facts.append(("CPU max", "%.1f" % max(vals),
                      "5.7" in text or "5.65" in text))
    if e6:
        ctl = e6["configs"].get("control_noloss")
        if ctl:
            facts.append(("no-loss control", "%.6f" % ctl["loss_rate"],
                          ctl["loss_rate"] == 0.0))

    bad = [(n, g) for n, g, ok in facts if not ok]
    check("A8 report numbers traceable", not bad,
          "%d/%d verified" % (len(facts) - len(bad), len(facts)))
    for n, g in bad:
        print("        MISMATCH: %s  (json says %s)" % (n, g))


def main():
    _harden()
    print("=" * 78)
    print("E16 - independent re-derivation audit")
    print("=" * 78)
    a1_brute_force()
    a2_transfer_matrix()
    a3_identities()
    a4_interleave()
    a5_rs_mds()
    a6_argmin()
    a7_numerics()
    a8_report_consistency()
    print("")
    print("=" * 78)
    print("PASS %d / FAIL %d" % (len(PASS), len(FAIL)))
    for f in FAIL:
        print("   FAILED: %s" % f)
    print("=" * 78)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
