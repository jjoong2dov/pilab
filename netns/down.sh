#!/bin/sh
# 실습 랩을 지운다. 네임스페이스를 지우면 안의 veth·브리지도 같이 사라진다.
# up.sh 가 만들었다고 적어 둔 네임스페이스(/run/pilab-netns)만 지운다. 같은 이름의 남의 것은 건드리지 않는다.
MARK=/run/pilab-netns
if [ ! -f "$MARK" ]; then
    echo "up.sh 가 만든 랩 기록($MARK)이 없다. 지울 것이 없다." >&2
    exit 0
fi
left=""
while read -r ns; do
    [ -e "/run/netns/$ns" ] || continue          # 이미 없다
    ip netns del "$ns" || left="$left $ns"
done < "$MARK"
if [ -n "$left" ]; then
    echo "지우지 못한 네임스페이스:$left ($MARK 는 남겨 둔다)" >&2
    exit 1
fi
rm -f "$MARK"
echo "lab down"
