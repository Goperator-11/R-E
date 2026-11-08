from __future__ import annotations

import json
import hashlib
import math
import os
import re
import socket
import struct
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B

RTT_MS = 50.0
CERT = 2955
GROUP = "X25519MLKEM768"
K = 2


def add(results, name, ok, detail, kind="시험"):
    indeterminate = kind == "판정불능"
    verdict = None if indeterminate else bool(ok)
    label = "판정불능" if indeterminate else ("통과" if verdict else "미흡")
    results.append({"check": name, "ok": verdict, "detail": detail,
                    "kind": kind, "gating": kind == "시험",
                    "status": "indeterminate" if indeterminate else ("passed" if verdict else "failed")})
    print("[%s] %-54s %s" % (label, name, detail if indeterminate or not verdict else detail[:78]))
    sys.stdout.flush()


def validate_client_rows(rows, expected, error=""):
    if error:
        raise ValueError("클라이언트 실행 오류: %s" % error)
    if len(rows) != expected:
        raise ValueError("측정 행 %d != 계획 %d" % (len(rows), expected))
    ids = []
    for row in rows:
        if not isinstance(row, dict) or type(row.get("ok")) is not bool:
            raise ValueError("측정 행에 bool ok가 없다")
        ident, ms = row.get("i"), row.get("ms")
        if type(ident) is not int:
            raise ValueError("측정 행에 정수 시행 번호가 없다")
        if (isinstance(ms, bool) or not isinstance(ms, (int, float))
                or not math.isfinite(ms) or ms < 0):
            raise ValueError("측정 행의 ms가 유한한 음이 아닌 수가 아니다")
        ids.append(ident)
    if sorted(ids) != list(range(expected)):
        raise ValueError("측정 시행 번호가 0..N-1의 고유 집합이 아니다")


def run_client_checked(*args, **kwargs):
    rows, stats, error = B.run_client(*args, **kwargs)
    validate_client_rows(rows, args[1], error)
    return rows, stats, error


def server_stats_present(stats, *fields):
    return (isinstance(stats, dict) and all(
        type(stats.get(field)) is int and stats[field] >= 0 for field in fields))


def complete_summary(summary, expected):
    return (summary["n"] == expected and summary["ok"] == expected
            and all(isinstance(summary.get(key), (int, float))
                    and math.isfinite(summary[key])
                    for key in ("p50", "p95")))


def c1_concurrent(results):
    B.set_netem(RTT_MS / 2.0, loss_c2s=3.0)
    p, sp = B.start_server(CERT, fec="on")
    qamp = B.require_bin()
    out = {}
    lock = threading.Lock()

    def worker(i):
        rows, error = [], ""
        try:
            r = subprocess.run(
                ["timeout", "180", qamp, "-mode", "client",
                 "-addr", "%s:%d" % (B.RX_IP, B.SERVER_PORT),
                 "-group", GROUP, "-n", "60", "-fec", "on", "-m", "1",
                 "-gap", "5ms", "-timeout", "8s", "-expect-k", str(K)],
                capture_output=True, text=True, timeout=200)
            rows = [json.loads(ln) for ln in r.stdout.splitlines()
                    if ln.strip().startswith("{")]
            validate_client_rows(rows, 60, "exit %d" % r.returncode
                                 if r.returncode else "")
        except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
            error = str(exc)
        with lock:
            out[i] = {"rows": rows, "error": error,
                      "ok": sum(1 for row in rows if isinstance(row, dict)
                                and row.get("ok") is True), "n": len(rows)}

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
    try:
        for t in ts:
            t.start()
        for t in ts:
            t.join()
    finally:
        B.stop_server(p)
    ss = B.read_server_stats(sp)
    tot_ok = sum(v["ok"] for v in out.values())
    tot_n = sum(v["n"] for v in out.values())
    valid = len(out) == 6 and all(not v["error"] for v in out.values())
    stats_ok = server_stats_present(ss, "recover_crc_fail", "bytes_to_stack", "bytes_in")
    crc = ss.get("recover_crc_fail")
    bad_acct = not stats_ok or ss["bytes_to_stack"] > ss["bytes_in"]
    add(results,
        "C1 동시 연결 6개 x 60회 (손실 3%) - 성공률과 회계가 유지되는가",
        valid and tot_ok == tot_n == 360 and crc == 0 and not bad_acct,
        "성공 %d/%d (계획 360), 복구 %s, CRC거절 %s, 회계 %s, 실행 유효 %s"
        % (tot_ok, tot_n, ss.get("recovered"), crc,
           "누락/위반" if bad_acct else "정상", valid))
    return {"ok": tot_ok, "n": tot_n, "srv": ss, "clients": out}


