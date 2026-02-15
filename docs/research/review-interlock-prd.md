# PRD Review: Interlock — Multi-Agent Same-Repo Coordination

**Reviewer:** Flux-Drive User & Product Lens
**Date:** 2026-02-14
**Document:** `/root/projects/Clavain/docs/prds/2026-02-14-interlock-multi-agent-coordination.md`
**Status:** READY FOR DEVELOPMENT with targeted clarifications

---

## Executive Summary

This PRD is **well-scoped, technically sound, and ready for implementation**. The flux-drive review process has effectively distilled a complex multi-agent coordination problem into 13 concrete features with mostly testable acceptance criteria.

**Top findings:**
1. **Scope is appropriately bounded** — Non-goals are explicit and justified; feature coupling is minimal.
2. **Acceptance criteria are ~85% concrete** — Most are testable; 3 features need minor clarification to close ambiguity.
3. **User experience is thoughtful** — Explicit opt-in, graceful degradation, and clear recovery paths reduce cognitive burden.
4. **Two risks flagged** — Signal file rotation strategy needs detail; git hook error messages require UX polish before rollout.

---

## Strengths

### 1. Scope Clarity and Coupling Analysis

**Finding:** Features are independently deliverable with minimal hidden dependencies.

**Evidence:**
- F1-F5 are purely intermute enrichments; can ship as a standalone release
- F6 (MCP server) depends only on F1-F5 being stable, not feature-complete
- F7-F9 (hooks, commands, signals) are orthogonal; any can be disabled without breaking others
- F10 (git hook) is optional enforcement; system works without it

**Assessment:** Excellent. The two-layer architecture (intermute + Interlock) cleanly separates concerns. This allows phased rollout: core resilience first (F1-F5), then Claude Code integration (F6-F9), then enforcement (F10).

**Recommendation:** Document this phasing explicitly in the PRD's "Implementation Path" section. Mention that F1-F5 can be released as intermute v0.5.0, and F6-F13 can follow as Interlock v0.1.0 without blocking each other.

---

### 2. Flux-Drive Review Integration

**Finding:** All 5 open questions from the brainstorm are resolved with clear, convergent reasoning.

**Evidence:**
- Auto-reserve rejection: All 4 reviewers agreed (safety + correctness concern)
- Reservation granularity: Dual support with sensible default
- Message protocol: Signals-only decision reduces queue complexity
- Service lifecycle: Hybrid (on-demand + idle timeout) balances resource use and responsiveness
- Graceful degradation: Matches established interphase pattern

**Assessment:** Strong. The PRD doesn't re-argue settled questions; it documents decisions and rationale. This reduces ambiguity for implementers.

---

### 3. Non-Goals Are Well-Justified

**Finding:** 8 non-goals are explicitly listed with reasoning.

**Spot-check:**
- "Auto-reserve on edit" — Removed due to TOCTOU/contention concerns ✓
- "Tool filtering profiles" — 9 tools ~0.9% context budget; not a constraint ✓
- "Dual persistence" — SQLite sufficient; no audit reader ✓
- "Contact policies" — Trusted local agents, not adversarial model ✓

**Assessment:** These are defensible, but their absence should be validated against real usage. See Risk #2 below.

---

### 4. Defense-in-Depth Architecture

**Finding:** PRD specifies multiple enforcement layers, not single points of failure.

**Layers:**
1. PreToolUse:Edit hooks (advisory warnings)
2. Git pre-commit hooks (mandatory enforcement)
3. Atomic DB operations (prevent TOCTOU races at API layer)
4. Startup sweep (crash recovery)

**Assessment:** Solid. This multi-layer approach reduces the damage from any single layer breaking or being bypassed. Git pre-commit hooks as the "backstop" is appropriate for a local coordination system.

---

## Acceptance Criteria Analysis

### Concrete and Testable (11 of 13)

**Examples:**
- F1: "CircuitBreaker struct with sync.Mutex, states CLOSED/OPEN/HALF_OPEN, threshold 5, reset 30s" — ✓ Verifiable
- F2: "If session_id matches existing agent with heartbeat >5min old, reuse identity" — ✓ Testable with mock time
- F4: "Single SQLite transaction: check conflict + insert reservation" — ✓ Verifiable via integration test
- F7: "SessionStart hook: exports INTERMUTE_AGENT_ID and INTERMUTE_AGENT_NAME to CLAUDE_ENV_FILE" — ✓ Observable

