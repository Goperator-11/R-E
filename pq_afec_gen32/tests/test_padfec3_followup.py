import os
import sys
import unittest
from unittest import mock

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from padfec import policy, quantum
from padfec3 import decide3, layout, learn3


C_PKT = policy.C_PKT_POLICY_DEFAULT
W = 1280
S = 16000.0 + policy.S0_BASE_MLKEM + quantum.bin_index(2 * W) * C_PKT
ACTION = (0, 3, 1)
KEY = learn3.arm_key(ACTION)


def warm_state():
    st = learn3.new_state()
    st.k_hist = [2] * learn3.K_WIN
    st.S_hist = [S] * learn3.S_WIN
    st.hct[KEY] = [80.0] * learn3.BASE_MIN
    st.hct_seq[KEY] = 0
    st.seq = 1
    return st


def core_inputs():
    return {"post": [1.0 / len(learn3.G)] * len(learn3.G), "k": 2,
            "W": W, "S": S, "u_mbps": 2.0, "rtt_ms": 50.0,
            "c_pkt": C_PKT}


def observe(st, **kwargs):
    inputs = {"action": ACTION, "hct_ms": 80.0, "ok": True, "k_obs": 2,
              "srv_bytes": S, "rtt_ms": 50.0, "W": W, "u_mbps": 2.0,
              "c_pkt": C_PKT, "j_pred": 75.0}
    inputs.update(kwargs)
    return learn3.observe3(st, **inputs)


