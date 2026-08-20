# -*- coding: utf-8 -*-
"""P4 - 모형이 실측을 맞췄는가.

모형을 실측에 맞춰 고치는 것은 쉽다. 그래서 여기서는 순서를 지킨다.

  1. s0(인증서를 뺀 서버 비행 크기)는 **기준선 팔(off) 하나에서만** 뽑는다.
     이것이 모형에 넣는 유일한 실측 상수다.
  2. 그 s0 로 다른 모든 팔의 임계를 **예측**하고, 예측이 실측 구간 안에
     들어가는지 본다. 여기에는 맞춰 넣은 자유도가 없다.
  3. 정책이 고른 팔이 실제로 가장 빨랐는지 본다. 정책이 틀렸으면
     그대로 기록한다.

Output: experiments/results/p4_model.json
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from padfec import amplif, policy   # noqa: E402

RESULTS = os.path.join(HERE, "results")


def load(name):
    p = os.path.join(RESULTS, name)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    p1 = load("p1_flight.json")
    p2 = load("p2_threshold.json")
    p3 = load("p3_effect.json")
    if not (p1 and p2 and p3):
        print("앞 단계 결과가 없다:",
              [n for n, v in (("p1", p1), ("p2", p2), ("p3", p3)) if not v])
        return 2

    out = {"threshold_prediction": [], "hct_prediction": [],
           "policy_check": []}

    # ---------------------------------------------- 1. s0 를 기준선에서만 뽑는다
    s0 = {}
    for r in p2["thresholds"]:
        if r["arm"] != "off" or not r.get("threshold_lo"):
            continue
        f = amplif.fit_s0(r["threshold_lo"], r["threshold_hi"],
                          r["client_bytes_total"])
        s0[r["group"]] = f["s0_mid"]
    print("=" * 96)
    print("1) 기준선 팔에서 뽑은 s0 (인증서를 뺀 서버 첫 비행 크기)")
    print("=" * 96)
    for g, v in s0.items():
        print("   %-16s s0 = %.0f B" % (g, v))
    out["s0"] = s0

    # ------------------------------------------- 2. 다른 팔의 임계를 예측한다
    print()
    print("=" * 96)
    print("2) 그 s0 로 나머지 팔의 임계를 예측 (맞춰 넣은 자유도 없음)")
    print("=" * 96)
    print("%-16s %-5s %-12s %-16s %-16s %s"
          % ("그룹", "팔", "클라 바이트", "예측 임계", "실측 임계", "판정"))
    nhit = ntot = 0
    for r in p2["thresholds"]:
        g = r["group"]
        if g not in s0 or not r.get("threshold_lo") or not r.get("threshold_hi"):
            continue
        pred = amplif.threshold_cert(r["client_bytes_total"], s0[g])
        lo, hi = r["threshold_lo"], r["threshold_hi"]
        # 임계는 100 B 해상도로 좁힌 구간이다. 예측이 그 구간에 들면 적중.
        hit = lo <= pred <= hi
        ntot += 1
        nhit += 1 if hit else 0
        out["threshold_prediction"].append(
            {"group": g, "arm": r["arm"],
             "client_bytes": r["client_bytes_total"],
             "predicted": pred, "measured_lo": lo, "measured_hi": hi,
             "hit": hit})
        print("%-16s %-5s %-12.0f %-16.0f %-16s %s"
              % (g, r["arm"], r["client_bytes_total"], pred,
                 "%d ~ %d" % (lo, hi), "적중" if hit else "빗나감"))
    print("   -> %d / %d 적중" % (nhit, ntot))
    out["threshold_hits"] = [nhit, ntot]

    # --------------------------------------------- 3. HCT 예측 대 실측
    print()
    print("=" * 96)
    print("3) 손실 조건의 HCT 예측 대 실측 (cert %d, RTT %.0f ms)"
          % (p3["cert"], p3["rtt_ms"]))
    print("=" * 96)
    print("%-16s %-6s %-6s %-5s %-5s %-10s %-10s %s"
          % ("그룹", "손실", "버스트", "방향", "팔", "예측 평균", "실측 평균",
             "차이"))
    Cmap = {}
    for c in p1["capacity_checks"]:
        if c["ips"] == 0:
            Cmap[c["group"]] = c["C"]
    errs = []
    for r in p3["runs"]:
        if not r.get("valid") or r["dir"] != "c2s":
            continue
        g = r["group"]
        if g not in Cmap or g not in s0:
            continue
        m = 0 if r["arm"] == "off" else r["m"]
        k = 2 if g == "X25519MLKEM768" else 1
        W = 1280
        e = policy.expected_hct_ms(p3["cert"], k, m, W, p3["rtt_ms"],
                                   r["loss"] / 100.0, r["burst"], s0[g])
        if m == 0:
            pf = (0.0 if r["loss"] <= 0 else
                  1.0 - policy.erasure_probs(k, r["loss"] / 100.0,
                                             r["burst"])[0])
            e["hct_ms"] = e["base_ms"] + pf * policy.PTO_NO_SAMPLE_MS
        meas = r["mean"]
        if meas is None:
            continue
        d = e["hct_ms"] - meas
        errs.append(abs(d))
        out["hct_prediction"].append(
            {"group": g, "loss": r["loss"], "burst": r["burst"],
             "arm": r["arm"], "predicted_ms": e["hct_ms"],
             "measured_ms": meas, "diff_ms": d})
        print("%-16s %-6s %-6.0f %-5s %-5s %-10.1f %-10.1f %+.1f"
              % (g, "%.1f%%" % r["loss"], r["burst"], r["dir"], r["arm"],
                 e["hct_ms"], meas, d))
    if errs:
        out["hct_mae_ms"] = sum(errs) / len(errs)
        print("   -> 평균 절대 오차 %.1f ms (%d 조건)"
              % (out["hct_mae_ms"], len(errs)))

    # --------------------------------------------- 4. 정책이 고른 팔이 최선이었나
    print()
    print("=" * 96)
    print("4) 정책이 고른 팔이 실제로 가장 빨랐는가")
    print("=" * 96)
    print("%-16s %-6s %-6s %-10s %-10s %s"
          % ("그룹", "손실", "버스트", "정책 선택", "실측 최선", "일치"))
    agree = tot = 0
    for g in Cmap:
        if g not in s0:
            continue
        k = 2 if g == "X25519MLKEM768" else 1
        for loss, burst in ((0.0, 1.0), (1.0, 1.0), (2.0, 1.0), (5.0, 1.0),
                            (2.0, 3.0), (5.0, 3.0)):
            arms = {}
            for r in p3["runs"]:
                if (r["group"] == g and r["loss"] == loss
                        and r["burst"] == burst and r["dir"] == "c2s"
                        and r.get("valid") and r["mean"] is not None):
                    arms[r["arm"]] = r["mean"]
            if len(arms) < 2:
                continue
            best = min(arms, key=lambda a: arms[a])
            d = policy.decide(Cmap[g], p3["cert"], p3["rtt_ms"],
                              loss / 100.0, burst, s0[g], W=1280, m_max=2)
            want = {"off": "off", "parity1": "on1", "parity2": "on2"}.get(
                d["choice"]["mode"], d["choice"]["mode"])
            tot += 1
            ok = want == best
            agree += 1 if ok else 0
            out["policy_check"].append(
                {"group": g, "loss": loss, "burst": burst,
                 "policy": want, "measured_best": best,
                 "means": arms, "agree": ok})
            print("%-16s %-6s %-6.0f %-10s %-10s %s   [%s]"
                  % (g, "%.1f%%" % loss, burst, want, best,
                     "예" if ok else "아니오",
                     "  ".join("%s %.1f" % (a, v) for a, v in
                               sorted(arms.items()))))
    if tot:
        out["policy_agreement"] = [agree, tot]
        print("   -> %d / %d 일치" % (agree, tot))

    path = os.path.join(RESULTS, "p4_model.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print()
    print("saved:", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
