"""여러 시험이 같이 쓰는 측정 도구.

측정 자체가 실패하면(명령 없음, 권한, 타임아웃, 출력 해석 불가) Blocked 를 던진다.
"응답 없음"과 "재지 못함"을 섞으면, 막혀야 PASS 인 시험이 측정 실패로도 PASS 가 된다.
"""

import json
import re
import time

from pitest.case import Blocked
from pitest.lab import q


def ping(host, dst, count=10, interval=0.05, size=None, dont_fragment=False, iface=None):
    """손실률(%)을 돌려준다. ping 이 정상적으로 count 개를 보냈을 때만 값을 믿는다."""
    opts = f"-c {int(count)} -i {interval} -W 1"
    if size is not None:
        opts += f" -s {int(size)}"
    if dont_fragment:
        opts += " -M do"
    if iface:
        opts += f" -I {q(iface)}"
    res = host.run(f"ping {opts} {q(dst)}", timeout=count * interval + 15)
    m = re.search(r"(\d+) packets transmitted, (\d+) received", res.out)
    # ping 종료 코드: 0 응답 있음, 1 응답 없음, 2 이상 오류
    if res.timed_out or res.rc not in (0, 1) or not m:
        raise Blocked(f"{host.name} ping {dst} 실행 실패 rc={res.rc}: {(res.err or res.out).strip()[:200]}")
    sent, got = int(m.group(1)), int(m.group(2))
    if sent != count:
        raise Blocked(f"{host.name} ping 이 {count}개 중 {sent}개만 보냄: {res.err.strip()[:200]}")
    return round(100 * (sent - got) / sent, 1)


def iperf(ctx, client, server, server_ip, seconds=5, reverse=False, udp=False, rate_mbps=None):
    """iperf3 로 처리량(Mbit/s)과 UDP 손실률(%)을 잰다.

    TCP 는 받는 쪽 처리량, UDP 는 (보낸 쪽 송신률, 받는 쪽이 센 손실률)이다.
    UDP 는 정한 속도를 실제로 보냈는지도 확인한다. 송신 단말이 느려 목표보다 적게 보내면
    손실이 적게 나와 거짓 PASS 가 되기 때문이다.
    """
    srv = ctx.spawn(server, f"iperf3 -s -1 --forceflush -B {q(server_ip)}", limit=seconds + 30)
    if not srv.wait_ready("Server listening", timeout=10, stream="out"):
        raise Blocked(f"iperf3 서버 시작 실패: {srv.stop()[1].strip()[:200]}")
    opts = f"-c {q(server_ip)} -t {int(seconds)} -J"
    if reverse:
        opts += " -R"
    if udp:
        opts += f" -u -b {int(rate_mbps)}M"
    res = client.run(f"iperf3 {opts}", timeout=seconds + 20)
    srv.stop()
    try:
        data = json.loads(res.out)
    except json.JSONDecodeError:
        raise Blocked(f"iperf3 출력 해석 실패 rc={res.rc}: {res.err.strip()[:200]}")
    if "error" in data or not res.ok:
        raise Blocked(f"iperf3 오류: {data.get('error', res.err.strip()[:200])}")
    end = data["end"]
    if not udp:
        return end["sum_received"]["bits_per_second"] / 1e6, None
    # 보낸 쪽(sum_sent)과 받은 쪽(sum_received)을 따로 읽는다 (iperf3 3.16 JSON 기준)
    sent, recv = end.get("sum_sent", {}), end.get("sum_received", {})
    if not sent.get("packets") or "lost_percent" not in recv:
        raise Blocked("iperf3 UDP 결과에 송신 패킷 수·수신 손실률이 없음 (iperf3 버전 확인)")
    sent_mbps = sent["bits_per_second"] / 1e6
    if sent_mbps < rate_mbps * 0.9:
        raise Blocked(f"송신 부하 부족: 목표 {rate_mbps}M 중 {sent_mbps:.0f}M 만 보냄 (송신 단말 성능)")
    return sent_mbps, recv["lost_percent"]


class Capture:
    """tcpdump 로 패킷을 센다. 시작이 확인된 뒤에 트래픽을 보내야 센 값을 믿을 수 있다.

        with Capture(ctx, ctx.pc, "eth0", "udp and dst host 239.1.1.1", seconds=5) as cap:
            ...트래픽 보내기...
        cap.count
    """

    def __init__(self, ctx, host, iface, bpf, seconds, direction="in"):
        self.ctx, self.host, self.seconds = ctx, host, seconds
        self.cmd = f"tcpdump -i {q(iface)} -Q {direction} -nn -l -q {q(bpf)}"
        self.count, self.lines = None, []

    def __enter__(self):
        self.proc = self.ctx.spawn(self.host, self.cmd, limit=self.seconds)
        if not self.proc.wait_ready("listening on", timeout=10):
            raise Blocked(f"{self.host.name} tcpdump 시작 실패: {self.proc.stop()[1].strip()[:200]}")
        return self

    def __exit__(self, exc_type, *_):
        # 트래픽을 다 보낸 뒤 1초만 더 듣는다. seconds 는 '최대' 관찰 시간이다.
        out, err, alive = self.proc.finish(grace=1.0)
        if exc_type:
            return False
        self.lines = [line for line in out.splitlines() if " > " in line]  # 패킷 줄만
        self.count = len(self.lines)
        self.ctx.note(f"capture {self.host.name} {self.count}개: {self.cmd}")
        # 관찰 창이 송신보다 먼저 닫혔거나 커널이 패킷을 버렸다면 '0개'는 증거가 못 된다
        if not alive:
            raise Blocked(f"{self.host.name} 캡처가 송신이 끝나기 전에 끝남 (seconds={self.seconds} 가 짧음)")
        m = re.search(r"(\d+) packets? dropped by kernel", err)
        if m and int(m.group(1)) > 0:
            raise Blocked(f"{self.host.name} 캡처 중 커널이 패킷 {m.group(1)}개를 버림")
        return False


def wait_for(cond, timeout, step=0.5):
    """cond() 가 참이 될 때까지 기다린다. 걸린 시간(초) 또는 None."""
    start = time.time()
    while time.time() - start < timeout:
        if cond():
            return round(time.time() - start, 1)
        time.sleep(step)
    return None
