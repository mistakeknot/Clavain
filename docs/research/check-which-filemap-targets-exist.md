# FileMap Target Existence Check (2026-02-10)

**Working Directory:** `/root/projects/Clavain`  
**Analysis Date:** 2026-02-10  
**Method:** Python3 script parsing `upstreams.json` and checking filesystem existence

## Executive Summary

Of 7 upstreams configured in `upstreams.json`, **5 have missing fileMap targets**:
- **compound-engineering**: 15 missing targets
- **oracle**: 11 missing targets
- **beads**: 5 missing targets
- **mcp-agent-mail**: 10 missing targets
- **superpowers**: 2 missing targets

**superpowers-lab** and **superpowers-dev** have all targets present.

Total: **43 missing targets** across all upstreams (all are SOURCE files in the upstream repos, not local files).

---

## BEADS

**Status:** 5 missing targets (0 found)

These are source files in the upstream beads repo that haven't been cloned locally:

```
MISSING:
  - claude-plugin/skills/beads/SKILL.md
    → maps to: skills/beads-workflow/SKILL.md
  
  - claude-plugin/skills/beads/README.md
    → maps to: skills/beads-workflow/references/upstream-readme.md
  
  - claude-plugin/skills/beads/CLAUDE.md
    → maps to: skills/beads-workflow/references/upstream-claude.md
  
  - claude-plugin/skills/beads/resources/*
    → maps to: skills/beads-workflow/references/*
  
  - claude-plugin/skills/beads/adr/*
    → maps to: skills/beads-workflow/references/adr/*
```

**Root Cause:** These are source files in `/root/projects/upstreams/beads/` (the cloned upstream), not local Clavain files. The fileMap defines how to copy them into Clavain when syncing.

---

## ORACLE

**Status:** 11 missing targets (1 found)

Source files in upstream oracle repo:

```
MISSING:
  - skills/oracle/SKILL.md
    → maps to: skills/interpeer/references/oracle-reference.md
  
  - docs/browser-mode.md
    → maps to: skills/interpeer/references/oracle-docs/browser-mode.md
  
  - docs/configuration.md
    → maps to: skills/interpeer/references/oracle-docs/configuration.md
  
  - docs/debug/remote-chrome.md
    → maps to: skills/interpeer/references/oracle-docs/debug/remote-chrome.md
  
  - docs/gemini.md
    → maps to: skills/interpeer/references/oracle-docs/gemini.md
  
  - docs/linux.md
    → maps to: skills/interpeer/references/oracle-docs/linux.md
  
  - docs/mcp.md
    → maps to: skills/interpeer/references/oracle-docs/mcp.md
  
  - docs/multimodel.md
    → maps to: skills/interpeer/references/oracle-docs/multimodel.md
  
  - docs/openai-endpoints.md
    → maps to: skills/interpeer/references/oracle-docs/openai-endpoints.md
  
  - docs/openrouter.md
    → maps to: skills/interpeer/references/oracle-docs/openrouter.md
  
  - docs/testing/mcp-smoke.md
    → maps to: skills/interpeer/references/oracle-docs/testing/mcp-smoke.md

FOUND:
  - README.md (exists locally — upstream root)
```

**Root Cause:** Oracle upstream files not present in `/root/projects/upstreams/oracle/`. These would be pulled during sync.

---

## MCP-AGENT-MAIL

**Status:** 10 missing targets (1 found)

Source files in mcp_agent_mail upstream repo:

```
MISSING:
  - SKILL.md
    → maps to: skills/agent-mail-coordination/SKILL.md
  
  - codex.mcp.json
    → maps to: skills/agent-mail-coordination/references/codex.mcp.json
  
  - scripts/integrate_codex_cli.sh
    → maps to: skills/agent-mail-coordination/references/integrate_codex_cli.sh
  
  - scripts/hooks/check_inbox.sh
    → maps to: skills/agent-mail-coordination/references/hooks/check_inbox.sh
  
  - scripts/hooks/codex_notify.sh
    → maps to: skills/agent-mail-coordination/references/hooks/codex_notify.sh
  
  - docs/GUIDE_TO_OPTIMAL_MCP_SERVER_DESIGN.md
    → maps to: skills/agent-mail-coordination/references/server-design-guide.md
  
  - docs/observability.md
    → maps to: skills/agent-mail-coordination/references/observability.md
  
  - docs/operations_alignment_checklist.md
    → maps to: skills/agent-mail-coordination/references/operations-alignment-checklist.md
  
  - docs/adr/*
    → maps to: skills/agent-mail-coordination/references/adr/*
  
  - docs/deployment_samples/*
    → maps to: skills/agent-mail-coordination/references/deployment_samples/*

FOUND:
  - README.md
```

