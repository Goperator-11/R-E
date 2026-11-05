import sys
sys.dont_write_bytecode = True
import argparse
import collections
from concurrent.futures import ProcessPoolExecutor
import gzip
import hashlib
import json
import multiprocessing
from pathlib import Path
import platform
import time


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA = "padfec.v33fix.replay/1"
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
OUT = ROOT / "g3/v33/V33FIX_replay_v1.json"
PROTOCOL = ROOT / "g3/v33/bench_protocol.json"
W1_SOURCE = "W1_raw_v32"
L3_OVERLAY = "L3_record_only_v1.json"
WIDE_PARITY_MAX = 1500 - 28
FINAL_SUMMARY_KEYS = ("p_mean", "p_map", "p_ge_010", "S_hat", "k_hat", "n_dec", "n_reeval", "guard_alarms")
V32_STATS = ("obs", "upd", "predict", "shield", "nominal2", "guard", "no_base", "no_ctx", "events",
             "fail", "resid", "reeval", "alarm_raised", "alarm_cleared")
L3_STATE_SKIP = {"v", "stats", "monitor", "monitor_pending"}
L3_STATS_SKIP = {"alarm_raised"}


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def policy_sources():
    return {path.relative_to(ROOT).as_posix(): file_hash(path)
            for package in ("afec", "padfec", "padfec3")
            for path in sorted((ROOT / package).rglob("*.py"))}


def summary_files(folder):
    return sorted(path for path in Path(folder).glob("seed?????.json"))


def none_tasks(runs, protocol_sha):
    root = Path(runs) / W1_SOURCE
    manifest = read_json(root / "manifest.json")
    if manifest["protocol_sha256"] != protocol_sha:
        raise ValueError("W1 v32 raw protocol differs from the repository protocol")
    tasks = []
    for cell_dir in sorted((root / "v32" / "full").iterdir()):
        for path in summary_files(cell_dir):
            summary = read_json(path)
            if (summary["generation"], summary["variant"], summary["scenario"]) != ("v32", "full", cell_dir.name):
                raise ValueError(f"unexpected W1 run identity: {path}")
            tasks.append({"mode": "none", "source": str(root), "summary": str(path)})
    return tasks, {"dir": str(root), "manifest_sha256": file_hash(root / "manifest.json"),
                   "policy_source_root": manifest["policy_source_fingerprints"]["v32"]["source_root"],
                   "policy_files_sha256": manifest["policy_source_fingerprints"]["v32"]["files"]}


def c1_tasks(runs, protocol_sha):
    tasks, sources = [], []
    for root in sorted(Path(runs).glob("L3_raw_v1_*")):
        if not root.is_dir() or not (root / "manifest.json").is_file():
            continue
        manifest = read_json(root / "manifest.json")
        if Path(manifest["overlay_path"]).name != L3_OVERLAY or manifest["observation_modes"] != ["c1"]:
            continue
        if manifest["protocol_sha256"] != protocol_sha:
            raise ValueError(f"L3 raw protocol differs: {root}")
        sources.append({"dir": str(root), "manifest_sha256": file_hash(root / "manifest.json"),
                        "scenarios": manifest["scenarios"],
                        "policy_source_root": manifest["policy"]["fingerprint"]["source_root"]})
        for cell in manifest["scenarios"]:
            for path in summary_files(root / "c1" / cell):
                summary = read_json(path)
                if (summary["observation_mode"], summary["scenario"]) != ("c1", cell):
                    raise ValueError(f"unexpected L3 run identity: {path}")
                tasks.append({"mode": "c1", "source": str(root), "summary": str(path)})
    return tasks, sources


