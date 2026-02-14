# Architecture Review: Intermute-Clavain Integration Design

**Date:** 2026-02-14
**Reviewer:** fd-architecture agent
**Document Under Review:** `docs/brainstorms/2026-02-14-intermute-clavain-integration-brainstorm.md`

## Executive Summary

The two-layer architecture (Intermute enrichments + Clavain/interlock integration) demonstrates strong boundary separation with clear ownership. The companion plugin decision (Option B: "interlock") aligns with Clavain's established extraction pattern and minimizes coupling. However, the design contains 4 must-fix coupling risks, 2 anti-patterns, and 6 unnecessary abstractions that should be cut before implementation.

**Verdict:** Structurally sound with significant cleanup needed. The core architecture is correct but over-specified.

---

## 1. Boundaries & Coupling Analysis

### 1.1 Two-Layer Architecture Separation

**Assessment: WELL-SEPARATED with one coupling risk**

**Layer 1 (Intermute Go enrichments):**
- Circuit breaker, retry logic, signal files, session identity, stale cleanup
- All changes are internal to Intermute's Go codebase
- No Clavain-specific logic leaks into Intermute
- Boundary: HTTP/MCP API surface

**Layer 2 (Clavain/interlock integration):**
- MCP tools, hooks (SessionStart, PreToolUse, Stop), interline integration
- All changes are client-side, consume Intermute's API
- Boundary: HTTP client + MCP protocol

**Coupling Risk Identified:**

**CR-1: MCP Server Placement Creates Dual-Protocol Maintenance**

The design proposes BOTH an HTTP server (existing) AND an MCP server (new) in the same Intermute binary. This creates two protocol surfaces for the same underlying operations:

```
Client Path 1: Hook scripts → curl → HTTP API → Store
Client Path 2: MCP tools → stdio → MCP server → Store
```

**Problem:** Any schema change to reservations or messaging requires updates to BOTH protocol layers. The MCP server is essentially a duplicate client surface.

**Recommendation:** Keep MCP server SEPARATE from Intermute. Create a thin MCP shim binary that wraps HTTP calls to Intermute. This follows the "dumb edge, smart center" pattern and allows Intermute to remain protocol-agnostic.

**Revised structure:**
```
Intermute Go binary → HTTP API only
interlock companion → MCP server (stdio, wraps HTTP calls)
```

This eliminates the dual-protocol maintenance burden and keeps Intermute's scope focused.

---

### 1.2 Companion Plugin Decision (Option B: "interlock")

**Assessment: CORRECT CHOICE**

**Why Option B is right:**
1. Follows established inter* extraction pattern (interphase, interline, interflux, interpath, interwatch)
2. Keeps Clavain's hook count manageable (already at 7 hooks)
3. Allows non-Clavain users to adopt Intermute coordination (Autarch already uses Intermute)
4. Clear ownership boundary: interlock owns coordination UX, Intermute owns state + API

**Why Option A is wrong:**
- Adding MCP server directly to Intermute violates single-responsibility principle
- Intermute becomes Claude Code-specific instead of general-purpose coordination service
- Autarch's integration would need to bypass the MCP layer (architectural split)

**Why Option C is wrong:**
- Clavain already has 7 hooks, 27 skills, 36 commands
- Adding 3+ hooks + 9+ MCP tools + skills directly increases Clavain's complexity footprint
- Violates Clavain's "general-purpose only" constraint (coordination is domain-specific to multi-agent workflows)

**Conclusion:** Option B is the only architecturally sound choice.

---

### 1.3 Coupling Risks: Intermute ↔ Clavain ↔ interlock ↔ interline

**CR-2: Interline's Signal File Format Dependency**

Section 2c proposes interline reads `/tmp/intermute-signal-*.json` directly:

```bash
SIGNAL_TYPE=$(jq -r '.type' "$INTERMUTE_SIGNAL")
```

**Problem:** Interline now depends on Intermute's internal signal schema. Any schema change to `SignalEvent` breaks interline's statusline parsing.

