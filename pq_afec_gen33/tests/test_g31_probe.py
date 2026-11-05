import pytest
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import g31_probe as P
import g3_stage0 as S
import g3bed as G
from _journal import Journal

A0 = "c6000_r80_u10_l0"


def parity_size(arm):
    a = P.ARMS[arm]
    return a["ips"] + 39 + 6 * P.EXPECT_K if a["m"] else 0


def fake_row(i, arm, ms, ok=True):
    a = P.ARMS[arm]
    row = {"i": i, "ms": ms, "ok": ok, "group": P.GROUP, "first_flight_datagrams": 2,
           "first_flight_bytes": 2 * a["ips"], "first_flight_parity_dgrams": a["m"],
           "first_flight_parity_bytes": a["m"] * parity_size(arm), "m_used": a["m"],
           "ips_used": a["ips"], "ips_eff": a["ips"], "layout": a["layout"],
           "lead": a["lead"], "first_flight_lead_dgrams": a["lead"], "server_bytes": 7600,
           "parity_sent": a["m"]}
    if not ok:
        row["err"] = "timeout: no recent network activity"
    return row


def fake_conn(i, first_rx_ns, sizes, timeline, offsets_ms, wait_ms=2.0, beff_parity=0,
              beff_credit=0, beff_orig=2562):
    t0 = first_rx_ns + int(wait_ms * 1e6)
    tx_ns = [t0 + int(round(o * 1e6)) for o in offsets_ms]
    return {"initial_dcid": "%016x" % (i + 1), "client_scid": "%08x" % (i + 7),
            "first_rx_ns": first_rx_ns, "first_tx_ns": tx_ns[0], "rx_dgrams": 6,
            "rx_bytes": 9000, "rx_orig_bytes": 2562, "rx_parity_bytes": 0,
            "stack_bytes": 8000, "tx_dgrams": len(sizes), "tx_bytes": sum(sizes),
            "beff_stack": timeline[0], "beff_phys": timeline[0], "beff_orig": beff_orig,
            "beff_parity": beff_parity, "beff_credit": beff_credit,
            "tx_rx_timeline": list(timeline), "tx_sizes": list(sizes), "tx_ns": tx_ns,
            "rx_crc": [1, 2]}


ONE_RTT_SIZES = [1280] * 6
ONE_RTT_TL = [2562] * 6
ONE_RTT_OFF = [0.0, 0.05, 0.1, 0.15, 0.2, 0.25]
TWO_RTT_SIZES = [1280] * 6 + [1280, 900]
TWO_RTT_TL = [2560] * 6 + [5120, 5120]
TWO_RTT_OFF = [0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 80.3, 80.35]


def fake_segment(arm, n, pos, ms_list, base_ns, conn_shape):
    rows = [fake_row(i, arm, ms_list[i]) for i in range(n)]
    sizes, tl, off = conn_shape
    conns = [fake_conn(i, base_ns + i * 300_000_000, sizes, tl, off) for i in range(n)]
    for c in conns:
        c["conn_key"] = "initial:%s/%s" % (c["initial_dcid"], c["client_scid"])
    return {"arm": arm, "pos": pos, "bin": P.ARMS[arm]["bin"], "port": P.PORTS[P.ARMS[arm]["bin"]],
            "argv": [], "rc": 0, "err": "", "client_err": "", "n_planned": n, "n_rows": n,
            "rows": rows, "client_stats": {"bytes_orig": n * 2562, "bytes_parity": 0,
                                           "parity_sent": 0},
            "server_delta": {"bytes_in": 9000 * n, "recover_crc_fail": 0},
            "server_after": {"bytes_in": 10, "bytes_to_stack": 9},
            "server_new_conns": list(reversed(conns)), "other_server_delta": {},
            "other_server_new_conns": 0}


