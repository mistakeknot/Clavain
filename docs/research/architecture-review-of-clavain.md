# Architecture Review of Clavain

**Date:** 2026-02-11
**Version:** 0.4.29
**Scope:** Full architectural review -- module boundaries, routing, hooks, MCP servers, upstream sync, knowledge layer, agent consolidation.

---

## Executive Summary

Clavain is a well-structured Claude Code plugin that consolidates 6 upstream projects into a cohesive engineering discipline layer. The 3-layer routing system, phased flux-drive review engine, and hook-based lifecycle management represent sound architectural decisions. However, the review identifies several areas of concern: count drift across documentation surfaces, accumulated redirect stubs inflating component totals, a 1,000-line sync script that has outgrown its bash origins, and an asymmetry in how the two Stop hooks coordinate. Below is a detailed analysis organized by the 7 requested focus areas, followed by prioritized recommendations.

---

## 1. Module Boundaries: Skills / Agents / Commands

### Separation Quality

The three-tier component model (skills = knowledge/process, agents = specialized subagents, commands = user-facing entry points) is cleanly defined in `AGENTS.md` lines 99-105:

- **Skills** teach Claude how to approach a class of work. They are invoked via the `Skill` tool and provide process guidance.
- **Agents** are dispatched as subagents via the `Task` tool. They execute in isolation with their own context.
- **Commands** are user-invoked via `/clavain:<name>`. They orchestrate skills and agents.

This separation is sound and well-enforced. Commands reference skills and dispatch agents; skills do not dispatch commands; agents do not invoke other agents. The dependency direction is clean: commands depend on skills and agents, but not the reverse.

### Overlap and Redundancy

**Finding 1 (P2): Three redirect-stub skills inflate the skill count.**

`prompterpeer`, `winterpeer`, and `splinterpeer` (at `/root/projects/Clavain/skills/prompterpeer/SKILL.md`, `/root/projects/Clavain/skills/winterpeer/SKILL.md`, `/root/projects/Clavain/skills/splinterpeer/SKILL.md`) are 5-10 line files that say "merged into interpeer, use mode X." They exist on disk, count toward the "33 skills" total (previously "34 skills" before other corrections), and are loaded by the Skill tool when invoked. They add no value beyond a redirect. Their descriptions are well-written (they use full sentences about Oracle, LLM council, etc.) which means the Skill tool's fuzzy matching might route users to them instead of directly to `interpeer`.

**Recommendation:** Delete the three stub skills. Update the skill count from 33 to 30. Alternatively, if backward compatibility matters, keep them but exclude from the count and add a `deprecated: true` frontmatter field that the routing table and tests can filter on.

**Finding 2 (P3): Review command vs quality-gates command vs flux-drive command overlap.**

Three commands serve the "review" stage:
- `/clavain:review` (`/root/projects/Clavain/commands/review.md`) -- PR-focused, hardcodes 5 agents (fd-architecture, fd-safety, fd-quality, git-history-analyzer, agent-native-reviewer), no triage phase.
- `/clavain:quality-gates` (`/root/projects/Clavain/commands/quality-gates.md`) -- git-diff-focused, always runs fd-architecture + fd-quality, caps at 5 agents.
- `/clavain:flux-drive` (`/root/projects/Clavain/commands/flux-drive.md`) -- the full system with scored triage, 4 phases, up to 8 agents.

The routing table at `/root/projects/Clavain/skills/using-clavain/SKILL.md` lines 73-80 clarifies when to use each, which is good. However, `review` hardcodes agent selection while `quality-gates` and `flux-drive` both do dynamic selection -- `review` is the odd one out. As the codebase matures, `review` risks diverging from the fd-* agent roster updates.

**Recommendation:** Consider having `review` delegate to `flux-drive` with a PR-specific input adapter rather than maintaining its own parallel agent dispatch logic. This would reduce the maintenance surface for review agent orchestration from 3 places to 1.

**Finding 3 (P3): `lfg` command chains 8 steps sequentially through other commands.**

`/clavain:lfg` (`/root/projects/Clavain/commands/lfg.md`) is a macro that chains brainstorm -> write-plan -> flux-drive -> work -> test -> quality-gates -> resolve -> ship. This is useful as a workflow template but creates a long-running session where context accumulation could degrade quality of later steps. Each step invokes a separate skill/command, which is architecturally clean (no cross-cutting), but the error recovery section (lines 56-67) only handles "retry once with tighter scope" -- there is no mechanism to checkpoint progress or resume from a specific step beyond manually re-invoking commands.

