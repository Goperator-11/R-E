import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RESULTS = os.path.join(HERE, "results")
os.makedirs(RESULTS, exist_ok=True)
sys.path.insert(0, ROOT)

from afec.rs import RSErasureCode

GRID = [(16, 4), (32, 4), (32, 8), (32, 16), (64, 8), (64, 16), (128, 32)]


def _harden():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


def bench_python(k, r, sym, blocks):
    code = RSErasureCode(k, r)
    src = [bytes(((i * 37 + t * 11) & 0xFF) for t in range(sym)) for i in range(k)]
    code.encode(src)
    t0 = time.perf_counter()
    for _ in range(blocks):
        code.encode(src)
    dt = time.perf_counter() - t0
    return {
        "encode_ms_per_block": dt * 1000.0 / blocks,
        "encode_ms_per_repair_symbol": dt * 1000.0 / blocks / r,
        "encode_MBps_source": (k * sym / 1e6) / (dt / blocks),
    }


def bench_python_decode(k, r, sym, blocks):
    code = RSErasureCode(k, r)
    src = [bytes(((i * 37 + t * 11) & 0xFF) for t in range(sym)) for i in range(k)]
    rep = code.encode(src)
    recv = {}
    for i in range(r, k):
        recv[i] = src[i]
    for j in range(r):
        recv[k + j] = rep[j]
    out = code.decode(recv)
    assert out == src, "decode mismatch - benchmark would be meaningless"
    t0 = time.perf_counter()
    for _ in range(blocks):
        code.decode(recv)
    dt = time.perf_counter() - t0
    return {"decode_ms_per_block": dt * 1000.0 / blocks}


def build_c(workdir):
    src = os.path.join(HERE, "rs_bench.c")
    if shutil.which("gcc") is None:
        return None
    out = os.path.join(workdir, "rs_bench")
    r = subprocess.run(["gcc", "-O3", "-march=native", "-o", out, src],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.stdout.write("gcc failed:\n%s\n" % r.stderr[-600:])
        return None
    return out


def bench_c(binary, k, r, sym, blocks, repeats=3):
    runs = []
    for _ in range(repeats):
        p = subprocess.run([binary, str(k), str(r), str(sym), str(blocks)],
                           capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError("rs_bench failed: %s" % p.stderr[:300])
        runs.append(json.loads(p.stdout.strip()))
    best = min(runs, key=lambda d: d["encode_ms_per_block"])
    best["repeats"] = repeats
    best["encode_ms_per_block_median"] = statistics.median(
        [d["encode_ms_per_block"] for d in runs])
    return best


def cpu_fraction(ms_per_block, k, sym, rate_bps):
    block_bits = k * sym * 8.0
    blocks_per_s = rate_bps / block_bits
    return blocks_per_s * (ms_per_block / 1000.0)


def main():
    _harden()
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", type=int, default=1200)
    ap.add_argument("--c-blocks", type=int, default=3000)
    ap.add_argument("--py-blocks", type=int, default=300)
    ap.add_argument("--rate-mbps", type=float, default=50.0)
    a = ap.parse_args()

    print("=" * 92)
    print("E8 - FEC coding CPU cost  (symbol=%dB, line rate=%.0f Mbps)"
          % (a.symbol, a.rate_mbps))
    print("=" * 92)

    workdir = os.path.join(HERE, "_build")
    os.makedirs(workdir, exist_ok=True)
    cbin = build_c(workdir)
    print("C encoder: %s" % (cbin or "NOT AVAILABLE (gcc missing)"))
    print("")

    out = {"symbol_bytes": a.symbol, "rate_mbps": a.rate_mbps,
           "platform": sys.platform, "python": sys.version.split()[0],
           "grid": {}}

    print("%-10s | %-28s | %-28s | %7s" %
          ("(k, r)", "python encode", "C encode", "C/py"))
    print("%-10s | %10s %8s %8s | %10s %8s %8s | %7s" %
          ("", "ms/blk", "us/sym", "CPU%", "ms/blk", "us/sym", "CPU%", "speedup"))
    print("-" * 92)
    for (k, r) in GRID:
        py = bench_python(k, r, a.symbol, a.py_blocks)
        pyd = bench_python_decode(k, r, a.symbol, max(30, a.py_blocks // 5))
        py_cpu = cpu_fraction(py["encode_ms_per_block"], k, a.symbol, a.rate_mbps * 1e6)
        row = {"python": py, "python_decode": pyd, "python_cpu_fraction": py_cpu}
        line = "%-10s | %10.4f %8.2f %7.2f%%" % (
            "(%d, %d)" % (k, r), py["encode_ms_per_block"],
            py["encode_ms_per_repair_symbol"] * 1000.0, py_cpu * 100.0)
        if cbin:
            c = bench_c(cbin, k, r, a.symbol, a.c_blocks)
            c_cpu = cpu_fraction(c["encode_ms_per_block"], k, a.symbol,
                                 a.rate_mbps * 1e6)
            row["c"] = c
            row["c_cpu_fraction"] = c_cpu
            row["speedup_c_over_python"] = (py["encode_ms_per_block"]
                                            / c["encode_ms_per_block"])
            line += " | %10.4f %8.2f %7.2f%% | %6.1fx" % (
                c["encode_ms_per_block"],
                c["encode_ms_per_repair_symbol"] * 1000.0,
                c_cpu * 100.0, row["speedup_c_over_python"])
        out["grid"]["k%d_r%d" % (k, r)] = row
        print(line)
    print("-" * 92)

    if cbin:
        c = bench_c(cbin, 2, 1, a.symbol, 200000, repeats=3)
        c["caveat"] = ("L1-resident best case, near timer resolution; "
                       "quote as '< 1 us per parity packet'")
        c["conservative_us_at_10GBps"] = 2.0 * a.symbol / 10e9 * 1e6
        out["xor_parity_k2"] = c
        print("")
        print("handshake shield (K=2, one XOR parity packet of %dB):" % a.symbol)
        print("  measured %.4f ms/packet (L1-resident best case, at timer floor)"
              % c["xor_parity_ms_per_block"])
        print("  conservative bound at a pessimistic 10 GB/s: %.2f us"
              % c["conservative_us_at_10GBps"])

    e1p = os.path.join(RESULTS, "e1_mlkem.json")
    if os.path.exists(e1p):
        with open(e1p, encoding="utf-8") as f:
            e1 = json.load(f)
        t = e1["timing"].get("ML-KEM-768")
        if t:
            enc_us = 1e6 / t["encaps_ops_median"]
            dec_us = 1e6 / t["decaps_ops_median"]
            out["mlkem768_encaps_us"] = enc_us
            out["mlkem768_decaps_us"] = dec_us
            print("")
            print("context - ML-KEM-768 per handshake (E1, ops/s derived):")
            print("  encaps %.2f us, decaps %.2f us" % (enc_us, dec_us))
            if cbin:
                xor_us = out["xor_parity_k2"]["conservative_us_at_10GBps"]
                print("  the shield's XOR parity costs at most %.2f us = %.1f%% of"
                      " one ML-KEM-768 encapsulation (conservative bound)"
                      % (xor_us, 100.0 * xor_us / enc_us))

    path = os.path.join(RESULTS, "e8_cpu.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("")
    print("saved: %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
