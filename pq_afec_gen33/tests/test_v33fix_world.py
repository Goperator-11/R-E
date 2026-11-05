import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from experiments.v33 import initial_count_diag as initial, j8_pto_impact as j8, world_ack_profile as ack
from experiments.v33 import worldsim
from experiments.v33.worldsim import Action, World, WorldContext


ROOT = Path(__file__).resolve().parents[1]
DIAG = ROOT / "g3" / "v33" / "V33FIX_world_diag_v1.json"
ACK_RESULT = ROOT / "g3" / "v33" / "V33FIX_ack_sensitivity_v1.json"


class FrozenWorldTests(unittest.TestCase):
    def test_frozen_world_sources_still_match_bench_protocol(self):
        protocol = json.loads((ROOT / "g3" / "v33" / "bench_protocol.json").read_text(encoding="utf-8"))
        for name, digest in protocol["world"]["source_sha256"].items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256((ROOT / "experiments" / "v33" / name).read_bytes()).hexdigest(), digest)


class AckProfileTests(unittest.TestCase):
    def test_c6000_reference_is_a_one_byte_knife_edge_and_margin30_is_not(self):
        context = WorldContext(k=2, w=1280, p=0.0, rtt_ms=120.0, uplink_mbps=10.0, cert_bytes=6000)
        values = {}
        for size in (28, 41, 42, 54):
            world = World({"server": {"preflight_ack_bytes": size}}, seed=31)
            for action in ((7, 0, 4), (12, 0, 4)):
                values[size, action] = world.sample(context, Action(*action), overrides={"decision_delay_ms": 0.}, connection=0)["hct"]
        self.assertEqual(values[28, (7, 0, 4)], values[41, (7, 0, 4)])
        self.assertGreater(values[42, (7, 0, 4)] - values[41, (7, 0, 4)], 100.0)
        self.assertEqual(len({values[size, (12, 0, 4)] for size in (28, 41, 42, 54)}), 1)

    def test_profiles_change_only_the_declared_inputs(self):
        self.assertEqual(ack.world_params("world_default", 41, 2), {"server": {"preflight_ack_bytes": 41}})
        self.assertEqual(ack.world_params("physical_fit", 30, 2)["server"],
                         {"preflight_ack_bytes": 30, "s0_mlkem_bytes": 1589.92, "packet_overhead_bytes": 40.05})
        self.assertEqual(ack.world_params("physical_fit", 30, 1)["server"]["packet_overhead_bytes"], 40.21)
        sealed = ack.context_for("B12_c12000_p0.08", "sealed_c12000_low")
        self.assertNotIn("cert_bytes", sealed)
        self.assertEqual(sealed["server_bytes"], 14017)
        self.assertEqual(ack.context_for("B4", "world_default")["cert_bytes"], 4032)
        for job in ack.jobs(4, 1):
            name, profile, size, action = job[:4]
            self.assertIn(action, ack.ROLES[name])
            self.assertTrue(28 <= size <= 54)

    def test_ack_source_does_not_claim_sealed_range(self):
        self.assertIn("Not a sealed measurement", ack.ACK_SOURCE["range_28_54"])

    @unittest.skipUnless(ACK_RESULT.exists(), "ACK sensitivity result not present")
    def test_published_ack_table_is_internally_consistent(self):
        data = json.loads(ACK_RESULT.read_text(encoding="utf-8"))
        rows = {(r["context_name"], r["profile"], r["ack_bytes"], tuple(r["action"])): r for r in data["rows"]}
        self.assertEqual(len(rows), len(data["rows"]))
        for item in data["cliffs"]:
            if item["first_ack_bytes_with_jump_over_half_rtt"] is not None:
                self.assertIn(item["action"], ([7, 0, 4], [7, 0, 2]))
                self.assertEqual(item["first_ack_bytes_with_jump_over_half_rtt"], 42)


