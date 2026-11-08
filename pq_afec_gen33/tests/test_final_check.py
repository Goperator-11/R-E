import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / 'tools/final_check.py'
SPEC = importlib.util.spec_from_file_location('final_checks', SCRIPT)
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)
HOLD_FAILURE = ('    qamp_hold_test.go:1: count=2 want=3\n'
                '--- FAIL: TestHoldQUICReferencePathUnusedParityBeforeFirstCrypto (0.00s)\n'
                '    --- FAIL: TestHoldQUICReferencePathUnusedParityBeforeFirstCrypto/none (0.00s)\n')
GO_PASS = '--- PASS: TestExample (0.00s)\nPASS\nok example\n'
M1_PASS = ('--- PASS: TestHoldPythonReadFromReference (1.00s)\n'
           '--- PASS: TestUDPHoldPythonReadBatchReference (1.00s)\nPASS\n')


def test_measurement_lock_rejects_before_any_subprocess_or_output(tmp_path, monkeypatch):
    lock = tmp_path / 'MEASURE_LOCK.json'
    lock.write_text('{}', encoding='utf-8')
    monkeypatch.setattr(CHECK, 'LOCK_WINDOWS', lock)
    monkeypatch.setattr(CHECK, 'LOCK_WSL', lock)
    run = Mock(side_effect=AssertionError('must not start a subprocess'))
    monkeypatch.setattr(CHECK.subprocess, 'run', run)
    output = tmp_path / 'result.json'
    assert CHECK.main(['--install', '--out', str(output)]) == 2
    run.assert_not_called()
    assert list(tmp_path.iterdir()) == [lock]


@pytest.mark.parametrize('install', [False, True])
def test_build_environment_drops_inherited_stage_pruning_and_redirects_outputs(
        tmp_path, monkeypatch, install):
    monkeypatch.setenv('GEN33_KEEP_STAGES', '1')
    monkeypatch.setenv('QAMP_GEN33_OUT', '/unsafe/inherited/output')
    monkeypatch.setenv('M1_REFERENCE_GZIP', '/unrelated/reference')
    link = Mock()
    monkeypatch.setattr(Path, 'symlink_to', link)
    env = CHECK.build_env(tmp_path, install)
    assert 'GEN33_KEEP_STAGES' not in env
    assert 'M1_REFERENCE_GZIP' not in env
    assert env['HOME'] == str(tmp_path)
    assert env['GOPATH'] == str(tmp_path / 'gopath')
    assert env['GOCACHE'] == str(tmp_path / ('.cache/go-build' if install else 'gocache'))
    assert env['GOMODCACHE'] == '/home/scien/gopath/pkg/mod'
    assert env['PYTHONDONTWRITEBYTECODE'] == '1'
    assert os.environ['GEN33_KEEP_STAGES'] == '1'
    if install:
        assert 'QAMP_GEN33_OUT' not in env
        link.assert_not_called()
    else:
        assert env['QAMP_GEN33_OUT'] == str(tmp_path / 'out')
        link.assert_called_once_with('/home/scien/goroot', target_is_directory=True)


@pytest.mark.parametrize('text', [
    '',
    'testing: warning: no tests to run\nPASS\nok example [no tests to run]\n',
    M1_PASS.replace('--- PASS: TestHoldPythonReadFromReference',
                    '--- SKIP: TestHoldPythonReadFromReference'),
    M1_PASS.replace('TestUDPHoldPythonReadBatchReference', 'TestUnrelated'),
    M1_PASS + '--- PASS: TestUnrelated (0.00s)\n',
])
def test_m1_rejects_missing_skipped_or_wrong_reference_tests(text):
    with pytest.raises(CHECK.CheckFailed, match='both reference tests'):
        CHECK.validate_m1(text)


def test_m1_accepts_both_executed_reference_tests():
    counts = CHECK.validate_m1(M1_PASS)
    assert counts['pass'] == 2
    assert counts['skip'] == counts['fail'] == 0


