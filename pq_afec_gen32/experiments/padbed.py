from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
import sys
import time
from _journal import save_result

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RESULTS = os.path.join(HERE, "results")
STATE = os.path.join(HERE, "state")
QBED = os.path.join(HERE, "quicbed")
HOME = os.path.expanduser("~")
BIN = os.path.join(HOME, "quicbed", "bin")

NS = "peer"
DEV_LOCAL, DEV_PEER = "v0", "v1"
TX_IP, RX_IP = "10.9.0.1", "10.9.0.2"
SERVER_PORT = 44433
QAMP = "/tmp/qamp"

def _cpu_list():
    try:
        cpus = sorted(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        cpus = list(range(os.cpu_count() or 1))
    if not cpus:
        raise RuntimeError("사용할 수 있는 CPU가 없다")
    return ",".join(str(cpu) for cpu in cpus[:4])


CPU_LIST = _cpu_list()
TASKSET = ["taskset", "-c", CPU_LIST] if shutil.which("taskset") else []
WORK = "/tmp/padfec"

LEGACY_DISABLED = ("Legacy live measurements are disabled in gen32; use the isolated "
                   "gen32 builder and a new measurement protocol.")


def refuse_legacy_live():
    raise RuntimeError(LEGACY_DISABLED)


def harden():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


def run(cmd, check=True):
    refuse_legacy_live()
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError("FAILED: %s | %s | %s" % (cmd, r.stdout, r.stderr))
    return r


def require_root():
    refuse_legacy_live()
    if os.geteuid() != 0:
        sys.stderr.write("네임스페이스가 필요하다: "
                         "unshare -r -m -n python3 ...\n")
        sys.exit(2)


def require_bin():
    refuse_legacy_live()
    src = os.path.join(BIN, "qamp")
    if os.path.exists(src):
        def digest(path):
            with open(path, "rb") as f:
                return hashlib.file_digest(f, "sha256").digest()
        stale = (not os.path.exists(QAMP)
                 or digest(src) != digest(QAMP))
        if stale:
            shutil.copy2(src, QAMP)
            os.chmod(QAMP, 0o755)
        if os.path.exists(src + ".srcsha"):
            shutil.copy2(src + ".srcsha", QAMP + ".srcsha")
        elif os.path.exists(QAMP + ".srcsha"):
            os.remove(QAMP + ".srcsha")
    if not os.path.exists(QAMP):
        sys.stderr.write("%s 가 없다: quicbed/build.sh 를 먼저 실행" % QAMP)
        sys.stderr.write(chr(10))
        sys.exit(2)
    return QAMP



def setup(mtu=1500):
    refuse_legacy_live()
    run("mount -t tmpfs none /run", check=False)
    os.makedirs("/run/netns", exist_ok=True)
    os.makedirs(WORK, exist_ok=True)
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
    verify_link(mtu)


def _mac(dev, ns=None):
    cmd = "ip link show %s" % dev
    if ns:
        cmd = "ip netns exec %s %s" % (ns, cmd)
    out = run(cmd).stdout
    for tok in out.split():
        if len(tok) == 17 and tok.count(":") == 5:
            return tok
    raise RuntimeError("MAC 을 못 읽었다: %s" % out)


def static_arp():
    ml = _mac(DEV_LOCAL)
    mp = _mac(DEV_PEER, NS)
    run("ip neigh replace %s lladdr %s dev %s nud permanent"
        % (RX_IP, mp, DEV_LOCAL))
    run("ip netns exec %s ip neigh replace %s lladdr %s dev %s nud permanent"
        % (NS, TX_IP, ml, DEV_PEER))


def verify_link(mtu):
    r = run("ip link show %s" % DEV_LOCAL)
    if ("mtu %d" % mtu) not in r.stdout:
        raise RuntimeError("%s MTU 가 %d 로 안 걸렸다: %s"
                           % (DEV_LOCAL, mtu, r.stdout))
    r = run("ip netns exec %s ip link show %s" % (NS, DEV_PEER))
    if ("mtu %d" % mtu) not in r.stdout:
        raise RuntimeError("%s MTU 가 %d 로 안 걸렸다" % (DEV_PEER, mtu))
    if DEV_PEER in run("ip link show").stdout:
        raise RuntimeError("%s 가 루트 네임스페이스에 남아 있다" % DEV_PEER)


def _netem_spec(one_way_ms, loss_pct, burst_len, rate_mbit=0.0):
    spec = "netem delay %.3fms" % one_way_ms
    if rate_mbit and rate_mbit > 0:
        spec += " rate %gmbit" % float(rate_mbit)
    if loss_pct and loss_pct > 0:
        if burst_len and burst_len > 1:
            r_ = 1.0 / float(burst_len)
            p_ = r_ * loss_pct / (100.0 - loss_pct)
            spec += " loss gemodel %.4f%% %.4f%%" % (p_ * 100.0, r_ * 100.0)
        else:
            spec += " loss %.4f%%" % loss_pct
    return spec


def set_netem(one_way_ms, loss_c2s=0.0, loss_s2c=0.0, burst_len=1.0,
              rate_up_mbit=0.0, rate_down_mbit=0.0):
    run("tc qdisc del dev %s root" % DEV_LOCAL, check=False)
    run("ip netns exec %s tc qdisc del dev %s root" % (NS, DEV_PEER),
        check=False)
    run("tc qdisc add dev %s root %s"
        % (DEV_LOCAL, _netem_spec(one_way_ms, loss_c2s, burst_len,
                                  rate_up_mbit)))
    run("ip netns exec %s tc qdisc add dev %s root %s"
        % (NS, DEV_PEER, _netem_spec(one_way_ms, loss_s2c, burst_len,
                                     rate_down_mbit)))


def start_server(certsize, fec="off", stats_path=None, extra=()):
    qamp = require_bin()
    if stats_path is None:
        stats_path = os.path.join(WORK, "srv_stats.json")
    try:
        os.unlink(stats_path)
    except OSError:
        pass
    cmd = ["ip", "netns", "exec", NS] + TASKSET + [qamp,
           "-mode", "server", "-addr", "%s:%d" % (RX_IP, SERVER_PORT),
           "-certsize", str(certsize), "-fec", fec, "-stats", stats_path]
    cmd += list(extra)
    err_path = os.path.join(WORK, "srv_stderr.txt")
    err_f = open(err_path, "wb")
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=err_f)
    err_f.close()
    deadline = time.monotonic() + 15
    ready = False
    while time.monotonic() < deadline:
        try:
            with open(err_path, "rb") as f:
                if b"READY" in f.read():
                    ready = True
                    break
        except OSError:
            pass
        if p.poll() is not None:
            break
        time.sleep(0.05)
    if not ready or p.poll() is not None:
        stop_server(p)
        with open(err_path, "rb") as f:
            diagnostic = f.read()[-1000:].decode("utf-8", "replace")
        raise RuntimeError("서버 준비 실패: %s" % diagnostic)
    return p, stats_path


