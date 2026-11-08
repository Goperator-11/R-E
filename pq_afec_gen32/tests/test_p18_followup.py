import ast
import contextlib
import copy
from datetime import datetime, timezone
import importlib.util
import io
import math
from pathlib import Path
import statistics
import tempfile
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "experiments" / "p18_mmax.py"
ARMS = [1, 2, 3, 4]
spec = importlib.util.spec_from_file_location("p18_test_blockstat", ROOT / "experiments" / "blockstat.py")
BST = importlib.util.module_from_spec(spec)
spec.loader.exec_module(BST)
spec_journal = importlib.util.spec_from_file_location("p18_test_journal", ROOT / "experiments" / "_journal.py")
JOURNAL = importlib.util.module_from_spec(spec_journal)
spec_journal.loader.exec_module(JOURNAL)


def functions(**overrides):
    ns = dict(math=math, statistics=statistics, copy=copy, datetime=datetime,
              timezone=timezone, ARMS=ARMS, RTT_MS=50.0, GROUP="synthetic", N=3,
              K=2, BST=BST, POL=SimpleNamespace(M_MAX_DEFAULT=3))
    ns.update(overrides)
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    selected = [x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name != "main"]
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(SOURCE), "exec"), ns)
    return ns


def fixture(name="base", up=0.0, unequal=False):
    values = {1: [152, 148, 153, 147], 2: [95, 100, 103, 106],
              3: [62, 58, 65, 55], 4: [50, 50, 50, 50]}
    segments, accumulated = [], {m: [] for m in ARMS}
    for block in range(4):
        for m in ARMS:
            n = 1 if unequal and block == 0 and m == 2 else 3
            vals = [values[m][block]] * n
            accumulated[m].extend(vals)
            segments.append(dict(block=block, m=m, pos=(m-1-block) % 4,
                                 planned_n=3, n=3, ok=n, fail=3-n, missing=0, err="",
                                 mean=values[m][block]))
    return dict(cond=name, cert=16000, burst=1, loss=0, uplink=up, n_per_block=3,
                complete=not unequal, err="", srv_stats_present=True, srv_crc_fail=0,
                segments=segments,
                arms={str(m): dict(n=len(vals), mean=sum(vals)/len(vals), ms=vals)
                      for m, vals in accumulated.items()})


