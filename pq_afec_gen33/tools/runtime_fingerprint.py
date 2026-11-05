import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def code_fingerprint(root, paths):
    root = Path(root).resolve(strict=True)
    files = {}
    for name in paths:
        path = (root / name).resolve(strict=True)
        relative = path.relative_to(root).as_posix()
        if relative in files:
            raise ValueError("duplicate code input")
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not files:
        raise ValueError("empty code input inventory")
    return {"code_fp": digest(files), "files": files}


def environment(root=ROOT):
    autocrlf = subprocess.run(["git", "-C", str(root), "config", "--get", "core.autocrlf"], capture_output=True, text=True)
    packages = {}
    for name in ("pytest", "matplotlib", "cryptography", "scipy"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    go = shutil.which("go")
    go_version = None
    if go:
        result = subprocess.run([go, "version"], capture_output=True, text=True, timeout=10,
                                env={**os.environ, "GOTOOLCHAIN": "local"})
        go_version = result.stdout.strip() if result.returncode == 0 else None
    return {"python": platform.python_version(), "implementation": platform.python_implementation(),
            "executable": str(Path(sys.executable).resolve()), "platform": platform.platform(),
            "machine": platform.machine(), "packages": packages, "go": {"executable": go, "version": go_version},
            "go_environment": {name: os.environ.get(name) for name in ("GOROOT", "GOPATH", "GOFLAGS", "GOAMD64", "GOTOOLCHAIN", "CGO_ENABLED")},
            "wsl_distro": os.environ.get("WSL_DISTRO_NAME"),
            "selected_wsl_distro": os.environ.get("PADFEC_WSL_DISTRO", "Ubuntu"),
            "autocrlf": autocrlf.stdout.strip() if autocrlf.returncode == 0 else None,
            "padfec": {key: value for key, value in sorted(os.environ.items()) if key.startswith("PADFEC_")}}


def make(root, paths, env=None):
    observed = environment(root) if env is None else env
    return {"schema": "padfec.runtime_fingerprint/1", **code_fingerprint(root, paths),
            "env_fp": digest(observed), "environment": observed}


def compare(previous, current):
    if previous.get("schema") != current.get("schema") or current.get("schema") != "padfec.runtime_fingerprint/1":
        raise ValueError("fingerprint schema differs")
    code_changed = previous["code_fp"] != current["code_fp"]
    env_changed = previous["env_fp"] != current["env_fp"]
    return {"code_changed": code_changed, "environment_changed": env_changed,
            "reuse_allowed": not code_changed and not env_changed,
            "remeasure_required": code_changed, "remeasure_recommended": env_changed}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args(argv)
    result = make(args.root, args.paths)
    if args.previous:
        result["comparison"] = compare(json.loads(args.previous.read_text(encoding="utf-8")), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
