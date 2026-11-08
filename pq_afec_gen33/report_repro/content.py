
TITLE_KO = 'ML-KEM 적용 시 전송 성능 개선을 위한 QUIC 기반 적응형 FEC 연구'
TITLE_EN = 'QUIC-based adaptive FEC for improving transmission performance under ML-KEM'
SCHOOL_KO = '강원과학고등학교'
SCHOOL_EN = 'Gangwon Science High School'

ABSTRACT = (
    'ML-KEM을 QUIC에 적용하면 first flight의 datagram이 늘어난다. 본 연구는 이 변화가 handshake 지연을 바꾸는 경로를 quic-go와 netem으로 측정하였다. '
    '무손실에서 지연을 좌우한 것은 ML-KEM 연산(수십 µs)이 아니라 anti-amplification limit에 의한 추가 왕복이었고, 인증서 4,032 B에서는 X25519MLKEM768이 X25519보다 RTT의 95.0~99.3% 빨랐다. '
    'QUIC 손실 취약성은 측정기 결함으로 판정을 보류하였다. 서버 예산을 늘리는 바이트를 parity로도 보내는 PAD-FEC를 구현하여, X25519, 손실 5%에서 padding과 결합한 평균 HCT를 114.59 ms에서 52.98 ms로 줄였다. '
    '사전 봉인 비교에서 v3.1은 지정한 두 조건에서 gen-2보다 28.01 ms, 12.38 ms 빨랐으나 전 조건 비열등과 적응 기여는 확인되지 않았다.'
)
KEYWORDS_LINE = '주제어: ML-KEM, QUIC, anti-amplification limit, FEC, handshake latency'
KEYWORDS_CELL = 'ML-KEM, QUIC, anti-amplification limit, FEC, handshake latency'

SUMMARY_NEED = [
    'NIST는 2024년 ML-KEM을 FIPS 203으로 표준화하였다. TLS 1.3의 hybrid group X25519MLKEM768에서 client key share는 1,216 B로 X25519의 38배이며, '
    'QUIC에서는 이 바이트가 first flight의 크기와 datagram 수를 직접 바꾼다.',
    '본 연구의 목적은 이 변화가 handshake 지연을 어떤 경로로 바꾸는지 측정으로 밝히고, 그 구조 안에서 padding과 parity를 선택하는 전송 정책을 '
    '설계하여 검증하는 것이다. 연구 문제는 (1) 비용이 발생하는 지점, (2) client 송신 바이트와 왕복 수의 규칙, (3) padding을 parity로 대체할 때의 이득과 비용, '
    '(4) 정책 세대 간 성능이다. padding 바이트를 parity로 대체하는 방식을 다룬 문헌은 2026년 11월 5일까지의 검색 범위에서 찾지 못하였다.',
]

SUMMARY_RESULT = [
    '교내 서버와 노트북의 netem·veth 테스트베드에서 quic-go v0.61.0을 사용하여 키 교환, 인증서 크기, RTT, Initial 크기, 손실률, uplink를 바꾸어 측정하였다. '
    '세대 비교는 프로토콜과 바이너리를 측정 전에 봉인하고 arm을 교대하여 259,600연결을 측정하였다.',
    '○ ML-KEM-768 연산은 24.1~28.2 µs였다. first flight는 X25519가 1개(1,280 B), X25519MLKEM768이 2개(2,560 B)였다. QUIC 손실 비교는 측정기 분모 결함이 드러나 판정을 보류하였다.',
    '○ 무손실 RTT 50 ms에서 2-RTT로 넘어가는 인증서 크기는 X25519 3,300~3,400 B, hybrid 5,900~6,000 B였다. 인증서 4,032 B에서 hybrid가 RTT의 95.0~99.3% 빨랐다. padding만 바꾸어도 경계가 이동하였다.',
    '○ quic-go에서는 datagram당 1 B 증가로 왕복 하나가 사라졌다(X25519, 인증서 4,032 B, 무손실, n = 400, 평균 차 50.88 ± 0.12 ms). 이 불연속은 구현의 packet 단위 판정에 의존한다.',
    '○ padding 자리의 parity는 12개 설정(8개는 k = 1)에서 용량 부등식을 위반하여 별도 datagram으로 바꾸었다. X25519, 인증서 4,032 B, 손실 5%의 평균 HCT는 처리 없음 114.59, padding 60.27, parity 57.65, 결합 52.98 ms였다.',
    '○ v3.1은 큰 인증서 조건에서 gen-2보다 28.01 ms, RTT 200 ms 조건에서 12.38 ms 빨랐고 2회차에서도 같은 방향이었다. 18조건 비열등(H2), held-out 셀 예측 일치(H3), 적응 기여(H4)는 확인되지 않았다.',
]

SUMMARY_PLAN = [
    '측정기를 고친 뒤 손실 취약성을 같은 블록 교대 설계로 재측정한다. 같은 바이트의 padding과 parity를 직접 비교하여 parity의 고유 몫을 분리한다. 실측이 없는 v3.2-dev와 v3.3.1-dev를 새 봉인 프로토콜로 측정한다.',
    '다른 QUIC 구현과 두 물리 호스트 사이의 경로로 범위를 넓히고, PQC 서명 인증서와 Initial congestion window 10 조건을 포함한다. first flight parity가 혼잡 제어와 공정성에 주는 영향도 측정한다.',
]

EXPERT = [
    '【입력 필요: 중간성과공유회(팀 초안에 9월 22일로 기재, 일시 확인 필요)에서 전문가가 실제로 지적한 내용과 그 반영 결과를 쓴다. 전문가 피드백이 없었다면 이 칸 전체를 X로 바꾼다.】',
]

PROBLEM = [
    '(1) 전제 재검토. 손실 취약성을 검증하던 중 손실이 없는 조건에서 왕복이 하나 더 생기는 현상을 관측하였다. padding만 바꾼 대조 실험으로 원인을 client 송신 바이트로 좁히고, 8월 19일 연구 방향 변경 보고서를 작성하였다.',
    '(2) 측정기 분모 결함. TLS·QUIC 측정기가 warm-up 실패를 실패 수에 넣은 것을 9월 AI 코드 감사에서 찾았다. TLS 자료는 행별 설계 횟수로 다시 계산하였으나 QUIC 자료는 시간열이 남아 있지 않아 판정을 보류하고, 이전 문서의 "기각" 표현을 정정하였다.',
    '(3) "추가 비용 없는 FEC" 폐기. 8월 19일 보고서의 주장을 곧이은 측정이 부정하였다. parity를 별도 datagram으로 바꾸고 비용을 정량화한 뒤 원본을 지우지 않고 8월 26일 정정 보고서를 작성하였다.',
    '(4) 계측 오류. loopback MTU 설정이 오류 없이 무시되어 TLS 1차 측정 120행을 손실 근거에서 제외하고 veth로 다시 측정하였다. netem 상관 옵션은 명목 5%가 0.19%로 떨어져 Gilbert-Elliott 역산으로 바꾸었다.',
    '(5) 측정 표류. 같은 조건과 표본의 두 실행에서 regret 구간이 겹치지 않았다(0.026 ± 0.025, 1.173 ± 0.049 ms). arm을 순차로 재며 생긴 표류로 판단하여 교대 측정과 batch means를 도입하였다.',
    '(6) 복구 구조 결함. 팀원1이 별도 환경에서 FEC 구현을 재현하다 복구가 erasure 하나에 묶인 구조를 보고하여 다중 erasure 복구로 고쳤다.',
    '(7) 봉인 판정 실패. v3.0이 held-out 셀에서 gen-2보다 45.86 ms 느렸다. 판정을 유지한 채 probe로 41 B 선행 송신을 찾고, v3.1을 새 봉인과 새 held-out 셀로 측정하였다.',
    '(미해결) 같은 바이트 padding 대 parity 비교, 손실 취약성 재측정, v3.3.1-dev 측정은 자동화 과제의 의존 구조가 교착되어 실행되지 않았다. 11월 2일 의존을 풀었으나 측정 러너가 아직 없으며 향후 연구에서 수행한다.',
]

