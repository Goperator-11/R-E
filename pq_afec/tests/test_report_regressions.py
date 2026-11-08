import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'experiments'))
import p6_report as report


class ReportRegressions(unittest.TestCase):
    def test_failed_pdf_render_preserves_existing_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'report.pdf'
            original = b'%PDF-1.4\nprevious valid report\n%%EOF'
            target.write_bytes(original)
            result = subprocess.CompletedProcess([], 1, '', 'renderer error')
            with patch.object(report.subprocess, 'run', return_value=result):
                self.assertFalse(report.render_pdf('browser', '<p>x</p>', str(target)))
            self.assertEqual(target.read_bytes(), original)

    def test_zero_exit_without_pdf_is_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'report.pdf'
            result = subprocess.CompletedProcess([], 0, '', '')
            with patch.object(report.subprocess, 'run', return_value=result), \
                 patch.object(report.time, 'monotonic', side_effect=[0, 61]):
                self.assertFalse(report.render_pdf('browser', '<p>x</p>', str(target)))
            self.assertFalse(target.exists())

    def test_successful_render_replaces_old_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'report.pdf'
            target.write_bytes(b'old')
            valid = b'%PDF-1.4\nnew content\n%%EOF'
            def fake_run(args, **kwargs):
                path = next(a.split('=', 1)[1] for a in args if a.startswith('--print-to-pdf='))
                Path(path).write_bytes(valid)
                self.assertTrue(any(a.startswith('--user-data-dir=') for a in args))
                return subprocess.CompletedProcess(args, 0, '', '')
            with patch.object(report.subprocess, 'run', side_effect=fake_run):
                self.assertTrue(report.render_pdf('browser', '<p>x</p>', str(target)))
            self.assertEqual(target.read_bytes(), valid)

    def test_missing_inputs_do_not_create_a_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / 'empty'
            result_dir.mkdir()
            output_dir = Path(tmp) / 'out'
            with patch.object(report, 'RESULTS', report.RESULTS):
                rc = report.main(['--results-dir', str(result_dir), '--output-dir', str(output_dir), '--no-pdf'])
            self.assertEqual(rc, 2)
            self.assertFalse(output_dir.exists())

    def test_manifest_records_hash_and_missing_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'p1_flight.json'
            p.write_text('{}', encoding='utf-8')
            with patch.object(report, 'RESULTS', tmp):
                manifest = report.source_manifest()
            row = next(r for r in manifest['sources'] if r['file'] == p.name)
            self.assertTrue(row['exists'])
            self.assertEqual(len(row['sha256']), 64)
            self.assertFalse(row['current_code_validated'])
            missing = next(r for r in manifest['sources'] if r['file'] == 'p2_threshold.json')
            self.assertFalse(missing['exists'])


if __name__ == '__main__':
    unittest.main()
