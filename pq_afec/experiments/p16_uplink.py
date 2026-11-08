from __future__ import annotations

import math
import os
import statistics
import sys
import datetime
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B
from padfec import policy as POL

RTT_MS = 50.0
GROUP = "x25519"
K = 1
W = 1280
CERT = 2000
N = 200

RULER_MS = 0.25

ARMS = [
    ("base", "off", 0, 0),
    ("pad",  "off", 0, 1452),
    ("m1",   "on",  1, 0),
    ("m2",   "on",  2, 0),
]

CONDS = [
    ("무제한", 0.0, POL.UPLINK_UNSHAPED),
    ("10Mbps", 10.0, POL.UPLINK_MOBILE_MBPS),
]


def mean(v):
    return (sum(v) / len(v)) if v else None


def slope_ms_per_byte(mbps):
    if mbps <= 0:
        return 0.0
    return 8.0 / (mbps * 1e6) * 1000.0


def implied_mbps(slope):
    if slope <= 1e-9:
        return float("inf")
    return 8.0 / (slope * 1e-3) / 1e6


def linfit(xs, ys):
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


import blockstat as BST

BATCH_MIN = BST.BATCH_MIN


def _batch_means(v):
    return BST.batch_means(v)


def _se(v):
    return BST.batch_se(v)


def _sd(v):
    return BST.batch_sd(v)


LOAD_TRACE_REF_0901 = {"무제한": {"base": 0.245, "m1": 0.088},
                       "note": "09-01 깨끗한 판, 블록 안에서 잰 lag-1. "
                               "10Mbps 는 이어붙임 기준 +0.11~+0.18 만 기록됨"}


def load_trace(blocks):
    rows = []
    for aname, bs in blocks.items():
        for b in bs:
            v = b.get("ms") or []
            se_b = BST.batch_se(v)
            se_i = (statistics.stdev(v) / math.sqrt(len(v))
                    if len(v) >= 2 else None)
            rows.append({"arm": aname, "pos": b.get("pos"), "n": len(v),
                         "lag1": BST.lag1(v),
                         "se_ratio_batch_over_iid":
                             (se_b / se_i) if (se_b and se_i) else None})
    return rows


def _z(alpha=0.05):
    return statistics.NormalDist().inv_cdf(1.0 - alpha / 2.0)


def diff_half(a, b, alpha=0.05):
    return BST.batch_diff_half(a, b, alpha)


def contrast_ci(groups, coefficients, alpha=0.05):
    out = {"estimate_ms": None, "half_ms": None, "variance": None, "df": None,
           "alpha": alpha, "groups": [], "status": "unavailable",
           "method": "group_batch_variances_welch_t",
           "assumptions": "independent group means and approximately independent batch means",
           "limits": "cross-group and residual time dependence are not estimated; no multiplicity adjustment"}
    if (not groups or len(groups) != len(coefficients)
            or not 0 < alpha < 1):
        return out
    terms = []
    estimate = 0.0
    for values, coefficient in zip(groups, coefficients):
        if (not values or any(type(x) not in (int, float) or not math.isfinite(x)
                              for x in values)
                or type(coefficient) not in (int, float) or not math.isfinite(coefficient)):
            return out
        se, method, count = BST.batch_se_info(values)
        batch_size = max(1, int(math.sqrt(len(values)))) if method == "batch" else 1
        out["groups"].append({"coefficient": coefficient, "n": len(values),
                              "se_method": method, "mean_se": se,
                              "effective_mean_count": count, "batch_size": batch_size,
                              "unused_batch_tail": len(values) - batch_size * count})
        if se is None or count < 2:
            return out
        estimate += coefficient * mean(values)
        terms.append((coefficient * coefficient * se * se, count))
    variance = sum(v for v, _ in terms)
    denominator = sum(v * v / (count - 1) for v, count in terms)
    df = variance * variance / denominator if denominator else None
    half = BST.t_crit(df, alpha) * math.sqrt(variance) if variance else 0.0
    out.update(estimate_ms=estimate, half_ms=half, variance=variance, df=df,
               status="available", iid_fallback=any(g["se_method"] == "iid" for g in out["groups"]))
    return out


