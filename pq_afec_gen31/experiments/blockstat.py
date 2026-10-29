# -*- coding: utf-8 -*-
"""라틴 방격 설계를 **설계대로** 분석한다 - 자리 효과를 흡수한 팔 대조.

왜 이것이 필요한가
------------------
p17·p18 은 팔을 라틴 방격으로 돌린다. 각 팔이 각 자리를 정확히 한 번씩
겪게 해서 **자리 효과(순서 표류)를 상쇄**하려는 설계다. 설계는 옳다.
그런데 **분석이 설계를 안 쓰고 있었다.**

두 군데가 틀려 있었다.

1) **팔 대조를 두 표본(Welch)으로 쟀다.** 그러면 자리 효과가 통째로
   잔차에 남아 신뢰구간을 부풀린다. 방격이 이미 상쇄해 준 것을 다시
   잡음으로 세는 것이다 - 설계로 번 정밀도를 버린다.

2) **「자리 효과 <= 신뢰반폭」을 합격 기준으로 썼다** (p18 검사 4).
   이 자는 **거꾸로 되어 있다.** 반폭은 표본이 늘수록 줄어들므로
   **정밀하게 잴수록 실패한다.** 실제로 p18 원자료에서:

       조건                  자리효과  반폭    이득    자리/이득  판정
       m_max2포기·무손실       0.71    0.32   +52.13    1.4%    실패
       임계사이·버스트3          6.15   11.10   +17.77     35%    통과
       임계위·무버스트           2.55    4.66    +1.19    214%    통과

   **비율로 가장 나쁜 조건을 통과시키고 무시해도 되는 조건을 실패시킨다.**

무엇이 맞는 자인가
------------------
라틴 방격은 **완전 균형 설계**다. 균형이 잡혀 있으면 팔 효과 추정량은
자리 효과가 아무리 커도 **편향되지 않는다.** 그러므로 「자리 효과가 크다」는
그 자체로 실패가 아니다. 자리 효과가 하는 일은 **정밀도를 깎는 것**뿐이고,
그것은 이미 신뢰구간이 말한다.

그래서 두 가지로 나눈다.

  (가) **설계 검사** — 방격이 실제로 균형인가. 각 (팔, 자리) 조합이 정확히
       한 번씩인가. 이건 자료가 아니라 **설계의 성질**이라 결정적으로
       판정된다. 깨져 있으면 그때는 진짜 실패다(추정량이 편향된다).
  (나) **자리를 흡수한 대조** — 표준 라틴 방격 분산분석.

           y[행][열] = mu + row + col + 팔 + eps

       팔 대조의 표준오차는 잔차평균제곱 MSE 로부터
           SE(팔i - 팔j) = sqrt(2 MSE / r),  r = 팔당 반복 수
       이고 자유도는 (t-1)(t-2) 다 (t x t 방격).

   자리 효과는 **버리지 않고 진단으로 남긴다** — F 검정으로 유의한지
   보고한다. 상쇄했다고 없던 일로 하지 않는다는 이 저장소의 규칙 그대로다.

한계: 이 분석은 가법 모형과 오차 독립성을 가정한다. 팔과 자리의 상호작용,
   이분산 또는 시계열 상관이 있으면 표준오차의 정확성을 보장할 수 없다.
   라틴 방격이라는 이유만으로 신뢰구간이 항상 보수적이라고 볼 수 없다.

참고한 것: Fisher 의 라틴 방격 분산분석 (표준 실험계획법). 새로 지어낸
절차가 아니라 **이미 검증된 절차를 이 자료에 맞게 쓴 것**이다.
"""
from __future__ import annotations

import math
import statistics
from functools import lru_cache


def _mean(v):
    return (sum(v) / len(v)) if v else None


# ---------------------------------------------------------------------------
# 🩸 2026-09-07 - **연속한 판은 독립이 아니다.** 한 팔의 연결 시계열은 부하·
#    열·캐시로 자기상관이 있어 s/sqrt(n) 이 불확실성을 과소평가한다(p16 이
#    09-01 에 실측: 배치평균 SE / 독립 SE = 1.66~2.43). p16 이 먼저 고쳤고
#    p11·p15 가 같은 자를 쓰도록 여기로 옮긴다 - 같은 식을 세 곳에 두면 한
#    곳만 고치는 사고가 난다. 배치 크기 b ~ sqrt(n) (표준 관례, 배치 수도
#    ~sqrt(n)). 배치가 BATCH_MIN 보다 적으면 배치평균 자체를 못 믿으므로
#    독립 가정으로 되돌아가되, 호출부가 그 사실을 알 수 있게 flag 를 준다.
# ---------------------------------------------------------------------------
BATCH_MIN = 8


def batch_means(v):
    """비겹침 배치평균. 배치가 BATCH_MIN 미만이면 None."""
    n = len(v)
    b = max(1, int(math.sqrt(n)))
    k = n // b
    if k < BATCH_MIN:
        return None
    return [sum(v[i * b:(i + 1) * b]) / float(b) for i in range(k)]


