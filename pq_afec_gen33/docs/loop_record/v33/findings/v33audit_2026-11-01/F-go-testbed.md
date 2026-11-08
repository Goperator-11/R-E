# F-go-testbed

## summary
직접 확인한 것: gen33 원본을 WSL 임시 복사본(/home/scien/v33audit_tmp/F, 끝난 뒤 삭제)에서 go vet을 돌려 경고 0, go test는 231 PASS·2 SKIP, go test -race는 경합 0으로 끝났다. SKIP 2개(M1 와이어 관문)는 Codex가 보관한 M1_wire_reference_02.tsv.gz(sha 59b34347…, Codex가 적은 값과 같다)를 넣고 따로 돌렸고, basic ReadFrom과 oob ReadBatch 각각 700116사례가 통과했다. -trimpath 빌드를 GOCACHE를 바꿔 두 번 했더니 SHA-256 41424293…로 같았고, ~/quicbed_gen33/bin/qamp.sha256과도 일치했다. srcsha 9798aa22도 HEAD 소스와 맞는다. 인증서는 별도 프로세스 두 번 생성에서 2955·6000·16000 B 모두 바이트 단위로 같았다. Go 코드 품질은 기준선보다 분명히 좋아졌다. 복호기를 연결별로 색인하고 상한을 두었고, 오래된 타이머가 새 묶음을 내보내던 문제를 막았고, 클라이언트 수신 필터를 넣었고, 같은 바이트 비교 팔과 토큰·resumption 팔을 만들었다. 측정 전에 고칠 결함은 네 가지를 재현했다. (1) 서버 C1 회신이 판본3으로만 나가서 동결 v3.1·gen-2 클라이언트 파서가 받지 못한다. (2) 주기 stats에서 conns가 빠졌고 계정이 완료 10초 뒤 만료되므로, 기존 하네스(g3bed new_conns, p13)로는 연결별 서버 기록을 얻을 수 없다. (3) lead-hold를 켜면 복구 불가 비행의 선행 패리티가 TTL에 버려져 증폭 신용으로 들어가지 않는다. hold를 끈 경로는 바로 신용으로 넣는다. (4) 사소한 결함으로, 비교 팔(pad/dup)에서 drop-parity 주입의 C1 장부가 어긋난다. 이밖에 기본값 변경 5종(udp-path oob, retrans-layout original_first, feedback-wait 1초, 정확 크기 인증서, 클라이언트 qlog tracer 상시 켬)은 하나씩은 D23·D25·D26·D28·T1·T4 문서에 적혀 있다. 하지만 v3.1 봉인 조건과 맞추는 표와 T7 러너는 아직 없다. original_first는 비용 모형(J3 blocked, J4 todo)보다 먼저 기본값이 되었다. 모든 X 측정이 아직 실행되지 않았으므로 성능 개선은 미확인이다.

## verdict_improved
테스트베드의 기능·견고성·재현성은 v3.2-dev 기준선보다 발전했다. 근거는 위 improvements의 직접 확인 결과다. 재현 빌드가 배포 바이너리와 일치하고, vet·test·race가 깨끗하고, 700116사례 와이어 관문이 두 경로 모두 통과하고, 인증서가 결정적이고, 복호기 색인과 상한, 오래된 타이머 차단, 같은 바이트 비교 팔과 재방문 팔이 생겼다. 다만 "측정에 그대로 쓸 수 있는 상태"는 아니다. 측정 전에 고칠 것을 우선순위로 적는다. (1) F1: C1 판본 호환을 해결하거나 세대가 섞인 공통 서버를 금지한다. (2) F2: 서버 연결별 기록 내보내기를 만든다. (3) F4: T7 러너에서 udp-path·retrans-layout·feedback-wait·cert-file을 명시해 v3.1 봉인 조건과 맞추고, tracer 비용을 A/A로 잰다. original_first와 비용 모형의 불일치(J3·J4)도 정리한다. (4) F3: hold 켬 팔을 측정하기 전에 TTL 폐기 성질을 재설계하거나 해석에 반영한다. (5) F5·F6은 주입 장부와 분할 표시를 보강한다. HCT 개선은 어떤 Go 변경에 대해서도 아직 재지 않았으므로 '성능이 나아졌다'고 말할 근거는 없다.

## frame_fit
대체로 연구 틀에 맞는다. T3(pad_junk·dup·k-inflate)는 '같은 바이트를 패딩 대신 패리티로'라는 신규성 주장을 직접 시험하는 X1의 전제다. T2(NEW_TOKEN·resumption·Retry)는 볼트의 '쓰면 안 되는 말'(토큰·resumption 단서 없는 재방문 이득)을 해소할 X4 기준선이다. T1은 증폭 경계 근처의 인증서 길이 잡음을 없앤다. T4의 C1 판본3과 qlog는 10-29 감사의 1순위 처방(데이터그램 단위 도착 증거)에 맞는다. M4 guard는 주소가 검증되면 증폭 한도가 풀리므로 선행 패리티를 0으로 둔다. '패리티의 값어치는 증폭 신용'이라는 틀과 정합한다. 어긋나는 점은 M1 hold다. 볼트는 '같은 바이트가 신용과 복구를 함께 산다'를 쓰면 안 되는 말로 두었는데 hold는 그 기제를 노린다. 게다가 복구가 불가능해지면 선행 패리티의 신용 자체를 TTL에 버린다(F3). hold 팔 결과로 그 주장을 하면 안 되고, 현 설계는 연구 전제에서 불리한 방향이다. Codex 문서는 대부분 '성능 효과 미확인'으로 적어 틀의 과장 금지를 지켰다.

## errors

### F1 [high] C1 회신 판본3이 동결 v3.1·gen-2 클라이언트와 호환되지 않음 (repro=True)
gen33 서버는 C1 회신을 fbVer=3으로만 만든다. 복원 CRC 목록 1바이트와 4×n바이트가 붙어서 나간다. 동결 v3.1(pq_afec_gen31 qamp.go:714,840)과 gen-2(pq_afec qamp.go:721)의 parseFeedback은 b[4]==2이고 blen==12+4*nc일 때만 받는다. T7이 T1 문서의 권고대로 gen33 공통 서버를 v31auto·g2auto 팔에 같이 쓰면서 -feedback을 켜면 문제가 생긴다. 옛 클라이언트는 회신을 서버 데이터그램으로 세어 countRx·srv_bytes가 약 51 B 늘어난다. C1은 '회신 없음'이 된다. gen-2에서는 HCT가 3×base를 넘으면 C2 전멸 추론으로 캐시가 비관 쪽으로 기운다. 어디에도 경고나 오류가 나지 않는다. 문서는 'gen33 클라이언트가 판본2를 읽는다'는 방향만 적었고, 서버에서 옛 클라이언트로 가는 방향의 비호환은 docs·DECISIONS 어디에도 없다.

