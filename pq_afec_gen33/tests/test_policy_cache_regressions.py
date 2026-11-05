import itertools
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from padfec import policy


class PolicyCacheRegression(unittest.TestCase):
    def setUp(self):
        policy.expected_rounds.cache_clear()

    def tearDown(self):
        policy.expected_rounds.cache_clear()

    def test_cached_recovery_rounds_equal_uncached_calculation(self):
        for args in itertools.product((1, 2, 4), (0, 1, 3),
                                      (0.0, 0.05, 0.3), (1.0, 3.0, 5.0)):
            with self.subTest(args=args):
                expected = policy.expected_rounds.__wrapped__(*args)
                self.assertEqual(policy.expected_rounds(*args), expected)
                self.assertEqual(policy.expected_rounds(*args), expected)

    def test_repeat_reuses_result_and_each_input_selects_its_own_entry(self):
        args = (2, 1, 0.05, 3.0)
        first = policy.expected_rounds(*args)
        self.assertEqual(policy.expected_rounds(*args), first)
        for changed in ((1, 1, 0.05, 3.0), (2, 3, 0.05, 3.0),
                        (2, 1, 0.15, 3.0), (2, 1, 0.05, 1.0)):
            self.assertEqual(policy.expected_rounds(*changed),
                             policy.expected_rounds.__wrapped__(*changed))
        stats = policy.expected_rounds.cache_info()
        self.assertEqual(stats.hits, 1)
        self.assertEqual(stats.misses, 5)
        self.assertEqual(stats.maxsize, 512)


if __name__ == "__main__":
    unittest.main()
