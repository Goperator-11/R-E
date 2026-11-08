import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RESULTS = os.path.join(HERE, "results")
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
os.makedirs(RESULTS, exist_ok=True)

from _journal import Journal, code_fingerprint
from afec.estimator import CongestionDetector

TX, RX = "10.9.0.1", "10.9.0.2"
PORT = 39101
PROBE = os.path.join(HERE, "probe.py")
WORK = "/tmp/pqafec_e19"


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


def clear_qdisc():
    run("tc qdisc del dev veth-tx root", check=False)
    run("ip netns exec rx tc qdisc del dev veth-rx root", check=False)


def set_delay(one_way_ms, loss_spec=""):
    clear_qdisc()
    spec = "delay %.3fms %s" % (one_way_ms, loss_spec)
    run("tc qdisc add dev veth-tx root netem limit 50000 %s" % spec)
    run("ip netns exec rx tc qdisc add dev veth-rx root netem limit 50000 %s"
        % spec)


def set_shaped(rate_mbit, one_way_ms, burst_kb=32, limit_kb=256, loss_spec=""):
    clear_qdisc()
    for dev, pre in (("veth-tx", ""), ("veth-rx", "ip netns exec rx ")):
        run("%stc qdisc add dev %s root handle 1: tbf rate %.3fmbit "
            "burst %dkb limit %dkb" % (pre, dev, rate_mbit, burst_kb, limit_kb))
        run("%stc qdisc add dev %s parent 1: handle 10: netem limit 50000 "
            "delay %.3fms %s" % (pre, dev, one_way_ms, loss_spec))


def ping_rtt(n=30):
    r = run("ping -c %d -i 0.05 -W 2 %s" % (n, RX), check=False)
    out = r.stdout
    for line in out.splitlines():
        if "rtt min/avg/max" in line or "round-trip" in line:
            nums = line.split("=")[1].strip().split()[0].split("/")
            return {"min": float(nums[0]), "avg": float(nums[1]),
                    "max": float(nums[2]), "mdev": float(nums[3])}
    return {}


