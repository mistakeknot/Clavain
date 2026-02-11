# Implementation Plan: gen-catalog.py

**Issue:** Clavain-i3o0 — Build gen-catalog.py to auto-generate counts + CI test for drift prevention  
**Date:** 2026-02-11  
**Status:** Plan

## Problem Statement

Component counts appear in 7+ documentation surfaces and they constantly drift out of sync. Current state of drift (actual filesystem counts vs. what files say):

| Component | Actual | plugin.json | agent-rig.json | CLAUDE.md | AGENTS.md | README.md | using-clavain |
|-----------|--------|-------------|----------------|-----------|-----------|-----------|---------------|
| Skills | **33** | 33 | 33 | 33 | 33 (Quick Ref) / **34** (tree) | 33 (intro) / **34** (heading+tree) | **34** |
| Agents | **16** | 16 | 16 | 16 | 16 | 16 | 16 |
| Commands | **28** | 28 | **23** | **28** (overview) / **27** (validation) | **28** (Quick Ref) / **25** (tree+validation) | **26** (intro) / **28** (heading) / **25** (tree) | **23** |
| Hooks | **5** | — | — | 5 | 5 | 5 | — |
| MCP Servers | **2** | 2 | 2 | 2 | 2 | 2 | — |

This demonstrates the exact problem: no single authoritative source, and counts are wrong in multiple places.

## Solution Architecture

### File: `scripts/gen-catalog.py`

A single Python script (stdlib only, no pip deps) that:
1. Reads the filesystem to count components and extract frontmatter
2. Generates `docs/catalog.json` as the single source of truth
3. Updates count strings in-place across 6 target files
4. Is idempotent — running twice produces no diff

### File: `tests/structural/test_catalog_freshness.py`

A pytest test that runs gen-catalog.py and verifies git diff is empty.

### Integration: `scripts/bump-version.sh` + `.github/workflows/test.yml`

gen-catalog.py is called before version bumps and in CI.

---

## Detailed Design

### 1. Counting Logic

The counting logic must exactly match the existing test suite (conftest.py + test_*.py):

```python
def count_skills(project_root: Path) -> list[dict]:
    """Count skills: directories under skills/ that contain SKILL.md."""
    skills_dir = project_root / "skills"
    return sorted(
        d for d in skills_dir.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    )
    # Returns list of Path objects; len() gives count

def count_agents(project_root: Path) -> dict[str, list[Path]]:
    """Count agents: .md files in explicit category dirs (excludes references/)."""
    agents_dir = project_root / "agents"
    result = {}
    for category in ("review", "research", "workflow"):
        category_dir = agents_dir / category
        if category_dir.is_dir():
            result[category] = sorted(category_dir.glob("*.md"))
    return result
    # Total = sum of all list lengths

def count_commands(project_root: Path) -> list[Path]:
    """Count commands: .md files in commands/."""
    return sorted((project_root / "commands").glob("*.md"))

def count_hooks(project_root: Path) -> int:
    """Count hooks: individual hook entries in hooks.json."""
    with open(project_root / "hooks" / "hooks.json") as f:
        data = json.load(f)
    count = 0
    for event_type, hook_groups in data.get("hooks", {}).items():
        for group in hook_groups:
            count += len(group.get("hooks", []))
    return count

def count_mcp_servers(project_root: Path) -> int:
    """Count MCP servers: keys in plugin.json mcpServers."""
    with open(project_root / ".claude-plugin" / "plugin.json") as f:
        data = json.load(f)
    return len(data.get("mcpServers", {}))
```

**Critical gotcha:** Agent counting uses `category_dir.glob("*.md")` which only matches `.md` files directly in the category directory. The `agents/review/references/` subdirectory is naturally excluded because glob("*.md") is not recursive. This must NOT be changed to `rglob` or `**/*.md`.

### 2. Frontmatter Parsing

Reuse the same YAML frontmatter parsing as `tests/structural/helpers.py`:

```python
def parse_frontmatter(path: Path) -> tuple[dict | None, str]:
    """Parse YAML frontmatter from a markdown file.
    
    Returns (frontmatter_dict, body_text) or (None, full_text) if no frontmatter.
    Uses only stdlib — no PyYAML dependency.
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text
    # Simple YAML parsing for flat key-value pairs (no PyYAML needed)
    fm = {}
    for line in parts[1].strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            fm[key] = value
    return fm, parts[2]
```

