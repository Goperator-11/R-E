import contextlib
import io
import json
import math
from pathlib import Path
import statistics
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT))
import p4_model as P4
import p10_completeness as P10


def trials(n, success=True):
    return [{"i": i, "ok": success, "ms": 50.0} for i in range(n)]


SERVER = {"recover_crc_fail": 0, "recovered": 1,
          "bytes_to_stack": 1, "bytes_in": 2}


class SampleGuidanceTests(unittest.TestCase):
    def test_actual_alpha_and_ceiling(self):
        result = P4.sample_size_advisory([0, 2], [1, 3], 1, .005)
        self.assertAlmostEqual(result["normal_critical_value"], 2.807033768343811)
        self.assertEqual(result["n_per_arm"], 32)
        uncorrected = P4.sample_size_advisory([0, 2], [1, 3], 1, .05)
        self.assertEqual(uncorrected["n_per_arm"], 16)
        self.assertEqual(result["status"], "approximation_only")

    def test_unequal_current_counts_plan_equal_future_counts(self):
        first, second = [0, 2], [0, 1, 2, 3]
        z = statistics.NormalDist().inv_cdf(1 - .005 / 2)
        expected = math.ceil(z * z * (statistics.variance(first)
                                     + statistics.variance(second)))
        result = P4.sample_size_advisory(first, second, 1, .005)
        self.assertEqual(result["n_per_arm"], expected)
        self.assertEqual(result["current_success_n"], [2, 4])

    def test_environment_floor_blocks_sample_only_recommendation(self):
        result = P4.sample_size_advisory([0, 2], [1, 3], 1, .005, 1.1)
        self.assertIsNone(result["n_per_arm"])
        self.assertEqual(result["statistical_only_n_per_arm"], 32)
        self.assertEqual(result["status"], "below_environment_floor")

    def test_no_finite_recommendation_from_no_gap_or_bad_data(self):
        cases = [([0, 2], [1, 3], 0, "zero_or_negative_gap"),
                 ([0, 2], [1], 1, "insufficient_samples"),
                 ([1, 1], [2, 2], 1, "zero_observed_variance"),
                 ([0, math.nan], [1, 3], 1, "invalid_samples"),
                 ([0, 2], [1, 3], math.inf, "invalid_gap")]
        for first, second, gap, status in cases:
            with self.subTest(status=status):
                result = P4.sample_size_advisory(first, second, gap, .005)
                self.assertIsNone(result["n_per_arm"])
                self.assertEqual(result["status"], status)
                json.dumps(result, allow_nan=False)

    def test_invalid_alpha_and_floor_rejected(self):
        for alpha in (0, 1, -1, math.nan, math.inf):
            with self.subTest(alpha=alpha), self.assertRaises(ValueError):
                P4.sample_size_advisory([0, 2], [1, 3], 1, alpha)
        with self.assertRaises(ValueError):
            P4.sample_size_advisory([0, 2], [1, 3], 1, .005, -1)

    def test_tiny_positive_gap_does_not_crash(self):
        result = P4.sample_size_advisory([0, 2], [1, 3], 5e-324, .005)
        self.assertEqual(result["status"], "unbounded_estimate")
        self.assertIsNone(result["n_per_arm"])


class InventoryTests(unittest.TestCase):
    def test_source_implementation_is_not_runtime_validation(self):
        with contextlib.redirect_stdout(io.StringIO()):
            records = P10.inventory([])
        closed, high_m = records[0], records[-1]
        self.assertTrue(closed["ok"])
        self.assertTrue(high_m["ok"])
        for item in (closed, high_m):
            self.assertEqual(item["implementation_status"], "source_present")
            self.assertEqual(item["validation_status"], "not_assessed_by_inventory")
            self.assertTrue(item["validation_stages"])
            self.assertEqual(len(item["source_sha256"]["qamp.go"]), 64)
        self.assertEqual(records[1]["implementation_status"], "out_of_scope")

    def test_policy_word_in_comments_is_not_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            qbed = Path(tmp) / "quicbed"
            qbed.mkdir()
            for name in ("qamp.go", "policy.go", "pfail_table.go"):
                (qbed / name).write_text(
                    '// policy newDestCache(cachePath) cache.decide( cache.observe(\n'
                    '/* if mode == "auto" { func (c *destCache) decide( */\n',
                    encoding="utf-8")
            with patch.object(P10, "HERE", tmp), contextlib.redirect_stdout(io.StringIO()):
                records = P10.inventory([])
        self.assertFalse(records[0]["ok"])
        self.assertFalse(records[-1]["ok"])


class MeasurementIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def mock_bed(self, server_stats=None):
        for name, value in (("set_netem", None), ("require_bin", "fake-qamp"),
                            ("start_server", (Mock(poll=Mock(return_value=None)), "stats")),
                            ("stop_server", None),
                            ("read_server_stats", SERVER if server_stats is None else server_stats)):
            patcher = patch.object(P10.B, name, return_value=value)
            self.addCleanup(patcher.stop)
            patcher.start()

    def test_rejects_empty_duplicate_nonfinite_and_failed_process(self):
        cases = [([], ""), (trials(2), "exit 1"),
                 ([{"i": 0, "ok": True, "ms": math.nan}, trials(1)[0]], ""),
                 ([trials(1)[0], trials(1)[0]], "")]
        for rows, error in cases:
            with self.subTest(rows=rows, error=error), self.assertRaises(ValueError):
                P10.validate_client_rows(rows, 2, error)
        P10.validate_client_rows(trials(2, False), 2)

    def test_concurrent_empty_processes_do_not_pass(self):
        self.mock_bed()
        with patch.object(P10.subprocess, "run", return_value=Mock(
                stdout="", returncode=0)):
            checks = []
            P10.c1_concurrent(checks)
        self.assertFalse(checks[0]["ok"])

    def test_concurrent_missing_stats_do_not_pass(self):
        self.mock_bed(server_stats={})
        data = "\n".join(json.dumps(row) for row in trials(60))
        with patch.object(P10.subprocess, "run", return_value=Mock(
                stdout=data, returncode=0)):
            checks = []
            P10.c1_concurrent(checks)
        self.assertFalse(checks[0]["ok"])

    def test_concurrent_complete_run_can_pass(self):
        self.mock_bed()
        data = "\n".join(json.dumps(row) for row in trials(60))
        with patch.object(P10.subprocess, "run", return_value=Mock(
                stdout=data, returncode=0)):
            checks = []
            P10.c1_concurrent(checks)
        self.assertTrue(checks[0]["ok"])

    def test_failed_rtt_baseline_cannot_be_zero_overhead(self):
        self.mock_bed()
        with patch.object(P10.B, "run_client", side_effect=lambda _group, n, **kw:
                          (trials(n, False), {}, "")):
            checks = []
            data = P10.c2_rtt(checks)
        overhead_checks = [check for check in checks if "오버헤드" in check["check"]]
        self.assertEqual(len(overhead_checks), 3)
        self.assertTrue(all(not check["ok"] for check in overhead_checks))
        self.assertTrue(all(row["overhead_ms"] is None for row in data))

    def test_invalid_run_always_stops_server(self):
        self.mock_bed()
        with patch.object(P10.B, "run_client", return_value=([], {}, "timeout")):
            with self.assertRaises(ValueError):
                P10.c2_rtt([])
        P10.B.stop_server.assert_called_once()

    def test_highloss_and_longrun_require_crc_stats(self):
        self.mock_bed(server_stats={})
        with patch.object(P10.B, "run_client", side_effect=lambda _group, n, **kw:
                          (trials(n), {}, "")):
            checks = []
            P10.c3_highloss(checks)
            P10.c5_longrun(checks)
        self.assertTrue(all(not check["ok"] for check in checks))

    def test_malformed_packet_test_requires_stats(self):
        self.mock_bed(server_stats={})
        with patch.object(P10.B, "run_client", return_value=(trials(30), {}, "")), \
                patch.object(P10.socket, "socket"), patch.object(P10.time, "sleep"):
            checks = []
            P10.c4_malformed(checks)
        self.assertFalse(checks[0]["ok"])

    def test_complete_other_scenarios_keep_existing_thresholds(self):
        self.mock_bed()
        with patch.object(P10.B, "run_client", side_effect=lambda _group, n, **kw:
                          (trials(n), {}, "")), \
                patch.object(P10.socket, "socket"), patch.object(P10.time, "sleep"):
            checks = []
            P10.c2_rtt(checks)
            P10.c3_highloss(checks)
            P10.c4_malformed(checks)
            P10.c5_longrun(checks)
        self.assertEqual(len(checks), 12)
        self.assertTrue(all(check["ok"] for check in checks))


if __name__ == "__main__":
    unittest.main()
