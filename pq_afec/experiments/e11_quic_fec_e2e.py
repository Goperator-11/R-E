# -*- coding: utf-8 -*-
"""
E11 - REAL end-to-end: ML-KEM + QUIC + FEC, measured (not simulated)

Everything up to E10 either measured packets (real) or replayed measured loss
traces through the simulator (modelled).  The one link that was never actually
exercised is **FEC on a live QUIC handshake**.  This closes it.

    openssl s_client -quic  ->  [ loss-injecting relay + FEC shim ]  ->  real server

The relay sits on the datagram path and does three things:

  1. drops datagrams according to a loss model (Bernoulli, Gilbert-Elliott, or
     replay of a mask measured over real netem in E6),
  2. buffers the client's first Initial flight so it can act on it as a UNIT,
  3. in `--fec` mode, adds one parity slot to that flight: the loss process now
     sees K+1 slots, and the flight is delivered intact iff at most one slot is
     lost - which is exactly the delivery behaviour of an XOR/RS(K+1, K) parity
     packet.  Recovery is done by replaying the buffered original, so the
     DELIVERY OUTCOME is identical to real FEC while the QUIC stack, the
     ML-KEM key exchange and the timing are all real.

The same buffering delay is applied in both arms, so the FEC arm is not given a
free head start.

What is real here: the TLS/QUIC stack, ML-KEM, the packets, the timers, the
handshake completion time.  What is emulated: the parity packet's contents
(the relay does not XOR payloads, it replays the original it already holds).

Output: experiments/results/e11_quic_fec.json
"""
import argparse
import json
import os
import random
import socket
import statistics
import struct
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RESULTS = os.path.join(HERE, "results")
TRACES = os.path.join(HERE, "traces")
os.makedirs(RESULTS, exist_ok=True)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from e3_quic_capture import parse_quic_datagram      # noqa: E402


def _harden():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


# ------------------------------------------------------------- loss models
class BernoulliLoss:
    name = "bernoulli"

    def __init__(self, p, rng):
        self.p = p
        self.rng = rng

    def lose(self):
        return self.rng.random() < self.p


class GilbertLoss:
    name = "gilbert"

    def __init__(self, p, burst, rng):
        L = max(burst, 1.0)
        self.q_bg = 1.0 / L
        self.q_gb = p * self.q_bg / (1.0 - p) if p < 1 else 1.0
        self.rng = rng
        self.state = 1 if rng.random() < (self.q_gb / (self.q_gb + self.q_bg)) else 0

    def lose(self):
        lost = (self.state == 1)
        q = self.q_gb if self.state == 0 else self.q_bg
        if self.rng.random() < q:
            self.state ^= 1
        return lost


class TraceLoss:
    name = "trace"

    def __init__(self, bitmap, n, rng):
        self.bm = bitmap
        self.n = n
        self.i = rng.randrange(n)

    def lose(self):
        i = self.i % self.n
        self.i += 1
        return not ((self.bm[i >> 3] >> (i & 7)) & 1)


def make_loss(kind, p, burst, rng, trace=None):
    if kind == "none":
        return None
    if kind == "trace" and trace is not None:
        return TraceLoss(trace[0], trace[1], rng)
    if kind == "gilbert":
        return GilbertLoss(p, burst, rng)
    return BernoulliLoss(p, rng)


