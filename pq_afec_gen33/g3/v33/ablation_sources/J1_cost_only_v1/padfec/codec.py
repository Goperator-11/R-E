from __future__ import annotations

import binascii
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from afec.rs import RSErasureCode

MAGIC = b"PFEC"
VERSION = 1
FOOTER_FMT = ">4sBHBBBHI"
FOOTER_LEN = struct.calcsize(FOOTER_FMT)
assert FOOTER_LEN == 16, FOOTER_LEN


def pack_footer(flight, index, k, m, symlen, sym):
    return struct.pack(FOOTER_FMT, MAGIC, VERSION, flight & 0xFFFF,
                       index & 0xFF, k & 0xFF, m & 0xFF, symlen & 0xFFFF,
                       binascii.crc32(sym) & 0xFFFFFFFF)


def unpack_footer(buf):
    if len(buf) < FOOTER_LEN:
        return None
    magic, ver, flight, index, k, m, symlen, crc = struct.unpack(
        FOOTER_FMT, buf[-FOOTER_LEN:])
    if magic != MAGIC or ver != VERSION:
        return None
    return {"flight": flight, "index": index, "k": k, "m": m,
            "symlen": symlen, "crc": crc}


class FlightCode(object):
    def __init__(self, k, m=1):
        if type(k) is not int or type(m) is not int:
            raise TypeError("k and m must be integers")
        if k < 1:
            raise ValueError("k >= 1 이어야 한다")
        if m < 1:
            raise ValueError("m >= 1 이어야 한다")
        if k + m > 256:
            raise ValueError("k + m must fit the one-byte symbol index")
        self.k = k
        self.m = m
        self.xor_only = (m == 1)
        self._rs = None if self.xor_only else RSErasureCode(k, m)

    def encode(self, datagrams):
        if len(datagrams) != self.k:
            raise ValueError("데이터그램 %d 개가 필요하다" % self.k)
        size = max(len(d) for d in datagrams)
        padded = [d.ljust(size, b"\x00") for d in datagrams]
        if self.xor_only:
            acc = bytearray(size)
            for d in padded:
                for i in range(size):
                    acc[i] ^= d[i]
            return [bytes(acc)]
        return [bytes(s) for s in self._rs.encode(padded)]

    def decode(self, received, sizes):
        if any(type(i) is not int or not 0 <= i < self.k + self.m
               for i in received):
            raise ValueError("received symbol index is outside the codeword")
        if len(received) < self.k:
            raise ValueError("심볼이 %d 개 미만이라 복호 불가" % self.k)
        width = max(len(s) for s in received.values())
        if any(type(n) is not int or not 0 <= n <= width
               for i, n in sizes.items() if 0 <= i < self.k):
            raise ValueError("original length must be within the symbol width")
        if self.xor_only:
            size = max(len(s) for s in received.values())
            norm = {i: s.ljust(size, b"\x00") for i, s in received.items()}
            missing = [i for i in range(self.k) if i not in norm]
            if len(missing) > 1:
                raise ValueError("XOR 은 소거 1개까지만 복구한다")
            out = []
            for i in range(self.k):
                if i in norm:
                    out.append(bytes(norm[i])[:sizes.get(i, size)])
                    continue
                acc = bytearray(size)
                for j, s in norm.items():
                    for b in range(size):
                        acc[b] ^= s[b]
                out.append(bytes(acc)[:sizes.get(i, size)])
            return out
        size = max(len(s) for s in received.values())
        norm = {i: s.ljust(size, b"\x00") for i, s in received.items()}
        src = self._rs.decode(norm)
        return [bytes(src[i])[:sizes.get(i, size)] for i in range(self.k)]


def verify_symbol(sym, footer):
    return (binascii.crc32(sym[:footer["symlen"]]) & 0xFFFFFFFF) == footer["crc"]