class FollowupTests(unittest.TestCase):
    def tearDown(self):
        learn3.clear_model_cache()

    def test_generated_parity_respects_requested_budget(self):
        for budget in range(layout.M_MAX + 1):
            with self.subTest(m_max=budget):
                raw = decide3.levers_s(2, W, 14, budget, S, C_PKT,
                                      decide3.MAX_IPS)
                self.assertTrue(all(c["m"] <= budget for c in raw))
                result = decide3.decide_core(**core_inputs(), m_max=budget,
                                             max_steps=14, keep_cands=True)
                self.assertTrue(all(c["m"] <= budget for c in result["cands"]))
                self.assertLessEqual(result["m"], budget)
                if budget == 0:
                    self.assertTrue(all(c["lead"] == c["T"] == 0
                                        for c in result["cands"]))

    def test_physical_candidate_bound_limits_large_step_count(self):
        original = quantum.delta_min

        def bounded_delta(*args, **kwargs):
            if bounded.call_count > 100:
                self.fail("physical candidate generation traversed excess steps")
            return original(*args, **kwargs)

        expected = decide3.candidates3(2, W, S, C_PKT, max_steps=100)
        with mock.patch.object(quantum, "delta_min", side_effect=bounded_delta) as bounded:
            actual = decide3.candidates3(2, W, S, C_PKT, max_steps=10 ** 12)
        self.assertEqual(actual, expected)
        self.assertLess(bounded.call_count, 100)
        self.assertTrue(all(c["W_eff"] <= decide3.MAX_IPS for c in actual))
        equal = decide3.candidates3(2, W, S, C_PKT, max_steps=10 ** 12,
                                    max_ips=W)
        self.assertTrue(all(c["delta"] == 0 for c in equal))
        self.assertEqual(decide3.candidates3(2, W, S, C_PKT,
                                             max_steps=10 ** 12,
                                             max_ips=W - 1), [])

    def test_option_validation_preserves_state_and_analysis_override(self):
        invalid = {"m_max": (-1, 5, True, 1.0, "1"),
                   "max_steps": (-1, True, 1.0, "1"),
                   "max_ips": (-1, 1199, True, 1452.0, "1452")}
        for cold in (False, True):
            for name, values in invalid.items():
                for value in values:
                    with self.subTest(cold=cold, option=name, value=value):
                        st = learn3.new_state() if cold else warm_state()
                        before = st.to_json()
                        with self.assertRaises((TypeError, ValueError)):
                            decide3.decide3(st, W, 2.0, 50.0, C_PKT,
                                            **{name: value})
                        self.assertEqual(st.to_json(), before)
        zero = decide3.candidates3(2, W, S, C_PKT, max_ips=0, max_steps=4)
        missing = decide3.candidates3(2, W, S, C_PKT, max_ips=None, max_steps=4)
        self.assertEqual(zero, missing)
        override = (200, 0, 4)
        result = decide3.decide_core(**core_inputs(), actions=[override],
                                     max_ips=decide3.MAX_IPS, m_max=0,
                                     max_steps=0)
        self.assertEqual(result["action"], override)
        self.assertGreater(result["W_eff"], decide3.MAX_IPS)
        self.assertGreater(result["m"], 0)

    def test_later_enum_is_checked_before_cold_or_warm_observation(self):
        for cold in (False, True):
            st = learn3.new_state() if cold else warm_state()
            before = st.to_json()
            with self.assertRaises(ValueError):
                observe(st, later="typo")
            self.assertEqual(st.to_json(), before)
        for mode in layout.LATER_MODES:
            with self.subTest(later=mode):
                st = warm_state()
                observe(st, later=mode)
                self.assertEqual(st.stats["obs"], 1)
                self.assertEqual(st.stats["predict"], 1)

    def test_late_observation_error_rolls_back_all_state_and_success_commits(self):
        st = warm_state()
        before = st.to_json()
        with mock.patch.object(learn3, "likelihood", side_effect=ValueError("late failure")):
            with self.assertRaisesRegex(ValueError, "late failure"):
                observe(st)
        self.assertEqual(st.to_json(), before)
        result = observe(st)
        self.assertTrue(result["updated"])
        self.assertEqual(st.stats["obs"], 1)
        self.assertEqual(st.stats["resid"], 1)
        self.assertEqual(st.stats["predict"], 1)
        self.assertEqual(st.stats["upd"], 1)
        self.assertEqual(st.g_resid[KEY], [5.0])
        self.assertEqual(st.g_common, [5.0])
        self.assertEqual(st.seq, 2)
        self.assertEqual(len(st.hct[KEY]), learn3.BASE_MIN + 1)
        self.assertNotEqual(st.post, before["post"])

    def test_restored_guard_gaps_reject_both_overflow_signs(self):
        for sign in (-1.0, 1.0):
            with self.subTest(sign=sign):
                data = warm_state().to_json()
                data["g_resid"] = {KEY: [sign * 1e308]}
                data["g_common"] = [-sign * 1e308]
                data["g_alarm"] = {KEY: 0}
                with self.assertRaisesRegex(ValueError, "guard gap"):
                    learn3.DestState3.from_json(data)
        data = warm_state().to_json()
        data["g_resid"] = {KEY: [1e308]}
        data["g_common"] = [0.0]
        restored = learn3.DestState3.from_json(data)
        self.assertEqual(restored.to_json(), data)

    def test_derived_guard_and_transferred_baseline_errors_preserve_observation(self):
        st = warm_state()
        st.g_resid[KEY] = [1e308] * learn3.GUARD_MIN
        st.g_common = [0.0] * 32 + [-1e308] * 32
        st = learn3.DestState3.from_json(st.to_json())
        before = st.to_json()
        with self.assertRaisesRegex(ValueError, "guard gap"):
            observe(st, action=(0, 2, 2), j_pred=1e308)
        self.assertEqual(st.to_json(), before)

        st = warm_state()
        st.hct[KEY] = [sys.float_info.max] * learn3.BASE_MIN
        before = st.to_json()
        with self.assertRaisesRegex(ValueError, "HCT baseline"):
            observe(st, action=(0, 0, 0), hct_ms=80.0, u_mbps=0.0,
                    rtt_ms=1e306, j_pred=None)
        self.assertEqual(st.to_json(), before)

    def test_fifo_cache_eviction_preserves_points_and_decision_values(self):
        args = (2, W, 2.0, 50.0, 14, 3, 4, 5)
        learn3.clear_model_cache()
        with mock.patch.object(learn3, "MODEL_CACHE_MAX", 3):
            wanted = learn3.model_point(*args)
            learn3.model_point(*args[:-1], 6)
            learn3.model_point(*args[:-1], 7)
            self.assertEqual(learn3.model_point(*args), wanted)
            learn3.model_point(*args[:-1], 8)
            key = args + (learn3.LATER_DEFAULT,)
            self.assertNotIn(key, learn3._MODEL)
            self.assertEqual(learn3.model_cache_size(), 3)
            self.assertEqual(learn3.model_point(*args), wanted)
            self.assertEqual(learn3.model_cache_size(), 3)
        learn3.clear_model_cache()
        expected = decide3.decide_core(**core_inputs(), keep_cands=True)
        learn3.clear_model_cache()
        with mock.patch.object(learn3, "MODEL_CACHE_MAX", 4):
            actual = decide3.decide_core(**core_inputs(), keep_cands=True)
            self.assertLessEqual(learn3.model_cache_size(), 4)
            repeated = decide3.decide_core(**core_inputs(), keep_cands=True)
            self.assertLessEqual(learn3.model_cache_size(), 4)
        self.assertEqual(actual, expected)
        self.assertEqual(repeated, expected)


if __name__ == "__main__":
    unittest.main()
