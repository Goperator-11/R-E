from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from padfec3 import learn3
from experiments.v33.lib import arms, blocks, observations, report


class PlanError(ValueError):
    pass


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PlanError(f"계획 JSON 중복 키: {key}")
        result[key] = value
    return result


def reject_constant(value):
    raise PlanError(f"계획 JSON 비유한수: {value}")


def read_plan(path):
    raw = Path(path).read_bytes()
    plan = json.loads(raw.decode("utf-8"), object_pairs_hook=strict_object,
                      parse_constant=reject_constant)
    if not isinstance(plan, dict) or plan.get("schema") != "padfec3.final_bundle.v1":
        raise PlanError("지원하지 않는 계획 schema")
    if plan.get("label") != "development" or plan.get("confirmatory") is not False:
        raise PlanError("계획은 development, confirmatory=false여야 한다")
    if plan.get("policy_version") != learn3.POLICY_VERSION:
        raise PlanError("계획 policy_version이 활성 정책과 다르다")
    if plan.get("state_version") != learn3.STATE_VERSION:
        raise PlanError("계획 state_version이 활성 정책과 다르다")
    if plan.get("cache_schema") != f"padfec3.cache3/{learn3.STATE_VERSION}":
        raise PlanError("계획 cache_schema가 활성 상태와 다르다")
    for key in ("precommit", "binaries", "common", "ordering", "profiles", "arms", "tasks"):
        if not isinstance(plan.get(key), dict) or not plan[key]:
            raise PlanError(f"계획 {key}가 비어 있거나 객체가 아니다")
    for name, info in plan["binaries"].items():
        if not isinstance(info, dict) or not isinstance(info.get("path"), str) or not info["path"]:
            raise PlanError(f"바이너리 경로 누락: {name}")
        for field in ("sha256", "srcsha"):
            value = info.get(field)
            if value is not None and (not isinstance(value, str) or not re.fullmatch("[0-9a-f]{64}", value)):
                raise PlanError(f"바이너리 {field} 형식 오류: {name}")
    return plan, hashlib.sha256(raw).hexdigest()


