# -*- coding: utf-8 -*-
"""
FEC shim pair for the QUIC testbed - a REAL forward-erasure-correction tunnel.

    qclient -> shim tx -> [ veth + netem ] -> shim rx -> qserver

The tx side watches for the client's FIRST Initial flight (the ClientHello,
which ML-KEM splits across two 1200-byte datagrams) and, when FEC is enabled,
appends one **real XOR parity packet** over that flight.  The parity packet is
a genuine extra datagram on the wire: it is exposed to netem loss exactly like
the originals are.

The rx side forwards every original the moment it arrives (so protection costs
no latency on the happy path) and, as soon as it holds k-1 originals plus the
parity, reconstructs the missing one by XOR and forwards it.  A late duplicate
is harmless - QUIC dedupes by packet number, which is what a real FEC-enabled
stack would rely on too.

Both arms (fec on / off) run the same code path and the same tx-side flight
buffering delay, so the comparison is not tilted by the shim itself.

Wire format (shim to shim, present in BOTH arms):
    0-1  magic 0xAF 0xEC
    2    type   0 = data, 1 = parity
    3    flight id, 0 = passthrough, 1..255 = protected flight (rotates)
    4    index within the flight
    5    count of originals in the flight
    6-7  payload length (big endian)
    8..  payload

🩸 The flight id is NOT a boolean.  It was, in the first version, and the rx
side then carried its `delivered` set across connections: from the second
handshake onward the Initial packets of every new connection were treated as
duplicates of the first one's and silently dropped, so every trial paid a full
PTO.  It showed up as a suspiciously constant 222 ms (= 200 ms PTO + 22 ms RTT)
on every arm, which is what caught it.

Standard library only.  ASCII output.
"""
import argparse
import json
import os
import signal
import socket
import struct
import sys
import threading
import time

MAGIC = b"\xaf\xec"
HDR = 8
T_DATA = 0
T_PARITY = 1


def _harden():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


def pack(kind, flight, index, count, payload):
    return (MAGIC + bytes([kind, flight, index, count])
            + struct.pack(">H", len(payload)) + payload)


def unpack(buf):
    if len(buf) < HDR or buf[0:2] != MAGIC:
        return None
    kind, flight, index, count = buf[2], buf[3], buf[4], buf[5]
    ln = struct.unpack(">H", buf[6:8])[0]
    return kind, flight, index, count, buf[HDR:HDR + ln]


def is_initial(d):
    """QUIC long header, type Initial (RFC 9000 17.2.2). Header bits 0-1 of the
    type field are visible; header protection only covers the low 4 bits."""
    return len(d) > 5 and (d[0] & 0x80) and (d[0] & 0x40) and ((d[0] & 0x30) >> 4) == 0


def xor_into(acc, data):
    n = max(len(acc), len(data))
    acc = acc.ljust(n, b"\x00")
    data = data.ljust(n, b"\x00")
    return bytes(a ^ b for a, b in zip(acc, data))


