# 독립 세계 시뮬레이터

`experiments/v33/worldsim.py`는 행동을 입력받아 패킷 송신, 손실, 도착, 복호, 서버 응답, ACK와 PTO 사건으로 관측을 생성한다. 정책을 선택하거나 학습하지 않고 정책 모듈도 import하지 않는다. 상수와 출처는 `experiments/v33/worldparams.json`에 둔다. 이 문서의 사건 모형은 QUIC 전체 구현이 아니다. 지원하는 규칙과 근사 범위는 아래에 적었다.

## 두 실행 모드

`World(profile="default")`는 독립 사건 모형이다. 반환 `model_kind`는 `independent_event_world`다. 손실 난수, 송신 순서, 직렬화, 복원된 바이트, 신용과 서버 송신량으로 연결 결과를 계산한다. 정책 비용식에서 hct를 뽑지 않는다.

`World(profile="policy_equivalent")`는 기존 J3와 대조하는 호환 모드다. iid 도착 패턴을 독립적으로 열거하고 기존 경주 표 및 현행 실패 비용 규칙을 적용한다. 정책 import는 없지만, 비교 대상과 같은 비용 정의를 의도적으로 사용한다. 반환 `model_kind`는 `policy_equivalent`다. 이 모드의 일치는 물리 세계 검증을 뜻하지 않는다. 일부 연결 전체 계수는 `None`이며, Initial 계수도 호환 비용에 붙인 합성값이다. 이 계수를 실측 재현에 사용하면 안 된다.

기본 세계의 무표본 PTO는 quic-go 프로파일 200ms다. 호환 모드는 기존 정책의 실측 상수 200.86ms와 ACK 비용 `1.125*RTT+1.424ms`를 유지한다. 두 값을 하나로 합치지 않는다.

## API

```python
from experiments.v33.worldsim import Action, World, WorldContext, load_params

context = WorldContext(
    k=2, w=1280, p=0.15, rtt_ms=50.0, uplink_mbps=2.0,
    cert_bytes=16000, loss_model="iid"
)
action = Action(delta=0, lead=3, trailing=1)
world = World(seed=20261030)
row = world.sample(context, action, connection=0, trace=True)
estimate = world.expectation(context, action, connections=4096)
```

이 코드는 저장소 루트를 import 경로에 둔 검증 드라이버에서 실행한다. 작업 명령은 `python -I -B`를 쓴다. 모듈 import와 World 생성은 파일을 쓰지 않는다.

`WorldContext`는 frozen dataclass다. 주요 필드는 다음과 같다.

| 필드 | 의미 |
|---|---|
| k, w | 원본 수와 패딩 전 원본 UDP 바이트. 실제 원본은 w+Action.delta다. |
| p, loss_model, burst_length | c2s 손실률, iid 또는 ge, GE의 평균 손실 버스트 길이. loss_model을 따로 지정한다. |
| rtt_ms, uplink_mbps | 지터를 넣기 전 전파 RTT(ms), 업링크 Mbps. u=0은 직렬화 제한 없음이다. |
| server_bytes | 서버 첫 비행의 실제 UDP 바이트 합을 지정할 때 사용한다. 양수이면 cert_bytes보다 우선한다. |
| server_dgram_sizes | 서버 첫 비행의 데이터그램 크기 tuple. 지정하면 server_bytes보다 우선한다. |
| cert_bytes | 명시한 서버 비행 크기가 없을 때 경험적 packetization으로 변환한다. 아래의 제한을 읽어야 한다. |
| n_need | 서버 비행 크기나 인증서를 주지 않았을 때 n_need개의 P바이트 패킷을 만드는 합성 입력. 호환 모드에서는 기존 J3의 필요 패킷 수로 직접 쓴다. |
| s2c_loss | 서버 데이터그램 손실률. ACK, Retry와 재전송에도 적용한다. |
| token, retry | 유효 토큰 보유와 Retry 요구 여부. |
| condition, c_proc_ms | 조건별 처리 지연 선택 또는 직접 지정. |
| cert_schedule | `(연결 시작 번호, 인증서 바이트)` 쌍의 tuple. |
| cert_mix | 연결마다 균등 추첨할 인증서 크기 tuple. schedule보다 뒤에 적용한다. |
| jitter_mean_ms | 연결별 지수 지터의 평균. 생략하면 설정값을 쓴다. |

