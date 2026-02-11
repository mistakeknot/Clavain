# Clavain Plugin: Upstream Integrations Research

**Generated:** 2026-02-10  
**Scope:** Complete analysis of upstream dependencies, sync mechanisms, MCP servers, and integration pain points

---

## Executive Summary

Clavain is a general-purpose engineering discipline plugin that aggregates **34 skills**, **16 agents**, **24 commands**, and **3 MCP servers** from **7 upstream repositories**. The plugin uses a sophisticated prompt-driven sync mechanism (Claude Code + Codex CLI orchestration) without custom code, tracked via `upstreams.json` with file-level granularity.

**Key Findings:**
- **6 of 7 upstreams are actively tracked** with commit hashes; only 2 (superpowers-lab, superpowers-dev) track non-release commits
- **8 agents were consolidated** (19 → 6 fd-* agents) creating stale reference risks across commands, skills, and routing tables
- **3 MCP servers** are integrated: context7 (HTTP), mcp-agent-mail (HTTP), qmd (stdio)
- **New agent dispatch blocking issue:** agents created mid-session aren't available until session restart
- **Knowledge layer** (flux-drive) now uses semantic search to inject learned patterns into code reviews

---

## 1. Upstream Repositories & File Mappings

### 1.1 Upstreams Tracked in `upstreams.json`

| Upstream | URL | Last Synced | Branch | Files Mapped |
|----------|-----|-------------|--------|-------------|
| **beads** | github.com/steveyegge/beads | eb1049b (v0.49.4) | main | 5 files (skill + docs + resources) |
| **oracle** | github.com/steipete/oracle | 5c053e2 (v0.8.5) | main | 10 files (interpeer ref docs) |
| **mcp-agent-mail** | github.com/Dicklesworthstone/mcp_agent_mail | 9992244 (v0.3.0) | main | 10 files (skill + server design guide + ADRs) |
| **superpowers** | github.com/obra/superpowers | a98c5df (v4.1.1) | main | 22 files (11 skills + 1 agent + 3 commands) |
| **superpowers-lab** | github.com/obra/superpowers-lab | 897eebf (no release) | main | 4 skills (tmux, slack, mcp-cli, dup-finding) |
| **superpowers-dev** | github.com/obra/superpowers-dev | 74afe93 (no release) | main | 2 skills (claude-code plugin dev, working with claude code) |
| **compound-engineering** | github.com/EveryInc/compound-engineering-plugin | 04ee7e4 (no release, synced to wrong commit) | main | 21 items (3 skills + 10 agents + 9 commands) |

**Last Check Date:** 2026-02-06 20:26:55 UTC (4 days stale)

### 1.2 File Mapping Patterns

Clavain uses glob patterns in `fileMap` entries, allowing:
- **Direct 1:1 mapping:** `"skills/brainstorming/SKILL.md": "skills/brainstorming/SKILL.md"` (superpowers)
- **Renamed mapping:** `"skills/using-superpowers/SKILL.md": "skills/using-clavain/SKILL.md"` (superpowers)
- **Namespace mapping:** `"agents/code-reviewer.md": "agents/review/plan-reviewer.md"` (superpowers)
- **Glob expansion:** `"claude-plugin/skills/beads/resources/*": "skills/beads-workflow/references/*"` (beads)
- **basePath prefix:** compound-engineering uses `"basePath": "plugins/compound-engineering"` — sync strips this before checking fileMap

### 1.3 Skills by Upstream Origin

| Source | Skills (Count) |
|--------|---|
| **superpowers** (founding) | brainstorming, dispatching-parallel-agents, executing-plans, receiving-code-review, requesting-code-review, subagent-driven-development, systematic-debugging, test-driven-development, using-clavain, verification-before-completion, writing-plans, writing-skills (12) |
| **compound-engineering** (founding) | agent-native-architecture, create-agent-skills, file-todos (3) |
| **superpowers-lab** | finding-duplicate-functions, mcp-cli, slack-messaging, using-tmux-for-interactive-commands (4) |
| **superpowers-dev** | developing-claude-code-plugins, working-with-claude-code (2) |
| **beads** | beads-workflow (1) |
| **oracle** | interpeer, prompterpeer, winterpeer, splinterpeer (via mapping; embedded in oracle skill) (1) |
| **mcp-agent-mail** | agent-mail-coordination (1) |
| **Clavain Local** | upstream-sync, flux-drive, landing-a-change, refactor-safely, and others (9+) |

