# A8: quic-go v0.61.0 소스와 Go 1.26.6 crypto/tls에서 PAD-FEC 모형·알고리즘이 기대거나 활용할 수 있는 사실

WSL Ubuntu의 quic-go 모듈(/home/scien/go/pkg/mod/github.com/quic-go/quic-go@v0.61.0, 아래 'quic-go/'), Go 표준 라이브러리(/home/scien/goroot/src, 아래 'goroot/'), C:/dev/pq_afec_gen32의 qamp.go·padfec3를 대조했고, sealed p31 저널(C:/dev/pq_afec_gen31/experiments/state/p31_run*_units.jsonl, 124,800행)을 재집계했다. PAD-FEC가 기대는 회계 규칙(연결 큐에서 꺼낼 때 데이터그램 단위로 계상, 데이터그램마다 보는 불리언 3배 검사, Handshake 패킷 1개로 검증 완료)은 소스 그대로이고, layout.py의 1-RTT 판정식과 A_pre = 41(k-1)도 실측 server_bytes와 맞았다(2 Mbps에서 +41~42 B, 무제한에서 0). 가장 큰 약점은 두 가지다. 첫째, quic-go 서버는 NEW_TOKEN을 무조건 발급하고 유효한 토큰이 오면 3배 한도를 아예 끄는데, 테스트베드 클라이언트는 TokenStore가 없고 Dial 직후 닫아서 이 경로가 비교군에서 빠졌다. 목적지별 반복 학습이라는 v3의 전제가 바로 토큰이 한도를 없애는 상황이다. 둘째, '신용과 복구는 한 패리티로 동시에 못 얻는다'는 qamp.go의 설계 전제는 quic-go의 FIFO 계상과 복호 가능 패킷 기상 규칙과 맞지 않는다. 선행 패리티를 디코더가 보류했다가 쓰면 같은 바이트로 둘 다 되고, 모형 세계에서 모든 후보 행동을 개선하며 15% 손실층 J3를 13~15 ms, P_fail을 0.06에서 0.0004로 줄인다. 그 밖에 quic-go가 주는 RTT 표본이 클라이언트 자신의 업링크 직렬화로 부풀어 정책 RTT(RTT 200에서 +11.3 ms)와 실패 비용 타이머를 흔든다는 것, 그 부풂으로 업링크 대역을 역산할 수 있다는 것, qlog Tracer의 사전 ACK 관측이 H4의 사후분포 고착을 푼다는 것, 1452 B 수신 버퍼 대 1472 B 패리티 상한 불일치, 키 대기 큐 재처리에 따른 바이트 이중 계상, RTT 200 조건의 200 ms PTO 헛재전송을 찾았다. 숫자는 저널 재집계(측정) 또는 padfec3 모형 계산(모형 세계)으로 구분해 적었다.

## A8-01 [research/high] NEW_TOKEN 토큰 하나로 증폭 한도가 통째로 꺼지는데, 테스트베드와 비교군에 토큰 경로가 없다

CLAIM: quic-go 서버는 핸드셰이크가 끝나면 조건 없이 NEW_TOKEN을 보내고, 다음 연결 Initial에 유효한 비-Retry 토큰이 있으면 그 연결의 sentPacketHandler를 처음부터 주소 검증 상태로 만들어 3배 한도를 적용하지 않는다. 토큰은 클라이언트 IP만 묶고(포트 무관) 기본 24시간 유효하며, 서버 RTT도 복원한다. 클라이언트는 Config.TokenStore만 켜면 이 경로를 쓴다. qamp.go 클라이언트는 TokenStore가 없고, 판마다 새 소켓을 열고, Dial 직후 연결을 닫아 약 1 RTT 뒤에 오는 NEW_TOKEN을 받을 수도 없다. v3 목적지별 사후분포와 gen-2 destCache는 같은 목적지에 반복 접속하는 상황을 전제하는데, quic-go 서버 상대로는 그 상황이 곧 토큰이 한도를 없애는 상황이다. PAD-FEC의 신용 이득이 남는 범위는 토큰 없는 첫 접속, IP가 바뀐 접속, 토큰 키를 공유하지 않는 서버 집합(quic-go는 키 미설정 시 Transport마다 무작위 키), 24시간 경과로 좁혀진다.

- EV: quic-go/connection.go:958-976 서버 handleHandshakeComplete가 tokenGenerator.NewToken 후 NewTokenFrame을 무조건 queueControlFrame
- EV: quic-go/internal/handshake/token_generator.go:74-85 NewToken(RemoteAddr, Timestamp, RTT); 120-126 encodeRemoteAddr는 UDPAddr의 IP만 담음(포트 없음); 30-33 ValidateRemoteAddr
- EV: quic-go/server.go:704-741 비-Retry 토큰이 validateToken(주소 일치, 나이 <= maxTokenAge)을 통과하면 clientAddrVerified=true; 755-759 토큰 RTT 복원; 817-837 newConn에 clientAddrVerified 전달
- EV: quic-go/connection.go:311-323 NewSentPacketHandler(..., clientAddressValidated, ...); internal/ackhandler/sent_packet_handler.go:143 peerAddressValidated=true; 1034-1036 isAmplificationLimited가 즉시 false
- EV: quic-go/transport.go:98-103, 212-215 MaxTokenAge 기본 24h; 397-403 TokenGeneratorKey 미설정 시 무작위 키
- EV: quic-go/interface.go:120-124 TokenStore 문서('Tokens are used to skip address validation on future connection attempts'); token_store.go:58-61 NewLRUTokenStore; connection.go:497-507 클라이언트가 TokenStore.Pop으로 토큰을 싣고 RTT 복원; 2088-2098 NEW_TOKEN 수신 시 Put
- EV: C:/dev/pq_afec_gen32/experiments/quicbed/qamp.go:2663-2671 클라이언트 quic.Config에 TokenStore 없음; 2638 판마다 새 UDP 소켓; 2743, 2782-2783 Dial 직후 CloseWithError와 tr.Close
- EV: qamp.go:2157, 2616, 2630, 2746, 2775 목적지(addr)별 캐시로 결정과 관측(반복 접속 전제)
- EV: quic-go/internal/congestion/pacer.go:64-69, cubic_sender.go:278-285: 토큰으로 RTT가 복원되면 서버 첫 비행에 pacing이 걸림(10데이터그램 버스트 뒤 데이터그램당 약 RTT/40)

PROPOSAL: (1) 비교군에 token 팔을 추가한다: 클라이언트 Config.TokenStore = quic.NewLRUTokenStore(16, 4), 첫 연결 후 1 RTT 이상 유지해 NEW_TOKEN을 받고, 같은 서버 프로세스에 재접속해 첫 접속과 재접속을 따로 집계한다. (2) 연구 주장을 '토큰 없는 주소의 첫 비행'으로 한정해 적고, 정책에 토큰 보유 분기를 넣는다: 토큰이 있으면 신용용 바이트(lead, delta)는 0, 손실 복구용 뒤 패리티만 고른다(토큰 유무는 클라이언트가 안다). (3) 토큰 연결은 서버 pacing이 켜지므로 첫 비행 꼬리 지연을 별도 항으로 잰다.

EFFECT: 반복 접속 조건에서 PAD-FEC와 토큰을 같은 표로 비교할 수 있다. 모형 세계 기준 S_bigcert(k=2, 2 Mbps, RTT 50, 손실 0)에서 v3 최선 (0,3,0) 76.21 ms, 6,553 B 대비 토큰 연결은 t_dec 10.24 + RTT 50 + pacing 꼬리 약 6.25 = 약 66.5 ms, 업링크 2,560 B다. 심사에서 'NEW_TOKEN을 왜 안 쓰나'에 데이터로 답하게 된다.

VALIDATION: cert 16000/2 Mbps/RTT 50에서 손실 0·2·15%로 token 팔, v3.1 auto, gen-2 auto를 교차 배치 측정한다. 재접속 연결의 첫 응답 비행이 3·B를 넘는지(server_bytes)로 토큰 검증 여부를 확인하고, 서버 qlog로 clientAddrVerified를 교차 확인한다.

