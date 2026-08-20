# -*- coding: utf-8 -*-
"""P9 - 두 개의 서로 다른 실험 환경에서 같은 값이 나오는가.

같은 결론이 하네스에 의존하면 그건 하네스의 성질이지 QUIC 의 성질이 아니다.
그래서 완전히 다른 두 테스트베드에서 같은 것을 재고 대조한다.

  환경 A - 인수인계 문서 환경 (2차)
      qamp 한 바이너리가 quic.Transport{Conn: countConn} 으로 직결.
      netns `peer`, veth v0/v1, 포트 44433, /tmp/qamp.
      클라이언트와 서버 사이에 우리 프로세스가 **없다**.

  환경 B - 1차 연구 환경
      qclient --(UDP)--> shim tx --(veth)--> shim rx --(UDP)--> qserver
      netns `rx`, veth veth-tx/veth-rx, 포트 4433.
      클라이언트는 quic.DialAddr 를 쓰고(소켓을 라이브러리가 만든다),
      경로 한가운데에 파이썬 중계 프로세스가 두 개 끼어 있다.
      비행 묶기(3 ms), 1바이트 flight id 같은 이 환경 고유의 성질이 있다.

둘은 코드도, 프로세스 구조도, 네임스페이스·장치·포트 이름도 다르다.
그런데도 증폭 임계가 같은 칸에서 나오면, 그 임계는 우리 구현이 아니라
RFC 9000 8.1 과 quic-go 의 성질이다.

Output: experiments/results/p9_crossenv.json
"""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B                               # noqa: E402
import e20_amplification as E20                  # noqa: E402
from _journal import Journal, code_fingerprint   # noqa: E402

RTT_MS = 50.0
N_PROBE = 15
N_CONFIRM = 40
RESOLUTION = 100
LO, HI = 1500, 16000
GROUPS = [("x25519", 1), ("X25519MLKEM768", 2)]
TEAM = {"x25519": (3300, 3400), "X25519MLKEM768": (5900, 6000)}


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def teardown_all():
    """두 환경이 같은 주소를 쓰므로 갈아탈 때 완전히 걷어낸다."""
    for c in ("ip link del v0", "ip netns del peer",
              "ip link del veth-tx", "ip netns del rx"):
        sh(c)


# ------------------------------------------------------------ 환경 A (문서)
def probe_a(group, k, cert, n, jr):
    key = "A|%s|c%d|n%d" % (group, cert, n)
    if jr.has(key):
        return jr.get(key)
    B.set_netem(RTT_MS / 2.0)
    p, sp = B.start_server(cert, fec="off")
    rows, cs, err = B.run_client(group, n, fec="off", gap_ms=15, expect_k=k)
    B.stop_server(p)
    s = B.summarize(rows, rtt_ms=RTT_MS)
    rec = {"cert": cert, "ok": s["ok"], "n": s["n"],
           "two_rtt_rate": s["two_rtt_rate"], "p50": s["p50"],
           "first_flight_bytes": cs.get("first_flight_bytes")}
    if s["ok"] == s["n"]:
        jr.record(key, rec)
    return rec