def require_binary_identifiers(plan):
    for name, info in plan["binaries"].items():
        for field in ("sha256", "srcsha"):
            if not isinstance(info.get(field), str) or not re.fullmatch("[0-9a-f]{64}", info[field]):
                raise PlanError(f"실행할 수 없다: 바이너리 {name}.{field}가 미확정이다")


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), "--no-optional-locks", *args],
                            capture_output=True, timeout=30,
                            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
    if result.returncode:
        raise PlanError("git 확인 실패: " + result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def committed_file(root, path):
    root = Path(root).resolve()
    path = Path(path).resolve()
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise PlanError("계획 파일이 저장소 밖에 있다") from exc
    git(root, "ls-files", "--error-unmatch", "--", relative)
    status = git(root, "status", "--porcelain=v1", "--untracked-files=all", "--", relative)
    if status.strip():
        raise PlanError(f"커밋하지 않은 계획 변경: {relative}")
    commit = git(root, "log", "-1", "--format=%H", "--", relative).decode("ascii").strip()
    if not re.fullmatch("[0-9a-f]{40,64}", commit):
        raise PlanError(f"계획의 변경 커밋이 없다: {relative}")
    git(root, "cat-file", "-e", commit + "^{commit}")
    blob = git(root, "show", f"{commit}:{relative}")
    current = path.read_bytes()
    if blob != current:
        raise PlanError(f"계획 파일 바이트가 마지막 변경 커밋과 다르다: {relative}")
    committed_at = int(git(root, "show", "-s", "--format=%ct", commit).strip())
    return {"path": relative, "commit": commit,
            "sha256": hashlib.sha256(current).hexdigest(), "committed_at": committed_at}


def verify_committed_plan(path, plan, plan_sha256, root=None):
    root = Path(root if root is not None else ROOT).resolve()
    paths = plan["precommit"].get("plan_paths")
    if not isinstance(paths, list) or len(paths) != 2 or len(set(paths)) != 2:
        raise PlanError("계획 JSON과 문서의 plan_paths 두 개가 필요하다")
    if any(not isinstance(value, str) or not value for value in paths):
        raise PlanError("plan_paths 형식 오류")
    selected = Path(path).resolve()
    if (root / paths[0]).resolve() != selected or Path(paths[1]).suffix != ".md":
        raise PlanError("선택한 계획 JSON 또는 companion 문서 경로가 plan_paths와 다르다")
    records = [committed_file(root, root / value) for value in paths]
    if records[0]["sha256"] != plan_sha256:
        raise PlanError("읽은 뒤 계획 파일이 바뀌었다")
    return {"plan_commit": records[0]["commit"], "plan_sha256": records[0]["sha256"],
            "plan_doc_commit": records[1]["commit"], "plan_doc_sha256": records[1]["sha256"],
            "plan_files": records}


def require_plan_before_start(provenance, started_at):
    started = datetime.fromisoformat(started_at)
    if started.tzinfo is None:
        raise PlanError("첫 단위 started_at에는 timezone이 필요하다")
    if any(info["committed_at"] >= started.timestamp() for info in provenance["plan_files"]):
        raise PlanError("계획 변경 커밋 시각이 첫 단위 started_at보다 앞서지 않는다")


def planned_summary(plan, plan_sha256, task_ids=None):
    selected = arms.selected_tasks(plan, task_ids)
    units = arms.iter_units(plan, selected)
    summaries = []
    for task_id in selected:
        task = plan["tasks"][task_id]
        task_units = [unit for unit in units if unit["task"] == task_id]
        cells = []
        for cell in task["cells"] + task.get("additional_cells", []):
            subset = [unit for unit in task_units if unit["cell"] == cell["id"]]
            cells.append({"cell": cell["id"], "arms": cell["arms"],
                          "trajectories": cell["trajectories"], "units": len(subset),
                          "connections": sum(unit["connections"] for unit in subset),
                          "burnin_connections": sum(unit["burnin_connections"] for unit in subset),
                          "warmup_connections": sum(unit["warmup_connections"] for unit in subset),
                          "measured_connections": sum(unit["measured_connections"] for unit in subset)})
        summaries.append({"task": task_id, "cells": cells,
                          "connections": sum(cell["connections"] for cell in cells),
                          "expected_minutes": task["expected_minutes"] + task.get("additional_expected_minutes", 0)})
    required = sum(task["connections_total"] for task in plan["tasks"].values())
    additional = sum(task.get("additional_connections_total", 0) for task in plan["tasks"].values())
    if required != plan["required_connections_total"] or additional != plan["required_additional_connections_total"]:
        raise PlanError("계획의 required 연결 합계가 맞지 않는다")
    expected = sum(task["expected_minutes"] + task.get("additional_expected_minutes", 0)
                   for task in plan["tasks"].values())
    if expected != plan["expected_required_minutes"]:
        raise PlanError("계획의 예상 시간 합계가 맞지 않는다")
    return {"schema": "padfec3.devbed.dry_run/1", "label": "development", "confirmatory": False,
            "policy_version": learn3.POLICY_VERSION, "plan_sha256": plan_sha256,
            "kind": "계획, 측정값 아님", "tasks": summaries, "units": len(units),
            "connections": sum(task["connections"] for task in summaries),
            "expected_minutes": sum(task["expected_minutes"] for task in summaries),
            "optional": [{"task": task["id"], "requires_subplan": task.get("requires_subplan", False),
                          "enabled": False} for task in plan.get("optional", [])]}


def collect_environment(run=subprocess.run):
    environment = {}
    for name, command in (("uname_r", ["uname", "-r"]),
                          ("python3_V", [sys.executable, "-I", "-B", "--version"]),
                          ("tc_V", ["tc", "-V"]), ("ip_V", ["ip", "-V"])):
        result = run(command, capture_output=True, text=True, encoding="utf-8", timeout=10)
        value = (result.stdout or result.stderr).strip()
        if result.returncode or not value:
            raise PlanError(f"환경 정보 수집 실패: {name}")
        environment[name] = value
    environment["cpu_list"] = sorted(os.sched_getaffinity(0))
    environment["cpu_count"] = os.cpu_count()
    if not environment["cpu_list"] or not environment["cpu_count"]:
        raise PlanError("CPU 환경 정보가 비어 있다")
    return environment


def load_reporter():
    try:
        module = importlib.import_module("experiments.v33.devreport")
    except ModuleNotFoundError as exc:
        if exc.name != "experiments.v33.devreport":
            raise PlanError("F24 결과 생성기 의존성이 없다: " + str(exc.name)) from exc
        raise PlanError("F24 결과 생성기가 없어 측정을 시작할 수 없다") from exc
    function = getattr(module, "report_run", None)
    if not callable(function):
        raise PlanError("F24 결과 생성기의 report_run 연결이 없다")
    return function


def write_new_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def run_paths(args, task):
    if not args.run_id:
        if args.resume or args.report_only:
            raise PlanError("재개와 report-only에는 --run-id가 필요하다")
        args.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8]
    if args.lock is None or args.artifacts_dir is None:
        raise PlanError("--lock과 --artifacts-dir가 필요하다")
    expected = (Path.home() / "v33_runs" / args.run_id).resolve()
    raw = args.raw_dir.resolve() if args.raw_dir is not None else expected
    if raw != expected:
        raise PlanError("원자료는 ~/v33_runs/<run-id>/에 두어야 한다")
    return {"raw": raw, "manifest": raw / f"manifest_{args.run_id}.json",
            "journal": raw / f"units_{args.run_id}.jsonl",
            "status": raw / f"status_{args.run_id}.json",
            "done": raw / f"DONE_{args.run_id}", "task": task}