class InitialCountTests(unittest.TestCase):
    def test_key_discard_definition_drops_reply_retransmissions_only(self):
        row = {"arrivals": [{"kind": kind} for kind in "OOPPRQRQA"], "initial_datagrams": 4, "ok": True, "hct": 283.}
        self.assertEqual(initial.counts(row), (4, 3))
        self.assertEqual(initial.classify(row, 4), "failure_or_initial_retransmission")
        self.assertEqual(initial.classify(row, 3), "tail")
        bad = {"arrivals": [{"kind": kind} for kind in "OORB"], "initial_datagrams": 4}
        with self.assertRaises(AssertionError):
            initial.counts(bad)

    def test_lost_reply_moves_from_retransmission_to_tail_class(self):
        context = WorldContext(k=2, w=1280, p=0.0, rtt_ms=50.0, uplink_mbps=2.0, cert_bytes=16000)
        row = World(seed=31).sample(context, Action(0, 0, 4), overrides={"c2s": [1] * 6 + [0, 0] + [1] * 100, "decision_delay_ms": 0.})
        w0, key = initial.counts(row)
        self.assertEqual((w0, key), (4, 3))
        self.assertEqual(initial.classify(row, w0), "failure_or_initial_retransmission")
        self.assertEqual(initial.classify(row, key), "tail")

    def test_merge_section_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "diag.json"
            initial.merge_section(path, "a", {"x": 1})
            initial.merge_section(path, "b", {"y": 2})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["sections"], {"a": {"x": 1}, "b": {"y": 2}})
            with self.assertRaises(ValueError):
                initial.merge_section(path, "a", {"x": 3})

    @unittest.skipUnless(DIAG.exists(), "diagnostics not present")
    def test_published_initial_section_reproduces_w0(self):
        section = json.loads(DIAG.read_text(encoding="utf-8"))["sections"]["initial_count"]
        self.assertTrue(all(section["w0_reproduced_exactly"].values()))
        rows = {row["id"]: row for row in section["rows"]}
        auto = rows["bigcert_15_g3auto_0"]["checks"]
        self.assertFalse(auto["w0"]["tail"]["within_w0_tolerance"])
        self.assertTrue(all(item["within_w0_tolerance"] for item in auto["key_discard"].values()))


class J8PatchTests(unittest.TestCase):
    def test_patch_applies_once_and_leaves_the_file_unchanged(self):
        before = hashlib.sha256(Path(worldsim.__file__).read_bytes()).hexdigest()
        text = j8.patched_source()
        for old, new in j8.PATCHES:
            self.assertEqual(text.count(new), 1)
        self.assertEqual(hashlib.sha256(Path(worldsim.__file__).read_bytes()).hexdigest(), before)
        self.assertIsNot(j8.patched_module().World, World)

    def test_no_server_loss_is_identical_and_lost_first_data_finishes_no_later(self):
        module = j8.patched_module()
        values = dict(k=2, w=1280, p=0.02, rtt_ms=50.0, uplink_mbps=2.0, cert_bytes=9000)
        for connection in range(30):
            a = World(seed=31).sample(WorldContext(**values), Action(0, 1, 2), connection=connection)
            b = module.World(seed=31).sample(module.WorldContext(**values), module.Action(0, 1, 2), connection=connection)
            self.assertEqual(a["hct"], b["hct"])
        values.update(p=0.0)
        overrides = {"s2c": [1, 0] + [1] * 100, "decision_delay_ms": 0.}
        a = World(seed=31).sample(WorldContext(**values), Action(0, 1, 2), overrides=overrides)
        b = module.World(seed=31).sample(module.WorldContext(**values), module.Action(0, 1, 2), overrides=overrides)
        self.assertLess(b["hct"], a["hct"])
        self.assertEqual(a["server_retransmission_bytes"], b["server_retransmission_bytes"])

    @unittest.skipUnless(DIAG.exists(), "diagnostics not present")
    def test_published_j8_section_reproduces_stored_tables(self):
        section = json.loads(DIAG.read_text(encoding="utf-8"))["sections"]["j8_pto"]
        self.assertTrue(section["w0_tables_reproduce_j6_pool"])
        self.assertTrue(all(section["w0_tables_reproduce_j6_pool"].values()))
        self.assertEqual(section["world_source_sha256"], hashlib.sha256(Path(worldsim.__file__).read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
