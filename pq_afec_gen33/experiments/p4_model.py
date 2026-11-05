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
import math
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from padfec import amplif, policy, quantum   # noqa: E402

RESULTS = os.path.join(HERE, "results")


# p3_effect.N_PRECISE 와 같이 유지한다 (모듈 임포트는 부작용이 있어 피한다).
P3_N_PRECISE = 1200


def sample_size_advisory(first, second, gap_ms, alpha, env_floor_ms=0.0):
    """Observed-gap normal approximation, not a power or bootstrap guarantee.

    Future arms are assumed to have equal N and the observed variances. The
    success-only samples do not model failures, batch drift or winner selection.
    Keep the pure sampling estimate visible even when the fixed environment
    floor prevents separation under the existing acceptance rule.
    """
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
    # Two samples per arm is the minimum for the estimated-variance calculation.
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

    # ---------------------------------------------- 1. s0 를 기준선에서만 뽑는다
    #
    # 🩸 2026-08-20 p13 수정. 예전에는 s0 를 상수로 쓰고(amplif.threshold_cert)
    # FEC 팔은 연결 전체 패리티 합산 바이트로 예측했다. 그 결과가 임계 4/8
    # (FEC 팔 전부 +4,000~8,000 B 빗나감)이었다. p13 직접 측정이 확정한 것:
    #   - B_eff = 첫 비행 원본 + 첫 비행 패리티 (p2 가 이제 그렇게 센다)
    #   - s0 는 상수가 아니라 s0(n) = s0_base + n·c, c = 40.0 (직접 계수)
    # 여기서는 여전히 기준선 팔에서만 앵커를 맞추고, FEC 팔은 전부 예측이다.
    # 🩸 2026-08-25 - 주석이 `40.0` 이라고 적혀 있었는데 실제 값은
    #    **41.983** 이다(코드가 옳고 주석이 두 세대 낡았다). 이 파일은
    #    상수를 정본에서 읽고 있으니 결과는 맞았다 - 주석만 고친다.
    C_PKT = policy.C_PKT_POLICY_DEFAULT     # 41.983, p13 직접 계수
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
        # 명세 §2.5 패킷항 임계식. client_bytes_total 은 p13 수정 후
        # 첫 비행 몫만 담는다(= 측정으로 확인된 B_eff).
        pred = quantum.threshold(int(round(r["client_bytes_total"])),
                                 s0_base[g], C_PKT)
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
        # 🩸 p13 수정: v1 식(expected_hct_ms, PTO 999 ms 상수)이 아니라
        # 검증된 v2 비용식으로 예측한다 - 결합 도착분포 + 실측 T_recover
        # (PTO 가지 200.86 ms 상수 / ACK 가지 1.125·RTT+1.42).
        cand = {"k": k, "m": m, "W_eff": W}
        cb = policy.client_bytes_of(cand)
        cand["server_flight"] = p3["cert"] + quantum.s0_at(
            quantum.bin_index(cb), s0_base[g], C_PKT)
        # 🩸 2026-08-21 - **2 차 실행이 잡은 실제 고장.** 같은 날
        #    1-RTT 판정을 '상태마다 S 와 allowed 비교' 에서 '상태 무관
        #    상수 n* 와 도착 칸 비교' 로 바꿨는데, cost_of_v2 가 그
        #    n* 를 후보 dict 에서 읽는다. quantum._candidate 는 채우지만
        #    여기처럼 **손으로 만든 후보**는 안 채워서 p4 가
        #    `KeyError: 'n_need'` 로 0.2 초 만에 죽었다.
        #    정책이 쓰는 것과 **같은 함수**로 채운다 - 다른 식으로
        #    채우면 p4 가 대조하는 대상이 정책이 아니게 된다.
        #    n* 는 cert 와 서버 상수만으로 정해지므로 팔과 무관하다.
        cand["n_need"] = quantum.bin_needed(p3["cert"], None,
                                            s0_base[g], C_PKT)
        # 🩸 2026-08-27 - `uplink_mbps` 를 안 넘기고 있었다. 그러면
        #    cost_of_v2 가 기본값 UPLINK_MOBILE_MBPS(=10 Mbps)를 쓰는데,
        #    이 단계가 대조하는 p3 측정은 **대역을 안 건 환경**에서
        #    잰 것이다(p3_effect.py 의 set_netem 은 delay·loss 만 건다).
        #    즉 존재하지도 않는 직렬화 비용을 예측에 얹고 실측과 견줬다.
        #    p16 이 그 사실을 이미 쟀다 - 무제한에서 추가 바이트의 비용은
        #    0.2 ms 미만인데 10 Mbps 모형은 같은 자리에 1.06 ms 를 청구한다.
        #    측정 환경과 같은 값(UPLINK_UNSHAPED = 0)을 **명시적으로** 준다.
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

    # --------------------------------------------- 4. 정책이 고른 팔이 최선이었나
    print()
    print("=" * 96)
    print("4) 정책이 고른 팔이 실제로 가장 빨랐는가")
    print("=" * 96)
    print("%-16s %-6s %-6s %-10s %-10s %s"
          % ("그룹", "손실", "버스트", "정책 선택", "실측 최선", "일치"))
    # 🩸 2026-08-23 - **다중비교 보정의 분모.** 조건마다 95% 로 검정하면
    #    K 개를 볼 때 오경보 기대값이 0.05K 다. 정밀 측정(K=10)에서
    #    실제로 1 건이 나왔고(ML-KEM 2%·b3, 7.04 ms), 7 개 실행 대조에서
    #    그 차이는 부호까지 뒤집혔다(-5.03 ~ +13.08). Bonferroni 로
    #    α = 0.05/K 를 쓴다. 검정력이 깎이는 만큼은 판정 불능으로
    #    드러난다. 표본 수 안내는 같은 alpha의 관측 차이 정규근사이며
    #    검정력 설계나 판정 성공의 보장이 아니다.
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
        # 🩸 2026-08-21 - **환경 잡음 바닥을 음성 대조에서 잰다.**
        #    무손실 조건은 FEC 가 이득을 줄 수 없는 자리다(복구할 손실이
        #    없다). 그런데 5 개 실행에서 팔 간 차이가 -0.35 ~ +0.30 ms 로
        #    흔들렸다(평균은 ~0). 계통적 표류가 아니라 배치 효과다 -
        #    팔들이 한 실행 안에서 순차 측정되므로 머신 상태가 팔에 걸린다.
        #    부트스트랩은 **한 실행 안의 표본 분산만** 보므로 이 요동을
        #    못 본다(무손실은 꼬리가 없어 SE ~0.02 ms → 0.35 ms 가 '유의').
        #    그래서 같은 실행의 무손실 스프레드를 잡음 바닥으로 삼는다.
        #    매직 상수가 아니라 **이 실행에서 실제로 잰 값**이다.
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
            # 무손실은 판정에서 뺀다 - env 의 출처라 순환이고, 애초에
            # '어느 팔이 최선인가'가 무의미한 자리다(이득이 0 이어야 한다).
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
            # 🩸 p13 수정: v1 decide 가 아니라 v2 결정 규칙으로 판정한다.
            # p3 의 팔이 {off, on1, on2} 뿐이므로 δ 후보는 끈다(max_steps=0) -
            # 실측에 없는 선택지를 정책에 주면 비교가 성립하지 않는다.
            # 2026-08-21 - **업링크를 명시한다.** 그전에는 인자를 안 줘서
            # 모형이 기본값 10 Mbps 로 돌았는데, 비교 대상인 p3 측정은
            # netem 에 rate 를 안 건 **대역 무제한** 테스트베드다.
            # 없는 비용을 청구하니 정책이 패리티를 과소 구매했다 -
            # 이 한 줄로 정책 일치가 5/12 -> 7/12 가 된다.
            # (p11·p15 에서 같은 결함을 이미 고쳤는데 p4 를 놓쳤다.)
            # 🩸 2026-08-29 - **m_max 를 실측 팔에서 유도한다.** 그전에는
            #    `m_max=policy.M_MAX_DEFAULT` 를 그대로 넘겼는데, 바로 위
            #    주석이 δ 에 대해 말한 것과 **같은 이유로 틀렸다**:
            #    "실측에 없는 선택지를 정책에 주면 비교가 성립하지 않는다."
            #    p3 의 팔은 {off, on1, on2} 뿐인데 M_MAX_DEFAULT 가 2 → 3 이
            #    된 2026-08-25 부터 정책이 **on3 를 고를 수 있게** 됐고,
            #    그러면 아래 판정은 원리적으로 일치할 수가 없다.
            #    실제로 2026-08-29 정밀도 실행에서 **10 조건 전부 on3 를
            #    골라 0/7** 이 나왔다 - 모형 결함으로 오해하기 딱 좋은 모양이다
            #    (내가 실제로 그렇게 의심했다). m_max=2 로 주면 12 조건 전부
            #    on1 을 고르고 실측 허용집합이 전부 ['on1','on2'] 이라 **7/7**.
            #
            #    상수 2 를 박지 않는 이유: p3 가 나중에 on3 팔을 더하면
            #    자동으로 따라가야 한다. 자는 **측정이 무엇을 담고 있는지**로
            #    정해져야지 정책 상수로 정해지면 안 된다.
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
            # 🩸 그래도 정책이 실측에 없는 팔을 고르면 **「일치/불일치」가
            #    아니라 「비교 불가」** 다. 조용히 불일치로 찍으면 사람이
            #    모형을 의심하게 된다 - 2026-08-29 에 실제로 그랬다.
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
            # 🩸 2026-08-21 재설계 - 옛 판정은 두 군데 틀렸다.
            #   (a) 상위-2 간격 < 1 ms 면 조건을 통째로 뺐다. p11 에서
            #       고친 것과 같은 결함이다 - 정책이 동률 집합 **안**을
            #       골랐다면 그것은 일치다. (tot 도 제외 전에 세서
            #       분모가 부풀어 있었다: 실제 판정 4 인데 1/12 로 보고.)
            #   (b) 고정 1 ms 문턱은 잡음 규모가 아니다. 4 개 실행에서
            #       버스트-3 조건의 '실측 최선'이 전부 뒤집혔다
            #       (x25519 2%: off->on2->on2->off). 평균 차 3~18 ms 가
            #       PTO 0~5 건에서 온다.
            #   옳은 판정: **부트스트랩 잡음 동률 집합** - 최선 팔과의
            #   평균 차이 95% 구간이 0 을 포함하는 팔들. 정책 선택이 그
            #   안이면 일치, 전 팔 동률이면 판정 불능(기록하고 제외).
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
                # 동률 조건 두 가지 (둘 중 하나면 동률):
                #  (i)  부트스트랩 - 한 실행 안의 표본 분산으로 0 과 구별 불가.
                #       🩸 2026-08-23 **Bonferroni 보정**: 2.5% 가 아니라
                #       α/2 를 쓴다. 보정 전에는 K=10 조건에서 오경보가
                #       기대대로 1 건 나왔다(위 _alpha 주석 참조).
                #  (ii) 환경 바닥 - 차이가 무손실 스프레드보다 작다
                #       (실행 간 배치 효과로 이만큼은 그냥 흔들린다)
                if (lo_cnt / 2000.0 > _alpha / 2.0
                        or abs(arms[a] - arms[best]) < env):
                    tie.add(a)
            if len(tie) == len(arms):
                # Use the same per-condition alpha as the comparison above.
                # This observed-gap approximation does not promise a future pass.
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

    # ------------------------------------------------------------ 판정
    # 2026-08-21 - 이 단계는 그전까지 **무조건 `return 0`** 이었다.
    # threshold_hits, hct_mae_ms, policy_agreement 를 계산해 놓고
    # 아무것도 게이트하지 않아서, 임계 7/8 · 정책 5/12 인 채로 loop2 에
    # '완료' 로 남았다. 모형과 실측을 대조하는 단계가 실패할 수 없으면
    # 그 아래 모든 주장이 근거를 잃는다.
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
    # ⚠️ 판정 기준을 '실측 밴드 안' 으로 잡지 **않는다.** 그 밴드는 이분
    #    탐색의 **해상도**(반폭 28 B)이지 신뢰구간이 아니다. 참 임계는
    #    밴드 어딘가에 있으므로 '밴드 밖 3.9 B' 는 오차가 3.9~60 B 라는
    #    뜻일 뿐이다. 연구가 주장하는 것은 **모형이 어느 칸인지 맞힌다**
    #    이므로, 오차를 칸 크기(1,280 B) 대비로 재는 것이 맞다.
    #    5% = 64 B 를 넘으면 경계 근처 인증서의 5% 이상을 오분류한다.
    #    밴드 안 개수는 **정보로 함께 찍는다** - 감추지 않는다.
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
