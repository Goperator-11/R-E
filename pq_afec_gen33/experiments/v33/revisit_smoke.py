import argparse
import importlib.util
import itertools
import json
from pathlib import Path
import shutil
import subprocess
import time

spec=importlib.util.spec_from_file_location('observation_smoke',Path(__file__).with_name('observation_smoke.py'))
obs=importlib.util.module_from_spec(spec);spec.loader.exec_module(obs)
CASES=[dict(name=f'verify{v}_token{t}_resume{r}',verify=bool(v),token=bool(t),resume=bool(r),server_resume=bool(r)) for v,t,r in itertools.product((0,1),repeat=3)]
CASES += [dict(name='resume_server_off',resume=True),dict(name='tickets_client_off',server_resume=True),dict(name='token_tail2',token=True,fec=True),dict(name='retry_token_tail2',token=True,verify=True,fec=True),dict(name='token_rtt200',token=True,delay_ms=100),dict(name='retry_token_resume_rtt200',token=True,resume=True,server_resume=True,verify=True,delay_ms=100)]


def varint(data,at):
    size=1<<(data[at]>>6);assert at+size<=len(data)
    return int.from_bytes(data[at:at+size],'big')&((1<<(8*size-2))-1),at+size


def initial_token_bytes(event):
    data=bytes.fromhex(event['wire_hex']);assert data[0]&0xf0==0xc0 and data[1:5]==b'\0\0\0\1'
    at=6+data[5];at+=1+data[at];length,at=varint(data,at);assert at+length<len(data)
    return length


