from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B

RTT_MS = 50.0
CERT = 2955
N = 40
GROUP = "X25519MLKEM768"
K = 2
PTO_FLOOR_MS = 900.0


def valid_trial_row(row):
    return (isinstance(row, dict) and type(row.get("i")) is int
            and type(row.get("ok")) is bool
            and type(row.get("ms")) in (int, float)
            and math.isfinite(row["ms"]) and row["ms"] >= 0)


def run_case(name, fec, m, drop_i="", drop_p=-1, corrupt_p=-1, n=N):
    extra = []
    if drop_i:
        extra += ["-drop-initial", drop_i]
    if drop_p >= 0:
        extra += ["-drop-parity", str(drop_p)]
    if corrupt_p >= 0:
        extra += ["-corrupt-parity", str(corrupt_p)]

    B.set_netem(RTT_MS / 2.0)
    p, sp = B.start_server(CERT, fec=("on" if fec == "on" else fec))
    rows, cs, err = B.run_client(GROUP, n, fec=fec, m=m, gap_ms=10,
                                 timeout_s=8, expect_k=K, extra=extra)
    B.stop_server(p)
    ss = B.read_server_stats(sp)
    valid_rows = [r for r in rows if valid_trial_row(r)]
    if (len(valid_rows) != n or len(valid_rows) != len(rows)
            or sorted(r["i"] for r in valid_rows) != list(range(n))):
        err = "; ".join(filter(None, (err, "client trial records missing or invalid")))
    rows = valid_rows
    s = B.summarize(rows, rtt_ms=RTT_MS)
    ok_ms = [r["ms"] for r in rows if r.get("ok")]
    return {
        "case": name, "fec": fec, "m": m,
        "drop_initial": drop_i, "drop_parity": drop_p,
        "corrupt_parity": corrupt_p,
        "planned_n": n, "n": s["n"], "ok": s["ok"], "fail": s["fail"],
        "p50": s["p50"], "p95": s["p95"], "max": s["max"],
        "pto_share": (sum(1 for t in ok_ms if t >= PTO_FLOOR_MS)
                      / float(len(ok_ms))) if ok_ms else None,
        "cli_dropped_orig": cs.get("dropped_originals"),
        "cli_dropped_par": cs.get("dropped_parities"),
        "cli_corrupt_par": cs.get("corrupted_parities"),
        "cli_parity_sent": cs.get("parity_sent"),
        "srv_recovered": ss.get("recovered"),
        "srv_late": ss.get("late_recovered"),
        "srv_crc_fail": ss.get("recover_crc_fail"),
        "srv_unrecover": ss.get("unrecoverable_seen"),
        "srv_refused": ss.get("recover_refused_by_accounting"),
        "srv_bytes_in": ss.get("bytes_in"),
        "srv_bytes_to_stack": ss.get("bytes_to_stack"),
        "err": err,
    }


def case_complete(case):
    counters = ("planned_n", "n", "ok", "fail",
                "cli_dropped_orig", "cli_dropped_par", "cli_corrupt_par",
                "cli_parity_sent", "srv_recovered", "srv_late", "srv_crc_fail",
                "srv_unrecover", "srv_refused",
                "srv_bytes_in", "srv_bytes_to_stack")
    if (case.get("err") != ""
            or not all(type(case.get(k)) is int and case[k] >= 0
                       for k in counters)):
        return False
    if (case["planned_n"] <= 0 or case["n"] != case["planned_n"]
            or case["ok"] + case["fail"] != case["n"]
            or case["srv_late"] > case["srv_recovered"]):
        return False
    timing = ("p50", "p95", "max", "pto_share")
    if case["ok"] == 0:
        return all(k in case and case[k] is None for k in timing)
    return (all(type(case.get(k)) in (int, float) and math.isfinite(case[k])
                for k in timing)
            and 0 <= case["p50"] <= case["p95"] <= case["max"]
            and 0 <= case["pto_share"] <= 1
            and case["srv_bytes_in"] > 0 and case["srv_bytes_to_stack"] > 0)


