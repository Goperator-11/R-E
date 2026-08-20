"""알고리즘 검증 스위트.

    python verify.py

"돌아간다"와 "맞게 돌아간다"는 다르다. 여기서 확인하는 것:

  A. 실제 Reed-Solomon 부호가 정말 MDS인가
     - 시뮬레이터와 비용식 전체가 "소실 r개까지 복구"라는 가정 위에 서 있다.
       그 가정을 실제 부호기로 검증한다. 여기가 무너지면 나머지는 전부 무의미하다.
  B. DP로 구한 P_fail이 맞는가
     - 독립 몬테카를로, 그리고 iid 경우의 정확한 이항분포와 대조한다.
  C. 제어기가 정말 비용을 최소화하는가
     - 완전탐색으로 argmin을 다시 구해 대조한다.
  D. 추정기가 참값으로 수렴하는가
  E. 핸드셰이크 해석해가 시뮬레이션과 맞는가
  F. 전 구간 통합 - 진짜 부호기로 인코딩/복호까지 돌려서 원본이 복원되는가

콘솔 출력은 ASCII만 쓴다(cp949 인코딩 에러 방지).
"""

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

MEASURED: dict[str, str] = {}   # 검증 중 잰 값들 (마지막에 요약 출력)

def _harden_console():
    """로케일이 빈약한 환경(리눅스 LANG=C, Windows cp949)에서 출력 크래시 방지.

    이 프로젝트는 마지막 print의 em-dash 하나로 12분 계산을 날린 적이 있다.
    인코딩이 못 담는 문자는 ?로 강등시켜서, 출력 때문에 계산이 죽는 일은
    구조적으로 없앤다. (표시가 깨질 뿐 계산·파일 기록은 무사하다)
    """
    import sys
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


_harden_console()


# ─────────────────────────────────────────────── A. 유한체와 RS 부호

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
    """핵심 검증: 임의의 r개 소실이 복구되고, r+1개면 실패해야 한다."""

    def _symbols(self, rng, k, size):
        return [bytes(rng.randrange(256) for _ in range(size)) for _ in range(k)]

    def test_recovers_any_r_erasures(self):
        rng = random.Random(7)
        for k, r in ((4, 2), (8, 4), (16, 8), (32, 8), (10, 1)):
            code = RSErasureCode(k, r)
            source = self._symbols(rng, k, 24)
            parity = code.encode(source)
            allsym = source + parity

            # 정확히 r개를 지우는 모든 경우를 무작위로 30번 뽑아 확인
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
        """원본 K개가 전부 사라지고 이중화만 남은 극단 - MDS면 이것도 복구된다."""
        rng = random.Random(13)
        k = 8
        code = RSErasureCode(k, k)
        source = self._symbols(rng, k, 32)
        parity = code.encode(source)
        received = {k + i: parity[i] for i in range(k)}
        self.assertEqual(code.decode(received), source)


# ─────────────────────────────────────────────── B. 채널 모델과 P_fail

class TestChannelModel(unittest.TestCase):

    def test_pmf_is_a_distribution(self):
        for p, L, n in ((0.02, 1.0, 20), (0.05, 4.0, 32), (0.2, 8.0, 16)):
            pmf = GilbertElliott.from_burst(p, L).erasure_pmf(n)
            self.assertAlmostEqual(sum(pmf), 1.0, places=9)
            self.assertTrue(all(v >= -1e-15 for v in pmf))

    def test_iid_case_matches_exact_binomial(self):
        """버스트 없는 경우 DP는 이항분포와 정확히 일치해야 한다."""
        for p, n in ((0.01, 24), (0.1, 16), (0.3, 12)):
            pmf = GilbertElliott.bernoulli(p).erasure_pmf(n)
            for i in range(n + 1):
                exact = math.comb(n, i) * p ** i * (1 - p) ** (n - i)
                self.assertAlmostEqual(pmf[i], exact, places=10,
                                       msg=f"p={p}, n={n}, i={i}")

    def test_dp_matches_monte_carlo(self):
        """DP의 P_fail을 독립 시뮬레이션과 대조."""
        rng = random.Random(21)
        worst = 0.0
        for p, L, k, r in ((0.02, 1.0, 20, 2), (0.05, 4.0, 24, 6),
                           (0.10, 8.0, 16, 8), (0.01, 3.0, 32, 1)):
            ch = GilbertElliott.from_burst(p, L)
            predicted = ch.p_fail(k, r)
            sampler = ChannelSampler(ch, rng)
            trials, fails = 40000, 0
            for _ in range(trials):
                sampler.reset_state()          # DP는 정상분포 시작을 가정한다
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
        """from_burst(p, L)이 정말 손실률 p, 평균 버스트 L을 내는가."""
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
        """최적화한 fail_curve가 개별 p_fail과 같은 값을 주는가."""
        ch = GilbertElliott.from_burst(0.03, 3.0)
        curve = ch.fail_curve(24, 10, interleave=2)
        for r, v in enumerate(curve):
            self.assertAlmostEqual(v, ch.p_fail(24, r, interleave=2), places=12)


# ─────────────────────────────────────────────── C. 제어기

class TestController(unittest.TestCase):

    def test_r_star_really_minimizes_cost(self):
        """제어기가 고른 r이 정말 argmin인지 완전탐색으로 대조."""
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
        """K가 줄면 히스테리시스가 과거의 큰 r을 물고 상한을 넘길 수 있다.

        손실 심한 구간에서 r을 키워 둔 뒤 링크 속도를 떨어뜨려 K를 줄인다.
        상한을 다시 적용하지 않으면 rho_max와 GF(256) 한계를 조용히 넘는다.
        """
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
        """히스테리시스로 r이 바뀌면 cost/P_fail도 그 r 기준이어야 한다."""
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


