#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "docs" / "catalog.json"
TARGET_FILES = (
    ROOT / ".claude-plugin" / "plugin.json",
    ROOT / "AGENTS.md",
    ROOT / "CLAUDE.md",
    ROOT / "README.md",
    ROOT / "skills" / "using-clavain" / "SKILL.md",
    ROOT / "agent-rig.json",
)


def utc_now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def unquote_scalar(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        quote = value[0]
        inner = value[1:-1]
        if quote == '"':
            return inner.replace(r"\\", "\\").replace(r'\"', '"')
        return inner.replace("''", "'")
    return value


def parse_frontmatter(path: Path) -> dict[str, str]:
    lines = read_text(path).splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"Missing YAML frontmatter start marker in {path}")

    frontmatter: dict[str, str] = {}
    index = 1
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped == "---":
            return frontmatter

        if not stripped or stripped.startswith("#"):
            index += 1
            continue

        if ":" not in line:
            index += 1
            continue

        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()

        if value in {"|", ">", "|-", "|+", ">-", ">+"}:
            block_lines: list[str] = []
            index += 1
            while index < len(lines):
                block_line = lines[index]
                if block_line.strip() == "---":
                    break
                if block_line.startswith((" ", "\t")):
                    block_lines.append(block_line.lstrip(" \t"))
                    index += 1
                    continue
                break
            frontmatter[key] = "\n".join(block_lines).strip()
            continue

        frontmatter[key] = unquote_scalar(value)
        index += 1

    raise ValueError(f"Missing YAML frontmatter end marker in {path}")


def require_field(frontmatter: dict[str, str], field: str, path: Path) -> str:
    value = frontmatter.get(field, "").strip()
    if not value:
        raise ValueError(f"Missing or empty frontmatter field '{field}' in {path}")
    return value


def collect_skills(root: Path) -> tuple[list[dict[str, str]], int]:
    skill_files = sorted((root / "skills").glob("*/SKILL.md"))
    skills: list[dict[str, str]] = []
    for path in skill_files:
        frontmatter = parse_frontmatter(path)
        skills.append(
            {
                "name": require_field(frontmatter, "name", path),
                "description": require_field(frontmatter, "description", path),
            }
        )
    skills.sort(key=lambda item: item["name"])
    return skills, len(skill_files)


def collect_agents(root: Path) -> tuple[list[dict[str, str]], int, dict[str, int]]:
    agents: list[dict[str, str]] = []
    count = 0
    category_counts: dict[str, int] = {}
    for category in ("review", "research", "workflow"):
        category_dir = root / "agents" / category
        if not category_dir.is_dir():
            continue
        cat_count = 0
        for path in sorted(category_dir.glob("*.md")):
            frontmatter = parse_frontmatter(path)
            agents.append(
                {
                    "name": require_field(frontmatter, "name", path),
                    "description": require_field(frontmatter, "description", path),
                    "category": category,
                }
            )
            count += 1
            cat_count += 1
        category_counts[category] = cat_count
    agents.sort(key=lambda item: (item["category"], item["name"]))
    return agents, count, category_counts


def collect_commands(root: Path) -> tuple[list[dict[str, str]], int]:
    command_files = sorted((root / "commands").glob("*.md"))
    commands: list[dict[str, str]] = []
    for path in command_files:
        frontmatter = parse_frontmatter(path)
        commands.append(
            {
                "name": require_field(frontmatter, "name", path),
                "description": require_field(frontmatter, "description", path),
            }
        )
    commands.sort(key=lambda item: item["name"])
    return commands, len(command_files)


def count_hook_entries(root: Path) -> int:
    payload = json.loads(read_text(root / "hooks" / "hooks.json"))
    hooks_by_event = payload.get("hooks")
    if not isinstance(hooks_by_event, dict):
        raise ValueError("hooks/hooks.json is missing top-level 'hooks' object")

    total = 0
    for event_name, groups in hooks_by_event.items():
        if not isinstance(groups, list):
            raise ValueError(f"hooks/hooks.json event {event_name!r} is not a list")
        for group in groups:
            if not isinstance(group, dict):
                raise ValueError(f"hooks/hooks.json event {event_name!r} has non-object group")
            hooks = group.get("hooks", [])
            if not isinstance(hooks, list):
                raise ValueError(f"hooks/hooks.json event {event_name!r} has non-list hooks")
            total += len(hooks)

    return total


