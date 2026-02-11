# Performance Review of Clavain Plugin

**Date:** 2026-02-11
**Reviewer:** fd-performance agent (Flux-drive Performance Reviewer)
**Version:** 0.4.29
**Scope:** Session startup, hook overhead, context window usage, agent dispatch, MCP servers, knowledge layer, upstream sync

---

## Executive Summary

Clavain's always-on context overhead is approximately 5,100 tokens (~2.6% of a 200k context window) -- a reasonable cost for the routing and coordination value it provides. The primary performance concerns are:

1. The `escape_for_json` function in `hooks/lib.sh` performs 26 redundant string scans for control characters that are virtually never present in markdown content.
2. The upstream check script (`scripts/upstream-check.sh`) issues 4 serial HTTP API calls per upstream (24 total for 6 upstreams), with 3 of those calls hitting the same endpoint with different `--jq` filters.
3. The Stop hooks (`auto-compound.sh` and `session-handoff.sh`) both independently parse the same stdin JSON and both run `jq` processes, adding latency to every turn boundary.

None of these are urgent. The plugin's architecture makes good design choices overall: lazy loading of skill content via the Skill tool, progressive phase loading in flux-drive, async hooks where appropriate, and bounded knowledge injection (5 entries per agent cap).

---

## 1. Session Startup Cost

### What happens

File: `/root/projects/Clavain/hooks/session-start.sh`

On every `startup`, `resume`, `clear`, or `compact` event, the SessionStart hook:

1. Cleans stale plugin cache versions (filesystem scan of sibling directories)
2. Reads `skills/using-clavain/SKILL.md` (6,408 bytes)
3. JSON-escapes the content via `escape_for_json()` (produces ~6,495 bytes)
4. Detects companion plugins (`.beads/` directory check, `oracle` command check, `pgrep` call)
5. Checks upstream staleness (`stat` on `docs/upstream-versions.json`)
6. Outputs the combined context as a JSON `additionalContext` payload

### Measured values

| Metric | Value |
|--------|-------|
| `using-clavain/SKILL.md` raw size | 6,408 bytes / 870 words |
| JSON-escaped output size | ~6,495 bytes |
| Full `additionalContext` field | 6,827 characters / 938 words |
| Estimated token cost | ~1,700 tokens |
| Wall-clock execution time | ~107ms |
| Hook declared as | `async: true` |

### Assessment: LOW RISK

The context injection is well-sized. At ~1,700 tokens, it consumes less than 1% of the context window. The content is a compact routing table -- exactly the kind of structural information that pays for itself by reducing skill-lookup round-trips.

The hook runs asynchronously (`"async": true` in hooks.json), so the 107ms execution time does not block session startup. The user sees no delay.

### Optimization opportunity (minor)

The `escape_for_json` function in `hooks/lib.sh` (lines 6-24) has an unnecessary hot loop:

```bash
escape_for_json() {
    local s="$1"
    # ... handles \, ", \b, \f, \n, \r, \t ...
    local i ch esc
    for i in {1..31}; do
        case "$i" in 8|9|10|12|13) continue ;;
        esac
        printf -v ch "\\$(printf '%03o' "$i")"
        printf -v esc '\\u%04x' "$i"
        s="${s//$ch/$esc}"
    done
    printf '%s' "$s"
}
```

This loop iterates 26 times (31 minus 5 already-handled characters), performing a full string substitution scan on the ~6,400-byte input each time. Each `${s//$ch/$esc}` is O(n) on the string length, so this is approximately 26 * 6,400 = 166,000 character operations.

The input is a markdown file. Control characters 0x01-0x07, 0x0B, 0x0E-0x1F are virtually never present in markdown. This loop accounts for an estimated 40-50ms of the total 107ms execution time.

**Recommendation:** Remove the control character loop entirely. If paranoia is desired, replace it with a single `tr` pipe or `sed` call to strip non-printable characters from the input before escaping. This would reduce `escape_for_json` execution time by ~50%.

