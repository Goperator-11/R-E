from __future__ import annotations

import math
import os
import sys
import datetime as dt
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B
from padfec import policy as POL

RTT_MS = 50.0
N_BEFF = 24
N_SWEEP = 12

N_LATE = 600
LATE_CRED_MIN = 0.99
P_SRV = 1280

FLIGHT_WINDOW_NS = 20_000_000

GROUPS = [("x25519", 1), ("X25519MLKEM768", 2)]
ARMS = [("off", "off", 0), ("on1", "on", 1), ("on2", "on", 2)]

CERT_NEAR = {
    ("x25519", "off"): 3340, ("x25519", "on1"): 8267, ("x25519", "on2"): 12005,
    ("X25519MLKEM768", "off"): 5945,
    ("X25519MLKEM768", "on1"): 10929, ("X25519MLKEM768", "on2"): 14611,
}

BIN_OF = {("x25519", "off"): 3, ("x25519", "on1"): 7, ("x25519", "on2"): 10,
          ("X25519MLKEM768", "off"): 6, ("X25519MLKEM768", "on1"): 10,
          ("X25519MLKEM768", "on2"): 13}


def req_interval(bin_n):
    return ((bin_n - 1) * P_SRV / 3.0, bin_n * P_SRV / 3.0)


SWEEP = [
    ("x25519", "off", "off", 0, [1000, 2000, 3000]),
    ("x25519", "on1", "on", 1, [4000, 5000, 6000, 7000, 8000]),
    ("x25519", "on2", "on", 2, [9000, 10500, 11500]),
    ("X25519MLKEM768", "off", "off", 0, [1000, 2500, 4000, 5500]),
    ("X25519MLKEM768", "on1", "on", 1, [6500, 8000, 9500, 10500]),
    ("X25519MLKEM768", "on2", "on", 2, [11500, 13000, 14000]),
]


def median(vals):
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def cp_lower(x, n, alpha=0.05):
    if not n or x is None:
        return None
    if x <= 0:
        return 0.0
    if x >= n:
        return alpha ** (1.0 / n)
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        s = 0.0
        for i in range(x, n + 1):
            s += math.exp(math.lgamma(n + 1) - math.lgamma(i + 1)
                          - math.lgamma(n - i + 1)
                          + i * math.log(mid)
                          + (n - i) * math.log1p(-mid))
        if s > alpha:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def late_parity_assessment(n_req, n_ok, n_conns, credited, err=""):
    counts_valid = (
        all(type(n) is int for n in (n_req, n_ok, n_conns, credited))
        and n_req > 0 and 0 <= n_ok <= n_req
        and 0 <= credited <= n_conns <= n_req)
    complete = (counts_valid and not err
                and n_ok == n_req and n_conns == n_req)
    frac = credited / float(n_conns) if counts_valid and n_conns else None
    observed_lo = cp_lower(credited, n_conns) if counts_valid else None
    lo = observed_lo if complete else None
    verdict = "inconclusive"
    if complete:
        if lo is not None and lo >= LATE_CRED_MIN:
            verdict = "refuted"
        elif frac is not None and frac <= 0.1:
            verdict = "confirmed"
    return {
        "frac": frac,
        "frac_scope": "observed_server_records",
        "observed_cred_ci95_lo": observed_lo,
        "cred_ci95_lo": lo,
        "coverage_complete": bool(complete),
        "server_coverage_frac": n_conns / float(n_req) if counts_valid else None,
        "n_missing_server": n_req - n_conns if counts_valid else None,
        "coverage_reason": (
            "요청·성공·서버 기록 수 일치" if complete else
            "요청 %s, 성공 %s, 서버 기록 %s, 오류 %s. 전체 시행의 신용률 판정 불가"
            % (n_req, n_ok, n_conns, err or "없음")),
        "verdict": verdict,
    }


def collection_evidence(rows, cs, ss, err, n_req):
    n_ok = sum(1 for row in rows if row.get("ok"))
    return {"n_req": n_req, "n_rows": len(rows), "n_ok": n_ok,
            "n_failed": len(rows) - n_ok, "n_missing": max(0, n_req - len(rows)),
            "client_rows": rows, "client_stats": cs, "server_stats": ss,
            "client_coverage_complete": len(rows) == n_req and n_ok == n_req and not err,
            "recording_scope": "returned client JSON rows and available server statistics; counts do not establish connection matching"}


