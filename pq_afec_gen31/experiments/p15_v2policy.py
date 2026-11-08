from __future__ import annotations

import os
import json
import re
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B
import blockstat as BST
import policy_evaluation as PE
from padfec import policy as POL

RTT_MS = 50.0
GROUP = "x25519"
K = 1
N_DEFAULT = 400
N_PRECISE = 1600
N = int(os.environ.get("PADFEC_P15_N")
        or (N_PRECISE if "--precise" in sys.argv else N_DEFAULT))
CACHE = "/tmp/padfec_p15_cache.json"

CONDS = [
    ("임계아래/무손실", 2955, 0.0),
    ("임계아래/손실2%", 2955, 2.0),
    ("임계아래/손실5%", 2955, 5.0),
    ("임계사이/무손실", 4032, 0.0),
    ("임계사이/손실2%", 4032, 2.0),
    ("임계사이/손실5%", 4032, 5.0),
]

UPLINK_MBPS = 0.0

ROUNDS_CLEAN = 10
ROUNDS_LOSSY = 10

FIXED = [("m0", "off", 0, 0), ("m1", "on", 1, 0), ("m2", "on", 2, 0),
         ("pad", "off", 0, 1281)]


def mean(v):
    return (sum(v) / len(v)) if v else None


def _delta_only_crossover(cert=4032, rtt_ms=RTT_MS):
    lo, hi = 0.0, 0.05
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        d = POL.decide_v2(C=267, cert_bytes=cert, rtt_ms=rtt_ms, p=mid,
                          burst=1.0, s0=None,
                          s0_base=POL.S0_BASE_X25519,
                          c_pkt=POL.C_PKT_POLICY_DEFAULT,
                          uplink_mbps=UPLINK_MBPS)
        if d["choice"]["mode"] == "pad":
            lo = mid
        else:
            hi = mid
    return lo


def added_bytes(row):
    ff = (row.get("first_flight_bytes") or 0) + (
        row.get("first_flight_parity_bytes") or 0)
    return max(0, ff - K * 1280)


def cache_evidence(path):
    try:
        with open(path, encoding="utf-8") as stream:
            return {"available": True, "value": json.load(stream)}
    except (OSError, ValueError) as exc:
        return {"available": False, "reason": type(exc).__name__}


def round_evidence(rows, cs, n_req):
    n_ok = sum(1 for row in rows if row.get("ok"))
    return {"n_req": n_req, "n_failed": len(rows) - n_ok,
            "n_missing": max(0, n_req - len(rows)),
            "client_rows": rows, "client_stats": cs,
            "joint_ips_m": dict(Counter("%s|%s" % (x.get("ips_used"), x.get("m_used"))
                                        for x in rows)),
            "recording_scope": "available client rows; actual k and ACK RTT retain their recorded presence or absence"}


def window_added_bytes(blocks, ids):
    selected = [b for b in blocks if b.get("round") in set(ids)]
    if len(selected) != len(set(ids)) or any("client_rows" not in b for b in selected):
        return None
    values = []
    for block in selected:
        rows = block["client_rows"]
        if not rows or any(type(x.get("first_flight_bytes")) is not int or
                           type(x.get("first_flight_parity_bytes")) is not int for x in rows):
            return None
        values.append(mean([added_bytes(x) for x in rows]))
    return mean(values)


ROUNDS_ORDER = ["auto"] + [f[0] for f in FIXED]


