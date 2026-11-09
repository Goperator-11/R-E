# T6 후속 Initial 모양 검증

2026-11-02 정정: 아래 결과는 `original_first`가 qamp 기본값이던 2026-11-01 상태의 기록이다. 지금 qamp `-retrans-layout` 기본값은 다시 `repeat_first`이고 `original_first`는 `-retrans-layout original_first`로 명시할 때만 쓴다(루프 결정 D43이 D28을 대체). 표의 두 행은 규칙별 와이어 모양 기록으로 그대로 읽고, 본문의 "새 기본값"은 그때의 기본값으로 읽는다. 근거는 `docs/V33FIX_testbed.md`(F4 절과 통합 정리 절)와 `C:\dev\codex_handoff\v33\state\DECISIONS_NEEDED.md`의 D43이다.

v3 FEC의 응답 전 후속 묶음은 기본 original_first에서 원본 우선·뒤 XOR1개를 쓴다. 첫 묶음, v2, 서버 큰 응답 뒤의 원본 즉시 송신은 유지한다. repeat_first 옵션은 기존 v3 후속 (L,O,T)를 재현한다. first action의 T=0이라도 새 기본값의 응답 전 후속 묶음에는 T'=1을 쓴다. off·buf에는 parity를 추가하지 않는다.

행의 retrans_layout은 적용 규칙, bytes_parity는 연결 전체의 성공한 parity 바이트다. flight_trace의 shape에는 묶음 시작 시점의 phase·rule·lead·trail·원본 즉시 송신 여부·qlog PTO 계수 하한이 들어간다. 묶음별 성공한 parity 수·바이트도 기록한다. pre_response_followup는 타이머 묶음의 위치를 뜻하며 모든 경우에 PTO 재전송이라는 뜻은 아니다.

Go212개·vet·race와 Python351개·하위548개가 통과했다. 새 단위5개는42설정·168묶음,84개 단일 원본 소거 복구, 묶음 도중 srvBig 변화, flightID 순환, 비활성·v2·입력 옵션을 검사했다. 기존 v2 golden은 그대로 통과했다. 이전 v3 전체 모양 시험은 repeat_first를 명시해 유지했다. 실제 CLI의 잘못된 값2개는 종료2로 거부됐다.

basic·oob 각15조건·45연결에서 정상42연결이 성공하고 의도한 c2s 전멸3연결이 실패했다. 두 경로 모두 기록의 묶음별 parity 헤더·수·바이트가 relay와 일치했고 C1 사후 평균24개는 Python과 정확히 같았다.

| 경로 | 연결 | 묶음 기록 | Initial형 송신 수 | 송신 B | 생략 기록 |
|---|---:|---:|---:|---:|---:|
| basic | 45 | 111 | 301 | 392167 | 0 |
| oob | 45 | 110 | 300 | 390806 | 0 |

RTT200의 두 고정 팔은 각각6연결에서 원본 Initial5개와 묶음 크기2·2·1을 유지했다. 첫 행동은 m4·lead3이다.

| 규칙 | 연결당 parity 수 | 응답 전 후속 parity 수 | 연결 전체 parity B 범위 | 유효 RTT 표본 |
|---|---:|---:|---:|---:|
| original_first | 6 | 1 | 7961~7991 | 0/6 |
| repeat_first | 9 | 4 | 11940~12020 | 0/6 |

12연결 모두 PTO 사건 뒤 보낸 Initial 패킷2·3의 CRYPTO 구간이 첫 패킷0·1과 같았다(T6_probe_path_v1.json). 새 규칙의 후속 parity는 m1·lead0, 이전 규칙은 m4·lead3으로 실제 헤더에서도 확인됐다. 일부 repeat_first 행은 qlog PTO 계수가2였지만 Initial 묶음은 여전히3개였다. PTO 계수와 Initial 재전송 횟수를 같은 값으로 쓰지 않는다.

A3-01의 연결 전체 later_parity_sent≤1은 새 규칙에서도 맞지 않는다. 이번 고정 팔은 응답 전1개와 응답 뒤1개, 합2개를 보냈다. T6은 묶음별 T'≤1을 구현하며 연결 합계를 따로 기록한다. RTT 표본은 두 팔 모두0/6이었다. 모양 변경으로 RTT 유효99%가 회복됐다고 쓰지 않는다. HCT 분포·Finished 출발 지연은 미확인이며 병행한 기능 smoke를 성능 비교로 쓰지 않는다.

정책23파일과 qamp 수신 앞부분·서버 영역, hold·decoder_index·UDP·observation·boundary·수신 전수 시험 코드는 불변이다. 두 경로 각각700116사례 관문을 재사용했고 공유85파일의 선언외 차이는0건이다. 비용 모형은 재전송 보호를 명시하지 않은 이전 실패 근사다. J3·J4에서 이 계약의 L'=0·T'=1, 첫 실패와 두 번째 실패·탐침 credit·전체 바이트를 함께 반영해야 한다. E15의 ACK·CID·큐 경로와 연결 전체 parity 묶음 상한 E19는 별도 후속이다.

검증 실패는 없었다. 보존 도구의 UNC 경로 열거가0파일을 반환해 예상40개와 달라 중단됐다. WSL 한 호출 안에서 같은 stage의40개 Go 소스를 실행 해시와 대조하고 전체48파일을 Windows runs로 복사했다. 누락 목록을 허용하지 않는 방식으로 바꿨으며 첫 도구와 빈 출력 폴더는 남겼다. 자료는 g3/v33/validation/T6_v1에 보존한다.
