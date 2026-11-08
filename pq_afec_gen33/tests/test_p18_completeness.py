import ast
import contextlib
import copy
from datetime import datetime, timezone
import io
import math
from pathlib import Path
import statistics
from types import SimpleNamespace
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "experiments" / "p18_mmax.py"
ARMS = [1, 2, 3, 4]


def pure_functions(names, **namespace):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    selected = [node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name in names]
    if {node.name for node in selected} != set(names):
        raise AssertionError("requested functions missing")
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace


P = pure_functions({"trial_coverage", "decision_gain", "ratio_ok"}, math=math)


def record(name, n=2, up=0.0):
    values = {1: 150.0, 2: 100.0, 3: 60.0, 4: 50.0}
    segments = [{"block": block, "m": m, "pos": (m - 1 - block) % 4,
                 "n": n, "ok": n, "mean": values[m]}
                for block in range(4) for m in ARMS]
    return {"cond": name, "n_per_block": n, "complete": True, "err": "",
            "cert": 16000, "burst": 1, "loss": 0, "uplink": up,
            "srv_crc_fail": 0, "srv_stats_present": True,
            "segments": segments,
            "arms": {str(m): {"n": 8, "mean": values[m],
                              "ms": [values[m] - 0.1, values[m] + 0.1] * 4}
                     for m in ARMS}}


