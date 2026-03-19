---
title: "Refactoring Safety and Consumer Awareness"
category: best-practices
tags: [refactoring-safety, stale-references, rename-sweep, templates, multiple-consumers, grep-sweep]
date: 2026-03-19
synthesized_from:
  - best-practices/agent-consolidation-stale-reference-sweep-20260210.md
  - best-practices/template-system-has-multiple-consumers-clodex-20260211.md
---

# Refactoring Safety and Consumer Awareness

Two patterns for avoiding breakage when renaming, consolidating, or simplifying shared infrastructure in a plugin codebase where references are string-based (markdown files, not type-checked imports).

## Pattern 1: Complete Reference Sweep After Agent Rename/Delete

When consolidating agents (e.g., merging 19 specialized agents into 6 core agents), stale references persist across commands, skills, routing tables, tests, documentation, and hardcoded counts. There is no compiler to catch stale string references in markdown.

**Mandatory sweep locations:**

| Location | What to update |
|----------|---------------|
| `commands/*.md` | Agent dispatch references |
| `skills/*/SKILL.md` | Routing tables, roster tables, triage examples |
| `skills/*/phases/*.md` | Monitoring examples, subagent_type examples, JSON templates |
| `scripts/validate-roster.sh` | Expected count, agent name patterns |
| `tests/smoke/` | `subagent_type:` strings |
| `tests/structural/` | Assert count AND error message string |
| `README.md`, `AGENTS.md`, `CLAUDE.md`, `plugin.json` | Hardcoded agent counts (5+ locations) |

**Do NOT update:** Historical records in `docs/research/`, `docs/solutions/`, `config/flux-drive/knowledge/` -- these are point-in-time records.

**Key gotcha:** Example/template code (monitoring output examples, JSON templates, triage scoring) contains agent names that look like documentation but are functionally significant -- they guide orchestrator behavior. First-pass grep misses these.

**After any rename/delete:** Run `grep -r 'old-name-1|old-name-2|...' skills/ agents/ commands/ hooks/ scripts/ tests/` before committing.

## Pattern 2: Check All Consumers Before Simplifying Shared Infrastructure

When simplifying a feature (e.g., removing template indirection from a skill), always grep for all consumers first. A system that appears single-consumer may have multiple independent callers.

**Example:** `dispatch.sh`'s template substitution was used by both clodex (general dispatch, where templates add unnecessary indirection) and flux-drive (review agent dispatch, where templates are essential for identity injection). Removing template support would break flux-drive.

**The safe approach:**
1. Scope changes to the consumer, not the infrastructure
2. Simplify the consumer that doesn't need the feature
3. Preserve the infrastructure for consumers that do

**Key grep before template/infrastructure changes:**
```bash
grep -r '--template\|--inject-docs\|FEATURE_FLAG' skills/ commands/ --include='*.md'
```

## Combined Checklist

Before any rename, delete, or simplification:
1. Grep for ALL references across active code (skills, commands, hooks, scripts, tests)
2. Check for multiple consumers of shared infrastructure
3. Update hardcoded counts in all locations (README, AGENTS.md, CLAUDE.md, plugin.json, tests, validation scripts)
4. Verify test assertions include both the numeric value AND the error message string
5. Leave historical records (docs/research, knowledge entries) untouched
6. Run `git mv` cleanup: verify old files are actually gone (`rm -f` explicit cleanup after `git mv`)
