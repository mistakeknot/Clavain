"""Regression: hooks/auto-publish.sh surfaces ic publish failures instead of
dying silently (Sylveste-dc9).

The 2026-07-19 incident: the marketplace clone had a dirty tracked interspect
DB, `ic publish --auto` failed on pull --rebase (exit 128), and the hook's
if/elif chain — which matches only happy patterns like "Published"/"Synced" —
fell through every branch and emitted nothing. Publishes silently didn't
happen. The fix adds a failure branch keyed on ic's exit code / error output
that emits a systemMessage.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

HOOK = "hooks/auto-publish.sh"


@pytest.fixture()
def plugin_repo(tmp_path: Path) -> Path:
    """A minimal plugin git repo on main with one commit (the hook requires
    a resolvable branch and .claude-plugin/plugin.json)."""
    repo = tmp_path / "plug"
    (repo / ".claude-plugin").mkdir(parents=True)
    (repo / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "testplug", "version": "0.0.1"})
    )
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True, env=env)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "init"],
                   cwd=repo, check=True, env=env)
    return repo


def _run_hook(project_root: Path, plugin_repo: Path, ic_script: str, tmp_path: Path) -> str:
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    ic = bindir / "ic"
    ic.write_text(ic_script)
    ic.chmod(0o755)

    payload = json.dumps({
        "tool_input": {"command": "git push origin main"},
        "cwd": str(plugin_repo),
        "tool_result": {"exit_code": "0"},
    })
    result = subprocess.run(
        ["bash", str(project_root / HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        # Real PATH after the stub dir: the hook needs jq and git; the stub ic
        # must win. gh lookups are safe — the temp repo has no remote.
        env={**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}"},
        timeout=30,
    )
    assert result.returncode == 0, f"hook must stay fail-open (exit 0); stderr: {result.stderr}"
    return result.stdout


def test_ic_failure_emits_system_message(project_root, plugin_repo, tmp_path):
    # The dc9 incident shape: ic exits 1 with a pull --rebase error.
    stdout = _run_hook(
        project_root, plugin_repo,
        "#!/bin/sh\n"
        "echo 'Error: pull --rebase (marketplace): exit status 128'\n"
        "exit 1\n",
        tmp_path,
    )
    assert stdout.strip(), "hook emitted nothing on ic failure (the dc9 silence)"
    out = json.loads(stdout)
    assert "AUTO-PUBLISH FAILED" in out.get("systemMessage", ""), out
    assert "pull --rebase" in out["systemMessage"], out


def test_successful_publish_does_not_trip_failure_branch(project_root, plugin_repo, tmp_path):
    stdout = _run_hook(
        project_root, plugin_repo,
        "#!/bin/sh\n"
        "echo 'Published testplug v0.0.2'\n"
        "exit 0\n",
        tmp_path,
    )
    out = json.loads(stdout)
    assert "Published" in out.get("additionalContext", ""), out
    assert "systemMessage" not in out, f"success must not raise the failure banner: {out}"
