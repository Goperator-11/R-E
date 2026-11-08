from __future__ import annotations

import math
import statistics
from functools import lru_cache


def _mean(v):
    return (sum(v) / len(v)) if v else None


BATCH_MIN = 8


def batch_means(v):
    n = len(v)
    b = max(1, int(math.sqrt(n)))
    k = n // b
    if k < BATCH_MIN:
        return None
    return [sum(v[i * b:(i + 1) * b]) / float(b) for i in range(k)]


def batch_se_info(v):
    if not v or len(v) < 2:
        return None, None, 0
    m = batch_means(v)
    method = "batch"
    if m is None:
        m = list(v)
        method = "iid"
    mu = sum(m) / len(m)
    se = math.sqrt(sum((x - mu) ** 2 for x in m) / (len(m) - 1) / len(m))
    return se, method, len(m)


def batch_se(v):
    return batch_se_info(v)[0]


def batch_sd(v):
    if not v or len(v) < 2:
        return None
    se = batch_se(v)
    return None if se is None else se * math.sqrt(len(v))


def batch_diff_half(a, b, alpha=0.05):
    sa, _ma, na = batch_se_info(a)
    sb, _mb, nb = batch_se_info(b)
    if sa is None or sb is None or min(na, nb) < 2:
        return None
    va, vb = sa*sa, sb*sb
    if va + vb == 0:
        return 0.0
    df = (va + vb)**2 / (va*va/(na-1) + vb*vb/(nb-1))
    return t_crit(df, alpha) * math.sqrt(va + vb)


def lag1(v):
    n = len(v)
    if n < 3:
        return None
    mu = sum(v) / n
    den = sum((x - mu) ** 2 for x in v)
    if den <= 0:
        return None
    num = sum((v[i] - mu) * (v[i + 1] - mu) for i in range(n - 1))
    return num / den


def balance(cells):
    if not cells:
        return False, "관측 칸이 없다"
    arms = sorted({a for a, _ in cells})
    poss = sorted({p for _, p in cells})
    cnt = {}
    for a, p in cells:
        cnt[(a, p)] = cnt.get((a, p), 0) + 1
    want = len(cells) / float(len(arms) * len(poss)) if arms and poss else 0
    bad = [(a, p, cnt.get((a, p), 0))
           for a in arms for p in poss
           if cnt.get((a, p), 0) != want]
    if not bad:
        return True, "팔 %d x 자리 %d, 각 칸 %g 회" % (len(arms), len(poss), want)
    return False, ("불균형 %d 칸 (기대 %g): %s"
                   % (len(bad), want, bad[:6]))


def latin_anova(rows):
    arms = sorted({r["arm"] for r in rows})
    poss = sorted({r["pos"] for r in rows})
    blks = sorted({r["block"] for r in rows})
    t = len(arms)
    if t < 2 or len(rows) < 4:
        return {"ok": False, "why": "칸이 모자란다"}
    vals = [r["value"] for r in rows if r["value"] is not None]
    if len(vals) != len(rows):
        return {"ok": False, "why": "빈 칸이 있다"}
    if any(isinstance(v, bool) or not isinstance(v, (int, float))
           or not math.isfinite(v) for v in vals):
        return {"ok": False, "why": "유한한 수치가 아닌 칸이 있다"}
    for left, right in (("arm", "pos"), ("arm", "block"), ("pos", "block")):
        balanced, why = balance([(r[left], r[right]) for r in rows])
        if not balanced:
            return {"ok": False, "why": "%s/%s: %s" % (left, right, why)}
    grand = _mean(vals)

    def group_mean(key):
        g = {}
        for r in rows:
            g.setdefault(r[key], []).append(r["value"])
        return {k: _mean(v) for k, v in g.items()}, g

    am, ag = group_mean("arm")
    pm, pg = group_mean("pos")
    bm, bg = group_mean("block")

    def ss(gm, gg):
        return sum(len(gg[k]) * (gm[k] - grand) ** 2 for k in gm)

    ss_tot = sum((v - grand) ** 2 for v in vals)
    ss_arm = ss(am, ag)
    ss_pos = ss(pm, pg)
    ss_blk = ss(bm, bg)
    ss_res = ss_tot - ss_arm - ss_pos - ss_blk
    if ss_res < -1e-10 * max(1.0, ss_tot):
        return {"ok": False, "why": "잔차 제곱합이 음수다"}
    if ss_res < 0:
        ss_res = 0.0
    df_res = len(rows) - 1 - (t - 1) - (len(poss) - 1) - (len(blks) - 1)
    if df_res <= 0:
        return {"ok": False, "why": "잔차 자유도가 0 이하"}
    mse = ss_res / df_res
    reps = len(rows) / float(t)
    se_c = math.sqrt(2.0 * mse / reps) if reps > 0 and mse >= 0 else None
    ms_pos = ss_pos / max(1, len(poss) - 1)
    pos_f = (ms_pos / mse) if mse > 0 else None
    return {
        "ok": True,
        "arm_means": am,
        "grand": grand,
        "mse": mse,
        "df_resid": df_res,
        "reps_per_arm": reps,
        "se_contrast": se_c,
        "ss": {"arm": ss_arm, "pos": ss_pos, "block": ss_blk,
               "resid": ss_res, "total": ss_tot},
        "pos_f": pos_f,
        "pos_share": (ss_pos / ss_tot) if ss_tot > 0 else 0.0,
    }


