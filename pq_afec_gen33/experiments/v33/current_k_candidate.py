from copy import deepcopy

from padfec3 import decide3, layout, learn3
from experiments.v33.natural_k_reference import natural_k, packetize


CANDIDATE_VERSION = "current-k-reference/1"


class UnsupportedRepacking(ValueError):
    pass


class CurrentKPolicy:
    def __init__(self, state=None):
        self.state = learn3.new_state() if state is None else state
        self.pending = None

    def decide(self, hello, width, u_mbps, rtt_ms, c_pkt, *, actions=None,
               later=learn3.LATER_DEFAULT, max_ips=decide3.MAX_IPS,
               m_max=decide3.M_MAX, max_steps=decide3.MAX_STEPS, keep_cands=False):
        if self.pending is not None:
            raise ValueError("an observation is pending")
        expected = packetize(hello, width)
        k = len(expected)
        candidate = deepcopy(self.state)
        history = deepcopy(candidate.k_hist)
        candidate.k_hist = [k]
        if actions is not None:
            actions = [learn3.check_action(tuple(a)) for a in actions]
        learn3.check_transport(width, u_mbps, rtt_ms, c_pkt, missing_rtt=True)
        learn3.check_later(later)
        decide3.check_candidate_options(max_ips, m_max, max_steps)
        if actions is not None:
            widths = [width + a[0] for a in actions]
        elif candidate.S_hist and 1 <= k <= layout.K_MAX and rtt_ms is not None and rtt_ms > 0:
            widths = [c["W_eff"] for c in decide3.candidates3(k, width, learn3.s_hat(candidate), c_pkt,
                      max_ips=max_ips, m_max=m_max, max_steps=max_steps)]
        else:
            widths = [width]
        for w in sorted(set(widths)):
            if natural_k(hello, w) != k:
                raise UnsupportedRepacking(f"candidate width {w} changes current k={k}")
        result = decide3.decide3(candidate, width, u_mbps, rtt_ms, c_pkt, actions=actions,
                                 later=later, max_ips=max_ips, m_max=m_max,
                                 max_steps=max_steps, keep_cands=keep_cands)
        candidate.k_hist = history
        result.update(candidate_version=CANDIDATE_VERSION, k_source="current_clienthello",
                      natural_k=k, expected_k=k, expected_scope="first_flight")
        pending = dict(k=k, width=width, u=u_mbps, c_pkt=c_pkt, later=later,
                       action=result["action"], predicted=result["j3_pred_pre_ms"],
                       decision_index=candidate.n_dec, observation_index=candidate.stats["obs"])
        self.state.__dict__.update(candidate.__dict__)
        pending["state"] = deepcopy(candidate.__dict__)
        self.pending = pending
        return result

    def observe(self, hct_ms, ok, k_obs, srv_bytes, rtt_ms, *, arrivals=None):
        if self.pending is None:
            raise ValueError("no decision is pending")
        plan = self.pending
        if self.state.__dict__ != plan["state"]:
            raise ValueError("state changed after the decision")
        if type(k_obs) is not int or not 0 <= k_obs <= 64:
            raise ValueError("observed k must be an integer in 0..64")
        if k_obs != 0 and k_obs != plan["k"]:
            raise ValueError("observed flight differs from current ClientHello")
        candidate = deepcopy(self.state)
        history = deepcopy(candidate.k_hist)
        candidate.k_hist = [plan["k"]]
        info = learn3.observe3(candidate, plan["action"], hct_ms, ok, k_obs, srv_bytes, rtt_ms,
                               W=plan["width"], u_mbps=plan["u"], c_pkt=plan["c_pkt"],
                               later=plan["later"], j_pred=plan["predicted"], arrivals=arrivals)
        if ok and k_obs >= 1:
            history.append(k_obs)
            history = history[-learn3.K_WIN:]
        candidate.k_hist = history
        info.update(candidate_version=CANDIDATE_VERSION, k_source="current_clienthello", natural_k=plan["k"])
        self.state.__dict__.update(candidate.__dict__)
        self.pending = None
        return info
