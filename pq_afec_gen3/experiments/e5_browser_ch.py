# -*- coding: utf-8 -*-
"""
E5 - real browser ClientHello sizes (the other end of the ch_base range)

`openssl s_client` sends a minimal ClientHello (measured in E4: 232 bytes of
non-key-share content).  Real browsers send much larger ones (GREASE, ALPN,
SNI, session tickets, compressed certificates, ...).  Because the Initial
CRYPTO budget is a hard 1150 bytes, ch_base decides whether a given ML-KEM
parameter set splits the ClientHello or not, so we need both ends of the range.

Part A: Chrome over TLS/TCP to a local listener  -> browser ch_base (TCP)
Part B: Chrome over QUIC through a recording relay to a real server
        -> browser ch_base (QUIC, includes quic_transport_parameters)
        Best effort: needs --host-resolver-rules to work and UDP/443 free.

Output: experiments/results/e5_browser_ch.json
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
os.makedirs(RESULTS, exist_ok=True)
sys.path.insert(0, HERE)

from e4_quic_decrypt import (  # noqa: E402
    iter_long_packets, initial_keys, decrypt_initial, parse_frames,
    parse_client_hello, EXT_NAMES)

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def _harden_console():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


def find_browser():
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    for n in ("chrome", "msedge"):
        w = shutil.which(n)
        if w:
            return w
    return None


# ------------------------------------------------------ Part A: TCP listener
def capture_tcp_clienthello(timeout=25):
    """Accept one TCP connection, read the TLS record holding the ClientHello."""
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)
    srv.settimeout(timeout)
    port = srv.getsockname()[1]
    result = {}

    def worker():
        try:
            c, _ = srv.accept()
        except socket.timeout:
            return
        c.settimeout(5)
        buf = b""
        try:
            while len(buf) < 5:
                d = c.recv(65535)
                if not d:
                    break
                buf += d
            if len(buf) >= 5:
                ln = (buf[3] << 8) | buf[4]
                while len(buf) < 5 + ln:
                    d = c.recv(65535)
                    if not d:
                        break
                    buf += d
                body = buf[5:5 + ln]
                if body and body[0] == 0x01:
                    result["record_wire"] = ln + 5
                    result["parsed"] = parse_client_hello(body)
        except Exception as e:
            result["error"] = str(e)
        finally:
            try:
                c.close()
            except Exception:
                pass
        try:
            srv.close()
        except Exception:
            pass

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return port, t, result


# ---------------------------------------------------- Part B: QUIC relay@443
class Relay443(object):
    def __init__(self, host, port=443):
        infos = socket.getaddrinfo(host, port, 0, socket.SOCK_DGRAM)
        v4 = [i for i in infos if i[0] == socket.AF_INET]
        pick = (v4 or infos)[0]
        self.family, self.upstream = pick[0], pick[4]
        self.local = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.local.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.local.bind(("127.0.0.1", 443))
        self.local.settimeout(0.3)
        self.up = socket.socket(self.family, socket.SOCK_DGRAM)
        self.up.settimeout(0.3)
        self.dgrams = []
        self.stop = threading.Event()
        self.caddr = None

    def _c(self):
        while not self.stop.is_set():
            try:
                d, a = self.local.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            self.caddr = a
            self.dgrams.append(("C2S", d))
            try:
                self.up.sendto(d, self.upstream)
            except OSError:
                break

    def _s(self):
        while not self.stop.is_set():
            try:
                d, _ = self.up.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            self.dgrams.append(("S2C", d))
            if self.caddr:
                try:
                    self.local.sendto(d, self.caddr)
                except OSError:
                    break

    def start(self):
        threading.Thread(target=self._c, daemon=True).start()
        threading.Thread(target=self._s, daemon=True).start()

    def shutdown(self):
        self.stop.set()
        time.sleep(0.4)
        for s in (self.local, self.up):
            try:
                s.close()
            except Exception:
                pass


def decrypt_client_hello(dgrams):
    odcid = None
    for d, buf in dgrams:
        if d != "C2S":
            continue
        for kind, s, pn_off, end, dcid, scid in iter_long_packets(buf):
            if kind == "Initial":
                odcid = dcid
                break
        if odcid:
            break
    if not odcid:
        return None
    keys = initial_keys(odcid)
    chunks = {}
    npkt = 0
    for d, buf in dgrams:
        if d != "C2S":
            continue
        for kind, s, pn_off, end, dcid, scid in iter_long_packets(buf):
            if kind != "Initial":
                continue
            try:
                pt, pn, b0 = decrypt_initial(buf, s, pn_off, end, keys["client"])
            except Exception:
                continue
            if pt is None:
                continue
            npkt += 1
            for f in parse_frames(pt):
                if f["type"] == "CRYPTO":
                    chunks[f["offset"]] = f["data"]
    if not chunks:
        return None
    out = bytearray()
    for off in sorted(chunks):
        if off > len(out):
            break
        out[off:off + len(chunks[off])] = chunks[off]
    if not out or out[0] != 0x01:
        return {"initial_packets": npkt, "stream_bytes": len(out),
                "note": "not a ClientHello"}
    r = parse_client_hello(bytes(out))
    r["initial_packets"] = npkt
    r["client_initial_datagrams"] = sum(1 for d, _ in dgrams if d == "C2S")
    return r


def summarise(parsed, label):
    ks = next((e for e in parsed["extensions"] if e["type"] == 51), None)
    share = sum(s["key_bytes"] for s in ks.get("shares", [])) if ks else 0
    groups = [s["group"] for s in ks.get("shares", [])] if ks else []
    qtp = next((e for e in parsed["extensions"] if e["type"] == 57), None)
    return {
        "label": label,
        "ch_wire": parsed["msg_wire_len"],
        "keyshare_bytes": share,
        "keyshare_groups": groups,
        "ch_base": parsed["msg_wire_len"] - share,
        "quic_transport_parameters": qtp["wire_len"] if qtp else None,
        "n_extensions": len(parsed["extensions"]),
        "extensions": [{"name": e["name"], "wire_len": e["wire_len"]}
                       for e in parsed["extensions"]],
    }


def main():
    _harden_console()
    print("=" * 78)
    print("E5 - real browser ClientHello")
    print("=" * 78)
    br = find_browser()
    if not br:
        print("no chrome/edge found; skipping")
        return 0
    print("browser: %s" % br)
    out = {"browser_path": br}

    common = ["--headless=new", "--disable-gpu", "--no-first-run",
              "--no-default-browser-check", "--disable-extensions",
              "--disable-background-networking", "--no-sandbox"]

    # ---- Part A: TLS over TCP
    print("")
    print("[A] browser ClientHello over TLS/TCP (local listener)")
    port, t, res = capture_tcp_clienthello()
    with tempfile.TemporaryDirectory() as ud:
        p = subprocess.Popen([br] + common + ["--user-data-dir=" + ud,
                                              "--ignore-certificate-errors",
                                              "https://127.0.0.1:%d/" % port],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        t.join(25)
        try:
            p.terminate()
        except Exception:
            pass
        time.sleep(0.5)
    if "parsed" in res:
        s = summarise(res["parsed"], "browser-tcp")
        out["tcp"] = s
        print("  CH wire       = %d bytes" % s["ch_wire"])
        print("  key share     = %d bytes  groups=%s" %
              (s["keyshare_bytes"], s["keyshare_groups"]))
        print("  ch_base (TCP) = %d bytes  (%d extensions)" %
              (s["ch_base"], s["n_extensions"]))
        big = sorted(s["extensions"], key=lambda e: -e["wire_len"])[:6]
        for e in big:
            print("      %-30s %5d" % (e["name"], e["wire_len"]))
    else:
        print("  FAILED: %s" % res.get("error", "no ClientHello captured"))

    # ---- Part B: QUIC through relay on udp/443
    print("")
    print("[B] browser ClientHello over QUIC (relay on udp/443 -> cloudflare.com)")
    host = os.environ.get("E5_HOST", "cloudflare.com")
    try:
        relay = Relay443(host)
    except OSError as e:
        print("  cannot bind udp/443 (%s) - skipping QUIC part" % e)
        relay = None
    if relay:
        relay.start()
        with tempfile.TemporaryDirectory() as ud:
            args = common + [
                "--user-data-dir=" + ud,
                "--origin-to-force-quic-on=%s:443" % host,
                "--host-resolver-rules=MAP %s 127.0.0.1" % host,
                "--ignore-certificate-errors",
                "https://%s/" % host,
            ]
            p = subprocess.Popen([br] + args, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            time.sleep(14)
            try:
                p.terminate()
            except Exception:
                pass
            time.sleep(1.0)
        relay.shutdown()
        print("  captured %d datagrams (%d C2S)" %
              (len(relay.dgrams), sum(1 for d, _ in relay.dgrams if d == "C2S")))
        parsed = decrypt_client_hello(relay.dgrams)
        if parsed and "extensions" in parsed:
            s = summarise(parsed, "browser-quic")
            s["initial_packets"] = parsed["initial_packets"]
            s["client_initial_datagrams"] = parsed["client_initial_datagrams"]
            out["quic"] = s
            print("  CH wire        = %d bytes" % s["ch_wire"])
            print("  key share      = %d bytes  groups=%s" %
                  (s["keyshare_bytes"], s["keyshare_groups"]))
            print("  ch_base (QUIC) = %d bytes  (%d extensions, quic_tp=%s)" %
                  (s["ch_base"], s["n_extensions"], s["quic_transport_parameters"]))
            print("  Initial packets carrying the ClientHello = %d" %
                  s["initial_packets"])
            for e in sorted(s["extensions"], key=lambda e: -e["wire_len"])[:6]:
                print("      %-30s %5d" % (e["name"], e["wire_len"]))
        else:
            print("  QUIC ClientHello not recovered (%s)" % (parsed or "no Initial"))

    path = os.path.join(RESULTS, "e5_browser_ch.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("")
    print("saved: %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