**Recommendation:** No immediate change needed. This is an acceptable trade-off for a macro command. If users report quality degradation in later steps, consider adding a checkpoint mechanism.

### Count Drift

**Finding 4 (P1): Component counts are inconsistent across documentation surfaces.**

| Source | Skills | Agents | Commands |
|--------|--------|--------|----------|
| `using-clavain/SKILL.md` line 24 | 34 | 16 | 23 |
| `CLAUDE.md` line 7 | 33 | 16 | 25 |
| `AGENTS.md` line 12 | 33 | 16 | 25 |
| `plugin.json` line 4 | 33 | 16 | 25 |
| `agent-rig.json` line 4 | 33 | 16 | 23 |
| `README.md` line 7 | 33 | 16 | 25 |
| Filesystem reality | 33 | 16 | 25 |

The `using-clavain/SKILL.md` routing table says "34 skills" and "23 commands" but the filesystem shows 33 skills and 25 commands. `agent-rig.json` also says "23 commands." These are the files injected into every session via the SessionStart hook and the agent rig, so the discrepancy is visible to every user.

**Recommendation:** Update `/root/projects/Clavain/skills/using-clavain/SKILL.md` line 24 to say "33 skills, 16 agents, and 25 commands." Update `/root/projects/Clavain/agent-rig.json` line 4 description to match. Consider adding a structural test that validates these strings against filesystem reality (the existing `tests/structural/test_skills.py` checks the count but not the embedded strings).

---

## 2. Routing Architecture

### 3-Layer Routing Effectiveness

The Stage -> Domain -> Concern routing system at `/root/projects/Clavain/skills/using-clavain/SKILL.md` is the architectural crown jewel of Clavain. It solves a real problem: with 33 skills, 16 agents, and 25 commands, users need guidance on which component to invoke.

**Strengths:**
- Layer 1 (Stage) maps cleanly to user intent verbs ("build" -> Execute, "fix" -> Debug, "review" -> Review).
- Layer 2 (Domain) disambiguates within a stage (Code vs Data vs Deploy).
- Layer 3 (Concern) is optional and only applies to the Review stage, keeping cognitive load low for non-review workflows.
- The "Which review command?" table (lines 73-80) directly addresses the most common decision point.
- The routing heuristic (lines 99-107) gives Claude a concrete algorithm for matching user messages to components.

**Finding 5 (P2): The routing table has gaps in coverage.**

Several skills are not represented in the routing tables:
- `create-agent-skills` appears as `create-agent-skill` in the Meta stage but the actual skill directory is `create-agent-skills` (plural).
- The three redirect stubs (`prompterpeer`, `winterpeer`, `splinterpeer`) are not in the routing table, which is correct since they redirect, but this means a user invoking them by name gets redirected rather than routed.
- `refactor-safely` is listed in Layer 2 (Domain: Code) but not in Layer 1 (any stage). A user asking to "refactor this" would need to hit the Code domain row, which is fine but could also merit a mention under the Execute stage.

**Finding 6 (P3): The EXTREMELY-IMPORTANT block is architecturally wasteful.**

Lines 6-12 of `using-clavain/SKILL.md` contain an `<EXTREMELY-IMPORTANT>` XML tag demanding that skills be invoked for "even a 1% chance." This content is injected into every session via the SessionStart hook. It consumes approximately 200 bytes of context window for every session, whether the user is doing skill-relevant work or not. More importantly, it sets a threshold so low (1%) that it encourages over-invocation, which wastes tool calls and context window on skill loads that add no value.

**Recommendation:** Consider raising the threshold language to something like "skills that are relevant to your current task" rather than the 1% absolutism. The skill descriptions already contain trigger phrases for fuzzy matching -- the routing heuristic is more useful than the demand for universal invocation.

### SessionStart Injection Size

The SessionStart hook reads the entire `using-clavain/SKILL.md` (6,408 bytes) and injects it as `additionalContext`. This is a fixed context window cost for every session. The content is well-structured and essential for routing, so this is a reasonable trade-off. However, as the routing table grows with new components, this cost will increase linearly.