class IntervalTests(unittest.TestCase):
    def setUp(self):
        self.ns = functions()
        self.models = {1: 150.0, 2: 100.0, 3: 60.0, 4: 50.0}

    def test_normal_half_uses_normal_quantile_and_two_sample_variance(self):
        a, b = [1, 2, 5, 8], [2, 3, 7]
        gain, half = self.ns["gain_ci"](a, b, .01)
        expected = statistics.NormalDist().inv_cdf(.995) * math.sqrt(
            statistics.variance(a)/len(a) + statistics.variance(b)/len(b))
        self.assertAlmostEqual(gain, statistics.mean(a)-statistics.mean(b))
        self.assertAlmostEqual(half, expected)

    def test_latin_interval_pairs_equal_cell_center_with_latin_half(self):
        rec = fixture(unequal=True)
        out = self.ns["analyse_condition"](rec, self.models, .01)
        self.assertNotEqual(out["obs_gain_m2_to_m4"], out["blocked_gain_m2_to_m4"])
        self.assertEqual(out["decision_ci_method"], "latin_square_t")
        self.assertAlmostEqual(out["blocked_gain_m2_to_m4"], (95+100+103+106)/4-50)
        self.assertEqual(out["decision_gain_m2_to_m4"], out["blocked_gain_m2_to_m4"])
        self.assertAlmostEqual(sum(out["blocked_ci"])/2, out["blocked_gain_m2_to_m4"])
        self.assertAlmostEqual(sum(out["decision_ci"])/2, out["decision_gain_m2_to_m4"])

    def test_normal_wider_selects_pooled_success_center(self):
        ns = functions(BST=SimpleNamespace(balance=lambda x: (True, "synthetic"),
                       latin_anova=lambda x: {"ok": True}, contrast=lambda *args: (1.0, .001)))
        out = ns["analyse_condition"](fixture(unequal=True), self.models, .01)
        self.assertEqual(out["decision_ci_method"], "normal_iid")
        self.assertEqual(out["decision_gain_m2_to_m4"], out["obs_gain_m2_to_m4"])
        self.assertEqual(out["ci_half_used"], out["connection_ci_half"])

    def test_tied_half_preserves_normal_estimate(self):
        rec = fixture(unequal=True)
        half = self.ns["gain_ci"](rec["arms"]["2"]["ms"], rec["arms"]["4"]["ms"], .01)[1]
        ns = functions(BST=SimpleNamespace(balance=lambda x: (True, "synthetic"),
                       latin_anova=lambda x: {"ok": True}, contrast=lambda *args: (1.0, half)))
        out = ns["analyse_condition"](rec, self.models, .01)
        self.assertEqual(out["decision_ci_method"], "normal_iid")

    def test_invalid_latin_falls_back_to_normal_but_keeps_design_failure(self):
        ns = functions(BST=SimpleNamespace(balance=lambda x: (False, "unbalanced"),
                       latin_anova=lambda x: {"ok": False}))
        out = ns["analyse_condition"](fixture(), self.models, .01)
        self.assertFalse(out["design_balanced"])
        self.assertIsNone(out["blocked_ci"])
        self.assertEqual(out["decision_ci_method"], "normal_iid")

    def test_confidence_and_plugin_names_do_not_claim_95_percent_or_power(self):
        out = self.ns["analyse_condition"](fixture(), self.models, .01)
        self.assertEqual(out["alpha"], .01)
        self.assertEqual(out["per_comparison_confidence_level"], .99)
        self.assertEqual(out["family_confidence_level"], .95)
        self.assertEqual(out["connection_ci_method"], "normal_iid")
        self.assertNotIn("obs_gain_ci95_half", out)
        self.assertNotIn("n_needed_per_arm", out)
        self.assertIn("no_power_guarantee", out["n_plugin_scope"])

    def test_ratio_uses_selected_center_and_keeps_0_5_to_2_threshold(self):
        v = dict(significant=True, pred_gain_m2_to_m4=1.0,
                 obs_gain_m2_to_m4=3.0, decision_gain_m2_to_m4=1.1, ci_half_used=.2)
        self.assertTrue(self.ns["ratio_ok"](v))
        v["decision_gain_m2_to_m4"] = 2.1
        self.assertFalse(self.ns["ratio_ok"](v))

    def test_legacy_center_remains_readable(self):
        self.assertEqual(self.ns["decision_gain"]({"obs_gain_m2_to_m4": 2}), 2)
        self.assertEqual(self.ns["decision_gain"]({"decision_gain_m2_to_m4": 3}), 3)

    def test_empty_sample_has_no_connection_interval(self):
        self.assertEqual(self.ns["gain_ci"]([], [1, 2], .01), (None, None))


