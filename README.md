# pilab — 라즈베리 파이 네트워크 시험 자동화 실습 코드

전자책 《라즈베리 파이로 만드는 네트워크 시험 자동화》(시리즈 《라즈베리 파이 × AI 실전 개발실》 1권)의 실습 저장소입니다.
책의 명령은 태그 `book1-v1.2` 기준입니다. 이 가지(태그 `book1-v1.2-br009`)는 16장에서 만든 시험 BR-009(LLDP 미전달)를 더한 결과입니다. (`book1-v1.0`, `book1-v1.1` 은 이전 공개본입니다. v1.2 를 쓰십시오.)

라즈베리 파이 한 대(또는 리눅스 PC 한 대) 안에 네트워크 네임스페이스로 시험 랩을 만들고, 그 위에서 시험 실행기·증거 로그·엑셀 결과표·회귀 비교를 실습합니다.

```
            라즈베리 파이 4 (또는 Ubuntu PC) 한 대
 ┌──────────────────────────────────────────────────────┐
 │ [pc] eth0 ──── lan0 [dut: br0, VLAN·NAT·QoS] wan0 ──── eth0 [pib] │
 └──────────────────────────────────────────────────────┘
   pc = LAN 쪽 단말, dut = 시험 대상 장비, pib = WAN 쪽 단말 (모두 가상)
```

## 시작 전에 꼭 읽기
- 이 코드는 `sudo` 로 네트워크 설정(네임스페이스, 브리지, VLAN, 방화벽, 속도 제한)을 만들고 지웁니다. **업무 자료나 인증 정보가 없는 시험 전용 파이·PC·VM** 에서 쓰십시오.
- 가상 랩은 `pc`, `dut`, `pib` 라는 이름의 네트워크 네임스페이스를 만듭니다. 같은 이름이 이미 있으면 만들지 않고 멈춥니다.
- 가상 랩의 처리량 값은 실제 네트워크 장비나 파이 유선 포트의 성능이 아닙니다. 커널 안에서 오가는 값입니다.

## 빠른 시작
라즈베리 파이 OS Lite 64비트(trixie) 또는 Ubuntu 24.04 기준입니다.
```sh
sudo apt install git iproute2 iputils-ping nftables iperf3 tcpdump python3-venv
git clone -b book1-v1.2 https://github.com/jjoong2dov/pilab.git ~/pilab
cd ~/pilab                                   # 이후 모든 명령은 이 폴더에서
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q                # 장비 없이 도는 단위 시험 (18 passed)
sudo sh netns/up.sh                          # 가상 랩 만들기
.venv/bin/python plan/make_plan.py           # 시험표 plan/plan.xlsx (처음 한 번)
sudo .venv/bin/python -m pitest run --lab lab.netns.yaml --plan plan/plan.xlsx
sudo sh netns/down.sh                        # 가상 랩 지우기
```
예상 결과: PASS 21, SKIP 1 (BR-009 포함) (BR-007 은 LAN 포트가 2개 필요해 SKIP). 라즈베리 파이 4 에서 약 1분 걸립니다. `sudo` 로 실행해도 결과 폴더와 시험표의 주인은 실행한 사용자로 돌려 놓습니다.

결함을 일부러 넣어 시험이 잡는지 볼 수 있습니다: `sudo sh netns/inject.sh vlan|flood|nat|lossy|leak300|lldpfwd` (되돌리기는 `down.sh` 후 `up.sh`).

## 자주 쓰는 명령
| 명령 | 하는 일 |
|---|---|
| `.venv/bin/python -m pitest summary results/<실행>` | 실행 결과 요약 |
| `.venv/bin/python -m pitest compare results/<이전> results/<이번>` | 두 실행 비교 (조건 차이를 먼저 보여 줌) |
| `.venv/bin/python -m pitest measures results/<실행1> results/<실행2> ... --only 'PERF-*'` | 측정값과 중앙값 (기준값 정하기) |
| `sudo .venv/bin/python -m pitest run --lab lab.netns.yaml --plan plan/plan.xlsx --resume results/<실행>` | 끊긴 실행 이어서 돌리기 |
| `sudo sh tools/repeat.sh 10` | 같은 전수를 10번 반복하며 첫 실행과 비교 |

## 구성
| 경로 | 내용 |
|---|---|
| `pitest/` | 실행기: 장비 연결, 시험 등록, 증거 기록, 전수 실행, 엑셀, 비교, 감시 |
| `cases/` | 시험 케이스 (BASE, L2, PERF, NAT, MCAST, QOS) |
| `helpers/` | 장비에 올려서 쓰는 도우미 (멀티캐스트 송수신, LLDP 송신) |
| `netns/` | 가상 랩 만들기·지우기, 결함 주입 |
| `plan/` | 시험표 만들기 |
| `tools/` | 반복 실행 |
| `tests/` | 실행기 단위 시험 |
| `pi/`, `lab.pi.yaml` | 실물 장비로 넓힐 때의 **설계안** (아래 참고) |

## 검증 범위
- 가상 랩: 라즈베리 파이 4 의 라즈베리 파이 OS Lite 64비트 2026-10-06 판(Debian 13, 커널 6.18, iperf3 3.18, Python 3.13)과 Ubuntu 24.04(커널 6.8, iperf3 3.16, Python 3.12)에서 전 시험, 결함 주입 5종, 중단·재개, 반복 실행을 확인했습니다. 다른 버전은 확인하지 않았습니다.
- ssh 로 명령을 보내는 경로: 원격 프로세스를 장비 안에서 끄고 마지막 출력(tcpdump 통계 등)을 받는 동작을 파이 한 대에서 ssh localhost 로 확인했습니다.
- `pi/` 스크립트와 `lab.pi.yaml`: PC·파이 두 대를 실제 케이블로 잇는 구성의 설계안입니다. 스크립트의 설정·되돌리기는 라즈베리 파이 OS 에서 veth 로 확인했지만, **실제 배선으로 전체 시험을 돌려 확인하지는 않았습니다.** 쓰려면 책 17장의 확인 순서를 따르고, 시험 포트는 사내망·집 공유기와 분리하십시오.
- 결과 폴더(`results/`)의 증거 로그에는 장비의 MAC 주소, 커널 로그, 인터페이스 정보가 들어갑니다. 공개하기 전에 확인하십시오.

## 문의
GitHub Issues 에 남겨 주십시오.

## 라이선스와 상표
- 이 저장소의 코드와 문서는 MIT 라이선스입니다(`LICENSE`). 전자책 본문의 이용 조건은 책을 따릅니다.
- Raspberry Pi is a trademark of Raspberry Pi Ltd. Claude 와 Claude Code 는 Anthropic, Codex 는 OpenAI, Microsoft Excel 은 Microsoft 의 상표입니다. 이 저장소와 책은 독립 저작물이며, 각 권리자의 공식 자료가 아니고 제휴·보증 관계도 없습니다.
