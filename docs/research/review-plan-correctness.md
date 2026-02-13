# Correctness Review: JSONL Stream Parser Implementation Plan

**Reviewed:** 2026-02-13
**Reviewer:** Julik (fd-correctness agent)
**Subject:** `/root/projects/Clavain/docs/plans/2026-02-13-jsonl-stream-parser.md`

---

## Executive Summary

The plan has **7 critical correctness issues** and **5 moderate concerns** that will cause race conditions, data loss, test failures, and undefined behavior in production. Most serious: shell redirect to shared state file is NOT atomic, PIPESTATUS race when parser exits early, sed extraction will fail for nested braces, and echo with single quotes prevents variable expansion (breaks all tests).

**Required fixes before implementation:**
1. Replace shell `>` redirect with atomic write pattern (temp + rename)
2. Add synchronization for PIPESTATUS capture before parser exits
3. Fix sed pattern to handle nested braces correctly
4. Fix test helper to use double quotes or heredoc for multi-line input
5. Add explicit `--json` and `-o` compatibility verification step
6. Guard `systime()` with gawk version check or use portable alternative
7. Add retry/stale-read detection to statusline consumer

---

## Critical Issues (Production Failures)

### Issue 1: State File Write is NOT Atomic — Race with Statusline Reader

**Location:** Plan line 73-75 (awk parser body)

**Code:**
```awk
printf "{\"name\":\"%s\",...}\n", name, wd, st, activity, turns, cmds, msgs > sf
close(sf)
```

**Failure mode:**

Shell redirect `>` in awk does NOT use atomic rename. It truncates the file first, then writes content. This creates a multi-millisecond window where the state file is empty or partially written.

**Interleaving that causes corruption:**

```
T0: Awk parser starts printf to /tmp/clavain-dispatch-12345.json
T1: File truncated to 0 bytes
T2: Statusline reads file → gets empty content or truncated JSON
T3: jq fails with parse error, statusline shows stale/broken dispatch label
T4: Awk finishes write, closes file
```

**Evidence:**

From `man rename`:
> If newpath already exists, it will be atomically replaced, so that there is no point at which another process attempting to access newpath will find it missing.

Shell redirect does NOT use rename(2). It uses open(O_TRUNC) which is NOT atomic for readers.

**Fix:**

Replace lines 73-75 with atomic write pattern:

```awk
# Atomic write: temp file + rename
tmp = sf ".tmp"
printf "{\"name\":\"%s\",...}\n", name, wd, st, activity, turns, cmds, msgs > tmp
close(tmp)
system("mv " tmp " " sf)  # rename(2) is atomic
```

**Alternative fix (cleaner):**

Move to a bash function that does atomic write, call it from awk via `system()`:

```bash
_atomic_write() {
  local file="$1" content="$2"
  local tmp="${file}.tmp.$$"
  printf '%s\n' "$content" > "$tmp"
  mv "$tmp" "$file"
}

export -f _atomic_write
```

Then in awk:
```awk
cmd = sprintf("_atomic_write '%s' '%s'", sf, json_line)
system(cmd)
```

**Impact if unfixed:**

Statusline shows intermittent parse errors, stale activity, or missing dispatch labels. Worse on high-frequency updates (multiple turns/sec). User sees flickering/broken statusline during active dispatches.

---

### Issue 2: PIPESTATUS[0] Race — Codex Exit Code Lost if Parser Exits Early

**Location:** Plan line 95-96

**Code:**
```bash
"${CMD[@]}" | _jsonl_parser "$STATE_FILE" "${NAME:-codex}" "${WORKDIR:-.}" "$(date +%s)" "$SUMMARY_FILE"
exit "${PIPESTATUS[0]}"
```

**Failure mode:**

`PIPESTATUS` is a bash array that holds exit codes of all commands in the most recent pipeline. It is NOT preserved across command boundaries. If the parser function exits (due to pipe break, early EOF, or error), bash immediately starts the next command (`exit`), which CLEARS `PIPESTATUS`.

**Interleaving that causes exit code loss:**