EFFORT: 중간: 팔 1개, 클라이언트 연결 유지 로직, 집계 분리 | CONF: 0.9 | IMPACT: 연구 주장 범위와 비교군의 완결성

## A8-02 [algorithm/high] '신용과 복구는 한 패리티로 동시에 못 얻는다'는 전제가 quic-go 처리 순서와 맞지 않다: 선행 패리티를 보류했다가 쓰면 같은 바이트로 둘 다 된다

CLAIM: qamp.go는 '패리티를 버릴지(복구) 넘길지(신용)는 도착 시점에 정해야 한다'는 전제로 선행 패리티를 신용 전용, 뒤 패리티를 복구용으로 나누고, layout.py도 복구에 뒤 패리티만 센다. 그러나 quic-go는 바이트를 데이터그램이 연결 큐에서 꺼내질 때 FIFO로 세고, 첫 비행 송신은 ClientHello를 완성하는 복호 가능 패킷을 처리한 직후에만 깨어난다. 따라서 decodeConn이 선행 패리티를 quic-go에 넘기지 않고 보관하다가, 마지막 원본이 도착한 순간 소거가 없으면 그 원본보다 먼저 pending에 넣고(신용, 경주 없음), 소거가 있으면 뒤 패리티를 먼저 쓰고 모자라는 만큼 선행 심볼로 복구하면(복원본만 넘김, '인계 <= 물리 도착' 불변식 유지) 모든 패리티가 신용과 복구를 겸한다. 송신 순서와 바이트는 그대로다. 모형 세계에서 이 변경은 4개 맥락의 모든 후보 행동에서 J3를 나쁘게 하지 않았고(악화 0개), 손실이 클수록 크게 줄였다.

- EV: quic-go/connection.go:1051-1052 handleOnePacket 첫 줄 ReceivedBytes(큐에서 꺼낼 때 계상); 1013-1039 handlePackets가 큐를 순서대로 처리하고 핸드셰이크 전 CRYPTO 송신 데이터가 생기면 중단
- EV: quic-go/connection.go:639-648 복호 성공 패킷이 있어야 즉시 송신 단계; 662-671 복호 실패뿐이면 'if !wasProcessed { continue }' (팀 인용: padfec/policy.py:604-604)
- EV: qamp.go:1242-1258 주석 '두 이득은 하나의 패리티로 동시에 가질 수 없다 ... 버릴지 말지는 패리티가 도착한 시점에 정해야 하고'; 1453-1476 v3 송신 순서 lead, 원본, 뒤 패리티
- EV: qamp.go:497-502 isCreditParity(index < lead); 1889-1902 creditLocked가 즉시 stackLocked하고 심볼 미보관; 2224-2236 '선행 패리티만 신용 전용이다'
- EV: qamp.go:1725-1737 decodeConn.ReadFrom은 pending을 먼저 내주는 구조라 보류 후 방출을 넣을 자리가 이미 있음
- EV: C:/dev/pq_afec_gen32/padfec3/layout.py:160-176 성공 조건 miss <= len(trail), 172 base_credit = la*pz + k*w
- EV: 모형 세계 m03_combined.py(같은 순서, 같은 바이트): S_bigcert(S=18231, RTT 50, 2 Mbps) p=0.15 현행 최선 (0,3,1) J=103.42 ms, P_fail 0.0607 -> 보류 최선 (0,4,0) J=90.09 ms, P_fail 0.0004 (-13.33 ms); p=0.10 -7.93, p=0.05 -2.14, p=0.02 -0.09 ms
- EV: m03_combined.py: H_c12000_u5(RTT 120, 5 Mbps) p=0.15 -15.03 ms, p=0.10 -6.32 ms; S_rtt200 p=0.15 -2.90 ms; H_c6000_u10 p=0.15 -3.52 ms; 모든 맥락에서 보류 변형이 더 나쁜 후보 0/16 또는 0/30
- EV: C:/dev/pq_afec_gen31/g3/RESULT_stage3.md:84 15% 층 (0,3,1)의 3-RTT·PTO 잔차(+171~+1,388 ms)가 경보를 일으킴

PROPOSAL: decodeConn에 flight 단위 보류 버퍼를 둔다. 선행 패리티는 도착 즉시 stackLocked하지 않고 심볼과 함께 보관한다. 마지막 원본(index k-1)이 오면 소거 집합 E를 확정하고(재정렬 없음 가정은 현행 뒤 패리티 판정과 같다), E가 비면 보관 패리티를 그 원본 앞에 pending으로 넣어 quic-go에 넘기고, E가 있으면 뒤 패리티 우선, 부족분은 선행 심볼로 recoverMany한다. 마지막 원본이 사라진 경우는 첫 뒤 패리티 도착 또는 τ(W)+1 ms 타이머로 확정한다. layout.py에 같은 규칙(need_lead = miss - trail_arrived <= lead_arrived이면 성공, 신용 (la - need_lead)*pz + k*w)을 넣고 policy3.go 미러와 parity gate를 갱신한다.

EFFECT: 업링크 바이트를 늘리지 않고 15% 손실층 P_fail을 약 0.06에서 0.0004로, J3를 13~15 ms 줄인다(모형 세계). H4에서 감시층 오경보를 만든 3-RTT·PTO 꼬리 잔차도 같이 줄어든다.

VALIDATION: (1) scriptConn 자체시험에서 도착 순열 전수로 '스택 인계 바이트 <= 물리 도착 바이트'와 '보류 패리티의 ReceivedBytes가 마지막 원본 처리보다 먼저'를 검사한다. (2) S_bigcert 15%와 H_c12000 8%에서 현행 디코더 (0,3,1) 대 보류 디코더 (0,3,1)·(0,4,0)을 교차 배치 측정하고 서버 BytesIn, BytesToStack, Recovered, HCT 분포를 비교한다.

EFFORT: 큼: decodeConn 보류 버퍼, layout와 Go 미러, gate 갱신 | CONF: 0.8 | IMPACT: 고손실층 핵심 지표(J3, P_fail)와 설계 전제 수정

## A8-03 [algorithm/medium] 증폭 회계의 정확한 규칙: 1-RTT 판정식은 quic-go와 정확히 맞지만, 그 일치가 quic-go 고유 동작에 기대고 있다

CLAIM: (a) 서버 연결에 귀속된 데이터그램은 파싱과 복호 전에 UDP 페이로드 전체 길이로 한 번 세며, 복호 실패, DCID가 다른 코얼레스 꼬리, 중복 PN, 예상 밖 SCID 패킷도 센 뒤 버린다. 연결 생성 후에는 1200 B 하한이 없다. 패리티는 AEAD 실패가 예약 비트 검사보다 먼저 반환되어 연결을 죽이지 않는다. (b) 연결 생성 전에는 1200 B 미만 Initial, Initial이 아닌 롱헤더, DCID 8 B 미만은 세지 않고 버린다. 첫 Initial은 복호 확인 없이 연결을 만들고 그대로 센다(선행 패리티가 연결을 만드는 경로). (c) 1452 B를 넘는 데이터그램은 1452 B만 읽혀 그만큼만 센다. (d) 검사는 데이터그램 하나를 보내기 전마다 bytesSent >= 3·bytesReceived를 보는 불리언이라 초과는 최대 1데이터그램(P-1 B)이고, bytesSent에는 ACK 전용 패킷도 들어간다. (e) 검증은 Handshake 패킷 1개 수신이나 유효 토큰으로 끝난다. (f) 한도 중에는 서버 손실 감지 알람이 꺼져 서버 쪽 재전송이 없다. layout.py:96-97의 3·credit - A_pre > 1280·(n_need-1)은 (d)를 정확히 옮긴 식이다. 하지만 정확히 절삭하는 서버(quiche)에서는 마지막 데이터그램 크기만큼, 클라이언트 신용으로 최대 약 427 B까지 경계가 옮겨지고, (a)의 '작은 데이터그램도 신용'은 RFC 9000 14.1을 엄격히 따르는 구현에서 보장되지 않는다.

