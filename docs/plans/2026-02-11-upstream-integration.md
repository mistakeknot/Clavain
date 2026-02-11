# Upstream Integration Plan

**Date:** 2026-02-11
**Beads:** Clavain-zkds (P1), Clavain-dbh7 (P2, DONE), Clavain-w219 (P2), Clavain-c9gv (P3), Clavain-fg41 (P3), Clavain-khpo (P3)

## Overview

Integrate 5 upstream improvements (1 already done). Ordered by priority and dependency.

---

## Task 1: Context Budget Audit (Clavain-zkds, P1)

Add `disable-model-invocation: true` to 13 commands and 8 skills that are manual-invocation-only.

### 1.1 Add flag to 13 commands

For each file, add `disable-model-invocation: true` after the `description:` line in frontmatter:

```
commands/lfg.md
commands/brainstorm.md
commands/strategy.md
commands/work.md
commands/smoke-test.md
commands/fixbuild.md
commands/resolve.md
commands/setup.md
commands/upstream-sync.md
commands/compound.md
commands/model-routing.md
commands/clodex-toggle.md
commands/debate.md
```

**Do NOT add to** (auto-discovery): quality-gates, plan-review, review, flux-drive, interpeer, repro-first-debugging, migration-safety, smoke-test... wait, smoke-test IS manual. Keep these WITHOUT the flag: quality-gates, plan-review, review, flux-drive, interpeer, repro-first-debugging, migration-safety.

### 1.2 Add flag to 8 skills

```
skills/using-clavain/SKILL.md
skills/upstream-sync/SKILL.md
skills/beads-workflow/SKILL.md
skills/developing-claude-code-plugins/SKILL.md
skills/brainstorming/SKILL.md
skills/writing-plans/SKILL.md
skills/landing-a-change/SKILL.md
skills/writing-skills/SKILL.md
```

### 1.3 Verify

```bash
grep -rl 'disable-model-invocation' commands/ | wc -l  # expect 21
grep -rl 'disable-model-invocation' skills/*/SKILL.md | wc -l  # expect 9
uv run --project tests pytest tests/structural/ -q
```

---

## Task 2: Async SessionStart (Clavain-dbh7, ALREADY DONE)

hooks.json already has `"async": true` on SessionStart. Close bead, no work needed.

---

## Task 3: /triage-prs Command (Clavain-w219, P2)

### 3.1 Create `commands/triage-prs.md`

7-step PR backlog triage:
1. Detect repo context (gh repo view, branch, recent merges)
2. Gather PRs + issues in parallel (gh pr list, gh issue list, gh label list)
3. Batch PRs by theme (bugs, features, docs, stale)
4. Spawn parallel fd-* review agents per batch
5. Cross-reference Fixes/Closes issue mentions
6. Generate triage report (markdown table)
7. Walk through each PR: merge / comment / close / skip

Frontmatter: `disable-model-invocation: true`

### 3.2 Update counts and docs

- CLAUDE.md, AGENTS.md, README.md (table + count), plugin.json: commands count +1
- test_commands.py: expected count +1

---

## Task 4: /review-doc Command (Clavain-c9gv, P3)

### 4.1 Create `commands/review-doc.md`

Lightweight single-pass document refinement:
1. Read the target document
2. Assess — unclear, unnecessary, missing sections
3. Score — Clarity/Completeness/Specificity/YAGNI (1-5)
4. Identify the single most critical issue
5. Fix — auto-fix minor issues, ask for substantive changes
6. Offer: refine again (max 2 rounds) or proceed

Frontmatter: `disable-model-invocation: true`

### 4.2 Update /lfg optional step

Add note in lfg.md after brainstorm: "Optionally run `/review-doc` to polish output before `/strategy`."

### 4.3 Update counts and docs

- All count locations +1
- README commands table: add row

---

## Task 5: Swarm Patterns (Clavain-fg41, P3)

### 5.1 Update `skills/dispatching-parallel-agents/SKILL.md`

Add "Orchestration Patterns" section with 3 patterns:
- **Parallel Specialists** — independent tasks via multiple Task tool calls in one message
- **Pipeline** — sequential handoff (agent N output feeds agent N+1)
- **Fan-out/Fan-in** — dispatch N agents, collect results, synthesize

### 5.2 Update `commands/lfg.md`

At execute step: "When plan has independent modules, dispatch in parallel using `dispatching-parallel-agents` skill."
At quality-gates + resolve: "These can overlap — quality-gates spawns review agents while resolve addresses known findings."

---

## Task 6: Dolt Docs (Clavain-khpo, P3)

### 6.1 Update AGENTS.md

In beads/bd section, note Dolt as default backend, JSONL for git portability, SQLite removed.

### 6.2 Update `skills/beads-workflow/SKILL.md`

Add backend note: bd init creates Dolt DB, .beads/dolt/ is gitignored, .beads/issues.jsonl is sync layer, bd doctor --fix --source=jsonl rebuilds from JSONL.

---

## Final Steps

After all tasks:
1. Run full test suite: `uv run --project tests pytest tests/structural/ -q && bats tests/shell/`
2. Close all beads: `bd close Clavain-zkds Clavain-dbh7 Clavain-w219 Clavain-c9gv Clavain-fg41 Clavain-khpo`
3. Commit, bump version, push, publish