# ------------------------------------------------------------------ tx side
class ShimTx(object):
    """Listens for the local QUIC client, tunnels to the rx shim."""

    def __init__(self, listen, peer, fec, flight_ms, stats_path,
                 dup_initial=0):
        self.sock_in = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_in.bind(listen)
        self.sock_in.settimeout(0.001)
        self.sock_out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_out.settimeout(0.001)
        self.peer = peer
        self.fec = fec
        self.dup_initial = int(dup_initial)
        self.flight_ms = flight_ms
        self.stats_path = stats_path
        self.stop = threading.Event()
        self.client = None
        self.state = {}          # client addr -> {'buf', 'done', 't', 'fid'}
        self._next_fid = 0
        # flight_sizes: how many Initial datagrams the ClientHello occupied.
        # This is the direct MTU-1500 test of the split hypothesis: x25519
        # should be 1, X25519MLKEM768 should be 2.
        self.stats = {"flights": 0, "parity_sent": 0, "dup_sent": 0,
                      "c2s": 0, "s2c": 0,
                      "flight_sizes": {}}

    def _new_state(self):
        self._next_fid = (self._next_fid % 255) + 1
        return {"buf": [], "done": False, "t": 0.0, "fid": self._next_fid}

    def _flush(self, addr):
        st = self.state.get(addr)
        if not st or st["done"] or not st["buf"]:
            return
        buf = st["buf"]
        fid = st["fid"]
        st["buf"] = []
        st["done"] = True
        k = len(buf)
        self.stats["flights"] += 1
        key = str(k)
        self.stats["flight_sizes"][key] = self.stats["flight_sizes"].get(key, 0) + 1
        for i, d in enumerate(buf):
            self.sock_out.sendto(pack(T_DATA, fid, i, k, d), self.peer)
        if self.fec and k >= 1:
            acc = b""
            for d in buf:
                acc = xor_into(acc, d)
            self.sock_out.sendto(pack(T_PARITY, fid, k, k, acc), self.peer)
            self.stats["parity_sent"] += 1

    def _from_client(self):
        while not self.stop.is_set():
            try:
                d, addr = self.sock_in.recvfrom(65535)
            except socket.timeout:
                for a in list(self.state):
                    st = self.state[a]
                    if (st["buf"] and not st["done"]
                            and (time.perf_counter() - st["t"]) * 1000 >= self.flight_ms):
                        self._flush(a)
                continue
            except OSError:
                break
            self.client = addr
            st = self.state.get(addr)
            if st is None:
                st = self.state[addr] = self._new_state()
            self.stats["c2s"] += 1
            if not st["done"] and is_initial(d):
                st["buf"].append(d)
                st["t"] = time.perf_counter()
                # 🔬 증폭 예산 실험용 모드 (E20).
                #
                # 우리 패리티는 rx 심이 흡수하고 서버로 안 넘긴다. 그래서
                # 서버의 QUIC 스택이 보는 바이트가 안 늘고, RFC 9000 8.1 의
                # 3배 예산도 그대로다 - 즉 "핸드셰이크 FEC 가 증폭 예산을
                # 키운다"는 가설은 **우리 구현으로는 성립 자체가 불가**하다.
                #
                # 메커니즘 자체가 참인지 보려면 서버가 **연결에 귀속시켜 셀 수
                # 있는** 바이트를 실제로 더 보내야 한다. XOR 패리티는 QUIC
                # 계층에서 쓰레기라 귀속이 안 될 수 있으므로, 대신 Initial
                # 데이터그램을 **그대로 복제**한다. 유효한 DCID 를 가진 정상
                # 패킷이라 서버가 연결에 귀속시키고, 패킷 번호가 중복이라
                # 폐기하지만 바이트는 센다. 이건 동시에 **반복부호(r=1)**,
                # 즉 가장 단순한 FEC 이기도 하다.
                for _ in range(self.dup_initial):
                    self.sock_out.sendto(pack(T_DATA, 0, 0, 1, d), self.peer)
                    self.stats["dup_sent"] += 1
                continue
            if st["buf"] and not st["done"]:
                self._flush(addr)
            self.sock_out.sendto(pack(T_DATA, 0, 0, 1, d), self.peer)

    def _from_peer(self):
        while not self.stop.is_set():
            try:
                d, _ = self.sock_out.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            u = unpack(d)
            if not u:
                continue
            _kind, _flight, _idx, _cnt, payload = u
            self.stats["s2c"] += 1
            if self.client:
                try:
                    self.sock_in.sendto(payload, self.client)
                except OSError:
                    pass

    def run(self):
        t1 = threading.Thread(target=self._from_client, daemon=True)
        t2 = threading.Thread(target=self._from_peer, daemon=True)
        t1.start(); t2.start()
        try:
            while not self.stop.is_set():
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
        self._dump()

    def _dump(self):
        if self.stats_path:
            with open(self.stats_path, "w") as f:
                f.write(repr(self.stats))
        self._dump_trace()

    def _dump_trace(self):
        if not getattr(self, "trace_path", ""):
            return
        try:
            with open(self.trace_path, "w") as f:
                json.dump({"stats": self.stats, "events": self.trace}, f)
        except Exception:
            pass


