import argparse
import os
import socket
import struct
import sys
import time

SENTINEL = 0xFFFFFFFF


def _harden():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


def recv_main(a):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 32 * 1024 * 1024)
    except OSError:
        pass
    s.bind((a.bind, a.port))
    s.settimeout(a.idle)
    nbytes = (a.n + 7) // 8
    bitmap = bytearray(nbytes)
    got = 0
    dup = 0
    out_of_range = 0
    sentinels = 0
    first_t = None
    last_t = None
    with open(a.ready, "w") as f:
        f.write("ready\n")
    while True:
        try:
            data, _ = s.recvfrom(4096)
        except socket.timeout:
            break
        if len(data) < 4:
            continue
        seq = struct.unpack(">I", data[:4])[0]
        if seq == SENTINEL:
            sentinels += 1
            if sentinels >= 3:
                break
            continue
        if seq >= a.n:
            out_of_range += 1
            continue
        now = time.perf_counter()
        if first_t is None:
            first_t = now
        last_t = now
        b, bit = seq >> 3, seq & 7
        if bitmap[b] & (1 << bit):
            dup += 1
        else:
            bitmap[b] |= (1 << bit)
            got += 1
    s.close()
    with open(a.out, "wb") as f:
        f.write(bitmap)
    dur = (last_t - first_t) if (first_t and last_t) else 0.0
    sys.stdout.write("RECV n=%d got=%d dup=%d oor=%d dur=%.3f\n"
                     % (a.n, got, dup, out_of_range, dur))
    return 0


def send_main(a):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8 * 1024 * 1024)
    except OSError:
        pass
    dst = (a.host, a.port)
    pad = bytes(max(0, a.size - 4))
    interval = 1.0 / a.pps
    sent = 0
    errs = 0
    t0 = time.perf_counter()
    for i in range(a.n):
        pkt = struct.pack(">I", i) + pad
        while True:
            try:
                s.sendto(pkt, dst)
                sent += 1
                break
            except OSError as e:
                errs += 1
                if errs > a.n:
                    break
                time.sleep(0.0005)
        target = t0 + (i + 1) * interval
        now = time.perf_counter()
        gap = target - now
        if gap > 0.0015:
            time.sleep(gap - 0.0005)
        else:
            while time.perf_counter() < target:
                pass
    dur = time.perf_counter() - t0
    time.sleep(0.3)
    for _ in range(8):
        try:
            s.sendto(struct.pack(">I", SENTINEL) + pad, dst)
        except OSError:
            pass
        time.sleep(0.02)
    s.close()
    sys.stdout.write("SEND n=%d sent=%d errs=%d dur=%.3f pps=%.0f\n"
                     % (a.n, sent, errs, dur, sent / dur if dur else 0))
    return 0


def main():
    _harden()
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", choices=("send", "recv"), required=True)
    ap.add_argument("--host", default="10.9.0.2")
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=39001)
    ap.add_argument("--n", type=int, default=100000)
    ap.add_argument("--pps", type=float, default=10000.0)
    ap.add_argument("--size", type=int, default=1200)
    ap.add_argument("--out", default="/tmp/mask.bin")
    ap.add_argument("--ready", default="/tmp/recv.ready")
    ap.add_argument("--idle", type=float, default=3.0)
    a = ap.parse_args()
    return recv_main(a) if a.role == "recv" else send_main(a)


if __name__ == "__main__":
    sys.exit(main())
