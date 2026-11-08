from collections import Counter, defaultdict
from copy import deepcopy
import math

from scipy.stats import t

from . import arms, report


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _mean(values):
    return math.fsum(values) / len(values) if values else None


def interval(values):
    values = list(values)
    if any(not _number(value) for value in values):
        raise ValueError("구간 입력은 유한수여야 한다")
    count = len(values)
    mean = _mean(values)
    result = {"mean": mean, "ci95": None, "halfwidth": None, "n": count,
              "df": count - 1 if count else None, "status": "표본 부족"}
    if count < 2:
        return result
    variance = math.fsum((value - mean) ** 2 for value in values) / (count - 1)
    halfwidth = float(t.ppf(0.975, count - 1)) * math.sqrt(variance / count)
    result.update(ci95=[mean - halfwidth, mean + halfwidth], halfwidth=halfwidth,
                  status="확인")
    return result


def _prepared(plan, task, units, payloads):
    expected = arms.iter_units(plan, [task])
    if len(units) != len(payloads) or len(units) != len(expected):
        raise ValueError("계획 단위 또는 payload가 누락됐다")
    supplied = {}
    for unit, payload in zip(units, payloads):
        key = unit["key"]
        if key in supplied:
            raise ValueError("통계 입력 단위가 중복됐다")
        supplied[key] = (unit, payload)
    result = []
    for unit in expected:
        if unit["key"] not in supplied or supplied[unit["key"]][0] != unit:
            raise ValueError("통계 입력 단위가 계획과 다르다")
        payload = supplied[unit["key"]][1]
        rows = payload.get("rows")
        if not isinstance(rows, list) or len(rows) != unit["rows_expected"]:
            raise ValueError("통계 입력 행 수가 계획과 다르다")
        if (any(type(row.get("i")) is not int for row in rows)
                or {row["i"] for row in rows} != set(range(len(rows)))):
            raise ValueError("통계 입력 연결 순번이 계획과 다르다")
        prepared = []
        for original_index, row in enumerate(rows):
            if (type(row.get("ok")) is not bool or not _number(row.get("ms"))
                    or row["ms"] < 0):
                raise ValueError("통계 입력 HCT 또는 성공 여부가 잘못됐다")
            index = row["i"]
            prepared.append({"row": row, "original_index": original_index,
                             "hct": row["ms"] if row["ok"] else plan["statistics"]["failure_hct_ms"],
                             "one_rtt": arms.one_rtt(row, unit["profile"]),
                             "burnin": index < unit["burnin_connections"],
                             "warmup": index < unit["warmup_connections"],
                             "measured": index >= unit["burnin_connections"] + unit["warmup_connections"]})
        prepared.sort(key=lambda item: item["row"]["i"])
        result.append({"unit": unit, "payload": payload, "rows": prepared})
    return result


def _selected(groups, selector):
    return [(group, [item for item in group["rows"] if selector(group, item)])
            for group in groups]


def _cost(selected):
    total = 0
    count = 0
    sources = set()
    missing = []
    for group, rows in selected:
        if not rows:
            continue
        count += len(rows)
        payload = group["payload"]
        if len(rows) == len(group["rows"]):
            value = (payload.get("server_delta") or {}).get("bytes_in")
            source = "server_delta.bytes_in"
        else:
            server = payload.get("collection", {}).get("server", {})
            conns = {conn["key"]: conn for conn in server.get("conns") or []}
            matches = {item["row_index"]: item["conn_key"]
                       for item in server.get("scid_matching", {}).get("matches", [])}
            values = []
            for item in rows:
                key = matches.get(item["original_index"])
                value = conns.get(key, {}).get("rx_bytes")
                if type(value) is not int or value < 0:
                    values = None
                    break
                values.append(value)
            value = sum(values) if values is not None else None
            source = "conn_log.rx_bytes"
        if type(value) is not int or value < 0:
            missing.append(group["unit"]["key"])
        else:
            total += value
            sources.add(source)
    available = count > 0 and not missing
    return {"bytes_in": total if available else None, "n_rows": count,
            "bytes_per_conn": total / count if available else None,
            "source": "+".join(sorted(sources)) if available else None,
            "status": "확인" if available else "미확인", "missing_units": missing,
            "meaning": "서버 계수의 서버 수신량, 클라이언트 반환 행당"}


