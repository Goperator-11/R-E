# -*- coding: utf-8 -*-
"""임시 탐침 — s0 를 임계에서 역산하지 말고 **직접 잰다**.

왜 필요한가
    명세 §2.5 는 s0 가 상수가 아니라 서버 패킷 수에 비례하는 항을 갖는다고 주장한다.
        s0(n) = s0_base + n * c ,  n = 서버 패킷 수 ,  c = 34.5 B
    그런데 그 c 는 그룹당 **2점**에서, 그것도 이분탐색 구간의 중점에서 나왔다.
    재감사가 정확히 짚었다 — **1 바이트 절벽 실험은 두 모형을 구분하지 못한다**
    (상수 s0 모형도 같은 10점을 똑같이 맞힌다). 구분하려면 다른 칸이 필요한데,
    ips 를 키우는 길은 막혔다: veth MTU 1500 + quic-go 가 InitialPacketSize 를
    1452 로 깎아서 x25519 는 칸 3·4, ML-KEM 은 칸 6·7 밖으로 못 나간다.

이 탐침의 착상
    임계는 잊는다. 클라이언트가 **서버에게서 받은 바이트**를 시행마다 기록하고 있다
    (`server_bytes`). 손실 0 이면 그 값이 곧 서버 비행 전체다. 그러면

        S(cert) = cert + s0        ->   s0 = S − cert

    를 **직접** 얻는다. cert 를 훑어 서버 패킷 수 n = ceil(S/P) 를 바꿔 가며
    s0 가 n 에 따라 계단을 밟는지 보면 두 모형이 갈린다.

두 모형의 예측 (x25519)
    상수 모형   : s0 = 500.0 (모든 cert)          -> S = cert + 500
    패킷항 모형 : s0 = 396.5 + n*34.5            -> S = cert + 396.5 + n*34.5
    cert=6000 에서 6,500 vs 6,603.5  (차 103.5 B)
    cert=12000 에서 12,500 vs 12,741.5 (차 241.5 B)
    `server_bytes` 는 정수 실측이라 이 차이는 잡음보다 훨씬 크다.

주의
    2-RTT 조건에서도 서버는 결국 같은 바이트를 다 보낸다(나눠 보낼 뿐).
    그래서 임계 위/아래를 가리지 않고 전 구간에서 잴 수 있다.

실행:  unshare -Urnm python3 experiments/_probe_s0.py [group] [n]
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import padbed  # noqa: E402

P = 1280
RTT_MS = 50.0

GROUP = sys.argv[1] if len(sys.argv) > 1 else "x25519"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 12

# 명세 §2.5 의 두 모형
CONST_S0 = {"x25519": 500.0, "X25519MLKEM768": 1734.5}
BASE_S0 = {"x25519": 396.5, "X25519MLKEM768": 1527.5}
C_PKT = 34.5

CERTS = [1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000,
         9000, 10000, 11000, 12000]


def main():
    padbed.harden()
    padbed.require_root()
    padbed.require_bin()
    padbed.setup(mtu=1500)
    padbed.set_netem(RTT_MS / 2.0, 0.0, 0.0)

    out = {"group": GROUP, "rtt_ms": RTT_MS, "n": N, "rows": []}
    print("cert    S(서버바이트)  n_pkt  s0_실측   상수예측  패킷항예측  "
          "상수오차  패킷항오차", flush=True)
    for cert in CERTS:
        srv = None
        try:
            srv, spath = padbed.start_server(cert, fec="off")
            rows, _cs, err = padbed.run_client(
                GROUP, N, fec="off", ips=0, gap_ms=25, timeout_s=12)
        finally:
            padbed.stop_server(srv)
        sb = [r.get("server_bytes") for r in rows
              if r.get("ok") and r.get("server_bytes")]
        if not sb:
            out["rows"].append({"cert": cert, "err": err or "no server_bytes"})
            print("%-8d(측정 실패: %s)" % (cert, err or "server_bytes 없음"),
                  flush=True)
            continue
        sb_sorted = sorted(sb)
        S = sb_sorted[len(sb_sorted) // 2]          # 중앙값
        spread = sb_sorted[-1] - sb_sorted[0]
        s0_obs = S - cert
        n_pkt = int(math.ceil(float(S) / P))
        pred_const = CONST_S0[GROUP]
        pred_pkt = BASE_S0[GROUP] + n_pkt * C_PKT
        rec = {"cert": cert, "S": S, "spread": spread, "n_ok": len(sb),
               "n_pkt": n_pkt, "s0_obs": s0_obs,
               "s0_const": pred_const, "s0_pkt": pred_pkt,
               "err_const": s0_obs - pred_const,
               "err_pkt": s0_obs - pred_pkt}
        out["rows"].append(rec)
        print("%-8d%-14d%-7d%-10.1f%-10.1f%-12.1f%-10.1f%-10.1f"
              % (cert, S, n_pkt, s0_obs, pred_const, pred_pkt,
                 rec["err_const"], rec["err_pkt"]), flush=True)

    good = [r for r in out["rows"] if "s0_obs" in r]
    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    if good:
        mae_c = sum(abs(r["err_const"]) for r in good) / len(good)
        mae_p = sum(abs(r["err_pkt"]) for r in good) / len(good)
        out["mae_const"] = mae_c
        out["mae_pkt"] = mae_p
        add("패킷항 모형이 상수 모형보다 정확하다", mae_p < mae_c,
            "평균절대오차 상수 %.1f B vs 패킷항 %.1f B" % (mae_c, mae_p))

        # s0 가 n 에 따라 실제로 커지는가 (모형 무관, 자료만 본다)
        by_n = {}
        for r in good:
            by_n.setdefault(r["n_pkt"], []).append(r["s0_obs"])
        ns = sorted(by_n)
        out["s0_by_n"] = {str(k): by_n[k] for k in ns}
        if len(ns) >= 2:
            means = [(k, sum(by_n[k]) / len(by_n[k])) for k in ns]
            inc = all(means[i + 1][1] >= means[i][1] - 1.0
                      for i in range(len(means) - 1))
            add("s0 가 서버 패킷 수에 대해 단조 증가", inc,
                " / ".join("n=%d: %.1f" % (k, v) for k, v in means))
            slope = ((means[-1][1] - means[0][1])
                     / float(means[-1][0] - means[0][0]))
            out["slope_per_pkt"] = slope
            add("패킷당 증분이 0 이 아니다 (상수 모형 기각)",
                abs(slope) > 5.0,
                "실측 기울기 %.1f B/패킷 (패킷항 모형 예측 %.1f)"
                % (slope, C_PKT))
        # 같은 n 안에서는 s0 가 일정해야 한다
        flat = all(max(v) - min(v) <= 2.0 for v in by_n.values() if len(v) > 1)
        add("같은 패킷 수 안에서는 s0 가 일정", flat,
            " / ".join("n=%d 폭 %.1f" % (k, max(by_n[k]) - min(by_n[k]))
                       for k in ns if len(by_n[k]) > 1))

    out["checks"] = checks
    out["passed"] = sum(1 for c in checks if c["ok"])
    out["total"] = len(checks)
    padbed.save("probe_s0_%s.json" % GROUP, out)
    print()
    for c in checks:
        print("[%s] %s | %s" % ("OK " if c["ok"] else "FAIL",
                                c["check"], c["detail"]))
    print("%d/%d" % (out["passed"], out["total"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