def verify_report_artifacts(result, journal_path, raw_files=()):
    if not isinstance(result, dict) or not {"result_path", "artifacts_manifest"} <= result.keys():
        raise PlanError("결과 생성기가 결과·SHA 목록 경로를 반환하지 않았다")
    manifest = Path(result["artifacts_manifest"]).resolve()
    found = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64}) [ *](.+)", line)
        if match is None:
            raise PlanError("SHA 목록 형식 오류")
        path = (manifest.parent / match.group(2)).resolve()
        if path in found or path.suffix.lower() == ".pem":
            raise PlanError("SHA 목록의 중복 경로 또는 PEM 반출")
        found.add(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != match.group(1):
            raise PlanError("SHA 목록 검증 실패: " + str(path))
    required = {Path(journal_path).resolve(), Path(result["result_path"]).resolve()}
    required.update(Path(path).resolve() for path in raw_files)
    if not required <= found:
        raise PlanError("SHA 목록에 결과·저널·원자료 로그가 빠졌다")
    summary = json.loads(Path(result["result_path"]).read_text(encoding="utf-8"))
    if summary.get("label") != "development" or summary.get("confirmatory") is not False:
        raise PlanError("결과의 development 표지가 잘못됐다")
    if summary.get("policy_version") != learn3.POLICY_VERSION:
        raise PlanError("결과 policy_version이 활성 정책과 다르다")


def m1_dependency(plan, task_id, path, plan_sha256):
    required = set(plan["statistics"]["aa_ruler"]["tasks"]) | set(plan["statistics"]["sealed_drift"]["apply_to"])
    if task_id not in required:
        if path is not None:
            raise PlanError("이 과제는 M1 결과를 입력받지 않는다")
        return None
    if path is None:
        raise PlanError("이 과제는 --m1-result가 필요하다")
    raw = Path(path).read_bytes()
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=strict_object, parse_constant=reject_constant)
    report.validate_m1_result(value, plan, plan_sha256)
    return {"sha256": hashlib.sha256(raw).hexdigest(), "result": value}


