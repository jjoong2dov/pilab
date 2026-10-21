"""속도 제한 시험 (10장). 시험이 DUT 설정을 바꾸고, 끝나면 반드시 되돌린다."""

from pitest.case import Blocked, case, expect
from pitest.lab import q

from .util import iperf

LIMIT = 50  # Mbit/s
DEFAULT_QDISCS = ("noqueue", "pfifo_fast", "fq_codel", "mq", "fq")


def _lan(ctx):
    return q(ctx.dut.vars.get("lan", "lan0"))


def _root_qdisc(ctx):
    out = ctx.dut.run(f"tc qdisc show dev {_lan(ctx)} root", check=True).out.split()
    return out[1] if len(out) > 1 else ""


@case("QOS-001", "QOS", f"하향 속도 제한({LIMIT} Mbit/s)을 지킨다")
def downstream_limit(ctx):
    d, lan = ctx.dut, _lan(ctx)
    # 원래 qdisc 가 기본값일 때만 바꾼다. 누가 따로 설정해 둔 것이면 지우면 복원할 수 없다.
    before = _root_qdisc(ctx)
    if before not in DEFAULT_QDISCS:
        raise Blocked(f"LAN 포트에 기본이 아닌 qdisc({before})가 있어 바꾸지 않음")
    # 복구는 바꾸기 전에 등록한다. 지울 때는 이 시험이 넣은 tbf 가 있을 때만 지운다.
    # 조회가 실패하면 복구 실패로 본다(조회 실패를 'tbf 없음'으로 읽지 않는다)
    ctx.defer(lambda: d.run(f"q=$(tc qdisc show dev {lan} root) || exit 1; "
                            f"case \"$q\" in 'qdisc tbf'*) tc qdisc del dev {lan} root ;; esac", check=True),
              "속도 제한 해제")
    d.run(f"tc qdisc replace dev {lan} root tbf rate {LIMIT}mbit burst 64kb latency 50ms", check=True)
    mbps, _ = iperf(ctx, ctx.pc, ctx.pib, ctx.pib.vars["ip"], seconds=5, reverse=True)
    ctx.measure("mbps", round(mbps, 1))
    expect(mbps <= LIMIT * 1.1, f"{mbps:.1f} Mbit/s 로 제한 {LIMIT} 의 110% 초과")
    expect(mbps >= LIMIT * 0.8, f"{mbps:.1f} Mbit/s 로 제한 {LIMIT} 의 80% 미만 (과하게 깎음)")


@case("QOS-002", "QOS", "속도 제한을 풀면 원래 처리량으로 돌아온다")
def limit_removed(ctx):
    # QOS-001 의 복구가 제대로 됐는지 본다. 복구가 안 됐으면 이후 시험이 모두 틀어진다.
    root = _root_qdisc(ctx)
    expect(root in DEFAULT_QDISCS, f"속도 제한이 남아 있음: {root}")
    mbps, _ = iperf(ctx, ctx.pc, ctx.pib, ctx.pib.vars["ip"], seconds=3, reverse=True)
    ctx.measure("mbps", round(mbps))
    need = ctx.expect["tcp_mbps"]  # PERF 와 같은 기준
    expect(mbps >= need, f"{mbps:.0f} Mbit/s < 기준 {need}, 제한이 풀리지 않은 것 같음")