# ─────────────────────────────────────────────── D. 추정기

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
        """정상적인 버스트 변동을 국면 전환으로 오인하면 안 된다."""
        est = LossEstimator(p_init=0.005)
        trace = self._feed(est, 0.005, 4.0, 400)
        rate = sum(1 for t in trace[100:] if t[2]) / len(trace[100:])
        MEASURED["정상 구간 급변 오탐률"] = f"{rate:.1%}"
        self.assertLess(rate, 0.03, f"오탐률 {rate:.1%} - 너무 자주 급변으로 판정")

    def test_surprise_detector_catches_real_shift(self):
        est = LossEstimator(p_init=0.005)
        self._feed(est, 0.005, 4.0, 200)          # 안정 구간으로 학습
        trace = self._feed(est, 0.10, 4.0, 20, seed=99)   # 급변
        self.assertTrue(any(t[2] for t in trace[:6]),
                        "손실률이 20배로 뛰었는데 급변을 못 잡았다")

    def test_confidence_bound_is_conservative_when_cold(self):
        est = LossEstimator(p_init=0.01)
        self.assertGreater(est.p_safe, est.p)

    def test_uncertainty_shrinks_as_evidence_accumulates(self):
        """연결 초반엔 se가 크고, 관측이 쌓이면 줄어야 한다.

        EWMA 창 크기만 쓰면 n_eff가 첫 블록부터 상수(약 1536)라 콜드 스타트에서
        불확실성이 0에 가깝게 나온다. 그러면 근거 없이 자신만만해진다.
        """
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
        """같은 손실률·같은 표본 수라도 버스트가 심하면 불확실성이 커야 한다.

        이항 표준오차는 표본 독립을 가정한다. 버스트 손실은 강하게 상관돼
        있어서 실제 분산이 훨씬 크다. 보정 없이 쓰면 하필 보호가 가장
        필요한 순간에 불확실성을 과소평가한다.
        """
        flat, bursty = LossEstimator(), LossEstimator()
        for est, L in ((flat, 1.0), (bursty, 4.0)):
            est._lost, est._sent, est.burst = 3.0, 64.0, L

        self.assertGreater(bursty.se, flat.se)
        # 이론 팽창계수 sqrt(2L(1-p)-1) 과 일치해야 한다
        p = flat.p
        expect = math.sqrt(2.0 * 4.0 * (1.0 - p) - 1.0)
        self.assertAlmostEqual(bursty.se / flat.se, expect, places=6)
        MEASURED["버스트 보정 se 배율 (L=4)"] = f"x{bursty.se / flat.se:.2f}"

    def test_rtt_min_forgets_old_path(self):
        """경로가 바뀌어 기저 RTT가 올라가면 rtt_min도 따라 올라가야 한다.

        전역 최솟값을 쓰면 옛 값이 영원히 남아 팽창률이 항상 높게 잡히고,
        혼잡 확신도 g가 1에 붙박여 **FEC가 영구히 억제된다.**
        """
        from afec.estimator import CongestionDetector
        cong = CongestionDetector(rtt_min_window=50)

        for _ in range(100):                  # 옛 경로: 20 ms
            cong.observe_rtt(20.0)
        self.assertAlmostEqual(cong.rtt_min, 20.0, places=6)
        self.assertEqual(cong.g, 0.0)

        for _ in range(200):                  # 새 경로: 60 ms (혼잡 아님)
            cong.observe_rtt(60.0)
        self.assertAlmostEqual(cong.rtt_min, 60.0, places=6,
                               msg="옛 경로의 최솟값을 아직 물고 있다")
        self.assertEqual(cong.g, 0.0, "경로 변경을 혼잡으로 오판하고 있다")

    def test_congestion_still_detected_after_window_fix(self):
        """창을 도입해도 진짜 큐 팽창은 여전히 잡아야 한다."""
        from afec.estimator import CongestionDetector
        cong = CongestionDetector(rtt_min_window=200)
        for _ in range(50):
            cong.observe_rtt(20.0)
        for _ in range(50):                   # 큐가 차서 RTT가 2배
            cong.observe_rtt(40.0)
        self.assertGreater(cong.g, 0.5)

    def test_burst_runs_stitched_across_blocks(self):
        """블록 경계를 걸친 손실 구간을 이어 붙이는가."""
        est = LossEstimator()
        est.burst = 1.0
        # 블록 A 끝 3개 손실 + 블록 B 앞 3개 손실 = 실제로는 6연속 1회
        est.observe_mask([False] * 5 + [True] * 3)
        est.observe_mask([True] * 3 + [False] * 5)
        self.assertGreater(est.burst, 1.5,
                           "경계를 걸친 6연속 손실을 짧게 세고 있다")


# ─────────────────────────────────────────────── D2. 목적지별 통계 캐시 (v0.2)

