import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
from pathlib import Path

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(path, text):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)

helper = (RUNS / "l5_response_audit_v1.py").read_text(encoding="utf-8")
helper = helper.replace("from collections import Counter", "from collections import Counter\nimport gzip\nimport json\nimport math")
helper = helper.replace('if request["rtt_ms"] is not None and row["observation_info"]["ctx"]["u"] > 0', 'if row["observation_info"]["ctx"]["u"] > 0')
helper = helper.replace('if time < previous:', 'if type(time) not in (int, float) or not math.isfinite(time) or time < 0 or time < previous:')
helper = helper.replace('            total += size', '            if kind != "data" and index is not None:\n                raise ValueError("non-data response identity")\n            if kind == "data" and (type(index) is not int or index < 0):\n                raise ValueError("invalid response identity")\n            total += size')
helper = helper.replace('            equal(sorted(packets)', '            if not packets:\n                raise ValueError("empty completed response")\n            equal(sorted(packets)')
helper = helper.replace('"final_resets": resets}', '"final_resets": resets, "final_window_count": len(window), "final_catalog_count": len(catalog),\n            "final_S_hat": median(sample["bytes"] for sample in window[-16:]) if window else None}')
helper += '''

def check_runs(audit, groups, protocol):
    totals = Counter()
    for runs in groups.values():
        for run in runs:
            if run["analysis_role"] not in ("l5", "single"):
                continue
            label = run["generation"] + ":" + run["scenario"] + ":" + str(run["seed"])
            audit.file(run["trace_path"], run["trace_sha256"])
            with gzip.open(run["trace_path"], "rt", encoding="utf-8") as stream:
                rows = [json.loads(line) for line in stream]
            audit.equal("response_rows:" + label, len(rows), run["n"])
            audit.equal("response_indices:" + label, [row["index"] for row in rows], list(range(run["n"])))
            value = audit_rows(rows, variant="single" if run["analysis_role"] == "single" else "full")
            audit.count += value["checks"]
            for observed, expected in (("size_window_count", "final_window_count"), ("size_catalog_count", "final_catalog_count"),
                                       ("size_reset_count", "final_resets"), ("S_hat", "final_S_hat")):
                audit.equal("response_final_state:" + label + observed, run["final_state"][observed], value[expected])
            for key in ("rows", "size_updates", "received_duplicate_data_bytes", "received_other_bytes", "received_post_complete_bytes", "final_resets"):
                totals[key] += value[key]
            totals["runs"] += 1
    return dict(totals)
'''
save(RUNS / "l5_response_audit_v2.py", helper)
grade = (RUNS / "j6_grade_audit_v1.py").read_text(encoding="utf-8").replace('("j6", "zero")', '("l5", "single")')
save(RUNS / "l5_grade_audit_v1.py", grade)
checker = (RUNS / "j6_joint_artifact_check_v2.py").read_text(encoding="utf-8").replace("j6", "l5").replace("J6", "L5")
checker = checker.replace('"zero"', '"single"').replace('"zero_none"', '"single_none"').replace('"zero_c1"', '"single_c1"').replace('"zero_"', '"single_"')
checker = checker.replace("margin_contrast", "mixture_change_contrast").replace("preflight_context_contrast", "response_geometry_contrast")
for old, path in (("98061ebdcaa6e95c6850f9d1c5d141cbdd0d5e3eecbf95f157b836539abf6703", ROOT / "experiments/v33/bench_learning_l5_report.py"),
                  ("31d6c7ecab527e026cf5619cd22f9d57c6ac2e01990d33ca33f4d2e0d9eeb981", RUNS / "l5_joint_driver_v1.py"),
                  ("adc2add9e2cfdaae9076b72114ce7006cf09c985ffc3ab16a55ea38a69b6d17f", RUNS / "l5_grade_audit_v1.py"),
                  ("6a687026e726ad9393234da5ceb1160ad77e2c0e630aa2a2c56d895fe9a2b846", RUNS / "l5_response_audit_v2.py")):
    assert old in checker
    checker = checker.replace(old, sha(path))
