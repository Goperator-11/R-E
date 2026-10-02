#!/usr/bin/env python3
"""증폭 신용 '경주'의 **문턱** q(d) 를 잰다 — 전이 구간을 촘촘히 훑어서.

padfec/policy.py 의 RACE_DELAY_MS / RACE_WIN_Q 는 **이 탐침이 만든 수**다.
그 표가 어디서 왔는지 다음 사람이 물으면 여기를 보면 된다.

  실행:  wsl -d Ubuntu -- bash -lc "cd /mnt/c/dev/pq_afec &&              unshare -Urnm python3 -u experiments/_probe_race.py"
  결과:  experiments/results/probe_race.json

무엇을 재나
-----------
뒤따르는 패리티(m=1 의 유일한 것)는 마지막 원본보다 d = 패리티바이트/대역 만큼
늦게 도착한다. 그 신용이 서버의 송신 결정보다 먼저 닿아야 1-RTT 가 된다.
대역을 바꾸면 d 가 바뀌므로, **대역 스윕이 곧 지연 스윕**이다.

⚠️ **손실 0%** 로 잰다. 손실이 있으면 m=1 의 2-RTT 가 두 원인(경주에 짐 /
   패리티 자체를 잃음)에서 나와 섞인다. 손실 0 이면 모형의 p_two_rtt 가 0 이라
   **m1 의 1-RTT 비율이 곧 q(d)** 로 읽힌다.

⚠️ **gap 50 ms.** gap 8 로 붙여 돌리면 앞 연결의 꼬리가 다음 연결 뒤에 줄을 선다
   (2026-08-26 §4c).

⚠️ **기계가 한가할 때 재라.** q 는 서버의 송신 결정 지연 분포이고 부하에 달렸다.
   다른 실험과 겹쳐 돌린 판은 10 Mbps 에서 0.387 을 냈고, 한가한 기계에서 같은
   자리가 0.004 였다. 겹쳐 재면 그 수는 자료가 아니다.

m0(늘 2-RTT)과 m2(늘 1-RTT)를 같이 재서 1-RTT/2-RTT 경계(cut)를 **자료에서**
뽑는다. m2 가 어느 대역에서도 100% 인 것 자체가 모형의 뼈대를 확인해 준다 -
앞선 패리티는 원본보다 먼저 나가므로 경주가 없다.
"""
import os, sys, json, statistics, time

sys.path.insert(0, "/mnt/c/dev/pq_afec/experiments")
sys.path.insert(0, "/mnt/c/dev/pq_afec")
import padbed as B

GROUP, K, RTT = "X25519MLKEM768", 2, 50.0
# 🩸 2026-08-26 - cert 만 리터럴로 박혀 있었다(9000 = 임계 위). 나머지 조건은
#    전부 환경변수인데 이것만 못 바꿔서, **임계 아래**(cert 2955)를 재려면
#    파일을 고쳐야 했다. p11 의 불일치 두 건이 바로 그 임계 아래에 있다.
CERT = int(os.environ.get("PROBE_CERT", "9000"))
LOSS = float(os.environ.get("PROBE_LOSS", "0.0"))
GAP = int(os.environ.get("PROBE_GAP", "50"))
# 0 = 무제한. 전이 구간(도착지연 0 ~ 2.7 ms)을 촘촘히.
RATES = [float(x) for x in os.environ.get(
    "PROBE_RATES", "0,40,20,13,10,8,6,5,4").split(",")]
# (이름, fec, m, N)  — m1 을 제일 많이 잰다. m0/m2 는 경계자다.
ARMS = [("m0", "off", 0, int(os.environ.get("PROBE_N0", "120"))),
        ("m1", "on",  1, int(os.environ.get("PROBE_N1", "300"))),
        ("m2", "on",  2, int(os.environ.get("PROBE_N2", "150")))]
OUT = os.environ.get("PROBE_OUT",
                     "/mnt/c/dev/pq_afec/experiments/results/probe_race.json")

B.harden()
B.require_root()
B.setup()

out = {"cert": CERT, "k": K, "rtt_ms": RTT, "loss_pct": LOSS, "gap_ms": GAP,
       "rates": RATES, "arms": [a[0] for a in ARMS], "rows": [],
       "started": time.strftime("%Y-%m-%d %H:%M:%S")}