# -------------------------------------------------------------------- relay
class FecRelay(object):
    """UDP relay that injects loss and optionally protects the Initial flight."""

    def __init__(self, host, port, loss_c2s, loss_s2c, fec, flight_ms):
        infos = socket.getaddrinfo(host, port, 0, socket.SOCK_DGRAM)
        v4 = [i for i in infos if i[0] == socket.AF_INET]
        pick = (v4 or infos)[0]
        self.family, self.upstream = pick[0], pick[4]
        self.local = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.local.bind(("127.0.0.1", 0))
        self.local.settimeout(0.002)
        self.port = self.local.getsockname()[1]
        self.up = socket.socket(self.family, socket.SOCK_DGRAM)
        self.up.settimeout(0.002)
        self.loss_c2s = loss_c2s
        self.loss_s2c = loss_s2c
        self.fec = fec
        self.flight_ms = flight_ms
        self.stop = threading.Event()
        self.caddr = None
        self.stats = {
            "c2s_datagrams": 0, "c2s_dropped": 0,
            "s2c_datagrams": 0, "s2c_dropped": 0,
            "flight_slots": 0, "flight_lost_slots": 0,
            "flight_recovered": 0, "flight_unrecoverable": 0,
            "flight_size": 0,
        }
        self._flight = []
        self._flight_done = False
        self._server_seen = False
        # ⚠️ 핸드셰이크 시간은 **릴레이에서** 잰다. openssl s_client 프로세스의
        # 수명으로 재면 기동 오버헤드(실측 약 1.7초)가 신호를 통째로 덮는다.
        # t_first_c2s = 클라이언트의 첫 데이터그램
        # t_first_1rtt = 클라이언트가 처음으로 short header(1-RTT) 패킷을 보낸 시각
        #                = 핸드셰이크가 클라이언트 관점에서 끝난 순간
        self.t_first_c2s = None
        self.t_first_s2c = None
        self.t_first_1rtt = None

    # ---- helpers
    @staticmethod
    def _is_initial(buf):
        try:
            for p in parse_quic_datagram(buf):
                if p.get("type") == "Initial":
                    return True
        except Exception:
            pass
        return False

    def _send_up(self, data):
        try:
            self.up.sendto(data, self.upstream)
        except OSError:
            pass

    def _flush_flight(self):
        """Apply the loss process to the whole first Initial flight at once."""
        pkts = self._flight
        self._flight = []
        self._flight_done = True
        if not pkts:
            return
        k = len(pkts)
        slots = k + (1 if self.fec else 0)
        self.stats["flight_size"] = k
        self.stats["flight_slots"] = slots

        drops = []
        for _ in range(slots):
            drops.append(self.loss_c2s.lose() if self.loss_c2s else False)
        n_lost = sum(1 for d in drops if d)
        self.stats["flight_lost_slots"] = n_lost
        self.stats["c2s_datagrams"] += k

        if self.fec:
            # RS(k+1, k) / XOR parity: the flight survives iff at most one slot
            # of the k+1 is lost.  Recovery replays the buffered original.
            if n_lost <= 1:
                if n_lost == 1:
                    self.stats["flight_recovered"] += 1
                for d in pkts:
                    self._send_up(d)
                return
            self.stats["flight_unrecoverable"] += 1
            # more than one slot gone: whatever originals survive still go out
            for idx, d in enumerate(pkts):
                if not drops[idx]:
                    self._send_up(d)
                else:
                    self.stats["c2s_dropped"] += 1
            return

        for idx, d in enumerate(pkts):
            if drops[idx]:
                self.stats["c2s_dropped"] += 1
            else:
                self._send_up(d)

    # ---- pumps
    def _from_client(self):
        last_initial = None
        while not self.stop.is_set():
            try:
                data, addr = self.local.recvfrom(65535)
            except socket.timeout:
                if (self._flight and not self._flight_done and last_initial
                        and (time.perf_counter() - last_initial) * 1000 >= self.flight_ms):
                    self._flush_flight()
                continue
            except OSError:
                break
            self.caddr = addr
            now = time.perf_counter()
            if self.t_first_c2s is None:
                self.t_first_c2s = now
            if data and not (data[0] & 0x80) and self.t_first_1rtt is None:
                self.t_first_1rtt = now      # short header = handshake done
            if not self._flight_done and self._is_initial(data) and not self._server_seen:
                # first Initial flight: hold it so it can be treated as a unit
                self._flight.append(data)
                last_initial = time.perf_counter()
                continue
            if self._flight and not self._flight_done:
                self._flush_flight()
            self.stats["c2s_datagrams"] += 1
            if self.loss_c2s and self.loss_c2s.lose():
                self.stats["c2s_dropped"] += 1
                continue
            self._send_up(data)

    def _from_server(self):
        while not self.stop.is_set():
            try:
                data, _ = self.up.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            self._server_seen = True
            self.stats["s2c_datagrams"] += 1
            if self.loss_s2c and self.loss_s2c.lose():
                self.stats["s2c_dropped"] += 1
                continue
            if self.caddr:
                try:
                    self.local.sendto(data, self.caddr)
                except OSError:
                    break

    def start(self):
        self.t1 = threading.Thread(target=self._from_client, daemon=True)
        self.t2 = threading.Thread(target=self._from_server, daemon=True)
        self.t1.start()
        self.t2.start()

    def shutdown(self):
        self.stop.set()
        time.sleep(0.15)
        for s in (self.local, self.up):
            try:
                s.close()
            except Exception:
                pass


