# 선행 조사 검색 기록

카드 F08(원천 RT-21). 작성 2026-11-07. 마지막 실제 검색 날짜는 2026-11-07이다.

보고서 원고의 두 문장(요약문 연구 필요성 22행, Ⅰ-3 연구 범위 85행)과 Table 1의 '대체' 행(104행)은 같은 대체를 다룬 문헌을 찾지 못했다고 쓴다. 이 기록은 그 문장이 어느 범위의 검색에서 나왔는지 남긴다. 행 번호는 보고서 작업 폴더의 원고 content.py 기준이다(로컬 보존). 첫 줄만 빠진 같은 본문이 `report_repro/content.py`에 있어 그쪽 행 번호는 1씩 작다.

## 1. 무엇을 같은 대체로 보나

같은 대체는 client가 서버의 anti-amplification credit을 사려고 보내는 uplink 바이트를 padding 대신 parity(repair) datagram으로 보내서, 서버 예산 확보와 erasure 복구를 한 바이트 회계로 묶는 설계다. 아래 네 가지는 같은 대체로 세지 않았다.

- 데이터 구간(0-RTT, 1-RTT, application data space)만 보호하는 QUIC FEC
- anti-amplification limit이 handshake에 왕복을 더한다는 문제 보고
- client Initial을 padding으로 키워 서버 예산을 넓히는 방법
- handshake 손실을 FEC로 흡수하지만 amplification credit을 다루지 않는 설계

앞의 세 가지는 보고서가 인용하는 선행이고 기여로 주장하지 않는다. 넷째에는 arXiv:2610.32356이 해당한다(6절).

## 2. 표를 읽는 법

- 앱 검색(N01~N12)은 web.run 검색 도구에 도메인 필터를 건 웹 색인 검색이다. DB 칸의 도메인이 제공하는 자체 검색 화면을 쓴 것이 아니다.
- Claude 검색(CL-01~CL-13)도 웹 색인 검색이다. WebSearch(일부 도메인 필터)와 Exa 검색을 썼다. CL-01~CL-11은 같은 날 앞 단계 조사에서, CL-12와 CL-13은 이 문서를 쓰면서 실행했다.
- 건수는 도구가 돌려준 고유 URL 수다. 관련 문헌 수가 아니고 부재 증명도 아니다. 반환 목록에는 무관한 결과가 섞여 있고, 전체 적중 수는 어느 도구도 주지 않았다.
- Google Scholar 자체 검색은 하지 않았다. ACM DL, IEEE Xplore, arXiv, Datatracker의 자체 검색 화면도 쓰지 않았다. ACM 도메인 필터 질의(N05, N06)는 무관한 결과만 돌려주었으므로 ACM DL 쪽 범위는 사실상 비어 있다.
- 과거 기록(2026-08~10)은 질의 원문과 건수가 남아 있지 않다. 원래 날짜를 그대로 두고 건수는 '미보존'으로 적었다.
- 11월 5일 검색은 기록이 없어 재구성하지 않았다.

## 3. 과거 기록 (원래 날짜, 로컬 보존)

원본은 gen1 저장소의 docs/선행연구 대조.md(A부, B부)와 v33 감사 결과 audit-prior-art.md(감사 묶음 A7)이다. 둘 다 이 저장소 밖에 있는 로컬 보존 문서이고 이번에 고치지 않았다.

