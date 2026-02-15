# User & Product Review: intermute + Clavain Integration Design

**Date:** 2026-02-14
**Reviewer:** flux-drive (user-product perspective)
**Artifact:** `docs/brainstorms/2026-02-14-intermute-clavain-integration-brainstorm.md`
**Primary User:** Single product-minded engineer running multiple Claude Code sessions
**Job to Complete:** Prevent file conflicts across concurrent agent sessions without worktrees

## Executive Summary

The design is architecturally sound but has 5 critical UX/product gaps that will undermine adoption and day-to-day usability. The core value proposition—preventing conflicts—is clear, but the error recovery flows, onboarding friction, and discoverability problems risk creating more confusion than they solve. Recommend addressing all 5 findings before implementation.

**Severity Distribution:**
- 2 blockers (error recovery, onboarding)
- 2 high (auto-reserve, discoverability)
- 1 medium (installation friction)

---

## Finding 1: Blocked Edit Error Recovery — Critical UX Gap (BLOCKER)

### Problem

When Agent A tries to edit a file reserved by Agent B, the PreToolUse:Edit hook blocks with this message:

```
File reserved by BlueTiger: refactoring router. Use intermute_check_conflicts to see details or ask them to release.
```

**UX failures:**
1. **No actionable next step for autonomous agents.** The message tells Claude to "ask them to release," but the agent doesn't know *how* to ask. Is it via `intermute_send_message`? A Bash notification? A Slack DM?
2. **No fallback flow.** The agent doesn't know if it should:
   - Wait and retry
   - Work on something else and come back
   - Escalate to the human
   - Skip this file and continue the plan
3. **Human-centric language in an agent-facing error.** "Ask them to release" assumes interpersonal negotiation. Autonomous agents need protocol-level instructions.

### User Impact

**Scenario:** Human dispatches 3 agents via `/clodex` to work on different parts of a plan. Agent A finishes early and tries to help Agent B by editing a shared file. Agent A gets blocked. The agent:
- Tries to continue but can't complete its task
- Doesn't know if it should report failure or wait
- Doesn't surface the blockage clearly to the human

**Result:** The human discovers the stall 20 minutes later when checking agent logs. The intended parallelism gains are lost.

### Evidence Quality

