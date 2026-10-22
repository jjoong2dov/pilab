"""콘솔 로그에서 warn/error 찾기 (13장).

정상 동작이라면 시험 중 콘솔에 warn/error 가 없어야 한다. 판정(PASS/FAIL)은 바꾸지 않고,
결과에 따로 붙여 사람이 본다. 알려진 무해한 메시지는 console_allow.txt 에 정규식으로 적어 걸러 낸다.

journalctl -o json 으로 받으면 줄마다 커널이 붙인 심각도(PRIORITY)가 있다. 그 값으로 고른다.
낱말만 보면 'Undervoltage detected!'(심각도 crit)처럼 warn·error 라는 낱말이 없는 메시지를 놓친다.
JSON 이 아닌 줄(다른 형식의 console_cmd)은 낱말로만 찾는다.
"""

import json
import re
from pathlib import Path

LEVELS = [
    ("panic", re.compile(r"kernel panic|oops|call trace|bug:|watchdog", re.I)),
    ("error", re.compile(r"\berr(or)?\b|fail(ed|ure)?\b", re.I)),
    ("warn", re.compile(r"\bwarn(ing)?\b", re.I)),
]
# syslog 심각도: 0 emerg 1 alert 2 crit 3 err 4 warning (5 이상은 보지 않는다)
PRIORITY = {0: "crit", 1: "crit", 2: "crit", 3: "error", 4: "warn"}


def load_allow(path):
    path = Path(path)
    if not path.exists():
        return []
    return [re.compile(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]


def _parse(line):
    """(메시지, 심각도 또는 None). JSON 줄이 아니면 줄 전체와 None."""
    if line.startswith("{"):
        try:
            entry = json.loads(line)
        except ValueError:
            return line, None
        msg = entry.get("MESSAGE", "")
        if isinstance(msg, list):
            if all(isinstance(b, int) for b in msg):  # 출력할 수 없는 바이트가 섞이면 숫자 배열로 온다
                msg = bytes(b & 0xFF for b in msg).decode("utf-8", "replace")
            else:  # 같은 필드가 여러 번 있으면 문자열 배열로 온다
                msg = " / ".join(map(str, msg))
        elif not isinstance(msg, str):
            msg = str(msg)
        prio = entry.get("PRIORITY")
        return msg, int(prio) if str(prio).isdigit() else None
    return line, None


def scan(lines, allow=()):
    hits = []
    for line in lines:
        msg, prio = _parse(line)
        if any(a.search(msg) for a in allow):
            continue
        level = next((lv for lv, pat in LEVELS if pat.search(msg)), None)
        if level != "panic" and prio in PRIORITY:
            level = PRIORITY[prio]  # 심각도가 있으면 낱말보다 심각도를 믿는다
        elif prio is not None and level != "panic":
            level = None  # info·debug 인데 'failed' 같은 낱말만 있는 것은 넘긴다
        if level:
            hits.append({"level": level, "line": msg.strip()[:300]})
    return hits
