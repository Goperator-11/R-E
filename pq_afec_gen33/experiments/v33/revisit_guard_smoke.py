import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import time

spec = importlib.util.spec_from_file_location('revisit_smoke', Path(__file__).with_name('revisit_smoke.py'))
revisit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(revisit)
obs = revisit.obs
CASES = [
    dict(name='parity_token', kind='parity', support='supported', token=True),
    dict(name='parity_retry_token', kind='parity', support='supported', token=True, verify=True),
    dict(name='parity_retry_cold', kind='parity', support='supported', verify=True),
    dict(name='parity_token_all_lead', kind='parity', support='supported', token=True, lead=3),
    dict(name='dup_unknown_token', kind='dup', support='unknown', token=True),
    dict(name='dup_unsupported_retry_token', kind='dup', support='unsupported', token=True, verify=True, server_fec=False),
    dict(name='pad_unknown_token', kind='pad_junk', support='unknown', token=True),
    dict(name='pad_unsupported_retry_token', kind='pad_junk', support='unsupported', token=True, verify=True, server_fec=False),
    dict(name='parity_token_resume_rtt200', kind='parity', support='supported', token=True, resume=True, delay_ms=100),
    dict(name='dup_unknown_retry_resume_rtt200', kind='dup', support='unknown', verify=True, resume=True, delay_ms=100),
]


def inspect(case, rows, events, server):
    ports = list(dict.fromkeys(e['peer_port'] for e in events if e['direction'] == 'c2s'))
    assert len(ports) == len(rows) == 3
    details = []
    for row, port in zip(rows, ports):
        i = row['i']
        assert row['ok'], (case['name'], i, row)
        records = row['flight_trace']['records']
        assert row['flight_trace']['omitted'] == 0 and records
        assert all(f['flushed'] and f['complete'] and f['flush_tx_errors'] == 0 for f in records)
        wire = [e for e in events if e['direction'] == 'c2s' and e['peer_port'] == port and e['initial']]
        originals = [e for e in wire if e['parity'] is None and b'JUNK' not in bytes.fromhex(e['wire_hex'])]
        token_bytes = revisit.initial_token_bytes(originals[0])
        token = bool(case.get('token')) and i > 0
        retry = bool(case.get('verify')) and not token
        assert bool(token_bytes) == token
        guard, extra = row['revisit_guard'], row['extra_sent']
        assert guard['version'] == 1 and guard['initial_seen']
        assert guard['initial_token_bytes'] == token_bytes and guard['token_input_source'] == 'first_initial_header'
        assert guard['server_acceptance'] == 'unknown' and guard['decoder_support'] == case['support']
        assert guard['retry_accepted'] == retry and guard['retry_consumed'] == retry
        assert row['revisit']['retry_received'] == int(retry)
        assert row['revisit']['tls_did_resume'] == (bool(case.get('resume')) and i > 0)
        lead, m = case.get('lead', 1), 3
        expected = (0 if case['kind'] == 'pad_junk' else m - lead) if token else m
        expected_lead = 0 if token else lead
        assert extra['kind'] == case['kind'] and extra['sent'] == extra['first_sent'] == expected
        assert extra['first_lead'] == expected_lead and extra['errors'] == 0
        assert guard['bundles_reserved'] == int(expected > 0)
        assert (records[0]['shape']['lead'], records[0]['shape']['trail']) == (expected_lead, expected - expected_lead)
        assert all(f['shape']['lead'] == f['shape']['trail'] == f['extra_sent']['sent'] == 0 for f in records[1:])
        assert sum(f['shape']['phase'] == 'retry_bundle' for f in records) == int(retry)
        count = sum(f['flush_tx_dgrams'] + (f['actual_k'] if f['original_immediate'] else 0) for f in records)
        total = sum(f['flush_tx_bytes'] + (f['original_bytes'] if f['original_immediate'] else 0) for f in records)
        assert (count, total) == (len(wire), sum(e['bytes'] for e in wire))
        assert extra['bytes'] == sum(f['extra_sent']['bytes'] for f in records)
        assert len(wire) == sum(f['actual_k'] for f in records) + expected
        if case['kind'] == 'parity':
            parity = [e for e in wire if e['parity']]
            assert len(parity) == expected and sum(e['bytes'] for e in parity) == extra['bytes']
            assert all(e['parity']['lead'] == expected_lead and e['parity']['m'] == expected for e in parity)
        elif case['kind'] == 'pad_junk':
            pads = [e for e in wire if b'JUNK' in bytes.fromhex(e['wire_hex'])]
            assert len(pads) == expected and sum(e['bytes'] for e in pads) == extra['bytes']
        else:
            assert len(wire) - len({e['wire_hex'] for e in wire}) >= expected
        details.append(dict(i=i, token_bytes=token_bytes, retry=retry, resumed=row['revisit']['tls_did_resume'], extra=extra, guard=guard, flights=len(records), wire_datagrams=len(wire), wire_bytes=total, pto_count=row['observation']['pto_count']))
    assert server['tls_accepted'] == 3
    assert server['tls_resumed'] == (2 if case.get('resume') else 0)
    assert server['address_verified_contexts'] == (3 if case.get('verify') else 2 if case.get('token') else 0)
    return details


