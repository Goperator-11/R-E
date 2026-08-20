# -*- coding: utf-8 -*-
"""T_recover 가 RTT 에 비례하는가, 고정 상수인가.

이 물음이 기본값을 어떻게 고쳐야 하는지를 정한다.
  - RTT 에 비례하면  -> t_recover = c * rtt  (지금 형태를 계수만 고치면 된다)
  - 고정 상수면      -> t_recover = 상수      (RTT 배수로 쓰는 것 자체가 틀렸다)

k=1(전멸 -> ACK 없음 -> PTO)과 k=2(부분 도착 -> ACK -> 즉시 재전송)를
RTT 3점에서 각각 잰다.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import padbed   # noqa: E402

N = 40
WARMUP = 8
CERT = 2308
IPS = 1280
RTTS = [10.0, 50.0, 100.0]

padbed.harden()
padbed.require_root()
padbed.require_bin()
padbed.setup(mtu=1500)

out = {"cert": CERT, "ips": IPS, "n": N, "rows": []}
srv = None
try:
    srv, _ = padbed.start_server(CERT, fec="off")
    for rtt in RTTS:
        padbed.set_netem(rtt / 2.0, 0.0, 0.0)
        for group, k in (("x25519", 1), ("X25519MLKEM768", 2)):
            base = padbed.summarize(
                padbed.run_client(group, N, fec="off", ips=IPS, gap_ms=20,
                                  timeout_s=15, warmup=WARMUP)[0],
                rtt_ms=rtt)
            drop = padbed.summarize(
                padbed.run_client(group, N, fec="off", ips=IPS, gap_ms=20,
                                  timeout_s=15, warmup=WARMUP,
                                  extra=["-drop-initial", "0"])[0],
                rtt_ms=rtt)
            if not (base.get("p50") and drop.get("p50")):
                print("  RTT=%s %s : 표본 부족" % (rtt, group))
                continue
            t = drop["p50"] - base["p50"]
            rec = {"rtt_ms": rtt, "group": group, "k": k,
                   "base_p50": base["p50"], "drop_p50": drop["p50"],
                   "t_recover_ms": t, "t_recover_rtt": t / rtt}
            out["rows"].append(rec)
            print("RTT=%-6.0f %-16s k=%d | 기준 %8.2f -> 소거 %8.2f | "
                  "T_rec = %8.2f ms = %5.2f RTT"
                  % (rtt, group, k, base["p50"], drop["p50"], t, t / rtt),
                  flush=True)
finally:
    padbed.stop_server(srv)

print()
print("=== 판정 ===")
for k, label in ((1, "k=1 (전멸 -> ACK 없음 -> PTO)"),
                 (2, "k=2 (부분 도착 -> ACK -> 즉시 재전송)")):
    rs = [r for r in out["rows"] if r["k"] == k]
    if len(rs) < 2:
        continue
    ms = [r["t_recover_ms"] for r in rs]
    mult = [r["t_recover_rtt"] for r in rs]
    spread_ms = (max(ms) - min(ms)) / (sum(ms) / len(ms))
    spread_x = (max(mult) - min(mult)) / (sum(mult) / len(mult))
    verdict = ("고정 상수에 가깝다" if spread_ms < spread_x
               else "RTT 에 비례한다")
    print("  %s" % label)
    print("    절대값 %s ms   (상대폭 %.2f)"
          % ("/".join("%.1f" % x for x in ms), spread_ms))
    print("    RTT 배수 %s     (상대폭 %.2f)"
          % ("/".join("%.2f" % x for x in mult), spread_x))
    print("    -> %s" % verdict)
    out.setdefault("verdict", {})[str(k)] = verdict

dst = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "probe_trecover_rtt.json"
with open(dst, "w") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print("wrote", dst)