**Total:** 34 skills (as stated in plugin.json description)

### 1.4 Agents by Upstream Origin

#### Imported from Upstreams (13 agents)

**From compound-engineering:**
- agents/research/: best-practices-researcher, framework-docs-researcher, git-history-analyzer, learnings-researcher, repo-research-analyst (5)
- agents/review/: agent-native-reviewer, data-migration-expert (2)
- agents/workflow/: bug-reproduction-validator, pr-comment-resolver (2)

**From superpowers:**
- agents/review/plan-reviewer (replaces `code-reviewer.md` from upstream) (1)

**Plus 3 more from compound-engineering in upstreams.json but not found locally:**
- architecture-strategist (deleted)
- deployment-verification-agent (deleted)
- security-sentinel (deleted)

#### Locally Developed (6 agents)

All under `agents/review/fd-*`:
- fd-architecture
- fd-correctness
- fd-performance
- fd-quality
- fd-safety
- fd-user-product

These are part of **flux-drive v2** — a structured code-review framework with triage, parallel reviews, and cross-AI validation (oracle).

**Current agent count:** 16 (not 29 as stated in plugin.json description — this is stale)

### 1.5 Commands by Upstream Origin

**From superpowers (3):**
- brainstorm, execute-plan, write-plan

**From compound-engineering (9):**
- agent-native-audit, changelog, create-agent-skill, generate-command, heal-skill, lfg, plan-review, resolve-parallel, resolve-pr-parallel, resolve-todo-parallel, triage

**Clavain local (12+):**
- upstream-sync, flux-drive, agent-native-prompt-check, and others

**Current count:** 24 commands (matches plugin.json)

---

## 2. Sync Mechanism: Prompt-Driven via Claude Code + Codex CLI

### 2.1 Architecture

```
.github/workflows/sync.yml (weekly cron + manual dispatch)
    ↓
[GitHub Actions] → git clone upstreams to .upstream-work/
    ↓
codex exec --sandbox workspace-write (Codex CLI)
    ↓
[Prompt-based orchestration — no custom code]
    ↓
For each upstream:
  1. git diff lastSyncedCommit...HEAD (with basePath filtering)
  2. Filter to fileMap entries
  3. For MODIFIED files → delegate merge to Codex AI
  4. For NEW files → copy in
  5. For DELETED files → skip with warning
    ↓
Update upstreams.json lastSyncedCommit hashes
    ↓
Workspace changes (uncommitted) → create-pull-request action
```

**Design Principle:** Zero custom code. The entire sync is orchestrated via a detailed prompt that Codex (ChatGPT API) executes. No shell scripts or Python runners — just markdown instructions.

### 2.2 Sync Workflow Details (from `.github/workflows/sync.yml`)

**Step 1: Preflight**
- Verify `CODEX_AUTH_JSON` secret exists
- Setup Node.js, install Codex CLI
- Authenticate Codex with ChatGPT auth file

**Step 2: Clone Upstreams**
- Parse `upstreams.json`, clone/fetch all repos to `.upstream-work/<name>/`
- Keep local clones for subsequent diffs

**Step 3: Codex Orchestrates Sync**
- Codex reads `.upstream-work/<upstream>/` files directly
- Compares against `lastSyncedCommit` using `git diff --name-status`
- Strips `basePath` prefix before fileMap lookup
- **Critical:** Glob patterns (e.g., `references/*`) are expanded against actual directory listings
- For each modified file, runs nested `codex exec` (with `--model o3` for deep reasoning) to merge content
- Merge validation: result must not be empty, must preserve YAML frontmatter if original had it

**Step 4: Update State**
- Only updates `lastSyncedCommit` for upstreams that succeeded (no errors)
- Leaves workspace changes uncommitted

**Step 5: Create PR**
- `create-pull-request` action opens PR with title "sync: upstream changes from parent repos"
- PR body lists all 7 upstreams and reminds reviewer to include decision record

### 2.3 Sync State Check (`scripts/upstream-check.sh`)

Checks upstreams against saved state in `docs/upstream-versions.json`. Reports:
- Latest release tag (if any)
- Latest commit SHA + message + date
- Comparison to synced state
- Exit code 0 = changes, 1 = no changes

