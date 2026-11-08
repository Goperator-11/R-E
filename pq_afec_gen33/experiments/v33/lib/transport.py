from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from . import arms, netbed


class TransportError(RuntimeError):
    def __init__(self, message, payload=None):
        super().__init__(message)
        self.payload = payload or {}


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hex(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise TransportError("잘못된 SHA256 식별값")
    return value


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise TransportError("JSON 중복 키")
        result[key] = value
    return result


def _constant(value):
    raise TransportError("JSON 비유한수: " + value)


def _json(raw):
    try:
        value = json.loads(raw, object_pairs_hook=_object, parse_constant=_constant)
    except (ValueError, UnicodeDecodeError) as exc:
        raise TransportError("JSON 자료를 읽지 못했다") from exc
    if not isinstance(value, dict) or not value:
        raise TransportError("비어 있지 않은 JSON 객체가 필요하다")
    return value


def _write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _stamp():
    return datetime.now(timezone.utc).isoformat()


class Transport:
    def __init__(self, plan, raw_dir, *, binary_paths=None, plan_sha256=None,
                 run=None, popen=None, sleep=None, monotonic=None):
        self.plan = plan
        self.raw_dir = Path(raw_dir).expanduser().resolve()
        root = (Path.home() / "v33_runs").resolve()
        if self.raw_dir.parent != root or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", self.raw_dir.name):
            raise TransportError("원자료는 ~/v33_runs/<id>/에 둬야 한다")
        provided = binary_paths or {}
        if set(provided) - set(plan["binaries"]):
            raise TransportError("계획에 없는 바이너리 경로")
        self.binary_paths = {key: Path(provided.get(key, info["path"])).expanduser().resolve()
                             for key, info in plan["binaries"].items()}
        self.plan_sha256 = plan_sha256
        self.run = run or subprocess.run
        self.popen = popen or subprocess.Popen
        self.sleep = sleep or time.sleep
        self.monotonic = monotonic or time.monotonic

    def verify_binaries(self, binary_ids=None):
        identities = {}
        for key in sorted(set(binary_ids or self.binary_paths)):
            expected = self.plan["binaries"][key]
            path = self.binary_paths[key]
            digest = _sha(path)
            srcsha = Path(str(path) + ".srcsha").read_text(encoding="utf-8").strip()
            if digest != _hex(expected["sha256"]) or srcsha != _hex(expected["srcsha"]):
                raise TransportError("바이너리 또는 소스 지문 불일치: " + key)
            if not os.access(path, os.X_OK):
                raise TransportError("바이너리 실행 권한 없음: " + key)
            if key == "gen33":
                netbed.require_bin(path)
            identities[key] = {"path": str(path), "sha256": digest, "srcsha": srcsha}
        return identities

    def _contained(self, path):
        path = Path(path).resolve()
        if not path.is_relative_to(self.raw_dir):
            raise TransportError("원자료 경로가 실행 폴더 밖이다")
        return path

    def prepare_certificate(self, unit):
        netbed.require_root()
        if self.plan["arms"][unit["arm"]]["server"] != "gen33":
            return None
        self.verify_binaries(["gen33"])
        for field in ("task", "cell"):
            if not re.fullmatch(r"[A-Za-z0-9_]+", unit[field]):
                raise TransportError("인증서 셀 식별자 오류")
        directory = self._contained(self.raw_dir / "certs")
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        size = unit["profile"]["certsize"]
        stem = f"{unit['task']}_{unit['cell']}_cert_{size}"
        path = self._contained(directory / (stem + ".pem"))
        metadata_path = self._contained(directory / (stem + ".json"))
        if path.exists() or metadata_path.exists():
            if not path.is_file() or not metadata_path.is_file():
                raise TransportError("기존 인증서 또는 metadata가 불완전하다")
            metadata = _json(metadata_path.read_bytes())
        else:
            command = [str(self.binary_paths["gen33"]), "-mode", "certgen", "-certsize", str(size), "-cert-file", str(path)]
            result = self.run(command, capture_output=True, timeout=60)
            if result.returncode:
                raise TransportError("인증서 생성 실패", {"returncode": result.returncode})
            metadata = _json(result.stdout)
            if not path.is_file():
                raise TransportError("인증서 생성 결과 파일 없음")
            self._validate_certificate(path, size, metadata)
            _write_json(metadata_path, metadata)
        self._validate_certificate(path, size, metadata)
        return {"path": str(path), "metadata": metadata}

    def _validate_certificate(self, path, size, metadata):
        if metadata.get("der_bytes") != size or _hex(metadata.get("file_sha256")) != _sha(path):
            raise TransportError("인증서 크기 또는 파일 지문 불일치")
        _hex(metadata.get("der_sha256"))

    def _stop(self, process):
        already_exited = process.poll() is not None
        forced = False
        if not already_exited:
            process.terminate()
        try:
            code = process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            forced = True
            process.kill()
            code = process.wait(timeout=10)
        return {"returncode": code, "forced_kill": forced, "exited_before_stop": already_exited}

    def _ready(self, process, stderr_path):
        deadline = self.monotonic() + 15
        while self.monotonic() < deadline:
            if process.poll() is not None:
                raise TransportError("서버가 READY 전에 종료했다")
            if any(line.startswith(b"READY ") for line in stderr_path.read_bytes().splitlines()):
                return
            self.sleep(0.05)
        raise TransportError("서버 READY 대기 시간 초과")

    def address_for(self, unit):
        arm = self.plan["arms"][unit["arm"]]
        port_slot = arm.get("port_slot", unit["arm"])
        slots = sorted({value.get("port_slot", name) for name, value in self.plan["arms"].items()})
        return f"{netbed.RX_IP}:{netbed.SERVER_PORT + slots.index(port_slot)}"

    def _tc_stats(self, path):
        result = {}
        for direction, command in (
            ("c2s", ["tc", "-s", "qdisc", "show", "dev", netbed.DEV_LOCAL]),
            ("s2c", ["ip", "netns", "exec", netbed.NS, "tc", "-s", "qdisc", "show", "dev", netbed.DEV_PEER]),
        ):
            response = self.run(command, capture_output=True, timeout=10)
            stdout = response.stdout.decode("utf-8", errors="strict")
            stderr = response.stderr.decode("utf-8", errors="strict")
            result[direction] = {"command": command, "stdout": stdout, "stderr": stderr,
                                 "returncode": response.returncode}
        _write_json(path, result)
        if any(item["returncode"] or not item["stdout"].strip() for item in result.values()):
            raise TransportError("tc 상태를 읽지 못했다")
        return result

    def run_unit(self, unit, *, cache_path=None, attempt=0):
        netbed.require_root()
        _hex(self.plan_sha256)
        if type(attempt) is not int or attempt < 0:
            raise TransportError("attempt는 음수가 아닌 정수여야 한다")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", unit["key"]):
            raise TransportError("단위 key 형식 오류")
        arm = self.plan["arms"][unit["arm"]]
        identities = self.verify_binaries([arm["binary"], arm["server"]])
        if cache_path is not None:
            cache_path = self._contained(cache_path)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
        certificate = self.prepare_certificate(unit)
        directory = self._contained(self.raw_dir / "units" / unit["key"] / f"attempt_{attempt}")
        directory.mkdir(parents=True, exist_ok=False)
        paths = {name: directory / filename for name, filename in {
            "client_stdout": "client.jsonl", "client_stderr": "client.stderr",
            "client_stats": "client.stats.json", "server_stdout": "server.stdout",
            "server_stderr": "server.stderr", "server_stats": "server.stats.json",
            "conn_log": "server.conns.jsonl", "tc_before": "tc_before.json",
            "tc_after": "tc_after.json"}.items()}
        address = self.address_for(unit)
        client = arms.client_command(self.plan, unit, binary_paths=self.binary_paths, address=address,
                                     cache=cache_path, stats=paths["client_stats"])
        server = ["ip", "netns", "exec", netbed.NS] + arms.server_command(
            self.plan, unit, binary_paths=self.binary_paths, address=address,
            cert_file=certificate["path"] if certificate else None,
            stats=paths["server_stats"], conn_log=paths["conn_log"])
        has_conn_log = arm["server"] == "gen33" and arm.get("conn_log", True)
        if has_conn_log and (paths["conn_log"].exists() or paths["conn_log"].is_symlink()):
            raise TransportError("새 conn-log 경로가 이미 있다")
        raw_files = {key: str(path) for key, path in paths.items() if key != "conn_log" or has_conn_log}
        payload = {"started_at": _stamp(), "commands": {"client": client, "server": server},
                   "binary_identifiers": identities, "raw_files": raw_files,
                   "client_rc": None, "server": {"returncode": None}}
        process = None
        client_started = False
        failure = None
        try:
            payload["tc_before"] = self._tc_stats(paths["tc_before"])
            with paths["server_stdout"].open("xb") as stdout, paths["server_stderr"].open("xb") as stderr:
                process = self.popen(server, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr)
            payload["server"]["pid"] = process.pid
            self._ready(process, paths["server_stderr"])
            with paths["client_stdout"].open("xb") as stdout, paths["client_stderr"].open("xb") as stderr:
                client_started = True
                result = self.run(client, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                  timeout=self.plan["common"]["timeout_s"] * unit["connections"] + 180)
            payload["client_rc"] = result.returncode
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            failure = exc
        finally:
            if process is not None:
                try:
                    if client_started:
                        self.sleep(arms.settle_s(unit["profile"]))
                    payload["server"].update(self._stop(process))
                except (OSError, subprocess.TimeoutExpired) as exc:
                    failure = failure or exc
            try:
                payload["tc_after"] = self._tc_stats(paths["tc_after"])
            except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
                failure = failure or exc
            payload["ended_at"] = _stamp()
        payload["server"].update({"stats_path": str(paths["server_stats"]),
                                   "stderr_path": str(paths["server_stderr"]),
                                   "conn_log_path": str(paths["conn_log"]) if has_conn_log else None,
                                   "certificate": certificate["metadata"] if certificate else None})
        if failure is not None:
            raise TransportError(str(failure), payload) from failure
        if payload["client_rc"] != 0 or payload["server"]["returncode"] != 0:
            raise TransportError("client 또는 server 종료 코드 오류", payload)
        if payload["server"]["forced_kill"] or payload["server"]["exited_before_stop"]:
            raise TransportError("서버 정상 SIGTERM 종료를 확인하지 못했다", payload)
        try:
            payload["client_stats"] = _json(paths["client_stats"].read_bytes())
            payload["server"]["stats"] = _json(paths["server_stats"].read_bytes())
            if payload["server"]["conn_log_path"] is not None and not paths["conn_log"].is_file():
                raise TransportError("conn-log 파일 없음")
            rows = [_json(line) for line in paths["client_stdout"].read_bytes().splitlines() if line.strip()]
            if len(rows) != unit["rows_expected"]:
                raise TransportError("클라이언트 행 수 불일치")
            provenance = {"binary_sha256": identities[arm["binary"]]["sha256"],
                          "srcsha": identities[arm["binary"]]["srcsha"],
                          "server_binary_sha256": identities[arm["server"]]["sha256"],
                          "server_srcsha": identities[arm["server"]]["srcsha"], "plan_sha256": self.plan_sha256}
            for row in rows:
                for key, value in provenance.items():
                    if key in row and row[key] != value:
                        raise TransportError("클라이언트 행 provenance 충돌")
                row.update(provenance)
            payload["rows"] = rows
        except (OSError, ValueError, RuntimeError) as exc:
            raise TransportError(str(exc), payload) from exc
        return payload
