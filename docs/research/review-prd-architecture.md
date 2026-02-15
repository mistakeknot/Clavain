# Architectural Review: Interlock PRD (2026-02-14)

**Reviewer:** Flux-Drive Architecture Agent
**Date:** 2026-02-14
**Scope:** PRD structure, feature boundaries, dependency coherence, phased migration path
**Depth:** PRD-level (not re-reviewing flux-drive design decisions)

---

## Executive Summary

**Verdict: ARCHITECTURALLY SOUND with 3 boundary clarifications and 1 migration risk.**

The Interlock PRD establishes clean feature boundaries and follows established Clavain companion plugin patterns. All 13 features layer correctly: intermute resilience (F1-F5) → MCP exposure (F6) → Clavain integration (F7-F12) → statusline integration (F13). However, three design boundaries need explicit clarification in implementation:

1. **F6/F7 boundary:** MCP server ownership vs. plugin manager lifecycle
2. **F9/F13 boundary:** Signal file format contract between Interlock and interline
3. **Phase migration (F1→F2→F3→F4→F5→F6):** intermute API stability during rollout

---

## 1. Feature Boundary Analysis

### 1.1 Layered Feature Structure

The 13 features organize into 4 coherent tiers:

```
TIER 1: intermute Resilience (F1-F5) — Go service enhancements
  ├─ F1: CircuitBreaker + RetryOnDBLock (SQLite reliability)
  ├─ F2: Session identity reuse (stale session collision detection)
  ├─ F3: Background cleanup (crash recovery)
  ├─ F4: Atomic check-and-reserve (conflict prevention)
  └─ F5: Unix socket listener (local deployment optimization)

TIER 2: MCP Exposure (F6) — Bridge layer
  └─ F6: Interlock MCP server (Claude Code client access)

TIER 3: Agent Lifecycle (F7-F12) — Clavain integration
  ├─ F7: Hooks (SessionStart/PreToolUse/Stop)
  ├─ F8: Commands (/interlock:join, :leave, :status, :setup)
  ├─ F9: Signal file adapter (sideband to interline)
  ├─ F10: Git pre-commit hook (enforcement backstop)
  ├─ F11: Skills (coordination-protocol, conflict-recovery)
  └─ F12: Clavain shim delegation (plugin discovery)

TIER 4: Statusline Rendering (F13) — UI integration
  └─ F13: interline signal consumption (persistent coordination status)
```

**Assessment:** Layering is correct. Each tier depends only on lower tiers; no upward dependencies. F6 cleanly separates concerns: MCP protocol handling vs. intermute HTTP/socket integration.

### 1.2 Feature Cohesion

Each feature has a single, clear responsibility:

| Feature | Responsibility | Scope | Risk |
|---------|----------------|-------|------|
| F1 | SQLite fault tolerance | intermute only | Low — adds circuit breaker middleware, non-breaking |
| F2 | Session reuse + collision detection | intermute API | Low — adds optional field, backward-compatible |
| F3 | Background cleanup | intermute only | Low — cleanup always idempotent |
| F4 | Atomic reserve-or-conflict | intermute API | **Medium** — NEW endpoint, must coexist with F3 cleanup |
| F5 | Unix socket transport | intermute only | Low — parallel to TCP, no interference |
| F6 | MCP wrapper | Bridge layer | **Medium** — stdio lifecycle must not conflict with intermute restarts |
| F7 | Lifecycle hooks | Clavain hooks | Low — graceful degradation if interlock unavailable |
| F8 | User commands | Claude Code CLI | Low — idempotent operations, safe re-invocation |
| F9 | Signal file generation | Interlock service | **Medium** — append-only semantics, rotations, permission model |
| F10 | Pre-commit enforcement | Git hook | Low — blocking, documented escape hatch |
| F11 | Educational skills | Markdown docs | Low — documentation, no runtime coupling |
| F12 | Plugin discovery | Clavain hooks | Low — follows interflux/interphase/interpath pattern |
| F13 | Statusline integration | interline plugin | **Medium** — depends on F9 signal format contract |

**Critical coupling points identified:**
- **F4 + F3 + heartbeat logic:** F3 sweeps inactive reservations while F4 checks them atomically. Requires explicit state transition semantics.
- **F6 + intermute service health:** MCP server must not crash the Claude Code session if intermute is restarting (F1/F3/F5 trigger this).
- **F9 + F13:** Signal file format must be versioned; interline must gracefully handle format evolution.