**Recommendation:** No immediate change. Monitor the file size. If it grows beyond ~10KB, consider splitting the routing table into a compact version (top commands only) injected by default, with a `/clavain:full-catalog` command for the complete listing.

---

## 3. Hook Architecture

### Overview

Five hooks are registered in `/root/projects/Clavain/hooks/hooks.json`:

| Hook | Event | Script | Timeout |
|------|-------|--------|---------|
| autopilot | PreToolUse (Edit/Write/MultiEdit/NotebookEdit) | `autopilot.sh` | 5s |
| session-start | SessionStart (startup/resume/clear/compact) | `session-start.sh` | async |
| auto-compound | Stop | `auto-compound.sh` | 5s |
| session-handoff | Stop | `session-handoff.sh` | 5s |
| dotfiles-sync | SessionEnd | `dotfiles-sync.sh` | async |

### Hook Design Quality

**autopilot.sh** (`/root/projects/Clavain/hooks/autopilot.sh`): Well-designed gating hook. The path-based exception system (lines 41-59) correctly allows documentation and config writes while blocking source code in clodex mode. The fallback JSON output (lines 81-89) when jq is unavailable is a good defensive pattern.

**session-start.sh** (`/root/projects/Clavain/hooks/session-start.sh`): Solid design with graceful fallback (line 28), companion detection (lines 33-48), and upstream staleness warning (lines 53-65). The stale cache cleanup (lines 17-25) solves a real problem documented in the comment -- deleting cache mid-session broke Stop hooks. Moving cleanup to the next session start is the right fix.

**dotfiles-sync.sh** (`/root/projects/Clavain/hooks/dotfiles-sync.sh`): Minimal and correct. The `|| true` on line 23 ensures failures are swallowed silently, which is appropriate for an async session-end hook that cannot surface errors to the user.

### Race Conditions and Coordination Issues

**Finding 7 (P2): Two Stop hooks with independent guard logic but no coordination.**

Both `auto-compound.sh` and `session-handoff.sh` fire on the Stop event. They share the same `stop_hook_active` guard (lines 24-27 in both scripts) to prevent infinite re-triggering. However, they have no coordination between them:

1. If `auto-compound.sh` fires first and returns `decision: "block"`, Claude processes its compound prompt. When Claude finishes compounding and tries to stop again, both hooks fire again. `auto-compound.sh` will likely fire again (the compound itself may generate signals), but `session-handoff.sh` will not re-fire because it writes a sentinel file (`/tmp/clavain-handoff-${SESSION_ID}`).

2. If `session-handoff.sh` fires first, it blocks with a HANDOFF.md prompt. When Claude completes the handoff and tries to stop, `auto-compound.sh` may fire and detect the handoff commit as a compoundable signal (it looks for `git commit` in the transcript). This could create a loop: handoff -> compound -> handoff (blocked by sentinel) -> compound (if new signals).

3. The hooks are registered as an array in the same Stop entry (lines 29-39 of `hooks.json`), meaning they run sequentially within the same hook cycle. Both can independently return `decision: "block"`, but only the first block is processed by Claude Code (the second is queued).

**Recommendation:** Add a shared sentinel mechanism. For example, `auto-compound.sh` could check for the `session-handoff.sh` sentinel before firing, and vice versa. Or introduce a `/tmp/clavain-stop-active-${SESSION_ID}` file that the first hook to fire creates, and the second hook skips if it exists. This prevents the compound-after-handoff loop.

**Finding 8 (P3): auto-compound.sh transcript parsing is fragile.**

`auto-compound.sh` lines 34-36 extract recent transcript lines with `tail -40` and then grep for signal patterns. The transcript is JSONL, but the grep patterns (lines 45-67) search for raw strings like `"git commit` and `"that worked`. These patterns depend on how Claude Code serializes tool calls and assistant messages in the transcript. If the transcript format changes (e.g., tool calls become nested JSON objects instead of flat strings), all signal detection breaks silently.

**Recommendation:** Consider using `jq` to parse the JSONL transcript properly rather than raw grep. Extract the `.content` or `.text` fields from the last N messages and search those. This is more resilient to format changes.

**Finding 9 (P3): session-handoff.sh sentinel uses /tmp which survives session restarts.**

