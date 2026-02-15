# Research: Codex CLI Dispatch Architecture and WebSocket Opportunity

**Research Date:** 2026-02-12  
**Codex CLI Version:** 0.101.0  
**Context:** Understanding current dispatch patterns to evaluate WebSocket streaming integration

---

## Executive Summary

Clodex currently uses **blocking, fire-and-forget dispatch** via `codex exec` with output collected only at completion via `-o <file>`. This creates a **visibility gap** during long-running Codex sessions (often 5-20+ minutes) where Claude Code has no real-time feedback. Codex CLI already supports **JSONL streaming via `--json`** flag, emitting per-turn and per-item events to stdout, but clodex dispatch.sh doesn't currently capture or use this stream.

**Key opportunity:** Integrate `--json` mode to enable real-time progress visibility without changing Codex CLI itself.

---

## 1. Current Dispatch Architecture

### 1.1 Entry Point: `dispatch.sh`

**Location:** `/root/projects/Clavain/scripts/dispatch.sh` (458 lines)

**Core wrapper** around `codex exec` that:
- Resolves model tiers from `config/dispatch/tiers.yaml` (fast→gpt-5.3-codex-spark, deep→gpt-5.3-codex)
- Injects docs (CLAUDE.md/AGENTS.md) via `--inject-docs` flag
- Supports prompt assembly from templates (`--template` + KEY: sections)
- Writes dispatch state file (`/tmp/clavain-dispatch-$$.json`) for statusline visibility
- Passes through to `codex exec` with flags: `-s <sandbox>`, `-C <workdir>`, `-o <output>`, `-m <model>`, `-i <images>`

**Key pattern (lines 456-457):**
```bash
"${CMD[@]}"  # Blocks until codex exec completes
```

No background execution, no polling, no stream capture. Claude Code's Bash tool call **blocks for the entire Codex session** (timeout: 600000ms = 10 minutes).

### 1.2 Invocation Pattern

From `skills/clodex/SKILL.md` (Step 2 — Dispatch):

```bash
bash "$DISPATCH" \
  --prompt-file "$TASK_FILE" \
  -C "$PROJECT_DIR" \
  -o "/tmp/codex-result-$(date +%s).md" \
  -s workspace-write \
  --tier deep
```

**Flow:**
1. Write prompt to `/tmp/codex-task-<timestamp>.md` (via Write tool)
2. Dispatch via Bash tool with 10-minute timeout
3. Block until completion
4. Read output file via Read tool
5. Parse verdict (`VERDICT: CLEAN` or `NEEDS_ATTENTION`)

### 1.3 Output Collection

**Primary mechanism:** `-o <file>` flag writes **only the final agent message** to file.

**Fallback mechanism (from troubleshooting.md):**
- If output file is empty, sessions are persisted to `~/.codex/sessions/<year>/<month>/<day>/`
- Full transcript available but not used by clodex
- Sessions persist by default (unless `--ephemeral` flag used)

**Current limitations:**
- No intermediate progress visibility
- No streaming output
- If Codex hangs/crashes, Claude has no feedback until timeout
- Multi-task parallel dispatches have no order-of-completion info (all Bash calls block simultaneously)

---

## 2. Codex CLI Capabilities

### 2.1 JSONL Streaming Mode

**Flag:** `--json`  
**Behavior:** "Print events to stdout as JSONL"

**Sample output (from live test):**
```json
{"type":"thread.started","thread_id":"019c5577-ea55-7202-8f16-eab7052aa138"}
{"type":"turn.started"}
{"type":"item.started","item":{"id":"item_0","type":"command_execution","command":"/bin/bash -lc 'echo test'","aggregated_output":"","exit_code":null,"status":"in_progress"}}
{"type":"item.completed","item":{"id":"item_0","type":"command_execution","command":"/bin/bash -lc 'echo test'","aggregated_output":"test\n","exit_code":0,"status":"completed"}}
{"type":"item.completed","item":{"id":"item_1","type":"agent_message","text":"`test`"}}
{"type":"turn.completed","usage":{"input_tokens":42030,"cached_input_tokens":28672,"output_tokens":289}}
```

