import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import time


def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+".py"))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


obs=load("observation_smoke");wirecheck=load("initial_inspect")
CASES=[dict(name=f"mlkem_pad{n}",group="X25519MLKEM768",padding=n,ips=1280) for n in (0,1,63,64,1280,2560,8192)]
CASES += [dict(name=f"mlkem_ips{n}",group="X25519MLKEM768",padding=0,ips=n) for n in (0,1200,1291,1341,1350,1452,1472)]
CASES += [dict(name=f"x25519_pad{n}",group="X25519",padding=n,ips=1280) for n in (0,1280,2560,8192)]
CASES.append(dict(name="mlkem_padding_omitted",group="X25519MLKEM768",padding=0,ips=1280,omit=True))


def run(args):
    binary,out,work=args.binary.resolve(),args.out.resolve(),args.work.resolve();assert work.is_relative_to(Path.home()/"quicbed_gen33")
    plan=dict(schema="t3-inflation-smoke/1",label="development",purpose="Authenticated ClientHello and Initial-size validation; no performance inference",udp_path=args.udp_path,cases=CASES,connections_per_case=3,binary=str(binary),binary_sha256=obs.sha(binary),script_sha256=obs.sha(__file__),relay_sha256=obs.sha(obs.__file__),inspector_sha256=obs.sha(wirecheck.__file__))
    if args.dry_run:
        obs.save(out.with_suffix(".plan.json"),plan);print(json.dumps(dict(status="PLAN",cases=len(CASES),connections=3*len(CASES))));return
    assert json.loads(out.with_suffix(".plan.json").read_text())==plan
    out.mkdir(parents=True,exist_ok=False);work.mkdir(parents=True,exist_ok=False)
    local=work/"qamp";shutil.copyfile(binary,local);local.chmod(0o700);assert obs.sha(local)==plan["binary_sha256"]
    results=[]
    for case in CASES:
        name=case["name"]
        with obs.bind() as temp:server_addr=temp.getsockname()
        stats,log=out/(name+".server.json"),out/(name+".server.stderr")
        server_cmd=[str(local),"-mode","server","-addr",f"{server_addr[0]}:{server_addr[1]}","-certsize","6000","-fec","off","-stats",str(stats),"-udp-path",args.udp_path]
        relay=None
        with log.open("xb") as stream:
            server=subprocess.Popen(server_cmd,stdout=stream,stderr=subprocess.STDOUT)
            try:
                obs.wait_ready(server,log);relay=obs.Relay(server_addr,dict(delay_ms=0,capture_wire=True))
                client=[str(local),"-mode","client","-addr",f"{relay.address[0]}:{relay.address[1]}","-fec","buf","-group",case["group"],"-ips",str(case["ips"]),"-n","3","-gap","10ms","-timeout","3s","-stats",str(out/(name+".client.json"))]
                if not case.get("omit"):client += ["-k-inflate",str(case["padding"])]
                completed=subprocess.run(client,capture_output=True,timeout=30)
                (out/(name+".stdout")).write_bytes(completed.stdout);(out/(name+".stderr")).write_bytes(completed.stderr)
                obs.save(out/(name+".command.json"),dict(server=server_cmd,client=client,exit_code=completed.returncode))
                assert completed.returncode==0,(name,completed.stderr.decode())
                rows=[json.loads(line) for line in completed.stdout.splitlines()];assert len(rows)==3
                time.sleep(1.1)
            finally:
                if relay:relay.close();obs.save(out/(name+".relay.json"),relay.events)
                obs.stop(server)
        ports=list(dict.fromkeys(e["peer_port"] for e in relay.events if e["direction"]=="c2s"))
        assert len(ports)==3 and all(r["ok"] for r in rows),(name,rows)
        details=[]
        for row,port in zip(rows,ports):
            wire=[e for e in relay.events if e["direction"]=="c2s" and e["peer_port"]==port and e["initial"]]
            inspected=wirecheck.inspect(wire,row["observation"])
            h=row["client_hello_padding"];n=case["padding"]
            assert h["bytes"]==n and inspected["padding_bytes"]==n and inspected["padding_present"]==bool(n) and inspected["padding_zero"]
            assert h["parameter_id"]==(9730 if n else 0) and h["encoded_bytes"]==(n+3+(n>=64) if n else 0)
            eff=min(1452,max(1200,case["ips"])) if case["ips"] else 1280
            assert row["ips_used"]==case["ips"] and row["ips_eff"]==eff
            firstk=row["first_flight_datagrams"]
            assert firstk>0 and row["first_flight_bytes"]==firstk*eff and all(e["bytes"]==eff for e in wire[:firstk])
            assert row["extra_sent"]["sent"]==row["parity_sent"]==row["bytes_parity"]==0
            if n>=1280:assert inspected["crypto_packets"]>=(3 if case["group"]=="X25519MLKEM768" else 2)
            details.append(dict(i=row["i"],padding=h,ips_requested=case["ips"],ips_effective=eff,first_k=firstk,first_bytes=row["first_flight_bytes"],inspection=inspected))
        ss=json.loads(stats.read_text());assert ss["recovered"]==0
        result=dict(name=name,connections=3,successes=3,rows=details);results.append(result)
        obs.save(out/(name+".inspection.json"),result)
    obs.save(out/"result.json",dict(status="PASS",plan=plan,results=results))
    print(json.dumps(dict(status="PASS",cases=len(CASES),connections=3*len(CASES))))


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--udp-path",choices=("basic","oob"),default="oob");p.add_argument("--binary",type=Path,required=True);p.add_argument("--out",type=Path,required=True);p.add_argument("--work",type=Path,required=True)
    g=p.add_mutually_exclusive_group(required=True);g.add_argument("--dry-run",action="store_true");g.add_argument("--smoke",action="store_true");run(p.parse_args())
