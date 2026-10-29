"""Report late-stage status without hiding failures behind stale counters."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'experiments'))
import p6_report as R


class LateStageReportTests(unittest.TestCase):
    def test_stale_pass_counter_cannot_hide_failed_checks(self):
        text = R.late_stage_summary({'p17_adaptive_value.json': {
            'passed': 10, 'total': 10,
            'checks': [{'check': 'coverage', 'ok': True},
                       {'check': 'adaptation', 'ok': False, 'detail': '40.3% | below threshold'}]}})
        self.assertIn('1/2', text)
        self.assertIn('adaptation', text)
        self.assertIn('40.3%', text)
        self.assertNotIn('10/10', text)

    def test_missing_and_unknown_checks_are_not_counted_as_passes(self):
        text = R.late_stage_summary({'missing.json': None, 'empty.json': {},
                                    'unknown.json': {'checks': [{'check': 'unknown', 'ok': None}]}})
        self.assertIn('missing.json', text)
        self.assertIn('empty.json', text)
        self.assertIn('0/1', text)

    def test_pdf_status_contains_failure_and_escapes_raw_data(self):
        text = R.late_stage_html({'p17.json': {'checks': [
            {'ok': False, 'check': 'adaptation', 'detail': '<script>failure</script>'}]}})
        self.assertIn('0/1', text)
        self.assertIn('adaptation', text)
        self.assertIn('&lt;script&gt;', text)
        self.assertNotIn('<script>', text)

    def test_diagnostics_are_visible_without_inflating_pass_counts(self):
        text = R.late_stage_summary({'p20_residual.json': {
            'checks': [{'ok': False, 'check': 'sample sufficiency', 'detail': '18 short'}],
            'diagnostics': [{'check': 'mass residuals', 'detail': '66/234 outside'}]}})
        self.assertIn('0/1', text)
        self.assertIn('66/234 outside', text)
        self.assertIn('mass residuals', text)
        self.assertNotIn('1/2', text)


if __name__ == '__main__':
    unittest.main()
