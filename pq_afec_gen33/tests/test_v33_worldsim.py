import ast
import dataclasses
import math
from pathlib import Path
import subprocess
import sys
import unittest

from experiments.v33.worldsim import Action, World, WorldContext

ROOT = Path(__file__).resolve().parents[1]


class WorldSimulationTests(unittest.TestCase):
    def context(self, **changes):
        values = {"k": 2, "w": 1280, "p": 0.0, "rtt_ms": 50.0, "uplink_mbps": 2.0, "server_bytes": 5000}
        values.update(changes)
        return WorldContext(**values)

    def test_world_has_no_policy_imports(self):
        source = ROOT / "experiments/v33/worldsim.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            self.assertFalse(any(name.split(".")[0] in {"padfec", "padfec3", "afec"} for name in modules), modules)

    def test_world_runs_when_policy_imports_are_blocked(self):
        code = """import sys, builtins
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {'padfec', 'padfec3', 'afec'}:
        raise RuntimeError('policy import forbidden')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from experiments.v33.worldsim import Action, World, WorldContext
row = World(seed=7).sample(WorldContext(k=2, w=1280, p=0.0, rtt_ms=50.0, uplink_mbps=2.0, server_bytes=5000), Action(0,0,0))
assert row['ok'] and row['hct'] > 0
"""
        result = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(ROOT)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_connection_replay_is_independent_of_call_order(self):
        context = self.context(p=0.15, s2c_loss=0.02)
        action = Action(0, 3, 1)
        one = World(seed=1984)
        wanted = one.sample(context, action, connection=9)
        one.sample(context, Action(0, 0, 0), connection=1)
        self.assertEqual(wanted, one.sample(context, action, connection=9))
        self.assertEqual(wanted, World(seed=1984).sample(context, action, connection=9))

    def test_successful_lossless_connection_has_explicit_accounting(self):
        row = World(seed=3).sample(self.context(), Action(0, 0, 0), trace=True)
        self.assertTrue(row["ok"])
        self.assertFalse(row["initial_failure"])
        self.assertGreaterEqual(row["hct"], 50.0)
        self.assertEqual(row["k_obs"], 2)
        self.assertEqual(row["client_first_flight_bytes"], 2560)
        self.assertGreaterEqual(row["client_total_uplink_bytes"], row["client_first_flight_bytes"])
        self.assertLessEqual(row["server_counted_uplink_bytes"], row["client_total_uplink_bytes"])
        self.assertGreaterEqual(sum(row["server_dgram_sizes"]), row["srv_bytes"])
        self.assertGreaterEqual(row["srv_bytes"], 5000)
        self.assertGreaterEqual(row["rtt"], 50.0)
        self.assertTrue(row["arrivals"])
        self.assertIn("trace", row)

    def test_all_loss_has_bounded_failure_and_zero_server_reception(self):
        row = World(seed=3).sample(self.context(p=1.0), Action(0, 3, 1))
        self.assertFalse(row["ok"])
        self.assertTrue(row["initial_failure"])
        self.assertTrue(math.isfinite(row["hct"]))
        self.assertEqual(row["server_counted_uplink_bytes"], 0)
        self.assertEqual(row["srv_bytes"], 0)
        self.assertGreater(row["pto_count"], 0)

    def test_token_releases_amplification_limit(self):
        context = self.context(server_bytes=18000)
        action = Action(0, 0, 0)
        limited = World(seed=3).sample(context, action)
        validated = World(seed=3).sample(dataclasses.replace(context, token=True), action)
        self.assertTrue(limited["ok"] and validated["ok"])
        self.assertGreater(limited["hct"], validated["hct"])
        self.assertGreaterEqual(limited["hct"] - validated["hct"], context.rtt_ms - 1e-9)

    def test_retry_adds_round_trip_and_transmission(self):
        context = self.context()
        action = Action(0, 0, 0)
        base = World(seed=3).sample(context, action)
        retried = World(seed=3).sample(dataclasses.replace(context, retry=True), action)
        self.assertTrue(retried["ok"])
        self.assertGreaterEqual(retried["hct"] - base["hct"], context.rtt_ms - 1e-9)
        self.assertGreater(retried["client_total_uplink_bytes"], base["client_total_uplink_bytes"])

    def test_lost_retry_is_reissued_on_a_later_initial(self):
        context = self.context(retry=True)
        row = World(seed=3).sample(context, Action(), overrides={"s2c": [False] + [True] * 64}, trace=True)
        self.assertTrue(row["ok"])
        retries = [event for event in row["trace"] if event["event"] == "server_send" and event["kind"] == "retry"]
        self.assertGreaterEqual(len(retries), 2)

    def test_both_profiles_are_identified_in_observations(self):
        context = self.context(n_need=4)
        action = Action(0, 0, 1)
        default = World(seed=3).sample(context, action)
        equivalent = World(profile="policy_equivalent", seed=3).sample(context, action)
        self.assertNotEqual(default["model_kind"], equivalent["model_kind"])

    def test_rs_symbols_from_different_retransmission_flights_do_not_mix(self):
        context = self.context(uplink_mbps=0.0)
        mask = [True, False, False, False, False, True] + [True] * 64
        row = World(seed=3).sample(context, Action(0, 0, 1), overrides={"c2s": mask}, trace=True)
        self.assertTrue(row["ok"])
        self.assertGreaterEqual(row["initial_datagrams"], 7)
        self.assertGreaterEqual(row["pto_count"], 2)

    def test_exact_budget_blocks_one_byte_overshoot(self):
        context = self.context(k=1, uplink_mbps=0.0, server_bytes=0, server_dgram_sizes=(1280, 1280, 1281))
        action = Action(0, 0, 0)
        granular = World(params={"server": {"mode": "granular"}}, seed=3).sample(context, action)
        exact = World(params={"server": {"mode": "exact"}}, seed=3).sample(context, action)
        self.assertTrue(granular["ok"] and exact["ok"])
        self.assertGreaterEqual(exact["hct"] - granular["hct"], context.rtt_ms - 1e-9)

    def test_congestion_window_remains_active_with_valid_token(self):
        context = self.context(server_bytes=18000, token=True, uplink_mbps=0.0)
        action = Action(0, 0, 0)
        large = World(params={"server": {"iw_packets": 32}}, seed=3).sample(context, action)
        small = World(params={"server": {"iw_packets": 10}}, seed=3).sample(context, action)
        self.assertTrue(large["ok"] and small["ok"])
        self.assertGreaterEqual(small["hct"] - large["hct"], context.rtt_ms - 1e-9)

    def test_dropped_datagram_can_consume_serialization_time(self):
        context = self.context()
        action = Action(0, 1, 0)
        overrides = {"c2s": [False, True, True] + [True] * 64, "decision_delay_ms": 0.0}
        before_link = World(params={"channel": {"lost_consumes_uplink": False}}, seed=3).sample(context, action, overrides=overrides)
        after_link = World(params={"channel": {"lost_consumes_uplink": True}}, seed=3).sample(context, action, overrides=overrides)
        self.assertTrue(before_link["ok"] and after_link["ok"])
        self.assertAlmostEqual(after_link["hct"] - before_link["hct"], 1331 * 8 / 2000, delta=1e-9)

    def test_s2c_loss_does_not_change_first_c2s_pattern(self):
        context = self.context(p=0.15)
        action = Action(0, 3, 1)
        no_downlink_loss = World(seed=7).sample(context, action, connection=17)
        downlink_loss = World(seed=7).sample(dataclasses.replace(context, s2c_loss=0.2), action, connection=17)
        self.assertEqual(no_downlink_loss["initial_arrival_pattern"], downlink_loss["initial_arrival_pattern"])

    def test_buffered_lead_waits_for_deadline_when_last_slots_are_lost(self):
        context = self.context()
        action = Action(0, 3, 1)
        mask = [True, True, True, True, False, False] + [True] * 64
        row = World(params={"fec": {"lead_mode": "buffered", "hold_margin_ms": 0.3}}, seed=3).sample(context, action, overrides={"c2s": mask}, trace=True)
        self.assertTrue(row["ok"])
        recovered = [event for event in row["trace"] if event["event"] == "fec_recover" and event["flight"] == 0]
        self.assertTrue(recovered)
        deadline = (4 * 1331 + 2 * 1280) * 8 / 2000 + context.rtt_ms / 2 + 0.3
        self.assertGreaterEqual(min(event["time_ms"] for event in recovered), deadline - 1e-9)

    def test_truncated_parity_arrives_but_cannot_recover_a_missing_original(self):
        context = self.context(w=1406, uplink_mbps=0.0)
        action = Action(0, 0, 1)
        overrides = {"c2s": [True, False, True] + [True] * 64}
        clipped = World(seed=3).sample(context, action, overrides=overrides)
        complete = World(params={"server": {"decoder_max_datagram_bytes": 1472}}, seed=3).sample(context, action, overrides=overrides)
        self.assertTrue(clipped["ok"] and complete["ok"])
        self.assertTrue(clipped["initial_failure"])
        self.assertFalse(complete["initial_failure"])
        self.assertGreater(clipped["hct"], complete["hct"])
        parity = next(row for row in clipped["arrivals"] if row["flight"] == 0 and row["kind"] == "P")
        self.assertTrue(parity["arrived"])
        self.assertFalse(parity["usable"])
        self.assertEqual(parity["size"], 1457)
        self.assertEqual(parity["read_size"], 1452)
        self.assertGreater(clipped["server_wire_received_bytes"], clipped["server_counted_uplink_bytes"])

    def test_certificate_schedule_and_mix_are_environment_inputs(self):
        context = self.context(server_bytes=0, cert_bytes=9000, cert_schedule=((2, 16000),))
        world = World(seed=8)
        before = world.sample(context, Action(), connection=1)
        after = world.sample(context, Action(), connection=2)
        self.assertEqual(before["selected_cert_bytes"], 9000)
        self.assertEqual(after["selected_cert_bytes"], 16000)
        self.assertGreater(after["server_first_flight_bytes"], before["server_first_flight_bytes"])
        mixed = dataclasses.replace(context, cert_schedule=(), cert_mix=(9000, 16000))
        selected = {world.sample(mixed, Action(), connection=i)["selected_cert_bytes"] for i in range(32)}
        self.assertEqual(selected, {9000, 16000})


if __name__ == "__main__":
    unittest.main()