EVIDENCE: qamp.go:715 const fbVer = 3, buildFeedback가 byte(fbVer)를 기록. gen31 qamp.go:840 `b[4] != fbVer`(=2)이면 nil. 재현: gen33 buildFeedback 출력을 gen31 parseFeedback 복사본에 넣는 임시 Go 시험(scratchpad gotests/zz_audit_feedback_compat_test.go). 결과 'gen33 feedback bytes=51 gen33=true v31copy=false'. gen31 qamp.go:1216-1223에서 parseFeedback==nil이면 countRx(n)를 탄다.

FIX: 서버에 -feedback-version 2|3 플래그를 두거나(판본2는 복원 목록 없이 기존 형식), T7에서 세대가 다른 클라이언트와 gen33 서버를 -feedback으로 섞지 못하게 막고 문서화한다.

### F2 [medium] 서버 연결별 기록(conns)을 측정 하네스가 더는 얻을 수 없음 (repro=True)
T5 이후 주기 stats(100 ms)는 report(false)로 써서 conns를 비운다. 계정은 핸드셰이크 완료나 종료 10초 뒤 만료되어 s.conns에서 지워진다. SIGTERM 최종 stats에도 최근 10초 안의 연결만 남는다. 기존 하네스 g3bed.new_conns(before/after, g3bed.py:336-344)와 p13_beff·p14_dominance는 conns에서 연결별 B_eff·TxSizes·TxRxTimeline을 읽는다. 이 값들이 조용히 빈 목록이 된다. T5_boundary_result는 '주기 스냅숏에는 전체 연결 표를 넣지 않았다'를 사실로만 적었고, 하네스가 깨진다는 점과 대체 수집 경로는 적지 않았다. T1 결과에서 '연결별 서버 첫 비행 패킷 수·크기 자료가 없어 미확인'으로 남은 공백이 X 측정에서도 메워지지 않는다.

EVIDENCE: qamp.go:2736 writeStats(false), :2743 writeStats(true), boundary.go:16 accountRetention = 10s. 재현: WSL loopback에서 서버(-fec on -feedback -udp-path oob)와 클라이언트 n=3. 주기 stats는 'conns 0, conn_acct_live 3'이었고, 11초 뒤 SIGTERM 최종 stats는 'conns 0, conn_acct_expired 3'이었다.

FIX: 계정 만료나 완료 때 연결 기록을 JSONL로 한 줄씩 추가하는 내보내기를 만들거나, 블록 경계 신호에서 conns 전체를 쓰게 한다. T7 러너가 이 경로를 쓰게 한다.

### F3 [medium] lead-hold에서 복구 불가 비행의 선행 패리티 신용이 TTL에 폐기됨 (repro=True)
hold 모드는 선행 패리티를 보류한다. 결정이 열린 뒤에도 남은 심볼이 누락 수보다 적으면 계속 보류한다(hold.go:152-155). 1초 TTL이 되면 'expired'로 버리고(hold.go:339-342) 스택에 넘기지 않는다. 첫 묶음 원본을 잃어 클라이언트가 PTO로 CH를 다시 보내는 경로가 바로 증폭 예산이 중요한 경로다. 이 경로에서 hold를 켠 팔은 끈 팔보다 신용이 패리티 하나 몫(재현에서 1246 B, 서버 송신 허용량 약 3.7 KB) 적다. M1 계약 문서에는 'TTL 시각에는 보관분을 정확히 한 번 폐기'로 적혀 있어 계약 위반은 아니다. 다만 연구 전제(패리티의 값어치는 증폭 신용)와 어긋나는 설계이고, X6 계획에는 'v33auto 보류 복호 켬' 팔이 있다. 메타데이터 충돌·중복 index 패리티를 신용으로 넘기지 않고 버리는 것도 같은 성질이다(hold.go:370-373, 430-435). legacy 경로는 이런 패리티를 신용으로 넘긴다.

EVIDENCE: 임시 시험 zz_audit_hold_credit_test.go(leadBuildFlight lead1·m2·k2, L0만 도착, 200 ms 뒤 새 CH 원본 2개). hold는 'leadReturned=false BytesIn=3596 BytesToStack=2350 HoldExpired=1246 CreditParities=0', hold 없음은 'leadReturned=true BytesToStack=3596 CreditParities=1'.

FIX: 결정이 열렸는데 복구가 불가능해지면(같은 연결의 새 묶음 도착이나 기한 경과) 쓰지 않은 보류 패리티를 신용으로 내보낸다. 이 성질을 M1 세계 모형과 X6 hold 팔 해석에 반영한다.

### F4 [medium] 측정 조건을 바꾸는 기본값 5종이 T7 전에 바뀌었고, v3.1 봉인 조건 대응표가 없음 (repro=True)
서버 -udp-path 기본값이 oob다(qamp.go:3708). v3.1 서버는 SyscallConn이 없어 basicConn을 탄다. 그래서 SO_RCVBUF 7 MB·DF·ECN·PKTINFO·핸드셰이크 뒤 GSO가 달라진다. -retrans-layout 기본값은 original_first다(:3715). v3.1의 응답 전 후속 묶음은 repeat 모양이었다. Codex가 RTT200 고정 팔에서 잰 연결당 패리티 바이트는 7961~7991 대 11940~12020이다(T6_result 기록 값). -feedback-wait 기본값은 1초다(:3714, 이전에는 고정 200 ms). 회신을 잃으면 연결 간격과 srv_bytes 수집 창이 달라진다. 인증서 DER은 2955 B로 정확하다. v3.1은 2962 B 내외였다(T1 기록). 클라이언트 qlog tracer는 조건 없이 항상 켜진다(:3006). 하나씩은 D23·D25·D26·D28·T1·T4 문서에 적혀 있다. 하지만 T7(todo)이 없어서, 지금 플래그 없이 gen33을 돌리면 봉인 조건과 다른 측정이 된다. 그리고 original_first는 auto3 비용 모형(layout.evaluate·p3Evaluate)이 반영하지 못한 채 기본값이 되었다. T6 문서 스스로 '재전송 보호를 명시하지 않은 기존 실패 근사'라고 적었고, J3는 blocked, J4는 todo다. 그래서 auto3는 와이어와 다른 모형으로 행동을 고르게 된다.

