import math
import unittest

from padfec3 import layout as baseline
from experiments.v33 import hold_layout
from experiments.v33.hold_decoder import HoldConfig


class HoldLayoutTests(unittest.TestCase):
    def test_first_flight_failure_matches_binomial_for_every_action(self):
        for k in range(1, 5):
            for m in range(5):
                for lead in range(m + 1):
                    for p in (0.0, 0.02, 0.15, 1.0):
                        with self.subTest(k=k, m=m, lead=lead, p=p):
                            rows = list(hold_layout.outcomes(k, m, lead, 1280, p, 2))
                            self.assertAlmostEqual(sum(r["pr"] for r in rows), 1, places=12)
                            fail = sum(r["pr"] for r in rows if r["kind"] != "ok")
                            expected = sum(math.comb(k+m, n) * (1-p)**n * p**(k+m-n) for n in range(k))
                            self.assertAlmostEqual(fail, expected, places=12)
                            for r in rows:
                                if r["kind"] == "ok":
                                    self.assertAlmostEqual(sum(weight for weight, _ in r["branches"]), 1, places=12)
                                    self.assertLessEqual(r["base_credit"], r["phys_at_dec"])

    def test_zero_parity_preserves_baseline_cost(self):
        for k in range(1, 5):
            for p in (0, 0.02, 0.15, 1):
                with self.subTest(k=k, p=p):
                    original = baseline.evaluate(k, 1280, 0, 0, p, 50, 2, 13)
                    actual = hold_layout.evaluate(k, 1280, 0, 0, p, 50, 2, 13)
                    for key in ("J", "p_one_rtt", "p_two_rtt", "p_fail", "client_bytes"):
                        self.assertAlmostEqual(actual[key], original[key], places=10)

    def test_used_parity_overhead_is_removed_from_credit(self):
        rows = list(hold_layout.outcomes(2, 4, 3, 1280, 0.15, 2))
        row = next(r for r in rows if r["pattern"] == (1, 1, 1, 1, 0, 0))
        self.assertEqual(row["decoder"]["used"], [0])
        self.assertEqual(row["base_credit"], 2*1280 + 2*1331)
        self.assertEqual(row["decoder"]["consumed_overhead"], 51)
        self.assertEqual(row["t_dec"], (3*1331 + 2*1280 + 1331) * 0.004 + 1)

    def test_deadline_uses_missing_tail_slots(self):
        rows = list(hold_layout.outcomes(2, 2, 2, 1280, 0.15, 2))
        row = next(r for r in rows if r["pattern"] == (1, 1, 0, 0))
        self.assertEqual(row["t_dec"], (2*1331 + 2*1280) * 0.004 + 1)
        self.assertGreater(row["t_dec"], max(t for t in row["arrival_ms"] if t is not None) + 1)

    def test_loss_location_is_explicit_and_affects_timing(self):
        before = {r["pattern"]: r for r in hold_layout.outcomes(2, 2, 2, 1280, 0.15, 2)}
        after = {r["pattern"]: r for r in hold_layout.outcomes(2, 2, 2, 1280, 0.15, 2, loss_placement="after_link")}
        pattern = (0, 1, 1, 0)
        self.assertAlmostEqual(after[pattern]["t_dec"] - before[pattern]["t_dec"], 1331 * 0.004)
        self.assertEqual(before[pattern]["decoder"]["used"], after[pattern]["decoder"]["used"])

    def test_receiver_rate_and_invalid_probability_are_rejected(self):
        for p in (True, -1, float("nan"), 1.1):
            with self.subTest(p=p), self.assertRaises(ValueError):
                list(hold_layout.outcomes(2, 2, 1, 1280, p, 2))
        with self.assertRaises(ValueError):
            list(hold_layout.outcomes(2, 2, 1, 1280, 0.15, 2, config=HoldConfig(uplink_kbps=5000)))


if __name__ == "__main__":
    unittest.main()
