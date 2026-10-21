"""빈 시험표(plan.xlsx)를 만든다. 자동화한 시험 + 사람이 하는 시험 + 해당 없는 시험."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pitest import plan  # noqa: E402

ROWS = [
    ("BASE-001", "BASE", "관리 연결", "모든 장비에 명령 전달"),
    ("BASE-002", "BASE", "도구 확인", "필요한 명령 설치됨"),
    ("BASE-003", "BASE", "DUT 설정 확인", "브리지·VLAN·NAT 설정이 기준과 같음"),
    ("BR-001", "L2", "untagged 전달", "ping 20회 손실 0%"),
    ("BR-002", "L2", "허용 VLAN(100) 전달", "ping 20회 손실 0%"),
    ("BR-003", "L2", "비허용 VLAN(300) 차단", "ping 10회 손실 100%"),
    ("BR-004", "L2", "MAC 학습", "pc MAC→LAN 포트, pib MAC→WAN 포트"),
    ("BR-005", "L2", "MAC 에이징", "에이징 5초 설정 후 15초 안에 삭제"),
    ("BR-006", "L2", "MTU 1500", "IP 1500B 손실 0%, IP 1508B(DF) 손실 100%"),
    ("BR-007", "L2", "LAN 포트 간 격리", "LAN 포트 사이 ping 손실 100% (LAN 포트 2개 필요)"),
    ("BR-008", "L2", "루프 방지(STP)", "루프 구성 시 한 포트 blocking (수동 시험)"),
    ("PERF-001", "PERF", "상향 TCP 처리량", "lab.yaml expect.tcp_mbps 이상"),
    ("PERF-002", "PERF", "하향 TCP 처리량", "lab.yaml expect.tcp_mbps 이상"),
    ("PERF-003", "PERF", "UDP 손실", "expect.udp_mbps 에서 손실 expect.udp_loss_pct 이하"),
    ("NAT-001", "NAT", "LAN→WAN 연결", "ping 10회 손실 0%"),
    ("NAT-002", "NAT", "주소 변환", "WAN 에서 본 출발지 = DUT WAN 주소"),
    ("NAT-003", "NAT", "WAN→LAN 새 연결 차단", "DUT 도달 > 0, LAN 응답 손실 100%"),
    ("MC-001", "MCAST", "미가입 그룹 차단", "LAN 에서 관측 0개"),
    ("MC-002", "MCAST", "가입 그룹 전달", "보낸 개수의 90% 이상 수신"),
    ("MC-003", "MCAST", "탈퇴 후 차단", "탈퇴 후 LAN 에서 관측 0개"),
    ("QOS-001", "QOS", "하향 속도 제한 50M", "측정값 40~55 Mbit/s"),
    ("QOS-002", "QOS", "속도 제한 해제 복원", "qdisc 기본값, expect.tcp_mbps 이상"),
    ("PHY-001", "PHY", "광 모듈 수신 레벨", "해당 없음 (구리 이더넷 랩)", "N/A"),
]

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--force"]
    out = Path(args[0] if args else Path(__file__).with_name("plan.xlsx"))
    if out.exists() and "--force" not in sys.argv:
        # 이미 결과가 쌓인 시험표를 새로 만들면 결과와 실행이력이 사라진다
        sys.exit(f"{out} 가 이미 있습니다. 새로 만들려면 다른 파일 이름을 주거나 --force 를 붙이십시오.")
    plan.new_plan(out, ROWS)
    print(f"{out}  항목 {len(ROWS)}개")
