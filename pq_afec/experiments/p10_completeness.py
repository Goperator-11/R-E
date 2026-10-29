# -*- coding: utf-8 -*-
"""P10 - 알고리즘의 **완성도**를 잰다. 잘 되는 것 말고 아직 안 되는 것을 찾는다.

p5/p7/p8 은 "설계한 대로 도는가"를 본다. 여기서는 다른 것을 묻는다.

    설계했지만 구현 안 된 것은 무엇인가
    한 번도 시험하지 않은 영역은 어디인가
    악의적인 입력을 받으면 어떻게 되는가

한 번도 안 해 본 것들을 골랐다. 지금까지의 측정은 전부
**순차 단일 연결 / RTT 50 ms / 손실 <= 5% / 정상 입력**이었다.

  C1 동시 연결      여러 클라이언트가 겹칠 때 서버 자료구조가 섞이지 않는가
  C2 극단 RTT       5 ms 와 300 ms 에서도 성립하는가 (타이머 상수가 RTT 에 묶여 있나)
  C3 극단 손실      20% 에서 무너지지 않는가
  C4 기형/악성 패리티 공격자가 만든 패리티에 서버가 죽거나 오작동하지 않는가
  C5 장수명 서버    한 프로세스로 오래 돌 때 자료구조가 새지 않는가

Output: experiments/results/p10_completeness.json
"""
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

import padbed as B                      # noqa: E402

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
    """Reject incomplete or malformed runs before computing any success metric."""
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


# ------------------------------------------------------------- C1 동시 연결
def c1_concurrent(results):
    """여러 클라이언트를 동시에 돌린다.

    지금까지 모든 측정이 순차 단일 연결이었다. 서버의 recent/flights 는
    연결이 섞여 들어와도 CRC 를 DCID 안에서만 맞추게 되어 있지만,
    실제로 겹쳐 본 적이 없다.
    """
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


# ------------------------------------------------------------- C2 극단 RTT
def tail_rate(v, thresh):
    if not v:
        return None
    return sum(1 for x in v if x > thresh) / float(len(v))


