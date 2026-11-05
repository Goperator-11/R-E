import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from experiments.v33 import bench, bench_learning_l3_report as report


spec = importlib.util.spec_from_file_location("l1_report_fixture", Path(__file__).with_name("test_v33_learning_report.py"))
fixture_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture_module)


class MonitorReportTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture_module.LearningReportTests()

    def fixture(self, family="B1"):
        protocol, baseline, previous, references, tables = self.base.fixture(family)
        candidate = copy.deepcopy(previous)
        ablations = [[copy.deepcopy(row) for row in previous if row["observation_mode"] == "c1"] for _ in range(3)]
        return [protocol, baseline, previous, candidate, *ablations, references, tables]

    def trace(self, run):
        rows = self.base.trace(run)
        if run["analysis_role"] in ("l3", "guard", "record", "beta"):
            for index, row in enumerate(rows):
                disabled = run["analysis_role"] == "guard"
                reason = "disabled" if disabled else "no_ctx" if index == 0 else None
                result = None if reason else {"direction": 0, "reactive": run["observation_mode"] != "none", "action": "record"}
                row["observation_info"].update(monitor=result, monitor_reason=reason)
                row["decision"] = {"monitor_prediction": {"beta": 0}, "reeval_feedback_suppressed": not disabled and run["observation_mode"] != "none" and index > 0}
        return rows

    def aggregate(self, fixture):
        return report.aggregate(fixture[0], report.analysis_runs(*fixture[:7]), fixture[7], fixture[8], trace_loader=self.trace)

    def test_inventory_exact_roles_and_originals_unchanged(self):
        fixture = self.fixture()
        original = copy.deepcopy(fixture)
        runs = report.analysis_runs(*fixture[:7])
        self.assertEqual(len(runs), 22)
        self.assertEqual(len({row["generation"] for row in runs}), 11)
        self.assertEqual(fixture, original)
        for index in range(1, 7):
            for kind in ("omit", "duplicate", "smoke", "foreign_seed", "foreign_mode"):
                changed = copy.deepcopy(fixture[:7])
                values = changed[index]
                if kind == "omit":
                    values.pop()
                elif kind == "duplicate":
                    values.append(copy.deepcopy(values[0]))
                elif kind == "smoke":
                    values[0]["mode"] = "smoke"
                elif kind == "foreign_seed":
                    values[0]["seed"] = 99
                else:
                    values[0]["observation_mode"] = "ideal" if index >= 4 else "unexpected"
                with self.subTest(index=index, kind=kind), self.assertRaises(ValueError):
                    report.analysis_runs(*changed)

    def test_family_union_includes_every_ablation(self):
        fixture = self.fixture()
        runs = report.analysis_runs(*fixture[:7])
        names = sorted({row["generation"] for row in runs})
        for row in runs:
            self.base.replace_action(row, (names.index(row["generation"]), 0, 0))
        with mock.patch.object(bench, "all_contexts", return_value={"c": {}}):
            manifest = report.legacy.family_manifest(fixture[0], "1" * 64, runs, fixture[7])
        self.assertEqual(manifest["evaluation_family_size"], 11)
        self.assertEqual({tuple(job["action"]) for job in manifest["jobs"]}, {(i, 0, 0) for i in range(11)})
        self.assertEqual(len(manifest["raw_run_identities"]), 22)

    def test_full_size_inventory_groups_and_primary_scope(self):
        fixture = self.fixture()
        protocol = fixture[0]
        protocol["seeds"] = list(range(31, 51))
        protocol["scenarios"] = [{**protocol["scenarios"][0], "id": f"cell{i:02d}"} for i in range(15)]
        for index in range(1, 7):
            fixture[index] = [{**copy.deepcopy(row), "seed": seed, "scenario": scenario["id"]}
                              for row in fixture[index] if row["seed"] == 31
                              for scenario in protocol["scenarios"] for seed in protocol["seeds"]]
        self.assertEqual([len(values) for values in fixture[1:7]], [600, 900, 900, 300, 300, 300])
        result = self.aggregate(fixture)
        self.assertEqual((len(result["groups"]), len(result["comparisons"])), (165, 210))
        self.assertEqual(sum(row["primary"] for row in result["comparisons"]), 45)
        self.assertEqual(len(result["noninferiority"]), 14)
        monitors = [row["monitor_diagnostics"] for row in result["groups"] if row["monitor_diagnostics"] is not None]
        self.assertEqual(len(monitors), 90)
        self.assertEqual(sum(row["connections"] for row in monitors), 10800)
        self.assertEqual(sum(row["monitored"] for row in monitors), 7500)
        self.assertTrue(all(row["cell_count"] == 15 for row in result["noninferiority"].values()))

    def test_direct_step_contrasts_cancel_reference_and_share_mc(self):
        fixture = self.fixture()
        for index, action in ((2, (1, 0, 0)), (3, (5, 0, 0)), (4, (2, 0, 0)), (5, (3, 0, 0)), (6, (4, 0, 0))):
            for row in fixture[index]:
                self.base.replace_action(row, action)
        for index in range(1, 6):
            fixture[8]["c", (index, 0, 0)] = self.base.table((index, 0, 0), mean=.6 - .1 * index, width=.01 * index)
        fixture[7]["c"]["selection_gap_upper_ms"] = None
        result = self.aggregate(fixture)
        for candidate, baseline, mean, bound, kind in (
            ("l3_c1", "l1_c1", -.4, .06, "direct_previous_policy"),
            ("guard_c1", "l1_c1", -.1, .03, "ablation_step_contrast"),
            ("record_c1", "guard_c1", -.1, .05, "ablation_step_contrast"),
            ("beta_c1", "record_c1", -.1, .07, "ablation_step_contrast"),
            ("l3_c1", "beta_c1", -.1, .09, "ablation_step_contrast")):
            row = next(row for row in result["comparisons"] if row["candidate"]["generation"] == candidate and row["baseline"]["generation"] == baseline)
            self.assertAlmostEqual(row["seed_summary"]["mean"], mean)
            self.assertAlmostEqual(row["shared_mc_bound_ms"], bound)
            self.assertEqual(row["selection_gap_bound_ms"], 0)
            self.assertEqual(row["kind"], kind)
        self.assertTrue(all(row["expected_regret"]["upper_bound_ms"] is None for row in result["groups"]))

    def test_unknown_and_failed_intervals_remain_visible(self):
        fixture = self.fixture()
        fixture[8]["c", (0, 0, 0)] = self.base.table(width=None)
        self.assertTrue(all(row["shared_mc_bound_ms"] == 0 for row in self.aggregate(fixture)["comparisons"]))
        for row in fixture[3]:
            self.base.replace_action(row, (1, 0, 0))
        fixture[8]["c", (1, 0, 0)] = self.base.table((1, 0, 0), mean=2, width=.01)
        self.assertEqual(self.aggregate(fixture)["noninferiority"]["l3_none_vs_l1_none"]["status"], "inconclusive")
        fixture[8]["c", (0, 0, 0)] = self.base.table(width=.01)
        failed = self.aggregate(fixture)
        self.assertEqual(failed["noninferiority"]["l3_none_vs_l1_none"]["status"], "fail")
        self.assertIn("| fail |", report.markdown(failed))

    def test_monitor_diagnostics_keep_cold_failed_and_all_decision_denominators(self):
        runs = report.analysis_runs(*self.fixture()[:7])
        rows = self.trace(next(row for row in runs if row["generation"] == "l3_c1"))
        rows[1]["ok"] = False
        rows[1]["observation_info"]["monitor"].update(direction=1, action="action_model")
        rows[2]["observation_info"]["monitor"].update(direction=-1, action="shared_change")
        rows[3]["observation_info"]["monitor"]["action"] = "recovery"
        rows[3]["decision"]["monitor_prediction"]["beta"] = -.3
        value = report.monitor_diagnostics(rows)
        self.assertEqual((value["connections"], value["monitored"], value["skipped"], value["failed_monitored"]), (6, 5, 1, 1))
        self.assertEqual((value["alarms"], value["up"], value["down"]), (2, 1, 1))
        self.assertEqual([value[k] for k in ("action_model", "recovery", "shared_change")], [1, 1, 1])
        self.assertAlmostEqual(value["alarm_per_1000_all_decisions"], 2000 / 6)
        self.assertEqual(value["alarm_per_1000_monitored"], 400)
        self.assertAlmostEqual(value["mean_abs_beta_decision"], .05)
        self.assertEqual(value["maximum_abs_beta_decision"], .3)
        guard = report.monitor_diagnostics(self.trace(next(row for row in runs if row["generation"] == "guard_c1")))
        self.assertEqual(guard["alarm_per_1000_all_decisions"], 0)
        self.assertIsNone(guard["alarm_per_1000_monitored"])

    def test_b1_alarm_gate_is_separate_from_legacy_summary(self):
        result = self.aggregate(self.fixture())
        group = next(row for row in result["groups"] if row["generation"] == "l3_c1")
        self.assertEqual(group["observed"]["alarm_rate_per_1000"]["mean"], 1)
        self.assertEqual(group["gates"]["monitor_alarm"]["status"], "pass")
        self.assertEqual(group["monitor_diagnostics"]["all_decision_alarm_seed_summary"]["mean"], 0)
        exact = report.bench_report.threshold_from_summary({"mean": 1, "lower": 1, "upper": 1}, 1)
        self.assertEqual(exact["status"], "fail")

    def test_phase_gates_and_convergence_preserve_rules(self):
        for family in ("B3", "B4", "B5"):
            with self.subTest(family=family):
                result = self.aggregate(self.fixture(family))
                if family == "B5":
                    self.assertTrue(all(row["gates"]["adaptation"]["status"] == "pass" for row in result["groups"]))
                else:
                    self.assertTrue(all(row["p_convergence"]["predecision_tail_gate"]["status"] == "pass" for row in result["groups"]))

    def test_collection_completion_required_before_raw_access(self):
        with tempfile.TemporaryDirectory() as folder:
            plan = Path(folder) / "plan.json"
            bench.write_new(plan, {"jobs": []})
            with mock.patch.object(report, "COLLECTION_PLAN_SHA256", bench.file_hash(plan)), mock.patch.object(report, "check_sources"), mock.patch.object(report.legacy, "prepare_plan") as old, mock.patch.object(report.loader, "load_learning_runs") as new:
                with self.assertRaisesRegex(ValueError, "entire L3 collection"):
                    report.prepare_plan(plan, plan)
                old.assert_not_called()
                new.assert_not_called()

    def test_failed_incomplete_root_and_changed_sources_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            plan = root / "plan.json"
            bench.write_new(plan, {"jobs": [{}]})
            bench.write_new(root / "L3_full_v1.started.json", {})
            finish = root / "L3_full_v1.finished.json"
            for status, jobs, error in (("failed", 1, None), ("complete", 0, None), ("complete", 1, "failed")):
                finish.write_text(json.dumps({"status": status, "jobs": jobs, "expected_jobs": 1, "error": error}), encoding="utf-8")
                with self.subTest(status=status, jobs=jobs, error=error), mock.patch.object(report, "COLLECTION_PLAN_SHA256", bench.file_hash(plan)), self.assertRaises(ValueError):
                    report.collection_attestation(plan)
        report.check_sources()
        with mock.patch.dict(report.FROZEN, {"bench_learning_l3.py": "0" * 64}), self.assertRaises(ValueError):
            report.check_sources()
        with self.assertRaises(ValueError):
            report.merge_inputs({"a": "1"}, {"a": "2"})


if __name__ == "__main__":
    unittest.main()
