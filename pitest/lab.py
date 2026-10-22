"""랩 구성(lab.yaml)과 장비에 명령을 보내는 방법.

장비마다 transport 가 netns 이면 `ip netns exec`, ssh 이면 ssh 로 명령을 보낸다.
시험 코드는 어느 쪽인지 몰라도 된다. 그래서 가상 랩에서 만든 시험을 ssh 로 닿는
실물 장비에도 같은 코드로 보낼 수 있다(장비별 명령이 같다면. 17장).

lab.yaml 은 실행 권한을 가진 설정이다(dut_version_cmd, console_cmd 는 셸 명령 그대로
실행된다). 남이 준 lab.yaml 은 읽어 보고 쓴다.
"""

import fcntl
import os
import shlex
import signal
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import yaml

SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-o", "ServerAliveInterval=5"]
PID_MARK = "@@pitest-pid "  # spawn() 이 장비 쪽 PID 를 알려 주는 줄
q = shlex.quote  # 설정값을 명령에 넣을 때는 항상 q() 로 감싼다


@dataclass
class CmdResult:
    cmd: str
    rc: int
    out: str
    err: str
    started: float
    elapsed: float
    timed_out: bool = False

    @property
    def ok(self):
        return self.rc == 0 and not self.timed_out


@dataclass
class Host:
    name: str
    transport: str            # "netns" | "ssh" | "local"
    target: str = ""          # netns 이름 또는 user@address
    sudo: bool = False
    vars: dict = field(default_factory=dict)
    recorder: object = None   # evidence.Recorder, 실행기가 시험마다 바꿔 끼운다
    _home: str = None

    def _argv(self, cmd, sudo=None):
        # 출력 해석(ping 통계 등)이 언어 설정에 흔들리지 않게 C 로케일로 실행한다
        cmd = f"export LC_ALL=C; {cmd}"
        if self.sudo if sudo is None else sudo:
            cmd = f"sudo -n sh -c {q(cmd)}"
        if self.transport == "netns":
            return ["ip", "netns", "exec", self.target, "sh", "-c", cmd]
        if self.transport == "ssh":
            return ["ssh", *SSH_OPTS, self.target, cmd]
        return ["sh", "-c", cmd]

    def run(self, cmd, timeout=30, check=False, sudo=None):
        """명령을 실행하고 결과를 증거로 남긴다. check=True 면 실패 시 예외.
        sudo=False 는 lab.yaml 의 sudo 설정과 상관없이 로그인 사용자로 실행한다."""
        started = time.time()
        p = subprocess.Popen(self._argv(cmd, sudo), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, start_new_session=True)
        try:
            out, err = p.communicate(timeout=timeout)
            res = CmdResult(cmd, p.returncode, out, err, started, time.time() - started)
        except subprocess.TimeoutExpired:
            _kill(p)
            out, err = p.communicate()
            res = CmdResult(cmd, -1, out, err, started, time.time() - started, True)
        except KeyboardInterrupt:
            _kill(p)  # 새 세션이라 Ctrl-C 가 전달되지 않는다. 복구 전에 직접 끈다
            raise
        if self.recorder:
            self.recorder.command(self.name, res)
        if check and not res.ok:
            raise CommandFailed(self.name, res)
        return res

    def spawn(self, cmd, limit):
        """끝나지 않는 명령(iperf3 서버, tcpdump 등)을 백그라운드로 띄운다.

        limit 초가 지나면 장비 쪽에서 스스로 끝나게 timeout 으로 감싼다. ssh 를 끊어도
        원격 프로세스가 남지 않게 하려는 것이다. 돌려받은 Proc 은 반드시 stop() 한다.
        장비 쪽 PID 를 먼저 알려 받아 두었다가, 일찍 끌 때는 장비 안에서 신호를 보낸다
        (ssh 에서는 이 PC 의 ssh 를 끊어도 원격 tcpdump 가 통계를 내지 않는다).
        """
        cmd = f"exec timeout {int(limit)} {cmd}"
        if self.recorder:
            self.recorder.note(f"[{self.name}] spawn: {cmd}")
        p = subprocess.Popen(self._argv(f'echo "{PID_MARK}$$" >&2; {cmd}'), stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, start_new_session=True)
        return Proc(self, cmd, p)

    def home(self):
        # 파일은 로그인 사용자(scp)로 올리므로 홈도 sudo 없이 묻는다. sudo 로 물으면 /root 가 나온다.
        if self._home is None:
            self._home = self.run("echo $HOME", check=True, sudo=False).out.strip()
        return self._home

    def put(self, local):
        """도우미 스크립트를 장비에 올리고 장비 쪽 절대 경로를 돌려준다.

        netns·local 은 파일 시스템을 공유하므로 저장소 안의 파일을 그대로 쓴다.
        ssh 는 다른 사용자가 끼어들 수 없는 홈 디렉터리 아래로 복사한다(/tmp 를 쓰지 않는다).
        """
        local = Path(local).resolve()
        if self.transport != "ssh":
            return str(local)
        remote_dir = f"{self.home()}/.pitest"
        self.run(f"mkdir -p {q(remote_dir)} && chmod 700 {q(remote_dir)}", check=True, sudo=False)
        remote = f"{remote_dir}/{local.name}"
        subprocess.run(["scp", "-q", *SSH_OPTS, str(local), f"{self.target}:{remote}"], check=True, timeout=60)
        return remote


