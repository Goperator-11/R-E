import math
import unittest

from experiments.v33.bench_metrics import adaptation, evaluate_threshold, paired_summary, student_t_critical, summarize_run


class BenchmarkMetricTests(unittest.TestCase):
    def rows(self, phases):
        rows = []
        for phase, (p, estimates) in enumerate(phases):
            for phase_index, estimate in enumerate(estimates):
                rows.append({"index": len(rows), "phase": phase, "phase_index": phase_index,
                             "phase_p": p, "p_mean_pre": estimate, "S_hat_pre": None,
                             "action": [0, 0, 0], "context_id": str(phase), "hct_ms": 50.0,
                             "ok": True, "extra_server_bytes": 0, "extra_first_flight_bytes": 0,
                             "alarm_raised": [], "guard_alarm": False, "reeval": False,
                             "updated": True, "decision_why": "ej"})
        return rows

    def test_student_t_critical_known_degrees_of_freedom(self):
        self.assertAlmostEqual(student_t_critical(19), 2.093024054408263, places=10)
        self.assertAlmostEqual(student_t_critical(1), 1 / math.tan(math.pi * .025), places=10)
        self.assertAlmostEqual(student_t_critical(2), .95 * math.sqrt(2 / (1 - .95 ** 2)), places=10)
        self.assertAlmostEqual(student_t_critical(30, .99), 2.7499956535670305, places=9)

    def test_paired_interval_uses_twenty_seed_differences(self):
        result = paired_summary(range(20))
        self.assertEqual(result["n"], 20)
        self.assertEqual(result["df"], 19)
        self.assertEqual(result["mean"], 9.5)
        self.assertAlmostEqual(result["se"], math.sqrt(1.75))
        self.assertAlmostEqual(result["upper"], 9.5 + 2.093024054408263 * math.sqrt(1.75))

    def test_empty_and_single_seed_do_not_claim_zero_uncertainty(self):
        for values in ([], [4.0]):
            result = paired_summary(values)
            self.assertIsNone(result["lower"])
            self.assertIsNone(result["upper"])
            self.assertFalse(result["interval_available"])
        self.assertEqual(paired_summary([4.0])["mean"], 4.0)
        self.assertEqual(paired_summary([4.0, 4.0])["half_width"], 0)

    def test_pair_validation(self):
        for values in ([math.nan, 1.0], [math.inf], [True]):
            with self.assertRaises(ValueError):
                paired_summary(values)
        for confidence in (0, 1, -1, math.nan):
            with self.assertRaises(ValueError):
                paired_summary([1, 2], confidence)

    def test_threshold_preserves_oracle_uncertainty(self):
        result = evaluate_threshold(.05, .04, .06, .1, mc_bound=.02, selection_gap=.03)
        self.assertTrue(result["point_pass"])
        self.assertEqual(result["status"], "inconclusive")
        self.assertAlmostEqual(result["adjusted_lower"], .02)
        self.assertAlmostEqual(result["adjusted_upper"], .11)
        self.assertEqual(evaluate_threshold(.05, .04, .06, .1, selection_gap=None)["status"], "inconclusive")
        self.assertEqual(evaluate_threshold(.2, .18, .22, .1, selection_gap=None)["status"], "fail")

    def test_strict_and_inclusive_threshold_boundaries(self):
        self.assertEqual(evaluate_threshold(2, 2, 2, 2)["status"], "fail")
        self.assertEqual(evaluate_threshold(2, 2, 2, 2, inclusive=True)["status"], "pass")
        self.assertEqual(evaluate_threshold(.05, .04, .09, .1)["status"], "pass")
        self.assertEqual(evaluate_threshold(.05, None, None, .1)["status"], "inconclusive")
        with self.assertRaises(ValueError):
            evaluate_threshold(0, 2, 1, 3)
        with self.assertRaises(ValueError):
            evaluate_threshold(0, -1, 1, 3, mc_bound=-1)

    def test_absolute_bias_requires_interval_inside_both_limits(self):
        self.assertEqual(evaluate_threshold(-.003, -.004, -.002, .005, absolute=True)["status"], "pass")
        self.assertEqual(evaluate_threshold(0, -.006, .002, .005, absolute=True)["status"], "inconclusive")
        self.assertEqual(evaluate_threshold(-.01, -.012, -.008, .005, absolute=True)["status"], "fail")

    def test_high_phase_bias_uses_pre_values_and_last_window(self):
        rows = self.rows([(.02, [.02] * 3), (.15, [.3, .3, .16, .14]), (.02, [.02] * 2)])
        result = summarize_run(rows, {}, {"metrics": {"p_bias_high_phase_last_n": 2}})
        self.assertAlmostEqual(result["p_bias_high_phase"], 0)
        self.assertAlmostEqual(result["p_mae_high_phase"], .01)
        self.assertEqual(result["p_bias_high_phase_n"], 2)
        self.assertEqual(result["high_phase_p"], .15)

    def test_alarm_episode_denominator_excludes_only_cold_and_following_band(self):
        rows = self.rows([(.02, [.02] * 5), (.15, [.15] * 5)])
        rows[0]["alarm_raised"] = ["cold"]
        rows[4]["alarm_raised"] = ["a", "a", "b"]
        rows[5]["alarm_raised"] = ["change"]
        rows[7]["alarm_raised"] = ["c"]
        result = summarize_run(rows, {}, {"metrics": {"cold_alarm_exclusion": 2, "transition_alarm_exclusion": 2}})
        self.assertEqual(result["alarm_eligible_connections"], 6)
        self.assertEqual(result["alarm_episode_count"], 3)
        self.assertEqual(result["alarm_connections"], 2)
        self.assertEqual(result["alarm_rate_per_1000"], 500)

    def test_fresh_destinations_have_no_post_cold_alarm_denominator(self):
        rows = self.rows([(.02, [.13] * 150)])
        result = summarize_run(rows, {"reset_each_connection": True}, {})
        self.assertEqual(result["alarm_eligible_connections"], 0)
        self.assertIsNone(result["alarm_rate_per_1000"])

    def test_failure_cost_and_negative_server_difference_are_not_dropped(self):
        rows = self.rows([(.02, [.02, .02])])
        rows[0].update(ok=False, hct_ms=120000, extra_server_bytes=-100)
        rows[1].update(extra_server_bytes=20, extra_client_first_flight_bytes=1331)
        result = summarize_run(rows, {}, {})
        self.assertEqual(result["mean_hct_ms"], 60025)
        self.assertEqual(result["failure_count"], 1)
        self.assertEqual(result["failure_rate"], .5)
        self.assertEqual(result["mean_extra_server_bytes"], -40)
        self.assertEqual(result["mean_extra_client_first_flight_bytes"], 1331)

    def test_unchanged_action_run_is_not_called_stuck(self):
        rows = self.rows([(.02, [.02] * 3), (.15, [.15] * 3)])
        rows[0]["action"] = [0, 3, 1]
        result = summarize_run(rows, {}, {})
        self.assertEqual(result["longest_unchanged_action_run"], 5)
        self.assertNotIn("longest_stuck", result)
        self.assertEqual(result["expected_regret_status"], "not_evaluated")

    def test_detected_transition_has_separate_start_and_confirmation(self):
        rows = self.rows([(.02, [.02] * 5), (.15, [.03, .03] + [.15] * 5)])
        result = summarize_run(rows, {}, {})["transitions"][0]
        self.assertEqual(result["detection_status"], "detected")
        self.assertEqual(result["detection_delay"], 2)
        self.assertEqual(result["detection_confirmed_delay"], 6)
        self.assertFalse(result["detection_censored"])

    def test_already_high_prior_is_not_zero_delay_detection(self):
        rows = self.rows([(.02, [.1378] * 5), (.15, [.1378] * 5)])
        result = summarize_run(rows, {}, {})["transitions"][0]
        self.assertEqual(result["tracking_delay"], 0)
        self.assertEqual(result["detection_status"], "already_on_new_side")
        self.assertIsNone(result["detection_delay"])
        self.assertFalse(result["detection_censored"])

    def test_transition_censor_does_not_turn_into_completed_delay(self):
        rows = self.rows([(.02, [.02] * 5), (.15, [.03, .15, .15, .03, .15])])
        result = summarize_run(rows, {}, {})["transitions"][0]
        self.assertTrue(result["tracking_censored"])
        self.assertTrue(result["detection_censored"])
        self.assertIsNone(result["detection_delay"])
        self.assertEqual(result["followup_decisions"], 5)

    def test_down_transition_and_unsettled_prechange(self):
        rows = self.rows([(.15, [.15] * 5), (.02, [.15] + [.02] * 5)])
        result = summarize_run(rows, {}, {})["transitions"][0]
        self.assertEqual(result["direction"], "down")
        self.assertEqual(result["detection_delay"], 1)
        rows[2]["p_mean_pre"] = .02
        self.assertEqual(summarize_run(rows, {}, {})["transitions"][0]["detection_status"], "prechange_unsettled")

    def test_adaptation_counts_observations_before_decision(self):
        rows = self.rows([(.02, [.02] * 8)])
        for row in rows:
            row["near"] = row["index"] >= 5
        result = adaptation(rows, lambda row: row["near"], [4])[0]
        self.assertEqual(result["start_new_observations"], 1)
        self.assertEqual(result["confirmed_new_observations"], 2)
        self.assertFalse(result["censored"])
        self.assertEqual(adaptation(rows, lambda row: True, [4])[0]["start_new_observations"], 0)

    def test_adaptation_cannot_confirm_across_next_change(self):
        rows = self.rows([(.02, [.02] * 6)])
        results = adaptation(rows, lambda row: row["index"] >= 2, [2, 3])
        self.assertTrue(results[0]["censored"])
        self.assertIsNone(results[0]["start_new_observations"])
        self.assertEqual(results[1]["start_new_observations"], 0)

    def test_unknown_near_optimal_and_invalid_row_order(self):
        rows = self.rows([(.02, [.02] * 3)])
        self.assertEqual(adaptation(rows, lambda row: None, [0])[0]["status"], "unresolved")
        rows[1]["index"] = 2
        with self.assertRaises(ValueError):
            summarize_run(rows, {}, {})
        with self.assertRaises(ValueError):
            adaptation(rows, lambda row: True, [0])


if __name__ == "__main__":
    unittest.main()
