import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "experiments/v33/policy_worker.py"
PROTOCOL = ROOT / "g3/v33/bench_protocol.json"


def sources():
    base = ROOT / "g3/v33/fixtures/S5_test_inputs_v1/policies"
    return {"v31": {"source_root": str(base / "v31")},
            "v32": {"source_root": str(base / "v32")},
            "current": {"source_root": str(ROOT)}}


def init_request(source_root=ROOT, variant="full"):
    return {"op": "init", "source_root": str(source_root), "W": 1280, "u_mbps": 2.0, "c_pkt": 41.983, "variant": variant}


def observe_request(destination="default", j_pred=100.0):
    return {"op": "observe", "destination": destination, "action": [0, 0, 0], "hct_ms": 120.0, "ok": True, "k_obs": 2, "srv_bytes": 18000.0, "rtt_ms": 50.0, "j_pred": j_pred}


def run_worker(requests, cwd=ROOT):
    result = subprocess.run([sys.executable, "-I", "-B", str(WORKER)], input="".join(json.dumps(row, allow_nan=False) + "\n" for row in requests), text=True, encoding="utf-8", capture_output=True, cwd=cwd, timeout=30)
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    return result, rows


def cache_inventory(root):
    return {str(path): (path.stat().st_size, path.stat().st_mtime_ns) for package in ("afec", "padfec", "padfec3") for path in (root / package).rglob("*") if path.is_file() and (path.suffix == ".pyc" or "__pycache__" in path.parts)}