def _sample_key(group, sample_unit):
    unit = group["unit"]
    if sample_unit == "trajectory":
        return (unit["trajectory"],)
    return (unit["trajectory"], unit["phase"], unit["block"])


def _metrics(selected, sample_unit):
    buckets = defaultdict(list)
    for group, rows in selected:
        if rows:
            buckets[_sample_key(group, sample_unit)].append((group, rows))
    result = {}
    for key, items in sorted(buckets.items()):
        rows = [row for _, selected_rows in items for row in selected_rows]
        result[key] = {"hct": _mean([row["hct"] for row in rows]),
                       "one_rtt": sum(row["one_rtt"] for row in rows) / len(rows),
                       "server_cost": _cost(items)["bytes_per_conn"]}
    return result


def _field_summary(rows, field):
    values = [item["row"].get(field) for item in rows]
    valid = [value for value in values if _number(value)]
    return {"sum": math.fsum(valid) if valid else None, "mean": _mean(valid),
            "samples": len(valid), "missing": len(rows) - len(valid)}


def _action(row):
    value = row.get("action")
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    return ",".join(map(str, value)) if all(type(item) is int for item in value) else None


def _pto(rows):
    primary = []
    auxiliary = []
    mismatch = 0
    comparable = 0
    invalid_scope = 0
    for item in rows:
        row = item["row"]
        observation = row.get("observation")
        count = observation.get("pto_count") if isinstance(observation, dict) else None
        scope_valid = (isinstance(observation, dict) and observation.get("tracer") == "memory_qlog"
                       and observation.get("pto_count_scope") == "qlog_loss_timer_expired_lower_bound")
        invalid_scope += not scope_valid
        first = row.get("first_flight_datagrams")
        initial = row.get("initial_datagrams")
        event = count >= 1 if scope_valid and type(count) is int and count >= 0 else None
        other = initial > first + 1 if (type(initial) is int and type(first) is int
                                       and initial >= 0 and first >= 0) else None
        primary.append(event)
        auxiliary.append(other)
        if event is not None and other is not None:
            comparable += 1
            mismatch += event != other
    def summary(values):
        valid = [value for value in values if value is not None]
        return {"events": sum(valid), "n_total": len(values), "n_valid": len(valid),
                "missing": len(values) - len(valid),
                "rate": sum(valid) / len(valid) if valid else None,
                "denominator": "유효 PTO 관측 수, 누락은 missing에 별도 기록"}
    return {"primary": {**summary(primary), "scope_invalid": invalid_scope,
                        "tracer": "memory_qlog", "count_scope": "qlog_loss_timer_expired_lower_bound"},
            "auxiliary": summary(auxiliary),
            "definition_mismatch": mismatch, "definition_comparable": comparable}


def _scope(groups, selector, sample_unit, *, pto=False):
    selected = _selected(groups, selector)
    rows = [item for _, values in selected for item in values]
    metrics = _metrics(selected, sample_unit)
    hct = interval([value["hct"] for value in metrics.values()])
    ok_values = [item["row"]["ms"] for item in rows if item["row"]["ok"]]
    p_values = [item["row"]["p_mean"] for item in rows if _number(item["row"].get("p_mean"))]
    actions = [_action(item["row"]) for item in rows]
    count = len(rows)
    hct_values = sorted(item["hct"] for item in rows)
    result = {"n_rows": count, "hct": hct, "inference_unit": sample_unit,
              "hct_mean_ms": _mean(hct_values),
              "success_hct_mean_ms": _mean(ok_values), "success_rows": len(ok_values),
              "failed_rows": count - len(ok_values),
              "failure_rate": (count - len(ok_values)) / count if count else None,
              "hct_p99_ms": hct_values[math.ceil(0.99 * count) - 1] if count else None,
              "hct_p99_method": "nearest rank, 실패 HCT 포함",
              "one_rtt_rate": sum(item["one_rtt"] for item in rows) / count if count else None,
              "server_cost": _cost(selected),
              "first_flight_bytes_mean": _field_summary(rows, "first_flight_bytes")["mean"],
              "first_flight_parity_bytes_mean": _field_summary(rows, "first_flight_parity_bytes")["mean"],
              "first_flight_extra_bytes_mean": _mean([item["row"]["extra_sent"]["first_bytes"]
                  for item in rows if isinstance(item["row"].get("extra_sent"), dict)
                  and _number(item["row"]["extra_sent"].get("first_bytes"))]),
              "action_hist": dict(sorted(Counter(value for value in actions if value is not None).items())),
              "action_missing": sum(value is None for value in actions),
              "p_mean": _mean(p_values), "p_mean_samples": len(p_values),
              "client_diagnostics": {field: _field_summary(rows, field)
                                     for field in ("bytes_parity", "parity_sent")},
              "mean_idle_ms": None, "idle_status": "미확인"}
    if pto:
        result["pto"] = _pto(rows)
    return result


