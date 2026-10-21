"""시험 케이스 등록과 판정 상태.

상태 정의 (4장):
  PASS     판정 기준을 만족했다
  FAIL     실행했고 판정 기준을 만족하지 못했다 (DUT 결함 후보)
  SKIP     실행하지 않았다. 이 랩에서 조건을 갖출 수 없다 (예: 포트 부족)
  BLOCKED  실행할 수 없었다. 선행 조건이 깨졌다 (예: BASELINE 실패, 환경 문제)
  N/A      이 제품·설정에는 해당하지 않는다. 시험표에서 정한다
  INVESTIGATING  사람이 붙이는 표시. 실행기는 쓰지 않는다
"""

import fnmatch
from dataclasses import dataclass

PASS, FAIL, SKIP, BLOCKED, NA = "PASS", "FAIL", "SKIP", "BLOCKED", "N/A"
STATUSES = [PASS, FAIL, SKIP, BLOCKED, NA, "INVESTIGATING"]


class Fail(Exception):
    """판정 기준 불만족."""


class Skip(Exception):
    """이 랩에서 실행할 조건이 안 된다."""


class Blocked(Exception):
    """선행 조건·환경 문제로 판정할 수 없다."""


@dataclass
class Case:
    id: str
    area: str
    title: str
    func: object
    needs: tuple = ()        # lab.yaml 의 hosts.*.vars 에 있어야 하는 키 (예: "lan1")
    retry: int = 0           # 환경 요인으로 흔들리는 시험만 재시도. 첫 실패는 기록에 남는다
    baseline: bool = False   # BASELINE 은 다른 시험보다 먼저 돌고, 실패하면 나머지는 BLOCKED


REGISTRY = {}


def case(id, area, title, needs=(), retry=0, baseline=False):
    def deco(func):
        if id in REGISTRY:
            raise ValueError(f"시험 ID 중복: {id}")
        REGISTRY[id] = Case(id, area, title, func, tuple(needs), retry, baseline)
        return func
    return deco


def select(patterns=None, areas=None):
    """ID 패턴(BR-*, NAT-00?)이나 영역으로 고른다. 아무 조건이 없으면 전부."""
    out = []
    for c in REGISTRY.values():
        if patterns and not any(fnmatch.fnmatch(c.id, p) for p in patterns):
            continue
        if areas and c.area not in areas:
            continue
        out.append(c)
    return sorted(out, key=lambda c: (not c.baseline, c.id))


def expect(cond, msg):
    """판정. 조건이 거짓이면 FAIL."""
    if not cond:
        raise Fail(msg)
