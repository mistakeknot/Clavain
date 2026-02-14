"""PRD and README freshness tests — verify docs stay in sync with reality."""

import json
import re
from pathlib import Path


def test_prd_version_matches_plugin_json(project_root):
    """PRD version header must match plugin.json version."""
    prd = (project_root / "docs" / "PRD.md").read_text()
    plugin = json.loads((project_root / ".claude-plugin" / "plugin.json").read_text())

    match = re.search(r"\*\*Version:\*\*\s*(\S+)", prd)
    assert match, "PRD.md missing **Version:** header"
    assert match.group(1) == plugin["version"], (
        f"PRD version ({match.group(1)}) != plugin.json version ({plugin['version']}). "
        "Update the **Version:** line in docs/PRD.md."
    )


def _extract_table_count(text, label):
    """Extract count from markdown table row like | **Label** | 27 | ..."""
    match = re.search(rf"\*\*{label}\*\*\s*\|\s*(\d+)", text)
    return int(match.group(1)) if match else None


def _extract_section_count(text, label):
    """Extract count from section header like ### Label (27)."""
    match = re.search(rf"###\s+{label}\s+\((\d+)\)", text)
    return int(match.group(1)) if match else None


def _extract_intro_counts(text):
    """Extract counts from README intro line like 'With 27 skills, 5 agents, 36 commands'."""
    skills = re.search(r"(\d+)\s+skills", text)
    agents = re.search(r"(\d+)\s+agents", text)
    commands = re.search(r"(\d+)\s+commands", text)
    return (
        int(skills.group(1)) if skills else None,
        int(agents.group(1)) if agents else None,
        int(commands.group(1)) if commands else None,
    )


def test_prd_component_counts(
    project_root, all_skill_dirs, all_agent_files, all_command_files
):
    """Section 4.1 component counts must match filesystem."""
    prd = (project_root / "docs" / "PRD.md").read_text()

    actual_skills = len(all_skill_dirs)
    actual_agents = len(all_agent_files)
    actual_commands = len(all_command_files)

    prd_skills = _extract_table_count(prd, "Skills")
    prd_agents = _extract_table_count(prd, "Agents")
    prd_commands = _extract_table_count(prd, "Commands")

    assert prd_skills is not None, "PRD.md missing Skills count in Section 4.1"
    assert prd_agents is not None, "PRD.md missing Agents count in Section 4.1"
    assert prd_commands is not None, "PRD.md missing Commands count in Section 4.1"

    assert prd_skills == actual_skills, (
        f"PRD says {prd_skills} skills, filesystem has {actual_skills}. "
        "Update Section 4.1 in docs/PRD.md."
    )
    assert prd_agents == actual_agents, (
        f"PRD says {prd_agents} agents, filesystem has {actual_agents}. "
        "Update Section 4.1 in docs/PRD.md."
    )
    assert prd_commands == actual_commands, (
        f"PRD says {prd_commands} commands, filesystem has {actual_commands}. "
        "Update Section 4.1 in docs/PRD.md."
    )


def test_readme_component_counts(
    project_root, all_skill_dirs, all_agent_files, all_command_files
):
    """README intro line and section headers must match filesystem."""
    readme = (project_root / "README.md").read_text()

    actual_skills = len(all_skill_dirs)
    actual_agents = len(all_agent_files)
    actual_commands = len(all_command_files)

    # Check intro line counts
    intro_skills, intro_agents, intro_commands = _extract_intro_counts(readme)
    assert intro_skills is not None, "README.md missing skills count in intro"
    assert intro_skills == actual_skills, (
        f"README intro says {intro_skills} skills, filesystem has {actual_skills}."
    )
    assert intro_agents == actual_agents, (
        f"README intro says {intro_agents} agents, filesystem has {actual_agents}."
    )
    assert intro_commands == actual_commands, (
        f"README intro says {intro_commands} commands, filesystem has {actual_commands}."
    )

    # Check section header counts
    section_skills = _extract_section_count(readme, "Skills")
    section_agents = _extract_section_count(readme, "Agents")
    section_commands = _extract_section_count(readme, "Commands")

    assert section_skills == actual_skills, (
        f"README '### Skills' says {section_skills}, filesystem has {actual_skills}."
    )
    assert section_agents == actual_agents, (
        f"README '### Agents' says {section_agents}, filesystem has {actual_agents}."
    )
    assert section_commands == actual_commands, (
        f"README '### Commands' says {section_commands}, filesystem has {actual_commands}."
    )
