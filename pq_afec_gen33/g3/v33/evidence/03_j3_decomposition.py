import sys
sys.dont_write_bytecode = True
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import average, comparison, histogram, numeric, rows, run


def model_parts(layout, action, probability):
    delta, lead, trailing = action
    k, w, m, rtt, uplink, need = 2, 1280 + delta, lead + trailing, 50.7, 2.0, 15
    response = layout.response_term(m, w, uplink, "v3")
    preflight = layout.preflight_bytes(k, uplink)
    parts = {name: {"probability": 0.0, "contribution_ms": 0.0} for name in ("one", "two", "pto", "ptoS", "ack")}
    failures = []
    rounds = success = 0.0
    for record in layout.outcomes(k, m, lead, w, probability, uplink):
        if record["kind"] != "ok":
            failures.append(record)
            continue
        for weight, credit in record["branches"]:
            nround = layout.rtt_count(credit, need, preflight)
            mass = record["pr"] * weight
            hct = record["t_dec"] + rtt * nround + (response if nround == 2 else 0.0)
            group = parts["one" if nround == 1 else "two"]
            group["probability"] += mass
            group["contribution_ms"] += mass * hct
            rounds += mass * nround
            success += mass
    failure_probability = sum(record["pr"] for record in failures)
    n_ok = rounds / success if success > 1e-15 else 2.0
    multiplier = 1.0 / (1.0 - failure_probability) if failure_probability < 1 else 1.0
    for record in failures:
        kind = record["kind"]
        if kind == "pto":
            cost = rtt + layout.T_PTO_MS + layout.tau(k * w, uplink)
        elif kind == "ptoS":
            cost = record["t_last_o"] + n_ok * rtt + layout.PTO_SAMPLED_MULT * rtt
        else:
            cost = record["t_last_o"] + n_ok * rtt + layout.T_ACK_SLOPE * rtt + layout.T_ACK_BASE_MS
        parts[kind]["probability"] += record["pr"]
        parts[kind]["contribution_ms"] += record["pr"] * multiplier * cost
    for group in parts.values():
        group["conditional_mean_ms"] = group["contribution_ms"] / group["probability"] if group["probability"] else None
    evaluated = layout.evaluate(k, w, m, lead, probability, rtt, uplink, need)
    return {"input": {"k": k, "w_B": w, "m": m, "lead": lead, "rtt_ms": rtt, "uplink_Mbps": uplink, "n_need": need, "p": probability}, "classes": parts, "layout_evaluate": evaluated, "parts_sum_ms": sum(group["contribution_ms"] for group in parts.values()), "sum_minus_layout_ms": sum(group["contribution_ms"] for group in parts.values()) - evaluated["J"]}


def classify(row):
    if not row.get("ok") or row["initial_datagrams"] >= 4:
        return "failure_or_initial_retransmission"
    if row["initial_datagrams"] == 3:
        if row["ms"] < 100:
            return "one"
        if row["ms"] < 200:
            return "two"
        return "tail"
    return "unclassified"


def summarize(layout, arm, loss, action, selected):
    n = len(selected)
    model = model_parts(layout, action, loss / 100.0)
    groups = {name: [] for name in ("one", "two", "tail", "failure_or_initial_retransmission", "unclassified")}
    for row in selected:
        groups[classify(row)].append(row)
    observed = {}
    for name, members in groups.items():
        observed[name] = {"count": len(members), "fraction": len(members) / n, "mean_ms": average(row["ms"] for row in members), "contribution_ms": sum(row["ms"] for row in members) / n}
    normal_two = observed["two"]["mean_ms"]
    tail_excess = sum(row["ms"] - normal_two for row in groups["tail"]) / n if normal_two is not None else None
    failure_contribution = sum(model["classes"][name]["contribution_ms"] for name in ("pto", "ptoS", "ack"))
    failure_probability = model["layout_evaluate"]["p_fail"]
    gap = average(row["ms"] for row in selected) - model["layout_evaluate"]["J"]
    regular_two = ((len(groups["two"]) + len(groups["tail"])) * normal_two / n - model["classes"]["two"]["contribution_ms"]) if normal_two is not None else None
    components = {"one_rtt_difference_ms": observed["one"]["contribution_ms"] - model["classes"]["one"]["contribution_ms"], "regular_two_rtt_difference_ms": regular_two, "tail_excess_ms": tail_excess, "failure_difference_ms": observed["failure_or_initial_retransmission"]["contribution_ms"] - failure_contribution, "unclassified_contribution_ms": observed["unclassified"]["contribution_ms"]}
    component_sum = sum(components.values()) if all(value is not None for value in components.values()) else None
    one_model = model["classes"]["one"]["conditional_mean_ms"]
    one_observed = observed["one"]["mean_ms"]
    return {"arm": arm, "loss_percent": loss, "action": list(action), "rows": n, "model_kind": "model_world", "model": model, "observed": observed, "observed_mean_ms": average(row["ms"] for row in selected), "observed_minus_model_ms": gap, "gap_components": components, "gap_components_sum_ms": component_sum, "gap_components_sum_minus_gap_ms": component_sum - gap if component_sum is not None else None, "one_rtt_mean_offset_ms": one_observed - one_model if one_observed is not None and one_model is not None else None, "tail_share_among_non_retransmitted_two_rtt": len(groups["tail"]) / (len(groups["tail"]) + len(groups["two"])) if groups["tail"] or groups["two"] else None, "failure_model_conditional_ms": failure_contribution / failure_probability if failure_probability else None, "decision_pre_prediction_ms": numeric(row.get("j3_pred_pre_ms") for row in selected), "decision_pre_p_mean": numeric(row.get("p_mean") for row in selected), "initial_datagrams": histogram(row["initial_datagrams"] for row in selected)}


