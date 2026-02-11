# Audit: Overwritten Clavain Customizations After Upstream Sync

**Date:** 2026-02-10
**Scope:** Check synced files for upstream namespace references, deleted agent/command references, and compound-engineering-specific content that should not be in Clavain.

---

## Summary

**Issues found: 10** (3 critical, 5 moderate, 2 informational)

The most significant problems are concentrated in two files:
- `commands/lfg.md` — heavily contaminated with compound-engineering namespace references and references to non-existent external plugins
- `agents/research/learnings-researcher.md` — contains Rails/Every.to-specific component values and a broken reference to a deleted skill

The core agent, skill, and command files are clean. The fd-* consolidation namespace changes held. No "superpowers:" or "compound-engineering:" namespace prefixes were found in any agent or skill content.

---

## 1. Namespace References

### Search: "superpowers", "compound-engineering", "compound_engineering", "EveryInc" in agents/, commands/, skills/

#### CRITICAL: `commands/lfg.md`

| Line | Problematic Text | Should Be |
|------|------------------|-----------|
| 10 | `/ralph-wiggum:ralph-loop "finish all slash commands" --completion-promise "DONE"` | Remove or replace with Clavain-native equivalent (no `ralph-wiggum` plugin in Clavain) |
| 12 | `/compound-engineering:deepen-plan` | `/clavain:deepen-plan` or remove (skill does not exist in Clavain) |
| 15 | `/compound-engineering:resolve_todo_parallel` | `/clavain:resolve` (consolidated command) |
| 16 | `/compound-engineering:test-browser` | Remove (browser-automation is excluded from Clavain per design decisions) |
| 17 | `/compound-engineering:feature-video` | Remove (not a Clavain capability) |

**Verdict:** `lfg.md` is entirely a compound-engineering workflow and references 5 external plugin namespaces/commands. It appears to have been synced directly from compound-engineering without any adaptation. Steps 2, 4, 5 reference `/workflows:plan`, `/workflows:work`, `/workflows:review` which are not Clavain skills either.

**Full file contents for reference:**
```markdown
---
name: lfg
description: Full autonomous engineering workflow
argument-hint: "[feature description]"
disable-model-invocation: true
---

Run these slash commands in order. Do not do anything else.

1. `/ralph-wiggum:ralph-loop "finish all slash commands" --completion-promise "DONE"`
2. `/workflows:plan $ARGUMENTS`
3. `/compound-engineering:deepen-plan`
4. `/workflows:work`
5. `/workflows:review`
6. `/compound-engineering:resolve_todo_parallel`
7. `/compound-engineering:test-browser`
8. `/compound-engineering:feature-video`
9. Output `<promise>DONE</promise>` when video is in PR

Start with step 1 now.
```

#### MODERATE: `commands/agent-native-audit.md` (line 30)

| Line | Problematic Text | Should Be |
|------|------------------|-----------|
| 30 | `/compound-engineering:agent-native-architecture` | `/clavain:agent-native-architecture` |

The rest of the file is clean and well-adapted. Only this one namespace reference was missed.

#### MODERATE: `commands/upstream-sync.md` (lines 3, 78-81)

| Line | Text | Assessment |
|------|------|------------|
| 3 | `description: Check upstream repos (beads, oracle, agent-mail, superpowers, compound-engineering)` | **Acceptable** — these are actual upstream repo names, not namespace references |
| 78-81 | Table listing superpowers, superpowers-lab, superpowers-dev, compound-engineering | **Acceptable** — upstream tracking table correctly lists source repos |

**Verdict:** These references are legitimate — they describe upstream repositories, not plugin namespaces. No changes needed.

---

## 2. Deleted Agent References

### Search: architecture-strategist, code-simplicity-reviewer, deployment-verification-agent, python-reviewer, typescript-reviewer, pattern-recognition-specialist, performance-oracle, security-sentinel, spec-flow-analyzer, go-reviewer, shell-reviewer, markdown-reviewer

**No issues found in agents/, commands/, or skills/ directories.**

References to deleted agents exist only in `config/flux-drive/knowledge/` files, where they are historical evidence in knowledge entries:
- `config/flux-drive/knowledge/agent-merge-accountability.md` (line 7): References `architecture-strategist` in historical context describing the fd-v2 merge
- `config/flux-drive/knowledge/agent-description-example-blocks-required.md` (line 7): References `architecture-strategist, security-sentinel` as historical comparison

**Verdict:** These are appropriate historical references in knowledge files documenting past decisions. No changes needed.

---

## 3. Deleted Command References

### Search: resolve-parallel, resolve-pr-parallel, resolve-todo-parallel, plan_review, resolve_parallel

**No direct references found in agents/, commands/, or skills/ directories.**

The only reference to a deleted command pattern is in `commands/lfg.md` line 15 (`/compound-engineering:resolve_todo_parallel`), already flagged in Section 1 above.

---

## 4. Plugin-Specific References (Every.to, Rails, Ruby, etc.)

### CRITICAL: `agents/research/learnings-researcher.md`

This file contains compound-engineering/Every.to-specific content that doesn't apply to a general-purpose plugin:

| Line | Problematic Text | Issue |
|------|------------------|-------|
| 156 | `Reference the [yaml-schema.md](../../skills/compound-docs/references/yaml-schema.md)` | **Broken link** — `skills/compound-docs/` does not exist in Clavain. This was a compound-engineering-specific skill. |
| 165 | `rails_model, rails_controller, rails_view, service_object` | **Rails-specific** component values in the schema reference |
| 166 | `frontend_stimulus, hotwire_turbo` | **Rails/Hotwire-specific** component values |
| 167 | `email_processing, brief_system` | **Every.to-specific** — "brief_system" is an Every.to product concept |
| 261 | `/deepen-plan` | References a command that does not exist in Clavain |

**Verdict:** The entire "Frontmatter Schema Reference" section (lines 154-176) is compound-engineering-specific and references Rails/Hotwire component types from the Every.to codebase. The file's core search strategy (Steps 1-7) is general-purpose and valid, but the schema reference section needs to be generalized or removed.

### Search: "Every.to", "EveryInc", "Rails", "Ruby", "dspy-ruby", "figma", "Xcode", "deploy-docs", "DHH", "Kieran" in agents/, commands/, skills/

**No other issues found.** All references to "Every.to", "EveryInc", and "Kieran" are in appropriate contexts:
- `README.md` — attribution credits (appropriate)
- `AGENTS.md` — upstream source attribution and design decision documentation (appropriate)
- `upstreams.json`, `scripts/` — upstream repository URLs (appropriate)
- `docs/research/` — research documents (appropriate)

---

## 5. Skill Cross-References

### CRITICAL: `commands/lfg.md`

As detailed in Section 1, this file references skills/commands from three non-Clavain plugins:
- `ralph-wiggum:ralph-loop` — external plugin
- `workflows:plan`, `workflows:work`, `workflows:review` — external plugin
- `compound-engineering:deepen-plan`, `compound-engineering:resolve_todo_parallel`, `compound-engineering:test-browser`, `compound-engineering:feature-video` — compound-engineering namespace

None of these are available in Clavain.

### MODERATE: `agents/research/learnings-researcher.md` (line 261)

| Line | Text | Issue |
|------|------|-------|
| 261 | `- /deepen-plan - To add depth with relevant learnings` | `/deepen-plan` does not exist as a Clavain command or skill |

---

## Consolidated Issue List

### Critical (must fix — references to non-existent commands/skills)

1. **`/root/projects/Clavain/commands/lfg.md`** — Entire file is compound-engineering-specific. All 9 steps reference non-Clavain plugins. Must be rewritten for Clavain namespace or removed.

2. **`/root/projects/Clavain/commands/agent-native-audit.md` line 30** — `/compound-engineering:agent-native-architecture` should be `/clavain:agent-native-architecture`

3. **`/root/projects/Clavain/agents/research/learnings-researcher.md` line 156** — Broken link to `skills/compound-docs/references/yaml-schema.md` (skill does not exist in Clavain)

### Moderate (should fix — domain-specific content in general-purpose plugin)

4. **`/root/projects/Clavain/agents/research/learnings-researcher.md` lines 165-167** — Rails/Hotwire/Every.to-specific component values (`rails_model`, `rails_controller`, `rails_view`, `frontend_stimulus`, `hotwire_turbo`, `brief_system`)

5. **`/root/projects/Clavain/agents/research/learnings-researcher.md` line 261** — References `/deepen-plan` which does not exist in Clavain

6. **`/root/projects/Clavain/agents/research/learnings-researcher.md` lines 9-25** — Example blocks reference Every.to-specific concepts ("brief system", "Brief generation"), but these are generic enough to serve as illustrations

### Informational (acceptable as-is)

7. **`/root/projects/Clavain/commands/upstream-sync.md` lines 78-81** — References to "superpowers" and "compound-engineering" are legitimate upstream repo names, not namespace references

8. **`/root/projects/Clavain/config/flux-drive/knowledge/*.md`** — Historical references to deleted agents are appropriate in knowledge files documenting past decisions

---

## Clean Areas (no issues found)

- `agents/review/*.md` — All fd-* agents clean, no stale references
- `agents/workflow/*.md` — Clean
- `skills/agent-native-architecture/` — Clean
- `skills/create-agent-skills/` — Clean
- `skills/file-todos/` — Clean
- `hooks/` — Clean, no upstream namespace leaks
- `.claude-plugin/plugin.json` — Clean, namespace is "clavain"
- `config/flux-drive/knowledge/` — Historical references only (appropriate)

---

## Recommended Actions

1. **Rewrite or remove `commands/lfg.md`** — Replace compound-engineering workflow with Clavain-native equivalent, or delete if no Clavain equivalent exists for the referenced commands
2. **Fix namespace in `commands/agent-native-audit.md`** — Change `/compound-engineering:agent-native-architecture` to `/clavain:agent-native-architecture`
3. **Fix or remove schema reference in `agents/research/learnings-researcher.md`** — Remove the broken `compound-docs` link and generalize the component values to remove Rails/Hotwire/Every.to-specific terms
4. **Update `/deepen-plan` reference** — Either create a `deepen-plan` command in Clavain or remove the reference from `learnings-researcher.md`
