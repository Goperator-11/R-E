# -*- coding: utf-8 -*-
"""증폭 예산 회계 - 클라이언트가 더 보낸 바이트의 '음의 비용'.

RFC 9000 8.1: 서버는 클라이언트 주소가 검증되기 전까지 **받은 바이트의
3배**까지만 보낼 수 있다. 넘으면 클라이언트의 다음 패킷을 기다려야 하고
그 대기가 곧 왕복 한 번이다.

이걸 우리가 직접 관측했다(E21, rx 심에서 서버 앞 바이트 타임라인):

    cert 6000 B / FEC 없음
      수신누적 2,560 B 에서 송신누적 7,680 B 에 닿고 정지
      7680 / 2560 = 3.00  <- 한계가 실제로 구속한다

그래서 클라이언트가 Δ 바이트를 더 보내면 서버 예산이 3Δ 늘어난다.
패리티 데이터그램은 '추가 비용'이 아니라 **예산을 사는 값**이기도 하다.

한 가지 더 - E21 이 밝힌 타이밍 조건. 추가 바이트는 **서버가 응답 비행을
만들기 전에 도착해야** 효력이 있다. dup1(복제 1회)은 복제분이 서버가 이미
보낸 뒤 2.3 ms 에 도착해 임계를 못 옮겼고, dup2/dup3 은 전부 먼저 도착해
임계를 13 KB 밖으로 밀어냈다. 패리티를 같은 비행에 붙여 보내는 우리
설계는 이 조건을 구조적으로 만족한다.
"""
from __future__ import annotations

AMPLIFICATION_FACTOR = 3  # RFC 9000 8.1

# 서버가 한 번에 내보내는 패킷 크기(quic-go 기본 1280 B).
# 이게 왜 중요한가: quic-go 는 패킷을 만들기 **전에** isAmplificationLimited()
# 로 `bytesSent >= 3*bytesReceived` 를 보므로, 아직 예산이 조금이라도 남아
# 있으면 패킷 하나를 통째로 더 보낸다. 그래서 실제 허용량은 예산 그 자체가
# 아니라 **예산을 넘어서는 첫 패킷 경계**다.
#
# 이 양자화가 팀 자료의 "교환비 1:3.8" 을 설명한다. 한계 기울기는 정확히 3
# 이지만, 클라이언트가 P/3 = 427 B 를 더 보낼 때마다 임계가 P = 1280 B 씩
# 계단으로 뛴다. 인접한 두 점만 보면 0 이거나 18 로 보이는 이유다.
SERVER_PACKET_SIZE = 1280


def budget(client_bytes):
    """주소 검증 전 서버가 보낼 수 있는 최대 바이트."""
    return AMPLIFICATION_FACTOR * client_bytes


def server_flight(cert_bytes, s0):
    """서버 첫 비행 크기. s0 = 인증서를 뺀 나머지(SH+EE+CV+Fin+QUIC 오버헤드)."""
    return cert_bytes + s0


def allowed_bytes(client_bytes, pkt=SERVER_PACKET_SIZE):
    """주소 검증 전 서버가 실제로 내보낼 수 있는 바이트 (패킷 경계 양자화 포함)."""
    b = budget(client_bytes)
    if pkt <= 0:
        return b
    n = (b - 1) // pkt + 1 if b > 0 else 0
    return n * pkt


def rtt_count(cert_bytes, client_bytes, s0, pkt=SERVER_PACKET_SIZE):
    """1-RTT 인가 2-RTT 인가."""
    return 1 if server_flight(cert_bytes, s0) <= allowed_bytes(
        client_bytes, pkt) else 2


def threshold_cert(client_bytes, s0, pkt=SERVER_PACKET_SIZE):
    """이 클라이언트 비행 크기에서 1-RTT 를 유지할 수 있는 최대 인증서."""
    return allowed_bytes(client_bytes, pkt) - s0


def exchange_ratio():
    """클라이언트 1 바이트가 사들이는 인증서 여유 바이트. 이론값은 정확히 3."""
    return float(AMPLIFICATION_FACTOR)


def credit_rtt(cert_bytes, client_bytes, extra_bytes, s0):
    """추가 바이트가 왕복 한 번을 없애주는가."""
    before = rtt_count(cert_bytes, client_bytes, s0)
    after = rtt_count(cert_bytes, client_bytes + extra_bytes, s0)
    return before - after          # 1 이면 RTT 하나를 벌었다


def fit_s0(threshold_lo, threshold_hi, client_bytes,
           pkt=SERVER_PACKET_SIZE):
    """관측된 임계 구간에서 s0 를 역산한다.

    임계는 인증서 크기 격자에서만 관측되므로 구간으로 나온다. 그
    구간이 그대로 s0 의 구간이 된다(부호가 뒤집힌다).
    """
    b = allowed_bytes(client_bytes, pkt)
    return {"allowed": b, "budget": budget(client_bytes),
            "s0_lo": b - threshold_hi, "s0_hi": b - threshold_lo,
            "s0_mid": b - 0.5 * (threshold_lo + threshold_hi)}