def unit_validator(plan, provenance, raw_dir, backend):
    def validate(unit, payload):
        require_plan_before_start(provenance, payload["started_at"])
        if payload.get("client_rc") != 0 or payload["server"].get("returncode") != 0:
            raise PlanError("완료 단위의 client 또는 server 종료 코드가 0이 아니다")
        arm = plan["arms"][unit["arm"]]
        for row in payload["rows"]:
            if type(row.get("ok")) is not bool:
                raise PlanError("클라이언트 행의 ok가 없다")
            if type(row.get("ms")) not in (int, float) or not math.isfinite(row["ms"]) or row["ms"] < 0:
                raise PlanError("클라이언트 행의 HCT가 유효하지 않다")
            for name, expected in (("plan_sha256", provenance["plan_sha256"]),
                                   ("binary_sha256", plan["binaries"][arm["binary"]]["sha256"]),
                                   ("srcsha", plan["binaries"][arm["binary"]]["srcsha"])):
                if row.get(name) != expected:
                    raise PlanError("클라이언트 행 지문 불일치: " + name)
        hashes = payload.get("raw_sha256")
        if not isinstance(hashes, dict) or not hashes:
            raise PlanError("완료 단위의 원자료 지문이 없다")
        for relative, expected in hashes.items():
            path = (raw_dir / relative).resolve()
            if not path.is_relative_to(raw_dir.resolve()) or path.suffix.lower() == ".pem":
                raise PlanError("원자료 경로 범위 오류")
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise PlanError("완료 단위 원자료 지문 불일치")
        expected = collection_validation(plan, unit, payload)
        if payload.get("collection") != expected:
            raise PlanError("저장된 수집 검사와 원자료 재검사가 다르다")
        if expected["execution_status"] == "자료 없음" or expected["reject_block"]:
            raise PlanError("완료 단위에 수집 실패 또는 버릴 블록이 있다")
        checks = {**expected["checks"], "ips": "pass" if "ips" not in arm or all(
            row.get("ips_eff") == arm["ips"] for row in payload["rows"]) else "fail"}
        if (payload.get("checks") != checks
                or payload.get("server_delta") != expected["server"]["server_delta"]
                or payload.get("execution_status") != report.execution_status(has_data=True, checks=checks)):
            raise PlanError("저장된 단위 집계가 수집 검사와 다르다")
        if unit["cache_key"] is not None:
            report.validate_cache_bytes(blocks.snapshot_bytes(payload["cache_after"]), arms.client_family(plan, arm),
                                        expected_address=backend.address_for(unit))
    return validate


def collection_validation(plan, unit, payload):
    server = report.validate_server_unit(plan, unit, payload)
    try:
        observed = observations.unit_observations(plan, unit, payload)
    except (KeyError, TypeError, ValueError) as exc:
        observed = {"checks": {"observations": "missing"}, "error": str(exc)}
    checks = {**server["checks"], **observed["checks"]}
    return {"server": server, "observations": observed, "checks": checks,
            "execution_status": report.execution_status(has_data=True, checks=checks),
            "reject_block": server["reject_block"]}


def _next_block(units, offset):
    first = units[offset]
    fields = ("task", "cell", "trajectory", "phase", "block")
    key = tuple(first[field] for field in fields)
    result = []
    for unit in units[offset:]:
        if tuple(unit[field] for field in fields) != key:
            break
        result.append(unit)
    return result


