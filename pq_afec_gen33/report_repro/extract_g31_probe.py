import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import REPORT_ROOT, source_path, source_reference


CELL_FIELDS = (
    "cell", "group_id", "probe_cell", "h_cell", "cert", "rtt_ms", "rate_mbit",
    "loss_pct", "blocks_planned", "blocks_done", "server_cert_der",
)
ARM_FIELDS = (
    "label", "action_delta_lead_trail", "binary", "flags", "n_requested",
    "n_returned", "ok", "failed", "timeouts", "missing", "server/conns",
    "server/conns_with_tx", "server/timeline_truncated", "server/first_tx_size_hist",
)
WITNESS_FIELDS = (
    "block", "index", "row/ok", "row/group", "row/first_flight_datagrams",
    "row/first_flight_bytes", "row/ips_used", "row/ips_eff", "server/tx_dgrams",
    "server/tx_sizes/0", "derived/server/first_tx_size",
    "derived/server/timeline_truncated",
)


def pointer_value(value, pointer):
    if not pointer:
        return value
    if not pointer.startswith("/"):
        raise ValueError("JSON pointer must start with '/'")
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def selected_fields(document, base, fields):
    return {base + "/" + field: pointer_value(document, base + "/" + field) for field in fields}


def build_excerpt():
    original = source_path("g31_probe")
    payload = original.read_bytes()
    document = json.loads(payload)
    metadata = selected_fields(document, "", (
        "schema", "label", "status", "confirmatory", "mode", "generated_at",
        "plan/group", "plan/loss_direction", "notes/0", "notes/3",
    ))
    rows = []
    for index, cell in enumerate(document["cells"]):
        if cell["rate_mbit"] <= 0:
            continue
        cell_base = "/cells/" + str(index)
        arms = []
        for arm_name, arm in cell["arms"].items():
            if arm["server"]["first_tx_size_hist"].get("41", 0) <= 0:
                raise ValueError("Selected rate-limited arm has no 41 B first datagram: " + arm_name)
            escaped_arm = arm_name.replace("~", "~0").replace("/", "~1")
            arm_base = cell_base + "/arms/" + escaped_arm
            witnesses = arm["per_connection"]["joined"]
            witness_index = next(
                i for i, row in enumerate(witnesses)
                if row["server"]["tx_sizes"] and row["server"]["tx_sizes"][0] == 41
            )
            witness_base = arm_base + "/per_connection/joined/" + str(witness_index)
            if pointer_value(document, witness_base + "/derived/server/first_tx_size") != 41:
                raise ValueError("First datagram summary disagrees with direct tx_sizes")
            arms.append({
                "source_pointer": arm_base,
                "fields": selected_fields(document, arm_base, ARM_FIELDS),
                "witness": {
                    "source_pointer": witness_base,
                    "fields": selected_fields(document, witness_base, WITNESS_FIELDS),
                },
            })
        rows.append({
            "source_pointer": cell_base,
            "fields": selected_fields(document, cell_base, CELL_FIELDS),
            "arms": arms,
        })
    if not rows:
        raise ValueError("No rate-limited probe cells")
    return {
        "schema": "padfec.report.g31_probe_excerpt/1",
        "source": {
            "alias": "g31_probe",
            "path": source_reference("g31_probe"),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
        },
        "report_location": "Ⅳ-5",
        "selection": "rate_mbit > 0인 모든 셀의 first_tx_size_hist 전체와 각 arm에서 tx_sizes[0] == 41인 첫 연결의 지정 필드",
        "limitations": [
            "first_tx_size_hist는 41 B 외의 관측값도 그대로 보존한다. 41 B를 모든 연결의 고정값으로 해석하지 않는다.",
            "각 witness는 41 B 관측의 직접 근거이며 전체 연결 표본을 대신하지 않는다.",
            "송신 크기는 qamp wrapper 기록이다. datagram이 ACK 전용이라는 해석과 모든 실패 셀의 원인 설명은 이 발췌로 확인하지 않는다.",
            "fixed arm의 development probe이며 v3 또는 v3.1 정책의 평가 자료가 아니다.",
        ],
        "source_fields": metadata,
        "cells": rows,
    }


def encode_excerpt(excerpt):
    return (json.dumps(excerpt, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--output", type=Path, default=REPORT_ROOT / "g31_probe_excerpt.json")
    args = parser.parse_args()
    try:
        expected = build_excerpt()
        if args.write:
            args.output.write_bytes(encode_excerpt(expected))
        else:
            actual = json.loads(args.output.read_text(encoding="utf-8"))
            if actual != expected:
                raise ValueError("Excerpt differs from source SHA, selected pointers, or values")
        arms = [arm for cell in expected["cells"] for arm in cell["arms"]]
        histograms = [arm["fields"][arm["source_pointer"] + "/server/first_tx_size_hist"] for arm in arms]
        print(json.dumps({
            "result": "pass", "mode": "write" if args.write else "check",
            "source_sha256": expected["source"]["sha256"],
            "cells": len(expected["cells"]), "arms": len(arms), "witnesses": len(arms),
            "first_tx_41_count": sum(hist.get("41", 0) for hist in histograms),
            "first_tx_other_count": sum(sum(count for size, count in hist.items() if size != "41") for hist in histograms),
            "excerpt_bytes": args.output.stat().st_size,
        }, ensure_ascii=False))
        return 0
    except (OSError, KeyError, ValueError, StopIteration) as exc:
        print("g31 probe excerpt check failed: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
