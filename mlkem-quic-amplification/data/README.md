# 데이터 안내

## 분석용 엑셀

| 파일 | 내용 |
|---|---|
| `ML-KEM_1단계_측정수치_v2.xlsx` | 크기 / 연산시간 / 패킷분할 (하이브리드 포함) |
| `sweep1_results.xlsx` | TLS 1차 스윕 120조건 — **무효, 대조용** |
| `sweep2_results.xlsx` | TLS 2차 스윕 250조건 + z검정 |
| `quic_amplification_v4.xlsx` | 증폭 실험 9시트 (최종) |

### quic_amplification_v4.xlsx 시트 구성
0 개요 / 1 개괄 / 2 임계정밀 / 3 RTT / 4 재현성 / 5 이론대조 / 6 한계 / 7 선행연구9편 / 8 패딩인과

**시트 8**이 인과 검증(패딩만 바꿔도 임계 이동)이라 설명할 때 가장 유용합니다.

## raw/

| 파일 | 행 | 열 |
|---|---|---|
| `run1.csv` | 120 | 12 — model, rtt_ms, loss_pct, group, n, fail, fail_rate_pct, mean/sd/p50/p95/p99 |
| `run2.csv` | 250 | 13 — 위 + tmo(타임아웃 건수) |

`run1.csv`는 loopback MTU 미적용 상태의 데이터라 손실 실험이 무효입니다.
