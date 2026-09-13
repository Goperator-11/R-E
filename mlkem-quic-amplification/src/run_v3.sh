#!/usr/bin/env bash
# ============================================================
#  확장 스윕 (B) — veth 링크 + MTU 1500 + 타임아웃
#
#  중첩 네트워크 네임스페이스로 veth 양끝을 분리한다.
#  loopback은 MTU 변경이 커널에서 무시되므로(exit=0이나 미적용)
#  실제 이더넷처럼 동작하는 veth 링크를 쓴다.
#
#    [기본 ns]  v0 10.9.0.1  <---- veth ---->  v1 10.9.0.2  [peer ns]
#       클라이언트(hct_v2)                        서버(s_server)
#
#  netem은 v0(송신측)에 걸어 단방향으로 적용 → delay = RTT (loopback과 달리 2배 아님)
#
#  2026-09-07 코드 감사에서 고친 것 (sweep2 자료는 수정 전 스크립트로 잰 것이다 -
#  README 「데이터 주의」 참고):
#   1. burst 모델의 gemodel 첫 인자를 손실률 그대로 넣으면 실제 손실이
#      p/(p+r) = L/(L+50) 로 약 2 배가 된다(5 -> 9.09%). r=50% 를 고정하고
#      p = L*r/(100-L) 로 역산해 표기 손실과 실제 손실을 맞춘다.
#   2. summary.csv 에 netem_sides 와 effective_loss_pct 열을 더한다.
#   3. NETEM_SIDES=both 를 주면 실험환경 명세서 §3-1·§4-2 대로 양쪽에
#      절반씩(지연 RTT/2, 손실 동일) 건다. 기본값 one 은 옛 동작(클라 송신측만)
#      그대로다 - 서버 비행(인증서)은 손실을 안 겪는다는 뜻이므로 보고서에
#      어느 쪽으로 쟀는지 적어야 한다.
# ============================================================
set -u
QUICK="${1:-full}"
NETEM_SIDES="${NETEM_SIDES:-one}"
PORT=45577
OUT="$(pwd)/resultsB_$(date +%Y%m%d_%H%M%S)"
BIN="$(pwd)/hct_v2"
CERT="$(pwd)/c.pem"; KEY="$(pwd)/k.pem"
TMO=5000

KEMS="X25519 MLKEM512 MLKEM768 MLKEM1024 X25519MLKEM768"
if [ "$QUICK" = "quick" ]; then
  RTTS="0 50"; LOSSES="0 2"; MODELS="uniform"; ITERS=100; WARMUP=10
else
  RTTS="0 10 50 100 200"; LOSSES="0 0.5 1 2 5"
  MODELS="uniform burst"; ITERS=2000; WARMUP=50
fi

[ -x "$BIN" ] || { echo "오류: hct_v2 없음. 먼저 컴파일하세요."; exit 1; }
[ -f "$CERT" ] || openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 \
  -keyout "$KEY" -out "$CERT" -days 30 -nodes -subj "/CN=localhost" 2>/dev/null
mkdir -p "$OUT"
echo "출력: $OUT"
export OUT BIN CERT KEY PORT KEMS RTTS LOSSES MODELS ITERS WARMUP TMO NETEM_SIDES

unshare -Urnm bash <<'INNER'
set -u
# --- veth 링크 구성 ---
mount -t tmpfs none /run 2>/dev/null
mkdir -p /run/netns
ip netns add peer
ip link add v0 type veth peer name v1
ip link set v1 netns peer
ip addr add 10.9.0.1/24 dev v0
ip link set v0 mtu 1500
ip link set v0 up
ip netns exec peer sh -c "ip addr add 10.9.0.2/24 dev v1; ip link set v1 mtu 1500; ip link set v1 up; ip link set lo up"

echo "링크 구성: v0(10.9.0.1) <-> v1(10.9.0.2)"
echo "v0 MTU = $(cat /sys/class/net/v0/mtu)"
ping -c 1 -W 2 10.9.0.2 >/dev/null 2>&1 && echo "연결 확인 OK" || { echo "연결 실패 — 중단"; exit 1; }

