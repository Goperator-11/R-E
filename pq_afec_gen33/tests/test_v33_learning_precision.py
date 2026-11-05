import contextlib
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from experiments.v33 import bench, bench_action_pool as pool, oracle
from experiments.v33 import bench_learning_precision as precision
from experiments.v33 import bench_learning_report as reporting


class PrecisionTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(oracle.World, "sample", side_effect=AssertionError("no world sampling in precision units"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, path, value):
        bench.write_new(path, value)
        return str(path.resolve()), bench.file_hash(path)

    def rewrite(self, path, value):
        Path(path).write_bytes(precision.json_bytes(value))

    def original(self, root):
        protocol = {"oracle": {"validation_samples": 131072, "validation_seed": 850001,
                               "selection_seed": 840001, "confidence": .99},
                    "scenarios": [], "seeds": list(range(20)), "thresholds": {"limit": .5},
                    "world": {"immutable": True}}
        context = {"context": {"p": .02}, "mixture": [], "world_params": {}}
        contexts = {f"c{index:02d}": context for index in range(19)}
        references = {cid: {"chosen_action": [0, 3, 1], "selection_gap_upper_ms": None} for cid in contexts}
        jobs, tables = [], {}
        for index in range(100):
            cid, action = f"c{index % 19:02d}", [index, 0, 0]
            job = {"context_id": cid, "action": action, "reference_action": [0, 3, 1],
                   "job_id": cid + "_" + "_".join(map(str, action))}
            jobs.append(job)
            structural = index >= 84
            tables[cid, tuple(action)] = {"method": "structural_zero_loss_pair" if structural else "independent_paired_validation",
                                        "n": 0 if structural else 131072}
        identities = [["synthetic", "full", "B1", index] for index in range(1500)]
        manifest = {"schema": "padfec.v33.oracle_jobs/1", "mode": "actions", "protocol_sha256": precision.ORIGINAL_PROTOCOL_SHA256,
                    "source_sha256": pool._sources(), "jobs": jobs, "evaluation_family_size": 100,
                    "raw_run_identities": identities, "oracle_digests": {cid: bench.digest(value) for cid, value in references.items()}}
        base_path = root / "base.json"
        evidence_path = root / "raw_evidence.json"
        family_path = root / "original_family.json"
        report_path = root / "original_report.json"
        markdown_path = root / "original.md"
        decision_path = root / "decision.md"
        old_pool = root / "original_pool"
        old_pool.mkdir()
        self.write(base_path, protocol)
        self.write(evidence_path, {"unchanged": True})
        self.write(family_path, {"fixture": "family"})
        markdown_path.write_text("original", encoding="utf-8")
        decision_path.write_text("fixed target, no repeated stopping", encoding="utf-8")
        inputs = dict([self.write(root / "attested.json", {"complete": True})])
        metadata = {"inputs_sha256": {str(evidence_path): bench.file_hash(evidence_path)}, "protocol_path": str(base_path),
                    "protocol_sha256": precision.ORIGINAL_PROTOCOL_SHA256}
        provenance = {"complete": True, "inputs_sha256": metadata["inputs_sha256"]}
        loaded = (protocol, [{}] * 600, [{}] * 900, references, provenance)
        attestation = {"pool_path": str(old_pool), "evaluation_family_size": 100,
                       "validated_run_ids": ["synthetic"], "files_sha256": inputs,
                       "execution_content_sha256": bench.digest(metadata), "manifest_content_sha256": bench.digest(manifest)}
        original_report = {"schema": reporting.REPORT_SCHEMA, "status": "complete", "missing": [], "missing_raw_groups": [],
                           "evaluation_family_size": 100, "analysis_aliases": reporting.ALIASES,
                           "comparison_plan": [list(pair) for pair in reporting.PAIRS],
                           "provenance": {"family_plan_path": str(family_path), "family_plan_sha256": bench.file_hash(family_path),
                                          "reporter_sha256": precision.REPORTER_SHA256, "frozen_sources": reporting.FROZEN_SOURCES,
                                          "learning_inputs": provenance, "action_pool": attestation}}
        self.write(report_path, original_report)
        artifacts = {str(report_path): bench.file_hash(report_path), str(markdown_path): bench.file_hash(markdown_path)}
        publication = {"schema": reporting.PUBLICATION_SCHEMA, "status": "complete", "published_ns": 123,
                       "family_plan_path": str(family_path), "family_plan_sha256": bench.file_hash(family_path),
                       "reporter_sha256": precision.REPORTER_SHA256, "input_inventory_sha256": bench.digest(metadata["inputs_sha256"]),
                       "execution_content_sha256": bench.digest(metadata), "pool_attestation_sha256": bench.digest(attestation),
                       "artifacts_sha256": artifacts}
        publication_path = Path(str(report_path) + ".published.json")
        self.write(publication_path, publication)
        all_inputs = precision.merge_inputs(metadata["inputs_sha256"], artifacts, inputs,
                            {str(family_path): bench.file_hash(family_path), str(publication_path): bench.file_hash(publication_path),
                             str(decision_path): bench.file_hash(decision_path), str(precision.PATH): precision.IMPORTED_SHA256})
        result = {"manifest": manifest, "metadata": metadata, "loaded": loaded,
                  "family_path": str(family_path), "family_sha256": bench.file_hash(family_path),
                  "report_path": str(report_path), "report_sha256": bench.file_hash(report_path),
                  "publication_path": str(publication_path), "publication_sha256": bench.file_hash(publication_path),
                  "decision_path": str(decision_path), "decision_sha256": bench.file_hash(decision_path),
                  "pool_path": str(old_pool), "pool_attestation_sha256": bench.digest(attestation),
                  "partition": precision.result_partition(manifest, tables), "inputs_sha256": all_inputs}
        return result, contexts, tables, attestation, original_report, publication

    @contextlib.contextmanager
    def pin_fixture(self, original):
        with mock.patch.multiple(precision, ORIGINAL_FAMILY_SHA256=original["family_sha256"],
                                 ORIGINAL_REPORT_SHA256=original["report_sha256"],
                                 ORIGINAL_PUBLICATION_SHA256=original["publication_sha256"]):
            yield

    def frozen_plan(self, root, original, contexts):
        path, effective = root / "precision_plan.json", root / "effective.json"
        with mock.patch.object(precision, "load_original", return_value=original), \
             mock.patch.object(bench, "all_contexts", return_value=contexts):
            saved = precision.freeze_plan(original["family_path"], original["family_sha256"], original["report_path"],
                                          original["decision_path"], effective, path)
        return path, saved

    def test_effective_protocol_changes_only_fixed_n_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as folder:
            original, contexts, *_ = self.original(Path(folder))
            base = original["loaded"][0]
            before = copy.deepcopy(base)
            effective = precision.effective_protocol(base)
            self.assertEqual(base, before)
            self.assertEqual(effective["oracle"]["validation_samples"], 1048576)
            with mock.patch.object(bench, "all_contexts", return_value=contexts):
                precision.validate_effective_protocol(base, effective)
                for section, key, value in (("oracle", "validation_samples", 2097152), ("oracle", "validation_seed", 850002),
                                             ("oracle", "confidence", .95), ("thresholds", "limit", 1), ("world", "immutable", False)):
                    with self.subTest(section=section, key=key):
                        changed = copy.deepcopy(effective)
                        changed[section][key] = value
                        with self.assertRaisesRegex(ValueError, "only the fixed"):
                            precision.validate_effective_protocol(base, changed)
                changed = copy.deepcopy(effective)
                changed["seeds"].pop()
                with self.assertRaises(ValueError):
                    precision.validate_effective_protocol(base, changed)

    def test_original_publication_binds_artifacts_source_inventory_and_raw_counts(self):
        with tempfile.TemporaryDirectory() as folder:
            original, _, _, _, value, publication = self.original(Path(folder))
            args = (Path(original["report_path"]), Path(original["family_path"]), original["family_sha256"],
                    original["metadata"], original["loaded"])
            with self.pin_fixture(original), mock.patch.object(reporting, "analysis_runs") as inventory:
                precision.validate_original_publication(publication, value, *args)
                inventory.assert_called_once_with(*original["loaded"][:3])
                for key, changed in (("schema", "bad"), ("status", "partial"), ("family_plan_sha256", "bad"),
                                     ("input_inventory_sha256", "bad"), ("pool_attestation_sha256", "bad"),
                                     ("execution_content_sha256", "bad"), ("reporter_sha256", "bad"), ("published_ns", True)):
                    with self.subTest(key=key), self.assertRaises(ValueError):
                        precision.validate_original_publication({**publication, key: changed}, value, *args)
                changed = copy.deepcopy(value)
                changed["provenance"]["learning_inputs"] = {}
                with self.assertRaises(ValueError):
                    precision.validate_original_publication(publication, changed, *args)
                loaded = list(original["loaded"])
                loaded[2] = loaded[2][:-1]
                with self.assertRaisesRegex(ValueError, "current run count"):
                    precision.validate_original_publication(publication, value, *args[:-1], loaded)

    def test_load_original_uses_original_contract_and_locked_attestation(self):
        with tempfile.TemporaryDirectory() as folder:
            original, _, tables, attestation, _, _ = self.original(Path(folder))
            held = []
            @contextlib.contextmanager
            def lock(path):
                self.assertEqual(path, Path(original["pool_path"]) / "pool.lock")
                held.append(True)
                try:
                    yield
                finally:
                    held.pop()
            def validate(out, manifest, metadata):
                self.assertTrue(held)
                self.assertEqual(metadata["protocol_sha256"], precision.ORIGINAL_PROTOCOL_SHA256)
                self.assertEqual(original["loaded"][0]["oracle"]["validation_samples"], 131072)
                return tables, attestation
            with self.pin_fixture(original), mock.patch.object(reporting, "execution_plan", return_value=(original["manifest"], original["metadata"], original["loaded"])) as loader, \
                 mock.patch.object(reporting, "analysis_runs"), mock.patch.object(pool, "exclusive_lock", side_effect=lock), \
                 mock.patch.object(reporting, "validate_pool_locked", side_effect=validate):
                loaded = precision.load_original(original["family_path"], original["family_sha256"], original["report_path"], original["decision_path"])
                self.assertEqual(loaded["partition"], original["partition"])
                self.assertEqual(loaded["inputs_sha256"], original["inputs_sha256"])
                loader.assert_called_once_with(Path(original["family_path"]), original["family_sha256"])
                self.assertFalse(held)

    def test_partition_rejects_missing_extra_or_reclassified_jobs(self):
        with tempfile.TemporaryDirectory() as folder:
            original, _, tables, *_ = self.original(Path(folder))
            self.assertEqual(len(precision.result_partition(original["manifest"], tables)["mc"]), 84)
            for kind in ("missing", "extra", "method", "classification"):
                with self.subTest(kind=kind):
                    changed = copy.deepcopy(tables)
                    key = next(iter(changed))
                    if kind == "missing":
                        del changed[key]
                    elif kind == "extra":
                        changed["unknown", (0, 0, 0)] = changed[key]
                    else:
                        changed[key]["method"] = "structural_zero_loss_pair" if kind == "classification" else "unknown"
                    with self.assertRaises(ValueError):
                        precision.result_partition(original["manifest"], changed)

    def test_plan_freezes_entire_family_lineage_and_no_self_reference(self):
        with tempfile.TemporaryDirectory() as folder:
            original, contexts, *_ = self.original(Path(folder))
            before = copy.deepcopy(original["manifest"])
            path, saved = self.frozen_plan(Path(folder), original, contexts)
            self.assertEqual(original["manifest"], before)
            self.assertEqual(saved["manifest"]["jobs"], before["jobs"])
            self.assertEqual(saved["manifest"]["oracle_digests"], before["oracle_digests"])
            self.assertEqual(saved["manifest"]["raw_run_identities"], before["raw_run_identities"])
            self.assertEqual(len(saved["manifest"]["raw_run_identities"]), 1500)
            self.assertEqual(saved["manifest"]["evaluation_family_size"], 100)
            self.assertNotIn(str(path), saved["inputs_sha256"])
            self.assertNotIn(str(path) + ".published.json", saved["inputs_sha256"])
            self.assertIn(original["decision_path"], saved["inputs_sha256"])
            self.assertEqual(saved["reference_lineage"]["protocol_sha256"], precision.ORIGINAL_PROTOCOL_SHA256)
            self.assertFalse(saved["reference_lineage"]["retagged"])
            marker = pool.read_json(Path(str(path) + ".published.json"))
            self.assertEqual(marker["artifacts_sha256"][str(path)], bench.file_hash(path))
            self.assertEqual(marker["artifacts_sha256"][saved["effective_protocol_path"]], bench.file_hash(saved["effective_protocol_path"]))

    def test_plan_outputs_are_new_and_publication_is_last(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original, contexts, *_ = self.original(root)
            path, saved = self.frozen_plan(root, original, contexts)
            with self.assertRaisesRegex(ValueError, "new files"):
                precision.freeze_plan("family", "sha", "report", "decision", saved["effective_protocol_path"], path)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original, contexts, *_ = self.original(root)
            write = bench.write_new
            def fail_on_plan(path, value):
                if Path(path).name == "precision_plan.json":
                    raise OSError("plan write failed")
                return write(path, value)
            with mock.patch.object(bench, "write_new", side_effect=fail_on_plan), self.assertRaises(OSError):
                self.frozen_plan(root, original, contexts)
            self.assertTrue((root / "effective.json").is_file())
            self.assertFalse((root / "precision_plan.json.published.json").exists())

    def execute_fixture(self, path, original, contexts):
        with mock.patch.object(precision, "load_original", return_value=original), \
             mock.patch.object(bench, "all_contexts", return_value=contexts), \
             mock.patch.object(bench, "load_protocol", side_effect=lambda p: pool.read_json(p)), \
             mock.patch.object(pool, "_check_sources"):
            return precision.execution_plan(path, bench.file_hash(path))

    def test_execution_reconstructs_full_plan_and_binds_plan_marker(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original, contexts, *_ = self.original(root)
            path, saved = self.frozen_plan(root, original, contexts)
            manifest, metadata, loaded = self.execute_fixture(path, original, contexts)
            self.assertEqual(manifest, saved["manifest"])
            self.assertIs(loaded, original["loaded"])
            self.assertEqual(metadata["protocol_path"], saved["effective_protocol_path"])
            self.assertEqual(metadata["inputs_sha256"][str(path)], bench.file_hash(path))
            self.assertIn(str(path) + ".published.json", metadata["inputs_sha256"])
            self.assertEqual(metadata["adapter_sha256"], reporting.FROZEN_SOURCES["bench_action_pool.py"])
            self.assertEqual(metadata["result_partition"], original["partition"])

    def test_missing_or_changed_plan_marker_is_rejected(self):
        for kind in ("missing", "status", "sha", "source"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                original, contexts, *_ = self.original(root)
                path, _ = self.frozen_plan(root, original, contexts)
                marker_path = Path(str(path) + ".published.json")
                marker = pool.read_json(marker_path)
                if kind == "missing":
                    marker_path.unlink()
                else:
                    marker[{"status": "status", "sha": "precision_plan_sha256", "source": "wrapper_sha256"}[kind]] = "bad"
                    self.rewrite(marker_path, marker)
                with self.assertRaises((ValueError, FileNotFoundError)):
                    self.execute_fixture(path, original, contexts)

    def test_rehashed_plan_tampering_fails_reconstruction(self):
        for kind in ("job", "reference", "partition", "alias", "decision"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                original, contexts, *_ = self.original(root)
                path, saved = self.frozen_plan(root, original, contexts)
                if kind == "job":
                    saved["manifest"]["jobs"][0]["action"] = [1, 1, 1]
                elif kind == "reference":
                    saved["reference_lineage"]["retagged"] = True
                elif kind == "partition":
                    saved["result_partition"]["mc"].pop()
                elif kind == "alias":
                    saved["analysis_aliases"] = {}
                else:
                    saved["original"]["decision_sha256"] = "bad"
                self.rewrite(path, saved)
                self.rewrite(Path(str(path) + ".published.json"),
                             {**precision.plan_publication(saved, path, bench.file_hash(path)), "published_ns": 123})
                with self.assertRaisesRegex(ValueError, "reconstructed complete"):
                    self.execute_fixture(path, original, contexts)

    def test_changed_effective_file_or_decision_is_rejected(self):
        for kind in ("effective", "decision"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                original, contexts, *_ = self.original(root)
                path, saved = self.frozen_plan(root, original, contexts)
                target = saved["effective_protocol_path"] if kind == "effective" else original["decision_path"]
                Path(target).write_text("changed", encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.execute_fixture(path, original, contexts)

    def test_checkpoint_identity_changes_with_n_and_old_checkpoint_is_rejected(self):
        context = {"context": {"p": .02}, "mixture": [], "world_params": {}}
        job = {"action": [0, 0, 0], "reference_action": [0, 3, 1]}
        base = {"oracle": {"validation_samples": 131072}}
        effective = {"oracle": {"validation_samples": 1048576}}
        old = pool._checkpoint_identity(base, context, job, 100)
        new = pool._checkpoint_identity(effective, context, job, 100)
        self.assertNotEqual(old, new)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "checkpoint.json"
            self.write(path, {"schema": oracle.SCHEMA, "identity": old, "completed_connections": 131072})
            run = oracle._Run(new, oracle._spec({"checkpoint_path": str(path)}), None)
            with self.assertRaisesRegex(ValueError, "checkpoint identity"):
                run.load()

    def semantic_result(self, structural=False):
        protocol = {"oracle": {"validation_samples": 1048576, "validation_seed": 850001,
                               "confidence": .99, "m_max": 0, "original_max_bytes": 1281}}
        context = {"context": {"k": 2, "w": 1280, "p": 0 if structural else .02,
                               "rtt_ms": 50, "uplink_mbps": 2, "cert_bytes": 2955 if structural else 9000},
                   "world_params": {}, "mixture": []}
        job = {"context_id": "synthetic", "job_id": "synthetic_1_0_0", "action": [1, 0, 0], "reference_action": [0, 0, 0]}
        expected, spec, params, mixture, _ = precision.bench_oracles._expected_result_contract(protocol, context, "actions", 100)
        result = {"schema": oracle.SCHEMA, "status": "complete", "context_id": job["context_id"], "job_id": job["job_id"],
                  "protocol_sha256": "effective", "source_hashes": oracle._source_hashes(), **expected,
                  "approximate": not structural, "validation_samples": 0 if structural else 1048576,
                  "n": 0 if structural else 1048576, "evaluation_family_size": 100,
                  "action": job["action"], "reference_action": job["reference_action"], "validation_seed": 850001}
        if structural:
            result.update(method="structural_zero_loss_pair", uncertainty_resolved=True,
                          certificate=oracle._certificate(mixture, params, oracle._source_hashes(), spec))
        else:
            result.update(method="independent_paired_validation", confidence=.99,
                          evaluation_seed_must_not_have_selected_either_action=True)
        manifest = {"protocol_sha256": "effective", "evaluation_family_size": 100}
        return result, manifest, protocol, {"synthetic": context}, job

    def test_frozen_result_validation_requires_new_n_seed_family_and_protocol(self):
        result, manifest, protocol, contexts, job = self.semantic_result()
        pool._validate_result(result, manifest, protocol, contexts, job)
        for key, value in (("n", 131072), ("validation_samples", 131072), ("n", 0),
                           ("validation_seed", 850002), ("evaluation_family_size", 84),
                           ("protocol_sha256", "original")):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                pool._validate_result({**result, key: value}, manifest, protocol, contexts, job)
        changed = copy.deepcopy(result)
        changed["spec"]["validation_samples"] = 131072
        with self.assertRaisesRegex(ValueError, "spec"):
            pool._validate_result(changed, manifest, protocol, contexts, job)

    def test_structural_n_zero_requires_actual_certificate_and_full_family(self):
        result, manifest, protocol, contexts, job = self.semantic_result(True)
        self.assertIsNotNone(result["certificate"])
        pool._validate_result(result, manifest, protocol, contexts, job)
        self.assertEqual(result["evaluation_family_size"], 100)
        for key, value in (("n", 1048576), ("evaluation_family_size", 16), ("certificate", None)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                pool._validate_result({**result, key: value}, manifest, protocol, contexts, job)

    def test_run_calls_frozen_pool_with_full_contract_and_worker_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            metadata = {"original": {"pool_path": str(root / "original")}, "inputs_sha256": {}}
            manifest = {"evaluation_family_size": 100}
            with mock.patch.object(precision, "execution_plan", return_value=(manifest, metadata, None)), \
                 mock.patch.object(pool, "run_pool", return_value={"status": "partial"}) as run, \
                 mock.patch.object(pool, "_check_inputs"):
                result = precision.run_precision("plan", "sha", root / "new", workers=8, resume=True, loop=True)
                run.assert_called_once_with(root / "new", manifest, metadata, workers=8, time_budget_seconds=300.0, resume=True, loop=True)
                self.assertEqual(result["status"], "partial")
                with self.assertRaisesRegex(ValueError, "overlaps"):
                    precision.run_precision("plan", "sha", root / "original" / "nested")
                with self.assertRaisesRegex(ValueError, "overlaps"):
                    precision.run_precision("plan", "sha", root)
            for workers in (0, 9, True):
                with self.subTest(workers=workers), self.assertRaisesRegex(ValueError, "workers"):
                    precision.run_precision("plan", "sha", root / "new", workers=workers)

    def aggregate_fixture(self):
        protocol = {"seeds": [1, 2], "scenarios": [{"id": "B1", "family": "B1", "context": {"cert_bytes": 9000}, "phases": [{"length": 1, "p": .15}]}],
                    "metrics": {"paired_confidence": .95, "adaptation_near_optimal_ms": .5, "adaptation_consecutive": 2,
                                "p_bias_high_phase_last_n": 1},
                    "thresholds": {"B1_regret_ms": .1, "B1_abs_p_bias": .005, "max_regression_vs_v31_ms": .5}}
        baseline, current = [], []
        for generation, mode in [("v31", None), ("v32", None)] + [("current", mode) for mode in reporting.MODES]:
            for seed in protocol["seeds"]:
                action = [1, 0, 0] if mode == "c1" else [0, 0, 0]
                run = {"generation": generation, "variant": "full", "mode": "full", "scenario": "B1", "seed": seed,
                       "action_counts": [{"context_id": "c", "action": action, "n": 1}], "n": 1,
                       "summary": {"mean_hct_ms": 60, "failure_rate": 0, "mean_extra_server_bytes": 0,
                                   "mean_extra_first_flight_bytes": 0, "mean_extra_client_first_flight_bytes": 0,
                                   "p_bias_high_phase": .001, "p_bias_high_phase_n": 1, "p_mae_high_phase": .001,
                                   "alarm_rate_per_1000": 0, "guard_alarm_fraction": 0,
                                   "longest_unchanged_action_run": 1, "transitions": []}, "final_state": {"p_mean": .15}}
                if mode is None:
                    baseline.append(run)
                else:
                    run["observation_mode"] = mode
                    current.append(run)
        refs = {"c": {"chosen_action": [0, 3, 1], "selection_gap_upper_ms": None, "uncertainty_resolved": False}}
        tables = {("c", (index, 0, 0)): {"action": [index, 0, 0], "reference_action": [0, 3, 1],
                  "mean_gap_ms": .2 if index == 0 else .1, "gap_half_width_ms": .01,
                  "approximate": True, "uncertainty_resolved": True, "zero_observed_variance": False} for index in (0, 1)}
        return (protocol, baseline, current, refs, {}), tables

    def test_post_pool_source_or_input_failure_cannot_return_complete(self):
        for kind in ("source", "input"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                metadata = {"original": {"pool_path": str(root / "original")}, "inputs_sha256": {}}
                with mock.patch.object(precision, "execution_plan", return_value=({}, metadata, None)), \
                     mock.patch.object(pool, "run_pool", return_value={"status": "complete"}) as execute, \
                     mock.patch.object(precision, "check_sources", side_effect=ValueError("source changed") if kind == "source" else None), \
                     mock.patch.object(pool, "_check_inputs", side_effect=ValueError("input changed") if kind == "input" else None), \
                     self.assertRaisesRegex(ValueError, "changed"):
                    precision.run_precision("plan", "sha", root / "new")
                execute.assert_called_once()

    def trace(self, run):
        row = {"index": 0, "context_id": "c", "action": run["action_counts"][0]["action"], "hct_ms": 60,
               "b0_hct_ms": 70, "global_fixed_hct_ms": 55, "server_bytes": 100,
               "b0_server_bytes": 100, "global_fixed_server_bytes": 100, "ok": True}
        if "observation_mode" in run:
            mode = run["observation_mode"]
            row.update(observation_mode=mode, observer_diagnostics={"mode": mode, "usable": False},
                       observation_info={"loss_update_kind": "categorical", "loss_evidence_src": "none", "arrival_sent": 0,
                                         "arrival_lost": 0, "arrival_trunc": False, "arrival_usable": False},
                       policy_observe_input={"optional": {"first_flight_evidence": {"src": "none", "sent": 0, "lost": 0, "bitmap": None, "trunc": False}}})
        return [row]

    def test_frozen_aggregate_recomputes_new_means_and_keeps_selection_null(self):
        loaded, tables = self.aggregate_fixture()
        base = reporting.aggregate_learning(*loaded[:4], tables, trace_loader=self.trace)
        result = precision.aggregate_precision(loaded, tables, trace_loader=self.trace)
        self.assertEqual(result["groups"], base["groups"])
        self.assertEqual(result["comparisons"], base["comparisons"])
        comparison = next(item for item in result["comparisons"] if item["candidate"]["generation"] == "current_c1" and item["baseline"]["generation"] == "v32")
        self.assertAlmostEqual(comparison["seed_summary"]["mean"], -.1)
        self.assertEqual(comparison["selection_gap_bound_ms"], 0)
        self.assertTrue(all(group["expected_regret"]["upper_bound_ms"] is None for group in result["groups"]))
        changed = copy.deepcopy(tables)
        changed["c", (1, 0, 0)]["mean_gap_ms"] = .3
        updated = precision.aggregate_precision(loaded, changed, trace_loader=self.trace)
        comparison_new = next(item for item in updated["comparisons"] if item["candidate"]["generation"] == "current_c1" and item["baseline"]["generation"] == "v32")
        self.assertAlmostEqual(comparison_new["seed_summary"]["mean"], .1)
        self.assertEqual(comparison_new["realized_hct_diagnostic"], comparison["realized_hct_diagnostic"])

    def test_zero_variance_unresolved_stays_null_and_identical_action_cancels(self):
        loaded, tables = self.aggregate_fixture()
        tables["c", (1, 0, 0)].update(gap_half_width_ms=None, zero_observed_variance=True, uncertainty_resolved=False)
        value = precision.aggregate_precision(loaded, tables, trace_loader=self.trace)
        c1 = next(item for item in value["comparisons"] if item["candidate"]["generation"] == "current_c1" and item["baseline"]["generation"] == "v32")
        self.assertIsNone(c1["upper_bound_ms"])
        self.assertEqual(c1["regression_gate"]["status"], "inconclusive")
        same = next(item for item in value["comparisons"] if item["candidate"]["generation"] == "current_none" and item["baseline"]["generation"] == "v32")
        self.assertEqual(same["shared_mc_bound_ms"], 0)

    def test_new_mc_means_recompute_seed_interval_with_unequal_action_weights(self):
        loaded, tables = self.aggregate_fixture()
        for run in loaded[2]:
            if run["observation_mode"] == "c1" and run["seed"] == 2:
                run["action_counts"] = [{"context_id": "c", "action": [0, 0, 0], "n": 1}]
        def comparison(value):
            return next(item for item in value["comparisons"] if item["candidate"]["generation"] == "current_c1"
                        and item["baseline"]["generation"] == "v32")
        old = comparison(precision.aggregate_precision(loaded, tables, trace_loader=self.trace))
        tables["c", (1, 0, 0)]["mean_gap_ms"] = .5
        new = comparison(precision.aggregate_precision(loaded, tables, trace_loader=self.trace))
        self.assertNotEqual(new["seed_estimates"], old["seed_estimates"])
        self.assertNotEqual(new["seed_summary"]["upper"] - new["seed_summary"]["lower"],
                            old["seed_summary"]["upper"] - old["seed_summary"]["lower"])
        self.assertEqual(new["realized_hct_diagnostic"], old["realized_hct_diagnostic"])

    def test_wrapper_and_frozen_reporter_source_changes_are_rejected(self):
        actual = bench.file_hash
        for target in (precision.PATH, reporting.PATH):
            with self.subTest(target=target):
                def changed(path):
                    return "0" * 64 if Path(path) == target else actual(path)
                with mock.patch.object(bench, "file_hash", side_effect=changed), self.assertRaisesRegex(ValueError, "source"):
                    precision.check_sources()

    def report_fixture(self, root):
        evidence = root / "evidence.json"
        inputs = dict([self.write(evidence, {"unchanged": True})])
        pool_dir = root / "new_pool"
        pool_dir.mkdir()
        metadata = {"inputs_sha256": inputs, "original": {"pool_path": str(root / "old_pool"), "publication_sha256": "original"},
                    "base_protocol_sha256": "base", "protocol_path": "effective", "protocol_sha256": "effective sha",
                    "reference_lineage": {"retagged": False}, "result_partition": {"mc": ["one"], "structural": []}}
        attestation = {"files_sha256": inputs}
        result = {"status": "complete", "missing": [], "missing_raw_groups": [], "noninferiority": {}}
        return pool_dir, {"evaluation_family_size": 100}, metadata, (1, 2, 3, 4, {}), attestation, result

    def test_report_lock_and_last_marker_bind_all_inputs_and_artifacts(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pool_dir, manifest, metadata, loaded, attestation, result = self.report_fixture(root)
            held = []
            @contextlib.contextmanager
            def lock(path):
                self.assertEqual(path, pool_dir / "pool.lock")
                held.append(True)
                try:
                    yield
                finally:
                    held.pop()
            def validate(*args):
                self.assertTrue(held)
                return {}, attestation
            def render(value):
                self.assertTrue(held)
                return "synthetic report"
            with mock.patch.object(precision, "execution_plan", return_value=(manifest, metadata, loaded)), \
                 mock.patch.object(pool, "exclusive_lock", side_effect=lock), \
                 mock.patch.object(reporting, "validate_pool_locked", side_effect=validate), \
                 mock.patch.object(precision, "result_partition", return_value=metadata["result_partition"]), \
                 mock.patch.object(precision, "aggregate_precision", return_value=result), \
                 mock.patch.object(pool, "_check_sources"), mock.patch.object(pool, "_check_inputs") as input_check, \
                 mock.patch.object(precision, "markdown", side_effect=render):
                out = root / "report.json"
                precision.final_report("plan", "sha", pool_dir, out, root / "report.md")
                self.assertGreaterEqual(input_check.call_count, 3)
                marker = pool.read_json(Path(str(out) + ".published.json"))
                self.assertEqual(marker["schema"], precision.PUBLICATION_SCHEMA)
                self.assertEqual(marker["artifacts_sha256"][str(out)], bench.file_hash(out))
                self.assertEqual(marker["original_publication_sha256"], "original")
                self.assertEqual(marker["execution_content_sha256"], bench.digest(metadata))
                self.assertFalse(held)

    def test_partial_or_changed_input_never_receives_report_publication(self):
        for kind in ("partial", "render", "changed_input"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                pool_dir, manifest, metadata, loaded, attestation, result = self.report_fixture(root)
                def render(value):
                    if kind == "render":
                        raise OSError("render failure")
                    if kind == "changed_input":
                        (root / "evidence.json").write_text("modified", encoding="utf-8")
                    return "report"
                with mock.patch.object(precision, "execution_plan", return_value=(manifest, metadata, loaded)), \
                     mock.patch.object(reporting, "validate_pool_locked", return_value=({}, attestation)), \
                     mock.patch.object(precision, "result_partition", return_value=metadata["result_partition"]), \
                     mock.patch.object(precision, "aggregate_precision", side_effect=ValueError("incomplete") if kind == "partial" else None, return_value=result), \
                     mock.patch.object(pool, "_check_sources"), mock.patch.object(pool, "_check_inputs", side_effect=lambda m: reporting.check_files(m["inputs_sha256"])), \
                     mock.patch.object(precision, "markdown", side_effect=render):
                    out = root / "report.json"
                    with self.assertRaises((ValueError, OSError)):
                        precision.final_report("plan", "sha", pool_dir, out, root / "report.md")
                    self.assertFalse(Path(str(out) + ".published.json").exists())
                    if kind == "partial":
                        self.assertFalse(out.exists())

    def test_partial_frozen_aggregate_is_rejected(self):
        with mock.patch.object(reporting, "aggregate_learning", return_value={"status": "pending", "missing": [], "missing_raw_groups": []}), \
             self.assertRaisesRegex(ValueError, "incomplete aggregate"):
            precision.aggregate_precision((1, 2, 3, 4, {}), {})

    def test_conflicting_hash_inventory_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "conflicting"):
            precision.merge_inputs({"one": "a"}, {"one": "b"})


if __name__ == "__main__":
    unittest.main()