class TestPathStatsCache(unittest.TestCase):
    """캐시의 키 설계·감쇠·병합과, '캐시가 틀렸을 때'의 안전장치를 검증한다."""

    def test_same_slash24_shares_entry(self):
        c = PathStatsCache()
        c.store("wifi:AA", "203.0.113.7", 0.05, 4.0, 800.0, now=0.0)
        hit = c.lookup("wifi:AA", "203.0.113.200", now=1.0)   # 같은 /24
        self.assertEqual(hit.source, "exact")
        self.assertAlmostEqual(hit.p, 0.05, places=9)
        miss = c.lookup("wifi:AA", "203.0.114.7", now=1.0)    # 다른 /24
        self.assertEqual(miss.source, "network")               # 망 집계로 폴백

    def test_network_aggregate_fallback(self):
        """같은 망에서 처음 가는 목적지도 망 집계의 덕을 봐야 한다."""
        c = PathStatsCache()
        c.store("wifi:AA", "203.0.113.7", 0.08, 3.0, 600.0, now=0.0)
        hit = c.lookup("wifi:AA", "198.51.100.9", now=1.0)
        self.assertEqual(hit.source, "network")
        self.assertAlmostEqual(hit.p, 0.08, places=9)

    def test_mobility_reads_nothing_from_old_network(self):
        """Wi-Fi -> 셀룰러 이동 무효화는 키 설계가 공짜로 해결한다.

        접속망 ID가 키의 절반이므로 망이 바뀌면 키가 달라져 옛 항목을
        아예 읽지 않는다. purge 이벤트나 감지 로직이 필요 없고, 같은 망으로
        돌아오면 그 망의 통계가 그대로 살아 있어야 한다.
        """
        c = PathStatsCache()
        c.store("wifi:AA", "203.0.113.7", 0.05, 4.0, 800.0, now=0.0)
        moved = c.lookup("cell:450-08", "203.0.113.7", now=1.0)
        self.assertEqual(moved.source, "default")
        back = c.lookup("wifi:AA", "203.0.113.7", now=2.0)
        self.assertEqual(back.source, "exact")

    def test_age_decays_then_expires(self):
        """오래된 항목은 발언권(weight)이 줄고, 더 오래되면 없는 항목이 된다.

        반출 상한(prior_out_cap=100) 아래에서 감쇠가 보이도록 증거 80으로
        저장한다: 80 -> 40(반감 1번) -> 20 < w_min(25) -> 소멸.
        """
        c = PathStatsCache(half_life_s=600.0, w_min=25.0)
        c.store("wifi:AA", "203.0.113.7", 0.05, 4.0, 80.0, now=0.0)
        fresh = c.lookup("wifi:AA", "203.0.113.7", now=0.0)
        aged = c.lookup("wifi:AA", "203.0.113.7", now=600.0)     # 반감기 1번
        self.assertAlmostEqual(aged.weight, fresh.weight / 2.0, delta=1.0)
        self.assertAlmostEqual(aged.p, fresh.p, places=9)        # 점추정은 유지
        gone = c.lookup("wifi:AA", "203.0.113.7", now=1200.0)    # 20 < w_min
        self.assertEqual(gone.source, "default")

    def test_lookup_weight_capped_at_default_prior(self):
        """반출 가중치는 기본 사전(100)을 넘지 않는다 - (w,z) 공동 튜닝의 결론.

        반출 w > 100이면 '캐시가 낮게 틀렸을 때' 후회가 콜드 스타트를
        초과한다(z=1.5에서 w=200이면 39.4% vs 콜드 33.5%). 캐시의 값어치는
        확신이 아니라 시작점이다. 저장 가중치(신선도 예산)는 그대로 크다.
        """
        c = PathStatsCache()
        c.store("wifi:AA", "203.0.113.7", 0.05, 4.0, 1536.0, now=0.0)
        pr = c.lookup("wifi:AA", "203.0.113.7", now=0.0)
        self.assertLessEqual(pr.weight, 100.0 + 1e-9)
        # 저장 쪽은 크게 남아 있어서 반감기 4번 뒤에도 살아 있다 (1536/16=96)
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
        """캐시를 거칠 때마다 증거가 눈덩이처럼 불어나면 안 된다.

        snapshot()은 직접 관측한 심볼 수만 반환해야 한다. 물려받은 사전
        가중치까지 더해 저장하면 (사전 640 -> 저장 640+640 -> 다음 사전 1280
        -> ...) 몇 번 만에 관측한 적 없는 확신을 주장하는 캐시가 된다.
        """
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
        """w는 확신(se)만 조절하고 추정치의 관성은 건드리면 안 된다.

        처음엔 반대로 설계했다(w가 EWMA 질량에 들어가 큰 w = 느린 추적).
        그러자 틀린 캐시에서 벗어나는 속도가 w에 비례해 느려져, 틀린-낮음
        캐시 후회가 w=1536에서 49%까지 갔다. 추적 속도는 채널 추적의 문제지
        캐시 신뢰의 문제가 아니다 - 사전값은 시작점과 확신도만 준다.
        """
        light = LossEstimator(p_init=0.01, prior_weight=100.0)
        heavy = LossEstimator(p_init=0.01, prior_weight=1500.0)
        self.assertLess(heavy.se, light.se)   # 확신은 w를 따라간다
        mask = [True] + [False] * 63          # 손실 1개짜리 블록 (놀랍지 않음)
        for _ in range(10):
            light.observe_mask(mask)
            heavy.observe_mask(mask)
        self.assertFalse(light.jumped or heavy.jumped)
        # 추정 궤적은 w와 무관하게 같아야 한다
        self.assertAlmostEqual(heavy.p, light.p, places=12,
                               msg="사전 가중치가 추정 관성에 새어 들어갔다")

    def test_jump_invalidates_prior(self):
        """국면 전환이 확정되면 캐시가 물려준 사전값도 무효화해야 한다.

        틀린 캐시에서 벗어나는 속도가 캐시 설계의 생명이다. 급변 판정 후에도
        prior_weight가 n_eff를 부풀리고 있으면, 새 국면의 증거가 몇 블록
        없는데도 se가 작게 나와 제어기가 계속 옛 사전값 편에 선다.
        """
        est = LossEstimator(p_init=0.005, prior_weight=1500.0, burst_init=1.0)
        bad_block = [True] * 10 + [False] * 54
        jumped_once = False
        for _ in range(3):
            est.observe_mask(bad_block)
            jumped_once |= est.jumped           # jumped는 순간 신호다
        self.assertTrue(jumped_once, "손실 16%가 3블록 연속인데 급변을 못 잡았다")
        self.assertEqual(est._prior_weight, 0.0,
                         "급변 후에도 사전 가중치가 남아 있다")
        self.assertLessEqual(est.n_eff, 3 * 64 + 1)

    def test_recovery_speed_independent_of_prior_weight(self):
        """틀린 캐시에서 벗어나는 속도는 w와 무관해야 한다 (v0.2 결함 2).

        급변 판정이 prior_weight(불확실성 장부)만 지우고 EWMA 질량(_sent)을
        안 지우면, 큰 w일수록 분모에 사전 질량이 남아 jump_alpha가 설계
        속도로 못 움직인다. 실측: 틀린-낮음 캐시의 후회가 w=100에서 33.9%,
        w=1536에서 49.0%로 벌어졌다. 질량 재조정 후에는 같아야 한다.
        """
        light = LossEstimator(p_init=0.005, prior_weight=100.0, burst_init=1.0)
        heavy = LossEstimator(p_init=0.005, prior_weight=1536.0, burst_init=1.0)
        bad_block = [True] * 7 + [False] * 57       # 손실 11% 블록
        jumped_once = [False, False]
        for _ in range(4):
            for i, est in enumerate((light, heavy)):
                est.observe_mask(bad_block)
                jumped_once[i] |= est.jumped        # jumped는 순간 신호다
        self.assertTrue(all(jumped_once))
        self.assertAlmostEqual(heavy.p, light.p, delta=0.2 * light.p,
                               msg="큰 사전 가중치가 급변 후에도 추정을 붙잡고 있다")

    def test_shield_consumes_cache_prior(self):
        """핸드셰이크 shield와 데이터 구간이 같은 캐시를 쓴다 - 배선 확인."""
        c = PathStatsCache()
        c.store("wifi:AA", "203.0.113.7", 0.03, 3.0, 800.0, now=0.0)
        pr = c.lookup("wifi:AA", "203.0.113.7", now=1.0)
        d = shield(profile(768), pr.p, pr.burst)
        self.assertGreaterEqual(d.r, 1)

    def test_confidence_bound_never_reduces_protection(self):
        """신뢰상한이 '가망 없음' 능선을 넘어도 보호를 끄면 안 된다 (v0.2 결함).

        argmin J는 p에 단조가 아니다. p_safe가 능선을 넘으면 (r_max로도
        P_fail ~ 1) 실패항이 상수가 되어 r*=0(포기)로 무너진다. 캐시가
        p=0.2를 물려준 채널에서 se 팽창으로 p_safe=0.53이 되자 실제로 r=0이
        나왔고, 참값 10% 채널에서 블록 6개 연속 실패(후회 45%)를 만들었다.
        상한은 불확실성 헤지이므로 보호를 늘리는 방향으로만 작용해야 한다.
        """
        # z는 능선을 넘는 조건을 만들기 위해 명시한다(가드 자체는 z와 무관)
        cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0, risk_z=2.5)
        est = LossEstimator(p_init=0.20, burst_init=4.0, prior_weight=50.0,
                            z=cfg.risk_z)
        self.assertGreater(est.p_safe, 0.4)      # 능선 너머 (포기 영역)
        ctrl = AdaptiveFecController(cfg, est)
        ctrl.cong.observe_rtt(40.0)
        d = ctrl.next_block()
        mean_r = choose_redundancy(d.k, est.p, est.burst_safe,
                                   80.0, 0.0, cfg).r
        self.assertGreaterEqual(d.r, mean_r,
                                "상한 결정이 평균 결정보다 보호를 줄였다")
        self.assertGreater(d.r, 0, "p=20% 사전값인데 보호를 껐다")