**Note on PyYAML:** The existing test suite uses PyYAML (`import yaml` in helpers.py), but gen-catalog.py must use stdlib only per requirements. The frontmatter in this project is simple flat key-value YAML (no nesting, no lists, no anchors), so a basic parser suffices. The fields we need are just `name` and `description`.

### 3. catalog.json Schema

```json
{
  "generated": "2026-02-11T14:30:00Z",
  "counts": {
    "skills": 33,
    "agents": 16,
    "agents_by_category": {
      "review": 9,
      "research": 5,
      "workflow": 2
    },
    "commands": 28,
    "hooks": 5,
    "mcp_servers": 2
  },
  "skills": [
    {
      "name": "agent-native-architecture",
      "description": "...",
      "path": "skills/agent-native-architecture/SKILL.md"
    }
  ],
  "agents": {
    "review": [
      {
        "name": "agent-native-reviewer",
        "description": "...",
        "model": "inherit",
        "path": "agents/review/agent-native-reviewer.md"
      }
    ],
    "research": [...],
    "workflow": [...]
  },
  "commands": [
    {
      "name": "agent-native-audit",
      "description": "...",
      "argument_hint": "...",
      "path": "commands/agent-native-audit.md"
    }
  ],
  "hooks": [
    {
      "event": "PreToolUse",
      "matcher": "Edit|Write|MultiEdit|NotebookEdit",
      "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/autopilot.sh\"",
      "timeout": 5
    }
  ],
  "mcp_servers": [
    {
      "name": "context7",
      "type": "http",
      "url": "https://mcp.context7.com/mcp"
    },
    {
      "name": "qmd",
      "type": "stdio",
      "command": "qmd"
    }
  ]
}
```

### 4. In-Place Update Targets

Each target file has different count format(s). The script must find and replace each pattern without disturbing surrounding content. Here are the exact patterns:

#### 4a. `.claude-plugin/plugin.json` (line 4)

**Current:** `"description": "General-purpose engineering discipline plugin. 16 agents, 28 commands, 33 skills, 2 MCP servers — combining workflow discipline..."`

**Pattern (regex):** `(\d+) agents, (\d+) commands, (\d+) skills, (\d+) MCP servers`

**Replacement:** `{agents} agents, {commands} commands, {skills} skills, {mcp_servers} MCP servers`

**Notes:** This file uses JSON so the count string is inside a quoted JSON value. The order is `agents, commands, skills, MCP servers` (different from other files). The regex must match within the `"description"` value only.

#### 4b. `agent-rig.json` (line 4)

**Current:** `"description": "General-purpose engineering discipline rig — 16 agents, 23 commands, 33 skills, 2 MCP servers. Combines workflow..."`

**Pattern (regex):** `(\d+) agents, (\d+) commands, (\d+) skills, (\d+) MCP servers`

**Replacement:** `{agents} agents, {commands} commands, {skills} skills, {mcp_servers} MCP servers`

**Notes:** Same format as plugin.json description.

#### 4c. `CLAUDE.md` (lines 7, 16-18)

**Location 1 — Overview line (line 7):**

**Current:** `General-purpose engineering discipline plugin for Claude Code — 33 skills, 16 agents, 28 commands, 5 hooks, 2 MCP servers.`

**Pattern:** `(\d+) skills, (\d+) agents, (\d+) commands, (\d+) hooks, (\d+) MCP servers`

**Replacement:** `{skills} skills, {agents} agents, {commands} commands, {hooks} hooks, {mcp_servers} MCP servers`

**Location 2 — Validation comments (lines 16-18):**

```
ls skills/*/SKILL.md | wc -l          # Should be 33
ls agents/{review,research,workflow}/*.md | wc -l  # Should be 16
ls commands/*.md | wc -l              # Should be 27
```

**Patterns:**
- `# Should be (\d+)` after `skills/*/SKILL.md` → `# Should be {skills}`
- `# Should be (\d+)` after `agents/` → `# Should be {agents}`
- `# Should be (\d+)` after `commands/*.md` → `# Should be {commands}`

