# ML-KEM × QUIC — 증폭 제한과 핸드셰이크 왕복 비용

2026 R&E · 강원과학고등학교
신레오 · 정도현 · 황요한 | 지도 이현미

> **비공개 저장소입니다.** 미발표 연구이므로 학회 발표 전까지 Public 전환하지 마세요.

---

## 한 줄 요약

후양자 키 교환(ML-KEM)이 QUIC 핸드셰이크를 **느리게 만들 것이라 예상했으나, 특정 인증서 크기 구간에서는 오히려 왕복 1회만큼 빠르다.** 원인은 RFC 9000 §8.1의 증폭 제한이다.

---

## 핵심 결과 6가지

| # | 발견 | 수치 |
|---|---|---|
| 1 | ML-KEM은 패킷 수를 늘린다 | 클라 송신 2→3개, 서버 송신 1→2개 |
| 2 | **그런데 손실 취약성은 유의하지 않다** | PTO 12.0% vs 10.4% (z=0.79) |
| 3 | **증폭 임계가 KEM별로 다르다** | X25519 3,300~3,400 B / PQC 5,900~6,000 B |
| 4 | **역전 구간이 존재한다** | 약 3,400~5,900 B에서 PQC가 더 빠름 |
| 5 | 격차는 정확히 왕복 1회 | RTT의 95~99% (RTT 10~200ms) |
| 6 | **원인은 알고리즘이 아니라 바이트 수** | 패딩만 늘려도 임계 이동 |

결과 2가 계획서의 전제를 기각했고, 그래서 FEC의 역할이 바뀌었습니다 → `docs/연구방향_변경보고.pdf`

---

## 먼저 읽을 것

| 목적 | 파일 |
|---|---|
| **전 과정을 알고 싶다** | `docs/종합기술문서.pdf` (50쪽) |
| 왜 방향이 바뀌었나 | `docs/연구방향_변경보고.pdf` (4쪽) |
| 실험을 재현하고 싶다 | `docs/실험환경_명세서.docx` (6쪽) |
| **FEC를 구현할 사람** | `docs/FEC_인수인계.docx` (6쪽) |

---

## 폴더 구조

```
src/        측정 도구 및 스크립트 (최신본)
docs/       보고서 4종 + 선행연구 노트
data/       분석용 엑셀 + raw/ 원시 CSV
archive/    구버전 — 참고용, 사용하지 말 것
```

### src/ 파일별 역할

| 파일 | 줄 | 역할 |
|---|---|---|
| `hct_v2.c` | 120 | TLS 핸드셰이크 측정기. 논블로킹 connect + poll 타임아웃 |
| `run_v3.sh` | 106 | TLS 스윕 오케스트레이터. veth + netem 구성 포함 |
| `qhct.go` | 371 | QUIC 핸드셰이크 측정기 |
| `qpkt.go` | 232 | QUIC 데이터그램 계측 (countConn 래핑) |
| `qamp.go` | — | 증폭 실험 본체 |
| `patch1_certsize.py` | 63 | 인증서 크기 팽창 패치 주입 |
| `patch2_initpkt.py` | 29 | Initial 패킷 크기 패치 주입 |
| `amp_sweep.sh` | 26 | 증폭 임계 스윕 |
| `check_env.sh` | — | 환경 점검 |
| `probe_veth.sh` | — | veth 링크 구성 확인 |

---

## 환경

```
Ubuntu 24.04.4 LTS · Xeon Gold 5218R 40코어 · 125 GiB · sudo 없음
conda env: oreo_34
  OpenSSL 3.5.6 · liboqs-python 0.15.0 · Python 3.12.13
  Go 1.26.5 · quic-go v0.61.0 · iproute2 6.1.0
```

**반드시 먼저:**
```bash
conda activate oreo_34
```
시스템 기본 OpenSSL은 3.0.13이라 ML-KEM을 지원하지 않습니다.

---

## 빠른 재현

### 1. TLS 측정기 빌드
```bash
gcc -O2 hct_v2.c -o hct_v2 \
  -I$CONDA_PREFIX/include -L$CONDA_PREFIX/lib -lssl -lcrypto -lm \
  -Wl,-rpath,$CONDA_PREFIX/lib
```

### 2. 축소 확인 (2분) — 전체 스윕 전에 반드시
```bash
bash run_v3.sh quick
```
첫 줄에 `v0 MTU = 1500`이 뜨는지 확인하세요. 안 뜨면 네트워크 구성이 실패한 겁니다.

### 3. QUIC 빌드
```bash
CGO_ENABLED=0 go build qpkt.go
```
`CGO_ENABLED=0`이 없으면 conda가 지정한 미설치 컴파일러를 찾다가 실패합니다.

### 4. 증폭 스윕
```bash
bash amp_sweep.sh
```

---

## 반드시 알아야 할 함정 8가지

| 증상 | 원인 | 대처 |
|---|---|---|
| `go: command not found` | conda 미활성화 | `conda activate oreo_34` |
| `cgo: C compiler not found` | conda가 CC를 미설치 컴파일러로 지정 | `CGO_ENABLED=0 go build` |
| MTU 변경이 반영 안 됨 (exit 0인데) | **loopback은 조용히 무시** | veth 사용 + `ip link show`로 검증 |
| 측정이 lo로 우회됨 | veth 양끝이 같은 네임스페이스 | 중첩 netns로 분리 |
| `Terminated`만 뜨고 셸 종료 | `pkill -f` 패턴이 부모 셸 포함 | PID 변수에 담아 `kill $PID` |
| 경로를 못 찾음 | 폴더명 `1311 신레오`의 **공백** | 실행 파일을 `/tmp`로 복사 |
| 무한 대기 | 타임아웃 미설정 | `timeout N` 필수, 첫 실행은 n 작게 |
| 순수 ML-KEM 협상 실패 | OpenSSL 3.5 기본이 하이브리드 중심 | 양쪽 `-groups` 명시 + 협상 검증 |

