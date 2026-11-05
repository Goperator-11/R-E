import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time

SIZES = (512, 513, 600, 1023, 1024, 1025, 2047, 2048, 2049, 2955, 4032, 5299, 6000, 6200, 7000, 7700, 8000, 9000, 10000, 12000, 14000, 16000, 18000, 32767, 32768, 65535, 65536, 1048576)
NETWORK_SIZES = (2955, 6000, 16000)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def save(path, obj):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(obj, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def run(args):
    out, work = args.out.resolve(), args.work.resolve()
    if not work.is_relative_to(Path.home() / "quicbed_gen33"):
        raise ValueError("work must be inside ~/quicbed_gen33")
    binary = args.binary.resolve()
    baseline = args.baseline.resolve()
    plan = dict(schema="t1-functional-certificate-smoke/1", label="development", purpose="Functional identity and handshake checks; no performance inference", exact_sizes=list(SIZES), network_sizes=list(NETWORK_SIZES), servers_per_size=3, connections_per_server=3, binary=str(binary), binary_sha256=sha(binary), baseline=str(baseline), baseline_sha256=sha(baseline), script_sha256=sha(__file__))
    if args.dry_run:
        save(out.with_suffix(".plan.json"), plan)
        print(json.dumps(plan))
        return
    fixed = json.loads(out.with_suffix(".plan.json").read_text(encoding="utf-8"))
    if plan != fixed:
        raise ValueError("smoke inputs differ from dry-run plan")
    out.mkdir(parents=True, exist_ok=False)
    work.mkdir(parents=True, exist_ok=False)
    local_binary = work / "qamp"
    shutil.copyfile(binary, local_binary)
    local_binary.chmod(0o700)
    assert sha(local_binary) == plan["binary_sha256"]
    receipts = []

    def command(label, argv, expected=0):
        completed = subprocess.run([str(local_binary)] + argv, capture_output=True, timeout=20)
        (out / (label + ".stdout")).write_bytes(completed.stdout)
        (out / (label + ".stderr")).write_bytes(completed.stderr)
        receipt = dict(label=label, argv=argv, exit_code=completed.returncode, stdout_sha256=hashlib.sha256(completed.stdout).hexdigest(), stderr_sha256=hashlib.sha256(completed.stderr).hexdigest())
        receipts.append(receipt)
        assert completed.returncode == expected, receipt
        return completed.stdout

    certificates = {}
    for size in SIZES:
        paths = [work / f"certificate_{size}_{copy}.pem" for copy in range(2)]
        preview = json.loads(command(f"preview_{size}", ["-mode", "certgen", "-certsize", str(size), "-cert-file", str(paths[0]), "-dry-run"]))
        assert not paths[0].exists()
        metas = [json.loads(command(f"generate_{size}_{copy}", ["-mode", "certgen", "-certsize", str(size), "-cert-file", str(path)])) for copy,path in enumerate(paths)]
        assert paths[0].read_bytes() == paths[1].read_bytes()
        for meta in (preview, *metas):
            assert meta["der_bytes"] == size and meta["file_sha256"] == sha(paths[0])
            assert meta["der_sha256"] == metas[0]["der_sha256"]
        shutil.copyfile(paths[0], out / paths[0].name)
        certificates[size] = dict(meta=metas[0], path=str(paths[0]))
    existing = Path(certificates[6000]["path"])
    before = sha(existing)
    command("existing_file", ["-mode", "certgen", "-certsize", "6000", "-cert-file", str(existing)], expected=2)
    assert sha(existing) == before
    for label,path,size in (("missing_file",work / "absent.pem",6000),("wrong_size",existing,6001)):
        command(label,["-mode","server","-certsize",str(size),"-cert-file",str(path),"-addr",f"127.0.0.1:{port()}"],expected=2)
    legacy, servers = [], []
    for size in NETWORK_SIZES:
        for index in range(2):
            label = f"baseline_{size}_{index}"
            log = out / (label + ".stderr")
            with log.open("xb") as stream:
                process = subprocess.Popen([str(baseline),"-mode","server","-certsize",str(size),"-addr",f"127.0.0.1:{port()}","-fec","off"],stdout=stream,stderr=subprocess.STDOUT)
                try:
                    wait_ready(process,log)
                    text = log.read_text(encoding="utf-8")
                    actual = int(re.search(r"cert DER = (\d+) bytes",text).group(1))
                    legacy.append(dict(target=size,actual=actual,exact=actual==size,log=log.name))
                finally:
                    stop(process)
        for index,mode in enumerate(("off","buf","on")):
            label = f"server_{size}_{index}"
            log,stats = out/(label+".stderr"),out/(label+".stats.json")
            address = f"127.0.0.1:{port()}"
            argv = [str(local_binary),"-mode","server","-certsize",str(size),"-cert-file",certificates[size]["path"],"-addr",address,"-fec",mode,"-stats",str(stats)]
            with log.open("xb") as stream:
                process = subprocess.Popen(argv,stdout=stream,stderr=subprocess.STDOUT)
                try:
                    wait_ready(process,log)
                    raw = command(label+"_client",["-mode","client","-addr",address,"-fec","off","-n","3","-timeout","3s","-gap","0s"])
                    rows = [json.loads(line) for line in raw.splitlines()]
                    assert len(rows)==3 and all(row["ok"] for row in rows)
                finally:
                    stop(process)
            saved = json.loads(stats.read_text(encoding="utf-8"))
            logged = [json.loads(line.removeprefix("CERT_META ")) for line in log.read_text(encoding="utf-8").splitlines() if line.startswith("CERT_META ")]
            assert len(logged)==1 and saved["certificate"]==logged[0]
            actual = saved["certificate"]
            expected = certificates[size]["meta"]
            assert actual["source"]=="file" and actual["der_bytes"]==size
            for field in ("der_sha256","file_sha256","key_type"):
                assert actual[field]==expected[field]
            servers.append(dict(target=size,mode=mode,connections=3,certificate=actual,stats_sha256=sha(stats),log_sha256=sha(log)))
    assert sha(binary)==plan["binary_sha256"] and sha(baseline)==plan["baseline_sha256"]
    result = dict(status="PASS",label="development",ended_utc=dt.datetime.now(dt.timezone.utc).isoformat(),plan=plan,exact_size_cases=len(certificates),independent_generations=len(certificates)*2,legacy=legacy,servers=servers,successful_handshakes=sum(s["connections"] for s in servers),receipts=receipts,scope="Functional checks only. No HCT, byte-efficiency, packet-boundary, or between-arm effect estimate.")
    save(out/"result.json",result)
    print(json.dumps({k:result[k] for k in ("status","exact_size_cases","independent_generations","successful_handshakes")}))


def wait_ready(process, log):
    deadline = time.monotonic()+5
    while time.monotonic()<deadline:
        if process.poll() is not None:
            raise RuntimeError("server exited before READY: "+log.read_text(encoding="utf-8"))
        if "READY " in log.read_text(encoding="utf-8"):
            return
        time.sleep(0.02)
    raise TimeoutError("server did not become ready")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary",type=Path,required=True)
    parser.add_argument("--baseline",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--work",type=Path,required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run",action="store_true")
    group.add_argument("--smoke",action="store_true")
    run(parser.parse_args())