def tail_rate(v, thresh):
    if not v:
        return None
    return sum(1 for x in v if x > thresh) / float(len(v))


def c2_rtt(results):
    rows = []
    for rtt in (5.0, 50.0, 300.0):
        rec = {"rtt": rtt}

        for arm, fec in (("off", "off"), ("on", "on")):
            B.set_netem(rtt / 2.0)
            p, sp = B.start_server(CERT, fec=fec)
            try:
                r, cs, err = run_client_checked(GROUP, 150, fec=fec, m=1, gap_ms=4,
                                                timeout_s=10, expect_k=K)
            finally:
                B.stop_server(p)
            s = B.summarize(r, rtt_ms=rtt)
            rec["cost_" + arm] = {"p50": s["p50"], "mean": s["mean"],
                                  "p95": s["p95"], "ok": s["ok"], "n": s["n"]}
        cost_valid = all(complete_summary(rec["cost_" + arm], 150)
                         for arm in ("off", "on"))
        overhead = (rec["cost_on"]["p50"] - rec["cost_off"]["p50"]
                    if cost_valid else None)
        rec["overhead_ms"] = overhead

        _base = rec["cost_off"]["p50"]
        if _base is None:
            tail_thresh = 1.5 * rtt
            rec["tail_thresh_basis"] = "물러섬: 1.5*rtt (기준선 p50 없음)"
        else:
            tail_thresh = _base + 0.5 * rtt
            rec["tail_thresh_basis"] = ("off 무손실 p50 %.2f + 0.5*%.0f"
                                        % (_base, rtt))
        rec["tail_thresh"] = tail_thresh
        rec["tail_headroom_ms"] = (
            tail_thresh - rec["cost_on"]["p50"] if cost_valid else None)

        for arm, fec in (("off", "off"), ("on", "on")):
            B.set_netem(rtt / 2.0, loss_c2s=3.0)
            p, sp = B.start_server(CERT, fec=fec)
            try:
                r, cs, err = run_client_checked(GROUP, 200, fec=fec, m=1, gap_ms=4,
                                                timeout_s=10, expect_k=K)
            finally:
                B.stop_server(p)
            ss = B.read_server_stats(sp)
            s = B.summarize(r, rtt_ms=rtt)
            ms = [x["ms"] for x in r if x.get("ok")]
            rec["eff_" + arm] = {"tail": tail_rate(ms, tail_thresh),
                                 "p50": s["p50"], "ok": s["ok"], "n": s["n"],
                                 "rec": ss.get("recovered"),
                                 "crc": ss.get("recover_crc_fail"),
                                 "stats_present": server_stats_present(
                                     ss, "recover_crc_fail", "recovered"),
                                 "ms": ms}
        rows.append(rec)

        _drift = "" if overhead is None or overhead > -1.0 else (
            "  ⚠ 기준선보다 %.2f ms 빨랐다 - 비용이 아니라 표류 의심"
            % (-overhead))
        add(results,
            "C2 RTT %.0f ms - 순수 오버헤드가 1 ms 미만인가 (한쪽 꼬리)" % rtt,
            cost_valid and overhead < 1.0,
            "손실 0 p50 %s -> %s ms, 오버헤드 %s ms, 150회씩 완전 성공 %s%s"
            % (rec["cost_off"]["p50"], rec["cost_on"]["p50"],
               overhead, cost_valid, _drift))

        a, b = rec["eff_off"], rec["eff_on"]

        _jit = None
        if rec["cost_on"]["p95"] is not None and rec["cost_on"]["p50"] is not None:
            _jit = rec["cost_on"]["p95"] - rec["cost_on"]["p50"]
        _head = rec["tail_headroom_ms"]
        _ruler_ok = (_head is not None and _jit is not None
                     and _head >= 3.0 * _jit)
        _ruler_note = ("" if _ruler_ok else
                       "  ⚠ 자 분해능 부족 - 여유 %s ms vs 흔들림 %s ms"
                       % ("?" if _head is None else "%.2f" % _head,
                          "?" if _jit is None else "%.2f" % _jit))

        add(results,
            "C2 RTT %.0f ms - 자에 분해능이 있는가 (여유 >= 3x 흔들림)" % rtt,
            _ruler_ok,
            "기준 %.2f ms (%s) | 여유 %s ms | 무손실 흔들림 %s ms"
            % (rec["tail_thresh"], rec["tail_thresh_basis"],
               "?" if _head is None else "%.2f" % _head,
               "?" if _jit is None else "%.2f" % _jit))

        if not _ruler_ok:
            add(results,
                "C2 RTT %.0f ms - 손실 3%% 에서 꼬리 비율이 줄어드는가" % rtt,
                True,
                "판정불능 - 자에 분해능이 없다%s (꼬리 %.1f%% -> %.1f%%, "
                "복구 %s, CRC거절 %s)"
                % (_ruler_note, 100 * (a["tail"] or 0), 100 * (b["tail"] or 0),
                   b["rec"], b["crc"]),
                kind="판정불능")
        else:
            add(results,
                "C2 RTT %.0f ms - 손실 3%% 에서 꼬리 비율이 줄어드는가" % rtt,
                a["ok"] == a["n"] == b["ok"] == b["n"] == 200
                and a["stats_present"] and b["stats_present"] and b["crc"] == 0
                and a["tail"] is not None and b["tail"] is not None
                and b["tail"] <= a["tail"],
                "꼬리 %.1f%% -> %.1f%%, 복구 %s, CRC거절 %s (기준 %.2f ms)"
                % (100 * (a["tail"] or 0), 100 * (b["tail"] or 0), b["rec"],
                   b["crc"], rec["tail_thresh"]))
    return rows


