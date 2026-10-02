import contextlib
import hashlib
import io
import itertools
import json
import math
import os
import shutil
import statistics
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

import blockstat as BST
import g3bed as G
import p21_gencompare as P

FAKE_SRC = "ab" * 32


def hcells():
    grid = {c["cell"]: c for c in P.h_cells()}
    return [grid[x] for x in P.h_draw(FAKE_SRC, excluded=[])["cells"]]


def write_dev_cells(root, cells=()):
    path = Path(root) / P.DEV_CELLS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": "padfec3.stage3_dev_cells.v1",
                                "cells": list(cells)}), encoding="utf-8")
    return path


def gate_reference(root):
    sha = {}
    for rel in (P.GATE_REFERENCE_REL,) + P.GATE_PY_SOURCES:
        path = Path(root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rel, encoding="utf-8")
        sha[rel] = G.sha256_file(str(path))
    return {"path": P.GATE_REFERENCE_REL, "sha256": sha[P.GATE_REFERENCE_REL],
            "sources": {rel: {"now": sha[rel]} for rel in P.GATE_PY_SOURCES}}


def cond_by(plan, cid):
    return next(c for c in plan["conds"] if c["cond"] == cid)


def blocks_of(plan, cid):
    return [b for b in plan["schedule"] if b["cond"] == cid]


def v31_row(ms, pred, alarm=False, reeval=False, alarmed=0, common=0.0, resid="auto"):
    return {"policy_version": "v3.1", "j3_pred_pre_ms": pred, "guard_alarm": alarm,
            "guard_resid_ms": (ms - pred) if resid == "auto" else resid,
            "guard_common_ms": common, "guard_alarmed_actions": alarmed, "reeval": reeval,
            "why3": "reeval" if reeval else "argmin"}


