import itertools
import importlib.util
import math
import struct
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from afec.channel import GilbertElliott
from afec.controller import AdaptiveFecController, FecConfig
from afec.rs import RSErasureCode
from padfec.codec import FlightCode
from padfec import policy, quantum


def load_shim(name):
    spec = importlib.util.spec_from_file_location(
        "core_audit_" + name, ROOT / "experiments/quicbed" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScriptSocket:
    def __init__(self, packets=()):
        self.packets = iter(packets)
        self.written = []

    def recvfrom(self, size):
        try:
            return next(self.packets), ("127.0.0.1", 5555)
        except StopIteration:
            raise OSError("end of scripted packets") from None

    def sendto(self, payload, target):
        self.written.append((payload, target))
        return len(payload)


class ShimDuplicateAudit(unittest.TestCase):
    def receiver(self, shim, packets):
        rx = shim.ShimRx.__new__(shim.ShimRx)
        rx.flights = {}
        rx.stats = dict.fromkeys(("recovered", "delivered", "parity_rx",
                                 "unrecoverable_seen", "flights", "flight_id_wraps",
                                 "srv_rx_bytes", "srv_tx_bytes", "srv_rx_dgrams",
                                 "srv_tx_dgrams"), 0)
        rx.sock_in = ScriptSocket(packets)
        rx.sock_srv = ScriptSocket()
        rx.stop = SimpleNamespace(is_set=lambda: False)
        rx.target = ("127.0.0.1", 4433)
        rx.trace_path = ""
        return rx

    def test_repeated_parity_and_late_original_count_one_recovery(self):
        shim = load_shim("shim")
        source = (b"abc", b"def")
        original = shim.pack(shim.T_DATA, 1, 0, 2, source[0])
        late = shim.pack(shim.T_DATA, 1, 1, 2, source[1])
        parity = shim.pack(shim.T_PARITY, 1, 2, 2,
                           bytes(a ^ b for a, b in zip(*source)))
        rx = self.receiver(shim, (original, parity, parity, original, late, parity))
        rx._from_peer()
        self.assertEqual(rx.stats["recovered"], 1)
        self.assertEqual(rx.stats["delivered"], 2)
        self.assertEqual([p for p, _ in rx.sock_srv.written], list(source))

    def test_repeated_parity_without_loss_does_not_count_recovery(self):
        shim = load_shim("shim")
        source = (b"abc", b"def")
        originals = [shim.pack(shim.T_DATA, 1, i, 2, p) for i, p in enumerate(source)]
        parity = shim.pack(shim.T_PARITY, 1, 2, 2,
                           bytes(a ^ b for a, b in zip(*source)))
        rx = self.receiver(shim, originals + [parity, parity])
        rx._from_peer()
        self.assertEqual(rx.stats["recovered"], 0)
        self.assertEqual([p for p, _ in rx.sock_srv.written], list(source))

    def test_data_shim_does_not_repeat_completed_recovery(self):
        shim = load_shim("shim_data")
        rx = shim.DataRx.__new__(shim.DataRx)
        rx.codecs = {}
        rx.sock_srv = ScriptSocket()
        rx.target = ("127.0.0.1", 4433)
        rx.stats = dict.fromkeys(("delivered", "recovered", "decode_fail",
                                 "decode_ms", "recover_malformed"), 0)
        source = (b"abc", b"def")
        symbols = [struct.pack(">H", len(p)) + p for p in source]
        parity = RSErasureCode(2, shim.R_MAX).encode(symbols)[0]
        block = {"k": 2, "sym": {0: source[0], 2: parity},
                 "done": False, "delivered": {0}}
        rx._try_decode(1, block)
        rx._try_decode(1, block)
        rx._deliver(block, 1, source[1])
        self.assertEqual(rx.stats["recovered"], 1)
        self.assertEqual([p for p, _ in rx.sock_srv.written], [source[1]])


class CoreAudit(unittest.TestCase):
    def test_combo_candidates_match_actual_credit_boundaries(self):
        for k, m, w, need in itertools.product(range(1, 5), range(1, 4),
                                              (1200, 1280), (4, 7, 10, 13, 16)):
            expected = set()
            last = policy.flight_outcome(k, m, w, 0.17, 3, need)["p_two_rtt"]
            for delta in range(1, 173):
                value = policy.flight_outcome(k, m, w+delta, 0.17, 3, need)["p_two_rtt"]
                if abs(value - last) > 1e-12:
                    expected.add(delta)
                last = value
            got = set(quantum._combo_deltas(k, m, w, 39+6*k, need, max_delta=172))
            self.assertEqual(got, expected, (k, m, w, need, got, expected))

    def test_rate_override_uses_current_rate_in_argmin(self):
        for rate in (100_000, 1_000_000, 100_000_000):
            cfg = FecConfig(k_min=8, k_max=8, rate_bps=10_000_000)
            loss = SimpleNamespace(p_safe=0.05, p=0.05, burst_safe=1 / 0.95)
            cong = SimpleNamespace(srtt=50.0, g=0.0)
            d = AdaptiveFecController(cfg, loss, cong).next_block(rate)
            costs = []
            for r in range(5):
                n = 8 + r
                fail = sum(math.comb(n, e) * 0.05 ** e * 0.95 ** (n-e)
                           for e in range(r + 1, n + 1))
                costs.append(r * 1200 * 8 / rate * 1000 + 100 * fail)
            optimum = min(range(5), key=costs.__getitem__)
            self.assertEqual(d.r, optimum, (rate, d.r, optimum))
            self.assertEqual(cfg.rate_bps, 10_000_000)
            self.assertAlmostEqual(d.table[d.r][1], d.cost, places=10)

    def test_rs_recovers_every_small_erasure_set(self):
        for k, m in ((1, 3), (3, 2), (4, 3)):
            src = [bytes((i * 17 + j) % 256 for j in range(19)) for i in range(k)]
            code = RSErasureCode(k, m)
            all_syms = src + code.encode(src)
            for keep in itertools.combinations(range(k + m), k):
                self.assertEqual(code.decode({i: all_syms[i] for i in keep}), src)

    def test_rs_rejects_unequal_received_lengths(self):
        code = RSErasureCode(2, 1)
        with self.assertRaises(ValueError):
            code.decode({0: b"abc", 1: b"de"})

    def test_rs_rejects_invalid_indices_even_if_all_originals_arrive(self):
        for index in (-1, 3, True):
            with self.subTest(index=index), self.assertRaises((ValueError, TypeError)):
                RSErasureCode(2, 1).decode({index: b"ef", 0: b"ab", 1: b"cd"})

    def test_xor_rejects_unknown_parity_index(self):
        with self.assertRaises(ValueError):
            FlightCode(2, 1).decode({0: b"ab", 9: b"ef"}, {0: 2, 1: 2})

    def test_flight_restores_variable_lengths(self):
        src = [b"one", b"longer", b"z"]
        for m in (1, 2, 3):
            code = FlightCode(3, m)
            symbols = src + code.encode(src)
            for keep in itertools.combinations(range(3 + m), 3):
                self.assertEqual(code.decode({i: symbols[i] for i in keep},
                                             {i: len(s) for i, s in enumerate(src)}), src)

    def test_channel_matches_direct_path_enumeration(self):
        for p, length in ((0.05, 1), (0.15, 3), (0.7, 4)):
            for n in (1, 2, 5, 8):
                pc = min(max(p, 0), 0.999)
                if length <= 1 / (1-pc):
                    ref = [math.comb(n, e) * pc**e * (1-pc)**(n-e)
                           for e in range(n+1)]
                else:
                    a, b = pc / (length*(1-pc)), 1/length
                    trans = ((1-a, a), (b, 1-b))
                    ref = [0.0] * (n+1)
                    for path in itertools.product((0, 1), repeat=n):
                        weight = pc if path[0] else 1-pc
                        for old, new in zip(path, path[1:]):
                            weight *= trans[old][new]
                        ref[sum(path)] += weight
                got = GilbertElliott.for_prior(pc, length).erasure_pmf(n)
                for actual, expected in zip(got, ref):
                    self.assertAlmostEqual(actual, expected, places=13)


if __name__ == "__main__":
    unittest.main(verbosity=2)
