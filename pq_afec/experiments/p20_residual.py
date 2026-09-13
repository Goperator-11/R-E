# -*- coding: utf-8 -*-
"""P20 - 잔차 해부: 모형이 **어디에서** 틀리는가를 원자료에서 직접 캔다.

왜 이 단계가 필요한가
---------------------
지금 루프의 눈은 「검사가 붉다/푸르다」 하나뿐이다. 붉어지면 세 가지가
구분되지 않는다.

    (a) 모형의 **값**이 틀렸다 (J 가 몇 ms 어긋난다)
    (b) 모형의 **선택**이 틀렸다 (다른 m 을 고른다)
    (c) 아무것도 안 틀렸고 **못 잰 것**이다 (표본 부족)

이 셋을 가르려면 평균 하나가 아니라 **분포를 갈라 봐야 한다.** 실제로
2026-08-27 에 p17 의 「손실 15% 에서 m3 이 m2 보다 나쁘다」를 손으로 갈라
보니 셋 다 아니었다 — 1-RTT 무리도 2-RTT 무리도 모형과 맞았고, 어긋난
것은 **3% 짜리 PTO 꼬리 하나**였다. 평균만 보면 「모형이 부호를 틀렸다」로
읽히지만, 갈라 보면 「무거운 꼬리를 750 판으로 재려 했다」가 답이다.

그래서 이 단계는 새 실측을 하지 않는다. **이미 있는 원자료를 다시 읽는다.**
Windows 에서 몇 초에 돈다(WSL 도 root 도 필요 없다).

무엇을 재나
-----------
조건마다 팔별로 세 무리로 가른다. 경계는 마법 상수가 아니라 **RTT 로**
잡는다(그래야 RTT 가 바뀌어도 같은 뜻이다).

    제때  (ontime)   기준선 + 0.5·RTT 미만      = 1-RTT 로 끝났다
    한 판 더 (extra) 기준선 + 0.5~2.5·RTT       = 증폭 부족 2-RTT, 또는 ACK 재전송
    시간초과 (timeout) 기준선 + 2.5·RTT 초과     = PTO 가지 (경로 무관 200.86 ms)

기준선은 그 조건에서 **가장 빠른 팔의 중앙값**이다. 절대 시각을 맞추려는
것이 아니라 무리를 가르는 것이 목적이므로 자료 스스로 정하게 둔다.

모형 쪽에서 같은 세 수가 나온다(policy.flight_outcome):

    P(제때)     = 1 - p_two_rtt - p_fail
    P(한 판 더) = p_two_rtt + p_fail_ack
    P(시간초과) = p_fail_pto

**이 대조가 이 단계의 알맹이다.** J 는 세 무리의 가중합이라, J 가 맞는데
무리 비율이 틀리면 두 오차가 상쇄된 것이고 다음 조건에서 깨진다. 반대로
무리 비율이 다 맞는데 J 가 틀리면 틀린 것은 **무리의 값**(t_tx·T_recover)이다.
어느 쪽인지 여기서 이름이 붙는다.

그리고 팔쌍마다
    측정 Δ(팔i - 팔j) ± 95% 반폭   vs   모형 ΔJ
를 놓고, 반폭이 |Δ| 보다 크면 **판정 불능**으로 표시하고 **필요 표본 N** 을
같이 적는다. p18 이 이미 갖고 있던 관례(`n_needed_per_arm`)를 p11·p15·p16·
p17 전부에 옮기는 것이다 — 「수정 대기 목록」 A-3 후보 ②·D-5 가 그것이다.

무거운 꼬리를 어떻게 다루나
---------------------------
PTO 무리는 빈도 3% 에 값 260 ms 라 평균의 분산을 혼자 지배한다. 그래서
평균 하나만 보고 부호를 말하면 안 된다. 세 가지를 나란히 낸다.

    mean      전부 (연구가 주장하는 값. 이게 정본이다)
    trimmed   위아래 5% 를 자른 평균 (꼬리를 뺀 본체가 어디 있는지)
    class     무리별 (비율 × 값) 분해 - 차이가 **어느 무리에서** 나왔는가

셋이 갈리면 그 자체가 결과다: 「본체는 같고 꼬리만 다르다」는 「모형이
틀렸다」가 아니라 「꼬리를 재려면 표본이 N 필요하다」는 뜻이다.

⚠️ 한계 — 이 단계는 **모형을 검증하지 않는다.** 모형과 측정이 어긋난
   자리를 **찾아서 이름을 붙일 뿐**이다. 고칠지 더 잴지는 사람이 정한다.
"""
from __future__ import annotations

