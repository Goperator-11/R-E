import ast
import datetime as dt
from pathlib import Path
from types import SimpleNamespace
import unittest

PATH = Path(__file__).resolve().parents[1] / 'experiments/p12_quantum.py'
tree = ast.parse(PATH.read_text(encoding='utf-8'))

def functions(names, **ns):
    exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names],
                           type_ignores=[]), str(PATH), 'exec'), ns)
    return ns

class UnitProvenanceTests(unittest.TestCase):
    def test_old_unit_keeps_stored_p50_and_origin_without_inventing_missing_raw_rows(self):
        old = {'n': 12, 'ok': 12, 'p50': 51.234}
        provenance = {'units': [{'key': 'old', 'reused': True, 'run_id': 'old-run', 'recorded_at': 'old-time'}]}
        jr = SimpleNamespace(get=lambda key: old, provenance=lambda: provenance)
        ns = functions({'consumed_units'})
        out = ns['consumed_units'](jr)
        self.assertEqual(out['probe_units'][0]['result']['p50'], 51.234)
        self.assertTrue(out['journal_provenance']['units'][0]['reused'])
        self.assertNotIn('client_rows', out['probe_units'][0]['result'])

    def test_new_failed_probe_retains_raw_rows_and_is_not_cached_as_valid(self):
        rows = [{'ok': True, 'ms': 50}, {'ok': False, 'error': 'timeout', 'ms': 5000}]
        bed = SimpleNamespace(start_server=lambda *a, **k: ('process', 'path'),
                              run_client=lambda *a, **k: (rows, {'first_flight_bytes': 1280}, ''),
                              stop_server=lambda *a: None,
                              read_server_stats=lambda *a: {'recover_crc_fail': 0},
                              summarize=lambda *a, **k: {'n': 2, 'ok': 1, 'p50': 50, 'two_rtt_rate': 0})
        jr = SimpleNamespace(has=lambda key: False, run_id='new', fingerprint='new-fp', recorded=[])
        jr.record = lambda key, rec: jr.recorded.append(rec)
        ns = functions({'probe'}, B=bed, dt=dt, RTT_MS=50.0)
        out = ns['probe']('x25519', 1280, 2000, 1, 2, jr)
        self.assertFalse(out['valid'])
        self.assertEqual((out['n_req'], out['n_failed'], out['n_missing']), (2, 1, 0))
        self.assertEqual(out['client_rows'], rows)
        self.assertEqual(out['collection_provenance']['run_id'], 'new')
        self.assertFalse(jr.recorded)
        jr.provenance = lambda: {'units': []}
        published = functions({'consumed_units'})['consumed_units'](jr)
        self.assertEqual(published['failed_probe_units'][0]['result'], out)
        self.assertFalse(published['failed_probe_units'][0]['journaled'])

    def test_failed_upper_search_bound_survives_when_threshold_ref_is_lower_bound(self):
        calls = iter([([{'ok': True, 'ms': 50}], {}, ''),
                      ([{'ok': False, 'ms': 5000, 'error': 'timeout'}], {}, 'timeout')])
        bed = SimpleNamespace(start_server=lambda *a, **k: ('process', 'path'),
                              run_client=lambda *a, **k: next(calls), stop_server=lambda *a: None,
                              read_server_stats=lambda *a: {'recover_crc_fail': 0},
                              summarize=lambda rows, **kw: {'n': len(rows),
                                  'ok': sum(bool(x.get('ok')) for x in rows),
                                  'p50': 50 if rows[0]['ok'] else None, 'two_rtt_rate': 0})
        saved = {}
        jr = SimpleNamespace(has=lambda key: key in saved, get=lambda key: saved[key],
                             run_id='new', fingerprint='fp',
                             record=lambda key, rec: saved.__setitem__(key, rec),
                             provenance=lambda: {'units': [{'key': k} for k in saved]})
        ns = functions({'probe', 'bisect_threshold', 'consumed_units'}, B=bed, dt=dt,
                       RTT_MS=50, LO=2000, HI=4000, RESOLUTION=56, N_PROBE=1,
                       P2=SimpleNamespace(is_two_rtt=lambda r: False if r['valid'] else None),
                       log=lambda *a: None)
        threshold = ns['bisect_threshold']('x25519', 1280, 1, jr)
        self.assertTrue(threshold['ref']['valid'])
        self.assertIsNone(threshold['lo'])
        published = ns['consumed_units'](jr)
        self.assertEqual(published['failed_probe_units'][0]['result']['cert'], 4000)
        self.assertEqual(published['failed_probe_units'][0]['result']['error'], 'timeout')
        self.assertEqual(published['failed_probe_units'][0]['result']['client_rows'][0]['error'], 'timeout')

if __name__ == '__main__':
    unittest.main()
