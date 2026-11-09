# T3 pad·dup 결과

반복40의 개발 기능 검증이다. T3는 partial이며 k-inflate와 Initial 크기 확대 검증을 이어간다. 고정 v3 FEC에 pad-junk·dup를 추가하고 첫·후속 묶음의 실제 추가 송신과 대조 parity 바이트를 기록했다. parity 계수에는 junk·dup를 넣지 않는다.

Go216개·vet·race와 Python351개·하위548개를 통과했다. 새 단위4개는42설정·3종류·378묶음의 위치·바이트·원본 보존, 수신기6사례, 기존 뒤 parity 한 개 손상, 입력 충돌을 확인한다. 잘못된 CLI 조합13개는 종료2였다.

basic·oob마다 새 비교13조건39연결이 모두 성공했다. 복호 on/off, 원본0 생략 여부, parity·pad·dup를 교차했고 뒤 parity 손상도 별도로 확인했다. dup의 원본0 생략12연결은 복호 on/off에서 모두 PTO0으로 완료됐다. padding24연결은 실제 바이트와 같은 자리 parity 대조 바이트가 일치하고 recovered0이었다. dup24연결의 첫 추가 송신은 대조 parity보다184~232 B 작았다. 이 수치는 헤더 차이이며 HCT 효과가 아니다.

기존 관측15조건45연결도 경로마다 정상42성공·의도한 전멸3실패였다. C1 사후24개가 Python과 같았다. 양쪽110묶음·300 Initial형 datagram, basic390886 B·oob390868 B가 relay와 일치했다. 정책23파일과 수신기·전수 검사 소스가 그대로이므로 앞선 두 경로 각700116사례 전수 관문을 재사용했다. 공유85파일의 선언 외 차이는0개다.

pad는 PFEC 표식을 JUNK로 바꿔 복호기에 들어가지 않는다. 감사 A5-02의 credit_parities 동일 조건은 적용하지 않는다. 그 계수는0이고, 단위 시험의 같은 입력에서는 무손실 수신·스택 바이트가 동일했다. 손실 때 parity의 복원본 대체 때문에 스택 바이트는 달라질 수 있다. 서버의 실제 증폭 송신 credit은 별도 관측 대상이다.

CLI·코드·측정 관문 실패는 없다. 검증 요약 도구 생성 때 UTF-8을 생략해 Windows cp949 읽기가 실패했고, 원본을 남기고 UTF-8을 명시한v2로 실행했다. 테스트 기준·seed·손실 일정은 바꾸지 않았다. 빌드 자료는 WSL에서 직접50파일을 보존하고42개 Go 소스를 실행 영수증과 대조했다.

X1은 같은 바이트·위치의 성능 비교와 서버 지원 범위를, 새 E20은 dup 정책 후보와 복호 지원 입력을 맡는다. J5는 burst 모형 과제이므로 후보군 확장을 맡긴다는 초안 문구를 고쳤다. 다음 T3 단계는 고정 quic-go의 AdditionalTransportParametersClient 개발용 훅을 읽고 보호된 모듈 캐시를 수정하지 않는 연결 방식을 검증한다. Initial 크기 요청1291~1472와 실제1452 상한은 따로 기록한다.

자료: T3_compare_result_v1.json, T3_compare_build_01.json, T3_compare_python_01.json, T3_compare_comparison_basic_v1/result.json, T3_compare_comparison_oob_v1/result.json, T3_compare_build_records_v1/manifest.json. 실제 연결을 병행 실행했으므로 성능 비교로 해석하지 않는다.
