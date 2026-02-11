# Upstream Changes Research (2026-02-11)

Research of 8 specific upstream changes for potential Clavain integration.

---

## 1. superpowers `038abed` — Fix O(n^2) escape_for_json

### Change Summary
Replaced character-by-character loop (`${input:$i:1}`) with bash parameter substitution (`${s//old/new}`). The old implementation was O(n^2) due to substring copy overhead, causing 60+ second hangs on Windows Git Bash.

### Performance Impact
- **macOS**: 7x faster
- **Windows Git Bash**: Dramatically faster (60s → <1s)

### Clavain Status
**ALREADY INTEGRATED** ✓

Clavain's `/root/projects/Clavain/hooks/lib.sh` (lines 6-24) uses the optimized parameter substitution version. However, it includes additional control character escaping (lines 15-22) that upstream doesn't have:

```bash
# Clavain addition: Escape ASCII control chars 1-31 as \uXXXX
for i in {1..31}; do
    case "$i" in 8|9|10|12|13) continue ;;  # already handled
    esac
    printf -v ch "\\$(printf '%03o' "$i")"
    printf -v esc '\\u%04x' "$i"
    s="${s//$ch/$esc}"
done
```

This is a Clavain enhancement over the upstream fix.

### Recommendation
**SKIP** — Already integrated. Clavain's version is actually more comprehensive (handles control characters 1-31).

---

## 2. superpowers `961052e` — Async SessionStart Hook

### Change Summary
Runs SessionStart hook with `"async": true` in `hooks/hooks.json` to prevent Windows terminal freeze. The synchronous hook blocked TUI raw mode entry while the O(n^2) escape function ran.

### Technical Details
```json
{
  "type": "command",
  "command": "${CLAUDE_PLUGIN_ROOT}/hooks/session-start.sh",
  "async": true
}
```

### Clavain Status
**NOT ASYNC** — Clavain's `hooks/hooks.json` does not use `"async": true` on any hooks.

### Linux Relevance
Clavain runs on Linux (ethics-gradient server) where the performance issue is much less severe. However:
- Async hooks are a best practice for long-running startup operations
- Prevents blocking the TUI even on fast systems
- Makes session startup feel more responsive

### Recommendation
**INTEGRATE** — Add `"async": true` to session-start hook in `hooks/hooks.json`. Low-risk improvement that prevents any potential startup blocking.

---

## 3. compound-engineering `f744b79` — 79% Context Reduction

