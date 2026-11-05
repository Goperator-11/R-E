import json
from pathlib import Path


def ceil_div(value, divisor):
    return -(-value // divisor)


def calculate():
    k, w, n_need, pkt, estimated_pre = 2, 1280, 7, 1280, 41
    prefix = (n_need - 1) * pkt
    base = k * w
    rows = []
    for margin in (0, 20, 30, 40):
        required = (prefix + estimated_pre) // 3 + 1 + ceil_div(margin, 3)
        flight_delta = required - base
        delta = ceil_div(flight_delta, k)
        credit = base + k * delta
        rows.append({
            "margin_server_bytes": margin,
            "required_client_credit_bytes": required,
            "minimum_flight_extra_bytes": flight_delta,
            "actual_original_extra_bytes": k * delta,
            "delta_per_datagram_bytes": delta,
            "slack_at_Apre41_server_bytes": 3 * credit - estimated_pre - prefix,
            "slack_at_Apre54_server_bytes": 3 * credit - 54 - prefix,
        })
    return {
        "kind": "integer_arithmetic_only_no_policy_or_world_imports",
        "inputs": {"k": k, "W": w, "n_need": n_need, "P": pkt,
                   "A_pre_estimate": estimated_pre, "prefix": prefix, "base_credit": base},
        "rows": rows,
        "boundary_checks": {
            "delta6_net_server_budget": 3 * (base + k * 6) - estimated_pre,
            "delta7_net_server_budget": 3 * (base + k * 7) - estimated_pre,
            "without_Apre_required_credit": prefix // 3 + 1,
            "without_Apre_flight_delta": prefix // 3 + 1 - base,
            "without_Apre_per_datagram_delta": ceil_div(prefix // 3 + 1 - base, k),
        },
    }


if __name__ == "__main__":
    output = json.dumps(calculate(), ensure_ascii=False, indent=2) + "\n"
    Path(__file__).with_suffix(".json").write_text(output, encoding="utf-8", newline="\n")
    print(output, end="")
