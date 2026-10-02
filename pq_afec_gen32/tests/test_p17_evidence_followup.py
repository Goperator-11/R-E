"""Oracle rounding, conditional adaptation lag and actual telemetry denominators."""
import ast
import math
from pathlib import Path
import statistics
from types import SimpleNamespace
import unittest

PATH = Path(__file__).resolve().parents[1] / 'experiments/p17_adaptive_value.py'

def functions(names, **ns):
    tree = ast.parse(PATH.read_text(encoding='utf-8'))
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert {n.name for n in funcs} == set(names)
    exec(compile(ast.Module(body=funcs, type_ignores=[]), str(PATH), 'exec'), ns)
    return ns

class EvidenceTests(unittest.TestCase):
    def test_sub_millisecond_candidate_means_are_not_rounded_before_oracle_selection(self):
        ns = functions({'allowed_by_loss', 'fixed_arm_names', 'block_means', 'paired_ci',
                        'oracle_gain', 'mean'},
                       ARMS=[('m0', 'off', 0), ('m1', 'on', 1), ('auto', 'auto', 1)],
                       SCHEDULE=[(2.0, 20), (15.0, 20)], TOL_MS=1.0, math=math,
                       BST=SimpleNamespace(t_crit=lambda df, alpha: 2.0))
        segments = [{'arm': arm, 'cycle': cyc, 'loss': loss, 'mean': value}
                    for cyc in range(2) for loss in (2.0, 15.0)
                    for arm, value in [('m0', 1.0004), ('m1', 1.0001)]]
        rec = {'segments': segments}
        alw = ns['allowed_by_loss'](rec)
        self.assertEqual(alw[2.0]['means']['m0'], 1.0004)
        self.assertEqual(alw[2.0]['means_display_ms']['m0'], 1.0)
        gain, half, labels = ns['oracle_gain'](rec, alw)
        self.assertEqual(labels['fixed_best'], 'm1')
        self.assertEqual((gain, half), (0.0, 0.0))

    def test_actual_k_and_current_rtt_denominators_do_not_filter_flush_hint_mismatches(self):
        ns = functions({'trial_inventory'}, math=math)
        rows = [{'first_flight_datagrams': 1, 'path_rtt_valid': False, 'path_rtt_ms': 0, 'ok': True},
                {'first_flight_datagrams': 2, 'path_rtt_valid': True, 'path_rtt_ms': 200, 'ok': True},
                {'first_flight_datagrams': 2, 'path_rtt_valid': True, 'path_rtt_ms': float('nan'), 'ok': False}]
        got = ns['trial_inventory']({'segments': [{'n_expected': 4, 'trial_records': rows}]})
        self.assertEqual(got['actual_k_counts'], {'1': 1, '2': 2})
        self.assertEqual((got['n_records'], got['n_missing_records']), (3, 1))
        self.assertEqual((got['current_ack_rtt_valid'], got['current_ack_rtt_missing_or_invalid']), (1, 2))

    def test_adapted_median_is_explicitly_conditional_and_never_segments_keep_denominator(self):
        ns = functions({'adapt_stats'},
                       SCHEDULE=[(2.0, 12)], ARMS=[('m1', 'on', 1)],
                       statistics=statistics, optimal_m=lambda *a: 1,
                       trial_timeline=lambda s: (s['choices'], 'all_attempts'))
        got = ns['adapt_stats']({'segments': [{'arm': 'auto', 'loss': 2.0, 'choices': [1] * 12},
                                             {'arm': 'auto', 'loss': 2.0, 'choices': [0] * 12}]},
                               0.0, {2.0: {'allowed': ['m1']}})[2.0]
        self.assertEqual((got['lag_med'], got['adapted_segments'], got['total_segments'], got['never_adapted']),
                         (0, 1, 2, 1))
        self.assertIn('conditional', got['lag_median_scope'])

if __name__ == '__main__':
    unittest.main()
