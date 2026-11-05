# T7 비교 조건: v3.1 봉인 조건과 gen33 기본값

2026-11-02, V33FIX 묶음 B. 같은 날 통합 정리(묶음 G)에서 `-feedback` 행, 예시 두 갈래, 규칙 3의 조건을 더했다. 이 문서는 gen33 `qamp`를 v3.1 봉인 측정과 같은 조건으로 돌리는 방법과, 같은 서버에 여러 세대 클라이언트를 붙일 때의 규칙을 정한다. 측정 결과는 없다. 아래 표의 v3.1 값은 `C:\dev\pq_afec_gen31\experiments\quicbed\qamp.go`(읽기만)에서, gen33 값은 이 저장소의 `experiments/quicbed/qamp.go`에서 읽었다. 수정 내역과 검증은 `docs/V33FIX_testbed.md`에 있다.

## 한 번에 맞추기: `-profile sealed31`

서버와 클라이언트 양쪽에 `-profile sealed31`을 준다. 이 프로필은 아래 표에서 "sealed31" 칸의 값을 한꺼번에 설정한다. 같은 플래그를 명시하면서 다른 값을 주면 종료 2로 거부한다(예: `-profile sealed31 -udp-path oob`). 같은 값을 명시하는 것은 허용한다. `-expect-k`는 v3.1에도 있던 플래그라서 명시한 값을 그대로 쓰고, 생략했을 때만 0(타이머만)으로 둔다. `-feedback`은 프로필이 정하지 않는다. 쓰임에 따라 아래 두 예시 가운데 하나를 고른다.

봉인 v3.1 조건 재현. v3.1 3단계 봉인 러너는 gen31 `experiments/p21_gencompare.py`다(gen31 `g3/PROTOCOL_stage3.md` 5행). 이 러너의 `start_server`(2264~2280행), `run_client`(2323~2336행), 팔 표 `ARMS`(293~306행) 어디에도 `-feedback`이 없다. 공용 하네스 `experiments/g3bed.py`의 `start_server`(261~273행)와 `run_client`(346~362행)도 같다. gen31 `experiments`에서 `-feedback`을 넘기는 러너는 `p17_adaptive_value.py`(367행) 하나다. 그래서 재현할 때는 양쪽 모두 끈다. 아래 클라이언트 줄은 3단계 고정 팔 `g3fixL3`(m4L3, `ARMS` 298행)이다. 그 러너는 `-expect-k`를 조건의 k(ML-KEM 조건은 2), `-gap`을 50 ms(netem 대역 제한이 없는 조건은 8 ms), `-timeout`을 10 s로 명시했다(`profile` 274~278행, `TIMEOUT_S` 88행, `run_client`). `-expect-k`를 명시하면 sealed31은 그 값을 그대로 쓴다. 셀마다 다른 `-group`, `-uplink-mbps`, netem 조건은 러너의 셀 표를 따른다.

```
qamp -mode server -profile sealed31 -fec on -stats server.json -conn-log conns.jsonl
qamp -mode client -profile sealed31 -fec on -layout v3 -m 4 -lead 3 -expect-k 2 -gap 50ms -timeout 10s -n 200
```

v33auto 학습 팔(T7·X6). auto3의 손실 학습은 C1 회신에서 오는 arrivals(`src` c1)를 쓴다. 클라이언트 `-feedback`을 끄면 `arrivalEvidence`가 `src` none, `c1.reason` disabled를 돌려주고(`experiments/quicbed/observation.go`), 정책은 그 연결의 데이터그램 손실 갱신을 `source_none`으로 건너뛴다(`policy3.go`의 `ArrivalReject`). 그 목적지는 끈끈한 표지 `c1_seen`이 켜지지 않으므로 활성 정책 v3.3.1-dev가 관측과 결정 모두 v3.2-dev와 같게 돈다(`docs/V33FIX_policy.md`). 즉 v3.3의 C1 학습 효과를 재려면 회신이 있어야 한다. 그래서 이 팔은 양쪽에 `-feedback`을 켠다. 이것은 봉인 v3.1 조건과 다른 점이다. 클라이언트 `-feedback`은 HCT 뒤 회신을 최대 `-feedback-wait`(sealed31에서 200 ms)만큼 기다리게 하므로 연결 사이 간격도 달라진다. 이 팔의 결과를 봉인 재현 결과와 같은 조건으로 부르지 않는다.