EVIDENCE: 직접 확인: loopback smoke 행에서 retrans_layout=original_first, 서버 stats에서 udp_path=oob_readmsg_batch1, udp_gso_calls=3·segments=3을 봤다. qamp.go:3708/3714/3715/3006. LOOP_STATE에서 T7 todo, J3 blocked, J4 todo.

FIX: T7 러너가 -udp-path, -retrans-layout, -feedback-wait, -cert-file을 행마다 명시하고 기록하게 한다. v31auto와 비교하는 블록은 basic·repeat_first·200ms로 맞춘다. tracer 비용은 A/A로 잰다. J3·J4가 T6 모양을 반영할 때까지 auto3 팔에 repeat_first를 쓸지 정한다.

### F5 [low] pad/dup 비교 팔에서 drop-parity 주입의 C1 장부가 어긋남 (repro=True)
emit에서 dropParity 분기가 kind 검사보다 먼저 ffParCRC에 CRC를 넣는다(qamp.go:1535-1537). 실제로 보낸 pad/dup 슬롯은 넣지 않는다(:1566-1575). 그래서 pad_junk 팔은 버린 슬롯만 '보냈으나 잃음'으로 세고, dup 팔은 원본과 같은 CRC가 겹쳐 trunc(검열)이 된다. checkComparisonFlags는 corrupt-parity만 막고 drop-parity는 막지 않는다.

EVIDENCE: 임시 시험 zz_audit_drop_compare_test.go(m2·lead1·k2, dropParity=0). 결과: parity는 sent=4, pad_junk는 ffParCRC=1·sent=3·lost=1, dup은 sent=3·trunc=true·reason=truncated_or_ambiguous_crc.

FIX: kind가 parity가 아니면 dropParity 분기에서 ffParCRC를 갱신하지 않게 하거나, pad/dup에서는 drop-parity를 거부한다.

### F6 [low] cached_k 과소 추정에 의한 첫 묶음 분할을 표시하지 못함 (repro=False)
cached_k가 실제 k보다 작으면 첫 묶음이 일찍 끝나고, 남은 원본은 pre_response_followup(original_first, L=0)으로 따로 나간다. C1 첫 비행 증거도 앞부분만 덮는다. split_suspected는 '실제<예상'일 때만 켜지므로 이 경우는 잡지 못한다. 반대 경우(타이머 해제)에만 이름이 '분할 의심'으로 붙는다. 이 한계는 T5_timing_contract에 적혀 있다.

EVIDENCE: flight_trace.go:83 SplitSuspected: expected>0 && len(fl)<expected, flight_input.go:206-211 첫 묶음 뒤 expected=0. qamp_flight_input_test.go:107-130이 k=1 과소 추정에서 Flights=2를 시험하지만 플래그는 시험하지 않는다.

FIX: 첫 묶음이 expected_k로 해제된 직후 parityDelay 안에 시작된 후속 묶음을 split으로 표시하고, 그 연결의 C1 학습 입력은 검열한다.

### F7 [low] build_gen33.sh가 stage를 지우지 않아 디스크가 계속 늘어남 (repro=True)
cleanup trap을 지우고 GOTMPDIR(-work)를 포함한 stage를 보존한다. 빌드할 때마다 수십 MB씩 쌓인다.

EVIDENCE: git diff 90859b973 HEAD -- build_gen33.sh(trap cleanup 삭제, 'preserved build stage'). 읽기 전용으로 확인한 결과 ~/quicbed_gen33/stage.* 53개, 디렉터리 전체 3.9G.

FIX: 영수증(build_record)만 남기고 go-work는 지우거나, 보존 개수에 상한을 둔다.

### F8 [low] 보고된 Go 시험 수에서 M1 와이어 관문 2개가 SKIP이라는 사실이 빠짐 (repro=True)
표준 빌드(build_gen33.sh)는 M1_REFERENCE_GZIP을 주지 않는다. 그래서 TestHoldPythonReadFromReference·TestUDPHoldPythonReadBatchReference는 SKIP이다. MORNING_REPORT의 'Go231 통과'에는 SKIP이 드러나지 않는다. 내가 저장된 gzip으로 돌리니 둘 다 통과했으므로 결함 자체보다는 보고 방식의 문제다.

EVIDENCE: ~/quicbed_gen33/bin/go_test.txt에서 PASS 231·SKIP 2를 읽기 전용으로 확인. qamp_hold_test.go:593-595. 내 실행 결과는 '700116 actual decoder cases, 60 configurations ... match Python'이 두 경로 모두 PASS(56 s).

FIX: 빌드 스크립트가 보관된 기준 gzip 경로를 넘겨 관문을 항상 돌리거나, SKIP 수를 영수증과 보고에 명시한다.