추가: `GROUPS`는 bash 예약변수입니다. 조용히 덮이니 `KEMS`처럼 다른 이름을 쓰세요.

---

## 현재 한계 (논문에 명시 예정)

1. **QUIC 단일 구현** (quic-go v0.61.0) — quiche 교차검증 미완
2. **QUIC은 하이브리드만** — Go crypto/tls가 X25519MLKEM768만 지원
3. 증폭 예산의 구간 분리 불가 — 전체 합산 계측
4. netem 시드 고정 불가
5. 버스트 파라미터(gemodel 5% 50%)에 문헌 근거 없음
6. 단일 인증서로 체인 대체
7. 시점 간 반복 부족 — 증폭 임계만 3회 반복

---

## 다음 할 일

| 과제 | 담당 |
|---|---|
| 패딩→FEC 구현 (Initial 패딩을 XOR 복구 심볼로) | 황요한 |
| quiche 또는 ngtcp2 교차검증 | 신레오 |
| 손실 × 인증서 2차원 스윕 | 공동 |
| 검증 전 구간 계측 (qlog 수준) | 공동 |

FEC 구현은 `docs/FEC_인수인계.docx`에 단계 0~4와 A/B/C 방식이 정리돼 있습니다.

---

## 주의

- `archive/`는 **구버전**입니다. 특히 `hct_client.c`는 타임아웃이 없어 실패가 집계되지 않는 결함이 있고, 1차 스윕 데이터(`sweep1_results.xlsx`)는 loopback MTU 미적용으로 **무효**입니다. 대조·이력 목적으로만 두었습니다.
- 실험은 비특권 사용자 네임스페이스에서 돕니다. `sudo`가 필요한 명령은 하나도 없습니다.

---

## 데이터 주의 (2026-09-07 코드 감사)

`src/` 스크립트 세 곳을 고쳤다. **이미 모은 자료(`data/sweep2_results.xlsx`,
`data/raw/run2.csv`, 증폭 스윕 CSV)는 수정 전 스크립트로 잰 것**이므로 아래를
알고 읽어야 한다.

1. `run_v3.sh` 의 burst 모델은 `gemodel ${loss}% 50%` 였다. netem 의 gemodel 은
   첫 인자가 good→bad 전이확률 p 이고 정상상태 손실률은 p/(p+r) 이다. 그래서
   burst 행의 표기 손실 0.5/1/2/5% 는 실제로 0.99/1.96/3.85/9.09% 였다.
   uniform 과 burst 를 「같은 손실률」로 비교한 문장은 다른 손실률의 비교다.
   지금 스크립트는 p 를 역산해 표기와 실제를 맞추고 `effective_loss_pct` 열을
   더 적는다.
2. 저장소의 `run_v3.sh` 는 netem 을 클라이언트 송신측(v0)에만 건다. 손실도
   클라→서버 방향에만 걸리므로 서버 비행(인증서, 크기가 KEM 과 인증서에 따라
   달라지는 그 비행)은 손실을 안 겪는다. 실험환경 명세서 §3-1·§4-2 의 양방향
   구성과 다르다. 그런데 `종합기술문서.pdf` 4.4 는 *"부록 A 의 run_v3.sh 초판은
   ... 단방향 ... 이후 대화에서 양방향 대칭(각 RTT/2)으로 패치되어 최종 스윕과
   이후 모든 QUIC·증폭 실험에 쓰였다"* 고 적는다. **그 패치된 판은 저장소에
   없다** (`src/run_v3.sh` 는 초판이고 README 는 이것을 최신본이라 부른다).
   sweep2 가 어느 판으로 돌았는지는 스크립트로는 확인할 수 없다. 패치판을 가진
   사람이 올려야 한다. 지금 스크립트는 `NETEM_SIDES=both bash run_v3.sh` 로
   양방향(각 RTT/2, 손실 동일)을 고를 수 있고 `netem_sides` 열이 어느 쪽으로
   쟀는지 남긴다. 참고로 `amp_sweep.sh` 는 문서 부록 A.7 그대로 양방향 지연(각
   25 ms)이라 이 문제가 없다.
3. `hct_v2.c`(와 `qhct.go` 의 같은 자리)는 ok/fail/tmo 를 워밍업 반복까지 셌다.
   n 은 워밍업을 뺀 수라 fail_rate 의 분모와 n 이 서로 다른 집합이었다
   (손실 0 조건에서 워밍업 50 / 측정 250). 둘 다 고쳤다(2026-09-08).
4. `amp_sweep.sh` 의 중앙값 `v[int(NR/2)]` 는 awk 배열이 1 기반이라 짝수 NR 에서
   한 칸 낮은 값을, NR=1 에서 0.0 을 냈다. `v[int((NR+1)/2)]` 로 고쳤다.

근거는 `C:\dev\claude_brain\06 세션 로그\2026-09-07 PAD-FEC 전량 재현과 코드 감사.md`.
