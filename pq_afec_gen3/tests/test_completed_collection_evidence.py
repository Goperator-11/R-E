import ast
import datetime as dt
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
import uuid

EXP = Path(__file__).resolve().parents[1] / "experiments"

def pure(filename, names, **ns):
    tree = ast.parse((EXP / filename).read_text(encoding="utf-8"))
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(funcs) == len(names)
    exec(compile(ast.Module(body=funcs, type_ignores=[]), filename, "exec"), ns)
    return ns

P13 = pure("p13_beff.py", {"cp_lower", "late_parity_assessment", "collection_evidence"},
           math=math, LATE_CRED_MIN=0.99)
P14 = pure("p14_dominance.py", {"arm_evidence"})

class CollectionEvidenceTests(unittest.TestCase):
    def test_returned_failed_trial_blocks_late_parity_conclusion(self):
        rows = [{"ok": True, "ms": 50.0} for _ in range(599)] + [
            {"ok": False, "ms": 5000.0, "error": "timeout"}]
        record = P13["collection_evidence"](rows, {}, {"conns": {}}, "", 600)
        self.assertEqual((record["n_rows"], record["n_ok"], record["n_failed"]), (600, 599, 1))
        result = P13["late_parity_assessment"](600, record["n_ok"], 600, 600)
        self.assertFalse(result["coverage_complete"])
        self.assertEqual(result["verdict"], "inconclusive")
        self.assertIsNone(result["cred_ci95_lo"])
        self.assertEqual(record["client_rows"][-1]["error"], "timeout")

    def test_complete_success_retains_existing_credit_threshold(self):
        record = P13["collection_evidence"]([{"ok": True}] * 600, {}, {}, "", 600)
        result = P13["late_parity_assessment"](600, record["n_ok"], 600, 600)
        self.assertTrue(record["client_coverage_complete"])
        self.assertEqual(result["verdict"], "refuted")

    def test_missing_rows_and_process_error_are_separate(self):
        for fn in (P13["collection_evidence"], P14["arm_evidence"]):
            with self.subTest(fn=fn.__name__):
                missing = fn([{"ok": True}], {}, {}, "", 2)
                self.assertEqual(missing["n_missing"], 1)
                self.assertFalse(missing["client_coverage_complete"])
                failed = fn([{"ok": True}] * 2, {}, {}, "exit 1", 2)
                self.assertEqual(failed["n_missing"], 0)
                self.assertFalse(failed["client_coverage_complete"])

    def test_all_server_and_client_fields_survive_recording(self):
        rows = [{"ok": True, "ms": 50, "ips_eff": 1280, "first_flight_datagrams": 1}]
        cs = {"collection_provenance": {"collection_id": "test"}}
        ss = {"conns": {"cid": {"rx_bytes": 1280, "tx_ns": [1]}}}
        for fn in (P13["collection_evidence"], P14["arm_evidence"]):
            with self.subTest(fn=fn.__name__):
                result = fn(rows, cs, ss, "", 1)
                self.assertEqual(result["client_rows"], rows)
                self.assertEqual(result["client_stats"], cs)
                self.assertEqual(result["server_stats"], ss)

    def test_collectors_preserve_failure_and_unit_provenance_without_network(self):
        rows = [{"ok": True, "ms": 50.0},
                {"ok": False, "ms": 5000.0, "error": "timeout"}]
        server = {"conns": {"first": {"rx_bytes": 1280}}}
        bed = SimpleNamespace(
            set_netem=lambda *a, **k: None,
            start_server=lambda *a, **k: ("process", "stats"),
            run_client=lambda *a, **k: (rows, {}, ""),
            stop_server=lambda *a: None,
            read_server_stats=lambda *a: server,
            pctl=lambda v, q: v[0] if v else None)
        p13 = pure("p13_beff.py", {"run_cond"},
                   B=bed, dt=dt, uuid=uuid, RTT_MS=50.0)
        observed, cs, ss, err = p13["run_cond"]("x25519", 1, "on", 1, 4032, 2)
        self.assertEqual(observed, rows)
        self.assertEqual(ss, server)
        self.assertEqual(cs["collection_provenance"]["n_req"], 2)
        self.assertTrue(cs["collection_provenance"]["collection_id"])
        self.assertLessEqual(cs["collection_provenance"]["started_at"],
                             cs["collection_provenance"]["finished_at"])
        p14 = pure("p14_dominance.py", {"run_arm", "arm_evidence", "mean"},
                   B=bed, dt=dt, uuid=uuid, RTT_MS=50.0, GROUP="x25519",
                   K=1, W=1280, CERT=4032, N=2, UPLINK_MBPS=0.0)
        result = p14["run_arm"]("parity", 0, 1, 5.0)
        self.assertEqual((result["n"], result["ok"], result["n_failed"]), (2, 1, 1))
        self.assertFalse(result["client_coverage_complete"])
        self.assertEqual(result["client_rows"], rows)
        self.assertEqual(result["server_stats"], server)
        self.assertEqual(result["client_stats"]["collection_provenance"]["loss_c2s_percent"], 5.0)

if __name__ == "__main__":
    unittest.main()
