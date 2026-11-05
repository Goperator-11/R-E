import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import collections
import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
ROOT = Path(r"C:\dev\pq_afec_gen33")
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
checker = read(RUNS / "L5_joint_artifact_check_v3.json")
assert checker["status"] == "pass" and checker["error"] is None
family = read(RUNS / "L5_joint_action_family_v1.json")
plan = read(RUNS / "L5_full_v1_plan.json")
params_path = ROOT / "experiments/v33/worldparams.json"
params = read(params_path)
cap = params["server"]["decoder_max_datagram_bytes"]
base, per_k = params["fec"]["parity_overhead_base"], params["fec"]["parity_overhead_per_k"]
roles = {Path(j["out"]).name: j["policy"] for j in plan["jobs"]}
groups = {}
inputs = {}
for name, digest in sorted(family["inputs_sha256"].items()):
    p = Path(name)
    if not (p.suffix == ".gz" and p.parent.name == "B12_c12000"):
        continue
    directory, mode = p.parents[2].name, p.parent.parent.name
    if directory.startswith("L1_raw_") and mode in ("none", "c1"):
        role = "L1"
    elif directory in roles:
        role = roles[directory]
    else:
        continue
    assert sha(p) == digest == checker["files_sha256"][name]
    inputs[name] = digest
    key = role + ":" + mode
    g = groups.setdefault(key, {"runs": 0, "rows_including_warmup": 0, "parity_oversize_rows": 0,
        "actions": collections.Counter(), "oversize_actions": collections.Counter(),
        "observer_reasons": collections.Counter(), "loss_updates": collections.Counter(),
        "prefixes": collections.Counter(), "phases": {}, "examples": []})
    g["runs"] += 1
    with gzip.open(p, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            action = tuple(row["action"])
            k, w = 2, 1280 + action[0]
            parity = w + base + per_k * k
            oversize = action[1] + action[2] > 0 and parity > cap
            g["rows_including_warmup"] += 1
            g["parity_oversize_rows"] += oversize
            g["actions"][str(action)] += 1
            if oversize:
                g["oversize_actions"][str(action)] += 1
            info = row["observation_info"]
            g["observer_reasons"][str(row.get("observer_diagnostics", {}).get("reason"))] += 1
            g["loss_updates"][str(info.get("loss_update_kind"))] += 1
            sample = info.get("size_sample")
            if sample:
                g["prefixes"][str((sample["bytes"], sample["prefix"], sample["n_need"]))] += 1
            ph = g["phases"].setdefault(str(row["phase"]), {"n": 0, "p_true": row["phase_p"], "p_pre_sum": 0.0})
            assert ph["p_true"] == row["phase_p"]
            ph["n"] += 1
            ph["p_pre_sum"] += row["p_mean_pre"]
            if "seed00032." in p.name and row["index"] in (1, 2, 1499):
                g["examples"].append({"path": name, "index": row["index"], "action": action,
                    "k_obs": row["policy_observe_input"]["k_obs"], "W_eff": w, "parity_bytes": parity,
                    "decoder_cap": cap, "oversize": oversize, "p_pre": row["p_mean_pre"],
                    "phase_p": row["phase_p"], "n_need": row["decision"].get("n_need"),
                    "prefix": info.get("size_sample", {}).get("prefix"),
                    "observation_reason": row.get("observer_diagnostics", {}).get("reason"),
                    "loss_update_kind": info.get("loss_update_kind")})
for g in groups.values():
    for ph in g["phases"].values():
        ph["mean_p_pre"] = ph.pop("p_pre_sum") / ph["n"]
sources = [params_path, ROOT / "experiments/v33/worldsim.py",
    ROOT / "g3/v33/policy_snapshots/L5_v1/padfec3/decide3.py",
    ROOT / "g3/v33/policy_snapshots/L5_v1/padfec3/layout.py",
    ROOT / "g3/v33/policy_snapshots/L5_v1/padfec3/learn3.py"]
result = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
    "script_sha256": sha(__file__), "checker_sha256": sha(RUNS / "L5_joint_artifact_check_v3.json"),
    "groups": groups, "inputs_sha256": inputs, "sources_sha256": {str(p): sha(p) for p in sources},
    "geometry": {"k": 2, "base_W": 1280, "parity_base": base, "parity_per_k": per_k, "decoder_cap": cap},
    "scope": "Read-only trace diagnosis including warmup. No new performance samples, candidate changes or adoption. Oversize geometry is exact; causal contribution to total regression has not been isolated by ablation."}
out = RUNS / "L5_c12000_diagnosis_v1.json"
with out.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps({key: {k: v for k, v in value.items() if k != "examples"} for key, value in groups.items()}, ensure_ascii=False))
