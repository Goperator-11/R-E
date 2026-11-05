import ast
import hashlib
import os
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
FOREIGN = re.compile(
    r"pq_" + r"afec(?:_(?:gen31|gen32|gen3|next))?(?![A-Za-z0-9_])"
    r"|quicbed_" + r"gen32(?![A-Za-z0-9_])|build_" + r"gen32\.sh")
HISTORICAL_ASSIGNMENTS = {
    ("experiments/p21_gencompare.py", "REGRESSION_STAGE2"): "봉인된 2단계 결과의 출처",
    ("experiments/p21_gencompare.py", "DEV_DATA"): "3단계 개발자료를 읽는 원본 목록",
    ("experiments/p21_gencompare.py", "DEV_EXT_GLOBS"): "3단계 개발자료를 읽는 원본 glob",
    ("experiments/replay_g3.py", "P17_DEFAULT"): "과거 p17 재생의 읽기 전용 입력",
    ("experiments/g31_probe.py", "GEN3_QUICBED"): "과거 gen3 소스 지문을 읽는 위치",
    ("experiments/v33/rtt_reference_report.py", "HISTORICAL_JOURNAL_DIR"): "과거 RTT 개발자료를 읽는 기본 입력",
}
HISTORICAL_TESTS = {
    ("tests/test_p21_gencompare.py", "test_dev_manifest_lists_stage2_probe_and_external_development_data"):
        "봉인 개발자료 목록의 정확한 역사 경로를 검사하는 시험",
}
ARCHIVE_READ_ONLY = {
    "g3/v33/archive/tools/create_archive.py": (
        "ea6e297180fc1045c1dd471760ea484b72675fe21c3a6fc344e39075fd98811e",
        "S1의 gen3/gen31 원자료 읽기와 append-only archive 복사"),
    "g3/v33/archive/tools/archive_wsl.py": (
        "ff7642016f5fb167e2085436986d9febf14841916ca6a21e3b714f396ee4cf5d",
        "S1의 보호 바이너리 읽기와 최초 frozen 사본 보존"),
    "g3/v33/archive/tools/verify_gen2_origin.py": (
        "218b116141cb6fb009489038a852f01925a2f717fb32ae62a0f72bf7d9131fc2",
        "git show로 동결 gen2 출처를 읽고 runs에 검증 결과 기록"),
}


def source_paths():
    ignored = {".git", "__pycache__", ".pytest_cache"}
    excluded = {"experiments/state", "experiments/results", "tests/fixtures", "g3/v33"}
    for folder, directories, files in os.walk(ROOT):
        base = Path(folder)
        directories[:] = [name for name in directories if name not in ignored
                          and (base / name).relative_to(ROOT).as_posix() not in excluded]
        for name in files:
            yield base / name
    yield from (ROOT / relative for relative in ARCHIVE_READ_ONLY)


def allowed_spans(relative, text):
    spans = []
    used = set()
    if not relative.endswith(".py"):
        return spans, used
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    key = relative, target.id
                    if key in HISTORICAL_ASSIGNMENTS:
                        values = [n for n in ast.walk(node.value)
                                  if isinstance(n, ast.Constant) and isinstance(n.value, str)
                                  and FOREIGN.search(n.value)]
                        for value in values:
                            spans.append((value.lineno, value.end_lineno))
                        if values:
                            used.add(key)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            key = relative, node.name
            if key in HISTORICAL_TESTS:
                values = [n for n in ast.walk(node)
                          if isinstance(n, ast.Constant) and isinstance(n.value, str)
                          and FOREIGN.search(n.value)]
                for value in values:
                    spans.append((value.lineno, value.end_lineno))
                if values:
                    used.add(key)
    return spans, used


def unexpected_lines(relative, text):
    spans, used = allowed_spans(relative, text)
    unexpected = []
    for number, line in enumerate(text.splitlines(), 1):
        if FOREIGN.search(line) and not any(start <= number <= end for start, end in spans):
            unexpected.append(number)
    return unexpected, used


class ForeignPathTests(unittest.TestCase):
    def test_executable_sources_have_no_foreign_generation_paths(self):
        problems = []
        used = set()
        archive_seen = set()
        for path in sorted(source_paths()):
            if not path.is_file():
                continue
            if path.suffix not in {".py", ".go", ".sh", ".ps1"} and path != ROOT / "genconfig.json":
                continue
            relative_path = path.relative_to(ROOT)
            if any(part in {".git", "__pycache__", ".pytest_cache"} for part in relative_path.parts):
                continue
            relative = relative_path.as_posix()
            if relative.startswith(("experiments/state/", "experiments/results/", "tests/fixtures/")):
                continue
            if relative.startswith("g3/v33/") and relative not in ARCHIVE_READ_ONLY:
                continue
            raw = path.read_bytes().replace(b"\r\n", b"\n")
            if relative in ARCHIVE_READ_ONLY:
                expected, reason = ARCHIVE_READ_ONLY[relative]
                self.assertEqual(hashlib.sha256(raw).hexdigest(), expected, (relative, reason))
                archive_seen.add(relative)
                continue
            text = raw.decode("utf-8-sig")
            unexpected, permitted = unexpected_lines(relative, text)
            used.update(permitted)
            problems.extend(f"{relative}:{line}" for line in unexpected)
        self.assertEqual(problems, [])
        self.assertEqual(used, set(HISTORICAL_ASSIGNMENTS) | set(HISTORICAL_TESTS))
        self.assertEqual(archive_seen, set(ARCHIVE_READ_ONLY))

    def test_historical_allowance_does_not_cover_executable_calls(self):
        foreign = "C:/dev/pq_" + "afec_gen31/result.json"
        text = f'DEV_DATA = ({foreign!r},)\nopen({foreign!r}, "w")\n'
        unexpected, used = unexpected_lines("experiments/p21_gencompare.py", text)
        self.assertEqual(unexpected, [2])
        self.assertEqual(used, {("experiments/p21_gencompare.py", "DEV_DATA")})

    def test_current_generation_does_not_match_old_root_prefix(self):
        current = "C:/dev/pq_" + "afec_gen33/experiments/pipeline.py"
        self.assertIsNone(FOREIGN.search(current))
        for name in ("afec", "afec_gen3", "afec_gen31", "afec_gen32", "afec_next"):
            self.assertIsNotNone(FOREIGN.search("C:/dev/pq_" + name + "/file.py"))


if __name__ == "__main__":
    unittest.main()