- EV: quic-go/connection.go:64 Size()=len(data); 1051-1052 ReceivedBytes가 handleOnePacket 첫 줄; 1079-1090 DCID가 다른 코얼레스 꼬리 break; 1325-1339 예상 밖 SCID Initial 폐기; 1367-1384 중복 폐기; 1420-1436 ErrDecryptionFailed 폐기
- EV: quic-go/packet_unpacker.go:127-140 예약 비트 오류가 있어도 복호를 먼저 하고 AEAD 실패를 반환
- EV: quic-go/server.go:499-513 연결 전 Initial < 1200 B 폐기(internal/protocol/protocol.go:116-117); 515-543 Initial 아닌 롱헤더 폐기; 680-694 DCID < 8 B 폐기; 817-838 newConn 후 conn.handlePacket(p); 699-702 대기 중 도착분은 두 번째 맵 조회로 연결에 전달
- EV: MinInitialPacketSize 사용처는 config.go:42, connection.go:2881, packet_packer.go:829-830, server.go:95뿐(연결 내부 검사 없음)
- EV: quic-go/sys_conn.go:96-100 net.UDPConn이 아니면 basicConn; 116-131 buffer.Data[:MaxPacketBufferSize]로 읽음; internal/protocol/protocol.go:107-111 MaxPacketBufferSize = 1452
- EV: quic-go/internal/ackhandler/sent_packet_handler.go:981-993 한도면 SendNone; 1034-1039 bytesSent >= amplificationFactor*bytesReceived; connection.go:2450-2459, 2536-2552 핸드셰이크 중 sendPackets 1회 = 코얼레스 데이터그램 1개
- EV: sent_packet_handler.go:252-264 SentPacket이 모든 패킷 크기를 bytesSent에 더함; connection.go:2788-2809 롱헤더 패킷마다 SentPacket
- EV: sent_packet_handler.go:233-239 서버가 Handshake 패킷을 받으면 peerAddressValidated=true; 721-731 한도 중 lossDetectionTime은 빈 알람
- EV: padfec3/layout.py:96-97 one_rtt_ok; experiments/quicbed/policy3.go:169-171 같은 식

PROPOSAL: (1) 보고서 회계 절에 위 6개 규칙을 'quic-go v0.61.0 고정 사실'로 행 번호와 함께 적고, 결과 해석을 quic-go 서버 기준으로 명시한다. (2) layout와 policy3에 서버 회계 방식을 매개변수로 두고(quic-go: 3·credit - A_pre > P·(n_need-1), strict: 3·credit - A_pre >= S_total) 두 경우 최적 행동이 갈리는 영역을 표로 낸다. (3) 연결 생성 후 1200 B 미만 신용 데이터그램을 쓰는 변형은 만들지 않는다.

EFFECT: '패리티가 신용이 된다'는 핵심 주장의 적용 범위가 소스 행 단위로 고정되고, strict 서버에서 1-byte cliff와 δ 지렛대가 얼마나 사라지는지 미리 수치로 보인다.

VALIDATION: 모형 세계에서 strict 규칙으로 S_bigcert와 H 맥락의 최선 행동과 J3 변화를 계산한다. 실측은 quiche 서버로 같은 비행을 보내 첫 응답 바이트가 3·B를 넘지 않는지 server_bytes로 확인한다.

EFFORT: 작음~중간: 문서화와 모형 매개변수 1개 | CONF: 0.9 | IMPACT: 일반화 범위의 근거

## A8-04 [code/medium] 키가 아직 없는 Handshake형 패킷은 큐에 들어갔다가 재처리되며 바이트가 두 번 세진다: 신용 지렛대로 쓰면 안 되는 quic-go 결함

CLAIM: 서버 연결이 Handshake 읽기 키를 얻기 전에 같은 DCID의 Handshake형 롱헤더 패킷이 오면, handleOnePacket이 바이트를 센 뒤 ErrKeysNotYetAvailable로 undecryptablePackets에 넣는다(최대 32개). ClientHello가 완성되어 키가 생기면 이 패킷들을 다시 handleOnePacket으로 처리하고, 그 첫 줄에서 ReceivedBytes가 또 불린다. 같은 수신 바이트가 3배 예산에 두 번 들어간다. 현재 패리티는 Initial형(0xC3)이라 Initial 키로 바로 복호 실패 처리되어 이 경로를 타지 않으므로 기존 실측은 오염되지 않았다. 그러나 '패리티를 Handshake형으로 만들면 신용이 2배'라는 지렛대가 소스상 존재하고, 이는 RFC 9000 8.1의 취지(실제로 받은 바이트만 센다)를 어긴다. 스푸핑 공격자도 같은 경로로 3배를 넘길 수 있어 upstream 보고 대상이다(소스 읽기로만 확인, 실행 검증 안 함).

- EV: quic-go/connection.go:1051-1052 handleOnePacket 첫 줄 ReceivedBytes
- EV: quic-go/internal/handshake/crypto_setup.go:651-655 handshakeOpener가 없고 initialOpener가 있으면 ErrKeysNotYetAvailable
- EV: quic-go/connection.go:1410-1414 ErrKeysNotYetAvailable이면 tryQueueingUndecryptablePacket; 2964-2994 큐 추가(internal/protocol/params.go:17-18 MaxUndecryptablePackets = 32)
- EV: quic-go/connection.go:2030-2033 EventReceivedReadKeys에서 큐를 undecryptablePacketsToProcess로 이동; 616-631 run loop 맨 앞에서 각 패킷을 handleOnePacket으로 재처리(1052에서 재계상)
- EV: quic-go/server.go:515-543 연결 전 Handshake형은 폐기되므로 연결 생성 후(첫 원본 또는 선행 패리티 이후) 도착분만 해당
- EV: qamp.go:524 buildParity 첫 바이트 0xC3(Initial)이라 현행 패리티는 이 경로 밖

PROPOSAL: (1) decodeConn에 '클라이언트 첫 비행에 Initial이 아닌 롱헤더가 섞이면 경보' 불변식 카운터를 추가해 향후 변형이 우연히 이 경로를 타지 않게 한다. (2) 연구 노트에 '사용하지 않는 지렛대'로 근거와 함께 적는다. (3) 저장소 밖 스크래치 모듈에서 quic-go 서버에 Initial과 같은 DCID의 쓰레기 Handshake 패킷을 보내 첫 응답 바이트가 3·물리 수신을 넘는지 재현하고, 재현되면 quic-go에 보안 이슈로 보고한다.

EFFECT: 신용 회계가 실제 수신 바이트만 반영한다는 보증이 하나 늘고, 심사와 윤리 측면에서 '규격 위반 지렛대를 쓰지 않았다'를 근거로 말할 수 있다.

VALIDATION: 위 재현 시험에서 서버 qlog의 packet_buffered 이벤트와 첫 응답 비행 바이트로 2배 계상 여부를 판정한다.

EFFORT: 작음: 카운터 1개, 스크래치 재현 1회 | CONF: 0.7 | IMPACT: 측정 신뢰성과 연구 윤리

## A8-05 [code/medium] 패리티 상한을 MTU 기준 1472 B로 걸었지만 quic-go 서버는 1452 B까지만 읽는다: 1453~1472 B 패리티는 잘려 복구 능력이 0이다

CLAIM: decide3, policy3.go, policy.go는 패리티 데이터그램이 1500 - 28 = 1472 B 이하면 후보로 허용한다. 서버 decodeConn.ReadFrom은 quic-go가 넘긴 버퍼에 직접 읽는데, quic-go basicConn은 그 버퍼를 1452 B로 잘라 넘긴다. 그래서 W_eff + 39 + 6k > 1452인 패리티는 커널에서 1452 B로 잘리고, parseFecBlock 길이 검사에서 탈락해 원본으로 분류된 뒤 1452 B 신용만 남는다. 복구용으로 고른 패리티가 실제로는 복구를 못 한다. sealed 저널에서 gen-2 auto가 W=1406(k=2, 패리티 1457 B)을 6번 골랐다. v3는 이번 조건에서 delta 0과 1만 써서 해당이 없었지만 candidates3는 이 범위를 막지 않는다(k=2이면 W_eff 1402~1421).

