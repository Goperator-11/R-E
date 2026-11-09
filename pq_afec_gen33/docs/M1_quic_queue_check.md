# M1의 실제 QUIC 처리 순서 검증

`qamp_hold_quic_test.go`는 로컬 UDP 소켓과 고정 quic-go v0.61.0으로 실제 TLS 연결을 만든다. 클라이언트 first flight는 X25519MLKEM768, Initial 1280 B, 원본 2개, 선행 RS parity 3개다. 서버 인증서 입력은 16000 B이고 보류 설정은 D20 기본값이다. 이 시험의 실행 시간은 HCT 성능 자료로 쓰지 않는다.

수신기는 미사용 parity를 복원 원본보다 앞에 반환한다. quic-go `connection.go`의 `handleOnePacket`은 `sentPacketHandler.ReceivedBytes`를 호출한 뒤 payload 복호와 `PacketDropped` 기록을 처리한다. 따라서 해당 연결의 payload 복호 실패 기록이 첫 송신 CRYPTO보다 먼저 나온 사실은 그 parity의 수신 바이트가 먼저 계상됐다는 근거다. 시험은 1200 B 이상의 payload 복호 실패 개수와 바이트를 첫 송신 CRYPTO 시점에 고정한다. 수신 CRYPTO와 ACK 전용 송신은 완료 신호로 쓰지 않는다.

## 두 입력 범위

first flight 분리 시험은 무손실, 첫 원본 소거, 마지막 원본 소거를 검사한다. 두 Initial을 생성한 뒤 첫 서버 CRYPTO가 관측되기 전의 추가 클라이언트 Initial은 시험용 PacketConn이 억제한다. 이 조작은 first flight의 타이머 복구를 실제 QUIC 스택에서 검사하려는 통제다. 실제 전송 코드나 성능 계획에는 적용하지 않으며 억제 개수를 로그에 남긴다. 기대하는 미사용 parity는 각각 3개, 2개, 2개다. 소거 조건은 실제 RS 원본 복원도 요구한다.

재전송을 허용한 시험은 같은 최초 원본 소거를 사용하고 추가 Initial을 억제하지 않는다. handshake 완료와 물리 수신량 이내의 스택·pending 회계를 검사한다. 미사용 parity가 항상 첫 CRYPTO보다 앞선다고 요구하거나 주장하지 않는다.

## 실패가 밝힌 범위

최초 `M1_build_07`의 마지막 원본 소거 조건은 첫 CRYPTO 앞의 parity 0개로 실패했다. 이 실패는 보존한다. `M1_build_10`의 재전송 허용 로그에서도 원본 0 수신, 서버 ACK, 새 Initial의 CRYPTO 꼬리 수신, 서버 첫 CRYPTO, parity 복호 실패 순서를 확인했다. 이 경로의 첫 송신 전 parity는 0개, FEC 복원도 0개였다. 재전송이 보류 기한보다 빨리 CH를 완성한 것이다. 원래의 무조건적인 첫 송신 credit 명제는 통과한 것으로 바꾸지 않는다.

`M1_build_08`과 `M1_build_09`의 진단 버전에는 CRYPTO 검사 분기가 수신 사건 아래로 이동한 계측 오류가 있었다. 그 두 로그의 prefix 계수는 송신 credit 근거로 쓰지 않는다. 잘못된 소스와 로그를 보존했고, 송신 CRYPTO만 완료로 세는 별도 시험을 추가한 `M1_build_10`으로 다시 검사했다.

`M1_build_10`에서 first flight 분리 조건은 parity 3·2·2개, 복원 0·1·1개였다. 마지막 원본 소거에서는 추가 Initial 6개를 억제했다. 재전송 허용 조건의 3·2·0개와 구분한다. 전체 122개 Go 시험, vet, race와 빌드가 통과했다. 수신기 전수 대조 700116개는 별도 단계의 결과다.

보류 묶음의 FIFO와 실제 QUIC의 바이트 처리 순서는 확인했지만, 재전송을 포함한 모든 연결에서 같은 credit 효과를 보장하지는 않는다. 동결 M1 사건 세계는 ACK 이후 quic-go의 실제 RTT·PTO 갱신과 CID 전환을 전부 재현하지 않는다. 세계 기대 비용, model-world J와 실제 개발 측정은 계속 구분한다. 활성 정책 채택과 Go 비용 모형 거울은 별도 관문으로 남아 있다.

## 기준 경로의 처리 순서

사전에 쓴 `M1_quic_reference_path_plan.md`에 따라 양방향25 ms 전파 지연과 상향2000 kbps 직렬화를 시험용 FIFO 큐에 적용했다. `M1_build_11`은 전체123개 Go 시험, vet, race와 빌드를 통과했다. 같은 stage의 기준 경로 시험을25회 반복한75개 연결도 통과했다. 무손실·첫 원본 소거·마지막 원본 소거의 첫 송신 CRYPTO 전 미사용 parity는 각각3·2·2개, 복원 원본은0·1·1개였다. 모든 연결에서 추가 Initial 억제는0개였다.

`runs/M1_quic_reference_path_v1.json`은 로그에서 소거 조건별25개 결과를 다시 읽어 기대 개수와 대조한 기록이다. 무손실의 미사용 parity 합은3978~4014 B, 각 단일 소거에서는2652~2676 B였다. 연결별 CID 길이에 따라 실제 parity 크기가 달라지므로 하나의 고정 바이트 값으로 바꾸지 않는다.

이 시험은 애플리케이션 큐와 호스트 스케줄러를 쓴다. 선택한 원본은 `fecConn`이 큐에 넣기 전에 소거하므로 소거된 바이트의 링크 직렬화 시간은 차지하지 않는다. 따라서 netem의 손실 위치나 독립 사건 세계의 전체 직렬화와 같다고 해석하지 않는다. 고정한 first flight 소거에서 처리 순서가 성립한 결과이며 무작위 손실의 HCT 분포나 모든 재전송 경로의 보장은 아니다. 지연 없는 재전송 허용 경로에서 관찰한 기존 실패는 그대로 남긴다.