**Fix:** Interlock should provide a normalized schema adapter:
```bash
# interlock's script layer
/usr/local/bin/interlock-signal-reader.sh → reads raw signal → outputs normalized format
```

Interline reads interlock's normalized format, NOT Intermute's raw signals. This insulates interline from Intermute schema churn.

**Recommended normalized schema:**
```json
{
  "layer": "coordination",
  "icon": "🔒",
  "text": "BlueTiger reserved src/*.go",
  "priority": 3
}
```

Interline's statusline already has a 4-layer priority system. This fits cleanly into its "dispatch state > bead context > workflow phase > clodex mode" hierarchy.

---

**CR-3: SessionStart Hook's Direct HTTP Dependency**

Section 2b proposes Clavain's SessionStart hook calls `curl http://localhost:7338/api/agents` directly.

**Problem:** This creates a hard dependency from Clavain → Intermute. If Intermute changes its port, endpoint structure, or auth scheme, Clavain's hook breaks.

**Fix:** Move agent registration into interlock's SessionStart hook, NOT Clavain's. Clavain's hook should delegate:

```bash
# Clavain's hooks/session-start.sh
if command -v interlock-register >/dev/null 2>&1; then
    interlock-register "$SESSION_ID" "$(pwd)" > /tmp/interlock-agent-${SESSION_ID}.json
fi
```

Interlock owns the HTTP protocol details. Clavain reads the result file for `AGENT_ID` if needed.

**Pattern:** This mirrors interphase's lib-gates.sh delegation — Clavain shims, companions implement.

---

**CR-4: PreToolUse:Edit Hook Blocking Decision Creates Edit Latency**

Section 2b proposes blocking Edit tool calls with a synchronous HTTP check:

```bash
curl -sf "http://localhost:7338/api/reservations/check?project=$(pwd)&path=${FILE_PATH}"
```

**Problem:** This adds network latency (5-50ms) to EVERY edit operation, even when Intermute is not running. This violates the "fast path for common case" principle.

**Fix:** Make the check async and advisory, not blocking:

1. PostToolUse:Edit hook (AFTER edit completes) checks for conflicts
2. If conflict detected, emit a warning message + signal file
3. Agent can choose to release-and-retry or coordinate with the other agent
4. For strict enforcement, use Git pre-commit hooks (Section 1f) instead

**Rationale:** Edit-time blocking creates UX friction. Commit-time enforcement is where conflicts actually matter (when work is persisted).

---

### 1.4 Data Flow End-to-End

**Trace: Agent wants to edit `router.go`**

**Current proposal:**
```
1. Claude calls Edit tool
2. PreToolUse:Edit hook fires
3. Hook calls curl → Intermute /api/reservations/check
4. Intermute queries SQLite
5. Returns conflict status
6. Hook blocks or allows
7. Edit proceeds (if allowed)
```

**Revised (fixing CR-4):**
```
1. Claude calls Edit tool
2. Edit proceeds immediately
3. PostToolUse:Edit hook fires (async)
4. Hook calls interlock-check-conflicts.sh
5. Interlock calls Intermute HTTP API
6. If conflict, emit warning + update signal file
7. Interline shows conflict warning in statusline
```

**Trace: Agent registers at session start**

**Current proposal:**
```
1. Clavain SessionStart hook
2. Calls curl → Intermute /api/agents
3. Parses response, writes AGENT_ID to CLAUDE_ENV_FILE
```

**Revised (fixing CR-3):**
```
1. Clavain SessionStart hook
2. Calls interlock-register (if installed)
3. Interlock calls Intermute HTTP API
4. Interlock writes /tmp/interlock-agent-${SESSION_ID}.json
5. Clavain reads file, exports INTERMUTE_AGENT_ID to CLAUDE_ENV_FILE
```

**Analysis:** Both traces now have clear ownership boundaries:
- Intermute: State + API
- interlock: Protocol adapter + coordination UX
- Clavain: Delegation + environment setup

---

## 2. Pattern Analysis

### 2.1 Identified Design Patterns

**Well-Applied Patterns:**

