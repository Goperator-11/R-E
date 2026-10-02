import copy
import math
import os
import subprocess
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from padfec import policy, quantum
from padfec3 import decide3, learn3


C_PKT = policy.C_PKT_POLICY_DEFAULT
ACTION = (0, 3, 1)
KEY = learn3.arm_key(ACTION)
S = 16000.0 + policy.S0_BASE_MLKEM + quantum.bin_index(2560) * C_PKT
BAD_NONNEGATIVE = (-1.0, float("nan"), float("inf"), float("-inf"),
                   True, "1", None)


def warm_state():
    st = learn3.new_state()
    st.k_hist = [2] * learn3.K_WIN
    st.S_hist = [S] * learn3.S_WIN
    st.hct[KEY] = [80.0] * learn3.BASE_MIN
    st.hct_seq[KEY] = 0
    st.seq = 1
    # Invalid decisions must not expire an alarm or increment this counter.
    st.n_dec = learn3.GUARD_REFRESH
    st.g_alarm[KEY] = 0
    st.g_resid[KEY] = [40.0] * learn3.GUARD_MIN
    st.g_common = [2.0] * learn3.GUARD_COMMON_WIN
    return st


def core_inputs():
    return {"post": [1.0 / len(learn3.G)] * len(learn3.G), "k": 2,
            "W": 1280, "S": S, "u_mbps": 2.0,
            "rtt_ms": 50.0, "c_pkt": C_PKT}