**Assessment:** High bar met. Most acceptance criteria can be validated by automated tests (unit/integration/smoke).

---

### Ambiguous Criteria (2 of 13)

#### Issue A: F3 — Stale Reservation Cleanup

**Criterion:** "Signal emission for released reservations (fire-and-forget)"

**Ambiguity:**
- What is the "signal"? (Webhook? Log line? Signal file?)
- To whom? (Interlock listeners? All agents?)
- Retry behavior? (Fire-and-forget means no retry; what if Interlock is offline?)

**Impact:** Moderate — Affects F9 (signal file generation), which depends on these signals being emitted.

**Recommendation:** Clarify in acceptance criteria:
```
- [ ] Signal emission: when stale reservation is deleted, emit event to all listening agents
      (via intermute's WebSocket subscribers OR via signal file writes by Interlock)
- [ ] Fire-and-forget: no retry if signal delivery fails; intermute logs failure for debugging
- [ ] Interlock watches intermute logs/API for deleted-reservation events and writes signal files
```

#### Issue B: F9 — Signal File Rotation

**Criterion:** "Signal file rotation when >1MB"

**Ambiguity:**
- Rotation strategy: truncate or archive to `.old`?
- Retention: keep N old files or delete?
- Timestamp format: include in filename or only in content?

**Impact:** Low — Non-critical feature; can be hardcoded initially.

**Recommendation:** Either:
1. **Option A (Reduce scope):** "Signal files initially append-only without rotation. Revisit if files exceed 10MB in practice."
2. **Option B (Specify):** "Rotate when >1MB: rename to `.1.jsonl`, start new file. Keep max 3 old files. Delete `.4.jsonl` and older."

**Suggested acceptance criterion:**
```
- [ ] When signal file exceeds 1MB:
      - Rename current file to `.1.jsonl`
      - Start new append-only file (same name, same location)
      - Keep 3 historical files (`.1.jsonl`, `.2.jsonl`, `.3.jsonl`)
      - OR document as "future work" if not critical for MVP
```

---

### Minor Clarity Gaps (3 of 13)

#### Gap A: F4 — Conflict Response Details

**Criterion:** "Response on 409: conflict details (held_by, pattern, reason, expires_at)"

**Question:** Does `held_by` contain the agent name (human-readable) or agent ID (UUID)? PR should specify:
```json
{
  "status": 409,
  "error": "file_reserved",
  "conflict": {
    "held_by": "claude-tmux-pane-2",        // ← Human-readable name
    "file": "src/router.go",                  // ← Specific file
    "pattern": "src/*.go",                    // ← Original reservation pattern
    "reason": "architecture refactor",        // ← Agent's stated reason
    "expires_at": "2026-02-14T12:35:00Z"     // ← ISO 8601 timestamp
  }
}
```

**Recommendation:** Add to F4 AC: "held_by field contains human-readable agent name (label or claude-{tmux-pane-N})"

#### Gap B: F7 — Selective Agent Registration

**Criterion:** "SessionStart hook: registers agent only if ~/.config/clavain/intermute-joined exists"

**Question:** What is the onboarding flow? Is this flag set by:
1. User manually: `touch ~/.config/clavain/intermute-joined`?
2. By `/interlock:join` command (recommended)?
3. By first-run setup script?

**Current state:** F8 mentions `/interlock:join` sets the flag, but flow is implicit.

**Recommendation:** Clarify in F7 AC:
```
- [ ] SessionStart hook reads ~/.config/clavain/intermute-joined to decide whether to register
- [ ] Flag is created by /interlock:join command (user opt-in)
- [ ] Flag is removed by /interlock:leave command (user opt-out)
- [ ] Flag absence = silent skip (graceful degradation)
```

#### Gap C: F8 — Human-Readable Agent Names

**Criterion:** "Commands use human-readable agent names (label or claude-{tmux-pane} or claude-{session:0:8})"

**Question:** Precedence? If user provides label, does tmux pane name override? Current spec is ambiguous.

**Recommendation:** Clarify in F8 AC:
```
- [ ] /interlock:join --name "BlueTiger" registers with name "BlueTiger"
- [ ] /interlock:join without --name: tries to detect tmux pane, falls back to claude-{session:0:8}
- [ ] Fallback detection: tmux list-panes -t $(echo $TMUX | cut -d, -f1) -F "#{pane_id}:#{pane_title}"
```