def c2_rtt(results):
    """RTT 를 극단으로 밀었을 때 두 가지를 따로 잰다.

    🩸 처음에는 손실을 건 채 p95 만 비교했는데, 60 시행 x 3% 손실이면 손실
    사건이 5 개뿐이라 95 분위가 또 경계에 놓인다. RTT 5 ms 에서
    off 9.2 -> on 9.4 가 나왔는데 이게 오버헤드인지 잡음인지 구분이 안 됐다.

    그래서 둘을 갈라 잰다.
      비용  손실 0 에서 p50 차이 = **순수 오버헤드**
      효과  손실 3% 에서 꼬리 비율(왕복 추가 시행 비율) 차이
    """
    rows = []
    for rtt in (5.0, 50.0, 300.0):
        # 🩸 2026-08-28 - 꼬리 기준이 `1.5 * rtt` 였다. 그 식은 **핸드셰이크가
        #    딱 1 왕복**이라고 가정한다. 실제로는 RTT 에 비례하지 않는 고정
        #    비용(암호 연산·직렬화·스케줄링)이 약 2 ms 붙는다 - 실측 세 점이
        #    전부 같은 값을 말한다:
        #        RTT   5 무손실 p50   6.94  (= RTT + 1.94)
        #        RTT  50 무손실 p50  52.45  (= RTT + 2.45)
        #        RTT 300 무손실 p50 302.10  (= RTT + 2.10)
        #    그래서 기준까지의 여유가 RTT 마다 딴판이 된다:
        #        RTT   5   7.50 - 7.09 =   0.41 ms  (왕복의  8%)
        #        RTT  50  75.00 - 52.08 = 22.92 ms  (왕복의 46%)
        #        RTT 300 450.00 - 302.19 = 147.81 ms (왕복의 49%)
        #    RTT 5 에서는 자에 분해능이 없다. 2026-08-28 바퀴에서 중앙값이
        #    **0.15 ms** 움직이자 표본의 58% 가 기준을 넘어가 꼬리가
        #    11.5% -> 70.0% 로 찍혔다. FEC 가 나빠진 게 아니라 자가 무너진
        #    것이다(RTT 50·300 에서는 같은 검사가 8.0%->0.5%, 2.0%->0.0% 로
        #    주장대로 작동했다).
        #
        #    고친 기준: **기준선 팔(off)의 무손실 중앙값 + 0.5 왕복.**
        #    이 검사의 진짜 주장은 「왕복이 하나 더 붙었나」이고, 그 판단의
        #    기준점은 RTT 의 배수가 아니라 **손실 없을 때 실제로 걸린 시간**
        #    이다. 두 팔에 같은 절대 기준을 써야 팔끼리 견줄 수 있으므로
        #    off 팔 하나에서만 뽑는다(그러면 FEC 의 고정 오버헤드도 정직하게
        #    FEC 쪽 꼬리에 잡힌다).
        #
        #    ⚠ `-gap` 은 **핸드셰이크 사이**의 간격이지(client.go:47
        #    "gap between handshakes") 핸드셰이크 안의 간격이 아니다.
        #    한 번의 지연에 영향을 주지 않으므로 RTT 에 맞춰 줄일 것이 없다.
        rec = {"rtt": rtt}

        # (1) 비용 - 손실 0 에서 순수 오버헤드
        for arm, fec in (("off", "off"), ("on", "on")):
            B.set_netem(rtt / 2.0)
            p, sp = B.start_server(CERT, fec=fec)
            try:
                r, cs, err = run_client_checked(GROUP, 150, fec=fec, m=1, gap_ms=4,
                                                timeout_s=10, expect_k=K)
            finally:
                B.stop_server(p)
            s = B.summarize(r, rtt_ms=rtt)
            # p95 도 남긴다 - 아래 분해능 검사가 **이 팔 자신의 흔들림**을
            # 자로 삼는다. 없으면 "여유가 충분한가"를 물을 수가 없다.
            rec["cost_" + arm] = {"p50": s["p50"], "mean": s["mean"],
                                  "p95": s["p95"], "ok": s["ok"], "n": s["n"]}
        cost_valid = all(complete_summary(rec["cost_" + arm], 150)
                         for arm in ("off", "on"))
        overhead = (rec["cost_on"]["p50"] - rec["cost_off"]["p50"]
                    if cost_valid else None)
        rec["overhead_ms"] = overhead

        # 기준선 팔의 무손실 중앙값에서 기준을 뽑는다(위 🩸 참고).
        # 못 재면 옛 식으로 물러서되, **물러섰다는 사실을 기록에 남긴다** -
        # 조용히 옛 자로 채점하면 이 수리가 없던 일이 된다.
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

        # (2) 효과 - 손실 3% 에서 꼬리 비율
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
            # 🩸 2026-08-28 - **연결별 ms 를 남긴다.** 2026-08-28 바퀴에서
            #    이 검사가 붉어졌을 때 요약(tail/p50/ok/n)만 남아 있어서
            #    **새 기준으로 재채점을 할 수 없었다.** 자를 고치면 옛
            #    원자료를 다시 채점할 수 있어야 한다 - 안 그러면 자를 고칠
            #    때마다 그 전 측정이 통째로 버려진다.
            rec["eff_" + arm] = {"tail": tail_rate(ms, tail_thresh),
                                 "p50": s["p50"], "ok": s["ok"], "n": s["n"],
                                 "rec": ss.get("recovered"),
                                 "crc": ss.get("recover_crc_fail"),
                                 "stats_present": server_stats_present(
                                     ss, "recover_crc_fail", "recovered"),
                                 "ms": ms}
        rows.append(rec)

        # 🩸 2026-08-27 - **한쪽 꼬리만 본다.** 옛 조건은 `abs(overhead) < 1`
        #    이었다. 이 검사의 주장은 「FEC 를 켜도 **비용이 안 든다**」이고,
        #    팔이 기준선보다 **빨랐다**는 사실은 그 주장을 반박하지 않는다.
        #    그런데 양쪽 꼬리를 보면 빠른 쪽도 실패로 찍힌다 - 실제로
        #    2026-08-27 바퀴에서 RTT 50 이 **-1.13 ms**(더 빠름)로 붉어졌다.
        #    p16 검사 2 가 2026-08-21 에 정확히 같은 이유로 같은 수리를
        #    받았다("팔이 base 보다 빨랐다는 사실은 그 주장을 반박하지
        #    않는다"). 같은 병이 다른 계기에 남아 있었다.
        #
        #    음수 쪽은 **감추지 않는다** - detail 에 그대로 적고, 그 크기가
        #    자를 넘으면 「표류 의심」으로 드러낸다. 빠른 쪽으로 1 ms 를
        #    넘는 것은 비용이 아니라 **측정이 흔들린다**는 신호이기 때문이다.
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

        # 🩸 2026-08-28 - **자에 분해능이 있는지 먼저 묻는다.** 위 🩸 에서
        #    본 병은 "기준이 틀렸다"만이 아니라 "기준이 틀렸는데도 검사가
        #    당당히 합격/불합격을 말했다"는 것이다. 기준까지의 여유가 이 팔
        #    자신의 흔들림(무손실 p95-p50)에 묻히면, 이 검사는 FEC 가 아니라
        #    잡음을 재는 것이다. 그때는 통과도 실패도 말하지 않는다.
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

        # 분해능이 없으면 꼬리 비교는 **판정하지 않는다.** 조용히 통과시키면
        # 진짜 회귀가 숨고, 조용히 실패시키면 오늘처럼 멀쩡한 알고리즘이
        # 붉어진다. 둘 다 거짓말이므로 판정을 유보하고 그 사실을 적는다.
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


# ------------------------------------------------------------ C3 극단 손실
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


# ----------------------------------------------------- C4 기형/악성 패리티
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
    """공격자가 만든 패리티를 서버에 직접 던진다.

    우리 파서는 공격자 입력을 받는 자리다. 여기서 죽거나, 남의 연결을
    건드리거나, 회계를 뚫으면 안 된다.
    """
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

    # 공격 뒤에도 정상 연결이 되는가
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


# ----------------------------------------------------------- C5 장수명 서버
def c5_longrun(results):
    """한 서버로 오래 돌 때 처지는가.

    🩸 처음에는 "처짐 < 2 ms" 같은 절대 기준을 썼는데 그게 틀렸다. 기준선(off)
    도 같이 처지기 때문이다 - 실제로 off 가 -3.11 / +3.51 ms, on 이
    -2.14 / +1.53 ms 로 **기준선이 더 흔들렸고 방향도 일정하지 않았다.**
    호스트 스케줄링 잡음이지 우리 자료구조가 아니다. 그래서 기준선 대비로 본다.
    """
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


# --------------------------------------------------- 설계 대비 구현 재고조사
def inventory(results):
    """Source inventory only; the separate experiment stages establish behavior."""
    from padfec import policy

    sources, fingerprints = {}, {}
    for name in ("qamp.go", "policy.go", "pfail_table.go"):
        path = os.path.join(HERE, "quicbed", name)
        with open(path, "rb") as stream:
            raw = stream.read()
        fingerprints[name] = hashlib.sha256(raw).hexdigest()
        # Checking named code paths is narrower than finding a word in comments.
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
