import argparse
import datetime as dt
import hashlib
import heapq
import json
from pathlib import Path
import select
import shutil
import socket
import subprocess
import threading
import time
import zlib


CASES = (
    dict(name="off_c1", mode="off", delay_ms=0, c1=True),
    dict(name="off_none", mode="off", delay_ms=0, c1=False),
    dict(name="off_rtt200", mode="off", delay_ms=100, c1=True),
    dict(name="fec_one", mode="on", delay_ms=0, c1=True, drop="0", m=1),
    dict(name="fec_two", mode="on", delay_ms=0, c1=True, drop="0,1", m=3),
    dict(name="fec_rtt200", mode="on", delay_ms=100, c1=True, drop="0", m=1),
    dict(name="hold_one", mode="on", delay_ms=0, c1=True, drop="0", m=1, hold=True),
    dict(name="auto3_c1", mode="auto3", delay_ms=0, c1=True),
    dict(name="auto3_explicit_timer", mode="auto3", delay_ms=0, c1=True, expect_k=0),
    dict(name="auto3_explicit_k", mode="auto3", delay_ms=0, c1=True, expect_k=2),
    dict(name="auto3_rtt200", mode="auto3", delay_ms=100, c1=True),
    dict(name="feedback_loss", mode="auto3", delay_ms=0, c1=True, lose_feedback=True),
    dict(name="v3_probe_original_first", mode="on", delay_ms=100, c1=True, layout="v3", lead=3, m=4, expect_k=2, retrans_layout="original_first"),
    dict(name="v3_probe_repeat_first", mode="on", delay_ms=100, c1=True, layout="v3", lead=3, m=4, expect_k=2, retrans_layout="repeat_first"),
    dict(name="all_c2s_loss", mode="auto3", delay_ms=0, c1=True, lose_c2s=True),
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, obj):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(obj, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def crc32c(data):
    value = 0xFFFFFFFF
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0x82F63B78 if value & 1 else 0)
    return value ^ 0xFFFFFFFF


def parity_info(data):
    if len(data)<23 or data[:5]!=bytes((0xC3,0,0,0,1)):
        return None
    i=6+data[5]
    if i>=len(data): return None
    i+=1+data[i]
    if i+3>len(data) or data[i]!=0 or data[i+1]&0xC0!=0x40: return None
    length=((data[i+1]&0x3F)<<8)|data[i+2]
    body=data[i+3:]
    if len(body)!=length or len(body)<12 or body[:4]!=b"PFEC" or body[4] not in (1,3): return None
    m=body[8]&15 if body[4]==3 else body[8]
    lead=body[8]>>4 if body[4]==3 else int(m>=2)
    k=body[7]
    size=int.from_bytes(body[10:12],"big")
    if not 1<=k<=32 or not 0<=lead<=m or not 0<=body[9]<m or len(body)!=12+6*k+size: return None
    return dict(version=body[4],flight=int.from_bytes(body[5:7],"big"),k=k,m=m,lead=lead,index=body[9])


def bind():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    return sock


class Relay:
    def __init__(self, server, case):
        self.server, self.case = server, case
        self.sock = bind()
        self.address = self.sock.getsockname()
        self.links, self.peers, self.queue, self.events = {}, {}, [], []
        self.closed = threading.Event()
        self.started = time.monotonic_ns()
        self.error = None
        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def run(self):
        try:
            while not self.closed.is_set():
                now = time.monotonic()
                while self.queue and self.queue[0][0] <= now:
                    _, _, sock, dest, data = heapq.heappop(self.queue)
                    sock.sendto(data, dest)
                timeout = min(0.01, max(0, self.queue[0][0] - now)) if self.queue else 0.01
                ready, _, _ = select.select([self.sock] + list(self.peers), [], [], timeout)
                for sock in ready:
                    data, source = sock.recvfrom(65535)
                    if sock is self.sock:
                        if source not in self.links:
                            upstream = bind()
                            self.links[source] = upstream
                            self.peers[upstream] = source
                        send, dest, direction = self.links[source], self.server, "c2s"
                    else:
                        send, dest, direction = self.sock, self.peers[sock], "s2c"
                    feedback = b"PFBK" in data
                    dropped = (direction == "c2s" and self.case.get("lose_c2s", False)) or (direction == "s2c" and feedback and self.case.get("lose_feedback", False))
                    self.events.append(dict(at_ns=time.monotonic_ns()-self.started, direction=direction, bytes=len(data), crc32=zlib.crc32(data), crc32c=crc32c(data), feedback=feedback, wire_hex=data.hex() if self.case.get("capture_wire") and direction=="c2s" else None, parity=parity_info(data), initial=bool(len(data)>=5 and data[0]&0xC0==0xC0 and (data[0]>>4)&3==0 and data[1:5]==bytes((0,0,0,1))), dropped=dropped, peer_port=(source if direction=="c2s" else dest)[1]))
                    if not dropped:
                        heapq.heappush(self.queue, (time.monotonic()+self.case["delay_ms"]/1000, len(self.events), send, dest, data))
        except BaseException as exc:
            self.error = repr(exc)

    def close(self):
        self.closed.set()
        self.thread.join(timeout=2)
        assert not self.thread.is_alive()
        for sock in [self.sock] + list(self.peers):
            sock.close()
        assert self.error is None, self.error


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def wait_ready(process, log):
    deadline = time.monotonic()+5
    while time.monotonic()<deadline:
        assert process.poll() is None, log.read_text()
        if "READY " in log.read_text():
            return
        time.sleep(0.02)
    raise TimeoutError(str(log))


