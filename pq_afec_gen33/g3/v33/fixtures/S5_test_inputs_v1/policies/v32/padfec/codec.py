# -*- coding: utf-8 -*-
"""PAD-FEC 부호기/복호기 - 심볼은 '데이터그램 하나의 와이어 바이트'다.

왜 데이터그램 전체를 심볼로 잡는가
--------------------------------------------------
복호 결과가 원본 데이터그램과 비트 단위로 같아지므로, **수신측이 QUIC
Initial 키를 몰라도 된다.** 복구한 바이트를 그대로 스택에 밀어 넣으면
스택은 그것이 재구성된 것인지 알 필요조차 없다. 인수인계 문서 3단계가
"복원한 패킷을 방금 수신한 것처럼 전달"이라고 쓴 그대로다.

실내용만 보호하면 심볼이 작아지지만 수신측이 재암호화를 해야 하고, 그
경우 패킷 번호·헤더 보호까지 우리가 다시 만들어야 한다. 이득보다 위험이
크다고 판단해 버렸다.

꼬리표(footer) 형식 - 심볼 뒤에 붙는 16 바이트
    magic   4   b"PFEC"
    ver     1   1
    flight  2   비행 식별자 (연결마다 증가, 랩어라운드 카운터 포함)
    index   1   이 심볼의 번호 (0..k+m-1). k 이상이면 패리티
    k       1   원본 심볼 수
    m       1   패리티 심볼 수
    symlen  2   심볼 길이(제로패딩 전의 원본 길이)
    crc     4   심볼의 CRC32 - 복구가 맞았는지 스스로 확인한다

⚠️ crc 는 장식이 아니다. 1차 연구에서 "복구했다고 세었는데 응용까지
도달하지 않은" 결함을 두 번 겪었다. 복구본이 원본과 같은지 부호가 스스로
확인하지 못하면 그 실패가 조용히 통계에 섞인다.
"""
from __future__ import annotations

import binascii
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from afec.rs import RSErasureCode  # noqa: E402  (검증된 GF(256) Cauchy RS)

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
    """버퍼 끝에서 꼬리표를 읽는다. 없으면 None."""
    if len(buf) < FOOTER_LEN:
        return None
    magic, ver, flight, index, k, m, symlen, crc = struct.unpack(
        FOOTER_FMT, buf[-FOOTER_LEN:])
    if magic != MAGIC or ver != VERSION:
        return None
    return {"flight": flight, "index": index, "k": k, "m": m,
            "symlen": symlen, "crc": crc}


class FlightCode(object):
    """한 비행(k 개 원본 + m 개 패리티)의 부호."""

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
        # m = 1 이면 평문 XOR 을 쓴다. 문서 2-3 이 지정한 형태이고, 1-소거에
        # 대해서는 XOR 도 MDS 라 RS 보다 나쁠 것이 없으면서 훨씬 싸다.
        # 핸드셰이크 경로에서 도는 코드이므로 이 차이가 실제로 중요하다.
        self.xor_only = (m == 1)
        self._rs = None if self.xor_only else RSErasureCode(k, m)

    # ------------------------------------------------------------- 부호화
    def encode(self, datagrams):
        """원본 데이터그램 목록 -> 패리티 심볼 목록.

        길이가 다르면 짧은 쪽을 0 으로 채워 맞춘다(인수인계 문서 단계 1의
        지시와 같다). 원본 길이는 꼬리표에 실어 복호 뒤 잘라낸다.
        """
        if len(datagrams) != self.k:
            raise ValueError("데이터그램 %d 개가 필요하다" % self.k)
        size = max(len(d) for d in datagrams)
        padded = [d.ljust(size, b"\x00") for d in datagrams]
        if self.xor_only:
            # k = 1 이면 XOR 패리티는 곧 복제(반복부호)다. k=1 비행에서
            # 유일하게 가능한 보호이며, 정당한 부호다.
            acc = bytearray(size)
            for d in padded:
                for i in range(size):
                    acc[i] ^= d[i]
            return [bytes(acc)]
        return [bytes(s) for s in self._rs.encode(padded)]

    # ------------------------------------------------------------- 복호화
    def decode(self, received, sizes):
        """received: {index: symbol}. 원본 k 개를 복원해 돌려준다.

        sizes: {index: 원본길이} - 제로패딩을 걷어내기 위해 필요하다.
        """
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
    """복구본이 원본과 같은지 부호 스스로 확인한다."""
    return (binascii.crc32(sym[:footer["symlen"]]) & 0xFFFFFFFF) == footer["crc"]