---

## Integration & Edge Cases

### Missing Edge Cases (Low Severity)

#### Edge Case A: Agent Name Collisions

**Scenario:** Two agents both named "BlueTiger" register simultaneously.

**Current spec:** No handling mentioned. Does intermute reject duplicate names? Allow both?

**Recommendation:** Add to F2 or F8 AC:
```
- [ ] Agent names need not be unique (two agents can have the same name)
- [ ] Internally, agents are tracked by UUID; name is for human readability only
- [ ] /interlock:status shows (name, uuid) pairs to disambiguate collisions
```

#### Edge Case B: Signal File Loss During Rotation

**Scenario:** Process crashes mid-rotation while `.jsonl` is being renamed to `.1.jsonl`.

**Current spec:** No recovery mentioned.

**Recommendation:** Add to F9 AC:
```
- [ ] Rotation is idempotent: if .1.jsonl exists, append to it, don't re-rotate
- [ ] On startup, check for orphaned `.1.jsonl` (no current `.jsonl`); rename back
```

#### Edge Case C: intermute Service Crashes During Reservation Hold

**Scenario:** Agent A reserves `src/router.go`, then intermute crashes and restarts.

**Current spec:** "Startup sweep: On launch, release ALL reservations >5 minutes old."

**Question:** What if <5 minutes? Does Agent A lose its reservation? Can Agent B now reserve the same file?

**Recommendation:** Document explicitly in F3 AC:
```
- [ ] Startup sweep releases only reservations >5 minutes old (assumes 5min = "stale" after crash)
- [ ] Reservations <5 minutes old are preserved (Agent A's edit session likely still active)
- [ ] Agents experiencing service restart: heartbeat loop halts → re-register via SessionStart hook
```

#### Edge Case D: Git Hook with Partial Commits

**Scenario:** User has 5 changed files staged; pre-commit hook fails on file 3; user fixes and re-stages files 1-5.

**Current spec:** "Hook aborts commit with clear error message."

**Question:** Do files 1 & 2 remain staged? Can user skip hook with `--no-verify` and commit a subset?

**Recommendation:** Add to F10 AC:
```
- [ ] Hook fails fast: first conflict found, error message printed, exit 1 (git aborts entire commit)
- [ ] User can skip hook: git commit --no-verify (documented escape hatch in error message)
- [ ] User can resolve: request_release, wait for expiry, or resolve conflict with reservation holder
```

---

## User Experience Review

### Strength: Explicit Opt-In Pattern

**Finding:** `/interlock:join` command creates clear user agency.

**Evidence:**
- Silent registration is rejected (good — avoids surprise coordination mode)
- Onboarding flag is persistent (`~/.config/clavain/intermute-joined`)
- `/interlock:leave` is symmetric (clear opt-out)

**Assessment:** Strong UX pattern. Matches established preference in flux-drive review.

---

### Concern: Error Recovery Path Clarity

**Finding:** PreToolUse:Edit hook warning message is sketched but not finalized.

**Current spec:** "Advisory warning (not blocking) with recovery instructions"

**Issue:** What exactly is the recovery message? Examples:

**Current (vague):**
```
File reserved by BlueTiger: architecture refactor (expires in 2m 30s).
Consider: intermute_request_release, work on other files, or wait for expiry.
Git pre-commit will enforce.
```

**Better (specific):**
```
INTERLOCK: src/router.go is reserved by BlueTiger (architecture refactor, expires 14:35 UTC)

Recover in 3 ways:
  1. Work on other files now; come back when BlueTiger releases
  2. Send release request: intermute_request_release(file="src/router.go", to="BlueTiger")
  3. Wait 2m 30s for reservation to expire

Note: git commit will block this file until resolved.
```

**Recommendation:** Move exact message template to F7 AC or a separate skill (`conflict-recovery`).

---

### Concern: Statusline Information Density

**Finding:** F13 proposes "N agents | M files reserved" indicator.

**Question:** Placement? Permanence?

**Current:** "Persistent indicator when coordination active"

**Concern:** If 5 agents are active with 15 files reserved, is `5 agents | 15 files` useful, or too dense?

