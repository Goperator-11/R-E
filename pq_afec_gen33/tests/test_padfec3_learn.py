import json
import math
import os
import random
import statistics
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from padfec import capacity, policy, quantum
from padfec3 import decide3, layout, learn3

C_PKT = policy.C_PKT_POLICY_DEFAULT
S0_ML = policy.S0_BASE_MLKEM


def synth_s(cert, k, w, s0_base=S0_ML):
    return float(cert) + s0_base + float(quantum.bin_index(k * w)) * C_PKT


def ctx_of(cert, rtt, u, k=2, w=1280):
    S = synth_s(cert, k, w)
    return {"k": k, "S": S, "W": w, "u": float(u), "rtt": float(rtt),
            "n_need": learn3.bin_needed_s(S, quantum.bin_index(k * w), C_PKT)}


def comb(st):
    return learn3.combined(st)


def predicted(post, w, n=1):
    for _ in range(n):
        post, w = learn3.predict_step(post, w)
    return post


def categorical_updates(post, weights, ctx, action, hcts, ok=True):
    for hct in hcts:
        grade = learn3.classify_hct(ctx, action, hct, ok)
        values = learn3.class_likelihood(ctx, action, grade)
        post, weights, _ = learn3.filter_step(post, weights, values)
    return post, weights


def c1_state():
    st = learn3.new_state()
    st.c1_seen = True
    return st


def feed(st, action, hcts, cert, rtt, u, k=2, w=1280):
    out = []
    S = synth_s(cert, k, w)
    for h in hcts:
        out.append(learn3.observe3(st, action, h, True, k, S, rtt, W=w,
                                   u_mbps=u, c_pkt=C_PKT))
    return out


