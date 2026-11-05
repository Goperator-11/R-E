import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from experiments.v33 import bench, bench_learning_l5_report as report


spec = importlib.util.spec_from_file_location("l1_report_fixture", Path(__file__).with_name("test_v33_learning_report.py"))
fixture_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture_module)


class PreservedDirectory:
    def __init__(self):
        self.name = tempfile.mkdtemp(prefix="padfec-test-")

    def __enter__(self):
        return self.name

    def __exit__(self, *args):
        return False

    def cleanup(self):
        pass


class JointLearningReportTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture_module.LearningReportTests()

    def fixture(self, family="B1"):
        protocol, baseline, previous, references, tables = self.base.fixture(family)
        candidate = copy.deepcopy(previous)
        fixed = [copy.deepcopy(row) for row in previous if row["observation_mode"] != "ideal"]
        return protocol, baseline, previous, candidate, fixed, references, tables

    def trace(self, run):
        return self.base.trace(run)

    def aggregate(self, fixture):
        protocol, baseline, previous, candidate, fixed, references, tables = fixture
        runs = report.analysis_runs(protocol, baseline, previous, candidate, fixed)
        return report.aggregate(protocol, runs, references, tables, trace_loader=self.trace)

    def test_inventory_binds_each_role_without_mutating_raw(self):
        fixture = self.fixture()
        original = copy.deepcopy(fixture)
        runs = report.analysis_runs(*fixture[:5])
        self.assertEqual(len(runs), 20)
        self.assertEqual(len({row["generation"] for row in runs}), 10)
        self.assertEqual(fixture, original)
        for index in range(1, 5):
            for kind in ("omit", "duplicate", "smoke", "foreign_seed", "foreign_mode"):
                changed = copy.deepcopy(list(fixture[:5]))
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
                    values[0]["observation_mode"] = "ideal" if index == 4 else "unexpected"
                with self.subTest(index=index, kind=kind), self.assertRaises(ValueError):
                    report.analysis_runs(*changed)

    def test_joint_family_contains_all_role_actions(self):
        fixture = self.fixture()
        runs = report.analysis_runs(*fixture[:5])
        names = sorted({row["generation"] for row in runs})
        for row in runs:
            self.base.replace_action(row, (names.index(row["generation"]), 0, 0))
        with mock.patch.object(bench, "all_contexts", return_value={"c": {}}):
            manifest = report.legacy.family_manifest(fixture[0], "1" * 64, runs, fixture[5])
        self.assertEqual(manifest["evaluation_family_size"], 10)
        self.assertEqual({tuple(job["action"]) for job in manifest["jobs"]}, {(i, 0, 0) for i in range(10)})
        self.assertEqual(len(manifest["raw_run_identities"]), 20)

    def test_full_size_roles_and_all_planned_comparisons(self):
        fixture = list(self.fixture())
        protocol = fixture[0]
        protocol["seeds"] = list(range(31, 51))
        protocol["scenarios"] = [{**protocol["scenarios"][0], "id": f"cell{i:02d}"} for i in range(15)]
        for index in range(1, 5):
            fixture[index] = [{**copy.deepcopy(row), "seed": seed, "scenario": scenario["id"]}
                              for row in fixture[index] if row["seed"] == 31
                              for scenario in protocol["scenarios"] for seed in protocol["seeds"]]
        self.assertEqual([len(values) for values in fixture[1:5]], [600, 900, 900, 600])
        result = self.aggregate(fixture)
        self.assertEqual((len(result["groups"]), len(result["comparisons"])), (150, 210))
        self.assertEqual(sum(row["primary"] for row in result["comparisons"]), 30)
        self.assertEqual(len(result["noninferiority"]), 14)
        self.assertTrue(all(row["cell_count"] == 15 for row in result["noninferiority"].values()))
        self.assertEqual(sum(row["observation_diagnostics"] is not None for row in result["groups"]), 120)

    def test_three_contrasts_use_direct_differences_and_shared_mc(self):
        fixture = self.fixture()
        for index, action in ((2, (1, 0, 0)), (3, (2, 0, 0)), (4, (3, 0, 0))):
            for row in fixture[index]:
                self.base.replace_action(row, action)
        for index, mean, width in ((1, .4, .03), (2, .1, .04), (3, .2, .02)):
            fixture[6]["c", (index, 0, 0)] = self.base.table((index, 0, 0), mean=mean, width=width)
        fixture[5]["c"]["selection_gap_upper_ms"] = None
        result = self.aggregate(fixture)
        for candidate, baseline, mean, bound, kind in (
            ("l5_c1", "l1_c1", -.3, .07, "direct_previous_policy"),
            ("l5_c1", "single_c1", -.1, .06, "mixture_change_contrast"),
            ("single_c1", "l1_c1", -.2, .05, "response_geometry_contrast")):
            row = next(row for row in result["comparisons"] if row["candidate"]["generation"] == candidate and row["baseline"]["generation"] == baseline)
            self.assertAlmostEqual(row["seed_summary"]["mean"], mean)
            self.assertAlmostEqual(row["shared_mc_bound_ms"], bound)
            self.assertEqual(row["selection_gap_bound_ms"], 0)
            self.assertEqual(row["kind"], kind)
            self.assertEqual(row["regression_gate"]["status"], "pass")
        self.assertTrue(all(row["expected_regret"]["upper_bound_ms"] is None for row in result["groups"]))

    def test_unknown_and_failed_bounds_are_not_hidden(self):
        fixture = self.fixture()
        fixture[6]["c", (0, 0, 0)] = self.base.table(width=None)
        same = self.aggregate(fixture)
        self.assertTrue(all(row["shared_mc_bound_ms"] == 0 for row in same["comparisons"]))
        for row in fixture[3]:
            self.base.replace_action(row, (1, 0, 0))
        fixture[6]["c", (1, 0, 0)] = self.base.table((1, 0, 0), mean=2, width=.01)
        unknown = self.aggregate(fixture)
        self.assertEqual(unknown["noninferiority"]["l5_none_vs_l1_none"]["status"], "inconclusive")
        fixture[6]["c", (0, 0, 0)] = self.base.table(width=.01)
        failed = self.aggregate(fixture)
        self.assertEqual(failed["noninferiority"]["l5_none_vs_l1_none"]["status"], "fail")
        self.assertEqual(failed["noninferiority"]["l5_c1_vs_l1_c1"]["status"], "fail")
        self.assertIn("| fail |", report.markdown(failed))

    def test_phase_gates_and_convergence_preserve_existing_rules(self):
        for family in ("B3", "B4", "B5"):
            with self.subTest(family=family):
                result = self.aggregate(self.fixture(family))
                if family == "B5":
                    self.assertTrue(all(row["gates"]["adaptation"]["status"] == "pass" for row in result["groups"]))
                else:
                    self.assertTrue(all(row["p_convergence"]["predecision_tail_gate"]["status"] == "pass" for row in result["groups"]))
                    self.assertTrue(all(row["p_convergence"]["final_post_observation_p_mean"]["mean"] == .9 for row in result["groups"]))

    def test_collection_missing_completion_stops_before_raw_load(self):
        with PreservedDirectory() as folder:
            plan = Path(folder) / "plan.json"
            bench.write_new(plan, {"jobs": []})
            with mock.patch.object(report, "COLLECTION_PLAN_SHA256", bench.file_hash(plan)), mock.patch.object(report, "check_sources"), mock.patch.object(report.legacy, "prepare_plan") as old, mock.patch.object(report.loader, "load_learning_runs") as new:
                with self.assertRaisesRegex(ValueError, "entire L5 collection"):
                    report.prepare_plan(plan, plan)
                old.assert_not_called()
                new.assert_not_called()

    def test_collection_rejects_failed_or_incomplete_root(self):
        with PreservedDirectory() as folder:
            root = Path(folder)
            plan = root / "plan.json"
            bench.write_new(plan, {"jobs": [{}]})
            bench.write_new(root / "L5_full_v1.started.json", {})
            finish = root / "L5_full_v1.finished.json"
            for status, jobs, error in (("failed", 1, None), ("complete", 0, None), ("complete", 1, "failed")):
                finish.write_text(json.dumps({"status": status, "jobs": jobs, "expected_jobs": 1, "error": error}), encoding="utf-8")
                with self.subTest(status=status, jobs=jobs, error=error), mock.patch.object(report, "COLLECTION_PLAN_SHA256", bench.file_hash(plan)), self.assertRaises(ValueError):
                    report.collection_attestation(plan)

    def test_input_inventory_conflicts_and_frozen_sources(self):
        self.assertEqual(report.merge_inputs({"a": "1"}, {"a": "1", "b": "2"}), {"a": "1", "b": "2"})
        with self.assertRaises(ValueError):
            report.merge_inputs({"a": "1"}, {"a": "2"})
        report.check_sources()
        with mock.patch.dict(report.FROZEN, {"bench_learning_l5.py": "0" * 64}), self.assertRaises(ValueError):
            report.check_sources()


if __name__ == "__main__":
    unittest.main()
