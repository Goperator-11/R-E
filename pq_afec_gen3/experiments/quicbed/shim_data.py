# -*- coding: utf-8 -*-
"""
Data-phase adaptive FEC shim - the live version of the algorithm.

The handshake shim (shim.py) protects one flight with one XOR parity packet.
This one protects the *data* phase: it groups QUIC datagrams into blocks of K,
asks the project's real controller (afec.AdaptiveFecController) how many repair
symbols the current channel deserves, generates them with the project's real
Reed-Solomon coder (afec.rs), and puts them on the wire.  The receiving side
decodes and injects the recovered datagrams.

So the loop is closed with real code end to end:

    quic-go app --datagrams--> shim tx --[K originals + r RS repairs]-->
        netem --> shim rx --(RS decode)--> quic-go app

Feedback is real too: the rx shim reports, per block, which symbol indices it
actually received; the tx shim feeds that mask straight into the estimator,
which is exactly the ACK-derived signal the algorithm was designed around.

Wire format is the same 8-byte header as shim.py, with two extra kinds:
    kind 3 = block symbol (originals index 0..K-1, repairs index K..K+r-1)
    kind 5 = feedback (payload = block id + received bitmap)

Both sides build RSErasureCode(k, R_MAX) with the SAME fixed R_MAX so their
generator matrices agree; the sender simply uses the first r rows.  (afec/rs.py
builds its Cauchy matrix from r, so an r that changes per block would give the
two sides different matrices - this is the reason for the constant.)

Standard library + afec only.  ASCII output.
"""
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

from afec import (AdaptiveFecController, FecConfig,  # noqa: E402
                  choose_block_size)
from afec.estimator import CongestionDetector, LossEstimator   # noqa: E402
from afec.rs import RSErasureCode                              # noqa: E402

MAGIC = b"\xaf\xec"
HDR = 8
T_DATA = 0
T_BLOCK = 3
T_FEEDBACK = 5
R_MAX = 32          # both sides must agree; see module docstring


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


# --------------------------------------------------------------------- tx
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
            # ⚠️ Without an RTT sample the controller falls back to pto_ms()
            # = 999 ms for T_recover, i.e. it prices a data-phase loss like a
            # handshake stall and massively over-provisions.  The data phase
            # recovers in ~2*RTT, so seed the RTT the path actually has.
            self.ctrl.cong.observe_rtt(rtt_ms)
        self.stop = threading.Event()
        self.client = None
        self.bid = 0
        self.buf = []
        self.sent_r = {}          # block id -> r, so feedback can span K+r
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
            # partial tail block - not a real block, so do not let it into the
            # blocks/r_sum counters or it drags mean_r down
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
        # 🩸 심볼은 길이가 제각각이다(QUIC ACK 전용 패킷은 작고 DATAGRAM은 ~1150B).
        # 부호화하려면 길이를 맞춰야 하는데, 단순히 0으로 패딩하면 **복구했을 때
        # 원래 길이를 알 방법이 없다.** 그대로 내보내면 QUIC 패킷 뒤에 0바이트가
        # 붙어 AEAD 인증에 실패하고 수신측이 조용히 버린다 - 심은 "복구했다"고
        # 세는데 응용은 아무것도 못 받는 상태가 된다 (2026-08-18 실측:
        # uniform_p5/static 이 161개 복구했는데 서버 수신은 오히려 6개 감소).
        # 그래서 **길이 2바이트를 심볼 안에 넣어** 부호화한다. 소실 정정이
        # 길이 접두사까지 같이 복원하므로 복구 후 정확히 잘라낼 수 있다.
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
                    # The mask must span the whole transmitted block (K + r),
                    # exactly like sim.py feeds sampler.send(k + r) to the
                    # estimator.  Reporting only the K originals truncates any
                    # burst that ran into the repair symbols and biases the
                    # burst-length estimate short.  r is known here, not at
                    # the receiver, so we look it up by block id.
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
        """추정기 내부값을 통계에 남긴다. r 이 이상할 때 원인이 '추정'인지
        '비용식'인지 구분하려면 이게 있어야 한다 - 없어서 두 라운드를 추측으로
        썼다."""
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


