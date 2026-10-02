from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import padbed as B
from _journal import runtime_context

WORK = "/tmp/padfec_g3"
BIN_ROOT = "/tmp/qamp_g3"
BINS = {"g2": BIN_ROOT + "/g2/qamp", "g3": BIN_ROOT + "/g3/qamp"}
PORTS = {"g2": 44433, "g3": 44434}
G2_FROZEN_SHA256 = "d98b05d73f44774ad622ab1c4993526cac58957b22310fc61122d7bd44964213"
G2_FROZEN_COPY = os.path.join(B.HOME, "quicbed", "bin", "qamp")
INSTALL_HINT = "bash experiments/quicbed/build_g3.sh (or --install-only after /tmp was cleared)"
QUICBED = os.path.join(HERE, "quicbed")
MEASURE_RE = re.compile(
    r"experiments/(p\d+\w*|e\d+\w*|_probe\w*|probe|fixloop|loop2|forever|"
    r"pipeline|gate_go_parity\w*|g3_\w+|p21_\w+)\.py")
LOAD_COMMS = ("go", "compile", "link", "asm", "cgo", "vet", "gcc", "cc1")
CONN_FIELDS = ("rx_dgrams", "rx_bytes", "rx_orig_bytes", "rx_parity_bytes",
               "rx_orig_n", "rx_parity_n", "recov_n", "credit_n", "stack_bytes",
               "tx_dgrams", "tx_bytes", "beff_stack", "beff_phys", "beff_orig",
               "beff_parity", "beff_credit", "first_rx_ns", "first_tx_ns",
               "peer_changes")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_or_none(path):
    try:
        return sha256_file(path)
    except OSError:
        return None


def _read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return None