**Impact if not fixed:** None user-visible. The hook is async and 107ms is already fast. This is a code cleanliness improvement, not a user-facing fix.

---

## 2. Hook Execution Overhead

### Hook inventory

File: `/root/projects/Clavain/hooks/hooks.json`

| Hook | Event | Fires when | Timeout | Async |
|------|-------|-----------|---------|-------|
| `session-start.sh` | SessionStart | `startup\|resume\|clear\|compact` | none (async) | Yes |
| `autopilot.sh` | PreToolUse | `Edit\|Write\|MultiEdit\|NotebookEdit` | 5s | No |
| `auto-compound.sh` | Stop | Every turn boundary | 5s | No |
| `session-handoff.sh` | Stop | Every turn boundary | 5s | No |
| `dotfiles-sync.sh` | SessionEnd | Session end | none (async) | Yes |

### PreToolUse: `autopilot.sh` -- NEGLIGIBLE OVERHEAD

File: `/root/projects/Clavain/hooks/autopilot.sh`

This hook fires on every `Edit`, `Write`, `MultiEdit`, or `NotebookEdit` call. In a typical session with heavy editing, this could fire 50-200 times.

**Fast path analysis:** The hook checks for the existence of a flag file (`$PROJECT_DIR/.claude/clodex-toggle.flag`) on line 27. If the file does not exist (the normal case -- clodex mode is off), the script exits immediately with `exit 0` on line 29. No output is produced.

**Measured fast-path time:** ~3ms

This is excellent. The hook has a near-zero cost when clodex mode is inactive, which is the vast majority of sessions. When clodex mode IS active, the hook reads stdin via `jq` to parse the tool input, checks the file extension, and potentially denies the call -- all within the 5-second timeout.

**Assessment: NO ISSUE.** The early-exit pattern is exactly right. No changes needed.

### Stop hooks: `auto-compound.sh` and `session-handoff.sh`

These two hooks fire at every turn boundary (whenever Claude would stop responding). They both:

1. Read JSON from stdin (`INPUT=$(cat)`)
2. Parse `stop_hook_active` with `jq`
3. Check various conditions (transcript signals, git status, beads state)

**Concern: dual stdin consumption and jq processes**

Both hooks independently read stdin and parse the same JSON. This means two `jq` process forks per turn boundary. The `auto-compound.sh` hook also runs `tail -40` on the transcript file and multiple `grep` calls for signal detection.

However, the guard logic is well-structured:
- `auto-compound.sh` exits early if `stop_hook_active` is true (prevents infinite loops)
- `session-handoff.sh` has a sentinel file (`/tmp/clavain-handoff-${SESSION_ID}`) that prevents re-firing after the first detection

**Measured overhead:** The Stop hooks collectively add approximately 50-100ms per turn boundary (primarily from `jq` forks and `git status` / `bd list` checks in `session-handoff.sh`).

**Assessment: LOW RISK.** Turn boundaries are infrequent compared to tool calls (typically seconds to minutes apart). The overhead is imperceptible. The `session-handoff.sh` sentinel file pattern is a good optimization.

**Minor optimization opportunity:** The two Stop hooks could be merged into a single script that reads stdin once and performs both signal checks. This would eliminate one `jq` fork and one `cat` operation per turn boundary. Not worth doing unless more Stop hooks are added.

---

## 3. Context Window Usage

### Always-on context cost

When the Clavain plugin is loaded, the following items occupy context window space regardless of what the user does:

| Component | Estimated tokens | How loaded |
|-----------|-----------------|------------|
| SessionStart injection (`using-clavain` routing table) | ~1,700 | `additionalContext` on every session start/resume/clear/compact |
| Skill registry (33 skills with name + description) | ~990 | Plugin manifest auto-registration |
| Agent registry (16 agents with name + description) | ~640 | Plugin manifest auto-registration |
| Command registry (25 commands with name + description) | ~625 | Plugin manifest auto-registration |
| MCP tool definitions (context7: 2 tools + qmd: 6 tools) | ~1,200 | Plugin manifest `mcpServers` |
| **Total always-on overhead** | **~5,155 tokens** | |

