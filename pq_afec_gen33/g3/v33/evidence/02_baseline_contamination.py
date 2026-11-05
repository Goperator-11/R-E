import sys
sys.dont_write_bytecode = True
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import comparison, histogram, numeric, rows, run


def analyze(context):
    from padfec3 import layout
    result = {}
    for run_id, expected_missed, expected_non_one in (("run1", 85, 535), ("run2", 55, 484)):
        grouped = {}
        for unit, value, segment, row in rows(context.load(f"p31_{run_id}_S_bigcert_units.jsonl"), "g3auto"):
            if tuple(row.get("action") or ()) != (0, 3, 1):
                continue
            bucket = grouped.setdefault(value["loss"], [])
            rtt = row.get("policy_rtt_ms")
            cutoff = layout.one_rtt_cutoff_ms(rtt, 2, 4, 3, 1280, 2.0) if rtt is not None and rtt > 0 else None
            classification = "missing_cutoff" if cutoff is None else ("fail" if not row["ok"] else ("one" if row["ms"] < cutoff else "non_one"))
            bucket.append({"key": unit["key"], "i": row["i"], "class": classification, "obs_y": row.get("obs_y"), "baseline_ms": row.get("obs_baseline_ms"), "cutoff_ms": cutoff, "updated": bool(row.get("obs_updated")), "hct_ms": row.get("ms"), "policy_rtt_ms": rtt})
        result[run_id] = {}
        for loss, records in sorted(grouped.items()):
            non_one = [r for r in records if r["class"] in ("non_one", "fail")]
            missed = [r for r in records if r["class"] == "non_one" and r["obs_y"] == 0]
            false_events = [r for r in records if r["class"] == "one" and r["obs_y"] == 1]
            elevated = [r for r in records if r["baseline_ms"] is not None and r["cutoff_ms"] is not None and r["baseline_ms"] >= r["cutoff_ms"]]
            summary = {"rows": len(records), "class_counts": histogram(r["class"] for r in records), "obs_y": histogram(r["obs_y"] for r in records), "non_one_count": len(non_one), "missed_non_one_y0": len(missed), "false_one_y1": len(false_events), "baseline_at_or_above_cutoff": len(elevated), "updated": sum(r["updated"] for r in records), "baseline_ms": numeric(r["baseline_ms"] for r in records), "cutoff_ms": numeric(r["cutoff_ms"] for r in records), "missed_records": missed}
            if loss == 15.0:
                summary["expected"] = {"missed": comparison(len(missed), expected_missed, "저장된 obs_y==0이고 ok인 연결의 HCT>=결정 전 policy_rtt_ms 기반 cutoff"), "non_one": comparison(len(non_one), expected_non_one, "ok=false 또는 HCT>=cutoff")}
            result[run_id][str(loss)] = summary
    return {"item": "A0-2", "data_kind": "measurement_reanalysis", "definition": "기록된 obs_y를 사용한다. 학습기 재생값을 대신 쓰지 않는다. cutoff는 one_rtt_cutoff_ms(policy_rtt_ms,2,4,3,1280,2.0).", "source_scripts": ["audit-learning/baseline_contam.py"], "source_discrepancy": "audit-learning/replay31.py의 재생 보고는 run1 86건이다. 카드의 raw 기록 기대값은 85건이며 이 스크립트는 raw 정의를 따른다.", "results": result}


if __name__ == "__main__":
    run(analyze)
