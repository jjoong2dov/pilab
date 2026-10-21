#!/bin/sh
# 노트북 한 대에 1권 실습 랩을 만든다. (root 필요)
#
#   [pc] eth0 ──── lan0 [dut: br0] wan0 ──── eth0 [pib]
#
# dut 는 라즈베리 파이 A, pib 는 라즈베리 파이 B, pc 는 제어용 PC 역할이다.
# 실제 파이 랩과 이름·주소를 똑같이 맞춰서 시험 코드를 바꾸지 않고 돌린다.
set -eu
HERE=$(dirname "$0")
MARK=/run/pilab-netns   # 이 스크립트가 만든 네임스페이스 목록. down.sh 는 여기 적힌 것만 지운다.

# 필요한 명령과 이름 충돌을 먼저 본다. 같은 이름의 네임스페이스가 이미 있으면 남의 것일 수 있으므로 손대지 않는다.
for c in ip bridge nft sysctl; do
    command -v "$c" >/dev/null || { echo "$c 명령이 없다: sudo apt install iproute2 nftables procps" >&2; exit 1; }
done
for ns in pc dut pib; do
    if [ -e "/run/netns/$ns" ]; then
        echo "네임스페이스 $ns 가 이미 있다. 전에 만든 실습 랩이면 sudo sh $HERE/down.sh 로 지우고 다시 하라." >&2
        exit 1
    fi
done
# 여기서부터 실패하면 이번에 만든 것만 지우고 끝낸다
trap 'echo "랩 만들기 실패: 만든 것을 지운다" >&2; sh "$HERE/down.sh"' EXIT
trap 'exit 1' HUP INT TERM   # 신호로 끊겨도 EXIT 정리를 거치게 한다
: > "$MARK"
for ns in pc dut pib; do
    echo "$ns" >> "$MARK"   # 만들기 전에 적는다. 만들다 실패해도 down.sh 가 지울 수 있게
    ip netns add "$ns"
    ip -n "$ns" link set lo up
done

ip link add pc-eth0 type veth peer name dut-lan0
ip link add pib-eth0 type veth peer name dut-wan0
ip link set pc-eth0 netns pc name eth0
ip link set pib-eth0 netns pib name eth0
ip link set dut-lan0 netns dut name lan0
ip link set dut-wan0 netns dut name wan0

# 시험 대상: VLAN 필터링 + IGMP 스누핑 브리지.
# 브리지가 질의기(querier)를 겸하므로 가입자가 없는 그룹은 LAN 포트로 내보내지 않는다.
ip -n dut link add br0 type bridge vlan_filtering 1 mcast_snooping 1 mcast_querier 1
for p in lan0 wan0; do
    ip -n dut link set "$p" master br0
    ip -n dut link set "$p" up
done
ip -n dut link set br0 up
bridge -n dut vlan add dev lan0 vid 100
bridge -n dut vlan add dev wan0 vid 100
bridge -n dut vlan add dev lan0 vid 200
bridge -n dut vlan add dev wan0 vid 201
bridge -n dut vlan add dev br0 vid 200 self
bridge -n dut vlan add dev br0 vid 201 self
ip -n dut addr add 192.0.2.1/24 dev br0

# 라우팅(NAT) 서비스: LAN 쪽 VLAN 200, WAN 쪽 VLAN 201
ip -n dut link add link br0 name br0.200 type vlan id 200
ip -n dut link add link br0 name br0.201 type vlan id 201
ip -n dut addr add 203.0.113.1/24 dev br0.200
ip -n dut addr add 198.51.100.1/24 dev br0.201
ip -n dut link set br0.200 up
ip -n dut link set br0.201 up
ip netns exec dut sysctl -qw net.ipv4.ip_forward=1
ip netns exec dut nft -f "$HERE/dut-nat.nft"

for ns in pc pib; do
    ip -n "$ns" link set eth0 up
done
ip -n pc addr add 192.0.2.10/24 dev eth0
ip -n pib addr add 192.0.2.20/24 dev eth0
# VLAN 인터페이스 이름은 plVID 로 짧게 짓는다. 리눅스 인터페이스 이름은 15자까지라
# USB 이더넷(enx00005e005301 같은 이름) 뒤에 .100 을 붙이면 만들 수 없다.
for ns in pc pib; do
    ip -n "$ns" link add link eth0 name pl100 type vlan id 100
    ip -n "$ns" link set pl100 up
done
ip -n pc addr add 192.0.2.110/24 dev pl100 noprefixroute
ip -n pib addr add 192.0.2.120/24 dev pl100 noprefixroute
ip -n pc route add 192.0.2.120/32 dev pl100
ip -n pib route add 192.0.2.110/32 dev pl100

ip -n pc link add link eth0 name pl200 type vlan id 200
ip -n pc link set pl200 up
ip -n pc addr add 203.0.113.10/24 dev pl200
ip -n pc route add 198.51.100.0/24 via 203.0.113.1
ip -n pib link add link eth0 name pl201 type vlan id 201
ip -n pib link set pl201 up
ip -n pib addr add 198.51.100.20/24 dev pl201
# 바깥에서 안쪽으로 가는 길은 있지만 DUT 방화벽이 막아야 한다 (NAT-003 시험)
ip -n pib route add 203.0.113.0/24 via 198.51.100.1

# 브리지 질의기는 첫 질의 후 응답 대기 시간(기본 10초)이 지나야 자리를 잡는다.
# 그 전에는 가입자 없는 멀티캐스트도 흘려보내므로, 바로 시험하면 MC-001 이 거짓 FAIL 난다.
sleep 12
trap - EXIT
echo "lab up: pc / dut / pib"
