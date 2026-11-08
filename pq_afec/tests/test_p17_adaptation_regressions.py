import contextlib
import importlib.util
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
spec = importlib.util.spec_from_file_location("p17_audit", ROOT / "experiments" / "p17_adaptive_value.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)


def trials(choices, failed=()):
    return [{"i": i, "m_used": m, "ok": i not in failed, "ms": 100.0,
             "m_why": "fixture"} for i, m in enumerate(choices)]


def segment(rows, expected=None):
    return {"cycle": 0, "loss": 2.0, "arm": "auto", "pos": 0,
            "n": len(rows), "n_expected": expected or len(rows),
            "ok": sum(r["ok"] for r in rows), "mean": 100.0,
            "m_used": [r["m_used"] for r in rows], "trial_records": rows}


class AdaptationTimelineTests(unittest.TestCase):
    def stats(self, s):
        with mock.patch.object(P, "SCHEDULE", [(2.0, s["n_expected"])]), \
                mock.patch.object(P, "optimal_m", return_value=1):
            return P.adapt_stats({"segments": [s]}, 2.0,
                                 {2.0: {"allowed": ["m1"], "best": "m1"}})[2.0]

    def test_failed_trial_action_breaks_consecutive_hits(self):
        s = segment(trials([1] * 5 + [0] + [1] * 5, failed={5}))
        got = self.stats(s)
        self.assertEqual(got["n"], 11)
        self.assertAlmostEqual(got["hit_rate"], 10 / 11)
        self.assertEqual(got["lags"], [None])
        self.assertEqual(got["never_adapted"], 1)

    def test_failed_trial_with_allowed_action_counts_as_choice_hit(self):
        got = self.stats(segment(trials([1] * 10, failed={3})))
        self.assertEqual(got["n"], 10)
        self.assertEqual(got["hit_rate"], 1.0)
        self.assertEqual(got["lags"], [0])

    def test_missing_trial_preserves_original_lag(self):
        rows = trials([0] + [1] * 10)[1:]
        got = self.stats(segment(rows, expected=11))
        self.assertEqual(got["lags"], [1])
        self.assertEqual(got["n"], 11)
        self.assertEqual(got["unknown_choices"], 1)
        self.assertFalse(got["timeline_complete"])

    def test_duplicate_or_invalid_id_cannot_fill_missing_attempt(self):
        for bad in (0, -1, True, 99):
            rows = trials([1] * 10)
            rows[-1]["i"] = bad
            choices, scope = P.trial_timeline(segment(rows))
            self.assertEqual(scope, "incomplete_trial_records")
            self.assertIsNone(choices[9])

    def test_legacy_failures_cannot_restore_original_indices(self):
        s = {"n": 11, "ok": 10, "m_used": [1] * 10}
        timeline, scope = P.trial_timeline(s)
        self.assertEqual(timeline, [None] * 11)
        self.assertEqual(scope, "legacy_missing_trial_indices")
        s["n"] = 10
        self.assertEqual(P.trial_timeline(s), ([1] * 10, "legacy_all_success"))

    def test_valid_rows_are_ordered_by_trial_id(self):
        s = segment(list(reversed(trials([0] + [1] * 10))))
        self.assertEqual(self.stats(s)["lags"], [1])

    def test_even_number_of_adapted_segments_uses_middle_pair(self):
        a = segment(trials([1] * 14))
        b = segment(trials([0] * 4 + [1] * 10))
        b["cycle"] = 1
        with mock.patch.object(P, "SCHEDULE", [(2.0, 14)]), \
                mock.patch.object(P, "optimal_m", return_value=1):
            got = P.adapt_stats({"segments": [a, b]}, 2.0,
                                {2.0: {"allowed": ["m1"], "best": "m1"}})[2.0]
        self.assertEqual(got["lags"], [0, 4])
        self.assertEqual(got["lag_med"], 2)


class CollectionTests(unittest.TestCase):
    def run_collection(self, rows):
        jr = mock.Mock()
        jr.has.return_value = False
        with mock.patch.multiple(P, N=12, CYCLES=1, SCHEDULE=[(2.0, 12)],
                                 ARMS=[("auto", "auto", 1)], DRYRUN=False), \
                mock.patch.object(P.os, "unlink"), \
                mock.patch.object(P, "cache_snapshot", return_value={"sha256": "fixture"}), \
                mock.patch.object(P.B, "start_server", return_value=(object(), "stats")), \
                mock.patch.object(P.B, "stop_server"), \
                mock.patch.object(P.B, "set_netem"), \
                mock.patch.object(P.B, "run_client", return_value=(rows, {"cpu_list": "test"}, "")), \
                mock.patch.object(P.B, "read_server_stats", return_value={"recover_crc_fail": 0}), \
                contextlib.redirect_stdout(io.StringIO()):
            rec = P.run_interleaved("fixture", 2, 2, 9000, 50, jr)
        return rec, jr

    def test_collection_saves_failure_action_and_protocol(self):
        rows = trials([1] * 12, failed={5})
        rec, jr = self.run_collection(rows)
        s = rec["segments"][0]
        self.assertEqual(s["trial_records"], rows)
        self.assertEqual(s["m_used"], [1] * 12)
        self.assertEqual((s["n_expected"], s["ok"], s["failed"]), (12, 11, 1))
        self.assertEqual(rec["protocol"]["choice_scope"], "all_attempts")
        self.assertEqual(s["cache_before"]["sha256"], "fixture")
        self.assertIn("+00:00", s["started_at"])
        jr.record.assert_called_once()

    def test_duplicate_missing_or_invalid_trial_is_not_journaled(self):
        for kind in ("duplicate", "missing", "bad_ms", "bad_ok"):
            rows = trials([1] * 12)
            if kind == "duplicate":
                rows[-1]["i"] = 0
            elif kind == "missing":
                rows.pop()
            elif kind == "bad_ms":
                rows[-1]["ms"] = float("nan")
            else:
                rows[-1]["ok"] = 1
            with self.subTest(kind=kind):
                _rec, jr = self.run_collection(rows)
                jr.record.assert_not_called()


if __name__ == "__main__":
    unittest.main()