class CompleteTrialTests(unittest.TestCase):
    def test_complete_trials_pass(self):
        out = P["trial_coverage"]([record("a")], [("a", 16000, 1, 0, 0, 2)], ARMS)
        self.assertTrue(out["complete"])
        self.assertEqual((out["planned_n"], out["recorded_n"], out["ok_n"]), (32, 32, 32))
        self.assertEqual((out["failed_n"], out["missing_n"]), (0, 0))

    def test_74000_planned_with_six_failures_cannot_pass_80_complete_segments(self):
        counts = [125, 2250, 750, 750, 750]
        conds = [(str(i), 16000, 1, 0, 0, n) for i, n in enumerate(counts)]
        rows = [record(str(i), n) for i, n in enumerate(counts)]
        rows[1]["segments"][0]["ok"] -= 5
        rows[1]["segments"][1]["ok"] -= 1
        rows[1]["complete"] = False
        out = P["trial_coverage"](rows, conds, ARMS)
        self.assertEqual(out["recorded_segments"], 80)
        self.assertEqual(out["planned_n"], 74000)
        self.assertEqual(out["ok_n"], 73994)
        self.assertEqual(out["failed_n"], 6)
        self.assertEqual(out["missing_n"], 0)
        self.assertFalse(out["complete"])

    def test_counts_are_checked_even_if_complete_flag_is_incorrectly_true(self):
        row = record("a")
        row["segments"][0]["ok"] = 1
        self.assertFalse(P["trial_coverage"]([row], [("a", 1, 1, 0, 0, 2)], ARMS)["complete"])

    def test_condition_error_and_segment_error_fail_independently(self):
        for where in ("condition", "segment"):
            row = record("a")
            target = row if where == "condition" else row["segments"][0]
            target["err"] = "timeout"
            with self.subTest(where=where):
                out = P["trial_coverage"]([row], [("a", 1, 1, 0, 0, 2)], ARMS)
                self.assertFalse(out["complete"])

    def test_missing_record_is_not_counted_as_success_or_recorded_failure(self):
        row = record("a")
        row["segments"][0].update(n=1, ok=1)
        out = P["trial_coverage"]([row], [("a", 1, 1, 0, 0, 2)], ARMS)
        self.assertEqual((out["ok_n"], out["failed_n"], out["missing_n"]), (31, 0, 1))
        self.assertFalse(out["complete"])

    def test_missing_conditions_and_nonfinite_means_fail(self):
        conds = [("a", 1, 1, 0, 0, 2), ("b", 1, 1, 0, 0, 2)]
        self.assertFalse(P["trial_coverage"]([record("a")], conds, ARMS)["complete"])
        row = record("a")
        row["segments"][0]["mean"] = math.nan
        self.assertFalse(P["trial_coverage"]([row], conds[:1], ARMS)["complete"])

    def test_missing_complete_contract_is_not_inferred_from_a_mean(self):
        row = record("a")
        del row["complete"]
        self.assertFalse(P["trial_coverage"]([row], [("a", 1, 1, 0, 0, 2)], ARMS)["complete"])

    def test_final_report_requires_complete_trials(self):
        rows = [record("base"), record("shaped", up=2.0)]
        rows[0]["segments"][0]["ok"] = 1
        rows[0]["complete"] = False
        conds = [("base", 16000, 1, 0, 0, 2), ("shaped", 16000, 1, 0, 2, 2)]
        ns = pure_functions(
            {"mean", "se", "gain_ci", "pos_effect", "trial_coverage", "decision_gain",
             "ratio_ok", "analyse_condition", "add_result", "build_result"},
            math=math, statistics=statistics, ARMS=ARMS,
            N=2, RTT_MS=50, GROUP="synthetic", POL=SimpleNamespace(M_MAX_DEFAULT=3),
            BST=SimpleNamespace(balance=lambda cells: (True, "synthetic"),
                                latin_anova=lambda cells: {"ok": False}))
        models = {r["cond"]: {1: 150.0, 2: 100.0, 3: 60.0, 4: 50.0} for r in rows}
        out = ns["build_result"](rows, models, conds)
        self.assertFalse(out["checks"][0]["ok"])
        self.assertLess(out["passed"], out["total"])
        self.assertEqual(out["trial_coverage"]["failed_n"], 1)
        self.assertEqual(out["hct_scope"], "successful_trials_only")

    def test_collector_preserves_failed_trials_and_every_process_error(self):
        calls = []

        def client(*args, **kwargs):
            i = len(calls)
            calls.append(i)
            return ([{"ok": True, "ms": 50.0},
                     {"ok": i != 0, "ms": 51.0, "err": "trial failure" if i == 0 else ""}],
                    {"sentinel_segment": i}, "process error" if i in (0, 1) else "")

        journal_writes = []
        b = SimpleNamespace(
            start_server=lambda *args, **kwargs: (None, "unused"),
            set_netem=lambda *args, **kwargs: None, run_client=client,
            stop_server=lambda *args: None,
            read_server_stats=lambda *args: {"recover_crc_fail": 0, "sentinel_shared": 91},
            pctl=lambda vals, p: vals[0] if vals else None)
        jr = SimpleNamespace(has=lambda key: False, fingerprint="synthetic-fp", run_id="synthetic-run",
                             record=lambda *args: journal_writes.append(args))
        f = pure_functions({"mean", "trial_coverage", "run_cond", "unit_key", "attach_unit_provenance"},
                           math=math, copy=copy, ARMS=ARMS, datetime=datetime, timezone=timezone,
                           B=b, RTT_MS=50, GROUP="synthetic", K=2)["run_cond"]
        with contextlib.redirect_stdout(io.StringIO()):
            out = f("a", 16000, 1, 0, 0, 2, jr)
        self.assertEqual(len(out["segments"]), 16)
        first = out["segments"][0]
        self.assertEqual((first["planned_n"], first["n"], first["ok"], first["fail"]), (2, 2, 1, 1))
        self.assertFalse(first["trial_records"][1]["ok"])
        self.assertEqual(len(first["trial_records"]), 2)
        self.assertIn("block0 m1", out["err"])
        self.assertIn("block0 m2", out["err"])
        self.assertFalse(out["complete"])
        self.assertEqual(journal_writes, [])
        self.assertEqual(first["client_stats"], {"sentinel_segment": 0})
        self.assertEqual(out["segments"][1]["client_stats"], {"sentinel_segment": 1})
        self.assertEqual(out["server_stats"], {"recover_crc_fail": 0, "sentinel_shared": 91})
        self.assertEqual(out["server_stats_scope"], "shared_condition_across_fixed_arms_and_blocks")
        self.assertFalse(out["unit_provenance"]["journaled"])
        self.assertEqual(out["unit_provenance"]["run_id"], "synthetic-run")
        self.assertIsNotNone(out["unit_provenance"]["recorded_at"])


class DecisionWidthTests(unittest.TestCase):
    def verdict(self, **kw):
        value = {"significant": True, "pred_gain_m2_to_m4": 1.0,
                 "obs_gain_m2_to_m4": 1.6, "obs_gain_ci95_half": 0.1,
                 "ci_half_used": 1.5}
        value.update(kw)
        return value

    def test_prediction_below_actual_decision_half_is_not_ratio_eligible(self):
        self.assertIsNone(P["ratio_ok"](self.verdict()))

    def test_same_selected_width_supports_pass_and_failure_without_widening_ratio(self):
        self.assertTrue(P["ratio_ok"](self.verdict(ci_half_used=0.5)))
        self.assertFalse(P["ratio_ok"](self.verdict(ci_half_used=0.5, obs_gain_m2_to_m4=2.1)))

    def test_missing_actual_half_never_falls_back_to_narrow_connection_interval(self):
        v = self.verdict()
        del v["ci_half_used"]
        self.assertIsNone(P["ratio_ok"](v))


if __name__ == "__main__":
    unittest.main()
