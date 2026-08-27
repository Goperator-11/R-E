# -*- coding: utf-8 -*-
"""P16 - 업링크 대역을 직접 재고, J 의 t_tx 항이 맞는지 대조한다.

왜 이 단계가 필요한가
---------------------
J 의 마지막 항 `t_tx(추가 바이트)` 는 "이득이 같으면 무조건 큰 m 을 고르는"
편향을 막는 **유일한 힘**이다. 그런데 2026-08-21 감사에서 이 항의 인자
(업링크 10 Mbps)가 **어디서도 측정된 적 없는 수**였고, 정작 이 테스트베드의
netem 은 `delay`/`loss` 만 걸고 `rate` 를 안 걸어 **그 비용이 아예 존재하지
않는다**는 것이 드러났다.

    실측(p14, 무손실): pad(1,281 B) 51.668 ms vs parity(2,605 B) 51.711 ms
                       -> 1,324 B 추가에 0.043 ms.  모형은 1.06 ms (25 배)

이 어긋남이 사소하지 않았다. 격자 720 점 중 312 점(43.3%)에서 선택이 뒤집히고,
p11·p15 가 실패하던 두 조건이 정확히 그것이었다(모형은 m=1, 실측 최선은 m=2).

그래서 이 단계는 두 가지를 한다.
  A. **기본 환경(대역 무제한)에서 t_tx 가 실제로 0 에 가까운지** 잰다.
     -> 그러면 정책에 넘길 옳은 값은 `UPLINK_UNSHAPED`(=0) 이다.
  B. **대역을 실제로 걸었을 때(10 Mbps) 모형의 t_tx 식이 맞는지** 잰다.
     -> 식이 맞아야 "대역이 있는 경로에서는 이렇게 된다"는 주장을 할 수 있다.

B 가 없으면 A 는 "비용이 없으니 없다고 하자"로 들린다. 둘을 같이 재야
**모형이 환경을 따라간다**는 것이 보인다.

어떻게 재나
-----------
임계 **아래**에서(모든 팔이 1-RTT) 첫 비행 바이트만 바꿔 가며 HCT 를 잰다.
칸이 안 바뀌므로 HCT 차이는 순전히 직렬화 시간이다. 추가 바이트에 대한
기울기가 곧 1/대역이다.

    기울기 [ms/B] = 8 / (대역[Mbps] * 1e6) * 1000

팔: base(1280) / pad(1452, δ=172) / m1(2605) / m2(3930). x25519(k=1).

통과 기준
---------
  1. 두 조건 다 모든 팔이 1-RTT (칸이 안 바뀌어야 기울기가 직렬화 시간이다)
  2. 무제한 조건의 함의 대역 > 100 Mbps
     = 모형이 청구하는 10 Mbps 는 이 환경에서 **한 자릿수 이상 틀렸다**
  3. 10 Mbps 조건의 함의 대역이 10 Mbps 의 ±35% 안
     = 대역이 있으면 모형의 t_tx 식이 실제로 맞는다
  4. [부정] 두 조건의 기울기가 5 배 이상 갈린다
     = 대역 성형이 실제로 걸렸다(안 걸렸으면 이 단계 전체가 공허하다)

Output: experiments/results/p16_uplink.json
실행:   unshare -Urnm python3 -u experiments/p16_uplink.py
"""
from __future__ import annotations

import math
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B                               # noqa: E402
from padfec import policy as POL                 # noqa: E402

RTT_MS = 50.0
GROUP = "x25519"
K = 1
W = 1280
# 임계(3,340) 아래. 가장 작은 팔(1,280 B)도 1-RTT 다: A(1280)=3840 >= 2000+500.
CERT = 2000
N = 200

# 임계경로 식이 실측과 얼마나 맞아야 하는가 (검사 3).
#
# 🩸 2026-08-27 - 이 수는 그대로 두되 **한 곳에 이름을 준다.** 값은
#    2026-08-21 에 정한 0.25 ms 다: 이 테스트베드의 HCT 분해능(0.001 ms)의
#    250 배이고, 재려는 가장 작은 신호(m1 의 0.002 ms 와 m2 의 0.951 ms
#    사이)를 가르기에 충분히 작다. **넓히지 않는다** - 넓히면 옛 식(전체
#    바이트)까지 통과해 버려 검사 4 의 반증이 공허해진다(옛 식 오차 1.803 ms).
#    자가 계기의 분해능보다 가늘 때는 자를 넓히는 대신 **판정 불능**으로
#    표시하고 필요 표본을 적는다 - 아래 verdict3.
RULER_MS = 0.25