def injections_match(case):
    if not case_complete(case):
        return False
    original = case.get("drop_initial")
    parity = case.get("drop_parity")
    corrupt = case.get("corrupt_parity")
    if (not isinstance(original, str)
            or type(parity) is not int or type(corrupt) is not int):
        return False
    count_original = len(set(original.split(","))) if original else 0
    n = case["planned_n"]
    return (case["cli_dropped_orig"] == count_original * n
            and case["cli_dropped_par"] == int(parity >= 0) * n
            and case["cli_corrupt_par"] == int(corrupt >= 0) * n)


def link_counters(dev, ns=None):
    cmd = "ip -s link show %s" % dev
    if ns:
        cmd = "ip netns exec %s %s" % (ns, cmd)
    out = B.run(cmd).stdout
    nums = re.findall(r"^\s+(\d+)\s+\d+\s+\d+", out, re.M)
    if len(nums) < 2:
        return None
    return {"rx_bytes": int(nums[0]), "tx_bytes": int(nums[1])}


def amplification_wire_check(fec="off", m=1):
    cert = 9000
    ONE_WAY_MS = 400.0
    B.set_netem(ONE_WAY_MS)
    p, sp = B.start_server(cert, fec="off")
    base = link_counters(B.DEV_PEER, B.NS)
    qamp = B.require_bin()
    t0 = time.monotonic()
    cli = subprocess.Popen(
        ["timeout", "40", qamp, "-mode", "client",
         "-addr", "%s:%d" % (B.RX_IP, B.SERVER_PORT),
         "-group", GROUP, "-n", "1", "-gap", "0ms", "-timeout", "30s",
         "-fec", fec, "-m", str(m), "-expect-k", str(K)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    timeline = []
    for _ in range(25):
        time.sleep(0.1)
        c = link_counters(B.DEV_PEER, B.NS)
        if not (c and base):
            continue
        timeline.append({"t": round(time.monotonic() - t0, 2),
                         "rx": c["rx_bytes"] - base["rx_bytes"],
                         "tx": c["tx_bytes"] - base["tx_bytes"]})
    client_returncode = None
    try:
        client_returncode = cli.wait(timeout=40)
    except subprocess.TimeoutExpired:
        cli.kill()
        cli.wait(timeout=3)
    B.stop_server(p)
    B.set_netem(RTT_MS / 2.0)

    worst = None
    for x in timeline:
        if x["rx"] <= 0:
            continue
        r = x["tx"] / float(x["rx"])
        if worst is None or r > worst["ratio"]:
            worst = {"t": x["t"], "rx": x["rx"], "tx": x["tx"], "ratio": r}
    errors = []
    if len(timeline) != 25:
        errors.append("커널 계수기 표본 %d/25" % len(timeline))
    if client_returncode != 0:
        errors.append("클라이언트 종료 코드 %s" % client_returncode)
    previous_rx, previous_tx = 0, 0
    for x in timeline:
        if x["rx"] < previous_rx or x["tx"] < previous_tx:
            errors.append("누적 계수기가 감소함")
            break
        previous_rx, previous_tx = x["rx"], x["tx"]
    if not timeline or timeline[-1]["rx"] <= 0 or timeline[-1]["tx"] <= 0:
        errors.append("양방향 트래픽을 관측하지 못함")
    if any(x["rx"] == 0 and x["tx"] > 0 for x in timeline):
        errors.append("수신 기록 없이 송신만 관측됨")
    max_ratio = worst["ratio"] if worst else None
    return {"cert": cert, "fec": fec, "m": m, "one_way_ms": ONE_WAY_MS,
            "timeline": timeline, "worst": worst,
            "max_ratio": max_ratio,
            "ok": not errors and max_ratio is not None and max_ratio <= 3.0,
            "observation_complete": not errors,
            "client_returncode": client_returncode,
            "detail": "; ".join(errors),
            "measurement_layer": "L2", "sample_interval_s": 0.1,
            "address_validation_tracked": False,
            "rfc_compliance_verified": False}


def main():
    B.harden()
    B.require_root()
    B.require_bin()
    B.setup()

    cases = []
    print("=" * 100)
    print("결정적 검증 - 소거를 우리가 만들고, 반드시 그래야 하는 결과와 대조한다")
    print("(그룹 %s, k=%d, cert %d, RTT %.0f ms, 무작위 손실 없음, 조건마다 n=%d)"
          % (GROUP, K, CERT, RTT_MS, N))
    print("=" * 100)

    cases.append(run_case("V0 fec m=1 / 소거 없음 / 규모 n=200", "on", 1,
                          n=200))
    cases.append(run_case("V1 off / 소거 없음", "off", 1))
    cases.append(run_case("V2 off / 원본0 소거", "off", 1, drop_i="0"))
    cases.append(run_case("V3 off / 원본1 소거", "off", 1, drop_i="1"))
    cases.append(run_case("V4 fec m=1 / 원본0 소거", "on", 1, drop_i="0"))
    cases.append(run_case("V5 fec m=1 / 원본1 소거", "on", 1, drop_i="1"))
    cases.append(run_case("V6 fec m=1 / 패리티 소거", "on", 1, drop_i="0",
                          drop_p=0))
    cases.append(run_case("V7 fec m=1 / 원본0 소거 + 패리티 손상", "on", 1,
                          drop_i="0", corrupt_p=0))
    cases.append(run_case("V8 fec m=2 / 원본0 소거", "on", 2, drop_i="0"))
    cases.append(run_case("V9 fec m=1 / 원본0+1 소거", "on", 1, drop_i="0,1"))

    for c in cases:
        print("%-34s 성공 %3d/%-3d  p50 %8.1f  PTO비율 %5.1f%%  "
              "복구 %-4s CRC거절 %-3s 소거주입 %s/%s/%s"
              % (c["case"], c["ok"], c["n"], c["p50"] or -1,
                 100 * (c["pto_share"] or 0), c["srv_recovered"],
                 c["srv_crc_fail"], c["cli_dropped_orig"],
                 c["cli_dropped_par"], c["cli_corrupt_par"]))
        sys.stdout.flush()

    def by(name):
        return next(c for c in cases if c["case"].startswith(name))

    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    incomplete = [c["case"] for c in cases if not case_complete(c)]
    add("모든 조건에 계획한 시행과 서버 통계가 기록됨", not incomplete,
        "불완전한 조건: " + (", ".join(incomplete) or "없음"))
    wrong_injection = [c["case"] for c in cases if not injections_match(c)]
    add("모든 시행에 계획한 소거와 손상이 주입됨", not wrong_injection,
        "주입 불일치 조건: " + (", ".join(wrong_injection) or "없음"))

    ONE_RTT = 1.5 * RTT_MS

    v0 = by("V0")
    add("V0 손실이 0 이면 규모를 키워도 복구가 0 이어야 한다 "
        "(유령 복구 금지)",
        case_complete(v0)
        and (v0["srv_recovered"] or 0) == 0 and (v0["srv_late"] or 0) == 0
        and (v0["srv_crc_fail"] or 0) == 0 and v0["ok"] == v0["n"],
        "n=%d 성공 %d, 복구 %s, 늦은복구 %s, CRC거절 %s"
        % (v0["n"], v0["ok"], v0["srv_recovered"], v0["srv_late"],
           v0["srv_crc_fail"]))

    v1 = by("V1")
    add("V1 기준선은 소거가 없으면 100% 성공, 모든 시행이 1-RTT",
        case_complete(v1) and v1["ok"] == v1["n"]
        and (v1["max"] or 1e9) < ONE_RTT,
        "성공 %d/%d, p50 %.1f ms, 최대 %.1f ms"
        % (v1["ok"], v1["n"], v1["p50"] or -1, v1["max"] or -1))

    for nm in ("V2", "V3"):
        c = by(nm)
        add("%s 기준선은 원본 하나만 잃어도 왕복을 더 쓴다" % nm,
            injections_match(c) and c["ok"] == c["n"]
            and (c["p50"] or 0) >= ONE_RTT,
            "p50 %.1f ms (= %.1f RTT), 소거주입 %s건"
            % (c["p50"] or -1, (c["p50"] or 0) / RTT_MS,
               c["cli_dropped_orig"]))

    for nm in ("V4", "V5", "V8"):
        c = by(nm)
        rec = c["srv_recovered"] or 0
        add("%s FEC 는 그 소거를 복구해 **모든 시행**이 1-RTT" % nm,
            injections_match(c) and c["ok"] == c["n"]
            and (c["max"] or 1e9) < ONE_RTT and rec == c["n"]
            and (c["srv_crc_fail"] or 0) == 0,
            "최대 %.1f ms, 복구 %d/%d, CRC실패 %s"
            % (c["max"] or -1, rec, c["n"], c["srv_crc_fail"]))

    c = by("V6")
    add("V6 패리티를 없애면 FEC 도 못 고치고 기준선으로 돌아간다 "
        "(개선이 다른 경로에서 온 것이 아님)",
        injections_match(c) and c["ok"] == c["n"]
        and (c["p50"] or 0) >= ONE_RTT and (c["srv_recovered"] or 0) == 0,
        "p50 %.1f ms, 복구 %s, 패리티소거 %s건"
        % (c["p50"] or -1, c["srv_recovered"], c["cli_dropped_par"]))

    c = by("V7")
    add("V7 패리티가 손상되면 CRC 가 걸러 내고 잘못된 복구를 안 넘긴다",
        injections_match(c) and c["ok"] == c["n"]
        and (c["srv_recovered"] or 0) == 0 and (c["srv_crc_fail"] or 0) > 0
        and (c["p50"] or 0) >= ONE_RTT,
        "복구 %s, CRC거절 %s, p50 %.1f ms"
        % (c["srv_recovered"], c["srv_crc_fail"], c["p50"] or -1))

    c = by("V9")
    add("V9 m=1 은 소거 2개를 복구하지 못한다 (능력을 과장하지 않는다)",
        injections_match(c) and (c["srv_recovered"] or 0) == 0
        and (c["ok"] == 0 or (c["p50"] or 0) >= ONE_RTT),
        "복구 %s, 소거주입 %s건, p50 %.1f ms"
        % (c["srv_recovered"], c["cli_dropped_orig"], c["p50"] or -1))

    bad = [c["case"] for c in cases
           if not case_complete(c)
           or c["srv_bytes_to_stack"] > c["srv_bytes_in"]]
    add("V10 모든 조건에서 스택 전달 바이트 <= 물리 수신 바이트",
        not bad, "위반 조건: %s" % (", ".join(bad) if bad else "없음"))

    amp_off = amplification_wire_check("off", 1)
    amp_on = amplification_wire_check("on", 2)
    for nm, a in (("off", amp_off), ("fec m=2", amp_on)):
        w = a.get("worst") or {}
        add("V11 커널 L2 계수기: %s 팔의 관측 시점 송수신비 <= 3 (보조 진단)"
            % nm, a.get("ok"),
            "최악 t=%.2fs 수신 %s B 송신 %s B 비 %.2f (한계 3.00)"
            % (w.get("t", -1), w.get("rx"), w.get("tx"),
               a.get("max_ratio") or -1))
    amp = {"off": amp_off, "fec_m2": amp_on}

    print()
    print("=" * 100)
    npass = 0
    for c in checks:
        npass += 1 if c["ok"] else 0
        print("[%s] %-58s %s" % ("통과" if c["ok"] else "실패",
                                 c["check"], c["detail"][:70]))
    print("-" * 100)
    print("%d / %d 통과" % (npass, len(checks)))

    out = {"rtt_ms": RTT_MS, "cert": CERT, "n": N, "group": GROUP,
           "cases": cases, "checks": checks, "amplification_wire": amp,
           "passed": npass, "total": len(checks)}
    print("saved:", B.save("p7_verify.json", out))
    return 0 if npass == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
