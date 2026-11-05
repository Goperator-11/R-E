import copy
import json
from pathlib import Path, PureWindowsPath
import tempfile
import unittest
from unittest.mock import patch

from experiments.v33 import bench_j7_family as family, bench_j7_report as report, bench_report


def relocated_shard(directory):
    root = Path(__file__).resolve().parents[1]
    inputs = root / "g3/v33/fixtures/S5_test_inputs_v1/j7"
    plan = family.collector.read(family.collector.PLAN)
    plan["raw_root"] = str(Path(directory) / "raw")
    plan["baseline_root"] = str(Path(directory) / "fixed")
    plan["protocols"]["wire39"]["seeds"] = [31]
    policy = plan["policies"]["j7"]
    old_root = PureWindowsPath(policy["fingerprint"]["source_root"])
    new_root = root / "g3/v33/policy_snapshots/J7_v1"
    policy["fingerprint"]["source_root"] = str(new_root)
    protocol_sha = family.bench.digest(plan["protocols"]["wire39"])
    plan_sha = family.bench.digest(plan)
    job = ["wire39", "j7", "c1", "B1"]
    folder = Path(plan["raw_root"]) / "_".join(job)
    folder.mkdir(parents=True)
    fixed_path = Path(plan["baseline_root"]) / "wire39/B1/seed00031.json"
    fixed_path.parent.mkdir(parents=True)
    fixed = family.read(inputs / "fixed.json")
    fixed.update(trace_path=str(inputs / "fixed.jsonl.gz"), protocol_sha256=protocol_sha)
    fixed_path.write_text(json.dumps(fixed), encoding="utf-8")
    run = family.read(inputs / "run.json")
    run.update(trace_path=str(inputs / "run.jsonl.gz"), protocol_sha256=protocol_sha,
               counterfactual_trace_path=fixed["trace_path"], baseline_path=str(fixed_path),
               baseline_sha256=family.bench.file_hash(fixed_path), source_sha256=family.collector.sources(),
               policy_fingerprint=policy["fingerprint"], plan_sha256=plan_sha)
    def relocate(path):
        return str(new_root.joinpath(*PureWindowsPath(path).relative_to(old_root).parts))
    for audit in (run["policy_audit"], run["policy_initial"]["audit"]):
        audit["source_root"] = str(new_root)
        audit["source_sha256"] = {relocate(p): sha for p, sha in audit["source_sha256"].items()}
        audit["actual_module_paths"] = {name: relocate(p) for name, p in audit["actual_module_paths"].items()}
        for value in audit["loaded_modules"].values():
            value["path"] = relocate(value["path"])
    target = folder / "seed00031.json"
    target.write_text(json.dumps(run), encoding="utf-8")
    (folder / "seed00031.stderr.txt").write_text("", encoding="utf-8")
    manifest = dict(schema=family.collector.SCHEMA, plan_sha256=plan_sha, job=job,
                    mode="full", seeds=[31], source_sha256=family.collector.sources(), policy=policy,
                    protocol_sha256=protocol_sha)
    manifest_path = folder / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    finished = dict(status="complete", job=job, seeds=[31], manifest_sha256=family.bench.file_hash(manifest_path),
                    results_sha256={str(target): family.bench.file_hash(target)})
    (folder / "finished.json").write_text(json.dumps(finished), encoding="utf-8")
    return plan, plan_sha, target, run, job