def fake_block(blk, shapes, ms):
    segs = []
    for pos, arm in enumerate(blk["order"]):
        n = blk["sizes"][arm]
        segs.append(fake_segment(arm, n, pos, ms[arm], 10 ** 12 + pos * 10 ** 11, shapes[arm]))
    return {"label": P.LABEL, "cell": blk["cell"], "block": blk["block"],
            "rotation": blk["rotation"], "order": blk["order"], "sizes": blk["sizes"],
            "attempt": 1, "netem": {"c2s": "x", "expected_tokens": {"c2s_delay": True}},
            "warmup": {"g2": {"n": 2, "ok": 2, "err": ""}, "g3b": {"n": 2, "ok": 2, "err": ""}},
            "servers": {"g2": {"cert_der": 6000}, "g3b": {"cert_der": 6000}},
            "segments": segs, "load_processes": [], "bins_sha256": {"g2": "a", "g3b": "b"},
            "runner_sha256": "r", "err": "", "client_errors": []}


class PlanTests(unittest.TestCase):
    def test_run_plan_blocks_rotation_and_counts(self):
        plan = P.build_plan("run")
        self.assertEqual(plan["label"], "development (not confirmatory)")
        self.assertEqual(len(plan["cells"]), 4)
        self.assertEqual(len(plan["schedule"]), 20)
        arms = list(P.ARM_ORDER)
        self.assertEqual(len(arms), 8)
        for cell in plan["cells"]:
            blocks = [b for b in plan["schedule"] if b["cell"] == cell["cell"]]
            self.assertEqual([b["block"] for b in blocks], list(range(5)))
            self.assertFalse(cell["latin_closed"])
            for arm in arms:
                self.assertEqual(sum(b["sizes"][arm] for b in blocks), 200)
                self.assertEqual({b["sizes"][arm] for b in blocks}, {40})
                self.assertEqual(Counter(b["order"].index(arm) for b in blocks).most_common(1)[0][1], 1)
            for b in blocks:
                r = b["block"] % len(arms)
                self.assertEqual(b["rotation"], r)
                self.assertEqual(b["order"], arms[r:] + arms[:r])
        self.assertEqual(sum(n for c in plan["cells"] for _a, n in c["arms"]), 6400)

    def test_smoke_plan_is_five_per_arm_in_one_block(self):
        plan = P.build_plan("smoke")
        self.assertEqual(len(plan["schedule"]), 4)
        for b in plan["schedule"]:
            self.assertEqual(b["order"], list(P.ARM_ORDER))
            self.assertEqual(set(b["sizes"].values()), {5})
        with self.assertRaises(ValueError):
            P.build_plan("full")

    def test_cells_conditions_and_h_mapping(self):
        cells = {c["cell"]: c for c in P.build_plan("run")["cells"]}
        self.assertEqual(set(cells), {"c6000_r80_u10_l0", "c6000_r80_u10_l1",
                                      "bigcert_r50_u2_l0", "c6000_r80_u0_l0"})
        a0, a1 = cells["c6000_r80_u10_l0"], cells["c6000_r80_u10_l1"]
        for c in (a0, a1):
            self.assertEqual((c["cert"], c["rtt_ms"], c["rate_mbit"]), (6000, 80.0, 10.0))
            self.assertEqual(c["h_cell"], "h_c6000_r80_u10")
            self.assertIn("rate 10mbit", c["netem"]["c2s"])
            self.assertIn("delay 40.000ms", c["netem"]["c2s"])
            self.assertNotIn("rate", c["netem"]["s2c"])
        self.assertEqual((a0["loss_pct"], a1["loss_pct"]), (0.0, 1.0))
        self.assertIn("loss 1.0000%", a1["netem"]["c2s"])
        self.assertNotIn("loss", a0["netem"]["c2s"])
        b = cells["bigcert_r50_u2_l0"]
        self.assertEqual((b["cert"], b["rtt_ms"], b["rate_mbit"], b["loss_pct"], b["h_cell"]),
                         (16000, 50.0, 2.0, 0.0, None))
        c = cells["c6000_r80_u0_l0"]
        self.assertEqual((c["cert"], c["rtt_ms"], c["rate_mbit"], c["h_cell"]),
                         (6000, 80.0, 0.0, "h_c6000_r80_u0"))
        self.assertNotIn("rate", c["netem"]["c2s"])

    def test_estimate_bounds(self):
        e = P.estimate(P.build_plan("run"))
        self.assertLess(e["total_low_s"], e["total_high_s"])
        self.assertAlmostEqual(e["planning_s"], e["total_high_s"] * P.PLAN_MARGIN)
        self.assertEqual(len(e["per_block_s"]), 20)
        self.assertTrue(15 * 60 < e["total_low_s"] < e["total_high_s"] < 40 * 60)


