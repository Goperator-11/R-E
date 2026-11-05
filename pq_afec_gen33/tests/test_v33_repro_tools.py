import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools import lint_ast, precommit_size, raw_io, runtime_fingerprint as fingerprint, scrub_for_publish


class ReproductionToolsTests(unittest.TestCase):
    def test_compressed_formats_preserve_unicode_and_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            rows = [{"text": "패킷", "bytes": 1280}, {"p": .25}]
            for suffix in (".json.gz", ".jsonl.gz"):
                path = Path(directory) / ("raw" + suffix)
                raw_io.write(path, rows)
                self.assertEqual(raw_io.read(path), rows)
                before = path.read_bytes()
                with self.assertRaises(FileExistsError):
                    raw_io.write(path, [])
                self.assertEqual(path.read_bytes(), before)
                same = Path(directory) / ("same" + suffix)
                raw_io.write(same, rows)
                self.assertEqual(same.read_bytes(), before)
                if suffix == ".jsonl.gz":
                    self.assertEqual(list(raw_io.iter_rows(path)), rows)
            with self.assertRaises(ValueError):
                raw_io.write(Path(directory) / "raw.json", rows)
            with self.assertRaises(ValueError):
                raw_io.write(Path(directory) / "nan.json.gz", {"bad": float("nan")})

    def test_code_identity_is_relocatable_and_environment_changes_are_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            roots = [Path(directory) / name for name in ("one", "two")]
            for root in roots:
                root.mkdir()
                (root / "source.py").write_text("x = 1\n", encoding="utf-8")
            one = fingerprint.make(roots[0], ["source.py"], {"python": "A"})
            two = fingerprint.make(roots[1], ["source.py"], {"python": "B"})
            self.assertEqual(one["code_fp"], two["code_fp"])
            result = fingerprint.compare(one, two)
            self.assertFalse(result["code_changed"])
            self.assertTrue(result["remeasure_recommended"])
            self.assertFalse(result["reuse_allowed"])
            (roots[1] / "source.py").write_text("x = 2\n", encoding="utf-8")
            changed = fingerprint.make(roots[1], ["source.py"], {"python": "A"})
            self.assertTrue(fingerprint.compare(one, changed)["remeasure_required"])
            with self.assertRaises(ValueError):
                fingerprint.code_fingerprint(roots[1], ["../one/source.py"])

    def test_ast_lint_detects_syntax_without_bytecode_or_archived_drafts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "valid.py").write_text("x = 1\n", encoding="utf-8")
            archived = root / "g3/v33/failed.py"
            archived.parent.mkdir(parents=True)
            archived.write_text("if :\n", encoding="utf-8")
            self.assertEqual(lint_ast.check(lint_ast.sources(root), root)["status"], "PASS")
            (root / "broken.py").write_text("if :\n", encoding="utf-8")
            self.assertEqual(lint_ast.check(lint_ast.sources(root), root)["errors"][0]["path"], "broken.py")
            self.assertEqual(list(root.rglob("*.pyc")), [])

    def git(self, root, *args):
        return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.STDOUT)

    def test_staged_blob_size_cannot_be_hidden_by_worktree_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.git(root, "init", "-q")
            path = root / "크기 입력.dat"
            path.write_bytes(b"a" * precommit_size.LIMIT)
            self.git(root, "add", "--", path.name)
            self.assertEqual(precommit_size.check(root)["status"], "PASS")
            with path.open("ab") as stream:
                stream.write(b"x")
            self.git(root, "add", "--", path.name)
            path.write_bytes(b"small")
            result = precommit_size.check(root)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["oversize"][0]["bytes"], precommit_size.LIMIT + 1)
            self.git(root, "add", "--", path.name)
            self.assertEqual(precommit_size.check(root)["status"], "PASS")

    def test_staged_private_key_is_rejected_even_with_a_pem_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.git(root, "init", "-q")
            path = root / "certificate.pem"
            key = "\n".join(("-----BEGIN PRIVATE KEY-----", "YWJjZA==", "-----END PRIVATE KEY-----", ""))
            path.write_text(key, encoding="utf-8")
            self.git(root, "add", "--", path.name)
            result = precommit_size.check(root)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["oversize"], [])
            self.assertEqual(result["private_key_files"], [path.name])

    def test_publish_check_reports_kinds_and_never_rewrites_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.git(root, "init", "-q")
            path = root / "fixture.txt"
            path.write_text("C:/Users/unit/data\na@example.invalid\n-----BEGIN PRIVATE KEY-----\n", encoding="utf-8")
            self.git(root, "add", "--", path.name)
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            result = scrub_for_publish.check(root)
            self.assertEqual(result["affected_file_counts"], {"user_path": 1, "email": 1, "private_key": 1})
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
            self.assertNotIn("a@example.invalid", json.dumps(result))

    def test_history_check_finds_removed_private_key_and_oversize_blob(self):
        if shutil.which("git") is None:
            self.skipTest("git is not installed")
        options = ["-c", "user.name=unit", "-c", "user.email=unit@example.invalid", "-c", "core.autocrlf=false"]

        def git(*args):
            try:
                return subprocess.check_output(["git", "-C", str(root), *options, *args],
                                               stderr=subprocess.STDOUT, timeout=120).decode("utf-8").strip()
            except subprocess.TimeoutExpired:
                self.skipTest("git is too slow for the synthetic history repository")

        with tempfile.TemporaryDirectory(prefix="v33-scrub-history-") as directory:
            root = Path(directory).resolve()
            git("init", "-q")
            (root / "keys").mkdir()
            key = "\n".join(("-----BEGIN PRIVATE KEY-----", "YWJjZA==", "-----END PRIVATE KEY-----", ""))
            (root / "keys/server.key").write_bytes(key.encode("ascii"))
            (root / "notes.txt").write_text("-----BEGIN PRIVATE KEY-----\nheader only\n", encoding="utf-8")
            git("add", "--", "keys/server.key", "notes.txt")
            git("commit", "-q", "-m", "add key")
            added = git("rev-parse", "HEAD")
            git("rm", "-q", "--", "keys/server.key")
            size = scrub_for_publish.HISTORY_LIMIT + 1
            (root / "big.dat").write_bytes(b"a" * size)
            git("add", "--", "big.dat")
            git("commit", "-q", "-m", "remove key, add big blob")
            removed = git("rev-parse", "HEAD")
            status = git("status", "--porcelain", "--untracked-files=all")
            result = scrub_for_publish.history(root)
            self.assertEqual(result["mode"], "history_check_only")
            self.assertEqual(result["status"], "FINDINGS")
            self.assertEqual(result["private_key_blob_count"], 1)
            row = result["private_key_blobs"][0]
            self.assertEqual(row["path_seen"], "keys/server.key")
            self.assertEqual(row["bytes"], len(key))
            self.assertEqual(row["head_paths"], [])
            self.assertEqual([c["commit"] for c in result["private_key_added_in"]], [added])
            self.assertEqual([c["commit"] for c in result["private_key_removed_in"]], [removed])
            self.assertEqual(result["oversize_limit_bytes"], scrub_for_publish.HISTORY_LIMIT)
            self.assertEqual(result["oversize_blob_count"], 1)
            self.assertEqual(result["oversize_blobs"][0]["bytes"], size)
            self.assertEqual(result["oversize_blobs"][0]["head_paths"], ["big.dat"])
            self.assertGreater(result["blob_bytes_scanned"], size)
            self.assertEqual(scrub_for_publish.history(root, limit=size)["oversize_blob_count"], 0)
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                self.assertEqual(scrub_for_publish.main(["--check", "--history", "--root", str(root)]), 1)
            self.assertEqual(json.loads(printed.getvalue())["private_key_blob_count"], 1)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                scrub_for_publish.main(["--history", "--root", str(root)])
            self.assertEqual(raised.exception.code, 2)
            self.assertEqual(git("rev-parse", "HEAD"), removed)
            self.assertEqual(git("status", "--porcelain", "--untracked-files=all"), status)
        self.assertFalse(root.exists())


if __name__ == "__main__":
    unittest.main()