# ------------------------------------------------------------ 환경 B (1차)
def probe_b(group, cert, n, jr):
    key = "B|%s|c%d|n%d" % (group, cert, n)
    if jr.has(key):
        return jr.get(key)
    procs = E20.start_stack("nofec", cert, 3.0)
    rows = E20.run_client(group, n, 15, 12)
    E20.stop_stack(procs)
    ok = [r["ms"] for r in rows if r.get("ok")]
    two = sum(1 for t in ok if t > 1.5 * RTT_MS)
    rec = {"cert": cert, "ok": len(ok), "n": len(rows),
           "two_rtt_rate": (two / float(len(ok))) if ok else None,
           "p50": sorted(ok)[len(ok) // 2] if ok else None}
    if rows and len(ok) == len(rows):
        jr.record(key, rec)
    return rec


def bisect(probe, log):
    lo, hi = LO, HI
    a, b = probe(lo, N_PROBE), probe(hi, N_PROBE)
    if not a.get("ok") or not b.get("ok"):
        return {"lo": None, "hi": None, "note": "경계에서 핸드셰이크 실패"}
    if (a["two_rtt_rate"] or 0) >= 0.5:
        return {"lo": None, "hi": lo, "note": "하한에서 이미 2-RTT"}
    if (b["two_rtt_rate"] or 0) < 0.5:
        return {"lo": hi, "hi": None, "note": "상한에서도 1-RTT"}
    while hi - lo > RESOLUTION:
        mid = (lo + hi) // 2
        r = probe(mid, N_PROBE)
        if not r.get("ok"):
            return {"lo": None, "hi": None, "note": "cert %d 에서 실패" % mid}
        rate = r["two_rtt_rate"] or 0.0
        if 0.2 < rate < 0.8:
            r = probe(mid, N_CONFIRM)
            rate = r["two_rtt_rate"] or 0.0
        if rate >= 0.5:
            hi = mid
        else:
            lo = mid
        log("      cert %-6d 2RTT %5.0f%%  ->  [%d, %d]"
            % (mid, 100 * rate, lo, hi))
    return {"lo": lo, "hi": hi, "note": ""}


def main():
    B.harden()
    B.require_root()

    def log(m):
        print(m)
        sys.stdout.flush()

    fp = code_fingerprint(["experiments/p9_crossenv.py",
                           "experiments/quicbed/qamp.go",
                           "experiments/quicbed/shim.py",
                           "experiments/padbed.py"], ROOT)
    jr = Journal(os.path.join(B.STATE, "p9_units.jsonl"), fp)

    out = {"rtt_ms": RTT_MS, "team": TEAM, "A": {}, "B": {}, "compare": []}

    # ------------------------------------------------------------ 환경 A
    log("=" * 100)
    log("환경 A - 인수인계 문서 환경 (qamp 직결, netns peer, v0/v1, :44433)")
    log("=" * 100)
    teardown_all()
    B.require_bin()
    B.setup()
    for group, k in GROUPS:
        log("  [%s]" % group)
        th = bisect(lambda c, n: probe_a(group, k, c, n, jr), log)
        ref = probe_a(group, k, 3000, N_PROBE, jr)
        out["A"][group] = {"threshold": [th["lo"], th["hi"]],
                           "note": th["note"],
                           "first_flight_bytes": ref.get("first_flight_bytes")}
        log("    => 임계 %s ~ %s B (첫 비행 %s B)"
            % (th["lo"], th["hi"], ref.get("first_flight_bytes")))

    # ------------------------------------------------------------ 환경 B
    log("")
    log("=" * 100)
    log("환경 B - 1차 연구 환경 (qclient -> 심 -> 심 -> qserver, "
        "netns rx, veth-tx/rx, :4433)")
    log("=" * 100)
    teardown_all()
    if not os.path.exists(os.path.join(E20.BIN, "qserver")):
        log("  qserver 가 없다 - 환경 B 를 건너뛴다")
    else:
        E20.setup()
        E20.set_delay(RTT_MS / 2.0)
        for group, _k in GROUPS:
            log("  [%s]" % group)
            th = bisect(lambda c, n: probe_b(group, c, n, jr), log)
            out["B"][group] = {"threshold": [th["lo"], th["hi"]],
                               "note": th["note"]}
            log("    => 임계 %s ~ %s B" % (th["lo"], th["hi"]))

    # ------------------------------------------------------------ 대조
    log("")
    log("=" * 100)
    log("두 환경 + 팀 자료 대조")
    log("=" * 100)
    log("%-16s %-18s %-18s %-16s %s"
        % ("그룹", "환경 A (문서)", "환경 B (1차)", "팀 자료", "판정"))
    allok = True
    for group, _k in GROUPS:
        a = out["A"].get(group, {}).get("threshold")
        b = out["B"].get(group, {}).get("threshold")
        t = TEAM.get(group)

        def ov(x, y):
            if not x or not y or x[0] is None or y[0] is None:
                return None
            return not (x[1] < y[0] or x[0] > y[1])

        ab, at, bt = ov(a, b), ov(a, t), ov(b, t)
        ok = all(v for v in (ab, at, bt) if v is not None)
        allok = allok and ok
        out["compare"].append({"group": group, "A": a, "B": b, "team": t,
                               "A_vs_B": ab, "A_vs_team": at,
                               "B_vs_team": bt, "ok": ok})
        log("%-16s %-18s %-18s %-16s %s"
            % (group,
               ("%s~%s" % (a[0], a[1])) if a else "-",
               ("%s~%s" % (b[0], b[1])) if b else "-",
               ("%d~%d" % t) if t else "-",
               "세 곳 모두 겹침" if ok else "불일치"))

    log("")
    log("결론: %s"
        % ("서로 다른 두 테스트베드와 다른 PC 의 팀 자료가 같은 칸을 가리킨다. "
           "임계는 우리 구현의 성질이 아니다."
           if allok else
           "환경에 따라 값이 다르다. 어느 쪽이 하네스 인공물인지 따로 봐야 한다."))
    out["all_agree"] = allok

    teardown_all()
    B.setup()          # 다음 단계를 위해 문서 환경으로 되돌려 둔다
    print("saved:", B.save("p9_crossenv.json", out))
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