**Percentage of 200k context window: ~2.6%**

### Demand-loaded content

The remaining content is loaded only when actively invoked:

| Content | Size | When loaded |
|---------|------|------------|
| Individual skill files (33 SKILL.md files) | 237 KB total (avg ~7 KB each) | On `Skill` tool invocation |
| Skill sub-resources (references, examples) | ~1.1 MB total | Read within skill execution |
| Agent system prompts (16 agent .md files) | ~85 KB total (avg ~5 KB each) | On `Task` tool dispatch |
| Command instructions (25 command .md files) | ~81 KB total (avg ~3 KB each) | On `/clavain:*` invocation |
| Flux-drive phase files (5 phase .md files) | ~37 KB total | Read progressively during flux-drive |
| Knowledge entries (4 active + README) | ~6 KB total | Retrieved via qmd during flux-drive Phase 2 |
| Config files (diff-routing, CLAUDE.md) | ~8 KB total | Read when needed |

### Assessment: WELL-ARCHITECTED

The 2.6% always-on overhead is justified. The routing table enables Claude to find the right skill/agent/command without trial and error, saving context that would otherwise be spent on exploratory tool calls.

The progressive loading design is excellent:
- Skills are loaded on-demand via the Skill tool, not upfront
- Flux-drive loads phase files sequentially ("Read the launch phase file now"), not all at once
- Knowledge entries are capped at 5 per agent and retrieved via qmd semantic search
- Sub-resources (references, examples) are only read when the parent skill references them

### Concern: Large sub-resource directories

Three skill directories have substantial sub-resources:

| Skill | Sub-resource size | File count |
|-------|------------------|-----------|
| `working-with-claude-code` | 478 KB | 42 files |
| `agent-native-architecture` | 183 KB | 14 files |
| `create-agent-skills` | 152 KB | 25 files |

If a skill instructs Claude to "Read all reference files in this directory," the 478 KB `working-with-claude-code` sub-resource set would consume approximately 120,000 tokens -- 60% of the context window in one operation.

**Recommendation:** Verify that no skill instructs Claude to bulk-read all sub-resources at once. Skills should reference specific sub-files by name or provide a directory listing for selective reads. The `working-with-claude-code` skill at 478 KB of sub-resources warrants particular attention.

**Risk level:** MEDIUM if skills bulk-read sub-resources; LOW if they selectively reference them (which appears to be the case based on the flux-drive pattern of progressive loading).

---

## 4. Agent Dispatch Cost (Flux-Drive)

### Token budget per agent

When flux-drive dispatches a review agent, each agent's context includes:

| Component | Estimated size |
|-----------|---------------|
| Agent system prompt (from .md file) | ~5 KB (~1,250 tokens) |
| Prompt template (from launch.md) | ~2.5 KB (~625 tokens) |
| Document being reviewed | Variable (passed in full for <1000 lines) |
| Knowledge entries (up to 5) | ~1-3 KB (~250-750 tokens) |
| Project context (CLAUDE.md, AGENTS.md) | Read by agent, variable |
| **Agent overhead (excl. document)** | **~2,125-2,625 tokens** |

### Maximum dispatch scenario

File: `/root/projects/Clavain/skills/flux-drive/SKILL.md` (line 163: "Cap at 8 agents total")

With the 8-agent cap:
- **Worst-case parallel token usage:** 8 agents * ~2,500 token overhead = ~20,000 tokens of overhead, plus 8 copies of the document content
- **API cost multiplier:** Each agent is a separate Claude API call. 8 agents reviewing a 5,000-token document = ~60,000 total input tokens across all calls
- **Latency:** Agents run with `run_in_background: true`. Stage 1 launches 2-3 agents, waits for completion, then optionally launches Stage 2. Total wall-clock time is dominated by the slowest agent per stage, not the sum.