# --------------------------------------------------------------------- rx
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

    # The block id is one byte and wraps every 256 blocks.  Reusing the stale
    # entry on wrap would mark every symbol of the new block as "already
    # delivered" - the same failure that cost shim.py a PTO per connection.
    # Blocks live for milliseconds and ids repeat seconds apart, so a TTL
    # separates them cleanly.
    BLOCK_TTL_S = 2.0
    STRAGGLER_GRACE_S = 0.15    # 다음 블록이 시작된 뒤 잔여 패킷 유예
    LAST_BLOCK_TIMEOUT_S = 3.0  # 뒤가 없는 마지막 블록용 절대 상한

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
        """Report EVERY index we saw, originals and repairs alike.

        🩸 Two bugs lived here.
        (1) Feedback used to be sent only from _try_decode, i.e. only for
            blocks that had enough symbols to decode.  Blocks that lost more
            than r symbols never reported at all, so the estimator saw a
            sample made only of survivors and drifted low - the same
            sample-selection bias the project already catalogued as defect 13.
            Now a timer reports unfinished blocks too.
        (2) The bitmap used to cover only the K originals, so a burst that ran
            into the repair symbols was truncated at the block boundary and
            the burst-length estimate came out short (defect 4, again).  The
            bitmap now spans K + R_MAX so the sender can rebuild the true
            K+r mask.
        """
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
        """Report blocks that never completed.

        🩸 첫 판은 "생성 후 0.2초가 지나면 보고"였는데 이게 훨씬 나쁜 편향을
        만들었다. 송신률 120pps에서 K=45 블록은 **채우는 데만 375ms**가 걸린다.
        0.2초에 보고하면 아직 보내지도 않은 심볼이 전부 '손실'로 잡혀
        추정 손실률이 47%까지 뛴다. 그러면 r_max를 다 써도 P_fail이 1에
        붙는 "가망 없음" 능선을 넘어 argmin이 r=0으로 무너지고 **보호가 통째로
        꺼진다**(실측: uniform_p5에서 적응형 r이 항상 0, 복구 0건).

        올바른 신호는 시간이 아니라 **송신자가 다음 블록으로 넘어갔다는 사실**
        이다. tx는 블록을 순서대로 닫으므로, 더 새 블록의 심볼이 보이면 이전
        블록은 전송이 끝난 것이다. 거기에 잔여 패킷이 들어올 유예만 준다.
        마지막 블록은 뒤가 없으므로 긴 절대 타임아웃으로 처리한다.
        """
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
        # 🩸 여기서 피드백을 보내면 안 된다.
        #
        # _try_decode 는 **K개 원본이 도착하는 순간** 발화하는데, 이중화 심볼은
        # 송신측이 블록을 닫은 **뒤에** 내보낸다. 그 시점에 보고하면 수신 심은
        # "원본 K개 받음, 이중화 r개 못 받음"이라고 말하게 되고, 송신 심은
        # **아직 보내지도 않은 이중화를 손실로** 집계한다 -> p_hat 이 r/(K+r)
        # 로 치솟아(실측 32%) 이중화가 상한에 붙는다.
        #
        # 앞서 스위퍼를 0.2초로 뒀을 때의 실패(아직 안 온 '원본'을 손실로 셈)와
        # **정확히 같은 뿌리의 반대편**이다: 수신측이 송신이 끝나기 전에 블록을
        # 보고하는 것. 그래서 두 관심사를 분리한다.
        #   - 복호: 가능해지는 즉시 (전달 지연을 줄여야 하므로)
        #   - 보고: 송신이 끝난 것이 확실해진 뒤 (_sweep 이 판정)
        if not missing:
            return
        # 이중화 심볼의 길이가 곧 이 블록의 부호화 단위 크기다(송신측이 그렇게
        # 맞췄다). 원본은 실제 길이 그대로 도착하므로, 복호 전에 송신측과 같은
        # [길이 2B][페이로드][0 패딩] 형식으로 되돌려 놓아야 한다.
        rep_sizes = [len(v) for i, v in b["sym"].items() if i >= k]
        if not rep_sizes:
            return                      # 이중화가 없으면 애초에 복구 불가
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
                # 길이 접두사가 말이 안 되면 복구가 틀린 것이다. 그냥 내보내면
                # 수신측이 버리고 우리만 "복구했다"고 세게 된다.
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
    """The orchestrator stops shims with SIGTERM; without this the stats file
    is never written and every counter silently reads as missing."""
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
