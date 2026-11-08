from __future__ import annotations

import math
import random
import time
import unittest

from afec import (AdaptiveFecController, FecConfig, GilbertElliott,
                  PathStatsCache, choose_block_size, choose_redundancy,
                  profile, shield)
from afec.estimator import LossEstimator
from afec.handshake import CH_BASE_BROWSER_QUIC, CH_BASE_MINIMAL_QUIC
from afec.rs import RSErasureCode, gf_inv, gf_mul
from afec.sim import (ChannelSampler, expected_handshake_ms, runs_of_losses,
                      simulate_data, simulate_handshake)

MEASURED: dict[str, str] = {}

def _harden_console():
    import sys
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


_harden_console()


class TestGaloisField(unittest.TestCase):

    def test_field_axioms(self):
        self.assertEqual(gf_mul(0, 123), 0)
        self.assertEqual(gf_mul(1, 123), 123)
        for a in range(1, 256):
            self.assertEqual(gf_mul(a, gf_inv(a)), 1, f"a={a}의 역원이 틀림")

    def test_distributive(self):
        rng = random.Random(1)
        for _ in range(500):
            a, b, c = (rng.randrange(256) for _ in range(3))
            self.assertEqual(gf_mul(a, b ^ c), gf_mul(a, b) ^ gf_mul(a, c))


class TestReedSolomonIsMDS(unittest.TestCase):
    def _symbols(self, rng, k, size):
        return [bytes(rng.randrange(256) for _ in range(size)) for _ in range(k)]

    def test_recovers_any_r_erasures(self):
        rng = random.Random(7)
        for k, r in ((4, 2), (8, 4), (16, 8), (32, 8), (10, 1)):
            code = RSErasureCode(k, r)
            source = self._symbols(rng, k, 24)
            parity = code.encode(source)
            allsym = source + parity

            for _ in range(30):
                lost = set(rng.sample(range(k + r), r))
                received = {i: allsym[i] for i in range(k + r) if i not in lost}
                recovered = code.decode(received)
                self.assertEqual(recovered, source,
                                 f"K={k}, r={r}, 소실={sorted(lost)} 복구 실패")

    def test_fails_beyond_r_erasures(self):
        rng = random.Random(11)
        for k, r in ((8, 4), (16, 8)):
            code = RSErasureCode(k, r)
            source = self._symbols(rng, k, 24)
            allsym = source + code.encode(source)
            for _ in range(20):
                lost = set(rng.sample(range(k + r), r + 1))
                received = {i: allsym[i] for i in range(k + r) if i not in lost}
                with self.assertRaises(ValueError):
                    code.decode(received)

    def test_worst_case_all_source_lost(self):
        rng = random.Random(13)
        k = 8
        code = RSErasureCode(k, k)
        source = self._symbols(rng, k, 32)
        parity = code.encode(source)
        received = {k + i: parity[i] for i in range(k)}
        self.assertEqual(code.decode(received), source)


class TestChannelModel(unittest.TestCase):

    def test_pmf_is_a_distribution(self):
        for p, L, n in ((0.02, 1.0, 20), (0.05, 4.0, 32), (0.2, 8.0, 16)):
            pmf = GilbertElliott.from_burst(p, L).erasure_pmf(n)
            self.assertAlmostEqual(sum(pmf), 1.0, places=9)
            self.assertTrue(all(v >= -1e-15 for v in pmf))

    def test_iid_case_matches_exact_binomial(self):
        for p, n in ((0.01, 24), (0.1, 16), (0.3, 12)):
            pmf = GilbertElliott.bernoulli(p).erasure_pmf(n)
            for i in range(n + 1):
                exact = math.comb(n, i) * p ** i * (1 - p) ** (n - i)
                self.assertAlmostEqual(pmf[i], exact, places=10,
                                       msg=f"p={p}, n={n}, i={i}")

    def test_dp_matches_monte_carlo(self):
        rng = random.Random(21)
        worst = 0.0
        for p, L, k, r in ((0.02, 1.0, 20, 2), (0.05, 4.0, 24, 6),
                           (0.10, 8.0, 16, 8), (0.01, 3.0, 32, 1)):
            ch = GilbertElliott.from_burst(p, L)
            predicted = ch.p_fail(k, r)
            sampler = ChannelSampler(ch, rng)
            trials, fails = 40000, 0
            for _ in range(trials):
                sampler.reset_state()
                if sum(sampler.send(k + r)) > r:
                    fails += 1
            empirical = fails / trials
            se = math.sqrt(max(predicted * (1 - predicted), 1e-12) / trials)
            gap = abs(empirical - predicted)
            worst = max(worst, gap / max(se, 1e-12))
            self.assertLess(gap, 5 * se + 1e-4,
                            f"p={p} L={L} K={k} r={r}: DP={predicted:.5f} "
                            f"MC={empirical:.5f}")
        MEASURED["DP vs MC 최대 편차"] = f"{worst:.2f} sigma"

    def test_channel_produces_requested_statistics(self):
        rng = random.Random(31)
        for p, L in ((0.02, 4.0), (0.10, 8.0)):
            ch = GilbertElliott.from_burst(p, L)
            sampler = ChannelSampler(ch, rng)
            mask = sampler.send(400000)
            runs = runs_of_losses(mask)
            got_p = sum(mask) / len(mask)
            got_L = sum(runs) / len(runs)
            self.assertAlmostEqual(got_p, p, delta=0.15 * p)
            self.assertAlmostEqual(got_L, L, delta=0.15 * L)

    def test_p_fail_decreases_with_redundancy(self):
        ch = GilbertElliott.from_burst(0.05, 4.0)
        curve = ch.fail_curve(32, 16)
        for a, b in zip(curve, curve[1:]):
            self.assertLessEqual(b, a + 1e-15)

    def test_interleaving_helps_on_bursty_channel(self):
        ch = GilbertElliott.from_burst(0.02, 8.0)
        plain = ch.p_fail(32, 8, interleave=1)
        spread = ch.p_fail(32, 8, interleave=8)
        self.assertLess(spread, plain)

    def test_fail_curve_matches_pointwise_p_fail(self):
        ch = GilbertElliott.from_burst(0.03, 3.0)
        curve = ch.fail_curve(24, 10, interleave=2)
        for r, v in enumerate(curve):
            self.assertAlmostEqual(v, ch.p_fail(24, r, interleave=2), places=12)


