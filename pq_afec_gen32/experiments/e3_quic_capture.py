# -*- coding: utf-8 -*-
"""
E3 - QUIC Initial packet framing: analytic budget + REAL capture

Part A: exact QUIC Initial CRYPTO capacity from RFC 9000 / RFC 9001 framing.
        This replaces the estimated INITIAL_CRYPTO_CAPACITY = 1150.

Part B: real QUIC handshakes (openssl s_client -quic) relayed through a local
        UDP proxy that records every datagram and parses the long headers, so
        we can COUNT how many Initial packets the ClientHello is split into
        with and without ML-KEM.  This is the direct test of hypothesis H1
        ("ML-KEM forces the ClientHello across multiple Initial packets").

Output: experiments/results/e3_quic.json

Standard library only.  ASCII console output.
Network: makes ordinary outbound QUIC (UDP/443) connections to public web
servers, exactly like a browser would.
"""
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
os.makedirs(RESULTS, exist_ok=True)


def _harden_console():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


# =========================================================== Part A: analytic
def varint_len(v):
    """RFC 9000 sec 16 variable-length integer encoding size."""
    if v < 2 ** 6:
        return 1
    if v < 2 ** 14:
        return 2
    if v < 2 ** 30:
        return 4
    return 8


def initial_crypto_capacity(datagram=1200, dcid=8, scid=8, pn_len=4,
                            token_len=0, crypto_offset=0, aead_tag=16):
    """Bytes of TLS handshake data that fit in the CRYPTO frame of ONE Initial
    packet that fills a `datagram`-byte UDP payload.

    Long header (RFC 9000 sec 17.2.2 Initial Packet):
      1  first byte (form/fixed/type/reserved/pn_len)
      4  version
      1  DCID Len  + dcid
      1  SCID Len  + scid
      v  Token Length (varint) + token
      v  Length (varint)  -- covers packet number + payload + AEAD tag
      p  Packet Number (1..4)
    Then the protected payload and a 16-byte AEAD tag (RFC 9001 sec 5.3,
    AEAD_AES_128_GCM).

    CRYPTO frame (RFC 9000 sec 19.6):
      1  frame type 0x06
      v  Offset (varint)
      v  Length (varint)
    """
    fixed = 1 + 4 + 1 + dcid + 1 + scid
    tok = varint_len(token_len) + token_len
    # Length field must encode (pn_len + payload + tag). For a 1200B datagram
    # that value is > 63 and < 16384, so it is a 2-byte varint.
    len_field = 2
    header = fixed + tok + len_field + pn_len
    payload_budget = datagram - header - aead_tag
    crypto_hdr = 1 + varint_len(crypto_offset) + varint_len(payload_budget)
    return {
        "datagram": datagram, "dcid": dcid, "scid": scid, "pn_len": pn_len,
        "token_len": token_len, "crypto_offset": crypto_offset,
        "header_bytes": header, "aead_tag": aead_tag,
        "payload_budget": payload_budget,
        "crypto_frame_header": crypto_hdr,
        "crypto_capacity": payload_budget - crypto_hdr,
    }


def split_count(ch_bytes, cap_first, cap_next):
    """How many Initial packets a ClientHello of ch_bytes needs."""
    if ch_bytes <= cap_first:
        return 1
    rest = ch_bytes - cap_first
    return 1 + (rest + cap_next - 1) // cap_next


# ============================================================ Part B: capture
LONG_TYPES = {0: "Initial", 1: "0-RTT", 2: "Handshake", 3: "Retry"}


def parse_quic_datagram(buf):
    """Parse coalesced QUIC packets in one UDP datagram.
    Only the cleartext outer framing is read (header protection covers just the
    low 4 bits of the first byte and the packet number, which we do not need)."""
    pkts = []
    i = 0
    n = len(buf)
    while i < n:
        b0 = buf[i]
        if not (b0 & 0x80):
            pkts.append({"form": "short", "bytes": n - i})
            break
        if (b0 & 0x40) == 0:
            pkts.append({"form": "not-quic", "bytes": n - i})
            break
        ptype = (b0 & 0x30) >> 4
        j = i + 1
        if j + 4 > n:
            break
        version = struct.unpack(">I", buf[j:j + 4])[0]
        j += 4
        if version == 0:
            pkts.append({"form": "version-negotiation", "bytes": n - i})
            break
        dcil = buf[j]; j += 1
        dcid = buf[j:j + dcil]; j += dcil
        scil = buf[j]; j += 1
        scid = buf[j:j + scil]; j += scil
        tok_len = 0
        if ptype == 0:  # Initial carries a token
            tok_len, j = read_varint(buf, j)
            j += tok_len
        if ptype == 3:  # Retry: rest of datagram
            pkts.append({"form": "long", "type": "Retry", "bytes": n - i,
                         "dcid_len": dcil, "scid_len": scil})
            break
        length, j = read_varint(buf, j)
        hdr_len = j - i
        total = hdr_len + length
        pkts.append({
            "form": "long", "type": LONG_TYPES.get(ptype, str(ptype)),
            "version": "0x%08x" % version,
            "dcid_len": dcil, "scid_len": scil, "token_len": tok_len,
            "length_field": length, "header_bytes": hdr_len,
            "packet_bytes": total,
        })
        i += total
        if total <= 0:
            break
    return pkts