def need_n(a, b, target, alpha=0.05, power=0.80):
    sa, sb = _sd(a), _sd(b)
    if sa is None or sb is None or not target or abs(target) < 1e-3:
        return None
    s2 = (sa * sa + sb * sb) / 2.0
    za = _z(alpha)
    zb = statistics.NormalDist().inv_cdf(power)
    return int(math.ceil(2.0 * (za + zb) ** 2 * s2 / (target * target)))


def verdict3(diff, half, ruler):
    if half is None:
        return "판정불능"
    if abs(diff) + half <= ruler:
        return "맞음"
    if abs(diff) - half > ruler:
        return "틀림"
    return "판정불능"


def ips_evidence(rows, requested, fec, m, n_req, base_ips=W, k=K):
    observations = [dict(row) for row in rows]
    return {
        "source": "qamp client JSON rows, including unsuccessful trials",
        "observations_scope": "full_client_json_rows",
        "ips_eff_semantics": "client effective configuration after the stack size cap",
        "wire_crosscheck": "data/parity bytes and datagrams; actual k and path RTT are retained",
        "requested_ips": requested, "base_ips": base_ips, "expected_k": k,
        "expected_k_semantics": "client flush hint; actual first_flight_datagrams is retained",
        "fec": fec, "configured_m": m, "n_req": n_req,
        "n_rows": len(observations), "observations": observations,
        "ips_used_values": sorted({r["ips_used"] for r in observations
                                   if type(r.get("ips_used")) is int}),
        "ips_eff_values": sorted({r["ips_eff"] for r in observations
                                  if type(r.get("ips_eff")) is int}),
    }


