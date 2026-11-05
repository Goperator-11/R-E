import sys
sys.dont_write_bytecode = True
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import average, comparison, numeric, rows, run
import statistics


def pattern_probability(pattern, p, burst=None):
    if burst is None:
        probability = 1.0
        for arrived in pattern:
            probability *= 1.0 - p if arrived else p
        return probability
    recovery = 1.0 / burst
    entry = p * recovery / (1.0 - p)
    states = [0 if arrived else 1 for arrived in pattern]
    probability = p if states[0] else 1.0 - p
    for previous, current in zip(states, states[1:]):
        if previous == 0:
            probability *= entry if current else 1.0 - entry
        else:
            probability *= 1.0 - recovery if current else recovery
    return probability


def model(layout, k, w, m, lead, p, rtt, uplink, need, burst=None):
    response = layout.response_term(m, w, uplink, "v3")
    preflight = layout.preflight_bytes(k, uplink)
    value = one = two = rounds = success = probability_sum = 0.0
    failures = []
    for record in layout.outcomes(k, m, lead, w, 0.5, uplink):
        probability = pattern_probability(record["pattern"], p, burst)
        probability_sum += probability
        if probability == 0:
            continue
        if record["kind"] != "ok":
            failures.append((record, probability))
            continue
        for weight, credit in record["branches"]:
            count = layout.rtt_count(credit, need, preflight)
            mass = probability * weight
            hct = record["t_dec"] + rtt * count + (response if count == 2 else 0.0)
            value += mass * hct
            if count == 1:
                one += mass
            else:
                two += mass
            rounds += mass * count
            success += mass
    fail = sum(probability for record, probability in failures)
    n_ok = rounds / success if success > 1e-15 else 2.0
    multiplier = 1.0 / (1.0 - fail) if fail < 1 else 1.0
    for record, probability in failures:
        if record["kind"] == "pto":
            cost = rtt + layout.T_PTO_MS + layout.tau(k * w, uplink)
        elif record["kind"] == "ptoS":
            cost = record["t_last_o"] + n_ok * rtt + layout.PTO_SAMPLED_MULT * rtt
        else:
            cost = record["t_last_o"] + n_ok * rtt + layout.T_ACK_SLOPE * rtt + layout.T_ACK_BASE_MS
        value += probability * multiplier * cost
    return {"J_ms": value, "p_one_rtt": one, "p_two_rtt": two, "p_fail": fail, "probability_sum": probability_sum}


def analyze(context):
    from padfec3 import layout, learn3
    from padfec import policy, quantum
    selected = list(rows(context.load("p31_run1_D_p18_burst3_units.jsonl")))
    server_sizes = sorted(row["server_bytes"] for _, _, _, row in selected if row.get("server_bytes"))
    upper_median = server_sizes[len(server_sizes) // 2]
    need = learn3.bin_needed_s(float(upper_median), quantum.bin_index(2 * 1280), policy.C_PKT_POLICY_DEFAULT)
    grouped = {}
    for _, value, segment, row in selected:
        if segment["arm"] == "g3auto":
            grouped.setdefault(tuple(row["action"]), []).append(row)
    results = []
    for action, observations in sorted(grouped.items()):
        delta, lead, trailing = action
        iid = model(layout, 2, 1280 + delta, lead + trailing, lead, 0.15, 50.0, 0.0, need)
        ge = model(layout, 2, 1280 + delta, lead + trailing, lead, 0.15, 50.0, 0.0, need, 3.0)
        direct = layout.evaluate(2, 1280 + delta, lead + trailing, lead, 0.15, 50.0, 0.0, need)
        failures = sum(not row["ok"] or row["initial_datagrams"] >= 4 for row in observations)
        result = {"action": list(action), "n": len(observations), "observed": {"mean_hct_ms": average(row["ms"] for row in observations), "failure_or_initial_retransmission_count": failures, "failure_or_initial_retransmission_fraction": failures / len(observations), "server_bytes": numeric(row.get("server_bytes") for row in observations)}, "iid_model": iid, "ge_model": ge, "iid_minus_layout_J_ms": iid["J_ms"] - direct["J"], "ge_plus_processing_2_6_ms": ge["J_ms"] + 2.6}
        if action == (0, 0, 4):
            result["expected"] = {"n": comparison(len(observations), 1368, "g3auto (0,0,4)"), "observed_mean_ms": comparison(result["observed"]["mean_hct_ms"], 60.98, "소수 둘째 자리 반올림값"), "observed_failure_fraction": comparison(failures / len(observations), 0.0409, "소수 넷째 자리 반올림값"), "iid_J_ms": comparison(iid["J_ms"], 50.07, "반올림값"), "iid_p_fail": comparison(iid["p_fail"], 0.0004, "반올림값"), "ge_J_ms": comparison(ge["J_ms"], 58.46, "반올림값"), "ge_p_fail": comparison(ge["p_fail"], 0.0430, "반올림값")}
        results.append(result)
    agreement = []
    for k, w, uplink, rtt, context_need in ((2, 1280, 2.0, 50.7, 15), (2, 1280, 0.0, 50.0, 4), (2, 1280, 10.0, 120.0, 7), (1, 1280, 0.0, 50.0, 6)):
        differences = []
        for m in range(5):
            for lead in range(m + 1):
                for p in (0.0, 0.02, 0.15, 0.3):
                    generic = model(layout, k, w, m, lead, p, rtt, uplink, context_need)
                    direct = layout.evaluate(k, w, m, lead, p, rtt, uplink, context_need)
                    differences.append(abs(generic["J_ms"] - direct["J"]))
        agreement.append({"context": [k, w, uplink, rtt, context_need], "comparisons": len(differences), "max_abs_J_difference_ms": max(differences)})
    return {"item": "A0-4", "data_kind": "measurement_reanalysis_and_model_world", "source_scripts": ["verify-A1/v04_ge.py", "verify-A1/vgen.py", "audit-cost-model/s26_p18.py"], "model_scope": "정책의 layout.outcomes와 경주·비용식을 재사용하고 패턴 확률만 iid/GE로 바꾼 모형 재현이다. W0 독립 세계 시뮬레이터가 아니다.", "input": {"k": 2, "w_B": 1280, "p": 0.15, "GE_mean_bad_run": 3.0, "GE_bad_to_good": 1.0 / 3.0, "GE_good_to_bad": 0.15 / (3.0 * 0.85), "GE_initial_distribution": "stationary", "rtt_ms": 50.0, "uplink_Mbps": 0.0, "observed_server_bytes_upper_median": upper_median, "observed_server_bytes_median": statistics.median(server_sizes), "n_need": need}, "failure_definition": "ok=false 또는 initial_datagrams>=4. 실제 연결 전체 실패율과 첫 비행 복구 실패를 구분한다.", "processing_note": "2.6 ms는 추가 보정 예시이며 이번 결과에 맞춰 재추정하지 않는다. 기본 GE 결과와 별도 열이다.", "iid_consistency": agreement, "results": results}


if __name__ == "__main__":
    run(analyze)