def load_rows(summary):
    trace = Path(summary["trace_path"])
    if file_hash(trace) != summary["trace_sha256"]:
        raise ValueError(f"trace hash differs: {trace}")
    rows = []
    with gzip.open(trace, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["index"] != len(rows):
                raise ValueError("trace index differs")
            rows.append(row)
    if len(rows) != summary["n"]:
        raise ValueError("trace length differs")
    return rows


def final_differences(mode, summary, learn3, st):
    if mode == "none":
        expected = summary["final_state"]
        post = learn3.post_summary(learn3.combined(st))
        actual = {"p_mean": post["p_mean"], "p_map": post["p_map"], "p_ge_010": post["p_ge_010"],
                  "S_hat": learn3.s_hat(st), "k_hat": learn3.k_hat(st), "n_dec": st.n_dec,
                  "n_reeval": st.n_reeval, "guard_alarms": dict(st.g_alarm)}
        bad = [key for key in FINAL_SUMMARY_KEYS if actual[key] != expected[key]]
        bad += ["stats." + key for key in V32_STATS if st.stats[key] != expected["stats"][key]]
        return bad
    expected = summary["final_serialized_state"]
    actual = json.loads(json.dumps(st.to_json()))
    bad = [key for key in expected if key not in L3_STATE_SKIP and actual.get(key) != expected[key]]
    bad += ["stats." + key for key in expected["stats"]
            if key not in L3_STATS_SKIP and actual["stats"].get(key) != expected["stats"][key]]
    return bad


def replay(task, parity_max):
    from padfec3 import decide3, learn3
    decide3.UDP_MAX = parity_max
    learn3.clear_model_cache()
    summary = read_json(task["summary"])
    protocol = read_json(PROTOCOL)
    scenario = {s["id"]: s for s in protocol["scenarios"]}[summary["scenario"]]
    W, u, c_pkt = scenario["context"]["w"], scenario["context"]["uplink_mbps"], protocol["c_pkt"]
    rows = load_rows(summary)
    st = learn3.new_state()
    steps = []
    for row in rows:
        if scenario["reset_each_connection"]:
            st = learn3.new_state()
        path_before = "c1" if st.c1_seen else "none"
        decision = decide3.decide3(st, W, u, row["policy_decide_input"]["rtt_ms"], c_pkt)
        recorded = row["decision"]
        steps.append({"index": row["index"], "path": path_before,
                      "match": list(decision["action"]) == recorded["action"] and decision["why"] == recorded["why"],
                      "ej_exact": decision["ej"] == recorded["ej"],
                      "p_mean_exact": decision["p_mean"] == recorded["p_mean"],
                      "n_cands_changed": decision["n_cands"] != recorded["n_cands"],
                      "recorded": {"action": recorded["action"], "why": recorded["why"], "ej": recorded["ej"],
                                   "n_cands": recorded["n_cands"]},
                      "replayed": {"action": list(decision["action"]), "why": decision["why"], "ej": decision["ej"],
                                   "n_cands": decision["n_cands"]}})
        request = row["policy_observe_input"]
        arrivals = None
        if task["mode"] == "c1":
            arrivals = request["optional"]["first_flight_evidence"]
        elif "optional" in request:
            raise ValueError("none replay received first-flight evidence")
        learn3.observe3(st, tuple(request["action"]), request["hct_ms"], request["ok"], request["k_obs"],
                        request["srv_bytes"], request["rtt_ms"], W=W, u_mbps=u, c_pkt=c_pkt,
                        j_pred=request["j_pred"], arrivals=arrivals)
    first_c1 = None
    if task["mode"] == "c1":
        first_c1 = next((row["index"] for row in rows
                         if row["policy_observe_input"]["optional"]["first_flight_evidence"]["src"] in ("c1", "ack")), None)
    return {"summary": summary, "steps": steps, "final_differences": final_differences(task["mode"], summary, learn3, st),
            "first_c1_index": first_c1, "trace_sha256": summary["trace_sha256"]}


def run_task(task):
    capped = replay(task, task["parity_max"])
    summary = capped.pop("summary")
    mismatched = [step for step in capped["steps"] if not step["match"]]
    wide = None
    if mismatched or capped["final_differences"]:
        wide_result = replay(task, WIDE_PARITY_MAX)
        wide = {"mismatch_indices": [step["index"] for step in wide_result["steps"] if not step["match"]],
                "final_differences": wide_result["final_differences"]}
    wide_mismatch = set() if wide is None else set(wide["mismatch_indices"])
    steps = capped["steps"]
    first_c1 = capped["first_c1_index"]
    first_divergence = next((step["index"] for step in steps if not step["p_mean_exact"]), None)
    diverged_before_c1 = (task["mode"] == "c1" and first_c1 is not None and first_divergence is not None
                          and first_divergence <= first_c1)
    mismatches = []
    for step in mismatched:
        cause = "parity_cap_1452" if step["index"] not in wide_mismatch else "unexplained"
        if cause == "unexplained" and diverged_before_c1:
            cause = ("before_first_c1_evidence" if step["index"] <= first_c1
                     else "state_diverged_before_first_c1_evidence")
        mismatches.append({"index": step["index"], "path": step["path"], "cause": cause,
                           "p_mean_exact": step["p_mean_exact"],
                           "recorded": step["recorded"], "replayed": step["replayed"]})
    return {"mode": task["mode"], "cell": summary["scenario"], "seed": summary["seed"],
            "source": task["source"], "trace_sha256": capped["trace_sha256"], "n": len(steps),
            "decision_match": sum(step["match"] for step in steps),
            "decision_mismatch": len(mismatched),
            "ej_exact": sum(step["ej_exact"] for step in steps),
            "p_mean_exact": sum(step["p_mean_exact"] for step in steps),
            "n_cands_changed": sum(step["n_cands_changed"] for step in steps),
            "first_c1_index": first_c1, "first_state_divergence_index": first_divergence,
            "path_counts": dict(collections.Counter(step["path"] for step in steps)),
            "final_state_match": not capped["final_differences"],
            "final_differences": capped["final_differences"],
            "wide_parity_check": wide, "mismatches": mismatches}


def aggregate(results):
    keys = ("n", "decision_match", "decision_mismatch", "ej_exact", "p_mean_exact", "n_cands_changed")
    modes = {}
    for result in results:
        mode = modes.setdefault(result["mode"], {"total": dict.fromkeys(keys, 0), "cells": {}})
        cell = mode["cells"].setdefault(result["cell"], {"total": dict.fromkeys(keys, 0), "seeds": {}})
        for target in (mode["total"], cell["total"]):
            for key in keys:
                target[key] += result[key]
            for mismatch in result["mismatches"]:
                name = "mismatch_" + mismatch["cause"]
                target[name] = target.get(name, 0) + 1
            target["final_state_match_seeds"] = target.get("final_state_match_seeds", 0) + int(result["final_state_match"])
            target["seeds"] = target.get("seeds", 0) + 1
        cell["seeds"][str(result["seed"])] = {key: result[key] for key in
            keys + ("first_c1_index", "first_state_divergence_index", "path_counts", "final_state_match",
                    "final_differences", "trace_sha256")}
        cell["seeds"][str(result["seed"])]["mismatch_causes"] = dict(collections.Counter(m["cause"] for m in result["mismatches"]))
    return modes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=Path, default=RUNS)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--modes", nargs="+", choices=("none", "c1"), default=["none", "c1"])
    parser.add_argument("--cells", nargs="+")
    parser.add_argument("--seeds", nargs="+", type=int)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.out.exists() and not args.overwrite:
        raise SystemExit(f"{args.out} exists; pass --overwrite to replace it")
    from padfec import policy
    from padfec3 import decide3, learn3
    started = time.time()
    protocol_sha = file_hash(PROTOCOL)
    sources_before = policy_sources()
    tasks, inputs = [], {}
    if "none" in args.modes:
        found, inputs["none"] = none_tasks(args.runs, protocol_sha)
        tasks += found
    if "c1" in args.modes:
        found, inputs["c1"] = c1_tasks(args.runs, protocol_sha)
        tasks += found
    selected = []
    for task in tasks:
        summary = read_json(task["summary"])
        if args.cells and summary["scenario"] not in args.cells:
            continue
        if args.seeds and summary["seed"] not in args.seeds:
            continue
        selected.append(dict(task, parity_max=policy.QUICGO_MAX_IPS))
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=multiprocessing.get_context("spawn")) as executor:
        results = list(executor.map(run_task, selected, chunksize=4))
    if policy_sources() != sources_before:
        raise RuntimeError("policy sources changed during replay")
    results.sort(key=lambda r: (r["mode"], r["cell"], r["seed"]))
    report = {"schema": SCHEMA, "policy_version": learn3.POLICY_VERSION, "state_version": learn3.STATE_VERSION,
              "parity_max": policy.QUICGO_MAX_IPS, "wide_parity_max": WIDE_PARITY_MAX,
              "decide3_udp_max": decide3.UDP_MAX,
              "protocol_path": str(PROTOCOL), "protocol_sha256": protocol_sha,
              "policy_sources_sha256": sources_before, "inputs": inputs,
              "selection": {"modes": args.modes, "cells": args.cells, "seeds": args.seeds},
              "replay_rules": {
                  "none": "W1_raw_v32 v3.2 traces; observe3 without arrivals; decision compared by action and why",
                  "c1": "L3_record_only_v1 c1 traces; observe3 with recorded first_flight_evidence; decision compared by action and why",
                  "inputs": "recorded decide rtt_ms and recorded observe inputs, including recorded action and j_pred",
                  "cause": ("a mismatch that disappears when decide3.UDP_MAX is widened to 1472 is parity_cap_1452; "
                            "in c1 replay, when the replayed posterior first differs at or before the first c1/ack "
                            "evidence, mismatches up to that evidence are before_first_c1_evidence and later ones "
                            "are state_diverged_before_first_c1_evidence; every other mismatch is unexplained")},
              "summary": aggregate(results),
              "mismatches": [dict(m, mode=r["mode"], cell=r["cell"], seed=r["seed"])
                             for r in results for m in r["mismatches"]],
              "runs": [{key: value for key, value in r.items() if key != "mismatches"} for r in results],
              "python": platform.python_version(), "elapsed_seconds": round(time.time() - started, 1)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w" if args.overwrite else "x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=1, allow_nan=False)
        stream.write("\n")
    print(json.dumps({key: value["total"] for key, value in report["summary"].items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
