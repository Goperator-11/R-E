import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import g3_stage0 as S
import g3bed as G
import padbed as B
from _journal import Journal

MS = {
    "bigcert_2": {"v2m1": 122.0, "v2m3": 132.0, "v3trm3": 127.0, "creditl3": 90.0, "m4L3": 80.0},
    "bigcert_15": {"v2m1": 134.0, "v2m3": 138.0, "v3trm3": 132.0, "creditl3": 155.0,
                   "m4L1": 131.0, "m4L3": 114.0},
    "rtt200_15": {"v2m3": 240.0, "v3trm3": 239.0, "m4L1": 237.0, "m4L2": 218.0, "creditl2": 388.0},
    "mbps2_15": {"v2m3": 83.0, "v3trm3": 82.0, "m4L2": 80.0},
}


def fake_row(i, arm, ms, ok=True):
    a = S.ARMS[arm]
    row = {"i": i, "ms": ms, "ok": ok, "group": S.GROUP,
           "first_flight_datagrams": 2, "first_flight_bytes": 2 * S.NOMINAL_W,
           "first_flight_parity_dgrams": a["m"],
           "first_flight_parity_bytes": a["m"] * S.NOMINAL_PARITY,
           "m_used": a["m"], "server_bytes": 7000, "parity_sent": a["m"]}
    if not ok:
        row["err"] = "timeout: handshake did not complete in time"
    if a["bin"] == "g3":
        row.update(layout="v3", lead=a["lead"], first_flight_lead_dgrams=a["lead"])
    return row


def fake_segment(arm, n, pos, ms, legacy_credit=False, fail_first=False):
    a = S.ARMS[arm]
    rows = [fake_row(i, arm, ms + (i % 3), ok=not (fail_first and i == 0)) for i in range(n)]
    credit = n * (min(a["lead"], 1) if legacy_credit else a["lead"])
    delta = {"parities": n * a["m"], "credit_parities": credit, "recover_crc_fail": 0,
             "bytes_in": 100 * n, "bytes_to_stack": 90 * n}
    if a["bin"] == "g3":
        delta["credit_parities_v3"] = credit
    conns = [{"tx_dgrams": 5, "beff_credit": a["lead"], "beff_stack": 6553, "beff_phys": 6553,
              "first_rx_ns": 10, "first_tx_ns": 2000010, "stack_bytes": 9000,
              "rx_bytes": 9500} for _ in range(n)]
    return {"arm": arm, "pos": pos, "bin": a["bin"], "port": G.PORTS[a["bin"]],
            "argv": [], "rc": 0, "err": "", "n_planned": n, "n_rows": n, "rows": rows,
            "client_stats": {"parity_sent": n * a["m"], "bytes_orig": n * 2 * S.NOMINAL_W,
                             "bytes_parity": n * a["m"] * S.NOMINAL_PARITY},
            "server_delta": delta, "server_after": {"bytes_in": 10, "bytes_to_stack": 9},
            "server_new_conns": conns, "other_server_delta": {}}


def fake_block(blk, legacy_credit=False, fail_first=False):
    segs = [fake_segment(arm, blk["sizes"][arm], pos, MS[blk["cell"]][arm],
                         legacy_credit=legacy_credit and arm == "m4L3",
                         fail_first=fail_first and pos == 0)
            for pos, arm in enumerate(blk["order"])]
    return {"cell": blk["cell"], "block": blk["block"], "rotation": blk["rotation"],
            "order": blk["order"], "sizes": blk["sizes"], "attempt": 1,
            "netem": {"c2s": "x"}, "servers": {"g2": {"cert_der": 16000}, "g3": {"cert_der": 16000}},
            "segments": segs, "load_processes": [], "bins_sha256": {"g2": "a", "g3": "b"},
            "runner_sha256": "r", "err": ""}