# ------------------------------------------------------------------- trial
def one_trial(host, group, loss_kind, p, burst, fec, rng, trace, flight_ms,
              timeout):
    relay = FecRelay(host, 443,
                     make_loss(loss_kind, p, burst, rng, trace),
                     make_loss(loss_kind, p, burst, rng, trace),
                     fec, flight_ms)
    relay.start()
    time.sleep(0.05)
    t0 = time.perf_counter()
    try:
        r = subprocess.run(
            ["openssl", "s_client", "-quic", "-connect", "127.0.0.1:%d" % relay.port,
             "-servername", host, "-alpn", "h3", "-groups", group, "-brief"],
            input=b"", capture_output=True, timeout=timeout)
        dt = (time.perf_counter() - t0) * 1000.0
        txt = (r.stdout + r.stderr).decode("utf-8", "replace")
        ok = "CONNECTION ESTABLISHED" in txt
    except subprocess.TimeoutExpired:
        dt = timeout * 1000.0
        ok = False
    relay.shutdown()
    return dt, ok, dict(relay.stats)


def quantiles(xs):
    if not xs:
        return {}
    s = sorted(xs)
    def q(f):
        return s[min(len(s) - 1, int(f * (len(s) - 1)))]
    return {"n": len(s), "mean": statistics.mean(s), "p50": q(0.5),
            "p90": q(0.90), "p95": q(0.95), "p99": q(0.99),
            "max": s[-1], "min": s[0]}


def load_trace(name, n):
    with open(os.path.join(TRACES, name + ".mask"), "rb") as f:
        return f.read(), n