AI_USED = '■ 활용함'
AI_NOT = '□ 활용하지 않음'
AI_TOOLS = 'Claude Code, Codex, PaperBanana(paper-banana.ai)'
AI_PURPOSE = '코드 구현, 측정 자동화, 통계 재계산, 코드 감사, 문헌 대조, 보고서 초안 작성, 구조도 생성'
AI_DETAIL = (
    '정책과 테스트베드 구현, 측정 실행, 감사, 본 보고서 초안의 상당 부분을 AI로 수행하였다. 방향 전환은 학생이 맡았고 설계 심사와 결함 발견에는 AI도 참여하였으며, '
    '수치는 원자료와 대조하였고 일부 결과는 팀원이 별도 기계에서 재현하였다. [Fig. 1], [Fig. 2]는 PaperBanana로 생성한 뒤 설계와 대조하여 라벨과 선을 일부 수정하였고, 측정값 그래프는 원자료에서 코드로 그렸다. 【확인 필요: 학생별 수행 범위】'
)

ROLE_HEAD = '각 팀원의 역할과 기여도'
ROLE1 = '교내 서버 실험망 구축, TLS·QUIC 측정기 제작, 인증서 경계와 padding 대조 측정, 별도 기계에서 FEC 구현 재현과 결함 보고, 다른 구현 대조, 중간 발표 자료 제작.'
ROLE2 = 'PAD-FEC 정책과 quic-go 테스트베드 구현(생성형 AI 활용), 팀원1이 보고한 결함 수정, gen-2·v3 측정과 결과 정리, 정정 보고서와 최종 보고서 정리.'
ROLE3 = '【입력 필요: 본인 확인 후 실제 수행한 역할을 쓴다. 계획 단계 배정은 padding-FEC 구현이었으나 수행 기록을 찾지 못하였다.】'

LEARN = [
    'QUIC handshake와 RFC 9000·9001·9002 읽기, FIPS 203과 hybrid 키 합의, XOR·Reed-Solomon 부호, Gilbert-Elliott 모형, netem·veth·namespace, Go와 quic-go 내부 구조, Welch 추정, batch means, Holm 보정, 비열등 판정, 사전 봉인 절차를 새로 배웠다.',
    '자체 평가: 부정 결과와 실패 판정을 지우지 않았고 무손실 대조군을 자동 검사로 넣은 점은 잘하였다. 구현이 이해보다 앞서 9월 이후 기초 공부를 따로 진행하여야 했고, 손실 통계 재측정, 다른 QUIC 구현 검증, 최신 개발본 실측은 끝내지 못하였다.',
]

W_TABLE = 44400

