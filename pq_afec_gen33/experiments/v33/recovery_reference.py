from dataclasses import dataclass, replace
import itertools
import math

from padfec3 import layout
from padfec import policy
from experiments.v33.server_cost_reference import ServerCost


def number(name, value, minimum=0.0, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(name + " must be finite")
    if value < minimum or positive and value <= minimum:
        raise ValueError(name + " is below its bound")
    return float(value)


@dataclass(frozen=True)
class RecoveryProfile:
    scope: str = "missing"
    retransmission: str = "original_first"
    sample_mode: str = "local_approx"
    explicit_sample_ms: float | None = None
    initial_pto_ms: float = layout.T_PTO_MS
    sampled_multiplier: float = layout.PTO_SAMPLED_MULT
    ack_slope: float = layout.T_ACK_SLOPE
    ack_base_ms: float = layout.T_ACK_BASE_MS

    def __post_init__(self):
        if self.scope not in ("missing", "all") or self.retransmission not in ("original_first", "repeat_first"):
            raise ValueError("unsupported retransmission profile")
        if self.sample_mode not in ("local_approx", "path", "explicit"):
            raise ValueError("unsupported sample mode")
        if self.sample_mode == "explicit":
            number("explicit sample", self.explicit_sample_ms, positive=True)
        elif self.explicit_sample_ms is not None:
            raise ValueError("explicit sample requires explicit mode")
        for key in ("initial_pto_ms", "sampled_multiplier", "ack_slope"):
            number(key, getattr(self, key), positive=True)
        number("ack_base_ms", self.ack_base_ms)


def retry_shape(k, missing, m, lead, profile):
    indices = tuple(range(k)) if profile.scope == "all" else tuple(sorted(missing))
    if profile.retransmission == "repeat_first":
        return indices, lead, m-lead
    return indices, 0, int(m > 0)


def flight_ledger(indices, needed, lead, trailing, width, uplink, pattern, *, lead_credited=True):
    if type(lead_credited) is not bool:
        raise ValueError("lead_credited must be bool")
    count = len(indices)
    if not 1 <= count <= 4 or len(set(indices)) != count or not needed or not set(needed) <= set(indices):
        raise ValueError("invalid retransmitted original coverage")
    if any(type(i) is not int or not 0 <= i <= 3 for i in indices):
        raise ValueError("invalid original index")
    if type(width) is not int or not 1200 <= width <= 1452:
        raise ValueError("invalid datagram width")
    number("uplink",uplink)
    layout.check_action(count, lead+trailing, lead)
    tokens = [("L", None)] * lead + [("O", i) for i in indices] + [("P", None)] * trailing
    if len(pattern) != len(tokens) or any(type(b) is not int or b not in (0,1) for b in pattern):
        raise ValueError("invalid arrival pattern")
    pz = layout.parity_bytes(width, count)
    needed, originals = set(needed), set()
    held = 0
    clock = physical = credit = 0.0
    complete = None
    events = []
    original_times = []
    for (kind, index), bit in zip(tokens, pattern):
        if not bit:
            continue
        size = width if kind == "O" else pz
        clock += layout.tau(size, uplink)
        physical += size
        increment = 0
        if kind == "L":
            increment += size if lead_credited else 0
        elif kind == "O":
            increment += size
            originals.add(index)
            needed.discard(index)
            original_times.append(clock)
        elif len(originals) == count:
            increment += size
        else:
            held += 1
        missing = count-len(originals)
        if missing and held >= missing:
            increment += missing*width
            held -= missing
            originals.update(indices)
            needed.clear()
        credit += increment
        if credit > physical:
            raise ArithmeticError("delivered credit exceeds physical arrivals")
        if increment:
            events.append((clock, increment))
        if not needed and complete is None:
            complete = (clock, credit, len(events))
    return dict(complete=complete, events=events, credit=credit, physical=physical,
                missing=tuple(sorted(needed)), original_times=original_times,
                sent_bytes=count*width+(lead+trailing)*pz,
                parity_bytes=(lead+trailing)*pz, held_symbols=held)


def weighted_patterns(n, probability):
    for pattern in itertools.product((0,1), repeat=n):
        weight = 1.0
        for bit in pattern:
            weight *= 1-probability if bit else probability
        if weight:
            yield pattern, weight


def completion(ledger, prior_credit, rtt, uplink, width, need, a_pre, *, server=None):
    if ledger["complete"] is None:
        raise ValueError("flight has not completed")
    at, credit, event_index = ledger["complete"]
    if server is not None:
        previous, expected = 1.0, 0.0
        base = int(prior_credit + credit)
        for when, increment in ledger["events"][event_index:]:
            q = policy.race_win_prob(when-at) if server.profile.trailing_race == "table" else 0.0
            expected += (previous-q)*(at+server.lossless_completion(base,rtt,uplink,width,a_pre))
            base += increment
            previous = q
        return expected+previous*(at+server.lossless_completion(base,rtt,uplink,width,a_pre))
    previous = 1.0
    expected = 0.0
    base = prior_credit+credit
    for when, increment in ledger["events"][event_index:]:
        q = policy.race_win_prob(when-at)
        nr = layout.rtt_count(base, need, a_pre)
        expected += (previous-q)*(at+nr*rtt+(layout.tau(width,uplink) if nr==2 else 0.0))
        base += increment
        previous = q
    nr = layout.rtt_count(base, need, a_pre)
    return expected+previous*(at+nr*rtt+(layout.tau(width,uplink) if nr==2 else 0.0))


def sample_value(profile, rtt, original_times):
    if profile.sample_mode == "explicit":
        return profile.explicit_sample_ms
    return rtt+(original_times[0] if profile.sample_mode == "local_approx" and original_times else 0.0)


def evaluate(k, width, m, lead, probability, rtt, uplink, need, *, profile=RecoveryProfile(), keep_branches=False, server=None):
    layout.check_action(k,m,lead)
    if type(width) is not int or not 1200 <= width <= 1452 or type(need) is not int or need < 1:
        raise ValueError("invalid width or required packet count")
    number("probability",probability)
    if probability>1:
        raise ValueError("probability exceeds one")
    number("rtt",rtt,positive=True)
    number("uplink",uplink)
    if not isinstance(profile,RecoveryProfile):
        raise ValueError("invalid recovery profile")
    if server is not None:
        if not isinstance(server, ServerCost) or need != len(server.sizes):
            raise ValueError("server packet list must match the required packet count")
        profile = replace(profile, initial_pto_ms=server.profile.pto_initial_ms)
    lead_credited = server is None or server.profile.lead_credited
    a_pre=layout.preflight_bytes(k,uplink)
    success_cost=fail_cost=fail_prob=terminal_prob=retry_bytes=retry_parity=retry_physical=0.0
    branches=[]
    kinds={name:0.0 for name in layout.FAIL_KINDS}
    for rec in layout.outcomes(k,m,lead,width,probability,uplink):
        pr=rec["pr"]
        if rec["kind"]=="ok":
            if server is None:
                for weight,credit in rec["branches"]:
                    nr=layout.rtt_count(credit,need,a_pre)
                    success_cost+=pr*weight*(rec["t_dec"]+nr*rtt+(layout.tau(width,uplink) if nr==2 else 0.0))
            else:
                base = server.profile.decision_credit(k*width, [layout.parity_bytes(width,k)]*rec["lead_arrived"])
                for weight,credit in server.profile.credit_branches(base, rec["after_delays"], rec["after_sizes"]):
                    success_cost += pr*weight*(rec["t_dec"]+server.lossless_completion(credit,rtt,uplink,width,a_pre))
            continue
        fail_prob+=pr
        kinds[rec["kind"]]+=pr
        arrived={i for i in range(k) if rec["pattern"][lead+i]}
        missing=set(range(k))-arrived
        initial_credit=len(arrived)*width+(rec["lead_arrived"]*layout.parity_bytes(width,k) if lead_credited else 0)
        first_times=[rec["arrival_ms"][lead+i] for i in range(k) if i in arrived]
        sample=sample_value(profile,rtt,first_times)
        timeout=profile.sampled_multiplier*sample if arrived else profile.initial_pto_ms
        if rec["kind"]=="pto":
            detection=profile.initial_pto_ms
        elif rec["kind"]=="ptoS":
            detection=rec["t_last_o"]+timeout
        else:
            detection=rec["t_last_o"]+profile.ack_slope*sample+profile.ack_base_ms
        indices,l2,t2=retry_shape(k,missing,m,lead,profile)
        conditional=tail=sent=parity=physical=0.0
        for pattern,weight in weighted_patterns(len(indices)+l2+t2,probability):
            ledger=flight_ledger(indices,missing,l2,t2,width,uplink,pattern,lead_credited=lead_credited)
            sent+=weight*ledger["sent_bytes"]
            parity+=weight*ledger["parity_bytes"]
            physical+=weight*ledger["physical"]
            if ledger["complete"] is not None:
                conditional+=weight*(detection+completion(ledger,initial_credit,rtt,uplink,width,need,a_pre,server=server))
            else:
                tail+=weight
                terminal_indices,lt,tt=retry_shape(k,ledger["missing"],m,lead,profile)
                terminal=flight_ledger(terminal_indices,ledger["missing"],lt,tt,width,uplink,(1,)*(len(terminal_indices)+lt+tt),lead_credited=lead_credited)
                next_sample=sample_value(profile,rtt,ledger["original_times"])
                next_timeout=timeout if arrived else (profile.sampled_multiplier*next_sample if ledger["original_times"] else profile.initial_pto_ms)
                delay=2*next_timeout
                conditional+=weight*(detection+delay+completion(terminal,initial_credit+int(ledger["credit"]),rtt,uplink,width,need,a_pre,server=server))
                sent+=weight*terminal["sent_bytes"]
                parity+=weight*terminal["parity_bytes"]
                physical+=weight*terminal["physical"]
        fail_cost+=pr*conditional
        terminal_prob+=pr*tail
        retry_bytes+=pr*sent
        retry_parity+=pr*parity
        retry_physical+=pr*physical
        if keep_branches:
            branches.append(dict(pattern=list(rec["pattern"]),kind=rec["kind"],probability=pr,missing=sorted(missing),
                                 initial_stack_credit=initial_credit,initial_physical_bytes=rec["phys_bytes"],
                                 initial_held_bytes=rec["phys_bytes"]-initial_credit,timer_sample_ms=sample if arrived else None,
                                 detection_ms=detection,retry_originals=len(indices),retry_lead=l2,retry_trailing=t2,
                                 conditional_cost_ms=conditional,second_failure_probability=tail))
            if server is not None:
                ignored_lead = 0 if lead_credited else rec["lead_arrived"]*layout.parity_bytes(width,k)
                branches[-1]["initial_ignored_lead_bytes"] = ignored_lead
                branches[-1]["initial_held_bytes"] -= ignored_lead
    result = dict(J=success_cost+fail_cost,success_contribution_ms=success_cost,failure_contribution_ms=fail_cost,
                p_fail=fail_prob,failure_kinds=kinds,conditional_failure_cost_ms=fail_cost/fail_prob if fail_prob else None,
                terminal_probability=terminal_prob,terminal_assumption="forced_lossless_completion_after_second_failure",
                first_client_bytes=layout.client_bytes(k,m,width),expected_retry_bytes=retry_bytes,
                expected_retry_parity_bytes=retry_parity,expected_retry_physical_bytes=retry_physical,
                expected_modeled_client_bytes=layout.client_bytes(k,m,width)+retry_bytes,
                response_and_ACK_bytes_included=False,sampled_multiplier_basis="RFC_derived_not_measured",
                presample_probe_regime=rtt+layout.tau(layout.pre_decision_bytes(k,m,lead,width),uplink)>=profile.initial_pto_ms,
                branches=branches)
    return server.attach(result) if server is not None else result