def run(args):
    binary,out,work=args.binary.resolve(),args.out.resolve(),args.work.resolve();assert work.is_relative_to(Path.home()/'quicbed_gen33')
    plan=dict(schema='t2-revisit-smoke/1',label='development',purpose='Same-IP token and TLS resumption functional validation; no performance inference',udp_path=args.udp_path,cases=CASES,connections_per_case=3,binary=str(binary),binary_sha256=obs.sha(binary),script_sha256=obs.sha(__file__),relay_sha256=obs.sha(obs.__file__))
    if args.dry_run:
        obs.save(out.with_suffix('.plan.json'),plan);print(json.dumps(dict(status='PLAN',cases=len(CASES),connections=3*len(CASES))));return
    assert json.loads(out.with_suffix('.plan.json').read_text(encoding='utf-8'))==plan
    out.mkdir(parents=True,exist_ok=False);work.mkdir(parents=True,exist_ok=False)
    local=work/'qamp';shutil.copyfile(binary,local);local.chmod(0o700);assert obs.sha(local)==plan['binary_sha256']
    results=[]
    for case in CASES:
        name=case['name'];token,resume,verify,server_resume=(bool(case.get(k)) for k in ('token','resume','verify','server_resume'))
        with obs.bind() as temp: server_addr=temp.getsockname()
        stats,log=out/(name+'.server.json'),out/(name+'.server.stderr')
        server_cmd=[str(local),'-mode','server','-addr',f'{server_addr[0]}:{server_addr[1]}','-certsize','6000','-fec','on','-stats',str(stats),'-udp-path',args.udp_path]
        if server_resume:server_cmd+=['-resume']
        if verify:server_cmd+=['-verify-source']
        relay=None
        with log.open('xb') as stream:
            server=subprocess.Popen(server_cmd,stdout=stream,stderr=subprocess.STDOUT)
            try:
                obs.wait_ready(server,log);relay=obs.Relay(server_addr,dict(delay_ms=case.get('delay_ms',0),capture_wire=True))
                client=[str(local),'-mode','client','-addr',f'{relay.address[0]}:{relay.address[1]}','-fec','on' if case.get('fec') else 'off','-n','3','-gap','10ms','-timeout','3s','-stats',str(out/(name+'.client.json'))]
                if token:client+=['-token-store']
                if resume:client+=['-resume']
                if case.get('fec'):client+=['-layout','v3','-lead','0','-m','2']
                completed=subprocess.run(client,capture_output=True,timeout=30)
                (out/(name+'.stdout')).write_bytes(completed.stdout);(out/(name+'.stderr')).write_bytes(completed.stderr)
                obs.save(out/(name+'.command.json'),dict(server=server_cmd,client=client,exit_code=completed.returncode))
                assert completed.returncode==0,(name,completed.stderr.decode())
                rows=[json.loads(line) for line in completed.stdout.splitlines()];assert len(rows)==3
                time.sleep(.15)
            finally:
                if relay:relay.close();obs.save(out/(name+'.relay.json'),relay.events)
                obs.stop(server)
        ports=list(dict.fromkeys(e['peer_port'] for e in relay.events if e['direction']=='c2s'))
        assert len(ports)==3 and all(r['ok'] for r in rows),(name,rows)
        details=[]
        for row,port in zip(rows,ports):
            i=row['i'];d=row['revisit'];expected_resume=resume and server_resume and i>0;expected_retry=verify and not(token and i>0)
            wire=[e for e in relay.events if e['direction']=='c2s' and e['peer_port']==port and e['initial'] and not e['parity']]
            token_len=initial_token_bytes(wire[0]);assert bool(token_len)==(token and i>0),(name,i,token_len)
            assert d['token_store']==token and d['resume']==resume and d['first_connection']==(i==0) and d['cache_scope']=='process'
            assert d['tls_observed'] and d['tls_did_resume']==expected_resume and not d['used_0rtt'],(name,i,d)
            assert d['retry_received']==int(expected_retry),(name,i,d)
            assert all(p['space']!='0RTT' for p in row['observation']['packets'])
            assert d['token']['gets']==int(token) and d['token']['hits']==int(token and i>0),(name,i,d)
            assert (d['token']['puts']>=1) if token else d['token']['puts']==0,(name,i,d)
            assert d['session']['hits']==int(expected_resume),(name,i,d)
            assert (d['session']['puts']>=1) if resume and server_resume else d['session']['puts']==0,(name,i,d)
            if token or resume:
                assert d['wait_completed'] and d['wait_elapsed_ns']>=d['wait_target_ns']>=max(d['wait_requested_ns'],d['wait_rtt_ns'],row['handshake_end_ns'])
            else:assert d['wait_elapsed_ns']==d['wait_target_ns']==0 and not d['wait_completed']
            details.append(dict(i=i,token_length=token_len,revisit=d,server_bytes=row['server_bytes'],handshake_end_ns=row['handshake_end_ns']))
        ss=json.loads(stats.read_text(encoding='utf-8'));expected_verified=3 if verify else 2 if token else 0
        assert ss['source_verify_enabled']==verify and ss['session_tickets_enabled']==server_resume
        assert ss['token_contexts']==ss['tls_accepted']==3 and ss['address_verified_contexts']==expected_verified,(name,ss)
        assert ss['tls_resumed']==(2 if resume and server_resume else 0),(name,ss)
        assert ss['source_verify_calls']>=sum(d['revisit']['retry_received'] for d in details)
        accepted=[c for c in ss['conns'].values() if c['tls_observed']]
        assert len(accepted)==3 and all(c['address_validation_observed'] for c in accepted),(name,ss)
        assert sum(c['address_verified_at_start'] for c in accepted)==expected_verified
        assert sum(c['tls_did_resume'] for c in accepted)==ss['tls_resumed']
        result=dict(name=name,connections=3,successes=3,server=dict(contexts=ss['token_contexts'],verified=ss['address_verified_contexts'],accepted=ss['tls_accepted'],resumed=ss['tls_resumed'],verify_calls=ss['source_verify_calls']),rows=details);results.append(result)
        obs.save(out/(name+'.inspection.json'),result)
    obs.save(out/'result.json',dict(status='PASS',plan=plan,results=results));print(json.dumps(dict(status='PASS',cases=len(CASES),connections=3*len(CASES))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--udp-path',choices=('basic','oob'),default='oob');p.add_argument('--binary',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--work',type=Path,required=True)
    g=p.add_mutually_exclusive_group(required=True);g.add_argument('--dry-run',action='store_true');g.add_argument('--smoke',action='store_true');run(p.parse_args())
