# JSONL Stream Parser for dispatch.sh

**Date:** 2026-02-13
**Bead:** Clavain-tb62
**Phase:** brainstorm (as of 2026-02-13T07:54:57Z)
**Status:** Brainstorm complete

## What We're Building

A lightweight inline JSONL stream parser in `scripts/dispatch.sh` that provides real-time activity visibility during Codex dispatches and a post-run summary.

**Problem:** Codex dispatches take 5-20 minutes. During that time, the statusline shows "Clodex: taskname" with zero progress indication. Meanwhile, `codex exec --json` emits rich JSONL events that are completely discarded.

**Solution:** Pipe the JSONL stream through a background awk coprocess that:
1. Updates the dispatch state file with current activity type (live)
2. Accumulates stats and writes a summary after completion

## Why This Approach

**Awk coprocess over bash+jq:** The JSONL events only need top-level field extraction (`type`, `item.type`, `item.status`). Awk handles this without spawning a new process per event (dozens per dispatch). jq would be more robust but the overhead isn't justified for simple field extraction.

**Inline over separate script:** The parser is ~30 lines of awk + ~10 lines of bash glue. Not enough to warrant a separate file and the indirection that comes with it.

**Live activity type (not activity+target):** Showing "running command" vs "editing main.go" is the 80/20 split. Activity type requires only `item.type` parsing; target would require extracting command strings and file paths from nested JSON, adding complexity for marginal value.

## Key Decisions

1. **Parser implementation:** Background awk coprocess reading from pipe
2. **Granularity:** Activity type only ("running command", "thinking", "writing message")
3. **State file:** Reuse existing `/tmp/clavain-dispatch-$$.json`, add `activity` field
4. **Post-run summary:** Written to `<output>.summary` companion file (not appended to -o output — keeps Codex's output clean)
5. **Architecture:** Inline in dispatch.sh (~40 lines total)
6. **Stderr filtering:** Skip non-JSON lines (Codex emits WARNING/ERROR to stdout when --json is used)

## JSONL Event Schema (from real captures)

```jsonl
{"type":"thread.started","thread_id":"019c55ec-..."}
{"type":"turn.started"}
{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"..."}}
{"type":"item.started","item":{"id":"item_1","type":"command_execution","command":"...","status":"in_progress"}}
{"type":"item.completed","item":{"id":"item_1","type":"command_execution","command":"...","aggregated_output":"...","exit_code":0,"status":"completed"}}
{"type":"turn.completed","usage":{"input_tokens":42431,"cached_input_tokens":28800,"output_tokens":704}}
```

**Key fields for parser:**
- `type`: event type (thread.started, turn.started, item.started, item.completed, turn.completed)
- `item.type`: "command_execution" or "agent_message"
- `item.status`: "in_progress" or "completed"
- `usage.input_tokens`, `usage.output_tokens`: token counts per turn

## State File Schema (updated)

```json
{
  "name": "taskname",
  "workdir": "/path/to/project",
  "started": 1234567890,
  "activity": "running command",
  "turns": 3,
  "commands": 5,
  "messages": 4
}
```

The `activity` field is what the statusline reads for live progress. It rotates through:
- `"starting"` — thread.started
- `"thinking"` — turn.started (before any item events)
- `"running command"` — item.started with type=command_execution
- `"writing"` — item.completed with type=agent_message
- `"done"` — turn.completed (final)

## Summary File Format

Written to `<output-path>.summary` after dispatch completes:

```
Dispatch: taskname
Duration: 4m 32s
Turns: 3 | Commands: 5 | Messages: 4
Tokens: 127,431 in / 2,104 out
```

## Interline Statusline Changes

The statusline's Layer 1 (dispatch) already reads from the state file. Only change needed: if `activity` field exists, append it to the display:

Current: `Clodex: taskname`
New: `Clodex: taskname (running command)`

This is a ~3 line change in interline's statusline.sh.

## Open Questions

None — design is fully specified.

## Files to Change

1. `scripts/dispatch.sh` — Add awk coprocess, pipe codex exec through it, write summary on completion
2. `/root/projects/interline/scripts/statusline.sh` — Read `activity` field from dispatch state, append to display