The sentinel file `/tmp/clavain-handoff-${SESSION_ID}` (line 30 of `session-handoff.sh`) uses the session ID, so it is per-session. However, `/tmp` files persist across session restarts on Linux (until reboot or tmpfiles cleanup). If a session is resumed (`resume` trigger), the handoff hook will not fire again because the sentinel from the previous run still exists. This is actually the desired behavior (documented: "only fire once per session"), but the comment says "once per session" while the implementation is "once per session ID lifetime in /tmp."

**Recommendation:** Document this behavior explicitly. If the intent is truly "once per session run" rather than "once per session ID," the sentinel should include a timestamp or be cleaned up by session-start.sh.

---

## 4. MCP Server Integration

### Current Configuration

Two MCP servers are bundled in `/root/projects/Clavain/.claude-plugin/plugin.json`:

```json
"mcpServers": {
  "context7": {
    "type": "http",
    "url": "https://mcp.context7.com/mcp"
  },
  "qmd": {
    "type": "stdio",
    "command": "qmd",
    "args": ["mcp"]
  }
}
```

### Analysis

**context7** is a remote HTTP MCP server providing runtime documentation fetching. It is also listed as a required companion plugin in `agent-rig.json`. This creates a potential double-registration: if the user has both the Clavain plugin and the standalone `context7` plugin installed, context7 is registered twice. Claude Code may handle this gracefully (deduplication), but it is an architectural smell.

**qmd** is a local stdio MCP server for semantic search. It requires `qmd` to be installed locally (`go install github.com/tobi/qmd@latest`). If `qmd` is not installed, the plugin fails to start the MCP server. The `agent-rig.json` marks qmd as optional (line 98), but the plugin manifest unconditionally registers it.

**Finding 10 (P2): qmd MCP server registration is unconditional but the tool is optional.**

The `plugin.json` always registers the qmd MCP server. If `qmd` is not installed, this produces an error at plugin load time. The `agent-rig.json` correctly marks qmd as optional with a `check` command (`command -v qmd`), but the plugin manifest has no conditional loading mechanism.

**Recommendation:** This is a Claude Code platform limitation -- plugin manifests cannot conditionally register MCP servers. Document this clearly in the README: "qmd must be installed for the Clavain plugin to load without errors. If you don't need local semantic search, you can fork and remove the qmd entry from plugin.json." Alternatively, wrap the qmd command in a shell script that no-ops if qmd is not installed.

**Finding 11 (P3): context7 double-registration risk.**

Both Clavain's `plugin.json` and the standalone `context7` plugin register the same MCP endpoint. If both are installed, tools like `resolve-library-id` and `query-docs` may appear twice in the tool list.

**Recommendation:** Add a note to the setup command (`/clavain:setup`) to detect and warn about the standalone context7 plugin if Clavain is installed, since Clavain bundles it.

---

## 5. Upstream Sync Architecture

### System Overview

The upstream sync system has two layers:

1. **Check system** (lightweight): `scripts/upstream-check.sh` + `.github/workflows/upstream-check.yml` (daily cron). Queries GitHub API for new commits/releases, opens issues with `upstream-sync` label. State tracked in `docs/upstream-versions.json`.

2. **Sync system** (automated merging): `scripts/sync-upstreams.sh` + `.github/workflows/sync.yml` (weekly cron). Clones upstream repos, applies three-way classification (COPY/AUTO/KEEP-LOCAL/CONFLICT/SKIP/REVIEW), uses AI analysis for conflicts, runs namespace replacement and blocklist filtering.

Configuration lives in `upstreams.json` with per-upstream `fileMap` entries and a shared `syncConfig` block for protected files, namespace replacements, and content blocklist.

### Sustainability Assessment

**Finding 12 (P1): sync-upstreams.sh at 1,019 lines has outgrown bash.**

The sync script (`/root/projects/Clavain/scripts/sync-upstreams.sh`) is a sophisticated three-way merge tool with:
- Python subprocesses for JSON parsing (lines 97-120, 185-207, 217-259)
- Namespace replacement logic using bash parameter substitution and sed (lines 146-162)
- AI-assisted conflict resolution via `claude -p` (lines 369-425)
- Interactive TUI with colored output and three-way diff display (lines 431-531)
- Report generation (lines 550-602)
- Main sync loop (lines 607-951)
- Contamination checking (lines 957-988)