`Action(delta=0, lead=0, trailing=0, order=None)`의 기본 순서는 L 반복, O 반복, P 반복이다. order에는 이 세 글자의 tuple을 넣을 수 있고 각 개수는 행동과 일치해야 한다. 호환 모드는 기본 순서만 지원한다. k와 패킷 크기는 양의 정수, 행동 개수는 음수가 아닌 정수다.

`World(params=None, profile="default", seed=0)`의 params는 부분 dict 또는 JSON 경로다. 중첩 설정을 덮어쓴다. 편의 별칭으로 lost_consumes_uplink, preserve_ge_across_connections, lead_mode, hold_margin_ms, retransmission_shape, server_mode, P, iw_packets, c_proc_ms, initial_pto_ms, jitter_mean_ms, decoder_max_datagram_bytes를 최상위에서 지정할 수 있다.

```python
world = World(params={"lost_consumes_uplink": True, "server_mode": "exact"})
params = load_params({"fec": {"lead_mode": "buffered"}})
```

현재 설정 로더는 알려지지 않은 키를 거부하지 않는다. 설정 오타를 피하려면 `load_params()`의 실제 키를 사용하고 결과의 params_sha256을 기록한다.

`sample(context, action, connection=0, trace=False, overrides=None)`은 연결 한 개의 dict를 반환한다. 원자료나 출력 파일을 자동으로 만들지 않는다. overrides는 사건 시험용이다.

```python
row = world.sample(
    context, action, connection=7, trace=True,
    overrides={
        "c2s": [True, False, True, True, True, True],
        "s2c": [True] * 64,
        "decision_delay_ms": 0.0,
        "jitter_ms": 0.0
    }
)
```

마스크의 True는 도착이다. c2s에는 최초 비행뿐 아니라 응답, ACK, 재전송도 송신 순서대로 포함한다. s2c에도 사전 ACK가 포함되므로 첫 원소가 반드시 서버 큰 비행의 첫 패킷인 것은 아니다. 마스크가 끝나면 seed 난수를 쓴다. `mask_exhaustion="error"`를 함께 주면 지정한 방향의 마스크 소진을 오류로 처리한다. 호환 모드는 overrides를 지원하지 않는다.

## 반환 관측