# ─────────────────────────────────────────────── D3. v0.2.1 추정기 결함 수정

class TestEstimatorV021(unittest.TestCase):
    """급변 부스트의 표본 선택 편향(결함 13)과 하향 SPRT 검증."""

    def test_steady_state_bias_is_small(self):
        """정상 상태에서 추정이 위로 표류하면 안 된다 (결함 13 회귀 방지).

        놀라운 블록에 jump_alpha를 주는 것은 관측치를 자기 자신의 극단성으로
        가중하는 것이다. 수정 전 실측 +10.3%(시드 16). 부스트를 확정 이후
        블록으로 옮긴 뒤 -3~0%. 시드 8개 평균으로 |편향| < 6%를 못박는다.
        (수정 전 코드는 이 검사를 통과하지 못한다)
        """
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
        """손실이 급감한 국면을 누적 증거(SPRT)로 잡아야 한다.

        단일 블록 하단 꼬리확률로는 원리적으로 못 잡는다: 소실 분포는 바닥이
        0에 붙어 있어 최선의 관측(무손실)조차 하단 꼬리가 크다.
        """
        rng = random.Random(3)
        est = LossEstimator(p_init=0.05, burst_init=4.0)   # 모델은 5%라 믿는 중
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
        """jump_alpha는 급변을 확정시킨 블록이 아니라 다음 블록부터 적용된다.

        트리거 블록은 극단성으로 선택된 편향 표본이고, 확정 이후 블록이
        새 국면의 공정한 표본이다.
        """
        est = LossEstimator(p_init=0.005, burst_init=1.0)
        bad = [True] * 10 + [False] * 54
        est.observe_mask(bad)                      # streak 1
        p_before = est.p
        est.observe_mask(bad)                      # streak 2 -> 확정(상승 엣지)
        self.assertTrue(est.jumped)
        # 확정 블록 자체는 보통 알파(0.08)로 반영됐어야 한다
        step = (est.p - p_before) / max(10 / 64 - p_before, 1e-9)
        self.assertLess(step, 0.25, "확정 블록에 부스트가 걸렸다(표본 선택 편향)")
        self.assertEqual(est._boost_left, est.jump_boost_blocks)
        est.observe_mask(bad)                      # 다음 블록은 부스트로 크게 이동
        self.assertEqual(est._boost_left, est.jump_boost_blocks - 1)

    def test_evidence_reset_only_on_rising_edge(self):
        """jumped가 여러 블록 이어져도 증거 리셋은 확정 순간 한 번만."""
        est = LossEstimator(p_init=0.005, burst_init=1.0)
        bad = [True] * 12 + [False] * 52
        for _ in range(2):
            est.observe_mask(bad)                  # 상승 엣지에서 리셋
        obs_after_edge = est._observed
        est.observe_mask(bad)                      # jumped 지속돼도
        self.assertGreater(est._observed, obs_after_edge,
                           "급변 지속 중 새 국면 증거가 계속 지워지고 있다")


# ─────────────────────────────────────────────── D4. 불변식·극한 입력

class TestInvariants(unittest.TestCase):
    """병리적 입력에서도 크래시·보호 붕괴·경계 위반이 없어야 한다."""

    def _assert_decision_bounds(self, d, cfg):
        r_cap = min(int(math.ceil(d.k * cfg.rho_max)), 255 - d.k)
        self.assertGreaterEqual(d.r, 0)
        self.assertLessEqual(d.r, r_cap, f"K={d.k}, r={d.r}가 상한 초과")
        self.assertLessEqual(d.k + d.r, 255)

    def test_survives_total_loss(self):
        """전 블록 손실이 이어져도 추정·결정이 경계 안에 있어야 한다."""
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
        """한 번에 150연속 손실 같은 병리적 버스트에서도 안전해야 한다."""
        cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0)
        ctrl = AdaptiveFecController(cfg)
        ctrl.cong.observe_rtt(40.0)
        ctrl.on_feedback([False] * 25 + [True] * 150 + [False] * 25, rtt_ms=40.0)
        for _ in range(5):
            d = ctrl.next_block()
            self._assert_decision_bounds(d, cfg)
            ctrl.on_feedback([False] * (d.k + d.r), rtt_ms=40.0)

    def test_empty_and_tiny_feedback(self):
        """빈 피드백, 심볼 1개짜리 피드백에서도 죽지 않는다."""
        est = LossEstimator()
        est.observe_mask([])
        est.observe_mask([True])
        est.observe_mask([False])
        self.assertTrue(0.0 <= est.p <= 1.0)
        self.assertGreaterEqual(est.n_eff, 1.0)
        self.assertGreater(est.se, 0.0)

    def test_rate_collapse_keeps_bounds_every_block(self):
        """링크 속도가 급락해 K가 줄어도 매 블록 경계를 지켜야 한다."""
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

    def test_library_footprint_is_pure(self):
        """afec/ 라이브러리는 파일·네트워크·프로세스·스레드를 일절 안 만진다.

        공유 서버에서 돌리기 위한 전제다: 알고리즘 코드는 순수 계산이고,
        파일 쓰기는 튜닝 스크립트가 자기 docs/ 폴더에 하는 것뿐이다.
        OS 수준 격리(run_confined.sh)는 그 위에 얹는 2차 방어선이다.
        여기서 걸리면 격리 전제가 깨진 것이니, 정말 필요해서 추가한
        것이라면 run_confined.sh와 README의 격리 설명도 같이 고칠 것.
        """
        import pathlib
        root = pathlib.Path(__file__).parent / "afec"
        banned = ("open(", "socket", "subprocess", "threading",
                  "multiprocessing", "os.system", "shutil", "os.remove",
                  "os.unlink", "os.rename", "mkdir", "urllib", "Popen")
        for f in sorted(root.glob("*.py")):
            src = f.read_text(encoding="utf-8")
            for tok in banned:
                self.assertNotIn(tok, src,
                                 f"{f.name}: '{tok}' 발견 - 격리 전제 위반")

    def test_cache_bounds_and_eviction(self):
        """캐시: 반출 가중치 경계, 용량 초과 시 축출."""
        c = PathStatsCache(max_entries=32)
        for i in range(300):
            c.store("wifi:AA", f"10.{i % 200}.{i // 200}.1", 0.05, 4.0,
                    500.0, now=float(i))
        self.assertLessEqual(len(c), 32)
        pr = c.lookup("wifi:AA", "10.7.0.1", now=300.0)
        self.assertTrue(0.0 <= pr.weight <= 100.0 + 1e-9)
        c.store("wifi:AA", "10.0.0.1", 0.05, 4.0, 0.0, now=301.0)    # 무증거
        c.store("wifi:AA", "10.0.0.1", 0.05, 4.0, -5.0, now=302.0)   # 음수
        self.assertTrue(0.0 <= c.lookup("wifi:AA", "10.0.0.1",
                                        now=303.0).weight <= 100.0 + 1e-9)


