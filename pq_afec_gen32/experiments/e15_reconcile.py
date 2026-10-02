# -*- coding: utf-8 -*-
"""
E15 - reconcile the model with the real quic-go measurement

E7 (model on measured traces) says the ML-KEM handshake has a LOWER mean
completion time than X25519.  E12 (real quic-go on real netem) says ML-KEM has
a HIGHER median.  Either one of them is wrong, or they are measuring different
statistics of the same distribution.  This settles it.

The mechanism under test:
  * X25519's ClientHello is ONE Initial packet.  If it is lost the server
    receives nothing, sends no ACK, and the client has no RTT sample - so
    recovery goes through PTO (~999 ms).  Low probability, huge penalty.
  * ML-KEM's ClientHello is TWO Initial packets.  Losing one still leaves the
    server able to ACK the survivor, so recovery is time-threshold based
    (~2 RTT).  Higher probability of being hit, much smaller penalty.

If that is right, the two experiments must disagree in exactly this pattern:
ML-KEM worse at the median (more packets = more chance of being touched at
all), ML-KEM no worse - possibly better - in the mean and the tail (its
failure mode is cheaper).

Output: experiments/results/e15_reconcile.json
"""
import argparse
import json
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RESULTS = os.path.join(HERE, "results")
sys.path.insert(0, ROOT)

from afec import profile                              # noqa: E402
from afec.channel import GilbertElliott               # noqa: E402
from afec.controller import pto_ms                    # noqa: E402
from afec.sim import ChannelSampler                   # noqa: E402


def _harden():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


def handshake_quantiles(k_client, k_server, r_client, r_server,
                        p, burst, rtt_ms, trials, seed=11,
                        ack_partial=True):
    """Same mechanics as afec.sim.simulate_handshake, but keeps the whole
    distribution so we can compare quantiles, not just the mean."""
    rng = random.Random(seed)
    ch = GilbertElliott.from_burst(p, burst)
    times = []
    for _ in range(trials):
        sampler = ChannelSampler(ch, rng)
        t = rtt_ms
        for k, r in ((k_client, r_client), (k_server, r_server)):
            attempt = 0
            while True:
                mask = sampler.send(k + r)
                n_lost = sum(mask)
                if n_lost <= r:
                    break
                if ack_partial and n_lost < k + r:
                    t += 2.0 * rtt_ms
                else:
                    t += pto_ms(backoff=attempt)
                sampler.reset_state()
                attempt += 1
                if attempt > 6:
                    break
        times.append(t)
    times.sort()

    def q(f):
        return times[min(int(f * (len(times) - 1)), len(times) - 1)]
    return {"n": len(times), "mean": statistics.fmean(times),
            "p50": q(0.50), "p90": q(0.90), "p95": q(0.95), "p99": q(0.99),
            "max": times[-1],
            "untouched_frac": sum(1 for x in times if x <= rtt_ms + 1e-9) / len(times)}