**Event types observed:**
- `thread.started` — session initialization
- `turn.started` — agent begins thinking
- `item.started` — tool use begins (command_execution, file operations, etc.)
- `item.completed` — tool use completes (includes exit codes, output)
- `turn.completed` — agent finishes turn (includes token usage)

**Key insight:** Codex emits **real-time structured events** but dispatch.sh doesn't capture them.

### 2.2 Other Relevant Flags

| Flag | Purpose | Current Use |
|------|---------|-------------|
| `-o <file>` | Write final message to file | Used for verdict collection |
| `--ephemeral` | Skip session persistence | Not used (sessions persist) |
| `--output-schema <file>` | Enforce JSON schema on final response | Not used |
| `-s <mode>` | Sandbox mode (read-only, workspace-write, danger-full-access) | Used for safety |
| `-C <dir>` | Working directory | Used |
| `-m <model>` | Model override | Used via tier resolution |
| `--full-auto` | Alias for workspace-write + auto-approval | Not used (explicit -s preferred) |

### 2.3 Session Persistence

**Location:** `~/.codex/sessions/<year>/<month>/<day>/`  
**Format:** Markdown transcripts with full conversation history  
**Ownership:** Mixed (501:staff for older sessions, claude-user:claude-user for recent)

Sessions persist by default. No evidence of websocket or streaming beyond JSONL stdout.

---

## 3. Bottlenecks and Limitations

### 3.1 Visibility Gap

**Problem:** Codex sessions can run 5-20+ minutes. During this time:
- Claude has no idea what Codex is doing
- If Codex hangs on a test, no way to detect until timeout
- Parallel dispatches show no order-of-completion (all block simultaneously)
- User sees statusline "dispatching to Codex" with no updates

**Current workarounds:**
- Set aggressive 10-minute timeout (line 111 in SKILL.md)
- Trust self-verification verdicts to avoid re-reading full diffs
- Use Split mode (3 separate agents) for more control (3x dispatch overhead)

### 3.2 No Incremental Feedback

**Problem:** JSONL events stream to stdout but are discarded.

**Useful events being lost:**
- Which files Codex is reading/editing (item.started with file operations)
- Test execution progress (command_execution items with test commands)
- Token usage per turn (turn.completed)
- Error messages from failed commands (item.completed with non-zero exit codes)

### 3.3 Multi-Task Coordination Overhead

**Parallel delegation mode (SKILL.md lines 136-185):**
- Launches N tasks with separate `bash "$DISPATCH"` calls in one message
- All block simultaneously
- No way to know which finishes first
- Manual file-overlap checking required before dispatch

**Sequential dependencies:**
- Must wait for Task N to complete before starting N+1
- No pipelining possible

---

## 4. Current Streaming/Real-Time Features

### 4.1 Dispatch State File

**Location:** `/tmp/clavain-dispatch-$$.json`  
**Written by:** dispatch.sh (lines 451-454)  
**Read by:** interline statusline renderer

**Format:**
```json
{"name":"codex","workdir":"/path/to/project","started":1707785234}
```

**Lifecycle:** Created on dispatch start, deleted on exit (trap cleanup line 452)

**Purpose:** Enable statusline to show "Codex: <name> in <workdir>" while dispatch is active.

### 4.2 interline Statusline Integration

**Pattern (from research-interline-patterns.md):**
- Plugins write state to `/tmp/clavain-dispatch-*.json` (keyed by PID)
- Statusline reads all matching files, picks highest priority
- 4-layer priority: dispatch state > bead context > workflow phase > clodex mode

**Current limitation:** Only shows **dispatch started**, not progress.

---

## 5. Opportunities for WebSocket Integration

### 5.1 Low-Hanging Fruit: JSONL Capture

**Change:** `dispatch.sh` spawns `codex exec --json` in background, tee stdout to file, parse JSONL in real-time.

**Benefits:**
- Real-time progress updates (which files being edited, tests running)
- Detect hangs/failures before timeout
- Update statusline with granular status (e.g., "Codex: running tests in auth/...")
- Parallel dispatch completion tracking (know which finishes first)

