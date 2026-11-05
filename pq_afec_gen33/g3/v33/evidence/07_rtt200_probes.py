import sys
sys.dont_write_bytecode = True
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import comparison, histogram, numeric, rows, run


def summarize(observations):
    n = len(observations)
    unavailable = sum(row.get("path_rtt_source") == "unavailable" for row in observations)
    valid = sum(bool(row.get("path_rtt_valid")) for row in observations)
    return {"n": n, "initial_datagrams": histogram(row.get("initial_datagrams") for row in observations), "parity_sent": histogram(row.get("parity_sent") for row in observations), "initial_and_parity_pairs": histogram([row.get("initial_datagrams"), row.get("parity_sent")] for row in observations), "path_rtt_source": histogram(row.get("path_rtt_source") for row in observations), "policy_rtt_source": histogram(row.get("policy_rtt_source") for row in observations), "path_rtt_unavailable_count": unavailable, "path_rtt_unavailable_fraction": unavailable / n if n else None, "path_rtt_valid_count": valid, "path_rtt_valid_fraction": valid / n if n else None, "policy_rtt_ms": numeric(row.get("policy_rtt_ms") for row in observations), "valid_path_rtt_ms": numeric(row.get("path_rtt_ms") for row in observations if row.get("path_rtt_valid")), "hct_ms": numeric(row.get("ms") for row in observations), "hct_below_300_ms": sum(row.get("ok") and row["ms"] < 300 for row in observations), "hct_300_to_520_ms": sum(row.get("ok") and 300 <= row["ms"] < 520 for row in observations), "hct_at_least_520_ms": sum(row.get("ok") and row["ms"] >= 520 for row in observations)}


def analyze(context):
    results = []
    for run_id in ("run1", "run2"):
        grouped = {}
        for _, value, segment, row in rows(context.load(f"p31_{run_id}_S_rtt200_units.jsonl")):
            arm = segment["arm"]
            action = tuple(row.get("action") or ()) if arm == "g3auto" else arm
            grouped.setdefault((arm, "all", "all"), []).append(row)
            grouped.setdefault((arm, value["loss"], action), []).append(row)
        for (arm, loss, action), observations in sorted(grouped.items(), key=str):
            result = {"run": run_id, "arm": arm, "loss_percent": loss, "action": list(action) if isinstance(action, tuple) else action, **summarize(observations)}
            if run_id == "run1" and loss == "all":
                expected_percent = {"g2auto": 99.3, "g3auto": 99.5, "g3fixL2": 99.4}.get(arm)
                result["expected"] = {"unavailable_percent": comparison(100.0 * result["path_rtt_unavailable_fraction"], expected_percent, "검증 문서의 소수 첫째 자리 반올림 백분율")}
                if arm == "g3auto":
                    result["expected"].update({"n": comparison(len(observations), 4500, "run1 S_rtt200 g3auto 전체"), "initial_datagrams_5_count": comparison(sum(row.get("initial_datagrams") == 5 for row in observations), 4500, "검증자 확인값"), "parity_sent_9_count": comparison(sum(row.get("parity_sent") == 9 for row in observations), 4490, "검증자 확인값")})
            results.append(result)
    reference_conditions = []
    for path in sorted(context.journals.glob("p31_run1_*_units.jsonl")):
        if path.name == "p31_run1_S_rtt200_units.jsonl":
            continue
        grouped = {}
        for _, value, segment, row in rows(context.load(path.name)):
            grouped.setdefault(segment["arm"], []).append(row)
        for arm, observations in sorted(grouped.items()):
            unavailable = sum(row.get("path_rtt_source") == "unavailable" for row in observations)
            reference_conditions.append({"journal": path.name, "arm": arm, "n": len(observations), "path_rtt_unavailable_count": unavailable, "path_rtt_unavailable_fraction": unavailable / len(observations) if observations else None})
    return {"item": "A0-7", "data_kind": "measurement_reanalysis", "source_scripts": ["verify-A6/rttsrc_all.py", "verify-A1/v06_bytes.py", "verify-A1/v15_rtt200.py", "audit-cost-model/s11_rtt200.py"], "definition": "initial_datagrams는 연결 전체 Initial 계수이며 first_flight_datagrams와 다르다. parity_sent도 연결 전체 계수다. path_rtt_source unavailable은 기록값 그대로 집계하고 원인을 이 분석만으로 단정하지 않는다.", "results": results, "run1_other_condition_rtt_availability": reference_conditions}


if __name__ == "__main__":
    run(analyze)
