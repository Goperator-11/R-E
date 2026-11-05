import sys
sys.dont_write_bytecode = True
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import select
import shutil
import socket
import subprocess
import threading
import time

source = Path(__file__).with_name("observation_smoke.py")
spec = importlib.util.spec_from_file_location("observation_smoke", source)
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)


def feedback(cid):
    body = b"PFBK" + bytes([3, 0, 0, 0, 0, 0, 0, 0, 0])
    return b"\xc3\x00\x00\x00\x01" + bytes([len(cid)]) + cid + b"\x04test\x00" + (0x4000 + len(body)).to_bytes(2, "big") + body


class BoundaryRelay:
    def __init__(self, server):
        self.server = server
        self.sock, self.foreign = common.bind(), common.bind()
        self.address = self.sock.getsockname()
        self.links, self.peers, self.events, self.injected = {}, {}, [], set()
        self.closed, self.error = threading.Event(), None
        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def run(self):
        try:
            while not self.closed.is_set():
                ready, _, _ = select.select([self.sock] + list(self.peers), [], [], 0.01)
                for sock in ready:
                    data, source_addr = sock.recvfrom(65535)
                    if sock is self.sock:
                        if source_addr not in self.links:
                            upstream = common.bind()
                            self.links[source_addr] = upstream
                            self.peers[upstream] = source_addr
                        if data[0] & 0xF0 == 0xC0:
                            pos = 6 + data[5]
                            cid = data[pos+1:pos+1+data[pos]]
                            key = (source_addr, cid)
                            if cid and key not in self.injected:
                                self.injected.add(key)
                                wrong = bytes([cid[0] ^ 1]) + cid[1:]
                                good_fb = feedback(cid)
                                bad_fb = feedback(wrong)
                                big = good_fb[:7+len(cid)] + bytes(1300-7-len(cid))
                                for origin, packet, reason in ((self.foreign, good_fb, "peer_feedback"), (self.foreign, big, "peer_bytes"), (self.sock, bad_fb, "cid_feedback")):
                                    origin.sendto(packet, source_addr)
                                    self.events.append(dict(direction="injected", reason=reason, cid=cid.hex(), bytes=len(packet), sha256=hashlib.sha256(packet).hexdigest()))
                        self.links[source_addr].sendto(data, self.server)
                        direction = "c2s"
                    else:
                        self.sock.sendto(data, self.peers[sock])
                        direction = "s2c"
                    self.events.append(dict(direction=direction, bytes=len(data), crc32c=common.crc32c(data), feedback=b"PFBK" in data))
        except BaseException as exc:
            self.error = repr(exc)

    def close(self):
        self.closed.set()
        self.thread.join(timeout=2)
        assert not self.thread.is_alive()
        for sock in [self.sock, self.foreign] + list(self.peers):
            sock.close()
        assert self.error is None, self.error


def run(args):
    binary, out, work = args.binary.resolve(), args.out.resolve(), args.work.resolve()
    assert work.is_relative_to(Path.home()/"quicbed_gen33")
    plan = dict(schema="t5-boundary-smoke/1", label="development", purpose="Functional validation only", connections=6, modes=["off", "on"], injections_per_connection=3, account_retention_seconds=10, binary_sha256=common.sha(binary), script_sha256=common.sha(__file__), helper_sha256=common.sha(source))
    if args.dry_run:
        common.save(out.with_suffix(".plan.json"), plan)
        print(json.dumps(dict(status="PLAN", connections=6)))
        return
    assert json.loads(out.with_suffix(".plan.json").read_text()) == plan
    out.mkdir(parents=True, exist_ok=False)
    work.mkdir(parents=True, exist_ok=False)
    local = work/"qamp"
    shutil.copyfile(binary, local)
    local.chmod(0o700)
    with common.bind() as sock:
        server_addr = sock.getsockname()
    stats, log = out/"server.json", out/"server.stderr"
    command = [str(local), "-mode", "server", "-addr", f"{server_addr[0]}:{server_addr[1]}", "-certsize", "6000", "-fec", "on", "-feedback", "-stats", str(stats)]
    rows = []
    relay = None
    with log.open("xb") as stream:
        server = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT)
        try:
            common.wait_ready(server, log)
            relay = BoundaryRelay(server_addr)
            for mode in plan["modes"]:
                cmd = [str(local), "-mode", "client", "-addr", f"{relay.address[0]}:{relay.address[1]}", "-fec", mode, "-n", "3", "-gap", "10ms", "-timeout", "3s", "-feedback", "-expect-k", "2", "-m", "1"]
                if mode == "on":
                    cmd += ["-drop-initial", "0"]
                completed = subprocess.run(cmd, capture_output=True, timeout=20)
                (out/(mode+".stdout")).write_bytes(completed.stdout)
                (out/(mode+".stderr")).write_bytes(completed.stderr)
                common.save(out/(mode+".command.json"), dict(command=cmd, exit_code=completed.returncode))
                assert completed.returncode == 0
                got = [json.loads(line) for line in completed.stdout.splitlines()]
                assert len(got) == 3
                for row in got:
                    assert row["ok"] and row["arrivals"]["src"] == "c1", row
                    assert row["rx_rejected_peer"] == 2 and row["rx_rejected_cid"] == 1, row
                    assert row["first_flight_non_initial_long"] == 0, row
                    assert row["server_bytes"] == sum(d["bytes"] for d in row["observation"]["server_datagrams"] if not d["feedback"])
                    assert all(any(e["direction"] == "s2c" and e["bytes"] == d["bytes"] and e["crc32c"] == d["crc32c"] for e in relay.events) for d in row["observation"]["server_datagrams"])
                rows.extend(got)
            snapshots = []
            poll_errors = []
            current = None
            deadline = time.monotonic() + 13
            while time.monotonic() < deadline:
                assert server.poll() is None, log.read_text()
                try:
                    current = json.loads(stats.read_text())
                except (FileNotFoundError, json.JSONDecodeError) as exc:
                    poll_errors.append(dict(at_ns=time.monotonic_ns(), error=type(exc).__name__))
                    time.sleep(0.1)
                    continue
                snapshots.append(dict(at_ns=time.monotonic_ns(), stats=current))
                if current["conn_acct_expired"] == 6:
                    break
                time.sleep(0.1)
            common.save(out/"account_snapshots.json", snapshots)
            common.save(out/"stats_poll_errors.json", poll_errors)
            assert current is not None, "no complete periodic statistics within 13 seconds"
            assert current["conn_acct_live"] == 0 and current["conn_acct_expired"] == 6 and current["conn_acct_completed"] == 6, current
            assert current["conn_acct_trace_unmapped"] == 0 and current["conn_acct_dropped"] == 0 and current["conn_acct_evicted_lru"] == 0, current
        finally:
            if relay:
                relay.close()
                common.save(out/"relay.json", relay.events)
            common.stop(server)
    assert len(relay.injected) == 6
    common.save(out/"result.json", dict(status="PASS", plan=plan, successful_connections=len(rows), rejected_peer=sum(r["rx_rejected_peer"] for r in rows), rejected_cid=sum(r["rx_rejected_cid"] for r in rows), accounts_completed=current["conn_acct_completed"], accounts_expired=current["conn_acct_expired"], files={p.name:common.sha(p) for p in out.iterdir() if p.is_file()}))
    print(json.dumps(dict(status="PASS", connections=6, rejected_peer=12, rejected_cid=6, accounts_completed=6, accounts_expired=6)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--smoke", action="store_true")
    run(parser.parse_args())
