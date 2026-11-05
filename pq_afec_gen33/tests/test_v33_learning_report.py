import contextlib
import copy
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from experiments.v33 import bench, bench_action_pool as pool, bench_learning_report as report


class LearningReportTests(unittest.TestCase):
    def fixture(self, family="B1"):
        phases = [{"length": 6, "p": 0 if family in ("B3", "B4") else .15}]
        if family == "B5":
            phases = [{"length": 3, "p": .02}, {"length": 3, "p": .02, "cert_bytes": 16000}]
        protocol = {"seeds": [31, 32], "scenarios": [{"id": family, "family": family,
                    "context": {"cert_bytes": 9000}, "phases": phases}], "baseline_generations": ["v31", "v32"],
                    "oracle": {"confidence": .99},
                    "metrics": {"paired_confidence": .95, "adaptation_near_optimal_ms": .5,
                                "adaptation_consecutive": 2, "p_bias_high_phase_last_n": 2},
                    "thresholds": {"B1_regret_ms": .1, "B2_regret_ms": .5, "B1_abs_p_bias": .005,
                                   "B4_extra_bytes": 1855, "B5_adaptation_connections": 2,
                                   "max_regression_vs_v31_ms": .5}}
        baseline, current = [], []
        for generation, mode in [("v31", None), ("v32", None)] + [("current", mode) for mode in report.MODES]:
            for seed in protocol["seeds"]:
                run = {"generation": generation, "variant": "full", "seed": seed, "scenario": family,
                       "mode": "full", "n": 6, "action_counts": [{"context_id": "c", "action": [0, 0, 0], "n": 6}],
                       "summary": {"mean_hct_ms": 60, "failure_rate": 0, "mean_extra_server_bytes": 10,
                                   "mean_extra_first_flight_bytes": 8, "mean_extra_client_first_flight_bytes": 8,
                                   "p_bias_high_phase": .001, "p_bias_high_phase_n": 2, "p_mae_high_phase": .002,
                                   "alarm_rate_per_1000": 1, "guard_alarm_fraction": .01,
                                   "longest_unchanged_action_run": 6, "transitions": []},
                       "final_state": {"p_mean": .9}, "test_actions": [[0, 0, 0]] * 6}
                if mode is not None:
                    run["observation_mode"] = mode
                    current.append(run)
                else:
                    baseline.append(run)
        references = {"c": {"chosen_action": [0, 3, 1], "selection_gap_upper_ms": .01, "uncertainty_resolved": True}}
        return protocol, baseline, current, references, {("c", (0, 0, 0)): self.table()}

    def table(self, action=(0, 0, 0), mean=.02, width=.01):
        return {"action": list(action), "reference_action": [0, 3, 1], "mean_gap_ms": mean,
                "gap_half_width_ms": width, "approximate": True, "uncertainty_resolved": width is not None,
                "zero_observed_variance": False}

    def trace(self, run):
        rows = []
        for index, action in enumerate(run["test_actions"]):
            row = {"index": index, "context_id": "c", "action": action, "hct_ms": 60,
                   "b0_hct_ms": 70, "global_fixed_hct_ms": 55, "server_bytes": 100,
                   "b0_server_bytes": 90, "global_fixed_server_bytes": 110, "ok": True}
            if "observation_mode" in run:
                mode = run["observation_mode"]
                evidence = {"src": "none" if mode == "none" else "c1", "sent": 2, "lost": 0,
                            "bitmap": None if mode == "none" else [1, 1], "trunc": False}
                usable = mode != "none"
                row.update(observation_mode=mode, observer_diagnostics={"mode": mode, "usable": usable},
                           observation_info={"loss_update_kind": "datagram" if usable else "categorical",
                                             "loss_evidence_src": evidence["src"], "arrival_sent": 2, "arrival_lost": 0,
                                             "arrival_trunc": False, "arrival_usable": usable},
                           policy_observe_input={"optional": {"first_flight_evidence": evidence}})
            rows.append(row)
        return rows

    def replace_action(self, run, action):
        run["action_counts"] = [{"context_id": "c", "action": list(action), "n": 6}]
        run["test_actions"] = [list(action)] * 6

    def aggregate(self, fixture):
        return report.aggregate_learning(*fixture, trace_loader=self.trace)

    def test_modes_are_alias_copies_and_inventory_is_exact(self):
        protocol, baseline, current, _, _ = self.fixture()
        original = copy.deepcopy(current)
        runs = report.analysis_runs(protocol, baseline, current)
        self.assertEqual(len(runs), 10)
        self.assertEqual({run["generation"] for run in runs}, {"v31", "v32", *report.ALIASES.values()})
        self.assertEqual(current, original)
        for changed in (current[:-1], current + [current[0]], [{**current[0], "mode": "smoke"}] + current[1:]):
            with self.subTest(change=len(changed)), self.assertRaises(ValueError):
                report.analysis_runs(protocol, baseline, changed)

    def test_family_union_keeps_all_modes_baselines_and_reference_digests(self):
        protocol, baseline, current, references, _ = self.fixture()
        for run in baseline + current:
            index = (["v31", "v32"].index(run["generation"]) if run["generation"] != "current"
                     else 2 + list(report.MODES).index(run["observation_mode"]))
            self.replace_action(run, (index, 0, 0))
        runs = report.analysis_runs(protocol, baseline, current)
        with mock.patch.object(bench, "all_contexts", return_value={"c": {}}):
            manifest = report.family_manifest(protocol, "1" * 64, runs, references)
        self.assertEqual(manifest["evaluation_family_size"], 5)
        self.assertEqual({tuple(job["action"]) for job in manifest["jobs"]}, {(i, 0, 0) for i in range(5)})
        self.assertEqual(len(manifest["raw_run_identities"]), 10)
        self.assertEqual(manifest["oracle_digests"], {"c": bench.digest(references["c"])})
        self.assertTrue(all(job["reference_action"] == [0, 3, 1] for job in manifest["jobs"]))

    def test_family_requires_every_context_and_rejects_unknown_context(self):
        protocol, baseline, current, references, _ = self.fixture()
        runs = report.analysis_runs(protocol, baseline, current)
        with mock.patch.object(bench, "all_contexts", return_value={"c": {}, "d": {}}):
            with self.assertRaisesRegex(ValueError, "reference contexts"):
                report.family_manifest(protocol, "1" * 64, runs, references)
            with self.assertRaisesRegex(ValueError, "cover every context"):
                report.family_manifest(protocol, "1" * 64, runs, {**references, "d": references["c"]})
        with mock.patch.object(bench, "all_contexts", return_value={"d": {}}):
            with self.assertRaisesRegex(ValueError, "outside"):
                report.family_manifest(protocol, "1" * 64, runs, {"d": references["c"]})

    def test_shared_mc_and_selection_error_keep_frozen_arithmetic(self):
        fixture = self.fixture()
        fixture[3]["c"]["selection_gap_upper_ms"] = .04
        fixture[4]["c", (0, 0, 0)] = self.table(mean=-.02, width=.03)
        result = self.aggregate(fixture)
        self.assertEqual(len(result["groups"]), 5)
        self.assertEqual(len(result["comparisons"]), 7)
        for group in result["groups"]:
            gap = group["expected_regret"]
            self.assertAlmostEqual(gap["seed_summary"]["mean"], -.02)
            self.assertAlmostEqual(gap["shared_mc_bound_ms"], .03)
            self.assertAlmostEqual(gap["selection_gap_bound_ms"], .04)
            self.assertAlmostEqual(gap["upper_bound_ms"], .05)
        self.assertFalse(result["inference_scope"]["combined_bounds_are_simultaneous_95_percent"])

    def test_full_design_produces_1500_runs_75_groups_105_comparisons(self):
        protocol, baseline, current, references, tables = self.fixture()
        protocol["seeds"] = list(range(31, 51))
        protocol["scenarios"] = [{**protocol["scenarios"][0], "id": f"cell{index:02d}"} for index in range(15)]
        def expand(runs):
            return [{**copy.deepcopy(run), "seed": seed, "scenario": scenario["id"]}
                    for run in runs if run["seed"] == 31 for scenario in protocol["scenarios"] for seed in protocol["seeds"]]
        baseline, current = expand(baseline), expand(current)
        self.assertEqual((len(baseline), len(current)), (600, 900))
        result = report.aggregate_learning(protocol, baseline, current, references, tables, trace_loader=self.trace)
        self.assertEqual((len(result["groups"]), len(result["comparisons"])), (75, 105))
        self.assertEqual(sum(item["primary"] for item in result["comparisons"]), 30)
        self.assertEqual(sum(group["observation_diagnostics"]["connections"] for group in result["groups"]
                             if group["observation_diagnostics"] is not None), 5400)

    def test_direct_comparisons_cancel_reference_and_share_action_mc(self):
        fixture = self.fixture()
        for run in fixture[2]:
            if run["observation_mode"] == "c1":
                self.replace_action(run, (1, 0, 0))
        fixture[3]["c"]["selection_gap_upper_ms"] = None
        fixture[4]["c", (0, 0, 0)] = self.table(mean=.2, width=.03)
        fixture[4]["c", (1, 0, 0)] = self.table((1, 0, 0), mean=.1, width=.04)
        result = self.aggregate(fixture)
        comparison = next(item for item in result["comparisons"] if item["candidate"]["generation"] == "current_c1"
                          and item["baseline"]["generation"] == "current_none")
        self.assertAlmostEqual(comparison["seed_summary"]["mean"], -.1)
        self.assertAlmostEqual(comparison["shared_mc_bound_ms"], .07)
        self.assertEqual(comparison["selection_gap_bound_ms"], 0)
        self.assertEqual(comparison["regression_gate"]["status"], "pass")
        self.assertIsNone(next(group for group in result["groups"] if group["generation"] == "current_c1")["expected_regret"]["upper_bound_ms"])

    def test_unknown_interval_is_inconclusive_but_same_actions_cancel(self):
        fixture = self.fixture()
        fixture[4]["c", (0, 0, 0)] = self.table(width=None)
        result = self.aggregate(fixture)
        self.assertTrue(all(group["gates"]["regret"]["status"] == "inconclusive" for group in result["groups"]))
        self.assertTrue(all(item["shared_mc_bound_ms"] == 0 for item in result["comparisons"]))
        self.assertTrue(all(item["regression_gate"]["status"] == "pass" for item in result["comparisons"]))

    def test_prepost_and_w1_noninferiority_are_separate_and_c1_is_primary(self):
        fixture = self.fixture()
        for run in fixture[1]:
            if run["generation"] == "v32":
                self.replace_action(run, (1, 0, 0))
        fixture[4]["c", (1, 0, 0)] = self.table((1, 0, 0), mean=-1, width=.01)
        result = self.aggregate(fixture)
        self.assertEqual(result["noninferiority"]["pre_post_vs_v32"]["c1"]["status"], "fail")
        self.assertEqual(result["noninferiority"]["w1_noninferiority_vs_v31"]["c1"]["status"], "pass")
        self.assertEqual(sum(item["primary"] for item in result["comparisons"]), 2)
        self.assertTrue(all(item["ideal_is_privileged_diagnostic"] for item in result["comparisons"]
                            if item["candidate"]["generation"] == "current_ideal"))

    def test_b5_rule_and_cases_are_identical_to_frozen_aggregate(self):
        fixture = self.fixture("B5")
        result = self.aggregate(fixture)
        runs = report.analysis_runs(fixture[0], fixture[1], fixture[2])
        original = report.bench_report.aggregate(runs, fixture[3], fixture[4], fixture[0], trace_loader=self.trace)
        self.assertEqual([group["gates"]["adaptation"] for group in result["groups"]],
                         [group["gates"]["adaptation"] for group in original["groups"]])
        self.assertTrue(all(group["gates"]["adaptation"]["status"] == "pass" for group in result["groups"]))

    def test_b3_b4_convergence_uses_predecision_tail_not_final_state(self):
        for family in ("B3", "B4"):
            with self.subTest(family=family):
                fixture = self.fixture(family)
                result = self.aggregate(fixture)
                for group in result["groups"]:
                    value = group["p_convergence"]
                    self.assertEqual(value["predecision_tail_gate"]["status"], "pass")
                    self.assertEqual(value["final_post_observation_p_mean"]["mean"], .9)
                    self.assertEqual(value["predecision_tail_p_mean"]["mean"], .001)
                fixture[2][0]["summary"]["p_bias_high_phase_n"] = 1
                group = next(g for g in self.aggregate(fixture)["groups"] if g["generation"] == "current_none")
                self.assertEqual(group["p_convergence"]["predecision_tail_gate"]["status"], "inconclusive")

    def test_diagnostics_include_failures_unknown_and_all_lost_in_denominator(self):
        current = self.fixture()[2]
        run = next(run for run in current if run["observation_mode"] == "c1")
        rows = self.trace(run)[:3]
        rows[0]["ok"] = False
        rows[0]["policy_observe_input"]["optional"]["first_flight_evidence"].update(lost=2, bitmap=[0, 0])
        rows[0]["observation_info"]["arrival_lost"] = 2
        rows[0]["observer_diagnostics"].update(all_lost=True, feedback_received=False)
        rows[1]["observer_diagnostics"]["all_lost"] = None
        merged = report.merge_diagnostics([report.observation_diagnostics(rows, "c1")])
        self.assertEqual((merged["connections"], merged["failures"], merged["learned_all_lost_connections"]), (3, 1, 1))
        self.assertEqual(merged["datagram_likelihood_sent"], 6)
        self.assertEqual(merged["datagram_likelihood_lost"], 2)
        self.assertEqual(merged["confirmed_all_lost_connections"], 1)
        self.assertEqual(merged["unknown_all_lost_connections"], 2)
        values = merged["distributions"]["all_lost"]
        self.assertEqual({(item["present"], item["value"]) for item in values}, {(False, None), (True, None), (True, True)})
        self.assertTrue(all(item["fraction_all_connections"] == 1 / 3 for item in values))
        self.assertTrue(all(sum(item["n"] for item in values) == 3 for values in merged["distributions"].values()))

    def test_unusable_false_sentinel_never_confirms_not_all_lost(self):
        current = self.fixture()[2]
        for mode, reason in (("none", "disabled"), ("c1", "feedback_missing"), ("c1", "feedback_lost"),
                             ("c1", "receiver_capacity_censoring")):
            with self.subTest(mode=mode, reason=reason):
                run = next(run for run in current if run["observation_mode"] == mode)
                rows = self.trace(run)[:2]
                for row in rows:
                    row["observer_diagnostics"].update(usable=False, all_lost=False, reason=reason)
                    row["observation_info"].update(arrival_usable=False, loss_update_kind="categorical", loss_evidence_src="none")
                    row["policy_observe_input"]["optional"]["first_flight_evidence"].update(src="none", bitmap=None)
                value = report.merge_diagnostics([report.observation_diagnostics(rows, mode)])
                self.assertEqual(value["unknown_all_lost_connections"], 2)
                self.assertEqual(value["confirmed_all_lost_connections"], 0)
                self.assertEqual(value["confirmed_not_all_lost_connections"], 0)
                self.assertEqual(value["distributions"]["all_lost"], [{"present": True, "value": False, "n": 2, "fraction_all_connections": 1.0}])

    def test_none_nonzero_counts_and_censored_counts_are_not_datagram_evidence(self):
        fixture = self.fixture()
        rows = self.trace(fixture[2][0])[:1]
        self.assertEqual(report.observation_diagnostics(rows, "none")["datagram_likelihood_sent"], 0)
        rows = self.trace(next(r for r in fixture[2] if r["observation_mode"] == "c1"))[:1]
        rows[0]["policy_observe_input"]["optional"]["first_flight_evidence"]["trunc"] = True
        rows[0]["observation_info"].update(arrival_trunc=True, arrival_usable=False, loss_update_kind="categorical")
        self.assertEqual(report.observation_diagnostics(rows, "c1")["datagram_likelihood_sent"], 0)
        rows[0]["observation_info"]["loss_update_kind"] = "datagram"
        with self.assertRaisesRegex(ValueError, "routing"):
            report.observation_diagnostics(rows, "c1")

    def test_inputs_are_absolute_and_modified_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "input.json"
            bench.write_new(path, {"version": 1})
            hashes = {str(path.resolve()): bench.file_hash(path)}
            report.check_files(hashes)
            path.write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "input"):
                report.check_files(hashes)
            with self.assertRaisesRegex(ValueError, "absolute"):
                report.check_files({"relative.json": "a" * 64})

    def test_execution_metadata_retains_frozen_adapter_and_full_family(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "plan.json"
            saved = {"schema": report.PLAN_SCHEMA, "overlay_path": "overlay", "raw_dirs": ["raw"],
                     "manifest": {"source_sha256": {"a": "b"}, "evaluation_family_size": 81},
                     "protocol_path": "base.json", "protocol_sha256": "a" * 64, "inputs_sha256": {"input": "b" * 64},
                     "contexts_sha256": "c" * 64, "planner_sha256": "d" * 64, "loader_sha256": "e" * 64,
                     "raw_schema": "new schema", "validation": "strict loader", "overlay_sha256": "f" * 64,
                     "analysis_aliases": report.ALIASES}
            bench.write_new(path, saved)
            with mock.patch.object(report, "prepare_plan", return_value=(saved, (1, 2, 3, 4, 5))), \
                 mock.patch.object(pool, "_check_sources") as source, mock.patch.object(pool, "_check_inputs"):
                manifest, metadata, loaded = report.execution_plan(path, bench.file_hash(path))
                self.assertEqual(manifest["evaluation_family_size"], 81)
                self.assertEqual(metadata["adapter_sha256"], report.FROZEN_SOURCES["bench_action_pool.py"])
                self.assertEqual(metadata["planner_sha256"], "d" * 64)
                self.assertEqual(metadata["input_validation_schema"], "new schema")
                source.assert_called_once_with(metadata)
                self.assertEqual(loaded, (1, 2, 3, 4, 5))
            changed = {**saved, "planner_sha256": "0" * 64}
            with mock.patch.object(report, "prepare_plan", return_value=(changed, None)), self.assertRaisesRegex(ValueError, "reconstructed"):
                report.execution_plan(path, bench.file_hash(path))

    def test_execution_calls_frozen_pool_without_partitioning(self):
        manifest, metadata = {"evaluation_family_size": 81}, {"planner_sha256": "abc"}
        with mock.patch.object(report, "execution_plan", return_value=(manifest, metadata, None)), \
             mock.patch.object(pool, "run_pool", return_value={"status": "partial"}) as execute:
            result = report.run_family("plan", "sha", "out", workers=8, time_budget_seconds=300, resume=True)
        execute.assert_called_once_with("out", manifest, metadata, workers=8, time_budget_seconds=300, resume=True)
        self.assertEqual(result["status"], "partial")

    def receipt_fixture(self, folder):
        out = Path(folder)
        job = {"context_id": "c", "action": [0, 0, 0], "reference_action": [0, 3, 1], "job_id": "c_0_0_0"}
        manifest = {"jobs": [job], "evaluation_family_size": 1}
        metadata = {"adapter_sha256": "a" * 64, "inputs_sha256": {}}
        run_id, attempt_id = "00000000000000000001_" + "1" * 32, "00000000000000000002_" + "2" * 32
        shared = {"schema": pool.SCHEMA, "run_id": run_id, "execution_sha256": bench.digest(metadata)}
        started = {**shared, "adapter_sha256": metadata["adapter_sha256"], "started_ns": 10}
        finished = {**shared, "status": "complete", "evaluation_family_size": 1, "complete_jobs": [job["job_id"]],
                    "pending_jobs": [], "failed_jobs": [], "finished_ns": 100}
        result_path, checkpoint_path = pool._job_paths(out, job["job_id"])
        bench.write_new(result_path, self.table())
        run_start, run_finish = out / "runs" / f"{run_id}.started.json", out / "runs" / f"{run_id}.finished.json"
        attempt_start = out / "attempts" / f"{job['job_id']}.{attempt_id}.started.json"
        attempt_finish = out / "attempts" / f"{job['job_id']}.{attempt_id}.finished.json"
        attempt = {**shared, "job": job, "pid": 123, "started_ns": 20}
        bench.write_new(run_start, started)
        bench.write_new(run_finish, finished)
        bench.write_new(attempt_start, {**attempt, "input_checkpoint_sha256": None})
        bench.write_new(attempt_finish, {**attempt, "status": "complete", "started_sha256": bench.file_hash(attempt_start),
                                        "result_sha256": bench.file_hash(result_path), "checkpoint_sha256": None, "finished_ns": 80})
        bench.write_new(out / "manifest.json", manifest)
        bench.write_new(out / "execution.json", metadata)
        return manifest, metadata, {"run_start": run_start, "run_finish": run_finish,
                                    "attempt_start": attempt_start, "attempt_finish": attempt_finish,
                                    "result": result_path, "checkpoint": checkpoint_path}

    def validate_receipts(self, out, manifest, metadata):
        with mock.patch.object(pool, "_load_execution", return_value=(manifest, metadata, {}, {"c": {}})), \
             mock.patch.object(pool, "_check_sources"), mock.patch.object(pool, "_check_inputs"), \
             mock.patch.object(pool, "_validate_result") as validator:
            result = report.validate_pool_locked(out, manifest, metadata)
            validator.assert_called_once()
            return result

    def change_json(self, path, update):
        value = pool.read_json(path)
        value.update(update)
        path.write_bytes(bench.canonical(value))

    def test_final_attestation_binds_every_receipt_result_and_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest, metadata, paths = self.receipt_fixture(folder)
            tables, receipt = self.validate_receipts(folder, manifest, metadata)
            self.assertEqual(set(tables), {("c", (0, 0, 0))})
            self.assertEqual(receipt["evaluation_family_size"], 1)
            self.assertEqual(len(receipt["files_sha256"]), 7)
            self.assertIn(str(paths["attempt_start"].resolve()), receipt["files_sha256"])

    def test_final_receipts_reject_failure_missing_pair_unknown_jobs_and_run(self):
        cases = [("run_finish", {"status": "failed"}), ("run_finish", {"pending_jobs": ["unknown"]}),
                 ("attempt_finish", {"run_id": "unknown"}), ("attempt_finish", {"finished_ns": 101}),
                 ("attempt_finish", {"status": "failed"}), ("run_start", {"execution_sha256": "bad"})]
        for key, change in cases:
            with self.subTest(key=key, change=change), tempfile.TemporaryDirectory() as folder:
                manifest, metadata, paths = self.receipt_fixture(folder)
                self.change_json(paths[key], change)
                with self.assertRaises(ValueError):
                    self.validate_receipts(folder, manifest, metadata)
        with tempfile.TemporaryDirectory() as folder:
            manifest, metadata, paths = self.receipt_fixture(folder)
            paths["attempt_finish"].unlink()
            with self.assertRaisesRegex(ValueError, "unmatched"):
                self.validate_receipts(folder, manifest, metadata)

    def test_result_and_checkpoint_corruption_and_start_hash_are_rejected(self):
        for kind in ("result", "checkpoint", "start_hash"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                manifest, metadata, paths = self.receipt_fixture(folder)
                if kind == "result":
                    self.change_json(paths["result"], {"mean_gap_ms": 1000})
                elif kind == "checkpoint":
                    bench.write_new(paths["checkpoint"], {"unexpected": True})
                else:
                    self.change_json(paths["attempt_finish"], {"started_sha256": "bad"})
                with self.assertRaisesRegex(ValueError, "hash"):
                    self.validate_receipts(folder, manifest, metadata)

    def test_completed_result_without_attempts_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest, metadata, paths = self.receipt_fixture(folder)
            paths["attempt_start"].unlink()
            paths["attempt_finish"].unlink()
            with self.assertRaisesRegex(ValueError, "missing"):
                self.validate_receipts(folder, manifest, metadata)

    def test_final_publication_holds_pool_lock_and_rechecks_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pool_dir = root / "pool"
            pool_dir.mkdir()
            evidence = root / "evidence.json"
            bench.write_new(evidence, {"verified": True})
            hashes = {str(evidence.resolve()): bench.file_hash(evidence)}
            held = []
            @contextlib.contextmanager
            def lock(path):
                self.assertEqual(path, pool_dir / "pool.lock")
                held.append(True)
                try:
                    yield
                finally:
                    held.pop()
            def execution(*args):
                self.assertTrue(held)
                return {"evaluation_family_size": 81}, {"inputs_sha256": hashes}, (1, 2, 3, 4, {"complete": True})
            def attestation(*args):
                self.assertTrue(held)
                return {}, {"files_sha256": hashes}
            aggregate = {"status": "complete", "missing": [], "missing_raw_groups": []}
            with mock.patch.object(pool, "exclusive_lock", side_effect=lock), \
                 mock.patch.object(report, "execution_plan", side_effect=execution), \
                 mock.patch.object(report, "validate_pool_locked", side_effect=attestation), \
                 mock.patch.object(report, "aggregate_learning", return_value=aggregate), \
                 mock.patch.object(pool, "_check_sources"), mock.patch.object(pool, "_check_inputs") as inputs:
                output = root / "report.json"
                report.final_report("family", "a" * 64, pool_dir, output)
                self.assertEqual(inputs.call_count, 2)
                self.assertEqual(pool.read_json(output)["evaluation_family_size"], 81)
                publication = pool.read_json(Path(str(output) + ".published.json"))
                self.assertEqual(publication["schema"], report.PUBLICATION_SCHEMA)
                self.assertEqual(publication["artifacts_sha256"], {str(output.resolve()): bench.file_hash(output)})
                self.assertEqual(publication["input_inventory_sha256"], bench.digest(hashes))
                self.assertFalse(held)
                with self.assertRaisesRegex(ValueError, "new files"):
                    report.final_report("family", "a" * 64, pool_dir, output)

    def test_markdown_failure_preserves_json_without_publication_marker(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pool_dir = root / "pool"
            pool_dir.mkdir()
            evidence = root / "evidence.json"
            bench.write_new(evidence, {"verified": True})
            hashes = {str(evidence.resolve()): bench.file_hash(evidence)}
            metadata = {"inputs_sha256": hashes}
            aggregate = {"status": "complete", "missing": [], "missing_raw_groups": []}
            with mock.patch.object(report, "execution_plan", return_value=({"evaluation_family_size": 81}, metadata, (1, 2, 3, 4, {}))), \
                 mock.patch.object(report, "validate_pool_locked", return_value=({}, {"files_sha256": hashes})), \
                 mock.patch.object(report, "aggregate_learning", return_value=aggregate), \
                 mock.patch.object(pool, "_check_sources"), mock.patch.object(pool, "_check_inputs"), \
                 mock.patch.object(report, "markdown", side_effect=OSError("failed markdown output")):
                output = root / "report.json"
                with self.assertRaisesRegex(OSError, "failed markdown"):
                    report.final_report("family", "a" * 64, pool_dir, output, root / "md" / "report.md")
                self.assertTrue(output.is_file())
                self.assertFalse(Path(str(output) + ".published.json").exists())

    def test_markdown_keeps_observed_and_direct_uncertainty_diagnostics(self):
        value = report.markdown(self.aggregate(self.fixture("B4")))
        for required in ("seed 구간", "합성 경계", "실현 HCT 차이", "서버 추가 B", "p 편향", "마지막 관측 뒤 p",
                         "전체 연결", "전멸 미확인", "0.5ms 비열등 통과는 개선 입증을 뜻하지 않는다"):
            self.assertIn(required, value)


if __name__ == "__main__":
    unittest.main()
