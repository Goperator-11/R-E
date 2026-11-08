# PAD-FEC v3.3.1-dev 알고리즘 명세

## 0. 범위

이 문서는 client first flight의 추가 바이트를 padding 대신 parity datagram으로 보내는 PAD-FEC의 현재 구현을 설명한다. Python이 정책의 기준 구현이며 Go client가 같은 산술을 수행한다. 정책은 행동 `(δ, lead, T)`를 고르고 목적지별 관측 이력을 다음 연결에 넘긴다.

| 이름 | 현재 값 | 의미 |
|---|---|---|
| `POLICY_VERSION` | `v3.3.1-dev` | 활성 정책 판본 |
| `STATE_VERSION` | `11` | Python 목적지 상태의 직렬화 판본 |
| `p3CacheSchema` | `padfec3.cache3/11` | Go cache wrapper의 schema |
| `gen_id` | `v3.3-dev` | 실행 환경을 구분하는 세대 이름 |
| `UDP_MAX` | `1452` | 후보 생성에서 모형 parity 길이에 적용하는 상한, B |
| `EPS` | `0.01` | none 경로의 이진 라벨 오염 확률 |
| `CLASS_EPS` | `0.001` | c1 경로의 등급 라벨 오염 확률 |

`gen_id`는 정책 판본과 별개다. `experiments/pipeline.py`의 `main`은 이 세대 이름으로 옛 파이프라인 실행을 막는다. 과거 문서의 "상태 4"와 "v3.3-dev"를 현재 상태 형식으로 읽지 않는다.

이 명세는 구현 계약이며 성능 결과표가 아니다. 2026-11-07 작성 시점에는 [smoke](FINAL_smoke.md), [M1 A/A](M1_result.md), [X1](X1_result.md), [X9](X9_result.md)의 개발 측정이 완료돼 있다. X6는 [실행 조건](FINAL_X6_run.md)대로 측정을 마쳤고 [결과](X6_result.md)는 개발 측정이다. 옛 문서의 "네트워크 측정 0건"은 그 문서 작성 당시의 상태다. 현재 개발 측정도 confirmatory로 해석하지 않는다.

근거 코드: [learn3.py](../padfec3/learn3.py)의 상수·`DestState3`, [decide3.py](../padfec3/decide3.py)의 `UDP_MAX`, [policy3.go](../experiments/quicbed/policy3.go)의 판본 상수, [genconfig.json](../genconfig.json), [pipeline.py](../experiments/pipeline.py)의 `main`. 원본 문서: [정책 변경 기록](V33FIX_policy.md), [세대 경로](generation_paths.md).

## 1. 문제와 기호

주소 검증 전 서버의 amplification limit은 수신 바이트의 3배다. 비용 모형은 서버가 받은 바이트를 credit으로 바꾸고, ClientHello가 완성된 뒤 그 credit으로 서버 응답을 보낼 수 있는 시점을 계산한다. 서버가 받은 바이트가 credit으로 계수되는 시점과 원본이 복구되는 시점은 따로 다룬다.

| 기호 | 뜻과 단위 |
|---|---|
| `B` | 모형에서 서버 credit으로 계수한 client 바이트, B. 복구한 원본 크기를 포함하므로 물리 수신량 `phys_at_dec`와 다를 수 있다 |
| `AMP` | credit 배수, 3 |
| `S` | 과거 성공 관측에서 추정한 서버 송신 바이트, B. 인증서 파일 크기와 다르다. |
| `P` 또는 `P_SERVER` | 모형의 서버 datagram 크기, 1280 B |
| `W` | 확대 전 원본 Initial의 모형 크기, B |
| `δ` | 원본 하나마다 추가하는 padding 길이, B |
| `W_eff` | `W+δ`, parity symbol 길이의 기준, B |
| `k` | first flight 원본 datagram 수, 모형 지원 범위 1..4 |
| `lead` 또는 `L` | 원본 앞에 보내는 parity 수 |
| `T` | 원본 뒤에 보내는 parity 수 |
| `m` | `lead+T`, 총 parity 수, 0..4 |
| `n_need` | 서버 응답에 필요한 모형 datagram 수 |
| `c_pkt` | 서버 packetization에 쓰는 packet당 보정 바이트 |
| `A_pre` | ClientHello 완성 전 모형 ACK 총량. u>0에서 41(k-1) B, u=0에서 0 B |
| `u` | client uplink 입력, Mbps. 0은 직렬화 지연을 0으로 두는 모형값이다. |
| `RTT` | 정책에 전달한 왕복시간, ms |
| `p` | IID datagram 손실 확률 |
| `J3` 또는 `J` | first flight 배치 비용 모형이 반환하는 기대 시간, ms |
| `HCT` | client에서 관측한 handshake 완료 시간, ms |
| `B0` | 행동 `(0,0,0)`, 확대와 parity가 없는 기준 행동 |

`k`는 성공 연결 이력의 최근 최빈값이다. 빈도가 같으면 가장 최근 값이 이긴다. `S`는 저장된 서버 바이트 이력의 중앙값이다. 서버의 총 송신량, 인증서 DER 크기, first flight 송신량은 같은 양이 아니므로 결과를 읽을 때 계측 필드를 확인한다.

근거 코드: [quantum.py](../padfec/quantum.py)의 `AMP`, `P_SERVER`, `bin_index`; [learn3.py](../padfec3/learn3.py)의 `k_hat`, `s_hat`, `bin_needed_s`; [layout.py](../padfec3/layout.py)의 상수·`preflight_bytes`. 원본 문서: [용어집](GLOSSARY.md), [정책 변경 기록](V33FIX_policy.md), [알려진 한계](FINAL_policy_limits.md).

## 2. 행동과 first flight 배치

행동은 `(δ, lead, T)`다. 원본 datagram 수는 `k`, parity 수는 `m=lead+T`이고, 활성 정책은 `1≤k≤4`, `0≤m≤4`, `0≤lead≤m`을 지원한다. `δ`는 원본 Initial의 목표 크기에 더할 B 수다. 비용 계산에서 원본과 부호 symbol의 크기는 `W_eff=W+δ`이며, Go client는 선택한 크기를 `quic.Config.InitialPacketSize`로 전달한다. 실제 부호기는 수집한 원본 중 가장 긴 길이에 맞춰 짧은 원본을 0으로 채운다. 정책의 목표 크기와 실제 수집된 datagram 길이는 구분한다.

v3 first flight의 송신 순서는 다음과 같다. `L`은 선행 parity, `O`는 원본, `P`는 뒤 parity다.

```text
L × lead, O × k, P × T
```

기본 서버에서 선행 parity는 credit용으로 QUIC 스택에 전달하며 복구에 쓰지 않는다. 뒤 parity는 빠진 원본을 복구할 때 보류하고, 사용한 parity 대신 복원본을 스택에 전달한다. 복구가 끝난 뒤 도착한 parity 등 복구에 쓰지 않은 datagram은 credit으로 전달될 수 있다. 이 순서와 역할 분리는 `lead-hold=false`인 기본 경로의 동작이다.

`levers_s`는 추가 바이트가 없는 행동, amplification budget의 구간 경계를 넘는 padding, parity, padding과 parity를 함께 쓰는 후보를 만든다. 기본 `max_steps=2`, `m_max=4`를 쓰며 combo의 δ는 `quantum._combo_deltas`로 생성한다. 이 경계식은 A_pre를 넣지 않고 gen-2 배치의 credit 가정으로 δ를 만든 뒤 v3 배치를 펼친다. `candidates3`는 같은 행동을 제거하고, parity가 있는 후보마다 `lead=0..m`을 열거한다. 기본 원본 크기 상한과 parity 모형 길이 상한은 모두 `1452 B`다. parity 모형 길이는 `W_eff+39+6k`이므로 다음 한계를 적용한다.

| k | parity 후보의 W_eff 상한 (B) |
|---|---:|
| 1 | 1407 |
| 2 | 1401 |
| 3 | 1395 |
| 4 | 1389 |

`δ=0`일 때 이 값이 base W의 상한이다. combo 행동은 `W+δ`를 비교해야 한다. 예를 들어 `W=1406`이면 `k≥2`에서 parity 후보가 없다. 측정에 쓰는 base `W=1280`은 이 상한 아래다. 이 표는 모형 필터이며 실제 CID 길이에 따른 wire 상한은 3절에서 따로 설명한다.