class PosteriorTests(unittest.TestCase):
    def test_posterior_sums_to_one(self):
        rng = random.Random(7)
        st = learn3.new_state()
        arms = [(0, 1, 2), (0, 2, 2), (0, 3, 1), (0, 4, 0)]
        for t in range(600):
            a = arms[t % len(arms)]
            h = 120.0 + rng.random() * 3 + (60.0 if rng.random() < 0.1 else 0)
            learn3.observe3(st, a, h, True, 2, synth_s(9000, 2, 1280), 50.0,
                            W=1280, u_mbps=2.0, c_pkt=C_PKT)
            self.assertAlmostEqual(sum(comb(st)), 1.0, delta=1e-12)
            self.assertAlmostEqual(sum(st.w), 1.0, delta=1e-12)
            for ph in st.post:
                self.assertAlmostEqual(sum(ph), 1.0, delta=1e-12)
            self.assertTrue(all(x >= learn3.W_FLOOR * 0.99 for x in st.w))
        self.assertGreater(st.stats["upd"], 400)

    def test_flat_likelihood_gives_hazard_mixed_prior(self):
        n = len(learn3.G)
        post = [[1.0 / n] * n for _ in learn3.H]
        w = [1.0 / len(learn3.H)] * len(learn3.H)
        p2, w2, zs = learn3.filter_step(post, w, [1.0] * n)
        for ph in p2:
            for x in ph:
                self.assertAlmostEqual(x, 1.0 / n, delta=1e-15)
        for x, y in zip(w2, w):
            self.assertAlmostEqual(x, y, delta=1e-15)
        ctx = ctx_of(16000, 50.0, 2.0)
        L = learn3.likelihood(ctx, (0, 0, 1), 1)
        for _ in range(30):
            post, w, _ = learn3.filter_step(post, w, L)
        prev = [list(ph) for ph in post]
        prev_w = list(w)
        dist0 = max(abs(x - 1.0 / n) for ph in prev for x in ph)
        p3, w3, zs = learn3.filter_step(prev, prev_w, [1.0] * n)
        for z in zs:
            self.assertAlmostEqual(z, 1.0, delta=1e-12)
        for x, y in zip(w3, prev_w):
            self.assertAlmostEqual(x, y, delta=1e-15)
        for h, ph, q in zip(learn3.H, prev, p3):
            for i in range(n):
                self.assertAlmostEqual(q[i], (1.0 - h) * ph[i] + h / n,
                                       delta=1e-15)
        cur = p3
        last = max(abs(x - 1.0 / n) for ph in cur for x in ph)
        self.assertLess(last, dist0)
        for _ in range(20000):
            cur, _, _ = learn3.filter_step(cur, prev_w, [1.0] * n)
        far = max(abs(x - 1.0 / n) for ph in cur for x in ph)
        self.assertLess(far, dist0 * 0.01)

    def test_outlier_does_not_move_baseline(self):
        rng = random.Random(11)
        st = learn3.new_state()
        arm = (0, 1, 2)
        rtt = 50.0
        ctx_args = (16000, rtt, 2.0)
        normal = lambda: 130.0 + rng.random() * 4.0
        feed(st, arm, [normal() for _ in range(20)], *ctx_args)
        ctx = learn3.context(st, 1280, 2.0, rtt, C_PKT)
        b_before, _ = learn3.baseline(st, ctx, arm)
        feed(st, arm, [82.4], *ctx_args)
        b_after, _ = learn3.baseline(st, ctx, arm)
        self.assertLess(abs(b_after - b_before), 1.0)
        ev0 = st.stats["events"]
        later = [normal() for _ in range(40)]
        infos = []
        all_time_min = 82.4
        for h in later:
            self.assertGreaterEqual(h - all_time_min, 0.5 * rtt)
            infos.extend(feed(st, arm, [h], *ctx_args))
        self.assertTrue(all(i["y"] == 0 for i in infos))
        self.assertEqual(st.stats["events"], ev0)

    def test_shielded_arm_applies_only_hazard_prediction(self):
        arm = (0, 0, 0)
        for rtt, expect_shield in ((200.0, True), (199.0, False)):
            st = learn3.new_state()
            feed(st, arm, [2 * rtt + 5.0 + 0.1 * i for i in range(10)], 9000,
                 rtt, 2.0)
            ctx = learn3.context(st, 1280, 2.0, rtt, C_PKT)
            self.assertTrue(learn3.nominal_two_rtt(ctx, arm))
            self.assertEqual(learn3.shielded(ctx, arm), expect_shield)
            post0 = [list(p) for p in st.post]
            w0 = list(st.w)
            want = "shield" if expect_shield else "nominal2"
            n0 = st.stats[want]
            infos = feed(st, arm, [2 * rtt + 5.0 + 1.5 * rtt, 2 * rtt + 5.2,
                                   2 * rtt + 5.0 + 3.0 * rtt], 9000, rtt, 2.0)
            self.assertEqual([i["y"] for i in infos], [1, 0, 1])
            self.assertEqual(st.post, predicted(post0, w0, 3))
            self.assertEqual(st.w, w0)
            self.assertFalse(any(i["updated"] for i in infos))
            self.assertEqual([i["shielded"] for i in infos], [expect_shield] * 3)
            self.assertEqual([i["skip"] for i in infos], [want] * 3)
            self.assertEqual(st.stats[want], n0 + 3)
            self.assertEqual(st.stats["upd"], 0)
        st = learn3.new_state()
        arm1 = (0, 1, 2)
        feed(st, arm1, [205.0 + 0.1 * i for i in range(10)], 9000, 200.0, 2.0)
        ctx = learn3.context(st, 1280, 2.0, 200.0, C_PKT)
        self.assertFalse(learn3.shielded(ctx, arm1))
        post0 = [list(p) for p in st.post]
        feed(st, arm1, [205.0 + 150.0], 9000, 200.0, 2.0)
        self.assertNotEqual(st.post, post0)

    def test_event_probability_follows_nominal_rounds(self):
        ctx = ctx_of(16000, 50.0, 2.0)
        for arm, nominal2 in (((0, 0, 1), True), ((0, 3, 1), False),
                              ((0, 1, 2), True), ((0, 0, 0), True),
                              ((0, 2, 2), True), ((0, 4, 0), False)):
            self.assertEqual(learn3.nominal_two_rtt(ctx, arm), nominal2)
            d, lead, t = arm
            for g in (0, 4, 13, 25):
                ev = layout.evaluate(2, 1280 + d, lead + t, lead, learn3.G[g],
                                     50.0, 2.0, ctx["n_need"], "v3")
                want = ev["p_fail"] if nominal2 else ev["e"]
                self.assertEqual(learn3.event_prob(ctx, arm, g), want)

    def test_failed_connection_is_event_and_not_pushed(self):
        for arm, n2 in (((0, 3, 1), False), ((0, 1, 2), True)):
            st = learn3.new_state()
            feed(st, arm, [130.0 + 0.1 * i for i in range(10)], 16000, 50.0, 2.0)
            ctx = learn3.context(st, 1280, 2.0, 50.0, C_PKT)
            self.assertEqual(learn3.nominal_two_rtt(ctx, arm), n2)
            n_k, n_s = len(st.k_hist), len(st.S_hist)
            n_h = len(st.hct[learn3.arm_key(arm)])
            post0 = [list(p) for p in st.post]
            info = learn3.observe3(st, arm, None, False, 2, 99999, 50.0, W=1280,
                                   u_mbps=2.0, c_pkt=C_PKT, j_pred=100.0)
            self.assertEqual(info["y"], 1)
            self.assertEqual(info["updated"], not n2)
            self.assertEqual(info["skip"], "nominal2" if n2 else None)
            self.assertEqual(st.post == post0, n2)
            self.assertIsNone(info["resid"])
            self.assertEqual((st.g_resid, st.g_common, st.stats["resid"]),
                             ({}, [], 0))
            self.assertEqual((len(st.k_hist), len(st.S_hist),
                              len(st.hct[learn3.arm_key(arm)])), (n_k, n_s, n_h))
            self.assertEqual(st.stats["fail"], 1)

    def test_baseline_transfer_uses_model_offset(self):
        st = learn3.new_state()
        ref = (0, 1, 2)
        feed(st, ref, [130.0 + 0.5 * i for i in range(9)], 16000, 50.0, 2.0)
        ctx = learn3.context(st, 1280, 2.0, 50.0, C_PKT)
        b, r = learn3.baseline(st, ctx, (0, 3, 1))
        self.assertEqual(r, learn3.arm_key(ref))
        want = (learn3.median(st.hct[r]) + learn3.j3_at(ctx, (0, 3, 1), 0)
                - learn3.j3_at(ctx, ref, 0))
        self.assertEqual(b, want)
        self.assertLess(b, learn3.median(st.hct[r]) - 30.0)