def stop_server(p):
    if p is None:
        return
    try:
        p.terminate()
    except Exception:
        pass
    try:
        p.wait(timeout=3)
    except Exception:
        try:
            p.kill()
            p.wait(timeout=3)
        except Exception:
            pass


def run_client(group, n, fec="off", m=1, ips=0, gap_ms=25, timeout_s=12,
               stats_path=None, quiet=True, expect_k=0, dump=None,
               extra=(), warmup=0, uplink_mbps=0.0):
    if not isinstance(n, int) or n <= 0 or not 0 <= warmup < n:
        raise ValueError("n must be positive and 0 <= warmup < n")
    qamp = require_bin()
    if stats_path is None:
        stats_path = os.path.join(WORK, "cli_stats.json")
    try:
        os.unlink(stats_path)
    except OSError:
        pass
    cmd = ["timeout", str(int(timeout_s * n + 120))] + TASKSET + [qamp,
           "-mode", "client",
           "-addr", "%s:%d" % (RX_IP, SERVER_PORT),
           "-group", group, "-n", str(n),
           "-fec", fec, "-m", str(m),
           "-gap", "%dms" % int(gap_ms),
           "-timeout", "%ds" % int(timeout_s),
           "-stats", stats_path,
           "-uplink-mbps", ("%g" % float(uplink_mbps))]
    if ips:
        cmd += ["-ips", str(ips)]
    if expect_k:
        cmd += ["-expect-k", str(expect_k)]
    if dump:
        cmd += ["-dump-flight", dump]
    cmd += list(extra)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout_s * n + 180)
    except subprocess.TimeoutExpired:
        return [], {}, "timeout"
    rows = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    n_warm = 0
    if warmup > 0:
        n_warm = min(warmup, len(rows))
        rows = rows[n_warm:]
    stats = {}
    if os.path.exists(stats_path):
        try:
            stats = json.load(open(stats_path))
        except Exception:
            stats = {}
    stats["warmup_dropped"] = n_warm
    stats["cpu_list"] = CPU_LIST
    err = ""
    if r.returncode != 0:
        tail = (r.stderr or "")[-300:].strip().replace("\n", " | ")
        err = ("timeout(rc124)" if r.returncode == 124
               else "exit %d: %s" % (r.returncode, tail))
    elif len(rows) + n_warm != n:
        err = "rows %d != n %d" % (len(rows) + n_warm, n)
    return rows, stats, err


