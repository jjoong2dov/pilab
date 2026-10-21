"""콘솔 로그에서 warn/error 찾기 (10장).

정상 동작이라면 시험 중 콘솔에 warn/error 가 없어야 한다. 하지만 키워드 검색은
오탐이 많으므로 판정(PASS/FAIL)은 바꾸지 않고, 결과에 따로 붙여 사람이 본다.
알려진 무해한 메시지는 console_allow.txt 에 정규식으로 적어 걸러 낸다.
"""

import re
from pathlib import Path

LEVELS = [
    ("panic", re.compile(r"kernel panic|oops|call trace|bug:|watchdog", re.I)),
    ("error", re.compile(r"\berr(or)?\b|fail(ed|ure)?\b", re.I)),
    ("warn", re.compile(r"\bwarn(ing)?\b", re.I)),
]


def load_allow(path):
    path = Path(path)
    if not path.exists():
        return []
    return [re.compile(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]


def scan(lines, allow=()):
    hits = []
    for line in lines:
        if any(a.search(line) for a in allow):
            continue
        for level, pat in LEVELS:
            if pat.search(line):
                hits.append({"level": level, "line": line.strip()[:300]})
                break
    return hits