class C1MissingReplyTests(unittest.TestCase):
    def test_c1_missing_reply_on_shielded_arm_applies_categorical_evidence(self):
        arm = (0, 0, 0)
        for rtt, expect_shield in ((200.0, True), (199.0, False)):
            st = c1_state()
            feed(st, arm, [2 * rtt + 5.0 + 0.1 * i for i in range(10)], 9000,
                 rtt, 2.0)
            ctx = learn3.context(st, 1280, 2.0, rtt, C_PKT)
            self.assertTrue(learn3.nominal_two_rtt(ctx, arm))
            self.assertEqual(learn3.shielded(ctx, arm), expect_shield)
            post0 = [list(p) for p in st.post]
            w0 = list(st.w)
            want = "shield" if expect_shield else "nominal2"
            n0 = st.stats[want]
            upd0 = st.stats["upd"]
            hcts = [2 * rtt + 5.0 + 1.5 * rtt, 2 * rtt + 5.2, 2 * rtt + 5.0 + 3.0 * rtt]
            expected, weights = categorical_updates(post0, w0, ctx, arm, hcts)
            infos = feed(st, arm, hcts, 9000, rtt, 2.0)
            self.assertEqual([i["y"] for i in infos], [1, 0, 1])
            self.assertEqual(st.post, expected)
            self.assertEqual(st.w, weights)
            self.assertTrue(all(i["updated"] and i["loss_update_kind"] == "categorical" for i in infos))
            self.assertEqual([i["legacy_shielded"] for i in infos], [expect_shield] * 3)
            self.assertEqual([i["legacy_skip_reason"] for i in infos], [want] * 3)
            self.assertEqual([i["skip"] for i in infos], [None] * 3)
            self.assertEqual(st.stats[want], n0 + 3)
            self.assertEqual(st.stats["upd"], upd0 + 3)
        st = c1_state()
        arm1 = (0, 1, 2)
        feed(st, arm1, [205.0 + 0.1 * i for i in range(10)], 9000, 200.0, 2.0)
        ctx = learn3.context(st, 1280, 2.0, 200.0, C_PKT)
        self.assertFalse(learn3.shielded(ctx, arm1))
        post0 = [list(p) for p in st.post]
        feed(st, arm1, [205.0 + 150.0], 9000, 200.0, 2.0)
        self.assertNotEqual(st.post, post0)

    def test_c1_failed_connection_without_reply_uses_categorical_evidence(self):
        for arm, n2 in (((0, 3, 1), False), ((0, 1, 2), True)):
            st = c1_state()
            feed(st, arm, [130.0 + 0.1 * i for i in range(10)], 16000, 50.0, 2.0)
            ctx = learn3.context(st, 1280, 2.0, 50.0, C_PKT)
            self.assertEqual(learn3.nominal_two_rtt(ctx, arm), n2)
            n_k, n_s = len(st.k_hist), len(st.S_hist)
            n_h = len(st.hct[learn3.arm_key(arm)])
            post0 = [list(p) for p in st.post]
            expected, weights = categorical_updates(post0, st.w, ctx, arm, [None], ok=False)
            info = learn3.observe3(st, arm, None, False, 2, 99999, 50.0, W=1280,
                                   u_mbps=2.0, c_pkt=C_PKT, j_pred=100.0)
            self.assertEqual(info["y"], 1)
            self.assertTrue(info["updated"])
            self.assertEqual(info["loss_update_kind"], "categorical")
            self.assertEqual(info["legacy_skip_reason"], "nominal2" if n2 else None)
            self.assertIsNone(info["skip"])
            self.assertEqual((st.post, st.w), (expected, weights))
            self.assertIsNone(info["resid"])
            self.assertEqual((st.g_resid, st.g_common, st.stats["resid"]),
                             ({}, [], 0))
            self.assertEqual((len(st.k_hist), len(st.S_hist),
                              len(st.hct[learn3.arm_key(arm)])), (n_k, n_s, n_h))
            self.assertEqual(st.stats["fail"], 1)

    def test_c1_nominal_two_rtt_missing_reply_updates_categorical_posterior(self):
        st = c1_state()
        feed(st, (0, 3, 1), [80.0 + 0.1 * i for i in range(10)], 16000, 50.0, 2.0)
        upd0 = st.stats["upd"]
        self.assertGreater(upd0, 0)
        arm = (0, 0, 4)
        ctx = learn3.context(st, 1280, 2.0, 50.0, C_PKT)
        self.assertTrue(learn3.nominal_two_rtt(ctx, arm))
        self.assertFalse(learn3.shielded(ctx, arm))
        self.assertEqual(learn3.skip_reason(ctx, arm), "nominal2")
        self.assertIsNone(learn3.skip_reason(ctx, (0, 3, 1)))
        post0 = [list(p) for p in st.post]
        w0 = list(st.w)
        k0 = len(st.k_hist)
        S_before = list(st.S_hist)
        expected, weights = categorical_updates(post0, w0, ctx, arm, [120.0, 121.0, 300.0])
        infos = feed(st, arm, [120.0, 121.0, 300.0], 16000, 50.0, 2.0)
        self.assertEqual([i["y"] for i in infos], [0, 0, 1])
        self.assertTrue(all(i["legacy_skip_reason"] == "nominal2" for i in infos))
        self.assertTrue(all(i["updated"] and i["loss_update_kind"] == "categorical" for i in infos))
        self.assertTrue(all(i["skip"] is None and not i["shielded"] for i in infos))
        self.assertEqual(st.post, expected)
        self.assertEqual(st.w, weights)
        self.assertEqual(st.stats["upd"], upd0 + 3)
        self.assertEqual(st.stats["nominal2"], 3)
        self.assertEqual(len(st.k_hist), k0 + 3)
        self.assertEqual(st.S_hist, (S_before + [synth_s(16000, 2, 1280)] * 2)[-learn3.S_WIN:])
        self.assertEqual(st.hct[learn3.arm_key(arm)], [120.0, 121.0, 300.0])
        info = feed(st, (0, 3, 1), [80.5], 16000, 50.0, 2.0)[0]
        self.assertTrue(info["updated"])
        self.assertNotEqual(st.post, post0)


