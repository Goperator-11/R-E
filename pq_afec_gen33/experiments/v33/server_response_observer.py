import math


def make_world_server_response(observation):
    if observation.get("model_kind") != "independent_event_world":
        raise ValueError("server response requires an independent event trace")
    rows = observation.get("trace")
    if not isinstance(rows, list) or type(observation.get("ok")) is not bool:
        raise ValueError("server response requires a trace and completion outcome")
    packets, compact = {}, []
    total = duplicates = other = post = 0
    completed = False
    previous = -1.0
    completion_ms = None
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid trace row")
        if row.get("event") not in ("client_receive", "handshake_complete"):
            continue
        time = row.get("time_ms")
        if isinstance(time, bool) or not isinstance(time, (int, float)) or not math.isfinite(time) or time < 0 or time < previous:
            raise ValueError("receive events must have ordered finite times")
        previous = time
        if row["event"] == "handshake_complete":
            if completed:
                raise ValueError("duplicate completion event")
            completed, completion_ms = True, time
            compact.append([time, "complete", None, None])
            continue
        size, kind, index = row.get("size"), row.get("kind"), row.get("index")
        if type(size) is not int or size <= 0 or kind not in ("data", "ack", "retry"):
            raise ValueError("invalid received datagram")
        if kind == "data" and (type(index) is not int or index < 0):
            raise ValueError("data needs an integer response index")
        compact.append([time, kind, size, index if kind == "data" else None])
        total += size
        if completed:
            post += size
        elif kind != "data":
            other += size
        elif index in packets:
            if packets[index] != size:
                raise ValueError("response index changed size")
            duplicates += size
        else:
            packets[index] = size
    if completed != observation["ok"] or total != observation.get("srv_bytes"):
        raise ValueError("completion or received-byte total disagrees with trace")
    if completed and (not packets or sorted(packets) != list(range(len(packets)))):
        raise ValueError("complete response has missing indices")
    if completed and completion_ms != observation.get("hct"):
        raise ValueError("completion time disagrees with HCT")
    return {"evidence": {"source": "world_receive_index_proxy", "complete": completed,
                         "packets": [[index, packets[index]] for index in sorted(packets)],
                         "received_server_bytes": total, "duplicate_data_bytes": duplicates,
                         "other_received_bytes": other, "post_complete_bytes": post},
            "received": compact,
            "diagnostics": {"completion_ms": completion_ms, "unreceived_server_bytes_used": False,
                            "actual_quic_response_identity_validated": False}}
