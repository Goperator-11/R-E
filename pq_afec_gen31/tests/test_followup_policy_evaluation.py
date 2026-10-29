"""Offline acquisition-window regressions; no network, netns or measurements."""
import contextlib
import copy
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT))
import policy_evaluation as PE
import p11_adaptive as P11
import p15_v2policy as P15


def block(index, raw, id_key="round", pos=0):
    valid = [v for v in raw if v is not None]
    return {id_key: index, "pos": pos, "n": len(raw), "ok": len(valid),
            "ms_rows": list(raw), "ms": valid,
            "mean": sum(valid) / len(valid) if valid else None}


class MemoryJournal:
    def __init__(self, *args, **kwargs):
        self.data = {}
    def has(self, key):
        return key in self.data
    def get(self, key):
        return self.data[key]
    def record(self, key, value):
        self.data[key] = value
    def provenance(self):
        return {"used_units": len(self.data)}


class WindowTests(unittest.TestCase):
    def test_failures_do_not_move_the_selection_boundary(self):
        blocks = [block(1, [1, None, None, None]), block(2, [9, 9, 9, 9])]
        _, train = PE.block_window(blocks, [1], "round")
        _, evaluation = PE.block_window(blocks, [2], "round")
        self.assertEqual(train, [1])
        self.assertEqual(evaluation, [9, 9, 9, 9])
        self.assertNotEqual(train, [1, 9])  # old success-array half

    def test_missing_duplicate_empty_and_nonfinite_blocks_fail_closed(self):
        examples = [[], [block(1, [1]), block(1, [2])], [block(1, [None])],
                    [block(1, [float("nan")])], [block(1, [True])]]
        for blocks in examples:
            with self.subTest(blocks=blocks), self.assertRaises(ValueError):
                PE.block_window(blocks, [1], "round")
        bad = block(1, [1, 2])
        bad["ok"] = 1
        with self.assertRaises(ValueError):
            PE.block_window([bad], [1], "round")

    def test_selection_is_frozen_before_evaluation(self):
        auto = [block(i, [3]) for i in range(1, 5)]
        fixed = {"m0": [block(i, [1 if i <= 2 else 5]) for i in range(1, 5)],
                 "m1": [block(i, [2 if i <= 2 else 1]) for i in range(1, 5)]}
        result = PE.matched_diagnostics(auto, fixed, [1, 2], [3, 4], "round")
        self.assertEqual(result["selected_fixed"], "m0")
        self.assertEqual(result["best_observed"], "m1")
        self.assertEqual(result["selected_fixed_contrast"]["mean_ms"], -2)
        self.assertEqual(result["observed_best_regret_ms"], 2)
        self.assertFalse(result["independent_confirmation"])

    def test_equal_round_weights_do_not_weight_successful_rounds_more(self):
        auto = [block(i, [10] * (1 if i % 2 else 10)) for i in range(1, 5)]
        fixed = {"m0": [block(i, [2 if i % 2 else 8] * (1 if i % 2 else 10))
                        for i in range(1, 5)]}
        result = PE.matched_diagnostics(auto, fixed, [1, 2], [3, 4], "round")
        self.assertEqual(result["observed_best_regret_ms"], 5)
        self.assertEqual(result["counts"]["m0"]["successful"], 11)

    def test_all_candidate_interval_accounts_for_supplied_family(self):
        auto = [block(i, [i]) for i in range(1, 5)]
        fixed = {a: [block(i, [0]) for i in range(1, 5)] for a in ("m0", "m1")}
        small = PE.matched_diagnostics(auto, fixed, [1, 2], [3, 4], "round")
        large = PE.matched_diagnostics(auto, fixed, [1, 2], [3, 4], "round", family_size=12)
        self.assertGreater(large["contrasts"]["m0"]["half_ms"], small["contrasts"]["m0"]["half_ms"])
        with self.assertRaises(ValueError):
            PE.matched_diagnostics(auto, fixed, [1, 2], [2, 3], "round")

    def test_boolean_metadata_and_invalid_contrasts_are_rejected(self):
        for field in ("round", "n", "ok", "mean"):
            b = block(1, [1])
            b[field] = True
            with self.subTest(field=field), self.assertRaises(ValueError):
                PE.block_window([b], [1], "round")
        with self.assertRaises(ValueError):
            PE.block_window([block(1, [1])], [True], "round")
        rows = [block(i, [1]) for i in range(1, 5)]
        for family in (True, 1.5, 0):
            with self.assertRaises(ValueError):
                PE.matched_diagnostics(rows, {"m0": rows}, [1, 2], [3, 4], "round", family)
        for invalid in (True, float("nan"), float("inf"), -1):
            with self.assertRaises(ValueError):
                PE.paired_contrast([{"mean": invalid}] * 2, [{"mean": 1}] * 2)


