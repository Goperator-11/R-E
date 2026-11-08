from copy import deepcopy
import json
import os
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from padfec3 import decide3, layout, learn3

C_PKT = 41.983
W = 1280
RTT = 50.0
EXPLORE = {"rate_ms": 0.05, "cap_ms": 100.0}


def step(st, k, s, u, hct, *, explore=EXPLORE, ok=True, arrivals=None):
    dec = decide3.decide3(st, W, u, RTT, C_PKT, explore=explore)
    action = tuple(dec["action"])
    kwargs = {} if arrivals is None else {"arrivals": arrivals}
    info = learn3.observe3(st, action, hct if ok else None, ok, k, s, RTT, W=W, u_mbps=u, c_pkt=C_PKT,
                           j_pred=dec.get("j3_pred_pre_ms"), **kwargs)
    return dec, info


def explore_ready():
    st = learn3.new_state()
    for _ in range(40):
        step(st, 2, 3840.0, 0.0, 53.0, explore=None)
    res = decide3.decide3(st, W, 0.0, RTT, C_PKT, keep_cands=True)
    st.x_ledger, st.x_pending = EXPLORE["cap_ms"], False
    return st, res


class ExploreOff(unittest.TestCase):
    def test_state_and_decisions_match_without_flag(self):
        a, b = learn3.new_state(), learn3.new_state()
        for i in range(40):
            hct = 53.0 + (260.0 if i == 20 else 0.0)
            da, _ = step(a, 2, 3840.0, 0.0, hct, explore=None)
            db = decide3.decide3(b, W, 0.0, RTT, C_PKT)
            learn3.observe3(b, tuple(db["action"]), hct, True, 2, 3840.0, RTT, W=W, u_mbps=0.0, c_pkt=C_PKT,
                            j_pred=db.get("j3_pred_pre_ms"))
            self.assertEqual(da["action"], db["action"])
        self.assertEqual(json.dumps(a.to_json(), sort_keys=True), json.dumps(b.to_json(), sort_keys=True))
        self.assertNotIn("x_ledger", a.to_json())
        self.assertNotIn("x_pending", a.to_json())


class ExploreOn(unittest.TestCase):
    def test_loss_free_reaches_unprotected_action(self):
        st = learn3.new_state()
        for _ in range(500):
            dec, _ = step(st, 2, 3840.0, 0.0, 53.0)
        self.assertEqual(tuple(dec["action"]), learn3.B0)
        self.assertEqual(dec["why"], "explore")
        self.assertLess(learn3.post_mean(learn3.combined(st)), 0.01)

    def test_event_debits_realized_excess(self):
        st = learn3.new_state()
        for _ in range(60):
            step(st, 2, 3840.0, 0.0, 53.0)
        before = st.x_ledger
        dec, info = step(st, 2, 3840.0, 0.0, 313.0)
        self.assertEqual(dec["why"], "explore")
        self.assertEqual(info["y"], 1)
        self.assertAlmostEqual(st.x_ledger, before + EXPLORE["rate_ms"] - (313.0 - info["baseline"]))
        self.assertLess(st.x_ledger, 0.0)
        self.assertFalse(st.x_pending)
        for _ in range(100):
            dec, _ = step(st, 2, 3840.0, 0.0, 53.0)
            self.assertNotEqual(dec["why"], "explore")

    def test_failure_debit_uses_pto_cost(self):
        st = learn3.new_state()
        for _ in range(60):
            step(st, 2, 3840.0, 0.0, 53.0)
        before = st.x_ledger
        dec, _ = step(st, 2, 3840.0, 0.0, None, ok=False)
        self.assertEqual(dec["why"], "explore")
        self.assertAlmostEqual(st.x_ledger, before + EXPLORE["rate_ms"] - layout.T_PTO_MS - RTT)

    def test_large_certificate_gate_stays_closed(self):
        st = learn3.new_state()
        for _ in range(300):
            dec, _ = step(st, 2, 20000.0, 2.0, 53.0)
            self.assertNotEqual(dec["why"], "explore")

    def test_c1_path_ignores_flag(self):
        evidence = {"src": "c1", "sent": 2, "lost": 0, "bitmap": [1, 1], "trunc": False}
        a, b = learn3.new_state(), learn3.new_state()
        for _ in range(60):
            da, _ = step(a, 2, 3840.0, 0.0, 53.0, arrivals=evidence)
            db, _ = step(b, 2, 3840.0, 0.0, 53.0, explore=None, arrivals=evidence)
            self.assertEqual(da["action"], db["action"])
        self.assertIsNone(a.x_ledger)

    def test_entering_c1_clears_pending(self):
        st = learn3.new_state()
        for _ in range(60):
            step(st, 2, 3840.0, 0.0, 53.0)
        evidence = {"src": "c1", "sent": 2, "lost": 0, "bitmap": [1, 1], "trunc": False}
        before = st.x_ledger
        dec, _ = step(st, 2, 3840.0, 0.0, 313.0, arrivals=evidence)
        self.assertEqual(dec["why"], "explore")
        self.assertFalse(st.x_pending)
        self.assertEqual(st.x_ledger, before + EXPLORE["rate_ms"])

    def test_state_round_trip(self):
        st = learn3.new_state()
        for _ in range(30):
            step(st, 2, 3840.0, 0.0, 53.0)
        back = learn3.DestState3.from_json(json.loads(json.dumps(st.to_json())))
        self.assertEqual(back.x_ledger, st.x_ledger)
        self.assertEqual(back.x_pending, st.x_pending)
        broken = st.to_json()
        del broken["x_pending"]
        with self.assertRaises(ValueError):
            learn3.DestState3.from_json(broken)

    def test_bad_flag_is_rejected(self):
        st = learn3.new_state()
        for bad in ({"rate_ms": 0.0, "cap_ms": 1.0}, {"rate_ms": 1.0}, {"rate_ms": float("nan"), "cap_ms": 1.0}):
            with self.assertRaises((TypeError, ValueError)):
                decide3.decide3(st, W, 0.0, RTT, C_PKT, explore=bad)



