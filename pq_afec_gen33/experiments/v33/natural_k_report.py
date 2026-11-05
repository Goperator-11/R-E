import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from experiments.v33 import initial_inspect as wire
from experiments.v33.natural_k_reference import FirstHello, packetize, width_intervals


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")


def extensions(hello):
    assert len(hello) >= 39 and hello[0] == 1
    assert len(hello) == int.from_bytes(hello[1:4], "big") + 4
    pos = 38

    def take(n):
        nonlocal pos
        assert 0 <= n <= len(hello) - pos
        data = hello[pos:pos+n]
        pos += n
        return data

    take(take(1)[0])
    take(int.from_bytes(take(2), "big"))
    take(take(1)[0])
    size = int.from_bytes(take(2), "big")
    assert pos + size == len(hello)
    found = set()
    while pos < len(hello):
        kind = int.from_bytes(take(2), "big")
        assert kind not in found
        found.add(kind)
        take(int.from_bytes(take(2), "big"))
    return sorted(found)


def decode_initial(data, key):
    parsed = list(wire.packets(data))
    assert len(parsed) == 1
    typ, start, pn_offset, end, dcid = parsed[0]
    assert typ == start == 0 and end == len(data)
    scid_at = 6 + len(dcid)
    scid_len = data[scid_at]
    scid = data[scid_at+1:scid_at+1+scid_len]
    token_len, token_start = wire.varint(data, scid_at + 1 + scid_len)
    token = data[token_start:token_start+token_len]
    _, after_length = wire.varint(data, token_start + token_len)
    assert after_length == pn_offset
    mask = Cipher(algorithms.AES(key["hp"]), modes.ECB()).encryptor().update(data[pn_offset+4:pn_offset+20])
    pn_len = ((data[0] ^ (mask[0] & 15)) & 3) + 1
    pn, plain = wire.decrypt(data, start, pn_offset, end, key)
    frames = wire.crypto_frames(plain)
    return dict(number=pn, number_bytes=pn_len, header_bytes=pn_offset+pn_len,
                dcid=dcid, scid=scid, token=token, frames=frames, plain=plain)


def replay(folder):
    results = []
    for path in sorted(folder.glob("*.stdout")):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        relay = json.loads(path.with_suffix(".relay.json").read_text(encoding="utf-8"))
        ports = list(dict.fromkeys(e["peer_port"] for e in relay if e["direction"] == "c2s"))
        assert len(rows) == len(ports) == 3
        for row, port in zip(rows, ports):
            sent = [e for e in relay if e["direction"] == "c2s" and e["peer_port"] == port and e["initial"]]
            inspection = wire.inspect(sent, row["observation"])
            first_k = row["first_flight_datagrams"]
            assert inspection["crypto_packets"] == first_k
            all_initial_datagrams = len(sent)
            sent = sent[:first_k]
            first = bytes.fromhex(sent[0]["wire_hex"])
            dcid = next(wire.packets(first))[4]
            key = wire.keys(dcid)
            decoded = [decode_initial(bytes.fromhex(e["wire_hex"]), key) for e in sent]
            assert all(d["dcid"] == dcid and d["scid"] == decoded[0]["scid"] and d["token"] == decoded[0]["token"] for d in decoded)
            assert [d["number"] for d in decoded] == list(range(len(decoded)))
            pieces = {}
            for d in decoded:
                assert len(d["frames"]) == 1
                offset, body = d["frames"][0]
                for index, value in enumerate(body, offset):
                    assert index not in pieces
                    pieces[index] = value
            assert len(pieces) == max(pieces) + 1
            hello = bytes(pieces[i] for i in range(len(pieces)))
            ext = extensions(hello)
            assert 0 not in ext and 0xfe0d not in ext
            inp = FirstHello(len(hello), len(dcid), len(decoded[0]["scid"]), len(decoded[0]["token"]), True, False, True)
            expected = packetize(inp, row["ips_eff"])
            assert len(expected) == len(decoded) == row["first_flight_datagrams"]
            observation = row["observation"]
            assert not observation["truncated"]
            packets = observation["packets"]
            received = [p["at_ns"] for p in packets if p["direction"] == "received"]
            before_response = []
            for record, raw, event in zip(expected, decoded, sent):
                offset, body = raw["frames"][0]
                assert (record.number, record.number_bytes, record.header_bytes, record.crypto_offset, record.crypto_bytes) == (raw["number"], raw["number_bytes"], raw["header_bytes"], offset, len(body))
                assert record.datagram_bytes == event["bytes"] == len(bytes.fromhex(event["wire_hex"]))
                q = [p for p in packets if p["direction"] == "sent" and p["space"] == "initial" and p["pn"] == raw["number"]]
                assert len(q) == 1 and q[0]["crypto"] == [[offset, len(body)]] and q[0]["ack_ranges"] == []
                assert not received or q[0]["at_ns"] < min(received)
                before_response.append(q[0]["at_ns"])
            results.append(dict(case=path.stem, connection=row["i"], input=asdict(inp),
                                width=row["ips_eff"], natural_k=len(expected), actual_k=len(decoded),
                                packets=[asdict(p) for p in expected], extensions=ext,
                                hello_sha256=hashlib.sha256(hello).hexdigest(),
                                all_authenticated_initial_packets=inspection["authenticated_initial_packets"],
                                all_initial_datagrams=all_initial_datagrams,
                                width_intervals=width_intervals(inp), before_response_ns=before_response))
    return results


def run(args):
    folders = [args.runs / f"T3_inflate_inflation_{mode}_v1" for mode in ("basic", "oob")]
    paths = sorted(p for folder in folders for p in folder.iterdir() if p.suffix in (".stdout",) or p.name.endswith(".relay.json"))
    plan = dict(schema="o4-natural-k-replay/1", purpose="offline authenticated packetization validation",
                inputs={str(p):sha(p) for p in paths}, script_sha256=sha(__file__),
                reference_sha256=sha(Path(__file__).with_name("natural_k_reference.py")),
                inspector_sha256=sha(wire.__file__))
    plan_path = args.out.with_suffix(".plan.json")
    if args.dry_run:
        save(plan_path, plan)
        print(json.dumps(dict(status="PLAN", files=len(paths))))
        return
    assert json.loads(plan_path.read_text(encoding="utf-8")) == plan
    args.out.mkdir(exist_ok=False)
    rows = [dict(path=folder.name, **row) for folder in folders for row in replay(folder)]
    changed = [row for row in rows if len(row["width_intervals"]) > 1]
    result = dict(status="PASS", label="development_offline", plan=plan,
                  connections=len(rows), authenticated_packets=sum(r["natural_k"] for r in rows),
                  all_authenticated_initial_packets=sum(r["all_authenticated_initial_packets"] for r in rows),
                  rows=rows, width_sensitive_connections=len(changed),
                  policy_adopted=False, live_expectation_changed=False)
    save(args.out / "result.json", result)
    print(json.dumps({k:result[k] for k in ("status", "connections", "authenticated_packets", "width_sensitive_connections")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--smoke", action="store_true")
    run(parser.parse_args())
