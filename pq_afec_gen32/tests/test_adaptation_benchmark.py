import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import adaptation_benchmark as bench
from padfec3 import layout, learn3


def protocol():
    return json.loads(bench.PROTOCOL_DEFAULT.read_text(encoding="utf-8"))


def small_spec():
    spec = copy.deepcopy(protocol()["conditions"][1])
    for phase in spec["phases"]:
        phase["steps"] = 4
    return spec


class AdaptationBenchmarkTests(unittest.TestCase):
    def test_catalogue_probability_and_expectation_match_layout_model(self):
        kinds, rtts = set(), set()
        for spec in protocol()["conditions"]:
            for action in ((0, 0, 0), (0, 1, 2), (1, 0, 4), (0, 4, 0)):
                for p in (0.0, 0.15, 0.30):
                    with self.subTest(condition=spec["id"], action=action, p=p):
                        cat = bench.catalogue(spec, action, p)
                        atoms = cat["atoms"]
                        self.assertAlmostEqual(math.fsum(a["probability"] for a in atoms), 1.0)
                        expected = math.fsum(a["probability"] * a["synthetic_cost_ms"] for a in atoms)
                        _, need = bench.true_context(spec)
                        ev = layout.evaluate(spec["k"], spec["W"] + action[0],
                                             action[1] + action[2], action[1], p,
                                             spec["rtt_ms"], spec["uplink_mbps"], need, "v3")
                        self.assertAlmostEqual(expected, ev["J"], places=9)
                        kinds.update(a["initial_kind"] for a in atoms)
                        rtts.update(a["n_rtt"] for a in atoms if a["initial_kind"] == "ok")
        self.assertEqual(kinds, {"ok", "pto", "ptoS", "ack"})
        self.assertEqual(rtts, {1, 2})

    def test_noise_semantics_determinism_and_variant_order_independence(self):
        spec = small_spec()
        noise = {"original": [0.1, 0.9, 0.4, 0.8],
                 "parity": [0.2, 0.7, 0.3, 0.6], "race": 0.35}
        for action in ((0, 0, 3), (1, 1, 2), (0, 2, 1)):
            sample = bench.sample_cost(spec, action, 0.5, noise)
            self.assertEqual(sample["pattern"],
                             [int(x >= 0.5) for x in noise["parity"][:action[1]]]
                             + [0, 1]
                             + [int(x >= 0.5) for x in noise["parity"][action[1]:3]])
            self.assertEqual(sample, bench.sample_cost(spec, action, 0.5, noise))
        tape, tape_hash = bench.noise_tape(31, spec["id"], "comparison", 12)
        self.assertEqual((tape, tape_hash), bench.noise_tape(31, spec["id"], "comparison", 12))
        self.assertEqual(tape_hash, hashlib.sha256(bench.canonical(tape)).hexdigest())
        first = bench.run_condition(spec, 31, 8)
        self.assertEqual(first, bench.run_condition(spec, 31, 8))
        self.assertEqual(first, bench.run_condition(spec, 31, 8, tuple(reversed(bench.VARIANTS))))
        for row in first["variants"]["full"]["rows"]:
            oracle = min(bench.catalogue(spec, a, row["p_true"])["expected_cost_ms"]
                         for a in first["candidate_actions"])
            self.assertEqual(row["oracle_min_expected_cost_ms"], oracle)
            self.assertEqual(row["expected_regret_ms"], row["true_expected_cost_ms"] - oracle)
            self.assertGreaterEqual(row["expected_regret_ms"], 0.0)

    def test_ablations_restore_only_loss_state_and_keep_observation_history(self):
        for informative in (False, True):
            spec = small_spec()
            spec["cert"] = 4000 if informative else 30000
            spec["rtt_ms"] = 80.0 if informative else 200.0
            action = (0, 0, 0)
            st = learn3.new_state()
            S, _ = bench.true_context(spec)
            st.k_hist, st.S_hist = [spec["k"]], [S]
            st.post = [[1.0] + [0.0] * (len(learn3.G) - 1) for _ in learn3.H]
            st.hct[learn3.arm_key(action)] = [100.0] * learn3.BASE_MIN
            st.hct_seq[learn3.arm_key(action)] = 0
            res = {"action": action, "j3_pred_pre_ms": 100.0}
            states, flags = {}, {}
            for variant in bench.VARIANTS:
                state = copy.deepcopy(st)
                info, effective = bench.observe_variant(
                    state, res, {"synthetic_cost_ms": 105.0}, spec, variant)
                self.assertEqual(info["updated"], informative)
                self.assertEqual(state.stats["obs"], 1)
                self.assertEqual(state.stats["predict"], 1)
                self.assertEqual(state.stats["resid"], 1)
                self.assertEqual(state.hct[learn3.arm_key(action)][-1], 105.0)
                self.assertEqual(state.seq, 1)
                self.assertEqual(state.g_resid[learn3.arm_key(action)], [5.0])
                states[variant], flags[variant] = state, effective
            self.assertNotEqual(states["full"].post, st.post)
            self.assertEqual(states["frozen_loss"].post, st.post)
            self.assertEqual(states["frozen_loss"].w, st.w)
            self.assertFalse(flags["frozen_loss"]["hazard_transition_committed"])
            expected = states["full"] if informative else st
            self.assertEqual(states["skip_hazard_ablation"].post, expected.post)
            self.assertEqual(states["skip_hazard_ablation"].w, expected.w)
            self.assertEqual(flags["skip_hazard_ablation"]["posterior_update_committed"], informative)
            self.assertEqual(states["full"].hct, states["frozen_loss"].hct)
            self.assertEqual(states["full"].g_resid, states["skip_hazard_ablation"].g_resid)

    def test_cli_synthetic_contract_hashes_atomic_output_and_input_protection(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            p = protocol()
            p["conditions"] = [small_spec()]
            p["warmup_steps"] = 4
            source = folder / "protocol.json"
            source.write_text(json.dumps(p), encoding="utf-8")
            original_hash = bench.sha256(source.read_bytes())
            out = folder / "output.json"
            cmd = [sys.executable, "-B", str(ROOT / "experiments/adaptation_benchmark.py"),
                   "--protocol", str(source)]
            def invoke(*args):
                return subprocess.run(cmd + list(args), cwd=folder, capture_output=True,
                                      text=True, timeout=60)
            result = invoke("--out", str(out))
            self.assertEqual(result.returncode, 0, result.stderr)
            doc = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(doc["synthetic"])
            self.assertFalse(doc["confirmatory"])
            self.assertEqual(doc["network_measurements"], 0)
            self.assertEqual(doc["protocol_input_sha256"], original_hash)
            self.assertEqual(doc["protocol_sha256"], bench.sha256(bench.canonical(p)))
            self.assertEqual(doc["source_sha256"], bench.source_hashes())
            self.assertEqual(set(doc["cases"][0]["variants"]), set(bench.VARIANTS))
            self.assertIn("No network measurements", result.stdout)
            initial_output = out.read_bytes()
            result = invoke("--out", str(out))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(out.read_bytes(), initial_output)
            self.assertEqual(list(folder.glob("output.json.*.tmp")), [])
            result = invoke("--out", str(source))
            self.assertEqual(result.returncode, 2)
            self.assertEqual(bench.sha256(source.read_bytes()), original_hash)
            result = invoke("--out", str(ROOT / "padfec3/learn3.py"))
            self.assertEqual(result.returncode, 2)
            bad = copy.deepcopy(p)
            bad["conditions"][0]["phases"][0]["p_true"] = 0.31
            source.write_text(json.dumps(bad), encoding="utf-8")
            bad_out = folder / "invalid.json"
            result = invoke("--out", str(bad_out))
            self.assertEqual(result.returncode, 2)
            self.assertFalse(bad_out.exists())


if __name__ == "__main__":
    unittest.main()
