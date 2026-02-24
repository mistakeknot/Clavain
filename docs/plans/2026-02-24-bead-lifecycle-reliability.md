# Plan: Bead Lifecycle Reliability — Auto-Close Parents + Universal Claiming

**Bead:** iv-kpoz8
**Complexity:** 3/5 (moderate)
**Plugin:** clavain (lib-sprint.sh, clavain-cli) + interphase (lib-discovery.sh)

---

## Task 1: Add `sprint_close_parent_if_done()` to lib-sprint.sh

**File:** `hooks/lib-sprint.sh` (append after `sprint_close_children()`)

Add a new function that checks upward: if the bead has a parent, and all the parent's children are closed, close the parent.

```bash
# Auto-close parent bead if all its children are now closed.
# Called after sprint ship to propagate completion upward (one level only).
# Usage: sprint_close_parent_if_done <bead_id> [reason]
# Returns: parent bead ID if closed, empty otherwise
sprint_close_parent_if_done() {
    local bead_id="${1:?bead_id required}"
    local reason="${2:-Auto-closed: all children completed}"
    command -v bd &>/dev/null || return 0

    # Get parent from bd show PARENT section
    local parent_id
    parent_id=$(bd show "$bead_id" 2>/dev/null \
        | awk '/^PARENT$/,/^(DEPENDS|CHILDREN|LABELS|NOTES|BLOCKS|DESCRIPTION|COMMENTS|$)/' \
        | grep '↑' \
        | sed 's/.*↑ [○◐●✓❄] //' \
        | cut -d: -f1 \
        | tr -d ' ' \
        | grep -E '^[A-Za-z]+-[A-Za-z0-9]+$' \
        | head -1) || parent_id=""

    [[ -z "$parent_id" ]] && return 0

    # Check if parent is still open (not already closed/deferred)
    local parent_status
    parent_status=$(bd show "$parent_id" 2>/dev/null | head -1) || return 0
    echo "$parent_status" | grep -qE "OPEN|IN_PROGRESS" || return 0

    # Check if all children of parent are closed
    local open_children
    open_children=$(bd show "$parent_id" 2>/dev/null \
        | awk '/^CHILDREN$/,/^(DEPENDS|PARENT|LABELS|NOTES|BLOCKS|DESCRIPTION|COMMENTS|$)/' \
        | grep -cE '↳ [○◐]' 2>/dev/null) || open_children=0

    if [[ "$open_children" -eq 0 ]]; then
        bd close "$parent_id" --reason="$reason" >/dev/null 2>&1 && echo "$parent_id"
    fi
}
```

- [x] Add function to lib-sprint.sh after sprint_close_children
- [x] Test: parent with all children closed → parent gets closed
- [x] Test: parent with one open child → parent stays open
- [x] Test: bead with no parent → no-op

## Task 2: Add `close-parent-if-done` subcommand to clavain-cli

**File:** `bin/clavain-cli`

Add new case to the dispatcher (in the "Child bead management" section):

```bash
    # ── Child bead management ────────────────────────────────────
    close-children)           shift; sprint_close_children "$@" ;;
    close-parent-if-done)     shift; sprint_close_parent_if_done "$@" ;;
```

Update the help text to include:

```
Children:
  close-children            <bead_id> <reason>
  close-parent-if-done      <bead_id> [reason]
```

- [x] Add case to clavain-cli dispatcher
- [x] Add to help text
- [x] Test: `clavain-cli close-parent-if-done <bead_id>` works

## Task 3: Add `bead_claim()` and `bead_release()` to lib-sprint.sh

**File:** `hooks/lib-sprint.sh` (append after close functions)

```bash
# Claim a bead for the current session (advisory lock via bd set-state).
# Usage: bead_claim <bead_id> [session_id]
# Returns: 0 if claimed, 1 if already claimed by another active session
bead_claim() {
    local bead_id="${1:?bead_id required}"
    local session_id="${2:-${CLAUDE_SESSION_ID:-unknown}}"
    command -v bd &>/dev/null || return 0

    # Check existing claim
    local existing_claim existing_at now_epoch age_seconds
    existing_claim=$(bd state "$bead_id" claimed_by 2>/dev/null) || existing_claim=""

    if [[ -n "$existing_claim" && "$existing_claim" != "(no claimed_by state set)" ]]; then
        # Same session? Already claimed by us.
        [[ "$existing_claim" == "$session_id" ]] && return 0

        # Check staleness (2h = 7200s)
        existing_at=$(bd state "$bead_id" claimed_at 2>/dev/null) || existing_at=""
        if [[ -n "$existing_at" && "$existing_at" != "(no claimed_at state set)" ]]; then
            now_epoch=$(date +%s)
            age_seconds=$(( now_epoch - existing_at ))
            if [[ $age_seconds -lt 7200 ]]; then
                local short_session="${existing_claim:0:8}"
                local age_min=$(( age_seconds / 60 ))
                echo "Bead $bead_id claimed by session ${short_session} (${age_min}m ago)" >&2
                return 1
            fi
        fi
    fi

    bd set-state "$bead_id" "claimed_by=$session_id" >/dev/null 2>&1 || true
    bd set-state "$bead_id" "claimed_at=$(date +%s)" >/dev/null 2>&1 || true
    return 0
}

# Release a bead claim.
# Usage: bead_release <bead_id>
bead_release() {
    local bead_id="${1:?bead_id required}"
    command -v bd &>/dev/null || return 0
    bd set-state "$bead_id" "claimed_by=" >/dev/null 2>&1 || true
    bd set-state "$bead_id" "claimed_at=" >/dev/null 2>&1 || true
}
```