class TestController(unittest.TestCase):

    def test_r_star_really_minimizes_cost(self):
        cfg = FecConfig(rate_bps=50e6)
        for p, L, t_rec, g in ((0.01, 1.0, 80.0, 0.0), (0.05, 4.0, 999.0, 0.0),
                               (0.02, 2.0, 40.0, 0.5), (0.10, 6.0, 80.0, 1.0)):
            d = choose_redundancy(32, p, L, t_rec, g, cfg)
            byte_ms = cfg.symbol_bytes * 8.0 / cfg.rate_bps * 1000.0
            weight = 1.0 + cfg.beta * g
            ch = GilbertElliott.cached(p, L)
            best_r, best_j = None, float("inf")
            for r in range(0, int(math.ceil(32 * cfg.rho_max)) + 1):
                j = weight * r * byte_ms + ch.p_fail(32, r) * t_rec
                if j < best_j - 1e-12:
                    best_r, best_j = r, j
            self.assertEqual(d.r, best_r, f"p={p} L={L} T={t_rec} g={g}")
            self.assertAlmostEqual(d.cost, best_j, places=9)

    def test_more_loss_means_more_redundancy(self):
        cfg = FecConfig(rate_bps=50e6)
        rs = [choose_redundancy(32, p, 1.0, 80.0, 0.0, cfg).r
              for p in (0.001, 0.005, 0.01, 0.02, 0.05)]
        self.assertEqual(rs, sorted(rs), f"손실률에 대해 단조가 아님: {rs}")

    def test_costlier_recovery_means_more_redundancy(self):
        cfg = FecConfig(rate_bps=50e6)
        rs = [choose_redundancy(32, 0.02, 2.0, t, 0.0, cfg).r
              for t in (10.0, 40.0, 100.0, 500.0, 999.0)]
        self.assertEqual(rs, sorted(rs), f"T_recover에 대해 단조가 아님: {rs}")

    def test_congestion_suppresses_redundancy(self):
        cfg = FecConfig(rate_bps=50e6)
        rs = [choose_redundancy(32, 0.05, 3.0, 80.0, g, cfg).r
              for g in (0.0, 0.25, 0.5, 0.75, 1.0)]
        self.assertEqual(rs, sorted(rs, reverse=True),
                         f"혼잡 확신도에 대해 역단조가 아님: {rs}")
        self.assertLess(rs[-1], rs[0])

    def test_respects_overhead_cap(self):
        cfg = FecConfig(rate_bps=50e6, rho_max=0.25)
        d = choose_redundancy(32, 0.30, 8.0, 999.0, 0.0, cfg)
        self.assertLessEqual(d.overhead, 0.25 + 1e-9)

    def test_block_size_respects_delay_budget(self):
        cfg = FecConfig(rate_bps=10e6, delay_budget_ms=10.0, k_max=1000)
        k = choose_block_size(cfg)
        fill_ms = k * cfg.symbol_bytes * 8.0 / cfg.rate_bps * 1000.0
        self.assertLessEqual(fill_ms, cfg.delay_budget_ms + 1e-6)

    def test_hysteresis_never_exceeds_cap(self):
        cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0, rho_max=0.5)
        ctrl = AdaptiveFecController(cfg)
        ctrl.cong.observe_rtt(40.0)
        rng = random.Random(3)
        sampler = ChannelSampler(GilbertElliott.from_burst(0.15, 4.0), rng)
        for _ in range(40):
            d = ctrl.next_block()
            ctrl.on_feedback(sampler.send(d.k + d.r), rtt_ms=40.0)
        self.assertGreater(ctrl.last_decision.r, 3, "먼저 r이 커져 있어야 의미 있는 검사")

        for rate in (50e6, 5e6, 1e6, 3e5):
            d = ctrl.next_block(rate_bps=rate)
            self.assertLessEqual(d.r, math.ceil(d.k * cfg.rho_max),
                                 f"rate={rate:.0e}: K={d.k}인데 r={d.r} - 상한 초과")
            self.assertLessEqual(d.k + d.r, 255)

    def test_decision_cost_matches_reported_r(self):
        cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0)
        ctrl = AdaptiveFecController(cfg)
        ctrl.cong.observe_rtt(40.0)
        rng = random.Random(5)
        sampler = ChannelSampler(GilbertElliott.from_burst(0.12, 5.0), rng)
        for _ in range(60):
            d = ctrl.next_block()
            ch = GilbertElliott.cached(d.p_used, d.burst_used)
            self.assertAlmostEqual(d.p_fail, ch.p_fail(d.k, d.r, cfg.interleave),
                                   places=12)
            byte_ms = cfg.symbol_bytes * 8.0 / cfg.rate_bps * 1000.0
            expect = ((1.0 + cfg.beta * d.g) * d.r * byte_ms
                      + d.p_fail * d.t_recover_ms)
            self.assertAlmostEqual(d.cost, expect, places=9)
            ctrl.on_feedback(sampler.send(d.k + d.r), rtt_ms=40.0)

    def test_r_floor_cannot_break_gf_limit(self):
        cfg = FecConfig(rate_bps=1e9, rho_max=1.0)
        d = choose_redundancy(250, 0.05, 2.0, 999.0, 0.0, cfg, r_floor=50)
        self.assertLessEqual(d.k + d.r, 255)

    def test_gf256_limit_never_exceeded(self):
        cfg = FecConfig(rate_bps=1e9, delay_budget_ms=1000.0, k_max=250,
                        rho_max=1.0)
        d = choose_redundancy(250, 0.30, 8.0, 999.0, 0.0, cfg)
        self.assertLessEqual(d.k + d.r, 255)