- EV: quic-go/sys_conn.go:116-131 basicConn.ReadPacket이 buffer.Data[:protocol.MaxPacketBufferSize]로 읽음(주석 'we only read a truncated packet'); internal/protocol/protocol.go:107-111 = 1452
- EV: qamp.go:1740 decodeConn.ReadFrom이 s.PacketConn.ReadFrom(b)로 quic-go 버퍼에 읽음; 908-912 parseFecBlock이 i+blen > len(d)이면 nil; 2193-2218 원본 경로로 처리
- EV: padfec3/decide3.py:9 UDP_MAX = quantum.TYPICAL_MTU - 28(padfec/quantum.py:17 = 1500); 113 parity_bytes(W_eff, k) > UDP_MAX만 제외
- EV: experiments/quicbed/policy3.go:51 p3UDPMax = typicalMTU - 28; 1205-1210 필터; policy.go:279 typicalMTU = 1500; 792-798 2026-09-07 감사 주석은 MTU만 고려
- EV: padfec/policy.py:282-286 패리티 크기 = W + 39 + 6k
- EV: p02_scan.py: 124,800행 중 평균 패리티 > 1452 B 행 6개(전부 g2auto, ips_eff 1406: S_rtt200 run1 4, run2 1, D_p17_unlimited 1); 패리티 크기 분포 1320대 41,785행, 1330대 81,455행, 1450대 3, 1460대 3

PROPOSAL: UDP_MAX를 1452(quic-go MaxPacketBufferSize)로 바꾸거나 같은 뜻으로 패리티 후보 조건에 W_eff <= 1413 - 6k를 넣는다(decide3.py:9·113, policy3.go:51·1209, policy.go:460). g3/policy3_reference_gen.py와 parity gate의 udp_max도 함께 갱신한다. decodeConn에 'parseFecBlock은 실패했지만 PFEC 매직이 들어 있는 데이터그램' 카운터를 추가해 잘림을 계측한다.

EFFECT: 복구 못 하는 패리티를 복구용으로 계산하는 오류가 사라진다. 영향 구간이 좁아 기존 결과 수치 변화는 작지만, delta가 큰 조건에서의 잠재 결함을 막는다.

VALIDATION: W=1406, k=2, m=1, drop-initial 0에서 서버 Recovered가 0인지(현행 예측) 확인하고, 수정 후에는 해당 후보가 생성되지 않는지 확인한다. 저널 재집계로 패리티 > 1452 B 행이 0이 되는지 본다.

EFFORT: 작음: 상수 3곳과 gate | CONF: 0.85 | IMPACT: 잠재 정확성 결함 제거

## A8-06 [algorithm/medium] 41 B 사전 ACK(A_pre)는 소스와 실측 모두 맞다. 다만 s_hat에 같은 41 B가 들어 있어 두 번 청구되고, 클라이언트가 피할 길은 k=1뿐인데 ML-KEM에서는 불가능하다

CLAIM: quic-go 서버는 Initial의 ack-eliciting 패킷을 즉시 ACK하고, 처리한 패킷이 있으면 곧바로 송신 단계로 가며, 서버의 ACK 전용 Initial은 패딩하지 않는다. 대역 제한으로 원본이 τ(W) 간격으로 오면 ClientHello가 완성되기 전 원본마다 41 B(헤더 20 + ACK 5 + 태그 16, CID 4 B 기준) ACK가 나가 bytesSent를 먹고, 무제한이면 한 배치로 처리되어 합쳐진다. 실측도 같다: 같은 인증서에서 server_bytes 중앙값이 2 Mbps 10,991~10,993 B, 무제한 10,949~10,951 B로 약 42 B 차이다. 문제는 두 가지다. (1) 학습이 S로 쓰는 srv_bytes는 클라이언트가 받은 모든 서버 바이트라 사전 ACK가 이미 들어 있는데, 판정식이 A_pre를 또 뺀다. S가 bin 경계 아래 41 B 안에 있으면 n_need가 1 커진다(S 4,000~20,000 중 3.07%). sealed 8개 조건은 모두 안 바뀌었다. (2) 41은 CID 길이에 묶인 상수다. 클라이언트 쪽 회피는 순서·간격 조작으로는 안 되고(모든 원본이 ack-eliciting이고 즉시 ACK) k=1만 되는데, X25519MLKEM768 ClientHello는 키 공유만 1,216 B라 실측상 W 1280·1281·1406 모두 k=2였다(1452에서도 k=2라는 것은 크기 추정에 따른 가설).

- EV: quic-go/internal/ackhandler/received_packet_tracker.go:15-16 'Every received packet is acknowledged immediately', 44-48, 51-72
- EV: quic-go/connection.go:645-648 처리된 패킷이 있으면 즉시 진행; 1013-1039 배치 처리
- EV: quic-go/packet_packer.go:319-323 서버는 ack-eliciting Initial만 패딩; internal/wire/extended_header.go:119-125 헤더 길이; internal/protocol/packet_number.go:43-57 첫 PN 2 B
- EV: qamp.go:1498 serverConnIDLength = 4; quic-go/transport.go:406-416 클라이언트 CID 길이 기본 4(internal/protocol/params.go:128-130)
- EV: padfec3/layout.py:16, 89-93; policy3.go:55, 162-167
- EV: qamp.go:1005-1020 fecConn.ReadFrom이 C1 회신을 뺀 모든 수신을 countRx; 2698 srvBytes; padfec3/learn3.py:642-643 srv_bytes를 그대로 S_hist에 넣음
- EV: p04_srvbytes.py: D_p17_mbps2(cert 9007/9008) 중앙 10,991/10,993 B 대 D_p17_unlimited(9006) 10,949 B
- EV: p06_hist.py: 'server_bytes - cert' 2 Mbps g2auto 1970~1990 B 3,996/4,027행, 1930~1950 B 31행; 무제한 g2auto 1930~1950 B 4,432/4,444행, 1970~1990 B 5행
- EV: p09_checks.py (d): bin_needed_s(S) != bin_needed_s(S+41) 비율 0.0307(k=2, W=1280, c_pkt 41.983); S 18231, 10992, 7908, 9950, 14072, 16149, 4678 모두 동일
- EV: goroot/src/crypto/mlkem/mlkem.go:26-30(캡슐화 키 1184, 암호문 1088); goroot/src/crypto/tls/key_schedule.go:188-193; handshake_client.go:141-159(CurvePreferences에 X25519가 없으면 fallback share 제거)
- EV: p09_checks.py (b): X25519MLKEM768 k=2 (W 1280: 93,992행, 1281: 3,596, 1406: 6), x25519 k=1

PROPOSAL: (1) S 관측에서 사전 ACK를 빼거나(fecConn.ReadFrom에서 첫 >=1200 B 서버 데이터그램 이전의 작은 Initial 데이터그램 크기를 따로 집계) 판정식의 A_pre를 빼되, 둘 중 하나만 남긴다. (2) A_pre를 상수 41 대신 목적지별 관측 중앙값으로 학습한다(CID가 8~20 B인 서버 대비). (3) ML-KEM에서 k=1을 노리는 행동은 후보에서 미리 빼고 근거(키 공유 크기)를 보고서에 적는다.

EFFECT: 약 3% S 값에서 생기는 n_need 과대(신용 약 427 B 과요구, 즉 불필요한 패리티 1개 수준)가 사라지고, A_pre 모형의 실측 근거가 문서로 남는다.

VALIDATION: 2 Mbps와 무제한 쌍이 있는 조건에서 s_hat 차이가 41(k-1)인지 확인하고, 수정 후 같은 cert에서 업링크 조건과 무관하게 s_hat이 같아지는지 본다. 모형 세계에서 S를 1 B 단위로 훑어 flip 구간이 0인지 확인한다.

EFFORT: 작음 | CONF: 0.85 | IMPACT: 모형 입력 편향 제거, A_pre 근거 확보

## A8-07 [measurement/medium] 정책 RTT는 클라이언트 자신의 업링크 직렬화로 부푼 quic-go MinRTT다: RTT 200 조건에서 +11.3 ms이고, 그 부풂의 기울기로 업링크 대역을 직접 잴 수 있다