**Recommendation:** Specify format and placement in F13 AC:
```
- [ ] Indicator format: "${NUM_AGENTS} agents | ${NUM_FILES} reserved"
- [ ] Placement: interline statusline, coordination layer
- [ ] Shown only when INTERMUTE_AGENT_ID is set (active session)
- [ ] Tappable to show /interlock:status equivalent (optional UX enhancement)
```

---

## Product & Strategy Fit

### Problem Validation

**Given:** "Multiple Claude Code sessions editing same repo overwrite each other's files, create merge conflicts, lose work silently."

**Evidence provided:** Problem statement + anecdotal (no data on frequency/impact)

**Assessment:** Problem is real (stated in flux-drive review), but frequency/severity are not quantified.

**Recommendation for later:** After implementation, add instrumentation to measure:
1. % of multi-agent sessions that experience file conflicts (before coordination)
2. % adoption of `/interlock:join` among users with multiple active sessions
3. Conflict resolution time (time from conflict detection to resolution)

This will validate whether coordination is a critical pain point or a nice-to-have for power users.

---

### Success Criteria (Missing)

**Finding:** PRD lacks explicit success signals post-launch.

**Examples of good success criteria:**
- "50% of multi-agent sessions use `/interlock:join` within 2 weeks"
- "Zero silent file overwrites in instrumented test runs"
- "Conflict detection latency <100ms (p95)"

**Current:** PRD focuses on feature delivery, not outcome measurement.

**Recommendation:** Add "Success Criteria" section:
```markdown
## Success Criteria

### Technical
- [ ] Atomic check-and-reserve API prevents TOCTOU races (verified by race detector tests)
- [ ] Stale reservation cleanup has zero false positives in 1-week stress test
- [ ] Signal file writes incur <10ms latency at 100 agents

### User
- [ ] 40% adoption rate (% of users issuing /interlock:join) within 2 weeks
- [ ] Zero reports of silent file overwrites in feedback
- [ ] Conflict resolution guided by skills (agents use intermute_request_release without manual escalation)
```

---

## Feature-by-Feature Assessment

| Feature | Status | Blocker | Notes |
|---------|--------|---------|-------|
| **F1: Circuit Breaker + Retry** | READY | — | Concrete, testable, standard Go pattern |
| **F2: Session Identity** | READY | — | UUID validation clear; collision rejection logic tight |
| **F3: Stale Cleanup** | NEEDS CLARITY | — | "Signal emission" needs definition (see Issue A) |
| **F4: Atomic Check-Reserve** | READY | — | Responses well-defined; minor: clarify held_by field |
| **F5: Unix Socket** | READY | — | Standard implementation; mode 0660 appropriate |
| **F6: MCP Server** | READY | — | 9 tools scoped well; fallback (socket→TCP) good |
| **F7: Hooks** | NEEDS CLARITY | — | OnboardingFlow implicit; clarify ~.config/clavain/ flag (see Gap B) |
| **F8: Commands** | READY | — | Minor: clarify name precedence (label > tmux > session:0:8) |
| **F9: Signals** | NEEDS CLARITY | — | Rotation strategy ambiguous (see Issue B) |
| **F10: Git Hook** | NEEDS UX POLISH | — | Error messages need finalization before rollout |
| **F11: Skills** | READY | — | Referenced in PRD; content TBD but scope clear |
| **F12: Clavain Integration** | READY | — | Follows established shim pattern (interphase) |
| **F13: interline Integration** | READY | — | Priority placement clear; info density TBD (see concern) |

---

## Risk Assessment

### Risk #1: Signal File Atomicity Under Load (Medium)

**Scenario:** 10 agents simultaneously reserve files; signal writes interleave.

**Current mitigation:** "Append-only JSONL with O_APPEND (atomic for <4KB payloads on Linux)"

**Gap:** What if signal events (JSON object + newline) exceed 4KB? Partial writes corrupt JSONL.

**Recommendation:**
1. Measure typical signal size (likely <200 bytes)
2. Document assumption in F9 AC: "Assume signal events <4KB (padding if needed)"
3. Add integration test: 10 concurrent writes to signal file, verify file integrity

**Likelihood:** Low (signals are ~200 bytes, 4KB is safe margin)
**Impact:** High (corrupted signal files break interline statusline)

---

### Risk #2: Non-Goals Viability (Medium)

**Scenario:** Users request auto-reserve on edit (convenience) or broadcast messages (team coordination).

