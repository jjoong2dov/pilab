# pilab — 라즈베리 파이 네트워크 시험 자동화 실습 코드

전자책 《라즈베리 파이로 만드는 네트워크 시험 자동화》(시리즈 《라즈베리 파이 × AI 실전 개발실》 1권)의 실습 저장소입니다.
책의 명령은 태그 `book1-v1.1` 기준입니다. (`book1-v1.0` 은 첫 공개본이며, 독자 장비 보호와 되돌리기가 약해 v1.1 을 쓰십시오.)

```
PC(USB 이더넷) ---- eth0 [파이 A: 시험 대상 DUT] eth1 ---- eth0 [파이 B]
```

## 시작 전에 꼭 읽기
- 이 코드는 `sudo` 로 네트워크 설정(브리지, VLAN, 방화벽, IP 전달, 속도 제한)을 바꿉니다. **업무 자료나 인증 정보가 없는 시험 전용 장비·VM** 에서 쓰십시오.
- 파이 랩의 유선 포트는 **실제 사내망·집 공유기에 연결하지 않은 별도 배선** 이어야 합니다. 시험 브리지는 STP 를 켜지 않으므로, 두 포트를 같은 스위치에 꽂으면 루프가 생길 수 있습니다.
- 파이 A 의 방화벽(nft 표 `pilab`)은 시험 VLAN 의 전달만 막지만, 컨테이너·VPN 등이 함께 도는 파이라면 쓰지 마십시오.
- 설정 스크립트는 바꾸기 전 상태를 `/run` 아래에 적어 두고, 되돌리기 스크립트가 그 기록대로 되돌립니다. 재부팅하면 설정과 기록이 함께 사라집니다.

## 빠른 시작 (장비 없이, 리눅스 PC 한 대)
Ubuntu 24.04 기준입니다.
```sh
sudo apt install git iproute2 iputils-ping nftables iperf3 tcpdump python3-venv
git clone -b book1-v1.1 https://github.com/jjoong2dov/pilab.git ~/pilab
cd ~/pilab                                   # 이후 모든 명령은 이 폴더에서
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q                # 장비 없이 도는 단위 시험
sudo sh netns/up.sh                          # 가상 랩 만들기 (약 15초)
.venv/bin/python plan/make_plan.py           # 시험표 plan/plan.xlsx (처음 한 번)
sudo .venv/bin/python -m pitest run --lab lab.netns.yaml --plan plan/plan.xlsx
sudo sh netns/down.sh                        # 가상 랩 지우기
```
예상 결과: PASS 20, SKIP 1 (BR-007 은 LAN 포트가 2개 필요해 SKIP). `sudo` 로 실행해도 결과 폴더와 시험표의 주인은 실행한 사용자로 돌려 놓습니다.

## 라즈베리 파이 랩
| 장비 | 설정 | 되돌리기 |
|---|---|---|
| 파이 A (DUT) | `sudo sh pi/dut-setup.sh [LAN] [WAN]` | `sudo sh pi/dut-reset.sh` |
| 파이 B | `sudo sh pi/endpoint-setup.sh pib eth0` | `sudo sh pi/endpoint-reset.sh` |
| PC | `sudo sh pi/endpoint-setup.sh pc <USB 이더넷 이름>` | `sudo sh pi/endpoint-reset.sh` |

관리 접속(SSH)은 Wi-Fi 등 시험 포트가 아닌 길로 합니다. SSH 가 시험 포트로 들어와 있으면 스크립트가 멈춥니다. 준비 순서(OS 설치, SSH 키, sudo 설정, `lab.pi.yaml` 의 인터페이스 이름 바꾸기)는 책 2장에 있습니다. 라즈베리 파이 실기 확인 결과는 출간 전에 이 저장소에 추가합니다.

## 구성
| 경로 | 내용 |
|---|---|
| `pitest/` | 실행기: 장비 연결, 시험 등록, 증거 기록, 전수 실행, 엑셀, 비교, 감시 |
| `cases/` | 시험 케이스 (BASE, L2, PERF, NAT, MCAST, QOS) |
| `helpers/` | 장비에 올려서 쓰는 도우미 (멀티캐스트 송수신) |
| `netns/` | 가상 랩 만들기·지우기, 결함 주입 |
| `pi/` | 라즈베리 파이·PC 설정과 되돌리기 |
| `plan/` | 시험표 만들기 |
| `tests/` | 실행기 단위 시험 |

## 검증 범위
- 가상 랩(netns): Ubuntu 24.04(커널 6.8, iperf3 3.16, Python 3.12) PC 와, 라즈베리 파이 4 의 라즈베리 파이 OS Lite 64비트 2026-10-06 판(Debian 13, 커널 6.18, iperf3 3.18, Python 3.13) 에서 전 시험을 확인했습니다. 다른 버전은 확인하지 않았습니다.
- `pi/` 스크립트: 라즈베리 파이 OS(NetworkManager) 에서 시험 포트 대신 veth 로 설정·되돌리기를 확인했습니다. USB 이더넷과 파이 두 대를 실제로 배선한 랩 확인은 출간 전에 추가합니다.
- 되돌리기 범위: 설정 스크립트는 IPv4 주소·경로, NetworkManager 관리 상태, IP 전달 값을 기록해 되돌립니다. 그 밖의 수동 설정(IPv6 경로 정책, 정책 라우팅, 다른 sysctl)이 있는 장비는 쓰지 마십시오.
- 가상 랩의 처리량 값은 파이 성능이 아닙니다. 파이 랩의 기준값은 직접 재서 정합니다(책 2장, 7장).
- 결과 폴더(`results/`)의 증거 로그에는 장비의 MAC 주소, 커널 로그, 인터페이스 정보가 들어갑니다. 공개하기 전에 확인하십시오.

## 문의
GitHub Issues 에 남겨 주십시오.

## 라이선스와 상표
- 이 저장소의 코드와 문서는 MIT 라이선스입니다(`LICENSE`). 전자책 본문의 이용 조건은 책을 따릅니다.
- Raspberry Pi is a trademark of Raspberry Pi Ltd. Claude 와 Claude Code 는 Anthropic, Codex 는 OpenAI, Microsoft Excel 은 Microsoft 의 상표입니다. 이 저장소와 책은 독립 저작물이며, 각 권리자의 공식 자료가 아니고 제휴·보증 관계도 없습니다.