class FlagTests(unittest.TestCase):
    def test_exact_flags_per_arm(self):
        want = {
            "none": ["-fec", "off", "-ips", "1280"],
            "pad": ["-fec", "off", "-ips", "1281"],
            "a104": ["-fec", "fec", "-m", "4", "-ips", "1281", "-layout", "v3", "-lead", "0"],
            "a113": ["-fec", "fec", "-m", "4", "-ips", "1281", "-layout", "v3", "-lead", "1"],
            "a004": ["-fec", "fec", "-m", "4", "-ips", "1280", "-layout", "v3", "-lead", "0"],
            "a031": ["-fec", "fec", "-m", "4", "-ips", "1280", "-layout", "v3", "-lead", "3"],
            "a013": ["-fec", "fec", "-m", "4", "-ips", "1280", "-layout", "v3", "-lead", "1"],
            "g2pad": ["-fec", "off", "-ips", "1281"],
        }
        self.assertEqual({a: P.arm_flags(a) for a in P.ARM_ORDER}, want)
        for arm in P.ARM_ORDER:
            a = P.ARMS[arm]
            delta, lead, trail = a["action"]
            self.assertEqual(a["ips"], 1280 + delta)
            self.assertEqual((a["lead"], a["trail"], a["m"]), (lead, trail, lead + trail))
            self.assertTrue(P.layout_flags_ok(arm))
        self.assertEqual(P.ARMS["g2pad"]["bin"], "g2")
        self.assertEqual({P.ARMS[a]["bin"] for a in P.ARM_ORDER if a != "g2pad"}, {"g3b"})

    def test_layout_rule_mirrors_qamp(self):
        bad = dict(P.ARMS["pad"], layout="v3")
        with patch.dict(P.ARMS, {"bad": bad}):
            self.assertFalse(P.layout_flags_ok("bad"))
        over = dict(P.ARMS["a031"], lead=5)
        with patch.dict(P.ARMS, {"over": over}):
            self.assertFalse(P.layout_flags_ok("over"))
        src = (ROOT / "experiments" / "quicbed" / "qamp.go").read_text(encoding="utf-8")
        self.assertIn('return fmt.Errorf("-layout v3 needs -fec fec or -fec auto, got %q", fmode)',
                      src)

    @pytest.mark.historical(reason='source-line references describe the historical gen31 qamp implementation')
    def test_historical_source_reference_locations(self):
        refs = P.source_refs()
        self.assertTrue(all(refs.values()), refs)

    def test_client_and_server_argv(self):
        argv = P.client_argv("g3b", P.arm_flags("a104"), 40, 10.0, "/w/cli.json")
        self.assertEqual(argv[:9], [P.BINS["g3b"], "-mode", "client", "-addr", "10.9.0.2:44434",
                                    "-group", "X25519MLKEM768", "-n", "40"])
        tail = argv[9 + len(P.arm_flags("a104")):]
        self.assertEqual(tail, ["-gap", "50ms", "-timeout", "10s", "-stats", "/w/cli.json",
                                "-uplink-mbps", "10", "-expect-k", "2"])
        g2 = P.client_argv("g2", P.arm_flags("g2pad"), 5, 0.0, "/w/c.json")
        self.assertIn("10.9.0.2:44433", g2)
        self.assertEqual(g2[g2.index("-uplink-mbps") + 1], "0")
        srv = P.server_argv("g3b", 6000, "/w/s.json")
        self.assertEqual(srv[-8:], ["-addr", "10.9.0.2:44434", "-certsize", "6000", "-fec", "on",
                                    "-stats", "/w/s.json"])
        self.assertIn(P.BINS["g3b"], srv)