| 필드 | 정의 |
|---|---|
| hct, ok | 핸드셰이크 완료까지 ms와 완료 여부. 종료 한도에 걸리면 ok=false이며 hct는 설정의 max_time_ms다. |
| k_obs | 이 연결의 원본 수. 현재는 항상 입력 k를 관측할 수 있다고 가정한다. |
| srv_bytes | 실제 도착한 서버 데이터그램 바이트의 합. ACK와 중복 수신을 포함한다. 완료 뒤 이미 비행 중인 서버 패킷도 포함하는 현재 근사는 아래에 설명한다. |
| rtt | ACK 또는 첫 서버 데이터로 얻은 최소 RTT 표본. 없으면 None. |
| arrivals | 송신한 각 패킷의 flight, index, kind, arrived, usable, size, read_size와 시각. arrived는 물리 도착, usable은 수신 버퍼 절삭 없이 처리 가능한 도착이다. 복원 여부와 별개다. |
| ack_seen | 사전 ACK 수신으로 확인한 원본 인덱스. 원본이 도착했더라도 ACK가 유실되면 여기에 없다. |
| server_dgram_sizes | 서버가 실제 송신한 데이터그램의 크기 목록. ACK, Retry, 중복 재전송을 포함한다. |
| server_counted_uplink_bytes | 서버 shim이 읽은 c2s UDP 바이트. 복호기에 삼켜진 패리티도 포함하며 수신 버퍼 절삭 뒤 n으로 계수한다. |
| server_wire_received_bytes | 서버에 도착한 c2s 바이트의 절삭 전 합계. 직렬화는 이 원래 크기를 사용한다. |
| server_stack_credit_bytes | 복호기를 지나 서버 스택 신용에 더해진 바이트. 물리 수신량과 별개다. |
| client_first_flight_bytes | 최초 비행의 송신 바이트. 손실 전 기준이다. |
| client_total_uplink_bytes | 연결에서 송신한 전체 c2s 바이트. 재전송과 응답 포함, 손실 전 기준이다. |
| initial_datagrams, parity_datagrams | 연결 전체의 해당 송신 계수. initial_datagrams는 최초 비행 크기가 아니다. |
| initial_failure | 최초 비행의 도착과 수신 절삭 결과로 원본을 복원할 수 없었는지. 최종 연결 실패와 다르다. |
| server_retransmission_bytes, pto_count | 실제 사건으로 발생한 서버 재전송 바이트와 클라이언트/서버 PTO 합계. |
| true_rtt_ms, sample_rtt_ms, min_rtt_ms, server_sample_rtt_ms | 전파 RTT, 최신 클라이언트 표본, 최소 클라이언트 표본, 최신 서버 표본. |
| server_first_flight_bytes, server_first_flight_sizes | 중복과 ACK를 제외한 서버 최초 비행의 입력 packetization. |
| world_class | 내부 원인 분류 one/two/tail/failure. A0의 HCT 및 Initial 계수로 정한 관측 분류와 같은 뜻은 아니다. |
| trace, stop_reason, event_count | 요청한 사건 기록, 종료 원인과 처리 사건 수. |

arrivals의 O/L/P는 최초 및 반복 ClientHello 비행의 원본/선행/후행이다. R/Q는 첫 서버 응답 뒤 Initial ACK와 XOR 패리티, A는 이후 ACK, B/V는 큰 서버 데이터그램을 봤지만 서버 Initial이 없는 상태에서의 Initial PTO 탐침과 XOR다. 물리 도착 목록은 세계의 정답 기록이다. 실제 C1의 유실, 비인증 부채널과 피드백 누락을 모두 모사한 것은 아니다. W1 관측 어댑터는 정책에 전달할 수 있는 첫 비행 비트와 관측 가능 여부를 따로 선택해야 한다.

## 사건과 기능 스위치

worldparams의 features에서 c2s_loss, s2c_loss, uplink_serialization, amplification_limit, preflight_ack, trailing_race, second_round_loss, processing_delay, rtt_inflation, retransmissions, presample_pto, token_retry, destination_changes를 독립적으로 켜고 끈다. 선행 보류는 fec.lead_mode가 credit_only 또는 buffered를 선택한다.

GE는 bad에서 전손실, good에서 전도착인 2상태 모형이다. 정상 손실 p, 평균 버스트 L에 대해 G→B는 `p/(L*(1-p))`, B→G는 `1/L`이다. 0<p<1에서는 L>=max(1,p/(1-p))이어야 한다. p=0과 p=1은 결정적 끝점으로 처리한다. iid 경계는 L=1/(1-p)이며 L=1이 아니다. 채널은 현재 상태로 손실을 결정하고 다음 송신을 위한 상태로 전이한다. 시간 간격만 바꿔도 GE 손실 상태가 변하는 시간 페이드 모형은 지원하지 않는다.

기본은 연결별 정상분포에서 시작한다. `preserve_ge_across_connections=true`이면 같은 World에서 동일 채널 문맥을 연속 connection 번호로 실행할 때 마지막 상태를 이어받는다. 번호가 불연속이면 정상분포로 다시 시작한다. 연결 사이에 상태가 이어지는 시뮬레이션과 독립 연결 MC를 구분해서 보고해야 한다.