CLAIM: qamp는 Dial 직후 ConnectionStats를 읽고 곧 닫으므로 그 시점의 RTT 표본은 첫 비행 Initial에 대한 서버 ACK뿐이다. quic-go 송신 시각은 패킷을 만든 시각이고, fecConn이 원본을 모아 선행 패리티 뒤에 내보내며 netem rate가 직렬화하므로 표본에 τ(선행 패리티) + τ(O0)가 그대로 들어간다. 연결별 MinRTT - netem RTT 중앙값은 2 Mbps·RTT 50에서 lead 0/1/2/3 = +6.02/+11.27/+16.77/+22.35 ms, 무제한 +0.95 ms다. v3 캐시는 목적지별 최솟값을 정책 RTT로 쓰는데, +0.7 ms짜리 깨끗한 표본은 드문 손실 경로(A8-08의 Handshake PTO 탐침)에서만 생겨, 15% 층이 있는 RTT 50 조건은 +0.75 ms로 내려앉았지만 S_rtt200은 +11.31 ms로 남았다. 모형은 t_dec로 직렬화를 따로 더하므로 이 몫이 왕복마다 이중 계상된다(모형 세계: S_rtt200 맥락에서 RTT 211.31을 넣으면 고르는 행동은 같지만 J_pred가 +11.53 ms(p=0.02), +11.70 ms(p=0.15)). 반대로 이 부풂은 정보다: lead 하나(약 1,331 B)당 +5.44 ms라 업링크 약 1.96 Mbps(참값 2)로 역산되고, 5 Mbps 조건은 4.86 Mbps다. 정책이 참 업링크 대역을 입력으로 받는 전제를 quic-go가 주는 값으로 대체할 수 있다.

- EV: qamp.go:2210-2212 Dial 시간, 2736 measuredPathRTT(conn.ConnectionStats()), 2743 즉시 CloseWithError; 2531-2536 MinRTT 사용
- EV: quic-go/internal/utils/rtt_stats.go:81-94 minRTT는 ack delay 보정 없는 원 표본; connection.go:2798-2809 SentPacket 시각은 패킹 시각
- EV: qamp.go:965-995 원본을 flight에 모았다가 flushFlight; 1453-1476 v3 순서 L..L O..O P..P
- EV: experiments/quicbed/policy3.go:1502-1507 policyRTT = e.MinRTT; 1710-1714 목적지별 min 갱신
- EV: p02_scan.py: (RTT 50, 2 Mbps) lead0 n=2206 +6.02, lead1 n=2524 +11.27, lead2 n=1990 +16.77, lead3 n=12014 +22.35; (120, 5) lead2 +6.99, lead3 +9.18; 무제한 +0.95 ms
- EV: p02_scan.py: policy_rtt - RTT 중앙 (50,2) +0.75(n=14,197), (200,2) +11.31(n=8,998), (120,5) +1.82, (120,10) +1.72, (80,10) +1.87 ms
- EV: p03_lowrtt.py: 2 Mbps에서 inflation < 3 ms인 행은 HCT 258~281 ms의 PTO 경로(예: D_p17_mbps2 g3auto i=219, HCT 258.676 ms, +0.75 ms)
- EV: p09_checks.py (c): decide_core(점질량 사후) S_rtt200 맥락 rtt 200 -> (0,1,2) J 219.57, rtt 211.31 -> (0,1,2) J 231.10; p=0.15 (0,2,2) 227.55 대 239.25

PROPOSAL: (1) 정책 RTT를 'MinRTT - τ(그 연결에서 O0 앞에 보낸 바이트 + W)'로 보정하거나, qlog Tracer로 사전 ACK가 확인한 O0 표본만 쓰고 τ를 뺀다. (2) 업링크 대역을 연결 기록으로 추정한다: 같은 목적지에서 lead가 다른 연결들의 MinRTT 차이를 바이트 차이에 회귀하거나, 한 연결 안의 O0 표본(사전 ACK)과 O1 표본(첫 비행 ACK) 차이 = τ(O1) + 서버 처리로 잡는다. (3) EVENT_RTT_FRAC, 감시 문턱 0.5·RTT, RTT 200 shield가 쓰는 RTT도 같은 보정값으로 통일한다.

EFFECT: RTT 200·2 Mbps에서 J3 예측 편향 약 11 ms가 사라진다(결정 불변, 예측·잔차·문턱 교정). 업링크 대역을 주지 않아도 같은 결정을 내릴 수 있음을 보이면 오라클 입력 비판을 피한다.

VALIDATION: 저널 재집계로 보정 RTT가 netem RTT ±1 ms 안에 드는지 조건별로 확인한다. 추정 대역을 2·5·10 Mbps 조건의 참값과 비교하고(목표 오차 10% 이내), 모형 세계에서 추정 대역으로 decide3를 돌려 sealed 결정과의 일치율을 잰다.

EFFORT: 중간 | CONF: 0.85 | IMPACT: 모형 입력의 정확성, 오라클 입력 제거

## A8-08 [algorithm/medium] 15% big-cert에서 J3가 6.84 ms 낮게 예측한 원인 후보 셋: 상수 처리 지연, 부푼 RTT로 도는 quic-go 타이머, 모형에 없는 '응답 비행 유실 후 클라이언트 PTO' 경로

CLAIM: g3fixL3 (0,3,1)의 관측 평균 110.26 ms 대 모형 J 103.42 ms(p=0.15, RTT 50)의 차이 6.84 ms는 다음 셋의 합 약 6.7 ms로 거의 설명된다. (a) 1-RTT 군집 평균 79.9 ms가 모형 t_dec + RTT = 76.27 ms보다 약 3.6 ms 길고, p=2%에서도 관측 83.06 대 J 79.29로 +3.77 ms라 손실과 무관한 상수다(성공 확률 약 0.95를 곱해 약 3.4 ms). 서버 pacing은 원인이 아니다: 토큰 없는 연결에서 서버는 SetInitialRTT(0)으로 SRTT가 0이 되고 대역 추정이 1 ms 기준이라 버스트가 약 80데이터그램이다. (b) quic-go 클라이언트의 손실 판정 지연 9/8·max(SRTT, latest)와 PTO SRTT + 4·RTTVAR는 A8-07의 부푼 표본으로 계산되는데, 모형 실패 비용은 참 RTT에 1.125와 3.0을 곱한다. lead 3·2 Mbps의 +22.35 ms를 넣으면 J가 +1.88 ms 커진다(모형 세계). (c) 명목 2-RTT 결과에서 클라이언트 응답 데이터그램이 모두 사라지면, 서버는 한도에 묶여 PTO 알람도 꺼져 있으므로 클라이언트의 anti-deadlock Handshake PTO 탐침을 기다린다. 이 경로는 모형에 없다. 관측된 'Initial 재전송 없이 HCT >= 185 ms' 행 0.8%(평균 303.7 ms)는 2-RTT 확률 0.375 × 0.15² = 0.0084와 맞고, 모형이 이를 2-RTT(약 131 ms)로 셈해서 약 1.4 ms가 빠진다. 이 탐침은 패딩 안 된 작은 Handshake PING이라 A8-07의 드문 깨끗한 RTT 표본을 만드는 원인으로도 보인다(소스와 HCT 군집으로부터의 추론, qlog 미확인).

- EV: quic-go/internal/ackhandler/sent_packet_handler.go:787-798 lossDelay = 9/8 * max(LatestRTT, SmoothedRTT); internal/utils/rtt_stats.go:69-77 PTO = SRTT + max(4·meanDev, 1 ms), 표본 전 2·100 ms
- EV: sent_packet_handler.go:646-657 핸드셰이크 미확인이고 전송 중 crypto가 없으며 peerCompletedAddressValidation false면 클라이언트 anti-deadlock PTO; 891-907 bytesInFlight 0이면 탐침 1개, Initial 키가 없으면 SendPTOHandshake; connection.go:2810-2817 첫 Handshake 송신 때 Initial 키 폐기
- EV: sent_packet_handler.go:721-731 서버는 한도 중 손실 감지 알람 해제
- EV: quic-go/server.go:755-759 토큰 없으면 rtt=0 -> connection.go:311 SetInitialRTT(0); rtt_stats.go:127-139; internal/congestion/cubic_sender.go:278-285 SRTT 0이면 1 ms로 대역 계산; pacer.go:64-69 maxBurstSize = max(bw·2 ms, 10·1280)
- EV: padfec3/layout.py:209 2-RTT HCT = t_dec + 2·rtt + resp; 221-231 실패 비용; padfec/policy.py:28-32 상수 출처
- EV: p08_hctclusters.py: S_bigcert 15% g3fixL3 n=2250 fast 0.576(평균 79.9), 2rtt 0.375(130.9), slow 0.049(310.8), slow이면서 Initial 재전송 없음 0.008(303.7); 2% 같은 팔 fast 0.945(79.9)
- EV: m02_timer_infl.py: (0,3,1) p=0.15 J=103.42, 실패 종류 pto 0.0225, ptoS 0.0191, ack 0.0191, 타이머 보정 dJ +1.88 ms(p=0.02 +0.04 ms)