| 날짜 | DB | 검색어 | 건수 | 검토 후보 | 왜 같은 대체가 아닌가 |
|---|---|---|---:|---|---|
| 2026-08-14 | 웹 문헌 조사, DB별 기록 없음 (B부, 로컬 보존) | 미보존. 옛 연구 질문 'PQC handshake를 표적한 적응형 FEC' 기준. 철회된 §0 원문에 표적 재검색 8회 이상이라고만 적힘 | 미보존 (문헌 지도 15편, 카탈로그 41건이라고 적힘) | QUIC-FEC, FlEC, rQUIC, Google QUIC(SIGCOMM'17 §7.3), RFC 9265, Cloudflare 2022와 2024, Paquin 2020, Kempf 2024, quicly #639, RFC 2140과 RFC 9040, RFC 9959, RFC 9002 §6.2.2, Bolot 1999, Boutremans 2003 | 옛 질문 기준이라 amplification credit 축이 없다. 이 판의 신규성 판정(§0)은 2026-08-30에 철회됐다. |
| 2026-08-28 | 웹 문헌 조사, DB별 기록 없음 (A부, 로컬 보존) | 미보존. 5 각도 병렬 조사와 충돌 후보 15건 원문 대조라고 적힘 | 미보존 | Nawrocki 2022, Kampanakis와 Lepoint 2023, Kampanakis quic@ 메일 2023-12, Kempf 2024, McManus 2020, quicwg base-drafts #3494, draft-an-fast-address-validation-00, 'Surfing the Web quicker than QUIC via a shared Address Validation', quic@ '5x' 제안 스레드 2024-07, 3GPP Padding BSR, US7793193B2, PadSteg, QUIC-FEC, FlEC, draft-michel-quic-fec, rQUIC, draft-zheng-quic-fec-extension-00, Adaptive FEC for delay-sensitive QUIC(2024-05), ReACKed QUICer, postquantum.com 블로그 | 문제 층(왕복 추가)과 lever 층(client 바이트로 예산 확보)은 선행이 있어 인용 대상이다. padding을 parity로 바꾸는 교환은 찾지 못했다고 적었다. A부가 padding 자리를 다른 용도에 쓰는 발상의 계보로 적은 Padding BSR, US7793193B2, PadSteg는 목적이 각각 스케줄링, 단방향 방송의 오류 정정, 은닉이다. ReACKed QUICer는 원문에 FEC가 없고 RTT 추정과 PTO가 대상이다. |
| 2026-08-30 | 새 검색 없음 (B부 재정리, 로컬 보존) | 해당 없음 | 해당 없음 | B부 §0~§5 재분류 | 08-14 판정을 철회하고 A부로 대체했다. 후보 목록은 늘지 않았다. |
| 2026-10-30 | 문헌과 구현 소스 대조 (audit-prior-art, 로컬 보존). quic-go v0.61.0, Google quiche, Cloudflare quiche, msquic 소스 포함 | 미보존 | 미보존 | Flach 외 SIGCOMM'13(Proactive 중복 전송), Google quiche CHP1/CHP2(discard transport parameter), draft-zheng-quic-fec-extension-02, draft-roca-nwcrg-rlc-fec-scheme-for-quic-03, draft-ietf-tls-key-share-prediction-05, RFC 9000 §8.1, Nawrocki 2022, Buchet와 Pelsser TMA 2025, ReACKed QUICer, Mücke 외 'Waiting for QUIC' | parity 대체를 한 문헌은 없었다. 다만 A7-07은 byte-identical 중복 Initial이 표준 서버에서도 같은 credit과 손실 복구를 준다고 지적했고, CHP1/CHP2는 ClientHello 안 padding으로 first flight를 키우는 실험 옵션이다. A7-18은 QUIC FEC 초안들이 transport parameter 협상 뒤에 동작해 client first flight를 원리상 보호하지 못한다고 정리했다. |

A부 A7절(문구 가이드)에는 '표준 변경 없이 client만 고쳐서 배포할 수 있다'는 문장이 있다. 2026-10-30 감사의 A7-07이 이것을 정정했다. 복구에는 서버 decoder가 필요하고, decoder가 없는 표준 서버에서 parity datagram은 padding과 같은 credit만 준다. 이 기록은 그 문장을 현재의 배포 사실로 옮기지 않는다.

A부 A5절의 'QUIC FEC 계열은 모두 handshake를 명시적으로 제외한다'는 일반화도 옮기지 않는다. 원문으로 확인한 것은 QUIC-FEC §III-A와 draft-michel-quic-fec-01 §8 두 곳이다(6절).

## 4. 2026-11-07 앱 검색 (N01~N12)

원 기록은 인계 폴더 runs/app_independent_reviews의 F08_app_search_handoff.md, F08_app_search_queries.json, F08_app_search_counts.py, F08_recent_candidates_review.md다(로컬 보존). 건수는 F08_app_search_counts.py로 다시 셀 수 있고, 2026-11-07에 다시 돌려 12행 모두 같은 수를 얻었다. DB 칸은 모두 '도메인 필터 웹 색인'이고 건수는 반환 고유 URL 수다.

| 날짜 | DB | 검색어 | 건수 | 검토 후보 | 왜 같은 대체가 아닌가 |
|---|---|---|---:|---|---|
| 2026-11-07 | 도메인 필터 웹 색인 (arxiv.org) | QUIC handshake FEC anti amplification | 8 | QFAM 2412.08936, QUICsand 2109.01106, TurboRetry 2608.02264, DoQ 2202.02987, 나머지 4건 무관 | 반환 제목 기준으로 handshake flood 방어와 측정 논문이다. 원문은 열지 않았다. |
| 2026-11-07 | 도메인 필터 웹 색인 (arxiv.org) | QUIC padding parity amplification credit | 7 | Nawrocki 2211.02421, QUIC padding privacy 2203.07806, QFAM, Kempf 2405.09264, 나머지 3건 무관 | Nawrocki는 문제 층 선행, Kempf는 PQC 전송 비용 측정 선행으로 인용한다. 두 본문에는 FEC와 parity가 나오지 않는다(F09 대조 때 확인). padding privacy 논문은 제목 기준으로 traffic analysis 방어가 목적이다. |
| 2026-11-07 | 도메인 필터 웹 색인 (datatracker.ietf.org) | QUIC FEC Initial handshake | 16 | RFC 9000, RFC 9312, draft-zheng-quic-fec-extension-00/01/02, IETF 115 TDD 슬라이드, IETF 118 Huawei FEC 슬라이드, IETF 123 ReACKed QUICer 슬라이드 | draft-zheng-02 §2~4는 transport parameter 협상과 stream 데이터의 source, repair 전송이다. padding을 parity로 바꿔 credit을 사는 설계는 읽은 범위에 없다. |
| 2026-11-07 | 도메인 필터 웹 색인 (datatracker.ietf.org) | QUIC amplification padding | 17 | RFC 9000, draft-ietf-quic-manageability 여러 판, RFC 9250, draft-lcurley-moq-probe-00, IETF 109 issue 정리, IETF 116 Nawrocki 슬라이드 2건 | 규칙 문서와 측정 발표다. 같은 문서의 여러 판이 따로 세어져 고유 URL 수가 고유 문헌 수보다 많다. |
| 2026-11-07 | 도메인 필터 웹 색인 (dl.acm.org) | QUIC forward error correction handshake | 6 | 6건 모두 무관 | ACM DL 자체 검색이 아니므로 이 결과로 ACM 문헌의 부재를 말하지 않는다. |
| 2026-11-07 | 도메인 필터 웹 색인 (dl.acm.org) | TLS certificates QUIC performance padding | 4 | 4건 모두 무관 | 위와 같다. |
| 2026-11-07 | 도메인 필터 웹 색인 (arxiv.org) | Embedding Large PQC KEMs in IKEv2 FEC | 10 | arXiv:2610.32356, 나머지 9건 무관 | IV-B는 IKEv2 fragmentation에 RaptorQ FEC를 넣어 손실을 흡수한다. IV-C의 QUIKE는 QUIC을 handshake 운반에 쓴다. amplification credit을 parity로 사는 설계가 아니다. |
| 2026-11-07 | 도메인 필터 웹 색인 (fastly.com) | QUIC handshake compression padding | 18 | McManus 2020 Fastly 글(언어판 3개), 저자 페이지, 'The Maturing of QUIC', 문서 아카이브 | client Initial을 키워 서버 응답 예산을 늘리는 방식을 직접 논한다. lever 층 선행이고 FEC parity 교환은 없다. |
| 2026-11-07 | 도메인 필터 웹 색인 (datatracker.ietf.org) | "Forward Erasure Correction" QUIC | 18 | draft-michel-quic-fec-00/01, draft-dmoskvitin-quic-short-message-fec-00, draft-dmoskvitin-quic-adaptive-fec-00, draft-ramadan-moq-fec-core-00, IETF 104, 115, 118 FEC 슬라이드 | draft-michel §8은 0-RTT와 1-RTT payload가 대상이다. dmoskvitin 두 초안은 application data space 한정이고 padding은 코딩 크기 정렬용이다. |
| 2026-11-07 | 도메인 필터 웹 색인 (arxiv.org) | "QUIC-FEC" handshake | 4 | QUIC-FEC 1904.11326, arXiv:2607.14482, FlEC 2208.07741, arXiv:2608.14593 | QUIC-FEC §III-A는 handshake가 끝나기 전 FEC frame을 보내지 않는다. 2607.14482는 MPQUIC DATAGRAM payload, 2608.14593은 application-data 블록이고 그 'Initial Phase'는 QUIC Initial packet이 아니다. FlEC는 이번에 원문을 열지 않았다(2026-08-28 기록은 데이터 구간으로 분류). |
| 2026-11-07 | 도메인 필터 웹 색인 (arxiv.org) | "ReACKed QUICer" | 1 | arXiv:2410.20602 | 2026-08-28 원문 대조에서 FEC가 없고 instant ACK와 RTT, PTO가 대상임을 확인했다. |
| 2026-11-07 | 도메인 필터 웹 색인 (arxiv.org) | "A Quantum of QUIC" | 1 | arXiv:2405.09264 | QUIC 암호 비용 측정이다. §V-E의 PQC 측정은 RTT 0.1 ms 미만 환경이고 본문에 FEC와 parity가 나오지 않는다. |

## 5. 2026-11-07 Claude 웹 검색 (CL-01~CL-13)

반환 URL은 부록에 남겼다.

| 날짜 | DB | 검색어 | 건수 | 검토 후보 | 왜 같은 대체가 아닌가 |
|---|---|---|---:|---|---|
| 2026-11-07 | 웹 색인 (WebSearch extended, 필터 없음) | QUIC Initial forward error correction parity anti-amplification limit post-quantum ML-KEM handshake | 9 | arXiv:2610.32356, RFC 9002, IETF 115 TDD 슬라이드, Nawrocki 2211.02421, Fastly 'The Maturing of QUIC', draft-tsvwg-quic-protocol-02, arXiv:1809.04822, USPTO 특허 2건 | 직접 일치가 없다. 1809.04822와 Fastly 회고는 데이터 구간 FEC와 gQUIC XOR FEC의 역사다. 2610.32356은 6절 표 참고. |
| 2026-11-07 | 웹 색인 (WebSearch, 필터 없음) | replace QUIC Initial padding with FEC repair packets amplification credit | 10 | QUIC-FEC 1904.11326, NWCRG 슬라이드(IETF 104, 105, 106), quic@ 'Padding in Initial Packets' 메일, cps-vo 서지 2건, QUIC symposium 2019 슬라이드, draft-roca-nwcrg-rlc-fec-scheme-for-quic-02 | QUIC-FEC 계열의 padding 이야기는 source symbol 크기를 맞추는 zero-padding이고 그 padding은 보내지 않아도 된다는 내용이다(IETF 104 슬라이드). repair는 별도 frame(FEC frame, REPAIR frame)에 실린다. |
| 2026-11-07 | 웹 색인 (WebSearch, datatracker.ietf.org 필터) | QUIC FEC Internet-Draft 2026 | 10 | ack-frequency, extended-key-update, qmux, iquic, moq-mmt, reverso, multicast 초안, arXiv:1809.04822 | 2026년 QUIC 자체 FEC 초안은 나오지 않았다. moq-mmt 초안이 MoQ FEC 초안을 인용한다. |
| 2026-11-07 | Exa 웹 검색 | paper that sends FEC parity datagrams in the QUIC client first flight so the server's anti-amplification budget grows, instead of padding | 10 | QUIC-FEC html, arXiv:1809.04822, draft-michel-quic-fec-01, RFC 9265, NWCRG IETF 105 슬라이드, FlEC(ToN 2022), draft-tsvwg-quic-protocol-01, quic-issues #3445 메일, QUIRL(ToN 2024), Holzinger 외 IFIP Networking 2025 | 모두 데이터 구간 FEC이거나 규칙 논의다. #3445 메일은 client가 PTO 때 보낼 packet으로 순수 padding을 선호한다는 의견이다. Holzinger 외는 HTTP/3 stream 데이터에 Tetrys FEC를 쓴다(초록 확인). |
| 2026-11-07 | Exa 웹 검색 | post-quantum TLS over QUIC handshake anti-amplification limit extra round trip mitigation 2025 2026 study | 10 | Montenegro 외 2026(Computer Networks), arXiv:2603.28728(조사 논문), IETF 116 Nawrocki 슬라이드, quantumnetwork.ch 해설(2026-11-06), Cloudflare broadcast 주소 글(2025-02-10), Cloudflare Connect 2026, arXiv:2603.11006, arXiv:2401.06657, quantumsequrity.com 해설(2026-07-30), Zhao 2026-10-29(doi 10.54097/wyn6tw24) | 측정과 해설이다. 언급된 대책은 인증서 체인 축소와 압축, address validation token, 인증서 별도 배포, Retry다. Zhao는 TCP 위 TLS 1.3 측정이다(초록 기준). FEC나 parity로 credit을 사는 제안은 반환 요약에 없다. |
| 2026-11-07 | 웹 색인 (WebSearch, arxiv.org 필터) | QUIC handshake erasure coding Initial packets loss post-quantum ClientHello redundancy | 10 | arXiv:2410.20602, 2608.02264, 2511.08375, 2603.01091, 2401.06657, 2603.28728, 1904.11326, 2211.02421, 2505.12690, USPTO 특허 1건 | 직접 일치가 없다. |
| 2026-11-07 | 웹 색인 (WebSearch, mailarchive.ietf.org와 github.com 필터) | QUIC anti-amplification limit Initial FEC repair handshake | 9 | 구현 저장소 PR과 issue 7건, arXiv:2211.02421, arXiv:2410.20602 | 구현의 anti-amplification limit 준수 이슈다. FEC가 없다. |
| 2026-11-07 | 웹 색인 (WebSearch, 필터 없음) | draft-zheng-quic-fec-extension latest version 2026 | 7 | draft-zheng-quic-fec-extension -00, -01, -02 미러 | 최신판은 2026-03-16의 -02다. Datatracker는 만료된 개인 초안으로 표시하고, 원문 머리글의 만료일은 2026-09-17이다. 새 판은 없다. 내용 판단은 N03 행과 같다. |
| 2026-11-07 | Exa 웹 검색 | arXiv 2026 anti-amplification limit post-quantum certificates QUIC handshake round trips measurement | 10 | Chou와 Cao arXiv:2604.24869, Potuganam 복제 패키지(Zenodo 10.5281/zenodo.22878525, 22878524), Montenegro 저자 사본, Nawrocki 2211.02421, IETF 116 슬라이드, Kempf 2405.09264, arXiv:2603.11006, 2603.01091, 2606.16473 | 2604.24869는 TLS TTFB와 MTC를 다룬다. Potuganam 패키지는 ML-KEM QUIC handshake 측정이고 FEC, parity, 의도적 padding을 평가하지 않는다. 6절 표 참고. |
| 2026-11-07 | Exa 웹 검색 | use padding bytes for redundancy: send forward error correction instead of padding in handshake packets (QUIC, DTLS, TLS ClientHello) | 10 | NWCRG IETF 104 Michel 슬라이드, QUIC over DTLS 초안, ECH issue #264, draft-zheng-quic-fec-extension-01, RFC 9849, arXiv:1809.04822, draft-dmoskvitin-quic-adaptive-fec-00, ECH 초안 원문, TLS interim 2020 회의록, RFC 9001 | ECH의 padding은 길이 은닉이 목적이다. FEC 초안들은 application data space 한정이다. |
| 2026-11-07 | 웹 색인 (WebSearch, datatracker.ietf.org와 ietf.org 필터) | "QUIC" "FEC" handshake "Initial" draft-michel OR draft-dmoskvitin OR "forward erasure correction" 2025 | 9 | draft-dmoskvitin-quic-adaptive-fec-00, draft-zheng-quic-fec-extension-00, draft-michel-quic-fec-01, draft-dmoskvitin-quic-short-message-fec-00, TAROT arXiv:2602.09880, QUIC-FEC 1904.11326, draft-tsvwg-quic-protocol-02 | handshake에서 하는 일은 FEC 지원 협상뿐이고 보호 대상은 데이터다. TAROT는 video streaming FEC 조절이다. |
| 2026-11-07 | 웹 색인 (WebSearch standard, 필터 없음) | QUIC client Initial parity datagrams instead of padding anti-amplification limit server budget erasure recovery | 10 | Nawrocki 2211.02421, quic@ 'Padding in Initial Packets' 메일 2건, quic-issues 메일 3건(base-drafts #2181, #2519, #3051), Go x/net issue 70264와 commit 1건, NDSS 2023 논문 PDF 1건, nginx 소스 1건 | Initial 1,200 B 규칙, padding과 coalescing 논의다. 반환 요약 기준으로 parity나 erasure 복구를 다룬 결과가 없다. NDSS 논문은 열지 않았다. |
| 2026-11-07 | Exa 웹 검색 | 2026 paper or Internet-Draft: QUIC first flight sends repair (FEC) packets instead of PADDING so the 3x anti-amplification credit and loss recovery come from the same bytes | 10 | draft-zheng-quic-fec-extension-02, draft-michel-quic-fec-01, draft-dmoskvitin-quic-adaptive-fec-00, draft-swett-nwcrg-coding-for-quic-01(HAL 사본), FlEC(ToN 2022), QUIRL(ToN 2024), draft-ramadan-moq-fec-01(2026-10-26), draft-dmoskvitin-quic-short-message-fec-00, RFC 9002, QUIC-FEC(IFIP 2019) | 모두 데이터 구간 또는 media object FEC다. draft-swett는 6절 표 참고. draft-ramadan-moq-fec-01은 MoQ media object에 repair track을 붙인다. |

## 6. 원문을 연 후보와 판단

| 후보 | 연 날짜 | 확인한 범위 | 왜 같은 대체가 아닌가 |
|---|---|---|---|
| arXiv:2610.32356v1, Herzinger 외, 2026-10-23 제출 | 2026-11-07 (앱, Claude) | 초록, §II-D, §IV-B, §IV-C | IKEv2 fragment에 RaptorQ FEC를 넣어 손실을 흡수한다. amplification은 QUIC의 배경 제약으로만 나온다. 이 문헌이 있으므로 'PQC handshake에 FEC를 처음 썼다'는 넓은 주장은 할 수 없다. |
| QUIC-FEC, arXiv:1904.11326v1 | 2026-11-07 (앱, Claude) | §III-A | handshake가 끝나기 전에는 FEC frame을 보내지 않는다. repair symbol을 암호화와 인증 뒤에 보내기 때문이다. |
| draft-michel-quic-fec-01 | 2026-11-07 (앱) | §8 | 0-RTT와 1-RTT 암호화 수준의 payload가 대상이다. 만료된 개인 초안이다. |
| draft-zheng-quic-fec-extension-02 | 2026-11-07 (앱) | §2~4 | 협상 뒤 stream 데이터의 source, repair 전송이다. 모든 handshake FEC를 금지한다는 문장을 확인한 것은 아니다. |
| McManus 2020, Fastly 글 | 2026-11-07 (앱, Claude) | 본문 전체 | client Initial padding으로 서버 예산을 사는 lever 층 선행이다. parity 교환은 없다. |
| draft-dmoskvitin-quic-short-message-fec-00 | 2026-11-07 (앱) | 3, 4, 5.1~5.3, 6~7절 | application data space 한정이다. 5.1절 handshake 내용은 FEC 지원 협상이다. 복구 바이트 회신은 통계용이고 credit으로 정의되지 않는다. |
| draft-dmoskvitin-quic-adaptive-fec-00 | 2026-11-07 (앱) | 3, 4, 5.1~5.4, 6~7절 | application data space 한정이고 padding은 크기 정렬용이다. |
| arXiv:2607.14482v1 | 2026-11-07 (앱) | III-A~D, IV-A~F, V-A | MPQUIC DATAGRAM payload의 블록 FEC이고 transport header와 Initial은 보호하지 않는다. |
| arXiv:2608.14593v1 | 2026-11-07 (앱) | II, III-A, III-D, IV 도입부, IV-B~C, IV-E.1 | application-data 블록의 마감시간 기반 추가 repair다. 'Initial Phase'는 QUIC Initial packet이 아니다. |
| draft-swett-nwcrg-coding-for-quic-01 (2018, HAL 사본) | 2026-11-07 (Claude, CL-13) | 검색 도구가 돌려준 본문의 3.2, 3.3, 3.5, 4.1, 5.2절 | FEC scheme을 handshake 중 transport parameter로 협상하고, 보호 대상은 STREAM 데이터이며, repair는 REPAIR frame에 싣는다. |
| rQUIC, GLOBECOM 2019 저자 공개 사본 | 2026-11-07 (Claude, F09 대조) | §I~§III | STREAM frame을 담은 packet에만 XOR FEC를 적용하고 residual loss로 비율을 조절한다. 읽은 범위에 amplification과 Initial padding 논의가 없다. |
| Potuganam, Zenodo 10.5281/zenodo.22878525(2026-09-21)와 GitHub sudarsanSDA/quic-mlkem-benchmark | 2026-11-07 (Claude) | Zenodo 기록의 제목, 키워드, 파일 목록, 저장소 README | ML-KEM QUIC handshake 지연과 anti-amplification 측정 패키지다. FEC, parity, 중복 packet, 의도적 Initial padding을 평가하지 않는다. 논문 본문은 찾지 못했다. |
| Chou와 Cao, arXiv:2604.24869 | 2026-11-07 (Claude) | 초록, 서론 | TLS의 인증서 체인 크기와 TTFB, MTC를 다룬다. 읽은 범위에 FEC가 없다. |
| draft-ramadan-moq-fec-core-00, 2026-11-02 | 2026-11-07 (Claude) | 초록, 1절 | Media over QUIC의 media object에 repair track을 붙이는 방식이다. |
| Holzinger 외, IFIP Networking 2025 | 2026-11-07 (Claude) | 초록, 서론 | HTTP/3 stream 데이터에 Tetrys FEC와 스케줄러를 넣는다. |
| Kampanakis와 Lepoint 2023 | 2026-11-07 (Claude, F09 대조) | §2.1의 QUIC 부분, Amazon Science 공개 사본 5~7쪽 | 3배 창 대책 넷(창 확대, 인증 데이터 축소, token, ClientHello 인위적 확대)을 든다. ClientHello 확대는 자원 낭비로 평가한다. FEC나 parity는 없다. |
| Montenegro 외 2026 | 2026-11-07 (Claude, F09 대조) | 저자 사본 §4.3, §5.5, 본문 문자열 검색 | QUIC과 TLS의 PQ handshake 측정이다. anti-amplification limit 논의와 FEC가 없다. |

## 7. 결론과 정오표 대조

- 이 기록의 범위(3~5절)에서 같은 대체를 제안하거나 평가한 문헌을 찾지 못했다. 범위 밖의 존재 여부는 모른다.
- 같은 대체는 아니어도 기여 문장을 좁히는 선행이 있다. 2610.32356 때문에 'PQC handshake에 FEC를 처음 적용했다'고 쓸 수 없다. Nawrocki 2022, Kampanakis와 Lepoint 2023, McManus 2020 때문에 왕복 비용의 발견과 padding lever는 기여가 아니다. A7-07의 중복 전송과 quiche CHP1/CHP2는 같은 바이트를 다른 형태로 쓰는 대안이다.
- 마지막 실제 검색 날짜는 2026-11-07이다. 정오표 RT-21-1, RT-21-2의 new에 들어가는 날짜는 이 날짜와 같아야 한다. 다시 검색하면 이 기록, 정오표의 RT-21 new, 정오표 검사의 LITERAL 날짜 키를 같이 고친다.
- 제출 직전 재검색은 사람 또는 Claude 몫이다. 아직 하지 않은 것은 Google Scholar 자체 검색, ACM DL과 IEEE Xplore 자체 검색, 국내 DB(KCI, RISS) 검색, 특허 DB 자체 검색이다.

## 부록. CL 행이 돌려준 URL

CL-01: arxiv.org/html/2610.32356, quicwg.org/base-drafts/rfc9002.html, datatracker.ietf.org/meeting/115/materials/slides-115-tdd-sessb-layering-and-security-00, arxiv.org/pdf/2211.02421, www.fastly.com/blog/maturing-of-quic, image-ppubs.uspto.gov (11258823), datatracker.ietf.org/doc/html/draft-tsvwg-quic-protocol-02, image-ppubs.uspto.gov (11317456), arxiv.org/pdf/1809.04822

CL-02: arxiv.org/pdf/1904.11326, datatracker.ietf.org/meeting/106/materials/slides-106-nwcrg-04-roca-rlc-fec-scheme-for-quic-update-00.pdf, datatracker.ietf.org/meeting/105/materials/slides-105-nwcrg-03-roca-coding-for-quic-update-01.pdf, www.arxiv.org/pdf/1809.04822, mailarchive.ietf.org/arch/msg/quic/d_XhcXRB2UfCIUpxiAA_KGdNYSU, datatracker.ietf.org/meeting/104/materials/slides-104-nwcrg-05-michel-fec-quic-results-00.pdf, archive.cps-vo.org/node/68463, quic.edm.uhasselt.be/symposium19/files/7_FrancoisMichel_FEC.pdf, archive.cps-vo.org/biblio/author/13744, datatracker.ietf.org/doc/draft-roca-nwcrg-rlc-fec-scheme-for-quic/02

CL-03: datatracker.ietf.org/doc/html/draft-ietf-quic-ack-frequency, .../draft-ietf-quic-extended-key-update-02, .../draft-ietf-quic-qmux-00, .../draft-ietf-quic-extended-key-update-03, datatracker.ietf.org/doc/draft-x1co-httpbis-iquic, .../html/draft-ramadan-moq-mmt-00, datatracker.ietf.org/doc/draft-frochet-quicwg-reverso-for-quic, datatracker.ietf.org/doc/draft-jholland-quic-multicast, datatracker.ietf.org/doc/draft-ramadan-moq-mmt, arxiv.org/pdf/1809.04822

CL-04: arxiv.org/html/1904.11326v1, doi.org/10.48550/arxiv.1809.04822, datatracker.ietf.org/doc/html/draft-michel-quic-fec-01, www.rfc-editor.org/rfc/rfc9265.pdf, datatracker.ietf.org/meeting/105/materials/slides-105-nwcrg-03-roca-coding-for-quic-update-01, doi.org/10.1109/tnet.2022.3195611, datatracker.ietf.org/doc/html/draft-tsvwg-quic-protocol-01, mailarchive.ietf.org/arch/msg/quic-issues/2lu1GgqqKiD4RJNF5SY-d8mG1zc, doi.org/10.1109/tnet.2024.3453759, www.net.in.tum.de/fileadmin/bibtex/publications/papers/holzinger2025quic.pdf

CL-05: doi.org/10.1016/j.comnet.2025.111957, arxiv.org/html/2603.28728, datatracker.ietf.org/meeting/116/materials/slides-116-quic-revisiting-quic-handshakes-and-tls-deployment-about-three-challenges-00, quantumnetwork.ch/knowledge-base/edge-to-cloud/post-quantum-quic-http-3-ml-kem-how-does-it-work, blog.cloudflare.com/mitigating-broadcast-address-attack, www.cloudflare.com/connect/2026/session/securing-internet-traffic-for-the-quantum-computing-era, arxiv.org/html/2603.11006v2, arxiv.org/html/2401.06657v3, quantumsequrity.com/blog/quic-pqc-implementation, doi.org/10.54097/wyn6tw24

CL-06: arxiv.org/html/2410.20602v1, arxiv.org/html/2608.02264, arxiv.org/pdf/2511.08375, arxiv.org/html/2603.01091v1, arxiv.org/pdf/2401.06657v3, arxiv.org/pdf/2603.28728, image-ppubs.uspto.gov (11258823), arxiv.org/pdf/1904.11326, arxiv.org/pdf/2211.02421, arxiv.org/pdf/2505.12690

CL-07: github.com/vitorpamplona/quic-kmp/pull/7, github.com/nullstyle/quic-zig/pull/12, arxiv.org/pdf/2211.02421, github.com/JakeChampion/lang/pull/12468, github.com/cpkb-bluezoo/hopf/issues/491, github.com/s3B-a/singularity/issues/49, arxiv.org/pdf/2410.20602, github.com/Hakkadaikon/wired/issues/178, github.com/Dicklesworthstone/asupersync/issues/68

CL-08: datatracker.ietf.org/doc/draft-zheng-quic-fec-extension, ftp.sjtu.edu.cn (-02.txt), bgpupdates.potaroo.net (-00.xml), ftp.kaist.ac.kr (-02.txt), ftp.sjtu.edu.cn (-01.txt), bgpupdates.potaroo.net (-01.xml), ftp.sjtu.edu.cn (-02.xml)

CL-09: arxiv.org/html/2604.24869v1, doi.org/10.5281/zenodo.22878525, www.nics.uma.es/wp-content/papers/Monte2026pqc.pdf, doi.org/10.5281/zenodo.22878524, arxiv.org/pdf/2211.02421, datatracker.ietf.org/meeting/116/materials/slides-116-quic-revisiting-quic-handshakes-and-tls-deployment-about-three-challenges-00, arxiv.org/abs/2405.09264, arxiv.org/abs/2603.11006, arxiv.org/abs/2603.01091, arxiv.org/html/2606.16473

CL-10: datatracker.ietf.org/meeting/104/materials/slides-104-nwcrg-05-michel-fec-quic-results-00.pdf, martinthomson.github.io/quic-dtls, github.com/tlswg/draft-ietf-tls-esni/issues/264, datatracker.ietf.org/doc/html/draft-zheng-quic-fec-extension-01, www.rfc-editor.org/rfc/rfc9849.pdf, arxiv.org/pdf/1809.04822, datatracker.ietf.org/doc/html/draft-dmoskvitin-quic-adaptive-fec-00, tlswg.org/draft-ietf-tls-esni/draft-ietf-tls-esni.txt, datatracker.ietf.org/doc/bluesheets-interim-2020-tls-02-202009031000, datatracker.ietf.org/doc/rfc9001

CL-11: datatracker.ietf.org/doc/draft-dmoskvitin-quic-adaptive-fec, www.ietf.org/archive/id/draft-zheng-quic-fec-extension-00.html, datatracker.ietf.org/doc/draft-michel-quic-fec, datatracker.ietf.org/doc/html/draft-dmoskvitin-quic-adaptive-fec-00, www.ietf.org/archive/id/draft-dmoskvitin-quic-short-message-fec-00.xml, datatracker.ietf.org/doc/html/draft-michel-quic-fec-01, arxiv.org/pdf/2602.09880, arxiv.org/pdf/1904.11326, datatracker.ietf.org/doc/html/draft-tsvwg-quic-protocol

CL-12: arxiv.org/pdf/2211.02421, golang.org/issue/70264, mailarchive.ietf.org/arch/msg/quic/d_XhcXRB2UfCIUpxiAA_KGdNYSU, mailarchive.ietf.org/arch/msg/quic-issues/4J9tY3OgBmZGxeHQUhdCXoZAOdM, mailarchive.ietf.org/arch/msg/quic-issues/Qy6Fgoxr_bBtCwQdO1zSPTzgOqk, mailarchive.ietf.org/arch/msg/quic-issues/5ExKX6lKcYQ_GNPyprxi213euKk, mailarchive.ietf.org/arch/msg/quic/v0kO1KxIyF4x_RC2_2tuXRcRPc4, go.googlesource.com/net/+/770149e9886ec895bb824b608bd02d661fce552d, www.ndss-symposium.org/wp-content/uploads/2023-72-paper.pdf, mdounin.ru/hg/nginx/file/7a9ab6f7cea3/src/event/ngx_event_connect.h

CL-13: datatracker.ietf.org/doc/html/draft-zheng-quic-fec-extension, datatracker.ietf.org/doc/html/draft-michel-quic-fec-01, www.ietf.org/archive/id/draft-dmoskvitin-quic-adaptive-fec-00.html, inria.hal.science/hal-01919858/file/draft-swett-nwcrg-coding-for-quic-01.pdf, doi.org/10.1109/tnet.2022.3195611, doi.org/10.1109/tnet.2024.3453759, datatracker.ietf.org/doc/html/draft-ramadan-moq-fec-01, www.ietf.org/archive/id/draft-dmoskvitin-quic-short-message-fec-00.txt, quicwg.org/base-drafts/rfc9002.html, doi.org/10.23919/ifipnetworking.2019.8816838
