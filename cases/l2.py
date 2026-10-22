"""L2 브리지 시험 (6장)."""

from pitest.case import Blocked, case, expect
from pitest.lab import q

from .util import Capture, has_iface, ping, wait_for

TEST_MAC = "02:00:5e:00:53:99"   # 시험 전용 MAC (로컬 관리 주소. 시험망에서 쓰는 MAC 과 겹치지 않게)
TEST_IP = "192.0.2.99"


@case("BR-001", "L2", "untagged 프레임이 LAN↔WAN 으로 전달된다")
def untagged(ctx):
    loss = ping(ctx.pc, ctx.pib.vars["ip"], count=20)
    ctx.measure("loss_pct", loss)
    expect(loss == 0, f"손실 {loss}%")


@case("BR-002", "L2", "허용한 VLAN(100) 프레임이 전달된다")
def vlan_allowed(ctx):
    loss = ping(ctx.pc, ctx.pib.vars["ip_vlan100"], count=20)
    ctx.measure("loss_pct", loss)
    expect(loss == 0, f"VLAN 100 손실 {loss}%")


@case("BR-003", "L2", "허용하지 않은 VLAN(300) 프레임은 버린다")
def vlan_denied(ctx):
    # ping 손실만 보면 거짓 PASS 가 날 수 있다. VLAN 300 에서는 ARP 부터 막히므로 요청이
    # 아예 나가지 않아도 '손실 100%' 가 된다. 그래서 상대 MAC 을 정적 이웃으로 넣어 ARP 없이
    # 요청이 나가게 하고, 보낸 쪽에서 나간 개수와 받는 쪽에 도착한 개수를 함께 센다.
    ends = ((ctx.pc, "192.0.2.130", ctx.pib, "192.0.2.140"), (ctx.pib, "192.0.2.140", ctx.pc, "192.0.2.130"))
    for host, me, peer_host, peer in ends:
        # pl300 이 이미 있으면 남의 것일 수 있으므로 만들지도 지우지도 않는다
        if has_iface(host, "pl300"):
            raise Blocked(f"{host.name} 에 pl300 인터페이스가 이미 있음 (이전 시험의 흔적인지 확인)")
    for host, me, peer_host, peer in ends:
        nic = q(host.vars["nic"])
        ctx.defer(lambda h=host: h.run("[ ! -e /sys/class/net/pl300 ] || ip link del pl300", check=True),
                  f"{host.name} VLAN 300 삭제")
        host.run(f"ip link add link {nic} name pl300 type vlan id 300", check=True)
        host.run(f"ip addr add {me}/32 dev pl300 && ip link set pl300 up && "
                 f"ip route add {peer}/32 dev pl300 && "
                 f"ip neigh replace {peer} lladdr {_mac(peer_host)} dev pl300 nud permanent", check=True)
    echo = "icmp[icmptype] == icmp-echo and src 192.0.2.130 and dst 192.0.2.140"
    # 받는 쪽은 태그와 상관없이 센다. DUT 가 태그를 떼거나 다른 VLAN 으로 바꿔 흘려도 '도착'이다.
    # (libpcap 은 'vlan' 뒤의 조건을 태그 안쪽으로 읽으므로 태그 없는 경우를 먼저 쓴다)
    with Capture(ctx, ctx.pc, ctx.pc.vars["nic"], f"vlan 300 and {echo}", seconds=10, direction="out") as left, \
         Capture(ctx, ctx.pib, ctx.pib.vars["nic"], f"({echo}) or (vlan and {echo})", seconds=10) as arrived:
        loss = ping(ctx.pc, "192.0.2.140", count=10)
    ctx.measure("loss_pct", loss)
    ctx.measure("vlan300_left_pc", left.count)
    ctx.measure("vlan300_reached_pib", arrived.count)
    if left.count < 10:
        raise Blocked(f"VLAN 300 요청이 pc 에서 10개 중 {left.count}개만 나감 (단말 VLAN·이웃 설정 확인, 차단 판정 불가)")
    expect(arrived.count == 0, f"막혀야 할 VLAN 300 요청 {arrived.count}개가 pib 에 도착")
    expect(loss == 100, f"막혀야 할 VLAN 300 이 {100 - loss:.0f}% 응답받음")


def _fdb(ctx):
    return ctx.dut.run("bridge fdb show br br0 dynamic", check=True).out


def _mac(host):
    return host.run(f"cat /sys/class/net/{q(host.vars['nic'])}/address", check=True).out.strip()


@case("BR-004", "L2", "단말 MAC 을 올바른 포트에서 학습한다")
def mac_learning(ctx):
    ping(ctx.pc, ctx.pib.vars["ip"], count=3)
    fdb = _fdb(ctx)
    lan, wan = ctx.dut.vars.get("lan", "lan0"), ctx.dut.vars.get("wan", "wan0")
    for host, port in ((ctx.pc, lan), (ctx.pib, wan)):
        mac = _mac(host)
        line = next((l for l in fdb.splitlines() if l.startswith(mac)), "")
        expect(f"dev {port}" in line, f"{host.name} MAC {mac} 을 {port} 에서 학습하지 못함: '{line}'")