def c3_highloss(results):
    rows = []
    for loss in (20.0,):
        B.set_netem(RTT_MS / 2.0, loss_c2s=loss)
        recs = {}
        for arm, fec in (("off", "off"), ("on", "on")):
            p, sp = B.start_server(CERT, fec=fec)
            try:
                r, cs, err = run_client_checked(GROUP, 120, fec=fec, m=1, gap_ms=5,
                                                timeout_s=10, expect_k=K)
            finally:
                B.stop_server(p)
            ss = B.read_server_stats(sp)
            s = B.summarize(r, rtt_ms=RTT_MS)
            recs[arm] = {"p50": s["p50"], "p95": s["p95"], "ok": s["ok"],
                         "n": s["n"], "rec": ss.get("recovered"),
                         "crc": ss.get("recover_crc_fail"),
                         "stats_present": server_stats_present(ss, "recover_crc_fail"),
                         "unrec": ss.get("unrecoverable_seen")}
        rows.append({"loss": loss, **recs})
        add(results,
            "C3 손실 %.0f%% 에서 무너지지 않는가 (성공률 유지, 잘못된 복구 0)"
            % loss,
            recs["on"]["ok"] == recs["on"]["n"] == recs["off"]["n"] == 120
            and recs["on"]["stats_present"] and recs["on"]["crc"] == 0
            and recs["on"]["ok"] >= recs["off"]["ok"],
            "off 성공 %d/%d p95 %.0f | on 성공 %d/%d p95 %.0f, "
            "복구 %s 복구불가 %s CRC거절 %s"
            % (recs["off"]["ok"], recs["off"]["n"], recs["off"]["p95"] or -1,
               recs["on"]["ok"], recs["on"]["n"], recs["on"]["p95"] or -1,
               recs["on"]["rec"], recs["on"]["unrec"], recs["on"]["crc"]))
    return rows


