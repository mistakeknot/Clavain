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


def test_hook_entry_points_have_set_euo_pipefail():
    """Hook entry-point .sh files contain 'set -euo pipefail'. Excludes lib.sh."""
    for script in HOOK_ENTRY_POINTS:
        if script.name == "lib.sh":
            continue
        text = script.read_text(encoding="utf-8")
        assert "set -euo pipefail" in text, (
            f"Hook entry point {script.name} is missing 'set -euo pipefail'"
        )