class TestEstimator(unittest.TestCase):

    def _feed(self, est, p, L, n_blocks, block=64, seed=5):
        rng = random.Random(seed)
        sampler = ChannelSampler(GilbertElliott.from_burst(p, L), rng)
        trace = []
        for _ in range(n_blocks):
            mask = sampler.send(block)
            est.observe_mask(mask)
            trace.append((est.p, est.burst, est.jumped))
        return trace

    def test_converges_to_true_loss_rate(self):
        for p, L in ((0.02, 1.0), (0.05, 4.0)):
            est = LossEstimator(p_init=0.01)
            trace = self._feed(est, p, L, 600)
            tail = [t[0] for t in trace[-300:]]
            mean_p = sum(tail) / len(tail)
            bias = (mean_p - p) / p
            MEASURED[f"손실률 추정 편향 (p={p:.0%}, L={L:.0f})"] = f"{bias:+.1%}"
            self.assertLess(abs(bias), 0.20,
                            f"p={p} L={L}: 추정 {mean_p:.4f} vs 참값 {p}")

    def test_converges_to_true_burst_length(self):
        est = LossEstimator(p_init=0.01)
        trace = self._feed(est, 0.05, 4.0, 800)
        tail = [t[1] for t in trace[-400:]]
        mean_L = sum(tail) / len(tail)
        MEASURED["버스트 추정 (참값 4.0)"] = f"{mean_L:.2f}"
        self.assertAlmostEqual(mean_L, 4.0, delta=0.8)

    def test_surprise_detector_ignores_normal_bursts(self):
        est = LossEstimator(p_init=0.005)
        trace = self._feed(est, 0.005, 4.0, 400)
        rate = sum(1 for t in trace[100:] if t[2]) / len(trace[100:])
        MEASURED["정상 구간 급변 오탐률"] = f"{rate:.1%}"
        self.assertLess(rate, 0.03, f"오탐률 {rate:.1%} - 너무 자주 급변으로 판정")

    def test_surprise_detector_catches_real_shift(self):
        est = LossEstimator(p_init=0.005)
        self._feed(est, 0.005, 4.0, 200)
        trace = self._feed(est, 0.10, 4.0, 20, seed=99)
        self.assertTrue(any(t[2] for t in trace[:6]),
                        "손실률이 20배로 뛰었는데 급변을 못 잡았다")

    def test_confidence_bound_is_conservative_when_cold(self):
        est = LossEstimator(p_init=0.01)
        self.assertGreater(est.p_safe, est.p)

    def test_uncertainty_shrinks_as_evidence_accumulates(self):
        est = LossEstimator(p_init=0.02)
        se_cold = est.se
        n_cold = est.n_eff

        rng = random.Random(17)
        sampler = ChannelSampler(GilbertElliott.from_burst(0.02, 1.0), rng)
        for _ in range(60):
            est.observe_mask(sampler.send(64))

        self.assertGreater(est.n_eff, n_cold * 2,
                           "관측이 쌓였는데 유효 표본 수가 안 늘었다")
        self.assertLess(est.se, se_cold * 0.7,
                        "관측이 쌓였는데 불확실성이 안 줄었다")
        MEASURED["se 감소 (콜드 -> 60블록)"] = f"{se_cold:.4f} -> {est.se:.4f}"

    def test_standard_error_accounts_for_burstiness(self):
        flat, bursty = LossEstimator(), LossEstimator()
        for est, L in ((flat, 1.0), (bursty, 4.0)):
            est._lost, est._sent, est.burst = 3.0, 64.0, L

        self.assertGreater(bursty.se, flat.se)
        p = flat.p
        expect = math.sqrt(2.0 * 4.0 * (1.0 - p) - 1.0)
        self.assertAlmostEqual(bursty.se / flat.se, expect, places=6)
        MEASURED["버스트 보정 se 배율 (L=4)"] = f"x{bursty.se / flat.se:.2f}"

    def test_rtt_min_forgets_old_path(self):
        from afec.estimator import CongestionDetector
        cong = CongestionDetector(rtt_min_window=50)

        for _ in range(100):
            cong.observe_rtt(20.0)
        self.assertAlmostEqual(cong.rtt_min, 20.0, places=6)
        self.assertEqual(cong.g, 0.0)

        for _ in range(200):
            cong.observe_rtt(60.0)
        self.assertAlmostEqual(cong.rtt_min, 60.0, places=6,
                               msg="옛 경로의 최솟값을 아직 물고 있다")
        self.assertEqual(cong.g, 0.0, "경로 변경을 혼잡으로 오판하고 있다")

    def test_congestion_still_detected_after_window_fix(self):
        from afec.estimator import CongestionDetector
        cong = CongestionDetector(rtt_min_window=200)
        for _ in range(50):
            cong.observe_rtt(20.0)
        for _ in range(50):
            cong.observe_rtt(40.0)
        self.assertGreater(cong.g, 0.5)

    def test_burst_runs_stitched_across_blocks(self):
        est = LossEstimator()
        est.burst = 1.0
        est.observe_mask([False] * 5 + [True] * 3)
        est.observe_mask([True] * 3 + [False] * 5)
        self.assertGreater(est.burst, 1.5,
                           "경계를 걸친 6연속 손실을 짧게 세고 있다")


class TestPathStatsCache(unittest.TestCase):
    def test_same_slash24_shares_entry(self):
        c = PathStatsCache()
        c.store("wifi:AA", "203.0.113.7", 0.05, 4.0, 800.0, now=0.0)
        hit = c.lookup("wifi:AA", "203.0.113.200", now=1.0)
        self.assertEqual(hit.source, "exact")
        self.assertAlmostEqual(hit.p, 0.05, places=9)
        miss = c.lookup("wifi:AA", "203.0.114.7", now=1.0)
        self.assertEqual(miss.source, "network")

    def test_network_aggregate_fallback(self):
        c = PathStatsCache()
        c.store("wifi:AA", "203.0.113.7", 0.08, 3.0, 600.0, now=0.0)
        hit = c.lookup("wifi:AA", "198.51.100.9", now=1.0)
        self.assertEqual(hit.source, "network")
        self.assertAlmostEqual(hit.p, 0.08, places=9)

    def test_mobility_reads_nothing_from_old_network(self):
        c = PathStatsCache()
        c.store("wifi:AA", "203.0.113.7", 0.05, 4.0, 800.0, now=0.0)
        moved = c.lookup("cell:450-08", "203.0.113.7", now=1.0)
        self.assertEqual(moved.source, "default")
        back = c.lookup("wifi:AA", "203.0.113.7", now=2.0)
        self.assertEqual(back.source, "exact")

    def test_age_decays_then_expires(self):
        c = PathStatsCache(half_life_s=600.0, w_min=25.0)
        c.store("wifi:AA", "203.0.113.7", 0.05, 4.0, 80.0, now=0.0)
        fresh = c.lookup("wifi:AA", "203.0.113.7", now=0.0)
        aged = c.lookup("wifi:AA", "203.0.113.7", now=600.0)
        self.assertAlmostEqual(aged.weight, fresh.weight / 2.0, delta=1.0)
        self.assertAlmostEqual(aged.p, fresh.p, places=9)
        gone = c.lookup("wifi:AA", "203.0.113.7", now=1200.0)
        self.assertEqual(gone.source, "default")

    def test_lookup_weight_capped_at_default_prior(self):
        c = PathStatsCache()
        c.store("wifi:AA", "203.0.113.7", 0.05, 4.0, 1536.0, now=0.0)
        pr = c.lookup("wifi:AA", "203.0.113.7", now=0.0)
        self.assertLessEqual(pr.weight, 100.0 + 1e-9)
        alive = c.lookup("wifi:AA", "203.0.113.7", now=600.0 * 4)
        self.assertEqual(alive.source, "exact")

    def test_merge_is_weighted_mean_and_capped(self):
        c = PathStatsCache(w_cap=1536.0)
        c.store("wifi:AA", "203.0.113.7", 0.02, 2.0, 300.0, now=0.0)
        c.store("wifi:AA", "203.0.113.7", 0.08, 4.0, 900.0, now=0.0)
        hit = c.lookup("wifi:AA", "203.0.113.7", now=0.0)
        self.assertAlmostEqual(hit.p, (0.02 * 300 + 0.08 * 900) / 1200, places=9)
        for _ in range(10):
            c.store("wifi:AA", "203.0.113.7", 0.08, 4.0, 900.0, now=0.0)
        self.assertLessEqual(c.lookup("wifi:AA", "203.0.113.7", now=0.0).weight,
                             1536.0 + 1e-9)

    def test_evidence_does_not_snowball(self):
        rng = random.Random(3)
        sampler = ChannelSampler(GilbertElliott.from_burst(0.02, 2.0), rng)

        est1 = LossEstimator(p_init=0.01)
        for _ in range(10):
            est1.observe_mask(sampler.send(64))
        p1, b1, ev1 = est1.snapshot()
        self.assertAlmostEqual(ev1, 640.0, places=6)

        c = PathStatsCache()
        c.store("wifi:AA", "203.0.113.7", p1, b1, ev1, now=0.0)
        pr = c.lookup("wifi:AA", "203.0.113.7", now=0.0)

        est2 = LossEstimator(p_init=pr.p, burst_init=pr.burst,
                             prior_weight=pr.weight)
        for _ in range(10):
            est2.observe_mask(sampler.send(64))
        ev2 = est2.snapshot()[2]
        self.assertAlmostEqual(ev2, 640.0, places=6,
                               msg="물려받은 사전 가중치가 증거에 섞여 들어갔다")

    def test_prior_weight_affects_confidence_not_tracking(self):
        light = LossEstimator(p_init=0.01, prior_weight=100.0)
        heavy = LossEstimator(p_init=0.01, prior_weight=1500.0)
        self.assertLess(heavy.se, light.se)
        mask = [True] + [False] * 63
        for _ in range(10):
            light.observe_mask(mask)
            heavy.observe_mask(mask)
        self.assertFalse(light.jumped or heavy.jumped)
        self.assertAlmostEqual(heavy.p, light.p, places=12,
                               msg="사전 가중치가 추정 관성에 새어 들어갔다")

    def test_jump_invalidates_prior(self):
        est = LossEstimator(p_init=0.005, prior_weight=1500.0, burst_init=1.0)
        bad_block = [True] * 10 + [False] * 54
        jumped_once = False
        for _ in range(3):
            est.observe_mask(bad_block)
            jumped_once |= est.jumped
        self.assertTrue(jumped_once, "손실 16%가 3블록 연속인데 급변을 못 잡았다")
        self.assertEqual(est._prior_weight, 0.0,
                         "급변 후에도 사전 가중치가 남아 있다")
        self.assertLessEqual(est.n_eff, 3 * 64 + 1)

    def test_recovery_speed_independent_of_prior_weight(self):
        light = LossEstimator(p_init=0.005, prior_weight=100.0, burst_init=1.0)
        heavy = LossEstimator(p_init=0.005, prior_weight=1536.0, burst_init=1.0)
        bad_block = [True] * 7 + [False] * 57
        jumped_once = [False, False]
        for _ in range(4):
            for i, est in enumerate((light, heavy)):
                est.observe_mask(bad_block)
                jumped_once[i] |= est.jumped
        self.assertTrue(all(jumped_once))
        self.assertAlmostEqual(heavy.p, light.p, delta=0.2 * light.p,
                               msg="큰 사전 가중치가 급변 후에도 추정을 붙잡고 있다")

    def test_shield_consumes_cache_prior(self):
        c = PathStatsCache()
        c.store("wifi:AA", "203.0.113.7", 0.03, 3.0, 800.0, now=0.0)
        pr = c.lookup("wifi:AA", "203.0.113.7", now=1.0)
        d = shield(profile(768), pr.p, pr.burst)
        self.assertGreaterEqual(d.r, 1)

    def test_confidence_bound_never_reduces_protection(self):
        cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0, risk_z=2.5)
        est = LossEstimator(p_init=0.20, burst_init=4.0, prior_weight=50.0,
                            z=cfg.risk_z)
        self.assertGreater(est.p_safe, 0.4)
        ctrl = AdaptiveFecController(cfg, est)
        ctrl.cong.observe_rtt(40.0)
        d = ctrl.next_block()
        mean_r = choose_redundancy(d.k, est.p, est.burst_safe,
                                   80.0, 0.0, cfg).r
        self.assertGreaterEqual(d.r, mean_r,
                                "상한 결정이 평균 결정보다 보호를 줄였다")
        self.assertGreater(d.r, 0, "p=20% 사전값인데 보호를 껐다")


