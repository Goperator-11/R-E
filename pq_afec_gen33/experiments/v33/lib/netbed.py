from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
EXPERIMENTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(EXPERIMENTS))
import gate_v3_parity
from padbed import _cpu_list, _netem_spec

NS = "peer"
DEV_LOCAL, DEV_PEER = "v0", "v1"
TX_IP, RX_IP = "10.9.0.1", "10.9.0.2"
SERVER_PORT = 44433
NS_GET_USERNS = 0xB701


def _namespace_owner(name):
    import fcntl

    with open("/proc/self/ns/" + name, "rb") as namespace:
        owner = fcntl.ioctl(namespace.fileno(), NS_GET_USERNS)
    try:
        info = os.fstat(owner)
        return info.st_dev, info.st_ino
    finally:
        os.close(owner)


def require_root():
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        raise RuntimeError("unshare -Urnm 안의 root가 필요하다")
    try:
        mapping = Path("/proc/self/uid_map").read_text().split()
        if len(mapping) != 3 or mapping[0] != "0" or mapping[2] != "1":
            raise RuntimeError("단일 root 매핑의 user namespace가 필요하다")
        user = os.stat("/proc/self/ns/user")
        identity = (user.st_dev, user.st_ino)
        for name in ("mnt", "net"):
            if _namespace_owner(name) != identity:
                raise RuntimeError(name + " namespace가 현재 user namespace 소유가 아니다")
    except OSError as exc:
        raise RuntimeError("unshare -Urnm 격리를 확인하지 못했다: " + str(exc)) from exc


def run(cmd, check=True):
    require_root()
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                            encoding="utf-8", timeout=30)
    if check and result.returncode:
        raise RuntimeError("FAILED: %s | %s | %s" % (cmd, result.stdout, result.stderr))
    return result


def pin_cpus():
    require_root()
    cpus = {int(cpu) for cpu in _cpu_list().split(",")}
    os.sched_setaffinity(0, cpus)
    actual = os.sched_getaffinity(0)
    if actual != cpus:
        raise RuntimeError("CPU affinity가 요청한 CPU와 다르다")
    return sorted(actual)


def setup(mtu=1500):
    require_root()
    if isinstance(mtu, bool) or not isinstance(mtu, int) or not 1280 <= mtu <= 65535:
        raise ValueError("MTU는 1280~65535 정수여야 한다")
    cpus = pin_cpus()
    run("mount -t tmpfs none /run")
    os.makedirs("/run/netns", exist_ok=True)
    run("ip netns del %s" % NS, check=False)
    run("ip netns add %s" % NS)
    run("ip link add %s type veth peer name %s" % (DEV_LOCAL, DEV_PEER))
    run("ip link set %s netns %s" % (DEV_PEER, NS))
    run("ip addr add %s/24 dev %s" % (TX_IP, DEV_LOCAL))
    run("ip link set %s mtu %d" % (DEV_LOCAL, mtu))
    run("ip link set %s up" % DEV_LOCAL)
    run("ip link set lo up")
    run("ip netns exec %s ip addr add %s/24 dev %s" % (NS, RX_IP, DEV_PEER))
    run("ip netns exec %s ip link set %s mtu %d" % (NS, DEV_PEER, mtu))
    run("ip netns exec %s ip link set %s up" % (NS, DEV_PEER))
    run("ip netns exec %s ip link set lo up" % NS)
    static_arp()
    links = verify_link(mtu)
    return {"cpu_affinity": cpus, "mtu": mtu, "links": links}


def _mac(dev, ns=None):
    cmd = "ip link show %s" % dev
    if ns:
        cmd = "ip netns exec %s %s" % (ns, cmd)
    output = run(cmd).stdout
    match = re.search(r"\blink/ether\s+([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})\b", output)
    if match is None:
        raise RuntimeError("MAC을 읽지 못했다: " + output)
    return match.group(1)


def static_arp():
    local = _mac(DEV_LOCAL)
    peer = _mac(DEV_PEER, NS)
    run("ip neigh replace %s lladdr %s dev %s nud permanent" % (RX_IP, peer, DEV_LOCAL))
    run("ip netns exec %s ip neigh replace %s lladdr %s dev %s nud permanent"
        % (NS, TX_IP, local, DEV_PEER))


