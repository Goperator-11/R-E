# qamp.go 패치 2 — 클라이언트 Initial 패킷 크기 조절 (-initpkt 플래그)
import re
raise SystemExit("Historical patch disabled: build the maintained qamp.go directly; certificate size and -initpkt are already integrated.")
p='qamp.go'; s=open(p).read()

# 클라이언트 함수 시그니처에 ips 추가
s=s.replace('func runClient(addr, group string, n int) {',
            'func runClient(addr, group string, n, ips int) {')
# Dial 의 quic.Config 에 InitialPacketSize 주입
s=s.replace('''		conn, err := tr.Dial(ctx, raddr, tlsConf, &quic.Config{
			HandshakeIdleTimeout:    5 * time.Second,''',
'''		qc := &quic.Config{
			HandshakeIdleTimeout:    5 * time.Second,''')
s=s.replace('''			MaxIdleTimeout:          30 * time.Second,
			DisablePathMTUDiscovery: true,
		})
		el := float64(time.Since(t0).Microseconds()) / 1000.0''',
'''			MaxIdleTimeout:          30 * time.Second,
			DisablePathMTUDiscovery: true,
		}
		if ips > 0 {
			qc.InitialPacketSize = uint16(ips)
		}
		conn, err := tr.Dial(ctx, raddr, tlsConf, qc)
		el := float64(time.Since(t0).Microseconds()) / 1000.0''')
# main 에 플래그
s=s.replace('\tcertSize := flag.Int("certsize", 0, "서버 인증서 목표 크기(B)")',
            '\tcertSize := flag.Int("certsize", 0, "서버 인증서 목표 크기(B)")\n\tips := flag.Int("initpkt", 0, "클라이언트 Initial 패킷 크기(B, 1200~1472). 0이면 기본")')
s=s.replace('\t\trunClient(*addr, *group, *n)','\t\trunClient(*addr, *group, *n, *ips)')
open(p,'w').write(s); print("패치 완료")
