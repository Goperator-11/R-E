import pytest
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import g3_m1confirm as M
import g3_stage0 as S
import g3bed as G
import padbed as B
from _journal import Journal

CUT_M4 = S.nominal_threshold(3, S.CONDS["bigcert"])
NS_GAP = 200 * 1000 * 1000


def fake_row(i, arm, ms, ok=True):
    a = S.ARMS[arm]
    row = {"i": i, "ms": ms, "ok": ok, "group": S.GROUP,
           "first_flight_datagrams": 2, "first_flight_bytes": 2 * S.NOMINAL_W,
           "first_flight_parity_dgrams": a["m"],
           "first_flight_parity_bytes": a["m"] * S.NOMINAL_PARITY,
           "m_used": a["m"], "server_bytes": 18000, "parity_sent": a["m"]}
    if not ok:
        row["err"] = "timeout: no recent network activity"
    if a["bin"] == "g3":
        row.update(layout="v3", lead=a["lead"], first_flight_lead_dgrams=a["lead"])
    return row


def fake_conn(k, credit, t0=10 ** 18):
    return {"tx_dgrams": 16, "beff_credit": credit, "beff_stack": 5267, "beff_phys": 5267,
            "first_rx_ns": t0 + k * NS_GAP, "first_tx_ns": t0 + k * NS_GAP + 16 * 10 ** 6,
            "stack_bytes": 10541, "rx_bytes": 10541, "credit_n": credit}


def fake_segment(arm, n, pos, block, credits=None, ms=None, ok=None, v3_delta=0,
                 drop_v3=False, conns_n=None):
    a = S.ARMS[arm]
    credits = credits if credits is not None else [a["lead"]] * n
    ms = ms if ms is not None else [122.0 if a["bin"] == "g2" else 80.0] * n
    ok = ok if ok is not None else [True] * n
    rows = [fake_row(i, arm, ms[i], ok[i]) for i in range(n)]
    t0 = 10 ** 18 + block * 10 ** 12
    conns = [fake_conn(k, credits[k], t0) for k in range(n if conns_n is None else conns_n)]
    conns = conns[1::2] + conns[0::2]
    credit = sum(c for c in credits if type(c) is int) if a["bin"] == "g3" else 0
    delta = {"parities": n * a["m"], "credit_parities": credit, "recover_crc_fail": 0,
             "bytes_in": 100 * n, "bytes_to_stack": 90 * n, "conn_acct_dropped": 0,
             "conn_acct_alias_conflicts": 0}
    if a["bin"] == "g3" and not drop_v3:
        delta["credit_parities_v3"] = credit + v3_delta
    return {"arm": arm, "pos": pos, "bin": a["bin"], "port": G.PORTS[a["bin"]],
            "argv": [], "rc": 0, "err": "", "client_err": "", "n_planned": n, "n_rows": n,
            "rows": rows,
            "client_stats": {"parity_sent": n * a["m"], "bytes_orig": n * 2 * S.NOMINAL_W,
                             "bytes_parity": n * a["m"] * S.NOMINAL_PARITY},
            "server_delta": delta, "server_after": {"bytes_in": 10, "bytes_to_stack": 9},
            "server_new_conns": conns, "other_server_delta": {}}


def fake_block(blk, per_arm=None):
    per_arm = per_arm or {}
    segs = [fake_segment(arm, blk["sizes"][arm], pos, blk["block"],
                         **per_arm.get((blk["block"], arm), per_arm.get(arm, {})))
            for pos, arm in enumerate(blk["order"])]
    return {"cell": blk["cell"], "block": blk["block"], "rotation": blk["rotation"],
            "order": blk["order"], "sizes": blk["sizes"], "attempt": 1,
            "netem": {"expected_tokens": {"c2s_loss": True}},
            "servers": {"g2": {"cert_der": 16000}, "g3": {"cert_der": 16000}},
            "segments": segs, "load_processes": [],
            "bins_sha256": {"g2": G.G2_FROZEN_SHA256, "g3": M.G3_STAGE0_SHA256},
            "runner_sha256": "r", "err": "", "client_errors": []}


