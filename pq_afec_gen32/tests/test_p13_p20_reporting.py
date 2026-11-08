import ast
import copy
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


EXPERIMENTS = Path(__file__).resolve().parents[1] / "experiments"


def functions_from(filename, names, **namespace):
    tree = ast.parse((EXPERIMENTS / filename).read_text(encoding="utf-8"))
    selected = [n for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name in names]
    if {n.name for n in selected} != set(names):
        raise AssertionError("requested pure functions missing")
    code = compile(ast.Module(body=selected, type_ignores=[]), filename, "exec")
    exec(code, namespace)
    return namespace


P13 = functions_from("p13_beff.py", {"cp_lower", "late_parity_assessment"},
                     math=math, LATE_CRED_MIN=0.99)
P16 = functions_from("p16_uplink.py", {"ips_evidence"}, W=1280, K=1)
P20 = functions_from("p20_residual.py", {"residual_report", "p16_pad_input"},
                     ALPHA=0.05)


def pair(verdict="부호일치", current=100, needed=50):
    return {"pair": "m1-m2", "verdict": verdict,
            "meas_delta_ms": 1.0, "model_delta_j_ms": 0.8,
            "ci95_half_ms": 0.1, "tail_share_of_delta": 0.0,
            "n_per_arm": current, "n_needed_per_arm": needed}


def condition(pairs=None, outside=True):
    return {"cond": "synthetic", "source": "p18",
            "arms": [{"arm": "m1", "model": {"j_ms": 50.0}, "class_residual": {
                "ontime": {"outside_ci": outside, "err_pp": 100.0}}}],
            "pairs": pairs if pairs is not None else [pair()]}


class LateParityCoverageTests(unittest.TestCase):
    def assess(self, n_req=600, n_ok=600, n_conns=600, credited=600, err=""):
        return P13["late_parity_assessment"](n_req, n_ok, n_conns, credited, err)

    def test_592_records_cannot_certify_all_600_trials(self):
        out = self.assess(n_conns=592, credited=592)
        self.assertEqual(out["n_missing_server"], 8)
        self.assertAlmostEqual(out["observed_cred_ci95_lo"], 0.05 ** (1 / 592))
        self.assertFalse(out["coverage_complete"])
        self.assertIsNone(out["cred_ci95_lo"])
        self.assertEqual(out["verdict"], "inconclusive")

    def test_complete_600_records_support_the_original_threshold(self):
        out = self.assess()
        self.assertTrue(out["coverage_complete"])
        self.assertEqual(out["verdict"], "refuted")
        self.assertGreater(out["cred_ci95_lo"], 0.99)

    def test_complete_small_sample_does_not_certify_99_percent(self):
        out = self.assess(24, 24, 24, 24)
        self.assertTrue(out["coverage_complete"])
        self.assertEqual(out["verdict"], "inconclusive")

    def test_missing_client_success_or_process_error_blocks_conclusion(self):
        for kw in ({"n_ok": 599}, {"err": "timeout"}, {"n_conns": 0, "credited": 0}):
            with self.subTest(kw=kw):
                self.assertEqual(self.assess(**kw)["verdict"], "inconclusive")

    def test_invalid_counts_cannot_look_complete(self):
        for kw in ({"n_req": 0}, {"n_req": True}, {"credited": 601},
                   {"n_conns": 601}, {"credited": -1}, {"n_ok": None}):
            with self.subTest(kw=kw):
                out = self.assess(**kw)
                self.assertFalse(out["coverage_complete"])
                self.assertIsNone(out["cred_ci95_lo"])

    def test_low_credit_also_requires_complete_coverage(self):
        self.assertEqual(self.assess(credited=0)["verdict"], "confirmed")
        self.assertEqual(self.assess(n_conns=592, credited=0)["verdict"], "inconclusive")


class ResidualReportingTests(unittest.TestCase):
    def test_outside_intervals_and_sign_flips_are_diagnostics_not_passes(self):
        out = P20["residual_report"]([condition([pair(verdict="부호반대")])])
        self.assertEqual((out["passed"], out["total"]), (3, 3))
        self.assertEqual(len(out["diagnostics"]), 2)
        self.assertIn("구간 밖 1 건 / 총 1 건", out["diagnostics"][0]["detail"])
        self.assertTrue(out["diagnostics"][1]["detail"].startswith("1 건"))
        for d in out["diagnostics"]:
            self.assertIsNone(d["ok"])
            self.assertFalse(d["gating"])
            self.assertEqual(d["status"], "diagnostic")
        self.assertFalse(out["classification_limits"]["same_event_definition_verified"])

    def test_existing_numeric_sample_shortage_rule_remains_a_failure(self):
        pairs = [pair(current=100, needed=101) for _ in range(18)]
        pairs.append(pair("판정불능", needed="분해능아래"))
        out = P20["residual_report"]([condition(pairs)])
        self.assertEqual((out["passed"], out["total"]), (2, 3))
        self.assertFalse(out["checks"][-1]["ok"])
        self.assertIn("모자란 쌍 18 개", out["checks"][-1]["detail"])
        self.assertIn("분해능아래 1", out["checks"][-1]["detail"])

    def test_missing_needed_sample_estimate_still_fails(self):
        out = P20["residual_report"]([condition([pair("판정불능", needed=None)])])
        self.assertFalse(out["checks"][1]["ok"])

    def test_empty_results_fail_presence_and_do_not_count_diagnostics(self):
        out = P20["residual_report"]([])
        self.assertFalse(out["checks"][0]["ok"])
        self.assertEqual(out["total"], 3)
        self.assertLess(out["passed"], out["total"])

    def test_report_does_not_rewrite_observations_or_model_values(self):
        conds = [condition()]
        before = copy.deepcopy(conds)
        P20["residual_report"](conds)
        self.assertEqual(conds, before)

    def test_unavailable_padding_model_is_visible_in_diagnostics(self):
        cond = condition()
        cond["arms"][0]["model"] = {"status": "unavailable", "err": "IPS evidence missing"}
        cond["arms"][0]["class_residual"] = {}
        out = P20["residual_report"]([cond])
        self.assertIn("IPS evidence missing", out["diagnostics"][-1]["detail"])
        self.assertIsNone(out["diagnostics"][-1]["ok"])
        self.assertEqual(out["total"], 3)