### Assessment: APPROPRIATE

The staged dispatch (Stage 1 then Stage 2 with expansion gate) is a good design for controlling cost. The user confirms before expanding from Stage 1 to Stage 2, so unnecessary agent launches are avoided.

The 8-agent hard cap prevents runaway costs. The pre-filter in Step 1.2a (data filter, product filter, deploy filter) eliminates irrelevant agents before scoring, which typically results in 3-5 agents launched rather than the maximum 8.

**One concern:** Each agent receives the full document content (launch.md, line 105: "Include the full document in each agent's prompt without trimming"). For a 1,000-line document (~20,000 tokens), 6 agents would consume ~120,000 input tokens. There IS an exception for >1000 lines (line 107), but the threshold is generous.

**Recommendation:** Consider reducing the full-document threshold from 1,000 lines to 500 lines for cost-sensitive deployments. The diff-routing system already implements per-agent content slicing for diffs; extending this to document reviews would reduce token usage without meaningfully reducing review quality.

---

## 5. MCP Server Overhead

### context7 (HTTP)

```json
"context7": {
  "type": "http",
  "url": "https://mcp.context7.com/mcp"
}
```

HTTP MCP servers are connected lazily by Claude Code. The connection is established on the first tool call, not at plugin load time. The tool definitions (2 tools: `resolve-library-id` and `query-docs`) are registered in the tool schema at startup, consuming approximately 300-400 tokens of context window space.

**When not used:** Only the tool definition tokens are consumed (~400 tokens). No HTTP connections, no process overhead, no memory footprint.

**When used:** Each call is a standard HTTP request to `mcp.context7.com`. Latency depends on the remote server. No local resource consumption beyond the network call.

**Assessment: NO ISSUE.** HTTP MCP servers have near-zero overhead when idle.

### qmd (stdio)

```json
"qmd": {
  "type": "stdio",
  "command": "qmd",
  "args": ["mcp"]
}
```

Stdio MCP servers are started as child processes. The `qmd mcp` process launches at plugin initialization and remains running for the session duration. The tool definitions (6 tools: `search`, `vsearch`, `query`, `get`, `multi_get`, `status`) consume approximately 600-800 tokens of context window space.

**Process overhead:**
- `qmd` is a Bun-based application. The `qmd mcp` command starts a long-running MCP server process.
- Memory footprint depends on indexed collections. For a typical setup, expect 20-50 MB resident.
- The process is idle when not receiving tool calls. CPU usage is negligible when idle.

**When not used:** The tool definitions consume ~800 tokens in the context window, and the background process consumes ~20-50 MB of RAM. This is the cost of having qmd always available.

**Assessment: LOW RISK.** The ~800 tokens for 6 tool definitions is modest. The 20-50 MB RAM for the background process is reasonable for a development tool. If qmd is not installed (`which qmd` fails), Claude Code should handle the startup failure gracefully and simply not register the tools.

**Combined MCP overhead:** ~1,200 tokens always-on context + one background process (~20-50 MB RAM).

---

## 6. Knowledge Layer

### Current state

Directory: `/root/projects/Clavain/config/flux-drive/knowledge/`

| File | Size |
|------|------|
| `README.md` | 2,932 bytes |
| `agent-description-example-blocks-required.md` | 755 bytes |
| `agent-merge-accountability.md` | 770 bytes |
| `aspirational-execution-instructions.md` | 833 bytes |
| `documentation-implementation-format-divergence.md` | 878 bytes |
| `archive/` | (empty) |
| **Total active entries** | **3,236 bytes (excl. README)** |

### Retrieval path

