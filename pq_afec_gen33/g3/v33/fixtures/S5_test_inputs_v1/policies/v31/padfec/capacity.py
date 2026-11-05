# -*- coding: utf-8 -*-
"""제자리(byte-neutral) 보호가 언제 가능한가 - 용량 부등식.

인수인계 문서 1-4 의 주장은 이렇다.

    "Initial 패킷은 최소 1,200 B 로 채워야 하는데(RFC 9000 14.1) 실제
     ClientHello 는 그보다 작아서 나머지가 PADDING 이다. 거기에 복구
     심볼을 넣으면 바이트 수가 그대로이므로 증폭 예산도 그대로고,
     버려지던 공간이 손실 복구에 쓰인다. 추가 비용이 없는 FEC 다."

전제는 옳다(패딩은 실제로 존재하며 우리가 실측했다). 그런데 **언제나
되는 것은 아니다.** 손실 단위가 데이터그램이기 때문에 제약이 생긴다.

기호
    W   한 데이터그램의 와이어 크기 (RFC 9000 14.1 로 >= 1200)
    h   패킷당 고정 비용 (롱헤더 + AEAD 태그 + CRYPTO 프레임 머리)
    f   우리 FEC 꼬리표(footer) 크기
    k   비행을 이루는 데이터그램 수
    C   ClientHello 총 바이트 (여러 데이터그램에 걸쳐 있는 실내용)

정리 (제자리 1-소거 보호 가능 조건)
--------------------------------------------------
    C <= (k - 1) * (W - h - f)

증명 스케치. 데이터그램 하나가 통째로 사라지므로, 그 안에 있던 실내용
s_i 바이트와 그 안에 있던 패리티 조각이 함께 사라진다. 실내용을 균등히
나누면 s = C/k 다. MDS 부호로 데이터그램 1개 소거를 복구하려면, 각
데이터그램이 실어야 하는 패리티 양 m*u 는 소거된 심볼 수 d+m 이 전체
패리티 개수 k*m 이하일 때 충분하다: m*(k-1) >= d. 데이터그램 하나에
들어가는 총량은 h + (d+m)*u + f <= W 이고, d*u = s = C/k 이므로

    h + (C/k) * (1 + 1/(k-1)) + f <= W
    <=> C/(k-1) <= W - h - f
    <=> C <= (k-1)(W - h - f)                                        ∎

따름정리 1 - k = 1 이면 우변이 0 이다. **데이터그램이 하나뿐인 비행은
어떤 방법으로도 비행 내부에서 보호할 수 없다.** 그 하나를 잃으면 아무것도
남지 않기 때문이다. x25519(CH 272 B)와 MLKEM512(1032 B)가 여기 해당한다.

따름정리 2 - quic-go 같은 구현은 패킷을 꽉 채워 보내므로 자연스러운
데이터그램 수는 k_nat = ceil(C / (W - h)) 이고, 이때 평균 채움률은
1 에 가깝다. 정리의 조건은 채움률이 (k-1)/k 이하일 것을 요구하므로,
**보통은 자연 비행보다 데이터그램이 하나 더 필요하다.**

따름정리 3 - 실측된 ML-KEM ClientHello(1416~1800 B)를 W=1200 에 넣으면
k_nat = 2 이고 (k-1)(W-h-f) ~ 1138 < C 다. 즉 **오늘의 후양자 핸드셰이크에서
제자리 무비용 FEC 는 성립하지 않는다.** 최소 실현은 패리티 데이터그램
하나를 더 보내는 것이고, 그 비용은 증폭 예산이 되갚는다(amplif 참고).

이 결론은 인수인계 문서의 기대와 다르다. 문서 8절의 지침을 따른다 -
"예상과 다른 결과가 나오는 것은 실패가 아니다. 데이터를 억지로 해석하지
말고 있는 그대로 기록하라."
"""
from __future__ import annotations

import math

# RFC 9000 14.1 - Initial 을 실은 데이터그램의 최소 크기.
MIN_INITIAL_DATAGRAM = 1200

# 롱헤더 Initial 한 패킷의 고정 비용(바이트). e4 실측 패킷에서 역산한 값이며
# measure_overhead() 로 실제 캡처에서 다시 확인한다.
#   b0 1 + version 4 + DCIL 1 + DCID 8 + SCIL 1 + SCID 8
#   + token_len 1 + length 2 + pn 2 + AEAD tag 16      = 44
#   + CRYPTO 프레임 머리 (type 1 + offset<=4 + len 2)   = 7
DEFAULT_H = 51

# 우리 FEC 꼬리표: magic 4 + ver 1 + flight 2 + index 1 + k 1 + m 1
#                  + symlen 2 + crc 4                  = 16
DEFAULT_F = 16


def inplace_capacity(k, W=MIN_INITIAL_DATAGRAM, h=DEFAULT_H, f=DEFAULT_F):
    """제자리 보호로 담을 수 있는 ClientHello 최대 바이트."""
    if k < 2:
        return 0
    return (k - 1) * (W - h - f)


def natural_k(C, W=MIN_INITIAL_DATAGRAM, h=DEFAULT_H):
    """구현이 패킷을 꽉 채워 보낼 때 나오는 데이터그램 수."""
    per = W - h
    if per <= 0:
        raise ValueError("W 가 패킷 고정비용보다 작다")
    return max(1, int(math.ceil(float(C) / per)))


def inplace_feasible(C, k, W=MIN_INITIAL_DATAGRAM, h=DEFAULT_H, f=DEFAULT_F):
    return C <= inplace_capacity(k, W, h, f)


def min_k_for_inplace(C, W=MIN_INITIAL_DATAGRAM, h=DEFAULT_H, f=DEFAULT_F):
    """제자리 보호가 성립하는 최소 데이터그램 수 (없으면 None)."""
    per = W - h - f
    if per <= 0:
        return None
    return int(math.ceil(float(C) / per)) + 1


def parity_symbol_bytes(C, k, h=DEFAULT_H):
    """비행 밖으로 뺄 때 패리티 심볼 하나의 크기.

    심볼을 '데이터그램 와이어 바이트 전체'로 잡으면 복구 결과가 원본
    데이터그램과 비트 단위로 같아져서 수신측이 키를 몰라도 된다. 대신
    심볼 크기가 W 가 된다. 실내용만 보호하면 더 작아지지만 수신측이
    재암호화를 해야 한다 - 우리는 전자를 쓴다(codec.SYMBOL_WHOLE_DATAGRAM).
    """
    return int(math.ceil(float(C) / k)) + h


def describe(C, W=MIN_INITIAL_DATAGRAM, h=DEFAULT_H, f=DEFAULT_F):
    """한 ClientHello 크기에 대해 어떤 보호가 가능한지 정리해 돌려준다."""
    k = natural_k(C, W, h)
    cap = inplace_capacity(k, W, h, f)
    need = min_k_for_inplace(C, W, h, f)
    flight = k * W
    return {
        "C": C, "W": W, "h": h, "f": f,
        "k_natural": k,
        "flight_bytes": flight,
        "fill_ratio": float(C) / (k * (W - h)),
        "inplace_capacity": cap,
        "inplace_feasible": C <= cap,
        "k_needed_for_inplace": need,
        "extra_datagrams": (None if need is None else max(0, need - k)),
        "extra_bytes": (None if need is None else max(0, need - k) * W),
        "protectable_at_all": k >= 2,
    }