Go의 `fecConn.WriteTo`는 FEC 모드의 Initial을 모아 `flushFlightFor`에서 내보낸다. 명시한 `expect-k`만큼 모이면 해제하며, 그 전에 시간이 지나면 `parity-delay-us` 타이머가 해제한다. 기본 타이머는 `300 µs`다. `expect-k`를 생략한 auto3 warm 결정은 cache의 유효한 k를 first flight에만 적용하고, 명시한 양수 k는 이후 전송에도 적용한다. `expect-k=0`은 타이머만 쓰는 명시 입력이다. 타이머 callback의 세대 번호가 달라지면 현재 전송을 해제하지 않는다. FEC off는 원본을 즉시 송신하고 같은 구조의 진단 기록만 남긴다.

근거 코드는 [layout.py](../padfec3/layout.py)의 `check_action`, `send_order`, [decide3.py](../padfec3/decide3.py)의 `levers_s`, `candidates3`, [qamp.go](../experiments/quicbed/qamp.go)의 `runClient`, `fecConn.WriteTo`, `flushFlightFor`, [flight_input.go](../experiments/quicbed/flight_input.go)의 `chooseFlightExpectation`이다. 원본 설명은 [V33FIX_policy.md](V33FIX_policy.md), [T5_flush_contract.md](T5_flush_contract.md), [T7_conditions_v31.md](T7_conditions_v31.md)다.

## 3. Wire 형식과 부호기

Go `buildParity`는 QUIC v1 Initial과 같은 long header 형태 안에 PFEC 본문을 넣는다. token length는 0이고 본문 길이는 2 B varint다. PFEC 본문은 표준 QUIC의 암호화된 payload가 아니며 AEAD 인증을 통과하는 QUIC packet도 아니다. 이 형식의 판본과 정책 판본은 서로 다른 번호다.

| 부분 | 길이 (B) | 내용 |
|---|---:|---|
| 바깥 헤더 | `10+D+S_c` | 첫 바이트, QUIC version, DCID·SCID 길이와 값, token length, 본문 길이 |
| PFEC 고정 머리 | 12 | `PFEC` 4, 판본 1, flight 2, k 1, m/lead 1, parity index 1, symbol length 2 |
| 원본 CRC 목록 | `4k` | 원본 datagram별 CRC32, big endian |
| 원본 길이 목록 | `2k` | 0을 채우기 전 원본 길이, big endian |
| parity symbol | `W_sym` | 가장 긴 원본에 맞춰 만든 부호 symbol |

v3 wire 판본은 3이다. m/lead 한 바이트의 상위 4 bit가 lead, 하위 4 bit가 m이다. index가 lead보다 작으면 선행 parity다. 호환 parser는 이전 판본 1도 읽으며 이때 `m≥2`이면 lead를 1로 해석한다. parser가 허용하는 wire 범위는 활성 정책의 `k≤4`, `m≤4`보다 넓으므로 parser의 허용 범위를 정책 후보 범위로 읽지 않는다.

직렬화된 parity 길이는 `W_sym+22+D+S_c+6k`다. 현재 client가 발급하는 SCID는 4 B이고, first Initial의 DCID 길이 `D=8..20` 조건이면 고정 부분은 `34..46 B`다. 비용 모형은 이를 `39 B`로 근사한다. 따라서 `W_eff+39+6k≤1452`를 통과해도 실제 parity가 1452 B 이하라는 보장은 없다. 이 CID 조건에서 1452 B를 넘지 않으려면 `W_sym≤1452-46-6k`여야 한다. 현행 `buildParity`에는 실제 길이 1452 B를 기준으로 송신을 거부하는 분기가 없다. [크기와 수신 상한의 기록](J7_wire_contract.md)에 적힌 46 B 고정 padding은 별도 후보의 설명이며 현재 송신 형식에 적용되지 않는다. 서버 `readFrom`은 기본 프로필에서 datagram을 1472 B 버퍼로 읽어 파싱하고 quic-go에는 앞 1452 B만 넘긴다. `sealed31`은 quic-go의 1452 B 버퍼로 그대로 읽는다. `fec_oversize_read`는 wide read에서 1452 B를 넘은 수신 수이고 0이면 stats에 나오지 않는다.

`parseFecBlock`은 magic·판본·길이·원본 수·parity 수·index·symbol length를 검사하고, 원본 길이가 symbol length보다 길면 거부한다. 보관할 symbol은 입력 버퍼와 별도로 복사한다. PFEC가 있어야 할 본문 시작점에서 magic은 읽히지만 parser가 거부한 수신은 `fec_parse_fail`로 센다. 이 수에는 malformed metadata도 들어가므로 네트워크 잘림 원인만의 계수가 아니다. FEC off는 PFEC 분류를 하지 않는다.

부호기는 GF(256)을 사용한다. `m=1`에서는 모든 원본의 XOR을 쓴다. `m>1`에서는 Cauchy 행렬의 계수 `inv(p xor (m+o))`를 쓰며 p는 parity index, o는 원본 index다. 복구기는 같은 계수를 사용하고, 복원 길이로 자른 원본의 CRC32가 metadata와 맞는지 확인한다. 계수가 m에 의존하므로 m을 늘린 새 부호와 이미 송신한 작은 m의 parity를 같은 부호로 섞을 수 없다.

Python `padfec.codec`의 `pack_footer`와 `unpack_footer`는 시험용 `16 B` footer를 다룬다. `FlightCode.encode`와 `decode`는 그 footer와 별도로 부호 symbol을 처리한다. 이 footer 길이는 Go wire 오버헤드나 비용 모형의 39 B를 대신하지 않는다. 단일 parity의 XOR과 다중 parity의 Cauchy RS라는 부호 규칙을 대조하는 용도다.

근거 코드는 [qamp.go](../experiments/quicbed/qamp.go)의 `buildParity`, `parseFecBlock`, `fecMagicAtBody`, `rsEncode`, `parityRow`, `recoverMany`, [boundary.go](../experiments/quicbed/boundary.go)의 `clientCIDGenerator`, [policy.py](../padfec/policy.py)의 `parity_datagram_bytes`, [codec.py](../padfec/codec.py)의 `FOOTER_FMT`, `FlightCode`다. 원본 설명은 [R3_codec_format.md](R3_codec_format.md), [J7_wire_contract.md](J7_wire_contract.md), [FINAL_policy_limits.md](FINAL_policy_limits.md)다.

## 4. J3 비용 모형

`layout.evaluate`는 행동 하나와 손실률 p를 받아 기대 HCT `J`, first flight의 1-RTT·2-RTT·실패 확률, credit과 직렬화 진단을 반환한다. `J3`는 여기서 비용 함수의 이름이다. 별도 두 단계 재전송 참조 후보의 이름과 구분한다. 그 참조는 활성 비용 함수에 들어 있지 않다.

### 4.1 필요한 서버 packet 수와 완료 경계

현재 결정은 성공 이력에서 저장한 서버 바이트 관측의 중앙값 S를 입력으로 쓴다. 기준 client 크기가 `kW`일 때 `n_base = ceil(3kW/P)`이며, `P = P_SERVER = 1280` B다. `learn3.bin_needed_s`는 `S_abs = S - n_base·c_pkt`를 만들고 `nP >= S_abs + n·c_pkt`를 만족하는 최소 양의 정수 n을 `n_need`로 삼는다. 실제 구현은 `q = S_abs/(P-c_pkt)`를 계산하고 정수 변환 뒤 부등식을 검사해 필요한 경우 1을 더한다. `c_pkt`는 0 이상 P 미만이어야 하고, 분모·몫·packet 바이트의 유한성과 정확한 정수 범위를 검사한다. 인증서 크기를 입력받는 보조 함수 `layout.n_need`와 활성 학습 경로의 `bin_needed_s`는 입력의 뜻이 다르다.

서버가 credit으로 계수한 바이트를 B로 둔 성공 가지가 한 번의 RTT로 끝나는 모형 조건은 다음과 같다.

```text
A_pre = 41·(k-1) B  (u > 0)
A_pre = 0 B         (u = 0)
3B - A_pre > P·(n_need-1)
```

`A_pre`는 server flight 전 ACK의 비용이다. 비교는 엄격한 `>`이고, 같으면 2-RTT로 분류한다. 이는 이 테스트베드의 packet 송신 전 amplification gate를 반영한 모형 경계다. RFC의 byte 상한과 같은 식이라고 일반화하지 않는다. 후보 δ 생성은 이 ACK 항을 넣지 않은 경계식을 사용하므로 비용 평가의 경계와 구분해야 한다.