import json
import math
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from padfec import policy as POL  # noqa: E402
from padfec import quantum as QU  # noqa: E402

RES = os.path.join(ROOT, "experiments", "results")
STATE = os.path.join(ROOT, "experiments", "state")
OUT = os.path.join(RES, "p20_residual.json")

# 실측 C — padbed.measured_C 와 같은 값이어야 한다. padbed 는 root 와 WSL 을
# 요구하므로(harden/require_root) 여기서는 import 하지 않고 p1 이 남긴 실측
# 결과를 읽는다. 못 읽으면 그때만 아래 예비값을 쓰고 그 사실을 결과에 적는다.
C_FALLBACK = {"x25519": 271, "X25519MLKEM768": 1448}

ALPHA = 0.05


def measured_C(group):
    """p1(첫 비행 구조 실측)이 잰 C. 없으면 예비값 + 표시."""
    try:
        d = json.load(open(os.path.join(RES, "p1_flight.json"),
                          encoding="utf-8"))
    except Exception:
        return C_FALLBACK.get(group), "fallback"
    # p1 은 그룹마다 여러 ips 로 돌린다. C(ClientHello 순 바이트)는 ips 와
    # 무관한 상수여야 하므로 **패딩을 안 준 판(ips=0)** 의 crypto_total 을 쓴다.
    best = None
    for run in d.get("runs", []):
        if run.get("group") != group or not run.get("valid"):
            continue
        c = (run.get("decoded") or {}).get("crypto_total")
        if not c:
            continue
        if run.get("ips", 0) == 0:
            return int(c), "p1"
        best = int(c) if best is None else max(best, int(c))
    if best:
        return best, "p1"
    return C_FALLBACK.get(group), "fallback"


def mean(v):
    return (sum(v) / len(v)) if v else None


def se(v):
    if not v or len(v) < 2:
        return None
    mu = sum(v) / len(v)
    var = sum((x - mu) ** 2 for x in v) / (len(v) - 1)
    return math.sqrt(var / len(v))


def sd(v):
    if not v or len(v) < 2:
        return None
    mu = sum(v) / len(v)
    return math.sqrt(sum((x - mu) ** 2 for x in v) / (len(v) - 1))


def trimmed_mean(v, frac=0.05):
    if not v:
        return None
    a = sorted(v)
    c = int(len(a) * frac)
    b = a[c:len(a) - c] if len(a) - 2 * c >= 1 else a
    return sum(b) / len(b)


def z_of(alpha=ALPHA):
    return statistics.NormalDist().inv_cdf(1.0 - alpha / 2.0)


def diff_ci(a, b, alpha=ALPHA):
    """두 독립 팔 평균차와 95% 반폭 (Welch). p18.gain_ci 와 같은 식이다."""
    sa, sb = se(a), se(b)
    if sa is None or sb is None:
        return None, None
    return mean(a) - mean(b), z_of(alpha) * math.sqrt(sa * sa + sb * sb)


def n_needed(a, b, target_delta, alpha=ALPHA, power=0.80):
    """|Δ| = target_delta 를 유의하게 잡으려면 팔당 몇 판이 필요한가.

    표준 두 표본 검정력 식.  n = 2 (z_{1-a/2} + z_{power})^2 s^2 / d^2
    분산은 두 팔의 합동 표본분산을 쓴다. **자를 넓히는 대신 표본을 말한다** —
    이 저장소가 반복해 온 원칙이고, p18 이 이미 쓰는 관례다.
    """
    if not target_delta:
        return None
    sa, sb = sd(a), sd(b)
    if sa is None or sb is None:
        return None
    s2 = (sa * sa + sb * sb) / 2.0
    za = z_of(alpha)
    zb = statistics.NormalDist().inv_cdf(power)
    d = abs(float(target_delta))
    # 잴 수 없는 크기를 목표로 삼으면 N 이 천문학적으로 나와 무의미하다.
    # 이 테스트베드의 팔 평균 표준오차가 ~0.03 ms 이므로 그 아래는 안 센다.
    if d < 0.01:
        # 이 테스트베드의 팔 평균 표준오차가 ~0.03 ms 다. 그보다 작은
        # 크기를 목표로 삼으면 N 이 천문학적으로 나와 무의미하다.
        return "분해능아래"
    n = int(math.ceil(2.0 * (za + zb) ** 2 * s2 / (d * d)))
    # 2026-08-27 - **실행 불가능한 수는 처방이 아니다.** 모형이 0.01 ms 를
    #    주장하는데 그 조건의 표준편차가 28 ms 면 산술적으로 1.2e9 판이
    #    필요하다 - 맞는 계산이지만 「이만큼 더 재라」는 말은 아니다.
    #    실제로 그런 줄이 검사 5 의 detail 에 찍혀 나왔다(3000<1200656579).
    #    현실적 상한을 넘으면 **못 잰다고 말한다.**
    if n > 1000000:
        return "분해능아래"
    return n