class Proc:
    """spawn() 으로 띄운 프로세스. stop() 은 몇 번 불러도 된다."""

    def __init__(self, host, cmd, popen):
        self.host, self.cmd, self.p = host, cmd, popen
        self.out = self.err = None
        self._pre = {"out": "", "err": ""}
        self.pid = None
        try:
            if self.wait_ready(PID_MARK, timeout=10):
                line = self._pre["err"].splitlines()[-1]
                self._pre["err"] = self._pre["err"][: -len(line) - 1]
                self.pid = int(line[len(PID_MARK):])
        except BaseException:
            # 아직 복구 목록에 오르기 전이다. 여기서 끊기면 직접 끈다
            # (ssh 라면 원격 쪽은 spawn 의 timeout 이 limit 초 뒤에 끝낸다)
            _kill(self.p)
            raise

    def wait_ready(self, marker, timeout=10, stream="err"):
        """stream(err/out)에 marker 가 나올 때까지 기다린다 (tcpdump 의 'listening on' 등)."""
        f = self.p.stderr if stream == "err" else self.p.stdout
        os.set_blocking(f.fileno(), False)
        deadline = time.time() + timeout
        try:
            while time.time() < deadline:
                line = f.readline()
                if line:
                    self._pre[stream] += line
                    if marker in line:
                        return True
                elif self.p.poll() is not None:
                    return False
                else:
                    time.sleep(0.05)
            return False
        finally:
            os.set_blocking(f.fileno(), True)

    def finish(self, grace=1.0):
        """관찰이 끝났으면 grace 초만 더 받고 끈다. limit 까지 다 기다리지 않는다.
        돌려주는 alive 가 False 면 관찰이 끝나기 전에 프로세스가 먼저 끝난 것이다."""
        alive = self.out is None and self.p.poll() is None
        if alive:
            time.sleep(grace)
            alive = self.p.poll() is None
            self._signal()
        out, err = self.stop()
        return out, err, alive

    def _signal(self):
        """장비 안에서 TERM 을 보낸다. timeout 이 받아 tcpdump 에 넘기고, tcpdump 는 통계를 찍고 끝난다.
        PID 를 모르거나 신호를 못 보냈으면 이 PC 쪽 프로세스 그룹을 끈다."""
        # 신호를 보낸 뒤 기다리며 출력을 받는 일은 stop() 의 communicate() 가 한다
        if not (self.pid and self.host.run(f"kill -TERM {self.pid}", timeout=10).ok):
            _kill(self.p)

    def stop(self, timeout=15):
        """끝나기를 기다렸다가, 안 끝나면 프로세스 그룹째 끈다. (out, err) 를 돌려준다."""
        if self.out is not None:
            return self.out, self.err
        try:
            out, err = self.p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill(self.p)
            out, err = self.p.communicate()
        self.out, self.err = self._pre["out"] + out, self._pre["err"] + err
        if self.host.recorder:
            self.host.recorder.note(f"[{self.host.name}] stopped rc={self.p.returncode}: {self.cmd}")
            for label, text in (("out", self.out), ("err", self.err)):
                for line in text.rstrip().splitlines()[-50:]:
                    self.host.recorder.note(f"    {label}| {line}")
        return self.out, self.err


def _kill(p):
    try:
        os.killpg(p.pid, signal.SIGTERM)
        p.wait(timeout=3)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


class CommandFailed(Exception):
    def __init__(self, host, res):
        super().__init__(f"{host}: '{res.cmd}' rc={res.rc}{' (timeout)' if res.timed_out else ''}\n{res.err.strip()}")
        self.res = res


@dataclass
class Lab:
    name: str
    hosts: dict
    expect: dict
    dut_version_cmd: str
    tester: str
    console_cmd: str = ""
    path: Path = None

    def __getitem__(self, name):
        return self.hosts[name]

    def spec(self):
        """재개(--resume)할 때 같은 랩인지 대조하는 값."""
        return {"name": self.name, "expect": self.expect,
                "hosts": {n: [h.transport, h.target, h.vars] for n, h in self.hosts.items()}}


def load_lab(path):
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    hosts = {
        name: Host(name, h["transport"], h.get("target", ""), h.get("sudo", False), h.get("vars", {}))
        for name, h in data["hosts"].items()
    }
    return Lab(
        name=data["name"],
        hosts=hosts,
        expect=data.get("expect", {}),
        dut_version_cmd=data.get("dut_version_cmd", "uname -r"),
        tester=data.get("tester", ""),
        console_cmd=data.get("console_cmd", ""),
        path=path,
    )


@contextmanager
def lab_lock(lab, lock_dir=None):
    """같은 랩을 두 실행이 동시에 쓰지 못하게 제어 PC 에서 잠근다.

    잠금 파일은 실행하는 사용자만 쓰는 디렉터리에 둔다. 누구나 쓰는 /tmp 에 고정 이름으로
    만들면, 다른 사용자가 미리 심어 둔 링크를 root 로 열어 엉뚱한 파일을 망칠 수 있다.
    """
    lock_dir = Path(lock_dir or Path.home() / ".cache" / "pitest")
    lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if lock_dir.is_symlink() or lock_dir.stat().st_uid != os.getuid():
        raise SystemExit(f"잠금 디렉터리를 믿을 수 없습니다: {lock_dir}")
    name = "".join(c if c.isalnum() or c in "-_." else "_" for c in lab.name)
    path = lock_dir / f"{name}.lock"
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)  # 열 때 내용을 지우지 않는다
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise SystemExit(f"다른 실행이 {lab.name} 랩을 쓰는 중입니다 ({path})")
    try:
        os.ftruncate(fd, 0)  # 잠금을 얻은 뒤에만 PID 를 쓴다
        os.write(fd, str(os.getpid()).encode())
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
