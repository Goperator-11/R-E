import contextlib
import io
import math
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments"))
import p7_verify as P7


def case_record(number, n=4):
    slow = number in (2, 3, 6, 7, 9)
    dropped = 2 if number == 9 else int(number >= 2)
    return {
        "case": "V%d synthetic" % number,
        "fec": "off" if number in (1, 2, 3) else "on",
        "m": 2 if number == 8 else 1,
        "drop_initial": "0,1" if dropped == 2 else ("0" if dropped else ""),
        "drop_parity": 0 if number == 6 else -1,
        "corrupt_parity": 0 if number == 7 else -1,
        "planned_n": n, "n": n, "ok": n, "fail": 0,
        "p50": 100.0 if slow else 50.0,
        "p95": 110.0 if slow else 55.0,
        "max": 120.0 if slow else 60.0, "pto_share": 0.0,
        "cli_dropped_orig": n * dropped,
        "cli_dropped_par": n if number == 6 else 0,
        "cli_corrupt_par": n if number == 7 else 0,
        "cli_parity_sent": 0 if number in (1, 2, 3, 6) else n,
        "srv_recovered": n if number in (4, 5, 8) else 0,
        "srv_late": 0, "srv_crc_fail": n if number == 7 else 0,
        "srv_unrecover": 0, "srv_refused": 0,
        "srv_bytes_in": 100000, "srv_bytes_to_stack": 99000, "err": "",
    }


def classify(cases):
    saved = []
    with mock.patch.multiple(P7.B, harden=mock.DEFAULT, require_root=mock.DEFAULT,
                             require_bin=mock.DEFAULT, setup=mock.DEFAULT), \
            mock.patch.object(P7, "run_case", side_effect=cases), \
            mock.patch.object(P7, "amplification_wire_check",
                              return_value={"ok": True}), \
            mock.patch.object(P7.B, "save", side_effect=lambda _, value:
                              saved.append(value) or "synthetic.json"), \
            contextlib.redirect_stdout(io.StringIO()):
        rc = P7.main()
    return rc, saved[0]


class P7ClassificationAudit(unittest.TestCase):
    def cases(self):
        return [case_record(i) for i in range(10)]

    def test_complete_synthetic_control_passes(self):
        rc, result = classify(self.cases())
        self.assertEqual(rc, 0)
        self.assertEqual(result["passed"], result["total"])

    def test_empty_or_partial_trials_fail_overall(self):
        for count in (0, 3):
            with self.subTest(count=count):
                cases = self.cases()
                cases[0].update(n=count, ok=count)
                rc, result = classify(cases)
                self.assertEqual(rc, 1)
                self.assertFalse(result["checks"][0]["ok"])

    def test_missing_server_or_client_counters_are_incomplete(self):
        for field in ("srv_recovered", "srv_late", "srv_crc_fail", "srv_refused",
                      "srv_unrecover", "srv_bytes_in", "srv_bytes_to_stack",
                      "cli_dropped_orig", "cli_dropped_par", "cli_corrupt_par",
                      "cli_parity_sent"):
            for value in (None, -1, True, 0.5, math.inf, math.nan):
                with self.subTest(field=field, value=value):
                    case = case_record(0)
                    case[field] = value
                    self.assertFalse(P7.case_complete(case))

    def test_required_trial_counts_cannot_be_omitted_or_negative(self):
        for field in ("planned_n", "n", "ok", "fail"):
            case = case_record(0)
            del case[field]
            with self.subTest(field=field):
                self.assertFalse(P7.case_complete(case))
        case = case_record(0)
        case.update(ok=5, fail=-1)
        self.assertFalse(P7.case_complete(case))

    def test_process_error_rejects_otherwise_complete_results(self):
        cases = self.cases()
        cases[4]["err"] = "timeout(rc124)"
        self.assertEqual(classify(cases)[0], 1)

    def test_missing_server_stats_cannot_pass_zero_accounting(self):
        cases = self.cases()
        for key in cases[0]:
            if key.startswith("srv_"):
                cases[0][key] = None
        rc, result = classify(cases)
        self.assertEqual(rc, 1)
        self.assertFalse(next(c["ok"] for c in result["checks"]
                              if c["check"].startswith("V10 ")))

    def test_nonfinite_timing_or_empty_server_traffic_is_incomplete(self):
        for field, value in (("p50", math.nan), ("p95", math.inf),
                             ("max", -1), ("pto_share", 1.1),
                             ("srv_bytes_in", 0), ("srv_bytes_to_stack", 0)):
            with self.subTest(field=field):
                case = case_record(0)
                case[field] = value
                self.assertFalse(P7.case_complete(case))

    def test_late_recovery_is_already_in_total(self):
        cases = self.cases()
        cases[4]["srv_late"] = 2
        self.assertEqual(classify(cases)[0], 0)

    def test_late_recovery_cannot_fill_missing_total_recoveries(self):
        cases = self.cases()
        cases[4].update(srv_recovered=2, srv_late=2)
        self.assertEqual(classify(cases)[0], 1)

    def test_every_planned_erasure_or_corruption_must_be_injected(self):
        for case_index, counter in ((2, "cli_dropped_orig"),
                                    (4, "cli_dropped_orig"),
                                    (6, "cli_dropped_par"),
                                    (7, "cli_corrupt_par"),
                                    (9, "cli_dropped_orig")):
            with self.subTest(case=case_index, counter=counter):
                cases = self.cases()
                cases[case_index][counter] -= 1
                self.assertEqual(classify(cases)[0], 1)

    def test_all_failed_v9_is_allowed_but_failed_v2_is_not(self):
        for number, expected in ((9, 0), (2, 1)):
            with self.subTest(case=number):
                cases = self.cases()
                cases[number].update(ok=0, fail=4, p50=None, p95=None, max=None,
                                     pto_share=None)
                self.assertEqual(classify(cases)[0], expected)


