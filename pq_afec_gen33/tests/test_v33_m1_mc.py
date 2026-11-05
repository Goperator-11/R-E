import math
from statistics import NormalDist
import unittest

from experiments.v33 import oracle, oracle_m1, bench_oracles_m1, bench_action_pool_m1
from experiments.v33 import bench_m1_report as report


class M1MCTests(unittest.TestCase):
    def test_off_oracle_replays_original_moments(self):
        context=dict(k=2,w=1280,p=.1,rtt_ms=50.,uplink_mbps=2.,cert_bytes=16000)
        spec=dict(validation_samples=32,validation_seed=910029,structural_certificates=False,evaluation_family_size=2)
        original=oracle.evaluate_action(context,(0,3,1),(0,0,0),spec=spec)
        changed=oracle_m1.evaluate_action(context,(0,3,1),(0,0,0),world_params={"lead_mode":"credit_only"},spec=spec)
        for key in ("mean_gap_ms","gap_variance_ms2","mean_hct_ms","reference_mean_hct_ms","variance_hct_ms2",
                    "reference_variance_hct_ms2","covariance_hct_ms2","n","gap_half_width_ms"):
            self.assertEqual(original[key],changed[key],key)

    def test_new_world_does_not_borrow_old_structural_certificate(self):
        context=dict(k=2,w=1280,p=0.,rtt_ms=50.,uplink_mbps=0.,cert_bytes=16000)
        result=oracle_m1.evaluate_action(context,(0,0,0),(0,0,0),spec=dict(validation_samples=8,validation_seed=910029))
        self.assertEqual(result["method"],"independent_paired_validation")
        self.assertEqual(result["n"],8)
        self.assertTrue(result["gap_exact_by_identity"])

    def test_source_contract_binds_independent_receiver(self):
        wanted={"oracle_m1.py","worldsim_m1.py","worldparams_m1.json","world_receiver_m1.py"}
        self.assertEqual(set(oracle_m1._source_hashes()),wanted)
        self.assertEqual(bench_oracles_m1.RESULT_SOURCES,wanted)
        self.assertTrue(wanted.issubset(bench_action_pool_m1._sources()))
        bad=oracle_m1._source_hashes();bad["world_receiver_m1.py"]="0"*64
        with self.assertRaises(ValueError):
            bench_oracles_m1._source_contract(bad,wanted)

    def rows(self,cid,action,real):
        return [dict(seed=s,n=1,summary={"mean_hct_ms":real},action_counts=[dict(context_id=cid,action=action,n=1)]) for s in range(31,51)]

    def table(self,mean,var=4.,identity=False):
        return dict(mean_hct_ms=mean,mean_gap_ms=mean-100.,variance_hct_ms2=var,gap_variance_ms2=var,n=100,
                    gap_exact_by_identity=identity,uncertainty_resolved=True,zero_observed_variance=False,
                    action=[0,3,1],reference_action=[0,0,0],gap_half_width_ms=1.)

    def rules(self):
        return dict(mc_family_confidence=.99,seed_confidence=.95,noninferiority_ms=.5)

    def test_cross_world_absolute_cost_and_joint_family_width(self):
        action=[0,3,1]
        tables={(cid,tuple(action)):self.table(mean) for cid,mean in (("hold",99.),("off",100.))}
        result=report.comparison(self.rows("hold",action,90.),self.rows("off",action,100.),tables,self.rules(),False)
        z=NormalDist().inv_cdf(1-.01/8)
        self.assertEqual(result["seed_summary"]["mean"],-1.)
        self.assertAlmostEqual(result["shared_mc_bound_ms"],2*z*.2,places=12)
        self.assertEqual(result["mc_scalar_family_size"],4)
        self.assertFalse(result["oracle_cancels"])
        self.assertNotEqual(result["seed_summary"]["mean"],result["realized_hct_diagnostic"]["mean"])

    def test_identical_same_world_weights_cancel_without_unknown_width(self):
        action=[0,3,1]
        tables={("hold",tuple(action)):self.table(99.,0.)}
        result=report.comparison(self.rows("hold",action,90.),self.rows("hold",action,90.),tables,self.rules(),True)
        self.assertEqual(result["shared_mc_bound_ms"],0.)
        self.assertEqual(result["seed_summary"]["mean"],0.)
        self.assertEqual(result["regression_gate"]["status"],"pass")

    def test_absolute_zero_variance_is_not_identity_across_worlds(self):
        action=[0,3,1]
        tables={(cid,tuple(action)):self.table(mean,0.,True) for cid,mean in (("hold",99.),("off",100.))}
        result=report.comparison(self.rows("hold",action,90.),self.rows("off",action,100.),tables,self.rules(),False)
        self.assertIsNone(result["shared_mc_bound_ms"])
        self.assertEqual(len(result["unresolved"]),2)
        self.assertEqual(result["regression_gate"]["status"],"inconclusive")

    def complete_fixture(self):
        plan=report.family.collector.read(report.family.collector.PLAN)
        runs=[]
        tables={}
        for profile in plan["protocols"]:
            roles=list(plan["policies"])+( ["v31","v32"] if profile=="off" else [])
            for role in roles:
                action=[0,3,1] if role=="m1" else [0,0,0]
                mean={"off":99. if role=="m1" else 100.,"hold":95. if role=="m1" else 96.}[profile]
                tables[profile,tuple(action)]=self.table(mean,.0001)
                modes=["legacy"] if role in ("v31","v32") else plan["modes"]
                for mode in modes:
                    for scenario in plan["protocols"][profile]["scenarios"]:
                        for row in self.rows(profile,action,mean):
                            runs.append(dict(row,profile=profile,role=role,observation_mode=mode,scenario=scenario["id"]))
        return plan,runs,tables

    def test_complete_factorial_and_historical_inventory(self):
        plan,runs,tables=self.complete_fixture()
        result=report.aggregate(runs,tables,plan)
        self.assertEqual(len(runs),4200)
        self.assertEqual(len(result["comparisons"]),180)
        self.assertEqual(len(result["factorial_contributions"]),135)
        verdict=result["performance_decision"]
        self.assertEqual(verdict["status"],"pass")
        self.assertEqual(verdict["counts"],{"pass":120})
        self.assertEqual(len(verdict["c1_endpoint_improved_cells"]),15)
        with self.assertRaises(ValueError):
            report.aggregate(runs[:-1],tables,plan)
        with self.assertRaises(ValueError):
            report.aggregate(runs+[runs[0]],tables,plan)

    def test_complete_report_rejects_known_harm(self):
        plan,runs,tables=self.complete_fixture()
        tables["hold",(0,3,1)]=self.table(102.,.0001)
        result=report.aggregate(runs,tables,plan)
        self.assertEqual(result["performance_decision"]["status"],"fail")
        self.assertEqual(result["performance_decision"]["counts"],{"fail":120})
        self.assertEqual(result["performance_decision"]["c1_endpoint_improved_cells"],[])


if __name__=="__main__":
    unittest.main()