# ─────────────────────────────────────── D5. v0.2.2 핸드셰이크 회복 모델 정밀화

class TestHandshakeRecoveryModel(unittest.TestCase):
    """부분 손실(~2RTT)과 전멸(PTO)의 분리 - 선행연구 대조에서 나온 수정.

    v0.1은 조각 1개 손실도 PTO ~999ms로 쳤는데, Initial 키가 DCID에서
    유도되므로 서버는 생존 조각을 ACK할 수 있고(quicly #639) 회복은
    시간임계 재전송 ~2RTT다. PTO가 맞는 건 플라이트 전멸/ACK 손실뿐.
    """

    def test_ack_partial_false_reduces_to_v01_formula(self):
        """ack_partial=False면 v0.1 공식(전부 PTO)으로 정확히 환원된다."""
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
        """단발 손실 지배 영역(L=1)에서 ACK 경로가 평균을 크게 줄인다."""
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
        """버스트 전멸이 진짜 적이고, 이기려면 패리티+페이싱 결합이 필요하다.

        v0.2.2 정밀화의 핵심 발견: 단발 손실은 2RTT로 회복되므로 초 단위
        정지는 버스트 전멸에서만 나온다. 그런데 K=2 플라이트에 **인접 배치된**
        패리티는 길이 4 버스트가 셋 다 삼키므로 전멸을 거의 못 막는다.
        조각들을 몇 ms 간격으로 페이싱(해석해의 interleave가 모델링)하면
        상관이 끊겨 패리티가 제값을 한다. 실측(p=3%, L=4, RTT 30):
        인접 FEC만 -19%, 페이싱만 -26%, 페이싱+FEC -49% (상승작용).
        """
        single = expected_handshake_ms(2, 5, 0, 0, 0.03, 1.0, 30.0).mean_ms
        bursty = expected_handshake_ms(2, 5, 0, 0, 0.03, 4.0, 30.0).mean_ms
        self.assertGreater(bursty, single * 1.3)     # 버스트가 평균을 키운다
        adj_fec = expected_handshake_ms(2, 5, 1, 2, 0.03, 4.0, 30.0).mean_ms
        self.assertLess(adj_fec, bursty)             # 인접 FEC도 이득은 있으나
        paced_fec = expected_handshake_ms(2, 5, 1, 2, 0.03, 4.0, 30.0,
                                          interleave=4).mean_ms
        self.assertLess(paced_fec, adj_fec * 0.75,   # 페이싱과 결합해야 크다
                        "페이싱+FEC 상승작용이 사라졌다")
        MEASURED["핸드셰이크 버스트 대응 (p=3%,L=4)"] = \
            f"{bursty:.0f}ms -> 인접FEC {adj_fec:.0f} -> 페이싱+FEC {paced_fec:.0f}ms"

    def test_shield_still_protects_split_hello(self):
        """정밀화 후에도 shield는 분할 ClientHello에 이중화를 붙인다."""
        d = shield(profile(768), p_prior=0.02, burst_prior=3.0)
        self.assertGreaterEqual(d.r, 1)
        self.assertLess(d.t_recover_ms, 999.0,
                        "유효 T_recover가 혼합이 아니라 순수 PTO로 남아 있다")

    def test_retry_correlation_toggle_bounds_the_tail(self):
        """재시도 상관 토글: 비관 경계(False)가 낙관 경계(True)보다 무겁다.

        1차 실측 스윕에서 버스트 조건의 평균이 균일 대비 1.8~6배로 나와
        "재시도 시점엔 상관이 끊긴다"(v0.1 가정)가 흔들렸다. 실측 대응이
        확정될 때까지 두 경계를 모두 잴 수 있어야 한다.
        """
        opt = simulate_handshake(2, 5, 0, 0, 0.05, 6.0, 30.0,
                                 trials=4000, seed=9, retry_decorrelate=True)
        pes = simulate_handshake(2, 5, 0, 0, 0.05, 6.0, 30.0,
                                 trials=4000, seed=9, retry_decorrelate=False)
        self.assertGreater(pes.mean_ms, opt.mean_ms,
                           "비관 경계가 낙관 경계보다 가볍다 - 토글이 죽었다")

    def test_rquic_baseline_behaves(self):
        """선행(rQUIC 2019) 임계값 휴리스틱 기준선의 기본 동작."""
        cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0)
        hi = simulate_data("rquic", 0.10, 4.0, 40.0, cfg, n_blocks=200, seed=5)
        lo = simulate_data("rquic", 0.0, 1.0, 40.0, cfg, n_blocks=200, seed=5)
        self.assertGreater(hi.mean_r, lo.mean_r)   # 손실에 반응해 올린다
        self.assertLessEqual(hi.overhead, cfg.rho_max + 0.05)


# ─────────────────────────────────────────────── E. 핸드셰이크