def craft(dcid, k, m, index, symlen, crcs, lens, sym, blen=None):
    body = b"PFEC" + bytes([1]) + struct.pack(">H", 7) \
        + bytes([k, m, index]) + struct.pack(">H", symlen)
    for c in crcs:
        body += struct.pack(">I", c)
    for l in lens:
        body += struct.pack(">H", l)
    body += sym
    n = blen if blen is not None else len(body)
    out = bytes([0xC3]) + struct.pack(">I", 1) + bytes([len(dcid)]) + dcid \
        + bytes([0]) + bytes([0]) \
        + bytes([0x40 | ((n >> 8) & 0x3F), n & 0xFF]) + body
    return out


def c4_malformed(results):
    B.set_netem(RTT_MS / 2.0)
    p, sp = B.start_server(CERT, fec="on")
    dcid = bytes(range(8))
    junk = bytes(1200)
    cases = [
        ("k=0", craft(dcid, 0, 1, 0, 8, [], [], bytes(8))),
        ("k=255 m=8", craft(dcid, 255, 8, 7, 8, [0] * 255, [0] * 255,
                            bytes(8))),
        ("symlen 과대", craft(dcid, 2, 1, 0, 60000, [0, 0], [0, 0],
                              bytes(16))),
        ("길이 필드 거짓", craft(dcid, 2, 1, 0, 8, [0, 0], [0, 0], bytes(8),
                                blen=9000)),
        ("본문 절단", craft(dcid, 2, 1, 0, 1200, [0, 0], [0, 0], bytes(4))),
        ("index >= m", craft(dcid, 2, 1, 5, 8, [0, 0], [0, 0], bytes(8))),
        ("전부 0", bytes(1300)),
        ("무작위", os.urandom(1300)),
        ("magic 만 맞음", b"PFEC" + os.urandom(1296)),
    ]
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0.5)
    sent = 0
    for _name, pkt in cases:
        for _ in range(20):
            try:
                s.sendto(pkt, (B.RX_IP, B.SERVER_PORT))
                sent += 1
            except OSError:
                pass
    s.close()
    time.sleep(0.6)
    alive_before = p.poll() is None

    try:
        r, cs, err = run_client_checked(GROUP, 30, fec="on", m=1, gap_ms=8,
                                        timeout_s=8, expect_k=K)
    finally:
        B.stop_server(p)
    ss = B.read_server_stats(sp)
    su = B.summarize(r, rtt_ms=RTT_MS)
    stats_ok = server_stats_present(ss, "recover_crc_fail", "bytes_to_stack", "bytes_in")
    ok = (sent == 20 * len(cases) and alive_before and su["ok"] == su["n"] == 30
          and stats_ok and ss["recover_crc_fail"] == 0
          and ss["bytes_to_stack"] <= ss["bytes_in"])
    add(results,
        "C4 기형/악성 패리티 %d개 투입 후에도 서버 생존 + 정상 연결 + 회계 유지"
        % sent, ok,
        "서버 생존 %s, 공격 후 성공 %d/%d, CRC거절 %s, 회계 %s"
        % (alive_before, su["ok"], su["n"], ss.get("recover_crc_fail"),
           "누락" if not stats_ok else (
               "정상" if ss["bytes_to_stack"] <= ss["bytes_in"] else "위반")))
    return {"sent": sent, "alive": alive_before, "srv": ss}