def _read_bytes(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return b""


def binary_report():
    rep = {}
    problems = []
    for tag in ("g2", "g3"):
        path = BINS[tag]
        info = {"path": path, "port": PORTS[tag], "exists": os.path.isfile(path)}
        if info["exists"]:
            info["sha256"] = sha256_file(path)
            info["executable"] = os.access(path, os.X_OK)
            info["srcsha"] = _read_text(path + ".srcsha")
            info["sha256_file"] = (_read_text(path + ".sha256") or "").split(" ")[0] or None
            if not info["executable"]:
                problems.append("%s binary is not executable: %s" % (tag, path))
        else:
            problems.append("%s binary missing: %s (install with %s)"
                            % (tag, path, INSTALL_HINT))
        rep[tag] = info
    g2, g3 = rep["g2"], rep["g3"]
    if g2["exists"] and g2["sha256"] != G2_FROZEN_SHA256:
        problems.append("g2 binary sha256 %s is not the frozen %s"
                        % (g2["sha256"], G2_FROZEN_SHA256))
    if g3["exists"]:
        _sources, current = quicbed_sources()
        g3["source_fingerprint_now"] = current
        if g3["sha256"] == G2_FROZEN_SHA256:
            problems.append("g3 binary is byte-identical to the frozen gen-2 binary")
        if not g3["srcsha"]:
            problems.append("g3 binary has no qamp.srcsha next to it (install with %s)"
                            % INSTALL_HINT)
        elif g3["srcsha"] != current:
            problems.append("g3 binary was built from other sources: srcsha %s, "
                            "experiments/quicbed now %s (rebuild with %s)"
                            % (g3["srcsha"], current, INSTALL_HINT))
        if g3["sha256_file"] and g3["sha256_file"] != g3["sha256"]:
            problems.append("g3 binary does not match its qamp.sha256")
    rep["frozen_g2_sha256"] = G2_FROZEN_SHA256
    rep["frozen_g2_build_copy_sha256"] = sha256_or_none(G2_FROZEN_COPY)
    return rep, problems


def help_flags(path):
    try:
        r = subprocess.run([path, "-h"], capture_output=True, text=True,
                           timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)
    text = (r.stdout or "") + (r.stderr or "")
    return sorted(set(re.findall(r"^\s+-([A-Za-z][\w-]*)", text, re.M))), ""


def flag_report(rep):
    out = {}
    problems = []
    for tag in ("g2", "g3"):
        if not rep.get(tag, {}).get("exists"):
            out[tag] = None
            continue
        flags, err = help_flags(rep[tag]["path"])
        out[tag] = {"flags": flags, "error": err}
        if flags is None:
            problems.append("%s -h failed: %s" % (tag, err))
            continue
        have = set(flags)
        if tag == "g3" and not {"layout", "lead"} <= have:
            problems.append("g3 binary lacks -layout/-lead (flags: %s)"
                            % ", ".join(flags))
        if tag == "g2" and "layout" in have:
            problems.append("g2 binary unexpectedly has -layout")
    return out, problems


def validate_client(tag, fec, m, extra=()):
    argv = [BINS[tag], "-mode", "client", "-addr", "%s:%d" % (B.RX_IP, PORTS[tag]),
            "-n", "0", "-fec", fec, "-m", str(m)] + list(extra)
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, argv, str(exc)
    text = ((r.stdout or "") + (r.stderr or "")).strip()
    return r.returncode == 0, argv, text[-300:]


def _proc_table():
    out = []
    try:
        names = os.listdir("/proc")
    except OSError:
        return None
    for name in names:
        if not name.isdigit():
            continue
        pid = int(name)
        try:
            with open("/proc/%d/cmdline" % pid, "rb") as f:
                argv = [a.decode("utf-8", "replace")
                        for a in f.read().split(b"\0") if a]
            with open("/proc/%d/comm" % pid, "rb") as f:
                comm = f.read().decode("utf-8", "replace").strip()
            with open("/proc/%d/stat" % pid, "rb") as f:
                stat = f.read().decode("utf-8", "replace")
            ppid = int(stat.rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            continue
        out.append({"pid": pid, "ppid": ppid, "comm": comm, "argv": argv})
    return out


def _lineage(table):
    by_pid = {p["pid"]: p for p in table}
    skip = {os.getpid()}
    cur = by_pid.get(os.getpid())
    while cur and cur["ppid"] > 1 and cur["ppid"] not in skip:
        skip.add(cur["ppid"])
        cur = by_pid.get(cur["ppid"])
    return skip


def pgrep_qamp():
    try:
        r = subprocess.run(["pgrep", "-x", "qamp"], capture_output=True,
                           text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode not in (0, 1):
        return None
    return [int(x) for x in (r.stdout or "").split() if x.isdigit()]


def busy_processes(allowed=()):
    allowed = set(allowed)
    table = _proc_table()
    if table is None:
        return ["cannot read /proc"]
    skip = _lineage(table) | allowed
    found = []
    seen = set()
    pg = pgrep_qamp()
    if pg is None:
        found.append("pgrep -x qamp failed")
    else:
        for pid in pg:
            if pid not in skip:
                seen.add(pid)
                found.append("qamp pid %d (pgrep -x qamp)" % pid)
    for p in table:
        if p["pid"] in skip or p["pid"] in seen:
            continue
        if p["comm"] == "qamp":
            found.append("qamp pid %d: %s" % (p["pid"], " ".join(p["argv"])[:200]))
            continue
        exe = os.path.basename(p["argv"][0]) if p["argv"] else ""
        if exe.startswith("python") and any(MEASURE_RE.search(a)
                                            for a in p["argv"][1:]):
            found.append("measurement script pid %d: %s"
                         % (p["pid"], " ".join(p["argv"])[:200]))
    return found


def load_processes():
    table = _proc_table() or []
    skip = _lineage(table)
    return ["%s pid %d: %s" % (p["comm"], p["pid"], " ".join(p["argv"])[:160])
            for p in table if p["pid"] not in skip and p["comm"] in LOAD_COMMS]


def setup(mtu=1500):
    os.makedirs(WORK, exist_ok=True)
    saved = B.WORK
    B.WORK = WORK
    try:
        B.setup(mtu)
    finally:
        B.WORK = saved


def netem_specs(one_way_ms, loss_c2s, rate_up_mbit):
    return {"c2s_dev": B.DEV_LOCAL,
            "c2s": B._netem_spec(one_way_ms, loss_c2s, 1.0, rate_up_mbit),
            "s2c_dev": B.DEV_PEER,
            "s2c": B._netem_spec(one_way_ms, 0.0, 1.0, 0.0)}


def set_netem(one_way_ms, loss_c2s, rate_up_mbit):
    B.set_netem(one_way_ms, loss_c2s=loss_c2s, rate_up_mbit=rate_up_mbit)
    out = netem_specs(one_way_ms, loss_c2s, rate_up_mbit)
    out["tc_c2s"] = B.run("tc qdisc show dev %s" % B.DEV_LOCAL,
                          check=False).stdout.strip()
    out["tc_s2c"] = B.run("ip netns exec %s tc qdisc show dev %s"
                          % (B.NS, B.DEV_PEER), check=False).stdout.strip()
    return out


def start_server(tag, certsize, fec="on", extra=()):
    path = BINS[tag]
    stats_path = os.path.join(WORK, "srv_%s.json" % tag)
    err_path = os.path.join(WORK, "srv_%s_stderr.txt" % tag)
    for p in (stats_path, stats_path + ".tmp"):
        try:
            os.unlink(p)
        except OSError:
            pass
    cmd = ["ip", "netns", "exec", B.NS] + B.TASKSET + [
        path, "-mode", "server", "-addr", "%s:%d" % (B.RX_IP, PORTS[tag]),
        "-certsize", str(certsize), "-fec", fec, "-stats", stats_path]
    cmd += list(extra)
    err_f = open(err_path, "wb")
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=err_f)
    err_f.close()
    deadline = time.monotonic() + 15
    ready = False
    while time.monotonic() < deadline:
        if b"READY" in _read_bytes(err_path):
            ready = True
            break
        if p.poll() is not None:
            break
        time.sleep(0.05)
    text = _read_bytes(err_path)
    if not ready or p.poll() is not None:
        B.stop_server(p)
        raise RuntimeError("server %s not ready: %s"
                           % (tag, text[-1000:].decode("utf-8", "replace")))
    der = re.search(rb"cert DER = (\d+) bytes", text)
    return {"tag": tag, "proc": p, "pid": p.pid, "stats_path": stats_path,
            "stderr_path": err_path, "argv": cmd, "certsize": certsize,
            "cert_der": int(der.group(1)) if der else None}


def stop_server(server):
    if server:
        B.stop_server(server.get("proc"))


def server_alive(server):
    return bool(server) and server["proc"].poll() is None


def read_stats(path, tries=20):
    for _ in range(tries):
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, ValueError):
                pass
        time.sleep(0.1)
    return {}


def scalar_delta(before, after):
    out = {}
    for k, v in (after or {}).items():
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        b = (before or {}).get(k, 0)
        if isinstance(b, bool) or not isinstance(b, (int, float)):
            b = 0
        out[k] = v - b
    return out


def scalars(stats):
    return {k: v for k, v in (stats or {}).items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)}