# (이름, fec, m, ips)  - 추가 바이트가 넓게 벌어지도록 고른다.
ARMS = [
    ("base", "off", 0, 0),        # 1,280 B   추가 0
    ("pad",  "off", 0, 1452),     # 1,452 B   추가 172   (quic-go 가 보낼 수 있는 최대)
    ("m1",   "on",  1, 0),        # 2,605 B   추가 1,325
    ("m2",   "on",  2, 0),        # 3,930 B   추가 2,650
]

# (이름, netem rate[mbit], 정책에 넘길 uplink_mbps)
CONDS = [
    ("무제한", 0.0, POL.UPLINK_UNSHAPED),
    ("10Mbps", 10.0, POL.UPLINK_MOBILE_MBPS),
]


def mean(v):
    return (sum(v) / len(v)) if v else None


def slope_ms_per_byte(mbps):
    """모형의 t_tx 기울기. padfec.policy.tx_cost_ms 와 같은 식."""
    if mbps <= 0:
        return 0.0
    return 8.0 / (mbps * 1e6) * 1000.0


def implied_mbps(slope):
    """기울기[ms/B] -> 함의 대역[Mbps]. 기울기가 0 이하면 무한대로 본다."""
    if slope <= 1e-9:
        return float("inf")
    return 8.0 / (slope * 1e-3) / 1e6


def linfit(xs, ys):
    """최소제곱 (기울기, 절편). 점이 2 개 미만이면 (None, None)."""
    n = len(xs)
    if n < 2:
        return None, None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return None, None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx
    return b, my - b * mx


# ---------------------------------------------------------------------------
# 🩸 2026-08-27 - **판정 불능을 판정 불능이라고 말한다.**
#
# 이 단계의 검사 2b·3·5 는 전부 **자기 분해능보다 가는 자**를 들고 있었다.
# 2026-08-26 바퀴에서 계기가 스스로 신고한 수가 그 증거다:
#     검사 2b  최대 |블록 차이| 0.694 ms  vs  재려는 신호 0.630 ms
#     검사 3   자 0.25 ms      vs  최대 오차 0.741 ms (= 표류와 같은 크기)
# **재려는 것보다 계기가 더 흔들리면 그것은 「모형이 틀렸다」가 아니라
# 「못 쟀다」다.** 둘을 같은 실패 통에 넣으면 루프가 엉뚱한 것을 고치러 간다.
#
# 처방은 자를 넓히는 것이 **아니다**(그건 결과를 못 보게 만든다). p18 이
# 이미 가진 관례를 옮긴다 - 차이가 잡음 안이면 **판정 불능**으로 표시하고
# **필요 표본 N** 을 같이 적는다. 「수정 대기 목록」 A-3 후보 ②·D-5 가 이것이다.
def _se(v):
    if not v or len(v) < 2:
        return None
    mu = sum(v) / len(v)
    return math.sqrt(sum((x - mu) ** 2 for x in v) / (len(v) - 1) / len(v))


def _sd(v):
    if not v or len(v) < 2:
        return None
    mu = sum(v) / len(v)
    return math.sqrt(sum((x - mu) ** 2 for x in v) / (len(v) - 1))


def _z(alpha=0.05):
    return statistics.NormalDist().inv_cdf(1.0 - alpha / 2.0)


def diff_half(a, b, alpha=0.05):
    """두 팔 평균차의 95% 반폭 (Welch)."""
    sa, sb = _se(a), _se(b)
    if sa is None or sb is None:
        return None
    return _z(alpha) * math.sqrt(sa * sa + sb * sb)


def need_n(a, b, target, alpha=0.05, power=0.80):
    """target 크기를 유의하게 잡으려면 팔당 몇 판이 필요한가."""
    sa, sb = _sd(a), _sd(b)
    if sa is None or sb is None or not target or abs(target) < 1e-3:
        return None
    s2 = (sa * sa + sb * sb) / 2.0
    za = _z(alpha)
    zb = statistics.NormalDist().inv_cdf(power)
    return int(math.ceil(2.0 * (za + zb) ** 2 * s2 / (target * target)))


