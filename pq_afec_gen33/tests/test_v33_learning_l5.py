import collections
import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.v33 import bench_learning_l5 as learning



class PreservedDirectory:
    def __init__(self):
        self.name = tempfile.mkdtemp(prefix="padfec-test-")

    def __enter__(self):
        return self.name

    def __exit__(self, *args):
        return False

    def cleanup(self):
        pass


class FakeWorker:
    instances = []
    initial_value = None
    close_failure = False

    def __init__(self, *args):
        self.initial = copy.deepcopy(self.initial_value)
        self.requests = []
        self.closed = False
        self.instances.append(self)

    def request(self, value):
        self.requests.append(copy.deepcopy(value))
        if value["op"] == "decide":
            return {"decision": {"action": [0, 0, 0], "p_mean": .02, "ej": 50.0}, "before": {"S_hat": 2955}}
        if value["op"] == "observe":
            return {"observation": {"updated": True}, "state": {"S_hat": 2955}}
        if value["op"] == "snapshot":
            return {"state": {"S_hat": 2955}, "audit": self.initial["audit"]}
        return {"state": {}}

    def close(self):
        self.closed = True
        if self.close_failure:
            raise RuntimeError("synthetic worker exit failure")


class FakeWorld:
    calls = []
    feature_enabled = True
    failure_index = None

    def __init__(self, params, seed):
        self.params = {"features": {"s2c_loss": self.feature_enabled}, "server": {"decoder_max_datagram_bytes": 1400}}
        self.seed = seed

    def sample(self, context, action, connection, trace):
        self.calls.append((self.seed, connection, trace, action))
        return {"hct": 120000 if connection == self.failure_index else 100.0,
                "ok": connection != self.failure_index, "k_obs": 2, "srv_bytes": 3000,
                "arrivals": [{"flight": 0, "arrived": True, "read_size": 1280}],
                "server_counted_uplink_bytes": 1280, "client_first_flight_bytes": 2560,
                "rtt": 50.0, "selected_cert_bytes": context.cert_bytes, "true_rtt_ms": context.rtt_ms,
                "initial_datagrams": 2, "stop_reason": "test", "secret_world_truth": .88,
                "model_kind": "independent_event_world", "trace": [
                    {"event": "client_receive", "time_ms": 1, "kind": "ack", "size": 41},
                    {"event": "client_receive", "time_ms": 2, "kind": "data", "size": 1280, "index": 0},
                    {"event": "client_receive", "time_ms": 3, "kind": "data", "size": 1679, "index": 1}] + ([] if connection == self.failure_index else [{"event": "handshake_complete", "time_ms": 100.0}])}