```
qamp -mode server -profile sealed31 -fec on -feedback -stats server.json -conn-log conns.jsonl
qamp -mode client -profile sealed31 -fec auto3 -cache3 c3.json -feedback -n 200
```

실행 기록에서 확인하는 곳: 클라이언트 행의 `profile`(sealed31일 때만 생긴다), `feedback_wait_limit_ms`, `retrans_layout`, `observation.tracer`, `flight_expectation`, `arrivals.src`. 서버 stats의 `profile`, `udp_path`, `feedback_version`, `fb_sent`.

## 대응표

| 항목 | 플래그 | v3.1 | gen33 기본값 | sealed31 | 바뀐 이유와 결정 |
|---|---|---|---|---|---|
| 서버 UDP 경로 | `-udp-path` | 플래그 없음. `decodeConn`이 `SyscallConn`을 노출하지 않아 quic-go의 basic 경로를 탄다(gen31 qamp.go 2411~2414행, 감사 F4) | `oob` | `basic` | D25, `docs/T5_udp_contract.md`. oob는 SO_RCVBUF·DF·ECN·PKTINFO·핸드셰이크 뒤 GSO를 바꾼다 |
| v3 응답 전 후속 묶음 | `-retrans-layout` | 플래그 없음. 첫 행동의 (L,O,T)를 반복 | `repeat_first` (이번 수정 전에는 `original_first`) | `repeat_first` | D28을 V33FIX가 대체. 이유는 아래 절 |
| C1 회신 켜기 | `-feedback`(서버와 클라이언트 각각) | 끔. 플래그 기본값이 false이고(gen31 qamp.go 3361행), 3단계 봉인 러너도 양쪽 모두 주지 않았다(gen31 `p21_gencompare.py` 2264~2280·2323~2336행, `g3bed.py` 261~273·346~362행) | 끔(플래그 기본값 false) | 정하지 않는다. 봉인 재현은 끄고 v33auto 학습 팔은 켠다 | auto3 학습이 C1 arrivals를 쓰기 때문이다(위 절). 켜면 클라이언트가 HCT 뒤 `-feedback-wait`까지 기다린다 |
| HCT 이후 C1 수집 대기 | `-feedback-wait` | 200 ms 고정(gen31 qamp.go 2695행). 클라이언트 `-feedback`일 때만 기다린다 | 1 s | 200 ms | D23, `docs/T4_observation_contract.md` |
| 클라이언트 qlog tracer | `-client-tracer` | 없음(gen31 클라이언트 `quic.Config`에 Tracer가 없다) | 켬 | 끔 | T4. 비용은 아직 재지 않았다 |
| 서버 C1 회신 판본 | `-feedback-version` | 2(gen31 qamp.go 714행) | 3 | 2 | T4는 판본 3을 도입했다. 판본 2는 F1 수정으로 다시 낼 수 있게 했다 |
| `-expect-k` 생략 시 첫 묶음 해제 | `-expect-k` | 0 = 300 µs 타이머(gen31 qamp.go 3350행) | auto3이면 cached_k를 첫 묶음에만 적용 | 0 (`explicit_timer`) | D26 |
| 서버 인증서 | `-certsize`, `-cert-file` | `makeCert` 무작위 키(gen31 qamp.go 2348행) | 결정적 ECDSA P-256, DER 길이가 certsize와 정확히 같다 | gen33과 같다. 재현하지 않는다 | T1, D22 |
| 서버 주기 stats의 연결별 기록 | 출력 | 100 ms마다 전체 `conns`(gen31 qamp.go 2328·2473행) | `conns` 없음, 계정은 완료·종료 10 s 뒤 만료 | gen33과 같다. 대신 `-conn-log`로 받는다 | T5, 감사 F2 |
| 서버 quic Tracer·ConnContext | 없음 | 없음 | `accountTracer`(qlog 기록 없이 nil trace를 돌려준다)·`accountContext` 상시 | gen33과 같다. 끄는 플래그 없음 | T2·T5 |
| 클라이언트 수신 필터·CID 생성기·첫 비행 경계 검사 | 없음 | 없음 | 상시 | gen33과 같다 | T5 |
| `server_bytes` 집계 | 출력 | `countRx` 전체(gen31 qamp.go 2698행) | 수신 필터를 통과한 비회신 데이터그램(관측 기록) | gen33과 같다 | T4·T5 |
| 오래된 parity 타이머 | 없음 | 세대 구분 없이 현재 묶음을 해제(gen31 qamp.go 1193행) | 세대 번호로 차단 | gen33과 같다(결함 수정) | T5 |
| 서버 복호기 상한 | 없음 | recent 512개, recentTTL 3 s, flightTTL 1 s, 계정 4096개(gen31 qamp.go 1695·1717~1719행) | D24의 비행 개수·바이트 상한과 그룹별 상한 추가 | gen33과 같다 | D24 |
| gen33 바이너리의 `-fec auto`(gen-2 정책) C2 전멸 적립 | 없음 | 있음 | 제거 | gen33과 같다 | D13. v31auto·g2auto 팔은 동결 바이너리를 쓰므로 영향이 없다 |
| 새 기능: lead-hold, token-store, resume, verify-source, revisit-guard, k-inflate, pad-junk, dup | 각 플래그 | 없음 | 기본 꺼짐 | 꺼짐. 명시하면 허용하고 행에 남는다. revisit-guard는 Retry를 tracer로 보므로 sealed31과 함께 쓸 수 없다(종료 2) | M1, T2, T3, M4 |

