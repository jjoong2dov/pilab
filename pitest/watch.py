"""실행 감시 (11장).

전수 실행은 몇 시간씩 걸린다. 사람이(또는 AI 세션이) 계속 붙어 있을 필요 없이
run.json 을 주기적으로 읽어 진행 상황을 알리고, 끝나거나 멈추면 알림을 보낸다.

  python -m pitest watch results/20261021-101500 --every 1800 --notify "notify-send 시험"

멈춤 판정: 현재 시험이 stall 초 넘게 바뀌지 않으면 "멈춘 것 같다"고 알린다.
"""

import json
import shlex
import subprocess
import time
from pathlib import Path


def read_run(run_dir):
    p = Path(run_dir) / "run.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def progress(run_dir):
    data = read_run(run_dir)
    if not data:
        return None, "run.json 없음"
    st, results = data["state"], data["results"]
    done, total = len(st["done"]), st["total"]
    fails = [r["id"] for r in results if r["status"] in ("FAIL", "BLOCKED")]
    avg = sum(r["duration"] for r in results) / len(results) if results else 0
    eta = f" 남은 시간 약 {avg * (total - done) / 60:.0f}분" if avg and done < total else ""
    text = f"{done}/{total} 완료{eta}"
    if st["current"]:
        text += f", 실행 중 {st['current']}"
    if fails:
        text += f", 실패·막힘 {len(fails)}건 ({', '.join(fails[-5:])})"
    if st["finished"]:
        text = f"완료 {st['finished']}: " + text
    elif st.get("stopped"):
        text = f"중단됨 ({st['stopped']}): " + text
    return st, text


def notify(cmd, text):
    print(text, flush=True)
    if cmd:
        # 알림이 실패하거나 멈춰도 감시는 계속한다
        try:
            subprocess.run(shlex.split(cmd) + [text], check=False, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as e:
            print(f"알림 실패: {e}", flush=True)


def watch(run_dir, every=1800, stall=3600, notify_cmd="", once=False):
    last_key, last_change = None, time.time()
    while True:
        st, text = progress(run_dir)
        key = (len(st["done"]), st["current"]) if st else None
        if key != last_key:
            last_key, last_change = key, time.time()
        elif time.time() - last_change > stall:
            text = f"멈춘 것 같습니다({int(time.time() - last_change) // 60}분째 그대로): " + text
        notify(notify_cmd, text)
        if once or (st and (st["finished"] or st.get("stopped"))):
            return st
        time.sleep(every)