class MetricTests(unittest.TestCase):
    def test_delta1_one_more_send_fits_under_the_limit(self):
        c = fake_conn(0, 10 ** 12, ONE_RTT_SIZES + [1280], ONE_RTT_TL + [2562],
                      ONE_RTT_OFF + [0.3])
        m = P.conn_metrics(c, 80.0, 2562)
        self.assertEqual(m["b1_n"], 7)
        self.assertEqual(m["b1_bytes"], 8960)
        self.assertTrue(m["amp_rule_held_in_b1"])
        self.assertEqual(m["amp_limit_at_b1_end"], 7686)
        self.assertEqual(m["headroom_at_b1_end"], 7686 - 8960)
        self.assertTrue(m["amp_exhausted_at_b1_end"])
        self.assertEqual(m["bursts"], 1)
        self.assertIsNone(m["resume_after_first_tx_ms"])
        self.assertAlmostEqual(m["first_send_after_rx_ms"], 2.0)
        self.assertFalse(m["first_send_before_all_originals"])

    def test_delta0_blocks_after_six_and_resumes_after_a_round_trip(self):
        c = fake_conn(0, 10 ** 12, TWO_RTT_SIZES, TWO_RTT_TL, TWO_RTT_OFF, beff_orig=2560)
        m = P.conn_metrics(c, 80.0, 2560)
        self.assertEqual(m["b1_n"], 6)
        self.assertEqual(m["b1_sizes"], [1280] * 6)
        self.assertEqual(m["b1_bytes"], 7680)
        self.assertEqual(m["headroom_at_b1_end"], 0)
        self.assertTrue(m["amp_exhausted_at_b1_end"])
        self.assertEqual(m["bursts"], 2)
        self.assertAlmostEqual(m["resume_after_first_tx_ms"], 80.3)
        self.assertEqual(m["stall_stack_growth"], 2560)
        self.assertEqual((m["b2_n"], m["b2_bytes"], m["b2_sizes"]), (2, 2180, [1280, 900]))
        self.assertAlmostEqual(m["b1_end_after_rx_ms"], 2.25)

    def test_amp_rule_violation_and_early_first_send(self):
        c = fake_conn(0, 10 ** 12, [1280] * 4, [1000] * 4, [0, 0.1, 0.2, 0.3], beff_orig=1281)
        m = P.conn_metrics(c, 80.0, 2562)
        self.assertFalse(m["amp_rule_held_in_b1"])
        self.assertTrue(m["first_send_before_all_originals"])
        self.assertEqual(m["stack_growth_in_b1"], 0)

    def test_no_tx_connection(self):
        m = P.conn_metrics({"first_rx_ns": 5, "tx_sizes": [], "tx_rx_timeline": [],
                            "tx_ns": [], "beff_orig": 0}, 50.0, 2560)
        self.assertFalse(m["has_tx"])
        self.assertNotIn("b1_n", m)

    def test_arrival_model(self):
        offs = P.arrival_offsets_ms([1281, 1281, 1332, 1332], 10.0)
        self.assertEqual(offs[0], 0.0)
        self.assertAlmostEqual(offs[1], 8 * 1323 / 10000.0)
        self.assertAlmostEqual(offs[3], 8 * (1323 + 1374 + 1374) / 10000.0)
        self.assertEqual(P.arrival_offsets_ms([1281, 1332, 1332], 0.0), [0.0, 0.0, 0.0])

    def test_joined_metrics_trailing_parities_after_the_block(self):
        cell = next(c for c in P.CELLS if c["cell"] == A0)
        row = fake_row(0, "a104", 121.0)
        conn = fake_conn(0, 10 ** 12, ONE_RTT_SIZES, ONE_RTT_TL, ONE_RTT_OFF)
        d = P.joined_metrics(row, conn, "a104", cell)
        thr = 120.0 + 8 * 2562 / 10000.0
        self.assertAlmostEqual(d["one_rtt_threshold_ms"], thr)
        self.assertTrue(d["one_rtt"])
        self.assertEqual((d["lead_sent"], d["trailing_sent"], d["originals_sent"]), (0, 4, 2))
        self.assertEqual(d["parity_dgram_bytes"], 1332)
        o = 8 * 1323 / 10000.0
        p = 8 * 1374 / 10000.0
        self.assertAlmostEqual(d["model_last_original_after_rx_ms"], o)
        want = [o + p * (j + 1) for j in range(4)]
        for got, w in zip(d["model_trailing_after_rx_ms"], want):
            self.assertAlmostEqual(got, w)
        self.assertEqual(d["model_trailing_before_first_send"], 0)
        self.assertLess(want[0], 2.25)
        self.assertEqual(d["model_trailing_after_b1_end"], 3)
        self.assertAlmostEqual(d["model_trailing_minus_first_send_ms"][0], want[0] - 2.0)
        self.assertAlmostEqual(d["model_trailing_minus_b1_end_ms"][3], want[3] - 2.25)
        self.assertEqual(d["parities_before_first_send"], 0)
        self.assertEqual(d["trailing_before_first_send_measured"], 0)
        slow = P.joined_metrics(fake_row(1, "a104", 165.0), dict(conn, beff_parity=1332),
                                "a104", cell)
        self.assertFalse(slow["one_rtt"])
        self.assertEqual(slow["parities_before_first_send"], 1)
        self.assertEqual(slow["trailing_before_first_send_measured"], 1)

    def test_new_conn_records_keep_every_field(self):
        before = {"conns": {"k1": {"tx_sizes": [1]}}}
        after = {"conns": {"k1": {"tx_sizes": [1]},
                           "k2": {"tx_sizes": [1280, 1280], "tx_ns": [1, 2],
                                  "tx_rx_timeline": [2562, 2562], "beff_credit": 0,
                                  "rx_crc": [7], "whatever_new": 3}}}
        out = P.new_conn_records(before, after)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["conn_key"], "k2")
        self.assertEqual(out[0]["whatever_new"], 3)
        self.assertEqual(out[0]["tx_sizes"], [1280, 1280])


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.plan = P.build_plan("smoke")
        self.cell = next(c for c in self.plan["cells"] if c["cell"] == A0)
        self.blk = next(b for b in self.plan["schedule"] if b["cell"] == A0)
        self.shapes = {a: (ONE_RTT_SIZES, ONE_RTT_TL, ONE_RTT_OFF) for a in P.ARM_ORDER}
        self.shapes["pad"] = (TWO_RTT_SIZES, TWO_RTT_TL, TWO_RTT_OFF)
        self.ms = {a: [121.0] * 5 for a in P.ARM_ORDER}
        self.ms["pad"] = [165.0, 166.0, 167.0, 121.0, 168.0]
        self.rec = fake_block(self.blk, self.shapes, self.ms)

    def test_block_is_complete_for_the_stage0_checker(self):
        self.assertTrue(S.block_complete(self.rec, self.blk))

    def test_arm_summary_math(self):
        out = P.summarize_arm("pad", self.cell, [self.blk], {0: self.rec})
        self.assertEqual((out["n_requested"], out["n_returned"], out["ok"]), (5, 5, 5))
        self.assertAlmostEqual(out["mean_ok_ms"], sum(self.ms["pad"]) / 5)
        self.assertAlmostEqual(out["one_rtt_rate"], 0.2)
        self.assertAlmostEqual(out["one_rtt_threshold_median_ms"], 120.0 + 8 * 2562 / 10000.0)
        sv = out["server"]
        self.assertEqual(sv["conns_with_tx"], 5)
        self.assertEqual(sv["b1_sizes_mode"], {"sizes": [1280] * 6, "count": 5, "share": 1.0})
        self.assertEqual(sv["b1_bytes"]["median"], 7680)
        self.assertEqual(sv["amp_exhausted_at_b1_end_share"], 1.0)
        self.assertEqual(sv["resume_after_first_tx_ms"]["median"], 80.3)
        self.assertEqual(sv["bursts_hist"], {"2": 5})
        self.assertEqual(sv["beff_stack"]["median"], 2560)
        self.assertEqual(out["client"]["first_flight_uplink_bytes"]["mean"], 2562)
        j = out["joined"]
        self.assertEqual((j["segments_joined"], j["connections"]), (1, 5))
        self.assertEqual(j["one_rtt_by_amp_exhausted_at_b1_end"]["true"]["n"], 5)
        self.assertEqual(j["one_rtt_by_amp_exhausted_at_b1_end"]["true"]["one_rtt"], 1)
        rows = [c["row"]["i"] for c in out["per_connection"]["joined"]]
        self.assertEqual(rows, list(range(5)))
        firsts = [c["server"]["first_rx_ns"] for c in out["per_connection"]["joined"]]
        self.assertEqual(firsts, sorted(firsts))
        self.assertEqual(out["per_connection"]["joined"][0]["server"]["tx_sizes"], TWO_RTT_SIZES)
        self.assertFalse(any(out["flag_mismatches"].values()))

    def test_v3_arm_trailing_summary(self):
        out = P.summarize_arm("a104", self.cell, [self.blk], {0: self.rec})
        self.assertEqual(out["one_rtt_rate"], 1.0)
        t = out["joined"]["trailing"]
        self.assertEqual(t["trailing_sent_hist"], {"4": 5})
        self.assertEqual(t["model_trailing_after_b1_end_hist"], {"3": 5})
        self.assertEqual(t["model_trailing_before_first_send_hist"], {"0": 5})
        self.assertEqual(len(t["model_minus_b1_end_ms_by_index"]), 4)
        self.assertFalse(any(out["flag_mismatches"].values()))
        self.assertEqual(out["client"]["first_flight_uplink_bytes"]["mean"], 2562 + 4 * 1332)

    def test_unjoinable_segment_keeps_raw_data(self):
        seg = next(s for s in self.rec["segments"] if s["arm"] == "pad")
        seg["server_new_conns"] = seg["server_new_conns"][:4]
        out = P.summarize_arm("pad", self.cell, [self.blk], {0: self.rec})
        j = out["joined"]
        self.assertEqual(j["segments_joined"], 0)
        self.assertIn("server connections 4 != client rows 5", j["segments_excluded"][0]["reason"])
        un = out["per_connection"]["unjoined_segments"][0]
        self.assertEqual((len(un["rows"]), len(un["server_conns"])), (5, 4))
        self.assertEqual(out["server"]["conns_with_tx"], 4)

    def test_failures_are_imputed(self):
        seg = next(s for s in self.rec["segments"] if s["arm"] == "a013")
        seg["rows"][0] = fake_row(0, "a013", 10000.0, ok=False)
        seg["rows"] = seg["rows"][:4]
        seg["client_err"] = "exit 1"
        out = P.summarize_arm("a013", self.cell, [self.blk], {0: self.rec})
        self.assertEqual((out["ok"], out["failed"], out["missing"], out["timeouts"]), (3, 1, 1, 1))
        self.assertAlmostEqual(out["mean_planned_imputed_ms"], (3 * 121.0 + 2 * 10000.0) / 5)
        self.assertAlmostEqual(out["one_rtt_rate"], 3 / 5)

    def test_finalize_writes_a_labelled_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(P.B, "STATE", tmp), patch.object(P.B, "RESULTS", tmp):
                paths = P.paths("smoke")
                jr = Journal(paths["journal"], "fp")
                for b in self.plan["schedule"]:
                    blk_rec = fake_block(b, self.shapes, self.ms)
                    jr.record(P.unit_key("smoke", b["cell"], b["block"]), blk_rec)
                meta = {"fp": "fp", "starts": [{"binaries": {"g2": {"sha256": "a"},
                                                             "g3b": {"sha256": "b"}},
                                                "quicbed_sources_sha256": {"x": "1"}}],
                        "finished": {"quicbed_sources_sha256": {"x": "1"}}}
                rep = P.finalize(self.plan, meta, jr, paths)
                with open(paths["result"], encoding="utf-8") as f:
                    saved = json.load(f)
        self.assertEqual(saved["label"], "development (not confirmatory)")
        self.assertFalse(saved["confirmatory"])
        self.assertEqual(len(saved["cells"]), 4)
        self.assertTrue(all(c["blocks_done"] == 1 for c in saved["cells"]))
        self.assertTrue(saved["integrity"]["binaries_constant"])
        self.assertTrue(saved["integrity"]["quicbed_sources_unchanged"])
        self.assertEqual(saved["integrity"]["missing_trials"], 0)
        self.assertEqual(rep["cells"][0]["arms"]["pad"]["joined"]["connections"], 5)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            P.print_summary(rep)
        self.assertIn("development (not confirmatory)", buf.getvalue())


