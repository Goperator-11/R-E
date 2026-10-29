"""Pure provenance and completeness regressions, without experiment imports."""
import ast
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
import tempfile
from types import SimpleNamespace
import unittest


EXPERIMENTS = Path(__file__).resolve().parents[1] / "experiments"


def pure(filename, names, assignments=(), **namespace):
    tree = ast.parse((EXPERIMENTS / filename).read_text(encoding="utf-8"))
    nodes = [node for node in tree.body
             if (isinstance(node, ast.FunctionDef) and node.name in names)
             or (isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id in assignments
                         for t in node.targets))]
    if {node.name for node in nodes if isinstance(node, ast.FunctionDef)} != set(names):
        raise AssertionError("pure function missing")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), filename, "exec"), namespace)
    return namespace


P8 = pure("p8_stability.py", {"trial_record", "unit_source", "input_coverage", "netem_counts"},
          math=math)
P20 = pure("p20_residual.py", {"input_manifest", "selected_p17_units", "p17_success_blocks", "source_coverage",
                              "p16_pad_input",
                              "residual_report", "analyse_condition", "mean", "se", "sd",
                              "trimmed_mean", "z_of", "diff_ci", "n_needed", "wilson", "classify"},
           assignments={"INPUT_FILES", "P17_CONDITIONS", "P18_CONDITIONS"},
           json=json, hashlib=hashlib, os=os, math=math, statistics=statistics, ALPHA=.05)


def fixture():
    data = {"p15": {"n": 4, "rows": []}, "p16": {"n": 2, "arms": []},
            "p17": {"cycles": 5, "n_per_seg": 2, "rows": []},
            "p18": {"n": 12, "rows": []}}
    conds = {}

    def analysed(stage, name, loss, arm, n):
        key = "%s|%s|loss%g" % (stage, name, loss)
        conds.setdefault(key, {"cond": key, "source": stage, "arms": [], "pairs": []})
        conds[key]["arms"].append({"arm": arm, "n": n, "model": {"j_ms": 50},
                                  "class_residual": {}})

    for cert in (2955, 4032):
        for loss in (0., 2., 5.):
            for arm in ("m0", "m1", "m2"):
                data["p15"]["rows"].append({"cert": cert, "loss": loss, "arm": arm,
                                             "n": 4, "ok": 4, "ms": [50.] * 4})
                analysed("p15", "cert%d" % cert, loss, arm, 4)
    for cond in ("무제한", "10Mbps"):
        for arm in ("base", "pad", "m1", "m2"):
            record = {"cond": cond, "arm": arm, "n": 4, "ok": 4,
                      "ms": [50.] * 4, "err": ""}
            if arm == "pad":
                record["ips_evidence"] = {
                    "requested_ips": 1452, "base_ips": 1280, "expected_k": 1,
                    "fec": "off", "configured_m": 0, "n_req": 4, "n_rows": 4,
                    "observations": [{"ok": True, "ips_used": 1452, "ips_eff": 1452,
                                      "first_flight_datagrams": 1, "first_flight_bytes": 1452,
                                      "first_flight_parity_dgrams": 0} for _ in range(4)]}
            data["p16"]["arms"].append(record)
            analysed("p16", cond, 0., arm, 4)
    for name in P20["P17_CONDITIONS"]:
        row = {"cond": name, "arms": {"auto": {"ms": [50.] * 20}}, "segments": []}
        for arm in ("m0", "m1", "m2", "m3"):
            row["arms"][arm] = {"ms": [50.] * 20}
            for cycle in range(5):
                for loss in (2., 15.):
                    row["segments"].append({"arm": arm, "loss": loss, "n": 2, "ok": 2, "mean": 50.})
            for loss in (2., 15.):
                analysed("p17", name, loss, arm, 10)
        data["p17"]["rows"].append(row)
    for index, name in enumerate(P20["P18_CONDITIONS"]):
        nblock = 40 if index == 0 else 36 if index == 1 else 12
        loss = 0. if index == 0 else 15. if index in (1, 2, 4) else 2.
        row = {"cond": name, "loss": loss, "n_per_block": nblock, "arms": {}, "segments": []}
        for m in range(1, 5):
            row["arms"][str(m)] = {"n": nblock * 4, "ms": [50.] * (nblock * 4)}
            for block in range(4):
                row["segments"].append({"m": m, "n": nblock})
            analysed("p18", name, loss, "m%d" % m, nblock * 4)
        data["p18"]["rows"].append(row)
    return data, list(conds.values())