def run_cond(group, k, fec, m, cert, n):
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    collection_id = uuid.uuid4().hex
    srv_mode = "on" if fec == "on" else "off"
    p, sp = B.start_server(cert, fec=srv_mode)
    rows, cs, err = B.run_client(group, n, fec=fec, m=max(m, 1), gap_ms=15,
                                 timeout_s=12, expect_k=k)
    B.stop_server(p)
    ss = B.read_server_stats(sp)
    cs["collection_provenance"] = {
        "collection_id": collection_id, "started_at": started,
        "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "group": group, "expected_k_flush_hint": k, "fec": fec, "m": m,
        "cert": cert, "n_req": n, "requested_rtt_ms": RTT_MS,
        "time_scope": "collection interval, not individual connection timestamps"}
    return rows, cs, ss, err


def conn_list(ss):
    conns = list((ss.get("conns") or {}).values())
    conns.sort(key=lambda c: c.get("first_rx_ns") or 0)
    return conns


def flight_of(conn):
    ts = conn.get("tx_ns") or []
    sz = conn.get("tx_sizes") or []
    if not ts or len(ts) != len(sz):
        return 0, 0, False, "타임라인 없음/길이 불일치"
    nfl = 0
    for i, t in enumerate(ts):
        if t - ts[0] < FLIGHT_WINDOW_NS:
            nfl = i + 1
        else:
            break
    has_tail = nfl < len(ts)
    timeline_full = conn.get("tx_dgrams") == len(ts)
    if has_tail:
        return nfl, sum(sz[:nfl]), True, "꼬리로 절단"
    if timeline_full:
        return nfl, sum(sz[:nfl]), True, "꼬리없음·타임라인 완전"
    return nfl, sum(sz[:nfl]), False, "타임라인 넘침"


