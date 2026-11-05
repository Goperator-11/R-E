# -*- coding: utf-8 -*-
"""
E2 - real TLS 1.3 handshake flight sizes (R&E research content 1)

Runs a REAL handshake between `openssl s_server` and `openssl s_client`
through a byte-counting TCP proxy, and records every TLS record in order.
Repeats for each key-exchange group so we can see exactly how many bytes
ML-KEM adds to the ClientHello and to the server flight.

This replaces the three estimated constants in afec/handshake.py:
    ch_base = 350          (ClientHello minus the key share)
    cert_chain = 3000      (server certificate flight)
    INITIAL_CRYPTO_CAPACITY = 1150   (computed separately in e3)

Output: experiments/results/e2_tls_flights.json

Standard library only. ASCII console output.
"""
import json
import os
import socket
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
PKI = os.path.join(HERE, "pki")
os.makedirs(RESULTS, exist_ok=True)
os.makedirs(PKI, exist_ok=True)

GROUPS = [
    "x25519",
    "secp256r1",
    "MLKEM512",
    "MLKEM768",
    "MLKEM1024",
    "X25519MLKEM768",
    "SecP256r1MLKEM768",
    "X448MLKEM1024",
]

CT_NAME = {20: "CCS", 21: "Alert", 22: "Handshake", 23: "AppData"}
HS_NAME = {1: "ClientHello", 2: "ServerHello", 4: "NewSessionTicket",
           8: "EncryptedExtensions", 11: "Certificate", 13: "CertificateRequest",
           15: "CertificateVerify", 20: "Finished"}


def _harden_console():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


def sh(cmd, check=True):
    r = subprocess.run(cmd, capture_output=True)
    if check and r.returncode != 0:
        raise RuntimeError("cmd failed: %s\n%s" % (cmd, r.stderr.decode("utf-8", "replace")))
    return r


# --------------------------------------------------------------------- PKI
def build_chain(kind):
    """Build root -> intermediate -> leaf. kind in {'rsa2048','ecdsa256'}.
    Returns (leaf_key, leaf_cert, chain_file)."""
    d = os.path.join(PKI, kind)
    os.makedirs(d, exist_ok=True)
    p = lambda n: os.path.join(d, n)
    if os.path.exists(p("chain.pem")) and os.path.exists(p("leaf.key")):
        return p("leaf.key"), p("leaf.crt"), p("chain.pem")

    if kind == "rsa2048":
        keyalg = ["-newkey", "rsa:2048"]
        genkey = lambda out: sh(["openssl", "genpkey", "-algorithm", "RSA",
                                 "-pkeyopt", "rsa_keygen_bits:2048", "-out", out])
    else:
        genkey = lambda out: sh(["openssl", "genpkey", "-algorithm", "EC",
                                 "-pkeyopt", "ec_paramgen_curve:P-256", "-out", out])

    for name in ("root", "inter", "leaf"):
        genkey(p(name + ".key"))

    # root (self-signed CA)
    sh(["openssl", "req", "-x509", "-new", "-key", p("root.key"),
        "-subj", "/C=KR/O=PQ-AFEC Test/CN=PQ-AFEC Test Root CA",
        "-days", "30", "-addext", "basicConstraints=critical,CA:TRUE",
        "-out", p("root.crt")])

    # intermediate CSR + sign by root
    sh(["openssl", "req", "-new", "-key", p("inter.key"),
        "-subj", "/C=KR/O=PQ-AFEC Test/CN=PQ-AFEC Test Intermediate CA",
        "-out", p("inter.csr")])
    with open(p("inter.ext"), "w") as f:
        f.write("basicConstraints=critical,CA:TRUE,pathlen:0\nkeyUsage=critical,keyCertSign,cRLSign\n")
    sh(["openssl", "x509", "-req", "-in", p("inter.csr"), "-CA", p("root.crt"),
        "-CAkey", p("root.key"), "-CAcreateserial", "-days", "30",
        "-extfile", p("inter.ext"), "-out", p("inter.crt")])

    # leaf CSR + sign by intermediate
    sh(["openssl", "req", "-new", "-key", p("leaf.key"),
        "-subj", "/C=KR/O=PQ-AFEC Test/CN=localhost", "-out", p("leaf.csr")])
    with open(p("leaf.ext"), "w") as f:
        f.write("basicConstraints=critical,CA:FALSE\n"
                "keyUsage=critical,digitalSignature,keyEncipherment\n"
                "extendedKeyUsage=serverAuth\n"
                "subjectAltName=DNS:localhost,IP:127.0.0.1\n")
    sh(["openssl", "x509", "-req", "-in", p("leaf.csr"), "-CA", p("inter.crt"),
        "-CAkey", p("inter.key"), "-CAcreateserial", "-days", "30",
        "-extfile", p("leaf.ext"), "-out", p("leaf.crt")])

    with open(p("chain.pem"), "wb") as out:
        for n in ("leaf.crt", "inter.crt"):
            with open(p(n), "rb") as f:
                out.write(f.read())
    return p("leaf.key"), p("leaf.crt"), p("chain.pem")