나머지 공통 플래그(`-certsize` 2955, `-n` 20, `-timeout` 12 s, `-gap` 25 ms, `-m` 1, `-ips` 0, `-parity-delay-us` 300, `-layout` v2, `-lead` -1, `-m-max`·`-uplink-mbps` 생성 표 값)는 두 세대의 기본값이 같다. 생성 표 상수(`mMaxDefault` 3, `uplinkMbpsDefault` 10, `quicgoMaxIPS` 1452, `cPktDefault` 41.983)도 두 `pfail_table.go`에서 같다. quic-go는 두 세대 모두 v0.61.0이다(각 go.mod 19행).

인증서는 v3.1 쪽 값을 하나로 정할 수 없다. `docs/T1_certificate_result.md`에 따르면 같은 PC의 수정 전 S4 바이너리는 목표 2955 B에서 2962 B를 냈고, 봉인 저널 406블록 중 334블록에서 서버 인증서 크기가 달랐으며 최대 차이는 3 B였다. sealed31은 이 무작위성을 재현하지 않고 정확한 2955 B를 쓴다.

## retrans-layout 기본값을 repeat_first로 되돌린 이유

D28은 v3 응답 전 후속 묶음의 기본 모양을 `original_first`(원본 먼저, 뒤 XOR 패리티 1개)로 바꿨다. 그런데 auto3이 행동을 고르는 비용 모형(`layout.evaluate`, Go `p3Evaluate`)은 이 재전송 보호를 반영하지 않는다. `docs/T6_retrans_contract.md` 다섯째 문단이 이를 "기존 실패 근사"라고 스스로 적었고, 이를 맞출 J3는 blocked, J4는 todo다(감사 F4·H). 기본 바이너리가 모형과 다른 와이어를 내면 auto3은 실제와 다른 비용으로 행동을 고르고, X6에서 L1 효과와 재전송 모양 효과가 섞인다. 그래서 기본값을 모형과 같은 `repeat_first`로 되돌렸다. `original_first`는 `-retrans-layout original_first`로 명시할 때만 쓴다. J3·J4가 비용 모형에 L'=0·T'=1을 넣은 뒤에 기본값을 다시 정한다.

## 공통 서버에서 세대를 섞을 때의 규칙