1. **Companion extraction** (interlock) — matches interphase, interline, interflux, interpath, interwatch
2. **Shim delegation** (env var → find in plugin cache) — established in hooks/lib-discovery.sh
3. **File-based sideband** (`/tmp/*.json`) — existing pattern for dispatch state, bead context
4. **Graceful degradation** (curl -sf fails silently) — matches interphase's no-op stubs
5. **Session identity via CLAUDE_ENV_FILE** — established in SessionStart hook for interphase integration

**Patterns Correctly Avoided:**

- No branching/worktrees (Clavain's "trunk-based" constraint)
- No Rails/Ruby/domain-specific logic (general-purpose only)
- No duplicate MCP servers in Clavain (separation via companion)

---

### 2.2 Anti-Patterns Detected

**AP-1: Dual Protocol Surface (HTTP + MCP in same binary)**

Already covered in CR-1. This is a **dual client interface** anti-pattern. Every feature needs two implementations.

**Fix:** Extract MCP server to interlock companion. Intermute stays HTTP-only.

---

**AP-2: God Module Risk in Intermute**

The design proposes adding 6 major features to Intermute in one pass:
1. Circuit breaker
2. Retry with jitter
3. Signal files
4. Session identity
5. Stale lock cleanup
6. Reservation conflict detection API
7. Git hook generation
8. MCP server

**Problem:** This increases Intermute's scope from "coordination service" to "coordination service + resilience layer + notification system + MCP protocol adapter + Git integration."

**Evidence of scope creep:**
- Signal files are a parallel notification channel to WebSocket messages (why two?)
- Git hook generation is a client-side concern (belongs in interlock)
- MCP server is a Claude Code-specific protocol (belongs in interlock)

**Fix:** Cut Intermute's scope to ONLY the "must-have" enrichments:
1. Circuit breaker + retry (resilience)
2. Session identity (state persistence)
3. Stale lock cleanup (maintenance)
4. Conflict detection API (core feature)

Move to interlock:
- Signal files (client-side notification, not server-side)
- Git hook generation (tooling, not core API)
- MCP server (protocol adapter)

**Result:** Intermute stays focused on "state + API." Interlock owns "UX + protocol."

---

### 2.3 Naming Consistency

**Assessment: GOOD**

- "Intermute" = coordination (existing)
- "interlock" = locking/coordination companion (new, fits inter* pattern)
- Signal files follow `/tmp/<plugin>-<type>-<project>-<id>.json` pattern (matches `/tmp/clavain-dispatch-*.json`)
- Agent naming: `claude-${SESSION_ID:0:8}` (consistent with existing session ID truncation)

**No naming drift detected.**

---

## 3. Simplicity & YAGNI Analysis

### 3.1 Unnecessary Abstractions (Cut These)

**UA-1: Window Identity (tmux UUID mapping)**

Section "Adaptation Checklist" marks this as "Should-have" but it's redundant:

**Reason to cut:** `CLAUDE_SESSION_ID` already provides unique session identity. Mapping tmux window UUIDs adds zero value — the session ID already survives within the same tmux pane. If the pane closes, the session ends anyway.

**Recommendation:** Delete this from the design. Use `CLAUDE_SESSION_ID` only.

---

**UA-2: Tool Filtering Profiles**

Marked "Should-have" in adaptation checklist. The proposal is to reduce MCP tool count via role-based filtering (e.g., "show only 20 of 40 tools for code editing agents").

**Why premature:**
- interlock will expose ~9 MCP tools, not 40
- Claude Code's context window is 200k tokens (tool schemas are ~200 tokens each)
- 9 tools = ~1,800 tokens = 0.9% of context budget
- No evidence of context pressure from tool schemas

**Recommendation:** Delete. Only add if context pressure is measured and confirmed.

---

**UA-3: Auto-Reserve on First Edit**

Section 2d proposes a PostToolUse:Edit hook that auto-reserves files on first edit.

**Why unnecessary:**
- Open Question #1 in the design already flags this as uncertain ("should auto-reserve be on by default?")
- Creates silent lock acquisition (agent doesn't know it happened)
- Can lock out other agents unintentionally (noted as "Con" in the design)
- Use case is unclear: if agents aren't coordinating intentionally, auto-locking won't help

**Recommendation:** Delete. Require explicit `intermute_reserve_files` MCP tool calls. Auto-reserve can be added later if UX friction is measured.

---

**UA-4: Dual Persistence (DB + Git)**

Marked "Nice-to-have" in adaptation checklist. Proposal: store coordination state in BOTH SQLite AND a Git-archived Markdown audit trail.

**Why unnecessary:**
- Intermute already persists to SQLite
- Audit trail use case is unclear (who reads Markdown logs of reservations?)
- Adds write complexity (dual-write failure modes)
- Markdown logs are not queryable (defeats the purpose of SQLite)

**Recommendation:** Delete. SQLite is sufficient. If audit trail is needed later, add structured logging to a separate log file, NOT Git-tracked Markdown.

---

**UA-5: Commit Queue with Batching**

Marked "Nice-to-have." Proposal: batch multiple small commits into a single commit to reduce Git overhead.

**Why unnecessary:**
- No evidence of "frequent small commits" problem in Clavain workflows
- Clavain's "Landing the Plane" workflow already emphasizes commit discipline
- Batching adds state (queue) and timing complexity (when to flush?)
- Git is fast enough for current needs (no performance bottleneck identified)

**Recommendation:** Delete. Only add if commit latency becomes a measured bottleneck.

---

**UA-6: Contact Policies**

Marked "Nice-to-have." Proposal from mcp_agent_mail: agents specify contact policies (allow/deny lists for who can message them).

**Why unnecessary:**
- Clavain agents are trusted local processes (not adversarial)
- All agents run under the same user (`claude-user`)
- No use case for "deny messages from agent X"
- Adds complexity to messaging layer (policy evaluation on every send)

**Recommendation:** Delete. All agents can message all agents. Simplicity wins.

---

### 3.2 Required Complexity (Keep These)

**Justified abstractions:**

1. **Circuit breaker** — Prevents cascading SQLite failures, measured need from mcp_agent_mail
2. **Retry with jitter** — SQLite WAL lock contention is real, retry is a proven fix
3. **Session identity** — Solves "agent survives session restart" problem (Claude Code's compaction/clear behavior)
4. **Stale lock cleanup** — Prevents orphaned locks from crashed sessions (reliability requirement)
5. **Reservation conflict detection** — Core feature, not an abstraction
6. **Git hook generation** — Enforcement layer, but only if user opts in (not auto-enabled)

**All of these solve CURRENT problems, not speculative future needs.**

---

## 4. Dependency Direction & Ownership

### 4.1 Dependency Graph

**Current proposal:**
```
Clavain hooks → Intermute HTTP API
Clavain hooks → interlock (if installed)
interline → Intermute signal files (direct)
interlock MCP → Intermute HTTP API
```

**Revised (after fixing coupling risks):**
```
Clavain hooks → interlock (if installed) → Intermute HTTP API
interline → interlock signal adapter → Intermute raw signals
interlock MCP server → Intermute HTTP API
```

**Dependency direction:** Always client → interlock → Intermute. No direct client → Intermute calls.

**Ownership boundaries:**
- **Intermute:** State persistence, reservation logic, agent registry, messaging
- **interlock:** MCP protocol, signal normalization, Git hook generation, coordination UX
- **Clavain:** Shim delegation, session setup, environment propagation
- **interline:** Statusline rendering (reads normalized signals only)

**Analysis:** Clean separation. No circular dependencies. Ownership is explicit.

---

### 4.2 Integration Seams (Failure Isolation)

**Seam 1: Intermute not running**

**Behavior (current proposal):** `curl -sf` fails silently, hooks skip.

**Assessment:** CORRECT. Matches interphase's no-op stub pattern. No warnings needed (graceful degradation).

---

**Seam 2: interlock not installed**

**Behavior:** Clavain's shim delegation returns empty string, hooks skip.

**Assessment:** CORRECT. Follows lib-discovery.sh pattern.

---

**Seam 3: SQLite lock contention**

**Behavior:** Retry with jitter (up to 7 retries). If all retries fail, circuit breaker opens, rejects requests for 30s.

**Assessment:** CORRECT. Prevents cascading failures. Matches mcp_agent_mail's proven approach.

---

**Seam 4: Signal file write failure**

**Problem:** Not specified in the design. What if `/tmp` is full or read-only?

**Recommendation:** Signal file writes should be fire-and-forget. Log errors but don't fail the parent operation (reservation, message send). Signal files are a UX enhancement, not a correctness requirement.

---

## 5. Scope Creep & Necessary Changes

### 5.1 Scope Creep Detected

**Components NOT necessary for the stated goal** ("multiple agents editing same repo without worktrees"):

1. **Auto-reserve on first edit** — Solves a problem that doesn't exist yet (silent locking)
2. **Tool filtering profiles** — Premature optimization (no context pressure measured)
3. **Dual persistence (DB + Git)** — Audit trail without a reader
4. **Commit queue with batching** — Performance optimization without a measured bottleneck
5. **Contact policies** — Security feature for adversarial agents (not the use case)
6. **Window identity (tmux UUID)** — Redundant with CLAUDE_SESSION_ID

**Total scope reduction:** 6 features cut = ~40% reduction in implementation surface.

---

### 5.2 Minimum Viable Design

**What's needed to solve "multi-agent same-repo coordination without worktrees":**

**Layer 1 (Intermute enrichments):**
1. Circuit breaker + retry (resilience for SQLite contention)
2. Session identity (survive Claude Code session restarts)
3. Stale lock cleanup (prevent orphaned locks)
4. Conflict detection API (`GET /api/reservations/check`)

**Layer 2 (interlock companion):**
1. MCP server with 9 tools (reserve, release, check, list, send, fetch, status)
2. SessionStart hook: register agent with Intermute
3. Stop hook: release all reservations
4. Git hook generator script (opt-in, not auto-enabled)
5. Signal file adapter for interline (normalized schema)

**Layer 2b (Clavain):**
1. Shim delegation in SessionStart hook (`interlock-register`)
2. Environment setup (INTERMUTE_AGENT_ID from interlock's output file)

**Layer 2c (interline):**
1. Read interlock's normalized signal files (not Intermute's raw signals)
2. Add coordination layer to statusline priority (between "bead context" and "workflow phase")

**Total: 4 Intermute changes + 9 interlock components + 2 Clavain changes + 1 interline change = 16 components.**

**Original design: ~25 components (including 6 cut features + dual protocol surface).**

**Scope reduction: 36% fewer components.**

---

## 6. Open Questions — Resolution Recommendations

**Q1: Should auto-reserve be on by default?**

**Answer: NO.** Delete auto-reserve entirely (see UA-3). Require explicit coordination.

---

**Q2: Reservation granularity — file-level or directory-level?**

**Answer: BOTH.** Intermute's glob pattern support already handles this. Default to file-level (safest). Allow directory globs when needed (`src/**/*.go`). No new abstraction required.

---

**Q3: Message protocol — auto-broadcast on reservation?**

**Answer: NO.** Signal files are sufficient for passive notification. Messages should be explicit agent-to-agent communication only. Auto-broadcast creates inbox clutter (noted in the design).

---

**Q4: Intermute as systemd service or start-on-demand?**

**Answer: SYSTEMD SERVICE.** Autarch already uses Intermute as a persistent service. Coordination state (agent registry, reservations) needs to survive individual session restarts. Start-on-demand creates a bootstrapping problem (who starts the server?).

**Recommendation:** Add `intermute.service` systemd unit to interlock's install script.

---

**Q5: Graceful degradation — silent skip or warn?**

**Answer: SILENT SKIP.** Matches interphase pattern. Warnings create noise for users who don't need coordination. If Intermute is needed, its absence will be obvious (conflicts happen, no statusline updates).

---

## 7. Migration Path (Smallest Viable Change)

**Sequence:**

### Phase 1: Intermute Core (No Plugin Changes Yet)
1. Add circuit breaker + retry to `internal/store/sqlite.go`
2. Add `session_id` field to agent registration
3. Add stale lock cleanup goroutine
4. Add `GET /api/reservations/check` endpoint
5. Add 111 → 120+ tests

**Validation:** Deploy to ethics-gradient, verify Autarch still works, measure SQLite lock contention reduction.

---

### Phase 2: interlock Companion
1. Create `/root/projects/interlock/` repo
2. Add MCP server (stdio, wraps HTTP calls)
3. Add 9 MCP tools
4. Add SessionStart/Stop hooks
5. Add signal file adapter script
6. Add Git hook generator script
7. Add systemd service unit
8. Add 17 structural tests (match interpath's test coverage)

**Validation:** Install interlock, verify MCP tools work, verify hooks fire correctly.

---

### Phase 3: Clavain + interline Integration
1. Add shim delegation to Clavain's SessionStart hook
2. Update interline to read interlock's normalized signals
3. Update Clavain's doctor.md to check for interlock (new check 3f)
4. Update Clavain's setup.md to install interlock from marketplace

**Validation:** Full integration test with 2 concurrent Claude Code sessions editing same repo.

---

**Total implementation estimate:** 3-4 days (1 day per phase).

---

## 8. Summary of Findings

### Must-Fix Boundary Violations

1. **CR-1:** MCP server should be in interlock, NOT Intermute (dual protocol surface)
2. **CR-3:** Clavain SessionStart hook should delegate to interlock, NOT call Intermute directly

### Must-Fix Coupling Risks

1. **CR-2:** Interline should read normalized signals from interlock, NOT raw Intermute signals
2. **CR-4:** PreToolUse:Edit hook should be async advisory, NOT blocking synchronous check

### Anti-Patterns

1. **AP-1:** Dual protocol surface (HTTP + MCP in same binary)
2. **AP-2:** God module risk (Intermute's scope creep to 8 features in one pass)

### Unnecessary Abstractions (Cut These)

1. **UA-1:** Window identity (tmux UUID) — redundant with CLAUDE_SESSION_ID
2. **UA-2:** Tool filtering profiles — premature optimization
3. **UA-3:** Auto-reserve on first edit — solves non-problem
4. **UA-4:** Dual persistence (DB + Git) — audit trail without reader
5. **UA-5:** Commit queue with batching — performance fix without measured bottleneck
6. **UA-6:** Contact policies — security for adversarial agents (not the use case)

### Open Questions — Resolved

1. Auto-reserve default: NO (delete feature)
2. Reservation granularity: BOTH (glob pattern support)
3. Auto-broadcast on reservation: NO (signal files sufficient)
4. Systemd service or on-demand: SYSTEMD SERVICE
5. Graceful degradation: SILENT SKIP

---

## 9. Final Recommendation

**GO/NO-GO:** GO with significant revisions.

**Required changes before implementation:**
1. Move MCP server from Intermute to interlock
2. Cut 6 unnecessary abstractions (UA-1 through UA-6)
3. Fix 4 coupling risks (CR-1 through CR-4)
4. Reduce Intermute's scope to 4 core enrichments (cut scope creep)
5. Follow 3-phase migration path (Intermute → interlock → Clavain+interline)

**Estimated scope reduction:** 36% fewer components, 40% fewer features.

**Revised component counts:**
- Intermute: +4 features (circuit breaker, retry, session identity, stale cleanup)
- interlock: 9 MCP tools + 2 hooks + 3 scripts + 1 systemd unit = 15 components
- Clavain: +2 hook modifications
- interline: +1 signal reader integration

**Architecture verdict:** The two-layer separation is sound. The companion plugin choice is correct. The coupling risks are fixable. The unnecessary complexity is cuttable. The core idea is solid — multi-agent coordination via explicit reservations + messaging. Proceed with revisions.
