# Plan: Clavain-16r — Add scripts/validate-roster.sh

## Context
After Clavain-th4 fixed the Agent Roster tier vocabulary, need a script to catch future drift between the roster table in SKILL.md and actual agent files/types.

## Changes

### 1. Create `scripts/validate-roster.sh`
- Parse the Agent Roster tables from `skills/flux-drive/SKILL.md`
- For each Plugin Agent row, verify the `subagent_type` exists in plugin.json's agents array
- For each Project Agent reference (`.claude/agents/fd-*.md`), just note it as "validated at runtime"
- For Cross-AI (Oracle), skip — it's a CLI tool not a subagent
- Exit 0 if all entries valid, exit 1 with list of mismatches
- Keep it simple: grep/awk parsing of the markdown table, not a full parser

### 2. Structure:
```bash
#!/usr/bin/env bash
set -euo pipefail

# Parse Plugin Agents table from SKILL.md
# For each row: extract agent name and subagent_type
# Check subagent_type exists in plugin.json agents array
# Report mismatches
```

## Acceptance Criteria
- Script is executable (`chmod +x`)
- Validates all Plugin Agent subagent_types against plugin.json
- Reports clear error messages for mismatches
- Exits 0 on success, 1 on failure
- Works from project root (`bash scripts/validate-roster.sh`)