### 1.3 Dependency Map

```
User (Claude Code)
  ↓
F8: Commands (/interlock:join/leave/status/setup)
F7: Hooks (SessionStart/PreToolUse/Stop)
F11: Skills (coordinate/conflict-recovery)
  ↓
F12: Clavain shim discovers Interlock plugin
F6: MCP server (9 tools) + Unix socket connection
  ↓
F9: Signal file adapter (writes to /var/run/intermute/signals/)
  ↓
F13: interline reads signals, updates statusline
  ↓ (separate flow)
  ↓
intermute (Go service)
F5: Unix domain socket listener
  ↓
F4: Atomic check-and-reserve endpoint
F2: Session reuse + collision rejection
F3: Background cleanup goroutine
  ↓
F1: Circuit breaker + retry middleware
  ↓
SQLite DB
```

**Dependency Assessment:**
- **Clean dependency direction:** User → Clavain → Interlock → intermute → SQLite. No upward/circular dependencies.
- **Optional companion pattern:** Interlock is a companion plugin (like interflux, interphase, interpath, interwatch). Clavain gracefully degrades if absent (F12 shim + all hooks have `if intermute unavailable { skip }`).
- **External service dependency:** intermute is a separate systemd service. F6 includes fallback logic (Unix socket → TCP).

**Concerns:**
- **F4 + F3 race window:** Between F3 cleanup and F4 atomic reserve, a stale reservation can be reclaimed. Acceptance criteria should specify TTL semantics for this window. **Recommend:** Clarify that F3 only sweeps reservations >5min old with heartbeat >5min stale — not both conditions independently.
- **F9 signal permission model:** If Interlock runs as different user than interline, `/var/run/intermute/signals/` 0700 permissions block reader. **Recommend:** Clarify whether Interlock and interline share a group or if signals are world-readable.

---

## 2. Pattern Consistency Review

### 2.1 Companion Plugin Pattern (Clavain's Established Practice)

Clavain integrates 5 companions via consistent 3-part pattern:

**1. Discovery** (`hooks/lib.sh`):
```bash
_discover_<plugin>_plugin() {
    if [[ -n "${<PLUGIN>_ROOT:-}" ]]; then echo "$<PLUGIN>_ROOT"; return 0; fi
    local f=$(find ~/.claude/plugins/cache -maxdepth 5 -path "*/<plugin>/*/marker-file" | sort -V | tail -1)
    if [[ -n "$f" ]]; then echo "$(dirname "$(dirname "$f")")"; return 0; fi
    echo ""
}
```

**2. Session detection** (`hooks/session-start.sh`):
Discovers all companions and injects them into context:
```json
"companions": {
    "interflux": "/root/.claude/plugins/cache/interflux-0.5.0",
    "interphase": "/root/.claude/plugins/cache/interphase-0.4.53",
    ...
}
```

**3. Delegation** (hooks and commands):
```bash
INTERLOCK_ROOT=$(_discover_interlock_plugin)
if [[ -n "$INTERLOCK_ROOT" ]]; then
    source "$INTERLOCK_ROOT/hooks/..."  # or scripts/...
else
    # graceful degradation: skip feature, don't fail
fi
```

**Interlock PRD alignment:**
- ✅ F12 discovery function follows pattern exactly
- ✅ F7 hooks delegate to interlock scripts (not direct curl to intermute)
- ✅ F8 commands use `/interlock:` namespace (companions use `/inter*:`)
- ✅ Graceful degradation: "All hooks skip silently if intermute unavailable"

**Assessment:** Perfect pattern consistency. No architectural friction.

### 2.2 Signal-Based Integration (interline Model)

interline is a companion statusline renderer that reads signal files:
- interpath writes to `/tmp/clavain-dispatch-*.json` (product artifacts)
- interphase writes to `/tmp/clavain-bead-*.json` (phase tracking)
- interline reads these and renders priority-ordered statusline

**Interlock's F9 follows this pattern:**
- F9 generates normalized signal files: `/var/run/intermute/signals/{project-slug}-{agent-id}.jsonl`
- F13 reads them and inserts into priority: `dispatch > **coordination** > bead > workflow > clodex`

**Deviation detected:** interpath/interphase use `/tmp/` (ephemeral), Interlock uses `/var/run/` (persistent).
- **Justification in PRD:** "Signal file rotation when >1MB" implies multi-session durability. `/var/run/` is correct.
- **BUT:** File lifetime must be managed. PRD should specify cleanup policy (e.g., "rotate weekly" or "delete on interlock stop").