This is a hybrid bash/Python script that invokes Python for every JSON operation and bash for file operations. The architecture works but is fragile:
- Inline Python scripts use variable interpolation from bash (`$UPSTREAMS_JSON`, `$upstream_name`), creating injection risks if file paths contain special characters.
- The classify_file function (lines 283-362) compares file contents using bash string equality (`[[ "$upstream_transformed" == "$local_content" ]]`), which works but is memory-inefficient for large files.
- Error handling relies on `set -euo pipefail` globally, but individual Python subprocess failures are not always caught (e.g., line 635 uses bare `python3 -c` without error handling).

**Recommendation:** Rewrite `sync-upstreams.sh` as a Python script. The existing Python subprocesses already handle all the complex logic (JSON parsing, file mapping, glob expansion). A Python rewrite would consolidate the ~15 inline Python snippets, eliminate bash/Python variable interpolation risks, and provide proper error handling. The script is already beyond the maintainability threshold for bash. The AI analysis function (lines 369-425) could remain as a subprocess call to `claude -p` from Python.

**Finding 13 (P2): syncConfig in upstreams.json conflates configuration with state.**

`upstreams.json` contains both upstream definitions (URLs, branches, file maps) and sync state (`lastSyncedCommit`). The `syncConfig` block (protected files, namespace replacements, content blocklist) is configuration that changes rarely, while `lastSyncedCommit` changes on every sync. This means every sync run modifies `upstreams.json`, creating noisy diffs that obscure actual configuration changes.

**Recommendation:** Split `upstreams.json` into two files: `upstreams.json` (static configuration: URLs, file maps, sync config) and `upstream-state.json` (mutable state: last synced commits). This separates concerns and makes configuration reviews cleaner. The state file could be gitignored if sync state is not needed in version control.

**Finding 14 (P2): Namespace replacement is a string-level operation with no awareness of context.**

The `namespaceReplacements` in syncConfig perform global string replacement:
```json
{
  "/compound-engineering:": "/clavain:",
  "/workflows:plan": "/clavain:write-plan",
  "ralph-wiggum:": "clavain:"
}
```

These replacements are applied to entire file contents via `sed -i` (line 160) or bash parameter substitution (line 150). They work for skill/command references but could produce false positives if the replacement strings appear in prose or code comments. For example, a comment saying "this was ported from compound-engineering:" would be incorrectly rewritten.

**Recommendation:** This is acceptable for the current scale (6 upstreams, ~50 mapped files) and the content blocklist provides a second check. If false positives become a problem, consider adding a "replacement context" that only matches within specific patterns (e.g., only replace within markdown link syntax `[text](/compound-engineering:...)` or YAML frontmatter).

**Finding 15 (P3): The content blocklist is a deny-list, not an allow-list.**

The `contentBlocklist` (`rails_model`, `rails_controller`, `hotwire_turbo`, `Every.to`, etc.) catches domain-specific terms that should not appear in Clavain. This is reactive -- it only catches known bad terms. A new upstream might introduce a term not on the blocklist (e.g., `shopify_api` or `sidekiq_job`) that also should not appear.

**Recommendation:** No immediate change. The deny-list approach is practical for the current upstream set. If new upstreams are added, audit their domain-specific terminology and extend the blocklist proactively.

---

## 6. Knowledge Layer

### Architecture

The knowledge layer lives at `/root/projects/Clavain/config/flux-drive/knowledge/`. It consists of markdown files with YAML frontmatter (`lastConfirmed`, `provenance`). The README (`/root/projects/Clavain/config/flux-drive/knowledge/README.md`) documents:

- **Entry format**: finding description + evidence anchors + verification steps
- **Provenance tracking**: `independent` vs `primed` to prevent false-positive feedback loops
- **Decay rules**: entries not independently confirmed in 10 reviews get archived
- **Sanitization rules**: no repo-specific paths, hostnames, or secrets
- **Retrieval**: via qmd semantic search during flux-drive Phase 2, capped at 5 entries per agent

### Assessment

**Finding 16 (P2): Knowledge retrieval depends on qmd but has no integration test.**

The knowledge layer's value proposition depends on qmd being available to perform semantic search during flux-drive reviews. If qmd is not installed or the MCP server fails, "agents run without knowledge injection" (README line 78). There is no test that verifies the knowledge retrieval path works end-to-end.