class ComparisonSettingsTests(unittest.TestCase):
    def test_default_stage3_uses_isolated_binary_and_artifact_paths(self):
        self.assertEqual(P.G3_TAG, "g3c")
        self.assertEqual(P.BINS["g3c"], "/tmp/qamp_g3/g3c/qamp")
        self.assertEqual(P.BUILD_SCRIPT, "experiments/quicbed/build_g3c.sh")
        self.assertEqual(P.ARMS["g3auto"]["bin"], P.G3_TAG)
        self.assertEqual(P.ARMS["g3fixL3"]["bin"], P.G3_TAG)
        self.assertEqual(P.ARMS["g3fixL2"]["bin"], P.G3_TAG)
        self.assertEqual(P.SERVERS_DEFAULT, {"A": "g2", "B": P.G3_TAG})
        self.assertEqual(P.SEAL_REL, "g3/SEAL_stage3.json")
        self.assertEqual(P.PROTOCOL_REL, "g3/PROTOCOL_stage3.md")
        self.assertEqual(P.HDRAW_REL, "g3/stage3_h_draw.json")
        self.assertEqual(P.HPRED_REL, "g3/stage3_h_predictions.json")
        self.assertEqual(P.DEV_CELLS_REL, "g3/dev_cells_stage3.json")
        self.assertEqual(P.TODO_MARK, "TODO(stage3-")
        self.assertEqual(P.WORK, "/tmp/padfec_p31")
        for path in P.paths("run1").values():
            self.assertTrue(os.path.basename(path).startswith("p31_"), path)

    def test_single_config_switches_tag_binary_build_and_stage_paths(self):
        cfg = dict(P.COMPARISON, stage=4, result_prefix="p41", g3_tag="g3d",
                   g3_bin="/tmp/qamp_g3/g3d/qamp",
                   build_script="experiments/quicbed/build_g3d.sh")
        settings = P.comparison_settings(cfg)
        self.assertEqual(settings["g3_tag"], "g3d")
        self.assertEqual(settings["bins"], {"g2": P.BINS["g2"],
                                             "g3d": "/tmp/qamp_g3/g3d/qamp"})
        self.assertEqual(settings["build_script"], cfg["build_script"])
        self.assertEqual(settings["work"], "/tmp/padfec_p41")
        self.assertEqual(settings["seal_rel"], "g3/SEAL_stage4.json")
        self.assertEqual(settings["hdraw_rel"], "g3/stage4_h_draw.json")
        self.assertEqual(settings["hpred_rel"], "g3/stage4_h_predictions.json")
        self.assertEqual(settings["dev_cells_rel"], "g3/dev_cells_stage4.json")
        self.assertEqual(settings["todo_mark"], "TODO(stage4-")

    def test_settings_refuse_stage2_artifact_or_binary_collisions(self):
        for change in ({"stage": 2}, {"result_prefix": "p21"}, {"g3_tag": "g3b"},
                       {"g3_bin": "/tmp/qamp_g3/g3b/qamp"},
                       {"g3_bin": "/tmp/qamp_g3/g2/qamp"},
                       {"g3_bin": "/tmp/qamp_g3/g3c/../g3b/qamp"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                P.comparison_settings(dict(P.COMPARISON, **change))


class PlanTests(unittest.TestCase):
    def test_run1_plan_matches_verdict_4_3(self):
        plan = P.build_plan("run1", hcells())
        fam = Counter(c["family"] for c in plan["conds"])
        self.assertEqual(fam, Counter({"AA": 1, "S": 2, "D": 12, "H": 4, "R": 1,
                                       "C": 2, "SEQ": 1}))
        n = {c["cond"]: c["n_per_arm"] for c in plan["conds"]}
        self.assertEqual(n["S_bigcert"], 4500)
        self.assertEqual(n["S_rtt200"], 4500)
        self.assertEqual(n["D_p17_mbps2"], 4500)
        self.assertEqual(n["D_p17_unlimited"], 4500)
        for cid in ("D_p11_2955_l0", "D_p11_9000_l5", "D_p15_4032_l2", "D_p18_burst3",
                    "SEQ_mbps2_l15"):
            self.assertEqual(n[cid], 1600)
        self.assertEqual(n["AA_bigcert"], 2700)
        self.assertEqual(cond_by(plan, "AA_bigcert")["cycles"], 3)
        self.assertEqual(n["C_bigcert_l2"], 800)
        self.assertEqual(n["C_2955_l0"], 800)
        for c in plan["conds"]:
            if c["family"] == "H":
                self.assertEqual(c["n_per_arm"], 1800)
                self.assertEqual(c["losses"], [1.0, 8.0])
                self.assertEqual(c["segment_n"], 300)
                self.assertEqual(c["cycles"], 3)
        self.assertEqual(cond_by(plan, "S_bigcert")["arms"], ["g2auto", "g3auto", "g3fixL3"])
        self.assertEqual(cond_by(plan, "S_rtt200")["arms"], ["g2auto", "g3auto", "g3fixL2"])
        for cid in ("S_bigcert", "S_rtt200"):
            self.assertEqual(cond_by(plan, cid)["servers"], {"A": "g2", "B": "g3c", "C": "g3c"})
        aa = cond_by(plan, "AA_bigcert")
        self.assertEqual(aa["servers"], {"A": "g2", "B": "g2"})
        self.assertEqual(aa["arms"], ["g2m3", "g2m3B"])
        seq = cond_by(plan, "SEQ_mbps2_l15")
        self.assertEqual(seq["servers"], {"A": "g2", "B": "g3c"})
        self.assertEqual(seq["arms"], ["g2m3", "g2m3B"])
        self.assertEqual(seq["loss"], 15.0)
        self.assertEqual(seq["n_per_arm"], 1600)
        self.assertEqual(seq["blocks"], 10)
        conns = sum(sum(b["sizes"].values()) for b in plan["schedule"])
        self.assertEqual(conns, 106800)
        self.assertEqual(len(plan["schedule"]), 386)
        for b in plan["schedule"]:
            c = cond_by(plan, b["cond"])
            self.assertEqual(sorted(b["order"]), sorted(c["arms"]))

    def test_run2_and_smoke_plans(self):
        r2 = P.build_plan("run2")
        self.assertEqual([c["cond"] for c in r2["conds"]], ["S_bigcert", "S_rtt200"])
        for c in r2["conds"]:
            self.assertEqual(c["arms"], ["g2auto", "g3auto"])
            self.assertEqual(c["n_per_arm"], 4500)
            self.assertEqual(c["batch"], "S run 2")
        sm = P.build_plan("smoke")
        fams = {c["family"] for c in sm["conds"]}
        self.assertEqual(fams, {"AA", "S", "D", "H", "R", "C", "SEQ"})
        h = [c for c in sm["conds"] if c["family"] == "H"][0]
        grid = {c["cell"] for c in P.h_cells()}
        self.assertNotIn(h["h_cell"], grid)
        r = cond_by(sm, P.REGRESSION_COND)
        self.assertEqual(r["regression_cell"], P.REGRESSION_CELL)
        self.assertIn(r["regression_cell"], P.load_h_exclusions()["cells"])
        self.assertEqual((r["segment_n"], r["cycles"], r["losses"]), (P.SMOKE_N, 1, [1.0, 8.0]))
        self.assertEqual([k["use"] for k in r["contrasts"]], [["REPORT_ONLY"]])

    def test_run1_without_draw_uses_labelled_placeholders(self):
        plan = P.build_plan("run1")
        hs = [c for c in plan["conds"] if c["family"] == "H"]
        self.assertEqual([c["cond"] for c in hs], ["H_slot1", "H_slot2", "H_slot3", "H_slot4"])
        self.assertTrue(all(c["placeholder"] for c in hs))

    def test_regression_condition_keeps_stage2_cell_and_schedule(self):
        plan = P.build_plan("run1", hcells())
        c = cond_by(plan, "R_c6000_r80_u10")
        self.assertEqual(c["family"], "R")
        self.assertEqual(c["arms"], ["g2auto", "g3auto"])
        self.assertEqual(c["profile"]["cert"], 6000)
        self.assertEqual(c["profile"]["rtt_ms"], 80)
        self.assertEqual(c["profile"]["uplink_policy_mbps"], 10)
        self.assertEqual(c["losses"], [1.0, 8.0])
        self.assertEqual(c["segment_n"], 300)
        self.assertEqual(c["cycles"], 3)
        self.assertEqual(c["n_per_arm"], 1800)
        self.assertEqual([(b["cycle"], b["loss"]) for b in blocks_of(plan, c["cond"])],
                         [(0, 1.0), (0, 8.0), (1, 1.0), (1, 8.0), (2, 1.0), (2, 8.0)])
        for contrast in c["contrasts"]:
            self.assertNotIn("H2", contrast["use"])
            self.assertNotIn("H3", contrast["use"])

    def test_arm_flags_mirror_p17_and_interface(self):
        self.assertEqual(P.arm_flags("g2auto", "/c"),
                         ["-fec", "auto", "-m", "1", "-cache", "/c", "-probe-every", "20"])
        self.assertEqual(P.arm_flags("g3auto", "/c"), ["-fec", "auto3", "-m", "1", "-cache3", "/c"])
        self.assertEqual(P.arm_flags("g3fixL3"), ["-fec", "fec", "-m", "4", "-layout", "v3",
                                                  "-lead", "3"])
        self.assertEqual(P.arm_flags("g3fixL2"), ["-fec", "fec", "-m", "4", "-layout", "v3",
                                                  "-lead", "2"])
        for a in ("g2m3", "g2m3B"):
            self.assertEqual(P.arm_flags(a, "/c"), ["-fec", "fec", "-m", "3"])
            self.assertEqual(P.ARMS[a]["bin"], "g2")
            self.assertFalse(P.is_auto(a))
        self.assertNotIn("g2autoB", P.ARMS)
        self.assertEqual(P.ARMS["g2auto"]["bin"], "g2")
        self.assertEqual(P.SLOTS[P.ARMS["g2auto"]["slot"]], 44433)
        self.assertEqual(P.SLOTS[P.ARMS["g3auto"]["slot"]], 44434)
        self.assertEqual(P.SLOTS[P.ARMS["g2m3"]["slot"]], 44433)
        self.assertEqual(P.SLOTS[P.ARMS["g2m3B"]["slot"]], 44434)
        self.assertEqual(P.SLOTS[P.ARMS["g3fixL3"]["slot"]], 44435)
        self.assertEqual(P.SLOTS[P.ARMS["g3fixL2"]["slot"]], 44435)
        self.assertEqual(P.BINS["g3c"], "/tmp/qamp_g3/g3c/qamp")
        self.assertNotIn("/g3/qamp", P.BINS.values())

    def test_every_arm_has_its_own_server_process(self):
        for run in ("run1", "run2", "smoke"):
            plan = P.build_plan(run, hcells() if run == "run1" else None)
            for c in plan["conds"]:
                slots = [P.ARMS[a]["slot"] for a in c["arms"]]
                self.assertEqual(len(set(slots)), len(slots), c["cond"])
                self.assertEqual(set(slots), set(c["servers"]), c["cond"])
        bad = P.conds_run1(hcells())
        bad[1]["servers"] = dict(P.SERVERS_DEFAULT)
        with patch.object(P, "conds_run1", lambda h: bad):
            with self.assertRaises(ValueError):
                P.build_plan("run1", hcells())
        est = {r["cond"]: r for r in P.estimate(P.build_plan("run1", hcells()))["conds"]}
        a = est["S_bigcert"]
        self.assertAlmostEqual(a["seconds"], a["connections"] * a["s_per_conn"]
                               + a["segments"] * (P.SEGMENT_FIXED_S
                                                  + P.settle_s(P.PROFILES["bigcert"]))
                               + 3 * P.SERVER_START_S)

    def test_profiles_and_flags_mirror_gen2_scripts(self):
        chk = P.mirror_check()
        self.assertTrue(chk["ok"], chk["differences"])
        self.assertEqual(P.PROFILES["bigcert"]["gap_ms"], 50)
        self.assertEqual(P.PROFILES["unlimited"]["gap_ms"], 8)
        self.assertEqual(P.PROFILES["p15_4032"]["group"], "x25519")
        self.assertEqual(P.PROFILES["p15_4032"]["expect_k"], 1)
        self.assertEqual(P.PROFILES["p18_burst3"]["burst"], 3.0)

    def test_condition_ids_unique_and_fingerprint_changes_with_plan(self):
        plan = P.build_plan("run1", hcells())
        ids = [c["cond"] for c in plan["conds"]]
        self.assertEqual(len(ids), len(set(ids)))
        c = plan["conds"][1]
        a = P.cond_fingerprint("run1", c, {"g2": "x", "g3c": "y"}, "s")
        c2 = dict(c, n_per_arm=c["n_per_arm"] + 1)
        self.assertNotEqual(a, P.cond_fingerprint("run1", c2, {"g2": "x", "g3c": "y"}, "s"))
        self.assertNotEqual(a, P.cond_fingerprint("run1", c, {"g2": "x", "g3c": "z"}, "s"))
        self.assertNotEqual(a, P.cond_fingerprint("run1", c, {"g2": "x", "g3c": "y"}, "t"))

    def test_estimate_has_all_batches(self):
        est = P.estimate(P.build_plan("run1", hcells()))
        self.assertEqual(set(est["batches"]), {"A/A", "S run 1", "D", "H", "cold",
                                               "server equivalence", "regression"})
        self.assertGreater(est["total_s"], 3600 * 3)
        self.assertLess(est["total_s"], 3600 * 8)
        self.assertEqual(set(P.estimate(P.build_plan("run2"))["batches"]), {"S run 2"})


class BalanceTests(unittest.TestCase):
    def test_w3_is_all_permutations(self):
        self.assertEqual(sorted(P.W3), sorted(itertools.permutations(range(3))))

    def precedence(self, blocks, x, y):
        return sum(1 for b in blocks if b["order"].index(x) < b["order"].index(y))

    def test_two_arm_schedules_balance_overall_and_within_one_per_stratum(self):
        plan = P.build_plan("run1", hcells())
        for c in plan["conds"]:
            if c["design"] != "sched" or len(c["arms"]) != 2:
                continue
            bl = blocks_of(plan, c["cond"])
            x, y = c["arms"]
            self.assertEqual(self.precedence(bl, x, y) * 2, len(bl), c["cond"])
            for s in range(len(c["losses"])):
                sb = [b for b in bl if b["stratum"] == s]
                k = self.precedence(sb, x, y)
                self.assertLessEqual(abs(2 * k - len(sb)), 1, c["cond"])

    def test_three_arm_s_conditions_balance_the_two_contrasts(self):
        plan = P.build_plan("run1", hcells())
        for cid, fx in (("S_bigcert", "g3fixL3"), ("S_rtt200", "g3fixL2")):
            bl = blocks_of(plan, cid)
            self.assertEqual(len(bl), 10)
            self.assertEqual(self.precedence(bl, "g2auto", "g3auto"), 5)
            self.assertEqual(self.precedence(bl, fx, "g3auto"), 5)
            for s in (0, 1):
                sb = [b for b in bl if b["stratum"] == s]
                self.assertIn(self.precedence(sb, "g2auto", "g3auto"), (2, 3))
                self.assertIn(self.precedence(sb, fx, "g3auto"), (2, 3))
            pos = P.order_balance(cond_by(plan, cid), bl)["positions"]
            for a, cnt in pos.items():
                self.assertEqual(sorted(cnt.values()), [3, 3, 4], (cid, a))

    def test_block_and_cold_designs_alternate_ab_ba(self):
        plan = P.build_plan("run1", hcells())
        for c in plan["conds"]:
            if c["design"] == "sched":
                continue
            bl = blocks_of(plan, c["cond"])
            for i, b in enumerate(bl):
                self.assertEqual(b["order"], c["arms"] if i % 2 == 0 else c["arms"][::-1])
            self.assertEqual(self.precedence(bl, *c["arms"]) * 2, len(bl))
            self.assertEqual(sum(b["sizes"][c["arms"][0]] for b in bl), c["n_per_arm"])
            if c["design"] == "cold":
                self.assertTrue(all(b["clear_cache"] for b in bl))
                self.assertTrue(all(set(b["sizes"].values()) == {8} for b in bl))
            else:
                self.assertFalse(any(b["clear_cache"] for b in bl))

    def test_sched_runs_cycle_major(self):
        plan = P.build_plan("run1", hcells())
        bl = blocks_of(plan, "S_bigcert")
        self.assertEqual([(b["cycle"], b["loss"]) for b in bl[:4]],
                         [(0, 2.0), (0, 15.0), (1, 2.0), (1, 15.0)])
        self.assertEqual([b["block"] for b in bl], list(range(10)))


class EstimatorTests(unittest.TestCase):
    def test_t_sf_inverts_t_crit(self):
        for df in (1.0, 4.0, 6.7, 30.0):
            for a in (0.05, 0.01, 0.0125):
                t = BST.t_crit(df, a)
                self.assertAlmostEqual(P.t_sf(t, df), a / 2.0, places=9)
                self.assertAlmostEqual(P.t_sf(-t, df), 1 - a / 2.0, places=9)
        self.assertAlmostEqual(P.t_sf(0.0, 5.0), 0.5)

    def test_stratified_welch_matches_hand_computation(self):
        d0 = [1.0, 2.0, 3.0, 4.0, 5.0]
        d1 = [10.0, 10.5, 9.0, 11.0, 12.5]
        dx = {(c, 0): 100.0 + d0[c] for c in range(5)}
        dx.update({(c, 1): 200.0 + d1[c] for c in range(5)})
        dy = {(c, 0): 100.0 for c in range(5)}
        dy.update({(c, 1): 200.0 for c in range(5)})
        r = P.stratified(dx, dy, {0: 0.5, 1: 0.5})
        v0, v1 = statistics.variance(d0), statistics.variance(d1)
        est = 0.5 * statistics.mean(d0) + 0.5 * statistics.mean(d1)
        t0, t1 = 0.25 * v0 / 5, 0.25 * v1 / 5
        self.assertAlmostEqual(r["est"], est)
        self.assertAlmostEqual(r["se"], math.sqrt(t0 + t1))
        self.assertAlmostEqual(r["df"], (t0 + t1) ** 2 / (t0 * t0 / 4 + t1 * t1 / 4))
        lo, hi = P.interval(r)
        h = BST.t_crit(r["df"], 0.05) * r["se"]
        self.assertAlmostEqual(lo, est - h)
        self.assertAlmostEqual(hi, est + h)

    def test_stratified_equal_variances_gives_pooled_df(self):
        d = [1.0, 3.0, 2.0, 5.0, 4.0]
        dx = {(c, s): d[c] for c in range(5) for s in (0, 1)}
        dy = {(c, s): 0.0 for c in range(5) for s in (0, 1)}
        self.assertAlmostEqual(P.stratified(dx, dy, {0: 0.5, 1: 0.5})["df"], 8.0)

    def test_stratified_needs_two_units_per_stratum(self):
        r = P.stratified({(0, 0): 1.0, (0, 1): 2.0}, {(0, 0): 0.0, (0, 1): 0.0},
                         {0: 0.5, 1: 0.5})
        self.assertIsNone(r["est"])
        self.assertEqual(P.interval(r), (None, None))
        self.assertEqual(P.q_value(r["est"], r["se"], r["df"], 0.0), 1.0)

    def test_paired_blocks(self):
        bx = {b: 50.0 + b + (0.5 if b % 2 else -0.5) for b in range(10)}
        by = {b: 50.0 + b for b in range(10)}
        r = P.paired_blocks(bx, by)
        d = [bx[b] - by[b] for b in range(10)]
        self.assertAlmostEqual(r["est"], statistics.mean(d))
        self.assertAlmostEqual(r["se"], statistics.stdev(d) / math.sqrt(10))
        self.assertEqual(r["df"], 9.0)
        same = P.paired_blocks({0: 1.0, 1: 2.0}, {0: 0.0, 1: 1.0})
        self.assertEqual(same["se"], 0.0)
        self.assertEqual(P.interval(same), (1.0, 1.0))
        self.assertEqual(P.q_value(1.0, 0.0, 1.0, 0.0), 0.0)
        self.assertEqual(P.q_value(-1.0, 0.0, 1.0, 0.0), 1.0)

    def test_imputation_counts_failed_and_missing_at_timeout(self):
        seg = {"rows": [{"ok": True, "ms": 50.0}, {"ok": False, "ms": 3.0},
                        {"ok": True, "ms": 70.0}]}
        self.assertAlmostEqual(P.segment_mean_imputed(seg, 4),
                               (50.0 + 70.0 + 2 * P.IMPUTE_MS) / 4)
        self.assertEqual(P.IMPUTE_MS, 10000.0)

    def test_one_rtt_rule_uses_row_lead_and_rate(self):
        prof = P.PROFILES["bigcert"]
        row = {"ok": True, "ms": 80.0, "first_flight_bytes": 2560,
               "first_flight_parity_dgrams": 4, "first_flight_parity_bytes": 4 * 1331,
               "first_flight_lead_dgrams": 3}
        cut = 1.5 * 50 + 8 * (2560 + 3 * 1331) / 2000.0
        self.assertTrue(P.one_rtt(dict(row, ms=cut - 0.01), prof))
        self.assertFalse(P.one_rtt(dict(row, ms=cut + 0.01), prof))
        legacy = {"ok": True, "ms": 1.0, "first_flight_bytes": 2560,
                  "first_flight_parity_dgrams": 3, "first_flight_parity_bytes": 3 * 1331,
                  "m_used": 3}
        self.assertEqual(P.row_lead(legacy), 1)
        self.assertEqual(P.row_lead(dict(legacy, m_used=1, first_flight_parity_dgrams=1)), 0)

    def test_row_action_fields(self):
        self.assertEqual(P.row_action({"action": [0, 2, 2]}), (0, 2, 2))
        self.assertEqual(P.row_action({"action": {"delta": 1, "lead": 1, "T": 0}}), (1, 1, 0))
        self.assertEqual(P.row_action({"a_delta": 0, "a_lead": 3, "a_T": 1}), (0, 3, 1))
        self.assertIsNone(P.row_action({"lead": 3, "m_used": 4}))
        self.assertEqual(P.row_j3({"ej": 81.5}), 81.5)
        self.assertEqual(P.row_pmean({"p_mean": 0.02}), 0.02)
        self.assertIsNone(P.row_j3({"j3_ms": True}))


class HolmTests(unittest.TestCase):
    def test_holm_ties_keep_original_family_order(self):
        tests = [{"cond": cid, "c": 0.0, "q": 0.01, "est": None}
                 for cid in ("S_rtt200", "S_bigcert", "H_slot1")]
        P.holm(tests)
        self.assertEqual([t["cond"] for t in tests], ["S_rtt200", "S_bigcert", "H_slot1"])
        self.assertEqual([t["holm_rank"] for t in tests], [1, 2, 3])

    def test_holm_step_down(self):
        tests = [{"c": 0.0, "q": q, "est": None} for q in (0.01, 0.04, 0.03, 0.005)]
        P.holm(tests)
        self.assertEqual([t["holm_rank"] for t in tests], [2, 4, 3, 1])
        self.assertEqual([t["reject"] for t in tests], [True, False, False, True])
        self.assertAlmostEqual(tests[3]["p_holm"], 0.02)
        self.assertAlmostEqual(tests[0]["p_holm"], 0.03)
        self.assertAlmostEqual(tests[2]["p_holm"], 0.06)
        self.assertAlmostEqual(tests[1]["p_holm"], 0.06)
        self.assertEqual([t["holm_level"] for t in tests],
                         [0.05 / 3, 0.05 / 1, 0.05 / 2, 0.05 / 4])

    def test_holm_bounds_agree_with_rejection_for_first_rank(self):
        tests = [{"c": 0.0, "est": 3.0, "se": 1.0, "df": 8.0},
                 {"c": 0.0, "est": 0.5, "se": 1.0, "df": 8.0}]
        P.holm(tests)
        first = tests[0]
        self.assertEqual(first["holm_rank"], 1)
        self.assertAlmostEqual(first["lb_holm"], 3.0 - BST.t_crit(8.0, 0.025))
        self.assertEqual(first["reject"], first["lb_holm"] > 0)
        self.assertFalse(tests[1]["reject"])
        self.assertLess(tests[1]["lb_holm"], 0)

    def test_holm_with_noninferiority_margin(self):
        tests = [{"c": -1.0, "est": -0.2, "se": 0.1, "df": 9.0}]
        P.holm(tests)
        self.assertTrue(tests[0]["reject"])
        self.assertGreater(tests[0]["lb_holm"], -1.0)
        tests = [{"c": -1.0, "est": -0.8, "se": 0.5, "df": 9.0}]
        P.holm(tests)
        self.assertFalse(tests[0]["reject"])


def con(cid, est, se, df=8.0, x="g2auto", y="g3auto"):
    r = {"id": cid, "x": x, "y": y, "est": est, "se": se, "df": df}
    r["lo95"], r["hi95"] = P.interval(r)
    return r


def csum(cid, family, cons, arms=None, h_cell=None):
    return {"cond": cid, "family": family, "contrasts": cons, "arms": arms or {},
            "h_cell": h_cell, "complete": True}


def harness(aa=(0.2, 0.3), seq=(-0.1, 0.2)):
    return [csum("AA_bigcert", "AA", [con("A-B", aa[0], aa[1], x="g2m3", y="g2m3B")]),
            csum("SEQ_mbps2_l15", "SEQ", [con("A-B", seq[0], seq[1], x="g2m3", y="g2m3B")])]


def harness_ok():
    return harness()


def bound_of(conds):
    return max(max(abs(c["contrasts"][0]["lo95"]), abs(c["contrasts"][0]["hi95"]))
               for c in conds)


def run1(s_est=(30.0, 20.0), s_se=(1.0, 2.0), d=(), h=(), fix=(5.0, 4.0), hx=None):
    conds = list(hx) if hx is not None else harness_ok()
    for (cid, e, se, f) in zip(("S_bigcert", "S_rtt200"), s_est, s_se, fix):
        conds.append(csum(cid, "S", [con("g2-g3", e, se),
                                     con("fix-g3", f, 1.0, x="g3fix", y="g3auto")]))
    for i, (e, se) in enumerate(d):
        conds.append(csum("D_%d" % i, "D", [con("g2-g3", e, se, df=9.0)]))
    for cell, e, se in h:
        conds.append(csum("H_" + cell, "H", [con("g2-g3", e, se)], h_cell=cell))
    return {"conds": conds}


class DecisionTests(unittest.TestCase):
    def test_development_keeps_statistics_without_h1_to_h4_verdicts(self):
        r1 = run1(h=[("h_c6000_r20_u0", 10.0, 1.0)])
        r2 = run1()
        pred = {"cells": {"h_c6000_r20_u0": {"delta_hat_ms": 8.0}}}
        with contextlib.ExitStack() as st:
            evaluators = [st.enter_context(patch.object(P, name))
                          for name in ("h1_eval", "h2_eval", "h3_eval", "h4_eval")]
            d = P.decide(r1, r2, pred, label="development")
        self.assertTrue(d["verdicts_suspended"])
        for key in ("H1", "H2", "H3", "H4"):
            self.assertFalse(d[key]["evaluable"])
            self.assertEqual(d[key]["status"], "평가 불가")
            self.assertNotIn("pass", d[key])
        self.assertEqual(d["H1"]["claim"], "평가 불가")
        self.assertEqual(d["descriptive"], {"run1": r1["conds"], "run2": r2["conds"]})
        self.assertNotIn("expected_failure_p15_bytes", d)
        for evaluator in evaluators:
            evaluator.assert_not_called()

    def test_h1_pass_and_claim_needs_run2_same_direction(self):
        d = P.decide(run1())
        self.assertTrue(d["harness"]["ok"])
        self.assertTrue(d["H1"]["run1"]["pass"])
        self.assertEqual(d["H1"]["claim"], "pending run 2")
        r2 = {"conds": [csum("S_bigcert", "S", [con("g2-g3", 25.0, 2.0)]),
                        csum("S_rtt200", "S", [con("g2-g3", 0.4, 3.0)])]}
        d = P.decide(run1(), r2)
        self.assertTrue(d["H1"]["claim"].startswith("improvement claimed"))
        self.assertFalse(d["H1"]["run2"]["pass"])
        r2 = {"conds": [csum("S_bigcert", "S", [con("g2-g3", 25.0, 2.0)]),
                        csum("S_rtt200", "S", [con("g2-g3", -0.4, 3.0)])]}
        d = P.decide(run1(), r2)
        self.assertTrue(d["H1"]["claim"].startswith("no improvement claim (run 2"))

    def test_h1_fails_on_one_lower_bound_or_small_mean(self):
        d = P.decide(run1(s_est=(30.0, 1.0), s_se=(1.0, 2.0)))
        self.assertFalse(d["H1"]["run1"]["pass"])
        self.assertTrue(d["H1"]["claim"].startswith("no improvement claim (H1 failed"))
        tiny = harness(aa=(0.0, 0.001), seq=(0.0, 0.001))
        d = P.decide(run1(s_est=(0.8, 0.8), s_se=(0.01, 0.01), hx=tiny))
        self.assertLess(d["harness"]["B_ms"], 0.01)
        t = d["H1"]["run1"]["tests"]
        self.assertTrue(all(x["reject"] for x in t))
        self.assertLess(d["H1"]["run1"]["mean_lb_holm"], 1.0)
        self.assertFalse(d["H1"]["run1"]["pass"])
        d = P.decide(run1(s_est=(1.6, 1.6), s_se=(0.05, 0.05), hx=tiny))
        self.assertGreaterEqual(d["H1"]["run1"]["mean_lb_holm"], 1.0)
        self.assertTrue(d["H1"]["run1"]["pass"])

    def test_h1_lower_bounds_must_exceed_the_harness_bound(self):
        hx = harness(aa=(0.5, 1.0), seq=(-0.2, 0.5))
        b = bound_of(hx)
        self.assertAlmostEqual(b, 0.5 + BST.t_crit(8.0, 0.05) * 1.0)
        d = P.decide(run1(s_est=(30.0, 3.0), s_se=(1.0, 0.2), hx=hx))
        self.assertAlmostEqual(d["harness"]["B_ms"], b)
        self.assertAlmostEqual(d["H1"]["run1"]["threshold_ms"], b)
        t = {x["cond"]: x for x in d["H1"]["run1"]["tests"]}
        self.assertGreater(t["S_rtt200"]["lb_holm"], 1.0)
        self.assertLess(t["S_rtt200"]["lb_holm"], b)
        self.assertFalse(t["S_rtt200"]["reject"])
        self.assertTrue(t["S_bigcert"]["reject"])
        self.assertGreaterEqual(d["H1"]["run1"]["mean_lb_holm"], 1.0)
        self.assertFalse(d["H1"]["run1"]["pass"])
        d = P.decide(run1(s_est=(30.0, 5.0), s_se=(1.0, 0.2), hx=hx))
        t = {x["cond"]: x for x in d["H1"]["run1"]["tests"]}
        self.assertGreater(t["S_rtt200"]["lb_holm"], b)
        self.assertTrue(d["H1"]["run1"]["pass"])
        self.assertEqual(d["H1"]["claim"], "pending run 2")
        r2 = {"conds": [csum("S_bigcert", "S", [con("g2-g3", 25.0, 2.0)]),
                        csum("S_rtt200", "S", [con("g2-g3", 3.0, 0.2)])]}
        d = P.decide(run1(s_est=(30.0, 5.0), s_se=(1.0, 0.2), hx=hx), r2)
        self.assertAlmostEqual(d["H1"]["run2"]["threshold_ms"], b)
        self.assertFalse(d["H1"]["run2"]["pass"])
        self.assertTrue(d["H1"]["claim"].startswith("improvement claimed"))

    def test_h2_noninferiority_over_s_d_h(self):
        d = P.decide(run1(d=[(0.1, 0.2), (-0.3, 0.2), (-3.0, 0.3)], h=[("h_c6000_r20_u0",
                                                                          2.0, 1.0)]))
        h2 = d["H2"]["run1"]
        self.assertEqual(h2["family_size"], 2 + 3 + 1)
        self.assertEqual(h2["failed"], ["D_2"])
        self.assertFalse(h2["pass"])
        d = P.decide(run1(d=[(0.1, 0.2), (-0.3, 0.2)]))
        self.assertTrue(d["H2"]["run1"]["pass"])

    def test_regression_is_reported_outside_h2_and_h3_families(self):
        cell = "h_c6000_r20_u0"
        r = run1(h=[(cell, 4.0, 0.1)])
        pred = {"cells": {cell: {"delta_hat_ms": 4.0},
                          "h_c6000_r80_u10": {"delta_hat_ms": 100.0}}}
        baseline = P.decide(r, None, pred)
        regression = csum("R_c6000_r80_u10", "R", [con("g2-g3", -100.0, 0.1)],
                          h_cell="h_c6000_r80_u10")
        r["conds"].append(regression)
        result = P.decide(r, None, pred)
        self.assertEqual(result["H2"], baseline["H2"])
        self.assertEqual(result["H3"], baseline["H3"])
        self.assertNotIn(regression["cond"],
                         [t["cond"] for t in result["H2"]["run1"]["tests"]])

    def test_h2_categories(self):
        d = P.decide(run1(d=[(0.1, 0.2), (-3.0, 0.3), (-0.5, 3.0), (-0.4, 0.1)]))
        h2 = d["H2"]["run1"]
        cat = {t["cond"]: t["category"] for t in h2["tests"]}
        self.assertEqual(cat["D_0"], "비열등 확인")
        self.assertEqual(cat["D_1"], "열등 확인")
        self.assertEqual(cat["D_2"], "판정불능(검정력 부족)")
        self.assertEqual(cat["D_3"], "비열등 확인")
        t3 = next(t for t in h2["tests"] if t["cond"] == "D_3")
        self.assertTrue(t3["holm_ub_below_0"])
        for t in h2["tests"]:
            self.assertAlmostEqual(t["ub_holm"], t["est"] + BST.t_crit(
                t["df"], t["inferior_holm_level"]) * t["se"])
            self.assertEqual(t["category"] == "비열등 확인", t["reject"])
            if t["category"] == "열등 확인":
                self.assertTrue(t["inferior_reject"])
                self.assertLess(t["ub_holm"], 0.0)
        inf = {t["cond"]: t for t in h2["tests"]}
        self.assertEqual(inf["D_1"]["inferior_holm_rank"], 1)
        self.assertAlmostEqual(inf["D_1"]["inferior_holm_level"], 0.05 / 6)
        self.assertEqual(inf["D_3"]["inferior_holm_rank"], 2)
        self.assertTrue(inf["D_3"]["inferior_reject"])
        self.assertFalse(inf["D_2"]["inferior_reject"])
        self.assertEqual(h2["category_counts"], {"비열등 확인": 4, "열등 확인": 1,
                                                 "판정불능(검정력 부족)": 1})
        self.assertEqual(h2["by_category"]["판정불능(검정력 부족)"], ["D_2"])
        self.assertFalse(h2["pass"])
        self.assertIn("not evidence", h2["reading"])
        d = P.decide(run1(d=[(0.1, 0.2), (-1.2, 0.4)]))
        t = next(x for x in d["H2"]["run1"]["tests"] if x["cond"] == "D_1")
        self.assertEqual(t["holm_rank"], 4)
        self.assertLess(t["est"] + BST.t_crit(t["df"], t["holm_level"]) * t["se"], 0.0)
        self.assertEqual(t["inferior_holm_rank"], 1)
        self.assertGreater(t["ub_holm"], 0.0)
        self.assertEqual(t["category"], "판정불능(검정력 부족)")
        d = P.decide(run1(d=[(0.1, 0.2), (-0.4, 0.1)]))
        self.assertEqual(d["H2"]["run1"]["category_counts"]["비열등 확인"], 4)
        self.assertTrue(d["H2"]["run1"]["pass"])
        miss = run1()
        miss["conds"].append(csum("D_x", "D", [{"id": "g2-g3", "est": None, "se": None,
                                                 "df": None, "lo95": None, "hi95": None}]))
        t = next(x for x in P.decide(miss)["H2"]["run1"]["tests"] if x["cond"] == "D_x")
        self.assertEqual(t["category"], "판정불능(검정력 부족)")
        self.assertIsNone(t["ub_holm"])
        self.assertIn("no estimate", t["why"])

    def test_h3_rules(self):
        h = [("h_c6000_r20_u0", 10.0, 1.0), ("h_c8000_r80_u1", 0.5, 1.0),
             ("h_c14000_r120_u5", 9.0, 1.0)]
        pred = {"cells": {"h_c6000_r20_u0": {"delta_hat_ms": 8.0},
                          "h_c8000_r80_u1": {"delta_hat_ms": 1.0},
                          "h_c14000_r120_u5": {"delta_hat_ms": 3.0}}}
        d = P.decide(run1(h=h), None, pred)
        h3 = d["H3"]
        self.assertTrue(h3["evaluable"])
        self.assertEqual([w["cond"] for w in h3["weak"]], ["H_h_c8000_r80_u1"])
        res = {t["cond"]: t for t in h3["strong"]}
        self.assertTrue(res["H_h_c6000_r20_u0"]["pass"])
        self.assertFalse(res["H_h_c14000_r120_u5"]["ratio_ok"])
        self.assertFalse(h3["pass"])
        self.assertFalse(P.decide(run1(h=h), None, None)["H3"]["evaluable"])
        part = {"cells": {"h_c6000_r20_u0": {"delta_hat_ms": 8.0}}}
        self.assertFalse(P.decide(run1(h=h), None, part)["H3"]["pass"])

    def test_h3_without_targets_reports_no_validation_evidence(self):
        cell = "h_c6000_r20_u0"
        for r, pred in ((run1(), {"cells": {}}),
                        (run1(h=[(cell, 20.0, 0.1)]),
                         {"cells": {cell: {"delta_hat_ms": 1.99}}})):
            with self.subTest(pred=pred):
                h3 = P.decide(r, None, pred)["H3"]
                self.assertEqual(h3["target_count"], 0)
                self.assertFalse(h3["evaluable"])
                self.assertFalse(h3["pass"])
                self.assertEqual(h3["status"], "대상 0개, H3 검증 증거 없음")
                self.assertEqual(h3["strong"], [])

    def test_h4_adaptation_contributed(self):
        d = P.decide(run1(fix=(5.0, -0.5)))
        t = {x["cond"]: x for x in d["H4"]["tests"]}
        self.assertTrue(t["S_bigcert"]["adaptation_contributed"])
        self.assertFalse(t["S_rtt200"]["adaptation_contributed"])

    def test_harness_not_detected_gives_the_bound(self):
        hx = harness(aa=(1.2, 1.0), seq=(-0.3, 0.4))
        d = P.decide(run1(hx=hx))
        h = d["harness"]
        self.assertFalse(h["harness_bias_detected"])
        self.assertTrue(h["ok"])
        self.assertFalse(d["verdicts_suspended"])
        aa, seq = h["controls"]["AA"], h["controls"]["SEQ"]
        self.assertLess(aa["lo95"], 0.0)
        self.assertGreater(aa["hi95"], 0.0)
        self.assertFalse(aa["ci_excludes_0"])
        self.assertAlmostEqual(aa["bound_ms"], max(abs(aa["lo95"]), abs(aa["hi95"])))
        self.assertAlmostEqual(seq["bound_ms"], max(abs(seq["lo95"]), abs(seq["hi95"])))
        self.assertAlmostEqual(h["B_ms"], max(aa["bound_ms"], seq["bound_ms"]))
        self.assertAlmostEqual(h["B_ms"], 1.2 + BST.t_crit(8.0, 0.05) * 1.0)
        self.assertAlmostEqual(h["h1_threshold_ms"], h["B_ms"])
        self.assertAlmostEqual(d["H1"]["run1"]["threshold_ms"], h["B_ms"])
        self.assertTrue(d["H1"]["run1"]["pass"])
        hx = harness(aa=(0.0, 0.0), seq=(0.0, 0.0))
        h = P.decide(run1(hx=hx))["harness"]
        self.assertTrue(h["ok"])
        self.assertEqual(h["B_ms"], 0.0)

    def test_harness_bias_detected_suspends_everything(self):
        for hx in (harness(aa=(3.0, 1.0)), harness(seq=(-0.6, 0.1)),
                   harness(aa=(-5.0, 1.0), seq=(0.5, 0.1))):
            d = P.decide(run1(hx=hx))
            self.assertTrue(d["harness"]["harness_bias_detected"])
            self.assertFalse(d["harness"]["ok"])
            self.assertIsNone(d["harness"]["h1_threshold_ms"])
            self.assertIsNotNone(d["harness"]["B_ms"])
            self.assertTrue(d["verdicts_suspended"])
            self.assertEqual(d["H1"]["claim"], "suspended (harness bias detected)")
            self.assertFalse(d["H1"]["run1"]["pass"])
        d = P.decide(run1(hx=harness(aa=(3.0, 1.0))))
        self.assertTrue(d["harness"]["controls"]["AA"]["ci_excludes_0"])
        self.assertFalse(d["harness"]["controls"]["SEQ"]["ci_excludes_0"])
        d = P.decide(run1(hx=harness(aa=(0.9, 0.1))))
        self.assertTrue(d["harness"]["harness_bias_detected"])

    def test_harness_missing_control_suspends(self):
        r = run1()
        r["conds"] = r["conds"][1:]
        d = P.decide(r)
        self.assertFalse(d["harness"]["ok"])
        self.assertFalse(d["harness"]["evaluable"])
        self.assertFalse(d["harness"]["harness_bias_detected"])
        self.assertIsNone(d["harness"]["B_ms"])
        self.assertTrue(d["verdicts_suspended"])
        self.assertEqual(d["H1"]["claim"], "suspended (harness control missing or not evaluable)")
        self.assertFalse(d["H1"]["run1"]["evaluable"])
        r = run1()
        r["conds"][0]["contrasts"] = [{"id": "A-B", "est": None, "se": None, "df": None,
                                       "lo95": None, "hi95": None}]
        self.assertFalse(P.decide(r)["harness"]["ok"])

    def test_p15_expected_failure_check(self):
        r = run1()
        r["conds"].append(csum("D_p15_4032_l0", "D", [con("g2-g3", 0.0, 0.1)], arms={
            "g2auto": {"final_block_added_bytes_mean": 1327.0},
            "g3auto": {"final_block_added_bytes_mean": 3979.0}}))
        e = P.decide(r)["expected_failure_p15_bytes"]
        self.assertEqual(P.P15_NOMINAL_M2_ADDED, 2650)
        self.assertTrue(e["arms"]["g2auto"]["pass"])
        self.assertFalse(e["arms"]["g3auto"]["pass"])
        self.assertTrue(e["g3_failed_as_expected"])

    def test_added_bytes_uses_k(self):
        row = {"first_flight_bytes": 1281, "first_flight_parity_bytes": 2 * 1326}
        self.assertEqual(P.added_bytes(row, 1), 1281 + 2652 - 1280)


def auto3_row(i, ms, action, ok=True, guard=True, **v31):
    r = {"i": i, "ok": ok, "ms": ms, "layout": "v3", "action": list(action), "j3_ms": 80.0,
         "p_mean": 0.02, "first_flight_bytes": 2562, "first_flight_parity_dgrams": 4,
         "first_flight_parity_bytes": 4 * 1320, "first_flight_lead_dgrams": action[1]}
    if guard:
        r.update(v31_row(ms, 80.0, **v31))
    return r


class GuardReportTests(unittest.TestCase):
    def rows(self):
        return [auto3_row(0, 85.0, (1, 0, 4)),
                auto3_row(1, 165.0, (1, 0, 4), alarm=True, alarmed=1, common=2.5),
                auto3_row(2, 86.0, (0, 2, 2), reeval=True, alarmed=1, common=2.5),
                auto3_row(3, 10000.0, (1, 0, 4), ok=False, alarm=True, alarmed=2, common=3.0,
                          resid=None),
                auto3_row(4, 90.0, (0, 2, 2), alarmed=2, common=3.0)]

    def test_guard_summary_counts_alarms_reeval_residuals_and_actions(self):
        g = P.guard_summary(self.rows())
        self.assertEqual(g["rows"], 5)
        self.assertEqual(g["policy_version"], {"v3.1": 5})
        self.assertEqual(g["rows_with_all_guard_fields"], 5)
        self.assertEqual((g["alarm_count"], g["alarm_observed_n"]), (2, 5))
        self.assertAlmostEqual(g["alarm_share"], 0.4)
        self.assertEqual(g["first_alarm_row"], 1)
        self.assertEqual(g["alarmed_chosen_actions"], {"1,0,4": 2})
        self.assertEqual((g["reeval_count"], g["reeval_observed_n"]), (1, 5))
        self.assertAlmostEqual(g["reeval_share"], 0.2)
        self.assertEqual(g["reeval_actions"], {"0,2,2": 1})
        self.assertEqual(g["reeval_why3_mismatch_rows"], 0)
        self.assertEqual(g["guard_resid_ms"]["n"], 4)
        self.assertAlmostEqual(g["guard_resid_ms"]["mean"], (5.0 + 85.0 + 6.0 + 10.0) / 4)
        self.assertEqual(g["guard_resid_ms_failed"]["n"], 0)
        self.assertEqual(g["guard_resid_null_rows"], 1)
        self.assertEqual(g["guard_resid_mismatch_ok_rows"], 0)
        self.assertEqual(g["guard_resid_missing_ok_rows"], 0)
        self.assertEqual(g["guard_common_ms"]["last"], 3.0)
        self.assertEqual(g["guard_alarmed_actions"]["max"], 2)
        self.assertEqual(g["guard_alarmed_actions"]["last"], 2)
        self.assertEqual(g["guard_alarmed_actions"]["rows_any"], 4)
        m = P.monitoring_summary(self.rows(), P.PROFILES["unlimited"])
        self.assertEqual(m["by_action"]["1,0,4"]["alarm_count"], 2)
        self.assertEqual(m["by_action"]["0,2,2"]["reeval_count"], 1)
        self.assertEqual(m["by_action"]["1,0,4"]["hct_resid_pre_ms"]["n"], 2)
        self.assertEqual(m["hct_resid_pre_ms_all"]["n"], 4)
        self.assertAlmostEqual(m["hct_resid_pre_ms_all"]["mean"], g["guard_resid_ms_ok"]["mean"])

    def test_guard_summary_flags_inconsistent_rows(self):
        rows = self.rows()
        rows[0]["guard_resid_ms"] = 99.0
        rows[2]["why3"] = "argmin"
        rows[4]["guard_resid_ms"] = None
        g = P.guard_summary(rows)
        self.assertEqual(g["guard_resid_mismatch_ok_rows"], 1)
        self.assertEqual(g["reeval_why3_mismatch_rows"], 1)
        self.assertEqual(g["guard_resid_missing_ok_rows"], 1)
        self.assertEqual(g["guard_resid_null_rows"], 2)
        rows[4]["j3_pred_pre_ms"] = None
        self.assertEqual(P.guard_summary(rows)["guard_resid_missing_ok_rows"], 0)

    def test_v3_rows_have_no_guard_report_and_count_as_mismatches(self):
        rows = [auto3_row(i, 85.0, (1, 0, 4), guard=False) for i in range(3)]
        self.assertIsNone(P.guard_summary(rows))
        self.assertIsNone(P.monitoring_summary(rows, P.PROFILES["unlimited"]))
        fm = P.flag_mismatches("g3auto", rows)
        self.assertEqual(fm["policy_version"], 3)
        self.assertEqual(fm["guard_fields_missing"], 3)
        self.assertEqual(fm["action_fields_missing"], 0)
        ok = P.flag_mismatches("g3auto", self.rows())
        self.assertEqual(ok["policy_version"], 0)
        self.assertEqual(ok["guard_fields_missing"], 0)
        g2 = P.flag_mismatches("g2auto", [{"layout": "v2", "m_used": 1}])
        self.assertEqual((g2["policy_version"], g2["guard_fields_missing"]), (0, 0))
        rows[0]["policy_version"] = "v3"
        self.assertEqual(P.guard_summary(rows)["policy_version"], {"None": 2, "v3": 1})

    def test_guard_report_in_decisions_and_regression(self):
        g = P.guard_summary(self.rows())
        r = run1(h=[("h_c6000_r20_u0", 1.0, 0.5)])
        for c in r["conds"]:
            if c["family"] in ("S", "H"):
                c["arms"] = {"g2auto": {}, "g3auto": {"guard": g, "by_loss": {
                    "1.0": {"guard": g}, "8.0": {}}}}
        r["conds"].append(csum("R_c6000_r80_u10", "R", [con("g2-g3", -40.0, 5.0)], arms={
            "g2auto": {"mean_planned_imputed_ms": 94.0},
            "g3auto": {"mean_planned_imputed_ms": 134.0, "guard": g}}))
        for label in ("confirmatory", "development"):
            d = P.decide(r, None, {"cells": {}}, label=label)
            gv = d["guard_v31"]["run1"]
            self.assertTrue(gv["present"])
            self.assertEqual([(x["cond"], x["arm"]) for x in gv["arms"]],
                             [("S_bigcert", "g3auto"), ("S_rtt200", "g3auto"),
                              ("H_h_c6000_r20_u0", "g3auto"), ("R_c6000_r80_u10", "g3auto")])
            first = gv["arms"][0]
            self.assertEqual(first["alarm_count"], 2)
            self.assertAlmostEqual(first["reeval_share"], 0.2)
            self.assertEqual(first["alarmed_chosen_actions"], {"1,0,4": 2})
            self.assertEqual(set(first["by_loss"]), {"1.0"})
            self.assertFalse(d["guard_v31"]["run2"]["present"])
            reg = d["regression"]["conds"]
            self.assertEqual(len(reg), 1)
            self.assertAlmostEqual(reg[0]["g2_minus_g3"]["est"], -40.0)
            self.assertIn("guard", reg[0]["arms"]["g3auto"])
            self.assertNotIn("guard", reg[0]["arms"]["g2auto"])
            self.assertIn("guard_resid_missing_ok_rows", first)
            self.assertIsNone(reg[0]["stage2_reference"])
        d = P.decide(run1(), None, {"cells": {}})
        self.assertFalse(d["guard_v31"]["run1"]["present"])
        self.assertEqual(d["guard_v31"]["run1"]["note"], "no v3.1 guard fields in any row")


class DrawTests(unittest.TestCase):
    def test_draw_is_deterministic_distinct_and_in_grid(self):
        a = P.h_draw(FAKE_SRC, excluded=[])
        self.assertEqual(a, P.h_draw(FAKE_SRC, excluded=[]))
        self.assertEqual(len(a["cells"]), 4)
        self.assertEqual(len(set(a["cells"])), 4)
        grid = {c["cell"] for c in P.h_cells()}
        self.assertEqual(len(grid), 60)
        self.assertTrue(set(a["cells"]) <= grid)
        self.assertNotEqual(a["cells"], P.h_draw("cd" * 32, excluded=[])["cells"])
        with self.assertRaises(ValueError):
            P.h_draw("not-a-sha", excluded=[])

    def test_stage2_and_development_cells_are_excluded_before_hash_ranking(self):
        stage2 = {"h_c8000_r120_u5", "h_c6000_r80_u10", "h_c6000_r80_u0",
                  "h_c6000_r120_u0"}
        baseline = P.h_draw(FAKE_SRC, excluded=[])
        dev = baseline["cells"][:2]
        excluded = stage2 | set(dev)
        draw = P.h_draw(FAKE_SRC, excluded=dev)
        self.assertTrue(set(draw["cells"]).isdisjoint(excluded))
        self.assertEqual(draw["excluded_cells"], sorted(excluded))
        self.assertEqual(draw["grid_count"], 60)
        self.assertEqual(draw["eligible_count"], 60 - len(excluded))
        ranked = sorted((c["cell"] for c in P.h_cells() if c["cell"] not in excluded),
                        key=lambda cid: (P.sha256_text(P.h_seed(FAKE_SRC) + "|" + cid), cid))
        self.assertEqual(draw["cells"], ranked[:4])
        self.assertEqual(draw, P.h_draw(FAKE_SRC, excluded=list(reversed(dev))))

    def test_draw_requires_explicit_valid_development_cells_file(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(P, "ROOT", tmp):
            with self.assertRaises(ValueError):
                P.load_h_exclusions()
            with self.assertRaises(ValueError):
                P.h_draw(FAKE_SRC)
            dev = [P.h_draw(FAKE_SRC, excluded=[])["cells"][0]]
            path = write_dev_cells(tmp, dev)
            loaded = P.load_h_exclusions()
            self.assertEqual(loaded["dev_cells_path"], P.DEV_CELLS_REL)
            self.assertEqual(loaded["dev_cells_sha256"], G.sha256_file(str(path)))
            self.assertIn(dev[0], loaded["cells"])
            self.assertNotIn(dev[0], P.h_draw(FAKE_SRC)["cells"])
            for invalid in ({"schema": "padfec3.stage3_dev_cells.v1"},
                            {"schema": "padfec3.stage3_dev_cells.v1", "cells": "h_c6000_r20_u0"},
                            {"schema": "padfec3.stage3_dev_cells.v1", "cells": ["not-a-cell"]},
                            {"schema": "unknown", "cells": []}, []):
                path.write_text(json.dumps(invalid), encoding="utf-8")
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    P.h_draw(FAKE_SRC)
            write_dev_cells(tmp)
            self.assertEqual(P.h_draw(FAKE_SRC)["cells"],
                             P.h_draw(FAKE_SRC, excluded=[])["cells"])

    def test_draw_refuses_too_few_eligible_cells_and_invalid_exclusion(self):
        grid = [c["cell"] for c in P.h_cells()]
        with self.assertRaises(ValueError):
            P.h_draw(FAKE_SRC, excluded=grid)
        with self.assertRaises(ValueError):
            P.h_draw(FAKE_SRC, excluded=["h_c9999_r80_u10"])

    def test_draw_check_and_predictions_check(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "g3"))
            write_dev_cells(tmp)
            with patch.object(P, "ROOT", tmp):
                self.assertFalse(P.draw_check()["ok"])
                d = P.h_draw(FAKE_SRC)
                with open(os.path.join(tmp, P.HDRAW_REL), "w", encoding="utf-8") as f:
                    json.dump(d, f)
                chk = P.draw_check(FAKE_SRC)
                self.assertTrue(chk["ok"], chk["problems"])
                self.assertFalse(P.draw_check("cd" * 32)["ok"])
                bad = dict(d, cells=list(reversed(d["cells"])))
                with open(os.path.join(tmp, P.HDRAW_REL), "w", encoding="utf-8") as f:
                    json.dump(bad, f)
                self.assertFalse(P.draw_check(FAKE_SRC)["ok"])
                with open(os.path.join(tmp, P.HDRAW_REL), "w", encoding="utf-8") as f:
                    json.dump(d, f)
                cells = P.draw_check(FAKE_SRC)["cells"]
                self.assertFalse(P.predictions_check(cells)["ok"])
                pred = P.h_predictions(cells, G.sha256_file(os.path.join(tmp, P.HDRAW_REL)))
                with open(os.path.join(tmp, P.HPRED_REL), "w", encoding="utf-8") as f:
                    json.dump(pred, f)
                chk = P.predictions_check(cells)
                self.assertTrue(chk["ok"], chk["problems"])
                first = cells[0]["cell"]
                pred["cells"][first]["delta_hat_ms"] += 0.5
                with open(os.path.join(tmp, P.HPRED_REL), "w", encoding="utf-8") as f:
                    json.dump(pred, f)
                chk = P.predictions_check(cells)
                self.assertFalse(chk["ok"])
                self.assertTrue(any("does not reproduce" in p for p in chk["problems"]))
                pred["cells"].pop(first)
                with open(os.path.join(tmp, P.HPRED_REL), "w", encoding="utf-8") as f:
                    json.dump(pred, f)
                self.assertFalse(P.predictions_check(cells)["ok"])
        finally:
            shutil.rmtree(tmp)

    def test_predict_mode_writes_once_and_refuses_a_changed_table(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "g3"))
            write_dev_cells(tmp)
            with patch.object(P, "ROOT", tmp):
                err = io.StringIO()
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(P.main(["--predict-h"]), 2)
                with open(os.path.join(tmp, P.HDRAW_REL), "w", encoding="utf-8") as f:
                    json.dump(P.h_draw(FAKE_SRC), f)
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(P.main(["--predict-h"]), 0)
                self.assertIn("wrote %s" % P.HPRED_REL, out.getvalue())
                path = os.path.join(tmp, P.HPRED_REL)
                d = P.read_json(path)
                self.assertEqual(sorted(d["cells"]), sorted(P.h_draw(FAKE_SRC)["cells"]))
                self.assertEqual(d["draw_sha256"], G.sha256_file(os.path.join(tmp, P.HDRAW_REL)))
                self.assertEqual(d["definition"], P.H_PRED_RULE)
                before = G.sha256_file(path)
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(P.main(["--predict-h"]), 0)
                self.assertIn("already recorded and reproduces", out.getvalue())
                self.assertEqual(G.sha256_file(path), before)
                cid = sorted(d["cells"])[0]
                d["cells"][cid]["delta_hat_ms"] = -99.0
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(d, f)
                tampered = G.sha256_file(path)
                with contextlib.redirect_stderr(io.StringIO()), \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(P.main(["--predict-h"]), 2)
                self.assertEqual(G.sha256_file(path), tampered)
        finally:
            shutil.rmtree(tmp)


class DrawModeTests(unittest.TestCase):
    def test_draw_h_writes_the_draw_and_the_predictions(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "g3"))
            write_dev_cells(tmp)
            gate = os.path.join(tmp, "gate.json")
            with open(gate, "w", encoding="utf-8") as f:
                json.dump({"pass": True, "binary": {"sha256": "b" * 64, "srcsha": FAKE_SRC},
                           "reference": gate_reference(tmp)}, f)
            rep = {"g2": {"exists": True}, "g3c": {"sha256": "b" * 64, "srcsha": FAKE_SRC}}
            with patch.object(P, "ROOT", tmp), patch.object(P.sys, "platform", "linux"), \
                    patch.object(P, "binary_report", lambda: (rep, [])):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(P.main(["--draw-h", "--gate-evidence", gate]), 0)
                draw = P.read_json(os.path.join(tmp, P.HDRAW_REL))
                pred = P.read_json(os.path.join(tmp, P.HPRED_REL))
                self.assertEqual(draw["cells"], P.h_draw(FAKE_SRC)["cells"])
                self.assertEqual(sorted(pred["cells"]), sorted(draw["cells"]))
                self.assertEqual(pred["draw_sha256"],
                                 G.sha256_file(os.path.join(tmp, P.HDRAW_REL)))
                cells = P.draw_check(FAKE_SRC)["cells"]
                self.assertTrue(P.predictions_check(cells)["ok"])
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(P.main(["--draw-h", "--gate-evidence", gate]), 0)
                self.assertIn("draw already recorded and reproduces", out.getvalue())
                self.assertIn("already recorded and reproduces", out.getvalue().split("\n", 1)[1])
                self.assertEqual(draw["gate_evidence"]["path"], "gate.json")
                self.assertEqual(P.draw_gate_problems(rep), [])
                learn = Path(tmp) / "padfec3" / "learn3.py"
                learn.write_text("edited after the gate", encoding="utf-8")
                self.assertIn("padfec3/learn3.py", " ".join(P.draw_gate_problems(rep)))
                learn.write_text("padfec3/learn3.py", encoding="utf-8")
                self.assertEqual(P.draw_gate_problems(rep), [])
                os.rename(gate, gate + ".moved")
                self.assertIn("missing", " ".join(P.draw_gate_problems(rep)))
                os.rename(gate + ".moved", gate)
                draw_path = os.path.join(tmp, P.HDRAW_REL)
                before = G.sha256_file(draw_path)
                write_dev_cells(tmp, [draw["cells"][0]])
                with contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(P.main(["--draw-h", "--gate-evidence", gate]), 2)
                self.assertEqual(G.sha256_file(draw_path), before)
        finally:
            shutil.rmtree(tmp)


