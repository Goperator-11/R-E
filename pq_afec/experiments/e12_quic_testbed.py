# -*- coding: utf-8 -*-
"""
E12 - the real thing: ML-KEM + QUIC + FEC on a controlled lossy link

    [netns A]  qclient(Go/quic-go) -> shim tx  ==veth+netem==>  shim rx -> qserver  [netns B]

Everything here is real software doing real work:
  * quic-go handshakes, Go crypto/tls negotiating X25519MLKEM768 (real ML-KEM)
  * a real Linux netem link with MTU 1500, so ML-KEM really does split the
    ClientHello across two datagrams (the flaw the team's 1st sweep had was
    MTU 65536 on loopback, which hid the split entirely)
  * a real XOR parity packet on the wire when --fec is on
  * handshake completion time measured inside the client around quic.DialAddr

Run it inside a namespace, no root needed:
    unshare -r -m -n python3 experiments/e12_quic_testbed.py

Output: experiments/results/e12_quic_testbed.json
"""
import argparse
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)      # 저널 지문이 참조하는 코드 경로의 기준
sys.path.insert(0, HERE)
from _journal import Journal, code_fingerprint     # noqa: E402
RESULTS = os.path.join(HERE, "results")
QBED = os.path.join(HERE, "quicbed")
os.makedirs(RESULTS, exist_ok=True)

HOME = os.path.expanduser("~")
BIN = os.path.join(HOME, "quicbed", "bin")
TX_IP = "10.9.0.1"
RX_IP = "10.9.0.2"
SHIM_TX_PORT = 5555      # client dials this, inside netns A
SHIM_RX_PORT = 5556      # tunnel endpoint, inside netns B
SERVER_PORT = 4433
WORK = "/tmp/pqafec_quicbed"


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


def setup_testbed(mtu):
    run("mount -t tmpfs none /run", check=False)
    os.makedirs("/run/netns", exist_ok=True)
    os.makedirs(WORK, exist_ok=True)
    run("ip netns del rx", check=False)
    run("ip netns add rx")
    run("ip link add veth-tx type veth peer name veth-rx")
    run("ip link set veth-rx netns rx")
    run("ip addr add %s/24 dev veth-tx" % TX_IP)
    # ⚠️ MTU 1500. The team's 1st sweep ran on loopback with MTU 65,536, so
    # every KEM fitted in one segment and the split hypothesis was untestable.
    run("ip link set veth-tx mtu %d" % mtu)
    run("ip link set veth-tx up")
    run("ip link set lo up")
    run("ip netns exec rx ip addr add %s/24 dev veth-rx" % RX_IP)
    run("ip netns exec rx ip link set veth-rx mtu %d" % mtu)
    run("ip netns exec rx ip link set veth-rx up")
    run("ip netns exec rx ip link set lo up")
    run("ip link set dev veth-tx txqueuelen 10000", check=False)


def set_netem(spec_tx, spec_rx):
    """Symmetric netem: each direction gets its own qdisc on its egress."""
    run("tc qdisc del dev veth-tx root", check=False)
    run("ip netns exec rx tc qdisc del dev veth-rx root", check=False)
    out = []
    if spec_tx:
        run("tc qdisc add dev veth-tx root netem limit 20000 %s" % spec_tx)
        out.append(run("tc qdisc show dev veth-tx").stdout.strip())
    if spec_rx:
        run("ip netns exec rx tc qdisc add dev veth-rx root netem limit 20000 %s"
            % spec_rx)
        out.append(run("ip netns exec rx tc qdisc show dev veth-rx").stdout.strip())
    return " | ".join(out)


def gemodel_spec(p, L):
    r = 1.0 / L
    q = p * r / (1.0 - p)
    return "loss gemodel %.4f%% %.4f%%" % (q * 100.0, r * 100.0)


def start_stack(fec, flight_ms, certsize, delay_ms):
    """server + rx shim inside netns rx, tx shim in the current netns."""
    logs = {}
    procs = {}
    srv_log = open(os.path.join(WORK, "server.log"), "wb")
    procs["server"] = subprocess.Popen(
        ["ip", "netns", "exec", "rx", os.path.join(BIN, "qserver"),
         "-addr", "127.0.0.1:%d" % SERVER_PORT, "-certsize", str(certsize)],
        stdout=subprocess.DEVNULL, stderr=srv_log)
    logs["server"] = srv_log
    time.sleep(0.8)

    rx_stats = os.path.join(WORK, "rx_stats.txt")
    procs["shim_rx"] = subprocess.Popen(
        ["ip", "netns", "exec", "rx", sys.executable,
         os.path.join(QBED, "shim.py"), "--role", "rx",
         "--listen", "%s:%d" % (RX_IP, SHIM_RX_PORT),
         "--target", "127.0.0.1:%d" % SERVER_PORT,
         "--stats", rx_stats],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    tx_stats = os.path.join(WORK, "tx_stats.txt")
    cmd = [sys.executable, os.path.join(QBED, "shim.py"), "--role", "tx",
           "--listen", "127.0.0.1:%d" % SHIM_TX_PORT,
           "--peer", "%s:%d" % (RX_IP, SHIM_RX_PORT),
           "--flight-ms", str(flight_ms), "--stats", tx_stats]
    if fec:
        cmd.append("--fec")
    procs["shim_tx"] = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL)
    time.sleep(0.6)
    return procs, logs, tx_stats, rx_stats


