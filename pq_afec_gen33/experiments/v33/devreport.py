from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.v33 import devbed
from experiments.v33.lib import arms, blocks, observations, report, report_checks, statistics


def read_json(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"),
                       object_pairs_hook=devbed.strict_object,
                       parse_constant=devbed.reject_constant)
    if not isinstance(value, dict):
        raise ValueError("JSON 객체가 필요하다")
    return value


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def verify_artifacts(path):
    path = Path(path).resolve()
    files = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64}) [ *](.+)", line)
        if match is None:
            raise ValueError("SHA 목록 형식 오류")
        target = (path.parent / match.group(2)).resolve()
        if target in files or target.suffix.lower() == ".pem":
            raise ValueError("SHA 목록 중복 또는 PEM 경로")
        if file_sha256(target) != match.group(1):
            raise ValueError("SHA 목록 검증 실패: " + str(target))
        files.append(target)
    if not files:
        raise ValueError("SHA 목록이 비어 있다")
    return files


class SavedBackend:
    def __init__(self, payloads):
        self.payloads = payloads

    def address_for(self, unit):
        command = self.payloads[unit["key"]]["commands"]["client"]
        if command.count("-addr") != 1:
            raise ValueError("저장된 client 주소 인자가 유일하지 않다")
        return command[command.index("-addr") + 1]


def _raw_paths(payload, raw_dir):
    hashes = payload.get("raw_sha256")
    files = payload.get("raw_files")
    if not isinstance(hashes, dict) or not hashes or not isinstance(files, dict) or not files:
        raise ValueError("단위 원자료 파일과 SHA 목록이 필요하다")
    paths = {}
    for relative, digest in hashes.items():
        path = (raw_dir / relative).resolve()
        if not path.is_relative_to(raw_dir) or path.suffix.lower() == ".pem":
            raise ValueError("원자료 경로 범위 오류")
        report._sha256(digest)
        if path in paths or file_sha256(path) != digest:
            raise ValueError("원자료 SHA 불일치 또는 중복")
        paths[path] = digest
    if {Path(path).resolve() for path in files.values()} != set(paths):
        raise ValueError("원자료 파일과 SHA 목록이 다르다")
    return paths


def _validate_metadata(meta, manifest, plan, digest):
    report.result_metadata(meta)
    provenance = manifest["provenance"]
    for key in ("plan_commit", "plan_sha256", "plan_doc_commit", "plan_doc_sha256", "plan_files"):
        if meta.get(key) != provenance.get(key) or key not in meta:
            raise ValueError("저장된 계획 provenance 불일치: " + key)
    if meta["plan_sha256"] != digest or meta["policy_version"] != plan["policy_version"]:
        raise ValueError("저장된 계획 SHA 또는 정책 판본 불일치")
    for key in ("plan_commit", "plan_doc_commit"):
        if not isinstance(meta[key], str) or re.fullmatch(r"[0-9a-f]{40,64}", meta[key]) is None:
            raise ValueError("저장된 계획 commit 형식 오류")
    report._sha256(meta["plan_doc_sha256"])
    if not meta["plan_files"]:
        raise ValueError("계획 선커밋 시각 근거가 없다")
    for field, binary_field in (("binary_sha256", "sha256"), ("srcsha", "srcsha")):
        expected = {key: value[binary_field] for key, value in plan["binaries"].items()}
        if meta.get(field) != expected:
            raise ValueError("저장된 바이너리 식별값 불일치: " + field)
    if not isinstance(meta.get("env"), dict) or any(
            key not in meta["env"] for key in plan["collection"]["env_keys"]):
        raise ValueError("최초 환경 metadata가 불완전하다")
    if any(meta.get(key) != manifest[key] for key in ("task", "run_id")):
        raise ValueError("최초 metadata의 실행 식별 불일치")


