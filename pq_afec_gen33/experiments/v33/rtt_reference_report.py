import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import re
import statistics
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.v33 import rtt_reference as ref
from padfec3 import learn3

HISTORICAL_JOURNAL_DIR = Path(r"C:\dev\pq_afec_gen31\experiments\state")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def observation(value):
    return ref.RttSample(0, "initial_ack", value, 1280, 0, 0.0, 0.0, 0.0, True, True, True)


def steps():
    rows = []
    for upper in (100.0, 150.0):
        track = ref.RttTrack()
        values = [50.0] * 64 + [upper] * 16 + [25.0] * 16
        for index, value in enumerate(values):
            result = track.observe_connection(index, [observation(value)])
            rows.append(dict(upper_ms=upper, index=index, true_ms=value, **result["state"]))
    return rows


def jitter(out, smoke):
    results = []
    seeds = range(31, 33) if smoke else range(31, 51)
    count = 80 if smoke else 2000
    for rtt, sigma in ((20.0, 5.0), (50.0, 10.0), (50.0, 20.0)):
        for seed in seeds:
            rng = random.Random(seed)
            track = ref.RttTrack()
            name = f"rtt{int(rtt)}_sigma{int(sigma)}_seed{seed}.jsonl"
            totals = {"min_one_wrong": 0, "ewma_one_wrong": 0, "var_one_wrong": 0,
                      "min_two_as_one": 0, "ewma_two_as_one": 0, "var_two_as_one": 0}
            evaluated = 0
            with (out / name).open("x", encoding="utf-8", newline="\n") as f:
                for index in range(count + 32):
                    path = max(0.1, rtt + rng.gauss(0.0, sigma))
                    grades = {}
                    if track.observations:
                        for label, policy_rtt, variance in (("min", track.min_ms, 0.0),
                                ("ewma", track.ewma_ms, 0.0), ("var", track.ewma_ms, track.variation_ms)):
                            ctx = {"k": 1, "W": 1280, "u": 0.0, "rtt": policy_rtt, "n_need": 1}
                            one = ref.classify_hct(ctx, (0, 0, 0), path, True, variance)
                            two = ref.classify_hct(ctx, (0, 0, 0), 2 * path, True, variance)
                            grades[label] = [one, two]
                            if index >= 32:
                                totals[label + "_one_wrong"] += int(one != 0)
                                totals[label + "_two_as_one"] += int(two == 0)
                        if index >= 32:
                            evaluated += 1
                    before = track.to_dict()
                    track.observe_connection(index, [observation(path)])
                    f.write(json.dumps(dict(index=index, path_ms=path, before=before, grades=grades),
                                       allow_nan=False, separators=(",", ":")) + "\n")
            results.append(dict(rtt_ms=rtt, sigma_ms=sigma, seed=seed, rows=count+32,
                                evaluated=evaluated, totals=totals, raw=name, sha256=digest(out / name)))
    return results


def historical(directory):
    groups = {}
    sources = []
    counters = {"rows": 0, "valid_rtt": 0, "approximate_correction": 0, "missing_byte_inputs": 0}
    for path in sorted(directory.glob("p31_run*_units.jsonl")):
        sources.append(dict(path=str(path), sha256=digest(path)))
        with path.open(encoding="utf-8") as f:
            for line in f:
                val = json.loads(line)["val"]
                netem = val.get("netem", {})
                delays = [re.search(r"delay ([0-9.]+)ms", netem.get(d, "")) for d in ("c2s", "s2c")]
                if not all(delays):
                    continue
                rtt = sum(float(m.group(1)) for m in delays)
                rate = re.search(r"rate ([0-9.]+)mbit", netem.get("c2s", ""))
                up = float(rate.group(1)) if rate else 0.0
                for segment in val.get("segments", []):
                    for row in segment.get("rows", []):
                        counters["rows"] += 1
                        if not row.get("ok") or not row.get("path_rtt_valid"):
                            continue
                        counters["valid_rtt"] += 1
                        lead = row.get("lead", row.get("first_flight_lead_dgrams"))
                        width = row.get("ips_eff")
                        nd = row.get("first_flight_parity_dgrams", 0)
                        nb = row.get("first_flight_parity_bytes", 0)
                        key = (rtt, up, segment["arm"], lead)
                        g = groups.setdefault(key, {"raw": [], "corrected": []})
                        g["raw"].append(row["path_rtt_ms"] - rtt)
                        if type(lead) is not int or lead < 0 or not isinstance(width, (int, float)) or width <= 0 or (lead and not nd):
                            counters["missing_byte_inputs"] += 1
                            continue
                        amount = width + (lead * nb / nd if lead else 0)
                        adjustment = amount * 0.008 / up if up else 0
                        g["corrected"].append(row["path_rtt_ms"] - adjustment - rtt)
                        counters["approximate_correction"] += 1
    rows = []
    for key, values in sorted(groups.items(), key=lambda item: repr(item[0])):
        rtt, up, arm, lead = key
        corrected = statistics.median(values["corrected"]) if values["corrected"] else None
        rows.append(dict(rtt_ms=rtt, uplink_mbps=up, arm=arm, lead=lead,
                         n_raw=len(values["raw"]), median_raw_bias_ms=statistics.median(values["raw"]),
                         n_approx=len(values["corrected"]), median_approx_bias_ms=corrected,
                         within_one_ms=None if corrected is None else abs(corrected) <= 1.0))
    return dict(scope="historical_development_approximation_without_packet_ownership",
                sources=sources, counters=counters, groups=rows)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--journal-dir", type=Path, default=HISTORICAL_JOURNAL_DIR)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args(argv)
    args.out.mkdir(exist_ok=False)
    step_rows = steps()
    (args.out / "steps.json").write_text(json.dumps(step_rows, indent=2)+"\n", encoding="utf-8", newline="\n")
    noise = jitter(args.out, args.smoke)
    history = historical(args.journal_dir)
    summary = []
    for rtt, sigma in ((20.0, 5.0), (50.0, 10.0), (50.0, 20.0)):
        selected = [x for x in noise if x["rtt_ms"] == rtt and x["sigma_ms"] == sigma]
        total = sum(x["evaluated"] for x in selected)
        summary.append(dict(rtt_ms=rtt, sigma_ms=sigma, evaluated=total,
            rates={k:sum(x["totals"][k] for x in selected)/total for k in selected[0]["totals"]}))
    result = dict(kind="development_reference_diagnostic", candidate_adopted=False,
                  jitter_scope="synthetic shared Gaussian path delay; true two-RTT labels supplied only for diagnostics",
                  seeds=sorted({x["seed"] for x in noise}), jitter=noise, jitter_summary=summary,
                  historical=history, steps_sha256=digest(args.out / "steps.json"),
                  reference_sha256=digest(Path(ref.__file__)), script_sha256=digest(Path(__file__)),
                  thresholds=dict(alpha=ref.RTT_ALPHA, beta=ref.VAR_ALPHA, variance_multiple=ref.VAR_MULTIPLIER))
    (args.out / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8", newline="\n")
    print(json.dumps(dict(jitter_summary=summary, historical=history["counters"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