def execute_run(args, plan, provenance, *, reporter, backend_factory=None,
                environment_collector=collect_environment, net=None):
    if net is None:
        from experiments.v33.lib import netbed as net
    if backend_factory is None:
        from experiments.v33.lib.transport import Transport
        backend_factory = Transport
    selected = ["M0"] if args.smoke else arms.selected_tasks(plan, args.task)
    if len(selected) != 1:
        raise PlanError("측정은 --task로 한 과제씩 실행한다")
    task_id = selected[0]
    dependency = m1_dependency(plan, task_id, args.m1_result, provenance["plan_sha256"])
    units = arms.iter_units(plan, selected)
    paths = run_paths(args, task_id)
    raw = paths["raw"]
    fingerprint = blocks.fingerprint(ROOT, provenance["plan_sha256"], plan["binaries"])
    binary_paths = {}
    for value in args.binary or []:
        name, separator, path = value.partition("=")
        if not separator or name not in plan["binaries"] or name in binary_paths or not path:
            raise PlanError("--binary는 중복 없는 binary ID=경로여야 한다")
        binary_paths[name] = Path(path).expanduser().resolve()
    backend = backend_factory(plan, raw, binary_paths=binary_paths or None,
                              plan_sha256=provenance["plan_sha256"])
    validator = unit_validator(plan, provenance, raw, backend)
    manifest = None
    if args.resume or args.report_only:
        manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
        if (manifest.get("run_id") != args.run_id or manifest.get("task") != task_id
                or manifest.get("fingerprint") != fingerprint or manifest.get("provenance") != provenance
                or manifest.get("m1_dependency") != dependency):
            raise PlanError("재개 manifest의 실행·계획·지문이 다르다")
        journal = blocks.UnitJournal(paths["journal"], args.run_id, fingerprint, units,
                                     resume=True, validator=validator)
        if journal.metadata != manifest["meta"]:
            raise PlanError("저널과 manifest의 metadata가 다르다")
        if args.report_only and not journal.complete:
            raise PlanError("report-only는 모든 단위가 완료된 저널이 필요하다")
    else:
        if raw.exists() and any(path.name != "bin" for path in raw.iterdir()):
            raise PlanError("같은 run ID의 원자료가 이미 있다")
        raw.mkdir(parents=True, exist_ok=True)
    minutes = plan["tasks"][task_id]["expected_minutes"] + plan["tasks"][task_id].get("additional_expected_minutes", 0)
    now = datetime.now(timezone(timedelta(hours=9)))
    lock = blocks.MeasurementLock(args.lock, paths["status"], paths["done"],
                                 task=plan["tasks"][task_id]["card"], run_id=args.run_id,
                                 expected_end_kst=(now + timedelta(minutes=minutes)).isoformat(),
                                 resume=args.resume or args.report_only)
    lock.start()
    try:
        resume_command = [sys.executable, "-I", "-B", str(Path(__file__).resolve()),
                          "--plan", str(args.plan.resolve()), "--task", task_id,
                          "--run-id", args.run_id, "--raw-dir", str(raw),
                          "--lock", str(args.lock.resolve()), "--artifacts-dir", str(args.artifacts_dir.resolve()), "--resume"]
        for value in args.binary or []:
            resume_command += ["--binary", value]
        if args.m1_result is not None:
            resume_command += ["--m1-result", str(args.m1_result.resolve())]
        lock.update(resume_command=resume_command, measurement_task=task_id)
        if not args.report_only:
            net.require_root()
            setup = net.setup()
            backend.verify_binaries()
            if manifest is None:
                meta = report.capture_metadata({"task": task_id, "run_id": args.run_id,
                    "env": environment_collector(), "netbed": setup, "m1_dependency": dependency,
                    "runtime_context": {"python": sys.version, "executable": sys.executable},
                    **provenance, "binary_sha256": {name: info["sha256"] for name, info in plan["binaries"].items()},
                    "srcsha": {name: info["srcsha"] for name, info in plan["binaries"].items()}})
                manifest = {"run_id": args.run_id, "task": task_id, "fingerprint": fingerprint,
                            "provenance": provenance, "meta": meta, "plan": plan, "m1_dependency": dependency}
                write_new_json(paths["manifest"], manifest)
                journal = blocks.UnitJournal(paths["journal"], args.run_id, fingerprint, units,
                                             metadata=meta, validator=validator)
            attempts = raw / "attempts"
            attempts.mkdir(exist_ok=True)
            attempt = 0
            while (attempts / str(attempt)).exists():
                attempt += 1
            attempt_dir = attempts / str(attempt)
            attempt_dir.mkdir()
            cache_paths = {}
            for unit in units:
                key = unit["cache_key"]
                if key is not None and key not in cache_paths:
                    path = attempt_dir / (key + ".json")
                    blocks.restore_cache(path, journal.cache_after(key))
                    cache_paths[key] = path
            while not journal.complete:
                entries = []
                for unit in _next_block(units, journal.next_index):
                    lock.check()
                    lock.update(unit=unit["key"], completed_units=journal.next_index, total_units=len(units))
                    net.set_netem(unit["profile"]["rtt_ms"] / 2,
                        loss_c2s=unit["loss_c2s_pct"], loss_s2c=unit["loss_s2c_pct"],
                        rate_up_mbit=unit["profile"]["netem_uplink_mbps"],
                        journal=lambda event, key=unit["key"]: journal.record_event(key, "netem", {"attempt": attempt, **event}))
                    started = datetime.now(timezone.utc).isoformat()
                    require_plan_before_start(provenance, started)
                    journal.record_event(unit["key"], "started", {"attempt": attempt, "started_at": started})
                    try:
                        payload = backend.run_unit(unit, cache_path=cache_paths.get(unit["cache_key"]), attempt=attempt)
                    except Exception as exc:
                        journal.record_event(unit["key"], "failed", {"attempt": attempt, "error": str(exc),
                            "execution_status": "자료 없음", "diagnostics": getattr(exc, "payload", {})})
                        raise
                    payload["attempt"] = attempt
                    payload["cache_after"] = blocks.snapshot_cache(cache_paths[unit["cache_key"]]) if unit["cache_key"] is not None else None
                    payload["raw_sha256"] = {}
                    for path in payload["raw_files"].values():
                        path = Path(path).resolve()
                        relative = path.relative_to(raw.resolve()).as_posix()
                        if path.suffix.lower() == ".pem":
                            raise PlanError("PEM을 단위 원자료 목록에 넣을 수 없다")
                        payload["raw_sha256"][relative] = hashlib.sha256(path.read_bytes()).hexdigest()
                    arm = plan["arms"][unit["arm"]]
                    collection = collection_validation(plan, unit, payload)
                    payload["collection"] = collection
                    payload["server_delta"] = collection["server"]["server_delta"]
                    payload.setdefault("checks", {}).update(collection["checks"])
                    payload.setdefault("checks", {})["ips"] = (
                        "pass" if "ips" not in arm or all(row.get("ips_eff") == arm["ips"] for row in payload["rows"]) else "fail")
                    payload["execution_status"] = report.execution_status(has_data=True, checks=payload["checks"])
                    if collection["execution_status"] == "자료 없음" or collection["reject_block"]:
                        journal.record_event(unit["key"], "unit_rejected", {"attempt": attempt,
                            "block_keys": [item["key"] for item in _next_block(units, journal.next_index)],
                            "payload": payload})
                        raise PlanError("단위 수집 검사 실패: " + collection["execution_status"])
                    entries.append({"key": unit["key"], "payload": payload})
                journal.record_block(entries)
                lock.check()
        lock.update(completed_units=journal.next_index, total_units=len(units))
        lock.mark_measurement_done()
        lock.check()
        if m1_dependency(plan, task_id, args.m1_result, provenance["plan_sha256"]) != dependency:
            raise PlanError("M1 입력이 측정 중 바뀌었다")
        raw_files = [raw / relative for entry in journal.records for relative in entry["payload"]["raw_sha256"]]
        sealed_inputs = {paths["journal"]: hashlib.sha256(paths["journal"].read_bytes()).hexdigest(),
                         paths["manifest"]: hashlib.sha256(paths["manifest"].read_bytes()).hexdigest()}
        for entry in journal.records:
            sealed_inputs.update({raw / relative: digest for relative, digest in entry["payload"]["raw_sha256"].items()})
        result = reporter(paths["journal"], plan_path=args.plan.resolve(), raw_dir=raw,
                          artifacts_dir=args.artifacts_dir.resolve(), m1_result=args.m1_result)
        if any(hashlib.sha256(path.read_bytes()).hexdigest() != digest for path, digest in sealed_inputs.items()):
            raise PlanError("결과 생성 중 원자료 또는 저널 바이트가 바뀌었다")
        if m1_dependency(plan, task_id, args.m1_result, provenance["plan_sha256"]) != dependency:
            raise PlanError("결과 생성 중 M1 입력이 바뀌었다")
        verify_report_artifacts(result, paths["journal"], raw_files)
        lock.finish_report_success()
        return result
    except BaseException as exc:
        try:
            lock.update(state="failed", error=str(exc))
        except (OSError, ValueError, RuntimeError):
            pass
        raise
    finally:
        lock.close()


