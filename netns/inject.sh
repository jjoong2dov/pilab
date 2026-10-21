#!/bin/sh
# 가상 DUT 에 일부러 결함을 넣는다 (13장 회귀 찾기 실습). 되돌리려면 down.sh 후 up.sh.
#   vlan   WAN 포트에서 VLAN 100 을 뺀다          → BASE-003 이 먼저 막아 나머지 BLOCKED
#   flood  IGMP 스누핑을 끈다(모든 멀티캐스트를 흘림) → MC-001, MC-003 FAIL
#   nat    주소 변환 규칙을 지운다                 → BASE-003 이 먼저 막아 나머지 BLOCKED
#   lossy  WAN 포트에 2% 손실을 넣는다             → PERF-003 FAIL, ping 시험 몇 개가 확률적으로 FAIL
set -eu
case "${1:-}" in
    vlan)  bridge -n dut vlan del dev wan0 vid 100 ;;
    flood) ip -n dut link set br0 type bridge mcast_snooping 0 ;;
    nat)   ip netns exec dut nft flush chain ip pilab postrouting ;;
    lossy) ip netns exec dut tc qdisc replace dev wan0 root netem loss 2% ;;
    *) echo "사용법: $0 vlan|flood|nat|lossy" >&2; exit 2 ;;
esac
echo "결함 주입: $1"
