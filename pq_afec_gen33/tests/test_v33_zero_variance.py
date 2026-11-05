import datetime
import json
import math
from pathlib import Path
from statistics import NormalDist
import tempfile
import unittest

from experiments.v33 import bench_report, zero_variance as zv, v33fix_j6_rejudge as rejudge
from experiments.v33.worldsim import Action, World, WorldContext


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "g3" / "v33" / "V33FIX_J6_rejudge_v1.json"


def moments(mean, variance, n=100):
    return {"n": n, "mean_hct_ms": mean, "variance_hct_ms2": variance}


def run(seed, counts, mean=100.):
    total = sum(counts.values())
    return {"seed": seed, "n": total, "summary": {"mean_hct_ms": mean},
            "action_counts": [{"context_id": "c", "action": list(action), "n": n} for action, n in counts.items()]}


class ZeroVarianceRuleTests(unittest.TestCase):
    def test_rule_section_is_registered_and_tamper_evident(self):
        self.assertEqual(zv.check_rule(), zv.RULE_SECTION_SHA256)
        text = zv.RULES_PATH.read_text(encoding="utf-8")
        self.assertIn("860001", zv.rule_section())
        with tempfile.TemporaryDirectory() as folder:
            changed = Path(folder) / "rules.md"
            changed.write_text(text.replace("N=131072", "N=131073"), encoding="utf-8")
            self.assertNotEqual(zv.rule_section_sha256(changed), zv.RULE_SECTION_SHA256)
            with self.assertRaises(ValueError):
                zv.check_rule(changed)
            changed.write_text(text + "\n## extra\n", encoding="utf-8")
            self.assertEqual(zv.rule_section_sha256(changed), zv.RULE_SECTION_SHA256)
            changed.write_text(text.replace(zv.RULE_END, ""), encoding="utf-8")
            with self.assertRaises(ValueError):
                zv.rule_section(changed)

    def test_critical_uses_frozen_mc_confidence_and_family(self):
        self.assertEqual(zv.critical(116), NormalDist().inv_cdf(1 - 0.01 / 232))
        self.assertAlmostEqual(zv.critical(1), 2.5758293035489, places=10)
        for bad in (0, True, 1.5):
            with self.assertRaises(ValueError):
                zv.critical(bad)

    def test_interval_and_effective_width_cover_unpaired_interval(self):
        result = zv.interval(moments(10.5, 4.), moments(10., 1.), 4, paired_gap=0.3)
        z = NormalDist().inv_cdf(1 - 0.01 / 8)
        se = math.sqrt(4. / 100 + 1. / 100)
        self.assertEqual(result["status"], "resolved")
        self.assertAlmostEqual(result["unpaired_difference_ms"], 0.5, places=12)
        self.assertAlmostEqual(result["unpaired_se_ms"], se, places=12)
        lower, upper = result["unpaired_interval_ms"]
        self.assertAlmostEqual(lower, 0.5 - z * se, places=12)
        h = result["effective_gap_half_width_ms"]
        self.assertLessEqual(0.3 - h, lower + 1e-15)
        self.assertGreaterEqual(0.3 + h, upper - 1e-15)
        self.assertAlmostEqual(h, max(upper - 0.3, 0.3 - lower), places=15)

    def test_degenerate_unpaired_variance_stays_unresolved(self):
        for a, b in ((0., 1.), (1., 1e-21), (0., 0.)):
            result = zv.interval(moments(1., a), moments(0., b), 116, paired_gap=1.)
            with self.subTest(a=a, b=b):
                self.assertEqual(result["status"], "unresolved")
                self.assertIsNone(result["unpaired_interval_ms"])
                self.assertIsNone(result["effective_gap_half_width_ms"])

    def test_unpaired_evaluation_uses_independent_seeds_and_world_samples(self):
        context = dict(k=2, w=1280, p=0.08, rtt_ms=120, uplink_mbps=10, cert_bytes=6000)
        result = zv.unpaired_difference(context, (12, 0, 4), (7, 0, 4), 860901, 860902, samples=48, family=116, paired_gap=0.008)
        world = World(seed=860901)
        values = [world.sample(WorldContext(**context), Action(12, 0, 4), connection=i)["hct"] for i in range(48)]
        self.assertAlmostEqual(result["action"]["mean_hct_ms"], sum(values) / 48, places=9)
        self.assertEqual((result["action"]["seed"], result["reference"]["seed"]), (860901, 860902))
        with self.assertRaises(ValueError):
            zv.unpaired_difference(context, (12, 0, 4), (7, 0, 4), 860901, 860901, samples=4)
        with self.assertRaises(ValueError):
            zv.unpaired_difference(context, (7, 0, 4), (7, 0, 4), 860901, 860902, samples=4)

    def test_needs_resolution_only_for_distinct_null_zero_variance(self):
        base = {"action": [12, 0, 4], "reference_action": [7, 0, 4], "zero_observed_variance": True, "gap_half_width_ms": None}
        self.assertTrue(zv.needs_resolution(base))
        self.assertFalse(zv.needs_resolution(dict(base, reference_action=[12, 0, 4])))
        self.assertFalse(zv.needs_resolution(dict(base, zero_observed_variance=False)))
        self.assertFalse(zv.needs_resolution(dict(base, gap_half_width_ms=0.01)))

    def tables(self):
        return {("c", (12, 0, 4)): {"action": [12, 0, 4], "reference_action": [7, 0, 4], "mean_gap_ms": 0.008,
                                    "gap_half_width_ms": None, "zero_observed_variance": True, "uncertainty_resolved": False},
                ("c", (0, 2, 2)): {"action": [0, 2, 2], "reference_action": [7, 0, 4], "mean_gap_ms": 3.4,
                                   "gap_half_width_ms": 0.05, "zero_observed_variance": False, "uncertainty_resolved": True},
                ("c", (7, 0, 4)): {"action": [7, 0, 4], "reference_action": [7, 0, 4], "mean_gap_ms": 0.,
                                   "gap_half_width_ms": 0., "zero_observed_variance": True, "uncertainty_resolved": True}}

    def test_bound_uses_resolution_only_where_registered(self):
        candidate = [run(1, {(12, 0, 4): 10}), run(2, {(12, 0, 4): 9, (0, 2, 2): 1}), run(3, {(12, 0, 4): 10})]
        baseline = [run(s, {(0, 2, 2): 10}) for s in (1, 2, 3)]
        coefficients = zv.direct_coefficients(candidate, baseline)
        self.assertIsNone(zv.weighted_bound(coefficients, self.tables(), {}))
        bound = zv.weighted_bound(coefficients, self.tables(), {("c", (12, 0, 4)): 0.02})
        expected = abs(float(coefficients[("c", (12, 0, 4))])) * 0.02 + abs(float(coefficients[("c", (0, 2, 2))])) * 0.05
        self.assertAlmostEqual(bound, expected, places=15)
        row = zv.rejudged_comparison(candidate, baseline, self.tables(), {("c", (12, 0, 4)): 0.02}, 0.5)
        self.assertIsNone(row["original_shared_mc_bound_ms"])
        self.assertEqual(row["regression_gate"]["status"], "pass")
        self.assertLess(row["upper_bound_ms"], 0)
        self.assertEqual(row["z1_resolved_terms"], [["c", [12, 0, 4]]])

    def test_without_unresolved_terms_matches_frozen_direct_comparison(self):
        candidate = [run(1, {(0, 2, 2): 8, (7, 0, 4): 2}), run(2, {(0, 2, 2): 9, (7, 0, 4): 1}), run(3, {(0, 2, 2): 7, (7, 0, 4): 3})]
        baseline = [run(s, {(0, 2, 2): 10}) for s in (1, 2, 3)]
        frozen = bench_report.direct_comparison(candidate, baseline, self.tables())
        row = zv.rejudged_comparison(candidate, baseline, self.tables(), {}, 0.5)
        self.assertEqual(row["shared_mc_bound_ms"], frozen["shared_mc_bound_ms"])
        self.assertEqual(row["upper_bound_ms"], frozen["upper_bound_ms"])

    def test_rejudge_assignments_use_fresh_distinct_seeds(self):
        seeds = [s for row in rejudge.ASSIGNMENTS for s in row[3:]]
        self.assertEqual(len(seeds), len(set(seeds)))
        self.assertTrue(all(s >= zv.SEED_START for s in seeds))
        self.assertNotIn(850001, seeds)
        self.assertNotIn(840001, seeds)
        self.assertTrue(rejudge.PRIMARY <= set(rejudge.PAIRS))

    @unittest.skipUnless(RESULT.exists(), "rejudge result not present")
    def test_published_rejudge_is_consistent_with_rule(self):
        data = json.loads(RESULT.read_text(encoding="utf-8"))
        self.assertEqual(data["rule_section_sha256"], zv.RULE_SECTION_SHA256)
        written = datetime.datetime.fromisoformat(data["rule_document_mtime_utc"])
        started = datetime.datetime.fromisoformat(data["started_kst"])
        self.assertLess(written, started)
        for row in data["z1_evaluations"]:
            lower, upper = row["unpaired_interval_ms"]
            g, h = row["paired_gap_ms"], row["effective_gap_half_width_ms"]
            self.assertLessEqual(g - h, lower + 1e-12)
            self.assertGreaterEqual(g + h, upper - 1e-12)
            self.assertEqual(row["action_moments"]["n"], 131072)
            self.assertEqual(row["reference_moments"]["n"], 131072)
            self.assertEqual(row["critical"], zv.critical(116))
        cells = data["j6_adoption"]["primary_cells"]
        self.assertEqual(len(cells), 30)
        upper_ok = all(c["adjusted_upper_ms"] is not None and c["adjusted_upper_ms"] <= 0.5 for c in cells)
        decrease = [c for c in cells if c["candidate"] == "j6_c1" and c["adjusted_upper_ms"] < 0]
        self.assertEqual(data["j6_adoption"]["adopt_under_original_rule"], upper_ok and bool(decrease))
        self.assertFalse(data["j6_adoption"]["active_policy_changed"])
        for check in data["reproduction_checks"]:
            self.assertTrue(check["reproduced"])


if __name__ == "__main__":
    unittest.main()
