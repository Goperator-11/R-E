import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock


spec = importlib.util.spec_from_file_location("l2_joint_driver", (Path(__file__).resolve().parents[1] / "g3/v33/validation/L2_final_analysis_v1/runs/l2_joint_driver_v1.py"))
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


class JointDriverTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name)
        replacements = {"ROOT": root, "RUNS": root, "WRAPPER": root / "wrapper.py",
                        "COLLECTION": root / "collection.json", "PREVIOUS": root / "previous.json",
                        "DESIGN": root / "design.md", "FAMILY": root / "family.json", "POOL": root / "pool",
                        "REPORT": root / "report.json", "MARKDOWN": root / "report.md"}
        for key in ("WRAPPER", "COLLECTION", "PREVIOUS", "DESIGN"):
            replacements[key].write_text(key, encoding="utf-8")
        replacements["WRAPPER_SHA"] = driver.sha(replacements["WRAPPER"])
        replacements["BOUND"] = {str(replacements[key]): driver.sha(replacements[key]) for key in ("COLLECTION", "PREVIOUS", "DESIGN")}
        patch = mock.patch.multiple(driver, **replacements)
        patch.start()
        self.addCleanup(patch.stop)

    def process(self, command, **kwargs):
        kwargs["stdout"].write(b"complete\n")
        command_name = command[4]
        if command_name == "freeze-family":
            driver.save(driver.FAMILY, {"frozen": True})
        elif command_name == "run":
            self.assertIn("--loop", command)
            self.assertNotIn("--resume", command)
            self.assertEqual(command[command.index("--workers") + 1], "8")
            driver.POOL.mkdir()
        else:
            driver.save(driver.REPORT, {"complete": True})
            driver.save(Path(str(driver.REPORT) + ".published.json"), {"complete": True})
            driver.MARKDOWN.write_text("report", encoding="utf-8")
        return types.SimpleNamespace(returncode=0)

    def test_all_phases_bind_preceding_complete_receipts(self):
        with mock.patch.object(driver.subprocess, "run", side_effect=self.process):
            for phase in ("plan", "run", "report"):
                self.assertEqual(driver.main([phase]), 0)
                value = driver.read(driver.RUNS / ("L2_joint_" + phase + "_v1.finished.json"))
                self.assertEqual(value["status"], "complete")
                self.assertEqual(value["driver_sha256"], value["driver_sha256_after"])
        final = driver.read(driver.RUNS / "L2_joint_report_v1.finished.json")
        self.assertEqual(final["preceding_run"], driver.phase_identity("run"))
        self.assertEqual(len(final["published_outputs_sha256"]), 3)

    def test_failed_run_is_preserved_and_report_refused(self):
        with mock.patch.object(driver.subprocess, "run", side_effect=self.process):
            driver.main(["plan"])
        with mock.patch.object(driver.subprocess, "run", return_value=types.SimpleNamespace(returncode=2)):
            self.assertEqual(driver.main(["run"]), 1)
        with self.assertRaisesRegex(ValueError, "did not complete"):
            driver.main(["report"])
        self.assertFalse(driver.REPORT.exists())

    def test_source_change_during_phase_prevents_complete(self):
        def changed(command, **kwargs):
            result = self.process(command, **kwargs)
            driver.WRAPPER.write_text("changed", encoding="utf-8")
            return result
        with mock.patch.object(driver.subprocess, "run", side_effect=changed):
            self.assertEqual(driver.main(["plan"]), 1)
        value = driver.read(driver.RUNS / "L2_joint_plan_v1.finished.json")
        self.assertEqual(value["status"], "post_validation_failed")
        self.assertTrue(driver.FAMILY.exists())

    def test_changed_plan_log_or_start_receipt_is_rejected(self):
        with mock.patch.object(driver.subprocess, "run", side_effect=self.process):
            driver.main(["plan"])
        for target in (driver.FAMILY, driver.RUNS / "L2_joint_plan_v1.stdout.txt", driver.RUNS / "L2_joint_plan_v1.started.json"):
            original = target.read_bytes()
            target.write_bytes(original + b" ")
            with self.subTest(target=target.name), self.assertRaises(ValueError):
                driver.phase_identity("plan")
            target.write_bytes(original)

    def test_duplicate_phase_and_existing_pool_are_refused(self):
        with mock.patch.object(driver.subprocess, "run", side_effect=self.process):
            driver.main(["plan"])
        with self.assertRaisesRegex(ValueError, "must be new"):
            driver.main(["plan"])
        driver.POOL.mkdir()
        with self.assertRaisesRegex(ValueError, "pool must be new"):
            driver.main(["run"])


if __name__ == "__main__":
    unittest.main()