def stop_stack(procs, logs):
    for p in procs.values():
        try:
            p.terminate()
        except Exception:
            pass
    time.sleep(0.4)
    for p in procs.values():
        try:
            p.kill()
        except Exception:
            pass
    for f in logs.values():
        try:
            f.close()
        except Exception:
            pass


def run_client(group, n, gap_ms, timeout_s):
    r = subprocess.run(
        [os.path.join(BIN, "qclient"),
         "-addr", "127.0.0.1:%d" % SHIM_TX_PORT,
         "-group", group, "-n", str(n),
         "-gap", "%dms" % int(gap_ms),
         "-timeout", "%ds" % int(timeout_s)],
        capture_output=True, text=True, timeout=timeout_s * n + 120)
    rows = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
    return rows, r.stderr[-400:]


def q(xs):
    if not xs:
        return {}
    s = sorted(xs)
    def pct(f):
        return s[min(len(s) - 1, int(round(f * (len(s) - 1))))]
    return {"n": len(s), "mean": statistics.mean(s), "sd":
            statistics.stdev(s) if len(s) > 1 else 0.0,
            "p50": pct(0.5), "p90": pct(0.9), "p95": pct(0.95),
            "p99": pct(0.99), "max": s[-1], "min": s[0]}


def read_stats(path):
    try:
        with open(path) as f:
            return eval(f.read())
    except Exception:
        return {}