loss-before-rate 기본값은 `lost_consumes_uplink=false`다. 이때 손실된 패킷은 업링크 직렬화 시간을 쓰지 않는다. true로 바꾸면 같은 손실 비트여도 뒤 패킷의 도착이 늦어진다. c2s GE 전이는 두 모드 모두 송신한 데이터그램마다 한 번 발생한다.

서버 granular 모드는 보내기 직전에 `sent>=3*credit`이면 멈추고 다음 패킷의 길이를 미리 더하지 않는다. exact 모드는 다음 패킷까지 포함해서 한도를 검사한다. ACK와 재전송도 sent에 포함된다. 유효 토큰과 주소 검증 이후에는 한도를 푼다. cwnd는 기본 32개의 미확인 서버 데이터 패킷을 허용한다.

선행 credit_only 패리티는 신용을 늘리지만 복구 심볼로 쓰지 않는다. 이미 응답을 만들고 있는 서버에서 invalid lead/trailing 수신은 즉시 송신을 재개하지 않는다. 신용 증가가 amp-limited 상태를 풀면 서버 PTO는 다시 활성화한다. trailing 경주는 연결당 결정 지연을 한 번 추첨해 표현한다. 여러 trailing 패킷에 각각 독립적인 경주 승패를 주지 않는다.

buffered 모드에서는 비행별 원본/선행/후행 상태를 보관한다. 복원에 쓴 패리티를 다시 신용으로 더하지 않는다. 마지막 원본, 첫 뒤 패리티 또는 마지막 예정 슬롯+margin이 결정 계기가 된다. 다른 PTO 비행의 RS 심볼은 섞지 않는다. 이미 복호해 스택에 전달한 ClientHello 조각은 연결 전체에서 유지한다.

작은 사전 ACK는 원본 일부가 도착했지만 ClientHello가 미완성이고 u>0인 경우 생성한다. 기본 크기는 관측값 41B이며 coalescing 대기시간은 설정 가능하다. 원본 하나당 ACK 하나가 항상 실제로 생긴다는 주장은 하지 않는다.

클라이언트 미표본 PTO는 기본 200ms이며 선택 프로파일은 999ms다. 표본 뒤에는 srtt와 rttvar로 PTO를 계산한다. 첫 표본 뒤에는 3배 관계가 나온다. 서버 RTT 상태는 클라이언트와 분리하고, 서버는 자신의 패킷에 대한 ACK를 받기 전에는 미표본 PTO를 쓴다. 서버의 9/8 시간 손실 판정은 ACK된 최대 인덱스보다 작은 미확인 데이터에만 적용한다. 꼬리 패킷은 PTO 대상이다. 실제 PN 공간의 세부 제한은 아래 범위 밖 항목을 따른다.

서버 첫 데이터 인덱스 0이 Initial/ServerHello를 제공한다고 가정한다. 나중 Handshake 데이터그램만 먼저 받으면 raw srvBig 표시는 생길 수 있지만, 유효 Handshake 응답과 주소 검증은 첫 데이터를 받을 때까지 기다린다. 이때 클라이언트 PTO는 Initial 탐침을 보내고 원본 우선의 후속 XOR를 사용한다.

Retry는 첫 c2s 패킷 도착에서 응답한다. ClientHello 복구 완료까지 기다리지 않는다. Retry가 유실되면 다음 클라이언트 비행의 첫 도착에서 다시 응답한다. 토큰 없는 이전 비행의 잔여 패킷은 새 Retry 비행에 섞지 않는다. 새 비행 원본이 서버에 도착하면 주소 검증을 적용한다.

처리 상수는 마지막 필수 서버 데이터 수신부터 Dial 완료까지의 고정 지연으로 적용한다. trailing 경주의 신용 결정 창을 이 상수만큼 넓히지 않는다. 이 지연을 TLS의 특정 함수 처리시간으로 실측했다고 해석하면 안 된다. 현재 구현에서는 위치를 분리하기 위한 근사다.

