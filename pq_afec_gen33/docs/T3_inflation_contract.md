# T3 ClientHello와 Initial 확대 계약

k-inflate는 추가 transport parameter의 값 길이(B)다. 기본0은 추가하지 않는다. 범위0~8192 B, 양수는 client의 고정 fec off·buf에서만 허용한다. adaptive 정책과 parity 추가를 함께 바꾸지 않는다. 이 값은 k 자체가 아니며 실제 첫 묶음 k·Initial 패킷 수·CRYPTO 범위를 별도로 검증한다.

quic-go v0.61.0의 internal/wire.AdditionalTransportParametersClient 개발 훅을 작은 로컬 모듈 padfec-local-hook에서 연결한다. 모듈 경로는 Go internal 접근 규칙을 충족하는 github.com/quic-go/quic-go/padfec-local-hook이며 외부 배포물이 아니다. go.mod의 로컬 replace만 사용하고 빌드 stage에 소스·모듈 파일을 복사한다. 캐시 안 quic-go 소스는 수정하지 않고 다운로드도 하지 않는다. srcsha와 검증 영수증에 하위 모듈 소스를 포함한다.

추가 parameter 번호는9730(27+31*313)이다. 고정 quic-go의 기본 GREASE 번호27+31*byte는 최대7932이므로 충돌하지 않는다. 값은0 바이트 반복이며 길이8192까지 허용한다. 이 번호의 wire ID는2 B이고 값 길이 varint는1~2 B다. 설정은 QUIC 연결을 만들기 전에 한 번 고정한다. 같은 값 재호출만 허용하며 값 변경·기존 훅 충돌은 거부한다. 런타임에 수정하거나 연결마다 바꾸지 않는다. ClientHello padding 행에는 값 길이·번호·추가 wire 길이·출처를 기록한다.

ips는 uint16 입력 범위0~65535만 받는다.0은1280,1~1199는1200,1453 이상은1452로 적용되는 고정 quic-go 동작을 ips_eff에 정확히 기록한다. ips_used는 요청값을 보존한다. 명시1291·1341·1350·1452·1472의 실제 첫 Initial 길이를 대조하며1472가 그대로 전송됐다고 쓰지 않는다. MTU Discovery는 계속 끈다.

검증은 훅의 직렬화·서버에 추가하지 않음·길이 경계·초기화 동결과 기존 관문, 확대·기본 팔 실제 연결의 AES-GCM 인증된 Initial 복호·ClientHello TP 길이·CRYPTO 범위 대조다. CRYPTO의 겹침은 내용 일치로 확인하고 qlog 관측과 맞춘다. 요청 padding이0인 팔에는9730이 없어야 한다. 실제 k는 타이머 분할과 구분한다. 기본300us를 유지한다. HCT·증폭 credit·MTC 효과는 이 기능 검사로 판정하지 않는다.