**Strategy:** Match the full validation lines since "Should be N" appears uniquely per line. Use three separate regex replacements, each anchored to the preceding glob pattern.

**Precise regexes:**
```python
(skills/\*/SKILL\.md.*?# Should be )\d+   → \g<1>{skills}
(agents/\{review,research,workflow\}/\*\.md.*?# Should be )\d+   → \g<1>{agents}
(commands/\*\.md.*?# Should be )\d+   → \g<1>{commands}
```

#### 4d. `AGENTS.md` (line 12, lines 26/40-43/214)

**Location 1 — Quick Reference table (line 12):**

**Current:** `| Components | 33 skills, 16 agents, 28 commands, 5 hooks, 2 MCP servers |`

**Pattern:** `(\| Components \| )(\d+) skills, (\d+) agents, (\d+) commands, (\d+) hooks, (\d+) MCP servers( \|)`

**Replacement:** `\g<1>{skills} skills, {agents} agents, {commands} commands, {hooks} hooks, {mcp_servers} MCP servers\g<7>`

**Location 2 — Architecture tree comments (lines 26, 40-43):**

```
├── skills/                        # 34 discipline skills
│   ├── review/                    # 9 review agents
│   ├── research/                  # 5 research agents
│   └── workflow/                  # 2 workflow agents
├── commands/                      # 25 slash commands
```

**Patterns (5 separate replacements):**
```python
(# )\d+( discipline skills)     → \g<1>{skills}\g<2>
(# )\d+( review agents)         → \g<1>{agents_review}\g<2>
(# )\d+( research agents)       → \g<1>{agents_research}\g<2>
(# )\d+( workflow agents)       → \g<1>{agents_workflow}\g<2>
(# )\d+( slash commands)        → \g<1>{commands}\g<2>
```

**Location 3 — Quick validation comments (lines 212, 214):**

```
echo "Skills: $(ls skills/*/SKILL.md | wc -l)"      # Should be 33
echo "Commands: $(ls commands/*.md | wc -l)"        # Should be 25
```

**Patterns:**
```python
(Skills:.*?# Should be )\d+     → \g<1>{skills}
(Commands:.*?# Should be )\d+   → \g<1>{commands}
```

#### 4e. `README.md` (line 7, lines 99/146/156/193/200, lines 259/261-264)

**Location 1 — Intro paragraph (line 7):**

**Current:** `With 33 skills, 16 agents, 26 commands, 5 hooks, and 2 MCP servers, there is a lot here`

**Pattern:** `(\d+) skills, (\d+) agents, (\d+) commands, (\d+) hooks, and (\d+) MCP servers`

**Replacement:** `{skills} skills, {agents} agents, {commands} commands, {hooks} hooks, and {mcp_servers} MCP servers`

**Location 2 — Section headings (lines 99, 146, 156, 193, 200):**

```
### Skills (34)
### Agents (16)
### Commands (28)
### Hooks (5)
### MCP Servers (2)
```

**Patterns:**
```python
### Skills \(\d+\)        → ### Skills ({skills})
### Agents \(\d+\)        → ### Agents ({agents})
### Commands \(\d+\)      → ### Commands ({commands})
### Hooks \(\d+\)         → ### Hooks ({hooks})
### MCP Servers \(\d+\)   → ### MCP Servers ({mcp_servers})
```

**Location 3 — Architecture tree (lines 259, 261-264):**

Same patterns as AGENTS.md tree:
```python
(# )\d+( discipline skills)     → same
(# )\d+( review agents)         → same
(# )\d+( research agents)       → same
(# )\d+( workflow agents)       → same
(# )\d+( slash commands)        → same
```

#### 4f. `skills/using-clavain/SKILL.md` (line 24)

**Current:** `Clavain provides 34 skills, 16 agents, and 23 commands.`

**Pattern:** `Clavain provides (\d+) skills, (\d+) agents, and (\d+) commands`

**Replacement:** `Clavain provides {skills} skills, {agents} agents, and {commands} commands`

#### 4g. Summary of AGENTS.md and CLAUDE.md validation comment patterns