## changes
- experiments/quicbed 변경: 57파일 +8834/−526. 이 폴더를 건드린 커밋은 19개다. 내 갈래 범위는 T1 60a2f18f9, T4 160d1c0cd, T5 b717eb434·e860f3060·a1efdffea·de9ae70ea·ed15ecd13, T6 11963066f, T3 b69e02a93·f6f10018a, T2 f9fe00bd3, M1 21cd5334e·98f9f116b·658490a1d, M4 1003e14ff이고, 나머지는 S3·S4·E12·J7이다.
- T1 certificate.go: 고정 seed P-256 키와 RFC6979 서명으로 DER 길이를 certsize에 정확히 맞춘다. -mode certgen, -cert-file(PEM 공유), -dry-run을 추가했고, 서버 stats와 로그에 CERT_META를 남긴다. 기존 makeCert(무작위 키·filler)를 대체했다.
- T2 revisit.go: -token-store(프로세스 LRU 16/4), -resume(서버 SessionTicketsDisabled=!resume), -verify-source(항상 Retry), -revisit-wait 200ms를 추가했다. 기본값은 모두 꺼짐이고 고정 FEC 모드에서만 허용한다.
- T3 comparison.go·inflation.go·padfechook/: -pad-junk는 패리티 슬롯을 같은 크기의 JUNK Initial로 바꾸고, -dup은 슬롯 j에 원본 j mod k의 사본을 보낸다. -k-inflate(0~8192 B)는 TP 9730으로 ClientHello를 키우며 off·buf에서만 허용한다. padfechook은 모듈 경로 github.com/quic-go/quic-go/padfec-local-hook로 quic-go internal/wire.AdditionalTransportParametersClient를 한 번만 설정한다. go.mod에 replace를 넣었다.
- T4 observation.go: C1 판본을 2에서 3으로 올려 수신 CRC와 복원 CRC를 따로 보낸다. 클라이언트 메모리 qlog tracer(ACK range·CRYPTO·RTT·PTO 하한)를 항상 켠다. arrivals·c1 행, unrecoverable_final·flights_finalized를 추가했다. -feedback-wait 기본 1s(이전 200ms 고정)를 넣었다. gen-2 auto의 '회신 없음이면 전멸' C2 추론을 없앴다(D13).
- T5 boundary.go: 클라이언트는 peer와 자기 CID인 서버 패킷만 받는다(clientCIDGenerator 4B). 서버 응답 전에 Initial이 아닌 롱헤더를 쓰려 하면 WriteTo 오류를 낸다. connAcct는 LRU(4096)와 완료·종료 10초 뒤 만료로 관리한다. 주기 stats에서 conns를 뺐다.
- T5 decoder_index.go: 원본·비행 색인을 (DCID, 계정)으로 바꾸고 상한을 두었다. 최근 원본은 전체 512·그룹별 64, 비행은 1024·그룹별 8, 비행당 32768 B, 전체 8 MiB, 여유 65535 B다. 이미 본 원본이 밀려나면 그 비행을 poison하고, 메타데이터가 다른 패리티는 신용으로 통과시킨다.
- T5 udp_linux.go: 서버 -udp-path 기본값을 oob로 바꿨다. ReadMsgUDP·WriteMsgUDP·ReadBatch(한 번에 1개)·SyscallConn을 노출하고, GSO segment별로 계정을 매기고, 송신 실패 시 롤백하고, 복원본과 C1에 PKTINFO를 붙인다.
- T5 flight_input.go·flight_trace.go: auto3에서 명시 -expect-k가 없으면 cached_k를 첫 묶음에만 적용한다. 타이머 세대 번호로 오래된 콜백의 flush를 막는다. 묶음별 trace(최대 128개)를 남긴다.
- T6 flight_shape.go: -retrans-layout 기본값을 original_first로 바꿨다. v3 응답 전 후속 묶음은 L=0·T=min(1,m)으로 나가고, repeat_first를 주면 이전 모양을 재현한다.
- M1 hold.go: -lead-hold(기본 꺼짐), -lead-hold-uplink-kbps 2000, -lead-hold-margin 1ms를 추가했다. 수신자 기한, 보류 복구, TTL 1초 폐기를 구현했고 SetReadDeadline·Close를 가로챈다.
- M4 revisit_guard.go: -revisit-guard와 -decoder-support를 추가했다. 토큰이나 Retry가 있으면 lead를 0으로 두고, 추가 묶음은 한 번만 허용한다.
- build_gen33.sh: -trimpath, -buildvcs=false, GOPROXY=off, GOSUMDB=off를 넣었다. padfechook vet·test를 돌리고 go version -m 기록을 남긴다. stage를 보존하는 쪽으로 바꿨다. 다른 build*.sh는 비활성 문구만 gen33으로 바꿨다.

## improvements
- [strong] 재현 빌드와 배포 바이너리 일치 :: 직접 확인: GOCACHE를 바꿔 두 번 빌드한 SHA-256이 41424293588f…로 같고 ~/quicbed_gen33/bin/qamp.sha256과 일치한다. HEAD 소스로 계산한 srcsha 9798aa226a1a…도 qamp.srcsha와 일치한다.
- [strong] 시험 범위가 넓어졌고 경합이 없음 :: 직접 확인: go vet 경고 0, go test 231 PASS·2 SKIP, -race 경합 0(73 s). 저장된 기준 gzip(sha 59b34347…)으로 basic ReadFrom과 oob ReadBatch 각각 700116사례·60설정이 PASS. 기준선 S0의 Go 시험은 101개였다(MORNING_REPORT 기록).
- [strong] 결정적 정확 크기 인증서 :: 직접 확인: 2955·6000·16000 B dry-run 출력이 별도 프로세스 사이에서 같았고, PEM 파일 두 개의 sha 783e80e8…도 같다. 이전 생성기는 2962 B 내외였다(T1 기록 값). 팔 사이 인증서 길이 차이라는 체계 오차를 없앤다.
- [strong] 같은 바이트 비교 팔과 재방문 팔을 확보함(X1·X4의 전제) :: comparison.go:55-68의 pad_junk는 패리티와 같은 크기다. quic-go가 복호 전에 바이트를 세는 지점(connection.go:1052)을 확인했으므로 같은 신용을 받는다. k-inflate는 TP로 실제 CH를 키운다. token·resume·Retry 팔도 있다. 연구 신규성(패딩 대신 패리티)을 직접 재는 데 필요한 장치다. 실제 측정은 아직 없다.
- [moderate] 오래된 타이머가 새 묶음을 조기 해제하는 문제를 차단 :: qamp.go flushFlightFor의 세대 비교, WriteTo의 timerGeneration. 기준선에는 세대 구분이 없었다. 관련 시험은 race 포함 전부 통과했다.
- [moderate] 복호기 색인과 메모리 상한 :: 기준선은 패킷마다 s.recent와 s.flights 전체를 선형 탐색했고(qamp_base.go pendingErasures·tryRecoverLocked·noteOriginal) 상한이 없었다. 지금은 (DCID, 계정) 키 조회와 개수·바이트 상한을 쓴다. 상한 산술을 검토한 결과 m≤4·symLen≤1472에서는 비행당 상한에 닿지 않는다. 연결 간 원본 공유도 막았다.
- [moderate] 학습 입력에서 거짓 손실을 줄임 :: C1 판본3이 물리 수신과 복원을 나눠 보낸다(observation.go:196-249). '회신 없음 + 느린 HCT = 전멸' 추론을 없앴다(D13). 회신 유실을 손실로 세던 편향이 사라진다. 효과 크기는 미측정이다.
- [weak] 서버가 quic-go의 OOB 경로를 쓰게 됨 :: 직접 확인: smoke에서 udp_path=oob_readmsg_batch1, gso_calls=3·segments=3. quic-go v0.61 connection.go:2536-2552를 보면 핸드셰이크 확정 전에는 gsoSize 0으로 하나씩 보내므로 핸드셰이크 구간의 netem 손실 단위는 그대로다. 성능 효과는 X3 전까지 미확인이다.
- [weak] 파서 경계 검사와 송신 회계 롤백 :: hasHandshake의 토큰·길이 경계 검사, parseFeedback의 정확 길이 검사, serverWrite의 실패 송신 롤백(udp_linux.go:227-261).