class InputValidationTests(unittest.TestCase):
    def test_combined_probability_mass_rejection_preserves_warm_and_cold_state(self):
        for cold in (False, True):
            with self.subTest(cold=cold):
                data = warm_state().to_json()
                for row in data["post"]:
                    row[0] += 8e-10
                data["w"][0] += 8e-10
                if cold:
                    data["k_hist"] = []
                    data["S_hist"] = []
                st = learn3.DestState3.from_json(data)
                before = st.to_json()
                with self.assertRaises(ValueError):
                    decide3.decide3(st, 1280, 2.0, 50.0, C_PKT)
                self.assertEqual(st.to_json(), before)

    def test_packet_count_extremes_are_rejected_with_bounded_runtime(self):
        cases = (
            (1e308, C_PKT), (1e308, 0.0),
            (1e308, math.nextafter(1280.0, 0.0)),
            (18000.0, math.nextafter(1280.0, 0.0)),
            (1.0, math.nextafter(1280.0, 0.0)),
        )
        code = ("from padfec3.learn3 import bin_needed_s\n"
                "for s, c in %r:\n"
                "    try:\n"
                "        bin_needed_s(s, 6, c)\n"
                "    except ValueError:\n"
                "        pass\n"
                "    else:\n"
                "        raise AssertionError('extreme packet count accepted')\n"
                "print('rejected')\n") % (cases,)
        result = subprocess.run([sys.executable, "-B", "-c", code],
                                cwd=ROOT, capture_output=True, text=True,
                                timeout=2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "rejected")
        self.assertEqual(learn3.bin_needed_s(7681.0, 6,
                                          math.nextafter(1280.0, 0.0)),
                         4398046511112)

    def test_cost_representation_errors_leave_decision_and_observation_unchanged(self):
        invalid = (
            ("W", 10 ** 100), ("u_mbps", 1e-308),
            ("u_mbps", 1e308), ("rtt_ms", 1e308),
        )
        for field, bad in invalid:
            for operation in ("decide", "observe"):
                with self.subTest(field=field, value=bad, operation=operation):
                    st = warm_state()
                    before = st.to_json()
                    kwargs = {"W": 1280, "u_mbps": 2.0, "rtt_ms": 50.0,
                              "c_pkt": C_PKT}
                    kwargs[field] = bad
                    with self.assertRaises(ValueError):
                        if operation == "decide":
                            decide3.decide3(st, **kwargs)
                        else:
                            learn3.observe3(st, ACTION, 80.0, True, 2, S,
                                            j_pred=75.0, **kwargs)
                    self.assertEqual(st.to_json(), before)

    def test_unsafe_server_window_or_incoming_flight_is_rejected_before_mutation(self):
        for missing_rtt in (0.0, 50.0):
            st = warm_state()
            before = st.to_json()
            with self.assertRaises(ValueError):
                learn3.observe3(st, ACTION, 80.0, True, 2, 1e308,
                                missing_rtt, W=1280, u_mbps=2.0, c_pkt=C_PKT)
            self.assertEqual(st.to_json(), before)
            st.S_hist = [1e308]
            before = st.to_json()
            with self.assertRaises(ValueError):
                learn3.observe3(st, ACTION, 80.0, True, 2, None,
                                missing_rtt, W=1280, u_mbps=2.0, c_pkt=C_PKT)
            self.assertEqual(st.to_json(), before)
            with self.assertRaises(ValueError):
                decide3.decide3(st, 1280, 2.0, missing_rtt, C_PKT)
            self.assertEqual(st.to_json(), before)

    def test_explicit_action_and_nonfinite_penalty_rejection_preserve_decision_state(self):
        st = warm_state()
        before = st.to_json()
        for action in ((learn3.MAX_EXACT_INT, 0, 0), (10 ** 100, 0, 0)):
            with self.subTest(action=action):
                with self.assertRaises(ValueError):
                    decide3.decide3(st, 1280, 2.0, 50.0, C_PKT, actions=[action])
                self.assertEqual(st.to_json(), before)
        with self.assertRaises(ValueError):
            decide3.decide_core(**core_inputs(), actions=[ACTION],
                                pen={KEY: float("inf")})

    def test_nonfinite_derived_residual_is_rejected_before_mutation(self):
        st = warm_state()
        before = st.to_json()
        with self.assertRaises(ValueError):
            learn3.observe3(st, ACTION, 1e308, True, 2, S, 50.0,
                            W=1280, u_mbps=2.0, c_pkt=C_PKT, j_pred=-1e308)
        self.assertEqual(st.to_json(), before)
        self.assertEqual(learn3.median([1e308, 1e308]), 1e308)
        self.assertEqual(learn3.median([-1e308, -1e308]), -1e308)
        self.assertEqual(learn3.median([-1e308, 1e308]), 0.0)

    def test_bin_needed_rejects_impossible_or_nonfinite_packet_cost(self):
        for bad in BAD_NONNEGATIVE + (1280.0, 1281.0):
            with self.subTest(c_pkt=bad):
                with self.assertRaises((TypeError, ValueError)):
                    learn3.bin_needed_s(S, 6, bad)
        for bad in BAD_NONNEGATIVE + (0.0,):
            with self.subTest(S=bad):
                with self.assertRaises((TypeError, ValueError)):
                    learn3.bin_needed_s(bad, 6, C_PKT)
        self.assertEqual(learn3.bin_needed_s(1280.0, 0, 0.0), 1)
        self.assertEqual(learn3.bin_needed_s(1280.5, 0, 0.0), 2)
        self.assertEqual(learn3.bin_needed_s(2560.0, 0, 0.0), 2)

    def test_invalid_observation_inputs_do_not_mutate_state(self):
        invalid = {
            "W": (1199, 1280.0, True, "1280", None),
            "u_mbps": BAD_NONNEGATIVE,
            "rtt_ms": BAD_NONNEGATIVE[:-1],
            "c_pkt": BAD_NONNEGATIVE + (1280.0, 1281.0),
            "srv_bytes": BAD_NONNEGATIVE[:-1],
        }
        for field, values in invalid.items():
            for bad in values:
                with self.subTest(field=field, value=bad):
                    st = warm_state()
                    before = st.to_json()
                    kwargs = {"W": 1280, "u_mbps": 2.0, "rtt_ms": 50.0,
                              "c_pkt": C_PKT, "srv_bytes": S}
                    kwargs[field] = bad
                    with self.assertRaises((TypeError, ValueError)):
                        learn3.observe3(st, ACTION, 80.0, True, 2,
                                        j_pred=75.0, **kwargs)
                    self.assertEqual(st.to_json(), before)

    def test_zero_or_missing_measurements_preserve_observation_behavior(self):
        for srv in (None, 0.0):
            for rtt in (None, 0.0, 50.0):
                with self.subTest(srv=srv, rtt=rtt):
                    st = warm_state()
                    old_server_window = list(st.S_hist)
                    info = learn3.observe3(st, ACTION, 80.0, True, 2,
                                           srv, rtt, W=1200, u_mbps=0.0,
                                           c_pkt=0.0)
                    self.assertEqual(st.S_hist, old_server_window)
                    self.assertEqual(st.stats["obs"], 1)
                    self.assertEqual(st.stats["predict"], 1)
                    if rtt in (None, 0.0):
                        self.assertIsNone(info["ctx"])

    def test_invalid_decide_inputs_do_not_refresh_alarm_or_increment_counter(self):
        invalid = {
            "W": (1199, 1280.0, True, "1280", None),
            "u_mbps": BAD_NONNEGATIVE,
            "rtt_ms": BAD_NONNEGATIVE[:-1],
            "c_pkt": BAD_NONNEGATIVE + (1280.0, 1281.0),
        }
        for field, values in invalid.items():
            for bad in values:
                with self.subTest(field=field, value=bad):
                    st = warm_state()
                    before = st.to_json()
                    kwargs = {"W": 1280, "u_mbps": 2.0, "rtt_ms": 50.0,
                              "c_pkt": C_PKT}
                    kwargs[field] = bad
                    with self.assertRaises((TypeError, ValueError)):
                        decide3.decide3(st, **kwargs)
                    self.assertEqual(st.to_json(), before)

    def test_cold_and_missing_rtt_decisions_remain_available(self):
        for rtt in (None, 0.0, 50.0):
            with self.subTest(kind="cold", rtt=rtt):
                st = learn3.new_state()
                decision = decide3.decide3(st, 1200, 0.0, rtt, 0.0)
                self.assertEqual(decision["why"], "cold")
                self.assertEqual(decision["action"], learn3.B0)
                self.assertEqual(st.n_dec, 1)
        for rtt in (None, 0.0):
            with self.subTest(kind="warm", rtt=rtt):
                st = warm_state()
                decision = decide3.decide3(st, 1280, 0.0, rtt, C_PKT)
                self.assertEqual(decision["why"], "no_rtt")
                self.assertEqual(decision["action"], learn3.B0)

    def test_decide_core_rejects_bad_context_before_model_evaluation(self):
        invalid = {
            "W": (1199, 1280.0, True, "1280", None),
            "k": (0, 5, 2.0, True, "2", None),
            "S": BAD_NONNEGATIVE + (0.0,),
            "u_mbps": BAD_NONNEGATIVE,
            "rtt_ms": BAD_NONNEGATIVE + (0.0,),
            "c_pkt": BAD_NONNEGATIVE + (1280.0, 1281.0),
        }
        for field, values in invalid.items():
            for bad in values:
                with self.subTest(field=field, value=bad):
                    kwargs = core_inputs()
                    kwargs[field] = bad
                    cache_before = learn3.model_cache_size()
                    with self.assertRaises((TypeError, ValueError)):
                        decide3.decide_core(**kwargs)
                    self.assertEqual(learn3.model_cache_size(), cache_before)

    def test_decide_core_rejects_invalid_probability_mass_and_values(self):
        n = len(learn3.G)
        bad_vectors = [[], [0.0] * n, [1.0] * n,
                       [1.0 / n] * (n - 1), None]
        for bad in BAD_NONNEGATIVE:
            vector = [1.0 / n] * n
            vector[0] = bad
            bad_vectors.append(vector)
        vector = [1.0 / n] * n
        vector[0] += 2e-9
        bad_vectors.append(vector)
        for post in bad_vectors:
            with self.subTest(post=post):
                kwargs = core_inputs()
                kwargs["post"] = post
                original = copy.deepcopy(post)
                with self.assertRaises((TypeError, ValueError)):
                    decide3.decide_core(**kwargs)
                if post is not None:
                    for value, initial in zip(post, original):
                        if isinstance(initial, float) and math.isnan(initial):
                            self.assertTrue(math.isnan(value))
                        else:
                            self.assertEqual(value, initial)
        kwargs = core_inputs()
        kwargs["post"][0] += 5e-10
        decision = decide3.decide_core(**kwargs, actions=[ACTION])
        self.assertEqual(decision["action"], ACTION)


