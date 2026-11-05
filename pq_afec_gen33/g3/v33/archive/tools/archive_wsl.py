import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")

ARCHIVE = Path("/mnt/c/dev/padfec_archive")
FROZEN = Path("/home/scien/frozen")
SPECS = (
    ("g2", "quicbed", "d98b05d73f44774ad622ab1c4993526cac58957b22310fc61122d7bd44964213", "b181677970b7dd4338099f37c6837b8bc4aacff3caa1a186b9a2c6c442f2be19"),
    ("g3", "quicbed_g3", "d519b331962cbcf2103bf572d228cfb199eae4e588eedf93f8305c0d95b01f91", "2b34636865dbf64308d20a5382801894d460f02219f485b4a493377d78e5f01c"),
    ("g3b", "quicbed_g3b", "ad5246f361ababca2f477724b047d4db75c3e95412368428c793c008b3f9c31e", "1d331c2fb3944c2ae416ee0e6f9a0616c7b431248dd3bf9cc59d1ed70417a85f"),
    ("g3c", "quicbed_g3c", "6baf2b5235d9906062d524af708ee28f06b2c20fa11c64fbc8bb51bc7f274d9b", "6284fdcf2d324bae4aee6aef56d7f339aa01c3b267e3aa3225277e7c87b3ade4"),
    ("gen32", "quicbed_gen32", "85f54cf578f45d5e61dfff85f4677c6d0bc9c638a322ae143662ae67cb2c2e8e", "9347504139a17614bf56a836e175ae9d8cd2e5cffd800503b9c2fcaf8fdb57f9"),
)


def immutable_bytes(path, data):
    if path.is_symlink() or not path.resolve().is_relative_to(ARCHIVE.resolve()):
        raise ValueError(f"archive 밖 목적지: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"기존 보존본 불일치: {path}")
    else:
        with path.open("xb") as stream:
            stream.write(data)


def main():
    if ARCHIVE.is_symlink() or FROZEN.is_symlink():
        raise ValueError("보존 폴더의 심볼릭 링크는 허용하지 않음")
    entries = []
    binaries = {}

    def record(source, logical, data, reason):
        immutable_bytes(ARCHIVE / logical, data)
        entries.append({"source": source, "logical_path": logical, "archive_path": logical,
                        "original_sha256": hashlib.sha256(data).hexdigest(), "original_bytes": len(data),
                        "compression": "none", "reasons": [reason]})

    for name, directory, expected_sha, expected_src in SPECS:
        source = Path("/home/scien") / directory / "bin"
        payload = (source / "qamp").read_bytes()
        srcsha = (source / "qamp.srcsha").read_bytes()
        if hashlib.sha256(payload).hexdigest() != expected_sha or srcsha.decode("utf-8").strip() != expected_src:
            raise ValueError(f"원본 바이너리 또는 srcsha가 기대값과 다름: {source}")
        buildinfo = subprocess.check_output(["/home/scien/goroot/bin/go", "version", "-m", str(source / "qamp")])
        label = name + "_" + expected_sha[:8]
        frozen = FROZEN / label
        data_files = {"qamp": payload, "qamp.srcsha": srcsha, "qamp.buildinfo": buildinfo}
        if frozen.exists():
            if frozen.is_symlink() or not frozen.is_dir():
                raise ValueError(f"기존 frozen 경로가 일반 디렉터리가 아님: {frozen}")
            for filename, data in data_files.items():
                target = frozen / filename
                if target.is_symlink() or not target.is_file() or target.read_bytes() != data:
                    raise ValueError(f"기존 frozen 파일 불일치, 읽기만 수행함: {target}")
                if target.stat().st_mode & 0o222:
                    raise ValueError(f"기존 frozen 파일에 쓰기 권한이 있음, 변경하지 않음: {target}")
        else:
            FROZEN.mkdir(parents=True, exist_ok=True)
            frozen.mkdir()
            for filename, data in data_files.items():
                target = frozen / filename
                with target.open("xb") as stream:
                    stream.write(data)
                target.chmod(0o555 if filename == "qamp" else 0o444)
                if target.read_bytes() != data:
                    raise ValueError(f"새 frozen 검증 실패: {target}")
            frozen.chmod(0o555)
        for filename, data in data_files.items():
            logical = "binaries/" + label + "/" + filename
            origin = str(source / filename) if filename != "qamp.buildinfo" else "generated:go version -m " + str(source / "qamp")
            record(origin, logical, data, "frozen_binary")
        for optional in ("go_test.txt", "go_race.txt", "qamp.sha256"):
            path = source / optional
            if path.is_file():
                record(str(path), "binaries/" + label + "/" + optional, path.read_bytes(), "existing_build_evidence")
        binaries[name] = {"archive_path": "binaries/" + label + "/qamp",
                          "srcsha_path": "binaries/" + label + "/qamp.srcsha",
                          "buildinfo_path": "binaries/" + label + "/qamp.buildinfo",
                          "expected_sha256": expected_sha, "expected_srcsha": expected_src,
                          "frozen_path": str(frozen)}
    origin_root = Path("/home/scien/quicbed")
    for relative in ("cmd/qamp/main.go", "cmd/qamp/policy.go", "cmd/qamp/pfail_table.go", "go.mod", "go.sum"):
        source = origin_root / relative
        record(str(source), "gen2_build_origin/" + relative, source.read_bytes(), "gen2_staged_source")
    entries.sort(key=lambda row: row["logical_path"])
    index = {"schema": "padfec.v33.wsl_archive/1", "entries": entries, "binaries": binaries,
             "source_writes": False, "existing_frozen_writes": False}
    data = (json.dumps(index, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    immutable_bytes(ARCHIVE / "binaries/WSL_INDEX.json", data)
    print(json.dumps({"binaries": len(binaries), "files": len(entries),
                      "bytes": sum(row["original_bytes"] for row in entries)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
