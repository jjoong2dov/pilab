"""시험 ID별 증거 기록: 언제, 어느 장비에서, 무슨 명령을, 어떤 결과로.

"AI가 PASS라고 했다"가 아니라 "이 로그가 PASS를 보여 준다"가 되도록,
판정에 쓴 모든 명령과 출력은 여기로 남긴다.
"""

import time
from pathlib import Path


def stamp(t=None):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t or time.time()))


class Recorder:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = self.path.open("a", encoding="utf-8")  # 재개해도 이전 시도 로그를 지우지 않는다

    def note(self, text):
        self._f.write(f"{stamp()} {text}\n")
        self._f.flush()

    def command(self, host, res):
        flag = " TIMEOUT" if res.timed_out else ""
        self._f.write(f"{stamp(res.started)} [{host}] $ {res.cmd}\n")
        self._f.write(f"    rc={res.rc}{flag} ({res.elapsed:.2f}s)\n")
        for label, text in (("out", res.out), ("err", res.err)):
            text = text.rstrip()
            if text:
                lines = text.splitlines()
                if len(lines) > 200:  # 너무 긴 출력은 앞뒤만
                    lines = lines[:100] + [f"... ({len(lines) - 200}줄 생략) ..."] + lines[-100:]
                self._f.write("".join(f"    {label}| {line}\n" for line in lines))
        self._f.flush()

    def close(self):
        self._f.close()