class ExploreGuards(unittest.TestCase):
    def test_ledger_stops_at_cap(self):
        explore = {"rate_ms": 7.5, "cap_ms": 30.0}
        st = learn3.new_state()
        seen = []
        for _ in range(20):
            step(st, 2, 3840.0, 2.0, 53.0, explore=explore)
            if st.x_ledger is not None:
                seen.append(st.x_ledger)
        self.assertEqual(max(seen), 30.0)
        self.assertEqual(st.x_ledger, 30.0)

    def test_excess_below_event_threshold_is_not_debited(self):
        explore = {"rate_ms": 5.0, "cap_ms": 100.0}
        st = learn3.new_state()
        for _ in range(30):
            step(st, 2, 3840.0, 0.0, 53.0, explore=explore)
        before = st.x_ledger
        dec, info = step(st, 2, 3840.0, 0.0, 63.0, explore=explore)
        self.assertEqual(dec["why"], "explore")
        self.assertEqual(info["y"], 0)
        self.assertGreater(63.0 - info["baseline"], 0.0)
        self.assertEqual(st.x_ledger, min(100.0, before + 5.0))

    def test_reevaluation_decision_is_not_explored(self):
        st, res = explore_ready()
        control_st, control = deepcopy(st), deepcopy(res)
        decide3.explore_step(control_st, control, EXPLORE, 0.0, RTT, learn3.LATER_DEFAULT, True, False)
        self.assertEqual(control["why"], "explore")
        self.assertTrue(control_st.x_pending)
        action = res["action"]
        res["reeval"], res["why"] = True, "reeval"
        decide3.explore_step(st, res, EXPLORE, 0.0, RTT, learn3.LATER_DEFAULT, True, False)
        self.assertEqual((res["action"], res["why"], st.x_pending), (action, "reeval", False))
        self.assertEqual(st.x_ledger, EXPLORE["cap_ms"])

    def test_explore_skips_alarmed_arm(self):
        st, res = explore_ready()
        first = decide3.explore_pick(st, res, 0.0, RTT, learn3.LATER_DEFAULT)
        self.assertIsNotNone(first)
        key = learn3.arm_key(first["action"])
        st.g_alarm[key] = st.n_dec
        second = decide3.explore_pick(st, res, 0.0, RTT, learn3.LATER_DEFAULT)
        self.assertTrue(second is None or learn3.arm_key(second["action"]) != key)


if __name__ == "__main__":
    unittest.main()
