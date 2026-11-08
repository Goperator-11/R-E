import argparse
import ast
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import DATA_ROOT, REPORT_ROOT, SOURCE_PATHS


def source(alias):
    candidates = []
    for relative in SOURCE_PATHS[alias]:
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("source path must be relative: " + alias)
        candidates.append(DATA_ROOT / path)
    return next((path for path in candidates if path.exists()), candidates[0])


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                            text=True, encoding="utf-8", errors="strict")
    if result.returncode:
        raise ValueError("git failed: " + result.stderr.strip())
    return result.stdout


def repo_root(manifest, supplied):
    if supplied:
        return supplied.resolve()
    configured = os.environ.get("REPORT_REPO_ROOT")
    if configured:
        return Path(configured).resolve()
    for relative in manifest["repository_candidates"]:
        candidate = DATA_ROOT / relative
        if (candidate / ".git").exists():
            return candidate.resolve()
    raise ValueError("R-E worktree not found; pass --repo-root")


def normalize(path):
    return str(path).replace("\\", "/").casefold().rstrip("/")


def inspect_sources(manifest, repository):
    aliases = sorted({alias for row in manifest["rows"] for alias in row["sources"]})
    index_path = source("archive_index")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    archive_root = index_path.parent
    all_tracked = set(git(repository, "ls-files", "-z").split("\0")) - {""}
    result = {}
    for alias in aliases:
        local = source(alias)
        if not local.exists():
            raise ValueError("missing local source: " + alias + " " + str(local))
        alternatives = SOURCE_PATHS[alias]
        relative = next((name for name in alternatives if (repository / name).exists()), alternatives[0])
        repo_path = repository / relative
        tracked = sorted(name for name in all_tracked if name == relative or name.startswith(relative.rstrip("/") + "/"))
        if tracked and not repo_path.exists():
            raise ValueError("tracked source missing from worktree: " + relative)
        archives = sorted({entry["archive_path"] for entry in index["entries"] if normalize(entry.get("source", "")) == normalize(local)})
        if alias in manifest["directory_archives"]:
            archives = manifest["directory_archives"][alias]
        for name in archives:
            stored = archive_root / name
            if not stored.exists():
                raise ValueError("missing archive source: " + str(stored))
            if stored.is_dir() and not any(entry["archive_path"].startswith(name + "/") for entry in index["entries"]):
                raise ValueError("archive directory has no INDEX entries: " + name)
        result[alias] = {
            "local": local.as_posix(),
            "relative": relative,
            "kind": "directory" if local.is_dir() else "file",
            "repo_exists": repo_path.exists(),
            "tracked_count": len(tracked),
            "tracked": bool(tracked),
            "archives": [(archive_root / name).as_posix() for name in archives],
        }
    return result


def code(value):
    return "`" + value.replace("|", "&#124;") + "`"


