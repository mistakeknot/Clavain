"""Stubbed harness for hooks/release-canary-check.sh (sylveste-ao0q).

The hook verifies pending release canaries against the session's plugin
resolution surface (installed_plugins.json installPath + parseable
plugin.json). Passed → record marked passed, silent. Failed → record marked
failed + loud systemMessage carrying the ready-to-run rollback command.
"""

import json
import os
import subprocess
from pathlib import Path

HOOK = "hooks/release-canary-check.sh"


def _run(project_root: Path, canary_file: Path, installed_file: Path) -> str:
    result = subprocess.run(
        ["bash", str(project_root / HOOK)],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "CLAVAIN_CANARY_FILE": str(canary_file),
            "CLAVAIN_INSTALLED_FILE": str(installed_file),
        },
        timeout=30,
    )
    assert result.returncode == 0, f"hook must stay fail-open; stderr: {result.stderr}"
    return result.stdout


def _fixtures(tmp_path: Path, *, healthy: bool):
    """A pending canary for testplug v1.1.0; installed state healthy or broken."""
    install_dir = tmp_path / "cache" / "testplug" / "1.1.0"
    if healthy:
        (install_dir / ".claude-plugin").mkdir(parents=True)
        (install_dir / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "testplug", "version": "1.1.0"})
        )
    # If not healthy the installPath simply does not exist — the 0lt shape.

    canary_file = tmp_path / "release-canaries.json"
    canary_file.write_text(json.dumps([{
        "plugin": "testplug",
        "marketplace": "interagency-marketplace",
        "version": "1.1.0",
        "prior_version": "1.0.0",
        "published_at": 1784600000,
        "status": "pending",
    }]))

    installed_file = tmp_path / "installed_plugins.json"
    installed_file.write_text(json.dumps({
        "version": 2,
        "plugins": {
            "testplug@interagency-marketplace": [{
                "scope": "user",
                "installPath": str(install_dir),
                "version": "1.1.0",
            }]
        },
    }))
    return canary_file, installed_file


def test_loaded_plugin_marks_canary_passed(project_root, tmp_path):
    canary_file, installed_file = _fixtures(tmp_path, healthy=True)
    stdout = _run(project_root, canary_file, installed_file)

    records = json.loads(canary_file.read_text())
    assert records[0]["status"] == "passed", records
    assert records[0]["checked_at"] > 0, records
    assert stdout.strip() == "", f"passed canary must stay silent: {stdout!r}"


def test_missing_plugin_alerts_with_rollback_command(project_root, tmp_path):
    canary_file, installed_file = _fixtures(tmp_path, healthy=False)
    stdout = _run(project_root, canary_file, installed_file)

    records = json.loads(canary_file.read_text())
    assert records[0]["status"] == "failed", records

    assert stdout.strip(), "failed canary must alert loudly"
    out = json.loads(stdout)
    msg = out.get("systemMessage", "")
    assert "RELEASE CANARY FAILED" in msg, out
    assert "ic publish rollback testplug" in msg, out
    assert out["hookSpecificOutput"]["additionalContext"], out