def read_run(journal_path, *, plan_path, raw_dir, m1_result=None):
    raw_dir = Path(raw_dir).resolve()
    journal_path = Path(journal_path).resolve()
    match = re.fullmatch(r"units_([A-Za-z0-9][A-Za-z0-9._-]{0,79})\.jsonl", journal_path.name)
    if match is None or journal_path.parent != raw_dir:
        raise ValueError("실행 폴더의 units_<run-id>.jsonl이 필요하다")
    run_id = match.group(1)
    manifest_path = raw_dir / f"manifest_{run_id}.json"
    inputs = {journal_path: file_sha256(journal_path), manifest_path: file_sha256(manifest_path),
              Path(plan_path).resolve(): file_sha256(plan_path)}
    manifest = read_json(manifest_path)
    plan, digest = devbed.read_plan(plan_path)
    if manifest.get("run_id") != run_id or manifest.get("plan") != plan:
        raise ValueError("저장된 실행 ID 또는 계획이 입력과 다르다")
    task = manifest["task"]
    units = arms.iter_units(plan, [task])
    meta = manifest["meta"]
    _validate_metadata(meta, manifest, plan, digest)
    dependency = devbed.m1_dependency(plan, task, m1_result, plan_sha256=digest)
    if dependency != manifest.get("m1_dependency") or dependency != meta.get("m1_dependency"):
        raise ValueError("러너와 결과 생성기의 M1 입력이 다르다")
    if m1_result is not None:
        inputs[Path(m1_result).resolve()] = file_sha256(m1_result)
    journal = blocks.UnitJournal(journal_path, run_id, manifest["fingerprint"], units, resume=True)
    if not journal.complete or journal.metadata != meta:
        raise ValueError("완료 저널 또는 최초 metadata가 일치하지 않는다")
    payloads = [entry["payload"] for entry in journal.records]
    backend = SavedBackend({entry["key"]: entry["payload"] for entry in journal.records})
    validate = devbed.unit_validator(plan, manifest["provenance"], raw_dir, backend)
    for unit, payload in zip(units, payloads):
        inputs.update(_raw_paths(payload, raw_dir))
        validate(unit, payload)
        arm = plan["arms"][unit["arm"]]
        for row in payload["rows"]:
            for key, field in (("server_binary_sha256", "sha256"), ("server_srcsha", "srcsha")):
                if row.get(key) != plan["binaries"][arm["server"]][field]:
                    raise ValueError("서버 행 지문이 계획과 다르다")
    log_names = {"client.jsonl", "client.stderr", "client.stats.json", "server.stdout",
                 "server.stderr", "server.stats.json", "server.conns.jsonl",
                 "tc_before.json", "tc_after.json"}
    for path in (raw_dir / "units").rglob("*"):
        if path.name in log_names and path.is_file():
            resolved = path.resolve()
            if not resolved.is_relative_to(raw_dir):
                raise ValueError("보존 로그 경로가 원자료 밖이다")
            inputs.setdefault(resolved, file_sha256(resolved))
    return {"plan": plan, "manifest": manifest, "journal": journal, "units": units,
            "payloads": payloads, "inputs": inputs,
            "m1_result": dependency["result"] if dependency else None}


def server_summary(plan, units, payloads):
    grouped = defaultdict(list)
    for unit, payload in zip(units, payloads):
        grouped[(unit["cell"], unit["arm"])].append(payload)
    result = []
    for (cell, arm_id), entries in sorted(grouped.items()):
        server = [item["collection"]["server"] for item in entries]
        rows = [row for item in entries for row in item["rows"]]
        counts = {}
        for field in ("fec_parse_fail", "not_accepted", "tls_accepted", "fb_sent", "frozen_arm_fb_sent"):
            values = [item[field] for item in server]
            counts[field] = sum(values) if all(value is not None for value in values) else None
        matches = [item["scid_matching"] for item in server]
        if all(item["status"] == "확인" for item in matches):
            scid = {"status": "확인", "matched": sum(item["matched"] for item in matches),
                    "client_rows": len(rows),
                    "unmatched_client_rows": sum(len(item["unmatched_client_rows"]) for item in matches),
                    "empty_client_rows": sum(len(item["empty_client_rows"]) for item in matches),
                    "duplicate_client_scids": sum(len(item["duplicate_client_scids"]) for item in matches),
                    "duplicate_server_scids": sum(len(item["duplicate_server_scids"]) for item in matches)}
            scid["matched_rate"] = scid["matched"] / len(rows) if rows else None
        else:
            scid = {"status": "미확인", "reasons": sorted({item["status"] for item in matches})}
        result.append({"cell": cell, "arm": arm_id, **counts, "scid_matching": scid,
            "conn_source": sorted({item["conn_source"] for item in server}),
            "server_connections": sum(len(item["conns"]) for item in server)
            if all(item["conns"] is not None for item in server) else None,
            "server_delta": {field: sum(item["server_delta"][field] for item in entries)
                             for field in ("bytes_in", "parities", "recovered", "credit_parities")},
            "client_rows": len(rows),
            "client_parity_count_unreliable": plan["arms"][arm_id].get("client_parity_count_unreliable", False),
            "g2auto_ips_used_ge1395": sum(type(row.get("ips_used")) in (int, float)
                                        and row["ips_used"] >= 1395 for row in rows)
            if arm_id == "g2auto" else None,
            "g2auto_ips_used_missing": sum(type(row.get("ips_used")) not in (int, float) for row in rows)
            if arm_id == "g2auto" else None})
        certificates = [item.get("certificate_observation") for item in server]
        if any(item is not None for item in certificates):
            observed = [item for item in certificates
                        if item is not None and item["status"] == "확인"]
            result[-1]["certificate_observation"] = {
                "source": "server.stderr", "units_total": len(server),
                "units_observed": len(observed),
                "der_bytes_values": sorted({item["der_bytes"] for item in observed}),
                "status": "확인" if len(observed) == len(server) else "미확인"}
    return result