def _all(group, item):
    return True


def _primary(group, item):
    return item["measured"]


def _burnin(group, item):
    return item["burnin"]


def _loss_selector(loss, base):
    return lambda group, item: ((group["unit"]["loss_c2s_pct"], group["unit"]["loss_s2c_pct"]) == loss
                                and base(group, item))


def _paired(left, right, selector, sample_unit):
    x = _metrics(_selected(left, selector), sample_unit)
    y = _metrics(_selected(right, selector), sample_unit)
    if x.keys() != y.keys():
        raise ValueError("대조의 짝 단위가 누락됐다")
    result = {}
    for name, output in (("hct", "hct"), ("one_rtt", "one_rtt_difference"),
                         ("server_cost", "server_bytes_in_per_conn_difference")):
        missing = [key for key in x if x[key][name] is None or y[key][name] is None]
        value = interval([x[key][name] - y[key][name] for key in x]) if not missing else interval([])
        value["missing_pairs"] = len(missing)
        result[output] = value
    result["n_pairs"] = len(x)
    result["inference_unit"] = sample_unit
    return result


def _first_flight_difference(plan, left, right):
    samples = {}
    for name, groups in (("x", left), ("y", right)):
        values = {"original": [], "extra": [], "total": []}
        missing = Counter()
        for group, rows in _selected(groups, _primary):
            padding = "-pad-junk" in plan["arms"][group["unit"]["arm"]]["client_flags"]
            for item in rows:
                row = item["row"]
                original = row.get("first_flight_bytes")
                extra = row.get("extra_sent", {}).get("first_bytes") if padding else row.get("first_flight_parity_bytes")
                original = original if _number(original) and original >= 0 else None
                extra = extra if _number(extra) and extra >= 0 else None
                for field, value in (("original", original), ("extra", extra),
                                     ("total", original + extra if original is not None and extra is not None else None)):
                    if value is None:
                        missing[field] += 1
                    else:
                        values[field].append(value)
        samples[name] = {"means": {field: _mean(items) if not missing[field] else None
                                    for field, items in values.items()},
                         "missing_rows": dict(missing)}
    result = {"unit": "B", "scope": "primary", "missing_rows": {
              name: item["missing_rows"] for name, item in samples.items()},
              "meaning": "first flight 행 계수 평균의 x-y, 동일 바이트 판정 없음"}
    for field in ("original", "extra", "total"):
        x, y = samples["x"]["means"][field], samples["y"]["means"][field]
        result[field + "_bytes"] = x - y if x is not None and y is not None else None
    return result


