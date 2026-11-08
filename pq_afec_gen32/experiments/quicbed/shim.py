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
    return len(d) > 5 and (d[0] & 0x80) and (d[0] & 0x40) and ((d[0] & 0x30) >> 4) == 0


def xor_into(acc, data):
    n = max(len(acc), len(data))
    acc = acc.ljust(n, b"\x00")
    data = data.ljust(n, b"\x00")
    return bytes(a ^ b for a, b in zip(acc, data))


class ShimTx(object):
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
        self.state = {}
        self._next_fid = 0
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


class ShimRx(object):
    def __init__(self, listen, target, stats_path, trace_path=""):
        self.trace_path = trace_path
        self.trace = []
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

    FLIGHT_TTL_S = 1.0

    def _fl(self, fid):
        now = time.perf_counter()
        fl = self.flights.get(fid)
        if fl is not None and (now - fl["t"]) > self.FLIGHT_TTL_S:
            fl = None
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
        if missing[0] in fl["delivered"]:
            return
        acc = fl["parity"]
        for i, d in fl["parts"].items():
            acc = xor_into(acc, d)
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
            self._deliver(fl, index, payload)
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
    def handler(signum, frame):
        try:
            path = obj.stats_path
            if path:
                with open(path, "w") as f:
                    f.write(repr(obj.stats))
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
