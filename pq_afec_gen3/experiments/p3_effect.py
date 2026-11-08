from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B
from _journal import Journal, code_fingerprint

RTT_MS = 50.0
CERT = 2955
N_DEFAULT = 200
N_PRECISE = 1200
N = int(os.environ.get("PADFEC_P3_N")
        or (N_PRECISE if "--precise" in sys.argv else N_DEFAULT))
GROUPS = [("X25519MLKEM768", 2), ("x25519", 1)]

CONDS = [(0.0, 1.0), (1.0, 1.0), (2.0, 1.0), (5.0, 1.0),
         (2.0, 3.0), (5.0, 3.0)]
DIRS = [("c2s", True, False), ("sym", True, True)]
ARMS = [("off", "off", 1), ("on1", "on", 1), ("on2", "on", 2)]


def unit(group, k, loss, burst, dname, lc, ls, arm, fec, m, jr):
    key = "%s|k%d|l%.1f|b%.1f|%s|%s|m%d|n%d" % (
        group, k, loss, burst, dname, arm, m, N)
    if jr.has(key):
        return jr.get(key), True
    B.set_netem(RTT_MS / 2.0,
                loss_c2s=(loss if lc else 0.0),
                loss_s2c=(loss if ls else 0.0),
                burst_len=burst)
    p, sp = B.start_server(CERT, fec=("on" if fec == "on" else fec))
    rows, cs, err = B.run_client(group, N, fec=fec, m=m, gap_ms=10,
                                 timeout_s=8, expect_k=k)
    B.stop_server(p)
    ss = B.read_server_stats(sp)
    s = B.summarize(rows, rtt_ms=RTT_MS)
    rec = {"group": group, "loss": loss, "burst": burst, "dir": dname,
           "arm": arm, "m": m,
           "n": s["n"], "ok": s["ok"], "fail": s["fail"],
           "p50": s["p50"], "p90": s["p90"], "p95": s["p95"], "p99": s["p99"],
           "mean": s["mean"], "max": s["max"],
           "pto_rate": s["pto_rate"],
           "samples": [r["ms"] for r in rows if r.get("ok")],
           "srv_originals": ss.get("originals"),
           "srv_parities": ss.get("parities"),
           "srv_recovered": ss.get("recovered"),
           "srv_recover_crc_fail": ss.get("recover_crc_fail"),
           "srv_late_recovered": ss.get("late_recovered"),
           "srv_unrecoverable": ss.get("unrecoverable_seen"),
           "err": err}
    ok = (s["n"] == N and (ss.get("recover_crc_fail") or 0) == 0
          and not err)
    if loss == 0.0:
        ok = ok and s["fail"] == 0
    rec["valid"] = ok
    if ok:
        jr.record(key, rec)
    return rec, ok


