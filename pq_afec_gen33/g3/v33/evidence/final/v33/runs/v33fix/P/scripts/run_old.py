import sys; sys.dont_write_bytecode=True; sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
HERE = Path(__file__).resolve().parent
OLD = HERE / "oldroot"
ROOT = r"C:\dev\pq_afec_gen33"
sys.path.insert(0, str(OLD))
sys.path.insert(1, ROOT)
sys.path.insert(2, ROOT + r"\tests")
sys.path.insert(3, ROOT + r"\experiments")
import padfec3, padfec3.learn3, padfec3.decide3, padfec, padfec.policy
assert Path(padfec3.__file__).resolve().is_relative_to(OLD), padfec3.__file__
print("padfec3 from", padfec3.__file__, "STATE_VERSION", padfec3.learn3.STATE_VERSION, "UDP_MAX", padfec3.decide3.UDP_MAX)
import unittest
results = {}

def run_case(case):
    r = unittest.TestResult()
    case.run(r)
    return {"failures": [f[1].strip().splitlines()[-1] for f in r.failures], "errors": [e[1].strip().splitlines()[-1] for e in r.errors], "ran": r.testsRun}

import test_v33_l3_candidate as L
try:
    L.test_active_l1_rejects_l3_candidate_state()
    results["l3_candidate"] = "passed"
except BaseException as exc:
    results["l3_candidate"] = "failed: %s %s" % (type(exc).__name__, exc)

import test_v33_policy_worker as W
W.init_request.__defaults__ = (OLD, "full")
results["policy_worker"] = run_case(W.PolicyWorkerTests("test_current_complete_first_flight_updates_cold_loss_state_once"))

import test_adaptation_benchmark as A
results["adaptation"] = run_case(A.AdaptationBenchmarkTests("test_ablations_restore_only_loss_state_and_keep_observation_history"))

import test_p21_gencompare as G
results["p21"] = run_case(G.HPredictionTests("test_toy_cell_matches_a_direct_computation"))

for k, v in results.items():
    print(k, v)
print("padfec3 still old:", Path(sys.modules["padfec3"].__file__).resolve().is_relative_to(OLD))
