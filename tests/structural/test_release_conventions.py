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


def test_all_capabilities_default_off(project_root):
    caps = json.loads((project_root / "config/capability-state.json").read_text())["capabilities"]
    assert caps and all(c["state"] == "off" for c in caps)


def test_drift_fails(project_root, tmp_path):
    doc = (project_root / "agents/development.md").read_text()
    drifted = doc.replace("Gradual rollout: off.", "Gradual rollout: on.")
    assert drifted != doc
    p = tmp_path / "d.md"
    p.write_text(drifted)
    r = cap(project_root, "--doc", str(p))
    assert r.returncode == 1 and "disagrees" in r.stderr


def test_source_flip_fails(project_root, tmp_path):
    src = json.loads((project_root / "config/capability-state.json").read_text())
    src["capabilities"][0]["state"] = "on"
    p = tmp_path / "s.json"
    p.write_text(json.dumps(src))
    assert cap(project_root, "--source", str(p)).returncode == 1


def test_missing_block_fails(project_root, tmp_path):
    p = tmp_path / "d.md"
    p.write_text("nothing here\n")
    assert cap(project_root, "--doc", str(p)).returncode == 1


def test_invalid_state_is_input_error(project_root, tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"capabilities": [{"label": "x", "state": "maybe"}]}))
    assert cap(project_root, "--source", str(p)).returncode == 2


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