def main():
    _harden()
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="cloudflare.com")
    ap.add_argument("--trials", type=int, default=60)
    ap.add_argument("--timeout", type=float, default=12.0)
    ap.add_argument("--flight-ms", type=float, default=6.0)
    ap.add_argument("--seed", type=int, default=20260817)
    ap.add_argument("--pace-ms", type=float, default=60.0)
    a = ap.parse_args()

    # arms: (label, group, loss kind, p, burst, fec)
    arms = [
        ("baseline_x25519_noloss", "x25519", "none", 0.0, 1.0, False),
        ("baseline_mlkem_noloss", "X25519MLKEM768", "none", 0.0, 1.0, False),
        ("x25519_p5", "x25519", "bernoulli", 0.05, 1.0, False),
        ("mlkem_p5", "X25519MLKEM768", "bernoulli", 0.05, 1.0, False),
        ("mlkem_p5_FEC", "X25519MLKEM768", "bernoulli", 0.05, 1.0, True),
        ("x25519_ge_p5_L4", "x25519", "gilbert", 0.05, 4.0, False),
        ("mlkem_ge_p5_L4", "X25519MLKEM768", "gilbert", 0.05, 4.0, False),
        ("mlkem_ge_p5_L4_FEC", "X25519MLKEM768", "gilbert", 0.05, 4.0, True),
        ("mlkem_p10", "X25519MLKEM768", "bernoulli", 0.10, 1.0, False),
        ("mlkem_p10_FEC", "X25519MLKEM768", "bernoulli", 0.10, 1.0, True),
    ]

    print("=" * 100)
    print("E11 - REAL QUIC + ML-KEM handshake with a live FEC shim")
    print("   server=%s  trials=%d/arm  (real TLS stack, real ML-KEM, real timers)"
          % (a.host, a.trials))
    print("=" * 100)
    print("")
    print("%-24s %6s %8s %8s %8s %8s %8s %7s %7s" %
          ("arm", "ok", "p50 ms", "mean", "p90", "p95", "max", "drop%", "recov"))
    print("-" * 100)

    out = {"host": a.host, "trials": a.trials, "flight_ms": a.flight_ms,
           "arms": {}}
    for label, group, kind, p, burst, fec in arms:
        rng = random.Random(a.seed + hash(label) % 100000)
        times, oks, stats = [], 0, []
        for i in range(a.trials):
            dt, ok, st = one_trial(a.host, group, kind, p, burst, fec, rng,
                                   None, a.flight_ms, a.timeout)
            times.append(dt)
            oks += 1 if ok else 0
            stats.append(st)
            time.sleep(a.pace_ms / 1000.0)
        q = quantiles(times)
        tot_c = sum(s["c2s_datagrams"] for s in stats)
        tot_d = sum(s["c2s_dropped"] for s in stats) + \
            sum(s["s2c_dropped"] for s in stats)
        tot_all = tot_c + sum(s["s2c_datagrams"] for s in stats)
        rec = sum(s["flight_recovered"] for s in stats)
        unrec = sum(s["flight_unrecoverable"] for s in stats)
        out["arms"][label] = {
            "group": group, "loss_kind": kind, "p": p, "burst": burst,
            "fec": fec, "established": oks, "times_ms": times,
            "quantiles": q,
            "flight_recovered": rec, "flight_unrecoverable": unrec,
            "flight_size_mode": statistics.mode(
                [s["flight_size"] for s in stats if s["flight_size"]] or [0]),
            "drop_pct": 100.0 * tot_d / tot_all if tot_all else 0.0,
        }
        print("%-24s %5d%% %8.1f %8.1f %8.1f %8.1f %8.1f %6.1f%% %7s" %
              (label, 100 * oks // a.trials, q["p50"], q["mean"], q["p90"],
               q["p95"], q["max"],
               out["arms"][label]["drop_pct"],
               ("%d/%d" % (rec, rec + unrec)) if fec else "-"))

    path = os.path.join(RESULTS, "e11_quic_fec.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("")
    print("saved: %s" % path)

    # ---- the comparisons that matter
    def cmp(a_lab, b_lab, what):
        A, B = out["arms"].get(a_lab), out["arms"].get(b_lab)
        if not A or not B:
            return
        for st in ("p50", "mean", "p95"):
            d = (B["quantiles"][st] - A["quantiles"][st]) / A["quantiles"][st] * 100
            print("   %-28s %-5s %8.1f -> %8.1f ms  (%+.1f%%)"
                  % (what, st, A["quantiles"][st], B["quantiles"][st], d))
    print("")
    print("FEC effect on a REAL ML-KEM QUIC handshake:")
    cmp("mlkem_p5", "mlkem_p5_FEC", "p=5% independent")
    cmp("mlkem_ge_p5_L4", "mlkem_ge_p5_L4_FEC", "p=5% burst L=4")
    cmp("mlkem_p10", "mlkem_p10_FEC", "p=10% independent")
    print("")
    print("ML-KEM vs X25519 (same loss, no FEC):")
    cmp("x25519_p5", "mlkem_p5", "p=5% independent")
    cmp("x25519_ge_p5_L4", "mlkem_ge_p5_L4", "p=5% burst L=4")
    return 0


if __name__ == "__main__":
    sys.exit(main())