동결 클라이언트(gen-2 `d98b05d7`, v3.1 `g3c_6baf2b52`, v3.2 `gen32_85f54cf5`)의 `parseFeedback`은 판본 2이고 길이가 `12+4*nc`와 정확히 같을 때만 회신을 받는다. 받지 못한 회신은 클라이언트 쪽 `-feedback` 설정과 상관없이 `countRx`로 들어가 `server_bytes`에 더해진다(gen31 qamp.go 1216~1223행). gen33 서버가 비행의 FEC 틀만 보고 클라이언트 세대를 가를 수는 없다. 틀 판본 1(v2 배치)은 gen-2·v3.1·v3.2·gen33이 모두 쓰고, 판본 3(v3 배치)은 v3.1·v3.2·gen33이 함께 쓴다(각 qamp.go의 `fecVer`·`fecVerLead`). FEC를 끈 팔은 틀 자체가 없다. 그래서 서버 플래그로 정한다.

1. 동결 클라이언트가 하나라도 붙는 gen33 서버에서 `-feedback`을 켜면 `-feedback-version 2`(또는 `-profile sealed31`)를 준다. 판본 3 서버에 동결 클라이언트를 붙인 결과는 비교에 쓰지 않는다.
2. 판본 2에서도 gen33 클라이언트의 `arrivals`(src·sent·lost·bitmap·trunc)는 판본 3과 같다. 달라지는 것은 진단 행 `c1.recovered_original`이 0이 되는 것뿐이다. 판본 3의 복원 CRC 진단이 필요하면 gen33 클라이언트만 붙는 서버를 따로 띄운다.
3. 실행마다 서버 stats의 `feedback_version`과 `fb_sent`를 기록하고 확인한다. `-feedback`을 켠 서버(`fb_sent` > 0)가 판본 3이고 동결 클라이언트 팔이 있으면 그 블록은 버린다. `-feedback`을 끈 서버는 회신을 보내지 않으므로(`fb_sent` 0) stats에 `feedback_version` 3이 남아 있어도 이 규칙으로 버리지 않는다. 묶음 B loopback의 `fixed_nofeedback` 서버가 이 경우다(`docs/V33FIX_testbed.md` 부록 A, `srv_fb_sent 0`, `srv_feedback_version 3`).
4. 기존 하네스처럼 팔마다 서버와 포트를 따로 띄우면 이 규칙이 필요 없다. 봉인 v3.1 3단계 러너(gen31 `p21_gencompare.py`)는 `-feedback`을 쓰지 않았고, 팔마다 슬롯(포트)을 나눠 서버를 따로 띄웠다(`ARMS`의 `slot`, `SERVERS_DEFAULT`·`SERVERS_S1`). 감사 F1 검증 의견도 공용 하네스 `g3bed.start_server`를 두고 같은 결론을 냈다.

이 규칙의 근거 시험과 loopback 결과는 `docs/V33FIX_testbed.md` F1 절에 있다.

## 연결별 서버 기록: `-conn-log`

`-conn-log 경로`는 새 파일을 만들고(이미 있으면 종료 2), 계정이 만료·LRU 축출될 때와 SIGTERM·SIGINT 종료 직전에 연결마다 JSON 한 줄을 쓴다. 각 줄은 기존 `conns` 값과 같은 필드에 `key`, `reason`(`expired`·`lru`·`shutdown`), `logged_ns`를 더한 것이다. 연결당 정확히 한 줄이다. 계정 수명(완료·종료 뒤 10 s) 때문에 `expired` 줄은 연결이 끝나고 약 10 s 뒤에 생긴다. 서버를 SIGKILL로 죽이면 아직 쓰지 않은 줄은 잃는다. 서버 stats의 `conn_log`에 기록 줄 수·오류 수·대기 수가 남는다. T7 러너는 서버를 SIGTERM으로 끝내고 이 파일을 읽는다. 기본값은 꺼짐이고 끄면 기존 동작과 같다.

## 아직 재지 않은 것

- 클라이언트 qlog tracer의 비용. 같은 블록에서 `-client-tracer`만 다른 A/A 비교로 HCT 분포 차이를 재야 한다. 그 전에는 tracer를 켠 팔과 끈 팔의 HCT를 섞어 비교하지 않는다.
- `-conn-log`의 서버 CPU 비용. 100 ms마다 만료 처리와 JSON 인코딩을 한다.
- udp-path basic과 oob의 HCT 차이(X3 과제).
- sealed31로 돌린 gen33과 동결 v3.1의 A/A 일치. 표에서 "gen33과 같다"로 남은 차이가 HCT에 얼마나 드러나는지는 이 비교로만 알 수 있다.