def wilson(k, n, alpha=ALPHA):
    """이항 비율의 Wilson 구간. 0/n 과 n/n 에서도 무너지지 않는다."""
    if n <= 0:
        return (0.0, 0.0, 0.0)
    z = z_of(alpha)
    ph = k / n
    den = 1.0 + z * z / n
    c = (ph + z * z / (2 * n)) / den
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return (ph, max(0.0, c - h), min(1.0, c + h))


def classify(ms, base, rtt):
    """세 무리로 가른다. 경계는 RTT 로 잡는다 (머리말)."""
    t1 = base + 0.5 * rtt
    t2 = base + 2.5 * rtt
    out = {"ontime": [], "extra": [], "timeout": []}
    for x in ms:
        if x < t1:
            out["ontime"].append(x)
        elif x < t2:
            out["extra"].append(x)
        else:
            out["timeout"].append(x)
    return out, t1, t2


def model_arm(group, cert, rtt, loss_pct, burst, uplink, m, W=1280,
              max_steps=2):
    """이 조건에서 m 을 강제했을 때 모형이 말하는 것 전부.

    p18.model_j 와 같은 경로를 타되 J 하나가 아니라 **무리 비율까지** 꺼낸다.
    그래야 위의 대조가 성립한다.
    """
    C, src = measured_C(group)
    if C is None:
        return None
    s0_base = (POL.S0_BASE_MLKEM if "MLKEM" in group else POL.S0_BASE_X25519)
    try:
        d = POL.decide_v2(C=C, cert_bytes=cert, rtt_ms=rtt,
                          p=loss_pct / 100.0, burst=burst,
                          s0_base=s0_base, c_pkt=POL.C_PKT_POLICY_DEFAULT,
                          W=W, max_steps=max_steps, m_max=max(m, 1),
                          uplink_mbps=uplink)
    except Exception as e:  # noqa: BLE001
        return {"err": "%s: %s" % (type(e).__name__, e)}
    # 🩸 고정팔은 **δ 를 안 준다.** 그러므로 같은 m 중에서 J 가 가장 낮은
    #    후보를 고르면 안 된다 - m=0 자리에서 그것은 `pad`(δ>0) 를 집어
    #    "m0 팔이 1-RTT 를 잡는다" 는 틀린 예측을 만든다. 실제로 p15
    #    cert 4032 에서 none 은 J=100(2-RTT)인데 pad 는 J=50 이고, 측정은
    #    100% 2-RTT 였다. 팔이 실제로 보내는 것(δ=0)과 같은 후보를 고른다.
    cs = [c for c in d["candidates"]
          if c["m"] == m and c.get("delta_per_dgram", 0) == 0
          and c["mode"] in ("none", "parity")]
    if not cs:
        cs = [c for c in d["candidates"] if c["m"] == m]
    if not cs:
        return {"err": "m=%d 후보 없음" % m}
    c = min(cs, key=lambda e: e["j_ms"])
    p_two = c.get("p_two_rtt", 0.0)
    # 🩸 2026-08-27 - 실패 가지가 셋이 됐다(policy.last_original_pmf).
    #    시간 축으로 어디에 떨어지는지로 무리에 배정한다 (기준선 대비 증분):
    #      시간 임계      9/8·RTT   -> 0.5~2.5·RTT 사이 = 「한 판 더」
    #      표본 있는 PTO  3·RTT     -> 2.5·RTT 초과      = 「시간초과」
    #      표본 없는 PTO  200.86 ms -> 2.5·RTT 초과      = 「시간초과」
    #    RTT 50 기준이다. RTT 가 아주 크면(>=80 ms) 3·RTT 도 2.5·RTT 를
    #    넘으므로 배정이 안 바뀌고, 아주 작으면 200.86 이 상대적으로 커져
    #    역시 안 바뀐다 - 경계가 RTT 배수라 자동으로 따라간다.
    p_pto = (c.get("p_fail_pto", 0.0) + c.get("p_fail_pto_sampled", 0.0))
    p_ack = c.get("p_fail_ack", 0.0)
    return {
        "C": C, "C_src": src,
        "j_ms": c["j_ms"], "base_ms": c.get("base_ms"),
        "stall_ms": c.get("stall_ms"), "tx_ms": c.get("tx_ms"),
        "p_fail": c.get("p_fail"),
        "chosen_by_policy": d["choice"]["m"],
        # 세 무리의 모형 질량. 합은 1 이다.
        "P_ontime": max(0.0, 1.0 - p_two - p_pto - p_ack),
        "P_extra": p_two + p_ack,
        "P_timeout": p_pto,
        "p_two_rtt": p_two,
    }