def detection_run(ctx, arm, seed, seg=450):
    rng = random.Random(seed)
    n = len(learn3.G)
    post = [[1.0 / n] * n for _ in learn3.H]
    w = [1.0 / len(learn3.H)] * len(learn3.H)
    Ls = {y: learn3.likelihood(ctx, arm, y) for y in (0, 1)}
    lo, hi = learn3.G.index(0.02), learn3.G.index(0.15)
    seq = [lo] * seg + [hi] * seg + [lo] * seg
    up = down = None
    for t, g in enumerate(seq):
        y = 1 if rng.random() < Ls[1][g] else 0
        post, w, _ = learn3.filter_step(post, w, Ls[y])
        c = [0.0] * n
        for wh, ph in zip(w, post):
            for i in range(n):
                c[i] += wh * ph[i]
        mass_hi = sum(q for q, p in zip(c, learn3.G) if p >= 0.10)
        if seg <= t < 2 * seg and up is None and mass_hi > 0.5:
            up = t - seg + 1
        if t >= 2 * seg and down is None and mass_hi < 0.5:
            down = t - 2 * seg + 1
    return up, down


def kl_delay(ctx, arm, g_from, g_to):
    a = learn3.likelihood(ctx, arm, 1)[g_from]
    b = learn3.likelihood(ctx, arm, 1)[g_to]
    kl = b * math.log(b / a) + (1 - b) * math.log((1 - b) / (1 - a))
    return math.log(300.0) / kl


class ChangeDetectionTests(unittest.TestCase):
    def check(self, ctx, arm):
        lo, hi = learn3.G.index(0.02), learn3.G.index(0.15)
        d_up = kl_delay(ctx, arm, lo, hi)
        d_down = kl_delay(ctx, arm, hi, lo)
        ups, downs = [], []
        for seed in range(40):
            u, d = detection_run(ctx, arm, seed)
            self.assertIsNotNone(u)
            self.assertIsNotNone(d)
            ups.append(u)
            downs.append(d)
        self.assertLessEqual(statistics.median(ups), 2.0 * d_up)
        self.assertLessEqual(statistics.median(downs), 2.0 * d_down)
        return statistics.median(ups), d_up, statistics.median(downs), d_down

    def test_bigcert_m1_change_detection(self):
        self.check(ctx_of(16000, 50.0, 2.0), (0, 0, 1))

    def test_2mbps_m3_change_detection(self):
        self.check(ctx_of(9000, 50.0, 2.0), (0, 1, 2))


def ref_pick(k, w, S, u, rtt, g):
    n_need = learn3.bin_needed_s(S, quantum.bin_index(k * w), C_PKT)
    rows = []
    for c in decide3.candidates3(k, w, S, C_PKT):
        J = layout.j3(k, c["W_eff"], c["m"], c["lead"], learn3.G[g], rtt, u,
                      n_need)
        rows.append((J, c))
    jmin = min(J for J, _ in rows)
    tied = [(J, c) for J, c in rows if J <= jmin + policy.J_TIE_MS]

    def key(r):
        J, c = r
        return (c["added"], 0 if c["m"] > 0 else 1, c["mode"],
                0 if c["lead"] == layout.legacy_lead(c["m"]) else 1, J,
                c["lead"], c["m"], c["delta"])
    return min(tied, key=key)


