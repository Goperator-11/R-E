import argparse
import gc
import hashlib
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROW_FIELDS = ("i", "ok", "ms", "ips_eff", "m_used", "parity_sent", "bytes_parity", "server_binary_sha256",
              "first_flight_bytes", "first_flight_parity_bytes", "extra_sent", "arrivals", "policy_path",
              "feedback_wait_received", "policy_uplink_mbps")
RUNS = {"M0": "final_m0_iter022_20261106", "M1": "final_m1_iter024_20261107", "X1": "final_x1_iter027_20261107",
        "X9": "final_x9_iter031_20261107", "X6": "final_x6_iter035_20261107"}


def light_row(row):
    light = {name: row[name] for name in ROW_FIELDS if name in row}
    trace = row.get("flight_trace")
    if isinstance(trace, dict):
        light["flight_trace"] = {"omitted": trace.get("omitted"),
                                 "records": [{"parity_sent": item.get("parity_sent"), "parity_bytes": item.get("parity_bytes")}
                                             for item in trace.get("records", [])]}
    return light


def light_payload(payload, keep_cache, keep_collection):
    light = {"attempt": payload.get("attempt"), "client_rc": payload["client_rc"], "checks": payload.get("checks", {}),
             "tc_before": {k: {"returncode": v["returncode"], "stdout": v["stdout"]} for k, v in payload["tc_before"].items()},
             "tc_after": {k: {"returncode": v["returncode"], "stdout": v["stdout"]} for k, v in payload["tc_after"].items()},
             "server": {"returncode": payload["server"]["returncode"], "stats": payload["server"].get("stats"),
                        "certificate": payload["server"].get("certificate")},
             "commands": {"client": payload["commands"]["client"]},
             "rows": [light_row(row) for row in payload["rows"]]}
    if keep_cache:
        light["cache_after"] = payload.get("cache_after")
    if keep_collection:
        light["collection"] = {"observations": payload["collection"]["observations"]}
    return light


def recheck(root, runs_dir):
    from experiments.v33.lib import arms, observations, report_checks

    report = {}
    for task, run in RUNS.items():
        manifest = json.loads((runs_dir / run / f"manifest_{run}.json").read_text(encoding="utf-8"))
        plan = manifest["plan"]
        units = arms.iter_units(plan, [task])
        last = {}
        for unit in units:
            key = (unit["cell"], unit["arm"], unit["trajectory"])
            if key not in last or (unit["phase"], unit["block"]) > last[key][0]:
                last[key] = ((unit["phase"], unit["block"]), unit["key"])
        keep = {value[1] for value in last.values()}
        payloads = {}
        events = []
        previous = "0" * 64
        sequence = 0
        with (runs_dir / run / f"units_{run}.jsonl").open("rb") as stream:
            for line in stream:
                record = json.loads(line)
                digest = record.pop("record_sha256")
                if record["sequence"] != sequence or record["previous_sha256"] != previous:
                    raise ValueError("journal chain broken: " + run)
                encoded = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")
                if hashlib.sha256(encoded).hexdigest() != digest:
                    raise ValueError("journal digest broken: " + run)
                previous, sequence = digest, sequence + 1
                if record["kind"] == "event":
                    if record["data"].get("event") == "netem":
                        events.append(record["data"])
                elif record["kind"] == "block":
                    for entry in record["data"]["units"]:
                        payloads[entry["key"]] = light_payload(entry["payload"], entry["key"] in keep, task == "M0")
                del record
        ordered = [payloads[unit["key"]] for unit in units]
        observed = (observations.summarize_observations(plan, [item["collection"]["observations"] for item in ordered])
                    if task == "M0" else [])
        result = report_checks.summarize_checks(plan, task, units, ordered, observed, events=events, extended=True)
        committed = json.loads((root / "g3/v33/results" / f"v33_dev_{task}_{run}.json").read_text(encoding="utf-8"))
        old_names = set(committed["check_details"])
        changed = sorted(name for name in old_names
                         if name in result["details"] and result["details"][name] != committed["check_details"][name])
        lost = sorted(old_names - set(result["details"]))
        added = sorted(set(result["details"]) - old_names)
        report[task] = {"run": run, "checks": result["checks"], "added": added, "old_details_changed": changed,
                        "old_details_lost": lost, "statuses_new": {name: result["checks"][name] for name in added},
                        "all_pass": set(result["checks"].values()) == {"pass"},
                        "realized_loss": [item for item in result["details"].get("realized_loss", [])],
                        "success_rate_min": min(item["rate"] for item in result["details"]["success_rate"]),
                        "success_groups": len(result["details"]["success_rate"]),
                        "policy_uplink": result["details"].get("policy_uplink", []),
                        "netem_units": len(result["details"].get("netem_config", []))}
        print(task, "all_pass", report[task]["all_pass"], "added", added, "changed", changed, "lost", lost, flush=True)
        del payloads, ordered, events, committed, result
        gc.collect()
    for task in report:
        report[task]["policy_uplink"] = {"n": len(report[task]["policy_uplink"]),
                                         "values": sorted({value for item in report[task]["policy_uplink"]
                                                           for value in item["values"]}),
                                         "statuses": sorted({item["status"] for item in report[task]["policy_uplink"]})}
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="완료 run 다섯 건의 저널로 확장 실행 검사를 다시 돌린다")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--runs-dir", type=Path, default=Path.home() / "v33_runs")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        report = recheck(root, args.runs_dir)
        with args.out.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(report, indent=1, ensure_ascii=False))
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print("DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
