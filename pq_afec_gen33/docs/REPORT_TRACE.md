# 보고서 출처 대조표

이 표는 보존한 감사 trace의 행 순서와 여섯 열을 그대로 옮겼다. 감사 판정 열은 당시 기록이며 이번 실행의 검증 결과가 아니다. 실제 파일을 다시 읽은 수치는 `report_repro/report_numbers.json`의 verified 항목에 있다. 수치 항목이 연결돼 있어도 그 행의 문장 전체를 검증했다는 뜻은 아니다.

원본 trace와 SHA-256은 `report_repro/trace_sources.json`에 보존한다. 외부 원문, 날짜의 의미, 서술형 주장처럼 자동 대조하지 않은 부분은 미확인으로 남는다.

| trace | content.py 줄 | 주장 | 보고서 값 | 출처 | 감사 값 | 감사 판정 | 이번 수치 대조 키 |
|---|---|---|---|---|---|---|---|
| T001 | 3 | 과제명 | ML-KEM 적용 시 전송 성능 개선을 위한 QUIC 기반 적응형 FEC 연구 | C:/dev/R-E/README.md 1행, VLT 프로젝트 노트 46행 | 같음, 팀 서명본은 다른 제목 | 일치, 팀 초안과 다름(RT-12) | 미확인: 자동 수치 대조 없음 |
| T002 | 10 | ML-KEM 연산 수십 µs | 24.1~28.2 | TEAM/data/ML-KEM_1단계_측정수치_v2.xlsx 2_연산시간 11행 | 24.1, 25.9, 28.2 | 일치 | 미확인: 자동 수치 대조 없음 |
| T003 | 10, 29, 162, 215 | 4,032 B에서 hybrid가 RTT의 95.0~99.3% 빠름 | 0.95, 0.984, 0.993, 0.989 | V4 3_RTT비례 E4:E7 | 9.5/10, 49.2/50, 99.3/100, 197.8/200 | 일치, RTT 50 행 출처 미해결(RT-08) | v4.rtt.row4, v4.rtt.row5, v4.rtt.row6, v4.rtt.row7 |
| T004 | 11, 31, 172, 215 | X25519 손실 5% 처리 없음→결합 | 114.59→52.98 | G2/p14_dominance.json arms[loss=5].ms | 114.5896, 52.9809 | 일치 | p14.base.loss0, p14.base.loss0.metadata, p14.pad.loss0, p14.pad.loss0.metadata, p14.parity.loss0, p14.parity.loss0.metadata, p14.combo.loss0, p14.combo.loss0.metadata, p14.base.loss5, p14.base.loss5.metadata, p14.pad.loss5, p14.pad.loss5.metadata, p14.parity.loss5, p14.parity.loss5.metadata, p14.combo.loss5, p14.combo.loss5.metadata |
| T005 | 12, 32 | v3.1 두 조건 | 28.01, 12.38 | V31/experiments/results/p31_gencompare_decisions.json H1.run1 | 28.009, 12.382 | 일치 | v30_decisions.H1.run1.S_bigcert, v30_decisions.H1.run1.S_rtt200, v30_decisions.H1.run2.S_bigcert, v30_decisions.H1.run2.S_rtt200, v31_decisions.H1.run1.S_bigcert, v31_decisions.H1.run1.S_rtt200, v31_decisions.H1.run2.S_bigcert, v31_decisions.H1.run2.S_rtt200 |
| T006 | 18, 79 | key share 1,216 B, 38배 | 1,216/32 | G2/p0_env.json 실측 {4588: 1216} | 38.0 | 일치 | 미확인: 자동 수치 대조 없음 |
| T007 | 22, 85 | 11월 5일까지 검색에서 같은 대체 못 찾음 | 날짜 | C:/dev/pq_afec/docs/선행연구 대조.md 수정 08-30, 이후 기록 없음 | 찾지 못함 | 출처 없음(RT-21) | 미확인: 자동 수치 대조 없음 |
| T008 | 27, 117 | 봉인 측정 259,600연결 | 259,600 | V30 RESULT_stage0 12,800, RESULT_m1confirm 800, RESULT_stage2 103,200+18,000, V31 RESULT_stage3 106,800+18,000 | 합 259,600, 세대 비교 246,000 | 합 일치, 27행 표현 불일치(RT-14) | v30_stage0.connections, v30_m1confirm.connections, v30_run1.connections, v30_run2.connections, v31_run1.connections, v31_run2.connections, sealed.total_connections, generation_comparison.connections |
| T009 | 28, 151 | first flight 1개 1,280 B, 2개 2,560 B | 1/1,280, 2/2,560 | G2/p1_flight.json runs[ips=0] | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T010 | 29, 162 | 경계 3,300~3,400, 5,900~6,000 | 구간 | V4 2_임계정밀 13~16, 41~44행 | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T011 | 30, 165 | 1 B로 왕복 제거 n=400 | 50.88±0.12, 50.876±0.119 | G2/p14_dominance.json base·pad loss 0 | 50.8762±0.1189 | 일치 | p14.base.loss0, p14.base.loss0.metadata, p14.pad.loss0, p14.pad.loss0.metadata, p14.parity.loss0, p14.parity.loss0.metadata, p14.combo.loss0, p14.combo.loss0.metadata, p14.base.loss5, p14.base.loss5.metadata, p14.pad.loss5, p14.pad.loss5.metadata, p14.parity.loss5, p14.parity.loss5.metadata, p14.combo.loss5, p14.combo.loss5.metadata, p14.loss0.base_minus_pad, p14.loss0.parity_minus_combo, p14.loss0.pad_minus_combo, p14.loss0.pad_minus_parity, p14.loss5.base_minus_pad, p14.loss5.parity_minus_combo, p14.loss5.pad_minus_combo, p14.loss5.pad_minus_parity |
| T012 | 31, 169, 215 | 12개 설정 위반, 8개 k=1 | 12, 8 | G2/p1_flight.json capacity_checks | feasible False 12, k=1 8 | 일치 | 미확인: 자동 수치 대조 없음 |
| T013 | 31, 172 | 네 방법 평균 | 114.59, 60.27, 57.65, 52.98 | G2/p14_dominance.json | 114.5896, 60.2651, 57.6527, 52.9809 | 일치 | p14.base.loss0, p14.base.loss0.metadata, p14.pad.loss0, p14.pad.loss0.metadata, p14.parity.loss0, p14.parity.loss0.metadata, p14.combo.loss0, p14.combo.loss0.metadata, p14.base.loss5, p14.base.loss5.metadata, p14.pad.loss5, p14.pad.loss5.metadata, p14.parity.loss5, p14.parity.loss5.metadata, p14.combo.loss5, p14.combo.loss5.metadata |
| T014 | 32 | H2, H3, H4 미확인 | 판정 | V31 decisions H2.run1, H3, H4 | pass False, pass False, adaptation_contributed False | 일치 | 미확인: 자동 수치 대조 없음 |
| T015 | 36, 216 | v3.2-dev, v3.3.1-dev 봉인 측정 예정 | 계획 | HO/v33/state/LOOP_STATE.json T7·X* todo | 지금 참 | 낡을 위험(RT-04) | 미확인: 자동 수치 대조 없음 |
| T016 | 45 | 8월 19일 방향 변경 보고 | 날짜 | TEAM/docs/연구방향_변경보고.docx, VLT 노트 71행 | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T017 | 46 | warm-up 실패가 분모에 섞임 | 330,046 대 330,000 | TEAM/README.md, TEAM/data/raw/run2.csv | n+fail 330,046, 설계 330,000 | 일치 | 미확인: 자동 수치 대조 없음 |
| T018 | 47 | 8월 26일 정정 보고 | 날짜 | VLT 노트 87행 | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T019 | 48 | TLS 1차 120행 제외 | 120 | TEAM/data/README.md | 120행 | 일치 | 미확인: 자동 수치 대조 없음 |
| T020 | 48, 121 | 상관 옵션 5%→0.19% | 0.19 | G2/e6_netem.json configs.corr_5_25.loss_rate | 0.185 | 일치(반올림), 볼트 옛 값 0.20 | 미확인: 자동 수치 대조 없음 |
| T021 | 49 | 두 실행 regret 구간 불겹침 | 0.026±0.025, 1.173±0.049 | R-E git 5ebc151, 6182128 p11 regret[임계아래/무손실] | late 0.026 ci 0.025, late 1.173 ci 0.049 | 일치, README는 다른 쌍(RT-07) | 미확인: 자동 수치 대조 없음 |
| T022 | 50 | 팀원1 보고로 다중 erasure 복구 | 사건 | VLT 06 세션 로그/2026-08-28 신레오 보고 검증과 버스트 한계.md | 같음 | 일치, 번호 배정 미확인(RT-10) | 미확인: 자동 수치 대조 없음 |
| T023 | 51 | v3.0 held-out 45.86 ms 느림 | −45.86 | V30 decisions H2.run1 H_h_c6000_r80_u10.est | −45.860 | 일치 | 미확인: 자동 수치 대조 없음 |
| T024 | 52 | 측정 교착, 러너 없음 | 상태 | HO LOOP_STATE G1 done, G2·T7·X todo | 지금 참 | 낡을 위험(RT-04) | 미확인: 자동 수치 대조 없음 |
| T025 | 57~61 | Fig. 1, 2 PaperBanana 생성 | 문구 | figs2/fig1_timing.tex, fig2_system.tex, tools/fig1.py, fig2.py | TikZ 코드 | 불일치(RT-01) | 미확인: 자동 수치 대조 없음 |
| T026 | 79 | RFC 10024, RFC 9846 | 제목 | rfc-editor info 페이지 | 제목 일치 | 일치 | 미확인: 자동 수치 대조 없음 |
| T027 | 80 | Kempf RTT<0.1 ms | 값 | V4 7_선행연구_대조 18행 | 같음 | 부분 확인 | 미확인: 자동 수치 대조 없음 |
| T028 | 80 | Paquin, Montenegro, Sakk 요지 | 문장 | DOI 유효, 본문 미대조 | 없음 | 미대조(RT-27) | 미확인: 자동 수치 대조 없음 |
| T029 | 89 | ML-KEM 크기와 hybrid share | 1,184, 1,088, 32, 1,216, 1,120 | ML-KEM xlsx 1_크기 5, 7행 | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T030 | 89 | 결합 shared secret 64 B | 64 | ML-KEM xlsx 1_크기 7행은 32, 보고서는 RFC 10024 인용 | 32 대 64 | 저장소 자료와 불일치(RT-07), 규격 원문 미대조 | 미확인: 자동 수치 대조 없음 |
| T031 | 91 | k, B 식 | 식 | G2/p1_flight.json k_model_matches | True | 일치 | 미확인: 자동 수치 대조 없음 |
| T032 | 91 | quic-go 기본 W 1,280 | 1,280 | quic-go v0.61.0 internal/protocol/params.go:12 | 1280 | 일치 | 미확인: 자동 수치 대조 없음 |
| T033 | 93 | 3배 제한 | 3 | quic-go internal/ackhandler/sent_packet_handler.go:25,1038 | 3 | 일치 | 미확인: 자동 수치 대조 없음 |
| T034 | 93 | Nawrocki 35%, 4,071, 38%, 1,362, 1,200~1,472 | 값 | arXiv 2211.02421v1 html | 3·1357=4071, 나머지 같음 | 일치, 약 1%는 부분 확인 | 미확인: 자동 수치 대조 없음 |
| T035 | 96 | Langley, QUIC-FEC, rQUIC 등 요지 | 문장 | DOI 유효, 본문 미대조 | 없음 | 미대조(RT-27) | 미확인: 자동 수치 대조 없음 |
| T036 | 96 | IKEv2 RaptorQ preprint | 문장 | arXiv 2610.32356v1 html | RaptorQ 있음, amplification은 DoS 문맥 | 부분 확인 | 미확인: 자동 수치 대조 없음 |
| T037 | 112 | 연산 N=10,000, 8월 | 값 | TEAM/archive/ML-KEM_1단계_측정수치.xlsx '(2026-08)', 2_연산시간 1행 | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T038 | 113 | TLS 250행, 설계 330,000, 8월 14일 | 값 | TEAM/data/raw/run2.csv, sweep2_results.xlsx 0_개요 | 250행, 330,000 | 일치 | 미확인: 자동 수치 대조 없음 |
| T039 | 114 | 왕복 경계 조건과 표본 | 값 | V4 0_개요, G2/p12_quantum.json n_probe, n_confirm | 15, 40 | 일치 | 미확인: 자동 수치 대조 없음 |
| T040 | 115 | 방법 비교 10월 2일, 셀당 400 | 값 | G2S/loop2.json p14 2026-10-02 03:33, p14 n | 400 | 일치 | 미확인: 자동 수치 대조 없음 |
| T041 | 116 | gen-2 4개 실험 418,400 | 418,400 | p11 4000×5×6, p15 22,400×6, p17 4×5×4500, p18 74,000 | 120,000+134,400+90,000+74,000 | 일치 | 미확인: 자동 수치 대조 없음 |
| T042 | 117 | v3 조건 23개 | 23 | V31 RESULT_stage3 23, V30 RESULT_stage2 22 | 22, 23 | 부분 확인(RT-26) | v30_stage0.connections, v30_stage0.condition_count, v30_m1confirm.connections, v30_m1confirm.condition_count, v30_run1.connections, v30_run1.condition_count, v30_run2.connections, v30_run2.condition_count, v31_run1.connections, v31_run1.condition_count, v31_run2.connections, v31_run2.condition_count |
| T043 | 120 | 교내 서버 사양 | 5218R, 40코어, 125 GiB, 24.04.4, Go 1.26.5, OpenSSL 3.5.6 | TEAM/docs/실험환경_명세서.docx | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T044 | 120 | 노트북 Go, OpenSSL | 1.26.6, 3.5.5 | G2/p0_env.json | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T045 | 120 | CPU 4개 taskset | 4 | C:/dev/pq_afec/experiments/padbed.py:63,76 | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T046 | 120 | ping 평균 | 50.068 | TEAM/docs/종합기술문서.docx | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T047 | 121 | 명목 5%, L=4 재현 | 5.23, 4.05, 500,000 | G2/e6_netem.json ge_p5_L4, n | 5.226, 4.054, 500000 | 일치, 실측 보고서 210행은 4.97(RT-07) | 미확인: 자동 수치 대조 없음 |
| T048 | 123 | PacketConn 기록 | 방법 | experiments/quicbed/qamp.go:1,803 | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T049 | 123 | session ticket, 0-RTT, PMTUD 끔 | 설정 | qamp.go:1921,1927,2473,2478,2482 | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T050 | 123 | 1.5·RTT, 3·RTT 분류 | 값 | p14 pto_rate, V30 g3_m1confirm.json one_rtt_rule | pad 4.25, combo 0.75, 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T051 | 125 | quic-go 송신 판정 | 코드 | sent_packet_handler.go:1034-1038 | bytesSent >= 3×bytesReceived | 일치 | 미확인: 자동 수치 대조 없음 |
| T052 | 127 | c, s0, 6구간 | 41.983, 382.45, 1,472.00 | C:/dev/pq_afec/padfec/policy.py:114,121,126,127 | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T053 | 127, 169 | f | 16 | p1 1450−46−1388 | 16 | 일치 | 미확인: 자동 수치 대조 없음 |
| T054 | 129 | Fig. 1 중앙값 | 102.5, 51.7, 252.4, 51.2 | p14 base·pad p50, pad·combo 5% 부류 | 102.465, 51.677, 252.408, 51.245 | 일치 | p14.base.loss0.metadata, p14.pad.loss0.metadata, p14.parity.loss0.metadata, p14.combo.loss0.metadata, p14.base.loss5.metadata, p14.pad.loss5.metadata, p14.parity.loss5.metadata, p14.combo.loss5.metadata |
| T055 | 130 | parity 크기 | W+39+6k, 1,331 | G33/docs/V33FIX_policy.md:110, G2/p2_threshold.json | 1331 | 일치 | policy.parity_constants, protocol.$.scenarios[0].context.w, protocol.$.scenarios[1].context.w, protocol.$.scenarios[2].context.w, protocol.$.scenarios[3].context.w, protocol.$.scenarios[4].context.w, protocol.$.scenarios[5].context.w, protocol.$.scenarios[6].context.w, protocol.$.scenarios[7].context.w, protocol.$.scenarios[8].context.w, protocol.$.scenarios[9].context.w, protocol.$.scenarios[10].context.w, protocol.$.scenarios[11].context.w, protocol.$.scenarios[12].context.w, protocol.$.scenarios[13].context.w, protocol.$.scenarios[14].context.w |
| T056 | 134 | PTO, ACK 대기, 동점 | 200.86, 1.125, 1.424, 0.01 | policy.py:28-30,336 | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T057 | 134 | 격자 26, hazard 5 | 26, 5 | padfec/table.py P_VALS, V31/padfec3/learn3.py H | 26, 5 | 일치 | 미확인: 자동 수치 대조 없음 |
| T058 | 134 | A_pre, 재평가 16 | 41(k−1), 16 | V31/padfec3/layout.py:89-93, learn3.py:22 | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T059 | 136 | batch means | floor(√n), 최소 8 | experiments/blockstat.py:12,17 | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T060 | 136 | regret 2 ms, 왕복 0.9/0.7 RTT | 값 | p11 checks, p17 bought_hi, bought_lo | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T061 | 136 | 판정불능에 필요 표본 함께 적음 | 문장 | 174행만 있음, p11·p17 키 없음 | 부분 | 부분 확인(RT-25) | 미확인: 자동 수치 대조 없음 |
| T062 | 136 | Bonferroni &#124;z&#124;>2.50 | 2.50 | 산술 0.05/4 양측 | 2.498 | 일치 | 미확인: 자동 수치 대조 없음 |
| T063 | 138 | 실패 10,000 ms | 10,000 | g3_m1confirm.json imputation | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T064 | 141~144 | Table 3 규칙 | 규칙 | decisions rule, V30/g3/PROTOCOL_stage2.md:87,90 | 60셀, sha256 시드 | 일치 | 미확인: 자동 수치 대조 없음 |
| T065 | 147 | 25단계 | 25 | G2S/loop2.json stages | 25 | 일치 | 미확인: 자동 수치 대조 없음 |
| T066 | 147 | 196,020점, 386점, 0.0103, 0.095 | 값 | G2/gate_go_parity.json | 196020, 386, 0.01028, 0.09497 | 일치 | 미확인: 자동 수치 대조 없음 |
| T067 | 147 | 격자 밖 조건 | 2,955·9,000·16,000, RTT 200, 2 Mbps | experiments/quicbed/policy.go policyGrid | cert 11개, rtt {10,50,100}, up {0,10,100} | 일치 | 미확인: 자동 수치 대조 없음 |
| T068 | 147 | 2,531항목 | 2531 | G2/p19_provenance.json | 2531, 0 | 일치 | 미확인: 자동 수치 대조 없음 |
| T069 | 147 | 봉인 파일 71개 | 71 | V30 SEAL 3+8+29, V31 SEAL 31 sha256 키 | 11-06 재해시 71, 불일치 0 | 일치 | seal_stage0.file_count, seal_m1confirm.file_count, seal_stage2.file_count, seal_stage3.file_count, sealed.file_count, sealed.rehash.current |
| T070 | 147 | v3 판정 223항목, 4.4e-12 | 223, 4.4e-12 | 산출물 없음, RESULT_stage3 5행 760·4.8e-12, HO/codex_out/X6.md | 찾지 못함 | 출처 없음(RT-05) | sealed.recompute.current, v31.recompute.items, v31.recompute.max_error |
| T071 | 151 | 연산 값, 합, 1/640 | 24.1, 25.9, 28.2, 78.2 | ML-KEM xlsx, 산술 | 78.2, 639 | 일치 | 미확인: 자동 수치 대조 없음 |
| T072 | 151 | CRYPTO, PADDING, n=10 | 261, 975, 1,447, 1,022 | p1 runs decoded | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T073 | 151 | 서버 수신 k·1,280, n=24 | 1,280, 2,560 | G2/p13_beff.json beff[off] | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T074 | 152~159 | Table 4 | 232, 222, 248, 370, 265; −0.47, 0.73, 5.64, 1.48 | TEAM/data/raw/run2.csv 설계−n | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T075 | 152 | hybrid +0.052%p CI | −0.017~0.120 | 같은 계산 | 0.0516, −0.017, 0.120 | 일치 | 미확인: 자동 수치 대조 없음 |
| T076 | 152 | PTO 12.0, 10.4, z=0.79 | 값 | TEAM/docs/연구방향_변경보고.docx | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T077 | 152 | n별 z | 1.60, 4.54 | 산술 | 1.60, 4.54 | 일치 | 미확인: 자동 수치 대조 없음 |
| T078 | 162 | 약 55→약 105 ms | 값 | V4 2_임계정밀 | 54.2~56, 104.9~106.6 | 일치 | 미확인: 자동 수치 대조 없음 |
| T079 | 162 | 노트북 이분탐색 | 3,312~3,368, 5,917~5,974 | G2/p2_threshold.json | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T080 | 162 | 14점 49.0~49.7 평균 49.44 | 값 | V4 2_임계정밀 쌍 | 14, 49.0, 49.7, 49.443 | 일치 | 미확인: 자동 수치 대조 없음 |
| T081 | 162 | 3,600~4,700 hybrid는 4,032뿐 | 문장 | V4 2_임계정밀 빈 구간, 1_개괄 | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T082 | 162 | 5,609 B와 5,400 B 재현 | 105.7, 55.4, 300연결 0건, 1/100 | V4 4_재현성 10, 14, 15행 | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T083 | 162 | RTT별 격차 | 9.5, 49.2, 99.3, 197.8 | V4 3_RTT비례 D열 | 같음, RTT 50이 3,500 B 행과 같음 | 일치(RT-08) | v4.rtt.row4, v4.rtt.row5, v4.rtt.row6, v4.rtt.row7, v4.threshold.c3500, v4.overview.c4032 |
| T084 | 163 | Fig. 3 'a separate run' | 문구 | 실행 기록 없음 | 확인 못 함 | 출처 없음(RT-08) | 미확인: 자동 수치 대조 없음 |
| T085 | 162 | 구간 밖 차이 | 0.9~1.4, 0.1 | V4 1_개괄스윕 | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T086 | 163 | Fig. 3 좌표 | 42점 | figs2/tools/final_check.py 재실행 | bad 0 | 일치 | 미확인: 자동 수치 대조 없음 |
| T087 | 164 | padding 경계 이동 | 4,557~4,614, 7,163~7,219 | p2 ips_sweep | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T088 | 165 | 1 B 절벽 | 104.829→53.699, 15/15→0/15, 105.718→54.774 | G2S/p12_units.jsonl fp 66975e9fc2a0 | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T089 | 166 | Fig. 4 | 51.1, 50.9, 14점 | 같은 저널, final_check | 51.13, 50.94, bad 0 | 일치 | 미확인: 자동 수치 대조 없음 |
| T090 | 167 | A(B)/B | 3.79 | 산술 | 3.793 | 일치 | 미확인: 자동 수치 대조 없음 |
| T091 | 167 | quiche 소스 동작 | 문장 | VLT 노트 243행 | 소스 직접 미확인 | 부분 확인(RT-24) | 미확인: 자동 수치 대조 없음 |
| T092 | 169 | 최소 초과 69.0, C=1,457 | 값 | p1 capacity_checks | 69.0 | 일치 | 미확인: 자동 수치 대조 없음 |
| T093 | 169 | 9월 29일 실행 | 날짜 | G2S/p1_units.jsonl recorded_at | 2026-09-29 | 일치 | 미확인: 자동 수치 대조 없음 |
| T094 | 169 | 실행 간 60~76 | 값 | R-E git 6dbf9e8, 7420d16, f3dcd4a, d96a56b, 4bab4a5 | 76, 60, 62, 75, 69 | 일치 | 미확인: 자동 수치 대조 없음 |
| T095 | 169 | 직렬화 5.32 | 값 | 산술 | 5.324 | 일치 | 미확인: 자동 수치 대조 없음 |
| T096 | 170 | parity 경계 | 8,239~8,296, 11,977~12,034, 10,901~10,958, 14,583~14,640 | p2 thresholds | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T097 | 170 | 수신 약 2,606, 3,892 | 값 | p13 on1 | 2,605~2,606.5, 3,891~3,893 | 일치 | 미확인: 자동 수치 대조 없음 |
| T098 | 170 | uplink별 1-RTT | 0.996, 0.972, 0.640, 0.404, 0.212, 0.004 | G2/probe_race.json m1 | 같음, 08-26 | 일치 | 미확인: 자동 수치 대조 없음 |
| T099 | 171 | 복구 주입 | 51.627, 110.182, 204.985, 51.887, 51.459, 110.663, 110.338, 40/40 | G2/p7_verify.json V1~V7 | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T100 | 172 | 반폭 | 4.44, 3.98, 1.62, 1.70 | p14 1.96·s/√n | 4.4368, 3.9750, 1.6188, 1.7000 | 3.98만 불일치(RT-13) | p14.base.loss0, p14.pad.loss0, p14.parity.loss0, p14.combo.loss0, p14.base.loss5, p14.pad.loss5, p14.parity.loss5, p14.combo.loss5 |
| T101 | 172 | 4.25%, 12.0% | 값 | p14 | 17/400, 48/400 | 일치 | p14.base.loss0.tail, p14.pad.loss0.tail, p14.parity.loss0.tail, p14.combo.loss0.tail, p14.base.loss5.tail, p14.pad.loss5.tail, p14.parity.loss5.tail, p14.combo.loss5.tail |
| T102 | 172 | 차이 | 4.67±2.35, 7.28±4.32, 2.61±4.29 | p14 | 4.6717±2.3475, 7.2842±4.3233, 2.6125±4.292 | 일치 | p14.loss0.base_minus_pad, p14.loss0.parity_minus_combo, p14.loss0.pad_minus_combo, p14.loss0.pad_minus_parity, p14.loss5.base_minus_pad, p14.loss5.parity_minus_combo, p14.loss5.pad_minus_combo, p14.loss5.pad_minus_parity |
| T103 | 172 | 네 실행 순서 유지 | 4회 | R-E git 7420d16, 5ebc151, 6182128, 4bab4a5 | 모두 combo<parity<pad<base | 일치 | 미확인: 자동 수치 대조 없음 |
| T104 | 173 | Fig. 5, Fisher | 3/400, 0/400, 0.25 | p14, 산술 | 0.249, bad 0 | 일치 | p14.base.loss0.tail, p14.pad.loss0.tail, p14.parity.loss0.tail, p14.combo.loss0.tail, p14.base.loss5.tail, p14.pad.loss5.tail, p14.parity.loss5.tail, p14.combo.loss5.tail |
| T105 | 174 | m2→m4 이득 | 51.82±0.11/50.00, 33.18±8.65/23.57, 11.19±4.56/11.23, 10.41±2.54/8.31, 0.19±1.07/0.15, 95,473 | G2/p18_mmax.json verdict | 같음, 16,000 B | 일치 | 미확인: 자동 수치 대조 없음 |
| T106 | 176 | 통과 17, 실패 7, 미실행 1 | 값 | C:/dev/R-E/README.md, HO/state/briefing_timeline.md | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T107 | 176 | regret 최대, 3조건 판정불능 | +1.10±0.47 | G2/p11_adaptive.json | 1.0978, 0.4748, indeterminate 3 | 일치 | 미확인: 자동 수치 대조 없음 |
| T108 | 176 | oracle | 1.167±1.275, 0.21 이하 | p17 gain | 1.1675±1.2745, 0.2020 | 일치, 0.21 이하는 참(RT-13에서 제외) | p17.2Mbps.gain, p17.무제한.gain, p17.큰cert.gain, p17.RTT200.gain |
| T109 | 176 | auto 3.75 느림 | 3.75 | p17 gain[큰cert].gain_ms | −3.752 | 일치 | p17.2Mbps.gain, p17.무제한.gain, p17.큰cert.gain, p17.RTT200.gain |
| T110 | 176 | π 경계와 추정기 하한 | 4.98e-5, 4.95e-3 | G2/p15_v2policy.json checks | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T111 | 176 | 바이트와 평균 | 1,261.4, 1.0, 51.376 | p15 checks, rows, regret | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T112 | 179 | p8 순서 효과 | 1.09 | G2/p8_stability.json | 1.09 | 일치 | p8.order_effect |
| T113 | 179 | 구간 평균 영향 0.024 | 0.024 | 파일 없음 | 1.09×10/450=0.0242, n=120이면 0.091 | 출처 없음(RT-17) | p8.projected_segment_effect, p8.projection_segment_length, p8.order_effect |
| T114 | 177 | Table 5 날짜 | 10-01 to 10-02 | G2S/p8_units.jsonl 09-29, loop2.json p8 10-01(재사용) | p8은 09-29 | 부분 불일치(RT-17) | p8.recorded_dates, loop.p8.last_failure_date, loop.p10.last_failure_date, loop.p15.last_failure_date, loop.p16.last_failure_date, loop.p17.last_failure_date, loop.p18.last_failure_date, loop.p20.last_failure_date |
| T115 | 180 | p10 | 2.34, 0.89 | G2/p10_completeness.json | 같음 | 일치 | p10.rtt.6, p10.rtt.7, p10.rtt.8, p10.rtt.9, p10.rtt.10, p10.rtt.11, p10.rtt.12, p10.rtt.13, p10.rtt.14 |
| T116 | 180 | 11/12 완주 | 11/12 | tests_passed, tests_total | 시험 통과 수 | 문구 불일치(RT-16) | p10.test_counts, p10.rtt.6, p10.rtt.7, p10.rtt.8, p10.rtt.9, p10.rtt.10, p10.rtt.11, p10.rtt.12, p10.rtt.13, p10.rtt.14 |
| T117 | 181 | p15 반폭 | 1.30 | p15 worst_ci95_half_ms | 1.3046 | 일치 | 미확인: 자동 수치 대조 없음 |
| T118 | 182 | p16 4/6, 6/6 | 값 | HO/state/briefing_timeline.md:33, G2/p16_uplink.json | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T119 | 182 | block 표류 0.39~0.75 | 값 | p16 check 2b | 0.393, 신호 0.762, 0.75 못 찾음 | 부분 확인(RT-18) | p16.block_drift |
| T120 | 183 | p17 적중 | 22.0, 40.3 | p17, G2S/fixloop_detached.txt:575 | 21.96, 40.3(09-27) | 일치 | p17.design, p17.2Mbps.loss2.0.adaptation, p17.2Mbps.loss15.0.adaptation, p17.무제한.loss2.0.adaptation, p17.무제한.loss15.0.adaptation, p17.큰cert.loss2.0.adaptation, p17.큰cert.loss15.0.adaptation, p17.RTT200.loss2.0.adaptation, p17.RTT200.loss15.0.adaptation, legacy.p17.hit, legacy.p17.date |
| T121 | 183 | 적응 중앙값 | 194.5/450 | p17 adapt lags | [76,null,null,313,null] | 일치, 3/5 미적응 누락(RT-15) | p17.design, p17.2Mbps.loss2.0.adaptation, p17.2Mbps.loss15.0.adaptation, p17.2Mbps.gain, p17.무제한.loss2.0.adaptation, p17.무제한.loss15.0.adaptation, p17.무제한.gain, p17.큰cert.loss2.0.adaptation, p17.큰cert.loss15.0.adaptation, p17.큰cert.gain, p17.RTT200.loss2.0.adaptation, p17.RTT200.loss15.0.adaptation, p17.RTT200.gain |
| T122 | 183, 208 | 관측 수 | 4~6, 2~6 | p17 rows auto m_used 0 개수 | 큰 인증서 첫 구간 19, 10 뒤 4~6, 나머지 2~6 | 일치 | p17.design, p17.2Mbps.loss2.0.adaptation, p17.2Mbps.loss15.0.adaptation, p17.무제한.loss2.0.adaptation, p17.무제한.loss15.0.adaptation, p17.큰cert.loss2.0.adaptation, p17.큰cert.loss15.0.adaptation, p17.RTT200.loss2.0.adaptation, p17.RTT200.loss15.0.adaptation |
| T123 | 184 | p18 실패 | 74,000 중 5 | p18 trial_coverage | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T124 | 185 | p20 | 108, 0, 19 | G2/p20_residual.json | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T125 | 188 | 고정 arm | 119.61, 81.62, −38.00, −39.50~−36.49 | V30/experiments/results/g3_m1confirm.json | −37.996, −39.498, −36.493 | 일치 | 미확인: 자동 수치 대조 없음 |
| T126 | 188 | credit과 1-RTT | 376, 101.2, 24 | 같은 파일 supporting | 376/376, 101.212, 0/24 | 일치 | 미확인: 자동 수치 대조 없음 |
| T127 | 188 | uplink 비용 | 3,892→7,888 | V30/g3/RESULT_stage0.md 37행 | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T128 | 188 | credit, 복구 몫 | 30.42, 16.23, 6.89, 41.04 | RESULT_stage0 17, 37, 38행 | 119.60−89.18, 149.48−133.25, 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T129 | 191~197 | Table 6 | B_h, H1, H2, H3, H4 | V30, V31 decisions | 3.577, 3.102, 28.178(22.881), 29.851, 11.355(9.244), 11.228, 28.009(24.331), 28.920, 12.382(10.762), 10.331, 1.154, 4.851, −3.986, −0.433, −3.801, +0.727 | 일치 | v30_decisions.H1.run1.S_bigcert, v30_decisions.H1.run1.S_rtt200, v30_decisions.H1.run2.S_bigcert, v30_decisions.H1.run2.S_rtt200, v31_decisions.H1.run1.S_bigcert, v31_decisions.H1.run1.S_rtt200, v31_decisions.H1.run2.S_bigcert, v31_decisions.H1.run2.S_rtt200 |
| T130 | 199 | 그린 조건과 하한 | 8, 10, −1 위 | final_check | 8, 10, −0.388, −0.349 | 일치 | 미확인: 자동 수치 대조 없음 |
| T131 | 199 | RTT 200 2% 층 | −0.19~−0.59 | run JSON by_loss | −0.191, −0.228, −0.223, −0.590 | 일치 | 미확인: 자동 수치 대조 없음 |
| T132 | 199 | v3.0 held-out | 94.28, 140.14, −58.08~−33.64 | V30 run1, decisions | 94.284, 140.143, −58.076, −33.643 | 일치 | 미확인: 자동 수치 대조 없음 |
| T133 | 199 | 41 B, 여유 6 B | 값 | V31/experiments/results/g31_probe.json, PROTOCOL_stage3.md 0.3절 | 3×2562−7680=6, 41 B 문서 대조 | 일치, 배포본 누락(RT-22) | 미확인: 자동 수치 대조 없음 |
| T134 | 199 | v3.1 held-out | 254.38/135.47, 253.61/136.59, 114.75, +19.74, −5.22~44.70 | V31 run1, decisions H3 | 254.379, 135.474, 253.605, 136.591, 114.746, 19.742, −5.217, 44.700 | 일치 | 미확인: 자동 수치 대조 없음 |
| T135 | 199 | 서버 수신 | 6,717/9,807, 16,684/16,860 | V31 run1 server_bytes_in_per_conn | 6717.3, 9807.1, 16683.6, 16859.7 | 일치 | 미확인: 자동 수치 대조 없음 |
| T136 | 200 | Fig. 6 | 54값 | final_check | bad 0 | 일치 | 미확인: 자동 수치 대조 없음 |
| T137 | 202 | 측정 없음 | 상태 | HO LOOP_STATE, G33/docs/V33FIX_evaluation.md 3행 | 같음 | 일치, 낡을 위험(RT-04) | 미확인: 자동 수치 대조 없음 |
| T138 | 202 | 재생 411,000 | 값 | G33/docs/V33FIX_policy.md:84 | 411,000/411,000 | 일치 | replay.none.total |
| T139 | 202 | 15개 중 넷 낮고 하나 높음 | 1.14~3.64, 0.16 | G33/docs/V33FIX_evaluation.md:68,69,71,117 | −1.788, −2.322, −1.142, −3.642, +0.164, B6 미확정 | 값 일치, 범위 누락(RT-19) | benchmark.n131072_l3_joint.none_floor, benchmark.n131072_l3_joint.v331_none.B1, benchmark.n131072_l3_joint.v331_none.B2, benchmark.n131072_l3_joint.v331_none.B3_u0, benchmark.n131072_l3_joint.v331_none.B3_u2, benchmark.n131072_l3_joint.v331_none.B4, benchmark.n131072_l3_joint.v331_none.B5, benchmark.n131072_l3_joint.v331_none.B6, benchmark.n131072_l3_joint.v331_none.B7, benchmark.n131072_l3_joint.v331_none.B8_j10, benchmark.n131072_l3_joint.v331_none.B8_j20, benchmark.n131072_l3_joint.v331_none.B9, benchmark.n131072_l3_joint.v331_none.B10, benchmark.n131072_l3_joint.v331_none.B11, benchmark.n131072_l3_joint.v331_none.B12_c6000, benchmark.n131072_l3_joint.v331_none.B12_c12000, benchmark.n131072_l3_joint.v331_c1.B1, benchmark.n131072_l3_joint.v331_c1.B2, benchmark.n131072_l3_joint.v331_c1.B3_u0, benchmark.n131072_l3_joint.v331_c1.B3_u2, benchmark.n131072_l3_joint.v331_c1.B4, benchmark.n131072_l3_joint.v331_c1.B5, benchmark.n131072_l3_joint.v331_c1.B6, benchmark.n131072_l3_joint.v331_c1.B7, benchmark.n131072_l3_joint.v331_c1.B8_j10, benchmark.n131072_l3_joint.v331_c1.B8_j20, benchmark.n131072_l3_joint.v331_c1.B9, benchmark.n131072_l3_joint.v331_c1.B10, benchmark.n131072_l3_joint.v331_c1.B11, benchmark.n131072_l3_joint.v331_c1.B12_c6000, benchmark.n131072_l3_joint.v331_c1.B12_c12000, benchmark.n1048576_l1_precision.none_floor, benchmark.n1048576_l1_precision.v331_none.B1, benchmark.n1048576_l1_precision.v331_none.B2, benchmark.n1048576_l1_precision.v331_none.B3_u0, benchmark.n1048576_l1_precision.v331_none.B3_u2, benchmark.n1048576_l1_precision.v331_none.B4, benchmark.n1048576_l1_precision.v331_none.B5, benchmark.n1048576_l1_precision.v331_none.B6, benchmark.n1048576_l1_precision.v331_none.B7, benchmark.n1048576_l1_precision.v331_none.B8_j10, benchmark.n1048576_l1_precision.v331_none.B8_j20, benchmark.n1048576_l1_precision.v331_none.B9, benchmark.n1048576_l1_precision.v331_none.B10, benchmark.n1048576_l1_precision.v331_none.B11, benchmark.n1048576_l1_precision.v331_none.B12_c6000, benchmark.n1048576_l1_precision.v331_none.B12_c12000, benchmark.n1048576_l1_precision.v331_c1.B1, benchmark.n1048576_l1_precision.v331_c1.B2, benchmark.n1048576_l1_precision.v331_c1.B3_u0, benchmark.n1048576_l1_precision.v331_c1.B3_u2, benchmark.n1048576_l1_precision.v331_c1.B4, benchmark.n1048576_l1_precision.v331_c1.B5, benchmark.n1048576_l1_precision.v331_c1.B6, benchmark.n1048576_l1_precision.v331_c1.B7, benchmark.n1048576_l1_precision.v331_c1.B8_j10, benchmark.n1048576_l1_precision.v331_c1.B8_j20, benchmark.n1048576_l1_precision.v331_c1.B9, benchmark.n1048576_l1_precision.v331_c1.B10, benchmark.n1048576_l1_precision.v331_c1.B11, benchmark.n1048576_l1_precision.v331_c1.B12_c6000, benchmark.n1048576_l1_precision.v331_c1.B12_c12000, benchmark.b6.seed_count, benchmark.b6.n131072_l3_joint.v331_c1_vs_v32.B6, benchmark.b6.n131072_l3_joint.v331_c1_vs_l1_c1.B6, benchmark.b6.n131072_l3_joint.v331_none_vs_v32.B6, benchmark.b6.n1048576_l1_precision.v331_c1_vs_v32.B6, benchmark.b6.n1048576_l1_precision.v331_c1_vs_l1_c1.B6, benchmark.b6.n1048576_l1_precision.v331_none_vs_v32.B6 |
| T140 | 206 | 3B와 padding 범위 | 3,840, 7,680, 4,557 | 산술, p2 | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T141 | 207 | parity가 padding을 지배 안 함 | 2.61±4.29 | p14 | 0 포함 | 일치 | p14.loss0.base_minus_pad, p14.loss0.parity_minus_combo, p14.loss0.pad_minus_combo, p14.loss0.pad_minus_parity, p14.loss5.base_minus_pad, p14.loss5.parity_minus_combo, p14.loss5.pad_minus_combo, p14.loss5.pad_minus_parity |
| T142 | 207 | 같은 바이트 비교 없음 | 상태 | X1 todo | 지금 참 | 낡을 위험(RT-04) | 미확인: 자동 수치 대조 없음 |
| T143 | 208 | 셋은 m=3, 큰 인증서만 갈림 | 판정 | p17 checks 6 | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T144 | 208 | 99% 안팎 적중 | 98.8~99.3 | p17 checks 7 | 같음 | 일치 | p17.2Mbps.loss2.0.adaptation, p17.2Mbps.loss15.0.adaptation, p17.무제한.loss2.0.adaptation, p17.무제한.loss15.0.adaptation, p17.큰cert.loss2.0.adaptation, p17.큰cert.loss15.0.adaptation, p17.RTT200.loss2.0.adaptation, p17.RTT200.loss15.0.adaptation |
| T145 | 210 | IW 32 | 32 | quic-go internal/congestion/cubic_sender.go:20 | 32 | 일치 | claims.initial_cwnd |
| T146 | 210 | burst 실제 손실 | 0.99~9.09 | TEAM/README.md, L/(L+50) | 0.99, 9.09 | 일치 | 미확인: 자동 수치 대조 없음 |
| T147 | 210 | 1,452 B, W≥1,402 | 값 | G33/docs/V33FIX_policy.md:153 | W≤1401 | 일치, 세대 표시 없음(RT-20) | policy.parity_constants, policy.parity_bound.k1, policy.parity_bound.k2, policy.parity_bound.k3, policy.parity_bound.k4, protocol.$.scenarios[0].context.w, protocol.$.scenarios[1].context.w, protocol.$.scenarios[2].context.w, protocol.$.scenarios[3].context.w, protocol.$.scenarios[4].context.w, protocol.$.scenarios[5].context.w, protocol.$.scenarios[6].context.w, protocol.$.scenarios[7].context.w, protocol.$.scenarios[8].context.w, protocol.$.scenarios[9].context.w, protocol.$.scenarios[10].context.w, protocol.$.scenarios[11].context.w, protocol.$.scenarios[12].context.w, protocol.$.scenarios[13].context.w, protocol.$.scenarios[14].context.w |
| T148 | 212, 216 | 후속 과제 | 계획 | HO LOOP_STATE | 지금 참 | 낡을 위험(RT-04) | 미확인: 자동 수치 대조 없음 |
| T149 | 215 | 결론 RQ1~RQ4 | 요약 | 위 각 행 | 같음 | 일치 | 미확인: 자동 수치 대조 없음 |
| T150 | 219~246 | 참고문헌 DOI 21개 | 유효 | doi.org | 모두 302 | 일치 | 미확인: 자동 수치 대조 없음 |
| T151 | 210 | 셋째 '첫 접속만' | 문구 | V31/g3/RESULT_stage3.md 16행 H5, G33/docs/REPORT_CLAIMS_v33.md 38행 | 첫 방문은 둘 다 b0, 이득은 재방문 조건부 | 불일치(RT-28) | v31.cold.C_bigcert_l2.g2auto, v31.cold.C_bigcert_l2.g3auto, v31.cold.C_2955_l0.g2auto, v31.cold.C_2955_l0.g3auto |
| T152 | 131, 210 | 정책의 uplink 입력 | 문구 | HO/v33/prompt/CONTEXT.md 72, 112행 | 131행 캡션에만 있고 한계 절에 없음 | 누락(RT-29) | 미확인: 자동 수치 대조 없음 |
| T153 | 32 | 큰 인증서 수치와 initial cwnd 단서 | 문구 | G33/docs/REPORT_CLAIMS_v33.md 49행 | 210행에만 단서 | 부분(RT-30) | v30_decisions.H1.run1.S_bigcert, v30_decisions.H1.run1.S_rtt200, v30_decisions.H1.run2.S_bigcert, v30_decisions.H1.run2.S_rtt200, v31_decisions.H1.run1.S_bigcert, v31_decisions.H1.run1.S_rtt200, v31_decisions.H1.run2.S_bigcert, v31_decisions.H1.run2.S_rtt200, claims.initial_cwnd |
