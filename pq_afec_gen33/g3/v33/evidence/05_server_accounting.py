import sys
sys.dont_write_bytecode = True
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import average, comparison, segments, run


def accumulate(bucket, value, segment):
    observations = segment["rows"]
    bucket["segments"] += 1
    bucket["returned_connections"] += len(observations)
    bucket["planned_connections"] += segment.get("n_planned", value["sizes"][segment["arm"]])
    bucket["ok_connections"] += sum(bool(row.get("ok")) for row in observations)
    for key in ("bytes_in", "parities", "originals", "recovered", "credit_parities"):
        count = segment.get("server_delta", {}).get(key)
        if count is None:
            bucket["missing_fields"].append({"block": value["block"], "field": "server_delta." + key})
        else:
            bucket["server_delta_sum"][key] = bucket["server_delta_sum"].get(key, 0) + count
    for key in ("bytes_orig", "bytes_parity", "parity_sent"):
        count = segment.get("client_stats", {}).get(key)
        if count is None:
            bucket["missing_fields"].append({"block": value["block"], "field": "client_stats." + key})
        else:
            bucket["client_stats_sum"][key] = bucket["client_stats_sum"].get(key, 0) + count
    for row in observations:
        first_original = row.get("first_flight_bytes")
        first_parity = row.get("first_flight_parity_bytes")
        if first_original is not None and first_parity is not None:
            bucket["first_flight_bytes_values"].append(first_original + first_parity)
        else:
            bucket["first_flight_missing"] += 1


def empty():
    return {"segments": 0, "returned_connections": 0, "planned_connections": 0, "ok_connections": 0, "server_delta_sum": {}, "client_stats_sum": {}, "first_flight_bytes_values": [], "first_flight_missing": 0, "missing_fields": []}


def finalize(bucket):
    result = {key: value for key, value in bucket.items() if key != "first_flight_bytes_values"}
    n = bucket["returned_connections"]
    server = bucket["server_delta_sum"]
    client = bucket["client_stats_sum"]
    complete = not bucket["missing_fields"]
    result["first_flight_sent_bytes_mean_B"] = average(bucket["first_flight_bytes_values"])
    result["server_received_bytes_per_returned_connection_B"] = server.get("bytes_in", 0) / n if n and complete else None
    result["server_received_parities_per_returned_connection"] = server.get("parities", 0) / n if n and complete else None
    result["client_counted_bytes_per_returned_connection_B"] = (client.get("bytes_orig", 0) + client.get("bytes_parity", 0)) / n if n and complete else None
    result["client_counted_parities_per_returned_connection"] = client.get("parity_sent", 0) / n if n and complete else None
    return result


def analyze(context):
    result = []
    for path in sorted(context.journals.glob("p31_run[12]_*_units.jsonl")):
        units = context.load(path.name)
        run_id = path.name.split("_", 2)[1]
        condition = path.name[len(f"p31_{run_id}_"):-len("_units.jsonl")]
        grouped = {}
        max_block = max(unit["val"]["block"] for unit in units)
        for _, value, segment in segments(units):
            arm = segment["arm"]
            for scope in ("whole_run", f"loss_percent={value['loss']}"):
                accumulate(grouped.setdefault((arm, scope), empty()), value, segment)
            if value["block"] == max_block:
                accumulate(grouped.setdefault((arm, "last_block"), empty()), value, segment)
        for (arm, scope), bucket in sorted(grouped.items()):
            summary = {"run": run_id, "condition": condition, "arm": arm, "scope": scope, "last_block_index": max_block, **finalize(bucket)}
            if run_id == "run1" and condition == "D_p11_2955_l0" and scope == "whole_run" and arm in ("g2auto", "g3auto"):
                expected = (4532, 8579, 11001) if arm == "g2auto" else (7991, 7991, 10546)
                summary["expected"] = {"client_parity": comparison(summary["client_stats_sum"].get("parity_sent"), expected[0], "실행 전체 클라이언트 계수"), "server_parity": comparison(summary["server_delta_sum"].get("parities"), expected[1], "실행 전체 서버 수신 계수"), "server_bytes_per_conn": comparison(summary["server_received_bytes_per_returned_connection_B"], expected[2], "감사 문서의 정수 B 반올림값")}
            if run_id == "run1" and scope == "last_block" and condition == "D_p11_2955_l0" and arm in ("g2auto", "g3auto"):
                summary["expected"] = {"server_bytes_per_conn": comparison(summary["server_received_bytes_per_returned_connection_B"], 7235 if arm == "g2auto" else 10551, "마지막 블록의 정수 B 반올림값")}
            result.append(summary)
    return {"item": "A0-5", "data_kind": "measurement_reanalysis", "source_scripts": ["audit-measurement/srvbytes.py", "audit-measurement/s11_bytes.py", "audit-measurement/jl.py"], "definitions": {"server_counter": "segments[].server_delta를 합산한다. 누적 server_after를 합산하지 않는다.", "denominator": "반환 행 수. 계획 연결 수도 별도로 출력한다.", "lossless": "서버 수신량과 송신량을 대조할 수 있는 조건이며 종료 패킷 등 계측 범위 차이가 남는다.", "lossy": "server_received_bytes는 손실 뒤 서버 수신량이다. 클라이언트 송신량으로 이름을 바꾸지 않는다.", "first_flight": "행별 first_flight_bytes + first_flight_parity_bytes. 연결 전체 바이트와 별도 통계다.", "missing": "필수 계수 중 하나라도 누락된 그룹은 연결당 계수를 null로 표시한다."}, "results": result}


if __name__ == "__main__":
    run(analyze)