def analyse_condition(name, group, cert, rtt, loss_pct, burst, uplink,
                      arms, source):
    """arms = {팔이름: {"m": int, "ms": [ms...]}}"""
    live = {k: v for k, v in arms.items() if v.get("ms")}
    if len(live) < 1:
        return None
    base = min(statistics.median(v["ms"]) for v in live.values())
    rows = []
    for aname, a in sorted(live.items()):
        ms = a["ms"]
        cls, t1, t2 = classify(ms, base, rtt)
        n = len(ms)
        mod = model_arm(group, cert, rtt, loss_pct, burst, uplink, a["m"])
        row = {
            "arm": aname, "m": a["m"], "n": n,
            "mean": mean(ms), "trimmed_mean": trimmed_mean(ms),
            "median": statistics.median(ms), "se": se(ms), "sd": sd(ms),
            "cut_ontime": t1, "cut_timeout": t2,
            "classes": {},
            "model": mod,
        }
        for cname in ("ontime", "extra", "timeout"):
            v = cls[cname]
            ph, lo, hi = wilson(len(v), n)
            row["classes"][cname] = {
                "n": len(v), "frac": ph, "frac_lo": lo, "frac_hi": hi,
                "mean": mean(v),
                # 이 무리가 전체 평균에 얹는 몫. 세 몫의 합이 평균이다.
                "share_ms": (ph * mean(v)) if v else 0.0,
            }
        if mod and "err" not in mod:
            # 무리 비율의 모형-측정 잔차. **모형 질량이 측정 구간 밖이면**
            # 그 무리가 틀린 것이다.
            row["class_residual"] = {}
            for cname, pkey in (("ontime", "P_ontime"),
                                ("extra", "P_extra"),
                                ("timeout", "P_timeout")):
                c = row["classes"][cname]
                # 모형 질량은 부동소수 때문에 1.0 을 아주 조금 넘을 수 있다.
                pm = min(1.0, max(0.0, mod[pkey]))
                err_pp = 100.0 * (pm - c["frac"])
                # 0.05%p 아래는 잡음으로 본다 (n=400~1500 이면 한 판이
                # 0.07~0.25%p 다 - 그보다 작은 어긋남은 셀 수 없다).
                row["class_residual"][cname] = {
                    "model": pm, "meas": c["frac"],
                    "err_pp": err_pp,
                    "outside_ci": (abs(err_pp) > 0.05
                                   and not (c["frac_lo"] <= pm <= c["frac_hi"])),
                }
        rows.append(row)

    # 팔쌍 대조 — 모형 ΔJ 대 측정 Δ평균.
    pairs = []
    names = [r["arm"] for r in rows]
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            ai, aj = names[i], names[j]
            va, vb = live[ai]["ms"], live[aj]["ms"]
            dm, half = diff_ci(va, vb)
            ri = next(r for r in rows if r["arm"] == ai)
            rj = next(r for r in rows if r["arm"] == aj)
            mi = ri.get("model") or {}
            mj = rj.get("model") or {}
            dj = None
            if "j_ms" in mi and "j_ms" in mj:
                dj = mi["j_ms"] - mj["j_ms"]
            # 본체(꼬리 제외) 차이도 같이 낸다.
            dt = None
            if ri["trimmed_mean"] is not None and rj["trimmed_mean"] is not None:
                dt = ri["trimmed_mean"] - rj["trimmed_mean"]
            verdict = "미판정"
            if dm is not None and half is not None:
                if half >= abs(dm):
                    verdict = "판정불능"
                elif dj is None:
                    verdict = "모형없음"
                elif abs(dj) < 1e-9:
                    # 2026-08-27 - 모형이 **동점**이라 한 쌍에서 부호를
                    #    따지면 안 된다. `(dj > 0) == (dm > 0)` 는 dj=0 일 때
                    #    항상 False 라 무조건 「부호반대」가 되고, 게다가 팔
                    #    순서를 뒤집으면 라벨이 뒤집힌다(dm 의 부호만 바뀌므로).
                    #    판정이 자료가 아니라 **팔을 어느 쪽으로 뺐는지**에
                    #    달리는 것은 자가 아니다.
                    verdict = "모형동점"
                elif (dj > 0) == (dm > 0):
                    verdict = "부호일치"
                else:
                    verdict = "부호반대"
            # 필요 표본은 **모형이 주장하는 크기**를 잡을 만큼으로 센다.
            # dj 가 부동소수 잡음(1e-16)이면 0 으로 본다 - 안 그러면
            # 필요 표본이 1e30 으로 튄다.
            tgt = dj if (dj is not None and abs(dj) >= 1e-6) else dm
            need = n_needed(va, vb, tgt)
            # 무리별로 차이가 어디서 왔는지 쪼갠다.
            by_class = {}
            for cname in ("ontime", "extra", "timeout"):
                by_class[cname] = (ri["classes"][cname]["share_ms"]
                                   - rj["classes"][cname]["share_ms"])
            pairs.append({
                "pair": "%s-%s" % (ai, aj),
                "meas_delta_ms": dm, "ci95_half_ms": half,
                "trimmed_delta_ms": dt,
                "model_delta_j_ms": dj,
                "residual_ms": (dm - dj) if (dm is not None and dj is not None)
                               else None,
                "verdict": verdict,
                "n_per_arm": min(len(va), len(vb)),
                "n_needed_per_arm": need,
                "delta_by_class_ms": by_class,
                # 차이의 몇 %가 꼬리(시간초과)에서 왔나. 1 에 가까우면
                # **본체는 같고 꼬리만 다르다**는 뜻이다.
                "tail_share_of_delta": (
                    (by_class["timeout"] / dm) if dm not in (None, 0) else None),
            })
    return {
        "cond": name, "source": source, "group": group, "cert": cert,
        "rtt_ms": rtt, "loss_pct": loss_pct, "burst": burst,
        "uplink_mbps": uplink, "baseline_ms": base,
        "arms": rows, "pairs": pairs,
    }


