import ast
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "g3" / "v33" / "CANDIDATE_ARCHIVE.json"
QAMP = ROOT / "experiments" / "quicbed" / "qamp.go"
POLICY3 = ROOT / "experiments" / "quicbed" / "policy3.go"
DECIDE3 = ROOT / "padfec3" / "decide3.py"
TRIAGE_IDS = ("L2", "L3", "L5", "J1", "J6", "J7", "M1", "O2", "J5", "O3", "O4", "J3", "M4", "J8")
LATER_IDS = ("AK1", "CX1")
EXPECTED_STATUS = dict({cid: "미채택" for cid in TRIAGE_IDS}, AK1="미채택", CX1="보류")
CHECKED = ("snapshot", "scripts", "tests", "docs")
KEYS = {"id", "status", "triage_state", "attempt", "snapshot", "scripts", "tests", "docs",
        "validation", "go_flags", "inactive_reason", "active_remnant"}
WITH_SNAPSHOT = {"L2", "L3", "L5", "J1", "J6", "J7", "M1"}
VALIDATION_PREFIX = "g3/v33/validation/"
SWITCH_DEFAULTS = {
    "lead-hold": "false",
    "revisit-guard": "false",
    "k-inflate": "0",
    "corrupt-parity": "-1",
    "pad-junk": "false",
    "dup": "false",
    "p3-explore-rate-ms": "0",
}
AUX_DEFAULTS = {
    "lead-hold-uplink-kbps": "2000",
    "lead-hold-margin": "time.Millisecond",
    "decoder-support": '"unknown"',
}
FLAG_DECL = re.compile(
    r'\bflag\.(?:Bool|Int|Int64|Uint|Uint64|Float64|String|Duration)\(\s*"([^"]+)"\s*,\s*(.*?)\s*,\s*(?=")',
    re.S)
FORBIDDEN = (("experiments", "v33"), ("g3", "v33"))
ACTIVE_PACKAGES = ("padfec", "padfec3")
REQUIRED_ACTIVE = {"padfec/__init__.py", "padfec/policy.py", "padfec/quantum.py", "padfec/table.py",
                   "padfec3/__init__.py", "padfec3/decide3.py", "padfec3/layout.py", "padfec3/learn3.py"}


def load_archive():
    return json.loads(ARCHIVE.read_text(encoding="utf-8"))


def go_flag_defaults(text):
    kept = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))
    found = {}
    for name, default in FLAG_DECL.findall(kept):
        found.setdefault(name, []).append(default.strip())
    return found


def call_name(func):
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def imported_modules(relative, node):
    if isinstance(node, ast.Import):
        return [alias.name.split(".") for alias in node.names]
    package = list(Path(relative).parent.parts)
    base = package[:max(0, len(package) - node.level + 1)] if node.level else []
    module = base + (node.module.split(".") if node.module else [])
    return [module] + [module + [alias.name] for alias in node.names if alias.name != "*"]


