#!/usr/bin/env bash
set -u
QUICK="${1:-full}"
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
export OUT BIN CERT KEY PORT KEMS RTTS LOSSES MODELS ITERS WARMUP TMO

unshare -Urn bash <<'INNER'
set -u
ip link set lo up
ip link set lo mtu 1500          # ★ 핵심: 기본 65536 → 1500. 이게 없으면 KEM별 패킷 수가 동일해짐
echo "loopback MTU: $(cat /sys/class/net/lo/mtu)"

SUM="$OUT/summary.csv"
echo "model,rtt_ms,loss_pct,group,n,fail,tmo,fail_rate_pct,mean_ms,sd_ms,p50_ms,p95_ms,p99_ms" > "$SUM"
tot=0
for m in $MODELS; do for r in $RTTS; do for l in $LOSSES; do for g in $KEMS; do tot=$((tot+1)); done;done;done;done
cnt=0
for model in $MODELS; do
 for rtt in $RTTS; do
  for loss in $LOSSES; do
    tc qdisc del dev lo root 2>/dev/null
    delay=$(awk "BEGIN{printf \"%.3f\",$rtt/2}")
    spec=""
    [ "$rtt" != "0" ] && spec="delay ${delay}ms"
    if [ "$loss" != "0" ]; then
      if [ "$model" = "burst" ]; then spec="$spec loss gemodel ${loss}% 50%"
      else spec="$spec loss ${loss}%"; fi
    fi
    [ -n "$spec" ] && tc qdisc add dev lo root netem $spec
    for group in $KEMS; do
      cnt=$((cnt+1))
      it=$ITERS
      [ "$loss" = "0" ] && it=$((ITERS/8))
      case "$rtt" in 100|200) it=$((it/2));; esac
      printf "[%3d/%3d] %-7s RTT=%-4s loss=%-4s %-16s " "$cnt" "$tot" "$model" "$rtt" "$loss" "$group"
      openssl s_server -cert "$CERT" -key "$KEY" -tls1_3 -groups "$group" \
        -accept 127.0.0.1:$PORT -quiet >/dev/null 2>&1 &
      SRV=$!; sleep 0.7
      csv="$OUT/raw_${model}_rtt${rtt}_loss${loss}_${group}.csv"
      out=$("$BIN" 127.0.0.1 $PORT "$group" "$it" "$WARMUP" "$csv" "$TMO" 2>/dev/null)
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
      echo "$model,$rtt,$loss,$group,${n:-0},${f:-0},${tm:-0},${fr:-0},${mm:-},${sd:-},${p50:-},${p95:-},${p99:-}" >> "$SUM"
      kill $SRV 2>/dev/null; wait $SRV 2>/dev/null
    done
  done
 done
done
tc qdisc del dev lo root 2>/dev/null
echo ""; echo "완료: $SUM"
INNER
