import unittest
from experiments.v33 import validate_m1_v2 as check, bench_m1_report as report


class M1IndependentTests(unittest.TestCase):
    def test_counts_ignore_row_order_and_reject_frequency_or_inventory_changes(self):
        rows=[dict(context_id="a",action=[0,0,0],n=1),dict(context_id="b",action=[0,3,1],n=9)]
        check.same_counts(rows,list(reversed(rows)),"order")
        with self.assertRaises(ValueError):
            check.same_counts(rows,[dict(rows[0],n=2),rows[1]],"frequency")
        with self.assertRaises(ValueError):
            check.same_counts(rows,rows+[rows[0]],"duplicate")

    def runs(self,cid,action,mean):
        return [dict(seed=seed,n=10,action_counts=[dict(context_id=cid,action=action,n=10)],
                     means={"mean_hct_ms":mean},summary={"mean_hct_ms":mean}) for seed in range(31,51)]

    def table(self,action,mean,variance):
        return dict(action=action,reference_action=[0,0,0],mean_hct_ms=mean,mean_gap_ms=mean-100,
                    n=131072,variance_hct_ms2=variance,gap_variance_ms2=variance,
                    gap_half_width_ms=1.,uncertainty_resolved=True,gap_exact_by_identity=False,
                    zero_observed_variance=False)

    def test_independent_scipy_bounds_match_cross_world_arithmetic(self):
        action=[0,3,1]
        tables={(cid,tuple(action)):self.table(action,mean,4.) for cid,mean in (("off",100.),("hold",98.))}
        ca,ba=self.runs("hold",action,97.),self.runs("off",action,100.)
        expected=check.difference(ca,ba,tables,False)
        actual=report.comparison(ca,ba,tables,dict(mc_family_confidence=.99,seed_confidence=.95,noninferiority_ms=.5),False)
        check.check_row(actual,expected)
        self.assertEqual(expected["mean"],-2.)
        self.assertEqual(expected["realized"][0],-3.)
        self.assertEqual(expected["status"],"pass")

    def test_independent_cross_world_zero_variance_stays_unresolved(self):
        action=[0,3,1]
        tables={(cid,tuple(action)):self.table(action,mean,0.) for cid,mean in (("off",100.),("hold",98.))}
        result=check.difference(self.runs("hold",action,98.),self.runs("off",action,100.),tables,False)
        self.assertIsNone(result["mc"])
        self.assertEqual(result["status"],"inconclusive")

    def test_independent_same_world_cancellation_requires_equal_context_mass(self):
        action=[0,3,1]
        tables={(cid,tuple(action)):self.table(action,mean,4.) for cid,mean in (("off",100.),("hold",98.))}
        with self.assertRaises(ValueError):
            check.difference(self.runs("hold",action,98.),self.runs("off",action,100.),tables,True)

    def test_independent_identical_action_weights_cancel_exactly(self):
        action=[0,3,1]
        tables={("hold",tuple(action)):self.table(action,98.,0.)}
        rows=self.runs("hold",action,98.)
        result=check.difference(rows,rows,tables,True)
        self.assertEqual(result["mc"],0.)
        self.assertEqual(result["mean"],0.)
        self.assertEqual(result["status"],"pass")


if __name__=="__main__":
    unittest.main()