class Stage0PlanTests(unittest.TestCase):
    def test_full_plan_follows_sealed_protocol_section_8(self):
        plan = S.build_plan("full")
        self.assertEqual(len(plan["schedule"]), 70)
        self.assertEqual(sum(n for c in plan["cells"] for _a, n in c["arms"]), 12800)
        cycles = {"bigcert_2": 10, "bigcert_15": 20, "rtt200_15": 20, "mbps2_15": 20}
        for cell in plan["cells"]:
            blocks = [b for b in plan["schedule"] if b["cell"] == cell["cell"]]
            arms = [a for a, _n in cell["arms"]]
            self.assertEqual(len(blocks), cycles[cell["cell"]])
            self.assertEqual(cell["latin_closed"], len(blocks) % len(arms) == 0)
            for arm, n in cell["arms"]:
                self.assertEqual(sum(b["sizes"][arm] for b in blocks), n)
                self.assertEqual({b["sizes"][arm] for b in blocks},
                                 {20 if arm == "creditl2" else 40})
                positions = Counter(b["order"].index(arm) for b in blocks)
                self.assertEqual(set(positions), set(range(len(arms))))
                self.assertLessEqual(max(positions.values()) - min(positions.values()), 1)
                if cell["latin_closed"]:
                    self.assertEqual(set(positions.values()), {len(blocks) // len(arms)})
            for i, b in enumerate(blocks):
                r = i % len(arms)
                self.assertEqual(b["order"], arms[r:] + arms[:r])

    def test_plan_matches_sealed_predictions_and_seal_holds(self):
        self.assertEqual(S.sealed_plan_check(S.build_plan("full")), [])
        self.assertTrue(S.seal_check()["ok"])
        cond = S.CONDS["bigcert"]
        self.assertAlmostEqual(S.nominal_threshold(3, cond), 101.212)
        self.assertAlmostEqual(S.nominal_threshold(0, cond), 85.24)
        self.assertAlmostEqual(S.nominal_threshold(2, S.CONDS["rtt200"]), 320.888)

    def test_requested_arm_sets_and_counts(self):
        plan = S.build_plan("full")
        got = {c["cell"]: dict(c["arms"]) for c in plan["cells"]}
        self.assertEqual(got["bigcert_2"], {"v2m1": 400, "v2m3": 400, "v3trm3": 400,
                                            "creditl3": 400, "m4L3": 400})
        self.assertEqual(got["bigcert_15"], {a: 800 for a in ("v2m1", "v2m3", "v3trm3",
                                                              "creditl3", "m4L1", "m4L3")})
        self.assertEqual(got["rtt200_15"], {"v2m3": 800, "v3trm3": 800, "m4L1": 800,
                                            "m4L2": 800, "creditl2": 400})
        self.assertEqual(got["mbps2_15"], {"v2m3": 800, "v3trm3": 800, "m4L2": 800})

    def test_smoke_plan_is_five_per_arm_per_cell(self):
        plan = S.build_plan("smoke")
        self.assertEqual(len(plan["schedule"]), 4)
        for b in plan["schedule"]:
            self.assertEqual(set(b["sizes"].values()), {5})

    def test_arm_flags_match_shared_spec(self):
        self.assertEqual(S.ARMS["v3trm3"]["extra"], ["-layout", "v3", "-lead", "1"])
        self.assertEqual((S.ARMS["creditl3"]["m"], S.ARMS["creditl3"]["extra"][-1]), (3, "3"))
        self.assertEqual((S.ARMS["creditl2"]["m"], S.ARMS["creditl2"]["extra"][-1]), (2, "2"))
        for arm, lead in (("m4L1", "1"), ("m4L2", "2"), ("m4L3", "3")):
            self.assertEqual((S.ARMS[arm]["m"], S.ARMS[arm]["extra"]),
                             (4, ["-layout", "v3", "-lead", lead]))
        self.assertEqual({a: S.ARMS[a]["bin"] for a in S.ARMS if a.startswith("v2")},
                         {"v2m1": "g2", "v2m3": "g2"})
        self.assertTrue(all(v["bin"] == "g3" for a, v in S.ARMS.items()
                            if not a.startswith("v2")))
        self.assertEqual(G.PORTS, {"g2": 44433, "g3": 44434})
        self.assertNotIn("/tmp/qamp", set(G.BINS.values()))

    def test_conditions_match_p17(self):
        chk = S.p17_check()
        self.assertTrue(chk["ok"], chk["differences"])
        self.assertEqual(chk["p17_conds"]["큰cert"]["cert"], 16000)
        self.assertEqual(chk["p17_conds"]["RTT200"]["rtt_ms"], 200.0)
        self.assertEqual(chk["p17_conds"]["2Mbps"]["uplink_policy_mbps"], 2.0)

    def test_netem_spec_is_p17s(self):
        spec = G.netem_specs(25.0, 2.0, 2.0)
        self.assertEqual(spec["c2s"], B._netem_spec(25.0, 2.0, 1.0, 2.0))
        self.assertEqual(spec["c2s"], "netem delay 25.000ms rate 2mbit loss 2.0000%")
        self.assertEqual(spec["s2c"], "netem delay 25.000ms")

    def test_pre_decision_bytes_and_threshold(self):
        cond = S.CONDS["mbps2"]
        row = fake_row(0, "v2m3", 70.0)
        row.pop("first_flight_lead_dgrams", None)
        self.assertEqual(S.pre_decision_bytes(row, 1), 3891)
        self.assertAlmostEqual(S.tau_ms(3891, 2.0), 15.564)
        self.assertAlmostEqual(S.one_rtt_threshold(row, 1, cond), 75.0 + 15.564)
        self.assertEqual(S.pre_decision_bytes(fake_row(0, "m4L3", 80.0), 3), 6553)
        self.assertEqual(S.pre_decision_bytes(fake_row(0, "v2m1", 80.0), 0), 2560)

    def test_measurement_process_pattern(self):
        for s in ("experiments/p17_adaptive_value.py", "/mnt/c/dev/pq_afec/experiments/fixloop.py",
                  "experiments/loop2.py", "experiments/g3_stage0.py", "experiments/p21_gencompare.py"):
            self.assertTrue(G.MEASURE_RE.search(s), s)
        for s in ("experiments/padbed.py", "experiments/blockstat.py", "tests/test_x.py"):
            self.assertFalse(G.MEASURE_RE.search(s), s)

    def test_cli_requires_explicit_mode(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                S.main([])

    def test_dry_run_writes_nothing(self):
        before = sorted(os.listdir(B.RESULTS)), sorted(os.listdir(B.STATE))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(S.main(["--dry-run"]), 0)
        self.assertEqual(before, (sorted(os.listdir(B.RESULTS)), sorted(os.listdir(B.STATE))))
        self.assertIn("schedule full: 70 blocks, 12800 connections", out.getvalue())
        self.assertIn("plan vs sealed predictions (arms, n, conditions, 1-RTT cutoffs): match",
                      out.getvalue())


class Stage0ReportTests(unittest.TestCase):
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

    def build(self, legacy_credit=False, fail_first=False):
        plan = S.build_plan("full")
        jr = Journal(self.P["journal"], "fp")
        for blk in plan["schedule"]:
            rec = fake_block(blk, legacy_credit=legacy_credit, fail_first=fail_first)
            self.assertTrue(S.block_complete(rec, blk))
            jr.record(S.unit_key("full", blk["cell"], blk["block"]), rec)
        meta = {"fp": "fp", "plan": plan,
                "starts": [{"binaries": {"g2": {"sha256": "a"}, "g3": {"sha256": "b"}},
                            "quicbed_sources_sha256": {"qamp.go": "x"}}],
                "finished": {"quicbed_sources_sha256": {"qamp.go": "x"}}}
        jr2 = Journal(self.P["journal"], "fp")
        return S.finalize(plan, meta, jr2, self.P)

    def test_mechanism_checks_pass_on_synthetic_v3_server(self):
        rep = self.build()
        mc = rep["mechanism_checks"]
        self.assertTrue(mc["M1"]["pass"], json.dumps(mc["M1"], default=str)[:2000])
        self.assertEqual(set(mc["M1"]["c_parts"]), {"m4L3_bound_ok", "m4L3_v3_consistent",
                                                    "m4L3_flag_mismatches_zero"})
        self.assertTrue(mc["M1"]["c_supporting"]["creditl3_all_parities_credited"])
        self.assertTrue(mc["M2"]["pass"])
        self.assertTrue(mc["M3"]["pass"])
        self.assertAlmostEqual(mc["M2"]["diff_ms"], 5.0)
        self.assertAlmostEqual(mc["M3"]["diff_ms"], 22.0)
        self.assertAlmostEqual(mc["M4"]["bigcert_15"]["fec_share_ms"], 41.0)
        cell = {c["cell"]: c for c in rep["cells"]}["bigcert_2"]
        self.assertEqual(cell["arms"]["m4L3"]["one_rtt_rate"], 1.0)
        self.assertEqual(cell["arms"]["v2m1"]["n_requested"], 400)
        self.assertEqual(len(cell["arms"]["v2m1"]["trials"]["ms"]), 400)
        self.assertEqual(rep["integrity"]["crc_fail_total"], 0)
        self.assertTrue(rep["integrity"]["binaries_constant"])
        self.assertTrue(rep["integrity"]["quicbed_sources_unchanged"])
        self.assertEqual(rep["integrity"]["flag_mismatches"], {})
        with open(self.P["result"], encoding="utf-8") as f:
            self.assertEqual(json.load(f)["schema"], "g3_stage0.result.v1")

    def test_legacy_credit_rule_fails_m1c(self):
        rep = self.build(legacy_credit=True)
        m1 = rep["mechanism_checks"]["M1"]
        self.assertFalse(m1["c_parts"]["m4L3_bound_ok"])
        self.assertFalse(m1["pass"])

    def test_failures_are_imputed_at_timeout(self):
        rep = self.build(fail_first=True)
        cell = {c["cell"]: c for c in rep["cells"]}["bigcert_2"]
        first = [b for b in S.build_plan("full")["schedule"] if b["cell"] == "bigcert_2"]
        fails = sum(1 for b in first if b["order"][0] == "v2m1")
        v = cell["arms"]["v2m1"]
        self.assertEqual(v["failed"], fails)
        self.assertEqual(v["timeouts"], fails)
        oks = [ms for ms, ok in zip(v["trials"]["ms"], v["trials"]["ok"]) if ok]
        self.assertAlmostEqual(v["mean_planned_imputed_ms"],
                               (sum(oks) + S.IMPUTE_MS * fails) / 400)

    def test_incomplete_block_is_not_complete(self):
        blk = S.build_plan("smoke")["schedule"][0]
        rec = fake_block(blk)
        self.assertTrue(S.block_complete(rec, blk))
        rec["segments"][1]["rows"].pop()
        self.assertFalse(S.block_complete(rec, blk))
        rec = fake_block(blk)
        rec["segments"][0]["err"] = "exit 1"
        self.assertFalse(S.block_complete(rec, blk))
        rec = fake_block(blk)
        rec["segments"] = rec["segments"][:-1]
        self.assertFalse(S.block_complete(rec, blk))
        rec = fake_block(blk)
        rec["segments"][1]["rows"] = rec["segments"][1]["rows"][:2]
        rec["segments"][1]["client_err"] = "exit 2: panic"
        self.assertTrue(S.block_complete(rec, blk))
        rec["segments"][1]["rows"] = rec["segments"][1]["rows"] * 4
        self.assertFalse(S.block_complete(rec, blk))

    def test_short_client_output_is_imputed_and_excluded_from_bound(self):
        plan = S.build_plan("full")
        jr = Journal(self.P["journal"], "fp")
        for blk in plan["schedule"]:
            rec = fake_block(blk)
            if blk["cell"] == "bigcert_2" and blk["block"] == 0:
                seg = next(s for s in rec["segments"] if s["arm"] == "m4L3")
                seg["rows"] = seg["rows"][:10]
                seg["n_rows"] = 10
                seg["rc"] = 2
                seg["client_err"] = "exit 2: panic"
                seg["client_stats"] = {}
                seg["server_delta"]["credit_parities"] = 0
                rec["client_errors"] = [{"arm": "m4L3", "rc": 2, "err": "exit 2: panic",
                                         "n_rows": 10, "n_planned": 40}]
            self.assertTrue(S.block_complete(rec, blk))
            jr.record(S.unit_key("full", blk["cell"], blk["block"]), rec)
        meta = {"fp": "fp", "plan": plan,
                "starts": [{"binaries": {"g2": {"sha256": "a"}, "g3": {"sha256": "b"}},
                            "quicbed_sources_sha256": {"qamp.go": "x"}}],
                "finished": {"quicbed_sources_sha256": {"qamp.go": "x"}}}
        rep = S.finalize(plan, meta, Journal(self.P["journal"], "fp"), self.P)
        v = {c["cell"]: c for c in rep["cells"]}["bigcert_2"]["arms"]["m4L3"]
        self.assertEqual(v["missing"], 30)
        self.assertEqual(v["n_returned"], 370)
        oks = [ms for ms, ok in zip(v["trials"]["ms"], v["trials"]["ok"]) if ok]
        self.assertAlmostEqual(v["mean_planned_imputed_ms"],
                               (sum(oks) + S.IMPUTE_MS * 30) / 400)
        self.assertAlmostEqual(v["one_rtt_rate"], 370 / 400)
        lc = v["server"]["lead_credit"]
        self.assertIsNone(lc["per_segment"][0]["bound_ok"])
        self.assertTrue(lc["bound_ok"])
        self.assertEqual(rep["integrity"]["client_error_segments"], 1)
        self.assertEqual(rep["integrity"]["missing_trials"], 30)


class FakeProc:
    def __init__(self, owner=None):
        self.owner = owner

    def poll(self):
        return 1 if self.owner is not None and self.owner.dead else None


class Stage0LiveFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "results"))
        os.makedirs(os.path.join(self.tmp, "state"))
        self.P = {"journal": os.path.join(self.tmp, "state", "j.jsonl"),
                  "meta": os.path.join(self.tmp, "state", "m.json"),
                  "status": os.path.join(self.tmp, "state", "s.json"),
                  "incidents": os.path.join(self.tmp, "state", "i.jsonl"),
                  "result": os.path.join(self.tmp, "results", "r.json")}
        self.calls = []
        self.fail_calls = set()
        self.die_calls = set()
        self.dead = False
        self.validated = []
        self.busy_after = None
        self.counter = {"g2": 0, "g3": 0}
        self.real_sha = G.sha256_or_none

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fake_client(self, tag, group, n, fec, m, gap_ms, timeout_s, expect_k, uplink, extra=()):
        self.calls.append((tag, n, m, tuple(extra)))
        arm = next(a for a, v in S.ARMS.items() if v["bin"] == tag and v["m"] == m
                   and list(v["extra"]) == list(extra))
        self.counter[tag] += n
        if len(self.calls) in self.die_calls:
            self.dead = True
        if len(self.calls) in self.fail_calls:
            return [fake_row(0, arm, 100.0)], {}, "exit 1: boom", ["x"], 1
        rows = [fake_row(i, arm, 100.0) for i in range(n)]
        return rows, {"parity_sent": n * m}, "", ["x"], 0

    def fake_validate(self, tag, fec, m, extra=()):
        self.validated.append((tag, fec, m, tuple(extra)))
        return True, ["x"], ""

    def fake_stats(self, path):
        tag = "g2" if path.endswith("srv_g2.json") else "g3"
        c = self.counter[tag]
        return {"parities": c, "credit_parities": c, "bytes_in": 10 * c,
                "bytes_to_stack": 9 * c, "conns": {}}

    def fake_busy(self, allowed=()):
        if self.busy_after is not None and len(self.calls) >= self.busy_after:
            return ["qamp pid 1 (pgrep -x qamp)"]
        return []

    def sha(self, path):
        if path == G.BINS["g2"]:
            return "a"
        if path == G.BINS["g3"]:
            return "b"
        return self.real_sha(path)

    def run_live(self, mode="smoke"):
        return self.run_live_inner(mode, validate=self.fake_validate)

    def run_live_inner(self, mode="smoke", validate=None):
        binrep = {"g2": {"exists": True, "sha256": "a", "path": G.BINS["g2"]},
                  "g3": {"exists": True, "sha256": "b", "path": G.BINS["g3"]}}
        def server(tag, cert, fec="on", extra=()):
            self.dead = False
            return {"tag": tag, "proc": FakeProc(self), "pid": 100 + len(tag), "certsize": cert,
                    "cert_der": cert, "argv": [], "stats_path": "/x/srv_%s.json" % tag}

        out = io.StringIO()
        patches = [
            patch.object(sys, "platform", "linux"),
            patch.object(S.B, "harden"),
            patch.object(S.B, "require_root"),
            patch.object(S.signal, "signal"),
            patch.object(S, "paths", lambda m: self.P),
            patch.object(G, "busy_processes", self.fake_busy),
            patch.object(G, "load_processes", lambda: []),
            patch.object(G, "binary_report", lambda: (binrep, [])),
            patch.object(G, "flag_report", lambda rep: ({}, [])),
            patch.object(G, "environment", lambda: {"quicbed_sources_sha256": {}}),
            patch.object(G, "quicbed_sources", lambda: ({}, "x")),
            patch.object(G, "setup"),
            patch.object(G, "start_server", server),
            patch.object(G, "stop_server"),
            patch.object(G, "set_netem", lambda *a: {"tc_c2s": "", "tc_s2c": ""}),
            patch.object(G, "read_stats", self.fake_stats),
            patch.object(G, "run_client", self.fake_client),
            patch.object(G, "validate_client", validate or G.validate_client),
            patch.object(G, "sha256_or_none", self.sha),
            patch.object(S.time, "sleep"),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(io.StringIO()),
        ]
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            return S.live(mode), out.getvalue()

    def test_smoke_flow_runs_every_arm_once_and_resumes(self):
        rc, _ = self.run_live()
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.calls), 19)
        self.assertTrue(all(n == 5 for _t, n, _m, _e in self.calls))
        with open(self.P["result"], encoding="utf-8") as f:
            rep = json.load(f)
        self.assertEqual([c["cell"] for c in rep["cells"]],
                         ["bigcert_2", "bigcert_15", "rtt200_15", "mbps2_15"])
        self.assertIsNone(rep["mechanism_checks"])
        self.assertEqual(rep["integrity"]["journal_provenance"]["reused_units"], 0)
        g2_args = [c for c in self.calls if c[0] == "g2"]
        self.assertEqual(sorted({c[2] for c in g2_args}), [1, 3])
        self.assertTrue(all(c[3] == () for c in g2_args))
        rc, _ = self.run_live()
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.calls), 19)
        with open(self.P["result"], encoding="utf-8") as f:
            self.assertEqual(json.load(f)["integrity"]["journal_provenance"]["reused_units"], 4)

    def test_server_death_retries_block_once(self):
        self.die_calls = {2}
        rc, _ = self.run_live()
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.calls), 21)
        with open(self.P["result"], encoding="utf-8") as f:
            rep = json.load(f)
        self.assertEqual(rep["integrity"]["attempts_gt_1"], 1)
        self.assertEqual(len(rep["integrity"]["incidents"]), 1)
        self.assertEqual(len(self.validated), 8)

    def test_client_crash_is_kept_as_imputed_data_without_retry(self):
        self.fail_calls = {2}
        rc, _ = self.run_live()
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.calls), 19)
        with open(self.P["result"], encoding="utf-8") as f:
            rep = json.load(f)
        self.assertEqual(rep["integrity"]["attempts_gt_1"], 0)
        self.assertEqual(rep["integrity"]["client_error_segments"], 1)
        self.assertEqual(rep["integrity"]["missing_trials"], 4)
        self.assertTrue(rep["integrity"]["incidents"][0]["kept_as_data"])
        arm = rep["cells"][0]["arms"][self.arm_of_call(2)]
        self.assertEqual((arm["n_returned"], arm["missing"]), (1, 4))
        self.assertAlmostEqual(arm["mean_planned_imputed_ms"], (100.0 + 4 * S.IMPUTE_MS) / 5)

    def arm_of_call(self, i):
        tag, _n, m, extra = self.calls[i - 1]
        return next(a for a, v in S.ARMS.items() if v["bin"] == tag and v["m"] == m
                    and tuple(v["extra"]) == extra)

    def test_client_exec_failure_is_infrastructure(self):
        real = self.fake_client

        def exec_fail(tag, group, n, fec, m, gap_ms, timeout_s, expect_k, uplink, extra=()):
            if len(self.calls) == 1:
                self.calls.append((tag, n, m, tuple(extra)))
                return [], {}, "exit 127: timeout: failed to run command", ["x"], 127
            return real(tag, group, n, fec, m, gap_ms, timeout_s, expect_k, uplink, extra)
        self.fake_client = exec_fail
        rc, _ = self.run_live()
        self.assertEqual(rc, 0)
        with open(self.P["result"], encoding="utf-8") as f:
            rep = json.load(f)
        self.assertEqual(rep["integrity"]["attempts_gt_1"], 1)
        self.assertEqual(rep["integrity"]["client_error_segments"], 0)

    def test_two_failures_abort_and_keep_finished_blocks(self):
        self.die_calls = {6, 7}
        rc, _ = self.run_live()
        self.assertEqual(rc, 3)
        self.assertFalse(os.path.exists(self.P["result"]))
        with open(self.P["meta"], encoding="utf-8") as f:
            fp = json.load(f)["fp"]
        self.assertEqual(len(Journal(self.P["journal"], fp)), 1)

    def test_full_flow_runs_the_sealed_plan(self):
        rc, _ = self.run_live("full")
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.calls), 330)
        self.assertEqual(sum(n for _t, n, _m, _e in self.calls), 12800)
        with open(self.P["result"], encoding="utf-8") as f:
            rep = json.load(f)
        self.assertIsNotNone(rep["mechanism_checks"])
        self.assertTrue(rep["env_starts"][0]["seal_check"]["ok"])
        self.assertEqual(rep["env_starts"][0]["sealed_plan_differences"], [])

    def test_full_refuses_on_broken_seal(self):
        bad = {"path": "g3/SEAL_stage0.json", "ok": False, "changed": ["g3/PROTOCOL_stage0.md"],
               "missing": []}
        with patch.object(S, "seal_check", lambda: bad):
            rc, _ = self.run_live("full")
        self.assertEqual(rc, 2)
        self.assertEqual(self.calls, [])

    def test_rejected_arm_flags_refuse_before_measuring(self):
        def reject(tag, fec, m, extra=()):
            return (m != 4), ["x"], "layout: -layout v3 needs lead <= m <= 15"
        with patch.object(G, "validate_client", reject):
            rc, _ = self.run_live_inner("smoke")
        self.assertEqual(rc, 2)
        self.assertEqual(self.calls, [])

    def test_foreign_measurement_aborts_before_next_block(self):
        self.busy_after = 5
        rc, _ = self.run_live()
        self.assertEqual(rc, 3)
        with open(self.P["status"], encoding="utf-8") as f:
            self.assertEqual(json.load(f)["state"], "aborted")


