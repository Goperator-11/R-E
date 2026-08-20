# -*- coding: utf-8 -*-
"""
E20 - QUIC 증폭 제한과 핸드셰이크 FEC (팀 자료 검증 + 가설 시험)

배경
----
다른 PC에서 측정된 팀 자료(quic_amplification_v2.xlsx)가 이렇게 보고한다:
RFC 9000 §8.1(서버는 주소 검증 전까지 수신 바이트의 3배까지만 송신)에 걸려,
인증서가 어느 크기를 넘으면 핸드셰이크가 1-RTT 에서 2-RTT 로 바뀐다. 그리고
ML-KEM 은 ClientHello 가 커서 **서버 예산도 커지므로 그 임계가 더 높다**:
    X25519         임계 3,300~3,400 B
    X25519MLKEM768 임계 5,900~6,000 B
    사이 구간에서 후양자가 오히려 1 RTT 빠르다 (RTT 50ms 에서 49ms)

이 파일이 확인하는 것
--------------------
Q1. 팀의 임계값이 우리 테스트베드에서 재현되는가            (독립 재현)
Q2. 그 임계가 RFC 9000 §8.1 산술과 맞는가                 (메커니즘)
Q3. 🔬 **핸드셰이크 FEC 가 그 임계를 밀어올리는가**         (새 가설)

Q3 이 이 실험의 이유다. 증폭 예산은 클라이언트가 보낸 바이트의 3배이므로,
핸드셰이크에 이중화를 붙이면 예산도 같이 커져 **왕복 하나를 없앨 수 있다**는
것이 우리 handshake.py 주석에 적혀 있으나 한 번도 측정된 적이 없다.

⚠️ 먼저 확인된 사실: **우리 심의 XOR 패리티는 rx 가 흡수하고 서버로 넘기지
않는다.** 서버의 QUIC 스택이 보는 바이트가 안 늘므로 예산도 안 는다. 즉 이
가설은 현재 구현으로는 성립 자체가 불가능하다. 그래서 팔을 셋으로 나눈다:

    nofec   기준선
    fec     현재 구현(패리티를 rx 가 흡수)      -> 예산 불변 예측
    dup     Initial 데이터그램 복제(= 반복부호)  -> 예산 증가 예측
            유효한 DCID 를 가진 정상 패킷이라 서버가 연결에 귀속시켜 센다.

세 팔의 임계를 비교하면 "메커니즘이 참인가"와 "우리 구현이 그걸 활용하는가"가
분리된다.

네임스페이스 안에서 실행:
    unshare -r -m -n python3 experiments/e20_amplification.py

Output: experiments/results/e20_amplification.json
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RESULTS = os.path.join(HERE, "results")
QBED = os.path.join(HERE, "quicbed")
sys.path.insert(0, HERE)
os.makedirs(RESULTS, exist_ok=True)

from _journal import Journal, code_fingerprint      # noqa: E402

HOME = os.path.expanduser("~")
BIN = os.path.join(HOME, "quicbed", "bin")
TX, RX = "10.9.0.1", "10.9.0.2"
SHIM_TX, SHIM_RX, SERVER = 5555, 5556, 4433
WORK = "/tmp/pqafec_e20"


def _harden():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


def run(cmd, check=True):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError("FAILED: %s\n%s\n%s" % (cmd, r.stdout, r.stderr))
    return r


def setup(mtu=1500):
    run("mount -t tmpfs none /run", check=False)
    os.makedirs("/run/netns", exist_ok=True)
    os.makedirs(WORK, exist_ok=True)
    run("ip netns del rx", check=False)
    run("ip netns add rx")
    run("ip link add veth-tx type veth peer name veth-rx")
    run("ip link set veth-rx netns rx")
    run("ip addr add %s/24 dev veth-tx" % TX)
    run("ip link set veth-tx mtu %d" % mtu)
    run("ip link set veth-tx up")
    run("ip link set lo up")
    run("ip netns exec rx ip addr add %s/24 dev veth-rx" % RX)
    run("ip netns exec rx ip link set veth-rx mtu %d" % mtu)
    run("ip netns exec rx ip link set veth-rx up")
    run("ip netns exec rx ip link set lo up")


def set_delay(one_way_ms):
    """지연만. 손실은 주지 않는다 - 증폭 효과를 손실과 섞으면 안 된다."""
    run("tc qdisc del dev veth-tx root", check=False)
    run("ip netns exec rx tc qdisc del dev veth-rx root", check=False)
    run("tc qdisc add dev veth-tx root netem limit 50000 delay %.3fms" % one_way_ms)
    run("ip netns exec rx tc qdisc add dev veth-rx root netem limit 50000 "
        "delay %.3fms" % one_way_ms)


def start_stack(arm, certsize, flight_ms):
    procs = {}
    procs["server"] = subprocess.Popen(
        ["ip", "netns", "exec", "rx", os.path.join(BIN, "qserver"),
         "-addr", "127.0.0.1:%d" % SERVER, "-certsize", str(certsize)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.8)
    procs["rx"] = subprocess.Popen(
        ["ip", "netns", "exec", "rx", sys.executable,
         os.path.join(QBED, "shim.py"), "--role", "rx",
         "--listen", "%s:%d" % (RX, SHIM_RX),
         "--target", "127.0.0.1:%d" % SERVER],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cmd = [sys.executable, os.path.join(QBED, "shim.py"), "--role", "tx",
           "--listen", "127.0.0.1:%d" % SHIM_TX,
           "--peer", "%s:%d" % (RX, SHIM_RX),
           "--flight-ms", str(flight_ms)]
    if arm == "fec":
        cmd.append("--fec")
    elif arm.startswith("dup"):
        cmd += ["--dup-initial", arm[3:] or "1"]
    procs["tx"] = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
    time.sleep(0.6)
    return procs


def stop_stack(procs):
    for p in procs.values():
        try:
            p.terminate()
        except Exception:
            pass
    time.sleep(0.35)
    for p in procs.values():
        try:
            p.kill()
        except Exception:
            pass


def run_client(group, n, gap_ms, timeout_s):
    r = subprocess.run(
        [os.path.join(BIN, "qclient"), "-addr", "127.0.0.1:%d" % SHIM_TX,
         "-group", group, "-n", str(n), "-gap", "%dms" % int(gap_ms),
         "-timeout", "%ds" % int(timeout_s)],
        capture_output=True, text=True, timeout=timeout_s * n + 120)
    rows = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def classify(times, rtt_ms):
    """1-RTT 인가 2-RTT 인가. HCT ~ n*RTT + 소수 ms 라 경계가 뚜렷하다."""
    if not times:
        return {}
    s = sorted(times)
    p50 = s[len(s) // 2]
    two = sum(1 for t in s if t > 1.5 * rtt_ms)
    return {"n": len(s), "p50": p50, "min": s[0], "max": s[-1],
            "two_rtt_rate": two / len(s),
            "rtt_multiple": p50 / rtt_ms}


def main():
    _harden()
    ap = argparse.ArgumentParser()
    ap.add_argument("--rtt", type=float, default=50.0)
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--gap-ms", type=float, default=12.0)
    ap.add_argument("--timeout", type=float, default=12.0)
    ap.add_argument("--flight-ms", type=float, default=3.0)
    ap.add_argument("--certs", default="3000,3400,4032,5000,5600,5900,6000,"
                                       "7000,8000,10000,12000")
    ap.add_argument("--arms", default="nofec,fec,dup1")
    ap.add_argument("--groups", default="x25519,X25519MLKEM768")
    a = ap.parse_args()

    if not os.path.exists(os.path.join(BIN, "qserver")):
        print("build first: bash experiments/quicbed/build.sh")
        return 2

    print("=" * 100)
    print("E20 - QUIC 증폭 제한과 핸드셰이크 FEC")
    print("      RTT %.0fms · 무손실 · MTU 1500 · 조건당 %d회"
          % (a.rtt, a.n))
    print("=" * 100)
    setup()
    set_delay(a.rtt / 2.0)

    fp = code_fingerprint(["experiments/e20_amplification.py",
                           "experiments/quicbed/shim.py",
                           "experiments/quicbed/client.go",
                           "experiments/quicbed/server.go"], root=ROOT)
    fp += "|%.0f|%d|%s|%s|%s" % (a.rtt, a.n, a.certs, a.arms, a.groups)
    jr = Journal(os.path.join(HERE, "state", "e20_units.jsonl"), fingerprint=fp)
    if len(jr):
        print("재개: 이미 끝난 단위 %d개" % len(jr))

    certs = [int(x) for x in a.certs.split(",")]
    arms = a.arms.split(",")
    groups = a.groups.split(",")
    out = {"rtt_ms": a.rtt, "n": a.n, "certs": certs, "arms": arms,
           "groups": groups, "cells": {}}

    print("")
    print("%-8s %-17s %-7s %9s %9s %10s %8s" %
          ("인증서", "키교환", "팔", "p50(ms)", "RTT배수", "2-RTT율", "복제/패리티"))
    print("-" * 92)
    for cert in certs:
        for group in groups:
            for arm in arms:
                # x25519 는 기준선만 - 팔 비교는 ML-KEM 에서 한다
                if group == "x25519" and arm != "nofec":
                    continue
                key = "%d/%s/%s" % (cert, group, arm)
                rec = jr.get(key)
                if rec is None:
                    procs = start_stack(arm, cert, a.flight_ms)
                    try:
                        rows = run_client(group, a.n, a.gap_ms, a.timeout)
                    finally:
                        stop_stack(procs)
                    ok = [r for r in rows if r.get("ok")]
                    rec = classify([r["ms"] for r in ok], a.rtt)
                    rec["arm"] = arm
                    rec["group"] = group
                    rec["cert"] = cert
                    rec["ok"] = len(ok)
                    rec["trials"] = len(rows)
                    jr.record(key, rec)
                out["cells"][key] = rec
                if not rec.get("n"):
                    print("%-8d %-17s %-7s   (측정 실패)" % (cert, group, arm))
                    continue
                print("%-8d %-17s %-7s %9.1f %9.2f %9.0f%% %8s" %
                      (cert, group, arm, rec["p50"], rec["rtt_multiple"],
                       100 * rec["two_rtt_rate"],
                       "복제" if arm.startswith("dup") else
                       ("패리티" if arm == "fec" else "-")))
        print("")

    # ------------------------------------------------------------- 임계 추출
    def threshold(group, arm):
        prev = None
        for cert in certs:
            r = out["cells"].get("%d/%s/%s" % (cert, group, arm))
            if not r or not r.get("n"):
                continue
            two = r["two_rtt_rate"] > 0.5
            if two and prev is not None:
                return (prev, cert)
            if not two:
                prev = cert
        return (prev, None)

    print("=" * 100)
    print("임계 (1-RTT -> 2-RTT 전환 구간)")
    print("=" * 100)
    ths = {}
    for group in groups:
        for arm in arms:
            if group == "x25519" and arm != "nofec":
                continue
            lo, hi = threshold(group, arm)
            ths["%s/%s" % (group, arm)] = [lo, hi]
            print("  %-17s %-7s : %s" %
                  (group, arm,
                   ("%d ~ %d B" % (lo, hi)) if hi else
                   ("> %s B (전 구간 1-RTT)" % lo if lo else "측정 불가")))
    out["thresholds"] = ths

    # ------------------------------------------------- 팀 자료 및 이론 대조
    print("")
    print("팀 자료(quic_amplification_v2.xlsx) 대조")
    team = {"x25519/nofec": (3300, 3400), "X25519MLKEM768/nofec": (5900, 6000)}
    for k, (tl, th) in team.items():
        mine = ths.get(k)
        if not mine or not mine[1]:
            print("  %-26s 팀 %d~%d B  /  우리 측정 불가" % (k, tl, th))
            continue
        agree = not (mine[1] < tl or mine[0] > th)
        print("  %-26s 팀 %5d~%-5d B  우리 %5d~%-5d B  %s"
              % (k, tl, th, mine[0], mine[1], "일치" if agree else "**불일치**"))

    # ------------------------------------------------------ Q3 가설 판정
    print("")
    print("Q3 판정 — 핸드셰이크 FEC 가 증폭 임계를 밀어올리는가")
    base = ths.get("X25519MLKEM768/nofec")
    fec = ths.get("X25519MLKEM768/fec")
    dup = ths.get("X25519MLKEM768/dup1")

    def lo(x):
        return x[0] if x and x[0] else None

    if base and fec:
        same = (lo(fec) == lo(base))
        print("  현재 구현(패리티 흡수) : 임계 %s -> %s   %s"
              % (lo(base), lo(fec),
                 "예측대로 불변" if same else "**예상과 다름 - 조사 필요**"))
        out["fec_moves_threshold"] = not same
    if base and dup:
        moved = lo(dup) is None or (lo(dup) or 0) > (lo(base) or 0)
        print("  Initial 복제(반복부호) : 임계 %s -> %s   %s"
              % (lo(base), lo(dup) if lo(dup) else "전 구간 1-RTT",
                 "**메커니즘 참**" if moved else "메커니즘 거짓"))
        out["dup_moves_threshold"] = moved

    path = os.path.join(RESULTS, "e20_amplification.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("")
    print("saved: %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