def _judgment(value, plan, task, profile, loss, m1_result, *, precision=False):
    aa = report.aa_ruler(m1_result, task=task, profile=profile, loss_pct=loss,
                         statistics=plan["statistics"]) if loss is not None else {
                             "applies": False, "ruler_ms": None, "note": "A/A 없음"}
    value["aa"] = aa
    hct = value["hct"]
    ci = hct["ci95"]
    reasons = []
    contains_zero = ci is not None and ci[0] <= 0 <= ci[1]
    if ci is None:
        reasons.append("표본 부족")
    if contains_zero:
        reasons.append("95% 구간이 0을 포함")
    if aa["applies"] and hct["mean"] is not None and abs(hct["mean"]) < aa["ruler_ms"]:
        reasons.append("차이가 A/A 자보다 작음")
    if precision and hct["halfwidth"] is not None and abs(hct["mean"]) < hct["halfwidth"]:
        reasons.append("차이가 실제 구간 반폭보다 작음")
    value.update(ci95_contains_zero=contains_zero if ci is not None else None,
                 inference_status="판정불능" if reasons else "차이 관측",
                 inference_reasons=reasons)
    return value


def _arm_summary(plan, task, groups):
    unit = groups[0]["unit"]
    arm = plan["arms"][unit["arm"]]
    sample_unit = "trajectory" if task == "X6" and not unit["additional"] else "block"
    losses = sorted({(group["unit"]["loss_c2s_pct"], group["unit"]["loss_s2c_pct"]) for group in groups})
    servers = [group["payload"].get("collection", {}).get("server", {}) for group in groups]
    parse_values = [server.get("fec_parse_fail") for server in servers]
    parse_available = all(type(value) is int and value >= 0 for value in parse_values)
    result = {"arm": unit["arm"], "binary": arm["binary"],
              "client_parity_count_unreliable": arm.get("client_parity_count_unreliable", False),
              "primary": _scope(groups, _primary, sample_unit, pto=task == "X9"),
              "all": _scope(groups, _all, sample_unit),
              "burnin": _scope(groups, _burnin, sample_unit),
              "by_loss": [{"loss_c2s_pct": loss[0], "loss_s2c_pct": loss[1],
                           "all": _scope(groups, _loss_selector(loss, _all), sample_unit),
                           "primary": _scope(groups, _loss_selector(loss, _primary), sample_unit)}
                          for loss in losses],
              "fec_parse_fail": sum(parse_values) if parse_available else None,
              "fec_parse_fail_status": "확인" if parse_available else "미확인",
              "g2auto_ips_used_ge_1395": sum(_number(item["row"].get("ips_used"))
                  and item["row"]["ips_used"] >= 1395 for group in groups for item in group["rows"])
                  if unit["arm"] == "g2auto" else None,
              "server_delta": {field: sum(group["payload"]["server_delta"][field] for group in groups)
                  if all(type(group["payload"].get("server_delta", {}).get(field)) is int for group in groups)
                  else None for field in ("bytes_in", "parities", "recovered", "credit_parities")},
              "conn_sources": sorted({server.get("conn_source", "미확인") for server in servers}),
              "not_accepted": sum(server["not_accepted"] for server in servers)
                  if all(type(server.get("not_accepted")) is int for server in servers) else None,
              "reweighted_1_1": None}
    if task == "X6" and len(losses) == 2:
        samples = defaultdict(list)
        for loss in losses:
            metrics = _metrics(_selected(groups, _loss_selector(loss, _primary)), "trajectory")
            for key, value in metrics.items():
                samples[key].append(value)
        if any(len(values) != 2 for values in samples.values()):
            raise ValueError("1:1 재계산의 손실 층이 누락됐다")
        result["reweighted_1_1"] = {"hct": interval([_mean([value["hct"] for value in values])
            for _, values in sorted(samples.items())]), "inference_unit": "trajectory",
            "losses": [list(loss) for loss in losses], "weights": [0.5, 0.5],
            "aa": "A/A 없음"}
    return result