def read_varint(buf, i):
    b = buf[i]
    pref = b >> 6
    if pref == 0:
        return b & 0x3F, i + 1
    if pref == 1:
        return ((b & 0x3F) << 8) | buf[i + 1], i + 2
    if pref == 2:
        return ((b & 0x3F) << 24) | (buf[i + 1] << 16) | (buf[i + 2] << 8) | buf[i + 3], i + 4
    v = b & 0x3F
    for k in range(1, 8):
        v = (v << 8) | buf[i + k]
    return v, i + 8


class UdpRelay(object):
    def __init__(self, host, port=443, prefer_v4=True):
        infos = socket.getaddrinfo(host, port, 0, socket.SOCK_DGRAM)
        v4 = [i for i in infos if i[0] == socket.AF_INET]
        pick = (v4 or infos)[0] if prefer_v4 else infos[0]
        self.family, self.upstream_addr = pick[0], pick[4]
        self.local = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.local.bind(("127.0.0.1", 0))
        self.local.settimeout(0.3)
        self.port = self.local.getsockname()[1]
        self.up = socket.socket(self.family, socket.SOCK_DGRAM)
        self.up.settimeout(0.3)
        self.log = []
        self.stop = threading.Event()
        self.client_addr = None
        self.t0 = None

    def _record(self, direction, data):
        if self.t0 is None:
            self.t0 = time.perf_counter()
        self.log.append({
            "dir": direction,
            "t_ms": (time.perf_counter() - self.t0) * 1000.0,
            "udp_bytes": len(data),
            "packets": parse_quic_datagram(data),
        })

    def _from_client(self):
        while not self.stop.is_set():
            try:
                data, addr = self.local.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            self.client_addr = addr
            self._record("C2S", data)
            try:
                self.up.sendto(data, self.upstream_addr)
            except OSError:
                break

    def _from_server(self):
        while not self.stop.is_set():
            try:
                data, _ = self.up.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            self._record("S2C", data)
            if self.client_addr:
                try:
                    self.local.sendto(data, self.client_addr)
                except OSError:
                    break

    def start(self):
        self.t1 = threading.Thread(target=self._from_client, daemon=True)
        self.t2 = threading.Thread(target=self._from_server, daemon=True)
        self.t1.start()
        self.t2.start()

    def shutdown(self):
        self.stop.set()
        time.sleep(0.4)
        for s in (self.local, self.up):
            try:
                s.close()
            except Exception:
                pass


def quic_handshake_through_relay(host, group, alpn="h3", timeout=25):
    relay = UdpRelay(host)
    relay.start()
    time.sleep(0.2)
    cmd = ["openssl", "s_client", "-quic",
           "-connect", "127.0.0.1:%d" % relay.port,
           "-servername", host, "-alpn", alpn, "-groups", group, "-brief"]
    try:
        r = subprocess.run(cmd, input=b"", capture_output=True, timeout=timeout)
        txt = (r.stdout + r.stderr).decode("utf-8", "replace")
        rc = r.returncode
    except subprocess.TimeoutExpired:
        txt, rc = "TIMEOUT", -1
    time.sleep(0.5)
    relay.shutdown()
    return relay.log, rc, txt


def summarise_capture(log):
    """Client Initial packets that carry the ClientHello, and server flight."""
    c_init = []
    s_init = []
    s_hs = []
    first_dgram = None
    for e in log:
        if e["dir"] == "C2S":
            if first_dgram is None:
                first_dgram = e["udp_bytes"]
            for p in e["packets"]:
                if p.get("type") == "Initial":
                    c_init.append(p["packet_bytes"])
        else:
            for p in e["packets"]:
                if p.get("type") == "Initial":
                    s_init.append(p["packet_bytes"])
                elif p.get("type") == "Handshake":
                    s_hs.append(p["packet_bytes"])
    c2s_dgrams = [e["udp_bytes"] for e in log if e["dir"] == "C2S"]
    s2c_dgrams = [e["udp_bytes"] for e in log if e["dir"] == "S2C"]
    # the ClientHello flight = leading run of C2S datagrams before any S2C
    ch_flight = []
    for e in log:
        if e["dir"] == "S2C":
            break
        ch_flight.append(e)
    ch_initials = 0
    ch_bytes = 0
    for e in ch_flight:
        for p in e["packets"]:
            if p.get("type") == "Initial":
                ch_initials += 1
                ch_bytes += p["packet_bytes"]
    return {
        "client_initial_packets_total": len(c_init),
        "clienthello_flight_datagrams": len(ch_flight),
        "clienthello_flight_initial_packets": ch_initials,
        "clienthello_flight_initial_bytes": ch_bytes,
        "clienthello_flight_udp_bytes": sum(e["udp_bytes"] for e in ch_flight),
        "server_initial_packets": len(s_init),
        "server_initial_bytes": sum(s_init),
        "server_handshake_packets": len(s_hs),
        "server_handshake_bytes": sum(s_hs),
        "c2s_datagrams": c2s_dgrams,
        "s2c_datagrams": s2c_dgrams,
    }


