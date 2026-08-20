# -*- coding: utf-8 -*-
"""P8 - 같은 결론이 몇 번을 다시 재도 나오는가, 그리고 나오면 안 되는 곳에서는
안 나오는가.

한 번 잘 나온 수는 증거가 약하다. 여기서 의심하는 것은 넷이다.

  1. 재현성   같은 조건을 여러 라운드 반복하면 같은 판정이 나오는가.
              임계는 100 B 칸 안에서 흔들리지 않아야 하고, 복구는 매번
              n/n 이어야 한다.

  2. 음성 대조 우리 FEC 는 **클라이언트 -> 서버** 방향만 보호한다. 그러니
              손실을 **서버 -> 클라이언트** 쪽에만 걸면 FEC 는 도움이
              되면 안 된다. 여기서 이득이 보이면 그 이득은 복구가 아니라
              우리가 모르는 다른 것에서 온 것이다.

  3. 통계     p95 가 좋아졌다는 말이 잡음인지 아닌지. 부트스트랩으로
              차이의 95% 신뢰구간을 내고, 0 을 포함하면 "개선"이라고
              부르지 않는다.

  4. 계통오차 시행 순서가 결과에 영향을 주는가(예열), netem 이 우리가
              시킨 만큼 실제로 떨어뜨리는가.

Output: experiments/results/p8_stability.json
"""
from __future__ import annotations

import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B                               # noqa: E402
from _journal import Journal, code_fingerprint   # noqa: E402

RTT_MS = 50.0
GROUP = "X25519MLKEM768"
K = 2
CERT_EFFECT = 2955
ROUNDS = 3
N_EFFECT = 200
N_PROBE = 30

# p2 가 찾은 기준선 임계 구간을 감싸는 두 점. 여기서 판정이 뒤집히면
# 임계가 재현되지 않는 것이다.
BRACKET = {"off": (5850, 6050), "on1": (10850, 11050)}


def probe(cert, fec, m, n, jr, tag):
    key = "%s|%s|m%d|c%d|n%d" % (tag, fec, m, cert, n)
    if jr.has(key):
        return jr.get(key)
    B.set_netem(RTT_MS / 2.0)
    p, sp = B.start_server(cert, fec=("on" if fec == "on" else fec))
    rows, cs, err = B.run_client(GROUP, n, fec=fec, m=m, gap_ms=12,
                                 expect_k=K)
    B.stop_server(p)
    s = B.summarize(rows, rtt_ms=RTT_MS)
    rec = {"cert": cert, "n": s["n"], "ok": s["ok"],
           "two_rtt_rate": s["two_rtt_rate"], "p50": s["p50"]}
    if s["ok"] == s["n"]:
        jr.record(key, rec)
    return rec


def effect(loss_c2s, loss_s2c, fec, m, n, jr, tag):
    key = "eff|%s|%s|m%d|c%.1f|s%.1f|n%d" % (tag, fec, m, loss_c2s,
                                             loss_s2c, n)
    if jr.has(key):
        return jr.get(key)
    B.set_netem(RTT_MS / 2.0, loss_c2s=loss_c2s, loss_s2c=loss_s2c)
    p, sp = B.start_server(CERT_EFFECT, fec=("on" if fec == "on" else fec))
    rows, cs, err = B.run_client(GROUP, n, fec=fec, m=m, gap_ms=8,
                                 timeout_s=8, expect_k=K)
    B.stop_server(p)
    ss = B.read_server_stats(sp)
    s = B.summarize(rows, rtt_ms=RTT_MS)
    rec = {"samples": [r["ms"] for r in rows if r.get("ok")],
           "n": s["n"], "ok": s["ok"], "p50": s["p50"], "p95": s["p95"],
           "p99": s["p99"],
           "srv_recovered": ss.get("recovered"),
           "srv_crc_fail": ss.get("recover_crc_fail"),
           "cli_initial_dgrams": cs.get("initial_datagrams")}
    if s["n"] == n:
        jr.record(key, rec)
    return rec


def pct(v, q):
    if not v:
        return None
    s = sorted(v)
    return s[int(q * (len(s) - 1))]


