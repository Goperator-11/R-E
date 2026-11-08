import argparse
import os
import signal
import socket
import struct
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from afec import (AdaptiveFecController, FecConfig,
                  choose_block_size)
from afec.estimator import CongestionDetector, LossEstimator
from afec.rs import RSErasureCode

MAGIC = b"\xaf\xec"
HDR = 8
T_DATA = 0
T_BLOCK = 3
T_FEEDBACK = 5
R_MAX = 32


def _harden():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


def pack(kind, bid, index, count, payload):
    return (MAGIC + bytes([kind, bid & 0xFF, index & 0xFF, count & 0xFF])
            + struct.pack(">H", len(payload)) + payload)


def unpack(buf):
    if len(buf) < HDR or buf[0:2] != MAGIC:
        return None
    ln = struct.unpack(">H", buf[6:8])[0]
    return buf[2], buf[3], buf[4], buf[5], buf[HDR:HDR + ln]


class DataTx(object):
    def __init__(self, listen, peer, policy, cfg, stats_path, static_ratio,
                 rtt_ms):
        self.sock_in = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_in.bind(listen)
        self.sock_in.settimeout(0.001)
        self.sock_out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_out.settimeout(0.001)
        self.peer = peer
        self.policy = policy
        self.cfg = cfg
        self.static_ratio = static_ratio
        self.stats_path = stats_path
        self.k = choose_block_size(cfg)
        self.codec = RSErasureCode(self.k, R_MAX)
        self.ctrl = None
        if policy == "adaptive":
            self.ctrl = AdaptiveFecController(
                cfg, LossEstimator(p_init=0.005, z=cfg.risk_z),
                CongestionDetector())
            self.ctrl.cong.observe_rtt(rtt_ms)
        self.stop = threading.Event()
        self.client = None
        self.bid = 0
        self.buf = []
        self.sent_r = {}
        self.last = time.perf_counter()
        self.stats = {"blocks": 0, "originals": 0, "repairs": 0,
                      "r_sum": 0, "encode_ms": 0.0, "feedback": 0,
                      "tail_blocks": 0}

    def _r_for_block(self):
        if self.policy == "none":
            return 0
        if self.policy == "static":
            return max(1, int(round(self.k * self.static_ratio)))
        d = self.ctrl.next_block()
        return min(d.r, R_MAX)

    def _close_block(self):
        if not self.buf:
            return
        payloads = self.buf
        self.buf = []
        bid = self.bid
        self.bid = (self.bid + 1) & 0xFF
        k = len(payloads)
        if k < self.k:
            self.stats["tail_blocks"] += 1
            return
        r = self._r_for_block()
        self.sent_r[bid] = r
        if len(self.sent_r) > 512:
            for key in list(self.sent_r)[:256]:
                if key != bid:
                    del self.sent_r[key]
        self.stats["blocks"] += 1
        self.stats["r_sum"] += r
        if r <= 0:
            return
        framed = [struct.pack(">H", len(pp)) + pp for pp in payloads]
        size = max(len(f) for f in framed)
        padded = [f.ljust(size, b"\x00") for f in framed]
        t0 = time.perf_counter()
        repairs = self.codec.encode(padded)[:r]
        self.stats["encode_ms"] += (time.perf_counter() - t0) * 1000.0
        for j, rep in enumerate(repairs):
            self.sock_out.sendto(pack(T_BLOCK, bid, k + j, k, rep), self.peer)
            self.stats["repairs"] += 1

    def _from_client(self):
        while not self.stop.is_set():
            try:
                d, addr = self.sock_in.recvfrom(65535)
            except socket.timeout:
                if self.buf and (time.perf_counter() - self.last) > 0.25:
                    self._close_block()
                continue
            except OSError:
                break
            self.client = addr
            idx = len(self.buf)
            self.sock_out.sendto(pack(T_BLOCK, self.bid, idx, self.k, d), self.peer)
            self.stats["originals"] += 1
            self.buf.append(d)
            self.last = time.perf_counter()
            if len(self.buf) >= self.k:
                self._close_block()

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
            kind, bid, index, count, payload = u
            if kind == T_FEEDBACK:
                self.stats["feedback"] += 1
                if self.ctrl is not None and payload:
                    k = payload[0]
                    bits = payload[1:]
                    r = self.sent_r.get(bid, 0)
                    mask = []
                    for i in range(k + r):
                        got = ((bits[i >> 3] >> (i & 7)) & 1
                               if (i >> 3) < len(bits) else 0)
                        mask.append(not got)
                    self.ctrl.on_feedback(mask)
                continue
            if self.client:
                try:
                    self.sock_in.sendto(payload, self.client)
                except OSError:
                    pass

    def run(self):
        for t in (threading.Thread(target=self._from_client, daemon=True),
                  threading.Thread(target=self._from_peer, daemon=True)):
            t.start()
        try:
            while not self.stop.is_set():
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
        self._dump()

    def _snapshot_estimator(self):
        if self.ctrl is None:
            return
        e = self.ctrl.loss
        self.stats["est_p"] = round(e.p, 5)
        self.stats["est_p_safe"] = round(e.p_safe, 5)
        self.stats["est_burst"] = round(e.burst, 3)
        self.stats["est_n_eff"] = round(e.n_eff, 1)
        self.stats["est_se"] = round(e.se, 5)
        d = self.ctrl.last_decision
        if d is not None:
            self.stats["last_r"] = d.r
            self.stats["last_k"] = d.k
            self.stats["last_p_fail"] = round(d.p_fail, 6)
            self.stats["last_t_recover"] = round(d.t_recover_ms, 2)

    def _dump(self):
        if self.stats_path:
            try:
                self._snapshot_estimator()
            except Exception:
                pass
            self.stats["mean_r"] = (self.stats["r_sum"] /
                                    max(self.stats["blocks"], 1))
            with open(self.stats_path, "w") as f:
                f.write(repr(self.stats))