**Current:** Both are non-goals with rationale ("false sense of safety", "over-engineering").

**Gap:** Rationale is sound but hasn't been tested against real usage.

**Recommendation:**
1. After 2-week MVP launch, survey users on convenience vs. safety trade-off
2. Keep data on "could have used auto-reserve" incidents
3. Document decision point: "Revisit auto-reserve if >3 users request in first month"

**Likelihood:** Medium (user feedback after MVP)
**Impact:** High (pivoting design if assumptions wrong)

---

### Risk #3: Git Hook Error Message UX (Low)

**Scenario:** User runs `git commit` with 5 conflicting files; hook produces 5 error messages.

**Current:** "Hook aborts commit with clear error message including: file, holder, reason, expiry, recovery steps"

**Gap:** Message template is not in PRD; needs UX review.

**Recommendation:**
1. Finalize error message template in F10 AC
2. Test with 3-5 users on message clarity
3. Include in smoke tests

**Likelihood:** High (will encounter in testing)
**Impact:** Low (easy to fix, affects UX only)

---

## Dependency Health

### intermute (`/root/projects/intermute/`)

**Status:** Assumed stable. PRD depends on existing APIs:
- Agent registry (POST /api/agents, GET /api/agents)
- File reservations (POST/GET /api/reservations)
- Messaging (POST/GET /api/messages)

**Risk:** If intermute APIs change, Interlock MCP tools break.

**Recommendation:** Lock intermute version in Interlock's dependencies. Interlock's MCP tools are the contract; don't change intermute APIs without coordinating.

### interline (`/root/projects/interline/`)

**Status:** Assumed stable. PRD depends on signal file reading + statusline priority system.

**Risk:** interline's priority order or signal file format change → Interlock signals don't display.

**Recommendation:** Document signal file format in interline's AGENTS.md. Interlock's signals must match interline's expected schema.

---

## Phasing & Timeline Realism

**PRD states:** "Total: ~3 days implementation"

**Assessment:** Realistic for experienced Go + bash + Claude Code plugin developers.

**Breakdown:**
- Phase 1 (intermute core): 1 day — Standard Go + SQL, well-scoped
- Phase 2 (Interlock companion): 1-2 days — CLI tools + MCP server + hooks, requires plugin architecture knowledge
- Phase 3 (Integration): 0.5 day — Glue code + tests

**Assumption:** Assumes Phase 1 APIs are stable and don't require intermute schema review.

**Recommendation:** Add integration test early (Phase 2) to catch intermute API mismatches before final Phase 3 polish.

---

## Documentation Gaps

| Gap | Severity | Recommendation |
|-----|----------|-----------------|
| F3: "Signal emission" definition | Medium | Clarify (webhook/log/signal file) + retry behavior |
| F7: Onboarding flow | Medium | Document ~/.config/clavain/intermute-joined flag creation |
| F8: Name precedence | Low | Label > tmux pane > session:0:8 order (or allow config) |
| F9: Rotation strategy | Low | Either reduce scope (no rotation MVP) or specify archive/retention |
| F10: Error message template | Low | Provide exact message template + UX test |
| F13: Statusline info density | Low | Clarify "N agents | M files" format + placement |
| Success criteria | Medium | Add post-launch measurement plan (adoption, conflict incidents) |

---

## Final Verdict

### Is this PRD ready for development?

**YES, with targeted clarifications.**

The PRD is:
- ✅ Well-scoped with independent features
- ✅ Based on solid flux-drive review
- ✅ Architecturally sound (multi-layer, graceful degradation)
- ✅ Mostly concrete acceptance criteria (85% specific)
- ❓ Three ambiguities (F3, F7, F9) + three gaps (message templates, info density, success metrics)

### Recommended prep work (before dev sprint):

1. **Resolve F3 (signal emission):** Define what "fire-and-forget" means — webhook, intermute event API, or Interlock polling?
2. **Clarify F7 (onboarding):** Document ~/.config/clavain/intermute-joined creation in /interlock:join flow.
3. **Pick F9 (rotation):** Either cut signal rotation as post-MVP, or specify archive/retention strategy.
4. **Draft F10 (error messages):** Provide 2-3 example pre-commit hook error outputs for UX review.
5. **Add success criteria:** Quantify what "good" looks like post-launch (adoption %, conflict resolution time, etc.).

### Estimated pre-work time: 1-2 hours (clarification calls + spec updates).