class TestHandshake(unittest.TestCase):

    def test_mlkem_splits_clienthello(self):
        """이 연구의 전제: 실제 브라우저 ClientHello 기준이면 ML-KEM 전 파라미터가
        Initial 패킷 2개 이상으로 쪼개진다 (ch_base=508B, Chrome 실측)."""
        self.assertEqual(profile(None).k_client, 1)
        for level in (512, 768, 1024):
            self.assertGreaterEqual(profile(level).k_client, 2,
                                    f"ML-KEM-{level}이 1패킷에 들어가 버림")

    def test_split_threshold_depends_on_ch_base(self):
        """🩸 2026-08-17 실측이 뒤집은 것: "ML-KEM이면 무조건 쪼개진다"는 거짓이다.

        최소 ClientHello(openssl, ch_base=232B)에서는 ML-KEM-512 단독이
        1032B라 1150B 예산에 들어가 Initial 1개로 끝난다 - 실제 QUIC 캡처에서도
        1개였다. 분할은 ML-KEM 자체가 아니라 (ch_base + 키공유 > 1150)이
        만든다. 이 경계를 검증에 고정해 둔다.
        """
        mini = CH_BASE_MINIMAL_QUIC
        self.assertEqual(profile(512, hybrid=False, ch_base=mini).k_client, 1,
                         "최소 CH에서 ML-KEM-512는 1패킷이어야 한다")
        for level in (768, 1024):
            self.assertGreaterEqual(
                profile(level, hybrid=False, ch_base=mini).k_client, 2)
        # 브라우저 CH로 바꾸면 512도 쪼개진다 - 같은 KEM, 다른 클라이언트
        self.assertEqual(profile(512, hybrid=False,
                                 ch_base=CH_BASE_BROWSER_QUIC).k_client, 2)

    def test_clienthello_bytes_match_real_capture(self):
        """실제 QUIC Initial을 복호화해 잰 ClientHello 바이트와 모델이 일치하는가.

        원자료: experiments/results/e4_quic_clienthello.json
        (openssl s_client -quic -> cloudflare.com / www.google.com, 2026-08-17)
        """
        mini = CH_BASE_MINIMAL_QUIC
        measured = {                       # (level, hybrid) -> 실측 CH wire bytes
            (512, False): 1032,
            (768, False): 1416,
            (1024, False): 1800,
            (768, True): 1448,             # X25519MLKEM768
        }
        for (level, hybrid), want in measured.items():
            got = profile(level, hybrid=hybrid, ch_base=mini).client_flight
            self.assertEqual(got, want,
                             f"ML-KEM-{level} hybrid={hybrid}: 모델 {got} != 실측 {want}")
        MEASURED["ClientHello 모델 vs 실측 (4종)"] = "전부 오차 0 byte"

    def test_serverhello_also_splits_under_mlkem(self):
        """서버 쪽도 실측으로 갈렸다: X25519MLKEM768의 ServerHello는 1210B라
        Initial 예산 1150B를 넘겨 서버의 Initial도 2패킷이 된다."""
        base = profile(None)
        mlkem = profile(768)
        self.assertEqual(base.k_server_initial, 1)
        self.assertGreaterEqual(mlkem.k_server_initial, 2)
        # SH_BASE=90은 x25519(122B)와 X25519MLKEM768(1210B) 양쪽 실측에서 나왔다
        self.assertEqual(base.server_initial_flight, 122)
        self.assertEqual(mlkem.server_initial_flight, 1210)

    def test_from_burst_never_builds_an_invalid_chain(self):
        """🩸 2026-08-18 독립 감사에서 발견한 결함.

        q_gb = p/(L(1-p)) 는 p > L/(1+L) 이면 1을 넘어 전이 '확률'이 아니게
        되고, DP 가 음수 확률과 발산값을 냈다:
            from_burst(0.60, 1.0) -> P_fail(32,8) = 8.195   (확률이 1 초과)
            from_burst(0.90, 1.0) -> P_fail(32,8) = -2.7e34
        p_safe 의 상한이 0.9 라 **도달 가능한 영역**이었고, 「포기 붕괴」 가드는
        P_fail > 0.25 를 보므로 음수일 때 발화하지 않는다(= 최대 r 선택).
        """
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
        """실현 불가능한 (p, L)을 받으면 **손실률을 지키고 버스트를 올린다.**

        손실률이 제어기 결정에 훨씬 크게 작용하므로 p 를 깎으면 안 된다.
        그리고 이건 근사가 아니라 사실이다 - 손실률 90%면 손실은 뭉칠 수밖에 없다
        (정상 구간 평균이 1패킷보다 짧을 수는 없으므로 L >= p/(1-p)).
        """
        from afec.channel import GilbertElliott
        for p, L_req in ((0.9, 1.0), (0.9, 2.0), (0.85, 4.0), (0.6, 1.0)):
            ch = GilbertElliott.from_burst(p, L_req)
            self.assertAlmostEqual(ch.loss_rate, p, places=9)
            self.assertGreaterEqual(ch.mean_burst, L_req - 1e-12)
            self.assertAlmostEqual(ch.mean_burst, max(L_req, p / (1 - p)),
                                   places=9)
        # 실현 가능한 조합은 손도 대지 않는다
        for p, L in ((0.05, 4.0), (0.01, 1.0), (0.2, 2.0)):
            ch = GilbertElliott.from_burst(p, L)
            self.assertAlmostEqual(ch.loss_rate, p, places=12)
            self.assertAlmostEqual(ch.mean_burst, L, places=12)

    def test_invalid_chain_raises_instead_of_returning_garbage(self):
        """생성자를 직접 쓴 무효 사슬은 조용히 쓰레기를 내면 안 된다."""
        from afec.channel import GilbertElliott
        with self.assertRaises(ValueError):
            GilbertElliott(q_gb=1.5, q_bg=0.5).erasure_pmf(8)
        with self.assertRaises(ValueError):
            GilbertElliott(q_gb=0.5, q_bg=-0.1).erasure_pmf(8)

    def test_controller_survives_extreme_estimates(self):
        """추정기가 극단값을 내도 제어기가 정상 범위의 r 을 내야 한다.

        E13 라이브에서 계측기 결함으로 p_hat 이 0.47 까지 갔었다. 그런 입력이
        들어와도 P_fail 이 [0,1] 을 벗어나거나 r 이 상한을 넘으면 안 된다.
        """
        cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0)
        for p in (0.4, 0.47, 0.5, 0.6, 0.75, 0.9):
            for L in (1.0, 2.0, 4.0):
                d = choose_redundancy(32, p, L, 40.0, 0.0, cfg)
                self.assertGreaterEqual(d.r, 0)
                self.assertLessEqual(d.r, 16)      # rho_max=0.5 * k=32
                self.assertGreaterEqual(d.p_fail, 0.0)
                self.assertLessEqual(d.p_fail, 1.0)
                self.assertTrue(math.isfinite(d.cost))

    # ─── 2026-08-18 적대적 감사에서 확인된 결함 8건의 회귀 테스트 ───
    # 감사의 반증 단계가 사용량 한도로 죽어 전부 '미검증 주장'이었고,
    # experiments/e17_verify_audit_claims.py 로 8건 전부 재현한 뒤 고쳤다.

    def test_H2_handshake_r_is_decided_by_cost_not_by_a_borrowed_threshold(self):
        """🩸 H2: shield()가 데이터 구간의 rho_max(0.5)를 써서 K=2 플라이트의
        탐색 후보가 {0,1}로 잘렸다. 이 연구의 논지가 "임계값이 아니라 비용
        최소화"인데 정작 핸드셰이크 r*을 임계값이 정하고 있었다
        (p=5%,L=3: 옛 shield r*=1 J=27.7 vs 자유탐색 r*=7 J=9.1).

        고친 뒤의 요구사항은 두 가지다.
        1) 흔한 구간(버스트 L<=3)에서는 상한이 답을 자르지 않는다.
        2) 상한이 걸릴 때는 **반드시 그 사실이 보고된다**(cap_bound). 캡에
           걸린 값을 '최적'이라고 보고했던 것이 이 결함의 핵심이었다.

        ⚠️ L>=4 에서는 여전히 상한이 걸린다. 이건 버그가 아니라 **모델의
        한계가 드러난 자리**다: 버스트가 길면 r 을 늘려도 플라이트가 통째로
        먹히므로 옳은 지렛대는 이중화가 아니라 **간격 벌리기(페이싱)**인데,
        비용식에 페이싱 항이 없어 J 가 계속 r 을 요구한다. E12 실측에서
        L=8 일 때 패리티 1장이 p99 를 +313% 악화시킨 것과 같은 이야기다.
        """
        cfg = FecConfig(rate_bps=10e6)
        prof = profile(768)
        for p, L in ((0.02, 1.0), (0.05, 1.0), (0.02, 3.0), (0.05, 3.0)):
            d = shield(prof, p, L, cfg)
            self.assertFalse(getattr(d, "cap_bound", False),
                             f"흔한 구간 p={p} L={L}에서 상한이 답을 자른다")
            best = min(d.table, key=lambda t: t[1])
            self.assertEqual(d.r, best[0], "J의 최소가 아니다")
        # 옛 결함의 직접 회귀: 버스트 구간에서 r이 1에 못박히면 안 된다
        self.assertGreater(shield(prof, 0.05, 3.0, cfg).r, 1)
        # 상한이 걸리는 구간에서는 그 사실이 보고돼야 한다
        d_hi = shield(prof, 0.05, 8.0, cfg)
        self.assertTrue(getattr(d_hi, "cap_bound", False),
                        "상한에 걸렸는데 보고되지 않는다")

    def test_H1_server_pto_uses_initial_space_only(self):
        """🩸 H1: 서버 플라이트를 한 블록으로 보면 전멸 확률을 3.4~8배
        과소평가한다. ServerHello(Initial 공간)가 전멸하면 클라이언트는
        Handshake 키를 못 만들어 그 공간 패킷을 복호도 ACK도 못 한다."""
        prof = profile(768)
        self.assertGreaterEqual(prof.k_server_initial, 2)
        self.assertGreater(prof.k_server_handshake, 0)
        for p, L in ((0.02, 2.0), (0.05, 3.0)):
            a = expected_handshake_ms(prof.k_client, prof.k_server, 0, 0,
                                      p, L, 30.0)
            b = expected_handshake_ms(prof.k_client, prof.k_server, 0, 0,
                                      p, L, 30.0,
                                      server_critical=prof.k_server_initial)
            self.assertGreater(b.mean_ms, a.mean_ms,
                               "Initial 공간 기준이면 더 비관적이어야 한다")
        # side='server'는 PTO를 만드는 부분 플라이트를 대상으로 한다
        d = shield(prof, 0.05, 3.0, side="server")
        self.assertEqual(d.k, prof.k_server_initial)

    def test_H10_prior_channel_allows_consecutive_losses(self):
        """🩸 H10: from_burst(p, 1.0)은 q_bg=1이라 연속 손실이 불가능한
        채널이다. 사전값 기본값이 그것이면 전멸 확률이 항상 0이 되어
        핸드셰이크 FEC의 근거인 PTO 항이 통째로 0으로 곱해진다."""
        from afec.channel import GilbertElliott
        for p in (0.01, 0.05, 0.10):
            degenerate = GilbertElliott.from_burst(p, 1.0)
            self.assertEqual(degenerate.erasure_pmf(2)[2], 0.0)
            prior = GilbertElliott.for_prior(p, 1.0)
            self.assertGreater(prior.erasure_pmf(2)[2], 0.0,
                               "사전 채널은 전멸이 가능해야 한다")
            self.assertAlmostEqual(prior.erasure_pmf(2)[2], p * p, places=12)
        # 버스트가 실제로 추정됐으면 GE를 그대로 쓴다
        self.assertAlmostEqual(GilbertElliott.for_prior(0.05, 4.0).mean_burst,
                               4.0, places=9)

    def test_H7_partial_loss_is_never_costlier_than_total_loss(self):
        """🩸 H7: base=pto_ms(srtt)=3*srtt인데 t_fast는 별도 기본값
        2*rtt_prior_ms(=200ms)를 썼다. 캐시가 srtt<66.7ms를 물려주면
        **전멸이 부분 손실보다 싸진다** - fp/ft를 나눈 이유의 정반대."""
        from afec.controller import pto_ms as _pto
        prof = profile(768)
        for srtt in (10.0, 20.0, 30.0, 50.0, 66.0, 100.0, 200.0):
            d = shield(prof, 0.05, 3.0, srtt_ms=srtt)
            base = _pto(srtt)
            # 비용식 안에서 쓰인 t_fast를 되짚는다: r=0의 비용이 f로 나뉜 값
            self.assertLessEqual(2.0 * srtt if srtt is not None else 0.0,
                                 base + 1e-9)
            self.assertGreaterEqual(d.t_recover_ms, 0.0)
            self.assertLessEqual(d.t_recover_ms, base + 1e-9,
                                 f"srtt={srtt}에서 회복 대가가 PTO를 넘는다")

    def test_E2_prior_weight_does_not_change_tracking_inertia(self):
        """🩸 E2: seed_mass = min(prior_weight, 100)이라 100 미만에서
        prior_weight가 EWMA 질량을 바꿨다. 문서화된 불변식("w는 불확실성에만")
        위반이고, 캐시 항목이 낡을수록 추적 속도가 달라졌다."""
        masses = set()
        for w in (100.0, 80.0, 48.0, 25.0, 1.0):
            e = LossEstimator(p_init=0.01, burst_init=4.0, prior_weight=w)
            masses.add(round(e._sent, 9))
            self.assertAlmostEqual(e.p, 0.01, places=12,
                                   msg="사전 점추정은 w와 무관해야 한다")
        self.assertEqual(len(masses), 1,
                         f"EWMA 질량이 prior_weight에 따라 달라진다: {masses}")
        # 같은 관측이면 궤적도 같아야 한다
        traj = {}
        for w in (100.0, 25.0):
            e = LossEstimator(p_init=0.01, burst_init=4.0, prior_weight=w)
            for _ in range(4):
                e.observe_mask([True] * 6 + [False] * 58)
            traj[w] = e.p
        self.assertAlmostEqual(traj[100.0], traj[25.0], places=12)

    def test_E1_unsupported_burst_prior_fades_with_evidence(self):
        """🩸 E1: 캐시된 버스트는 '끝난 손실 구간'이 있는 블록에서만 갱신되므로
        링크가 깨끗해지면 영원히 남아 se 팽창 sqrt(2L(1-p)-1)을 계속 곱했다.
        무손실 300블록 뒤에도 burst 6.0 그대로 -> 깨끗한 링크에서 r=6 vs 2."""
        e = LossEstimator(p_init=0.20, burst_init=6.0, prior_weight=100.0)
        start = e.burst
        for _ in range(300):
            e.observe_mask([False] * 64)
        self.assertLess(e.burst, start - 1.0,
                        "무증거 사전 버스트가 관측이 쌓여도 안 지워진다")
        self.assertLess(e.burst, 1.5)
        # 손실 구간을 실제로 보면 그 추정은 살아 있어야 한다
        e2 = LossEstimator(p_init=0.05, burst_init=4.0, prior_weight=100.0)
        for _ in range(40):
            e2.observe_mask([False] * 20 + [True] * 4 + [False] * 40)
        self.assertGreater(e2.burst, 2.5, "실제 관측된 버스트까지 지우면 안 된다")

    def test_E4_down_cusum_is_not_starved_of_negative_evidence(self):
        """🩸 E4: 상단 급변 검정이 먼저 return True 를 해서 하단 CUSUM 이
        음수 llr(=손실 많은 블록)을 체계적으로 놓쳤다. 양수 기여만 먹고
        음수 기여를 빼먹으니 S 가 위로 표류해 정상 채널에서 허위 급변이 났다.

        ⚠️ '값이 안 변한 블록 수'로 재면 안 된다 - S = max(0, S+llr) 의 바닥
        클램프가 대부분이라 정상 동작까지 잡힌다(실측 122개 전부 클램프).
        재야 할 것은 **정상 채널에서의 허위 급변률**이다.
        """
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
        # 사전값이 정확한 정상 채널에서 연결당 급변 확정이 잦으면 안 된다
        self.assertLess(mean, 4.0,
                        f"정상 채널에서 연결당 {mean:.2f}회 급변 - CUSUM 표류")
        # 그리고 행동으로 직접 증명한다: 상단 검정을 **발화시키는** 블록에서도
        # 하단 CUSUM이 갱신돼야 한다. S를 양수로 올려둔 뒤 손실이 많은 블록을
        # 먹이면, 누적이 살아 있으면 S가 내려가고 건너뛰면 그대로다.
        # (소스 문자열 검사로 하려다 이 결함을 설명하는 **주석 안의**
        #  "return True"를 코드로 착각했다 - 행동 검사가 옳다.)
        e2 = LossEstimator(p_init=0.02, burst_init=1.0, prior_weight=100.0)
        e2._down_llr = 2.0
        before = e2._down_llr
        spike = [True] * 12 + [False] * 52      # 상단 검정이 확실히 걸리는 블록
        self.assertTrue(e2._is_surprising(64, 12), "상단 검정이 안 걸렸다")
        self.assertLess(e2._down_llr, before,
                        "상단이 걸린 블록에서 하단 CUSUM이 갱신되지 않았다")

    def test_C5_export_cap_applies_to_the_default_prior_too(self):
        """🩸 C5: 반출 상한이 _get() 안에서만 걸려 캐시 미스(=콜드 스타트)가
        상한을 우회했다. 상한은 (w,z) 공동 튜닝이 세운 유일한 안전 성질이다."""
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
        """PTO가 1초라 아주 낮은 손실률에서도 이중화가 나와야 한다."""
        d = shield(profile(768), 0.005, 1.0)
        self.assertGreaterEqual(d.r, 1)

    def test_analytic_matches_simulation(self):
        for p in (0.01, 0.05):
            an = expected_handshake_ms(2, 5, 0, 0, p, 3.0, 30.0)
            mc = simulate_handshake(2, 5, 0, 0, p, 3.0, 30.0, trials=40000)
            rel = abs(mc.mean_ms - an.mean_ms) / an.mean_ms
            MEASURED[f"핸드셰이크 해석해 vs MC (p={p:.0%})"] = (
                f"{an.mean_ms:.0f} vs {mc.mean_ms:.0f} ms ({rel:+.0%})")
            # 해석해는 플라이트 간 독립을 가정하므로 약간 비관적이다
            self.assertLess(rel, 0.30)

    def test_fec_reduces_handshake_time(self):
        for p in (0.01, 0.05, 0.10):
            without = expected_handshake_ms(2, 5, 0, 0, p, 3.0, 30.0).mean_ms
            with_fec = expected_handshake_ms(2, 5, 1, 1, p, 3.0, 30.0).mean_ms
            self.assertLess(with_fec, without, f"p={p}에서 FEC가 도움이 안 됨")


