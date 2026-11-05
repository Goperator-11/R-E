"""핸드셰이크 구간 - ML-KEM 때문에 FEC가 가장 크게 이기는 자리.

왜 여기가 핵심인가
------------------
QUIC Initial 패킷을 담는 데이터그램은 최소 1200바이트여야 한다(RFC 9000 14.1).
그런데 X25519MLKEM768 하이브리드의 클라이언트 키 공유만 1216바이트다.
즉 **ML-KEM을 켜는 순간 ClientHello가 Initial 패킷 한 개에 안 들어가서
반드시 2개 이상으로 쪼개진다.** 기존 X25519(32바이트)는 1개면 됐다.

쪼개진 조각 중 하나만 잃으면 어떻게 되나?
- 뒤따르는 패킷이 없으니 패킷 임계값(kPacketThreshold=3) 검출이 안 걸린다.
- RTT 표본이 없어 PTO는 kInitialRtt=333ms 기준 -> 333 + 4*166.5 = 약 999 ms.
즉 **패킷 1개 손실 = 약 1초 정지**. RTT가 20ms인 망에서도 1초다.

여분 패킷 1개(1200바이트)를 미리 붙이면 이 1초를 확률적으로 없앨 수 있다.
비용은 1.2KB, 이득은 초 단위 지연. 이 비대칭이 핸드셰이크 FEC의 근거다.

덤: 3배 증폭 제한(RFC 9000 8.1)
서버는 주소 검증 전까지 받은 바이트의 3배까지만 보낼 수 있다.
클라이언트가 2패킷(2400B) 대신 3패킷(3600B)을 보내면 서버 예산이
7200B -> 10800B로 늘어난다. ML-KEM 암호문 + 인증서 체인이 실린
서버 플라이트가 증폭 제한에 걸리는 걸 완화하는 부수 효과가 있다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .channel import GilbertElliott
from .controller import Decision, FecConfig, pto_ms

# FIPS 203 기준 (바이트) : (암호화키 ek, 암호문 ct)
# 2026-08-17 실측 확인: OpenSSL 3.5.5 네이티브 ML-KEM의 genpkey/encap 산출물이
# 세 파라미터 셋 모두 아래 값과 바이트 단위로 일치 (experiments/e1_mlkem_bench.py).
ML_KEM_SIZES = {
    512: (800, 768),
    768: (1184, 1088),
    1024: (1568, 1568),
}
X25519_BYTES = 32

# ─────────────────────────────────────────────────────────────────────────
# 실측으로 확정된 상수들 (2026-08-17). 전부 experiments/results/*.json 에 원자료.
# 이 블록 이전에는 세 값이 전부 "추정"이라고 표시돼 있었다.
# ─────────────────────────────────────────────────────────────────────────

# QUIC Initial 패킷 하나가 실어나를 수 있는 CRYPTO 페이로드.
#   1200(RFC 9000 14.1 최소 데이터그램)
#   - 롱헤더 30 (첫바이트1+버전4+DCID(1+8)+SCID(1+8)+토큰길이1+길이2+PN4)
#   - AEAD 태그 16 (RFC 9001 5.3)
#   - CRYPTO 프레임 헤더 4 (타입1+오프셋varint1+길이varint2)
#   = 1150
# experiments/e3_quic_capture.py 가 이 계산을 RFC 프레이밍으로 재현하고,
# 실제 Cloudflare/Google QUIC 핸드셰이크에서 클라이언트가 정확히 1200B
# 데이터그램을 보내는 것을 캡처로 확인했다. 추정값 1150이 정확했다.
INITIAL_CRYPTO_CAPACITY = 1150

# ClientHello 중 키 공유가 아닌 부분. **클라이언트 구현에 따라 2배 이상 차이나고,
# 이 값이 ML-KEM-512의 분할 여부를 가른다** (아래 profile() 주석 참고).
CH_BASE_MINIMAL_QUIC = 232    # openssl s_client -quic 실측 (E4). 하한.
CH_BASE_BROWSER_QUIC = 508    # Chrome 헤드리스 실측 (E5). ECH 254B + quic_tp 90B 포함.
CH_BASE_CLASSICAL_MIN = 240   # 고전 그룹만 제시할 때의 openssl 하한 (E4).

# ServerHello 중 키 공유가 아닌 부분. x25519(122B)와 X25519MLKEM768(1210B)
# 양쪽에서 동일하게 90B로 떨어졌다 (E2, TLS 레코드 실측).
SH_BASE = 90

# 서버 인증서 플라이트(EE+Certificate+CertificateVerify+Finished).
# 실측: QUIC Handshake 패킷 바이트 합계 (E3).
CERT_FLIGHT_CLOUDFLARE = 2955   # ECDSA P-256 체인
CERT_FLIGHT_GOOGLE = 5299       # 더 긴 체인
CERT_FLIGHT_DEFAULT = CERT_FLIGHT_CLOUDFLARE


@dataclass
class HandshakeProfile:
    kem: str                 # 'x25519' | 'mlkem512' | ...
    client_share: int
    server_share: int
    client_flight: int       # ClientHello 전체 바이트
    server_flight: int       # ServerHello..Finished 전체 바이트
    k_client: int            # 클라이언트 Initial 패킷 수
    k_server: int            # 서버 플라이트 패킷 수 (Initial + Handshake)
    # v0.3에서 추가 - 서버 플라이트는 두 패킷 번호 공간에 나뉘어 산다.
    server_initial_flight: int = 0    # ServerHello (Initial 공간)
    server_handshake_flight: int = 0  # EE/Cert/CV/Fin (Handshake 공간)
    k_server_initial: int = 0
    k_server_handshake: int = 0

    @property
    def amplification_budget(self) -> int:
        return 3 * self.k_client * 1200


def profile(level: int | None = 768, hybrid: bool = True,
            ch_base: int = CH_BASE_BROWSER_QUIC,
            cert_chain: int = CERT_FLIGHT_DEFAULT) -> HandshakeProfile:
    """키 교환 방식별 핸드셰이크 크기와 패킷 수를 계산한다.

    level=None 이면 기존 X25519 단독(대조군).
    ch_base   = 키 공유를 뺀 ClientHello 나머지(SNI/ALPN/암호목록/전송파라미터).
    cert_chain= 서버 인증서 플라이트 크기. 서버마다 크게 다르므로 파라미터.

    2026-08-17 실측 검증 (experiments/e4_quic_decrypt.py)
    -----------------------------------------------------
    `client_flight = ch_base + client_share` 라는 이 함수의 뼈대는 실제 QUIC
    Initial 패킷을 복호화해 **바이트 단위로 정확히** 확인됐다. openssl
    (ch_base=232) 기준 실측 ClientHello:
        x25519         272 = 240 + 32
        MLKEM512      1032 = 232 + 800
        MLKEM768      1416 = 232 + 1184
        X25519MLKEM768 1448 = 232 + 1216
        MLKEM1024     1800 = 232 + 1568

    ⚠️ 그래서 드러난 것: **ML-KEM이면 무조건 쪼개진다는 건 사실이 아니다.**
    최소 ClientHello(openssl, ch_base=232)에서는 ML-KEM-512 단독이 1032B라
    1150B 예산에 들어가 **Initial 패킷 1개로 끝난다**(실측에서도 1개였다).
    분할이 강제되는 건 ch_base + share > 1150 일 때이고, 실제 브라우저는
    ch_base가 508B(Chrome 실측, ECH 254B 포함)라 **ML-KEM-512도 쪼개진다**.
    기본값을 브라우저 실측값으로 둔 이유가 이것이다. 보고서에는
    "ML-KEM은 쪼갠다"가 아니라 **"실제 브라우저 ClientHello 기준으로는
    ML-KEM 전 파라미터가 쪼개지고, 최소 클라이언트에선 512만 안 쪼개진다"**
    로 쓸 것.

    서버 쪽도 실측으로 갈라놨다: ServerHello는 Initial 공간, 인증서 플라이트는
    Handshake 공간에 산다(손실·회복이 서로 독립). X25519MLKEM768에서
    ServerHello가 1210B라 **서버의 Initial도 2패킷이 된다**(SH_BASE 90 실측).
    """
    if level is None:
        name = "x25519"
        ck = sk = X25519_BYTES
    else:
        ek, ct = ML_KEM_SIZES[level]
        name = f"{'x25519+' if hybrid else ''}mlkem{level}"
        extra = X25519_BYTES if hybrid else 0
        ck, sk = ek + extra, ct + extra

    def npkt(nbytes):
        return max(1, -(-nbytes // INITIAL_CRYPTO_CAPACITY))

    client_flight = ch_base + ck
    server_initial = SH_BASE + sk        # ServerHello
    server_hs = cert_chain               # EE + Certificate + CertVerify + Finished
    k_si = npkt(server_initial)
    k_sh = npkt(server_hs)

    return HandshakeProfile(
        kem=name, client_share=ck, server_share=sk,
        client_flight=client_flight,
        server_flight=server_initial + server_hs,
        k_client=npkt(client_flight),
        k_server=k_si + k_sh,
        server_initial_flight=server_initial,
        server_handshake_flight=server_hs,
        k_server_initial=k_si,
        k_server_handshake=k_sh,
    )


def shield(prof: HandshakeProfile, p_prior: float, burst_prior: float = 1.0,
           cfg: FecConfig | None = None, side: str = "client",
           ack_partial: bool = True, srtt_ms: float | None = None,
           rtt_prior_ms: float = 100.0) -> Decision:
    """핸드셰이크 플라이트에 붙일 이중화 패킷 수를 정한다.

    데이터 구간과 **같은 비용식**(전송비용 + 실패확률x대가)을 쓰되, 실패의
    대가를 두 갈래로 나눈다 (2026-08-14 선행연구 대조에서 정밀화):

        J(r) = r*t_sym + fp(r)*2*RTT + ft(r)*PTO
        fp = 부분 실패 확률 (일부 조각 도착 -> 서버가 생존 조각을 ACK ->
             RTT 표본 + 시간임계 검출 -> 약 2*RTT 회복. quicly #639 실증)
        ft = 전멸 확률 (플라이트 전체 손실 -> ACK 없음 -> PTO ~999ms.
             버스트가 인접 데이터그램을 같이 삼킬 때 - GE가 정확히 준다)

    v0.1은 모든 실패를 PTO로 쳤는데 이는 FEC 이득의 과장이었다. 이 분리로
    **버스트가 핸드셰이크의 진짜 적**임이 드러난다: 단발 손실은 2*RTT로
    회복되지만 버스트 전멸만이 초 단위 정지를 만들고, r 배치는 정확히
    그 전멸 확률을 낮춘다.

    ack_partial=False: 부분 CH를 ACK하지 않는 서버 구현 대비(전부 PTO 경로).
    srtt_ms: 캐시가 물려준 직전 srtt (RFC 9002 6.2.2 재개 연결 조항) -
             있으면 PTO 기저가 999ms보다 작아진다.
    p_prior = 사전 손실률 추정치. 출처 우선순위:
      1) 같은 목적지(/24 프리픽스)로의 직전 연결 통계 캐시
      2) 같은 접속망에서 최근 측정한 값
      3) 기본값(예: 0.01)
    K=1 플라이트도 같은 식이 자연히 처리한다 - RS(1+r,1)은 복제 전송과
    같고(부호기로 확인), J가 그 비용/이득을 그대로 저울질한다.
    """
    cfg = cfg or FecConfig()

    # 🩸 H1 (2026-08-18 감사): 서버 플라이트를 **한 덩어리로 보면 안 된다.**
    # ServerHello 는 Initial 공간, 인증서 플라이트는 Handshake 공간에 산다.
    # 클라이언트는 ServerHello 없이는 Handshake 키를 유도할 수 없으므로,
    # Initial 공간이 전멸하면 Handshake 패킷이 아무리 많이 도착해도 복호도
    # ACK 도 못 한다. 즉 "ACK 이 아예 없다(=PTO)"는 사건은 '플라이트 전체 손실'
    # 이 아니라 **'Initial 공간 전체 손실'**이고, 후자가 훨씬 흔하다
    # (실측: profile(768) 에서 3.4~8배 과소평가).
    # 그래서 side='server' 는 **PTO 를 만드는 부분 플라이트(ServerHello)**를
    # 대상으로 한다. 인증서 플라이트는 클라이언트가 이미 RTT 표본을 가진
    # 뒤이므로 회복이 ~2*RTT 이고, side='server_certs' 로 따로 정한다.
    if side == "client":
        k = prof.k_client
    elif side == "server":
        k = prof.k_server_initial or prof.k_server
    elif side == "server_certs":
        k = prof.k_server_handshake or prof.k_server
    else:
        raise ValueError("side must be client | server | server_certs")

    # 🩸 H10: 버스트 정보가 없을 때(L<=1) from_burst 는 '연속 손실 불가' 채널을
    # 주어 전멸 확률을 0으로 만든다. 사전값 경로는 독립 손실을 써야 한다.
    ch = GilbertElliott.for_prior(p_prior, burst_prior)

    base = pto_ms(srtt_ms)
    # 🩸 H7 (2026-08-18 감사): base 는 srtt 에서 나오는데 t_fast 는 별도 기본값
    # (rtt_prior_ms=100)을 쓰고 있었다. pto_ms(srtt)=3*srtt 이므로 캐시가
    # srtt<66.7ms 를 물려주면 **전멸(PTO)이 부분 손실보다 싸진다** - fp/ft 를
    # 나눈 이유의 정반대다 (실측: srtt=30 이면 PTO 90ms vs 빠른경로 200ms).
    # 두 값은 같은 RTT 추정에서 나와야 한다.
    rtt_for_fast = srtt_ms if srtt_ms is not None else rtt_prior_ms
    t_fast = 2.0 * rtt_for_fast
    # 부분 손실이 전멸보다 비쌀 수는 없다 - 구조적 불변식으로 못박는다.
    t_fast = min(t_fast, base)

    # 인증서 플라이트는 이미 ACK 경로가 열려 있어 PTO 가 아니라 시간임계 회복이다.
    if side == "server_certs":
        base = t_fast

    byte_ms = cfg.symbol_bytes * 8.0 / cfg.rate_bps * 1000.0
    # 🩸 H2: 데이터 구간의 rho_max 를 쓰면 K=2 에서 후보가 {0,1} 로 잘린다.
    rho = getattr(cfg, "handshake_rho_max", cfg.rho_max)
    r_max = min(max(int(math.ceil(k * rho)), 1), max(255 - k, 0))

    best = None
    table = []
    for r in range(r_max + 1):
        n = k + r
        pmf = ch.erasure_pmf(n)
        f = sum(pmf[r + 1:])
        ft = pmf[n] if ack_partial else f
        fp = f - ft
        cost = r * byte_ms + fp * t_fast + ft * base
        table.append((r, cost, f))
        if best is None or cost < best[1] - 1e-12:
            best = (r, cost, f, ft)

    r_star, cost, f, ft = best
    # 상한이 실제로 답을 잘랐는지 기록한다. 이걸 안 남겨서 "비용 최소화"라고
    # 보고한 값이 사실은 임계값이었던 것을 오래 못 봤다 (H2).
    _cap_bound = (r_star == r_max and r_max > 0)
    t_eff = ((f - ft) * t_fast + ft * base) / f if f > 0 else base
    d = Decision(k=k, r=r_star, p_used=p_prior, burst_used=burst_prior,
                 g=0.0, t_recover_ms=t_eff, p_fail=f, cost=cost, table=table)
    d.cap_bound = _cap_bound
    return d
