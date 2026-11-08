import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
LOCK_WINDOWS = Path('C:/dev/codex_handoff/final/state/MEASURE_LOCK.json')
LOCK_WSL = Path('/mnt/c/dev/codex_handoff/final/state/MEASURE_LOCK.json')
M1_REFERENCE = ROOT / 'g3/v33/validation/M1_stage1/runs/M1_wire_reference_02.tsv.gz'
M1_NAMES = {'TestHoldPythonReadFromReference', 'TestUDPHoldPythonReadBatchReference'}
FLAKY_TEST = 'TestHoldQUICReferencePathUnusedParityBeforeFirstCrypto'


class CheckFailed(Exception):
    pass


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def clean_env():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
    env.pop('GEN33_KEEP_STAGES', None)
    env.pop('M1_REFERENCE_GZIP', None)
    return env


def build_env(home, install):
    env = clean_env()
    env.update(HOME=str(home), GOPATH=str(home / 'gopath'),
               GOCACHE=str(home / ('.cache/go-build' if install else 'gocache')),
               GOMODCACHE='/home/scien/gopath/pkg/mod', GOROOT='/home/scien/goroot',
               CGO_ENABLED='0', GOFLAGS='-mod=readonly', GOAMD64='v1',
               GOTOOLCHAIN='local', GOPROXY='off', GOSUMDB='off')
    env['PATH'] = '/home/scien/goroot/bin:' + env.get('PATH', '')
    if install:
        env.pop('QAMP_GEN33_OUT', None)
    else:
        env['QAMP_GEN33_OUT'] = str(home / 'out')
        (home / 'goroot').symlink_to('/home/scien/goroot', target_is_directory=True)
    return env


def go_counts(text):
    names = {kind.lower(): re.findall(r'^--- ' + kind + r': (\S+)', text, re.MULTILINE)
             for kind in ('PASS', 'SKIP', 'FAIL')}
    return {**{kind: len(items) for kind, items in names.items()}, 'names': names}


def known_hold_failure(text):
    failures = re.findall(r'^\s*--- FAIL: (\S+)', text, re.MULTILINE)
    errors = ('DATA RACE', 'panic:', 'fatal error:', '[build failed]',
              'timed out', 'no space left', 'signal: killed', 'undefined:')
    return (bool(failures) and all(name.split('/')[0] == FLAKY_TEST for name in failures)
            and re.search(r'count=2\s+want=3', text) is not None
            and not any(error in text for error in errors))


def validate_m1(text):
    counts = go_counts(text)
    if (set(counts['names']['pass']) != M1_NAMES or counts['pass'] != 2
            or counts['skip'] or counts['fail'] or 'no tests to run' in text):
        raise CheckFailed('M1 must execute and pass both reference tests without skips')
    return counts


def run_step(report, artifacts, name, command, env, cwd=ROOT, required=True):
    log = artifacts / (name + '.log')
    step = {'name': name, 'command': [str(part) for part in command], 'log': str(log)}
    report['steps'].append(step)
    started = time.monotonic()
    print('running ' + name, flush=True)
    try:
        with log.open('w', encoding='utf-8') as stream:
            result = subprocess.run(command, cwd=cwd, env=env, stdout=stream,
                                    stderr=subprocess.STDOUT, check=False)
        step['returncode'] = result.returncode
    except OSError as error:
        step['returncode'] = 1
        step['error'] = str(error)
        log.write_text(str(error) + '\n', encoding='utf-8')
    step['seconds'] = round(time.monotonic() - started, 3)
    if required and step['returncode']:
        raise CheckFailed(name + ' failed; see ' + str(log))
    return step, log.read_text(encoding='utf-8', errors='replace')


def stages(home):
    return sorted(path for path in (home / 'quicbed_gen33').glob('stage.*') if path.is_dir())