class DataRx(object):
    def __init__(self, listen, target, stats_path):
        self.sock_in = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_in.bind(listen)
        self.sock_in.settimeout(0.001)
        self.sock_srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_srv.settimeout(0.001)
        self.target = target
        self.stats_path = stats_path
        self.stop = threading.Event()
        self.peer = None
        self.blocks = {}
        self.seq = 0
        self.codecs = {}
        self.stats = {"delivered": 0, "recovered": 0, "decode_fail": 0,
                      "blocks_seen": 0, "decode_ms": 0.0, "block_id_wraps": 0,
                      "feedback_sent": 0, "feedback_late": 0, "seq_blocks": 0,
                      "recover_malformed": 0}

    def _codec(self, k):
        c = self.codecs.get(k)
        if c is None:
            c = self.codecs[k] = RSErasureCode(k, R_MAX)
        return c

    BLOCK_TTL_S = 2.0
    STRAGGLER_GRACE_S = 0.15
    LAST_BLOCK_TIMEOUT_S = 3.0

    def _blk(self, bid, k):
        now = time.perf_counter()
        b = self.blocks.get(bid)
        if b is not None and ((now - b["t"]) > self.BLOCK_TTL_S or b["k"] != k):
            b = None
            self.stats["block_id_wraps"] += 1
        if b is None:
            b = self.blocks[bid] = {"k": k, "sym": {}, "delivered": set(),
                                    "done": False, "reported": False, "t": now,
                                    "seq": self.seq, "last": now}
            self.seq += 1
            self.stats["blocks_seen"] += 1
            if len(self.blocks) > 300:
                for key in list(self.blocks)[:150]:
                    if key != bid:
                        del self.blocks[key]
        return b

    def _deliver(self, b, i, payload):
        if i in b["delivered"]:
            return
        b["delivered"].add(i)
        self.stats["delivered"] += 1
        try:
            self.sock_srv.sendto(payload, self.target)
        except OSError:
            pass

    def _feedback(self, bid, b):
        if not self.peer or b["reported"]:
            return
        b["reported"] = True
        k = b["k"]
        span = k + R_MAX
        bits = bytearray((span + 7) // 8)
        for i in b["sym"]:
            if i < span:
                bits[i >> 3] |= 1 << (i & 7)
        payload = bytes([k]) + bytes(bits)
        try:
            self.sock_in.sendto(pack(T_FEEDBACK, bid, 0, k, payload), self.peer)
            self.stats["feedback_sent"] += 1
        except OSError:
            pass

    def _sweep(self):
        now = time.perf_counter()
        newest = self.seq - 1
        for bid, b in list(self.blocks.items()):
            if b["reported"]:
                continue
            sender_moved_on = b["seq"] < newest
            quiet = (now - b["last"]) > self.STRAGGLER_GRACE_S
            stale = (now - b["t"]) > self.LAST_BLOCK_TIMEOUT_S
            if (sender_moved_on and quiet) or stale:
                self._feedback(bid, b)
                self.stats["feedback_late"] += 1

    def _try_decode(self, bid, b):
        k = b["k"]
        if b["done"] or len(b["sym"]) < k:
            return
        missing = [i for i in range(k) if i not in b["sym"]]
        b["done"] = True
        if not missing:
            return
        rep_sizes = [len(v) for i, v in b["sym"].items() if i >= k]
        if not rep_sizes:
            return
        size = max(rep_sizes)
        symbols = {}
        for i, v in b["sym"].items():
            if i >= k:
                symbols[i] = v.ljust(size, b"\x00")
            else:
                symbols[i] = (struct.pack(">H", len(v)) + v).ljust(size, b"\x00")
        t0 = time.perf_counter()
        try:
            out = self._codec(k).decode(symbols)
        except Exception:
            self.stats["decode_fail"] += 1
            return
        self.stats["decode_ms"] += (time.perf_counter() - t0) * 1000.0
        for i in missing:
            sym = out[i]
            ln = struct.unpack(">H", sym[:2])[0] if len(sym) >= 2 else 0
            if ln == 0 or 2 + ln > len(sym):
                self.stats["recover_malformed"] += 1
                continue
            self.stats["recovered"] += 1
            self._deliver(b, i, sym[2:2 + ln])

    def _from_peer(self):
        while not self.stop.is_set():
            try:
                d, addr = self.sock_in.recvfrom(65535)
            except socket.timeout:
                self._sweep()
                continue
            except OSError:
                break
            self.peer = addr
            u = unpack(d)
            if not u:
                continue
            kind, bid, index, count, payload = u
            if kind != T_BLOCK:
                try:
                    self.sock_srv.sendto(payload, self.target)
                except OSError:
                    pass
                continue
            b = self._blk(bid, count)
            b["sym"][index] = payload
            b["last"] = time.perf_counter()
            if index < count:
                self._deliver(b, index, payload)
            self._try_decode(bid, b)

    def _from_server(self):
        while not self.stop.is_set():
            try:
                d, _ = self.sock_srv.recvfrom(65535)
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
        for t in (threading.Thread(target=self._from_peer, daemon=True),
                  threading.Thread(target=self._from_server, daemon=True)):
            t.start()
        try:
            while not self.stop.is_set():
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
        if self.stats_path:
            with open(self.stats_path, "w") as f:
                f.write(repr(self.stats))


def install_dump_on_term(obj):
    def handler(signum, frame):
        try:
            if getattr(obj, "stats_path", ""):
                st = dict(obj.stats)
                if isinstance(obj, DataTx):
                    st["mean_r"] = st["r_sum"] / max(st["blocks"], 1)
                with open(obj.stats_path, "w") as f:
                    f.write(repr(st))
        finally:
            os._exit(0)
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, handler)
        except Exception:
            pass


