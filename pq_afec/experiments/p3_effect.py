# -*- coding: utf-8 -*-
"""P3 - 복구가 실제로 되는가, 그리고 손실 조건에서 무엇이 나아지는가.

인수인계 문서 단계 3(디코더)과 단계 4(효과 측정)에 해당한다.

두 부분
  A. 복구 정확성
     손실을 걸고, 서버가 XOR 로 복원한 데이터그램이 **원본과 같은지**
     부호 스스로 CRC 로 확인한 뒤 스택에 넘겼는지 센다. 복구 실패
     (crc 불일치)가 하나라도 있으면 그 조건은 무효로 표시한다.
     ⚠️ 1차 연구에서 "복구했다고 세었는데 응용까지 도달하지 않은" 결함을
        두 번 겪었다. 그래서 카운터가 아니라 **핸드셰이크 성공률과 HCT**로
        효과를 판정한다 - 복구가 진짜면 꼬리가 줄어야 한다.

  B. 효과
     손실 0~5%, 균일/버스트, 방향(c2s 전용 / 대칭) 을 훑으며
     HCT p50/p95/p99 와 PTO 발생률을 off / on 두 팔에서 비교한다.
     우리 FEC 는 클라이언트->서버 방향만 보호하므로 c2s 전용 조건이
     메커니즘을 분리해 보여 주고, 대칭 조건이 현실적인 이득을 보여 준다.

자체 점검 (하나라도 깨지면 그 단위는 무효)
  * 손실 0 조건에서 성공률이 100% 여야 한다
  * FEC 를 켠 팔의 성공률이 끈 팔보다 낮으면 안 된다
  * 복구 crc 실패는 0 이어야 한다

Output: experiments/results/p3_effect.json
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B                               # noqa: E402
from _journal import Journal, code_fingerprint   # noqa: E402

RTT_MS = 50.0
CERT = 2955          # 두 팔 모두 1-RTT 인 크기. 증폭 효과와 섞이지 않게.
N = 200
GROUPS = [("X25519MLKEM768", 2), ("x25519", 1)]

# (손실%, 평균버스트) - 버스트는 netem gemodel
CONDS = [(0.0, 1.0), (1.0, 1.0), (2.0, 1.0), (5.0, 1.0),
         (2.0, 3.0), (5.0, 3.0)]
DIRS = [("c2s", True, False), ("sym", True, True)]
# on1 = 패리티 1개 (원본 뒤 -> 복구만)
# on2 = 패리티 2개 (앞 1 = 증폭 신용, 뒤 1 = 복구)
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
    # 🩸 순서가 중요하다. 서버는 종료 신호를 받을 때 통계를 마지막으로
    # 기록하므로, **먼저 죽이고 나서 읽어야** 마지막 시행들이 반영된다.
    # 반대로 하면 복구 건수가 실제보다 적게 보고된다(40회 중 39회로 나왔다).
    B.stop_server(p)
    ss = B.read_server_stats(sp)
    s = B.summarize(rows, rtt_ms=RTT_MS)
    rec = {"group": group, "loss": loss, "burst": burst, "dir": dname,
           "arm": arm, "m": m,
           "n": s["n"], "ok": s["ok"], "fail": s["fail"],
           "p50": s["p50"], "p90": s["p90"], "p95": s["p95"], "p99": s["p99"],
           "mean": s["mean"], "max": s["max"],
           "pto_rate": s["pto_rate"],
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
                    continue          # 무손실은 방향이 의미 없다
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

    # ------------------------------------------------------------- 대조표
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

    out = {"rtt_ms": RTT_MS, "cert": CERT, "n": N, "runs": results,
           "comparisons": comps, "valid_units": n_valid,
           "total_units": len(results), "total_recovered": recovered,
           "recover_crc_fail": crc_fail}
    print("saved:", B.save("p3_effect.json", out))
    return 0 if crc_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