def direct_delta_hat(cert, rtt, up):
    from padfec import policy, quantum
    from padfec3 import decide3, layout
    k, w = 2, 1280
    s0b, cp = policy.S0_BASE_MLKEM, policy.C_PKT_POLICY_DEFAULT
    need = quantum.bin_needed(cert, None, s0b, cp)
    g2 = set()
    for c in quantum.levers(2308, cert, None, W=w, h=51, f=16, max_steps=2, m_max=3,
                            s0_base=s0b, c_pkt=cp, parity_bytes=policy.parity_datagram_bytes,
                            max_delta=1452 - w):
        if c["mode"] == "pad_repack" or c["W_eff"] > 1452:
            continue
        if c["m"] > 0 and policy.parity_datagram_bytes(c["W_eff"], 2) > 1472:
            continue
        if c["m"] <= 3:
            g2.add((c["delta_per_dgram"], c["m"]))
    s_eq = cert + 1472.0 + 6 * 41.983
    g3 = {(c["delta"], c["lead"], c["m"]) for c in decide3.candidates3(k, w, s_eq, cp)}
    out = {}
    for loss in (1.0, 8.0):
        p = loss / 100.0
        j2 = min(layout.evaluate(k, w + d, m, 1 if m >= 2 else 0, p, rtt, up, need,
                                 later="g2")["J"] for d, m in g2)
        j3 = min(layout.evaluate(k, w + d, m, lead, p, rtt, up, need, later="v3")["J"]
                 for d, lead, m in g3)
        out[loss] = (j2, j3)
    return 0.5 * (out[1.0][0] - out[1.0][1]) + 0.5 * (out[8.0][0] - out[8.0][1]), out, g2, g3


