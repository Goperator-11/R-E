import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "CODE_MAP.md"
CHECKER = ROOT / "tools" / "check_algorithm_map.py"
QAMP = ROOT / "experiments" / "quicbed" / "qamp.go"
ARCHIVE = ROOT / "g3" / "v33" / "CANDIDATE_ARCHIVE.json"
V33 = ROOT / "experiments" / "v33"
SECTIONS = ("활성 정책", "테스트베드", "관문", "세계와 재판정", "미채택 후보 보존", "비활성 도구",
            "수량별 알고리즘 지도", "experiments/v33 파일 목록")
HISTORICAL = ("experiments/quicbed/policy3_l1.go", "experiments/gate_l1_go.py", "tests/test_l1_go_gate.py")
HISTORICAL_TEXT = "활성 정책 관문, 이름은 역사적"
INACTIVE = ("experiments/gate_go_parity.py", "g3/l1_go_reference_gen.py")
REQUIRED_FLAGS = {"lead-hold", "revisit-guard", "k-inflate", "pad-junk", "dup", "corrupt-parity",
                  "p3-explore-rate-ms", "profile"}
FLAG_DECL = re.compile(
    r'\bflag\.(?:Bool|Int|Int64|Uint|Uint64|Float64|String|Duration)\(\s*"([^"]+)"\s*,\s*(.*?)\s*,\s*(?=")',
    re.S)
WIDE_READ = re.compile(r"func wideReadFor\(profile string\) bool \{\s*return profile != profileSealed31\s*\}")
TICK = re.compile(r"`([^`]+)`")


def text():
    return DOC.read_text(encoding="utf-8")


def section(name):
    lines = text().splitlines()
    starts = [index for index, line in enumerate(lines)
              if line.startswith("## ") and re.sub(r"^##\s+(?:\d+\.\s*)?", "", line).strip() == name]
    if len(starts) != 1:
        raise AssertionError("section %r appears %d times" % (name, len(starts)))
    body = []
    for line in lines[starts[0] + 1:]:
        if line.startswith("## "):
            break
        body.append(line)
    return body


def cells(line):
    value = line.strip().strip("|")
    return [cell.strip() for cell in value.split("|")]


def flag_rows():
    rows, header = [], None
    for line in section("테스트베드"):
        if not line.lstrip().startswith("|"):
            header = None
            continue
        row = cells(line)
        if header is None:
            header = row
            continue
        if header[0] == "플래그" and not set("".join(row)) <= set("-: "):
            rows.append(row)
    return rows


def go_flag_defaults():
    kept = "\n".join(line for line in QAMP.read_text(encoding="utf-8").splitlines()
                     if not line.lstrip().startswith("//"))
    found = {}
    for name, default in FLAG_DECL.findall(kept):
        found.setdefault(name, []).append(default.strip())
    return found


def run_checker(*args):
    return subprocess.run([sys.executable, "-I", "-B", str(CHECKER), *args], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


class CodeMapTests(unittest.TestCase):
    def test_sections_are_present_once(self):
        for name in SECTIONS:
            with self.subTest(section=name):
                self.assertIsInstance(section(name), list)

    def test_every_experiments_v33_python_file_is_listed(self):
        paths = sorted(path for path in V33.rglob("*.py") if "__pycache__" not in path.parts)
        self.assertTrue(paths)
        listed = "\n".join(section("experiments/v33 파일 목록"))
        for path in paths:
            relative = path.relative_to(ROOT).as_posix()
            with self.subTest(path=relative):
                self.assertIn("`%s`" % relative, listed)
        named = {token for token in TICK.findall(listed)
                 if token.startswith("experiments/v33/") and token.endswith(".py")}
        self.assertEqual(named, {path.relative_to(ROOT).as_posix() for path in paths})

    def test_default_off_flag_table_matches_qamp_declarations(self):
        found = go_flag_defaults()
        rows = flag_rows()
        names = set()
        for row in rows:
            flag = TICK.findall(row[0])
            default = TICK.findall(row[1])
            with self.subTest(row=row[0]):
                self.assertEqual(len(flag), 1)
                self.assertEqual(len(default), 1)
                self.assertTrue(flag[0].startswith("-"))
                name = flag[0][1:]
                names.add(name)
                self.assertEqual(found.get(name), [default[0]])
        self.assertTrue(REQUIRED_FLAGS <= names, REQUIRED_FLAGS - names)

    def test_wide_read_row_records_the_profile_dependence(self):
        rows = [row for row in flag_rows() if TICK.findall(row[0]) == ["-profile"]]
        self.assertEqual(len(rows), 1)
        joined = " ".join(rows[0])
        self.assertIn("기본 on", joined)
        self.assertIn("sealed31 off", joined)
        self.assertIn("wide read", joined)
        self.assertRegex(QAMP.read_text(encoding="utf-8"), WIDE_READ)

    def test_historical_gate_names_and_inactive_tools_are_marked(self):
        gates = section("관문")
        inactive = section("비활성 도구")
        for relative in HISTORICAL:
            with self.subTest(path=relative):
                self.assertTrue((ROOT / relative).is_file())
                self.assertTrue(any("`%s`" % relative in line and HISTORICAL_TEXT in line for line in gates))
        for relative in INACTIVE:
            with self.subTest(path=relative):
                self.assertTrue((ROOT / relative).is_file())
                self.assertTrue(any("`%s`" % relative in line and "비활성" in line for line in inactive))

    def test_candidate_section_names_every_archive_entry(self):
        listed = "\n".join(section("미채택 후보 보존"))
        self.assertIn("g3/v33/CANDIDATE_ARCHIVE.json", listed)
        ids = [entry["id"] for entry in json.loads(ARCHIVE.read_text(encoding="utf-8"))["candidates"]]
        self.assertEqual(len(ids), 16)
        for cid in ids:
            with self.subTest(candidate=cid):
                self.assertRegex(listed, r"(?<![\w])%s(?![\w])" % re.escape(cid))

    def test_algorithm_map_checker_passes(self):
        result = run_checker("--quiet")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS rows 11", result.stdout)

    def test_algorithm_map_checker_rejects_a_missing_name(self):
        original = text()
        self.assertIn("`p3OneRTTOK`", original)
        with tempfile.TemporaryDirectory() as folder:
            broken = Path(folder) / "CODE_MAP.md"
            broken.write_text(original.replace("`p3OneRTTOK`", "`p3OneRTTOKMissing`", 1), encoding="utf-8")
            result = run_checker("--quiet", "--doc", str(broken))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("p3OneRTTOKMissing not found", result.stdout)


if __name__ == "__main__":
    unittest.main()
