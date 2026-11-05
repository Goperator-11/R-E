import unittest
from experiments.v33 import validate_m1_fixed as check


class M1FixedIndependentTests(unittest.TestCase):
    def test_extremal_bounds_need_not_use_the_point_winner(self):
        result = check.design_minimum([
            dict(action=[0, 3, 1], mean_hct_ms=100., half_width_ms=10.),
            dict(action=[0, 4, 0], mean_hct_ms=101., half_width_ms=1.)])
        self.assertEqual(result["action"], [0, 3, 1])
        self.assertEqual((result["lower_ms"], result["upper_ms"]), (90., 102.))

    def test_unknown_width_on_loser_cannot_be_discarded(self):
        result = check.design_minimum([
            dict(action=[0, 3, 1], mean_hct_ms=100., half_width_ms=1.),
            dict(action=[0, 4, 0], mean_hct_ms=200., half_width_ms=None)])
        self.assertIsNone(result["lower_ms"])
        self.assertIsNone(result["upper_ms"])

    def test_quantile_implementations_agree_in_frozen_family(self):
        from statistics import NormalDist
        from scipy.stats import norm
        check.compare(float(norm.isf(.01 / (4 * 277))), NormalDist().inv_cdf(1 - .01 / (4 * 277)))

    def test_unknown_boolean_and_nonfinite_values_are_rejected(self):
        for actual, expected in ((0, False), (None, 0.), (True, 1), (float("nan"), 0.), (float("inf"), 0.)):
            with self.subTest(actual=actual, expected=expected):
                with self.assertRaises(ValueError):
                    check.compare(actual, expected)


if __name__ == "__main__":
    unittest.main()