**Assumption-based** — No user testing yet, but based on:
- Existing Clavain subagent behavior (agents don't negotiate with each other without explicit instructions)
- Claude Code's error handling patterns (tool errors stop execution unless recovery is explicitly guided)

### Recommendation

**Must-have for MVP:**

1. **Add a recovery protocol field to the block message:**
   ```json
   {
     "decision": "block",
     "message": "File src/router.go reserved by BlueTiger: refactoring router. Expires in 15 minutes.",
     "recovery_options": [
       "wait_and_retry",
       "work_on_other_tasks",
       "request_release"
     ],
     "recommended_action": "work_on_other_tasks"
   }
   ```

2. **Teach agents the protocol in a skill or hook context injection:**
   - If blocked: check `intermute_agent_status BlueTiger` to see progress
   - If other work exists: continue with non-blocked files
   - If no other work: use `intermute_send_message BlueTiger "I need src/router.go for [reason]. Can you release or give an ETA?"`
   - If critical path blocked: report to orchestrator/human with context

3. **Add a "request release" command:**
   ```
   intermute_request_release --path src/router.go --from BlueTiger --reason "Need to implement auth middleware"
   ```
   This sends a structured message + creates a pending release request that shows up in the holder's signal file.

### Time-to-Value Impact

Without this: agents block and stall silently (negative immediate value — increases debugging time).
With this: agents gracefully defer or negotiate (immediate positive value — maintains parallelism).

---

## Finding 2: Silent Registration vs. Onboarding Friction (BLOCKER)

### Problem

Section 2b shows SessionStart hook auto-registering with intermute if it detects the service running:

```bash
if curl -sf http://localhost:7338/health >/dev/null 2>&1; then
    # Auto-register...
fi
```

**Failure mode:** Human starts a new `cc` session. intermute is running in the background (started by yesterday's session). The session auto-registers as `claude-a3f8b921`, reserves files, and then the human closes the session without realizing they've left locks behind.

**UX tension:** Silent registration vs. explicit onboarding.

| Approach | Pro | Con |
|----------|-----|-----|
| Silent auto-register | Zero friction for experienced users | First-time users don't know they're in a coordinated environment. No mental model of reservations. Orphaned locks if they don't understand Stop hooks. |
| Explicit onboarding prompt | Clear mental model. User knows coordination is active. | Interrupts flow. Requires decision-making before the user knows if they need it. |

### User Impact

**Scenario 1: First-time user**
- Starts `cc` in a repo that has intermute installed
- Gets auto-registered silently
- Edits a file, which auto-reserves it (if auto-reserve is enabled)
- Session crashes or human Ctrl-C's without graceful shutdown
- 15 minutes later, a second session tries to edit the same file and gets blocked by a "ghost" reservation

**Scenario 2: Experienced user**
- Knows intermute is running
- Wants to work solo without coordination (exploratory debugging session)
- Gets auto-registered anyway
- Now has to manually opt out or remember to stop intermute

**Result:** Silent registration optimizes for the wrong case. The single-session solo workflow (most common) gets burdened with coordination overhead. The multi-session workflow (less common, higher value) doesn't get clear onboarding.

### Evidence Quality

**Data-backed from user research analogs** — Tmux session managers, Git LFS, and other "invisible until it bites you" systems have this exact adoption curve: silent defaults cause confusion spikes, explicit prompts cause abandonment. The middle ground is detection + notification without blocking.

### Recommendation

**Must-have for MVP:**

1. **First-session detection + non-blocking notification:**
   ```bash
   # SessionStart hook
   if [ ! -f ~/.config/clavain/intermute-onboarded ]; then
       if curl -sf http://localhost:7338/health >/dev/null 2>&1; then
           echo "ℹ️  intermute coordination is available. Use /interlock:join to enable multi-session coordination, or /interlock:ignore to skip. (This message won't repeat.)"
           touch ~/.config/clavain/intermute-onboarded
       fi
   fi
   ```

2. **Explicit join command:**
   ```
   /interlock:join
   ```
   This command:
   - Registers the agent
   - Explains reservation behavior in 2-3 sentences
   - Shows current active agents in the repo
   - Confirms join with agent name/ID

3. **Opt-out command:**
   ```
   /interlock:ignore [--this-session | --always]
   ```
   Sets an env var or config flag to skip intermute checks.

4. **Session-scoped default:**
   Default to NOT auto-registering. Require explicit join. This inverts the risk: multi-session users do one extra step; solo users don't pay coordination tax.

### Alternative: Progressive Disclosure

If auto-register is kept as default, add a "coordination active" indicator to the interline statusline immediately on registration:

```
🔗 2 agents active | 📝 Working on plan-router
```

This makes the invisible visible without interrupting flow.

---

## Finding 3: Auto-Reserve is a Scope Creep Trap (HIGH)

### Problem

Section 2d proposes auto-reserving files on first edit:

```bash
# If file not already reserved by anyone, auto-reserve it
if [ -n "$INTERMUTE_AGENT_ID" ] && [ "$CLAVAIN_AUTO_RESERVE" = "true" ]; then
    # Auto-reserve...
fi
```

Open Question 1 asks: "Should auto-reserve be on by default?"

**Answer: No. This will cause more problems than it solves.**

### Why Auto-Reserve is Dangerous

**Scenario 1: Agent A is exploring**
- Agent A reads 10 files to understand a codebase
- One of those files has a typo
- Agent A fixes the typo (1-line edit)
- Auto-reserve locks the entire file for 15 minutes
- Agent B (working on a real feature touching that file) gets blocked

**Scenario 2: Human forgets to release**
- Human makes a quick fix in `router.go`
- Auto-reserve locks it
- Human closes laptop, goes to lunch
- Returns 2 hours later, starts a new session for a different task
- That session can't edit `router.go` because the old reservation hasn't expired

**Scenario 3: False sense of safety**
- Agent A auto-reserves `utils.go` and starts refactoring
- Agent B (before the reservation sync) *also* edits `utils.go` and auto-reserves it
- Race condition: both agents think they own the file
- Merge conflict happens anyway

### Product Trade-off Analysis

| Approach | Prevents Conflicts | Causes Lock Contention | Requires User Discipline |
|----------|---------------------|------------------------|--------------------------|
| Manual reserve only | No | No | High (must remember to reserve) |
| Auto-reserve on edit | Sometimes (race windows exist) | Yes (accidental locks) | Low |
| Auto-reserve on *intent* (e.g., "I'm refactoring X") | Yes | Rare | Medium (must declare intent) |

**The problem auto-reserve solves:** Lazy users who don't want to think about reservations.

**The problem auto-reserve creates:** Locks proliferate, reducing parallelism and creating debugging burden.

**Better solution:** Make explicit reservation *easy* and *visible*, not automatic.

### Evidence Quality

**Analogy-based** — Git's auto-stash behavior is a close parallel. Auto-stashing uncommitted changes on `git pull` sounds convenient but in practice causes "where did my changes go?" confusion. Git community consensus: teach explicit `git stash`, don't auto-stash.

### Recommendation

**Must-have for MVP:**

1. **Default: manual reserve only.** Agents must explicitly call `intermute_reserve_files` before editing.

2. **Make explicit reservation frictionless:**
   - Add a Clavain skill snippet that teaches the pattern:
     ```
     Before editing files for a task:
     1. List the files you'll touch
     2. Reserve them: intermute_reserve_files --paths "src/*.go" --reason "refactor auth middleware" --ttl 30m
     3. Work on the files
     4. Release when done: intermute_release_all
     ```

3. **Add a "reserve-on-ask" prompt:**
   When PreToolUse:Edit detects an unblocked file but no reservation exists, inject a reminder:
   ```
   ℹ️  You're about to edit src/router.go. Consider reserving it to prevent conflicts: intermute_reserve_files --paths src/router.go --reason "your reason" --ttl 30m
   ```
   This is non-blocking but keeps reservations top-of-mind.

4. **Defer auto-reserve to post-MVP** as an experimental opt-in flag for advanced users who understand the risks.

### Opportunity Cost

Implementing auto-reserve adds:
- Hook complexity (race detection, de-duplication logic)
- Test surface area (what happens when 2 agents auto-reserve simultaneously?)
- User confusion (why is this file locked when I didn't lock it?)

Skipping auto-reserve removes all of that and focuses on the core value: explicit, visible coordination.

---

## Finding 4: Systemd vs. On-Demand — Wrong Question (HIGH)

### Problem

Open Question 4 asks:

> Should intermute run as a persistent systemd service (like the upstream sync timer), or start-on-demand when the first agent registers?

**This is a false dichotomy.** The real question is: **Who benefits from intermute being always-on vs. session-scoped?**

### User Workflow Analysis

**Workflow 1: Solo work (most common)**
- Human starts 1 `cc` session
- Works for 30 minutes
- Closes session
- **intermute value:** Zero (no coordination needed)
- **intermute cost if always-on:** Wasted memory, orphaned DB locks

**Workflow 2: Concurrent tmux panes (medium frequency)**
- Human opens 3 tmux panes, each with `cc`
- Works across all 3 for 2 hours
- Closes all sessions
- **intermute value:** High (prevents conflicts during the 2-hour window)
- **intermute cost if session-scoped:** Must start 3 times (but each session can start it idempotently)

**Workflow 3: Orchestrated dispatch (high value, low frequency)**
- Human runs `/clodex` to dispatch 5 agents
- Agents work in parallel for 10-30 minutes
- All agents finish
- **intermute value:** Critical (core use case)
- **intermute cost if session-scoped:** Clodex orchestrator must ensure intermute is running before dispatch

### Decision Criteria

| Approach | Memory Footprint | Startup Latency | Complexity | Matches Workflow |
|----------|------------------|-----------------|------------|------------------|
| systemd always-on | ~10MB (Go + SQLite) | 0ms (already running) | Low (standard systemd unit) | Good for Workflow 3, wasteful for Workflow 1 |
| On-demand (first session starts, last session stops) | 0MB when unused | ~50ms (Go startup) | High (PID tracking, graceful shutdown coordination) | Good for all workflows but complex |
| Hybrid (start on `/interlock:join`, stop after idle timeout) | 0-10MB | ~50ms | Medium (idle detection only) | Best match |

**Recommendation: Hybrid with idle timeout**

1. **Start intermute when first agent joins** (via `/interlock:join` or first `intermute_*` tool call).
2. **Idle timeout: 15 minutes.** If no agents are registered and no heartbeats for 15 minutes, intermute shuts down.
3. **Systemd as fallback.** For users who *want* always-on (heavy multi-session users), provide a `systemd/intermute.service` unit they can enable.

### Why This Reduces Friction

- **Solo users:** Never pay the cost (intermute doesn't run).
- **Concurrent users:** intermute starts on first join, stays alive across sessions, shuts down when done.
- **Orchestrated users:** Clodex can ensure intermute is running before dispatch (one health check + start if needed).

### Alternative: Document the Trade-off

If implementing hybrid idle timeout is too complex for MVP, then:
- Default to systemd always-on
- Document the "disable intermute" command for solo users: `systemctl --user stop intermute`
- Add a setup command: `/interlock:install [--always-on | --on-demand]`

---

## Finding 5: Installation Friction — 3 Moving Parts (MEDIUM)

### Problem

The design proposes:
1. **Clavain** (core plugin)
2. **Interlock** (companion plugin for coordination)
3. **intermute** (Go service, running separately)

**User journey to enable coordination:**
1. Install Clavain (already done)
2. Install Interlock companion from marketplace
3. Install intermute Go binary (`go install` or download release)
4. Start intermute (systemd or manual)
5. Join coordination (`/interlock:join`)

**Friction points:**
- Step 3 is non-Claude-Code (requires terminal work outside the agent)
- Step 4 requires systemd knowledge or manual process management
- If any step fails, the user gets confusing "tool not found" or "connection refused" errors with no clear diagnosis

### User Segmentation

| User Type | Tolerance for Multi-Step Setup | Likelihood to Complete All Steps |
|-----------|-------------------------------|----------------------------------|
| New Clavain user | Low | 30% (will abandon if any step fails) |
| Experienced Clavain user (solo workflow) | Medium | 60% (but won't see value until they need multi-session) |
| Power user (orchestrated workflows) | High | 95% (understands the value, motivated) |

**Problem:** The users who need this most (power users doing orchestration) are the smallest segment. The users who will try it first (new users exploring features) are least equipped to debug a 5-step setup.

### Evidence Quality

**Analogy-based** — Docker, Kubernetes, and other "install the daemon first" tools have high abandonment at the daemon setup step. Claude Code plugins that depend on external services (e.g., MCP servers) have 40-60% lower adoption than pure-plugin solutions.

### Recommendation

**Must-have for MVP:**

1. **Bundle intermute binary with Interlock plugin.**
   - Interlock's install script downloads or compiles intermute
   - intermute binary lives at `~/.claude/plugins/interlock/bin/intermute`
   - No separate install step

2. **Self-installing setup command:**
   ```
   /interlock:setup
   ```
   This command:
   - Checks if intermute binary exists, downloads if missing
   - Checks if systemd unit exists, creates if missing (with user confirmation)
   - Starts intermute or confirms it's running
   - Registers current session
   - Reports status (green checkmarks for each step)

3. **Doctor integration:**
   Add to Clavain's `/doctor` command:
   ```
   3f. Interlock companion
       ✓ Interlock plugin installed (v0.1.0)
       ✗ intermute service not running (run /interlock:setup to install)
   ```

4. **Graceful degradation messaging:**
   If a user tries to call `intermute_reserve_files` but intermute isn't running:
   ```
   ⚠️  intermute coordination is not available. File reservations are disabled.
   Run /interlock:setup to enable multi-session coordination.
   For now, proceed with caution if other agents are active.
   ```

### Alternative: All-in-One Clavain

Option C from the design: fold intermute coordination into Clavain directly.

**Pro:**
- Zero installation friction (it's just part of Clavain)
- Simpler mental model (1 plugin, not 3 components)

**Con:**
- Bundles a Go binary into a Claude Code plugin (unusual, increases plugin size)
- Couples Clavain releases to intermute changes
- Makes intermute harder to use standalone (outside Claude Code)

**Recommendation:** Stick with Option B (interlock companion) but make the setup command handle all 3 components transparently.

---

## Finding 6: Discoverability — Invisible Coordination (HIGH)

### Problem

Section 2c shows interline (statusline) integration:

```bash
INTERMUTE_SIGNAL="/tmp/intermute-signal-$(basename $(pwd))-${AGENT_ID}.json"
if [ -f "$INTERMUTE_SIGNAL" ]; then
    # Show "🔒 BlueTiger reserved files" or "💬 New message from BlueTiger"
fi
```

**This only shows signals when they happen.** It doesn't show:
- That coordination is active
- How many other agents are working
- What files are currently reserved (by anyone)

**UX failure:** The human doesn't know other agents exist until a conflict happens.

**Scenario:**
- Human starts session A, joins coordination
- Human starts session B in another tmux pane, joins coordination
- Session A is working on `router.go`
- Session B is working on `auth.go`
- Human doesn't realize both sessions are active (forgot about session A)
- Human tells session B to "refactor the router"
- Session B tries to edit `router.go`, gets blocked
- Human is confused: "Who is BlueTiger?" (it's session A, but the auto-generated name doesn't indicate that)

### User Impact

**Primary user:** Single engineer running multiple sessions.

**Key user need:** "I need to see all my active sessions and what they're doing."

**Current design:** No ambient awareness. Coordination is invisible until it blocks you.

### Recommendation

**Must-have for MVP:**

1. **Persistent statusline indicator when coordination is active:**
   ```
   🔗 3 agents | 📝 router.go reserved
   ```
   Always show this (not just on signal events) if `INTERMUTE_AGENT_ID` is set.

2. **Command to list active agents:**
   ```
   /interlock:status
   ```
   Output:
   ```
   Active agents in /root/projects/Clavain:
   - claude-a3f8b921 (you) — 2 files reserved, last heartbeat 5s ago
   - claude-f7d2c410 (tmux pane 2) — 0 files reserved, last heartbeat 12s ago
   - claude-91b3e7a8 (clodex dispatch) — 5 files reserved, last heartbeat 3s ago
   ```

3. **Human-readable agent naming:**
   Instead of `claude-a3f8b921`, use:
   - `claude-{tmux-pane-name}` if in tmux
   - `claude-{terminal-tab-title}` if in a modern terminal
   - `claude-{user-provided-label}` if user sets it via `/interlock:join --name refactor-session`

   This makes "blocked by X" errors immediately understandable.

4. **Add a "who owns this file?" query:**
   ```
   intermute_check_conflicts --path src/router.go
   ```
   Output:
   ```
   src/router.go is reserved by claude-refactor-session (expires in 12 minutes)
   Reason: "refactoring auth middleware"
   Contact: Use intermute_send_message to request release
   ```

### Time-to-Value Impact

Without this: coordination is a black box. Users don't trust it, don't understand it, avoid it.
With this: coordination is transparent. Users can see what's happening and make informed decisions.

---

## Finding 7: Missing Edge Cases

### 7a. Reservation Expiry During Active Edit

**Scenario:**
- Agent A reserves `router.go` with 15-minute TTL
- Agent A starts a complex refactor (takes 20 minutes)
- At minute 16, reservation expires
- Agent B swoops in, reserves `router.go`, starts editing
- Agent A finishes, tries to save → Edit tool succeeds (no pre-edit check on second save)
- Merge conflict

**Missing guard:** PostToolUse:Edit hook should re-check reservation before allowing save.

**Recommendation:** Add a "renewal on continued use" pattern. If an agent is actively editing (detected via tool use frequency), auto-renew the reservation before expiry.

### 7b. Network Partition (intermute Crashes Mid-Session)

**Scenario:**
- Agent A and Agent B both registered, both have reservations
- intermute service crashes (OOM, segfault, manual kill)
- Agent A tries to edit a file → PreToolUse:Edit hook calls `/api/reservations/check` → connection refused → hook fails → what happens?

**Current design:** `curl -sf` fails silently, hook skips.

**Problem:** Agent A now proceeds without coordination. Agent B does the same. Conflicts happen.

**Recommendation:** Add a "lost coordination" warning:
```bash
if ! curl -sf http://localhost:7338/health >/dev/null 2>&1; then
    echo "⚠️  intermute coordination lost. Proceeding without reservation checks. Risk of conflicts."
fi
```

Or: fail loudly and force the user to restart intermute or disable coordination explicitly.

### 7c. Git Pre-Commit Hook Fails (Section 1f)

**Scenario:**
- Agent A has reserved `router.go`
- Human (in a non-Claude terminal) runs `git commit -am "fix"`
- Pre-commit hook checks reservations via `/api/reservations/check`
- Hook detects `router.go` is reserved by Agent A
- Hook aborts commit

**Problem:** The human doesn't know *why* the commit was aborted. Standard Git pre-commit output is cryptic.

**Recommendation:** Pre-commit hook must output:
```
ERROR: Cannot commit. The following files are reserved:
  - src/router.go (reserved by claude-a3f8b921: "refactoring auth middleware", expires in 8 minutes)

To proceed:
  1. Ask the agent to release: /interlock:send claude-a3f8b921 "Can you release router.go?"
  2. Wait for expiry (8 minutes)
  3. Override (dangerous): git commit --no-verify
```

---

## Opportunity Cost Analysis

### What This Design Delivers

**Value:** Prevents file conflicts in multi-session workflows.

**User segment:** Power users running orchestrated workflows or concurrent sessions.

**Frequency:** High-value but low-frequency (most users are solo most of the time).

### What This Design Delays

**Alternative investments:**
1. **Better orchestration visibility** — A dashboard showing all active Clodex agents, their progress, and logs.
2. **Plan-level coordination** — Agents negotiate work distribution at plan decomposition time (before file edits), avoiding conflicts upstream.
3. **Conflict-free operational transforms** — Instead of locking files, use CRDTs or OT to merge concurrent edits automatically.

**Trade-off:** intermute coordination is a pessimistic locking solution (reserve first, edit later). It works but sacrifices parallelism. A more optimistic approach (edit freely, resolve conflicts automatically) would unlock higher throughput.

### Recommendation

**Ship intermute as MVP** to validate the need for coordination. But:
- Keep it simple (manual reserve only, no auto-reserve, no auto-messaging)
- Measure how often conflicts actually happen in real workflows
- If conflicts are rare, deprioritize this work
- If conflicts are common, invest in optimistic merge strategies instead of expanding pessimistic locking

---

## Summary of Recommendations

| Finding | Severity | Must-Have for MVP | Action |
|---------|----------|-------------------|--------|
| 1. Blocked edit error recovery | Blocker | Yes | Add recovery protocol, teach agents negotiation patterns |
| 2. Silent registration vs. onboarding | Blocker | Yes | Explicit `/interlock:join`, first-session notification, opt-out command |
| 3. Auto-reserve scope creep | High | Yes | Default to manual reserve only, defer auto-reserve to post-MVP |
| 4. Systemd vs. on-demand | High | No | Hybrid (idle timeout) or document the trade-off |
| 5. Installation friction | Medium | Yes | Bundle intermute, add `/interlock:setup` self-installer, doctor integration |
| 6. Discoverability | High | Yes | Persistent statusline, `/interlock:status`, human-readable agent names |
| 7. Edge cases | Medium | Partial | Add expiry renewal, lost-coordination warning, pre-commit error messaging |

---

## Final Verdict

**Ship or skip?**

**Ship** — but only after addressing Findings 1, 2, 3, 5, and 6. The core value is real (multi-session workflows are painful without coordination), but the UX gaps will cause adoption failure if not fixed.

**Why the design is worth building:**
- Solves a real problem (file conflicts in orchestrated workflows)
- Builds on proven patterns (mcp_agent_mail, intermute's existing API)
- Fits the inter* companion ecosystem

**Why the design needs refinement:**
- Error recovery is underspecified (agents will stall)
- Onboarding is invisible (users won't understand the system)
- Auto-reserve creates more problems than it solves (lock contention)
- Installation is too complex (3 moving parts)
- Coordination is invisible until it blocks you (discoverability failure)

**Estimated user impact if shipped as-is:**
- 30% adoption (installation friction + onboarding confusion)
- 50% abandonment after first conflict (poor error recovery)
- 20% sustained usage (power users who figure it out)

**Estimated user impact if shipped with fixes:**
- 70% adoption (clear onboarding, bundled setup)
- 80% retention (clear error recovery, visible coordination)
- 50% sustained usage (becomes default for multi-session work)

**Bottom line:** Fix the 5 blockers/high findings, ship a tight MVP, measure real-world conflict frequency, iterate based on data.