**Last checked:** 2026-02-06 (4+ days stale at time of this research)

---

## 3. MCP Servers Integration

### 3.1 MCP Servers Declared in `plugin.json`

```json
{
  "mcpServers": {
    "context7": {
      "type": "http",
      "url": "https://mcp.context7.com/mcp"
    },
    "mcp-agent-mail": {
      "type": "http",
      "url": "http://127.0.0.1:8765/mcp"
    },
    "qmd": {
      "type": "stdio",
      "command": "qmd",
      "args": ["mcp"]
    }
  }
}
```

### 3.2 MCP Server Usage

| Server | Purpose | Type | Startup |
|--------|---------|------|---------|
| **context7** | Framework & library documentation lookup (cross-model search) | HTTP (remote) | Automatic |
| **mcp-agent-mail** | Agent coordination, message/task dispatch, cross-project comm | HTTP (localhost:8765) | Requires local service |
| **qmd** | Semantic search over project knowledge (flux-drive integration) | stdio | Auto-launched (`qmd mcp`) |

### 3.3 Known MCP Issues

**Issue: qmd (stdio MCP server) missing dependencies in Claude Code plugin cache**
- Root cause: Claude Code's marketplace caches plugin source but NOT `node_modules/`
- stdio MCP servers fail on first start: `ERR_MODULE_NOT_FOUND: Cannot find package '@modelcontextprotocol/sdk'`
- **Solution** (documented in `/docs/solutions/`): Use bootstrap wrapper script (`scripts/start.sh`) that runs `npm install` on first start, then `exec` into server
- **Status:** Workaround in place; no upstream fix (Claude Code would need `postInstall` lifecycle hooks)

**Context7 Integration:**
- Used by Context7 skill and flux-drive for semantic search during code reviews
- HTTP remote service — no local startup needed
- Returns API docs and code examples from 500+ documentation sources

**mcp-agent-mail:**
- Requires HTTP server running at `127.0.0.1:8765`
- Used by agent-mail-coordination skill
- Tracks agent mailboxes, messages, and cross-project coordination
- Integrated via MCP but requires external service (not included in Clavain distribution)

---

## 4. Local-Only & Locally Modified Content

### 4.1 Locally Developed Features

**Flux-Drive Framework** (core local development)
- 6 specialized agents (fd-architecture, fd-correctness, fd-performance, fd-quality, fd-safety, fd-user-product)
- Replaced older 19-agent model with specialized parallelizable reviewers
- Phases: Triage → Launch → Synthesize
- Knowledge layer: semantic search over learned patterns
- Cross-AI validation: oracle integration for blind-spot detection

**Knowledge Layer** (`config/flux-drive/knowledge/`)
- Entry format: YAML frontmatter + markdown evidence + verification steps
- Provenance tracking: `independent` vs `primed` (prevents false-positive feedback loops)
- Decay rules: entries archived after 10 reviews without independent re-confirmation
- Sanitization: entries stored as generalized heuristics (no file paths, hostnames, secrets)

**Skills Created Locally:**
- upstream-sync (orchestrates the sync workflow)
- flux-drive (code review orchestration)
- landing-a-change (deployment checklist)
- refactor-safely (risk-aware refactoring)
- others (exact count not enumerated but ~9+ additional local skills)

### 4.2 Upstream-Specific Modifications

**Namespace Renaming:**
- `skills/using-superpowers/SKILL.md` → `skills/using-clavain/SKILL.md`
- References to "superpowers" are replaced with "clavain" in content

**Agent Path Reorganization:**
- `agents/code-reviewer.md` (from superpowers) → `agents/review/plan-reviewer.md`

**File Renames (compound-engineering):**
- `agents/review/data-integrity-guardian.md` → `agents/review/data-integrity-reviewer.md`
- `agents/review/kieran-python-reviewer.md` → `agents/review/python-reviewer.md`
- `agents/review/kieran-typescript-reviewer.md` → `agents/review/typescript-reviewer.md`

### 4.3 Deleted Agents (Consolidation)

8 agents were deleted as part of flux-drive v2 consolidation (19 → 6):
- architecture-strategist (consolidated into fd-architecture)
- code-simplicity-reviewer (consolidated into fd-quality)
- deployment-verification-agent (deleted, no fd-* replacement yet)
- performance-oracle (consolidated into fd-performance)
- security-sentinel (consolidated into fd-safety)
- and 3 others referenced in upstreams.json but not found locally