def run_condition(cert, loss, rounds, jr):
    if rounds < 2 * len(ROUNDS_ORDER) or rounds % (2 * len(ROUNDS_ORDER)) or N < rounds or N % rounds:
        raise ValueError("P15 requires two complete Latin squares and N divisible by rounds")
    key = "%s|latin|%d|%.1f|r%d|n%d" % (PE.PROTOCOL, cert, loss, rounds, N)
    if jr.has(key):
        v = jr.get(key)
        return v["fixed"], v["auto"]
    n_blk = N // rounds
    B.set_netem(RTT_MS / 2.0, loss_c2s=loss)
    try:
        os.unlink(CACHE)
    except OSError:
        pass
    fx_rows = {f[0]: [] for f in FIXED}
    fx_blocks = {f[0]: [] for f in FIXED}
    fx_err = {f[0]: "" for f in FIXED}
    fixed_by = {f[0]: f for f in FIXED}
    hist = []
    collection_provenance = {"run_id": jr.run_id, "journal_fingerprint": jr.fingerprint,
                             "journal_key": key, "cert": cert, "loss_c2s_percent": loss,
                             "group": GROUP, "expected_k_flush_hint": K,
                             "time_scope": "round collection intervals, not individual connection timestamps"}
    p, sp = B.start_server(cert, fec="on")
    try:
        for rnd in range(1, rounds + 1):
            r = (rnd - 1) % len(ROUNDS_ORDER)
            order = ROUNDS_ORDER[r:] + ROUNDS_ORDER[:r]
            for pos, aname in enumerate(order):
                started_ns = time.time_ns()
                if aname == "auto":
                    cache_before = cache_evidence(CACHE)
                    rows, cs, err = B.run_client(
                        GROUP, N, fec="auto", m=1, gap_ms=8, timeout_s=10,
                        expect_k=K,
                        extra=["-cache", CACHE, "-probe-every", "20"],
                        uplink_mbps=UPLINK_MBPS)
                    ok = [x["ms"] for x in rows if x.get("ok")]
                    why = ""
                    mp = None
                    for _r in reversed(rows):
                        _w = _r.get("m_why", "") or ""
                        _m = re.search(r"p=([0-9.]+)", _w)
                        if _m:
                            why, mp = _w, _m
                            break
                    if not why and rows:
                        why = rows[-1].get("m_why", "") or ""
                    hist.append({
                        **round_evidence(rows, cs, N),
                        "collection_provenance": collection_provenance,
                        "round": rnd, "pos": pos, "n": len(rows), "ok": len(ok),
                        "started_at_unix_ns": started_ns,
                        "finished_at_unix_ns": time.time_ns(),
                        "mean": mean(ok),
                        "p50": B.pctl(ok, 0.5), "p95": B.pctl(ok, 0.95),
                        "tail": (sum(1 for x in ok if x > 1.5 * RTT_MS)
                                 / float(len(ok)) if ok else None),
                        "ips_used": dict(Counter(x.get("ips_used")
                                                 for x in rows)),
                        "m_used": dict(Counter(x.get("m_used") for x in rows)),
                        "added_bytes_mean": mean([added_bytes(x)
                                                  for x in rows]),
                        "p_est": float(mp.group(1)) if mp else None,
                        "ms": ok,
                        "ms_rows": [x["ms"] if x.get("ok") else None
                                    for x in rows],
                        "probe_rows": [(x.get("m_why") or "")
                                       .startswith("탐색") for x in rows],
                        "cache_before": cache_before,
                        "cache_after": cache_evidence(CACHE),
                        "why_last": why, "err": err})
                    continue
                _n, fec, m, ips = fixed_by[aname]
                rows, cs, err = B.run_client(
                    GROUP, n_blk, fec=fec, m=max(m, 1), ips=ips,
                    gap_ms=8, timeout_s=10, expect_k=K,
                    uplink_mbps=UPLINK_MBPS)
                if err:
                    fx_err[aname] = err
                fx_rows[aname].extend(rows)
                ok = [x["ms"] for x in rows if x.get("ok")]
                fx_blocks[aname].append({"round": rnd, "pos": pos,
                                         **round_evidence(rows, cs, n_blk),
                                         "collection_provenance": collection_provenance,
                                         "n": len(rows), "ok": len(ok),
                                         "mean": mean(ok), "ms": ok,
                                         "started_at_unix_ns": started_ns,
                                         "finished_at_unix_ns": time.time_ns(),
                                         "ms_rows": [x["ms"] if x.get("ok") else None
                                                     for x in rows]})
            print("   라운드 %2d/%d  auto %.2f  %s"
                  % (rnd, rounds, hist[-1]["mean"] or -1,
                     "  ".join("%s(자리%d) %.2f"
                               % (a, fx_blocks[a][-1]["pos"],
                                  fx_blocks[a][-1]["mean"] or -1)
                               for a in order if a != "auto")), flush=True)
    finally:
        B.stop_server(p)
    ss = B.read_server_stats(sp)
    fixed = {}
    for aname, fec, m, ips in FIXED:
        rows = fx_rows[aname]
        ok = [x["ms"] for x in rows if x.get("ok")]
        fixed[aname] = {
            **round_evidence(rows, {}, n_blk * rounds),
            "arm": aname, "cert": cert, "loss": loss, "n": len(rows),
            "ok": len(ok), "mean": mean(ok), "p50": B.pctl(ok, 0.5),
            "p95": B.pctl(ok, 0.95),
            "tail": (sum(1 for x in ok if x > 1.5 * RTT_MS) / float(len(ok))
                     if ok else None),
            "added_bytes_mean": mean([added_bytes(x) for x in rows]),
            "blocks": fx_blocks[aname],
            "srv_recovered": ss.get("recovered"),
            "srv_crc_fail": ss.get("recover_crc_fail"),
            "ms": ok,
            "ms_rows": [x["ms"] if x.get("ok") else None for x in rows],
            "srv_stats_present": bool(ss),
            "server_statistics_scope": "shared condition total, not separate statistics for this arm",
            "err": fx_err[aname]}
    au = {"cert": cert, "loss": loss, "rounds": hist,
          "final": hist[-1] if hist else None,
          "srv_stats_present": bool(ss),
          "server_stats": ss,
          "server_statistics_scope": "one server for the entire condition and all arms",
          "srv_crc_fail": ss.get("recover_crc_fail")}
    complete = (all(len(fx_rows[f[0]]) == n_blk * rounds and
                    all(row.get("ok") for row in fx_rows[f[0]]) for f in FIXED)
                and hist and all(h["n"] == h["ok"] == N for h in hist))
    if (complete and not any(fx_err.values()) and not any(h["err"] for h in hist)
            and bool(ss) and (ss.get("recover_crc_fail") or 0) == 0):
        jr.record(key, {"fixed": fixed, "auto": au})
    return fixed, au