**Implementation sketch:**
```bash
codex exec --json "${ARGS[@]}" > >(tee /tmp/codex-stream-$$.jsonl | parse-codex-stream.py) &
CODEX_PID=$!
wait $CODEX_PID
```

**Challenges:**
- Need parser script to extract state from JSONL stream
- Update `/tmp/clavain-dispatch-$$.json` incrementally
- Handle stream errors/malformed JSON

### 5.2 True WebSocket Mode (Future)

**Concept:** `codex exec --websocket ws://127.0.0.1:<port>` sends events over WebSocket instead of JSONL stdout.

**Why this doesn't exist yet:**
- Codex CLI already has structured event stream (`--json`)
- WebSocket adds complexity without clear benefit over JSONL
- Codex likely has no built-in WebSocket client (it's a CLI tool)

**If Codex added websocket support, benefits:**
- Bi-directional communication (Claude could pause/resume Codex)
- Lower latency than polling JSONL file
- Cleaner integration with Claude Code's async tool system

**Realistic assessment:** Codex CLI maintainers unlikely to add WebSocket support when JSONL already works. Better to build tooling around `--json` mode.

### 5.3 Hybrid: JSONL + File-Based Sideband

**Pattern (already used by interphase/interline):**
- dispatch.sh spawns background parser that reads JSONL stream
- Parser writes state updates to `/tmp/clavain-dispatch-$$.json` (same file, incremental updates)
- Statusline polls this file (current behavior, no changes needed)
- Claude can optionally poll for updates via Bash `cat` (non-blocking)

**Advantages:**
- No changes to Codex CLI
- No changes to statusline renderer
- No WebSocket server overhead
- Works with existing infra

**Disadvantages:**
- File-based polling has ~1s latency (statusline refresh rate)
- Need to handle race conditions (dispatch.sh writing, statusline reading)
- Parser script adds complexity

---

## 6. Related Patterns and References

### 6.1 Oracle CLI (from MEMORY.md)

**Similar pattern:** Oracle browser mode uses `--write-output <path>` instead of stdout redirect because browser mode writes via `console.log` (includes ANSI formatting).

**Lesson:** Tools that emit structured data often have dedicated output flags to avoid shell redirection issues.

**Codex parallel:** `--json` + `-o <file>` work together (JSONL to stdout, final message to file). No conflicts.

### 6.2 Debate Mode (debate.sh)

**Pattern:** Sequential 2-round dispatch with intermediate prompt assembly.

**Flow:**
1. Round 1: dispatch → read output → assemble Round 2 prompt
2. Round 2: dispatch → final output

**No streaming used:** Waits for full completion between rounds.

**Opportunity:** Could use JSONL to show "Round 1: Codex analyzing..." then "Round 2: Codex rebutting..." with substatus.

### 6.3 Split Mode (3-phase dispatch)

**Pattern:** Explore (fast, read-only) → Implement (deep, workspace-write) → Verify (fast, read-only)

**Current overhead:** 3x dispatch calls, each blocking until completion.

**Opportunity:** Streaming would show "Phase 2/3: Implementing..." with file-level detail.

---

## 7. Technical Constraints

### 7.1 Claude Code Bash Tool Limitations

**Key constraint:** Bash tool calls block until command exits. No native async/background execution visibility.

**Workarounds:**
- Use `run_in_background: true` parameter (but lose immediate output)
- Spawn background process, write to file, poll file in subsequent Bash calls
- Use tmux/screen for long-running commands (clodex doesn't currently do this)

**Implication:** Even with JSONL streaming, Claude can't see progress **during** the Bash call. Would need to:
1. Start dispatch in background (run_in_background: true)
2. Poll JSONL file in separate Bash calls
3. Read final output when complete

### 7.2 Timeout Behavior

**Current:** 600000ms (10 minutes) timeout on Bash tool call.

**With background dispatch:**
- Need to handle timeout differently (kill background process, clean up temp files)
- Risk of orphaned Codex processes if Claude's Bash tool times out

### 7.3 JSONL Parsing Complexity

**Events are not guaranteed to be complete JSON objects per line** — need robust parser.

**Error handling:** Stream can contain stderr lines (ERROR logs seen in test output). Parser must skip non-JSON lines.

---

## 8. Recommendations

### 8.1 Short-Term (Minimal Changes)

**Goal:** Capture JSONL stream for post-hoc analysis and debugging.

**Changes:**
- dispatch.sh: Add `--json` flag support, tee stdout to `/tmp/codex-stream-<name>-<timestamp>.jsonl`
- Keep blocking behavior (no background execution)
- Add debug command `/clodex-debug <name>` to read/parse JSONL file after completion

**Benefit:** Richer debugging when verdicts fail, no behavior changes.

### 8.2 Medium-Term (Statusline Updates)

**Goal:** Real-time statusline updates during dispatch.

**Changes:**
- dispatch.sh: Spawn JSONL parser in background (parse-codex-stream.py)
- Parser reads JSONL, updates `/tmp/clavain-dispatch-$$.json` with current item details
- Statusline reads enhanced state (shows "Codex: editing auth.go (3/7 files)")

**Benefit:** User sees progress, Claude doesn't see it (still blocking on Bash call).

### 8.3 Long-Term (Interactive Dispatch)

**Goal:** Claude can see progress and react (e.g., cancel runaway tests).

**Changes:**
- dispatch.sh: Use `run_in_background: true` for Codex dispatch
- New skill: `/clodex-status` polls JSONL file, shows current state
- New skill: `/clodex-cancel <name>` kills Codex process, cleans up
- clodex workflow: dispatch → poll status every 30s → read output when complete

**Benefit:** Full visibility and control, but adds complexity (polling loops, error handling).

**Challenge:** Claude Code's tool system isn't designed for long-polling. Would need explicit poll-in-loop pattern in skill instructions.

---

## 9. Key Findings Summary

1. **Codex already has structured event streaming** via `--json` flag (JSONL to stdout), emitting turn/item lifecycle events.
2. **dispatch.sh currently blocks and discards the stream**, only reading final message from `-o <file>`.
3. **Visibility gap is 5-20+ minutes** during long Codex sessions with no intermediate feedback.
4. **JSONL events contain rich detail**: files being edited, tests running, exit codes, token usage.
5. **Statusline integration exists** but only shows "dispatch started", not progress.
6. **WebSocket mode doesn't exist in Codex CLI** (and isn't needed — JSONL is sufficient).
7. **Low-hanging fruit:** Capture JSONL stream, parse in background, update statusline file for real-time progress visibility.
8. **Full interactivity requires polling pattern** not currently implemented (would need skill changes + background dispatch).

---

## 10. Open Questions

1. **Does Codex CLI support WebSocket natively?** No evidence found. `--json` is the streaming interface.
2. **Can we pause/resume Codex sessions?** `codex exec resume <SESSION_ID>` exists for follow-up prompts, but no mid-execution pause.
3. **What's the latency of JSONL events?** Need empirical testing (likely <1s per event).
4. **How reliable is JSONL parsing?** Need to handle stderr interleaving and malformed lines.
5. **Would background dispatch break existing workflows?** Yes — needs careful migration (polling loops, timeout handling).

---

## Appendix: File Inventory

### Key Files Analyzed

- `/root/projects/Clavain/scripts/dispatch.sh` (458 lines) — core dispatch wrapper
- `/root/projects/Clavain/scripts/debate.sh` (308 lines) — 2-round debate orchestration
- `/root/projects/Clavain/skills/clodex/SKILL.md` (197 lines) — clodex skill instructions
- `/root/projects/Clavain/skills/clodex/references/cli-reference.md` — Codex flag reference
- `/root/projects/Clavain/skills/clodex/references/troubleshooting.md` — common issues
- `/root/projects/Clavain/config/dispatch/tiers.yaml` — model tier configuration
- `~/.codex/config.toml` — Codex CLI user config
- `~/.codex/sessions/` — persisted session transcripts

### Commands Used

```bash
# Discover JSONL streaming
codex exec --help | grep json

# Test JSONL output
codex exec -C /root/projects/Clavain --json -s read-only "echo test"

# Check session persistence
ls -lah ~/.codex/sessions/2026/02/12/

# Version check
codex --version  # 0.101.0
```

---

**Research complete.** Next steps: Decide on integration approach (short/medium/long-term) and prototype JSONL parser.
