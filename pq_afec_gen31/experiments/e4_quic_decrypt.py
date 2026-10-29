# -*- coding: utf-8 -*-
"""
E4 - decrypt real QUIC Initial packets and read the actual ClientHello

QUIC Initial packets are protected with keys derived from the client's original
Destination Connection ID and a well-known salt (RFC 9001 sec 5.2), so anyone
who sees the packets can read them.  That lets us measure - not estimate - the
exact ClientHello that ML-KEM produces on the wire, including the QUIC
transport-parameters extension that TLS-over-TCP does not carry.

This pins down the last estimated constant in afec/handshake.py:
    ch_base   (ClientHello bytes that are NOT the key share)

AES is done through the `openssl` CLI (ECB for header protection, CTR for the
GCM keystream) so that no third-party python package is needed.

Output: experiments/results/e4_quic_clienthello.json
"""
import hashlib
import hmac
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
os.makedirs(RESULTS, exist_ok=True)

INITIAL_SALT_V1 = bytes.fromhex("38762cf7f55934b34d179ae6a4c80cadccbb7f0a")


def _harden_console():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


# ------------------------------------------------------------------- HKDF
def hkdf_extract(salt, ikm):
    return hmac.new(salt, ikm, hashlib.sha256).digest()


def hkdf_expand(prk, info, length):
    out, t, i = b"", b"", 1
    while len(out) < length:
        t = hmac.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
        out += t
        i += 1
    return out[:length]


def hkdf_expand_label(secret, label, context, length):
    full = b"tls13 " + label.encode()
    info = struct.pack(">H", length) + bytes([len(full)]) + full \
        + bytes([len(context)]) + context
    return hkdf_expand(secret, info, length)


def initial_keys(dcid):
    prk = hkdf_extract(INITIAL_SALT_V1, dcid)
    out = {}
    for side, lbl in (("client", "client in"), ("server", "server in")):
        s = hkdf_expand_label(prk, lbl, b"", 32)
        out[side] = {
            "secret": s,
            "key": hkdf_expand_label(s, "quic key", b"", 16),
            "iv": hkdf_expand_label(s, "quic iv", b"", 12),
            "hp": hkdf_expand_label(s, "quic hp", b"", 16),
        }
    return out


# -------------------------------------------------------------- AES via CLI
def aes_ecb_block(key, block):
    with tempfile.TemporaryDirectory() as d:
        i, o = os.path.join(d, "i"), os.path.join(d, "o")
        with open(i, "wb") as f:
            f.write(block)
        r = subprocess.run(["openssl", "enc", "-aes-128-ecb", "-K", key.hex(),
                            "-nopad", "-in", i, "-out", o], capture_output=True)
        if r.returncode != 0:
            raise RuntimeError("aes-ecb failed: %s" % r.stderr.decode("utf-8", "replace"))
        with open(o, "rb") as f:
            return f.read()


def aes_ctr(key, counter_block, data):
    with tempfile.TemporaryDirectory() as d:
        i, o = os.path.join(d, "i"), os.path.join(d, "o")
        with open(i, "wb") as f:
            f.write(data)
        r = subprocess.run(["openssl", "enc", "-aes-128-ctr", "-K", key.hex(),
                            "-iv", counter_block.hex(), "-nopad",
                            "-in", i, "-out", o], capture_output=True)
        if r.returncode != 0:
            raise RuntimeError("aes-ctr failed: %s" % r.stderr.decode("utf-8", "replace"))
        with open(o, "rb") as f:
            return f.read()


# ------------------------------------------------------------ QUIC parsing
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


def iter_long_packets(dgram):
    """Yield (kind, start, pn_offset, end) for each coalesced long-header packet."""
    i = 0
    n = len(dgram)
    while i < n:
        b0 = dgram[i]
        if not (b0 & 0x80):
            return
        ptype = (b0 & 0x30) >> 4
        j = i + 1
        if j + 4 > n:
            return
        version = struct.unpack(">I", dgram[j:j + 4])[0]
        j += 4
        if version == 0:
            return
        dcil = dgram[j]; j += 1
        dcid = dgram[j:j + dcil]; j += dcil
        scil = dgram[j]; j += 1
        scid = dgram[j:j + scil]; j += scil
        if ptype == 3:      # Retry
            yield ("Retry", i, None, n, dcid, scid)
            return
        if ptype == 0:      # Initial has a token
            tl, j = read_varint(dgram, j)
            j += tl
        length, j = read_varint(dgram, j)
        pn_off = j
        end = pn_off + length
        kind = {0: "Initial", 1: "0-RTT", 2: "Handshake"}.get(ptype, str(ptype))
        yield (kind, i, pn_off, end, dcid, scid)
        if end <= i:
            return
        i = end


