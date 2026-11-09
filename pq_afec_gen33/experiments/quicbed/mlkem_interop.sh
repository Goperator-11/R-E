#!/bin/bash
set -u
D=/tmp/mlkem
rm -rf "$D"
mkdir -p "$D"
cd "$D" || exit 2

for B in qamp mlkemcheck; do
    if [ ! -x "/tmp/$B" ] && [ -x "$HOME/quicbed/bin/$B" ]; then
        cp "$HOME/quicbed/bin/$B" "/tmp/$B"
    fi
done

echo "=== 도구 버전 ==="
openssl version
echo

echo "=== ML-KEM-768 키/암호문 크기 (FIPS 203) ==="
openssl genpkey -algorithm ML-KEM-768 -out mk.pem 2>/dev/null
openssl pkey -in mk.pem -pubout -out mkpub.pem 2>/dev/null
python3 - <<'PYEOF'
import base64
raw = open("/tmp/mlkem/mkpub.pem").read()
b = base64.b64decode("".join(l for l in raw.splitlines()
                             if not l.startswith("-----")))
print("  OpenSSL ML-KEM-768 공개키 DER = %d B" % len(b))
print("  기대: ASN.1 머리(약 20 B) + 캡슐화키 1184 B")
print("  캡슐화키 1184 B 포함 여부: %s" % ("예" if len(b) >= 1184 else "아니오"))
PYEOF
echo

echo "=== OpenSSL 이 X25519MLKEM768 을 지원하는가 ==="
openssl list -tls1_3-kem-algorithms 2>/dev/null | head -5
openssl list -kem-algorithms 2>/dev/null | grep -i mlkem | head -3
echo

echo "=== 상호운용: OpenSSL 3.5 서버 <-> Go crypto/tls 클라이언트 ==="
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem \
    -days 2 -nodes -subj "/CN=mlkem.test" >/dev/null 2>&1

for GRP in X25519MLKEM768 x25519; do
    OSSLGRP="$GRP"
    if [ "$GRP" = "x25519" ]; then OSSLGRP="X25519"; fi
    openssl s_server -accept 44443 -cert cert.pem -key key.pem \
        -groups "$OSSLGRP" -tls1_3 -naccept 1 -quiet \
        >"$D/srv_$GRP.log" 2>&1 &
    SRV=$!
    sleep 1.2
    timeout 30 /tmp/mlkemcheck -addr 127.0.0.1:44443 -group "$GRP"
    RC=$?
    kill "$SRV" 2>/dev/null
    wait "$SRV" 2>/dev/null
    echo "  ($GRP) exit=$RC"
    sleep 0.4
done