## 기대값, 난수와 검증

`exact_expectation(context, action)`은 호환 모드에서만 사용할 수 있다. 반환은 mean_hct_ms, variance_hct_ms, p_one_rtt, p_two_rtt, p_fail, probability_sum과 설정 해시다. 패턴 표를 context/action별로 캐시한다. 기본 세계에 이 함수를 호출하면 예외가 발생한다.

`expectation(context, action, connections=4096, seed=None, use_cache=True)`은 기본 세계에서 결정적인 seed 목록의 MC를 실행하고 평균, 표본분산, 표준오차, n, 실패/등급 비율을 돌려준다. 결과에는 approximate=true가 붙는다. 같은 문맥, 행동, 표본 수, seed 결과는 캐시한다. n=1의 표준오차 0은 정밀도 증명이 아니다. 연결 간 GE 상태 유지 모드의 stderr는 독립 가정식이므로 `stderr_assumes_independent_connections=false`를 확인해야 한다. 그 모드의 구간 추정은 독립 시드별 배치나 자기상관을 고려한 별도 검증이 필요하다.

4096연결 MC를 0.1ms 수준 정책 판정의 정확한 oracle로 쓰면 안 된다. W1에서 작은 차이를 판단할 때 표본오차를 보고 독립적인 더 큰 평가 표본이나 짝비교를 사용해야 한다. 후보를 많이 비교하면 같은 유한 MC의 최소값을 고르는 선택 편향도 생길 수 있다.

환경, c2s, s2c, 호환 샘플의 RNG를 seed와 connection으로 분리한다. 정책의 패킷 수가 달라도 다음 연결의 인증서와 지터 추첨이 밀리지 않는다. 같은 연결 안에서 패킷 개수가 달라지면 후속 패킷의 난수 위치도 달라진다. 연결 간 GE 유지 모드에서는 이 차이가 다음 상태에 영향을 주며, 그것을 지우기 위해 패킷 비트열을 강제로 맞추지 않는다.

손실 검산용 독립 API는 ge_parameters, pattern_probability, sample_loss_pattern, first_flight_outcome이다. pattern의 True는 도착이며 first_flight_outcome은 기본 L/O/P 순서의 순수 블록 복구만 판정한다. 이 함수에는 타이머, 신용, deadline이 포함되지 않는다. 결과에 timing_included=false가 붙는다.

정책 동치의 사전 기준은 행동별 100,000연결의 평균 3표준오차와 exact enumeration 비교다. 기본 세계의 실측 보정 기준은 `g3/v33/world_validation_protocol.json`에 사전 고정했다. 결과는 루프 작업 폴더의 `runs/W0_calibration.md`와 별도 검증 산출물에 기록한다. 대규모 검증 결과는 g3/v33/validation/W0/W0_calibration.md에 있다. 호환 30조건과 손실 검산은 통과했으며, 기본 세계의 15% 자동 행동 셀은 두 등급 비율이 사전 기준 밖이다.

## 지원 범위와 남은 근사

