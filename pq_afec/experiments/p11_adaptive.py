from __future__ import annotations

import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B
import blockstat as BST
import policy_evaluation as PE
from padfec import policy as POL
from _journal import Journal, code_fingerprint

RTT_MS = 50.0
GROUP = "X25519MLKEM768"
K = 2
N_DEFAULT = 600
N_PRECISE = 4000
N = int(os.environ.get("PADFEC_P11_N")
        or (N_PRECISE if "--precise" in sys.argv else N_DEFAULT))
CACHE = "/tmp/padfec_p11_cache.json"

UPLINK_MBPS = 0.0

FIXED_ARMS = tuple("m%d" % i for i in range(POL.M_MAX_DEFAULT + 1))
ALL_ARMS = FIXED_ARMS + ("auto",)

CONDS = [
    ("임계아래/무손실", 2955, 0.0),
    ("임계아래/손실2%", 2955, 2.0),
    ("임계아래/손실5%", 2955, 5.0),
    ("임계위/무손실", 9000, 0.0),
    ("임계위/손실2%", 9000, 2.0),
    ("임계위/손실5%", 9000, 5.0),
]


def mean(v):
    return (sum(v) / len(v)) if v else None


def tail_rate(v, thresh):
    return (sum(1 for x in v if x > thresh) / float(len(v))) if v else None