def build(report, artifacts, env, home):
    for attempt in (1, 2):
        before = set(stages(home))
        step, output = run_step(report, artifacts, 'build_' + str(attempt),
                                ['bash', 'experiments/quicbed/build_gen33.sh', '--race'],
                                env, required=False)
        created = set(stages(home)) - before
        step['stages'] = [str(path) for path in sorted(created)]
        logs = []
        for index, stage in enumerate(sorted(created)):
            for filename in ('go_test.txt', 'go_race.txt'):
                source = stage / 'build_record' / filename
                if source.is_file():
                    target = artifacts / ('build_%d_stage_%d_%s' % (attempt, index, filename))
                    shutil.copyfile(source, target)
                    logs.append(source.read_text(encoding='utf-8', errors='replace'))
        if step['returncode'] == 0:
            if len(created) != 1:
                raise CheckFailed('build did not produce exactly one stage')
            stage = next(iter(created))
            record = stage / 'build_record'
            report['go'] = go_counts((record / 'go_test.txt').read_text(encoding='utf-8'))
            race_text = (record / 'go_race.txt').read_text(encoding='utf-8')
            report['race_reports'] = race_text.count('WARNING: DATA RACE')
            if report['go']['pass'] == 0 or report['go']['fail'] or report['race_reports']:
                raise CheckFailed('Go results do not show a successful suite and race check')
            return stage
        if attempt == 1 and step['returncode'] == 4 and known_hold_failure(output + '\n' + '\n'.join(logs)):
            step['retry_reason'] = 'known hold timing failure count=2 want=3'
            print(step['retry_reason'], flush=True)
            continue
        raise CheckFailed('Go build failed; see ' + step['log'])


def wsl_worker(report, artifacts, install):
    scope = nullcontext(str(Path.home())) if install else tempfile.TemporaryDirectory(prefix='gen33-final-')
    with scope as directory:
        home = Path(directory)
        env = build_env(home, install)
        before = stages(home)
        report['stages_before'] = len(before)
        try:
            if LOCK_WSL.exists():
                raise CheckFailed('measurement lock appeared before build')
            stage = build(report, artifacts, env, home)
            binary = home / 'quicbed_gen33/bin/qamp'
            report['binary'] = str(binary)
            report['sha256'] = digest(binary)
            report['srcsha'] = binary.with_suffix('.srcsha').read_text().strip()
            declared = binary.with_suffix('.sha256').read_text().split()[0]
            if declared != report['sha256']:
                raise CheckFailed('binary SHA256 differs from qamp.sha256')
            for suffix in ('.sha256', '.srcsha', '.buildinfo'):
                shutil.copyfile(binary.with_suffix(suffix), artifacts / ('qamp' + suffix))
            if M1_REFERENCE.is_file():
                m1env = dict(env, M1_REFERENCE_GZIP=str(M1_REFERENCE))
                _, output = run_step(report, artifacts, 'm1_reference',
                                     ['go', 'test', '-count=1', '-run',
                                      '^(' + '|'.join(sorted(M1_NAMES)) + ')$', '-v', './cmd/qamp'],
                                     m1env, cwd=stage)
                report['m1'] = {'status': 'pass', **validate_m1(output),
                                'reference': str(M1_REFERENCE), 'sha256': digest(M1_REFERENCE)}
            else:
                report['m1'] = {'status': 'skip', 'reason': 'reference file absent',
                                'reference': str(M1_REFERENCE)}
            _, output = run_step(report, artifacts, 'cli_wiring',
                                 ['bash', 'experiments/quicbed/cli_tests/run_cli_tests.sh'], env)
            report['cli_wiring'] = go_counts(output)
            if report['cli_wiring']['pass'] == 0 or report['cli_wiring']['fail']:
                raise CheckFailed('CLI wiring tests did not pass')
            for name, script, extra, key in (
                ('gate_v3', 'experiments/gate_v3_parity.py', [], 'pass'),
                ('gate_l1', 'experiments/gate_l1_go.py',
                 ['--ref', 'g3/v33/V33FIX_policy_reference_v3.json', '--bin', str(binary)], 'passed'),
            ):
                target = artifacts / (name + '.json')
                run_step(report, artifacts, name, [sys.executable, '-I', '-B', script,
                         *extra, '--out', str(target)], env)
                result = json.loads(target.read_text(encoding='utf-8'))
                report[name] = result
                if result.get(key) is not True or result.get('problems') != []:
                    raise CheckFailed(name + ' did not pass without problems')
            run_step(report, artifacts, 'reference_check',
                     [sys.executable, '-I', '-B', 'g3/policy3_reference_gen.py', '--check'], env)
            _, output = run_step(report, artifacts, 'staging_unittest',
                                 [sys.executable, '-I', '-B', 'tests/test_gen33_build_staging.py'], env)
            match = re.search(r'Ran (\d+) tests? in', output)
            if not match or int(match[1]) != 2 or not re.search(r'^OK\s*$', output, re.MULTILINE):
                raise CheckFailed('both WSL staging tests must execute successfully')
            report['staging_tests'] = int(match[1])
        finally:
            after = stages(home)
            report['stages_after'] = len(after)
            report['stages_preserved'] = set(before).issubset(after)
            if not install:
                subprocess.run(['chmod', '-R', 'u+w', str(home)], check=True)
        if not report['stages_preserved']:
            raise CheckFailed('existing build stages were removed')


