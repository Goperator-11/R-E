import importlib.util
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
CANDIDATE = ROOT / "g3/v33/candidate_sources/M1_v1"
sys.path.insert(0, str(CANDIDATE))
from padfec3 import layout, learn3, decide3

spec = importlib.util.spec_from_file_location("m1_original_layout", ROOT/"padfec3/layout.py")
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)


class M1CandidateTests(unittest.TestCase):
    def test_import_origin_and_version(self):
        for module in (layout, learn3, decide3):
            self.assertTrue(Path(module.__file__).resolve().is_relative_to(CANDIDATE))
        self.assertEqual(learn3.STATE_VERSION, 10)

    def test_old_state_rejected_and_current_state_roundtrips(self):
        state = learn3.new_state().to_json()
        for version in range(1,10):
            with self.subTest(version=version), self.assertRaises(ValueError):
                learn3.DestState3.from_json(dict(state, v=version))
        self.assertEqual(learn3.DestState3.from_json(state).to_json(),state)

    def test_disabled_branch_is_exact_legacy_cost(self):
        for k in range(1,5):
            for m in range(5):
                for lead in range(m+1):
                    for p in (0., .02, .15):
                        args = (k,1280,m,lead,p,50.,2.,15)
                        with self.subTest(k=k,m=m,lead=lead,p=p):
                            self.assertEqual(layout.evaluate(*args,lead_hold=False),original.evaluate(*args))
                            self.assertEqual(list(layout.outcomes(k,m,lead,1280,p,2.,lead_hold=False)),
                                             list(original.outcomes(k,m,lead,1280,p,2.)))

    def test_learning_uses_candidate_cost_and_probabilities(self):
        ctx = dict(k=2,W=1280,u=2.,rtt=50.,n_need=15)
        for action in ((0,0,0),(0,3,1),(0,4,0)):
            for g in (0,5,10,len(learn3.G)-1):
                d,l,t = action
                expected = layout.evaluate(2,1280+d,l+t,l,learn3.G[g],50.,2.,15)
                self.assertEqual(learn3.j3_at(ctx,action,g),expected["J"])
                self.assertEqual(learn3.class_probabilities(ctx,action,g),
                    [expected["p_one_rtt"],expected["p_two_rtt"],expected["p_fail"]])

    def test_no_parity_is_baseline_equivalent(self):
        for k in range(1,5):
            for p in (0.,.02,.15):
                a=layout.evaluate(k,1280,0,0,p,50.,2.,15)
                b=original.evaluate(k,1280,0,0,p,50.,2.,15)
                for key in b:
                    if isinstance(b[key],float):
                        self.assertAlmostEqual(a[key],b[key],places=11)
                    else:
                        self.assertEqual(a[key],b[key])


if __name__ == "__main__":
    unittest.main()