def decrypt_initial(dgram, start, pn_off, end, keys):
    """Return (plaintext_payload, pn, first_byte)."""
    sample = dgram[pn_off + 4:pn_off + 4 + 16]
    if len(sample) < 16:
        return None, None, None
    mask = aes_ecb_block(keys["hp"], sample)
    b0 = dgram[start] ^ (mask[0] & 0x0F)
    pn_len = (b0 & 0x03) + 1
    pn_bytes = bytes(dgram[pn_off + k] ^ mask[1 + k] for k in range(pn_len))
    pn = int.from_bytes(pn_bytes, "big")

    body = dgram[pn_off + pn_len:end]
    if len(body) < 16:
        return None, None, None
    ct, _tag = body[:-16], body[-16:]

    nonce = bytearray(keys["iv"])
    pnb = pn.to_bytes(12, "big")
    for k in range(12):
        nonce[k] ^= pnb[k]
    counter_block = bytes(nonce) + struct.pack(">I", 2)
    pt = aes_ctr(keys["key"], counter_block, ct)
    return pt, pn, b0


FRAME_NAMES = {0x00: "PADDING", 0x01: "PING", 0x02: "ACK", 0x03: "ACK_ECN",
               0x06: "CRYPTO", 0x1c: "CONNECTION_CLOSE", 0x1d: "CONNECTION_CLOSE_APP"}


def parse_frames(pt):
    """Return list of frames; CRYPTO frames carry (offset, data)."""
    out = []
    i = 0
    n = len(pt)
    while i < n:
        t = pt[i]
        if t == 0x00:
            j = i
            while j < n and pt[j] == 0:
                j += 1
            out.append({"type": "PADDING", "bytes": j - i})
            i = j
            continue
        if t == 0x01:
            out.append({"type": "PING"}); i += 1; continue
        if t in (0x02, 0x03):
            i += 1
            largest, i = read_varint(pt, i)
            delay, i = read_varint(pt, i)
            cnt, i = read_varint(pt, i)
            first, i = read_varint(pt, i)
            for _ in range(cnt):
                g, i = read_varint(pt, i)
                r, i = read_varint(pt, i)
            if t == 0x03:
                for _ in range(3):
                    _v, i = read_varint(pt, i)
            out.append({"type": "ACK", "largest": largest})
            continue
        if t == 0x06:
            i += 1
            off, i = read_varint(pt, i)
            ln, i = read_varint(pt, i)
            data = pt[i:i + ln]
            i += ln
            out.append({"type": "CRYPTO", "offset": off, "length": ln, "data": data})
            continue
        if t in (0x1c, 0x1d):
            i += 1
            code, i = read_varint(pt, i)
            if t == 0x1c:
                _ft, i = read_varint(pt, i)
            rl, i = read_varint(pt, i)
            reason = pt[i:i + rl]; i += rl
            out.append({"type": "CONNECTION_CLOSE", "code": code,
                        "reason": reason.decode("utf-8", "replace")})
            continue
        out.append({"type": "unknown-0x%02x" % t, "at": i})
        break
    return out


# ------------------------------------------------------ TLS ClientHello parse
EXT_NAMES = {
    0: "server_name", 5: "status_request", 10: "supported_groups",
    13: "signature_algorithms", 16: "ALPN", 18: "SCT", 21: "padding",
    22: "encrypt_then_mac", 23: "extended_master_secret",
    27: "compress_certificate", 35: "session_ticket", 41: "pre_shared_key",
    42: "early_data", 43: "supported_versions", 44: "cookie",
    45: "psk_key_exchange_modes", 47: "certificate_authorities",
    50: "signature_algorithms_cert", 51: "key_share",
    57: "quic_transport_parameters", 0xff01: "renegotiation_info",
}


