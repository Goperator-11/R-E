import argparse
import hashlib
import json
from pathlib import Path
import statistics


def digest(path):
    value = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def journal_rows(path):
    run_id = None
    rows = {}
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            run_id = run_id or record.get("run_id")
            if record.get("kind") != "block":
                continue
            for unit in record["data"]["units"]:
                if unit["key"] in rows:
                    raise SystemExit("duplicate unit " + unit["key"])
                rows[unit["key"]] = unit["payload"]["rows"]
    return run_id, rows


def arm_values(rows, task, cell, arm, failure_ms):
    values = []
    for key, items in rows.items():
        parts = key.split(".")
        if len(parts) != 6:
            raise SystemExit("unexpected unit key " + key)
        if (parts[0], parts[1], parts[5]) == (task, cell, arm):
            values.extend(item["ms"] if item.get("ok") else failure_ms for item in items)
    if not values:
        raise SystemExit("no rows for " + cell + " " + arm)
    return values


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--task", default="X1")
    args = parser.parse_args(argv)
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    result = json.loads(args.result.read_text(encoding="utf-8"))
    run_id, rows = journal_rows(args.journal)
    if run_id != result["run_id"]:
        raise SystemExit("journal run_id differs from result")
    failure_ms = plan["statistics"]["failure_hct_ms"]
    cells = []
    for contrast in plan["tasks"][args.task]["contrasts"]:
        x = arm_values(rows, args.task, contrast["cell"], contrast["x"], failure_ms)
        y = arm_values(rows, args.task, contrast["cell"], contrast["y"], failure_ms)
        median_x, median_y = statistics.median(x), statistics.median(y)
        cells.append({"cell": contrast["cell"], "contrast_id": contrast["id"], "x": contrast["x"], "y": contrast["y"],
                      "median_x_ms": median_x, "median_y_ms": median_y,
                      "median_diff_ms": round(median_x - median_y, 6), "n_x": len(x), "n_y": len(y)})
    document = {
        "schema": "derived_x1_medians/1",
        "label": "development",
        "analysis": "사후 기술 통계. 결과 JSON에 없는 팔 전체 HCT 중앙값이며 구간 추정은 없다.",
        "run_id": run_id,
        "task": args.task,
        "journal": args.journal.name,
        "journal_sha256": digest(args.journal),
        "plan_sha256": digest(args.plan),
        "result": "g3/v33/results/" + args.result.name,
        "result_sha256": digest(args.result),
        "rows": "저널 block 기록의 모든 클라이언트 행(워밍업 포함). 실패 행은 failure_hct_ms를 쓴다.",
        "failure_hct_ms": failure_ms,
        "cells": cells,
    }
    with open(args.out, "x", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, ensure_ascii=False, indent=1)
        stream.write("\n")
    print(json.dumps([[cell["cell"], cell["median_diff_ms"], cell["n_x"], cell["n_y"]] for cell in cells]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