def policy_uplink_inputs(plan, task, units):
    profiles = {}
    for unit in units:
        profiles.setdefault((unit["cell"], unit["arm"]), unit["profile"])
    specs = plan["tasks"][task]["cells"] + plan["tasks"][task].get("additional_cells", [])
    rows = [{"cell": cell["id"], "arm": arm_id,
             "policy_uplink_mbps": profiles[(cell["id"], arm_id)]["policy_uplink_mbps"],
             "netem_uplink_mbps": profiles[(cell["id"], arm_id)]["netem_uplink_mbps"]}
            for cell in specs for arm_id in cell["arms"] if (cell["id"], arm_id) in profiles]
    if all(row["policy_uplink_mbps"] == row["netem_uplink_mbps"] for row in rows):
        return None
    return rows


def build_result(run):
    plan, manifest = run["plan"], run["manifest"]
    task = manifest["task"]
    units, payloads = run["units"], run["payloads"]
    observed = observations.summarize_observations(
        plan, [payload["collection"]["observations"] for payload in payloads])
    stats = statistics.summarize(plan, task, units, payloads, m1_result=run["m1_result"],
                                 env=manifest["meta"]["env"])
    checked = report_checks.summarize_checks(plan, task, units, payloads, observed,
                                             events=run["journal"].events)
    checks = {**stats.get("checks", {}), **checked["checks"]}
    meta = manifest["meta"]
    result = {"schema": "padfec3.devreport/1", "task": task, "run_id": manifest["run_id"],
        "label": meta["label"], "confirmatory": meta["confirmatory"],
        "policy_version": meta["policy_version"], **deepcopy(manifest["provenance"]),
        "binary_sha256": meta["binary_sha256"], "srcsha": meta["srcsha"], "env": meta["env"],
        "fingerprint": manifest["fingerprint"],
        "first_unit_started_at": min(payload["started_at"] for payload in payloads),
        "last_unit_ended_at": max(payload["ended_at"] for payload in payloads),
        "conditions": deepcopy(plan["common"]), "statistics": stats,
        "observations": observed, "server_summary": server_summary(plan, units, payloads),
        "checks": checks, "check_details": checked["details"],
        "execution_status": report.execution_status(has_data=True, checks=checks),
        "status": stats.get("inference_status", "판정 없음"),
        "m1_result": run["m1_result"],
        "m1_result_sha256": manifest["m1_dependency"]["sha256"] if manifest["m1_dependency"] else None,
        "measured_items": [], "units_completed": len(units),
        "client_rows": sum(len(payload["rows"]) for payload in payloads),
        "idle_check": {"status": "미확인", "mean_idle_ms": None, "decision": "D79",
                       "reason": observations.IDLE_UNAVAILABLE}}
    for name in ("contrasts", "a_vs_sealed", "n_blocks"):
        if name in stats:
            result[name] = stats[name]
    if task == "M1":
        result["meta"] = {"env": deepcopy(meta["env"])}
    if task == "X9":
        result["x9_by_direction"] = {}
        for cell in stats["cells"]:
            by_arm = {arm["arm"]: arm for arm in cell["arms"]}
            pto = {name: by_arm[name]["primary"]["pto"]
                   for name in ("x25519_off", "mlkem_off")}
            contrast = cell["pto_contrast"]["primary"]
            result["x9_by_direction"][cell["cell"]] = {
                "definition": "primary", "effect_sign": contrast["effect_sign"],
                "units": {"pto_rate": "proportion", "diff_ci95": "proportion",
                          "n_measured": "connections", "warmup_excluded": "connections",
                          "pto_definition_mismatch": "connections"},
                "pto_rate_x25519": pto["x25519_off"]["primary"]["rate"],
                "pto_rate_mlkem": pto["mlkem_off"]["primary"]["rate"],
                "diff_ci95": deepcopy(contrast["ci95"]),
                "n_measured": {name: value["primary"]["n_valid"] for name, value in pto.items()},
                "warmup_excluded": {name: by_arm[name]["warmup_excluded"] for name in pto},
                "pto_definition_mismatch": {name: value["definition_mismatch"]
                                            for name, value in pto.items()}}
    result["result_source"] = f"g3/v33/results/v33_dev_{task}_{manifest['run_id']}.json"
    inputs = policy_uplink_inputs(plan, task, units)
    if inputs is not None:
        result["policy_uplink_inputs"] = inputs
    if task == "X2":
        result["measured_items"] = [{"id": "X2", "n_rows": result["client_rows"],
                                     "execution_status": result["execution_status"]}]
    if plan.get("exploratory") is True:
        result["exploratory"] = True
        result["plan_id"] = plan["plan_id"]
    return result


