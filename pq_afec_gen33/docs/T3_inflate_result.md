# T3 ClientHello·Initial 확대 결과

반복41의 개발 기능 검증으로 T3 구현 범위를 완료했다. 반복40의 pad·dup에 이어 k-inflate를 추가하고 ips_used 요청값과 ips_eff 실제 기본·상한을 구분했다. k-inflate는 고정 off·buf에서0~8192 B를 받으며 TP9730의 값으로 넣는다. 값0은 추가하지 않는다.

고정 quic-go v0.61.0의 개발용 훅을 로컬 모듈로 연결했다. 모듈 캐시를 고치거나 내려받지 않았다. 빌더가 하위 모듈을 stage에 복사하고 vet·test·race 및 srcsha 대상에 포함한다. j7_command_v2.py도 하위 Go·go.mod를 해시에 포함한다. 개발 훅은 QUIC 연결 전 한 번 설정하고 다른 값 재설정을 거부한다.

Go220개·vet·race, Python351개·하위548개를 통과했다. 새 단위4개가 TP 길이·경계·서버 미적용·초기화 고정·입력 충돌·Initial 크기 정규화를 검사했다. 잘못된 CLI8조합은 종료2였다.

basic·oob마다 확대19조건57연결이 모두 성공했다. 전체114연결의 Initial426패킷을 AES-GCM 인증 복호하고 ClientHello를 재조립했다. TP9730의 존재·값 길이·0 바이트, qlog의 PN·CRYPTO 구간, 첫 묶음 k를 직접 대조했다. 태그 또는 키를 바꾼228사례는 모두 InvalidTag로 거부됐다. 복호 도구는 WSL Python3.14.4·cryptography46.0.5를 사용했다.

| 키 교환 | 추가 TP 값(B) | 실제 첫 묶음 k |
|---|---|---|
| X25519MLKEM768 |0·1280·2560·8192|2·3·4·8|
| X25519 |0·1280·2560·8192|1·2·3·7|

위 표의 각 입력은 두 경로 합6연결이다. ML-KEM의1·63·64 B 입력도 각각6연결에서 k2였다. 추가 TP 자체의 encoded_bytes는 값 길이와 ID·길이 varint를 합친다. 연결마다 기본 GREASE 길이가 달라 전체 ClientHello 길이 차이를 추가 바이트와 같다고 가정하지 않았다.

ML-KEM Initial 요청1291·1341·1350·1452 B는 실제 요청 길이로,1472 B는1452 B로 전송됐다. 모든 해당 연결은 k2였다. 요청0의 ips_eff는1280이다. 경계1~1199는1200,1453~65535는1452라는 고정 라이브러리 규칙을 단위 시험으로 확인했으며 음수·65536은 거부한다. 실제1472 B 송신은 구현하지 않았다.

기존 관측은 경로마다45연결 중 정상42성공·의도한 전멸3실패, C1 사후24개 Python 동치를 유지했다. pad·dup 비교도 경로마다39연결 전부 성공했다. 이번 전체 기능 실행은282연결이고 의도한 전멸6개 외에는 성공했다. 병행 실행이므로 HCT 효과를 판단하지 않는다.

정책23파일과 수신기 기능·전수 검사 소스는 변하지 않았다. qamp 앞부분의 새 훅 import1줄을 제외한 함수와 서버 영역을 바이트 대조해 이전 두 경로 각700116사례를 재사용했다. 공유85파일의 선언 외 차이는0개다. 빌드 자료55파일·Go46소스를 실행 영수증과 대조했다. quic-go의 원본 TP 소스 해시는 훅 탐색 전과 같다.

Windows에서 CLI 검사를 시작한 첫 WSL 호출이15초 안에 반환하지 않아 준비 도구가 종료됐다. 원인은 미확인이다. 실행 인수·실패 기록을 남기고 한 WSL 호출 안에서8조합을 모두 실행해 종료2를 확인했다. 소스·시험 기준·seed·손실 일정은 바꾸지 않았다. 기능 관문은 모두 통과했다.

T3_coverage.md의4항목을 구현 범위에서 처리했다. X1은 성능·같은 바이트·서버 지원 범위, A1은 MTC 관련 문헌 검토, E20은 dup 정책 후보와 복호 지원 입력을 맡는다. MTC 크기·HCT 효과·1472 B 와이어·다른 스택 지원을 확인한 것으로 쓰지 않는다. 다음은 T2다. T7과 X1은 G1/G2 의존 때문에 아직 실행하지 않는다.

자료: T3_inflate_result_v1.json, T3_inflate_build_01.json, T3_inflate_python_01.json, T3_inflate_inflation_basic_v1/result.json, T3_inflate_inflation_oob_v1/result.json, T3_inflate_auth_negative_v1.json, T3_inflate_build_records_v1/manifest.json.
