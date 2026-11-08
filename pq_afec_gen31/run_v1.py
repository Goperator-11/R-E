from __future__ import annotations

from afec import (AdaptiveFecController, FecConfig, GilbertElliott,
                  PathStatsCache, choose_block_size, choose_redundancy,
                  profile, pto_ms, shield)
from afec.sim import expected_handshake_ms, simulate_data, simulate_handshake

def _harden_console():
    import sys
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


_harden_console()

LINE = "-" * 78


def h(title):
    print("\n" + LINE)
    print(title)
    print(LINE)


def exp1_sizes():
    h("[1] ML-KEM key share -> QUIC Initial packet count  (FIPS 203 / RFC 9000)")
    print(f"{'kex':<18}{'c.share':>9}{'CH bytes':>10}{'c.pkts':>8}"
          f"{'s.share':>9}{'SF bytes':>10}{'s.pkts':>8}{'amp budget':>12}")
    for level in (None, 512, 768, 1024):
        pr = profile(level)
        print(f"{pr.kem:<18}{pr.client_share:>9}{pr.client_flight:>10}{pr.k_client:>8}"
              f"{pr.server_share:>9}{pr.server_flight:>10}{pr.k_server:>8}"
              f"{pr.amplification_budget:>12}")
    print("\n  -> x25519 alone fits in ONE Initial packet; every ML-KEM hybrid needs 2+.")
    print("     Splitting is what makes a single packet loss cost a full PTO.")


def exp2_shield():
    h("[2] Handshake shield: r* chosen by the cost function (T_recover = PTO)")
    print(f"    first PTO with no RTT sample = {pto_ms():.0f} ms  (RFC 9002 6.2.1)")
    cfg = FecConfig(rate_bps=10e6)
    pr = profile(768)
    print(f"\n{'p_prior':>9}{'burst':>7}{'K':>4}{'r*':>4}{'overhead':>10}"
          f"{'P_fail(r*)':>12}{'P_fail(0)':>12}")
    for p in (0.001, 0.005, 0.01, 0.02, 0.05, 0.10):
        for burst in (1.0, 3.0):
            d = shield(pr, p, burst, cfg)
            base = GilbertElliott.from_burst(p, burst).p_fail(d.k, 0)
            print(f"{p:>9.3f}{burst:>7.1f}{d.k:>4}{d.r:>4}{d.overhead:>9.0%}"
                  f"{d.p_fail:>12.2e}{base:>12.2e}")
    print("\n  -> r*=1 already appears at p=0.1%: one 1.2KB packet vs a ~1 s stall.")


def exp3_handshake_sim():
    h("[3] Handshake completion time  (RTT = 30 ms, burst = 3) -- analytic")
    rtt, burst = 30.0, 3.0
    base = profile(None)
    mlkem = profile(768)
    print(f"{'loss':>7} | {'x25519':>9} | {'MLKEM r=0':>10} | {'MLKEM r=1':>10}"
          f" | {'PQC cost':>9} | {'FEC gain':>9} | {'stall r0->r1':>14}")
    for p in (0.005, 0.01, 0.02, 0.05, 0.10):
        a = expected_handshake_ms(base.k_client, base.k_server, 0, 0, p, burst, rtt)
        b = expected_handshake_ms(mlkem.k_client, mlkem.k_server, 0, 0, p, burst, rtt)
        c = expected_handshake_ms(mlkem.k_client, mlkem.k_server, 1, 1, p, burst, rtt)
        pqc_cost = (b.mean_ms - a.mean_ms) / a.mean_ms * 100.0
        gain = (b.mean_ms - c.mean_ms) / b.mean_ms * 100.0
        print(f"{p:>7.1%} | {a.mean_ms:>7.0f}ms | {b.mean_ms:>8.0f}ms"
              f" | {c.mean_ms:>8.0f}ms | {pqc_cost:>8.1f}% | {gain:>8.1f}%"
              f" | {b.stall_prob:>5.1%} -> {c.stall_prob:>4.1%}")
    print("\n  -> 'PQC cost' = slowdown caused by switching to ML-KEM.")
    print("     'FEC gain'  = how much of it one repair packet per flight buys back.")

    print("\n    cross-check against Monte Carlo (p95 is robust, mean is not):")
    print(f"    {'loss':>6}{'analytic mean':>15}{'MC mean':>10}{'MC p95':>10}")
    for p in (0.01, 0.05):
        an = expected_handshake_ms(mlkem.k_client, mlkem.k_server, 0, 0, p, burst, rtt)
        mc = simulate_handshake(mlkem.k_client, mlkem.k_server, 0, 0, p, burst, rtt,
                                trials=60000)
        print(f"    {p:>6.1%}{an.mean_ms:>14.0f}m{mc.mean_ms:>9.0f}m{mc.p95_ms:>9.0f}m")


