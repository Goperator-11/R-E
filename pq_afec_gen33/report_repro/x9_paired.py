import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path

ONE_RTT_CUTOFF_RTTS = 1.5


def digest(path):
    value = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def continued_fraction(a, b, x):
    tiny = 1e-300
    c = 1.0
    d = 1.0 - (a + b) * x / (a + 1.0)
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 1000):
        step = 2 * m
        for numerator in (m * (b - m) * x / ((a - 1.0 + step) * (a + step)),
                          -(a + m) * (a + b + m) * x / ((a + step) * (a + 1.0 + step))):
            d = 1.0 + numerator * d
            d = 1.0 / (d if abs(d) > tiny else tiny)
            c = 1.0 + numerator / c
            c = c if abs(c) > tiny else tiny
            h *= d * c
        if abs(d * c - 1.0) < 1e-15:
            return h
    raise ArithmeticError("incomplete beta did not converge")


def incomplete_beta(a, b, x):
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * continued_fraction(a, b, x) / a
    return 1.0 - front * continued_fraction(b, a, 1.0 - x) / b


def t_quantile(probability, df):
    low, high = 0.0, 1000.0
    for _ in range(200):
        middle = (low + high) / 2
        if 1.0 - 0.5 * incomplete_beta(df / 2.0, 0.5, df / (df + middle * middle)) < probability:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def interval(values):
    n = len(values)
    mean = sum(values) / n
    if n < 2:
        return {"n": n, "mean": mean, "ci95": None, "df": None, "halfwidth": None}
    sd = math.sqrt(sum((value - mean) ** 2 for value in values) / (n - 1))
    half = t_quantile(0.975, n - 1) * sd / math.sqrt(n)
    return {"n": n, "mean": mean, "ci95": [mean - half, mean + half], "df": n - 1, "halfwidth": half}


def is_int(value):
    return type(value) is int


def unit_metrics(payload, warmup, failure_ms, cutoff_ms):
    rows = [(index, row) for index, row in enumerate(payload["rows"]) if row["i"] >= warmup]
    server = payload["collection"]["server"]
    conns = {conn["key"]: conn for conn in server.get("conns") or []}
    matches = {item["row_index"]: item["conn_key"] for item in server["scid_matching"]["matches"]}
    received = []
    for index, _ in rows:
        value = conns.get(matches.get(index), {}).get("rx_bytes")
        received.append(value if is_int(value) and value >= 0 else None)
    pto = [row["observation"]["pto_count"] for _, row in rows
           if isinstance(row.get("observation"), dict) and is_int(row["observation"].get("pto_count"))]
    extra = [row["initial_datagrams"] > row["first_flight_datagrams"] + 1 for _, row in rows
             if is_int(row.get("initial_datagrams")) and is_int(row.get("first_flight_datagrams"))]
    return {
        "n": len(rows),
        "hct_ms": sum(row["ms"] if row.get("ok") else failure_ms for _, row in rows) / len(rows),
        "one_rtt_rate": sum(bool(row.get("ok")) and row["ms"] < cutoff_ms for _, row in rows) / len(rows),
        "server_bytes_in_per_conn": None if None in received else sum(received) / len(received),
        "pto_rate": sum(value >= 1 for value in pto) / len(pto) if pto else None,
        "extra_initial_rate": sum(extra) / len(extra) if extra else None,
    }


def read_blocks(path, task, plan):
    cells = {cell["id"]: cell for cell in plan["tasks"][task]["cells"]}
    failure_ms = plan["statistics"]["failure_hct_ms"]
    run_id = None
    blocks = defaultdict(dict)
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            run_id = run_id or record.get("run_id")
            if record.get("kind") != "block":
                continue
            for unit in record["data"]["units"]:
                name, cell_id, trajectory, phase, block, arm = unit["key"].split(".")
                if name != task:
                    raise SystemExit("unexpected task " + unit["key"])
                cell = cells[cell_id]
                profile = plan["profiles"][cell["profile"]]
                if profile.get("netem_uplink_mbps"):
                    raise SystemExit("uplink serialization term is not implemented")
                cutoff = ONE_RTT_CUTOFF_RTTS * profile["rtt_ms"]
                key = (cell_id, trajectory, phase, block)
                if arm in blocks[key]:
                    raise SystemExit("duplicate unit " + unit["key"])
                blocks[key][arm] = unit_metrics(unit["payload"], cell["warmup_per_arm_block"], failure_ms, cutoff)
    return run_id, blocks