def new_conns(before, after):
    bc = (before or {}).get("conns") or {}
    ac = (after or {}).get("conns") or {}
    out = []
    for key in sorted(set(ac) - set(bc)):
        c = ac[key]
        if isinstance(c, dict):
            out.append({f: c.get(f) for f in CONN_FIELDS})
    return out


def run_client(tag, group, n, fec, m, gap_ms, timeout_s, expect_k,
               uplink_mbps, extra=()):
    if not isinstance(n, int) or n <= 0:
        raise ValueError("n must be a positive int")
    path = BINS[tag]
    stats_path = os.path.join(WORK, "cli_stats.json")
    try:
        os.unlink(stats_path)
    except OSError:
        pass
    argv = [path, "-mode", "client", "-addr", "%s:%d" % (B.RX_IP, PORTS[tag]),
            "-group", group, "-n", str(n), "-fec", fec, "-m", str(m),
            "-gap", "%dms" % int(gap_ms), "-timeout", "%ds" % int(timeout_s),
            "-stats", stats_path, "-uplink-mbps", "%g" % float(uplink_mbps)]
    if expect_k:
        argv += ["-expect-k", str(expect_k)]
    argv += list(extra)
    cmd = ["timeout", str(int(timeout_s * n + 120))] + B.TASKSET + argv
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout_s * n + 180)
    except subprocess.TimeoutExpired:
        return [], {}, "timeout(python)", argv, None
    rows = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    stats = {}
    if os.path.exists(stats_path):
        try:
            with open(stats_path, encoding="utf-8") as f:
                stats = json.load(f)
        except (OSError, ValueError):
            stats = {}
    err = ""
    if r.returncode != 0:
        tail = (r.stderr or "")[-300:].strip().replace("\n", " | ")
        err = ("timeout(rc124)" if r.returncode == 124
               else "exit %d: %s" % (r.returncode, tail))
    elif len(rows) != n:
        err = "rows %d != n %d" % (len(rows), n)
    elif not stats:
        err = "client stats missing"
    return rows, stats, err, argv, r.returncode


def quicbed_sources():
    out = {}
    try:
        names = sorted(os.listdir(QUICBED))
    except OSError:
        return {}, None
    for name in names:
        if name.endswith((".go", ".sh", ".mod", ".sum")):
            out[name] = sha256_or_none(os.path.join(QUICBED, name))
    build_like = [n for n in names
                  if n.endswith(".go") or n in ("build.sh", "go.mod", "go.sum")]
    lines = "".join("%s %s\n" % (n, out.get(n)) for n in sorted(build_like))
    return out, hashlib.sha256(lines.encode()).hexdigest()


def _cmd_text(args):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=20)
        return ((r.stdout or "") + (r.stderr or "")).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "unavailable: %s" % exc


def environment():
    sources, build_fp = quicbed_sources()
    return {"uname_r": _cmd_text(["uname", "-r"]),
            "python3_V": _cmd_text(["python3", "-V"]),
            "python_running": sys.version,
            "tc_V": _cmd_text(["tc", "-V"]),
            "ip_V": _cmd_text(["ip", "-V"]),
            "cpu_list": B.CPU_LIST, "taskset": B.TASKSET,
            "cpu_count": os.cpu_count(),
            "work": WORK, "bins": BINS, "ports": PORTS,
            "netns": B.NS, "devs": [B.DEV_LOCAL, B.DEV_PEER],
            "addrs": [B.TX_IP, B.RX_IP],
            "runtime_context": runtime_context(),
            "quicbed_sources_sha256": sources,
            "quicbed_build_style_fingerprint": build_fp}
