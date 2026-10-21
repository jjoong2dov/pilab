"""명령줄 진입점.

  python -m pitest list                                  등록된 시험 목록
  python -m pitest run --lab lab.netns.yaml --plan plan/plan.xlsx [--only 'BR-*'] [--exclude exclude.txt]
  python -m pitest run --resume results/20261021-101500 --lab lab.netns.yaml --plan plan/plan.xlsx
  python -m pitest rerun-failed results/OLD --lab ... --plan ...   이전 실행의 실패·막힘만 다시
  python -m pitest summary results/RUN
  python -m pitest compare results/OLD results/NEW
  python -m pitest slow results/RUN
  python -m pitest watch results/RUN [--every 1800] [--notify CMD]
"""

import argparse
import importlib
import os
import pkgutil
import signal
import sys
from pathlib import Path

from . import plan, report, watch
from .case import REGISTRY, select
from .lab import lab_lock, load_lab
from .runner import Run

ROOT = Path(__file__).resolve().parent.parent


def load_cases():
    sys.path.insert(0, str(ROOT))
    import cases
    for m in pkgutil.iter_modules(cases.__path__):
        importlib.import_module(f"cases.{m.name}")


def read_exclude(path):
    """exclude.txt: 'ID  이유' 한 줄씩. 이유 없이 빼지 않도록 이유를 강제한다."""
    out = {}
    if not path:
        return out
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        id_, _, why = line.partition(" ")
        if not why.strip():
            raise SystemExit(f"제외 이유가 없습니다: {id_}")
        out[id_] = why.strip()
    return out


def plan_cases(args, only=None):
    items = plan.read_plan(args.plan)
    planned = [i["id"] for i in items if i["status"] not in plan.KEEP]
    missing = [i for i in planned if i not in REGISTRY]
    if missing:
        print(f"시험표에는 있지만 자동화 안 된 항목 {len(missing)}개: {', '.join(missing)}")
    baseline = [c.id for c in select() if c.baseline]
    lacking = [i for i in baseline if i not in planned]
    if lacking:
        raise SystemExit(f"BASELINE 이 시험표에 없거나 N/A·INVESTIGATING 입니다: {', '.join(lacking)}")
    patterns = only or args.only
    chosen = {c.id: c for c in select(patterns)}
    chosen.update({c.id: c for c in select() if c.baseline})  # 일부만 돌려도 BASELINE 은 항상
    ordered = [chosen[i] for i in planned if i in chosen]  # 시험표 순서를 따른다
    if patterns and all(c.baseline for c in ordered):
        raise SystemExit(f"고른 시험이 없습니다: {' '.join(patterns)}")
    return sorted(ordered, key=lambda c: not c.baseline)  # BASELINE 은 맨 앞


def cmd_run(args, only=None, resume=None):
    lab = load_lab(args.lab)
    cases = plan_cases(args, only)
    exclude = read_exclude(args.exclude)
    skipped_base = [c.id for c in cases if c.baseline and c.id in exclude]
    if skipped_base:
        raise SystemExit(f"BASELINE 은 제외할 수 없습니다: {', '.join(skipped_base)}")
    unknown_ex = [i for i in exclude if i not in {c.id for c in cases}]
    if unknown_ex:  # 패턴이나 오타는 아무것도 빼지 못한 채 조용히 넘어가므로 막는다
        raise SystemExit(f"제외 목록의 ID 가 이번 실행 시험에 없습니다(패턴은 쓸 수 없음): {', '.join(unknown_ex)}")
    with lab_lock(lab):
        run = Run(lab, cases, root=args.results, exclude=exclude, resume=resume or args.resume)
        print(f"실행 {run.dir}  시험 {len(cases)}개  DUT {run.meta['dut_version']}")
        try:
            results = run.execute()
        except KeyboardInterrupt:
            results = run.results  # 끊기기 전까지의 결과는 엑셀에 남긴다
        # 엑셀도 잠금 안에서 쓴다. 다른 실행이 같은 시험표를 동시에 저장하면 한쪽이 사라진다.
        unknown = plan.apply_results(args.plan, results, run.meta, run.dir)
        give_back(run.dir, args.plan)
    if unknown:
        print(f"시험표에 없는 결과: {', '.join(unknown)}")
    print(report.summary(run.dir))
    if run.state["stopped"]:
        print(f"중단됨: {run.state['stopped']}\n"
              f"랩 상태를 확인(필요하면 초기화)하고 같은 옵션에 --resume {run.dir} 를 붙여 이어서 돌리세요.")
        return 3
    return 0 if all(r["status"] in ("PASS", "SKIP") for r in results) else 1


