import math
from collections import Counter

MAX_BYTES = (1 << 53) - 1
MAX_PACKETS = 4096
WINDOW = 64
CATALOG_MAX = 8
SOURCES = ("world_receive_index_proxy",)
SCOPES = ("legacy_unclassified", "complete_response")


def byte_count(name, value, *, positive=False):
    if type(value) is not int:
        raise TypeError("%s must be an integer" % name)
    if not (1 if positive else 0) <= value <= MAX_BYTES:
        raise ValueError("%s exceeds the exact byte range" % name)
    return value


def physical(packet_sizes):
    if not isinstance(packet_sizes, (list, tuple)) or not 1 <= len(packet_sizes) <= MAX_PACKETS:
        raise ValueError("complete response needs a bounded nonempty packet list")
    sizes = [byte_count("response packet", value, positive=True) for value in packet_sizes]
    total = byte_count("complete response bytes", sum(sizes), positive=True)
    prefix = total - sizes[-1]
    return {"bytes": total, "prefix": prefix, "packet": max(sizes),
            "n_packets": len(sizes), "n_need": prefix // 1280 + 1}


def effective_bytes(s_obs, n_obs, tail, base_bin, c_pkt):
    byte_count("S_obs", s_obs, positive=True)
    byte_count("N_obs", n_obs, positive=True)
    byte_count("base_bin", base_bin)
    if n_obs > MAX_PACKETS:
        raise ValueError("N_obs exceeds the packet limit")
    for name, value in (("tail", tail), ("c_pkt", c_pkt)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError("%s must be finite and nonnegative" % name)
    if tail >= s_obs or c_pkt >= 1280:
        raise ValueError("tail or c_pkt is outside its range")
    result = s_obs - tail - (n_obs - base_bin) * c_pkt
    if not math.isfinite(result) or not 0 < result <= MAX_BYTES:
        raise ValueError("effective response bytes are outside their range")
    return result


def normalize(value, srv_bytes, ok):
    if value is None:
        return None
    fields = {"source", "complete", "packets", "received_server_bytes", "duplicate_data_bytes",
              "other_received_bytes", "post_complete_bytes"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("server response fields do not match the observation contract")
    if value["source"] not in SOURCES or type(value["complete"]) is not bool:
        raise ValueError("invalid response source or completion marker")
    if value["complete"] and not ok:
        raise ValueError("a failed connection cannot supply a complete response")
    packets = value["packets"]
    if not isinstance(packets, list) or len(packets) > MAX_PACKETS:
        raise ValueError("response packets must be a bounded list")
    normalized = []
    previous = -1
    for row in packets:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            raise ValueError("response packets require index,size pairs")
        index, size = byte_count("response index", row[0]), byte_count("response size", row[1], positive=True)
        if index <= previous or index >= MAX_PACKETS:
            raise ValueError("response indices must be unique and increasing")
        previous = index
        normalized.append([index, size])
    if value["complete"] and (not normalized or [row[0] for row in normalized] != list(range(len(normalized)))):
        raise ValueError("complete response indices must start at zero without gaps")
    counts = {key: byte_count(key, value[key]) for key in fields - {"source", "complete", "packets"}}
    unique = byte_count("unique response bytes", sum(size for _, size in normalized))
    if counts["received_server_bytes"] != unique + counts["duplicate_data_bytes"] + counts["other_received_bytes"] + counts["post_complete_bytes"]:
        raise ValueError("response accounting does not match received bytes")
    if isinstance(srv_bytes, bool) or not isinstance(srv_bytes, (int, float)) or not math.isfinite(srv_bytes) or srv_bytes != counts["received_server_bytes"]:
        raise ValueError("response and srv_bytes must use the same received-byte scope")
    return {"source": value["source"], "complete": value["complete"], "packets": normalized,
            **counts, "sample": physical([size for _, size in normalized]) if value["complete"] else None}


def new_history():
    return {"seq": 0, "next_id": 0, "catalog": [], "window": [], "resets": 0}


def _sample(value):
    if not isinstance(value, dict) or set(value) != {"bytes", "prefix", "packet", "cluster"}:
        raise ValueError("invalid response history sample")
    result = {key: byte_count(key, item, positive=key in ("bytes", "packet")) for key, item in value.items()}
    if not 0 <= result["prefix"] < result["bytes"] or result["packet"] > result["bytes"] or result["bytes"] - result["prefix"] > result["packet"]:
        raise ValueError("inconsistent physical response history")
    return result


def validate_history(value):
    if not isinstance(value, dict) or set(value) != {"seq", "next_id", "catalog", "window", "resets"}:
        raise ValueError("invalid response history")
    result = {key: byte_count(key, value[key]) for key in ("seq", "next_id", "resets")}
    if not isinstance(value["catalog"], list) or len(value["catalog"]) > CATALOG_MAX:
        raise ValueError("response catalog exceeds its cap")
    if not isinstance(value["window"], list) or len(value["window"]) > WINDOW:
        raise ValueError("response window exceeds its cap")
    catalog, ids = [], set()
    for entry in value["catalog"]:
        if not isinstance(entry, dict) or set(entry) != {"id", "bytes", "packet", "last_seen"}:
            raise ValueError("invalid response catalog entry")
        row = {key: byte_count(key, item, positive=key in ("bytes", "packet", "last_seen")) for key, item in entry.items()}
        if row["id"] in ids or row["id"] >= result["next_id"] or row["last_seen"] > result["seq"] or row["packet"] > row["bytes"]:
            raise ValueError("inconsistent response catalog")
        ids.add(row["id"])
        catalog.append(row)
    window = [_sample(row) for row in value["window"]]
    if any(row["cluster"] not in ids for row in window) or len(window) > result["seq"] or result["resets"] > result["seq"]:
        raise ValueError("inconsistent response history sequence")
    if bool(window) != bool(catalog) or bool(catalog) != bool(result["seq"]):
        raise ValueError("response history empty state mismatch")
    return {**result, "catalog": catalog, "window": window}


def record(history, sample, *, mode="full"):
    if mode not in ("full", "single"):
        raise ValueError("invalid response history mode")
    history["seq"] += 1
    eligible = [row for row in history["catalog"] if 2 * abs(sample["bytes"] - row["bytes"]) < min(sample["packet"], row["packet"])]
    reset = False
    if eligible:
        chosen = min(eligible, key=lambda row: (abs(sample["bytes"] - row["bytes"]), row["id"]))
    else:
        if len(history["catalog"]) == CATALOG_MAX:
            evicted = min(history["catalog"], key=lambda row: (row["last_seen"], row["id"]))
            history["catalog"].remove(evicted)
            history["window"] = [row for row in history["window"] if row["cluster"] != evicted["id"]]
        chosen = {"id": history["next_id"], "bytes": sample["bytes"], "packet": sample["packet"], "last_seen": history["seq"]}
        history["next_id"] += 1
        history["catalog"].append(chosen)
        if mode == "full" and history["window"]:
            history["window"] = []
            history["resets"] += 1
            reset = True
    chosen["last_seen"] = history["seq"]
    history["window"].append({key: sample[key] for key in ("bytes", "prefix", "packet")} | {"cluster": chosen["id"]})
    history["window"] = history["window"][-WINDOW:]
    return {"size_reset": reset, "size_cluster": chosen["id"], "size_window_n": len(history["window"]), "size_catalog_n": len(history["catalog"])}


def distribution(history, *, mode="full"):
    rows = history["window"]
    if not rows:
        return None
    if mode == "single":
        recent = rows[-16:]
        ordered = sorted(row["bytes"] for row in recent)
        n = len(ordered)
        doubled = 2 * ordered[n // 2] if n % 2 else ordered[n // 2 - 1] + ordered[n // 2]
        selected = min(reversed(recent), key=lambda row: abs(2 * row["bytes"] - doubled))
        rows = [selected]
    elif mode != "full":
        raise ValueError("invalid response distribution mode")
    counts = Counter((row["prefix"], row["bytes"], row["packet"]) for row in rows)
    return [{"prefix": prefix, "S": total, "packet": packet, "n_need": prefix // 1280 + 1, "weight": count / len(rows)}
            for (prefix, total, packet), count in sorted(counts.items())]


def validate_distribution(value):
    if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= WINDOW:
        raise ValueError("size distribution must be a bounded nonempty sequence")
    result = []
    previous = None
    for row in value:
        if not isinstance(row, dict) or set(row) != {"prefix", "S", "packet", "n_need", "weight"}:
            raise ValueError("invalid size distribution entry")
        prefix, total, packet, need = (byte_count(key, row[key], positive=key != "prefix") for key in ("prefix", "S", "packet", "n_need"))
        weight = row["weight"]
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight) or not 0 < weight <= 1:
            raise ValueError("invalid size distribution weight")
        key = (prefix, total, packet)
        if previous is not None and key <= previous:
            raise ValueError("size distribution must be unique and sorted")
        if prefix >= total or packet > total or total - prefix > packet or need != prefix // 1280 + 1:
            raise ValueError("inconsistent size distribution geometry")
        result.append({"prefix": prefix, "S": total, "packet": packet, "n_need": need, "weight": float(weight)})
        previous = key
    if abs(sum(row["weight"] for row in result) - 1.0) > 1e-9:
        raise ValueError("size distribution mass must be one")
    return result