The CLAUDE.md validation section has 3 lines, AGENTS.md has 2 lines with `# Should be N`. Both reference filesystem glob patterns. These "Should be N" comments should be treated as count targets.

### 5. Update Engine Design

```python
def update_file(path: Path, replacements: list[tuple[str, str]]) -> bool:
    """Apply regex replacements to a file. Returns True if any changes made."""
    text = path.read_text(encoding="utf-8")
    original = text
    for pattern, replacement in replacements:
        text, count = re.subn(pattern, replacement, text)
        if count == 0:
            print(f"  WARNING: pattern not matched in {path.name}: {pattern[:60]}...", file=sys.stderr)
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False
```

Each target file gets a list of `(pattern, replacement)` tuples. The function:
- Reads the file once
- Applies all replacements sequentially
- Writes once if anything changed
- Warns (to stderr) if a pattern fails to match — this catches format drift in the targets themselves

### 6. Script Structure

```python
#!/usr/bin/env python3
"""Generate component catalog and sync counts across documentation.

Reads the filesystem to count skills, agents, commands, hooks, and MCP servers,
generates docs/catalog.json, and updates count strings in-place across 6 target files.

Usage:
    python3 scripts/gen-catalog.py              # Generate catalog + update files
    python3 scripts/gen-catalog.py --check      # Check only (exit 1 if stale)
    python3 scripts/gen-catalog.py --dry-run    # Show what would change
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate component catalog")
    parser.add_argument("--check", action="store_true",
                        help="Check mode: exit 1 if catalog or docs are stale")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without writing")
    parser.add_argument("--project-root", type=Path, default=None,
                        help="Project root (default: auto-detect from script location)")
    args = parser.parse_args()

    project_root = args.project_root or Path(__file__).resolve().parent.parent
    
    # 1. Count everything
    counts = gather_counts(project_root)
    
    # 2. Build full catalog
    catalog = build_catalog(project_root, counts)
    
    # 3. Write catalog.json
    catalog_path = project_root / "docs" / "catalog.json"
    if not args.check and not args.dry_run:
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        with open(catalog_path, "w") as f:
            json.dump(catalog, f, indent=2)
            f.write("\n")
    
    # 4. Update target files
    warnings = update_all_targets(project_root, counts, 
                                   check=args.check, dry_run=args.dry_run)
    
    # 5. Report
    if args.check and warnings:
        print(f"FAIL: {len(warnings)} file(s) have stale counts", file=sys.stderr)
        for w in warnings:
            print(f"  {w}", file=sys.stderr)
        return 1
    
    if not args.check:
        print(f"Catalog: {counts['skills']} skills, {counts['agents']} agents, "
              f"{counts['commands']} commands, {counts['hooks']} hooks, "
              f"{counts['mcp_servers']} MCP servers")
    
    return 0


def gather_counts(root: Path) -> dict:
    """Return a flat dict of all component counts."""
    skills = count_skills(root)
    agents = count_agents(root)
    commands = count_commands(root)
    hooks = count_hooks(root)
    mcp = count_mcp_servers(root)
    
    return {
        "skills": len(skills),
        "agents": sum(len(v) for v in agents.values()),
        "agents_review": len(agents.get("review", [])),
        "agents_research": len(agents.get("research", [])),
        "agents_workflow": len(agents.get("workflow", [])),
        "commands": len(commands),
        "hooks": hooks,
        "mcp_servers": mcp,
    }
```

### 7. Replacement Rules — Complete Specification

Here is the complete list of replacement rules for each file, specified precisely enough for implementation:

```python
def get_replacements(counts: dict) -> dict[str, list[tuple[str, str]]]:
    """Return {relative_path: [(regex_pattern, replacement), ...]}."""
    c = counts
    return {
        ".claude-plugin/plugin.json": [
            # "description" field: "N agents, N commands, N skills, N MCP servers"
            (r'(\d+)( agents, )(\d+)( commands, )(\d+)( skills, )(\d+)( MCP servers)',
             f'{c["agents"]}\\2{c["commands"]}\\4{c["skills"]}\\6{c["mcp_servers"]}\\8'),
        ],
        "agent-rig.json": [
            # "description" field: same format as plugin.json
            (r'(\d+)( agents, )(\d+)( commands, )(\d+)( skills, )(\d+)( MCP servers)',
             f'{c["agents"]}\\2{c["commands"]}\\4{c["skills"]}\\6{c["mcp_servers"]}\\8'),
        ],
        "CLAUDE.md": [
            # Overview line: "N skills, N agents, N commands, N hooks, N MCP servers"
            (r'(\d+)( skills, )(\d+)( agents, )(\d+)( commands, )(\d+)( hooks, )(\d+)( MCP servers)',
             f'{c["skills"]}\\2{c["agents"]}\\4{c["commands"]}\\6{c["hooks"]}\\8{c["mcp_servers"]}\\10'),
            # Validation: skills Should be N
            (r'(skills/\*/SKILL\.md.*?# Should be )\d+',
             f'\\g<1>{c["skills"]}'),
            # Validation: agents Should be N
            (r'(agents/\{review,research,workflow\}/\*\.md.*?# Should be )\d+',
             f'\\g<1>{c["agents"]}'),
            # Validation: commands Should be N
            (r'(commands/\*\.md.*?# Should be )\d+',
             f'\\g<1>{c["commands"]}'),
        ],
        "AGENTS.md": [
            # Quick Reference table: "| Components | N skills, N agents, ... |"
            (r'(\d+)( skills, )(\d+)( agents, )(\d+)( commands, )(\d+)( hooks, )(\d+)( MCP servers)',
             f'{c["skills"]}\\2{c["agents"]}\\4{c["commands"]}\\6{c["hooks"]}\\8{c["mcp_servers"]}\\10'),
            # Architecture tree: discipline skills
            (r'(# )\d+( discipline skills)',
             f'\\g<1>{c["skills"]}\\2'),
            # Architecture tree: review agents
            (r'(# )\d+( review agents)',
             f'\\g<1>{c["agents_review"]}\\2'),
            # Architecture tree: research agents
            (r'(# )\d+( research agents)',
             f'\\g<1>{c["agents_research"]}\\2'),
            # Architecture tree: workflow agents
            (r'(# )\d+( workflow agents)',
             f'\\g<1>{c["agents_workflow"]}\\2'),
            # Architecture tree: slash commands
            (r'(# )\d+( slash commands)',
             f'\\g<1>{c["commands"]}\\2'),
            # Validation: Skills Should be N
            (r'(Skills:.*?# Should be )\d+',
             f'\\g<1>{c["skills"]}'),
            # Validation: Commands Should be N
            (r'(Commands:.*?# Should be )\d+',
             f'\\g<1>{c["commands"]}'),
        ],
        "README.md": [
            # Intro paragraph: "N skills, N agents, N commands, N hooks, and N MCP servers"
            (r'(\d+)( skills, )(\d+)( agents, )(\d+)( commands, )(\d+)( hooks, and )(\d+)( MCP servers)',
             f'{c["skills"]}\\2{c["agents"]}\\4{c["commands"]}\\6{c["hooks"]}\\8{c["mcp_servers"]}\\10'),
            # Section headings
            (r'### Skills \(\d+\)',
             f'### Skills ({c["skills"]})'),
            (r'### Agents \(\d+\)',
             f'### Agents ({c["agents"]})'),
            (r'### Commands \(\d+\)',
             f'### Commands ({c["commands"]})'),
            (r'### Hooks \(\d+\)',
             f'### Hooks ({c["hooks"]})'),
            (r'### MCP Servers \(\d+\)',
             f'### MCP Servers ({c["mcp_servers"]})'),
            # Architecture tree: discipline skills
            (r'(# )\d+( discipline skills)',
             f'\\g<1>{c["skills"]}\\2'),
            # Architecture tree: review agents
            (r'(# )\d+( review agents)',
             f'\\g<1>{c["agents_review"]}\\2'),
            # Architecture tree: research agents
            (r'(# )\d+( research agents)',
             f'\\g<1>{c["agents_research"]}\\2'),
            # Architecture tree: workflow agents
            (r'(# )\d+( workflow agents)',
             f'\\g<1>{c["agents_workflow"]}\\2'),
            # Architecture tree: slash commands
            (r'(# )\d+( slash commands)',
             f'\\g<1>{c["commands"]}\\2'),
        ],
        "skills/using-clavain/SKILL.md": [
            # "Clavain provides N skills, N agents, and N commands"
            (r'(Clavain provides )\d+( skills, )\d+( agents, and )\d+( commands)',
             f'\\g<1>{c["skills"]}\\2{c["agents"]}\\3{c["commands"]}\\4'),
        ],
    }
```