## checked_but_ok
- padfechook: Configure는 한 번만 실행되고 값을 바꾸면 거부한다. 0~8192 범위를 검증한다. TP 9730=27+31×313은 GREASE ID다. PerspectiveClient에서만 붙는다(padding_test). qamp 시험 중에 전역 훅을 켜는 것은 없다. internal 패키지 접근은 import 경로 접두 규칙을 이용한 것이며 vet·build·race가 통과했다.
- 인증서 결정성: 키 seed, 날짜, serial, filler가 고정이고, 인증서 서명은 Sign(nil)이라 Go 1.26에서 RFC6979로 결정적이다. CertificateVerify는 연결마다 무작위라는 한계가 D22에 적혀 있다.
- 잠금 순서: c.mu 다음 observer.mu 순서로 잡는다. memoryTrace.RecordEvent는 observer.mu를 푼 뒤 onRetry를 부르므로 역순 잠금이 생기지 않는다. WriteTo의 writeMu와 타이머 flush 사이에도 교착이 없다. -race로 확인했다.
- parseFecBlock은 심볼을 복사하므로(qamp.go:1000) quic-go 버퍼를 재사용해도 보류 심볼이 오염되지 않는다.
- 서버 Tracer connID는 ODCID다(quic-go server.go:804-810). acctLocked가 클라이언트 DCID를 serverCIDs에 묶으므로 accountTracer 조회가 맞다.
- quic-go는 복호 전에 수신 바이트를 센다(connection.go:1052). 그래서 pad_junk·dup·패리티 모두 증폭 신용이 된다.
- 핸드셰이크 확정 전에는 quic-go가 GSO를 쓰지 않는다(connection.go:2536-2552). 따라서 oob 기본값이 netem의 핸드셰이크 구간 손실 단위를 바꾸지 않는다. smoke의 GSO 분절 수도 호출 수와 같았다.
- basic 경로 의미: 상한과 경계 검사를 빼면 기준선과 같다. 700116사례 basic 관문 PASS로 확인했다.
- D5: gen33의 gen-2 auto 경로 변경(S4 이식, C2 제거)은 동결 d98b05d7 바이너리 비교에 영향이 없다.
- D26: 명시 -expect-k가 여전히 최우선이다. v3.1 하네스는 명시값을 넘긴다(g3bed.py:360, g3_m1confirm.py:601). 따라서 그 실행 방식에서는 cached_k가 끼어들지 않는다.
- feedback-wait: HCT는 대기 전에 고정된다(runClient). 대기 한도와 실제 대기 시간이 행에 기록된다(smoke의 feedback_wait_ns 372~390 ns 확인).
- hold의 기한·TTL·heap: 계약과 일치하고, 계약이 정한 사례 전수는 Python 기준과 바이트·회계가 일치한다(직접 실행).
- 저장소 무결성: 검증 뒤 git status가 깨끗했다. __pycache__와 .pytest_cache도 생기지 않았다. WSL 임시 디렉터리 F는 삭제했다. ~/quicbed*는 ls·du·cat으로 읽기만 했다.
- Codex 이전부터 있던 한계(Codex 변경 아님): quic-go가 1452 B 버퍼로 읽기 때문에(sys_conn.go:120, sys_conn_oob.go:168) 1452 B를 넘는 패리티는 잘린다. 문서는 1472 B까지 다룬다고 쓰지만, 잘린 데이터그램은 원본으로 처리되어 신용이 물리 바이트를 넘지 않는 안전한 방향이다.
- 직접 재현하지 않은 것: Python 기준 생성기(hold_wire_reference.py)를 다시 돌리지는 않았다. Codex가 보관한 gzip과 Go의 일치만 확인했다. T5 CPU 미시 대조 수치와 relay 바이트 일치는 Codex 문서에서 읽은 값이다.

## VERIFY

- F1 (error): **partly** sev=medium :: 비호환 자체와 srv_bytes 부풀림은 직접 재현했다. 그러나 '서버에서 옛 클라이언트로 가는 방향의 비호환은 docs·DECISIONS 어디에도 없다'는 주장은 틀렸다. docs/c1_status.md:7(커밋 b717eb434, HEAD에 있음)에 '동결된 판본2 클라이언트는 판본3 회신을 이해하지 못하므로 T7에서 피드백 호환성을 별도로 다뤄야 한다'고 적혀 있다. 문서에 빠진 것은 '옛 클라이언트가 회신을 서버 바이트로 센다'는 결과뿐이다. 봉인 v3.1 러너(g3bed.start_server)는 -feedback을 쓰지 않았고, 기존 하네스는 팔(tag)마다 서버와 포트를 따로 띄운다(g3bed PORTS[tag]). 그래서 이 문제는 T7이 -feedback을 켠 gen33 공통 서버를 고를 때만 생긴다. 잠재 위험이고 T7 과제로 이미 적혀 있으므로 high는 과장이다. || 코드: gen33 qamp.go:715 const fbVer = 3, :734 byte(fbVer). gen31 qamp.go:714 fbVer=2, :840 b[4] != fbVer이면 nil, :1216-1223 parseFeedback==nil이면 countRx(n). gen-2 qamp.go:721·847이 같고, :2570의 C2(hct > 3*base) 경로도 확인했다. 내 Go 시험(zzv_audit_test.go, WSL 임시 복사본): gen33 buildFeedback을 gen31 파서 복사본에 넣으면 nc=0~6, nrec=0~1의 모든 경우에서 'version' 사유로 거부된다. nc=4·nrec=0일 때 길이는 51 B다. 종단 재현(loopback): gen33 서버 -feedback과 동결 ~/frozen/g3c_6baf2b52 클라이언트 n=4를 붙이면 fb_recv 0, fb_magic_seen 4, server_bytes 4859/4872/4862/4870이었다. v3.1 서버와 v3.1 클라이언트는 fb_recv 4, server_bytes 4825/4841/4826/4823이었다(약 +37 B). -feedback 없는 gen33 서버는 4825~4829였다.