**Impact:** Commands, skills, and routing tables still contain stale references (documented as known issue in `docs/solutions/best-practices/agent-consolidation-stale-reference-sweep-20260210.md`)

---

## 5. Current Sync State & Behind-ness Analysis

### 5.1 Sync Status

**Last Sync Check:** 2026-02-06 20:26:55 UTC  
**Current Date:** 2026-02-10 13:00+ UTC  
**Days Behind:** 4 days (no automated weekly sync visible in recent commits)

### 5.2 Per-Upstream Status

| Upstream | Synced Commit | Synced Release | Status | Notes |
|----------|---------------|---|--------|-------|
| beads | eb1049b | v0.49.4 | ✓ Released | Up to date at release version |
| oracle | 5c053e2 | v0.8.5 | ✓ Released | Up to date at release version |
| mcp-agent-mail | 9992244 | v0.3.0 | ✓ Released | Up to date at release version |
| superpowers | a98c5df | v4.1.1 | ✓ Released | Up to date at release version |
| superpowers-lab | 897eebf | (no release) | ? | Commit-based tracking; no release tags |
| superpowers-dev | 74afe93 | (no release) | ? | Commit-based tracking; no release tags |
| compound-engineering | e4ff6a8 (upstreams.json shows 04ee7e4) | (no release) | ⚠ Mismatch | Versions don't match; sync state unclear |

**Note on compound-engineering:** The synced commit in `upstreams.json` (04ee7e4) doesn't match `upstream-versions.json` (e4ff6a8). This indicates either:
1. Partial sync that updated `upstream-versions.json` but failed to commit `upstreams.json`
2. Manual edits to one file but not the other
3. Sync mechanism bug — requires investigation

### 5.3 Release vs Commit Tracking

- **Released upstreams (4):** beads, oracle, mcp-agent-mail, superpowers — have version tags and are more predictable
- **Unreleased upstreams (3):** superpowers-lab, superpowers-dev, compound-engineering — tracked only by commit hash, harder to follow upstream progress

---

## 6. Pain Points & Integration Challenges

### 6.1 Agent Consolidation & Stale References

**Problem:** Deleting/renaming agents leaves stale references scattered across:
- Commands (dispatch references: `/review` still calls `architecture-strategist`)
- Skills (routing tables: `using-clavain/SKILL.md`, flux-drive roster)
- Tests (agent type assertions, error message strings)
- Documentation (README, AGENTS.md, CLAUDE.md)
- Hardcoded counts in 5+ locations

**Example:** After consolidating 19 agents → 6 fd-* agents, grep found stale refs in:
- skills/flux-drive/phases/launch.md (monitoring examples)
- skills/flux-drive/SKILL.md (roster table)
- skills/landing-a-change/SKILL.md (checklist references)
- commands/plan-review.md (agent dispatch)
- scripts/validate-roster.sh (expected count)
- tests/smoke/smoke-prompt.md (subagent_type strings)

**Mitigation:** Manual grep sweep required post-consolidation. Workflow documented but labor-intensive.

### 6.2 New Agents Not Available Until Session Restart

**Problem:** New agent `.md` files created mid-session are not available as `subagent_type` values in Task tool until session restart.

**Root Cause:** Claude Code's plugin system loads agent registry once at session start. Creating files doesn't refresh the registry.

**Workaround:** Use `subagent_type: general-purpose` + paste full agent prompt into task

**Proper Fix:** Commit → push → bump version → publish → restart session (adds 10+ minutes to development cycle)

**Impact:** Flux-drive v2 development was slowed by inability to test new agents in same session

### 6.3 Compound-Engineering Sync Commit Mismatch

**Problem:** `upstreams.json` shows `lastSyncedCommit: 04ee7e450653a3f6f8721a128d3c372867adfcc8` but `docs/upstream-versions.json` shows `e4ff6a8`. Files disagree on current state.

**Impact:** Unclear if we're behind upstream or not. Next sync may not work correctly if commit is unreachable.

**Requires Investigation:** Does the sync workflow validate commit reachability? Can it recover from commit mismatch?

### 6.4 Sync Mechanism Opacity

**Problem:** Entire sync is orchestrated via Claude Code → Codex CLI with nested AI prompts. No way to audit what was merged or why without reading generated PR.