### 8. Update Test Suite Hard-Coded Counts

**Important consideration:** The existing test files in `tests/structural/` have hard-coded count assertions:
- `test_skills.py` line 29: `assert len(dirs) == 33`
- `test_agents.py` line 23: `assert len(agent_files) == 16`
- `test_commands.py` line 23: `assert len(files) == 28`

These should **NOT** be updated by gen-catalog.py. The tests serve as independent regression guards. If they disagree with catalog.json, that is a signal that either:
1. Components were added/removed without running gen-catalog.py, or
2. gen-catalog.py has a counting bug

Instead, the tests should be **changed to read from catalog.json** (see Section 12 below for the optional migration plan). For the initial implementation, the hard-coded test counts should be manually updated when gen-catalog.py is first run, then kept in sync by the CI drift test.

### 9. CI Test: test_catalog_freshness.py

```python
"""Test that docs/catalog.json and doc counts are fresh.

Runs gen-catalog.py --check and fails if any counts have drifted.
"""
import subprocess
import sys
from pathlib import Path


def test_catalog_not_stale(project_root):
    """gen-catalog.py --check exits 0 (no stale counts)."""
    script = project_root / "scripts" / "gen-catalog.py"
    result = subprocess.run(
        [sys.executable, str(script), "--check", "--project-root", str(project_root)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Catalog counts are stale. Run: python3 scripts/gen-catalog.py\n"
        f"stderr: {result.stderr}"
    )
```

**Alternative approach (more robust):** Instead of shelling out to the script, the test could import the counting functions directly and compare against catalog.json:

```python
"""Test that docs/catalog.json matches the filesystem."""
import json
from pathlib import Path


def test_catalog_counts_match_filesystem(project_root):
    """catalog.json counts match actual filesystem counts."""
    catalog_path = project_root / "docs" / "catalog.json"
    assert catalog_path.exists(), (
        "docs/catalog.json not found. Run: python3 scripts/gen-catalog.py"
    )
    
    with open(catalog_path) as f:
        catalog = json.load(f)
    
    # Count from filesystem (same logic as conftest.py fixtures)
    skills_dir = project_root / "skills"
    actual_skills = len([
        d for d in skills_dir.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    ])
    
    agents_dir = project_root / "agents"
    actual_agents = 0
    for cat in ("review", "research", "workflow"):
        cat_dir = agents_dir / cat
        if cat_dir.is_dir():
            actual_agents += len(list(cat_dir.glob("*.md")))
    
    actual_commands = len(list((project_root / "commands").glob("*.md")))
    
    counts = catalog["counts"]
    assert counts["skills"] == actual_skills, f"Skills: catalog={counts['skills']}, fs={actual_skills}"
    assert counts["agents"] == actual_agents, f"Agents: catalog={counts['agents']}, fs={actual_agents}"
    assert counts["commands"] == actual_commands, f"Commands: catalog={counts['commands']}, fs={actual_commands}"
```

**Recommendation:** Use both approaches:
1. `test_catalog_counts_match_filesystem` — verifies catalog.json is fresh against the filesystem
2. `test_doc_counts_not_stale` — shells out to `gen-catalog.py --check` to verify docs are synced to catalog

### 10. --check Mode Implementation

The `--check` mode is crucial for CI. It should:

1. Count components from filesystem
2. Compare against existing catalog.json
3. For each target file, read current content and apply replacements, but instead of writing, compare against current content
4. Return exit code 0 if everything matches, 1 if anything is stale

