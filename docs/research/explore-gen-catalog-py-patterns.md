# gen-catalog.py Pattern Analysis

## Overview

`gen-catalog.py` is a Python 3 build tool that:
1. Scans the plugin for skills, agents, commands, hooks, and MCP servers
2. Generates/maintains `docs/catalog.json` (metadata + counts)
3. Updates 6 documentation files with synchronized count strings
4. Supports `--check` mode for CI validation (exit 1 if drift detected)

## Collection Mechanisms

### Skills (`collect_skills()`)
- **Source**: `skills/*/SKILL.md` (glob pattern)
- **Count method**: `len(skill_files)` — file count
- **Metadata extracted**: `name`, `description` from YAML frontmatter
- **Sorting**: By name
- **Returns**: Tuple of (list[skills], count)

### Agents (`collect_agents()`)
- **Source**: `agents/{review,research,workflow}/*.md` (explicit category iteration)
- **Count method**: Increment counter for each `.md` file found across 3 categories
- **Metadata extracted**: `name`, `description`, `category` from YAML frontmatter
- **Important limitation**: Does NOT recursively scan subdirs — only top-level `.md` files
  - This automatically excludes `agents/review/references/` subdirectory
- **Sorting**: By `(category, name)` tuples
- **Returns**: Tuple of (list[agents], count)

### Commands (`collect_commands()`)
- **Source**: `commands/*.md` (glob pattern)
- **Count method**: `len(command_files)` — file count
- **Metadata extracted**: `name`, `description` from YAML frontmatter
- **Sorting**: By name
- **Returns**: Tuple of (list[commands], count)

### Hooks (`count_hook_entries()`)
- **Source**: `hooks/hooks.json` (not shell scripts)
- **Count method**: Counts hook **entries** (scalars in the hooks list), NOT event types
  - Parses JSON structure: `hooks.<event_name>[*].hooks[*]`
  - Iterates each event, each group within that event, each hook within that group
  - Sums `len(hooks)` across all groups
- **Important distinction**: If one event has 2 groups with 3 hooks each, total = 6, not 1 or 2
- **Returns**: Integer count

### MCP Servers (`count_mcp_servers()`)
- **Source**: `.claude-plugin/plugin.json`
- **Count method**: `len(mcpServers)` dict/list
- **Returns**: Integer count

## Pattern Catalog: Count String Updates

### 1. plugin.json
**Pattern**: `\d+ agents, \d+ commands, \d+ skills, \d+ MCP servers`
**Format**: `{agents} agents, {commands} commands, {skills} skills, {mcp_servers} MCP servers`
**Location**: Top-level description field
**Function**: `update_plugin_json_counts()`

Example:
```json
{
  "description": "29 agents, 37 commands, 29 skills, 2 MCP servers"
}
```

### 2. agent-rig.json
**Pattern**: `\d+ agents, \d+ commands, \d+ skills, \d+ MCP servers` (same as plugin.json)
**Format**: `{agents} agents, {commands} commands, {skills} skills, {mcp_servers} MCP servers`
**Function**: `update_plugin_json_counts()` (reused)

### 3. AGENTS.md
**Patterns** (5 total):

#### 3a. Intro summary line
- **Pattern**: `\d+ skills, \d+ agents, \d+ commands, \d+ hooks, \d+ MCP servers`
- **Format**: `{skills} skills, {agents} agents, {commands} commands, {hooks} hooks, {mcp_servers} MCP servers`

#### 3b. Architecture comment
- **Pattern**: `# \d+ discipline skills`
- **Format**: `# {skills} discipline skills`

#### 3c. Slash commands comment
- **Pattern**: `# \d+ slash commands`
- **Format**: `# {commands} slash commands`

#### 3d. Review agent count suffix (conflicts table)
- **Pattern**: `\(\+ \d+ others\)`
- **Format**: `(+ {others} others)` where `others = max(commands - 2, 0)`
- **Logic**: Subtracts 2 fixed commands (presumably `/flux-drive` and `/flux-gen`) from total

#### 3e. Skills validation comment
- **Pattern**: `echo "Skills: \$\(ls skills/\*/SKILL\.md \| wc -l\)"\s+# Should be \d+`
- **Format**: `echo "Skills: $(ls skills/*/SKILL.md | wc -l)"      # Should be {skills}`
- **Note**: Preserves exact spacing and shell variable interpolation

#### 3f. Commands validation comment
- **Pattern**: `echo "Commands: \$\(ls commands/\*\.md \| wc -l\)"\s+# Should be \d+`
- **Format**: `echo "Commands: $(ls commands/*.md | wc -l)"        # Should be {commands}`

**Function**: `update_agents_md_counts()` (6 replacements)

### 4. CLAUDE.md
**Patterns** (2 total):

#### 4a. Intro summary line
- **Pattern**: `\d+ skills, \d+ agents, \d+ commands, \d+ hooks, \d+ MCP servers`
- **Format**: `{skills} skills, {agents} agents, {commands} commands, {hooks} hooks, {mcp_servers} MCP servers`

#### 4b. Commands validation comment
- **Pattern**: `ls commands/\*\.md \| wc -l\s+# Should be \d+`
- **Format**: `ls commands/*.md | wc -l              # Should be {commands}`

**Function**: `update_claude_md_counts()`

### 5. README.md
**Patterns** (5 total):

#### 5a. Intro summary line
- **Pattern**: `\d+ skills, \d+ agents, \d+ commands, \d+ hooks, and \d+ MCP servers`
- **Format**: `{skills} skills, {agents} agents, {commands} commands, {hooks} hooks, and {mcp_servers} MCP servers`
- **Note**: Includes "and" before final count (differs from AGENTS.md/CLAUDE.md)