### 4.2 도착 패턴과 credit 분기

송신 순서는 선행 parity, 원본, 후행 parity다. `outcomes`는 각 datagram의 도착 여부를 0과 1로 열거하고, 독립 손실 가정 아래 패턴 확률을 `p^(유실 수)·(1-p)^(도착 수)`로 계산한다. 각 패턴 확률은 송신 순서대로 곱한다.

`tau(b,u) = 8b/(1000u)` ms이며 u=0에서는 0이다. 현재 `outcomes`의 도착 시각은 도착한 datagram의 직렬화 시간만 순서대로 더한다. 유실 datagram도 실제 uplink 시간을 쓸 수 있다는 점은 이 식의 한계다.

도착 원본 수를 a, 도착 선행 parity 수를 l, 도착 후행 parity 수를 t라 두면, 원본 결손 `k-a`가 0이거나 t 이하일 때 first flight 복구에 성공한다. 선행 parity는 이 복구 조건에 넣지 않는다. 원본이 모두 도착했으면 마지막 원본 도착 시각이 `t_dec`이고, 결손이 있으면 결손 수만큼의 후행 parity가 도착한 시각이 `t_dec`다.

그때 기본 credit은 `B_base = l·parity_bytes(W_eff,k) + k·W_eff`다. 복구에 쓴 parity는 복원한 원본 바이트로 바뀌어 이 값에 들어간다. 결정 이후 남은 후행 parity는 `race_branches`가 추가 credit을 얻는 가지로 나눈다. 후행 도착 지연을 d1,...,dr, `q_j = race_win_prob(dj)`, q0=1이라 두면 j개가 credit에 반영되는 질량은 `q_j-q_(j+1)`이고, 마지막 r개 가지의 질량은 q_r다. 양의 질량만 합산한다.

`race_win_prob`는 고정 지연 표를 선형 보간한다. d<=0이면 1이고, 마지막 마디 1.066 ms 이상이면 0이다. 마지막 표 값 0.004는 그 마디 직전 구간의 보간에 쓰이며 끝점 반환값은 0이다. 이 표와 실패 시간 상수는 `padfec.policy`의 환경별 보정값이므로 다른 서버의 지연 분포를 보장하지 않는다. 늦은 parity가 서버 송신을 바로 깨우지 못하는 quic-go v0.61.0 소스 위치는 connection.go 1052행(handleOnePacket 첫 줄의 ReceivedBytes), 663~671행(복호되지 않은 패킷만 처리하면 송신 판정을 건너뛰는 run loop), sent_packet_handler.go 224~231행(한도 해제 때 loss timer만 다시 맞춤)이다. 이 위치는 소스를 읽어 확인했고 qlog나 packet capture로 직접 확인한 것은 아니다.

### 4.3 성공 비용과 응답 직렬화

성공 가지의 RTT 수 nr은 4.1의 조건에 따라 1 또는 2다. 그 가지의 HCT는 `t_dec + nr·RTT + (nr=2이면 response_term, 아니면 0)`이다. `evaluate`는 패턴 확률과 credit 가지 질량을 곱해 이 값을 누적한다.

`response_term`의 기본 `later="v3"` 값은 `tau(W_eff,u)`다. `later="off"`이면 0이다. 비교용 `later="g2"`는 `tau(W_eff,u)`에 m>=2일 때 k=1 parity의 직렬화 시간, m>=1일 때 0.3 ms를 더한다. 이 항은 둘째 왕복의 정상 응답 직렬화 근사이며 둘째 왕복의 손실과 재전송 꼬리를 모델링하지 않는다.

### 4.4 실패 비용

복구하지 못한 패턴은 도착 원본이 하나도 없으면 `pto`, 일부 원본은 왔으나 마지막 원본이 없으면 `ptoS`, 나머지는 `ack`로 나눈다. `t_last_o`는 도착한 마지막 원본의 모형 시각이며 원본이 전부 없으면 0이다.

성공 질량을 P_s, 실패 질량을 P_f라 하고, 성공 가지에서 누적한 확률 가중 RTT 수를 N_s라 둔다. `n_ok = N_s/P_s`이며 P_s<=1e-15이면 2다. 재시도 배수 `M = 1/(1-P_f)`이며 P_f=1에서는 구현이 M=1을 쓴다. 활성 손실 격자는 p<=0.30이다.

| 실패 종류 | 비용 c (ms) |
|---|---|
| pto | RTT + 200.86 + tau(k·W_eff,u) |
| ptoS | t_last_o + n_ok·RTT + 3.0·RTT |
| ack | t_last_o + n_ok·RTT + 1.1250·RTT + 1.424 |

성공 비용을 먼저 모두 누적한 뒤, 저장한 실패 패턴 순서대로 `패턴 확률·M·c`를 더한다. 표본 PTO 배수 3.0은 측정 적합 상수와 구분한다. `J`에는 별도의 byte 가격이 없고, u=0에서는 직렬화 비용도 0이다. 실패 뒤 선행 parity의 재전송 직렬화, 실제 timer 재무장, 하향 손실은 이 비용에 포함되지 않는다.

### 4.5 출력 확률의 의미

`p_one_rtt`, `p_two_rtt`, `p_fail`은 first flight 분할이다. 성공 뒤 둘째 왕복에서 일어날 손실까지 포함한 실제 HCT 등급 분포가 아니다. `e = p_two_rtt + p_fail`이며, `n_rtt_expected`는 성공 가지의 RTT 수만 확률로 가중한 합이다. `n_rtt_given_ok`는 그 합을 성공 질량으로 나눈 값이다. `client_bytes`는 first flight 송신 크기이고 연결 전체 uplink 사용량이 아니다.

근거 코드는 [layout.py](../padfec3/layout.py)의 `tau`, `n_need`, `preflight_bytes`, `one_rtt_ok`, `outcomes`, `race_branches`, `response_term`, `evaluate`, [learn3.py](../padfec3/learn3.py)의 `bin_needed_s`, `_model_result`, [policy.py](../padfec/policy.py)의 `race_win_prob`와 시간 상수다. 원본 설명은 [정책 변경 기록](V33FIX_policy.md), [둘째 왕복 손실 참조](J1_tail_design.md), [두 단계 실패 참조](J3_reference_result.md), [알려진 한계](FINAL_policy_limits.md)다. 뒤 두 참조의 후보 비용은 활성 비용과 구분해 읽는다.

## 5. Learning layer

### 5.1. 격자 posterior와 연결 시계

손실 격자 `G`는 `table.P_VALS`의 값을 순서대로 쓴다.

```text
0, 0.002, 0.005, 0.01, 0.02, 0.03, 0.04, 0.05, 0.065, 0.08,
0.10, 0.12, 0.135, 0.15, 0.1625, 0.175, 0.1875, 0.20, 0.2125,
0.225, 0.2375, 0.25, 0.2625, 0.275, 0.2875, 0.30
```

각 hazard `h ∈ {1/30, 1/100, 1/300, 1/1000, 1/3000}`마다 격자 posterior `q_h`를 두고, hazard의 가중치 `w_h`를 따로 둔다. 초기 posterior와 가중치는 각각 균등하다. 연결마다 이전 posterior에 균등 사전을 재주입한다. 격자 수를 `N`이라 하면 다음과 같다.

```text
prior_h[i] = (1-h) q_h[i] + h (1/N)
z_h = sum_i prior_h[i] L[i]
q'_h[i] = prior_h[i] L[i] / z_h
raw_h = w_h z_h
```

`raw_h`를 정규화한 뒤 각 가중치를 `W_FLOOR=1e-6` 이상으로 올리고 다시 정규화한다. 결정에 쓰는 혼합 posterior는 `sum_h w_h q_h[i]`다. 관측 우도를 쓸 수 없으면 `predict_step`으로 위 prior만 적용하고 hazard 가중치는 유지한다. 우도 갱신 `filter_step` 안에 이미 이 전이가 있으므로 한 연결에서 예측과 우도 갱신을 중복 실행하지 않는다. `stats.predict`는 이런 연결당 전이 횟수다.

`context`는 갱신 전 이력의 `k`, `S`와 호출자가 전달한 `W`, `u`, `RTT`, `c_pkt`로 만든다. 이력이 없거나 `k`가 지원 범위 밖이거나 양의 RTT가 없으면 문맥은 없다. 현재 연결의 `k`나 `srv_bytes`를 미리 이력에 넣어 문맥을 만들지 않는다.

### 5.2. 목적지 경로 전환