class SafetyTests(unittest.TestCase):
    @pytest.mark.historical(reason='requires the enabled historical runner; gen33 intentionally refuses legacy execution')
    def test_dry_run_writes_nothing(self):
        real = {m: P.paths(m) for m in ("run", "smoke")}
        exist_before = {m: {k: os.path.exists(v) for k, v in p.items()} for m, p in real.items()}
        listing = {d: sorted(x for x in os.listdir(d) if x.startswith("g31_probe"))
                   for d in (P.B.STATE, P.B.RESULTS)}
        with tempfile.TemporaryDirectory() as tmp:
            work = os.path.join(tmp, "work")
            buf = io.StringIO()
            with patch.object(P.B, "STATE", tmp), patch.object(P.B, "RESULTS", tmp), \
                    patch.object(P, "WORK", work), contextlib.redirect_stdout(buf):
                rc = P.main(["--dry-run"])
            self.assertEqual(rc, 0)
            self.assertEqual(os.listdir(tmp), [])
        out = buf.getvalue()
        self.assertIn("development (not confirmatory)", out)
        self.assertIn("plan for", out)
        self.assertIn("--install-only && unshare -Urnm python3 -u experiments/g31_probe.py --run",
                      out)
        self.assertEqual({m: {k: os.path.exists(v) for k, v in p.items()}
                          for m, p in real.items()}, exist_before)
        self.assertEqual({d: sorted(x for x in os.listdir(d) if x.startswith("g31_probe"))
                          for d in listing}, listing)

    @pytest.mark.historical(reason='requires the enabled historical runner; gen33 intentionally refuses legacy execution')
    def test_live_refuses_off_linux(self):
        if sys.platform.startswith("linux"):
            self.skipTest("Linux host")
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            rc = P.main(["--run"])
        self.assertEqual(rc, 2)
        self.assertIn("wsl -d Ubuntu", buf.getvalue())

    def test_busy_sees_another_probe_but_not_a_dry_run(self):
        table = [{"pid": 900, "ppid": 1, "comm": "python3",
                  "argv": ["python3", "-u", "experiments/g31_probe.py", "--run"]},
                 {"pid": 901, "ppid": 1, "comm": "python3",
                  "argv": ["python3", "experiments/g31_probe.py", "--dry-run"]}]
        with patch.object(G, "busy_processes", return_value=[]), \
                patch.object(G, "_proc_table", return_value=table), \
                patch.object(G, "_lineage", return_value=set()):
            found = P.busy()
        self.assertEqual(len(found), 1)
        self.assertIn("pid 900", found[0])

    def test_binary_report_flags_foreign_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            g2 = os.path.join(tmp, "g2")
            g3 = os.path.join(tmp, "g3b")
            for p, data in ((g2, b"not frozen"), (g3, b"g3b build")):
                with open(p, "wb") as f:
                    f.write(data)
            with open(g3 + ".srcsha", "w", encoding="utf-8", newline="\n") as f:
                f.write(P.STAGE2_G3B_SRCSHA + "\n")
            with patch.dict(P.BINS, {"g2": g2, "g3b": g3}):
                rep, problems, warnings = P.binary_report()
        self.assertTrue(any("not the frozen" in p for p in problems))
        self.assertTrue(rep["g3b"]["srcsha_matches"]["stage2_g3b_draw"])
        if rep["source_fingerprints"]["gen31_quicbed_now"] != P.STAGE2_G3B_SRCSHA:
            self.assertTrue(any("stage2_g3b_draw" in w for w in warnings))