class LearningBenchTests(unittest.TestCase):
    def setUp(self):
        self.temp = PreservedDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.overlay_path = self.root / "overlay.json"
        self.overlay_path.write_text("{}", encoding="utf-8")
        self.policy_root = self.root / "snapshot"
        self.policy_root.mkdir()
        policy_path = self.policy_root / "padfec3" / "learn3.py"
        policy_path.parent.mkdir()
        policy_path.write_text("x=1\n", encoding="utf-8")
        fingerprint = {"source_root": str(self.policy_root), "files": {"padfec3/learn3.py": learning.bench.file_hash(policy_path)}}
        audit = {"source_root": str(self.policy_root), "source_unchanged": True,
                 "source_sha256": {str(policy_path): fingerprint["files"]["padfec3/learn3.py"]},
                 "actual_module_paths": {"padfec3.learn3": str(policy_path)},
                 "isolated": True, "dont_write_bytecode": True, "read_only_audit": True}
        self.policy = {"fingerprint": fingerprint, "policy_version": "v3.3-dev", "state_version": 9,
                       "receipt_path": str(self.overlay_path), "receipt_sha256": learning.bench.file_hash(self.overlay_path)}
        self.source = {"bench_learning_l5.py": "synthetic-source"}
        self.scenario = {"id": "B1", "family": "B1", "context": {"k": 2, "w": 1280, "p": .02,
            "rtt_ms": 50, "uplink_mbps": 2, "cert_bytes": 2955, "s2c_loss": .2},
            "phases": [{"length": 5, "p": .02}, {"length": 6, "p": .15}],
            "world_params": {}, "reset_each_connection": False}
        self.protocol = {"seeds": [31], "scenarios": [self.scenario], "metrics": {}, "c_pkt": .1}
        self.overlay = {"scenarios": ["B1"], "source_sha256": self.source, "policy": self.policy,
                        "base_protocol_sha256": "base-hash", "base_protocol_path": str(self.overlay_path),
                        "import_receipt_path": str(self.overlay_path), "import_receipt_sha256": learning.bench.file_hash(self.overlay_path)}
        rows = []
        for phase_number, phase_index, index, phase in learning.schedule(self.scenario):
            spec = learning.bench.context_spec(self.scenario, phase)
            rows.append({"index": index, "phase": phase_number, "phase_index": phase_index,
                "context_id": learning.bench.context_id(spec), "phase_p": phase["p"], "action": [0, 0, 0],
                "selected_cert_bytes": 2955, "true_rtt_ms": 50, "b0_server_bytes": 1280,
                "b0_hct_ms": 100, "global_fixed_hct_ms": 105, "global_fixed_server_bytes": 2000})
        self.baseline_path = self.root / "baseline.jsonl.gz"
        with gzip.open(self.baseline_path, "wt", encoding="utf-8") as stream:
            stream.write("\n".join(json.dumps(row) for row in rows) + "\n")
        counts = collections.Counter((r["context_id"], tuple(r["action"])) for r in rows)
        self.baseline = {"generation": "v32", "variant": "full", "scenario": "B1", "seed": 31,
                         "n": len(rows), "trace_path": str(self.baseline_path), "trace_sha256": learning.bench.file_hash(self.baseline_path),
                         "action_counts": [{"context_id": key[0], "action": list(key[1]), "n": n} for key, n in counts.items()]}
        self.baselines = [dict(self.baseline, generation="v31"), self.baseline]
        self.receipt = {"files_sha256": {str(self.baseline_path): self.baseline["trace_sha256"]},
                        "rules_path": str(self.overlay_path), "rules_sha256": learning.bench.file_hash(self.overlay_path),
                        "provenance": {"raw_manifests": []}}
        FakeWorker.instances = []
        FakeWorker.close_failure = False
        FakeWorker.initial_value = {"policy_version": "v3.3-dev", "state_version": 9, "variant": "full",
                                   "runtime_overrides": {}, "capabilities": {"observe_extra": ["first_flight_evidence", "server_response"]}, "audit": audit}
        FakeWorld.calls = []
        FakeWorld.feature_enabled = True
        FakeWorld.failure_index = None
        self.observer_calls = []

        def observer(row, **kwargs):
            self.observer_calls.append((copy.deepcopy(row), kwargs))
            return {"evidence": {"src": "none" if kwargs["mode"] == "none" else "c1",
                                 "sent": 2, "lost": 0, "bitmap": None if kwargs["mode"] == "none" else [1, 1], "trunc": False},
                    "diagnostics": {"mode": kwargs["mode"], "evaluation_only_hidden": .88}}

        patches = [patch.object(learning, "load_overlay", return_value=(self.overlay, self.protocol)),
                   patch.object(learning, "imported_runs", return_value=(self.baselines, {}, self.receipt)),
                   patch.object(learning, "assert_sources"), patch.object(learning, "sources", return_value=self.source),
                   patch.object(learning, "PolicyWorker", FakeWorker), patch.object(learning.bench, "World", FakeWorld),
                   patch.object(learning, "make_world_evidence", observer)]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def collect(self, **kwargs):
        out = self.root / "raw"
        learning.collect(self.overlay_path, out, **kwargs)
        return out

    def test_smoke_preserves_original_world_indexes_and_calls_world_once(self):
        out = self.collect(modes=["c1"], smoke=True)
        self.assertEqual([value[1] for value in FakeWorld.calls], [0, 1, 2, 3, 5, 6, 7, 8])
        self.assertTrue(all(value[2] for value in FakeWorld.calls))
        result = learning.read_json(out / "c1/B1/seed00031.json")
        self.assertEqual(result["n"], 8)
        self.assertTrue(FakeWorker.instances[0].closed)
        for row, kwargs in self.observer_calls:
            self.assertEqual(kwargs["feedback_loss_probability"], .2)
            self.assertEqual(kwargs["receiver_max_datagram_bytes"], 1400)
            self.assertEqual(kwargs["feedback_grace_ms"], 200)
            self.assertEqual(kwargs["crc_list_limit"], 64)

    def test_truth_and_observer_diagnostics_never_cross_worker_boundary(self):
        self.collect(modes=["c1"], smoke=True)
        requests = FakeWorker.instances[0].requests
        decisions = [r for r in requests if r["op"] == "decide"]
        self.assertIsNone(decisions[0]["rtt_ms"])
        self.assertEqual(decisions[1]["rtt_ms"], 50)
        for request in requests:
            self.assertNotIn("secret_world_truth", json.dumps(request))
            self.assertNotIn("evaluation_only_hidden", json.dumps(request))
            self.assertNotIn("s2c_loss", json.dumps(request))

    def test_none_collects_server_response_trace_and_feature_disabled_feedback_is_zero(self):
        FakeWorld.feature_enabled = False
        self.collect(modes=["none"], smoke=True)
        self.assertTrue(all(value[2] for value in FakeWorld.calls))
        self.assertTrue(all(kwargs["feedback_loss_probability"] == 0 for row, kwargs in self.observer_calls))

    def test_failure_cost_stays_in_trace_but_observation_hct_is_null(self):
        FakeWorld.failure_index = 0
        out = self.collect(modes=["ideal"], smoke=True)
        result = learning.read_json(out / "ideal/B1/seed00031.json")
        rows = learning.bench_report.load_trace(result)
        self.assertEqual(rows[0]["hct_ms"], 120000)
        self.assertIsNone(rows[0]["policy_observe_input"]["hct_ms"])
        self.assertEqual(result["summary"]["failure_count"], 1)

    def test_reset_each_connection_keeps_policy_rtt_cold(self):
        self.scenario["reset_each_connection"] = True
        self.collect(modes=["none"], smoke=True)
        requests = FakeWorker.instances[0].requests
        self.assertTrue(all(r["rtt_ms"] is None for r in requests if r["op"] == "decide"))
        self.assertEqual(sum(r["op"] == "reset" for r in requests), 9)

    def test_completed_full_inventory_loads_and_binds_inputs(self):
        out = self.collect()
        protocol, baseline, current, refs, provenance = learning.load_learning_runs(self.overlay_path, [out])
        self.assertEqual(len(baseline), 2)
        self.assertEqual(len(current), 3)
        self.assertTrue(provenance["complete"])
        self.assertIn(str(self.baseline_path), provenance["inputs_sha256"])
        self.assertEqual(set(r["observation_mode"] for r in current), set(learning.MODES))

    def test_missing_mode_or_seed_and_duplicate_shard_are_rejected(self):
        out = self.collect(modes=["none"])
        with self.assertRaisesRegex(ValueError, "full three-mode"):
            learning.load_learning_runs(self.overlay_path, [out])
        with self.assertRaisesRegex(ValueError, "duplicate learning"):
            learning.load_learning_runs(self.overlay_path, [out, out], require_complete=False)
        (out / "none/B1/seed00031.json").rename(out / "none/B1/seed00031.saved")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            learning.load_learning_runs(self.overlay_path, [out])

    def test_smoke_cannot_be_loaded_as_full(self):
        out = self.collect(smoke=True)
        with self.assertRaisesRegex(ValueError, "only full"):
            learning.load_learning_runs(self.overlay_path, [out])

    def test_resume_requires_matching_producer_and_completed_receipt(self):
        out = self.collect(modes=["none"])
        calls = len(FakeWorld.calls)
        learning.collect(self.overlay_path, out, modes=["none"], resume=True)
        self.assertEqual(len(FakeWorld.calls), calls)
        path = out / "none/B1/seed00031.json"
        result = learning.read_json(path)
        finished = path.parent / (result["attempt_id"] + ".finished.json")
        finished.rename(finished.with_suffix(".saved"))
        with self.assertRaises(FileNotFoundError):
            learning.collect(self.overlay_path, out, modes=["none"], resume=True)

    def test_source_or_mode_changes_are_rejected_before_numeric_use(self):
        out = self.collect(modes=["none"])
        path = out / "none/B1/seed00031.json"
        original = learning.read_json(path)
        for key, bad in (("source_sha256", {}), ("source_sha256_before", {}), ("observation_mode", "ideal"), ("seed", 32)):
            changed = copy.deepcopy(original)
            changed[key] = bad
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaises(ValueError):
                learning.load_learning_runs(self.overlay_path, [out], require_complete=False)
        path.write_text(json.dumps(original), encoding="utf-8")

    def test_worker_exit_failure_cannot_publish_complete_summary(self):
        FakeWorker.close_failure = True
        with self.assertRaisesRegex(RuntimeError, "exit failure"):
            self.collect(modes=["none"])
        folder = self.root / "raw/none/B1"
        self.assertFalse((folder / "seed00031.json").exists())
        self.assertEqual(len(list(folder.glob("*.failed.json"))), 1)

    def test_baseline_trace_mutation_is_rejected_before_policy_observations(self):
        self.baseline_path.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "trace hash"):
            self.collect(modes=["none"])
        self.assertFalse(any(r["op"] == "observe" for r in FakeWorker.instances[0].requests))

    def test_post_run_source_failure_preserves_attempt_and_resume_uses_new_worker(self):
        learning.assert_sources.side_effect = [None, FileNotFoundError("synthetic disappeared producer")]
        with self.assertRaisesRegex(FileNotFoundError, "disappeared producer"):
            self.collect(modes=["none"])
        folder = self.root / "raw/none/B1"
        self.assertFalse((folder / "seed00031.json").exists())
        self.assertEqual(len(list(folder.glob("*.failed.json"))), 1)
        old_traces = set(folder.glob("*.jsonl.gz"))
        self.assertEqual(len(old_traces), 1)
        self.assertTrue(FakeWorker.instances[0].closed)
        learning.assert_sources.side_effect = None
        learning.collect(self.overlay_path, self.root / "raw", modes=["none"], resume=True)
        self.assertEqual(len(FakeWorker.instances), 2)
        self.assertEqual(FakeWorker.instances[1].requests[0], {"op": "reset", "destination": "d"})
        self.assertEqual(len(list(folder.glob("*.jsonl.gz"))), 2)
        self.assertTrue(old_traces.issubset(set(folder.glob("*.jsonl.gz"))))
        self.assertTrue((folder / "seed00031.json").is_file())

    def test_receipt_and_summary_mismatch_cannot_be_resumed(self):
        out = self.collect(modes=["none"])
        path = out / "none/B1/seed00031.json"
        result = learning.read_json(path)
        finished = path.parent / (result["attempt_id"] + ".finished.json")
        receipt = learning.read_json(finished)
        receipt["result_digest"] = "other-attempt"
        finished.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "finished receipt"):
            learning.collect(self.overlay_path, out, modes=["none"], resume=True)


