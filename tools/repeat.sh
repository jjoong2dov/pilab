#!/bin/sh
# 같은 전수를 N번 반복한다 (14장). 첫 실행을 기준으로 매번 비교하고, 중단·복구 실패면 멈춘다.
#
#   sudo sh tools/repeat.sh 10 lab.netns.yaml plan/plan.xlsx
#
# 실행마다 결과 폴더가 따로 생긴다. 남은 디스크가 500MB 아래로 내려가면 새 실행을 시작하지 않는다.
set -u
N=${1:?"사용법: sudo sh tools/repeat.sh 반복횟수 [lab.yaml] [plan.xlsx]"}
LAB=${2:-lab.netns.yaml}
PLAN=${3:-plan/plan.xlsx}
cd "$(dirname "$0")/.."
PY=.venv/bin/python
LOG=$(mktemp)
RC=$(mktemp)
trap 'rm -f "$LOG" "$RC"' EXIT
first=""
i=1
while [ "$i" -le "$N" ]; do
    free=$(df -Pm . | awk 'NR == 2 { print $4 }')
    if [ "$free" -lt 500 ]; then
        echo "남은 디스크 ${free}MB: 반복을 멈춘다 ($i/$N 전)"
        exit 4
    fi
    # 파이프 뒤의 종료 코드는 tee 의 것이므로 실행기의 종료 코드는 따로 받아 둔다
    { "$PY" -m pitest run --lab "$LAB" --plan "$PLAN" 2>&1; echo $? > "$RC"; } | tee "$LOG"
    rc=$(cat "$RC")
    run=$(sed -n 's/^실행 \([^ ]*\) .*/\1/p' "$LOG" | head -1)
    echo "== 반복 $i/$N: $run (종료 코드 $rc)"
    if [ -z "$run" ] || grep -q '^Traceback' "$LOG"; then
        # 결과 폴더도 못 만들고 끝났거나 실행기가 예외로 죽었다. 시험 FAIL 과 다른 실행 오류다
        echo "실행 자체가 실패했다. 위 메시지를 확인할 때까지 반복하지 않는다."
        exit 5
    fi
    if [ -z "$first" ]; then
        first=$run
    elif [ -n "$run" ]; then
        "$PY" -m pitest compare "$first" "$run"
    fi
    if grep -q '^중단됨:' "$LOG"; then
        echo "중단되거나 복구에 실패했다. 랩을 확인할 때까지 반복하지 않는다."
        exit 3
    fi
    i=$((i + 1))
done
echo "반복 $N번 끝. 기준 실행: $first"