def render(manifest, observed):
    lines = [
        "# 보고서 원자료 위치표",
        "",
        "보고서의 Table·Fig와 본문 수치군을 원자료에 연결한다. 경로는 `source_paths.json`에서 읽으며 `REPORT_DATA_ROOT`를 기준으로 찾는다. 환경변수가 없으면 이 폴더의 상위 두 단계 디렉터리를 기준으로 한다. 세대별 저장소가 나란히 있거나 R-E 아래에 배치된 구조에 맞춘 값이다.",
        "",
        "R-E 추적 여부는 `check_sources.py` 실행 시 선택한 worktree의 `git ls-files`와 파일 존재 여부다. 현재 행은 F07 작성 시점이며 배포가 반영되면 `--write`로 갱신한 뒤 다시 검사한다. 미추적 파일을 GitHub에 있다고 세지 않는다. 원자료 재계산에 필요한 Python과 패키지는 별도로 설치해야 한다.",
        "",
        "로컬 원본과 archive는 로컬 보존 위치다. archive 경로는 보존 INDEX와 대조한 기존 파일만 적었다. '미보존'은 INDEX에서 해당 원본의 사본을 찾지 못했다는 뜻이며, 임의의 미래 경로를 존재하는 사본으로 표시하지 않는다. 압축된 저널은 읽기 전에 별도 작업 폴더에 풀어야 한다.",
        "",
        "재계산 명령은 해당 수치군의 재계산 범위를 적은 것이다. 저장값 조회, 도식 재생성, 규칙의 사람 대조와 수치 재계산을 구분한다. 이 표의 경로 검사는 수치·해석·문헌 원문의 정확성 검사를 대신하지 않는다.",
        "",
        "| 보고서 위치(Table n, Fig. n, 절) | 수치군 | 파일과 키 | R-E 추적 여부 | 로컬 원본 | archive 경로 | 재계산 명령 | GitHub만으로 가능 여부 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in manifest["rows"]:
        inputs, tracked, local, archives = [], [], [], []
        for alias, selector in row["sources"].items():
            item = observed[alias]
            inputs.append(code(alias) + ": " + code(item["relative"]) + " # " + selector)
            status = "추적" if item["tracked"] else "미추적"
            existence = "존재" if item["repo_exists"] else "없음"
            tracked.append(code(alias) + f": {status}, worktree {existence}")
            local.append(code(alias) + ": " + code(item["local"]))
            archives.append(code(alias) + ": " + ("; ".join(code(path) for path in item["archives"]) or "미보존(INDEX 미등재)"))
        available = all(observed[alias]["tracked"] and observed[alias]["repo_exists"] for alias in row["sources"])
        availability = "입력 전체 추적. " if available else "일부 입력 미추적. "
        cells = [row["location"], row["group"], "<br>".join(inputs), "<br>".join(tracked), "로컬 보존: " + "<br>".join(local), "로컬 보존: " + "<br>".join(archives), code(row["recompute"]) if row["recompute"].startswith("python ") else row["recompute"], availability + row["scope"]]
        lines.append("| " + " | ".join(cell.replace("\n", " ").replace("|", "&#124;") for cell in cells) + " |")
    lines.extend([
        "",
        "## 경로 검사와 갱신",
        "",
        "저장소 루트에서 실행한다. `--repo-root`는 R-E worktree를 지정한다. 지정하지 않으면 `REPORT_REPO_ROOT` 또는 원자료 루트 아래 배포 작업 위치를 찾는다. 기본 실행은 파일을 쓰지 않으며 표·manifest·현재 경로 상태가 다르면 종료 코드 1이다.",
        "",
        "```powershell",
        "python -I -B report_repro/check_sources.py",
        "python -I -B report_repro/check_sources.py --write",
        "python -I -B report_repro/check_sources.py",
        "```",
        "",
        "`sources_manifest.json`에는 표의 수치군과 필드 설명을 둔다. 검사기는 모든 입력의 존재와 R-E 추적 상태, archive 파일 존재를 검사하고 표 전체를 현재 상태에서 다시 만들어 대조한다. 보존한 `content.py`의 Table·Fig 토큰 집합이 표에 모두 있는지도 검사한다. 원본 content 파일이 있으면 두 파일의 Python AST와 토큰 집합을 비교하고 SHA256을 각각 기록한다. 사본은 coding 주석과 줄 끝 형식이 달라 원본과 바이트가 다르다. 원본이 없으면 사본으로 검사한 사실을 출력한다.",
        "",
        "## 그림과 수치 재현",
        "",
        "`report_repro/tools/export_data.py`는 입력을 읽어 `report_repro/data`의 그림용 JSON을 다시 쓴다. 각 JSON의 source는 선택한 입력의 상대 경로다. Fig. 3의 threshold_bisect_laptop과 Fig. 4의 P, c, s0는 원본 exporter에 적힌 값을 유지한다. 이 실행에서 새로 측정하는 값은 아니다.",
        "",
        "```powershell",
        "python -I -B -m pip install -r report_repro/requirements.txt",
        "python -I -B report_repro/tools/export_data.py",
        "python -I -B report_repro/check_report_numbers.py",
        "```",
        "",
        "`check_report_numbers.py`는 Fig. 3, 4, 6, 5 순서로 .tex 수치를 원자료와 대조하고 불일치가 하나라도 있으면 종료 코드 1이다. LaTeX 컴파일·HWP 문단 비교·문서 변환을 하지 않는다. `report_repro/tools/final_check.py`는 같은 검사의 호환 진입점이다. Fig. 6은 H2/run1/tests에서 그려진 조건을 대조하고, 그리지 않은 조건의 하한과 전체 조건 수를 진단으로 남긴다.",
        "",
        "## 배포하지 않는 자료",
        "",
        "v3 저널과 v3.3.1 평가 원자료는 로컬 보존한다. probe는 원본 전체 대신 `g31_probe_excerpt.json`에 첫 송신 크기의 histogram과 직접 근거 행, 원본 SHA256을 담는다. `extract_g31_probe.py --check`는 원본 SHA256과 선택한 포인터·값을 대조한다. 41 B가 ACK 전용이라는 해석과 모든 실패 셀의 원인은 이 발췌로 확인하지 않는다.",
        "",
        "TLS 계산은 손실이 있는 행의 설계 횟수에서 성공 수 n을 빼 실패 수를 구하고, 두 비율의 pooled z를 계산한다. 설계 횟수는 보존 실행 스크립트의 loss=0 시 1/8, RTT 100·200 ms 시 1/2 규칙을 따른다. 연결별 시간열은 이 CSV에 없으므로 독립성 가정과 실제 netem 방향은 이 계산으로 검증되지 않는다.",
    ])
    return "\n".join(lines) + "\n"


def coverage(manifest):
    content_path = source(manifest["content_source"])
    content = content_path.read_text(encoding="utf-8-sig")
    pattern = r"\b(?:Table\s+\d+|Fig\.\s*\d+)\b"
    expected = set(re.findall(pattern, content))
    actual = set(re.findall(pattern, " ".join(row["location"] for row in manifest["rows"])))
    if expected != actual:
        raise ValueError("Table/Fig coverage differs: " + repr(sorted(expected ^ actual)))
    original = Path(manifest["original_content"])
    original_checked = original.is_file()
    hashes = {"preserved": hashlib.sha256(content_path.read_bytes()).hexdigest()}
    if original_checked:
        original_text = original.read_text(encoding="utf-8-sig")
        hashes["original"] = hashlib.sha256(original.read_bytes()).hexdigest()
        if ast.dump(ast.parse(original_text)) != ast.dump(ast.parse(content)):
            raise ValueError("original content and preserved AST differ")
        if set(re.findall(pattern, original_text)) != expected:
            raise ValueError("original content and preserved Table/Fig tokens differ")
    return {"tokens": sorted(expected), "original_checked": original_checked, "sha256": hashes}


def tls_recalculate():
    rows = list(csv.DictReader(source("tls_raw").open(encoding="utf-8-sig", newline="")))
    groups = {}
    attempts = 0
    for row in rows:
        loss = float(row["loss_pct"])
        planned = 250 if loss == 0 else 2000
        if float(row["rtt_ms"]) in (100, 200):
            planned //= 2
        attempts += planned
        if loss == 0:
            continue
        succeeded = int(row["n"])
        if not 0 <= succeeded <= planned:
            raise ValueError("TLS successes outside planned range")
        item = groups.setdefault(row["group"], {"attempts": 0, "failures": 0})
        item["attempts"] += planned
        item["failures"] += planned - succeeded
    reference = groups["X25519"]
    for name, item in groups.items():
        item["failure_percent"] = 100 * item["failures"] / item["attempts"]
        pooled = (item["failures"] + reference["failures"]) / (item["attempts"] + reference["attempts"])
        variance = pooled * (1 - pooled) * (1 / item["attempts"] + 1 / reference["attempts"])
        item["z_vs_X25519"] = (item["failures"] / item["attempts"] - reference["failures"] / reference["attempts"]) / math.sqrt(variance)
    return {"source": source("tls_raw").as_posix(), "rows": len(rows), "planned_attempts_all": attempts, "loss_groups": groups, "scope": "row-level design minus successes; independent proportions assumed"}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--recalculate", choices=("table4",))
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    if args.recalculate:
        print(json.dumps(tls_recalculate(), ensure_ascii=False, indent=2))
        return 0
    manifest = json.loads((REPORT_ROOT / "sources_manifest.json").read_text(encoding="utf-8"))
    repository = repo_root(manifest, args.repo_root)
    found = inspect_sources(manifest, repository)
    covered = coverage(manifest)
    expected = render(manifest, found)
    output = REPORT_ROOT / "SOURCES.md"
    if args.write:
        output.write_text(expected, encoding="utf-8", newline="\n")
    if output.read_text(encoding="utf-8") != expected:
        raise ValueError("SOURCES.md differs from manifest/current paths; review and run --write")
    result = {"status": "pass", "rows": len(manifest["rows"]), "source_count": len(found), "coverage": covered, "repository": repository.as_posix(), "sources": found}
    if args.json:
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: rows={len(manifest['rows'])}, sources={len(found)}, Table/Fig={len(covered['tokens'])}, original_checked={covered['original_checked']}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, UnicodeError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        raise SystemExit(1)
