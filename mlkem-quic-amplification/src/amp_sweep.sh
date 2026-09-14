#!/usr/bin/env bash
# RTT 50 ms, no induced loss. Preserve per-connection CSV and server logs.
set -euo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
BIN=${BIN:-"$SCRIPT_DIR/qamp"}
OUT=${OUT:-"$SCRIPT_DIR/results_amp_$(date +%Y%m%d_%H%M%S)"}
CERT_SIZES=${CERT_SIZES:-"2900 3000 3100 3200 3300 3400 3500 4800 4900 5000 5100 5200 5300 5400 5500 5600 5700 5800 5900 6000"}
KEMS=${KEMS:-"X25519 X25519MLKEM768"}
ITERS=${ITERS:-30}
WARMUP=${WARMUP:-5}
INITIAL_SIZE=${INITIAL_SIZE:-1280}
[[ -x "$BIN" ]] || { echo "Build $SCRIPT_DIR/qamp.go first." >&2; exit 1; }
mkdir -p "$OUT"
BIN=$(realpath "$BIN")
OUT=$(realpath "$OUT")
export SCRIPT_DIR BIN OUT CERT_SIZES KEMS ITERS WARMUP INITIAL_SIZE
unshare -Urnm bash <<'INNER'
set -euo pipefail
SRV=""
cleanup() {
  if [[ -n "$SRV" ]]; then kill "$SRV" 2>/dev/null || true; wait "$SRV" 2>/dev/null || true; fi
}
trap cleanup EXIT
mount -t tmpfs none /run
mkdir -p /run/netns
ip netns add peer
ip link add v0 type veth peer name v1
ip link set v1 netns peer
ip addr add 10.9.0.1/24 dev v0
ip link set v0 mtu 1500 up
ip netns exec peer ip addr add 10.9.0.2/24 dev v1
ip netns exec peer ip link set v1 mtu 1500 up
ip netns exec peer ip link set lo up
tc qdisc add dev v0 root netem delay 25ms
ip netns exec peer tc qdisc add dev v1 root netem delay 25ms
ping -c 1 -W 2 10.9.0.2 >/dev/null
printf 'certsize_target,group,p50_ms,sent_pkts,sent_bytes,recv_pkts,recv_bytes,n,fail,timeout,certsize_actual,initial_size,rtt_ms,netem_sides\n' > "$OUT/summary.csv"
for cs in $CERT_SIZES; do
  for g in $KEMS; do
    stem="$OUT/cert${cs}_${g}_ips${INITIAL_SIZE}"
    ip netns exec peer "$BIN" -mode server -addr 10.9.0.2:44494 -group "$g" -certsize "$cs" >"$stem.server.log" 2>&1 &
    SRV=$!
    for attempt in {1..50}; do
      kill -0 "$SRV" 2>/dev/null || { cat "$stem.server.log" >&2; exit 1; }
      if grep -q '인증서=' "$stem.server.log"; then break; fi
      sleep 0.1
    done
    grep -q '인증서=' "$stem.server.log" || { echo "Server did not become ready" >&2; exit 1; }
    actual=$(sed -n 's/.*인증서=\([0-9]*\)B.*/\1/p' "$stem.server.log" | head -1)
    timeout 300 "$BIN" -mode client -addr 10.9.0.2:44494 -group "$g" -n "$ITERS" -warmup "$WARMUP" -initpkt "$INITIAL_SIZE" -csv "$stem.csv" -summary >"$stem.client.log" 2>&1
    python3 "$SCRIPT_DIR/summarize_amp.py" "$stem.csv" --expected "$ITERS" --certsize "$cs" --actual "$actual" --group "$g" --initial-size "$INITIAL_SIZE" >> "$OUT/summary.csv"
    cleanup
    SRV=""
  done
done
printf 'Saved %s\n' "$OUT/summary.csv"
INNER