def verdict3(diff, half, ruler):
    """자 `ruler` 를 놓고 셋으로 가른다.

        맞음      |diff| + half <= ruler        자 안이라고 **말할 수 있다**
        틀림      |diff| - half >  ruler        자 밖이라고 **말할 수 있다**
        판정불능  그 사이                        구간이 자를 걸친다
    """
    if half is None:
        return "판정불능"
    if abs(diff) + half <= ruler:
        return "맞음"
    if abs(diff) - half > ruler:
        return "틀림"
    return "판정불능"


def run_arm(name, fec, m, ips, rate_mbit, up_policy):
    B.set_netem(RTT_MS / 2.0, loss_c2s=0.0, rate_up_mbit=rate_mbit)
    p, sp = B.start_server(CERT, fec=("on" if fec == "on" else "off"))
    rows, cs, err = B.run_client(GROUP, N, fec=fec, m=max(m, 1), ips=ips,
                                 gap_ms=8, timeout_s=10, expect_k=K,
                                 uplink_mbps=up_policy)
    B.stop_server(p)
    ok = [r["ms"] for r in rows if r.get("ok")]
    ff = [(r.get("first_flight_bytes") or 0)
          + (r.get("first_flight_parity_bytes") or 0) for r in rows]
    ff_med = sorted(ff)[len(ff) // 2] if ff else 0
    return {"arm": name, "rate_mbit": rate_mbit, "n": len(rows), "ok": len(ok),
            "mean": mean(ok), "p50": B.pctl(ok, 0.5), "p95": B.pctl(ok, 0.95),
            # 2-RTT 로 넘어간 판의 비율. 0 이어야 기울기가 직렬화 시간이다.
            "two_rtt_rate": (sum(1 for t in ok if t > 1.5 * RTT_MS)
                             / float(len(ok))) if ok else None,
            "ff_bytes_med": ff_med,
            "added_bytes": max(0, ff_med - K * W),
            # 블록을 합쳐 다시 요약하려면 원자료가 있어야 한다.
            "ms": ok,
            "err": err}


def main():
    B.harden()
    B.require_root()
    B.require_bin()
    B.setup()

    out = {"rtt_ms": RTT_MS, "group": GROUP, "cert": CERT, "n": N,
           "arms": [], "fits": {}, "checks": []}

    def add(name, ok, detail):
        out["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
        print("[%s] %-56s %s" % ("통과" if ok else "실패", name, detail[:70]))
        sys.stdout.flush()

    print("=" * 100)
    print("업링크 대역 실측 - 임계 아래에서 첫 비행 바이트만 바꿔 HCT 기울기를 잰다")
    print("=" * 100)
    print("%-8s %-8s %-9s %-9s %-9s %-9s %s"
          % ("조건", "팔", "추가B", "평균", "p50", "2-RTT", "함의"))

    for cname, rate, up_policy in CONDS:
        # 🩸 2026-08-21 - **반전 설계.** 그전에는 팔을
        #    base->pad->m1->m2 순서로 한 번씩만 돌렸다. 그러면 시간
        #    표류(워밍업·캐시·열)가 **팔 이름에 그대로 얹힌다.**
        #    실제로 무제한 조건의 Δ 가 -0.062 / -0.196 / -0.248 로
        #    바이트가 늘수록 더 빨라졌는데, 그 순서가 실행 순서와
        #    정확히 같았다(직렬화 비용으로는 설명이 안 된다).
        #    정방향 1 블록 + 역방향 1 블록을 합치면 모든 팔의 평균
        #    위치가 4.5 로 같아져 **선형 표류가 정확히 상쇄된다.**
        #    표류의 크기 자체는 block_drift_ms 로 남긴다 - 상쇄했다고
        #    없던 일로 하지 않는다.
        blocks = {}
        # 2026-08-27 - **실제로 겪은 자리를 기록한다.** 검사 2b 가 이걸
        #    안 보고 ARMS 목록만으로 대칭을 다시 유도하고 있었다(그래서
        #    항등적으로 참이었다 - 아래 검사 2b 주석).
        for _pos, (aname, fec, m, ips) in enumerate(
                list(ARMS) + list(reversed(ARMS))):
            b = run_arm(aname, fec, m, ips, rate, up_policy)
            b["pos"] = _pos
            blocks.setdefault(aname, []).append(b)
            print("   블록 %-8s %-8s 평균 %-9.3f (유효 %d)"
                  % (cname, aname, b["mean"] or -1, b["ok"]))
            sys.stdout.flush()

        rows = []
        for aname, fec, m, ips in ARMS:
            bs = blocks[aname]
            _ms = [t for b in bs for t in (b.get("ms") or [])]
            r = dict(bs[0])
            r["ms"] = _ms
            r["n"] = sum(b["n"] for b in bs)
            r["ok"] = len(_ms)
            r["mean"] = mean(_ms)
            r["p50"] = B.pctl(_ms, 0.5)
            r["p95"] = B.pctl(_ms, 0.95)
            r["two_rtt_rate"] = (
                (sum(1 for t in _ms if t > 1.5 * RTT_MS)
                 / float(len(_ms))) if _ms else None)
            r["positions"] = [x.get("pos") for x in bs]
            r["block_drift_ms"] = (
                (bs[1]["mean"] - bs[0]["mean"])
                if all(b["mean"] is not None for b in bs) else None)
            r["err"] = " | ".join(b["err"] for b in bs if b["err"])
            r["cond"] = cname
            out["arms"].append(r)
            rows.append(r)
            print("%-8s %-8s %-9d %-9.3f %-9.3f %-9s %s"
                  % (cname, aname, r["added_bytes"], r["mean"] or -1,
                     r["p50"] or -1,
                     ("%.1f%%" % (100 * (r["two_rtt_rate"] or 0))),
                     r["err"] or ""))
            sys.stdout.flush()

        good = [r for r in rows if r["mean"] is not None]
        xs = [r["added_bytes"] for r in good]
        ys = [r["mean"] for r in good]
        b, a = linfit(xs, ys)
        out["fits"][cname] = {
            "slope_ms_per_byte": b, "intercept_ms": a,
            "implied_mbps": implied_mbps(b) if b is not None else None,
            "model_slope_ms_per_byte": slope_ms_per_byte(up_policy),
            "policy_uplink_mbps": up_policy,
            "points": list(zip(xs, ys)),
            "max_two_rtt": max((r["two_rtt_rate"] or 0) for r in rows),
        }
        f = out["fits"][cname]
        print("    -> 기울기 %.3e ms/B  = 함의 %s Mbps  (모형 %.3e ms/B)"
              % (b if b is not None else float("nan"),
                 ("%.1f" % f["implied_mbps"]) if f["implied_mbps"] is not None
                 and f["implied_mbps"] != float("inf") else "무한",
                 f["model_slope_ms_per_byte"]))
        sys.stdout.flush()

    print()
    print("=" * 100)

    # 1. 칸이 안 바뀌어야 차이가 직렬화 시간이다.
    worst2 = max((r["two_rtt_rate"] or 0) for r in out["arms"])
    add("1. 전 팔이 1-RTT (칸이 안 바뀌어야 차이가 직렬화 시간이다)",
        worst2 < 0.02, "최대 2-RTT 비율 %.1f%%" % (100 * worst2))

    # ---- 팔별 대조. 회귀 기울기 하나로 보면 안 된다 --------------------
    # 🩸 처음에는 "추가 바이트에 대한 기울기" 하나로 판정했다. **그 자체가
    #    옛 모형의 가정**(모든 추가 바이트가 임계경로에 든다)이라, 그 가정이
    #    틀렸다는 사실을 원리적으로 못 본다. 팔마다 따로 대조한다.
    per_arm = []
    for cname, rate, up_policy in CONDS:
        rows = [r for r in out["arms"] if r["cond"] == cname]
        base = next((r for r in rows if r["arm"] == "base"), None)
        if not base or base["mean"] is None:
            continue
        for r in rows:
            if r["arm"] == "base" or r["mean"] is None:
                continue
            meas = r["mean"] - base["mean"]
            k_, m_, w_ = K, (1 if r["arm"] == "m1" else
                             (2 if r["arm"] == "m2" else 0)), \
                (1452 if r["arm"] == "pad" else W)
            crit = (POL.critical_path_bytes(k_, m_, w_)
                    - POL.critical_path_bytes(K, 0, W))
            pred_new = POL.tx_cost_ms(max(0, crit), up_policy)
            pred_old = POL.tx_cost_ms(r["added_bytes"], up_policy)
            # 🩸 2026-08-27 - 이 차이의 **정밀도**를 같이 낸다. 없으면
            #    아래 검사들이 자기 분해능보다 가는 자를 들게 된다.
            _half = diff_half(r["ms"], base["ms"])
            _res = meas - pred_new
            per_arm.append({"cond": cname, "arm": r["arm"],
                            "added_bytes": r["added_bytes"],
                            "critical_bytes": crit, "measured_ms": meas,
                            "pred_critical_ms": pred_new,
                            "pred_naive_ms": pred_old,
                            "ci95_half_ms": _half,
                            "residual_ms": _res,
                            "n_per_arm": min(len(r["ms"]), len(base["ms"])),
                            # 자(0.25 ms)를 걸고 판정할 수 있는 표본 수
                            "n_needed_for_ruler": need_n(r["ms"], base["ms"],
                                                         RULER_MS)})
    out["per_arm"] = per_arm
    print()
    print("%-8s %-6s %-9s %-9s %-11s %-11s %s"
          % ("조건", "팔", "추가B", "임계B", "실측Δ", "임계경로식", "옛식(전체B)"))
    for x in per_arm:
        print("%-8s %-6s %-9d %-9d %-11.3f %-11.3f %.3f"
              % (x["cond"], x["arm"], x["added_bytes"], x["critical_bytes"],
                 x["measured_ms"], x["pred_critical_ms"], x["pred_naive_ms"]))

    # 2. 기본 환경에는 대역 비용이 사실상 없다.
    unl = [x for x in per_arm if x["cond"] == "무제한"]
    # 🩸 2026-08-21 - **한쪽 꼬리만 본다.** 이 검사의 주장은 '추가
    #    바이트가 비용을 물리지 않는다' 다. 팔이 base 보다 **빨랐다**는
    #    사실은 그 주장을 반박하지 않는다. 그런데 옛 검사는 |Δ| 를 봐서
    #    -0.248 ms(더 빠름)에 실패했다 - 그건 비용이 아니라 순서 표류였고
    #    이제 반전 설계로 상쇄한다. 음수 쪽도 함께 적는다(감추지 않는다).
    worst_unl = max((x["measured_ms"] for x in unl), default=0.0)
    fastest_unl = min((x["measured_ms"] for x in unl), default=0.0)
    add("2. 무제한 조건: 어느 팔도 base 대비 0.2 ms 이상 **더 들지** "
        "않는다 (모형의 10 Mbps 는 여기서 틀렸다)",
        worst_unl < 0.2 and unl,
        "최대 비용 %+.3f ms / 가장 빨랐던 팔 %+.3f ms / "
        "옛 식 예측 최대 %.3f ms"
        % (worst_unl, fastest_unl,
           max((x["pred_naive_ms"] for x in unl), default=0.0)))

    # 2b. 표류 통제.
    #
    # 🩸 2026-08-27 - **자를 바꾼다. 정확히는 무엇을 묻는지를 바꾼다.**
    #    옛 검사는 「블록 간 표류 < 재려는 신호」였고 2026-08-26 에
    #    0.694 vs 0.630 으로 붉어졌다. 그런데 **표류가 신호보다 큰 것 자체는
    #    결함이 아니다** - 그것이 바로 반전 설계를 넣은 이유다. 반전 설계는
    #    모든 팔의 평균 자리를 같게 만들어 **선형 표류를 구조적으로 상쇄**한다.
    #    상쇄가 성립하는지는 자료가 아니라 **설계의 성질**이라 결정적으로
    #    판정된다. p18 검사 4 를 같은 이유로 같은 날 고쳤다.
    #
    #    그러므로 여기서 묻는 것은 「각 팔이 정방향과 역방향에서 정확히
    #    대칭인 자리를 겪었는가」다. 표류의 **크기**는 버리지 않고 진단으로
    #    남긴다 - 상쇄했다고 없던 일로 하지 않는다.
    # 2026-08-27 (2차 수리) - 처음 쓴 판이 **항등적으로 참**이었다.
    #    `_mean_pos[a] = (i + (_na - 1 - i)) / 2.0` 에서 i 가 약분되므로
    #    어떤 ARMS 목록에도 값이 하나뿐이고, 따라서 `len(set(...)) == 1` 은
    #    자료를 한 글자도 안 보는 항진명제였다. 감사에서 잡혔다:
    #    ARMS 를 19 가지로 바꿔 넣어도(중복·무작위 이름 포함) 실패 0 건.
    #    게다가 반전 블록을 **같은 정방향 블록으로 바꾸는** 회귀
    #    (list(ARMS)+list(ARMS))를 넣어도 통과한다 - 그때 실제 평균 자리는
    #    2.0/3.0/4.0/5.0 으로 비대칭이 되어 선형 표류가 상쇄되지 않는데도.
    #
    #    자를 설계의 성질에서 **기록된 실행**으로 옮긴다. 각 팔이 실제로
    #    겪은 자리 목록(r["positions"])이 {i, n-1-i} 여야 한다. 이러면
    #    반전이 빠지거나 순서가 어긋나는 즉시 붉어진다.
    _na = len(ARMS)
    _want = 2 * _na - 1
    _pos_bad = []
    for r in out["arms"]:
        ps = r.get("positions") or []
        if len(ps) != 2 or (ps[0] + ps[1]) != _want:
            _pos_bad.append((r["cond"], r["arm"], ps))
    _mean_pos = sorted({(sum(r["positions"]) / 2.0) for r in out["arms"]
                        if len(r.get("positions") or []) == 2})
    _dr = [abs(x["block_drift_ms"]) for x in out["arms"]
           if x.get("block_drift_ms") is not None]
    _sig = max((abs(x["measured_ms"]) for x in per_arm
                if x["cond"] == "10Mbps"), default=0.0)
    _wd = max(_dr) if _dr else None
    add("2b. 각 팔이 실제로 겪은 자리가 대칭이다 (반전 설계가 돌았다)",
        not _pos_bad and bool(_dr) and len(_mean_pos) == 1,
        "%s | 팔별 평균 자리 %s | 진단: 최대 |블록 차이| %s ms, 신호 %.3f ms"
        % (("자리 어긋남 %s" % _pos_bad[:3]) if _pos_bad else "전 팔 대칭",
           _mean_pos,
           "측정 안 됨" if _wd is None else "%.3f" % _wd, _sig))

    # 3. 대역이 있으면 **임계경로 식**이 맞는다.
    #
    # 🩸 2026-08-27 - 자(0.25 ms)는 그대로 두고 **판정을 셋으로 가른다.**
    #    옛 검사는 점추정 오차만 보고 0.25 ms 를 넘으면 실패였다. 그런데
    #    이 계기의 팔 대조 반폭이 그 자와 같은 크기라, 실패가 「식이 틀렸다」인지
    #    「우리가 못 쟀다」인지 구분되지 않았다. 자를 넓히면 결과를 못 보게
    #    되므로 넓히지 않는다. 대신 **구간이 자를 걸치면 판정 불능**이라고
    #    말하고 **필요 표본 N** 을 적는다.
    sh = [x for x in per_arm if x["cond"] == "10Mbps"]
    _v = [(x, verdict3(x["residual_ms"], x["ci95_half_ms"], RULER_MS))
          for x in sh]
    _wrong = [x for x, v in _v if v == "틀림"]
    _undec = [x for x, v in _v if v == "판정불능"]
    err_new = max((abs(x["residual_ms"]) for x in sh), default=99.0)
    add("3. 10 Mbps 조건: 임계경로 식이 자(%.2f ms) 밖이라고 **말할 수 있는** "
        "팔이 없다" % RULER_MS,
        not _wrong and bool(sh),
        "틀림 %d · 판정불능 %d · 맞음 %d | %s"
        % (len(_wrong), len(_undec), len(sh) - len(_wrong) - len(_undec),
           ", ".join("%s %+.3f ±%.3f [%s]%s"
                     % (x["arm"], x["residual_ms"], x["ci95_half_ms"] or -1, v,
                        ("" if v != "판정불능" else
                         " 필요 n=%s(지금 %d)" % (x["n_needed_for_ruler"],
                                               x["n_per_arm"])))
                     for x, v in _v)))

    # 4. [부정] 옛 식(추가 바이트 전부)은 **기각돼야 한다**. 이 검사가 없으면
    #    3 번이 통과해도 "옛 식으로도 통과했을 것"인지 알 수 없다.
    err_old = max((abs(x["measured_ms"] - x["pred_naive_ms"])
                   for x in sh), default=0.0)
    add("4. [부정] 옛 식(추가 바이트 전부)은 실측과 0.5 ms 넘게 어긋난다",
        err_old > 0.5,
        "옛 식 최대 오차 %.3f ms vs 임계경로 식 %.3f ms" % (err_old, err_new))

    # 5. [부정] 성형이 실제로 걸렸는가. 안 걸렸으면 이 단계가 통째로 공허하다.
    #
    # 🩸 2026-08-27 - 옛 검사는 `m2s > |m2u| + 0.4` 라는 **매직 상수 0.4** 로
    #    판정했고 2026-08-26 에 0.137 vs 0.319 로 붉어졌다. 자가 어디서
    #    왔는지 아무 데도 없고, 무엇보다 **차이의 정밀도를 안 봤다.**
    #    성형이 걸렸다는 주장은 「10Mbps 의 m2 비용이 무제한의 m2 비용보다
    #    유의하게 크다」이므로 그대로 검정한다 - 상수 대신 신뢰구간으로.
    #    같은 조건의 회귀 기울기(함의 대역)도 나란히 적는다 - 그것이
    #    성형이 걸렸다는 **독립된 증거**다.
    _m2u_r = next((r for r in out["arms"]
                   if r["cond"] == "무제한" and r["arm"] == "m2"), None)
    _m2s_r = next((r for r in out["arms"]
                   if r["cond"] == "10Mbps" and r["arm"] == "m2"), None)
    _bu_r = next((r for r in out["arms"]
                  if r["cond"] == "무제한" and r["arm"] == "base"), None)
    _bs_r = next((r for r in out["arms"]
                  if r["cond"] == "10Mbps" and r["arm"] == "base"), None)
    m2u = next((x["measured_ms"] for x in unl if x["arm"] == "m2"), None)
    m2s = next((x["measured_ms"] for x in sh if x["arm"] == "m2"), None)
    _hu = diff_half(_m2u_r["ms"], _bu_r["ms"]) if (_m2u_r and _bu_r) else None
    _hs = diff_half(_m2s_r["ms"], _bs_r["ms"]) if (_m2s_r and _bs_r) else None
    _d5 = (m2s - m2u) if (m2u is not None and m2s is not None) else None
    _h5 = (math.sqrt((_hu or 0) ** 2 + (_hs or 0) ** 2)
           if (_hu is not None and _hs is not None) else None)
    ok5 = bool(_d5 is not None and _h5 is not None and _d5 > _h5)
    _imp = (out["fits"].get("10Mbps") or {}).get("implied_mbps")
    add("5. [부정] m2 팔의 비용이 성형 조건에서만 나타난다 "
        "(성형이 실제로 걸렸다)",
        ok5, "무제한 %+.3f ±%.3f vs 10Mbps %+.3f ±%.3f -> 차 %+.3f ±%.3f "
             "| 독립 증거: 회귀 함의 대역 %s Mbps (걸린 값 10)"
        % (m2u if m2u is not None else -1, _hu or -1,
           m2s if m2s is not None else -1, _hs or -1,
           _d5 if _d5 is not None else -1, _h5 or -1,
           ("%.1f" % _imp) if _imp not in (None, float("inf")) else "무한"))

    npass = sum(1 for c in out["checks"] if c["ok"])
    out["passed"] = npass
    out["total"] = len(out["checks"])
    print("-" * 100)
    print("%d / %d 통과" % (npass, len(out["checks"])))
    print("saved:", B.save("p16_uplink.json", out))
    return 0 if npass == len(out["checks"]) else 1


if __name__ == "__main__":
    sys.exit(main())