def report_run(journal_path, *, plan_path, raw_dir, artifacts_dir, m1_result=None,
               result_dir=None, docs_dir=None):
    from experiments.v33.lib.report_docs import render_document
    run = read_run(journal_path, plan_path=plan_path, raw_dir=raw_dir, m1_result=m1_result)
    result = build_result(run)
    task, run_id = result["task"], result["run_id"]
    result_path = Path(result_dir if result_dir is not None else ROOT / "g3/v33/results") / f"v33_dev_{task}_{run_id}.json"
    document_name = run["plan"]["result_contract"].get("document_names", {}).get(task, f"{task}_result.md")
    document_path = Path(docs_dir if docs_dir is not None else ROOT / "docs") / document_name
    artifacts_path = Path(artifacts_dir) / f"{task}_artifacts.sha256"
    outputs = [path.resolve() for path in (result_path, document_path, artifacts_path)]
    if len(set(outputs)) != len(outputs) or any(path in run["inputs"] or path.is_relative_to(Path(raw_dir).resolve())
                                              for path in outputs):
        raise ValueError("결과 경로가 서로 겹치거나 원자료 안에 있다")
    result_bytes = json_bytes(result)
    document_bytes = render_document(result).encode("utf-8")
    if any(file_sha256(path) != digest for path, digest in run["inputs"].items()):
        raise ValueError("집계 중 입력 바이트가 바뀌었다")
    for path, content in ((result_path, result_bytes), (document_path, document_bytes)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    artifacts_path.parent.mkdir(parents=True, exist_ok=True)
    paths = set(run["inputs"]) | {result_path.resolve(), document_path.resolve()}
    lines = []
    for path in sorted(paths, key=lambda item: item.as_posix()):
        try:
            relative = Path(os.path.relpath(path, artifacts_path.parent.resolve())).as_posix()
        except ValueError:
            relative = path.as_posix()
        if "\n" in relative or "\r" in relative or "\\" in relative:
            raise ValueError("SHA 목록 경로 형식 오류")
        lines.append(file_sha256(path) + "  " + relative + "\n")
    artifacts_path.write_bytes("".join(lines).encode("utf-8"))
    verify_artifacts(artifacts_path)
    if any(file_sha256(path) != digest for path, digest in run["inputs"].items()):
        raise ValueError("SHA 기록 중 입력 바이트가 바뀌었다")
    return {"result_path": str(result_path.resolve()), "document_path": str(document_path.resolve()),
            "artifacts_manifest": str(artifacts_path.resolve())}


def main(argv=None):
    parser = argparse.ArgumentParser(description="저장된 개발 측정 저널의 결과·문서·SHA 생성")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--report-only", type=Path)
    mode.add_argument("--check-doc", type=Path)
    mode.add_argument("--verify-artifacts", type=Path)
    parser.add_argument("--section")
    parser.add_argument("--result", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--artifacts-dir", type=Path)
    parser.add_argument("--result-dir", type=Path)
    parser.add_argument("--docs-dir", type=Path)
    parser.add_argument("--m1-result", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.verify_artifacts:
            files = verify_artifacts(args.verify_artifacts)
            output = {"status": "pass", "files": len(files)}
        elif args.check_doc:
            from experiments.v33.lib.report_docs import check_document
            output = check_document(args.check_doc, section=args.section,
                                    result=read_json(args.result) if args.result else None, repo_root=ROOT)
        else:
            if args.plan is None or args.artifacts_dir is None:
                raise ValueError("--plan과 --artifacts-dir가 필요하다")
            journal = args.report_only
            if journal.is_dir():
                paths = list(journal.glob("units_*.jsonl"))
                if len(paths) != 1:
                    raise ValueError("실행 폴더의 저널이 유일하지 않다")
                journal = paths[0]
            output = report_run(journal, plan_path=args.plan,
                raw_dir=args.raw_dir if args.raw_dir else journal.parent,
                artifacts_dir=args.artifacts_dir, m1_result=args.m1_result,
                result_dir=args.result_dir, docs_dir=args.docs_dir)
        print(json.dumps(output, ensure_ascii=False, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
