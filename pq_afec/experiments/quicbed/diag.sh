#!/bin/bash
# Isolate where the handshake latency comes from:
#   A) client -> server directly, no netem, no shim
#   B) client -> server directly, netem delay only
#   C) client -> shim -> shim -> server, netem delay only
BIN="$HOME/quicbed/bin"
QBED=/mnt/c/dev/pq_afec/experiments/quicbed
mount -t tmpfs none /run 2>/dev/null
mkdir -p /run/netns
ip netns del rx 2>/dev/null
ip netns add rx
ip link add veth-tx type veth peer name veth-rx
ip link set veth-rx netns rx
ip addr add 10.9.0.1/24 dev veth-tx
ip link set veth-tx mtu 1500
ip link set veth-tx up
ip link set lo up
ip netns exec rx ip addr add 10.9.0.2/24 dev veth-rx
ip netns exec rx ip link set veth-rx mtu 1500
ip netns exec rx ip link set veth-rx up
ip netns exec rx ip link set lo up

echo "=== A) direct, no netem ==="
ip netns exec rx "$BIN/qserver" -addr 10.9.0.2:4433 -certsize 2955 2>/dev/null &
sleep 1
"$BIN/qclient" -addr 10.9.0.2:4433 -group X25519MLKEM768 -n 6 -gap 20ms 2>/dev/null
kill %1 2>/dev/null; wait 2>/dev/null

echo "=== B) direct, netem delay 10ms each way ==="
tc qdisc add dev veth-tx root netem delay 10ms
ip netns exec rx tc qdisc add dev veth-rx root netem delay 10ms
ip netns exec rx "$BIN/qserver" -addr 10.9.0.2:4433 -certsize 2955 2>/dev/null &
sleep 1
"$BIN/qclient" -addr 10.9.0.2:4433 -group X25519MLKEM768 -n 6 -gap 20ms 2>/dev/null
kill %1 2>/dev/null; wait 2>/dev/null

echo "=== C) through both shims, same netem ==="
ip netns exec rx "$BIN/qserver" -addr 127.0.0.1:4433 -certsize 2955 2>/dev/null &
sleep 1
ip netns exec rx python3 "$QBED/shim.py" --role rx --listen 10.9.0.2:5556 --target 127.0.0.1:4433 &
sleep 0.5
python3 "$QBED/shim.py" --role tx --listen 127.0.0.1:5555 --peer 10.9.0.2:5556 --flight-ms 3 &
sleep 0.5
"$BIN/qclient" -addr 127.0.0.1:5555 -group X25519MLKEM768 -n 6 -gap 20ms 2>/dev/null
kill %1 %2 %3 2>/dev/null; wait 2>/dev/null

tc qdisc del dev veth-tx root 2>/dev/null
echo "diag done"