After clarifications, this PRD is suitable for:
- Code review (architecture + API contracts)
- Test planning (unit, integration, smoke)
- User story breakdown (per phase)
- Marketing/docs (feature discovery, onboarding guides)

---

## Appendix: Feature Dependency Graph

```
┌─────────────────────────────────────────────────────────────┐
│ intermute Enrichments (Phase 1) - Independent              │
├─────────────────────────────────────────────────────────────┤
│ F1: Circuit Breaker + Retry                                │
│ F2: Session Identity (survive restarts)                    │
│ F3: Stale Reservation Cleanup                              │
│ F4: Atomic Check-and-Reserve API                           │
│ F5: Unix Domain Socket Listener                            │
└────────────────┬────────────────────────────────────────────┘
                 │ (depends on stable intermute APIs)
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ Interlock Companion (Phase 2) - Semi-Independent           │
├─────────────────────────────────────────────────────────────┤
│ F6: MCP Server (wraps intermute HTTP/socket)               │
│ F7: Hooks (SessionStart, Stop, PreToolUse:Edit advisory)   │
│ F8: Commands (join, leave, status, setup)                  │
│ F9: Signal File Adapter (JSONL append-only)                │
│ F10: Git Pre-Commit Hook Generator                         │
│ F11: Coordination Skills (teaching skills)                 │
└────────────────┬────────────────────────────────────────────┘
                 │ (depends on Interlock stable)
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ Clavain + interline Integration (Phase 3) - Glue          │
├─────────────────────────────────────────────────────────────┤
│ F12: Clavain shim delegation + doctor check                │
│ F13: interline signal reading + statusline priority        │
└─────────────────────────────────────────────────────────────┘

Dependency flow: F1-F5 independent → F6-F11 depend on 1-5 → F12-F13 depend on 6-11
Parallel: F6-F11 can overlap; F12-F13 are blocking only for final integration test.
```

---

## Appendix: Acceptance Criteria Checklist Template

For dev team: Use this to track acceptance criteria verification.

```markdown
## Phase 1: intermute Enrichments (intermute v0.5.0)

### F1: Circuit Breaker + Retry
- [ ] CircuitBreaker struct implemented with sync.Mutex
- [ ] States: CLOSED → OPEN (after 5 failures) → HALF_OPEN (after 30s) → CLOSED
- [ ] RetryOnDBLock: 7 attempts, 0.05s base, 25% jitter
- [ ] Unit tests: breaker opens/resets/retries correctly
- [ ] go test -race passes

### F2: Session Identity
- [ ] session_id field added to RegisterAgentRequest
- [ ] UUID validation on session_id (reject malformed)
- [ ] Active collision rejection: 409 if heartbeat <5min
- [ ] Schema migration: agents.session_id (nullable, unique)
- [ ] Tests: reuse after stale, reject active, null creates new

### F3: Stale Reservation Cleanup
- [ ] Sweep goroutine: DELETE WHERE expires_at < ? AND agent_id NOT IN (active agents)
- [ ] Startup sweep: release all reservations >5min old
- [ ] ~~Graceful shutdown~~ (out of scope? clarify)
- [ ] Tests: sweep correctness, startup recovery, active reservation preservation

### F4: Atomic Check-and-Reserve
- [ ] POST /api/reservations?if_not_conflict=true endpoint
- [ ] Single transaction: check + insert
- [ ] 201 response: full reservation details
- [ ] 409 response: {held_by, file, pattern, reason, expires_at}
- [ ] Tests: concurrent atomicity, idempotent re-reserve

### F5: Unix Domain Socket
- [ ] --socket /var/run/intermute.sock flag
- [ ] Mode 0660, owned by intermute user
- [ ] Health endpoint accessible via curl --unix-socket
- [ ] TCP fallback available
- [ ] Tests: socket connect, permission enforcement

## Phase 2: Interlock Companion (Interlock v0.1.0)

### F6: MCP Server
- [ ] bin/interlock-mcp binary (Go or shell)
- [ ] 9 tools: reserve_files, release_files, etc.
- [ ] Unix socket fallback to TCP
- [ ] .mcp.json with CLAUDE_PLUGIN_ROOT paths
- [ ] Tests: tool schemas, error handling

[... continue for F7-F13 ...]
```

---

**Review complete. Ready for handoff to dev team.**
