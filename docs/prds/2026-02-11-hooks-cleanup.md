# PRD: Hooks Cleanup Batch

## Problem

Stop hooks (`auto-compound.sh` and `session-handoff.sh`) can cascade: handoff commits trigger compound, which blocks again. Auto-compound also fires too broadly on routine commits during `/work`. Additionally, `escape_for_json` in `lib.sh` wastes cycles on a 26-iteration control-char loop that's unnecessary for markdown content.

## Solution

Fix the cross-hook cascade bug with a shared sentinel, narrow auto-compound triggers with co-occurrence requirements + opt-out + throttle, and simplify escape_for_json by removing the dead control-char loop.

## Features

### F1: Shared Stop Hook Sentinel (Clavain-8t5l)
**What:** Prevent auto-compound from firing after session-handoff commits by adding a shared sentinel file.
**Acceptance criteria:**
- [ ] Both `auto-compound.sh` and `session-handoff.sh` check for `/tmp/clavain-stop-<SESSION_ID>` sentinel
- [ ] First Stop hook to produce a "block" decision writes the sentinel
- [ ] Second Stop hook sees sentinel and exits cleanly (exit 0, no JSON output)
- [ ] Sentinel uses SESSION_ID from hook input JSON
- [ ] `bash -n` passes on both modified files
- [ ] Existing bats tests still pass

### F2: Narrow Auto-Compound Triggers (Clavain-azlo)
**What:** Reduce false positives by requiring stronger signal co-occurrence, adding per-repo opt-out, and throttling.
**Acceptance criteria:**
- [ ] Raise weight threshold from 2 to 3 (commit alone = 1, needs real resolution/investigation signal)
- [ ] Check for `.claude/clavain.no-autocompound` file — if present, exit immediately
- [ ] Add 5-minute throttle via `/tmp/clavain-compound-last-<SESSION_ID>` timestamp check
- [ ] Remove or downweight the `high-activity` signal (weight 1→0, or remove entirely — bash count alone shouldn't trigger)
- [ ] Remove or downweight `error-fix-cycle` signal (too broad — any error + any edit fires)
- [ ] `bash -n` passes
- [ ] Existing bats tests still pass

### F3: Simplify escape_for_json (Clavain-gw0h)
**What:** Remove the unnecessary control character loop from `escape_for_json` in `lib.sh`.
**Acceptance criteria:**
- [ ] Remove the for-loop (lines 15-22 in current lib.sh) that iterates over control chars 1-31
- [ ] Keep the 7 explicit replacements: `\\`, `"`, `\b`, `\f`, `\n`, `\r`, `\t`
- [ ] Function still produces valid JSON when tested with `session-start.sh | jq .`
- [ ] `bash -n hooks/lib.sh` passes
- [ ] Existing bats tests still pass (`session_start.bats`)

## Non-goals

- Rewriting hooks in Python (that's a separate effort)
- Adding new Stop hooks
- Changing SessionStart hook behavior
- Modifying hooks.json registration

## Dependencies

- None — all changes are to existing files with no external dependencies

## Open Questions

None.
