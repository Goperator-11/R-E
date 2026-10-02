"""Offline regressions for measurement integrity. No netns or live traffic."""
import argparse
import contextlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT))
import _journal as J
import blockstat as BST
import fixloop as F
import loop2 as L
import padbed as B
import p2_threshold as P2
import p9_crossenv as P9
import p19_provenance as P19
import p18_mmax as P18
import gate_go_parity as GATE
import p0_env as P0
import p12_quantum as P12


class JournalTests(unittest.TestCase):
    def test_torn_utf8_tail_does_not_swallow_next_record(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "units.jsonl"
            journal = J.Journal(str(path), "test")
            journal.record("first", 1)
            with path.open("ab") as stream:
                stream.write(b'{"val":"\xed\x95')
            resumed = J.Journal(str(path), "test")
            resumed.record("second", 2)
            self.assertEqual(J.Journal(str(path), "test").items(), {"first": 1, "second": 2})

    def test_bad_record_shapes_are_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "units.jsonl"
            path.write_text('[]\nnull\n{"fp":"test"}\n', encoding="utf-8")
            self.assertEqual(len(J.Journal(str(path), "test")), 0)

    def test_failed_serialization_or_fsync_does_not_mark_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = J.Journal(str(Path(directory) / "units.jsonl"), "test")
            with self.assertRaises(TypeError):
                journal.record("bad", object())
            self.assertFalse(journal.has("bad"))
            with patch.object(J.os, "fsync", side_effect=OSError("disk")):
                with self.assertRaises(OSError):
                    journal.record("disk", 1)
            self.assertFalse(journal.has("disk"))

    def test_result_replace_failure_preserves_original_and_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results" / "report.json"
            backups = Path(directory) / "backups"
            J.save_result(str(path), {"v": 1}, backup_dir=str(backups))
            with patch.object(J.os, "replace", side_effect=OSError("blocked")):
                with self.assertRaises(OSError):
                    J.save_result(str(path), {"v": 2}, backup_dir=str(backups))
            self.assertEqual(json.loads(path.read_text()), {"v": 1})
            self.assertEqual(len(list(backups.glob("*.json"))), 1)

    def test_source_helper_and_environment_invalidate_journal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "experiments"
            path.mkdir()
            (path / "main.py").write_text("# main")
            helper = path / "helper.py"
            helper.write_text("# v1")
            before = J.code_fingerprint(["experiments/main.py"], directory)
            helper.write_text("# v2")
            after = J.code_fingerprint(["experiments/main.py"], directory)
            self.assertNotEqual(before, after)
            with patch.dict(os.environ, {"PADFEC_P11_N": "99999"}):
                self.assertNotEqual(after, J.code_fingerprint(["experiments/main.py"], directory))


class StatisticsTests(unittest.TestCase):
    def test_empty_design_fails(self):
        self.assertFalse(BST.balance([])[0])

    def test_confounded_design_cannot_return_zero_standard_error(self):
        rows = [dict(arm=i // 4, pos=i // 4, block=i % 4, value=float(i // 4))
                for i in range(16)]
        self.assertFalse(BST.latin_anova(rows)["ok"])

    def test_balanced_design_agrees_with_direct_residual_fit(self):
        rows = [dict(arm=(r+c) % 4, pos=c, block=r,
                     value=20.0 + 3*((r+c) % 4) + 2*r - c + (r*c % 3)*.2)
                for r in range(4) for c in range(4)]
        anova = BST.latin_anova(rows)
        self.assertTrue(anova["ok"])
        by = {key: {level: sum(x["value"] for x in rows if x[key] == level)/4
                     for level in range(4)} for key in ("arm", "pos", "block")}
        residual = sum((x["value"] - by["arm"][x["arm"]] - by["pos"][x["pos"]]
                        - by["block"][x["block"]] + 2*anova["grand"])**2 for x in rows)
        self.assertAlmostEqual(anova["mse"], residual / 6, places=10)
        self.assertEqual(anova["df_resid"], 6)
        rows[0]["value"] = float("nan")
        self.assertFalse(BST.latin_anova(rows)["ok"])

    def test_t_critical_small_df_known_and_arbitrary_alpha(self):
        for alpha in (.05, .025, .0125, .01, .005, .0037):
            # df=1 is exactly the Cauchy distribution.
            expected = 1 / math.tan(math.pi * alpha / 2)
            self.assertAlmostEqual(BST.t_crit(1, alpha), expected, delta=expected*1e-10)
            # df=2 has a closed-form quantile.
            z = 1-alpha
            expected2 = math.sqrt(2*z*z / (1-z*z))
            self.assertAlmostEqual(BST.t_crit(2, alpha), expected2, delta=expected2*1e-10)
        self.assertAlmostEqual(BST.t_crit(6, .01), 3.707428021324907, places=9)
        self.assertAlmostEqual(BST.t_crit(120, .0125), 2.5359148400775, places=9)

    def test_invalid_t_inputs_fail(self):
        for df, alpha in [(0, .05), (-1, .05), (math.nan, .05), (1, 0), (1, 1), (1, math.nan)]:
            with self.assertRaises(ValueError):
                BST.t_crit(df, alpha)

    def test_batch_difference_uses_batch_degrees_of_freedom(self):
        values = [float(i) for i in range(8) for _ in range(8)]
        se, method, batches = BST.batch_se_info(values)
        self.assertEqual((method, batches), ("batch", 8))
        expected = BST.t_crit(14) * math.sqrt(2) * se
        self.assertAlmostEqual(BST.batch_diff_half(values, values), expected, places=10)
        self.assertGreater(expected, 1.96 * math.sqrt(2) * se)
        self.assertIsNone(BST.batch_diff_half([], values))

    def test_fixed_m_model_does_not_select_padding_candidate(self):
        candidates = [{"m": 2, "delta_per_dgram": 0, "W_eff": 1280, "j_ms": 100},
                      {"m": 2, "delta_per_dgram": 1, "W_eff": 1281, "j_ms": 50}]
        with patch.object(P18.B, "measured_C", return_value=1448), \
             patch.object(P18.POL, "decide_v2", return_value={"candidates": candidates}):
            self.assertEqual(P18.model_j(16000, 1, 0, 0, 2), 100)


class HarnessTests(unittest.TestCase):
    def test_p0_server_readiness_timeout_does_not_block_on_readline(self):
        process = Mock()
        process.poll.return_value = None
        with patch.object(P0.subprocess, "Popen", return_value=process), \
             patch.object(P0.subprocess, "run") as client, patch.object(B, "stop_server") as stop, \
             patch.object(P0.time, "monotonic", side_effect=[0, 16]):
            ok, info = P0.loopback_stage0()
        self.assertFalse(ok)
        self.assertFalse(info["ready"])
        client.assert_not_called()
        stop.assert_called_once_with(process)

    def test_p0_nonzero_exit_rejects_five_success_rows(self):
        process = Mock()
        process.poll.return_value = None
        def spawn(*args, **kwargs):
            kwargs["stderr"].write(b"READY\n")
            kwargs["stderr"].flush()
            return process
        output = '\n'.join(json.dumps({"ok": True, "kem_id": 29}) for _ in range(5))
        result = subprocess.CompletedProcess([], 1, output, "crash after rows")
        with patch.object(P0.subprocess, "Popen", side_effect=spawn), \
             patch.object(P0.subprocess, "run", return_value=result), patch.object(B, "stop_server"):
            ok, info = P0.loopback_stage0()
        self.assertFalse(ok)
        self.assertEqual(info["ok"], 5)
        self.assertEqual(info["client_returncode"], 1)

    def test_affinity_uses_actual_cpu_ids(self):
        with patch.object(B.os, "sched_getaffinity", return_value={8, 10, 12, 14, 16}, create=True):
            self.assertEqual(B._cpu_list(), "8,10,12,14")

    def test_identical_size_and_mtime_do_not_hide_stale_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "build"
            binary.mkdir()
            source = binary / "qamp"
            target = Path(directory) / "qamp"
            source.write_bytes(b"new!")
            target.write_bytes(b"old!")
            os.utime(source, (1000000, 1000000))
            os.utime(target, (2000000, 2000000))
            Path(str(source) + ".srcsha").write_text("new hash")
            with patch.object(B, "BIN", str(binary)), patch.object(B, "QAMP", str(target)):
                B.require_bin()
            self.assertEqual(target.read_bytes(), b"new!")
            self.assertEqual(Path(str(target) + ".srcsha").read_text(), "new hash")

    def test_warmup_is_dropped_even_when_client_stops_early(self):
        output = '\n'.join(json.dumps({"ok": True, "ms": 1}) for _ in range(2))
        result = subprocess.CompletedProcess([], 0, output, "")
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(B, "require_bin", return_value="fake"), patch.object(B.subprocess, "run", return_value=result):
                rows, stats, err = B.run_client("x25519", 10, warmup=3,
                                                stats_path=str(Path(directory) / "missing"))
            self.assertEqual(rows, [])
            self.assertEqual(stats["warmup_dropped"], 2)
            self.assertTrue(err)

    def test_server_exit_before_ready_raises(self):
        process = Mock()
        process.poll.return_value = 1
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(B, "WORK", directory), patch.object(B, "require_bin", return_value="fake"), \
                 patch.object(B.subprocess, "Popen", return_value=process), patch.object(B, "stop_server") as stop:
                with self.assertRaises(RuntimeError):
                    B.start_server(4000)
                stop.assert_called_once_with(process)


class ThresholdTests(unittest.TestCase):
    def test_empty_client_run_is_not_journaled(self):
        journal = Mock()
        journal.has.return_value = False
        with patch.object(B, "start_server", return_value=(None, "stats")), \
             patch.object(B, "run_client", return_value=([], {}, "timeout")), \
             patch.object(B, "stop_server"), patch.object(B, "read_server_stats", return_value={}):
            rec = P2.probe("x25519", "off", 1, 3000, 1, 15, journal)
        self.assertFalse(rec["valid"])
        journal.record.assert_not_called()
        self.assertIsNone(P2.is_two_rtt(rec))

    def test_partial_success_has_no_threshold_classification(self):
        self.assertIsNone(P2.is_two_rtt({"n": 15, "ok": 1, "two_rtt_rate": 0.0}))

    def test_failed_confirmation_does_not_move_lower_bound(self):
        low = {"n": 15, "ok": 15, "two_rtt_rate": 0.0}
        high = {"n": 15, "ok": 15, "two_rtt_rate": 1.0}
        middle = {"n": 15, "ok": 15, "two_rtt_rate": .5}
        failed = {"n": 0, "ok": 0, "two_rtt_rate": None}
        with patch.object(P2, "probe", side_effect=[low, high, middle, failed]):
            result = P2.bisect_threshold("x25519", "off", 1, 1, None, lambda x: None)
        self.assertIsNone(result["lo"])
        probe = Mock(side_effect=[low, high, middle, failed])
        self.assertIsNone(P9.bisect(probe, lambda x: None)["lo"])
        with patch.object(P12, "probe", side_effect=[low, high, middle, failed]), \
             patch.object(P12, "log"):
            self.assertIsNone(P12.bisect_threshold("x25519", 1280, 1, None)["lo"])

    def test_p12_partial_client_run_is_not_journaled(self):
        journal = Mock()
        journal.has.return_value = False
        with patch.object(B, "start_server", return_value=(None, "stats")), \
             patch.object(B, "run_client", return_value=([{"ok": True, "ms": 50}], {}, "rows 1 != n 15")), \
             patch.object(B, "stop_server"):
            rec = P12.probe("x25519", 1280, 3000, 1, 15, journal)
        self.assertFalse(rec["valid"])
        journal.record.assert_not_called()


class PipelineTests(unittest.TestCase):
    def stage(self, output=()):
        return L.Stage("example", "test", "win", [sys.executable, "-c", "pass"], output, [])

    def test_runtime_and_soft_dependencies_change_stage_fingerprint(self):
        stage = self.stage()
        before = stage.fingerprint()
        with patch.dict(os.environ, {"PADFEC_P11_N": "98765"}):
            self.assertNotEqual(before, stage.fingerprint())
        stage.deps = ["p1"]
        before = stage.fingerprint()
        stage.soft_deps = ["p1"]
        self.assertNotEqual(before, stage.fingerprint())

    def test_changed_output_invalidates_done_without_source_change(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(L, "ROOT", directory):
            output = Path(directory) / "result.json"
            output.write_text('{"v":1}')
            stage = self.stage(["result.json"])
            state = {"stages": {stage.id: {"status": "done", "fingerprint": stage.fingerprint(),
                                          "output_hashes": stage.output_hashes()}}}
            self.assertEqual(L.stage_status(stage, state)[0], "done")
            output.write_text('{"v":2}')
            self.assertEqual(L.stage_status(stage, state)[0], "stale")

    def test_zero_exit_without_required_output_fails(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(L, "ROOT", directory), \
             patch.object(L, "STATE_DIR", directory):
            ok, error, *_ = L.run_stage(self.stage(["missing.json"]))
        self.assertFalse(ok)
        self.assertIn("산출물", error)

    def test_keep_going_returns_failure_for_failed_leaf(self):
        stage = self.stage()
        state = {"stages": {}, "history": []}
        with patch.object(L, "build_stages", return_value=[stage]), \
             patch.object(L, "load_state", side_effect=lambda: state), \
             patch.object(L, "atomic_write_json"), patch.object(L, "show_status"), \
             patch.object(L, "harden"), patch.object(L, "run_stage", return_value=(False, "exit 1", .1, "", "log")), \
             patch.object(sys, "argv", ["loop2.py", "--loop", "--keep-going"]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(L.main(), 1)

    def test_p12_and_report_artifacts_are_registered(self):
        stages = {s.id: s for s in L.build_stages()}
        self.assertIn("p12", stages)
        self.assertEqual(len(stages["p6"].outputs), 3)
        self.assertIn("verify.py", stages["lint"].cmd)
        self.assertIn("afec/channel.py", stages["lint"].scripts)
        self.assertIn("experiments/quicbed/shim.py", stages["lint"].scripts)

    def test_module_lock_changes_invalidate_go_build_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(GATE, "QUICBED", directory):
            for filename in ("qamp.go", "build.sh", "go.mod", "go.sum"):
                (Path(directory) / filename).write_text(filename)
            old = GATE.go_src_fingerprint()
            (Path(directory) / "go.sum").write_text("updated dependency")
            self.assertNotEqual(old, GATE.go_src_fingerprint())
        self.assertIn("experiments/quicbed/go.mod", L.BED)
        self.assertIn("experiments/quicbed/go.sum", L.BED)

    def test_detach_preserves_unlock_before_remainder(self):
        args = argparse.Namespace(rounds=1, max_env_retry=3, force_unlock=True,
                                  loop2_arg=["--only", "p11"])
        command = F.detached_command(args)
        self.assertLess(command.index("--force-unlock"), command.index("--loop2-arg"))

    def test_refused_breakaway_goes_directly_to_wmi(self):
        args = argparse.Namespace(rounds=1, max_env_retry=3, force_unlock=True, loop2_arg=[])
        startup = Mock(dwFlags=0)
        result = subprocess.CompletedProcess([], 0, "456\n", "")
        with tempfile.TemporaryDirectory() as directory, patch.object(F, "STATE_DIR", directory), \
             patch.object(F.subprocess, "STARTUPINFO", return_value=startup, create=True), \
             patch.object(F.subprocess, "STARTF_USESHOWWINDOW", 1, create=True), \
             patch.object(F.subprocess, "Popen", side_effect=OSError("breakaway refused")) as spawn, \
             patch.object(F.subprocess, "run", return_value=result) as wmi, patch.object(F, "journal"), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(F.detach(args), 0)
            spawn.assert_called_once()
            self.assertEqual(spawn.call_args.kwargs["creationflags"], 0x01000210)
            self.assertIn("Invoke-CimMethod", wmi.call_args.args[0][-1])

    def test_wmi_launcher_preserves_precision_and_redirects_without_shell(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(F, "STATE_DIR", directory):
            output = str(Path(directory) / "out.txt")
            command = F.detached_launcher([sys.executable, "-c", "import os; print(os.environ['PADFEC_P11_N'])"],
                                          output, {"PADFEC_P11_N": "4321", "UNRELATED_SECRET": "never persist"})
            source = Path(command[-1]).read_text(encoding="utf-8")
            self.assertNotIn("UNRELATED_SECRET", source)
            subprocess.run(command, check=True)
            self.assertEqual(Path(output).read_text().strip(), "4321")


class ProvenanceTests(unittest.TestCase):
    def test_missing_arrays_and_nonfinite_values_fail(self):
        self.assertTrue(P19.missing_raw({"rows": [{"mean": 1}]}, "p11_adaptive.json"))
        self.assertTrue(P19.missing_raw({"rows": [{"ms": [math.nan]}]}, "p11_adaptive.json"))
        self.assertFalse(P19.close(math.inf, math.inf))

    def test_success_sample_count_is_checked(self):
        pairs = P19._basic({"n": 20, "ok": 2, "mean": 1, "p50": 1}, [1], "test")
        count = next(pair for pair in pairs if "raw_success_count" in pair[0])
        self.assertFalse(P19.close(count[1], count[2]))

    def test_tail_recalculation_uses_recorded_rtt(self):
        pairs = P19.check_p11({"rtt_ms": 100, "rows": [{"n": 1, "ok": 1, "ms": [100],
                                      "mean": 100, "p50": 100, "tail": 0}]})
        tail = next(pair for pair in pairs if pair[0].endswith(".tail"))
        self.assertEqual(tail[1], tail[2])


if __name__ == "__main__":
    unittest.main()
