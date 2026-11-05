import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import copy
import hashlib
import importlib.util
import json
from pathlib import Path


RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
PATH = RUNS / "l2_findings_extract_v1.py"
spec = importlib.util.spec_from_file_location("l2_findings", PATH)
extractor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extractor)
comparisons = []
pairs = [("l2_" + mode, base) for mode in ("none", "c1", "ideal") for base in ("v32", "v31")]
pairs += [("l2_c1", "l2_none")] + [("l2_" + mode, "l1_" + mode) for mode in ("none", "c1", "ideal")]
pairs += [("l2_" + mode, "fixed_" + mode) for mode in ("none", "c1")]
pairs += [("fixed_" + mode, "l1_" + mode) for mode in ("none", "c1")]
primary = {("l2_none", "l1_none"), ("l2_c1", "l1_c1"), ("l2_c1", "v31"), ("l2_c1", "v32")}
for candidate, baseline in pairs:
    for index in range(15):
        comparisons.append({"candidate": {"generation": candidate}, "baseline": {"generation": baseline},
            "scenario": f"cell{index:02d}", "primary": (candidate, baseline) in primary, "kind": "synthetic",
            "seed_summary": {"mean": -.1, "lower": -.12, "upper": -.08}, "shared_mc_bound_ms": .03,
            "lower_bound_ms": -.15, "upper_bound_ms": -.05, "regression_gate": {"status": "pass"}})
report = {"comparisons": comparisons, "groups": [], "data_kind": "synthetic"}
before = copy.deepcopy(report)
value = extractor.extract(report)
assert report == before
assert value["candidate_eligible_for_adoption"] and value["primary_cell_count"] == 60
assert len(value["before_after_reduction_cells"]) == 30 and len(value["pair_summaries"]) == 14
primary_index = next(index for index, row in enumerate(comparisons) if row["primary"])
nonprimary_index = next(index for index, row in enumerate(comparisons) if not row["primary"])
for status in ("fail", "inconclusive"):
    changed = copy.deepcopy(report)
    changed["comparisons"][primary_index]["regression_gate"]["status"] = status
    assert not extractor.extract(changed)["candidate_eligible_for_adoption"]
changed = copy.deepcopy(report)
changed["comparisons"][nonprimary_index]["regression_gate"]["status"] = "fail"
assert extractor.extract(changed)["candidate_eligible_for_adoption"]
for row in changed["comparisons"]:
    row["upper_bound_ms"] = .2
assert not extractor.extract(changed)["candidate_eligible_for_adoption"]
changed["comparisons"][primary_index]["upper_bound_ms"] = None
unknown = extractor.extract(changed)
assert unknown["pair_summaries"]["l2_c1_vs_v32"]["null_upper_cells"] == ["cell00"]
text = extractor.prose(value)
assert text.count("| synthetic |") == 0
assert text.count("[-0.120000, -0.080000] | 0.030000 | [-0.150000, -0.050000] | pass |") == 210
result = {"status": "pass", "scope": "synthetic extraction invariants only", "comparison_rows_checked": 210,
          "primary_rows": 60, "improved_before_after_rows": 30, "cases": ["input_unchanged", "all_primary_pass",
          "primary_fail_blocks", "primary_inconclusive_blocks", "diagnostic_fail_retained", "no_improvement_blocks", "null_bound_retained", "all_CI_rows_displayed"],
          "extractor_sha256": hashlib.sha256(PATH.read_bytes()).hexdigest(), "review_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
out = RUNS / "L2_findings_extract_review_v1.json"
with out.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps(result))