def forbidden_imports(relative, text):
    found = []
    for node in ast.walk(ast.parse(text, filename=relative)):
        targets = []
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            targets = imported_modules(relative, node)
        elif (isinstance(node, ast.Call) and call_name(node.func) in {"import_module", "__import__"}
              and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
            targets = [node.args[0].value.split(".")]
        for parts in targets:
            if tuple(parts[:2]) in FORBIDDEN:
                found.append((node.lineno, ".".join(parts)))
    return found


def active_sources():
    return sorted(path for package in ACTIVE_PACKAGES for path in (ROOT / package).rglob("*.py")
                  if "__pycache__" not in path.parts)


class CandidateArchiveTests(unittest.TestCase):
    def test_candidate_ids_are_exactly_the_triage_list_and_later_two(self):
        ids = [entry["id"] for entry in load_archive()["candidates"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(tuple(ids[:len(TRIAGE_IDS)]), TRIAGE_IDS)
        self.assertEqual(set(ids), set(TRIAGE_IDS) | set(LATER_IDS))
        self.assertEqual(len(ids), 16)

    def test_every_entry_has_the_index_fields_and_a_final_status(self):
        text = ARCHIVE.read_text(encoding="utf-8")
        self.assertNotIn("기각", text)
        for entry in load_archive()["candidates"]:
            with self.subTest(candidate=entry["id"]):
                self.assertEqual(set(entry), KEYS)
                self.assertEqual(entry["status"], EXPECTED_STATUS[entry["id"]])
                for key in ("triage_state", "attempt", "inactive_reason", "active_remnant"):
                    self.assertIsInstance(entry[key], str)
                    self.assertTrue(entry[key].strip())
                for key in CHECKED + ("validation", "go_flags"):
                    self.assertIsInstance(entry[key], list)

    def test_listed_traces_exist_from_the_repository_root(self):
        checked = 0
        for entry in load_archive()["candidates"]:
            for category in CHECKED:
                for relative in entry[category]:
                    with self.subTest(candidate=entry["id"], category=category, path=relative):
                        self.assertIsInstance(relative, str)
                        self.assertFalse(Path(relative).is_absolute())
                        self.assertNotIn("\\", relative)
                        self.assertNotIn("..", Path(relative).parts)
                        self.assertIsNone(re.search(r"[*?\[\]]", relative))
                        self.assertFalse(relative.startswith(VALIDATION_PREFIX))
                        self.assertTrue((ROOT / relative).exists())
                        checked += 1
        self.assertGreater(checked, 200)

    def test_categories_that_have_traces_are_not_left_empty(self):
        by_id = {entry["id"]: entry for entry in load_archive()["candidates"]}
        for cid in TRIAGE_IDS:
            entry = by_id[cid]
            with self.subTest(candidate=cid):
                for category in ("scripts", "tests", "docs", "validation"):
                    self.assertTrue(entry[category], category)
                self.assertEqual(bool(entry["snapshot"]), cid in WITH_SNAPSHOT)
                self.assertIn("docs/미채택 후보 평가 기록.md", entry["docs"])
                self.assertEqual(bool(entry["go_flags"]), cid in {"M1", "M4"})
        self.assertTrue(by_id["CX1"]["scripts"])
        self.assertTrue(by_id["CX1"]["tests"])
        self.assertTrue(by_id["CX1"]["go_flags"])
        for category in CHECKED + ("validation", "go_flags"):
            self.assertEqual(by_id["AK1"][category], [])

    def test_validation_paths_stay_strings_under_the_bundle_prefix(self):
        for entry in load_archive()["candidates"]:
            for relative in entry["validation"]:
                with self.subTest(candidate=entry["id"], path=relative):
                    self.assertIsInstance(relative, str)
                    self.assertTrue(relative.startswith(VALIDATION_PREFIX + entry["id"] + "_"))
                    self.assertEqual(relative.count("/"), 3)

    def test_go_flag_reader_handles_multiline_and_commented_declarations(self):
        text = ('a := flag.Int("corrupt-parity", -1,\n\t\t"usage")\n'
                '// b := flag.Bool("dup", true, "old")\n'
                'c := flag.Bool("dup", false, "one, two")\n'
                'd := flag.String("decoder-support", "unknown", "x")\n'
                'e := flag.Duration("lead-hold-margin", time.Millisecond, "y")\n')
        self.assertEqual(go_flag_defaults(text), {
            "corrupt-parity": ["-1"], "dup": ["false"], "decoder-support": ['"unknown"'],
            "lead-hold-margin": ["time.Millisecond"]})

    def test_candidate_switches_are_declared_off_in_qamp(self):
        found = go_flag_defaults(QAMP.read_text(encoding="utf-8"))
        for name, expected in dict(SWITCH_DEFAULTS, **AUX_DEFAULTS).items():
            with self.subTest(flag=name):
                self.assertEqual(found.get(name), [expected])

    def test_archive_flag_values_match_qamp_declarations(self):
        archive = load_archive()
        found = go_flag_defaults(QAMP.read_text(encoding="utf-8"))
        listed = {row["name"]: row["default"] for row in archive["testbed_default_off"]}
        self.assertEqual(listed, SWITCH_DEFAULTS)
        for entry in archive["candidates"]:
            for row in entry["go_flags"]:
                with self.subTest(candidate=entry["id"], flag=row["name"]):
                    expected = SWITCH_DEFAULTS if row["switch"] else AUX_DEFAULTS
                    self.assertEqual(row["default"], expected[row["name"]])
                    self.assertEqual(found.get(row["name"]), [row["default"]])

    def test_cx1_is_off_unless_requested(self):
        tree = ast.parse(DECIDE3.read_text(encoding="utf-8"))
        decide = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "decide3")
        names = [arg.arg for arg in decide.args.kwonlyargs]
        default = decide.args.kw_defaults[names.index("explore")]
        self.assertIsInstance(default, ast.Constant)
        self.assertIsNone(default.value)
        self.assertRegex(POLICY3.read_text(encoding="utf-8"), re.compile(r"^\s*p3ExploreRateMs\s+float64\s*$", re.M))

    def test_import_detector_reads_every_import_form(self):
        relative = "padfec3/probe.py"
        positive = (
            "import experiments.v33.worldsim as w\n",
            "from experiments.v33 import bench\n",
            "from experiments import v33 as old\n",
            "from g3 import v33\n",
            "def f():\n    from g3.v33 import x\n",
            "from ..g3.v33 import y\n",
            "if True:\n    import importlib\n    importlib.import_module('experiments.v33.oracle')\n",
            "__import__('g3.v33.tools')\n",
        )
        negative = (
            "import experiments.v33_extra\n",
            "from experiments import v330\n",
            "NAME = 'experiments.v33'\n",
            "from . import layout\n",
            "from padfec import policy\n",
        )
        for text in positive:
            with self.subTest(text=text):
                self.assertTrue(forbidden_imports(relative, text))
        for text in negative:
            with self.subTest(text=text):
                self.assertEqual(forbidden_imports(relative, text), [])

    def test_active_packages_do_not_import_candidate_code(self):
        paths = active_sources()
        relatives = {path.relative_to(ROOT).as_posix() for path in paths}
        self.assertTrue(REQUIRED_ACTIVE <= relatives, REQUIRED_ACTIVE - relatives)
        problems = []
        for path in paths:
            relative = path.relative_to(ROOT).as_posix()
            problems.extend((relative, line, name)
                            for line, name in forbidden_imports(relative, path.read_text(encoding="utf-8-sig")))
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
