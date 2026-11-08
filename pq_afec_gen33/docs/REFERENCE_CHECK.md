# 참고문헌 내용 대조

카드 F09(원천 RT-27). 대조 날짜 2026-11-07.

대상은 보고서 원고 content.py의 REFS 키 26개 전부다. 행 번호는 보고서 작업 폴더의 원고 기준이다(로컬 보존). 저장소의 `report_repro/content.py`는 첫 줄만 빠진 같은 본문이라 행 번호가 1씩 작다. 원문은 공개된 판을 웹으로 열어 대조했다. 원문 문장은 옮기지 않고 위치와 요지만 적는다.

## 1. 대조표

| 키 | 인용 문장 위치(content.py 행) | 원문 위치(쪽, 절) | 확인 날짜 | 상태 |
|---|---|---|---|---|
| rfc9000 | 79, 85, 91, 93, 101, 102 | RFC 9000 §8.1, §14.1 | 2026-11-07 | 일치 |
| rfc9001 | 79, 91 | RFC 9001 초록, §5, §5.2 | 2026-11-07 | 일치 |
| rfc9002 | 134, 210 | RFC 9002 §5.3, §6.2.1, §7.2 | 2026-11-07 | 일치 |
| rfc9846 | 79 | RFC 9846 표지와 초록 | 2026-11-07 | 일치 |
| fips203 | 79, 89 | FIPS 203 표지, §8 Table 3(PDF 48쪽) | 2026-11-07 | 일치 |
| rfc10024 | 79, 89 | RFC 10024 표지, §4.1, §4.2, §4.3 | 2026-11-07 | 일치 |
| nawrocki | 85, 93, 100, 102 | arXiv:2211.02421v1 초록(1쪽), §2(2쪽), §3.2(3쪽), §4.1(3~4쪽), §4.2(4쪽) | 2026-11-07 | 일치 |
| kampanakis | 85, 100, 102 | Amazon Science 공개 사본 §2.1(3쪽부터, QUIC 부분은 5~7쪽의 Fig. 3, Fig. 4와 대책 목록) | 2026-11-07 | 일치 |
| mcmanus | 85, 93, 100, 102 | Fastly 글의 'The problem', 'The dataset', 'The analysis' 절 | 2026-11-07 | 일치 |
| cf2022 | 79, 101 | Cloudflare 글의 'Where things might break in practice' 아래 'Fragmented ClientHello' | 2026-11-07 | 일치 |
| kempf | 80, 206 | arXiv:2405.09264 §V-E(6~7쪽) | 2026-11-07 | 일치 |
| paquin | 80 | 저자 공개 사본 초록(1쪽), 6쪽(측정 방법), 12쪽(결론) | 2026-11-07 | 일치 |
| montenegro | 80 | 저자 공개 사본 §4.3 Table 6(7쪽), §5.5(12쪽부터), 본문 문자열 검색 | 2026-11-07 | 일치 |
| sakk | 80 | MDPI 공개 본문의 초록, §3.5, §3.6, §3.7 | 2026-11-07 | 일치 |
| herzinger | 96, 103 | arXiv:2610.32356v1 초록, §II-D, §IV-B, §IV-C | 2026-11-07 | 일치 |
| langley | 96, 103, 207 | 저자 공개 PDF §7.3(11~12쪽, 학회 판 193~194쪽) | 2026-11-07 | 일치 |
| quicfec | 96, 103 | arXiv:1904.11326v1 §III-A | 2026-11-07 | 일치 |
| rquic | 96, 103 | 칸타브리아 대학 저장소의 저자 공개 사본 §III-A 2항(Adaptive FEC), §III-B | 2026-11-07 | 일치 |
| rfc9265 | 96 | RFC 9265 §1, §6.3 | 2026-11-07 | 일치 |
| bolot | 96 | INFOCOM'99 초록, 1998 UMass 기술보고서 판의 서론과 결론(검색 도구 수집본) | 2026-11-07 | 일치 |
| boutremans | 96 | EPFL 저자 사본 초록(1쪽), §I(1쪽) | 2026-11-07 | 일치 |
| gilbert | 95 | §II 'The Model'(1254~1255쪽, archive.org OCR 판) | 2026-11-07 | 일치 |
| elliott | 95 | §V(1985~1986쪽), §VI(1988쪽, archive.org OCR 판) | 2026-11-07 | 일치 |
| reed | 95 | 300쪽, 301~302쪽(웹에 올라온 학술지 판 사본) | 2026-11-07 | 일치 |
| quicgo | 91 | quic-go v0.61.0 태그의 internal/protocol/params.go, v0.61.0 release 페이지 | 2026-11-07 | 일치 |
| liboqs | 120 | liboqs-python GitHub 태그 목록과 PyPI 판 이력, liboqs(C) GitHub 태그 목록 | 2026-11-07 | 어긋남 |

