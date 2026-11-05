from pathlib import Path
import sys

from experiments.v33.worldsim import World


def sample_with_server_trace(world, context, action, *, connection=0, overrides=None, max_records=100000):
    if type(world) is not World or world.profile != "default":
        raise ValueError("server tracing requires the unmodified default World class")
    if type(max_records) is not int or max_records < 1:
        raise ValueError("max_records must be a positive integer")
    if sys.getprofile() is not None:
        raise RuntimeError("an existing profiler must not be replaced")
    source = str(Path(sys.modules[World.__module__].__file__).resolve())
    records = []
    names = {"send_server", "arm_server_pto", "handle_server_ack", "flush_server", "credit", "schedule"}
    state_keys = ("validated", "server_epoch", "server_retry", "server_next", "server_srtt", "server_rttvar",
                  "server_latest_rtt", "client_epoch", "client_retry", "sample_rtt", "srtt", "rttvar",
                  "last_flight", "srv_big", "reply_active")

    def record(frame, event, result):
        code = frame.f_code
        if event not in ("call", "return") or code.co_filename != source or code.co_name not in names:
            return
        local = frame.f_locals
        if code.co_name == "schedule" and local.get("kind") not in ("server_pto", "server_loss", "client_pto", "reply_pto"):
            return
        if len(records) >= max_records:
            raise RuntimeError("server trace record limit reached")
        owner = frame.f_back
        while owner is not None and not (owner.f_code.co_filename == source and owner.f_code.co_name == "_sample_events"):
            owner = owner.f_back
        if owner is None:
            raise RuntimeError("world event owner frame is missing")
        environment = owner.f_locals
        state = environment["state"]
        counters = environment["counters"]
        row = dict(index=len(records), event=event, function=code.co_name, time_ms=local.get("time"),
                   state={key: state[key] for key in state_keys if key in state},
                   counters={key: counters[key] for key in ("stack_credit", "server_sent", "server_retransmission") if key in counters},
                   outstanding=sorted(environment["outstanding"].items()))
        for key in ("kind", "size", "data", "retransmission", "amount", "acknowledged", "base"):
            if key in local:
                value = local[key]
                row[key] = sorted(value) if isinstance(value, set) else value
        if code.co_name == "send_server" and event == "return":
            row["sent"] = result
        if code.co_name == "arm_server_pto" and event == "return":
            epoch = state.get("server_epoch")
            row["armed_deadlines"] = [item[0] for item in environment["queue"] if item[2] == "server_pto" and item[3] == epoch]
        records.append(row)

    sys.setprofile(record)
    try:
        outcome = world.sample(context, action, connection=connection, trace=True, overrides=overrides)
    finally:
        sys.setprofile(None)
    return dict(outcome=outcome, server_internal_trace=records, source=source)
