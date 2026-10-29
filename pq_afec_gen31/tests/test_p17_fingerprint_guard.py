"""Prevent a live run from consuming a forced historical journal generation."""
import contextlib
import io
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
with patch.object(os, "makedirs"):
    import p17_adaptive_value as P


class StopBeforeJournal(Exception):
    pass


class FingerprintGuardTests(unittest.TestCase):
    def test_live_override_rejected_before_any_measurement_setup(self):
        with patch.object(P, "FP_OVERRIDE", "historical"), patch.object(P, "DRYRUN", False), \
                patch.object(P.B, "harden") as harden, \
                patch.object(P.B, "require_root") as require_root, \
                patch.object(P.B, "setup") as setup, patch.object(P, "Journal") as journal, \
                contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(P.main(), 2)
            self.assertIn("only with PADFEC_P17_DRYRUN=1", error.getvalue())
            harden.assert_not_called()
            require_root.assert_not_called()
            setup.assert_not_called()
            journal.assert_not_called()

    def test_dryrun_can_read_historical_generation_without_network_setup(self):
        with patch.object(P, "FP_OVERRIDE", "historical"), patch.object(P, "DRYRUN", True), \
                patch.object(P.B, "harden"), patch.object(P.B, "require_root") as require_root, \
                patch.object(P.B, "setup") as setup, patch.object(P, "code_fingerprint") as fingerprint, \
                patch.object(P, "Journal", side_effect=StopBeforeJournal) as journal, \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(StopBeforeJournal):
                P.main()
            self.assertEqual(journal.call_args.args[1], "historical")
            require_root.assert_not_called()
            setup.assert_not_called()
            fingerprint.assert_not_called()

    def test_live_run_derives_fingerprint_from_current_source(self):
        with patch.object(P, "FP_OVERRIDE", None), patch.object(P, "DRYRUN", False), \
                patch.object(P.B, "harden"), patch.object(P.B, "require_root"), \
                patch.object(P.B, "setup"), \
                patch.object(P, "code_fingerprint", return_value="current") as fingerprint, \
                patch.object(P, "Journal", side_effect=StopBeforeJournal) as journal:
            with self.assertRaises(StopBeforeJournal):
                P.main()
            self.assertEqual(journal.call_args.args[1], "current")
            fingerprint.assert_called_once()
            self.assertEqual(fingerprint.call_args.args[1], P.ROOT)


if __name__ == "__main__":
    unittest.main()
