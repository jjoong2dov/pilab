"""전수 실행기 (11장).

- BASELINE 시험을 먼저 돌리고, 실패하면 나머지는 BLOCKED 로 남긴다.
- 시험마다 증거 로그를 남기고, 끝날 때마다 run.json 하나에 진행 상태와 결과를 함께
  저장한다. 중간에 끊겨도 --resume 으로 이어서 돌릴 수 있다.
- 재시도는 retry 를 준 시험만 한다. 첫 실패는 attempts 에 그대로 남긴다.
- 시험이 바꾼 설정은 ctx.defer() 로 등록한 복구 함수로 반드시 되돌린다. 복구가 실패하면
  랩이 오염된 것이므로 실행을 멈춘다.
- 콘솔 로그의 warn/error 는 판정을 바꾸지 않고 결과에 따로 붙인다 (13장).
"""

import json
import time
from pathlib import Path

from . import logscan
from .case import BLOCKED, FAIL, PASS, SKIP, Blocked, Fail, Skip
from .evidence import Recorder, stamp
from .lab import CommandFailed

HELPERS = Path(__file__).resolve().parent.parent / "helpers"


class LabDirty(Exception):
    """복구 실패. 랩을 초기화하고 BASELINE 부터 다시 해야 한다."""


class Context:
    """시험 함수가 받는 인자. 장비, 기대값, 증거 기록, 복구 등록을 묶는다."""

    def __init__(self, lab, recorder):
        self.lab = lab
        self.rec = recorder
        self.expect = lab.expect
        self._cleanups = []
        self.measured = {}

    def __getattr__(self, name):
        # ctx.dut, ctx.pc, ctx.pib 처럼 장비 이름으로 바로 쓴다
        hosts = self.__dict__["lab"].hosts
        if name in hosts:
            return hosts[name]
        raise AttributeError(name)

    def note(self, text):
        self.rec.note(text)

    def measure(self, key, value):
        """판정에 쓴 측정값. 결과 엑셀의 비고와 실행 비교에 나온다."""
        self.measured[key] = value
        self.rec.note(f"measure {key}={value}")

    def defer(self, func, label=""):
        """시험이 끝나면(성공·실패·중단 상관없이) 실행할 복구 작업을 등록한다."""
        self._cleanups.append((func, label))

    def spawn(self, host, cmd, limit):
        """host.spawn() 과 같고, 시험이 끝나면 자동으로 멈춘다."""
        proc = host.spawn(cmd, limit)
        self.defer(proc.stop, f"{host.name} 프로세스 정리")
        return proc

    def helper(self, host, name):
        """helpers/ 의 도우미 스크립트를 장비에 올리고 경로를 돌려준다."""
        return host.put(HELPERS / name)

    def run_cleanups(self):
        errors = []
        for func, label in reversed(self._cleanups):
            try:
                func()
            except Exception as e:  # 복구 실패는 다음 시험을 오염시키므로 꼭 드러낸다
                errors.append(f"{label or func.__name__}: {e}")
                self.rec.note(f"CLEANUP FAILED {label}: {e}")
        self._cleanups.clear()
        return errors


def _attempt(case, lab, recorder):
    ctx = Context(lab, recorder)
    status, reason = PASS, ""
    try:
        case.func(ctx)
    except Fail as e:
        status, reason = FAIL, str(e)
    except Skip as e:
        status, reason = SKIP, str(e)
    except (Blocked, CommandFailed) as e:
        status, reason = BLOCKED, str(e)
    except Exception as e:  # 시험 코드 버그도 PASS/FAIL 로 섞이면 안 된다
        status, reason = BLOCKED, f"시험 코드 예외: {type(e).__name__}: {e}"
    finally:
        # Ctrl-C 로 끊겨도 복구는 한다
        cleanup_errors = ctx.run_cleanups()
    recorder.note(f"=> {status} {reason}")
    return status, reason, ctx.measured, cleanup_errors


