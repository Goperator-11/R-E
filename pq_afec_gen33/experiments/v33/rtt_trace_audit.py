import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


TOLERANCE_NS = 1_000_000
DIRECTORIES = ("T2_observation_basic_v1", "T2_observation_oob_v1",
               "T2_revisit_basic_v1", "T2_revisit_oob_v1",
               "T2_revisit_negative_basic_v2", "T2_revisit_negative_oob_v1")


def _integer(name, value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(name + " must be a bounded integer")
    return value


def _space(value):
    return "1RTT" if value == "0RTT" else value


def audit_row(row):
    if not isinstance(row, dict) or not isinstance(row.get("observation"), dict):
        raise ValueError("row requires observation")
    obs = row["observation"]
    if type(obs.get("version")) is not int or obs["version"] != 1:
        raise ValueError("unsupported observation version")
    if type(obs.get("truncated")) is not bool:
        raise ValueError("trace truncation status missing")
    end = _integer("handshake_end_ns", row["handshake_end_ns"])
    packets = obs["packets"]
    updates = obs["rtt_updates"]
    if not isinstance(packets, list) or not isinstance(updates, list):
        raise ValueError("packet and metric lists required")
    sent = defaultdict(list)
    crc_counts = Counter()
    previous = -1
    for i, p in enumerate(packets):
        at = _integer("packet at_ns", p["at_ns"])
        _integer("packet number", p["pn"])
        _integer("packet bytes", p["bytes"])
        _integer("packet checksum", p["crc32c"])
        if not isinstance(p["space"], str) or p["direction"] not in ("sent", "received"):
            raise ValueError("invalid packet direction or space")
        if at < previous:
            raise ValueError("packet callback time went backwards")
        previous = at
        if not isinstance(p["ack_ranges"], list):
            raise ValueError("ACK ranges must be list")
        for pair in p["ack_ranges"]:
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError("invalid ACK range")
            if _integer("ACK low", pair[0]) > _integer("ACK high", pair[1]):
                raise ValueError("reversed ACK range")
        if p["direction"] == "sent":
            sent[(_space(p["space"]), p["pn"])].append((i, p))
            crc_counts[p["crc32c"]] += 1
    acknowledgments = []
    retries = []
    for i, p in enumerate(packets):
        if p["direction"] != "received":
            continue
        if p["space"] == "retry":
            retries.append(p["at_ns"])
        if not p["ack_ranges"]:
            continue
        largest = max(pair[1] for pair in p["ack_ranges"])
        matches = [(j, q) for j, q in sent[(_space(p["space"]), largest)] if q["at_ns"] <= p["at_ns"]]
        record = dict(received_index=i, received_at_ns=p["at_ns"], space=_space(p["space"]),
                      largest_acked=largest, sent_candidates=len(matches))
        if len(matches) == 1:
            j, q = matches[0]
            record.update(sent_index=j, sent_at_ns=q["at_ns"], callback_delta_ns=p["at_ns"]-q["at_ns"],
                          packet_bytes=q["bytes"], crc32c=q["crc32c"],
                          same_crc_sent_records=crc_counts[q["crc32c"]] if q["crc32c"] else None)
        acknowledgments.append(record)
    results = []
    previous = -1
    for i, metric in enumerate(updates):
        at = _integer("RTT at_ns", metric["at_ns"])
        latest = _integer("latest_ns", metric["latest_ns"], 1)
        _integer("min_ns", metric["min_ns"], 1)
        if at < previous:
            raise ValueError("RTT callback time went backwards")
        previous = at
        candidates = []
        for ack in acknowledgments:
            if ack["sent_candidates"] != 1:
                continue
            event_gap = ack["received_at_ns"] - at
            value_gap = ack["callback_delta_ns"] - latest
            if abs(event_gap) <= TOLERANCE_NS and abs(value_gap) <= TOLERANCE_NS:
                candidates.append(dict(ack, callback_event_gap_ns=event_gap, rtt_value_gap_ns=value_gap))
        results.append(dict(index=i, at_ns=at, latest_ns=latest, min_ns=metric["min_ns"],
                            after_handshake=at > end, candidates=candidates,
                            near_retry=any(abs(at-t) <= TOLERANCE_NS for t in retries),
                            eligible_for_correction=False))
    return dict(trace_version=1, truncated=obs["truncated"],
                metric_updates=results, acknowledgments=acknowledgments,
                sent_1rtt=sum(p["direction"] == "sent" and p["space"] == "1RTT" for p in packets),
                received_1rtt_ack=sum(a["space"] == "1RTT" for a in acknowledgments),
                retry_packets=len(retries), eligible_samples=0,
                missing_evidence=["transport_send_timestamp", "metric_ack_owner", "applied_ack_delay",
                                  "udp_datagram_send_timestamp_and_bytes", "queued_bytes_at_send"])


def counts(rows):
    result = Counter(connections=len(rows))
    for row in rows:
        audit = row["audit"]
        result["path_rtt_valid"] += bool(row["path_rtt_valid"])
        result["truncated_connections"] += audit["truncated"]
        result["connections_with_1rtt_ack"] += audit["received_1rtt_ack"] > 0
        result["connections_with_retry"] += audit["retry_packets"] > 0
        result["eligible_samples"] += audit["eligible_samples"]
        for update in audit["metric_updates"]:
            n = len(update["candidates"])
            result["metric_updates"] += 1
            result["after_handshake_updates"] += update["after_handshake"]
            result["unique_numeric_candidate"] += n == 1
            result["multiple_numeric_candidates"] += n > 1
            result["no_numeric_candidate"] += n == 0
            result["near_retry_updates"] += update["near_retry"]
            if n == 1:
                candidate = update["candidates"][0]
                result["unique_1rtt_candidate"] += candidate["space"] == "1RTT"
                result["metric_before_received_callback"] += candidate["callback_event_gap_ns"] > 0
    return dict(result)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    args.out.mkdir(exist_ok=False)
    files, rows = [], []
    for directory in DIRECTORIES:
        for path in sorted((args.runs / directory).glob("*.stdout")):
            files.append(dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
            for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
                if not line.strip():
                    continue
                raw = json.loads(line)
                rows.append(dict(source=str(path), source_line=index+1, case=path.stem, directory=directory,
                                 i=raw["i"], path_rtt_valid=raw["path_rtt_valid"],
                                 path_rtt_ms=raw["path_rtt_ms"], audit=audit_row(raw)))
    assert len(files) == 66
    output = args.out / "connections.jsonl"
    with output.open("x", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, separators=(",", ":"), allow_nan=False)+"\n")
    result = dict(scope="existing development functional trace audit; no corrected policy samples",
                  files=files, file_count=len(files), totals=counts(rows),
                  directories={d:counts([r for r in rows if r["directory"] == d]) for d in DIRECTORIES},
                  tolerance_ns=TOLERANCE_NS, source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  connections_sha256=hashlib.sha256(output.read_bytes()).hexdigest())
    (args.out / "result.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8", newline="\n")
    print(json.dumps(result["totals"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