**Recommendation:** Add a smoke test that indexes the knowledge directory with qmd, performs a search, and verifies results contain at least one entry. This guards against silent failures where qmd is installed but the knowledge directory is not indexed.

**Finding 17 (P3): Only 4 knowledge entries exist (plus an archive directory).**

The current knowledge base is thin:
1. `agent-description-example-blocks-required.md` -- convention enforcement
2. `agent-merge-accountability.md` -- merge mapping completeness
3. `aspirational-execution-instructions.md` -- orchestrator instruction realism
4. `documentation-implementation-format-divergence.md` -- docs/code drift

All 4 entries have `lastConfirmed: 2026-02-10` and `provenance: independent`, suggesting they were all created on the same day from a single flux-drive review. The decay rule (10 reviews without independent confirmation) means these entries have a limited shelf life.

**Recommendation:** This is expected for a young system. The entries are well-formed and follow the documented format. The auto-compound hook (`auto-compound.sh`) detects compoundable signals and prompts knowledge capture, which should naturally grow the knowledge base over time.

**Finding 18 (P3): The provenance tracking is documented but not enforced.**

The README explains the `independent` vs `primed` distinction in detail, but there is no mechanism to enforce it. When an agent produces a finding that matches a knowledge entry, the compounding process must manually set provenance to `primed` if the agent had the entry in its context. There is no tooling to detect whether an agent was given knowledge entries and thus whether a re-confirmation is independent or primed.

**Recommendation:** Add a `knowledge_injected` field to the flux-drive synthesis report that lists which knowledge entries each agent received. This creates an audit trail for provenance decisions.

---

## 7. Agent Consolidation

### Consolidation History

The v1 roster had 19 review agents (language-specific and domain-specific). These were consolidated into 6 core fd-* agents plus 3 standalone agents:

**Core fd-* agents** (at `/root/projects/Clavain/agents/review/`):
- `fd-architecture.md` -- boundaries, coupling, patterns, complexity
- `fd-safety.md` -- security, credentials, trust, deployment
- `fd-correctness.md` -- data integrity, concurrency, async
- `fd-quality.md` -- naming, conventions, idioms
- `fd-user-product.md` -- user flows, UX, product reasoning
- `fd-performance.md` -- bottlenecks, scaling, resources

**Standalone review agents:**
- `plan-reviewer.md` -- lightweight 3-agent plan review
- `agent-native-reviewer.md` -- agent-native architecture review
- `data-migration-expert.md` -- database migration safety

**Research agents** (5): best-practices-researcher, framework-docs-researcher, git-history-analyzer, learnings-researcher, repo-research-analyst

**Workflow agents** (2): bug-reproduction-validator, pr-comment-resolver

### Assessment

**Finding 19 (P3): fd-* agents are well-designed with consistent structure.**

Each fd-* agent follows a common pattern:
1. Mandatory first step: check for CLAUDE.md/AGENTS.md
2. Codebase-aware vs generic mode selection
3. Structured review approach with numbered sections
4. Focus rules and decision lens

The language auto-detection approach (replacing 19 language-specific agents with 6 domain-specific agents that auto-detect) is a correct architectural choice. It reduces the agent roster by 68% while maintaining coverage. The trade-off is that each agent is larger (fd-architecture.md is 82 lines of system prompt), but this is a reasonable context window cost since only 3-8 agents run per review.

**Finding 20 (P2): The knowledge entry about missing example blocks is still applicable.**

The knowledge entry `agent-description-example-blocks-required.md` notes that fd-* agent descriptions lack `<example>` blocks with `<commentary>`. Checking the current agents:

- `fd-architecture.md` description (line 3): No `<example>` blocks.
- `fd-safety.md` description (line 3): No `<example>` blocks.
- All 6 fd-* agents: No `<example>` blocks in descriptions.

The AGENTS.md convention (lines 129-130) explicitly requires: "Description must include concrete `<example>` blocks with `<commentary>` explaining WHY to trigger." The 3 standalone review agents (plan-reviewer, agent-native-reviewer, data-migration-expert) DO have example blocks. Only the 6 fd-* agents violate this convention.

