import json
from pathlib import Path


def load_config(root=None):
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    config = json.loads((root / "genconfig.json").read_text(encoding="utf-8"))
    required = {"gen_id", "build_script", "binary", "install_binary", "wsl_root"}
    if set(config) != required or any(not isinstance(config[k], str) or not config[k] for k in required):
        raise ValueError("invalid generation configuration")
    build = config["build_script"]
    if Path(build).name != build or "/" in build or "\\" in build or not build.endswith(".sh"):
        raise ValueError("build_script must be a shell filename")
    if not config["binary"].startswith(("~/", "/")):
        raise ValueError("binary must be an absolute or home-relative Linux path")
    if not config["install_binary"].startswith("/tmp/") or not config["wsl_root"].startswith("/mnt/"):
        raise ValueError("invalid generation installation or WSL path")
    return config
