# T5 UDP 연결 결과

구현 검증이다. 서버 기본 경로를 udp-path=oob로 연결했고 basic도 명시 선택할 수 있다. 실제 quic-go가 ReadBatch를 통해 복호기를 호출한다. 물리 패킷과 보류 raw는 각자의 OOB를 유지하고, 복원본은 처음 복호 기록을 만든 parity의 packet-info만 사용한다. C1 회신도 그 주소에서 보낸다.

| 검증 | 결과 |
|---|---|
| Go·vet·race | 193개 통과, 새 UDP 시험 13개 |
| Python | 351개·하위 548개 통과 |
| 기본 ReadFrom | 700116사례·60설정, 고정 Python 참조와 바이트·회계 일치 |
| OOB ReadBatch | 같은 700116사례·60설정, 같은 참조와 일치 |
| 실제 QUIC | basic·oob 각각 33연결. 정상 30성공·의도한 c2s 전멸 3실패 |
| C1 산술 | 두 경로의 사후 평균 12개가 Python과 정확히 일치 |
| 수신 경계 | 6연결에서 잘못된peer12개·CID6개 거부. 계정 6개 완료·만료 |
| 실제 IPv4·IPv6 | 목적지 packet-info·ECN 수신, 복원본 ECN 제거, C1 출발지 보존 |
| quic-go 소켓 설정 | IPv4·IPv6 DF(PROBE)·ECN·packet-info 옵션 확인 |
| 실제 GSO | 2500 B 송신이 1200·1200·100 B로 수신됨. 분절 3개로 집계 |

GSO에는 segment별 연결 식별과 바이트·시각 기록을 적용한다. 서로 다른 계정이 한 송신 버퍼에 담긴 시험도 통과했다. EIO와 짧은 송신은 송신 계수·첫 송신 스냅숏·타임라인을 복구하고 그동안 갱신된 수신 계수는 유지한다. 재시도한 일반 송신을 두 번 세지 않는다.

기능 실행의 UDP 계수는 다음과 같다. 이 값과 HCT를 성능 비교로 해석하지 않는다. 소거 일정과 C1 검사 기준은 이전 단계와 같다.

| 경로 | 물리 ReadMsg | 복호 ReadBatch | WriteMsg | GSO 호출 | GSO 분절 | 송신 오류 |
|---|---:|---:|---:|---:|---:|---:|
| basic | 0 | 0 | 0 | 0 | 0 | 0 |
| oob | 392 | 392 | 287 | 30 | 30 | 0 |

초기 UDP 단위 시험 하나는 송신 packet-info를 수신 ControlMessage.Parse로 검사해 실패했다. 고정 x/net 소스에서 IPv4 Spec_dst와 수신 Addr의 위치가 다르고 Src는 송신 전용임을 확인했다. 송신 CMSG 구조를 직접 검사하도록 고쳤다. 실제 wildcard 회신 검사는 처음부터 통과했다. 실패 stage와 로그를 보존한다.

소스·실행 영수증은 runs/T5_udp_*에 있으며 빌드 4개를 T5_udp_build_records_v1에 보존했다. 정책 23파일은 T4 관문과 같고 공유 85파일에서 선언되지 않은 차이는 0건이다. 전체 근거는 g3/v33/validation/T5_udp_v1에 보존한다.

ReadBatch는 복호 결과 1개씩 반환한다. native recvmmsg 배치나 성능 동등성을 뜻하지 않는다. X3는 basic/oob를 같은 블록에서 비교해야 한다. 클라이언트는 기존 기본 PacketConn 경로를 유지한다. 재전송·Retry·다른 스택의 효과는 T6·M4·X7의 범위다. C1은 평문이며 헤더 검사로 인증되지는 않는다.

T5는 세 번째 partial이다. 남은 A3-14는 EXTRA_TASKS.md의 E17(k 추정과 flush 입력), E18(실제 대기·분할 관측)로 나눴다. 외부 의존 장애는 없어 부모 T5 안에서 바로 이어간다. 기본 타이머 300 us·lead-hold off·L1상태 4는 유지한다.