**Merge Logic:** Codex receives upstream diff + full file content and decides how to merge. Merge decisions are not logged, only the result is visible in PR.

**Risk:** Silent incorrect merges, especially for YAML frontmatter preservation or section-order changes. Reviewer must manually check every merged file.

**Mitigation:** Upstream changes should be manually reviewed in PR before merge. Documentation warns of this.

### 6.5 MCP Server Startup Fragility

**Problem:** stdio-based MCP servers (qmd) fail to start if `node_modules/` missing (Claude Code plugin cache doesn't include deps)

**Current State:** Workaround in place with bootstrap wrapper, but requires special handling per server

**Better Solution:** Would require Claude Code to support `postInstall` lifecycle hooks in `plugin.json`

### 6.6 False-Positive Feedback Loop in Flux-Drive Knowledge

**Problem:** Knowledge entries injected into agent context can cause agents to re-flag the same finding (primed confirmation), creating permanent false positives.

**Mitigation:** Provenance field (`independent` vs `primed`) tracks whether agent had entry in context. Only independent confirmations refresh decay timer.

**Decay:** Entries archived after 10 reviews without independent re-confirmation

**Risk:** Still possible if agent re-discovers finding independently but artifact hasn't rotted yet

---

## 7. Architectural Insights

### 7.1 3-Layer Routing (Skills Organization)

Clavain organizes skills by stage → domain → language:

```
skills/
├── [Stage] dispatching-parallel-agents, executing-plans, writing-plans
├── [Domain] brainstorming, debugging, testing, code-review, deployment
├── [Language] developing-claude-code-plugins, working-with-claude-code
└── [Cross-cutting] flux-drive, agent-mail-coordination, upstream-sync
```

Routing table in `skills/using-clavain/SKILL.md` maps user queries to skills, formerly included stale agent names.

### 7.2 Flux-Drive: Structured Code Review

**Purpose:** Reduce latency and cost of code reviews by:
1. Parallelizing specialized reviewers (architecture, correctness, performance, safety, quality, user-product)
2. Triage phase: decide which reviewers to run (cost optimization)
3. Synthesize phase: aggregate findings, cross-check with oracle

**Phases:**
- **Triage:** Single agent samples code, recommends reviewer subset
- **Launch:** Parallel dispatch to selected fd-* agents
- **Synthesize:** Aggregate findings, invoke oracle for cross-model validation
- **Knowledge Injection:** qmd semantic search retrieves 5 relevant knowledge entries per agent

**Cross-AI Validation:** oracle CLI runs code through GPT-5.2-pro to catch blind spots Claude-only reviewers might miss

### 7.3 Upstream vs Local Tensions

**Superpowers & Compound-Engineering are "Founding Sources":** They contribute multiple core skills and agents. Clavain is essentially a highly customized instantiation of these.

**Divergence Risk:** As Clavain adds local features (flux-drive, knowledge layer), it becomes harder to absorb upstream changes without conflicts. The prompt-based merge mechanism helps but isn't foolproof.

**Strategy:** Most upstream changes are additive (new skills). Conflicting changes (agent deletions, skill renames) are rare but high-impact.

---

## 8. Recommendations & Outstanding Questions

### 8.1 Immediate Actions

1. **Fix compound-engineering commit mismatch** in upstreams.json (04ee7e4 → e4ff6a8)
2. **Re-run upstream-check.sh** to get current state (currently 4 days stale)
3. **Complete agent consolidation stale reference sweep:**
   - Verify all 8 deleted agents are removed from commands, skills, tests
   - Hardcoded counts should match: README, AGENTS.md, CLAUDE.md, plugin.json, validate-roster.sh
4. **Verify qmd stdio MCP server** is starting cleanly with bootstrap wrapper

### 8.2 Medium-Term Improvements

1. **Automate stale reference detection:** Add CI check that counts agents and compares to hardcoded values
2. **Improve merge transparency:** Log Codex AI merge decisions (which sections merged, which skipped) to PR comments
3. **Test new agents without restart:** File RFE with Claude Code for agent registry refresh mid-session OR implement workaround pattern library
4. **Formalize upstream consolidation:** Document agent → agent mappings (19 → 6) to catch future reference sweeps

### 8.3 Outstanding Questions

1. **compound-engineering:** Why is the synced commit different in upstreams.json vs upstream-versions.json? When was this last synced?
2. **Unreleased upstreams:** superpowers-lab and superpowers-dev have no release tags. Are we tracking the right branch? Should we pin to a specific commit?
3. **Deleted agents:** Why were 8 agents deleted instead of preserved with deprecation warnings? What handles routing for old code that references them?
4. **Knowledge decay:** Are entries actually being archived after 10 reviews? Any entries approaching the 10-review mark yet?
5. **Oracle integration:** How often does oracle validation catch issues Claude misses? Is the cross-AI model working well?

---

## 9. Files Modified During Consolidation (Not in Upstream Mapping)

These are known renames/deletions not reflected in upstreams.json:

**Deleted Agents:**
- agents/review/architecture-strategist.md → fd-architecture.md
- agents/review/security-sentinel.md → fd-safety.md
- agents/review/performance-oracle.md → fd-performance.md
- agents/review/code-simplicity-reviewer.md → fd-quality.md
- agents/review/deployment-verification-agent.md → (no fd-* replacement)
- agents/workflow/spec-flow-analyzer.md → (no fd-* replacement)

**Renamed (from compound-engineering):**
- agents/review/data-integrity-guardian.md → data-integrity-reviewer.md
- agents/review/kieran-python-reviewer.md → python-reviewer.md
- agents/review/kieran-typescript-reviewer.md → typescript-reviewer.md

---

## Appendix A: Upstream Repository Structure

### Beads (steveyegge/beads)
- Skill: beads-workflow (task execution and feedback loops)
- README, CLAUDE.md, resources/, adr/ → skill references/

### Oracle (steipete/oracle)
- Interpeer reviewers (oracle, prompterpeer, winterpeer, splinterpeer)
- Browser automation, multimodel support
- Docs: configuration, linux, mcp, debug modes

### MCP-Agent-Mail (Dicklesworthstone/mcp_agent_mail)
- Agent coordination and mailbox system
- MCP server design guide, deployment samples, ADRs

### Superpowers (obra/superpowers)
- **Founding source:** 11 core skills, 1 agent, 3 commands
- Skills: brainstorming, planning, execution, debugging, testing, code review, agent dispatch
- Structured methodology for engineering discipline

### Superpowers-Lab (obra/superpowers-lab)
- Supplementary skills: tmux automation, slack messaging, MCP CLI, duplicate detection

### Superpowers-Dev (obra/superpowers-dev)
- Plugin development skills and best practices
- Claude Code plugin architecture references

### Compound-Engineering (EveryInc/compound-engineering-plugin)
- **Founding source:** 3 skills, 10 agents, 9 commands
- Research agents: best-practices-researcher, framework-docs-researcher, etc.
- Review agents: agent-native-reviewer, various language-specific reviewers
- Workflow agents: bug-reproduction-validator, pr-comment-resolver
- File-todos skill for persistent task tracking

---

## Appendix B: Sync Workflow File Reference

| File | Purpose |
|------|---------|
| `upstreams.json` | Source of truth: upstream repos, commit hashes, file mappings |
| `.github/workflows/sync.yml` | Weekly cron + manual dispatch, orchestrates sync via Codex |
| `docs/upstream-versions.json` | Historical check state (last release tag, commit, check date per upstream) |
| `scripts/upstream-check.sh` | Bash script to check all upstreams for changes |
| `scripts/upstream-impact-report.py` | Analyzes commits since last sync, infers feature/breaking signals |
| `.upstream-work/` | .gitignored working directory for cloned upstream repos during sync |

---

## Appendix C: Key Configuration & Documentation Files

| File | Role |
|------|------|
| `.claude-plugin/plugin.json` | Plugin manifest with MCP server declarations, version, description |
| `config/flux-drive/knowledge/README.md` | Knowledge layer format, provenance rules, decay policy |
| `skills/flux-drive/SKILL.md` | Flux-drive phases, agent roster, cross-AI validation |
| `skills/upstream-sync/SKILL.md` | User-facing documentation of sync process |
| `docs/solutions/` | Known issues: agent consolidation, MCP cache, new agent restart requirement |
| `docs/research/flux-drive/` | Past flux-drive review outputs and analysis |
| `config/CLAUDE.md` | Engineering conventions (Clavain-specific) |

---

**Document Complete**