class P8RawAccounting(unittest.TestCase):
    def record(self, rows, requested=3, err=""):
        summary = {"n": len(rows), "ok": sum(isinstance(r, dict) and r.get("ok") is True for r in rows)}
        return P8["trial_record"](requested, rows, {"counter": 7}, err, summary,
                                  {"recover_crc_fail": 0}, {"run_id": "new"})

    def test_failures_and_missing_rows_keep_original_raw_data(self):
        rows = [{"ok": True, "ms": 51.}, {"ok": False, "err": "timeout"}]
        out = self.record(rows)
        self.assertEqual(out["raw_client_rows"], rows)
        self.assertEqual(out["samples"], [51.])
        c = out["trial_coverage"]
        self.assertEqual((c["requested_n"], c["returned_n"], c["successful_n"], c["failed_n"], c["missing_n"]), (3, 2, 1, 1, 1))
        self.assertFalse(c["complete"])

    def test_complete_data_does_not_hide_client_error_or_invalid_latency(self):
        rows = [{"ok": True, "ms": 51.} for _ in range(3)]
        self.assertTrue(self.record(rows)["trial_coverage"]["complete"])
        self.assertFalse(self.record(rows, err="client error")["trial_coverage"]["complete"])
        for bad in (None, float("nan"), -1, True):
            r = copy.deepcopy(rows)
            r[0]["ms"] = bad
            self.assertFalse(self.record(r)["trial_coverage"]["complete"])

    def test_unknown_old_unit_remains_incomplete(self):
        unit = {"kind": "old", "record": {"ok": 3, "unit_source": {"journal_key": "old"}}}
        out = P8["input_coverage"]([unit], 1, 3)
        self.assertFalse(out["complete"])
        self.assertIn("no preserved denominators", out["problems"][0])

    def test_duplicate_or_incomplete_units_cannot_pass(self):
        record = self.record([{"ok": True, "ms": 51.} for _ in range(3)])
        record["unit_source"] = {"journal_key": "a"}
        unit = {"kind": "new", "record": record}
        self.assertTrue(P8["input_coverage"]([unit], 1, 3)["complete"])
        self.assertFalse(P8["input_coverage"]([unit, unit], 2, 6)["complete"])
        self.assertFalse(P8["input_coverage"]([unit], 2, 6)["complete"])

    def test_old_provenance_is_preserved_without_inventing_time(self):
        rec = {"n": 3}
        jr = SimpleNamespace(fingerprint="fp", run_id="new", has=lambda key: True,
                             provenance=lambda keys: {"units": [{"key": keys[0], "run_id": "old", "recorded_at": None, "reused": True}]})
        out = P8["unit_source"](rec, jr, "key", True)
        self.assertEqual(out["unit_source"]["run_id"], "old")
        self.assertIsNone(out["unit_source"]["recorded_at"])
        self.assertNotIn("raw_client_rows", out)
        self.assertEqual(rec, {"n": 3})

    def test_netem_uses_packet_denominator_and_preserves_raw_output(self):
        raw = "qdisc netem 1: root\n Sent 12345 bytes 95 pkt (dropped 5, overlimits 0 requeues 0)"
        out = P8["netem_counts"](raw)
        self.assertEqual(out["total_packets"], 100)
        self.assertEqual(out["effective_loss"], .05)
        self.assertEqual(out["raw_tc_output"], raw)
        self.assertIsNone(P8["netem_counts"]("no counters")["effective_loss"])