def main():
    B.harden()
    B.require_root()
    B.require_bin()
    B.setup(mtu=1500)
    B.set_netem(RTT_MS / 2.0, 0.0, 0.0)

    out = {"rtt_ms": RTT_MS, "n_beff": N_BEFF, "n_sweep": N_SWEEP,
           "beff": [], "sweep": [], "fits": {}, "checks": []}

    def add(name, ok, detail):
        out["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
        print("[%s] %-58s %s" % ("통과" if ok else "실패", name, detail[:90]),
              flush=True)

    print("=" * 100)
    print("1) B_eff - 서버 첫 송신 직전의 수신 누적 (스택 기준, 원본/패리티 분리)")
    print("=" * 100)
    print("%-16s %-4s %-6s %-9s %-9s %-9s %-9s %-11s %s"
          % ("그룹", "팔", "cert", "B_eff", "원본몫", "패리티몫", "클라FF",
             "FF패리티", "판정구간"))

    for group, k in GROUPS:
        for arm, fec, m in ARMS:
            certs = sorted({3000, CERT_NEAR[(group, arm)]})
            for cert in certs:
                rows, cs, ss, err = run_cond(group, k, fec, m, cert, N_BEFF)
                conns = conn_list(ss)
                _rxd = sorted(c.get("rx_dgrams") or 0 for c in conns)
                _rxmed = _rxd[len(_rxd) // 2] if _rxd else 0
                merged_n = sum(1 for c in conns
                               if _rxmed and (c.get("rx_dgrams") or 0)
                               >= 1.5 * _rxmed)
                beff = [c["beff_stack"] for c in conns]
                borg = [c["beff_orig_bytes"]
                        if "beff_orig_bytes" in c else c.get("beff_orig", 0)
                        for c in conns]
                bpar = [c.get("beff_parity", 0) for c in conns]
                ffb = [r.get("first_flight_bytes") or 0 for r in rows]
                ffp = [r.get("first_flight_parity_bytes") or 0 for r in rows]
                lo, hi = req_interval(BIN_OF[(group, arm)])
                rec = {**collection_evidence(rows, cs, ss, err, N_BEFF),
                       "group": group, "arm": arm, "m": m, "cert": cert,
                       "n_conns": len(conns), "n_rows": len(rows),
                       "merged_suspect": merged_n,
                       "err": err,
                       "beff_med": median(beff),
                       "beff_min": min(beff) if beff else None,
                       "beff_max": max(beff) if beff else None,
                       "beff_orig_med": median(borg),
                       "beff_parity_med": median(bpar),
                       "client_ff_bytes_med": median(ffb),
                       "client_ff_parity_med": median(ffp),
                       "req_lo": lo, "req_hi": hi,
                       "parity_credited_frac": (
                           sum(1 for v in bpar if v > 0) / float(len(bpar))
                           if bpar and m > 0 else None),
                       "beff_parity_all": sorted(bpar),
                       "client_ff_parity_all": sorted(ffp),
                       "parity_jitter_b": ((max(ffp) - min(ffp))
                                           if ffp and m > 0 else 0)}
                out["beff"].append(rec)
                print("%-16s %-4s %-6d %-9s %-9s %-9s %-9s %-11s (%.0f, %.1f]"
                      % (group, arm, cert, rec["beff_med"],
                         rec["beff_orig_med"], rec["beff_parity_med"],
                         rec["client_ff_bytes_med"],
                         rec["client_ff_parity_med"], lo, hi), flush=True)

    def pick(group, arm, cert=None):
        cand = [r for r in out["beff"]
                if r["group"] == group and r["arm"] == arm
                and (cert is None or r["cert"] == cert)]
        return cand[-1] if cand else None

    neg_bad = []
    for group, k in GROUPS:
        for r in [x for x in out["beff"] if x["group"] == group
                  and x["arm"] == "off"]:
            if r["beff_parity_med"] != 0 or r["beff_med"] != k * 1280:
                neg_bad.append((group, r["cert"], r["beff_med"],
                                r["beff_parity_med"]))
    add("1. 음성 대조: off 팔 B_eff == k*1280, 패리티 몫 0", not neg_bad,
        str(neg_bad[:3]) if neg_bad else "4/4 조건 정확히 k*1280")

    r = pick("x25519", "on1", CERT_NEAR[("x25519", "on1")])
    ok2 = r and r["beff_med"] is not None and 2560 < r["beff_med"] <= 8960 / 3.0
    add("2. [loop2 기준] x25519 on1 B_eff ∈ (2560, 2986.7]", ok2,
        "B_eff 중앙값 %s" % (r and r["beff_med"]))

    miss = []
    for group, k in GROUPS:
        for arm in ("on1", "on2"):
            rr = pick(group, arm, CERT_NEAR[(group, arm)])
            if not rr or rr["beff_med"] is None or not (
                    rr["req_lo"] < rr["beff_med"] <= rr["req_hi"]):
                miss.append((group, arm, rr and rr["beff_med"]))
    add("3. FEC 4팔 전부 B_eff 가 해당 칸 구간 안", not miss,
        str(miss) if miss else "on1/on2 x 두 그룹 전부 적중")

    par_bad, cred_bad = [], []
    for group, k in GROUPS:
        for arm in ("on1", "on2"):
            for rr in [x for x in out["beff"] if x["group"] == group
                       and x["arm"] == arm]:
                n_c = rr["n_conns"] or 0
                frac = rr.get("parity_credited_frac")
                if frac is not None and n_c:
                    if frac < 0.95:
                        cred_bad.append((group, arm, rr["cert"],
                                         round(frac, 4),
                                         round(cp_lower(int(round(frac * n_c)),
                                                        n_c) or 0, 4), n_c))
                tol = max(0, rr.get("parity_jitter_b") or 0)
                d = abs((rr["beff_parity_med"] or 0)
                        - (rr["client_ff_parity_med"] or 0))
                if d > tol:
                    par_bad.append((group, arm, rr["cert"],
                                    rr["beff_parity_med"],
                                    rr["client_ff_parity_med"], tol))
    _n_for_95 = int(math.ceil(math.log(0.05) / math.log(0.95)))
    add("4a. 패리티가 서버 결정 전에 도착해 신용된다 (점추정 >= 0.95; "
        "하한 인증은 검사 5)",
        not cred_bad, str(cred_bad[:3]) if cred_bad
        else " | ".join("%s/%s c%d %.3f (하한 %.3f, n=%d)"
                        % (r["group"][:6], r["arm"], r["cert"],
                           r["parity_credited_frac"],
                           cp_lower(int(round((r["parity_credited_frac"] or 0)
                                               * (r["n_conns"] or 0))),
                                     r["n_conns"] or 1),
                           r["n_conns"])
                        for r in out["beff"]
                        if r.get("parity_credited_frac") is not None)
             + " | 하한 0.95 인증에는 조건당 n>=%d 필요 (지금 %d)"
               % (_n_for_95, N_BEFF))
    add("4b. 서버 패리티 몫 == 클라 패리티 (CID 흔들림 폭 안)",
        not par_bad, str(par_bad[:3]) if par_bad
        else "전 조건에서 흔들림 폭 안 (폭 %s B)"
             % sorted({r.get("parity_jitter_b") for r in out["beff"]
                       if r.get("parity_jitter_b") is not None}))

    _lcert = CERT_NEAR[("x25519", "on1")]
    print()
    print("5) late-parity 전용 측정: x25519 k=1 m=1 cert=%d, %d 연결"
          % (_lcert, N_LATE), flush=True)
    _lrows, _lcs, _lss, _lerr = run_cond("x25519", 1, "on", 1,
                                        _lcert, N_LATE)
    _lconns = conn_list(_lss)
    _lpar = [c.get("beff_parity", 0) for c in _lconns]
    _lcred = sum(1 for v in _lpar if v > 0)
    _lsum = B.summarize(_lrows, rtt_ms=RTT_MS)
    _late = late_parity_assessment(N_LATE, _lsum.get("ok"),
                                   len(_lconns), _lcred, _lerr)
    _llo = _late["cred_ci95_lo"]
    out["late_parity"] = {
        "cert": _lcert, "n_req": N_LATE, "n_conns": len(_lconns),
        "credited": _lcred, "err": _lerr,
        "two_rtt_rate": _lsum.get("two_rtt_rate"),
        "p50": _lsum.get("p50"),
        **collection_evidence(_lrows, _lcs, _lss, _lerr, N_LATE),
        **_late,
    }
    print("   관측 기록 신용 %d/%d (전체 시행 하한 %s) | 2-RTT %s"
          % (_lcred, len(_lconns),
             "-" if _llo is None else "%.4f" % _llo,
             out["late_parity"]["two_rtt_rate"]), flush=True)
    out["late_parity_verdict"] = _late["verdict"]
    add("5a. late-parity: 요청 시행의 성공·서버 기록이 빠짐없이 있다",
        _late["coverage_complete"],
        "%s | 서버 기록 누락 %s"
        % (_late["coverage_reason"], _late["n_missing_server"]))
    add("5. late-parity: 완전한 시행 표본으로 가설을 판정했다",
        out["late_parity_verdict"] != "inconclusive",
        "관측 신용 %d/%d, 전체 시행 95%% 하한 %s -> %s"
        " (refuted 기준 %.2f; 관측 기록만의 하한 %s)"
        % (_lcred, len(_lconns),
           "-" if _llo is None else "%.4f" % _llo,
           out["late_parity_verdict"], LATE_CRED_MIN,
           "-" if _late["observed_cred_ci95_lo"] is None
           else "%.4f" % _late["observed_cred_ci95_lo"]))

    ack_bad = []
    for rr in out["beff"]:
        full = (rr["client_ff_bytes_med"] or 0) + (rr["client_ff_parity_med"]
                                                   or 0)
        if rr["beff_med"] is not None and rr["beff_med"] > full:
            ack_bad.append((rr["group"], rr["arm"], rr["cert"],
                            rr["beff_med"], full))
    add("6. B_eff <= 첫 비행(원본+패리티) - 뒤 비행 몫이 안 섞임", not ack_bad,
        str(ack_bad[:3]) if ack_bad else "전 조건에서 상한 준수")

    inc = [(r_["group"], r_["arm"], r_["cert"], r_["n_conns"], r_["n_rows"])
           for r_ in out["beff"] if r_["n_conns"] != r_["n_rows"]]
    _bad7 = [x for x in inc if x[4] - x[3] >= 2]
    _miss = sum(x[4] - x[3] for x in inc)
    _exp = sum(r_["n_rows"] * (r_["n_rows"] - 1) / 2.0 / 28232.0
               for r_ in out["beff"])
    add("7. 연결별 회계 완전성 (포트 생일충돌 기대 이내, 조건별 <= 1)",
        (not _bad7) and _miss <= max(1, 3.0 * _exp),
        "누락 합 %d (생일 기대 %.2f) | 조건별 2+ 누락 %s | 상세 %s"
        % (_miss, _exp, _bad7 or "없음", inc[:3] or "완전"))

    print()
    print("=" * 100)
    print("2) c (서버 패킷 오버헤드) - 첫 비행 데이터그램을 직접 세서 s0(n) 회귀")
    print("=" * 100)
    print("%-16s %-4s %-6s %-7s %-9s %-9s %-6s" % (
        "그룹", "팔", "cert", "n비행", "비행바이트", "s0직접", "유효"))

    for group, arm, fec, m, certs in SWEEP:
        k = 2 if group == "X25519MLKEM768" else 1
        for cert in certs:
            rows, cs, ss, err = run_cond(group, k, fec, m, cert, N_SWEEP)
            conns = conn_list(ss)
            nfl, sfl, s0d = [], [], []
            valid = 0
            why_n = {}
            for c in conns:
                n_, s_, ok_, why_ = flight_of(c)
                why_n[why_] = why_n.get(why_, 0) + 1
                if not ok_:
                    continue
                valid += 1
                nfl.append(n_)
                sfl.append(s_)
                s0d.append(s_ - cert)
            two = B.summarize(rows, rtt_ms=RTT_MS).get("two_rtt_rate")
            srvb = [r.get("server_bytes") or 0 for r in rows
                    if r.get("ok")]
            rec = {**collection_evidence(rows, cs, ss, err, N_SWEEP),
                   "group": group, "arm": arm, "cert": cert, "err": err,
                   "n_conns": len(conns), "n_valid": valid,
                   "two_rtt_rate": two,
                   "n_flight_med": median(nfl), "flight_bytes_med": median(sfl),
                   "s0_direct_med": median(s0d),
                   "s0_spread": (max(s0d) - min(s0d)) if s0d else None,
                   "flight_why": why_n,
                   "srv_rx_med": median(srvb),
                   "srv_rx_minus_flight": (
                       (median(srvb) - median(sfl))
                       if srvb and sfl else None),
                   "usable": bool(s0d) and valid >= N_SWEEP // 2
                             and (two is not None and two < 0.1)}
            out["sweep"].append(rec)
            print("%-16s %-4s %-6d %-7s %-9s %-9s %-6s"
                  % (group, arm, cert, rec["n_flight_med"],
                     rec["flight_bytes_med"], rec["s0_direct_med"],
                     "예" if rec["usable"] else "아니오"), flush=True)

    for group, _k in GROUPS:
        pts = [(r_["n_flight_med"], r_["s0_direct_med"])
               for r_ in out["sweep"] if r_["group"] == group and r_["usable"]]
        by_n = {}
        for n_, s_ in pts:
            by_n.setdefault(n_, []).append(s_)
        xy = sorted((n_, sum(v) / len(v)) for n_, v in by_n.items())
        fit = {"points": xy, "by_n": {str(k_): v for k_, v in by_n.items()}}
        if len(xy) >= 2:
            n_ = len(xy)
            mx = sum(x for x, _ in xy) / n_
            my = sum(y for _, y in xy) / n_
            den = sum((x - mx) ** 2 for x, _ in xy)
            c_hat = sum((x - mx) * (y - my) for x, y in xy) / den
            b_hat = my - c_hat * mx
            fit["c"] = c_hat
            fit["s0_base"] = b_hat
            fit["mae"] = sum(abs(y - (b_hat + c_hat * x)) for x, y in xy) / n_
        out["fits"][group] = fit
        if "c" in fit:
            print("  %-16s c = %.2f B/패킷, s0_base = %.1f, 적합 MAE %.1f B, "
                  "n 격자 %s" % (group, fit["c"], fit["s0_base"], fit["mae"],
                                 [x for x, _ in xy]), flush=True)

    mono_bad = []
    for group, _k in GROUPS:
        xy = out["fits"][group].get("points", [])
        for i in range(1, len(xy)):
            if xy[i][1] < xy[i - 1][1] - 1.0:
                mono_bad.append((group, xy[i - 1], xy[i]))
    add("8. s0 가 첫 비행 데이터그램 수에 대해 단조 증가", not mono_bad,
        str(mono_bad[:3]) if mono_bad else "두 그룹 전부 단조")

    mae_bad = []
    for group, _k in GROUPS:
        mae = out["fits"][group].get("mae")
        if mae is None or mae > 15.0:
            mae_bad.append((group, mae))
    add("9. s0(n) 회귀 MAE <= 15 B (임계 예측 용도의 적합도)", not mae_bad,
        str(mae_bad) if mae_bad else
        "x25519 %.1f / MLKEM %.1f B (같은 n 안 실폭은 fits.by_n 에 기록)"
        % (out["fits"][GROUPS[0][0]].get("mae", -1),
           out["fits"][GROUPS[1][0]].get("mae", -1)))

    cs_ = [out["fits"][g].get("c") for g, _ in GROUPS]
    ok10 = all(c_ is not None and c_ > 5.0 for c_ in cs_)
    add("10. c > 5 B/패킷 (상수 s0 모형 기각)", ok10,
        "x25519 %.2f / MLKEM %.2f" % tuple(c_ if c_ is not None else -1
                                           for c_ in cs_))

    _gaps = [(r_["group"], r_["arm"], r_["cert"],
              r_["srv_rx_minus_flight"]) for r_ in out["sweep"]
             if r_.get("usable") and r_.get("srv_rx_minus_flight") is not None]
    _bad13 = [g for g in _gaps if abs(g[3]) >= P_SRV]
    add("13. 폐루프 입력(server_bytes)이 첫 비행과 한 칸(1280 B) 안",
        (not _bad13) and bool(_gaps),
        (str(_bad13[:3]) if _bad13 else
         "%d 조건, 차이 %+d ~ %+d B (중앙 %+d)"
         % (len(_gaps), min(g[3] for g in _gaps),
            max(g[3] for g in _gaps),
            sorted(g[3] for g in _gaps)[len(_gaps) // 2]))
        if _gaps else "측정된 조건이 없다")

    noconn = [(r_["group"], r_["arm"], r_["cert"], r_["err"])
              for r_ in out["sweep"] if not r_["n_conns"]]
    add("11. 스윕 전 조건에서 연결이 실제로 생겼다", not noconn,
        str(noconn[:3]) if noconn else
        "%d 조건 전부 n_conns > 0" % len(out["sweep"]))

    thin = [(g_, len(out["fits"][g_].get("points", [])))
            for g_, _k in GROUPS
            if len(out["fits"][g_].get("points", [])) < 3]
    add("12. 두 그룹 모두 n 격자 3 점 이상에서 회귀했다", not thin,
        str(thin) if thin else "x25519 %d 점 / MLKEM %d 점"
        % (len(out["fits"][GROUPS[0][0]].get("points", [])),
           len(out["fits"][GROUPS[1][0]].get("points", []))))

    out["c_policy_default"] = POL.C_PKT_POLICY_DEFAULT

    npass = sum(1 for c in out["checks"] if c["ok"])
    out["passed"] = npass
    out["total"] = len(out["checks"])
    print()
    print("-" * 100)
    print("%d / %d 통과" % (npass, len(out["checks"])))
    print("late-parity 판정: %s" % out["late_parity_verdict"])
    print("saved:", B.save("p13_beff.json", out))
    return 0 if npass == len(out["checks"]) else 1


if __name__ == "__main__":
    sys.exit(main())
