# T1 고정 인증서 계약

gen33 qamp의 합성 인증서는 ECDSA P-256을 유지한다. 고정 개발용 seed로 키를 만들고 인증서 자체는 RFC 6979로 서명한다. 날짜·일련번호·subject·SAN·채움값을 고정하고 filler 길이를 조정해 DER 길이가 certsize와 정확히 같을 때만 쓴다. 범위는 512~1048576 B이며, 정확한 길이를 만들 수 없으면 실패한다. 고정 seed와 파일 안 키는 공개 가능한 시험 재료다. 실제 서비스 자격 증명으로 쓰지 않는다.

`-mode certgen -certsize N -cert-file PATH`는 인증서와 PKCS#8 키가 든 한 PEM 파일을 새로 만든다. 같은 판본·크기에서는 파일 바이트도 같다. 기존 파일은 덮지 않는다. `-dry-run`은 파일을 쓰지 않고 예상 DER·파일 SHA와 크기를 출력한다. 서버의 `-cert-file`은 같은 파일을 읽고 크기·키·서명·단일 인증서를 검사한다. 파일이 없거나 잘못됐을 때 새 인증서로 조용히 대체하지 않는다.

인증서 파일이 없는 기존 호출은 같은 결정적 생성기를 메모리에서 사용한다. T7의 실제 비교 계획은 명시 파일을 생성해 모든 gen33 서버 팔에 전달하고 DER 크기와 SHA를 대조해야 한다. 읽은 파일 SHA와 DER SHA는 시작 로그의 CERT_META와 서버 stats의 certificate에 들어간다. 동결 gen2·v31 바이너리는 새 플래그를 지원한다고 가정하지 않는다. 그 서버를 써야 할 때는 T7에서 공통 서버 또는 명시된 한계를 택한다.

TLS handshake에는 원래 ECDSA 키를 전달한다. CertificateVerify는 계속 연결별 무작위 서명이다. 인증서 공유는 팔에 고정된 인증서 길이 차이를 없애지만, 모든 서버 first flight의 길이나 시간까지 같게 만들지는 않는다. Ed25519로 바꾸지 않는 선택은 D22다.

Go 1.26.6 로컬 `crypto/ecdsa`·`crypto/x509` 소스와 [Go ECDSA 문서](https://pkg.go.dev/crypto/ecdsa)를 확인했다. GenerateKey와 SignASN1에 고정 Reader를 전달하는 방식은 사용하지 않는다. 인증서 생성에만 Sign(nil, digest, opts)를 호출하는 signer를 두며 새 암호 산술을 구현하지 않는다.

검증은 사용 크기 목록의 정확 길이·반복 생성 동치, PEM 왕복·파일 재사용·잘못된 파일 거부, Go vet·test·race, 동일 파일의 여러 실제 QUIC 서버 handshake를 포함한다. smoke의 시간은 성능값으로 보고하지 않는다. 인증서 크기 비교에서 확인된 효과만 적고 기존 봉인 결과의 유불리를 추정하지 않는다.