def _x6_contrasts(plan, cell, grouped, m1_result):
    result = []
    losses = sorted({(group["unit"]["loss_c2s_pct"], group["unit"]["loss_s2c_pct"])
                     for group in next(iter(grouped.values()))})
    scopes = [("primary", _primary, None), ("all", _all, None), ("burnin", _burnin, None)]
    scopes += [(f"loss_{loss[0]:g}_{loss[1]:g}", _loss_selector(loss, _primary), loss[0]) for loss in losses]
    scopes += [(f"all_loss_{loss[0]:g}_{loss[1]:g}", _loss_selector(loss, _all), loss[0]) for loss in losses]
    for contrast in plan["tasks"]["X6"]["contrasts"]:
        left, right = grouped[contrast["x"]], grouped[contrast["y"]]
        for scope, selector, loss in scopes:
            value = {**contrast, "scope": scope, **_paired(left, right, selector, "trajectory")}
            result.append(_judgment(value, plan, "X6", cell["profile"], loss,
                                    m1_result, precision=True))
        if len(losses) == 2:
            x = [_metrics(_selected(left, _loss_selector(loss, _primary)), "trajectory") for loss in losses]
            y = [_metrics(_selected(right, _loss_selector(loss, _primary)), "trajectory") for loss in losses]
            keys = x[0].keys()
            if any(mapping.keys() != keys for mapping in x + y):
                raise ValueError("1:1 대조의 궤적 또는 층이 누락됐다")
            value = {**contrast, "scope": "reweighted_1_1", "n_pairs": len(keys),
                     "inference_unit": "trajectory", "weights": [0.5, 0.5]}
            for metric, output in (("hct", "hct"), ("one_rtt", "one_rtt_difference"),
                                   ("server_cost", "server_bytes_in_per_conn_difference")):
                missing = any(mapping[key][metric] is None for mapping in x + y for key in keys)
                value[output] = interval([]) if missing else interval([
                    _mean([x[index][key][metric] - y[index][key][metric] for index in range(2)]) for key in keys])
            result.append(_judgment(value, plan, "X6", cell["profile"], None,
                                    m1_result, precision=True))
    return result


def _x9_contrast(grouped):
    result = {}
    for definition in ("primary", "auxiliary"):
        values = {}
        for arm in ("mlkem_off", "x25519_off"):
            values[arm] = {_sample_key(group, "block"): _pto(selected)[definition]
                           for group, selected in _selected(grouped[arm], _primary)}
        x, y = values["mlkem_off"], values["x25519_off"]
        if x.keys() != y.keys():
            raise ValueError("PTO 대조의 짝 블록이 누락됐다")
        missing = sum(x[key]["missing"] > 0 or y[key]["missing"] > 0
                      or x[key]["rate"] is None or y[key]["rate"] is None for key in x)
        result[definition] = interval([x[key]["rate"] - y[key]["rate"] for key in x]) if not missing else interval([])
        result[definition].update(missing_blocks=missing, n_blocks=len(x),
                                  effect_sign="MLKEM-x25519", unit="비율")
    return result