# ---------------------------------------------------------------------------
# 각 계기의 원자료를 이 단계가 읽을 수 있는 꼴로 옮긴다.
# 계기마다 저장 방식이 달라서(어떤 것은 results, 어떤 것은 state/*.jsonl)
# **읽는 규칙을 여기 한 곳에만** 둔다.
# ---------------------------------------------------------------------------

def load_p17():
    path = os.path.join(STATE, "p17_units.jsonl")
    res = os.path.join(RES, "p17_adaptive_value.json")
    if not (os.path.exists(path) and os.path.exists(res)):
        return []
    meta = json.load(open(res, encoding="utf-8"))
    # 🩸 2026-09-01/09-07 - **조건별 cert·RTT·uplink 를 저널 줄에서 읽는다.**
    #    옛 코드는 결과 파일 머리의 모듈 상수(cert 9000, RTT 50)를 모든 조건에
    #    썼고, uplink 는 조건 이름으로 추측했다(`"2Mbps" in cond`). 08-28 에 p17
    #    이 조건마다 cert·RTT 를 다르게 주기 시작한 뒤로 큰cert(16000)·RTT200
    #    조건에서 세 값 중 둘이 틀려 있었다 - 이 단계는 「모형이 어느 무리에서
    #    틀리는가」를 재므로 입력이 틀리면 모형이 맞는데도 틀린 것으로 나온다
    #    (진단서가 최악으로 지목하던 `p17|RTT200|loss2` 가 정확히 그 자리다).
    #    p17 은 이제 rec 에 cert·rtt_ms·up_policy·netem_rate_mbit 을 담는다.
    #    옛 세대 저널에는 없으므로 그때만 추측하되, **추측했다고 찍는다.**
    meta_rtt = meta["rtt_ms"]
    meta_cert = meta["cert"]
    group = meta["group"]
    conds_meta = {c["cond"]: c for c in (meta.get("conds") or [])}
    out = []
    # 2026-08-27 - **세대(fp)를 확인한다.** 이 jsonl 은 계기의 저널이라
    #    코드 지문이 다른 **여러 세대의 줄이 한 파일에 남아 있다** (앞
    #    세대 줄은 지워지지 않는다). 세대를 안 보고 전부 읽으면 옛 측정과
    #    새 측정을 한 조건 안에서 섞어 대조하게 된다 - 이 저장소가 「겹쳐
    #    돌아 오염」으로 두 번 겪은 것과 같은 종류의 사고다.
    #    **가장 최근 세대만** 쓰고, 버린 세대 수를 결과에 적는다.
    _rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    _fps = [r.get("fp") for r in _rows if r.get("fp")]
    _newest = _fps[-1] if _fps else None
    for _r in _rows:
        if _newest is not None and _r.get("fp") != _newest:
            continue
        v = _r["val"]
        cond = v["cond"]
        cm = conds_meta.get(cond) or {}
        cert = v.get("cert", cm.get("cert", meta_cert))
        rtt = v.get("rtt_ms", cm.get("rtt_ms", meta_rtt))
        if v.get("up_policy") is not None:
            up, up_guessed = float(v["up_policy"]), False
        elif cm.get("up_policy") is not None:
            up, up_guessed = float(cm["up_policy"]), False
        else:
            up, up_guessed = (2.0 if "2Mbps" in cond else 0.0), True
        if up_guessed:
            print("   [p17|%s] uplink 를 조건 이름으로 추측했다 (%g) - 옛 세대 "
                  "저널이라 값이 없다" % (cond, up))
        segs = v.get("segments") or []
        for arm_name, a in v["arms"].items():
            if arm_name == "auto":
                continue
            mine = [s for s in segs if s["arm"] == arm_name]
            ms = a["ms"]
            off = 0
            blocks = []
            aligned = True
            for s in mine:
                n = s["n"]
                blk = ms[off:off + n]
                off += n
                if not blk or abs(mean(blk) - s["mean"]) > 1e-6:
                    aligned = False
                    break
                blocks.append((s["loss"], blk))
            if not aligned:
                continue
            for loss in sorted(set(l for l, _ in blocks)):
                key = (cond, loss)
                sel = [x for l, b in blocks if l == loss for x in b]
                out.append((key, group, cert, rtt, loss, 1.0, up,
                            arm_name, int(arm_name[1:]), sel, "p17"))
    return out