def exp4_data_phase():
    h("[4] Data phase: same payload, which policy finishes first?")
    cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0)
    k = choose_block_size(cfg)
    rtt, burst = 40.0, 4.0
    print(f"    K = {k} symbols/block, RTT = {rtt:.0f} ms, burst = {burst:.0f}, "
          f"link = {cfg.rate_bps/1e6:.0f} Mbps")
    probs = (0.0, 0.005, 0.02, 0.05, 0.10)
    results: dict = {}
    for p in probs:
        print(f"\n  loss = {p:.1%}")
        print(f"    {'policy':<10}{'total ms':>10}{'goodput':>11}"
              f"{'overhead':>10}{'blk fail':>10}{'mean r':>8}")
        for pol in ("none", "static", "adaptive", "oracle"):
            r = simulate_data(pol, p, burst, rtt, cfg)
            results.setdefault(pol, {})[p] = r
            print(f"    {r.label:<10}{r.total_ms:>10.0f}{r.goodput_mbps:>10.2f}M"
                  f"{r.overhead:>9.1%}{r.block_fail_rate:>10.2%}{r.mean_r:>8.2f}")

    print(f"\n  regret vs oracle (total time, %):")
    print(f"    {'policy':<10}" + "".join(f"{p:>9.1%}" for p in probs)
          + f"{'WORST':>9}")
    for pol in ("none", "static", "adaptive"):
        regs = [(results[pol][p].total_ms / results['oracle'][p].total_ms - 1) * 100
                for p in probs]
        print(f"    {pol:<10}" + "".join(f"{v:>8.1f}%" for v in regs)
              + f"{max(regs):>8.1f}%")
    print("\n  -> the point is the WORST column: 'static' is only good near the loss")
    print("     rate it was tuned for. 'adaptive' stays close to oracle everywhere.")

    print("\n  same thing on SHORT connections (30 blocks, averaged over 8 seeds):")
    print(f"    {'policy':<10}" + "".join(f"{p:>9.1%}" for p in probs)
          + f"{'WORST':>9}")
    seeds = range(11, 19)
    short = {}
    for pol in ("none", "static", "adaptive", "warm", "oracle"):
        short[pol] = {}
        for p in probs:
            runs = [simulate_data(pol, p, burst, rtt, cfg, n_blocks=30, seed=s).total_ms
                    for s in seeds]
            short[pol][p] = sum(runs) / len(runs)
    for pol in ("none", "static", "adaptive", "warm"):
        regs = [(short[pol][p] / short["oracle"][p] - 1) * 100 for p in probs]
        print(f"    {pol:<10}" + "".join(f"{v:>8.1f}%" for v in regs)
              + f"{max(regs):>8.1f}%")
    print("\n  -> with 30 blocks and 1-RTT feedback lag the controller barely has")
    print("     time to learn, so plain 'adaptive' loses its edge over 'static'.")
    print("     'warm' = same controller started from a cached per-destination")
    print("     prior. That gap is the value of carrying state across connections.")


def exp5_burst():
    h("[5] Why burstiness matters: same loss rate, different burst length")
    cfg = FecConfig(rate_bps=50e6)
    k = choose_block_size(cfg)
    p, t_rec = 0.02, 80.0
    print(f"    K = {k}, p = {p:.1%}, T_recover = {t_rec:.0f} ms\n")
    print(f"{'burst L':>9}{'r*':>5}{'overhead':>10}{'P_fail(r*)':>13}"
          f"{'P_fail with r* from L=1':>26}")
    r_iid = choose_redundancy(k, p, 1.0, t_rec, 0.0, cfg).r
    for burst in (1.0, 2.0, 4.0, 8.0, 16.0):
        d = choose_redundancy(k, p, burst, t_rec, 0.0, cfg)
        wrong = GilbertElliott.from_burst(p, burst).p_fail(k, r_iid)
        print(f"{burst:>9.0f}{d.r:>5}{d.overhead:>9.0%}{d.p_fail:>13.2e}"
              f"{wrong:>26.2e}")
    print(f"\n  -> assuming independent losses fixes r at {r_iid}; the last column shows")
    print("     the real failure probability that choice leaves you with.")

    print("\n    interleaving (D) breaks the burst apart instead of paying for it:")
    print(f"    {'burst L':>9}{'D':>4}{'r*':>5}{'overhead':>10}{'P_fail':>12}")
    for burst in (8.0, 16.0):
        for d_int in (1, 4, 8):
            c2 = FecConfig(rate_bps=cfg.rate_bps, interleave=d_int)
            d = choose_redundancy(k, p, burst, t_rec, 0.0, c2)
            print(f"    {burst:>9.0f}{d_int:>4}{d.r:>5}{d.overhead:>9.0%}{d.p_fail:>12.2e}")
    print("\n    -> D>1 costs latency (you must span D blocks), not bandwidth.")
    print("       Trading latency for redundancy is the cheaper deal on bursty links.")


