import argparse
import hashlib
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from _journal import Journal, code_fingerprint
RESULTS = os.path.join(HERE, "results")
QBED = os.path.join(HERE, "quicbed")
os.makedirs(RESULTS, exist_ok=True)

HOME = os.path.expanduser("~")
BIN = os.path.join(HOME, "quicbed", "bin")
TX_IP = "10.9.0.1"
RX_IP = "10.9.0.2"
SHIM_TX_PORT = 6555
SHIM_RX_PORT = 6556
SERVER_PORT = 4444
WORK = "/tmp/pqafec_data"


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


def setup(mtu):
    run("mount -t tmpfs none /run", check=False)
    os.makedirs("/run/netns", exist_ok=True)
    os.makedirs(WORK, exist_ok=True)
    run("ip netns del rx", check=False)
    run("ip netns add rx")
    run("ip link add veth-tx type veth peer name veth-rx")
    run("ip link set veth-rx netns rx")
    run("ip addr add %s/24 dev veth-tx" % TX_IP)
    run("ip link set veth-tx mtu %d" % mtu)
    run("ip link set veth-tx up")
    run("ip link set lo up")
    run("ip netns exec rx ip addr add %s/24 dev veth-rx" % RX_IP)
    run("ip netns exec rx ip link set veth-rx mtu %d" % mtu)
    run("ip netns exec rx ip link set veth-rx up")
    run("ip netns exec rx ip link set lo up")
    run("ip link set dev veth-tx txqueuelen 20000", check=False)


def set_netem(spec):
    run("tc qdisc del dev veth-tx root", check=False)
    run("ip netns exec rx tc qdisc del dev veth-rx root", check=False)
    if spec:
        run("tc qdisc add dev veth-tx root netem limit 50000 %s" % spec)
        run("ip netns exec rx tc qdisc add dev veth-rx root netem limit 50000 %s"
            % spec)


def gemodel(p, L):
    r = 1.0 / L
    q = p * r / (1.0 - p)
    return "loss gemodel %.4f%% %.4f%%" % (q * 100.0, r * 100.0)


def one_run(policy, spec, n, size, pps, rate_mbps, budget_ms, static_ratio,
            timeout, rtt_ms):
    set_netem(spec)
    summary = os.path.join(WORK, "summary.json")
    tx_stats = os.path.join(WORK, "tx.txt")
    rx_stats = os.path.join(WORK, "rx.txt")
    for f in (summary, tx_stats, rx_stats):
        if os.path.exists(f):
            os.remove(f)

    srv = subprocess.Popen(
        ["ip", "netns", "exec", "rx", os.path.join(BIN, "qdata"),
         "-role", "server", "-addr", "127.0.0.1:%d" % SERVER_PORT,
         "-n", str(n), "-size", str(size), "-out", summary],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.9)

    rx = subprocess.Popen(
        ["ip", "netns", "exec", "rx", sys.executable,
         os.path.join(QBED, "shim_data.py"), "--role", "rx",
         "--listen", "%s:%d" % (RX_IP, SHIM_RX_PORT),
         "--target", "127.0.0.1:%d" % SERVER_PORT, "--stats", rx_stats],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.4)

    tx = subprocess.Popen(
        [sys.executable, os.path.join(QBED, "shim_data.py"), "--role", "tx",
         "--listen", "127.0.0.1:%d" % SHIM_TX_PORT,
         "--peer", "%s:%d" % (RX_IP, SHIM_RX_PORT),
         "--policy", policy, "--static-ratio", str(static_ratio),
         "--rate-mbps", str(rate_mbps), "--budget-ms", str(budget_ms),
         "--symbol-bytes", str(size), "--rtt-ms", str(rtt_ms),
         "--stats", tx_stats],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.5)

    cli_err = ""
    timed_out = False
    try:
        cli = subprocess.run(
            [os.path.join(BIN, "qdata"), "-role", "client",
             "-addr", "127.0.0.1:%d" % SHIM_TX_PORT,
             "-n", str(n), "-size", str(size), "-pps", str(pps)],
            capture_output=True, text=True, timeout=timeout)
        cli_err = cli.stderr
    except subprocess.TimeoutExpired as e:
        timed_out = True
        cli_err = (e.stderr or b"").decode("utf-8", "replace") if e.stderr else ""

    try:
        srv.wait(timeout=20)
    except Exception:
        srv.kill()
    for p in (tx, rx):
        p.terminate()
    time.sleep(0.5)
    for p in (tx, rx):
        try:
            p.kill()
        except Exception:
            pass

    def rd(path, js=False):
        try:
            with open(path) as f:
                t = f.read()
            return json.loads(t) if js else eval(t)
        except Exception:
            return {}

    sent = skipped = None
    elapsed_ms = None
    for tok in cli_err.split():
        pass
    parts = cli_err.replace("\n", " ").split()
    for i, tok in enumerate(parts):
        if tok == "SENT" and i + 1 < len(parts):
            sent = int(parts[i + 1])
        elif tok == "SKIPPED" and i + 1 < len(parts):
            skipped = int(parts[i + 1])
        elif tok == "ELAPSED_MS" and i + 1 < len(parts):
            elapsed_ms = float(parts[i + 1])
    sender = {"sent": sent, "skipped": skipped, "elapsed_ms": elapsed_ms,
              "timed_out": timed_out}
    return rd(summary, True), rd(tx_stats), rd(rx_stats), sender


