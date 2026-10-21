"""멀티캐스트 송신기: 그룹으로 초당 rate 개씩 seconds 초 동안 보내고 보낸 개수를 출력한다."""
import argparse
import socket
import time

ap = argparse.ArgumentParser()
ap.add_argument("group")
ap.add_argument("--port", type=int, default=5000)
ap.add_argument("--src", default="")
ap.add_argument("--rate", type=int, default=50)
ap.add_argument("--seconds", type=float, default=3)
a = ap.parse_args()

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
if a.src:
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(a.src))
sent, end = 0, time.time() + a.seconds
while time.time() < end:
    s.sendto(f"pitest {sent}".encode(), (a.group, a.port))
    sent += 1
    time.sleep(1 / a.rate)
print(sent)