**Recommendation:** Add `<example>` blocks to all 6 fd-* agent descriptions. This is both a convention compliance issue and a practical one: the example blocks help Claude Code's agent selection logic match the right agent to the right task. Without them, the fd-* agents rely solely on the description text for matching, which is less precise than example-based matching.

**Finding 21 (P3): Research and workflow agent categories are stable.**

The 5 research agents and 2 workflow agents have clear, non-overlapping responsibilities:
- Research agents gather information (best practices, framework docs, git history, learnings, repo structure).
- Workflow agents execute process steps (bug reproduction, PR comment resolution).

No consolidation or split is needed here. The categorization is clean.

**Finding 22 (P3): The `references/` directory under `agents/review/` is a potential glob trap.**

The directory `agents/review/references/` contains `concurrency-patterns.md`, which is a reference document, not an agent. The test suite uses explicit category directory globs (`agents/{review,research,workflow}/*.md`) to avoid counting reference files as agents (documented in MEMORY.md: "Agent globs MUST use explicit category dirs"). This is correct but fragile -- if someone adds another file to `references/`, it is silently excluded. And if someone uses a naive `agents/**/*.md` glob, they get inflated counts.

**Recommendation:** No immediate change needed. The current approach works and is documented. Consider adding a structural test that explicitly verifies `agents/review/references/` contains no files with agent-like frontmatter (name + description + model fields).

---

## Cross-Cutting Findings

### Finding 23 (P2): The `agent-rig.json` is a useful but undocumented concept.

The file at `/root/projects/Clavain/agent-rig.json` describes Clavain as a "rig" with plugin dependencies (required, recommended, infrastructure, conflicts), tool requirements, environment variables, and behavioral configuration. This is a more expressive format than `plugin.json` and could serve as a machine-readable modpack descriptor.

However, `agent-rig.json` is not referenced by any workflow, hook, or test. It appears to be informational only. Its version (0.4.29) is bumped by `bump-version.sh` (line 80), but no code reads it.

**Recommendation:** Either integrate `agent-rig.json` into the setup command (`/clavain:setup`) so it can automatically install companion plugins, or document it as a proposed standard. Currently it is maintained effort (version bumps, dependency list updates) with no consumer.

### Finding 24 (P2): bump-version.sh depends on sibling directory layout.

The version bump script (`/root/projects/Clavain/scripts/bump-version.sh`) hardcodes the marketplace path as `$REPO_ROOT/../interagency-marketplace` (line 12). This assumes a specific directory layout where the marketplace repo is a sibling of the Clavain repo. If the repos are in different locations, the script fails with a non-obvious error ("Marketplace repo not found").

**Recommendation:** Make the marketplace path configurable via an environment variable with a fallback to the sibling directory convention. For example: `MARKETPLACE_ROOT="${MARKETPLACE_ROOT:-$REPO_ROOT/../interagency-marketplace}"`.

### Finding 25 (P3): lib.sh escape_for_json handles control characters thoroughly.

The shared utility at `/root/projects/Clavain/hooks/lib.sh` implements JSON string escaping using pure bash parameter substitution. The implementation correctly handles all ASCII control characters (0-31), not just the common ones (newline, tab, carriage return). The loop on lines 16-22 handles the remaining control characters with `\u00XX` escapes. This is thorough and correct.

---

## Prioritized Recommendations

### Must-Fix (P1)

1. **Fix count drift in `using-clavain/SKILL.md` and `agent-rig.json`.** The routing table injected into every session says "34 skills" and "23 commands" but reality is 33 skills and 25 commands. This creates immediate user confusion. Files: `/root/projects/Clavain/skills/using-clavain/SKILL.md` line 24, `/root/projects/Clavain/agent-rig.json` line 4.

2. **Rewrite `sync-upstreams.sh` in Python.** At 1,019 lines with 15 inline Python subprocesses, the script has outgrown bash. The hybrid architecture creates injection risks and makes error handling difficult. File: `/root/projects/Clavain/scripts/sync-upstreams.sh`.

### Should-Fix (P2)

3. **Add coordination between Stop hooks.** The two Stop hooks (`auto-compound.sh` and `session-handoff.sh`) can create a compound-after-handoff loop. Add a shared sentinel mechanism.

4. **Add `<example>` blocks to all 6 fd-* agent descriptions.** Convention violation that reduces agent selection accuracy. Files: `/root/projects/Clavain/agents/review/fd-*.md`.

