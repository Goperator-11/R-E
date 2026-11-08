import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"C:\dev\pq_afec_gen33"
SNAP = ROOT + r"\g3\v33\policy_snapshots\M1_v1"
sys.path.insert(0, ROOT)
sys.path.insert(0, SNAP)
import collections
from concurrent.futures import ProcessPoolExecutor
import datetime
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import time

RAW = Path(r"C:\dev\codex_handoff\v33\runs\M1_factorial_raw_v1")
SEED = 31
N = int(sys.argv[2]) if len(sys.argv) > 2 else 6000
BIG = dict(k=2, w=1280, rtt_ms=50.0, uplink_mbps=2.0, cert_bytes=16000)
B7 = dict(k=2, w=1280, rtt_ms=50.0, uplink_mbps=2.0, cert_bytes=9000, p=0.02, s2c_loss=0.01)
B10 = dict(k=2, w=1280, rtt_ms=50.0, uplink_mbps=0.0, cert_bytes=4032, p=0.15, loss_model="ge", burst_length=3)
C6 = dict(k=2, w=1280, rtt_ms=120.0, uplink_mbps=10.0, cert_bytes=6000, p=0.08)
C12 = dict(k=2, w=1280, rtt_ms=120.0, uplink_mbps=5.0, cert_bytes=12000, p=0.08)
UPLINK_CASES = (("B10", B10, (0, 1, 3)), ("B10", B10, (0, 0, 4)), ("B12_c6000_p0.08", C6, (0, 3, 1)),
                ("B12_c6000_p0.08", C6, (0, 0, 4)), ("B12_c12000_p0.08", C12, (0, 4, 0)), ("B12_c12000_p0.08", C12, (0, 0, 4)))


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def key(action):
    return ",".join(map(str, action))


def series(job):
    label, context, action, params, seed, n = job
    from experiments.v33 import worldsim_m1 as M
    world = M.World(params=params, seed=seed)
    ctx = M.WorldContext(**context)
    rows = []
    for connection in range(n):
        row = world.sample(ctx, M.Action(*action), connection=connection)
        rows.append((row["hct"], row["world_class"]))
    return label, rows


def summary(rows):
    values = [x[0] for x in rows]
    classes = collections.Counter(x[1] for x in rows)
    tail = [x[0] for x in rows if x[1] == "tail"]
    return {"n": len(values), "mean_hct_ms": statistics.fmean(values), "se_ms": statistics.stdev(values) / math.sqrt(len(values)),
            "class_counts": dict(classes), "tail_mean_hct_ms": statistics.fmean(tail) if tail else None}


def paired(a, b):
    diffs = [x[0] - y[0] for x, y in zip(a, b)]
    return {"mean_ms": statistics.fmean(diffs), "se_ms": statistics.stdev(diffs) / math.sqrt(len(diffs))}


def model(action, p, n_need, hold, rtt=50.0, u=2.0):
    from padfec3 import layout
    d, lead, trail = action
    return layout.evaluate(2, 1280 + d, lead + trail, lead, p, rtt, u, n_need, lead_hold=hold)["J"]


def pattern_terms(p):
    from padfec3 import layout
    k, w, rtt, u, n = 2, 1280, 50.0, 2.0, 15
    lead, trail = 3, 1
    m = lead + trail
    resp = layout.response_term(m, w, u, "v3")
    apre = layout.preflight_bytes(k, u)
    out = {}
    for hold in (False, True):
        rows = {}
        for rec in layout.outcomes(k, m, lead, w, p, u, lead_hold=hold):
            if rec["kind"] != "ok":
                continue
            value = 0.0
            for weight, credit in rec["branches"]:
                rounds = layout.rtt_count(credit, n, apre)
                value += weight * (rec["t_dec"] + rtt * rounds + (resp if rounds == 2 else 0.0))
            rows[tuple(int(x) for x in rec["pattern"])] = (rec["pr"], rec["t_dec"], rec.get("base_credit"), value)
        out[hold] = rows
    target = (1, 1, 1, 0, 1, 1)
    contribution = (out[True][target][3] - out[False][target][3]) * out[False][target][0]
    total = model((0, 3, 1), p, 15, True) - model((0, 3, 1), p, 15, False)
    return {"pattern": list(target), "probability": out[False][target][0],
            "off": {"t_dec_ms": out[False][target][1], "credit_at_decision": out[False][target][2], "expected_hct_ms": out[False][target][3]},
            "hold": {"t_dec_ms": out[True][target][1], "credit_at_decision": out[True][target][2], "expected_hct_ms": out[True][target][3]},
            "weighted_contribution_ms": contribution, "model_total_hold_minus_off_ms": total}


def raw_actions(arm, phase=None):
    counts, hcts, p_pre = collections.Counter(), collections.defaultdict(list), []
    hashes = {}
    for seed in range(31, 51):
        path = RAW / arm / f"seed{seed:05d}.jsonl.gz"
        hashes[str(path)] = file_hash(path)
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if phase is not None and row.get("phase") != phase:
                    continue
                action = tuple(row["action"])
                counts[action] += 1
                hcts[action].append(row["hct_ms"])
                p_pre.append(row["p_mean_pre"])
    total = sum(counts.values())
    top = [{"action": list(a), "share": c / total, "mean_hct_ms": statistics.fmean(hcts[a])} for a, c in counts.most_common(4)]
    return {"arm": arm, "phase": phase, "connections": total, "top_actions": top,
            "p_mean_pre_median": statistics.median(p_pre), "inputs_sha256": hashes}