상태 집계: 일치 25, 어긋남 1(liboqs), 미확인 0.

## 2. 항목별 요지

원고 쪽은 인용 문장이 말하는 내용, 원문 쪽은 대조에서 확인한 내용이다.

| 키 | 원고가 말한 것 | 원문에서 확인한 것 |
|---|---|---|
| rfc9000 | 3배 제한, 폐기된 packet의 datagram도 수신 바이트, Initial 1,200 B | §8.1 3배 제한과 고유 귀속 datagram 전부 계산. §14.1 1,200 B로 확장 |
| rfc9001 | TLS를 QUIC으로 운반, Initial 키는 DCID에서 유도해 관측자가 복호 | §5.2 client DCID에서 유도. §5 Initial은 기밀성 보호로 보지 않음 |
| rfc9002 | PTO 표본이 있으면 3·RTT, 권장 initial window 10 packet | 첫 표본에서 rttvar는 RTT/2, Initial 공간은 max_ack_delay 0이라 3·RTT는 PTO 식의 귀결. §7.2 권장 initial window는 10·max_datagram_size에 상한을 둠 |
| rfc9846 | TLS 1.3 규격 | E. Rescorla, 2026년 7월, RFC 8446을 대체하는 TLS 1.3 |
| fips203 | 2024년 표준화, ek 1,184 B, ct 1,088 B, ss 32 B | 2024년 8월 발행. Table 3의 ML-KEM-768 값이 같음 |
| rfc10024 | X25519MLKEM768 규정, client 1,216 B, server 1,120 B, shared secret 64 B | 2026년 8월. §4.1 client share 1,216 B, §4.2 server share 1,120 B, §4.3 shared secret 64 B |
| nawrocki | chain 35%가 4,071 B 초과, Initial 1,362 B에서 38%가 multi-RTT, 약 1% 개선과 도달성 감소 | 35%가 3·1,357 B 초과. 1,362 B에서 38%. 약 1% 증감, 큰 Initial에서 도달성 1.2% 감소. 본문에 FEC와 parity가 나오지 않음 |
| kampanakis | 3배 제한이 왕복을 더함, ClientHello 인위적 확대는 자원 낭비 | NIST 선정 서명은 모두 창을 넘음. 대책 넷째(ClientHello 확대)를 낭비로 평가 |
| mcmanus | 3배 제한의 왕복, client Initial 확대 효과를 TCP 표본 환산 모형으로 제시 | TCP 스택의 인증서 표본을 QUIC 크기로 계산. QUIC 실측은 없음 |
| cf2022 | Kyber 크기 key share가 ClientHello를 보통 두 packet으로 나눔 | 'Fragmented ClientHello' 절에 같은 내용 |
| kempf | RTT 0.1 ms 미만 망에서 Kyber TTFB 측정 | §V-E에서 RTT 0.1 ms 미만이라 왕복을 무시하고 TTFB를 정의 |
| paquin | TCP 위 TLS, 손실 3~5% 초과에서 다중 packet 알고리즘 영향 증가 | 초록에 같은 내용. 측정은 TCP 연결 반복 |
| montenegro | QUIC과 TLS의 손실 민감도 비교, X25519MLKEM768 없음, anti-amplification limit 논의 없음 | §5.5 손실 분석. Table 6의 X25519 hybrid는 x25519_mlkem512뿐. amplif는 일반 동사로만 나옴 |
| sakk | LoRa 조건 해석 모형에서 packet 수가 늘면 전달 성공 확률 하락 | §3.5 packet 수 모형, §3.7 독립 packet 성공확률 p에서 handshake 성공확률을 packet 수의 거듭제곱으로 계산, §3.6 끝에서 이 모형을 1차 해석 근사로 밝힘. 초록: LoRa에서 ML-KEM handshake 최대 62 packet, packet 전달 99% 근처에서 성공 약 50% |
| herzinger | IKEv2 fragment에 RaptorQ, 목적은 손실 흡수, amplification credit은 다루지 않음 | §IV-B FEC로 손실 흡수. amplification은 QUIC의 배경 제약(§II-D, §IV-C)으로만 나옴 |
| langley | XOR FEC는 이득이 작아 2016년 초 제거 | §7.3 이득 부족과 코드 복잡도 두 이유로 2016년 초 제거 |
| quicfec | handshake가 끝나기 전 FEC frame을 보내지 않음 | §III-A에 같은 내용. repair symbol을 암호화와 인증 뒤에 보내기 때문 |
| rquic | residual loss에 따라 비율 조절, STREAM packet에 적용 | §III-A 2항 재전송 비율로 잰 residual loss가 목표를 넘으면 FEC ratio를 바꿈(측정 주기 3·RTT). §III-B STREAM frame을 담은 packet에만 FEC를 적용 |
| rfc9265 | FEC가 혼잡 신호를 가려서는 안 됨 | §1 같은 취지. §6.3 복구된 packet도 혼잡 관점에서는 손실 |
| bolot | 품질 함수를 최적화해 FEC 양을 고르는 Internet telephony 사례 | 초록: 제약 최적화로 주관적 음질을 최적화 |
| boutremans | 위와 같음 | 초록: 지연과 왜곡으로 만든 품질 척도를 최적화하는 joint 제어 |
| gilbert | 2상태 Gilbert-Elliott 모형 | §II G와 B 두 상태 Markov chain, 오류는 B에서만 |
| elliott | 2상태 Gilbert-Elliott 모형 | §V Gilbert 모형 분석, §VI G 상태 오류를 허용하는 일반화 |
| reed | Reed-Solomon 부호는 parity 수만큼 erasure 복원 | erasure라는 말은 없음. 오류 없는 m개 값만으로 계수를 정하는 Vandermonde 논증이 같은 성질 |
| quicgo | 기본 Initial 크기 W = 1,280 B | v0.61.0의 InitialPacketSize 상수가 1280 |
| liboqs | ML-KEM 연산 측정은 liboqs-python 0.15.0 | liboqs-python 공개 판에 0.15.0이 없음. 0.15.0은 liboqs(C) 태그 |