5. **Address qmd unconditional registration.** The plugin manifest always registers qmd but the tool is optional. Either document the requirement clearly or wrap the command in a no-op shell script.

6. **Split upstreams.json into config and state.** Separating mutable sync state from static configuration reduces diff noise.

7. **Consolidate review orchestration.** The `review` command hardcodes agent selection while `flux-drive` and `quality-gates` do dynamic selection. Consider having `review` delegate to `flux-drive`.

### Nice-to-Have (P3)

8. **Delete redirect stub skills** (`prompterpeer`, `winterpeer`, `splinterpeer`) or add `deprecated: true` frontmatter.

9. **Add knowledge retrieval integration test** to verify the qmd -> knowledge -> agent injection path.

10. **Make bump-version.sh marketplace path configurable** via environment variable.

11. **Add provenance audit trail** to flux-drive synthesis report for knowledge layer feedback loop prevention.

12. **Add structural test for agent reference files** to catch glob trap in `agents/review/references/`.

---

## Architecture Diagram (Current State)

```
User Input
    |
    v
[SessionStart Hook]
    |-- injects using-clavain/SKILL.md (6.4KB routing table)
    |-- detects companions (beads, oracle)
    |-- warns if upstream stale
    |
    v
[3-Layer Routing]
    |-- Stage (explore/plan/execute/debug/review/ship/meta)
    |-- Domain (code/data/deploy/docs/research/workflow/design/infra)
    |-- Concern (architecture/safety/correctness/quality/user-product/performance)
    |
    +-- Commands (/clavain:*) --> orchestrate skills + agents
    |     |-- flux-drive: 4-phase scored review (triage->launch->synthesize->cross-ai)
    |     |-- quality-gates: quick diff-based review
    |     |-- review: PR-focused multi-agent review
    |     |-- lfg: full workflow macro
    |     +-- 21 others
    |
    +-- Skills (Skill tool) --> process/domain knowledge
    |     |-- 33 skills across 8 domains
    |     +-- 3 redirect stubs (prompterpeer/winterpeer/splinterpeer)
    |
    +-- Agents (Task tool) --> isolated subagent execution
          |-- 6 core fd-* review agents (auto-detect language + project docs)
          |-- 3 standalone review agents
          |-- 5 research agents
          +-- 2 workflow agents

[PreToolUse Hook: autopilot.sh]
    |-- gates source code writes when clodex mode active

[Stop Hooks]
    |-- auto-compound.sh: detects compoundable signals, prompts /compound
    +-- session-handoff.sh: detects incomplete work, prompts HANDOFF.md

[SessionEnd Hook: dotfiles-sync.sh]
    |-- syncs config changes to dotfiles repo

[MCP Servers]
    |-- context7 (HTTP): runtime documentation fetching
    +-- qmd (stdio): local semantic search

[Knowledge Layer: config/flux-drive/knowledge/]
    |-- 4 entries with provenance tracking
    |-- retrieved via qmd during flux-drive Phase 2
    +-- decay: archive after 10 unconfirmed reviews

[Upstream Sync]
    |-- 6 upstreams (beads, oracle, superpowers x3, compound-engineering)
    |-- daily check (GitHub Actions -> issues)
    |-- weekly sync (GitHub Actions -> PR with decision gate)
    +-- file maps in upstreams.json with namespace replacement
```

---

## Conclusion

Clavain's architecture is fundamentally sound. The 3-layer routing system solves a real organizational problem. The flux-drive review engine with scored triage and phased execution is well-engineered. The hook lifecycle management is thoughtful, with appropriate async/sync choices and graceful degradation.

The primary areas of concern are operational rather than structural:
- **Count drift** is the most visible issue (P1) and the easiest to fix.
- **sync-upstreams.sh** is the largest maintenance risk -- it works today but will become increasingly fragile as upstreams evolve.
- **Stop hook coordination** is a latent bug that will manifest as user-visible loops when both hooks fire in the same session.

The agent consolidation from 19 to 6+3 was a correct architectural decision that reduced surface area by 68%. The knowledge layer is well-designed with anti-feedback-loop mechanisms, though it needs time to accumulate entries.

No broad rewrites are recommended. The must-fix items are surgical corrections to existing components.
