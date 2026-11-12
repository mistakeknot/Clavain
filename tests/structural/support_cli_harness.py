"""Isolated test-only CLI host. Never packaged with the adapter."""
import argparse
import http.client
import ssl
import importlib.util
import json
from pathlib import Path
import socket
import _socket
import sys
import time

class SocketForbidden(RuntimeError):
    pass

def forbid(*args, **kwargs):
    raise SocketForbidden("qualification socket guard")

for name in ("socket", "create_connection", "socketpair", "getaddrinfo"):
    setattr(socket, name, forbid)
_socket.socket = forbid

parser = argparse.ArgumentParser()
parser.add_argument("--replies", required=True)
parser.add_argument("args", nargs=argparse.REMAINDER)
args = parser.parse_args()
steps = iter(json.loads(Path(args.replies).read_text()))
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "scripts"))
from clavain_selector import credentials, jev_client

def transport(body, timeout, progress):
    step = next(steps)
    if step.get("probe") == "socket":
        for call in (lambda: socket.create_connection(("127.0.0.1", 9)), lambda: _socket.socket()):
            try: call()
            except SocketForbidden: pass
            else: raise AssertionError("socket guard missing")
    for phase in ("connect", "request_sent", "response_read"):
        progress(phase)
        if step.get("fail_at") == phase: raise OSError("dummy transport failure")
    time.sleep(step.get("delay_ms", 0) / 1000)
    return jev_client.RawReply(step["status"], step.get("headers", {}), step.get("body", "").encode())

credentials.load = lambda **kwargs: credentials.SecretStr("dummy-qualification-value")
spec = importlib.util.spec_from_file_location("support_cli", root / "scripts/clavain-select.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
raise SystemExit(cli.main(args.args[1:] if args.args[:1] == ["--"] else args.args,
                          _transport=transport, _credential_loader=credentials.load))
