import sys
sys.dont_write_bytecode = True
import json
from pathlib import Path

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
failure = {"status": "fail", "phase": "synthetic B6 checker fixture", "error_type": "KeyError",
           "error": "mixture_fixed_regret", "cause": "fixture renamed every B6 scenario cell00..14 but frozen reporter binds the original B6 scenario ID",
           "correction": "keep one actual B6 ID and use B1 family for remaining synthetic cells; policy/report thresholds unchanged"}
with (RUNS / "L5_adaptation_fixture_second_failure.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(failure, stream, indent=2)
    stream.write("\n")
code = (RUNS / "l5_adaptation_fixture_check_v2.py").read_text(encoding="utf-8")
code = code.replace('"id": f"cell{i:02d}"', '"id": "B6" if i == 0 else f"cell{i:02d}", "family": "B6" if i == 0 else "B1"')
code = code.replace('    for group in report["groups"]:\n        audit.equal("B6_expected_gate", group["gates"]["mixture_fixed_regret"]["status"], status)', '    for group in report["groups"]:\n        if group["family"] == "B6":\n            audit.equal("B6_expected_gate", group["gates"]["mixture_fixed_regret"]["status"], status)')
code = code.replace('altered["groups"][0]["gates"]["mixture_fixed_regret"]', 'next(group for group in altered["groups"] if group["family"] == "B6")["gates"]["mixture_fixed_regret"]')
code = code.replace('"B6_groups": 600', '"B6_groups": 40')
code = code.replace('L5_adaptation_fixture_check_v2.json', 'L5_adaptation_fixture_check_v3.json')
with (RUNS / "l5_adaptation_fixture_check_v3.py").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(code)