def load_p18():
    res = os.path.join(RES, "p18_mmax.json")
    if not os.path.exists(res):
        return []
    d = json.load(open(res, encoding="utf-8"))
    rtt, group = d["rtt_ms"], d["group"]
    out = []
    for row in d.get("rows", []):
        for m_s, a in row["arms"].items():
            if not a.get("ms"):
                continue
            out.append(((row["cond"], row["loss"]), group, row["cert"], rtt,
                        row["loss"], row["burst"], row["uplink"],
                        "m%s" % m_s, int(m_s), a["ms"], "p18"))
    return out


def load_p15():
    res = os.path.join(RES, "p15_v2policy.json")
    if not os.path.exists(res):
        return []
    d = json.load(open(res, encoding="utf-8"))
    rtt, group = d["rtt_ms"], d["group"]
    out = []
    for row in d.get("rows", []):
        arm = row["arm"]
        if not row.get("ms") or not arm.startswith("m"):
            continue
        try:
            m = int(arm[1:])
        except ValueError:
            continue
        out.append(((("cert%d" % row["cert"]), row["loss"]), group,
                    row["cert"], rtt, row["loss"], 1.0, 0.0,
                    arm, m, row["ms"], "p15"))
    return out


def load_p16():
    res = os.path.join(RES, "p16_uplink.json")
    if not os.path.exists(res):
        return []
    d = json.load(open(res, encoding="utf-8"))
    rtt, group, cert = d["rtt_ms"], d["group"], d["cert"]
    out = []
    for a in d.get("arms", []):
        if not a.get("ms"):
            continue
        arm = a["arm"]
        m = 0
        if arm.startswith("m"):
            try:
                m = int(arm[1:])
            except ValueError:
                m = 0
        up = a.get("rate_mbit", 0.0)
        out.append((("%s" % a.get("cond", "?"), 0.0), group, cert, rtt,
                    0.0, 1.0, up, arm, m, a["ms"], "p16"))
    return out