class DecideTests(unittest.TestCase):
    def test_first_connection_returns_b0(self):
        st = learn3.new_state()
        r = decide3.decide3(st, 1280, 2.0, 50.0, C_PKT)
        self.assertEqual(r["action"], (0, 0, 0))
        self.assertEqual(r["why"], "cold")
        self.assertIsNone(r["ej"])
        learn3.observe3(st, r["action"], 120.0, True, 2, 18232, 50.0, W=1280,
                        u_mbps=2.0, c_pkt=C_PKT)
        r2 = decide3.decide3(st, 1280, 2.0, 50.0, C_PKT)
        self.assertEqual(r2["why"], "ej")
        self.assertIsNotNone(r2["ej"])

    def test_k_hat_is_recent_mode(self):
        self.assertEqual(learn3.mode_recent([2, 2, 1, 1]), 1)
        self.assertEqual(learn3.mode_recent([1, 1, 2, 2]), 2)
        self.assertEqual(learn3.mode_recent([1, 2, 2, 1, 2]), 2)
        self.assertEqual(learn3.mode_recent([2, 3, 1]), 1)
        st = learn3.new_state()
        arm = (0, 0, 1)
        for kk in [3] * 10 + [2] * 9:
            learn3.observe3(st, arm, 100.0, True, kk, 11000, 50.0, W=1280,
                            u_mbps=0.0, c_pkt=C_PKT)
        self.assertEqual(len(st.k_hist), learn3.K_WIN)
        self.assertEqual(st.k_hist.count(3), 7)
        self.assertEqual(learn3.k_hat(st), 2)
        learn3.observe3(st, arm, 100.0, True, 1, 11000, 50.0, W=1280,
                        u_mbps=0.0, c_pkt=C_PKT)
        self.assertEqual(learn3.k_hat(st), 2)

    def test_point_mass_decide_equals_j3_argmin(self):
        cases = [(2, 1280, 16000, 50.0, 2.0), (2, 1280, 9000, 200.0, 2.0),
                 (2, 1280, 9000, 50.0, 0.0), (1, 1200, 3200, 10.0, 10.0),
                 (3, 1350, 12000, 100.0, 5.0), (4, 1280, 6500, 50.0, 100.0),
                 (2, 1200, 12000, 50.0, 2.0), (1, 1280, 5609, 100.0, 0.0)]
        n = len(learn3.G)
        for k, w, cert, rtt, u in cases:
            S = synth_s(cert, k, w)
            for g in (0, 3, 4, 7, 13, 25):
                st = learn3.new_state()
                st.k_hist = [k]
                st.S_hist = [S]
                st.post = [[1.0 if i == g else 0.0 for i in range(n)]
                           for _ in learn3.H]
                st.w = [1.0, 0.0, 0.0, 0.0, 0.0]
                r = decide3.decide3(st, w, u, rtt, C_PKT)
                J, c = ref_pick(k, w, S, u, rtt, g)
                self.assertEqual(r["action"], c["action"],
                                 (k, w, cert, rtt, u, g))
                self.assertEqual(r["ej"], J)

    def test_levers_port_matches_quantum(self):
        def c_for_k(k, w):
            return ((k - 1) * (w - 51) + 1 + k * (w - 51)) // 2
        for k in (1, 2, 3, 4):
            for w in (1200, 1280, 1350):
                C = c_for_k(k, w)
                self.assertEqual(capacity.natural_k(C, w, 51), k)
                for cert in (1000, 3200, 5800, 9000, 12000, 16000):
                    for s0b in (382.45, 1472.0):
                        for mmax in (3, 4):
                            S = synth_s(cert, k, w, s0b)
                            py = quantum.levers(
                                C, cert, None, W=w, h=51, f=16, max_steps=2,
                                m_max=mmax, s0_base=s0b, c_pkt=C_PKT,
                                parity_bytes=policy.parity_datagram_bytes,
                                max_delta=max(0, 1452 - w))
                            py = [(x["mode"], x["m"], x["W_eff"] - w)
                                  for x in py if x["mode"] != "pad_repack"]
                            go = [(x["mode"], x["m"], x["delta"])
                                  for x in decide3.levers_s(k, w, 2, mmax, S,
                                                            C_PKT, 1452)]
                            self.assertEqual(py, go)
                            self.assertEqual(
                                quantum.bin_needed(cert, None, s0b, C_PKT),
                                learn3.bin_needed_s(
                                    S, quantum.bin_index(k * w), C_PKT))

    def test_candidates_contain_gen2_legacy_actions(self):
        for cert in (3200, 9000, 12000, 16000):
            C = 1447
            d = policy.decide_v2(C=C, cert_bytes=cert, rtt_ms=50.0, p=0.05,
                                 s0_base=S0_ML, c_pkt=C_PKT, W=1280,
                                 m_max=policy.M_MAX_DEFAULT, uplink_mbps=2.0)
            S = synth_s(cert, 2, 1280)
            mine = set(c["action"] for c in decide3.candidates3(2, 1280, S,
                                                                C_PKT))
            for c in d["candidates"]:
                a = (c["W_eff"] - 1280, layout.legacy_lead(c["m"]),
                     c["m"] - layout.legacy_lead(c["m"]))
                if c["m"] > 0 and policy.parity_datagram_bytes(c["W_eff"], 2) > decide3.UDP_MAX:
                    self.assertNotIn(a, mine)
                else:
                    self.assertIn(a, mine)

    def test_state_json_roundtrip(self):
        rng = random.Random(3)
        st = learn3.new_state()
        for t in range(80):
            r = decide3.decide3(st, 1280, 2.0, 50.0, C_PKT)
            h = 80.0 + rng.random() * 5 + (50.0 if rng.random() < 0.1 else 0)
            if t % 4 == 1:
                h += 60.0
            learn3.observe3(st, r["action"], h, True, 2, 18232 + t % 3, 50.0,
                            W=1280, u_mbps=2.0, c_pkt=C_PKT,
                            j_pred=r["j3_pred_pre_ms"])
        self.assertGreater(len(st.g_common), 0)
        self.assertGreater(st.n_dec, 0)
        d = json.loads(json.dumps(st.to_json()))
        self.assertEqual(d["v"], 11)
        self.assertFalse(d["c1_seen"])
        st2 = learn3.DestState3.from_json(d)
        self.assertEqual(st2.to_json(), st.to_json())
        r1 = decide3.decide3(st, 1280, 2.0, 50.0, C_PKT)
        r2 = decide3.decide3(st2, 1280, 2.0, 50.0, C_PKT)
        self.assertEqual((r1["action"], r1["ej"], r1["pen"], r1["why"]),
                         (r2["action"], r2["ej"], r2["pen"], r2["why"]))
        self.assertEqual(st2.to_json(), st.to_json())
        old = dict(d)
        old["v"] = 4
        with self.assertRaises(ValueError):
            learn3.DestState3.from_json(old)
        bad = json.loads(json.dumps(d))
        bad["g_alarm"] = {"9,9": 3}
        with self.assertRaises(ValueError):
            learn3.DestState3.from_json(bad)

    def test_no_default_c_pkt(self):
        st = learn3.new_state()
        with self.assertRaises(TypeError):
            decide3.decide3(st, 1280, 2.0, 50.0, None)


