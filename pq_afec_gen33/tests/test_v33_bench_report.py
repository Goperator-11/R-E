import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from experiments.v33 import bench_report as report


class BenchmarkReportTests(unittest.TestCase):
    def input_fixture(self, folder, structural=False):
        from experiments.v33 import bench
        root = Path(folder)
        policy = root / "policy"
        for package in ("afec", "padfec", "padfec3"):
            (policy / package).mkdir(parents=True)
            (policy / package / "__init__.py").write_text("", encoding="utf-8")
        protocol = self.protocol()
        if structural:
            protocol["oracle"] = {"stage_sizes": [2], "validation_samples": 2, "min_elimination_samples": 2,
                                  "max_parity": 0, "chunk_size": 2}
            protocol["scenarios"][0]["context"] = {"k": 2, "w": 1280, "p": 0, "cert_bytes": 2955,
                                                  "rtt_ms": 50, "uplink_mbps": 2}
            protocol["scenarios"][0]["phases"] = [{"length": 6, "p": 0}]
        protocol["generations"] = {"v31": {"source_root": str(policy)}}
        protocol["scenarios"][0]["world_params"] = {}
        protocol_path = root / "protocol.json"
        protocol_path.write_text(json.dumps(protocol), encoding="utf-8")
        sha = report.file_hash(protocol_path)
        fingerprint = bench.policy_source_fingerprints(protocol, ["v31"])
        raw = root / "raw"
        manifest = {"schema": "padfec.v33.benchmark_raw_manifest/1", "protocol_sha256": sha,
                    "mode": "full", "variant": "full", "generations": ["v31"], "scenarios": ["B1"],
                    "seeds": protocol["seeds"], "protocol": protocol,
                    "source_sha256": {name: report.file_hash(Path(report.__file__).with_name(name)) for name in report.RAW_SOURCES},
                    "policy_source_fingerprints": fingerprint}
        run_dir = raw / "v31/full/B1"
        run_dir.mkdir(parents=True)
        (raw / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        audit = {"source_root": str(policy.resolve()), "source_unchanged": True,
                 "source_sha256": {str(policy / path): value for path, value in fingerprint["v31"]["files"].items()}}
        cid = bench.context_id(bench.context_spec(protocol["scenarios"][0], protocol["scenarios"][0]["phases"][0]))
        for run in self.runs(protocol):
            for count in run["action_counts"]:
                count["context_id"] = cid
            trace = run_dir / f"seed{run['seed']:05d}.trace.jsonl.gz"
            with gzip.open(trace, "wt", encoding="utf-8") as stream:
                for row in self.trace(run):
                    row["context_id"] = cid
                    stream.write(json.dumps(row) + "\n")
            run.update(mode="full", protocol_sha256=sha, trace_path=str(trace), trace_sha256=report.file_hash(trace), policy_audit=audit)
            (run_dir / f"seed{run['seed']:05d}.json").write_text(json.dumps(run), encoding="utf-8")
        return protocol, protocol_path, raw, policy

    def protocol(self, family="B1", length=6):
        phases = [{"length": length, "p": .15}]
        context = {"cert_bytes": 9000}
        if family == "B5":
            phases = [{"length": 3, "p": .02}, {"length": length - 3, "p": .02, "cert_bytes": 16000}]
        return {"seeds": list(range(31, 51)), "scenarios": [{"id": family, "family": family, "context": context, "phases": phases}],
                "baseline_generations": ["v31", "v32"],
                "metrics": {"paired_confidence": .95, "adaptation_near_optimal_ms": .5, "adaptation_consecutive": 2, "p_bias_high_phase_last_n": 2},
                "thresholds": {"B1_regret_ms": .1, "B2_regret_ms": .5, "B1_abs_p_bias": .005,
                               "B4_extra_bytes": 1855, "B5_adaptation_connections": 2, "max_regression_vs_v31_ms": .5}}

    def table(self, action=(0, 0, 0), mean=.02, width=.01, **kwargs):
        return {"action": list(action), "reference_action": [0, 3, 1], "mean_gap_ms": mean,
                "gap_half_width_ms": width, "approximate": True, "uncertainty_resolved": width is not None,
                "zero_observed_variance": False, **kwargs}

    def reference(self, gap=.01):
        return {"chosen_action": [0, 3, 1], "selection_gap_upper_ms": gap, "uncertainty_resolved": gap is not None}

    def make_run(self, seed=31, generation="v31", scenario="B1", actions=None, length=6):
        actions = actions or [(0, 0, 0)] * length
        counts = {}
        for action in actions:
            counts[action] = counts.get(action, 0) + 1
        return {"seed": seed, "generation": generation, "variant": "full", "scenario": scenario, "n": len(actions),
                "action_counts": [{"context_id": "c", "action": list(action), "n": n} for action, n in counts.items()],
                "summary": {"mean_hct_ms": 60, "failure_rate": 0, "mean_extra_server_bytes": 10,
                            "mean_extra_first_flight_bytes": 8, "mean_extra_client_first_flight_bytes": 8,
                            "p_bias_high_phase": .001, "p_bias_high_phase_n": 2, "p_mae_high_phase": .002,
                            "alarm_rate_per_1000": 1, "guard_alarm_fraction": .01,
                            "longest_unchanged_action_run": 4, "transitions": []},
                "test_actions": actions}

    def trace(self, run):
        return [{"index": i, "context_id": "c", "action": list(action), "hct_ms": 60,
                 "b0_hct_ms": 70, "global_fixed_hct_ms": 55, "server_bytes": 100,
                 "b0_server_bytes": 90, "global_fixed_server_bytes": 110} for i, action in enumerate(run["test_actions"])]

    def runs(self, protocol, generation="v31", actions=None):
        scenario = protocol["scenarios"][0]
        length = sum(p["length"] for p in scenario["phases"])
        return [self.make_run(seed, generation, scenario["id"], actions=actions, length=length) for seed in protocol["seeds"]]

    def test_expected_gap_retains_negative_and_shared_mc_does_not_shrink(self):
        protocol = self.protocol()
        runs = self.runs(protocol)
        tables = {("c", (0, 0, 0)): self.table(mean=-.02, width=.03)}
        result = report.expected_regret(runs, {"c": self.reference(.04)}, tables)
        self.assertAlmostEqual(result["seed_summary"]["mean"], -.02)
        self.assertAlmostEqual(result["shared_mc_bound_ms"], .03)
        self.assertAlmostEqual(result["selection_gap_bound_ms"], .04)
        self.assertAlmostEqual(result["lower_bound_ms"], -.05)
        self.assertAlmostEqual(result["upper_bound_ms"], .05)

    def test_missing_table_never_uses_partial_seed_average(self):
        runs = [self.make_run(), self.make_run(32, actions=[(0, 1, 0)] * 6)]
        tables = {("c", (0, 0, 0)): self.table()}
        result = report.expected_regret(runs, {"c": self.reference()}, tables)
        self.assertEqual(result["status"], "pending")
        self.assertIsNone(result["seed_summary"]["mean"])
        self.assertIsNone(result["shared_mc_bound_ms"])
        self.assertEqual(len(result["missing"]), 1)

    def test_context_selection_bounds_follow_connection_weights(self):
        run = self.make_run(length=4)
        run["action_counts"] = [{"context_id": "c", "action": [0, 0, 0], "n": 3},
                                {"context_id": "d", "action": [0, 0, 0], "n": 1}]
        second = copy.deepcopy(run)
        second["seed"] = 32
        tables = {("c", (0, 0, 0)): self.table(mean=.2, width=.02),
                  ("d", (0, 0, 0)): self.table(mean=.6, width=.04)}
        result = report.expected_regret([run, second], {"c": self.reference(.1), "d": self.reference(.3)}, tables)
        self.assertAlmostEqual(result["seed_summary"]["mean"], .3)
        self.assertAlmostEqual(result["shared_mc_bound_ms"], .025)
        self.assertAlmostEqual(result["selection_gap_bound_ms"], .15)

    def test_unresolved_zero_variance_does_not_become_exact(self):
        table = self.table(width=0, zero_observed_variance=True, uncertainty_resolved=True)
        self.assertIsNone(report.gap_width(table))
        table.update(approximate=False, method="structural_zero_loss_pair")
        self.assertEqual(report.gap_width(table), 0)
        table.update(approximate=True, action=[0, 3, 1])
        self.assertEqual(report.gap_width(table), 0)

    def test_direct_contrast_cancels_oracle_and_skips_zero_mean_coefficients(self):
        a, b = (0, 0, 0), (0, 1, 0)
        candidate = [self.make_run(31, actions=[a] * 6), self.make_run(32, actions=[b] * 6)]
        baseline = [self.make_run(31, actions=[b] * 6), self.make_run(32, actions=[a] * 6)]
        tables = {("c", a): self.table(a, mean=1, width=None), ("c", b): self.table(b, mean=2, width=None)}
        result = report.direct_comparison(candidate, baseline, tables)
        self.assertEqual(result["seed_summary"]["mean"], 0)
        self.assertGreater(result["seed_summary"]["se"], 0)
        self.assertEqual(result["shared_mc_bound_ms"], 0)
        self.assertEqual(result["selection_gap_bound_ms"], 0)
        self.assertTrue(result["oracle_cancels"])

    def test_identical_actions_require_no_gap_table_for_direct_difference(self):
        runs = [self.make_run(31), self.make_run(32)]
        result = report.direct_comparison(runs, copy.deepcopy(runs), {})
        self.assertEqual(result["seed_summary"]["mean"], 0)
        self.assertEqual(result["shared_mc_bound_ms"], 0)
        self.assertEqual(result["missing"], [])

    def test_direct_bound_uses_absolute_coefficients(self):
        a, b = (0, 0, 0), (0, 1, 0)
        candidate = [self.make_run(31, actions=[a] * 6), self.make_run(32, actions=[a] * 6)]
        baseline = [self.make_run(31, actions=[b] * 6), self.make_run(32, actions=[b] * 6)]
        tables = {("c", a): self.table(a, mean=.2, width=.03), ("c", b): self.table(b, mean=.1, width=.04)}
        result = report.direct_comparison(candidate, baseline, tables)
        self.assertAlmostEqual(result["seed_summary"]["mean"], .1)
        self.assertAlmostEqual(result["shared_mc_bound_ms"], .07)

    def test_direct_comparison_rejects_context_or_seed_mismatch(self):
        a, b = self.make_run(), self.make_run()
        b["action_counts"][0]["context_id"] = "other"
        with self.assertRaises(ValueError):
            report.direct_comparison([a], [b], {})
        b = self.make_run(32)
        with self.assertRaises(ValueError):
            report.direct_comparison([a], [b], {})

    def test_near_optimal_three_valued_logic(self):
        row = {"context_id": "c", "action": [0, 0, 0]}
        refs = {"c": self.reference(.2)}
        table = {("c", (0, 0, 0)): self.table(mean=.2, width=.05)}
        self.assertTrue(report.near_optimal(row, refs, table, .5))
        refs["c"] = self.reference(.3)
        self.assertIsNone(report.near_optimal(row, refs, table, .5))
        table[("c", (0, 0, 0))] = self.table(mean=.6, width=.05)
        self.assertFalse(report.near_optimal(row, {}, table, .5))

    def test_suboptimal_episodes_distinguish_unknown_rows(self):
        a, b, u = (0, 0, 0), (0, 1, 0), (0, 2, 0)
        run = self.make_run(actions=[b, b, u, b, a, a])
        tables = {("c", a): self.table(a, mean=0, width=0), ("c", b): self.table(b, mean=1, width=.1)}
        protocol = self.protocol()
        result = report.trace_metrics(run, protocol["scenarios"][0], protocol, {"c": self.reference(0)}, tables, self.trace)
        self.assertEqual(result["longest_confirmed_suboptimal_episode"], 2)
        self.assertEqual(result["longest_possible_suboptimal_episode"], 4)
        self.assertEqual(result["unknown_cost_rows"], 1)
        self.assertEqual(result["fixed_comparators"]["b0"]["candidate_minus_fixed_ms"], -10)
        self.assertEqual(result["fixed_comparators"]["b0"]["candidate_minus_fixed_server_bytes"], 10)
        self.assertEqual(result["fixed_comparators"]["global_fixed_031"]["candidate_minus_fixed_server_bytes"], -10)

    def test_transition_display_keeps_censored_and_unqualified_denominators(self):
        runs = [self.make_run(31), self.make_run(32), self.make_run(33)]
        event = {"from_phase": 0, "to_phase": 1, "old_p": .02, "new_p": .15,
                 "detection_status": "detected", "detection_delay": 3, "detection_confirmed_delay": 7,
                 "detection_censored": False, "tracking_delay": 3, "tracking_censored": False}
        runs[0]["summary"]["transitions"] = [event]
        runs[1]["summary"]["transitions"] = [{**event, "detection_status": "right_censored", "detection_censored": True,
                                              "detection_delay": None, "detection_confirmed_delay": None,
                                              "tracking_delay": None, "tracking_censored": True}]
        runs[2]["summary"]["transitions"] = [{**event, "detection_status": "already_on_new_side", "detection_delay": None,
                                              "detection_confirmed_delay": None, "tracking_delay": 0}]
        value = report.transition_summary(runs)[0]
        self.assertEqual(value["n"], 3)
        self.assertEqual(value["detected_n"], 1)
        self.assertEqual(value["mean_detection_start_among_detected"], 3)
        self.assertEqual(value["detection_right_censored_n"], 1)
        self.assertEqual(value["prechange_unqualified_n"], 1)

    def test_markdown_exposes_observed_metrics_and_inference_scope(self):
        protocol = self.protocol()
        raw = self.runs(protocol) + self.runs(protocol, "v32")
        result = report.aggregate(raw, {"c": self.reference(0)}, {("c", (0, 0, 0)): self.table()}, protocol, self.trace)
        text = report.markdown(result)
        self.assertIn("0.001000", text)
        self.assertIn("alarm/1000", text)
        self.assertIn("정책−b0 서버 B", text)
        self.assertIn("전체 동시 95%", text)
        self.assertFalse(result["inference_scope"]["combined_bounds_are_simultaneous_95_percent"])

    def test_b5_unknown_early_window_is_inconclusive_not_failure(self):
        good, bad, unknown = (0, 0, 0), (0, 1, 0), (0, 2, 0)
        protocol = self.protocol("B5", length=10)
        run = self.make_run(scenario="B5", actions=[bad] * 3 + [unknown, unknown, unknown, good, good, good, good])
        tables = {("c", good): self.table(good, mean=0, width=0), ("c", bad): self.table(bad, mean=1, width=.1)}
        result = report.trace_metrics(run, protocol["scenarios"][0], protocol, {"c": self.reference(0)}, tables, self.trace)
        event = result["adaptation"][0]
        self.assertEqual(event["start_new_observations"], 3)
        self.assertEqual(event["threshold_status"], "inconclusive")

    def test_b5_known_late_start_fails_and_early_start_passes(self):
        good, bad = (0, 0, 0), (0, 1, 0)
        protocol = self.protocol("B5", length=10)
        tables = {("c", good): self.table(good, mean=0, width=0), ("c", bad): self.table(bad, mean=1, width=.1)}
        for late, expected in ((True, "fail"), (False, "pass")):
            run = self.make_run(scenario="B5", actions=[bad] * (6 if late else 5) + [good] * (4 if late else 5))
            result = report.trace_metrics(run, protocol["scenarios"][0], protocol, {"c": self.reference(0)}, tables, self.trace)
            self.assertEqual(result["adaptation"][0]["threshold_status"], expected)

    def test_b5_all_seed_rule_does_not_average_one_late_seed(self):
        good, bad = (0, 0, 0), (0, 1, 0)
        protocol = self.protocol("B5", length=10)
        protocol["baseline_generations"] = ["v31"]
        runs = self.runs(protocol, actions=[bad] * 3 + [good] * 7)
        runs[0] = self.make_run(31, scenario="B5", actions=[bad] * 6 + [good] * 4)
        tables = {("c", good): self.table(good, mean=0, width=0), ("c", bad): self.table(bad, mean=1, width=.1)}
        result = report.aggregate(runs, {"c": self.reference(0)}, tables, protocol, self.trace)
        gate = result["groups"][0]["gates"]["adaptation"]
        self.assertEqual(gate["status"], "fail")
        self.assertEqual(len(gate["confirmed_start_distribution"]), 20)
        self.assertLess(sum(gate["confirmed_start_distribution"]) / 20, 2)

    def test_full_and_diagnostic_variants_are_separate(self):
        protocol = self.protocol()
        runs = self.runs(protocol) + self.runs(protocol, "v32")
        diagnostics = copy.deepcopy(self.runs(protocol))
        for run in diagnostics:
            run["variant"] = "guard_off"
        result = report.aggregate(runs + diagnostics, {"c": self.reference(0)}, {("c", (0, 0, 0)): self.table(mean=.01, width=.01)}, protocol, self.trace)
        self.assertEqual(len(result["groups"]), 3)
        self.assertEqual({item["kind"] for item in result["comparisons"]}, {"generation_regression", "diagnostic_variant_contrast"})
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["noninferiority"]["v32"]["status"], "pass")

    def test_pending_expected_does_not_replace_with_realized_hct(self):
        protocol = self.protocol()
        result = report.aggregate(self.runs(protocol) + self.runs(protocol, "v32"), {}, {}, protocol, self.trace)
        self.assertEqual(result["status"], "partial")
        self.assertIsNone(result["groups"][0]["expected_regret"]["seed_summary"]["mean"])
        self.assertEqual(result["groups"][0]["observed"]["mean_hct_ms"]["mean"], 60)
        self.assertEqual(result["comparisons"][0]["realized_hct_diagnostic"]["mean"], 0)
        self.assertIn("partial", report.markdown(result))

    def test_missing_cell_does_not_erase_proven_noninferiority_failure(self):
        protocol = self.protocol()
        second = copy.deepcopy(protocol["scenarios"][0])
        second.update(id="B2", family="B2")
        protocol["scenarios"].append(second)
        a, b = (0, 0, 0), (0, 1, 0)
        runs = self.runs(protocol, "v31", actions=[a] * 6) + self.runs(protocol, "v32", actions=[b] * 6)
        tables = {("c", a): self.table(a, mean=0, width=0, approximate=False),
                  ("c", b): self.table(b, mean=1, width=0, approximate=False)}
        result = report.aggregate(runs, {"c": self.reference(0)}, tables, protocol, self.trace)
        self.assertEqual(result["status"], "partial")
        self.assertFalse(result["noninferiority"]["v32"]["all_cells_present"])
        self.assertEqual(result["noninferiority"]["v32"]["status"], "fail")

    def test_missing_seed_and_bad_counts_are_rejected(self):
        protocol = self.protocol()
        with self.assertRaises(ValueError):
            report.aggregate(self.runs(protocol)[:-1], {}, {}, protocol, self.trace)
        bad = self.make_run()
        bad["action_counts"][0]["n"] = 5
        with self.assertRaises(ValueError):
            report.weights(bad)

    def test_b4_uses_server_whole_connection_metric(self):
        protocol = self.protocol("B4")
        protocol["baseline_generations"] = ["v31"]
        runs = self.runs(protocol)
        for run in runs:
            run["summary"].update(mean_extra_server_bytes=2000, mean_extra_first_flight_bytes=10)
        result = report.aggregate(runs, {"c": self.reference(0)}, {("c", (0, 0, 0)): self.table()}, protocol, self.trace)
        self.assertEqual(result["groups"][0]["gates"]["server_extra_bytes"]["status"], "fail")

    def test_trace_loader_checks_counted_actions(self):
        run = self.make_run()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "trace.jsonl.gz"
            with gzip.open(path, "wt", encoding="utf-8") as stream:
                for row in self.trace(run):
                    stream.write(json.dumps(row) + "\n")
            run["trace_path"] = str(path)
            self.assertEqual(len(report.load_trace(run)), 6)
            run["action_counts"][0]["action"] = [1, 0, 0]
            with self.assertRaises(ValueError):
                report.load_trace(run)

    def test_cli_requires_allow_pending_and_creates_only_new_outputs(self):
        protocol = self.protocol()
        raw = self.runs(protocol) + self.runs(protocol, "v32")
        inputs = (protocol, raw, {}, {}, {"protocol_sha256": "synthetic", "reporting_rules_sha256": "synthetic"}, [])
        with tempfile.TemporaryDirectory() as folder:
            out, md = Path(folder) / "report.json", Path(folder) / "report.md"
            argv = ["--raw-dirs", folder, "--out", str(out), "--markdown", str(md)]
            with mock.patch.object(report, "load_inputs", return_value=inputs), mock.patch.object(report, "load_trace", side_effect=self.trace):
                with mock.patch.object(report, "aggregate", return_value=report.aggregate(raw, {}, {}, protocol, self.trace)):
                    with self.assertRaises(ValueError):
                        report.main(argv)
                    self.assertFalse(out.exists())
                    result = report.main(argv + ["--allow-pending"])
                    self.assertEqual(result["status"], "partial")
                    self.assertTrue(out.is_file())
                    self.assertTrue(md.is_file())
                    with self.assertRaises(ValueError):
                        report.main(argv + ["--allow-pending"])

    def test_input_loader_checks_frozen_policy_files_and_complete_seed_inventory(self):
        from experiments.v33 import bench
        with tempfile.TemporaryDirectory() as folder:
            protocol, path, raw, policy = self.input_fixture(folder)
            with mock.patch.object(bench, "load_protocol", return_value=protocol):
                loaded = report.load_inputs(path, [raw], [], [])
                self.assertEqual(len(loaded[1]), 20)
                self.assertEqual(len(loaded[4]["raw_summary_files"]), 20)
                self.assertEqual(len(loaded[4]["raw_trace_files"]), 20)
                (policy / "padfec3/__init__.py").write_text("changed", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "fingerprint"):
                    report.load_inputs(path, [raw], [], [])

    def test_input_loader_rejects_manifest_seed_subset_even_if_marked_full(self):
        from experiments.v33 import bench
        with tempfile.TemporaryDirectory() as folder:
            protocol, path, raw, _ = self.input_fixture(folder)
            manifest_path = raw / "manifest.json"
            manifest = report.read_json(manifest_path)
            manifest["seeds"] = [31]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with mock.patch.object(bench, "load_protocol", return_value=protocol):
                with self.assertRaisesRegex(ValueError, "entire frozen seed"):
                    report.load_inputs(path, [raw], [], [])

    def test_source_inventory_cannot_hide_a_changed_producer(self):
        sources = {name: report.file_hash(Path(report.__file__).with_name(name)) for name in report.RAW_SOURCES}
        report.source_check(sources, report.RAW_SOURCES)
        sources["bench.py"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "source differs"):
            report.source_check(sources, report.RAW_SOURCES)
        sources.pop("bench.py")
        with self.assertRaisesRegex(ValueError, "inventory"):
            report.source_check(sources, report.RAW_SOURCES)

    def test_loader_integrates_shared_oracle_validator_without_simulation(self):
        from experiments.v33 import bench, bench_oracles, oracle
        with tempfile.TemporaryDirectory() as folder:
            protocol, path, raw, _ = self.input_fixture(folder, structural=True)
            sha = report.file_hash(path)
            contexts = bench.all_contexts(protocol)
            cid, context = next(iter(contexts.items()))
            expected, spec, params, mixture, _ = bench_oracles._expected_result_contract(protocol, context, "build", None)
            sources = oracle._source_hashes()
            certificate = oracle._certificate(mixture, params, sources, spec)
            self.assertIsNotNone(certificate)
            reference = {**expected, "schema": oracle.SCHEMA, "status": "complete", "protocol_sha256": sha,
                         "context_id": cid, "job_id": cid, "source_hashes": sources,
                         "method": "structural_zero_loss_certificate", "approximate": False,
                         "validation_samples": 0, "model_kind": "independent_event_world",
                         "chosen_action": [0, 0, 0], "certificate": certificate, "uncertainty_resolved": True,
                         "confidence": None, "stage_results": [], "oracle_gap_upper_ms": 0.0, "selection_gap_upper_ms": 0.0}
            expected_action, action_spec, _, _, _ = bench_oracles._expected_result_contract(protocol, context, "actions", 1)
            job_id = cid + "_0_0_0"
            action = {**expected_action, "schema": oracle.SCHEMA, "status": "complete", "protocol_sha256": sha,
                      "context_id": cid, "job_id": job_id, "source_hashes": sources,
                      "method": "structural_zero_loss_pair", "approximate": False, "validation_samples": 0,
                      "action": [0, 0, 0], "reference_action": [0, 0, 0], "validation_seed": action_spec["validation_seed"],
                      "n": 0, "evaluation_family_size": 1, "certificate": certificate, "uncertainty_resolved": True,
                      "mean_gap_ms": 0, "gap_half_width_ms": 0, "zero_observed_variance": True}
            folders = []
            for mode, result, job in (("build", reference, {"context_id": cid, "job_id": cid}),
                                      ("actions", action, {"context_id": cid, "job_id": job_id, "action": [0, 0, 0], "reference_action": [0, 0, 0]})):
                destination = Path(folder) / mode
                (destination / "results").mkdir(parents=True)
                manifest = {"schema": "padfec.v33.oracle_jobs/1", "mode": mode, "protocol_sha256": sha,
                            "source_sha256": {name: report.file_hash(Path(report.__file__).with_name(name)) for name in bench_oracles.MANIFEST_SOURCES},
                            "jobs": [job], "evaluation_family_size": 1 if mode == "actions" else None,
                            "oracle_digests": {cid: report.digest(reference)} if mode == "actions" else {}}
                (destination / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
                (destination / "results" / (job["job_id"] + ".json")).write_text(json.dumps(result), encoding="utf-8")
                folders.append(destination)
            with mock.patch.object(bench, "load_protocol", return_value=protocol), mock.patch.object(oracle.World, "sample", side_effect=AssertionError("simulation forbidden")):
                loaded = report.load_inputs(path, [raw], [folders[0]], [folders[1]])
                self.assertEqual(loaded[2][cid]["chosen_action"], [0, 0, 0])
                self.assertEqual(loaded[3][(cid, (0, 0, 0))]["n"], 0)
                self.assertEqual(loaded[5], [])
                action["n"] = 2
                (folders[1] / "results" / (job_id + ".json")).write_text(json.dumps(action), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "oracle n differs"):
                    report.load_inputs(path, [raw], [folders[0]], [folders[1]])


if __name__ == "__main__":
    unittest.main()
