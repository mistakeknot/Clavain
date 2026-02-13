# JSONL Stream Parser Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Goal:** Add live Codex progress visibility to the statusline and post-run dispatch summaries by parsing the JSONL event stream from `codex exec --json`.

**Architecture:** A background awk coprocess in dispatch.sh reads JSONL events from codex exec's stdout, updates the existing dispatch state file with activity type and counters, and writes a summary file after completion. Interline's statusline reads the new `activity` field from the state file to show live progress.

**Tech Stack:** bash, awk (JSONL parser), jq (statusline reader), bats-core (tests)

**Bead:** Clavain-tb62
**Phase:** planned (as of 2026-02-13T07:56:40Z)

---

### Task 1: Add awk JSONL stream parser to dispatch.sh

**Files:**
- Modify: `scripts/dispatch.sh:449-457` (replace the execution block)

**Step 1: Write the awk parser function and piping logic**

Replace the final execution block (lines 449-457) of `scripts/dispatch.sh` with:

```bash
# Write dispatch state file for statusline visibility
STATE_FILE="/tmp/clavain-dispatch-$$.json"
SUMMARY_FILE=""
if [[ -n "$OUTPUT" ]]; then
  SUMMARY_FILE="${OUTPUT}.summary"
fi
trap 'rm -f "$STATE_FILE"' EXIT INT TERM

# Initial state
printf '{"name":"%s","workdir":"%s","started":%d,"activity":"starting","turns":0,"commands":0,"messages":0}\n' \
  "${NAME:-codex}" "${WORKDIR:-.}" "$(date +%s)" > "$STATE_FILE"

# Awk JSONL parser: reads events, updates state file, accumulates stats.
# Skips non-JSON lines (Codex emits WARNING/ERROR to stderr-in-stdout).
# Uses simple string matching — no JSON library needed for top-level fields.
_jsonl_parser() {
  local state_file="$1" name="$2" workdir="$3" started="$4" summary_file="$5"
  awk -v sf="$state_file" -v name="$name" -v wd="$workdir" -v st="$started" -v smf="$summary_file" '
    BEGIN { turns=0; cmds=0; msgs=0; in_tok=0; out_tok=0; activity="starting" }

    # Skip non-JSON lines (stderr noise from Codex)
    !/^\{/ { next }

    {
      line = $0
      # Extract top-level "type" value
      ev = ""; match(line, /"type":"([^"]+)"/, a); if (RSTART) ev = a[1]

      if (ev == "turn.started") {
        turns++; activity = "thinking"
      }
      else if (ev == "item.started") {
        # Check item.type
        if (index(line, "\"command_execution\"")) activity = "running command"
      }
      else if (ev == "item.completed") {
        if (index(line, "\"command_execution\"")) cmds++
        else if (index(line, "\"agent_message\"")) { msgs++; activity = "writing" }
      }
      else if (ev == "turn.completed") {
        # Extract token counts
        match(line, /"input_tokens":([0-9]+)/, t); if (RSTART) in_tok += t[1]+0
        match(line, /"output_tokens":([0-9]+)/, t); if (RSTART) out_tok += t[1]+0
        activity = "thinking"
      }

      # Update state file
      printf "{\"name\":\"%s\",\"workdir\":\"%s\",\"started\":%d,\"activity\":\"%s\",\"turns\":%d,\"commands\":%d,\"messages\":%d}\n", \
        name, wd, st, activity, turns, cmds, msgs > sf
      close(sf)
    }

    END {
      if (smf != "") {
        elapsed = systime() - st
        mins = int(elapsed / 60)
        secs = elapsed % 60
        printf "Dispatch: %s\nDuration: %dm %ds\nTurns: %d | Commands: %d | Messages: %d\nTokens: %d in / %d out\n", \
          name, mins, secs, turns, cmds, msgs, in_tok, out_tok > smf
        close(smf)
      }
    }
  '
}

# Add --json to capture JSONL stream, pipe through parser
CMD+=(--json)

# Execute: pipe stdout through parser, preserve exit code
"${CMD[@]}" | _jsonl_parser "$STATE_FILE" "${NAME:-codex}" "${WORKDIR:-.}" "$(date +%s)" "$SUMMARY_FILE"
exit "${PIPESTATUS[0]}"
```

**Step 2: Verify syntax**

