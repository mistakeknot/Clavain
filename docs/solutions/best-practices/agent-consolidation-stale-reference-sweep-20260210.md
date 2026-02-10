---
module: System
date: 2026-02-10
problem_type: best_practice
component: tooling
symptoms:
  - "Stale agent references in commands, skills, routing tables, and tests after deleting/renaming agents"
  - "Hardcoded agent counts in 5+ locations drift from actual file counts after consolidation"
  - "git mv leaves old files on disk requiring explicit rm -f cleanup"
  - "Template/example code in skill phases contains agent names that first-pass grep misses"
root_cause: missing_workflow_step
resolution_type: workflow_improvement
severity: medium
tags: [agent-consolidation, rename-sweep, stale-references, plugin-maintenance, grep-sweep]
---

# Best Practice: Agent Consolidation with Complete Reference Sweep

## Problem

When consolidating multiple agents into fewer merged agents (e.g., 19 specialized v1 agents into 6 core fd-* agents), stale references to deleted agent names persist across commands, skills, routing tables, tests, documentation, and hardcoded counts. A naive find-and-replace misses several non-obvious locations.

## Environment
- Module: System (Clavain plugin)
- Affected Component: agents/, commands/, skills/, tests/, README.md, AGENTS.md, CLAUDE.md, plugin.json
- Date: 2026-02-10

## Symptoms
- Commands dispatch deleted agents at runtime (e.g., `/review` still calls `architecture-strategist`)
- Routing table in `using-clavain/SKILL.md` sends users to non-existent agents
- `validate-roster.sh` passes but smoke tests fail on stale `subagent_type` strings
- README.md, AGENTS.md, CLAUDE.md, plugin.json all show different agent counts
- Test assertions have correct numeric value but wrong error message string

## The Pattern

### Step 1: Delete old agent files

```bash
# Delete v1 agents that were merged into new ones
git rm agents/review/architecture-strategist.md agents/review/security-sentinel.md ...

# Also delete from workflow/ if any were merged
git rm agents/workflow/spec-flow-analyzer.md
```

### Step 2: Rename new agents (drop version prefix)

```bash
# git mv creates new files but may leave old ones on disk
git mv agents/review/fd-v2-architecture.md agents/review/fd-architecture.md

# GOTCHA: Verify old files are actually gone
rm -f agents/review/fd-v2-architecture.md  # Explicit cleanup
```

Update frontmatter `name:` fields in each renamed file.

### Step 3: Grep sweep — all active code locations

Run a comprehensive grep for ALL old agent names across active code:

```bash
# Build a regex of all deleted/renamed agent names
grep -r 'architecture-strategist|security-sentinel|performance-oracle|...|fd-v2-' \
  skills/ agents/ commands/ hooks/ scripts/ tests/
```

**Locations that need updating (easy to miss):**

| Location | What to update |
|----------|---------------|
| `commands/*.md` | Agent dispatch references |
| `skills/using-clavain/SKILL.md` | 3-layer routing table |
| `skills/flux-drive/SKILL.md` | Roster table, triage examples |
| `skills/flux-drive/phases/launch.md` | Monitoring examples (`fd-architecture (47s)`), subagent_type examples |
| `skills/flux-drive/phases/synthesize.md` | findings.json template example |
| `skills/landing-a-change/SKILL.md` | Agent references in checklists |
| `skills/refactor-safely/SKILL.md` | Agent table |
| `scripts/validate-roster.sh` | Expected count, agent name patterns |
| `tests/smoke/smoke-prompt.md` | `subagent_type:` strings |
| `tests/structural/test_agents.py` | Assert count AND error message string |

### Step 4: Update hardcoded counts in 5+ locations

```bash
# All locations with hardcoded agent counts:
# 1. README.md — "With N skills, N agents..." + Architecture tree + Agents section
# 2. AGENTS.md — Quick Reference table + Architecture tree + Category descriptions
# 3. CLAUDE.md — Overview line + validation comments
# 4. plugin.json — description field
# 5. tests/structural/test_agents.py — assertion value AND error message
# 6. scripts/validate-roster.sh — EXPECTED_COUNT variable
```

### Step 5: Do NOT update historical records

These contain old agent names but are point-in-time records — leave them alone:

- `docs/research/` — Past flux-drive review outputs
- `docs/solutions/` — Past problem documentation
- `config/flux-drive/knowledge/` — Knowledge entries from past reviews
- `.claude/settings.local.json` — Stale permission entries (harmless)

## Why This Works

Agent names are scattered across the codebase as string references in markdown files, not as imports or type-checked symbols. There's no compiler to catch stale references. The grep sweep acts as a manual "find all references" pass. The key insight is that **example/template code** (monitoring output examples, JSON templates, triage scoring examples) contains agent names that look like documentation but are actually functional — they guide the orchestrator's behavior.

## Prevention

1. **After any agent rename/delete, always run a full grep sweep** — don't trust that you caught everything in the files you edited
2. **Maintain a single source of truth for counts** — currently 5+ locations have hardcoded counts that can drift
3. **`validate-roster.sh` catches roster/file mismatches** but not stale references in other skills/commands
4. **Knowledge layer entries and research artifacts are historical** — never update them during a rename sweep
5. **Test assertions need both the value AND the error message updated** — easy to fix one but not the other

## Related Issues

- See also: [new-agents-not-available-until-restart-20260210.md](../integration-issues/new-agents-not-available-until-restart-20260210.md) — related agent dispatch issue
