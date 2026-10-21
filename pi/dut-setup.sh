#!/bin/sh
# 라즈베리 파이 A 를 시험 대상(DUT)으로 만든다. netns/up.sh 의 dut 와 같은 설정이다.
#   sudo sh dut-setup.sh [LAN포트] [WAN포트]     기본: eth0(내장) eth1(USB 이더넷)
#
# 관리 연결(SSH)은 Wi-Fi(wlan0)로 한다. 유선 두 포트는 모두 브리지에 들어가므로
# 설정이 잘못돼도 Wi-Fi 로는 계속 들어올 수 있다. 되돌리기는 dut-reset.sh.
set -eu
LAN=${1:-eth0}
WAN=${2:-eth1}
MGMT=${MGMT:-wlan0}
HERE=$(dirname "$0")
STATE=/run/pilab

[ "$LAN" != "$WAN" ] || { echo "LAN 과 WAN 이 같다" >&2; exit 1; }
for p in "$LAN" "$WAN"; do
    [ "$p" != "$MGMT" ] || { echo "$p 는 관리 포트다" >&2; exit 1; }
    ip link show "$p" >/dev/null 2>&1 || { echo "$p 없음" >&2; exit 1; }
done
# 지금 이 장비에 SSH 로 들어와 있는 연결이 쓰는 포트 이름들(VLAN 이면 부모 포트도). sudo 는
# SSH_CLIENT 같은 환경 변수를 지우므로, 실제 연결(ss)에서 sshd 쪽 주소를 찾는다. root 로 실행한다.
ssh_ports() {
    conns=$(ss -Htnp state established) || { echo "ss 실패: SSH 연결을 확인할 수 없다" >&2; return 1; }
    echo "$conns" | grep '"sshd' | awk '{print $3}' | sed 's/:[0-9]*$//; s/^\[//; s/\]$//' |
    while read -r a; do ip -o addr show | awk -v a="$a" '{split($4, x, "/"); if (x[1] == a) print $2}'; done |
    while read -r dev; do
        echo "$dev"
        ip -o link show "$dev" | sed -n 's/^[0-9]*: [^@:]*@\([^:]*\):.*/\1/p'   # pl100@eth0 → eth0
    done | sort -u
}

# 관리 포트에 주소가 있고, 지금 SSH 가 시험 포트로 들어와 있지 않은지 확인한다
ip -4 addr show dev "$MGMT" 2>/dev/null | grep -q inet || { echo "$MGMT 에 주소가 없다: 관리 연결 없이 진행하지 않는다" >&2; exit 1; }
ports=$(ssh_ports) || exit 1
for p in $ports; do
    if [ "$p" = "$LAN" ] || [ "$p" = "$WAN" ]; then
        echo "지금 SSH 가 $p 로 들어와 있다. 설정하면 끊기므로 멈춘다. $MGMT 로 접속해서 다시 하라." >&2
        exit 1
    fi
done

sh "$HERE/dut-reset.sh" "$LAN" "$WAN" >/dev/null 2>&1 || true
# 여기서부터 실패하면(set -e) 바꾼 것을 되돌리고 끝낸다
trap 'echo "설정 중 실패: 되돌린다" >&2; sh "$HERE/dut-reset.sh" "$LAN" "$WAN"' EXIT
# 되돌릴 때 쓸 원래 상태
mkdir -p "$STATE"
sysctl -n net.ipv4.ip_forward > "$STATE/ip_forward"
if command -v nmcli >/dev/null; then
    for p in "$LAN" "$WAN"; do
        nmcli -g GENERAL.STATE device show "$p" | grep -q unmanaged && echo no > "$STATE/managed.$p" || echo yes > "$STATE/managed.$p"
        nmcli device set "$p" managed no
    done
fi
ip addr flush dev "$LAN"
ip addr flush dev "$WAN"

ip link add br0 type bridge vlan_filtering 1 mcast_snooping 1 mcast_querier 1
for p in "$LAN" "$WAN"; do
    ip link set "$p" master br0
    ip link set "$p" up
done
ip link set br0 up
bridge vlan add dev "$LAN" vid 100
bridge vlan add dev "$WAN" vid 100
bridge vlan add dev "$LAN" vid 200
bridge vlan add dev "$WAN" vid 201
bridge vlan add dev br0 vid 200 self
bridge vlan add dev br0 vid 201 self
ip addr add 192.0.2.1/24 dev br0

ip link add link br0 name br0.200 type vlan id 200
ip link add link br0 name br0.201 type vlan id 201
ip addr add 203.0.113.1/24 dev br0.200
ip addr add 198.51.100.1/24 dev br0.201
ip link set br0.200 up
ip link set br0.201 up
sysctl -qw net.ipv4.ip_forward=1
nft -f "$HERE/../netns/dut-nat.nft"

echo "pilab-dut-1.0 $(uname -r)" > "$STATE/version"
sleep 12   # IGMP 질의기가 자리 잡을 때까지 (netns/up.sh 참고)
trap - EXIT
echo "DUT ready: LAN=$LAN WAN=$WAN"