def parse_client_hello(msg):
    """msg = full handshake message (type 0x01 + 3-byte len + body)."""
    assert msg[0] == 0x01, "not a ClientHello"
    total = int.from_bytes(msg[1:4], "big")
    b = msg[4:4 + total]
    i = 0
    i += 2                       # legacy_version
    i += 32                      # random
    sid_len = b[i]; i += 1 + sid_len
    cs_len = int.from_bytes(b[i:i + 2], "big"); i += 2 + cs_len
    comp_len = b[i]; i += 1 + comp_len
    ext_total = int.from_bytes(b[i:i + 2], "big"); i += 2
    end = i + ext_total
    exts = []
    while i < end:
        et = int.from_bytes(b[i:i + 2], "big")
        el = int.from_bytes(b[i + 2:i + 4], "big")
        body = b[i + 4:i + 4 + el]
        e = {"type": et, "name": EXT_NAMES.get(et, "ext-%d" % et),
             "len": el, "wire_len": el + 4}
        if et == 51:  # key_share
            kl = int.from_bytes(body[0:2], "big")
            shares, k = [], 2
            while k < 2 + kl:
                grp = int.from_bytes(body[k:k + 2], "big")
                sl = int.from_bytes(body[k + 2:k + 4], "big")
                shares.append({"group": grp, "key_bytes": sl, "entry_wire": sl + 4})
                k += 4 + sl
            e["shares"] = shares
        exts.append(e)
        i += 4 + el
    return {
        "msg_wire_len": total + 4,
        "body_len": total,
        "cipher_suites_bytes": cs_len,
        "extensions_total_wire": ext_total + 2,
        "extensions": exts,
    }


def parse_server_hello(msg):
    assert msg[0] == 0x02
    total = int.from_bytes(msg[1:4], "big")
    b = msg[4:4 + total]
    i = 2 + 32
    sid_len = b[i]; i += 1 + sid_len
    i += 2 + 1                   # cipher suite + compression
    ext_total = int.from_bytes(b[i:i + 2], "big"); i += 2
    end = i + ext_total
    exts = []
    while i < end:
        et = int.from_bytes(b[i:i + 2], "big")
        el = int.from_bytes(b[i + 2:i + 4], "big")
        body = b[i + 4:i + 4 + el]
        e = {"type": et, "name": EXT_NAMES.get(et, "ext-%d" % et), "wire_len": el + 4}
        if et == 51 and el >= 4:
            e["group"] = int.from_bytes(body[0:2], "big")
            e["key_bytes"] = int.from_bytes(body[2:4], "big")
        exts.append(e)
        i += 4 + el
    return {"msg_wire_len": total + 4, "extensions": exts}


# ------------------------------------------------------------------- relay
class RawRelay(object):
    def __init__(self, host, port=443):
        infos = socket.getaddrinfo(host, port, 0, socket.SOCK_DGRAM)
        v4 = [i for i in infos if i[0] == socket.AF_INET]
        pick = (v4 or infos)[0]
        self.family, self.upstream = pick[0], pick[4]
        self.local = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.local.bind(("127.0.0.1", 0))
        self.local.settimeout(0.3)
        self.port = self.local.getsockname()[1]
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


def capture(host, group, alpn="h3", timeout=25):
    r = RawRelay(host)
    r.start()
    time.sleep(0.2)
    try:
        p = subprocess.run(
            ["openssl", "s_client", "-quic", "-connect", "127.0.0.1:%d" % r.port,
             "-servername", host, "-alpn", alpn, "-groups", group, "-brief"],
            input=b"", capture_output=True, timeout=timeout)
        txt = (p.stdout + p.stderr).decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        txt = "TIMEOUT"
    time.sleep(0.4)
    r.shutdown()
    return r.dgrams, txt