# ─────────────────────────────────────────────── F. 통합

class TestEndToEnd(unittest.TestCase):

    def test_real_codec_with_controller(self):
        """진짜 RS 부호기로 인코딩 -> 채널에 흘림 -> 복호. 원본이 나와야 한다.

        지금까지 시뮬레이터는 '소실 <= r이면 복구'라고 세고만 있었다.
        여기서는 실제 바이트를 복원해서 대조한다.
        """
        cfg = FecConfig(rate_bps=50e6, delay_budget_ms=5.0, k_max=16)
        ctrl = AdaptiveFecController(cfg)
        ctrl.cong.observe_rtt(40.0)
        rng = random.Random(77)
        sampler = ChannelSampler(GilbertElliott.from_burst(0.06, 3.0), rng)

        sym_size = 48
        decoded_ok = decode_failed = 0

        for _ in range(120):
            d = ctrl.next_block()
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
        self.assertGreater(decoded_ok, 0)

    def test_adaptive_beats_static_in_worst_case(self):
        """이 연구의 핵심 주장: 손실률을 모를 때 최악이 낫다."""
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
        """손실이 없으면 이중화를 거의 안 써야 한다."""
        cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0)
        r = simulate_data("adaptive", 0.0, 1.0, 40.0, cfg)
        MEASURED["무손실 링크 오버헤드"] = f"{r.overhead:.1%}"
        self.assertLess(r.overhead, 0.05)


# ─────────────────────────────────────────────── 부호화 속도 측정

def benchmark_codec():
    """부호화 속도 -> FecConfig.cpu_cost_ms_per_symbol 에 넣을 값."""
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