**Assessment:** Pattern is sound, but lifecycle management needs explicit spec.

### 2.3 Atomic Operations in SQLite (intermute's Style)

intermute already uses SQLite transactions for atomic operations:
- Agent registration (F2 adds `session_id` field)
- Message delivery
- Existing reservations API (F4 references "single-statement atomic DELETE")

**F4 acceptance criteria:**
- "Single SQLite transaction: check conflict + insert reservation"
- "Concurrent atomic reserves (only one succeeds), idempotent re-reserve by same agent"

**Assessment:** Consistent with intermute's existing patterns. Tests cover concurrency correctly.

---

## 3. Phased Migration Path Analysis

### 3.1 Phase Sequencing

The PRD lists features F1-F13 in a logical build order:

```
Phase 1: SQLite resilience foundation (F1-F5)
  ├─ F1: Circuit breaker + retry (no API changes)
  ├─ F2: Session identity reuse (backward-compatible API addition)
  ├─ F3: Background cleanup (backward-compatible, startup hook)
  ├─ F4: Atomic reserve (new endpoint, non-breaking)
  └─ F5: Unix socket (parallel transport, non-breaking)

Phase 2: MCP exposure (F6)
  └─ F6: Interlock MCP server (new repo/plugin)

Phase 3: Clavain integration (F7-F12)
  ├─ F7: Hooks (delegates to F6, gracefully degrades)
  ├─ F8: Commands (delegate to F6)
  ├─ F9: Signal adapter (new Interlock feature)
  ├─ F10: Pre-commit hook (local git hook, no service dependency)
  ├─ F11: Skills (documentation)
  └─ F12: Clavain shim (plugin discovery)

Phase 4: UI integration (F13)
  └─ F13: interline update (depends on F9 signal contract)
```

**Rollout risks identified:**

| Phase | Risk | Mitigation |
|-------|------|-----------|
| 1 | F1 circuit breaker state must persist across server restarts | Store breaker state in DB, or reset on startup |
| 1 | F2 session reuse + F3 cleanup can race (stale session reclaimed while new session re-registering) | Define clear heartbeat TTL boundaries: cleanup >5min AND stale >5min |
| 1 | F4 atomic reserve is NEW endpoint; clients must upgrade to use it | F4 is optional; old clients use F2 + manual conflict checking |
| 1 | F5 Unix socket adds /var/run/ permission model; must not break TCP-only setups | Both listeners run simultaneously; TCP fallback in F6 |
| 2 | F6 MCP server crashes ≠ intermute down; Claude Code must handle MCP unavailability | F6 acceptance: "error handling for intermute unavailable" |
| 3 | F7 hooks fire before F9 signal adapter exists | F9 is part of Interlock plugin, available when F7 is discovered |
| 3 | F10 pre-commit hook blocks pushes if intermute is down | F10 acceptance: "passes if no intermute agent is registered" + `--no-verify` escape hatch |
| 4 | F13 reads F9 signal format; format evolution breaks interline | Define signal schema version, interline gracefully handles unknown versions |

**Critical dependency:** F9 signal format MUST be defined before F13 is implemented.

### 3.2 API Stability During Phased Rollout

**intermute APIs used by Interlock (F6):**
- `POST /api/reservations?if_not_conflict=true` — NEW in F4
- `GET /api/reservations/check` — existing, preserved
- `POST /api/agents` — existing, modified in F2 (session_id field added)
- Agent heartbeat, message send/fetch — existing, unchanged

**Migration path:**
1. F1-F5 ship to intermute; old clients still work (backward-compatible)
2. F6 Interlock MCP server launches; uses old APIs (no new intermute calls)
3. F4 atomic endpoint available; F6 can upgrade to use it (opt-in)
4. Old intermute versions (pre-F1-F5) will fail on F6 registration attempt; F6 graceful degradation catches it

**Recommendation:** Add to F6 acceptance criteria: "MCP tools fail gracefully if intermute version <X.Y.Z (missing atomic reserve)" — otherwise F6 will incorrectly report success when using non-atomic reserve.

### 3.3 Backward Compatibility

**F1-F5 (intermute):** All backward-compatible
- F1: Middleware layer, no API changes
- F2: Optional `session_id` field, defaults to null (old behavior)
- F3: Cleanup only affects stale records, doesn't touch active ones
- F4: New endpoint, old clients ignore it
- F5: Parallel transport, TCP still works

