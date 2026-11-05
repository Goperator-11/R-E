import sys
sys.dont_write_bytecode = True
import ast
from pathlib import Path

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
def save(path, code):
    ast.parse(code)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(code)

code = (RUNS / "j6_findings_extract_v1.py").read_text(encoding="utf-8").replace("j6", "l5").replace("J6", "L5")
code = code.replace('    adopt = noninferior and bool(improved)', '''    required_groups = {(mode, family) for mode in ("none", "c1") for family in ("B5", "B6")}
    found = {}
    for group in report.get("groups", []):
        key = group["generation"].removeprefix("l5_"), group["scenario"]
        if key in required_groups:
            if key in found:
                raise ValueError("duplicate B5/B6 group")
            gate = "adaptation" if key[1] == "B5" else "mixture_fixed_regret"
            status = group["gates"][gate]["status"]
            if status not in ("pass", "fail", "inconclusive"):
                raise ValueError("unknown specific gate status")
            found[key] = status
    if set(found) != required_groups:
        raise ValueError("all none/c1 B5/B6 gates required")
    historical = report.get("historical_new_methods_gate")
    if historical not in ("pass", "blocked_missing_inputs", "fail"):
        raise ValueError("historical new-method gate required")
    specific = all(status == "pass" for status in found.values())
    adopt = noninferior and specific and historical == "pass"
    reasons = []
    if not noninferior:
        reasons.append("primary noninferiority failed or inconclusive")
    if not specific:
        reasons.append("B5 adaptation or B6 mixture gate failed or inconclusive")
    if historical != "pass":
        reasons.append("historical new-method validation: " + historical)''')
begin = code.index('        "reason": "all primary cells')
end = code.index('        "primary_rows":', begin)
code = code[:begin] + '''        "reason": "; ".join(reasons) if reasons else "all predeclared primary, B5/B6 and historical gates pass",
        "historical_gate": historical, "specific_gates": {mode + ":" + family: status for (mode, family), status in found.items()},
''' + code[end:]
code = code.replace('in ("B1", "B2")', 'in ("B1", "B2", "B5", "B6")')
code = code.replace('preflight_fixture_sha256=sha(RUNS / "L5_preflight_fixture_check_v2.json")', 'response_fixture_sha256=sha(RUNS / "L5_response_fixture_check_v3.json"),\n        adaptation_fixture_sha256=sha(RUNS / "L5_adaptation_fixture_check_v3.json")')
code = code.replace('Original 30 adoption cells; all other comparisons and absolute B1/B2 results retained as diagnostics. No zero-margin substitution or new samples.', 'Original 30 noninferiority cells and none/c1 B5/B6 gates plus historical new-method validation. Single is diagnostic only; no substitution or new samples.')
code = code.replace('비열등은 각 셀의 조정 상한0.5 ms 이하를 요구한다. 비용 감소는 c1의 조정 상한0 미만으로 판정한다.', '비열등은 각 셀의 조정 상한0.5 ms 이하를 요구한다. 채택에는 none·C1의 B5 적응·B6 혼합 관문과 두 새 산출법의 역사 관문도 필요하다.')
code = code.replace('    lines += ["", "비열등', '    lines += ["", "세부 관문: " + str(result["specific_gates"]) + ". 역사 관문: " + result["historical_gate"] + ".", "비열등')
save(RUNS / "l5_findings_extract_v1.py", code)

code = (RUNS / "j6_revert_candidate_v1.py").read_text(encoding="utf-8").replace("j6", "l5").replace("J6", "L5")
code = code.replace("e94961a4f472bc043374cb0ec15034583acc2f34", "91432c35c122dd83bc946b2d53e68c96bd6fa14b")
code = code.replace('"tests/test_v33_l3_candidate.py", "tests/test_v33_policy_worker.py"', '"tests/test_v33_l3_candidate.py", "tests/test_v33_policy_worker.py", "tests/test_padfec3_followup.py"')
code = code.replace("test_padfec3_preflight.py", "test_padfec3_server_size.py").replace("test_v33_preflight_observer.py", "test_v33_server_response_observer.py").replace("padfec3/preflight.py", "padfec3/server_size.py")
begin = code.index('        if "observer" in name:')
end = code.index('        moves.append', begin)
code = code[:begin] + '''        if "observer" in name:
            assert "root = Path(__file__).resolve().parents[1]" in text
            assert '"source_root": str(root)' in text
            text = text.replace("root = Path(__file__).resolve().parents[1]", 'root = Path(__file__).resolve().parents[3]')
            text = text.replace('"source_root": str(root)', '"source_root": str(root / "g3/v33/policy_snapshots/L5_v1")')
''' + code[end:]
code = code.replace('learn3.STATE_VERSION != 8', 'learn3.STATE_VERSION != 9').replace('value["v"] = 8', 'value["v"] = 9')
save(RUNS / "l5_revert_candidate_v1.py", code)

code = (RUNS / "j6_revert_check_v1.py").read_text(encoding="utf-8")
code = code.replace('"test_v33_j6_candidate.py",', '"test_v33_j6_candidate.py", "test_v33_l5_candidate.py", "test_v33_learning_l5.py", "test_v33_learning_l5_report.py", "test_v33_l5_joint_driver.py", "test_v33_l5_findings.py",')
code = code.replace('sources += sorted((ROOT / "experiments/v33/candidate_tests").glob("j6_*.py"))', 'sources += sorted((ROOT / "experiments/v33/candidate_tests").glob("j6_*.py"))\nsources += sorted((ROOT / "experiments/v33/candidate_tests").glob("l5_*.py"))')
code = code.replace('; import pytest; raise SystemExit', '; import runpy; runpy.run_path(' + repr(str(RUNS / "preserve_test_files_v1.py")) + '); import pytest; raise SystemExit')
save(RUNS / "l5_revert_check_v1.py", code)