def addr(s):
    h, p = s.rsplit(":", 1)
    return (h, int(p))


def main():
    _harden()
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", choices=("tx", "rx"), required=True)
    ap.add_argument("--listen", required=True)
    ap.add_argument("--peer", default="")
    ap.add_argument("--target", default="")
    ap.add_argument("--policy", default="adaptive",
                    choices=("none", "static", "adaptive"))
    ap.add_argument("--static-ratio", type=float, default=0.25)
    ap.add_argument("--rate-mbps", type=float, default=20.0)
    ap.add_argument("--budget-ms", type=float, default=20.0)
    ap.add_argument("--symbol-bytes", type=int, default=1100)
    ap.add_argument("--rtt-ms", type=float, default=20.0)
    ap.add_argument("--stats", default="")
    a = ap.parse_args()
    cfg = FecConfig(rate_bps=a.rate_mbps * 1e6, delay_budget_ms=a.budget_ms,
                    symbol_bytes=a.symbol_bytes)
    if a.role == "tx":
        obj = DataTx(addr(a.listen), addr(a.peer), a.policy, cfg, a.stats,
                     a.static_ratio, a.rtt_ms)
    else:
        obj = DataRx(addr(a.listen), addr(a.target), a.stats)
    install_dump_on_term(obj)
    obj.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