@case("BR-005", "L2", "학습한 MAC 은 에이징 시간이 지나면 지운다")
def mac_ageing(ctx):
    # 단말의 진짜 MAC 은 mDNS·IPv6 등으로 계속 말을 하므로 에이징을 볼 수 없다.
    # 시험 전용 MAC 을 가진 macvlan 을 잠깐 만들어 몇 번 말하게 한 뒤 지운다.
    d, pc = ctx.dut, ctx.pc
    old = d.run("cat /sys/class/net/br0/bridge/ageing_time", check=True).out.strip()
    # 복구는 바꾸기 전에 등록한다. 바꾸는 명령이 시간 초과로 끝나도(실제로는 바뀌었을 수 있다) 되돌린다.
    ctx.defer(lambda: d.run(f"ip link set br0 type bridge ageing_time {int(old)}", check=True), "에이징 시간 복원")
    d.run("ip link set br0 type bridge ageing_time 500", check=True)  # 5초 (단위 1/100초)
    # plage 가 이미 있으면 남의 것일 수 있으므로 만들지도 지우지도 않는다
    if has_iface(pc, "plage"):
        raise Blocked("pc 에 plage 인터페이스가 이미 있음 (이전 시험의 흔적인지 확인)")
    ctx.defer(lambda: pc.run("[ ! -e /sys/class/net/plage ] || ip link del plage", check=True), "시험 MAC 삭제")
    pc.run(f"ip link add link {q(pc.vars['nic'])} name plage address {TEST_MAC} type macvlan mode bridge",
           check=True)
    pc.run("sysctl -qw net.ipv6.conf.plage.disable_ipv6=1", check=True)
    pc.run(f"ip addr add {TEST_IP}/32 dev plage && ip link set plage up", check=True)
    ping(pc, ctx.pib.vars["ip"], count=3, iface="plage")
    if TEST_MAC not in _fdb(ctx):
        raise Blocked("시험 MAC 을 학습조차 하지 않음 (macvlan 송신 확인 필요)")
    pc.run("ip link del plage", check=True)  # 이제 이 MAC 으로는 아무것도 안 나간다
    took = wait_for(lambda: TEST_MAC not in _fdb(ctx), timeout=15)
    ctx.measure("aged_after_s", took)
    expect(took is not None, "에이징 시간(5초)의 3배가 지나도 MAC 이 남아 있음")


@case("BR-006", "L2", "MTU: IP 1500 바이트는 전달하고, 넘는 프레임은 버린다")
def mtu(ctx):
    # 1500 은 IP 패킷 크기다 (ICMP 데이터 1472 + 헤더 28). 이더넷 헤더는 뺀 값.
    # 단말 MTU 를 잠깐 키워야 큰 패킷이 실제로 DUT 까지 간다. 아니면 단말이 스스로
    # 거부해서 "DUT 가 버렸다"와 구분할 수 없다(거짓 PASS).
    # 리눅스는 포트 MTU 를 검사할 때 VLAN 태그 4바이트만큼 여유를 두므로 1501~1504 는 지나간다.
    # 그래서 '넘는 프레임'은 여유를 확실히 넘는 IP 1508 바이트로 본다.
    for host in (ctx.pc, ctx.pib):
        nic = q(host.vars["nic"])
        old = host.run(f"cat /sys/class/net/{nic}/mtu", check=True).out.strip()
        ctx.defer(lambda h=host, n=nic, m=int(old): h.run(f"ip link set {n} mtu {m}", check=True),
                  f"{host.name} MTU 복원")
        host.run(f"ip link set {nic} mtu 1600", check=True)
    dst = ctx.pib.vars["ip"]
    ok = ping(ctx.pc, dst, count=5, size=1472, dont_fragment=True)
    # 1508 바이트가 보낸 쪽 선에 실제로 나갔는지, 받는 쪽에는 하나도 안 왔는지 함께 센다.
    # 이더넷 프레임 1522 = IP 1508 + 헤더 14
    big_bpf = f"icmp and src {ctx.pc.vars['ip']} and greater 1522"
    with Capture(ctx, ctx.pc, ctx.pc.vars["nic"], big_bpf, seconds=10, direction="out") as left, \
         Capture(ctx, ctx.pib, ctx.pib.vars["nic"], big_bpf, seconds=10) as arrived:
        big = ping(ctx.pc, dst, count=5, size=1480, dont_fragment=True)
    ctx.measure("loss_ip1500", ok)
    ctx.measure("loss_ip1508", big)
    ctx.measure("ip1508_left_pc", left.count)
    ctx.measure("ip1508_reached_pib", arrived.count)
    expect(ok == 0, f"IP 1500 바이트 손실 {ok}%")
    if left.count == 0:
        raise Blocked("IP 1508 바이트가 보내는 단말에서 나가지 않음 (단말 MTU 확인)")
    expect(arrived.count == 0 and big == 100, f"IP 1508 바이트 {arrived.count}개가 MTU 1500 포트를 지나감")


@case("BR-007", "L2", "LAN 포트끼리는 서로 격리된다", needs=("lan1",))
def lan_isolation(ctx):
    # 포트가 하나뿐인 기본 랩에서는 SKIP 된다. USB 이더넷을 하나 더 달면 lab.yaml 에 lan1 을 적는다.
    loss = ping(ctx.pc, ctx.dut.vars["lan1_peer_ip"], count=5)
    expect(loss == 100, "LAN 포트 사이로 프레임이 지나감")