class RunnerTests(unittest.TestCase):
    def run_main(self, module, condition_result):
        saved = []
        with contextlib.ExitStack() as stack:
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            for name in ("harden", "require_root", "require_bin", "setup"):
                stack.enter_context(patch.object(module.B, name))
            stack.enter_context(patch.object(module.B, "save", side_effect=lambda name, data: saved.append(copy.deepcopy(data))))
            stack.enter_context(patch.object(module, "CONDS", [("fixture", 2955, 2.0)]))
            stack.enter_context(patch.object(module, "N", 100))
            stack.enter_context(patch.object(module, "run_condition", return_value=condition_result))
            stack.enter_context(patch("_journal.Journal", MemoryJournal))
            if module is P11:
                stack.enter_context(patch.object(module, "Journal", MemoryJournal))
            module.main()
        return saved[0]

    def test_p11_main_preserves_failed_trial_block_boundary(self):
        arms = {}
        for arm in P11.ALL_ARMS:
            blocks = [block(i, ([None] * 9 + [0]) if i < 5 else [10] * 10, "block")
                      for i in range(10)]
            raw = [v for b in blocks for v in b["ms_rows"]]
            ok = [v for v in raw if v is not None]
            arms[arm] = {"arm": arm, "cert": 2955, "loss": 2.0, "n": 100,
                         "ok": len(ok), "mean": sum(ok) / len(ok), "mean_late": 10,
                         "ms": ok, "ms_rows": raw, "ms_late": [10] * 50,
                         "late_trial_indices": list(range(50, 100)),
                         "probe_rows": [False] * 100, "m_used": [0] * 100,
                         "blocks": blocks, "tail": 0, "srv_recovered": 0,
                         "srv_crc_fail": 0, "srv_stats_present": True, "err": ""}
        result = self.run_main(P11, arms)
        self.assertEqual(result["regret"][0]["regret_holdout_ms"], 0)
        self.assertEqual(result["regret"][0]["matched_block_diagnostic"]["evaluation_ids"], [5, 6, 7, 8, 9])

    def p15_fixture(self):
        arms = {}
        for arm, *_ in P15.FIXED:
            blocks = [block(i, [float(i)] * 10) for i in range(1, 11)]
            values = [v for b in blocks for v in b["ms"]]
            arms[arm] = {"arm": arm, "cert": 2955, "loss": 2.0, "n": 100,
                         "ok": 100, "mean": 5.5, "p95": 10, "tail": 0,
                         "added_bytes_mean": 0, "blocks": blocks, "ms": values,
                         "srv_recovered": 0, "srv_crc_fail": 0,
                         "srv_stats_present": True, "err": ""}
        hist = []
        for i in range(1, 11):
            h = block(i, [float(i)] * 100)
            h.update({"probe_rows": [False] * 100, "m_used": {0: 100},
                      "ips_used": {1280: 100}, "added_bytes_mean": 0,
                      "p_est": 0.02, "err": ""})
            hist.append(h)
        return arms, {"cert": 2955, "loss": 2.0, "rounds": hist,
                      "final": hist[-1], "srv_stats_present": True, "srv_crc_fail": 0}

    def test_p15_main_removes_last_round_vs_five_round_drift(self):
        result = self.run_main(P15, self.p15_fixture())
        regret = result["regret"][0]
        self.assertEqual(regret["regret_ms"], 0)
        self.assertEqual(regret["regret_holdout_ms"], 0)
        self.assertEqual(regret["auto_mean_late"], 8)
        self.assertEqual(regret["auto_final_mean"], 10)
        self.assertEqual(regret["legacy_final_vs_late"]["regret_ms"], 2)
        self.assertEqual(regret["paired_rounds"], 5)

    def test_missing_candidate_or_round_does_not_improve_headline(self):
        for missing in ("candidate", "round"):
            fixture = self.p15_fixture()
            if missing == "candidate":
                fixture[0].pop("m2")
            else:
                fixture[0]["m2"]["blocks"].pop()
            result = self.run_main(P15, fixture)
            self.assertEqual(result["regret"], [])
            self.assertFalse(result["checks"][0]["ok"])

    def test_invalid_p15_block_count_rejected_before_network(self):
        with patch.object(P15, "N", 101), patch.object(P15.B, "set_netem") as network:
            with self.assertRaises(ValueError):
                P15.run_condition(2955, 2.0, 10, MemoryJournal())
            network.assert_not_called()

    def test_p11_acquisition_versions_journal_and_records_failures(self):
        journal = MemoryJournal()
        journal.data["2955|2.0|latin|n100|b10"] = "old-result"
        def client(group, n, **kwargs):
            return [{"ok": i > 0, "ms": 1, "m_used": 0} for i in range(n)], {}, ""
        with contextlib.ExitStack() as stack:
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            stack.enter_context(patch.object(P11, "N", 100))
            stack.enter_context(patch.object(P11.os, "unlink"))
            for name in ("set_netem", "stop_server"):
                stack.enter_context(patch.object(P11.B, name))
            stack.enter_context(patch.object(P11.B, "start_server", return_value=(object(), "unused")))
            stack.enter_context(patch.object(P11.B, "read_server_stats", return_value={"recover_crc_fail": 0}))
            measure = stack.enter_context(patch.object(P11.B, "run_client", side_effect=client))
            result = P11.run_condition(2955, 2.0, journal)
        self.assertEqual(measure.call_count, 50)
        self.assertEqual(result["auto"]["blocks"][0]["ms_rows"][0], None)
        self.assertEqual(result["auto"]["late_trial_indices"][0], 50)
        self.assertTrue(any(key.startswith(PE.PROTOCOL) for key in journal.data))
        self.assertIn("started_at_unix_ns", result["auto"]["blocks"][0])


if __name__ == "__main__":
    unittest.main()
