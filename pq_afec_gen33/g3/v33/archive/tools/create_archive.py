import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")


def digest(path, compressed=False):
    h = hashlib.sha256()
    size = 0
    with (gzip.open(path, "rb") if compressed else path.open("rb")) as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
            size += len(block)
    return h.hexdigest(), size


def under(root, relative):
    path = root / relative
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"허용 범위 밖 경로: {path}")
    return path


def immutable_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"기존 파일 불일치, 덮어쓰지 않음: {path}")
        return
    with path.open("xb") as stream:
        stream.write(data)


def canonical(data):
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", type=Path, default=Path("C:/dev/padfec_archive"))
    args = ap.parse_args()
    if args.archive.is_symlink():
        raise ValueError("보존 폴더의 심볼릭 링크는 허용하지 않음")
    archive = args.archive.resolve()
    if archive != Path("C:/dev/padfec_archive").resolve():
        raise ValueError("보존 폴더는 C:/dev/padfec_archive만 허용")
    wsl_path = under(archive, "binaries/WSL_INDEX.json")
    wsl = json.loads(wsl_path.read_text(encoding="utf-8"))
    plans = {}

    def add(source, logical, reason):
        source = source.resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        relative = Path(logical).as_posix()
        under(archive, relative)
        if relative in plans:
            if plans[relative]["source"] != source:
                raise ValueError(f"목적지 중복: {relative}")
            plans[relative]["reasons"].add(reason)
        else:
            plans[relative] = {"source": source, "reasons": {reason}}

    seals = []
    for generation, target, sealname in (
        ("pq_afec_gen31", "v31_stage3", "SEAL_stage3.json"),
        ("pq_afec_gen3", "v30_stage2", "SEAL_stage2.json"),
    ):
        source_root = Path("C:/dev") / generation
        for folder in ("experiments/state", "experiments/results", "g3"):
            for source in sorted((source_root / folder).rglob("*")):
                if source.is_symlink():
                    raise ValueError(f"원본 심볼릭 링크 확인 필요: {source}")
                if source.is_file():
                    add(source, target + "/" + source.relative_to(source_root).as_posix(), "generation_tree")
        seal = json.loads((source_root / "g3" / sealname).read_text(encoding="utf-8"))
        descriptor = {"root": target, "seal": target + "/g3/" + sealname, "development": {}}
        for section in ("sha256", "also_recorded_sha256"):
            for key in seal[section]:
                source = under(source_root, key)
                add(source, target + "/" + key, section)
        for key, value in seal.get("development_data_sha256", {}).items():
            if not value.get("exists", False):
                raise ValueError(f"봉인에 exists=false 항목이 있음: {key}")
            source = Path(key) if Path(key).is_absolute() else under(source_root, key)
            source = source.resolve()
            if source.drive.upper() != "C:":
                raise ValueError(f"확인하지 않은 개발자료 드라이브: {source}")
            logical = "dev_data/C/" + "/".join(source.parts[1:])
            add(source, logical, "development_data_sha256")
            descriptor["development"][key] = logical
        seals.append(descriptor)
    for relative in ("state/evo/verdict_v3.md", "tools/run_p31_run1.sh", "tools/run_p31_run2.sh",
                     "tools/run_p31_draw.sh", "tools/run_p31_seal.sh"):
        source = Path("C:/dev/codex_handoff") / relative
        add(source, "dev_data/C/dev/codex_handoff/" + relative, "preregistration_and_runner_provenance")
    for name in ("create_archive.py", "verify_archive.py", "archive_wsl.py", "freeze_binaries.sh"):
        add(Path(__file__).resolve().parent / name, "tools/" + name, "reproduction_tool")
    prepared = []
    for logical, plan in sorted(plans.items()):
        source = plan["source"]
        sha, size = digest(source)
        compressed = source.suffix == ".jsonl"
        stored = logical + ".gz" if compressed else logical
        prepared.append({"logical_path": logical, "archive_path": stored,
                         "source": str(source), "original_sha256": sha,
                         "original_bytes": size, "compression": "gzip" if compressed else "none",
                         "reasons": sorted(plan["reasons"])})
    entries = []
    copied = 0
    reused = 0
    for row in prepared:
        dest = under(archive, row["archive_path"])
        source = Path(row["source"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        compressed = row["compression"] == "gzip"
        if dest.exists():
            if digest(dest, compressed) != (row["original_sha256"], row["original_bytes"]):
                raise ValueError(f"기존 보존본 불일치, 덮어쓰지 않음: {dest}")
            reused += 1
        else:
            with source.open("rb") as src, dest.open("xb") as raw:
                if compressed:
                    with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=6, mtime=0) as dst:
                        shutil.copyfileobj(src, dst, length=1024 * 1024)
                else:
                    shutil.copyfileobj(src, raw, length=1024 * 1024)
            if digest(dest, compressed) != (row["original_sha256"], row["original_bytes"]):
                raise ValueError(f"새 보존본 검증 실패, 삭제하지 않고 남김: {dest}")
            copied += 1
        if digest(source) != (row["original_sha256"], row["original_bytes"]):
            raise ValueError(f"복사 중 원본 변경: {source}")
        stored_sha, stored_size = digest(dest)
        row.update(stored_sha256=stored_sha, stored_bytes=stored_size)
        entries.append(row)
    for original in wsl["entries"]:
        row = dict(original)
        dest = under(archive, row["archive_path"])
        if digest(dest) != (row["original_sha256"], row["original_bytes"]):
            raise ValueError(f"WSL 보존본 불일치: {dest}")
        row.update(stored_sha256=row["original_sha256"], stored_bytes=row["original_bytes"])
        entries.append(row)
    wsl_sha, wsl_size = digest(wsl_path)
    entries.append({"logical_path": "binaries/WSL_INDEX.json", "archive_path": "binaries/WSL_INDEX.json",
                    "source": "generated:archive_wsl.py", "original_sha256": wsl_sha,
                    "original_bytes": wsl_size, "stored_sha256": wsl_sha, "stored_bytes": wsl_size,
                    "compression": "none", "reasons": ["wsl_index"]})
    entries.sort(key=lambda row: row["logical_path"])
    if len({row["logical_path"] for row in entries}) != len(entries):
        raise ValueError("최종 index의 논리 경로 중복")
    index = {"schema": "padfec.v33.archive/1", "entries": entries, "seals": seals,
             "binaries": wsl["binaries"], "scope": {
                 "included": ["gen31/gen3 state 전체(backup 포함)", "gen31/gen3 results/g3 전체",
                              "stage3/stage2 raw와 recorded 봉인 파일", "stage3/stage2 개발자료 전체",
                              "verdict_v3.md와 run_p31 실행 래퍼 4개",
                              "qamp 바이너리 5개와 srcsha/buildinfo", "gen2 staged qamp 소스와 go.mod/go.sum"],
                 "excluded": ["다른 gen2 실행 파일(qserver, qdata, qclient, mlkemcheck)",
                              "Go 모듈 캐시 및 컴파일 캐시", "전체 Windows/WSL 시스템 백업"],
                 "source_files_deleted": False, "network_uploads": False,
                 "confirmatory_execution": False}}
    immutable_bytes(under(archive, "INDEX.json"), canonical(index))
    manifest = "".join(row["original_sha256"] + "  " + row["logical_path"] + "\n" for row in entries)
    immutable_bytes(under(archive, "MANIFEST.sha256"), manifest.encode("utf-8"))
    print(json.dumps({"copied": copied, "reused": reused, "files": len(entries),
                      "original_bytes": sum(row["original_bytes"] for row in entries),
                      "stored_bytes": sum(row["stored_bytes"] for row in entries)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
