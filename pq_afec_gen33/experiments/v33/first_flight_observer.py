import hashlib
import math
import random


MODES = ("none", "c1", "ideal")
EVIDENCE_FIELDS = frozenset(("src", "sent", "lost", "bitmap", "trunc"))


def _number(name, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return float(value)


def _integer(name, value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _none(sent=0, trunc=False):
    return {"src": "none", "sent": sent, "lost": 0, "bitmap": None, "trunc": trunc}


def observe_first_flight(sender, receiver, feedback, *, mode, deadline_ms,
                         closed_at_ms, receiver_max_datagram_bytes=1452):
    if mode not in MODES:
        raise ValueError("unknown observation mode")
    deadline = _number("deadline_ms", deadline_ms)
    closed_at = _number("closed_at_ms", closed_at_ms)
    capacity = _integer("receiver_max_datagram_bytes", receiver_max_datagram_bytes, 1)
    if not isinstance(sender, list) or not isinstance(receiver, list):
        raise ValueError("sender and receiver must be lists")
    identities = []
    sender_sizes = {}
    sender_times = {}
    for packet in sender:
        if not isinstance(packet, dict) or set(packet) != {"id", "size", "sent_ms"}:
            raise ValueError("invalid sender manifest packet")
        identity = packet["id"]
        if not isinstance(identity, str) or not identity or identity in sender_sizes:
            raise ValueError("sender identities must be nonempty and unique")
        sender_sizes[identity] = _integer("sender size", packet["size"], 1)
        sender_times[identity] = _number("sender sent_ms", packet["sent_ms"])
        if sender_times[identity] > closed_at:
            raise ValueError("first-flight closure precedes a send")
        identities.append(identity)
    if len(identities) > 8:
        raise ValueError("first-flight manifest exceeds the supported eight datagrams")
    records = []
    for packet in receiver:
        if not isinstance(packet, dict) or set(packet) != {"id", "read_size", "wire_size", "time_ms"}:
            raise ValueError("invalid receiver record")
        if not isinstance(packet["id"], str) or not packet["id"]:
            raise ValueError("invalid receiver identity")
        read_size = _integer("receiver read_size", packet["read_size"], 1)
        wire_size = _integer("receiver wire_size", packet["wire_size"], 1)
        if read_size > wire_size or read_size > capacity:
            raise ValueError("receiver sizes exceed the datagram or capacity")
        if packet["id"] in sender_sizes and sender_sizes[packet["id"]] != wire_size:
            raise ValueError("receiver wire size differs from the sender manifest")
        received_at = _number("receiver time_ms", packet["time_ms"])
        if packet["id"] in sender_times and received_at < sender_times[packet["id"]]:
            raise ValueError("receiver time precedes sender completion")
        records.append({**packet, "time_ms": received_at})
    diagnostics = {"mode": mode, "sent": len(identities), "deadline_ms": deadline,
                   "closed_at_ms": closed_at, "feedback_generated": feedback is not None,
                   "feedback_received": False, "freeze_time_ms": None,
                   "feedback_received_ms": None, "crc_list_truncated": False,
                   "receiver_datagram_truncated": any(size > capacity for size in sender_sizes.values()),
                   "matched": 0, "unmatched": 0, "duplicates": 0,
                   "all_lost": False, "all_lost_basis": None,
                   "usable": False, "reason": "disabled"}
    if mode == "none":
        return {"evidence": _none(), "diagnostics": diagnostics}
    if not identities:
        diagnostics["reason"] = "empty_manifest"
        return {"evidence": _none(), "diagnostics": diagnostics}
    if mode == "ideal":
        freeze = deadline
        snapshot = [packet["id"] for packet in records if packet["time_ms"] <= freeze]
        diagnostics["freeze_time_ms"] = freeze
    else:
        if feedback is None:
            diagnostics["reason"] = "feedback_missing"
            return {"evidence": _none(len(identities)), "diagnostics": diagnostics}
        if not isinstance(feedback, dict) or set(feedback) != {"freeze_ms", "received_ms", "identities", "truncated"}:
            raise ValueError("invalid feedback delivery")
        freeze = _number("feedback freeze_ms", feedback["freeze_ms"])
        delivered = feedback["received_ms"]
        if delivered is not None:
            delivered = _number("feedback received_ms", delivered)
            if delivered < freeze:
                raise ValueError("feedback delivery precedes snapshot")
        if type(feedback["truncated"]) is not bool:
            raise ValueError("feedback truncated must be boolean")
        snapshot = feedback["identities"]
        if not isinstance(snapshot, list) or any(not isinstance(value, str) or not value for value in snapshot):
            raise ValueError("invalid feedback identifiers")
        available = {packet["id"] for packet in records if packet["time_ms"] <= freeze}
        if not set(snapshot) <= available:
            raise ValueError("feedback contains an unobserved or future packet")
        if not feedback["truncated"] and set(snapshot) != available:
            raise ValueError("complete feedback omits a recorded packet")
        diagnostics.update(freeze_time_ms=freeze, feedback_received_ms=delivered,
                           feedback_received=delivered is not None and delivered <= deadline,
                           crc_list_truncated=feedback["truncated"])
        if not diagnostics["feedback_received"]:
            diagnostics["reason"] = "feedback_lost" if delivered is None else "feedback_after_deadline"
            return {"evidence": _none(len(identities)), "diagnostics": diagnostics}
        if feedback["truncated"]:
            diagnostics["reason"] = "feedback_list_truncated"
            return {"evidence": _none(len(identities), True), "diagnostics": diagnostics}
    if freeze < closed_at:
        diagnostics["reason"] = "snapshot_before_first_flight_closed"
        return {"evidence": _none(len(identities), True), "diagnostics": diagnostics}
    diagnostics["receiver_datagram_truncated"] |= any(packet["id"] in sender_sizes
                                                     and packet["time_ms"] <= freeze
                                                     and packet["read_size"] < packet["wire_size"]
                                                     for packet in records)
    if mode == "c1" and diagnostics["receiver_datagram_truncated"]:
        diagnostics["reason"] = "receiver_capacity_censoring"
        return {"evidence": _none(len(identities), True), "diagnostics": diagnostics}
    matching = {packet["id"] for packet in records if packet["time_ms"] <= freeze
                and (mode == "ideal" or packet["read_size"] == packet["wire_size"])
                and packet["wire_size"] == sender_sizes.get(packet["id"])}
    snapshot_set = set(snapshot)
    bitmap = [int(identity in snapshot_set and identity in matching) for identity in identities]
    diagnostics.update(matched=sum(bitmap), unmatched=len(snapshot_set - set(identities)),
                       duplicates=len(snapshot) - len(snapshot_set), usable=True,
                       all_lost=not any(bitmap), reason="complete_receiver_counts" if mode == "ideal" else "c1_snapshot")
    if diagnostics["all_lost"]:
        diagnostics["all_lost_basis"] = "complete_receiver_observation" if mode == "ideal" else "delivered_complete_snapshot"
    return {"evidence": {"src": "c1", "sent": len(identities), "lost": bitmap.count(0),
                         "bitmap": bitmap, "trunc": False}, "diagnostics": diagnostics}


def _packet_id(flight, kind, index):
    return f"{flight}:{kind}:{index}"


def _feedback_draw(seed, connection):
    _integer("seed", seed)
    _integer("connection", connection)
    material = f"{seed}:{connection}:v33-c1-feedback-v1".encode("utf-8")
    return random.Random(int.from_bytes(hashlib.blake2b(material, digest_size=16).digest(), "big")).random()


def make_world_evidence(observation, *, mode, seed, connection,
                        feedback_loss_probability=0.0, receiver_max_datagram_bytes=1452,
                        feedback_grace_ms=200.0, crc_list_limit=64):
    if mode not in MODES:
        raise ValueError("unknown observation mode")
    probability = _number("feedback_loss_probability", feedback_loss_probability)
    if probability > 1:
        raise ValueError("feedback_loss_probability exceeds one")
    grace = _number("feedback_grace_ms", feedback_grace_ms)
    limit = _integer("crc_list_limit", crc_list_limit, 1)
    _integer("seed", seed)
    _integer("connection", connection)
    if mode == "none":
        return {"evidence": _none(), "diagnostics": {"mode": mode, "usable": False,
                "reason": "disabled", "all_lost": False, "all_lost_basis": None}}
    if observation.get("model_kind") != "independent_event_world":
        raise ValueError("C1 projection requires the independent event world")
    tape = observation.get("trace")
    if not isinstance(tape, list) or not tape:
        raise ValueError("C1 projection requires sample(trace=True)")
    one_way = _number("world RTT", observation["true_rtt_ms"]) / 2.0
    emissions = [packet for packet in observation["arrivals"]
                 if packet["flight"] == 0 and packet["kind"] in ("L", "O", "P")]
    sender = [{"id": _packet_id(packet["flight"], packet["kind"], packet["index"]),
               "size": packet["size"], "sent_ms": packet["wire_finish_ms"]}
              for packet in emissions]
    closed_at = max((packet["sent_ms"] + one_way for packet in sender), default=0.0)
    receiver = [{"id": _packet_id(event["flight"], event["kind"], event["index"]),
                 "read_size": event["size"], "wire_size": event["wire_size"],
                 "time_ms": event["time_ms"]}
                for event in tape if event["event"] == "server_receive" and event["kind"] in ("L", "O", "P", "B", "V", "Q")]
    hct = _number("HCT", observation["hct"])
    client_deadline = hct + (grace if observation["ok"] else 0.0)
    processed_horizon = max(event["time_ms"] for event in tape)
    if mode == "ideal":
        deadline = processed_horizon
        feedback = None
    else:
        deadline = client_deadline
        freezes = [event["time_ms"] for event in tape if event["event"] == "server_receive" and event["kind"] == "R" and event["usable"]]
        feedback = None
        if freezes:
            freeze = min(freezes)
            identifiers = list(dict.fromkeys(packet["id"] for packet in receiver if packet["time_ms"] <= freeze))
            feedback = {"freeze_ms": freeze,
                        "received_ms": freeze + one_way if _feedback_draw(seed, connection) >= probability else None,
                        "identities": identifiers[:limit], "truncated": len(identifiers) > limit}
    result = observe_first_flight(sender, receiver, feedback, mode=mode, deadline_ms=deadline,
                                  closed_at_ms=closed_at, receiver_max_datagram_bytes=receiver_max_datagram_bytes)
    diagnostic = result["diagnostics"]
    diagnostic.update(identity_kind="virtual_flight_kind_index", passive_feedback=True,
                      closure_basis="fixed_per_connection_world_delay", feedback_trigger="physical_R_proxy",
                      client_deadline_ms=client_deadline, processed_horizon_ms=processed_horizon)
    first_ids = {packet["id"] for packet in sender}
    received_ids = {packet["id"] for packet in receiver if packet["id"] in first_ids and packet["time_ms"] <= client_deadline}
    evaluation_closed = min(client_deadline, processed_horizon) >= closed_at
    diagnostic["evaluation_only_closed"] = evaluation_closed
    diagnostic["evaluation_only_all_lost"] = bool(first_ids) and not received_ids if evaluation_closed else None
    diagnostic["evaluation_only_no_response_pto"] = observation["pto_count"] > 0 and not any(event["event"] == "client_receive" and event["time_ms"] <= client_deadline for event in tape)
    diagnostic["evaluation_only_c2_false_all_lost"] = diagnostic["evaluation_only_no_response_pto"] and bool(received_ids)
    return result
