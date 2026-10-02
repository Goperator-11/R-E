#!/bin/bash
echo "The historical live demo is disabled in gen32; a new isolated measurement protocol is required." >&2
exit 2
# A visible walk-through of the testbed: build it, show it, run real ML-KEM
# QUIC handshakes through it with loss, and print what the FEC shim did.
BIN="$HOME/quicbed/bin"
QBED=/mnt/c/dev/pq_afec/experiments/quicbed
W=/tmp/livedemo
mkdir -p $W

echo "==============================================================="
echo " 1. 테스트베드 구성 (권한 없이 - unshare 안)"
echo "==============================================================="
mount -t tmpfs none /run 2>/dev/null
mkdir -p /run/netns
ip netns del rx 2>/dev/null
ip netns add rx
ip link add veth-tx type veth peer name veth-rx
ip link set veth-rx netns rx
ip addr add 10.9.0.1/24 dev veth-tx
ip link set veth-tx mtu 1500
ip link set veth-tx up; ip link set lo up
ip netns exec rx ip addr add 10.9.0.2/24 dev veth-rx
ip netns exec rx ip link set veth-rx mtu 1500
ip netns exec rx ip link set veth-rx up
ip netns exec rx ip link set lo up
echo "[netns 기본]  $(ip -o addr show veth-tx | awk '{print $2, $4}')  mtu=$(cat /sys/class/net/veth-tx/mtu)"
echo "[netns rx  ]  $(ip netns exec rx ip -o addr show veth-rx | awk '{print $2, $4}')"
echo "권한: uid=$(id -u) (네임스페이스 안 root, 호스트에는 무권한)"

echo ""
echo "==============================================================="
echo " 2. 손실 주입: netem gemodel  (목표 손실 10%, 평균 버스트 1)"
echo "==============================================================="
tc qdisc add dev veth-tx root netem limit 20000 loss 10% delay 10ms
ip netns exec rx tc qdisc add dev veth-rx root netem limit 20000 loss 10% delay 10ms
echo "송신 방향: $(tc qdisc show dev veth-tx)"
echo "수신 방향: $(ip netns exec rx tc qdisc show dev veth-rx)"

for MODE in nofec fec; do
  echo ""
  echo "==============================================================="
  if [ "$MODE" = "fec" ]; then
    echo " 3b. ML-KEM QUIC 핸드셰이크 40회  —  XOR 패리티 ON"
  else
    echo " 3a. ML-KEM QUIC 핸드셰이크 40회  —  FEC 없음"
  fi
  echo "==============================================================="
  rm -f $W/tx.txt $W/rx.txt
  ip netns exec rx "$BIN/qserver" -addr 127.0.0.1:4433 -certsize 2955 2>/dev/null &
  sleep 1
  ip netns exec rx python3 "$QBED/shim.py" --role rx --listen 10.9.0.2:5556 \
      --target 127.0.0.1:4433 --stats $W/rx.txt >/dev/null 2>&1 &
  sleep 0.4
  if [ "$MODE" = "fec" ]; then
    python3 "$QBED/shim.py" --role tx --listen 127.0.0.1:5555 --peer 10.9.0.2:5556 \
        --flight-ms 3 --fec --stats $W/tx.txt >/dev/null 2>&1 &
  else
    python3 "$QBED/shim.py" --role tx --listen 127.0.0.1:5555 --peer 10.9.0.2:5556 \
        --flight-ms 3 --stats $W/tx.txt >/dev/null 2>&1 &
  fi
  sleep 0.5

  "$BIN/qclient" -addr 127.0.0.1:5555 -group X25519MLKEM768 -n 40 -gap 10ms 2>/dev/null \
    | python3 -c "
import sys, json
t=[]
for line in sys.stdin:
    line=line.strip()
    if not line.startswith('{'): continue
    d=json.loads(line); t.append(d['ms'])
    bar = '#' * min(60, int(d['ms']/8))
    flag = '  <-- PTO 정지' if d['ms'] > 100 else ''
    print('  %2d  %8.1f ms |%s%s' % (d['i'], d['ms'], bar, flag))
t.sort()
n=len(t)
print('  ---------------------------------------------')
print('  n=%d  p50=%.1f  평균=%.1f  p90=%.1f  최대=%.1f ms'
      % (n, t[n//2], sum(t)/n, t[int(0.9*(n-1))], t[-1]))
print('  1초 근처 정지(>100ms) 발생: %d회' % sum(1 for x in t if x > 100))
"
  kill %1 %2 %3 2>/dev/null; wait 2>/dev/null
  echo "  [FEC 심 카운터] tx: $(cat $W/tx.txt 2>/dev/null)"
  echo "                  rx: $(cat $W/rx.txt 2>/dev/null)"
done

tc qdisc del dev veth-tx root 2>/dev/null
echo ""
echo "demo 끝"
