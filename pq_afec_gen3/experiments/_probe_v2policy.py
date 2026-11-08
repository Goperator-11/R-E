import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import padbed

RTT_MS = 50.0
CERT = 4032
IPS = 1280
N = 400
CACHE = "/tmp/padfec/v2cache.json"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "results", "probe_v2policy.json")


def main():
    padbed.harden()
    padbed.require_root()
    padbed.require_bin()
    padbed.setup(mtu=1500)
    padbed.set_netem(RTT_MS / 2.0, 0.0, 0.0)

    try:
        os.unlink(CACHE)
    except OSError:
        pass

    out = {"rtt_ms": RTT_MS, "cert": CERT, "ips_base": IPS, "n": N, "arms": []}
    srv = None
    try:
        srv, _ = padbed.start_server(CERT, fec="fec")
        for label, fec, extra in (
            ("기준선 off (ips 1280)", "off", []),
            ("사람이 준 ips 1281", "off", []),
            ("auto (v2 정책)", "auto", ["-cache", CACHE, "-probe-every", "20"]),
        ):
            ips = 1281 if label.startswith("사람") else IPS
            rows, _st, err = padbed.run_client(
                "x25519", N, fec=fec, m=1, ips=ips, gap_ms=20,
                timeout_s=12, warmup=0, extra=extra)
            s = padbed.summarize(rows, rtt_ms=RTT_MS)
            used = Counter(r.get("ips_used") for r in rows)
            musd = Counter(r.get("m_used") for r in rows)
            tail = rows[len(rows) // 2:]
            st = padbed.summarize(tail, rtt_ms=RTT_MS)
            rec = {"arm": label, "err": err, "n": s.get("n"),
                   "p50": s.get("p50"), "two_rtt_rate": s.get("two_rtt_rate"),
                   "tail_p50": st.get("p50"),
                   "tail_two_rtt": st.get("two_rtt_rate"),
                   "ips_used": dict(used), "m_used": dict(musd),
                   "why_last": rows[-1].get("m_why") if rows else None}
            out["arms"].append(rec)
            print("%-22s p50=%-9s 2rtt=%-6s | 뒤절반 p50=%-9s 2rtt=%-6s "
                  "| ips=%s m=%s"
                  % (label, rec["p50"], rec["two_rtt_rate"], rec["tail_p50"],
                     rec["tail_two_rtt"], dict(used), dict(musd)), flush=True)
            if rec["why_last"]:
                print("    마지막 판단: %s" % rec["why_last"], flush=True)
    finally:
        padbed.stop_server(srv)

    print()
    print("=== 판정 ===")
    by = {a["arm"]: a for a in out["arms"]}
    base = by["기준선 off (ips 1280)"]
    manual = by["사람이 준 ips 1281"]
    auto = by["auto (v2 정책)"]
    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print("  [%s] %s | %s" % ("OK " if ok else "FAIL", name, detail))

    def rate(a, key, miss):
        v = a.get(key)
        return miss if v is None else v

    add("기준선(ips 1280)은 2-RTT", rate(base, "two_rtt_rate", 0) > 0.9,
        "2rtt=%s p50=%s" % (base["two_rtt_rate"], base["p50"]))
    add("사람이 준 1281 은 1-RTT", rate(manual, "two_rtt_rate", 1) < 0.1,
        "2rtt=%s p50=%s" % (manual["two_rtt_rate"], manual["p50"]))
    add("auto 가 스스로 ips=1281 을 골랐다", 1281 in auto["ips_used"],
        "쓴 ips: %s" % auto["ips_used"])
    add("auto 뒤절반이 1-RTT", rate(auto, "tail_two_rtt", 1) < 0.1,
        "뒤절반 2rtt=%s p50=%s" % (auto["tail_two_rtt"], auto["tail_p50"]))
    if base["p50"] and auto["tail_p50"]:
        d = base["p50"] - auto["tail_p50"]
        add("정책이 스스로 왕복 하나를 벌었다 (>= 0.8 RTT)", d >= 0.8 * RTT_MS,
            "%.2f ms = %.3f RTT" % (d, d / RTT_MS))
    add("무손실에서 패리티 없이(m=0) 도는 판이 다수",
        auto["m_used"].get(0, 0) > N // 2, "m 분포: %s" % auto["m_used"])

    n_ok = sum(1 for c in checks if c["ok"])
    print()
    print("  %d/%d" % (n_ok, len(checks)))
    out["checks"] = checks

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("wrote", OUT)
    return 0 if n_ok == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