class BlockRunnerTests(unittest.TestCase):
    def test_run_block_with_fake_processes(self):
        plan = P.build_plan("smoke")
        blk = plan["schedule"][0]
        cell = next(c for c in P.CELLS if c["cell"] == blk["cell"])
        state = {t: {"bytes_in": 0, "bytes_to_stack": 0, "conns": {}} for t in P.TAGS}
        clock = {"ns": 10 ** 12}

        class Proc:
            pid = 42

            def poll(self):
                return None

        def fake_start(cert):
            return {t: {"tag": t, "proc": Proc(), "pid": 42, "stats_path": "srv_%s" % t,
                        "argv": ["qamp"], "certsize": cert, "cert_der": cert} for t in P.TAGS}

        def fake_client(tag, flags, n, rate, stats_name="cli_stats.json"):
            rows = []
            for i in range(n):
                clock["ns"] += 300_000_000
                key = "initial:%d" % clock["ns"]
                state[tag]["conns"][key] = fake_conn(i, clock["ns"], ONE_RTT_SIZES, ONE_RTT_TL,
                                                     ONE_RTT_OFF)
                state[tag]["bytes_in"] += 9000
                state[tag]["bytes_to_stack"] += 8000
                arm = next((a for a in P.ARM_ORDER if P.arm_flags(a) == list(flags)), "none")
                rows.append(fake_row(i, arm, 121.0))
            return rows, {"bytes_orig": 1}, "", ["qamp"] + list(flags), 0

        def fake_read(path, tries=20):
            return json.loads(json.dumps(state[path[4:]]))

        netem = {"c2s": "x", "s2c": "y", "tc_c2s": "", "tc_s2c": "", "expected_tokens": {}}
        with patch.object(P, "set_netem", return_value=netem),                 patch.object(P, "start_servers", side_effect=fake_start),                 patch.object(P, "stop_servers") as stop,                 patch.object(P, "run_client", side_effect=fake_client),                 patch.object(G, "read_stats", side_effect=fake_read),                 patch.object(G, "load_processes", return_value=[]),                 patch.object(P.time, "sleep"):
            rec = P.run_block(blk, cell, 1, {"g2": "a", "g3b": "b"})
        self.assertEqual(rec["err"], "")
        self.assertTrue(S.block_complete(rec, blk))
        self.assertEqual(rec["label"], P.LABEL)
        self.assertEqual(set(rec["warmup"]), set(P.TAGS))
        stop.assert_called_once()
        for seg in rec["segments"]:
            self.assertEqual(len(seg["server_new_conns"]), 5)
            self.assertEqual(seg["other_server_new_conns"], 0)
            self.assertTrue(all("tx_sizes" in c and "conn_key" in c
                                for c in seg["server_new_conns"]))
            self.assertEqual(seg["server_delta"]["bytes_in"], 5 * 9000)
        out = P.summarize_arm("a104", cell, [blk], {0: rec})
        self.assertEqual(out["joined"]["connections"], 5)
        self.assertEqual(out["one_rtt_rate"], 1.0)

    def test_run_block_reports_a_server_that_does_not_start(self):
        plan = P.build_plan("smoke")
        blk = plan["schedule"][0]
        cell = next(c for c in P.CELLS if c["cell"] == blk["cell"])
        with patch.object(P, "set_netem", return_value={"expected_tokens": {}}),                 patch.object(P, "start_servers", side_effect=RuntimeError("no READY")),                 patch.object(G, "load_processes", return_value=[]):
            rec = P.run_block(blk, cell, 1, {})
        self.assertIn("server start failed: no READY", rec["err"])
        self.assertFalse(S.block_complete(rec, blk))


class DevCellsTests(unittest.TestCase):
    @pytest.mark.historical(reason='requires historical sealed protocol, prediction or development-cell files absent from gen33')
    def test_manifest_matches_the_runner_schema(self):
        data = json.loads((ROOT / "g3" / "dev_cells_stage3.json").read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], "padfec3.stage3_dev_cells.v1")
        cells = data["cells"]
        self.assertEqual(len(cells), len(set(cells)))
        grid = {"h_c%d_r%d_u%d" % (c, r, u) for c in (6000, 8000, 10000, 12000, 14000)
                for r in (20, 80, 120) for u in (0, 1, 5, 10)}
        self.assertLessEqual(set(cells), grid)
        self.assertLessEqual({"h_c8000_r120_u5", "h_c6000_r80_u10", "h_c6000_r80_u0",
                              "h_c6000_r120_u0"}, set(cells))
        probe = {c["h_cell"] for c in P.CELLS if c["h_cell"]}
        self.assertLessEqual(probe, set(cells))
        self.assertIn("note", data)


if __name__ == "__main__":
    unittest.main()