BODY = [
    ('h1', 'Ⅰ. 서론'),
    ('h2', '1. 연구 배경'),
    ('p', 'NIST는 2024년 격자 기반 key encapsulation mechanism인 ML-KEM을 FIPS 203으로 표준화하였다{c:fips203}. TLS 1.3{c:rfc9846}에서는 X25519와 ML-KEM-768을 결합한 hybrid group X25519MLKEM768이 RFC 10024로 규정되었고{c:rfc10024}, client key share는 1,216 B로 X25519의 32 B보다 38배 크다. QUIC{c:rfc9000}은 TLS handshake를 UDP datagram 위에서 수행하므로{c:rfc9001} 이 증가가 첫 왕복에 그대로 반영된다. Cloudflare는 이 크기의 key share가 ClientHello를 보통 두 packet으로 나눈다고 설명하였다{c:cf2022}.'),
    ('p', 'post-quantum(PQC) handshake의 전송 비용에 관한 선행연구는 조건이 제한적이다. Kempf 등은 RTT가 0.1 ms 미만인 망에서 Kyber의 TTFB를 측정하였고{c:kempf}, Paquin 등은 TCP 위의 TLS에서 손실이 3~5%를 넘으면 여러 packet으로 나뉘는 알고리즘의 영향이 커짐을 보였다{c:paquin}. Montenegro 등은 QUIC과 TLS의 손실 민감도를 비교하였으나 X25519MLKEM768을 포함하지 않았고 anti-amplification limit을 논의하지 않았다{c:montenegro}. Sakk 등의 해석 모형은 LoRa 조건에서 packet 수 증가가 전달 성공 확률을 낮춘다고 제시하였다{c:sakk}.'),
    ('p', '본 연구는 처음에 세 전제를 세웠다. ML-KEM은 first flight의 packet 수를 늘리고, packet이 늘면 손실에 더 취약해지며, 손실률에 맞춘 적응형 FEC로 이를 개선할 수 있다는 것이다. 측정 결과 첫째는 사실이었고, 둘째는 측정기 결함으로 판정하지 못하였으며, 셋째는 RQ4에서 다룬다. 손실이 없어도 왕복이 하나 더 생기는 현상을 관측하여, 이 왕복이 생기는 경로를 밝히고 padding과 parity를 고르는 정책을 검증하는 것을 연구 목적으로 삼았다.'),
    ('h2', '2. 연구 문제'),
    ('p', 'RQ1. ML-KEM 적용은 연산, first flight 구성, 손실 민감도 중 어디에서 비용을 만드는가? RQ2. anti-amplification limit 아래에서 client 송신 바이트는 handshake 왕복 수를 어떤 규칙으로 결정하는가? RQ3. 서버 송신 예산을 늘리는 바이트를 padding 대신 parity로 보내면 왕복 제거와 손실 복구를 어디까지 얻고 비용은 얼마인가? RQ4. 이 선택을 비용 모형과 온라인 학습으로 자동화한 정책은 사전에 고정한 조건에서 앞 세대보다 나은가?'),
    ('h2', '3. 연구 범위와 기여'),
    ('p', 'anti-amplification limit이 QUIC handshake에 왕복을 더한다는 사실은 Nawrocki 등{c:nawrocki}, Kampanakis와 Lepoint{c:kampanakis}, McManus{c:mcmanus}가 보고하였다. client 바이트를 늘려 서버 예산을 넓히는 방법도 RFC 9000의 규칙에서 따라 나오며{c:rfc9000}, Kampanakis와 Lepoint는 ClientHello의 인위적 확대를 자원 낭비로 평가하였다{c:kampanakis}. 본 연구의 기여는 그 uplink 바이트를 padding 대신 parity datagram으로 보내 예산 확보와 erasure 복구를 하나의 바이트 회계로 묶은 것이다. 2026년 11월 5일까지의 검색 범위에서 같은 대체를 제안하거나 평가한 문헌을 찾지 못하였다(<Table 1>). 이 결과는 quic-go와 emulation 조건의 것이고, 복구에는 서버 decoder가 필요하다.'),

    ('h1', 'Ⅱ. 이론적 배경'),
    ('h2', '1. ML-KEM과 hybrid key share'),
    ('p', 'ML-KEM-768의 encapsulation key는 1,184 B, ciphertext는 1,088 B, shared secret은 32 B이다{c:fips203}. X25519MLKEM768에서 client share는 1,216 B, server share는 1,120 B, 결합된 shared secret은 64 B이다{c:rfc10024}. 서버 쪽 바이트는 주소 검증 전 서버 예산을 소비하고 client 쪽 바이트는 그 예산을 늘린다.'),
    ('h2', '2. QUIC handshake와 first flight'),
    ('p', '본 연구에서 first flight는 client가 서버의 첫 응답을 받기 전에 보내는 datagram의 묶음을 뜻한다. client Initial을 담은 datagram은 최소 1,200 B여야 하고(RFC 9000 §14.1){c:rfc9000}, 실험에 사용한 quic-go{c:quicgo}의 기본 크기 W는 1,280 B이다. ClientHello의 CRYPTO 바이트를 C, packet 고정비를 h라 하면 datagram 수는 k = ceil(C / (W − h))이고 first flight 바이트는 B = k·W이다. Initial 보호 키는 Destination Connection ID에서 유도되므로{c:rfc9001} 관측자가 복호할 수 있으며, 본 연구는 이 성질로 first flight 구성을 확인하였다.'),
    ('h2', '3. Anti-amplification limit'),
    ('p', '서버는 client 주소를 검증하기 전까지 그 주소에서 받은 바이트의 3배까지만 보낼 수 있다(RFC 9000 §8.1){c:rfc9000}. 한 연결에 고유하게 귀속되는 datagram은 그 안의 packet이 모두 폐기되어도 payload 전체가 수신 바이트에 든다. 서버 flight가 3B를 넘으면 서버는 남은 바이트를 보내지 못하고 client의 다음 packet을 기다리며, 이때 왕복이 하나 추가된다. Nawrocki 등은 약 100만 도메인 조사에서 수집한 certificate chain의 35%가 4,071 B를 넘고, Initial 1,362 B handshake의 38%가 여러 왕복을 쓴다고 보고하였다{c:nawrocki}. client가 Initial을 더 채우는 방법의 효과는 McManus가 TCP 표본을 환산한 모형으로 제시하였고{c:mcmanus}, Nawrocki 등은 Initial 1,200~1,472 B 실험에서 약 1%의 개선과 도달성 감소를 함께 보고하였다{c:nawrocki}.'),
    ('h2', '4. FEC와 손실 모형'),
    ('p', 'FEC(forward erasure correction)는 repair symbol로 손실된 원본을 재전송 없이 복원한다. XOR parity는 erasure 하나를, Reed-Solomon 부호{c:reed}는 parity 수만큼의 erasure를 복원할 수 있다. 본 연구의 구현은 m = 1이면 XOR(k = 1이면 복제), m ≥ 2이면 GF(2^8)의 Cauchy 행렬 기반 RS 부호를 쓴다. 연속 손실은 2상태 Gilbert-Elliott 모형{c:gilbert,elliott}으로 다루며, 평균 손실률 π와 평균 burst 길이 L에서 전이확률은 r = 1/L, p = π·r/(1 − π)이다.'),
    ('p', 'QUIC에서 FEC는 주로 handshake 이후 구간에서 연구되었다. Google QUIC은 XOR FEC의 이득이 작아 2016년 초에 제거하였고{c:langley}, QUIC-FEC는 handshake가 끝나기 전에는 FEC frame을 보내지 않으며{c:quicfec}, rQUIC은 residual loss에 따라 비율을 조절하되 STREAM packet에 적용하였다{c:rquic}. RFC 9265는 FEC가 혼잡 신호를 가려서는 안 된다고 정리하였다{c:rfc9265}. 품질 함수를 최적화하여 FEC 양을 고르는 사례는 Internet telephony에 있다{c:bolot,boutremans}. handshake 구간에서는 IKEv2 fragment에 RaptorQ를 적용한 preprint가 있으나 목적이 손실 흡수이고 amplification credit을 다루지 않는다{c:herzinger}.'),
    ('h2', '5. 선행연구와 본 연구의 위치'),
    ('table', 'Table 1. Position of this study relative to prior work', [8200, 21000, 15200], [
        ['층위', '이미 알려진 것', '본 연구의 몫'],
        ['문제', ('3배 제한과 큰 서버 flight가 왕복을 더함{c:nawrocki,kampanakis,mcmanus}', 1, 'L'), ('quic-go에서 재확인', 1, 'L')],
        ['KEM 효과', ('ClientHello 두 packet 분할{c:cf2022}, 예산 증가(규칙의 귀결){c:rfc9000}', 1, 'L'), ('구간과 격차를 측정, 독자 발견이 아님', 1, 'L')],
        ['수단', ('client 바이트로 서버 예산 확보{c:rfc9000,nawrocki,kampanakis,mcmanus}', 1, 'L'), ('quic-go 증가 규칙 측정', 1, 'L')],
        ['손실 FEC', ('데이터 구간과 IKEv2 fragment{c:langley,quicfec,rquic,herzinger}', 1, 'L'), ('없음', 1, 'L')],
        ['대체', ('padding 바이트를 parity로 대체: 찾지 못함', 1, 'L'), ('설계, 구현, 측정(같은 바이트 비교 없음)', 1, 'L')],
    ]),

    ('h1', 'Ⅲ. 연구 방법 및 절차'),
    ('h2', '1. 연구 설계'),
    ('p', '연구는 네 단계로 진행하였다. 1단계(RQ1)는 연산 비용, first flight, 손실 민감도를 측정하였다. 2단계(RQ2)는 인증서 크기, RTT, Initial 크기를 바꾸어 왕복 수의 규칙을 찾았다. 3단계(RQ3)는 padding과 parity 바이트(credit)로 서버 예산을 늘리는 PAD-FEC를 구현하여 고정 arm으로 측정하였다. 4단계(RQ4)는 정책 세대(gen-2, v3)를 같은 실행 안에서 교대로 비교하였다. 측정 구성은 <Table 2>와 같다.'),
    ('table', 'Table 2. Experiments and sample sizes', [9200, 10300, 15100, 9800], [
        ['실험', '환경, 시기', '독립변수', '표본'],
        ['연산', '교내 서버, 8월', 'ML-KEM 3종', '알고리즘당 10,000회'],
        ['TLS 손실', '교내 서버, 8월 14일', 'KEM 5종, RTT 5수준, 손실 5수준, uniform·burst', '250행, 설계 330,000회'],
        ['왕복 경계', '교내 서버 8월 18일, 노트북 9~10월', '인증서 500~16,000 B, RTT 10~200 ms, Initial 1,200~1,450 B', '점당 n = 20~30, 이분탐색 15~40'],
        ['방법 비교', '노트북, 10월 2일', '처리 없음, padding, parity, 결합 × 손실 0·5%', '셀당 400연결'],
        ['gen-2 정책', '노트북, 10월 1~2일', '인증서, 손실, uplink, 고정 arm과 auto', '4개 실험 418,400연결'],
        ['v3 봉인', '노트북, 10월 2~3일', '세대, 고정 arm, 조건 23개', '합계 259,600연결'],
    ]),
    ('h2', '2. 실험 환경'),
    ('p', '교내 서버(Intel Xeon Gold 5218R, 40 코어, 125 GiB, Ubuntu 24.04.4, 일반 사용자 권한, Go 1.26.5, OpenSSL 3.5.6)에서는 unshare -Urnm으로 만든 user namespace 안에서 veth 쌍을 network namespace로 분리하였다. 노트북(WSL2 Ubuntu, Go 1.26.6, OpenSSL 3.5.5)도 같은 구조이고 CPU 4개를 taskset으로 고정하였다. MTU는 1,500 B, QUIC 구현은 quic-go v0.61.0, ML-KEM 연산 측정은 liboqs-python 0.15.0{c:liboqs}이다. 지연은 netem으로 양방향에 RTT/2씩 넣었고(8월 TLS는 미확정, 25 ms 설정에서 ping 평균 50.068 ms), gen-2 이후 실험의 손실과 대역 제한은 client→server 방향에만 적용하였다.'),
    ('p', 'burst 손실은 Gilbert-Elliott 전이확률을 역산한 netem gemodel로 만들었다. 500,000 packet 검증에서 명목 5%, L = 4는 손실 5.23%, burst 4.05로 재현되었다. netem의 loss p% corr%는 명목 5%, 상관 25%에서 실효 0.19%로 떨어져 쓰지 않았다.'),
    ('h2', '3. 측정 변수'),
    ('p', '주 종속변수는 handshake completion time(HCT)이다. quic-go 실험은 Dial 호출부터 반환까지, TLS 실험은 TCP connect 시작부터 SSL_connect 반환까지 측정하였다. tcpdump를 쓸 수 없어 net.PacketConn을 감싸 datagram 크기와 수를 기록하고, first flight 구성은 Initial을 복호하여 확인하였다. 인증서 크기는 DER에 더미 확장을 넣어 맞추었고, session ticket, 0-RTT, path MTU discovery를 껐다. HCT가 1.5·RTT(v3 판정은 직렬화 시간을 더함) 이하이면 1-RTT, 3·RTT를 넘으면 PTO형 대기로 분류하였다.'),
    ('h2', '4. PAD-FEC 설계'),
    ('p', 'quic-go v0.61.0은 packet을 만들기 전에 송신 바이트가 수신 바이트의 3배에 도달했는지만 검사하므로, 남은 예산이 조금이라도 있으면 packet 하나를 온전히 보낸다. 서버 packet 크기를 P = 1,280 B라 할 때 관찰되는 예산은 식 (1)이다. 이는 RFC의 규정이 아니라 이 구현의 동작을 설명하는 모형이다.'),
    ('eq', 'A(B) = ceil(3B / P) · P     (1)'),
    ('p', '서버 flight의 크기를 S(n) = cert + s0 + n·c로 두면 필요한 packet 수는 n* = min{n : n·P ≥ S(n)}이고, 1-RTT 조건은 A(B) ≥ n*·P이다([Fig. 1]). s0와 c는 경계 6구간에 fit한 유효 파라미터이다(c = 41.983 B, s0 = 382.45 B와 1,472.00 B). 손실 단위가 datagram이므로 datagram 하나의 erasure를 추가 바이트 없이 복원하려면 ClientHello가 나머지 k − 1개의 여유 공간에 들어가야 한다(f는 parity 식별 정보의 크기).'),
    ('eq', 'C ≤ (k − 1)(W − h − f)     (2)'),
    ('fig', 'fig1_timing', 140, '[Fig. 1] Handshake timing for X25519, certificate 4,032 B, RTT 50 ms, to scale (δ: per-datagram padding increase, P = 1,280 B); burst packets and the parity are drawn apart by up to 7.6 ms. Measured medians: (a) 102.5, (b) 51.7 ms without loss; at 5% loss, 252.4 ms for the PTO class of (c), 51.2 ms for the 1-RTT class of (d)'),
    ('p', '정책의 행동은 datagram당 padding 증가량 δ와 parity 수로 이루어진다([Fig. 2]). gen-2는 (δ, m)을 고르며 m = 1이면 parity를 원본 뒤에, m ≥ 2이면 하나를 원본 앞에 둔다. v3는 앞에 두는 parity 수 ℓ과 뒤에 두는 parity 수 T를 분리하여 (δ, ℓ, T), m = ℓ + T ≤ 4로 확장하였다. 서버는 ℓ개를 바로 스택에 넘겨 credit으로만 쓰고, T개는 복구가 필요 없으면 그대로 넘겨 credit이 되며 복구하면 복원본으로 대체한다. 따라서 같은 바이트가 credit과 복구에 중복으로 쓰이지 않는다. parity datagram은 약 W + 39 + 6k B이고(DCID 길이에 따라 변동, k = 2, W = 1,280에서 약 1,331 B), 원본별 CRC-32와 길이를 담는다. CRC는 복원본 자기 확인용이며 인증이 아니다.'),
    ('fig', 'fig2_system', 140, '[Fig. 2] Closed-loop view of PAD-FEC v3 on the quic-go testbed (ℓ = k = T = 2; the rightmost datagram leaves first). S: server bytes received by the client; the uplink rate is configured, not learned'),
    ('p', '비용 모형은 식 (3)이다. E[n_rtt]는 복구에 성공한 도착 조합의 기대 왕복 수, stall은 복구 실패 가지의 기대 대기, t_tx는 임계 경로에서 늘어난 바이트의 직렬화 시간이다.'),
    ('eq', 'J(δ, m) = E[n_rtt] · RTT + stall + t_tx     (3)'),
    ('p', 'stall은 Gilbert-Elliott 도착 결합분포와 기대 라운드 수로 계산하고, 대기는 PTO 200.86 ms, ACK로 손실이 드러나는 경우 1.125·RTT + 1.424 ms, PTO 표본이 있는 경우 3·RTT(RFC 9002{c:rfc9002}에서 유도)로 나눈다. 앞의 두 상수는 이 환경의 quic-go 측정값이다. 정책(auto)은 J가 최소인 행동을 고르되 0.01 ms 안의 동점은 추가 바이트가 적은 쪽을 택한다. v3의 비용 J(δ, ℓ, T)는 도착 조합을 열거한다. 학습은 gen-2가 m = 0 연결의 지연으로, v3가 손실률 격자 26점과 hazard 5개의 혼합 사후분포로 한다. v3.1은 uplink 제한 시 완료 판정에 선행 송신 A_pre = 41·(k − 1) B를 넣고, 명목 2-RTT 행동의 관측을 학습에서 빼고, 16번째 결정마다의 재평가와 잔차 감시층을 더하였다.'),
    ('h2', '5. 통계 처리와 해석 기준'),
    ('p', '정책 비교는 arm을 교대로 돌리고 오차를 batch means로 추정하였다(크기 floor(√n), 최소 8개). regret(auto − 최선 고정 arm)은 상한 ≤ 2 ms이면 맞음, 하한 > 2 ms이면 틀림, 그 밖은 판정불능이다. 왕복 제거는 0.9 RTT 이상 줄면 성공, 0.7 RTT 이하이면 실패로 판정하였다. gen-2의 판정불능은 성공으로도 실패로도 쓰지 않고 필요 표본을 함께 적었다. 실패율은 비율 z 검정과 층화 CMH, Bonferroni 기준 |z| > 2.50을 쓰되 반복을 독립으로 가정하였다. 동등성 마진을 미리 정하지 않았으므로 비유의를 "차이 없음"으로 해석하지 않는다.'),
    ('h2', '6. 사전 봉인 세대 비교'),
    ('p', 'v3.0과 v3.1의 비교는 프로토콜, held-out 셀 추첨, 예측, 러너, 정책과 Go 소스, 바이너리의 SHA-256을 측정 전에 고정하였다. 계획한 block이 끝나기 전에는 결과를 보지 않고, 측정 뒤 코드를 고치면 개발 자료로 강등한다. 지표는 계획한 모든 시도의 평균 HCT(실패는 10,000 ms 대입)이고, Δ = gen-2 auto − v3 auto이다. 층별 짝 차이에 Welch-Satterthwaite 자유도를 쓰고 가설군별 Holm 보정 하한(LB)으로 판정하였다. 판정 규칙은 <Table 3>이다. A/A와 서버 동등성 대조의 95% 구간이 0을 배제하면 모든 판정을 보류하고, 아니면 두 구간 끝 절댓값의 최대를 H1 문턱 B_h로 쓴다. 조건은 주 조건(S), 이월 조건(D), held-out 셀(H)로 나뉜다.'),
    ('table', 'Table 3. Sealed hypotheses and decision rules', [3000, 21000, 20400], [
        ['가설', '조건', '성립 규칙'],
        ['H1', ('큰 인증서(16,000 B, RTT 50 ms, 2 Mbps)와 RTT 200 ms(9,000 B, 2 Mbps), 손실 2%↔15% 전환', 1, 'L'), ('두 조건 LB > max(0, B_h), LB 평균 ≥ 1 ms, 2회차 같은 방향', 1, 'L')],
        ['H2', ('S·D·H 18개 조건', 1, 'L'), ('모든 조건 LB > −1 ms', 1, 'L')],
        ['H3', ('격자 60셀에서 소스 해시로 추첨한 held-out 셀 중 예측 2 ms 이상', 1, 'L'), ('LB > 0, 관측/예측 0.5~2', 1, 'L')],
        ['H4', ('S 두 조건의 지정 고정 arm 대 auto(탐색적)', 1, 'L'), ('고정 arm − auto의 LB > 0일 때만 적응 기여로 표기', 1, 'L')],
    ]),
    ('h2', '7. 재현성과 무결성'),
    ('p', 'gen-2 측정은 25단계 의존 그래프로 묶고, 단계 지문에 소스와 환경 해시를 넣어 코드가 바뀌면 재사용을 막았다. Go와 Python 정책의 선택은 196,020 격자점 중 386점만 달랐고(비용 차 최대 0.0103 ms) J 차는 최대 0.095 ms였다. 다만 이 격자에 인증서 2,955·9,000·16,000 B, RTT 200 ms, uplink 2 Mbps는 없다. 결과 2,531항목의 재계산 불일치는 0이었다. 봉인 파일 71개는 2026년 11월 5일 다시 해시하여 일치를 확인하였고, v3 네 회차의 판정 223항목을 저널에서 재계산하여 최대 4.4×10⁻¹² ms 차이를 확인하였다. 이 대조는 구현과 계산의 일치를 보는 것이고 성능 근거가 아니다.'),

    ('h1', 'Ⅳ. 연구 결과'),
    ('h2', '1. 연산 비용, first flight, 손실 민감도(RQ1)'),
    ('p', 'ML-KEM-768의 keygen, encapsulation, decapsulation은 각각 24.1, 25.9, 28.2 µs였다(N = 10,000, warm-up 100회 제외). 셋의 합 78.2 µs도 왕복 차이(RTT 50 ms에서 약 50 ms)의 약 1/640이다. Initial 복호 결과 X25519의 first flight는 datagram 1개, 1,280 B(CRYPTO 261 B, PADDING 975 B)이고, X25519MLKEM768은 2개, 2,560 B(CRYPTO 1,447 B, PADDING 1,022 B)였다(n = 10). 서버가 첫 송신 직전까지 받은 바이트의 중앙값도 k·1,280 B와 같았다(n = 24).'),
    ('p', 'TLS over TCP 자료는 warm-up 실패가 분모에 섞여 있어 행별 설계 횟수로 다시 계산하였다(<Table 4>). 연결 독립을 가정한 z에서 ML-KEM-1024만 X25519보다 실패율이 유의하게 높았고, hybrid의 차이는 +0.052%p(95% CI −0.017~0.120)로 검출되지 않았다. 동등성은 검정하지 않았다. 8월 17일 QUIC의 PTO 기록 X25519 12.0%, hybrid 10.4%(z = 0.79)는 같은 결함이 9월 7일 발견되었고 분모와 사건 정의가 남지 않아 판정을 보류한다. 동일 n을 가정하면 n = 2,000에서 z는 1.60이고 8조건 합산 16,000에서는 4.54여서 결론이 분모에 달려 있다. 따라서 둘째 전제는 기각된 것이 아니라 판정되지 않았다.'),
    ('table', 'Table 4. TLS failure rate under loss, warm-up excluded (64,000 attempts per group)', [15000, 9800, 9800, 9800], [
        ['키 교환', '실패 수', '실패율(%)', 'X25519 대비 z'],
        ['X25519', '232', '0.3625', '기준'],
        ['ML-KEM-512', '222', '0.3469', '−0.47'],
        ['ML-KEM-768', '248', '0.3875', '0.73'],
        ['ML-KEM-1024', '370', '0.5781', '5.64'],
        ['X25519MLKEM768', '265', '0.4141', '1.48'],
    ]),
    ('h2', '2. client 바이트와 왕복 수의 규칙(RQ2)'),
    ('p', '무손실 RTT 50 ms에서 인증서를 키우면 중앙값 HCT가 약 55 ms에서 약 105 ms로 뛰는 경계가 나타났다([Fig. 3](a)). 경계는 X25519가 3,300~3,400 B, hybrid가 5,900~6,000 B였고, 노트북의 이분탐색에서도 3,312~3,368 B, 5,917~5,974 B로 재현되었다. 두 경계 사이의 측정점 14개에서 hybrid는 49.0~49.7 ms(평균 49.44 ms, RTT의 98.0~99.4%) 빨랐다. 3,600~4,700 B의 hybrid 측정은 4,032 B뿐이다. hybrid 5,609 B의 첫 실행(n = 200)은 중앙값 105.7 ms였으나 둘째 실행은 55.4 ms였고 3회 반복 300연결에서는 2-RTT가 나오지 않아 원인을 확정하지 못하였다. 5,400 B에서는 3회 모두 100연결 중 1건이 2-RTT였다. 인증서 4,032 B에서 RTT를 10, 50, 100, 200 ms로 바꾸면 격차는 9.5, 49.2, 99.3, 197.8 ms(RTT의 95.0, 98.4, 99.3, 98.9%)였다([Fig. 3](b)). 단일 실행(n = 30)이라 구간 추정은 없다. 구간 밖에서는 hybrid가 0.9~1.4 ms 느렸다(16,000 B에서 0.1 ms).'),
    ('fig', 'fig3_threshold', 140, '[Fig. 3] (a) Median HCT against certificate size (RTT 50 ms, no loss, n = 30); dotted segments have no sweep points and 4,032 B is from the overview sweep. (b) HCT gap against RTT (4,032 B, n = 30) with the gap as a share of RTT; a separate run, 49.2 ms against 49.6 ms in (a)'),
    ('p', '원인이 키 자체인지 바이트 수인지 가르기 위해 키 교환을 고정하고 Initial 크기만 바꾸었다. X25519는 Initial 1,200·1,280 B에서 경계가 3,312~3,368 B였고 1,350·1,450 B에서 4,557~4,614 B였다. hybrid도 5,917~5,974 B에서 7,163~7,219 B로 이동하였다. 1,350 B와 1,450 B가 같은 계단인 점은 연속적인 3B 규칙이 아니라 식 (1)의 계단을 가리킨다([Fig. 4](a)). 이 실험은 padding 길이만 바꾸었으므로 바이트 내용의 영향까지 말하지는 않는다.'),
    ('p', 'W = 1,280 B이면 3B가 P의 배수여서 datagram당 1 B만 늘려도 다음 계단으로 넘어간다. X25519, 인증서 4,218 B에서 Initial을 1,280 B에서 1,281 B로 바꾸자 중앙값이 104.829 ms에서 53.699 ms로, 2-RTT 비율이 15/15에서 0/15로 바뀌었다. hybrid, 인증서 6,937 B에서는 105.718 ms에서 54.774 ms였다(총 +2 B, [Fig. 4](b)). 별도의 400연결 비교(X25519, 인증서 4,032 B)에서 평균 차는 50.876 ± 0.119 ms였다.'),
    ('fig', 'fig4_staircase_cliff', 140, '[Fig. 4] (a) Certificate size at the 2-RTT boundary against received bytes (RTT 50 ms, no loss); open markers are parity arms, and lines are Eq. (1) with the fitted S(n), dotted where no arm was measured. (b) Median HCT at the 1-byte boundary (n = 15; 4,218 B for X25519, 6,937 B for hybrid; drops of 51.1 and 50.9 ms)'),
    ('p', '이 불연속은 quic-go의 송신 판정에 의존한다. 3B가 P의 배수가 아니면 A(B)/B는 3을 넘는다(X25519, Initial 1,350 B에서 모형값 3.79). 소스 코드 기준으로 Cloudflare quiche는 남은 예산으로 datagram을 잘라 보내므로 같은 계단을 기대하기 어렵지만, 측정 원자료가 저장소에 없어 결과로 제시하지 않는다. 일반화할 수 있는 것은 3배 제한과 client 바이트의 관계까지이다.'),
    ('h2', '3. parity의 credit과 복구(RQ3)'),
    ('p', '측정한 12개 설정 모두 식 (2)를 위반하였다. 8개는 k = 1이어서 우변이 0이고, k = 2의 최소 초과는 hybrid, Initial 1,450 B, C = 1,457 B에서 69.0 B(f = 16 B)였다(9월 29일 실행, 실행 간 60~76 B). 따라서 parity는 별도 datagram이어야 하며 "추가 비용 없는 FEC"라는 초기 가설을 폐기하였다. parity 하나는 k = 2에서 약 1,331 B이고, 원본 앞에 두면 uplink 2 Mbps에서 직렬화 5.32 ms(계산값)가 더해진다.'),
    ('p', 'parity datagram은 경계를 밀어 올렸다. X25519는 3,312~3,368 B에서 m = 1에 8,239~8,296 B, m = 2에 11,977~12,034 B로, hybrid는 5,917~5,974 B에서 10,901~10,958 B, 14,583~14,640 B로 이동하였다([Fig. 4](a)의 빈 표식). 서버가 첫 송신 직전까지 받은 바이트의 중앙값도 m = 1에서 X25519 약 2,606 B, hybrid 약 3,892 B로 늘었다. 다만 뒤에 붙는 parity는 uplink가 낮으면 서버 첫 송신보다 늦게 도착한다. hybrid, 인증서 9,000 B, m = 1의 1-RTT 비율은 80, 40, 30, 20, 15, 10 Mbps에서 0.996, 0.972, 0.640, 0.404, 0.212, 0.004였다(8월 26일 실행).'),
    ('p', '복구는 결정적 erasure 주입으로 확인하였다(hybrid, 인증서 2,955 B, n = 40). 중앙값은 기준 51.627 ms에 대해 FEC 없이 첫째 원본을 잃으면 110.182 ms, 둘째 원본을 잃으면 204.985 ms였고, m = 1에서는 각각 51.887, 51.459 ms(복구 40/40)였다. parity까지 잃으면 110.663 ms, parity를 변조하면 110.338 ms(CRC 거절 40/40)로 복구가 일어나지 않았다.'),
    ('p', '네 방법의 비교는 [Fig. 5]와 같다(X25519, k = 1). 평균 HCT는 처리 없음 114.59 ± 4.44, padding 60.27 ± 3.98(+1 B), parity 57.65 ± 1.62(+1,326 B), 결합 52.98 ± 1.70 ms였다. padding은 추가 왕복을 없앴으나 3·RTT를 넘는 대기 4.25%가 남았고, parity는 대기를 없앴으나 12.0%가 2-RTT였다. parity가 유실되거나 복구에 쓰이면 credit이 줄기 때문이다. 결합의 평균은 parity보다 4.67 ± 2.35 ms, padding보다 7.28 ± 4.32 ms 작았고, padding과 parity의 차이 2.61 ± 4.29 ms는 구별되지 않았다. 코드 판이 다른 네 번의 실행에서 평균의 순서는 유지되었다.'),
    ('fig', 'fig5_levers', 140, '[Fig. 5] HCT at 5% client-to-server loss (X25519, 4,032 B, RTT 50 ms, n = 400 per method). (a) Share of connections slower than t (log-log); dotted lines mark 1.5·RTT and 3·RTT. Above 150 ms, 3/400 (padding + parity) and 0/400 (parity) are not separable (Fisher exact p = 0.25). (b) Mean HCT with 95% half-width and added median first-flight bytes; open markers send parity'),
    ('p', '모형은 고정 m 비교로 대조하였다. m = 2에서 4로 늘릴 때의 이득(실측/모형)은 51.82 ± 0.11/50.00 ms(무손실, 인증서 16,000 B), 33.18 ± 8.65/23.57 ms(burst 3), 11.19 ± 4.56/11.23 ms(경계 위), 10.41 ± 2.54/8.31 ms(2 Mbps, 15%)였다. 2 Mbps, 손실 2%의 0.19 ± 1.07/0.15 ms는 판정불능이다(arm당 95,473 필요). 허용 범위는 비율 0.5~2배이므로 정밀 일치를 뜻하지 않고, burst 3의 예측은 실측 구간 밖이며, 기대 라운드 항은 이전 검사가 실패한 뒤 넣은 것이어서 독립 검증이 아니다.'),
    ('h2', '4. gen-2 정책 검증(RQ4)'),
    ('p', '25단계의 첫 판정은 통과 17, 실패 7, 미실행 1이었고 실패 단계의 내용은 <Table 5>와 같다. regret은 hybrid, 인증서 2,955·9,000 B, 손실 0·2·5%, arm당 4,000연결에서 최대 +1.10 ± 0.47 ms였으나, 보수적인 짝 block 진단에서는 3조건이 판정불능이었다. 손실 2%↔15% 전환에서 oracle 이득(손실 구간별 최선 arm이 최선 단일 고정 arm보다 빠른 값)은 큰 인증서가 1.167 ± 1.275 ms(판정불능), 나머지 세 조건이 0.21 ms 이하였고, auto는 큰 인증서에서 최선 고정 arm보다 3.75 ms 느렸다. X25519, 인증서 4,032 B 무손실에서 auto는 δ = 1 단독을 고르지 않았다. padding이 이기려면 π < 4.98×10⁻⁵이어야 하는데 추정기 하한이 4.95×10⁻³이기 때문이다. 그 결과 auto는 연결당 1,261.4 B를, padding 고정은 1.0 B를 더 보냈고 후반 평균은 둘 다 51.376 ms였다.'),
    ('table', 'Table 5. Steps that failed the first verdict of the gen-2 run (10-01 to 10-02)', [3100, 11300, 15200, 14800], [
        ['단계', '측정 대상', '결과', '해석과 조치'],
        ['p8', ('초기 10회가 평균을 미는 정도', 1, 'L'), ('순서 효과 1.09 ms, 기준 1 ms 초과', 1, 'L'), ('기준 근처 잡음. 구간 평균 영향 상한 0.024 ms', 1, 'L')],
        ['p10', ('극한 조건 안정성', 1, 'L'), ('RTT 5 ms 여유 2.34 < 3×흔들림 0.89', 1, 'L'), ('RTT 5 ms에서 분해능 부족. 11/12 완주', 1, 'L')],
        ['p15', ('δ·m auto의 regret', 1, 'L'), ('regret 기준 통과, 최대 반폭 1.30 ms', 1, 'L'), ('정밀도 미달. 표본 부족', 1, 'L')],
        ['p16', ('직렬화 비용 청구 방식', 1, 'L'), ('첫 판 4/6, 같은 소스 재측정 6/6', 1, 'L'), ('block 표류 0.39~0.75 ms와 같은 크기, 통과도 미확정', 1, 'L')],
        ['p17', ('손실 전환에서 적응 이득', 1, 'L'), ('큰 인증서 적중(허용 arm 선택) 22.0%(이전 실행 40.3%), 적응까지 중앙값 194.5/450연결', 1, 'L'), ('3구간부터 관측 4~6개로 π 추정 고착', 1, 'L')],
        ['p18', ('고정 m으로 모형 대조', 1, 'L'), ('74,000회 중 실패 5회로 불완전', 1, 'L'), ('성공 조건부 평균이 m = 1에 유리', 1, 'L')],
        ['p20', ('모형 잔차', 1, 'L'), ('108쌍 중 부호 반대 0, 표본 부족 19', 1, 'L'), ('미세 순서는 표본 부족으로 판정 못함', 1, 'L')],
    ]),
    ('h2', '5. v3.0과 v3.1의 봉인 측정(RQ4)'),
    ('p', '큰 인증서, 손실 2%의 평균 HCT는 고정 arm (δ, ℓ, T) = (0, 0, 1)이 119.61 ms, (0, 3, 1)이 81.62 ms였다(−38.00 ms, 95% CI −39.50~−36.49). 첫 판정법 M1은 client 집계 결함으로 규칙상 실패하였고, 서버 기록으로 다시 봉인한 M1′(문턱 0.90은 M1 값을 본 뒤 결정)을 통과하였다. 서버가 집계한 앞 parity(credit)가 3개인 376연결은 모두 1-RTT(기준 101.2 ms), 2개인 24연결은 모두 아니었다. 대가로 first flight uplink가 3,892 B에서 7,888 B로 늘었다. (0, 0, 1)에 비해 credit만으로는 손실 2%에서 30.42 ms 빨라졌고 15%에서 16.23 ms 느려졌으며, 여기에 복구 parity를 더하면 각각 6.89, 41.04 ms 더 빨라졌다. 저손실 이득의 대부분은 credit 바이트의 위치와 수에서 왔다.'),
    ('table', 'Table 6. Sealed verdicts by generation (ms; H4: fixed arm − auto)', [9400, 17500, 17500], [
        ['항목', 'v3.0 (10월 2일)', 'v3.1 (10월 2~3일)'],
        ['B_h', '3.58', '3.10'],
        ['H1 큰 인증서', '28.18 (LB 22.88), 2회차 29.85', '28.01 (LB 24.33), 2회차 28.92'],
        ['H1 RTT 200', '11.35 (LB 9.24), 2회차 11.23', '12.38 (LB 10.76), 2회차 10.33'],
        ['H1 판정', '성립', '성립'],
        ['H2', '실패: 비열등 17, 열등 1', '실패: 비열등 17, 판정불능 1'],
        ['H3', '통과(대상 1셀, 비율 1.15)', '실패(4셀 중 1셀 미달, 비율 4.85)'],
        ['H4', '미확인(−3.99, −0.43)', '미확인(−3.80, +0.73)'],
    ]),
    ('p', '<Table 6>에서 두 세대 모두 미리 지정한 두 조건의 개선은 2회차까지 재현되었다. [Fig. 6]은 1회차이며 18조건 중 v3.0은 8개, v3.1은 10개를 그렸고, 그리지 않은 조건의 95% 하한은 모두 −1 ms 위이다. RTT 200 ms 조건의 이득은 손실 15% 층에서 나왔고 2% 층은 네 회차 모두 −0.19~−0.59 ms였다. v3.0은 held-out 셀(6,000 B, RTT 80 ms, 10 Mbps)에서 94.28 대 140.14 ms로 45.86 ms 느렸다(95% CI −58.08~−33.64). uplink 제한 probe에서 서버 첫 송신이 41 B datagram으로 시작하여 δ = 1의 여유 6 B를 넘는 것을 바이트 단위로 확인하였으나, 이것이 ACK 전용이라는 것은 해석이고 실패 셀 전부를 설명하지는 못한다. v3.1은 이를 반영하여 새 held-out 셀로 다시 봉인하였다. RTT 120 ms 셀 중 5 Mbps(12,000, 14,000 B)는 254.38 대 135.47 ms, 253.61 대 136.59 ms로 예측 114.75 ms와 맞았으나, 6,000 B, 10 Mbps는 +19.74 ms(95% CI −5.22~44.70)로 판정불능이었다. 고정 arm − auto의 LB가 0을 넘지 못하여 적응 기여는 두 세대 모두 미확인이다. 연결당 서버 수신 바이트(gen-2/v3.1)는 큰 인증서에서 6,717/9,807 B, RTT 200 ms에서 16,684/16,860 B였다.'),
    ('fig', 'fig6_forest', 140, '[Fig. 6] Generation contrast in run 1 with unadjusted 95% intervals on a signed log axis, sign(Δ)·log10(1 + |Δ|). Shown (8 of 18 conditions for v3.0, 10 of 18 for v3.1): all primary conditions, four of twelve carried-over conditions and the uplink-limited held-out cells. Rows use hybrid unless marked (*: X25519; †: burst 3); a↔b alternates between loss rates'),
    ('h2', '6. 실측 없는 개발본'),
    ('p', 'v3.2-dev와 v3.3.1-dev는 네트워크 측정이 없다. v3.3.1-dev는 서버의 datagram 도착 회신(C1)이 없는 목적지에서 v3.2-dev와 같은 결정을 하도록 설계하였고 재생 411,000단계에서 일치하였다. C1 비용을 0으로 가정한 개발용 사건 시뮬레이션 15개 시나리오 중 넷은 기대 비용이 1.14~3.64 ms/연결 낮았고 하나는 0.16 ms 높았다. 이는 결과 일부를 본 뒤의 사후 분석이고 시뮬레이터가 정책 상수를 공유하므로 성능 근거로 쓰지 않는다.'),

    ('h1', 'Ⅴ. 고찰'),
    ('h2', '1. 결과의 해석'),
    ('p', '두 경계 사이에서 hybrid가 빠른 것은 큰 key share가 padding처럼 예산을 늘린 결과로 해석된다. X25519의 3B는 3,840 B, hybrid는 7,680 B이다. PQC를 적용하면 handshake가 느려진다는 예상은 인증서 크기와 RTT에 따라 성립하지 않을 수 있다. 다만 이 구간은 W = 1,280 B와 quic-go에 한정되고, 같은 효과를 padding(4,557 B까지)과 parity로도 얻으므로 ML-KEM 고유의 이점은 아니다. RTT 0.1 ms 미만의 측정{c:kempf}으로는 이 왕복 차이가 드러나지 않으므로, 전송 비용 평가는 실제 망에 가까운 RTT를 포함해야 한다.'),
    ('p', 'parity는 padding을 지배하지 않는다. X25519, 손실 5%에서 둘의 평균은 구별되지 않았고(padding +1 B, parity +1,326 B), 복구에 쓰인 parity는 credit에서 빠지므로 하나의 parity가 두 이득을 동시에 주지 못한다. 저손실 이득의 대부분은 padding에 가까운 기제이며, 복구 parity를 더한 효과는 손실이 클 때 커졌다(2% 6.89 ms, 15% 41.04 ms). 같은 바이트의 padding과 비교한 값은 아직 없다. Langley 등이 XOR FEC를 제거한 이유{c:langley}를 고려하면, 범위를 첫 왕복으로 좁힌 본 정책도 복구 이득과 바이트 비용을 함께 보아야 한다.'),
    ('p', '과제명이 가정한 "손실률 적응" 이득은 확인되지 않았다. 탐색적 네 조건 중 왕복을 없앤 셋은 m = 3 고정으로 충분하였고 큰 인증서만 갈렸다. gen-2는 m = 0 연결에서만 배워 관측이 구간당 대체로 2~6개뿐이어서 추정치가 전환을 따라가지 못하였다. 99% 안팎의 적중률도 전이점이 낮아 고정 arm이 같은 값을 내는 경우였으므로 적응의 증거로 쓰지 않는다. datagram 단위 도착 증거가 개선 방향이지만 현재 근거는 시뮬레이션뿐이다.'),
    ('h2', '2. 연구의 한계'),
    ('p', '첫째, 구현이 quic-go v0.61.0 하나이고 Initial congestion window가 32 packet이다. RFC 9002의 권장값은 10 packet이므로{c:rfc9002} 큰 인증서 결과에는 이 단서가 붙는다. 둘째, 테스트베드는 한 기계 안의 합성 링크이며 실제 경로, 혼잡, 재정렬을 포함하지 않았고 손실은 client→server 방향에 한정된다. 셋째, session ticket과 NEW_TOKEN을 쓰지 않는 첫 접속만 다루었다. 넷째, credit은 서버의 수신 집계에 의존하고 복구는 서버 decoder가 필요하므로 client만 바꾸어 얻는 이득이 아니며, 혼잡 제어와 공정성은 측정하지 않았다. 다섯째, 8월 TLS는 실행 스크립트가 없어 netem 방향을 확정할 수 없고 burst 라벨은 전이확률이어서 실제 손실은 0.99~9.09%이다. 여섯째, s0와 c는 FEC arm을 포함해 fit한 값이므로 [Fig. 4](a)의 일치는 표본 내 일치이다. 일곱째, parity 크기를 1,452 B로 제한하면 k = 2에서 W ≥ 1,402 B일 때 parity 후보가 사라진다. 구현과 분석의 상당 부분에 생성형 AI를 사용하였으므로 수치는 원자료와 대조하였으나, 사람이 코드를 줄 단위로 검증한 것은 아니다.'),
    ('h2', '3. 연구의 의의와 기대효과'),
    ('p', '본 연구는 알려진 두 사실, 곧 3배 제한의 왕복 비용과 client 바이트로 예산을 늘리는 수단을 잇는 padding의 parity 대체를 구현하고 그 비용을 측정하였다(같은 바이트 비교는 후속 과제). quic-go 조건에서 지연이 연산 속도보다 first flight 바이트에 달려 있음을 인증서 크기와 RTT별 수치로 보였고, gen-2 이후 도구와 판정 기록을 해시와 함께 남겼다. 이 수치는 PQC 전환을 검토할 때 지연 변화를 일률적으로 가정하지 말고 인증서 크기와 RTT를 함께 재야 한다는 근거의 하나이다. 참여 학생은 전제가 틀렸을 때 방향을 바꾸고, 부정 결과를 지우지 않으며, 판정 기준을 측정 전에 고정하는 절차를 경험하였다.'),

    ('h1', 'Ⅵ. 결론'),
    ('p', 'RQ1: ML-KEM-768 연산은 수십 µs였고 변한 것은 first flight 바이트이며, QUIC 손실 취약성은 판정을 보류하였다. RQ2: 왕복 수는 client 송신 바이트로 정해지는 서버 예산이 결정하며, quic-go에서 그 예산은 1,280 B 단위 계단이어서 경계에서는 datagram당 1 B로 왕복 하나가 사라졌다. 인증서 4,032 B에서는 hybrid가 RTT의 95.0~99.3% 빨랐다. RQ3: padding 자리의 parity는 12개 설정(8개는 k = 1)에서 식 (2)를 위반하였고, 별도 datagram parity(k = 2에서 약 1,331 B)는 경계를 올리고 erasure를 복구하였다. X25519, 손실 5%에서 parity 단독은 padding과 구별되지 않았고 결합은 평균 HCT를 114.59 ms에서 52.98 ms로 줄였다. RQ4: v3.0과 v3.1은 미리 정한 두 조건에서 gen-2보다 빨랐으나, H2(v3.0은 열등 1셀, v3.1은 판정불능 1셀)와 v3.1의 H3은 성립하지 않았고 H4는 미확인이다.'),
    ('p', '후속 연구는 측정기를 고친 손실 취약성 재측정, 같은 바이트의 padding과 parity 비교, v3.3.1-dev의 봉인 측정, 다른 QUIC 구현과 실제 경로에서의 재현, Initial congestion window 10과 PQC 서명 인증서 조건, 혼잡 제어 영향 측정 순으로 진행한다.'),
]

