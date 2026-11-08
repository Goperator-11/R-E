from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from experiments.v33 import devbed
from experiments.v33.lib import blocks
from experiments.v33.lib.transport import Transport


class StageError(RuntimeError):
    pass


def require_linux():
    if not sys.platform.startswith("linux"):
        raise StageError("준비는 Ubuntu WSL 안에서 실행해야 한다")


def ensure_idle():
    result = subprocess.run(["pgrep", "-af", "devbed"], capture_output=True,
                            text=True, encoding="utf-8", timeout=15)
    if result.returncode == 0:
        raise StageError("살아 있는 devbed가 있어 시작하지 않는다: " + result.stdout.strip())
    if result.returncode != 1 or result.stdout.strip() or result.stderr.strip():
        raise StageError("devbed 프로세스 조회 실패: " + result.stderr.strip())


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_plain_path(path, base):
    path = Path(path)
    base = Path(base)
    path.relative_to(base)
    current = path
    while current != base:
        if current.is_symlink():
            raise StageError("실행 사본 경로에 symlink가 있다: " + str(current))
        current = current.parent
    if base.is_symlink() or not path.resolve().is_relative_to(base.resolve()):
        raise StageError("실행 사본 경로가 보존 폴더 밖이다")


def copy_new_or_verify(source, target, *, copy, resume, executable=False):
    source = Path(source)
    target = Path(target)
    if target.exists():
        if not target.is_file() or sha256(source) != sha256(target):
            raise StageError("기존 실행 사본이 원본과 다르다: " + str(target))
        return
    if resume:
        raise StageError("재개할 실행 사본이 없다: " + str(target))
    if not copy:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as reader, target.open("xb") as writer:
        shutil.copyfileobj(reader, writer)
        writer.flush()
        os.fsync(writer.fileno())
    if executable:
        target.chmod(source.stat().st_mode & 0o777)
    if sha256(source) != sha256(target):
        raise StageError("복사한 실행 사본의 SHA가 다르다: " + str(target))


def prepare(config, *, copy=True):
    require_linux()
    ensure_idle()
    run_id = config["run_id"]
    mode = config["mode"]
    task = config["task"]
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", run_id):
        raise StageError("run ID 형식 오류")
    if mode not in {"smoke", "run", "resume", "report-only"}:
        raise StageError("지원하지 않는 실행 모드")
    if mode == "smoke" and task != "M0":
        raise StageError("smoke는 M0만 실행한다")
    plan_path = Path(config["plan"])
    lock_path = Path(config["lock"])
    artifacts = Path(config["artifacts_dir"])
    if not all(path.is_absolute() for path in (plan_path, lock_path, artifacts)):
        raise StageError("계획·잠금·산출물 경로는 절대 경로여야 한다")
    plan, plan_sha = devbed.read_plan(plan_path)
    if plan_sha != config["plan_sha256"]:
        raise StageError("launcher가 읽은 계획 SHA와 다르다")
    devbed.require_binary_identifiers(plan)
    provenance = devbed.verify_committed_plan(plan_path, plan, plan_sha)
    devbed.planned_summary(plan, plan_sha, [task])
    devbed.load_reporter()
    m1_path = Path(config["m1_result"]) if config.get("m1_result") else None
    if m1_path is not None and not m1_path.is_absolute():
        raise StageError("M1 결과 경로는 절대 경로여야 한다")
    dependency = devbed.m1_dependency(plan, task, m1_path, plan_sha)
    base = Path.home() / "v33_runs"
    raw = base / run_id
    require_plain_path(raw, Path.home())
    for key, path in (("raw_dir", raw), ("status_file", raw / f"status_{run_id}.json"),
                      ("done_marker", raw / f"DONE_{run_id}")):
        if key in config and config[key] != str(path):
            raise StageError("launcher 실행 경로가 다르다: " + key)
    resume = mode in {"resume", "report-only"}
    if lock_path.exists() and mode != "report-only":
        raise StageError("측정 잠금이 남아 있다. 사망 확인과 잠금 처리가 먼저다")
    if resume:
        manifest = json.loads((raw / f"manifest_{run_id}.json").read_text(encoding="utf-8"))
        if (manifest.get("run_id") != run_id or manifest.get("task") != task
                or manifest.get("provenance") != provenance
                or manifest.get("fingerprint") != blocks.fingerprint(devbed.ROOT, plan_sha, plan["binaries"])
                or manifest.get("m1_dependency") != dependency):
            raise StageError("재개 manifest의 실행·계획·지문이 다르다")
    elif raw.exists() and any(path.name != "bin" for path in raw.iterdir()):
        raise StageError("같은 run ID의 원자료가 이미 있다")
    sources = {name: Path(info["path"]).expanduser().resolve()
               for name, info in plan["binaries"].items()}
    Transport(plan, raw, binary_paths=sources, plan_sha256=plan_sha).verify_binaries()
    targets = {}
    transfers = []
    for name in sorted(sources):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name):
            raise StageError("바이너리 ID 형식 오류")
        source = sources[name]
        target = raw / "bin" / name / "qamp"
        targets[name] = target
        suffixes = ["", ".srcsha"] + ([".sha256"] if name == "gen33" else [])
        for suffix in suffixes:
            destination = Path(str(target) + suffix)
            require_plain_path(destination, Path.home())
            transfers.append((Path(str(source) + suffix), destination, not suffix))
    for source, target, executable in transfers:
        copy_new_or_verify(source, target, copy=False, resume=resume, executable=executable)
    if copy:
        for source, target, executable in transfers:
            copy_new_or_verify(source, target, copy=True, resume=resume, executable=executable)
    if copy or all(target.exists() for source, target, executable in transfers):
        Transport(plan, raw, binary_paths=targets, plan_sha256=plan_sha).verify_binaries()
    command = ["unshare", "-Urnm", sys.executable, "-I", "-B", str(Path(devbed.__file__).resolve()),
               "--plan", str(plan_path), "--task", task, "--run-id", run_id,
               "--raw-dir", str(raw), "--lock", str(lock_path), "--artifacts-dir", str(artifacts)]
    command += ["--" + mode]
    for name, target in sorted(targets.items()):
        command += ["--binary", name + "=" + str(target)]
    if m1_path is not None:
        command += ["--m1-result", str(m1_path)]
    return {"raw_dir": str(raw), "binary_paths": {name: str(path) for name, path in targets.items()},
            "status_file": str(raw / f"status_{run_id}.json"),
            "done_marker": str(raw / f"DONE_{run_id}"), "command": command,
            "plan_sha256": plan_sha, "provenance": provenance, "copied": copy}
