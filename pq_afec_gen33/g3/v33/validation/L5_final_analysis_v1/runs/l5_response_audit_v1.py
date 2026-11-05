import sys
sys.dont_write_bytecode = True
from collections import Counter
from statistics import median


def audit_rows(rows, *, variant, reset_each_connection=False):
    if variant not in ("full", "single"):
        raise ValueError("unknown L5 size variant")
    catalog, window, sequence, next_id, resets = [], [], 0, 0, 0
    checks = updates = duplicates = others = late = 0
    def equal(actual, expected, name):
        nonlocal checks
        checks += 1
        if actual != expected:
            raise ValueError("L5 response audit mismatch: " + name)
    def distribution():
        samples = window
        if variant == "single" and samples:
            recent = samples[-16:]
            center = median(row["bytes"] for row in recent)
            samples = [min(reversed(recent), key=lambda row: abs(row["bytes"] - center))]
        counts = Counter((row["prefix"], row["bytes"], row["packet"]) for row in samples)
        return [{"prefix": prefix, "S": total, "packet": packet, "n_need": prefix // 1280 + 1, "weight": count / len(samples)}
                for (prefix, total, packet), count in sorted(counts.items())]
    for row in rows:
        if reset_each_connection:
            catalog, window, sequence, next_id, resets = [], [], 0, 0, 0
        request, info, decision = row["policy_observe_input"], row["observation_info"], row["decision"]
        expected_distribution = distribution()
        if expected_distribution:
            equal(decision["size_distribution"], expected_distribution, "causal decision distribution")
            equal(decision["a_pre"], 41 * (decision["k"] - 1) if request["rtt_ms"] is not None and row["observation_info"]["ctx"]["u"] > 0 else 0, "one preflight charge")
        else:
            equal(decision.get("size_distribution"), None, "cold decision without future size")
        equal(row["S_hat_pre"], median(sample["bytes"] for sample in window[-16:]) if window else None, "prior S display")
        packets, total, duplicate, other, post, finished = {}, 0, 0, 0, 0, False
        completion, previous = None, -1.0
        for time, kind, size, index in row["server_response_received"]:
            if time < previous:
                raise ValueError("unordered response input")
            previous = time
            if kind == "complete":
                if finished or size is not None or index is not None:
                    raise ValueError("invalid response completion")
                finished, completion = True, time
                continue
            if type(size) is not int or size <= 0 or kind not in ("data", "ack", "retry"):
                raise ValueError("invalid response receipt")
            total += size
            if finished:
                post += size
            elif kind != "data":
                other += size
            elif index in packets:
                equal(size, packets[index], "stable response identity")
                duplicate += size
            else:
                if type(index) is not int or index < 0:
                    raise ValueError("invalid response identity")
                packets[index] = size
        equal(finished, row["ok"], "observed completion")
        equal(total, request["srv_bytes"], "raw received bytes")
        if finished:
            equal(sorted(packets), list(range(len(packets))), "complete contiguous response")
            equal(completion, row["hct_ms"], "completion time")
        evidence = {"source": "world_receive_index_proxy", "complete": finished,
                    "packets": [[index, packets[index]] for index in sorted(packets)],
                    "received_server_bytes": total, "duplicate_data_bytes": duplicate,
                    "other_received_bytes": other, "post_complete_bytes": post}
        equal(request["optional"]["server_response"], evidence, "response evidence")
        duplicates += duplicate
        others += other
        late += post
        sample = None
        if finished:
            sizes = [packets[index] for index in sorted(packets)]
            sample = {"bytes": sum(sizes), "prefix": sum(sizes[:-1]), "packet": max(sizes),
                      "n_packets": len(sizes), "n_need": sum(sizes[:-1]) // 1280 + 1}
        equal(info["size_sample"], sample, "physical response geometry")
        equal(info["size_scope_before"], "complete_response" if window else "legacy_unclassified", "scope before")
        if info["ctx"] is not None and finished:
            expected = dict(info["ctx"])
            expected.update(n_need=sample["n_need"], a_pre=41 * (expected["k"] - 1) if expected["u"] > 0 else 0,
                size_distribution=[{"prefix": sample["prefix"], "S": sample["bytes"], "packet": sample["packet"], "n_need": sample["n_need"], "weight": 1.0}])
            equal(info["loss_context"], expected, "conditional size likelihood context")
            equal(info["loss_context_source"], "observed_complete_response", "conditional context source")
        else:
            equal(info["loss_context"], info["ctx"], "unobserved size likelihood context")
            equal(info["loss_context_source"], "prior_distribution", "prior context source")
        did_reset = False
        if finished:
            sequence += 1
            choices = [entry for entry in catalog if 2 * abs(sample["bytes"] - entry["bytes"]) < min(sample["packet"], entry["packet"])]
            if choices:
                chosen = min(choices, key=lambda entry: (abs(sample["bytes"] - entry["bytes"]), entry["id"]))
            else:
                if len(catalog) == 8:
                    evicted = min(catalog, key=lambda entry: (entry["last_seen"], entry["id"]))
                    catalog.remove(evicted)
                    window = [entry for entry in window if entry["cluster"] != evicted["id"]]
                chosen = {"id": next_id, "bytes": sample["bytes"], "packet": sample["packet"], "last_seen": sequence}
                next_id += 1
                catalog.append(chosen)
                if variant == "full" and window:
                    window = []
                    resets += 1
                    did_reset = True
            chosen["last_seen"] = sequence
            window.append({"bytes": sample["bytes"], "prefix": sample["prefix"], "packet": sample["packet"], "cluster": chosen["id"]})
            window = window[-64:]
            equal(info["size_window_n"], len(window), "updated window count")
            equal(info["size_catalog_n"], len(catalog), "updated catalog count")
            equal(info["size_cluster"], chosen["id"], "cluster assignment")
            updates += 1
        equal(info["size_reset"], did_reset, "change reset")
        equal(info["size_updated"], finished, "all completed response updates")
        equal(info["size_scope_after"], "complete_response" if window else "legacy_unclassified", "scope after")
        equal(row["S_hat_post"], median(sample["bytes"] for sample in window[-16:]) if window else None, "updated S display")
    return {"checks": checks, "rows": len(rows), "size_updates": updates, "received_duplicate_data_bytes": duplicates,
            "received_other_bytes": others, "received_post_complete_bytes": late, "final_resets": resets}