def run(args):
    binary, out, work = args.binary.resolve(), args.out.resolve(), args.work.resolve()
    assert work.is_relative_to(Path.home()/"quicbed_gen33")
    plan = dict(schema="t4-observation-smoke/1", label="development", purpose="Functional trace validation; no performance inference", udp_path=args.udp_path, cases=list(CASES), connections_per_case=3, cert_size=6000, binary=str(binary), binary_sha256=sha(binary), script_sha256=sha(__file__))
    if args.dry_run:
        save(out.with_suffix(".plan.json"), plan)
        print(json.dumps(dict(status="PLAN", cases=len(CASES), connections=3*len(CASES))))
        return
    assert json.loads(out.with_suffix(".plan.json").read_text())==plan
    out.mkdir(parents=True, exist_ok=False)
    work.mkdir(parents=True, exist_ok=False)
    local = work/"qamp"
    shutil.copyfile(binary, local)
    local.chmod(0o700)
    assert sha(local)==plan["binary_sha256"]
    results=[]
    for case in CASES:
        name=case["name"]
        with bind() as temporary:
            server_addr=temporary.getsockname()
        stats, log=out/(name+".server.json"),out/(name+".server.stderr")
        cmd=[str(local),"-mode","server","-addr",f"{server_addr[0]}:{server_addr[1]}","-certsize","6000","-fec","on","-stats",str(stats),"-udp-path",args.udp_path]
        if case["c1"]: cmd.append("-feedback")
        if case.get("hold"): cmd.append("-lead-hold")
        relay=None
        with log.open("xb") as stream:
            server=subprocess.Popen(cmd,stdout=stream,stderr=subprocess.STDOUT)
            try:
                wait_ready(server,log)
                relay=Relay(server_addr,case)
                client=[str(local),"-mode","client","-addr",f"{relay.address[0]}:{relay.address[1]}","-fec",case["mode"],"-n","3","-gap","10ms","-timeout","350ms" if case.get("lose_c2s") else "3s","-uplink-mbps","0","-cache",str(work/(name+".cache.json")),"-stats",str(out/(name+".client.json"))]
                if case["c1"]: client.append("-feedback")
                if case["mode"]=="auto3": client += ["-cache3",str(work/(name+".cache3.json"))]
                if "expect_k" in case: client += ["-expect-k",str(case["expect_k"])]
                if case.get("drop"): client += ["-drop-initial",case["drop"],"-m",str(case["m"]),"-expect-k","2"]
                if case.get("hold"): client += ["-layout","v3","-lead","0"]
                if "layout" in case: client += ["-layout",case["layout"],"-lead",str(case["lead"]),"-m",str(case["m"])]
                if "retrans_layout" in case: client += ["-retrans-layout",case["retrans_layout"]]
                completed=subprocess.run(client,capture_output=True,timeout=30)
                (out/(name+".stdout")).write_bytes(completed.stdout)
                (out/(name+".stderr")).write_bytes(completed.stderr)
                save(out/(name+".command.json"),dict(server=cmd,client=client,exit_code=completed.returncode))
                assert completed.returncode==0,(name,completed.stderr.decode())
                rows=[json.loads(line) for line in completed.stdout.splitlines()]
                assert len(rows)==3
                time.sleep(1.1)
            finally:
                if relay:
                    relay.close()
                    save(out/(name+".relay.json"),relay.events)
                stop(server)
        server_stats=json.loads(stats.read_text())
        assert server_stats["udp_path"] == ("basic" if args.udp_path == "basic" else "oob_readmsg_batch1")
        if args.udp_path == "oob" and not case.get("lose_c2s"):
            assert server_stats["udp_read_msg"]>0 and server_stats["udp_read_batch"]>0 and server_stats["udp_write_msg"]>0
        if args.udp_path == "basic":
            assert server_stats["udp_read_msg"]==server_stats["udp_read_batch"]==server_stats["udp_write_msg"]==0
        ports=list(dict.fromkeys(e["peer_port"] for e in relay.events if e["direction"]=="c2s"))
        assert len(ports)==len(rows),(name,ports)
        for row,port in zip(rows,ports):
            trace=row["flight_trace"]
            records=trace["records"]
            assert trace["omitted"]==0 and all(f["complete"] for f in records),(name,trace)
            assert trace["flushed_originals"]+trace["discarded_originals"]==row["initial_datagrams"]
            assert sum(f["actual_k"] for f in records if f["flushed"])==trace["flushed_originals"]
            assert sum(f["original_bytes"] for f in records if f["flushed"])==trace["flushed_bytes"]
            assert sum(f["actual_k"] for f in records if not f["flushed"])==trace["discarded_originals"]
            first=next(f for f in records if f["flushed"])
            assert (first["actual_k"],first["original_bytes"])==(row["first_flight_datagrams"],row["first_flight_bytes"])
            for i,f in enumerate(records):
                assert f["sequence"]==i+1 and 0<=f["first_input_ms"]<=f["last_input_ms"]<=f["flush_ms"]<=f["end_ms"]
                assert f["k_mismatch"]==(f["expected_k"]>0 and f["actual_k"]!=f["expected_k"])
                assert f["split_suspected"]==(f["expected_k"]>0 and f["actual_k"]<f["expected_k"])
                if f["original_immediate"] or not f["flushed"]:
                    assert f["buffered_first_wait_ms"]==f["buffered_last_wait_ms"]==0
                else:
                    assert abs(f["buffered_first_wait_ms"]-(f["flush_ms"]-f["first_input_ms"]))<1e-6
                    assert abs(f["buffered_last_wait_ms"]-(f["flush_ms"]-f["last_input_ms"]))<1e-6
                assert f["flush_tx_errors"]==0
                if f["reason"]=="timer": assert f["flush_ms"]-f["last_input_ms"]>=0.3-1e-6
            wire=[e for e in relay.events if e["direction"]=="c2s" and e["peer_port"]==port and e["initial"]]
            sent_n=sum(f["flush_tx_dgrams"]+(f["actual_k"] if f["original_immediate"] else 0) for f in records)
            sent_bytes=sum(f["flush_tx_bytes"]+(f["original_bytes"] if f["original_immediate"] else 0) for f in records)
            assert (sent_n,sent_bytes)==(len(wire),sum(e["bytes"] for e in wire)),(name,row["i"],sent_n,sent_bytes,wire)
            parity_wire=[e for e in wire if e["parity"] is not None]
            assert sum(e["bytes"] for e in parity_wire)==row["bytes_parity"]
            assert len(parity_wire)==row["parity_sent"]==sum(f["parity_sent"] for f in records)
            assert row["bytes_parity"]==sum(f["parity_bytes"] for f in records)
            for f in records:
                shape=f["shape"]
                par=[e for e in parity_wire if e["parity"]["flight"]==f["id"]]
                assert len(par)==f["parity_sent"] and sum(e["bytes"] for e in par)==f["parity_bytes"]
                assert all(e["parity"]["k"]==f["actual_k"] and e["parity"]["lead"]==shape["lead"] and e["parity"]["m"]==shape["lead"]+shape["trail"] for e in par)
                assert shape["original_immediate"]==f["original_immediate"]
            if name.startswith("v3_probe_"):
                assert row["retrans_layout"]==case["retrans_layout"]
                assert row["initial_datagrams"]==5 and row["parity_sent"]==(6 if case["retrans_layout"]=="original_first" else 9)
                assert [f["shape"]["phase"] for f in records]==["first_bundle","pre_response_followup","post_response"]
                follow=records[1]
                assert follow["shape"]["rule"]==case["retrans_layout"] and follow["shape"]["pto_count_at_start"]>=1
                assert (follow["shape"]["lead"],follow["shape"]["trail"])==((0,1) if case["retrans_layout"]=="original_first" else (3,1))
            assert row["ok"]==not_lost(case)
            obs,arr,c1=row["observation"],row["arrivals"],row["c1"]
            assert obs["version"]==1 and not obs["truncated"] and obs["end_ns"]>=row["handshake_end_ns"]
            assert obs["pto_count"]==len(obs["pto_at_ns"])
            assert all(p["at_ns"]>=0 for p in obs["packets"])
            assert all(r["latest_ns"]>0 for r in obs["rtt_updates"])
            assert sum(p["bytes"] for p in obs["server_datagrams"] if not p["feedback"])==row["server_bytes"]
            assert all(any(e["direction"]=="s2c" and not e["dropped"] and e["bytes"]==p["bytes"] and e["crc32c"]==p["crc32c"] for e in relay.events) for p in obs["server_datagrams"])
            if case["c1"] and not case.get("lose_feedback") and not case.get("lose_c2s"):
                assert arr["src"]=="c1" and c1["version"]==3 and not arr["trunc"],(name,arr,c1)
                assert arr["lost"]==arr["bitmap"].count(0)
                assert arr["sent"]-arr["lost"]==c1["physical_original"]+c1["physical_parity"]
                if case.get("drop"):
                    assert arr["lost"]==len(case["drop"].split(",")),(name,arr)
                    assert c1["recovered_original"]==arr["lost"],(name,c1)
            else:
                assert arr==dict(src="none",sent=0,lost=0,bitmap=None,trunc=False),(name,arr)
            if case.get("lose_c2s"):
                assert obs["pto_count"]>=1 and not obs["rtt_updates"] and not row["path_rtt_valid"]
            if case["mode"]=="auto3":
                assert "obs_err" not in row
                hint=row["flight_expectation"]
                if "expect_k" in case:
                    k=case["expect_k"]
                    assert hint==dict(k=k,source="explicit" if k else "explicit_timer",scope="all_flights" if k else "timer_only"),(name,hint)
                elif row["k_hat"] is not None:
                    assert hint==dict(k=row["k_hat"],source="cached_k",scope="first_flight"),(name,hint,row["k_hat"])
                else:
                    assert hint==dict(k=0,source="timer_only",scope="timer_only"),(name,hint)
        if name in ("auto3_c1","auto3_rtt200"):
            assert sum(r["flight_expectation"]["source"]=="cached_k" for r in rows)==2,(name,rows)
        if case.get("drop"):
            assert server_stats["recovered"]>=3*len(case["drop"].split(","))
            assert server_stats["unrecoverable_final"]==0
        result=dict(name=name,connections=3,successes=sum(r["ok"] for r in rows),c1=sum(r["arrivals"]["src"]=="c1" for r in rows),rtt_valid=sum(r["path_rtt_valid"] for r in rows),rtt_update_rows=sum(bool(r["observation"]["rtt_updates"]) for r in rows),initial_ack_rows=sum(any(p["direction"]=="received" and p["space"]=="initial" and p["ack_ranges"] for p in r["observation"]["packets"]) for r in rows),pto_counts=[r["observation"]["pto_count"] for r in rows],server_unrecoverable_seen=server_stats["unrecoverable_seen"],server_unrecoverable_final=server_stats["unrecoverable_final"],server_flights_finalized=server_stats["flights_finalized"],stdout_sha256=sha(out/(name+".stdout")),server_stats_sha256=sha(stats),relay_sha256=sha(out/(name+".relay.json")))
        results.append(result)
        print(json.dumps(result),flush=True)
    assert sha(binary)==plan["binary_sha256"]
    save(out/"result.json",dict(status="PASS",label="development",plan=plan,results=results,ended_utc=dt.datetime.now(dt.timezone.utc).isoformat()))


def not_lost(case):
    return not case.get("lose_c2s",False)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--udp-path", choices=("basic","oob"), default="oob")
    parser.add_argument("--binary",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--work",type=Path,required=True)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run",action="store_true")
    group.add_argument("--smoke",action="store_true")
    run(parser.parse_args())
