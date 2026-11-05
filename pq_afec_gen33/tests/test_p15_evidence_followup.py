"""P15 raw evidence and byte comparison windows; no actual communication."""
import ast
from collections import Counter
import contextlib
import io
import json
from pathlib import Path
import re
from types import SimpleNamespace
import unittest

PATH = Path(__file__).resolve().parents[1] / 'experiments/p15_v2policy.py'

def functions(names, **ns):
    tree = ast.parse(PATH.read_text(encoding='utf-8'))
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert {n.name for n in funcs} == set(names)
    exec(compile(ast.Module(body=funcs, type_ignores=[]), str(PATH), 'exec'), ns)
    return ns

class ByteWindowTests(unittest.TestCase):
    def setUp(self):
        self.ns = functions({'mean', 'added_bytes', 'window_added_bytes', 'round_evidence'},
                            Counter=Counter, K=1)

    def test_equal_round_window_differs_from_final_or_pooled(self):
        blocks = [{'round': 1, 'client_rows': [{'first_flight_bytes': 1281, 'first_flight_parity_bytes': 0}]},
                  {'round': 2, 'client_rows': [{'first_flight_bytes': 1380, 'first_flight_parity_bytes': 0}] * 10},
                  {'round': 3, 'client_rows': [{'first_flight_bytes': 1480, 'first_flight_parity_bytes': 0}]}]
        self.assertEqual(self.ns['window_added_bytes'](blocks, [2, 3]), 150.0)
        self.assertEqual(self.ns['window_added_bytes'](blocks, [3]), 200.0)

    def test_absent_old_rows_or_missing_byte_field_remains_unknown(self):
        for block in ({'round': 1}, {'round': 1, 'client_rows': []},
                      {'round': 1, 'client_rows': [{'first_flight_bytes': 1281}]}):
            self.assertIsNone(self.ns['window_added_bytes']([block], [1]))
        self.assertIsNone(self.ns['window_added_bytes']([], [1]))

    def test_joint_choice_cannot_be_inferred_from_two_marginal_modes(self):
        a = [{'ok': True, 'ips_used': 1281, 'm_used': 0},
             {'ok': True, 'ips_used': 1280, 'm_used': 1}]
        b = [{'ok': True, 'ips_used': 1281, 'm_used': 1},
             {'ok': True, 'ips_used': 1280, 'm_used': 0}]
        ra, rb = [self.ns['round_evidence'](rows, {}, 2) for rows in (a, b)]
        self.assertNotEqual(ra['joint_ips_m'], rb['joint_ips_m'])
        self.assertEqual(ra['client_rows'], a)

class CollectorTests(unittest.TestCase):
    def collect(self, failed=False):
        clock = iter(range(1000))
        fixed = [('m0', 'off', 0, 0), ('m1', 'on', 1, 0),
                 ('m2', 'on', 2, 0), ('pad', 'off', 0, 1281)]
        def client(group, n, **kwargs):
            rows = [{'ok': True, 'ms': 50.0, 'ips_used': kwargs.get('ips', 1280),
                     'm_used': kwargs.get('m', 1), 'm_why': 'p=0.01',
                     'k': 1, 'ack_rtt_ms': 25.0,
                     'first_flight_bytes': 1280, 'first_flight_parity_bytes': 0} for _ in range(n)]
            if failed and kwargs['fec'] == 'auto':
                rows[-1].update(ok=False, error='timeout')
            return rows, {'tag': 'all client statistics'}, ''
        bed = SimpleNamespace(set_netem=lambda *a, **k: None,
                              start_server=lambda *a, **k: ('process', 'path'),
                              run_client=client, stop_server=lambda *a: None,
                              read_server_stats=lambda *a: {'recovered': 3, 'recover_crc_fail': 0},
                              pctl=lambda v, q: v[0] if v else None)
        journal = SimpleNamespace(has=lambda key: False, run_id='unit-test',
                                  fingerprint='test-fingerprint', recorded=[])
        journal.record = lambda key, val: journal.recorded.append((key, val))
        ns = functions({'run_condition', 'round_evidence', 'added_bytes', 'mean'},
                       Counter=Counter, K=1, N=10, FIXED=fixed, ROUNDS_ORDER=['auto']+[x[0] for x in fixed],
                       CACHE='unused', RTT_MS=50.0, GROUP='x25519', UPLINK_MBPS=0.0,
                       PE=SimpleNamespace(PROTOCOL='test'), B=bed, re=re,
                       time=SimpleNamespace(time_ns=lambda: next(clock)),
                       os=SimpleNamespace(unlink=lambda path: None),
                       cache_evidence=lambda path: {'available': True, 'value': {'obs': 1}})
        with contextlib.redirect_stdout(io.StringIO()):
            arms, auto = ns['run_condition'](4032, 0, 10, journal)
        return arms, auto, journal

    def test_complete_collector_preserves_raw_joint_choices_cache_and_condition_server(self):
        arms, auto, journal = self.collect()
        self.assertEqual(len(journal.recorded), 1)
        self.assertEqual(auto['server_stats']['recovered'], 3)
        self.assertEqual(len(auto['rounds']), 10)
        for block in auto['rounds']:
            self.assertEqual(len(block['client_rows']), block['n_req'])
            self.assertEqual(block['collection_provenance']['run_id'], 'unit-test')
            self.assertEqual(block['cache_after']['value'], {'obs': 1})
        self.assertEqual(arms['pad']['blocks'][0]['client_stats']['tag'], 'all client statistics')

    def test_failed_returned_trials_are_retained_but_not_journaled_as_complete(self):
        arms, auto, journal = self.collect(failed=True)
        self.assertFalse(journal.recorded)
        self.assertEqual(auto['rounds'][0]['n_failed'], 1)
        self.assertEqual(auto['rounds'][0]['client_rows'][-1]['error'], 'timeout')

if __name__ == '__main__':
    unittest.main()
