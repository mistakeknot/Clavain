# Stale Subagent Notification Fix
**Phase:** planned (as of 2026-02-20T03:08:23Z)

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Goal:** Prevent stale subagent notifications from flooding context after context compaction by detecting the `compact` trigger in SessionStart and injecting a warning instead of re-reporting already-delivered agents.

**Architecture:** Read `source` from SessionStart HOOK_INPUT. When `source == "compact"`, skip the full inflight agent detection (manifest + live scan) and inject a compact-specific `additionalContext` warning telling Claude that task-notifications from prior agents are stale and should not be re-actioned.

**Tech Stack:** Bash (session-start.sh), jq

---

### Task 1: Read `source` from HOOK_INPUT and branch on compact

**Files:**
- Modify: `hooks/session-start.sh:7-8` (after HOOK_INPUT read)

**Step 1: Add source extraction after HOOK_INPUT read**

After line 7 (`HOOK_INPUT=$(cat)`), add:

```bash
# Detect trigger type (startup, resume, clear, compact)
_hook_source=$(echo "$HOOK_INPUT" | jq -r '.source // "startup"' 2>/dev/null) || _hook_source="startup"
```

**Step 2: Wrap inflight detection in source guard**

Find the inflight agent detection block (lines 227-272 in session-start.sh). Wrap it:

```bash
# In-flight agent detection — skip on compact (agents already delivered this session)
if [[ "$_hook_source" != "compact" ]]; then
    # ... existing inflight detection code (lines 229-272) ...
fi
```

**Step 3: Add compact-specific warning injection**

After the inflight detection block, add:

```bash
# Compact trigger — warn about stale notifications instead of re-detecting
if [[ "$_hook_source" == "compact" ]]; then
    inflight_context="\n\n**Context was compacted.** Task-notifications from background agents received after this point may reference work already completed or reviewed. Check agent output freshness before re-actioning."
fi
```

**Step 4: Syntax check**

Run: `bash -n hooks/session-start.sh`
Expected: No output (clean syntax)

**Step 5: Commit**

```bash
git add hooks/session-start.sh
git commit -m "fix(session-start): detect compact trigger, skip stale inflight detection"
```

---

### Task 2: Verify with manual test

**Files:**
- Test: `hooks/session-start.sh`

**Step 1: Test startup source (default behavior preserved)**

```bash
echo '{"session_id":"test-123","source":"startup"}' | bash hooks/session-start.sh
```

Verify: Output JSON has `additionalContext` with normal content (inflight detection would run if agents existed).

**Step 2: Test compact source (new behavior)**

```bash
echo '{"session_id":"test-123","source":"compact"}' | bash hooks/session-start.sh
```

Verify: Output JSON has `additionalContext` containing "Context was compacted" warning. Should NOT contain "In-flight agents" section.

**Step 3: Test missing source (defaults to startup)**

```bash
echo '{"session_id":"test-123"}' | bash hooks/session-start.sh
```

Verify: Behaves identically to startup source.

**Step 4: Commit test results (if any test script created)**

No test file needed — these are manual verification commands.
