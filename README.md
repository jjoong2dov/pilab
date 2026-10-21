# pilab — 라즈베리 파이 네트워크 시험 자동화 실습 코드

《라즈베리 파이로 만드는 AI 네트워크 시험 자동화》 실습 저장소.

```
PC(USB 이더넷) ── eth0 [파이 A: 시험 대상 DUT] eth1 ── eth0 [파이 B]
```

## 빠른 시작 (장비 없이, 리눅스 노트북 한 대)
```sh
sudo apt install iperf3 tcpdump python3-venv
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
sudo sh netns/up.sh                       # 가상 랩 (약 15초)
.venv/bin/python plan/make_plan.py        # plan/plan.xlsx
sudo .venv/bin/python -m pitest run --lab lab.netns.yaml --plan plan/plan.xlsx
sudo sh netns/down.sh
```

## 라즈베리 파이 랩
`pi/` 의 스크립트와 `lab.pi.yaml` 을 쓴다. 자세한 순서는 책 2장.

## 구성
| 경로 | 내용 |
|---|---|
| `pitest/` | 실행기: 장비 연결, 시험 등록, 증거 기록, 전수 실행, 엑셀, 비교, 감시 |
| `cases/` | 시험 케이스 (BASE, L2, PERF, NAT, MCAST, QOS) |
| `helpers/` | 장비에 올려서 쓰는 도우미 (멀티캐스트 송수신) |
| `netns/` | 가상 랩 만들기·지우기, 결함 주입 |
| `pi/` | 라즈베리 파이 설정·복구 |
| `plan/` | 시험표 만들기 |
| `tests/` | 실행기 단위 시험 (`pytest -q`) |

## 검증 범위
- 가상 랩(netns): Ubuntu 24.04, 커널 6.8, iperf3 3.16, Python 3.12 에서 전 시험 확인.
- 라즈베리 파이: 책 출간 전 실기 확인 결과를 `docs/pi-verification.md` 에 적는다.
- 가상 랩의 처리량 값은 파이 성능이 아니다. 파이 기준값은 직접 재서 정한다.

## 라이선스
MIT
