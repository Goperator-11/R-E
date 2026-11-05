import unittest

from experiments.v33 import validate_j7_v2 as check


class J7IndependentValidatorTests(unittest.TestCase):
    def run_for(self, seed, action, cid="c"):
        return {"seed": seed, "n": 10, "action_counts": [{"context_id": cid, "action": action, "n": 10}]}

    def test_independent_error_bound_preserves_common_mc_error(self):
        a, b = (0, 0, 1), (0, 0, 2)
        tables = {("c", a): {"mean_gap_ms": -1, "gap_half_width_ms": 0.2, "uncertainty_resolved": True},
                  ("c", b): {"mean_gap_ms": 0, "gap_half_width_ms": 0.3, "uncertainty_resolved": True}}
        result = check.independent_difference([self.run_for(s, a) for s in range(20)],
                                              [self.run_for(s, b) for s in range(20)], tables)
        self.assertEqual(result["mc"], 0.5)
        self.assertEqual(result["adjusted_upper"], -0.5)
        self.assertEqual(result["status"], "pass")

    def test_unresolved_term_prevents_passing(self):
        a, b = (0, 0, 1), (0, 0, 2)
        tables = {("c", a): {"mean_gap_ms": -10, "gap_half_width_ms": None, "uncertainty_resolved": False},
                  ("c", b): {"mean_gap_ms": 0, "gap_half_width_ms": 0, "uncertainty_resolved": True}}
        ca, ba = ([self.run_for(s, action) for s in range(20)] for action in (a, b))
        result = check.independent_difference(ca, ba, tables)
        self.assertEqual(result["status"], "inconclusive")
        self.assertIsNone(result["adjusted_upper"])
        same = check.independent_difference(ca, ca, tables)
        self.assertEqual(same["mc"], 0)

    def test_wrong_context_or_seed_pairing_rejected(self):
        action = (0, 0, 1)
        ca = [self.run_for(s, action) for s in range(20)]
        for ba in ([self.run_for(s, action, "other") for s in range(20)],
                   [self.run_for(s, action) for s in range(1, 21)]):
            with self.assertRaises(ValueError):
                check.independent_difference(ca, ba, {})

    def test_numeric_and_type_corruption_rejected(self):
        for actual, expected in ((1.01, 1), (float("nan"), 1), (True, 1), (None, 0), (0, None)):
            with self.subTest(actual=actual, expected=expected), self.assertRaises(ValueError):
                check.close(actual, expected, "mutation")
        check.close(1 + 1e-12, 1, "numerical tolerance")
        check.close(None, None, "unresolved")

    def test_student_interval_has_seed_uncertainty(self):
        mean, low, high = check.paired(list(range(20)))
        self.assertEqual(mean, 9.5)
        self.assertLess(low, mean)
        self.assertGreater(high, mean)
        with self.assertRaises(ValueError):
            check.check_summary({"n": 20, "mean": mean, "lower": mean, "upper": mean}, list(range(20)), "erased uncertainty")


if __name__ == "__main__":
    unittest.main()
