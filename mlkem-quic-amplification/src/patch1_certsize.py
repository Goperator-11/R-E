import re
raise SystemExit("Historical patch disabled: build the maintained qamp.go directly; certificate size and -initpkt are already integrated.")
p='qamp.go'; s=open(p).read()

s=s.replace('\t"crypto/x509/pkix"\n', '\t"crypto/x509/pkix"\n\t"encoding/asn1"\n')

old=re.search(r'func genCert\(\).*?\n}\n', s, flags=re.S).group(0)
new='''func makeCert(target int) (tls.Certificate, int) {
	build := func(pad int) ([]byte, *ecdsa.PrivateKey) {
		key, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
		tmpl := x509.Certificate{
			SerialNumber: big.NewInt(1),
			Subject:      pkix.Name{CommonName: "localhost"},
			NotBefore:    time.Now().Add(-time.Hour),
			NotAfter:     time.Now().Add(24 * 365 * time.Hour),
			DNSNames:     []string{"localhost"},
		}
		if pad > 0 {
			blob := make([]byte, pad)
			rand.Read(blob)
			tmpl.ExtraExtensions = []pkix.Extension{{
				Id:    asn1.ObjectIdentifier{1, 3, 6, 1, 4, 1, 99999, 1},
				Value: blob,
			}}
		}
		der, err := x509.CreateCertificate(rand.Reader, &tmpl, &tmpl, &key.PublicKey, key)
		if err != nil {
			log.Fatal(err)
		}
		return der, key
	}
	base, _ := build(0)
	pad := 0
	if target > len(base) {
		pad = target - len(base)
	}
	der, key := build(pad)
	if diff := target - len(der); pad > 0 && diff != 0 && pad+diff > 0 {
		der, key = build(pad + diff)
	}
	return tls.Certificate{Certificate: [][]byte{der}, PrivateKey: key}, len(der)
}
'''
s=s.replace(old,new)

s=s.replace('func runServer(addr, group string) {','func runServer(addr, group string, certSize int) {')
s=s.replace('Certificates:           []tls.Certificate{genCert()},',
            'Certificates:           []tls.Certificate{cert},')
s=s.replace('\tua, err := net.ResolveUDPAddr("udp", addr)',
            '\tcert, actualSize := makeCert(certSize)\n\tua, err := net.ResolveUDPAddr("udp", addr)')
s=s.replace('fmt.Printf("서버 기동: %s  group=%s\\n", addr, group)',
            'fmt.Printf("서버 기동: %s  group=%s  인증서=%dB (목표 %dB)\\n", addr, group, actualSize, certSize)')

s=s.replace('\tn := flag.Int("n", 5, "반복 횟수")',
            '\tn := flag.Int("n", 5, "반복 횟수")\n\tcertSize := flag.Int("certsize", 0, "서버 인증서 목표 크기(B)")')
s=s.replace('\t\trunServer(*addr, *group)','\t\trunServer(*addr, *group, *certSize)')

open(p,'w').write(s); print("패치 완료")