Run: `bash -n scripts/dispatch.sh`
Expected: No output (clean syntax)

**Step 3: Smoke test with a trivial dispatch**

Run:
```bash
mkdir -p /tmp/codex-parser-test && cd /tmp/codex-parser-test && git init 2>/dev/null
bash /root/projects/Clavain/scripts/dispatch.sh \
  -C /tmp/codex-parser-test \
  -o /tmp/codex-parser-test-output.md \
  --name parser-test \
  "List files in the current directory. Be brief."
```

Verify:
1. `/tmp/codex-parser-test-output.md` exists with Codex output
2. `/tmp/codex-parser-test-output.md.summary` exists with dispatch stats
3. No `/tmp/clavain-dispatch-*.json` left behind (trap cleaned up)

**Step 4: Commit**

```bash
git add scripts/dispatch.sh
git commit -m "feat(dispatch): add JSONL stream parser for live Codex progress"
```

---

### Task 2: Update interline statusline to display activity

**Files:**
- Modify: `/root/projects/interline/scripts/statusline.sh:129-131` (dispatch label construction)

**Step 1: Add activity field to dispatch display**

In `statusline.sh`, find the dispatch label construction (line 130-131):

```bash
      name=$(jq -r '.name // "codex"' "$state_file" 2>/dev/null)
      dispatch_label="$(_il_color "$cfg_color_dispatch" "${dispatch_prefix}: ${name}")"
```

Replace with:

```bash
      name=$(jq -r '.name // "codex"' "$state_file" 2>/dev/null)
      activity=$(jq -r '.activity // empty' "$state_file" 2>/dev/null)
      if [ -n "$activity" ] && [ "$activity" != "starting" ] && [ "$activity" != "done" ]; then
        dispatch_label="$(_il_color "$cfg_color_dispatch" "${dispatch_prefix}: ${name} (${activity})")"
      else
        dispatch_label="$(_il_color "$cfg_color_dispatch" "${dispatch_prefix}: ${name}")"
      fi
```

**Step 2: Verify by running the statusline with a mock state file**

```bash
printf '{"name":"parser-test","workdir":"/tmp","started":1234567890,"activity":"running command","turns":2,"commands":3,"messages":1}\n' > /tmp/clavain-dispatch-$$.json
echo '{"model":{"display_name":"Opus 4.6"},"workspace":{"project_dir":"/root/projects/Clavain"}}' | ~/.claude/statusline.sh
rm -f /tmp/clavain-dispatch-$$.json
```

Expected output contains: `Clodex: parser-test (running command)`

**Step 3: Re-run install.sh to deploy updated statusline**

```bash
bash /root/projects/interline/scripts/install.sh
```

**Step 4: Commit interline changes**

```bash
cd /root/projects/interline
git add scripts/statusline.sh
git commit -m "feat: show Codex activity in dispatch statusline layer"
```

---

### Task 3: Add bats tests for the JSONL parser

**Files:**
- Create: `tests/shell/dispatch-parser.bats`

**Step 1: Write tests**

