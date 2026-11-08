import math
import re
from collections.abc import Mapping

from padfec3 import layout


def williams(n):
    if type(n) is not int or n < 1:
        raise ValueError("팔 수는 양의 정수여야 한다")
    first = [0]
    low, high = 1, n - 1
    while low <= high:
        first.append(low)
        low += 1
        if low <= high:
            first.append(high)
            high -= 1
    rows = [[(item + shift) % n for item in first] for shift in range(n)]
    return rows + [list(reversed(row)) for row in rows] if n % 2 else rows


def order_for(arm_ids, idx):
    if type(idx) is not int or idx < 0 or len(set(arm_ids)) != len(arm_ids):
        raise ValueError("팔 목록 또는 Williams 행 번호가 잘못됐다")
    rows = williams(len(arm_ids))
    return [arm_ids[item] for item in rows[idx % len(rows)]]


def _count(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name}: {minimum} 이상의 정수가 필요하다")
    return value


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_]+", value):
        raise ValueError(f"잘못된 식별자: {value!r}")
    return value


def _number(value, name, minimum=0, maximum=None):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or value < minimum or (maximum is not None and value > maximum)):
        raise ValueError(f"{name}: 범위 안의 유한한 수가 필요하다")
    return value


def client_family(plan, arm):
    return plan["binaries"][arm["binary"]].get("family", arm["binary"])


def selected_tasks(plan, task_ids=None):
    order = plan["ordering"]["required_task_order"]
    wanted = order if task_ids is None else ([task_ids] if isinstance(task_ids, str) else list(task_ids))
    if not wanted or len(set(wanted)) != len(wanted):
        raise ValueError("과제 목록은 비어 있거나 중복될 수 없다")
    optional = {item["id"]: item for item in plan.get("optional", [])}
    for task_id in wanted:
        _identifier(task_id)
        if task_id in optional:
            if optional[task_id].get("requires_subplan"):
                raise ValueError(f"{task_id}: 커밋한 보충 계획이 필요하다")
            raise ValueError(f"{task_id}: optional 실행은 아직 지원하지 않는다")
        if task_id not in order or task_id not in plan["tasks"]:
            raise ValueError(f"알 수 없는 과제: {task_id}")
    return [task_id for task_id in order if task_id in wanted]


def _profile(plan, profile_id, arm):
    profile = dict(plan["profiles"][profile_id])
    for row in plan.get("gap_table", []):
        if row["profile"] == profile_id:
            gap_key = "v33c1_ms" if arm.get("server_feedback") else "other_arms_ms"
            if gap_key in row:
                profile["gap_ms"] = row[gap_key]
    for name in tuple(profile):
        if name in arm:
            profile[name] = arm[name]
    for name in ("rtt_ms", "netem_uplink_mbps", "policy_uplink_mbps", "gap_ms", "feedback_wait_ms"):
        _number(profile[name], name)
    _count(profile["expect_k"], "expect_k", 1)
    _count(profile["certsize"], "certsize", 1)
    return profile


def iter_units(plan, task_ids=None, include_additional=True):
    units = []
    for task_id in selected_tasks(plan, task_ids):
        task = plan["tasks"][task_id]
        if task.get("requires_subplan"):
            raise ValueError(f"{task_id}: 커밋한 보충 계획이 필요하다")
        cells = [(cell, False) for cell in task["cells"]]
        if include_additional:
            cells += [(cell, True) for cell in task.get("additional_cells", [])]
        cell_ids = set()
        totals = {False: 0, True: 0}
        for cell, additional in cells:
            cell_id = _identifier(cell["id"])
            if cell_id in cell_ids:
                raise ValueError(f"중복 셀: {task_id}/{cell_id}")
            cell_ids.add(cell_id)
            profile_id = _identifier(cell["profile"])
            arm_ids = cell["arms"]
            order_for(arm_ids, 0)
            for arm_id in arm_ids:
                _identifier(arm_id)
                arm = plan["arms"][arm_id]
                if arm.get("tier") == "optional" or arm.get("requires_subplan"):
                    raise ValueError(f"{arm_id}: optional 팔 실행은 아직 지원하지 않는다")
                for binary_id in (arm["binary"], arm["server"]):
                    if binary_id not in plan["binaries"]:
                        raise ValueError(f"알 수 없는 바이너리: {binary_id}")
            trajectories = _count(cell["trajectories"], "trajectories", 1)
            burnin = _count(cell["burnin_per_arm_trajectory"], "burnin_per_arm_trajectory")
            warmup = _count(cell.get("warmup_per_arm_block", 0), "warmup_per_arm_block")
            for trajectory in range(trajectories):
                offset = 0
                block_across_phases = 0
                for phase_index, phase in enumerate(cell["phases"]):
                    blocks = _count(phase["blocks"], "blocks", 1)
                    connections = _count(phase["connections_per_arm_block"], "connections_per_arm_block", 1)
                    total = _count(phase["connections_per_arm"], "connections_per_arm", 1)
                    if blocks * connections != total:
                        raise ValueError(f"{task_id}/{cell_id}: 블록별 연결 수와 phase 총계 불일치")
                    if warmup > connections or (burnin and warmup):
                        raise ValueError(f"{task_id}/{cell_id}: 번인과 워밍업 설정 오류")
                    if "measured_per_arm_block" in cell and connections - warmup != cell["measured_per_arm_block"]:
                        raise ValueError(f"{task_id}/{cell_id}: 블록별 측정 분모 불일치")
                    for loss_name in ("loss_c2s_pct", "loss_s2c_pct"):
                        _number(phase[loss_name], loss_name, maximum=100)
                    for block in range(blocks):
                        excluded = min(connections, max(0, burnin - offset))
                        for arm_id in order_for(arm_ids, block_across_phases + trajectory):
                            arm = plan["arms"][arm_id]
                            cache_key = f"{task_id}.{cell_id}.t{trajectory}.{arm_id}" if arm["kind"] in ("auto2", "auto3") else None
                            units.append({
                                "key": f"{task_id}.{cell_id}.t{trajectory}.p{phase_index}.b{block}.{arm_id}",
                                "task": task_id,
                                "cell": cell_id,
                                "additional": additional,
                                "profile_id": profile_id,
                                "profile": _profile(plan, profile_id, arm),
                                "trajectory": trajectory,
                                "phase": phase_index,
                                "block": block,
                                "block_across_phases": block_across_phases,
                                "arm": arm_id,
                                "connections": connections,
                                "rows_expected": connections,
                                "burnin_connections": excluded,
                                "warmup_connections": warmup,
                                "measured_connections": connections - excluded - warmup,
                                "connection_offset": offset,
                                "cache_key": cache_key,
                                "loss_c2s_pct": phase["loss_c2s_pct"],
                                "loss_s2c_pct": phase["loss_s2c_pct"],
                            })
                            totals[additional] += connections
                        offset += connections
                        block_across_phases += 1
                if burnin > offset:
                    raise ValueError(f"{task_id}/{cell_id}: 번인이 궤적 길이보다 크다")
                if "measured_per_arm" in cell and offset - warmup * block_across_phases - burnin != cell["measured_per_arm"]:
                    raise ValueError(f"{task_id}/{cell_id}: 궤적별 측정 분모 불일치")
        if totals[False] != task["connections_total"]:
            raise ValueError(f"{task_id}: 계획 연결 총계 불일치")
        if include_additional and totals[True] != task.get("additional_connections_total", 0):
            raise ValueError(f"{task_id}: 추가 연결 총계 불일치")
    return units


