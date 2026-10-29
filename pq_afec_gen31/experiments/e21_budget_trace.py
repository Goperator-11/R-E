# -*- coding: utf-8 -*-
"""E21 - 증폭 예산(RFC 9000 8.1)을 바이트 단위로 직접 관측한다.

E20 은 "임계가 움직였나"만 봤다. 그런데 dup1 은 임계를 안 움직이고 dup3 은
13 KB 까지 전 구간 1-RTT 였다. 선형 예산 모델(예산 = 3 x 수신바이트)이면
dup1 도 임계를 두 배 가까이 밀어야 하므로, 둘 중 하나는 내 해석이 틀렸다.

그래서 해석을 빼고 **수를 직접 본다**. rx 심은 서버 QUIC 스택 바로 앞에
있으므로, 거기서 기록한 두 수열이 곧 RFC 9000 8.1 의 좌변과 우변이다.

    to_srv   : 서버가 받은 바이트  -> 예산 = 3 x 누적
    from_srv : 서버가 보낸 바이트  -> 이 누적이 예산에 닿으면 서버가 멈춘다

서버가 멈춘 지점에서 (보낸 누적) / (받은 누적) 이 3.0 에 붙으면 증폭 한계가
실제로 구속(binding)한 것이고, 3.0 에 한참 못 미치는데 멈췄으면 다른 것이
원인이다. 이 스크립트는 그 비율을 각 팔마다 뽑는다.
"""
from __future__ import print_function

import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import e20_amplification as E20  # noqa: E402

OUT = os.path.join(HERE, "results", "e21_budget_trace.json")


