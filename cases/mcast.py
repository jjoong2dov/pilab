"""IGMP 스누핑 시험 (9장).

WAN 쪽(pib)이 멀티캐스트 서버, LAN 쪽(pc)이 시청자다. DUT 브리지는 IGMP 가입을
엿듣고(snooping), 가입한 포트로만 멀티캐스트를 보내야 한다.

순서가 중요하다: 캡처·수신기가 준비된 것을 확인한 다음에 보낸다. 반대로 하면
송신이 캡처 시작 전에 끝나서 '0개 관측'이 거짓 PASS 가 된다.
"""

import time

from pitest.case import Blocked, case, expect
from pitest.lab import q

from .util import Capture

GROUP, PORT = "239.1.1.1", 5000
BPF = f"udp and dst host {GROUP} and dst port {PORT}"


def _deploy(ctx):
    """도우미를 먼저 올려 둔다. 캡처를 연 뒤에 올리면 그 시간만큼 관찰 창이 줄어든다."""
    return ctx.helper(ctx.pib, "mcast_send.py"), ctx.helper(ctx.pc, "mcast_recv.py")


def _send(ctx, path, seconds=2, rate=50):
    """송신하고 보낸 개수를 돌려준다. 끝날 때까지 기다린다."""
    res = ctx.pib.run(f"python3 {q(path)} {GROUP} --port {PORT} --src {q(ctx.pib.vars['ip'])} "
                      f"--rate {int(rate)} --seconds {seconds}", timeout=seconds + 15)
    if not res.ok or not res.out.strip().isdigit() or int(res.out) == 0:
        raise Blocked(f"송신기 실패: {res.err.strip()[:200]}")
    return int(res.out)


def _joined(ctx, path, seconds):
    """가입해 있는 수신기를 띄운다. 가입이 끝났다는 신호(ready)를 받은 뒤 돌려준다."""
    rx = ctx.spawn(ctx.pc, f"python3 -u {q(path)} {GROUP} --port {PORT} --iface-ip {q(ctx.pc.vars['ip'])} "
                           f"--seconds {seconds}", limit=seconds + 10)
    if not rx.wait_ready("ready", timeout=10):
        raise Blocked(f"수신기 가입 실패: {rx.stop()[1].strip()[:200]}")
    time.sleep(1)  # IGMP report 가 브리지에 반영될 시간
    return rx


def _received(rx):
    out, err = rx.stop(timeout=30)
    lines = out.split()
    if not lines or not lines[-1].isdigit():
        raise Blocked(f"수신기 결과 없음: {err.strip()[:200]}")
    return int(lines[-1])


@case("MC-001", "MCAST", "가입하지 않은 그룹은 LAN 포트로 내보내지 않는다")
def no_join_no_flood(ctx):
    send, _ = _deploy(ctx)
    with Capture(ctx, ctx.pc, ctx.pc.vars["nic"], BPF, seconds=8) as cap:
        sent = _send(ctx, send)
    ctx.measure("sent", sent)
    ctx.measure("seen_on_lan", cap.count)
    expect(cap.count == 0, f"가입 없이 {cap.count}개가 LAN 으로 나옴")


@case("MC-002", "MCAST", "가입한 그룹은 LAN 포트로 전달한다", retry=1)
def join_delivers(ctx):
    send, recv = _deploy(ctx)
    rx = _joined(ctx, recv, seconds=6)
    sent = _send(ctx, send, seconds=2)
    got = _received(rx)
    ctx.measure("sent", sent)
    ctx.measure("received", got)
    expect(got >= sent * 0.9, f"보낸 {sent}개 중 {got}개만 받음")


@case("MC-003", "MCAST", "탈퇴하면 더 이상 LAN 포트로 내보내지 않는다")
def leave_stops(ctx):
    # 1) 가입 상태에서 실제로 받는지 먼저 확인한다. 가입이 안 된 채로는 '탈퇴 후 0개'가 의미 없다.
    send, recv = _deploy(ctx)
    rx = _joined(ctx, recv, seconds=4)
    sent = _send(ctx, send, seconds=1)
    got = _received(rx)  # 수신기가 끝나면서 소켓을 닫는다 = 탈퇴(IGMP leave)
    ctx.measure("received_while_joined", got)
    if got < sent * 0.9:
        raise Blocked(f"가입 상태에서도 {sent}개 중 {got}개만 받음 (MC-002 먼저 확인)")
    ctx.note("탈퇴 직후 mdb:\n" + ctx.dut.run("bridge mdb show", check=True).out)
    time.sleep(ctx.expect.get("leave_wait_s", 3))  # 마지막 가입자 확인 질의(last member query) 시간
    # 2) 탈퇴 뒤에는 LAN 에 하나도 나오지 않아야 한다
    with Capture(ctx, ctx.pc, ctx.pc.vars["nic"], BPF, seconds=8) as cap:
        _send(ctx, send)
    ctx.measure("seen_after_leave", cap.count)
    expect(cap.count == 0, f"탈퇴 뒤에도 {cap.count}개가 LAN 으로 나옴")