```bash
#!/usr/bin/env bats

# Tests for JSONL stream parser in dispatch.sh

setup() {
    STATE_FILE="/tmp/clavain-dispatch-test-$$.json"
    SUMMARY_FILE="/tmp/codex-test-$$.md.summary"
    # Source dispatch.sh's parser function by extracting it
    # We test by piping synthetic JSONL through the function
    DISPATCH_SCRIPT="${BATS_TEST_DIRNAME}/../../scripts/dispatch.sh"
}

teardown() {
    rm -f "$STATE_FILE" "$SUMMARY_FILE"
}

# Helper: extract and run the parser with synthetic input
run_parser() {
    local input="$1"
    # Extract _jsonl_parser function from dispatch.sh and run it
    bash -c "
        $(sed -n '/_jsonl_parser()/,/^}/p' "$DISPATCH_SCRIPT")
        echo '$input' | _jsonl_parser '$STATE_FILE' 'test' '/tmp' '$(date +%s)' '$SUMMARY_FILE'
    "
}

@test "parser: skips non-JSON lines" {
    run_parser 'WARNING: some noise
{"type":"thread.started","thread_id":"abc"}
ERROR: more noise'
    [ -f "$STATE_FILE" ]
    activity=$(jq -r '.activity' "$STATE_FILE")
    [ "$activity" = "starting" ]
}

@test "parser: turn.started sets activity to thinking" {
    run_parser '{"type":"turn.started"}'
    activity=$(jq -r '.activity' "$STATE_FILE")
    [ "$activity" = "thinking" ]
    turns=$(jq -r '.turns' "$STATE_FILE")
    [ "$turns" = "1" ]
}

@test "parser: item.started command_execution sets activity" {
    run_parser '{"type":"item.started","item":{"type":"command_execution","command":"ls","status":"in_progress"}}'
    activity=$(jq -r '.activity' "$STATE_FILE")
    [ "$activity" = "running command" ]
}

@test "parser: item.completed agent_message increments messages" {
    run_parser '{"type":"item.completed","item":{"type":"agent_message","text":"hello"}}'
    msgs=$(jq -r '.messages' "$STATE_FILE")
    [ "$msgs" = "1" ]
    activity=$(jq -r '.activity' "$STATE_FILE")
    [ "$activity" = "writing" ]
}

@test "parser: item.completed command_execution increments commands" {
    run_parser '{"type":"item.completed","item":{"type":"command_execution","command":"ls","exit_code":0,"status":"completed"}}'
    cmds=$(jq -r '.commands' "$STATE_FILE")
    [ "$cmds" = "1" ]
}

@test "parser: turn.completed accumulates tokens" {
    run_parser '{"type":"turn.completed","usage":{"input_tokens":1000,"cached_input_tokens":500,"output_tokens":200}}'
    [ -f "$STATE_FILE" ]
}

@test "parser: full session produces correct summary" {
    run_parser '{"type":"thread.started","thread_id":"abc"}
{"type":"turn.started"}
{"type":"item.completed","item":{"type":"agent_message","text":"thinking..."}}
{"type":"item.started","item":{"type":"command_execution","command":"ls","status":"in_progress"}}
{"type":"item.completed","item":{"type":"command_execution","command":"ls","exit_code":0,"status":"completed"}}
{"type":"item.completed","item":{"type":"agent_message","text":"done"}}
{"type":"turn.completed","usage":{"input_tokens":5000,"output_tokens":300}}'
    [ -f "$SUMMARY_FILE" ]
    grep -q "Turns: 1" "$SUMMARY_FILE"
    grep -q "Commands: 1" "$SUMMARY_FILE"
    grep -q "Messages: 2" "$SUMMARY_FILE"
}

@test "parser: state file preserves name and workdir" {
    run_parser '{"type":"turn.started"}'
    name=$(jq -r '.name' "$STATE_FILE")
    [ "$name" = "test" ]
    workdir=$(jq -r '.workdir' "$STATE_FILE")
    [ "$workdir" = "/tmp" ]
}
```

**Step 2: Run tests**

Run: `bats tests/shell/dispatch-parser.bats`
Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/shell/dispatch-parser.bats
git commit -m "test: add bats tests for dispatch JSONL stream parser"
```

---

### Task 4: Integration test — end-to-end dispatch with live statusline

**Files:**
- No new files — manual verification

**Step 1: Run a real dispatch and watch the state file**

In one terminal, watch the state file:
```bash
watch -n 0.5 'cat /tmp/clavain-dispatch-*.json 2>/dev/null | jq . || echo "no dispatch active"'
```

In another, run a dispatch:
```bash
bash scripts/dispatch.sh -C /root/projects/Clavain -o /tmp/e2e-test.md --name e2e-test \
  "Read the README.md, then list the top 5 most important files and explain why."
```

**Step 2: Verify live updates**

Watch the state file — `activity` should cycle through:
1. `starting` (initial)
2. `thinking` (turn starts)
3. `running command` (when Codex runs shell commands)
4. `writing` (when Codex produces messages)

**Step 3: Verify summary**

```bash
cat /tmp/e2e-test.md.summary
```

Expected: Dispatch stats with turns, commands, messages, tokens.

**Step 4: Verify cleanup**

After dispatch completes:
```bash
ls /tmp/clavain-dispatch-*.json 2>/dev/null && echo "LEAK: state file not cleaned up" || echo "OK: state file cleaned up"
```

**Step 5: Final commit — bump version**

```bash
bash scripts/bump-version.sh 0.5.6
```