- F2 (error): **confirmed** sev=medium :: 직접 재현했다. 기준선의 주기 stats는 s.conns 전체를 넣었다(기준선 qamp.go report(), 주기 writeStats). HEAD는 주기 기록에 report(false)를 쓰고, 계정은 완료나 종료 10초 뒤 report() 안의 expireAccountsLocked가 지운다. 대체 내보내기 플래그는 없다(flag 목록에 conn/log/export류 없음). 다만 g3bed.BINS에는 g2·g3만 있어 지금 하네스가 gen33을 돌리지는 않는다. 그러므로 '조용히 빈 목록이 된다'는 하네스를 gen33에 연결했을 때 생기는 일이다. X3 카드의 '서버 첫 송신 크기·시각 기록'은 연결별 자료가 필요하므로 측정 전 해결 대상이라는 판단은 맞다. || qamp.go:2736 writeStats(false), :2743 writeStats(true), :2602 report() 안의 expireAccountsLocked. boundary.go:16 accountRetention = 10s, :101-115 accountEndedLocked가 deadline=now+10s, :63 delete(s.conns). 내 smoke(gen33 qampA, loopback, n=3): 주기 기록은 conns 0·live 3, SIGTERM 2초 뒤는 conns 3, SIGTERM 11초 뒤는 conns 0·expired 3. docs/T5_boundary_result.md:7 '주기 스냅숏에는 전체 연결 표를 넣지 않았다'.

- F3 (error): **partly** sev=low :: 동작과 숫자는 내 독립 시험으로 정확히 재현했다. 다만 TTL 폐기 위치를 hold.go:339-342로 인용했는데 실제로는 decoder_index.go:339-342(tickHoldIndexLocked case 0)다. 이 동작은 M1 계약이 명시한 설계다('TTL 시각에는 보관분을 정확히 한 번 폐기', '복구에 쓴 패리티는 반환하지 않는다'). 신용을 잃는 경우는 복구가 불가능하고 이미 PTO로 가는 비행뿐이다. 그 비용은 재전송 뒤 예산이 경계를 넘을 때 생기는 RTT 하나이고 확률도 작다(lead1·m2·k2에서는 L0만 도착하는 경우뿐). 그래서 medium은 과장이다. 덧붙여, 복구에 성공한 비행에서도 쓰인 선행 패리티는 신용이 되지 않는다. 이것도 계약대로이며 hold_layout.py는 decoder.delivered로 신용을 세므로 모형에 반영되어 있다. || zzv_audit_test.go TestZZVHoldUnrecoverableLeadCredit(leadBuildFlight lead1·m2·k2, L0만 도착, 200 ms 뒤 새 원본 2개). hold=true: leadReturned=false, BytesIn=3596, BytesToStack=2350, HoldExpiredBytes=1246, CreditParities=0. hold=false: leadReturned=true, BytesToStack=3596, CreditParities=1. quic-go v0.61 server.go:679-850 handleInitialImpl은 복호 전에 연결을 만들고, connection.go:1052 handleOnePacket은 복호 전에 ReceivedBytes를 센다. 그래서 레거시 경로의 선행 패리티는 실제로 신용이 된다. 추가 시험 TestZZVLegacyVsHoldRecoverable: L0+O0에서 legacy는 2446 B를 신용으로 넘기지만 복구 0이고, hold는 2350 B와 복구 1이다. docs/M1_hold_contract.md '회계와 수명' 절.

- F4 (error): **confirmed** sev=medium :: 인용한 줄과 값이 모두 맞다. 기준선은 waitFeedback(200 ms) 고정, tracer 없음, original_first 없음이었다. 각 변경은 D23·D25·D26·D28과 T1·T4·T6 문서에 적혀 있다. 그래도 T7이 todo, J3가 blocked, J4가 todo라서 플래그 없이 돌리면 봉인 조건과 달라진다. auto3 비용 모형도 기본 와이어 모양(original_first)과 어긋난다(T6_retrans_contract.md:11이 스스로 인정). 이 두 점은 사실이다. || qamp.go:3708 udp-path 기본 oob, :3714 feedback-wait 기본 1s, :3715 retrans-layout 기본 original_first, :3006 qconf.Tracer = observer.tracer(조건 없음). 기준선 qamp.go:2695 waitFeedback(200*time.Millisecond), 기준선에는 Tracer 없음. HEAD :3031-3037에서 srvBytes를 대기 뒤에 집계한다. docs/T6_result.md 표의 7961~7991 대 11940~12020과 일치. LOOP_STATE: T7 todo, J3 blocked, J4 todo. 내 smoke stats: udp_path oob_readmsg_batch1, udp_gso_calls 3·segments 3, 행 retrans_layout original_first.

- F5 (error): **confirmed** sev=low :: 그대로 재현했다. dup 쪽 결과는 검열(trunc)로 끝난다. T3_comparison_contract가 'dup 팔은 학습 관측에 쓰지 않는다'고 이미 정했으므로 해가 없다. 실질 결함은 pad_junk와 drop-parity 조합에서 버린 쓰레기 슬롯을 '보냈으나 잃은 패리티'로 세는 것뿐이다. X1 계획에 이 조합은 없다. || qamp.go:1535-1540 dropParity 분기가 kind와 무관하게 ffParCRC에 append한다. :1566-1573에서 kind != parity이면 ffParCRC를 추가하지 않는다. comparison.go:42-53 checkComparisonFlags는 corrupt만 검사한다. 내 시험 TestZZVDropParityComparison(m2·lead1·k2, dropParity=0): parity는 ffPar=2·sent=4, pad_junk는 ffPar=1·sent=3·lost=1·reason complete_crc_lists, dup은 ffPar=1·sent=3·trunc=true·reason truncated_or_ambiguous_crc.