class J7ReportTests(unittest.TestCase):
    def plan(self):
        return {"protocols": {p: {"scenarios": [{"id": f"B{i}"} for i in range(15)], "seeds": list(range(31, 51))}
                              for p in ("wire39", "wire46")}, "policies": {"l1": {}, "j7": {}},
                "modes": ["none", "c1", "ideal"],
                "report_rules": {"primary_profiles": ["wire39", "wire46"], "primary_modes": ["none", "c1"]}}

    def cells(self):
        return [{"profile": p, "mode": m, "scenario": f"B{i}", "primary": True,
                 "upper_bound_ms": -0.01 if m == "c1" and i == 0 else 0.1,
                 "regression_gate": {"status": "pass"}}
                for p in ("wire39", "wire46") for m in ("none", "c1") for i in range(15)]

    def test_every_primary_cell_required(self):
        cells = self.cells()
        self.assertEqual(report.decision(cells, self.plan())["status"], "pass")
        for changed in (cells[:-1], cells + [cells[0]]):
            with self.assertRaises(ValueError):
                report.decision(changed, self.plan())
        for status in ("fail", "inconclusive"):
            changed = copy.deepcopy(cells)
            changed[-1]["regression_gate"]["status"] = status
            self.assertEqual(report.decision(changed, self.plan())["status"], status)

    def test_improvement_requires_strict_c1_upper(self):
        cells = self.cells()
        for cell in cells:
            cell["upper_bound_ms"] = 0.0 if cell["mode"] == "c1" else -5.0
        self.assertEqual(report.decision(cells, self.plan())["status"], "inconclusive")
        cells.append({"primary": False, "mode": "ideal", "upper_bound_ms": -50})
        self.assertFalse(report.decision(cells, self.plan())["improvement_satisfied"])

    def run_for(self, seed, action):
        return {"seed": seed, "n": 10, "action_counts": [{"context_id": "c", "action": action, "n": 10}],
                "summary": {"mean_hct_ms": 100.0}}

    def table(self, action, gap, width, unresolved=False):
        return {"action": action, "reference_action": [0, 0, 0], "mean_gap_ms": gap,
                "mean_hct_ms": 100 + gap, "gap_half_width_ms": width,
                "uncertainty_resolved": not unresolved, "zero_observed_variance": unresolved, "approximate": True}

    def test_shared_mc_bound_does_not_shrink_by_seed_count(self):
        a, b = (0, 0, 1), (0, 0, 2)
        tables = {("c", a): self.table(a, -2, 0.3), ("c", b): self.table(b, -1, 0.4)}
        for n in (2, 20):
            result = bench_report.direct_comparison([self.run_for(s, a) for s in range(n)],
                                                     [self.run_for(s, b) for s in range(n)], tables)
            self.assertAlmostEqual(result["shared_mc_bound_ms"], 0.7)
            self.assertAlmostEqual(result["upper_bound_ms"], -0.3)

    def test_zero_variance_different_actions_are_unresolved(self):
        a, b = (0, 0, 1), (0, 0, 2)
        tables = {("c", a): self.table(a, 0, None, True), ("c", b): self.table(b, 0, None, True)}
        ca, ba = ([self.run_for(s, action) for s in range(20)] for action in (a, b))
        result = bench_report.direct_comparison(ca, ba, tables)
        self.assertIsNone(result["shared_mc_bound_ms"])
        self.assertIsNone(result["upper_bound_ms"])
        same = bench_report.direct_comparison(ca, ca, tables)
        self.assertEqual(same["upper_bound_ms"], 0)

    def test_profiles_are_not_cancelled(self):
        action = (0, 0, 1)
        ca, ba = ([self.run_for(s, action) for s in range(20)] for _ in range(2))
        for row in ca:
            row["action_counts"][0]["context_id"] = "new"
        tables = {("c", action): self.table(action, 0, 0), ("new", action): self.table(action, 3, 0)}
        with self.assertRaises(ValueError):
            bench_report.direct_comparison(ca, ba, tables)
        result = report.cross_profile(ca, ba, tables, 0.95)
        self.assertEqual(result["expected_cost_point_ms"], 3)
        self.assertFalse(result["oracle_cancels"])
        self.assertFalse(result["used_for_adoption"])

    def test_combined_protocol_keeps_profile_worlds(self):
        plan = family.collector.read(family.collector.PLAN)
        old = copy.deepcopy(plan)
        combined = family.combined_protocol(plan)
        self.assertEqual(plan, old)
        self.assertEqual(len(combined["scenarios"]), 30)
        for scenario in combined["scenarios"]:
            profile, sid = scenario["id"].split("_", 1)
            source = next(s for s in plan["protocols"][profile]["scenarios"] if s["id"] == sid)
            self.assertEqual({**scenario, "id": sid}, source)

    def test_collected_run_mutations_rejected(self):
        original_read = family.read
        with tempfile.TemporaryDirectory() as directory:
            plan, plan_sha, target, base, job = relocated_shard(directory)
            with patch.object(family.collector, "load_plan", return_value=plan), patch.object(family, "PLAN_SHA", plan_sha):
                accepted = family.validate_shard("unit-fixture", job)
                self.assertEqual(len(accepted["runs"]), 1)
                self.assertEqual(accepted["runs"][0]["n"], 1350)
                mutations = [("seed", 32), ("profile", "wire46"), ("observation_mode", "ideal"),
                             ("n", base["n"] - 1), ("trace_sha256", "0" * 64), ("policy_fingerprint", {})]
                for field, value in mutations:
                    changed = copy.deepcopy(base)
                    changed[field] = value
                    def read(path):
                        return changed if family.Path(path) == target else original_read(path)
                    with self.subTest(field=field), patch.object(family, "read", side_effect=read):
                        with self.assertRaises(ValueError):
                            family.validate_shard("unit-fixture", job)


if __name__ == "__main__":
    unittest.main()
