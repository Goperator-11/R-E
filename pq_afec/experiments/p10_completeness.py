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
import os
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
    results.append({"check": name, "ok": bool(ok), "detail": detail,
                    "kind": kind})
    print("[%s] %-54s %s" % ("통과" if ok else "미흡", name, detail[:78]))
    sys.stdout.flush()


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
        r = subprocess.run(
            ["timeout", "180", qamp, "-mode", "client",
             "-addr", "%s:%d" % (B.RX_IP, B.SERVER_PORT),
             "-group", GROUP, "-n", "60", "-fec", "on", "-m", "1",
             "-gap", "5ms", "-timeout", "8s", "-expect-k", str(K)],
            capture_output=True, text=True)
        ok = sum(1 for ln in r.stdout.splitlines()
                 if ln.strip().startswith("{")
                 and json.loads(ln)["ok"])
        n = sum(1 for ln in r.stdout.splitlines()
                if ln.strip().startswith("{"))
        with lock:
            out[i] = (ok, n)

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    B.stop_server(p)
    ss = B.read_server_stats(sp)
    tot_ok = sum(v[0] for v in out.values())
    tot_n = sum(v[1] for v in out.values())
    crc = ss.get("recover_crc_fail") or 0
    bad_acct = (ss.get("bytes_to_stack") or 0) > (ss.get("bytes_in") or 0)
    add(results,
        "C1 동시 연결 6개 x 60회 (손실 3%) - 성공률과 회계가 유지되는가",
        tot_ok == tot_n and crc == 0 and not bad_acct,
        "성공 %d/%d, 복구 %s, CRC거절 %s, 회계 %s"
        % (tot_ok, tot_n, ss.get("recovered"), crc,
           "위반" if bad_acct else "정상"))
    return {"ok": tot_ok, "n": tot_n, "srv": ss}


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
            r, cs, err = B.run_client(GROUP, 150, fec=fec, m=1, gap_ms=4,
                                      timeout_s=10, expect_k=K)
            B.stop_server(p)
            s = B.summarize(r, rtt_ms=rtt)
            # p95 도 남긴다 - 아래 분해능 검사가 **이 팔 자신의 흔들림**을
            # 자로 삼는다. 없으면 "여유가 충분한가"를 물을 수가 없다.
            rec["cost_" + arm] = {"p50": s["p50"], "mean": s["mean"],
                                  "p95": s["p95"], "ok": s["ok"], "n": s["n"]}
        overhead = (rec["cost_on"]["p50"] or 0) - (rec["cost_off"]["p50"] or 0)
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
            None if _base is None else tail_thresh - (rec["cost_on"]["p50"] or _base))

        # (2) 효과 - 손실 3% 에서 꼬리 비율
        for arm, fec in (("off", "off"), ("on", "on")):
            B.set_netem(rtt / 2.0, loss_c2s=3.0)
            p, sp = B.start_server(CERT, fec=fec)
            r, cs, err = B.run_client(GROUP, 200, fec=fec, m=1, gap_ms=4,
                                      timeout_s=10, expect_k=K)
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
        _drift = "" if overhead > -1.0 else (
            "  ⚠ 기준선보다 %.2f ms 빨랐다 - 비용이 아니라 표류 의심"
            % (-overhead))
        add(results,
            "C2 RTT %.0f ms - 순수 오버헤드가 1 ms 미만인가 (한쪽 꼬리)" % rtt,
            overhead < 1.0,
            "손실 0 에서 p50 %.2f -> %.2f ms (오버헤드 %+.2f ms, "
            "RTT 대비 %+.1f%%)%s"
            % (rec["cost_off"]["p50"] or -1, rec["cost_on"]["p50"] or -1,
               overhead, 100 * overhead / rtt, _drift))

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
                b["ok"] == b["n"] and (b["crc"] or 0) == 0
                and (b["tail"] or 0) <= (a["tail"] or 0),
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
            r, cs, err = B.run_client(GROUP, 120, fec=fec, m=1, gap_ms=5,
                                      timeout_s=10, expect_k=K)
            B.stop_server(p)
            ss = B.read_server_stats(sp)
            s = B.summarize(r, rtt_ms=RTT_MS)
            recs[arm] = {"p50": s["p50"], "p95": s["p95"], "ok": s["ok"],
                         "n": s["n"], "rec": ss.get("recovered"),
                         "crc": ss.get("recover_crc_fail"),
                         "unrec": ss.get("unrecoverable_seen")}
        rows.append({"loss": loss, **recs})
        add(results,
            "C3 손실 %.0f%% 에서 무너지지 않는가 (성공률 유지, 잘못된 복구 0)"
            % loss,
            recs["on"]["ok"] == recs["on"]["n"]
            and (recs["on"]["crc"] or 0) == 0
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
    r, cs, err = B.run_client(GROUP, 30, fec="on", m=1, gap_ms=8,
                              timeout_s=8, expect_k=K)
    B.stop_server(p)
    ss = B.read_server_stats(sp)
    su = B.summarize(r, rtt_ms=RTT_MS)
    ok = (alive_before and su["ok"] == su["n"]
          and (ss.get("recover_crc_fail") or 0) == 0
          and (ss.get("bytes_to_stack") or 0) <= (ss.get("bytes_in") or 0))
    add(results,
        "C4 기형/악성 패리티 %d개 투입 후에도 서버 생존 + 정상 연결 + 회계 유지"
        % sent, ok,
        "서버 생존 %s, 공격 후 성공 %d/%d, CRC거절 %s, 회계 %s"
        % (alive_before, su["ok"], su["n"], ss.get("recover_crc_fail"),
           "정상" if (ss.get("bytes_to_stack") or 0)
           <= (ss.get("bytes_in") or 0) else "위반"))
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
        r, cs, err = B.run_client(GROUP, 600, fec=fec, m=1, gap_ms=4,
                                  timeout_s=8, expect_k=K)
        B.stop_server(p)
        ss = B.read_server_stats(sp)
        s = B.summarize(r, rtt_ms=RTT_MS)
        ms = [x["ms"] for x in r if x.get("ok")]
        first, last = ms[:100], ms[-100:]
        drift = ((sum(last) / len(last)) - (sum(first) / len(first))
                 if first and last else None)
        rec[arm] = {"ok": s["ok"], "n": s["n"], "drift": drift,
                    "recovered": ss.get("recovered"),
                    "crc": ss.get("recover_crc_fail")}
    d_on = abs(rec["on"]["drift"] or 0.0)
    d_off = abs(rec["off"]["drift"] or 0.0)
    add(results,
        "C5 한 서버로 600 연결 - FEC 가 기준선보다 더 처지지 않는가",
        rec["on"]["ok"] == rec["on"]["n"] and (rec["on"]["crc"] or 0) == 0
        and d_on <= d_off + 2.0,
        "처짐 off %+.2f ms / on %+.2f ms, 성공 %d/%d, 복구 %s, CRC거절 %s"
        % (rec["off"]["drift"] or 0, rec["on"]["drift"] or 0,
           rec["on"]["ok"], rec["on"]["n"], rec["on"]["recovered"],
           rec["on"]["crc"]))
    return rec


# --------------------------------------------------- 설계 대비 구현 재고조사
def inventory(results):
    """설계했지만 구현 안 된 것을 정직하게 센다."""
    qamp = open(os.path.join(HERE, "quicbed", "qamp.go"),
                encoding="utf-8").read()
    gaps = []

    closed_loop = "policy" in qamp
    gaps.append({
        "item": "적응 정책의 폐루프",
        "designed": "padfec/policy.py 가 (C, k, W, cert, p, L, RTT) 로 m 을 고른다",
        "implemented": "아니다 - m 은 -m 플래그로 사람이 준다",
        "ok": closed_loop,
        "why": "정책이 필요로 하는 서버 비행 크기(cert)와 손실률 p 를 "
               "클라이언트가 **첫 접속 순간에는 알 수 없다**. 알려면 "
               "목적지별 캐시가 있어야 하는데 2차 범위 밖으로 뒀다."})

    gaps.append({
        "item": "서버 -> 클라이언트 방향 보호",
        "designed": "없음 (설계상 제외)",
        "implemented": "없음",
        "ok": False,
        "why": "서버 비행에는 패딩이 없고(인증서로 꽉 찬다) 서버에게 쓸 수 "
               "있는 무료 바이트도 없다. 원리적 제외이지 미구현이 아니다."})

    gaps.append({
        "item": "제자리(패딩 자리) 배치",
        "designed": "인수인계 문서 단계 2-B",
        "implemented": "아니다 - 용량 부등식 위반으로 불가 판정",
        "ok": False,
        "why": "C <= (k-1)(W-h-f) 를 실측 12개 설정 전부가 위반한다. "
               "미구현이 아니라 **불가능하다는 결과**다."})

    gaps.append({
        "item": "k(비행 데이터그램 수) 제어",
        "designed": "용량 정리는 k 를 늘리면 제자리가 가능해진다고 말한다",
        "implemented": "아니다 - quic-go 가 정하는 값을 받아들인다",
        "ok": False,
        "why": "k 를 늘리려면 패킷 번호 공간을 건드려야 하고, 그러면 "
               "클라이언트가 보내지 않은 PN 의 ACK 를 받아 "
               "PROTOCOL_VIOLATION 이 된다."})

    gaps.append({
        "item": "m >= 3",
        "designed": "정책 상한은 policy.M_MAX_DEFAULT (2026-08-25 실측으로 3)",
        "implemented": "부호는 임의 m 을 지원",
        "ok": False,
        "why": "필요를 못 봤다. 부호·복호는 되지만 정책이 고르지 않는다."})

    for g in gaps:
        add(results, "재고: %s" % g["item"], g["ok"],
            "%s | %s" % (g["implemented"], g["why"][:60]), kind="재고")
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
           "open_gaps": len(open_gaps)}
    print("saved:", B.save("p10_completeness.json", out))
    return 0 if npass == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