class HPredictionTests(unittest.TestCase):
    def test_toy_cell_matches_a_direct_computation(self):
        for cell in ({"cell": "toy_a", "cert": 14000, "rtt_ms": 80, "uplink_mbps": 5},
                     {"cell": "toy_b", "cert": 6000, "rtt_ms": 20, "uplink_mbps": 0},
                     {"cell": "toy_c", "cert": 12000, "rtt_ms": 120, "uplink_mbps": 1}):
            got = P.h_predict_cell(cell)
            dh, by, g2, g3 = direct_delta_hat(cell["cert"], float(cell["rtt_ms"]),
                                              float(cell["uplink_mbps"]))
            self.assertAlmostEqual(got["delta_hat_ms"], dh, places=9)
            for loss in ("1", "8"):
                self.assertAlmostEqual(got["j_g2"][loss], by[float(loss)][0], places=9)
                self.assertAlmostEqual(got["j_g3"][loss], by[float(loss)][1], places=9)
                self.assertAlmostEqual(got["by_loss"][loss]["delta_ms"],
                                       by[float(loss)][0] - by[float(loss)][1], places=9)
            self.assertEqual(got["n_actions_g2"], len(g2))
            self.assertEqual(got["n_actions_g3"], len(g3))
            self.assertEqual(sorted((d, l + t) for d, l, t in got["actions_g2"]), sorted(g2))
            for d, l, t in got["actions_g2"]:
                self.assertEqual(l, 1 if l + t >= 2 else 0)
                self.assertLessEqual(l + t, 3)
                self.assertIn((d, l, l + t), g3)
            self.assertGreaterEqual(got["delta_hat_ms"], 0.0)
            self.assertEqual(got["h3_target"], got["delta_hat_ms"] >= 2.0)
            self.assertEqual(got["inputs"]["n_need"],
                             P._padfec_modules()[2].n_need(cell["cert"], s0_base=1472.0,
                                                          c_pkt=41.983))

    def test_toy_cell_uses_pad_and_combo_levers(self):
        got = P.h_predict_cell({"cell": "toy", "cert": 12000, "rtt_ms": 80,
                                "uplink_mbps": 5})
        self.assertTrue(any(d > 0 for d, _l, _t in got["actions_g2"]))
        self.assertGreater(got["n_actions_g3"], got["n_actions_g2"])

    def test_every_grid_cell_has_a_consistent_n_need(self):
        for cell in P.h_cells():
            inp = P.h_cell_inputs(cell)
            self.assertGreaterEqual(inp["n_need"], 1)

    def test_gate_check_needs_pass_and_the_installed_g3c(self):
        tmp = tempfile.mkdtemp()
        try:
            ref = gate_reference(tmp)
            rep = {"g3c": {"sha256": "b" * 64, "srcsha": FAKE_SRC}}
            gate = {"pass": True, "binary": {"sha256": "b" * 64, "srcsha": FAKE_SRC},
                    "reference": ref}
            with patch.object(P, "ROOT", tmp):
                self.assertEqual(P.gate_check(gate, rep), [])
                self.assertTrue(P.gate_check({}, rep))
                self.assertTrue(P.gate_check([], rep))
                self.assertTrue(P.gate_check(dict(gate, **{"pass": False}), rep))
                self.assertTrue(P.gate_check(dict(gate, binary={"sha256": "c" * 64,
                                                                "srcsha": FAKE_SRC}), rep))
                self.assertTrue(P.gate_check(dict(gate, binary={"sha256": "b" * 64,
                                                                "srcsha": "cd" * 32}), rep))
                self.assertTrue(P.gate_check({k: v for k, v in gate.items()
                                              if k != "reference"}, rep))
                stale = dict(ref, sources=dict(ref["sources"],
                                               **{"padfec3/learn3.py": {"now": "0" * 64}}))
                self.assertEqual(len(P.gate_check(dict(gate, reference=stale), rep)), 1)
                (Path(tmp) / "padfec3" / "layout.py").write_text("changed", encoding="utf-8")
                self.assertIn("padfec3/layout.py", " ".join(P.gate_check(gate, rep)))
        finally:
            shutil.rmtree(tmp)

    def test_dev_manifest_lists_the_g3_replay(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "g3"))
            with open(os.path.join(tmp, "g3", "replay_g3_dev.json"), "w") as f:
                f.write("{}")
            with patch.object(P, "ROOT", tmp), patch.object(P, "DEV_DATA", ()), \
                    patch.object(P, "DEV_EXT_GLOBS", ()):
                self.assertIn("g3/replay_g3_dev.json", P.dev_data_manifest(False))
        finally:
            shutil.rmtree(tmp)

    def test_dev_manifest_lists_stage2_probe_and_external_development_data(self):
        tmp = tempfile.mkdtemp()
        ext = tempfile.mkdtemp()
        try:
            for rel in ("experiments/results/g31_probe.json",
                        "experiments/state/g31_probe_units.jsonl",
                        "experiments/state/g31_probe_console.log",
                        "experiments/state/g31_probe_status.json",
                        "g3/dev_v31_redecide.json", "g3/dev_v31_redecide.py",
                        "experiments/state/p21_run1_H_h_c6000_r80_u10_units.jsonl"):
                os.makedirs(os.path.join(tmp, os.path.dirname(rel)), exist_ok=True)
                with open(os.path.join(tmp, rel), "w") as f:
                    f.write("{}")
            for name in ("X6.md", "X7.md", "X8.md"):
                with open(os.path.join(ext, name), "w") as f:
                    f.write("x")
            pattern = ext.replace("\\", "/") + "/X[1-7].md"
            with patch.object(P, "ROOT", tmp), patch.object(P, "DEV_DATA", ()), \
                    patch.object(P, "DEV_EXT_GLOBS", (pattern,)):
                man = P.dev_data_manifest(True)
            for rel in ("experiments/results/g31_probe.json",
                        "experiments/state/g31_probe_units.jsonl",
                        "experiments/state/g31_probe_console.log",
                        "g3/dev_v31_redecide.json",
                        "experiments/state/p21_run1_H_h_c6000_r80_u10_units.jsonl"):
                self.assertIn(rel, man)
            for rel in ("experiments/state/g31_probe_status.json", "g3/dev_v31_redecide.py"):
                self.assertNotIn(rel, man)
            head = ext.replace("\\", "/")
            self.assertIn(head + "/X6.md", man)
            self.assertIn(head + "/X7.md", man)
            self.assertNotIn(head + "/X8.md", man)
            self.assertEqual(man[head + "/X7.md"]["bytes"], 1)
            self.assertEqual(len(man[head + "/X7.md"]["sha256"]), 64)
        finally:
            shutil.rmtree(tmp)
            shutil.rmtree(ext)
        for path in ("C:/dev/pq_afec_gen3/g3/RESULT_stage2.md",
                     "C:/dev/pq_afec_gen3/g3/stage2_h_draw.json"):
            self.assertIn(path, P.DEV_DATA)
        for pattern in ("C:/dev/pq_afec_gen3/experiments/state/p21_*_units.jsonl",
                        "C:/dev/codex_handoff/codex_out/X[1-7].md",
                        "C:/dev/codex_handoff/state/evo/v31/*.md"):
            self.assertIn(pattern, P.DEV_EXT_GLOBS)

    def test_seal_check_detects_changes_and_new_files(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "g3"))
            os.makedirs(os.path.join(tmp, "experiments", "quicbed"))
            f1 = os.path.join(tmp, "experiments", "quicbed", "qamp.go")
            with open(f1, "w") as f:
                f.write("a")
            seal = {"sha256": {"experiments/quicbed/qamp.go": G.sha256_file(f1)}}
            with open(os.path.join(tmp, P.SEAL_REL), "w") as f:
                json.dump(seal, f)
            with patch.object(P, "ROOT", tmp), patch.object(P, "SEALED_FIXED", ()):
                self.assertTrue(P.seal_check()["ok"])
                with open(os.path.join(tmp, "experiments", "quicbed", "policy3.go"), "w") as f:
                    f.write("b")
                chk = P.seal_check()
                self.assertFalse(chk["ok"])
                self.assertEqual(chk["unsealed_new"], ["experiments/quicbed/policy3.go"])
                os.remove(os.path.join(tmp, "experiments", "quicbed", "policy3.go"))
                with open(f1, "w") as f:
                    f.write("changed")
                self.assertEqual(P.seal_check()["changed"], ["experiments/quicbed/qamp.go"])
        finally:
            shutil.rmtree(tmp)