def trace_once(arm, certsize, group, rtt_ms, flight_ms=3.0):
    """한 번의 핸드셰이크 동안 rx 심이 본 바이트 타임라인을 돌려준다."""
    tracef = "/tmp/e21_trace_%s_%d.json" % (arm, certsize)
    try:
        os.unlink(tracef)
    except OSError:
        pass

    procs = {}
    procs["server"] = subprocess.Popen(
        ["ip", "netns", "exec", "rx", os.path.join(E20.BIN, "qserver"),
         "-addr", "127.0.0.1:%d" % E20.SERVER, "-certsize", str(certsize)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.8)
    procs["rx"] = subprocess.Popen(
        ["ip", "netns", "exec", "rx", sys.executable,
         os.path.join(E20.QBED, "shim.py"), "--role", "rx",
         "--listen", "%s:%d" % (E20.RX, E20.SHIM_RX),
         "--target", "127.0.0.1:%d" % E20.SERVER,
         "--trace", tracef],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cmd = [sys.executable, os.path.join(E20.QBED, "shim.py"), "--role", "tx",
           "--listen", "127.0.0.1:%d" % E20.SHIM_TX,
           "--peer", "%s:%d" % (E20.RX, E20.SHIM_RX),
           "--flight-ms", str(flight_ms)]
    if arm == "fec":
        cmd.append("--fec")
    elif arm.startswith("dup"):
        cmd += ["--dup-initial", arm[3:] or "1"]
    procs["tx"] = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
    time.sleep(0.6)

    rows = E20.run_client(group, 1, 0, 20)
    time.sleep(0.4)
    # rx 심만 먼저 정중히 내려서 트레이스를 받아낸다.
    try:
        procs["rx"].terminate()
        procs["rx"].wait(timeout=3)
    except Exception:
        pass
    E20.stop_stack(procs)

    tr = None
    for _ in range(20):
        if os.path.exists(tracef):
            try:
                tr = json.load(open(tracef))
                break
            except Exception:
                pass
        time.sleep(0.1)
    return rows, tr


def analyse(tr, rtt_ms):
    """타임라인에서 '서버가 멈춘 지점'과 그때의 증폭비를 뽑는다."""
    if not tr or not tr.get("events"):
        return None
    ev = sorted(tr["events"], key=lambda e: e[0])
    rx_cum = 0
    tx_cum = 0
    steps = []
    for t, kind, n in ev:
        if kind == "to_srv":
            rx_cum += n
        else:
            tx_cum += n
        steps.append({"t": t, "kind": kind, "n": n,
                      "rx_cum": rx_cum, "tx_cum": tx_cum,
                      "budget": 3 * rx_cum,
                      "headroom": 3 * rx_cum - tx_cum})

    # 첫 정지: from_srv 가 끊긴 뒤 다음 from_srv 까지의 간격이 RTT 의 절반을
    # 넘는 지점. 그 직전 상태가 '서버가 더 못 보낸 순간'이다.
    stall = None
    last_tx = None
    for st in steps:
        if st["kind"] != "from_srv":
            continue
        if last_tx is not None and st["t"] - last_tx["t"] > 0.5 * rtt_ms:
            stall = last_tx
            break
        last_tx = st
    if stall is None and last_tx is not None:
        stall = last_tx

    first_burst_end = stall
    return {
        "n_events": len(steps),
        "rx_total": rx_cum,
        "tx_total": tx_cum,
        "stall_t": first_burst_end["t"] if first_burst_end else None,
        "stall_rx_cum": first_burst_end["rx_cum"] if first_burst_end else None,
        "stall_tx_cum": first_burst_end["tx_cum"] if first_burst_end else None,
        "stall_ratio": (first_burst_end["tx_cum"] /
                        float(first_burst_end["rx_cum"]))
        if first_burst_end and first_burst_end["rx_cum"] else None,
        "steps": steps[:60],
    }


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--rtt", type=float, default=50.0)
    ap.add_argument("--certs", default="6000")
    ap.add_argument("--arms", default="nofec,dup1,dup2,dup3")
    ap.add_argument("--group", default="X25519MLKEM768")
    a = ap.parse_args()

    if os.geteuid() != 0:
        print("netns 가 필요하다: unshare -r -m -n python3 ...", file=sys.stderr)
        return 2
    if not os.path.exists(os.path.join(E20.BIN, "qserver")):
        print("qserver 바이너리가 없다", file=sys.stderr)
        return 2

    E20.setup()
    E20.set_delay(a.rtt / 2.0)

    certs = [int(x) for x in a.certs.split(",")]
    arms = a.arms.split(",")
    out = {"rtt_ms": a.rtt, "group": a.group, "runs": []}

    for cert in certs:
        for arm in arms:
            rows, tr = trace_once(arm, cert, a.group, a.rtt)
            an = analyse(tr, a.rtt)
            hct = [r.get("ms") for r in rows if r.get("ok")]
            rec = {"arm": arm, "cert": cert, "hct_ms": hct,
                   "kem": rows[0].get("kem_id") if rows else None,
                   "shim_stats": (tr or {}).get("stats"),
                   "analysis": an}
            out["runs"].append(rec)

            print("=" * 78)
            print("팔 %-6s  cert %5d B   HCT %s ms   kem %s"
                  % (arm, cert,
                     ("%.1f" % hct[0]) if hct else "실패",
                     rec["kem"]))
            if not an:
                print("  (트레이스 없음)")
                continue
            print("  서버 수신 총 %5d B / 송신 총 %5d B"
                  % (an["rx_total"], an["tx_total"]))
            print("  정지 시점 t=%.1f ms  수신누적 %5d B  송신누적 %5d B  "
                  "증폭비 %.2f  (한계 3.00)"
                  % (an["stall_t"], an["stall_rx_cum"], an["stall_tx_cum"],
                     an["stall_ratio"] or 0.0))
            print("  %-8s %-9s %6s %8s %8s %8s %8s"
                  % ("t(ms)", "방향", "bytes", "수신누적", "송신누적",
                     "예산3x", "여유"))
            for st in an["steps"][:24]:
                print("  %8.2f %-9s %6d %8d %8d %8d %8d"
                      % (st["t"],
                         "->서버" if st["kind"] == "to_srv" else "서버->",
                         st["n"], st["rx_cum"], st["tx_cum"],
                         st["budget"], st["headroom"]))

    try:
        os.makedirs(os.path.dirname(OUT))
    except OSError:
        pass
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    print("\nsaved:", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