def main():
    _harden()
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=60000)
    ap.add_argument("--rtt", type=float, default=20.0)
    a = ap.parse_args()

    base = profile(None)          # x25519
    mk = profile(768)             # X25519MLKEM768
    print("=" * 92)
    print("E15 - 모델과 실제 quic-go 측정의 대조")
    print("=" * 92)
    print("플라이트 패킷 수: x25519 = %d(client) + %d(server), "
          "ML-KEM = %d + %d" % (base.k_client, base.k_server,
                                mk.k_client, mk.k_server))
    print("")

    conds = [("uniform_p2", 0.02, 1.0), ("uniform_p5", 0.05, 1.0),
             ("uniform_p10", 0.10, 1.0), ("burst_p5_L4", 0.05, 4.0),
             ("burst_p5_L8", 0.05, 8.0)]

    out = {"rtt_ms": a.rtt, "trials": a.trials,
           "packets": {"x25519": [base.k_client, base.k_server],
                       "mlkem": [mk.k_client, mk.k_server]},
           "conditions": {}}

    print("%-13s %-8s %8s %8s %8s %8s %9s" %
          ("condition", "arm", "p50", "mean", "p95", "p99", "무손실비율"))
    print("-" * 92)
    for cname, p, L in conds:
        row = {}
        arms = [("x25519", base.k_client, base.k_server, 0, 0),
                ("mlkem", mk.k_client, mk.k_server, 0, 0),
                ("mlkem_fec", mk.k_client, mk.k_server, 1, 1)]
        for label, kc, ks, rc, rs in arms:
            st = handshake_quantiles(kc, ks, rc, rs, p, L, a.rtt, a.trials)
            row[label] = st
            print("%-13s %-8s %8.1f %8.1f %8.1f %8.1f %8.1f%%" %
                  (cname, label, st["p50"], st["mean"], st["p95"], st["p99"],
                   100 * st["untouched_frac"]))
        out["conditions"][cname] = row
        x, m = row["x25519"], row["mlkem"]
        row["direction"] = {
            "p50_mlkem_worse": m["p50"] > x["p50"],
            "mean_mlkem_worse": m["mean"] > x["mean"],
            "p95_mlkem_worse": m["p95"] > x["p95"],
        }
        print("%-13s %-8s p50 %+.1f%%  mean %+.1f%%  p95 %+.1f%%" %
              ("", "-> ML-KEM",
               100 * (m["p50"] - x["p50"]) / x["p50"],
               100 * (m["mean"] - x["mean"]) / x["mean"],
               100 * (m["p95"] - x["p95"]) / x["p95"]))
        print("")

    # ------------------------------------------------ compare against E12
    e12p = os.path.join(RESULTS, "e12_quic_testbed.json")
    if os.path.exists(e12p):
        with open(e12p, encoding="utf-8") as f:
            e12 = json.load(f)
        print("-" * 92)
        print("실제 quic-go 측정(E12)과 방향 대조")
        print("%-13s %-6s %9s %-11s %9s %-11s %6s" %
              ("condition", "stat", "모델비", "모델 판정", "실측비",
               "실측 판정", "대조"))
        print("-" * 92)
        agree = disagree = 0
        checks = []
        for cname, _, _ in conds:
            ax = e12["arms"].get("%s/x25519/nofec" % cname)
            am = e12["arms"].get("%s/X25519MLKEM768/nofec" % cname)
            if not ax or not am or cname not in out["conditions"]:
                continue
            mx = out["conditions"][cname]["x25519"]
            mm = out["conditions"][cname]["mlkem"]
            for stat in ("p50", "mean", "p95"):
                qx = (ax.get("quantiles") or {}).get(stat)
                qm = (am.get("quantiles") or {}).get(stat)
                if not qx or not qm:
                    continue
                model_ratio = mm[stat] / mx[stat]
                meas_ratio = qm / qx
                # 🩸 부호만 보는 이분법(>1.0)은 **동률을 불일치로 셌다**.
                # 모델 p50이 정확히 1.000(둘 다 무손실 중앙값=RTT)인데 실측이
                # 1.007이면 "방향이 다르다"고 잡히지만, 실제로는 둘 다 "차이
                # 없음"을 말하고 있다. 5% 띠를 두어 3분류로 비교한다.
                def cls(x, band=0.05):
                    if x > 1.0 + band:
                        return "ML-KEM 나쁨"
                    if x < 1.0 - band:
                        return "ML-KEM 좋음"
                    return "차이 없음"
                mc, ec = cls(model_ratio), cls(meas_ratio)
                same = (mc == ec)
                agree += 1 if same else 0
                disagree += 0 if same else 1
                checks.append({"condition": cname, "stat": stat,
                               "model_ratio": model_ratio,
                               "measured_ratio": meas_ratio,
                               "model_class": mc, "measured_class": ec,
                               "agree": same})
                print("%-13s %-6s %9.3f %-11s %9.3f %-11s %6s" %
                      (cname, stat, model_ratio, mc, meas_ratio, ec,
                       "일치" if same else "**불일치**"))
        out["e12_comparison"] = {"checks": checks, "agree": agree,
                                 "disagree": disagree}
        print("-" * 92)
        print("방향 일치 %d / %d" % (agree, agree + disagree))

    path = os.path.join(RESULTS, "e15_reconcile.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("")
    print("saved: %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