class P7RawRecordAudit(unittest.TestCase):
    def run_rows(self, rows, client_stats=None, server_stats=None):
        client_stats = ({"dropped_originals": 0, "dropped_parities": 0,
                         "corrupted_parities": 0, "parity_sent": 2}
                        if client_stats is None else client_stats)
        server_stats = ({"recovered": 0, "late_recovered": 0,
                         "recover_crc_fail": 0, "unrecoverable_seen": 0,
                         "recover_refused_by_accounting": 0,
                         "bytes_in": 10000, "bytes_to_stack": 10000}
                        if server_stats is None else server_stats)
        with mock.patch.object(P7.B, "set_netem"), \
                mock.patch.object(P7.B, "start_server", return_value=(object(), "stats")), \
                mock.patch.object(P7.B, "run_client", return_value=(rows, client_stats, "")), \
                mock.patch.object(P7.B, "stop_server"), \
                mock.patch.object(P7.B, "read_server_stats", return_value=server_stats):
            return P7.run_case("V0 synthetic", "on", 1, n=2)

    def test_two_distinct_raw_trials_pass(self):
        rows = [{"i": i, "ok": True, "ms": 50.0} for i in range(2)]
        self.assertTrue(P7.case_complete(self.run_rows(rows)))

    def test_raw_missing_duplicate_and_malformed_trials_fail(self):
        first = {"i": 0, "ok": True, "ms": 50.0}
        for rows in ([], [first], [first, first],
                     [first, {"i": 2, "ok": True, "ms": 50.0}],
                     [first, {"i": 1, "ok": "true", "ms": 50.0}],
                     [first, {"i": 1, "ok": True}],
                     [first, {"i": 1, "ok": True, "ms": math.nan}]):
            with self.subTest(rows=rows):
                result = self.run_rows(rows)
                self.assertTrue(result["err"])
                self.assertFalse(P7.case_complete(result))

    def test_raw_missing_stats_fail_with_complete_trials(self):
        rows = [{"i": i, "ok": True, "ms": 50.0} for i in range(2)]
        for kwargs in ({"client_stats": {}}, {"server_stats": {}}):
            with self.subTest(kwargs=kwargs):
                self.assertFalse(P7.case_complete(self.run_rows(rows, **kwargs)))


class P7WireObservationAudit(unittest.TestCase):
    def observe(self, samples, rc=0):
        base = {"rx_bytes": 1000, "tx_bytes": 1000}
        readings = [base] + [None if x is None else
                            {"rx_bytes": 1000 + x[0], "tx_bytes": 1000 + x[1]}
                            for x in samples]
        client = mock.Mock()
        client.wait.return_value = rc
        with mock.patch.object(P7.B, "set_netem"), \
                mock.patch.object(P7.B, "start_server", return_value=(object(), "stats")), \
                mock.patch.object(P7.B, "stop_server"), \
                mock.patch.object(P7.B, "require_bin", return_value="qamp"), \
                mock.patch.object(P7, "link_counters", side_effect=readings), \
                mock.patch.object(P7.subprocess, "Popen", return_value=client), \
                mock.patch.object(P7.time, "sleep"):
            return P7.amplification_wire_check()

    def test_complete_bidirectional_observation_is_auxiliary_only(self):
        result = self.observe([(100, 200)] * 25)
        self.assertTrue(result["ok"])
        self.assertEqual(result["measurement_layer"], "L2")
        self.assertFalse(result["rfc_compliance_verified"])
        self.assertFalse(result["address_validation_tracked"])

    def test_partial_silent_failed_or_reset_observations_fail(self):
        scenarios = (([None] * 24 + [(100, 200)], 0),
                     ([(100, 0)] * 25, 0),
                     ([(100, 200)] * 25, 1),
                     ([(100, 200)] * 24 + [(99, 200)], 0),
                     ([(0, 20)] + [(100, 200)] * 24, 0),
                     ([(100, 301)] * 25, 0))
        for samples, rc in scenarios:
            with self.subTest(samples=samples, rc=rc):
                self.assertFalse(self.observe(samples, rc)["ok"])


if __name__ == "__main__":
    unittest.main()
