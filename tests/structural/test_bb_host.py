"""BB integration must fail closed outside explicitly enrolled machines."""
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def probe(tmp_path, monkeypatch, host="host_pda34naxgq", status=0, missing=None):
    cli = tmp_path / "bb"
    cli.write_text("#!/bin/sh\n" + (f"exit {status}\n" if status else
        "cat <<'EOF'\n" + json.dumps({"thread": {"id": "thr_test", "environment": {"hostId": host}}}) + "\nEOF\n"))
    cli.chmod(0o755)
    env = dict(os.environ, BB_CLI=str(cli), BB_THREAD_ID="thr_test", BB_SERVER_URL="https://bb.example")
    if missing:
        env.pop(missing)
    return subprocess.run(["python3", str(ROOT / "scripts/bb-host.py")], env=env, capture_output=True)


def test_allowed_machine(tmp_path, monkeypatch):
    assert probe(tmp_path, monkeypatch).returncode == 0


def test_mac_with_bb_environment(tmp_path, monkeypatch):
    assert probe(tmp_path, monkeypatch, host="host_mac").returncode == 1


def test_failed_status(tmp_path, monkeypatch):
    assert probe(tmp_path, monkeypatch, status=1).returncode == 1


def test_required_environment(tmp_path, monkeypatch):
    for name in ("BB_THREAD_ID", "BB_SERVER_URL"):
        assert probe(tmp_path, monkeypatch, missing=name).returncode == 1