- F6 (error): **partly** sev=low :: 논리는 맞지만 인용이 틀렸다. flight_input.go는 32줄짜리라 '206-211'은 없는 줄이다. 실제 근거는 flight_input.go:22-27 expectedKLocked이고, 첫 묶음 범위 밖이면 0을 돌려준다. 게다가 이 한계는 T5_timing_contract.md에 그대로 적혀 있다('과소 추정으로 잘린 뒤 예상과 같은 크기가 된 묶음은 이 검사로 판별하지 못한다'). D26도 '과소 추정·이전 비행 분할의 영향을 없앴다고 주장하지 않는다'고 했다. 문서화된 한계이므로 결함보다는 개선 제안에 가깝다. || flight_trace.go:83 SplitSuspected: expected > 0 && len(fl) < expected. flight_input.go:22-27. qamp_flight_input_test.go:107-130 TestFlightWrongKRetainsTimerFallback(k=1일 때 Flights=2만 검사). docs/T5_timing_contract.md 둘째 문단. DECISIONS_NEEDED.md D26.

- F7 (error): **partly** sev=low :: 수치는 맞다. 다만 이것을 Codex의 실수로 보기는 어렵다. 루프 규칙 LOOP_PROMPT.md 1절 7항은 '작업 저장소 안에서 git이 추적하는 파일만 git rm, 그 밖은 지우지 말고 trash_list에 적는다'고 정한다. 커밋 570ab2e62 메시지도 '빌드·시험·fresh 입력을 삭제하지 않고 보존한다'고 의도를 밝혔다. 남는 지적은 상한이 없고 trash_list.md에 기록하지 않았다는 운영상의 문제다. || git diff 90859b973 HEAD -- build_gen33.sh: cleanup trap 삭제, 'preserved build stage', GOTMPDIR=$STAGE/go-work. 읽기 전용 확인: ~/quicbed_gen33/stage.* 53개, 합계 3141 MB(평균 59 MB), 디렉터리 전체 3.9G, 생성 시각 10-31 20:07~11-01 08:19. runs/trash_list.md 없음.

- F8 (error): **confirmed** sev=low :: MORNING_REPORT의 'Go231'은 SKIP 2개를 드러내지 않는다. 다만 와이어 관문 결과는 T2_result(basic·oob 각 700116사례)와 S4·T5 문서에 따로 적혀 있다. 나도 저장된 gzip으로 HEAD에서 관문을 돌려 통과를 확인했고, HEAD의 Python 기준을 다시 생성하면 같은 gzip이 나오는 것도 확인했다. || ~/quicbed_gen33/bin/go_test.txt: --- PASS 231, --- SKIP 2(TestHoldPythonReadFromReference, TestUDPHoldPythonReadBatchReference, qamp_hold_test.go:593-595). MORNING_REPORT.md:78·195·207 'Go231'. 내 실행: M1_REFERENCE_GZIP=g3/v33/validation/M1_stage1/runs/M1_wire_reference_02.tsv.gz(sha 59b34347…)로 두 시험 모두 PASS, '700116 actual decoder cases, 60 configurations'(26.9 s, 28.6 s). HEAD의 experiments/v33/hold_wire_reference.py로 재생성한 gzip_sha256도 59b3434763af…로 같다(52 s).

- 재현 빌드와 배포 바이너리 일치 (improvement): **confirmed** sev= :: GOCACHE를 달리해 두 번 빌드한 결과가 배포 바이너리와 같다. srcsha도 일치한다. || WSL 임시 stage에서 go build -trimpath -buildvcs=false를 두 번 실행: 둘 다 41424293588fde08…이고 ~/quicbed_gen33/bin/qamp.sha256과 같다. /mnt/c 작업 트리(git status 깨끗함)로 build_gen33.sh와 같은 방식으로 계산한 srcsha 9798aa226a1a…가 qamp.srcsha와 일치한다.

- 시험 범위가 넓어졌고 경합이 없음 (improvement): **confirmed** sev= :: 직접 재실행해 같은 결과를 얻었다. || go vet(cmd/qamp, padfec-local-hook) 경고 0. go test 231 PASS·2 SKIP·0 FAIL. -race는 cmd/qamp 53.7 s, 전체 65 s에 rc=0. 기준선의 시험 함수 수를 git grep으로 세면 101개, HEAD는 233개(231+2 SKIP).

- 결정적 정확 크기 인증서 (improvement): **confirmed** sev= :: 별도 프로세스 dry-run 결과가 같고 크기도 정확하다. || qampA -mode certgen -dry-run을 2955·6000·16000에서 두 번씩 실행: der_bytes가 목표와 같고 der_sha256·file_sha256이 동일하다(2955의 file_sha256 783e80e8…). certificate.go는 Sign(nil,…)로 RFC6979를 쓴다.

- 같은 바이트 비교 팔과 재방문 팔을 확보함(X1·X4의 전제) (improvement): **confirmed** sev= :: pad_junk가 패리티와 같은 길이이고 복호 전에 신용을 받는 경로가 맞다. dup은 같은 바이트가 아니다(원본 복사라 더 작다). 감사자는 dup을 같은 바이트라고 주장하지 않았고, T3_comparison_contract가 이 차이를 밝혀 둔 데다 시험(qamp_comparison_test.go 'duplicate overhead hidden')도 검사한다. 실측은 아직 없으므로 장치가 생겼다는 의미로만 인정한다. || comparison.go:55-68, qamp_comparison_test.go의 pad_junk 길이 동일 단언과 dup st.Bytes < par.Bytes 단언. quic-go v0.61 server.go handleInitialImpl(복호 전 newConn), connection.go:1052. docs/T3_comparison_contract.md 셋째 문단.

- 오래된 타이머가 새 묶음을 조기 해제하는 문제를 차단 (improvement): **confirmed** sev= :: 기준선은 time.AfterFunc(c.parityDelay, c.flushFlight)로 세대 구분 없이 현재 묶음을 해제했다. HEAD는 세대 번호로 오래된 콜백을 무시한다. || 기준선 qamp.go:1193, :1300-1316. HEAD qamp.go:1265-1268 timerGeneration, :1395 generation != c.timerGeneration이면 반환.

