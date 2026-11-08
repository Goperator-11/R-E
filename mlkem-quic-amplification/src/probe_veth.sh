#!/usr/bin/env bash
echo "=== 방식 A: 중첩 netns (ip netns) ==="
unshare -Urnm bash -c '
mount -t tmpfs none /run 2>/dev/null || echo "  tmpfs mount 실패"
mkdir -p /run/netns 2>/dev/null
ip netns add peer 2>&1 && echo "  netns 생성 OK" || echo "  netns 생성 실패"
ip link add v0 type veth peer name v1 2>&1
ip link set v1 netns peer 2>&1 && echo "  veth 이동 OK" || echo "  veth 이동 실패"
ip addr add 10.9.0.1/24 dev v0; ip link set v0 up; ip link set v0 mtu 1500
ip netns exec peer sh -c "ip addr add 10.9.0.2/24 dev v1; ip link set v1 up; ip link set v1 mtu 1500; ip link set lo up" 2>&1
echo "  --- ping 시험 ---"
ping -c 2 -W 2 10.9.0.2 2>&1 | tail -2
' 2>&1

echo ""
echo "=== 방식 B: 단일 netns + veth (정책 라우팅으로 우회 방지) ==="
unshare -Urn bash -c '
ip link add v0 type veth peer name v1
ip addr add 10.9.0.1/24 dev v0
ip addr add 10.9.0.2/24 dev v1
ip link set v0 up; ip link set v1 up
ip link set v0 mtu 1500; ip link set v1 mtu 1500
echo "  --- ping 시험 ---"
ping -c 2 -W 2 10.9.0.2 2>&1 | tail -2
echo "  --- 실제 경로 확인 ---"
ip route get 10.9.0.2 2>&1 | head -1
' 2>&1
