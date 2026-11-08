from __future__ import annotations

import json
import math
import os
import random
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B
from _journal import Journal, code_fingerprint

RTT_MS = 50.0
GROUP = "X25519MLKEM768"
K = 2
CERT_EFFECT = 2955
ROUNDS = 3
N_EFFECT = 200
N_PROBE = 30

BRACKET = {"off": (5850, 6050), "on1": (10850, 11050)}


def trial_record(n_req, rows, cs, err, summary, server_stats, provenance):
    good = [r for r in rows if isinstance(r, dict) and r.get("ok") is True]
    samples = [r["ms"] for r in good if type(r.get("ms")) in (int, float)
               and math.isfinite(r["ms"]) and r["ms"] > 0]
    coverage = {"requested_n": n_req, "returned_n": len(rows),
                "successful_n": len(good), "failed_n": len(rows) - len(good),
                "missing_n": max(0, n_req - len(rows)),
                "extra_n": max(0, len(rows) - n_req),
                "success_latency_n": len(samples), "error": err or ""}
    coverage["complete"] = (type(n_req) is int and n_req > 0
                             and len(rows) == len(good) == len(samples) == n_req
                             and not err and summary.get("n") == len(rows)
                             and summary.get("ok") == len(good))
    return {"n_req": n_req, "n": len(rows), "ok": len(good),
            "samples": samples, "raw_client_rows": rows,
            "client_stats": cs, "server_stats": server_stats,
            "err": err or "", "trial_coverage": coverage,
            "collection_provenance": provenance,
            "latency_scope": "successful returned rows only"}


def unit_source(rec, jr, key, reused):
    source = {"journal_key": key, "fingerprint": jr.fingerprint,
              "reused": reused, "journaled": jr.has(key)}
    if source["journaled"]:
        source.update(jr.provenance([key])["units"][0])
    else:
        source.update(run_id=jr.run_id, recorded_at=None)
    return dict(rec, unit_source=source)


def input_coverage(units, expected_units, expected_trials):
    problems = []
    keys = [u["record"]["unit_source"]["journal_key"] for u in units]
    if len(units) != expected_units or len(keys) != len(set(keys)):
        problems.append("missing or duplicate measurement unit")
    requested = returned = successful = failed = missing = 0
    for u in units:
        r = u["record"]
        coverage = r.get("trial_coverage")
        if not coverage:
            problems.append("%s: stored unit has no preserved denominators" % u["kind"])
            continue
        requested += coverage["requested_n"]
        returned += coverage["returned_n"]
        successful += coverage["successful_n"]
        failed += coverage["failed_n"]
        missing += coverage["missing_n"]
        if not coverage.get("complete"):
            problems.append("%s: incomplete trials or client error" % u["kind"])
    if requested != expected_trials:
        problems.append("requested trial count differs from the fixed design")
    return {"complete": not problems, "problems": problems,
            "expected_units": expected_units, "recorded_units": len(units),
            "expected_trials": expected_trials, "requested_n": requested,
            "returned_n": returned, "successful_n": successful,
            "failed_n": failed, "missing_n": missing}


def netem_counts(tcout):
    import re
    match = re.search(r"Sent\s+\d+\s+bytes\s+(\d+)\s+pkt\s+\(dropped\s+(\d+)", tcout)
    if not match:
        return {"sent_packets": None, "dropped_packets": None,
                "total_packets": None, "effective_loss": None, "raw_tc_output": tcout}
    sent, dropped = int(match.group(1)), int(match.group(2))
    total = sent + dropped
    return {"sent_packets": sent, "dropped_packets": dropped,
            "total_packets": total,
            "effective_loss": dropped / float(total) if total else None,
            "raw_tc_output": tcout}


def probe(cert, fec, m, n, jr, tag):
    key = "%s|%s|m%d|c%d|n%d" % (tag, fec, m, cert, n)
    if jr.has(key):
        return unit_source(jr.get(key), jr, key, True)
    started = datetime.now(timezone.utc).isoformat()
    B.set_netem(RTT_MS / 2.0)
    p, sp = B.start_server(cert, fec=("on" if fec == "on" else fec))
    rows, cs, err = B.run_client(GROUP, n, fec=fec, m=m, gap_ms=12,
                                 expect_k=K)
    B.stop_server(p)
    ss = B.read_server_stats(sp)
    s = B.summarize(rows, rtt_ms=RTT_MS)
    rec = {"cert": cert, "n": s["n"], "ok": s["ok"],
           "two_rtt_rate": s["two_rtt_rate"], "p50": s["p50"]}
    rec.update(trial_record(n, rows, cs, err, s, ss,
                           {"run_id": jr.run_id, "journal_key": key,
                            "started_at": started,
                            "finished_at": datetime.now(timezone.utc).isoformat()}))
    if rec["trial_coverage"]["complete"]:
        jr.record(key, rec)
    return unit_source(rec, jr, key, False)


