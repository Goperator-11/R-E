#!/usr/bin/env bash
set -u

QUICK="${1:-full}"
PORT=45555
OUT="results_$(date +%Y%m%d_%H%M%S)"
BIN="$(pwd)/hct_client"
CERT="$(pwd)/c.pem"
KEY="$(pwd)/k.pem"

GROUPS="X25519 MLKEM512 MLKEM768 MLKEM1024 X25519MLKEM768"
if [ "$QUICK" = "quick" ]; then
  RTTS="0 100"; LOSSES="0 2"; MODELS="uniform"; ITERS=50; WARMUP=10
else
  RTTS="0 10 50 100 200"
  LOSSES="0 0.5 1 2 5"
  MODELS="uniform burst"
  ITERS=500; WARMUP=20
fi

[ -x "$BIN" ]  || { echo "오류: hct_client 없음. 먼저 컴파일하세요."; exit 1; }
[ -f "$CERT" ] || {
  echo "인증서 생성 중..."
  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 \
    -keyout "$KEY" -out "$CERT" -days 30 -nodes -subj "/CN=localhost" 2>/dev/null
}

mkdir -p "$OUT"
echo "출력 디렉터리: $OUT"

export OUT BIN CERT KEY PORT GROUPS RTTS LOSSES MODELS ITERS WARMUP

unshare -Urn bash <<'INNER'
set -u
ip link set lo up

SUMMARY="$OUT/summary.csv"
echo "model,rtt_ms,loss_pct,group,n,fail,fail_rate_pct,mean_ms,sd_ms,p50_ms,p95_ms,p99_ms" > "$SUMMARY"

total=0; done_n=0
for m in $MODELS; do for r in $RTTS; do for l in $LOSSES; do for g in $GROUPS; do
  total=$((total+1)); done; done; done; done

for model in $MODELS; do
 for rtt in $RTTS; do
  for loss in $LOSSES; do

    # ---- NetEm 적용 ----
    # loopback은 편도 지연이 왕복에 두 번 반영되므로 delay = RTT/2
    tc qdisc del dev lo root 2>/dev/null
    delay=$(awk "BEGIN{printf \"%.3f\", $rtt/2}")
    spec=""
    [ "$rtt"  != "0" ] && spec="delay ${delay}ms"
    if [ "$loss" != "0" ]; then
      if [ "$model" = "burst" ]; then
        # Gilbert-Elliott: p(good→bad) 를 손실률에 비례시키고
        # r(bad→good)=50% 로 두어 평균 버스트 길이 2 프레임
        spec="$spec loss gemodel ${loss}% 50%"
      else
        spec="$spec loss ${loss}%"
      fi
    fi
    [ -n "$spec" ] && tc qdisc add dev lo root netem $spec

    for group in $GROUPS; do
      done_n=$((done_n+1))
      printf "[%3d/%3d] %-8s RTT=%-4s loss=%-4s %-18s " \
             "$done_n" "$total" "$model" "$rtt" "$loss" "$group"

      # 이 조건 전용 서버 기동 (KEM마다 -groups 를 따로 줘야 함)
      openssl s_server -cert "$CERT" -key "$KEY" -tls1_3 -groups "$group" \
        -accept 127.0.0.1:$PORT -quiet >/dev/null 2>&1 &
      SRV=$!
      sleep 0.7

      csv="$OUT/raw_${model}_rtt${rtt}_loss${loss}_${group}.csv"
      line=$("$BIN" 127.0.0.1 $PORT "$group" "$ITERS" "$WARMUP" "$csv" 2>/dev/null)
      echo "$line" | tail -1

      # 요약 행 추출
      st=$(echo "$line" | grep -o 'n=[0-9]*  fail=[0-9]*  실패율=[0-9.]*%')
      n=$(echo   "$st" | sed -n 's/.*n=\([0-9]*\).*/\1/p')
      f=$(echo   "$st" | sed -n 's/.*fail=\([0-9]*\).*/\1/p')
      fr=$(echo  "$st" | sed -n 's/.*실패율=\([0-9.]*\)%.*/\1/p')
      mm=$(echo "$line" | sed -n 's/.*mean=\([0-9.]*\).*/\1/p')
      sd=$(echo "$line" | sed -n 's/.*sd=\([0-9.]*\).*/\1/p')
      p50=$(echo "$line" | sed -n 's/.*p50=\([0-9.]*\).*/\1/p')
      p95=$(echo "$line" | sed -n 's/.*p95=\([0-9.]*\).*/\1/p')
      p99=$(echo "$line" | sed -n 's/.*p99=\([0-9.]*\).*/\1/p')
      echo "$model,$rtt,$loss,$group,${n:-0},${f:-0},${fr:-0},${mm:-},${sd:-},${p50:-},${p95:-},${p99:-}" >> "$SUMMARY"

      kill $SRV 2>/dev/null; wait $SRV 2>/dev/null
    done
  done
 done
done

tc qdisc del dev lo root 2>/dev/null
echo ""
echo "완료. 요약: $SUMMARY"
INNER

echo ""
echo "=============================================="
echo " 결과 디렉터리: $OUT"
echo "   summary.csv  — 조건별 통계 (분석·작도용)"
echo "   raw_*.csv    — 개별 핸드셰이크 원자료 (CDF·이상치 분석용)"
echo "=============================================="