#### 5b. Skills section header
- **Pattern**: `### Skills \(\d+\)`
- **Format**: `### Skills ({skills})`

#### 5c. Commands section header
- **Pattern**: `### Commands \(\d+\)`
- **Format**: `### Commands ({commands})`

#### 5d. Discipline skills comment
- **Pattern**: `# \d+ discipline skills \(SKILL\.md each\)`
- **Format**: `# {skills} discipline skills (SKILL.md each)`

#### 5e. Slash commands comment
- **Pattern**: `# \d+ slash commands`
- **Format**: `# {commands} slash commands`

**Function**: `update_readme_counts()`

**Gap**: No pattern for `### Hooks (N)` header — script does NOT update it

### 6. using-clavain/SKILL.md
**Pattern**: `\d+ skills, \d+ agents, and \d+ commands`
**Format**: `{skills} skills, {agents} agents, and {commands} commands`
**Location**: Quick Router table
**Function**: `update_using_clavain_counts()`

**Gap**: No pattern for hooks or MCP servers in this file

## File Update Flow

```
build_expected_files(root)
├─ collect_skills(root) → (skills[], count)
├─ collect_agents(root) → (agents[], count)
├─ collect_commands(root) → (commands[], count)
├─ count_hook_entries(root) → int
├─ count_mcp_servers(root) → int
├─ build_catalog_text() → catalog.json string
└─ for each TARGET_FILES:
   └─ update_count_strings(path, current_text, counts) → updated_text
      └─ Dispatch to file-specific update function
         └─ Multiple replace_once() calls (1 pattern per replacement)

compute_drift(expected)
├─ Read current file content
└─ Compare with expected → list of drifted paths

write_updates(expected, drifted)
└─ for each drifted path:
   └─ write new content
```

## Catalog JSON Structure

**Path**: `docs/catalog.json`

**Schema**:
```json
{
  "generated": "2026-02-13T12:34:56Z",
  "counts": {
    "skills": 29,
    "agents": 17,
    "commands": 37,
    "hooks": 6,
    "mcp_servers": 2
  },
  "skills": [
    {"name": "...", "description": "..."},
    ...
  ],
  "agents": [
    {"name": "...", "description": "...", "category": "review|research|workflow"},
    ...
  ],
  "commands": [
    {"name": "...", "description": "..."},
    ...
  ]
}
```

**Timestamp persistence**: If catalog exists and core content (counts, skills, agents, commands) hasn't changed, the existing `generated` timestamp is preserved (idempotent).

## Check Mode (`--check`)

**Behavior**:
1. Build expected files (same as normal run)
2. Compute drift against current files
3. If any drifted paths: print list and exit 1
4. If no drift: print "Catalog and count strings are fresh." and exit 0

**Use case**: CI/CD validation that counts are synchronized before merge

## Gaps and Non-Updates

| Item | Pattern Present? | Location |
|------|------------------|----------|
| Hooks section header (`### Hooks (N)`) | ❌ NO | README.md (if it exists) |
| MCP servers section header | ❌ NO | Not found in any file |
| Architecture tree comment in AGENTS.md | ✓ YES | `# \d+ discipline skills` |
| Conflicts table in AGENTS.md | ✓ PARTIAL | Computes `(+ N others)` based on commands |

## Parsing & Error Handling

### YAML Frontmatter Parser (`parse_frontmatter()`)
- Requires `---` markers at start and end
- Skips empty lines and comments
- Handles scalar values (quoted strings)
- Handles block scalars (`|`, `>`, `|-`, `|+`, `>-`, `>+`)
- Throws ValueError if markers missing or field invalid

### Field Validation (`require_field()`)
- Throws ValueError if field missing or empty after strip

### Pattern Matching (`replace_once()`)
- Uses `re.MULTILINE` flag
- Replaces **exactly once per file** (count=1)
- Throws ValueError if pattern not found
- Catches logic errors early (missing patterns trigger build failure)

## Counts Summary

```python
counts = {
    "skills": 29,         # From len(skills/*/SKILL.md)
    "agents": 17,         # From agents/{review,research,workflow}/*.md
    "commands": 37,       # From len(commands/*.md)
    "hooks": 6,           # From hooks/hooks.json entries (not events)
    "mcp_servers": 2,     # From .claude-plugin/plugin.json mcpServers
}
```

## Target Files (6 total)

```python
TARGET_FILES = (
    .claude-plugin/plugin.json,
    AGENTS.md,
    CLAUDE.md,
    README.md,
    skills/using-clavain/SKILL.md,
    agent-rig.json,
)
```

Plus `docs/catalog.json` (always generated/updated)

## Coupling to Clavain Architecture

The script's design reflects Clavain's structure:
- **Agent categories**: review, research, workflow (hardcoded iteration order)
- **Skill location**: skills/*/SKILL.md (mandatory structure)
- **Command location**: commands/*.md (mandatory structure)
- **Hook structure**: hooks.json with event-based grouping
- **MCP servers**: Declared in plugin.json
- **Documentation**: 6 coordinated markdown + JSON files that must stay in sync

## Key Invariants

1. **All patterns use `re.MULTILINE`** — anchors can match line boundaries
2. **Each pattern must match exactly once per file** — script fails if pattern matches 0 or 2+ times
3. **Hook count is entries, not events** — counts individual hook items in hooks.json
4. **Agent count excludes references subdir** — only top-level agents/*.md files counted
5. **Catalog timestamp is sticky** — only updates if content changes, preserving history
6. **Check mode is idempotent** — no side effects, safe for CI