def verify_link(mtu):
    local = run("ip link show %s" % DEV_LOCAL).stdout
    peer = run("ip netns exec %s ip link show %s" % (NS, DEV_PEER)).stdout
    for dev, output in ((DEV_LOCAL, local), (DEV_PEER, peer)):
        if re.search(r"\bmtu %d\b" % mtu, output) is None:
            raise RuntimeError("%s MTU가 %d로 설정되지 않았다: %s" % (dev, mtu, output))
    if re.search(r"^\d+: %s(?:@|:)" % DEV_PEER, run("ip link show").stdout, re.M):
        raise RuntimeError("%s가 root namespace에 남아 있다" % DEV_PEER)
    return {"local": local, "peer": peer}


def set_netem(one_way_ms, loss_c2s=0.0, loss_s2c=0.0, burst_len=1.0,
              rate_up_mbit=0.0, rate_down_mbit=0.0, *, journal):
    require_root()
    if not callable(journal):
        raise TypeError("실제 tc 출력을 기록할 journal callback이 필요하다")
    values = [float(value) for value in (one_way_ms, loss_c2s, loss_s2c, burst_len,
                                         rate_up_mbit, rate_down_mbit)]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("netem 인자는 유한수여야 한다")
    delay, c2s, s2c, burst, up, down = values
    if min(delay, c2s, s2c, up, down) < 0 or max(c2s, s2c) > 100 or burst < 1:
        raise ValueError("netem 인자 범위 오류")
    if burst > 1 and any(loss * (1 + 1 / burst) > 100 for loss in (c2s, s2c)):
        raise ValueError("gemodel 전이 확률이 100%를 넘는다")
    run("tc qdisc del dev %s root" % DEV_LOCAL, check=False)
    run("ip netns exec %s tc qdisc del dev %s root" % (NS, DEV_PEER), check=False)
    run("tc qdisc add dev %s root %s" % (DEV_LOCAL, _netem_spec(delay, c2s, burst, up)))
    run("ip netns exec %s tc qdisc add dev %s root %s"
        % (NS, DEV_PEER, _netem_spec(delay, s2c, burst, down)))
    event = {"event": "netem", "requested": dict(zip(
        ("one_way_ms", "loss_c2s", "loss_s2c", "burst_len", "rate_up_mbit", "rate_down_mbit"),
        values)), "qdisc": {}}
    for direction, cmd in (
        ("c2s", "tc qdisc show dev %s" % DEV_LOCAL),
        ("s2c", "ip netns exec %s tc qdisc show dev %s" % (NS, DEV_PEER)),
    ):
        result = run(cmd)
        if not re.search(r"^qdisc netem .*\broot\b", result.stdout, re.M):
            raise RuntimeError("netem qdisc를 확인하지 못했다: " + result.stdout)
        event["qdisc"][direction] = {"command": cmd, "stdout": result.stdout,
                                      "stderr": result.stderr, "returncode": result.returncode}
    journal(event)
    return event


def require_bin(path):
    binary = Path(path).expanduser().resolve()
    report, problems = gate_v3_parity.binary_report(str(binary))
    if problems:
        raise RuntimeError("; ".join(problems))
    if not os.access(binary, os.X_OK):
        raise RuntimeError("바이너리 실행 권한이 없다: " + str(binary))
    return report


def selftest(binary):
    require_root()
    report = require_bin(binary)
    environment = setup()
    set_netem(25, loss_c2s=2, loss_s2c=2, rate_up_mbit=2, rate_down_mbit=2,
              journal=lambda event: print(json.dumps(event, ensure_ascii=False), flush=True))
    print(json.dumps({"selftest": "pass", "environment": environment,
                      "binary": report}, ensure_ascii=False), flush=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="gen33 격리 netem 환경 확인")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--bin", default=gate_v3_parity.BIN_DEFAULT)
    args = parser.parse_args(argv)
    if not args.selftest:
        parser.error("--selftest가 필요하다")
    try:
        return selftest(args.bin)
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