def point_state(k, w, cert, g):
    n = len(learn3.G)
    st = learn3.new_state()
    st.k_hist = [k]
    st.S_hist = [synth_s(cert, k, w)]
    st.post = [[1.0 if i == g else 0.0 for i in range(n)] for _ in learn3.H]
    st.w = [1.0, 0.0, 0.0, 0.0, 0.0]
    return st


def nominal2_ref(k, w, S, u, rtt, c):
    nn = learn3.bin_needed_s(S, quantum.bin_index(k * w), C_PKT)
    return layout.evaluate(k, c["W_eff"], c["m"], c["lead"], 0.0, rtt, u, nn)["e"] >= 0.5


class NominalSkipTests(unittest.TestCase):
    def test_nominal_two_rtt_observation_updates_windows_and_predicts(self):
        st = learn3.new_state()
        feed(st, (0, 3, 1), [80.0 + 0.1 * i for i in range(10)], 16000, 50.0, 2.0)
        upd0 = st.stats["upd"]
        self.assertGreater(upd0, 0)
        arm = (0, 0, 4)
        ctx = learn3.context(st, 1280, 2.0, 50.0, C_PKT)
        self.assertTrue(learn3.nominal_two_rtt(ctx, arm))
        self.assertFalse(learn3.shielded(ctx, arm))
        self.assertEqual(learn3.skip_reason(ctx, arm), "nominal2")
        self.assertIsNone(learn3.skip_reason(ctx, (0, 3, 1)))
        post0 = [list(p) for p in st.post]
        w0 = list(st.w)
        k0 = len(st.k_hist)
        S_before = list(st.S_hist)
        infos = feed(st, arm, [120.0, 121.0, 300.0], 16000, 50.0, 2.0)
        self.assertEqual([i["y"] for i in infos], [0, 0, 1])
        self.assertTrue(all(i["skip"] == "nominal2" for i in infos))
        self.assertFalse(any(i["updated"] or i["shielded"] for i in infos))
        self.assertEqual(st.post, predicted(post0, w0, 3))
        self.assertEqual(st.w, w0)
        self.assertEqual(st.stats["upd"], upd0)
        self.assertEqual(st.stats["nominal2"], 3)
        self.assertEqual(len(st.k_hist), k0 + 3)
        self.assertEqual(st.S_hist, (S_before + [synth_s(16000, 2, 1280)] * 2)[-learn3.S_WIN:])
        self.assertEqual(st.hct[learn3.arm_key(arm)], [120.0, 121.0, 300.0])
        info = feed(st, (0, 3, 1), [80.5], 16000, 50.0, 2.0)[0]
        self.assertTrue(info["updated"])
        self.assertNotEqual(st.post, post0)

    def test_skip_uses_v31_completion_rule(self):
        S = synth_s(6000, 2, 1280)
        ctx10 = {"k": 2, "S": S, "W": 1280, "u": 10.0, "rtt": 80.0,
                 "n_need": learn3.bin_needed_s(S, quantum.bin_index(2560), C_PKT)}
        ctx0 = dict(ctx10, u=0.0)
        self.assertEqual(ctx10["n_need"], 7)
        for arm in ((1, 0, 0), (1, 0, 4)):
            self.assertTrue(learn3.nominal_two_rtt(ctx10, arm))
            self.assertFalse(learn3.nominal_two_rtt(ctx0, arm))
        for arm in ((1, 1, 3), (0, 2, 2), (0, 1, 3)):
            self.assertFalse(learn3.nominal_two_rtt(ctx10, arm))