def _render(flags, values):
    rendered = []
    for token in flags:
        if not isinstance(token, str):
            raise ValueError("명령 인자는 문자열이어야 한다")
        rendered.append(token.format_map(values))
    return rendered


def _values(unit):
    values = dict(unit["profile"])
    values["unit_connections"] = unit["connections"]
    return {key: format(value, "g") if type(value) in (int, float) else value for key, value in values.items()}


def client_command(plan, unit, *, binary_paths, address, cache=None, stats=None):
    arm = plan["arms"][unit["arm"]]
    if arm["kind"] in ("auto2", "auto3") and cache is None:
        raise ValueError("auto 팔은 궤적별 캐시 경로가 필요하다")
    values = _values(unit)
    values["cache"] = str(cache) if cache is not None else ""
    flags = plan["common"]["client_common_flags"] + arm["client_flags"]
    if any(token == "-ips" or token.startswith("-ips=") for token in flags):
        raise ValueError("-ips는 계획 팔의 ips 값으로만 지정한다")
    command = [str(binary_paths[arm["binary"]])] + _render(flags, values) + ["-addr", str(address)]
    if "ips" in arm:
        command += ["-ips", str(_count(arm["ips"], "ips", 1))]
    if stats is not None:
        command += ["-stats", str(stats)]
    return command


def server_command(plan, unit, *, binary_paths, address, cert_file=None, stats, conn_log=None):
    arm = plan["arms"][unit["arm"]]
    server_id = arm["server"]
    values = _values(unit)
    values.update(cert_file=str(cert_file), stats=str(stats), conn_log=str(conn_log))
    flags = list(plan["common"]["server_flags" if server_id == "gen33" else "frozen_server_flags"])
    if server_id == "gen33":
        if cert_file is None:
            raise ValueError("gen33 서버는 셀의 공통 인증서가 필요하다")
        if arm.get("conn_log", True):
            if conn_log is None:
                raise ValueError("gen33 서버는 단위 conn-log 경로가 필요하다")
        else:
            index = flags.index("-conn-log")
            del flags[index:index + 2]
        if arm.get("server_feedback"):
            flags.append("-feedback")
        if unit["task"] == "X9":
            flags += ["-udp-path", "basic"]
    return [str(binary_paths[server_id])] + _render(flags, values) + ["-addr", str(address)]


def row_lead(row):
    value = row.get("first_flight_lead_dgrams")
    if type(value) is int:
        return value
    count = row.get("first_flight_parity_dgrams")
    m = row.get("m_used")
    if type(count) is int and type(m) is int:
        return min(1 if m >= 2 else 0, count)
    return 0


def pre_decision_bytes(row):
    original = row.get("first_flight_bytes") or 0
    extra = row.get("extra_sent")
    if isinstance(extra, Mapping) and extra.get("kind") == "pad_junk":
        count = extra.get("first_sent") or 0
        total = extra.get("first_bytes") or 0
        lead = extra.get("first_lead") or 0
    else:
        count = row.get("first_flight_parity_dgrams") or 0
        total = row.get("first_flight_parity_bytes") or 0
        lead = row_lead(row)
    return original + lead * (total / float(count) if count else 0.0)


def one_rtt(row, profile):
    if not row.get("ok"):
        return False
    rate = profile["netem_uplink_mbps"]
    delay = 8.0 * pre_decision_bytes(row) / (1000.0 * rate) if rate > 0 else 0.0
    return row["ms"] < layout.ONE_RTT_CUTOFF_RTTS * profile["rtt_ms"] + delay


def settle_s(profile):
    return 0.3 + 2.0 * profile["rtt_ms"] / 1000.0