## 3. 서지 대조

18개 키(nawrocki, kampanakis, kempf, paquin, montenegro, sakk, langley, quicfec, rquic, rfc9265, bolot, boutremans, gilbert, elliott, reed, fips203, rfc9846, rfc10024)는 DOI로 Crossref 메타데이터를 조회했다. 제목, 저자, 게재처, 권, 쪽, 연도가 원고 REFS와 같았다. herzinger는 arXiv 서지(2026-10-23 제출, 저자 6명)와 같다. mcmanus(2020-05-18, McManus)와 cf2022(2022-10-03, Westerbaan과 Rubin)는 글에 적힌 날짜와 저자가 같다. rfc9000, rfc9001, rfc9002, quicgo, liboqs는 Crossref를 조회하지 않았고 1절의 원문 대조만 했다.

## 4. 어긋남과 대조 범위

liboqs. 원고 120행과 REFS의 'liboqs-python (Version 0.15.0)'은 공개 판에 없는 번호다. liboqs-python의 GitHub 태그는 0.12.0(2025-01-16) 다음이 0.16.0(2026-07-23)이고, PyPI 판 이력에는 0.16.0, 0.16.0.1, 0.16.0.2만 있다. 0.15.0은 C 라이브러리 liboqs의 태그(2025-11-14)다. 팀 초안의 참고문헌 [14]는 'liboqs (ver. 0.15.0)'과 liboqs 저장소 주소를 적었다(보고서 작업 폴더의 팀 초안 텍스트, 로컬 보존). 설치본이 태그 사이의 저장소 판이었는지는 공개 기록으로 가릴 수 없다. 정오표 행 후보는 아래와 같고, 교내 서버에서 `oqs.oqs_version()`과 `oqs.oqs_python_version()` 값을 확인한 뒤 적용한다.

- 120행 old: "ML-KEM 연산 측정은 liboqs-python 0.15.0{c:liboqs}이다."
- 120행 new 후보: "ML-KEM 연산 측정은 liboqs 0.15.0{c:liboqs}을 Python 바인딩(liboqs-python)으로 호출하였다."
- REFS old: "Open Quantum Safe. liboqs-python (Version 0.15.0) [Computer software]. https://github.com/open-quantum-safe/liboqs-python"
- REFS new 후보: "Open Quantum Safe. liboqs (Version 0.15.0) [Computer software]. https://github.com/open-quantum-safe/liboqs"

rquic은 GLOBECOM 2019의 IEEE 판이 유료라 열지 않았고, 칸타브리아 대학 저장소의 저자 공개 사본으로 대조했다. 공개 사본과 IEEE 출판본의 차이는 대조하지 않았다.

고칠 필요는 없지만 적어 둔다. langley 96행은 제거 이유로 이득 부족만 적었고 원문은 코드 복잡도도 함께 든다. sakk의 '해석 모형'은 §3.6과 §3.7의 확률 모형을 가리키며, 저자들도 이 모형을 채널 모형이 아닌 1차 근사로 둔다.