class FakeBed:
    def __init__(self, work, fail_at=None):
        self.work = work
        self.calls = 0
        self.fail_at = fail_at
        self.counters = {"A": 0, "B": 0, "C": 0}
        self.started = []

    def start_servers(self, cond):
        out = {}
        for slot in sorted(cond["servers"]):
            out[slot] = {"slot": slot, "tag": cond["servers"][slot], "pid": 1000 + ord(slot),
                         "proc": None, "stats_path": slot, "argv": [],
                         "certsize": cond["profile"]["cert"], "cert_der": None}
        self.started.append((cond["cond"], sorted(out)))
        return out

    def read_stats(self, path):
        return {"bytes_in": 100 + self.counters[path], "bytes_to_stack": 90 + self.counters[path],
                "recover_crc_fail": 0, "parities": self.counters[path]}

    def run_client(self, arm, n, prof, cache_path):
        self.calls += 1
        if self.fail_at is not None and self.calls == self.fail_at:
            raise KeyboardInterrupt
        a = P.ARMS[arm]
        self.counters[a["slot"]] += n
        if P.is_auto(arm):
            try:
                with open(cache_path, encoding="utf-8") as f:
                    seen = json.load(f)["seen"]
            except OSError:
                seen = 0
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump({"seen": seen + n}, f)
        base = {"g2auto": 60.0, "g2m3": 62.0, "g2m3B": 62.0, "g3auto": 55.0, "g3fixL3": 57.0,
                "g3fixL2": 57.0}[arm]
        rows = []
        for i in range(n):
            r = {"i": i, "ok": True, "ms": base + (i % 3), "m_used": a["m"] if a["kind"] == "fixed"
                 else 3, "ips_used": 1280,
                 "first_flight_bytes": 2560, "first_flight_parity_dgrams": 3,
                 "first_flight_parity_bytes": 3 * 1331}
            if a["bin"] == "g3c":
                r.update(layout="v3", lead=a.get("lead", 1), first_flight_lead_dgrams=1)
                if a["kind"] == "auto3":
                    r.update(action=[0, 1, 2], ej=60.0, p_mean=0.05)
                    r.update(v31_row(r["ms"], 60.0, alarm=i == 1, reeval=i == 2,
                                     alarmed=1 if i >= 1 else 0))
            rows.append(r)
        return rows, {"bytes_orig": 2560 * n, "bytes_parity": 3 * 1331 * n,
                      "parity_sent": 3 * n}, "", ["fake", arm], 0


class LiveFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state = os.path.join(self.tmp, "state")
        self.results = os.path.join(self.tmp, "results")
        self.work = os.path.join(self.tmp, "work")
        for d in (self.state, self.results, self.work):
            os.makedirs(d)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_exec(self, bed, run, plan, meta):
        P_ = P.paths(run)
        meta["starts"].append({"seal_check": {"ok": False}, "bins_sha256": {"g2": None,
                                                                          "g3c": None},
                               "source_hashes": {"x": "y"}})
        with contextlib.ExitStack() as st:
            st.enter_context(patch.object(P, "start_servers", bed.start_servers))
            st.enter_context(patch.object(P, "stop_servers", lambda s: None))
            st.enter_context(patch.object(P, "server_alive", lambda s: True))
            st.enter_context(patch.object(P, "run_client", bed.run_client))
            st.enter_context(patch.object(P, "set_netem", lambda prof, loss: {"loss": loss}))
            st.enter_context(patch.object(P.G, "read_stats", bed.read_stats))
            st.enter_context(patch.object(P.G, "busy_processes", lambda allowed=(): []))
            st.enter_context(patch.object(P.G, "load_processes", lambda: []))
            st.enter_context(patch.object(P.time, "sleep", lambda s: None))
            st.enter_context(contextlib.redirect_stdout(io.StringIO()))
            return P.execute(run, plan, meta, P_, {"g2": None, "g3c": None}, None)

    def patches(self):
        return [patch.object(P, "STATE", self.state), patch.object(P, "RESULTS", self.results),
                patch.object(P, "WORK", self.work)]

    def test_smoke_flow_journals_caches_and_report(self):
        with contextlib.ExitStack() as st:
            for p in self.patches():
                st.enter_context(p)
            plan = P.build_plan("smoke")
            fps = {c["cond"]: P.cond_fingerprint("smoke", c, {"g2": None, "g3c": None}, None)
                   for c in plan["conds"]}
            meta = {"run": "smoke", "plan": plan, "fps": fps, "starts": []}
            bed = FakeBed(self.work)
            self.assertEqual(self.run_exec(bed, "smoke", plan, meta), 0)
            for c in plan["conds"]:
                self.assertTrue(os.path.isfile(P.journal_path("smoke", c["cond"])))
            s = cond_by(plan, "S_bigcert")
            with open(P.cache_path("smoke", s["cond"], "g3auto"), encoding="utf-8") as f:
                self.assertEqual(json.load(f)["seen"], s["n_per_arm"])
            with open(P.cache_path("smoke", "C_bigcert_l2", "g2auto"), encoding="utf-8") as f:
                self.assertEqual(json.load(f)["seen"], 8)
            meta["finished"] = {"source_hashes": {"x": "y"}}
            with contextlib.redirect_stdout(io.StringIO()):
                rep = P.finalize("smoke", plan, meta)
            self.assertTrue(os.path.isfile(P.paths("smoke")["result"]))
            self.assertTrue(all(c["complete"] for c in rep["conds"]))
            sb = next(c for c in rep["conds"] if c["cond"] == "S_bigcert")
            self.assertAlmostEqual(sb["arms"]["g2auto"]["mean_planned_imputed_ms"], 61.0)
            self.assertAlmostEqual(sb["arms"]["g3auto"]["mean_planned_imputed_ms"], 56.0)
            g = P.get_contrast(sb, "g2-g3")
            self.assertAlmostEqual(g["overall_diff_ms"], 5.0)
            self.assertIsNone(g["est"])
            p11 = next(c for c in rep["conds"] if c["cond"] == "D_p11_9000_l2")
            self.assertAlmostEqual(P.get_contrast(p11, "g2-g3")["est"], 5.0)
            integ = rep["integrity"]
            self.assertEqual(integ["crc_fail_total"], 0)
            self.assertEqual(integ["cross_traffic_segments"], 0)
            self.assertEqual(integ["flag_mismatches"], {})
            gr = integ["g3_rows_with_action_j3_pmean"]
            self.assertEqual(gr["rows"], gr["action"])
            v31 = integ["g3_rows_v31"]
            self.assertEqual(v31["rows"], gr["rows"])
            self.assertEqual(v31["policy_version_ok"], v31["rows"])
            self.assertEqual(v31["all_guard_fields"], v31["rows"])
            n_auto3_segments = sum(1 for b in plan["schedule"] for a in b["order"]
                                   if a == "g3auto")
            self.assertEqual(v31["alarm_rows"], n_auto3_segments)
            self.assertEqual(v31["reeval_rows"], n_auto3_segments)
            self.assertEqual(v31["guard_resid_mismatch_ok_rows"], 0)
            self.assertEqual(v31["guard_resid_missing_ok_rows"], 0)
            self.assertEqual(v31["reeval_why3_mismatch_rows"], 0)
            g3g = sb["arms"]["g3auto"]["guard"]
            self.assertEqual(g3g["alarmed_chosen_actions"], {"0,1,2": 2})
            self.assertEqual(g3g["first_alarm_row"], 1)
            self.assertIn("guard", sb["arms"]["g3auto"]["by_loss"]["2.0"])
            self.assertNotIn("guard", sb["arms"]["g2auto"])
            reg = rep["decisions_smoke"]["regression"]["conds"]
            self.assertEqual([c["cond"] for c in reg], [P.REGRESSION_COND])
            self.assertIn("guard", reg[0]["arms"]["g3auto"])
            ref = reg[0]["stage2_reference"]
            self.assertEqual(ref["mean_planned_imputed_ms"], {"g2auto": 94.28, "g3auto": 140.14})
            self.assertEqual(sum(ref["g3auto_action_hist"].values()), P.H_SEGMENT * 2 * P.H_CYCLES)
            gv = rep["decisions_smoke"]["guard_v31"]["run1"]
            self.assertTrue(gv["present"])
            self.assertEqual({(x["cond"], x["arm"]) for x in gv["arms"]},
                             {(c["cond"], "g3auto") for c in plan["conds"]
                              if "g3auto" in c["arms"]})
            self.assertNotIn(P.REGRESSION_COND, [t["cond"] for t in
                                                 rep["decisions_smoke"]["H2"]["run1"]["tests"]])
            self.assertEqual(integ["journal"]["reused_units"], 0)
            self.assertTrue(integ["sources_unchanged"])
            self.assertEqual(rep["label"].split()[0], "smoke")
            self.assertIn("decisions_smoke", rep)
            self.assertIn(("S_bigcert", ["A", "B", "C"]), bed.started)
            self.assertIn(("AA_bigcert", ["A", "B"]), bed.started)
            fx = sb["arms"]["g3fixL3"]
            self.assertEqual((fx["port"], fx["server_binary"]), (44435, "g3c"))
            self.assertEqual((sb["arms"]["g3auto"]["port"], sb["arms"]["g3auto"]["server_binary"]),
                             (44434, "g3c"))
            self.assertEqual(sb["arms"]["g3fixL3"]["server_counters"]["parities"],
                             sb["arms"]["g3fixL3"]["n_returned"])
            aa = next(c for c in rep["conds"] if c["cond"] == "AA_bigcert")
            self.assertEqual(set(aa["arms"]), {"g2m3", "g2m3B"})
            self.assertEqual(aa["arms"]["g2m3B"]["server_binary"], "g2")
            self.assertEqual(aa["arms"]["g2m3"]["flags"], ["-fec", "fec", "-m", "3"])
            seq = next(c for c in rep["conds"] if c["cond"] == "SEQ_mbps2_l15")
            self.assertEqual(seq["arms"]["g2m3B"]["server_binary"], "g3c")
            self.assertAlmostEqual(P.get_contrast(seq, "A-B")["est"], 0.0)

    def test_resume_restores_caches_from_journal(self):
        with contextlib.ExitStack() as st:
            for p in self.patches():
                st.enter_context(p)
            plan = P.build_plan("smoke")
            plan["conds"] = [cond_by(plan, "S_bigcert")]
            plan["schedule"] = blocks_of(plan, "S_bigcert")
            fps = {"S_bigcert": "fp"}
            meta = {"run": "smoke", "plan": plan, "fps": fps, "starts": []}
            bed = FakeBed(self.work, fail_at=5)
            with self.assertRaises(KeyboardInterrupt):
                self.run_exec(bed, "smoke", plan, meta)
            shutil.rmtree(os.path.join(self.work, "cache"))
            bed2 = FakeBed(self.work)
            self.assertEqual(self.run_exec(bed2, "smoke", plan, meta), 0)
            for a in ("g2auto", "g3auto"):
                with open(P.cache_path("smoke", "S_bigcert", a), encoding="utf-8") as f:
                    self.assertEqual(json.load(f)["seen"], 2 * P.SMOKE_N)
            inc = P.read_jsonl(P.paths("smoke")["incidents"])
            self.assertTrue(any(i.get("resumed_at_block") == 1 for i in inc))
            self.assertEqual(bed2.calls, 3)

    def test_meta_on_disk_names_journal_ids_before_a_hard_kill(self):
        with contextlib.ExitStack() as st:
            for p in self.patches():
                st.enter_context(p)
            plan = P.build_plan("smoke")
            plan["conds"] = [cond_by(plan, "S_bigcert")]
            plan["schedule"] = blocks_of(plan, "S_bigcert")
            meta = {"run": "smoke", "plan": plan, "fps": {"S_bigcert": "fp"}, "starts": []}
            with self.assertRaises(KeyboardInterrupt):
                self.run_exec(FakeBed(self.work, fail_at=5), "smoke", plan, meta)
            disk = P.read_json(P.paths("smoke")["meta"])
            self.assertIsNotNone(disk)
            self.assertIn("S_bigcert", disk["starts"][-1]["journal_run_ids"])
            self.assertEqual(self.run_exec(FakeBed(self.work), "smoke", plan, disk), 0)
            prov = P.journal_provenance("smoke", plan, disk)
            self.assertEqual(prov["used_units"], 2)
            self.assertEqual(prov["reused_units"], 0)

    def test_source_change_during_a_run_demotes_it(self):
        with contextlib.ExitStack() as st:
            for p in self.patches():
                st.enter_context(p)
            plan = P.build_plan("smoke")
            plan["conds"] = [cond_by(plan, "D_p11_9000_l2")]
            plan["schedule"] = blocks_of(plan, "D_p11_9000_l2")
            meta = {"run": "run2", "plan": plan, "fps": {"D_p11_9000_l2": "fp"}, "starts": []}
            self.run_exec(FakeBed(self.work), "run2", plan, meta)
            meta["starts"][0]["seal_check"] = {"ok": True, "sha256": "s"}
            meta["finished"] = {"source_hashes": {"x": "y"},
                                "bins_sha256": {"g2": None, "g3c": None}}
            with contextlib.redirect_stdout(io.StringIO()), \
                    patch.object(P, "final_validation", return_value={"ok": True}):
                rep = P.finalize("run2", plan, meta)
            self.assertTrue(rep["confirmatory"])
            meta["finished"] = {"source_hashes": {"x": "z"},
                                "bins_sha256": {"g2": None, "g3c": None}}
            with contextlib.redirect_stdout(io.StringIO()), \
                    patch.object(P, "final_validation", return_value={"ok": True}):
                rep = P.finalize("run2", plan, meta)
            self.assertFalse(rep["confirmatory"])
            self.assertIn("sources_unchanged", rep["label"])

    def test_server_death_retries_block_with_restored_cache(self):
        with contextlib.ExitStack() as st:
            for p in self.patches():
                st.enter_context(p)
            plan = P.build_plan("smoke")
            plan["conds"] = [cond_by(plan, "D_p11_9000_l2")]
            plan["schedule"] = blocks_of(plan, "D_p11_9000_l2")
            meta = {"run": "smoke", "plan": plan, "fps": {"D_p11_9000_l2": "fp"}, "starts": []}
            bed = FakeBed(self.work)
            state = {"n": 0}

            def alive(_s):
                state["n"] += 1
                return state["n"] not in (1, 2)

            with patch.object(P, "server_alive", alive):
                P_ = P.paths("smoke")
                meta["starts"].append({})
                with contextlib.ExitStack() as st2:
                    st2.enter_context(patch.object(P, "start_servers", bed.start_servers))
                    st2.enter_context(patch.object(P, "stop_servers", lambda s: None))
                    st2.enter_context(patch.object(P, "run_client", bed.run_client))
                    st2.enter_context(patch.object(P, "set_netem", lambda prof, loss: {}))
                    st2.enter_context(patch.object(P.G, "read_stats", bed.read_stats))
                    st2.enter_context(patch.object(P.G, "busy_processes",
                                                   lambda allowed=(): []))
                    st2.enter_context(patch.object(P.G, "load_processes", lambda: []))
                    st2.enter_context(patch.object(P.time, "sleep", lambda s: None))
                    st2.enter_context(contextlib.redirect_stdout(io.StringIO()))
                    P.execute("smoke", plan, meta, P_, {"g2": None, "g3c": None}, None)
            inc = P.read_jsonl(P.paths("smoke")["incidents"])
            self.assertTrue(any(i.get("attempt") == 1 and "server died" in (i.get("err") or "")
                                for i in inc))
            for a in ("g2auto", "g3auto"):
                with open(P.cache_path("smoke", "D_p11_9000_l2", a), encoding="utf-8") as f:
                    self.assertEqual(json.load(f)["seen"], 2 * P.SMOKE_N)

    def test_block_complete_rejects_bad_records(self):
        blk = {"order": ["g2auto", "g3auto"], "sizes": {"g2auto": 2, "g3auto": 2}}
        seg = lambda a, rows, **kw: dict({"arm": a, "n_planned": 2, "rows": rows,
                                          "server_after": {"bytes_in": 1}}, **kw)
        good_rows = [{"ok": True, "ms": 1.0}, {"ok": False, "ms": 2.0}]
        rec = {"segments": [seg("g2auto", good_rows), seg("g3auto", good_rows)],
               "cache_after": {"g2auto": {}, "g3auto": {}}}
        self.assertTrue(P.block_complete(rec, blk))
        self.assertFalse(P.block_complete(dict(rec, cache_after={"g2auto": {}}), blk))
        short = dict(rec, segments=[seg("g2auto", good_rows[:1]), seg("g3auto", good_rows)])
        self.assertFalse(P.block_complete(short, blk))
        short["segments"][0]["client_err"] = "exit 2"
        self.assertTrue(P.block_complete(short, blk))
        self.assertFalse(P.block_complete(dict(rec, err="server died"), blk))
        nan = dict(rec, segments=[seg("g2auto", [{"ok": True, "ms": float("nan")}] * 2),
                                  seg("g3auto", good_rows)])
        self.assertFalse(P.block_complete(nan, blk))

    def test_build_before_a_block_aborts_and_records_an_incident(self):
        with contextlib.ExitStack() as st:
            for p in self.patches():
                st.enter_context(p)
            plan = P.build_plan("smoke")
            cond = cond_by(plan, "S_bigcert")
            plan["conds"] = [cond]
            plan["schedule"] = blocks_of(plan, cond["cond"])
            bed = FakeBed(self.work)
            st.enter_context(patch.object(P, "start_servers", bed.start_servers))
            stopped = st.enter_context(patch.object(P, "stop_servers"))
            st.enter_context(patch.object(P.G, "busy_processes", return_value=[]))
            st.enter_context(patch.object(P.G, "load_processes",
                                          return_value=["1234 go build ./..."]))
            st.enter_context(patch.object(P.G, "sha256_or_none", return_value=None))
            run_block = st.enter_context(patch.object(P, "run_block"))
            with self.assertRaisesRegex(P.Abort, "go build"):
                P.run_condition("smoke", cond, plan, "fp", P.paths("smoke"),
                                {"g2": None, "g3c": None}, {})
            run_block.assert_not_called()
            stopped.assert_called_once()
            incidents = P.read_jsonl(P.paths("smoke")["incidents"])
            self.assertEqual(len(incidents), 1)
            self.assertEqual(incidents[0]["attempt"], 1)
            self.assertEqual(incidents[0]["abort"], ["1234 go build ./..."])


