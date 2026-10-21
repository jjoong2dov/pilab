#!/bin/sh
# dut-setup.sh 로 바꾼 것을 되돌린다. 유선 포트의 원래 주소는 NetworkManager 가 다시 잡는다.
LAN=${1:-eth0}
WAN=${2:-eth1}
STATE=/run/pilab
nft delete table ip pilab 2>/dev/null
ip link del br0.200 2>/dev/null
ip link del br0.201 2>/dev/null
ip link del br0 2>/dev/null
[ -f "$STATE/ip_forward" ] && sysctl -qw net.ipv4.ip_forward="$(cat "$STATE/ip_forward")"
if command -v nmcli >/dev/null; then
    for p in "$LAN" "$WAN"; do
        [ -f "$STATE/managed.$p" ] && nmcli device set "$p" managed "$(cat "$STATE/managed.$p")"
    done
fi
if ip link show br0 >/dev/null 2>&1 || nft list table ip pilab >/dev/null 2>&1; then
    echo "되돌리기 실패: br0 또는 NAT 테이블이 남아 있다. $STATE 는 지우지 않는다." >&2
    exit 1
fi
rm -rf "$STATE"
echo "DUT reset"
