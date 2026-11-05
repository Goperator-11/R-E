import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import time

spec=importlib.util.spec_from_file_location("observation_smoke",Path(__file__).with_name("observation_smoke.py"))
obs=importlib.util.module_from_spec(spec)
spec.loader.exec_module(obs)
CASES=[dict(name=f"{kind}_{server}_{drop}",kind=kind,server=server,drop=drop,delay_ms=0,capture_wire=True) for server in ("on","off") for kind in ("parity","pad_junk","dup") for drop in ("none","0")]
CASES.append(dict(name="corrupt_tail_on_none",kind="corrupt_tail",server="on",drop="none",delay_ms=0,capture_wire=True))


def junk_info(data):
    if len(data)<23 or data[:5]!=bytes((0xc3,0,0,0,1)):return None
    i=6+data[5]
    if i>=len(data):return None
    i+=1+data[i]+3
    if data[i:i+4]!=b"JUNK":return None
    return obs.parity_info(data[:i]+b"PFEC"+data[i+4:])


def run(args):
    binary,out,work=args.binary.resolve(),args.out.resolve(),args.work.resolve()
    assert work.is_relative_to(Path.home()/"quicbed_gen33")
    plan=dict(schema="t3-comparison-smoke/1",label="development",purpose="Functional comparison-arm validation; no performance inference",udp_path=args.udp_path,cases=CASES,connections_per_case=3,binary=str(binary),binary_sha256=obs.sha(binary),script_sha256=obs.sha(__file__),relay_sha256=obs.sha(obs.__file__))
    if args.dry_run:
        obs.save(out.with_suffix(".plan.json"),plan)
        print(json.dumps(dict(status="PLAN",cases=len(CASES),connections=3*len(CASES))))
        return
    assert json.loads(out.with_suffix(".plan.json").read_text())==plan
    out.mkdir(parents=True,exist_ok=False);work.mkdir(parents=True,exist_ok=False)
    local=work/"qamp";shutil.copyfile(binary,local);local.chmod(0o700)
    assert obs.sha(local)==plan["binary_sha256"]
    results=[]
    for case in CASES:
        name=case["name"]
        with obs.bind() as temp:server_addr=temp.getsockname()
        stats,log=out/(name+".server.json"),out/(name+".server.stderr")
        server_cmd=[str(local),"-mode","server","-addr",f"{server_addr[0]}:{server_addr[1]}","-certsize","6000","-fec",case["server"],"-stats",str(stats),"-udp-path",args.udp_path]
        relay=None
        with log.open("xb") as stream:
            server=subprocess.Popen(server_cmd,stdout=stream,stderr=subprocess.STDOUT)
            try:
                obs.wait_ready(server,log);relay=obs.Relay(server_addr,case)
                client=[str(local),"-mode","client","-addr",f"{relay.address[0]}:{relay.address[1]}","-fec","on","-layout","v3","-m","4","-lead","3","-expect-k","2","-n","3","-gap","10ms","-timeout","3s","-stats",str(out/(name+".client.json"))]
                if case["kind"] in ("pad_junk","dup"):client.append("-"+case["kind"].replace("_","-"))
                if case["kind"]=="corrupt_tail":client += ["-corrupt-parity","3"]
                if case["drop"]!="none":client += ["-drop-initial",case["drop"]]
                completed=subprocess.run(client,capture_output=True,timeout=30)
                (out/(name+".stdout")).write_bytes(completed.stdout);(out/(name+".stderr")).write_bytes(completed.stderr)
                obs.save(out/(name+".command.json"),dict(server=server_cmd,client=client,exit_code=completed.returncode))
                assert completed.returncode==0,(name,completed.stderr.decode())
                rows=[json.loads(line) for line in completed.stdout.splitlines()];assert len(rows)==3
                time.sleep(1.1)
            finally:
                if relay:relay.close();obs.save(out/(name+".relay.json"),relay.events)
                obs.stop(server)
        ss=json.loads(stats.read_text());ports=list(dict.fromkeys(e["peer_port"] for e in relay.events if e["direction"]=="c2s"))
        assert len(ports)==3 and all(row["ok"] for row in rows),(name,rows)
        details=[]
        for row,port in zip(rows,ports):
            extra=row["extra_sent"];records=row["flight_trace"]["records"]
            kind="parity" if case["kind"]=="corrupt_tail" else case["kind"]
            assert extra["kind"]==kind and extra["first_sent"]==4 and extra["first_lead"]==3
            assert row["first_flight_datagrams"]==2
            assert extra["sent"]==sum(r["extra_sent"]["sent"] for r in records)
            assert extra["bytes"]==sum(r["extra_sent"]["bytes"] for r in records)
            wire=[e for e in relay.events if e["direction"]=="c2s" and e["peer_port"]==port and e["initial"]]
            actual_count=sum(r["flush_tx_dgrams"]+(r["actual_k"] if r["original_immediate"] else 0) for r in records)
            actual_bytes=sum(r["flush_tx_bytes"]+(r["original_bytes"] if r["original_immediate"] else 0) for r in records)
            assert (actual_count,actual_bytes)==(len(wire),sum(e["bytes"] for e in wire)),(name,actual_count,len(wire))
            first_count=6-(case["drop"]!="none");first=[bytes.fromhex(e["wire_hex"]) for e in wire[:first_count]]
            if kind=="pad_junk":
                assert row["parity_sent"]==row["bytes_parity"]==0
                pads=[junk_info(d) for d in first]
                expected=[0,1,2]+[None]*(first_count-4)+[3]
                assert [(x["index"] if x else None) for x in pads]==expected
                assert extra["bytes"]==extra["parity_budget_bytes"] and extra["first_bytes"]==extra["first_parity_budget_bytes"]
            elif kind=="dup":
                assert row["parity_sent"]==row["bytes_parity"]==0
                assert first[0]==first[2] and first[1]==first[-1]
                if case["drop"]=="none":assert first[0]==first[3] and first[1]==first[4]
                else:assert first[1]==first[3]
                assert extra["bytes"]<extra["parity_budget_bytes"] and extra["first_bytes"]<extra["first_parity_budget_bytes"]
            else:
                assert extra["sent"]==row["parity_sent"] and extra["bytes"]==row["bytes_parity"]
                assert [obs.parity_info(d)["index"] if obs.parity_info(d) else None for d in first]==[0,1,2]+[None]*(first_count-4)+[3]
            assert row["arrivals"]["src"]=="none"
            details.append(dict(i=row["i"],extra=extra,first_original_bytes=row["first_flight_bytes"],wire_initial_count=len(wire),wire_initial_bytes=actual_bytes,pto_count=row["observation"]["pto_count"]))
        if case["kind"] in ("pad_junk","dup") or case["server"]=="off":assert ss["recovered"]==0,(name,ss)
        if case["kind"] in ("pad_junk","dup"):assert ss["credit_parities"]==0,(name,ss)
        if case["kind"]=="parity" and case["server"]=="on" and case["drop"]=="0":assert ss["recovered"]>=3
        if case["kind"]=="dup" and case["drop"]=="0":assert all(x["pto_count"]==0 for x in details),(name,details)
        assert ss["bytes_to_stack"]<=ss["bytes_in"]
        results.append(dict(name=name,connections=3,successes=3,recovered=ss["recovered"],credit_parities=ss["credit_parities"],bytes_in=ss["bytes_in"],bytes_to_stack=ss["bytes_to_stack"],rows=details))
    result=dict(status="PASS",plan=plan,results=results)
    obs.save(out/"result.json",result)
    print(json.dumps(dict(status="PASS",cases=len(CASES),connections=3*len(CASES))))


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--udp-path",choices=("basic","oob"),default="oob")
    p.add_argument("--binary",type=Path,required=True);p.add_argument("--out",type=Path,required=True);p.add_argument("--work",type=Path,required=True)
    g=p.add_mutually_exclusive_group(required=True);g.add_argument("--dry-run",action="store_true");g.add_argument("--smoke",action="store_true")
    run(p.parse_args())