def batch_se_info(v):
    """(표준오차, 방법, 배치 수). 방법은 "batch" 또는 "iid".

    2026-09-07 감사 - batch_se 가 짧은 표본에서 **말없이** 독립 가정으로
    되돌아갔고, p11·p15 는 se_method 를 "batch_means" 로 무조건 적었다. n<64
    면 배치가 8 개가 안 돼 iid 다. 호출부가 방법을 기록하고 검사할 수 있게
    셋을 같이 준다.
    """
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
    """평균의 표준오차 (배치평균 기준). 짧으면 독립 가정으로 되돌아간다 -
    방법까지 알아야 하면 batch_se_info 를 쓴다."""
    return batch_se_info(v)[0]


def batch_sd(v):
    """필요 표본 계산이 쓰는 「한 판의 유효 표준편차」 = batch_se * sqrt(n).
    반폭과 필요 표본이 같은 자료를 말하게 하려는 것이다."""
    if not v or len(v) < 2:
        return None
    se = batch_se(v)
    return None if se is None else se * math.sqrt(len(v))


def batch_diff_half(a, b, alpha=0.05):
    """Welch-t half-width using the number of batch means, not connections.

    Independent batch means are an approximation. Residual cross-arm/time
    correlation and selection of the best arm still need separate treatment.
    """
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
    """lag-1 자기상관. 부하 자국의 서명이다(09-01: 오염된 판 +0.36~+0.53,
    깨끗한 판 +0.11~+0.18 - 이어붙여 잰 값). 판정에 쓰지 않고 정보로 찍는다."""
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
    """설계 검사 (가). cells = [(팔, 자리), ...]

    돌려주는 것: (균형인가, 설명). 각 팔이 각 자리를 같은 횟수로 겪어야 한다.
    """
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
    """라틴 방격 분산분석. rows = [{"arm","pos","block","value"}, ...]

    value 는 그 칸의 **블록 평균**이다(연결 하나가 아니라). 반복 없는 3 원
    가법 모형이므로 잔차 자유도는 (t-1)(t-2) 다.

    돌려주는 것:
        arm_means      팔별 평균 (자리·블록이 균형이므로 이것이 곧 조정평균)
        mse            잔차평균제곱
        df_resid       잔차 자유도
        se_contrast    두 팔 차의 표준오차
        pos_f         자리 효과의 F (진단용). MSE=0이면 정의되지 않아 None.
        ok             계산이 성립했는가
    """
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
    # The sum-of-squares subtraction below is valid only for orthogonal factors.
    # Checking arm/position alone misses confounding with the cycle/block.
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
    # Only rounding-sized negative residuals can be clamped.
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
    # 자리 효과의 F. 진단용이다 - 이것으로 합격/불합격을 가르지 않는다.
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
    """Continued fraction for the regularized incomplete beta function."""
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
    """양측 Student t 임계값. 불완전 베타 함수를 역산하며 외부 패키지를 쓰지 않는다.

    양의 자유도(소수 포함)와 0 < alpha < 1을 받는다. 분포 식은
    https://mooseframework.inl.gov/source/distributions/StudentT.html 참고.
    표에 없는 alpha를 정규 근사로 바꾸던 이전 동작은 제거했다.
    """
    df, alpha = float(df), float(alpha)
    if not math.isfinite(df) or df <= 0 or not 0 < alpha < 1:
        raise ValueError("df must be positive and finite; alpha must be between 0 and 1")
    # P(|T_df| > t) = I_{df/(df+t*t)}(df/2, 1/2).
    # The old unknown-alpha approximation gave 9.04 instead of 127.32
    # at df=1, alpha=.005. Invert the distribution for every alpha.
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


# 이전 공개 상수와의 호환을 위해 남긴 표이며 t_crit의 계산에는 쓰지 않는다.
# 양측 t 임계값을 **alpha 별로** 담는다. 라틴 방격은 자유도가 작아
# (4x4 방격이면 6) 정규 근사를 쓰면 구간이 눈에 띄게 좁아진다.
#   0.05   단일 비교
#   0.025  조건 2 개 Bonferroni
#   0.0125 조건 4 개
#   0.01   조건 5 개  <- p18 이 실제로 쓰는 값
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
    """팔 a - 팔 b 의 조정 대조와 신뢰반폭. an = latin_anova 의 결과."""
    if not an.get("ok"):
        return None, None
    am = an["arm_means"]
    if a not in am or b not in am:
        return None, None
    d = am[a] - am[b]
    half = t_crit(an["df_resid"], alpha) * an["se_contrast"]
    return d, half


def n_needed_blocked(an, target_delta, alpha=0.05, power=0.80):
    """자리를 흡수한 잔차분산 기준으로 필요한 **블록 수**.

    블록 하나가 팔당 n_conn 연결이므로, 필요한 총 표본은
    (블록 수) x (블록당 연결 수) 다. 두 표본 식과 달리 **자리 효과가
    빠진 분산**을 쓰므로 요구량이 작아진다 - 설계로 번 정밀도가 여기 나타난다.
    """
    if not an.get("ok") or not target_delta:
        return None
    d = abs(float(target_delta))
    if d < 0.01:
        return None
    z = statistics.NormalDist()
    za = z.inv_cdf(1.0 - alpha / 2.0)
    zb = z.inv_cdf(power)
    return int(math.ceil(2.0 * (za + zb) ** 2 * an["mse"] / (d * d)))
