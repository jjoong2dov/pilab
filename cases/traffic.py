"""트래픽 시험 (7장). 판정 기준은 lab.yaml 의 expect 에 랩별로 적는다."""

from pitest.case import case, expect

from .util import iperf


@case("PERF-001", "PERF", "상향 TCP 처리량이 기준 이상이다")
def tcp_up(ctx):
    mbps, _ = iperf(ctx, ctx.pc, ctx.pib, ctx.pib.vars["ip"], seconds=ctx.expect.get("seconds", 5))
    ctx.measure("mbps", round(mbps))
    need = ctx.expect["tcp_mbps"]
    expect(mbps >= need, f"{mbps:.0f} Mbit/s < 기준 {need}")


@case("PERF-002", "PERF", "하향 TCP 처리량이 기준 이상이다")
def tcp_down(ctx):
    mbps, _ = iperf(ctx, ctx.pc, ctx.pib, ctx.pib.vars["ip"], seconds=ctx.expect.get("seconds", 5), reverse=True)
    ctx.measure("mbps", round(mbps))
    need = ctx.expect["tcp_mbps"]
    expect(mbps >= need, f"{mbps:.0f} Mbit/s < 기준 {need}")


@case("PERF-003", "PERF", "기준 속도의 UDP 를 손실 기준 이하로 전달한다", retry=1)
def udp_loss(ctx):
    rate = ctx.expect["udp_mbps"]
    mbps, loss = iperf(ctx, ctx.pc, ctx.pib, ctx.pib.vars["ip"], seconds=ctx.expect.get("seconds", 5),
                       udp=True, rate_mbps=rate)
    ctx.measure("mbps", round(mbps))
    ctx.measure("loss_pct", round(loss, 3))
    limit = ctx.expect["udp_loss_pct"]
    expect(loss <= limit, f"UDP {rate}M 손실 {loss:.3f}% > 기준 {limit}%")