class TestEstimatorV021(unittest.TestCase):
    def test_steady_state_bias_is_small(self):
        biases = []
        for seed in range(5, 13):
            rng = random.Random(seed)
            sampler = ChannelSampler(GilbertElliott.from_burst(0.05, 4.0), rng)
            est = LossEstimator(p_init=0.01)
            tail = []
            for i in range(600):
                est.observe_mask(sampler.send(64))
                if i >= 300:
                    tail.append(est.p)
            biases.append(sum(tail) / len(tail) / 0.05 - 1.0)
        mean_bias = sum(biases) / len(biases)
        MEASURED["정상상태 손실률 편향 (시드 8평균)"] = f"{mean_bias:+.1%}"
        self.assertLess(abs(mean_bias), 0.06,
                        f"steady-state bias {mean_bias:+.1%}")

    def test_downshift_detected_by_accumulated_evidence(self):
        rng = random.Random(3)
        est = LossEstimator(p_init=0.05, burst_init=4.0)
        sampler = ChannelSampler(GilbertElliott.from_burst(0.005, 1.0), rng)
        fired = None
        for i in range(25):
            est.observe_mask(sampler.send(64))
            if fired is None and est.jumped:
                fired = i + 1
        self.assertIsNotNone(fired, "10배 하향 급변을 25블록에도 못 잡았다")
        self.assertLess(est.p, 0.02,
                        f"하향 급변 후에도 추정이 {est.p:.3f}에 머묾")
        MEASURED["하향 급변(5%->0.5%) 포착"] = f"{fired}블록"

    def test_boost_skips_the_trigger_block(self):
        est = LossEstimator(p_init=0.005, burst_init=1.0)
        bad = [True] * 10 + [False] * 54
        est.observe_mask(bad)
        p_before = est.p
        est.observe_mask(bad)
        self.assertTrue(est.jumped)
        step = (est.p - p_before) / max(10 / 64 - p_before, 1e-9)
        self.assertLess(step, 0.25, "확정 블록에 부스트가 걸렸다(표본 선택 편향)")
        self.assertEqual(est._boost_left, est.jump_boost_blocks)
        est.observe_mask(bad)
        self.assertEqual(est._boost_left, est.jump_boost_blocks - 1)

    def test_evidence_reset_only_on_rising_edge(self):
        est = LossEstimator(p_init=0.005, burst_init=1.0)
        bad = [True] * 12 + [False] * 52
        for _ in range(2):
            est.observe_mask(bad)
        obs_after_edge = est._observed
        est.observe_mask(bad)
        self.assertGreater(est._observed, obs_after_edge,
                           "급변 지속 중 새 국면 증거가 계속 지워지고 있다")