def paired(blocks, cell_id, x, y, metric):
    keys = sorted(key for key, arms in blocks.items() if key[0] == cell_id and x in arms and y in arms)
    values = [blocks[key][x][metric] - blocks[key][y][metric] for key in keys
              if blocks[key][x][metric] is not None and blocks[key][y][metric] is not None]
    result = interval(values)
    result["missing_pairs"] = len(keys) - len(values)
    return result


def arm_mean(blocks, cell_id, arm, metric):
    values = [arms[arm][metric] for key, arms in blocks.items() if key[0] == cell_id and arm in arms]
    return sum(values) / len(values)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--task", default="X9")
    parser.add_argument("--x", default="mlkem_off")
    parser.add_argument("--y", default="x25519_off")
    args = parser.parse_args(argv)
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    result = json.loads(args.result.read_text(encoding="utf-8"))
    run_id, blocks = read_blocks(args.journal, args.task, plan)
    if run_id != result["run_id"]:
        raise SystemExit("journal run_id differs from result")
    stored = {cell["cell"]: cell["pto_contrast"] for cell in result["statistics"]["cells"]}
    cells = []
    for cell in plan["tasks"][args.task]["cells"]:
        cell_id = cell["id"]
        contrasts = {metric: paired(blocks, cell_id, args.x, args.y, metric)
                     for metric in ("hct_ms", "one_rtt_rate", "server_bytes_in_per_conn", "extra_initial_rate", "pto_rate")}
        check = {}
        for metric, name in (("pto_rate", "primary"), ("extra_initial_rate", "auxiliary")):
            mine, theirs = contrasts[metric], stored[cell_id][name]
            check[name] = {"mean_abs_diff": abs(mine["mean"] - theirs["mean"]),
                           "ci95_abs_diff": max(abs(a - b) for a, b in zip(mine["ci95"], theirs["ci95"])),
                           "n_blocks": [mine["n"], theirs["n_blocks"]]}
        cells.append({
            "cell": cell_id, "x": args.x, "y": args.y,
            "arm_means": {arm: {metric: arm_mean(blocks, cell_id, arm, metric)
                                for metric in ("hct_ms", "one_rtt_rate", "server_bytes_in_per_conn")}
                          for arm in (args.x, args.y)},
            "contrasts": {metric: contrasts[metric] for metric in ("hct_ms", "one_rtt_rate", "server_bytes_in_per_conn", "extra_initial_rate")},
            "check_against_result": check,
        })
    document = {
        "schema": "x9_paired/1",
        "label": "development",
        "analysis": "사후 짝 대조(탐색). 계획 primary(PTO)가 아니며 결과를 본 뒤 계산했다.",
        "run_id": run_id,
        "task": args.task,
        "effect_sign": args.x + " - " + args.y,
        "journal": args.journal.name,
        "journal_sha256": digest(args.journal),
        "plan_sha256": digest(args.plan),
        "result": "g3/v33/results/" + args.result.name,
        "result_sha256": digest(args.result),
        "inference": "block 평균의 짝 차이, Student t 95% 구간",
        "rules": {
            "warmup": "block마다 i < warmup_per_arm_block 행 제외",
            "hct_ms": "측정 행 평균, 실패 행은 failure_hct_ms",
            "one_rtt_rate": "ok이고 ms < 1.5 × RTT인 측정 행 비율. netem uplink 0이라 직렬화 항은 0",
            "server_bytes_in_per_conn": "측정 행의 SCID 대응 conn_log rx_bytes 합 / 측정 행 수",
            "extra_initial_rate": "initial_datagrams > first_flight_datagrams + 1 비율(계획 auxiliary)",
        },
        "failure_hct_ms": plan["statistics"]["failure_hct_ms"],
        "cells": cells,
    }
    with open(args.out, "x", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, ensure_ascii=False, indent=1)
        stream.write("\n")
    for cell in cells:
        print(cell["cell"], json.dumps({metric: [round(value["mean"], 6), [round(v, 6) for v in value["ci95"]], value["n"]]
                                        for metric, value in cell["contrasts"].items()}),
              json.dumps(cell["check_against_result"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
