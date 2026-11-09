# 동결 세대 문서 정정표

동결 세대 폴더(gen-2 `pq_afec`, v3.0 `pq_afec_gen3`, v3.1 `pq_afec_gen31`, v3.2-dev `pq_afec_gen32`)와 팀 자료 폴더 `mlkem-quic-amplification`의 문서에 남은 틀린 문장을 이 표에 모은다. 틀린 문장은 원문에서 고치지 않고 이 표로 바로잡는다. 경로는 R-E 저장소 안의 경로로 적었다. 같은 파일의 로컬 원본은 정도현 노트북의 C:\dev 아래 같은 이름 폴더에 있다(로컬 보존).

## 1. 원문을 고치지 않는 이유

D61에 따라 동결 세대 문서의 틀린 문장은 원문을 고치지 않고 이 정정표로만 바로잡는다.

봉인 때문이다. R-E 루트의 tools/verify_seals.py는 봉인 네 개(gen31 SEAL_stage3.json, gen3 SEAL_stage2.json, SEAL_stage0.json, SEAL_m1confirm.json)에 적힌 파일 107개의 SHA-256을 대조한다(F60). gen31 SEAL_stage3.json에는 g3/PROTOCOL_stage3.md, g3/RESULT_stage0.md, g3/RESULT_m1confirm.md, g3/PROTOCOL_stage2.md, g3/GEN31_CHANGES.md 같은 문서도 들어 있어 문장 하나만 고쳐도 대조가 깨진다.

코드 파일(pq_afec/padfec/policy.py, pq_afec/afec/rs.py)은 주석만 바꿔도 BL-02가 적은 대로 소스 지문과 봉인 해시가 달라진다. 2026-11-08 정리(R-E 루트 README)에서 이 폴더들의 코드 주석을 지우고 봉인 밖 문서의 표기와 문체를 다듬었다. 내용과 수치는 바꾸지 않았고 봉인된 g3 문서는 손대지 않았다. 그래서 지금 R-E의 `pq_afec`는 로컬 원본과 바이트가 다르고, 봉인 대조는 정리 전 커밋 `4f26a51`의 바이트로 한다. 아래 표의 원문 인용과 행 번호도 `4f26a51`의 문서 기준이다.

BL-02가 원래 요구한 md 문장 교체와 R-E 루트 docs/ERRATA.md는 D61 때문에 하지 않았고 이 정정표가 대신한다.

## 2. 정정 표

### 2-1. 정오표

`docs/REPORT_CLAIMS_v33.md`의 "팀 문서 정정 제안" 표 30행을 옮겼다. 그중 원문이 이미 맞던 1행은 2-2절로 나눴다. 성격 칸은 같은 문서 "정정 행의 성격" 절의 분류(2026-11-02 감사 G-E4)를 따른다. 실제 정정은 원문이 틀렸거나 지금 사실로 낡은 행이고, 상태 주석은 과거 기록이나 수정 대기 항목에 붙이는 설명이다. 둘 다 정오표로 센다. 이 표에서 실제 정정은 16행, 상태 주석은 13행이다.

인용 칸은 그 표의 발췌를 그대로 옮겼다. 그 발췌는 원문의 굵게 표시와 코드 표시(backtick)를 뺐고 긴 문장은 "(이하 발췌 생략)"으로 줄였다. 원문 전체와 파일 SHA-256은 A1 원문 목록 `A1_claim_sources_v3.json`에 있다(로컬 보존). 행 번호는 그 스냅숏 기준이다. 동결 폴더와 팀 자료 폴더의 29행은 R-E final 작업 트리의 같은 행에서 발췌 첫머리를 다시 찾았다. 동결 폴더가 아닌 R-E 루트 README 행은 지금 다른 행에 있어 새 행 번호를 함께 적었다. 맞는 문장 칸은 전문 용어를 영어 원어로 다시 썼다.

gen33 `padfec/policy.py`에 있던 같은 옛 수치와 CID 설명은 F15(BL-13, 커밋 `13e2f4c94`)에서 결과 파일 안내로 줄였다. 동결 gen-2 사본에 남은 설명의 정오표는 아래 policy.py 세 행이다. 코드 파일 행(policy.py, rs.py)과 봉인 문서 행(PROTOCOL_stage3.md, SEAL_stage0.json, SEAL_stage2.json)도 정오표로만 적고 원본은 두었다.