def effect(loss_c2s, loss_s2c, fec, m, n, jr, tag):
    key = "eff|%s|%s|m%d|c%.1f|s%.1f|n%d" % (tag, fec, m, loss_c2s,
                                             loss_s2c, n)
    if jr.has(key):
        return unit_source(jr.get(key), jr, key, True)
    started = datetime.now(timezone.utc).isoformat()
    B.set_netem(RTT_MS / 2.0, loss_c2s=loss_c2s, loss_s2c=loss_s2c)
    p, sp = B.start_server(CERT_EFFECT, fec=("on" if fec == "on" else fec))
    rows, cs, err = B.run_client(GROUP, n, fec=fec, m=m, gap_ms=8,
                                 timeout_s=8, expect_k=K)
    B.stop_server(p)
    ss = B.read_server_stats(sp)
    s = B.summarize(rows, rtt_ms=RTT_MS)
    rec = {"n": s["n"], "ok": s["ok"], "p50": s["p50"], "p95": s["p95"],
           "p99": s["p99"],
           "srv_recovered": ss.get("recovered"),
           "srv_crc_fail": ss.get("recover_crc_fail"),
           "cli_initial_dgrams": cs.get("initial_datagrams")}
    rec.update(trial_record(n, rows, cs, err, s, ss,
                           {"run_id": jr.run_id, "journal_key": key,
                            "started_at": started,
                            "finished_at": datetime.now(timezone.utc).isoformat()}))
    if s["n"] == n:
        jr.record(key, rec)
    return unit_source(rec, jr, key, False)


def pct(v, q):
    if not v:
        return None
    s = sorted(v)
    return s[int(q * (len(s) - 1))]


def tail_rate(v, thresh):
    if not v:
        return None
    return sum(1 for x in v if x > thresh) / float(len(v))