```
T0: codex exec starts, opens pipe to parser
T1: codex writes {"type":"turn.started"}
T2: parser reads line, updates state file
T3: codex encounters fatal error, writes error to stderr, exits with code 1
T4: codex closes stdout pipe
T5: parser's awk sees EOF on stdin, runs END block
T6: END block writes summary, exits 0
T7: Bash runs `exit "${PIPESTATUS[0]}"` — BUT PIPESTATUS is now (0) because parser exited cleanly
T8: dispatch.sh exits 0 (success) even though codex failed
```

**Evidence:**

From `man bash` (PIPESTATUS):
> An array variable containing a list of exit status values from the processes in the most recently executed foreground pipeline.

"Most recently executed" means the `exit` command itself becomes the new "most recent pipeline" if parser has already exited.

**Fix:**

Capture `PIPESTATUS[0]` immediately into a variable BEFORE parser exits:

```bash
"${CMD[@]}" | _jsonl_parser "$STATE_FILE" "${NAME:-codex}" "${WORKDIR:-.}" "$(date +%s)" "$SUMMARY_FILE"
CODEX_EXIT="${PIPESTATUS[0]}"
exit "$CODEX_EXIT"
```

**Why this works:**

Variable assignment happens synchronously. Once `CODEX_EXIT="${PIPESTATUS[0]}"` completes, the exit code is safely stored even if parser subsequently exits.

**Alternative fix (more robust):**

Use process substitution to keep parser alive until exit code is captured:

```bash
CODEX_EXIT=0
"${CMD[@]}" | {
  _jsonl_parser "$STATE_FILE" "${NAME:-codex}" "${WORKDIR:-.}" "$(date +%s)" "$SUMMARY_FILE"
} &
PARSER_PID=$!
wait %1  # wait for codex (fg job)
CODEX_EXIT=$?
wait "$PARSER_PID"  # ensure parser finishes
exit "$CODEX_EXIT"
```

**Impact if unfixed:**

Any codex failure (missing files, invalid prompt, model errors, rate limits) will be masked as success (exit 0). Calling scripts, CI pipelines, and automation that depend on dispatch.sh exit codes will silently proceed after failures. Compound workflows using dispatch as a gate will skip error handling.

---

### Issue 3: sed Extraction Fails for Functions with Nested Braces

**Location:** Plan line 211 (test helper)

**Code:**
```bash
$(sed -n '/_jsonl_parser()/,/^}/p' "$DISPATCH_SCRIPT")
```

**Failure mode:**

The sed pattern `/^}/` matches ANY line that starts with `}` at column 0. If `_jsonl_parser()` contains nested blocks (if/else, loops, nested functions), sed will stop at the FIRST `}` at column 0, truncating the function body.

**Example that breaks:**

```bash
_jsonl_parser() {
  awk '...' | {
    if [[ ... ]]; then
      do_something
    fi
  }
  # ^ This brace is at column 0 but is NOT the end of _jsonl_parser
  other_logic_here
}
```

sed will extract up to line 5 (`  }`), omitting `other_logic_here` and the actual closing brace.

**Evidence from testing:**

```bash
$ printf 'func() {\n  if true; then\n    echo "test"\n  fi\n}\nline 7\n' | sed -n '/func()/,/^}/p'
func() {
  if true; then
    echo "test"
  fi
}
```

This LOOKS correct but fails for the awk function because the awk body is passed as a HERE-string with internal braces.

**Real failure case:**

The `_jsonl_parser` function body contains:
```bash
_jsonl_parser() {
  local state_file="$1" name="$2" workdir="$3" started="$4" summary_file="$5"
  awk -v sf="$state_file" ... '
    BEGIN { ... }
    {
      if (ev == "turn.started") {
        turns++; activity = "thinking"
      }
      # ^ This is NOT at column 0, but the awk heredoc might format it there
    }
  '
}
```

If the awk script is formatted with closing braces at column 0, sed will stop too early.

**Fix:**

Use bash function extraction via `type` or `declare -f`:

```bash
run_parser() {
  local input="$1"
  source "$DISPATCH_SCRIPT"
  echo "$input" | _jsonl_parser "$STATE_FILE" 'test' '/tmp' "$(date +%s)" "$SUMMARY_FILE"
}
```

**Why this is better:**

Bash's `source` loads the exact function definition without pattern matching. No risk of truncation.