def chain_wire_bytes(chain_file):
    """DER bytes of every cert in the chain (what actually goes on the wire)."""
    r = sh(["openssl", "crl2pkcs7", "-nocrl", "-certfile", chain_file,
            "-outform", "DER"])
    # simpler: convert each PEM cert separately
    with open(chain_file, "rb") as f:
        pem = f.read()
    parts = pem.split(b"-----END CERTIFICATE-----")
    total = 0
    each = []
    for part in parts:
        if b"-----BEGIN CERTIFICATE-----" not in part:
            continue
        blob = part + b"-----END CERTIFICATE-----\n"
        r = subprocess.run(["openssl", "x509", "-outform", "DER"],
                           input=blob, capture_output=True)
        each.append(len(r.stdout))
        total += len(r.stdout)
    return total, each


# ------------------------------------------------------------------- proxy
def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class RecordSplitter(object):
    """Feed raw TLS stream bytes, get complete records out."""

    def __init__(self):
        self.buf = b""

    def feed(self, data):
        self.buf += data
        out = []
        while len(self.buf) >= 5:
            ctype = self.buf[0]
            ln = (self.buf[3] << 8) | self.buf[4]
            if len(self.buf) < 5 + ln:
                break
            body = self.buf[5:5 + ln]
            self.buf = self.buf[5 + ln:]
            out.append((ctype, ln, body))
        return out


def plaintext_hs_messages(body):
    """For an unencrypted handshake record, list (msg_type, msg_len)."""
    out = []
    i = 0
    while i + 4 <= len(body):
        mt = body[i]
        ml = int.from_bytes(body[i + 1:i + 4], "big")
        out.append((mt, ml))
        i += 4 + ml
    return out


def run_proxy(listen_port, target_port, log, stop_evt):
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", listen_port))
    srv.listen(1)
    srv.settimeout(20)
    try:
        cli, _ = srv.accept()
    except socket.timeout:
        srv.close()
        return
    up = socket.socket()
    up.connect(("127.0.0.1", target_port))
    t0 = time.perf_counter()

    splitters = {"C2S": RecordSplitter(), "S2C": RecordSplitter()}

    def pump(a, b, tag):
        while not stop_evt.is_set():
            try:
                data = a.recv(65536)
            except Exception:
                break
            if not data:
                break
            for ctype, ln, body in splitters[tag].feed(data):
                entry = {
                    "dir": tag,
                    "t_ms": (time.perf_counter() - t0) * 1000.0,
                    "type": ctype,
                    "type_name": CT_NAME.get(ctype, str(ctype)),
                    "record_len": ln,
                    "wire_len": ln + 5,
                }
                if ctype == 22 and len(body) >= 4 and body[0] in HS_NAME:
                    msgs = plaintext_hs_messages(body)
                    if msgs and all(m[0] in HS_NAME for m in msgs):
                        entry["messages"] = [
                            {"type": m[0], "name": HS_NAME.get(m[0], str(m[0])),
                             "len": m[1], "wire_len": m[1] + 4} for m in msgs]
                log.append(entry)
            try:
                b.sendall(data)
            except Exception:
                break
        try:
            b.shutdown(socket.SHUT_WR)
        except Exception:
            pass

    t1 = threading.Thread(target=pump, args=(cli, up, "C2S"), daemon=True)
    t2 = threading.Thread(target=pump, args=(up, cli, "S2C"), daemon=True)
    t1.start()
    t2.start()
    t1.join(20)
    t2.join(20)
    for s in (cli, up, srv):
        try:
            s.close()
        except Exception:
            pass


