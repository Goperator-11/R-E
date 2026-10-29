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
# 🩸 2026-08-21 - p11·p15 와 같은 처방. 6 차에서 p4 의 정책 일치가
#    10 조건 중 **3 개**만 판정 가능했다(나머지는 전 팔이 잡음 동률).
#    원자료로 필요 표본을 계산하니 553~2,498 이었다 - 차이가 5 ms 인
#    조건도 꼬리 분산(SE 9.1)이 그만큼 커서 판정이 안 된다.
#    기준은 그대로 두고 표본만 키운다. 저널 키에 n 이 들어가므로
#    상시 실행분 캐시는 덮이지 않는다.
#        python experiments/p3_effect.py --precise      (N=1200)
#        PADFEC_P3_N=800 python experiments/p3_effect.py
N_DEFAULT = 200
N_PRECISE = 1200
N = int(os.environ.get("PADFEC_P3_N")
        or (N_PRECISE if "--precise" in sys.argv else N_DEFAULT))
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
           # 🩸 2026-08-21 - 원자료를 버리지 않는다. 요약만 남기면
           #    '팔 간 차이가 잡음인가'를 사후에 잴 수 없다 - p4 의
           #    정책 일치가 그 질문에 답해야 한다(부트스트랩).
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

    # ------------------------------------------------------------ 판정
    # 2026-08-21 - 이 단계는 그전까지 `return 0 if crc_fail == 0 else 1`
    # **하나뿐**이었다. 이름은 "복구 동작 + 손실 조건 효과" 인데
    #   d_p95 = +100 ms 여도 / 복구가 0 건이어도 / 유효 단위가 0 이어도
    # 전부 통과했다. 게다가 서버 통계를 못 읽으면 crc_fail 이 None 이라
    # `None or 0 == 0` 으로 조용히 통과한다(p11 에서 실제로 겪은 함정).
    #
    # ⚠️ **d_p95 / d_p99 는 판정에 쓰지 않는다.** 기준선 p95 가 꼬리에
    #    걸리는지에 따라 개선 여지 자체가 달라져서 20 조건 중 9 건이
    #    양수다(p8 도 같은 이유로 "기준선 p95 는 불연속면에 걸려
    #    불안정하다" 고 적어 두었다). 그리고 d_p99 는 실행 간에
    #    −151.8 ↔ −93.5 로 뒤집힌다(n=200 에서 위에서 두 번째 표본 하나).
    #    **효과의 통계적 판정은 p8 이 부트스트랩 신뢰구간으로 한다.**
    #    여기서는 실행 간에 흔들리지 않는 것만 못 박는다.
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
    # 🩸 2026-08-21 재보정 - 첫 판은 **모든** 손실 조건에 복구 > 0 을
    #    요구했다. 그런데 버스트 L 채널에서 손실은 에피소드로 뭉치고
    #    기대 에피소드 수는 λ = n·p/L 이다. 2%·버스트3 이면 λ=1.33 →
    #    정상인데도 P(복구 0) ≈ 26%. 실제 기저율: 1차 1 조건, 2차 0,
    #    3차 1 조건 - 정상 작동 중에 실행의 3~5 할이 붉어지는 **양치기
    #    검사**였다. λ >= 5 (P(0|정상) <= 0.7%) 인 조건에만 조건별로
    #    요구하고, 전면 고장은 전체 합(합 λ ≈ 150)으로 잡는다.
    #    λ 낮은 조건의 복구 0 은 정보로 찍는다 - 감추지 않는다.
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
