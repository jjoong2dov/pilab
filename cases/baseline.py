"""BASELINE: 본 시험 전에 랩이 시험할 수 있는 상태인지 본다 (11장).

여기서 실패하면 DUT 결함이 아니라 랩 문제다. 나머지 시험은 BLOCKED 가 된다.
"설정이 기준과 같은가"까지만 보고, "기능이 동작하는가"는 본 시험이 판정한다.
"""

import json

from pitest.case import Blocked, case

TOOLS = {"pc": ["ping", "iperf3", "tcpdump", "python3", "timeout"],
         "pib": ["ping", "iperf3", "tcpdump", "python3", "timeout"],
         "dut": ["ip", "bridge", "nft", "tc", "tcpdump", "timeout"]}

# 포트별로 있어야 하는 VLAN (pvid 1 은 기본값이라 따로 보지 않는다)
VLANS = {"lan": {100, 200}, "wan": {100, 201}, "br0": {200, 201}}


@case("BASE-001", "BASE", "관리 연결: 모든 장비에 명령을 보낼 수 있다", baseline=True)
def management(ctx):
    for name, host in ctx.lab.hosts.items():
        if not host.run("true", timeout=10).ok:
            raise Blocked(f"{name} 에 명령을 보낼 수 없음")


@case("BASE-002", "BASE", "도구 확인: 시험에 필요한 명령이 설치돼 있다", baseline=True)
def tools(ctx):
    missing = []
    for name, tools in TOOLS.items():
        for t in tools:
            if not ctx.lab[name].run(f"command -v {t}").ok:
                missing.append(f"{name}:{t}")
    if missing:
        raise Blocked("없음 " + ", ".join(missing))


@case("BASE-003", "BASE", "DUT 설정 확인: 브리지·VLAN·NAT 설정이 기준과 같다", baseline=True)
def dut_config(ctx):
    d = ctx.dut
    ports = {"lan": d.vars.get("lan", "lan0"), "wan": d.vars.get("wan", "wan0"), "br0": "br0"}
    links = json.loads(d.run("ip -j link show master br0", check=True).out)
    members = {link["ifname"] for link in links}
    for role in ("lan", "wan"):
        if ports[role] not in members:
            raise Blocked(f"{ports[role]} 가 br0 에 없음")
    table = json.loads(d.run("bridge -j vlan show", check=True).out)
    have = {e["ifname"]: {v["vlan"] for v in e["vlans"]} for e in table}
    for role, need in VLANS.items():
        lack = need - have.get(ports[role], set())
        if lack:
            raise Blocked(f"{ports[role]} 에 VLAN {sorted(lack)} 없음")
    rules = d.run("nft list table ip pilab").out
    if "masquerade" not in rules or "policy drop" not in rules:
        raise Blocked("NAT 테이블(pilab)이 없거나 기준과 다름")
    ctx.note("DUT 설정이 기준과 같음")
