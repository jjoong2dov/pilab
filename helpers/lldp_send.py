"""LLDP 송신기: 인터페이스로 LLDP 프레임(01:80:c2:00:00:0e, 0x88cc)을 count 개 보내고 보낸 개수를 출력한다.
Chassis ID 에 --chassis 값을 넣는다. 받는 쪽은 이 값으로 시험 프레임만 골라 센다. root 필요.
--dst, --ethertype 을 바꾸면 같은 내용을 링크 로컬이 아닌 대조 프레임으로 보낸다."""
import argparse
import socket
import struct
import time

ap = argparse.ArgumentParser()
ap.add_argument("iface")
ap.add_argument("--chassis", required=True)
ap.add_argument("--dst", default="01:80:c2:00:00:0e")
ap.add_argument("--ethertype", type=lambda v: int(v, 0), default=0x88cc)
ap.add_argument("--count", type=int, default=10)
ap.add_argument("--interval", type=float, default=0.05)
a = ap.parse_args()


def tlv(kind, value):
    return struct.pack("!H", (kind << 9) | len(value)) + value


s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW)
s.bind((a.iface, 0))
src = s.getsockname()[4]
pdu = (tlv(1, b"\x07" + a.chassis.encode())          # Chassis ID, 7 = 임의 지정 값
       + tlv(2, b"\x05" + a.iface.encode())          # Port ID, 5 = 인터페이스 이름
       + tlv(3, struct.pack("!H", 120))              # TTL
       + tlv(0, b""))                                # End
frame = bytes.fromhex(a.dst.replace(":", "")) + src + struct.pack("!H", a.ethertype) + pdu
frame += b"\0" * (60 - len(frame))                   # 최소 프레임 길이(FCS 제외)
sent = 0
for _ in range(a.count):
    if s.send(frame) != len(frame):
        break
    sent += 1
    time.sleep(a.interval)
print(sent)