def probe(n, pps, size=1200, idle=4.0):
    mask = os.path.join(WORK, "m.bin")
    ready = os.path.join(WORK, "ready")
    for f in (mask, ready):
        if os.path.exists(f):
            os.remove(f)
    rx = subprocess.Popen(
        ["ip", "netns", "exec", "rx", sys.executable, PROBE, "--role", "recv",
         "--bind", RX, "--port", str(PORT), "--n", str(n), "--out", mask,
         "--ready", ready, "--idle", str(idle)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for _ in range(200):
        if os.path.exists(ready):
            break
        time.sleep(0.05)
    tx = subprocess.run(
        [sys.executable, PROBE, "--role", "send", "--host", RX, "--port",
         str(PORT), "--n", str(n), "--pps", str(pps), "--size", str(size)],
        capture_output=True, text=True)
    out, _ = rx.communicate(timeout=180)
    lost = n
    try:
        with open(mask, "rb") as f:
            bm = f.read()
        got = sum(1 for i in range(n) if (bm[i >> 3] >> (i & 7)) & 1)
        lost = n - got
    except OSError:
        got = 0
    return {"n": n, "got": got, "lost": lost, "loss_rate": lost / n,
            "send": tx.stdout.strip(), "recv": out.strip()}


def main():
    _harden()
    ap = argparse.ArgumentParser()
    ap.add_argument("--rtts", default="10,20,50,100")
    ap.add_argument("--rate-mbit", type=float, default=10.0)
    ap.add_argument("--loads", default="50,80,100,120")
    ap.add_argument("--probe-n", type=int, default=20000)
    ap.add_argument("--size", type=int, default=1200)
    a = ap.parse_args()

    print("=" * 92)
    print("E19 - RTT 스윕 + 네트워크 혼잡 재현 (계획서 「연구 내용 2」)")
    print("=" * 92)
    setup()

    fp = code_fingerprint(["experiments/e19_rtt_congestion.py",
                           "experiments/probe.py"], root=ROOT)
    fp += "|%s|%.1f|%s|%d" % (a.rtts, a.rate_mbit, a.loads, a.probe_n)
    jr = Journal(os.path.join(HERE, "state", "e19_units.jsonl"), fingerprint=fp)
    if len(jr):
        print("재개: 이미 끝난 단위 %d개" % len(jr))

    out = {"rate_mbit": a.rate_mbit, "probe_n": a.probe_n, "size": a.size,
           "rtt_sweep": {}, "congestion": {}, "detector": {}}

    print("")
    print("[A] RTT 스윕 — netem delay 가 설정대로 나오는가")
    print("%10s %12s %12s %12s %10s" %
          ("설정 RTT", "실측 min", "실측 avg", "실측 max", "오차"))
    print("-" * 62)
    for rtt in [float(x) for x in a.rtts.split(",")]:
        key = "rtt/%.0f" % rtt
        rec = jr.get(key)
        if rec is None:
            set_delay(rtt / 2.0)
            time.sleep(0.3)
            rec = ping_rtt(40)
            rec["target"] = rtt
            jr.record(key, rec)
        out["rtt_sweep"]["%.0f" % rtt] = rec
        err = 100 * (rec.get("avg", 0) - rtt) / rtt if rtt else 0
        print("%9.0fms %11.2fms %11.2fms %11.2fms %9.1f%%" %
              (rtt, rec.get("min", 0), rec.get("avg", 0), rec.get("max", 0), err))

    print("")
    print("[B] 혼잡 계단 — 대역 %.0f Mbit/s 에 부하를 올린다" % a.rate_mbit)
    print("   (netem 은 손실·지연만 준다. 큐가 차서 생기는 지연은 대역 제한이")
    print("    있어야 나오고, 그게 진짜 혼잡이다)")
    print("%8s %10s %12s %12s %12s %10s" %
          ("부하", "제안 pps", "기저 RTT", "부하중 RTT", "RTT 팽창", "손실률"))
    print("-" * 74)
    base_rtt_ms = 20.0
    cap_pps = a.rate_mbit * 1e6 / (a.size * 8)
    for load in [float(x) for x in a.loads.split(",")]:
        key = "cong/%.0f" % load
        rec = jr.get(key)
        if rec is None:
            set_shaped(a.rate_mbit, base_rtt_ms / 2.0)
            time.sleep(0.3)
            idle = ping_rtt(20)
            pps = cap_pps * load / 100.0
            n = max(int(pps * 6), 2000)
            sender = subprocess.Popen(
                [sys.executable, PROBE, "--role", "send", "--host", RX,
                 "--port", str(PORT), "--n", str(n), "--pps", str(pps),
                 "--size", str(a.size)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1.5)
            busy = ping_rtt(25)
            sender.wait(timeout=120)
            pr = probe(min(n, 8000), pps, a.size)
            rec = {"load_pct": load, "offered_pps": pps,
                   "idle_rtt": idle, "busy_rtt": busy,
                   "loss_rate": pr["loss_rate"]}
            jr.record(key, rec)
        out["congestion"]["%.0f" % load] = rec
        i, b = rec["idle_rtt"].get("avg", 0), rec["busy_rtt"].get("avg", 0)
        infl = (b - i) / i if i else 0
        print("%7.0f%% %10.0f %11.2fms %11.2fms %11.1f%% %9.4f" %
              (load, rec["offered_pps"], i, b, 100 * infl, rec["loss_rate"]))

    print("")
    print("[C] 혼잡 판별력 — g 가 '왜 잃었는가'를 실제로 구분하는가")
    print("   설계의 핵심 주장: 혼잡 손실에 이중화로 대응하면 상황이 악화되므로")
    print("   g 가 1 로 가서 이중화를 눌러야 한다. 링크 오류면 g=0 이어야 한다.")
    print("%-26s %12s %12s %8s" % ("시나리오", "기저 RTT", "관측 RTT", "g"))
    print("-" * 62)
    scenarios = []
    scenarios.append(("링크 오류 (손실 5%, 큐 여유)", False, "loss 5%", 40.0))
    scenarios.append(("혼잡 (대역 초과, 손실설정 없음)", True, "", 120.0))
    for label, shaped, loss, load in scenarios:
        key = "det/%s" % label
        rec = jr.get(key)
        if rec is None:
            if shaped:
                set_shaped(a.rate_mbit, base_rtt_ms / 2.0)
            else:
                set_delay(base_rtt_ms / 2.0, loss)
            time.sleep(0.3)
            idle = ping_rtt(20)
            pps = cap_pps * load / 100.0
            n = max(int(pps * 5), 2000)
            sender = subprocess.Popen(
                [sys.executable, PROBE, "--role", "send", "--host", RX,
                 "--port", str(PORT), "--n", str(n), "--pps", str(pps),
                 "--size", str(a.size)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1.2)
            busy = ping_rtt(25)
            sender.wait(timeout=120)
            rec = {"idle": idle, "busy": busy}
            jr.record(key, rec)
        det = CongestionDetector()
        for _ in range(30):
            det.observe_rtt(rec["idle"].get("min", base_rtt_ms))
        for _ in range(30):
            det.observe_rtt(rec["busy"].get("avg", base_rtt_ms))
        g = det.g
        out["detector"][label] = {"idle_rtt": rec["idle"], "busy_rtt": rec["busy"],
                                  "g": g, "inflation": det.inflation}
        print("%-26s %11.2fms %11.2fms %8.2f" %
              (label, rec["idle"].get("avg", 0), rec["busy"].get("avg", 0), g))

    print("")
    print("[D] 측정된 g 를 비용식에 넣으면 이중화가 실제로 눌리는가")
    print("   판별만 잘해도 소용없다. J = (1+β·g)·t_tx + P_fail·T_recover 에서")
    print("   g 가 1 이면 여분 바이트의 대가가 (1+β)배로 뛰어 r 이 내려가야 한다.")
    from afec.controller import FecConfig, choose_block_size, choose_redundancy
    cfg = FecConfig(rate_bps=a.rate_mbit * 1e6, delay_budget_ms=20.0)
    k = choose_block_size(cfg)
    print("%-26s %6s %8s %10s %10s" % ("시나리오", "g", "K", "r*", "오버헤드"))
    print("-" * 66)
    link_r = cong_r = None
    for label, v in out["detector"].items():
        g = v["g"]
        d = choose_redundancy(k, 0.05, 2.0, 2.0 * base_rtt_ms, g, cfg)
        v["r_under_g"] = d.r
        v["overhead_under_g"] = d.r / k if k else 0
        if "링크" in label:
            link_r = d.r
        else:
            cong_r = d.r
        print("%-26s %6.2f %8d %10d %9.1f%%"
              % (label, g, k, d.r, 100 * d.r / k))
    if link_r is not None and cong_r is not None:
        out["congestion_suppresses_redundancy"] = cong_r < link_r
        print("   -> 같은 손실률 5%%인데 혼잡이면 r 이 %d -> %d 로 눌린다  %s"
              % (link_r, cong_r,
                 "ok" if cong_r < link_r else "*** 안 눌린다 ***"))

    clear_qdisc()

    print("")
    print("자기검사")
    ok = True
    for rtt, rec in out["rtt_sweep"].items():
        e = abs(rec.get("avg", 0) - float(rtt)) / float(rtt)
        if e > 0.15:
            print("   *** RTT %s ms 설정 오차 %.0f%% - netem delay 가 안 맞는다"
                  % (rtt, 100 * e))
            ok = False
    if ok:
        print("   RTT 스윕: 전 구간 설정값 오차 15%% 이내  ok")
    gs = out["detector"]
    link = next((v["g"] for k, v in gs.items() if "링크" in k), None)
    cong = next((v["g"] for k, v in gs.items() if "혼잡" in k), None)
    if link is not None and cong is not None:
        good = cong > link + 0.3
        print("   판별력: 혼잡 g=%.2f vs 링크오류 g=%.2f  %s"
              % (cong, link, "ok" if good else "*** 구분 못 함 ***"))
        out["detector_discriminates"] = good
    if out.get("congestion_suppresses_redundancy") is not None:
        print("   억제 고리: 혼잡에서 이중화가 눌리는가  %s"
              % ("ok" if out["congestion_suppresses_redundancy"]
                 else "*** 실패 ***"))

    path = os.path.join(RESULTS, "e19_rtt_congestion.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("")
    print("saved: %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
