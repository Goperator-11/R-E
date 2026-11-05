import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from experiments.v33 import initial_inspect as wire
from experiments.v33.natural_k_reference import FirstHello, packetize
from experiments.v33.natural_k_report import decode_initial, extensions, save, sha


def first_hello(events, observation, width):
    assert not observation["truncated"]
    packets = observation["packets"]
    received = [p["at_ns"] for p in packets if p["direction"] == "received"]
    assert received
    first_receive = min(received)
    originals = [e for e in events if e["direction"] == "c2s" and e["initial"] and not e["parity"]]
    assert originals
    dcid = next(wire.packets(bytes.fromhex(originals[0]["wire_hex"])))[4]
    key = wire.keys(dcid)
    hello = bytearray()
    records = []
    expected_length = None
    owner = None
    for event in originals[:64]:
        raw = decode_initial(bytes.fromhex(event["wire_hex"]), key)
        assert len(raw["frames"]) == 1
        offset, body = raw["frames"][0]
        assert raw["number"] == len(records) and offset == len(hello)
        identity = (raw["dcid"], raw["scid"], raw["token"])
        if owner is None:
            owner = identity
        assert identity == owner
        q = [p for p in packets if p["direction"] == "sent" and p["space"] == "initial" and p["pn"] == raw["number"]]
        assert len(q) == 1 and q[0]["at_ns"] < first_receive
        assert q[0]["crypto"] == [[offset, len(body)]] and q[0]["ack_ranges"] == []
        assert q[0]["crc32c"] == event["crc32c"] and event["bytes"] == width
        hello.extend(body)
        if expected_length is None:
            assert len(hello) >= 4 and hello[0] == 1
            expected_length = 4 + int.from_bytes(hello[1:4], "big")
            assert 4 <= expected_length <= 65536
        assert len(hello) <= expected_length
        records.append(dict(number=raw["number"], number_bytes=raw["number_bytes"],
                            header_bytes=raw["header_bytes"], crypto_offset=offset, crypto_bytes=len(body),
                            datagram_bytes=event["bytes"], crc32c=event["crc32c"], sent_callback_ns=q[0]["at_ns"]))
        if len(hello) == expected_length:
            break
    assert expected_length == len(hello)
    ext = extensions(hello)
    assert 0 not in ext and 0xfe0d not in ext
    h = FirstHello(len(hello), len(owner[0]), len(owner[1]), len(owner[2]), True, False, True)
    expected = packetize(h, width)
    assert len(expected) == len(records)
    for packet, raw in zip(expected, records):
        for field in ("number", "number_bytes", "header_bytes", "crypto_offset", "crypto_bytes", "datagram_bytes"):
            assert getattr(packet, field) == raw[field]
    later_before = [p for p in packets if p["direction"] == "sent" and p["space"] == "initial" and p["at_ns"] < first_receive and p["pn"] >= len(records)]
    return dict(input=asdict(h), width=width, natural_k=len(records), raw_packets=records,
                reference_packets=[asdict(p) for p in expected], first_receive_ns=first_receive,
                later_initial_before_response=len(later_before), extensions=ext,
                hello_sha256=hashlib.sha256(hello).hexdigest())


def run(args):
    folders = [args.runs / f"T2_revisit_{mode}_v1" for mode in ("basic", "oob")]
    inputs = sorted(p for folder in folders for p in folder.iterdir() if p.suffix == ".stdout" or p.name.endswith(".relay.json"))
    sources = [Path(__file__), Path(wire.__file__), Path(__file__).with_name("natural_k_reference.py"), Path(__file__).with_name("natural_k_report.py")]
    plan = dict(schema="o4-token-replay/1", label="development_offline", input_sha256={str(p):sha(p) for p in inputs}, source_sha256={str(p):sha(p) for p in sources})
    if args.dry_run:
        save(args.out.with_suffix(".plan.json"), plan)
        print(json.dumps(dict(status="PLAN", files=len(inputs))))
        return
    assert json.loads(args.out.with_suffix(".plan.json").read_text(encoding="utf-8")) == plan
    args.out.mkdir(exist_ok=False)
    results = []
    for folder in folders:
        for path in sorted(folder.glob("*.stdout")):
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            relay = json.loads(path.with_suffix(".relay.json").read_text(encoding="utf-8"))
            ports = list(dict.fromkeys(e["peer_port"] for e in relay if e["direction"] == "c2s"))
            assert len(rows) == len(ports) == 3
            for row, port in zip(rows, ports):
                events = [e for e in relay if e["peer_port"] == port]
                got = first_hello(events, row["observation"], row["ips_eff"])
                assert got["natural_k"] == row["first_flight_datagrams"]
                assert bool(got["input"]["token_bytes"]) == bool(row["revisit"]["token"]["hits"])
                results.append(dict(path=folder.name, case=path.stem, connection=row["i"],
                                    token_hit=bool(row["revisit"]["token"]["hits"]),
                                    tls_resumed=row["revisit"]["tls_did_resume"], retry_received=row["revisit"]["retry_received"], **got))
    result = dict(status="PASS", plan=plan, rows=results, connections=len(results),
                  packets=sum(r["natural_k"] for r in results), token_connections=sum(r["token_hit"] for r in results),
                  resumed_connections=sum(r["tls_resumed"] for r in results),
                  retry_connections=sum(bool(r["retry_received"]) for r in results),
                  excluded_later_initial_before_response=sum(r["later_initial_before_response"] for r in results),
                  unsupported_connections=0, policy_adopted=False)
    save(args.out / "result.json", result)
    print(json.dumps({k:v for k,v in result.items() if k not in ("rows", "plan")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--smoke", action="store_true")
    run(parser.parse_args())