class BinaryReportTests(unittest.TestCase):
    def test_g2_must_be_frozen_and_g3_must_match_current_sources(self):
        tmp = tempfile.mkdtemp()
        try:
            bins = {"g2": os.path.join(tmp, "g2", "qamp"), "g3": os.path.join(tmp, "g3", "qamp")}
            for tag, path in bins.items():
                os.makedirs(os.path.dirname(path))
                with open(path, "wb") as f:
                    f.write(tag.encode())
                os.chmod(path, 0o755)
            with open(bins["g3"] + ".srcsha", "w", encoding="utf-8") as f:
                f.write("old\n")
            with patch.object(G, "BINS", bins), \
                    patch.object(G, "quicbed_sources", lambda: ({}, "now")):
                rep, problems = G.binary_report()
                self.assertTrue(any("not the frozen" in p for p in problems))
                self.assertTrue(any("built from other sources" in p for p in problems))
                with open(bins["g3"] + ".srcsha", "w", encoding="utf-8") as f:
                    f.write("now\n")
                rep, problems = G.binary_report()
                self.assertFalse(any("g3" in p for p in problems), problems)
                self.assertEqual(rep["g3"]["source_fingerprint_now"], "now")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_build_style_fingerprint_matches_build_g3_formula(self):
        import hashlib
        qb = ROOT / "experiments" / "quicbed"
        names = sorted(n for n in os.listdir(qb)
                       if n.endswith(".go") or n in ("build.sh", "go.mod", "go.sum"))
        lines = "".join("%s %s\n" % (n, hashlib.sha256((qb / n).read_bytes()).hexdigest())
                        for n in names)
        self.assertEqual(G.quicbed_sources()[1], hashlib.sha256(lines.encode()).hexdigest())


if __name__ == "__main__":
    unittest.main()
