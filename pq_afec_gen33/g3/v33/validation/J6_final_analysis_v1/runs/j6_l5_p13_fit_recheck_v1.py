import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import collections
import datetime as dt
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
inventory_path = RUNS / "L5_history_availability_during_J6_v2.json"
inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
results = []
for source in inventory["records"]:
    path = Path(source["path"])
    assert sha(path) == source["sha256"]
    obj = json.loads(path.read_text(encoding="utf-8"))
    for group, saved in obj["fits"].items():
        grouped = collections.defaultdict(list)
        for row in obj["sweep"]:
            if row["group"] == group and row["usable"]:
                grouped[Fraction(str(row["n_flight_med"]))].append(Fraction(str(row["s0_direct_med"])))
        points = [(n, sum(v) / len(v)) for n, v in sorted(grouped.items())]
        n = len(points)
        mx, my = sum(x for x, y in points) / n, sum(y for x, y in points) / n
        c = sum((x - mx) * (y - my) for x, y in points) / sum((x - mx) ** 2 for x, y in points)
        b = my - c * mx
        mae = sum(abs(y - b - c * x) for x, y in points) / n
        assert [[float(x), float(y)] for x, y in points] == saved["points"]
        for key, value in (("c", c), ("s0_base", b), ("mae", mae)):
            assert math.isclose(float(value), saved[key], rel_tol=0, abs_tol=1e-10)
        difference = Fraction("41.983") - c
        results.append({"source": str(path), "source_sha256": source["sha256"], "group": group,
                        "grouped_points": n, "c_exact": str(c), "c": float(c), "s0_base": float(b), "mae": float(mae),
                        "effective_model_c": 41.983, "difference_from_effective_c": float(difference),
                        "within_doc_1_5_bytes": abs(difference) <= Fraction("1.5"), "saved_fit_matches": True})
    assert sha(path) == source["sha256"]
doc = Path(r"C:\dev\pq_afec\docs\PADFEC v2 명세.md")
source_code = Path(r"C:\dev\pq_afec\experiments\p13_beff.py")
result = {"schema": "padfec.v33.l5_p13_fit_recheck/1", "recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
          "script_sha256": sha(__file__), "input_sha256": {str(inventory_path): sha(inventory_path), str(doc): sha(doc), str(source_code): sha(source_code)},
          "results": results, "scope": "Exact rational recalculation from stored sweep aggregates; not a refit of raw packet data or new policy calibration.",
          "documentation": {"physical_c_x25519": 40.55, "physical_c_mlkem": 41.39, "claimed_max_difference": 1.5,
                            "matching_original_run": "unidentified in these five stored result versions"}}
out = RUNS / "J6_L5_p13_fit_recheck_v1.json"
with out.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps({"verified_fits": len(results), "current_results": results[:2], "scope": result["scope"]}, ensure_ascii=False))