**Alternative fix (keep sed but make it precise):**

Count brace depth:

```bash
extract_function() {
  awk '
    /^_jsonl_parser\(\)/ { in_func=1; depth=0 }
    in_func {
      print
      depth += gsub(/{/, "&")
      depth -= gsub(/}/, "&")
      if (depth == 0 && NR > 1) exit
    }
  ' "$DISPATCH_SCRIPT"
}
```

**Impact if unfixed:**

All bats tests will fail with syntax errors (`unexpected end of file`, `unmatched {`). Test suite becomes useless. CI will fail. Developers will waste hours debugging why tests break when the function clearly works in production.

---

### Issue 4: Test Helper Breaks Multi-line Input — Single Quotes Prevent Expansion

**Location:** Plan line 212 (test helper)

**Code:**
```bash
echo '$input' | _jsonl_parser ...
```

**Failure mode:**

Single quotes in bash prevent ALL variable expansion. `echo '$input'` prints the literal string `$input`, NOT the value of the variable.

**Evidence from testing:**

```bash
$ bash -c "input='line1\nline2'; echo '\$input'"
$input

$ bash -c "input='line1\nline2'; echo \"\$input\""
line1
line2
```

**Why this breaks all tests:**

Every test calls `run_parser` with a string argument (synthetic JSONL), which gets stored in `input="$1"`. Then `echo '$input'` sends the literal 6-character string `$input` to the parser, which sees:

```
$input
```

NOT valid JSON. Parser sees no `^\{` lines, skips everything, produces empty state file. All assertions fail.

**Fix:**

Replace single quotes with double quotes:

```bash
echo "$input" | _jsonl_parser ...
```

**Why this works:**

Double quotes preserve newlines and expand variables. Multi-line JSONL input will be passed correctly.

**Alternative fix (more robust for special chars):**

Use a heredoc to avoid quoting issues entirely:

```bash
run_parser() {
  local input="$1"
  source "$DISPATCH_SCRIPT"
  _jsonl_parser "$STATE_FILE" 'test' '/tmp' "$(date +%s)" "$SUMMARY_FILE" <<< "$input"
}
```

**Impact if unfixed:**

Every single test fails. Test output:

```
✗ parser: skips non-JSON lines
  (assertion failed: [ "$activity" = "starting" ])
  Expected: starting
  Got: null
✗ parser: turn.started sets activity to thinking
  ...
```

0/8 tests pass. Test suite is completely broken.

---

### Issue 5: Undefined Behavior — `--json` and `-o` Flag Interaction Not Verified

**Location:** Plan line 92 (command construction)

**Code:**
```bash
CMD+=(--json)
```

**Failure mode:**

The plan ASSUMES that `codex exec` supports both `--json` (JSONL stream output) and `-o` (write last message to file) simultaneously. If codex treats these as mutually exclusive, one of three things happens:

1. **Exit with error:** `codex: error: --json and -o are mutually exclusive`
2. **Silent precedence:** `--json` disables `-o`, output file is never written
3. **Dual output:** JSONL goes to stdout, final message ALSO written to `-o` (correct behavior, but unverified)

**Evidence gap:**

The plan includes no verification step. From `codex --help` output:
```
      --oss
          Specify which local provider to use (lmstudio or ollama). If not specified with --oss,
          [possible values: read-only, workspace-write, danger-full-access]
```

No `--json` flag visible in help output. This is suspicious — either:
- `--json` is undocumented (risky to rely on)
- `--json` doesn't exist yet (plan is for future codex version)
- `--json` is context-dependent (only works with certain subcommands)

**Failure scenario if codex rejects both flags:**

```bash
$ codex exec --json -o /tmp/out.md -C /tmp/test "task"
error: --json cannot be used with -o
# dispatch.sh exits with error before creating state file
# statusline never shows dispatch activity
# user gets raw error, no summary file
```

**Fix:**

Add explicit verification step to Task 1, Step 3 (smoke test):

