#!/usr/bin/env bash
# ============================================================
#  R&E 2단계 관문 확인 스크립트
#  ML-KEM + QUIC 실험 환경이 학교 서버에서 구성 가능한지 점검
#  사용법:  bash check_env.sh
#  ※ 아무것도 설치하지 않습니다. 확인만 합니다.
# ============================================================
ok(){   printf "  \033[32m[OK]\033[0m   %s\n" "$1"; }
ng(){   printf "  \033[31m[없음]\033[0m %s\n" "$1"; }
warn(){ printf "  \033[33m[주의]\033[0m %s\n" "$1"; }
hd(){   printf "\n\033[1m%s\033[0m\n" "$1"; }

echo "============================================================"
echo " R&E 2단계 환경 점검  ·  $(date '+%Y-%m-%d %H:%M')"
echo "============================================================"

hd "0. 시스템"
echo "  호스트 : $(hostname)"
echo "  OS     : $(. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME")"
echo "  커널   : $(uname -r)"
echo "  CPU    : $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | xargs)"
echo "  코어   : $(nproc)   메모리: $(free -h | awk '/Mem:/{print $2}')"
echo "  ※ 위 CPU/메모리는 논문 '측정 환경' 절에 그대로 기재하세요."

hd "1. OpenSSL — ML-KEM 지원 (★ 가장 중요)"
if command -v openssl >/dev/null 2>&1; then
  V=$(openssl version | awk '{print $2}')
  echo "  설치된 버전: $V"
  MAJ=${V%%.*}; MIN=$(echo "$V" | cut -d. -f2)
  if [ "$MAJ" -gt 3 ] || { [ "$MAJ" -eq 3 ] && [ "$MIN" -ge 5 ]; }; then
    ok "3.5 이상 — ML-KEM 네이티브 지원"
  else
    ng "3.5 미만 — 순수 ML-KEM-512/768/1024 스윕 불가"
    warn "Ubuntu 24.04/Debian 12 기본값은 3.0입니다. 소스 빌드 또는 oqs-provider 필요"
  fi
  echo "  -- 사용 가능한 그룹에서 MLKEM 검색 --"
  G=$(openssl list -tls-groups 2>/dev/null | grep -i mlkem)
  if [ -n "$G" ]; then echo "$G" | sed 's/^/    /'; ok "ML-KEM 그룹 확인됨"
  else ng "ML-KEM 그룹 없음"; fi
else
  ng "openssl 명령 없음"
fi

hd "2. Go — quic-go (FEC 프로토타입용)"
if command -v go >/dev/null 2>&1; then
  GV=$(go version | awk '{print $3}' | sed 's/go//')
  echo "  설치된 버전: $GV"
  GMAJ=$(echo "$GV" | cut -d. -f1); GMIN=$(echo "$GV" | cut -d. -f2)
  if [ "$GMAJ" -gt 1 ] || { [ "$GMAJ" -eq 1 ] && [ "$GMIN" -ge 24 ]; }; then
    ok "1.24 이상 — crypto/tls가 X25519MLKEM768 기본 지원"
  else
    ng "1.24 미만 — X25519MLKEM768 미지원. Go 업그레이드 필요"
  fi
else
  ng "go 명령 없음"
fi

hd "3. 네트워크 모사 도구 (NetEm / tc)"
command -v tc >/dev/null 2>&1 && ok "tc 있음 ($(tc -V 2>&1 | head -1))" || ng "tc 없음 (iproute2 필요)"
if lsmod 2>/dev/null | grep -q sch_netem; then ok "sch_netem 모듈 적재됨"
elif modinfo sch_netem >/dev/null 2>&1; then warn "sch_netem 모듈 있으나 미적재 (첫 tc 사용 시 자동 적재)"
else ng "sch_netem 모듈 없음"; fi
echo "  -- 버스트 손실(Gilbert-Elliott) 지원 여부 --"
unshare -Urn sh -c 'ip link set lo up && tc qdisc add dev lo root netem loss gemodel 1% 50%' 2>/dev/null \
  && ok "격리된 네임스페이스에서 gemodel 지원 확인" \
  || warn "격리된 gemodel 시험 실패 (user namespace 또는 netem 사용 가능 여부 확인 필요)"

hd "4. 권한 — tc는 root 또는 CAP_NET_ADMIN 필요"
if [ "$(id -u)" -eq 0 ]; then ok "root로 실행 중"
elif sudo -n true 2>/dev/null; then ok "무암호 sudo 사용 가능"
else warn "sudo 확인 필요 — 안 되면 선생님께 권한 요청하거나 네트워크 네임스페이스 사용" ; fi

hd "5. 빌드 도구 (ngtcp2 소스 빌드용)"
for t in gcc g++ cmake make git pkg-config autoconf libtool; do
  command -v $t >/dev/null 2>&1 && ok "$t" || ng "$t"
done

hd "6. 패킷 관측"
command -v tshark  >/dev/null 2>&1 && ok "tshark 있음"  || warn "tshark 없음 (qlog로 대체 가능)"
command -v tcpdump >/dev/null 2>&1 && ok "tcpdump 있음" || warn "tcpdump 없음"

hd "7. 1단계 재현성 확인"
python3 - <<'PY' 2>/dev/null || echo "  liboqs-python 미설치 또는 python3 없음"
try:
    import oqs, platform
    print("  liboqs-python:", getattr(oqs, "__version__", "?"))
    print("  liboqs core  :", oqs.oqs_version())
    print("  Python       :", platform.python_version())
    print("  ML-KEM 지원  :", [m for m in oqs.get_enabled_kem_mechanisms() if "ML-KEM" in m])
except Exception as e:
    print("  오류:", e)
PY

echo ""
echo "============================================================"
echo " 판정 기준"
echo "   · 1번이 OK        → ngtcp2+OpenSSL 경로 진행 가능 (512/768/1024 스윕)"
echo "   · 2번이 OK        → quic-go 경로 진행 가능 (FEC 프로토타입)"
echo "   · 3·4번이 OK      → NetEm 실험 가능"
echo "   · 1·2 모두 NG     → 진행 불가. 선생님과 환경 구성 협의 필요"
echo "============================================================"