- TLS 암호문, QUIC 프레임 파싱, 실제 CRC와 RS 계산을 하지 않는다. 동일 비행에서 도착한 독립 패리티 수로 복원 가능 여부를 판단한다. 비행 간 심볼 혼합은 금지한다.
- packetization 입력을 직접 주는 것이 가장 명확하다. cert_bytes만 주면 s0=1472B(k>=2) 또는 382.45B(k=1), 패킷당 41.983B의 기존 경험적 계수로 서버 비행을 구성한다. 이는 실제 QUIC 패킷 생성기의 대체식이다. 관측 srv_bytes에 든 ACK·중복을 이 입력과 혼동하면 안 된다.
- 서버의 Initial/Handshake PN 공간 전체를 구현하지 않는다. 첫 패킷의 키 선행조건과 ACK 범위 제한을 근사하며, 하나의 데이터 인덱스를 PN 대신 쓴다. 다른 스택의 패킷화나 혼합 encryption-level 손실은 별도 trace 검증이 필요하다.
- 초회 실패 뒤 전체 [L,O,T]를 다시 보내는 경로는 카드의 비행 모형이다. 실제 quic-go PTO의 PING, CRYPTO 재배치, 일반 탐침 2개와 bytes-in-flight=0 특수 탐침 1개를 모든 k에서 정확히 재현하지 않는다. 큰 서버 패킷 수신 뒤의 초기 탐침은 기본 두 개로 모델링한다. RTT200 Initial5가 나온 것만으로 모든 실측 행의 원인을 확정할 수 없다.
- cwnd는 미확인 데이터그램 개수 제한이다. 완전한 혼잡 제어, cwnd 증가/감소, GSO, ECN, 큐 공유, OS 스케줄링을 구현하지 않는다. ACK coalescing도 설정한 고정 창의 근사다.
- 원본이 1452B를 넘으면 quic-go Initial 크기 clamp와 재분할을 구현하지 않았으므로 unsupported 예외를 낸다. 패리티는 기본 wire 한도 1472B까지 허용한다. 1452B를 넘으면 wire 송신량과 직렬화는 원래 크기를 쓰고, shim 수신량과 스택 신용은 1452B다. 잘린 패리티는 복구 심볼로 쓰지 않는다. 이는 qamp의 parseFecBlock 실패 뒤 raw Initial을 스택에 넘기는 경로를 모델링한 것이며, QUIC AEAD 복호는 성공하지 않는다. wire 한도보다 큰 패킷의 IP 단편화나 EMSGSIZE는 지원하지 않는다. J7이 형식을 바꾸면 v3.1 설정과 새 형식 설정을 구분해야 한다.
- 완료 후 이미 송신된 c2s 패킷은 끝까지 도착시켜 서버 물리 수신량에 포함한다. srv_bytes도 이미 비행 중인 서버 데이터그램을 전부 포함한다. 실제 qamp는 Dial 뒤 parity 지연의 3배와 선택적 C1 대기 뒤 수신량을 스냅숏으로 잡고 연결을 닫으므로 경계가 다르다. 특히 RTT200/s2c 재전송의 srv_bytes는 이 차이를 별도로 검토해야 한다. 현재 hct 이후에 새 PTO를 시작하지는 않는다.
- 실제 MinRTT는 ACK 범위, 재전송 모호성과 ConnectionStats 유효성에 영향을 받는다. 세계는 사전 ACK 또는 사용 가능한 서버 Initial을 받은 시점에 시간 표본을 연결한 근사다. Initial 없이 Handshake 데이터만 받으면 표본을 만들지 않는다. 서버 재전송은 같은 데이터 인덱스의 최신 송신 시각으로 ACK RTT를 계산하므로 실제 PN별 재전송 모호성과 차이가 있다. `path_rtt_source=unavailable`의 실측 빈도를 그대로 재현한다고 주장하지 않는다.
- C1 피드백 패킷의 유실과 대기, Retry 토큰의 암호 검증, 토큰 만료와 서버 지원 신호는 지원하지 않는다. arrivals는 정책 관측 어댑터를 시험할 수 있는 참값이며 실제 피드백 성공 보장은 아니다.
- 시간 제한이나 사건 수 제한은 무한 재전송을 막는 모델 경계다. 종료 실패를 표본에서 빼면 안 된다. 평균과 실패율에 포함하고 stop_reason을 보고한다.

문헌 원식이 확인되지 않은 GE 검산은 두 독립 방법의 자체 검산으로 표기한다. 근거 검색 범위와 적용한 감사 정정은 루프 작업 폴더의 `runs/W0_review_design.md`, transport 코드 근거는 `runs/W0_transport_review.md`에 있다. v3.1 저널에 맞지 않는 결과와 지원 범위 밖 조건은 숨기지 않고 세계 모형의 한계로 기록한다.