새 상태는 `c1_seen=False`, `arrival_streak=0`이다. 정규화된 `arrivals.src`가 `c1` 또는 `ack`인 관측을 처음 받으면 `enter_c1`이 표지를 True로 바꾸고 기존 guard 경보를 지운다. 잘린 회신이나 `sent=0`도 이 전환을 일으킨다. 전환을 일으킨 관측부터 c1 규칙을 쓴다. 같은 목적지 상태 안에는 none으로 돌아가는 경로나 표지 자체의 만료가 없다. Go wrapper에도 TTL이나 자동 만료가 없다. 저장 형식은 10절에서 설명한다.

none 경로의 관측·결정은 v3.2-dev와의 동치 검증 대상이다. 다만 Python 무작위 열과 Go 비교에서는 상대의 parity 상한도 1452 B로 맞췄다. 원래 v3.2-dev 상한은 1472 B라 후보 집합이 달라지는 문맥까지 결정 동치를 넓혀 말할 수 없다. 원자료 재생의 비교 범위는 [주장 기준의 동치 검증 절](REPORT_CLAIMS_v33.md#v32-dev와-같다는-시험의-범위)을 따른다.

### 5.3. none 경로의 이진 우도

선택 행동의 성공 HCT 이력이 `BASE_MIN=8` 이상이면 그 중앙값을 baseline으로 쓴다. 부족하면 표본 수와 마지막 갱신 순으로 고른 다른 행동의 중앙값에 두 행동의 무손실 `J3` 차이를 더한다. 쓸 수 있는 baseline과 양의 RTT가 있으면 실패 또는 `HCT-baseline >= 0.5 RTT`를 `y=1`, 그 외를 `y=0`으로 붙인다.

손실 0에서 비1-RTT 확률 `e0 >= 0.5`인 행동은 명목 2-RTT로 본다. 그때 RTT가 200 ms 이상이면 `shield`, 나머지는 `nominal2`로 갱신을 건너뛴다. 이 조건이 없고 선택 행동에 guard 경보가 있으면 `guard`로 건너뛴다. 실제 처리 우선순위는 baseline 부재, 문맥 부재, skip 사유, 이진 우도 순이다.

격자별 사건 확률 `e`는 명목 2-RTT 행동이면 first flight 복구 실패 질량, 그 외에는 모형의 비1-RTT 확률 `p_two_rtt+p_fail`이다. `EPS=0.01`을 써서 `L1=(1-EPS)e+EPS(1-e)`, `L0=1-L1`을 만든다. 우도가 적용되면 `loss_update_kind=binary`, 아니면 `predict_only`다. none 경로의 `events`는 실제 이진 갱신에서 `y=1`인 경우에만 증가한다.

### 5.4. c1 경로의 도착 증거와 등급 우도

`arrivals`는 정확히 `src`, `sent`, `lost`, `bitmap`, `trunc`의 다섯 필드를 받는다. `None`은 계수 0의 `src=none`으로 정규화한다. `sent`와 `lost`는 bool이 아닌 정수이며 `0 <= lost <= sent <= 8`이다. bitmap은 null 또는 정수 0/1 목록이다. 완전한 bitmap은 길이가 sent이고 0의 수가 lost여야 한다. 잘린 bitmap은 길이 상한만 검사하며 손실 우도에는 넣지 않는다.

`src`가 c1/ack이고 `trunc=False`, `sent>0`이면 도착 증거를 쓴다. 격자 우도는 `p^lost (1-p)^(sent-lost)`이며, 구현은 1에서 시작해 p를 lost번 곱하고 1-p를 sent-lost번 곱한다. 이항계수와 EPS 평활화는 없다. 이 우도는 문맥·baseline 부재나 handshake 실패와 관계없이 쓸 수 있으며 HCT 우도를 추가로 곱하지 않는다.

도착 증거를 쓸 수 없고 문맥이 있으면 HCT를 세 등급으로 나눈다. 첫 경계는 `1.5 RTT + tau(k W_eff + lead parity_bytes(W_eff,k),u) + 3.0 ms`, 둘째는 첫 경계에 RTT와 `response_term(...)`을 더한 값이다. 성공 HCT가 첫 경계 미만이면 `one_rtt`, 첫 경계 이상·둘째 미만이면 `two_rtt`, 둘째 이상 또는 실패이면 `late_or_failure`다. 각 등급 확률 `q`는 `layout.evaluate`의 `p_one_rtt`, `p_two_rtt`, `p_fail`을 사용한다. `CLASS_EPS=0.001`로 우도를 `(1-CLASS_EPS)q + CLASS_EPS(1-q)/2`로 만든다. 문맥도 없으면 예측만 한다.

3.0 ms는 고정 등급 여유다. `p_fail`은 first flight 복구 실패 확률이라 늦은 HCT 전체의 확률과 같지 않다. 관측 어댑터는 실제 물리 도착을 보증할 수 없는 ACK·늦은 도착·복구 원본을 완전한 arrivals로 만들면 안 된다. 학습 API가 그 진위를 판별하지는 않는다.

c1 경로의 guard 잔차는 기록만 한다. 경보와 가산 벌점은 없고 CUSUM이나 β 반응도 활성 결정에 없다. usable 도착 증거가 이어지면 `arrival_streak`를 최대 8까지 늘리고, 그렇지 않으면 0으로 만든다. `events`는 우도 종류와 관계없이 `y=1`이면 증가한다. `legacy_skip_reason`은 예전 이진 경로의 진단이므로 실제 학습 누락 여부는 `loss_update_kind`로 읽는다.

### 5.5. 이력 반영과 오류

손실 갱신 뒤 성공 연결의 유효한 `k_obs`를 최대 16개, 행동별 HCT를 최대 32개 보존한다. 양의 `srv_bytes`는 `y != 1`일 때만 최대 16개 보존한다. 그래서 도착 우도가 있어도 서버 바이트 추정의 표본 선택은 남는다. `observe3`는 상태 사본에서 검증·갱신한 뒤 성공했을 때 원본을 교체하므로 입력 오류가 원본 상태의 일부만 바꾸지 않는다.

근거 코드: [learn3.py](../padfec3/learn3.py)의 `normalize_arrivals`, `context`, `predict_step`, `filter_step`, `baseline`, `likelihood`, `arrival_likelihood`, `class_likelihood`, `enter_c1`, `_observe_none`, `_observe_c1`, `observe3`; [table.py](../padfec/table.py)의 `P_VALS`. 원본 문서: [L1 학습](L1_learning.md), [관측 계약](L1_observation_contract.md), [현재 경로 변경 기록](V33FIX_policy.md), [record_only의 설계 배경](L3_monitor_design.md). 원본의 상태 4 설명보다 이 명세와 현재 코드를 우선한다.

## 6. 결정 규칙

### 6.1 입력과 기본 행동

`decide3`는 먼저 W·uplink·RTT·c_pkt·later·후보 생성 선택지를 검사한다. W는 bool이 아닌 정수이며 1200 B 이상, uplink는 유한한 0 이상 값, c_pkt는 유한한 0 이상 1280 미만 값이다. `decide3`는 없는 RTT 또는 0 RTT를 기본 행동으로 처리하지만, 음수·비유한 RTT는 거부한다. `decide_core`는 양의 RTT와 S, 1..4의 정수 k, 합이 1인 비음수 posterior를 요구한다. 확률 합 오차 허용치는 1e-9다. 바이트와 비용 산술은 정확한 정수 범위 및 유한성 검사를 통과해야 한다.

목적지 표지 `c1_seen`은 bool이어야 한다. `arrival_streak`는 0..8의 정수이고, none 경로에서는 0이어야 한다. c1 경로에 guard 경보가 남은 상태는 거부한다. 명시 행동 `actions=`는 각 원소가 음수가 아닌 정수 `(δ,lead,T)`이고 lead+T<=4인지 검사하지만, 자동 후보 생성의 UDP 크기 필터를 따로 적용하지 않는다. 이 입력은 Python 진단 경로이며 기본 auto3 후보와 같은 제한이라고 읽지 않는다.

k 추정은 성공 이력의 최근 최빈값이며 동률이면 가장 최근 값이다. S 추정은 저장 창의 중앙값이다. S 또는 k 창이 비면 `why="cold"`, k가 1..4 밖이면 `"k_range"`, 유효 RTT가 없으면 `"no_rtt"`로 `B0=(0,0,0)`을 반환한다. 이 결과의 `ej`, `score`, `W_eff`, `client_bytes`, `j3_pred_pre_ms`는 null이다.

### 6.2 기대 비용과 동점

평가할 posterior는 hazard 성분들의 가중 혼합이다. `decide_core`는 각 후보의 기대 비용 `ej(a)=sum_g posterior[g]·J3(a,G[g])`를 계산한다. 합은 0.0에서 시작해 격자 인덱스 순서대로 더하며 질량이 정확히 0인 격자점은 건너뛴다. none 경로에서는 경보가 유효한 행동에 guard 벌점을 더하고, c1 경로에서는 `pen=0`이다. 결정 점수는 `score=ej+pen`이다.

최소 점수를 jmin이라 할 때 `score<=jmin+0.01 ms`인 후보만 동점 집합에 넣는다. `J_TIE=0.01 ms`는 none 학습 우도의 `EPS=0.01`과 다른 상수다. 동점 집합에서는 다음 튜플을 사전식으로 비교해 가장 작은 후보를 고른다.

```text
(added, m>0이면 0 아니면 1, mode,
 lead==legacy_lead(m)이면 0 아니면 1,
 score, lead, m, delta)
```

`added`는 기본 kW 대비 증가한 first flight 바이트다. `mode`는 문자열 순서로 비교한다. `legacy_lead(m)`은 m>=2에서 1, 그 밖에서 0이다. 바이트 비교가 전체 목적함수인 것은 아니며 최소 점수의 0.01 ms 이내에서만 이 순서를 쓴다.

각 후보의 `n2`는 p=0에서 `e>=0.5`인지 나타낸다. 주 선택이 n2이고 n2가 거짓인 대안이 있으면 `reeval_cond=True`다. 대안은 n2가 거짓인 후보들에 같은 점수·동점 규칙을 적용해 고른다.

### 6.3 guard와 재평가

guard 잔차는 성공 관측의 `HCT-j3_pred_pre_ms`다. `j3_pred_pre_ms`는 벌점 없는 ej다. 공통 잔차 창은 최근 64개, 행동별 창은 최근 32개를 저장한다. 공통 지연 b는 공통 창의 중앙값이며 빈 창이면 0이다. none 경로에서는 잔차를 기록한 뒤, 아직 경보가 없고 행동 창이 8개 이상이며 `행동 중앙값-b>0.5·관측 RTT`인 모든 행동에 경보를 세운다. 이미 경보가 있으면 조건이 약해져도 만료 전까지 유지한다.

결정 시 유효 경보의 벌점은 `max(0, 행동 중앙값-b)`다. 현재 `n_dec-경보 시점>=64`인 경보는 그 결정의 벌점 계산에서 제외한다. 선택을 마친 뒤 `guard_refresh`가 경보와 해당 행동의 잔차 창을 지운다. c1 경로는 잔차 창의 유한성만 검사하며 벌점과 경보를 쓰지 않는다.

재평가는 `not c1_seen or arrival_streak==0`일 때 열려 있다. 이 조건과 `reeval_cond`를 함께 만족한 결정에서만 재평가 계수기를 센다. `(n_reeval+1)%16==0`이면 대안을 최종 행동으로 바꾸고 `why="reeval"`로 기록한다. 따라서 모든 연결의 16번째가 아니라 조건을 만족한 결정의 16번째마다 재평가한다. 직전 관측까지 완전한 도착 증거가 이어진 c1 목적지는 재평가를 보류하며, 현재 연결의 미래 회신 여부는 쓰지 않는다.

### 6.4 상태 변경 순서와 비교 범위

`decide3`는 표지·입력을 검증한 뒤 공통 지연과 벌점, posterior, 문맥, 후보 점수와 재평가를 계산한다. none 경로의 만료 경보를 지운 뒤 `n_dec`를 1 늘린다. B0 결정도 여기에 포함된다. 그 뒤 적격 재평가 계수와 재평가 통계를 갱신하고, 선택 이유·경보·정책 경로·연속 도착 증거 수를 반환한다. 이 함수는 연결당 한 번 호출하는 상태 변경 함수다.

none 경로의 학습·벌점·재평가 규칙은 v3.2-dev와 비교한다. 결정 동치의 범위는 두 참조의 UDP 상한을 1452 B로 맞춘 회귀 검사와 원래 W=1280 궤적 재생이다. 원래 v3.2의 1472 B 상한까지 허용하는 모든 문맥과 전역적으로 같은 후보를 만든다는 뜻은 아니다. c1 경로는 L1 관측과 record_only 결정을 쓰며 CUSUM이나 β 비용 보정은 활성 정책에 없다. c1 전환 전의 none 학습 이력이 남기 때문에 처음부터 c1을 쓴 궤적과도 구분한다.

근거 코드는 [decide3.py](../padfec3/decide3.py)의 `decide_core`, `pick`, `tie_key`, `b0_result`, `decide3`, [learn3.py](../padfec3/learn3.py)의 `check_transport`, `check_model_arithmetic`, `check_probabilities`, `k_hat`, `s_hat`, `guard_record`, `guard_check`, `guard_penalty`, `guard_refresh`다. 원본 설명은 [정책 변경 기록](V33FIX_policy.md), [record_only 설계 기록](L3_monitor_design.md), [비교 범위와 주장 기준](REPORT_CLAIMS_v33.md), [알려진 한계](FINAL_policy_limits.md)다. 과거 문서의 평균 잔차나 상태 판본 설명은 현재 구현의 중앙값과 판본을 대신하지 않는다.

## 7. C1 회신과 신뢰 경계

C1은 서버가 받은 datagram을 client에게 알려 주는 비표준 평문 회신이다. 서버와 client의 `-feedback` 기본값은 false다. 서버가 C1을 보내려면 별도로 켜야 하고, client가 학습 증거로 쓰려면 client에서도 켜야 한다.

현재 기본 판본 3의 본문은 `PFBK`, 판본, flight, k, 실제 원본 수, 실제 parity 수, 복구 수, 실제 수신 CRC 목록, 복원 CRC 목록 순서다. 각 목록은 최대 64개이고 목록 개수를 담는 바이트의 상위 bit는 잘림 여부다. raw 수신 수와 복구 수는 각각 1 B이며 송신 전에 최대 255로 제한한다. `feedbackLocked`는 현재 flight 필드에 0을 넣는다. 그러므로 그 필드만으로 first flight를 식별하지 않는다.

client의 `matchFirstFlight`는 자신이 송신한 first flight 원본·parity의 CRC와 서버의 실제 수신 CRC를 대조한다. 중복 CRC를 한 번만 세며, 해당 first flight 목록 밖의 CRC는 별도로 기록한다. 복원 CRC는 물리 도착으로 세지 않는다. `arrivalEvidence`는 송신 CRC가 중복되었거나, 목록이 잘렸거나, first flight의 소켓 쓰기가 실패하면 검열 표시를 붙인다. 회신의 raw 계수를 바로 손실 표본으로 사용하는 것과 구분된다.

기본 설정에서 서버는 첫 Handshake 헤더를 식별하면 연결당 한 번 회신하고 실제 도착 목록을 닫는다. 진단 전용 환경변수 `PADFEC_FB_EARLY=1`이면 Handshake 조건을 우회해 해석 가능한 long header에서 조기 회신할 수 있다. 이 진단 설정은 측정 조건으로 쓰지 않는다. 복원한 Handshake에도 같은 발생 조건을 적용한다. 이는 QUIC 스택이 그 packet의 AEAD 인증을 마쳤다는 관측이 아니다. `truncated=false`도 그 시점의 목록이 저장 상한에 걸리지 않았다는 뜻이며, 이후 늦은 도착까지 포함한 최종 목록이라는 뜻이 아니다. 회신 없음이나 PTO만으로 원본 전멸을 추정하지 않는다.

client 수신 필터는 peer의 IP·port·zone과 자신이 발급한 CID를 확인한다. 첫 SCID뿐 아니라 연결 중 발급한 CID도 추적하며 최대 64개를 저장한다. CRC32와 CID 검사는 메시지 인증이 아니다. peer와 CID를 아는 경로 위 공격자의 회신 위조를 막지 못하며, `c1_seen`을 켜는 관측과 그 뒤 학습·결정에도 영향을 줄 수 있다. 기본 false 설정과 이미 C1 이력이 있는 목적지 cache는 구분해야 한다. flag를 끈다고 저장된 `c1_seen`이 해제되지는 않는다.

client는 성공한 `Dial`의 경과시간을 HCT로 정한 뒤 C1을 기다린다. 기본 대기 한도는 1 s다. `server_bytes`는 C1 datagram을 빼고 대기 중 받은 비회신 datagram까지 센 전체 값이다. 정책에 넣는 S는 parity 지연의 3배만큼 잔 뒤 C1을 기다리기 전에 찍은 `server_bytes_pre_wait`다. 정책 RTT 입력도 대기 전 ConnectionStats이고, 대기 뒤 값은 `path_rtt_after_wait_ms`, `path_rtt_after_wait_valid`에 남는다. C1을 기다리지 않는 연결은 `server_bytes`를 그대로 정책에 넣고 이 세 필드를 행에 쓰지 않는다. 비용 모형에는 C1의 실제 바이트·처리 비용·다음 연결까지의 대기가 없으므로 C1 비용을 0으로 둔 가정과 실제 실행 비용을 구분한다.

서버는 `-feedback-version 2`도 지원한다. 판본 2에는 복원 CRC 목록이 없고 gen-2·v3.1·v3.2 동결 client가 읽을 수 있다. gen33 parser는 두 판본을 읽는다. 동결 client가 붙는 공통 서버에서 feedback을 켤 때는 판본 2를 지정한다. `-profile sealed31`도 이 설정을 적용한다.

근거 코드는 [qamp.go](../experiments/quicbed/qamp.go)의 `buildFeedback`, `parseFeedback`, `matchFirstFlight`, `runClient`, [observation.go](../experiments/quicbed/observation.go)의 `arrivalEvidence`, `feedbackLocked`, `writeFeedback`, [boundary.go](../experiments/quicbed/boundary.go)의 `acceptServerLocked`, `clientCIDGenerator`다. 원본 설명은 [c1_status.md](c1_status.md), [c1_threat_model.md](c1_threat_model.md), [T4_observation_contract.md](T4_observation_contract.md), [L1_observation_contract.md](L1_observation_contract.md), [T7_conditions_v31.md](T7_conditions_v31.md)다.

## 8. 서버와 테스트베드

`decodeConn`은 UDP 소켓과 quic-go 사이에서 parity를 분류하고 원본을 복원한다. 기본 경로는 선행 parity를 스택에 전달하고 뒤 parity를 복구에 사용한다. 원본은 물리 수신 바이트와 스택 인계 바이트를 먼저 계상한 뒤 recent cache에 기록한다. 복구 때는 사용한 뒤 parity를 스택에 중복 전달하지 않으며, 복원본을 예약·전달할 때 `BytesToStack + pendingBytes + 복원본 길이 ≤ BytesIn`을 확인한다. `done`이나 `poisoned`로 표시된 flight는 다시 복구하지 않는다. 이 회계는 같은 수신 바이트를 parity와 복원본으로 두 번 계상하지 않으려는 구현 조건이다.

복호기가 유지하는 주요 상한은 다음과 같다. 저장 payload 상한은 Go 객체와 index 전체의 메모리 사용량 상한을 뜻하지 않는다.

| 대상 | 상한·수명 | 코드 상수 |
|---|---:|---|
| recent 원본 전체 | 512개, 3 s | `recentCap`, `recentTTL` |
| 같은 DCID·계정의 recent 원본 | 64개 | `decoderGroupRecentCap` |
| flight 전체 | 1024개, 1 s | `decoderFlightCap`, `flightTTL` |
| 같은 DCID·계정의 flight | 8개 | `decoderGroupFlightCap` |
| flight당 payload | 32768 B | `decoderFlightPayloadCap` |
| 복호 payload와 pending | 8 MiB, 입력 여유 65535 B 예약 | `decoderPayloadCap`, `decoderInputReserve` |
| 연결 계정 | 4096개, 완료·종료 뒤 10 s 보존 | `connAcctCap`, `accountRetention` |

복호기 입력 보관의 `udpMaxPayload=1472`와 정책 후보 필터의 `UDP_MAX=1452`는 다른 상수다. 기본 프로필의 wide read 버퍼도 이 값이다. 이 저장 상한을 실제 socket 수신이 1472 B까지 항상 성공한다는 보장으로 해석하지 않는다. 최종 복구 실패 계수는 알려진 FEC flight가 TTL에 도달했을 때 부족한 원본이 남았는지를 센다. metadata도 받지 못한 전멸은 알려진 flight 분모에 들어가지 않는다.

`-lead-hold`는 기본 false이며, 켰을 때만 선행 parity까지 보관하는 별도 수신 경로를 쓴다. 기본 개발 설정은 명시 uplink 2000 kbps, margin 1 ms, flight TTL 1 s다. 첫 유효 parity 이후 남은 명목 송신 슬롯의 직렬화 시간과 margin으로 기한을 정한다. 이 경로의 존재가 활성 정책의 비용 모형이나 성능 채택을 뜻하지 않는다.

Linux 서버의 기본 UDP 경로는 `oob`다. `ReadMsgUDP`와 `ReadBatch`를 복호 경로에 연결하고, 원본에는 수신 OOB를 보존한다. 복원본에는 local packet-info만 붙이며 원본을 받지 못했으므로 그 원본의 ECN이나 수신 timestamp를 복제하지 않는다. `ReadBatch` 한 번은 복호 결과 하나를 반환한다. `basic`은 이 확장 경로를 쓰지 않는 비교 설정이다.

v3 client의 서버 응답 전 후속 전송은 기본 `repeat_first`로, 처음 선택한 `(lead,O,T)` 배치를 반복한다. `original_first`를 명시하면 원본 뒤 XOR parity를 `min(1, m)`개 붙이는 별도 배치를 쓴다. 첫 행동의 m이 0이면 parity 없이 원본만 보낸다. 충분히 큰 서버 datagram을 관측한 뒤에는 원본을 즉시 보내고, 첫 행동에 뒤 parity가 있었다면 최대 하나의 XOR parity만 뒤에 붙인다. 각 전송의 시작 시점에 모양을 정해 중간에 바꾸지 않는다.

| 설정 | 기본값 | `sealed31` |
|---|---|---|
| UDP 경로 | oob | basic |
| 응답 전 후속 배치 | repeat_first | repeat_first |
| C1 수집 대기 한도 | 1 s | 200 ms |
| 서버 C1 판본 | 3 | 2 |
| client qlog tracer | 켬 | 끔 |
| 생략한 expect-k | 유효한 auto3 warm 결정이면 cached_k | 타이머만 |

`sealed31`은 위 값과 충돌하는 명시 flag를 거부한다. `feedback` 자체는 이 프로필이 정하지 않는다. 현재 생성하는 정확한 DER 인증서, 수신 필터, 복호기 상한과 계정 hook은 유지되므로 이 프로필만으로 동결 v3.1 바이너리와 모든 조건이 같아지는 것은 아니다.

서버는 결정적 ECDSA P-256 시험 인증서를 만들거나 지정한 PEM을 읽는다. `certsize`는 DER 길이이며 client가 관측한 서버 송신 바이트 S와 다르다. client는 시험 인증서 검증을 생략하고, client와 서버는 path MTU discovery를 끈다. `token-store`, `resume`, `verify-source`, `revisit-guard`는 기본 false이고 0-RTT는 허용하지 않는다. 토큰과 session ticket을 끈 조건의 반복 연결 결과는 일반 배포의 재방문 효과를 뜻하지 않는다.

근거 코드는 [qamp.go](../experiments/quicbed/qamp.go)의 `decodeConn.readFrom`, `settleRecovery`, `stackLocked`, `runServer`, `runClient`, `defaultRunSettings`, `sealed31Settings`, [decoder_index.go](../experiments/quicbed/decoder_index.go)의 `legacyFlightLocked`, `addLegacySymbolLocked`, [hold.go](../experiments/quicbed/hold.go)의 `defaultHoldConfig`, `holdReceiveLocked`, [udp_linux.go](../experiments/quicbed/udp_linux.go)의 `readWire`, `ReadBatch`, `packetMeta.recovery`, [flight_shape.go](../experiments/quicbed/flight_shape.go)의 `flightShapeLocked`, [certificate.go](../experiments/quicbed/certificate.go)의 `serverCertificate`, [boundary.go](../experiments/quicbed/boundary.go)의 `accountEndedLocked`다. 원본 설명은 [T1_certificate_contract.md](T1_certificate_contract.md), [T2_revisit_contract.md](T2_revisit_contract.md), [T5_decoder_contract.md](T5_decoder_contract.md), [T5_udp_contract.md](T5_udp_contract.md), [T6_retrans_contract.md](T6_retrans_contract.md), [M1_hold_contract.md](M1_hold_contract.md), [V33FIX_testbed.md](V33FIX_testbed.md), [T7_conditions_v31.md](T7_conditions_v31.md)다.

## 9. Go 거울과 관문

`qamp -fec auto3`는 Python의 비용 계산, 학습 상태와 결정 순서를 Go로 옮긴 구현이다. Python의 `layout.evaluate`, `learn3.observe3`, `decide3.decide3`에 대응하는 함수는 각각 `p3Evaluate`, `p3Observe`, `p3Decide`다. `experiments/quicbed/policy3_l1.go`에는 datagram 우도, HCT 등급과 범주 우도를 계산하는 함수 및 참조 입력 실행기가 있다. `p3ObserveCandidate`가 none과 c1 관측을 나누며, `p3Decide`가 경로에 맞춰 guard 벌점과 재평가를 적용한다.

실수의 연산 순서도 비교 대상이다. Go는 계산 중간값을 명시적으로 `float64`로 바꾸고, 필요한 합에는 `p3PySum`을 쓴다. 후보 동률 키에 기대 비용과 guard 벌점을 합한 `score`의 정확 비교가 포함되므로 수학적으로 같은 식을 임의로 재배열하는 것은 허용하지 않는다.

두 관문은 `qamp -mode policy3ref`에 JSON 입력을 보내고 응답을 Python 기준과 비교한다. 네트워크 연결이나 실제 성능을 측정하는 관문은 아니다.

| 관문 | 비교 대상 | 판정 범위 |
|---|---|---|
| `experiments/gate_v3_parity.py` | 기본 참조의 상수, 비용 원시값, 결정, 합성 학습 궤적과 추가 seed 표본 | 행동·후보 순서·분류·카운터와 `k_hist`, `S_hist`, `hct` 이력은 정확 비교한다. guard 이력 `g_resid`, `g_common`은 모양만 정확 비교하고 값은 절대오차 1e-9를 허용한다. 비용은 절대오차 1e-9, posterior와 가중치 및 p_mean은 상대오차 1e-12를 허용한다. 비트 일치 수를 별도로 기록한다. |
| `experiments/gate_l1_go.py` | datagram 우도, HCT 경계·등급·확률·우도, none/c1 관측과 전환, 결정·관측 열, 목적지 cache 왕복, 잘못된 arrivals·상태·cache 거부 | 사전 키 집합과 목록 길이를 포함해 재귀 비교한다. 먼저 정확히 비교하고, 다른 실수에만 posterior·가중치·확률·우도·p_mean·p_after의 상대오차 1e-12 또는 나머지 실수의 절대오차 1e-9를 적용한다. S·HCT 창은 정확 비교한다. |

`gate_v3_parity`는 참조가 기록한 소스 지문과 현재 소스, 바이너리와 옆 SHA 파일, 바이너리의 srcsha와 현재 Go 소스 지문을 확인한다. 기본 추가 표본은 결정 5,000개와 원시값 2,000개 이상을 요구하며, `--no-fresh`로 건너뛰면 통과하지 못한다. `gate_l1_go`는 참조 소스 지문과 receipt의 SHA도 확인하고, 바이너리의 policy_version·state_version·udp_max를 참조와 대조한다. 두 관문의 통과는 이 입력 집합과 비교 규칙 안의 구현 일치를 뜻한다.

none 경로와 v3.2-dev를 비교한 회귀 검증은 이 언어 간 관문과 별개다. Python 무작위 열 및 Go 비교는 v3.2의 parity 상한만 1452 B로 맞춘 판을 사용했고, W1 원자료 재생과 폐루프 비교는 원래 1472 B 상한의 판을 사용했다. W1의 W=1280 조건에서 후보 차이가 없었다는 확인 범위와, 큰 W에서 두 상한이 다른 후보를 만드는 사실을 함께 읽어야 한다. 이 명세는 그 기록을 전체 입력에 대한 결정 동치로 넓히지 않는다.

근거 코드: [Go 정책](../experiments/quicbed/policy3.go)의 `p3Evaluate`, `p3PySum`, `p3Observe`, `p3ObserveCandidate`, `p3Decide`, `policy3RefMain`; [L1 거울과 참조 실행기](../experiments/quicbed/policy3_l1.go)의 `p3ArrivalLikelihood`, `p3ClassLikelihood`, `p3RunL1Reference`; [기본 관문](../experiments/gate_v3_parity.py)의 `compare_primitives`, `compare_decisions`, `compare_trajectories`, `binary_report`, `reference_report`, `main`; [L1 관문](../experiments/gate_l1_go.py)의 `expected`, `compare`, `check`. 원본 문서: [Go 이식 기록](V33FIX_policy_go.md), [v3.2 비교 범위](REPORT_CLAIMS_v33.md#v32-dev와-같다는-시험의-범위).

## 10. 상태 직렬화

Python `DestState3.to_json`은 아래 필드를 저장한다. 행동을 key로 쓰는 mapping은 `"δ,lead,T"` 문자열을 사용하며 출력 key를 정렬한다.

| 필드 | 내용과 로드 조건 |
|---|---|
| `v` | 정수 11만 허용한다. 다른 판본은 `state version mismatch`로 거부한다. |
| `k_hist`, `S_hist` | 각각 최대 16개. k는 1 이상 정수, S는 양의 유한수다. |
| `hct`, `hct_seq`, `seq` | 행동별 최대 32개 양의 HCT, 마지막 갱신 순서, 성공 관측 순서다. 순서값은 음수가 아닌 정수다. |
| `post`, `w` | hazard별 격자 분포와 hazard 가중치다. 길이를 검사하고, 음수·비유한수·질량 1에서 1e-9 넘게 벗어난 값을 거부한다. |
| `n_dec`, `n_reeval` | 결정 수와 reeval_cond·reeval_open을 함께 만족한 결정 수, 음수가 아닌 정수다. |
| `g_resid`, `g_common` | 행동별 최대 32개 잔차와 공통 최대 64개 잔차, 모두 유한수다. |
| `g_alarm` | 행동별 경보가 켜진 결정 번호. 음수가 아니며 `n_dec` 이하여야 한다. |
| `c1_seen`, `arrival_streak` | bool과 0..8 정수. False인 상태의 양의 streak와 True인 상태의 남은 경보를 거부한다. |
| `stats` | 관측·우도·진단 계수. 값은 음수가 아닌 정수다. 생략된 기본 계수는 0으로 둔다. |

필수 필드가 빠지면 로드를 실패시킨다. `stats`는 생략할 수 있고, 현재 기본 계수에 입력 계수를 합친다. 상태 version과 주요 수치의 bool 입력은 거부한다. `k_hist`가 모형 지원 상한 4를 넘는 것 자체는 로드 오류가 아니며, 결정 시 `k_range`로 B0를 고르는 사유가 된다. 로드 마지막에는 guard 중앙값 차이의 유한성도 검사하므로 유한 입력끼리의 뺄셈 overflow를 거부한다. 현재 로더가 모든 알 수 없는 key를 거부한다고 보장하지 않는다.

근거 코드: [learn3.py](../padfec3/learn3.py)의 `DestState3.to_json`, `DestState3.from_json`, `_mapping`, `_sequence`, `check_probabilities`, `parse_arm_key`; [policy3.go](../experiments/quicbed/policy3.go)의 cache 구현. 원본 문서: [상태와 결정 규칙](V33FIX_policy.md), [Go 정책 기록](V33FIX_policy_go.md).

### Go 목적지 cache

Go cache의 바깥 문서는 `schema`와 `dests`를 갖고 schema 값은 `padfec3.cache3/11`이다. `dests`의 키는 `runClient`가 전달한 `addr` 문자열이다. 각 항목은 `state`, `min_rtt_ms`, `rtt_observations`, `min_hct_ms`, `conns`를 저장한다. TTL이나 저장 시각 필드는 없고, 만료에 따른 자동 삭제도 없다. 주소 문자열이 같으면 파일을 다시 읽은 뒤에도 같은 목적지 상태를 사용한다.

`loadDestCache3`는 빈 경로나 없는 파일에 새 빈 cache를 만들고, 이미 있는 파일의 schema가 다르면 오류로 거부한다. schema를 확인한 다음 목적지 항목을 해석하며, 모르는 키와 문서 뒤의 추가 JSON·비공백 데이터도 거부한다. 목적지 상태가 없거나 RTT/HCT 최솟값이 비유한·음수이거나 관측·연결 카운터가 음수이면 거부한다. 각 내부 상태도 `p3State.validate`를 통과해야 한다. Python의 `from_json`과 Go 해석기가 모르는 키를 처리하는 규칙은 다르다. Go는 모르는 키를 거부한다.

`policyRTT`는 유효 ACK RTT 관측이 있으면 최소 RTT를 쓰고, 없으면 성공 HCT 최솟값을 proxy로 쓴다. 두 값 모두 없으면 RTT는 0이다. `plan`과 `observePred`는 복제한 항목에서 계산하고 성공한 경우에만 원래 map에 반영한다. 파일 저장은 `<cache 경로>.tmp`에 쓴 뒤 rename한다. mutex는 한 프로세스 안의 접근을 보호하며, 여러 프로세스가 같은 cache 파일을 쓰는 사용법은 지원하지 않는다.

근거 코드: [Go cache](../experiments/quicbed/policy3.go)의 `cache3Entry`, `policyRTT`, `loadDestCache3`, `save`, `candidate`, `commit`, `plan`, `observePred`; [client 호출](../experiments/quicbed/qamp.go)의 `runClient`. 원본 문서: [Go 직렬화 기록](V33FIX_policy_go.md), [상태·입력 검증](V33FIX_policy.md).

## 11. 한계

모형의 후보 필터와 실제 wire 안전 범위는 다르다. W가 1406 B이고 k가 2 이상이면 parity 후보가 없으며, W가 1400 B이고 k가 3 이상일 때도 없다. 이것은 해당 모형 입력의 제약이다. 기본 W 1280 B인 측정 조건까지 parity가 꺼진다고 확대하지 않는다. `actions=`를 명시한 Python 분석 경로는 UDP 상한 필터를 별도로 적용하지 않는다.

J3는 IID uplink 손실, 고정 서버 datagram 크기, quic-go의 송신 전 credit 검사와 보정된 ACK/PTO 동작을 사용한다. 하향 손실·서버 재전송·명시적 바이트 가격은 J3의 독립 항이 아니다. u=0에서는 직렬화 비용도 0이므로 비용 동률 규칙 밖에서 추가 바이트를 줄일 유인이 없다. none 경로의 무손실 보호 행동 고착과 균등 prior 재주입의 한계가 남는다.

목적지별 k·S 추정과 RTT 입력은 실제 경로·서버 변경을 완전히 식별하지 못한다. Go가 보존하는 RTT는 역사적 최솟값이어서 경로 지연 증가를 따라 올리지 않는다. uplink는 사용자 입력이며 자동 대역 추정값이 아니다. 실제 first flight timer 대기와 RTT200 부근의 PTO 탐침도 모형 시간과 어긋날 수 있다.

독립 사건 세계는 정책 비용 함수와 별도의 사건 처리기이지만 packetization·parity 크기·경주 표 등의 상수는 공유한다. 세계의 기대 비용 감소를 네트워크 성능의 확인으로 바꿔 쓰지 않는다. C1의 세계 결과는 회신 비용 0 가정이며, 실제 회신 비용과 다음 연결의 idle은 별도 관측 대상이다. 현재 개발 계측에는 연결의 절대 시작·완료 시각이 없어 실제 mean_idle_ms는 미확인이다.

서버와 테스트베드 검증은 고정된 quic-go 조건을 따른다. 큰 인증서 조건의 해석에는 initial cwnd 32 packet, 토큰·session ticket 설정과 손실 방향을 함께 적는다. C1은 비표준·비인증이며 한 번의 회신이 목적지의 경로를 바꾼다. 기본 feedback off로 실행해도 이미 저장된 `c1_seen=True`를 지우지는 않는다. 다른 QUIC 구현, 인증된 C1, 자동 대역 추정과 새 학습 후보의 성능은 이 명세의 검증 범위 밖이다.

근거 코드: [decide3.py](../padfec3/decide3.py)의 `candidates3`, `explicit_candidates`; [layout.py](../padfec3/layout.py)의 `evaluate`, `outcomes`; [learn3.py](../padfec3/learn3.py)의 `predict_step`, `enter_c1`; [policy3.go](../experiments/quicbed/policy3.go)의 `policyRTT`, `observePred`; [worldparams.json](../experiments/v33/worldparams.json), [observations.py](../experiments/v33/lib/observations.py)의 idle 관측. 원본 문서: [알려진 한계](FINAL_policy_limits.md), [세계 지원 범위](worldsim.md), [C1 위협 모형](c1_threat_model.md), [T7 조건](T7_conditions_v31.md), [수집 계약](FINAL_collection.md).

## 12. 세대 변경 표

아래는 구현 규칙이 바뀐 경로다. 각 세대의 성능 판정은 해당 세대의 측정·세계 평가와 따로 확인해야 한다. 개발용 후보의 저장 상태 판본은 이 표의 활성 정책 판본 사이에 존재할 수 있다.

| 세대 | 규칙과 변경 이유 | 코드와 원본 기록 |
|---|---|---|
| gen-2 | δ와 m을 골라 padding, parity 또는 두 수단의 조합을 사용한다. 증폭 credit의 계단 모형과 first flight 복구 비용을 행동 선택에 연결했다. v2 배치의 parity 위치는 m에 따른 기존 배치다. | [gen-2 결정 함수](../padfec/policy.py)의 `decide_v2`, [배치 함수](../padfec3/layout.py)의 `legacy_lead`; 원본은 gen-2의 `PADFEC v2 명세.md`(로컬 보존), [정정과 출처](REPORT_CLAIMS_v33.md) |
| v3.0 | 행동을 (δ, lead, T)로 펼쳐 parity 위치도 선택한다. J3 비용을 손실률 격자의 posterior로 평균 내며 목적지별 HCT 사건 관측으로 학습한다. | [배치](../padfec3/layout.py)의 `send_order`, [후보 생성](../padfec3/decide3.py)의 `candidates3`; 원본은 gen3의 `g3/policy3_reference.md`(로컬 보존) |
| v3.1 | uplink가 있을 때 사전 서버 송신 41 B·(k−1)를 완료 조건에서 뺀다. 명목 2-RTT 관측의 학습 생략, 조건부 16번째 재평가와 행동별 잔차 guard를 둔다. 개발 조건에서 확인한 서버 사전 송신과 관측 혼동을 다루려는 변경이다. | [완료 조건](../padfec3/layout.py)의 `preflight_bytes`, `one_rtt_ok`; 원본은 gen31의 `g3/PROTOCOL_stage3.md` 0.5절과 `g3/GEN31_CHANGES.md`(로컬 보존), [비교 조건](T7_conditions_v31.md) |
| v3.2-dev | 우도를 생략한 관측에서도 hazard 전이를 한 번 적용한다. guard의 행동 창 통계를 평균에서 중앙값으로 바꾸고 경보 중인 성공 잔차도 공통 창에 넣는다. 입력·직렬화 검증과 오류 시 상태 보존을 보강했다. | [보존된 v3.2 학습기](../g3/v33/fixtures/S5_test_inputs_v1/policies/v32/padfec3/learn3.py)의 `predict_step`, `guard_excess`, `guard_observe`, `observe3`; 원본은 gen32의 `README.md`(로컬 보존), [상속 규칙](../README.md#v32-dev에서-물려받은-기제) |
| v3.3-dev | L1이 도착 증거를 datagram 우도로 사용하고, 쓸 수 있는 회신이 없는 연결에는 HCT 3등급 우도를 사용했다. 저장 상태 판본은 4다. | [L1 보존본](../g3/v33/policy_snapshots/L1_v1/padfec3/learn3.py)의 `arrival_likelihood`, `class_likelihood`, `observe3`; [L1 설계](L1_learning.md) |
| v3.3.1-dev | c1_seen=False는 v3.2의 이진 관측·guard·재평가 규칙을 따른다. 한 번 C1/ACK 출처를 본 목적지는 L1 관측과 record_only 결정 규칙으로 전환한다. c1 경로의 guard 벌점을 없애고 쓸 수 있는 회신이 연속되는 동안 재평가를 보류한다. 자동 parity 후보 상한은 1452 B, 상태 판본은 11이다. none 회귀와 수신 상한 차이를 다룬 변경이다. | [현재 학습기](../padfec3/learn3.py)의 `enter_c1`, `_observe_none`, `_observe_c1`; [현재 결정](../padfec3/decide3.py)의 `candidates3`, `decide3`; [정책 변경 기록](V33FIX_policy.md) |
