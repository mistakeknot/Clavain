# Plan: Clavain-th4 — Fix Agent Roster: tier vocabulary, spec-flow-analyzer categorization, table cleanup

## Context
The Agent Roster table in SKILL.md has inconsistencies in tier vocabulary and agent categorization. The YAML output spec includes a "domain" tier that no agent uses. spec-flow-analyzer is listed with Adaptive Reviewers but uses `clavain:workflow:` subagent_type, not `clavain:review:`.

## Current State
- `skills/flux-drive/SKILL.md` contains the Agent Roster table
- YAML output spec (in launch.md Output Format Override) includes `tier: {domain|project|adaptive|cross-ai}`
- "domain" tier is listed but no agents use it
- spec-flow-analyzer is in the Adaptive Reviewers section but its subagent_type is `clavain:workflow:spec-flow-analyzer`
- launch.md and launch-codex.md reference tiers in their prompt templates

## Implementation Plan

### Step 1: Fix tier enum in output format
**File:** `skills/flux-drive/phases/launch.md`

In the Output Format Override YAML schema, change:
```yaml
tier: {domain|project|adaptive|cross-ai}
```
to:
```yaml
tier: {project|adaptive|cross-ai}
```

Remove "domain" from the enum — no agents use it.

### Step 2: Fix tier references in launch-codex.md
**File:** `skills/flux-drive/phases/launch-codex.md`

Same change to tier enum in the TIER section of the task description format.

### Step 3: Recategorize spec-flow-analyzer
**File:** `skills/flux-drive/SKILL.md`

Two options:
- **Option A**: Move spec-flow-analyzer to its own "Workflow Agents" sub-table
- **Option B**: Rename "Adaptive Reviewers" to "Plugin Agents" to accurately cover all non-Project, non-Oracle agents

**Recommended: Option B** — Adding a whole sub-table for one agent is over-engineering. "Plugin Agents" accurately describes all agents loaded via `clavain:*` subagent_type, whether they're reviewers or workflow agents. The key distinction is Project (user's repo) vs Plugin (Clavain plugin) vs Cross-AI (Oracle).

Implementation:
- Rename "Adaptive Reviewers" header to "Plugin Agents" in the roster table
- Update any text that says "Adaptive Reviewers" to "Plugin Agents" in SKILL.md
- Keep the `adaptive` tier value in YAML output (changing it would break existing outputs) — add a note: "Plugin Agents use tier: adaptive"

### Step 4: Standardize tier vocabulary across files
Audit and fix references:
- `skills/flux-drive/SKILL.md` — roster section, scoring rules, category bonuses
- `skills/flux-drive/phases/launch.md` — prompt template, tier in YAML
- `skills/flux-drive/phases/launch-codex.md` — task description format

Ensure consistent use of:
- `project` — Project Agents (user's `.claude/agents/fd-*.md`)
- `adaptive` — Plugin Agents (Clavain plugin agents loaded via `subagent_type`)
- `cross-ai` — Cross-AI (Oracle)

### Step 5: Clean up roster table formatting
- Ensure all agents have consistent columns: Name, subagent_type, Domain/Focus
- Remove any stale entries for agents that no longer exist
- Verify every listed agent has a corresponding file

## Design Decisions
- **Keep `adaptive` tier value**: Changing it to `plugin` would break existing output files and the YAML schema. The display name changes ("Plugin Agents") but the tier value stays `adaptive`.
- **Option B over Option A**: One agent doesn't justify a new category. "Plugin Agents" is more accurate than "Adaptive Reviewers" for a group that includes both reviewers and workflow agents.
- **Remove "domain" tier**: Dead code. No agent has ever used it. Clean it up.

## Files Changed
1. `skills/flux-drive/SKILL.md` — Rename section, fix tier references, clean up table
2. `skills/flux-drive/phases/launch.md` — Remove "domain" from tier enum
3. `skills/flux-drive/phases/launch-codex.md` — Same tier enum fix

## Estimated Scope
~10-15 lines changed across 3 files. Mostly find-and-replace.

## Acceptance Criteria
- [ ] "domain" removed from tier enum in YAML output spec
- [ ] "Adaptive Reviewers" renamed to "Plugin Agents" in SKILL.md
- [ ] spec-flow-analyzer is properly categorized under Plugin Agents
- [ ] Tier vocabulary is consistent across SKILL.md, launch.md, launch-codex.md
- [ ] `adaptive` tier value is preserved in YAML (display name change only)
- [ ] Roster table is clean with no stale entries
