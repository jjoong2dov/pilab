#!/bin/sh
# 단말(파이 B 또는 PC)의 시험용 유선 포트를 설정한다. netns/up.sh 의 pc·pib 와 같은 주소다.
#   sudo sh endpoint-setup.sh pib eth0               파이 B (WAN 쪽)
#   sudo sh endpoint-setup.sh pc enx00e04c680001     PC 의 USB 이더넷 (LAN 쪽)
# 고른 포트는 시험 전용이 된다(주소를 지운다). 관리 연결은 Wi-Fi 나 다른 포트로 한다.
set -eu
ROLE=${1:-}
NIC=${2:-}
case "$ROLE" in pc|pib) ;; *) echo "사용법: $0 pc|pib NIC" >&2; exit 2 ;; esac
ip link show "$NIC" >/dev/null 2>&1 || { echo "$NIC 없음" >&2; exit 1; }
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
# 지금 SSH 로 들어온 길이 이 포트라면 끊기므로 멈춘다
ports=$(ssh_ports) || exit 1
if echo "$ports" | grep -qx -e "$NIC" -e pl100 -e pl200 -e pl201 -e pl300; then
    echo "$NIC(또는 그 위의 시험용 VLAN)는 지금 SSH 관리 연결이 쓰는 포트다. 다른 포트로 접속해서 다시 하라." >&2
    exit 1
fi
if command -v nmcli >/dev/null; then nmcli device set "$NIC" managed no; fi
for v in pl100 pl200 pl201 pl300; do ip link del "$v" 2>/dev/null || true; done
ip addr flush dev "$NIC"
ip link set "$NIC" up
ip link add link "$NIC" name pl100 type vlan id 100
ip link set pl100 up
if [ "$ROLE" = pc ]; then
    ip addr add 192.0.2.10/24 dev "$NIC"
    ip addr add 192.0.2.110/24 dev pl100 noprefixroute
    ip route add 192.0.2.120/32 dev pl100
    ip link add link "$NIC" name pl200 type vlan id 200
    ip link set pl200 up
    ip addr add 203.0.113.10/24 dev pl200
    ip route add 198.51.100.0/24 via 203.0.113.1
else
    ip addr add 192.0.2.20/24 dev "$NIC"
    ip addr add 192.0.2.120/24 dev pl100 noprefixroute
    ip route add 192.0.2.110/32 dev pl100
    ip link add link "$NIC" name pl201 type vlan id 201
    ip link set pl201 up
    ip addr add 198.51.100.20/24 dev pl201
    ip route add 203.0.113.0/24 via 198.51.100.1
fi
echo "$ROLE ready on $NIC"
