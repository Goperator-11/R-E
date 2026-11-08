import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]

GUARDED_PROCESS = r'''
import builtins
import io
import os
import runpy
import shutil
import socket
import subprocess
import sys

root, target, *args = sys.argv[1:]
sys.path[:0] = [root, os.path.join(root, "experiments")]

def forbidden(*args, **kwargs):
    raise AssertionError("filesystem mutation, process launch or network operation attempted")

original_open = builtins.open
def read_only_open(file, mode="r", *args, **kwargs):
    if any(flag in mode for flag in "wax+"):
        forbidden()
    return original_open(file, mode, *args, **kwargs)

builtins.open = read_only_open
io.open = read_only_open
os.makedirs = forbidden
os.mkdir = forbidden
os.replace = forbidden
os.remove = forbidden
os.unlink = forbidden
shutil.copy = forbidden
shutil.copy2 = forbidden
subprocess.run = forbidden
subprocess.Popen = forbidden
socket.socket = forbidden
if target == "padbed":
    import padbed
    for fn, args in ((padbed.require_root, ()), (padbed.require_bin, ()),
                     (padbed.setup, ()), (padbed.run, ("never execute",))):
        try:
            fn(*args)
        except RuntimeError as exc:
            assert "disabled in gen33" in str(exc)
        else:
            raise AssertionError("legacy live entry did not refuse")
    print("padbed import and shared live guards passed")
else:
    sys.argv = [target] + args
    runpy.run_path(os.path.join(root, "experiments", target), run_name="__main__")
'''


class RunnerIsolationTests(unittest.TestCase):
    def run_guarded(self, target, *args):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, "-I", "-B", "-c", GUARDED_PROCESS, str(ROOT), target, *args],
                cwd=directory, capture_output=True, text=True, timeout=20)
            self.assertEqual(list(Path(directory).iterdir()), [])
            self.assertNotIn("operation attempted", result.stderr)
            return result

    def test_legacy_loop_clis_refuse_before_writes_or_process_launch(self):
        cases = (("loop2.py", "--only-exact", "--only", "p11"),
                 ("loop2.py", "--status"),
                 ("fixloop.py", "--detach", "--rounds", "2"),
                 ("forever.py", "--rounds", "2"),
                 ("pipeline.py", "--status"), ("pipeline.py", "--loop"))
        for args in cases:
            with self.subTest(args=args):
                result = self.run_guarded(*args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("disabled in", result.stderr)

    def test_historical_comparison_and_probe_clis_refuse(self):
        for args in (("p21_gencompare.py", "--run1"), ("g31_probe.py", "--run"),
                     ("g3_stage0.py", "--smoke"), ("g3_m1confirm.py", "--full"),
                     ("_probe_race.py",), ("_add_drop_flags.py",),
                     ("_fix_qfec_cauchy.py",)):
            with self.subTest(args=args):
                result = self.run_guarded(*args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("disabled in", result.stderr)

    def test_padbed_import_and_shared_live_entries_do_not_write_or_run(self):
        result = self.run_guarded("padbed")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("shared live guards passed", result.stdout)

    def test_historical_shell_entry_points_exit_before_old_paths(self):
        names = ("live_demo.sh", "build.sh", "build_g3.sh", "build_g3b.sh",
                 "build_g3c.sh", "build_server.sh", "diag.sh")
        for name in names:
            with self.subTest(name=name):
                lines = (ROOT / "experiments" / "quicbed" / name).read_text(encoding="utf-8").splitlines()
                self.assertEqual(lines[0], "#!/bin/bash")
                self.assertIn("disabled in gen33", lines[1])
                self.assertEqual(lines[2], "exit 2")


if __name__ == "__main__":
    unittest.main()
