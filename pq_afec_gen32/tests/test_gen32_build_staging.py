import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

GO_STUB = '''#!PYTHON
import json, os, pathlib, sys
cwd = pathlib.Path.cwd()
home = pathlib.Path(os.environ['HOME'])
assert cwd.parent == home / 'quicbed_gen32', cwd
assert cwd.name.startswith('stage.'), cwd
assert not (cwd / 'cmd/qamp/obsolete_test.go').exists()
assert (cwd / 'cmd/qamp/main.go').is_file()
with open(os.environ['STAGE_TEST_LOG'], 'a') as f:
    f.write(json.dumps({'cwd': str(cwd), 'args': sys.argv[1:]}) + '\\n')
if sys.argv[1] == 'test':
    print('--- PASS: TestBuildStub (0.00s)')
    print('ok stub/cmd/qamp')
elif sys.argv[1] == 'build':
    pathlib.Path(sys.argv[sys.argv.index('-o') + 1]).write_bytes(b'staging-test-stub')
'''


@unittest.skipIf(os.name == 'nt' or shutil.which('bash') is None,
                 'Run Bash integration in WSL')
class BuildStagingTests(unittest.TestCase):
    def test_repeated_build_uses_fresh_sources_and_cleans_only_its_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            old = home / 'quicbed_gen32/cmd/qamp/obsolete_test.go'
            old.parent.mkdir(parents=True)
            old.write_text('old source must never be compiled', encoding='utf-8')
            compiler = home / 'goroot/bin/go'
            compiler.parent.mkdir(parents=True)
            compiler.write_text(GO_STUB.replace('PYTHON', sys.executable, 1), encoding='utf-8')
            compiler.chmod(0o755)
            log = home / 'compiler-calls.jsonl'
            env = dict(os.environ, HOME=str(home), STAGE_TEST_LOG=str(log))
            # Replace only the installation path in a scratch copy of the builder.
            source = ROOT / 'experiments/quicbed'
            scratch = home / 'source'
            shutil.copytree(source, scratch)
            script = scratch / 'build_gen32.sh'
            script.write_text(script.read_text().replace('OUT=/tmp/qamp_gen32',
                              'OUT="$HOME/install"'), encoding='utf-8')
            for _ in range(2):
                result = subprocess.run(['bash', str(script), '--race'], env=env,
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('gen32 race passed', result.stdout)
                self.assertEqual(list((home / 'quicbed_gen32').glob('stage.*')), [])
                self.assertEqual(old.read_text(), 'old source must never be compiled')
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual(len(calls), 8)
            self.assertEqual(len({call['cwd'] for call in calls}), 2)
            self.assertEqual(sum('-race' in call['args'] for call in calls), 2)

    def test_unknown_option_exits_before_creating_build_files(self):
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, HOME=directory)
            result = subprocess.run(['bash', str(ROOT / 'experiments/quicbed/build_gen32.sh'),
                                     '--invalid'], env=env, capture_output=True,
                                    text=True, timeout=5)
            self.assertEqual(result.returncode, 2)
            self.assertIn('usage:', result.stderr)
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