class TestInvariants(unittest.TestCase):
    def _assert_decision_bounds(self, d, cfg):
        r_cap = min(int(math.ceil(d.k * cfg.rho_max)), 255 - d.k)
        self.assertGreaterEqual(d.r, 0)
        self.assertLessEqual(d.r, r_cap, f"K={d.k}, r={d.r}가 상한 초과")
        self.assertLessEqual(d.k + d.r, 255)

    def test_survives_total_loss(self):
        cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0)
        ctrl = AdaptiveFecController(cfg)
        ctrl.cong.observe_rtt(40.0)
        for _ in range(30):
            d = ctrl.next_block()
            self._assert_decision_bounds(d, cfg)
            ctrl.on_feedback([True] * (d.k + d.r), rtt_ms=40.0)
        self.assertLessEqual(ctrl.loss.p, 1.0)
        self.assertLessEqual(ctrl.loss.p_safe, 0.9)

    def test_survives_pathological_burst(self):
        cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0)
        ctrl = AdaptiveFecController(cfg)
        ctrl.cong.observe_rtt(40.0)
        ctrl.on_feedback([False] * 25 + [True] * 150 + [False] * 25, rtt_ms=40.0)
        for _ in range(5):
            d = ctrl.next_block()
            self._assert_decision_bounds(d, cfg)
            ctrl.on_feedback([False] * (d.k + d.r), rtt_ms=40.0)

    def test_empty_and_tiny_feedback(self):
        est = LossEstimator()
        est.observe_mask([])
        est.observe_mask([True])
        est.observe_mask([False])
        self.assertTrue(0.0 <= est.p <= 1.0)
        self.assertGreaterEqual(est.n_eff, 1.0)
        self.assertTrue(0.005 < est.se < 0.05,
                        f"tiny-feedback se={est.se:.5f} - 기대 ~0.0103")

    def test_rate_collapse_keeps_bounds_every_block(self):
        cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0)
        ctrl = AdaptiveFecController(cfg)
        ctrl.cong.observe_rtt(40.0)
        rng = random.Random(9)
        sampler = ChannelSampler(GilbertElliott.from_burst(0.10, 4.0), rng)
        rates = [50e6] * 10 + [2e6] * 10 + [50e6] * 10
        for rate in rates:
            d = ctrl.next_block(rate_bps=rate)
            self._assert_decision_bounds(d, cfg)
            ctrl.on_feedback(sampler.send(d.k + d.r), rtt_ms=40.0)

    _FOOTPRINT_ALLOW = {("padfec/table.py", "open("): 1}
    _FOOTPRINT_GENERATORS = ("padfec/table.py",)

    def test_library_footprint_is_pure(self):
        import ast
        import pathlib
        base = pathlib.Path(__file__).parent
        banned = ("open(", "socket", "subprocess", "threading",
                  "multiprocessing", "os.system", "shutil", "os.remove",
                  "os.unlink", "os.rename", "mkdir", "urllib", "Popen")
        seen = 0
        for pkg in ("afec", "padfec"):
            for f in sorted((base / pkg).rglob("*.py")):
                if "__pycache__" in f.parts:
                    continue
                seen += 1
                rel = "%s/%s" % (pkg, f.relative_to(base / pkg).as_posix())
                src = f.read_text(encoding="utf-8")
                for tok in banned:
                    limit = self._FOOTPRINT_ALLOW.get((rel, tok), 0)
                    n = src.count(tok)
                    self.assertLessEqual(
                        n, limit,
                        f"{rel}: '{tok}' {n} 개 (허용 {limit}) - 격리 전제 위반")
                if rel in self._FOOTPRINT_GENERATORS:
                    self._assert_generator_is_guarded(rel, src, ast)
        self.assertGreaterEqual(seen, 14, "발자국 검사 대상이 너무 적다")

    def _assert_generator_is_guarded(self, rel, src, ast):
        tree = ast.parse(src)
        fn_spans = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn_spans.append((node.lineno, getattr(node, "end_lineno",
                                                     node.lineno)))
        local_fns = {n.name for n in tree.body
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "open"):
                inside = any(a <= node.lineno <= b for a, b in fn_spans)
                self.assertTrue(inside, "%s:%d - open 이 모듈 최상위에 있다"
                                % (rel, node.lineno))
        for stmt in tree.body:
            if not (isinstance(stmt, ast.Expr)
                    and isinstance(stmt.value, ast.Call)):
                continue
            fn = stmt.value.func
            self.assertFalse(
                isinstance(fn, ast.Name) and fn.id in local_fns,
                "%s:%d - 최상위에서 %s() 를 부른다: import 만으로 실행된다"
                % (rel, stmt.lineno,
                   getattr(fn, "id", "?")))

    def test_cache_bounds_and_eviction(self):
        c = PathStatsCache(max_entries=32)
        for i in range(300):
            c.store("wifi:AA", f"10.{i % 200}.{i // 200}.1", 0.05, 4.0,
                    500.0, now=float(i))
        self.assertLessEqual(len(c), 32)
        pr = c.lookup("wifi:AA", "10.7.0.1", now=300.0)
        self.assertTrue(0.0 <= pr.weight <= 100.0 + 1e-9)
        c.store("wifi:AA", "10.0.0.1", 0.05, 4.0, 0.0, now=301.0)
        c.store("wifi:AA", "10.0.0.1", 0.05, 4.0, -5.0, now=302.0)
        self.assertTrue(0.0 <= c.lookup("wifi:AA", "10.0.0.1",
                                        now=303.0).weight <= 100.0 + 1e-9)


class TestHandshakeRecoveryModel(unittest.TestCase):
    def test_ack_partial_false_reduces_to_v01_formula(self):
        from afec.controller import pto_ms as _pto
        p, L, rtt = 0.03, 3.0, 30.0
        got = expected_handshake_ms(2, 5, 1, 2, p, L, rtt,
                                    ack_partial=False).mean_ms
        ch = GilbertElliott.cached(p, L)
        base = _pto()
        want = rtt
        for k, r in ((2, 1), (5, 2)):
            f = ch.p_fail(k, r)
            want += base * sum((2 ** (a - 1)) * (f ** a) for a in range(1, 7))
        self.assertAlmostEqual(got, want, places=9)

    def test_partial_loss_costs_rtts_not_seconds(self):
        rtt = 30.0
        v01 = expected_handshake_ms(2, 5, 0, 0, 0.02, 1.0, rtt,
                                    ack_partial=False).mean_ms
        v022 = expected_handshake_ms(2, 5, 0, 0, 0.02, 1.0, rtt,
                                     ack_partial=True).mean_ms
        MEASURED["핸드셰이크 평균 (v0.1 모델 -> 정밀화)"] = \
            f"{v01:.0f}ms -> {v022:.0f}ms (p=2%, L=1, FEC 없음)"
        self.assertLess(v022 - rtt, 0.5 * (v01 - rtt),
                        "부분 손실이 여전히 PTO 비용으로 계산되고 있다")

    def test_burst_needs_spacing_plus_parity(self):
        single = expected_handshake_ms(2, 5, 0, 0, 0.03, 1.0, 30.0).mean_ms
        bursty = expected_handshake_ms(2, 5, 0, 0, 0.03, 4.0, 30.0).mean_ms
        self.assertGreater(bursty, single * 1.3)
        adj_fec = expected_handshake_ms(2, 5, 1, 2, 0.03, 4.0, 30.0).mean_ms
        self.assertLess(adj_fec, bursty)
        paced_fec = expected_handshake_ms(2, 5, 1, 2, 0.03, 4.0, 30.0,
                                          interleave=4).mean_ms
        self.assertLess(paced_fec, adj_fec * 0.75,
                        "페이싱+FEC 상승작용이 사라졌다")
        MEASURED["핸드셰이크 버스트 대응 (p=3%,L=4)"] = \
            f"{bursty:.0f}ms -> 인접FEC {adj_fec:.0f} -> 페이싱+FEC {paced_fec:.0f}ms"

    def test_shield_still_protects_split_hello(self):
        d = shield(profile(768), p_prior=0.02, burst_prior=3.0)
        self.assertGreaterEqual(d.r, 1)
        self.assertLess(d.t_recover_ms, 999.0,
                        "유효 T_recover가 혼합이 아니라 순수 PTO로 남아 있다")

    def test_retry_correlation_toggle_bounds_the_tail(self):
        opt = simulate_handshake(2, 5, 0, 0, 0.05, 6.0, 30.0,
                                 trials=4000, seed=9, retry_decorrelate=True)
        pes = simulate_handshake(2, 5, 0, 0, 0.05, 6.0, 30.0,
                                 trials=4000, seed=9, retry_decorrelate=False)
        self.assertGreater(pes.mean_ms, opt.mean_ms,
                           "비관 경계가 낙관 경계보다 가볍다 - 토글이 죽었다")

    def test_rquic_baseline_behaves(self):
        cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0)
        hi = simulate_data("rquic", 0.10, 4.0, 40.0, cfg, n_blocks=200, seed=5)
        lo = simulate_data("rquic", 0.0, 1.0, 40.0, cfg, n_blocks=200, seed=5)
        self.assertGreater(hi.mean_r, lo.mean_r)
        self.assertLessEqual(hi.overhead, cfg.rho_max + 0.05)


