"""Tests for cross-references between plugin components."""

import re
from pathlib import Path


def test_hooks_json_scripts_exist(hooks_json, project_root):
    """Every .sh referenced in hooks.json exists on disk."""
    for event_type, hook_groups in hooks_json["hooks"].items():
        for group in hook_groups:
            for hook in group.get("hooks", []):
                command = hook.get("command", "")
                # Extract path, stripping bash prefix and quotes
                path_str = command
                path_str = path_str.replace('bash ', '').strip()
                path_str = path_str.strip('"').strip("'")
                path_str = path_str.replace("${CLAUDE_PLUGIN_ROOT}/", "")
                resolved = project_root / path_str
                assert resolved.exists(), (
                    f"Hook script not found: {command} -> {resolved}"
                )


def test_lib_sourced_by_hooks(project_root):
    """Hooks that source lib.sh — lib.sh must exist."""
    hooks_dir = project_root / "hooks"
    lib_path = hooks_dir / "lib.sh"
    assert lib_path.exists(), "hooks/lib.sh does not exist"

    # Verify hooks that source lib.sh reference an existing file
    for sh_file in hooks_dir.glob("*.sh"):
        if sh_file.name == "lib.sh":
            continue
        text = sh_file.read_text(encoding="utf-8")
        if "source" in text and "lib.sh" in text:
            assert lib_path.exists(), (
                f"{sh_file.name} sources lib.sh but it doesn't exist"
            )


def test_routing_table_references(project_root):
    """Parse using-clavain/SKILL.md for clavain: refs, verify each resolves."""
    skill_md = project_root / "skills" / "using-clavain" / "SKILL.md"
    assert skill_md.exists(), "using-clavain/SKILL.md not found"

    text = skill_md.read_text(encoding="utf-8")

    # Find all clavain: references (e.g., /clavain:write-plan, clavain:flux-drive)
    refs = re.findall(r"clavain:([a-z0-9][-a-z0-9]*)", text)
    assert len(refs) > 0, "No clavain: references found in using-clavain/SKILL.md"

    skills_dir = project_root / "skills"
    commands_dir = project_root / "commands"

    unresolved = []
    for ref in set(refs):
        # A clavain: reference can resolve to a skill directory or command file
        skill_exists = (skills_dir / ref / "SKILL.md").exists()
        command_exists = (commands_dir / f"{ref}.md").exists()
        if not skill_exists and not command_exists:
            unresolved.append(ref)

    assert not unresolved, (
        f"Unresolved clavain: references in using-clavain/SKILL.md: {sorted(unresolved)}"
    )
