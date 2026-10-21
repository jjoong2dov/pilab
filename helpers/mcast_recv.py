"""멀티캐스트 수신기: 그룹에 가입(IGMP join)해서 seconds 초 동안 받은 개수를 출력한다.
끝날 때 소켓을 닫으면 커널이 탈퇴(IGMP leave)를 보낸다."""
import argparse
import socket
import struct
import sys
import time

ap = argparse.ArgumentParser()
ap.add_argument("group")
ap.add_argument("--port", type=int, default=5000)
ap.add_argument("--iface-ip", default="0.0.0.0")
ap.add_argument("--seconds", type=float, default=5)
a = ap.parse_args()

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("", a.port))
mreq = struct.pack("4s4s", socket.inet_aton(a.group), socket.inet_aton(a.iface_ip))
s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
print("ready", file=sys.stderr, flush=True)  # 가입 완료 신호
s.settimeout(0.2)
got, end = 0, time.time() + a.seconds
while time.time() < end:
    try:
        s.recv(2048)
        got += 1
    except socket.timeout:
        pass
s.close()
print(got)
