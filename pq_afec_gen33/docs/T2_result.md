# T2 토큰·TLS 재개 구현 검증

고정 클라이언트의 token-store·resume와 서버 verify-source·resume를 구현했다. 기본값은 모두 off다. 클라이언트 LRU는 시행 루프 밖에서 공유하고, 실제 토큰 수신·조회 적중·TLS DidResume를 구분해 기록한다. 서버는 ClientInfo.AddrVerified와 Accept 후 TLS DidResume를 연결별·누적으로 남긴다. 코드와 입력 계약은 docs/T2_revisit_contract.md에 있다.

HCT를 고정한 뒤 기본 200 ms·HCT·유효 최근 RTT의 최댓값만큼 연결을 열어 둔다. 수집 대기 90건 모두 목표 시간을 채웠다. 토큰·티켓을 쓰지 않는 기존 팔에는 새 대기가 없다. C1 대기는 기존 필드로 따로 기록한다. 0-RTT는 계속 끈다.

| 기능 관문 | 결과 |
|---|---|
| Go | 225개, vet·race 통과. 새 시험 5개 |
| Python | 351개, 하위 548개 통과 |
| 새 연결 | basic·oob 각각 54개, 전체 108개 성공 |
| 첫 연결 분리 | 36개. 첫 Initial 토큰 없음·TLS 재개 없음 |
| 토큰 | cache 적중 48개 중 같은 IP40개는 검증 통과. IP 변경 8개는 토큰 무효 처리 |
| TLS | 클라이언트와 서버 DidResume32개 일치. 서버 티켓 off에서는 재개 0 |
| Retry | 수신 26개. 강제 검증과 토큰 유효성에 따른 예상값 일치 |
| 복구 | 토큰을 쓰며 원본 0을 생략한 12연결에서 원본 12개 복구 |
| 기존 관측 | 각 45연결 중 정상 42개 성공, 의도한 전멸 3개 실패. C1 사후 24개 Python과 정확히 일치 |
| 수신 전수 | basic·oob 각각 60설정·700116사례. Python 바이트·회계와 일치 |
| CLI | 잘못된 7조합 모두 종료 2 |
| 출처 | 정책 23파일 불변. 공유 85파일 선언 외 차이 0. WSL57파일·Go48소스 실행 해시와 일치 |

기존 관측의 송신 묶음 기록도 relay와 일치한다. basic은 110묶음·300 Initial·390600 B, oob는 111묶음·301 Initial·392023 B다. 기존 비교 팔·inflation·FEC 송신 함수와 개발 훅은 이전 커밋과 같다. 새 서버 메타데이터 배선을 포함해 수신 전수 관문을 다시 통과했다.

IP 변경 음성 대조는 같은 relay 목적지를 유지하면서 서버가 보는 source IP를 127.0.0.1,127.0.0.2,127.0.0.1로 바꿨다. 클라이언트가 토큰을 꺼내 보냈다는 사실만으로 주소 검증을 가정하지 않는다. 강제 검증 서버에서는 무효 토큰 뒤 Retry를 거쳤고, 강제 검증이 없으면 해당 연결의 AddrVerified는 false였다. 같은 연결에서 TLS 재개는 유지됐다.

basic 음성 시험의 첫 실행은 서버 준비 로그를 읽다가 OSError61(No data available)로 중단됐다. 파일시스템 오류의 원인은 미확인이다. T2_revisit_negative_basic_v1과 실패 영수증을 남겼고, 소스·조건을 바꾸지 않은 v2 출력 폴더에서 12연결을 통과했다. 실패를 성공 표본에 합산하지 않는다.

이 결과는 기능 검증이다. 같은 IP의 토큰 팔은 유효성 상한 비교이고, loopback IP 변경은 무효화 대조다. 실제 재방문 비율·1-RTT 완료 비율·HCT 우위·첫 응답 pacing 꼬리 효과는 미확인이다. X4에서 같은 블록·서버 바이트·수집 대기 조건을 고정해 측정해야 한다. T7 의존을 우회하지 않는다. auto·auto3 토큰 입력은 E21의 정책 검증 전까지 거부한다. A7 검증자가 확인하지 못한 다른 QUIC 스택의 NEW_TOKEN 미지원 주장은 채택하지 않았다.

재현 자료는 runs/T2_result_v2.json, t2_verify_v3.py, T2_build_01.json, T2_udp_wire_01.json과 각 smoke plan·명령·stdout·서버통계·relay다. 고정 quic-go 관련 원문 7파일은 T2_upstream_source_v1에 해시와 함께 보존했다. 원본 모듈은 수정하지 않았다.

커밋 전 파일 대조는 revisit_smoke.py의 마지막 CRLF1개가 Git의 LF 규칙으로 바뀌어 첫 보존 단계에서 중단됐다. 실행한 원본은 T2_revisit_smoke_before_lf.py에 보존했고, AST와 정규화 후 index 바이트가 같음을 T2_lf_normalization_v1.json에 기록했다. 기능 실행 자료의 원래 소스 해시는 유지한다. 재검증 도구의 첫 재실행은 기존 drift 출력 파일을 다시 만들려다 중단됐고, 새 출력 경로를 쓴v3가 통과했다. 원본 보존 묶음은 유지하고 후속 기록을 추가했다.