def main():
    B.harden()
    B.require_root()
    B.require_bin()
    B.setup()

    fp = code_fingerprint(["experiments/p3_effect.py",
                           "experiments/quicbed/qamp.go",
                           "experiments/padbed.py"], ROOT)
    jr = Journal(os.path.join(B.STATE, "p3_units.jsonl"), fp)

    results = []
    for group, k in GROUPS:
        for loss, burst in CONDS:
            for dname, lc, ls in DIRS:
                if loss == 0.0 and dname == "sym":
                    continue
                for arm, fec, m in ARMS:
                    rec, ok = unit(group, k, loss, burst, dname, lc, ls,
                                   arm, fec, m, jr)
                    results.append(rec)
                    print("%-16s 손실%4.1f%% 버스트%.0f %-4s %-4s | "
                          "성공 %3d/%3d  p50 %6.1f  p95 %7.1f  p99 %7.1f  "
                          "PTO %5.1f%%  복구 %s%s"
                          % (group, loss, burst, dname, arm,
                             rec["ok"], rec["n"], rec["p50"] or -1,
                             rec["p95"] or -1, rec["p99"] or -1,
                             100 * (rec["pto_rate"] or 0),
                             rec["srv_recovered"],
                             "" if ok else "   <-- 무효"))
                    sys.stdout.flush()

    print()
    print("=" * 104)
    print("off 대비 FEC 팔 (같은 조건)")
    print("=" * 104)
    print("%-16s %-6s %-6s %-5s %-5s %-9s %-8s %-8s %-8s %s"
          % ("그룹", "손실", "버스트", "방향", "팔", "성공률Δ", "p50Δ", "p95Δ",
             "p99Δ", "PTO율 off->on"))
    comps = []
    for group, _k in GROUPS:
        for loss, burst in CONDS:
            for dname, _lc, _ls in DIRS:
                if loss == 0.0 and dname == "sym":
                    continue
                a = [r for r in results if r["group"] == group
                     and r["loss"] == loss and r["burst"] == burst
                     and r["dir"] == dname and r["arm"] == "off"]
                if not a or not a[0]["valid"]:
                    continue
                a = a[0]
                for armname in ("on1", "on2"):
                    b = [r for r in results if r["group"] == group
                         and r["loss"] == loss and r["burst"] == burst
                         and r["dir"] == dname and r["arm"] == armname]
                    if not b or not b[0]["valid"]:
                        continue
                    b = b[0]

                    def d(f, a=a, b=b):
                        if a[f] is None or b[f] is None:
                            return None
                        return b[f] - a[f]
                    c = {"group": group, "loss": loss, "burst": burst,
                         "dir": dname, "arm": armname,
                         "d_success": (b["ok"] - a["ok"]) / float(N),
                         "d_p50": d("p50"), "d_p95": d("p95"),
                         "d_p99": d("p99"),
                         "pto_off": a["pto_rate"], "pto_on": b["pto_rate"],
                         "recovered": b["srv_recovered"]}
                    comps.append(c)
                    print("%-16s %-6s %-6.0f %-5s %-5s %+8.1f%% %+7.1f "
                          "%+7.1f %+7.1f   %.1f%% -> %.1f%%"
                          % (group, "%.1f%%" % loss, burst, dname, armname,
                             100 * c["d_success"], c["d_p50"] or 0,
                             c["d_p95"] or 0, c["d_p99"] or 0,
                             100 * (a["pto_rate"] or 0),
                             100 * (b["pto_rate"] or 0)))

    n_valid = sum(1 for r in results if r["valid"])
    crc_fail = sum(r["srv_recover_crc_fail"] or 0 for r in results)
    recovered = sum(r["srv_recovered"] or 0 for r in results)
    print()
    print("유효 단위 %d/%d | 총 복구 %d 건 | 복구 CRC 실패 %d 건"
          % (n_valid, len(results), recovered, crc_fail))

    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok),
                       "detail": detail})
        print("[%s] %-54s %s" % ("통과" if ok else "실패", name,
                                 detail[:60]))

    print()
    add("유효 단위가 전부다 (무효 측정이 조용히 빠지지 않는다)",
        n_valid == len(results),
        "%d/%d" % (n_valid, len(results)))
    _nostat = [r for r in results if r.get("srv_recovered") is None]
    add("모든 팔에서 서버 통계가 실제로 있었다 "
        "(없으면 CRC 판정이 공허해진다)",
        not _nostat,
        "없는 팔 %d 개" % len(_nostat))
    _loss = [r for r in results if (r.get("loss") or 0) > 0
             and r.get("arm") != "off"]
    def _lam(r):
        return (r.get("n") or 0) * (r.get("loss") or 0) / 100.0 \
            / max(1.0, r.get("burst") or 1.0)
    _hi = [r for r in _loss if _lam(r) >= 5.0]
    _norec_hi = [r for r in _hi if (r.get("srv_recovered") or 0) <= 0]
    _norec_lo = [(r["group"], r["loss"], r["burst"], r["dir"],
                  r["arm"], round(_lam(r), 2)) for r in _loss
                 if _lam(r) < 5.0 and (r.get("srv_recovered") or 0) <= 0]
    add("복구가 실제로 일어난다 (λ>=5 인 손실 조건 전부)",
        _hi and not _norec_hi,
        "λ>=5 조건 %d 개 중 복구 0 인 것 %d | λ<5 에서 복구 0: %s"
        % (len(_hi), len(_norec_hi), _norec_lo or "없음"))
    _tot_rec = sum(r.get("srv_recovered") or 0 for r in _loss)
    add("손실 조건 전체 합의 복구 > 0 (전면 고장 감지)",
        _loss and _tot_rec > 0,
        "손실 %d 조건 합계 %d 건" % (len(_loss), _tot_rec))
    _clean = [r for r in results if (r.get("loss") or 0) == 0]
    _ghost = sum(r.get("srv_recovered") or 0 for r in _clean)
    add("[부정] 무손실 조건의 복구가 정확히 0 (헛복구가 없다)",
        _clean and _ghost == 0,
        "무손실 %d 팔에서 복구 %d 건" % (len(_clean), _ghost))
    _d50 = [abs(c.get("d_p50") or 0.0) for c in comps
            if (c.get("loss") or 0) == 0]
    add("무손실에서 FEC 의 p50 비용이 1 ms 미만 (공짜에 가깝다)",
        _d50 and max(_d50) < 1.0,
        "최대 %.3f ms (%d 조건)" % (max(_d50) if _d50 else -1,
                                   len(_d50)))
    add("복구 CRC 실패 0", crc_fail == 0, "총 %d 건" % crc_fail)
    npass = sum(1 for c in checks if c["ok"])
    print("-" * 78)
    print("%d / %d 통과" % (npass, len(checks)))

    out = {"rtt_ms": RTT_MS, "cert": CERT, "n": N, "runs": results,
           "comparisons": comps, "valid_units": n_valid,
           "total_units": len(results), "total_recovered": recovered,
           "recover_crc_fail": crc_fail,
           "checks": checks, "passed": npass, "total": len(checks)}
    _fname = ("smoke_" if N < N_DEFAULT else "") + "p3_effect.json"
    print("saved:", B.save(_fname, out))
    return 0 if npass == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
