from collections import defaultdict
import math
import re

from scipy.stats import binom

from . import arms, blocks, report


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("음수가 아닌 유한수가 필요하다")
    return value


def _count(value):
    if type(value) is not int or value < 0:
        raise ValueError("음수가 아닌 정수가 필요하다")
    return value


def _merge(values):
    if not values or "missing" in values:
        return "missing"
    return "fail" if "fail" in values else "pass"


def _equal(value, expected):
    return type(value) in (int, float) and math.isfinite(value) and value == expected


def _parity_lengths(row):
    total = _count(row["parity_sent"])
    size = _count(row["bytes_parity"])
    if total == 0:
        if size:
            raise ValueError("parity 수와 바이트가 맞지 않는다")
        return []
    trace = row["flight_trace"]
    if _count(trace["omitted"]) != 0:
        raise ValueError("flight trace 생략으로 parity 전체를 확인하지 못했다")
    lengths = []
    counts = sizes = 0
    for record in trace["records"]:
        count = _count(record["parity_sent"])
        amount = _count(record["parity_bytes"])
        if count:
            if amount <= 0 or amount % count:
                raise ValueError("flight parity 크기가 정수 길이가 아니다")
            lengths.append(amount // count)
        elif amount:
            raise ValueError("flight parity 수와 바이트가 맞지 않는다")
        counts += count
        sizes += amount
    if counts != total or sizes != size:
        raise ValueError("행과 flight parity 총계가 다르다")
    return lengths


def _qdisc_settings(item):
    if type(item["returncode"]) is not int or item["returncode"] != 0:
        raise ValueError("tc 종료 코드가 0이 아니다")
    matches = re.findall(r"^qdisc netem .*\broot\b[^\r\n]*", item["stdout"], re.M)
    if len(matches) != 1:
        raise ValueError("root netem 한 개를 확인하지 못했다")
    line = matches[0]
    delay = re.search(r"\bdelay\s+([0-9.]+)(us|ms|s)\b", line)
    rate = re.search(r"\brate\s+([0-9.]+)(bit|Kbit|Mbit|Gbit)\b", line, re.I)
    loss = re.search(r"\bloss\s+(?:random\s+)?([0-9.]+)%", line)
    if " loss " in line and loss is None:
        raise ValueError("독립 손실률을 읽지 못했다")
    return {"delay_ms": float(delay[1]) * {"us": .001, "ms": 1, "s": 1000}[delay[2]] if delay else 0,
            "rate_mbps": float(rate[1]) * {"bit": 1e-6, "kbit": .001, "mbit": 1, "gbit": 1000}[rate[2].lower()] if rate else 0,
            "loss_pct": float(loss[1]) if loss else 0}


def _tc_counts(item):
    _qdisc_settings(item)
    matches = re.findall(r"\bSent\s+\d+\s+bytes\s+(\d+)\s+pkt\s+\(dropped\s+(\d+),", item["stdout"])
    if len(matches) != 1:
        raise ValueError("tc Sent와 dropped 계수를 읽지 못했다")
    return tuple(int(value) for value in matches[0])


def _c1_path(entries):
    state = defaultdict(bool)
    valid, after_count = True, 0
    for unit, payload in sorted(entries, key=lambda entry: (entry[0]["trajectory"], entry[0]["connection_offset"])):
        for row in sorted(payload["rows"], key=lambda item: item["i"]):
            received = row["feedback_wait_received"]
            if type(received) is not bool or row["policy_path"] not in ("none", "c1"):
                raise ValueError("C1 수신 또는 정책 경로가 없다")
            if state[unit["trajectory"]]:
                after_count += 1
                valid = valid and row["policy_path"] == "c1"
            state[unit["trajectory"]] = state[unit["trajectory"]] or received
    return valid, {"rows_after_first_receipt": after_count}


def _cache_seen(payload, expected):
    command = payload["commands"]["client"]
    if command.count("-addr") != 1:
        raise ValueError("cache 목적지 인자가 유일하지 않다")
    address = command[command.index("-addr") + 1]
    raw = blocks.snapshot_bytes(payload["cache_after"])
    if raw is None:
        raise ValueError("궤적 마지막 cache가 없다")
    value = report.validate_cache_bytes(raw, "gen33", address)
    seen = value["dests"][address]["state"]["c1_seen"]
    return seen is expected, {"c1_seen": seen, "expected": expected}


def _netem_config(unit, payload, event_groups):
    selected = event_groups[(unit["key"], payload.get("attempt"))]
    if len(selected) != 1:
        raise ValueError("완료 attempt의 netem 기록 한 개가 필요하다")
    event = selected[0]
    request = event["requested"]
    expected_request = {"one_way_ms": unit["profile"]["rtt_ms"] / 2,
                        "loss_c2s": unit["loss_c2s_pct"], "loss_s2c": unit["loss_s2c_pct"],
                        "burst_len": 1, "rate_up_mbit": unit["profile"]["netem_uplink_mbps"],
                        "rate_down_mbit": 0}
    valid = all(_equal(request[key], value) for key, value in expected_request.items())
    actual = {}
    for direction, rate, loss in (("c2s", unit["profile"]["netem_uplink_mbps"], unit["loss_c2s_pct"]),
                                  ("s2c", 0, unit["loss_s2c_pct"])):
        expected = {"delay_ms": unit["profile"]["rtt_ms"] / 2, "rate_mbps": rate, "loss_pct": loss}
        actual[direction] = {}
        for source, collection in (("configured", event["qdisc"]),
                                   ("before", payload["tc_before"]),
                                   ("after", payload["tc_after"])):
            values = _qdisc_settings(collection[direction])
            actual[direction][source] = values
            valid = valid and values == expected
    return valid, {"actual": actual, "requested": request}


def _realized_loss(entries, direction, nominal, confidence):
    sent = dropped = 0
    for unit, payload in entries:
        before = _tc_counts(payload["tc_before"][direction])
        after = _tc_counts(payload["tc_after"][direction])
        if any(last < first for first, last in zip(before, after)):
            raise ValueError("tc 계수가 단위 안에서 감소했다")
        sent += after[0] - before[0]
        dropped += after[1] - before[1]
    total = sent + dropped
    if total <= 0:
        raise ValueError("실현 손실 분모가 없다")
    p = nominal / 100
    tail = (1 - confidence) / 2
    low, high = [int(binom.ppf(value, total, p)) for value in (tail, 1 - tail)]
    return low <= dropped <= high, {"sent": sent, "dropped": dropped, "attempts": total,
                                   "nominal_loss_pct": p * 100, "prediction_interval": [low, high],
                                   "confidence": confidence}


def _success_rate(plan, rows):
    if not rows or any(type(row["ok"]) is not bool for row in rows):
        raise ValueError("성공률 분모나 ok가 없다")
    rate = sum(row["ok"] for row in rows) / len(rows)
    return rate >= plan["smoke_checks"]["success_rate_min"], {"rate": rate, "n": len(rows)}


def _policy_uplink(unit, rows):
    expected = unit["profile"]["policy_uplink_mbps"]
    values = sorted({_number(row["policy_uplink_mbps"]) for row in rows})
    return values == [expected], {"values": values, "expected": expected}


MEASURED_PLAN_IDS = frozenset({"final_bundle_v1"})


def summarize_checks(plan, task, units, payloads, observed, events=(), extended=None):
    if len(units) != len(payloads) or not units:
        raise ValueError("검사할 단위와 payload가 일치해야 한다")
    if extended is None:
        extended = plan.get("plan_id") not in MEASURED_PLAN_IDS
    details = defaultdict(list)

    def add(name, identity, valid=None, **values):
        status = "missing" if valid is None else "pass" if valid else "fail"
        details[name].append({**identity, "status": status, **values})

    def attempt(name, identity, operation):
        try:
            valid, values = operation()
            add(name, identity, valid, **values)
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            add(name, identity, error=str(exc))

    groups = defaultdict(list)
    cells = defaultdict(list)
    event_groups = defaultdict(list)
    for event in events:
        if event.get("event") == "netem":
            event_groups[(event.get("key"), event.get("data", {}).get("attempt"))].append(event["data"])
    for unit, payload in zip(units, payloads):
        identity = {"unit": unit["key"], "cell": unit["cell"], "arm": unit["arm"]}
        arm = plan["arms"][unit["arm"]]
        rows = payload["rows"]
        groups[(unit["cell"], unit["arm"])].append((unit, payload))
        cells[unit["cell"]].append((unit, payload))
        for name, status in payload.get("checks", {}).items():
            add(name, identity, None if status == "missing" else status == "pass")
        attempt("process_rc", identity, lambda: (
            type(payload["client_rc"]) is int and type(payload["server"]["returncode"]) is int
            and payload["client_rc"] == payload["server"]["returncode"] == plan["smoke_checks"]["process_rc"],
            {"client_rc": payload["client_rc"], "server_rc": payload["server"]["returncode"]}))
        if arms.client_family(plan, arm) == "gen33":
            def w_bound():
                valid = True
                lengths = []
                for row in rows:
                    ips, count = _count(row["ips_eff"]), _count(row["m_used"])
                    valid = valid and ips >= plan["common"]["w_base_bytes"] and (count == 0 or ips <= 1401)
                    lengths.extend(_parity_lengths(row))
                return valid and all(size <= plan["smoke_checks"]["gen33_parity_max_bytes"] for size in lengths), {
                    "rows": len(rows), "maximum_parity_datagram_bytes": max(lengths) if lengths else None,
                    "parity_length_source": "flight parity_bytes/parity_sent, 같은 flight의 동일 직렬화 길이"}
            attempt("w_bound", identity, w_bound)
            if extended and arm["kind"] == "auto3":
                attempt("policy_uplink", identity, lambda: _policy_uplink(unit, rows))
        if extended or task == "M0":
            attempt("netem_config", identity, lambda: _netem_config(unit, payload, event_groups))
        if task != "M0":
            continue
        attempt("recover_crc_fail", identity, lambda: (
            _count(payload["server"]["stats"]["recover_crc_fail"]) == plan["smoke_checks"]["recover_crc_fail"],
            {"recover_crc_fail": payload["server"]["stats"]["recover_crc_fail"]}))

    for cell, entries in sorted(cells.items()):
        if task == "M1":
            add("server_uniform", {"cell": cell}, True, exception="계획된 M1 세대별 서버 대조")
        else:
            def server_uniform():
                certs, servers = set(), set()
                valid = True
                for unit, payload in entries:
                    cert = payload["server"]["certificate"]
                    digest = cert["der_sha256"]
                    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                        raise ValueError("DER SHA가 없다")
                    certs.add(digest)
                    valid = valid and _count(cert["der_bytes"]) == unit["profile"]["certsize"]
                    for row in payload["rows"]:
                        digest = row["server_binary_sha256"]
                        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                            raise ValueError("서버 SHA가 없다")
                        servers.add(digest)
                        valid = valid and digest == plan["binaries"]["gen33"]["sha256"]
                return valid and len(certs) == len(servers) == 1, {"der_sha256": sorted(certs), "server_binary_sha256": sorted(servers)}
            attempt("server_uniform", {"cell": cell}, server_uniform)
        confidence = plan["smoke_checks"]["realized_loss"]["confidence"]
        if task == "M0":
            def realized_loss():
                losses = {unit["loss_c2s_pct"] for unit, payload in entries}
                if len(losses) != 1:
                    raise ValueError("smoke 셀에 서로 다른 명목 손실률이 있다")
                return _realized_loss(entries, "c2s", next(iter(losses)), confidence)
            attempt("realized_loss", {"cell": cell}, realized_loss)
            continue
        if not extended:
            continue
        strata = defaultdict(list)
        for unit, payload in entries:
            strata[("c2s", unit["loss_c2s_pct"])].append((unit, payload))
            strata[("s2c", unit["loss_s2c_pct"])].append((unit, payload))
        for (direction, nominal), subset in sorted(strata.items()):
            attempt("realized_loss", {"cell": cell, "direction": direction, "loss_pct": nominal},
                    lambda: _realized_loss(subset, direction, nominal, confidence))

    if task == "M0":
        for (cell, arm_id), entries in sorted(groups.items()):
            identity = {"cell": cell, "arm": arm_id}
            arm = plan["arms"][arm_id]
            rows = [row for unit, payload in entries for row in payload["rows"]]
            attempt("success_rate", identity, lambda: _success_rate(plan, rows))
            if arm["kind"] == "fixed":
                def first_bytes():
                    values = [_count(row["first_flight_bytes"]) for row in rows]
                    return all(value == plan["smoke_checks"]["fixed_first_flight_bytes"] for value in values), {
                        "minimum": min(values), "maximum": max(values)}
                attempt("fixed_first_flight_bytes", identity, first_bytes)
                def parity_range():
                    values = [_count(row["extra_sent"]["first_bytes"] if "-pad-junk" in arm["client_flags"]
                                     else row["first_flight_parity_bytes"]) for row in rows]
                    width = max(values) - min(values)
                    return width <= plan["smoke_checks"]["fixed_parity_bytes_range_max"], {
                        "minimum": min(values), "maximum": max(values), "range": width,
                        "source": "extra_sent.first_bytes" if "-pad-junk" in arm["client_flags"] else "first_flight_parity_bytes"}
                attempt("fixed_extra_byte_range", identity, parity_range)
            if "-pad-junk" in arm["client_flags"]:
                attempt("pad_recovered", identity, lambda: (
                    sum(_count(payload["server"]["stats"]["recovered"]) for unit, payload in entries) == plan["smoke_checks"]["pad_server_recovered"],
                    {"recovered": sum(payload["server"]["stats"]["recovered"] for unit, payload in entries)}))
            if arms.client_family(plan, arm) != "gen33":
                attempt("frozen_parities", identity, lambda: (
                    sum(_count(payload["server"]["stats"]["parities"]) for unit, payload in entries) > 0,
                    {"parities": sum(payload["server"]["stats"]["parities"] for unit, payload in entries)}))
            recovery = plan["smoke_checks"]["recovered_positive"]
            if arm_id in recovery["arms"] and all(unit["loss_c2s_pct"] == recovery["loss_pct"] for unit, payload in entries):
                attempt("recovered_positive", identity, lambda: (
                    sum(_count(payload["server"]["stats"]["recovered"]) for unit, payload in entries) > 0,
                    {"recovered": sum(payload["server"]["stats"]["recovered"] for unit, payload in entries)}))
            if arm_id == "v33none" or arm.get("none_path_check"):
                attempt("none_path", identity, lambda: (
                    all(row["arrivals"]["src"] == row["policy_path"] == "none" for row in rows), {"n": len(rows)}))
            if arm.get("server_feedback", False):
                def c1_arrivals():
                    sources = [row["arrivals"]["src"] for row in rows]
                    if any(source not in ("none", "c1") for source in sources):
                        raise ValueError("arrivals src 형식 오류")
                    rate = sources.count("c1") / len(sources)
                    return rate >= plan["smoke_checks"]["c1_arrivals_fraction_min"], {"rate": rate, "n": len(sources)}
                attempt("c1_arrivals", identity, c1_arrivals)
                attempt("c1_path", identity, lambda: _c1_path(entries))
                def c1_wait():
                    matches = [item for item in observed if item["cell"] == cell and item["arm"] == arm_id]
                    if len(matches) != 1:
                        raise ValueError("셀 전체 C1 수신 집계가 없다")
                    counts = matches[0]["feedback_received"]
                    if _count(counts["missing"]):
                        raise ValueError("C1 수신 필드 누락")
                    total, received = _count(counts["n"]), _count(counts["received"])
                    if total != len(rows) or not total or received > total:
                        raise ValueError("C1 수신 분모 불일치")
                    rate = received / total
                    return rate >= plan["smoke_checks"]["c1_feedback_wait_received_fraction_min"], {"rate": rate, "n": total}
                attempt("c1_feedback_received", identity, c1_wait)
            mean_key = cell + ":" + arm_id
            if mean_key in plan["smoke_checks"]["hct_mean_ranges_ms"]:
                def hct_range():
                    values = [_number(row["ms"]) if row["ok"] else plan["common"]["timeout_s"] * 1000 for row in rows]
                    mean = math.fsum(values) / len(values)
                    low, high = plan["smoke_checks"]["hct_mean_ranges_ms"][mean_key]
                    return low <= mean <= high, {"mean": mean, "allowed": [low, high]}
                attempt("hct_mean_range", identity, hct_range)
    elif extended:
        for (cell, arm_id), entries in sorted(groups.items()):
            rows = [row for unit, payload in entries for row in payload["rows"]]
            attempt("success_rate", {"cell": cell, "arm": arm_id}, lambda: _success_rate(plan, rows))
    if task in ("X1", "X2", "X6"):
        for (cell, arm_id), entries in sorted(groups.items()):
            identity = {"cell": cell, "arm": arm_id}
            arm = plan["arms"][arm_id]
            if task == "X1":
                if "-pad-junk" in arm["client_flags"] or arm_id == "m4L3":
                    def recovery_check():
                        recovered = sum(_count(payload["server"]["stats"]["recovered"]) for unit, payload in entries)
                        return (recovered == 0 if "-pad-junk" in arm["client_flags"] else recovered > 0), {"recovered": recovered}
                    attempt("pad_recovered" if "-pad-junk" in arm["client_flags"] else "m4L3_recovered", identity, recovery_check)
            elif arms.client_family(plan, arm) == "gen33" and arm["kind"] == "auto3":
                expected = arm.get("server_feedback", False)
                if expected:
                    attempt("c1_path", identity, lambda: _c1_path(entries))
                else:
                    attempt("none_path", identity, lambda: (
                        all(row["arrivals"]["src"] == row["policy_path"] == "none"
                            for unit, payload in entries for row in payload["rows"]),
                        {"n": sum(len(payload["rows"]) for unit, payload in entries)}))
                trajectories = defaultdict(list)
                for unit, payload in entries:
                    trajectories[unit["trajectory"]].append((unit, payload))
                for trajectory, subset in sorted(trajectories.items()):
                    unit, payload = max(subset, key=lambda item: (item[0]["phase"], item[0]["block"]))
                    attempt("trajectory_end_c1_seen", {**identity, "trajectory": trajectory, "unit": unit["key"]},
                            lambda: _cache_seen(payload, expected))
    return {"checks": {name: _merge([item["status"] for item in values]) for name, values in sorted(details.items())},
            "details": dict(sorted(details.items()))}