**F6 (MCP server):** New plugin, ships independently
- No changes to intermute; MCP server is thin wrapper
- If interlock plugin absent, Claude Code sessions work normally

**F7-F12 (Clavain integration):** All gracefully degrade
- F7 hooks skip if intermute unavailable
- F8 commands error with helpful message if interlock plugin absent
- F12 shim discovery is optional

**F13 (interline):** Depends on F9 signal contract
- If signal file missing/corrupt, interline gracefully shows no coordination status
- Version mismatch: interline should log warning, not crash

**Assessment:** Phased rollout is sound. All breaking points have documented escape hatches.

---

## 4. Coupling Analysis: Cross-Feature Risks

### 4.1 Session Identity Collision Window (F2 + F3)

**Current specification:**
- F2: "If session_id matches existing agent with heartbeat >5min old, reuse identity"
- F3: "Sweep goroutine runs every 60s using single-statement atomic DELETE (expires + inactive heartbeat)"

**Risk:** Race between F2 reuse check and F3 cleanup sweep

```
Timeline:
T0: Agent A registers with session_id=X, heartbeat=now
T1: Agent A crashes, heartbeat not updated for 6 minutes
T2: Agent A restarts, re-registers with session_id=X
  → F2 checks: heartbeat >5min? YES → reuse identity
T3: F3 cleanup sweep runs (every 60s)
  → F3 checks: heartbeat >5min AND reservations expired? YES → DELETE
  → But Agent A (T2) is using this identity now!

Result: Agent A loses its identity mid-session.
```

**Mitigation in PRD:** None specified; relies on "5 min old" threshold implying TTL.

**Recommendation:**
- Clarify F2 logic: "If heartbeat is STALE (>5min old) AND reservations are EXPIRED (>5min), reuse. Otherwise, reject as collision."
- Clarify F3 logic: "Delete only reservations where heartbeat is STALE AND agent is INACTIVE for >5min." Add acceptance criterion: "F3 never deletes an active agent's reservation."
- Add concurrency test: "F2 reuse + F3 sweep can run concurrently; no data corruption."

### 4.2 Git Pre-Commit Hook Blocking Behavior (F10)

**Current specification:**
- F10: "Hook passes if no intermute agent is registered (graceful degradation)"
- F10: "Hook skippable with `--no-verify` (escape hatch documented)"

**Risk:** Developers unaware of `/interlock:join` step run normal `git push`, hook blocks them.

**Scenario:**
```bash
# Developer joins interlock (F8 /interlock:join)
$ git add . && git commit -m "..."
# Pre-commit hook (F10) checks files against intermute
# Another agent has file reserved
# Hook aborts: "cannot commit; file reserved by agent-X"
# Developer runs git push --no-verify (mistake)
# Silent conflict, other agent's work lost
```

**Mitigation in PRD:** F10 acceptance criterion says "Hook aborts commit with clear error message including: file, holder, reason, expiry, recovery steps." This is good. But "recovery steps" should explicitly mention:
1. Request release via `/interlock:request-release` (not in PRD — is this a F8 command?)
2. Stash changes, work elsewhere, rebase after release
3. Last resort: `--no-verify` with clear warning

**Recommendation:**
- Add F8 command: `/interlock:request-release <agent-id>` or rename existing `request_release` MCP tool to be user-facing
- Update F10 acceptance criteria to reference this command

### 4.3 Signal File Format Contract (F9 + F13)

**F9 specification:**
```json
{"layer":"coordination","icon":"lock","text":"...","priority":3,"ts":"..."}
```

**F13 specification:**
- "Reads `/var/run/intermute/signals/{project-slug}-{agent-id}.jsonl` (latest line)"
- "Coordination layer inserted into priority: dispatch > **coordination** > bead > workflow > clodex"

**Risk:** If F9 emits format that F13 doesn't expect, interline crashes or silently ignores coordination status.

**Current mitigation:** None specified. PRD lists both as acceptance criteria but doesn't define a versioned schema.

**Recommendation:**
- Add to F9 acceptance criteria: "Signal schema includes `version: 1` field for forward compatibility"
- Add to F13 acceptance criteria: "interline gracefully ignores signals with unknown version or missing required fields; logs warning, doesn't crash"
- Document signal schema in a shared file (e.g., `docs/signals-schema.md`) both plugins reference

### 4.4 intermute Service Lifecycle (F1 + F3 + F5 + F6)

