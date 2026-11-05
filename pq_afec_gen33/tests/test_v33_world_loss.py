import itertools
import math
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.v33 import validate_loss as validation
from experiments.v33 import worldsim


class WorldLossTests(unittest.TestCase):
    def test_valid_ge_parameters_preserve_stationary_loss_and_mean_bad_run(self):
        for p, length in ((0.02, 3.0), (0.15, 3.0), (0.30, 3.0), (0.8, 4.0)):
            with self.subTest(p=p, length=length):
                entry, recovery = worldsim.ge_parameters(p, length)
                self.assertGreaterEqual(entry, 0.0)
                self.assertLessEqual(entry, 1.0)
                self.assertAlmostEqual(entry / (entry + recovery), p, delta=1e-12)
                self.assertAlmostEqual(1.0 / recovery, length, delta=1e-12)

    def test_markov_pattern_probabilities_and_block_recovery_match_independent_methods(self):
        for case in validation.default_cases():
            with self.subTest(case=case.name):
                reference = validation.reference_enumeration(case)
                forward = validation.reference_forward(case)
                world = validation.world_enumeration(case, worldsim)
                self.assertAlmostEqual(reference["probability_sum"], 1.0, delta=1e-12)
                for actual in (forward, world):
                    self.assertAlmostEqual(actual["probability_sum"], 1.0, delta=1e-12)
                    self.assertAlmostEqual(actual["p_fail"], reference["p_fail"], delta=1e-12)

    def test_iid_boundary_matches_binomial_rs_failure_and_lead_does_not_protect(self):
        for p in (0.02, 0.15, 0.30):
            for k, lead, trailing in ((1, 2, 1), (2, 0, 4), (2, 3, 1), (3, 1, 3)):
                with self.subTest(p=p, k=k, lead=lead, trailing=trailing):
                    case = validation.LossCase("iid", k, lead, trailing, p, 1.0 / (1.0 - p))
                    n = k + trailing
                    expected = math.fsum(math.comb(n, delivered) * (1 - p) ** delivered * p ** (n - delivered) for delivered in range(k))
                    actual = validation.world_enumeration(case, worldsim)
                    self.assertAlmostEqual(actual["p_fail"], expected, delta=1e-12)

    def test_burst_length_one_does_not_equal_iid(self):
        p = 0.15
        self.assertEqual(worldsim.pattern_probability((False, False), p, loss_model="ge", burst_length=1.0), 0.0)
        self.assertAlmostEqual(worldsim.pattern_probability((False, False), p, loss_model="iid"), p * p)

    def test_buffered_lead_symbols_recover_and_credit_only_symbols_do_not(self):
        pattern = (True, True, True, False, False, False)
        credit = worldsim.first_flight_outcome(pattern, 2, 3, 1, lead_mode="credit_only")
        buffered = worldsim.first_flight_outcome(pattern, 2, 3, 1, lead_mode="buffered")
        self.assertFalse(credit["success"])
        self.assertTrue(buffered["success"])
        for bits in itertools.product((False, True), repeat=6):
            credit = worldsim.first_flight_outcome(bits, 2, 3, 1, lead_mode="credit_only")
            buffered = worldsim.first_flight_outcome(bits, 2, 3, 1, lead_mode="buffered")
            self.assertFalse(credit["success"] and not buffered["success"])

    def test_invalid_stationary_transition_parameters_are_rejected(self):
        for p, length in ((-0.01, 3), (1.01, 3), (math.nan, 3), (0.15, 0), (0.15, 0.9), (0.15, math.inf), (0.8, 3), (True, 3)):
            with self.subTest(p=p, length=length):
                with self.assertRaises((TypeError, ValueError)):
                    worldsim.ge_parameters(p, length)

    def test_deterministic_endpoints_and_seed_replay(self):
        for p in (0.0, 1.0):
            for connection in (0, 1, 17):
                pattern = worldsim.sample_loss_pattern(6, p, loss_model="ge", burst_length=3.0, seed=531000, connection=connection)
                self.assertEqual(tuple(pattern), (p == 0.0,) * 6)
        first = worldsim.sample_loss_pattern(100, 0.15, loss_model="ge", burst_length=3.0, seed=531000, connection=19)
        replay = worldsim.sample_loss_pattern(100, 0.15, loss_model="ge", burst_length=3.0, seed=531000, connection=19)
        self.assertEqual(tuple(first), tuple(replay))


if __name__ == "__main__":
    unittest.main()