class TestHandshake(unittest.TestCase):

    def test_mlkem_splits_clienthello(self):
        self.assertEqual(profile(None).k_client, 1)
        for level in (512, 768, 1024):
            self.assertGreaterEqual(profile(level).k_client, 2,
                                    f"ML-KEM-{level}이 1패킷에 들어가 버림")

    def test_split_threshold_depends_on_ch_base(self):
        mini = CH_BASE_MINIMAL_QUIC
        self.assertEqual(profile(512, hybrid=False, ch_base=mini).k_client, 1,
                         "최소 CH에서 ML-KEM-512는 1패킷이어야 한다")
        for level in (768, 1024):
            self.assertGreaterEqual(
                profile(level, hybrid=False, ch_base=mini).k_client, 2)
        self.assertEqual(profile(512, hybrid=False,
                                 ch_base=CH_BASE_BROWSER_QUIC).k_client, 2)

    def test_clienthello_bytes_match_real_capture(self):
        mini = CH_BASE_MINIMAL_QUIC
        measured = {
            (512, False): 1032,
            (768, False): 1416,
            (1024, False): 1800,
            (768, True): 1448,
        }
        for (level, hybrid), want in measured.items():
            got = profile(level, hybrid=hybrid, ch_base=mini).client_flight
            self.assertEqual(got, want,
                             f"ML-KEM-{level} hybrid={hybrid}: 모델 {got} != 실측 {want}")
        MEASURED["ClientHello 모델 vs 실측 (4종)"] = "전부 오차 0 byte"

    def test_serverhello_also_splits_under_mlkem(self):
        base = profile(None)
        mlkem = profile(768)
        self.assertEqual(base.k_server_initial, 1)
        self.assertGreaterEqual(mlkem.k_server_initial, 2)
        self.assertEqual(base.server_initial_flight, 122)
        self.assertEqual(mlkem.server_initial_flight, 1210)

    def test_from_burst_never_builds_an_invalid_chain(self):
        from afec.channel import GilbertElliott
        for p in (0.0, 0.01, 0.3, 0.5, 0.51, 0.6, 0.8, 0.9, 0.99, 0.999):
            for L in (1.0, 1.5, 2.0, 4.0, 8.0, 64.0):
                ch = GilbertElliott.from_burst(p, L)
                for name, v in (("q_gb", ch.q_gb), ("q_bg", ch.q_bg),
                                ("p_good", ch.p_good), ("p_bad", ch.p_bad)):
                    self.assertGreaterEqual(v, 0.0, f"{name} at p={p} L={L}")
                    self.assertLessEqual(v, 1.0, f"{name} at p={p} L={L}")
                pmf = ch.erasure_pmf(32)
                self.assertAlmostEqual(sum(pmf), 1.0, places=9,
                                       msg=f"pmf sum at p={p} L={L}")
                self.assertGreaterEqual(min(pmf), -1e-15,
                                        f"negative prob at p={p} L={L}")
                for r in (0, 4, 8, 16):
                    pf = ch.p_fail(32, r)
                    self.assertGreaterEqual(pf, 0.0)
                    self.assertLessEqual(pf, 1.0)

    def test_from_burst_keeps_loss_rate_and_raises_burst(self):
        from afec.channel import GilbertElliott
        for p, L_req in ((0.9, 1.0), (0.9, 2.0), (0.85, 4.0), (0.6, 1.0)):
            ch = GilbertElliott.from_burst(p, L_req)
            self.assertAlmostEqual(ch.loss_rate, p, places=9)
            self.assertGreaterEqual(ch.mean_burst, L_req - 1e-12)
            self.assertAlmostEqual(ch.mean_burst, max(L_req, p / (1 - p)),
                                   places=9)
        for p, L in ((0.05, 4.0), (0.01, 1.0), (0.2, 2.0)):
            ch = GilbertElliott.from_burst(p, L)
            self.assertAlmostEqual(ch.loss_rate, p, places=12)
            self.assertAlmostEqual(ch.mean_burst, L, places=12)

    def test_invalid_chain_raises_instead_of_returning_garbage(self):
        from afec.channel import GilbertElliott
        with self.assertRaises(ValueError):
            GilbertElliott(q_gb=1.5, q_bg=0.5).erasure_pmf(8)
        with self.assertRaises(ValueError):
            GilbertElliott(q_gb=0.5, q_bg=-0.1).erasure_pmf(8)

    def test_controller_survives_extreme_estimates(self):
        cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0)
        for p in (0.4, 0.47, 0.5, 0.6, 0.75, 0.9):
            for L in (1.0, 2.0, 4.0):
                d = choose_redundancy(32, p, L, 40.0, 0.0, cfg)
                self.assertGreaterEqual(d.r, 0)
                self.assertLessEqual(d.r, 16)
                self.assertGreaterEqual(d.p_fail, 0.0)
                self.assertLessEqual(d.p_fail, 1.0)
                self.assertTrue(math.isfinite(d.cost))

    def test_H2_handshake_r_is_decided_by_cost_not_by_a_borrowed_threshold(self):
        cfg = FecConfig(rate_bps=10e6)
        prof = profile(768)
        for p, L in ((0.02, 1.0), (0.05, 1.0), (0.02, 3.0), (0.05, 3.0)):
            d = shield(prof, p, L, cfg)
            self.assertFalse(getattr(d, "cap_bound", False),
                             f"흔한 구간 p={p} L={L}에서 상한이 답을 자른다")
            best = min(d.table, key=lambda t: t[1])
            self.assertEqual(d.r, best[0], "J의 최소가 아니다")
        self.assertGreater(shield(prof, 0.05, 3.0, cfg).r, 1)
        d_hi = shield(prof, 0.05, 8.0, cfg)
        self.assertTrue(getattr(d_hi, "cap_bound", False),
                        "상한에 걸렸는데 보고되지 않는다")

    def test_H1_server_pto_uses_initial_space_only(self):
        prof = profile(768)
        self.assertEqual(prof.k_server_initial, 2)
        self.assertEqual(prof.k_server_handshake, 3)
        for p, L in ((0.02, 2.0), (0.05, 3.0)):
            a = expected_handshake_ms(prof.k_client, prof.k_server, 0, 0,
                                      p, L, 30.0)
            b = expected_handshake_ms(prof.k_client, prof.k_server, 0, 0,
                                      p, L, 30.0,
                                      server_critical=prof.k_server_initial)
            self.assertGreater(b.mean_ms, a.mean_ms,
                               "Initial 공간 기준이면 더 비관적이어야 한다")
        d = shield(prof, 0.05, 3.0, side="server")
        self.assertEqual(d.k, prof.k_server_initial)

    def test_H10_prior_channel_allows_consecutive_losses(self):
        from afec.channel import GilbertElliott
        for p in (0.01, 0.05, 0.10):
            degenerate = GilbertElliott.from_burst(p, 1.0)
            self.assertEqual(degenerate.erasure_pmf(2)[2], 0.0)
            prior = GilbertElliott.for_prior(p, 1.0)
            self.assertGreater(prior.erasure_pmf(2)[2], 0.0,
                               "사전 채널은 전멸이 가능해야 한다")
            self.assertAlmostEqual(prior.erasure_pmf(2)[2], p * p, places=12)
        self.assertAlmostEqual(GilbertElliott.for_prior(0.05, 4.0).mean_burst,
                               4.0, places=9)

    def test_H7_partial_loss_is_never_costlier_than_total_loss(self):
        from afec.controller import pto_ms as _pto
        prof = profile(768)
        for srtt in (10.0, 20.0, 30.0, 50.0, 66.0, 100.0, 200.0):
            d = shield(prof, 0.05, 3.0, srtt_ms=srtt)
            base = _pto(srtt)
            self.assertGreater(
                base, 0.0, f"srtt={srtt}에서 PTO 기준선이 0 이면 시험이 공허하다")
            self.assertGreaterEqual(d.t_recover_ms, 0.0)
            self.assertLessEqual(d.t_recover_ms, base + 1e-9,
                                 f"srtt={srtt}에서 회복 대가가 PTO를 넘는다")
            self.assertGreaterEqual(
                d.t_recover_ms, srtt - 1e-9,
                f"srtt={srtt}에서 회복 대가가 왕복 하나보다 작다 - "
                f"상수로 굳었는지 확인하라")
        _tr = [shield(prof, 0.05, 3.0, srtt_ms=s).t_recover_ms
               for s in (10.0, 200.0)]
        self.assertGreater(
            _tr[1] - _tr[0], 10.0,
            f"t_recover 가 srtt 10->200 ms 에서 {_tr[1]-_tr[0]:.1f} ms 밖에 "
            f"안 움직인다 - 상수로 굳었다(H7 결함의 정체)")

    def test_E2_prior_weight_does_not_change_tracking_inertia(self):
        masses = set()
        for w in (100.0, 80.0, 48.0, 25.0, 1.0):
            e = LossEstimator(p_init=0.01, burst_init=4.0, prior_weight=w)
            masses.add(round(e._sent, 9))
            self.assertAlmostEqual(e.p, 0.01, places=12,
                                   msg="사전 점추정은 w와 무관해야 한다")
        self.assertEqual(len(masses), 1,
                         f"EWMA 질량이 prior_weight에 따라 달라진다: {masses}")
        traj = {}
        for w in (100.0, 25.0):
            e = LossEstimator(p_init=0.01, burst_init=4.0, prior_weight=w)
            for _ in range(4):
                e.observe_mask([True] * 6 + [False] * 58)
            traj[w] = e.p
        self.assertAlmostEqual(traj[100.0], traj[25.0], places=12)

    def test_E1_unsupported_burst_prior_fades_with_evidence(self):
        e = LossEstimator(p_init=0.20, burst_init=6.0, prior_weight=100.0)
        start = e.burst
        for _ in range(300):
            e.observe_mask([False] * 64)
        self.assertLess(e.burst, start - 1.0,
                        "무증거 사전 버스트가 관측이 쌓여도 안 지워진다")
        self.assertLess(e.burst, 1.5)
        e2 = LossEstimator(p_init=0.05, burst_init=4.0, prior_weight=100.0)
        for _ in range(40):
            e2.observe_mask([False] * 20 + [True] * 4 + [False] * 40)
        self.assertGreater(e2.burst, 2.5, "실제 관측된 버스트까지 지우면 안 된다")

    def test_E4_down_cusum_is_not_starved_of_negative_evidence(self):
        import random as _r
        from afec.channel import GilbertElliott
        confirms = []
        for seed in range(12):
            rng = _r.Random(100 + seed)
            ch = GilbertElliott.from_burst(0.05, 4.0)
            s_ = ChannelSampler(ch, rng)
            e = LossEstimator(p_init=0.05, burst_init=4.0, prior_weight=100.0)
            was = False
            n = 0
            for _ in range(300):
                e.observe_mask(s_.send(64))
                if e.jumped and not was:
                    n += 1
                was = e.jumped
            confirms.append(n)
        mean = sum(confirms) / len(confirms)
        MEASURED["정상 채널 허위 급변 (연결당, 시드 12)"] = "%.2f회" % mean
        self.assertLess(mean, 4.0,
                        f"정상 채널에서 연결당 {mean:.2f}회 급변 - CUSUM 표류")
        e2 = LossEstimator(p_init=0.02, burst_init=1.0, prior_weight=100.0)
        e2._down_llr = 2.0
        before = e2._down_llr
        spike = [True] * 12 + [False] * 52
        self.assertTrue(e2._is_surprising(64, 12), "상단 검정이 안 걸렸다")
        self.assertLess(e2._down_llr, before,
                        "상단이 걸린 블록에서 하단 CUSUM이 갱신되지 않았다")

    def test_C5_export_cap_applies_to_the_default_prior_too(self):
        c = PathStatsCache(prior_out_cap=50.0)
        miss = c.lookup("wifi:home", "203.0.113.10", now=0.0)
        self.assertLessEqual(miss.weight, 50.0)
        c.store("wifi:home", "203.0.113.10", 0.05, 4.0, 1536.0, now=0.0)
        hit = c.lookup("wifi:home", "203.0.113.10", now=0.0)
        self.assertLessEqual(hit.weight, 50.0)

    def test_key_share_sizes_match_fips203(self):
        self.assertEqual(profile(768).client_share, 1184 + 32)
        self.assertEqual(profile(768).server_share, 1088 + 32)
        self.assertEqual(profile(1024, hybrid=False).client_share, 1568)

    def test_shield_adds_redundancy_even_at_low_loss(self):
        d = shield(profile(768), 0.005, 1.0)
        self.assertGreaterEqual(d.r, 1)

    def test_analytic_matches_simulation(self):
        TOL = {0.01: 0.10, 0.05: 0.15}
        for p in (0.01, 0.05):
            an = expected_handshake_ms(2, 5, 0, 0, p, 3.0, 30.0)
            mc = simulate_handshake(2, 5, 0, 0, p, 3.0, 30.0, trials=40000)
            rel = abs(mc.mean_ms - an.mean_ms) / an.mean_ms
            MEASURED[f"핸드셰이크 해석해 vs MC (p={p:.0%})"] = (
                f"{an.mean_ms:.0f} vs {mc.mean_ms:.0f} ms ({rel:+.0%})")
            self.assertLess(
                rel, TOL[p],
                f"p={p:.0%}: 상대오차 {rel:.1%} > 허용 {TOL[p]:.0%} "
                f"(해석 {an.mean_ms:.1f} vs MC {mc.mean_ms:.1f} ms)")
            self.assertGreaterEqual(
                an.mean_ms, mc.mean_ms - 0.02 * an.mean_ms,
                f"p={p:.0%}: 해석해가 MC 보다 낙관적이다 "
                f"({an.mean_ms:.1f} < {mc.mean_ms:.1f}) - "
                f"'독립 가정이라 비관적' 이라는 주석과 어긋난다")

    def test_fec_reduces_handshake_time(self):
        for p in (0.01, 0.05, 0.10):
            without = expected_handshake_ms(2, 5, 0, 0, p, 3.0, 30.0).mean_ms
            with_fec = expected_handshake_ms(2, 5, 1, 1, p, 3.0, 30.0).mean_ms
            self.assertLess(with_fec, without, f"p={p}에서 FEC가 도움이 안 됨")


