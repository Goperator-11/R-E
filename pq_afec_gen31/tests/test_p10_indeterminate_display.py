import ast
import contextlib
import io
from pathlib import Path
import sys
import unittest

PATH = Path(__file__).resolve().parents[1] / 'experiments/p10_completeness.py'
tree = ast.parse(PATH.read_text(encoding='utf-8'))
ns = {'sys': sys}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'add'],
                        type_ignores=[]), str(PATH), 'exec'), ns)

class IndeterminateDisplayTests(unittest.TestCase):
    def test_precision_failure_and_unresolved_effect_remain_distinct(self):
        records, output = [], io.StringIO()
        with contextlib.redirect_stdout(output):
            ns['add'](records, 'resolution', False, '2.344 < 3 * 0.893')
            ns['add'](records, 'effect', True, 'effect unresolved', kind='판정불능')
        self.assertFalse(records[0]['ok'])
        self.assertTrue(records[0]['gating'])
        self.assertIsNone(records[1]['ok'])
        self.assertFalse(records[1]['gating'])
        self.assertEqual(records[1]['status'], 'indeterminate')
        self.assertIn('[판정불능]', output.getvalue())
        self.assertNotIn('[통과]', output.getvalue())
        tests = [r for r in records if r['kind'] == '시험']
        self.assertEqual((sum(bool(r['ok']) for r in tests), len(tests)), (0, 1))

    def test_resolved_success_still_counts_as_original_test(self):
        records = []
        with contextlib.redirect_stdout(io.StringIO()):
            ns['add'](records, 'complete', True, 'all successful')
        self.assertTrue(records[0]['ok'])
        self.assertTrue(records[0]['gating'])

    def test_unresolved_detail_is_not_truncated(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            ns['add']([], 'effect', True, 'x' * 100 + 'missing resolution', kind='판정불능')
        self.assertIn('missing resolution', output.getvalue())

if __name__ == '__main__':
    unittest.main()
