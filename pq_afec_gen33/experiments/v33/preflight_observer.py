import math


def make_world_preflight(observation):
    if observation.get("model_kind") != "independent_event_world":
        raise ValueError("preflight observation requires the independent event trace")
    rows = observation.get("trace")
    if not isinstance(rows, list):
        raise ValueError("client arrival trace is required")
    sizes = []
    first_large = None
    total_received = 0
    previous_time = -1.0
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid trace row")
        if row.get("event") != "client_receive":
            continue
        time = row.get("time_ms")
        if isinstance(time, bool) or not isinstance(time, (int, float)) or not math.isfinite(time) or time < 0 or time < previous_time:
            raise ValueError("client arrivals must have ordered finite times")
        previous_time = time
        size = row.get("size")
        if type(size) is not int or size <= 0:
            raise ValueError("received datagram size must be a positive integer")
        total_received += size
        if first_large is None:
            if size >= 1200:
                first_large = time
            elif row.get("kind") == "ack":
                sizes.append(size)
    if total_received != observation.get("srv_bytes"):
        raise ValueError("arrival trace does not account for received server bytes")
    if len(sizes) > 64:
        raise ValueError("preflight observation exceeds the declared list limit")
    evidence = {"source": "world_arrival_proxy", "small_initial_sizes": sizes,
                "first_large_seen": first_large is not None,
                "srv_bytes_scope": "includes_observed_preflight"}
    return {"evidence": evidence,
            "diagnostics": {"first_large_ms": first_large, "observed_preflight_bytes": sum(sizes),
                            "received_server_bytes": total_received,
                            "response_received_bytes": total_received - sum(sizes),
                            "unreceived_server_bytes_used": False,
                            "actual_quic_initial_classifier_validated": False}}
