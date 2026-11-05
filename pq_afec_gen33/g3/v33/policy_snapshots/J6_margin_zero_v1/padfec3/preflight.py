import math

HISTORY_MAX = 64
WINDOW = 16
MARGIN = 0
MAX_BYTES = (1 << 53) - 1
SOURCES = ("client_initial", "world_arrival_proxy")
SCOPES = ("legacy_unclassified", "response_excludes_observed_preflight")


def byte_count(name, value):
    if type(value) is not int:
        raise TypeError("%s must be an integer" % name)
    if not 0 <= value <= MAX_BYTES:
        raise ValueError("%s is outside the exact byte range" % name)
    return value


def uplink(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("uplink must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError("uplink must be finite and nonnegative")
    return result


def normalize(value, srv_bytes):
    if value is None:
        return None
    fields = {"source", "small_initial_sizes", "first_large_seen", "srv_bytes_scope"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("preflight requires source,small_initial_sizes,first_large_seen,srv_bytes_scope")
    if value["source"] not in SOURCES:
        raise ValueError("invalid preflight source")
    if type(value["first_large_seen"]) is not bool:
        raise TypeError("first_large_seen must be bool")
    if value["srv_bytes_scope"] != "includes_observed_preflight":
        raise ValueError("preflight and srv_bytes must describe the same received bytes")
    sizes = value["small_initial_sizes"]
    if not isinstance(sizes, list) or len(sizes) > HISTORY_MAX:
        raise ValueError("small_initial_sizes must be a bounded list")
    for size in sizes:
        if not 0 < byte_count("small Initial size", size) < 1200:
            raise ValueError("small Initial size must be in 1..1199")
    total = sum(sizes)
    if srv_bytes is None or isinstance(srv_bytes, bool) or not isinstance(srv_bytes, (int, float)):
        raise ValueError("preflight requires received server bytes")
    if not math.isfinite(srv_bytes) or srv_bytes < total:
        raise ValueError("preflight exceeds received server bytes")
    return {**value, "small_initial_sizes": list(sizes), "total": total,
            "response_bytes": srv_bytes - total}


def validate_history(rows):
    if not isinstance(rows, list) or len(rows) > HISTORY_MAX:
        raise ValueError("preflight history must be a bounded list")
    result = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"k", "u", "bytes", "source"}:
            raise ValueError("invalid preflight history record")
        k = byte_count("preflight k", row["k"])
        if not 1 <= k <= 4 or row["source"] not in SOURCES:
            raise ValueError("invalid preflight history context")
        count = byte_count("preflight bytes", row["bytes"])
        if not 0 < count <= HISTORY_MAX * 1199:
            raise ValueError("preflight history needs a positive observed total")
        result.append({"k": k, "u": uplink(row["u"]), "bytes": count, "source": row["source"]})
    return result


def estimate(rows, k, u, fallback):
    selected = [row["bytes"] for row in rows if row["k"] == k and row["u"] == u][-WINDOW:]
    if not selected:
        return {"a_pre": fallback, "a_pre_median": None, "a_pre_n": 0,
                "a_pre_source": "legacy_estimate"}
    selected.sort()
    n = len(selected)
    doubled = 2 * selected[n // 2] if n % 2 else selected[n // 2 - 1] + selected[n // 2]
    return {"a_pre": (doubled + 1) // 2, "a_pre_median": doubled / 2.0,
            "a_pre_n": n, "a_pre_source": "received_initial_median"}


def record(rows, observation, k, u):
    if observation is None or not observation["first_large_seen"] or observation["total"] == 0:
        return False
    if type(k) is not int or not 1 <= k <= 4:
        return False
    rows.append({"k": k, "u": uplink(u), "bytes": observation["total"], "source": observation["source"]})
    del rows[:-HISTORY_MAX]
    return True
