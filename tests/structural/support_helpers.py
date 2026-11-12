"""Qualification isolation, shared fixtures; no production credential loading."""
import errno
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import pytest

PROBE = '''import errno, fcntl, socket, struct
names = [line.split(':')[0].strip() for line in open('/proc/self/net/dev') if ':' in line]
assert names == ['lo'], 'run under unshare -rn'
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
flags = struct.unpack('16sH14x', fcntl.ioctl(s, 0x8913, struct.pack('16sH14x', b'lo', 0)))[1]
assert not flags & 1, 'run under unshare -rn'
for kind, addr in [(socket.SOCK_STREAM, ('127.0.0.1', 9)), (socket.SOCK_DGRAM, ('192.0.2.1', 9))]:
 s = socket.socket(socket.AF_INET, kind)
 try: s.connect(addr)
 except OSError as e: assert e.errno == errno.ENETUNREACH
 else: raise AssertionError('run under unshare -rn')
'''

@pytest.fixture(scope="session")
def require_netns():
    child = subprocess.run([sys.executable, "-I", "-c", PROBE], capture_output=True)
    assert child.returncode == 0, "run under unshare -rn"

class SocketForbidden(RuntimeError):
    pass

def forbid(*args, **kwargs):
    raise SocketForbidden("socket forbidden in qualification")

@pytest.fixture
def isolation(monkeypatch, tmp_path):
    from clavain_selector import credentials
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CLAVAIN_STATE_DIR", str(tmp_path / "state"))
    for name in ("socket", "create_connection", "getaddrinfo", "socketpair"):
        monkeypatch.setattr(socket, name, forbid)
    import _socket
    monkeypatch.setattr(_socket, "socket", forbid)
    monkeypatch.setattr(credentials, "load", lambda **kw: credentials.SecretStr("dummy-qualification-value"))

@pytest.fixture
def request_packet(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], env=env).decode().strip()
    git("init", "-q")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.invalid")
    git("remote", "add", "origin", "https://github.com/mistakeknot/support-fixture.git")
    (root / "source.md").write_text("First line.\nSecond line.\n")
    git("add", "source.md")
    git("commit", "-qm", "Fixture")
    digest = lambda text: hashlib.sha256(text.encode()).hexdigest()
    return {"schema": "clavain.selector.support_request", "schema_version": 1, "run_id": "fixture_run", "case_id": "fixture_case", "claim": {"text": "First line.", "sha256": digest("First line.")}, "project_root": str(root), "revision": git("rev-parse", "HEAD"), "sections": [{"path": "source.md", "start_line": 1, "end_line": 1, "text": "First line.\n", "sha256": digest("First line.\n")}], "label_descriptions": {"supported": "Direct support.", "not_supported": "Direct contradiction.", "unclear": "Insufficient evidence."}, "abstain_below": .7, "deadline_ms": 5000}
