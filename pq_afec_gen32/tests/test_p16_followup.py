"""P16 pure-function and mocked collection regressions. Never execute main."""
import ast
import copy
import datetime
import math
from pathlib import Path
import statistics
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import uuid

EXPERIMENTS = Path(__file__).resolve().parents[1] / "experiments"
sys.path.insert(0, str(EXPERIMENTS))
import blockstat as BST


def pure_functions():
    source = (EXPERIMENTS / "p16_uplink.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name != "main"]
    bed = SimpleNamespace(pctl=lambda values, q: sorted(values)[int(q * (len(values)-1))]
                          if values else None)
    namespace = dict(math=math, statistics=statistics, datetime=datetime, time=time, uuid=uuid,
                     B=bed, BST=BST, W=1280, K=1, N=200, GROUP="x25519", CERT=2000, RTT_MS=50.0)
    exec(compile(ast.Module(body=functions, type_ignores=[]), "p16_pure_helpers", "exec"), namespace)
    return SimpleNamespace(**namespace)


P = pure_functions()


def client_row(index=0, data=1280, parity=1325, ok=True, ms=51.0, **extra):
    return dict(i=index, ok=ok, ms=ms, ips_used=0, ips_eff=0,
                first_flight_bytes=data, first_flight_parity_bytes=parity,
                first_flight_datagrams=1, first_flight_parity_dgrams=1,
                path_rtt_ms=49.0, path_rtt_valid=True, path_rtt_source="quic_ack_min_rtt",
                m_used=1, **extra)


def block(rows, position=0, n_req=None, err=""):
    n_req = len(rows) if n_req is None else n_req
    values = [row["ms"] for row in rows if row["ok"]]
    return dict(client_rows=copy.deepcopy(rows), rate_mbit=10.0, pos=position,
                mean=P.mean(values), err=err,
                denominators=P.trial_denominators(rows, n_req, err),
                collection={"run_id": "run", "unit_id": "unit-%d" % position,
                            "started_at": "fixture-start", "finished_at": "fixture-end"},
                client_stats={"connections": n_req, "extra_client": position},
                server_stats={"n_conns": len(rows), "conn_rows": [{"id": position}],
                              "rx_parity": position})


class ContrastTests(unittest.TestCase):
    def test_four_group_formula_uses_variances_then_one_welch_quantile(self):
        groups = [[3, 5, 8, 11], [1, 2, 3], [6, 12, 15, 21, 24], [2, 4, 6, 8]]
        weights = [1, -1, -1, 1]
        info = P.contrast_ci(groups, weights)
        variances = [statistics.variance(group) / len(group) for group in groups]
        variance = sum(variances)
        df = variance ** 2 / sum(v ** 2 / (len(group)-1) for v, group in zip(variances, groups))
        self.assertAlmostEqual(info["variance"], variance)
        self.assertAlmostEqual(info["df"], df)
        self.assertAlmostEqual(info["half_ms"], BST.t_crit(df) * math.sqrt(variance))
        self.assertAlmostEqual(info["estimate_ms"], sum(w * statistics.mean(g)
                                                        for w, g in zip(weights, groups)))

    def test_halfwidth_quadrature_with_different_df_is_not_used(self):
        groups = [[1, 2, 15], [1, 2, 3, 4, 5, 6], [20, 40, 60, 80], [1, 1, 2, 2, 3, 3, 4]]
        info = P.contrast_ci(groups, [1, -1, -1, 1])
        old = math.hypot(BST.batch_diff_half(groups[0], groups[1]),
                         BST.batch_diff_half(groups[2], groups[3]))
        self.assertGreater(abs(info["half_ms"] - old), .01)

    def test_two_group_helper_agrees_with_existing_pair_formula(self):
        left = [float(i % 13) for i in range(200)]
        right = [float(i % 7) for i in range(400)]
        self.assertAlmostEqual(P.contrast_ci([left, right], [1, -1])["half_ms"],
                               BST.batch_diff_half(left, right), places=12)

    def test_group_order_and_matching_weights_do_not_change_result(self):
        groups = [[1, 4, 9], [4, 5, 7], [8, 10, 12, 15], [2, 3, 4, 6]]
        weights = [1, -1, -1, 1]
        original = P.contrast_ci(groups, weights)
        reverse = P.contrast_ci(list(reversed(groups)), list(reversed(weights)))
        self.assertAlmostEqual(original["half_ms"], reverse["half_ms"])
        self.assertAlmostEqual(original["estimate_ms"], reverse["estimate_ms"])

    def test_coefficient_scaling_scales_halfwidth(self):
        groups = [[1, 4, 9], [4, 5, 7]]
        info = P.contrast_ci(groups, [2, -2])
        reference = P.contrast_ci(groups, [1, -1])
        self.assertAlmostEqual(info["half_ms"], 2 * reference["half_ms"])
        self.assertAlmostEqual(info["df"], reference["df"])

    def test_batch_count_and_unused_tail_are_explicit(self):
        info = P.contrast_ci([[i % 7 for i in range(201)]] * 4, [1, -1, -1, 1])
        self.assertFalse(info["iid_fallback"])
        for group in info["groups"]:
            self.assertEqual((group["n"], group["batch_size"], group["effective_mean_count"],
                              group["unused_batch_tail"]), (201, 14, 14, 5))

    def test_iid_fallback_is_reported_for_short_groups(self):
        info = P.contrast_ci([[1, 2, 3], [4, 5, 7]], [1, -1])
        self.assertTrue(info["iid_fallback"])
        self.assertEqual({g["se_method"] for g in info["groups"]}, {"iid"})

    def test_empty_single_nonfinite_and_wrong_shape_are_unavailable(self):
        for groups, weights in (([], []), ([[1]], [1]), ([[1, math.nan]], [1]),
                                ([[1, math.inf]], [1]), ([[True, 2]], [1]),
                                ([[1, 2]], []), ([[1, 2]], [math.nan])):
            with self.subTest(groups=groups, weights=weights):
                self.assertEqual(P.contrast_ci(groups, weights)["status"], "unavailable")

    def test_constant_groups_do_not_crash_at_zero_variance(self):
        info = P.contrast_ci([[1, 1], [2, 2], [3, 3], [4, 4]], [1, -1, -1, 1])
        self.assertEqual((info["half_ms"], info["variance"], info["df"]), (0.0, 0.0, None))

    def test_inputs_are_not_mutated(self):
        groups = [[1, 2, 3], [5, 8, 9]]
        before = copy.deepcopy(groups)
        P.contrast_ci(groups, [1, -1])
        self.assertEqual(groups, before)


class DenominatorTests(unittest.TestCase):
    def test_complete_counts_include_all_four_denominators(self):
        rows = [client_row(i) for i in range(4)]
        info = P.trial_denominators(rows, 4)
        self.assertTrue(info["complete"])
        self.assertEqual([info[k] for k in ("requested", "returned", "successful", "byte_rows")], [4]*4)

    def test_failed_connection_is_counted_and_not_deleted_from_bytes(self):
        rows = [client_row(0), client_row(1, ok=False, ms=10000)]
        info = P.trial_denominators(rows, 2)
        self.assertEqual((info["returned"], info["successful"], info["failed"], info["byte_rows"]),
                         (2, 1, 1, 2))
        self.assertFalse(info["complete"])

    def test_returned_missing_and_excess_rows_are_separate(self):
        self.assertEqual(P.trial_denominators([client_row()], 2)["missing_returned"], 1)
        self.assertEqual(P.trial_denominators([client_row(), client_row(1)], 1)["excess_returned"], 1)

    def test_missing_successful_latency_does_not_change_success_count(self):
        row = client_row()
        del row["ms"]
        info = P.trial_denominators([row], 1)
        self.assertEqual((info["successful"], info["successful_latency_rows"], info["missing_successful_latency"]),
                         (1, 0, 1))
        self.assertFalse(info["complete"])

    def test_nonfinite_latency_and_nonboolean_success_cannot_look_complete(self):
        for changed in ({"ms": math.nan}, {"ms": math.inf}, {"ms": True}, {"ok": 1}):
            with self.subTest(changed=changed):
                row = client_row()
                row.update(changed)
                self.assertFalse(P.trial_denominators([row], 1)["complete"])

    def test_missing_parity_is_not_replaced_with_zero(self):
        row = client_row()
        del row["first_flight_parity_bytes"]
        evidence = P.byte_evidence([row])
        self.assertEqual(evidence["parity_bytes"], [None])
        self.assertEqual(evidence["total_bytes"], [None])
        self.assertIsNone(evidence["total_bytes_median"])
        self.assertFalse(P.trial_denominators([row], 1)["complete"])

    def test_byte_values_must_be_nonnegative_integers(self):
        for value in (-1, True, 1280.0, math.nan):
            with self.subTest(value=value):
                self.assertEqual(P.byte_evidence([client_row(data=value)])["n_missing"], 1)

    def test_process_error_prevents_complete_even_with_all_rows(self):
        self.assertFalse(P.trial_denominators([client_row()], 1, "exit 1")["complete"])


class MergeTests(unittest.TestCase):
    def merge(self, blocks):
        return P.merge_blocks(blocks, "m1", "on", 1, 0, "10Mbps")

    def test_median_and_added_bytes_use_both_blocks(self):
        first = block([client_row(0, parity=0), client_row(1, parity=0)], 0)
        second = block([client_row(0, parity=1325), client_row(1, parity=1325)], 7)
        merged = self.merge([first, second])
        self.assertEqual(merged["ff_bytes_med"], 2605)
        self.assertEqual(merged["added_bytes"], 1325)
        self.assertEqual(merged["byte_evidence"]["total_bytes"], [1280, 1280, 2605, 2605])

    def test_full_rows_rtt_k_and_unknown_fields_survive(self):
        row = client_row(first_flight_datagrams_override=2, extra_nested={"kept": True})
        row["first_flight_datagrams"] = 2
        blocks = [block([row], 0), block([client_row()], 7)]
        merged = self.merge(blocks)
        self.assertEqual(merged["client_rows"][0], row)
        self.assertEqual(merged["ips_evidence"]["observations"][0], row)
        self.assertEqual(merged["ips_evidence"]["observations_scope"], "full_client_json_rows")

    def test_collection_range_ids_stats_and_counts_align(self):
        merged = self.merge([block([client_row(0), client_row(1)], 0), block([client_row()], 7)])
        units = merged["collection_units"]
        self.assertEqual([(u["row_start"], u["row_stop"]) for u in units], [(0, 2), (2, 3)])
        self.assertEqual([u["collection"]["unit_id"] for u in units], ["unit-0", "unit-7"])
        self.assertEqual([u["server_stats"]["conn_rows"] for u in units], [[{"id": 0}], [{"id": 7}]])
        self.assertTrue(all(not u["server_connection_completeness_verified"] for u in units))

    def test_missing_second_block_cannot_be_hidden_by_first_block_summary(self):
        first = block([client_row()], 0)
        second = block([], 7, n_req=1)
        merged = self.merge([first, second])
        self.assertEqual((merged["n_req"], merged["n"], merged["ok"]), (2, 1, 1))
        self.assertFalse(merged["denominators"]["complete"])

    def test_missing_and_excess_in_separate_units_do_not_cancel(self):
        first = block([client_row(i) for i in range(199)], 0, n_req=200)
        second = block([client_row(i) for i in range(201)], 7, n_req=200)
        merged = self.merge([first, second])
        self.assertEqual((merged["n_req"], merged["n"], merged["ok"]), (400, 400, 400))
        coverage = merged["denominators"]
        self.assertEqual((coverage["missing_returned"], coverage["excess_returned"]), (1, 1))
        self.assertEqual((coverage["aggregate_missing_returned"], coverage["aggregate_excess_returned"]), (0, 0))
        self.assertEqual(coverage["incomplete_units"], 2)
        self.assertFalse(coverage["complete"])

    def test_failed_rows_remain_in_byte_and_client_evidence(self):
        merged = self.merge([block([client_row()], 0), block([client_row(ok=False)], 7)])
        self.assertEqual((merged["n"], merged["ok"], len(merged["ms"])), (2, 1, 1))
        self.assertEqual(len(merged["byte_evidence"]["total_bytes"]), 2)
        self.assertFalse(merged["client_rows"][1]["ok"])

    def test_merge_preserves_inputs_and_both_process_errors(self):
        blocks = [block([client_row()], 0, err="first"), block([client_row()], 7, err="second")]
        before = copy.deepcopy(blocks)
        merged = self.merge(blocks)
        self.assertEqual(blocks, before)
        self.assertEqual(merged["err"], "first | second")

    def test_empty_block_list_is_rejected(self):
        with self.assertRaises(ValueError):
            self.merge([])


class CollectionTests(unittest.TestCase):
    def bed(self, rows, err=""):
        return SimpleNamespace(pctl=P.B.pctl, set_netem=Mock(),
                               start_server=Mock(return_value=("fake", "fake-server.json")),
                               run_client=Mock(return_value=(rows, {"full_client": [1, 2]}, err)),
                               stop_server=Mock(), read_server_stats=Mock(return_value={"full_server": {"rows": [1, 2]}}))

    def collect(self, bed):
        old = P.run_arm.__globals__["B"]
        P.run_arm.__globals__["B"] = bed
        try:
            return P.run_arm("m1", "on", 1, 0, 10, 10, run_id="synthetic", block_pos=4)
        finally:
            P.run_arm.__globals__["B"] = old

    def test_mock_collection_keeps_full_client_and_server_data(self):
        bed = self.bed([client_row(i) for i in range(200)])
        collected = self.collect(bed)
        self.assertEqual(collected["client_stats"], {"full_client": [1, 2]})
        self.assertEqual(collected["server_stats"], {"full_server": {"rows": [1, 2]}})
        self.assertEqual(len(collected["client_rows"]), 200)
        self.assertTrue(collected["denominators"]["complete"])
        bed.read_server_stats.assert_called_once_with("fake-server.json")
        bed.stop_server.assert_called_once_with("fake")

    def test_unit_id_time_run_and_actual_k_are_retained(self):
        rows = [client_row(i) for i in range(200)]
        rows[0]["first_flight_datagrams"] = 2
        collected = self.collect(self.bed(rows))
        meta = collected["collection"]
        self.assertEqual((meta["run_id"], meta["block_position"]), ("synthetic", 4))
        self.assertEqual(len(meta["unit_id"]), 32)
        self.assertLessEqual(meta["started_at_ns"], meta["finished_at_ns"])
        self.assertIsNotNone(datetime.datetime.fromisoformat(meta["started_at"]).tzinfo)
        self.assertEqual(collected["ips_evidence"]["observations"][0]["first_flight_datagrams"], 2)

    def test_successful_missing_latency_is_success_but_not_complete(self):
        rows = [client_row(i) for i in range(200)]
        del rows[0]["ms"]
        collected = self.collect(self.bed(rows))
        self.assertEqual((collected["ok"], len(collected["ms"])), (200, 199))
        self.assertFalse(collected["denominators"]["complete"])

    def test_collection_failure_still_stops_mock_server(self):
        bed = self.bed([])
        bed.run_client.side_effect = RuntimeError("synthetic client failure")
        with self.assertRaises(RuntimeError):
            self.collect(bed)
        bed.stop_server.assert_called_once_with("fake")


class ContractTests(unittest.TestCase):
    def test_performance_constants_and_collection_size_are_unchanged(self):
        tree = ast.parse((EXPERIMENTS / "p16_uplink.py").read_text(encoding="utf-8"))
        constants = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
                     if isinstance(node, ast.Assign) and len(node.targets) == 1
                     and isinstance(node.targets[0], ast.Name)
                     and node.targets[0].id in {"N", "K", "W", "RULER_MS", "RTT_MS", "CERT", "ARMS"}}
        self.assertEqual({name: constants[name] for name in ("N", "K", "W", "RULER_MS", "RTT_MS", "CERT")},
                         {"N": 200, "K": 1, "W": 1280, "RULER_MS": .25, "RTT_MS": 50.0, "CERT": 2000})
        self.assertEqual(constants["ARMS"], [("base", "off", 0, 0), ("pad", "off", 0, 1452),
                                            ("m1", "on", 1, 0), ("m2", "on", 2, 0)])


if __name__ == "__main__":
    unittest.main()
