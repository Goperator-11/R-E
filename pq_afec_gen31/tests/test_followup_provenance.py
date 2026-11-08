import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'experiments'))
import p19_provenance as P


def fixture():
    return {'rows': [{'cond': 'test', 'protocol': {'version': 2, 'cycles': 1,
                                                 'schedule': [[2, 3]],
                                                 'arms': [['auto', 'auto', 0]]},
                     'arms': {'auto': {'n': 2, 'mean': 15, 'p50': 10, 'ms': [10, 20]}},
                     'segments': [{'arm': 'auto', 'cycle': 0, 'loss': 2,
                                   'n_expected': 3, 'n': 3, 'ok': 2,
                                   'failed': 1, 'mean': 15, 'trial_records': [
                                       {'i': 0, 'ok': True, 'ms': 10, 'm_used': 1},
                                       {'i': 1, 'ok': False, 'ms': 10000, 'm_used': 2},
                                       {'i': 2, 'ok': True, 'ms': 20, 'm_used': 1}]}]}]}


class TrialProvenanceTests(unittest.TestCase):
    def test_failed_attempt_is_counted_but_not_in_success_latency(self):
        data = fixture()
        self.assertEqual(P.missing_raw(data, 'p17_adaptive_value.json'), [])
        self.assertTrue(all(P.close(a, b) for _, a, b in P.check_p17(data)))

    def test_edited_segment_summary_is_detected(self):
        data = fixture()
        data['rows'][0]['segments'][0]['ok'] = 3
        mismatches = [k for k, a, b in P.check_p17(data) if not P.close(a, b)]
        self.assertIn('test|segment0.ok', mismatches)

    def test_aggregate_raw_cannot_disagree_with_trial_rows(self):
        data = fixture()
        data['rows'][0]['arms']['auto'].update(ms=[15, 15], p50=15)
        self.assertTrue(any(k.endswith('trial_sample_mismatches') and not P.close(a, b)
                            for k, a, b in P.check_p17(data)))

    def test_duplicate_missing_or_nonfinite_trials_are_rejected(self):
        for mutation in ('duplicate', 'missing', 'nan', 'bool_id'):
            with self.subTest(mutation=mutation):
                data = fixture()
                rows = data['rows'][0]['segments'][0]['trial_records']
                if mutation == 'duplicate':
                    rows[2]['i'] = 0
                elif mutation == 'missing':
                    rows.pop()
                elif mutation == 'nan':
                    rows[0]['ms'] = float('nan')
                else:
                    rows[0]['i'] = False
                self.assertTrue(P.missing_raw(data, 'p17_adaptive_value.json'))

    def test_legacy_file_retains_legacy_checks_without_fabricating_trials(self):
        data = fixture()
        del data['rows'][0]['protocol']
        del data['rows'][0]['segments']
        saved = copy.deepcopy(data)
        self.assertEqual(P.check_p17(data), P.check_nested_arms(data))
        self.assertEqual(saved, data)

    def test_whole_segment_omission_and_duplicate_are_rejected(self):
        for mutation in ('omission', 'duplicate', 'shortened_plan'):
            with self.subTest(mutation=mutation):
                data = fixture()
                rec = data['rows'][0]
                if mutation == 'omission':
                    rec['protocol']['cycles'] = 2
                elif mutation == 'duplicate':
                    rec['segments'].append(copy.deepcopy(rec['segments'][0]))
                else:
                    rec['protocol']['schedule'] = [[2, 4]]
                self.assertTrue(P.missing_raw(data, 'p17_adaptive_value.json'))


if __name__ == '__main__':
    unittest.main()