def summarize(plan, task, units, payloads, m1_result=None, *, env=None):
    prepared = _prepared(plan, task, units, payloads)
    by_cell = defaultdict(lambda: defaultdict(list))
    for group in prepared:
        by_cell[group["unit"]["cell"]][group["unit"]["arm"]].append(group)
    result = {"cells": [], "checks": {}, "inference_status": "기술통계"}
    specs = plan["tasks"][task]["cells"] + plan["tasks"][task].get("additional_cells", [])
    for cell in specs:
        grouped = by_cell[cell["id"]]
        additional = next(iter(grouped.values()))[0]["unit"]["additional"]
        output = {"cell": cell["id"], "profile": cell["profile"], "additional": additional,
                  "arms": [_arm_summary(plan, task, grouped[arm]) for arm in cell["arms"]],
                  "contrasts": []}
        if task == "X1":
            contrasts = [value for value in plan["tasks"][task]["contrasts"] if value["cell"] == cell["id"]]
            diagnostic = plan["tasks"][task]["diagnostic_contrast"]
            if diagnostic["x"] in grouped and diagnostic["y"] in grouped:
                contrasts += [{"id": "trailing_junk_minus_parity", **diagnostic, "diagnostic": True}]
            for contrast in contrasts:
                value = {**contrast, "scope": "primary", **_paired(grouped[contrast["x"]],
                         grouped[contrast["y"]], _primary, "block")}
                value["first_flight_difference"] = _first_flight_difference(
                    plan, grouped[contrast["x"]], grouped[contrast["y"]])
                output["contrasts"].append(_judgment(value, plan, task, cell["profile"],
                    cell["phases"][0]["loss_c2s_pct"], m1_result))
        elif task == "X2":
            for contrast in plan["tasks"][task]["contrasts"]:
                if contrast["cell"] != cell["id"]:
                    continue
                value = {**contrast, "scope": "primary", "independent_trajectory_claim": False,
                         **_paired(grouped[contrast["x"]], grouped[contrast["y"]], _primary, "block")}
                output["contrasts"].append(_judgment(value, plan, task, cell["profile"],
                    cell["phases"][0]["loss_c2s_pct"], m1_result))
        elif task == "X6" and not additional:
            output["contrasts"] = _x6_contrasts(plan, cell, grouped, m1_result)
        elif task == "X6":
            for name in ("comparator", "additional_comparator"):
                target = cell[name]
                left = next(iter(grouped.values()))
                right = [group for group in by_cell[target["cell"]][target["arm"]]
                         if group["unit"]["trajectory"] == target["trajectory"]]
                value = {"id": left[0]["unit"]["arm"] + "_minus_" + target["arm"],
                         "x": left[0]["unit"]["arm"], "y": target["arm"], "scope": "primary",
                         "independent_trajectory_claim": False, **_paired(left, right, _primary, "block")}
                output["contrasts"].append(_judgment(value, plan, task, cell["profile"], None, m1_result))
        elif task == "X9":
            output["pto_contrast"] = _x9_contrast(grouped)
            for arm in output["arms"]:
                pto = arm["primary"]["pto"]["primary"]
                result["checks"][cell["id"] + ":" + arm["arm"] + ":pto_denominator"] = (
                    "pass" if pto["n_valid"] >= cell["n_measured_accept_min"] else "fail")
                for definition in ("primary", "auxiliary"):
                    result["checks"][cell["id"] + ":" + arm["arm"] + ":pto_" + definition + "_fields"] = (
                        "missing" if arm["primary"]["pto"][definition]["missing"] else "pass")
                arm["warmup_excluded"] = arm["all"]["n_rows"] - arm["primary"]["n_rows"]
                arm["n_measured_planned"] = cell["measured_per_arm"]
        result["cells"].append(output)
    if task == "M1":
        cell = specs[0]
        grouped = by_cell[cell["id"]]
        result["contrasts"] = {}
        for name, contrast in plan["tasks"][task]["contrasts"].items():
            value = _paired(grouped[contrast["x"]], grouped[contrast["y"]], _primary, "block")
            result["contrasts"][name] = {**contrast, **value["hct"], "n_blocks": value["n_pairs"]}
        result["n_blocks"] = min(value["n_blocks"] for value in result["contrasts"].values())
        result["checks"]["n_blocks"] = "pass" if result["n_blocks"] >= plan["tasks"][task]["n_blocks_required"] else "fail"
        contrast = result["contrasts"][plan["statistics"]["m1_aa"]["contrast"]]
        aa = report.m1_aa(contrast, plan["statistics"]) if contrast["ci95"] is not None else {
            "inference_status": "판정불능", "ruler_ms": None}
        result["aa"] = aa
        result["inference_status"] = aa["inference_status"]
        result["status"] = aa["inference_status"]
        reference = plan["statistics"]["sealed_drift"]
        mean = _scope(grouped[reference["arm"]], _primary, "block")["hct"]["mean"]
        result["a_vs_sealed"] = {"current_mean_ms": mean, "sealed_mean_ms": reference["value_ms"],
            "delta_ms": mean - reference["value_ms"], "source": reference["source"],
            "exploratory": reference["exploratory"], "sealed_kernel": reference["sealed_kernel"],
            "kernel": (env or {}).get("uname_r")}
    if task == "X9":
        result["power"] = deepcopy(plan["tasks"][task]["power"])
    if task == "X6":
        result["idle_comparison"] = {"status": "미확인", "difference_ms": None,
            "reason": "절대 연결 시각 부재, 실제 유휴 차이 5 ms 기준을 판정할 수 없다"}
    return result
