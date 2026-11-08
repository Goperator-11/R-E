#!/usr/bin/env python3
import os, sys, json, statistics, time

sys.path.insert(0, "/mnt/c/dev/pq_afec/experiments")
sys.path.insert(0, "/mnt/c/dev/pq_afec")
import padbed as B

GROUP, K, RTT = "X25519MLKEM768", 2, 50.0
CERT = int(os.environ.get("PROBE_CERT", "9000"))
LOSS = float(os.environ.get("PROBE_LOSS", "0.0"))
GAP = int(os.environ.get("PROBE_GAP", "50"))
RATES = [float(x) for x in os.environ.get(
    "PROBE_RATES", "0,40,20,13,10,8,6,5,4").split(",")]
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
    cut = float(os.environ["PROBE_CUT"]) if os.environ.get("PROBE_CUT") else (
        (statistics.median(m0v) + statistics.median(m2v)) / 2.0
        if (m0v and m2v) else None)
    if not os.environ.get("PROBE_CUT") and m0v and m2v:
        if statistics.median(m0v) < 1.5 * RTT:
            print("⚠ m0 중앙값 %.1f ms < 1.5·RTT — m0 가 2-RTT 가 아니다. "
                  "자동 경계를 믿지 마라 (PROBE_CUT 을 줘라)."
                  % statistics.median(m0v), flush=True)
    for aname, fec, m, n in ARMS:
        d = per[aname]; v = d["ms"]; ss = d["srv"]
        frac = (sum(1 for x in v if x < cut) / len(v)) if (cut and v) else None
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