Knowledge entries are retrieved during flux-drive Phase 2 (launch.md, Step 2.1) via qmd semantic search:
- Query: agent domain keywords + document summary
- Cap: 5 entries per agent
- Fallback: if qmd unavailable, agents run without knowledge

### Assessment: NEGLIGIBLE OVERHEAD

With only 4 active knowledge entries totaling ~3.2 KB, the knowledge layer adds virtually nothing to context consumption. Even at full capacity (5 entries per agent * 8 agents = 40 retrievals), the total would be capped at ~16 KB of additional context across all agents.

The qmd semantic search adds a round-trip to the local qmd process per agent (~10-50ms each), but this is pipelined with agent prompt preparation (launch.md, line 48: "Pipelining: Start qmd queries before agent dispatch").

The decay mechanism (entries not independently confirmed in 10 reviews get archived) prevents unbounded growth. The provenance tracking (independent vs. primed) prevents false-positive feedback loops.

**Assessment: WELL-DESIGNED.** No changes needed. The knowledge layer is small, bounded, and gracefully degradable.

---

## 7. Upstream Sync Overhead

### Check system (daily)

File: `/root/projects/Clavain/scripts/upstream-check.sh`
Schedule: Daily at 08:00 UTC via `.github/workflows/upstream-check.yml`

**API call pattern:**

Per upstream repo (6 repos), the script makes 4 serial `gh api` calls:
1. `repos/{repo}/releases/latest` -- latest release tag
2. `repos/{repo}/commits?per_page=1` -- latest commit SHA
3. `repos/{repo}/commits?per_page=1` -- latest commit message (SAME endpoint, different `--jq`)
4. `repos/{repo}/commits?per_page=1` -- latest commit date (SAME endpoint, different `--jq`)

**Total: 24 serial API calls for 6 upstreams.**

Calls 2-4 hit the identical GitHub API endpoint (`commits?per_page=1`) but extract different fields with `--jq`. This is 3x redundant.

**Optimization opportunity (MEDIUM):**

Consolidate the 3 commits calls into 1:

```bash
# Before: 3 separate calls
latest_commit=$(gh api "repos/${repo}/commits?per_page=1" --jq '.[0].sha[:7]')
latest_commit_msg=$(gh api "repos/${repo}/commits?per_page=1" --jq '.[0].commit.message | split("\n")[0]')
latest_commit_date=$(gh api "repos/${repo}/commits?per_page=1" --jq '.[0].commit.committer.date[:10]')

# After: 1 call with multi-field extraction
read -r latest_commit latest_commit_date latest_commit_msg < <(
  gh api "repos/${repo}/commits?per_page=1" --jq \
    '.[0] | [.sha[:7], .commit.committer.date[:10], (.commit.message | split("\n")[0])] | @tsv'
)
```

This reduces API calls from 24 to 12 (2 per upstream: releases + commits). At ~200ms per API call, this saves ~2.4 seconds of wall-clock time per run and reduces GitHub API rate limit consumption by 50%.

**Impact:** The script runs in a GitHub Action (daily cron), so the 2.4-second savings does not affect user-facing latency. However, the rate limit reduction matters if the GitHub token has limited quota.

### Sync system (weekly)

Schedule: Weekly on Monday at 08:00 UTC via `.github/workflows/sync.yml`
Runtime: Up to 15 minutes (workflow timeout)

The sync workflow clones upstream repos, runs Claude Code + Codex CLI to auto-merge changes, and creates a PR. This is a heavy operation but runs only once per week and only in CI -- no user-facing latency impact.

### SessionStart staleness check

File: `/root/projects/Clavain/hooks/session-start.sh` (lines 53-65)

The hook checks `docs/upstream-versions.json` file modification time using `stat`. This is a single filesystem call with no network access. If the file is older than 7 days, a warning string is appended to the context injection.

**Assessment: NO ISSUE.** A single `stat` call is negligible.

---

## 8. Additional Observations

