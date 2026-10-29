"""Offline checks for provenance across interrupted/resumed collections."""
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments"))
import _journal as J


class JournalProvenanceTests(unittest.TestCase):
    def test_old_record_has_unknown_time_and_is_not_new_measurement(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "units.jsonl"
            path.write_text(json.dumps({"fp": "same", "key": "old", "val": 42}) + "\n")
            journal = J.Journal(str(path), "same")
            self.assertEqual(journal.provenance()["used_units"], 0)
            self.assertEqual(journal.get("old"), 42)
            info = journal.provenance()
            self.assertEqual(info["reused_units"], 1)
            self.assertEqual(info["unknown_recording_time_units"], 1)
            self.assertIsNone(info["units"][0]["recorded_at"])

    def test_resumed_result_identifies_both_runs_without_redating_units(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "units.jsonl")
            first = J.Journal(path, "same")
            first.record("a", [1, 2])
            stamp = first.provenance()["units"][0]["recorded_at"]
            self.assertIsNotNone(datetime.fromisoformat(stamp).tzinfo)
            resumed = J.Journal(path, "same")
            resumed.get("a")
            resumed.record("b", [3])
            info = resumed.provenance()
            self.assertEqual((info["used_units"], info["reused_units"]), (2, 1))
            self.assertEqual(info["units"][0]["recorded_at"], stamp)
            self.assertNotEqual(info["units"][0]["run_id"], info["units"][1]["run_id"])

    def test_incompatible_fingerprint_and_unused_records_are_not_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "units.jsonl")
            old = J.Journal(path, "old")
            old.record("a", 1)
            current = J.Journal(path, "current")
            current.record("b", 2)
            loaded = J.Journal(path, "current")
            self.assertIsNone(loaded.get("a"))
            self.assertEqual(loaded.provenance()["used_units"], 0)
            self.assertEqual(loaded.items(), {"b": 2})
            self.assertEqual([u["key"] for u in loaded.provenance()["units"]], ["b"])
            with self.assertRaises(KeyError):
                loaded.provenance(["a"])

    def test_failed_flush_does_not_publish_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = J.Journal(str(Path(directory) / "units.jsonl"), "same")
            with patch.object(J.os, "fsync", side_effect=OSError("disk")):
                with self.assertRaises(OSError):
                    journal.record("failed", 1)
            self.assertEqual(journal.provenance()["used_units"], 0)

    def test_reset_clears_values_and_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = J.Journal(str(Path(directory) / "units.jsonl"), "same")
            journal.record("a", 1)
            journal.reset()
            self.assertEqual(journal.items(), {})
            self.assertEqual(journal.provenance()["used_units"], 0)


if __name__ == "__main__":
    unittest.main()