class ReportTests(unittest.TestCase):
    def assemble(self, rows):
        conds = [(r["cond"], r["cert"], r["burst"], r["loss"], r["uplink"], 3) for r in rows]
        models = {r["cond"]: {1: 150.0, 2: 100.0, 3: 60.0, 4: 50.0} for r in rows}
        return functions()["build_result"](rows, models, conds)

    def test_diagnostics_are_separate_and_cannot_increment_pass_count(self):
        out = self.assemble([fixture(), fixture("shaped", up=2)])
        self.assertEqual(out["total"], 10)
        self.assertEqual(out["diagnostic_count"], 2)
        self.assertEqual(out["passed"], sum(c["ok"] for c in out["checks"]))
        self.assertTrue(all(d["ok"] is None and not d["counted"] for d in out["diagnostics"]))
        self.assertTrue(any(d["check"].startswith("4b.") for d in out["diagnostics"]))

    def test_actual_point_criteria_remain_counted_and_cap_is_3(self):
        out = self.assemble([fixture(), fixture("shaped", up=2)])
        self.assertEqual(out["current_adaptive_default_m_max"], 3)
        self.assertEqual(out["comparison_scope"], "fixed_m2_vs_m4_not_adaptive_cap_intervention")
        names = [c["check"].split(".")[0] for c in out["checks"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue({"6b", "8", "9"}.issubset(names))

    def test_one_failure_cannot_pass_with_valid_success_conditioned_ci(self):
        out = self.assemble([fixture(unequal=True), fixture("shaped", up=2)])
        self.assertFalse(out["checks"][0]["ok"])
        self.assertEqual(out["trial_coverage"]["failed_n"], 2)
        self.assertEqual(out["hct_scope"], "successful_trials_only")

    def test_builder_does_not_change_input_rows_or_models(self):
        rows = [fixture(), fixture("shaped", up=2)]
        original = copy.deepcopy(rows)
        self.assemble(rows)
        self.assertEqual(rows, original)


class MockJournal:
    def __init__(self, cached=None, old_metadata=None):
        self.fingerprint = "synthetic-fp"
        self.run_id = "current-run"
        self.cached = cached
        self.metadata = old_metadata
        self.writes = []

    def has(self, key):
        return self.cached is not None

    def get(self, key):
        return self.cached

    def record(self, key, rec):
        self.writes.append((key, rec))
        self.metadata = dict(key=key, run_id=self.run_id,
                             recorded_at=datetime.now(timezone.utc).isoformat(), reused=False)

    def provenance(self, keys):
        return {"units": [dict(self.metadata, key=keys[0])]}


def mock_transport(failed=False, server_present=True):
    calls = []
    def client(*args, **kwargs):
        fail = failed and not calls
        calls.append(kwargs)
        return ([dict(i=0, ok=not fail, ms=50.0, err="timeout" if fail else ""),
                 dict(i=1, ok=True, ms=51.0)], {"sentinel_segment": len(calls)-1}, "")
    return SimpleNamespace(start_server=lambda *a, **kw: (None, "synthetic"),
        set_netem=lambda *a, **kw: None, run_client=client, stop_server=lambda *a: None,
        read_server_stats=lambda *a: {"recover_crc_fail": 0, "sentinel_shared": 91} if server_present else {},
        pctl=lambda vals, p: statistics.median(vals) if vals else None), calls


class UnitProvenanceTests(unittest.TestCase):
    def collect(self, jr, **kwargs):
        b, calls = mock_transport(**kwargs)
        ns = functions(B=b)
        with contextlib.redirect_stdout(io.StringIO()):
            rec = ns["run_cond"]("a", 16000, 1, 0, 0, 2, jr)
        return rec, calls

    def test_incomplete_unit_retains_current_run_and_completion_without_journal_write(self):
        jr = MockJournal()
        rec, calls = self.collect(jr, failed=True)
        meta = rec["unit_provenance"]
        self.assertEqual(len(calls), 16)
        self.assertFalse(rec["complete"])
        self.assertEqual(jr.writes, [])
        self.assertEqual(meta["run_id"], "current-run")
        self.assertEqual(meta["recorded_at"], meta["measurement_finished_at"])
        self.assertLessEqual(meta["measurement_started_at"], meta["measurement_finished_at"])
        self.assertFalse(meta["journaled"])
        self.assertFalse(meta["reused"])

    def test_missing_server_stats_is_unjournaled_even_with_all_client_successes(self):
        jr = MockJournal()
        rec, _ = self.collect(jr, server_present=False)
        self.assertTrue(rec["complete"])
        self.assertFalse(rec["unit_provenance"]["journaled"])
        self.assertEqual(jr.writes, [])

    def test_complete_unit_keeps_journal_timestamp_and_does_not_modify_stored_record(self):
        jr = MockJournal()
        rec, _ = self.collect(jr)
        self.assertEqual(len(jr.writes), 1)
        self.assertTrue(rec["unit_provenance"]["journaled"])
        self.assertEqual(rec["unit_provenance"]["recorded_at"], jr.metadata["recorded_at"])
        self.assertNotIn("unit_provenance", jr.writes[0][1])
        self.assertNotIn("trial_records", rec["unit_provenance"])
        self.assertEqual(rec["segments"][0]["client_stats"], {"sentinel_segment": 0})
        self.assertEqual(rec["server_stats"], {"recover_crc_fail": 0, "sentinel_shared": 91})
        self.assertEqual(rec["server_stats_scope"], "shared_condition_across_fixed_arms_and_blocks")

    def test_cached_unit_keeps_true_old_run_time_without_transport(self):
        old = fixture()
        before = copy.deepcopy(old)
        jr = MockJournal(old, dict(run_id="old-run", recorded_at="2026-09-29T00:00:00Z", reused=True))
        b = SimpleNamespace(start_server=lambda *a, **kw: self.fail("transport used for cache"))
        rec = functions(B=b)["run_cond"]("a", 16000, 1, 0, 0, 2, jr)
        self.assertEqual(rec["unit_provenance"]["run_id"], "old-run")
        self.assertEqual(rec["unit_provenance"]["recorded_at"], "2026-09-29T00:00:00Z")
        self.assertTrue(rec["unit_provenance"]["reused"])
        self.assertNotIn("measurement_started_at", rec["unit_provenance"])
        self.assertEqual(old, before)
        self.assertEqual(jr.writes, [])

    def test_legacy_unknown_dates_are_preserved_and_counted_unknown(self):
        jr = MockJournal(fixture(), dict(run_id=None, recorded_at=None, reused=True))
        rec = functions()["run_cond"]("a", 16000, 1, 0, 0, 2, jr)
        provenance = functions()["result_provenance"]([rec], jr)
        self.assertIsNone(rec["unit_provenance"]["run_id"])
        self.assertEqual(provenance["unknown_run_id_units"], 1)
        self.assertEqual(provenance["unknown_recording_time_units"], 1)

    def test_summary_separates_reused_journal_and_new_unjournaled_units(self):
        jr = MockJournal()
        fresh, _ = self.collect(jr, failed=True)
        cached = functions()["attach_unit_provenance"](fixture(),
            MockJournal(fixture(), dict(run_id="old", recorded_at="old-time", reused=True)),
            "cached", journaled=True)
        out = functions()["result_provenance"]([cached, fresh], jr)
        self.assertEqual((out["used_units"], out["reused_units"], out["new_units"],
                          out["unjournaled_units"]), (2, 1, 1, 1))
        fresh["unit_provenance"]["run_id"] = "mutated"
        self.assertEqual(out["units"][1]["run_id"], "current-run")

    def test_real_journal_api_roundtrip_uses_original_id_time_without_rewriting(self):
        with tempfile.TemporaryDirectory(prefix="p18_mock_journal_") as directory:
            path = Path(directory) / "units.jsonl"
            first_journal = JOURNAL.Journal(str(path), "synthetic-fp")
            fresh, _ = self.collect(first_journal)
            initial = path.read_bytes()
            second_journal = JOURNAL.Journal(str(path), "synthetic-fp")
            b = SimpleNamespace(start_server=lambda *a, **kw: self.fail("transport used for cache"))
            cached = functions(B=b)["run_cond"]("a", 16000, 1, 0, 0, 2, second_journal)
            self.assertNotEqual(first_journal.run_id, second_journal.run_id)
            self.assertEqual(cached["unit_provenance"]["run_id"], first_journal.run_id)
            self.assertEqual(cached["unit_provenance"]["recorded_at"], fresh["unit_provenance"]["recorded_at"])
            self.assertTrue(cached["unit_provenance"]["reused"])
            self.assertEqual(path.read_bytes(), initial)

    def test_real_journal_does_not_store_incomplete_mock_unit(self):
        with tempfile.TemporaryDirectory(prefix="p18_mock_journal_") as directory:
            path = Path(directory) / "units.jsonl"
            journal = JOURNAL.Journal(str(path), "synthetic-fp")
            rec, _ = self.collect(journal, failed=True)
            self.assertFalse(path.exists())
            self.assertEqual(rec["unit_provenance"]["run_id"], journal.run_id)
            self.assertFalse(rec["unit_provenance"]["journaled"])


if __name__ == "__main__":
    unittest.main()