def c5_longrun(results):
    rec = {}
    for arm, fec in (("off", "off"), ("on", "on")):
        B.set_netem(RTT_MS / 2.0, loss_c2s=3.0)
        p, sp = B.start_server(CERT, fec=fec)
        try:
            r, cs, err = run_client_checked(GROUP, 600, fec=fec, m=1, gap_ms=4,
                                            timeout_s=8, expect_k=K)
        finally:
            B.stop_server(p)
        ss = B.read_server_stats(sp)
        s = B.summarize(r, rtt_ms=RTT_MS)
        ms = [x["ms"] for x in r if x.get("ok")]
        first, last = ms[:100], ms[-100:]
        drift = ((sum(last) / len(last)) - (sum(first) / len(first))
                 if first and last else None)
        rec[arm] = {"ok": s["ok"], "n": s["n"], "drift": drift,
                    "recovered": ss.get("recovered"),
                    "stats_present": server_stats_present(ss, "recover_crc_fail"),
                    "crc": ss.get("recover_crc_fail")}
    complete = all(rec[a]["ok"] == rec[a]["n"] == 600
                   and rec[a]["drift"] is not None and rec[a]["stats_present"]
                   for a in ("off", "on"))
    d_on = abs(rec["on"]["drift"]) if complete else None
    d_off = abs(rec["off"]["drift"]) if complete else None
    add(results,
        "C5 한 서버로 600 연결 - FEC 가 기준선보다 더 처지지 않는가",
        complete and rec["on"]["crc"] == 0
        and d_on <= d_off + 2.0,
        "처짐 off %s ms / on %s ms, 성공 %d/%d, 복구 %s, CRC거절 %s"
        % (rec["off"]["drift"], rec["on"]["drift"],
           rec["on"]["ok"], rec["on"]["n"], rec["on"]["recovered"],
           rec["on"]["crc"]))
    return rec


def inventory(results):
    from padfec import policy

    sources, fingerprints = {}, {}
    for name in ("qamp.go", "policy.go", "pfail_table.go"):
        path = os.path.join(HERE, "quicbed", name)
        with open(path, "rb") as stream:
            raw = stream.read()
        fingerprints[name] = hashlib.sha256(raw).hexdigest()
        sources[name] = re.sub(r"//[^\n]*|/\*.*?\*/", "", raw.decode("utf-8"),
                               flags=re.S)
    qamp, policy_go = sources["qamp.go"], sources["policy.go"]
    evidence = {
        "auto_branch": bool(re.search(r'if\s+mode\s*==\s*"auto"\s*\{', qamp)),
        "cache_construction": "newDestCache(cachePath)" in qamp,
        "policy_call": "cache.decide(" in qamp,
        "observation_call": "cache.observe(" in qamp,
        "policy_definition": bool(re.search(
            r"func\s+\(c\s+\*destCache\)\s+decide\s*\(", policy_go)),
        "observation_definition": bool(re.search(
            r"func\s+\(c\s+\*destCache\)\s+observe\s*\(", policy_go)),
    }
    closed_loop = all(evidence.values())
    go_match = re.search(r"\bconst\s+mMaxDefault\s*=\s*(\d+)\b",
                         sources["pfail_table.go"])
    go_max = int(go_match.group(1)) if go_match else None
    high_m = (policy.M_MAX_DEFAULT >= 3 and go_max == policy.M_MAX_DEFAULT
              and bool(re.search(r"func\s+rsEncode\s*\(", qamp))
              and 'flag.Int("m-max", mMaxDefault,' in qamp)
    gaps = []
    gaps.append({
        "item": "적응 정책의 폐루프",
        "designed": "padfec/policy.py 가 (C, k, W, cert, p, L, RTT) 로 m 을 고른다",
        "implemented": ("auto 모드의 목적지 캐시 선택·관측 경로가 소스에 있다"
                        if closed_loop else "필수 폐루프 소스 경로 일부를 확인하지 못했다"),
        "implementation_status": "source_present" if closed_loop else "source_incomplete",
        "ok": closed_loop,
        "validation_status": "not_assessed_by_inventory",
        "validation_stages": ["p11", "p15", "p17"],
        "source_checks": evidence, "source_sha256": fingerprints,
        "why": "처음 접속할 때는 캐시가 없어 콜드스타트를 쓴다. "
               "소스 경로의 존재는 성능·적응 성공의 증거가 아니며 "
               "동일 소스에 대한 p11·p15·p17 결과를 별도로 검토해야 한다."})

    gaps.append({
        "item": "서버 -> 클라이언트 방향 보호",
        "designed": "없음 (설계상 제외)",
        "implemented": "없음",
        "implementation_status": "out_of_scope",
        "ok": False,
        "validation_status": "not_assessed_by_inventory",
        "why": "현재 설계의 보호 방향은 c2s다. s2c 보호는 구현 범위 밖이다. "
               "이 제외를 모든 서버 방향 FEC의 불가능성으로 해석하지 않는다."})

    gaps.append({
        "item": "제자리(패딩 자리) 배치",
        "designed": "인수인계 문서 단계 2-B",
        "implemented": "현재 구현은 별도 패리티 데이터그램을 보낸다",
        "implementation_status": "not_implemented",
        "ok": False,
        "validation_status": "not_assessed_by_inventory",
        "validation_stages": ["p1"],
        "why": "용량 부등식의 성립 여부는 p1의 실제 설정과 원자료로 확인한다. "
               "시험한 설정의 용량 부족을 모든 패킷 구성의 불가능성으로 넓히지 않는다."})

    gaps.append({
        "item": "k(비행 데이터그램 수) 제어",
        "designed": "용량 정리는 k 를 늘리면 제자리가 가능해진다고 말한다",
        "implemented": "아니다 - quic-go 가 정하는 값을 받아들인다",
        "implementation_status": "not_implemented",
        "ok": False,
        "validation_status": "not_assessed_by_inventory",
        "why": "InitialPacketSize 선택과 원본 패킷 수의 직접 제어는 다르다. "
               "원본 분할과 ACK 처리를 바꾸는 별도 구현은 현재 재고에 없다."})

    gaps.append({
        "item": "m >= 3",
        "designed": "정책 기본 상한은 policy.M_MAX_DEFAULT=%d" % policy.M_MAX_DEFAULT,
        "implemented": "Python 기본 상한 %d, Go 생성 표 기본 상한 %s, m-max 선택 경로 %s"
                       % (policy.M_MAX_DEFAULT, go_max, high_m),
        "implementation_status": "source_present" if high_m else "source_incomplete",
        "ok": high_m,
        "validation_status": "not_assessed_by_inventory",
        "validation_stages": ["gate", "p18"],
        "source_sha256": fingerprints,
        "why": "m>=3 후보와 부호화 경로의 존재를 기록한다. "
               "동일 소스의 관문·p18 검증이 필요하며, "
               "상한 설정만으로 선택 빈도·성능 이득·상한 없는 지원을 주장하지 않는다."})

    for g in gaps:
        add(results, "재고: %s" % g["item"], g["ok"],
            "%s | 구현 상태 %s | 실측 검증 별도"
            % (g["implemented"], g["implementation_status"]), kind="재고")
    return gaps


