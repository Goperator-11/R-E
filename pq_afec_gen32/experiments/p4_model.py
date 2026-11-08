from __future__ import annotations

import json
import math
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from padfec import amplif, policy, quantum

RESULTS = os.path.join(HERE, "results")


P3_N_PRECISE = 1200


def sample_size_advisory(first, second, gap_ms, alpha, env_floor_ms=0.0):
    if not math.isfinite(alpha) or not 0 < alpha < 1:
        raise ValueError("alpha must be finite and between zero and one")
    if not math.isfinite(env_floor_ms) or env_floor_ms < 0:
        raise ValueError("environment floor must be finite and nonnegative")
    z = statistics.NormalDist().inv_cdf(1.0 - alpha / 2.0)
    out = {"method": "observed_gap_normal_approximation_equal_n",
           "alpha": alpha, "normal_critical_value": z,
           "gap_ms": gap_ms, "env_floor_ms": env_floor_ms,
           "current_success_n": [len(first), len(second)],
           "statistical_only_n_per_arm": None, "n_per_arm": None,
           "status": "insufficient_samples",
           "assumptions": "같은 관측 분산, 독립 표본, 두 팔에 같은 성공 표본 수",
           "limitations": "관측된 최선·차선 차이의 정규근사 안내값이다. "
                          "검정력 설계나 부트스트랩 통과 보장이 아니며, "
                          "실패 연결·배치 효과·최선 팔 선택 편향을 반영하지 않는다."}
    if not math.isfinite(gap_ms):
        out["gap_ms"] = None
        out["status"] = "invalid_gap"
        return out
    if gap_ms <= 0:
        out["status"] = "zero_or_negative_gap"
        return out
    if min(len(first), len(second)) < 2:
        return out
    if not all(isinstance(x, (int, float)) and not isinstance(x, bool)
               and math.isfinite(x) for samples in (first, second) for x in samples):
        out["status"] = "invalid_samples"
        return out
    try:
        variance_sum = statistics.variance(first) + statistics.variance(second)
        estimate = z * z * variance_sum / (gap_ms * gap_ms)
    except (OverflowError, ZeroDivisionError):
        out["status"] = "unbounded_estimate"
        return out
    if not math.isfinite(estimate):
        out["status"] = "unbounded_estimate"
        return out
    out["statistical_only_n_per_arm"] = max(2, math.ceil(estimate))
    if gap_ms < env_floor_ms:
        out["status"] = "below_environment_floor"
        return out
    if variance_sum == 0:
        out["status"] = "zero_observed_variance"
        return out
    out["status"] = "approximation_only"
    out["n_per_arm"] = out["statistical_only_n_per_arm"]
    return out


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

    C_PKT = policy.C_PKT_POLICY_DEFAULT
    s0 = {}
    s0_base = {}
    for r in p2["thresholds"]:
        if r["arm"] != "off" or not r.get("threshold_lo"):
            continue
        f = amplif.fit_s0(r["threshold_lo"], r["threshold_hi"],
                          r["client_bytes_total"])
        s0[r["group"]] = f["s0_mid"]
        n_off = f["allowed"] // amplif.SERVER_PACKET_SIZE
        s0_base[r["group"]] = f["s0_mid"] - n_off * C_PKT
    print("=" * 96)
    print("1) 기준선 팔에서 뽑은 s0 앵커 (c = %.3f 는 p13 직접 계수)" % C_PKT)
    print("=" * 96)
    for g, v in s0.items():
        print("   %-16s s0(기준선 칸) = %.0f B  ->  s0_base = %.1f B"
              % (g, v, s0_base[g]))
    out["s0"] = s0
    out["s0_base"] = s0_base
    out["c_pkt"] = C_PKT

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
        pred = quantum.threshold(int(round(r["client_bytes_total"])),
                                 s0_base[g], C_PKT)
        lo, hi = r["threshold_lo"], r["threshold_hi"]
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
        cand = {"k": k, "m": m, "W_eff": W}
        cb = policy.client_bytes_of(cand)
        cand["server_flight"] = p3["cert"] + quantum.s0_at(
            quantum.bin_index(cb), s0_base[g], C_PKT)
        cand["n_need"] = quantum.bin_needed(p3["cert"], None,
                                            s0_base[g], C_PKT)
        e = policy.cost_of_v2(cand, W, p3["rtt_ms"], r["loss"] / 100.0,
                              r["burst"],
                              uplink_mbps=policy.UPLINK_UNSHAPED)
        pred_ms = e["j_ms"]
        meas = r["mean"]
        if meas is None:
            continue
        d = pred_ms - meas
        errs.append(abs(d))
        out["hct_prediction"].append(
            {"group": g, "loss": r["loss"], "burst": r["burst"],
             "arm": r["arm"], "predicted_ms": pred_ms,
             "measured_ms": meas, "diff_ms": d})
        print("%-16s %-6s %-6.0f %-5s %-5s %-10.1f %-10.1f %+.1f"
              % (g, "%.1f%%" % r["loss"], r["burst"], r["dir"], r["arm"],
                 pred_ms, meas, d))
    if errs:
        out["hct_mae_ms"] = sum(errs) / len(errs)
        print("   -> 평균 절대 오차 %.1f ms (%d 조건)"
              % (out["hct_mae_ms"], len(errs)))

    print()
    print("=" * 96)
    print("4) 정책이 고른 팔이 실제로 가장 빨랐는가")
    print("=" * 96)
    print("%-16s %-6s %-6s %-10s %-10s %s"
          % ("그룹", "손실", "버스트", "정책 선택", "실측 최선", "일치"))
    _n_judge = sum(1 for _g in ("x25519", "X25519MLKEM768")
                   for _l, _b in ((1.0, 1.0), (2.0, 1.0), (5.0, 1.0),
                                  (2.0, 3.0), (5.0, 3.0)))
    _alpha = 0.05 / max(1, _n_judge)
    out["multiple_comparison"] = {"k": _n_judge, "alpha": _alpha,
                                  "method": "Bonferroni"}
    print("   다중비교 보정: 판정 %d 조건 -> α=%.4f (양측 %.2f%% 구간)"
          % (_n_judge, _alpha, 100 * (1 - _alpha)))

    agree = tot = 0
    skipped = []
    for g in Cmap:
        if g not in s0:
            continue
        k = 2 if g == "X25519MLKEM768" else 1
        _z = {}
        for _r0 in p3["runs"]:
            if (_r0["group"] == g and _r0["loss"] == 0.0
                    and _r0["dir"] == "c2s" and _r0.get("valid")
                    and _r0["mean"] is not None):
                _z[_r0["arm"]] = _r0["mean"]
        env = ((max(_z.values()) - min(_z.values()))
               if len(_z) >= 2 else 0.0)
        out.setdefault("env_floor_ms", {})[g] = env
        print("   [%s] 환경 잡음 바닥(무손실 팔 간 스프레드) %.3f ms"
              % (g, env))
        for loss, burst in ((0.0, 1.0), (1.0, 1.0), (2.0, 1.0), (5.0, 1.0),
                            (2.0, 3.0), (5.0, 3.0)):
            if loss == 0.0:
                continue
            arms = {}
            samp = {}
            for r in p3["runs"]:
                if (r["group"] == g and r["loss"] == loss
                        and r["burst"] == burst and r["dir"] == "c2s"
                        and r.get("valid") and r["mean"] is not None):
                    arms[r["arm"]] = r["mean"]
                    samp[r["arm"]] = r.get("samples") or []
            if len(arms) < 2:
                continue
            best = min(arms, key=lambda a: arms[a])
            _m_avail = [int(a[2:]) for a in arms
                        if a.startswith("on") and a[2:].isdigit()]
            _m_max = max(_m_avail) if _m_avail else 0
            d = policy.decide_v2(C=Cmap[g], cert_bytes=p3["cert"],
                                 rtt_ms=p3["rtt_ms"], p=loss / 100.0,
                                 burst=burst, s0_base=s0_base[g],
                                 c_pkt=C_PKT, W=1280, max_steps=0,
                                 m_max=_m_max,
                                 uplink_mbps=policy.UPLINK_UNSHAPED)
            want = ("off" if d["choice"]["mode"] == "none"
                    else "on%d" % d["choice"]["m"])
            if want not in arms:
                skipped.append({"group": g, "loss": loss, "burst": burst,
                                "why": "정책이 고른 %s 가 실측 팔에 없다"
                                       % want,
                                "want": want, "arms": sorted(arms),
                                "m_max_given": _m_max, "n_needed": None})
                print("%-16s %-6s %-6.0f %-10s %-10s 비교 불가   "
                      "실측 팔 %s (m_max=%d 로 줬는데도)"
                      % (g, "%.1f%%" % loss, burst, want, "-",
                         sorted(arms), _m_max))
                continue
            import random as _rnd
            _r = _rnd.Random(23)
            _bs = samp.get(best) or []
            tie = set([best])
            for a, sv in samp.items():
                if a == best or not sv or not _bs:
                    continue
                lo_cnt = 0
                for _ in range(2000):
                    ma = sum(sv[_r.randrange(len(sv))]
                             for _i in range(len(sv))) / len(sv)
                    mb = sum(_bs[_r.randrange(len(_bs))]
                             for _i in range(len(_bs))) / len(_bs)
                    if ma - mb <= 0:
                        lo_cnt += 1
                if (lo_cnt / 2000.0 > _alpha / 2.0
                        or abs(arms[a] - arms[best]) < env):
                    tie.add(a)
            if len(tie) == len(arms):
                _ord = sorted(arms, key=lambda a: arms[a])
                advisory = sample_size_advisory(
                    samp.get(_ord[0]) or [], samp.get(_ord[1]) or [],
                    arms[_ord[1]] - arms[_ord[0]], _alpha, env)
                advisory["arms"] = _ord[:2]
                _need = advisory["n_per_arm"]
                skipped.append({"group": g, "loss": loss,
                                "burst": burst,
                                "why": "전 팔이 잡음 동률",
                                "n_needed": _need,
                                "sample_size_advisory": advisory,
                                "means": arms})
                print("%-16s %-6s %-6.0f %-10s %-10s 판정불능 "
                      "(팔당 성공 표본 정규근사 N %s, %s) [%s]"
                      % (g, "%.1f%%" % loss, burst, want, best,
                         _need if _need is not None else "계산 불가",
                         advisory["status"],
                         "  ".join("%s %.1f" % (a, v) for a, v in
                                   sorted(arms.items()))))
                continue
            tot += 1
            ok = want in tie
            agree += 1 if ok else 0
            out["policy_check"].append(
                {"group": g, "loss": loss, "burst": burst,
                 "policy": want, "measured_best": best,
                 "tie_set": sorted(tie),
                 "means": arms, "agree": ok})
            print("%-16s %-6s %-6.0f %-10s %-10s %s   허용 %s (바닥 %.2f) [%s]"
                  % (g, "%.1f%%" % loss, burst, want, best,
                     "예" if ok else "아니오", sorted(tie), env,
                     "  ".join("%s %.1f" % (a, v) for a, v in
                               sorted(arms.items()))))
    if tot:
        out["policy_agreement"] = [agree, tot]
        print("   -> %d / %d 일치 (전 팔 잡음 동률이라 판정 불능: %d 조건)"
              % (agree, tot, len(skipped)))
    out["policy_skipped"] = skipped

    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok),
                       "detail": detail})
        print("[%s] %-52s %s" % ("통과" if ok else "실패", name,
                                  detail[:64]))

    tp = out["threshold_prediction"]
    devs = [(abs(t["predicted"]
                 - 0.5 * (t["measured_lo"] + t["measured_hi"])),
             t["group"], t["arm"]) for t in tp]
    worst = max(devs) if devs else (0.0, "-", "-")
    inband = sum(1 for t in tp if t["hit"])
    print()
    add("임계 예측 오차가 칸의 5%% (64 B) 미만",
        worst[0] < 0.05 * 1280,
        "최대 %.1f B (%s %s) = 칸의 %.1f%% | 밴드 안 %d/%d, 밴드 반폭 28 B"
        % (worst[0], worst[1], worst[2], 100 * worst[0] / 1280.0,
           inband, len(tp)))
    add("HCT 해석해의 평균절대오차 < 5 ms",
        out.get("hct_mae_ms") is not None
        and out["hct_mae_ms"] < 5.0,
        "MAE %.2f ms" % (out.get("hct_mae_ms") or -1))
    pa = out.get("policy_agreement")
    add("정책 예측이 실측 최선과 일치 (팔이 갈린 조건만)",
        bool(pa) and pa[0] == pa[1],
        "%s | 잡음이라 제외 %d 조건"
        % (pa, len(out.get("policy_skipped") or [])))
    _needs = sorted(x["n_needed"] for x in (out.get("policy_skipped") or [])
                    if x.get("n_needed"))
    add("[부정] 판정할 조건이 실제로 남았다 (전부 제외되면 공허하다)",
        bool(pa) and pa[1] >= 4,
        "판정 대상 %d 조건 | 판정불능 조건의 팔당 성공 표본 정규근사 N %s"
        % (pa[1] if pa else 0,
           ("%s (중앙 %d) | p3 --precise(N=%d) 이하 안내값 %d 조건. "
            "검정력·추가 판정 보장 아님"
            % (_needs[:5], _needs[len(_needs) // 2], P3_N_PRECISE,
               sum(1 for n in _needs if n <= P3_N_PRECISE)))
           if _needs else "계산 불가"))
    out["checks"] = checks
    npass = sum(1 for c in checks if c["ok"])
    out["passed"], out["total"] = npass, len(checks)
    print("-" * 76)
    print("%d / %d 통과" % (npass, len(checks)))

    path = os.path.join(RESULTS, "p4_model.json")
    from _journal import save_result
    save_result(path, out)
    print()
    print("saved:", path)
    return 0 if npass == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