**Risk:** F1 circuit breaker opens, F3 sweeps stale data, F5 socket listener cycles, while F6 MCP clients are connected.

**Scenario:**
```
T0: intermute serving normally via TCP + Unix socket
T1: SQLite locks up (F1 circuit breaker OPEN)
T2: F3 background sweep is blocked (circuit open)
T3: MCP client (F6) tries to reserve file
    → F6 wraps HTTP call to intermute
    → intermute returns 503 (circuit open)
    → F6 should handle 503 gracefully
T4: Circuit breaker resets (after 30s F1 timeout)
T5: F3 sweep runs and cleans up stale data
T6: MCP client retries reserve
    → Success
```

**Current mitigation:** F6 acceptance criteria says "error handling for intermute unavailable" — vague.

**Recommendation:**
- Add to F6 acceptance criteria: "MCP tools handle HTTP 5xx errors by returning structured error (not crashing); client sees `{"error":"intermute unavailable","code":503,"retry_after":30}`"
- Add to F1 acceptance criteria: "Circuit breaker state is visible via `/health` endpoint so F6 can check readiness before retrying"

---

## 5. Non-Goals Assessment

**Listed non-goals and their justification:**

| Non-Goal | Justification | Assessment |
|----------|---------------|------------|
| Auto-reserve on edit | "Creates lock contention, TOCTOU races, false safety" | ✅ Correct — reservations are explicit workflow, not implicit |
| Tool filtering profiles | "9 MCP tools at ~1,800 tokens is 0.9% of context budget" | ✅ Reasonable — context budget not a constraint |
| Dual persistence (DB + Git) | "Audit trail without a reader. SQLite is sufficient." | ✅ Correct — intermute already audits via DB |
| Commit queue with batching | "No measured bottleneck for commit frequency" | ✅ Reasonable — premature optimization |
| Contact policies | "Over-engineering for trusted local agents" | ✅ Correct — same machine/network, policy unnecessary |
| Cross-project product bus | "Premature. Revisit when cross-repo coordination needed" | ✅ Correct — single-repo MVP is right scope |
| MCP server inside intermute | "Avoids dual-protocol anti-pattern. Interlock owns MCP layer." | ✅ **Correct — separates concerns cleanly** |
| Blocking PreToolUse:Edit | "Advisory only. Git pre-commit hooks provide enforcement." | ✅ Correct — permissive advisory + mandatory enforcement is right model |

**Assessment:** All non-goals are well-justified. No scope creep detected.

---

## 6. Architecture Soundness Verdict

### 6.1 Strengths

1. **Tier-based layering is clean:**
   - intermute resilience (F1-F5) stands alone; can ship independently
   - MCP wrapper (F6) is thin and stateless
   - Clavain integration (F7-F12) follows established companion plugin pattern
   - Statusline rendering (F13) is optional enhancement

2. **Dependency direction is correct:**
   - No upward dependencies; users depend on Clavain depend on Interlock depend on intermute depend on SQLite
   - Graceful degradation at every layer: Interlock absent → no coordination, but Clavain works fine

3. **Backward compatibility throughout:**
   - F1-F5 don't break existing intermute clients
   - F6 is new plugin; existing sessions unaffected
   - F7-F12 degrade gracefully if intermute unavailable

4. **Pattern consistency:**
   - Follows Clavain's companion plugin discovery, shim delegation, and graceful degradation
   - Matches interline's signal-file-based integration
   - Mirrors intermute's atomic transaction semantics

5. **Phased rollout is feasible:**
   - F1-F5 ship independently to intermute
   - F6 wraps existing intermute APIs (no new intermute version required)
   - F7-F12 ship as separate Interlock plugin
   - F13 is optional; interline updates independently

### 6.2 Medium-Severity Concerns

1. **F2 + F3 race condition:** Heartbeat TTL semantics for stale session cleanup need explicit definition. Add test for concurrent reuse + cleanup.

2. **F9 + F13 signal contract:** Schema versioning not specified. Add `version` field to schema; interline must handle unknown versions gracefully.

3. **F10 + user awareness:** Pre-commit hook can block pushes; recovery path (request release, work elsewhere) not fully integrated into F8 commands. Add `/interlock:request-release` command.