# ===================================================================== main
def main():
    _harden_console()
    print("=" * 78)
    print("E3 - QUIC Initial framing: analytic budget + real capture")
    print("=" * 78)
    out = {"analytic": {}, "capture": {}}

    # ---- Part A
    print("")
    print("[A] analytic CRYPTO capacity of one Initial packet (RFC 9000/9001)")
    print("-" * 78)
    print("%-42s %8s %8s %10s" % ("configuration", "header", "budget", "CRYPTO cap"))
    cfgs = [
        ("1200B dgram, DCID8/SCID8, PN4, offset0", dict(dcid=8, scid=8, pn_len=4)),
        ("1200B dgram, DCID8/SCID8, PN1, offset0", dict(dcid=8, scid=8, pn_len=1)),
        ("1200B dgram, DCID20/SCID20, PN4", dict(dcid=20, scid=20, pn_len=4)),
        ("1200B dgram, DCID8/SCID0, PN4", dict(dcid=8, scid=0, pn_len=4)),
        ("1252B dgram (IPv4 min PMTU), DCID8/SCID8, PN4",
         dict(datagram=1252, dcid=8, scid=8, pn_len=4)),
        ("1200B, 2nd packet (offset>=1024 -> 2B varint)",
         dict(dcid=8, scid=8, pn_len=4, crypto_offset=1200)),
    ]
    for name, kw in cfgs:
        a = initial_crypto_capacity(**kw)
        out["analytic"][name] = a
        print("%-42s %8d %8d %10d" %
              (name, a["header_bytes"], a["payload_budget"], a["crypto_capacity"]))

    base = initial_crypto_capacity(dcid=8, scid=8, pn_len=4)
    nxt = initial_crypto_capacity(dcid=8, scid=8, pn_len=4, crypto_offset=1200)
    out["recommended_INITIAL_CRYPTO_CAPACITY"] = base["crypto_capacity"]
    out["recommended_next_packet_capacity"] = nxt["crypto_capacity"]
    print("")
    print("  -> INITIAL_CRYPTO_CAPACITY (first packet)  = %d" % base["crypto_capacity"])
    print("     capacity of each following Initial      = %d" % nxt["crypto_capacity"])

    # measured ClientHello sizes from E2, if available
    e2p = os.path.join(RESULTS, "e2_tls_flights.json")
    if os.path.exists(e2p):
        with open(e2p, encoding="utf-8") as f:
            e2 = json.load(f)
        print("")
        print("  predicted Initial-packet split for the measured ClientHellos")
        print("  %-22s %10s %8s" % ("group", "CH msg B", "packets"))
        pred = {}
        for k, h in e2["handshakes"].items():
            if not k.startswith("ecdsa256/"):
                continue
            ch = h.get("clienthello_msg_wire")
            if not ch:
                continue
            n = split_count(ch, base["crypto_capacity"], nxt["crypto_capacity"])
            pred[h["group"]] = {"ch_msg_bytes": ch, "initial_packets": n}
            print("  %-22s %10d %8d" % (h["group"], ch, n))
        out["predicted_split_tcp_ch"] = pred

    # ---- Part B
    hosts = os.environ.get("E3_HOSTS", "cloudflare.com,www.google.com").split(",")
    groups = os.environ.get(
        "E3_GROUPS", "x25519,X25519MLKEM768,SecP256r1MLKEM768,MLKEM768").split(",")
    reps = int(os.environ.get("E3_REPS", "3"))

    print("")
    print("[B] real QUIC handshakes through a recording UDP relay")
    print("-" * 78)
    print("%-18s %-20s %5s %7s %7s %9s %9s" %
          ("host", "group", "rc", "CHdgrm", "CHpkts", "CHbytes", "srvInit"))
    for host in hosts:
        for group in groups:
            rows = []
            for i in range(reps):
                try:
                    log, rc, txt = quic_handshake_through_relay(host, group)
                except Exception as e:
                    print("%-18s %-20s  EXC %s" % (host, group, str(e)[:40]))
                    break
                s = summarise_capture(log)
                s["rc"] = rc
                s["established"] = "CONNECTION ESTABLISHED" in txt
                rows.append(s)
                time.sleep(0.3)
            if not rows:
                continue
            ok = [r for r in rows if r["established"]] or rows
            r0 = ok[0]
            out["capture"]["%s/%s" % (host, group)] = {
                "reps": rows,
                "established_count": sum(1 for r in rows if r["established"]),
            }
            print("%-18s %-20s %5d %7d %7d %9d %9d" %
                  (host, group, r0["rc"],
                   r0["clienthello_flight_datagrams"],
                   r0["clienthello_flight_initial_packets"],
                   r0["clienthello_flight_udp_bytes"],
                   r0["server_initial_bytes"]))

    path = os.path.join(RESULTS, "e3_quic.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("")
    print("saved: %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