BLOCKS = 10
N_REQ = N
N = (N // BLOCKS) * BLOCKS
if N != N_REQ:
    print("   N=%d 은 블록 %d 로 안 나뉜다 - 팔당 %d 판으로 맞춘다"
          % (N_REQ, BLOCKS, N), flush=True)


def run_condition(cert, loss, jr):
    if N < BLOCKS or BLOCKS % (2 * len(ALL_ARMS)):
        raise ValueError("P11 requires two complete Latin squares and positive block sizes")
    key = "%s|%d|%.1f|latin|n%d|b%d" % (PE.PROTOCOL, cert, loss, N, BLOCKS)
    if jr.has(key):
        return jr.get(key)
    n_blk = N // BLOCKS
    B.set_netem(RTT_MS / 2.0, loss_c2s=loss)
    try:
        os.unlink(CACHE)
    except OSError:
        pass
    rows_by = {a: [] for a in ALL_ARMS}
    blocks_by = {a: [] for a in ALL_ARMS}
    err_by = {a: "" for a in ALL_ARMS}
    p, sp = B.start_server(cert, fec="on")
    try:
        for b in range(BLOCKS):
            r = b % len(ALL_ARMS)
            order = ALL_ARMS[r:] + ALL_ARMS[:r]
            for pos, arm in enumerate(order):
                if arm == "auto":
                    fec, m, extra = "auto", 1, ["-cache", CACHE]
                else:
                    m = int(arm[1:])
                    fec, extra = ("off" if m == 0 else "on"), []
                started_ns = time.time_ns()
                rows, cs, e = B.run_client(
                    GROUP, n_blk, fec=fec, m=max(m, 1), gap_ms=8,
                    timeout_s=10, expect_k=K, extra=extra,
                    uplink_mbps=UPLINK_MBPS)
                if e:
                    err_by[arm] = e
                row_start = len(rows_by[arm])
                rows_by[arm].extend(rows)
                ok = [x["ms"] for x in rows if x.get("ok")]
                blocks_by[arm].append({"block": b, "pos": pos, "n": len(rows),
                                       "ok": len(ok), "mean": mean(ok),
                                       "row_start": row_start, "row_stop": len(rows_by[arm]),
                                       "started_at_unix_ns": started_ns,
                                       "finished_at_unix_ns": time.time_ns(),
                                       "ms_rows": [x["ms"] if x.get("ok") else None
                                                   for x in rows]})
            print("   블록 %2d/%d  %s"
                  % (b + 1, BLOCKS,
                     "  ".join("%s(자리%d) %.2f"
                               % (a, blocks_by[a][-1]["pos"],
                                  blocks_by[a][-1]["mean"] or -1)
                               for a in order)), flush=True)
    finally:
        B.stop_server(p)
    ss = B.read_server_stats(sp)
    out = {}
    for arm in ALL_ARMS:
        rows = rows_by[arm]
        ok = [r["ms"] for r in rows if r.get("ok")]
        late_blocks = [b for b in blocks_by[arm] if b["block"] >= BLOCKS // 2]
        late_rows = [row for b in late_blocks
                     for row in rows[b["row_start"]:b["row_stop"]]]
        ok_late = [r["ms"] for r in late_rows if r.get("ok")]
        out[arm] = {
            "arm": arm, "cert": cert, "loss": loss,
            "n": len(rows), "ok": len(ok),
            "mean": mean(ok), "mean_late": mean(ok_late),
            "p50": B.pctl(ok, 0.5), "p95": B.pctl(ok, 0.95),
            "tail": tail_rate(ok, 1.5 * RTT_MS),
            "tail_late": tail_rate(ok_late, 1.5 * RTT_MS),
            "m_used": [r.get("m_used") for r in rows],
            "ms_rows": [r["ms"] if r.get("ok") else None for r in rows],
            "probe_rows": [(r.get("m_why") or "").startswith("탐색")
                           for r in rows],
            "ms": ok, "ms_late": ok_late,
            "late_trial_indices": [i for b in late_blocks
                                   for i in range(b["row_start"], b["row_stop"])],
            "m_why": [r.get("m_why") for r in rows[:3]],
            "blocks": blocks_by[arm],
            "srv_recovered": ss.get("recovered"),
            "srv_crc_fail": ss.get("recover_crc_fail"),
            "srv_stats_present": bool(ss),
            "err": err_by[arm]}
    complete = all(len(rows_by[a]) == n_blk * BLOCKS for a in ALL_ARMS)
    if complete and not any(err_by.values()) and bool(ss) and (ss.get("recover_crc_fail") or 0) == 0:
        jr.record(key, out)
    return out


def main():
    B.harden()
    B.require_root()
    B.require_bin()
    B.setup()

    fp = code_fingerprint(["experiments/p11_adaptive.py",
                           "experiments/quicbed/qamp.go",
                           "experiments/quicbed/policy.go",
                           "experiments/quicbed/pfail_table.go",
                           "experiments/padbed.py",
                           "experiments/policy_evaluation.py",
                           "experiments/blockstat.py", "experiments/_journal.py"], ROOT)
    jr = Journal(os.path.join(B.STATE, "p11_units.jsonl"), fp)

    out = {"rtt_ms": RTT_MS, "n": N, "n_requested": N_REQ, "group": GROUP,
           "blocks": BLOCKS, "interleaved": True, "analysis_protocol": PE.PROTOCOL,
           "inference_limits": {
               "confirmatory": False,
               "batch_assumption": "batch means use approximate independence; residual time/cache and cross-arm dependence can remain",
               "observed_best": "best fixed arm selected from the same data; unadjusted intervals are descriptive",
               "internal_split": "chronological selection/evaluation windows within one run, not independent repetitions",
               "selection_check": "modal auto choice belongs to the observed 1 ms allowed fixed-arm set; not every trial is optimal",
               "server_statistics": "shared condition totals copied to arm rows; presence is not per-connection matching completeness"},
           "rows": [], "regret": [], "checks": []}

    def add(name, ok, detail):
        out["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
        print("[%s] %-52s %s" % ("통과" if ok else "실패", name, detail[:76]))
        sys.stdout.flush()

    print("=" * 104)
    print("폐루프(auto) 대 고정 m - 조건마다 팔당 n=%d, 블록 %d 교대" % (N, BLOCKS))
    print("=" * 104)
    print("%-18s %-6s %-9s %-9s %-9s %-9s %s"
          % ("조건", "팔", "평균", "수렴후평균", "꼬리", "복구(조건합)", "고른 m"))

    for name, cert, loss in CONDS:
        print("### %s (cert %d, 손실 %g%%)" % (name, cert, loss), flush=True)
        arms = run_condition(cert, loss, jr)
        if set(arms) != set(ALL_ARMS):
            out.setdefault("dropped", []).append(
                {"cond": name, "cert": cert, "loss": loss, "why": "missing candidate", "raw_arms": arms})
            continue
        for arm in ALL_ARMS:
            r = arms[arm]
            out["rows"].append(r)
            ms = r["m_used"]
            if arm == "auto":
                from collections import Counter
                mtxt = str(dict(sorted(Counter(ms).items(), key=lambda item: str(item[0]))))
            else:
                mtxt = arm[1:]
            print("%-18s %-6s %-9.2f %-9.2f %-9s %-9s %s"
                  % (name, arm, r["mean"] or -1, r["mean_late"] or -1,
                     ("%.1f%%" % (100 * (r["tail"] or 0))),
                     r["srv_recovered"], mtxt))
            sys.stdout.flush()

        try:
            if any(arms[a].get("n") != N or arms[a].get("err") for a in ALL_ARMS):
                raise ValueError("missing trials or client error")
            matched = PE.matched_diagnostics(
                arms["auto"]["blocks"], {a: arms[a]["blocks"] for a in FIXED_ARMS},
                range(BLOCKS // 2), range(BLOCKS // 2, BLOCKS), "block",
                family_size=len(FIXED_ARMS) * len(CONDS))
        except (KeyError, TypeError, ValueError) as exc:
            out.setdefault("dropped", []).append(
                {"cond": name, "cert": cert, "loss": loss, "why": str(exc)})
            continue

        fixed = {a: arms[a]["mean"] for a in FIXED_ARMS
                 if arms[a]["mean"] is not None}
        if not fixed or arms["auto"]["mean"] is None:
            out.setdefault("dropped", []).append(
                {"cond": name, "cert": cert, "loss": loss,
                 "why": "측정 실패", "errs": {a: arms[a].get("err")
                                          for a in arms}})
            print("    -> !! 측정 실패로 이 조건이 빠졌다: %s" % name)
            sys.stdout.flush()
            continue
        best_arm = min(fixed, key=lambda a: fixed[a])
        reg = arms["auto"]["mean"] - fixed[best_arm]
        fixed_late = {a: arms[a]["mean_late"] for a in FIXED_ARMS
                      if arms[a]["mean_late"] is not None}
        best_late = min(fixed_late, key=lambda a: fixed_late[a])
        reg_late = arms["auto"]["mean_late"] - fixed_late[best_late]

        _mr = arms["auto"].get("ms_rows") or []
        _pr = arms["auto"].get("probe_rows") or []
        probe_tax = reg_sel = n_probe_late = None
        if _mr and len(_mr) == len(_pr):
            _ids = arms["auto"]["late_trial_indices"]
            _lp = [_mr[i] for i in _ids if _pr[i] and _mr[i] is not None]
            _ls = [_mr[i] for i in _ids if not _pr[i] and _mr[i] is not None]
            n_probe_late = len(_lp)
            if _lp and _ls:
                _f = len(_lp) / float(len(_lp) + len(_ls))
                probe_tax = _f * (mean(_lp) - mean(_ls))
                reg_sel = reg_late - probe_tax

        sel, ev, hold_values_by = {}, {}, {}
        for a in FIXED_ARMS:
            _, first_values = PE.block_window(arms[a]["blocks"], range(BLOCKS // 2), "block")
            _, last_values = PE.block_window(arms[a]["blocks"], range(BLOCKS // 2, BLOCKS), "block")
            sel[a], ev[a], hold_values_by[a] = mean(first_values), mean(last_values), last_values
        best_hold = min(sel, key=sel.get)
        reg_hold = arms["auto"]["mean_late"] - ev[best_hold]
        se_hold = None

        _se_methods = []

        def _se(v):
            se, method, kb = BST.batch_se_info(v)
            _se_methods.append((method, kb))
            return se

        se_auto = _se(arms["auto"].get("ms_late") or [])
        se_fix = _se(arms[best_late].get("ms_late") or [])
        se_reg = None
        if se_auto is not None and se_fix is not None:
            se_reg = (se_auto ** 2 + se_fix ** 2) ** 0.5

        se_auto_f = _se(arms["auto"].get("ms") or [])
        se_fix_f = _se(arms[best_arm].get("ms") or [])
        se_reg_f = None
        if se_auto_f is not None and se_fix_f is not None:
            se_reg_f = (se_auto_f ** 2 + se_fix_f ** 2) ** 0.5
        if best_hold is not None:
            _se_h = _se(hold_values_by[best_hold])
            if se_auto is not None and _se_h is not None:
                se_hold = (se_auto ** 2 + _se_h ** 2) ** 0.5
        _methods = sorted(set(m for m, _k in _se_methods if m))
        half_late = BST.batch_diff_half(arms["auto"].get("ms_late") or [],
                                        arms[best_late].get("ms_late") or [])
        half_full = BST.batch_diff_half(arms["auto"].get("ms") or [],
                                        arms[best_arm].get("ms") or [])
        half_hold = None
        if best_hold is not None:
            hold_values = hold_values_by[best_hold]
            half_hold = BST.batch_diff_half(arms["auto"].get("ms_late") or [],
                                            hold_values)

        out["regret"].append({
            "cond": name, "cert": cert, "loss": loss,
            "matched_block_diagnostic": matched,
            "holdout_scope": "internal chronological split; not independent confirmation",
            "best_fixed": best_arm, "best_fixed_mean": fixed[best_arm],
            "auto_mean": arms["auto"]["mean"], "regret_ms": reg,
            "best_fixed_late": best_late,
            "auto_mean_late": arms["auto"]["mean_late"],
            "regret_late_ms": reg_late,
            "regret_holdout_ms": reg_hold,
            "probe_rounds_late": n_probe_late,
            "probe_tax_ms": probe_tax,
            "regret_late_sel_ms": reg_sel,
            "best_fixed_holdout": best_hold,
            "se_regret_ms": se_reg,
            "ci95_half_ms": half_late,
            "ci95_half_full_ms": half_full,
            "ci95_half_holdout_ms": half_hold,
            "ci_method": "Welch-t on batch means (iid fallback for short samples)",
            "se_method": ("batch" if _methods == ["batch"]
                          else "+".join(_methods) or None),
            "se_batches_min": min((k for _m, k in _se_methods if k),
                                  default=None),
            "fixed_means": fixed,
            "fixed_means_late": fixed_late})
        print("    -> 최선 고정팔 %s (%.2f ms), auto %.2f ms, "
              "후회 %+.2f ms (수렴후 %+.2f ms, 홀드아웃 %s, ±%s ms)"
              % (best_arm, fixed[best_arm], arms["auto"]["mean"], reg,
                 reg_late,
                 ("%+.2f" % reg_hold) if reg_hold is not None else "-",
                 ("%.2f" % half_late) if half_late is not None else "-"))
        if probe_tax is not None:
            print("       내역: 선택 오류분 %+.2f ms + 탐색세 %+.2f ms "
                  "(수렴후 탐색 %d 라운드)"
                  % (reg_sel, probe_tax, n_probe_late))
        sys.stdout.flush()

    _taxes = [r["probe_tax_ms"] for r in out["regret"]
              if r.get("probe_tax_ms") is not None]
    out["worst_probe_tax_ms"] = max(_taxes) if _taxes else None

    print()
    print("=" * 104)
    add("6 조건이 전부 측정됐다 (빠진 조건이 헤드라인을 좋게 만들 수 없다)",
        len(out["regret"]) == len(CONDS),
        "%d/%d 조건 | 빠짐 %s"
        % (len(out["regret"]), len(CONDS),
           [d["cond"] for d in out.get("dropped", [])] or "없음"))
    add("모든 팔 행에 공유한 조건 서버 통계가 있었다 (연결 대응 검사가 아님)",
        all(r.get("srv_stats_present") for r in out["rows"]) and out["rows"],
        "%d/%d 행, 조건 합계를 각 팔에 공유"
        % (sum(1 for r in out["rows"] if r.get("srv_stats_present")),
           len(out["rows"])))

    regs = [r["regret_ms"] for r in out["regret"]]
    regs_late = [r["regret_late_ms"] for r in out["regret"]]
    regs_hold = [r["regret_holdout_ms"] for r in out["regret"]
                 if r["regret_holdout_ms"] is not None]
    cis = [r["ci95_half_ms"] for r in out["regret"]
           if r["ci95_half_ms"] is not None]
    worst = max(regs) if regs else None
    worst_late = max(regs_late) if regs_late else None
    worst_hold = max(regs_hold) if regs_hold else None
    out["worst_regret_ms"] = worst
    out["worst_regret_late_ms"] = worst_late
    out["worst_regret_holdout_ms"] = worst_hold
    out["worst_ci95_half_ms"] = max(cis) if cis else None

    def _ci_at(field, value, key):
        if value is None:
            return None
        for _r in out["regret"]:
            if _r.get(field) == value:
                return _r.get(key)
        return None

    out["worst_regret_ci95_half_ms"] = _ci_at(
        "regret_ms", worst, "ci95_half_full_ms")
    out["worst_regret_late_ci95_half_ms"] = _ci_at(
        "regret_late_ms", worst_late, "ci95_half_ms")
    add("최악 후회가 5 ms 미만 (전 구간, 콜드스타트 포함)",
        worst is not None and worst < 5.0,
        "최악 %s ms | 조건별 %s"
        % (("%+.2f" % worst) if worst is not None else "데이터 없음",
           ["%+.1f" % v for v in regs]))
    def _verdict(est, half, ruler=2.0):
        if est is None:
            return "데이터없음"
        if half is None:
            return "맞음" if est < ruler else "틀림"
        if est + half <= ruler:
            return "맞음"
        if est - half > ruler:
            return "틀림"
        return "판정불능"

    def _need_n(half, ruler, est, n_now):
        if half is None or est is None or n_now is None:
            return None
        want = abs(ruler - est)
        if want < 1e-9:
            return None
        return int(math.ceil(n_now * (half / want) ** 2))

    _h_late = out.get("worst_regret_late_ci95_half_ms")
    _v_late = _verdict(worst_late, _h_late)
    add("최악 후회가 2 ms 밖이라고 **말할 수 있는** 조건이 없다 (수렴 후)",
        _v_late in ("맞음", "판정불능"),
        "최악 %s ms ±%s -> %s%s | 조건별 %s"
        % (("%+.2f" % worst_late) if worst_late is not None else "데이터 없음",
           ("%.2f" % _h_late) if _h_late is not None else "?", _v_late,
           ("  필요 n=%s (지금 %d)"
            % (_need_n(_h_late, 2.0, worst_late, N), N))
           if _v_late == "판정불능" else "",
           ["%+.1f" % v for v in regs_late]))
    _h_hold = _ci_at("regret_holdout_ms", worst_hold, "ci95_half_holdout_ms")
    _v_hold = _verdict(worst_hold, _h_hold)
    add("최악 후회가 2 ms 밖이라고 **말할 수 있는** 조건이 없다 "
        "(수렴 후 · 내부 시간분할 비교)",
        _v_hold in ("맞음", "판정불능"),
        "최악 %s ms ±%s -> %s | 조건별 %s"
        % (("%+.2f" % worst_hold) if worst_hold is not None else "데이터 없음",
           ("%.2f" % _h_hold) if _h_hold is not None else "?", _v_hold,
           ["%+.1f" % v for v in regs_hold]))
    add("후회 추정의 95% 신뢰반폭이 1 ms 미만 (기준 2 ms 를 판정할 정밀도)",
        len(cis) == len(CONDS) and max(cis) < 1.0,
        "최대 반폭 %s ms | 조건별 %s"
        % (("%.2f" % max(cis)) if cis else "-",
           ["%.2f" % v for v in cis]))

    agree = 0
    tot = 0
    detail = []
    for r in out["regret"]:
        row = next((x for x in out["rows"]
                    if x["arm"] == "auto" and x["cert"] == r["cert"]
                    and x["loss"] == r["loss"]), None)
        if not row:
            continue
        late = [row["m_used"][i] for i in row["late_trial_indices"]]
        if not late:
            continue
        from collections import Counter
        mode_m = Counter(late).most_common(1)[0][0]
        want = int(r["best_fixed_late"][1:])
        fm = r["fixed_means_late"]
        best_val = min(fm.values())
        tie = sorted(a for a, v in fm.items() if (v - best_val) < 1.0)
        if len(tie) == len(fm):
            detail.append("%s: 전 팔이 최선과 1 ms 안 -> 판정 제외"
                          % r["cond"])
            continue
        tot += 1
        picked_ok = isinstance(mode_m, int) and ("m%d" % mode_m) in tie
        if picked_ok:
            agree += 1
        detail.append("%s: auto m=%s / 최선 m=%d / 허용 %s%s"
                      % (r["cond"], mode_m, want, tie,
                         "" if picked_ok else " <-- 불일치"))
    if tot:
        add("수렴 후 auto 가 최선과 잡음 안에서 같은 m 을 골랐다",
            agree == tot, "%d/%d | %s" % (agree, tot, "; ".join(detail)))
        out["agreement"] = [agree, tot]
        add("판별력 있는 조건이 절반 이상 (없으면 위 검사가 공허하다)",
            tot * 2 >= len(out["regret"]) and tot > 0,
            "%d/%d 조건에서 팔 선택이 실제로 손익을 가른다"
            % (tot, len(out["regret"])))

    _seen = set()
    crc = 0
    for r in out["rows"]:
        k_ = (r["cert"], r["loss"])
        if k_ in _seen:
            continue
        _seen.add(k_)
        crc += r["srv_crc_fail"] or 0
    add("모든 팔에서 복구 CRC 실패 0", crc == 0, "총 %d 건 (조건별 합)" % crc)
    _bad_se = [r["cond"] for r in out["regret"] if r.get("se_method") != "batch"]
    add("모든 조건의 반폭이 배치평균으로 나왔다 (배치 간 독립성은 근사)",
        out["regret"] and not _bad_se,
        "iid 로 되돌아간 조건: %s" % (_bad_se or "없음"))

    out["journal_provenance"] = jr.provenance()
    npass = sum(1 for c in out["checks"] if c["ok"])
    print("-" * 104)
    print("%d / %d 통과" % (npass, len(out["checks"])))
    out["passed"] = npass
    out["total"] = len(out["checks"])
    _fname = ("smoke_" if N < N_DEFAULT else "") + "p11_adaptive.json"
    print("saved:", B.save(_fname, out))
    return 0 if npass == len(out["checks"]) else 1


if __name__ == "__main__":
    sys.exit(main())
