#!/bin/sh
# [설계안] 실물 랩용. veth 로 설정·되돌리기만 확인했고, 실제 배선 전체 시험은 확인하지 않았다 (책 17장).
# dut-setup.sh 로 바꾼 것을 되돌린다. 유선 포트의 원래 주소는 NetworkManager 가 다시 잡는다.
# 되돌릴 근거는 dut-setup.sh 가 남긴 /run/pilab 기록이다. 기록이 없으면 아무것도 지우지 않는다.
STATE=/run/pilab
if [ ! -d "$STATE" ]; then
    echo "dut-setup.sh 기록($STATE)이 없다. 되돌릴 것이 없다(재부팅했으면 이미 원래대로다)." >&2
    exit 0
fi
if ! read -r LAN WAN < "$STATE/ports" || [ -z "$LAN" ] || [ -z "$WAN" ]; then
    echo "$STATE/ports 를 읽지 못했다. 추측해서 되돌리지 않는다. 기록을 확인하라." >&2
    exit 1
fi
fail=0
nft delete table ip pilab 2>/dev/null
ip link del br0.200 2>/dev/null
ip link del br0.201 2>/dev/null
ip link del br0 2>/dev/null
if [ -f "$STATE/ip_forward" ]; then
    sysctl -qw net.ipv4.ip_forward="$(cat "$STATE/ip_forward")" || { echo "IP 전달 설정을 되돌리지 못했다" >&2; fail=1; }
fi
if command -v nmcli >/dev/null; then
    for p in "$LAN" "$WAN"; do
        if [ -f "$STATE/managed.$p" ]; then
            nmcli device set "$p" managed "$(cat "$STATE/managed.$p")" || { echo "$p NetworkManager 관리 상태를 되돌리지 못했다" >&2; fail=1; }
        fi
    done
fi
if ip link show br0 >/dev/null 2>&1 || nft list table ip pilab >/dev/null 2>&1; then
    echo "되돌리기 실패: br0 또는 NAT 테이블이 남아 있다." >&2
    fail=1
fi
if [ "$fail" -ne 0 ]; then
    echo "$STATE 는 지우지 않는다. 원인을 고친 뒤 다시 실행하라." >&2
    exit 1
fi
rm -rf "$STATE"
echo "DUT reset"