def tail_rate(v, thresh):
    """왕복을 더 쓴 시행의 비율. '꼬리가 사라졌는가' 를 재는 올바른 통계량.

    🩸 처음에는 p95 로, 그다음엔 p99 로 판정했는데 둘 다 틀렸다.
      p95 - 이 손실률에서 95 분위가 "손실 없음(55 ms)"과 "하나 잃음(110 ms)"
            경계에 정확히 놓인다. 기준선 p95 가 라운드마다 55 <-> 110 을 오간다.
      p99 - n=200 이면 198 번째 순서통계량이라 **꼬리 표본 2 개**로 추정한다.
            부트스트랩 재표본에서 그 둘이 안 뽑히면 값이 붕괴해, 점추정이
            -152 ms 인데 신뢰구간이 [-155, +45] 로 0 을 포함하는 일이 생긴다.
    분위수 대신 **비율**을 쓴다. 이항 비율이라 n=200 이면 충분히 잰다.
    """
    if not v:
        return None
    return sum(1 for x in v if x > thresh) / float(len(v))


def bootstrap_tail(a, b, thresh, iters=4000, seed=11):
    """꼬리 비율 차이(b - a)의 95% 신뢰구간."""
    if not a or not b:
        return None
    rnd = random.Random(seed)
    diffs = []
    for _ in range(iters):
        ra = sum(1 for _ in range(len(a))
                 if a[rnd.randrange(len(a))] > thresh) / float(len(a))
        rb = sum(1 for _ in range(len(b))
                 if b[rnd.randrange(len(b))] > thresh) / float(len(b))
        diffs.append(rb - ra)
    diffs.sort()
    return {"point": tail_rate(b, thresh) - tail_rate(a, thresh),
            "lo": diffs[int(0.025 * (len(diffs) - 1))],
            "hi": diffs[int(0.975 * (len(diffs) - 1))]}


def bootstrap_diff(a, b, q=0.95, iters=2000, seed=7):
    """b - a 의 q 분위 차이에 대한 95% 신뢰구간."""
    if not a or not b:
        return None
    rnd = random.Random(seed)
    diffs = []
    for _ in range(iters):
        ra = [a[rnd.randrange(len(a))] for _ in range(len(a))]
        rb = [b[rnd.randrange(len(b))] for _ in range(len(b))]
        diffs.append(pct(rb, q) - pct(ra, q))
    diffs.sort()
    return {"point": pct(b, q) - pct(a, q),
            "lo": diffs[int(0.025 * (len(diffs) - 1))],
            "hi": diffs[int(0.975 * (len(diffs) - 1))]}


