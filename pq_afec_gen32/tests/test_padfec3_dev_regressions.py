import json
import os
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from padfec import policy, quantum
from padfec3 import decide3, learn3


C_PKT = policy.C_PKT_POLICY_DEFAULT
W = 1280
U = 2.0
ONE_RTT_ACTION = (0, 3, 1)
TWO_RTT_ACTION = (0, 0, 4)


def server_bytes(cert=16000, k=2):
    return (float(cert) + policy.S0_BASE_MLKEM
            + quantum.bin_index(k * W) * C_PKT)


def point_state(cert=16000):
    st = learn3.new_state()
    point = learn3.G.index(0.15)
    st.post = [[float(i == point) for i in range(len(learn3.G))]
               for _ in learn3.H]
    st.w = [0.05, 0.10, 0.15, 0.25, 0.45]
    st.k_hist = [2] * learn3.K_WIN
    st.S_hist = [server_bytes(cert)] * learn3.S_WIN
    return st


def baseline_for(st, action, hct=80.0):
    key = learn3.arm_key(action)
    st.hct[key] = [float(hct)] * learn3.BASE_MIN
    st.hct_seq[key] = 0
    st.seq = 1


def observe(st, action, hct=80.0, rtt=50.0, *, ok=True,
            cert=16000, j_pred=None):
    return learn3.observe3(st, action, hct, ok, 2, server_bytes(cert), rtt,
                          W=W, u_mbps=U, c_pkt=C_PKT, j_pred=j_pred)


class PredictionClockTests(unittest.TestCase):
    def assert_one_prediction(self, before, after):
        n = len(learn3.G)
        for h, initial, result in zip(learn3.H, before, after):
            for old, current in zip(initial, result):
                self.assertAlmostEqual(current, (1.0 - h) * old + h / n,
                                       delta=1e-15)
            self.assertAlmostEqual(sum(result), 1.0, delta=1e-12)

    def test_skipped_observations_advance_prediction_once_without_evidence(self):
        cases = (
            ("nominal2", TWO_RTT_ACTION, 50.0),
            ("shield", TWO_RTT_ACTION, 200.0),
            ("guard", ONE_RTT_ACTION, 50.0),
            ("no_base", ONE_RTT_ACTION, 50.0),
            ("no_ctx", ONE_RTT_ACTION, 50.0),
        )
        for reason, action, rtt in cases:
            with self.subTest(reason=reason):
                st = point_state()
                if reason != "no_base":
                    baseline_for(st, action)
                if reason == "guard":
                    st.g_alarm[learn3.arm_key(action)] = 0
                if reason == "no_ctx":
                    st.k_hist = []
                before = [list(p) for p in st.post]
                weights = list(st.w)
                info = observe(st, action, rtt=rtt)
                self.assertFalse(info["updated"])
                if reason in ("nominal2", "shield", "guard"):
                    self.assertEqual(info["skip"], reason)
                else:
                    self.assertEqual(st.stats[reason], 1)
                self.assert_one_prediction(before, st.post)
                self.assertEqual(st.w, weights)
                self.assertEqual(st.stats["obs"], 1)
                self.assertEqual(st.stats["predict"], 1)
                self.assertEqual((st.stats["upd"], st.stats["events"]), (0, 0))

    def test_informative_observation_uses_one_prediction_and_likelihood(self):
        for ok, hct, event in ((True, 80.0, 0), (True, 130.0, 1),
                               (False, None, 1)):
            with self.subTest(ok=ok, event=event):
                st = point_state()
                baseline_for(st, ONE_RTT_ACTION)
                context = learn3.context(st, W, U, 50.0, C_PKT)
                self.assertFalse(learn3.nominal_two_rtt(context, ONE_RTT_ACTION))
                likelihood = learn3.likelihood(context, ONE_RTT_ACTION, event)
                before = [list(p) for p in st.post]
                weights = list(st.w)
                n = len(learn3.G)
                predicted = [[(1.0 - h) * q + h / n for q in ph]
                             for h, ph in zip(learn3.H, before)]
                normalizers = [sum(q * l for q, l in zip(ph, likelihood))
                               for ph in predicted]
                expected = [[q * l / z for q, l in zip(ph, likelihood)]
                            for ph, z in zip(predicted, normalizers)]
                raw_weights = [wh * z for wh, z in zip(weights, normalizers)]
                total = sum(raw_weights)
                expected_weights = [max(wh / total, learn3.W_FLOOR)
                                    for wh in raw_weights]
                expected_total = sum(expected_weights)
                expected_weights = [wh / expected_total
                                    for wh in expected_weights]

                info = observe(st, ONE_RTT_ACTION, hct=hct, ok=ok)
                self.assertEqual(info["y"], event)
                self.assertTrue(info["updated"])
                self.assertIsNone(info["skip"])
                for actual, wanted in zip(st.post, expected):
                    for current, target in zip(actual, wanted):
                        self.assertAlmostEqual(current, target, delta=1e-15)
                for current, target in zip(st.w, expected_weights):
                    self.assertAlmostEqual(current, target, delta=1e-15)
                self.assertEqual(st.stats["predict"], 1)
                self.assertEqual(st.stats["upd"], 1)
                self.assertEqual(st.stats["events"], event)
                self.assertEqual(st.stats["fail"], int(not ok))

    def test_repeated_skips_decay_stale_concentration_and_keep_weights(self):
        st = point_state()
        baseline_for(st, TWO_RTT_ACTION)
        before = [list(p) for p in st.post]
        weights = list(st.w)
        n = len(learn3.G)
        count = 40
        for _ in range(count):
            info = observe(st, TWO_RTT_ACTION)
            self.assertEqual(info["skip"], "nominal2")
        for h, initial, actual in zip(learn3.H, before, st.post):
            for old, current in zip(initial, actual):
                wanted = 1.0 / n + (1.0 - h) ** count * (old - 1.0 / n)
                self.assertAlmostEqual(current, wanted, delta=1e-12)
        self.assertEqual(st.w, weights)
        self.assertEqual((st.stats["obs"], st.stats["predict"]), (count, count))
        self.assertEqual(st.stats["upd"], 0)