def count_mcp_servers(root: Path) -> int:
    payload = json.loads(read_text(root / ".claude-plugin" / "plugin.json"))
    servers = payload.get("mcpServers", {})
    if isinstance(servers, dict):
        return len(servers)
    if isinstance(servers, list):
        return len(servers)
    raise ValueError(".claude-plugin/plugin.json has invalid 'mcpServers' shape")


def replace_once(text: str, pattern: str, replacement: str, path: Path) -> str:
    compiled = re.compile(pattern, re.MULTILINE)
    if not compiled.search(text):
        raise ValueError(f"Pattern not found in {path}: {pattern}")
    return compiled.sub(lambda _match: replacement, text, count=1)


def update_plugin_json_counts(text: str, counts: dict[str, int], path: Path) -> str:
    return replace_once(
        text,
        r"\d+ agents, \d+ commands, \d+ skills, \d+ MCP servers",
        f"{counts['agents']} agents, {counts['commands']} commands, {counts['skills']} skills, {counts['mcp_servers']} MCP servers",
        path,
    )


def update_agents_md_counts(text: str, counts: dict[str, int], path: Path) -> str:
    others = max(counts["commands"] - 2, 0)
    updated = replace_once(
        text,
        r"\d+ skills, \d+ agents, \d+ commands, \d+ hooks, \d+ MCP servers",
        f"{counts['skills']} skills, {counts['agents']} agents, {counts['commands']} commands, {counts['hooks']} hooks, {counts['mcp_servers']} MCP servers",
        path,
    )
    updated = replace_once(updated, r"# \d+ discipline skills", f"# {counts['skills']} discipline skills", path)
    updated = replace_once(updated, r"# \d+ slash commands", f"# {counts['commands']} slash commands", path)
    updated = replace_once(updated, r"\(\+ \d+ others\)", f"(+ {others} others)", path)
    updated = replace_once(
        updated,
        r'echo "Skills: \$\(ls skills/\*/SKILL\.md \| wc -l\)"\s+# Should be \d+',
        f'echo "Skills: $(ls skills/*/SKILL.md | wc -l)"      # Should be {counts["skills"]}',
        path,
    )
    updated = replace_once(
        updated,
        r'echo "Commands: \$\(ls commands/\*\.md \| wc -l\)"\s+# Should be \d+',
        f'echo "Commands: $(ls commands/*.md | wc -l)"        # Should be {counts["commands"]}',
        path,
    )
    for category in ("review", "research", "workflow"):
        if category in counts:
            updated = replace_once(updated, rf"# \d+ {category} agents", f"# {counts[category]} {category} agents", path)
    return updated


def update_claude_md_counts(text: str, counts: dict[str, int], path: Path) -> str:
    updated = replace_once(
        text,
        r"\d+ skills, \d+ agents, \d+ commands, \d+ hooks, \d+ MCP servers",
        f"{counts['skills']} skills, {counts['agents']} agents, {counts['commands']} commands, {counts['hooks']} hooks, {counts['mcp_servers']} MCP servers",
        path,
    )
    updated = replace_once(
        updated,
        r"ls commands/\*\.md \| wc -l\s+# Should be \d+",
        f"ls commands/*.md | wc -l              # Should be {counts['commands']}",
        path,
    )
    return updated


def update_readme_counts(text: str, counts: dict[str, int], path: Path) -> str:
    updated = replace_once(
        text,
        r"\d+ skills, \d+ agents, \d+ commands, \d+ hooks, and \d+ MCP servers",
        f"{counts['skills']} skills, {counts['agents']} agents, {counts['commands']} commands, {counts['hooks']} hooks, and {counts['mcp_servers']} MCP servers",
        path,
    )
    updated = replace_once(updated, r"### Skills \(\d+\)", f"### Skills ({counts['skills']})", path)
    updated = replace_once(updated, r"### Commands \(\d+\)", f"### Commands ({counts['commands']})", path)
    updated = replace_once(
        updated,
        r"# \d+ discipline skills \(SKILL\.md each\)",
        f"# {counts['skills']} discipline skills (SKILL.md each)",
        path,
    )
    updated = replace_once(updated, r"# \d+ slash commands", f"# {counts['commands']} slash commands", path)
    updated = replace_once(updated, r"### Hooks \(\d+\)", f"### Hooks ({counts['hooks']})", path)
    updated = replace_once(updated, r"\d+ review agents", f"{counts['review']} review agents", path)
    updated = replace_once(updated, r"### Agents \(\d+\)", f"### Agents ({counts['agents']})", path)
    return updated