def bootstrap_tail(a, b, thresh, iters=4000, seed=11):
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
           "negative_rounds": [], "checks": [], "diagnostics": [], "raw_units": [],
           "statistical_limits": "Bootstrap treats successful latencies as independent; pooled rounds are not independent replications."}

    def remember(kind, rec):
        out["raw_units"].append({"kind": kind, "record": rec})

    def diagnose(name, detail):
        out["diagnostics"].append({"check": name, "ok": None,
                                   "status": "diagnostic", "gating": False,
                                   "detail": detail})
        print("[진단] %s %s" % (name, detail))

    def add(name, ok, detail):
        out["checks"].append({"check": name, "ok": bool(ok),
                              "detail": detail})
        print("[%s] %-56s %s" % ("통과" if ok else "실패", name, detail[:80]))
        sys.stdout.flush()

    print("=" * 100)
    print("1) 임계 재현성 - 같은 두 점에서 %d 라운드 반복" % ROUNDS)
    print("=" * 100)
    for r in range(ROUNDS):
        row = {"round": r}
        for arm, (lo, hi) in BRACKET.items():
            fec, m = ("off", 1) if arm == "off" else ("on", 1)
            a = probe(lo, fec, m, N_PROBE, jr, "r%d" % r)
            b = probe(hi, fec, m, N_PROBE, jr, "r%d" % r)
            remember("threshold", a)
            remember("threshold", b)
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

    print()
    print("=" * 100)
    print("2) 효과 재현성 - c2s 손실 2%%, off 대 on1, %d 라운드 (조건마다 n=%d)"
          % (ROUNDS, N_EFFECT))
    print("=" * 100)
    _pool_off, _pool_on = [], []
    for r in range(ROUNDS):
        a = effect(2.0, 0.0, "off", 1, N_EFFECT, jr, "r%d" % r)
        b = effect(2.0, 0.0, "on", 1, N_EFFECT, jr, "r%d" % r)
        remember("effect", a)
        remember("effect", b)
        _pool_off.extend(a["samples"] or [])
        _pool_on.extend(b["samples"] or [])
        bs95 = bootstrap_diff(a["samples"], b["samples"], 0.95)
        bs99 = bootstrap_diff(a["samples"], b["samples"], 0.99)
        TAIL = 1.5 * RTT_MS
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
        if bstail is not None:
            print("  라운드 %d  꼬리비율 off %5.1f%% -> on1 %5.1f%%  "
              "차이 %+6.1f%%p [%+.1f, %+.1f] | p99 %6.1f -> %6.1f | 복구 %s"
              % (r, 100 * (row["tail_off"] or 0), 100 * (row["tail_on1"] or 0),
                 100 * bstail["point"], 100 * bstail["lo"], 100 * bstail["hi"],
                 a["p99"] or -1, b["p99"] or -1, b["srv_recovered"]))
        else:
            print("  라운드 %d: 성공 지연 표본이 없어 꼬리 구간 판정 불가" % r)
        sys.stdout.flush()

    _bs_pool = bootstrap_tail(_pool_off, _pool_on, 1.5 * RTT_MS)
    out["tail_pooled"] = _bs_pool
    _incl = [x["round"] for x in out["effect_rounds"]
             if x["d_tail"] is None or x["d_tail"]["hi"] >= 0]
    _rev = [x["round"] for x in out["effect_rounds"]
            if x["d_tail"] is not None and x["d_tail"]["lo"] > 0]
    add("c2s 손실에서 꼬리 감소가 통계적으로 확실 "
        "(합동 %d판 부트스트랩 구간이 0 제외 + 반대방향 라운드 없음)"
        % len(_pool_off),
        _bs_pool is not None and _bs_pool["hi"] < 0 and not _rev,
        "합동 %+.1f%%p [%+.1f, %+.1f] | 반대방향 라운드 %s | "
        "라운드별(정보) %s -> %s, 0 포함 %s"
        % (100 * _bs_pool["point"], 100 * _bs_pool["lo"],
           100 * _bs_pool["hi"], _rev or "없음",
           ["%.1f%%" % (100 * (x["tail_off"] or 0))
            for x in out["effect_rounds"]],
           ["%.1f%%" % (100 * (x["tail_on1"] or 0))
            for x in out["effect_rounds"]],
           _incl or "없음") if _bs_pool else "표본 없음")
    p95s = [x["off"]["p95"] for x in out["effect_rounds"] if x["off"]["p95"] is not None]
    out["p95_baseline_unstable"] = (max(p95s) - min(p95s)) > 20 if p95s else None
    diagnose("기준선 p95 변동 (참고값, 통과 집계 제외)",
        "기준선 p95 라운드별 %s; 효과 판정은 1.5 RTT 초과 비율의 합동 95%% 구간"
        % ["%.1f" % v for v in p95s])

    bad = [x for x in out["effect_rounds"] if x["crc_fail"] is None or x["crc_fail"] > 0]
    add("모든 라운드에서 복구 CRC 실패 0", not bad,
        "CRC 실패 또는 통계 누락 라운드 %d" % len(bad))

    print()
    print("=" * 100)
    print("3) 음성 대조 - 손실을 **서버->클라이언트** 쪽에만 건다.")
    print("   우리 FEC 는 반대 방향만 보호하므로 **도움이 되면 안 된다**.")
    print("=" * 100)
    for r in range(ROUNDS):
        a = effect(0.0, 2.0, "off", 1, N_EFFECT, jr, "r%d" % r)
        b = effect(0.0, 2.0, "on", 1, N_EFFECT, jr, "r%d" % r)
        remember("negative", a)
        remember("negative", b)
        bs = bootstrap_diff(a["samples"], b["samples"], 0.95)
        row = {"round": r, "off_p95": a["p95"], "on1_p95": b["p95"],
               "d_p95": bs, "recovered": b["srv_recovered"]}
        out["negative_rounds"].append(row)
        if bs is not None:
            print("  라운드 %d  off p95 %7.1f | on1 p95 %7.1f | 차이 %+7.1f "
              "[%+.1f, %+.1f] | 복구 %s"
              % (r, a["p95"] or -1, b["p95"] or -1, bs["point"], bs["lo"],
                 bs["hi"], b["srv_recovered"]))
        else:
            print("  라운드 %d: 성공 지연 표본이 없어 음성 대조 판정 불가" % r)
        sys.stdout.flush()

    claims = [x for x in out["negative_rounds"]
              if x["d_p95"] is not None and x["d_p95"]["hi"] < 0]
    add("음성 대조: s2c 손실에서 p95의 유의한 개선 라운드가 없다",
        not claims and all(x["d_p95"] is not None for x in out["negative_rounds"]),
        "개선이 관측된 라운드 %d/%d; 동등성이나 원인은 판정하지 않음"
        % (len(claims), ROUNDS))

    print()
    print("=" * 100)
    print("4) 계통오차 - 시행 순서 효과와 netem 실효 손실률")
    print("=" * 100)
    started = datetime.now(timezone.utc).isoformat()
    B.set_netem(RTT_MS / 2.0)
    p, sp = B.start_server(CERT_EFFECT, fec="off")
    rows, cs, err = B.run_client(GROUP, 120, fec="off", gap_ms=8, expect_k=K)
    B.stop_server(p)
    ss = B.read_server_stats(sp)
    order = trial_record(120, rows, cs, err, B.summarize(rows, rtt_ms=RTT_MS), ss,
                         {"run_id": jr.run_id, "journal_key": "order|off|n120",
                          "started_at": started,
                          "finished_at": datetime.now(timezone.utc).isoformat()})
    order = unit_source(order, jr, "order|off|n120", False)
    remember("order", order)
    ms = order["samples"]
    first10 = ms[:10]
    rest = ms[10:]
    drift = ((sum(first10) / len(first10)) - (sum(rest) / len(rest))) \
        if first10 and rest else None
    out["order_effect"] = {"record": order, "first_success_n": len(first10),
                           "remaining_success_n": len(rest), "first_success_ms": first10,
                           "remaining_success_ms": rest, "mean_difference_ms": drift,
                           "selection_scope": "first ten successful returned rows, then remaining successful rows"}
    add("시행 순서 효과 - 처음 10 성공 지연과 나머지의 평균 차이가 1 ms 미만",
        drift is not None and abs(drift) < 1.0,
        "차이 %.2f ms (첫 10회 %.2f, 나머지 %.2f)"
        % (drift if drift is not None else -1, sum(first10) / max(1, len(first10)),
           sum(rest) / max(1, len(rest))))

    started = datetime.now(timezone.utc).isoformat()
    B.run("tc qdisc del dev %s root" % B.DEV_LOCAL, check=False)
    B.run("tc qdisc add dev %s root %s"
          % (B.DEV_LOCAL, B._netem_spec(RTT_MS / 2.0, 5.0, 1.0)))
    p, sp = B.start_server(CERT_EFFECT, fec="on")
    rows, cs, err = B.run_client(GROUP, 150, fec="on", gap_ms=8, timeout_s=8,
                                 expect_k=K)
    B.stop_server(p)
    ss = B.read_server_stats(sp)
    tcout = B.run("tc -s qdisc show dev %s" % B.DEV_LOCAL).stdout
    counters = netem_counts(tcout)
    eff = counters["effective_loss"]
    netem = trial_record(150, rows, cs, err, B.summarize(rows, rtt_ms=RTT_MS), ss,
                         {"run_id": jr.run_id, "journal_key": "netem|5|n150",
                          "started_at": started,
                          "finished_at": datetime.now(timezone.utc).isoformat()})
    netem = unit_source(netem, jr, "netem|5|n150", False)
    remember("netem", netem)
    out["netem_observation"] = {"requested_loss_pct": 5.0, "record": netem,
                               "kernel": counters,
                               "denominator_scope": "kernel packets, not requested client connections"}
    if counters["total_packets"] is not None:
        passed, dropped = counters["sent_packets"], counters["dropped_packets"]
        detail = "통과 %d, 폐기 %d, 실효 %.2f%%" % (passed, dropped,
                                                   100 * (eff or 0))
    else:
        detail = "tc 통계를 못 읽었다: %s" % tcout.strip()[:60]
    add("netem 이 시킨 만큼 떨어뜨린다 (5% 요청 -> 커널 실측 3~7%)",
        eff is not None and 0.03 <= eff <= 0.07, detail)
    out["netem_effective_loss"] = eff
    B.set_netem(RTT_MS / 2.0)

    coverage = input_coverage(out["raw_units"], ROUNDS * 8 + 2,
                              ROUNDS * (4 * N_PROBE + 4 * N_EFFECT) + 120 + 150)
    out["trial_coverage"] = coverage
    out["journal_provenance"] = jr.provenance()
    add("필수 시행의 요청·반환·성공·지연 분모와 오류 기록이 완전하다",
        coverage["complete"],
        "요청 %d/%d, 반환 %d, 성공 %d, 실패 %d, 누락 %d | %s" % (
            coverage["requested_n"], coverage["expected_trials"],
            coverage["returned_n"], coverage["successful_n"], coverage["failed_n"],
            coverage["missing_n"], "; ".join(coverage["problems"]) or "누락 없음"))

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
