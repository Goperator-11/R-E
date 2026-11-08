from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import padbed

P = 1280
RTT_MS = 50.0

GROUP = sys.argv[1] if len(sys.argv) > 1 else "x25519"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 12

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
        S = sb_sorted[len(sb_sorted) // 2]
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