def handshake_once(group, key, chain, sigalg_note):
    sport = free_port()
    pport = free_port()
    srv = subprocess.Popen(
        ["openssl", "s_server", "-accept", str(sport), "-www", "-quiet",
         "-key", key, "-cert_chain", chain, "-cert", os.path.join(
             os.path.dirname(chain), "leaf.crt"),
         "-tls1_3", "-groups", group, "-naccept", "1"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(1.2)
    if srv.poll() is not None:
        err = srv.stderr.read().decode("utf-8", "replace")
        raise RuntimeError("s_server died for group %s:\n%s" % (group, err[-800:]))

    log = []
    stop = threading.Event()
    pt = threading.Thread(target=run_proxy, args=(pport, sport, log, stop), daemon=True)
    pt.start()
    time.sleep(0.4)

    cli = subprocess.run(
        ["openssl", "s_client", "-connect", "127.0.0.1:%d" % pport,
         "-tls1_3", "-groups", group, "-CAfile",
         os.path.join(os.path.dirname(chain), "root.crt"),
         "-servername", "localhost", "-brief"],
        input=b"GET / HTTP/1.0\r\n\r\n", capture_output=True, timeout=30)
    time.sleep(0.6)
    stop.set()
    pt.join(5)
    try:
        srv.terminate()
    except Exception:
        pass

    cli_txt = (cli.stdout + cli.stderr).decode("utf-8", "replace")
    negotiated = None
    for line in cli_txt.splitlines():
        if "Negotiated TLS1.3 group" in line or "Server Temp Key" in line:
            negotiated = line.strip()
    return log, negotiated, cli_txt


def summarise(log):
    """Split the record log into flights (maximal same-direction runs)."""
    flights = []
    cur = None
    for e in log:
        if cur is None or cur["dir"] != e["dir"]:
            cur = {"dir": e["dir"], "records": [], "wire_bytes": 0}
            flights.append(cur)
        cur["records"].append(e)
        cur["wire_bytes"] += e["wire_len"]
    return flights


def main():
    _harden_console()
    print("=" * 78)
    print("E2 - real TLS 1.3 handshake flight sizes")
    print("=" * 78)

    out = {"chains": {}, "handshakes": {}}

    for kind in ("ecdsa256", "rsa2048"):
        key, leaf, chain = build_chain(kind)
        total, each = chain_wire_bytes(chain)
        out["chains"][kind] = {"der_total": total, "der_each": each}
        print("chain %-9s : %d DER bytes  %s" % (kind, total, each))
    print("")

    for kind in ("ecdsa256", "rsa2048"):
        key, leaf, chain = build_chain(kind)
        print("-" * 78)
        print("cert chain: %s" % kind)
        print("-" * 78)
        print("%-20s %10s %10s %10s   %s" %
              ("group", "CH wire", "S flight", "C flight2", "note"))
        for g in GROUPS:
            try:
                log, neg, txt = handshake_once(g, key, chain, kind)
            except Exception as e:
                print("%-20s  SKIP  %s" % (g, str(e)[:60]))
                continue
            fl = summarise(log)
            c2s = [f for f in fl if f["dir"] == "C2S"]
            s2c = [f for f in fl if f["dir"] == "S2C"]
            ch = c2s[0]["wire_bytes"] if c2s else 0
            sf = s2c[0]["wire_bytes"] if s2c else 0
            cf2 = c2s[1]["wire_bytes"] if len(c2s) > 1 else 0
            ch_msg = None
            if c2s and c2s[0]["records"] and "messages" in c2s[0]["records"][0]:
                ch_msg = c2s[0]["records"][0]["messages"][0]["wire_len"]
            key_ = "%s/%s" % (kind, g)
            out["handshakes"][key_] = {
                "group": g, "chain": kind,
                "clienthello_wire": ch,
                "clienthello_msg_wire": ch_msg,
                "server_flight1_wire": sf,
                "client_flight2_wire": cf2,
                "negotiated": neg,
                "flights": [{"dir": f["dir"], "wire_bytes": f["wire_bytes"],
                             "n_records": len(f["records"])} for f in fl],
                "records": log,
            }
            print("%-20s %10d %10d %10d   %s" % (g, ch, sf, cf2, neg or ""))
        print("")

    path = os.path.join(RESULTS, "e2_tls_flights.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("saved: %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