def main():
    _harden()
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=6000, help="datagrams per run")
    ap.add_argument("--size", type=int, default=1100)
    ap.add_argument("--pps", type=float, default=2000.0)
    ap.add_argument("--mtu", type=int, default=1500)
    ap.add_argument("--rtt", type=float, default=20.0)
    ap.add_argument("--rate-mbps", type=float, default=20.0)
    ap.add_argument("--budget-ms", type=float, default=20.0)
    ap.add_argument("--static-ratio", type=float, default=0.25)
    ap.add_argument("--timeout", type=float, default=180.0)
    a = ap.parse_args()

    if not os.path.exists(os.path.join(BIN, "qdata")):
        print("build first: bash experiments/quicbed/build.sh")
        return 2

    print("=" * 100)
    print("E13 - live data phase: real controller + real RS on real QUIC datagrams")
    print("      n=%d x %dB at %.0f pps, MTU=%d, RTT=%.0fms"
          % (a.n, a.size, a.pps, a.mtu, a.rtt))
    print("=" * 100)
    setup(a.mtu)

    half = a.rtt / 2.0
    delay = "delay %.1fms" % half
    conditions = [
        ("noloss", delay),
        ("uniform_p2", "loss 2%% %s" % delay),
        ("uniform_p5", "loss 5%% %s" % delay),
        ("burst_p5_L4", "%s %s" % (gemodel(0.05, 4.0), delay)),
        ("burst_p5_L8", "%s %s" % (gemodel(0.05, 8.0), delay)),
    ]
    policies = ["none", "static", "adaptive"]

    out = {"n": a.n, "size": a.size, "pps": a.pps, "rtt_ms": a.rtt,
           "rate_mbps": a.rate_mbps, "runs": {}}
    fp = hashlib.sha256(json.dumps(
        {"n": a.n, "size": a.size, "pps": a.pps, "rate": a.rate_mbps,
         "budget": a.budget_ms, "static": a.static_ratio, "rtt": a.rtt,
         "code": code_fingerprint(
             ["experiments/quicbed/shim_data.py",
              "experiments/quicbed/dataapp.go",
              "afec/rs.py", "afec/controller.py"], root=ROOT)},
        sort_keys=True).encode()).hexdigest()[:16]
    jr = Journal(os.path.join(HERE, "state", "e13_units.jsonl"), fingerprint=fp)
    if len(jr):
        print("재개: 이미 끝난 조합 %d개는 건너뛴다" % len(jr))

    print("")
    print("%-13s %-9s %8s %8s %9s %9s %9s %8s %8s" %
          ("condition", "policy", "deliv%", "skip%", "recovered", "goodput",
           "overhead", "mean r", "enc/blk"))
    print("-" * 100)
    for cname, spec in conditions:
        for pol in policies:
            ukey = "%s/%s" % (cname, pol)
            cached = jr.get(ukey)
            if cached is not None:
                out["runs"][ukey] = cached
                v = cached
                print("%-13s %-9s %7.2f%% %7.2f%% %9d %7.2fMb %8.1f%% %8.1f %8.3f  (재개: 기록됨)"
                      % (cname, pol, 100.0 * v["delivery_rate"],
                         100.0 * v["skip_fraction"], v["rx"].get("recovered", 0),
                         v["goodput_nominal_mbps"], 100.0 * v["overhead"],
                         v["tx"].get("mean_r", 0),
                         v["tx"].get("encode_ms", 0) / max(v["tx"].get("blocks", 1), 1)))
                continue
            s, tx, rx, sender = one_run(pol, spec, a.n, a.size, a.pps,
                                        a.rate_mbps, a.budget_ms,
                                        a.static_ratio, a.timeout, a.rtt)
            if not s:
                print("%-13s %-9s   no summary (timed_out=%s)"
                      % (cname, pol, sender.get("timed_out")))
                continue
            orig = tx.get("originals", 0) or 1
            rep = tx.get("repairs", 0)
            blocks = tx.get("blocks", 0) or 1
            sent = sender.get("sent") or a.n
            skipped = sender.get("skipped") or 0
            offered = sent + skipped
            deliv = s["received"] / sent if sent else 0.0
            skip_frac = skipped / offered if offered else 0.0
            nominal_s = a.n / a.pps
            goodput = s["received"] * a.size * 8 / nominal_s / 1e6
            row = {
                "condition": cname, "netem": spec, "policy": pol,
                "summary": s, "tx": tx, "rx": rx, "sender": sender,
                "overhead": rep / orig,
                "delivery_rate": deliv,
                "skip_fraction": skip_frac,
                "goodput_nominal_mbps": goodput,
                "valid": skip_frac < 0.01 and not sender.get("timed_out"),
            }
            out["runs"][ukey] = row
            if row["valid"]:
                jr.record(ukey, row)
            else:
                print("        (무효 -> 저널에 넣지 않음. 다음 실행에서 재시도)")
            flag = "" if skip_frac < 0.01 else "  <-- SENDER LIMITED, invalid"
            print("%-13s %-9s %7.2f%% %7.2f%% %9d %7.2fMb %8.1f%% %8.1f %8.3f%s" %
                  (cname, pol, 100.0 * deliv, 100.0 * skip_frac,
                   rx.get("recovered", 0), goodput,
                   100.0 * rep / orig, tx.get("mean_r", 0),
                   tx.get("encode_ms", 0) / blocks, flag))

    set_netem(None)
    path = os.path.join(RESULTS, "e13_data_live.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("")
    print("saved: %s" % path)

    print("")
    print("SELF-CHECK 1 - no-loss control must deliver ~100% with every policy")
    for pol in policies:
        r = out["runs"].get("noloss/%s" % pol)
        if not r:
            continue
        d = r["delivery_rate"]
        print("   %-9s delivery %.4f  %s"
              % (pol, d, "ok" if d > 0.995
                 else "*** FAIL - the harness is losing packets ***"))

    print("")
    print("SELF-CHECK 2 - the sender must not be the bottleneck")
    print("   (QUIC datagrams are congestion controlled; if the offered rate")
    print("    exceeds what the controller allows, 'delivery' measures quic-go")
    print("    back-pressure and redundancy makes FEC look worse than no FEC)")
    bad = [k for k, v in out["runs"].items() if not v["valid"]]
    for k, v in sorted(out["runs"].items()):
        if v["skip_fraction"] >= 0.01 or v["sender"].get("timed_out"):
            print("   %-24s skipped %.2f%%  timed_out=%s  *** invalid ***"
                  % (k, 100 * v["skip_fraction"], v["sender"].get("timed_out")))
    if not bad:
        print("   all runs sender-clean (skip < 1%)")
    out["invalid_runs"] = bad

    print("")
    print("SELF-CHECK 3 - FEC must not reduce delivery below 'none'")
    for cname, _ in conditions:
        base = out["runs"].get("%s/none" % cname)
        if not base:
            continue
        for pol in ("static", "adaptive"):
            r = out["runs"].get("%s/%s" % (cname, pol))
            if not r:
                continue
            ok = r["delivery_rate"] >= base["delivery_rate"] - 0.002
            print("   %-13s %-9s %.4f vs none %.4f  %s"
                  % (cname, pol, r["delivery_rate"], base["delivery_rate"],
                     "ok" if ok else "*** FEC HURT - check sender limiting ***"))
    print("")
    print("SELF-CHECK 4 - 복구한 심볼이 정말 응용에 닿는가 (런 내부 비교)")
    print("   심이 서버로 넘긴 수 대비 서버가 실제로 센 수의 비율을 본다.")
    print("   복구가 깨져 있으면(예: 심볼 길이를 잘못 복원해 QUIC AEAD 실패)")
    print("   이중화를 쓰는 정책만 이 비율이 떨어진다. 서로 다른 런의 전달률을")
    print("   비교하면 난수 추첨 차이에 묻히지만, 이 비율은 런 안에서 닫힌다.")
    for cname, _ in conditions:
        base = out["runs"].get("%s/none" % cname)
        if not base or not base.get("valid"):
            continue
        bd = base["rx"].get("delivered", 0) or 1
        bratio = base["summary"]["received"] / bd
        for pol in ("static", "adaptive"):
            r = out["runs"].get("%s/%s" % (cname, pol))
            if not r or not r.get("valid"):
                continue
            if r["rx"].get("recovered", 0) < 10:
                continue
            d = r["rx"].get("delivered", 0) or 1
            ratio = r["summary"]["received"] / d
            ok = ratio > bratio - 0.02
            print("   %-13s %-9s 서버수신/심전달 %.3f (무FEC %.3f)  복구 %d  %s"
                  % (cname, pol, ratio, bratio, r["rx"]["recovered"],
                     "ok" if ok else "*** 복구분이 버려지고 있다 ***"))
            r["recovery_reaches_app"] = ok
    mal = sum(v["rx"].get("recover_malformed", 0) for v in out["runs"].values())
    print("   복구했으나 형식이 깨진 심볼: %d개" % mal)
    print("")
    print("SELF-CHECK 5 - 적응형은 손실이 오르면 이중화를 올려야 한다")
    print("   (이게 평평하면 제어기가 반응을 못 하는 것이다. 실제로 수신 심이")
    print("    아직 도착도 안 한 심볼을 '손실'로 조기 보고해 추정 손실률이 47%로")
    print("    뛰고, argmin 이 '가망 없음' 능선을 넘어 r=0 으로 무너진 적이 있다)")
    pairs = []
    for cname, _ in conditions:
        r = out["runs"].get("%s/adaptive" % cname)
        if r and r.get("valid"):
            pairs.append((cname, r["summary"]["loss_rate"],
                          r["tx"].get("mean_r", 0)))
    for cname, loss, mr in pairs:
        print("   %-13s 실측손실 %5.2f%%  ->  평균 r = %.2f" % (cname, 100 * loss, mr))
    lossy = [(l, m) for c, l, m in pairs if l > 0.03]
    clean = [(l, m) for c, l, m in pairs if l < 0.005]
    if lossy and clean:
        ok = max(m for _, m in lossy) > max(m for _, m in clean) + 0.5
        print("   판정: %s" % ("ok" if ok else
                              "*** 적응형이 손실에 반응하지 않는다 ***"))
        out["adaptive_responds_to_loss"] = ok

    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