def main():
    B.harden()
    B.require_root()
    B.require_bin()
    B.setup(mtu=1500)

    from _journal import Journal, code_fingerprint
    fp = code_fingerprint(["experiments/p15_v2policy.py",
                           "experiments/quicbed/qamp.go",
                           "experiments/quicbed/policy.go",
                           "experiments/quicbed/pfail_table.go",
                           "experiments/padbed.py",
                           "experiments/policy_evaluation.py",
                           "experiments/blockstat.py", "experiments/_journal.py"], ROOT)
    jr = Journal(os.path.join(B.STATE, "p15_units.jsonl"), fp)

    out = {"rtt_ms": RTT_MS, "n": N, "group": GROUP,
           "interleaved": True, "analysis_protocol": PE.PROTOCOL,
           "comparison_window": "equal-weighted matching late acquisition rounds",
           "limitations": ["Auto has N trials per round, each fixed arm N/rounds; exposure and wall-clock durations remain unequal.",
                           "One run with chronological split, not an independent confirmatory experiment."],
           "rows": [], "auto": [], "regret": [], "checks": []}

    def add(name, ok, detail):
        out["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
        print("[%s] %-58s %s" % ("통과" if ok else "실패", name, detail[:86]),
              flush=True)

    print("=" * 104)
    print("v2 정책(auto) 대 고정 {m0, m1, m2, pad(δ=1)} - 조건마다 고정팔 n=%d, "
          "auto 라운드 n=%d (교대 측정)" % (N, N))
    print("=" * 104)

    for name, cert, loss in CONDS:
        rounds = ROUNDS_CLEAN if loss == 0.0 else ROUNDS_LOSSY
        print("### %s (cert %d, 손실 %g%%) - %d 라운드 교대"
              % (name, cert, loss, rounds), flush=True)
        arms, au = run_condition(cert, loss, rounds, jr)
        if set(arms) != {a[0] for a in FIXED}:
            out.setdefault("dropped", []).append(
                {"cond": name, "cert": cert, "loss": loss, "why": "missing candidate",
                 "raw_arms": arms, "raw_auto": au})
            continue
        for aname, fec, m, ips in FIXED:
            r = arms[aname]
            out["rows"].append(r)
            print("%-16s %-5s 평균 %-8.2f p95 %-8.2f 꼬리 %5.1f%% 복구 %-5s "
                  "추가B %s"
                  % (name, aname, r["mean"] or -1, r["p95"] or -1,
                     100 * (r["tail"] or 0), r["srv_recovered"],
                     round(r["added_bytes_mean"] or 0, 1)), flush=True)
        au["cond"] = name
        out["auto"].append(au)
        fin = au["final"]
        for h in au["rounds"]:
            print("%-16s auto r%d 평균 %-8.2f p추정 %-8s ips %s m %s"
                  % (name, h["round"], h["mean"] or -1, h["p_est"],
                     h["ips_used"], h["m_used"]), flush=True)

        fixed_means = {a: arms[a]["mean"] for a in arms
                       if arms[a]["mean"] is not None}
        if not fixed_means or not fin or fin["mean"] is None:
            out.setdefault("dropped", []).append(
                {"cond": name, "cert": cert, "loss": loss, "why": "측정 실패"})
            print("    -> !! 측정 실패로 이 조건이 빠졌다: %s" % name,
                  flush=True)
            continue
        try:
            if set(arms) != {a[0] for a in FIXED}:
                raise ValueError("missing fixed candidate")
            if any(arms[a].get("n") != N or arms[a].get("err") for a in arms):
                raise ValueError("missing fixed trials or client error")
            if len(au["rounds"]) != rounds or any(h.get("n") != N or h.get("err") for h in au["rounds"]):
                raise ValueError("missing auto rounds/trials or client error")
            matched = PE.matched_diagnostics(
                au["rounds"], {a: arms[a]["blocks"] for a in arms},
                range(1, rounds // 2 + 1), range(rounds // 2 + 1, rounds + 1), "round",
                family_size=len(FIXED) * len(CONDS))
        except (KeyError, TypeError, ValueError) as exc:
            out.setdefault("dropped", []).append(
                {"cond": name, "cert": cert, "loss": loss, "why": str(exc)})
            continue
        late_ids = set(matched["evaluation_ids"])
        def _late_ms(a):
            return PE.block_window(arms[a]["blocks"], matched["evaluation_ids"], "round")[1]
        fixed_means_late = matched["fixed_means_ms"]
        best = matched["best_observed"]
        best_full = min(fixed_means, key=fixed_means.get)
        auto_late_mean = matched["auto_mean_ms"]
        reg = matched["observed_best_regret_ms"]
        reg_full = fin["mean"] - fixed_means[best_full]
        legacy_fixed_late = {a: mean(_late_ms(a)) for a in arms}
        legacy_best = min(legacy_fixed_late, key=legacy_fixed_late.get)
        legacy_regret = fin["mean"] - legacy_fixed_late[legacy_best]
        selected = matched["selected_fixed"]
        reg_hold = matched["selected_fixed_contrast"]["mean_ms"]

        n_probe_fin = sum(1 for t, probe in zip(fin.get("ms_rows", []), fin.get("probe_rows", []))
                          if t is not None and probe)
        probe_tax = reg_sel = None
        taxes = []
        for h in au["rounds"]:
            if h["round"] not in late_ids:
                continue
            raw, flags = h.get("ms_rows", []), h.get("probe_rows", [])
            if len(raw) != len(flags):
                break
            probes = [t for t, flag in zip(raw, flags) if flag and t is not None]
            choices = [t for t, flag in zip(raw, flags) if not flag and t is not None]
            if not choices:
                break
            taxes.append((len(probes) / (len(probes) + len(choices))) *
                         (mean(probes) - mean(choices)) if probes else 0.0)
        if len(taxes) == len(late_ids):
            probe_tax = mean(taxes)
            reg_sel = reg - probe_tax

        late_auto, _ = PE.block_window(au["rounds"], matched["evaluation_ids"], "round")
        late_fixed, _ = PE.block_window(arms[best]["blocks"], matched["evaluation_ids"], "round")
        paired = PE.paired_contrast(late_auto, late_fixed)
        reg_paired, reg_paired_half = paired["mean_ms"], paired["half_ms"]
        se_reg, half_reg = paired["se_ms"], paired["half_ms"]

        rr = au["rounds"] if au else []
        def _modal(dd):
            return (max(dd.items(), key=lambda kv: kv[1])[0]
                    if dd else None)

        conv_ok, conv_why = False, "라운드가 3 개 미만"
        if len(rr) >= 3:
            _ms = [_modal(r_["m_used"]) for r_ in rr[-3:]]
            _is = [_modal(r_["ips_used"]) for r_ in rr[-3:]]
            conv_ok = (all(v not in (None, "null", "None") for v in _ms + _is)
                       and len(set(_ms)) == 1 and len(set(_is)) == 1)
            ps = [r_["p_est"] for r_ in rr[-3:]
                  if r_["p_est"] is not None]
            _dr = ((max(ps) - min(ps)) / max(ps)
                   if len(ps) == 3 and max(ps) > 0 else None)
            conv_why = ("최빈 선택 ips%s m%s | p 표류 %s"
                        % (_is, _ms,
                           ("%.1f%%" % (100 * _dr))
                           if _dr is not None else "읽지 못함"))

        out["regret"].append({
            "cond": name, "cert": cert, "loss": loss,
            "best_fixed": best, "best_fixed_mean": fixed_means_late[best],
            "best_fixed_full": best_full,
            "best_fixed_mean_full": fixed_means[best_full],
            "fixed_means_late": fixed_means_late,
            "auto_final_mean": fin["mean"], "auto_mean_late": auto_late_mean,
            "regret_ms": reg, "matched_block_diagnostic": matched,
            "best_fixed_holdout": selected,
            "ci95_half_holdout_ms": matched["selected_fixed_contrast"]["half_ms"],
            "legacy_final_vs_late": {"best_fixed": legacy_best,
                                     "regret_ms": legacy_regret,
                                     "fixed_mean": legacy_fixed_late[legacy_best],
                                     "ci95_half_ms": BST.batch_diff_half(fin.get("ms") or [], _late_ms(legacy_best))},
            "regret_full_ms": reg_full,
            "regret_full_scope": "legacy final auto round vs pooled all fixed rounds",
            "probe_tax_window": "same equally weighted late rounds as regret_ms",
            "se_method": "paired_rounds",
            "regret_holdout_ms": reg_hold,
            "probe_rounds_final": n_probe_fin,
            "probe_tax_ms": probe_tax,
            "regret_sel_ms": reg_sel,
            "se_regret_ms": se_reg,
            "ci95_half_ms": half_reg,
            "ci_method": "paired t on matched round means; observed-best selection is descriptive",
            "regret_paired_late_ms": reg_paired,
            "regret_paired_late_ci95_half_ms": reg_paired_half,
            "paired_rounds": paired["blocks"],
            "converged": conv_ok, "converge_why": conv_why,
            "convergence_scope": "separate IPS and m marginal modes over the final three rounds; not joint-choice, loss-estimator or optimal-policy convergence",
            "fixed_means": fixed_means,
            "auto_added_bytes": fin["added_bytes_mean"],
            "best_added_bytes": arms[best]["added_bytes_mean"],
            "legacy_byte_windows": {"auto_added_bytes": [rounds],
                                    "best_added_bytes": list(range(1, rounds + 1))},
            "matched_added_bytes": {"round_ids": matched["evaluation_ids"],
                                    "estimator": "equal round means of all returned trials; k=K baseline",
                                    "auto": window_added_bytes(au["rounds"], matched["evaluation_ids"]),
                                    "best_fixed": window_added_bytes(arms[best]["blocks"], matched["evaluation_ids"])},
            "candidate_scope": "auto may use m3 or a padding/FEC combination outside the fixed m0/m1/m2/pad candidates; negative regret is not equal-resource adaptive gain"})
        print("    -> 최선 고정팔 %s (수렴후창 %.2f ms), auto 수렴후 %.2f ms, "
              "후회 %+.2f ms (전구간창 %+.2f, 홀드아웃 %s, ±%s ms) | 수렴 %s (%s)"
              % (best, fixed_means_late[best], auto_late_mean, reg, reg_full,
                 ("%+.2f" % reg_hold) if reg_hold is not None else "-",
                 ("%.2f" % half_reg) if half_reg is not None else "-",
                 "예" if conv_ok else "**아니오**", conv_why),
              flush=True)

    print()
    print("=" * 104)
    add("6 조건이 전부 측정됐다 (빠진 조건이 헤드라인을 좋게 만들 수 없다)",
        len(out["regret"]) == len(CONDS),
        "%d/%d | 빠짐 %s" % (len(out["regret"]), len(CONDS),
                            [d["cond"] for d in out.get("dropped", [])]
                            or "없음"))
    add("각 고정팔 행에 공유한 조건 서버 통계가 있었다 (연결 대응 검사가 아님)",
        all(r.get("srv_stats_present") for r in out["rows"]) and out["rows"],
        "%d/%d 행, 조건 합계를 각 팔에 공유" % (sum(1 for r in out["rows"]
                         if r.get("srv_stats_present")), len(out["rows"])))

    regs = [r["regret_ms"] for r in out["regret"]]
    regs_h = [r["regret_holdout_ms"] for r in out["regret"]
              if r["regret_holdout_ms"] is not None]
    cis = [r["ci95_half_ms"] for r in out["regret"]
           if r["ci95_half_ms"] is not None]
    worst = max(regs) if regs else None
    out["worst_regret_ms"] = worst
    out["worst_regret_holdout_ms"] = max(regs_h) if regs_h else None
    out["worst_ci95_half_ms"] = max(cis) if cis else None
    add("후반 대응 라운드 최악 후회 점추정 < 2 ms",
        worst is not None and worst < 2.0,
        "최악 %s ms | 조건별 %s"
        % (("%+.2f" % worst) if worst is not None else "데이터 없음",
           ["%+.2f" % v for v in regs]))
    add("후반 대응 라운드 최악 후회 < 2 ms (내부 시간분할 비교)",
        len(regs_h) == len(CONDS) and max(regs_h) < 2.0,
        "최악 %s ms | 조건별 %s"
        % (("%+.2f" % max(regs_h)) if regs_h else "데이터 없음",
           ["%+.2f" % v for v in regs_h]))
    add("후회 추정의 95% 신뢰반폭이 1 ms 미만 (기준 2 ms 를 판정할 정밀도)",
        len(cis) == len(CONDS) and max(cis) < 1.0,
        "최대 반폭 %s ms | 조건별 %s"
        % (("%.2f" % max(cis)) if cis else "-",
           ["%.2f" % v for v in cis]))
    nconv = sum(1 for r in out["regret"] if r.get("converged"))
    add("모든 조건의 마지막 3라운드 IPS·m 각각의 최빈값이 안정적이었다",
        nconv == len(out["regret"]) and out["regret"],
        "%d/%d | %s" % (nconv, len(out["regret"]),
                        "; ".join("%s:%s" % (r["cond"], r["converge_why"])
                                  for r in out["regret"]
                                  if not r.get("converged")) or "전부 수렴"))

    conv = next((a for a in out["auto"] if a["cert"] == 4032
                 and a["loss"] == 0.0), None)
    if conv and conv["final"]:
        fin = conv["final"]
        n1281 = fin["ips_used"].get(1281, fin["ips_used"].get("1281", 0))
        add("임계사이/무손실: 마지막 라운드 IPS 1281이 과반 (FEC 결합 포함)",
            n1281 > N // 2, "ips 분포 %s | p추정 %s" % (fin["ips_used"],
                                                       fin["p_est"]))
        ab = fin["added_bytes_mean"]
        m2b = next((r["added_bytes_mean"] for r in out["rows"]
                    if r["arm"] == "m2" and r["cert"] == 4032
                    and r["loss"] == 0.0), None)
        add("임계사이/무손실: auto 가 최대치로 도배하지 않는다 "
            "(m2 고정팔의 70% 미만)",
            ab is not None and m2b and ab < 0.7 * m2b,
            "auto 평균 추가 %.1f B vs m2 %.1f B" % (ab or -1, m2b or -1))
        _pcrit = _delta_only_crossover()
        _pfloor = 0.5 / 101.0
        add("δ 단독 구간은 추정기가 도달할 수 없다 "
            "(그래서 결합을 고르는 것이 옳다)",
            _pcrit < _pfloor,
            "pad 단독이 이기는 p < %.2e vs 추정기 하한 %.2e (%.0f 배)"
            % (_pcrit, _pfloor, _pfloor / max(_pcrit, 1e-12)))

    pad4032 = next((r for r in out["rows"] if r["arm"] == "pad"
                    and r["cert"] == 4032 and r["loss"] == 0.0), None)
    m04032 = next((r for r in out["rows"] if r["arm"] == "m0"
                   and r["cert"] == 4032 and r["loss"] == 0.0), None)
    if pad4032 and m04032 and pad4032["p50"] and m04032["p50"]:
        d = m04032["p50"] - pad4032["p50"]
        add("pad(δ=1) 고정팔이 맨몸보다 1 왕복 빠르다 (임계사이/무손실)",
            d >= 0.8 * RTT_MS, "%.2f ms = %.3f RTT" % (d, d / RTT_MS))

    crc = sum(a.get("srv_crc_fail") or 0 for a in out["auto"])
    add("모든 팔에서 복구 CRC 실패 0", crc == 0, "총 %d 건 (조건별 합)" % crc)
    _bad_se = [r["cond"] for r in out["regret"] if r.get("se_method") != "paired_rounds"]
    add("모든 조건의 반폭이 같은 후반 라운드의 대응 평균차로 나왔다",
        out["regret"] and not _bad_se,
        "대응 라운드 대조가 없는 조건: %s" % (_bad_se or "없음"))

    out["journal_provenance"] = jr.provenance()
    npass = sum(1 for c in out["checks"] if c["ok"])
    out["passed"] = npass
    out["total"] = len(out["checks"])
    print("-" * 104)
    print("%d / %d 통과" % (npass, len(out["checks"])))
    _fname = ("smoke_" if N < N_DEFAULT else "") + "p15_v2policy.json"
    print("saved:", B.save(_fname, out))
    return 0 if npass == len(out["checks"]) else 1


if __name__ == "__main__":
    sys.exit(main())