4. **F6 intermute unavailability handling:** MCP tools need explicit error handling spec (HTTP 5xx → structured error, don't crash).

### 6.3 Low-Severity Recommendations

1. Add F1 circuit breaker state to `/health` endpoint for visibility.
2. Document F9 signal file lifecycle/cleanup policy (rotation weekly? permanent? deleted on Interlock stop?).
3. Add F5 Unix socket file cleanup spec to graceful shutdown (F5 acceptance criteria mentions removal but not atomic guarantees).
4. Clarify F4 vs. F2 usage: when should client use atomic reserve vs. manual check? Recommend in acceptance criteria: "F4 is primary path for MCP clients; F2 is fallback for backward-compat."

### 6.4 Integration Readiness

**Prerequisites before implementation:**
- [ ] intermute 0.X.Y+ with F1-F5 complete
- [ ] interline companion plugin deployed (for F13 readiness)
- [ ] F9 signal schema documented + versioned in shared spec
- [ ] F10 + F8 recovery workflow integrated (request-release command)

**Parallel work streams:**
- intermute team: F1-F5 (SQLite resilience layer)
- Interlock team: F6 + F7-F12 (MCP server + Clavain integration)
- interline team: F13 (signal file consumption)

---

## 7. Final Recommendations

### 7.1 PRD Refinements (Before Implementation)

1. **F2 + F3:** Add acceptance criterion: "F3 sweep never deletes an active agent's reservation; concurrent reuse + cleanup is safe."

2. **F4 + F2:** Clarify: "F4 atomic reserve is recommended for new clients; F2 session reuse is for legacy clients without atomic reserve support."

3. **F6:** Add acceptance criterion: "MCP tools gracefully handle intermute unavailability; HTTP 5xx → structured `{error, code, retry_after}`, not crash."

4. **F9:** Add acceptance criterion: "Signal schema includes `version: 1` field; rotation policy documented (e.g., weekly rotation, max 1MB)."

5. **F10:** Add acceptance criterion: "Error message includes actionable recovery steps: request release via `/interlock:request-release`, stash + work elsewhere, or `--no-verify` (documented risk)."

6. **F13:** Add acceptance criterion: "Gracefully ignores signal files with unknown schema version; logs warning, doesn't crash; falls back to 'no coordination status'."

7. **Add F14 (optional):** Signal schema documentation (`docs/signals-schema.md`) as shared reference for Interlock + interline.

### 7.2 Implementation Sequence

```
Week 1-2:  intermute F1-F5 (SQLite resilience + Unix socket)
           [Dependencies resolved; new intermute tag ready]

Week 3:    Interlock F6 (MCP wrapper)
           [MCP client can connect to intermute]

Week 4-5:  Interlock F7-F12 (Clavain integration + hooks + commands)
           [Interlock plugin ships; Clavain discovers it]

Week 6:    interline F13 (signal consumption)
           [Final UI integration; all 13 features complete]

Week 7:    Testing + documentation
           [Smoke tests across all layers]
```

### 7.3 Risk Mitigation Plan

| Risk | Mitigation |
|------|-----------|
| F2 + F3 race condition | Add concurrency tests; define heartbeat TTL explicitly; add integration test: 1000 concurrent reuse + cleanup attempts |
| F4 intermute version skew | Add `/health` endpoint check; document minimum intermute version in F6 README |
| F9 signal format evolution | Add schema versioning; document backward compatibility policy |
| F10 developer awareness | Add prominent warning in `/interlock:join` output; link to recovery workflow |
| F6 MCP server crash | Add supervisor (systemd restart-on-failure or Claude Code plugin health check) |
| F9 signal file permissions | Document group/ACL model; verify interline can read signals |

---

## Conclusion

**Interlock PRD is architecturally sound.** All features layer correctly, dependencies flow downward, and backward compatibility is maintained. The phased migration path is feasible, and the companion plugin pattern is consistent with Clavain's established architecture.

**Three boundaries require explicit clarification in implementation specs** (F2+F3 TTL semantics, F9+F13 signal schema versioning, F10 recovery workflow), but these are refinements, not structural flaws.

**Recommend:**
1. Incorporate 7.1 PRD refinements into feature acceptance criteria
2. Follow 7.2 implementation sequence (intermute first, then Interlock, then interline)
3. Execute 7.3 risk mitigations concurrently with development

**Architecture rating: 8.5/10**
- Loses 1 point for F2+F3 TTL semantics not fully specified
- Loses 0.5 points for F10 recovery workflow not integrated into commands

Feature boundaries are clean, coupling is minimal, and the system will degrade gracefully if any component is unavailable.
