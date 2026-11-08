import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import padbed
from padfec import policy, quantum

RTT_MS = 50.0
N = 200
WARMUP = 20
GROUP = "x25519"
K = 1
IPS = 1280
S0_BASE, C_PKT = 396.5, 34.5

CERTS = [2308, 4032]

LOSSES = [("0", 0.0, 1.0),
          ("2%", 0.02, 1.0),
          ("5%", 0.05, 1.0),
          ("gemodel 5% 50%", 0.05, 2.0)]

ARMS = [("off", 0), ("fec", 1), ("fec", 2)]


def s0_pred(client_bytes):
    a = quantum.allowed(client_bytes)
    return S0_BASE + (a // 1280) * C_PKT


def _binom(n, k, q):
    if k < 0 or k > n:
        return 0.0
    c = 1.0
    for i in range(k):
        c = c * float(n - i) / float(i + 1)
    return c * (q ** k) * ((1.0 - q) ** (n - k))


def j_old(k, m, w, p, burst, server_flight, rtt):
    parity = policy.parity_datagram_bytes(w, k)
    q = 1.0 - p
    n = 0.0
    for i in range(k + 1):
        pi = _binom(k, i, q)
        for j in range(m + 1):
            pj = _binom(m, j, q)
            arrived = i * w + j * parity
            n += pi * pj * (2.0 if server_flight > quantum.allowed(arrived)
                            else 1.0)
    pf = policy.p_fail_of({"k": k, "m": m}, p, burst)
    tx = policy.tx_cost_ms(m * parity, 10.0)
    return n * rtt + pf * rtt + tx


def j_new(k, m, w, p, burst, server_flight, rtt):
    e = policy.cost_of_v2({"k": k, "m": m, "W_eff": w,
                           "server_flight": server_flight,
                           "n_need":
                               policy.n_need_for_flight(server_flight)},
                          w, rtt, p, burst, k0=k)
    return e["j_ms"]


def main():
    padbed.harden()
    padbed.require_root()
    padbed.require_bin()
    padbed.setup(mtu=1500)

    out = {"rtt_ms": RTT_MS, "n": N, "warmup": WARMUP, "group": GROUP,
           "ips": IPS, "cpu_list": padbed.CPU_LIST, "rows": []}

    for cert in CERTS:
        sf = cert + s0_pred(K * IPS)
        srv = None
        try:
            srv, _ = padbed.start_server(cert, fec="fec")
            for lname, p, burst in LOSSES:
                padbed.set_netem(RTT_MS / 2.0, loss_c2s=p * 100.0,
                                 loss_s2c=0.0, burst_len=burst)
                for fec, m in ARMS:
                    t0 = time.time()
                    rows, _st, err = padbed.run_client(
                        GROUP, N, fec=fec, m=m, ips=IPS,
                        gap_ms=20, timeout_s=10, warmup=WARMUP)
                    summ = padbed.summarize(rows, rtt_ms=RTT_MS)
                    rec = {
                        "cert": cert, "loss": lname, "p": p, "burst": burst,
                        "arm": ("off" if fec == "off" else "m=%d" % m),
                        "m": m if fec != "off" else 0,
                        "n_ok": summ.get("ok"), "n": summ.get("n"),
                        "mean": summ.get("mean"), "p50": summ.get("p50"),
                        "p95": summ.get("p95"),
                        "two_rtt_rate": summ.get("two_rtt_rate"),
                        "err": err, "secs": round(time.time() - t0, 1),
                    }
                    mm = rec["m"]
                    rec["j_old"] = round(j_old(K, mm, IPS, p, burst, sf,
                                               RTT_MS), 3)
                    rec["j_new"] = round(j_new(K, mm, IPS, p, burst, sf,
                                               RTT_MS), 3)
                    out["rows"].append(rec)
                    print("cert=%-5d loss=%-15s %-4s | 실측 mean=%-8s p50=%-8s "
                          "2rtt=%-5s | J_old=%-8.2f J_new=%-8.2f (%ss)"
                          % (cert, lname, rec["arm"], rec["mean"], rec["p50"],
                             rec["two_rtt_rate"], rec["j_old"], rec["j_new"],
                             rec["secs"]), flush=True)
        finally:
            padbed.stop_server(srv)

    print()
    print("=== 팔 순위: 실측 vs 두 모형 ===")
    checks = []
    by = {}
    for r in out["rows"]:
        by.setdefault((r["cert"], r["loss"]), []).append(r)
    for key, rs in sorted(by.items()):
        rs = [r for r in rs if r["mean"] is not None]
        if len(rs) < 2:
            continue
        obs = [r["arm"] for r in sorted(rs, key=lambda r: r["mean"])]
        old = [r["arm"] for r in sorted(rs, key=lambda r: r["j_old"])]
        new = [r["arm"] for r in sorted(rs, key=lambda r: r["j_new"])]
        ok_new = obs[0] == new[0]
        ok_old = obs[0] == old[0]
        checks.append({"cond": "cert=%s loss=%s" % key, "obs": obs,
                       "old": old, "new": new,
                       "new_best_matches": ok_new, "old_best_matches": ok_old})
        print("  cert=%-5s loss=%-15s 실측 %-22s | 옛 %-22s %s | 새 %-22s %s"
              % (key[0], key[1], ">".join(obs), ">".join(old),
                 "O" if ok_old else "X", ">".join(new), "O" if ok_new else "X"))
    n_new = sum(1 for c in checks if c["new_best_matches"])
    n_old = sum(1 for c in checks if c["old_best_matches"])
    print()
    print("최적 팔을 맞힌 조건 수:  옛 식 %d/%d,  새 식 %d/%d"
          % (n_old, len(checks), n_new, len(checks)))
    out["ranking"] = checks
    out["summary"] = {"conditions": len(checks), "old_correct": n_old,
                      "new_correct": n_new}

    dst = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "probe_losstest.json")
    with open(dst, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("wrote", dst)


if __name__ == "__main__":
    main()
