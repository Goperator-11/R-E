import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
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

    def test_private_key_patterns_cover_legacy_encrypted_headers(self):
        def block(*lines, newline="\n"):
            return newline.join(lines).encode("ascii")

        legacy = ("-----BEGIN RSA PRIVATE KEY-----", "Proc-Type: 4,ENCRYPTED", "DEK-Info: AES-128-CBC,00112233445566778899AABBCCDDEEFF",
                  "", "YWJjZA==", "ZWZnaA==", "-----END RSA PRIVATE KEY-----", "")
        found = {
            "pkcs8": block("-----BEGIN PRIVATE KEY-----", "YWJjZA==", "-----END PRIVATE KEY-----", ""),
            "ec": block("-----BEGIN EC PRIVATE KEY-----", "YWJjZA==", "-----END EC PRIVATE KEY-----", ""),
            "pkcs8_crlf": block("-----BEGIN PRIVATE KEY-----", "YWJjZA==", "-----END PRIVATE KEY-----", "", newline="\r\n"),
            "legacy_encrypted_rsa": block(*legacy),
            "legacy_encrypted_rsa_crlf": block(*legacy, newline="\r\n"),
            "legacy_encrypted_in_text": b"notes\n" + block(*legacy) + b"more notes\n",
        }
        quiet = {
            "begin_only": block("-----BEGIN PRIVATE KEY-----", "header only", ""),
            "headers_without_body": block("-----BEGIN RSA PRIVATE KEY-----", "Proc-Type: 4,ENCRYPTED",
                                          "DEK-Info: AES-128-CBC,00", "-----END RSA PRIVATE KEY-----", ""),
            "kind_mismatch": block("-----BEGIN RSA PRIVATE KEY-----", "Proc-Type: 4,ENCRYPTED", "", "YWJjZA==",
                                   "-----END EC PRIVATE KEY-----", ""),
            "described_format": block("-----BEGIN RSA PRIVATE KEY-----", "Proc-Type: 4,ENCRYPTED", "<base64 body>",
                                      "-----END RSA PRIVATE KEY-----", ""),
        }
        for pattern in (precommit_size.PRIVATE_KEY, scrub_for_publish.PRIVATE_KEY_BLOCK):
            for name, raw in found.items():
                with self.subTest(pattern=pattern.pattern[:12], case=name):
                    self.assertIsNotNone(pattern.search(raw))
            for name, raw in quiet.items():
                with self.subTest(pattern=pattern.pattern[:12], case=name):
                    self.assertIsNone(pattern.search(raw))
        self.assertEqual(precommit_size.PRIVATE_KEY.pattern, scrub_for_publish.PRIVATE_KEY_BLOCK.pattern)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.git(root, "init", "-q")
            path = root / "legacy.key"
            path.write_bytes(found["legacy_encrypted_rsa"])
            self.git(root, "add", "--", path.name)
            result = precommit_size.check(root)
            self.assertEqual(result["status"], "FAIL")
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
            self.assertEqual(result["file_listing"], "git ls-files")
            self.assertEqual(result["affected_file_counts"], {"user_path": 1, "email": 1, "private_key": 1})
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
            self.assertNotIn("a@example.invalid", json.dumps(result))

    def test_publish_check_walks_a_plain_folder_and_skips_git_folders(self):
        with tempfile.TemporaryDirectory() as directory:
            outer = Path(directory)
            self.git(outer, "init", "-q")
            root = outer / "pq_afec_gen33"
            (root / "docs").mkdir(parents=True)
            (root / "docs/기록.md").write_text("C:/Users/unit/data\n", encoding="utf-8")
            (root / "notes.txt").write_text("a@example.invalid\n", encoding="utf-8")
            (root / "figure.png").write_bytes(b"\x89PNG C:/Users/unit/x")
            (root / "vendor/.git").mkdir(parents=True)
            (root / "vendor/.git/config").write_text("C:/Users/unit/hidden\n", encoding="utf-8")
            (root / "vendor/keep.txt").write_text("plain\n", encoding="utf-8")
            before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
            result = scrub_for_publish.check(root)
            self.assertEqual(result["file_listing"], "os.walk")
            self.assertEqual(result["status"], "FINDINGS")
            self.assertEqual(result["affected_file_counts"], {"user_path": 1, "email": 1})
            self.assertEqual(result["text_files_scanned"], 3)
            self.assertEqual(result["known_binary_files_not_decoded"], 1)
            self.assertEqual(sorted(row["path"] for row in result["examples"]), ["docs/기록.md", "notes.txt"])
            self.assertEqual(result["unavailable"], [])
            self.assertEqual({path: path.read_bytes() for path in root.rglob("*") if path.is_file()}, before)
            parent = scrub_for_publish.check(outer)
            self.assertEqual(parent["file_listing"], "git ls-files")
            self.assertEqual(parent["text_files_scanned"], 0)

    def test_publish_check_prints_utf8_json_when_stdout_starts_as_cp949(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "한글 경로.txt").write_text("C:/Users/unit/data\n", encoding="utf-8")
            raw = io.BytesIO()
            stream = io.TextIOWrapper(raw, encoding="cp949", newline="\n")
            with contextlib.redirect_stdout(stream):
                self.assertEqual(scrub_for_publish.main(["--check", "--root", str(root)]), 1)
            stream.flush()
            result = json.loads(raw.getvalue().decode("utf-8"))
            self.assertEqual(result["file_listing"], "os.walk")
            self.assertEqual(result["examples"], [{"path": "한글 경로.txt", "line": 1, "kind": "user_path"}])
            script = Path(scrub_for_publish.__file__).resolve()
            done = subprocess.run([sys.executable, "-I", "-B", str(script), "--check", "--root", str(root)],
                                  capture_output=True, timeout=120)
            self.assertEqual(done.returncode, 1, done.stderr)
            self.assertEqual(json.loads(done.stdout.decode("utf-8")), result)

    def test_history_check_refuses_a_folder_that_is_not_a_git_top_folder(self):
        with tempfile.TemporaryDirectory() as plain, tempfile.TemporaryDirectory() as directory:
            outer = Path(directory)
            self.git(outer, "init", "-q")
            inside = outer / "pq_afec_gen33"
            inside.mkdir()
            (inside / "notes.txt").write_text("plain\n", encoding="utf-8")
            for root in (Path(plain), inside):
                with self.subTest(root=root.name):
                    with contextlib.redirect_stdout(io.StringIO()) as printed, contextlib.redirect_stderr(io.StringIO()) as message:
                        self.assertEqual(scrub_for_publish.main(["--check", "--history", "--root", str(root)]), 2)
                    self.assertEqual(printed.getvalue(), "")
                    self.assertIn("--history", message.getvalue())
                    self.assertIn(str(root), message.getvalue())
            missing = outer / "missing"
            with contextlib.redirect_stdout(io.StringIO()) as printed, contextlib.redirect_stderr(io.StringIO()) as message:
                self.assertEqual(scrub_for_publish.main(["--check", "--root", str(missing)]), 2)
            self.assertEqual(printed.getvalue(), "")
            self.assertIn(str(missing), message.getvalue())

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