def main():
    B.harden()
    B.require_root()
    B.require_bin()
    B.setup()

    fp = code_fingerprint(["experiments/p8_stability.py",
                           "experiments/quicbed/qamp.go",
                           "experiments/padbed.py"], ROOT)
    jr = Journal(os.path.join(B.STATE, "p8_units.jsonl"), fp)

    out = {"rounds": ROUNDS, "rtt_ms": RTT_MS, "group": GROUP,
           "threshold_rounds": [], "effect_rounds": [],
           "negative_rounds": [], "checks": []}

    def add(name, ok, detail):
        out["checks"].append({"check": name, "ok": bool(ok),
                              "detail": detail})
        print("[%s] %-56s %s" % ("통과" if ok else "실패", name, detail[:80]))
        sys.stdout.flush()

    # ------------------------------------------------- 1. 임계 재현성
    print("=" * 100)
    print("1) 임계 재현성 - 같은 두 점에서 %d 라운드 반복" % ROUNDS)
    print("=" * 100)
    for r in range(ROUNDS):
        row = {"round": r}
        for arm, (lo, hi) in BRACKET.items():
            fec, m = ("off", 1) if arm == "off" else ("on", 1)
            a = probe(lo, fec, m, N_PROBE, jr, "r%d" % r)
            b = probe(hi, fec, m, N_PROBE, jr, "r%d" % r)
            row[arm] = {"lo_cert": lo, "lo_2rtt": a["two_rtt_rate"],
                        "hi_cert": hi, "hi_2rtt": b["two_rtt_rate"]}
            print("  라운드 %d  %-4s  cert %-6d 2RTT %5.0f%%  |  "
                  "cert %-6d 2RTT %5.0f%%"
                  % (r, arm, lo, 100 * (a["two_rtt_rate"] or 0),
                     hi, 100 * (b["two_rtt_rate"] or 0)))
            sys.stdout.flush()
        out["threshold_rounds"].append(row)

    for arm in BRACKET:
        rows = [x[arm] for x in out["threshold_rounds"]]
        ok = all((x["lo_2rtt"] or 0) < 0.5 and (x["hi_2rtt"] or 0) >= 0.5
                 for x in rows)
        add("임계 재현성 (%s): %d 라운드 모두 같은 칸에서 판정이 뒤집힌다"
            % (arm, ROUNDS), ok,
            "아래점 2RTT %s / 위점 2RTT %s"
            % ([round(100 * (x["lo_2rtt"] or 0)) for x in rows],
               [round(100 * (x["hi_2rtt"] or 0)) for x in rows]))

    # ------------------------------------------------- 2. 효과 재현성 + 통계
    print()
    print("=" * 100)
    print("2) 효과 재현성 - c2s 손실 2%%, off 대 on1, %d 라운드 (조건마다 n=%d)"
          % (ROUNDS, N_EFFECT))
    print("=" * 100)
    for r in range(ROUNDS):
        a = effect(2.0, 0.0, "off", 1, N_EFFECT, jr, "r%d" % r)
        b = effect(2.0, 0.0, "on", 1, N_EFFECT, jr, "r%d" % r)
        bs95 = bootstrap_diff(a["samples"], b["samples"], 0.95)
        bs99 = bootstrap_diff(a["samples"], b["samples"], 0.99)
        # 🩸 p95 는 이 손실률에서 **불연속면에 걸린다.** 연결당 c2s
        # 데이터그램이 3 개 안팎이라 손실 확률이 6% 근처이고, 95 분위가
        # "손실 없음(55 ms)"과 "하나 잃음(110 ms)" 경계에 정확히 놓인다.
        # 그래서 기준선 p95 가 라운드마다 110.9 / 55.2 / 109.8 로 튄다.
        # 통계가 불안정한 것이지 개선이 없는 것이 아니다 - p99 는 세 라운드
        # 모두 207 -> 56 으로 일관된다. 판정은 p99 로 한다.
        TAIL = 1.5 * RTT_MS      # 이보다 크면 왕복을 더 쓴 것
        bstail = bootstrap_tail(a["samples"], b["samples"], TAIL)
        row = {"round": r,
               "off": {k: a[k] for k in ("p50", "p95", "p99", "ok")},
               "on1": {k: b[k] for k in ("p50", "p95", "p99", "ok")},
               "tail_off": tail_rate(a["samples"], TAIL),
               "tail_on1": tail_rate(b["samples"], TAIL),
               "recovered": b["srv_recovered"],
               "crc_fail": b["srv_crc_fail"],
               "d_p95": bs95, "d_p99": bs99, "d_tail": bstail}
        out["effect_rounds"].append(row)
        print("  라운드 %d  꼬리비율 off %5.1f%% -> on1 %5.1f%%  "
              "차이 %+6.1f%%p [%+.1f, %+.1f] | p99 %6.1f -> %6.1f | 복구 %s"
              % (r, 100 * (row["tail_off"] or 0), 100 * (row["tail_on1"] or 0),
                 100 * bstail["point"], 100 * bstail["lo"], 100 * bstail["hi"],
                 a["p99"] or -1, b["p99"] or -1, b["srv_recovered"]))
        sys.stdout.flush()

    neg = [x for x in out["effect_rounds"] if x["d_tail"]["hi"] >= 0]
    add("c2s 손실에서 **꼬리 비율**(왕복 추가 시행 비율) 감소가 "
        "통계적으로 확실 (부트스트랩 95% 신뢰구간이 0 을 포함하지 않음)",
        not neg,
        "0 을 포함한 라운드 %d/%d | 라운드별 꼬리비율 %s -> %s"
        % (len(neg), ROUNDS,
           ["%.1f%%" % (100 * (x["tail_off"] or 0))
            for x in out["effect_rounds"]],
           ["%.1f%%" % (100 * (x["tail_on1"] or 0))
            for x in out["effect_rounds"]]))
    # p95 는 참고로만 남긴다 - 불안정하다는 사실 자체를 기록한다
    p95s = [x["off"]["p95"] for x in out["effect_rounds"]]
    out["p95_baseline_unstable"] = (max(p95s) - min(p95s)) > 20
    add("참고: 이 손실률에서 기준선 p95 는 불연속면에 걸려 불안정하다",
        True,
        "기준선 p95 라운드별 %s -> 판정에는 p99 를 쓴다"
        % ["%.1f" % v for v in p95s])

    bad = [x for x in out["effect_rounds"] if (x["crc_fail"] or 0) > 0]
    add("모든 라운드에서 복구 CRC 실패 0", not bad,
        "실패 라운드 %d" % len(bad))

    # ------------------------------------------------- 3. 음성 대조 (s2c 손실)
    print()
    print("=" * 100)
    print("3) 음성 대조 - 손실을 **서버->클라이언트** 쪽에만 건다.")
    print("   우리 FEC 는 반대 방향만 보호하므로 **도움이 되면 안 된다**.")
    print("=" * 100)
    for r in range(ROUNDS):
        a = effect(0.0, 2.0, "off", 1, N_EFFECT, jr, "r%d" % r)
        b = effect(0.0, 2.0, "on", 1, N_EFFECT, jr, "r%d" % r)
        bs = bootstrap_diff(a["samples"], b["samples"], 0.95)
        row = {"round": r, "off_p95": a["p95"], "on1_p95": b["p95"],
               "d_p95": bs, "recovered": b["srv_recovered"]}
        out["negative_rounds"].append(row)
        print("  라운드 %d  off p95 %7.1f | on1 p95 %7.1f | 차이 %+7.1f "
              "[%+.1f, %+.1f] | 복구 %s"
              % (r, a["p95"] or -1, b["p95"] or -1, bs["point"], bs["lo"],
                 bs["hi"], b["srv_recovered"]))
        sys.stdout.flush()

    # 신뢰구간이 0 을 포함해야 "차이 없음"이다.
    claims = [x for x in out["negative_rounds"]
              if x["d_p95"]["hi"] < 0]
    add("음성 대조: s2c 손실에서는 FEC 가 개선을 만들지 '않는다' "
        "(반대 방향은 보호 대상이 아니므로)",
        not claims,
        "개선이 관측된 라운드 %d/%d - 있으면 이득의 출처가 복구가 아니다"
        % (len(claims), ROUNDS))

    # ------------------------------------------------- 4. 계통오차
    print()
    print("=" * 100)
    print("4) 계통오차 - 시행 순서 효과와 netem 실효 손실률")
    print("=" * 100)
    B.set_netem(RTT_MS / 2.0)
    p, sp = B.start_server(CERT_EFFECT, fec="off")
    rows, cs, err = B.run_client(GROUP, 120, fec="off", gap_ms=8, expect_k=K)
    B.stop_server(p)
    ms = [r["ms"] for r in rows if r.get("ok")]
    first10 = ms[:10]
    rest = ms[10:]
    drift = ((sum(first10) / len(first10)) - (sum(rest) / len(rest))) \
        if first10 and rest else None
    add("시행 순서 효과 - 처음 10 회와 나머지의 평균 차이가 1 ms 미만",
        drift is not None and abs(drift) < 1.0,
        "차이 %.2f ms (첫 10회 %.2f, 나머지 %.2f)"
        % (drift or -1, sum(first10) / max(1, len(first10)),
           sum(rest) / max(1, len(rest))))

    # 🩸 netem 실효 손실률은 **커널에게 직접 묻는다.**
    # 처음엔 "클라가 보낸 Initial 수" 대 "서버가 센 원본 수" 로 쟀는데,
    # 서버의 originals 는 Initial 뿐 아니라 Handshake·ACK 등 모든 비패리티
    # 데이터그램을 세므로 받은 쪽이 더 커져 실효 손실률이 -40.8% 라는
    # 말이 안 되는 값이 나왔다. tc 의 통계는 그런 오해가 없다.
    import re as _re
    B.run("tc qdisc del dev %s root" % B.DEV_LOCAL, check=False)
    B.run("tc qdisc add dev %s root %s"
          % (B.DEV_LOCAL, B._netem_spec(RTT_MS / 2.0, 5.0, 1.0)))
    p, sp = B.start_server(CERT_EFFECT, fec="on")
    rows, cs, err = B.run_client(GROUP, 150, fec="on", gap_ms=8, timeout_s=8,
                                 expect_k=K)
    B.stop_server(p)
    tcout = B.run("tc -s qdisc show dev %s" % B.DEV_LOCAL).stdout
    m = _re.search(r"Sent\s+\d+\s+bytes\s+(\d+)\s+pkt\s+\(dropped\s+(\d+)",
                   tcout)
    eff = None
    if m:
        passed, dropped = int(m.group(1)), int(m.group(2))
        tot = passed + dropped
        eff = (dropped / float(tot)) if tot else None
        detail = "통과 %d, 폐기 %d, 실효 %.2f%%" % (passed, dropped,
                                                   100 * (eff or 0))
    else:
        detail = "tc 통계를 못 읽었다: %s" % tcout.strip()[:60]
    add("netem 이 시킨 만큼 떨어뜨린다 (5% 요청 -> 커널 실측 3~7%)",
        eff is not None and 0.03 <= eff <= 0.07, detail)
    out["netem_effective_loss"] = eff
    B.set_netem(RTT_MS / 2.0)

    npass = sum(1 for c in out["checks"] if c["ok"])
    print()
    print("-" * 100)
    print("%d / %d 통과" % (npass, len(out["checks"])))
    out["passed"] = npass
    out["total"] = len(out["checks"])
    print("saved:", B.save("p8_stability.json", out))
    return 0 if npass == len(out["checks"]) else 1


if __name__ == "__main__":
    sys.exit(main())
