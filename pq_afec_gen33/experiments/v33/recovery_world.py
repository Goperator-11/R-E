import heapq
import itertools
import random
import math

from experiments.v33.worldsim import World, WorldContext, Action
from experiments.v33.worldsim import _seed, _tau, first_flight_outcome, ge_parameters


class RecoveryWorld(World):
    def _validate_params(self):
        fec = self.params["fec"]
        shape = fec["retransmission_shape"]
        if fec.get("retransmission_scope", "all") not in ("all", "unacked"):
            raise ValueError("invalid retransmission scope")
        if fec.get("credit_scope", "connection") not in ("connection", "flight"):
            raise ValueError("invalid credit scope")
        if fec.get("retransmission_scope", "all") != "all" and shape != "t6_originals_first":
            raise ValueError("unacked scope requires the T6 retransmission shape")
        if shape == "t6_originals_first":
            if self.profile != "default" or fec["lead_mode"] != "credit_only":
                raise ValueError("T6 recovery world requires the event profile and credit-only lead")
            fec["retransmission_shape"] = "originals_first"
        try:
            super()._validate_params()
        finally:
            fec["retransmission_shape"] = shape

    def expectation(self, *args, **kwargs):
        raise ValueError("use the versioned diagnostic driver to preserve per-connection evidence")

    def _sample_events(self, context, action, connection, keep_trace, overrides):
        params = self.params
        features, channel, fec, timers = params["features"], params["channel"], params["fec"], params["timers"]
        server = params["server"]
        world_rng = random.Random(_seed(self.seed, connection, "environment"))
        c2s_rng = random.Random(_seed(self.seed, connection, "c2s"))
        s2c_rng = random.Random(_seed(self.seed, connection, "s2c"))
        sizes, selected_cert = self._packetization(context, connection, world_rng)
        p = context.p if features["c2s_loss"] else 0.0
        q = context.s2c_loss if features["s2c_loss"] else 0.0
        a, b = ge_parameters(p, context.burst_length) if context.loss_model == "ge" else (0.0, 0.0)
        state_key = (context.p, context.burst_length, context.condition)
        prior = self._ge_states.get(state_key)
        ge_bad = prior[1] if channel["preserve_ge_across_connections"] and prior is not None and prior[0] + 1 == connection else c2s_rng.random() < p
        c2s_mask, s2c_mask = tuple(overrides.get("c2s", ())), tuple(overrides.get("s2c", ()))
        for mask in (c2s_mask, s2c_mask):
            if any(bit not in (0, 1, False, True) for bit in mask):
                raise ValueError("override masks must contain arrival bits")
        mask_positions = {"c2s": 0, "s2c": 0}
        jitter_mean = context.jitter_mean_ms if context.jitter_mean_ms is not None else channel["jitter_mean_ms"]
        jitter = overrides.get("jitter_ms", world_rng.expovariate(1.0 / jitter_mean) if jitter_mean > 0 and features["destination_changes"] else 0.0)
        if not math.isfinite(jitter) or jitter < 0:
            raise ValueError("jitter must be finite and nonnegative")
        true_rtt = context.rtt_ms + jitter
        half_rtt = true_rtt / 2.0
        uplink = context.uplink_mbps if features["uplink_serialization"] else 0.0
        w = context.w + action.delta
        parity_size = self._parity_size(w, context.k)
        processing = context.c_proc_ms if context.c_proc_ms is not None else params["processing"]["conditions"].get(context.condition, params["processing"]["default_ms"])
        processing = processing if features["processing_delay"] else 0.0
        decision_delay = overrides.get("decision_delay_ms", self._race_delay(world_rng) if features["trailing_race"] else 0.0)
        if decision_delay < 0 or not math.isfinite(decision_delay):
            raise ValueError("decision delay must be finite and nonnegative")
        initial_pto = timers["rfc_initial_pto_ms"] if timers["use_rfc_initial_pto"] else timers["initial_pto_ms"]
        queue, trace_rows, arrival_rows = [], [], []
        serial = itertools.count()
        original_arrivals, original_stack, ack_seen = set(), set(), set()
        decoders = {}
        flight_originals = {}
        received_server, server_acked, outstanding = set(), set(), {}
        server_tx_sizes = []
        counters = {"client_bytes": 0, "first_bytes": 0, "physical_received": 0, "stack_credit": 0,
                    "server_sent": 0, "server_retransmission": 0, "initial": 0, "parity": 0, "pto": 0,
                    "client_server_received": 0, "wire_received": 0}
        state = {"uplink_free": 0.0, "ready": False, "ready_scheduled": False, "validated": bool(context.token and features["token_retry"]),
                 "retry_done": False, "retry_sent": False, "server_next": 0, "server_epoch": 0,
                 "client_epoch": 0, "sample_rtt": None, "srtt": None, "rttvar": None,
                 "min_rtt": None, "server_latest_rtt": None, "server_srtt": None, "server_rttvar": None,
                 "flight": 0, "last_flight": 0.0, "first_failure": None, "first_pattern": (),
                 "first_prefix": None, "srv_big": False, "reply_generation": 0,
                 "reply_delivered": False, "reply_active": False, "reply_retry": 0,
                 "max_orig_ack": -1, "preack_scheduled": False, "pending_ack": set(),
                 "pending_ack_reference": None, "reference_flight": 0.0, "post_ack_scheduled": False,
                 "retry_accepted_flight": 0, "probe_delivered": set(),
                 "last_retry_flight": -1,
                 "complete": False, "hct": timers["max_time_ms"], "second_round": False,
                 "tail": False, "client_retry": 0, "server_retry": 0, "stop_reason": "event_queue_empty"}

        def emit(name, time, **details):
            if keep_trace:
                trace_rows.append({"event": name, "time_ms": time, **details})

        def schedule(time, kind, data=None):
            if time <= timers["max_time_ms"]:
                heapq.heappush(queue, (time, next(serial), kind, data))

        def channel_bit(direction, later=False):
            nonlocal ge_bad
            mask = c2s_mask if direction == "c2s" else s2c_mask
            position = mask_positions[direction]
            mask_positions[direction] += 1
            if direction == "c2s":
                natural = not ge_bad if context.loss_model == "ge" else c2s_rng.random() >= p
                if context.loss_model == "ge":
                    ge_bad = c2s_rng.random() >= b if ge_bad else c2s_rng.random() < a
                if later and not features["second_round_loss"]:
                    natural = True
            else:
                natural = s2c_rng.random() >= q
            if position < len(mask):
                return bool(mask[position])
            if direction in overrides and overrides.get("mask_exhaustion") == "error":
                raise ValueError(f"{direction} override mask exhausted at {position}")
            return natural

        def transmit_client(time, kind, size, index, flight, later=False, server_ack=()):
            bit = channel_bit("c2s", later)
            start = max(time, state["uplink_free"])
            finish = start + (_tau(size, uplink) if bit or channel["lost_consumes_uplink"] else 0.0)
            state["uplink_free"] = finish
            counters["client_bytes"] += size
            if kind in ("O", "R", "B"):
                counters["initial"] += 1
            elif kind in ("L", "P", "Q", "V"):
                counters["parity"] += 1
            if flight == 0:
                counters["first_bytes"] += size
            arrival_rows.append({"flight": flight, "index": index, "kind": kind, "arrived": bit,
                                 "size": size, "sent_ms": time, "wire_finish_ms": finish,
                                 "read_size": min(size, server["decoder_max_datagram_bytes"]) if bit else 0,
                                 "usable": bit and size <= server["decoder_max_datagram_bytes"],
                                 "arrival_ms": finish + half_rtt if bit else None})
            emit("client_send", time, kind=kind, size=size, index=index, flight=flight, arrived=bit)
            if kind == "O" and state["first_prefix"] is None:
                state["first_prefix"] = max(0.0, start - time)
            if bit:
                schedule(finish + half_rtt, "client_arrival", (kind, size, index, flight, time, finish, server_ack))
            return bit, finish

        def sampled_pto():
            if state["sample_rtt"] is None:
                return initial_pto
            if state["srtt"] is None:
                return timers["sampled_pto_multiplier"] * state["sample_rtt"]
            return state["srtt"] + max(4.0 * state["rttvar"], 1.0)

        def server_pto():
            if state["server_latest_rtt"] is None:
                return initial_pto
            return state["server_srtt"] + max(4.0 * state["server_rttvar"], 1.0)

        def arm_client_pto(time):
            state["client_epoch"] += 1
            if not features["retransmissions"] or (state["sample_rtt"] is None and not features["presample_pto"]):
                return
            timeout = sampled_pto() * 2 ** state["client_retry"]
            schedule(max(time, state["last_flight"] + timeout), "client_pto", state["client_epoch"])

        def send_flight(time, retry=False):
            flight = state["flight"]
            standard = self._order(context, action)
            order = standard
            if retry and fec["retransmission_shape"] == "originals_first":
                order = ("O",) * context.k + (("P",) if action.trailing else ())
            indices = tuple(range(context.k))
            if retry and fec["retransmission_shape"] == "t6_originals_first":
                if fec.get("retransmission_scope", "all") == "unacked":
                    indices = tuple(i for i in indices if i not in ack_seen)
                if not indices:
                    raise ValueError("pre-response retry without unacknowledged CRYPTO is unsupported")
                order = ("O",) * len(indices) + (("P",) if action.lead+action.trailing else ())
            flight_originals[flight] = indices
            flight_parity_size = self._parity_size(w, len(indices))
            original_index = parity_index = 0
            bits, canonical = [], {"L": [], "O": [], "P": []}
            for kind in order:
                index = indices[original_index] if kind == "O" else parity_index
                bit, _ = transmit_client(time, kind, w if kind == "O" else flight_parity_size, index, flight)
                bits.append(bit)
                packet_size = w if kind == "O" else flight_parity_size
                canonical[kind].append(bit and packet_size <= server["decoder_max_datagram_bytes"])
                original_index += kind == "O"
                parity_index += kind != "O"
            if flight == 0:
                state["first_pattern"] = tuple(bits)
                outcome = first_flight_outcome(canonical["L"] + canonical["O"] + canonical["P"], context.k, action.lead, action.trailing, fec["lead_mode"])
                state["first_failure"] = not outcome["success"]
            if fec["lead_mode"] == "buffered":
                nominal = time + sum(_tau(w if kind == "O" else parity_size, uplink) for kind in order)
                schedule(nominal + half_rtt + fec["hold_margin_ms"], "hold_deadline", flight)
            state["last_flight"] = time
            state["flight"] += 1
            arm_client_pto(time)

        def can_send(size):
            if not features["amplification_limit"] or state["validated"] or server["mode"] == "unlimited":
                return True
            budget = 3 * counters["stack_credit"]
            return counters["server_sent"] < budget if server["mode"] == "granular" else counters["server_sent"] + size <= budget

        def send_server(time, kind, size, data, retransmission=False):
            if not can_send(size):
                emit("server_amp_blocked", time, kind=kind, size=size, sent=counters["server_sent"], credit=counters["stack_credit"])
                return False
            counters["server_sent"] += size
            server_tx_sizes.append(size)
            if retransmission:
                counters["server_retransmission"] += size
            bit = channel_bit("s2c")
            emit("server_send", time, kind=kind, size=size, arrived=bit, retransmission=retransmission)
            if bit:
                schedule(time + half_rtt, "server_arrival", (kind, size, data, time, retransmission))
            return True

        def arm_server_pto(time):
            state["server_epoch"] += 1
            if not outstanding or not features["retransmissions"] or not can_send(1):
                return
            base = server_pto()
            schedule(time + base * 2 ** state["server_retry"], "server_pto", state["server_epoch"])

        def flush_server(time):
            if not state["ready"]:
                return
            if context.retry and features["token_retry"] and not state["retry_done"]:
                if not state["retry_sent"]:
                    state["retry_sent"] = send_server(time, "retry", server["retry_bytes"], None)
                return
            while state["server_next"] < len(sizes) and len(outstanding) < server["iw_packets"]:
                index = state["server_next"]
                if not send_server(time, "data", sizes[index], index):
                    break
                outstanding[index] = time
                state["server_next"] += 1
            arm_server_pto(time)

        def credit(time, amount):
            blocked = not can_send(1)
            counters["stack_credit"] += amount
            emit("server_credit", time, amount=amount, total=counters["stack_credit"])
            if blocked and can_send(1) and outstanding:
                arm_server_pto(time)

        def decoder(flight):
            return decoders.setdefault(flight, {"originals": set(), "lead": {}, "trailing": {}})

        def request_ready(time):
            if len(original_arrivals) == context.k and not state["ready"] and not state["ready_scheduled"]:
                state["ready_scheduled"] = True
                schedule(time + decision_delay, "server_ready")

        def try_decode(time, flight, force=False):
            record = decoder(flight)
            held_lead, held_trailing = record["lead"], record["trailing"]
            indices = flight_originals[flight]
            missing = len(indices) - len(record["originals"])
            usable_trailing = list(held_trailing)
            usable_lead = list(held_lead) if fec["lead_mode"] == "buffered" else []
            if missing > len(usable_trailing) + len(usable_lead):
                request_ready(time)
                return
            if fec["lead_mode"] == "buffered" and missing and not force:
                request_ready(time)
                return
            for symbol in usable_trailing[:missing]:
                held_trailing.pop(symbol)
            used_lead = max(0, missing - len(usable_trailing))
            for symbol in usable_lead[:used_lead]:
                held_lead.pop(symbol)
            for index in indices:
                if index not in record["originals"]:
                    record["originals"].add(index)
                    original_arrivals.add(index)
                    original_stack.add(index)
                    credit(time, w)
                    emit("fec_recover", time, index=index, flight=flight)
            if fec["lead_mode"] == "buffered":
                for value in held_lead.values():
                    credit(time, value)
                held_lead.clear()
            for value in held_trailing.values():
                credit(time, value)
            held_trailing.clear()
            request_ready(time)

        def preack(time, index, sent_time):
            if not features["preflight_ack"] or uplink <= 0 or state["ready"]:
                return
            state["pending_ack"].add(index)
            reference = state["pending_ack_reference"]
            state["pending_ack_reference"] = sent_time if reference is None else min(reference, sent_time)
            if not state["preack_scheduled"]:
                state["preack_scheduled"] = True
                schedule(time + server["preflight_ack_coalesce_ms"], "send_preack")

        def record_rtt(value):
            value = value if features["rtt_inflation"] else true_rtt
            state["min_rtt"] = value if state["min_rtt"] is None else min(state["min_rtt"], value)
            if state["sample_rtt"] is None:
                state["sample_rtt"] = value
                state["srtt"] = value
                state["rttvar"] = value / 2.0
            else:
                state["sample_rtt"] = value
                state["rttvar"] = 0.75 * state["rttvar"] + 0.25 * abs(state["srtt"] - value)
                state["srtt"] = 0.875 * state["srtt"] + 0.125 * value

        def send_reply(time, retry=False):
            generation = state["reply_generation"]
            if not retry:
                state["reply_generation"] += 1
                generation = state["reply_generation"]
                state["reply_active"] = True
            flight = 1000000 + generation
            acknowledged = tuple(sorted(received_server))
            transmit_client(time, "R", w, generation, flight, True, acknowledged)
            if action.trailing and fec["response_xor"]:
                transmit_client(time, "Q", self._parity_size(w, 1), generation, flight, True, acknowledged)
            schedule(time + sampled_pto() * 2 ** state["reply_retry"], "reply_pto", generation)

        def handle_server_ack(time, acknowledged):
            acknowledged = set(acknowledged)
            newly_acked = acknowledged.intersection(outstanding)
            if newly_acked:
                newest = max(newly_acked)
                sample = time - outstanding[newest]
                state["server_latest_rtt"] = sample
                if state["server_srtt"] is None:
                    state["server_srtt"] = sample
                    state["server_rttvar"] = sample / 2.0
                else:
                    state["server_rttvar"] = 0.75 * state["server_rttvar"] + 0.25 * abs(state["server_srtt"] - sample)
                    state["server_srtt"] = 0.875 * state["server_srtt"] + 0.125 * sample
            server_acked.update(acknowledged)
            for packet_index in acknowledged:
                outstanding.pop(packet_index, None)
            if acknowledged:
                largest = max(acknowledged)
                for packet_index, packet_sent in tuple(outstanding.items()):
                    if packet_index < largest:
                        threshold = timers["loss_time_multiplier"] * max(state["server_latest_rtt"] or true_rtt, state["server_srtt"] or true_rtt)
                        schedule(max(time, packet_sent + threshold), "server_loss", packet_index)
            if state["server_next"] < len(sizes):
                state["second_round"] = True
            if not state["complete"]:
                flush_server(time)

        def send_post_big_probes(time):
            for probe in range(timers["initial_probe_packets"]):
                identifier = state["flight"] * timers["initial_probe_packets"] + probe
                transmit_client(time, "B", w, identifier, state["flight"])
                if action.trailing and fec["response_xor"]:
                    transmit_client(time, "V", self._parity_size(w, 1), identifier, state["flight"])
            state["flight"] += 1
            state["last_flight"] = time
            arm_client_pto(time)

        send_flight(0.0)
        events = 0
        while queue and events < timers["max_events"]:
            time, _, kind, data = heapq.heappop(queue)
            events += 1
            if state["complete"] and kind not in ("client_arrival", "server_arrival"):
                continue
            if kind == "client_arrival":
                token, size, index, flight, sent_time, finish, server_ack = data
                wire_size = size
                size = min(wire_size, server["decoder_max_datagram_bytes"])
                counters["wire_received"] += wire_size
                counters["physical_received"] += size
                usable = size == wire_size
                emit("server_receive", time, kind=token, size=size, wire_size=wire_size, usable=usable, index=index, flight=flight)
                if context.retry and features["token_retry"]:
                    if not state["retry_done"]:
                        if flight != state["last_retry_flight"]:
                            credit(time, size)
                            state["retry_sent"] = send_server(time, "retry", server["retry_bytes"], None)
                            state["last_retry_flight"] = flight
                        continue
                    if flight < state["retry_accepted_flight"]:
                        continue
                    if token == "O":
                        state["validated"] = True
                if not usable and token in ("L", "P", "Q", "V"):
                    credit(time, size)
                    emit("parity_truncated", time, kind=token, wire_size=wire_size, read_size=size)
                    continue
                if token in ("B", "V"):
                    if index not in state["probe_delivered"]:
                        state["probe_delivered"].add(index)
                        credit(time, w)
                        if not state["complete"]:
                            flush_server(time)
                    else:
                        credit(time, size)
                    continue
                if token == "A":
                    credit(time, size)
                    handle_server_ack(time, server_ack)
                    continue
                if token in ("R", "Q"):
                    if not state["reply_delivered"]:
                        state["reply_delivered"] = True
                        credit(time, w)
                        state["validated"] = True
                        state["server_retry"] = 0
                        handle_server_ack(time, server_ack)
                    else:
                        credit(time, size)
                    continue
                if token == "O":
                    state["reference_flight"] = max(state["reference_flight"], sent_time)
                    decoder(flight)["originals"].add(index)
                    original_arrivals.add(index)
                    original_stack.add(index)
                    credit(time, size)
                    if len(original_arrivals) < context.k:
                        preack(time, index, sent_time)
                    try_decode(time, flight, force=index == flight_originals[flight][-1])
                    if state["ready"] and not state["complete"]:
                        flush_server(time)
                elif token == "L":
                    if fec["lead_mode"] == "credit_only" or state["ready"]:
                        credit(time, size)
                    else:
                        decoder(flight)["lead"][index] = size
                else:
                    if fec.get("credit_scope", "connection") == "connection" and (state["ready"] or state["ready_scheduled"]):
                        credit(time, size)
                    else:
                        decoder(flight)["trailing"][index] = size
                        try_decode(time, flight, force=True)
            elif kind == "hold_deadline":
                try_decode(time, data, force=True)
            elif kind == "send_preack":
                state["preack_scheduled"] = False
                acknowledged = tuple(sorted(state["pending_ack"]))
                reference = state["pending_ack_reference"]
                state["pending_ack"].clear()
                state["pending_ack_reference"] = None
                if acknowledged:
                    send_server(time, "ack", server["preflight_ack_bytes"], (acknowledged, reference))
            elif kind == "server_ready":
                state["ready"] = True
                state["ready_scheduled"] = False
                emit("server_ready", time)
                flush_server(time)
            elif kind == "server_arrival":
                token, size, index, packet_sent, retransmission = data
                counters["client_server_received"] += size
                emit("client_receive", time, kind=token, size=size, index=index)
                if state["complete"]:
                    continue
                if token == "retry":
                    state["retry_done"] = True
                    state["retry_accepted_flight"] = state["flight"]
                    state["ready"] = False
                    state["ready_scheduled"] = False
                    original_arrivals.clear()
                    original_stack.clear()
                    decoders.clear()
                    state["client_retry"] = 0
                    send_flight(time, retry=True)
                    continue
                if token == "ack":
                    indices, reference = index
                    ack_seen.update(indices)
                    record_rtt(time - reference)
                    highest = max(indices)
                    if highest > state["max_orig_ack"]:
                        state["max_orig_ack"] = highest
                        if any(i not in ack_seen for i in range(highest)) and features["retransmissions"]:
                            schedule(max(time, state["last_flight"] + timers["loss_time_multiplier"] * state["sample_rtt"] + timers["loss_timer_extra_ms"]), "client_loss")
                    arm_client_pto(time)
                    continue
                received_server.add(index)
                if 0 in received_server and state["sample_rtt"] is None:
                    record_rtt(time - state["reference_flight"])
                if size >= 1200:
                    state["srv_big"] = True
                if 0 in received_server and not state["reply_active"]:
                    schedule(time, "send_reply")
                    state["reply_active"] = True
                elif 0 in received_server and state["reply_delivered"] and not state["post_ack_scheduled"]:
                    schedule(time, "send_post_ack")
                    state["post_ack_scheduled"] = True
                if len(received_server) == len(sizes):
                    schedule(time + processing, "complete")
                elif retransmission:
                    state["tail"] = True
            elif kind == "send_reply":
                send_reply(time)
            elif kind == "send_post_ack":
                state["post_ack_scheduled"] = False
                transmit_client(time, "A", server["preflight_ack_bytes"], 0, 2000000, True, tuple(sorted(received_server)))
            elif kind == "client_loss":
                if not state["srv_big"] and state["client_retry"] < timers["max_pto_backoff"]:
                    state["client_retry"] += 1
                    send_flight(time, retry=True)
            elif kind == "client_pto":
                if data != state["client_epoch"] or (state["srv_big"] and 0 in received_server and state["reply_active"]):
                    continue
                if state["client_retry"] >= timers["max_pto_backoff"]:
                    state["stop_reason"] = "client_pto_limit"
                    continue
                counters["pto"] += 1
                emit("client_pto", time, retry=state["client_retry"])
                state["client_retry"] += 1
                if state["srv_big"]:
                    send_post_big_probes(time)
                else:
                    send_flight(time, retry=True)
            elif kind == "reply_pto":
                if data != state["reply_generation"] or state["reply_delivered"]:
                    continue
                if state["reply_retry"] >= timers["max_pto_backoff"] or not features["retransmissions"]:
                    continue
                counters["pto"] += 1
                state["tail"] = True
                state["reply_retry"] += 1
                send_reply(time, retry=True)
            elif kind == "server_loss":
                if data not in outstanding or data in server_acked:
                    continue
                if send_server(time, "data", sizes[data], data, True):
                    outstanding[data] = time
                    state["tail"] = True
                arm_server_pto(time)
            elif kind == "server_pto":
                if data != state["server_epoch"] or not outstanding or not can_send(1):
                    continue
                if state["server_retry"] >= timers["max_pto_backoff"]:
                    continue
                counters["pto"] += 1
                state["server_retry"] += 1
                for packet_index in sorted(outstanding)[:2]:
                    if send_server(time, "data", sizes[packet_index], packet_index, True):
                        outstanding[packet_index] = time
                state["tail"] = True
                arm_server_pto(time)
            elif kind == "complete":
                state["complete"] = True
                state["hct"] = time
                state["stop_reason"] = "handshake_complete"
                emit("handshake_complete", time)
        if events >= timers["max_events"]:
            state["stop_reason"] = "event_limit"
        if channel["preserve_ge_across_connections"]:
            self._ge_states[state_key] = (connection, ge_bad)
        category = "failure" if state["first_failure"] or not state["complete"] else ("tail" if state["tail"] else ("two" if state["second_round"] else "one"))
        return {"hct": state["hct"], "ok": state["complete"], "k_obs": context.k,
                "srv_bytes": counters["client_server_received"],
                "rtt": state["min_rtt"], "initial_datagrams": counters["initial"],
                "initial_failure": bool(state["first_failure"]), "arrivals": arrival_rows,
                "ack_seen": sorted(ack_seen), "server_dgram_sizes": server_tx_sizes,
                "server_counted_uplink_bytes": counters["physical_received"],
                "server_wire_received_bytes": counters["wire_received"],
                "server_stack_credit_bytes": counters["stack_credit"],
                "client_first_flight_bytes": counters["first_bytes"],
                "client_total_uplink_bytes": counters["client_bytes"],
                "server_retransmission_bytes": counters["server_retransmission"],
                "server_total_sent_bytes": counters["server_sent"],
                "parity_datagrams": counters["parity"], "pto_count": counters["pto"],
                "world_class": category, "model_kind": "independent_event_world",
                "true_rtt_ms": true_rtt, "sample_rtt_ms": state["sample_rtt"],
                "min_rtt_ms": state["min_rtt"], "server_sample_rtt_ms": state["server_latest_rtt"],
                "selected_cert_bytes": selected_cert, "server_first_flight_bytes": sum(sizes),
                "server_first_flight_sizes": list(sizes), "initial_arrival_pattern": state["first_pattern"],
                "stop_reason": state["stop_reason"], "event_count": events,
                "params_sha256": self.params_sha256, "trace": trace_rows,
                "recovery_world_version": 1,
                "retransmission_scope": fec.get("retransmission_scope", "all"),
                "credit_scope": fec.get("credit_scope", "connection"),
                "flight_originals": {str(key): list(value) for key,value in flight_originals.items()}}