def parser():
    value = argparse.ArgumentParser(description="gen33 개발 측정 계획과 재개 입력 검사")
    value.add_argument("--plan", type=Path, required=True)
    mode = value.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--smoke", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--report-only", action="store_true")
    value.add_argument("--resume", action="store_true")
    value.add_argument("--task", action="append")
    value.add_argument("--run-id")
    value.add_argument("--raw-dir", type=Path)
    value.add_argument("--lock", type=Path)
    value.add_argument("--artifacts-dir", type=Path)
    value.add_argument("--m1-result", type=Path)
    value.add_argument("--binary", action="append")
    return value


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if not any((args.dry_run, args.smoke, args.run, args.report_only, args.resume)):
            raise PlanError("--dry-run, --smoke, --run, --resume, --report-only 중 모드가 필요하다")
        if args.resume and (args.dry_run or args.report_only):
            raise PlanError("--resume은 측정 실행 모드에서만 쓴다")
        if args.smoke and args.task not in (None, ["M0"]):
            raise PlanError("--smoke는 계획의 M0만 실행한다")
        if args.run_id is not None and not re.fullmatch("[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", args.run_id):
            raise PlanError("run ID 형식 오류")
        plan, plan_sha256 = read_plan(args.plan)
        tasks = ["M0"] if args.smoke else args.task
        summary = planned_summary(plan, plan_sha256, tasks)
        if args.dry_run:
            print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))
            return 0
        require_binary_identifiers(plan)
        provenance = verify_committed_plan(args.plan, plan, plan_sha256)
        result = execute_run(args, plan, provenance, reporter=load_reporter())
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