def analyse(dgrams):
    """Decrypt client + server Initials, reassemble the CRYPTO streams."""
    odcid = None
    for d, buf in dgrams:
        if d != "C2S":
            continue
        for kind, s, pn_off, end, dcid, scid in iter_long_packets(buf):
            if kind == "Initial":
                odcid = dcid
                break
        if odcid is not None:
            break
    if odcid is None:
        return None
    keys = initial_keys(odcid)

    streams = {"C2S": {}, "S2C": {}}
    pkt_rows = []
    saw_retry = False
    for d, buf in dgrams:
        side = "client" if d == "C2S" else "server"
        for kind, s, pn_off, end, dcid, scid in iter_long_packets(buf):
            if kind == "Retry":
                saw_retry = True
                continue
            if kind != "Initial":
                continue
            try:
                pt, pn, b0 = decrypt_initial(buf, s, pn_off, end, keys[side])
            except Exception:
                continue
            if pt is None:
                continue
            frames = parse_frames(pt)
            crypto = [f for f in frames if f["type"] == "CRYPTO"]
            for f in crypto:
                streams[d][f["offset"]] = f["data"]
            pkt_rows.append({
                "dir": d, "pn": pn, "packet_bytes": end - s,
                "udp_bytes": len(buf),
                "crypto_frames": [{"offset": f["offset"], "length": f["length"]}
                                  for f in crypto],
                "crypto_total": sum(f["length"] for f in crypto),
                "padding": sum(f.get("bytes", 0) for f in frames
                               if f["type"] == "PADDING"),
                "frame_types": [f["type"] for f in frames],
            })

    def reassemble(m):
        if not m:
            return b""
        out = bytearray()
        for off in sorted(m):
            if off > len(out):
                break
            out[off:off + len(m[off])] = m[off]
        return bytes(out)

    ch_raw = reassemble(streams["C2S"])
    sh_raw = reassemble(streams["S2C"])
    res = {"odcid_len": len(odcid), "retry": saw_retry, "packets": pkt_rows,
           "clienthello_stream_bytes": len(ch_raw),
           "serverhello_stream_bytes": len(sh_raw)}
    if ch_raw and ch_raw[0] == 0x01:
        res["clienthello"] = parse_client_hello(ch_raw)
    if sh_raw and sh_raw[0] == 0x02:
        res["serverhello"] = parse_server_hello(sh_raw)
    return res


def main():
    _harden_console()
    print("=" * 78)
    print("E4 - decrypt real QUIC Initial packets, measure the ClientHello")
    print("=" * 78)
    hosts = os.environ.get("E4_HOSTS", "cloudflare.com,www.google.com").split(",")
    groups = os.environ.get("E4_GROUPS",
                            "x25519,secp256r1,X25519MLKEM768,MLKEM512,MLKEM768,MLKEM1024").split(",")
    out = {}
    print("")
    print("%-16s %-18s %6s %8s %8s %9s %s" %
          ("host", "group", "pkts", "CH wire", "keyshare", "CH-share", "quic_tp"))
    print("-" * 90)
    for host in hosts:
        for g in groups:
            try:
                dg, txt = capture(host, g)
                a = analyse(dg)
            except Exception as e:
                print("%-16s %-18s  EXC %s" % (host, g, str(e)[:40]))
                continue
            if not a:
                print("%-16s %-18s  no Initial captured" % (host, g))
                continue
            a["established"] = "CONNECTION ESTABLISHED" in txt
            out["%s/%s" % (host, g)] = a
            ch = a.get("clienthello")
            if not ch:
                print("%-16s %-18s  CH not recovered (%d bytes)" %
                      (host, g, a["clienthello_stream_bytes"]))
                continue
            ks = next((e for e in ch["extensions"] if e["type"] == 51), None)
            share_bytes = sum(s["key_bytes"] for s in ks.get("shares", [])) if ks else 0
            qtp = next((e for e in ch["extensions"] if e["type"] == 57), None)
            n_client_init = sum(1 for p in a["packets"] if p["dir"] == "C2S")
            print("%-16s %-18s %6d %8d %8d %9d %s" %
                  (host, g, n_client_init, ch["msg_wire_len"], share_bytes,
                   ch["msg_wire_len"] - share_bytes,
                   (str(qtp["wire_len"]) + "B") if qtp else "-"))
    path = os.path.join(RESULTS, "e4_quic_clienthello.json")

    def enc(o):
        if isinstance(o, bytes):
            return o.hex()
        raise TypeError
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False, default=enc)
    print("")
    print("saved: %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
