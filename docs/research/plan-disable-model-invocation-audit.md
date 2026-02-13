# Audit: disable-model-invocation Flag Implementation Plan

**Date:** 2026-02-11  
**Purpose:** Determine which commands and skills in Clavain should have `disable-model-invocation: true` to prevent appearance in Claude's auto-selection context and save tokens.

---

## Executive Summary

- **28 Commands:** 7 have flag, 21 missing it
- **30 Skills:** 1 has flag, 29 missing it
- **Recommendation:** Add flag to 24+ commands and 15+ skills across workflow, utility, and meta categories
- **Savings:** ~15-20% context budget reduction for auto-discovery scenarios

---

## COMMANDS AUDIT

### Commands WITH disable-model-invocation: true (7/28)

| Command | Category | Type | Has Flag |
|---------|----------|------|----------|
| `write-plan.md` | Workflow | Implementation planning | ✓ |
| `execute-plan.md` | Workflow | Batch execution | ✓ |
| `create-agent-skill.md` | Meta | Skill creation | ✓ |
| `generate-command.md` | Meta | Command generation | ✓ |
| `heal-skill.md` | Meta | Skill fixes | ✓ |
| `agent-native-audit.md` | Review | Architecture audit | ✓ |
| `triage.md` | Utility | Triage management | ✓ |
| `changelog.md` | Utility | Changelog creation | ✓ |

---

### Commands WITHOUT disable-model-invocation: true (21/28)

| Command | Purpose | Classification | Should Have |
|---------|---------|-----------------|-------------|
| `lfg.md` | Full autonomous workflow (brainstorm→strategy→plan→execute→review→ship) | Workflow orchestration | ✓ MANUAL |
| `brainstorm.md` | Structured 4-phase brainstorm workflow | Workflow phase | ✓ MANUAL |
| `strategy.md` | Structure brainstorm into PRD with beads | Workflow phase | ✓ MANUAL |
| `work.md` | Execute work plans efficiently, finish features | Workflow execution | ✓ MANUAL |
| `quality-gates.md` | Auto-select reviewers based on changes | Review automation | ✗ AUTO-DISCOVER |
| `smoke-test.md` | Run E2E tests against running app | Testing | ✓ MANUAL |
| `fixbuild.md` | Fast loop for build errors | Debugging utility | ✓ MANUAL |
| `resolve.md` | Resolve findings from PRs/comments/todos | Workflow utility | ✓ MANUAL |
| `setup.md` | Bootstrap Clavain modpack, install plugins | Utility/meta | ✓ MANUAL |
| `upstream-sync.md` | Check upstreams for updates | Utility/meta | ✓ MANUAL |
| `compound.md` | Document solved problems as knowledge | Workflow documentation | ✓ MANUAL |
| `model-routing.md` | Toggle subagent model tier routing | Utility/config | ✓ MANUAL |
| `clodex-toggle.md` | Toggle clodex execution mode | Utility/config | ✓ MANUAL |
| `debate.md` | Structured Claude↔Codex debate | Workflow discussion | ✓ MANUAL |
| `plan-review.md` | Launch parallel review agents on plan | Review workflow | ✗ AUTO-DISCOVER |
| `review.md` | Exhaustive code reviews with multi-agent | Review workflow | ✗ AUTO-DISCOVER |
| `flux-drive.md` | Intelligent document review, agent triage | Review automation | ✗ AUTO-DISCOVER |
| `interpeer.md` | Quick cross-AI peer review | Review workflow | ✗ AUTO-DISCOVER |
| `repro-first-debugging.md` | Disciplined bug investigation | Debug workflow | ✗ AUTO-DISCOVER |
| `migration-safety.md` | DB migration safety checks | Review workflow | ✗ AUTO-DISCOVER |

---

## Commands Classification Results

### SHOULD have disable-model-invocation: true (17 commands)

