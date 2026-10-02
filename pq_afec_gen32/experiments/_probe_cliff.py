# -*- coding: utf-8 -*-
"""임시 탐침 — 양자 경계 절벽을 1점으로 확인한다.

정식 실험은 p12_quantum.py 다. 이건 헤드라인 주장을 **가장 싼 방법으로**
죽이거나 살리려고 만든 일회용 스크립트다.

주장 (PADFEC v2 명세 §2 따름정리)
    quic-go 기본 InitialPacketSize=1280 은 증폭 양자 경계에 정확히 걸터앉는다.
    3B = 3k*1280 은 항상 1280 의 배수이므로 허용량이 딱 맞아떨어지고,
    1 바이트만 더 보내면 허용량이 1280 B 뛴다.

설계
    인증서를 두 예측 임계 **사이**에 고정한다 (x25519: 3340 < cert < 4585.5).
    cert = 4000 B 로 잡으면
        ips=1280 -> 허용 3840, 서버 비행 4000+500 = 4500 > 3840 -> 2-RTT
        ips=1281 -> 허용 5120, 4000+534.5 = 4534.5 <= 5120        -> 1-RTT
    즉 **1 바이트 차이로 HCT 가 약 106 ms <-> 55 ms** 로 갈려야 한다.

부정 시험
    ips=1279 는 1280 과 **같은 칸**이어야 한다(경계를 안 넘으므로 2-RTT).
    이게 깨지면 "경계는 1281" 이 아니라 다른 것이 원인이다.

실행:  unshare -Urnm python3 experiments/_probe_cliff.py
"""
from __future__ import annotations

import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import padbed  # noqa: E402

P = 1280
AMP = 3
RTT_MS = 50.0

# 인자: [group] [cert] [n]
#   x25519(k=1)          cert 4000 은 예측 임계 3340 과 4585.5 사이
#   X25519MLKEM768(k=2)  cert 6500 은 예측 임계 5945.5 와 7191 사이
GROUP = sys.argv[1] if len(sys.argv) > 1 else "x25519"
CERT = int(sys.argv[2]) if len(sys.argv) > 2 else (
    4000 if GROUP == "x25519" else 6500)
N = int(sys.argv[3]) if len(sys.argv) > 3 else 40
K_EXPECT = 1 if GROUP in ("x25519", "secp256r1") else 2

# 명세 §2.5 의 정밀화 모형
S0_BASE = {"x25519": 396.5, "X25519MLKEM768": 1527.5}
C_PKT = 34.5


def allowed(client_bytes):
    if client_bytes <= 0:
        return 0
    return -(-AMP * client_bytes // P) * P


def predict(group, k, ips):
    b = k * ips
    a = allowed(b)
    n_pkt = a // P
    s0 = S0_BASE[group] + n_pkt * C_PKT
    thr = a - s0
    return {"client_bytes": b, "allowed": a, "n_bin": n_pkt,
            "s0_pred": s0, "threshold_pred": thr,
            "n_rtt_pred": 1 if (CERT + s0) <= a else 2}


def main():
    padbed.harden()
    padbed.require_root()
    padbed.require_bin()
    padbed.setup(mtu=1500)
    padbed.set_netem(RTT_MS / 2.0, 0.0, 0.0)

    out = {"group": GROUP, "cert": CERT, "rtt_ms": RTT_MS, "n": N, "rows": []}
    plan = [(GROUP, K_EXPECT, ips)
            for ips in (1279, 1280, 1281, 1282, 1350)]

    srv = None
    try:
        srv, spath = padbed.start_server(CERT, fec="off")
        for group, k, ips in plan:
            pred = predict(group, k, ips)
            rows, _stats, err = padbed.run_client(
                group, N, fec="off", ips=(0 if ips == 1280 else ips),
                gap_ms=25, timeout_s=12)
            summ = padbed.summarize(rows, rtt_ms=RTT_MS)
            rec = {"group": group, "ips": ips, "k_expect": k}
            rec.update(pred)
            rec["err"] = err
            for key in ("n", "ok", "p50", "p95", "two_rtt_rate",
                        "rtt_multiple", "initial_datagrams_median"):
                rec[key] = summ.get(key)
            ff = [r.get("first_flight_bytes") for r in rows
                  if r.get("first_flight_bytes")]
            rec["first_flight_bytes"] = padbed.pctl(ff, 0.5) if ff else None
            rec["n_rtt_obs"] = (
                None if summ.get("two_rtt_rate") is None
                else (2 if summ["two_rtt_rate"] > 0.5 else 1))
            out["rows"].append(rec)
            print("ips=%-5d B=%-6s A=%-6s bin=%-3s thr_pred=%-8.1f "
                  "n_rtt pred=%s obs=%s  p50=%s  2rtt=%s"
                  % (ips, rec["client_bytes"], rec["allowed"], rec["n_bin"],
                     rec["threshold_pred"], rec["n_rtt_pred"],
                     rec["n_rtt_obs"], rec["p50"], rec["two_rtt_rate"]),
                  flush=True)
    finally:
        padbed.stop_server(srv)

    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    by = {r["ips"]: r for r in out["rows"]}
    if 1280 in by and 1281 in by:
        a, b = by[1280], by[1281]
        add("1280 은 2-RTT, 1281 은 1-RTT (1 바이트 절벽)",
            a["n_rtt_obs"] == 2 and b["n_rtt_obs"] == 1,
            "1280: n_rtt=%s p50=%s / 1281: n_rtt=%s p50=%s"
            % (a["n_rtt_obs"], a["p50"], b["n_rtt_obs"], b["p50"]))
        if a["p50"] and b["p50"]:
            add("절벽의 크기가 왕복 하나(>= 0.8 RTT)",
                (a["p50"] - b["p50"]) >= 0.8 * RTT_MS,
                "차 %.2f ms = %.3f RTT" % (a["p50"] - b["p50"],
                                           (a["p50"] - b["p50"]) / RTT_MS))
    if 1279 in by and 1280 in by:
        add("부정 시험: 1279 와 1280 은 같은 칸",
            by[1279]["n_rtt_obs"] == by[1280]["n_rtt_obs"],
            "1279 n_rtt=%s / 1280 n_rtt=%s"
            % (by[1279]["n_rtt_obs"], by[1280]["n_rtt_obs"]))
    if 1281 in by and 1350 in by:
        add("1281 과 1350 이 같은 칸 (IPS +1 B와 +70 B의 임계 효과가 같음)",
            by[1281]["n_rtt_obs"] == by[1350]["n_rtt_obs"],
            "1281 n_rtt=%s / 1350 n_rtt=%s"
            % (by[1281]["n_rtt_obs"], by[1350]["n_rtt_obs"]))
    for r in out["rows"]:
        pass
    bad = [r for r in out["rows"]
           if r["first_flight_bytes"] not in (None, r["client_bytes"])]
    add("모든 설정에서 첫 비행 = k x ips", not bad,
        "어긋난 설정: %s" % [(r["ips"], r["first_flight_bytes"]) for r in bad])

    out["checks"] = checks
    out["passed"] = sum(1 for c in checks if c["ok"])
    out["total"] = len(checks)
    padbed.save("probe_cliff_%s.json" % GROUP, out)
    print()
    for c in checks:
        print("[%s] %s | %s" % ("OK " if c["ok"] else "FAIL",
                                c["check"], c["detail"]))
    print("%d/%d" % (out["passed"], out["total"]))
    return 0 if out["passed"] == out["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