PROPOSAL: (1) 1-RTT HCT에 조건별 상수 c_proc(인증서 크기와 KEM별, big-cert ML-KEM 약 3.6 ms)를 넣고 sealed 2% 층으로 적합한다. (2) 실패 비용의 타이머 항을 클라이언트가 실제로 가질 표본(rtt + τ(L^lead) + τ(W) + 처리)으로 계산한다. (3) 2-RTT 가지에 '응답 비행 전부 유실' 확률 p^r(r = 응답 데이터그램 수, 관측상 2)과 그때 비용(anti-deadlock PTO ≈ 3·부푼 표본 + RTT)을 추가한다.

EFFECT: 15% 층 예측 오차를 6.84 ms에서 약 0.2 ms 수준으로 줄여(모형 세계) H3와 감시층 잔차의 기준선을 바로잡는다.

VALIDATION: 수정한 evaluate로 sealed 전 조건의 팔별 평균 HCT를 예측해 현재 오차와 비교한다. (c)는 Tracer를 켠 소규모 진단 실행에서 Handshake PTO 탐침 송신과 그 ACK의 RTT 표본을 직접 확인한다.

EFFORT: 중간 | CONF: 0.6 | IMPACT: H3·H4 해석과 감시층 교정

## A8-09 [algorithm/high] quic-go Tracer가 주는 패킷 단위 ACK·RTT·손실 이벤트로, 명목 2-RTT 행동을 고른 동안에도 손실률을 계속 배울 수 있다(H4 사후분포 고착의 해법)

CLAIM: v3는 연결당 1비트 y만 쓰고, 명목 2-RTT 행동(예 (0,0,4))에서는 y가 거의 항상 1이라 정보가 없어 관측을 건너뛴다. 그래서 H4에서 사후분포가 교차점 위에 갇혔다. quic-go Config.Tracer는 사용자 Recorder에 qlog.PacketReceived(ACK range를 포함한 프레임), qlog.MetricsUpdated(LatestRTT 등), qlog.PacketLost를 Go 구조체로 넘긴다. 대역 제한 업링크에서는 서버가 원본마다 41 B 사전 ACK를 보내므로(A8-06), 클라이언트는 FEC가 나중에 복구한 원본까지 포함해 O0..O_{k-2}의 물리 도착 여부를 서버 수정 없이 안다. 이 관측은 행동과 무관하게 연결마다 k-1개 이상의 Bernoulli 표본이다. 모형 세계 Fisher 정보: S_bigcert (0,0,4)에서 y의 정보는 0(P(y=1) = 0.990 고정)인데 원본 도착 1비트는 p=0.02/0.05/0.10/0.15에서 51.0/21.1/11.1/7.8이다. H_c12000 (0,3,1) p=0.02에서도 y 4.36 대 51.0이다. 반면 S_bigcert (0,3,1)처럼 사건 확률이 가파른 곳은 y가 더 크므로(134 대 51) 대체가 아니라 결합이 맞다. 패리티는 복호되지 않아 ACK되지 않으므로 패리티 손실은 이 경로로 안 보이고(C1이 필요한 몫), 무제한 업링크에서는 사전 ACK가 없어 복구된 원본과 도착한 원본이 구별되지 않는다.

- EV: quic-go/interface.go:185 Config.Tracer func(ctx, isClient, connID) qlogwriter.Trace; qlogwriter/writer.go:15-46 Trace.AddProducer와 Recorder.RecordEvent(Event)는 사용자 구현 가능
- EV: quic-go/connection.go:1713-1739 롱헤더 수신마다 qlog.PacketReceived{Header(PN), Frames}; connection_logging.go:16-21, 49-58 AckFrame 변환; qlog/event.go:264-272, 438-446, 502-505
- EV: quic-go/internal/ackhandler/sent_packet_handler.go:314-340 MetricsUpdated; 814, 830 PacketLost
- EV: qamp.go:2192-2200 클라이언트 Config에 Tracer 없음; 2733-2736 ConnectionStats만 읽음
- EV: padfec3/learn3.py:596-600 y 정의(EVENT_RTT_FRAC 0.5); 244-251, 615-626 nominal2·shield·guard면 likelihood 생략
- EV: C:/dev/pq_afec_gen31/g3/RESULT_stage3.md:84 15% 층 경보와 고착 서술
- EV: m04_info.py 모형 세계 Fisher 정보(위 숫자), EPS 0.01 반영

PROPOSAL: qamp 클라이언트에 메모리 Recorder를 붙여 (a) Initial 공간 ACK range와 수신 시각, (b) 사전 ACK의 PN, (c) LatestRTT 표본을 trial 기록에 남긴다. learn3에 두 번째 가능도 항을 넣는다: 사전 ACK로 확인된 원본 도착 비트 ~ Bernoulli(1-p), 행동이 명목 2-RTT여도 갱신한다. 무제한 업링크(사전 ACK 없음)에서는 이 항을 끄고 C1을 쓴다.

EFFECT: 명목 2-RTT 행동 구간에서도 연결당 약 8~51의 Fisher 정보가 쌓여(모형 세계) 관측 생략에 따른 고착이 구조적으로 사라지고, 저손실 목적지에서 수렴이 수 배 빨라진다.

VALIDATION: adaptation_benchmark.py에 'ACK 비트 관측' 변형을 넣어 손실 2%에서 15%로 바뀌는 시나리오에서 교차점 이탈까지 걸리는 연결 수를 비교한다. 실측은 Tracer를 켠 소규모 진단에서 drop-initial 주입으로 사전 ACK가 원본 도착과 1:1인지 확인한다.

EFFORT: 중간: Recorder 구현, learn3 가능도 항, Go 미러 | CONF: 0.7 | IMPACT: H4 실패 원인의 직접 해소

## A8-10 [measurement/low] RTT 200 조건의 모든 연결에서 클라이언트가 200 ms PTO로 ClientHello를 헛재전송한다(탐침 2장, 각 W 바이트)

CLAIM: quic-go 클라이언트는 RTT 표본이 없으면 PTO를 2·100 ms로 고정하고(토큰으로 RTT를 복원해도 hasMeasurement 전에는 같다), 터지면 탐침 2개를 보낸다. 첫 ACK는 RTT + τ(O0 앞 바이트 + W) + 처리 뒤에 오므로 netem RTT 200에서는 항상 늦는다. 실측 S_rtt200의 1-RTT 행은 전 팔에서 클라이언트 Initial 데이터그램이 첫 비행 + 3개(ACK 1 + 탐침 2)였고, RTT 50에서는 + 1개였다. 탐침은 W로 패딩되어 연결당 업링크가 약 2,560 B 늘지만 first_flight_bytes 비용 지표에는 안 잡힌다. 탐침은 복호 가능 패킷이라 2-RTT 상황에서 서버를 깨워 3W를 더 보내게 할 수 있는데 모형에 없다. v3의 RTT 200 shield와 이 경계는 다르다: 2 Mbps·lead 3이면 참 RTT 약 178 ms(200 - 22.35), lead 0이면 약 194 ms부터 헛재전송이 생긴다(계산값).