def _beta_fraction(a, b, x):
    floor = 1e-300
    c = 1.0
    d = 1.0 - (a + b) * x / (a + 1.0)
    d = 1.0 / (d if abs(d) > floor else floor)
    h = d
    for m in range(1, 10001):
        aa = m * (b - m) * x / ((a + 2*m - 1) * (a + 2*m))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        d = 1.0 / (d if abs(d) > floor else floor)
        c = c if abs(c) > floor else floor
        h *= d * c
        aa = -(a + m) * (a + b + m) * x / ((a + 2*m) * (a + 2*m + 1))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        d = 1.0 / (d if abs(d) > floor else floor)
        c = c if abs(c) > floor else floor
        change = d * c
        h *= change
        if abs(change - 1.0) < 1e-13:
            return h
    raise ArithmeticError("incomplete beta did not converge")


def _regularized_beta(x, a, b):
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    factor = math.exp(math.lgamma(a+b) - math.lgamma(a) - math.lgamma(b)
                      + a * math.log(x) + b * math.log1p(-x))
    if x < (a+1.0) / (a+b+2.0):
        return factor * _beta_fraction(a, b, x) / a
    return 1.0 - factor * _beta_fraction(b, a, 1.0-x) / b


@lru_cache(maxsize=512)
def t_crit(df, alpha=0.05):
    df, alpha = float(df), float(alpha)
    if not math.isfinite(df) or df <= 0 or not 0 < alpha < 1:
        raise ValueError("df must be positive and finite; alpha must be between 0 and 1")
    lo, hi = 0.0, 1.0
    while _regularized_beta(df / (df + hi*hi), df/2, 0.5) > alpha:
        hi *= 2.0
        if not math.isfinite(hi*hi):
            raise ArithmeticError("t critical value exceeds numerical range")
    for _ in range(100):
        mid = (lo + hi) / 2.0
        if _regularized_beta(df / (df + mid*mid), df/2, 0.5) > alpha:
            lo = mid
        else:
            hi = mid
        if hi - lo <= 1e-12 * max(1.0, hi):
            break
    return (lo + hi) / 2.0


T_TABLE = {
    0.05: {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
           7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179,
           13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 18: 2.101, 20: 2.086,
           24: 2.064, 30: 2.042, 40: 2.021, 60: 2.000, 120: 1.980},
    0.025: {1: 25.452, 2: 6.205, 3: 4.177, 4: 3.495, 5: 3.163, 6: 2.969,
            7: 2.841, 8: 2.752, 9: 2.685, 10: 2.634, 12: 2.560, 15: 2.490,
            20: 2.423, 30: 2.360, 60: 2.299, 120: 2.270},
    0.0125: {1: 50.923, 2: 8.860, 3: 5.392, 4: 4.315, 5: 3.810, 6: 3.521,
             7: 3.335, 8: 3.206, 9: 3.111, 10: 3.038, 12: 2.934, 15: 2.837,
             20: 2.744, 30: 2.657, 60: 2.575, 120: 2.536},
    0.01: {1: 63.657, 2: 9.925, 3: 5.841, 4: 4.604, 5: 4.032, 6: 3.707,
           7: 3.499, 8: 3.355, 9: 3.250, 10: 3.169, 11: 3.106, 12: 3.055,
           13: 3.012, 14: 2.977, 15: 2.947, 16: 2.921, 18: 2.878, 20: 2.845,
           24: 2.797, 30: 2.750, 40: 2.704, 60: 2.660, 120: 2.617},
}

KNOWN_ALPHAS = tuple(sorted(T_TABLE))


def contrast(an, a, b, alpha=0.05):
    if not an.get("ok"):
        return None, None
    am = an["arm_means"]
    if a not in am or b not in am:
        return None, None
    d = am[a] - am[b]
    half = t_crit(an["df_resid"], alpha) * an["se_contrast"]
    return d, half


def n_needed_blocked(an, target_delta, alpha=0.05, power=0.80):
    if not an.get("ok") or not target_delta:
        return None
    d = abs(float(target_delta))
    if d < 0.01:
        return None
    z = statistics.NormalDist()
    za = z.inv_cdf(1.0 - alpha / 2.0)
    zb = z.inv_cdf(power)
    return int(math.ceil(2.0 * (za + zb) ** 2 * an["mse"] / (d * d)))