# ------------------------------------------------------------------ rx side
class ShimRx(object):
    """Receives the tunnel, recovers, delivers to the local QUIC server."""

    def __init__(self, listen, target, stats_path, trace_path=""):
        # 🔬 E20 검증용 바이트 타임라인.
        # rx 심은 서버 바로 앞에 있으므로 여기서 재면 서버의 QUIC 스택이
        # 실제로 '받은 바이트'와 '보낸 바이트'가 그대로 보인다. RFC 9000
        # 8.1 의 3배 예산은 구현을 안 뜯어도 이 두 수열로 드러난다.
        self.trace_path = trace_path
        self.trace = []          # (t_ms, 'to_srv'|'from_srv', nbytes)
        self.t0 = time.perf_counter()
        self.sock_in = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_in.bind(listen)
        self.sock_in.settimeout(0.001)
        self.sock_srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_srv.settimeout(0.001)
        self.target = target
        self.stats_path = stats_path
        self.stop = threading.Event()
        self.peer = None
        # per-flight state, keyed by the flight id the tx shim stamps in.
        # Keeping this global across connections is exactly the bug that
        # made every trial after the first one pay a PTO.
        self.flights = {}
        self.stats = {"recovered": 0, "delivered": 0, "parity_rx": 0,
                      "unrecoverable_seen": 0, "flights": 0,
                      "flight_id_wraps": 0,
                      "srv_rx_bytes": 0, "srv_tx_bytes": 0,
                      "srv_rx_dgrams": 0, "srv_tx_dgrams": 0}

    def _mark(self, kind, n):
        if kind == "to_srv":
            self.stats["srv_rx_bytes"] += n
            self.stats["srv_rx_dgrams"] += 1
        else:
            self.stats["srv_tx_bytes"] += n
            self.stats["srv_tx_dgrams"] += 1
        if self.trace_path and len(self.trace) < 4000:
            self.trace.append(((time.perf_counter() - self.t0) * 1000.0,
                               kind, n))

    # 🩸 The flight id is one byte, so it wraps every 255 connections.  The
    # first version reused the stale entry on wrap, which made connections
    # 256+ look like duplicates and cost each of them a full PTO.  With
    # n=300 per arm that is 15% of trials - it showed up as p90 = 222 ms in
    # the NO-LOSS condition, which is impossible and is what gave it away.
    # A TTL separates reuses: consecutive uses of one id are >=255
    # connections apart (seconds), a live flight lasts milliseconds.
    FLIGHT_TTL_S = 1.0

    def _fl(self, fid):
        now = time.perf_counter()
        fl = self.flights.get(fid)
        if fl is not None and (now - fl["t"]) > self.FLIGHT_TTL_S:
            fl = None                        # stale: this is a new flight
            self.stats["flight_id_wraps"] += 1
        if fl is None:
            fl = self.flights[fid] = {"parts": {}, "parity": None,
                                      "count": 0, "delivered": set(), "t": now}
            self.stats["flights"] += 1
        return fl

    def _deliver(self, fl, idx, payload):
        if idx in fl["delivered"]:
            return
        fl["delivered"].add(idx)
        self.stats["delivered"] += 1
        try:
            self.sock_srv.sendto(payload, self.target)
            self._mark("to_srv", len(payload))
        except OSError:
            pass

    def _try_recover(self, fl):
        if fl["parity"] is None or not fl["count"]:
            return
        missing = [i for i in range(fl["count"]) if i not in fl["parts"]]
        if len(missing) != 1:
            if len(missing) > 1:
                self.stats["unrecoverable_seen"] += 1
            return
        # Reconstructed originals are absent from parts, which records physical
        # arrivals. A repeated parity must not count an already delivered repair.
        if missing[0] in fl["delivered"]:
            return
        acc = fl["parity"]
        for i, d in fl["parts"].items():
            acc = xor_into(acc, d)
        # the XOR was taken over zero-padded payloads; QUIC Initial datagrams
        # in a flight are the same size, so no length ambiguity in practice
        self.stats["recovered"] += 1
        self._deliver(fl, missing[0], acc)

    def _from_peer(self):
        while not self.stop.is_set():
            try:
                d, addr = self.sock_in.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            self.peer = addr
            u = unpack(d)
            if not u:
                continue
            kind, flight, index, count, payload = u
            if flight == 0:
                try:
                    self.sock_srv.sendto(payload, self.target)
                    self._mark("to_srv", len(payload))
                except OSError:
                    pass
                continue
            fl = self._fl(flight)
            fl["count"] = count
            if kind == T_PARITY:
                fl["parity"] = payload
                self.stats["parity_rx"] += 1
                self._try_recover(fl)
                continue
            fl["parts"][index] = payload
            self._deliver(fl, index, payload)  # forward at once, no added delay
            self._try_recover(fl)

    def _from_server(self):
        while not self.stop.is_set():
            try:
                d, _ = self.sock_srv.recvfrom(65535)
                self._mark("from_srv", len(d))
            except socket.timeout:
                continue
            except OSError:
                break
            if self.peer:
                try:
                    self.sock_in.sendto(pack(T_DATA, 0, 0, 1, d), self.peer)
                except OSError:
                    pass

    def run(self):
        t1 = threading.Thread(target=self._from_peer, daemon=True)
        t2 = threading.Thread(target=self._from_server, daemon=True)
        t1.start(); t2.start()
        try:
            while not self.stop.is_set():
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
        if self.stats_path:
            with open(self.stats_path, "w") as f:
                f.write(repr(self.stats))
        self._dump_trace()

    def _dump_trace(self):
        if not getattr(self, "trace_path", ""):
            return
        try:
            with open(self.trace_path, "w") as f:
                json.dump({"stats": self.stats, "events": self.trace}, f)
        except Exception:
            pass


