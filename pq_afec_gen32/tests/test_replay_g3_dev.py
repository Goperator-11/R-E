import contextlib
import copy
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from experiments import replay_g3
from padfec3 import learn3


def trial(i=0, action=(0, 0, 0), ms=100.0, ok=True):
    return {"i": i, "action": list(action), "ms": ms, "ok": ok,
            "first_flight_datagrams": 2, "server_bytes": 18231,
            "path_rtt_valid": True, "path_rtt_ms": 50.0,
            "policy_version": "v3.1"}


def decision(action=(0, 0, 1), prediction=20.0, **fields):
    res = {"action": action, "why": "ej", "n_need": 15, "k": 2,
           "ej": 11.0, "j3_pred_pre_ms": prediction, "guard_alarm": False,
           "guard_common_ms": 0.0, "guard_alarmed_actions": 0,
           "reeval": False, "policy_version": learn3.POLICY_VERSION}
    res.update(fields)
    return res


class ReplayDevelopmentTests(unittest.TestCase):
    def test_observation_uses_unpenalized_predecision_prediction_and_reports_guard(self):
        pol = replay_g3.V3Learn(2.0, "v3")
        res = decision(guard_alarm=True, guard_alarmed_actions=1,
                       reeval=True, why="reeval", score=1000.0)
        with mock.patch.object(replay_g3.decide3, "decide3", return_value=res):
            arm = pol.decide()
        row = trial(action=res["action"])
        before = copy.deepcopy(row)
        with mock.patch.object(learn3, "observe3", wraps=learn3.observe3) as observe:
            pol.observe(arm, row)
        self.assertEqual(observe.call_args.kwargs["j_pred"], 20.0)
        self.assertEqual(row, before)
        diag = pol.diag()
        self.assertEqual(diag["policy_version"], learn3.POLICY_VERSION)
        self.assertEqual(diag["guard"], {"rows": 1, "alarm_rows": 1, "reeval_rows": 1})
        self.assertEqual(diag["last_row"]["guard_resid_ms"], 80.0)
        self.assertTrue(diag["last_row"]["reeval"])
        self.assertEqual(diag["residuals"], {"n": 1, "mean_ms": 80.0})

    def test_cold_and_failed_observations_have_null_residuals(self):
        pol = replay_g3.V3Learn(2.0, "v3")
        arm = pol.decide()
        pol.observe(arm, trial())
        self.assertIsNone(pol.last_row["j3_pred_pre_ms"])
        self.assertIsNone(pol.last_row["guard_resid_ms"])
        with mock.patch.object(replay_g3.decide3, "decide3", return_value=decision()):
            arm = pol.decide()
        pol.observe(arm, trial(ok=False))
        self.assertIsNone(pol.last_row["guard_resid_ms"])
        self.assertEqual(pol.diag()["residuals"]["n"], 0)

    def test_observe_requires_the_chosen_arm(self):
        pol = replay_g3.V3Learn(2.0, "v3")
        with self.assertRaises(RuntimeError):
            pol.observe(0, trial())
        pol.decide()
        with self.assertRaises(ValueError):
            pol.observe(1, trial())

    def write_journal(self, directory, rows=None):
        path = os.path.join(directory, "historical.jsonl")
        unit = {"run_id": "fixture", "key": "run1|S_bigcert|b000",
                "val": {"cond": "S_bigcert", "attempt": 1,
                        "segments": [{"arm": "g3auto", "argv":
                                      ["qamp", "-uplink-mbps", "2"],
                                      "rows": rows or [trial(), trial(1)]}]}}
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(unit) + "\n")
        return path

    def test_recorded_action_prediction_is_distinct_from_new_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_journal(directory, [trial(), trial(1, (0, 3, 1))])
            res = [decision((0, 0, 0), None), decision((0, 0, 4), 40.0)]
            with mock.patch.object(replay_g3.decide3, "decide3", side_effect=res), \
                    mock.patch.object(replay_g3.decide3, "decide_core",
                                      return_value={"ej": 20.0}), \
                    mock.patch.object(learn3, "observe3", wraps=learn3.observe3) as obs:
                rows = replay_g3.recorded_v31(path)
            self.assertEqual(rows[1]["recorded_action"], [0, 3, 1])
            self.assertEqual(rows[1]["new_decision"]["action"], (0, 0, 4))
            self.assertEqual(rows[1]["new_decision"]["j3_pred_pre_ms"], 40.0)
            self.assertEqual(rows[1]["recorded_action_prediction_ms"], 20.0)
            self.assertEqual(rows[1]["recorded_action_residual_ms"], 80.0)
            self.assertEqual(set(rows[1]["new_observation"]),
                             {"y", "skip", "updated", "raised", "alarmed", "common", "n_alarm"})
            self.assertEqual(set(rows[1]["new_posterior_after"]),
                             {"p_mean", "p_map", "p_ge_010", "mass"})
            self.assertEqual(rows[1]["new_stats_after"]["obs"], 2)
            self.assertEqual(rows[1]["new_stats_after"]["predict"], 2)
            self.assertEqual(obs.call_args.args[1], (0, 3, 1))
            self.assertEqual(obs.call_args.kwargs["j_pred"], 20.0)

    def test_recorded_cli_labels_historical_observations_and_keeps_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_journal(directory)
            output = os.path.join(directory, "development.json")
            with open(path, "rb") as f:
                before = hashlib.sha256(f.read()).hexdigest()
            result = subprocess.run(
                [sys.executable, "-B", os.path.join(ROOT, "experiments", "replay_g3.py"),
                 "--recorded-v31", "--journal", path, "--out", output, "--limit", "1"],
                capture_output=True, text=True, check=True)
            with open(output, encoding="utf-8") as f:
                doc = json.load(f)
            with open(path, "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), before)
            self.assertEqual(doc["label"], "development/counterfactual")
            self.assertFalse(doc["confirmatory"])
            self.assertEqual(doc["policy_version"], learn3.POLICY_VERSION)
            self.assertEqual(doc["trajectory_kind"], "recorded_action_observation_replay")
            self.assertEqual(len(doc["rows"]), 1)
            self.assertEqual(doc["journal"]["recorded_policy_version"], "v3.1")
            self.assertIn("not a measured or closed-loop trajectory", result.stdout)

    def test_recorded_cold_visit_resets_counterfactual_state(self):
        with tempfile.TemporaryDirectory() as directory:
            rows = [trial(), trial(1), trial(2)]
            rows[2]["why3"] = "cold"
            path = self.write_journal(directory, rows)
            results = replay_g3.recorded_v31(path)
            self.assertIsNotNone(results[1]["new_decision"]["j3_pred_pre_ms"])
            self.assertIsNone(results[2]["new_decision"]["j3_pred_pre_ms"])
            self.assertIsNone(results[2]["recorded_action_residual_ms"])

    def test_recorded_cli_requires_output_and_refuses_input_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_journal(directory)
            for args in (["--recorded-v31", "--journal", path],
                         ["--recorded-v31", "--journal", path, "--out", path]):
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    replay_g3.main(args)

    def test_recorded_mode_rejects_non_v31_rows_and_duplicate_units(self):
        with tempfile.TemporaryDirectory() as directory:
            row = trial()
            row["policy_version"] = "v3.2-dev"
            path = self.write_journal(directory, [row])
            with self.assertRaisesRegex(ValueError, "requires v3.1"):
                replay_g3.recorded_v31(path)
            path = self.write_journal(directory)
            with open(path, encoding="utf-8") as f:
                unit = f.read()
            with open(path, "a", encoding="utf-8") as f:
                f.write(unit)
            with self.assertRaisesRegex(ValueError, "duplicate"):
                replay_g3.recorded_v31(path)


if __name__ == "__main__":
    unittest.main()