- 복호기 색인과 메모리 상한 (improvement): **partly** sev= :: 선형 탐색을 (DCID, 계정) 키 조회로 바꾼 것과 비행 수·바이트 상한을 새로 둔 것은 맞다. 그러나 '기준선은 … 상한이 없었다'는 틀렸다. 기준선에도 recentCap=512와 recentTTL 3 s, flightTTL 1 s 만료, connAcctCap=4096, connAliasCap=16이 있었다. 새로 생긴 것은 비행 개수·payload 상한(1024, 그룹당 8, 32768 B, 8 MiB)과 그룹당 recent 64개다. || 기준선 qamp.go:1695 connAcctCap=4096, :1717-1719 flightTTL·recentTTL·recentCap=512, :1754 connAliasCap=16, :1945-1960 expireLocked, :1947 per-packet range s.recent. HEAD decoder_index.go:12-16 상수.

- 학습 입력에서 거짓 손실을 줄임 (improvement): **confirmed** sev= :: 기준선에 있던 C2 전멸 적립 호출이 HEAD에서 사라졌다. 판본3은 물리 수신과 복원을 나눠 보낸다. 효과 크기는 측정되지 않았다는 감사자 단서도 맞다. || 기준선 qamp.go:2760-2768 (hct > 3*base) → cache.observeSymbolsWhy(…, true). HEAD에는 해당 호출 없음. observation.go:196-249. DECISIONS D13. docs/c1_status.md 마지막 문단.

- 서버가 quic-go의 OOB 경로를 쓰게 됨 (improvement): **confirmed** sev= :: 직접 확인했다. 성능 효과는 미확인이라는 단서도 맞다. || 내 smoke a.json: udp_path oob_readmsg_batch1, udp_gso_calls 3, udp_gso_segments 3. quic-go v0.61 connection.go:2536-2552는 handshakeConfirmed 전에는 PackCoalescedPacket을 하나씩 보내고, GSO는 그 뒤에만 쓴다.

- 파서 경계 검사와 송신 회계 롤백 (improvement): **confirmed** sev= :: 코드상 근거가 있다. 약한 개선이라는 평가가 적절하다. || qamp.go:802-832 hasHandshake의 토큰·길이 경계 검사. udp_linux.go:222-261 GSO 세그먼트별 previous 사본을 떠 두었다가 실패 시 되돌린다.

- verdict_improved (verdict): **partly** sev= :: 기능·견고성·재현성이 기준선보다 나아졌다는 판정과 '측정에 바로 쓸 상태는 아니다'라는 결론에는 동의한다. vet·test·race, 재현 빌드, 700116사례 관문, 결정적 인증서는 모두 내가 재확인했다. 다만 근거와 우선순위 일부를 고쳐야 한다. (1) F1을 1순위로 둔 근거 중 '문서 어디에도 없다'는 틀렸다(c1_status.md:7). 봉인 v3.1은 -feedback을 쓰지 않았고 기존 하네스는 팔마다 서버를 따로 띄운다. 그러므로 F2(연결별 서버 기록 없음)와 F4(기본값과 비용 모형 불일치)가 F1보다 앞서야 한다. (2) 개선 목록의 '기준선에는 상한이 없었다'는 사실과 다르다. (3) F3·F6·F7은 계약이나 루프 규칙에 이미 적힌 설계 선택 또는 한계에 가깝고, F3·F6은 파일·줄 인용이 틀렸다. 'HCT 개선을 잴 근거가 아직 없다'는 단서는 맞다. || 위 항목별 근거. docs/c1_status.md:7, g3bed.py start_server(-feedback 없음)·PORTS[tag], pq_afec_gen31/experiments에서 -feedback 사용은 p17_adaptive_value.py뿐이다. 기준선 qamp.go:1695·1717-1719.

### missed

- [low] F1 영향은 옛 클라이언트의 -feedback 설정과 무관하다 :: gen31과 gen-2 클라이언트의 ReadFrom은 parseFeedback이 nil이면 클라이언트 쪽 -feedback 플래그와 상관없이 countRx(n)으로 그 데이터그램을 서버 바이트에 더한다. 따라서 T7에서 v33auto의 C1 학습을 위해 공통 gen33 서버에 -feedback을 켜면, -feedback을 끈 v31auto·g2auto 팔의 srv_bytes(auto 정책의 S 관측 입력)도 연결마다 수십 바이트씩 부푼다. 감사자는 이를 C1 '회신 없음' 문제와 함께 묶어 적었다. 실제로는 S 관측 편향이 더 직접적인 영향이다. || pq_afec_gen31/experiments/quicbed/qamp.go:1216-1223(parseFeedback==nil이면 countRx, 플래그 검사 없음). 이 동작에 대한 코드 주석('세면 -feedback 팔의 srv_bytes 만 +31 B 라 S 관측이 갈린다')도 같은 줄에 있다. 내 종단 smoke에서 gen33 서버 -feedback에 v3.1 클라이언트를 붙이면 server_bytes가 약 +37~45 B였다.

- [low] hold 팔은 복구에 성공한 비행에서도 선행 패리티 신용을 포기한다(설계상 교환, X1·X6 해석 주의) :: F3은 복구가 불가능한 비행만 다뤘다. 실제로는 hold가 선행 패리티를 복구에 쓰면 그 패리티 바이트가 스택에 넘어가지 않으므로, 레거시가 주던 신용이 hold에서는 모든 '선행 도착' 경우에 줄어든다. 계약과 hold_layout.py 모두 이를 반영하므로 결함은 아니다. 다만 X1의 'm4L3 대 m4L3+보류 복호' 비교에서 '같은 바이트, 같은 신용'이라는 전제가 성립하지 않는다는 점을 측정 계획에 적어야 한다. || 내 시험 TestZZVLegacyVsHoldRecoverable(lead1·m2·k2): L0+O0에서 legacy는 BytesToStack 2446·CreditParities 1·Recovered 0, hold는 2350·0·1. L0+T1에서 legacy는 1246·1·0, hold는 2350·0·2. docs/M1_hold_contract.md '복구에 쓴 패리티는 반환하지 않는다'.