- [x] Add bead_claim() to lib-sprint.sh
- [x] Add bead_release() to lib-sprint.sh
- [x] Test: first claim succeeds (exit 0)
- [x] Test: second claim by different session fails (exit 1) within 2h
- [x] Test: same session re-claim succeeds (idempotent)
- [x] Test: stale claim (>2h) gets overridden

## Task 4: Add claim subcommands to clavain-cli

**File:** `bin/clavain-cli`

```bash
    # ── Bead claiming ────────────────────────────────────────────
    bead-claim)              shift; bead_claim "$@" ;;
    bead-release)            shift; bead_release "$@" ;;
```

Update help:

```
Bead Claiming:
  bead-claim              <bead_id> [session_id]
  bead-release            <bead_id>
```

- [x] Add cases to clavain-cli
- [x] Add to help text

## Task 5: Add claim awareness to discovery_scan_beads() in interphase

**File:** `interverse/interphase/hooks/lib-discovery.sh`

In `discovery_scan_beads()`, after the existing stale-parent check (~line 298), add claim checking. For each bead, check `bd state <id> claimed_by`. If claimed by another session and not stale, add `"claimed_by": "<session>"` to the JSON entry and reduce score by 50 (strong deprioritization, but still visible).

The sprint SKILL.md already handles "claimed" display via the action label format — we just need discovery to emit the data.

```bash
# After line ~329 (score computation), before appending to results:
local claimed_by_val
claimed_by_val=$(bd state "$bead_id" claimed_by 2>/dev/null) || claimed_by_val=""
if [[ -n "$claimed_by_val" && "$claimed_by_val" != "(no claimed_by state set)" && "$claimed_by_val" != "${CLAUDE_SESSION_ID:-}" ]]; then
    local claimed_at_val age_sec
    claimed_at_val=$(bd state "$bead_id" claimed_at 2>/dev/null) || claimed_at_val=""
    if [[ -n "$claimed_at_val" && "$claimed_at_val" != "(no claimed_at state set)" ]]; then
        age_sec=$(( $(date +%s) - claimed_at_val ))
        if [[ $age_sec -lt 7200 ]]; then
            score=$((score - 50))
            claimed_by="\"claimed_by\":\"${claimed_by_val:0:8}\","
        else
            # Stale claim — auto-release
            bd set-state "$bead_id" "claimed_by=" >/dev/null 2>&1 || true
            claimed_by=""
        fi
    else
        claimed_by=""
    fi
else
    claimed_by=""
fi
```

Then include `$claimed_by` in the JSON entry construction.

- [x] Add claim check in discovery_scan_beads loop
- [x] Stale claims (>2h) auto-released during scan
- [x] Score penalty (-50) for claimed beads
- [x] claimed_by field included in JSON output
- [x] Test: claimed bead appears with reduced score
- [x] Test: stale claim auto-released

## Task 6: Wire claiming into sprint workflow + session-end cleanup

**File:** `hooks/lib-sprint.sh` — modify `sprint_claim()` to also call `bead_claim()`
**File:** `hooks/session-end-handoff.sh` — add claim release on session end

In `sprint_claim()` (~line 540), after the existing ic-run-based claim succeeds, also set the bd claim:
```bash
bead_claim "$sprint_id" "$session_id" || true
```

In `sprint_release()` (~line 594), also release the bd claim:
```bash
bead_release "$sprint_id" || true
```

In `session-end-handoff.sh`, add near the end:
```bash
# Release any bead claims held by this session
if [[ -n "${CLAVAIN_BEAD_ID:-}" ]]; then
    bead_release "$CLAVAIN_BEAD_ID" 2>/dev/null || true
fi
```

- [x] Wire bead_claim into sprint_claim()
- [x] Wire bead_release into sprint_release()
- [x] Add claim release to session-end-handoff.sh

## Task 7: Wire close-parent-if-done into sprint Step 10

**File:** `hooks/lib-sprint.sh` — modify `sprint_close_children()` to also try closing parent

After the existing downward close sweep in `sprint_close_children()`, add an upward check:

```bash
# After the close loop, try closing parent
sprint_close_parent_if_done "$epic_id" "All children completed under epic $epic_id" || true
```

This way any call to `close-children` automatically does the upward check too.

- [x] Add upward check to sprint_close_children
- [x] Test: sprint ship closes children AND parent when all siblings done

## Task 8: Tests

**File:** `tests/shell/test_bead_lifecycle.bats` (new)

Write bats tests covering:
1. `bead_claim` + `bead_release` lifecycle
2. Claim conflict detection (different session)
3. Stale claim override (>2h)
4. `sprint_close_parent_if_done` with all-closed children
5. `sprint_close_parent_if_done` with open children remaining
6. End-to-end: close-children triggers close-parent-if-done

- [x] Create test file
- [x] All tests pass

---

## Files Changed

| File | Change |
|------|--------|
| `os/clavain/hooks/lib-sprint.sh` | Add sprint_close_parent_if_done, bead_claim, bead_release; wire into sprint_claim/release and close_children |
| `os/clavain/bin/clavain-cli` | Add close-parent-if-done, bead-claim, bead-release subcommands |
| `interverse/interphase/hooks/lib-discovery.sh` | Add claim checking in discovery_scan_beads loop |
| `os/clavain/hooks/session-end-handoff.sh` | Add bead claim release on session end |
| `os/clavain/tests/shell/test_bead_lifecycle.bats` | New test file |
