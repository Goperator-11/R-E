#!/bin/bash
# ML-KEM 동일성 확인 - 크기와 상호운용.
#
# 인수인계 문서의 환경에는 OpenSSL 3.5 가 있다. 우리 Go 구현이 그것과
# 같은 ML-KEM 인지, 말이 아니라 두 가지로 보인다.
#   1) FIPS 203 이 정한 크기가 나오는가
#   2) Go 클라이언트가 OpenSSL 서버와 X25519MLKEM768 로 핸드셰이크를 끝내는가
#      (서로 다른 두 구현이 같은 비밀에 도달해야만 끝난다)
set -u
D=/tmp/mlkem
rm -rf "$D"
mkdir -p "$D"
cd "$D" || exit 2

# WSL 은 세션이 내려가면 /tmp 를 비운다. 없으면 빌드본에서 복사한다.
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
# SubjectPublicKeyInfo 안에 1184 B 캡슐화키가 들어 있어야 한다
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
    # 문서 6절: 모든 실행에 timeout 을 붙인다
    timeout 30 /tmp/mlkemcheck -addr 127.0.0.1:44443 -group "$GRP"
    RC=$?
    kill "$SRV" 2>/dev/null
    wait "$SRV" 2>/dev/null
    echo "  ($GRP) exit=$RC"
    sleep 0.4
done