class ReevalTests(unittest.TestCase):
    def test_reeval_every_16th_qualifying_decision(self):
        k, w, cert, u, rtt = 2, 1280, 16000, 2.0, 50.0
        S = synth_s(cert, k, w)
        hi, lo = learn3.G.index(0.3), learn3.G.index(0.02)
        st = point_state(k, w, cert, hi)
        ref = decide3.decide_core(learn3.combined(st), k, w, S, u, rtt, C_PKT,
                                  keep_cands=True)
        self.assertTrue(ref["n2"])
        self.assertTrue(ref["reeval_cond"])
        self.assertTrue(nominal2_ref(k, w, S, u, rtt, ref))
        n1 = [c for c in ref["cands"] if not nominal2_ref(k, w, S, u, rtt, c)]
        self.assertEqual([c["n2"] for c in ref["cands"]],
                         [nominal2_ref(k, w, S, u, rtt, c) for c in ref["cands"]])
        jmin1 = min(c["ej"] for c in n1)
        tied1 = [c for c in n1 if c["ej"] <= jmin1 + policy.J_TIE_MS]
        alt = min(tied1, key=decide3.tie_key)
        self.assertEqual(ref["alt"]["action"], alt["action"])
        self.assertEqual(ref["alt"]["ej"], alt["ej"])
        self.assertFalse(alt["n2"])
        self.assertNotEqual(alt["action"], ref["action"])
        main, other = ref["action"], alt["action"]
        got = []
        for t in range(48):
            r = decide3.decide3(st, w, u, rtt, C_PKT)
            got.append((r["action"], r["why"], r["reeval"]))
            self.assertEqual(r["dec_index"], t + 1)
            self.assertEqual(r["n_reeval"], t + 1)
            self.assertEqual(r["j3_pred_pre_ms"], r["ej"])
            self.assertEqual(r["policy_version"], "v3.3.1-dev")
        for t, (a, why, rv) in enumerate(got):
            if (t + 1) % 16 == 0:
                self.assertEqual((a, why, rv), (other, "reeval", True))
            else:
                self.assertEqual((a, why, rv), (main, "ej", False))
        self.assertEqual(st.stats["reeval"], 3)
        st.post = [[1.0 if i == lo else 0.0 for i in range(len(learn3.G))]
                   for _ in learn3.H]
        for _ in range(10):
            r = decide3.decide3(st, w, u, rtt, C_PKT)
            self.assertFalse(r["reeval_cond"])
            self.assertEqual(r["why"], "ej")
        self.assertEqual(st.n_reeval, 48)
        self.assertEqual(st.n_dec, 58)
        st.post = [[1.0 if i == hi else 0.0 for i in range(len(learn3.G))]
                   for _ in learn3.H]
        whys = [decide3.decide3(st, w, u, rtt, C_PKT)["why"] for _ in range(16)]
        self.assertEqual(whys, ["ej"] * 15 + ["reeval"])
        self.assertEqual(st.stats["reeval"], 4)

    def test_no_reeval_without_nominal_one_candidate(self):
        st = point_state(2, 1280, 30000, learn3.G.index(0.3))
        for _ in range(40):
            r = decide3.decide3(st, 1280, 5.0, 200.0, C_PKT, keep_cands=True)
            self.assertTrue(r["n2"])
            self.assertIsNone(r["alt"])
            self.assertTrue(all(c["n2"] for c in r["cands"]))
            self.assertFalse(r["reeval_cond"])
            self.assertEqual(r["why"], "ej")
        self.assertEqual((st.n_reeval, st.n_dec, st.stats["reeval"]), (0, 40, 0))

    def test_cold_decisions_count_but_never_reeval(self):
        st = learn3.new_state()
        r = decide3.decide3(st, 1280, 2.0, 50.0, C_PKT)
        self.assertEqual((r["why"], r["reeval"], r["j3_pred_pre_ms"]), ("cold", False, None))
        self.assertEqual((st.n_dec, st.n_reeval), (1, 0))
        self.assertEqual(r["policy_version"], "v3.3.1-dev")


def feed_g(st, action, hcts, j_pred, cert=9000, rtt=50.0, u=2.0, k=2, w=1280):
    S = synth_s(cert, k, w)
    return [learn3.observe3(st, action, h, True, k, S, rtt, W=w, u_mbps=u,
                            c_pkt=C_PKT, j_pred=j_pred) for h in hcts]