REFS = {
    'rfc9000': 'Iyengar, J., & Thomson, M. (Eds.). (2021). QUIC: A UDP-based multiplexed and secure transport (RFC 9000). IETF. https://doi.org/10.17487/RFC9000',
    'rfc9001': 'Thomson, M., & Turner, S. (Eds.). (2021). Using TLS to secure QUIC (RFC 9001). IETF. https://doi.org/10.17487/RFC9001',
    'rfc9002': 'Iyengar, J., & Swett, I. (Eds.). (2021). QUIC loss detection and congestion control (RFC 9002). IETF. https://doi.org/10.17487/RFC9002',
    'rfc9846': 'Rescorla, E. (2026). The Transport Layer Security (TLS) protocol version 1.3 (RFC 9846). IETF. https://doi.org/10.17487/RFC9846',
    'fips203': 'National Institute of Standards and Technology. (2024). Module-lattice-based key-encapsulation mechanism standard (FIPS 203). https://doi.org/10.6028/NIST.FIPS.203',
    'rfc10024': 'Kwiatkowski, K., Kampanakis, P., Westerbaan, B. E., & Stebila, D. (2026). Post-quantum traditional (PQ/T) hybrid key agreement mechanisms for TLS 1.3 (RFC 10024). IETF. https://doi.org/10.17487/RFC10024',
    'nawrocki': 'Nawrocki, M., Tehrani, P. F., Hiesgen, R., Mücke, J., Schmidt, T. C., & Wählisch, M. (2022). On the interplay between TLS certificates and QUIC performance. Proc. ACM CoNEXT \'22, 204-213. https://doi.org/10.1145/3555050.3569123',
    'kampanakis': 'Kampanakis, P., & Lepoint, T. (2023). Vision paper: Do we need to change some things? SSR 2023, LNCS 13895, 78-102. https://doi.org/10.1007/978-3-031-30731-7_4',
    'mcmanus': 'McManus, P. (2020, May 18). Does the QUIC handshake require compression to be fast? Fastly Blog. https://www.fastly.com/blog/quic-handshake-tls-compression-certificates-extension-study',
    'cf2022': 'Westerbaan, B., & Rubin, C. D. (2022, October 3). Defending against future threats: Cloudflare goes post-quantum. Cloudflare Blog. https://blog.cloudflare.com/post-quantum-for-all/',
    'kempf': 'Kempf, M., Gauder, N., Jaeger, B., Zirngibl, J., & Carle, G. (2024). A quantum of QUIC: Dissecting cryptography with post-quantum insights. IFIP Networking 2024, 195-203. https://doi.org/10.23919/IFIPNetworking62109.2024.10619916',
    'paquin': 'Paquin, C., Stebila, D., & Tamvada, G. (2020). Benchmarking post-quantum cryptography in TLS. PQCrypto 2020, LNCS 12100, 72-91. https://doi.org/10.1007/978-3-030-44223-1_5',
    'montenegro': 'Montenegro, J. A., Rios, R., & Bonilla, J. (2026). Comparative analysis of post-quantum handshake performance in QUIC and TLS protocols. Computer Networks, 275, 111957. https://doi.org/10.1016/j.comnet.2025.111957',
    'sakk': 'Sakk, E., Xu, G., Mao, J., & Wang, S. (2026). Evaluating post-quantum cryptography in IoT networks: Communication, fragmentation, and reliability. Future Internet, 18(6), 316. https://doi.org/10.3390/fi18060316',
    'herzinger': 'Herzinger, D., Thomas, M., Handirk, T., Gazdag, S.-L., Loebenberger, D., & Margraf, M. (2026). Embedding large PQC KEMs in IKEv2 (preprint). https://arxiv.org/abs/2610.32356',
    'langley': 'Langley, A., et al. (2017). The QUIC transport protocol: Design and Internet-scale deployment. Proc. ACM SIGCOMM \'17, 183-196. https://doi.org/10.1145/3098822.3098842',
    'quicfec': 'Michel, F., De Coninck, Q., & Bonaventure, O. (2019). QUIC-FEC: Bringing the benefits of forward erasure correction to QUIC. IFIP Networking 2019, 1-9. https://doi.org/10.23919/IFIPNetworking.2019.8816838',
    'rquic': 'Garrido, P., Sanchez, I., Ferlin, S., Aguero, R., & Alay, O. (2019). rQUIC: Integrating FEC with QUIC for robust wireless communications. IEEE GLOBECOM 2019, 1-7. https://doi.org/10.1109/GLOBECOM38437.2019.9013401',
    'rfc9265': 'Kuhn, N., Lochin, E., Michel, F., & Welzl, M. (2022). Forward erasure correction (FEC) coding and congestion control in transport (RFC 9265). IRTF. https://doi.org/10.17487/RFC9265',
    'bolot': 'Bolot, J.-C., Fosse-Parisis, S., & Towsley, D. (1999). Adaptive FEC-based error control for Internet telephony. IEEE INFOCOM \'99, 3, 1453-1460. https://doi.org/10.1109/INFCOM.1999.752166',
    'boutremans': 'Boutremans, C., & Le Boudec, J.-Y. (2003). Adaptive joint playout buffer and FEC adjustment for Internet telephony. IEEE INFOCOM 2003, 1, 652-662. https://doi.org/10.1109/INFCOM.2003.1208715',
    'gilbert': 'Gilbert, E. N. (1960). Capacity of a burst-noise channel. Bell System Technical Journal, 39(5), 1253-1265. https://doi.org/10.1002/j.1538-7305.1960.tb03959.x',
    'elliott': 'Elliott, E. O. (1963). Estimates of error rates for codes on burst-noise channels. Bell System Technical Journal, 42(5), 1977-1997. https://doi.org/10.1002/j.1538-7305.1963.tb00955.x',
    'reed': 'Reed, I. S., & Solomon, G. (1960). Polynomial codes over certain finite fields. Journal of the SIAM, 8(2), 300-304. https://doi.org/10.1137/0108018',
    'quicgo': 'quic-go contributors. quic-go (Version 0.61.0) [Computer software]. https://github.com/quic-go/quic-go',
    'liboqs': 'Open Quantum Safe. liboqs-python (Version 0.15.0) [Computer software]. https://github.com/open-quantum-safe/liboqs-python',
}