def wsl_path(path):
    value = str(path.resolve()).replace('\\', '/')
    if len(value) > 2 and value[1] == ':':
        return '/mnt/' + value[0].lower() + value[2:]
    return value


def git_output(*args):
    result = subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True,
                            text=True, encoding='utf-8', check=True, env=clean_env())
    return result.stdout.strip()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--install', action='store_true')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--wsl-worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    lock = LOCK_WINDOWS if os.name == 'nt' else LOCK_WSL
    if lock.exists():
        print('measurement lock exists: ' + str(lock), file=sys.stderr)
        return 2
    target = args.out.resolve()
    artifacts = target.parent / (target.stem + '_artifacts')
    if target.exists() or artifacts.exists():
        parser.error('output and artifact paths must be new')
    target.parent.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir()
    report = {'schema': 'gen33.final_check/1', 'install': args.install, 'passed': False,
              'started_utc': datetime.now(timezone.utc).isoformat(), 'steps': []}
    try:
        report['git_head'] = git_output('rev-parse', 'HEAD')
        if not args.wsl_worker:
            report['git_status'] = git_output('status', '--short')
        report['tool_sha256'] = digest(Path(__file__))
        if args.wsl_worker:
            if os.name == 'nt':
                raise CheckFailed('WSL worker requires Linux')
            wsl_worker(report, artifacts, args.install)
        else:
            if os.name != 'nt':
                raise CheckFailed('run this command with Windows Python')
            _, output = run_step(report, artifacts, 'pytest',
                                 [sys.executable, '-I', '-B', '-m', 'pytest', '-q',
                                  '-p', 'no:cacheprovider'], clean_env())
            report['pytest'] = {key: int(value) for value, key in re.findall(
                r'(\d+) (passed|skipped|deselected|failed|subtests passed)', output)}
            if report['pytest'].get('passed', 0) == 0:
                raise CheckFailed('pytest did not report passing tests')
            if lock.exists():
                raise CheckFailed('measurement lock appeared before WSL')
            worker_json = artifacts / 'wsl.json'
            command = ['python3', '-I', '-B', wsl_path(Path(__file__)), '--wsl-worker',
                       '--out', wsl_path(worker_json)]
            if args.install:
                command.append('--install')
            shell = 'unset GEN33_KEEP_STAGES; exec ' + shlex.join(command)
            step, _ = run_step(report, artifacts, 'wsl',
                               ['wsl', '-d', 'Ubuntu', '--exec', 'bash', '-c', shell],
                               clean_env(), required=False)
            if worker_json.is_file():
                worker = json.loads(worker_json.read_text(encoding='utf-8'))
                report['wsl'] = worker
                for key in ('sha256', 'srcsha', 'go', 'm1', 'race_reports', 'staging_tests',
                            'stages_before', 'stages_after', 'stages_preserved'):
                    if key in worker:
                        report[key] = worker[key]
            if step['returncode'] or not report.get('wsl', {}).get('passed'):
                raise CheckFailed('WSL verification failed; see ' + step['log'])
        report['git_head_after'] = git_output('rev-parse', 'HEAD')
        if report['git_head_after'] != report['git_head']:
            raise CheckFailed('git HEAD changed during verification')
        report['passed'] = True
    except (CheckFailed, OSError, ValueError, subprocess.SubprocessError) as error:
        report['error'] = str(error)
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        write_json(target, report)
    print(json.dumps({'passed': report['passed'], 'out': str(target),
                      'error': report.get('error')}, ensure_ascii=False), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