**Root Cause:** Upstream files in `/root/projects/upstreams/mcp-agent-mail/` not present. Will be synced.

---

## SUPERPOWERS

**Status:** 2 missing targets (25 found)

**Most targets are present** — only 2 mismatches in the fileMap configuration:

```
MISSING:
  - skills/using-superpowers/SKILL.md
    → maps to: skills/using-clavain/SKILL.md
    NOTE: This is a NAMESPACE RENAME. Local file exists as using-clavain (superpowers → clavain).
    The fileMap source path is outdated.
  
  - agents/code-reviewer.md
    → maps to: agents/review/plan-reviewer.md
    NOTE: This is a RESTRUCTURE. The agent was moved into agents/review/ subdirectory.
    The fileMap source path is outdated.

FOUND (sample of 25 total):
  - skills/brainstorming/SKILL.md
  - skills/dispatching-parallel-agents/SKILL.md
  - skills/executing-plans/SKILL.md
  - skills/receiving-code-review/SKILL.md
  - skills/requesting-code-review/SKILL.md
  - ... (20 more)
```

**Analysis:** These are known mapping issues documented in MEMORY.md:
- `using-superpowers/SKILL.md` was renamed to `using-clavain/SKILL.md` in Clavain during namespace consolidation
- `agents/code-reviewer.md` was moved to `agents/review/plan-reviewer.md` as part of the 3-layer routing restructure

**Action:** Update fileMap in upstreams.json to reflect local paths, not upstream paths.

---

## SUPERPOWERS-LAB

**Status:** 0 missing targets (4 found)

All fileMap targets exist locally:

```
FOUND:
  - skills/finding-duplicate-functions/SKILL.md
  - skills/mcp-cli/SKILL.md
  - skills/slack-messaging/SKILL.md
  - skills/using-tmux-for-interactive-commands/SKILL.md
```

---

## SUPERPOWERS-DEV

**Status:** 0 missing targets (7 found)

All fileMap targets exist locally:

```
FOUND:
  - skills/developing-claude-code-plugins/SKILL.md
  - skills/developing-claude-code-plugins/references/common-patterns.md
  - skills/developing-claude-code-plugins/references/plugin-structure.md
  - skills/developing-claude-code-plugins/references/polyglot-hooks.md
  - skills/developing-claude-code-plugins/references/troubleshooting.md
  - ... (2 more)
```

---

## COMPOUND-ENGINEERING

**Status:** 15 missing targets (23 found)

These are UPSTREAM source files (in `/root/projects/upstreams/compound-engineering/plugins/compound-engineering/`), most are agent and command files that don't exist in that upstream:

```
MISSING (Agent files - NOT present in compound-engineering upstream):
  - agents/review/architecture-strategist.md
    → maps to: agents/review/architecture-strategist.md
  
  - agents/review/code-simplicity-reviewer.md
    → maps to: agents/review/code-simplicity-reviewer.md
  
  - agents/review/data-integrity-guardian.md
    → maps to: agents/review/data-integrity-reviewer.md
  
  - agents/review/deployment-verification-agent.md
    → maps to: agents/review/deployment-verification-agent.md
  
  - agents/review/kieran-python-reviewer.md
    → maps to: agents/review/python-reviewer.md
  
  - agents/review/kieran-typescript-reviewer.md
    → maps to: agents/review/typescript-reviewer.md
  
  - agents/review/pattern-recognition-specialist.md
    → maps to: agents/review/pattern-recognition-specialist.md
  
  - agents/review/performance-oracle.md
    → maps to: agents/review/performance-oracle.md
  
  - agents/review/security-sentinel.md
    → maps to: agents/review/security-sentinel.md
  
  - agents/workflow/spec-flow-analyzer.md
    → maps to: agents/workflow/spec-flow-analyzer.md

MISSING (Command files - NOT present in compound-engineering upstream):
  - commands/generate_command.md
    → maps to: commands/generate-command.md
  
  - commands/plan_review.md
    → maps to: commands/plan-review.md
  
  - commands/resolve_parallel.md
    → maps to: commands/resolve-parallel.md
  
  - commands/resolve_pr_parallel.md
    → maps to: commands/resolve-pr-parallel.md
  
  - commands/resolve_todo_parallel.md
    → maps to: commands/resolve-todo-parallel.md

FOUND (sample of 23 total):
  - skills/agent-native-architecture/SKILL.md
  - skills/create-agent-skills/SKILL.md
  - skills/requesting-architecture-review/SKILL.md
  - ... (20 more)
```