class TestEndToEnd(unittest.TestCase):

    def test_real_codec_with_controller(self):
        cfg = FecConfig(rate_bps=50e6, delay_budget_ms=5.0, k_max=16)
        ctrl = AdaptiveFecController(cfg)
        ctrl.cong.observe_rtt(40.0)
        rng = random.Random(77)
        chan = GilbertElliott.from_burst(0.06, 3.0)
        sampler = ChannelSampler(chan, rng)

        sym_size = 48
        decoded_ok = decode_failed = 0
        mu_ok = var_ok = 0.0

        for _ in range(120):
            d = ctrl.next_block()
            pmf = chan.erasure_pmf(d.k + d.r)
            p_ok = sum(pmf[:d.r + 1])
            mu_ok += p_ok
            var_ok += p_ok * (1.0 - p_ok)
            code = RSErasureCode(d.k, d.r)
            source = [bytes(rng.randrange(256) for _ in range(sym_size))
                      for _ in range(d.k)]
            allsym = source + code.encode(source)

            mask = sampler.send(d.k + d.r)
            received = {i: s for i, (s, lost) in enumerate(zip(allsym, mask))
                        if not lost}
            n_lost = sum(mask)

            if n_lost <= d.r:
                recovered = code.decode(received)
                self.assertEqual(recovered, source,
                                 f"소실 {n_lost}개 <= r={d.r} 인데 복구 실패")
                decoded_ok += 1
            else:
                with self.assertRaises(ValueError):
                    code.decode(received)
                decode_failed += 1

            ctrl.on_feedback(mask, rtt_ms=40.0)

        MEASURED["실제 부호기 블록 복구"] = f"{decoded_ok}/{decoded_ok + decode_failed}"
        total = decoded_ok + decode_failed
        sigma = var_ok ** 0.5
        self.assertGreaterEqual(
            decoded_ok, mu_ok - 5.0 * sigma,
            f"복구 {decoded_ok}/{total} < 기대 {mu_ok:.1f} - 5σ({sigma:.1f})")
        self.assertGreaterEqual(
            mu_ok / total, 0.90,
            f"제어기가 고른 r 의 기대 복구율 {mu_ok / total:.3f} < 0.90")

    def test_adaptive_beats_static_in_worst_case(self):
        cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0)
        probs = (0.0, 0.005, 0.02, 0.05, 0.10)
        regret = {}
        for pol in ("none", "static", "adaptive"):
            worst = 0.0
            for p in probs:
                mine = simulate_data(pol, p, 4.0, 40.0, cfg).total_ms
                best = simulate_data("oracle", p, 4.0, 40.0, cfg).total_ms
                worst = max(worst, mine / best - 1.0)
            regret[pol] = worst
            MEASURED[f"최악 후회 ({pol})"] = f"{worst:.1%}"

        self.assertLess(regret["adaptive"], regret["static"])
        self.assertLess(regret["adaptive"], regret["none"])
        self.assertLess(regret["adaptive"], 0.15)

    def test_no_redundancy_on_clean_link(self):
        cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0)
        r = simulate_data("adaptive", 0.0, 1.0, 40.0, cfg)
        MEASURED["무손실 링크 오버헤드"] = f"{r.overhead:.1%}"
        self.assertLess(r.overhead, 0.05)


