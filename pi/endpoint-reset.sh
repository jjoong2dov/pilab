#!/bin/sh
# endpoint-setup.sh 로 바꾼 것을 되돌린다: 시험용 VLAN 을 지우고, 원래 IPv4 주소·경로·NetworkManager 상태를 되살린다.
#   sudo sh endpoint-reset.sh
STATE=/run/pilab-endpoint
if [ ! -d "$STATE" ]; then
    echo "endpoint-setup.sh 기록($STATE)이 없다. 되돌릴 것이 없다(재부팅했으면 이미 원래대로다)." >&2
    exit 0
fi
# 바꾸기 전에 기록부터 확인한다. 기록이 깨졌으면 아무것도 바꾸지 않는다.
NIC=$(cat "$STATE/nic" 2>/dev/null)
if [ -z "$NIC" ] || [ ! -f "$STATE/addrs" ] || [ ! -f "$STATE/routes" ] || ! ip link show "$NIC" >/dev/null 2>&1; then
    echo "$STATE 기록이 온전하지 않거나 포트($NIC)가 없다. 아무것도 바꾸지 않는다." >&2
    exit 1
fi
fail=0
for v in pl100 pl200 pl201 pl300; do
    ip link del "$v" 2>/dev/null
done
ip -4 addr flush dev "$NIC" || fail=1
while read -r a; do
    [ -n "$a" ] && { ip addr add "$a" dev "$NIC" || fail=1; }
done < "$STATE/addrs"
while read -r r; do
    [ -n "$r" ] && { ip route replace $r dev "$NIC" || fail=1; }
done < "$STATE/routes"
if [ -f "$STATE/managed" ] && command -v nmcli >/dev/null; then
    nmcli device set "$NIC" managed "$(cat "$STATE/managed")" || fail=1
fi
for v in pl100 pl200 pl201 pl300; do
    ip link show "$v" >/dev/null 2>&1 && { echo "$v 가 남아 있다" >&2; fail=1; }
done
if [ "$fail" -ne 0 ]; then
    echo "되돌리기 일부 실패. $STATE 는 지우지 않는다. 위 메시지를 보고 정리하라." >&2
    exit 1
fi
rm -rf "$STATE"
echo "endpoint reset: $NIC"
