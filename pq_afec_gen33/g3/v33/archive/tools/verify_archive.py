import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")


def digest(path):
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
            size += len(block)
    return h.hexdigest(), size


def under(root, relative):
    path = root / relative
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"허용 범위 밖 경로: {path}")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", type=Path, default=Path("C:/dev/padfec_archive"))
    ap.add_argument("--verify-root", type=Path, default=Path("C:/dev/codex_handoff/v33/runs/s1_verify"))
    args = ap.parse_args()
    archive = args.archive.resolve()
    verify_root = args.verify_root.resolve()
    if verify_root.is_relative_to(archive):
        raise ValueError("검증 임시 폴더는 archive 밖이어야 함")
    allowed = Path("C:/dev/codex_handoff/v33/runs").resolve()
    if not verify_root.is_relative_to(allowed):
        raise ValueError("검증 출력은 v33/runs 아래만 허용")
    index = json.loads(under(archive, "INDEX.json").read_text(encoding="utf-8"))
    if index["schema"] != "padfec.v33.archive/1":
        raise ValueError("알 수 없는 archive schema")
    verify_root.mkdir(parents=True, exist_ok=True)
    unpacked = Path(tempfile.mkdtemp(prefix="check-", dir=verify_root))
    failures = []
    available = {}
    entries = index["entries"]
    if len({row["logical_path"] for row in entries}) != len(entries):
        raise ValueError("index 논리 경로 중복")
    for row in entries:
        try:
            stored = under(archive, row["archive_path"])
            if digest(stored) != (row["stored_sha256"], row["stored_bytes"]):
                raise ValueError("저장 바이트 sha256 또는 크기 불일치")
            if row["compression"] == "gzip":
                original = under(unpacked, row["logical_path"])
                original.parent.mkdir(parents=True, exist_ok=True)
                with gzip.open(stored, "rb") as src, original.open("xb") as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)
            elif row["compression"] == "none":
                original = stored
            else:
                raise ValueError("알 수 없는 압축 형식")
            if digest(original) != (row["original_sha256"], row["original_bytes"]):
                raise ValueError("원본 바이트 sha256 또는 크기 불일치")
            available[row["logical_path"]] = original
        except Exception as exc:
            failures.append({"file": row["logical_path"], "error": str(exc)})
    manifest = "".join(row["original_sha256"] + "  " + row["logical_path"] + "\n" for row in entries)
    if under(archive, "MANIFEST.sha256").read_bytes() != manifest.encode("utf-8"):
        failures.append({"file": "MANIFEST.sha256", "error": "index와 원본 manifest 불일치"})
    seal_counts = {}
    for descriptor in index["seals"]:
        try:
            seal = json.loads(available[descriptor["seal"]].read_text(encoding="utf-8"))
        except Exception as exc:
            failures.append({"seal": descriptor["seal"], "error": str(exc)})
            continue
        counts = {}
        for section in ("sha256", "also_recorded_sha256", "development_data_sha256"):
            checked = 0
            for key, expected in seal.get(section, {}).items():
                try:
                    logical = (descriptor["development"][key] if section == "development_data_sha256"
                               else descriptor["root"] + "/" + key)
                    expected_hash = expected["sha256"] if isinstance(expected, dict) else expected
                    actual_hash, actual_size = digest(available[logical])
                    if actual_hash != expected_hash:
                        raise ValueError(f"봉인 sha256 불일치: {actual_hash} != {expected_hash}")
                    if isinstance(expected, dict) and actual_size != expected["bytes"]:
                        raise ValueError("봉인 원본 크기 불일치")
                    checked += 1
                except Exception as exc:
                    failures.append({"seal": descriptor["seal"], "section": section,
                                     "file": key, "error": str(exc)})
            counts[section] = {"passed": checked, "total": len(seal.get(section, {}))}
        for name, expected in seal.get("binaries", {}).items():
            try:
                is_source = name.endswith("_srcsha")
                binary = index["binaries"][name[:-7] if is_source else name]
                logical = binary["srcsha_path"] if is_source else binary["archive_path"]
                actual = (available[logical].read_text(encoding="utf-8").strip() if is_source
                          else digest(available[logical])[0])
                if actual != expected:
                    raise ValueError("봉인 바이너리 해시 불일치")
            except Exception as exc:
                failures.append({"seal": descriptor["seal"], "binary": name,
                                 "error": str(exc)})
        seal_counts[descriptor["seal"]] = counts
    for name, binary in index["binaries"].items():
        try:
            if digest(available[binary["archive_path"]])[0] != binary["expected_sha256"]:
                raise ValueError("기대 바이너리 해시 불일치")
            if available[binary["srcsha_path"]].read_text(encoding="utf-8").strip() != binary["expected_srcsha"]:
                raise ValueError("기대 srcsha 불일치")
        except Exception as exc:
            failures.append({"binary": name, "error": str(exc)})
    report = {"schema": "padfec.v33.archive_verification/1", "passed": not failures,
              "files": len(entries), "verified_files": len(available),
              "original_bytes": sum(row["original_bytes"] for row in entries),
              "stored_bytes": sum(row["stored_bytes"] for row in entries),
              "unpacked_directory": str(unpacked), "seal_checks": seal_counts,
              "failures": failures, "temporary_outputs_preserved": True}
    with (unpacked / "VERIFICATION.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print("전부 일치" if not failures else "검증 실패")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