@pytest.mark.parametrize('outcomes, expected_calls, success', [
    ([(4, HOLD_FAILURE, ''), (0, GO_PASS, 'ok example\n')], 2, True),
    ([(4, HOLD_FAILURE, ''), (4, HOLD_FAILURE, '')], 2, False),
    ([(4, HOLD_FAILURE + '--- FAIL: TestOther (0.00s)\n', '')], 1, False),
    ([(4, HOLD_FAILURE, 'WARNING: DATA RACE\n')], 1, False),
    ([(4, HOLD_FAILURE.replace('count=2 want=3', 'count=1 want=3'), '')], 1, False),
    ([(1, HOLD_FAILURE, '')], 1, False),
    ([(137, HOLD_FAILURE, '')], 1, False),
    ([(4, HOLD_FAILURE + 'FAIL example [build failed]\n', '')], 1, False),
    ([(4, HOLD_FAILURE + 'fatal error: all goroutines are asleep\n', '')], 1, False),
    ([(4, HOLD_FAILURE + 'test timed out after 10m\n', '')], 1, False),
    ([(4, HOLD_FAILURE + 'write: no space left on device\n', '')], 1, False),
    ([(4, HOLD_FAILURE + 'signal: killed\n', '')], 1, False),
    ([(4, HOLD_FAILURE + 'file.go:1: undefined: missingSymbol\n', '')], 1, False),
    ([(4, '', '')], 1, False),
])
def test_build_retries_only_one_known_hold_failure(
        tmp_path, monkeypatch, outcomes, expected_calls, success):
    artifacts = tmp_path / 'artifacts'
    artifacts.mkdir()
    report = {'steps': []}
    calls = []
    stale = tmp_path / 'quicbed_gen33/bin'
    stale.mkdir(parents=True)
    (stale / 'go_test.txt').write_text(HOLD_FAILURE, encoding='utf-8')

    def fake_step(current_report, current_artifacts, name, command, env, required):
        assert required is False
        calls.append(command)
        rc, test_text, race_text = outcomes[len(calls) - 1]
        stage = tmp_path / 'quicbed_gen33' / ('stage.%06d' % len(calls))
        record = stage / 'build_record'
        record.mkdir(parents=True)
        if test_text:
            (record / 'go_test.txt').write_text(test_text, encoding='utf-8')
        if race_text:
            (record / 'go_race.txt').write_text(race_text, encoding='utf-8')
        step = {'name': name, 'returncode': rc, 'log': str(artifacts / (name + '.log'))}
        current_report['steps'].append(step)
        return step, ''

    monkeypatch.setattr(CHECK, 'run_step', fake_step)
    if success:
        stage = CHECK.build(report, artifacts, {}, tmp_path)
        assert stage.name == 'stage.000002'
        assert report['go']['pass'] == 1
        assert report['race_reports'] == 0
        assert (artifacts / 'build_1_stage_0_go_test.txt').read_text() == HOLD_FAILURE
        assert (artifacts / 'build_2_stage_0_go_test.txt').read_text() == GO_PASS
    else:
        with pytest.raises(CHECK.CheckFailed, match='Go build failed'):
            CHECK.build(report, artifacts, {}, tmp_path)
    assert len(calls) == expected_calls
    assert all(call[-1] == '--race' for call in calls)


@pytest.mark.parametrize('error', [OSError('command unavailable'), None])
def test_main_records_failed_step_and_log_in_json(tmp_path, monkeypatch, error):
    absent_lock = tmp_path / 'absent-lock.json'
    monkeypatch.setattr(CHECK, 'LOCK_WINDOWS', absent_lock)
    monkeypatch.setattr(CHECK, 'LOCK_WSL', absent_lock)
    monkeypatch.setattr(CHECK, 'os', SimpleNamespace(name='nt', environ=os.environ))
    monkeypatch.setattr(CHECK, 'git_output', Mock(side_effect=['head-sha', '']))
    run = Mock(side_effect=error, return_value=SimpleNamespace(returncode=3))
    monkeypatch.setattr(CHECK.subprocess, 'run', run)
    output = tmp_path / 'result.json'
    assert CHECK.main(['--out', str(output)]) == 1
    report = json.loads(output.read_text(encoding='utf-8'))
    assert report['passed'] is False
    assert report['git_head'] == 'head-sha'
    assert len(report['steps']) == 1
    step = report['steps'][0]
    assert step['name'] == 'pytest'
    assert step['returncode'] == (1 if error else 3)
    assert Path(step['log']).is_file()
    assert step['log'] in report['error']
    assert report['finished_utc']
    command = run.call_args.args[0]
    assert command[1:] == ['-I', '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider']
    if error:
        assert 'command unavailable' in Path(step['log']).read_text(encoding='utf-8')


def test_main_rejects_success_exit_without_passing_tests(tmp_path, monkeypatch):
    absent_lock = tmp_path / 'absent-lock.json'
    monkeypatch.setattr(CHECK, 'LOCK_WINDOWS', absent_lock)
    monkeypatch.setattr(CHECK, 'LOCK_WSL', absent_lock)
    monkeypatch.setattr(CHECK, 'os', SimpleNamespace(name='nt', environ=os.environ))
    monkeypatch.setattr(CHECK, 'git_output', Mock(side_effect=['head-sha', '']))
    run = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(CHECK.subprocess, 'run', run)
    output = tmp_path / 'result.json'
    assert CHECK.main(['--out', str(output)]) == 1
    report = json.loads(output.read_text(encoding='utf-8'))
    assert report['passed'] is False
    assert report['error'] == 'pytest did not report passing tests'
    assert run.call_count == 1
