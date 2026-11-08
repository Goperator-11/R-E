from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B
from padfec import amplif
from _journal import Journal, code_fingerprint

RTT_MS = 50.0
N_PROBE = 15
N_CONFIRM = 40
RESOLUTION = 100
LO, HI = 1500, 16000

ARMS = [("off", "off", 1), ("buf", "buf", 1), ("on1", "on", 1),
        ("on2", "on", 2)]
GROUPS = [("x25519", 1), ("X25519MLKEM768", 2)]

TEAM = {"x25519": (3300, 3400), "X25519MLKEM768": (5900, 6000)}


def probe(group, arm_fec, m, cert, k, n, jr):
    key = "%s|%s|m%d|c%d|n%d" % (group, arm_fec, m, cert, n)
    if jr.has(key):
        return jr.get(key)
    p, sp = B.start_server(cert, fec=("on" if arm_fec == "on" else arm_fec))
    rows, cs, err = B.run_client(group, n, fec=arm_fec, m=m, gap_ms=15,
                                 expect_k=k)
    B.stop_server(p)
    ss = B.read_server_stats(sp)
    s = B.summarize(rows, rtt_ms=RTT_MS)
    ffp = sorted(r.get("first_flight_parity_bytes") or 0 for r in rows)
    rec = {"cert": cert, "n": s["n"], "ok": s["ok"], "p50": s["p50"],
           "two_rtt_rate": s["two_rtt_rate"],
           "first_flight_bytes": cs.get("first_flight_bytes"),
           "ff_parity_bytes_med": (ffp[len(ffp) // 2] if ffp else 0),
           "parity_bytes_per_conn": (
               round((cs.get("bytes_parity") or 0) / float(max(1, s["n"])), 1)),
           "srv_bytes_in": ss.get("bytes_in"),
           "srv_bytes_to_stack": ss.get("bytes_to_stack"),
           "error": err,
           "valid": not err and n > 0 and s["ok"] == s["n"] == n}
    if rec["valid"]:
        jr.record(key, rec)
    return rec


def is_two_rtt(rec):
    if (not rec.get("ok") or rec.get("ok") != rec.get("n")
            or rec.get("valid") is False or rec.get("error")):
        return None
    r = rec.get("two_rtt_rate")
    return None if r is None else r >= 0.5


def bisect_threshold(group, arm_fec, m, k, jr, log):
    lo, hi = LO, HI
    r_lo = probe(group, arm_fec, m, lo, k, N_PROBE, jr)
    r_hi = probe(group, arm_fec, m, hi, k, N_PROBE, jr)
    log("  경계 확인: cert %d -> ok %d/%d 2RTT %.0f%% / cert %d -> ok %d/%d "
        "2RTT %.0f%%"
        % (lo, r_lo["ok"], r_lo["n"], 100 * (r_lo["two_rtt_rate"] or 0),
           hi, r_hi["ok"], r_hi["n"], 100 * (r_hi["two_rtt_rate"] or 0)))
    a, b = is_two_rtt(r_lo), is_two_rtt(r_hi)
    if a is None or b is None:
        return {"lo": None, "hi": None,
                "note": "경계에서 핸드셰이크 실패 - 판정 불가"}
    if a:
        return {"lo": None, "hi": lo, "note": "하한에서 이미 2-RTT"}
    if not b:
        return {"lo": hi, "hi": None, "note": "상한(%d B)에서도 1-RTT" % hi}
    while hi - lo > RESOLUTION:
        mid = (lo + hi) // 2
        r = probe(group, arm_fec, m, mid, k, N_PROBE, jr)
        if is_two_rtt(r) is None:
            return {"lo": None, "hi": None,
                    "note": "cert %d 에서 핸드셰이크 실패 - 판정 불가" % mid}
        rate = r["two_rtt_rate"] or 0.0
        if 0.2 < rate < 0.8:
            r = probe(group, arm_fec, m, mid, k, N_CONFIRM, jr)
            if is_two_rtt(r) is None:
                return {"lo": None, "hi": None,
                        "note": "cert %d 재확인 실패 - 판정 불가" % mid}
            rate = r["two_rtt_rate"] or 0.0
        if rate >= 0.5:
            hi = mid
        else:
            lo = mid
        log("    cert %-6d 2RTT %5.0f%%  ->  구간 [%d, %d]"
            % (mid, 100 * rate, lo, hi))
    return {"lo": lo, "hi": hi, "note": ""}


def main():
    B.harden()
    B.require_root()
    B.require_bin()
    B.setup()
    B.set_netem(RTT_MS / 2.0)

    fp = code_fingerprint(["experiments/p2_threshold.py",
                           "experiments/quicbed/qamp.go",
                           "experiments/padbed.py"], ROOT)
    jr = Journal(os.path.join(B.STATE, "p2_units.jsonl"), fp)

    def log(msg):
        print(msg)
        sys.stdout.flush()

    out = {"rtt_ms": RTT_MS, "resolution": RESOLUTION, "thresholds": [],
           "ips_sweep": [], "exchange": {}, "team": TEAM}

    for group, k in GROUPS:
        for arm, fec, m in ARMS:
            log("")
            log("[%s / %s] 임계 이분탐색" % (group, arm))
            th = bisect_threshold(group, fec, m, k, jr, log)
            ref = probe(group, fec, m, 3000, k, N_PROBE, jr)
            client_bytes = (ref["first_flight_bytes"] or 0) + (
                ref.get("ff_parity_bytes_med", 0) if fec == "on" else 0)
            legacy = (ref["first_flight_bytes"] or 0) + (
                ref["parity_bytes_per_conn"] if fec == "on" else 0)
            rec = {"group": group, "arm": arm, "m": m,
                   "threshold_lo": th["lo"], "threshold_hi": th["hi"],
                   "note": th["note"],
                   "first_flight_bytes": ref["first_flight_bytes"],
                   "ff_parity_bytes": ref.get("ff_parity_bytes_med", 0),
                   "parity_bytes": ref["parity_bytes_per_conn"],
                   "client_bytes_total": client_bytes,
                   "client_bytes_total_legacy": legacy}
            if th["lo"] and th["hi"]:
                rec["s0_est"] = amplif.fit_s0(th["lo"], th["hi"],
                                              client_bytes)
            out["thresholds"].append(rec)
            log("  => 임계 %s ~ %s B  (클라 %s B, 예산 %s B)"
                % (th["lo"], th["hi"], client_bytes,
                   amplif.budget(client_bytes)))

    log("")
    log("=" * 92)
    log("인수인계 문서 1-3 재현 - 알고리즘 고정, InitialPacketSize(패딩)만 변경")
    log("=" * 92)
    for group, k in GROUPS:
        for ips in (1200, 1280, 1350, 1450):
            key = "ips|%s|%d" % (group, ips)
            if jr.has(key):
                rec = jr.get(key)
            else:
                lo, hi = LO, HI
                def pr(cert, n):
                    kk = "%s|off|ips%d|c%d|n%d" % (group, ips, cert, n)
                    if jr.has(kk):
                        return jr.get(kk)
                    p, sp = B.start_server(cert, fec="off")
                    rows, cs, _e = B.run_client(group, n, fec="off",
                                                ips=(0 if ips == 1280 else ips),
                                                gap_ms=15, expect_k=k)
                    B.stop_server(p)
                    s = B.summarize(rows, rtt_ms=RTT_MS)
                    r = {"cert": cert, "two_rtt_rate": s["two_rtt_rate"],
                         "first_flight_bytes": cs.get("first_flight_bytes"),
                         "ok": s["ok"], "n": s["n"], "error": _e,
                         "valid": not _e and n > 0 and s["ok"] == s["n"] == n}
                    if not r["valid"]:
                        raise RuntimeError("IPS 임계 측정 불완전: %s" % r)
                    jr.record(kk, r)
                    return r
                base = pr(3000, N_PROBE)
                while hi - lo > RESOLUTION:
                    mid = (lo + hi) // 2
                    r = pr(mid, N_PROBE)
                    if not r.get("ok"):
                        break
                    rate = r["two_rtt_rate"] or 0.0
                    if 0.2 < rate < 0.8:
                        r = pr(mid, N_CONFIRM)
                        rate = r["two_rtt_rate"] or 0.0
                    if rate >= 0.5:
                        hi = mid
                    else:
                        lo = mid
                rec = {"group": group, "ips": ips,
                       "first_flight_bytes": base["first_flight_bytes"],
                       "threshold_lo": lo, "threshold_hi": hi}
                jr.record(key, rec)
            out["ips_sweep"].append(rec)
            log("  %-16s IPS %-5d 첫비행 %-6s B  임계 %d ~ %d B"
                % (rec["group"], rec["ips"], rec["first_flight_bytes"],
                   rec["threshold_lo"], rec["threshold_hi"]))

    log("")
    log("=" * 92)
    log("교환비 - 클라이언트 1 B 가 사들이는 인증서 여유 (이론값 3.0)")
    log("=" * 92)
    ex = []
    for group, _k in GROUPS:
        pts = [(r["first_flight_bytes"],
                0.5 * (r["threshold_lo"] + r["threshold_hi"]))
               for r in out["ips_sweep"]
               if r["group"] == group and r["threshold_lo"]
               and r["threshold_hi"]]
        pts.sort()
        for i in range(1, len(pts)):
            db = pts[i][0] - pts[i - 1][0]
            dt = pts[i][1] - pts[i - 1][1]
            if db:
                ex.append({"group": group, "d_client_bytes": db,
                           "d_threshold": dt, "ratio": dt / float(db)})
                log("  %-16s 클라 +%-5d B  ->  임계 +%-6.0f B   비 %.2f"
                    % (group, db, dt, dt / float(db)))
    for group, _k in GROUPS:
        base = [r for r in out["thresholds"]
                if r["group"] == group and r["arm"] == "off"]
        for arm in ("on1", "on2"):
            cur = [r for r in out["thresholds"]
                   if r["group"] == group and r["arm"] == arm]
            if not base or not cur:
                continue
            b, c = base[0], cur[0]
            if not (b["threshold_lo"] and b["threshold_hi"]
                    and c["threshold_lo"] and c["threshold_hi"]):
                continue
            db = c["client_bytes_total"] - b["client_bytes_total"]
            dt = (0.5 * (c["threshold_lo"] + c["threshold_hi"])
                  - 0.5 * (b["threshold_lo"] + b["threshold_hi"]))
            if db:
                ex.append({"group": group, "arm": arm, "d_client_bytes": db,
                           "d_threshold": dt, "ratio": dt / float(db)})
                log("  %-16s %s 패리티 +%-6.0f B -> 임계 +%-7.0f B  비 %.2f"
                    % (group, arm, db, dt, dt / float(db)))
    out["exchange"]["points"] = ex
    if ex:
        rs = [e["ratio"] for e in ex]
        out["exchange"]["mean_ratio"] = sum(rs) / len(rs)
        log("  인접 두 점의 비 평균 %.2f  <- 계단 때문에 의미가 약하다"
            % out["exchange"]["mean_ratio"])
    for group, _k in GROUPS:
        pts = [(r["first_flight_bytes"],
                0.5 * (r["threshold_lo"] + r["threshold_hi"]))
               for r in out["ips_sweep"]
               if r["group"] == group and r["threshold_lo"]]
        if len(pts) >= 2:
            n = len(pts)
            mx = sum(x for x, _ in pts) / n
            my = sum(y for _, y in pts) / n
            den = sum((x - mx) ** 2 for x, _ in pts)
            slope = (sum((x - mx) * (y - my) for x, y in pts) / den
                     if den else None)
            out["exchange"]["slope_" + group] = slope
            log("  %-16s 전 구간 회귀 기울기 %.2f (이론 3.00)"
                % (group, slope if slope is not None else -1))
    log("")
    log("양자화 모형 대조  허용 = ceil(3*클라 / 1280) * 1280,  임계 = 허용 - s0")
    s0s = []
    for r in out["ips_sweep"]:
        if not r["threshold_lo"]:
            continue
        f = amplif.fit_s0(r["threshold_lo"], r["threshold_hi"],
                          r["first_flight_bytes"])
        s0s.append((r["group"], f["s0_mid"]))
        log("  %-16s 클라 %-5s 예산 %-6d 허용 %-6d 임계 %d~%d  =>  s0 %.0f"
            % (r["group"], r["first_flight_bytes"], f["budget"],
               f["allowed"], r["threshold_lo"], r["threshold_hi"],
               f["s0_mid"]))
    out["s0_estimates"] = [{"group": g, "s0": v} for g, v in s0s]

    log("")
    log("팀 자료 대조")
    for group, (tlo, thi) in TEAM.items():
        ours = [r for r in out["thresholds"]
                if r["group"] == group and r["arm"] == "off"]
        if not ours or not ours[0].get("threshold_lo")                 or not ours[0].get("threshold_hi"):
            log("  %-16s 우리 측정에서 임계를 확정하지 못했다 (%s)"
                % (group, ours[0].get("note", "?") if ours else "자료 없음"))
            continue
        o = ours[0]
        agree = not (o["threshold_hi"] < tlo or o["threshold_lo"] > thi)
        log("  %-16s 팀 %d~%d B   우리 %d~%d B   %s"
            % (group, tlo, thi, o["threshold_lo"], o["threshold_hi"],
               "일치" if agree else "불일치"))
        o["team_agrees"] = agree

    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok),
                       "detail": detail})
        log("[%s] %-50s %s" % ("통과" if ok else "실패", name,
                               detail[:60]))

    log("")
    ths = out["thresholds"]
    _nolo = [t for t in ths
             if not t.get("threshold_lo") or not t.get("threshold_hi")]
    add("전 팔에서 임계가 확정됐다",
        ths and not _nolo,
        "%d 팔 중 미확정 %d" % (len(ths), len(_nolo)))
    _w = [t["threshold_hi"] - t["threshold_lo"] for t in ths
          if t.get("threshold_lo") and t.get("threshold_hi")]
    add("밴드 폭이 이분탐색 해상도 이내 (<= 64 B)",
        _w and max(_w) <= 64,
        "최대 %d B (팔 %d 개)" % (max(_w) if _w else -1, len(_w)))
    _ta = [t for t in ths if "team_agrees" in t]
    _bad = [t for t in _ta if not t["team_agrees"]]
    add("팀 자료와 일치 (이미 계산해 놓고 안 쓰던 값)",
        _ta and not _bad,
        "대조 %d 건 중 불일치 %d" % (len(_ta), len(_bad)))

    def _band(group, arm):
        r = [t for t in ths if t["group"] == group and t["arm"] == arm]
        return (r[0]["threshold_lo"], r[0]["threshold_hi"]) if r else None

    _groups = sorted(set(t["group"] for t in ths))
    _obdiff = []
    for _g in _groups:
        _o, _b = _band(_g, "off"), _band(_g, "buf")
        if _o and _b and _o != _b:
            _obdiff.append((_g, _o, _b))
    add("[부정] off 와 buf 의 임계가 같다 "
        "(버퍼링만으로는 임계가 안 움직인다)",
        not _obdiff, str(_obdiff[:2]) or "전 그룹 동일")
    _mono = []
    for _g in _groups:
        _seq = [_band(_g, a) for a in ("off", "on1", "on2")]
        if all(_seq) and not (_seq[0][1] < _seq[1][0]
                              and _seq[1][1] < _seq[2][0]):
            _mono.append((_g, _seq))
    add("패리티가 늘수록 임계가 오른다 (off < on1 < on2, 밴드가 안 겹친다)",
        _groups and not _mono, str(_mono[:1]) or "전 그룹 단조")
    npass = sum(1 for c in checks if c["ok"])
    log("-" * 78)
    log("%d / %d 통과" % (npass, len(checks)))
    out["checks"] = checks
    out["passed"], out["total"] = npass, len(checks)

    path = B.save("p2_threshold.json", out)
    log("saved: %s" % path)
    return 0 if npass == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