### Change Summary
Reduced plugin description character count from ~50,500 chars (316% of Claude Code's 16K limit) to ~10,400 chars (65%) by:

1. Trimming all 29 agent descriptions (moved examples to body)
2. Adding `disable-model-invocation: true` to 18 manual commands
3. Adding `disable-model-invocation: true` to 6 manual skills

### The Problem
Claude Code silently excludes components when plugins exceed the description budget. Components were being dropped without warning.

### The `disable-model-invocation` Pattern

**Frontmatter field:**
```yaml
---
name: triage-prs
description: Triage all open PRs with parallel agents
disable-model-invocation: true
---
```

**Effect:**
- Component is loaded and available for direct invocation (`/clavain:triage`)
- Component does NOT appear in Claude's tool selection context (saves tokens)
- User can still invoke it explicitly

**When to use:**
- Commands intended for manual invocation only (workflows, utilities)
- Skills that should only be loaded when explicitly needed
- Long documentation that doesn't need to be in every message context

### Clavain Status
**PARTIALLY ADOPTED** — Found 32 occurrences of `disable-model-invocation` in 17 files, but not systematically applied.

Files using it:
- `commands/heal-skill.md`, `changelog.md`, `triage.md`, `create-agent-skill.md`, `agent-native-audit.md`, `generate-command.md`, `execute-plan.md`, `write-plan.md`
- `skills/file-todos/SKILL.md`, `skills/create-agent-skills/SKILL.md`

### Current Plugin Size
No immediate size warning, but as Clavain grows (currently 16 agents, 33 skills, 28 commands), proactive trimming prevents future silent exclusions.

### Recommendation
**INTEGRATE SELECTIVELY** — Audit all commands and skills. Add `disable-model-invocation: true` to:
- Workflow commands (lfg, write-plan, execute-plan, strategy, quality-gates, resolve, ship, triage)
- Utility commands (heal-skill, changelog, generate-command, agent-native-audit)
- Manual-only skills (file-todos, create-agent-skills)

Keep OFF for:
- Core review agents (fd-*, plan-reviewer, agent-native-reviewer)
- Research agents (auto-compound learners)
- Skills Claude should discover organically (flux-drive, brainstorm, using-clavain)

---

## 4. compound-engineering `a5bba3d` — document-review Skill

### Change Summary
New skill for refining brainstorm/plan documents before proceeding to next workflow step. Applies structured review:

1. **Assess** — Identify unclear/unnecessary/unstated parts
2. **Evaluate** — Score against Clarity/Completeness/Specificity/YAGNI
3. **Identify Critical Issue** — Highlight the "must address" item
4. **Make Changes** — Auto-fix minor issues, ask approval for substantive changes
5. **Offer Next Action** — Refine again or complete (max 2 rounds recommended)

### Integration Points
- `/workflows:brainstorm` Step 4 offers "Review and refine"
- `/workflows:plan` post-generation offers "Review and refine" after technical review
- YAGNI-based simplification guidance

### Clavain Equivalent
Clavain has `/flux-drive` which performs multi-agent review with specialized agents (fd-architecture, fd-safety, fd-correctness, fd-quality, fd-user-product, fd-performance).

**Comparison:**

| Feature | document-review | flux-drive |
|---------|----------------|------------|
| **Approach** | Single-agent structured self-review | Multi-agent specialist review |
| **Depth** | Surface-level (clarity, completeness) | Deep domain analysis (security, performance, data integrity) |
| **Speed** | Fast (1 agent, ~30s) | Slower (6+ agents, parallel, 2-3 min) |
| **Use case** | Quick polish before planning | Comprehensive pre-execution gate |

### Recommendation
**ADAPT, DON'T COPY** — Clavain's flux-drive is more powerful for quality gates. However, the lightweight document-review pattern could be useful for:
- Quick post-brainstorm polish (before strategy phase)
- Plan refinement after Codex delegation (catch obvious issues fast)

If integrated:
- Position it as "quick review" vs flux-drive's "comprehensive review"
- Keep the YAGNI simplification guidance (aligns with Clavain's philosophy)
- Cap at 2 iterations like upstream

---

## 5. compound-engineering `e4ff6a8` — orchestrating-swarms Skill

### Change Summary
1,717-line comprehensive guide to multi-agent swarm orchestration using Claude Code's TeammateTool and Task system.

**Key content:**
- **Primitives**: Agent, Team, Teammate, Leader, Task, Inbox, Message, Backend (in-process, tmux, iterm2)
- **Lifecycle**: Create team → Create tasks → Spawn teammates → Work → Coordinate → Shutdown → Cleanup
- **Message flow**: Leader-teammate communication via JSON inboxes
- **Spawn backends**: Auto-detects environment (tmux splits, iTerm splits, in-process invisible)
- **Task dependencies**: Blocking, parent-child, milestone tracking
- **Orchestration patterns**: Map-reduce, pipeline, priority queue, self-organizing swarms

**Also includes `/slfg` command:**
Swarm-enabled LFG that parallelizes review + browser tests after work phase.

### Clavain Equivalent
Clavain has:
- **`/lfg`** — Sequential workflow (brainstorm → strategy → plan → flux-drive → execute → test → quality-gates → resolve → ship)
- **`dispatching-parallel-agents` skill** — 50-line guide focused on independent problem domains (test failures, subsystem bugs)

**Comparison:**

| Feature | orchestrating-swarms | dispatching-parallel-agents |
|---------|---------------------|----------------------------|
| **Size** | 1,717 lines | ~50 lines |
| **Scope** | Comprehensive TeammateTool reference | Tactical parallel dispatch pattern |
| **Use case** | Building swarm orchestration systems | Quick parallel bug investigation |
| **Examples** | Complete code snippets, message formats, backend setup | Conceptual "when to use" diagrams |

### Recommendation
**EXTRACT PATTERNS, NOT FULL SKILL** — The 1,717-line skill is comprehensive but overlaps heavily with official Claude Code docs. Instead:

1. **Keep `dispatching-parallel-agents` as-is** — It's lightweight and practical
2. **Extract key patterns from orchestrating-swarms:**
   - **Inbox message patterns** (shutdown_request, idle_notification)
   - **Task dependency chains** (milestone blocking, sequential gates)
   - **Spawn backend detection** (tmux vs in-process)
3. **Update `/lfg` with optional swarm mode:**
   - Add "Use swarm mode for parallel execution" flag
   - If enabled, parallelize Steps 6-7 (test suite + quality-gates)
   - Document in using-clavain skill

**Why not full integration:**
- Official TeammateTool docs are the authoritative source
- Clavain's approach is more sequential by design (flux-drive gates → execution → review)
- 1.7K lines would bloat the skill catalog

---

## 6. compound-engineering `4f4873f` — /triage-prs Command

### Change Summary
New command that triages all open PRs using parallel review agents:

1. **Gather context** (parallel): List PRs, issues, labels, recent merges
2. **Batch PRs by theme**: Group 4-6 PRs (bugs, features, docs, config, stale)
3. **Parallel review**: Spawn one agent per batch, each produces markdown table with description/label/action/related PRs
4. **Cross-reference issues**: Match PRs to `Fixes #X` / `Closes #X`
5. **Apply labels**: Bulk label PRs based on agent recommendations
6. **Generate report**: Grouped triage report by category
7. **Walk through one-by-one**: Ask user to merge/comment/close each PR

**Uses:**
- `gh pr list`, `gh pr view`, `gh pr diff`
- `gh issue list`
- `gh label list`
- Parallel agent spawning via Task tool

### Clavain Equivalent
**`/resolve`** — Resolves findings from any source (TODOs, PR comments, code TODOs). Auto-detects source and resolves in parallel.

**Comparison:**

| Feature | triage-prs | resolve |
|---------|-----------|---------|
| **Input** | All open PRs in a repo | Findings (TODOs, PR comments) |
| **Scope** | Triage unopened work | Fix identified issues |
| **Output** | Labels, grouped report, merge decisions | Commits resolving todos/comments |
| **Agents** | Review agents (one per batch) | pr-comment-resolver agents (one per item) |

**Overlap:** Both work with PR comments, but different stages:
- `triage-prs` = "What should we work on?" (before merge)
- `resolve` = "Fix the review feedback" (after review)

### Recommendation
**INTEGRATE AS COMPLEMENT** — `/triage-prs` fills a gap Clavain doesn't currently address (repo-wide PR backlog management).

**Integration path:**
1. Add `/triage` command (name already exists in Clavain, may need to rename to `/triage-prs` or consolidate)
2. Use Clavain's review agents (fd-correctness, fd-quality, fd-safety) instead of generic batch reviewers
3. Add to workflow: `/triage-prs` → select PRs to land → `/resolve` on chosen PRs → merge

**Positioning:** Repository hygiene tool (quarterly cleanup, onboarding to new repos).

---

## 7. beads — Dolt Transition (Multiple Commits)

### Change Summary
Beads completed a multi-phase transition from SQLite to Dolt:

**Phase 1: Dual backend**
- Added Dolt storage backend alongside SQLite
- Maintained JSONL sync layer for git portability

**Phase 2: Delete SQLite (commit `237f47ba`)**
- Deleted entire `internal/storage/sqlite/` package (~43K lines, 150+ files)
- Made Dolt the sole backend (treats "sqlite" as alias for "dolt")
- Preserved backward-compatible `beads.NewSQLiteStorage()` wrapper

**Recent fixes (last 20 commits):**
- Connection pool deadlocks
- CI test failures
- Doctor integrity checks
- Migration validation
- Cycle detection
- `--rig` flag for cross-rig queries

**Current status:**
- Default backend: Dolt
- Fallback: JSONL mode when CGO unavailable
- SQLite: Completely removed

### What is Dolt?
From beads README:
> **Dolt-Powered:** Version-controlled SQL database with cell-level merge and native branching. JSONL maintained for git portability.

**Key features:**
- SQL database with git-like versioning
- Cell-level merge conflict resolution
- Native branching (database branches track git branches)
- Multi-rig support (query across multiple project instances)

### Why Transition?
SQLite issues in multi-agent/multi-branch workflows:
- Merge conflicts on binary database files
- No cell-level resolution
- WAL files don't survive branch switches

Dolt solves these:
- Text-based diff/merge (like git)
- Tracks changes at cell level
- Branch-aware database state

### Clavain Impact
**NONE — Clavain doesn't bundle beads.** 

The beads MCP server runs as an external service at `/root/mcp_agent_mail` (not bundled in Clavain plugin). Users install `bd` CLI separately.

Clavain's `upstreams.json` tracks beads for documentation sync only (no code sync).

### Recommendation
**MONITOR ONLY** — Track Dolt stabilization (still seeing fixes 20 commits after deletion). If Dolt issues surface, document workarounds in Clavain's beads integration notes.

Update Clavain docs:
- `AGENTS.md` — Note Dolt as default backend
- `using-clavain` skill — Mention `bd init` uses Dolt (JSONL fallback if CGO unavailable)

---

## 8. superpowers `a98c5df` — v4.2.0 Release (Codex Native Skill Discovery)

### Change Summary
**Codex: Replaced bootstrap CLI with native skill discovery**

Removed:
- `superpowers-codex` bootstrap CLI
- Windows `.cmd` wrapper
- Bootstrap content file
- Node.js dependency

New approach:
- Skills symlinked to `~/.agents/skills/superpowers/`
- Codex native skill discovery (no custom tools)
- Just clone + symlink (no CLI, no npm install)

**Old path (deprecated):** `~/.codex/skills/`  
**New path:** `~/.agents/skills/`

**Other v4.2.0 changes:**
- Windows async SessionStart hook (covered in #2)
- O(n^2) escape_for_json fix (covered in #1)
- Worktree isolation required before implementation
- Main branch protection softened (require explicit consent)

### What is "Codex Native Skill Discovery"?
Codex CLI (from ethics-gradient, separate from Claude Code) now discovers skills via filesystem scan at `~/.agents/skills/*/SKILL.md` instead of requiring a bootstrap CLI tool.

**Before:** `use_skill` and `find_skills` CLI commands  
**After:** Direct filesystem access to `~/.agents/skills/`

### Clavain Impact
**INFORMATIONAL** — Clavain doesn't have Codex-specific bootstrap tooling.

Clavain uses:
- **Claude Code native plugin system** (`.claude-plugin/`)
- **Clodex dispatch** (`scripts/dispatch.sh` via `dispatching-clodex` skill)
- **SessionStart hook** for context injection

### Recommendation
**NO ACTION** — This is specific to superpowers' Codex integration. Clavain doesn't use bootstrap CLIs.

**Takeaway:** Native tool discovery > custom CLI wrappers. Clavain already follows this pattern (uses `.claude-plugin/plugin.json` natively).

---

## Summary Table

| Change | Status | Action | Priority |
|--------|--------|--------|----------|
| 1. escape_for_json optimization | ✓ Integrated | None (Clavain has better version) | N/A |
| 2. Async SessionStart hook | Not integrated | Add `"async": true` to hooks.json | P2 |
| 3. 79% context reduction | Partial | Audit & apply `disable-model-invocation` | P1 |
| 4. document-review skill | Not integrated | Add lightweight quick-review variant | P3 |
| 5. orchestrating-swarms skill | Not integrated | Extract patterns, add swarm mode to /lfg | P3 |
| 6. /triage-prs command | Not integrated | Add as repo hygiene tool | P2 |
| 7. Beads Dolt transition | External | Update docs, monitor stability | P3 |
| 8. Codex native skill discovery | N/A | None (informational) | N/A |

---

## Recommended Integration Order

### P1 (High Impact, Low Risk)
**Context reduction audit** — Systematically apply `disable-model-invocation` to workflow/utility commands and manual-only skills. Prevents future silent component exclusion.

**Effort:** 1-2 hours (audit 28 commands + 33 skills, test with `/help`)

### P2 (Medium Impact, Low Risk)
**Async SessionStart hook** — Add `"async": true` to `hooks/hooks.json` session-start hook. Improves startup responsiveness.

**Effort:** 5 minutes (one-line JSON change, restart session to test)

**Triage command** — Add `/triage-prs` (or consolidate with existing `/triage`) for repo-wide PR backlog management. Complements `/resolve`.

**Effort:** 2-3 hours (adapt upstream command, integrate fd-* review agents)

### P3 (Nice to Have)
**Lightweight document-review** — Add quick pre-planning review option in `/brainstorm` or `/strategy` workflows. Position as "quick polish" vs flux-drive's "comprehensive gates."

**Effort:** 3-4 hours (adapt upstream skill, integrate into workflow commands)

**Swarm patterns** — Extract key orchestration patterns (inbox messages, task dependencies, spawn backend detection) from upstream's 1,717-line skill. Add optional swarm mode to `/lfg` for parallel test + quality-gates.

**Effort:** 4-6 hours (extract patterns, update /lfg, document in using-clavain)

**Beads docs update** — Note Dolt as default backend in AGENTS.md and using-clavain skill. Mention JSONL fallback.

**Effort:** 15 minutes (doc updates only)

---

## Appendix: Technical Details

### A. Parameter Substitution Performance

**O(n^2) character loop (old):**
```bash
for (( i=0; i<${#input}; i++ )); do
    char="${input:$i:1}"  # Substring copy on each iteration
    case "$char" in
        '"') output+='\"' ;;
        # ...
    esac
done
```

**O(n) parameter substitution (new):**
```bash
s="${s//\\/\\\\}"    # Single C-level pass per pattern
s="${s//\"/\\\"}"    # Much faster
```

### B. disable-model-invocation Use Cases

**Manual workflows:**
```yaml
---
name: lfg
description: Full autonomous engineering workflow
disable-model-invocation: true
---
```
Claude can't suggest `/lfg` but users can invoke it.

**Utility commands:**
```yaml
---
name: heal-skill
description: Fix skill documentation issues
disable-model-invocation: true
---
```
Claude doesn't recommend healing skills unless explicitly asked.

**Manual-only skills:**
```yaml
---
name: file-todos
description: File-based todo tracking
disable-model-invocation: true
---
```
Skill loads when user says "use file todos" but doesn't appear in tool selection.

### C. Swarm Mode Orchestration Pattern

**Sequential (current):**
```
brainstorm → strategy → plan → flux-drive → execute → test → quality-gates → resolve → ship
```

**With swarm mode (proposed):**
```
brainstorm → strategy → plan → flux-drive → execute
                                              ↓
                                   ┌──────────┴──────────┐
                                   ↓                     ↓
                            test (agent 1)      quality-gates (agent 2)
                                   ↓                     ↓
                                   └──────────┬──────────┘
                                              ↓
                                          resolve → ship
```

**Parallelization saves:** ~2-3 minutes (test suite + 6 review agents overlap instead of sequence).

### D. Triage-PRs Batch Structure

**Example batch (4-6 PRs):**
```
Batch: Bug Fixes
- PR #123: Fix null pointer in auth flow
- PR #145: Resolve race condition in cache
- PR #167: Handle edge case in validator
- PR #189: Fix memory leak in parser

Batch: Features
- PR #134: Add OAuth2 support
- PR #156: Implement rate limiting
- PR #178: Add export to CSV
```

Each batch gets one review agent → parallel processing across batches.

---

**End of Research**
