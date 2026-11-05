import ast
import dataclasses
import itertools
from pathlib import Path
import random
import unittest

from experiments.v33 import worldsim as old, worldsim_m1 as new
from experiments.v33.world_receiver_m1 import Receiver
from experiments.v33.hold_decoder import HoldConfig, HoldDecoder, FlightSpec


class M1WorldTests(unittest.TestCase):
    def context(self, **kw):
        return new.WorldContext(**dict(k=2, w=1280, p=0.0, rtt_ms=50.0,
                                      uplink_mbps=2.0, server_bytes=18000, **kw))

    def test_independent_imports(self):
        for name in ("worldsim_m1.py", "world_receiver_m1.py"):
            path = Path(new.__file__).with_name(name)
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                modules = [n.name for n in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                for module in modules:
                    self.assertFalse(module.split(".")[0] in {"padfec", "padfec3", "afec"})
                    self.assertNotIn("hold_decoder", module)
                    self.assertNotIn("hold_layout", module)

    def test_credit_only_replays_frozen_world(self):
        cases = [dict(), dict(p=0.15), dict(p=0.25, loss_model="ge", burst_length=4),
                 dict(p=0.15, s2c_loss=0.1), dict(p=0.15, jitter_mean_ms=20),
                 dict(token=True), dict(retry=True)]
        for seed, change, action in itertools.product((31, 50), cases, ((0, 0, 0), (0, 3, 1), (0, 4, 0), (0, 0, 4))):
            values = dict(k=2, w=1280, p=0.02, rtt_ms=50., uplink_mbps=2., server_bytes=18000)
            values.update(change)
            a = old.World(seed=seed).sample(old.WorldContext(**values), old.Action(*action), trace=True, connection=17)
            b = new.World(params={"lead_mode": "credit_only"}, seed=seed).sample(new.WorldContext(**values), new.Action(*action), trace=True, connection=17)
            a.pop("params_sha256"); b.pop("params_sha256")
            with self.subTest(seed=seed, case=change, action=action):
                self.assertEqual(a, b)

    def test_receiver_boundary_differential(self):
        rng = random.Random(410029)
        for case in range(240):
            k, m = rng.randrange(1, 5), rng.randrange(1, 5)
            lead = rng.randrange(m+1)
            config = HoldConfig(uplink_kbps=rng.choice((0, 1, 2000)), margin_ns=rng.choice((0, 1, 1000000)),
                                ttl_ns=rng.choice((100000, 1000000000)), flight_memory_cap=rng.choice((1, 32768)))
            spec = FlightSpec(tuple(1200+i*17 for i in range(k)), m, lead, 1331)
            a, b = HoldDecoder(spec, config), Receiver(spec.lengths, m, lead, 1331, config.uplink_kbps,
                config.margin_ns, config.ttl_ns, config.recent_ns, config.flight_memory_cap)
            stamp = 0
            for step in range(12):
                stamp += rng.choice((0, 1, 1000, 500000000))
                kind = rng.choice(("o", "p")); index = rng.randrange(k if kind == "o" else m)
                opts = dict(metadata_ok=rng.random() > .1, symbol_ok=rng.random() > .1)
                a.receive_and_drain(kind, index, stamp, **opts)
                b.receive(kind, index, stamp, **opts)
                with self.subTest(case=case, step=step):
                    self.assertEqual({key:a.result()[key] for key in b.result()}, b.result())

    def test_first_parity_anchor_and_nominal_lost_tail(self):
        row = new.World(seed=31).sample(self.context(), new.Action(0,3,1), trace=True,
            overrides={"c2s": [0,1,1,1,0,0]+[1]*100, "decision_delay_ms":0.})
        physical = [r for r in row["arrivals"] if r["flight"] == 0 and r["arrived"]]
        first = next(r for r in physical if r["kind"] == "L")
        expected = round(first["arrival_ms"]*1000000) + (2*1331+2*1280)*4000 + 1000000
        recovered = [r for r in row["trace"] if r["event"] == "fec_recover" and r["flight"] == 0]
        self.assertEqual([r["index"] for r in recovered], [1])
        self.assertEqual(round(recovered[0]["time_ms"]*1000000), expected)
        self.assertFalse(row["initial_failure"])

    def test_fifo_credit_precedes_completing_original(self):
        row = new.World(seed=31).sample(self.context(), new.Action(0,3,1), trace=True,
            overrides={"c2s":[1]*100,"decision_delay_ms":0.})
        packets = [r for r in row["trace"] if r["event"] == "m1_stack" and r["flight"] == 0]
        self.assertEqual([(r["kind"],r["index"]) for r in packets], [("o",0),("p",0),("p",1),("p",2),("o",1)])
        ready = next(i for i,r in enumerate(row["trace"]) if r["event"] == "server_ready")
        prefix = row["trace"][:ready]
        self.assertEqual(sum(r["size"] for r in prefix if r["event"] == "m1_stack"), 2560+3*1331)
        late = next(i for i,r in enumerate(row["trace"]) if r["event"] == "server_receive" and r["kind"] == "P")
        self.assertEqual((row["trace"][late+1]["event"], row["trace"][late+1]["amount"]), ("server_credit", 1331))
        self.assertEqual(row["server_stack_credit_bytes"], row["server_counted_uplink_bytes"])

    def test_all_first_flight_patterns_within_supported_lifetime(self):
        for lead in range(5):
            for pattern in itertools.product((0,1), repeat=6):
                row = new.World(params={"features":{"retransmissions":False}},seed=31).sample(
                    self.context(),new.Action(0,lead,4-lead),trace=True,
                    overrides={"c2s":list(pattern)+[1]*100,"decision_delay_ms":0.})
                with self.subTest(lead=lead,pattern=pattern):
                    self.assertEqual(row["initial_failure"],sum(pattern)<2)
                    self.assertLessEqual(row["server_stack_credit_bytes"],row["server_counted_uplink_bytes"])

    def lead_zero_pair(self, values, action, seed, connection, overrides=None):
        context = new.WorldContext(**values)
        off = new.World(params={"lead_mode": "credit_only"}, seed=seed).sample(context, action, connection=connection, trace=True, overrides=overrides)
        hold = new.World(seed=seed).sample(context, action, connection=connection, trace=True, overrides=overrides)
        return off, hold

    def assert_lead_zero_equal(self, off, hold):
        sends = lambda row: [(r["time_ms"], r["kind"], r["size"], r["arrived"], r["retransmission"])
                             for r in row["trace"] if r["event"] == "server_send"]
        self.assertEqual(off["hct"], hold["hct"])
        self.assertEqual(sends(off), sends(hold))
        self.assertEqual(off["server_dgram_sizes"], hold["server_dgram_sizes"])
        skip = {"trace", "params_sha256", "event_count"}
        self.assertEqual({k: v for k, v in off.items() if k not in skip}, {k: v for k, v in hold.items() if k not in skip})

    def test_lead_zero_hold_matches_off_across_loss_seeds_and_contexts(self):
        contexts = {"bigcert": dict(k=2, w=1280, rtt_ms=50., uplink_mbps=2., cert_bytes=16000),
                    "B7": dict(k=2, w=1280, rtt_ms=50., uplink_mbps=2., cert_bytes=9000, s2c_loss=0.01)}
        for (name, base), p, seed, delta, trailing in itertools.product(contexts.items(), (0., .02, .15, .25), (31, 50), (0, 12), range(5)):
            values = dict(base, p=p)
            for connection in range(40):
                off, hold = self.lead_zero_pair(values, new.Action(delta, 0, trailing), seed, connection)
                with self.subTest(context=name, p=p, seed=seed, action=(delta, 0, trailing), connection=connection):
                    self.assert_lead_zero_equal(off, hold)

    def test_lead_zero_hold_matches_off_with_token_and_retry(self):
        contexts = {"bigcert": dict(k=2, w=1280, rtt_ms=50., uplink_mbps=2., cert_bytes=16000),
                    "B7": dict(k=2, w=1280, rtt_ms=50., uplink_mbps=2., cert_bytes=9000, s2c_loss=0.01)}
        variants = {"token": dict(token=True), "retry": dict(retry=True)}
        for (name, base), (variant, change), p, seed, delta, trailing in itertools.product(
                contexts.items(), variants.items(), (0., .02, .15, .25), (31, 50), (0, 12), range(5)):
            values = dict(base, p=p, **change)
            for connection in range(20):
                off, hold = self.lead_zero_pair(values, new.Action(delta, 0, trailing), seed, connection)
                with self.subTest(context=name, variant=variant, p=p, seed=seed, action=(delta, 0, trailing), connection=connection):
                    self.assert_lead_zero_equal(off, hold)

    def test_retry_initial_failure_follows_first_flight_pattern(self):
        context = self.context(retry=True)
        for lead in range(5):
            for pattern in itertools.product((0, 1), repeat=6):
                row = new.World(params={"features": {"retransmissions": False}}, seed=31).sample(
                    context, new.Action(0, lead, 4 - lead),
                    overrides={"c2s": list(pattern) + [1] * 100, "decision_delay_ms": 0.})
                with self.subTest(lead=lead, pattern=pattern):
                    self.assertEqual(row["initial_failure"], sum(pattern) < 2)
                    self.assertEqual(row["world_class"] == "failure", row["initial_failure"] or not row["ok"])

    def test_lead_zero_regressions_from_audit(self):
        values = dict(k=2, w=1280, rtt_ms=50., uplink_mbps=2., cert_bytes=16000, p=0.25)
        off, hold = self.lead_zero_pair(values, new.Action(0, 0, 1), 31, 2041)
        self.assert_lead_zero_equal(off, hold)
        for trailing in (3, 4):
            off, hold = self.lead_zero_pair(dataclasses.asdict(self.context()), new.Action(0, 0, trailing), 31, 0,
                                            {"c2s": [1] * 200, "decision_delay_ms": 0.})
            self.assert_lead_zero_equal(off, hold)
            self.assertAlmostEqual(off["hct"], 117.96, places=6)

    def test_parity_after_ready_is_credit_not_recovery(self):
        values = dict(k=2, w=1280, rtt_ms=50., uplink_mbps=2., cert_bytes=16000, p=0.)
        overrides = {"c2s": [1, 0, 0, 0, 1, 1] + [1] * 200, "decision_delay_ms": 0.}
        off, hold = self.lead_zero_pair(values, new.Action(0, 0, 1), 31, 0, overrides)
        self.assert_lead_zero_equal(off, hold)
        self.assertEqual(hold["server_stack_credit_bytes"], 6537)
        self.assertFalse([r for r in hold["trace"] if r["event"] == "fec_recover"])

    def test_receiver_deadline_uses_d20_uplink_unless_context_requested(self):
        overrides = {"c2s": [0, 1, 1, 1, 0, 0] + [1] * 100, "decision_delay_ms": 0.}
        for source, per_byte in (("fixed", 4000), ("context", 800)):
            params = None if source == "fixed" else {"hold_uplink_source": "context"}
            context = new.WorldContext(k=2, w=1280, p=0., rtt_ms=50., uplink_mbps=10., server_bytes=18000)
            row = new.World(params=params, seed=31).sample(context, new.Action(0, 3, 1), trace=True, overrides=overrides)
            first = next(r for r in row["arrivals"] if r["flight"] == 0 and r["arrived"] and r["kind"] == "L")
            recovered = [r for r in row["trace"] if r["event"] == "fec_recover" and r["flight"] == 0]
            expected = round(first["arrival_ms"] * 1000000) + (2 * 1331 + 2 * 1280) * per_byte + 1000000
            with self.subTest(source=source):
                self.assertEqual(round(recovered[0]["time_ms"] * 1000000), expected)
        self.assertEqual(new.load_params()["fec"]["hold_uplink_kbps"], 2000)
        self.assertEqual(new.load_params()["fec"]["hold_uplink_source"], "fixed")
        new.World().sample(new.WorldContext(k=2, w=1280, p=0., rtt_ms=50., uplink_mbps=2.0005, server_bytes=18000), new.Action(0, 1, 1))
        with self.assertRaises(ValueError):
            new.World(params={"hold_uplink_source": "context"}).sample(
                new.WorldContext(k=2, w=1280, p=0., rtt_ms=50., uplink_mbps=2.0005, server_bytes=18000), new.Action(0, 1, 1))
        with self.assertRaises(ValueError):
            new.World(params={"hold_uplink_source": "true"})

    def test_buffered_unsupported_profiles_are_rejected(self):
        with self.assertRaises(ValueError):
            new.World(profile="policy_equivalent")
        with self.assertRaises(ValueError):
            new.World().sample(self.context(),new.Action(0,1,0,order=("O","L","O")))
        with self.assertRaises(ValueError):
            new.World(params={"fec":{"retransmission_shape":"originals_first"}}).sample(self.context(),new.Action())


if __name__ == "__main__":
    unittest.main()