class RobustGuardTests(unittest.TestCase):
    A = (0, 1, 2)
    B = (0, 2, 2)

    def reference_state(self):
        st = point_state(cert=9000)
        for _ in range(learn3.GUARD_COMMON_WIN):
            observe(st, self.B, hct=102.0, cert=9000, j_pred=100.0)
        self.assertEqual(st.g_common, [2.0] * learn3.GUARD_COMMON_WIN)
        self.assertEqual(st.g_alarm, {})
        return st

    def test_bimodal_residuals_and_one_pto_do_not_alarm(self):
        st = self.reference_state()
        normal = [-15.0] * 20 + [35.0] * 12
        for resid in normal:
            info = observe(st, self.A, hct=100.0 + resid,
                           cert=9000, j_pred=100.0)
            self.assertEqual(info["raised"], [])
        info = observe(st, self.A, hct=1488.0, cert=9000, j_pred=100.0)
        key = learn3.arm_key(self.A)
        self.assertEqual(info["raised"], [])
        self.assertNotIn(key, st.g_alarm)
        self.assertEqual(learn3.guard_common(st), 2.0)
        self.assertEqual(learn3.guard_excess(st, key, 2.0), -17.0)
        self.assertEqual(learn3.guard_penalty(st, key, 2.0), 0.0)
        self.assertEqual(st.stats["alarm_raised"], 0)

    def test_sustained_action_bias_still_raises_and_uses_median_penalty(self):
        st = self.reference_state()
        key = learn3.arm_key(self.A)
        for _ in range(learn3.GUARD_MIN - 1):
            info = observe(st, self.A, hct=140.0, cert=9000, j_pred=100.0)
            self.assertEqual(info["raised"], [])
        info = observe(st, self.A, hct=140.0, cert=9000, j_pred=100.0)
        self.assertEqual(info["raised"], [key])
        self.assertTrue(info["alarmed"])
        self.assertEqual(info["skip"], "guard")
        self.assertEqual(learn3.guard_penalty(st, key, 2.0), 38.0)

        info = observe(st, self.A, hct=1488.0, cert=9000, j_pred=100.0)
        self.assertTrue(info["alarmed"])
        self.assertEqual(learn3.guard_excess(st, key, 2.0), 38.0)
        self.assertEqual(learn3.guard_penalty(st, key, 2.0), 38.0)

    def test_alarmed_success_enters_common_window(self):
        st = self.reference_state()
        for _ in range(learn3.GUARD_MIN):
            observe(st, self.A, hct=140.0, cert=9000, j_pred=100.0)
        key = learn3.arm_key(self.A)
        self.assertIn(key, st.g_alarm)
        previous = list(st.g_common)
        info = observe(st, self.A, hct=107.0, cert=9000, j_pred=100.0)
        self.assertTrue(info["alarmed"])
        self.assertEqual(st.g_common, (previous + [7.0])[-learn3.GUARD_COMMON_WIN:])
        self.assertEqual(st.g_resid[key][-1], 7.0)


class DevelopmentStateTests(unittest.TestCase):
    def test_state_version_three_rejects_prior_cache_and_round_trips(self):
        st = point_state(cert=9000)
        baseline_for(st, ONE_RTT_ACTION)
        key = learn3.arm_key(ONE_RTT_ACTION)
        st.g_alarm[key] = 0
        for _ in range(8):
            decision = decide3.decide3(st, W, U, 50.0, C_PKT)
            observe(st, decision["action"], hct=100.0, cert=9000,
                    j_pred=decision["j3_pred_pre_ms"])
        data = json.loads(json.dumps(st.to_json()))
        self.assertEqual(data["v"], 3)
        self.assertGreater(data["stats"]["predict"], 0)
        restored = learn3.DestState3.from_json(data)
        self.assertEqual(restored.to_json(), st.to_json())
        first = decide3.decide3(st, W, U, 50.0, C_PKT)
        second = decide3.decide3(restored, W, U, 50.0, C_PKT)
        self.assertEqual(first, second)
        self.assertEqual(restored.to_json(), st.to_json())
        for version in (1, 2):
            with self.subTest(version=version):
                old = dict(data, v=version)
                with self.assertRaises(ValueError):
                    learn3.DestState3.from_json(old)


if __name__ == "__main__":
    unittest.main()
