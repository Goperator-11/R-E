import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
TRACES = os.path.join(HERE, "traces")
PROBE = os.path.join(HERE, "probe.py")
os.makedirs(RESULTS, exist_ok=True)
os.makedirs(TRACES, exist_ok=True)

TX_IP = "10.9.0.1"
RX_IP = "10.9.0.2"
PORT = 39001
WORK = "/tmp/pqafec_netem"


def _harden():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


def run(cmd, check=True, quiet=True):
    r = subprocess.run(cmd, shell=isinstance(cmd, str),
                       capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError("FAILED: %s\n%s\n%s" % (cmd, r.stdout, r.stderr))
    if not quiet:
        sys.stdout.write(r.stdout)
    return r


def setup_testbed():
    run("mount -t tmpfs none /run", check=False)
    os.makedirs("/run/netns", exist_ok=True)
    os.makedirs(WORK, exist_ok=True)
    run("ip netns del rx", check=False)
    run("ip netns add rx")
    run("ip link add veth-tx type veth peer name veth-rx")
    run("ip link set veth-rx netns rx")
    run("ip addr add %s/24 dev veth-tx" % TX_IP)
    run("ip link set veth-tx up")
    run("ip link set lo up")
    run("ip netns exec rx ip addr add %s/24 dev veth-rx" % RX_IP)
    run("ip netns exec rx ip link set veth-rx up")
    run("ip netns exec rx ip link set lo up")
    run("ip link set dev veth-tx txqueuelen 10000", check=False)


def set_netem(spec):
    run("tc qdisc del dev veth-tx root", check=False)
    if spec is None:
        return "none"
    cmd = "tc qdisc add dev veth-tx root netem limit 20000 %s" % spec
    run(cmd)
    r = run("tc qdisc show dev veth-tx")
    return r.stdout.strip()


def analyse_mask(path, n):
    with open(path, "rb") as f:
        bm = f.read()
    arrived = 0
    losses = 0
    loss_runs = []
    good_runs = []
    cur_loss = 0
    cur_good = 0
    for i in range(n):
        bit = (bm[i >> 3] >> (i & 7)) & 1
        if bit:
            arrived += 1
            if cur_loss:
                loss_runs.append(cur_loss)
                cur_loss = 0
            cur_good += 1
        else:
            losses += 1
            if cur_good:
                good_runs.append(cur_good)
                cur_good = 0
            cur_loss += 1
    if cur_loss:
        loss_runs.append(cur_loss)
    if cur_good:
        good_runs.append(cur_good)

    n_bursts = len(loss_runs)
    mean_burst = (losses / n_bursts) if n_bursts else 0.0
    mean_gap = (sum(good_runs) / len(good_runs)) if good_runs else 0.0
    loss_rate = losses / n if n else 0.0

    pair_ll = pair_gl = 0
    prev = None
    for i in range(n):
        bit = (bm[i >> 3] >> (i & 7)) & 1
        cur = 0 if bit else 1
        if prev is not None:
            if prev == 1 and cur == 1:
                pair_ll += 1
            if prev == 0 and cur == 1:
                pair_gl += 1
        prev = cur
    p_loss_given_loss = pair_ll / losses if losses else 0.0
    p_loss_given_ok = pair_gl / arrived if arrived else 0.0

    q_bg = 1.0 / mean_burst if mean_burst else 0.0
    q_gb = 1.0 / mean_gap if mean_gap else 0.0
    ge_steady = q_gb / (q_gb + q_bg) if (q_gb + q_bg) else 0.0

    return {
        "n": n, "arrived": arrived, "lost": losses,
        "loss_rate": loss_rate,
        "n_bursts": n_bursts,
        "mean_burst": mean_burst,
        "max_burst": max(loss_runs) if loss_runs else 0,
        "mean_gap": mean_gap,
        "p_loss_given_loss": p_loss_given_loss,
        "p_loss_given_ok": p_loss_given_ok,
        "ge_q_gb": q_gb, "ge_q_bg": q_bg, "ge_steady_loss": ge_steady,
        "burst_hist": _hist(loss_runs),
    }


def _hist(runs):
    h = {}
    for r in runs:
        k = str(r) if r <= 10 else ">10"
        h[k] = h.get(k, 0) + 1
    return h


def gemodel_for(p_target, burst_target):
    r = 1.0 / burst_target
    p = p_target * r / (1.0 - p_target)
    return p, r


def build_configs():
    cfgs = []
    cfgs.append(("control_noloss", None, {"model": "none"}))
    for pct in (1, 2, 5, 10):
        cfgs.append(("uniform_%d" % pct, "loss %d%%" % pct,
                     {"model": "bernoulli", "p_target": pct / 100.0,
                      "burst_target": 1.0}))
    for pct, corr in ((5, 0), (5, 10), (5, 25), (5, 50), (5, 75), (5, 90)):
        spec = "loss %d%%" % pct if corr == 0 else "loss %d%% %d%%" % (pct, corr)
        cfgs.append(("corr_%d_%d" % (pct, corr), spec,
                     {"model": "netem-correlated", "p_target": pct / 100.0,
                      "corr": corr}))
    for pct, L in ((1, 4), (2, 4), (5, 2), (5, 4), (5, 8), (10, 4)):
        p, r = gemodel_for(pct / 100.0, L)
        cfgs.append(("ge_p%d_L%d" % (pct, L),
                     "loss gemodel %.4f%% %.4f%%" % (p * 100.0, r * 100.0),
                     {"model": "gemodel", "p_target": pct / 100.0,
                      "burst_target": float(L),
                      "netem_p": p, "netem_r": r}))
    return cfgs


def one_run(name, spec, n, pps, size):
    qdisc = set_netem(spec)
    mask = os.path.join(TRACES, name + ".mask")
    ready = os.path.join(WORK, "ready")
    for f in (mask, ready):
        if os.path.exists(f):
            os.remove(f)

    rx = subprocess.Popen(
        ["ip", "netns", "exec", "rx", sys.executable, PROBE,
         "--role", "recv", "--bind", RX_IP, "--port", str(PORT),
         "--n", str(n), "--out", mask, "--ready", ready, "--idle", "4"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for _ in range(200):
        if os.path.exists(ready):
            break
        time.sleep(0.05)
    else:
        rx.kill()
        raise RuntimeError("receiver did not become ready")

    tx = subprocess.run(
        [sys.executable, PROBE, "--role", "send", "--host", RX_IP,
         "--port", str(PORT), "--n", str(n), "--pps", str(pps),
         "--size", str(size)],
        capture_output=True, text=True)
    rx_out, rx_err = rx.communicate(timeout=120)
    stats = analyse_mask(mask, n)
    stats["qdisc"] = qdisc
    stats["send_line"] = tx.stdout.strip()
    stats["recv_line"] = rx_out.strip()
    return stats


def main():
    _harden()
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100000)
    ap.add_argument("--pps", type=float, default=10000.0)
    ap.add_argument("--size", type=int, default=1200)
    ap.add_argument("--only", default=None, help="substring filter on config name")
    a = ap.parse_args()

    print("=" * 86)
    print("E6 - netem loss traces  (n=%d, %.0f pps, %dB)" % (a.n, a.pps, a.size))
    print("=" * 86)
    setup_testbed()
    print("testbed: %s <-> %s (veth, two netns, no root)" % (TX_IP, RX_IP))
    print("")

    cfgs = build_configs()
    if a.only:
        cfgs = [c for c in cfgs if a.only in c[0]]

    path = os.path.join(RESULTS, "e6_netem.json")
    out = {"n": a.n, "pps": a.pps, "size": a.size, "configs": {}}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                prev = json.load(f)
            if prev.get("n") == a.n and prev.get("size") == a.size:
                out["configs"] = prev.get("configs", {})
                print("merging into %d existing configs" % len(out["configs"]))
        except Exception:
            pass
    print("%-16s %9s %9s %8s %8s %8s %9s %9s" %
          ("config", "loss tgt", "loss meas", "L tgt", "L meas", "maxL",
           "P(L|L)", "P(L|ok)"))
    print("-" * 86)
    for name, spec, meta in cfgs:
        try:
            st = one_run(name, spec, a.n, a.pps, a.size)
        except Exception as e:
            print("%-16s ERROR %s" % (name, str(e)[:60]))
            continue
        st.update(meta)
        st["netem_spec"] = spec
        out["configs"][name] = st
        print("%-16s %9s %9.4f %8s %8.2f %8d %9.4f %9.4f" %
              (name,
               ("%.4f" % meta["p_target"]) if "p_target" in meta else "-",
               st["loss_rate"],
               ("%.1f" % meta["burst_target"]) if "burst_target" in meta else "-",
               st["mean_burst"], st["max_burst"],
               st["p_loss_given_loss"], st["p_loss_given_ok"]))

    set_netem(None)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("")
    print("saved: %s" % path)
    print("masks: %s" % TRACES)
    return 0


if __name__ == "__main__":
    sys.exit(main())