def load_seal_script():
    spec = importlib.util.spec_from_file_location("seal_m1confirm",
                                                  ROOT / "g3" / "seal_m1confirm.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TempPaths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "results"))
        os.makedirs(os.path.join(self.tmp, "state"))
        self.P = {"journal": os.path.join(self.tmp, "state", "j.jsonl"),
                  "meta": os.path.join(self.tmp, "state", "m.json"),
                  "status": os.path.join(self.tmp, "state", "s.json"),
                  "incidents": os.path.join(self.tmp, "state", "i.jsonl"),
                  "result": os.path.join(self.tmp, "results", "r.json")}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class PlanTests(unittest.TestCase):
    def test_plan_is_one_bigcert_2_cell_with_two_arms(self):
        plan = M.build_plan()
        self.assertEqual(plan["mode"], "m1confirm")
        self.assertEqual(len(plan["cells"]), 1)
        cell = plan["cells"][0]
        self.assertEqual(cell["arms"], [["v2m1", 400], ["m4L3", 400]])
        self.assertEqual((cell["cell"], cell["pred_id"], cell["cond"], cell["loss_pct"]),
                         ("bigcert_2", "bigcert_loss2", "bigcert", 2.0))
        stage0 = next(c for c in S.build_plan("full")["cells"] if c["cell"] == "bigcert_2")
        self.assertEqual((stage0["cond"], stage0["loss_pct"], stage0["blocks"]),
                         (cell["cond"], cell["loss_pct"], cell["blocks"]))
        self.assertEqual(plan["conds"], {"bigcert": S.CONDS["bigcert"]})
        self.assertEqual(S.CONDS["bigcert"]["cert"], 16000)
        self.assertEqual(S.CONDS["bigcert"]["rtt_ms"], 50.0)
        self.assertEqual(S.CONDS["bigcert"]["netem_rate_mbit"], 2.0)
        self.assertEqual(plan["loss_direction"], "client_to_server_only")
        self.assertEqual(plan["arms"]["v2m1"], S.ARMS["v2m1"])
        self.assertEqual(plan["arms"]["m4L3"]["extra"], ["-layout", "v3", "-lead", "3"])
        self.assertEqual((plan["arms"]["v2m1"]["bin"], plan["arms"]["m4L3"]["bin"]), ("g2", "g3"))
        self.assertEqual(plan["ports"], {"g2": 44433, "g3": 44434})
        self.assertEqual(plan["bins_sha256_required"]["g2"], G.G2_FROZEN_SHA256)

    def test_schedule_is_cyclic_and_position_balanced(self):
        plan = M.build_plan()
        sched = plan["schedule"]
        self.assertEqual(len(sched), 10)
        for b in sched:
            self.assertEqual(b["sizes"], {"v2m1": 40, "m4L3": 40})
            self.assertEqual(b["order"], ["v2m1", "m4L3"] if b["block"] % 2 == 0
                             else ["m4L3", "v2m1"])
        cell = plan["cells"][0]
        self.assertTrue(cell["latin_closed"])
        self.assertEqual(cell["position_counts"], {"v2m1": [5, 5], "m4L3": [5, 5]})
        self.assertEqual(sum(sum(b["sizes"].values()) for b in sched), 800)

    def test_paths_are_separate_from_stage0(self):
        P = M.paths()
        self.assertEqual(os.path.relpath(P["result"], ROOT).replace("\\", "/"),
                         "experiments/results/g3_m1confirm.json")
        for k, suffix in (("journal", "_units.jsonl"), ("meta", "_meta.json"),
                          ("status", "_status.json"), ("incidents", "_incidents.jsonl")):
            self.assertEqual(os.path.relpath(P[k], ROOT).replace("\\", "/"),
                             "experiments/state/g3_m1confirm" + suffix)
        used = set(S.paths("full").values()) | set(S.paths("smoke").values())
        self.assertFalse(set(P.values()) & used)

    @pytest.mark.historical(reason='requires the historical stage0 seal, which is absent from gen33')
    def test_importing_does_not_touch_stage0_module(self):
        self.assertEqual(len(S.CELLS), 4)
        self.assertTrue(S.PREDICTIONS.endswith("stage0_predictions.json"))
        self.assertTrue(S.SEAL.endswith("SEAL_stage0.json"))
        self.assertEqual(len(S.build_plan("full")["schedule"]), 70)
        self.assertTrue(S.seal_check()["ok"])


class SealedFilesTests(unittest.TestCase):
    @pytest.mark.historical(reason='requires historical sealed protocol, prediction or development-cell files absent from gen33')
    def test_predictions_are_verbatim_copies_of_stage0(self):
        with open(ROOT / "g3" / "stage0_predictions.json", "rb") as f:
            raw = f.read()
        src = json.loads(raw.decode("utf-8"))
        with open(M.PREDICTIONS, encoding="utf-8") as f:
            ours = json.load(f)
        self.assertEqual(ours["copied_from"]["sha256"], hashlib.sha256(raw).hexdigest())
        sc = src["conditions"]["bigcert_loss2"]
        oc = ours["conditions"]["bigcert_loss2"]
        self.assertEqual(set(oc["arms"]), {"v2-m1", "m4L3"})
        for arm in ("v2-m1", "m4L3"):
            self.assertEqual(oc["arms"][arm], sc["arms"][arm])
        self.assertEqual({k: v for k, v in oc.items() if k != "arms"},
                         {k: v for k, v in sc.items() if k != "arms"})
        self.assertEqual(ours["one_rtt_definition"], src["one_rtt_definition"])
        self.assertEqual(ours["stage0_decision_rule_M1"], src["decision_rules"]["M1"])
        rule = ours["decision_rule"]
        self.assertEqual(rule["a"]["predicted"], src["decision_rules"]["M1"]["criteria"][0]["predicted"])
        self.assertEqual(rule["b"]["predicted"], src["decision_rules"]["M1"]["criteria"][1]["predicted"])
        self.assertEqual((rule["a"]["threshold"], rule["b"]["threshold"],
                          rule["c_prime"]["threshold"]), (0.85, -18.0, 0.9))
        self.assertEqual(rule["c_prime"]["reference_binomial"], 0.98 ** 3)

    @pytest.mark.historical(reason='requires historical sealed protocol, prediction or development-cell files absent from gen33')
    def test_plan_matches_sealed_predictions(self):
        self.assertEqual(M.sealed_plan_check(M.build_plan()), [])
        self.assertAlmostEqual(S.nominal_threshold(0, S.CONDS["bigcert"]), 85.24)
        self.assertAlmostEqual(CUT_M4, 101.212)

    @pytest.mark.historical(reason='requires historical sealed protocol, prediction or development-cell files absent from gen33')
    def test_plan_check_catches_changed_threshold_and_n(self):
        with open(M.PREDICTIONS, encoding="utf-8") as f:
            pred = json.load(f)
        pred["decision_rule"]["c_prime"]["threshold"] = 0.85
        pred["conditions"]["bigcert_loss2"]["arms"]["m4L3"]["n_planned"] = 800
        tmp = tempfile.mkdtemp()
        try:
            path = os.path.join(tmp, "p.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(pred, f)
            with patch.object(M, "PREDICTIONS", path):
                diffs = M.sealed_plan_check(M.build_plan())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertTrue(any("c_prime threshold" in d for d in diffs), diffs)
        self.assertTrue(any("m4L3: n 400 vs sealed 800" in d for d in diffs), diffs)

    @pytest.mark.historical(reason='requires historical sealed protocol, prediction or development-cell files absent from gen33')
    def test_seal_holds_and_covers_protocol_predictions_and_runners(self):
        chk = M.seal_check()
        self.assertTrue(chk["ok"], chk)
        with open(M.SEAL, encoding="utf-8") as f:
            seal = json.load(f)
        self.assertEqual(set(seal["sha256"]), set(M.SEALED_FILES))
        self.assertEqual(list(load_seal_script().SEALED), list(M.SEALED_FILES))
        for rel in ("g3/PROTOCOL_m1confirm.md", "g3/m1confirm_predictions.json",
                    "experiments/g3_m1confirm.py", "experiments/g3_stage0.py"):
            self.assertIn(rel, seal["sha256"])
        self.assertRegex(seal["sealed_utc"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    @pytest.mark.historical(reason='requires historical sealed protocol, prediction or development-cell files absent from gen33')
    def test_seal_check_fails_on_change_or_missing_coverage(self):
        real = G.sha256_or_none
        runner = os.path.join(str(ROOT), "experiments", "g3_m1confirm.py")

        def changed(path):
            if os.path.normpath(path) == os.path.normpath(runner):
                return "0" * 64
            return real(path)
        with patch.object(G, "sha256_or_none", changed):
            chk = M.seal_check()
        self.assertFalse(chk["ok"])
        self.assertEqual(chk["changed"], ["experiments/g3_m1confirm.py"])
        with patch.object(M, "SEALED_FILES", M.SEALED_FILES + ("experiments/extra.py",)):
            chk = M.seal_check()
        self.assertFalse(chk["ok"])
        self.assertEqual(chk["uncovered"], ["experiments/extra.py"])

    @pytest.mark.historical(reason='requires historical sealed protocol, prediction or development-cell files absent from gen33')
    def test_protocol_text_rules(self):
        text = (ROOT / "g3" / "PROTOCOL_m1confirm.md").read_text(encoding="utf-8")
        self.assertNotIn("\u2014", text)
        self.assertNotIn("\u2013", text)
        self.assertNotIn("\r", text)
        for needle in ("RESULT_stage0.md", "0.9325", "0.9412", "3.5", "0.90", "-18 ms",
                       "0.85", "10,000 ms", "beff_credit", "credit_parities_v3",
                       "first_rx_ns", "g3_m1confirm.json"):
            self.assertIn(needle, text)


class DecisionTests(TempPaths):
    def build(self, per_arm=None, mutate=None):
        plan = M.build_plan()
        jr = Journal(self.P["journal"], "fp")
        for blk in plan["schedule"]:
            rec = fake_block(blk, per_arm)
            if mutate:
                mutate(blk, rec)
            self.assertTrue(S.block_complete(rec, blk))
            jr.record(S.unit_key(M.MODE, blk["cell"], blk["block"]), rec)
        meta = {"fp": "fp", "plan": plan,
                "starts": [{"binaries": {"g2": {"sha256": "a"}, "g3": {"sha256": "b"}},
                            "quicbed_sources_sha256": {"qamp.go": "x"},
                            "seal_check": {"ok": True}}],
                "finished": {"quicbed_sources_sha256": {"qamp.go": "x"}}}
        return M.finalize(plan, meta, Journal(self.P["journal"], "fp"), self.P)

    def test_pass_on_synthetic_v3_server(self):
        rep = self.build()
        m = rep["m1_prime"]
        self.assertTrue(m["pass"], json.dumps(m, default=str)[:1500])
        self.assertEqual(m["a"]["one_rtt_rate"], 1.0)
        self.assertAlmostEqual(m["a"]["cutoff_ms"], 101.212)
        self.assertAlmostEqual(m["b"]["diff_ms"], -42.0)
        self.assertEqual(m["b"]["paired_blocks"]["blocks"], 10)
        self.assertEqual((m["c_prime"]["conns_with_tx"], m["c_prime"]["beff_credit_eq_lead"]),
                         (400, 400))
        self.assertTrue(m["c_prime"]["v3_equal_every_segment"])
        self.assertEqual(len(m["c_prime"]["per_segment"]), 10)
        self.assertTrue(m["stage0_c_reported_only"]["bound_ok"])
        sup = rep["supporting"]["credit_vs_one_rtt"]
        self.assertTrue(sup["reported_not_judged"])
        self.assertEqual(sup["segments_joined"], 10)
        self.assertEqual(sup["groups"]["eq_lead"], {"n": 400, "one_rtt": 400, "one_rtt_rate": 1.0})
        with open(self.P["result"], encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["schema"], "g3_m1confirm.result.v1")
        self.assertIn("does not overturn", saved["stage0_m1"])

    def credit_spec(self, n_short):
        per_arm = {}
        left = n_short
        for b in range(10):
            k = min(left, 40)
            left -= k
            credits = [2] * k + [3] * (40 - k)
            ms = [140.0] * k + [80.0] * (40 - k)
            per_arm[(b, "m4L3")] = {"credits": credits, "ms": ms}
        return per_arm

    def test_c_prime_threshold_is_inclusive_at_090(self):
        m = self.build(self.credit_spec(40))["m1_prime"]
        self.assertEqual(m["c_prime"]["frac_beff_credit_eq_lead"], 0.9)
        self.assertTrue(m["c_prime"]["ok"])
        self.assertTrue(m["pass"])

    def test_c_prime_fails_below_090_while_a_and_b_hold(self):
        rep = self.build(self.credit_spec(41))
        m = rep["m1_prime"]
        self.assertAlmostEqual(m["c_prime"]["frac_beff_credit_eq_lead"], 359 / 400)
        self.assertFalse(m["c_prime"]["frac_ok"])
        self.assertTrue(m["a"]["ok"])
        self.assertTrue(m["b"]["ok"])
        self.assertFalse(m["pass"])
        g = rep["supporting"]["credit_vs_one_rtt"]["groups"]
        self.assertEqual((g["eq_lead"]["n"], g["eq_lead"]["one_rtt"]), (359, 359))
        self.assertEqual((g["lt_lead"]["n"], g["lt_lead"]["one_rtt"]), (41, 0))

    def test_missing_beff_credit_counts_as_not_three(self):
        credits = [None] * 40
        m = self.build({(0, "m4L3"): {"credits": credits}})["m1_prime"]
        self.assertEqual(m["c_prime"]["conns_with_tx"], 400)
        self.assertEqual(m["c_prime"]["beff_credit_eq_lead"], 360)
        self.assertTrue(m["c_prime"]["frac_ok"])
        m = self.build({(0, "m4L3"): {"credits": credits},
                        (1, "m4L3"): {"credits": [3] * 39 + [None]}})["m1_prime"]
        self.assertFalse(m["c_prime"]["frac_ok"])

    def test_v3_counter_must_match_in_every_segment(self):
        m = self.build({(3, "m4L3"): {"v3_delta": 1}})["m1_prime"]
        self.assertFalse(m["c_prime"]["v3_equal_every_segment"])
        self.assertFalse(m["pass"])
        m = self.build({(7, "m4L3"): {"drop_v3": True}})["m1_prime"]
        self.assertFalse(m["c_prime"]["v3_equal_every_segment"])
        self.assertFalse(m["pass"])

    def test_flag_mismatch_fails_c_prime(self):
        def mutate(blk, rec):
            if blk["block"] == 4:
                seg = next(s for s in rec["segments"] if s["arm"] == "m4L3")
                seg["rows"][5]["lead"] = 2
        m = self.build(mutate=mutate)["m1_prime"]
        self.assertEqual(m["c_prime"]["flag_mismatches"]["lead"], 1)
        self.assertFalse(m["c_prime"]["flag_mismatches_zero"])
        self.assertFalse(m["pass"])

    def test_a_and_b_fail_when_m4l3_is_slow(self):
        m = self.build({"m4L3": {"ms": [110.0] * 40}})["m1_prime"]
        self.assertEqual(m["a"]["one_rtt_rate"], 0.0)
        self.assertFalse(m["a"]["ok"])
        self.assertAlmostEqual(m["b"]["diff_ms"], -12.0)
        self.assertFalse(m["b"]["ok"])
        self.assertTrue(m["c_prime"]["ok"])
        self.assertFalse(m["pass"])

    def test_failures_are_imputed_at_10000_ms_in_b(self):
        ok = [False] + [True] * 39
        rep = self.build({(0, "m4L3"): {"ok": ok}})
        m = rep["m1_prime"]
        v = rep["cells"][0]["arms"]["m4L3"]
        self.assertAlmostEqual(v["mean_planned_imputed_ms"], (399 * 80.0 + 10000.0) / 400)
        self.assertAlmostEqual(m["b"]["diff_ms"], (399 * 80.0 + 10000.0) / 400 - 122.0)
        self.assertFalse(m["b"]["ok"])
        self.assertAlmostEqual(m["a"]["one_rtt_rate"], 399 / 400)

    def test_unjoinable_segment_is_excluded_from_report_only(self):
        rep = self.build({(2, "m4L3"): {"conns_n": 39}})
        sup = rep["supporting"]["credit_vs_one_rtt"]
        self.assertEqual(sup["segments_joined"], 9)
        self.assertEqual(sup["segments_excluded"],
                         [{"block": 2, "reason": "server connections 39 != client rows 40"}])
        self.assertEqual(sup["groups"]["eq_lead"]["n"], 360)


class JoinTests(unittest.TestCase):
    def seg(self, **kw):
        credits = [3] * 20 + [1] * 20
        ms = [80.0] * 20 + [140.0] * 20
        return fake_segment("m4L3", 40, 0, 0, credits=credits, ms=ms, **kw)

    def test_join_orders_connections_by_first_rx(self):
        seg = self.seg()
        self.assertNotEqual([c["first_rx_ns"] for c in seg["server_new_conns"]],
                            sorted(c["first_rx_ns"] for c in seg["server_new_conns"]))
        pairs, why = M.join_segment(seg)
        self.assertEqual(why, "")
        self.assertEqual([r["i"] for r, _c in pairs], list(range(40)))
        rx = [c["first_rx_ns"] for _r, c in pairs]
        self.assertEqual(rx, sorted(rx))
        for r, c in pairs:
            self.assertEqual(c["beff_credit"] == 3, r["ms"] < CUT_M4)

    def test_join_refuses_unsafe_segments(self):
        seg = self.seg()
        seg["rows"] = seg["rows"][:39]
        self.assertEqual(M.join_segment(seg), (None, "client rows incomplete or out of order"))
        seg = self.seg()
        seg["rows"][3], seg["rows"][4] = seg["rows"][4], seg["rows"][3]
        self.assertIsNone(M.join_segment(seg)[0])
        seg = self.seg()
        seg["server_new_conns"].append(fake_conn(99, 3))
        self.assertIn("server connections 41", M.join_segment(seg)[1])
        seg = self.seg()
        seg["server_new_conns"][0]["first_rx_ns"] = None
        self.assertEqual(M.join_segment(seg)[1], "server connection without first_rx_ns")
        seg = self.seg()
        cs = sorted(seg["server_new_conns"], key=lambda c: c["first_rx_ns"])
        cs[5]["first_rx_ns"] = cs[4]["first_rx_ns"] + 49 * 10 ** 6
        self.assertIn("< client gap 50 ms", M.join_segment(seg)[1])
        seg = self.seg()
        seg["server_delta"]["conn_acct_alias_conflicts"] = 1
        self.assertIsNone(M.join_segment(seg)[0])
        seg = self.seg()
        seg["server_delta"]["conn_acct_dropped"] = 2
        self.assertIsNone(M.join_segment(seg)[0])

    def test_credit_classes(self):
        self.assertEqual(M.credit_class({"tx_dgrams": 3, "beff_credit": 3}, 3), "eq_lead")
        self.assertEqual(M.credit_class({"tx_dgrams": 3, "beff_credit": 2}, 3), "lt_lead")
        self.assertEqual(M.credit_class({"tx_dgrams": 3, "beff_credit": 4}, 3), "gt_lead")
        self.assertEqual(M.credit_class({"tx_dgrams": 0, "beff_credit": 3}, 3),
                         "no_tx_or_unknown")
        self.assertEqual(M.credit_class({"tx_dgrams": 3}, 3), "no_tx_or_unknown")


class FakeProc:
    def __init__(self, owner):
        self.owner = owner

    def poll(self):
        return 1 if self.owner.dead else None


class LiveFlowTests(TempPaths):
    def setUp(self):
        super().setUp()
        self.calls = []
        self.dead = False
        self.die_calls = set()
        self.busy = []
        self.bin_problems = []
        self.conns = {"g2": {}, "g3": {}}
        self.count = {"g2": 0, "g3": 0}
        self.clock = 10 ** 18
        self.real_sha = G.sha256_or_none
        self.binrep = {"g2": {"exists": True, "sha256": G.G2_FROZEN_SHA256,
                              "path": G.BINS["g2"]},
                       "g3": {"exists": True, "sha256": M.G3_STAGE0_SHA256,
                              "path": G.BINS["g3"]}}

    def fake_client(self, tag, group, n, fec, m, gap_ms, timeout_s, expect_k, uplink, extra=()):
        self.calls.append((tag, n, m, tuple(extra)))
        arm = next(a for a, v in S.ARMS.items() if v["bin"] == tag and v["m"] == m
                   and list(v["extra"]) == list(extra))
        if len(self.calls) in self.die_calls:
            self.dead = True
        rows = []
        for i in range(n):
            self.clock += NS_GAP
            self.conns[tag]["initial:%d" % self.clock] = fake_conn(0, 3 if tag == "g3" else 0,
                                                                   self.clock)
            rows.append(fake_row(i, arm, 80.0 if tag == "g3" else 122.0))
        self.count[tag] += n
        return rows, {"parity_sent": n * m}, "", ["x"], 0

    def fake_stats(self, path):
        tag = "g2" if path.endswith("srv_g2.json") else "g3"
        c = self.count[tag]
        out = {"parities": c * (4 if tag == "g3" else 1),
               "credit_parities": 3 * c if tag == "g3" else 0, "bytes_in": 10 * c,
               "bytes_to_stack": 9 * c, "conns": dict(self.conns[tag])}
        if tag == "g3":
            out["credit_parities_v3"] = 3 * c
        return out

    def sha(self, path):
        for tag in ("g2", "g3"):
            if path == G.BINS[tag]:
                return self.binrep[tag]["sha256"]
        return self.real_sha(path)

    def go(self, fn=None):
        def server(tag, cert, fec="on", extra=()):
            self.dead = False
            return {"tag": tag, "proc": FakeProc(self), "pid": 100 + len(tag),
                    "certsize": cert, "cert_der": cert, "argv": [],
                    "stats_path": "/x/srv_%s.json" % tag}

        out = io.StringIO()
        patches = [
            patch.object(sys, "platform", "linux"),
            patch.object(S.B, "harden"),
            patch.object(S.B, "require_root"),
            patch.object(S.signal, "signal"),
            patch.object(M, "paths", lambda: self.P),
            patch.object(G, "busy_processes", lambda allowed=(): list(self.busy)),
            patch.object(G, "load_processes", lambda: []),
            patch.object(G, "binary_report", lambda: (self.binrep, list(self.bin_problems))),
            patch.object(G, "flag_report", lambda rep: ({}, [])),
            patch.object(G, "environment", lambda: {"quicbed_sources_sha256": {}}),
            patch.object(G, "quicbed_sources", lambda: ({}, "x")),
            patch.object(G, "setup"),
            patch.object(G, "start_server", server),
            patch.object(G, "stop_server"),
            patch.object(G, "set_netem", lambda *a: {"tc_c2s": "", "tc_s2c": ""}),
            patch.object(G, "read_stats", self.fake_stats),
            patch.object(G, "run_client", self.fake_client),
            patch.object(G, "validate_client", lambda tag, fec, m, extra=(): (True, ["x"], "")),
            patch.object(G, "sha256_or_none", self.sha),
            patch.object(S.time, "sleep"),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(io.StringIO()),
        ]
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            return (fn or M.live)(), out.getvalue()

    @pytest.mark.historical(reason='requires the enabled historical runner; gen33 intentionally refuses legacy execution')
    def test_full_flow_runs_plan_and_passes_on_v3_like_server(self):
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(self.calls), 20)
        self.assertTrue(all(n == 40 for _t, n, _m, _e in self.calls))
        self.assertEqual(sum(n for _t, n, _m, _e in self.calls), 800)
        self.assertEqual({(t, m, e) for t, _n, m, e in self.calls},
                         {("g2", 1, ()), ("g3", 4, ("-layout", "v3", "-lead", "3"))})
        self.assertEqual([c[0] for c in self.calls[:4]], ["g2", "g3", "g3", "g2"])
        with open(self.P["result"], encoding="utf-8") as f:
            rep = json.load(f)
        self.assertTrue(rep["m1_prime"]["pass"], json.dumps(rep["m1_prime"])[:1500])
        self.assertEqual(rep["supporting"]["credit_vs_one_rtt"]["segments_joined"], 10)
        self.assertTrue(rep["env_starts"][0]["seal_check"]["ok"])
        self.assertEqual(rep["env_starts"][0]["sealed_plan_differences"], [])
        self.assertEqual(rep["integrity"]["runner_sha256_seen"], [M.runner_sha256()])
        with open(self.P["meta"], encoding="utf-8") as f:
            fp = json.load(f)["fp"]
        keys = sorted(Journal(self.P["journal"], fp).keys())
        self.assertEqual(keys, ["m1confirm|bigcert_2|b%02d" % b for b in range(10)])
        self.assertIn("M1' PASS", out)
        rc, _ = self.go()
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.calls), 20)
        with open(self.P["result"], encoding="utf-8") as f:
            self.assertEqual(json.load(f)["integrity"]["journal_provenance"]["reused_units"], 10)
        rc, _ = self.go(M.report_only)
        self.assertEqual(rc, 0)

    @pytest.mark.historical(reason='requires the enabled historical runner; gen33 intentionally refuses legacy execution')
    def test_server_death_retries_block_once(self):
        self.die_calls = {3}
        rc, _ = self.go()
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.calls), 21)
        with open(self.P["result"], encoding="utf-8") as f:
            rep = json.load(f)
        self.assertEqual(rep["integrity"]["attempts_gt_1"], 1)

    def test_refuses_on_broken_seal(self):
        bad = {"path": M.SEAL_REL, "ok": False, "changed": ["g3/PROTOCOL_m1confirm.md"],
               "missing": [], "uncovered": []}
        with patch.object(M, "seal_check", lambda: bad):
            rc, _ = self.go()
        self.assertEqual(rc, 2)
        self.assertEqual(self.calls, [])
        self.assertFalse(os.path.exists(self.P["meta"]))

    def test_refuses_when_plan_differs_from_sealed_predictions(self):
        with patch.object(M, "sealed_plan_check", lambda plan: ["x: n 400 vs sealed 800"]):
            rc, _ = self.go()
        self.assertEqual(rc, 2)
        self.assertEqual(self.calls, [])

    def test_refuses_on_missing_predictions(self):
        with patch.object(M, "PREDICTIONS", os.path.join(self.tmp, "none.json")):
            rc, _ = self.go()
        self.assertEqual(rc, 2)
        self.assertEqual(self.calls, [])

    def test_refuses_when_g3_is_not_the_stage0_binary(self):
        self.binrep["g3"]["sha256"] = "b" * 64
        rc, _ = self.go()
        self.assertEqual(rc, 2)
        self.assertEqual(self.calls, [])

    def test_refuses_when_binaries_are_missing(self):
        self.bin_problems = ["g3 binary missing: /tmp/qamp_g3/g3/qamp"]
        rc, _ = self.go()
        self.assertEqual(rc, 2)
        self.assertEqual(self.calls, [])

    def test_refuses_when_another_measurement_runs(self):
        self.busy = ["measurement script pid 9: python3 experiments/p17_adaptive_value.py"]
        rc, _ = self.go()
        self.assertEqual(rc, 2)
        self.assertEqual(self.calls, [])

    @pytest.mark.historical(reason='requires the enabled historical runner; gen33 intentionally refuses legacy execution')
    def test_foreign_measurement_mid_run_aborts(self):
        def client(*a, **k):
            if len(self.calls) == 4:
                self.busy = ["qamp pid 1 (pgrep -x qamp)"]
            return LiveFlowTests.fake_client(self, *a, **k)
        self.fake_client = client
        rc, _ = self.go()
        self.assertEqual(rc, 3)
        with open(self.P["status"], encoding="utf-8") as f:
            self.assertEqual(json.load(f)["state"], "aborted")
        self.assertFalse(os.path.exists(self.P["result"]))
        self.assertEqual(len(self.calls), 6)
        rc, _ = self.go(M.report_only)
        self.assertEqual(rc, 3)
        self.assertFalse(os.path.exists(self.P["result"]))

    def test_report_only_without_meta_refuses(self):
        rc, _ = self.go(M.report_only)
        self.assertEqual(rc, 2)


class CliTests(unittest.TestCase):
    @pytest.mark.historical(reason='requires the enabled historical runner; gen33 intentionally refuses legacy execution')
    def test_cli_requires_explicit_mode(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                M.main([])

    @pytest.mark.historical(reason='requires the enabled historical runner; gen33 intentionally refuses legacy execution')
    def test_dry_run_writes_nothing(self):
        before = sorted(os.listdir(B.RESULTS)), sorted(os.listdir(B.STATE))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(M.main(["--dry-run"]), 0)
        self.assertEqual(before, (sorted(os.listdir(B.RESULTS)), sorted(os.listdir(B.STATE))))
        text = out.getvalue()
        self.assertIn("schedule m1confirm: 10 blocks, 800 connections", text)
        self.assertIn("seal check g3/SEAL_m1confirm.json", text)
        self.assertIn("plan vs sealed predictions (condition, arms, n, 1-RTT cutoffs, "
                      "thresholds): match", text)
        self.assertIn("same cell as stage-0 bigcert_2: True", text)
        self.assertIn("build_g3.sh --install-only && unshare -Urnm python3 -u "
                      "experiments/g3_m1confirm.py --full", text)


if __name__ == "__main__":
    unittest.main()
