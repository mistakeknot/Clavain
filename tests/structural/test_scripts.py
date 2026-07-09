"""Tests for shell and Python script validity."""

import subprocess
from pathlib import Path

import pytest


def _get_shell_scripts():
    """Get all .sh files in scripts/ and hooks/."""
    root = Path(__file__).resolve().parent.parent.parent
    files = []
    for subdir in ("scripts", "hooks"):
        d = root / subdir
        if d.is_dir():
            files.extend(sorted(d.glob("*.sh")))
    return files


def _get_python_scripts():
    """Get all .py files in scripts/."""
    root = Path(__file__).resolve().parent.parent.parent
    scripts_dir = root / "scripts"
    if scripts_dir.is_dir():
        return sorted(scripts_dir.glob("*.py"))
    return []


def _get_hook_entry_points():
    """Get hook entry-point .sh files (those referenced in hooks.json), excluding lib.sh."""
    import json
    root = Path(__file__).resolve().parent.parent.parent
    hooks_json_path = root / "hooks" / "hooks.json"
    with open(hooks_json_path) as f:
        data = json.load(f)

    entry_points = set()
    for event_type, hook_groups in data["hooks"].items():
        for group in hook_groups:
            for hook in group.get("hooks", []):
                command = hook.get("command", "")
                path_str = command.replace('bash ', '').strip().strip('"').strip("'")
                path_str = path_str.replace("${CLAUDE_PLUGIN_ROOT}/", "")
                resolved = root / path_str
                if resolved.exists() and resolved.suffix == ".sh":
                    entry_points.add(resolved)

    return sorted(entry_points)


SHELL_SCRIPTS = _get_shell_scripts()
PYTHON_SCRIPTS = _get_python_scripts()
HOOK_ENTRY_POINTS = _get_hook_entry_points()


@pytest.mark.parametrize("script", SHELL_SCRIPTS, ids=lambda p: p.name)
def test_shell_scripts_syntax(script):
    """All .sh files pass bash -n syntax check."""
    result = subprocess.run(
        ["bash", "-n", str(script)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, (
        f"Syntax error in {script.name}: {result.stderr}"
    )


@pytest.mark.parametrize("script", PYTHON_SCRIPTS, ids=lambda p: p.name)
def test_python_scripts_syntax(script):
    """All .py files pass python3 -m py_compile check."""
    result = subprocess.run(
        ["python3", "-m", "py_compile", str(script)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, (
        f"Syntax error in {script.name}: {result.stderr}"
    )


@pytest.mark.parametrize("script", SHELL_SCRIPTS, ids=lambda p: p.name)
def test_scripts_have_shebang(script):
    """All .sh files start with a shebang line."""
    first_line = script.read_text(encoding="utf-8").split("\n", 1)[0]
    assert first_line.startswith("#!/"), (
        f"{script.name} is missing a shebang line (starts with: {first_line!r})"
    )


# Hooks that deliberately fail open (trap ERR -> exit 0) instead of using
# 'set -euo pipefail', so an internal error never blocks/noises the user's
# session. See 6d40e83 "fix(hooks): fail-open on errors to prevent PostToolUse
# noise after updates".
FAIL_OPEN_HOOKS = {
    "agents-md-refresh.sh",
    "auto-publish.sh",
    "auto-push.sh",
    "auto-stop-actions.sh",
    "bead-agent-bind.sh",
    "catalog-reminder.sh",
    "dotfiles-sync.sh",
    "guard-plugin-cache.sh",
    "peer-routing-telemetry.sh",
    "session-start.sh",
    "validate-plugin-edit.sh",
}

# gate-calibration-session-end.sh fails open by a different mechanism: bare
# `set -u` with every command wrapped in `|| true` and a hard `exit 0` at the
# end, rather than `trap ERR -> exit 0`. Same intent, different idiom.
FAIL_OPEN_HOOKS_NO_TRAP = {"gate-calibration-session-end.sh"}


def test_hook_entry_points_have_set_euo_pipefail():
    """Hook entry-point .sh files contain 'set -euo pipefail', except lib.sh and
    deliberately fail-open hooks (FAIL_OPEN_HOOKS), which use trap ERR -> exit 0
    instead so an internal error never blocks the user's session."""
    for script in HOOK_ENTRY_POINTS:
        if (
            script.name == "lib.sh"
            or script.name in FAIL_OPEN_HOOKS
            or script.name in FAIL_OPEN_HOOKS_NO_TRAP
        ):
            continue
        text = script.read_text(encoding="utf-8")
        assert "set -euo pipefail" in text, (
            f"Hook entry point {script.name} is missing 'set -euo pipefail'"
        )


def test_fail_open_hooks_use_trap_err_exit_zero():
    """Fail-open hooks use trap ERR -> exit 0 instead of set -e, so they never
    block the user's session on an internal error."""
    for script in HOOK_ENTRY_POINTS:
        if script.name not in FAIL_OPEN_HOOKS:
            continue
        text = script.read_text(encoding="utf-8")
        assert "set -uo pipefail" in text, (
            f"Fail-open hook {script.name} must use 'set -uo pipefail' (no -e)"
        )
        assert "trap" in text and "ERR" in text, (
            f"Fail-open hook {script.name} must trap ERR to exit 0"
        )
