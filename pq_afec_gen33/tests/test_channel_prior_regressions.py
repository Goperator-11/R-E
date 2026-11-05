import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from afec.channel import GilbertElliott
from afec.controller import FecConfig, choose_redundancy
from afec.estimator import LossEstimator


class ChannelPriorRegression(unittest.TestCase):
    def test_cached_unknown_burst_matches_independent_loss_distribution(self):
        for p in (0.01, 0.05, 0.2):
            for burst in (1.0, 1.01):
                with self.subTest(p=p, burst=burst):
                    actual = GilbertElliott.cached(p, burst).erasure_pmf(8)
                    expected = [math.comb(8, e) * p**e * (1-p)**(8-e)
                                for e in range(9)]
                    for got, want in zip(actual, expected):
                        self.assertAlmostEqual(got, want, places=13)

    def test_controller_default_burst_uses_binomial_cost_minimum(self):
        p, k, recovery_ms = 0.05, 8, 100.0
        cfg = FecConfig(rate_bps=10_000_000)
        decision = choose_redundancy(k, p, 1.0, recovery_ms, cfg=cfg)
        reference = []
        for r in range(math.ceil(k * cfg.rho_max) + 1):
            n = k + r
            fail = sum(math.comb(n, e) * p**e * (1-p)**(n-e)
                       for e in range(r + 1, n + 1))
            cost = r * cfg.symbol_bytes * 8 / cfg.rate_bps * 1000
            reference.append(cost + recovery_ms * fail)
        optimum = min(range(len(reference)), key=reference.__getitem__)
        self.assertEqual(decision.r, optimum)
        self.assertAlmostEqual(decision.cost, reference[optimum], places=13)

    def test_estimator_default_burst_uses_binomial_likelihood_ratio(self):
        p, n = 0.05, 8
        estimator = LossEstimator(p_init=p)
        estimator._is_surprising(n, 0)
        expected = n * (math.log1p(-p / 2) - math.log1p(-p))
        self.assertAlmostEqual(estimator._down_llr, expected, places=13)

    def test_cached_observed_burst_preserves_markov_distribution(self):
        for p, burst in ((0.05, 3.0), (0.2, 5.0)):
            with self.subTest(p=p, burst=burst):
                actual = GilbertElliott.cached(p, burst).erasure_pmf(8)
                expected = GilbertElliott.from_burst(p, burst).erasure_pmf(8)
                self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