- EV: quic-go/internal/utils/rtt_stats.go:17-18 DefaultInitialRTT 100 ms; 69-72 표본 없으면 PTO = 2·DefaultInitialRTT; 127-139 SetInitialRTT는 hasMeasurement를 바꾸지 않음
- EV: quic-go/internal/ackhandler/sent_packet_handler.go:909-929 PTO 시 numProbesToSend += 2; connection.go:2696-2733 sendProbePacket; packet_packer.go:319-328 클라이언트 Initial 패딩
- EV: p09_checks.py (a): 1-RTT 행의 initial_datagrams - first_flight_datagrams가 S_rtt200 2%·15% 전 팔에서 3(g3auto 4,480/4,481, g2auto 4,384/4,384, g3fixL2 2,248/2,248), S_bigcert 전 팔 1
- EV: padfec/policy.py:28 T_PTO_NO_ACK_MS = 200.86(같은 200 ms PTO의 실측); padfec3/learn3.py:17 SHIELD_RTT_MS = 200.0

PROPOSAL: (1) 비용 보고에 탐침을 포함한 전체 클라이언트 업링크 바이트(fecConn TxBytes)를 함께 싣는다. (2) shield 조건을 'RTT + τ(pre_decision_bytes) + c_proc >= 200 ms'로 바꾸거나 모형에 탐침 2장의 업링크 점유와 신용을 넣는다. (3) 보고서에 이 헛재전송은 quic-go 설정으로 못 끈다는 점(PTO 규칙이 hasMeasurement 전 고정)을 적는다.

EFFECT: RTT 200 층 업링크 비용이 약 2.5 KB 작게 보고되는 문제를 바로잡고 shield 경계를 quic-go 동작에 맞춘다.

VALIDATION: 저널에서 조건별 전체 업링크 바이트를 재집계하고, netem RTT 160~200 ms를 2 Mbps·lead 0/3으로 훑어 헛재전송 시작 RTT가 계산값(약 178/194 ms)과 맞는지 확인한다.

EFFORT: 작음 | CONF: 0.85 | IMPACT: 비용 지표와 shield 경계의 정확성

## A8-11 [algorithm/low] 1280(P_SERVER)과 k는 서버 설정, 난수 CID, KEM에 묶인 값이다: P는 클라이언트가 첫 서버 데이터그램 길이로 바로 잴 수 있다

CLAIM: (a) 서버 첫 비행 데이터그램 크기는 서버 Config.InitialPacketSize(기본 1280, 허용 1200~1452)로 시작하는 MTU discoverer 값이고, 클라이언트 max_udp_payload_size로만 줄어든다. 전송 매개변수를 처리하기 전에는 1200이지만 그때는 패딩 안 된 ACK만 나간다. PMTUD는 핸드셰이크 확인 뒤에만 시작하므로 DisablePathMTUDiscovery와 무관하게 첫 라운드는 P로 고정이다. ack-eliciting Initial은 P로 패딩되고 Handshake CRYPTO는 꽉 채워져 첫 라운드 데이터그램은 마지막 하나 빼고 정확히 P다. PAD-FEC의 양자화(A(B) = ceil(3B/P)·P, n_need, δ cliff)는 P = 1280 상수로 박혀 있어, InitialPacketSize를 바꾼 quic-go 서버나 다른 구현에서는 경계가 틀린다. 클라이언트는 첫 >=1200 B 서버 데이터그램 길이로 P를 그대로 관측한다. (b) ML-KEM ServerHello는 키 공유 1,120 B라 첫 Initial 패킷이 1280 - 128 = 1152 B를 넘어 Handshake와 코얼레스되지 않고 패딩된다. (c) k = ceil(CH / (W - 헤더 - 16 - CRYPTO 헤더))인데 클라이언트의 원래 DCID가 8~20 B 난수라 연결마다 용량이 12 B까지 흔들리고, 토큰을 실으면 약 91~103 B 준다(토큰 = salt 32 + nonce 12 + ASN.1 약 31~43 + 태그 16, 계산값). 테스트베드는 SNI가 없어 ClientHello scrambling이 꺼져 있다.

- EV: quic-go/connection.go:2868-2884 maxPacketSize(서버는 discoverer 전 1200); 2416-2448 applyTransportParameters가 InitialPacketSize로 discoverer 생성, 2438-2441 상대 max_udp_payload_size 상한; 2378 서버는 전송 매개변수를 즉시 적용; 994-996 PMTUD는 handleHandshakeConfirmed에서 시작
- EV: quic-go/config.go:42-46 1200~1452로 자름, 103-105 기본값; internal/protocol/params.go:11-12 InitialPacketSize = 1280
- EV: quic-go/packet_packer.go:319-328 패딩; 362 코얼레스 조건 size < maxSize - MinCoalescedPacketSize(params.go:88-90, 128)
- EV: goroot/src/crypto/mlkem/mlkem.go:26-30; goroot/src/crypto/tls/key_schedule.go:240-249 서버 키 공유 = 암호문 1088 + X25519 32
- EV: quic-go/internal/protocol/connection_id.go:60-69 원래 DCID 8~20 B 난수; internal/wire/extended_header.go:119-125; internal/handshake/token_protector.go:27-38 토큰 = salt 32 + GCM(nonce, 태그)
- EV: quic-go/crypto_stream.go:114-157 scrambling은 SNI 또는 ECH가 있을 때만
- EV: padfec/quantum.py:13 P_SERVER = 1280; experiments/quicbed/policy.go:13; padfec3/learn3.py:19; qamp.go:2049-2054 서버 Config에 InitialPacketSize 미설정

PROPOSAL: P를 목적지별 관측값(첫 서버 비행의 최대 데이터그램 길이, fecConn.ReadFrom에서 이미 보는 n)으로 학습하고 quantum, layout, policy3의 P_SERVER를 매개변수화한다. 검증 실험에 서버 InitialPacketSize = 1452 조건을 추가한다. 보고서 한계 절에 'SNI 없는 ClientHello, CID 4 B'를 적는다.

EFFECT: 서버 설정이 다른 환경에서 δ와 패리티 개수 판단이 틀리는 것을 막고, 일반화 질문에 소스 근거로 답할 수 있다.

VALIDATION: 서버 InitialPacketSize 1452로 S_bigcert를 측정해 첫 라운드 데이터그램 크기와 1-RTT 경계가 P = 1452 식과 맞고 P = 1280 고정 모형은 어긋나는지 비교한다.

EFFORT: 중간 | CONF: 0.8 | IMPACT: 일반화 범위

## A8-12 [code/low] Retry 경로는 테스트베드에서 한 번도 안 열렸다: Retry가 걸리면 첫 비행 패리티는 전부 낭비되고 연결 전 도착한 패리티마다 Retry가 또 나간다

CLAIM: quic-go 서버는 Transport.VerifySourceAddress가 true일 때만 토큰 없는 Initial에 Retry를 보낸다(무상태). 클라이언트는 첫 Retry 하나만 받아 토큰을 싣고 Initial을 다시 보내고, 서버는 Retry 토큰(IP, ODCID, RSCID, 수명 2·HandshakeIdleTimeout)이 유효하면 그 연결을 처음부터 검증된 주소로 다룬다. Retry는 항상 1 RTT를 더 쓰는 대신 한도를 없앤다. 이때 PAD-FEC 첫 비행의 신용은 쓸모가 없고, Retry는 상태를 남기지 않으므로 같은 DCID의 패리티 데이터그램(Initial형, >=1200 B, 토큰 없음)이 닿을 때마다 새 연결 시도로 처리되어 Retry가 추가로 나간다(클라이언트는 무시). 재시도 비행에서도 fecConn은 1200 B 이상 서버 데이터그램을 아직 못 받아 srvBig이 false라 첫 비행과 같은 패리티 배치를 또 보낸다. qamp 서버는 VerifySourceAddress를 설정하지 않아 이 경로는 측정되지 않았다.

- EV: quic-go/server.go:743-753 token == nil && verifySourceAddress(addr)이면 retryQueue; 901-958 sendRetryPacket; internal/handshake/token_generator.go:55-72 NewRetryToken
- EV: quic-go/server.go:663-677 validateToken(673 Retry 토큰 수명); config.go:17-23 maxRetryTokenAge = 2·HandshakeIdleTimeout; server.go:95-95 유효한 Retry 토큰이면 clientAddrVerified
- EV: quic-go/connection.go:1480-1518 클라이언트는 패킷을 받은 뒤의 Retry와 두 번째 Retry를 무시
- EV: quic-go/transport.go:110-119 VerifySourceAddress 문서('adds one additional network roundtrip')
- EV: qamp.go:2035 서버 Transport에 VerifySourceAddress 없음; 1214-1222 srvBig은 n >= 1200 서버 데이터그램 수신 시에만 true; 1170-1176 curLater 결정