def main():
    _harden()
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200, help="handshakes per arm")
    ap.add_argument("--mtu", type=int, default=1500)
    ap.add_argument("--rtt", type=float, default=20.0, help="total RTT ms")
    ap.add_argument("--certsize", type=int, default=2955)
    ap.add_argument("--flight-ms", type=float, default=3.0)
    ap.add_argument("--gap-ms", type=float, default=15.0)
    ap.add_argument("--timeout", type=float, default=12.0)
    a = ap.parse_args()

    if not os.path.exists(os.path.join(BIN, "qserver")):
        print("build first: bash experiments/quicbed/build.sh")
        return 2

    print("=" * 104)
    print("E12 - real quic-go + real ML-KEM + real XOR parity over real netem")
    print("      MTU=%d  RTT=%.0fms  cert=%dB  n=%d per arm"
          % (a.mtu, a.rtt, a.certsize, a.n))
    print("=" * 104)
    setup_testbed(a.mtu)

    half = a.rtt / 2.0
    delay = "delay %.1fms" % half

    conditions = [
        ("noloss", None),
        ("uniform_p2", "loss 2%"),
        ("uniform_p5", "loss 5%"),
        ("uniform_p10", "loss 10%"),
        ("burst_p5_L4", gemodel_spec(0.05, 4.0)),
        ("burst_p5_L8", gemodel_spec(0.05, 8.0)),
    ]
    groups = ["x25519", "X25519MLKEM768"]

    out = {"mtu": a.mtu, "rtt_ms": a.rtt, "certsize": a.certsize, "n": a.n,
           "flight_ms": a.flight_ms, "arms": {}}

    # 단계 내부 재개: 팔(조건 x 그룹 x FEC) 하나가 끝날 때마다 저널에 남긴다.
    fp = hashlib.sha256(json.dumps(
        {"mtu": a.mtu, "rtt": a.rtt, "cert": a.certsize, "n": a.n,
         "flight_ms": a.flight_ms, "gap": a.gap_ms,
         "code": code_fingerprint(
             ["experiments/quicbed/shim.py",
              "experiments/quicbed/client.go",
              "experiments/quicbed/server.go"], root=ROOT)},
        sort_keys=True).encode()).hexdigest()[:16]
    jr = Journal(os.path.join(HERE, "state", "e12_units.jsonl"), fingerprint=fp)
    if len(jr):
        print("재개: 이미 끝난 팔 %d개는 건너뛴다" % len(jr))

    print("")
    print("%-14s %-16s %-4s %5s %8s %8s %8s %8s %8s %7s" %
          ("condition", "group", "fec", "ok%", "p50", "mean", "p90", "p95",
           "max", "recov"))
    print("-" * 104)

    for cname, closs in conditions:
        spec = (closs + " " + delay) if closs else delay
        for group in groups:
            fec_modes = [False] if (group == "x25519" or closs is None) else [False, True]
            if closs is None:
                fec_modes = [False]
            for fec in fec_modes:
                label = "%s/%s/%s" % (cname, group, "fec" if fec else "nofec")
                cached = jr.get(label)
                if cached is not None:
                    out["arms"][label] = cached
                    qq = cached.get("quantiles") or {}
                    print("%-14s %-16s %-4s %4d%% %8.1f %8.1f %8.1f %8.1f %8.1f %7s  (재개)"
                          % (cname, group, "on" if fec else "off",
                             (100 * cached["ok"] // max(cached["trials"], 1)),
                             qq.get("p50", 0), qq.get("mean", 0), qq.get("p90", 0),
                             qq.get("p95", 0), qq.get("max", 0),
                             str(cached.get("shim_rx", {}).get("recovered", "-"))))
                    continue
                set_netem(spec, spec)
                procs, logs, txs, rxs = start_stack(fec, a.flight_ms,
                                                    a.certsize, half)
                try:
                    rows, err = run_client(group, a.n, a.gap_ms, a.timeout)
                finally:
                    stop_stack(procs, logs)
                ok = [r for r in rows if r.get("ok")]
                times = [r["ms"] for r in ok]
                st_tx, st_rx = read_stats(txs), read_stats(rxs)
                arm = {
                    "condition": cname, "netem": spec, "group": group,
                    "fec": fec, "trials": len(rows), "ok": len(ok),
                    "quantiles": q(times), "times_ms": times,
                    "kem_ids": sorted(set(r.get("kem_id") for r in ok)),
                    "shim_tx": st_tx, "shim_rx": st_rx,
                }
                out["arms"][label] = arm
                jr.record(label, arm)     # 재개 지점
                qq = arm["quantiles"] or {}
                print("%-14s %-16s %-4s %4d%% %8.1f %8.1f %8.1f %8.1f %8.1f %7s" %
                      (cname, group, "on" if fec else "off",
                       (100 * len(ok) // max(len(rows), 1)),
                       qq.get("p50", 0), qq.get("mean", 0), qq.get("p90", 0),
                       qq.get("p95", 0), qq.get("max", 0),
                       str(st_rx.get("recovered", "-"))))

    set_netem(None, None)

    # ---------------------------------------------------------------- guard
    # 🩸 A harness that quietly drops packets will produce beautiful-looking
    # numbers that mean nothing.  The no-loss arms are the control: with netem
    # applying delay only, EVERY handshake must take about one RTT.  If the
    # tail runs away there, the loss is coming from the harness, not the link.
    # (This check exists because the first run had p90 = 222 ms at zero loss -
    # a one-byte flight id wrapping every 255 connections.)
    print("")
    print("SELF-CHECK - no-loss control arms (tail must not run away)")
    bad = []
    for label, arm in out["arms"].items():
        if arm["condition"] != "noloss" or not arm["quantiles"]:
            continue
        qd = arm["quantiles"]
        ratio = qd["p99"] / qd["p50"] if qd["p50"] else 0
        ok = ratio < 1.5
        print("   %-34s p50 %6.1f  p99 %7.1f  ratio %.2f  %s"
              % (label, qd["p50"], qd["p99"], ratio, "ok" if ok else "*** FAIL ***"))
        if not ok:
            bad.append(label)
    out["self_check_noloss_failed"] = bad
    if bad:
        print("   >>> the harness is losing packets on a lossless link.")
        print("   >>> every number below is contaminated; fix before reading.")

    path = os.path.join(RESULTS, "e12_quic_testbed.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("")
    print("saved: %s" % path)

    # ---- the two questions this experiment exists to answer
    print("")
    print("Q1  does ML-KEM cost anything on a real lossy link? (no FEC)")
    for cname, _ in conditions:
        a1 = out["arms"].get("%s/x25519/nofec" % cname)
        a2 = out["arms"].get("%s/X25519MLKEM768/nofec" % cname)
        if not a1 or not a2 or not a1["quantiles"]:
            continue
        for st in ("p50", "mean", "p95"):
            d = a2["quantiles"][st] - a1["quantiles"][st]
            rel = 100.0 * d / a1["quantiles"][st]
            print("   %-14s %-5s x25519 %8.1f -> ML-KEM %8.1f ms  (%+.1f%%)"
                  % (cname, st, a1["quantiles"][st], a2["quantiles"][st], rel))
    print("")
    print("Q2  does one real XOR parity packet buy anything?")
    for cname, _ in conditions:
        a1 = out["arms"].get("%s/X25519MLKEM768/nofec" % cname)
        a2 = out["arms"].get("%s/X25519MLKEM768/fec" % cname)
        if not a1 or not a2 or not a1["quantiles"] or not a2["quantiles"]:
            continue
        for st in ("p50", "mean", "p95", "p99"):
            b = a1["quantiles"].get(st, 0)
            f = a2["quantiles"].get(st, 0)
            rel = 100.0 * (f - b) / b if b else 0
            print("   %-14s %-5s nofec %8.1f -> fec %8.1f ms  (%+.1f%%)"
                  % (cname, st, b, f, rel))
    return 0


if __name__ == "__main__":
    sys.exit(main())
