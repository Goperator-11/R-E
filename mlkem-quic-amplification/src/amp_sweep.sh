#!/usr/bin/env bash
# 증폭 임계 정밀 스윕 — 중첩 netns + veth + 양방향 대칭 netem(각 25ms = RTT 50ms)
cd ~/Desktop/workspace/34/"1311 신레오"/quic
cp qamp /tmp/qamp
unshare -Urnm bash -c '
mount -t tmpfs none /run 2>/dev/null; mkdir -p /run/netns
ip netns add peer
ip link add v0 type veth peer name v1
ip link set v1 netns peer
ip addr add 10.9.0.1/24 dev v0; ip link set v0 mtu 1500; ip link set v0 up
ip netns exec peer sh -c "ip addr add 10.9.0.2/24 dev v1; ip link set v1 mtu 1500; ip link set v1 up"
tc qdisc add dev v0 root netem delay 25ms
ip netns exec peer tc qdisc add dev v1 root netem delay 25ms
echo "certsize,group,p50_ms,sent_pkts,sent_bytes,recv_pkts,recv_bytes"
for cs in 2900 3000 3100 3200 3300 3400 3500 4800 4900 5000 5100 5200 5300 5400 5500 5600 5700 5800 5900 6000; do
for g in X25519 X25519MLKEM768; do
  ip netns exec peer /tmp/qamp -mode server -addr 10.9.0.2:44494 -group $g -certsize $cs >/dev/null 2>&1 &
  SRV=$!; sleep 1
  OUT=$(timeout 120 /tmp/qamp -mode client -addr 10.9.0.2:44494 -group $g -n 30 2>/dev/null)
  P50=$(echo "$OUT" | grep "HCT=" | awk -F"HCT=" "{split(\$2,a,\"ms\"); print a[1]}" | sort -n | awk "{v[NR]=\$1} END {printf \"%.1f\", v[int(NR/2)]}")
  AVG=$(echo "$OUT" | grep "평균:" | sed "s/[^0-9. ]//g")
  echo "$cs,$g,$P50,$AVG"
  kill $SRV 2>/dev/null; sleep 1
done
done
'