def exp6_congestion_guard():
    h("[6] Congestion guard: identical loss, different cause")
    cfg = FecConfig(rate_bps=50e6, beta=4.0)
    k = choose_block_size(cfg)
    p, burst, t_rec = 0.05, 3.0, 80.0
    print(f"    K = {k}, p = {p:.1%}, burst = {burst:.0f}\n")
    print(f"{'RTT inflation':>15}{'g':>7}{'r*':>5}{'overhead':>10}{'P_fail':>12}")
    for g in (0.0, 0.25, 0.5, 0.75, 1.0):
        d = choose_redundancy(k, p, burst, t_rec, g, cfg)
        label = "link error" if g == 0 else ("congestion" if g == 1 else "")
        print(f"{g*100:>13.0f}% {g:>6.2f}{d.r:>5}{d.overhead:>9.0%}"
              f"{d.p_fail:>12.2e}   {label}")
    print("\n  -> same 5% loss, but redundancy is pulled back as the evidence")
    print("     points to a full queue rather than a lossy link.")


def exp7_tracking():
    h("[7] Adaptation trace: loss jumps 0.5% -> 8% at block 100, back at 250")
    cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0)
    ctrl = AdaptiveFecController(cfg)
    ctrl.cong.observe_rtt(40.0)

    import random
    from afec.sim import ChannelSampler
    rng = random.Random(3)

    print(f"{'block':>7}{'true p':>9}{'p_hat':>9}{'burst_hat':>11}{'r':>4}{'overhead':>10}")
    sampler = None
    prev = None
    for i in range(400):
        true_p = 0.005 if (i < 100 or i >= 250) else 0.08
        if true_p != prev:
            sampler = ChannelSampler(GilbertElliott.from_burst(true_p, 4.0), rng)
            prev = true_p
        d = ctrl.next_block()
        mask = sampler.send(d.k + d.r)
        ctrl.on_feedback(mask, rtt_ms=40.0)
        if i % 25 == 0 or i in (100, 101, 105, 110, 250, 255, 270):
            print(f"{i:>7}{true_p:>9.3f}{ctrl.loss.p:>9.3f}"
                  f"{ctrl.loss.burst:>11.2f}{d.r:>4}{d.overhead:>10.0%}")
    print("\n  -> reacts within a few blocks of the jump (feedback is 1 RTT stale),")
    print("     then decays geometrically once the surprise test stops firing.")


def exp8_cache():
    h("[8] Per-destination stats cache: repeated short connections (30 blocks)")
    cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0)
    p, burst, rtt = 0.05, 4.0, 40.0
    cache = PathStatsCache()
    dst = "203.0.113.10"

    print(f"    channel: loss {p:.0%}, burst {burst:.0f}, RTT {rtt:.0f} ms")
    print(f"    {'conn':<24}{'prior src':>10}{'prior p':>9}{'w':>7}"
          f"{'regret':>9}{'overhead':>10}")

    def one(label, net, seed, t):
        pr = cache.lookup(net, dst, now=t)
        r = simulate_data("cached", p, burst, rtt, cfg, n_blocks=30,
                          seed=seed, prior=(pr.p, pr.burst, pr.weight))
        oracle = simulate_data("oracle", p, burst, rtt, cfg, n_blocks=30,
                               seed=seed)
        cache.store(net, dst, *r.snapshot, now=t + 30.0)
        print(f"    {label:<24}{pr.source:>10}{pr.p:>9.3f}{pr.weight:>7.0f}"
              f"{r.total_ms / oracle.total_ms - 1:>9.1%}{r.overhead:>10.1%}")

    one("1st visit (cold)", "wifi:home", 41, 0.0)
    one("2nd visit", "wifi:home", 42, 60.0)
    one("3rd visit", "wifi:home", 43, 120.0)
    one("move to cellular", "cell:450-05", 44, 180.0)
    one("back on home wifi", "wifi:home", 45, 240.0)

    print("\n  -> the mobility line starts cold BY DESIGN: the access network is")
    print("     half of the cache key, so moving networks never reads stale stats.")
    print("     returning to wifi picks the old entry right back up.")
    print("     (single-seed demo - negative regret is per-seed noise;")
    print("      the statistics are in tune_cache.py, 32 seeds)")


if __name__ == "__main__":
    exp1_sizes()
    exp2_shield()
    exp3_handshake_sim()
    exp4_data_phase()
    exp5_burst()
    exp6_congestion_guard()
    exp7_tracking()
    exp8_cache()
    print()