def analyze(context):
    from padfec3 import layout
    grouped = {}
    for run_id in ("run1", "run2"):
        for unit, value, segment, row in rows(context.load(f"p31_{run_id}_S_bigcert_units.jsonl")):
            arm = segment["arm"]
            action = tuple(row.get("action") or ()) if arm == "g3auto" else ((0, 3, 1) if arm == "g3fixL3" else None)
            if action not in ((0, 3, 1), (0, 0, 4)):
                continue
            for key in ((run_id, arm, value["loss"], action), ("pooled_runs", arm, value["loss"], action), ("pooled_runs", "pooled_auto_and_fixed", value["loss"], action)):
                grouped.setdefault(key, []).append(row)
    results = []
    for (run_id, arm, loss, action), selected in sorted(grouped.items(), key=str):
        summary = summarize(layout, arm, loss, action, selected)
        summary["run"] = run_id
        if run_id == "pooled_runs" and loss == 15.0:
            if arm == "pooled_auto_and_fixed" and action == (0, 3, 1):
                summary["expected"] = {"rows": comparison(len(selected), 4655, "auto와 고정 팔을 합친 기술 통계"), "observed_ms": comparison(summary["observed_mean_ms"], 109.74, "검증 문서의 소수 둘째 자리 반올림값"), "model_ms": comparison(summary["model"]["layout_evaluate"]["J"], 104.45, "RTT 50.7 ms 입력의 반올림값"), "tail_excess_ms": comparison(summary["gap_components"]["tail_excess_ms"], 1.67, "정상 2RTT 평균을 뺀 꼬리 초과분의 전체 연결당 기여")}
            elif arm == "g3auto" and action == (0, 0, 4):
                summary["expected"] = {"rows": comparison(len(selected), 1885, "두 회차 g3auto (0,0,4)"), "observed_ms": comparison(summary["observed_mean_ms"], 123.62, "반올림값"), "model_ms": comparison(summary["model"]["layout_evaluate"]["J"], 116.87, "반올림값"), "tail_excess_ms": comparison(summary["gap_components"]["tail_excess_ms"], 4.29, "정상 2RTT 평균을 뺀 초과분")}
            elif arm == "g3fixL3" and action == (0, 3, 1):
                summary["expected"] = {"failures": comparison(summary["observed"]["failure_or_initial_retransmission"]["count"], 130, "고정 팔 2,250행 중 재전송 또는 실패"), "failure_conditional_ms": comparison(summary["observed"]["failure_or_initial_retransmission"]["mean_ms"], 266.4, "반올림값"), "failure_model_ms": comparison(summary["failure_model_conditional_ms"], 233.4, "반올림값")}
            elif arm == "g3auto" and action == (0, 3, 1):
                summary["expected"] = {"failures": comparison(summary["observed"]["failure_or_initial_retransmission"]["count"], 114, "자동 팔 2,405행 중 재전송 또는 실패"), "failure_conditional_ms": comparison(summary["observed"]["failure_or_initial_retransmission"]["mean_ms"], 270.0, "반올림값")}
        results.append(summary)
    return {"item": "A0-3", "data_kind": "measurement_reanalysis_and_model_world", "definitions": {"one": "ok이고 initial_datagrams=3, HCT<100 ms", "two": "ok이고 initial_datagrams=3, 100<=HCT<200 ms", "tail": "ok이고 initial_datagrams=3, HCT>=200 ms", "failure": "ok=false 또는 initial_datagrams>=4", "tail_excess": "sum(tail HCT - 같은 그룹의 정상 2RTT HCT 평균)/전체 반환 연결 수", "processing_offset": "one_rtt_mean_offset_ms는 해당 그룹 1RTT 조건부 평균의 관측-모형 차이다. 2% 자료를 처리 상수의 근거로 보고 15% 자료와 구분한다."}, "source_scripts": ["verify-A1/v02_bigcert.py", "verify-A1/v08_fail.py", "audit-cost-model/mlib.py"], "notes": ["자동 팔과 고정 팔의 실패 빈도를 분리한다. 합산 기술 통계만으로 선택 편향을 없앴다고 해석하지 않는다.", "모형 실패 기여는 반복 복구 multiplier를 포함한다. 실제의 첫 실패당 측정값과 구별한다.", "원문에서 꼬리 HCT 전체를 기여로 적은 2.81/7.64 ms를 초과 지연으로 사용하지 않는다."], "results": results}


if __name__ == "__main__":
    run(analyze)
