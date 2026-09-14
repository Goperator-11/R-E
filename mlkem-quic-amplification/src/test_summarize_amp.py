import unittest
from summarize_amp import summarize


class SummaryTests(unittest.TestCase):
    @staticmethod
    def row(i, hct, status='ok'):
        return dict(iter=str(i), hct_ms=str(hct), sent_pkts='1', sent_bytes='1280', recv_pkts='2', recv_bytes='1970', status=status)

    def test_even_median_interpolates(self):
        self.assertEqual(summarize([self.row(i, x) for i, x in enumerate([10, 20, 30, 40])], 4)[0], 25)

    def test_all_timeouts_leave_latency_blank(self):
        self.assertEqual(summarize([self.row(0, '', 'timeout')], 1), [''] * 5 + [0, 1, 1])

    def test_failures_do_not_dilute_successful_means(self):
        result = summarize([self.row(0, 12), self.row(1, '', 'fail')], 2)
        self.assertEqual(result, [12, 1, 1280, 2, 1970, 1, 1, 0])

    def test_missing_row_rejected(self):
        with self.assertRaises(ValueError):
            summarize([], 1)

    def test_duplicate_iteration_rejected(self):
        with self.assertRaises(ValueError):
            summarize([self.row(0, 10), self.row(0, 20)], 2)

    def test_nonfinite_success_rejected(self):
        with self.assertRaises(ValueError):
            summarize([self.row(0, 'nan')], 1)


if __name__ == '__main__':
    unittest.main()