def main():
    B.harden()
    B.require_root()
    B.require_bin()
    B.setup()

    results = []
    print("=" * 100)
    print("설계 대비 구현 재고조사")
    print("=" * 100)
    gaps = inventory(results)

    print()
    print("=" * 100)
    print("한 번도 시험하지 않은 영역")
    print("=" * 100)
    data = {}
    data["c1"] = c1_concurrent(results)
    data["c2"] = c2_rtt(results)
    data["c3"] = c3_highloss(results)
    data["c4"] = c4_malformed(results)
    data["c5"] = c5_longrun(results)

    tests = [r for r in results if r["kind"] == "시험"]
    npass = sum(1 for r in tests if r["ok"])
    open_gaps = [g for g in gaps if not g["ok"]]
    print()
    print("-" * 100)
    print("새 영역 시험 %d / %d 통과 | 미구현·제외 항목 %d 건"
          % (npass, len(tests), len(open_gaps)))

    out = {"results": results, "gaps": gaps, "data": data,
           "tests_passed": npass, "tests_total": len(tests),
           "open_gaps": len(open_gaps),
           "inventory_basis": "source_presence_not_runtime_validation",
           "inventory_status_counts": {
               status: sum(g["implementation_status"] == status for g in gaps)
               for status in sorted({g["implementation_status"] for g in gaps})}}
    print("saved:", B.save("p10_completeness.json", out))
    return 0 if npass == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