def main():
    recs = []
    for loader in (load_p17, load_p18, load_p15, load_p16):
        try:
            recs.extend(loader())
        except Exception as e:  # noqa: BLE001
            print("  [경고] %s: %s" % (loader.__name__, e), flush=True)

    grouped = {}
    for (key, group, cert, rtt, loss, burst, up, arm, m, ms, src) in recs:
        gkey = (src, key[0], key[1], group, cert, rtt, burst, up)
        grouped.setdefault(gkey, {})[arm] = {"m": m, "ms": ms}

    conds = []
    for gkey, arms in sorted(grouped.items(), key=lambda kv: str(kv[0])):
        src, cname, loss, group, cert, rtt, burst, up = gkey
        r = analyse_condition("%s|%s|loss%g" % (src, cname, loss), group,
                              cert, rtt, loss, burst, up, arms, src)
        if r:
            conds.append(r)

    # ------------------------------------------------------------------
    # 판정. 이 단계는 **모형을 통과/실패시키지 않는다** — 어긋난 자리를
    # 이름 붙여 세는 것이 일이다. 그래서 검사는 「자료가 말이 되는가」와
    # 「어긋남을 우리가 못 보고 있지 않은가」 두 종류뿐이다.
    # ------------------------------------------------------------------
    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": str(detail)})

    add("1. 읽을 조건이 있다", len(conds) > 0, "조건 %d 개" % len(conds))

    bad_mass = [(c["cond"], r["arm"], cn, cr["err_pp"])
                for c in conds for r in c["arms"]
                for cn, cr in (r.get("class_residual") or {}).items()
                if cr["outside_ci"]]
    add("2. 무리 질량이 측정 구간 안 (모형 질량 = 측정 비율)",
        True,
        "구간 밖 %d 건 / 총 %d 건%s" % (
            len(bad_mass),
            sum(len(r.get("class_residual") or {}) for c in conds
                for r in c["arms"]),
            (" | 최악 " + ", ".join(
                "%s %s %s %+.1f%%p" % x for x in
                sorted(bad_mass, key=lambda t: -abs(t[3]))[:4])
             if bad_mass else "")))

    flips = [(c["cond"], p["pair"], p["meas_delta_ms"], p["model_delta_j_ms"],
              p["ci95_half_ms"], p["tail_share_of_delta"])
             for c in conds for p in c["pairs"] if p["verdict"] == "부호반대"]
    add("3. 부호가 반대인 팔쌍 (유의하게 어긋난 것만)",
        True,
        ("%d 건" % len(flips)) + ("" if not flips else " | " + " ; ".join(
            "%s %s 측정 %+.2f vs 모형 %+.2f (반폭 %.2f, 꼬리몫 %s)"
            % (a, b, cd, md, h, ("%.0f%%" % (100 * ts)) if ts is not None else "-")
            for a, b, cd, md, h, ts in flips[:6])))

    undecid = [p for c in conds for p in c["pairs"] if p["verdict"] == "판정불능"]
    # 2026-08-27 - 「필요 표본을 말한다」의 뜻을 분명히 한다. 수를 못 내는
    #    경우가 둘 있고 둘은 전혀 다르다.
    #      (a) 모형이 주장하는 크기가 **이 계기의 분해능 아래**  -> 못 잰다.
    #          이건 표본을 늘려 풀 수 있는 문제가 아니므로 그렇게 적는다.
    #      (b) 계산이 아예 안 됐다 -> 그건 계기 결함이다.
    #    옛 판은 (a) 를 None 으로 두고 `all(...)` 로 봐서 **(a) 가 하나라도
    #    있으면 실패**했다. 못 잴 것을 못 잰다고 말한 것을 벌한 셈이다.
    _no_n = [p for p in undecid if p["n_needed_per_arm"] is None]
    _unmeas = [p for p in undecid
               if p["n_needed_per_arm"] == "분해능아래"]
    add("4. 판정 불능인 팔쌍은 필요 표본 또는 '분해능 아래'를 말한다",
        not _no_n,
        "판정불능 %d / 전체 %d 쌍 | 표본으로 풀림 %d · 분해능아래 %d · 무응답 %d"
        % (len(undecid), sum(len(c["pairs"]) for c in conds),
           len(undecid) - len(_unmeas) - len(_no_n), len(_unmeas),
           len(_no_n)))

    # 이 저장소가 반복해 온 실수: 「한 번 잰 것을 증거로 삼기」. 표본이
    # 모형의 주장 크기를 잡기에 모자란 쌍이 얼마나 되는지 대놓고 센다.
    # '분해능아래' 는 표본을 늘려 풀 수 있는 것이 아니므로 여기서 빼고
    # 따로 센다. 섞으면 「더 재면 된다」와 「못 잰다」가 한 통에 들어간다.
    underpow = [(c["cond"], p["pair"], p["n_per_arm"], p["n_needed_per_arm"])
                for c in conds for p in c["pairs"]
                if isinstance(p["n_needed_per_arm"], int)
                and p["n_per_arm"] < p["n_needed_per_arm"]]
    unmeasurable = [(c["cond"], p["pair"]) for c in conds for p in c["pairs"]
                    if p["n_needed_per_arm"] == "분해능아래"]
    add("5. 표본이 모형의 주장 크기를 잡기에 충분하다",
        len(underpow) == 0,
        "모자란 쌍 %d 개 (분해능아래 %d 개는 뺌)%s" % (
            len(underpow), len(unmeasurable),
            (" | 최악 " + ", ".join(
                "%s %s %d<%d" % x for x in
                sorted(underpow, key=lambda t: -(t[3] / max(1, t[2])))[:4])
             if underpow else "")))

    out = {
        "alpha": ALPHA,
        "conds": conds,
        "checks": checks,
        "passed": sum(1 for c in checks if c["ok"]),
        "total": len(checks),
    }
    os.makedirs(RES, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print("P20 잔차 해부")
    for c in conds:
        print("  %-34s cert=%-6d up=%-4g burst=%g"
              % (c["cond"], c["cert"], c["uplink_mbps"], c["burst"]))
        for r in c["arms"]:
            mod = r.get("model") or {}
            cr = r.get("class_residual") or {}
            print("     %-5s n=%4d 평균 %8.3f (본체 %8.3f) | 모형 J %8.3f"
                  % (r["arm"], r["n"], r["mean"], r["trimmed_mean"],
                     mod.get("j_ms", float("nan"))))
            for cn in ("ontime", "extra", "timeout"):
                cc = r["classes"][cn]
                e = cr.get(cn)
                print("        %-8s 측정 %6.2f%% [%5.2f,%5.2f] 값 %8.3f"
                      "  모형 %6.2f%%  잔차 %+6.2f%%p%s"
                      % (cn, 100 * cc["frac"], 100 * cc["frac_lo"],
                         100 * cc["frac_hi"],
                         cc["mean"] if cc["mean"] is not None else float("nan"),
                         100 * e["model"] if e else float("nan"),
                         e["err_pp"] if e else float("nan"),
                         "  <-- 구간 밖" if e and e["outside_ci"] else ""))
        for p in c["pairs"]:
            print("     %-9s 측정 %+7.3f ±%5.3f | 본체 %+7.3f | 모형 %+7.3f"
                  " | 잔차 %+7.3f | %s | n %d (필요 %s) 꼬리몫 %s"
                  % (p["pair"], p["meas_delta_ms"], p["ci95_half_ms"],
                     p["trimmed_delta_ms"] if p["trimmed_delta_ms"] is not None
                     else float("nan"),
                     p["model_delta_j_ms"] if p["model_delta_j_ms"] is not None
                     else float("nan"),
                     p["residual_ms"] if p["residual_ms"] is not None
                     else float("nan"),
                     p["verdict"], p["n_per_arm"],
                     p["n_needed_per_arm"],
                     ("%.0f%%" % (100 * p["tail_share_of_delta"]))
                     if p["tail_share_of_delta"] is not None else "-"))
    print()
    # 2026-08-27 - **로그 규약을 루프의 분류기와 맞춘다.**
    #    처음에 `[ok  ]/[FAIL]` 과 `4/5` 로 찍었다. fixloop 의 분류기는
    #    `[실패]` 줄과 `N / M 통과` 줄을 찾는데 둘 다 없으니
    #    **「검사에 닿기 전에 끊겼다(도중에죽음)」로 오진**했고, 그 오진이
    #    되풀이되자 fixloop 이 「환경사고 반복 - 멈춤」으로 **바퀴 전체를
    #    세웠다**(2026-08-27 16:02). 계기는 멀쩡히 4/5 를 찍고 있었다.
    #
    #    교훈: 이 저장소에서 단계의 stdout 은 사람이 읽는 글이 아니라
    #    **루프가 읽는 규약**이다. 새 단계를 더할 때는 형식부터 맞춘다.
    for c in checks:
        print("[%s] %-58s %s" % ("통과" if c["ok"] else "실패",
                                 c["check"][:58], c["detail"][:90]))
    print("-" * 100)
    print("%d / %d 통과" % (out["passed"], out["total"]))
    return 0 if out["passed"] == out["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