**Analysis:** The 15 missing entries are NOT FILES THAT SHOULD EXIST in the upstream. They represent:

1. **Clavain-local agents** created during consolidation (fd-* agents, etc.)
2. **Clavain-local commands** not present in compound-engineering
3. **Clavain renames** (data-integrity-guardian → data-integrity-reviewer, kieran-* agent renames)

These fileMap entries are **stale/incorrect** — they were created during the initial sync setup but represent files that Clavain owns (not compound-engineering).

**Recommendation:** Review and **remove invalid fileMap entries** for agents/commands that don't exist in compound-engineering upstream. Keep only the ones that actually sync down (the 23 found items are the legitimate syncs).

---

## Key Findings

### Pattern 1: Upstream Clone Files (beads, oracle, mcp-agent-mail)

The "missing" files for these upstreams are **source files in the upstream clones**, not local Clavain files:
- `/root/projects/upstreams/beads/claude-plugin/skills/beads/SKILL.md` (upstream file)
- `/root/projects/upstreams/oracle/docs/browser-mode.md` (upstream file)
- `/root/projects/upstreams/mcp_agent_mail/SKILL.md` (upstream file)

These are **expected to be missing** if the upstream hasn't been cloned yet. The fileMap defines how to copy them when syncing. Not an issue.

### Pattern 2: Clavain-Local Namespace Consolidation (superpowers)

Two mapping mismatches reflect local changes:
- `using-superpowers` → `using-clavain` (namespace rename)
- `agents/code-reviewer.md` → `agents/review/plan-reviewer.md` (structural move)

**Action:** Update superpowers fileMap entries to point to local paths.

### Pattern 3: Invalid Compound-Engineering FileMap (15 entries)

The compound-engineering fileMap includes **15 agents and commands that don't exist** in the upstream repo. These are Clavain-local creations (fd-* agents, command renames, etc.).

**Action:** Remove these from compound-engineering fileMap. They bloat the configuration and signal false sync expectations.

---

## Recommendations

### 1. Fix superpowers FileMap (2 entries)

Update in `upstreams.json`:
```json
{
  "name": "superpowers",
  "fileMap": {
    "skills/using-superpowers/SKILL.md": "skills/using-clavain/SKILL.md",  // Keep as-is (rename)
    "agents/code-reviewer.md": "agents/review/plan-reviewer.md"  // Already renamed locally
    // ... other entries unchanged
  }
}
```

Actually, this might be working as a one-way rename (copy upstream, rename on import). Verify with `/interpub:pull superpowers --diff`.

### 2. Clean up compound-engineering FileMap (remove 15 invalid entries)

These don't exist in the upstream:
- Remove all 9 agent mappings (architecture-strategist, security-sentinel, etc.)
- Remove all 5 command mappings (generate_command, plan_review, etc.)
- Remove spec-flow-analyzer

Keep only the ~23 legitimate skill/reference syncs.

### 3. Verify upstream clones exist

If upstreams don't have `.git/` clones under `/root/projects/upstreams/`:
- Run `scripts/clone-upstreams.sh` (one-time setup)
- Or run `scripts/pull-upstreams.sh --pull` to fetch all

---

## Test Verification

To test the actual sync behavior:
```bash
# See which files would be pulled from compound-engineering
scripts/pull-upstreams.sh --diff compound-engineering

# Dry-run the sync
./upstreams.json compound-engineering check
```

---

## Metadata

- **Config:** `/root/projects/Clavain/upstreams.json`
- **Upstreams Directory:** `/root/projects/upstreams/`
- **Python Script Used:** Inline parser reading JSON, checking `os.path.exists(target)` for each fileMap entry
- **Scope:** All 7 upstreams (beads, oracle, mcp-agent-mail, superpowers, superpowers-lab, superpowers-dev, compound-engineering)