class FinalValidationTests(unittest.TestCase):
    def test_finalize_and_report_only_recheck_full_seal_and_binaries(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as st:
            root = Path(tmp)
            (root / "g3").mkdir()
            sealed_paths = (P.PROTOCOL_REL, P.HDRAW_REL, P.HPRED_REL)
            initial_files = {
                P.PROTOCOL_REL: b"sealed protocol\n",
                P.HDRAW_REL: b'{"cells": ["h_test"]}\n',
                P.HPRED_REL: b'{"cells": {"h_test": {"delta_hat_ms": 8.0}}}\n',
                "g2": b"frozen-g2", "g3c": b"sealed-g3c"}
            for rel, content in initial_files.items():
                (root / rel).write_bytes(content)
            bins = {tag: str(root / tag) for tag in ("g2", "g3c")}
            bins_sha = {tag: G.sha256_file(path) for tag, path in bins.items()}
            seal = {"sha256": {rel: G.sha256_file(str(root / rel)) for rel in sealed_paths},
                    "binaries": dict(bins_sha, g3c_srcsha=FAKE_SRC)}
            initial_files[P.SEAL_REL] = json.dumps(seal).encode("utf-8")
            (root / P.SEAL_REL).write_bytes(initial_files[P.SEAL_REL])
            st.enter_context(patch.object(P, "ROOT", tmp))
            st.enter_context(patch.object(P, "STATE", tmp))
            st.enter_context(patch.object(P, "RESULTS", tmp))
            st.enter_context(patch.object(P, "BINS", bins))
            st.enter_context(patch.object(P, "SEALED_FIXED", sealed_paths))
            st.enter_context(patch.object(P, "SEALED_GLOBS", ()))
            st.enter_context(patch.object(P.B, "harden"))
            st.enter_context(patch.object(P, "write_decisions"))
            st.enter_context(patch.object(P, "print_summary"))
            st.enter_context(contextlib.redirect_stdout(io.StringIO()))

            def binary_report():
                return {tag: {"sha256": G.sha256_or_none(path), "srcsha": FAKE_SRC}
                        for tag, path in bins.items()}, []

            binary = st.enter_context(patch.object(P, "binary_report", side_effect=binary_report))
            plan = {"conds": [], "schedule": []}
            meta = {"run": "run2", "plan": plan, "fps": {},
                    "starts": [{"seal_check": P.seal_check(), "bins_sha256": bins_sha,
                                "source_hashes": {"source": "same"}}],
                    "finished": {"bins_sha256": bins_sha, "source_hashes": {"source": "same"}}}
            seal_sha = meta["starts"][0]["seal_check"]["sha256"]
            predictions, check = P.sealed_predictions(seal_sha)
            self.assertTrue(check["ok"])
            self.assertEqual(predictions["cells"]["h_test"]["delta_hat_ms"], 8.0)

            def report(mode, current_meta):
                if mode == "finalize":
                    return P.finalize("run2", plan, current_meta)
                P.atomic_write_json(P.paths("run2")["meta"], current_meta)
                self.assertEqual(P.report_only("run2"), 0)
                return P.read_json(P.paths("run2")["result"])

            changes = (
                (P.PROTOCOL_REL, b"changed protocol\n"),
                (P.HDRAW_REL, b'{"cells": ["other"]}\n'),
                (P.HPRED_REL, b'{"cells": {"h_test": {"delta_hat_ms": 40.0}}}\n'),
                (P.SEAL_REL, initial_files[P.SEAL_REL] + b"\n"),
                (P.SEAL_REL, b"not JSON"),
                (P.SEAL_REL, b"[]"),
                (P.HPRED_REL, None),
                ("g3c", b"replacement binary"),
            )
            for mode in ("finalize", "report-only"):
                self.assertTrue(report(mode, meta)["confirmatory"])
                for rel, replacement in changes:
                    with self.subTest(mode=mode, rel=rel, replacement=replacement):
                        if replacement is None:
                            (root / rel).unlink()
                        else:
                            (root / rel).write_bytes(replacement)
                        result = report(mode, meta)
                        self.assertFalse(result["confirmatory"])
                        self.assertTrue(result["label"].startswith("development"))
                        self.assertFalse(result["integrity"]["final_validation"]["ok"])
                        if rel in (P.HPRED_REL, P.SEAL_REL):
                            predictions, check = P.sealed_predictions(seal_sha)
                            self.assertIsNone(predictions)
                            self.assertFalse(check["ok"])
                        (root / rel).write_bytes(initial_files[rel])
                altered = P.canon(meta)
                altered["finished"]["bins_sha256"]["g3c"] = "changed-at-finish"
                result = report(mode, altered)
                self.assertFalse(result["confirmatory"])
                self.assertFalse(result["integrity"]["binaries_constant"])
                changed_start = P.canon(meta)
                changed_start["starts"].append(P.canon(meta["starts"][0]))
                changed_start["starts"][-1]["seal_check"]["sha256"] = "other-seal"
                self.assertFalse(report(mode, changed_start)["confirmatory"])
                with patch.object(P, "binary_report",
                                  return_value=(binary_report()[0], ["source mismatch"])):
                    self.assertFalse(report(mode, meta)["confirmatory"])
            self.assertGreater(binary.call_count, 0)


class DecisionFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write(self, run, obj):
        with open(os.path.join(self.tmp, "p31_gencompare_%s.json" % run), "w",
                  encoding="utf-8") as f:
            json.dump(obj, f)

    def test_write_decisions_combines_runs_with_the_same_seal(self):
        with patch.object(P, "RESULTS", self.tmp), patch.object(P, "ROOT", self.tmp), \
                patch.object(P, "final_validation", return_value={"ok": True}) as validation, \
                patch.object(P, "sealed_predictions", return_value=({"cells": {}},
                                                                     {"ok": True})):
            self.assertIsNone(P.write_decisions())
            r1 = dict(run1(), confirmatory=True, seal_sha256="s1")
            self.write("run1", r1)
            d = P.write_decisions()
            self.assertEqual(d["label"], "confirmatory")
            self.assertEqual(d["H1"]["claim"], "pending run 2")
            self.assertTrue(os.path.isfile(P.paths("run1")["decisions"]))
            r2 = {"confirmatory": True, "seal_sha256": "s2",
                  "conds": [csum("S_bigcert", "S", [con("g2-g3", 25.0, 2.0)]),
                            csum("S_rtt200", "S", [con("g2-g3", 3.0, 1.0)])]}
            self.write("run2", r2)
            d = P.write_decisions()
            self.assertIsNone(d["runs_used"]["run2"])
            self.assertIsNotNone(d["run2_excluded_reason"])
            self.assertEqual(d["H1"]["claim"], "pending run 2")
            r2["seal_sha256"] = "s1"
            self.write("run2", r2)
            d = P.write_decisions()
            self.assertTrue(d["H1"]["claim"].startswith("improvement claimed"))
            validation.side_effect = [{"ok": False}, {"ok": True}]
            d = P.write_decisions()
            self.assertIsNone(d["runs_used"]["run2"])
            self.assertEqual(d["H1"]["claim"], "pending run 2")
            validation.side_effect = [{"ok": True}, {"ok": False}]
            d = P.write_decisions()
            self.assertEqual(d["label"], "development")
            self.assertEqual(d["H1"]["claim"], "평가 불가")
            validation.side_effect = None
            r1["confirmatory"] = False
            self.write("run1", r1)
            self.assertEqual(P.write_decisions()["label"], "development")

    def test_report_only_needs_meta(self):
        with patch.object(P, "STATE", self.tmp), patch.object(P, "RESULTS", self.tmp):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(P.report_only("run1"), 2)


class ProtocolDocTests(unittest.TestCase):
    def text(self):
        return (ROOT / P.PROTOCOL_REL).read_text(encoding="utf-8")

    def test_todo_marks_sit_only_in_the_two_section_15_slots(self):
        t = self.text()
        lines = [ln for ln in t.splitlines() if P.TODO_MARK in ln]
        if not lines:
            draw = json.loads((ROOT / P.HDRAW_REL).read_text(encoding="utf-8"))
            sec = t[t.index("## 15."):t.index("## 16.")]
            for rank, cell in enumerate(draw["cells"], 1):
                self.assertIn("| %d | %s |" % (rank, cell), sec)
            self.assertIn(hashlib.sha256((ROOT / P.HDRAW_REL).read_bytes()).hexdigest(), sec)
            self.assertIn(hashlib.sha256((ROOT / P.HPRED_REL).read_bytes()).hexdigest(), sec)
            return
        self.assertEqual([ln.split(")")[0] + ")" for ln in lines],
                         ["TODO(stage3-draw)", "TODO(stage3-predictions)"])
        self.assertTrue(all(ln.startswith(P.TODO_MARK) for ln in lines))

    def test_seal_refuses_while_slots_are_open(self):
        if (ROOT / P.SEAL_REL).exists():
            self.skipTest("a stage-3 seal exists")
        if P.TODO_MARK not in self.text():
            self.skipTest("section 15 slots are filled")
        err = io.StringIO()
        with patch.object(P.sys, "platform", "linux"), contextlib.redirect_stderr(err), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(P.seal_mode(), 2)
        self.assertIn("still has %s slots" % P.TODO_MARK, err.getvalue())
        self.assertFalse((ROOT / P.SEAL_REL).exists())

    def test_protocol_numbers_match_the_runner(self):
        t = self.text()
        plan = P.build_plan("run1")
        conns = sum(sum(b["sizes"].values()) for b in plan["schedule"])
        self.assertIn("1회차는 %d조건, %d블록, %s연결" % (len(plan["conds"]), len(plan["schedule"]),
                                                   format(conns, ",")), t)
        sm = P.build_plan("smoke")
        self.assertIn("%d조건, %d블록, %d연결" % (len(sm["conds"]), len(sm["schedule"]),
                                              sum(sum(b["sizes"].values())
                                                  for b in sm["schedule"])), t)
        for s in (P.COMPARISON["g3_bin"], P.BUILD_SCRIPT, P.SEAL_REL, P.HDRAW_REL,
                  P.HPRED_REL, P.DEV_CELLS_REL, P.REGRESSION_COND, P.WORK,
                  "PREFLIGHT_ACK_BYTES = 41", "q_i = min(1, 2·p_i)",
                  "대상 0개, H3 검증 증거 없음",
                  "후보는 %d셀" % (len(P.h_cells()) - len(P.load_h_exclusions()["cells"]))):
            self.assertIn(s, t)
        for cell in P.STAGE2_H_CELLS:
            self.assertIn(cell, t)
        for ch in ("—", "–"):
            self.assertNotIn(ch, t)


class CliTests(unittest.TestCase):
    def test_dry_run_returns_zero_and_writes_nothing(self):
        before = set(os.listdir(P.STATE)) | set(os.listdir(P.RESULTS))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(P.main(["--dry-run"]), 0)
        out = buf.getvalue()
        self.assertIn("mirror check against the gen-2 stage scripts: ok", out)
        self.assertIn("schedule run1: 23 conditions", out)
        self.assertIn("schedule smoke: 10 conditions", out)
        self.assertIn("total run2:", out)
        self.assertIn("excluded before ranking", out)
        for cell in P.STAGE2_H_CELLS:
            self.assertIn(cell, out)
        self.assertIn("regression condition R_c6000_r80_u10", out)
        self.assertIn("policy_version=v3.1", out)
        self.assertIn("build_g3c.sh", out)
        buf = io.StringIO()
        with patch.object(P, "DEV_CELLS_REL", "g3/no_such_dev_cells.json"), \
                contextlib.redirect_stdout(buf):
            self.assertEqual(P.main(["--dry-run"]), 0)
        self.assertIn("held-out draw would refuse", buf.getvalue())
        self.assertEqual(before, set(os.listdir(P.STATE)) | set(os.listdir(P.RESULTS)))

    def test_live_and_seal_modes_refuse_off_linux(self):
        if sys.platform.startswith("linux"):
            self.skipTest("refusal path is for non-Linux hosts")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(P.main(["--run1"]), 2)
            self.assertEqual(P.main(["--seal"]), 2)
            self.assertEqual(P.main(["--draw-h", "--gate-evidence", "x"]), 2)
        self.assertIn("REFUSED", err.getvalue())


if __name__ == "__main__":
    unittest.main()
