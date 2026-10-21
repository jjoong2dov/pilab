#!/bin/sh
# 실습 랩을 지운다. 네임스페이스를 지우면 안의 veth·브리지도 같이 사라진다.
for ns in pc dut pib; do
    ip netns del "$ns" 2>/dev/null || true
done
echo "lab down"
