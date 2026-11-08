#!/bin/bash
set -e

RTT_MS="${1:-50}"
LOSS_SPEC="${2:-0}"
shift 2 || true

HALF=$(python3 -c "print(f'{${RTT_MS}/2:g}')")

if [ "$LOSS_SPEC" = "0" ] || [ -z "$LOSS_SPEC" ]; then
  NETEM_LOSS=""
else
  NETEM_LOSS="loss $LOSS_SPEC"
fi

export RTT_MS HALF NETEM_LOSS
export INNER_CMD="$*"

exec unshare -Urnm bash -c '
set -e
mount -t tmpfs none /run 2>/dev/null || true
mkdir -p /run/netns

ip netns add peer
ip link add v0 type veth peer name v1
ip link set v1 netns peer

ip addr add 10.9.0.1/24 dev v0
ip link set v0 mtu 1500
ip link set v0 up
ip link set lo up

ip netns exec peer sh -c "ip addr add 10.9.0.2/24 dev v1; \
    ip link set v1 mtu 1500; ip link set v1 up; ip link set lo up"

# 명세 4-2: 양방향에 절반씩 걸어야 대칭 지연이 된다.
tc qdisc add dev v0 root netem delay ${HALF}ms $NETEM_LOSS
ip netns exec peer tc qdisc add dev v1 root netem delay ${HALF}ms $NETEM_LOSS

# ---- 명세 3-2 가 요구하는 적용 확인 -------------------------------------
MTU0=$(ip -o link show v0 | grep -o "mtu [0-9]*" | cut -d" " -f2)
MTU1=$(ip netns exec peer ip -o link show v1 | grep -o "mtu [0-9]*" | cut -d" " -f2)
DEV=$(ip route get 10.9.0.2 | head -1 | grep -o "dev [a-z0-9]*" | cut -d" " -f2)
if [ "$MTU0" != "1500" ] || [ "$MTU1" != "1500" ]; then
  echo "FATAL: MTU 미적용 (v0=$MTU0 v1=$MTU1)" >&2; exit 1
fi
if [ "$DEV" != "v0" ]; then
  echo "FATAL: 경로가 veth 가 아니다 (dev=$DEV) - 명세 3-2 의 2차 실패" >&2; exit 1
fi
echo "[netbed] MTU v0=$MTU0 v1=$MTU1 · route dev=$DEV · netem ${HALF}ms x2 ${NETEM_LOSS:-무손실}" >&2

if [ -n "$INNER_CMD" ]; then
  eval "$INNER_CMD"
else
  echo "[netbed] 준비 완료 (명령 없음)" >&2
fi
'
