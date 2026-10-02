# -*- coding: utf-8 -*-
"""손실 실험 분석 — 두 비용식의 **구조**를 공정하게 비교한다.

공정하게 하려면 두 가지를 먼저 정리해야 한다.

1. **t_tx 를 빼야 한다.** 모형의 기본값은 업링크 10 Mbps 인데 이 테스트베드는
   netem 이 지연·손실만 걸 뿐 대역 제한이 없다. 실측이 그것을 그대로 보여준다 —
   무손실에서 m=1 은 52.465, m=2 는 52.466 ms 로 **차이가 0.001 ms** 인데
   모형은 +1.06 ms 를 매긴다. 테스트베드 대조에서는 uplink 를 무한으로 둔다.

2. **자유 상수를 각 구조에 똑같이 하나씩 준다.** 옛 식이 "우연히 맞은" 것인지
   보려면 T_recover 를 고정하면 안 된다. 두 구조 모두 (기저 오프셋 c0,
   복구비용 T_rec) 두 개를 최소제곱으로 맞춘 뒤 **잔차**를 비교한다.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from padfec import policy, quantum   # noqa: E402

RTT = 50.0
IPS = 1280
K = 1
S0B, CP = 396.5, 34.5

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "probe_losstest.json")) as f:
    D = json.load(f)


def s0p(cb):
    return S0B + (quantum.allowed(cb) // 1280) * CP


def binom(n, k, q):
    if k < 0 or k > n:
        return 0.0
    c = 1.0
    for i in range(k):
        c = c * float(n - i) / float(i + 1)
    return c * (q ** k) * ((1.0 - q) ** (n - k))


def shape_old(k, m, w, p, burst, sf):
    """옛 구조: (모든 상태의 E[n]) 과 (p_fail) 계수를 따로 돌려준다."""
    parity = policy.parity_datagram_bytes(w, k)
    q = 1.0 - p
    n = 0.0
    for i in range(k + 1):
        pi = binom(k, i, q)
        for j in range(m + 1):
            pj = binom(m, j, q)
            n += pi * pj * (2.0 if sf > quantum.allowed(i * w + j * parity)
                            else 1.0)
    pf = policy.p_fail_of({"k": k, "m": m}, p, burst)
    return n * RTT, pf          # J = n*RTT + pf*T_rec + c0


def shape_new(k, m, w, p, burst, sf):
    """새 구조: (복구 성공 상태만의 E[n]) 과 (p_fail) 계수."""
    o = policy.flight_outcome(k, m, w, p, burst, sf)
    # J = n*RTT + pf*(RTT + T_rec) + c0  ->  기저 = n*RTT + pf*RTT
    return (o["n_rtt_expected"] + o["p_fail"]) * RTT, o["p_fail"]


def fit(rows, shape):
    """y = base + pf*T + c0 를 (T, c0) 에 대해 최소제곱."""
    A = []
    y = []
    for r in rows:
        sf = r["cert"] + s0p(K * IPS)
        base, pf = shape(K, r["m"], IPS, r["p"], r["burst"], sf)
        A.append((pf, 1.0))
        y.append(r["mean"] - base)
    n = len(A)
    sxx = sum(a[0] * a[0] for a in A)
    sx = sum(a[0] for a in A)
    sy = sum(y)
    sxy = sum(A[i][0] * y[i] for i in range(n))
    det = sxx * n - sx * sx
    if abs(det) < 1e-12:
        return None
    T = (sxy * n - sx * sy) / det
    c0 = (sxx * sy - sx * sxy) / det
    res = []
    for i, r in enumerate(rows):
        sf = r["cert"] + s0p(K * IPS)
        base, pf = shape(K, r["m"], IPS, r["p"], r["burst"], sf)
        res.append(r["mean"] - (base + pf * T + c0))
    mae = sum(abs(x) for x in res) / n
    rmse = (sum(x * x for x in res) / n) ** 0.5
    return {"T_rec": T, "c0": c0, "mae": mae, "rmse": rmse, "res": res}


rows = [r for r in D["rows"] if r.get("mean") is not None]
print("조건 %d 개 (cert 2 x 손실 4 x 팔 3)" % len(rows))
print()
print("=== 1. t_tx 항이 이 테스트베드에 맞는가 ===")
z = {(r["cert"], r["loss"], r["arm"]): r["mean"] for r in rows}
print("  무손실 cert=2308: m=1 %.3f ms, m=2 %.3f ms -> 차 %.3f ms"
      % (z[(2308, "0", "m=1")], z[(2308, "0", "m=2")],
         z[(2308, "0", "m=2")] - z[(2308, "0", "m=1")]))
print("  모형(10 Mbps)이 매기는 차: %.3f ms"
      % (policy.tx_cost_ms(policy.parity_datagram_bytes(IPS, K), 10.0)))
print("  -> 대역 제한이 없는 테스트베드에서는 t_tx 를 빼야 공정하다.")

print()
print("=== 2. 자유 상수 2개를 똑같이 주고 구조만 비교 ===")
fo = fit(rows, shape_old)
fn = fit(rows, shape_new)
for name, f in (("옛 구조", fo), ("새 구조", fn)):
    print("  %s : T_rec=%7.2f ms (%.2f RTT)  c0=%6.2f ms  MAE=%6.3f  RMSE=%6.3f"
          % (name, f["T_rec"], f["T_rec"] / RTT, f["c0"], f["mae"], f["rmse"]))
better = "새 구조" if fn["rmse"] < fo["rmse"] else "옛 구조"
print("  -> 잔차가 작은 쪽: **%s** (RMSE %.3f vs %.3f)"
      % (better, min(fn["rmse"], fo["rmse"]), max(fn["rmse"], fo["rmse"])))

print()
print("=== 3. 기본값 T_recover=RTT 는 맞는가 ===")
print("  적합된 T_rec = %.1f ms = %.2f RTT (새 구조)" % (fn["T_rec"],
                                                        fn["T_rec"] / RTT))
print("  현재 코드 기본값 = RTT = %.1f ms" % RTT)
print("  -> 기본값이 %.1f 배 작다." % (fn["T_rec"] / RTT))

print()
print("=== 4. 잔차가 가장 큰 조건 (모형이 못 맞히는 곳) ===")
pairs = sorted(zip(rows, fn["res"]), key=lambda t: -abs(t[1]))[:6]
for r, e in pairs:
    print("  cert=%-5d %-15s %-4s 실측 %7.2f  잔차 %+7.2f  (2rtt=%.3f)"
          % (r["cert"], r["loss"], r["arm"], r["mean"], e,
             r["two_rtt_rate"] or 0.0))

print()
print("=== 5. 평균이 아니라 p50 으로 보면 ===")
for cert in (2308, 4032):
    line = []
    for loss in ("0", "2%", "5%", "gemodel 5% 50%"):
        v = [r for r in rows if r["cert"] == cert and r["loss"] == loss]
        line.append("%s: " % loss + "/".join("%.1f" % r["p50"] for r in v))
    print("  cert=%d  %s" % (cert, "   ".join(line)))
print("  (팔 순서 off/m=1/m=2. p50 은 손실이 없던 판이 대부분이라 거의 안 움직인다 —")
print("   손실 비용은 전부 꼬리에 있다. 평균으로 봐야 하는 이유다.)")
