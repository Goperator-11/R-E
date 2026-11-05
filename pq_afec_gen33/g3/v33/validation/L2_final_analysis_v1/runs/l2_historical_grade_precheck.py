import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
EVIDENCE = ROOT / "g3/v33/evidence"
ORIGINAL = EVIDENCE / "02_baseline_contamination.json"
OUT = RUNS / "L2_historical_grade_precheck.json"
EXPECTED = {ROOT / "padfec3/learn3.py": "80f924c67b28b5030de4195fa2856c655a3c5a59fe34780f34d98518a0ae4452",
            ROOT / "padfec3/layout.py": "b18582cb245d1737dc77224f1b831bbd769387a7bb713e9e3d5e3442acbe5a4a",
            EVIDENCE / "common.py": "836059cc6cf71db8b7fdb14ce620663a47eed9a8810a7a57eda8871b72ede216"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    require(not OUT.exists(), "output must be new")
    original = json.loads(ORIGINAL.read_text(encoding="utf-8"))
    sources = {**{Path(path): expected for path, expected in original["source_sha256"].items()},
               **EXPECTED, ORIGINAL: sha(ORIGINAL), Path(__file__).resolve(): sha(__file__)}
    for source, expected in sources.items():
        require(sha(source) == expected, "preparation source changed: " + str(source))
    spec = importlib.util.spec_from_file_location("grade_precheck_common", EVIDENCE / "common.py")
    common = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(common)
    sys.path.insert(0, str(ROOT))
    from padfec3 import learn3, layout
    require(learn3.CLASS_C_PROC_MS == 3.0 and learn3.LATER_DEFAULT == "v3", "fixed L1 boundary changed")
    output = {}
    input_diagnostics = []
    for run_id, old_input in zip(("run1", "run2"), original["inputs"]):
        source = Path(old_input["path"])
        require(source.name == "p31_" + run_id + "_S_bigcert_units.jsonl", "historical input order differs")
        require(sha(source) == old_input["sha256"], "historical source differs from A0")
        sources[source] = old_input["sha256"]
        context = common.EvidenceContext(SimpleNamespace(root=ROOT, journals=source.parent, out=OUT))
        units = context.load(source.name)
        require(context.inputs[0] == old_input, "A0 loader selected a different input set")
        input_diagnostics.extend(context.inputs)
        grouped = {}
        seen = set()
        for unit, value, segment, row in common.rows(units, "g3auto"):
            if tuple(row.get("action") or ()) != (0, 3, 1):
                continue
            identity = (unit["fp"], unit["key"], segment["arm"], row["i"])
            require(identity not in seen, "duplicate selected row")
            seen.add(identity)
            rtt, hct = row.get("policy_rtt_ms"), row.get("ms")
            ctx = {"rtt": rtt, "k": 2, "W": 1280, "u": 2.0} if rtt is not None and rtt > 0 else None
            if ctx is None:
                old_cutoff = first = second = None
                old_class = "missing_cutoff"
                grade = learn3.classify_hct(None, (0, 3, 1), hct, row["ok"])
            else:
                old_cutoff = layout.one_rtt_cutoff_ms(rtt, 2, 4, 3, 1280, 2.0)
                first, second = learn3.grade_cutoffs(ctx, (0, 3, 1))
                old_class = "fail" if not row["ok"] else "one" if hct < old_cutoff else "non_one"
                grade = learn3.classify_hct(ctx, (0, 3, 1), hct, row["ok"])
                require(math.isclose(first - old_cutoff, 3.0, abs_tol=1e-12), "unexpected first-boundary offset")
                expected_grade = 2 if not row["ok"] else 0 if hct < first else 1 if hct < second else 2
                require(grade == expected_grade, "classification and saved boundaries differ")
            record = {"fingerprint": unit["fp"], "unit_key": unit["key"], "row_i": row["i"], "loss_percent": value["loss"],
                      "ok": row["ok"], "hct_ms": hct, "policy_rtt_ms": rtt, "obs_y": row.get("obs_y"),
                      "legacy_baseline_ms": row.get("obs_baseline_ms"), "legacy_updated": bool(row.get("obs_updated")),
                      "old_cutoff_ms": old_cutoff, "old_reference_class": old_class,
                      "l1_first_cutoff_ms": first, "l1_second_cutoff_ms": second, "l1_grade": grade}
            grouped.setdefault(str(value["loss"]), []).append(record)
        output[run_id] = {}
        for loss, records in sorted(grouped.items()):
            old = original["results"][run_id][loss]
            checks = {"rows": len(records), "class_counts": common.histogram(r["old_reference_class"] for r in records),
                      "obs_y": common.histogram(r["obs_y"] for r in records),
                      "non_one_count": sum(r["old_reference_class"] in ("non_one", "fail") for r in records),
                      "missed_non_one_y0": sum(r["old_reference_class"] == "non_one" and r["obs_y"] == 0 for r in records),
                      "false_one_y1": sum(r["old_reference_class"] == "one" and r["obs_y"] == 1 for r in records),
                      "baseline_at_or_above_cutoff": sum(r["legacy_baseline_ms"] is not None and r["old_cutoff_ms"] is not None and r["legacy_baseline_ms"] >= r["old_cutoff_ms"] for r in records),
                      "updated": sum(r["legacy_updated"] for r in records)}
            require(all(old[key] == actual for key, actual in checks.items()), "A0 summary reproduction differs")
            output[run_id][loss] = {"original_A0_reproduction": checks,
                "l1_grade_counts": common.histogram(r["l1_grade"] for r in records),
                "old_reference_to_l1_grade": common.histogram([r["old_reference_class"], r["l1_grade"]] for r in records),
                "old_non_one_now_l1_one": sum(r["old_reference_class"] == "non_one" and r["l1_grade"] == 0 for r in records),
                "old_one_now_l1_non_one": sum(r["old_reference_class"] == "one" and r["l1_grade"] in (1, 2) for r in records),
                "old_missed_y0_to_l1_grade": common.histogram(r["l1_grade"] for r in records if r["old_reference_class"] == "non_one" and r["obs_y"] == 0),
                "records": records}
    for source, expected in sources.items():
        require(sha(source) == expected, "source changed during precheck: " + str(source))
    result = {"schema": "padfec.v33.historical_grade_precheck/1", "status": "pass",
              "recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
              "data_kind": "historical_measurement_reanalysis_not_new_measurement",
              "scope": "Fixed L1 boundaries on the exact A0 selected rows; no policy replay, EPS calibration, margin search or physical RTT truth labels",
              "not_claimed": ["L2 completion", "zero physical classification error", "L1 precision performance", "calibrated processing delay"],
              "fixed_context": {"action": [0, 3, 1], "k": 2, "W_B": 1280, "uplink_mbps": 2.0, "later": "v3", "c_proc_margin_ms": 3.0,
                                "rtt": "stored policy_rtt_ms, same row field as original A0"},
              "sources_sha256": {str(path): expected for path, expected in sources.items()}, "inputs": input_diagnostics, "results": output}
    with OUT.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    compact = {run_id: {loss: {key: value for key, value in item.items() if key != "records"} for loss, item in groups.items()} for run_id, groups in output.items()}
    print(json.dumps({"out": str(OUT), "sha256": sha(OUT), "status": "pass", "results": compact}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
