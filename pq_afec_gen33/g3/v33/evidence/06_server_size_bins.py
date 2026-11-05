import sys
sys.dont_write_bytecode = True
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import comparison, histogram, numeric, rows, run


def analyze(context):
    from padfec import policy, quantum
    from padfec3 import learn3
    results = []
    missing = []
    for run_id in ("run1", "run2"):
        filename = f"p31_{run_id}_H_h_c12000_r120_u5_units.jsonl"
        if not (context.journals / filename).exists():
            missing.append(filename)
            continue
        grouped = {}
        for _, value, segment, row in rows(context.load(filename)):
            grouped.setdefault(segment["arm"], []).append(row)
        for arm, observations in sorted(grouped.items()):
            server_sizes = [row["server_bytes"] for row in observations if row.get("ok") and row.get("server_bytes")]
            base_bin = quantum.bin_index(2 * 1280)
            c_pkt = policy.C_PKT_POLICY_DEFAULT
            effective = quantum.bin_needed(12000, None, policy.S0_BASE_MLKEM, c_pkt)
            computed = [learn3.bin_needed_s(float(size), base_bin, c_pkt) for size in server_sizes]
            recorded = [row.get("n_need") for row in observations]
            result = {"run": run_id, "arm": arm, "rows": len(observations), "group": histogram(row.get("group") for row in observations), "recorded_k_hat": histogram(row.get("k_hat") for row in observations), "recorded_n_need": histogram(recorded), "recorded_s_hat": numeric(row.get("s_hat") for row in observations), "observed_server_bytes": numeric(server_sizes), "n_need_from_observed_server_bytes": histogram(computed), "effective_model_n_need": effective, "input": {"cert_B": 12000, "k": 2, "w_B": 1280, "base_bin": base_bin, "s0_base_B": policy.S0_BASE_MLKEM, "c_pkt_B": c_pkt}, "effective_S_at_base_B": 12000 + quantum.s0_at(base_bin, policy.S0_BASE_MLKEM, c_pkt), "expected": {"effective_n_need": comparison(effective, 11, "cert=12000 B의 유효 모형을 기존 식으로 계산")}}
            if run_id == "run1" and arm == "g3auto":
                result["expected"].update({"recorded_n12_count": comparison(sum(value == 12 for value in recorded), 1799, "cold 결정을 제외한 기록 n_need=12 행"), "min_observed_server_bytes": comparison(min(server_sizes) if server_sizes else None, 14058, "배경 문서의 관측 S 최솟값 B"), "max_observed_server_bytes": comparison(max(server_sizes) if server_sizes else None, 14114, "배경 문서의 관측 S 최댓값 B")})
            results.append(result)
    return {"item": "A0-6", "data_kind": "measurement_reanalysis_and_model_world", "source_scripts": ["audit-gen2-foundation/s01_nneed_journals.py"], "definition": "관측 server_bytes를 유효 S 입력으로 간주하는 기존 bin_needed_s와 cert=12000 B에 맞춘 유효 quantum.bin_needed를 나란히 계산한다. 새 보정식을 제안하거나 적용하지 않는다.", "missing_optional_run_files": missing, "results": results}


if __name__ == "__main__":
    run(analyze)