class PolicyWorkerTests(unittest.TestCase):
    def test_current_complete_first_flight_updates_cold_loss_state_once(self):
        request = observe_request()
        request["optional"] = {"first_flight_evidence": {
            "src": "c1", "sent": 2, "lost": 0, "bitmap": [1, 1], "trunc": False}}
        process, rows = run_worker([init_request(), {"op": "decide", "rtt_ms": None},
                                    request, {"op": "snapshot"}])
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertEqual(rows[0]["result"]["state_version"], 11)
        self.assertEqual(rows[0]["result"]["capabilities"]["observe_extra"], ["first_flight_evidence"])
        info = rows[2]["result"]["observation"]
        self.assertEqual(info["loss_update_kind"], "datagram")
        self.assertEqual(info["legacy_skip_reason"], "no_base")
        stats = rows[3]["result"]["state"]["stats"]
        self.assertEqual((stats["obs"], stats["predict"], stats["upd"], stats["datagram"]), (1, 1, 1, 1))
        self.assertEqual((stats["arr_sent"], stats["arr_lost"]), (2, 0))
        self.assertLess(rows[3]["result"]["state"]["p_mean"], rows[1]["result"]["before"]["p_mean"])

    def test_legacy_workers_reject_first_flight_without_declared_capability(self):
        request = observe_request()
        request["optional"] = {"first_flight_evidence": {
            "src": "c1", "sent": 2, "lost": 0, "bitmap": [1, 1], "trunc": False}}
        for label in ("v31", "v32"):
            with self.subTest(generation=label):
                process, rows = run_worker([init_request(Path(sources()[label]["source_root"])),
                                            {"op": "decide", "rtt_ms": None}, request])
                self.assertEqual(process.returncode, 2)
                self.assertEqual(rows[0]["result"]["capabilities"]["observe_extra"], [])
                self.assertFalse(rows[2]["ok"])
                self.assertEqual(rows[2]["error"]["type"], "ValueError")

    def test_source_isolation_cold_decision_and_read_only_observation(self):
        for label, spec in sources().items():
            source = Path(spec["source_root"]).resolve()
            before = cache_inventory(source)
            with self.subTest(generation=label):
                process, rows = run_worker([init_request(source), {"op": "decide", "rtt_ms": None}, observe_request(), {"op": "decide", "rtt_ms": 50.0}, {"op": "snapshot"}])
                self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
                self.assertEqual(len(rows), 5)
                self.assertTrue(all(row["ok"] for row in rows))
                self.assertEqual(rows[1]["result"]["decision"]["why"], "cold")
                self.assertEqual(rows[1]["result"]["decision"]["action"], [0, 0, 0])
                self.assertEqual(rows[2]["result"]["state"]["S_hat"], 18000.0)
                self.assertEqual(rows[2]["result"]["state"]["k_hat"], 2)
                audit = rows[-1]["result"]["audit"]
                self.assertTrue(audit["source_unchanged"])
                self.assertTrue(audit["isolated"] and audit["dont_write_bytecode"])
                self.assertTrue(all(Path(path).resolve().is_relative_to(source) for path in audit["actual_module_paths"].values()))
                self.assertTrue(all(not Path(path or str(ROOT)).resolve().is_relative_to(source) for path in audit["sys_path"]))
                self.assertGreaterEqual(len(audit["path_insertions_blocked"]), 2)
                if label in ("v31", "v32"):
                    self.assertEqual(rows[0]["result"]["policy_version"], {"v31": "v3.1", "v32": "v3.2-dev"}[label])
                self.assertEqual(cache_inventory(source), before)

    def test_destination_reset_does_not_change_other_destination(self):
        process, rows = run_worker([init_request(), {"op": "decide", "destination": "one", "rtt_ms": None}, observe_request("one"), {"op": "decide", "destination": "two", "rtt_ms": None}, observe_request("two"), {"op": "reset", "destination": "one"}, {"op": "snapshot", "destination": "two"}, {"op": "snapshot", "destination": "one"}])
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertEqual(rows[-2]["result"]["state"]["stats"]["obs"], 1)
        self.assertEqual(rows[-1]["result"]["state"]["stats"]["obs"], 0)
        self.assertIsNone(rows[-1]["result"]["state"]["S_hat"])

    def test_variant_changes_are_declared_and_fixed_per_process(self):
        for variant in ("guard_off", "reeval_off"):
            with self.subTest(variant=variant):
                process, rows = run_worker([init_request(variant=variant), {"op": "decide", "rtt_ms": None}, observe_request(), {"op": "snapshot"}])
                self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
                self.assertEqual(rows[0]["result"]["variant"], variant)
                if variant == "guard_off":
                    self.assertIsNone(rows[2]["result"]["j_pred_used"])
                    self.assertEqual(rows[2]["result"]["state"]["stats"]["resid"], 0)
                else:
                    self.assertEqual(rows[0]["result"]["runtime_overrides"]["learn3.REEVAL_EVERY"]["effective"], 2 ** 63)
        process, rows = run_worker([init_request(), init_request(variant="guard_off")])
        self.assertEqual(process.returncode, 2)
        self.assertFalse(rows[-1]["ok"])

    def test_unsupported_world_information_and_extra_observations_fail(self):
        for invalid in ({"op": "decide", "rtt_ms": 50.0, "true_p": 0.15}, {**observe_request(), "optional": {"world": {"p": 0.15}}}, {**observe_request(), "optional": {"arrivals": [True, True]}}):
            with self.subTest(op=invalid["op"]):
                process, rows = run_worker([init_request(), {"op": "decide", "rtt_ms": None}, invalid])
                self.assertEqual(process.returncode, 2)
                self.assertFalse(rows[-1]["ok"])
                self.assertEqual(rows[-1]["error"]["type"], "ValueError")

    def test_missing_or_invalid_requests_fail_with_json_error(self):
        for commands in ([{"op": "snapshot"}], [init_request(), {"op": "decide", "rtt_ms": None}, {**observe_request(), "ok": "true"}], [init_request(), {"op": "decide", "rtt_ms": -1}]):
            with self.subTest(commands=len(commands)):
                process, rows = run_worker(commands)
                self.assertEqual(process.returncode, 2)
                self.assertFalse(rows[-1]["ok"])

    def test_decision_observation_pairing_is_enforced(self):
        for commands in ([init_request(), observe_request()], [init_request(), {"op": "decide", "rtt_ms": None}, observe_request(), observe_request()], [init_request(), {"op": "decide", "rtt_ms": None}, {**observe_request(), "action": [0, 0, 1]}], [init_request(), {"op": "decide", "rtt_ms": None}, {"op": "decide", "rtt_ms": None}]):
            with self.subTest(commands=len(commands)):
                process, rows = run_worker(commands)
                self.assertEqual(process.returncode, 2)
                self.assertFalse(rows[-1]["ok"])

    def test_read_only_audit_blocks_import_time_write(self):
        with tempfile.TemporaryDirectory(prefix="v33-worker-source-") as directory:
            fixture = Path(directory).resolve()
            self.assertFalse(fixture.is_relative_to(ROOT.resolve()))
            marker = fixture / "unexpected_write.txt"
            for name in ("afec", "padfec", "padfec3"):
                package = fixture / name
                package.mkdir()
                text = f"open({str(marker)!r}, 'w').write('unexpected')\n" if name == "padfec3" else ""
                (package / "__init__.py").write_text(text, encoding="utf-8")
            process, rows = run_worker([init_request(fixture)])
            self.assertEqual(process.returncode, 2)
            self.assertEqual(rows[-1]["error"]["type"], "PermissionError")
            self.assertFalse(marker.exists())
        self.assertFalse(fixture.exists())


if __name__ == "__main__":
    unittest.main()