```python
def update_all_targets(root: Path, counts: dict, 
                       check: bool = False, dry_run: bool = False) -> list[str]:
    """Update (or check) all target files. Returns list of stale file warnings."""
    warnings = []
    replacements_map = get_replacements(counts)
    
    for rel_path, replacements in replacements_map.items():
        path = root / rel_path
        if not path.exists():
            warnings.append(f"Missing file: {rel_path}")
            continue
        
        text = path.read_text(encoding="utf-8")
        updated = text
        for pattern, replacement in replacements:
            updated = re.sub(pattern, replacement, updated)
        
        if updated != text:
            if check:
                warnings.append(f"Stale counts in: {rel_path}")
            elif dry_run:
                print(f"  Would update: {rel_path}")
            else:
                path.write_text(updated, encoding="utf-8")
                print(f"  Updated: {rel_path}")
    
    # Also check catalog.json freshness
    catalog_path = root / "docs" / "catalog.json"
    if check and catalog_path.exists():
        with open(catalog_path) as f:
            existing = json.load(f)
        if existing.get("counts", {}).get("skills") != counts["skills"] or \
           existing.get("counts", {}).get("agents") != counts["agents"] or \
           existing.get("counts", {}).get("commands") != counts["commands"] or \
           existing.get("counts", {}).get("hooks") != counts["hooks"] or \
           existing.get("counts", {}).get("mcp_servers") != counts["mcp_servers"]:
            warnings.append("Stale: docs/catalog.json")
    elif check and not catalog_path.exists():
        warnings.append("Missing: docs/catalog.json")
    
    return warnings
```

### 11. Integration with bump-version.sh

Add gen-catalog.py call before the version bump in `scripts/bump-version.sh`:

```bash
# --- Add after VERSION validation, before the update_file calls ---

echo "Syncing component catalog..."
if ! python3 "$REPO_ROOT/scripts/gen-catalog.py" --project-root "$REPO_ROOT"; then
    echo -e "${RED}Error: gen-catalog.py failed${NC}" >&2
    exit 1
fi

# Add catalog.json to the commit
# (later in the script, add to the git add command)
```

Modify the git add line (line 103) from:
```bash
git add .claude-plugin/plugin.json agent-rig.json
```
to:
```bash
git add .claude-plugin/plugin.json agent-rig.json docs/catalog.json CLAUDE.md AGENTS.md README.md skills/using-clavain/SKILL.md
```

### 12. Integration with CI (test.yml)

The existing test.yml already runs `cd tests && uv run pytest structural/ -v --tb=short`. Since `test_catalog_freshness.py` goes into `tests/structural/`, it will be picked up automatically.

**One consideration:** The test shells out to `python3 scripts/gen-catalog.py --check`. In CI, the Python version is 3.12 (from test.yml). gen-catalog.py uses only stdlib, so this should work. However, the test needs to find `python3` or `sys.executable`. Using `sys.executable` is safer since it matches whatever pytest is running under.

### 13. Optional: Migrate Hard-Coded Test Counts to catalog.json

After gen-catalog.py is stable, the hard-coded counts in `test_skills.py`, `test_agents.py`, and `test_commands.py` can be migrated to read from catalog.json:

```python
# In conftest.py, add:
@pytest.fixture(scope="session")
def catalog(project_root: Path) -> dict:
    """Parsed docs/catalog.json."""
    catalog_path = project_root / "docs" / "catalog.json"
    assert catalog_path.exists(), "Run: python3 scripts/gen-catalog.py"
    with open(catalog_path) as f:
        return json.load(f)

# In test_skills.py, change:
def test_skill_count(skills_dir, catalog):
    dirs = sorted(d for d in skills_dir.iterdir() if d.is_dir() and (d / "SKILL.md").exists())
    expected = catalog["counts"]["skills"]
    assert len(dirs) == expected, f"Expected {expected} skills, found {len(dirs)}"
```

**Recommendation:** Do this in a follow-up PR, not in the initial gen-catalog.py PR. The initial PR should focus on getting the catalog generator right. Changing the test fixtures adds risk.

---

## Implementation Steps

### Step 1: Create `scripts/gen-catalog.py`