def masked(action, params):
    from experiments.v33 import worldsim_m1 as M
    ctx = M.WorldContext(**dict(BIG, p=0.0))
    row = M.World(params=params, seed=SEED).sample(ctx, M.Action(*action), trace=True,
                                                   overrides={"c2s": [1, 1, 1, 0, 1, 1] + [1] * 200, "decision_delay_ms": 0.0})
    ready = next(r["time_ms"] for r in row["trace"] if r["event"] == "server_ready")
    credit = max((r["total"] for r in row["trace"] if r["event"] == "server_credit" and r["time_ms"] <= ready), default=0)
    return {"hct_ms": row["hct"], "server_ready_ms": ready, "stack_credit_at_ready": credit}


def main():
    started_kst = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()
    started = time.monotonic()
    off = {"lead_mode": "credit_only"}
    b2_actions = ((0, 4, 0), (0, 3, 1), (0, 0, 4), (0, 2, 2), (0, 1, 3))
    b7_actions = ((0, 3, 1), (0, 2, 2), (0, 1, 3), (0, 0, 4))
    jobs = []
    for action in b2_actions:
        for name, params in (("hold", None), ("off", off)):
            jobs.append((("B2_p0.25", name, action), dict(BIG, p=0.25), action, params, SEED, N))
    for action in ((0, 4, 0), (0, 3, 1)):
        jobs.append((("B2_p0.25", "hold_no_response_xor", action), dict(BIG, p=0.25), action, {"fec": {"response_xor": False}}, SEED, N))
    for action in b7_actions:
        jobs.append((("B7", "hold", action), B7, action, None, SEED, N))
    for name, params in (("hold", None), ("off", off)):
        jobs.append((("bigcert_p0.02", name, (0, 3, 1)), dict(BIG, p=0.02), (0, 3, 1), params, SEED, N))
    for label, context, action in UPLINK_CASES:
        for name, params in (("hold_d20_fixed", None), ("hold_context_oracle", {"hold_uplink_source": "context"})):
            jobs.append(((label, name, action), context, action, params, SEED, N))
    with ProcessPoolExecutor(max_workers=24) as pool:
        data = dict(pool.map(series, jobs))
    b2 = {"world": {name + ":" + key(a): summary(rows) for (label, name, a), rows in data.items() if label == "B2_p0.25"},
          "paired_hold_040_minus_031_ms": paired(data[("B2_p0.25", "hold", (0, 4, 0))], data[("B2_p0.25", "hold", (0, 3, 1))]),
          "model_hold_J_ms": {key(a): model(a, 0.25, 15, True) for a in b2_actions},
          "model_off_J_ms": {key(a): model(a, 0.25, 15, False) for a in b2_actions},
          "frozen_run_selection_m1_c1": raw_actions("hold_m1_c1_B2", phase=1),
          "frozen_run_selection_l1_c1": raw_actions("hold_l1_c1_B2", phase=1)}
    b7 = {"world_hold": {key(a): summary(data[("B7", "hold", a)]) for a in b7_actions},
          "paired_hold_031_minus_022_ms": paired(data[("B7", "hold", (0, 3, 1))], data[("B7", "hold", (0, 2, 2))]),
          "frozen_run_selection_m1_none": raw_actions("hold_m1_none_B7"),
          "frozen_run_selection_l1_none": raw_actions("hold_l1_none_B7"),
          "model_hold_J_ms_at_p": {str(p): {key(a): model(a, p, 9, True) for a in b7_actions} for p in (0.02, 0.1378, 0.25)}}
    decision = {"world_bigcert_p0.02": {"hold": summary(data[("bigcert_p0.02", "hold", (0, 3, 1))]),
                                        "off": summary(data[("bigcert_p0.02", "off", (0, 3, 1))]),
                                        "paired_hold_minus_off_ms": paired(data[("bigcert_p0.02", "hold", (0, 3, 1))], data[("bigcert_p0.02", "off", (0, 3, 1))])},
                "model_pattern": pattern_terms(0.02),
                "masked_pattern_world": {"off": masked((0, 3, 1), off), "hold": masked((0, 3, 1), None)},
                "one_parity_datagram_ms_at_2mbps": 8.0 * 1331 / 2000.0,
                "first_flight_bound_ms_m1_fixed_checks": 8.0 * (2 * 1280 + 4 * 1331) / 2000.0 + 1.0}
    uplink = []
    for label, context, action in UPLINK_CASES:
        a, b = data[(label, "hold_d20_fixed", action)], data[(label, "hold_context_oracle", action)]
        uplink.append({"context": label, "context_uplink_mbps": context["uplink_mbps"], "action": list(action),
                       "d20_fixed": summary(a), "context_oracle": summary(b), "paired_fixed_minus_oracle_ms": paired(a, b)})
    from experiments.v33 import initial_count_diag
    source = Path(__file__).read_text(encoding="utf-8")
    payload = {"item": "E-M1-1, E-M1-3, E-M1-4, E verifier missed 1", "started_kst": started_kst,
               "seconds": time.monotonic() - started, "seed": SEED, "connections": N,
               "world_sources_sha256": {name: file_hash(Path(ROOT) / "experiments" / "v33" / name) for name in ("worldsim_m1.py", "world_receiver_m1.py", "worldparams_m1.json")},
               "snapshot_sha256": {name: file_hash(Path(SNAP) / "padfec3" / name) for name in ("layout.py", "hold_layout.py")},
               "script_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(), "script_source": source,
               "b2_pure_lead": b2, "b7_none": b7, "decision_rule_p0.02": decision, "hold_uplink": uplink,
               "scope": "Small development diagnostic in the V33FIX M1 world. Not a 120-cell M1 reevaluation (E14 to E16)."}
    initial_count_diag.merge_section(sys.argv[1] if len(sys.argv) > 1 else initial_count_diag.DIAG, "m1_cost_model", payload)
    print(json.dumps({"seconds": payload["seconds"]}))


if __name__ == "__main__":
    main()