class GuardTests(unittest.TestCase):
    A = (0, 1, 2)
    B = (0, 2, 2)

    def warm(self):
        st = learn3.new_state()
        ctx_feed = feed_g(st, self.B, [102.0] * 10, 100.0)
        self.assertTrue(all(i["resid"] == 2.0 for i in ctx_feed))
        ctx = learn3.context(st, 1280, 2.0, 50.0, C_PKT)
        self.assertFalse(learn3.nominal_two_rtt(ctx, self.A))
        self.assertFalse(learn3.nominal_two_rtt(ctx, self.B))
        return st

    def test_common_delay_is_median_of_all_success_residuals(self):
        st = learn3.new_state()
        self.assertEqual(learn3.guard_common(st), 0.0)
        feed_g(st, self.B, [101.0, 103.0], 100.0)
        self.assertEqual(learn3.guard_common(st), 2.0)
        feed_g(st, self.B, [110.0], 100.0)
        self.assertEqual(learn3.guard_common(st), 3.0)
        feed_g(st, self.B, [100.0 + i for i in range(100)], 100.0)
        self.assertEqual(len(st.g_common), learn3.GUARD_COMMON_WIN)
        self.assertEqual(len(st.g_resid[learn3.arm_key(self.B)]), learn3.GUARD_ACTION_WIN)
        self.assertEqual(st.g_common, [float(i) for i in range(36, 100)])
        self.assertEqual(learn3.guard_common(st), (67.0 + 68.0) / 2.0)
        self.assertEqual(learn3.mean_seq([1.0, 2.0, 4.0]), 7.0 / 3.0)

    def test_alarm_needs_eight_residuals_and_half_rtt_excess(self):
        st = self.warm()
        ka = learn3.arm_key(self.A)
        infos = feed_g(st, self.A, [140.0] * 7, 100.0)
        self.assertEqual(st.g_alarm, {})
        self.assertTrue(all(i["updated"] for i in infos if i["y"] is not None))
        self.assertEqual(learn3.guard_common(st), 2.0)
        post0 = [list(p) for p in st.post]
        info = feed_g(st, self.A, [140.0], 100.0)[0]
        self.assertEqual(info["raised"], [ka])
        self.assertTrue(info["alarmed"])
        self.assertEqual(info["skip"], "guard")
        self.assertFalse(info["updated"])
        self.assertEqual(st.post, predicted(post0, st.w))
        self.assertEqual(st.g_alarm, {ka: 0})
        self.assertEqual(st.stats["guard"], 1)
        self.assertEqual(st.stats["alarm_raised"], 1)
        self.assertEqual(len(st.g_common), 18)
        st2 = self.warm()
        feed_g(st2, self.B, [102.0] * 30, 100.0)
        feed_g(st2, self.A, [127.0] * 8, 100.0)
        self.assertEqual(learn3.guard_common(st2), 2.0)
        self.assertEqual(learn3.guard_excess(st2, ka, 2.0), 25.0)
        self.assertEqual(st2.g_alarm, {})
        feed_g(st2, self.A, [128.0] * 9, 100.0)
        self.assertEqual(learn3.guard_common(st2), 2.0)
        self.assertEqual(st2.g_alarm, {ka: 0})

    def test_alarmed_action_penalty_skip_and_clear(self):
        st = self.warm()
        ka = learn3.arm_key(self.A)
        feed_g(st, self.A, [140.0] * 8, 100.0)
        self.assertEqual(st.g_alarm, {ka: 0})
        n_common = len(st.g_common)
        b = learn3.guard_common(st)
        self.assertEqual(b, 2.0)
        self.assertEqual(learn3.guard_penalties(st, b), {ka: 38.0})
        r = decide3.decide3(st, 1280, 2.0, 50.0, C_PKT, keep_cands=True)
        self.assertEqual(r["guard_alarmed_actions"], 1)
        self.assertEqual(r["guard_common_ms"], 2.0)
        ca = [c for c in r["cands"] if c["action"] == self.A][0]
        self.assertEqual((ca["pen"], ca["score"]), (38.0, ca["ej"] + 38.0))
        self.assertTrue(all(c["pen"] == 0.0 for c in r["cands"] if c["action"] != self.A))
        self.assertTrue(all(c["score"] == c["ej"] for c in r["cands"] if c["action"] != self.A))
        self.assertEqual(r["guard_alarm"], r["action"] == self.A)
        self.assertEqual(r["jmin"], min(c["score"] for c in r["cands"]))
        post0 = [list(p) for p in st.post]
        infos = feed_g(st, self.A, [150.0, 150.0], 100.0)
        self.assertTrue(all(i["skip"] == "guard" and not i["updated"] for i in infos))
        self.assertEqual(st.post, predicted(post0, st.w, 2))
        self.assertEqual(len(st.g_common), n_common + 2)
        self.assertEqual(len(st.g_resid[ka]), 10)
        self.assertEqual(learn3.guard_penalties(st, b), {ka: 38.0})
        for t in range(2, 65):
            r = decide3.decide3(st, 1280, 2.0, 50.0, C_PKT)
            self.assertEqual(r["guard_cleared"], [])
            self.assertEqual(r["guard_alarmed_actions"], 1)
        self.assertEqual(st.n_dec, 64)
        r = decide3.decide3(st, 1280, 2.0, 50.0, C_PKT, keep_cands=True)
        self.assertEqual(r["guard_cleared"], [ka])
        self.assertEqual(r["guard_alarmed_actions"], 0)
        self.assertFalse(r["guard_alarm"])
        self.assertTrue(all(c["pen"] == 0.0 for c in r["cands"]))
        self.assertNotIn(ka, st.g_resid)
        self.assertEqual(st.g_alarm, {})
        self.assertEqual(st.stats["alarm_cleared"], 1)
        feed_g(st, self.B, [102.0] * 40, 100.0)
        feed_g(st, self.A, [140.0] * 7, 100.0)
        self.assertEqual(st.g_alarm, {})
        feed_g(st, self.A, [140.0], 100.0)
        self.assertEqual(st.g_alarm, {ka: 65})

    def test_penalty_floors_at_zero_when_common_delay_rises(self):
        st = self.warm()
        ka, kb = learn3.arm_key(self.A), learn3.arm_key(self.B)
        feed_g(st, self.A, [140.0] * 8, 100.0)
        self.assertIn(ka, st.g_alarm)
        feed_g(st, self.B, [160.0] * 64, 100.0)
        b = learn3.guard_common(st)
        self.assertEqual(b, 60.0)
        self.assertNotIn(kb, st.g_alarm)
        self.assertEqual(learn3.guard_penalty(st, ka, b), 0.0)
        self.assertEqual(learn3.guard_penalties(st, b), {ka: 0.0})

    def test_other_actions_can_alarm_when_common_delay_falls(self):
        st = learn3.new_state()
        ka = learn3.arm_key(self.A)
        feed_g(st, self.A, [120.0] * 8, 100.0)
        self.assertEqual(st.g_alarm, {})
        feed_g(st, self.B, [90.0] * 40, 100.0)
        self.assertEqual(learn3.guard_common(st), -10.0)
        self.assertEqual(st.g_alarm, {ka: 0})

    def test_no_residual_without_prediction(self):
        st = learn3.new_state()
        info = feed(st, self.B, [100.0], 9000, 50.0, 2.0)[0]
        self.assertIsNone(info["resid"])
        self.assertEqual((st.g_resid, st.g_common), ({}, []))
        with self.assertRaises(ValueError):
            learn3.observe3(st, self.B, 100.0, True, 2, 10000, 50.0, W=1280,
                            u_mbps=2.0, c_pkt=C_PKT, j_pred=float("nan"))


if __name__ == "__main__":
    unittest.main()
