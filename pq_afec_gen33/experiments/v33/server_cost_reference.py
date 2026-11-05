from dataclasses import dataclass

from experiments.v33.server_profile import ServerProfile, integer, number


@dataclass(frozen=True)
class ServerCost:
    profile: ServerProfile
    sizes: tuple
    p_d: float = 0.0
    ack_bytes: int = 41

    def __post_init__(self):
        if not isinstance(self.profile, ServerProfile):
            raise ValueError("invalid server profile")
        if type(self.sizes) is not tuple:
            raise ValueError("sizes must be an immutable tuple")
        self.profile.packets(self.sizes)
        number("downlink loss", self.p_d, 0, 1)
        integer("ACK bytes", self.ack_bytes, 1, self.profile.P)

    def lossless_completion(self, credit, rtt_ms, uplink_mbps, reply_bytes, prior_server_bytes):
        number("RTT", rtt_ms)
        if rtt_ms == 0:
            raise ValueError("RTT must be positive")
        number("uplink", uplink_mbps)
        integer("reply bytes", reply_bytes, 1200, 1452)
        first = self.profile.send_prefix(credit, self.sizes, sent_bytes=prior_server_bytes)
        if first["sent_packets"] == 0:
            raise ValueError("no first server data packet; client credit probe timing is unresolved")
        remaining = len(self.sizes) - first["sent_packets"]
        extra_rounds = (remaining + self.profile.iw_pkts - 1) // self.profile.iw_pkts
        delay = (1 + extra_rounds) * rtt_ms
        if extra_rounds and uplink_mbps:
            delay += 8 * (reply_bytes + (extra_rounds - 1) * self.ack_bytes) / (1000 * uplink_mbps)
        return delay

    def attach(self, result):
        output = dict(result)
        output.update(server_profile=self.profile.to_dict(), server_dgram_sizes=self.sizes,
                      downlink_loss=self.p_d, downlink_loss_probability=1-(1-self.p_d)**len(self.sizes),
                      server_window_model="fixed_packet_count_after_each_ack",
                      lossless_server_reply_assumption="first_data_packet_enables_lossless_address_validation",
                      server_ack_bytes=self.ack_bytes)
        if self.p_d:
            output["lossless_counterfactual_J"] = output.pop("J")
            output["J"] = None
            keys = ("success_contribution_ms", "failure_contribution_ms", "conditional_failure_cost_ms")
            output["lossless_counterfactual_costs"] = {key: output[key] for key in keys}
            for key in keys:
                output[key] = None
            output["branches"] = [dict(row, conditional_cost_ms=None, lossless_counterfactual_cost_ms=row["conditional_cost_ms"])
                                  for row in output["branches"]]
            output["cost_complete"] = False
            output["unresolved"] = "downlink_retransmission_timing_and_validation"
        else:
            output["cost_complete"] = True
            output["unresolved"] = None
        return output