class SnapshotTests(unittest.TestCase):
    def test_snapshot_retains_old_bytes_after_original_policy_changes(self):
        with PreservedDirectory() as directory:
            root = Path(directory)
            original, snapshot = root / "original", root / "snapshot"
            for folder in (original, snapshot):
                for package in learning.PACKAGES:
                    (folder / package).mkdir(parents=True)
                    (folder / package / "__init__.py").write_text("value=1\n", encoding="utf-8")
            files = learning.inventory(original)["files"]
            receipt = root / "receipt.json"
            receipt.write_text(json.dumps({"schema": "padfec.v33.policy_snapshot/1", "source_root": str(original),
                "snapshot_root": str(snapshot), "source_and_snapshot_byte_identical": True, "files": files,
                "state_version": 9, "size_variant": "full"}), encoding="utf-8")
            before = learning.snapshot_identity(snapshot, receipt, original)
            (original / "padfec3/__init__.py").write_text("value=2\n", encoding="utf-8")
            self.assertEqual(learning.snapshot_identity(snapshot, receipt), before)
            with self.assertRaisesRegex(ValueError, "original bytes"):
                learning.snapshot_identity(snapshot, receipt, original)
            (snapshot / "padfec3/extra.py").write_text("value=3\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "complete source inventory"):
                learning.snapshot_identity(snapshot, receipt)

    def test_unsupported_policy_state_or_missing_evidence_capability_is_rejected(self):
        policy = {"policy_version": "v3.3-dev", "state_version": 9}
        initial = {"policy_version": "v3.3-dev", "state_version": 3}
        with self.assertRaisesRegex(ValueError, "state version"):
            learning.validate_initial(initial, policy)
        initial.update(state_version=9, variant="full", runtime_overrides={}, capabilities={"observe_extra": []})
        with self.assertRaisesRegex(ValueError, "explicitly support"):
            learning.validate_initial(initial, policy)


if __name__ == "__main__":
    unittest.main()
