"""NAT·방화벽 시험 (8장). LAN 은 VLAN 200, WAN 은 VLAN 201 로 라우팅한다."""

from pitest.case import Blocked, case, expect

from .util import Capture, ping


@case("NAT-001", "NAT", "LAN 단말이 WAN 쪽 서버에 닿는다")
def outbound(ctx):
    loss = ping(ctx.pc, ctx.pib.vars["wan_ip"], count=10)
    ctx.measure("loss_pct", loss)
    expect(loss == 0, f"손실 {loss}%")


@case("NAT-002", "NAT", "WAN 쪽에서는 LAN 주소 대신 DUT WAN 주소가 보인다")
def masquerade(ctx):
    wan_ip = ctx.dut.vars["wan_ip"]
    with Capture(ctx, ctx.pib, ctx.pib.vars["vlan_wan"], "icmp[icmptype] == icmp-echo", seconds=8) as cap:
        ping(ctx.pc, ctx.pib.vars["wan_ip"], count=3)
    seen = {line.split()[2] for line in cap.lines}
    ctx.measure("sources", ",".join(sorted(seen)))
    if not seen:
        raise Blocked("WAN 쪽에서 요청을 하나도 못 봄 (캡처 위치 확인)")
    expect(seen == {wan_ip}, f"WAN 에서 보인 출발지 {seen} (기대 {wan_ip})")


@case("NAT-003", "NAT", "WAN 에서 먼저 연 연결은 LAN 으로 들어오지 못한다")
def inbound_blocked(ctx):
    lan_ip = ctx.pc.vars["lan_ip"]
    # 대조 시험: LAN 단말은 DUT 의 ping 에 답한다. 이게 안 되면 아래 '응답 없음'은 증거가 못 된다.
    if ping(ctx.dut, lan_ip, count=3) != 0:
        raise Blocked("LAN 단말이 DUT ping 에도 응답하지 않음 (단말 방화벽 등)")
    bpf = f"icmp[icmptype] == icmp-echo and dst {lan_ip}"
    with Capture(ctx, ctx.dut, "br0.201", bpf, seconds=10) as at_wan, \
         Capture(ctx, ctx.pc, ctx.pc.vars["vlan_lan"], bpf, seconds=10) as at_lan:
        loss = ping(ctx.pib, lan_ip, count=5)
    ctx.measure("loss_pct", loss)
    ctx.measure("reached_dut_wan", at_wan.count)
    ctx.measure("reached_lan", at_lan.count)
    if at_wan.count == 0:
        # DUT 결함이 아니라 랩 경로 문제다. FAIL 로 적으면 없는 결함을 쫓게 된다.
        raise Blocked("요청이 DUT 까지 오지 않음 (랩 경로 문제, 방화벽 판정 불가)")
    expect(at_lan.count == 0, f"WAN 에서 연 요청 {at_lan.count}개가 LAN 까지 들어옴")
    expect(loss == 100, f"WAN→LAN 새 연결이 {100 - loss:.0f}% 응답받음")