class Run:
    def __init__(self, lab, cases, root="results", exclude=None, resume=None, log=print):
        self.lab = lab
        self.cases = cases
        self.exclude = exclude or {}
        self.log = log
        spec = {"lab": lab.spec(), "cases": [c.id for c in cases], "exclude": sorted(self.exclude)}
        if resume:
            self.dir = Path(resume)
            saved = json.loads((self.dir / "run.json").read_text(encoding="utf-8"))
            if saved["spec"] != spec:
                raise SystemExit("이어서 돌리려는 랩·시험 목록·제외 목록이 처음과 다릅니다. 새로 실행하세요.")
            self.state, self.results = saved["state"], saved["results"]
            # 끊긴 사이 랩이 바뀌었을 수 있으므로 BASELINE 은 다시 돌린다. BASELINE 때문에 막혔던
            # 시험도 다시 돈다. 그 밖의 끝난 시험 결과는 그대로 둔다.
            redo = {r["id"] for r in self.results
                    if r.get("baseline") or r["reason"].startswith("BASELINE ")}
            self.results = [r for r in self.results if r["id"] not in redo]
            # 결과가 있는 시험과 제외한 시험만 '끝남'으로 본다 (저장 직전에 끊겼어도 어긋나지 않게)
            self.state["done"] = [r["id"] for r in self.results] + [i for i in self.exclude]
            self.state["finished"] = None
        else:
            self.dir = Path(root) / time.strftime("%Y%m%d-%H%M%S")
            self.dir.mkdir(parents=True)
            self.state = {"total": len(cases), "done": [], "current": None, "started": stamp(),
                          "finished": None, "stopped": None, "excluded": self.exclude}
            self.results = []
        self.spec = spec
        self.meta = self._meta()

    def _meta(self):
        p = self.dir / "meta.json"
        dut = self.lab.hosts.get("dut")
        version = dut.run(self.lab.dut_version_cmd).out.strip() if dut else ""
        if p.exists():
            meta = json.loads(p.read_text(encoding="utf-8"))
            if meta["dut_version"] != version:
                raise SystemExit(f"DUT 버전이 바뀌었습니다({meta['dut_version']} → {version}). 새로 실행하세요.")
            return meta
        meta = {"lab": self.lab.name, "dut_version": version, "tester": self.lab.tester,
                "started": stamp(), "cases": [c.id for c in self.cases]}
        p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return meta

    def _save(self):
        # 상태와 결과를 한 파일에 같이 쓴다. 따로 쓰면 그 사이에 죽었을 때 둘이 어긋난다.
        data = {"spec": self.spec, "state": self.state, "results": self.results}
        tmp = self.dir / "run.json.tmp"
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.dir / "run.json")  # 감시 스크립트가 반쯤 쓴 파일을 읽지 않게

    def _baseline_failed(self):
        """통과하지 못한(또는 아직 돌지 않은) BASELINE 이 있으면 그 ID."""
        passed = {r["id"] for r in self.results if r.get("baseline") and r["status"] == PASS}
        return next((c.id for c in self.cases if c.baseline and c.id not in passed), None)

    def execute(self):
        self.state["stopped"] = None
        try:
            for i, case in enumerate(self.cases, 1):
                if case.id in self.state["done"]:
                    continue
                if case.id in self.exclude:
                    self.log(f"[{i}/{len(self.cases)}] {case.id} 제외: {self.exclude[case.id]}")
                    self.state["done"].append(case.id)
                    continue
                self.state["current"] = case.id
                self._save()
                result = self._run_case(case)
                self.results.append(result)
                self.state["done"].append(case.id)
                self.state["current"] = None
                self._save()
                left = len(self.cases) - len(self.state["done"])
                self.log(f"[{i}/{len(self.cases)}] {case.id} {result['status']} "
                         f"({result['duration']:.1f}s) {result['reason'][:80]}  남은 시험 {left}")
                if result["cleanup_errors"]:
                    raise LabDirty(f"{case.id} 복구 실패: {'; '.join(result['cleanup_errors'])}")
        except (KeyboardInterrupt, LabDirty) as e:
            # 어느 시험에서 왜 멈췄는지 남긴다. current 는 지우지 않는다.
            self.state["stopped"] = f"{self.state['current'] or ''} {type(e).__name__}: {e}".strip()
            self.log(f"중단: {self.state['stopped']}")
            if isinstance(e, KeyboardInterrupt):
                raise
        finally:
            if len(self.state["done"]) == len(self.cases) and not self.state["stopped"]:
                self.state["finished"] = stamp()
            self._save()
        return self.results

    def _run_case(self, case):
        started = time.time()
        rec = Recorder(self.dir / "logs" / f"{case.id}.log")
        for h in self.lab.hosts.values():
            h.recorder = rec
        rec.note(f"case {case.id} {case.title}")
        attempts, cleanup_errors = [], []
        try:
            since = self._dut_clock()
            missing = [k for k in case.needs if not any(k in h.vars for h in self.lab.hosts.values())]
            blocked_by = None if case.baseline else self._baseline_failed()
            if missing:
                status, reason, measured = SKIP, f"랩에 없음: {', '.join(missing)}", {}
            elif blocked_by:
                status, reason, measured = BLOCKED, f"BASELINE 실패: {blocked_by}", {}
            else:
                for n in range(case.retry + 1):
                    if n:
                        rec.note(f"--- 재시도 {n}/{case.retry}")
                    status, reason, measured, cleanup_errors = _attempt(case, self.lab, rec)
                    attempts.append({"status": status, "reason": reason})
                    if status != FAIL or cleanup_errors:
                        break
            if cleanup_errors:
                reason = f"{reason} / 복구 실패: {'; '.join(cleanup_errors)}".lstrip(" /")
                status = BLOCKED if status == PASS else status
            console, console_error = self._console(since, rec)
        finally:
            for h in self.lab.hosts.values():
                h.recorder = None
            rec.close()
        return {
            "id": case.id, "area": case.area, "title": case.title, "status": status,
            "reason": reason, "measured": measured, "attempts": attempts,
            "flaky": len(attempts) > 1 and status == PASS, "cleanup_errors": cleanup_errors,
            "console": console, "console_error": console_error, "baseline": case.baseline,
            "started": stamp(started), "duration": round(time.time() - started, 2),
            "log": f"logs/{case.id}.log",
        }

    def _dut_clock(self):
        """콘솔 로그를 자를 기준 시각. 제어 PC 시계가 아니라 DUT 시계를 쓴다."""
        dut = self.lab.hosts.get("dut")
        if not self.lab.console_cmd or not dut:
            return None
        res = dut.run("date +%s", timeout=10)
        return int(res.out.strip()) if res.ok and res.out.strip().isdigit() else None

    def _console(self, since, rec):
        """시험 동안 DUT 콘솔(커널 로그)에 찍힌 warn/error 를 모은다. 판정은 바꾸지 않는다."""
        if not self.lab.console_cmd:
            return [], None
        if since is None:
            return [], "DUT 시각을 못 읽어 콘솔을 확인하지 못함"
        try:
            res = self.lab.hosts["dut"].run(self.lab.console_cmd.format(since=since))
            if not res.ok:
                return [], f"콘솔 수집 실패 rc={res.rc}: {res.err.strip()[:200]}"
            allow = logscan.load_allow(self.lab.path.parent / "console_allow.txt")
            hits = logscan.scan(res.out.splitlines(), allow)
        except Exception as e:  # 콘솔 확인이 실패해도 본 시험 결과는 지킨다
            return [], f"콘솔 확인 오류: {e}"
        for h in hits:
            rec.note(f"console {h['level']}: {h['line']}")
        return hits, None