| 항목 | 파일·행 | 틀린 문장(원문 인용) | 맞는 문장 | 근거 | 성격 |
| --- | --- | --- | --- | --- | --- |
| Q-02 | `pq_afec/docs/수정 대기 목록.md:49` (로컬 보존) | ## A-2 🟡 p18 검사 4의 자가 거꾸로 되어 있다<br><br>- 무엇 — 「자리 효과가 측정 반폭 이내」로 판정하는데, 반폭은 표본이 늘수록 줄어든다.<br>  즉 정밀하게 잴수록 이 검사가 실패한다.<br>- 증거 (results/p18_mmax.json, 검사 4)<br><br>  \| 조건 \| 자리효과 \| 반폭 \| 이득 \| 자리/이득 \| 판정 \|<br>  \|---\|---\|---\|---\|---\|---\|<br>  \| m_max2포기·무손실 \| 0.71 \|  (이하 발췌 생략) | 2026-08-26에 쓴 수정 대기 목록의 옛 p18 검사 기록이다. 현재 보존된 p18 결과의 검사 4는 라틴 방격 균형을 확인하고 자리 F는 진단으로만 보고한다. 새 분석은 연결 단위와 블록 단위 구간을 함께 싣는다. 과거 문턱을 사후에 바꾼 확증으로 쓰지 않는다. | `A1_numeric_audit_v1.json`의 p18.checks, `pq_afec/experiments/results/p18_mmax.json` | 상태 주석 |
| Q-05, Q-09 | `pq_afec/docs/수정 대기 목록.md:110` (로컬 보존) | - results/p10_completeness.json gap 1 (ok: true = 결함 아님으로 표시됨)<br>  - 설계: padfec/policy.py가 (C, k, W, cert, p, L, RTT)로 m을 고른다<br>  - 구현: m은 -m 플래그로 사람이 준다<br>  - 이유: 정책이 필요로 하는 서버 비행 크기(cert)와 손실률 p를 클라이언트가<br>    첫 접속 순간에는 알 수 없다. 그래서 목적지별 통계 캐시(v0.2)가 그 (이하 발췌 생략) | 수동 `-m` 팔과 자동 정책 팔을 구분한다. gen-2 자동 팔은 있지만 cold 접속의 인증서, 손실 정보와 online 학습 검증에는 한계가 있다. gen33(v3.3.1-dev) Go 경로를 실제 network에서 잰 값은 2026-11-07 development 측정 문서를 따른다. | `A0_evidence.md`, `docs/T4_observation_result.md`, `docs/X6_result.md` | 상태 주석 |
| Q-05 | `pq_afec/docs/수정 대기 목록.md:118` (로컬 보존) | ## A-6 ⚪ k(비행 데이터그램 수) 제어 불가<br><br>- 용량 정리는 k를 늘리면 제자리 배치가 가능해진다고 말하지만, quic-go가 정하는 값을 받아들인다.<br>- k를 늘리려면 패킷 번호 공간을 건드려야 하고, 그러면 클라이언트가 보내지 않은 PN의 ACK를 받아<br>  PROTOCOL_VIOLATION 위험이 있다. (p10_completeness.json gap 4) | 과거 구현은 quic-go가 정한 k를 받았다. v3.3 T3의 인증된 ClientHello 확장은 k 제어용 개발 기능이고, O4의 후보별 k 정책 연결은 미채택이다. | `docs/T3_inflate_result.md`, `T3_coverage.md`, `O4_coverage.md` | 상태 주석 |
| Q-05, Q-09 | `pq_afec/docs/수정 대기 목록.md:129` (로컬 보존) | ## A-8 ⚪ 서버 → 클라이언트 방향 미보호 — 원리적 제외<br><br>- 서버 비행에는 패딩이 없고(인증서로 꽉 찬다) 서버에게 쓸 수 있는 무료 바이트도 없다.<br>- 미구현이 아니라 설계상 제외다. 보고서 「한계」에 이미 적혀 있다. | 현재 parity 복구 범위는 클라이언트에서 서버로 가는 first flight다. 서버에서 클라이언트로 가는 손실을 복구하거나 모든 인터넷 경로에서 이득을 보장한다고 쓰지 않는다. | A5-12, A7-01 | 상태 주석 |
| Q-08 | `pq_afec/docs/수정 대기 목록.md:197` (로컬 보존) | ## C-1 🔵 docs/다음 세션 인계.md가 12일 낡았고 새 세션을 틀린 방향으로 보낸다<br><br>- 마지막 갱신 2026-08-14 (v0.2.1 시점). 본문: "다음 할 일은 §4 — 1순위는 추정 상수 3개의<br>  실측 교체다."<br>- 그 작업은 2026-08-17에 끝났고, 2026-08-19에 연구 방향 자체가 바뀌었다.<br>- 「먼저 읽을 것」으로 알고리즘 명세 v0.1.md · v0.2.md를 가리키는데 둘 다 옛 (이하 발췌 생략) | 2026-08-26 문서 점검 기록이다. 인계 문서는 그 뒤 2026-09-08에 다시 갱신됐고 정본 v2와 역사 문서 v0.1, v0.2를 구분한다. v3.3 이후 진행 상태는 gen33 저장소 기록으로 확인한다. | `pq_afec/docs/다음 세션 인계.md:4`, 같은 파일 37행 | 상태 주석 |
| Q-08 | `pq_afec/docs/수정 대기 목록.md:215` (로컬 보존) | ## C-3 🔵 보고서가 둘, 파이프라인이 둘<br><br>\| \| 파이프라인 \| 산출물 \| 갱신 \| 성격 \|<br>\|---\|---\|---\|---\|---\|<br>\| 옛것 \| experiments/pipeline.py (18단계, e1~e21) \| docs/실측 보고서.md (648줄) + docs/실측 결과표.md \| 2026-08-18 \| 서술은 손으로 씀 \|<br>\| 지금 \| experiments/loop2.py (24단계, p0~p19) + fixloop (이하 발췌 생략) | 두 pipeline은 세대와 목적이 다르다. 선행연구 대조 A부에는 2026-08-28 개정 표지가 있고, v0.1과 v0.2에는 역사 문서 표지가 있다. 이 옛 점검표를 현재 미수정 목록으로 옮기지 않는다. | `pq_afec/docs/선행연구 대조.md:3`, `pq_afec/docs/알고리즘 명세 v0.1.md:3`, `pq_afec/docs/알고리즘 명세 v0.2.md:3` | 상태 주석 |
| Q-08 | `pq_afec/docs/수정 대기 목록.md:250` (로컬 보존) | ## C-8 🔵 원본 변경보고의 HTML 소스가 없다<br><br>- 「구버전 파일 정리」 규칙대로 중간 파일이 지워져 있어 원본 PDF를 고칠 수 없었다.<br>  그래서 별도 1쪽으로 낸 것이다.<br>- 규칙 자체는 도현님 방침이므로 유지하되, 제출 폴더 밖(스크래치패드/저장소)에 소스를<br>  남기는 예외를 둘지 결정이 필요하다. | 2026-08-26 기록에는 변경보고 HTML 소스가 없었다. 제출 원고의 최신 소스 위치는 A1에서 확인하지 못했다. 소스 재생성, 삭제, 원본 PDF 편집은 하지 않았다. | 수정 대기 목록 C-8, D6과 D10 기본값 | 상태 주석 |
| Q-09 | `pq_afec/docs/수정 대기 목록.md:257` (로컬 보존) | ## C-9 · 보고서에 추가로 들어가야 할 한계 (아직 안 들어감)<br><br>- A-3 (p16의 자가 자기 표류보다 곱다) — 오늘 처음 드러나 아직 미반영<br>- A-5 (폐루프가 배선은 됐지만 m을 사람이 준다) — 「폐루프」라는 말의 뜻을 갈라 써야 함<br>- A-1 (뒤따르는 패리티 항이 검증도 반증도 안 됨)<br>- ✅ 이미 반영된 것: 허용집합 자(A-4) · 용량 정리(A-9) · 서버 방향(A-8) · 미구현 4건 | 한계 절에는 순차 측정 표류, p16 자와 harness 표류의 차이, trailing parity의 credit 항 미확정, 자동 정책의 cold 정보와 적응 검증 한계, s2c 미보호를 적는다. gen-2와 v3.3 개발 상태를 나눠 쓴다. | A5-11, Q-03, Q-04, `A1_numeric_audit_v1.json` | 상태 주석 |
| Q-08 | `pq_afec/docs/다음 세션 인계.md:30` (로컬 보존) | 한 줄이면 된다. 커밋은 안 했다(도현님 지시 대기). 작업 사본과 저장소 사본은<br>소스·문서만 동기화해 뒀다.<br><br>---<br><br>## 1. 먼저 읽을 것 (순서대로)<br><br>1. docs\PADFEC v2 명세.md — 알고리즘 본체. 이게 정본이다.<br>   (알고리즘 명세 v0.1/v0.2.md 는 옛 판이다. 역사로만 봐라.) | 2026-09-08 시점 인계 기록이다. 당시 커밋 여부를 현재 상태로 읽지 않고, v0.1과 v0.2는 역사 자료로만 쓴다. v3.3 이후 진행은 gen33 저장소 기록으로 확인한다. 이 파일은 3절의 작업 메모다. | `pq_afec/docs/다음 세션 인계.md:4` | 상태 주석 |
| Q-08, Q-16 | `pq_afec/docs/알고리즘 명세 v0.1.md:12` (로컬 보존) | > - 손실 통계의 목적지별 캐시는 v2 결정 경로에 없다. | 역사 문서 표지는 유지한다. 목적지별 손실 cache는 gen-2 Go의 destCache에서 쓰인다. Python 단발 계산과 Go 연결 간 상태를 구분한다. | `pq_afec/experiments/quicbed/policy.go:577`, A7-03 | 실제 정정 |
| Q-08, Q-16 | `pq_afec/docs/알고리즘 명세 v0.2.md:12` (로컬 보존) | > - 손실 통계의 목적지별 캐시는 v2 결정 경로에 없다. | 역사 문서 표지는 유지한다. 목적지별 손실 cache는 gen-2 Go의 destCache에서 쓰인다. Python 단발 계산과 Go 연결 간 상태를 구분한다. | `pq_afec/experiments/quicbed/policy.go:577`, A7-03 | 실제 정정 |
| Q-16 | `pq_afec/docs/선행연구 대조.md:105` (로컬 보존) | 표준 변경 없이 클라이언트만 고쳐서 배포할 수 있다." | padding credit은 서버의 byte 계수 규칙에 의존한다. parity 복구에는 서버 decodeConn 수정이 필요하다. 같은 datagram을 중복으로 보내는 방식은 별도 기준선이다. | A7-18, A8-03, `pq_afec/experiments/quicbed/qamp.go` | 실제 정정 |
| Q-16 | `pq_afec/docs/선행연구 대조.md:278` (로컬 보존) | \| 3 \| 캐시 반입 게이트 (RFC 9959 §3.2) \| ⛔ 놓을 자리가 없어졌다. 연결 간 손실 캐시는 v1(afec/) 것이고 v2 결정 경로에 없다. 캐시를 되살리기 전에는 게이트를 만들 자리 자체가 없다 \| | gen-2 Go에는 목적지별 destCache가 있다. cache가 있다는 사실과 손실 추정이나 privacy 성능이 검증됐다는 주장은 구분한다. | `pq_afec/experiments/quicbed/policy.go:577`, A7-03, A7-M03 | 실제 정정 |
| Q-16 | `pq_afec/afec/rs.py:1` (로컬 보존) | 복구할 수 있다(=MDS). 반데르몬드 행렬을 systematic 형태로 행축약하면 이 성질이<br>깨질 수 있는 반면, Cauchy 행렬은 구성상 항상 MDS다. | 가역 행변환으로 systematic 형식을 만들면 MDS 성질은 보존된다. I와 Vandermonde 행을 단순히 쌓는 것과 구분한다. 설명에 관한 정정이며 현재 부호 계산 오류를 뜻하지 않는다. 코드 파일이라 원본은 고치지 않는다. | `docs/R3_codec_format.md`, Q-16 | 실제 정정 |
| Q-13 | `pq_afec/README.md:164` (로컬 보존) | Go 1.26.5 는 버전까지 맞췄다. | 명세상 Go 1.26.5와 실제 빌드 Go 1.26.6을 구분해 적는다. gen33 검증 환경은 Go 1.26.6, quic-go v0.61.0이다. | `pq_afec/docs/실험환경 대조.md:31`, `experiments/quicbed/go.mod` | 실제 정정 |
| Q-13 | `pq_afec/docs/실험환경 대조.md:65` (로컬 보존) | \| OS \| Ubuntu 24.04.4 LTS \| Kali Rolling (WSL2) \| 커널 기능은 동일 경로. 낮음 \|<br>\| 커널 \| 7.0.0-28-generic \| 6.18.35.2-microsoft-standard-WSL2 \| netem/veth 동작 동일 확인. 낮음 \| | 과거 스냅숏 표다. 측정은 `wsl -d Ubuntu`로 돌았으므로 Kali 실측으로 소개하지 않는다. gen33 검증 환경은 S5 doctor 기록을 따른다. | A6-11, `docs/S5_test_hygiene.md` | 상태 주석 |
| Q-14 | `mlkem-quic-amplification/src/run_v3.sh:4` (로컬 보존) | NETEM_SIDES="${NETEM_SIDES:-one}" | NETEM_SIDES 기본값 one은 클라이언트 송신 한쪽 설정이다. both 실행은 양쪽 설정을 요청했는지 로그로 확인한다. 이 스크립트를 기본 양방향 실험이라고 쓰지 않는다. | 같은 파일 83, 89, 101~103행 | 상태 주석 |
| Q-19 | `pq_afec_gen31/g3/PROTOCOL_stage3.md:3` (로컬 보존) | 상태: 초안이다. 봉인 전이고 3단계 측정은 없다. 15절의 H 추첨 결과와 H 예측표는 빈칸 표식(러너의 TODO_MARK, 단계 번호가 붙은 TODO 괄호)으로 비워 두었다. --seal은 이 문서에 그 표식이 하나라도 남아 있으면 거부하므로, 표식은 15절의 두 빈칸에만 쓴다. 2단계 봉인 기록(g3/PROTOCOL_stage2.md, g3/SEAL_stage2.json)과 2단계 판정은 고치지 않는다. | 이 파일은 '초안' 상태 문장이 남은 채 stage3에 봉인됐다. 봉인 원문은 두고, 같은 폴더 RESULT_stage3.md의 문서 결함 절과 이 정정표로 실제 봉인 상태를 알린다. | `pq_afec_gen31/g3/RESULT_stage3.md:101`, `A1_context_checks_v1.json`의 stage3 | 실제 정정 |
| Q-19 | `pq_afec_gen31/g3/SEAL_stage0.json:1` (로컬 보존) | {<br> "schema": "padfec3.stage0_seal.v1",<br> "sealed_utc": "2026-10-02T00:45:16Z",<br> "stage": "PAD-FEC v3 stage 0 (verdict_v3.md section 4.2)",<br> "sha256": { | gen31 트리에 있는 상속 stage0 manifest는 gen3 파일과 같다. gen31 현재 트리에서는 고정 3개 중 2개, 기록 6개 중 5개가 맞고 원래 gen3 트리에서는 전부 맞는다. stage3 무결성과 혼동하지 않는다. | `A1_context_checks_v1.json`의 seals | 상태 주석 |
| Q-19 | `pq_afec_gen31/g3/SEAL_stage2.json:1` (로컬 보존) | {<br> "schema": "padfec3.stage2_seal.v1",<br> "sealed_utc": "2026-10-02T03:27:08Z",<br> "stage": "PAD-FEC v3 stage 2 (verdict_v3.md 4.3-4.5)",<br> "sha256": { | gen31 트리에 있는 상속 stage2는 현재 트리에서 고정 29개 중 22개, 기록 9개 중 7개가 맞는다. 원래 gen3 트리는 29/29와 9/9, gen31 stage3는 31/31과 14/14다. 상속 범위 차이로 적고 옛 봉인은 고치지 않는다. | `A1_context_checks_v1.json`의 seals | 상태 주석 |
| A4-11 | `pq_afec/docs/PADFEC v2 명세.md:522` (로컬 보존) | \| 모형 R (신설) \| 1.2148 \| 1.2590 \| 1.1566 \| 1.0993 \|<br>\| 비 \| 1.02 \| 1.07 \| 1.05 \| 1.03 \|<br>\| 옛 모형 \| 1.000 \| 1.000 \| 1.000 \| 1.000 \|<br><br>오차가 m 에 따라 달랐다는 것이 핵심이다 — m 끼리의 비교를 왜곡한다.<br>p18 검사 6 이 버스트 3 에서 실측 이득 +31.01 vs 예측 +13.51 로 붉어진 것이 | 현재 보존 자료의 버스트 3 모형 기대 라운드는 m1~4에서 1.214766, 1.188659, 1.114800, 1.072777이다. p18 m2→m4는 예측 23.568929 ms, 관측 33.182179 ms, 블록 반폭 8.654651 ms다. | `A1_numeric_audit_v1.json`의 expected_rounds, p18 | 실제 정정 |
| A4-11 | `pq_afec/docs/PADFEC v2 명세.md:765` (로컬 보존) | 수렴 여유는 1.42 배뿐이다.<br><br>    pad 가 이기는 상한   p <  0.00703   (§3 의 J 비교, 이분탐색) | 해당 고정 입력에서 현 비용식의 padding 선택 경계 p는 약 4.9783e-5다. p<0.00703을 일반 경계로 인용하지 않는다. 입력이나 식 판본이 바뀌면 다시 계산한다. | `a1_numeric_audit_v1.py`의 choice, `A1_numeric_audit_v1.json`의 pad_threshold_p | 실제 정정 |
| A6-11, A6r1-11 | R-E 루트 `README.md:25`(A1 스냅숏 24행) (로컬 보존) | \| gen-2 (pq_afec) \| 2026-10-01~10-02 실행 \| 17단계 통과, 7단계 실패(p8 p10 p16 p17 p15 p18 p20), p6 미실행. 10월 2일·7일 코드 수정 뒤 새 실측 없음 \| | gen-2 첫 판정은 통과 17, 실패 7, 미실행 1(p6)이다. p16은 10월 1일 실패 뒤 10월 2일 재실행에서 통과해 마지막 state는 통과 18, 실패 6(p8 p10 p15 p17 p18 p20)이고 p6는 stale이다. R-E 루트 README는 동결 폴더가 아니어서 이 줄은 R-E README 작업(F62)에서 고친다. | RP-03, `docs/S2_hygiene.md`, `pq_afec/experiments/state/fixloop_triage.json` | 실제 정정 |
| A4-11 | `pq_afec/padfec/policy.py:338` (로컬 보존) | 이 항이 이득 예측을 얼마나 움직였는지의 전후 비교(「212% -> 97%」로 적혀<br>    있었다)는 재현 가능한 기록이 없어 지웠다(2026-09-07). 지금 p18 원자료<br>    (results/p18_mmax.json, 임계사이·버스트3, 팔당 8,999 판)로는<br>    m=2 -> m=4 이득이 예측 +13.51 vs 실측 +31.01 ± 7.40 ms 로 예측이 실측의 | 이 주석의 옛 수치쌍은 현 결과로 대체됐다. 버스트 3의 관측 이득 33.182179 ms, 모형 23.568929 ms, 블록 반폭 8.654651 ms를 입력, 판본과 함께 인용한다. gen33의 같은 설명은 F15에서 결과 파일 안내로 줄였고 동결 사본은 그대로다. | `A1_numeric_audit_v1.json`의 p18, `docs/FINAL_verification.md`의 F15 절 | 실제 정정 |
| A4-11 | `pq_afec/padfec/policy.py:752` (로컬 보존) | #      실측 이득 +31.01 vs 예측 +13.51 (212%) 로 붉어진 것이 이것이다. | 옛 31.01/13.51의 비율은 약 230%이고 212%는 산술 오류다. 현재 결과는 다른 실행이므로 관측 33.182179 ms, 예측 23.568929 ms로 따로 적는다. | `A1_numeric_audit_v1.json`의 p18, 옛 비율 31.01/13.51 | 실제 정정 |
| A4-11 | `pq_afec/README.md:371` (로컬 보존) | > 임계사이·버스트3 에서 230% 로 실패한다(실측 +31.01 / 예측 +13.51). | 이 옛 결과를 최신 p18 판정으로 쓰지 않는다. 현재 버스트 3 값은 관측 33.182179 ms, 모형 23.568929 ms이고 실패 5회를 뺀 성공 연결 통계다. | `A1_numeric_audit_v1.json`의 p18 | 실제 정정 |
| A4-11 | `pq_afec/docs/PADFEC v2 명세.md:508` (로컬 보존) | 1,323.5~1,332 B 로 W+32+6k 보다 ~7 B 컸다. CID 길이 무작위성 때문에 ±수 B 는 남고,<br>남는 오차는 신용 과소평가 쪽(보수)이다.) | CID 길이 차이는 credit의 과소평가와 과대평가를 둘 다 만들 수 있다. 고정 39 B 근사보다 실제 parity가 작으면 credit을 과대평가한다. 실제 직렬화 길이를 쓴다. | `docs/R3_codec_format.md`, A4-02 | 실제 정정 |
| A4-11 | `pq_afec/padfec/policy.py:278` (로컬 보존) | # x25519 1323.5~1326.5, ML-KEM 1331~1332 로, W+32+6k(1318/1324)보다 ~7 B 크다.<br># 원인은 CID 길이(quic-go 가 고르는 무작위 길이)라 연결마다 ±수 B 흔들리며,<br># 실측 중앙값 기준 base ≈ 38.5~39.5 다. 39 로 둔다. 남는 ±수 B 는 신용을<br># 과소평가하는 쪽(보수)으로만 작용한다.<br>PARITY_OVERHEAD_BASE = 39      # 롱헤더+CID 약 26 + FEC 머리  (이하 발췌 생략) | 남은 CID 오차가 credit을 과소평가하는 쪽으로만 작용한다는 설명은 틀렸다. 실제 직렬화 길이와 근사값을 비교한다. gen33의 같은 단정은 F15에서 뺐고 동결 사본은 그대로다. | `docs/R3_codec_format.md`, A4-02, `docs/FINAL_verification.md`의 F15 절 | 실제 정정 |
| A6-11 | `pq_afec/README.md:154` (로컬 보존) | python -m padfec.policy     # 19 checks<br>python -m padfec.quantum    # 39 checks | 자체시험 개수는 고정된 옛 주석 대신 해당 판본의 실제 출력으로 확인한다. gen33의 pytest 수는 명령별 자체시험 개수와 더하지 않으며, 현재 값은 `docs/REPRODUCE.md`의 명령으로 잰다. | `A1_pytest_v1.json`, `docs/S5_test_hygiene.md` | 실제 정정 |

### 2-2. 재확인

원문 바로 아래에 맞는 정정이 이미 붙어 있어 다시 확인만 한 행이다.

| 항목 | 파일·행 | 틀린 문장(원문 인용) | 맞는 문장 | 근거 | 성격 |
| --- | --- | --- | --- | --- | --- |
| Q-13 | `pq_afec/docs/실험환경 대조.md:31` (로컬 보존) | \| Go \| 1.26.5 \| 1.26.6 (아래 정정 참고) \|<br><br>> ⚠️ 정정 (2026-09-07). 이 표는 원래 「1.26.5 (GOTOOLCHAIN 으로 고정)」이라<br>> 적혀 있었다. 2026-08-20 에 GOTOOLCHAIN=go1.26.5 build.sh 로 한 번 빌드한 것은<br>> 맞지만(툴체인 캐시 ~/gopath/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.5 가<br>> 남아 있다), lo (이하 발췌 생략) | 원문 바로 아래에 2026-09-07 정정이 이미 붙어 있다. 2026-08-20 단일 빌드와 그 뒤 반복 빌드의 Go 판본을 나눈 그 정정을 그대로 읽는다. | 같은 파일 31행 아래 정정문, `docs/S5_test_hygiene.md` | 재확인 |

### 2-3. 표 밖 추가 행

REPORT_CLAIMS 표에 없던 행이다. 30행 합계에 넣지 않고 따로 센다. Q-18은 gen-2 C1 문서의 알려진 결함 절이 gen33 클라이언트와 맞지 않는 점을, Q-22는 p15 검사 이름을 다룬다. 나머지 8행은 DC-07이 위치로 적은 문장이다. 이 절의 인용 칸은 R-E final 작업 트리의 원문을 굵게 표시까지 그대로 옮겼고, 표 칸이 깨지지 않게 세로줄 앞에만 역슬래시를 붙였다.

| 항목 | 파일·행 | 틀린 문장(원문 인용) | 맞는 문장 | 근거 | 성격 |
| --- | --- | --- | --- | --- | --- |
| Q-18 | `pq_afec/docs/C1 서버 피드백 설계.md:109` 알려진 결함 절, 119~121행 (로컬 보존) | ## 알려진 결함 (2026-09-07 코드 감사, 미수정)<br>(중략)<br>처방(미적용): 패리티 블록 헤더의 원본 CRC 목록으로 재전송을 가른다(재전송은<br>패킷 번호가 바뀌어 CRC 가 다르다). m=0 연결은 패리티가 없어 못 가르므로<br>별도 `rxRetx` 필드로 드러내거나 첫 서버 송신 이후의 Initial 을 제외해야 한다. | 서버의 RxOrigN과 RxParityN이 첫 Handshake를 보기 전 원시 계수라 중복과 재전송이 섞일 수 있다는 사실은 여전히 맞다. 그러나 gen33 클라이언트의 matchFirstFlight는 T4 이전부터 first flight CRC 목록과 서버의 실제 수신 CRC를 대조하고 있었다. 그래서 '처방(미적용)' 문장은 gen33 클라이언트에 맞지 않는다. m=0 연결도 클라이언트가 보낸 원본 CRC 목록으로 같게 대조한다. | `docs/c1_status.md:5`, A3-15 | 정오표, 표 밖 |
| Q-22 | `pq_afec/experiments/results/p15_v2policy.json`의 checks[6] (로컬 보존) | 임계사이/무손실: 수렴 후 평상시 선택이 pad(δ=1) (ips 1281 과반) | 이 검사는 ips 분포만 본다. A1 감사가 같은 결과의 cert 4032, 무손실 auto 행을 다시 읽으니 3~10 라운드마다 1600연결 중 1520연결이 m=1 parity를 함께 보냈고 80연결만 padding만 보냈다. 현재 소스 `pq_afec/experiments/p15_v2policy.py:482`는 검사 이름을 'IPS 1281이 과반 (FEC 결합 포함)'으로 바꿨지만 결과 파일에는 옛 이름이 남아 있다. 판정은 m_used와 추가 byte를 함께 본다. | `A1_numeric_audit_v1.json`의 p15_pad_rounds, `a1_numeric_audit_v1.py` | 정오표, 표 밖 |
| DC-07 | `pq_afec/docs/다음 세션 인계.md:15` 15~16행 (로컬 보존) | 신용을 사야 하는데, 그 바이트를 **의미 없는 패딩(δ)** 대신 **패리티(m)** 로<br>내면 같은 신용을 사면서 **손실 복구까지 덤으로 얻는다.** 그 교환을 언제 | parity는 별도 datagram이라 클라이언트가 보내는 byte가 실제로 늘고, 용량 부등식 C ≤ (k−1)(W−h−f) 때문에 측정한 12개 설정 모두 padding 자리 안에 parity를 넣지 못했다. 기존 u≤10 Mbps 측정 셀에서 lead parity는 credit 전용이고 trailing parity가 경주 뒤 복구에 쓰인다. 복구를 덤으로 얻는다고 쓰지 않고 byte 비용을 함께 적는다. 이 파일은 3절의 작업 메모다. | `docs/REPORT_CLAIMS_v33.md`의 '쓰면 안 되는 주장' 표에서 같은 parity 바이트 행과 추가 비용 행, `pq_afec/experiments/results/p1_flight.json`의 capacity_checks | 정오표, 표 밖 |
| DC-07 | `pq_afec/docs/선행연구 대조.md:326` 326~327행 (로컬 보존) | **「어차피 증폭 신용을 사려고 내보내야 하는 패딩 바이트를, 같은 신용을 사면서<br>복구까지 되는 패리티로 바꾼다」** 이다. 위 §0~§5 의 신규성 논증은 **앞의 질문**에 | 2026-08-19 방향 전환 때 적은 주장 요약이다. parity가 padding 자리를 비용 없이 채우지는 못한다(12/12 설정 위반). lead parity는 credit 전용이고 trailing parity가 복구를 맡는다. 기여는 credit을 사려고 늘리는 byte를 padding 대신 parity로 내는 교환으로 좁혀 쓰고 byte 비용을 함께 적는다. | `docs/REPORT_CLAIMS_v33.md`의 같은 표, `pq_afec/docs/선행연구 대조.md:16` | 정오표, 표 밖 |
| DC-07 | `pq_afec/docs/PADFEC v2 명세.md:883` 883~884행 (로컬 보존) | 1. **양자 경계 절벽** — `Δ_min = 1` 따름정리와 그 실측. 기본값이 최악점에<br>   걸터앉는다는 사실. **새로 만든 것, v2 의 헤드라인.** | 같은 저장소 선행연구 대조 A부(2026-08-28)는 '신규성 주장을 좁혀야 한다'고 판정했다. amplification limit 때문에 PQ handshake가 왕복을 더 쓴다는 정량화와 클라이언트가 byte를 늘려 예산을 사는 lever는 선행연구에 있다. Δ_min = 1 따름정리와 실측은 인용할 수 있지만 '새로 만든 것, v2의 헤드라인'이라는 서열은 쓰지 않는다. | `pq_afec/docs/선행연구 대조.md:16`, `docs/REPORT_CLAIMS_v33.md`의 '쓰면 안 되는 주장' 표에서 선행연구 위치를 다룬 행 | 정오표, 표 밖 |
| DC-07 | `pq_afec/docs/알고리즘 명세 v0.2.md:260` (로컬 보존) | - **캐시가 어떻게 틀려도 콜드보다 나쁘지 않다** (인계 문서의 요구사항). | 이 결론은 같은 문서 '(w, z) 격자 결과' 절(시드 32)에서 z=1.5, w=100일 때 cache가 틀린 셀의 최악 후회가 같은 z의 cold 최악 33.5%를 넘지 않았다는 판정이다(wrongLO 33.5%로 같다). 같은 저장소 실측 보고서.md 4.1절의 짧은 연결 표에서는 cache 5배 과대의 최악 후회가 108.8%로 cold 64.5%보다 나빴다. '어떻게 틀려도'로 일반화하지 않는다. | `pq_afec/docs/알고리즘 명세 v0.2.md`의 '(w, z) 격자 결과' 절, `pq_afec/docs/실측 보고서.md:316` | 정오표, 표 밖 |
| DC-07 | `pq_afec/docs/PADFEC 실측 보고서.md:60` (로컬 보존) | - **실측 결과** — 12개 설정 중 12개 위반. 최소 초과 **60.0 B** (X25519MLKEM768 / Initial 1450 B — C=1449 B, 용량 1389.0 B), 우변이 0 이 아닌 4개 설정 전체로는 60.0 ~ 318.5 B 초과. | 60.0 B는 2026-08-27 보고서 기준 값이다. 2026-10-01 p1_flight.json 기준으로는 같은 설정(X25519MLKEM768, Initial 1450 B)에서 C=1457 B, 용량 1388.0 B라 69.0 B를 넘는다. 두 시점 모두 12/12 위반이다. 초과분은 라운드마다 흔들리는 관측값이라 설정과 자료 날짜를 함께 인용한다. | `pq_afec/experiments/results/p1_flight.json`의 capacity_checks[11], `docs/REPORT_CLAIMS_v33.md`의 추가 비용 행 | 정오표, 표 밖 |
| DC-07 | `pq_afec/README.md:54` (로컬 보존) | python experiments/loop2.py --status | 새 clone에서 이 명령은 단계 전부를 '무효, 코드가 바뀜'으로 표시한다. 단계 지문에 Python 판본과 실행 경로, platform, CPU 수가 들어가고 2026-10-07 코드 수정 뒤 재측정이 없어서이며 결과 파일이 틀렸다는 뜻은 아니다. gen-2 판정은 `pq_afec/experiments/state/loop2.json`과 `pq_afec/experiments/state/fixloop_triage.json`에서 읽는다. 첫 판정은 통과 17, 실패 7, 미실행 1이고 마지막 state는 통과 18, 실패 6, p6 stale이다. | RP-03, `pq_afec/experiments/_journal.py:150` | 정오표, 표 밖 |
| DC-07 | `pq_afec_gen31/g3/RESULT_stage3.md:12` (로컬 보존) | \| H1 \| 1회차: 큰cert g2−g3 +28.01 ms(Holm 하한 24.33), RTT200 +12.38 ms(하한 10.76), 둘 다 B 초과, 하한 평균 17.55. 2회차: +28.92 ms [25.58, 32.26], +10.33 ms [7.33, 13.33](보정하지 않은 95%) \| **개선 주장 성립** (두 회차 같은 방향) \| | 이 H1 값은 quic-go 서버의 initial cwnd 32 패킷 조건에서 token과 resumption을 끄고 잰 값이다. 첫 접속이나 유효한 token, ticket이 없는 재방문에 대한 조건부 결과다. RFC, quiche, msquic의 initial cwnd는 10 패킷이고 IW 10 서버 profile은 재지 않았다. 인용할 때 'quic-go IW 32, token과 resumption 끔' 단서를 붙인다. | `docs/REPORT_CLAIMS_v33.md`의 '쓰면 안 되는 주장' 표 첫 행과 큰cert H1 행, `docs/T7_conditions_v31.md`, `docs/J8_profiles.md` | 정오표, 표 밖 |
| DC-07 | `pq_afec_gen31/g3/RESULT_stage3.md:36` (로컬 보존) | \| S 큰cert(16000, 2 Mbps, RTT 50) \| 128.47 ms \| 100.46 ms \| +28.01 \| 0.000 / 0.618 \| 4,149 / 7,864 B \| | 12행과 같은 단서(quic-go initial cwnd 32, token과 resumption 끔)를 붙인다. ms 차이만 싣지 않고 같은 행의 first flight uplink(g2 4,149 B, v3.1 7,864 B)를 함께 적는다. | `docs/REPORT_CLAIMS_v33.md`의 큰cert H1 행과 H1 이득 행 | 정오표, 표 밖 |

## 3. 작업 메모 표시

아래 네 파일은 2026-08~09에 쓴 작업 메모다. 안에 있는 "다음 할 일", "먼저 읽을 것", "커밋은 안 했다" 같은 문장은 쓴 날의 사실이다. 현재 상태와 읽는 순서는 gen33 `docs/`의 정본을 따른다. 옛 '먼저 읽을 것' 문서에 정정 줄을 다는 일(BL-10)은 D61 때문에 하지 않고 이 표시로 대신한다.

| 파일 | 쓴 시점 | 읽는 법 |
|---|---|---|
| `pq_afec/docs/다음 세션 인계.md` (로컬 보존) | 4행 "마지막 갱신: 2026-09-08 09:50" | 2026-09-08까지의 인계 기록이다. 15~16행은 2-3절, 30행은 2-1절에 정오표가 있다. |
| `pq_afec/docs/이어서 작업 프롬프트.md` (로컬 보존) | 파일 안에 날짜가 없다. R-E 이력에서 이 파일을 바꾼 커밋은 2026-08-20의 `6dbf9e8` 하나다. | 새 세션에 붙이던 안내문이다. 세부는 다음 세션 인계를 가리킨다. |
| `pq_afec/docs/할 일 목록.md` (로컬 보존) | 3행 "작성 2026-08-26", 66행에 2026-08-30 현황 덧붙임 | 작성 당시 사람이 할 일을 모은 목록이다. 지금 할 일 목록으로 읽지 않는다. |
| `pq_afec/docs/수정 대기 목록.md` (로컬 보존) | 3행 "작성 2026-08-26" | 2026-08-26 점검 목록이다. 항목별 현재 상태는 2-1절의 수정 대기 목록 행에 있다. |

## 4. 봉인 문서의 알려진 문구 결함

gen31 g3/PROTOCOL_stage3.md 3행은 "초안이다. 봉인 전이고 3단계 측정은 없다"로 남은 채 stage3에 봉인됐다. 같은 폴더 g3/RESULT_stage3.md 101행의 문서 결함 절이 이 사실을 적었고, 봉인 뒤 고치면 측정이 개발 자료로 강등되므로 고치지 않았다고 썼다. 정오표는 2-1절 Q-19 첫 행이다.

gen31 트리 안의 g3/SEAL_stage0.json과 g3/SEAL_stage2.json은 gen3에서 물려받은 봉인이다. gen31 현재 트리에서는 일부 파일만 맞고 원래 gen3 트리에서는 전부 맞는다(2-1절 Q-19 둘째, 셋째 행). R-E의 봉인 대조 107개는 gen31 SEAL_stage3.json과 gen3의 봉인 세 개를 보며, gen31 안의 상속 봉인 두 개는 대조 대상이 아니다.

gen31 g3/RESULT_stage3.md의 큰 cert 값(12행 H1, 36행 S 큰cert)은 quic-go initial cwnd 32 패킷, token과 resumption을 끈 조건의 값이다. 정오표는 2-3절 마지막 두 행이다.

## 5. 합계와 관련 문서

정오표 29 + 재확인 1 = 30, 볼트 5행은 D78로 Claude 몫, 합 35 (로컬 보존)

2-1절은 실제 정정 16행과 상태 주석 13행, 2-2절은 재확인 1행이다. 볼트 5행은 2026-11-07 Claude 세션이 D78대로 처리했고 그 내용은 이 문서로 옮기지 않았다 (로컬 보존). 2-3절의 표 밖 추가 행은 Q-18 1행, Q-22 1행, DC-07 위치 8행으로 모두 10행이며 위 합계에 넣지 않았다.

보고서 수치와 원자료의 대응은 [REPORT_NUMBERS_CROSSWALK.md](REPORT_NUMBERS_CROSSWALK.md)에 있다.
