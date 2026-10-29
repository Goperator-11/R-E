# -*- coding: utf-8 -*-
"""v2 정책 실측 - 정책이 **스스로** δ 를 골라 왕복 하나를 사는가.

이식 전에는 `-fec auto` 가 m 만 골랐다. 헤드라인("1 바이트로 왕복 하나")은
사람이 `-ips 1281` 을 직접 줄 때만 실현됐다 - 정책이 그 자리를 스스로 찾은
적이 한 번도 없었다. 이 시험은 결정을 정책의 손에 넘긴 뒤, **아무 힌트 없이
빈 캐시에서 시작해서** 정책이 그 자리를 찾아가는지 본다.

설계
    인증서를 두 예측 임계 사이에 고정한다(x25519: 3340 < cert < 4585.5).
    이 자리에서는 ips=1280 이 2-RTT 이고 1281 이 1-RTT 다.

    A 기준선   -fec off, ips 1280   -> 2-RTT 여야 한다
    B 사람 손   -fec off, ips 1281   -> 1-RTT 여야 한다 (헤드라인의 상한)
    C auto     정책이 스스로         -> B 에 닿아야 한다

🩸 마지막 검사("무손실인데 m=0 이 다수인가")가 **일부러 빡빡하다.** C 가
   1-RTT 를 달성하는 방법은 두 가지다 - δ 로 1 바이트를 더 보내거나, 패리티
   2 개(2,636 B)를 사서 그 바이트로 칸을 올리거나. 둘 다 왕복은 벌지만 값이
   2,600 배 다르다. 왕복 수만 보면 이 차이가 안 보이므로 m 분포를 따로 본다.
   (2026-08-20 실측: 5/6 통과, 이 항목만 실패 - 손실률 추정이 아직 참값에서
   멀어 패리티가 이겼다. 수렴은 _probe_v2converge.py 가 따로 잰다.)

실행: unshare -Urnm python3 experiments/_probe_v2policy.py
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import padbed   # noqa: E402

RTT_MS = 50.0
CERT = 4032          # 명세 4-4 Tranco p50. 예측 임계 3340 < 4032 < 4585.5
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

    # 빈 캐시에서 시작한다 - "아무 힌트 없이" 가 이 시험의 전제다.
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
            # 콜드스타트 이후(뒤 절반)만 따로 본다 - 정책이 배운 뒤의 상태다.
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