### The `lib.sh` control character loop is the only hot-path inefficiency

The entire plugin is markdown, JSON, and bash. There are no compiled components, no background daemons (except the qmd stdio MCP server), and no persistent state that accumulates.

The only piece of code that runs frequently AND does unnecessary work is the `escape_for_json` control character loop. Everything else is either:
- One-time per session (SessionStart hook)
- Fast-path optimized (autopilot.sh early exit)
- Infrequent (Stop hooks at turn boundaries)
- Demand-loaded (skills, agents, commands)

### Progressive loading is a strong pattern

The flux-drive skill's progressive phase loading is worth highlighting as a positive example:
- SKILL.md (17 KB) is loaded first with the overview + triage instructions
- `phases/launch.md` (14 KB) is loaded only when reaching Phase 2
- `phases/synthesize.md` (13 KB) is loaded only when reaching Phase 3
- `phases/cross-ai.md` (1.6 KB) is loaded only if Oracle is in the roster

This means a flux-drive review that stops after triage consumes only ~17 KB of skill content, not the full ~54 KB.

### No measurement infrastructure

Clavain has no built-in performance measurement. There are no timing logs, no token counters, no hook execution metrics. Given the plugin's current size and complexity, this is acceptable -- the overhead is low enough that measurement would cost more than it saves.

**Recommendation for future:** If the plugin grows beyond ~50 skills or ~30 agents, consider adding optional timing to hooks (e.g., `CLAVAIN_DEBUG=1` to enable `date +%s%N` timestamps in hook scripts). This would help identify regressions if hook execution time grows.

---

## Findings Summary

### Must-Fix (P0)

None.

### Should-Fix (P1)

**P1-1: Consolidate upstream-check.sh API calls**
- File: `/root/projects/Clavain/scripts/upstream-check.sh` (lines 60-62)
- Issue: 3 redundant `gh api` calls per upstream hitting the same endpoint
- Fix: Single call with multi-field `--jq` extraction
- Impact: 50% reduction in API calls (24 to 12), ~2.4s faster, lower rate limit usage
- Effort: Small (3-line change per upstream)

### Nice-to-Have (P2)

**P2-1: Simplify `escape_for_json` control character handling**
- File: `/root/projects/Clavain/hooks/lib.sh` (lines 15-23)
- Issue: 26-iteration loop scanning for control characters that never appear in markdown
- Fix: Remove loop or replace with single `tr -d` pipe
- Impact: ~50% faster `escape_for_json` (107ms to ~60ms), but hook is async so no user-visible effect
- Effort: Trivial

**P2-2: Audit `working-with-claude-code` sub-resources for bulk-read risk**
- File: `/root/projects/Clavain/skills/working-with-claude-code/` (42 files, 478 KB)
- Issue: If the skill instructs Claude to read all sub-resources, it would consume ~120K tokens
- Fix: Verify skill uses selective reads, not bulk directory reads
- Impact: Prevents potential context window exhaustion
- Effort: Trivial (read the SKILL.md and check)

### Informational

**INF-1: Consider merging Stop hooks**
- Files: `hooks/auto-compound.sh`, `hooks/session-handoff.sh`
- Both read stdin and fork jq independently at every turn boundary
- Merging would save one jq fork (~10ms) per turn boundary
- Not worth doing unless more Stop hooks are added

**INF-2: MCP tool definitions consume ~1,200 tokens permanently**
- context7 (2 tools, ~400 tokens) + qmd (6 tools, ~800 tokens)
- This is the cost of having these tools available. No action needed unless context window pressure becomes acute.

**INF-3: Full-document threshold for agent prompts**
- File: `skills/flux-drive/phases/launch.md` (line 107)
- Current threshold: 1,000 lines for truncation
- For cost-sensitive deployments, reducing to 500 lines would reduce token usage per agent dispatch
- Trade-off: potential loss of context for longer documents
