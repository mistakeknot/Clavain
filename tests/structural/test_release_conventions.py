"""Capability-state drift check and version-endpoint check (bead mk-xxem2)."""
import json
import subprocess
import sys

import pytest

CAP = "scripts/check-capability-state.py"
VER = "scripts/check-version-endpoint.sh"


def cap(project_root, *args):
    return subprocess.run([sys.executable, "-I", str(project_root / CAP), *args],
                          capture_output=True, text=True, timeout=30)


def test_repo_block_agrees_with_source(project_root):
    assert cap(project_root).returncode == 0


# Capabilities deliberately switched on. Add an id here in the same change that flips it.
ALLOWED_ON = set()


def load_source(project_root):
    return json.loads((project_root / "config/capability-state.json").read_text())


def test_capabilities_default_off_unless_allowed(project_root):
    caps = load_source(project_root)["capabilities"]
    assert caps and all(c["state"] == "off" for c in caps if c["id"] not in ALLOWED_ON)


def test_drift_fails(project_root, tmp_path):
    c = load_source(project_root)["capabilities"][0]
    flipped = "off" if c["state"] == "on" else "on"
    doc = (project_root / "agents/development.md").read_text()
    drifted = doc.replace(f"- {c['label']}: {c['state']}.", f"- {c['label']}: {flipped}.")
    assert drifted != doc
    p = tmp_path / "d.md"
    p.write_text(drifted)
    r = cap(project_root, "--doc", str(p))
    assert r.returncode == 1 and "disagrees" in r.stderr


def test_source_flip_fails(project_root, tmp_path):
    src = load_source(project_root)
    c = src["capabilities"][0]
    c["state"] = "off" if c["state"] == "on" else "on"
    p = tmp_path / "s.json"
    p.write_text(json.dumps(src))
    assert cap(project_root, "--source", str(p)).returncode == 1


def test_missing_block_fails(project_root, tmp_path):
    p = tmp_path / "d.md"
    p.write_text("nothing here\n")
    assert cap(project_root, "--doc", str(p)).returncode == 1


@pytest.mark.parametrize("payload", [
    {"capabilities": [{"label": "x", "state": "maybe"}]},
    {"capabilities": [None]},
    {"capabilities": ["off"]},
    {"capabilities": {"a": 1}},
    {"capabilities": [{"state": "off"}]},
])
def test_invalid_state_is_input_error(project_root, tmp_path, payload):
    p = tmp_path / "s.json"
    p.write_text(json.dumps(payload))
    r = cap(project_root, "--source", str(p))
    assert r.returncode == 2
    assert "invalid state in source" in r.stderr or "unreadable input" in r.stderr
    assert "Traceback" not in r.stderr and "can't open file" not in r.stderr


@pytest.fixture
def fetcher(tmp_path):
    def make(body, fail=False):
        f = tmp_path / "fetch.sh"
        f.write_text("#!/bin/sh\n" + ("exit 22\n" if fail else f"printf '%s' '{body}'\n"))
        f.chmod(0o755)
        return {"CHECK_VERSION_FETCH_CMD": str(f), "PATH": "/usr/bin:/bin"}
    return make


def ver(project_root, env, *args):
    return subprocess.run(["bash", str(project_root / VER), "https://x.example", "proj", *args],
                          capture_output=True, text=True, env=env, timeout=30)


def test_endpoint_match_and_prefix(project_root, fetcher):
    env = fetcher('{"version":"1.2.3","commit":"abcdef1234567"}')
    assert ver(project_root, env, "abcdef1234567890", "1.2.3").returncode == 0
    assert ver(project_root, env, "abcdef1").returncode == 0


def test_endpoint_mismatch(project_root, fetcher):
    env = fetcher('{"version":"1.2.3","commit":"abcdef1234567"}')
    assert ver(project_root, env, "9999999").returncode == 1
    assert ver(project_root, env, "abcdef1", "9.9.9").returncode == 1


def test_endpoint_bad_payload_and_fetch_failure(project_root, fetcher):
    assert ver(project_root, fetcher('{"version":"1"}'), "abcdef1").returncode == 1
    assert ver(project_root, fetcher("", fail=True), "abcdef1").returncode == 2
    assert ver(project_root, fetcher('{"version":"1","commit":"ab"}'), "ab").returncode == 1


@pytest.mark.parametrize("body", [
    '{"version":null,"commit":"abcdef1234567"}',
    '{"version":{},"commit":1234567}',
    '{"version":"1","commit":1234567}',
    '{"version":"1","commit":"not-hex-commit"}',
    '{"version":["1"],"commit":"abcdef1234567"}',
])
def test_endpoint_rejects_non_string_or_malformed_fields(project_root, fetcher, body):
    r = ver(project_root, fetcher(body), "abcdef1")
    assert r.returncode == 1 and "payload lacks" in r.stderr