def update_using_clavain_counts(text: str, counts: dict[str, int], path: Path) -> str:
    return replace_once(
        text,
        r"\d+ skills, \d+ agents, and \d+ commands",
        f"{counts['skills']} skills, {counts['agents']} agents, and {counts['commands']} commands",
        path,
    )


def update_count_strings(path: Path, text: str, counts: dict[str, int]) -> str:
    relative = path.relative_to(ROOT).as_posix()
    if relative == ".claude-plugin/plugin.json":
        return update_plugin_json_counts(text, counts, path)
    if relative == "agent-rig.json":
        return update_plugin_json_counts(text, counts, path)
    if relative == "AGENTS.md":
        return update_agents_md_counts(text, counts, path)
    if relative == "CLAUDE.md":
        return update_claude_md_counts(text, counts, path)
    if relative == "README.md":
        return update_readme_counts(text, counts, path)
    if relative == "skills/using-clavain/SKILL.md":
        return update_using_clavain_counts(text, counts, path)
    raise ValueError(f"Unexpected target file: {path}")


def load_existing_catalog(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(read_text(path))
    if isinstance(payload, dict):
        return payload
    raise ValueError(f"{path} is not a JSON object")


def build_catalog_text(
    counts: dict[str, int],
    skills: list[dict[str, str]],
    agents: list[dict[str, str]],
    commands: list[dict[str, str]],
    existing_catalog: dict[str, Any] | None,
) -> str:
    core = {
        "counts": counts,
        "skills": skills,
        "agents": agents,
        "commands": commands,
    }

    generated = utc_now_iso()
    if existing_catalog is not None:
        existing_core = {key: existing_catalog.get(key) for key in core}
        if existing_core == core:
            existing_generated = existing_catalog.get("generated")
            if isinstance(existing_generated, str) and existing_generated:
                generated = existing_generated

    payload = {
        "generated": generated,
        **core,
    }
    return json.dumps(payload, indent=2) + "\n"


def build_expected_files(root: Path) -> dict[Path, str]:
    skills, skill_count = collect_skills(root)
    agents, agent_count, agent_category_counts = collect_agents(root)
    commands, command_count = collect_commands(root)
    counts = {
        "skills": skill_count,
        "agents": agent_count,
        "commands": command_count,
        "hooks": count_hook_entries(root),
        "mcp_servers": count_mcp_servers(root),
        **agent_category_counts,
    }

    expected: dict[Path, str] = {}
    existing_catalog = load_existing_catalog(CATALOG_PATH)
    expected[CATALOG_PATH] = build_catalog_text(counts, skills, agents, commands, existing_catalog)

    for path in TARGET_FILES:
        current = read_text(path)
        expected[path] = update_count_strings(path, current, counts)

    return expected


def compute_drift(expected: dict[Path, str]) -> list[Path]:
    drifted: list[Path] = []
    for path, desired in expected.items():
        current = read_text(path) if path.exists() else None
        if current != desired:
            drifted.append(path)
    return drifted


def write_updates(expected: dict[Path, str], drifted: list[Path]) -> None:
    for path in drifted:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(expected[path], encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate docs/catalog.json and refresh component counts.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check for drift without writing files (exit 1 if changes are needed).",
    )
    args = parser.parse_args()

    expected = build_expected_files(ROOT)
    drifted = compute_drift(expected)

    if args.check:
        if drifted:
            print("Drift detected:")
            for path in drifted:
                print(f"- {path.relative_to(ROOT).as_posix()}")
            return 1
        print("Catalog and count strings are fresh.")
        return 0

    if not drifted:
        print("Catalog and count strings are already fresh.")
        return 0

    write_updates(expected, drifted)
    print("Updated files:")
    for path in drifted:
        print(f"- {path.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - fatal path
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2)