print("cert=%d k=%d rtt=%.0f loss=%.1f%% gap=%dms" % (CERT, K, RTT, LOSS, GAP))
print("%-9s %-4s %5s %8s %8s %8s %9s %9s" %
      ("rate", "arm", "n", "mean", "p50", "cut", "1-RTT%", "par_bytes"))

for rate in RATES:
    B.set_netem(RTT / 2.0, loss_c2s=LOSS, rate_up_mbit=rate)
    per = {}
    for aname, fec, m, n in ARMS:
        sp = "/tmp/padfec/race2_%g_%s.json" % (rate, aname)
        p, sp = B.start_server(CERT, fec="on", stats_path=sp)
        try:
            rows, cs, e = B.run_client(GROUP, n, fec=fec, m=max(m, 1),
                                       gap_ms=GAP, timeout_s=10, expect_k=K,
                                       uplink_mbps=rate)
        finally:
            B.stop_server(p)
        ss = B.read_server_stats(sp) or {}
        ok = [r["ms"] for r in rows if r.get("ok")]
        pb = [r.get("first_flight_parity_bytes", 0) for r in rows if r.get("ok")]
        per[aname] = {"ms": ok, "srv": ss, "err": e, "m": m,
                      "par_bytes": (statistics.median(pb) if pb else None)}
    m0v, m2v = per["m0"]["ms"], per["m2"]["ms"]
    # 🩸 2026-08-26 - 자동 경계는 **m0 가 2-RTT 라는 전제** 위에 서 있다.
    #    임계 **아래**(cert 2955)에서는 m0 도 1-RTT 라 두 중앙값이 붙어
    #    경계가 ~50 ms 에 놓이고, 그러면 1-RTT 비율이 통째로 헛수가 된다.
    #    자가 조건에 안 맞는 자리다. 그럴 땐 PROBE_CUT 으로 직접 준다
    #    (p18 이 쓰는 관례와 같이 1.5·RTT = 75 ms).
    cut = float(os.environ["PROBE_CUT"]) if os.environ.get("PROBE_CUT") else (
        (statistics.median(m0v) + statistics.median(m2v)) / 2.0
        if (m0v and m2v) else None)
    if not os.environ.get("PROBE_CUT") and m0v and m2v:
        # 전제가 깨졌으면 조용히 넘어가지 말고 말한다.
        if statistics.median(m0v) < 1.5 * RTT:
            print("⚠ m0 중앙값 %.1f ms < 1.5·RTT — m0 가 2-RTT 가 아니다. "
                  "자동 경계를 믿지 마라 (PROBE_CUT 을 줘라)."
                  % statistics.median(m0v), flush=True)
    for aname, fec, m, n in ARMS:
        d = per[aname]; v = d["ms"]; ss = d["srv"]
        frac = (sum(1 for x in v if x < cut) / len(v)) if (cut and v) else None
        # 도착지연: 뒤따르는 패리티 하나의 직렬화 시간
        pbv = d["par_bytes"] or 0
        delay = (pbv * 8.0 / (rate * 1e6) * 1e3) if rate > 0 else 0.0
        rec = {"rate": rate, "arm": aname, "m": m, "n_ok": len(v),
               "mean_ms": statistics.fmean(v) if v else None,
               "p50_ms": statistics.median(v) if v else None,
               "cut_ms": cut, "frac_1rtt": frac,
               "parity_bytes": pbv, "arrive_delay_ms": delay,
               "credit_parities": ss.get("credit_parities"),
               "recovered": ss.get("recovered"),
               "err": d["err"], "ms": v}
        out["rows"].append(rec)
        print("%-9s %-4s %5d %8s %8s %8s %9s %9s" % (
            ("무제한" if rate == 0 else "%g" % rate), aname, len(v),
            ("%.2f" % rec["mean_ms"]) if rec["mean_ms"] else "-",
            ("%.2f" % rec["p50_ms"]) if rec["p50_ms"] else "-",
            ("%.1f" % cut) if cut else "-",
            ("%.1f%%" % (100 * frac)) if frac is not None else "-",
            pbv), flush=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print()

out["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
print("saved:", OUT)
