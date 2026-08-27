# -*- coding: utf-8 -*-
"""T_recover 를 **결정적 소거**로 직접 잰다.

왜 이 방법인가
--------------
무작위 손실(netem)로는 손실 사건이 n=180 중 ~9 회뿐이라 평균이 잡음에 묻힌다
(손실 실험의 잔차 RMSE 6.5 ms 가 그것이다). `-drop-initial` 로 **매 판마다**
첫 비행의 특정 데이터그램을 버리면, 모든 표본이 손실 사건이 되어
회복 비용이 한 번에 나온다.

    T_recover = (소거 판 HCT) - (정상 판 HCT)

세 팔
    A 정상                      기준선
    B 소거 + FEC 없음           회복 비용 그대로
    C 소거 + 패리티 m=1         FEC 가 실제로 복구하는가 (A 로 돌아와야 한다)

실행: unshare -Urnm python3 trec.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import padbed   # noqa: E402

RTT_MS = 50.0
N = 60
WARMUP = 10
CERT = 2308          # 명세 4-4 Tranco p5. 예측 임계 3340 아래 -> 정상은 1-RTT
IPS = 1280

CASES = [
    ("x25519", 1, "A 정상",            "off", 1, None),
    ("x25519", 1, "B 소거(0) FEC없음",  "off", 1, "0"),
    ("x25519", 1, "C 소거(0) 패리티1",  "fec", 1, "0"),
    ("X25519MLKEM768", 2, "A 정상",            "off", 1, None),
    ("X25519MLKEM768", 2, "B 소거(0) FEC없음",  "off", 1, "0"),
    ("X25519MLKEM768", 2, "C 소거(0) 패리티1",  "fec", 1, "0"),
]


def main():
    padbed.harden()
    padbed.require_root()
    padbed.require_bin()
    padbed.setup(mtu=1500)
    padbed.set_netem(RTT_MS / 2.0, 0.0, 0.0)   # 손실 0 — 소거는 우리가 건다

    out = {"rtt_ms": RTT_MS, "cert": CERT, "ips": IPS, "n": N, "rows": []}
    srv = None
    try:
        srv, _ = padbed.start_server(CERT, fec="fec")
        for group, k, label, fec, m, drop in CASES:
            extra = ["-drop-initial", drop] if drop else []
            rows, _st, err = padbed.run_client(
                group, N, fec=fec, m=m, ips=IPS, gap_ms=20,
                timeout_s=15, warmup=WARMUP, extra=extra)
            summ = padbed.summarize(rows, rtt_ms=RTT_MS)
            rec = {"group": group, "k": k, "case": label, "fec": fec,
                   "drop": drop, "n": summ.get("n"), "ok": summ.get("ok"),
                   "mean": summ.get("mean"), "p50": summ.get("p50"),
                   "p95": summ.get("p95"), "err": err}
            out["rows"].append(rec)
            print("%-16s %-18s n=%-4s ok=%-5s mean=%-9s p50=%-9s p95=%-9s %s"
                  % (group, label, rec["n"], rec["ok"],
                     None if rec["mean"] is None else round(rec["mean"], 2),
                     rec["p50"], rec["p95"], err), flush=True)
    finally:
        padbed.stop_server(srv)

    print()
    print("=== T_recover 직접 측정 ===")
    by = {}
    for r in out["rows"]:
        by[(r["group"], r["case"][0])] = r
    for group in ("x25519", "X25519MLKEM768"):
        a, b, c = by.get((group, "A")), by.get((group, "B")), by.get((group, "C"))
        if not (a and b and a["p50"] and b["p50"]):
            continue
        t_p50 = b["p50"] - a["p50"]
        t_mean = b["mean"] - a["mean"]
        print("  %s" % group)
        print("    기준선 p50 %.2f ms  ->  소거 p50 %.2f ms" % (a["p50"], b["p50"]))
        print("    T_recover = %.2f ms = %.2f RTT   (평균 기준 %.2f ms = %.2f RTT)"
              % (t_p50, t_p50 / RTT_MS, t_mean, t_mean / RTT_MS))
        if c and c["p50"]:
            back = c["p50"] - a["p50"]
            print("    패리티 m=1 로 복구: p50 %.2f ms (기준선 대비 %+.2f ms) -> %s"
                  % (c["p50"], back,
                     "복구 성공" if back < 0.5 * RTT_MS else "복구 실패"))
        out.setdefault("t_recover", {})[group] = {
            "p50_ms": t_p50, "p50_rtt": t_p50 / RTT_MS,
            "mean_ms": t_mean, "mean_rtt": t_mean / RTT_MS}

    print()
    print("코드 기본값은 T_recover = RTT = %.1f ms 다 (padfec/policy.py cost_of_v2)."
          % RTT_MS)

    dst = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "probe_trecover.json")
    with open(dst, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("wrote", dst)


if __name__ == "__main__":
    main()