SUM="$OUT/summary.csv"
echo "model,rtt_ms,loss_pct,group,n,fail,tmo,fail_rate_pct,mean_ms,sd_ms,p50_ms,p95_ms,p99_ms,netem_sides,effective_loss_pct" > "$SUM"
tot=0
for m in $MODELS; do for r in $RTTS; do for l in $LOSSES; do for g in $KEMS; do tot=$((tot+1)); done;done;done;done
cnt=0
for model in $MODELS; do
 for rtt in $RTTS; do
  for loss in $LOSSES; do
    # netem: NETEM_SIDES=one 이면 v0 송신측에만(단방향, delay = 목표 RTT),
    # both 면 양쪽에 절반씩(명세 §4-2).
    tc qdisc del dev v0 root 2>/dev/null
    ip netns exec peer tc qdisc del dev v1 root 2>/dev/null
    spec=""
    if [ "$rtt" != "0" ]; then
      if [ "$NETEM_SIDES" = "both" ]; then
        spec="delay $(awk -v r="$rtt" 'BEGIN{printf "%g", r/2}')ms"
      else spec="delay ${rtt}ms"; fi
    fi
    eff="$loss"
    if [ "$loss" != "0" ]; then
      if [ "$model" = "burst" ]; then
        # gemodel p r: 정상상태 손실률 = p/(p+r). r=50% 고정, p 를 역산한다.
        pg=$(awk -v L="$loss" 'BEGIN{printf "%.4f", L*50/(100-L)}')
        spec="$spec loss gemodel ${pg}% 50%"
      else spec="$spec loss ${loss}%"; fi
    fi
    [ -n "$spec" ] && tc qdisc add dev v0 root netem $spec
    if [ "$NETEM_SIDES" = "both" ] && [ -n "$spec" ]; then
      ip netns exec peer tc qdisc add dev v1 root netem $spec
    fi

    for group in $KEMS; do
      cnt=$((cnt+1))
      it=$ITERS
      [ "$loss" = "0" ] && it=$((ITERS/8))
      case "$rtt" in 100|200) it=$((it/2));; esac
      printf "[%3d/%3d] %-7s RTT=%-4s loss=%-4s %-16s " "$cnt" "$tot" "$model" "$rtt" "$loss" "$group"

      # 서버는 peer ns 안에서 기동
      ip netns exec peer openssl s_server -cert "$CERT" -key "$KEY" -tls1_3 \
        -groups "$group" -accept 10.9.0.2:$PORT -quiet >/dev/null 2>&1 &
      SRV=$!; sleep 0.8

      csv="$OUT/raw_${model}_rtt${rtt}_loss${loss}_${group}.csv"
      out=$("$BIN" 10.9.0.2 $PORT "$group" "$it" "$WARMUP" "$csv" "$TMO" 2>/dev/null)
      neg=$(echo "$out"|sed -n 's/.*negotiated=\([A-Za-z0-9_]*\).*/\1/p')
      n=$(echo  "$out"|head -1|sed -n 's/.*[[:space:]]n=\([0-9]*\)[[:space:]].*/\1/p')
      f=$(echo  "$out"|sed -n 's/.*fail=\([0-9]*\).*/\1/p')
      tm=$(echo "$out"|sed -n 's/.*tmo=\([0-9]*\).*/\1/p')
      fr=$(echo "$out"|sed -n 's/.*failrate=\([0-9.]*\)%.*/\1/p')
      mm=$(echo "$out"|sed -n 's/.*mean=\([0-9.]*\).*/\1/p')
      sd=$(echo "$out"|sed -n 's/.*sd=\([0-9.]*\).*/\1/p')
      p50=$(echo "$out"|sed -n 's/.*p50=\([0-9.]*\).*/\1/p')
      p95=$(echo "$out"|sed -n 's/.*p95=\([0-9.]*\).*/\1/p')
      p99=$(echo "$out"|sed -n 's/.*p99=\([0-9.]*\).*/\1/p')
      [ "${neg^^}" != "${group^^}" ] && printf "!!협상불일치(%s) " "$neg"
      printf "p50=%-9s 실패=%-6s tmo=%s\n" "${p50:--}" "${fr:--}" "${tm:-0}"
      echo "$model,$rtt,$loss,$group,${n:-0},${f:-0},${tm:-0},${fr:-0},${mm:-},${sd:-},${p50:-},${p95:-},${p99:-},$NETEM_SIDES,$eff" >> "$SUM"
      kill $SRV 2>/dev/null; wait $SRV 2>/dev/null
    done
  done
 done
done
tc qdisc del dev v0 root 2>/dev/null
ip netns exec peer tc qdisc del dev v1 root 2>/dev/null
echo ""; echo "완료: $SUM"
INNER
