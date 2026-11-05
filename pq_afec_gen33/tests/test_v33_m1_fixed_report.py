import unittest
from experiments.v33 import m1_fixed_world_report as report


class M1FixedReportTests(unittest.TestCase):
    def test_minimum_interval_allows_selected_action_to_change(self):
        rows=[dict(action=[0,3,1],mean_hct_ms=100.,half_width_ms=5.),
              dict(action=[0,4,0],mean_hct_ms=101.,half_width_ms=1.)]
        result=report.minimum(rows)
        self.assertEqual(result["action"],[0,3,1])
        self.assertEqual((result["lower_ms"],result["upper_ms"]),(95.,102.))

    def test_unknown_action_bound_prevents_minimum_certificate(self):
        rows=[dict(action=[0,3,1],mean_hct_ms=100.,half_width_ms=1.),
              dict(action=[0,4,0],mean_hct_ms=101.,half_width_ms=None)]
        result=report.minimum(rows)
        self.assertIsNone(result["lower_ms"])
        self.assertIsNone(result["upper_ms"])

    def test_full_fixed_design_uses_exact_profiles_and_all_actions(self):
        plan=report.family.collector.read(report.family.collector.PLAN)
        fixed=report.family.read(report.family.collector.ROOT/"g3/v33/validation/M1_stage2_validation/M1_fixed_checks_01.json")
        tables={}
        for profile in ("off","hold"):
            for cid,spec in report.bench.all_contexts(plan["protocols"][profile]).items():
                for action in fixed["actions"]:
                    tables[cid,tuple(action)]=dict(n=100,mean_hct_ms=90. if profile=="hold" else 100.,variance_hct_ms2=.0001)
        result=report.summarize(tables,plan,fixed)
        self.assertEqual(len(result["fixed_rows"]),64)
        self.assertEqual(len(result["fixed_differences"]),32)
        self.assertEqual(len(result["finite_design_minima"]),2)
        for row in result["finite_design_minima"]:
            self.assertEqual(row["hold_minus_off_ms"],-10.)
            self.assertLess(row["upper_ms"],0.)
        self.assertFalse(result["global_optimum_claim"])


if __name__=="__main__":
    unittest.main()
