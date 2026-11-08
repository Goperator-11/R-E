from copy import deepcopy
import json
import math
from pathlib import Path
import re

from padfec3 import learn3

from . import arms


def capture_metadata(fields):
    if not isinstance(fields, dict):
        raise ValueError("측정 metadata 객체가 필요하다")
    result = deepcopy(fields)
    identity = {"label": "development", "confirmatory": False,
                "policy_version": learn3.POLICY_VERSION}
    for key, value in identity.items():
        if key in result and (result[key] != value or type(result[key]) is not type(value)):
            raise ValueError("측정 identity가 현재 정책과 다르다: " + key)
        result[key] = value
    return result


def result_metadata(stored):
    if (not isinstance(stored, dict) or stored.get("label") != "development"
            or stored.get("confirmatory") is not False
            or not isinstance(stored.get("policy_version"), str)
            or not stored["policy_version"]):
        raise ValueError("저장된 측정 identity가 없거나 올바르지 않다")
    return deepcopy(stored)


def _sha256(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("SHA256은 소문자 64자리 hex여야 한다")
    return value


def attach_row_provenance(row, *, plan_sha256, binary_sha256, srcsha,
                          server_binary_sha256=None, server_srcsha=None):
    values = {"plan_sha256": plan_sha256, "binary_sha256": binary_sha256,
              "srcsha": srcsha}
    if (server_binary_sha256 is None) != (server_srcsha is None):
        raise ValueError("서버 바이너리와 소스 지문은 함께 필요하다")
    if server_binary_sha256 is not None:
        values.update(server_binary_sha256=server_binary_sha256, server_srcsha=server_srcsha)
    result = deepcopy(row)
    for key, value in values.items():
        _sha256(value)
        if key in result and result[key] != value:
            raise ValueError("기존 행 provenance가 다르다: " + key)
        result[key] = value
    return result


def execution_status(*, has_data, checks):
    if type(has_data) is not bool or not isinstance(checks, dict):
        raise ValueError("자료 존재 여부와 checks 객체가 필요하다")
    if any(value not in ("pass", "fail", "missing") for value in checks.values()):
        raise ValueError("checks 값은 pass, fail, missing이어야 한다")
    if not has_data or "missing" in checks.values():
        return "자료 없음"
    if not checks:
        raise ValueError("자료 판정에는 비어 있지 않은 checks가 필요하다")
    return "판정 실패" if "fail" in checks.values() else "판정 통과"


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("유한수가 필요하다")
    return float(value)


def _interval(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("구간의 양 끝값이 필요하다")
    low, high = map(_number, value)
    if low > high:
        raise ValueError("구간의 하한이 상한보다 크다")
    return low, high


def m1_aa(contrast, statistics):
    mean = _number(contrast["mean"])
    low, high = _interval(contrast["ci95"])
    if not low <= mean <= high:
        raise ValueError("평균이 구간 밖에 있다")
    tolerance_low, tolerance_high = _interval(statistics["m1_aa"]["tolerance_ms"])
    inconclusive = low < tolerance_low or high > tolerance_high
    return {"inference_status": "판정불능" if inconclusive else "판정 가능",
            "mean": mean, "ci95": [low, high],
            "ruler_ms": abs(mean) + (high - low) / 2}


def validate_m1_result(value, plan, plan_sha256):
    result_metadata(value)
    if value.get("task") != "M1":
        raise ValueError("M1 과제의 결과가 필요하다")
    if value.get("policy_version") != plan["policy_version"]:
        raise ValueError("M1 정책 판본이 선택한 계획과 다르다")
    if _sha256(value.get("plan_sha256")) != _sha256(plan_sha256):
        raise ValueError("M1 계획 SHA가 선택한 계획과 다르다")
    if value.get("execution_status") != "판정 통과":
        raise ValueError("M1 실행 자료가 정상 완료되지 않았다")
    required = plan["tasks"]["M1"]["n_blocks_required"]
    count = value.get("n_blocks")
    if type(count) is not int or count < required:
        raise ValueError("M1 완료 블록 수가 계획보다 적다")
    contrasts = value.get("contrasts")
    if not isinstance(contrasts, dict):
        raise ValueError("M1 contrasts 객체가 없다")
    for name in plan["tasks"]["M1"]["primary"]:
        contrast = contrasts.get(name)
        if not isinstance(contrast, dict):
            raise ValueError("M1 필수 contrast가 없다: " + name)
        blocks = contrast.get("n_blocks")
        if type(blocks) is not int or blocks < required or blocks != count:
            raise ValueError("M1 짝 블록 수가 완료 블록 수와 다르다: " + name)
        mean = _number(contrast.get("mean"))
        low, high = _interval(contrast.get("ci95"))
        if not low <= mean <= high:
            raise ValueError("M1 contrast 평균이 구간 밖에 있다: " + name)
    aa = m1_aa(contrasts[plan["statistics"]["m1_aa"]["contrast"]], plan["statistics"])
    if value.get("status") != aa["inference_status"]:
        raise ValueError("M1 판정 상태가 C/D 구간과 다르다")
    drift = value.get("a_vs_sealed")
    if not isinstance(drift, dict):
        raise ValueError("M1 a_vs_sealed 객체가 없다")
    _number(drift.get("delta_ms"))
    return deepcopy(value)


def aa_ruler(m1_result, *, task, profile, loss_pct, statistics):
    rule = statistics["aa_ruler"]
    applies = (task in rule["tasks"] and profile == rule["profile"]
               and _number(loss_pct) == _number(rule["loss_pct"]))
    if not applies:
        return {"applies": False, "ruler_ms": None, "note": "A/A 없음"}
    if not isinstance(m1_result, dict):
        raise ValueError("이 셀의 A/A 자에는 M1 결과 JSON이 필요하다")
    result = m1_aa(m1_result["contrasts"][statistics["m1_aa"]["contrast"]], statistics)
    return {"applies": True, **result,
            "note": rule["drift_note_if_m1_inconclusive"]
            if result["inference_status"] == "판정불능" else None}


def valid_rtt_warning(valid, total, *, threshold=0.9):
    if (type(valid) is not int or type(total) is not int
            or not 0 <= valid <= total):
        raise ValueError("유효 RTT 수와 전체 수가 올바르지 않다")
    threshold = _number(threshold)
    if not 0 <= threshold <= 1:
        raise ValueError("유효 RTT 경고 문턱은 0~1이어야 한다")
    rate = valid / total if total else None
    return {"valid": valid, "total": total, "valid_rtt_rate": rate,
            "warning": rate is not None and rate < threshold}


def _conn_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("연결 JSON 중복 키: " + key)
        result[key] = value
    return result


def _conn_constant(value):
    raise ValueError("연결 JSON 비유한수: " + value)


def _count_field(mapping, key):
    value = mapping[key]
    if type(value) is not int or value < 0:
        raise ValueError("서버 계수는 음수가 아닌 정수여야 한다: " + key)
    return value


def _conn_record(value, *, logged):
    if not isinstance(value, dict):
        raise ValueError("연결 기록은 객체여야 한다")
    if not isinstance(value.get("key"), str) or not value["key"]:
        raise ValueError("연결 기록 key가 없다")
    for key in ("initial_dcid", "client_scid"):
        if not isinstance(value.get(key), str):
            raise ValueError("연결 기록 CID 문자열이 없다: " + key)
    for key in ("rx_bytes", "rx_orig_bytes", "rx_parity_bytes", "stack_bytes",
                "beff_stack", "beff_phys", "beff_orig", "beff_parity"):
        _count_field(value, key)
    for key in ("rx_dgrams", "rx_orig_n", "rx_parity_n", "recov_n", "credit_n",
                "tx_dgrams", "tx_bytes", "beff_credit", "first_rx_ns", "first_tx_ns",
                "handshake_complete_ns", "closed_ns", "peer_changes"):
        if key in value:
            _count_field(value, key)
    for key in ("tx_rx_timeline", "tx_sizes", "tx_ns"):
        if key in value:
            if value[key] is not None and (not isinstance(value[key], list)
                    or any(type(item) is not int or item < 0 for item in value[key])):
                raise ValueError("연결 기록 timeline 형식 오류: " + key)
    if logged:
        if value.get("reason") not in ("expired", "lru", "shutdown"):
            raise ValueError("연결 기록 reason 오류")
        _count_field(value, "logged_ns")
    return deepcopy(value)


def read_conn_log(path):
    raw = Path(path).read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise ValueError("conn-log 마지막 행이 끝나지 않았다")
    records = []
    keys = set()
    for index, line in enumerate(raw.splitlines(), 1):
        try:
            value = json.loads(line.decode("utf-8"), object_pairs_hook=_conn_object,
                               parse_constant=_conn_constant, parse_float=lambda item: _number(float(item)))
            record = _conn_record(value, logged=True)
            if record["key"] in keys:
                raise ValueError("conn-log 연결 key 중복")
        except (ValueError, KeyError) as exc:
            raise ValueError(f"conn-log {index}행 오류: {exc}") from exc
        keys.add(record["key"])
        records.append(record)
    return records


def match_client_scids(rows, conns):
    clients = {}
    servers = {}
    empty_rows = []
    empty_conns = []
    for index, row in enumerate(rows):
        scid = row.get("client_scid")
        if not isinstance(scid, str) or not scid:
            empty_rows.append(index)
        else:
            clients.setdefault(scid, []).append(index)
    for conn in conns:
        scid = conn["client_scid"]
        if not scid:
            empty_conns.append(conn["key"])
        else:
            servers.setdefault(scid, []).append(conn["key"])
    matches = [{"row_index": indexes[0], "client_scid": scid,
                "conn_key": servers[scid][0]}
               for scid, indexes in clients.items()
               if len(indexes) == 1 and len(servers.get(scid, [])) == 1]
    matches.sort(key=lambda item: item["row_index"])
    matched_rows = {item["row_index"] for item in matches}
    matched_conns = {item["conn_key"] for item in matches}
    return {"status": "확인", "client_rows": len(rows), "server_conns": len(conns),
            "matched": len(matches), "matched_rate": len(matches) / len(rows) if rows else None,
            "matches": matches, "empty_client_rows": empty_rows,
            "empty_server_keys": sorted(empty_conns),
            "duplicate_client_scids": {key: value for key, value in sorted(clients.items()) if len(value) > 1},
            "duplicate_server_scids": {key: sorted(value) for key, value in sorted(servers.items()) if len(value) > 1},
            "unmatched_client_rows": [index for index in range(len(rows)) if index not in matched_rows],
            "unmatched_server_keys": sorted(conn["key"] for conn in conns if conn["key"] not in matched_conns)}


def _frozen_certificate_observation(server):
    result = {"source": "server.stderr", "status": "미확인", "der_bytes": None,
              "reported_lines": None}
    try:
        path = server.get("stderr_path")
        if not isinstance(path, str) or not path:
            raise ValueError("동결 서버 stderr 경로 없음")
        raw = Path(path).read_bytes()
        lines = [line for line in raw.splitlines() if line.startswith(b"cert DER")]
        result["reported_lines"] = len(lines)
        if len(lines) != 1:
            raise ValueError("동결 서버 DER 크기 행이 하나가 아니다")
        match = re.fullmatch(rb"cert DER = ([1-9][0-9]*) bytes", lines[0])
        if match is None or not any(line == lines[0] + b"\n" or line == lines[0] + b"\r\n"
                                    for line in raw.splitlines(keepends=True)):
            raise ValueError("동결 서버 DER 크기 행이 완전하지 않다")
        result.update(status="확인", der_bytes=int(match.group(1)))
    except (OSError, ValueError) as exc:
        result["reason"] = str(exc)
    return result


def validate_server_unit(plan, unit, payload):
    arm = plan["arms"][unit["arm"]]
    family = arms.client_family(plan, arm)
    identity = {key: unit[key] for key in ("task", "cell", "trajectory", "arm", "phase",
                                         "block", "block_across_phases", "key")}
    source = "conn_log" if arm["server"] == "gen33" else "frozen_stats"
    if source == "conn_log" and arm.get("conn_log", True) is False:
        source = "planned_omission"
    result = {"unit_identity": identity, "conn_source": source, "checks": {},
              "incidents": [], "server_delta": None, "conns": None, "conn_log": None,
              "tls_accepted": None, "not_accepted": None, "fb_sent": None,
              "frozen_arm_fb_sent": None, "feedback_version": None,
              "fec_parse_fail": None, "scid_matching": {"status": "미확인"}}

    def missing(check, exc):
        result["checks"][check] = "missing"
        result["incidents"].append({"check": check, "reason": str(exc)})

    def checked(check, valid, reason):
        result["checks"][check] = "pass" if valid else "fail"
        if not valid:
            result["incidents"].append({"check": check, "reason": reason})

    server = payload.get("server")
    rows = payload.get("rows")
    if not isinstance(server, dict):
        missing("server_process", "서버 실행 자료 없음")
        server = {}
    else:
        if (type(server.get("returncode")) is not int or server["returncode"] != 0
                or server.get("forced_kill") is not False
                or server.get("exited_before_stop") is not False):
            missing("server_process", "서버 정상 SIGTERM 종료를 확인하지 못했다")
        else:
            result["checks"]["server_process"] = "pass"
    if unit["task"] == "M1" and source == "frozen_stats":
        result["certificate_observation"] = _frozen_certificate_observation(server)
    if (not isinstance(rows, list) or len(rows) != unit["rows_expected"]
            or any(not isinstance(row, dict) or type(row.get("ok")) is not bool for row in rows)):
        missing("client_rows", "계획한 클라이언트 행 수 또는 ok 형식 불일치")
        rows = None
    else:
        result["checks"]["client_rows"] = "pass"
    stats = server.get("stats")
    if not isinstance(stats, dict) or not stats:
        missing("server_stats", "서버 최종 stats 객체 없음")
        stats = None
    else:
        try:
            result["server_delta"] = {key: _count_field(stats, key)
                                      for key in ("bytes_in", "parities", "recovered", "credit_parities")}
            result["fb_sent"] = _count_field(stats, "fb_sent")
            if arm["server"] == "gen33":
                result["tls_accepted"] = _count_field(stats, "tls_accepted")
                result["feedback_version"] = _count_field(stats, "feedback_version")
                result["fec_parse_fail"] = _count_field(stats, "fec_parse_fail")
            result["checks"]["server_stats"] = "pass"
        except (KeyError, ValueError) as exc:
            missing("server_stats", exc)
    if result["fb_sent"] is not None:
        if family != "gen33":
            result["frozen_arm_fb_sent"] = result["fb_sent"]
            checked("frozen_feedback", result["fb_sent"] == 0, "동결 클라이언트 팔의 서버 fb_sent가 0이 아니다")
        elif not arm.get("server_feedback", False):
            checked("no_feedback", result["fb_sent"] == 0, "회신을 끈 팔의 서버 fb_sent가 0이 아니다")
    if arm.get("server_feedback", False) and result["feedback_version"] is not None:
        checked("c1_feedback_version", result["feedback_version"] == 2, "C1 서버 feedback_version이 2가 아니다")
    if (family == "gen33" and arm["kind"] == "auto3"
            and result["fec_parse_fail"] is not None):
        checked("fec_parse_fail", result["fec_parse_fail"] == 0, "gen33 auto 서버 fec_parse_fail이 양수다")
    if stats is not None:
        try:
            if source == "conn_log":
                log = stats["conn_log"]
                if not isinstance(log, dict):
                    raise ValueError("최종 stats.conn_log 객체 없음")
                counts = {key: _count_field(log, key) for key in ("lines", "errors", "pending")}
                evicted = _count_field(stats, "conn_acct_evicted_lru")
                path = server["conn_log_path"]
                if not isinstance(path, str) or not path or Path(log["path"]).resolve() != Path(path).resolve():
                    raise ValueError("conn-log 경로가 최종 stats와 다르다")
                conns = read_conn_log(path)
                result["conns"] = conns
                result["conn_log"] = {**counts, "actual_lines": len(conns), "conn_acct_evicted_lru": evicted}
                accepted = _count_field(stats, "tls_accepted")
                result["not_accepted"] = counts["lines"] - accepted
                if counts["errors"] or counts["pending"] or evicted:
                    raise ValueError("conn-log errors, pending 또는 LRU 축출이 0이 아니다")
                if counts["lines"] != len(conns) or counts["lines"] < accepted:
                    raise ValueError("conn-log 줄 수가 실제 행 또는 tls_accepted와 맞지 않는다")
                if rows is not None and all(row["ok"] for row in rows) and counts["lines"] != len(rows):
                    raise ValueError("실패 없는 단위의 conn-log 줄 수가 클라이언트 행 수와 다르다")
            elif source == "frozen_stats":
                stored = stats["conns"]
                if not isinstance(stored, dict):
                    raise ValueError("동결 서버 stats.conns 객체 없음")
                conns = []
                for key, value in sorted(stored.items()):
                    if not isinstance(value, dict) or ("key" in value and value["key"] != key):
                        raise ValueError("동결 서버 연결 객체 또는 key 충돌")
                    conns.append(_conn_record({**value, "key": key}, logged=False))
                result["conns"] = conns
                if rows is not None and all(row["ok"] for row in rows) and len(conns) != len(rows):
                    raise ValueError("실패 없는 단위의 동결 서버 연결 수가 클라이언트 행 수와 다르다")
            elif unit["task"] != "M1" or unit["arm"] != "g":
                raise ValueError("계획된 M1 g 외에는 gen33 conn-log를 생략할 수 없다")
            result["checks"]["connection_collection"] = "pass"
        except (KeyError, TypeError, ValueError, OSError) as exc:
            missing("connection_collection", exc)
    if family != "gen33":
        result["scid_matching"] = {"status": "동결 클라이언트 필드 미제공"}
    elif source == "planned_omission":
        result["scid_matching"] = {"status": "계획된 conn-log 생략"}
    elif result["conns"] is not None and rows is not None:
        result["scid_matching"] = match_client_scids(rows, result["conns"])
    result["has_data"] = "missing" not in result["checks"].values()
    result["execution_status"] = execution_status(has_data=result["has_data"], checks=result["checks"])
    result["reject_block"] = (not result["has_data"] or any(result["checks"].get(key) == "fail"
        for key in ("frozen_feedback", "no_feedback", "c1_feedback_version")))
    return result


def _cache_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("캐시 JSON 중복 키: " + key)
        result[key] = value
    return result


def _cache_constant(value):
    raise ValueError("캐시 JSON 비유한수: " + value)


def _cache_numeric(value, *, integer=False, nonnegative=False):
    number = _number(value)
    if (integer and type(value) is not int) or (nonnegative and number < 0):
        raise ValueError("캐시 숫자 필드의 형식 또는 범위 오류")


def _cache_array(value, *, size=None, nonnegative=False):
    if not isinstance(value, list) or (size is not None and len(value) != size):
        raise ValueError("캐시 배열의 형식 또는 크기 오류")
    for item in value:
        _cache_numeric(item, nonnegative=nonnegative)


def _cache_state(state, version):
    if not isinstance(state, dict) or type(state.get("v")) is not int or state["v"] != version:
        raise ValueError("cache3 state 판본 오류")
    for field in ("seq", "n_dec", "n_reeval"):
        _cache_numeric(state[field], integer=True, nonnegative=True)
    for field in ("k_hist", "S_hist", "g_common"):
        _cache_array(state[field])
    post = state.get("post")
    if not isinstance(post, list) or len(post) != 5:
        raise ValueError("cache3 posterior 행 수 오류")
    for row in post:
        _cache_array(row, size=26, nonnegative=True)
    _cache_array(state["w"], size=5, nonnegative=True)
    for field in ("hct", "g_resid", "hct_seq", "g_alarm", "stats"):
        mapping = state[field]
        if not isinstance(mapping, dict):
            raise ValueError("cache3 state map 형식 오류: " + field)
        for value in mapping.values():
            if field in ("hct", "g_resid"):
                _cache_array(value)
            else:
                _cache_numeric(value, integer=True, nonnegative=True)
    if version == 11:
        if type(state.get("c1_seen")) is not bool:
            raise ValueError("cache3 c1_seen 필드 오류")
        _cache_numeric(state["arrival_streak"], integer=True, nonnegative=True)


def validate_cache_bytes(raw, binary_id, expected_address=None):
    if not isinstance(raw, bytes):
        raise ValueError("캐시의 원본 bytes가 필요하다")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_cache_object,
                       parse_constant=_cache_constant)
    if not isinstance(value, dict):
        raise ValueError("캐시 JSON은 객체여야 한다")
    if binary_id in ("gen33", "g3c"):
        version = 11 if binary_id == "gen33" else 2
        if set(value) != {"schema", "dests"} or value["schema"] != f"padfec3.cache3/{version}":
            raise ValueError("cache3 schema 오류")
        dests = value["dests"]
    elif binary_id == "g2":
        dests = value
    else:
        raise ValueError("알 수 없는 캐시 바이너리: " + str(binary_id))
    if not isinstance(dests, dict) or any(not isinstance(key, str) or not key for key in dests):
        raise ValueError("캐시 목적지 map 오류")
    if expected_address is not None and expected_address not in dests:
        raise ValueError("캐시에 실행 목적지가 없다")
    try:
        for entry in dests.values():
            if not isinstance(entry, dict):
                raise ValueError("캐시 목적지 entry가 객체가 아니다")
            if binary_id in ("gen33", "g3c"):
                for field in ("min_rtt_ms", "min_hct_ms"):
                    _cache_numeric(entry[field], nonnegative=True)
                for field in ("rtt_observations", "conns"):
                    _cache_numeric(entry[field], integer=True, nonnegative=True)
                _cache_state(entry["state"], version)
            else:
                for field in ("k", "rtt_observations", "conns", "since_probe"):
                    _cache_numeric(entry[field], integer=True, nonnegative=True)
                for field in ("server_flight", "min_hct_ms", "min_rtt_ms", "loss_count",
                              "obs_count", "loss_hct_ms", "probe_min_hct_ms", "sym_loss",
                              "sym_obs", "sym_c2_conns", "sym_c2_symbols"):
                    _cache_numeric(entry[field], nonnegative=True)
    except KeyError as exc:
        raise ValueError("캐시 필수 필드 누락: " + str(exc)) from exc
    return value