def addr(s):
    h, p = s.rsplit(":", 1)
    return (h, int(p))


def install_dump_on_term(obj):
    """The orchestrator stops shims with SIGTERM; without this the stats file
    is never written and the recovery counters silently read as missing."""
    def handler(signum, frame):
        try:
            path = obj.stats_path
            if path:
                with open(path, "w") as f:
                    f.write(repr(obj.stats))
            # 🩸 트레이스도 여기서 안 쓰면 SIGTERM 으로 죽는 심의
            # 타임라인이 통째로 사라진다(stats 때와 같은 실수).
            obj._dump_trace()
        finally:
            os._exit(0)
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, handler)
        except Exception:
            pass


def main():
    _harden()
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", choices=("tx", "rx"), required=True)
    ap.add_argument("--listen", required=True)
    ap.add_argument("--peer", default="")
    ap.add_argument("--target", default="")
    ap.add_argument("--fec", action="store_true")
    ap.add_argument("--flight-ms", type=float, default=3.0)
    ap.add_argument("--dup-initial", type=int, default=0,
                    help="E20: 클라이언트 Initial 을 이 횟수만큼 복제해 "
                         "서버까지 실제로 보낸다(증폭 예산 메커니즘 시험)")
    ap.add_argument("--stats", default="")
    ap.add_argument("--trace", default="",
                    help="E20: rx 심에서 본 서버 송수신 바이트 타임라인 JSON")
    a = ap.parse_args()
    if a.role == "tx":
        obj = ShimTx(addr(a.listen), addr(a.peer), a.fec, a.flight_ms,
                     a.stats, a.dup_initial)
    else:
        obj = ShimRx(addr(a.listen), addr(a.target), a.stats, a.trace)
    install_dump_on_term(obj)
    obj.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
