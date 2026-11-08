import pytest
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))
import loop2 as L
import p19_provenance as P19


class ContentProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "experiments/results").mkdir(parents=True)
        for name in ("loop2.py", "_journal.py", "stage.py"):
            (self.root / "experiments" / name).write_text("value = 1\n", encoding="utf-8")
        self.context = {"python": "test-python", "executable": "test-python",
                        "platform": "test-platform", "machine": "test-machine",
                        "cpu_count": 4, "affinity": None,
                        "padfec_env": {"PADFEC_P3_N": "1200"}}
        self.patches = [patch.object(L, "ROOT", str(self.root)),
                        patch.object(L, "runtime_context", lambda: copy.deepcopy(self.context))]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.stage = L.Stage("p3", "test", "win", ["python", "stage.py"],
                             ["experiments/results/p3_effect.json"], ["experiments/stage.py"])
        self.output = self.root / self.stage.outputs[0]

    def record(self, success=True):
        provenance = self.stage.provenance()
        before = self.stage.observe_outputs()
        started = time.time_ns()
        self.output.write_text('{"runs": []}', encoding="utf-8")
        return {"status": "done" if success else "failed",
                "fingerprint": L.fingerprint_from_provenance(provenance),
                "provenance": provenance,
                "result_provenance": L.result_provenance(self.stage, before, started, True),
                "output_hashes": self.stage.output_hashes() if success else {}}

    def verify(self, record):
        return P19.verify_recorded_result(self.stage, record, str(self.output))

    def test_rewritten_identical_source_is_verified_even_with_newer_mtime(self):
        record = self.record()
        source = self.root / "experiments/stage.py"
        source.write_bytes(source.read_bytes())
        os.utime(source, ns=(time.time_ns(), time.time_ns() + 10_000_000_000))
        self.assertEqual(self.verify(record)["status"], "verified")

    def test_source_change_with_preserved_size_and_mtime_is_rejected(self):
        record = self.record()
        source = self.root / "experiments/stage.py"
        old = source.stat()
        source.write_text("value = 2\n", encoding="utf-8")
        os.utime(source, ns=(old.st_atime_ns, old.st_mtime_ns))
        self.assertEqual(self.verify(record)["status"], "mismatch")

    def test_output_change_with_preserved_size_and_mtime_is_rejected(self):
        record = self.record()
        old = self.output.stat()
        self.output.write_text('{"runs": {}}', encoding="utf-8")
        os.utime(self.output, ns=(old.st_atime_ns, old.st_mtime_ns))
        self.assertEqual(self.verify(record)["status"], "mismatch")

    def test_environment_must_match_including_precision(self):
        record = self.record()
        self.context["padfec_env"]["PADFEC_P3_N"] = "8"
        self.assertEqual(self.verify(record)["status"], "mismatch")

    def test_missing_old_metadata_remains_unverifiable(self):
        record = self.record()
        del record["provenance"]
        self.assertEqual(self.verify(record)["status"], "unverifiable")

    def test_tampered_aggregate_fingerprint_is_rejected(self):
        record = self.record()
        record["fingerprint"] = "0" * 16
        self.assertEqual(self.verify(record)["status"], "mismatch")

    def test_failed_check_can_preserve_new_output_provenance(self):
        record = self.record(success=False)
        result = self.verify(record)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["measurement_status"], "failed")
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["output_hashes"], {})

    def test_failed_run_cannot_claim_an_untouched_old_result(self):
        record = self.record(success=False)
        before = self.stage.observe_outputs()
        record["result_provenance"] = L.result_provenance(self.stage, before, time.time_ns(), True)
        self.assertEqual(self.verify(record)["status"], "unverifiable")

    def test_missing_source_consistency_and_generation_time_are_rejected(self):
        record = self.record()
        record["result_provenance"]["source_consistent"] = False
        self.assertEqual(self.verify(record)["status"], "unverifiable")
        record["result_provenance"]["source_consistent"] = True
        record["result_provenance"]["started_at_ns"] = time.time_ns() + 10_000_000_000
        self.assertEqual(self.verify(record)["status"], "unverifiable")

    def test_missing_source_cannot_be_certified(self):
        (self.root / "experiments/stage.py").unlink()
        record = self.record()
        self.assertEqual(self.verify(record)["status"], "unverifiable")

    def test_filesystem_clock_lag_does_not_override_observed_new_file(self):
        record = self.record()
        evidence = record["result_provenance"]
        evidence["outputs"][self.stage.outputs[0]]["after"]["mtime_ns"] = evidence["started_at_ns"] - 3_000_000
        self.assertEqual(self.verify(record)["status"], "verified")

    def test_command_snapshot_does_not_mutate_with_stage(self):
        snapshot = self.stage.provenance()
        self.stage.cmd.append("--changed")
        self.assertNotEqual(snapshot["command"], self.stage.provenance()["command"])

    def test_corrupt_state_is_read_only_and_does_not_get_recovered(self):
        state = self.root / "bad_state.json"
        state.write_text("{invalid", encoding="utf-8")
        with patch.object(L, "build_stages", return_value=[self.stage]), \
             patch.object(P19, "RESULT_STAGES", {"p3_effect.json": "p3"}):
            results = P19.audit_content_provenance(str(self.output.parent), str(state))
        self.assertEqual(results[0]["status"], "unverifiable")
        self.assertEqual(state.read_text(encoding="utf-8"), "{invalid")
        self.assertFalse(state.with_suffix(".json.corrupt").exists())

    @pytest.mark.historical(reason='requires the enabled historical runner; gen33 intentionally refuses legacy execution')
    def test_loop_records_failed_run_without_marking_it_done(self):
        state = {"stages": {}, "history": []}
        def run(stage):
            self.output.write_text('{"runs": []}', encoding="utf-8")
            return False, "exit 1", .1, "statistical failure", "temporary-log"
        with patch.object(L, "build_stages", return_value=[self.stage]), \
             patch.object(L, "load_state", return_value=state), \
             patch.object(L, "atomic_write_json"), patch.object(L, "run_stage", side_effect=run), \
             patch.object(L, "show_status"), patch.object(sys, "argv", ["loop2", "--only", "p3"]), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(L.main(), 1)
        record = state["stages"]["p3"]
        self.assertEqual(record["status"], "failed")
        self.assertEqual(self.verify(record)["status"], "verified")

    def test_imports_do_not_create_state_or_result_directories(self):
        code = ("import os,sys; sys.path[:0]=" + repr([str(ROOT / "experiments"), str(ROOT)]) + ";"
                "os.makedirs=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('mkdir during import'));"
                "import loop2,p19_provenance")
        result = subprocess.run([sys.executable, "-B", "-c", code], cwd=self.root,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class ReportDependencyTests(unittest.TestCase):
    def setUp(self):
        self.stages = L.build_stages()
        self.by_id = {stage.id: stage for stage in self.stages}

    def test_every_input_precedes_its_reader_including_provenance_before_report(self):
        positions = {stage.id: i for i, stage in enumerate(self.stages)}
        for stage in self.stages:
            for dependency in stage.deps:
                self.assertLess(positions[dependency], positions[stage.id],
                                (stage.id, dependency))
        self.assertLess(positions["p19"], positions["p6"])
        self.assertIn("p7", self.by_id["p19"].soft_deps)

    def test_changed_report_inputs_invalidate_report(self):
        for changed in ("p13", "p15", "p16", "p19", "p20"):
            with self.subTest(changed=changed), patch.object(
                    L, "stage_status", side_effect=lambda stage, state:
                    ("stale" if stage.id == changed else "done", "test")):
                self.assertIn("p6", L.resolve(self.stages, {}, []))
        with patch.object(L, "stage_status", side_effect=lambda stage, state:
                          ("stale" if stage.id == "p7" else "done", "test")):
            self.assertIn("p19", L.resolve(self.stages, {}, []))

    def test_new_soft_inputs_do_not_weaken_existing_hard_requirements(self):
        report = self.by_id["p6"]
        self.assertEqual(set(report.soft_deps), {"p13", "p15", "p16", "p19", "p20"})
        self.assertEqual(set(report.deps) - set(report.soft_deps),
                         {"p1", "p2", "p3", "p4", "p5", "p7", "p8", "p9", "p10",
                          "p11", "p12", "p17", "p18"})
        with patch.object(L, "stage_status", side_effect=lambda stage, state:
                          ("pending" if stage.id in report.soft_deps else "done", "test")):
            self.assertEqual(L.stale_upstream(self.stages, {}, "p6"), [])
        with patch.object(L, "stage_status", side_effect=lambda stage, state:
                          ("pending" if stage.id == "p17" else "done", "test")):
            self.assertIn("p17(pending)", L.stale_upstream(self.stages, {}, "p6"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