checker = checker.replace('l5_preflight_audit_v3.py', 'l5_response_audit_v2.py').replace("PREFLIGHT", "RESPONSE").replace("preflight_spec", "response_spec").replace("preflight_audit", "response_audit").replace("preflight_counts", "response_counts").replace("independent_preflight", "independent_response")
marker = "\n\n\n\nclass Audit"
assert marker in checker
checker = checker.replace(marker, '\nADAPTATION_PATH = RUNS / "l5_adaptation_audit_v1.py"\nADAPTATION_SHA = ' + repr(sha(RUNS / "l5_adaptation_audit_v1.py")) + '''
assert file_hash(ADAPTATION_PATH) == ADAPTATION_SHA
adaptation_spec = importlib.util.spec_from_file_location("independent_l5_adaptation", ADAPTATION_PATH)
adaptation_audit = importlib.util.module_from_spec(adaptation_spec)
adaptation_spec.loader.exec_module(adaptation_audit)


class Audit''')
marker = '    audit.equal("report_missing", report["missing"], [])'
checker = checker.replace(marker, marker + '\n    audit.equal("historical_gate", report["historical_new_methods_gate"], "blocked_missing_inputs")\n    audit.equal("historical_no_independent_validation", report["historical_fit_is_independent_validation"], False)')
marker = '    audit.file(RESPONSE_PATH, RESPONSE_SHA)'
checker = checker.replace(marker, '''    audit.file(ADAPTATION_PATH, ADAPTATION_SHA)
    scenarios = {row["id"]: row for row in protocol["scenarios"]}
    adaptation_cases = 0
    for group in report["groups"]:
        if group["family"] == "B5":
            adaptation_cases += adaptation_audit.check_group(audit, group, groups[group["generation"], group["scenario"]],
                scenarios[group["scenario"]], protocol, refs, tables, base.width)
''' + marker)
checker = checker.replace('"response_audit": response_counts,', '"response_audit": response_counts, "adaptation_cases": adaptation_cases,')
checker = checker.replace('causal preflight-budget checks. S selection uses preserved legacy_y.', 'causal complete-response geometry, history, mixture and B5 adaptation checks. Historical new-method inputs remain missing.')
marker = '        for field, summary in group["observed"].items():'
checker = checker.replace(marker, '''        if group["family"] == "B6":
            check_gate(audit, "mixture_gate:" + label, group["gates"]["mixture_fixed_regret"], expected["seed_summary"], mc, selection, .5, True)
''' + marker)
save(RUNS / "l5_joint_artifact_check_v1.py", checker)
fixture = (RUNS / "j6_checker_fixture_check_v1.py").read_text(encoding="utf-8").replace("j6", "l5").replace("J6", "L5").replace('"zero"', '"single"').replace('"margin_zero"', '"single"')
save(RUNS / "l5_checker_fixture_check_v1.py", fixture)
preserved = (ROOT / "tests/test_v33_learning_l5.py").read_text(encoding="utf-8")
preserved = preserved[preserved.index("class PreservedDirectory:"):preserved.index("class FakeWorker:")]
for name in ("test_v33_learning_l5_report.py", "test_v33_l5_joint_driver.py"):
    path = ROOT / "tests" / name
    code = path.read_text(encoding="utf-8")
    code = code.replace("tempfile.TemporaryDirectory()", "PreservedDirectory()")
    marker = "class JointLearningReportTests" if "report" in name else "class JointDriverTests"
    code = code.replace(marker, preserved + marker)
    path.write_text(code, encoding="utf-8", newline="\n")
launcher = (RUNS / "launch_j6_joint_plan_v1.ps1").read_text(encoding="utf-8-sig").replace("j6", "l5").replace("J6", "L5")
launcher = launcher.replace("31d6c7ecab527e026cf5619cd22f9d57c6ac2e01990d33ca33f4d2e0d9eeb981", sha(RUNS / "l5_joint_driver_v1.py"))
launcher = launcher.replace("0d71b6acb7b2e6e2a8faa79b3ef3d61e352def415db0debcdf6ab0d2207ab7d3", sha(RUNS / "L5_full_v1_plan.json"))
save(RUNS / "launch_l5_joint_plan_v1.ps1", launcher)
print(sha(RUNS / "l5_joint_artifact_check_v1.py"))