def benchmark_codec():
    rng = random.Random(2)
    k, r, size = 32, 8, 1200
    code = RSErasureCode(k, r)
    source = [bytes(rng.randrange(256) for _ in range(size)) for _ in range(k)]

    t0 = time.perf_counter()
    reps = 20
    for _ in range(reps):
        parity = code.encode(source)
    enc_ms = (time.perf_counter() - t0) / reps * 1000.0

    allsym = source + parity
    lost = set(rng.sample(range(k + r), r))
    received = {i: allsym[i] for i in range(k + r) if i not in lost}
    t0 = time.perf_counter()
    for _ in range(reps):
        code.decode(received)
    dec_ms = (time.perf_counter() - t0) / reps * 1000.0

    print(f"\n  RS({k + r},{k}) x {size}B  (pure Python)")
    print(f"    encode : {enc_ms:7.2f} ms/block  = {enc_ms / r:.3f} ms per repair symbol")
    print(f"    decode : {dec_ms:7.2f} ms/block  (worst case: {r} erasures)")
    print(f"    -> FecConfig.cpu_cost_ms_per_symbol 후보값: {enc_ms / r:.3f}")
    print("       ⚠️ 정정(2026-08-17 실측): C 구현은 100배가 아니라 **약 4배** 빠르다")
    print("       (experiments/e8_cpu_cost.py, gcc -O3 -march=native, i7-14700HX:")
    print("        RS(40,32) 파이썬 0.043 vs C 0.011 ms/심볼 = 3.9x.")
    print("        rs.py가 bytes.translate + big-int XOR로 이미 C 레벨에서 돌기 때문)")


if __name__ == "__main__":
    print("=" * 74)
    print("PQ-AFEC 검증 스위트")
    print("=" * 74)

    suite = unittest.defaultTestLoader.loadTestsFromModule(__import__("__main__"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)

    print("\n" + "=" * 74)
    print("검증 중 측정된 값")
    print("=" * 74)
    for name, value in MEASURED.items():
        print(f"  {name:<40} {value}")

    benchmark_codec()

    print("\n" + "=" * 74)
    print(f"결과: {result.testsRun}개 실행, "
          f"실패 {len(result.failures)}, 에러 {len(result.errors)}")
    print("=" * 74)
    raise SystemExit(0 if result.wasSuccessful() else 1)
