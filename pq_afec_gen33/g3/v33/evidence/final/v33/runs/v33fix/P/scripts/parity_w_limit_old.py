import sys; sys.dont_write_bytecode=True; sys.stdout.reconfigure(encoding="utf-8")
import json
sys.path.insert(0, r"C:\Users\scien\AppData\Local\Temp\claude\C--Users-scien\98dad099-940c-4208-8359-61078035dc93\scratchpad\v33fix2\P-policy-claims\oldroot")
from padfec import policy
from padfec3 import decide3, layout, learn3
print("POLICY_VERSION", learn3.POLICY_VERSION, "UDP_MAX", decide3.UDP_MAX, "MAX_IPS", decide3.MAX_IPS, "K_MAX", layout.K_MAX, "M_MAX", decide3.M_MAX, "MIN_W", decide3.MIN_W)
c_pkt = policy.C_PKT_POLICY_DEFAULT
S_VALUES = (2000.0, 9000.0, 16000.0, 30000.0)
W_RANGE = range(decide3.MIN_W, decide3.MAX_IPS + 1)
out = {"udp_max": decide3.UDP_MAX, "max_ips": decide3.MAX_IPS, "c_pkt": c_pkt, "S_values": S_VALUES,
       "W_range": [W_RANGE.start, W_RANGE.stop - 1], "per_k": {}}
for k in range(1, layout.K_MAX + 1):
    has = {}
    for W in W_RANGE:
        flags = []
        for S in S_VALUES:
            c = decide3.candidates3(k, W, S, c_pkt)
            flags.append(any(x["m"] > 0 for x in c))
        has[W] = flags
    any_par = [W for W, f in has.items() if any(f)]
    all_par = [W for W, f in has.items() if all(f)]
    w_max_any = max(any_par) if any_par else None
    w_max_all = max(all_par) if all_par else None
    gaps = [W for W in W_RANGE if W <= (w_max_any or 0) and not all(has[W])]
    formula = 1452 - policy.PARITY_OVERHEAD_BASE - policy.PARITY_OVERHEAD_PER_K * k
    out["per_k"][k] = {"w_max_with_parity_any_S": w_max_any, "w_max_with_parity_all_S": w_max_all,
                       "W_without_parity_below_max": gaps[:20], "n_gaps": len(gaps),
                       "formula_udp_max_minus_39_minus_6k": formula}
    print("k", k, "max W with parity candidate:", w_max_any, "(all S:", w_max_all, ") gaps", len(gaps), "formula", formula)
detail = {}
for W in (1280, 1350, 1395, 1396, 1400, 1401, 1402, 1406):
    for k in range(1, layout.K_MAX + 1):
        row = []
        for S in S_VALUES:
            c = decide3.candidates3(k, W, S, c_pkt)
            row.append({"S": S, "n": len(c), "n_parity": sum(1 for x in c if x["m"] > 0),
                        "actions": [list(x["action"]) for x in c] if len(c) <= 4 else None})
        detail["W%d_k%d" % (W, k)] = row
        print("W", W, "k", k, [(r["S"], r["n"], r["n_parity"]) for r in row])
out["detail"] = detail
json.dump(out, open(sys.argv[1], "w", encoding="utf-8"), indent=1)