def byte_evidence(rows):
    data = [row.get("first_flight_bytes") for row in rows]
    parity = [row.get("first_flight_parity_bytes") for row in rows]
    valid = lambda x: type(x) is int and x >= 0
    totals = [d + p if valid(d) and valid(p) else None for d, p in zip(data, parity)]
    missing = sum(value is None for value in totals)
    median = sorted(totals)[len(totals) // 2] if totals and not missing else None
    return {"data_bytes": data, "parity_bytes": parity, "total_bytes": totals,
            "n_rows": len(rows), "n_valid": len(rows) - missing, "n_missing": missing,
            "total_bytes_median": median, "median_method": "upper_order_statistic"}


def trial_denominators(rows, n_req, err=""):
    successes = [row for row in rows if row.get("ok") is True]
    finite = lambda x: type(x) in (int, float) and math.isfinite(x)
    latencies = [row["ms"] for row in successes if finite(row.get("ms"))]
    byte_counts = byte_evidence(rows)
    n_unknown = sum(type(row.get("ok")) is not bool for row in rows)
    out = {"requested": n_req, "returned": len(rows), "successful": len(successes),
           "failed": sum(row.get("ok") is False for row in rows),
           "missing_returned": max(0, n_req - len(rows)),
           "excess_returned": max(0, len(rows) - n_req),
           "unknown_success_flag": n_unknown,
           "successful_latency_rows": len(latencies),
           "missing_successful_latency": len(successes) - len(latencies),
           "byte_rows": byte_counts["n_valid"], "missing_byte_rows": byte_counts["n_missing"]}
    out["complete"] = (type(n_req) is int and n_req > 0 and len(rows) == n_req
                       and len(successes) == n_req and len(latencies) == n_req
                       and byte_counts["n_valid"] == n_req and not n_unknown and not err)
    return out


def merge_blocks(blocks, name, fec, m, ips, condition):
    if not blocks:
        raise ValueError("collection blocks are required")
    rows = [dict(row) for block in blocks for row in block["client_rows"]]
    err = " | ".join(block["err"] for block in blocks if block["err"])
    n_req = sum(block["denominators"]["requested"] for block in blocks)
    counts = trial_denominators(rows, n_req, err)
    counts["aggregate_missing_returned"] = counts["missing_returned"]
    counts["aggregate_excess_returned"] = counts["excess_returned"]
    counts["missing_returned"] = sum(block["denominators"]["missing_returned"] for block in blocks)
    counts["excess_returned"] = sum(block["denominators"]["excess_returned"] for block in blocks)
    counts["incomplete_units"] = sum(block["denominators"].get("complete") is not True for block in blocks)
    counts["complete"] = bool(counts["complete"] and counts["incomplete_units"] == 0)
    counts["return_coverage_scope"] = "unit sums; missing and excess in distinct units do not cancel"
    latencies = [row["ms"] for row in rows if row.get("ok") is True
                 and type(row.get("ms")) in (int, float) and math.isfinite(row["ms"])]
    bytes_ = byte_evidence(rows)
    units = []
    offset = 0
    for block in blocks:
        units.append({"collection": dict(block["collection"]), "position": block.get("pos"),
                      "row_start": offset, "row_stop": offset + len(block["client_rows"]),
                      "client_stats": block["client_stats"], "server_stats": block["server_stats"],
                      "denominators": block["denominators"],
                      "server_stats_present": bool(block["server_stats"]),
                      "server_connection_completeness_verified": False})
        offset += len(block["client_rows"])
    median = bytes_["total_bytes_median"]
    return {"arm": name, "cond": condition, "rate_mbit": blocks[0]["rate_mbit"],
            "n": len(rows), "n_req": n_req, "ok": counts["successful"], "ms": latencies,
            "mean": mean(latencies), "p50": B.pctl(latencies, .5), "p95": B.pctl(latencies, .95),
            "two_rtt_rate": (sum(t > 1.5 * RTT_MS for t in latencies) / len(latencies)
                             if latencies else None),
            "ff_bytes_med": median, "added_bytes": max(0, median - K * W) if median is not None else None,
            "added_bytes_reference": "configured expected_k * base W; actual k is retained in client rows",
            "positions": [block.get("pos") for block in blocks],
            "block_drift_ms": (blocks[1]["mean"] - blocks[0]["mean"]
                               if len(blocks) == 2 and all(block["mean"] is not None for block in blocks)
                               else None),
            "client_rows": rows, "ips_evidence": ips_evidence(rows, ips, fec, m, n_req),
            "byte_evidence": bytes_, "denominators": counts,
            "collection_units": units, "err": err}


def run_arm(name, fec, m, ips, rate_mbit, up_policy, run_id=None, block_pos=None):
    collection = {"run_id": run_id, "unit_id": uuid.uuid4().hex, "block_position": block_pos,
                  "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  "started_at_ns": time.time_ns()}
    B.set_netem(RTT_MS / 2.0, loss_c2s=0.0, rate_up_mbit=rate_mbit)
    p, sp = B.start_server(CERT, fec=("on" if fec == "on" else "off"))
    try:
        rows, cs, err = B.run_client(GROUP, N, fec=fec, m=max(m, 1), ips=ips,
                                 gap_ms=8, timeout_s=10, expect_k=K,
                                 uplink_mbps=up_policy)
    finally:
        B.stop_server(p)
    srv = B.read_server_stats(sp)
    collection.update(finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      finished_at_ns=time.time_ns(), server_stats_path=sp)
    counts = trial_denominators(rows, N, err)
    ok = [r["ms"] for r in rows if r.get("ok") is True
          and type(r.get("ms")) in (int, float) and math.isfinite(r["ms"])]
    bytes_ = byte_evidence(rows)
    ff_med = bytes_["total_bytes_median"]
    return {"arm": name, "rate_mbit": rate_mbit, "n": len(rows), "ok": counts["successful"],
            "mean": mean(ok), "p50": B.pctl(ok, 0.5), "p95": B.pctl(ok, 0.95),
            "two_rtt_rate": (sum(1 for t in ok if t > 1.5 * RTT_MS)
                             / float(len(ok))) if ok else None,
            "ff_bytes_med": ff_med,
            "added_bytes": max(0, ff_med - K * W) if ff_med is not None else None,
            "ms": ok,
            "ips_evidence": ips_evidence(rows, ips, fec, m, N),
            "client_rows": [dict(row) for row in rows], "client_stats": cs, "server_stats": srv,
            "collection": collection, "denominators": counts, "byte_evidence": bytes_,
            "err": err}


def main():
    B.harden()
    B.require_root()
    B.require_bin()
    B.setup()

    out = {"rtt_ms": RTT_MS, "group": GROUP, "cert": CERT, "n": N,
           "arms": [], "fits": {}, "checks": [], "run_id": uuid.uuid4().hex,
           "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "statistical_limits": {
               "ci": "batch means with Welch degrees of freedom; iid fallback is reported for short samples",
               "dependence": "residual batch, arm, block, and condition dependence is not estimated",
               "sample_size": "normal-approximation diagnostic; no automatic resampling or precision guarantee",
               "scope": "x25519, cert 2000 B, RTT 50 ms, no loss, fixed arms; not general PQ adaptation evidence"}}

    def add(name, ok, detail):
        out["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
        print("[%s] %-56s %s"
              % ("통과" if ok else "실패", name, detail if not ok else detail[:70]))
        sys.stdout.flush()

    print("=" * 100)
    print("업링크 대역 실측 - 임계 아래에서 첫 비행 바이트만 바꿔 HCT 기울기를 잰다")
    print("=" * 100)
    print("%-8s %-8s %-9s %-9s %-9s %-9s %s"
          % ("조건", "팔", "추가B", "평균", "p50", "2-RTT", "함의"))

    for cname, rate, up_policy in CONDS:
        blocks = {}
        for _pos, (aname, fec, m, ips) in enumerate(
                list(ARMS) + list(reversed(ARMS))):
            b = run_arm(aname, fec, m, ips, rate, up_policy,
                        run_id=out["run_id"], block_pos=_pos)
            b["pos"] = _pos
            blocks.setdefault(aname, []).append(b)
            print("   블록 %-8s %-8s 평균 %-9.3f (유효 %d)"
                  % (cname, aname, b["mean"] or -1, b["ok"]))
            sys.stdout.flush()

        rows = []
        for aname, fec, m, ips in ARMS:
            bs = blocks[aname]
            r = merge_blocks(bs, aname, fec, m, ips, cname)
            out["arms"].append(r)
            rows.append(r)
            print("%-8s %-8s %-9s %-9.3f %-9.3f %-9s %s"
                  % (cname, aname, r["added_bytes"], r["mean"] or -1,
                     r["p50"] or -1,
                     ("%.1f%%" % (100 * (r["two_rtt_rate"] or 0))),
                     r["err"] or ""))
            sys.stdout.flush()

        _lt = load_trace(blocks)
        out.setdefault("load_trace", {})[cname] = _lt
        _worst_lag = max((x["lag1"] for x in _lt if x["lag1"] is not None),
                         default=None)
        print("    [정보] 부하 자국 %s: 최대 lag-1 %s | 팔별 %s | 09-01 깨끗한 판 %s"
              % (cname,
                 ("%+.3f" % _worst_lag) if _worst_lag is not None else "-",
                 " ".join("%s%s%+.2f" % (x["arm"], x["pos"], x["lag1"])
                          for x in _lt if x["lag1"] is not None),
                 LOAD_TRACE_REF_0901.get(cname, "기준 없음")))
        sys.stdout.flush()

        good = [r for r in rows if r["mean"] is not None and r["added_bytes"] is not None]
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
            "evidence_scope": "diagnostic from the same four arms; not independent evidence or a critical-path-only bandwidth estimate",
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

    incomplete = ["%s/%s: %s" % (r["cond"], r["arm"], r["denominators"])
                  for r in out["arms"] if not r["denominators"]["complete"]]
    add("0. 전 팔 요청/반환/성공과 지연·바이트 원자료 분모가 일치한다",
        bool(out["arms"]) and not incomplete,
        "완전한 팔 %d/%d | %s" % (len(out["arms"]) - len(incomplete), len(out["arms"]),
                                   "; ".join(incomplete)))

    worst2 = max((r["two_rtt_rate"] or 0) for r in out["arms"])
    add("1. 전 팔이 1-RTT (칸이 안 바뀌어야 차이가 직렬화 시간이다)",
        worst2 < 0.02, "최대 2-RTT 비율 %.1f%%" % (100 * worst2))

    per_arm = []
    for cname, rate, up_policy in CONDS:
        rows = [r for r in out["arms"] if r["cond"] == cname]
        base = next((r for r in rows if r["arm"] == "base"), None)
        if not base or base["mean"] is None:
            continue
        for r in rows:
            if (r["arm"] == "base" or r["mean"] is None
                    or r["added_bytes"] is None or base["added_bytes"] is None):
                continue
            meas = r["mean"] - base["mean"]
            k_, m_, w_ = K, (1 if r["arm"] == "m1" else
                             (2 if r["arm"] == "m2" else 0)), \
                (1452 if r["arm"] == "pad" else W)
            crit = (POL.critical_path_bytes(k_, m_, w_)
                    - POL.critical_path_bytes(K, 0, W))
            pred_new = POL.tx_cost_ms(max(0, crit), up_policy)
            pred_old = POL.tx_cost_ms(r["added_bytes"], up_policy)
            _ci = contrast_ci([r["ms"], base["ms"]], [1, -1])
            _half = _ci["half_ms"]
            _res = meas - pred_new
            per_arm.append({"cond": cname, "arm": r["arm"],
                            "added_bytes": r["added_bytes"],
                            "critical_bytes": crit, "measured_ms": meas,
                            "pred_critical_ms": pred_new,
                            "pred_naive_ms": pred_old,
                            "ci95_half_ms": _half,
                            "ci_diagnostic": _ci,
                            "residual_ms": _res,
                            "n_per_arm": min(len(r["ms"]), len(base["ms"])),
                            "n_needed_for_ruler": need_n(r["ms"], base["ms"],
                                                         RULER_MS),
                            "n_needed_semantics": "normal approximation diagnostic based on batch-derived effective SD; no precision guarantee"})
    out["per_arm"] = per_arm
    print()
    print("%-8s %-6s %-9s %-9s %-11s %-11s %s"
          % ("조건", "팔", "추가B", "임계B", "실측Δ", "임계경로식", "옛식(전체B)"))
    for x in per_arm:
        print("%-8s %-6s %-9s %-9d %-11.3f %-11.3f %.3f"
              % (x["cond"], x["arm"], x["added_bytes"], x["critical_bytes"],
                 x["measured_ms"], x["pred_critical_ms"], x["pred_naive_ms"]))

    unl = [x for x in per_arm if x["cond"] == "무제한"]
    worst_unl = max((x["measured_ms"] for x in unl), default=0.0)
    fastest_unl = min((x["measured_ms"] for x in unl), default=0.0)
    add("2. 무제한 조건: 어느 팔도 base 대비 0.2 ms 이상 **더 들지** "
        "않는다 (모형의 10 Mbps 는 여기서 틀렸다)",
        worst_unl < 0.2 and unl,
        "최대 비용 %+.3f ms / 가장 빨랐던 팔 %+.3f ms / "
        "옛 식 예측 최대 %.3f ms"
        % (worst_unl, fastest_unl,
           max((x["pred_naive_ms"] for x in unl), default=0.0)))

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
                         " 표본 진단 n=%s(지금 %d, 정밀도 보장 아님)" % (x["n_needed_for_ruler"],
                                               x["n_per_arm"])))
                     for x, v in _v)))

    err_old = max((abs(x["measured_ms"] - x["pred_naive_ms"])
                   for x in sh), default=0.0)
    add("4. [부정] 옛 식(추가 바이트 전부)은 실측과 0.5 ms 넘게 어긋난다",
        err_old > 0.5,
        "옛 식 최대 오차 %.3f ms vs 임계경로 식 %.3f ms" % (err_old, err_new))

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
    _ci5 = (contrast_ci([_m2s_r["ms"], _bs_r["ms"], _m2u_r["ms"], _bu_r["ms"]],
                        [1, -1, -1, 1]) if all((_m2s_r, _bs_r, _m2u_r, _bu_r)) else None)
    _h5 = _ci5["half_ms"] if _ci5 is not None else None
    out["shaping_contrast_ci"] = _ci5
    ok5 = bool(_d5 is not None and _h5 is not None and _d5 > _h5)
    _imp = (out["fits"].get("10Mbps") or {}).get("implied_mbps")
    add("5. [부정] m2 팔의 비용이 성형 조건에서만 나타난다 "
        "(성형이 실제로 걸렸다)",
        ok5, "무제한 %+.3f ±%.3f vs 10Mbps %+.3f ±%.3f -> 차 %+.3f ±%.3f "
             "| 같은 팔 회귀 진단: 함의 대역 %s Mbps (걸린 값 10)"
        % (m2u if m2u is not None else -1, _hu or -1,
           m2s if m2s is not None else -1, _hs or -1,
           _d5 if _d5 is not None else -1, _h5 or -1,
           ("%.1f" % _imp) if _imp not in (None, float("inf")) else "무한"))

    npass = sum(1 for c in out["checks"] if c["ok"])
    out["passed"] = npass
    out["total"] = len(out["checks"])
    out["finished_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    print("-" * 100)
    print("%d / %d 통과" % (npass, len(out["checks"])))
    print("saved:", B.save("p16_uplink.json", out))
    return 0 if npass == len(out["checks"]) else 1


if __name__ == "__main__":
    sys.exit(main())
