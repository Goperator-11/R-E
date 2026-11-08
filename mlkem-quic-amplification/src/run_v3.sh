#!/usr/bin/env bash
set -euo pipefail
QUICK="${1:-full}"
NETEM_SIDES="${NETEM_SIDES:-one}"
case "$QUICK" in quick|full) ;; *) echo "usage: $0 [quick|full]" >&2; exit 2;; esac
case "$NETEM_SIDES" in one|both) ;; *) echo "NETEM_SIDES must be one or both" >&2; exit 2;; esac
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PORT=45577
OUT="$(pwd)/resultsB_$(date +%Y%m%d_%H%M%S)"
BIN="${BIN:-$SCRIPT_DIR/hct_v2}"
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
if [ ! -f "$CERT" ] || [ ! -f "$KEY" ]; then openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 \
  -keyout "$KEY" -out "$CERT" -days 30 -nodes -subj "/CN=localhost" 2>/dev/null
fi
mkdir -p "$OUT"
echo "출력: $OUT"
export OUT BIN CERT KEY PORT KEMS RTTS LOSSES MODELS ITERS WARMUP TMO NETEM_SIDES

unshare -Urnm bash <<'INNER'
set -euo pipefail
SRV=""
cleanup() {
  if [ -n "$SRV" ]; then kill "$SRV" 2>/dev/null || true; wait "$SRV" 2>/dev/null || true; fi
}
trap cleanup EXIT
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
    tc qdisc del dev v0 root 2>/dev/null || true
    ip netns exec peer tc qdisc del dev v1 root 2>/dev/null || true
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
        -groups "$group" -accept 10.9.0.2:$PORT -quiet >"$OUT/server_${model}_rtt${rtt}_loss${loss}_${group}.log" 2>&1 &
      SRV=$!; sleep 0.8
      kill -0 "$SRV" 2>/dev/null || { echo "server failed: $group" >&2; exit 1; }

      csv="$OUT/raw_${model}_rtt${rtt}_loss${loss}_${group}.csv"
      out=$("$BIN" 10.9.0.2 "$PORT" "$group" "$it" "$WARMUP" "$csv" "$TMO" 2>"$csv.stderr.log")
      printf '%s\n' "$out" > "$csv.summary.log"
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
      [[ "$n" =~ ^[0-9]+$ && "$f" =~ ^[0-9]+$ && "$tm" =~ ^[0-9]+$ ]] || { echo "invalid measurement output" >&2; exit 1; }
      [ "$((n+f))" -eq "$it" ] || { echo "measurement count mismatch" >&2; exit 1; }
      if [ "$n" -gt 0 ] && [ "${neg^^}" != "${group^^}" ]; then
        printf "협상불일치(%s), 중단\n" "$neg" >&2; exit 1
      fi
      printf "p50=%-9s 실패=%-6s tmo=%s\n" "${p50:--}" "${fr:--}" "${tm:-0}"
      echo "$model,$rtt,$loss,$group,${n:-0},${f:-0},${tm:-0},${fr:-0},${mm:-},${sd:-},${p50:-},${p95:-},${p99:-},$NETEM_SIDES,$eff" >> "$SUM"
      cleanup
      SRV=""
    done
  done
 done
done
tc qdisc del dev v0 root 2>/dev/null || true
ip netns exec peer tc qdisc del dev v1 root 2>/dev/null || true
echo ""; echo "완료: $SUM"
INNER
