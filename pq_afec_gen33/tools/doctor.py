import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.runtime_fingerprint import environment


def inspect(root=ROOT):
    root = Path(root).resolve()
    env = environment(root)
    paths = {name: (root / name).is_file() for name in ("pytest.ini", "requirements.txt", "experiments/quicbed/go.mod", "experiments/quicbed/go.sum", "experiments/quicbed/build_gen33.sh")}
    versions = {}
    for name in ("pytest", "matplotlib", "cryptography", "scipy"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    distro = env["selected_wsl_distro"]
    if os.name == "nt":
        result = subprocess.run(["wsl", "-d", distro, "--", "printenv", "WSL_DISTRO_NAME"], capture_output=True, text=True, timeout=20)
        observed = result.stdout.strip() if result.returncode == 0 else None
    else:
        observed = env["wsl_distro"]
    problems = ["missing path: " + name for name, found in paths.items() if not found]
    problems.extend("missing package: " + name for name, version in versions.items() if version is None)
    if (os.name == "nt" or env["wsl_distro"]) and observed != distro:
        problems.append("configured WSL distribution differs from observed distribution")
    return {"status": "FAIL" if problems else "PASS", "root": str(root), "environment": env,
            "observed_wsl_distro": observed, "paths": paths, "packages": versions, "problems": problems}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    result = inspect()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(bool(result["problems"]))


if __name__ == "__main__":
    raise SystemExit(main())