PROPOSAL: fecConn.ReadFrom에서 Retry(롱헤더 type 3)를 감지하면 그 연결의 다음 비행을 복구 전용(lead 0, delta 0, 뒤 패리티만)으로 바꾼다. 실험 설계에 VerifySourceAddress가 켜진 서버 조건을 하나 넣어 PAD-FEC가 손해를 보지 않음을 확인한다.

EFFECT: Retry 서버 상대로 쓸모없는 업링크(첫 비행 패리티 m개와 재시도 비행 패리티)를 없애고 추가 Retry 송신 같은 부작용을 막는다.

VALIDATION: VerifySourceAddress가 항상 true인 서버로 v3 고정 팔을 돌려 서버 Retry 송신 수와 HCT(2·RTT + τ 기대)를 기록하고, 감지 로직 적용 전후 업링크 바이트를 비교한다.

EFFORT: 작음 | CONF: 0.7 | IMPACT: 배포 환경 견고성

- COMP: 모든 스크립트 위치: C:/Users/scien/AppData/Local/Temp/claude/C--Users-scien/3c292366-4266-4001-ba22-f5d1b25999cd/scratchpad/wf/audit-quicgo-source/ (python -I -B, C:/dev 아래 __pycache__ 생성 없음을 확인). WSL 조회는 같은 폴더의 s01_env.sh, s02_amp.sh와 read-only grep/sed.
- COMP: p02_scan.py (측정, p31 저널 25파일 124,800행): 연결별 path_rtt - netem RTT 중앙값 (RTT 50, 2 Mbps) lead0 +6.02(n=2206), lead1 +11.27(2524), lead2 +16.77(1990), lead3 +22.35(12014); 무제한 +0.95; (120,5) lead3 +9.18; (120,10) lead2 +3.73. policy_rtt - RTT 중앙 (50,2) +0.75, (200,2) +11.31, (120,5) +1.82, (120,10) +1.72, (80,10) +1.87 ms. 평균 패리티 > 1452 B 행 6개(g2auto, ips 1406).
- COMP: p03_lowrtt.py (측정): 2 Mbps에서 MinRTT inflation < 3 ms인 행은 HCT 258~281 ms의 PTO 경로 행(g3auto lead0 49행, g2auto 93행 등).
- COMP: p04_srvbytes.py, p06_hist.py (측정): server_bytes 중앙 D_p17_mbps2 10,991/10,993 B 대 D_p17_unlimited 10,949 B(+42 B); 'server_bytes - cert' 히스토그램 2 Mbps g2auto 1970~1990 B 3,996/4,027행, 무제한 g2auto 1930~1950 B 4,432/4,444행.
- COMP: p05_preack.py (측정): 상대 임계값 분류는 ±15 B 산포 때문에 부정확해 최종 판단은 p06 히스토그램으로 대체(10 Mbps H·R 조건도 1890~1910 B 군집 94~99.8%).
- COMP: p07_ctx.py (측정): S_bigcert k_hat 2, s_hat 18,231, n_need 15, 주 행동 (0,3,1)(2% 4,372회, 15% 2,405회)과 (0,0,4)(15% 1,885회); S_rtt200 s_hat 10,992, n_need 9, (0,2,2) 위주, policy_rtt 중앙 211.31.
- COMP: p08_hctclusters.py (측정): S_bigcert 15% g3fixL3 fast 0.576/79.9 ms, 2rtt 0.375/130.9, slow 0.049/310.8, slow이면서 Initial 재전송 없음 0.008/303.7; S_rtt200 전 팔 'client retx' 1.000.
- COMP: p09_checks.py (측정+모형): 1-RTT 행 extra Initial 데이터그램 S_rtt200 = 3, S_bigcert = 1; ML-KEM k=2(W 1280/1281/1406), x25519 k=1; decide_core 점질량 사후로 RTT 200 대 211.31에서 행동 동일, J_pred +11.53/+11.70 ms; bin_needed_s(S) != bin_needed_s(S+41) 비율 0.0307, sealed 8개 S 모두 불변.
- COMP: m01_holdlead.py (모형 세계): 전부 선행 + 보류 디코더 변형 대 현행 최선. S_bigcert p=0.15 103.42 -> 90.09 ms, p=0.02 +1.81 ms 악화(뒤 패리티 없는 변형의 t_dec 증가 때문).
- COMP: m03_combined.py (모형 세계): 같은 순서·바이트에서 선행 심볼을 복구에도 쓰는 보류 변형. 모든 후보에서 악화 0; S_bigcert p=0.05/0.10/0.15 -2.14/-7.93/-13.33 ms, P_fail 0.0607 -> 0.0004; H_c12000_u5 p=0.15 -15.03; S_rtt200 -2.90; H_c6000_u10 -3.52.
- COMP: m02_timer_infl.py (모형 세계): 실패 비용 타이머를 부푼 RTT(+22.35 ms)로 계산하면 S_bigcert (0,3,1) p=0.15 dJ +1.88 ms, p=0.02 +0.04 ms; H 조건 +0.23 ms.
- COMP: m04_info.py (모형 세계): 연결당 Fisher 정보. S_bigcert (0,0,4) y 정보 0(P(y=1)=0.990), 원본 도착 1비트 51.0/21.1/11.1/7.8 (p=0.02/0.05/0.10/0.15); (0,3,1) y 134.0/62.8/35.0/24.7; H_c12000 (0,3,1) y 4.36/13.04/17.64/18.08.
- COMP: 손계산: 서버 ACK 전용 Initial = 헤더 20(1+4+1+4+1+4+1+2+2) + ACK 5 + 태그 16 = 41 B; 토큰 크기 약 32 + 12 + 31~43 + 16 = 91~103 B; 토큰 연결 서버 pacing 간격 = 1280 / (1.25·40960/RTT) = RTT/40; strict 서버 경계 이동 최대 1280/3 ≈ 427 B; 헛 PTO 시작 RTT = 200 - inflation(lead 3: 약 178 ms, lead 0: 약 194 ms); 업링크 역산 1,331·8/5.44 ms = 1.96 Mbps, 1,331·8/2.19 ms = 4.86 Mbps.
- Q: 실제 브라우저와 HTTP/3 클라이언트가 NEW_TOKEN을 저장해 쓰는지, 주요 서버(CDN)가 토큰으로 증폭 한도를 푸는지는 이번 범위(quic-go 소스) 밖이라 확인하지 않았다. A8-01의 실제 영향 크기를 정하려면 외부 확인이 필요하다.
- Q: 1-RTT HCT의 손실 무관 상수 약 3.6 ms(S_bigcert)의 원인: quic-go pacing은 소스로 배제했지만 서버 TLS 계산, 클라이언트 인증서 처리, WSL 스케줄링 중 무엇인지는 미확인이다.
- Q: 보류 디코더(A8-02)에서 마지막 원본 유실 판정 타이머(τ(W)+1 ms)가 netem 지터와 CPU 부하에서 안전한지, 재정렬이 있는 경로에서 오판이 얼마나 생기는지는 실측이 필요하다.
- Q: 드문 깨끗한 RTT 표본(+0.7 ms)과 'Initial 재전송 없는 느린 HCT'가 클라이언트 anti-deadlock Handshake PTO 탐침에서 온다는 해석은 소스와 HCT 군집에서 나온 추론이다. qlog로 직접 확인하지 않았다.
- Q: 키 대기 큐 재처리 이중 계상(A8-04)은 소스 읽기로만 확인했다. 저장소 밖 재현 시험과 upstream 보고를 누가 언제 할지 팀 결정이 필요하다.
- Q: A8-09의 '사전 ACK가 원본별 물리 도착을 드러낸다'는 전제에서, 마지막 원본의 복구 여부를 첫 응답 지연 τ(P)로 구별하는 부분은 10 Mbps(τ(P) 약 1.1 ms)에서 서버 처리 지터와 겹칠 수 있다. 대역별 판별력은 미측정이다.