def give_back(*paths):
    """sudo 로 돌렸으면 결과 폴더와 시험표의 주인을 sudo 를 부른 사용자로 돌려준다.
    그러지 않으면 다음에 sudo 없이 시험표를 열어 고치거나 결과를 지울 때 권한 오류가 난다."""
    uid, gid = os.environ.get("SUDO_UID"), os.environ.get("SUDO_GID")
    if os.geteuid() != 0 or not uid or not gid:
        return
    for p in map(Path, paths):
        # 심볼릭 링크는 따라가지 않는다(링크가 가리키는 바깥 파일의 주인을 바꾸지 않게)
        for q in [p, *(p.rglob("*") if p.is_dir() and not p.is_symlink() else [])]:
            os.lchown(q, int(uid), int(gid))
        # results/ 폴더 자체는 이번에 root 로 만들어진 경우에만 돌려준다
        if p.is_dir() and p.parent.stat().st_uid == 0:
            os.lchown(p.parent, int(uid), int(gid))


def cmd_rerun_failed(args):
    res, _ = report.load(args.old)
    ids = [i for i, r in res.items() if r["status"] in ("FAIL", "BLOCKED")]
    if not ids:
        print("다시 돌릴 실패가 없습니다")
        return 0
    baseline = [c.id for c in select() if c.baseline]
    return cmd_run(args, only=baseline + ids)


def main(argv=None):
    load_cases()
    ap = argparse.ArgumentParser(prog="pitest")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    for name in ("run", "rerun-failed"):
        p = sub.add_parser(name)
        if name == "rerun-failed":
            p.add_argument("old")
        p.add_argument("--lab", required=True)
        p.add_argument("--plan", required=True)
        p.add_argument("--only", nargs="*")
        p.add_argument("--exclude")
        p.add_argument("--resume")
        p.add_argument("--results", default="results")
    for name in ("summary", "slow"):
        sub.add_parser(name).add_argument("run")
    p = sub.add_parser("compare")
    p.add_argument("old")
    p.add_argument("new")
    p = sub.add_parser("watch")
    p.add_argument("run")
    p.add_argument("--every", type=int, default=1800)
    p.add_argument("--stall", type=int, default=3600)
    p.add_argument("--notify", default="")
    p.add_argument("--once", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "list":
        for c in select():
            print(f"{c.id:10} {c.area:6} {c.title}{'  [BASELINE]' if c.baseline else ''}")
        return 0
    if args.cmd in ("run", "rerun-failed"):
        # 스크립트나 nohup 으로 띄운 백그라운드 실행은 SIGINT 를 무시한 채로 시작한다.
        # 그래도 kill -INT 나 kill(TERM)로 멈추면 Ctrl-C 와 똑같이 복구하고 끝나게 한다.
        def stop(signum, frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "rerun-failed":
        return cmd_rerun_failed(args)
    if args.cmd == "summary":
        print(report.summary(args.run))
    elif args.cmd == "slow":
        print(report.slowest(args.run))
    elif args.cmd == "compare":
        print(report.format_compare(report.compare(args.old, args.new)))
    elif args.cmd == "watch":
        watch.watch(args.run, args.every, args.stall, args.notify, args.once)
    return 0


if __name__ == "__main__":
    sys.exit(main())
