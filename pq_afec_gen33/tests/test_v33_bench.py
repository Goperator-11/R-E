import copy
import json
from pathlib import Path
import tempfile
import unittest

from experiments.v33 import bench


class BenchmarkBoundaryTests(unittest.TestCase):
    def test_truth_fields_are_not_sent_to_policy(self):
        decision = {"action":[0,3,1], "j3_pred_pre_ms":100.0}
        world_row = {"hct":110.0,"ok":True,"k_obs":2,"srv_bytes":19000,"p":.15,"true_rtt_ms":50,"rtt":55,"arrivals":[{"arrived":False}],"server_dgram_sizes":[1280],"cert_bytes":16000,"initial_failure":True,"world_class":"tail"}
        sent = bench.observation_request(decision, world_row, 54.0)
        self.assertEqual(set(sent), {"op","destination","action","hct_ms","ok","k_obs","srv_bytes","rtt_ms","j_pred"})
        self.assertEqual(sent["rtt_ms"],54.0)
        self.assertEqual(world_row["arrivals"],[{"arrived":False}])

    def test_failed_world_cost_remains_outside_observation(self):
        sent = bench.observation_request({"action":[0,0,0]}, {"hct":120000,"ok":False,"k_obs":2,"srv_bytes":0}, None)
        self.assertIsNone(sent["hct_ms"])
        self.assertFalse(sent["ok"])

    def test_observed_rtt_has_no_truth_seed(self):
        history = bench.ObservedRTT()
        self.assertIsNone(history.value())
        history.observe({"ok":False,"hct":120000,"rtt":None})
        self.assertIsNone(history.value())
        history.observe({"ok":True,"hct":100,"rtt":None})
        self.assertEqual(history.value(),100)
        history.observe({"ok":True,"hct":120,"rtt":60})
        self.assertEqual(history.value(),60)
        history.observe({"ok":True,"hct":90,"rtt":70})
        self.assertEqual(history.value(),60)
        history.observe({"ok":False,"hct":120000,"rtt":55})
        self.assertEqual(history.value(),55)
        self.assertEqual(history.minimum_hct,90)

    def test_resume_rejects_different_seed_even_with_valid_trace(self):
        scenario = {"id":"B1","phases":[{"length":1}]}
        planned = {"mode":"full","protocol_sha256":"fixed"}
        result = {"generation":"v31","variant":"full","scenario":"B1","seed":32,"mode":"full","protocol_sha256":"fixed","n":1}
        with self.assertRaisesRegex(ValueError,"identity"):
            bench.validate_resume(result,generation="v31",variant="full",scenario=scenario,seed=31,planned=planned,fingerprint={})

    def test_policy_fingerprint_rejects_mixed_generation_bytes(self):
        root = bench.ROOT
        expected = {"source_root":str(root),"files":{"padfec3/learn3.py":"old"}}
        audit = {"source_root":str(root),"source_unchanged":True,"source_sha256":{str(root / "padfec3/learn3.py"):"new"}}
        with self.assertRaisesRegex(ValueError,"differs"):
            bench.validate_policy_audit(audit,expected)

    def test_mixture_assignment_is_replayable_and_action_independent(self):
        spec = {"context":{"k":2,"w":1280,"p":.02,"rtt_ms":50,"uplink_mbps":2,"cert_bytes":2955},"mixture":[{"weight":.65,"context":{"cert_bytes":2955}},{"weight":.35,"context":{"cert_bytes":16000}}]}
        first = [bench.mixture_context(spec,31,i).cert_bytes for i in range(100)]
        second = [bench.mixture_context(spec,31,i).cert_bytes for i in reversed(range(100))][::-1]
        self.assertEqual(first,second)
        self.assertEqual(set(first),{2955,16000})

    def test_protocol_retains_both_switching_regimes_and_twenty_seeds(self):
        protocol = bench.load_protocol(bench.ROOT / "g3/v33/bench_protocol.json")
        scenarios = {s["id"]:s for s in protocol["scenarios"]}
        self.assertEqual([p["p"] for p in scenarios["B1"]["phases"]],[.02,.15,.02])
        self.assertEqual([p["p"] for p in scenarios["B2"]["phases"]],[.02,.25,.02])
        self.assertEqual(len(protocol["seeds"]),20)
        self.assertTrue(scenarios["B9"]["reset_each_connection"])
        self.assertEqual(len(bench.all_contexts(protocol)),19)

    def test_protocol_rejects_duplicate_seeds(self):
        protocol = json.loads((bench.ROOT / "g3/v33/bench_protocol.json").read_text(encoding="utf-8"))
        protocol["seeds"][1] = protocol["seeds"][0]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "protocol.json"
            path.write_text(json.dumps(protocol),encoding="utf-8")
            with self.assertRaises(ValueError):
                bench.load_protocol(path)

    def test_protocol_requires_both_world_hashes(self):
        protocol = json.loads((bench.ROOT / "g3/v33/bench_protocol.json").read_text(encoding="utf-8"))
        for mapping in ({}, {"worldsim.py":protocol["world"]["source_sha256"]["worldsim.py"]}):
            changed = copy.deepcopy(protocol)
            changed["world"]["source_sha256"] = mapping
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "protocol.json"
                path.write_text(json.dumps(changed),encoding="utf-8")
                with self.assertRaisesRegex(ValueError,"hashes"):
                    bench.load_protocol(path)


if __name__ == "__main__":
    unittest.main()