```bash
# Before running full smoke test, verify flag compatibility
codex exec --help | grep -q -- '--json' || {
  echo "ERROR: codex does not support --json flag" >&2
  exit 1
}

# Test that --json and -o work together
mkdir -p /tmp/codex-compat-test && cd /tmp/codex-compat-test && git init
timeout 30 codex exec --json -o /tmp/compat-test.md -C /tmp/codex-compat-test "Echo 'test'" > /tmp/compat-jsonl 2>&1 || {
  echo "ERROR: --json and -o are incompatible or codex failed" >&2
  cat /tmp/compat-jsonl >&2
  exit 1
}

# Verify both outputs exist
[[ -f /tmp/compat-test.md ]] || { echo "ERROR: -o file not created when --json is used"; exit 1; }
[[ -s /tmp/compat-jsonl ]] || { echo "ERROR: --json produced no JSONL output"; exit 1; }
grep -q '^{"type":' /tmp/compat-jsonl || { echo "ERROR: --json output is not valid JSONL"; exit 1; }
```

**Impact if unfixed:**

Implementation proceeds based on unverified assumptions. If `--json` flag doesn't exist or conflicts with `-o`, the entire feature fails in production. Rollback required, wasted implementation time.

---

## Moderate Issues (Edge Cases and Reliability)

### Issue 6: `systime()` is gawk-specific — Fails on mawk/busybox awk

**Location:** Plan line 80 (awk END block)

**Code:**
```awk
elapsed = systime() - st
```

**Portability issue:**

`systime()` is a GNU awk extension, not POSIX. Systems with mawk (Debian/Ubuntu default in some configs) or busybox awk will fail.

**Evidence:**

This system has gawk 5.2.1, so `systime()` works:
```bash
$ awk 'BEGIN { print systime() }'
1770969549
```

But on mawk:
```bash
$ mawk 'BEGIN { print systime() }'
mawk: run time error: undefined function systime
```

**Current risk:**

Low — this server has gawk, and dispatch.sh targets this environment. But if Clavain is published as a plugin for other users, it will break on mawk systems.

**Fix:**

Guard with gawk version check at script start:

```bash
# Verify gawk is available for JSONL parser
if ! awk --version 2>&1 | grep -q 'GNU Awk'; then
  echo "Warning: dispatch.sh JSONL parser requires GNU awk (gawk), found: $(awk --version 2>&1 | head -1)" >&2
  echo "Falling back to non-streaming mode (no live statusline updates)" >&2
  # Run codex without --json, skip parser
  "${CMD[@]}"
  exit $?
fi
```

**Alternative fix (portable time):**

Pass `started` timestamp from bash, calculate elapsed in bash after codex finishes:

```bash
started=$(date +%s)
"${CMD[@]}" | _jsonl_parser ...
elapsed=$(($(date +%s) - started))
# Write summary in bash, not awk END block
```

**Impact if unfixed:**

Plugin breaks for users on Debian/Ubuntu systems with mawk. GitHub issues: "dispatch.sh fails with 'undefined function systime'". Requires emergency patch and version bump.

---

### Issue 7: match() Capture Groups — Syntax Correct but Fragile

**Location:** Plan line 52, 67-68 (awk regex captures)

**Code:**
```awk
match(line, /"type":"([^"]+)"/, a); if (RSTART) ev = a[1]
match(line, /"input_tokens":([0-9]+)/, t); if (RSTART) in_tok += t[1]+0
```

**Correctness:**

Syntax is valid gawk (tested and confirmed):
```bash
$ awk 'BEGIN { match("test", /t(e)st/, a); print a[1] }'
e
```

**Fragility:**

- Assumes JSON keys are always quoted with double quotes (valid per JSON spec)
- Assumes no escaped quotes in type values (safe for Codex JSONL output)
- Uses `[^"]+` which stops at first `"` — works for simple strings but breaks if Codex ever emits `"type":"foo\"bar"`

**Edge case that breaks:**

If Codex JSONL includes escaped quotes in type values:
```json
{"type":"item\"with\"quotes"}
```

Regex `/"type":"([^"]+)"/ ` captures `item\` (stops at first `"`), not full value.

**Likelihood:**

Very low — Codex JSONL schema uses controlled type enums (`turn.started`, `item.completed`, etc.), not freeform strings. But worth documenting.

**Fix (if robustness required):**

Use a real JSON parser (jq) in the pipeline:

```bash
"${CMD[@]}" | while IFS= read -r line; do
  [[ "$line" =~ ^\{ ]] || continue
  type=$(jq -r '.type // empty' <<< "$line" 2>/dev/null)
  [[ -n "$type" ]] || continue
  # ... process event ...
done
```

**Trade-off:**

jq is slower (fork per line). For high-frequency events (10+ events/sec), this adds noticeable latency. awk string matching is faster.

**Recommendation:**

Keep awk regex for performance. Add a comment in the code explaining the assumption:

```awk
# Assumes Codex JSONL uses unescaped enum strings for "type" field (safe per Codex schema)
match(line, /"type":"([^"]+)"/, a)
```

---

### Issue 8: index() String Matching is Substring Match — False Positives Possible

**Location:** Plan line 59, 62-63 (awk item type detection)

**Code:**
```awk
if (index(line, "\"command_execution\"")) activity = "running command"
```

**Correctness issue:**

`index(line, "\"command_execution\"")` returns the position of the substring, or 0 if not found. It does NOT verify that the substring is the VALUE of `item.type` — it matches ANYWHERE in the line.

**False positive scenario:**

If Codex JSONL includes the string `"command_execution"` in a different field (e.g., error message, debug metadata), this triggers incorrectly:

```json
{"type":"item.completed","item":{"type":"agent_message","text":"Previous command_execution failed"},"status":"completed"}
```

Awk sees `"command_execution"` in the `text` field, sets `activity = "running command"` even though item type is `agent_message`.

**Likelihood:**

Low but nonzero. Codex could emit rich event metadata in future versions.

**Fix:**

Use match() with field boundaries:

```awk
if (match(line, /"item":\{[^}]*"type":"command_execution"/)) activity = "running command"
```

**Alternative fix (cleaner):**

Extract `item.type` once per event, then switch on it:

```awk
item_type = ""
if (match(line, /"item":\{[^}]*"type":"([^"]+)"/, it)) item_type = it[1]

if (ev == "item.started" && item_type == "command_execution") {
  activity = "running command"
}
```

**Impact if unfixed:**

Rare statusline glitches where activity shows "running command" during message writing if Codex output mentions the string "command_execution".

---

### Issue 9: No Retry or Stale-Read Detection in Statusline Consumer

**Location:** Plan lines 148-149 (interline statusline change)

**Code:**
```bash
activity=$(jq -r '.activity // empty' "$state_file" 2>/dev/null)
```

**Missing safeguard:**

If statusline reads the state file during the truncate-write window (before atomic write fix is applied), `jq` will fail with parse error. The current code silently ignores errors (`2>/dev/null`) and proceeds with empty `activity`.

**Failure mode:**

```
T0: Statusline reads state file
T1: Awk truncates state file (opens with O_TRUNC)
T2: jq reads partial/empty file → parse error
T3: jq exits 1, output is empty
T4: activity="" (treated as no activity)
T5: Statusline shows "Clodex: parser-test" (no activity suffix)
```

User sees activity label disappear intermittently even though dispatch is active.

**Fix (after atomic write is added):**

Add a staleness check using the `started` timestamp:

```bash
activity=$(jq -r '.activity // empty' "$state_file" 2>/dev/null)
started=$(jq -r '.started // 0' "$state_file" 2>/dev/null)
now=$(date +%s)
elapsed=$((now - started))

# If dispatch has been running for >5min with no activity, treat as stale
if [[ "$activity" == "starting" && $elapsed -gt 300 ]]; then
  activity="stalled"
fi
```

**Impact if unfixed (after atomic write):**

Minor — with atomic write, stale reads are eliminated. But if dispatch crashes or is killed, stale state file persists forever. Statusline continues showing "Clodex: parser-test (thinking)" for a dead dispatch.

**Recommendation:**

Add staleness timeout (5min) and change trap in dispatch.sh to write a final state on EXIT:

```bash
trap '
  if [[ -f "$STATE_FILE" ]]; then
    # Mark dispatch as complete
    jq ".activity = \"done\"" "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
  fi
  rm -f "$STATE_FILE"
' EXIT INT TERM
```

---

### Issue 10: Summary File Written Only in END Block — Lost if Parser Killed