class FixedPaddingEvidenceTests(unittest.TestCase):
    def rows(self):
        return [{"ok": True, "ips_used": 1452, "ips_eff": 1452,
                 "first_flight_bytes": 1452, "first_flight_datagrams": 1,
                 "first_flight_parity_dgrams": 0} for _ in range(4)]

    def arm(self, rows=None):
        rows = self.rows() if rows is None else rows
        return {"arm": "pad", "n": 4, "ok": 4, "err": "",
                "ips_evidence": P16["ips_evidence"](rows, 1452, "off", 0, 4)}

    def test_historical_median_only_record_is_unavailable(self):
        out = P20["p16_pad_input"]({"ff_bytes_med": 1452, "added_bytes": 172})
        self.assertIn("model_input_error", out)
        self.assertNotIn("model_delta_per_dgram", out)

    def test_configured_and_observed_padding_agree(self):
        out = P20["p16_pad_input"](self.arm())
        self.assertEqual(out["model_delta_per_dgram"], 172)
        self.assertNotIn("model_input_error", out)

    def test_missing_capped_or_different_wire_configuration_is_unavailable(self):
        for field, value in (("ips_eff", None), ("ips_eff", 1280),
                             ("ips_used", 1500), ("first_flight_bytes", 1280),
                             ("first_flight_datagrams", 2),
                             ("first_flight_parity_dgrams", 1), ("ok", False)):
            with self.subTest(field=field):
                rows = self.rows()
                rows[0][field] = value
                out = P20["p16_pad_input"](self.arm(rows))
                self.assertIn("model_input_error", out)

    def test_missing_rows_cannot_be_hidden_by_summary_values(self):
        arm = self.arm(self.rows()[:-1])
        self.assertEqual(arm["ips_evidence"]["n_rows"], 3)
        self.assertIn("model_input_error", P20["p16_pad_input"](arm))

    def test_evidence_keeps_unsuccessful_rows_and_both_blocks(self):
        rows = self.rows()
        rows[0]["ok"] = False
        first = P16["ips_evidence"](rows[:2], 1452, "off", 0, 2)
        second = P16["ips_evidence"](rows[2:], 1452, "off", 0, 2)
        combined = P16["ips_evidence"](
            first["observations"] + second["observations"], 1452, "off", 0, 4)
        self.assertEqual(combined["observations"], rows)
        self.assertEqual(combined["n_req"], 4)

    def test_fixed_delta_is_scored_even_when_optimizer_does_not_enumerate_it(self):
        seen = {}

        def candidate(*args, **kwargs):
            seen["delta"] = args[2]
            return {"k": 1, "m": 0, "delta_per_dgram": args[2], "mode": "pad"}

        def cost(cand, *args, **kwargs):
            seen["scored_delta"] = cand["delta_per_dgram"]
            return {"j_ms": 50.1376, "base_ms": 50.0, "tx_ms": 0.1376}

        policy = SimpleNamespace(
            S0_BASE_MLKEM=1500, S0_BASE_X25519=500,
            C_PKT_POLICY_DEFAULT=40, QUICGO_MAX_IPS=1452,
            parity_datagram_bytes=lambda *args: 0,
            decide_v2=lambda **kwargs: {
                "choice": {"m": 0},
                "candidates": [{"mode": "none", "k": 1, "m": 0,
                                "delta_per_dgram": 0, "j_ms": 50.0}]},
            cost_of_v2=cost)
        quantum = SimpleNamespace(_candidate=candidate, bin_index=lambda *args: 3,
                                  P_SERVER=1280)
        f = functions_from("p20_residual.py", {"model_arm"}, POL=policy, QU=quantum,
                           measured_C=lambda group: (258, "synthetic"))["model_arm"]
        out = f("x25519", 2000, 50, 0, 1, 10, 0, delta_per_dgram=172)
        self.assertEqual(seen, {"delta": 172, "scored_delta": 172})
        self.assertEqual(out["j_ms"], 50.1376)
        self.assertEqual(out["fixed_delta_per_dgram"], 172)

    def test_fixed_padding_uses_real_policy_cost_without_importing_a_runner(self):
        sys.path.insert(0, str(EXPERIMENTS.parent))
        from padfec import policy, quantum
        f = functions_from("p20_residual.py", {"model_arm"}, POL=policy, QU=quantum,
                           measured_C=lambda group: (258, "synthetic"))["model_arm"]
        base = f("x25519", 2000, 50, 0, 1, 10, 0)
        padded = f("x25519", 2000, 50, 0, 1, 10, 0, delta_per_dgram=172)
        self.assertNotIn("err", padded)
        self.assertAlmostEqual(padded["j_ms"] - base["j_ms"], 172 * 8 / 10000)
        self.assertEqual(padded["P_ontime"], 1.0)
        self.assertEqual(padded["fixed_delta_per_dgram"], 172)


if __name__ == "__main__":
    unittest.main()