def read_server_stats(path):
    for _ in range(20):
        if os.path.exists(path):
            try:
                return json.load(open(path))
            except Exception:
                pass
        time.sleep(0.1)
    return {}


def pctl(vals, q):
    if not vals:
        return None
    s = sorted(vals)
    i = int(q * (len(s) - 1))
    return s[i]


def summarize(rows, rtt_ms=None):
    ok = [r["ms"] for r in rows if r.get("ok")]
    out = {
        "n": len(rows),
        "ok": len(ok),
        "fail": len(rows) - len(ok),
        "p50": pctl(ok, 0.50), "p90": pctl(ok, 0.90),
        "p95": pctl(ok, 0.95), "p99": pctl(ok, 0.99),
        "min": min(ok) if ok else None, "max": max(ok) if ok else None,
        "mean": (sum(ok) / len(ok)) if ok else None,
    }
    if rtt_ms:
        out["pto_rate"] = (sum(1 for t in ok if t > rtt_ms + 500.0)
                           / float(len(ok))) if ok else None
        out["two_rtt_rate"] = (sum(1 for t in ok if t > 1.5 * rtt_ms)
                               / float(len(ok))) if ok else None
        out["rtt_multiple"] = (out["p50"] / rtt_ms) if out["p50"] else None
    if rows:
        kems = set(r.get("kem_id") for r in rows if r.get("ok"))
        out["kem_ids"] = sorted(x for x in kems if x is not None)
        dg = [r.get("initial_datagrams") for r in rows
              if r.get("initial_datagrams")]
        out["initial_datagrams_median"] = pctl(dg, 0.5)
    return out


def measured_C(group):
    p = os.path.join(RESULTS, "p1_flight.json")
    if not os.path.exists(p):
        raise SystemExit(
            "measured_C: %s 가 없다. C 는 측정값이므로 지어낼 수 없다. "
            "먼저 p1 을 돌려라 (python experiments/loop2.py --only p1)."
            % p)
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    for c in d.get("capacity_checks", []):
        if c.get("group") == group and c.get("ips") == 0 \
                and isinstance(c.get("C"), int):
            return c["C"]
    raise SystemExit(
        "measured_C: p1_flight.json 에 그룹 %r 의 C 가 없다. "
        "있는 그룹: %s"
        % (group, [c.get("group") for c in d.get("capacity_checks", [])
                   if c.get("ips") == 0]))


def save(name, obj):
    return save_result(os.path.join(RESULTS, name), obj)