def run(args):
    binary, out, work = args.binary.resolve(), args.out.resolve(), args.work.resolve()
    assert work.is_relative_to(Path.home() / 'quicbed_gen33')
    plan = dict(schema='m4-revisit-guard-smoke/1', label='development', purpose='Fixed-arm wire invariants; no HCT performance inference', cases=CASES, connections_per_case=3, udp_path=args.udp_path, binary=str(binary), binary_sha256=obs.sha(binary), script_sha256=obs.sha(__file__), revisit_script_sha256=obs.sha(revisit.__file__), relay_sha256=obs.sha(obs.__file__))
    if args.dry_run:
        obs.save(out.with_suffix('.plan.json'), plan)
        print(json.dumps(dict(status='PLAN', cases=len(CASES), connections=3 * len(CASES))))
        return
    assert json.loads(out.with_suffix('.plan.json').read_text(encoding='utf-8')) == plan
    out.mkdir(exist_ok=False)
    work.mkdir(exist_ok=False)
    local = work / 'qamp'
    shutil.copyfile(binary, local)
    local.chmod(0o700)
    assert obs.sha(local) == plan['binary_sha256']
    results = []
    for case in CASES:
        name = case['name']
        with obs.bind() as temporary:
            addr = temporary.getsockname()
        stats, log = out / (name + '.server.json'), out / (name + '.server.stderr')
        cmd = [str(local), '-mode', 'server', '-addr', f'{addr[0]}:{addr[1]}', '-certsize', '6000', '-fec', 'on' if case.get('server_fec', True) else 'off', '-stats', str(stats), '-udp-path', args.udp_path]
        if case.get('verify'):
            cmd += ['-verify-source']
        if case.get('resume'):
            cmd += ['-resume']
        relay = None
        with log.open('xb') as stream:
            server = subprocess.Popen(cmd, stdout=stream, stderr=subprocess.STDOUT)
            try:
                obs.wait_ready(server, log)
                relay = obs.Relay(addr, dict(delay_ms=case.get('delay_ms', 0), capture_wire=True))
                client = [str(local), '-mode', 'client', '-addr', f'{relay.address[0]}:{relay.address[1]}', '-fec', 'on', '-layout', 'v3', '-lead', str(case.get('lead', 1)), '-m', '3', '-expect-k', '2', '-n', '3', '-gap', '10ms', '-timeout', '3s', '-revisit-guard', '-decoder-support', case['support'], '-stats', str(out / (name + '.client.json'))]
                if case['kind'] != 'parity':
                    client += ['-dup' if case['kind'] == 'dup' else '-pad-junk']
                if case.get('token'):
                    client += ['-token-store']
                if case.get('resume'):
                    client += ['-resume']
                completed = subprocess.run(client, capture_output=True, timeout=30)
                (out / (name + '.stdout')).write_bytes(completed.stdout)
                (out / (name + '.stderr')).write_bytes(completed.stderr)
                obs.save(out / (name + '.command.json'), dict(server=cmd, client=client, exit_code=completed.returncode))
                assert completed.returncode == 0, (name, completed.stderr.decode())
                rows = [json.loads(line) for line in completed.stdout.splitlines()]
                time.sleep(.15)
            finally:
                if relay:
                    relay.close()
                    obs.save(out / (name + '.relay.json'), relay.events)
                obs.stop(server)
        ss = json.loads(stats.read_text(encoding='utf-8'))
        details = inspect(case, rows, relay.events, ss)
        value = dict(name=name, connections=3, successes=3, rows=details)
        results.append(value)
        obs.save(out / (name + '.inspection.json'), value)
    obs.save(out / 'result.json', dict(status='PASS', plan=plan, results=results))
    print(json.dumps(dict(status='PASS', cases=len(CASES), connections=3 * len(CASES))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--udp-path', choices=('basic', 'oob'), required=True)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--dry-run', action='store_true')
    group.add_argument('--smoke', action='store_true')
    run(parser.parse_args())