class P20Coverage(unittest.TestCase):
    def test_p17_failure_does_not_shift_latencies_between_loss_segments(self):
        row = {"arms": {"m0": {"ms": [50.] * 4 + [10., 90., 50., 50., 50., 50.] + [50.] * 6}},
               "segments": [
                   {"arm": "m0", "loss": 15., "n": 6, "ok": 4, "mean": 50.},
                   {"arm": "m0", "loss": 2., "n": 6, "ok": 6, "mean": 50.},
                   {"arm": "m0", "loss": 15., "n": 6, "ok": 6, "mean": 50.}]}
        blocks = P20["p17_success_blocks"](row, "m0")
        low = [x for segment, block in blocks if segment["loss"] == 2. for x in block]
        high = [x for segment, block in blocks if segment["loss"] == 15. for x in block]
        self.assertEqual(low, [10., 90., 50., 50., 50., 50.])
        self.assertEqual(high, [50.] * 10)
        for change in (lambda r: r["segments"][0].pop("ok"),
                       lambda r: r["segments"][0].update(mean=51.),
                       lambda r: r["arms"]["m0"]["ms"].append(50.),
                       lambda r: r["arms"]["m0"]["ms"].pop()):
            broken = copy.deepcopy(row)
            change(broken)
            with self.assertRaises(ValueError):
                P20["p17_success_blocks"](broken, "m0")

    def test_complete_existing_design_preserves_success_and_attempt_counts(self):
        data, conds = fixture()
        out = P20["source_coverage"](data, conds)
        self.assertTrue(out["complete"], out["problems"])
        self.assertEqual((out["analysed_conditions"], out["analysed_arms"]), (21, 78))

    def test_missing_input_condition_arm_segment_or_duplicate_fails_closed(self):
        for change in (lambda d, c: d.pop("p15"),
                       lambda d, c: d["p15"]["rows"].pop(),
                       lambda d, c: d["p17"]["rows"][0]["arms"].pop("m3"),
                       lambda d, c: d["p17"]["rows"][0]["segments"].pop(),
                       lambda d, c: d["p16"]["arms"].append(copy.deepcopy(d["p16"]["arms"][0])),
                       lambda d, c: c.pop()):
            data, conds = fixture()
            change(data, conds)
            self.assertFalse(P20["source_coverage"](data, conds)["complete"])

    def test_invalid_latency_or_request_denominator_is_not_complete(self):
        for change in (lambda d: d["p15"]["rows"][0]["ms"].pop(),
                       lambda d: d["p16"]["arms"][0].update(n=3),
                       lambda d: d["p18"]["rows"][0].update(n_per_block=39),
                       lambda d: d["p16"]["arms"][1].pop("ips_evidence"),
                       lambda d: d["p16"].update(n=True),
                       lambda d: d["p15"]["rows"][0]["ms"].__setitem__(0, float("nan"))):
            data, conds = fixture()
            change(data)
            self.assertFalse(P20["source_coverage"](data, conds)["complete"])

    def test_recorded_timeout_remains_separate_from_success_latency(self):
        data, conds = fixture()
        row = data["p18"]["rows"][1]
        row["arms"]["1"]["n"] -= 1
        row["arms"]["1"]["ms"].pop()
        name = "p18|%s|loss15" % row["cond"]
        next(a for c in conds if c["cond"] == name for a in c["arms"] if a["arm"] == "m1")["n"] -= 1
        out = P20["source_coverage"](data, conds)
        self.assertTrue(out["complete"], out["problems"])
        self.assertEqual(out["expected"][name]["m1"]["failed_n"], 1)

    def test_input_error_blocks_pass_without_changing_three_numeric_checks(self):
        data, conds = fixture()
        plain = P20["residual_report"](conds)
        coverage = P20["source_coverage"](data, conds, ["missing file"])
        out = P20["residual_report"](conds, input_coverage=coverage)
        self.assertEqual(plain["checks"], out["checks"][:3])
        self.assertFalse(out["checks"][-1]["ok"])
        self.assertEqual(out["total"], 4)

    def test_exact_journal_generation_and_condition_set_are_required(self):
        units = [{"fp": "expected", "key": name, "val": {"cond": name}} for name in P20["P17_CONDITIONS"]]
        meta = {"journal_fp": "expected"}
        self.assertEqual(P20["selected_p17_units"](meta, units)[1], units)
        for altered in (units[:-1], units + [units[0]], units + [{"fp": "other", "key": "x", "val": {"cond": "x"}}]):
            with self.assertRaises(ValueError):
                P20["selected_p17_units"](meta, altered)

    def test_input_sha_and_journal_unit_source_match_consumed_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            units = [{"fp": "fp", "key": name, "run_id": "old", "recorded_at": "old-time", "val": {"cond": name}}
                     for name in P20["P17_CONDITIONS"]]
            for stage, filename in P20["INPUT_FILES"].items():
                value = {"journal_fp": "fp", "rows": [u["val"] for u in units]} if stage == "p17" else {}
                (root / filename).write_text(json.dumps(value), encoding="utf-8")
            raw_journal = "\n".join(json.dumps(u) for u in units)
            (root / "p17_units.jsonl").write_text(raw_journal, encoding="utf-8")
            data, provenance, errors = P20["input_manifest"](temp, temp)
            self.assertFalse(errors)
            for stage, filename in P20["INPUT_FILES"].items():
                self.assertEqual(provenance[stage]["sha256"], hashlib.sha256((root / filename).read_bytes()).hexdigest())
            selected = provenance["p17"]["journal_selection"]
            self.assertEqual(selected["fingerprint"], "fp")
            self.assertEqual(selected["units"][0]["run_id"], "old")
            (root / P20["INPUT_FILES"]["p15"]).unlink()
            self.assertTrue(P20["input_manifest"](temp, temp)[2])


class P20TargetSource(unittest.TestCase):
    def test_zero_model_effect_uses_observed_target_without_claiming_model_effect(self):
        before = P20.get("model_arm")
        P20["model_arm"] = lambda *args, **kwargs: {"j_ms": 50., "P_ontime": 1., "P_extra": 0., "P_timeout": 0.}
        try:
            out = P20["analyse_condition"]("fixture", "x25519", 2000, 50., 0., 1., 0.,
                                           {"m0": {"m": 0, "ms": [50., 51., 52., 53.]},
                                            "m1": {"m": 1, "ms": [51., 52., 53., 54.]}}, "p16")
            pair = out["pairs"][0]
            self.assertEqual(pair["n_target_source"], "observed_same_data_delta")
            self.assertEqual(pair["n_target_delta_ms"], pair["meas_delta_ms"])
            self.assertEqual(pair["n_needed_per_arm"], P20["n_needed"]([50., 51., 52., 53.], [51., 52., 53., 54.], -1.))
            report = P20["residual_report"]([out])
            self.assertEqual(report["sample_target_counts"]["all"]["observed_same_data_delta"], 1)
        finally:
            P20["model_arm"] = before


if __name__ == "__main__":
    unittest.main()