**Functions to implement:**
1. `parse_frontmatter(path)` — Simple YAML parser (stdlib only)
2. `count_skills(root)` — Returns list of skill directories
3. `count_agents(root)` — Returns dict of category -> list of agent paths
4. `count_commands(root)` — Returns list of command paths
5. `count_hooks(root)` — Returns int
6. `count_mcp_servers(root)` — Returns int
7. `gather_counts(root)` — Returns flat dict with all counts
8. `build_catalog(root, counts)` — Returns full catalog dict with frontmatter data
9. `get_replacements(counts)` — Returns {rel_path: [(pattern, replacement), ...]}
10. `update_all_targets(root, counts, check, dry_run)` — Apply or check replacements
11. `main()` — CLI entry point with argparse

**Estimated size:** ~250-300 lines of Python.

### Step 2: Create `tests/structural/test_catalog_freshness.py`

Two tests:
1. `test_catalog_counts_match_filesystem` — Direct comparison
2. `test_doc_counts_not_stale` — Shells out to gen-catalog.py --check

**Estimated size:** ~50 lines.

### Step 3: Run gen-catalog.py for the first time

This will:
- Create `docs/catalog.json`
- Fix all drifted counts across the 6 target files
- The resulting diff will show all the count corrections

### Step 4: Update hard-coded test counts

After gen-catalog.py runs, update:
- `test_skills.py` line 29: `== 33` (already correct)
- `test_agents.py` line 23: `== 16` (already correct)
- `test_commands.py` line 23: `== 28` (already correct)

These should match the catalog output. If they already do, no change needed.

### Step 5: Update bump-version.sh

Add the gen-catalog.py call and expand the git add line.

### Step 6: Add catalog.json to .gitignore? No.

`docs/catalog.json` should be **committed** to the repo. It serves as:
- A machine-readable inventory for tooling
- The authoritative source that tests verify against
- A diffable record of component changes

### Step 7: Update MEMORY.md

Add a note about gen-catalog.py to the project memory.

---

## Edge Cases and Error Handling

1. **Missing target file:** Warn and continue (don't exit 1 for missing optional files)
2. **Pattern not matched in target:** Warn to stderr. This means the target file's format has changed and the regex needs updating.
3. **Frontmatter parsing failure:** Log to stderr, skip the component (don't fail the whole script)
4. **hooks.json parse error:** Exit 1 with clear error message
5. **plugin.json parse error:** Exit 1 with clear error message
6. **Empty categories:** Handle gracefully (e.g., if workflow/ has 0 agents)
7. **New agent category directory:** The script only counts review/research/workflow. If a new category is added, the script must be updated. This is intentional — it matches the test suite behavior.

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Regex matches wrong occurrence in a file | Each pattern is specific enough to match exactly once per file. The update function warns if a pattern matches 0 or >1 times. |
| Script breaks when doc format changes | --check mode in CI catches this immediately. Warning on unmatched patterns helps debug. |
| catalog.json conflicts on merge | JSON is auto-generated; resolve by re-running gen-catalog.py. |
| PyYAML vs stdlib frontmatter parsing mismatch | The frontmatter in this project is flat key-value only. Test by comparing outputs. |
| Script introduces dependency on Python 3.12+ | Use only Python 3.8+ compatible features (pathlib, f-strings, type hints with `from __future__ import annotations`). |

## Files to Create

1. **`scripts/gen-catalog.py`** — Main script (~250-300 lines)
2. **`tests/structural/test_catalog_freshness.py`** — CI test (~50 lines)
3. **`docs/catalog.json`** — Generated output (committed)

## Files to Modify

4. **`scripts/bump-version.sh`** — Add gen-catalog.py call + expand git add
5. **`tests/structural/test_skills.py`** — Update count if needed (line 29)
6. **`tests/structural/test_agents.py`** — Update count if needed (line 23)
7. **`tests/structural/test_commands.py`** — Update count if needed (line 23)
8. **Plus the 6 target files** that gen-catalog.py auto-updates (CLAUDE.md, AGENTS.md, README.md, plugin.json, agent-rig.json, using-clavain/SKILL.md)

## Verification

After implementation:
```bash
# Generate catalog and fix counts
python3 scripts/gen-catalog.py

# Verify idempotency
python3 scripts/gen-catalog.py
git diff  # Should be empty

# Verify check mode
python3 scripts/gen-catalog.py --check
echo $?  # Should be 0

# Run test suite
cd tests && uv run pytest structural/ -v --tb=short
```