class StateValidationTests(unittest.TestCase):
    def reject_change(self, path, replacement):
        data = warm_state().to_json()
        target = data
        for component in path[:-1]:
            target = target[component]
        target[path[-1]] = replacement
        original = copy.deepcopy(data)
        with self.assertRaises((TypeError, ValueError)):
            learn3.DestState3.from_json(data)
        # Compare JSON encoding so NaN remains comparable in corrupted fixtures.
        import json
        self.assertEqual(json.dumps(data, sort_keys=True),
                         json.dumps(original, sort_keys=True))

    def test_rejects_bad_shapes_probability_values_and_mass(self):
        for path, value in (
            (("post",), []), (("post",), {}), (("post", 0), []),
            (("w",), []), (("w",), {}),
            (("post", 0), [0.0] * len(learn3.G)),
            (("w",), [0.0] * len(learn3.H)),
            (("post", 0), [1.0] * len(learn3.G)),
            (("w",), [1.0] * len(learn3.H)),
        ):
            with self.subTest(path=path, value=value):
                self.reject_change(path, value)
        for bad in BAD_NONNEGATIVE:
            for path in (("post", 0, 0), ("w", 0)):
                with self.subTest(path=path, value=bad):
                    self.reject_change(path, bad)
        data = warm_state().to_json()
        data["post"][0][0] += 5e-10
        data["w"][0] += 5e-10
        restored = learn3.DestState3.from_json(data)
        self.assertEqual(restored.to_json(), data)
        self.reject_change(("post", 0, 0), 1.0 / len(learn3.G) + 2e-9)
        self.reject_change(("w", 0), 1.0 / len(learn3.H) + 2e-9)

    def test_rejects_excess_windows_and_invalid_stored_measurements(self):
        windows = (
            (("k_hist",), learn3.K_WIN, 2),
            (("S_hist",), learn3.S_WIN, S),
            (("hct", KEY), learn3.HCT_WIN, 80.0),
            (("g_resid", KEY), learn3.GUARD_ACTION_WIN, -2.0),
            (("g_common",), learn3.GUARD_COMMON_WIN, -2.0),
        )
        for path, cap, good in windows:
            with self.subTest(path=path, kind="cap"):
                self.reject_change(path, [good] * (cap + 1))
            with self.subTest(path=path, kind="shape"):
                self.reject_change(path, {})
        for path in (("S_hist", 0), ("hct", KEY, 0)):
            for bad in BAD_NONNEGATIVE + (0.0,):
                with self.subTest(path=path, value=bad):
                    self.reject_change(path, bad)
        for path in (("g_resid", KEY, 0), ("g_common", 0)):
            for bad in (float("nan"), float("inf"), float("-inf"),
                        True, "-2", None):
                with self.subTest(path=path, value=bad):
                    self.reject_change(path, bad)

    def test_integer_fields_reject_coercion_and_negative_counters(self):
        counters = (("seq",), ("n_dec",), ("n_reeval",),
                    ("hct_seq", KEY), ("g_alarm", KEY), ("stats", "obs"))
        for path in counters:
            for bad in (-1, True, 1.5, 1.0, "1", None):
                with self.subTest(path=path, value=bad):
                    self.reject_change(path, bad)
        for bad in (0, -1, True, 2.5, 2.0, "2", None):
            with self.subTest(field="k_hist", value=bad):
                self.reject_change(("k_hist", 0), bad)
        self.reject_change(("g_alarm", KEY), learn3.GUARD_REFRESH + 1)
        self.reject_change(("v",), float(learn3.STATE_VERSION))
        for mapping in ("hct", "hct_seq", "g_resid", "g_alarm"):
            with self.subTest(field=mapping, kind="shape"):
                self.reject_change((mapping,), [])
            with self.subTest(field=mapping, kind="action"):
                value = 0 if mapping in ("hct_seq", "g_alarm") else [1.0]
                self.reject_change((mapping,), {"0,9,0": value})
        self.reject_change(("stats",), [])
        self.reject_change(("hct",), {"%d,0,0" % (10 ** 100): [80.0]})

    def test_valid_full_windows_and_signed_residuals_round_trip(self):
        data = warm_state().to_json()
        data["hct"][KEY] = [80.0] * learn3.HCT_WIN
        data["g_resid"][KEY] = [-2.0, 4.0] * (learn3.GUARD_ACTION_WIN // 2)
        data["g_common"] = [-2.0, 4.0] * (learn3.GUARD_COMMON_WIN // 2)
        restored = learn3.DestState3.from_json(data)
        self.assertEqual(restored.to_json(), data)
        data["k_hist"] = [5] * learn3.K_WIN
        restored = learn3.DestState3.from_json(data)
        decision = decide3.decide3(restored, 1280, 2.0, 50.0, C_PKT)
        self.assertEqual(decision["why"], "k_range")


if __name__ == "__main__":
    unittest.main()
