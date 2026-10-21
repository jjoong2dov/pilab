"""실행 결과 요약과 두 실행 비교 (10장, 12장)."""

import json
from collections import Counter
from pathlib import Path

GOOD = {"PASS"}


def load(run_dir):
    run_dir = Path(run_dir)
    if not (run_dir / "run.json").exists():
        raise SystemExit(f"결과 폴더가 아니거나 아직 결과가 없습니다: {run_dir} (results/ 아래 실행 폴더를 주십시오)")
    results = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["results"]
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    return {r["id"]: r for r in results}, meta


def summary(run_dir):
    res, meta = load(run_dir)
    state = json.loads((Path(run_dir) / "run.json").read_text(encoding="utf-8")).get("state", {})
    c = Counter(r["status"] for r in res.values())
    lines = [f"실행 {Path(run_dir).name}  DUT {meta.get('dut_version', '')}  수행자 {meta.get('tester', '')}",
             "  " + "  ".join(f"{k} {v}" for k, v in sorted(c.items()))]
    for r in res.values():
        if r["status"] not in GOOD:
            lines.append(f"  {r['status']:8} {r['id']:10} {r['reason'][:90]}")
    flaky = [r["id"] for r in res.values() if r["flaky"]]
    if flaky:
        lines.append(f"  흔들림(재시도 후 PASS): {', '.join(flaky)}")
    for id_, why in state.get("excluded", {}).items():
        lines.append(f"  제외     {id_:10} {why}")
    unchecked = [r["id"] for r in res.values() if r.get("console_error")]
    if unchecked:
        lines.append(f"  콘솔 확인 못 함: {', '.join(unchecked)}")
    noisy = [f"{r['id']}({len(r['console'])})" for r in res.values() if r["console"]]
    if noisy:
        lines.append(f"  콘솔 warn/error: {', '.join(noisy)}")
    return "\n".join(lines)


def compare(old_dir, new_dir):
    """이전 실행 대비 바뀐 것. 회귀(이전 PASS → 지금 FAIL)를 맨 위에 둔다."""
    old, _ = load(old_dir)
    new, _ = load(new_dir)
    out = {"regressed": [], "blocked": [], "fixed": [], "changed": [], "new": [], "missing": []}
    for id_, r in new.items():
        if id_ not in old:
            out["new"].append((id_, None, r["status"]))
            continue
        a, b = old[id_]["status"], r["status"]
        if a == b:
            continue
        if a in GOOD:
            # PASS → FAIL 만 DUT 회귀다. PASS → BLOCKED/SKIP 은 랩·환경 쪽을 먼저 본다.
            key = "regressed" if b == "FAIL" else "blocked"
        else:
            key = "fixed" if b in GOOD else "changed"
        out[key].append((id_, a, b))
    out["missing"] = [(id_, old[id_]["status"], None) for id_ in old if id_ not in new]
    return out


def format_compare(diff):
    names = {"regressed": "회귀", "blocked": "막힘", "fixed": "해결", "changed": "변경", "new": "새 시험"}
    lines = []
    for key, label in names.items():
        for id_, a, b in diff[key]:
            lines.append(f"{label:6} {id_:10} {a or '-':8} -> {b or '-'}")
    if diff["missing"]:  # 부분 실행이면 많으므로 개수만
        lines.append(f"이번에 안 돈 시험 {len(diff['missing'])}개")
    return "\n".join(lines) or "바뀐 결과 없음"


def slowest(run_dir, n=10):
    res, _ = load(run_dir)
    rows = sorted(res.values(), key=lambda r: -r["duration"])[:n]
    total = sum(r["duration"] for r in res.values())
    lines = [f"전체 {total / 60:.1f}분"]
    lines += [f"  {r['duration']:7.1f}s  {r['duration'] / total:5.1%}  {r['id']}" for r in rows]
    return "\n".join(lines)
