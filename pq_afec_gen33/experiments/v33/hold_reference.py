import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import time

from experiments.v33.hold_decoder import FlightSpec, HoldConfig, HoldDecoder


def configurations():
    for k in range(1, 5):
        for m in range(5):
            for lead in range(m + 1):
                yield k, m, lead


def case_orders(n):
    for count in range(n + 1):
        yield from itertools.permutations(range(n), count)


def run_case(k, m, lead, order):
    spec = FlightSpec(tuple(1200 + i * 17 for i in range(k)), m, lead, 1331, 1331 - 34 - 6*k)
    decoder = HoldDecoder(spec, HoldConfig())
    for position, symbol in enumerate(order):
        decoder.receive_and_drain("o" if symbol < k else "p", symbol if symbol < k else symbol - k, (position + 1) * 1000)
    if decoder.created_ns is not None and decoder.terminal is None:
        decoder.advance(max(decoder.now_ns, decoder.deadline_ns))
        decoder.drain()
    result = decoder.result()
    if result["complete"] != (len(order) >= k):
        raise AssertionError((k, m, lead, order, result))
    if len(set(result["recovered"])) != len(result["recovered"]):
        raise AssertionError("recovery repeated")
    used = set(result["used"])
    if any(p.kind == "p" and p.index in used for p in decoder.delivered):
        raise AssertionError("consumed parity returned")
    if result["complete"] and result["held_bytes"]:
        raise AssertionError("completed flight retains bytes")
    return decoder


def canonical_case(k, m, lead, order, decoder):
    r = decoder.result()
    header = [str(k), str(m), str(lead), ",".join(map(str, order)), str(int(r["complete"]))]
    header.extend(str(r[name]) for name in ("bytes_in", "bytes_to_stack", "pending_bytes", "held_bytes", "discard_bytes", "consumed_overhead"))
    header.extend((r["terminal"] or "", r["open_reason"] or "", ",".join(map(str, r["used"])), ",".join(map(str, r["recovered"]))))
    header.append(";".join(":".join(map(str, (p.kind, p.index, p.size, int(p.recovered), p.at_ns))) for p in decoder.delivered))
    header.append(";".join(":".join(str(e[name]) for name in ("event", "at_ns", "bytes_in", "bytes_to_stack", "pending_bytes", "held_bytes", "discard_bytes", "consumed_overhead")) for e in decoder.events))
    return ("|".join(header) + "\n").encode("ascii")


def generate(output):
    if output.exists():
        raise FileExistsError(output)
    started = time.monotonic()
    groups = []
    all_cases = hashlib.sha256()
    sources = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__), Path(__file__).with_name("hold_decoder.py"))}
    for k, m, lead in configurations():
        digest, ids = hashlib.sha256(), hashlib.sha256()
        counts = [0] * (k + m + 1)
        success = recovered = events = 0
        for order in case_orders(k + m):
            decoder = run_case(k, m, lead, order)
            row = canonical_case(k, m, lead, order, decoder)
            digest.update(row)
            all_cases.update(row)
            ids.update((",".join(map(str, order)) + "\n").encode("ascii"))
            counts[len(order)] += 1
            success += int(decoder.result()["complete"])
            recovered += len(decoder.recovered)
            events += len(decoder.events)
        expected = [math.factorial(k + m) // math.factorial(k + m - n) for n in range(k + m + 1)]
        assert counts == expected
        assert success == sum(expected[k:])
        group = {"k": k, "m": m, "lead": lead, "cases": sum(counts), "by_arrived_count": counts,
                 "complete": success, "recovered_originals": recovered, "checked_transitions": events,
                 "case_ids_sha256": ids.hexdigest(), "output_sha256": digest.hexdigest()}
        groups.append(group)
        print(json.dumps(group), flush=True)
    assert len(groups) == 60 and sum(g["cases"] for g in groups) == 700116
    assert sources == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in map(Path, sources)}
    report = {"schema": "m1-python-event-reference-v1", "kind": "deterministic_model", "wire_checked": False,
              "sources_sha256": sources, "config": HoldConfig().__dict__, "groups": groups,
              "cases": sum(g["cases"] for g in groups), "checked_transitions": sum(g["checked_transitions"] for g in groups),
              "output_sha256": all_cases.hexdigest(), "elapsed_seconds": time.monotonic() - started}
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("groups", "sources_sha256", "config")}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(args.output)


if __name__ == "__main__":
    main()