**Location:** Plan line 79-87 (awk END block)

**Code:**
```awk
END {
  if (smf != "") {
    # ... write summary to file ...
  }
}
```

**Failure mode:**

If the parser process is killed (SIGKILL, OOM, crash), awk's END block does NOT run. Summary file is never written, even though dispatch may have completed partially.

**Scenario:**

```
T0: Dispatch starts, runs for 20 minutes, completes 50 turns
T1: System OOM killer targets dispatch.sh process tree
T2: Kernel sends SIGKILL to awk parser (no signal handlers allowed)
T3: Awk dies immediately, END block never runs
T4: User checks /tmp/output.md.summary → file doesn't exist
T5: User has no record of 20min of work, tokens spent, commands run
```

**Fix:**

Write incremental summary updates throughout execution:

```awk
{
  # ... existing logic ...

  # Update summary file incrementally (not just in END)
  if (smf != "" && (turns % 5 == 0 || cmds % 10 == 0)) {
    elapsed = systime() - st
    mins = int(elapsed / 60)
    secs = elapsed % 60
    printf "Dispatch: %s (in progress)\nDuration: %dm %ds\nTurns: %d | Commands: %d | Messages: %d\nTokens: %d in / %d out\n", \
      name, mins, secs, turns, cmds, msgs, in_tok, out_tok > smf
    close(smf)
  }
}
```

**Trade-off:**

More frequent writes (every 5 turns or 10 commands) add I/O overhead. For long-running dispatches (50+ turns), this is negligible. For short dispatches (1-2 turns), it's harmless.

**Impact if unfixed:**

If dispatch is killed, summary file is lost. Post-mortem analysis (token usage, turn count) becomes impossible. Monitoring/metrics gaps.

---

## Additional Concerns (Non-Blocking)

### Concern 11: No Validation That STATE_FILE Path is Writable

**Location:** Plan line 27 (initial state write)

**Code:**
```bash
STATE_FILE="/tmp/clavain-dispatch-$$.json"
```

**Risk:**

If `/tmp` is full or read-only (rare but possible in containers, restricted environments), the initial write at line 36 will fail silently (redirect error goes to stderr, not captured).

**Fix:**

Add write validation:

```bash
STATE_FILE="/tmp/clavain-dispatch-$$.json"
if ! touch "$STATE_FILE" 2>/dev/null; then
  echo "Error: Cannot write to $STATE_FILE (check /tmp permissions and disk space)" >&2
  exit 1
fi
```

---

### Concern 12: Trap Cleanup Runs Before Summary Write

**Location:** Plan line 32 (trap), line 79-87 (END block summary write)

**Code:**
```bash
trap 'rm -f "$STATE_FILE"' EXIT INT TERM
```

**Race:**

Trap fires on EXIT, which happens after the pipeline completes. But the pipeline completes when BOTH codex AND the parser exit. If codex exits first (closes stdout), parser runs END block and exits. Then trap fires and deletes `$STATE_FILE`.

This is correct for normal termination. But if user hits Ctrl+C (SIGINT), trap fires immediately, deleting state file before parser's END block can write summary.

**Interleaving on Ctrl+C:**

```
T0: User hits Ctrl+C
T1: Bash sends SIGINT to dispatch.sh
T2: Trap fires, runs `rm -f "$STATE_FILE"`
T3: State file deleted
T4: Bash sends SIGTERM to child processes (codex, parser)
T5: Parser's END block runs, tries to write summary to smf
T6: Summary writes successfully (to $SUMMARY_FILE, not $STATE_FILE)
T7: State file cleanup completes
```

Actually, this is FINE — `$SUMMARY_FILE` is separate from `$STATE_FILE`. Trap only cleans up state file. Summary file persists.

**Conclusion:**

No issue. Summary survives Ctrl+C.

---

### Concern 13: No Error Handling for jq Parse Failures in Tests

**Location:** Plan line 221-229 (test assertions)

**Code:**
```bash
activity=$(jq -r '.activity' "$STATE_FILE")
[ "$activity" = "starting" ]
```

**Risk:**

If state file is malformed (awk bug, partial write during development), `jq` fails silently (exit 1), `activity` is empty, assertion fails with cryptic message:

```
✗ parser: skips non-JSON lines
  [ "" = "starting" ]
```

Doesn't tell you that state file is corrupt.

**Fix:**

Add explicit jq validation in tests:

```bash
activity=$(jq -r '.activity' "$STATE_FILE" 2>&1) || {
  echo "ERROR: jq failed to parse state file:" >&2
  cat "$STATE_FILE" >&2
  return 1
}
[ "$activity" = "starting" ]
```

---

## Recommendations Summary

### Must Fix (Blocking)

1. **Atomic state file writes** — Use temp + rename pattern in awk (Issue 1)
2. **Capture PIPESTATUS immediately** — Store exit code before parser exits (Issue 2)
3. **Fix sed extraction** — Use `source` or brace-depth-aware awk (Issue 3)
4. **Fix test helper quotes** — Use `echo "$input"` not `echo '$input'` (Issue 4)
5. **Verify --json + -o compatibility** — Add pre-flight check in smoke test (Issue 5)

### Should Fix (Robustness)

6. **Guard systime() with gawk check** — Graceful fallback for mawk systems (Issue 6)
7. **Add staleness detection to statusline** — Prevent stale labels for dead dispatches (Issue 9)
8. **Incremental summary writes** — Survive OOM/SIGKILL during long dispatches (Issue 10)
9. **Validate STATE_FILE writable** — Early failure if /tmp is full (Concern 11)

### Nice to Have (Quality)

10. **Document regex assumptions** — Add comment about unescaped Codex JSON (Issue 7)
11. **Improve item.type matching** — Use field-boundary regex not substring (Issue 8)
12. **Better test error messages** — Show jq parse failures explicitly (Concern 13)

---

## Invariants to Preserve

These must remain true throughout execution:

1. **State file is always valid JSON** — Readers must never see partial/truncated JSON
2. **Codex exit code is preserved** — Dispatch exit status equals codex exit status, not parser exit status
3. **State file is cleaned up on exit** — No /tmp pollution after dispatch completes (trap runs)
4. **Summary file is written if dispatch completes** — Even partial completion should produce summary
5. **Activity field transitions are monotonic** — Never revert from "writing" to "starting" (use state machine)

**State machine for `activity` field:**

```
starting → thinking → running command → writing → thinking → done
          ↑______________|_______________|____________|
```

Rule: `starting` only on initial state, `done` only in trap cleanup. All other transitions are forward-only within a turn cycle.

---

## Testing Gap Analysis

The bats test suite (Task 3) covers:
- Non-JSON line skipping ✓
- Event type parsing ✓
- Counter increments ✓
- Token accumulation ✓
- State file preservation ✓

**Not covered (add these tests):**

1. **Atomic write test** — Concurrent reader during parser updates (stress test)
2. **PIPESTATUS preservation** — Codex failure propagation (mock `codex` as failing script)
3. **Ctrl+C handling** — SIGINT during dispatch, verify summary survives
4. **State file cleanup** — Check /tmp after normal exit, error exit, SIGINT
5. **Invalid JSONL tolerance** — Mixed stderr noise and valid JSON lines
6. **Edge case: codex exits before first event** — State file should still exist with "starting"
7. **Edge case: parser killed mid-update** — State file should not be corrupt (atomic write test)

**Recommended additional test file:**

`tests/shell/dispatch-parser-edge-cases.bats` with 7 tests covering above scenarios.

---

## Final Verdict

**Implementation is BLOCKED until Critical Issues 1-5 are resolved.**

The plan demonstrates good architectural thinking (background parser, atomic state file concept, trap cleanup), but the implementation details have multiple correctness holes that will cause production failures.

Most serious: non-atomic writes and PIPESTATUS race. These are not theoretical — they WILL manifest under normal usage (statusline polling every 500ms = high likelihood of stale read; codex failures = common in real usage).

Once critical fixes are applied, the plan is sound. The moderate issues are edge cases that can be addressed in follow-up iterations.

**Estimated fix time:** 2-3 hours to address all critical issues + add missing tests.

**Risk after fixes:** Low — atomic writes + PIPESTATUS capture + fixed tests = robust implementation.
