import unittest

from experiments.v33.hold_decoder import FlightSpec, HoldConfig, HoldDecoder


class HoldDecoderTests(unittest.TestCase):
    def decoder(self, k=2, m=3, lead=3, **config):
        return HoldDecoder(FlightSpec((1280,) * k, m, lead, 1331), HoldConfig(**config))

    def receive(self, d, kind, index, when, **kwargs):
        d.receive(kind, index, when, **kwargs)
        return d.drain()

    def test_unused_lead_precedes_completing_original(self):
        d = self.decoder()
        for i in range(3):
            self.assertEqual(self.receive(d, "p", i, i), [])
        self.assertEqual([(p.kind, p.index) for p in self.receive(d, "o", 0, 3)], [("o", 0)])
        out = self.receive(d, "o", 1, 4)
        self.assertEqual([(p.kind, p.index) for p in out], [("p", 0), ("p", 1), ("p", 2), ("o", 1)])
        self.assertEqual(d.result()["bytes_to_stack"], 6553)
        self.assertEqual(d.recovered, [])

    def test_last_original_loss_recovered_by_timer(self):
        d = self.decoder(m=2, lead=2)
        self.receive(d, "p", 0, 10)
        self.receive(d, "p", 1, 20)
        self.receive(d, "o", 0, 30)
        deadline = 10 + (1331 + 2560) * 4000 + 1_000_000
        self.assertEqual(d.deadline_ns, deadline)
        d.advance(deadline - 1)
        self.assertFalse(d.decision_open)
        d.advance(deadline)
        out = d.drain()
        self.assertEqual([(p.kind, p.index, p.recovered) for p in out], [("p", 1, False), ("o", 1, True)])
        self.assertEqual(d.used, [0])
        self.assertEqual(d.consumed_overhead, 51)
        self.assertTrue(d.result()["complete"])

    def test_trailing_is_used_before_lead(self):
        d = self.decoder(k=4, m=4, lead=2)
        for i, t in ((0, 10), (1, 20), (2, 30)):
            self.receive(d, "p", i, t)
        self.assertTrue(d.decision_open)
        out = self.receive(d, "o", 0, 40)
        self.assertEqual(d.used, [2, 0, 1])
        self.assertEqual([(p.index, p.recovered) for p in out], [(0, False), (1, True), (2, True), (3, True)])

    def test_decision_remains_open_after_insufficient_deadline(self):
        d = self.decoder(k=4, m=4, lead=4)
        self.receive(d, "p", 0, 1)
        d.advance(d.deadline_ns)
        self.assertTrue(d.decision_open)
        t = d.now_ns
        self.receive(d, "o", 0, t + 1)
        self.receive(d, "o", 1, t + 2)
        self.receive(d, "p", 1, t + 3)
        self.assertEqual(d.recovered, [2, 3])
        self.assertTrue(d.result()["complete"])

    def test_timer_wins_tie_and_late_original_is_physical(self):
        d = self.decoder(m=1, lead=1)
        self.receive(d, "p", 0, 0)
        self.receive(d, "o", 0, 1)
        out = self.receive(d, "o", 1, d.deadline_ns)
        self.assertEqual([(p.index, p.recovered) for p in out], [(1, True), (1, False)])
        self.assertEqual(d.recovered, [1])
        self.assertEqual(d.bytes_in, 3891)
        self.assertEqual(d.bytes_to_stack, 3840)

    def test_originals_before_metadata_are_not_held(self):
        d = self.decoder()
        self.receive(d, "o", 1, 1)
        self.receive(d, "o", 0, 2)
        self.assertIsNone(d.created_ns)
        self.assertTrue(d.result()["complete"])
        self.receive(d, "p", 0, 3)
        self.assertEqual([p.kind for p in d.delivered], ["o", "o", "p"])
        self.assertEqual(d.recovered, [])

    def test_duplicate_and_conflicting_metadata_cannot_add_rank(self):
        d = self.decoder(k=3)
        self.receive(d, "p", 0, 0)
        self.receive(d, "p", 0, 1)
        self.receive(d, "p", 1, 2, metadata_ok=False)
        d.advance(d.deadline_ns)
        d.drain()
        self.assertEqual(len(d.held), 1)
        self.assertEqual(d.recovered, [])
        self.assertEqual(d.discard_bytes, 2662)
        self.assertEqual(d.discards["duplicate"], 1331)
        self.assertEqual(d.discards["metadata"], 1331)

    def test_crc_failure_discards_atomically(self):
        d = self.decoder(m=2, lead=2)
        self.receive(d, "p", 0, 0, symbol_ok=False)
        self.receive(d, "p", 1, 1)
        d.advance(d.deadline_ns)
        self.assertEqual(d.terminal, "crc")
        self.assertEqual(d.pending, [])
        self.assertEqual(d.discard_bytes, 2662)
        self.assertEqual(d.recovered, [])

    def test_expiry_clears_held_once_and_does_not_rearm(self):
        d = self.decoder(k=4, ttl_ns=100_000_000)
        self.receive(d, "p", 0, 100)
        d.advance(100_000_100)
        self.assertEqual(d.terminal, "expired")
        self.assertEqual(d.held_bytes, 0)
        self.assertEqual(d.discard_bytes, 1331)
        self.receive(d, "p", 1, 100_000_101)
        d.advance(2_000_000_000)
        self.assertEqual(d.discard_bytes, 1331)
        self.assertEqual(d.recovered, [])

    def test_cap_discard_does_not_become_recovery_credit(self):
        d = self.decoder(k=3, flight_memory_cap=3000)
        self.receive(d, "p", 0, 0)
        self.receive(d, "p", 1, 1)
        self.assertEqual(d.terminal, "cap")
        self.assertEqual(d.discards["cap"], 1331)
        self.receive(d, "p", 2, 2)
        self.assertEqual(d.bytes_to_stack, 2662)
        self.assertFalse(d.result()["complete"])

    def test_small_buffer_accounts_only_copied_bytes(self):
        d = self.decoder(k=1, m=1, lead=1)
        d.receive("p", 0, 0)
        d.advance(d.deadline_ns)
        packet = d.read(7)
        self.assertEqual(packet.size, 7)
        self.assertEqual(d.bytes_to_stack, 7)
        self.assertEqual(d.pending_bytes, 0)
        self.assertEqual(d.discards["truncated"], 1273)
        self.assertFalse(d.result()["complete"])

    def test_unequal_original_lengths_replace_consumed_parity(self):
        d = HoldDecoder(FlightSpec((1200, 1280), 2, 2, 1331))
        self.receive(d, "p", 1, 0)
        self.receive(d, "p", 0, 1)
        d.advance(d.deadline_ns)
        d.drain()
        self.assertEqual([p.size for p in d.delivered], [1200, 1280])
        self.assertEqual(d.consumed_overhead, 182)
        self.assertEqual(d.used, [0, 1])

    def test_no_metadata_and_no_packets_cannot_create_timer(self):
        d = self.decoder()
        d.advance(10_000_000_000)
        self.assertEqual(d.events, [])
        self.assertIsNone(d.created_ns)
        self.assertEqual(d.bytes_in, 0)

    def test_deadline_at_ttl_is_explicit_fallback(self):
        d = self.decoder(m=1, lead=1, ttl_ns=11_240_000)
        self.receive(d, "p", 0, 10)
        self.assertEqual(d.terminal, "unsupported_deadline")
        self.assertEqual(d.bytes_to_stack, 1331)
        self.assertEqual(d.recovered, [])

    def test_reordering_uses_first_observed_slot_without_future_inputs(self):
        d = self.decoder(k=4, m=4, lead=4)
        self.receive(d, "p", 3, 100)
        self.assertEqual(d.deadline_ns, 100 + 5120 * 4000 + 1_000_000)
        deadline = d.deadline_ns
        self.receive(d, "p", 0, 1000)
        self.assertEqual(d.deadline_ns, deadline)

    def test_recent_original_cache_expires_at_boundary(self):
        d = self.decoder(m=1, lead=1, uplink_kbps=0, margin_ns=1)
        self.receive(d, "o", 0, 0)
        self.receive(d, "p", 0, d.config.recent_ns)
        d.advance(d.deadline_ns)
        self.assertEqual(d.recovered, [])
        self.assertEqual(d.terminal, None)

    def test_invalid_input_is_rejected_before_mutation(self):
        d = self.decoder()
        for args in (("o", 4, 0), ("x", 0, 0), ("p", True, 0), ("o", 0, -1)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                d.receive(*args)
            self.assertEqual(d.bytes_in, 0)
        for kwargs in ({"uplink_kbps": True}, {"margin_ns": -1}, {"ttl_ns": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                HoldConfig(**kwargs)

    def test_read_scheduler_services_timer_before_later_input(self):
        d = self.decoder(m=1, lead=1)
        d.receive_and_drain("p",0,0)
        d.receive_and_drain("o",0,1)
        deadline = d.deadline_ns
        out = d.receive_and_drain("o",1,deadline+1234)
        self.assertEqual([(p.index,p.recovered,p.at_ns) for p in out], [(1,True,deadline),(1,False,deadline+1234)])
        reads = [e for e in d.events if e["event"] == "read"]
        self.assertEqual(reads[-2]["bytes_in"], 2611)
        self.assertEqual(reads[-1]["bytes_in"], 3891)

    def test_read_scheduler_at_deadline_keeps_physical_prefix(self):
        d = self.decoder(m=1, lead=1)
        d.receive_and_drain("p",0,0)
        d.receive_and_drain("o",0,1)
        deadline = d.deadline_ns
        d.receive_and_drain("o",1,deadline)
        rows = [e for e in d.events if e["at_ns"] == deadline]
        self.assertEqual([e["event"] for e in rows], ["deadline","read","original","read"])
        self.assertEqual(rows[1]["bytes_in"],2611)

    def test_symbol_padding_counts_toward_memory_cap(self):
        d = HoldDecoder(FlightSpec((1200,1217),2,2,1331,1285),HoldConfig())
        d.receive_and_drain("p",0,0)
        self.assertEqual(d.held_memory,2616)


if __name__ == "__main__":
    unittest.main()