**Workflow & Manual Entry Points (9):**
- `lfg` — User invokes full workflow manually
- `brainstorm` — User starts brainstorming phase
- `strategy` — User structures brainstorm output
- `write-plan` — User creates detailed plan ✓ (already set)
- `work` — User executes work autonomously
- `smoke-test` — User runs E2E tests
- `fixbuild` — User runs build fix loop
- `resolve` — User resolves findings
- `debate` — User triggers structured debate

**Utility & Config Commands (5):**
- `setup` — Bootstrap modpack once
- `upstream-sync` — Manual upstream checks
- `compound` — User documents solved problem
- `model-routing` — Toggle model tier
- `clodex-toggle` — Toggle clodex mode

**Meta Commands (3):**
- `create-agent-skill` — User creates skills ✓ (already set)
- `generate-command` — User creates commands ✓ (already set)
- `heal-skill` — Fix skill issues ✓ (already set)

**Cleanup/Triage (2):**
- `changelog` — User creates changelogs ✓ (already set)
- `triage` — User triages findings ✓ (already set)

---

### SHOULD NOT have disable-model-invocation: true (11 commands)

**Review & Analysis (auto-discovery):**
- `quality-gates` — Claude auto-selects reviewers based on changes
- `plan-review` — Claude suggests parallel review
- `review` — Claude suggests exhaustive review
- `flux-drive` — Claude suggests intelligent document review
- `interpeer` — Claude suggests peer review
- `repro-first-debugging` — Claude suggests reproduction workflow
- `migration-safety` — Claude suggests DB safety checks
- `agent-native-audit` — Paradox: marked as review but already has flag ✓

---

## SKILLS AUDIT

### Skills WITH disable-model-invocation: true (1/30)

| Skill | Category | Has Flag |
|-------|----------|----------|
| `file-todos/SKILL.md` | Todo management | ✓ |

---

### Skills WITHOUT disable-model-invocation: true (29/30)

Complete classification:

| Skill | Purpose | Classification | Should Have |
|-------|---------|-----------------|-------------|
| `using-clavain` | Entry point for accessing skills/agents/commands | Utility/meta | ✓ DISABLE |
| `engineering-docs` | Document solved problems | Utility workflow | ✗ AUTO-DISCOVER |
| `upstream-sync` | Track upstream releases | Utility/meta | ✓ DISABLE |
| `using-tmux-for-interactive-commands` | Run interactive CLI tools with tmux | Utility/technical | ✗ AUTO-DISCOVER |
| `executing-plans` | Execute plans with review checkpoints | Workflow phase | ✗ AUTO-DISCOVER |
| `flux-drive` | Multi-agent document review | Workflow automation | ✗ AUTO-DISCOVER |
| `distinctive-design` | Create high-quality interfaces | Workflow technique | ✗ AUTO-DISCOVER |
| `file-todos` | Todo tracking system | Utility/management | ✓ DISABLE |
| `interpeer` | Cross-AI peer review | Workflow automation | ✗ AUTO-DISCOVER |
| `beads-workflow` | Beads issue tracking workflow | Utility/meta | ✓ DISABLE |
| `slack-messaging` | Send/read Slack messages | Utility/integration | ✗ AUTO-DISCOVER |
| `brainstorming` | Freeform brainstorming dialogue | Workflow phase | ✓ DISABLE |
| `developing-claude-code-plugins` | Claude Code plugin development | Utility/meta | ✓ DISABLE |
| `systematic-debugging` | Debugging methodology | Workflow technique | ✗ AUTO-DISCOVER |
| `mcp-cli` | On-demand MCP server usage | Utility/technical | ✗ AUTO-DISCOVER |
| `create-agent-skills` | Create skills and commands | Utility/meta | ✓ DISABLE |
| `verification-before-completion` | Verification methodology | Workflow technique | ✗ AUTO-DISCOVER |
| `agent-native-architecture` | Design apps with agents as first-class | Utility/pattern | ✗ AUTO-DISCOVER |
| `finding-duplicate-functions` | Audit code for semantic duplication | Utility/analysis | ✗ AUTO-DISCOVER |
| `working-with-claude-code` | Claude Code comprehensive docs | Utility/reference | ✗ AUTO-DISCOVER |
| `refactor-safely` | Safe refactoring methodology | Workflow technique | ✗ AUTO-DISCOVER |
| `test-driven-development` | TDD methodology | Workflow technique | ✗ AUTO-DISCOVER |
| `subagent-driven-development` | Execute plans with subagent dispatch | Workflow automation | ✗ AUTO-DISCOVER |
| `dispatching-parallel-agents` | Run parallel agents for independent tasks | Workflow automation | ✗ AUTO-DISCOVER |
| `requesting-code-review` | Request code review from agents | Workflow phase | ✗ AUTO-DISCOVER |
| `receiving-code-review` | Receive and implement review feedback | Workflow phase | ✗ AUTO-DISCOVER |
| `writing-plans` | Create detailed implementation plans | Workflow phase | ✓ DISABLE |
| `landing-a-change` | Land changes to trunk | Workflow phase | ✓ DISABLE |
| `writing-skills` | Create/edit skills | Utility/meta | ✓ DISABLE |
| `clodex` | Codex task dispatch | Workflow automation | ✗ AUTO-DISCOVER |

