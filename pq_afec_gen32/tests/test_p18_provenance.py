import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments"))
import p19_provenance as P


def fixture(failed=True):
    segments = []
    accumulated = {"1": [], "2": []}
    for block in range(2):
        for m in (1, 2):
            trials = [{"i": i, "ok": not (failed and block == 0 and m == 1 and i == 1),
                       "ms": value} for i, value in enumerate((10, 20, 30))]
            success = [r["ms"] for r in trials if r["ok"]]
            accumulated[str(m)].extend(success)
            segments.append({"block": block, "m": m, "planned_n": 3,
                             "n": 3, "ok": len(success), "fail": 3 - len(success),
                             "missing": 0, "mean": sum(success) / len(success),
                             "trial_records": trials, "err": ""})
    coverage = {"planned_n": 12, "recorded_n": 12, "ok_n": 11 if failed else 12,
                "failed_n": 1 if failed else 0, "missing_n": 0,
                "planned_segments": 4, "recorded_segments": 4, "complete": not failed}
    return {"arms": [1, 2], "trial_coverage": copy.deepcopy(coverage), "rows": [{
        "cond": "test", "n_per_block": 3, "segments": segments, "err": "",
        "complete": not failed, "trial_coverage": coverage,
        "arms": {m: {"n": len(v), "mean": sum(v) / len(v), "p50": sorted(v)[(len(v)-1)//2],
                      "ms": v} for m, v in accumulated.items()}}]}


class P18ProvenanceTests(unittest.TestCase):
    def test_failure_counts_and_success_conditioned_latency_reproduce(self):
        data = fixture()
        self.assertEqual(P.missing_raw(data, "p18_mmax.json"), [])
        self.assertTrue(all(P.close(a, b) for _, a, b in P.check_p18(data)))
        self.assertFalse(data["trial_coverage"]["complete"])
        self.assertEqual(data["trial_coverage"]["failed_n"], 1)

    def test_complete_successful_fixture_reproduces(self):
        self.assertTrue(all(P.close(a, b) for _, a, b in P.check_p18(fixture(False))))

    def test_edited_segment_or_condition_or_total_counts_are_detected(self):
        for level in ("segment", "condition", "total"):
            with self.subTest(level=level):
                data = fixture()
                if level == "segment":
                    data["rows"][0]["segments"][0]["ok"] = 3
                elif level == "condition":
                    data["rows"][0]["trial_coverage"]["failed_n"] = 0
                else:
                    data["trial_coverage"]["recorded_n"] = 13
                self.assertTrue(any(not P.close(a, b) for _, a, b in P.check_p18(data)))

    def test_falsely_complete_failed_measurement_is_detected(self):
        data = fixture()
        data["rows"][0]["complete"] = True
        data["rows"][0]["trial_coverage"]["complete"] = True
        data["trial_coverage"]["complete"] = True
        wrong = [k for k, a, b in P.check_p18(data) if not P.close(a, b)]
        self.assertEqual(len([k for k in wrong if k.endswith("complete")]), 3)

    def test_forged_success_samples_are_detected_even_if_mean_unchanged(self):
        data = fixture()
        data["rows"][0]["arms"]["1"]["ms"][0] += 1
        data["rows"][0]["arms"]["1"]["ms"][1] -= 1
        self.assertTrue(any(k.endswith("trial_sample_mismatches") and not P.close(a, b)
                            for k, a, b in P.check_p18(data)))

    def test_duplicate_missing_bool_ids_and_nonfinite_times_rejected(self):
        for mutation in ("duplicate", "missing", "bool_id", "nan", "bad_ok"):
            with self.subTest(mutation=mutation):
                data = fixture()
                trials = data["rows"][0]["segments"][0]["trial_records"]
                if mutation == "duplicate":
                    trials[2]["i"] = 0
                elif mutation == "missing":
                    trials.pop()
                elif mutation == "bool_id":
                    trials[0]["i"] = False
                elif mutation == "nan":
                    trials[0]["ms"] = float("nan")
                else:
                    trials[0]["ok"] = 1
                self.assertTrue(P.missing_raw(data, "p18_mmax.json"))

    def test_segment_omission_or_plan_change_is_rejected(self):
        for mutation in ("missing", "duplicate", "plan"):
            with self.subTest(mutation=mutation):
                data = fixture()
                segments = data["rows"][0]["segments"]
                if mutation == "missing":
                    segments.pop()
                elif mutation == "duplicate":
                    segments.append(copy.deepcopy(segments[0]))
                else:
                    segments[0]["planned_n"] = 2
                self.assertTrue(P.missing_raw(data, "p18_mmax.json"))

    def test_old_file_keeps_old_checks_and_reports_missing_trial_scope(self):
        data = fixture()
        del data["trial_coverage"]
        del data["rows"][0]["trial_coverage"]
        for segment in data["rows"][0]["segments"]:
            del segment["trial_records"]
        before = copy.deepcopy(data)
        self.assertEqual(P.check_p18(data), P.check_nested_arms(data))
        self.assertTrue(P.trial_record_limits(data, "p18_mmax.json"))
        self.assertEqual(before, data)


if __name__ == "__main__":
    unittest.main()
