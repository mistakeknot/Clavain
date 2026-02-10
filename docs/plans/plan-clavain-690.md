# Plan: Clavain-690 — Surface per-agent completion ticks during 3-5 min wait

## Context
During flux-drive Phase 2, after launching agents with `run_in_background: true`, the orchestrator waits up to 5 minutes for `.md` files to appear in OUTPUT_DIR. Currently this is a silent wait — the user sees nothing until all agents finish or timeout. The dependencies (Clavain-8xs atomic rename protocol, Clavain-nta parallel dispatch correctness) are now resolved, so we can safely poll for completion.

## Current State
- `skills/flux-drive/phases/launch.md` Step 2.3 (lines 168-191) checks for `.md` files but only at the end
- Completion signal: `.md.partial` → `.md` rename (atomic)
- `<!-- flux-drive:complete -->` comment is the final marker before rename
- No progress reporting during the wait

## Implementation Plan

### Step 1: Add polling loop instructions to launch.md Step 2.3
**File:** `skills/flux-drive/phases/launch.md`

After all agents are dispatched (end of Step 2.2), replace the current "wait for completion" block with a polling-based progress reporter:

1. **Initial status line**: After dispatch, print a status table showing all launched agents with `⏳` status:
   ```
   Agent dispatch complete. Waiting for results...
   ⏳ architecture-strategist
   ⏳ security-sentinel  
   ⏳ go-reviewer
   ```

2. **Polling loop** (every 30 seconds, up to 5 minutes):
   - Use `Glob` to check for `{OUTPUT_DIR}/*.md` files (not `.partial`)
   - For each new `.md` file found since last check, print a tick:
     ```
     ✅ architecture-strategist (45s)
     ```
   - Print running count: `[2/5 agents complete]`

3. **Early completion**: If all agents have `.md` files before timeout, stop polling immediately.

4. **Timeout handling**: After 5 minutes, report which agents are still pending:
   ```
   ⚠️ Timeout: security-sentinel still running (300s)
   ```

### Step 2: Add equivalent polling to launch-codex.md
**File:** `skills/flux-drive/phases/launch-codex.md`

Same polling pattern but adapted for Codex dispatch:
- Codex agents write directly to OUTPUT_DIR, same `.md` completion signal
- Poll interval: 30 seconds (same as Task dispatch)
- Note: Codex dispatch uses `timeout: 600000` (10 min) on Bash calls, so outer polling should also extend to 10 min for Codex mode

### Step 3: Update SKILL.md Phase 2 description
**File:** `skills/flux-drive/SKILL.md`

Add a brief note in the Phase 2 section that progress is reported during the wait, so users know to expect it.

## Design Decisions
- **30-second polling interval**: Frequent enough to feel responsive, infrequent enough to not spam. Agents typically take 1-3 minutes.
- **Glob-based detection**: Aligns with existing completion protocol (`.md` file existence = done). No new completion signals needed.
- **Time elapsed per agent**: Useful for identifying slow agents and calibrating expectations.
- **No spinner/animation**: This is a skill prompt, not code. The orchestrator (Claude) just prints text updates.

## Files Changed
1. `skills/flux-drive/phases/launch.md` — Add polling progress section to Step 2.3
2. `skills/flux-drive/phases/launch-codex.md` — Add equivalent polling for Codex mode
3. `skills/flux-drive/SKILL.md` — Minor note about progress reporting

## Estimated Scope
~30-40 lines of new instructional content across 3 files. No code changes — purely prompt/skill instructions.

## Acceptance Criteria
- [ ] During Phase 2 wait, user sees which agents are pending
- [ ] As each agent completes, a tick appears with elapsed time
- [ ] Running count shows progress (e.g., "3/6 agents complete")
- [ ] Timeout clearly identifies which agents are still running
- [ ] Works for both Task dispatch and Codex dispatch modes