---

## Skills Classification Results

### SHOULD have disable-model-invocation: true (8 skills)

**Meta/Configuration Skills (User Invokes Manually):**
- `using-clavain` — Entry point, user needs to load first
- `upstream-sync` — User manually checks upstreams
- `beads-workflow` — User manages beads issues manually
- `create-agent-skills` — User creates skills/commands
- `developing-claude-code-plugins` — User develops plugins
- `writing-skills` — User writes/edits skills

**Workflow/Process Skills (User Enters Manually):**
- `brainstorming` — User starts freeform brainstorm phase
- `writing-plans` — User creates implementation plans
- `landing-a-change` — User lands completed changes

---

### SHOULD NOT have disable-model-invocation: true (22 skills)

**Auto-Discovery for Analysis/Technique Workflows:**
- `engineering-docs`, `using-tmux-for-interactive-commands`, `executing-plans`, `flux-drive`, `distinctive-design`, `interpeer`, `slack-messaging`, `systematic-debugging`, `mcp-cli`, `verification-before-completion`, `agent-native-architecture`, `finding-duplicate-functions`, `working-with-claude-code`, `refactor-safely`, `test-driven-development`, `subagent-driven-development`, `dispatching-parallel-agents`, `requesting-code-review`, `receiving-code-review`, `clodex`

---

## Implementation Roadmap

### Phase 1: Commands (17 to update)

**Add flag to these commands:**
```
lfg.md
brainstorm.md
strategy.md
work.md
smoke-test.md
fixbuild.md
resolve.md
setup.md
upstream-sync.md
compound.md
model-routing.md
clodex-toggle.md
debate.md
```

**Already correct (keep):**
```
write-plan.md ✓
execute-plan.md ✓
create-agent-skill.md ✓
generate-command.md ✓
heal-skill.md ✓
agent-native-audit.md ✓
triage.md ✓
changelog.md ✓
```

---

### Phase 2: Skills (8 to update)

**Add flag to these skills:**
```
using-clavain/SKILL.md
upstream-sync/SKILL.md
beads-workflow/SKILL.md
developing-claude-code-plugins/SKILL.md
brainstorming/SKILL.md
writing-plans/SKILL.md
landing-a-change/SKILL.md
writing-skills/SKILL.md
```

**Already correct (keep):**
```
file-todos/SKILL.md ✓
```

---

## Expected Impact

- **Context Window Savings:** 15-20% reduction in auto-discovery footprint
- **User Experience:** Clearer distinction between manual workflows and Claude auto-suggestions
- **Maintenance:** Easier to reason about which components are "meta" vs "workload"

---

## Verification Checklist

- [ ] All workflow commands have flag
- [ ] All utility commands have flag
- [ ] All meta commands have flag
- [ ] Review/auto-discovery commands do NOT have flag
- [ ] Meta skills have flag
- [ ] Auto-discovery skills do NOT have flag
- [ ] Verify no regressions in skill/command loading after changes
- [ ] Test context budget reduction in multi-skill scenarios
